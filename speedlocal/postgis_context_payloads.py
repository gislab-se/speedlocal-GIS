"""Bounded immutable context text behind a fresh whole-content SQL proof.

The caller owns the read-only transaction and retains all metadata, domain and
semantic validation. This cache changes transport only, never the input refresh
window. The ordinary UTF-8 tuple/text transport returns independently decoded
objects; custom transport and offline cursors retain their original raw reader.
"""
from __future__ import annotations

from collections import OrderedDict
import hashlib
import json
import re
import sys
from threading import RLock
import time

import psycopg
from psycopg import sql
from psycopg.adapt import AdaptersMap
from psycopg.pq import Format
from psycopg.rows import tuple_row
from psycopg.types import json as pg_json
from psycopg.types.string import TextLoader

_default_text_adapters = AdaptersMap()
_default_text_adapters.register_loader(25, TextLoader)
_DEFAULT_TEXT_LOADER = _default_text_adapters.get_loader(25, Format.TEXT)
del _default_text_adapters

_MAX_ENTRIES = 4
_MAX_BYTES = 64 * 1024 * 1024
_TTL_SECONDS = 300
_SHA256 = re.compile(r"[0-9a-f]{64}")
_KIND = re.compile(r"[a-z][a-z0-9_]*")
_entries = OrderedDict()
_bytes = 0
_generation = 0
_lock = RLock()


def clear_context_payload_cache():
    global _bytes, _generation
    with _lock:
        _entries.clear()
        _bytes = 0
        _generation += 1


def _retained_size(value, seen):
    identity = id(value)
    if identity in seen:
        return 0
    seen.add(identity)
    size = sys.getsizeof(value)
    if isinstance(value, (tuple, list)):
        size += sum(_retained_size(item, seen) for item in value)
    return size


def _prune(now):
    global _bytes
    for key, (expires, _rows, charge) in tuple(_entries.items()):
        if expires <= now:
            del _entries[key]
            _bytes -= charge


def _proof(rows):
    if not rows:
        raise ValueError("Current context dataset content gate is empty")
    proof = []
    for row in rows:
        if (not isinstance(row, (tuple, list)) or len(row) != 2
                or type(row[0]) is not str or not _KIND.fullmatch(row[0])
                or type(row[1]) is not str or not _SHA256.fullmatch(row[1])):
            raise ValueError("Current context dataset content gate is invalid")
        proof.append((row[0], row[1]))
    kinds = tuple(kind for kind, _digest in proof)
    if kinds != tuple(sorted(set(kinds))):
        raise ValueError("Current context dataset membership is duplicated or unordered")
    return tuple(proof)


def _decode(rows):
    return tuple((kind, json.loads(encoded)) for kind, encoded in rows)


def _default_json_transport(cursor):
    """Only optimize the app's ordinary transport; preserve custom callbacks."""
    return (cursor.format == Format.TEXT and cursor.row_factory is tuple_row
            and cursor.connection.info.encoding == "utf-8"
            and cursor.adapters.get_loader(25, Format.TEXT) is _DEFAULT_TEXT_LOADER
            and all(cursor.adapters.get_loader(oid, Format.TEXT) is loader
                    and loader._loads is json.loads
                    for oid, loader in ((114, pg_json.JsonLoader), (3802, pg_json.JsonbLoader))))


def read_context_dataset_rows(cursor, binding):
    """Return current ordered rows; independent full semantic checks still follow."""
    global _bytes
    suffix = " from {}.regional_context_datasets where revision_sha256 = %s order by dataset_kind"
    if not isinstance(cursor, psycopg.Cursor) or not _default_json_transport(cursor):
        # Preserve custom public transport/importer rows and decoder error order.
        cursor.execute(sql.SQL("select dataset_kind, payload" + suffix).format(
            sql.Identifier(binding.database_schema)), (binding.revision_sha256,))
        return tuple(cursor.fetchall())

    with _lock:
        generation = _generation
    digest = "encode(pg_catalog.sha256(convert_to(payload::text, 'UTF8')), 'hex')"
    cursor.execute(sql.SQL("select dataset_kind, " + digest + suffix).format(
        sql.Identifier(binding.database_schema)), (binding.revision_sha256,))
    proof = _proof(cursor.fetchall())
    info = cursor.connection.info
    connection = (info.host, info.port, info.dbname, info.user)
    key = (connection, binding.region_id, binding.database_schema,
           binding.revision_sha256, proof)
    with _lock:
        _prune(time.monotonic())
        previous = _entries.get(key)
        if previous is not None:
            _entries.move_to_end(key)
    if previous is not None:
        return _decode(previous[1])

    cursor.execute(sql.SQL("select dataset_kind, payload::text" + suffix).format(
        sql.Identifier(binding.database_schema)), (binding.revision_sha256,))
    rows = cursor.fetchall()
    if len(rows) != len(proof):
        raise ValueError("Context dataset membership changed during content acquisition")
    encoded_rows = []
    for row, (kind, expected_digest) in zip(rows, proof, strict=True):
        if (not isinstance(row, (tuple, list)) or len(row) != 2
                or type(row[0]) is not str or row[0] != kind or type(row[1]) is not str):
            raise ValueError("Context dataset rows changed during content acquisition")
        encoded = row[1].encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() != expected_digest:
            # Also binds the miss for a public READ COMMITTED cursor.
            raise ValueError("Context dataset content changed during acquisition")
        encoded_rows.append((kind, encoded))
    encoded_rows = tuple(encoded_rows)
    decoded = _decode(encoded_rows)
    # JSON null/scalars retain the original semantic rejection and are not kept.
    # Object bytes alone are not semantic approval: the full decoder always runs.
    if not all(type(payload) is dict for _kind, payload in decoded):
        return decoded
    with _lock:
        now = time.monotonic()
        _prune(now)
        expires = now + _TTL_SECONDS
        seen = set()
        # Include every retained nested object plus the OrderedDict overhead.
        # The final charge int has the same size as zero within this byte limit.
        charge = _retained_size(key, seen) + _retained_size((expires, encoded_rows, 0), seen)
        if generation == _generation and key not in _entries and charge < _MAX_BYTES:
            _entries[key] = (expires, encoded_rows, charge)
            _bytes += charge
            while _entries and (len(_entries) > _MAX_ENTRIES
                    or _bytes + sys.getsizeof(_entries) > _MAX_BYTES):
                _, (_expires, _rows, removed) = _entries.popitem(last=False)
                _bytes -= removed
    return decoded
