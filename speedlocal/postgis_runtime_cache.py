"""Reuse precise GIS decoding behind fresh, whole-row PostGIS content proofs.

This is private in-memory transport reuse, not a different input refresh policy.
Only bytes produced here from the precise reader are deserialized; no file or
caller-provided pickle is accepted. Live revision, SELECT and coverage checks
precede every reuse. Public/import cursors retain the independent precise reader.
"""
from collections import OrderedDict
import json
import pickle
import re
import sys
from threading import RLock
import time
import zlib

import psycopg
from psycopg import sql
from psycopg.adapt import AdaptersMap
from psycopg.pq import Format
from psycopg.rows import tuple_row
from psycopg.postgres import register_default_types
from psycopg.types import bool as pg_bool, numeric as pg_numeric, string as pg_string, json as pg_json

_DEFAULT_ADAPTERS = AdaptersMap()
register_default_types(_DEFAULT_ADAPTERS.types)
for _module in (pg_bool, pg_numeric, pg_string, pg_json):
    _module.register_default_adapters(_DEFAULT_ADAPTERS)
_OIDS = (16, 17, 20, 21, 23, 25, 701, 114, 3802)
_DEFAULT_LOADERS = tuple(_DEFAULT_ADAPTERS.get_loader(oid, Format.BINARY) for oid in _OIDS)
_MAX_ENTRIES = 4
_MAX_BYTES = 64 * 1024 * 1024
_TTL_SECONDS = 300
_SHA256 = re.compile(r'[0-9a-f]{64}\Z')
_entries = OrderedDict()
_bytes = 0
_generation = 0
_lock = RLock()

# Match every selected field and the exact order of the precise row reader.
# float8send retains signed zero and the complete binary double value; geometry
# includes both the selected NDR WKB and SRID. JSON strings escape delimiters.
_STREAMS = (
    ('analysis_runtime_sources',
     "source_id, feature_index, encode(ST_AsBinary(geom, 'NDR'), 'hex'), ST_SRID(geom)",
     'source_id, feature_index'),
    ('analysis_runtime_cells',
     "domain_id, resolution, cell_id, area_value::text, pg_typeof(area_value)::text, encode(pg_catalog.float8send(area_value::double precision), 'hex'), encode(ST_AsBinary(geom, 'NDR'), 'hex'), ST_SRID(geom)",
     'domain_id, resolution, cell_id'),
    ('analysis_runtime_observations',
     "source_id, domain_id, resolution, cell_id, distance_m::text, pg_typeof(distance_m)::text, encode(pg_catalog.float8send(distance_m::double precision), 'hex'), intersects",
     'source_id, domain_id, resolution, cell_id'),
    ('analysis_runtime_context_observations',
     "source_id, domain_id, resolution, cell_id, distance_m::text, pg_typeof(distance_m)::text, encode(pg_catalog.float8send(distance_m::double precision), 'hex'), intersects",
     'source_id, domain_id, resolution, cell_id'),
)


def clear_runtime_payload_cache():
    global _bytes, _generation
    with _lock:
        _entries.clear()
        _bytes = 0
        _generation += 1


def _ordinary_transport(cursor):
    return (isinstance(cursor, psycopg.Cursor)
            and cursor.format == Format.BINARY and cursor.row_factory is tuple_row
            and cursor.connection.info.encoding == 'utf-8'
            and all(cursor.adapters.get_loader(oid, Format.BINARY) is loader
                    for oid, loader in zip(_OIDS, _DEFAULT_LOADERS))
            and all(cursor.adapters.get_loader(oid, Format.BINARY)._loads is json.loads
                    for oid in (114, 3802)))


def _content_proof(cursor, binding):
    parts = []
    for view, columns, ordering in _STREAMS:
        query = (
            "(select jsonb_build_array(count(*), encode(pg_catalog.sha256(convert_to("
            "coalesce(string_agg(jsonb_build_array(" + columns + ")::text, E'\\n' order by "
            + ordering + "), ''), 'UTF8')), 'hex')) from {}.{} where revision_sha256=%s)"
        )
        parts.append(sql.SQL(query).format(sql.Identifier(binding.database_schema), sql.Identifier(view)))
    cursor.execute(sql.SQL('select ') + sql.SQL(', ').join(parts),
                   (binding.revision_sha256,) * len(parts))
    row = cursor.fetchone()
    if not isinstance(row, tuple) or len(row) != len(_STREAMS):
        raise ValueError('Current runtime content proof is missing')
    proof = []
    for item in row:
        if (not isinstance(item, (list, tuple)) or len(item) != 2
                or type(item[0]) is not int or item[0] < 0
                or type(item[1]) is not str or not _SHA256.fullmatch(item[1])):
            raise ValueError('Current runtime content proof is invalid')
        proof.append(tuple(item))
    return tuple(proof)


def _prune(now):
    global _bytes
    for key, (expires, _encoded, charge) in tuple(_entries.items()):
        if expires <= now:
            del _entries[key]
            _bytes -= charge


def read_runtime_with_content_reuse(cursor, binding):
    """Private repeatable-read caller; retain precise public cursor semantics."""
    global _bytes
    from .postgis_runtime import (
        _read_validated_runtime_metadata, read_road_runtime_from_cursor,
    )
    if not _ordinary_transport(cursor):
        return read_road_runtime_from_cursor(cursor, binding)
    cursor.execute("select current_setting('transaction_read_only'), current_setting('transaction_isolation')")
    if cursor.fetchone() != ('on', 'repeatable read'):
        raise ValueError('Runtime content reuse requires a read-only repeatable-read transaction')
    with _lock:
        generation = _generation
    # Check the exact descriptor and every physical stream even on a hit. A
    # permission failure or changed row can never retrieve a previous snapshot.
    _read_validated_runtime_metadata(cursor, binding)
    proof = _content_proof(cursor, binding)
    info = cursor.connection.info
    connection = (info.host, info.port, info.dbname, info.user)
    key = (connection, binding.region_id, binding.database_schema, binding.revision_sha256, proof)
    with _lock:
        _prune(time.monotonic())
        previous = _entries.get(key) if generation == _generation else None
        if previous is not None:
            _entries.move_to_end(key)
    if previous is not None:
        inputs = pickle.loads(zlib.decompress(previous[1]))
        from .postgis_domain_inputs import validate_runtime_coverage_from_cursor
        validate_runtime_coverage_from_cursor(cursor, inputs)
        return inputs

    inputs = read_road_runtime_from_cursor(cursor, binding)
    # Low-cost compression bounds retained geometry/observation bytes across
    # regions without retaining another graph of decoded Python objects.
    encoded = zlib.compress(pickle.dumps(inputs, protocol=5), level=1)
    # Count all retained bytes, including key tuples/scalars and container cost.
    def size(value):
        return sys.getsizeof(value) + (sum(size(item) for item in value) if isinstance(value, tuple) else 0)
    charge = (size(key) + sys.getsizeof(encoded) + sys.getsizeof((0., encoded, 0))
              + sys.getsizeof(0.) + sys.getsizeof(0))
    with _lock:
        now = time.monotonic()
        _prune(now)
        if generation == _generation and key not in _entries and charge < _MAX_BYTES:
            _entries[key] = (now + _TTL_SECONDS, encoded, charge)
            _bytes += charge
            while _entries and (len(_entries) > _MAX_ENTRIES
                    or _bytes + sys.getsizeof(_entries) > _MAX_BYTES):
                _, (_expires, _encoded, removed) = _entries.popitem(last=False)
                _bytes -= removed
    return inputs
