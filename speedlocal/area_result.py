from __future__ import annotations

import json
import math
import hashlib
from collections import OrderedDict, deque, namedtuple
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import get_ident, RLock
from time import monotonic as _monotonic
import sys
import zlib
from typing import Any, Iterable, Mapping

import h3
import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import Polygon, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree

from .catalogs import load_analysis, load_region
from .contracts import (
    AnalysisContract,
    AnalysisDomainContract,
    LayerContract,
)
from .geometry import (
    GeometryPreviewError,
    VectorBufferPreview,
    WEB_CRS,
    _atomic_geometry_parts,
    _direct_distance_domain_geometries_from_payload,
    _load_validated_source_geometries,
    _metric_crs,
)
from .sources import (
    eligible_surface_contract_for_analysis,
    eligible_surface_level,
    read_analysis_domain_input,
    resolve_analysis_domain_cell_areas_km2,
    resolve_eligible_surface_cell_areas_km2,
)
from .validation import validate_contract, validate_layer


FEASIBILITY_DISSOLVE_MIN_BUFFER_M = 5_000.0
FEASIBILITY_DISSOLVE_MIN_PARTS = 1_000

_EXCLUSION_BATCH_MAX_GROUPS = 64
_EXCLUSION_BATCH_MAX_SLOTS = 262_144
_EXCLUSION_BATCH_MAX_COORDINATES = 250_000


@dataclass(frozen=True)
class AreaCellResult:
    cell_id: str
    model_area_km2: float
    remaining_area_km2: float
    potential_pct: float


@dataclass(frozen=True)
class TechnologyAreaResult:
    region_id: str
    analysis_id: str
    technology: str
    resolution: int
    selected_layer_ids: tuple[str, ...]
    active_group_ids: tuple[str, ...]
    model_area_km2: float
    remaining_area_km2: float
    potential_pct: float
    cells: tuple[AreaCellResult, ...]


@dataclass(frozen=True)
class _BufferedLayerGeometry:
    parts: tuple[BaseGeometry, ...]
    source_feature_count: int
    declared_feature_count: int


_CLIPPING_MAX_ENTRIES = 8
_CLIPPING_MAX_BYTES = 128 * 1024 * 1024
_CLIPPING_MAX_ITEMS = 100_000
_ClippingCacheInfo = namedtuple(
    'ClippingCacheInfo', 'hits misses bypasses currsize retained_bytes peak_retained_bytes',
)


@dataclass
class _ClippingOperation:
    thread_id: int
    implementation: Any
    active: bool = True
    entries: OrderedDict = field(default_factory=OrderedDict)
    retained_bytes: int = 0
    peak_retained_bytes: int = 0
    hits: int = 0
    misses: int = 0
    bypasses: int = 0


@dataclass
class _ClippingDomain:
    operation: _ClippingOperation
    identity: tuple
    active: bool = True


_clipping_operation: ContextVar[_ClippingOperation | None] = ContextVar(
    'speedlocal_clipping_operation', default=None,
)
_clipping_domain: ContextVar[_ClippingDomain | None] = ContextVar(
    'speedlocal_clipping_domain', default=None,
)

# Only validated technology-support feasibility geometry survives an operation.
# No GEOS objects, source inputs, declared areas or user results are retained.
_FEASIBILITY_MAX_ENTRIES = 4
_FEASIBILITY_MAX_BYTES = 16 * 1024 * 1024
_FEASIBILITY_TTL_SECONDS = 300.0
_feasibility_entries: OrderedDict = OrderedDict()
_feasibility_lock = RLock()
_feasibility_generation = 0
_feasibility_hits = 0
_feasibility_misses = 0
_FeasibilityCacheInfo = namedtuple(
    'FeasibilityCacheInfo', 'hits misses currsize retained_bytes',
)


def clear_feasibility_clipping_cache():
    """Release memory and invalidate in-flight admission; retain optional disk files."""
    global _feasibility_generation, _feasibility_hits, _feasibility_misses
    with _feasibility_lock:
        _feasibility_entries.clear()
        _feasibility_generation += 1
        _feasibility_hits = _feasibility_misses = 0
    store = sys.modules.get(__package__ + '.feasibility_store')
    if store is not None:
        store.invalidate()


def _expire_feasibility_entries():
    now = _monotonic()
    for key, entry in tuple(_feasibility_entries.items()):
        if entry[0] <= now:
            del _feasibility_entries[key]


def _feasibility_retained_bytes():
    return sys.getsizeof(_feasibility_entries) + sum(
        entry[4] for entry in _feasibility_entries.values()
    )


def feasibility_clipping_cache_info():
    """Observe bounded immutable storage, without exposing source geometry."""
    with _feasibility_lock:
        _expire_feasibility_entries()
        return _FeasibilityCacheInfo(
            _feasibility_hits, _feasibility_misses, len(_feasibility_entries),
            _feasibility_retained_bytes(),
        )


def _feasibility_key(operation_key, implementation):
    identity, keep_inside, cells, parts = operation_key
    if (keep_inside is not True or identity[1] != 'technology_support'
            or _FEASIBILITY_MAX_ENTRIES <= 0 or _FEASIBILITY_MAX_BYTES <= 0
            or _FEASIBILITY_TTL_SECONDS <= 0):
        return None
    # Length-framed actual ordered WKB, not object identity or revision alone.
    digest = hashlib.sha256()
    for blobs in (cells, parts):
        digest.update(len(blobs).to_bytes(8, 'little'))
        for blob in blobs:
            digest.update(len(blob).to_bytes(8, 'little'))
            digest.update(blob)
    return identity, implementation, digest.digest()


