"""Reuse revision descriptors behind a live, whole-content SQL SHA-256 gate.

Large display descriptors are metadata too: transferring them repeatedly can
dominate an interaction. Every lookup still reads the current row and hashes
its entire JSONB content in that transaction. Full input/geography readers keep
their existing independent row validation and refresh policy.
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

from .postgis_runtime import RuntimeBinding, canonical_json


_MAX_ENTRIES = 8
_MAX_BYTES = 64 * 1024 * 1024
_TTL_SECONDS = 30
_entries = OrderedDict()
_bytes = 0
_generation = 0
_lock = RLock()
_SHA256 = re.compile(r"[0-9a-f]{64}")


def clear_revision_metadata_cache():
    global _bytes, _generation
    with _lock:
        _entries.clear()
        _bytes = 0
        _generation += 1


def _prune(now):
    global _bytes
    for key, (expires, _, _, charge) in tuple(_entries.items()):
        if expires <= now:
            del _entries[key]
            _bytes -= charge


def _canonical_digest(metadata):
    return hashlib.sha256(canonical_json(metadata).encode("utf-8")).hexdigest()


def read_analysis_revision_metadata(cursor, binding: RuntimeBinding):
    """Compatibility reader returning only independently decoded rows."""
    return read_analysis_revision_metadata_with_digest(cursor, binding)[0]


def read_analysis_revision_metadata_with_digest(cursor, binding: RuntimeBinding):
    """Return (independent rows, canonical digest) from the current cursor.

    Public/offline cursor fixtures retain the original full-read seam. Runtime
    PostgreSQL cursors require no extension: SHA-256 is built into PostgreSQL.
    The live digest is an additional transport identity, not the application's
    canonical revision signature. Callers still check shape, expected revision
    and membership; a cached signature belongs only to the immutable bytes.
    """
    global _bytes
    full = sql.SQL(
        "select region_id, metadata from {}.analysis_runtime_revisions "
        "where revision_sha256 = %s"
    ).format(sql.Identifier(binding.database_schema))
    if not isinstance(cursor, psycopg.Cursor):
        cursor.execute(full, (binding.revision_sha256,))
        # Preserve importer/fixture validation order in the consumers.
        return cursor.fetchall(), None
    digest_sql = "encode(pg_catalog.sha256(convert_to(metadata::text, 'UTF8')), 'hex')"
    gate = sql.SQL(
        "select region_id, " + digest_sql + " from {}.analysis_runtime_revisions "
        "where revision_sha256 = %s"
    ).format(sql.Identifier(binding.database_schema))
    cursor.execute(gate, (binding.revision_sha256,))
    rows = cursor.fetchall()
    if (len(rows) != 1 or rows[0][0] != binding.region_id
            or type(rows[0][1]) is not str or not _SHA256.fullmatch(rows[0][1])):
        raise ValueError("Current runtime revision content gate is invalid")
    live_digest = rows[0][1]
    info = cursor.connection.info
    # Connection identity excludes credentials; every caller still exercises
    # current SELECT permission through the live gate, including on cache hits.
    connection = (info.host, info.port, info.dbname, info.user)
    key = (connection, binding.region_id, binding.database_schema,
           binding.revision_sha256, live_digest)
    with _lock:
        _prune(time.monotonic())
        generation = _generation
        previous = _entries.get(key)
        if previous is not None:
            _entries.move_to_end(key)
    if previous is not None:
        return [(binding.region_id, json.loads(previous[1]))], previous[2]

    # Bind the transferred row to the live digest even for public read-only
    # cursors whose transaction might not be repeatable-read.
    query = sql.SQL(
        "select region_id, metadata::text from {}.analysis_runtime_revisions "
        "where revision_sha256 = %s"
    ).format(sql.Identifier(binding.database_schema))
    cursor.execute(query, (binding.revision_sha256,))
    rows = cursor.fetchall()
    if (len(rows) != 1 or rows[0][0] != binding.region_id
            or type(rows[0][1]) is not str):
        raise ValueError("Runtime descriptor changed during content acquisition")
    encoded = rows[0][1].encode('utf-8')
    if hashlib.sha256(encoded).hexdigest() != live_digest:
        raise ValueError("Runtime descriptor changed during content acquisition")
    # Exact PostgreSQL JSON text is immutable. Each caller decodes its own dict
    # and retains the original canonical-revision and membership validations.
    metadata = json.loads(encoded)
    if type(metadata) is not dict:
        raise ValueError("Runtime descriptor must be a JSON object")
    canonical_digest = _canonical_digest(metadata)
    charge = (sys.getsizeof(key) + sys.getsizeof(connection)
              + sum(sys.getsizeof(v) for v in connection)
              + sum(sys.getsizeof(v) for v in key[1:])
              + sys.getsizeof(encoded) + sys.getsizeof(canonical_digest)
              + sys.getsizeof((0., encoded, canonical_digest, 0)))
    with _lock:
        now = time.monotonic()
        _prune(now)
        if (canonical_digest == binding.revision_sha256 and generation == _generation
                and key not in _entries and charge < _MAX_BYTES):
            _entries[key] = (now + _TTL_SECONDS, encoded, canonical_digest, charge)
            _bytes += charge
            while _entries and (len(_entries) > _MAX_ENTRIES
                    or _bytes + sys.getsizeof(_entries) > _MAX_BYTES):
                _, (_, _, _, removed) = _entries.popitem(last=False)
                _bytes -= removed
    return [(binding.region_id, metadata)], canonical_digest
