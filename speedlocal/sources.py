from __future__ import annotations

import csv
import hashlib
import json
import math
import operator
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field, replace
from functools import lru_cache
from io import StringIO
from pathlib import Path
from threading import get_ident
from typing import Any

import h3
from pyproj import CRS
from shapely import from_wkb
from shapely.geometry import Polygon, mapping, shape

from .contracts import (
    AnalysisContract,
    AnalysisDomainContract,
    AnalysisDomainRollupContract,
    EligibleSurfaceContract,
    EligibleSurfaceRollupContract,
    LayerContract,
    PostgisSourceReferenceContract,
    RegionAnalysisDomainContract,
    StandardResultSurfaceContract,
    StandardResultSurfaceRollupContract,
    TechnologyContextContract,
    canonical_contract_evidence,
    TechnologySupportDomainContract,
)
from ._input_refresh_cache import cache_input_windows
from .paths import resolve_source_path
from .postgis_runtime import DistanceObservation, LayerGeometryInput, RuntimeBinding, read_road_runtime, source_geometry_policies


@dataclass(frozen=True)
class LayerAssets:
    geojson_path: Path | None
    distance_path: Path | None
    manifest_status: str
    declared_geometry_family: str
    feature_count: int
    geojson_sha256: str
    geojson_bytes: int
    distance_sha256: str = ""
    geojson_payload: bytes | None = None
    distance_observations: tuple[DistanceObservation, ...] | None = None
    runtime_identity: tuple[str, str, str] | None = None
    upstream_geojson_sha256: str = ""
    upstream_geojson_bytes: int | None = None
    upstream_distance_sha256: str = ""
    upstream_distance_row_count: int | None = None


def _postgis_database_url(connection_alias: str, environ=None) -> str:
    environment = os.environ if environ is None else environ
    value = str(environment.get(f"SPEEDLOCAL_DATABASE_URL_{connection_alias.upper()}", "")).strip()
    if not value and connection_alias == "speedlocal":
        value = str(environment.get("DATABASE_URL", "")).strip()
    if not value:
        raise ValueError("The declared PostGIS connection is not configured")
    return value


@cache_input_windows(window_index=4)
def _cached_postgis_inputs(connection_alias, region_id, schema, revision, window):
    del window
    return read_road_runtime(
        _postgis_database_url(connection_alias),
        RuntimeBinding(region_id, schema, revision),
    )


@dataclass(repr=False)
class _PostgisInputOperation:
    thread_id: int
    generation: int
    active: bool = True
    snapshots: dict = field(default_factory=dict)
    layer_assets: dict = field(default_factory=dict)
    geometry_family_proofs: dict[tuple[str, int, str], str] = field(default_factory=dict)
    context_snapshots: dict = field(default_factory=dict)
    snapshot_revision: tuple[Any, str] | None = None


_postgis_operation: ContextVar[_PostgisInputOperation | None] = ContextVar(
    "speedlocal_postgis_input_operation", default=None,
)
_postgis_cache_generation = 0


def _current_postgis_operation():
    operation = _postgis_operation.get()
    if operation is not None:
        if not operation.active or operation.thread_id != get_ident():
            raise RuntimeError("PostGIS input operation escaped its execution context")
        if operation.generation != _postgis_cache_generation:
            operation.snapshots.clear()
            operation.layer_assets.clear()
            operation.geometry_family_proofs.clear()
            operation.snapshot_revision = None
            operation.generation = _postgis_cache_generation
    return operation


@contextmanager
def postgis_input_operation():
    """Reuse immutable pinned GIS inputs within one synchronous app operation.

    The ordinary cross-operation refresh and live readiness probes are retained.
    No connection is held open; all references are released on return, rerun,
    stop or failure. Nested calls in the same operation share its snapshot.
    """
    if _current_postgis_operation() is not None:
        yield
        return
    operation = _PostgisInputOperation(get_ident(), _postgis_cache_generation)
    token = _postgis_operation.set(operation)
    try:
        yield
    finally:
        operation.active = False
        operation.snapshots.clear()
        operation.layer_assets.clear()
        operation.geometry_family_proofs.clear()
        operation.context_snapshots.clear()
        operation.snapshot_revision = None
        _postgis_operation.reset(token)


def clear_postgis_runtime_cache() -> None:
    """Invalidate bounded input reuse after an operator/configuration change."""
    global _postgis_cache_generation
    _postgis_cache_generation += 1
    _cached_postgis_inputs.cache_clear()
    from .postgis_revision_metadata import clear_revision_metadata_cache
    clear_revision_metadata_cache()
    from .postgis_runtime_cache import clear_runtime_payload_cache
    clear_runtime_payload_cache()
    _serialized_postgis_source_geometry.cache_clear()
    from .postgis_domain_inputs import clear_domain_payload_cache
    clear_domain_payload_cache()