def _prepared_feasibility_get(key):
    global _feasibility_hits, _feasibility_misses
    with _feasibility_lock:
        _expire_feasibility_entries()
        generation = _feasibility_generation
        entry = _feasibility_entries.get(key)
        if entry is None:
            _feasibility_misses += 1
            return None, generation
        _feasibility_entries.move_to_end(key)
    # Decoding and GEOS work never hold the shared bookkeeping lock.
    try:
        _, compressed, lengths, raw_size, _ = entry
        if (len(lengths) > _CLIPPING_MAX_ITEMS
                or not 0 <= raw_size <= _CLIPPING_MAX_BYTES
                or any(type(size) is not int or size < 0 for size in lengths)
                or sum(lengths) != raw_size):
            raise ValueError('Invalid prepared geometry size')
        decoder = zlib.decompressobj()
        raw = decoder.decompress(compressed, raw_size + 1)
        if (len(raw) != raw_size or not decoder.eof
                or decoder.unconsumed_tail or decoder.unused_data):
            raise ValueError('Invalid prepared geometry payload')
        blobs = []
        offset = 0
        for size in lengths:
            blobs.append(raw[offset:offset + size])
            offset += size
        result = shapely.from_wkb(blobs)
    except (ValueError, zlib.error, shapely.errors.GEOSException):
        with _feasibility_lock:
            if _feasibility_entries.get(key) is entry:
                del _feasibility_entries[key]
            _feasibility_misses += 1
        return None, generation
    with _feasibility_lock:
        if generation != _feasibility_generation:
            return None, generation
        _feasibility_hits += 1
    return result, generation


def _prepared_feasibility_put(key, output, generation, *, expires_at_monotonic=None):
    lengths = tuple(map(len, output))
    raw_size = sum(lengths)
    if raw_size > _CLIPPING_MAX_BYTES:
        return
    encoder = zlib.compressobj(level=1)
    compressed = b''.join([encoder.compress(blob) for blob in output] + [encoder.flush()])
    expires = _monotonic() + _FEASIBILITY_TTL_SECONDS
    if expires_at_monotonic is not None:
        if not math.isfinite(expires_at_monotonic):
            return
        expires = min(expires, expires_at_monotonic)
        if expires <= _monotonic():
            return
    charge = _clipping_retained_size((key, (expires, compressed, lengths, raw_size, 0)))
    if charge + sys.getsizeof(OrderedDict()) > _FEASIBILITY_MAX_BYTES:
        return
    with _feasibility_lock:
        if generation != _feasibility_generation:
            return
        _expire_feasibility_entries()
        _feasibility_entries.pop(key, None)
        _feasibility_entries[key] = (expires, compressed, lengths, raw_size, charge)
        while _feasibility_entries and (
            len(_feasibility_entries) > _FEASIBILITY_MAX_ENTRIES
            or _feasibility_retained_bytes() > _FEASIBILITY_MAX_BYTES
        ):
            _feasibility_entries.popitem(last=False)


def _current_clipping_operation() -> _ClippingOperation | None:
    operation = _clipping_operation.get()
    if operation is None or not operation.active or operation.thread_id != get_ident():
        return None
    return operation


@contextmanager
def area_clipping_operation():
    """Share bounded pure clipping output during one synchronous app operation."""
    if _current_clipping_operation() is not None:
        yield
        return
    operation = _ClippingOperation(get_ident(), _clip_cells_with_parts_uncached)
    token = _clipping_operation.set(operation)
    try:
        yield
    finally:
        operation.active = False
        operation.entries.clear()
        operation.retained_bytes = 0
        _clipping_operation.reset(token)


def area_clipping_cache_info():
    """Observe the current owner operation; no geometry or result is exposed."""
    operation = _current_clipping_operation()
    if operation is None:
        return None
    return _ClippingCacheInfo(
        operation.hits, operation.misses, operation.bypasses, len(operation.entries),
        operation.retained_bytes + sys.getsizeof(operation.entries),
        operation.peak_retained_bytes,
    )


@contextmanager
def _area_clipping_domain(domain, metric_crs):
    # Callers establish this only after their ordinary current domain read.
    # Policy, source checks and declared-area arithmetic stay with each caller.
    from .postgis_domain_inputs import DomainDisplayPayload

    operation = _current_clipping_operation()
    scope = None
    if operation is not None and type(domain) is DomainDisplayPayload:
        identity = (
            domain.region_id, domain.role, domain.domain_id, domain.resolution,
            domain.upstream_source_sha256, domain.payload_sha256,
            domain.runtime_revision_sha256, metric_crs.to_wkt(),
        )
        if (type(identity[3]) is int
                and all(type(value) is str and value for value in identity[:3] + identity[4:])
                and sum(len(value) for value in identity[:3] + identity[4:]) <= 16_384):
            scope = _ClippingDomain(operation, identity)
    token = _clipping_domain.set(scope)
    try:
        yield
    finally:
        if scope is not None:
            scope.active = False
        _clipping_domain.reset(token)


