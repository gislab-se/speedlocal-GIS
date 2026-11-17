"""Optional exact clipping sidecars, read only after current input validation.

Six fixed slots contain derived WKB, never an input-provider fallback. Request
scopes are owned by one thread/PostGIS operation. Invalidation fences in-flight
use and admission; it deliberately preserves files, which require fresh input
identities again on every subsequent lookup.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import struct
from threading import RLock, get_ident
import time
import zlib

import numpy as np
import shapely

from .catalogs import load_region
from .native_area_store import ROOT_ENV, _implementation_identity, _writer_lock
from .sources import _current_postgis_operation, _postgis_database_url

SCHEMA = "native-feasibility-1"
MAGIC = b"SLFG\x01"
MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_HEADER_BYTES = 2 * 1024 * 1024
MAX_RAW_BYTES = 128 * 1024 * 1024
MAX_ITEMS = 100_000
MAX_AGE_SECONDS = 24 * 60 * 60
_REGIONS = frozenset(("bornholm", "skaraborg", "trondelag"))
_lock = RLock()
_generation = 0


@dataclass
class _Scope:
    region: str
    analysis: str
    access: str
    contract_signature: str
    aliases: tuple[str, ...]
    root: Path
    operation: object
    thread_id: int
    generation: int
    active: bool = True


@dataclass(frozen=True)
class _Lookup:
    scope: _Scope
    path: Path
    key: str
    expected_count: int
    generation: int


_scope: ContextVar[_Scope | None] = ContextVar("speedlocal_feasibility_store", default=None)


def invalidate():
    """Fence this process's in-flight lookups/writes; do not remove disk files."""
    global _generation
    with _lock:
        _generation += 1


@contextmanager
def request_scope(contract, request):
    """Enable a narrow engine call without doing eager input/config validation."""
    configured = os.environ.get(ROOT_ENV, "").strip()
    scope = None
    operation = _current_postgis_operation() if configured else None
    if (configured and operation is not None and request.region_id in _REGIONS
            and request.analysis_id in {"wind", "solar"}
            and contract.region_id == request.region_id and contract.id == request.analysis_id
            and request.access_scope in {"product:" + request.region_id, "review:" + request.region_id}):
        aliases = set()
        for layer_id in request.selected_layer_ids:
            layer = contract.layers.get(layer_id)
            reference = layer.source.postgis_reference if layer is not None else None
            if reference is None:
                break
            aliases.add(reference.connection_alias)
        else:
            if aliases:
                with _lock:
                    scope = _Scope(request.region_id, request.analysis_id, request.access_scope,
                                   request.contract_signature_sha256, tuple(sorted(aliases)),
                                   Path(configured).expanduser(), operation, get_ident(), _generation)
    token = _scope.set(scope)
    try:
        yield
    finally:
        if scope is not None:
            scope.active = False
        _scope.reset(token)


def _valid(scope, generation):
    return (scope is not None and scope.active and scope.thread_id == get_ident()
            and _scope.get() is scope and generation == scope.generation == _generation
            and _current_postgis_operation() is scope.operation)


def _production_kernel(kernel):
    from . import area_result
    sentinel = getattr(area_result, "_PERSISTENT_CLIPPING_IMPLEMENTATION", None)
    return sentinel is not None and kernel is sentinel and area_result._clip_cells_with_parts_uncached is sentinel


def lookup(prepared_key, expected_count):
    """Bind validated actual inputs; current connection/config errors propagate."""
    scope = _scope.get()
    if (scope is None or not _valid(scope, scope.generation)
            or type(expected_count) is not int or not 0 <= expected_count <= MAX_ITEMS
            or type(prepared_key) is not tuple or len(prepared_key) != 3):
        return None
    identity, kernel, geometry_digest = prepared_key
    if (type(identity) is not tuple or len(identity) != 8
            or identity[:2] != (scope.region, "technology_support")
            or type(identity[3]) is not int
            or not all(type(value) is str and value for value in identity[:3] + identity[4:])
            or sum(map(len, identity[:3] + identity[4:])) > 16_384
            or type(geometry_digest) is not bytes or len(geometry_digest) != 32
            or not _production_kernel(kernel)):
        return None
    load_region(scope.region)
    connections = [(alias, hashlib.sha256(_postgis_database_url(alias).encode()).hexdigest())
                   for alias in scope.aliases]
    payload = {"schema": SCHEMA, "implementation": _implementation_identity(),
               "scope": [scope.region, scope.analysis, scope.access, scope.contract_signature],
               "connections": connections, "domain": identity,
               "geometry_sha256": geometry_digest.hex(), "count": expected_count}
    key = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                   ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    try:
        if scope.root.is_symlink():
            return None
        folder = scope.root.resolve() / SCHEMA
        if folder.is_symlink():
            return None
    except OSError:
        return None
    with _lock:
        if not _valid(scope, scope.generation):
            return None
        return _Lookup(scope, folder / f"{scope.region}-{scope.analysis}.slfg", key,
                       expected_count, scope.generation)