def load_postgis_runtime_snapshot(reference: PostgisSourceReferenceContract):
    # Configuration is checked even on a cache hit. Passwords/hosts never
    # enter a cache key. Between operations the existing 30-second refresh
    # applies; one operation keeps its validated immutable revision throughout.
    database_url = _postgis_database_url(reference.connection_alias)
    operation = _current_postgis_operation()
    key = (reference.connection_alias, reference.region_id, reference.database_schema)
    if operation is not None and key in operation.snapshots:
        previous_url, previous_revision, snapshot = operation.snapshots[key]
        if (previous_url != database_url
                or previous_revision != reference.revision_sha256):
            raise ValueError("PostGIS binding changed during the current operation")
        return snapshot
    snapshot = _cached_postgis_inputs(
        reference.connection_alias, reference.region_id,
        reference.database_schema, reference.revision_sha256,
        int(time.monotonic() // 30),
    )
    if operation is not None:
        operation.snapshots[key] = (database_url, reference.revision_sha256, snapshot)
    return snapshot


_READINESS_COUNT_BATCH_SIZE = 64


def probe_postgis_runtime_revisions(references, *, environ=None) -> tuple[dict[str, str], ...]:
    """One bounded read-only snapshot for a readiness batch, with exact membership."""
    import psycopg
    from psycopg import sql
    from .postgis_domain_inputs import validate_live_coverage_geography
    references = tuple(references)
    if not references:
        return ()
    aliases = {reference.connection_alias for reference in references}
    if len(aliases) != 1:
        raise ValueError("One readiness batch must use one declared database connection")
    database_url = _postgis_database_url(references[0].connection_alias, environ)
    loaded = {}
    count_queries = {}
    expected_counts = []
    results = []
    try:
        with psycopg.connect(database_url, connect_timeout=5, options="-c default_transaction_read_only=on -c statement_timeout=5000") as connection:
            with connection.cursor() as cursor:
                cursor.execute("set transaction isolation level repeatable read, read only")
                for reference in references:
                    key = (reference.region_id, reference.database_schema, reference.revision_sha256)
                    metadata = loaded.get(key)
                    if metadata is None:
                        from .postgis_revision_metadata import read_analysis_revision_metadata_with_digest
                        rows, metadata_digest = read_analysis_revision_metadata_with_digest(cursor, RuntimeBinding(
                            reference.region_id, reference.database_schema, reference.revision_sha256))
                        if len(rows) != 1 or rows[0][0] != reference.region_id:
                            raise ValueError("PostGIS runtime revision is missing or belongs to another region")
                        metadata = rows[0][1]
                        if not isinstance(metadata, dict) or metadata.get("format") != "roads-postgis-1" or metadata.get("region_id") != reference.region_id:
                            raise ValueError("PostGIS runtime revision metadata is invalid")
                        if metadata_digest is None:
                            encoded = json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
                            metadata_digest = hashlib.sha256(encoded).hexdigest()
                        if metadata_digest != reference.revision_sha256:
                            raise ValueError("PostGIS runtime revision metadata drifted")
                        loaded[key] = metadata
                    sources = [item for item in metadata.get("sources", ()) if item.get("source_id") == reference.source_id]
                    domains = [item for item in metadata.get("domains", ()) if (item.get("domain_id"), item.get("resolution")) == (reference.domain_id, reference.resolution)]
                    observations = [item for item in metadata.get("observations", ()) if (item.get("source_id"), item.get("domain_id"), item.get("resolution")) == (reference.source_id, reference.domain_id, reference.resolution)]
                    if len(sources) != 1 or len(domains) != 1 or len(observations) != 1 or domains[0].get("role") != "standard_analysis":
                        raise ValueError("PostGIS runtime source/domain membership is missing")
                    expected = (sources[0]["asset_feature_count"], domains[0]["cell_count"], observations[0]["row_count"], observations[0].get("context_row_count", 0))
                    keys = []
                    for view, predicate, parameters in (
                        ("analysis_runtime_sources", "source_id = %s", (reference.source_id,)),
                        ("analysis_runtime_cells", "domain_id = %s and resolution = %s", (reference.domain_id, reference.resolution)),
                        ("analysis_runtime_observations", "source_id = %s and domain_id = %s and resolution = %s", (reference.source_id, reference.domain_id, reference.resolution)),
                        ("analysis_runtime_context_observations", "source_id = %s and domain_id = %s and resolution = %s", (reference.source_id, reference.domain_id, reference.resolution)),
                    ):
                        key = (reference.database_schema, reference.revision_sha256,
                               view, predicate, parameters)
                        keys.append(key)
                        if key not in count_queries:
                            count_queries[key] = sql.SQL(
                                "(select count(*) from {}.{} where revision_sha256 = %s and " + predicate + ")"
                            ).format(sql.Identifier(reference.database_schema), sql.Identifier(view))
                    expected_counts.append((tuple(keys), expected))
                    results.append({"region_id": reference.region_id, "database_schema": reference.database_schema,
                        "revision_sha256": reference.revision_sha256, "source_id": reference.source_id,
                        "domain_id": reference.domain_id, "state": "available_revision"})
                # All counts use this call's same read-only repeatable-read
                # snapshot. Deduplicate only identical SQL predicates, then
                # check every requested reference against its own descriptor.
                # Bound each SELECT to 64 scalar counts, including for callers
                # outside the three-region product's smaller source inventory.
                observed = {}
                queries = tuple(count_queries.items())
                for offset in range(0, len(queries), _READINESS_COUNT_BATCH_SIZE):
                    batch = queries[offset:offset + _READINESS_COUNT_BATCH_SIZE]
                    parameters = tuple(value for key, _ in batch
                                       for value in (key[1], *key[4]))
                    cursor.execute(sql.SQL("select ") + sql.SQL(", ").join(
                        query for _, query in batch), parameters)
                    values = cursor.fetchone()
                    if values is None or len(values) != len(batch):
                        raise ValueError("PostGIS runtime row coverage drifted")
                    observed.update((key, value) for (key, _), value in zip(batch, values))
                for keys, expected in expected_counts:
                    if tuple(observed[key] for key in keys) != expected:
                        raise ValueError("PostGIS runtime row coverage drifted")
                # One coverage validation per revision, still inside the same
                # transaction as every source/domain membership observation.
                for (region_id, _schema, _revision), metadata in loaded.items():
                    for domain in metadata["domains"]:
                        display = domain.get("display_metadata")
                        if (display is not None and domain.get("role") == "technology_support"
                                and display.get("geometry_use") == "base_analysis_and_display"):
                            coverage = display.get("coverage_geography")
                            if coverage is None:
                                raise ValueError("Typed runtime has no approved coverage geography")
                            validate_live_coverage_geography(cursor, region_id, coverage)
    except psycopg.Error:
        raise ValueError("PostGIS runtime revision is unavailable") from None
    return tuple(results)


def probe_postgis_runtime_revision(reference: PostgisSourceReferenceContract, *, environ=None) -> dict[str, str]:
    """Compatibility wrapper; readiness callers should submit one full batch."""
    return probe_postgis_runtime_revisions((reference,), environ=environ)[0]


def read_layer_geojson_bytes(assets: LayerAssets) -> bytes:
    if assets.runtime_identity is not None:
        if assets.geojson_path is not None or assets.geojson_payload is None:
            raise ValueError("PostGIS source payload is incomplete or mixed with a file path")
        payload = assets.geojson_payload
    else:
        if assets.geojson_path is None or assets.geojson_payload is not None:
            raise ValueError("File source payload has no exclusive file binding")
        payload = assets.geojson_path.read_bytes()
    if len(payload) != assets.geojson_bytes or hashlib.sha256(payload).hexdigest() != assets.geojson_sha256:
        raise ValueError("Layer source bytes drifted from their validated input")
    return payload


def read_layer_geojson(assets: LayerAssets) -> dict[str, Any]:
    payload = json.loads(read_layer_geojson_bytes(assets).decode("utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Layer source must be a GeoJSON object")
    return payload


def detect_layer_geometry_family(
    assets: LayerAssets, geometry_collection_policy: str = "reject_mixed",
) -> str:
    """Reuse successful family detection for exact bytes in one input operation.

    Integrity is checked on every call. Only digest, size, policy and the
    immutable family string are retained; current asset/contract validation
    stays with the caller. Failures and optional-source fallbacks are not saved.
    """
    payload_bytes = read_layer_geojson_bytes(assets)
    operation = (
        _current_postgis_operation() if assets.runtime_identity is not None else None
    )
    key = (assets.geojson_sha256, assets.geojson_bytes, geometry_collection_policy)
    if operation is not None and key in operation.geometry_family_proofs:
        return operation.geometry_family_proofs[key]
    payload = json.loads(payload_bytes.decode("utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("Layer source must be a GeoJSON object")
    detected = detect_geometry_family(payload, geometry_collection_policy)
    if operation is not None:
        if len(operation.geometry_family_proofs) >= 16:
            del operation.geometry_family_proofs[next(iter(operation.geometry_family_proofs))]
        operation.geometry_family_proofs[key] = detected
    return detected


def read_layer_distance_observations(assets: LayerAssets) -> tuple[DistanceObservation, ...]:
    if assets.runtime_identity is not None:
        if assets.distance_path is not None or not assets.distance_observations:
            raise ValueError("PostGIS observations are incomplete or mixed with a file path")
        return assets.distance_observations
    if assets.distance_path is None:
        raise ValueError("Layer distance artifact is unavailable")
    payload = assets.distance_path.read_bytes()
    if not assets.distance_sha256 or hashlib.sha256(payload).hexdigest() != assets.distance_sha256:
        raise ValueError("Layer distance bytes drifted from their validated input")
    reader = csv.DictReader(StringIO(payload.decode("utf-8-sig"), newline=""))
    if not {"hex_id", "distance_m", "intersects"}.issubset(reader.fieldnames or ()):
        raise ValueError("Layer distance artifact has unsupported columns")
    rows = []
    seen = set()
    for row in reader:
        cell_id = str(row["hex_id"] or "").strip()
        flag = str(row["intersects"] or "").strip().lower()
        distance = float(row["distance_m"])
        if not cell_id or cell_id in seen or flag not in {"0", "1", "false", "true", "no", "yes"} or not math.isfinite(distance) or distance < 0:
            raise ValueError("Layer distance artifact contains invalid observations")
        seen.add(cell_id)
        rows.append(DistanceObservation(cell_id, distance, flag in {"1", "true", "yes"}))
    if not rows:
        raise ValueError("Layer distance artifact has no rows")
    return tuple(rows)


@lru_cache(maxsize=16)
def _serialized_postgis_source_geometry(source: LayerGeometryInput) -> tuple[bytes, str]:
    """Reuse only exact geometry bytes after the caller validates current inputs.

    The frozen source key contains actual immutable WKB, representation and
    provenance, so changed source content cannot reuse another source's bytes.
    Keep a regional working set with bounded spare entries; retain
    neither complete GIS snapshots nor observations or mutable decoded payloads.
    Full reads, the 30-second window and current-contract checks stay outside.
    """
    payload = json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": mapping(from_wkb(part))}
        for part in source.feature_wkb
    ]}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return payload, hashlib.sha256(payload).hexdigest()


def _resolve_postgis_layer_assets(layer: LayerContract) -> LayerAssets:
    reference = layer.source.postgis_reference
    if reference is None:
        raise ValueError("Layer has no PostGIS source reference")
    snapshot = load_postgis_runtime_snapshot(reference)
    try:
        source = snapshot.source(reference.source_id)
        domain = snapshot.domain(reference.domain_id, reference.resolution)
        observations = snapshot.observations(reference.source_id, reference.domain_id, reference.resolution)
    except StopIteration:
        raise ValueError("PostGIS source/domain membership is incomplete") from None
    from .source_catalog import load_delivery_source_selection
    from .paths import repo_root
    from .catalogs import load_region
    selected = load_delivery_source_selection(repo_root(), reference.region_id)
    selected_source = next((item for item in selected.sources if item.id == reference.source_id), None)
    native_crs = load_region(reference.region_id).get("native_crs")
    operation = _current_postgis_operation()
    asset_key = None
    if operation is not None:
        asset_key = (id(snapshot), json.dumps(asdict(layer), sort_keys=True,
                     separators=(",", ":"), allow_nan=False), selected_source, native_crs)
        if asset_key in operation.layer_assets:
            return operation.layer_assets[asset_key][1]
    coverage = layer.source.distance_coverage
    all_observations = observations.all_rows
    observed_ids_sha256 = hashlib.sha256("".join(f"{row.cell_id}\n" for row in all_observations).encode("ascii")).hexdigest()
    if (
        domain.role != "standard_analysis"
        or len(all_observations) != coverage.expected_source_row_count
        or observed_ids_sha256 != coverage.source_ids_sha256
        or source.geometry_family not in layer.source.expected_geometry_families
        or source.data_representation != layer.source.data_representation
        or source_geometry_policies(source) != (
            layer.source.geometry_collection_policy, layer.source.geometry_validity_policy,
        )
        or json.loads(source.provenance_json).get("group_id") != layer.group_id
        or selected_source is None
        or selected_source.group_id != layer.group_id
        or source.source_sha256 != selected_source.sha256
        or source.original_feature_count != selected_source.source_feature_count
        or source.native_crs != native_crs
    ):
        raise ValueError("PostGIS source does not match its declared analysis input")
    payload, payload_sha256 = _serialized_postgis_source_geometry(source)
    assets = LayerAssets(
        geojson_path=None, distance_path=None, manifest_status="ok",
        declared_geometry_family=source.geometry_family,
        feature_count=source.analysis_declared_feature_count,
        geojson_sha256=payload_sha256, geojson_bytes=len(payload),
        distance_sha256=hashlib.sha256(json.dumps([(row.cell_id, float(row.distance_m).hex(), row.intersects) for row in all_observations], separators=(",", ":")).encode("ascii")).hexdigest(),
        geojson_payload=payload, distance_observations=all_observations,
        # The reader verified this pin before caching the deeply immutable
        # snapshot. Reusing its requested identity avoids rehashing every row.
        runtime_identity=(reference.region_id, reference.database_schema, reference.revision_sha256),
        upstream_geojson_sha256=source.asset_sha256,
        upstream_geojson_bytes=reference.upstream_geojson_bytes,
        upstream_distance_sha256=observations.artifact_sha256,
        upstream_distance_row_count=observations.input_row_count,
    )
    if operation is not None:
        # Retain the exact snapshot as well as its id until scope exit.
        operation.layer_assets[asset_key] = (snapshot, assets)
    return assets


@dataclass(frozen=True)
class TechnologySupportObservation:
    cell_id: str
    distance_m: float
    intersects: bool


@dataclass(frozen=True)
class TechnologySupportObservationMetadataSnapshot:
    """Exact bytes and parsed payload for validated support observations."""

    path: Path | None
    payload_json: str
    sha256: str
    byte_count: int


@dataclass(frozen=True)
class AnalysisDomainDisplayArtifact:
    region_id: str
    domain_id: str
    resolution: int
    source_sha256: str
    cell_ids_sha256: str
    cell_count: int
    total_area_km2: float
    id_field: str
    area_field: str
    area_unit: str
    feature_collection_json: str
    upstream_source_sha256: str = ''
    runtime_revision_sha256: str = ''


"""Insert into sources.py at root integration; no catalog/app activation here."""

from .postgis_domain_inputs import DomainDisplayPayload


def _analysis_domain_postgis_reference(contract):
    """A domain read must use one complete current storage binding."""
    references = [layer.source.postgis_reference for layer in contract.layers.values()]
    if not any(reference is not None for reference in references):
        return None
    if any(reference is None for reference in references):
        raise ValueError("Domain runtime cannot mix file and PostGIS layer bindings")
    identities = {
        (reference.connection_alias, reference.region_id, reference.database_schema,
         reference.revision_sha256, reference.domain_id, reference.resolution)
        for reference in references
    }
    if len(identities) != 1:
        raise ValueError("Analysis layers disagree about the current domain runtime")
    reference = references[0]
    if (contract.analysis_domain is None or reference.region_id != contract.region_id
            or reference.database_schema != contract.region_id
            or reference.domain_id != "standard_analysis"
            or reference.resolution != contract.analysis_domain.resolution):
        raise ValueError("PostGIS domain binding differs from its current analysis")
    return reference


def _analysis_input_level(contract, role, resolution):
    if isinstance(resolution, bool) or not isinstance(resolution, int):
        raise ValueError("Domain input resolution must be an integer")
    if role == "standard_analysis":
        base, domain_id = contract.analysis_domain, "standard_analysis"
    elif role == "technology_support":
        base = eligible_surface_contract_for_analysis(contract)
        domain_id = base.support_domain_id
    elif role == "standard_result_surface":
        base = contract.standard_result_surface
        domain_id = base.id if base is not None else ""
    else:
        raise ValueError("Undeclared domain input role")
    if base is None:
        raise ValueError("Analysis has no declared domain for this input role")
    level = base if resolution == base.resolution else base.rollups.get(resolution)
    if level is None:
        raise ValueError("Analysis has no declared domain input at this resolution")
    return base, domain_id, level


def read_analysis_domain_input(
    contract: AnalysisContract,
    role: str,
    resolution: int,
    *,
    geometry_use: str = "display",
) -> "DomainDisplayPayload":
    """Acquire exact current domain bytes; existing consumers retain all math."""
    from .postgis_domain_inputs import domain_payload
    from .postgis_runtime import RuntimeBinding

    base, domain_id, level = _analysis_input_level(contract, role, resolution)
    if (geometry_use not in {"display", "base_analysis"}
            or (geometry_use == "base_analysis" and resolution != base.resolution)):
        raise ValueError("Exact geometry calculations require the declared base level")
    reference = _analysis_domain_postgis_reference(contract)
    if reference is not None:
        # Missing new metadata or a declared parent domain is an error. Never
        # fall back to the old artifact when an active PostGIS pin exists.
        inputs = load_postgis_runtime_snapshot(reference)
        binding = RuntimeBinding(reference.region_id, reference.database_schema,
                                 reference.revision_sha256)
        payload = domain_payload(inputs, binding, contract, role, resolution,
                                 geometry_use=geometry_use)
        return DomainDisplayPayload(
            payload.region_id, payload.domain_id, payload.role, payload.resolution,
            payload.upstream_source_sha256, payload.payload_sha256,
            payload.runtime_revision_sha256, payload.geojson_bytes)
    path = resolve_source_path(level.provider, level.path)
    blob = path.read_bytes()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != level.sha256:
        raise ValueError("Domain input checksum differs from its declared file")
    return DomainDisplayPayload(contract.region_id, domain_id, role, resolution,
                                level.sha256, digest, "", blob)


def _read_analysis_domain_area_values(contract, role, resolution):
    """Keep the existing area decoder and all callers' rollup checks."""
    base, domain_id, level = _analysis_input_level(contract, role, resolution)
    reference = _analysis_domain_postgis_reference(contract)
    if reference is None:
        return _resolve_domain_level_cell_areas_km2(level)
    if role == "standard_result_surface" and resolution < base.resolution:
        from .postgis_domain_inputs import standard_result_area_rollup
        from .postgis_runtime import RuntimeBinding
        return standard_result_area_rollup(
            load_postgis_runtime_snapshot(reference),
            RuntimeBinding(reference.region_id, reference.database_schema,
                           reference.revision_sha256), contract, resolution)
    payload = read_analysis_domain_input(contract, role, resolution)
    # The string below is provenance in error messages only, never an I/O path.
    return _domain_level_cell_areas_from_payload(
        level, json.loads(payload.feature_collection_json), str(level.path))


DECLARED_GEOMETRY_FAMILY_ALIASES = {
    "polygon_proxy_from_250m_centroids": "polygon",
}


def _declared_geometry_family(value: Any) -> str:
    normalized = str(value or "unknown").strip().lower()
    return DECLARED_GEOMETRY_FAMILY_ALIASES.get(normalized, normalized)


def _domain_level_area_to_km2(
    raw_value: Any,
    level: (
        AnalysisDomainContract
        | AnalysisDomainRollupContract
        | EligibleSurfaceContract
        | EligibleSurfaceRollupContract
        | StandardResultSurfaceContract
        | StandardResultSurfaceRollupContract
    ),
    feature_index: int,
    path: Path,
) -> float:
    if not level.area_field.strip():
        raise ValueError("Analysis-domain area field is required")
    if level.area_unit not in {"m2", "km2"}:
        raise ValueError(
            f"Unsupported analysis-domain area unit: {level.area_unit}"
        )
    if isinstance(raw_value, bool):
        raise ValueError(
            f"Analysis-domain feature {feature_index} has invalid "
            f"{level.area_field}: {raw_value!r} ({path})"
        )
    try:
        area = float(raw_value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"Analysis-domain feature {feature_index} has invalid "
            f"{level.area_field}: {raw_value!r} ({path})"
        ) from exc
    if not math.isfinite(area) or area <= 0.0:
        raise ValueError(
            f"Analysis-domain feature {feature_index} has non-positive or "
            f"non-finite {level.area_field}: {raw_value!r} ({path})"
        )
    return area / 1_000_000.0 if level.area_unit == "m2" else area


def _resolve_domain_level_cell_areas_km2(
    level: (
        AnalysisDomainContract
        | AnalysisDomainRollupContract
        | EligibleSurfaceContract
        | EligibleSurfaceRollupContract
        | StandardResultSurfaceContract
        | StandardResultSurfaceRollupContract
    ),
) -> dict[str, float]:
    path = resolve_source_path(level.provider, level.path)
    if not path.is_file():
        raise FileNotFoundError(f"Analysis-domain source is missing: {path}")
    expected_sha256 = str(getattr(level, "sha256", "") or "").strip().lower()
    if expected_sha256:
        verify_source_sha256(path, expected_sha256, "Analysis-domain source")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return _domain_level_cell_areas_from_payload(level, payload, path)


def _domain_level_cell_areas_from_payload(level, payload, path):
    if payload.get("type") != "FeatureCollection":
        raise ValueError(f"Analysis-domain source must be a FeatureCollection: {path}")

    cell_areas: dict[str, float] = {}
    for index, feature in enumerate(payload.get("features") or []):
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(
                f"Analysis-domain feature {index} has no properties: {path}"
            )
        cell_id = str(properties.get(level.id_field) or "").strip()
        if not cell_id:
            raise ValueError(
                f"Analysis-domain feature {index} has no {level.id_field}: {path}"
            )
        try:
            resolution = int(h3.get_resolution(cell_id))
        except Exception as exc:
            raise ValueError(
                f"Analysis-domain feature {index} has invalid H3 id: {cell_id}"
            ) from exc
        if resolution != level.resolution:
            raise ValueError(
                f"Analysis-domain cell {cell_id} is R{resolution}; "
                f"expected R{level.resolution}"
            )
        if cell_id in cell_areas:
            raise ValueError(
                f"Analysis-domain source contains duplicate cell ids: {path}"
            )
        if level.area_field not in properties:
            raise ValueError(
                f"Analysis-domain feature {index} has no {level.area_field}: "
                f"{path}"
            )
        cell_areas[cell_id] = _domain_level_area_to_km2(
            properties[level.area_field],
            level,
            index,
            path,
        )

    if len(cell_areas) != level.expected_cell_count:
        raise ValueError(
            f"Analysis-domain source has {len(cell_areas)} cells; "
            f"expected {level.expected_cell_count}"
        )
    return cell_areas


@lru_cache(maxsize=512)
def _versioned_file_sha256(
    path_str: str,
    size: int,
    mtime_ns: int,
    expected_sha256: str,
) -> str:
    path = Path(path_str)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_source_sha256(path: Path, expected_sha256: str, label: str) -> None:
    stat = path.stat()
    normalized_expected = str(expected_sha256).lower()
    actual = _versioned_file_sha256(
        str(path.resolve()),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        normalized_expected,
    )
    if actual != normalized_expected:
        raise ValueError(
            f"{label} checksum does not match its manifest: {path} "
            f"({actual} != {expected_sha256})"
        )


@lru_cache(maxsize=32)
def _eligible_surface_id_digest(
    path_str: str,
    artifact_sha256: str,
    id_field: str,
    resolution: int,
    expected_cell_count: int,
) -> str:
    path = Path(path_str)
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("type") != "FeatureCollection":
        raise ValueError(
            f"Eligible-surface artifact must be a FeatureCollection: {path}"
        )
    cell_ids: list[str] = []
    for index, feature in enumerate(payload.get("features") or []):
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(
                f"Eligible-surface feature {index} has no properties: {path}"
            )
        cell_id = str(properties.get(id_field) or "").strip()
        try:
            cell_resolution = int(h3.get_resolution(cell_id))
        except Exception as exc:
            raise ValueError(
                f"Eligible-surface feature {index} has an invalid H3 id"
            ) from exc
        if cell_resolution != resolution:
            raise ValueError(
                f"Eligible-surface cell {cell_id!r} is R{cell_resolution}; "
                f"expected R{resolution}"
            )
        cell_ids.append(cell_id)
    if (
        len(cell_ids) != expected_cell_count
        or len(cell_ids) != len(set(cell_ids))
    ):
        raise ValueError(
            "Eligible-surface artifact cell ids are incomplete or duplicated"
        )
    return hashlib.sha256(
        "".join(f"{cell_id}\n" for cell_id in sorted(cell_ids)).encode(
            "utf-8"
        )
    ).hexdigest()


def resolve_eligible_surface_cell_ids_sha256(
    contract: AnalysisContract,
) -> str:
    """Return the verified source-level eligible-surface H3-id digest."""

    surface = eligible_surface_contract_for_analysis(contract)
    if _analysis_domain_postgis_reference(contract) is not None:
        from .postgis_domain_inputs import domain_cell_ids_sha256
        reference = _analysis_domain_postgis_reference(contract)
        return domain_cell_ids_sha256(load_postgis_runtime_snapshot(reference),
            RuntimeBinding(reference.region_id, reference.database_schema, reference.revision_sha256),
            contract, "technology_support", surface.resolution)
    path = resolve_source_path(surface.provider, surface.path)
    if not path.is_file():
        raise FileNotFoundError(f"Eligible-surface artifact is missing: {path}")
    verify_source_sha256(
        path,
        surface.sha256,
        "Eligible-surface artifact",
    )
    return _eligible_surface_id_digest(
        str(path.resolve()),
        surface.sha256,
        surface.id_field,
        surface.resolution,
        surface.expected_cell_count,
    )


def eligible_surface_contract_for_analysis(
    contract: AnalysisContract,
) -> EligibleSurfaceContract:
    area_result = contract.area_result
    if area_result is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no area-result contract"
        )
    surface_id = area_result.eligible_surface_id
    surface = contract.eligible_surfaces.get(surface_id)
    if surface is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no eligible surface "
            f"{surface_id!r}"
        )
    return surface