def _clipping_geometry_bytes(geometries: np.ndarray) -> tuple[bytes, ...] | None:
    # WKB has no GEOS precision model. Other dimensions/types keep strict execution.
    if (type(geometries) is not np.ndarray or geometries.ndim != 1
            or geometries.dtype != object or len(geometries) > _CLIPPING_MAX_ITEMS):
        return None
    if (not bool(np.all(shapely.is_geometry(geometries)))
            or bool(np.any(shapely.get_precision(geometries) != 0.0))
            or bool(np.any(shapely.get_coordinate_dimension(geometries) != 2))
            or int(np.sum(shapely.get_num_coordinates(geometries))) > _CLIPPING_MAX_BYTES // 16):
        return None
    blobs = tuple(shapely.to_wkb(geometries, include_srid=True, byte_order=1))
    if sys.getsizeof(blobs) + sum(sys.getsizeof(blob) for blob in blobs) > _CLIPPING_MAX_BYTES:
        return None
    return blobs


def _clipping_key(cells, parts, keep_inside, identity):
    if type(keep_inside) is not bool or _CLIPPING_MAX_ENTRIES <= 0 or _CLIPPING_MAX_BYTES <= 0:
        return None
    cell_bytes = _clipping_geometry_bytes(cells)
    if cell_bytes is None:
        return None
    part_bytes = _clipping_geometry_bytes(parts)
    if part_bytes is None:
        return None
    key = (identity, keep_inside, cell_bytes, part_bytes)
    if _clipping_retained_size(key) > _CLIPPING_MAX_BYTES:
        return None
    return key


def _clipping_retained_size(value) -> int:
    # Only flat immutable values/tuples enter here; count repeated references
    # conservatively instead of excluding potentially shared storage.
    return sys.getsizeof(value) + (
        sum(_clipping_retained_size(item) for item in value) if type(value) is tuple else 0
    )


def _clip_cells_with_parts(cells, parts, *, keep_inside):
    operation = _current_clipping_operation()
    scope = _clipping_domain.get()
    if (operation is None or scope is None or not scope.active
            or scope.operation is not operation
            or operation.implementation is not _clip_cells_with_parts_uncached):
        return _clip_cells_with_parts_uncached(cells, parts, keep_inside=keep_inside)
    key = _clipping_key(cells, parts, keep_inside, scope.identity)
    if key is None:
        operation.bypasses += 1
        return _clip_cells_with_parts_uncached(cells, parts, keep_inside=keep_inside)
    cached = operation.entries.get(key)
    if cached is not None:
        operation.hits += 1
        operation.entries.move_to_end(key)
        # Each caller owns its array and GEOS objects; retained output is immutable.
        return shapely.from_wkb(cached[0])
    operation.misses += 1
    prepared_key = _feasibility_key(key, operation.implementation)
    result = None
    if prepared_key is not None:
        result, generation = _prepared_feasibility_get(prepared_key)
    prepared_hit = result is not None
    disk_context = None
    disk_deadline = None
    if prepared_key is not None and not prepared_hit:
        from . import feasibility_store
        disk_context = feasibility_store.lookup(prepared_key, len(cells))
        if disk_context is not None:
            read_started = _monotonic()
            retained = feasibility_store.read(disk_context)
            if retained is not None and generation == _feasibility_generation:
                result, remaining_seconds = retained
                disk_deadline = read_started + remaining_seconds
    if result is None:
        result = _clip_cells_with_parts_uncached(cells, parts, keep_inside=keep_inside)
    output = _clipping_geometry_bytes(result)
    if (output is None or not operation.active or not scope.active
            or _current_clipping_operation() is not operation
            or _clipping_key(cells, parts, keep_inside, scope.identity) != key):
        return result
    if prepared_key is not None and not prepared_hit:
        if disk_deadline is None:
            _prepared_feasibility_put(prepared_key, output, generation)
        else:
            _prepared_feasibility_put(prepared_key, output, generation,
                                      expires_at_monotonic=disk_deadline)
        if (disk_context is not None and disk_deadline is None
                and generation == _feasibility_generation):
            feasibility_store.write(disk_context, output)
    charge = _clipping_retained_size(key) + _clipping_retained_size((output, 0))
    if charge + sys.getsizeof(OrderedDict()) > _CLIPPING_MAX_BYTES:
        return result
    previous = operation.entries.pop(key, None)
    if previous is not None:
        operation.retained_bytes -= previous[1]
    operation.entries[key] = (output, charge)
    operation.retained_bytes += charge
    while operation.entries and (
        len(operation.entries) > _CLIPPING_MAX_ENTRIES
        or operation.retained_bytes + sys.getsizeof(operation.entries) > _CLIPPING_MAX_BYTES
    ):
        _, removed = operation.entries.popitem(last=False)
        operation.retained_bytes -= removed[1]
    operation.peak_retained_bytes = max(
        operation.peak_retained_bytes,
        operation.retained_bytes + sys.getsizeof(operation.entries),
    )
    return result


def _clip_cells_with_parts_uncached(
    cells: np.ndarray,
    parts: np.ndarray,
    *,
    keep_inside: bool,
) -> np.ndarray:
    """Clip cells against a local overlap-safe union of nearby parts."""

    if len(parts) == 0:
        if keep_inside:
            return np.asarray([Polygon() for _ in cells], dtype=object)
        return cells.copy()

    # Query and intersect bounded cell groups before creating GEOS results.
    # The tree, cell order and each cell's ordered part sequence stay the same.
    # A single dense cell can still require an arbitrarily large exact union.
    tree = STRtree(parts)
    if len(cells) <= 512:
        return _clip_cells_with_parts_batch(cells, parts, tree, keep_inside=keep_inside)
    result = np.empty(len(cells), dtype=object)
    if (keep_inside is False
            and type(cells) is np.ndarray and type(parts) is np.ndarray
            and cells.ndim == 1 and parts.ndim == 1
            and cells.dtype == object and parts.dtype == object):
        # Overlap query/intersection work as well as unions. Each worker uses
        # serial inner unions, so a call still has at most two GEOS workers.
        def clip_outer(first):
            return _clip_cells_with_parts_batch(
                cells[first:first + 512], parts, tree,
                keep_inside=False, parallel_unions=False)

        pending = deque()
        starts = iter(range(0, len(cells), 512))
        pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="exclusion-cell-batch")
        try:
            for _ in range(2):
                first = next(starts)
                pending.append((first, pool.submit(clip_outer, first)))
            while pending:
                first, future = pending.popleft()
                geometries = future.result()
                result[first:first + 512] = geometries
                # A Future retains its result. Release it before admitting the
                # next batch; a slow early batch cannot accumulate later ones.
                del geometries, future
                first = next(starts, None)
                if first is not None:
                    pending.append((first, pool.submit(clip_outer, first)))
        finally:
            for _, future in pending:
                future.cancel()
            # Consume errors in input order and leave no workers behind.
            pool.shutdown(wait=True, cancel_futures=True)
        return result
    for first in range(0, len(cells), 512):
        last = min(first + 512, len(cells))
        result[first:last] = _clip_cells_with_parts_batch(
            cells[first:last], parts, tree, keep_inside=keep_inside)
    return result