def _current(context):
    from . import area_result
    return (type(context) is _Lookup and _valid(context.scope, context.generation)
            and _production_kernel(area_result._clip_cells_with_parts_uncached))


def _remaining(created):
    if type(created) not in (int, float) or not math.isfinite(created):
        return None
    age = time.time() - created
    return MAX_AGE_SECONDS - age if 0 <= age < MAX_AGE_SECONDS else None


def read(context):
    """Return independently decoded exact geometry and its remaining disk TTL."""
    if not _current(context):
        return None
    try:
        path = context.path
        if (context.scope.root.is_symlink() or path.parent.is_symlink() or path.is_symlink()
                or path.stat().st_size > MAX_ENTRY_BYTES):
            return None
        with path.open("rb") as stream:
            data = stream.read(MAX_ENTRY_BYTES + 1)
        if len(data) > MAX_ENTRY_BYTES or not data.startswith(MAGIC):
            return None
        prefix = len(MAGIC) + 4
        header_size = struct.unpack("<I", data[len(MAGIC):prefix])[0]
        if not 0 < header_size <= MAX_HEADER_BYTES or prefix + header_size >= len(data):
            return None
        header = json.loads(data[prefix:prefix + header_size])
        if (set(header) != {"schema", "key", "created", "count", "lengths", "raw_size", "raw_sha256"}
                or header["schema"] != SCHEMA or header["key"] != context.key
                or type(header["count"]) is not int or header["count"] != context.expected_count
                or type(header["lengths"]) is not list or len(header["lengths"]) != context.expected_count
                or any(type(size) is not int or size <= 0 for size in header["lengths"])
                or type(header["raw_size"]) is not int or not 0 <= header["raw_size"] <= MAX_RAW_BYTES
                or sum(header["lengths"]) != header["raw_size"]
                or _remaining(header["created"]) is None):
            return None
        decoder = zlib.decompressobj()
        raw = decoder.decompress(data[prefix + header_size:], header["raw_size"] + 1)
        if (len(raw) != header["raw_size"] or not decoder.eof or decoder.unconsumed_tail
                or decoder.unused_data or hashlib.sha256(raw).hexdigest() != header["raw_sha256"]):
            return None
        blobs, offset = [], 0
        for size in header["lengths"]:
            blobs.append(raw[offset:offset + size])
            offset += size
        result = shapely.from_wkb(blobs)
        if (type(result) is not np.ndarray or result.dtype != object or result.ndim != 1
                or len(result) != context.expected_count or not bool(np.all(shapely.is_geometry(result)))
                or bool(np.any(shapely.get_precision(result) != 0.0))
                or bool(np.any(shapely.get_coordinate_dimension(result) != 2))):
            return None
        remaining = _remaining(header["created"])
        with _lock:
            return (result, remaining) if remaining is not None and _current(context) else None
    except (OSError, ValueError, TypeError, KeyError, OverflowError, struct.error,
            zlib.error, shapely.errors.GEOSException):
        return None


def write(context, output):
    """Write one bounded fixed slot atomically; failure leaves precise execution."""
    if (not _current(context) or type(output) is not tuple or len(output) != context.expected_count
            or any(type(blob) is not bytes or not blob for blob in output)):
        return False
    lengths = tuple(map(len, output))
    raw_size = sum(lengths)
    if raw_size > MAX_RAW_BYTES:
        return False
    encoder, digest = zlib.compressobj(level=1), hashlib.sha256()
    pieces, compressed_size = [], 0
    for blob in output:
        digest.update(blob)
        piece = encoder.compress(blob)
        compressed_size += len(piece)
        if compressed_size > MAX_ENTRY_BYTES:
            return False
        pieces.append(piece)
    pieces.append(encoder.flush())
    header = json.dumps({"schema": SCHEMA, "key": context.key, "created": time.time(),
                         "count": context.expected_count, "lengths": lengths,
                         "raw_size": raw_size, "raw_sha256": digest.hexdigest()},
                        separators=(",", ":"), allow_nan=False).encode()
    if (len(header) > MAX_HEADER_BYTES
            or len(MAGIC) + 4 + len(header) + sum(map(len, pieces)) > MAX_ENTRY_BYTES):
        return False
    path, folder = context.path, context.path.parent
    temporary, writer_lock = path.with_suffix(".tmp"), path.with_suffix(".lock")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if any(p.is_symlink() for p in (context.scope.root, folder, path, temporary, writer_lock)):
            return False
        with _writer_lock(writer_lock):
            try:
                if not _current(context):
                    return False
                with temporary.open("wb") as stream:
                    stream.write(MAGIC + struct.pack("<I", len(header)) + header)
                    for piece in pieces:
                        stream.write(piece)
                    stream.flush()
                    os.fsync(stream.fileno())
                with _lock:
                    if not _current(context):
                        return False
                    os.replace(temporary, path)
                    return _current(context)
            finally:
                if temporary.exists() and not temporary.is_symlink():
                    temporary.unlink()
    except OSError:
        return False