def technology_context_contract_for_analysis(
    contract: AnalysisContract,
) -> TechnologyContextContract:
    """Return the typed optional-context authority for a technology surface."""

    return eligible_surface_contract_for_analysis(contract).technology_context


def resolve_technology_context_path(contract: AnalysisContract) -> Path:
    """Resolve and verify the full technology-context H3 source fail closed."""

    context = technology_context_contract_for_analysis(contract)
    path = resolve_source_path(context.provider, context.path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Technology-context source is missing: {path}"
        )
    verify_source_sha256(
        path,
        context.sha256,
        "Technology-context source",
    )
    cell_ids_sha256 = _eligible_surface_id_digest(
        str(path.resolve()),
        context.sha256,
        context.id_field,
        context.resolution,
        context.expected_cell_count,
    )
    if cell_ids_sha256 != context.cell_ids_sha256:
        raise ValueError(
            "Technology-context H3-id digest does not match its manifest"
        )
    return path


def resolve_region_geography_asset_path(
    region_id: str,
    geography_id: str,
) -> Path:
    """Resolve one checksum-pinned region geography asset fail closed."""

    from .catalogs import load_region_geography

    geography = load_region_geography(str(region_id))
    asset = geography.geographies.get(str(geography_id))
    if asset is None:
        raise KeyError(
            f"{region_id} has no region geography {geography_id!r}"
        )
    path = resolve_source_path(asset.provider, asset.path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Region geography asset is missing: {path}"
        )
    verify_source_sha256(
        path,
        asset.sha256,
        f"Region geography {geography_id}",
    )
    return path


def region_analysis_domain_contract(
    region_id: str,
    domain_id: str,
) -> RegionAnalysisDomainContract:
    """Return one repo-declared regional analysis domain fail closed."""

    from .catalogs import load_region_geography

    geography = load_region_geography(str(region_id))
    domain = geography.analysis_domains.get(str(domain_id))
    if domain is None:
        raise KeyError(
            f"{region_id} has no region analysis domain {domain_id!r}"
        )
    return domain


def resolve_region_analysis_domain_metadata_path(
    region_id: str,
    domain_id: str,
) -> Path:
    """Resolve one generated domain metadata artifact with its checksum."""

    domain = region_analysis_domain_contract(region_id, domain_id)
    path = resolve_source_path(domain.metadata_provider, domain.metadata_path)
    if not path.is_file():
        raise FileNotFoundError(f"Region analysis-domain metadata is missing: {path}")
    verify_source_sha256(
        path,
        domain.metadata_sha256,
        "Region analysis-domain metadata",
    )
    return path


def resolve_region_analysis_domain_metadata(
    region_id: str,
    domain_id: str,
) -> dict[str, Any]:
    """Validate the same original metadata from the current file/DB authority."""
    domain = region_analysis_domain_contract(region_id, domain_id)
    blob = _regional_domain_metadata_input(region_id, domain)
    return _validate_region_analysis_domain_metadata(domain, json.loads(blob.decode("utf-8")))