_PERSISTENT_CLIPPING_IMPLEMENTATION = _clip_cells_with_parts_uncached


def _clip_cells_with_parts_batch(cells, parts, tree, *, keep_inside, parallel_unions=True):
    pairs = tree.query(cells, predicate="intersects")
    if pairs.shape[1] == 0:
        if keep_inside:
            return np.asarray([Polygon() for _ in cells], dtype=object)
        return cells.copy()

    order = np.argsort(pairs[0], kind="stable")
    cell_indices = pairs[0][order]
    part_indices = pairs[1][order]
    intersections = shapely.intersection(
        cells[cell_indices],
        parts[part_indices],
    )
    starts = np.flatnonzero(
        np.r_[True, cell_indices[1:] != cell_indices[:-1]]
    )
    ends = np.r_[starts[1:], len(cell_indices)]
    if keep_inside:
        result = np.asarray([Polygon() for _ in cells], dtype=object)
    else:
        result = cells.copy()
    if keep_inside:
        # Feasibility and source previews retain the precise scalar path.
        for start, end in zip(starts, ends):
            cell_index = int(cell_indices[start])
            local_union = shapely.union_all(intersections[start:end])
            result[cell_index] = local_union
        return result

    sizes = ends - starts
    coordinates_per_group = np.add.reduceat(
        shapely.get_num_coordinates(intersections), starts
    )
    batches: list[tuple[int, int]] = []
    first = 0
    while first < len(starts):
        last = min(first + _EXCLUSION_BATCH_MAX_GROUPS, len(starts))
        # Bound padding and ordinary batch size. A single dense cell still
        # requires its exact union; these limits do not cap native GEOS memory.
        while last > first + 1 and (
            (last - first) * int(np.max(sizes[first:last]))
            > _EXCLUSION_BATCH_MAX_SLOTS
            or int(np.sum(coordinates_per_group[first:last]))
            > _EXCLUSION_BATCH_MAX_COORDINATES
        ):
            last = first + max(1, (last - first) // 2)
        batches.append((first, last))
        first = last

    def clip_batch(bounds: tuple[int, int]) -> tuple[np.ndarray, np.ndarray]:
        first, last = bounds
        width = int(np.max(sizes[first:last]))
        matrix = np.full((last - first, width), None, dtype=object)
        for index in range(first, last):
            # Preserve each cell's original ordered intersection sequence.
            matrix[index - first, :sizes[index]] = intersections[starts[index]:ends[index]]
        unions = shapely.union_all(matrix, axis=1)
        indices = cell_indices[starts[first:last]]
        return indices, shapely.difference(cells[indices], unions)

    if len(batches) == 1 or not parallel_unions:
        for bounds in batches:
            indices, geometries = clip_batch(bounds)
            result[indices] = geometries
    else:
        # Workers own their matrices/results; only this thread places outputs.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="exclusion-union") as pool:
            for indices, geometries in pool.map(clip_batch, batches):
                result[indices] = geometries
    return result


def calculate_remaining_area_cells(
    model_cells: Mapping[str, BaseGeometry],
    model_areas_km2: Mapping[str, float],
    *,
    exclusion_groups: Iterable[Iterable[BaseGeometry]] = (),
    feasibility_groups: Iterable[Iterable[BaseGeometry]] = (),
) -> tuple[AreaCellResult, ...]:
    """Return overlap-safe remaining area using one declared denominator.

    Exclusions are unioned before removal. Each feasibility group is a union
    internally, while multiple feasibility groups are intersected. Geometry
    area is used only to derive the remaining fraction; the final denominator
    is always the manifest-declared model area.
    """

    cell_ids = tuple(str(cell_id) for cell_id in model_areas_km2)
    if not cell_ids or set(cell_ids) != set(model_cells):
        raise ValueError(
            "Model geometries and declared model areas must contain the same cells"
        )
    cells = np.asarray([model_cells[cell_id] for cell_id in cell_ids], dtype=object)
    geometry_areas = np.asarray(shapely.area(cells), dtype=float)
    if not bool(np.all(np.isfinite(geometry_areas) & (geometry_areas > 0.0))):
        raise ValueError("Model-cell geometries must have positive finite area")
    declared_areas = np.asarray(
        [float(model_areas_km2[cell_id]) for cell_id in cell_ids],
        dtype=float,
    )
    if not bool(np.all(np.isfinite(declared_areas) & (declared_areas > 0.0))):
        raise ValueError("Declared model-cell areas must be positive and finite")

    remaining = cells.copy()
    for group in feasibility_groups:
        group_parts = [part for part in group if not part.is_empty]
        remaining = _clip_cells_with_parts(
            remaining,
            np.asarray(group_parts, dtype=object),
            keep_inside=True,
        )
    exclusion_parts = [
        part
        for group in exclusion_groups
        for part in group
        if not part.is_empty
    ]
    if exclusion_parts:
        remaining = _clip_cells_with_parts(
            remaining,
            np.asarray(exclusion_parts, dtype=object),
            keep_inside=False,
        )

    remaining_geometry_areas = np.asarray(shapely.area(remaining), dtype=float)
    fractions = np.divide(
        remaining_geometry_areas,
        geometry_areas,
        out=np.zeros_like(remaining_geometry_areas),
        where=geometry_areas > 0.0,
    )
    fractions = np.clip(fractions, 0.0, 1.0)
    remaining_declared_areas = declared_areas * fractions
    return tuple(
        AreaCellResult(
            cell_id=cell_id,
            model_area_km2=float(model_area),
            remaining_area_km2=float(remaining_area),
            potential_pct=float(fraction * 100.0),
        )
        for cell_id, model_area, remaining_area, fraction in zip(
            cell_ids,
            declared_areas,
            remaining_declared_areas,
            fractions,
        )
    )


def _domain_level(
    contract: AnalysisContract,
    resolution: int,
) -> AnalysisDomainContract:
    domain = contract.analysis_domain
    if domain is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no analysis-domain contract"
        )
    if int(resolution) == int(domain.resolution):
        return domain
    rollup = domain.rollups.get(int(resolution))
    if rollup is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no R{resolution} "
            "analysis-domain rollup"
        )
    return AnalysisDomainContract(
        provider=rollup.provider,
        path=rollup.path,
        sha256=rollup.sha256,
        id_field=rollup.id_field,
        area_field=rollup.area_field,
        area_unit=rollup.area_unit,
        cell_kind=domain.cell_kind,
        resolution=rollup.resolution,
        expected_cell_count=rollup.expected_cell_count,
        expected_total_area_km2=rollup.expected_total_area_km2,
    )


