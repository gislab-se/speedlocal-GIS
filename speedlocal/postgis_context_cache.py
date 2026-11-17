"""Reuse validated context behind fresh proofs in the same SQL snapshot.

Private compressed bytes originate only in the precise reader. Public/import
cursors remain the independent reference. Hits decode independent objects and
never extend the ordinary input refresh or the fixed retention deadline.
"""
from collections import OrderedDict
import hashlib
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
from psycopg.postgres import register_default_types
from psycopg.rows import tuple_row
from psycopg.types import bool as pg_bool, numeric, string, json as pg_json

_adapters = AdaptersMap()
register_default_types(_adapters.types)
for _module in (pg_bool, numeric, string, pg_json):
    _module.register_default_adapters(_adapters)
_OIDS = (16, 17, 20, 21, 23, 25, 701, 114, 3802)
_LOADERS = tuple(_adapters.get_loader(oid, Format.TEXT) for oid in _OIDS)
_MAX_ENTRIES = 4
_MAX_BYTES = 16 * 1024 * 1024
_TTL_SECONDS = 300
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_entries = OrderedDict()
_bytes = 0
_generation = 0
_lock = RLock()


def clear_validated_context_cache():
    global _bytes, _generation
    with _lock:
        _entries.clear()
        _bytes = 0
        _generation += 1


def _ordinary_transport(cursor):
    return (isinstance(cursor, psycopg.Cursor)
            and cursor.format == Format.TEXT and cursor.row_factory is tuple_row
            and cursor.connection.info.encoding == "utf-8"
            and all(cursor.adapters.get_loader(oid, Format.TEXT) is loader
                    for oid, loader in zip(_OIDS, _LOADERS))
            and all(cursor.adapters.get_loader(oid, Format.TEXT)._loads is json.loads
                    for oid in (114, 3802)))


def _domain_proof(cursor, binding, domain_id, resolution, *, geometry):
    # Match the precise reader's complete ordered values, including raw numeric
    # type/text, signed zero, NDR WKB and SRID when landscape uses geometry.
    columns = "cell_id"
    if geometry:
        columns += (", area_value::text, pg_typeof(area_value)::text, "
                    "encode(pg_catalog.float8send(area_value::double precision), 'hex'), "
                    "encode(ST_AsBinary(geom, 'NDR'), 'hex'), ST_SRID(geom)")
    query = ("select count(*), encode(pg_catalog.sha256(convert_to(coalesce("
             "string_agg(jsonb_build_array(" + columns + ")::text, E'\\n' "
             "order by cell_id), ''), 'UTF8')), 'hex') from {}.analysis_runtime_cells "
             "where revision_sha256 = %s and domain_id = %s and resolution = %s")
    cursor.execute(sql.SQL(query).format(sql.Identifier(binding.database_schema)),
                   (binding.revision_sha256, domain_id, resolution))
    row = cursor.fetchone()
    if (not isinstance(row, tuple) or len(row) != 2 or type(row[0]) is not int
            or row[0] < 0 or type(row[1]) is not str or not _SHA256.fullmatch(row[1])):
        raise ValueError("Current context domain content proof is invalid")
    return row


def _prune(now):
    global _bytes
    for key, (expires, _encoded, charge) in tuple(_entries.items()):
        if expires <= now:
            del _entries[key]
            _bytes -= charge


def _size(value):
    return sys.getsizeof(value) + (sum(_size(item) for item in value)
                                  if isinstance(value, tuple) else 0)


def read_context_with_content_reuse(cursor, binding, **current):
    """Private application seam; every hit proves current access and content."""
    global _bytes
    from .postgis_context_inputs import (
        _read_context_revision_metadata, read_regional_context_from_cursor,
        required_context_dataset_kinds,
    )
    from .postgis_context_payloads import _proof
    from .postgis_runtime import RuntimeBinding
    from .combined_result_compiler import registered_combined_score_executor_ids

    if not _ordinary_transport(cursor):
        return read_regional_context_from_cursor(cursor, binding, **current)
    cursor.execute("select current_setting('transaction_read_only'), current_setting('transaction_isolation')")
    if cursor.fetchone() != ('on', 'repeatable read'):
        raise ValueError("Context content reuse requires a read-only repeatable-read transaction")
    with _lock:
        generation = _generation
    scope = current['expected_scope']
    required = required_context_dataset_kinds(scope, current['analyses'],
        combined_policy_manifest=current['combined_policy_manifest'],
        landscape_contract=current['landscape_contract'])
    _metadata, parent = _read_context_revision_metadata(cursor, binding, scope)
    # The metadata reader checks both immutable revisions against current scope.
    # Content proofs exercise all columns used by the precise context reader;
    # metadata pins/counts alone are insufficient to authorize a cache hit.
    cursor.execute(sql.SQL("select dataset_kind, encode(pg_catalog.sha256("
        "convert_to(payload::text, 'UTF8')), 'hex') from {}.regional_context_datasets "
        "where revision_sha256 = %s order by dataset_kind").format(
            sql.Identifier(binding.database_schema)), (binding.revision_sha256,))
    datasets = _proof(cursor.fetchall())
    if tuple(kind for kind, _digest in datasets) != required:
        raise ValueError("Context dataset membership differs from current contracts")
    parent_binding = RuntimeBinding(scope.region_id, binding.database_schema,
                                    scope.analysis_revision_sha256)
    support = scope.support_domain
    domains = [_domain_proof(cursor, parent_binding, support.domain_id,
                            support.resolution, geometry=False)]
    if "rooftop_population" in required or "landscape" in required:
        solar = next(analysis for analysis in current['analyses'] if analysis.id == 'solar')
        standard = solar.analysis_domain
        matches = [value for value in parent.get('domains', ())
                   if value.get('role') == 'standard_analysis'
                   and standard is not None and value.get('resolution') == standard.resolution]
        if len(matches) != 1:
            raise ValueError("Parent GIS revision lacks one exact canonical standard domain")
        domains.append(_domain_proof(cursor, parent_binding, matches[0]['domain_id'],
                                    standard.resolution, geometry="landscape" in required))
    # Hash every supplied contract field and manifest location, including declared
    # absence. Only private reader-produced result bytes are ever deserialized.
    declarations = hashlib.sha256(pickle.dumps(
        (current, registered_combined_score_executor_ids()), protocol=5)).hexdigest()
    info = cursor.connection.info
    key = ((info.host, info.port, info.dbname, info.user), binding.region_id,
           binding.database_schema, binding.revision_sha256, declarations,
           datasets, tuple(domains))
    with _lock:
        _prune(time.monotonic())
        previous = _entries.get(key) if generation == _generation else None
        if previous is not None:
            _entries.move_to_end(key)
    if previous is not None:
        return pickle.loads(zlib.decompress(previous[1]))

    result = read_regional_context_from_cursor(cursor, binding, **current)
    encoded = zlib.compress(pickle.dumps(result, protocol=5), level=1)
    charge = _size(key) + _size((0., encoded, 0))
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
    return result