def _validate_region_analysis_domain_metadata(domain, payload):
    """Unchanged regional-domain semantic checks, reusable by offline import."""
    if not isinstance(payload, dict):
        raise ValueError("Region analysis-domain metadata must be an object")
    artifacts = domain.artifacts
    expected_levels = {
        artifacts.resolution: artifacts,
        **artifacts.rollups,
    }
    raw_levels = payload.get("levels")
    if not isinstance(raw_levels, list):
        raise ValueError("Region analysis-domain metadata levels are required")
    levels_by_resolution: dict[int, dict[str, Any]] = {}
    for item in raw_levels:
        if not isinstance(item, dict) or isinstance(item.get("resolution"), bool):
            raise ValueError("Region analysis-domain metadata level is invalid")
        try:
            resolution = int(item["resolution"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "Region analysis-domain metadata resolution is invalid"
            ) from exc
        if resolution in levels_by_resolution:
            raise ValueError(
                f"Region analysis-domain metadata duplicates R{resolution}"
            )
        levels_by_resolution[resolution] = item
    if set(levels_by_resolution) != set(expected_levels):
        raise ValueError(
            "Region analysis-domain metadata does not cover every contract level"
        )
    for resolution, level in expected_levels.items():
        metadata_level = levels_by_resolution[resolution]
        if (
            metadata_level.get("path") != level.path
            or metadata_level.get("sha256") != level.sha256
            or metadata_level.get("cell_count") != level.expected_cell_count
            or metadata_level.get("cell_ids_sha256")
            != domain.cell_ids_sha256[resolution]
        ):
            raise ValueError(
                f"Region analysis-domain R{resolution} metadata disagrees "
                "with its contract"
            )
    if (
        payload.get("schema_version") != "1.0"
        or payload.get("domain_id") != domain.id
        or payload.get("domain_scope") != domain.domain_scope
        or payload.get("status") != domain.status
        or payload.get("coverage_rule") != domain.coverage_rule
        or payload.get("empty_intersection_policy")
        != domain.empty_intersection_policy
        or payload.get("missing_observation_policy")
        != domain.missing_observation_policy
        or payload.get("rollup_strategy") != domain.rollup_strategy
        or payload.get("source_h3_resolution") != artifacts.resolution
        or payload.get("rollup_resolutions")
        != list(artifacts.rollups)
    ):
        raise ValueError(
            "Region analysis-domain metadata semantics disagree with its contract"
        )
    return payload


def _load_analysis_domain_display_artifact(
    *,
    region_id: str,
    domain_id: str,
    artifacts: AnalysisDomainContract,
    resolution: int | None,
    expected_cell_ids_sha256: dict[int, str] | None,
    domain_input=None,
) -> AnalysisDomainDisplayArtifact:
    """Validate one exact H3 display artifact from its consumed bytes."""

    if resolution is None:
        requested = artifacts.resolution
    elif (
        not isinstance(resolution, (int, float))
        or isinstance(resolution, bool)
        or not math.isfinite(float(resolution))
        or not float(resolution).is_integer()
    ):
        raise ValueError("Analysis-domain display resolution must be an integer")
    else:
        requested = int(resolution)
    level = (
        artifacts
        if requested == artifacts.resolution
        else artifacts.rollups.get(requested)
    )
    if level is None:
        raise ValueError(
            f"{region_id}/{domain_id} has no R{requested} "
            "analysis-domain display level"
        )
    if domain_input is None:
        path = resolve_source_path(level.provider, level.path)
        if not path.is_file():
            raise FileNotFoundError(f"Analysis-domain display source is missing: {path}")
        source_bytes = path.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        if source_sha256 != str(level.sha256).strip().lower():
            raise ValueError("Analysis-domain display checksum changed")
        upstream_source_sha256 = ''
        runtime_revision_sha256 = ''
    else:
        if (domain_input.region_id != region_id or domain_input.resolution != requested
                or domain_input.role != 'standard_analysis'
                or domain_input.upstream_source_sha256 != level.sha256):
            raise ValueError('Domain display input differs from its current contract')
        path = str(level.path)  # provenance for errors only
        source_bytes = domain_input.geojson_bytes
        source_sha256 = domain_input.payload_sha256
        upstream_source_sha256 = (domain_input.upstream_source_sha256 if domain_input.runtime_revision_sha256 else '')
        runtime_revision_sha256 = domain_input.runtime_revision_sha256
    try:
        source_text = source_bytes.decode("utf-8")
        payload = json.loads(source_text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Analysis-domain display source is unreadable") from exc
    features = payload.get("features") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("type") != "FeatureCollection"
        or not isinstance(features, list)
    ):
        raise ValueError("Analysis-domain display source must be a FeatureCollection")
    crs_declaration = payload.get("crs")
    if crs_declaration is not None:
        if (
            not isinstance(crs_declaration, dict)
            or crs_declaration.get("type") != "name"
            or not isinstance(crs_declaration.get("properties"), dict)
        ):
            raise ValueError("Analysis-domain display CRS declaration is invalid")
        try:
            declared_crs = CRS.from_user_input(
                crs_declaration["properties"].get("name")
            )
        except Exception as exc:
            raise ValueError(
                "Analysis-domain display CRS declaration is invalid"
            ) from exc
        if not declared_crs.equals(CRS.from_epsg(4326), ignore_axis_order=True):
            raise ValueError("Analysis-domain display must use CRS84/EPSG:4326")

    cell_areas: dict[str, float] = {}
    for index, feature in enumerate(features):
        if not isinstance(feature, dict):
            raise ValueError(
                f"Analysis-domain display feature {index} must be an object"
            )
        if feature.get("type") != "Feature":
            raise ValueError(
                f"Analysis-domain display feature {index} has an invalid type"
            )
        geometry = feature.get("geometry")
        if (
            not isinstance(geometry, dict)
            or geometry.get("type") not in {"Polygon", "MultiPolygon"}
        ):
            raise ValueError(
                f"Analysis-domain display feature {index} is not polygonal"
            )
        try:
            polygon = shape(geometry)
        except Exception as exc:
            raise ValueError(
                f"Analysis-domain display feature {index} is unreadable"
            ) from exc
        if polygon.is_empty or not polygon.is_valid:
            raise ValueError(
                f"Analysis-domain display feature {index} is empty or invalid"
            )
        min_x, min_y, max_x, max_y = polygon.bounds
        if (
            not all(math.isfinite(value) for value in polygon.bounds)
            or min_x < -180.0
            or max_x > 180.0
            or min_y < -90.0
            or max_y > 90.0
        ):
            raise ValueError(
                f"Analysis-domain display feature {index} is outside CRS84"
            )
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(
                f"Analysis-domain display feature {index} has no properties"
            )
        cell_id = str(properties.get(level.id_field) or "").strip()
        if not cell_id or cell_id in cell_areas:
            raise ValueError(
                "Analysis-domain display contains a missing or duplicate H3 id"
            )
        try:
            cell_resolution = int(h3.get_resolution(cell_id))
        except Exception as exc:
            raise ValueError(
                f"Analysis-domain display has an invalid H3 id: {cell_id}"
            ) from exc
        if cell_resolution != requested:
            raise ValueError(
                f"Analysis-domain display cell {cell_id} is R{cell_resolution}; "
                f"expected R{requested}"
            )
        cell_polygon = Polygon(
            [(float(lng), float(lat)) for lat, lng in h3.cell_to_boundary(cell_id)]
        )
        if (
            cell_polygon.is_empty
            or not cell_polygon.is_valid
            or polygon.intersection(cell_polygon).area <= 0.0
        ):
            raise ValueError(
                f"Analysis-domain display geometry does not intersect {cell_id}"
            )
        if level.area_field not in properties:
            raise ValueError(
                f"Analysis-domain display feature {index} has no "
                f"{level.area_field}"
            )
        cell_areas[cell_id] = _domain_level_area_to_km2(
            properties[level.area_field],
            level,
            index,
            path,
        )
    if len(cell_areas) != level.expected_cell_count:
        raise ValueError(
            f"Analysis-domain display has {len(cell_areas)} cells; "
            f"expected {level.expected_cell_count}"
        )
    cell_ids_sha256 = hashlib.sha256(
        "".join(f"{cell_id}\n" for cell_id in sorted(cell_areas)).encode("utf-8")
    ).hexdigest()
    if (
        expected_cell_ids_sha256 is not None
        and cell_ids_sha256 != expected_cell_ids_sha256[requested]
    ):
        raise ValueError("Analysis-domain display H3-id digest changed")
    total_area_km2 = math.fsum(cell_areas.values())
    if not math.isclose(
        total_area_km2,
        artifacts.expected_total_area_km2,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise ValueError("Analysis-domain display total area changed")
    return AnalysisDomainDisplayArtifact(
        region_id=region_id,
        domain_id=domain_id,
        resolution=requested,
        source_sha256=source_sha256,
        upstream_source_sha256=upstream_source_sha256,
        runtime_revision_sha256=runtime_revision_sha256,
        cell_ids_sha256=cell_ids_sha256,
        cell_count=len(cell_areas),
        total_area_km2=total_area_km2,
        id_field=str(level.id_field),
        area_field=str(level.area_field),
        area_unit=str(level.area_unit),
        feature_collection_json=source_text,
    )


def load_analysis_contract_domain_display_artifact(
    contract: AnalysisContract,
    resolution: int | None = None,
) -> AnalysisDomainDisplayArtifact:
    """Load an analysis contract's checksum-bound display domain.

    This variant deliberately has no catalog or region-geography dependency,
    so a non-indexed manifest portability fixture uses the same byte-level
    domain validation as a catalog region. The contract SHA, cell count, H3
    resolution, geometry, and total area are all verified. The returned
    ``cell_ids_sha256`` is derived from those exact consumed bytes.
    """

    domain = contract.analysis_domain
    if domain is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no analysis domain"
        )
    requested = domain.resolution if resolution is None else resolution
    if (not isinstance(requested, (int, float)) or isinstance(requested, bool)
            or not math.isfinite(float(requested)) or not float(requested).is_integer()):
        raise ValueError('Analysis-domain display resolution must be an integer')
    return _load_analysis_domain_display_artifact(
        region_id=str(contract.region_id).strip().lower(),
        domain_id=f"{contract.id}.analysis_domain",
        artifacts=domain,
        resolution=resolution,
        expected_cell_ids_sha256=None,
        domain_input=read_analysis_domain_input(
            contract, 'standard_analysis', int(requested)),
    )


def load_region_analysis_domain_display_artifact(
    region_id: str,
    domain_id: str,
    resolution: int | None = None,
) -> AnalysisDomainDisplayArtifact:
    """Load one checksum-bound H3 display artifact from the consumed bytes."""

    normalized_region_id = str(region_id or "").strip().lower()
    normalized_domain_id = str(domain_id or "").strip()
    domain = region_analysis_domain_contract(
        normalized_region_id,
        normalized_domain_id,
    )
    resolve_region_analysis_domain_metadata(
        normalized_region_id,
        normalized_domain_id,
    )
    return _load_analysis_domain_display_artifact(
        region_id=normalized_region_id,
        domain_id=normalized_domain_id,
        artifacts=domain.artifacts,
        resolution=resolution,
        expected_cell_ids_sha256=domain.cell_ids_sha256,
        domain_input=read_analysis_domain_input(
            _analysis_for_regional_domain(normalized_region_id, domain), "standard_analysis",
            domain.artifacts.resolution if resolution is None else int(resolution)),
    )


def resolve_region_analysis_domain_cell_areas_km2(
    region_id: str,
    domain_id: str,
    resolution: int | None = None,
) -> dict[str, float]:
    """Resolve a checksum-pinned regional H3 domain and derived rollups."""

    domain = region_analysis_domain_contract(region_id, domain_id)
    artifacts = domain.artifacts
    requested = artifacts.resolution if resolution is None else int(resolution)
    level = artifacts if requested == artifacts.resolution else artifacts.rollups.get(requested)
    if level is None:
        raise ValueError(
            f"{region_id}/{domain_id} has no R{requested} analysis-domain level"
        )
    resolve_region_analysis_domain_metadata(region_id, domain_id)
    analysis = _analysis_for_regional_domain(region_id, domain)
    areas = _read_analysis_domain_area_values(analysis, "standard_analysis", requested)
    actual_digest = hashlib.sha256(
        "".join(f"{cell_id}\n" for cell_id in sorted(areas)).encode("utf-8")
    ).hexdigest()
    if actual_digest != domain.cell_ids_sha256[requested]:
        raise ValueError(
            f"Region analysis-domain R{requested} H3-id digest changed"
        )
    expected_total = artifacts.expected_total_area_km2
    if not math.isclose(
        math.fsum(areas.values()),
        expected_total,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise ValueError(
            f"Region analysis-domain R{requested} total area changed"
        )
    if requested != artifacts.resolution:
        source_areas = resolve_region_analysis_domain_cell_areas_km2(
            region_id,
            domain_id,
            artifacts.resolution,
        )
        expected_parent_areas: dict[str, float] = {}
        for cell_id, area_km2 in source_areas.items():
            parent_id = str(h3.cell_to_parent(cell_id, requested))
            expected_parent_areas[parent_id] = (
                expected_parent_areas.get(parent_id, 0.0) + area_km2
            )
        if set(areas) != set(expected_parent_areas):
            raise ValueError(
                f"Region analysis-domain R{requested} does not match source parents"
            )
        for parent_id, expected_area in expected_parent_areas.items():
            if not math.isclose(
                areas[parent_id],
                expected_area,
                rel_tol=1e-12,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    f"Region analysis-domain R{requested} parent area changed: "
                    f"{parent_id}"
                )
    return areas


def technology_support_domain_for_eligible_surface(
    contract: AnalysisContract,
) -> TechnologySupportDomainContract:
    """Resolve and cross-check an eligible surface's explicit support domain."""

    from .catalogs import load_region_geography

    surface = eligible_surface_contract_for_analysis(contract)
    support_domain_id = surface.support_domain_id.strip()
    if not support_domain_id:
        raise ValueError(
            f"{contract.region_id}/{contract.id} eligible surface "
            f"{surface.id!r} has no support_domain_id"
        )
    geography = load_region_geography(contract.region_id)
    support_domain = geography.technology_support_domains.get(
        support_domain_id
    )
    if support_domain is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} eligible surface "
            f"{surface.id!r} references undeclared technology support "
            f"domain {support_domain_id!r}"
        )
    _require_support_coverage_input(contract, support_domain)
    if (
        surface.source.coverage_geometry_id
        != support_domain.coverage_geometry_id
    ):
        raise ValueError(
            f"Eligible surface {surface.id!r} source is not derived from "
            f"support domain {support_domain_id!r} coverage geometry"
        )
    if (
        surface.support_observations.missing_policy
        != support_domain.missing_observation_policy
    ):
        raise ValueError(
            f"Eligible surface {surface.id!r} support-observation policy does "
            f"not match support domain {support_domain_id!r}"
        )
    if not set(surface.technologies).issubset(
        set(support_domain.technologies)
    ):
        raise ValueError(
            f"Eligible surface {surface.id!r} technologies do not match "
            f"support domain {support_domain_id!r}"
        )
    if (
        surface.cell_kind != support_domain.cell_kind
        or surface.resolution != support_domain.source_resolution
    ):
        raise ValueError(
            f"Eligible surface {surface.id!r} H3 source level does not "
            f"match support domain {support_domain_id!r}"
        )
    if set(surface.rollups) != set(support_domain.rollup_resolutions):
        raise ValueError(
            f"Eligible surface {surface.id!r} rollups do not match support "
            f"domain {support_domain_id!r}"
        )
    area_result = contract.area_result
    if (
        area_result is not None
        and area_result.technology not in support_domain.technologies
    ):
        raise ValueError(
            f"Technology {area_result.technology!r} is not declared by "
            f"support domain {support_domain_id!r}"
        )
    return support_domain


def _canonical_contract_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _support_surface_contract_evidence(surface: Any) -> dict[str, Any]:
    """Return the stable observation-input surface evidence.

    ``context_fields`` belongs to the independently replayable technology-
    context consumer.  It does not change distance/intersection observation
    rows, so adding the field declaration must not invalidate an already
    checksum-pinned observation package.
    """

    evidence = asdict(surface)
    evidence.pop("support_observations", None)
    technology_context = evidence.get("technology_context")
    if isinstance(technology_context, dict):
        technology_context.pop("context_fields", None)
    return evidence


def _support_area_result_semantics(area_result: Any) -> dict[str, Any]:
    evidence = asdict(area_result)
    evidence.pop("technology", None)
    return evidence