def _requested_resolution(
    contract: AnalysisContract,
    target_resolution: int | None,
) -> int:
    domain = contract.analysis_domain
    if domain is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no analysis-domain contract"
        )
    if target_resolution is None:
        return int(domain.resolution)
    if isinstance(target_resolution, bool) or not isinstance(
        target_resolution,
        int,
    ):
        raise TypeError("target_resolution must be an integer")
    resolution = int(target_resolution)
    if resolution > int(domain.resolution):
        raise ValueError(
            f"Area results must be calculated at R{int(domain.resolution)} "
            f"or rolled up to a coarser declared resolution, not R{resolution}"
        )
    _domain_level(contract, resolution)
    eligible_surface_level(contract, resolution)
    return resolution


def _rollup_cells(
    source_cells: tuple[AreaCellResult, ...],
    target_areas_km2: Mapping[str, float],
    target_resolution: int,
) -> tuple[AreaCellResult, ...]:
    grouped_model_area: dict[str, float] = {}
    grouped_remaining_area: dict[str, float] = {}
    for cell in source_cells:
        parent_id = str(
            h3.cell_to_parent(cell.cell_id, int(target_resolution))
        )
        grouped_model_area[parent_id] = (
            grouped_model_area.get(parent_id, 0.0) + cell.model_area_km2
        )
        grouped_remaining_area[parent_id] = (
            grouped_remaining_area.get(parent_id, 0.0)
            + cell.remaining_area_km2
        )
    if set(grouped_model_area) != set(target_areas_km2):
        missing = sorted(set(target_areas_km2) - set(grouped_model_area))[:5]
        extra = sorted(set(grouped_model_area) - set(target_areas_km2))[:5]
        raise ValueError(
            "R7 area-result children do not cover the declared rollup domain "
            f"(missing={missing}, extra={extra})"
        )
    rows: list[AreaCellResult] = []
    for cell_id, target_area_km2 in target_areas_km2.items():
        source_model_area = grouped_model_area[cell_id]
        if not math.isfinite(source_model_area) or source_model_area <= 0.0:
            raise ValueError(
                f"Area-result rollup cell {cell_id} has no positive R7 area"
            )
        fraction = max(
            0.0,
            min(
                1.0,
                grouped_remaining_area[cell_id] / source_model_area,
            ),
        )
        declared_area = float(target_area_km2)
        rows.append(
            AreaCellResult(
                cell_id=str(cell_id),
                model_area_km2=declared_area,
                remaining_area_km2=declared_area * fraction,
                potential_pct=fraction * 100.0,
            )
        )
    return tuple(rows)