def _shared_support_analysis_contracts(
    contract: AnalysisContract,
    support_domain: TechnologySupportDomainContract,
    *, offline_analyses: dict[str, AnalysisContract] | None = None,
) -> tuple[AnalysisContract, ...]:
    """Resolve one equivalent analysis contract per declared technology."""

    from .catalogs import load_analysis, load_region
    from .validation import validate_contract

    region = load_region(contract.region_id)
    manifest_ids = tuple(
        str(analysis_id)
        for analysis_id in (region.get("analysis_manifests") or {})
    )
    if contract.id not in manifest_ids:
        raise ValueError(
            f"Analysis {contract.id!r} is not declared for {contract.region_id}"
        )
    if offline_analyses is not None:
        if set(offline_analyses) != set(manifest_ids) or offline_analyses.get(contract.id) != contract or any(
            (candidate.region_id, candidate.id) != (contract.region_id, analysis_id)
            or any(layer.source.postgis_reference is not None for layer in candidate.layers.values())
            for analysis_id, candidate in offline_analyses.items()
        ):
            raise ValueError("Offline support preparation requires complete same-region file analysis contracts")
    candidates: dict[str, list[AnalysisContract]] = {
        technology: [] for technology in support_domain.technologies
    }
    # An explicitly loaded import/reference contract must compare with the
    # other technology's same storage evidence. Production catalogs already
    # require the declared overlay before reaching this boundary.
    use_runtime_bindings = any(
        layer.source.postgis_reference is not None
        for layer in contract.layers.values()
    )
    for analysis_id in manifest_ids:
        candidate = (
            offline_analyses[analysis_id]
            if offline_analyses is not None
            else contract
            if analysis_id == contract.id
            else load_analysis(contract.region_id, analysis_id, use_runtime_bindings=use_runtime_bindings)
        )
        validate_contract(candidate)
        area_result = candidate.area_result
        if area_result is None or area_result.technology not in candidates:
            continue
        surface = candidate.eligible_surfaces.get(
            area_result.eligible_surface_id
        )
        if surface is None or surface.support_domain_id != support_domain.id:
            continue
        candidates[area_result.technology].append(candidate)

    problems = {
        technology: [candidate.id for candidate in contracts]
        for technology, contracts in candidates.items()
        if len(contracts) != 1
    }
    if problems:
        raise ValueError(
            "Technology support domain must resolve exactly one analysis per "
            f"declared technology: {problems}"
        )
    contracts = tuple(
        candidates[technology][0]
        for technology in support_domain.technologies
    )
    reference = contracts[0]
    reference_area = reference.area_result
    if reference_area is None:
        raise ValueError("Shared support analysis has no area-result contract")
    reference_surface = reference.eligible_surfaces[
        reference_area.eligible_surface_id
    ]
    for candidate in contracts[1:]:
        area_result = candidate.area_result
        if area_result is None:
            raise ValueError(
                f"Shared support analysis {candidate.id!r} has no area result"
            )
        surface = candidate.eligible_surfaces[area_result.eligible_surface_id]
        if any(
            (
                candidate.groups != reference.groups,
                candidate.layers != reference.layers,
                surface.support_observations
                != reference_surface.support_observations,
                _support_surface_contract_evidence(surface)
                != _support_surface_contract_evidence(reference_surface),
                _support_area_result_semantics(area_result)
                != _support_area_result_semantics(reference_area),
            )
        ):
            raise ValueError(
                "Technology analyses sharing a support domain must have "
                "equivalent group, layer/source, surface, and area-result "
                f"contracts: {reference.id!r} != {candidate.id!r}"
            )
    return contracts


def _shared_support_analysis_evidence(
    contracts: tuple[AnalysisContract, ...],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for contract in contracts:
        if any(layer.source.postgis_reference is not None for layer in contract.layers.values()):
            # These signatures describe the unchanged original observation
            # build, not its later storage. The mandatory overlay separately
            # proves every replaced source declaration and changes no controls.
            from .catalogs import load_analysis
            original = load_analysis(contract.region_id, contract.id, use_runtime_bindings=False)
            layers = dict(contract.layers)
            storage_fields = {
                "provider", "asset_manifest", "diagnostic_source_snapshot",
                "postgis_reference", "distance_provider", "distance_path",
                "distance_h3_resolution", "distance_coverage", "requires_explicit_parameters",
            }
            for layer_id, layer in contract.layers.items():
                if layer.source.postgis_reference is None:
                    continue
                previous = original.layers.get(layer_id)
                if previous is None:
                    raise ValueError("PostGIS support source has no original contract evidence")
                source_semantics = {key: value for key, value in asdict(layer.source).items() if key not in storage_fields}
                previous_semantics = {key: value for key, value in asdict(previous.source).items() if key not in storage_fields}
                requires_parameters = previous.source.requires_explicit_parameters or previous.source.diagnostic_source_snapshot is not None
                if source_semantics != previous_semantics or layer.source.requires_explicit_parameters != requires_parameters:
                    raise ValueError("PostGIS support source semantics differ from their original evidence")
                # Restore only storage evidence. Current layer operations,
                # parameters, surfaces and other groups still enter every hash.
                layers[layer_id] = replace(layer, source=previous.source)
            contract = replace(contract, layers=layers)
        area_result = contract.area_result
        if area_result is None:
            raise ValueError(
                f"Shared support analysis {contract.id!r} has no area result"
            )
        surface = contract.eligible_surfaces[area_result.eligible_surface_id]
        ordered_layers = [
            contract.layers[layer_id] for layer_id in sorted(contract.layers)
        ]
        evidence.append(
            {
                "analysis_id": contract.id,
                "technology": area_result.technology,
                "eligible_surface_id": area_result.eligible_surface_id,
                "group_ids": list(contract.groups),
                "layer_ids": [layer.id for layer in ordered_layers],
                "area_result_semantics_sha256": _canonical_contract_sha256(
                    _support_area_result_semantics(area_result)
                ),
                "eligible_surface_contract_sha256": (
                    _canonical_contract_sha256(
                        _support_surface_contract_evidence(surface)
                    )
                ),
                "layer_contracts_sha256": _canonical_contract_sha256(
                    [
                        canonical_contract_evidence(layer)
                        for layer in ordered_layers
                    ]
                ),
                "source_contracts_sha256": _canonical_contract_sha256(
                    [
                        canonical_contract_evidence(layer.source)
                        for layer in ordered_layers
                    ]
                ),
            }
        )
    return evidence


def _technology_support_observation_metadata(
    contract: AnalysisContract,
    *, offline_analyses: dict[str, AnalysisContract] | None = None,
) -> tuple[dict[str, Any], Path | None]:
    """Resolve and validate one surface's complete observation-set metadata."""

    surface = eligible_surface_contract_for_analysis(contract)
    support_domain = technology_support_domain_for_eligible_surface(contract)
    support_analyses = _shared_support_analysis_contracts(
        contract,
        support_domain,
        offline_analyses=offline_analyses,
    )
    analysis_bindings = _shared_support_analysis_evidence(support_analyses)
    support_domain_contract_sha256 = _canonical_contract_sha256(
        asdict(support_domain)
    )
    reference_analysis = support_analyses[0]
    group_order = {
        group_id: index
        for index, group_id in enumerate(reference_analysis.groups)
    }
    expected_layer_ids = [
        layer.id
        for layer in sorted(
            reference_analysis.layers.values(),
            key=lambda layer: (group_order[layer.group_id], layer.id),
        )
    ]
    observations = surface.support_observations
    metadata_bytes, metadata_path = _support_metadata_input(contract)
    try:
        metadata = json.loads(metadata_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Technology-support observation metadata is not UTF-8 JSON") from exc
    if not isinstance(metadata, dict) or metadata.get("schema_version") != "2.0":
        raise ValueError(
            "Technology-support observation metadata has an unsupported schema"
        )
    if any(
        (
            metadata.get("region_id") != contract.region_id,
            metadata.get("support_domain_id") != support_domain.id,
            metadata.get("technologies")
            != list(support_domain.technologies),
            metadata.get("analysis_bindings") != analysis_bindings,
            metadata.get("support_domain_contract_sha256")
            != support_domain_contract_sha256,
            metadata.get("groups") != list(reference_analysis.groups),
            metadata.get("native_crs") != support_domain.native_crs,
            metadata.get("distance_semantics")
            != "support_surface_representative_point_to_source",
            metadata.get("intersection_semantics")
            != "support_surface_geometry_intersects_source",
        )
    ):
        raise ValueError(
            "Technology-support observation metadata identity or semantics drifted"
        )
    eligible_cell_ids_sha256 = resolve_eligible_surface_cell_ids_sha256(
        contract
    )
    if eligible_cell_ids_sha256 != observations.cell_ids_sha256:
        raise ValueError(
            "Technology-support observation ids do not match the actual "
            "eligible-surface artifact"
        )
    support_surface = metadata.get("support_surface")
    if not isinstance(support_surface, dict) or any(
        (
            support_surface.get("resolution") != observations.resolution,
            support_surface.get("cell_count")
            != observations.expected_cell_count,
            support_surface.get("cell_ids_sha256")
            != observations.cell_ids_sha256,
            support_surface.get("sha256") != surface.sha256,
            Path(str(support_surface.get("path") or "")).name
            != Path(surface.path).name,
        )
    ):
        raise ValueError(
            "Technology-support observation metadata does not bind the "
            "eligible surface"
        )
    coverage = metadata.get("coverage_evidence")
    if not isinstance(coverage, dict) or any(
        (
            coverage.get("mode") != "complete",
            coverage.get("missing_observation_policy")
            != observations.missing_policy,
            coverage.get("expected_layer_count")
            != len(observations.layers),
            coverage.get("complete_layer_count")
            != len(observations.layers),
            coverage.get("expected_rows_per_layer")
            != observations.expected_cell_count,
            coverage.get("missing_cell_count") != 0,
            coverage.get("unexpected_cell_count") != 0,
            coverage.get("all_layers_complete") is not True,
        )
    ):
        raise ValueError(
            "Technology-support observations do not declare complete "
            "fail-closed coverage"
        )
    metadata_layer_ids = metadata.get("layer_ids")
    if (
        not isinstance(metadata_layer_ids, list)
        or len(metadata_layer_ids) != len(set(metadata_layer_ids))
        or metadata_layer_ids != expected_layer_ids
        or set(metadata_layer_ids) != set(observations.layers)
    ):
        raise ValueError(
            "Technology-support observation metadata layer set drifted"
        )
    metadata_layers = metadata.get("layers")
    if not isinstance(metadata_layers, list):
        raise ValueError(
            "Technology-support observation metadata has no layer evidence"
        )
    indexed_layers: dict[str, dict[str, Any]] = {}
    for item in metadata_layers:
        if not isinstance(item, dict):
            raise ValueError(
                "Technology-support observation layer evidence is invalid"
            )
        layer_id = str(item.get("layer_id") or "")
        if not layer_id or layer_id in indexed_layers:
            raise ValueError(
                "Technology-support observation layer evidence is duplicated"
            )
        indexed_layers[layer_id] = item
    if set(indexed_layers) != set(observations.layers):
        raise ValueError(
            "Technology-support observation layer evidence is incomplete"
        )
    input_sources: list[dict[str, str]] = []
    artifact_signature: list[dict[str, str]] = []
    for layer_id, declared in observations.layers.items():
        item = indexed_layers[layer_id]
        if any(
            (
                item.get("group_id") != contract.layers[layer_id].group_id,
                item.get("resolution") != observations.resolution,
                item.get("row_count") != observations.expected_cell_count,
                item.get("cell_ids_sha256") != observations.cell_ids_sha256,
                item.get("missing_cell_count") != 0,
                item.get("unexpected_cell_count") != 0,
                item.get("sha256") != declared.sha256,
                item.get("rows_sha256") != declared.rows_sha256,
                Path(str(item.get("path") or "")).name
                != Path(declared.path).name,
            )
        ):
            raise ValueError(
                f"Technology-support observation evidence for {layer_id!r} "
                "drifted"
            )
        assets = resolve_layer_assets(contract.layers[layer_id])
        source_geometry_sha256 = str(
            item.get("source_geometry_sha256") or ""
        ).strip().lower()
        if not source_geometry_sha256:
            raise ValueError(
                f"Technology-support observation evidence for {layer_id!r} "
                "has no source-geometry fingerprint"
            )
        if assets.runtime_identity is not None:
            if assets.upstream_geojson_sha256 != source_geometry_sha256:
                raise ValueError("PostGIS support source differs from its original geometry evidence")
            observed_source_bytes = assets.upstream_geojson_bytes
        else:
            verify_source_sha256(
                assets.geojson_path,
                source_geometry_sha256,
                f"Technology-support source geometry {layer_id}",
            )
            observed_source_bytes = assets.geojson_path.stat().st_size
        source_geometry_bytes = item.get("source_geometry_bytes")
        if (
            isinstance(source_geometry_bytes, bool)
            or not isinstance(source_geometry_bytes, int)
            or source_geometry_bytes != observed_source_bytes
        ):
            raise ValueError(
                f"Technology-support observation source geometry for "
                f"{layer_id!r} changed"
            )
        input_sources.append(
            {
                "layer_id": layer_id,
                "source_geometry_sha256": source_geometry_sha256,
            }
        )
        artifact_signature.append(
            {
                "layer_id": layer_id,
                "sha256": declared.sha256,
                "rows_sha256": declared.rows_sha256,
            }
        )
    surface_metadata_sha256 = str(
        support_surface.get("metadata_sha256") or ""
    ).strip().lower()
    if len(surface_metadata_sha256) != 64 or any(
        character not in "0123456789abcdef"
        for character in surface_metadata_sha256
    ):
        raise ValueError(
            "Technology-support observations have no eligible-surface "
            "metadata fingerprint"
        )
    build_inputs = {
        "region_id": contract.region_id,
        "support_domain_id": support_domain.id,
        "technologies": list(support_domain.technologies),
        "analysis_bindings": analysis_bindings,
        "support_domain_contract_sha256": (
            support_domain_contract_sha256
        ),
        "native_crs": support_domain.native_crs,
        "coverage_rule": support_domain.coverage_rule,
        "resolution": observations.resolution,
        "cell_count": observations.expected_cell_count,
        "cell_ids_sha256": observations.cell_ids_sha256,
        "surface_geojson_sha256": surface.sha256,
        "surface_metadata_sha256": surface_metadata_sha256,
        "sources": input_sources,
    }
    if metadata.get(
        "build_input_signature_sha256"
    ) != _canonical_contract_sha256(build_inputs):
        raise ValueError(
            "Technology-support observation build-input signature drifted"
        )
    if metadata.get(
        "artifact_set_signature_sha256"
    ) != _canonical_contract_sha256(artifact_signature):
        raise ValueError(
            "Technology-support observation artifact-set signature drifted"
        )
    return metadata, metadata_path


def resolve_support_observation_metadata_snapshot(
    contract: AnalysisContract,
) -> TechnologySupportObservationMetadataSnapshot:
    """Return the exact validated metadata bytes used by a consumer.

    The existing contract validator establishes all semantic and source
    bindings.  This public boundary then reads the file once, hashes and
    parses that same byte buffer, and requires the parsed value to equal the
    validated payload.  Callers can therefore bind execution to the consumed
    bytes instead of relying on a path or a prior stat-based cache lookup.
    """

    validated_payload, metadata_path = (
        _technology_support_observation_metadata(contract)
    )
    observations = eligible_surface_contract_for_analysis(
        contract
    ).support_observations
    payload_bytes, observed_path = _support_metadata_input(contract)
    if observed_path != metadata_path:
        raise ValueError("Support metadata storage changed during validation")
    actual_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    if actual_sha256 != observations.sha256:
        raise ValueError(
            "Technology-support observation metadata checksum drifted"
        )
    try:
        payload_json = payload_bytes.decode("utf-8")
        consumed_payload = json.loads(payload_json)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Technology-support observation metadata is not UTF-8 JSON"
        ) from exc
    if consumed_payload != validated_payload:
        raise ValueError(
            "Technology-support observation metadata changed during "
            "validation"
        )
    return TechnologySupportObservationMetadataSnapshot(
        path=metadata_path,
        payload_json=payload_json,
        sha256=actual_sha256,
        byte_count=len(payload_bytes),
    )


def resolve_support_observation_path(
    contract: AnalysisContract,
    layer_id: str,
    *, offline_analyses: dict[str, AnalysisContract] | None = None,
) -> Path:
    """Resolve one checksum-pinned support-domain observation table."""

    surface = eligible_surface_contract_for_analysis(contract)
    normalized_layer_id = str(layer_id).strip()
    layer = contract.layers.get(normalized_layer_id)
    if layer is not None and layer.source.postgis_reference is not None:
        raise ValueError("PostGIS support observations have no runtime file path")
    declared = surface.support_observations.layers.get(normalized_layer_id)
    if declared is None:
        raise KeyError(
            f"{contract.region_id}/{contract.id} has no support observation "
            f"for layer {normalized_layer_id!r}"
        )
    _technology_support_observation_metadata(contract, offline_analyses=offline_analyses)
    path = resolve_source_path(declared.provider, declared.path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Technology-support observation table is missing: {path}"
        )
    verify_source_sha256(
        path,
        declared.sha256,
        f"Technology-support observation {normalized_layer_id}",
    )
    return path


@lru_cache(maxsize=256)
def _load_support_observations_cached(
    path_str: str,
    file_size: int,
    file_mtime_ns: int,
    artifact_sha256: str,
    rows_sha256: str,
    expected_resolution: int,
    expected_cell_count: int,
    expected_cell_ids_sha256: str,
    layer_id: str,
) -> tuple[TechnologySupportObservation, ...]:
    del file_size, file_mtime_ns, artifact_sha256
    path = Path(path_str)
    rows: list[TechnologySupportObservation] = []
    cell_ids: list[str] = []
    rows_digest = hashlib.sha256()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["hex_id", "distance_m", "intersects"]:
            raise ValueError(
                f"Technology-support observation schema drifted: {path}"
            )
        for row_number, row in enumerate(reader, start=2):
            cell_id = str(row.get("hex_id") or "").strip()
            try:
                cell_resolution = int(h3.get_resolution(cell_id))
            except Exception as exc:
                raise ValueError(
                    f"Technology-support observation row {row_number} has "
                    f"an invalid H3 id: {cell_id!r}"
                ) from exc
            if cell_resolution != int(expected_resolution):
                raise ValueError(
                    f"Technology-support observation {cell_id!r} is R"
                    f"{cell_resolution}; expected R{expected_resolution}"
                )
            distance_text = str(row.get("distance_m") or "").strip()
            try:
                distance_m = float(distance_text)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(
                    f"Technology-support observation row {row_number} has "
                    "an invalid distance"
                ) from exc
            if not math.isfinite(distance_m) or distance_m < 0.0:
                raise ValueError(
                    f"Technology-support observation row {row_number} has "
                    "a non-finite or negative distance"
                )
            canonical_distance = f"{distance_m:.12f}".rstrip("0").rstrip(".")
            canonical_distance = canonical_distance or "0"
            if distance_text != canonical_distance:
                raise ValueError(
                    f"Technology-support observation row {row_number} has "
                    "non-canonical distance serialization"
                )
            intersects_text = str(row.get("intersects") or "").strip()
            if intersects_text not in {"true", "false"}:
                raise ValueError(
                    f"Technology-support observation row {row_number} has "
                    "an invalid intersects value"
                )
            intersects = intersects_text == "true"
            rows.append(
                TechnologySupportObservation(
                    cell_id=cell_id,
                    distance_m=distance_m,
                    intersects=intersects,
                )
            )
            cell_ids.append(cell_id)
            rows_digest.update(
                f"{cell_id},{canonical_distance},{intersects_text}\n".encode(
                    "utf-8"
                )
            )
    if len(rows) != expected_cell_count:
        raise ValueError(
            f"Technology-support observation {layer_id!r} has "
            f"{len(rows)} rows; expected {expected_cell_count}"
        )
    if cell_ids != sorted(cell_ids) or len(cell_ids) != len(set(cell_ids)):
        raise ValueError(
            f"Technology-support observation {layer_id!r} ids "
            "must be unique and sorted"
        )
    id_digest = hashlib.sha256(
        "".join(f"{cell_id}\n" for cell_id in cell_ids).encode("utf-8")
    ).hexdigest()
    if id_digest != expected_cell_ids_sha256:
        raise ValueError(
            f"Technology-support observation {layer_id!r} does "
            "not cover the declared eligible cell universe"
        )
    if rows_digest.hexdigest() != rows_sha256:
        raise ValueError(
            f"Technology-support observation {layer_id!r} row "
            "digest drifted"
        )
    return tuple(rows)


def resolve_support_observations(
    contract: AnalysisContract,
    layer_id: str,
    *, offline_analyses: dict[str, AnalysisContract] | None = None,
) -> tuple[TechnologySupportObservation, ...]:
    """Load one complete, exact-R7 support observation table fail closed."""

    surface = eligible_surface_contract_for_analysis(contract)
    observations = surface.support_observations
    normalized_layer_id = str(layer_id).strip()
    declared = observations.layers.get(normalized_layer_id)
    if declared is None:
        raise KeyError(
            f"{contract.region_id}/{contract.id} has no support observation "
            f"for layer {normalized_layer_id!r}"
        )
    layer = contract.layers.get(normalized_layer_id)
    if layer is not None and layer.source.postgis_reference is not None:
        # The same current contract/metadata seal applies regardless of where
        # row data lives. Its migrated source checks use snapshot provenance.
        _technology_support_observation_metadata(contract, offline_analyses=offline_analyses)
        reference = layer.source.postgis_reference
        # Validate source selection and base-domain membership before using the
        # same immutable snapshot for the distinct technology-support domain.
        assets = _resolve_postgis_layer_assets(layer)
        snapshot = load_postgis_runtime_snapshot(reference)
        try:
            domain = snapshot.domain(surface.support_domain_id, surface.resolution)
            observed = snapshot.observations(reference.source_id, surface.support_domain_id, surface.resolution)
        except StopIteration:
            raise ValueError("PostGIS technology-support observations are incomplete") from None
        if (
            domain.role != "technology_support"
            or domain.source_sha256 != surface.sha256
            or len(domain.cells) != surface.expected_cell_count
            or domain.cell_ids_sha256 != observations.cell_ids_sha256
            or len(observed.rows) != observations.expected_cell_count
            or observed.context_rows
            or observed.artifact_sha256 != declared.sha256
            or assets.runtime_identity != (reference.region_id, reference.database_schema, reference.revision_sha256)
        ):
            raise ValueError("PostGIS support observations differ from their declared surface")
        divisor = 1_000_000.0 if domain.area_unit == "m2" else 1.0
        if not math.isclose(math.fsum(cell.area_value / divisor for cell in domain.cells), surface.expected_total_area_km2, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError("PostGIS support-domain area drifted")
        rows_digest = hashlib.sha256()
        for row in observed.rows:
            distance_text = f"{row.distance_m:.12f}".rstrip("0").rstrip(".") or "0"
            intersects_text = "true" if row.intersects else "false"
            rows_digest.update(f"{row.cell_id},{distance_text},{intersects_text}\n".encode("utf-8"))
        if rows_digest.hexdigest() != declared.rows_sha256:
            raise ValueError("PostGIS support observation row fingerprint drifted")
        return tuple(TechnologySupportObservation(row.cell_id, row.distance_m, row.intersects) for row in observed.rows)
    path = resolve_support_observation_path(contract, normalized_layer_id, offline_analyses=offline_analyses)
    stat = path.stat()
    return _load_support_observations_cached(
        str(path.resolve()),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        declared.sha256,
        declared.rows_sha256,
        observations.resolution,
        observations.expected_cell_count,
        observations.cell_ids_sha256,
        normalized_layer_id,
    )


def eligible_surface_level(
    contract: AnalysisContract,
    resolution: int | None = None,
) -> EligibleSurfaceContract | EligibleSurfaceRollupContract:
    surface = eligible_surface_contract_for_analysis(contract)
    requested = surface.resolution if resolution is None else int(resolution)
    if requested == surface.resolution:
        return surface
    rollup = surface.rollups.get(requested)
    if rollup is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} eligible surface has no "
            f"R{requested} rollup"
        )
    return rollup


def resolve_eligible_surface_path(
    contract: AnalysisContract,
    resolution: int | None = None,
) -> Path:
    surface = eligible_surface_contract_for_analysis(contract)
    technology_support_domain_for_eligible_surface(contract)
    source_path = resolve_source_path(
        surface.source.provider,
        surface.source.path,
    )
    if not source_path.is_file():
        raise FileNotFoundError(
            f"Eligible-surface source is missing: {source_path}"
        )
    verify_source_sha256(
        source_path,
        surface.source.sha256,
        "Eligible-surface source",
    )
    level = eligible_surface_level(contract, resolution)
    path = resolve_source_path(level.provider, level.path)
    if not path.is_file():
        raise FileNotFoundError(f"Eligible-surface artifact is missing: {path}")
    verify_source_sha256(
        path,
        level.sha256,
        "Eligible-surface artifact",
    )
    return path


def resolve_eligible_surface_cell_areas_km2(
    contract: AnalysisContract,
    resolution: int | None = None,
) -> dict[str, float]:
    surface = eligible_surface_contract_for_analysis(contract)
    requested = surface.resolution if resolution is None else int(resolution)
    level = eligible_surface_level(contract, requested)
    if _analysis_domain_postgis_reference(contract) is None:
        resolve_eligible_surface_path(contract, requested)
    else:
        # Root's geography/context seam must preserve this current
        # support-source coverage check without opening archive files.
        technology_support_domain_for_eligible_surface(contract)
    areas = _read_analysis_domain_area_values(contract, 'technology_support', requested)
    expected_total = float(level.expected_total_area_km2)
    actual_total = math.fsum(areas.values())
    if not math.isclose(
        actual_total,
        expected_total,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError(
            f"{contract.region_id}/{contract.id} eligible-surface R{requested} "
            f"area changed ({actual_total} != {expected_total})"
        )
    if requested < surface.resolution:
        source_areas = resolve_eligible_surface_cell_areas_km2(
            contract,
            surface.resolution,
        )
        expected_parent_areas: dict[str, float] = {}
        for cell_id, area_km2 in source_areas.items():
            parent_id = str(h3.cell_to_parent(cell_id, requested))
            expected_parent_areas[parent_id] = (
                expected_parent_areas.get(parent_id, 0.0) + area_km2
            )
        if set(areas) != set(expected_parent_areas):
            raise ValueError(
                f"Eligible-surface R{requested} cells do not match R"
                f"{surface.resolution} parents"
            )
        for cell_id, expected_area in expected_parent_areas.items():
            if not math.isclose(
                areas[cell_id],
                expected_area,
                rel_tol=0.0,
                abs_tol=1e-6,
            ):
                raise ValueError(
                    f"Eligible-surface R{requested} cell {cell_id} does not "
                    f"derive from R{surface.resolution}"
                )
    return areas


def standard_result_surface_level(
    contract: AnalysisContract,
    resolution: int | None = None,
) -> StandardResultSurfaceContract | StandardResultSurfaceRollupContract:
    surface = contract.standard_result_surface
    if surface is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no standard-result "
            "surface contract"
        )
    requested = surface.resolution if resolution is None else int(resolution)
    if requested == surface.resolution:
        return surface
    rollup = surface.rollups.get(requested)
    if rollup is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} standard result surface has "
            f"no R{requested} rollup"
        )
    return rollup