def _buffered_layer_geometry(
    layer: LayerContract,
    *,
    native_crs: str,
    buffer_m: float,
) -> _BufferedLayerGeometry:
    validated = validate_layer(layer)
    parameter = layer.parameters.get("buffer_m")
    if parameter is None or parameter.unit != "m":
        raise ValueError(f"Layer {layer.id} has no metric buffer contract")
    distance = layer.source.additional_buffer_m(parameter.validate_value(buffer_m))
    target_crs = _metric_crs(native_crs)
    source_geometries, source_crs = _load_validated_source_geometries(validated)
    transformer = Transformer.from_crs(
        source_crs,
        target_crs,
        always_xy=True,
    )
    atomic_parts: list[BaseGeometry] = []
    for geometry in source_geometries:
        transformed = transform(transformer.transform, geometry)
        atomic_parts.extend(
            _atomic_geometry_parts(
                transformed,
                validated.geometry_family,
            )
        )
    parts = np.asarray(atomic_parts, dtype=object)
    if distance > 0.0:
        parts = shapely.buffer(parts, distance, quad_segs=16)
    usable = tuple(
        part
        for part in parts
        if not part.is_empty and math.isfinite(float(part.area))
    )
    if not usable:
        raise GeometryPreviewError(
            "area_result_empty",
            f"Layer {layer.id!r} produced no area geometry.",
        )
    return _BufferedLayerGeometry(
        parts=usable,
        source_feature_count=len(source_geometries),
        declared_feature_count=int(validated.assets.feature_count),
    )


def _layer_buffer_parts(
    layer: LayerContract,
    *,
    native_crs: str,
    buffer_m: float,
) -> tuple[BaseGeometry, ...]:
    return _buffered_layer_geometry(
        layer,
        native_crs=native_crs,
        buffer_m=buffer_m,
    ).parts