def resolve_standard_result_surface_path(
    contract: AnalysisContract,
    resolution: int | None = None,
) -> Path:
    level = standard_result_surface_level(contract, resolution)
    path = resolve_source_path(level.provider, level.path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Standard-result-surface artifact is missing: {path}"
        )
    verify_source_sha256(
        path,
        level.sha256,
        "Standard-result-surface artifact",
    )
    return path


def resolve_standard_result_surface_cell_areas_km2(
    contract: AnalysisContract,
    resolution: int | None = None,
) -> dict[str, float]:
    surface = contract.standard_result_surface
    if surface is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no standard-result "
            "surface contract"
        )
    requested = surface.resolution if resolution is None else int(resolution)
    level = standard_result_surface_level(contract, requested)
    if _analysis_domain_postgis_reference(contract) is None:
        resolve_standard_result_surface_path(contract, requested)
    areas = _read_analysis_domain_area_values(contract, 'standard_result_surface', requested)
    actual_total = math.fsum(areas.values())
    if not math.isclose(
        actual_total,
        level.expected_total_area_km2,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError(
            f"Standard-result-surface R{requested} area total changed "
            f"({actual_total} != {level.expected_total_area_km2})"
        )
    domain_ids = set(resolve_analysis_domain_cell_ids(contract, requested))
    if set(areas) != domain_ids:
        raise ValueError(
            f"Standard-result-surface R{requested} cells do not match the "
            "analysis domain"
        )
    if requested < surface.resolution:
        source_areas = resolve_standard_result_surface_cell_areas_km2(
            contract,
            surface.resolution,
        )
        expected_parent_areas: dict[str, float] = {}
        for cell_id, area_km2 in source_areas.items():
            parent_id = str(h3.cell_to_parent(cell_id, requested))
            expected_parent_areas[parent_id] = (
                expected_parent_areas.get(parent_id, 0.0) + area_km2
            )
        if set(areas) != set(expected_parent_areas):
            raise ValueError(
                f"Standard-result-surface R{requested} does not match R"
                f"{surface.resolution} parents"
            )
        for cell_id, expected_area in expected_parent_areas.items():
            if not math.isclose(
                areas[cell_id],
                expected_area,
                rel_tol=0.0,
                abs_tol=1e-6,
            ):
                raise ValueError(
                    f"Standard-result-surface R{requested} cell {cell_id} "
                    f"does not derive from R{surface.resolution}"
                )
    return areas


def resolve_analysis_domain_cell_areas_km2(
    contract: AnalysisContract,
    resolution: int | None = None,
) -> dict[str, float]:
    domain = contract.analysis_domain
    if domain is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no analysis-domain contract"
        )
    if domain.cell_kind != "h3":
        raise ValueError(
            f"Unsupported analysis-domain cell kind: {domain.cell_kind}"
        )
    if domain.resolution < 0 or domain.resolution > 15:
        raise ValueError(
            f"Invalid H3 analysis-domain resolution: {domain.resolution}"
        )
    if domain.expected_cell_count <= 0:
        raise ValueError("Analysis domain expected cell count must be positive")
    if not domain.area_field.strip():
        raise ValueError("Analysis domain area field is required")
    if domain.area_unit not in {"m2", "km2"}:
        raise ValueError(
            f"Unsupported analysis-domain area unit: {domain.area_unit}"
        )

    if resolution is None:
        requested_resolution = domain.resolution
    else:
        if isinstance(resolution, bool):
            raise TypeError("resolution must be an integer")
        try:
            requested_resolution = int(operator.index(resolution))
        except TypeError as exc:
            raise TypeError("resolution must be an integer") from exc
    if requested_resolution == domain.resolution:
        source_areas = _read_analysis_domain_area_values(contract, 'standard_analysis', domain.resolution)
        source_total = math.fsum(source_areas.values())
        if not math.isclose(
            source_total,
            domain.expected_total_area_km2,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError(
                f"Analysis-domain R{domain.resolution} area total "
                f"{source_total:.12f} km2 does not match pinned total "
                f"{domain.expected_total_area_km2:.12f} km2"
            )
        return source_areas

    rollup = domain.rollups.get(requested_resolution)
    if rollup is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no R{requested_resolution} "
            "analysis-domain rollup"
        )
    target_areas = _read_analysis_domain_area_values(contract, 'standard_analysis', requested_resolution)
    source_areas = _read_analysis_domain_area_values(contract, 'standard_analysis', domain.resolution)
    source_total = math.fsum(source_areas.values())
    target_total = math.fsum(target_areas.values())
    for label, actual_total, expected_total in (
        ("source", source_total, domain.expected_total_area_km2),
        ("rollup", target_total, rollup.expected_total_area_km2),
    ):
        if not math.isclose(
            actual_total,
            expected_total,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError(
                f"Analysis-domain R{requested_resolution} {label} area "
                f"total {actual_total:.12f} km2 does not match pinned "
                f"total {expected_total:.12f} km2"
            )
    expected_parent_areas: dict[str, float] = {}
    for cell_id, area_km2 in source_areas.items():
        parent_id = str(h3.cell_to_parent(cell_id, requested_resolution))
        expected_parent_areas[parent_id] = (
            expected_parent_areas.get(parent_id, 0.0) + area_km2
        )
    expected_parent_ids = set(expected_parent_areas)
    target_set = set(target_areas)
    if target_set != expected_parent_ids:
        raise ValueError(
            f"Analysis-domain R{requested_resolution} rollup does not match "
            f"the R{domain.resolution} parent domain: "
            f"missing={len(expected_parent_ids - target_set)}, "
            f"unexpected={len(target_set - expected_parent_ids)}"
        )
    if not math.isclose(
        target_total,
        source_total,
        rel_tol=1e-12,
        abs_tol=1e-9,
    ):
        raise ValueError(
            f"Analysis-domain R{requested_resolution} rollup area total "
            f"{target_total:.12f} km2 does not match R{domain.resolution} "
            f"total {source_total:.12f} km2"
        )
    for parent_id, expected_area in expected_parent_areas.items():
        actual_area = target_areas[parent_id]
        if not math.isclose(
            actual_area,
            expected_area,
            rel_tol=1e-12,
            abs_tol=1e-9,
        ):
            raise ValueError(
                f"Analysis-domain R{requested_resolution} parent "
                f"{parent_id} area {actual_area:.12f} km2 does not match "
                f"its R{domain.resolution} children {expected_area:.12f} km2"
            )
    return target_areas


def resolve_analysis_domain_cell_ids(
    contract: AnalysisContract,
    resolution: int | None = None,
) -> tuple[str, ...]:
    return tuple(
        resolve_analysis_domain_cell_areas_km2(contract, resolution)
    )


def _clean_relative(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text or text.upper() == "NA":
        raise FileNotFoundError(f"Layer asset has no {field}")
    return text


def _resolve_diagnostic_source_snapshot_assets(layer: LayerContract) -> LayerAssets:
    """Resolve one checksum-pinned diagnostic snapshot with no legacy fallback."""

    reference = layer.source.diagnostic_source_snapshot
    if reference is None:
        raise ValueError("Diagnostic source-snapshot reference is missing")

    # Local imports keep the generic catalog/source modules acyclic.
    from .catalogs import load_region, load_region_geography
    from .paths import repo_root
    from .source_snapshot import (
        load_region_source_snapshot,
        sha256_file,
        snapshot_build_contract_signature,
    )

    region = load_region(reference.region_id)
    behavior_reference = region.get("behavior_reference") or {}
    landing_card = region.get("landing_card") or {}
    if (
        region.get("status") != "onboarding"
        or behavior_reference.get("status") != "diagnostic_only"
        or landing_card.get("enabled") is not False
    ):
        raise ValueError(
            "Diagnostic source snapshots require an onboarding, disabled, "
            "diagnostic-only region"
        )

    snapshot, snapshot_path = load_region_source_snapshot(
        reference.region_id,
        reference.snapshot_id,
    )
    if (
        snapshot.get("classification") != "diagnostic_candidate_only"
        or snapshot.get("accepted_public_reference") is not False
        or snapshot.get("product_route_eligible") is not False
    ):
        raise ValueError("Diagnostic source snapshot made a product claim")
    declared_layer = (snapshot.get("layers") or {}).get(layer.source.layer_id)
    if not isinstance(declared_layer, dict):
        raise KeyError(
            f"{layer.source.layer_id} is missing from diagnostic source "
            f"snapshot {reference.snapshot_id!r}"
        )
    if layer.source.layer_id != layer.id:
        raise ValueError(
            "Diagnostic source-snapshot layer id must match the analysis layer id"
        )

    output = snapshot["output"]
    expected_metadata_sha256 = str(output.get("metadata_sha256") or "")
    if (
        output.get("artifact_status") != "checksum_pinned"
        or len(expected_metadata_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in expected_metadata_sha256
        )
    ):
        raise ValueError(
            "Diagnostic source-snapshot metadata must be checksum-pinned"
        )
    output_directory = str(output["relative_directory"]).rstrip("/")
    metadata_name = _clean_relative(
        output.get("metadata_name"),
        "metadata_name",
    )
    metadata_path = resolve_source_path(
        "generated_runtime",
        f"{output_directory}/{metadata_name}",
    )
    if sha256_file(metadata_path) != expected_metadata_sha256:
        raise ValueError(
            "Diagnostic source-snapshot metadata checksum does not match its "
            "repo contract"
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            "Diagnostic source-snapshot metadata is unreadable"
        ) from exc
    if not isinstance(metadata, dict):
        raise ValueError("Diagnostic source-snapshot metadata must be an object")
    expected_domain = snapshot["analysis_domain"]
    metadata_domain = metadata.get("analysis_domain")
    coverage = metadata.get("coverage_evidence")
    if (
        metadata.get("schema_version") != "1.0"
        or metadata.get("snapshot_id") != snapshot.get("snapshot_id")
        or metadata.get("region_id") != reference.region_id
        or metadata.get("classification") != "diagnostic_candidate_only"
        or metadata.get("accepted_public_reference") is not False
        or metadata.get("product_route_eligible") is not False
        or metadata.get("contract_path")
        != snapshot_path.relative_to(repo_root()).as_posix()
        or metadata.get("contract_signature_sha256")
        != snapshot_build_contract_signature(snapshot)
        or metadata.get("distance_semantics") != output["distance_semantics"]
        or metadata.get("intersection_semantics")
        != output["intersection_semantics"]
        or not isinstance(metadata_domain, dict)
        or metadata_domain.get("domain_id") != expected_domain["domain_id"]
        or metadata_domain.get("resolution") != expected_domain["resolution"]
        or metadata_domain.get("cell_count")
        != expected_domain["expected_cell_count"]
        or metadata_domain.get("cell_ids_sha256")
        != expected_domain["cell_ids_sha256"]
        or not isinstance(coverage, dict)
        or coverage.get("mode") != "complete"
        or coverage.get("missing_observation_policy") != "error"
        or coverage.get("expected_layer_count") != len(snapshot["layers"])
        or coverage.get("complete_layer_count") != len(snapshot["layers"])
        or coverage.get("expected_rows_per_layer")
        != expected_domain["expected_cell_count"]
        or coverage.get("all_layers_complete") is not True
    ):
        raise ValueError(
            "Diagnostic source-snapshot metadata identity or domain binding "
            "drifted"
        )
    metadata_rows = metadata.get("layers")
    metadata_layer_ids = (
        [
            str(item.get("layer_id"))
            for item in metadata_rows
            if isinstance(item, dict)
        ]
        if isinstance(metadata_rows, list)
        else []
    )
    if (
        len(metadata_layer_ids) != len(snapshot["layers"])
        or len(metadata_layer_ids) != len(set(metadata_layer_ids))
        or set(metadata_layer_ids) != set(snapshot["layers"])
    ):
        raise ValueError(
            "Diagnostic source-snapshot metadata layer set drifted"
        )

    geography = load_region_geography(reference.region_id)
    region_domain = geography.analysis_domains.get(
        str(expected_domain["domain_id"])
    )
    if (
        region_domain is None
        or metadata_domain.get("sha256") != region_domain.artifacts.sha256
        or metadata_domain.get("metadata_sha256")
        != region_domain.metadata_sha256
    ):
        raise ValueError(
            "Diagnostic source snapshot is not bound to the regional domain"
        )
    metadata_row = (
        next(
            (
                item
                for item in metadata_rows
                if isinstance(item, dict)
                and item.get("layer_id") == layer.source.layer_id
            ),
            None,
        )
        if isinstance(metadata_rows, list)
        else None
    )
    if not isinstance(metadata_row, dict):
        raise ValueError(
            f"{layer.source.layer_id} is missing from validated diagnostic "
            "source-snapshot metadata"
        )
    if (
        metadata_row.get("source_feature_count")
        != declared_layer.get("expected_source_feature_count")
        or metadata_row.get("geojson_path") != f"{layer.id}.geojson"
        or metadata_row.get("distance_path") != f"{layer.id}.csv"
    ):
        raise ValueError(
            f"{layer.id} diagnostic source-snapshot layer binding drifted"
        )

    geojson_name = _clean_relative(
        metadata_row.get("geojson_path"),
        "geojson_path",
    )
    distance_name = _clean_relative(
        metadata_row.get("distance_path"),
        "distance_path",
    )
    geojson_path = resolve_source_path(
        "generated_runtime",
        f"{output_directory}/{geojson_name}",
    )
    distance_path = resolve_source_path(
        "generated_runtime",
        f"{output_directory}/{distance_name}",
    )
    for path, bytes_field, hash_field in (
        (geojson_path, "geojson_bytes", "geojson_sha256"),
        (distance_path, "distance_bytes", "distance_sha256"),
    ):
        if (
            not path.is_file()
            or path.stat().st_size != metadata_row.get(bytes_field)
            or sha256_file(path) != metadata_row.get(hash_field)
        ):
            raise ValueError(
                f"Diagnostic source-snapshot artifact failed integrity: "
                f"{path.name}"
            )
    return LayerAssets(
        geojson_path=geojson_path,
        distance_path=distance_path,
        manifest_status="ok",
        declared_geometry_family=_declared_geometry_family(
            declared_layer.get("geometry_family")
        ),
        feature_count=int(metadata_row["source_feature_count"]),
        geojson_sha256=str(metadata_row["geojson_sha256"]),
        geojson_bytes=int(metadata_row["geojson_bytes"]),
        distance_sha256=str(metadata_row["distance_sha256"]),
    )


def resolve_layer_assets(layer: LayerContract) -> LayerAssets:
    source = layer.source
    if source.postgis_reference is not None:
        return _resolve_postgis_layer_assets(layer)
    if source.diagnostic_source_snapshot is not None:
        return _resolve_diagnostic_source_snapshot_assets(layer)
    if source.provider is None or source.asset_manifest is None:
        raise ValueError("Layer source has no resolvable asset declaration")
    manifest_path = resolve_source_path(source.provider, source.asset_manifest)
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    row = next((item for item in rows if item.get("layer_id") == source.layer_id), None)
    if row is None:
        raise KeyError(f"{source.layer_id} is missing from {manifest_path}")
    distance_path = (
        resolve_source_path(source.distance_provider, source.distance_path)
        if source.distance_provider is not None and source.distance_path is not None
        else resolve_source_path(
            source.provider,
            _clean_relative(row.get("distance_path"), "distance_path"),
        )
    )
    geojson_path = resolve_source_path(
        source.provider,
        _clean_relative(row.get("geojson_path"), "geojson_path"),
    )
    validated_integrity: dict[str, tuple[str, int]] = {}
    for path, digest_field, bytes_field, label in (
        (
            geojson_path,
            "geojson_sha256",
            "geojson_bytes",
            f"Layer {layer.id} geometry",
        ),
        (
            distance_path,
            "distance_sha256",
            "distance_bytes",
            f"Layer {layer.id} distance observations",
        ),
    ):
        declared_digest = str(row.get(digest_field) or "").strip().lower()
        if declared_digest:
            verify_source_sha256(path, declared_digest, label)
        declared_bytes = str(row.get(bytes_field) or "").strip()
        if declared_bytes:
            try:
                expected_bytes = int(declared_bytes)
            except ValueError as exc:
                raise ValueError(
                    f"{label} has an invalid {bytes_field} declaration"
                ) from exc
            if expected_bytes < 0 or path.stat().st_size != expected_bytes:
                raise ValueError(
                    f"{label} byte count does not match its asset manifest"
                )
        stat = path.stat()
        actual_digest = declared_digest or _versioned_file_sha256(
            str(path.resolve()),
            int(stat.st_size),
            int(stat.st_mtime_ns),
            "",
        )
        validated_integrity[digest_field] = (
            actual_digest,
            stat.st_size,
        )
    return LayerAssets(
        geojson_path=geojson_path,
        distance_path=distance_path,
        manifest_status=str(row.get("status") or ""),
        declared_geometry_family=_declared_geometry_family(
            row.get("geometry_family")
        ),
        feature_count=int(float(row.get("feature_count") or 0)),
        geojson_sha256=validated_integrity["geojson_sha256"][0],
        geojson_bytes=validated_integrity["geojson_sha256"][1],
        distance_sha256=validated_integrity["distance_sha256"][0],
    )


def resolve_layer_source_assets(layer: LayerContract) -> LayerAssets:
    """Resolve and verify source geometry without consuming derived distances.

    Direct-distance rebuilds must be able to replace a missing or stale
    observation table.  The normal runtime resolver intentionally verifies
    both geometry and observations, so using it while rebuilding creates a
    circular dependency on the artifact being replaced.  This bounded
    resolver keeps the exact same manifest authority for the source geometry
    while deliberately leaving the derived distance path unverified.

    Diagnostic source snapshots are immutable evidence bundles and are not a
    supported rebuild input through this path.
    """

    source = layer.source
    if source.postgis_reference is not None:
        return _resolve_postgis_layer_assets(layer)
    if source.diagnostic_source_snapshot is not None:
        raise ValueError(
            "Diagnostic source snapshots are immutable and cannot be rebuilt "
            "through the direct-distance source-only resolver"
        )
    if source.provider is None or source.asset_manifest is None:
        raise ValueError("Layer source has no resolvable asset declaration")

    manifest_path = resolve_source_path(source.provider, source.asset_manifest)
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    row = next(
        (item for item in rows if item.get("layer_id") == source.layer_id),
        None,
    )
    if row is None:
        raise KeyError(f"{source.layer_id} is missing from {manifest_path}")

    geojson_path = resolve_source_path(
        source.provider,
        _clean_relative(row.get("geojson_path"), "geojson_path"),
    )
    declared_digest = str(row.get("geojson_sha256") or "").strip().lower()
    if declared_digest:
        verify_source_sha256(
            geojson_path,
            declared_digest,
            f"Layer {layer.id} geometry",
        )
    declared_bytes = str(row.get("geojson_bytes") or "").strip()
    if declared_bytes:
        try:
            expected_bytes = int(declared_bytes)
        except ValueError as exc:
            raise ValueError(
                f"Layer {layer.id} geometry has an invalid geojson_bytes "
                "declaration"
            ) from exc
        if expected_bytes < 0 or geojson_path.stat().st_size != expected_bytes:
            raise ValueError(
                f"Layer {layer.id} geometry byte count does not match its "
                "asset manifest"
            )
    stat = geojson_path.stat()
    actual_digest = declared_digest or _versioned_file_sha256(
        str(geojson_path.resolve()),
        int(stat.st_size),
        int(stat.st_mtime_ns),
        "",
    )

    # Keep the declared path in the shared DTO for compatibility, but do not
    # read, stat, or checksum it here.  It may be exactly the stale/missing
    # derived artifact this operation is rebuilding.
    distance_path = (
        resolve_source_path(source.distance_provider, source.distance_path)
        if (
            source.distance_provider is not None
            and source.distance_path is not None
        )
        else resolve_source_path(
            source.provider,
            _clean_relative(row.get("distance_path"), "distance_path"),
        )
    )
    return LayerAssets(
        geojson_path=geojson_path,
        distance_path=distance_path,
        manifest_status=str(row.get("status") or ""),
        declared_geometry_family=_declared_geometry_family(
            row.get("geometry_family")
        ),
        feature_count=int(float(row.get("feature_count") or 0)),
        geojson_sha256=actual_digest,
        geojson_bytes=stat.st_size,
    )


def detect_geojson_geometry_family(
    path: Path,
    geometry_collection_policy: str = "reject_mixed",
) -> str:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return detect_geometry_family(payload, geometry_collection_policy, label=str(path))


def detect_geometry_family(
    payload: dict[str, Any], geometry_collection_policy: str = "reject_mixed",
    *, label: str = "captured source",
) -> str:
    geometry_types: set[str] = set()

    def add_geometry_types(geometry: Any) -> None:
        if not isinstance(geometry, dict):
            return
        geometry_type = str(geometry.get("type") or "").lower()
        if geometry_type == "geometrycollection":
            for child in geometry.get("geometries") or []:
                add_geometry_types(child)
        elif geometry_type:
            geometry_types.add(geometry_type)

    if payload.get("type") == "FeatureCollection":
        for feature in payload.get("features") or []:
            add_geometry_types(feature.get("geometry"))
    elif payload.get("type") == "Feature":
        add_geometry_types(payload.get("geometry"))
    elif payload.get("type"):
        add_geometry_types(payload)

    families = set()
    for geometry_type in geometry_types:
        if "point" in geometry_type:
            families.add("point")
        elif "line" in geometry_type:
            families.add("line")
        elif "polygon" in geometry_type:
            families.add("polygon")
    if len(families) > 1 and geometry_collection_policy == "highest_dimension":
        dimensions = {"point": 0, "line": 1, "polygon": 2}
        return max(families, key=dimensions.__getitem__)
    if len(families) != 1:
        raise ValueError(f"Expected one geometry family in {label}, found: {sorted(families)}")
    return families.pop()


"""Root-owned sources.py insertion. Paths in DB evidence are provenance only."""


def _regional_domain_metadata_input(region_id, regional_domain):
    from .catalogs import load_analysis, load_region
    from .postgis_domain_inputs import regional_domain_metadata_bytes
    from .postgis_runtime import RuntimeBinding

    analysis = _analysis_for_regional_domain(region_id, regional_domain)
    reference = _analysis_domain_postgis_reference(analysis)
    if reference is not None:
        return regional_domain_metadata_bytes(
            load_postgis_runtime_snapshot(reference),
            RuntimeBinding(reference.region_id, reference.database_schema, reference.revision_sha256),
            analysis, regional_domain)
    path = resolve_region_analysis_domain_metadata_path(region_id, regional_domain.id)
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != regional_domain.metadata_sha256:
        raise ValueError("Regional domain metadata changed during file acquisition")
    return blob


def _support_metadata_input(contract):
    from .postgis_domain_inputs import support_observation_metadata_bytes
    from .postgis_runtime import RuntimeBinding

    reference = _analysis_domain_postgis_reference(contract)
    if reference is not None:
        blob = support_observation_metadata_bytes(
            load_postgis_runtime_snapshot(reference),
            RuntimeBinding(reference.region_id, reference.database_schema, reference.revision_sha256),
            contract)
        return blob, None
    observations = eligible_surface_contract_for_analysis(contract).support_observations
    path = resolve_source_path(observations.provider, observations.path)
    blob = path.read_bytes()
    if hashlib.sha256(blob).hexdigest() != observations.sha256:
        raise ValueError("Technology-support observation metadata checksum drifted")
    return blob, path


"""Root-owned source seam additions; source bytes remain import-only for DB."""


def _analysis_for_regional_domain(region_id, regional_domain):
    from .catalogs import load_analysis, load_region
    analyses = [load_analysis(region_id, name)
                for name in load_region(region_id)["analysis_manifests"]]
    matching = [analysis for analysis in analyses if analysis.analysis_domain == regional_domain.artifacts]
    if not matching:
        raise ValueError("No current analysis binds the requested geography domain")
    references = [_analysis_domain_postgis_reference(analysis) for analysis in matching]
    if any(reference is not None for reference in references):
        if any(reference is None for reference in references):
            raise ValueError("Shared regional domain cannot mix file and PostGIS storage")
        identities = {(ref.connection_alias, ref.region_id, ref.database_schema,
                       ref.revision_sha256, ref.domain_id, ref.resolution) for ref in references}
        if len(identities) != 1:
            raise ValueError("Regional analyses disagree about the current domain revision")
    return matching[0]


def _require_support_coverage_input(contract, support_domain):
    reference = _analysis_domain_postgis_reference(contract)
    if reference is None:
        resolve_region_geography_asset_path(contract.region_id, support_domain.coverage_geometry_id)
        return
    from .postgis_domain_inputs import require_support_coverage
    require_support_coverage(
        load_postgis_runtime_snapshot(reference),
        RuntimeBinding(reference.region_id, reference.database_schema, reference.revision_sha256),
        contract, support_domain)