def build_area_group_preview(
    region: str,
    analysis: str,
    group_id: str,
    layers: Iterable[str],
    buffer_m: float,
) -> VectorBufferPreview:
    """Build the exact, analysis-domain-clipped geometry for one area group.

    The preview uses the same validated source resolver, metric buffering,
    R7 domain geometry and local overlap-safe clipping primitives as the
    technology area calculation. It intentionally avoids the historical
    whole-cell proximity proxy and the much slower global source dissolve.
    """

    contract = load_analysis(str(region), str(analysis))
    validate_contract(contract)
    area_contract = contract.area_result
    if area_contract is None:
        raise ValueError(f"{region}/{analysis} has no area_result contract")
    canonical_group_id = str(group_id)
    if canonical_group_id not in area_contract.applicable_group_ids:
        raise ValueError(
            f"{region}/{analysis} does not apply group {canonical_group_id!r}"
        )
    requested = tuple(str(layer_id) for layer_id in layers)
    if not requested:
        raise ValueError("An area-group preview requires at least one layer")
    if len(requested) != len(set(requested)):
        raise ValueError("Area-group preview layer ids must not contain duplicates")
    unknown = set(requested) - set(contract.layers)
    if unknown:
        raise KeyError(
            f"Layers are not configured for {region}/{analysis}: {sorted(unknown)}"
        )
    selected_layers = tuple(contract.layers[layer_id] for layer_id in requested)
    if any(layer.group_id != canonical_group_id for layer in selected_layers):
        raise ValueError(
            "Every area-group preview layer must belong to the requested group"
        )
    operations = {layer.operation for layer in selected_layers}
    if len(operations) != 1:
        raise ValueError("An area-group preview requires one shared operation")
    operation = operations.pop()

    region_contract = load_region(str(region))
    native_crs = str(region_contract.get("native_crs") or "").strip()
    if not native_crs:
        raise ValueError(f"{region} has no native_crs")
    if contract.analysis_domain is None:
        raise ValueError(f"{region}/{analysis} has no analysis-domain contract")
    source_resolution = int(contract.analysis_domain.resolution)
    domain_level = _domain_level(contract, source_resolution)
    target_crs = _metric_crs(native_crs)
    domain_input = read_analysis_domain_input(
        contract, 'standard_analysis', source_resolution, geometry_use='base_analysis')
    model_cells = _direct_distance_domain_geometries_from_payload(
        domain_level, target_crs, json.loads(domain_input.feature_collection_json))

    parts: list[BaseGeometry] = []
    source_feature_count = 0
    declared_feature_count = 0
    thresholds: list[float] = []
    for layer in selected_layers:
        parameter = layer.parameters.get("buffer_m")
        if parameter is None:
            raise ValueError(f"Layer {layer.id} has no buffer_m contract")
        threshold = parameter.validate_value(buffer_m)
        thresholds.append(threshold)
        buffered = _buffered_layer_geometry(
            layer,
            native_crs=native_crs,
            buffer_m=threshold,
        )
        parts.extend(buffered.parts)
        source_feature_count += buffered.source_feature_count
        declared_feature_count += buffered.declared_feature_count
    if not all(
        math.isclose(value, thresholds[0], rel_tol=0.0, abs_tol=1e-9)
        for value in thresholds
    ):
        raise ValueError("Area-group preview layers must share one threshold")
    if (
        operation == "proximity_feasibility"
        and thresholds[0] >= FEASIBILITY_DISSOLVE_MIN_BUFFER_M
        and len(parts) >= FEASIBILITY_DISSOLVE_MIN_PARTS
    ):
        dissolved = shapely.union_all(np.asarray(parts, dtype=object))
        parts = [
            part
            for part in shapely.get_parts(dissolved)
            if not part.is_empty
        ]

    with _area_clipping_domain(domain_input, target_crs):
        clipped = _clip_cells_with_parts(
            np.asarray(list(model_cells.values()), dtype=object),
            np.asarray(parts, dtype=object),
            keep_inside=True,
        )
    nonempty = [geometry for geometry in clipped if not geometry.is_empty]
    if not nonempty:
        raise GeometryPreviewError(
            "area_group_preview_empty",
            "The exact area-group preview contains no geometry.",
        )
    try:
        native_result = unary_union(nonempty)
    except Exception as exc:
        raise GeometryPreviewError(
            "area_group_preview_union_failed",
            "The exact clipped area-group geometry could not be dissolved.",
        ) from exc
    if (
        native_result.is_empty
        or not native_result.is_valid
        or not all(math.isfinite(float(value)) for value in native_result.bounds)
    ):
        raise GeometryPreviewError(
            "area_group_preview_invalid",
            "The exact clipped area-group geometry is invalid.",
        )
    area_m2 = float(native_result.area)
    cell_ids = tuple(model_cells)
    cell_geometry_areas = np.asarray(
        shapely.area(np.asarray(list(model_cells.values()), dtype=object)),
        dtype=float,
    )
    clipped_geometry_areas = np.asarray(shapely.area(clipped), dtype=float)
    declared_cell_areas_km2 = resolve_analysis_domain_cell_areas_km2(
        contract,
        source_resolution,
    )
    if set(cell_ids) != set(declared_cell_areas_km2):
        raise ValueError(
            "Exact area-group preview cells do not match the declared domain"
        )
    fractions = np.divide(
        clipped_geometry_areas,
        cell_geometry_areas,
        out=np.zeros_like(clipped_geometry_areas),
        where=cell_geometry_areas > 0.0,
    )
    fractions = np.clip(fractions, 0.0, 1.0)
    # The public percentages are reported on a 0–100 scale. A 1e-12
    # percentage tolerance therefore corresponds to 1e-14 as a fraction.
    zero_cell_count = int(np.count_nonzero(fractions <= 1e-14))
    full_cell_count = int(np.count_nonzero(fractions >= 1.0 - 1e-14))
    partial_cell_count = int(len(fractions) - zero_cell_count - full_cell_count)
    model_area_m2 = math.fsum(
        float(declared_cell_areas_km2[cell_id])
        * float(fraction)
        * 1_000_000.0
        for cell_id, fraction in zip(cell_ids, fractions)
    )
    try:
        to_web = Transformer.from_crs(target_crs, WEB_CRS, always_xy=True)
        web_geometry = transform(to_web.transform, native_result)
    except Exception as exc:
        raise GeometryPreviewError(
            "area_group_preview_transform_failed",
            "The exact clipped area-group geometry could not be transformed.",
        ) from exc
    if not web_geometry.is_valid:
        web_geometry = shapely.make_valid(web_geometry)
        polygon_parts = [
            part
            for part in shapely.get_parts(web_geometry)
            if "Polygon" in part.geom_type and not part.is_empty
        ]
        if polygon_parts:
            web_geometry = unary_union(polygon_parts)
    if web_geometry.is_empty or not web_geometry.is_valid:
        raise GeometryPreviewError(
            "area_group_preview_web_invalid",
            "The transformed exact area-group geometry is invalid.",
        )
    distance = float(thresholds[0])
    return VectorBufferPreview(
        geojson={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "analysis_id": str(analysis),
                        "group_id": canonical_group_id,
                        "layer_ids": list(requested),
                        "native_crs": target_crs.to_string(),
                        "buffer_m": distance,
                        "operation": operation,
                        "source_h3_resolution": source_resolution,
                        "semantics": "exact_area_clip",
                    },
                    "geometry": mapping(web_geometry),
                }
            ],
        },
        layer_ids=requested,
        native_crs=target_crs.to_string(),
        buffer_m=distance,
        semantics="exact_area_clip",
        geometry_type=web_geometry.geom_type,
        source_feature_count=source_feature_count,
        declared_feature_count=declared_feature_count,
        area_m2=area_m2,
        model_area_m2=model_area_m2,
        zero_cell_count=zero_cell_count,
        partial_cell_count=partial_cell_count,
        full_cell_count=full_cell_count,
    )


def run_area_analysis(
    region: str,
    analysis: str,
    layers: Iterable[str],
    parameters: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    target_resolution: int | None = None,
) -> TechnologyAreaResult:
    """Run the manifest-declared exact vector area contract."""

    contract = load_analysis(region, analysis)
    validate_contract(contract)
    area_contract = contract.area_result
    if area_contract is None:
        raise ValueError(f"{region}/{analysis} has no area_result contract")
    requested = tuple(str(layer_id) for layer_id in layers)
    if len(requested) != len(set(requested)):
        raise ValueError("Area analysis layer ids must not contain duplicates")
    unknown = set(requested) - set(contract.layers)
    if unknown:
        raise KeyError(
            f"Layers are not configured for {region}/{analysis}: {sorted(unknown)}"
        )
    resolution = _requested_resolution(contract, target_resolution)
    region_contract = load_region(region)
    native_crs = str(region_contract.get("native_crs") or "").strip()
    if not native_crs:
        raise ValueError(f"{region} has no native_crs")

    selected_by_group: dict[str, list[LayerContract]] = {}
    for layer_id in requested:
        layer = contract.layers[layer_id]
        if layer.group_id not in area_contract.applicable_group_ids:
            raise ValueError(
                f"Layer {layer_id} group {layer.group_id} is not applicable "
                f"to {area_contract.technology}"
            )
        selected_by_group.setdefault(layer.group_id, []).append(layer)

    exclusion_groups: list[tuple[BaseGeometry, ...]] = []
    feasibility_groups: list[tuple[BaseGeometry, ...]] = []
    active_group_ids: list[str] = []
    for group_id in area_contract.applicable_group_ids:
        group_layers = selected_by_group.get(group_id, [])
        if not group_layers:
            continue
        operations = {layer.operation for layer in group_layers}
        if len(operations) != 1:
            raise ValueError(
                f"Area-result group {group_id} must use one operation"
            )
        operation = operations.pop()
        thresholds: list[float] = []
        group_parts: list[BaseGeometry] = []
        for layer in group_layers:
            parameter = layer.parameters.get("buffer_m")
            if parameter is None:
                raise ValueError(f"Layer {layer.id} has no buffer_m contract")
            raw_value = (parameters or {}).get(layer.id, {}).get(
                "buffer_m",
                parameter.default,
            )
            threshold = parameter.validate_value(raw_value)
            thresholds.append(threshold)
            group_parts.extend(
                _layer_buffer_parts(
                    layer,
                    native_crs=native_crs,
                    buffer_m=threshold,
                )
            )
        if not all(
            math.isclose(value, thresholds[0], rel_tol=0.0, abs_tol=1e-9)
            for value in thresholds
        ):
            raise ValueError(
                f"Area-result group {group_id} layers must share one threshold"
            )
        if operation in {"distance_exclusion", "hard_exclusion"}:
            exclusion_groups.append(tuple(group_parts))
        elif operation == "proximity_feasibility":
            if (
                thresholds[0] >= FEASIBILITY_DISSOLVE_MIN_BUFFER_M
                and len(group_parts) >= FEASIBILITY_DISSOLVE_MIN_PARTS
            ):
                dissolved = shapely.union_all(
                    np.asarray(group_parts, dtype=object)
                )
                group_parts = [
                    part
                    for part in shapely.get_parts(dissolved)
                    if not part.is_empty
                ]
            feasibility_groups.append(tuple(group_parts))
        else:
            raise ValueError(
                f"Area-result group {group_id} has unsupported operation {operation}"
            )
        active_group_ids.append(group_id)

    surface = eligible_surface_contract_for_analysis(contract)
    source_resolution = int(surface.resolution)
    surface_level = eligible_surface_level(contract, source_resolution)
    target_crs = _metric_crs(native_crs)
    source_model_areas_km2 = resolve_eligible_surface_cell_areas_km2(
        contract,
        source_resolution,
    )
    domain_input = read_analysis_domain_input(
        contract, 'technology_support', source_resolution, geometry_use='base_analysis')
    model_cells = _direct_distance_domain_geometries_from_payload(
        surface_level, target_crs, json.loads(domain_input.feature_collection_json))
    with _area_clipping_domain(domain_input, target_crs):
        source_cells = calculate_remaining_area_cells(
            model_cells,
            source_model_areas_km2,
            exclusion_groups=exclusion_groups,
            feasibility_groups=feasibility_groups,
        )
    cells = source_cells
    if resolution < source_resolution:
        cells = _rollup_cells(
            source_cells,
            resolve_eligible_surface_cell_areas_km2(contract, resolution),
            resolution,
        )
    model_area_km2 = math.fsum(cell.model_area_km2 for cell in cells)
    remaining_area_km2 = math.fsum(
        cell.remaining_area_km2 for cell in cells
    )
    return TechnologyAreaResult(
        region_id=region,
        analysis_id=analysis,
        technology=area_contract.technology,
        resolution=resolution,
        selected_layer_ids=requested,
        active_group_ids=tuple(active_group_ids),
        model_area_km2=model_area_km2,
        remaining_area_km2=remaining_area_km2,
        potential_pct=(remaining_area_km2 / model_area_km2 * 100.0),
        cells=cells,
    )


def rollup_native_area_result(
    contract: AnalysisContract,
    native_result: TechnologyAreaResult,
    target_resolution: int,
) -> TechnologyAreaResult:
    """Derive one target directly from original ordered native cell results.

    The workspace boundary owns request/revision validation. This pure rollup
    retains the established additions, declared parent denominator and totals.
    It never rebuilds buffers or clips geometry and never chains parent cells.
    """

    resolution = _requested_resolution(contract, target_resolution)
    surface = eligible_surface_contract_for_analysis(contract)
    if (
        contract.area_result is None
        or native_result.region_id != contract.region_id
        or native_result.analysis_id != contract.id
        or native_result.technology != contract.area_result.technology
        or native_result.resolution != int(surface.resolution)
    ):
        raise ValueError("Area rollup requires this contract's native result")
    if resolution == native_result.resolution:
        return native_result
    cells = _rollup_cells(
        native_result.cells,
        resolve_eligible_surface_cell_areas_km2(contract, resolution),
        resolution,
    )
    model_area_km2 = math.fsum(cell.model_area_km2 for cell in cells)
    remaining_area_km2 = math.fsum(cell.remaining_area_km2 for cell in cells)
    return TechnologyAreaResult(
        region_id=native_result.region_id,
        analysis_id=native_result.analysis_id,
        technology=native_result.technology,
        resolution=resolution,
        selected_layer_ids=native_result.selected_layer_ids,
        active_group_ids=native_result.active_group_ids,
        model_area_km2=model_area_km2,
        remaining_area_km2=remaining_area_km2,
        potential_pct=(remaining_area_km2 / model_area_km2 * 100.0),
        cells=cells,
    )
