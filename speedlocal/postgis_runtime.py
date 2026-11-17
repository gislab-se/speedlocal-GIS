"""Path-free, checksum-bound inputs for declared PostGIS standard groups.

This module reads already prepared inputs. It never imports files, chooses an
analysis method, repairs geometry, or falls back when a database read fails.
The caller owns caching; ``RuntimeBinding.cache_key`` identifies an immutable
revision and contains no connection credentials.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from itertools import chain
from typing import Any, Iterable

import h3
from psycopg import sql
from pyproj import CRS
from shapely import from_wkb, to_wkb


FORMAT_VERSION = "roads-postgis-1"
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,62}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
STANDARD_GROUP_IDS = frozenset({"roads", "population", "nature", "culture", "grid_infrastructure"})
_GEOMETRY_TYPES = {
    "point": {"Point", "MultiPoint"},
    "line": {"LineString", "MultiLineString"},
    "polygon": {"Polygon", "MultiPolygon"},
}
_REPRESENTATION_FAMILIES = {
    "network": {"line"}, "features": {"point", "line", "polygon"},
    "grid": {"point", "polygon"}, "privacy_protected_surface": {"polygon"},
}


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


def _digest(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise ValueError(f"Invalid {label}")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _rows_digest(rows: Iterable[Any]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(canonical_json(row).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _validated_wkb_geometry(value: bytes):
    geometry = from_wkb(bytes(value))
    if geometry.is_empty or not geometry.is_valid or geometry.has_z:
        raise ValueError("Runtime geometry must be valid, nonempty and two-dimensional")
    if not all(math.isfinite(value) for value in geometry.bounds):
        raise ValueError("Runtime geometry bounds must be finite")
    west, south, east, north = geometry.bounds
    if west < -180 or east > 180 or south < -90 or north > 90:
        raise ValueError("Runtime geometry must use WGS84 longitude/latitude")
    return geometry


def canonical_wkb(value: bytes) -> bytes:
    geometry = _validated_wkb_geometry(value)
    return bytes(to_wkb(geometry, byte_order=1, output_dimension=2, include_srid=False))


def _canonical_geometry_has_type(value: bytes, geometry_types: set[str] | str) -> bool:
    """Keep one decoded geometry for canonical bytes and family checks.

    Foreign values retain the public decoder path and its original call order.
    No decoded geometry escapes this validation call.
    """
    if type(value) is not bytes:
        if canonical_wkb(value) != value:
            return False
        actual_type = from_wkb(value).geom_type
    else:
        geometry = _validated_wkb_geometry(value)
        canonical = bytes(to_wkb(geometry, byte_order=1, output_dimension=2, include_srid=False))
        if canonical != value:
            return False
        actual_type = geometry.geom_type
    # Source-family lookup originally followed geometry decoding. Keep that
    # order even for a foreign string with custom hashing/comparison behavior.
    allowed_types = (_GEOMETRY_TYPES[geometry_types]
                     if isinstance(geometry_types, str) else geometry_types)
    return actual_type in allowed_types


@dataclass(frozen=True)
class RuntimeBinding:
    region_id: str
    database_schema: str
    revision_sha256: str

    def __post_init__(self) -> None:
        _identifier(self.region_id, "region id")
        _identifier(self.database_schema, "database schema")
        _digest(self.revision_sha256, "runtime revision")
        # The delivery's schema-per-region boundary is part of this contract.
        if self.database_schema != self.region_id:
            raise ValueError("Runtime schema must belong to the requested region")

    @property
    def cache_key(self) -> tuple[str, str, str]:
        return self.region_id, self.database_schema, self.revision_sha256


@dataclass(frozen=True)
class LayerGeometryInput:
    source_id: str
    source_sha256: str
    asset_sha256: str
    source_crs: str
    native_crs: str
    geometry_family: str
    data_representation: str
    original_feature_count: int
    provenance_json: str
    feature_wkb: tuple[bytes, ...]

    @property
    def asset_feature_count(self) -> int:
        return len(self.feature_wkb)

    @property
    def analysis_declared_feature_count(self) -> int:
        """Keep analysis asset metadata separate from catalog and part counts."""
        provenance = json.loads(self.provenance_json)
        if "analysis_declared_feature_count" in provenance:
            count = provenance["analysis_declared_feature_count"]
        elif provenance.get("group_id") == "roads":
            # Earlier road snapshots used the same declared and catalog count.
            # Other groups need explicit evidence; normalized parts cannot infer it.
            count = self.original_feature_count
        else:
            raise ValueError("Runtime source lacks its analysis-declared feature count")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError("Runtime analysis-declared feature count must be a positive integer")
        return count

    @property
    def geometry_sha256(self) -> str:
        return _rows_digest(part.hex() for part in self.feature_wkb)


def source_geometry_policies(source: LayerGeometryInput) -> tuple[str, str]:
    """Policy provenance for prepared geometry; older road revisions are strict."""
    preparation = json.loads(source.provenance_json).get("geometry_preparation")
    if preparation is None:
        return "reject_mixed", "reject_invalid"
    if not isinstance(preparation, dict) or set(preparation) != {
        "policy_version", "geometry_collection_policy", "geometry_validity_policy",
        "input_feature_count", "feature_source_indices",
    } or preparation["policy_version"] != "source_contract_v1":
        raise ValueError("Runtime source geometry preparation is invalid")
    policies = preparation["geometry_collection_policy"], preparation["geometry_validity_policy"]
    if policies[0] not in {"reject_mixed", "highest_dimension"} or policies[1] not in {"reject_invalid", "make_valid"}:
        raise ValueError("Runtime source geometry preparation policy is unsupported")
    count, indices = preparation["input_feature_count"], preparation["feature_source_indices"]
    if (
        isinstance(count, bool) or not isinstance(count, int) or count <= 0
        or not isinstance(indices, list) or len(indices) != source.asset_feature_count
        or any(isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < count for index in indices)
        or indices != sorted(indices)
    ):
        raise ValueError("Runtime source geometry preparation lost its original feature mapping")
    return policies


@dataclass(frozen=True)
class DomainCell:
    cell_id: str
    area_value: float
    geometry_wkb: bytes


@dataclass(frozen=True)
class DomainCellsInput:
    domain_id: str
    role: str
    resolution: int
    source_sha256: str
    area_unit: str
    cells: tuple[DomainCell, ...]
    display_metadata_json: str = ""

    @property
    def cell_ids_sha256(self) -> str:
        return hashlib.sha256("".join(f"{cell.cell_id}\n" for cell in self.cells).encode("ascii")).hexdigest()

    @property
    def geometry_sha256(self) -> str:
        return _rows_digest((cell.cell_id, cell.geometry_wkb.hex()) for cell in self.cells)

    @property
    def cells_sha256(self) -> str:
        return _rows_digest((cell.cell_id, float(cell.area_value).hex(), cell.geometry_wkb.hex()) for cell in self.cells)

    def cell_areas_km2(self) -> dict[str, float]:
        divisor = 1_000_000.0 if self.area_unit == "m2" else 1.0
        return {cell.cell_id: cell.area_value / divisor for cell in self.cells}


@dataclass(frozen=True)
class DistanceObservation:
    cell_id: str
    distance_m: float
    intersects: bool


@dataclass(frozen=True)
class LayerObservationsInput:
    source_id: str
    domain_id: str
    resolution: int
    artifact_sha256: str
    input_row_count: int
    distance_semantics: str
    intersection_semantics: str
    rows: tuple[DistanceObservation, ...]
    context_rows: tuple[DistanceObservation, ...] = ()

    @property
    def rows_sha256(self) -> str:
        return _rows_digest((row.cell_id, float(row.distance_m).hex(), row.intersects) for row in self.rows)

    @property
    def context_rows_sha256(self) -> str:
        return _rows_digest((row.cell_id, float(row.distance_m).hex(), row.intersects) for row in self.context_rows)

    @property
    def all_rows(self) -> tuple[DistanceObservation, ...]:
        """Original observations, before the engine's parent-domain filtering."""
        return tuple(sorted(self.rows + self.context_rows, key=lambda row: row.cell_id))


@dataclass(frozen=True)
class RoadRuntimeInputs:
    region_id: str
    sources: tuple[LayerGeometryInput, ...]
    domains: tuple[DomainCellsInput, ...]
    observation_sets: tuple[LayerObservationsInput, ...]

    def source(self, source_id: str) -> LayerGeometryInput:
        return next(item for item in self.sources if item.source_id == source_id)

    def domain(self, domain_id: str, resolution: int) -> DomainCellsInput:
        return next(item for item in self.domains if (item.domain_id, item.resolution) == (domain_id, resolution))

    def observations(self, source_id: str, domain_id: str, resolution: int) -> LayerObservationsInput:
        return next(item for item in self.observation_sets if (item.source_id, item.domain_id, item.resolution) == (source_id, domain_id, resolution))

    @property
    def revision_sha256(self) -> str:
        return hashlib.sha256(canonical_json(runtime_metadata(self)).encode("utf-8")).hexdigest()

    def binding(self) -> RuntimeBinding:
        return RuntimeBinding(self.region_id, self.region_id, self.revision_sha256)


def runtime_metadata(inputs: RoadRuntimeInputs) -> dict[str, Any]:
    """Small generated descriptor; each row set is independently fingerprinted."""
    return {
        "format": FORMAT_VERSION,
        "region_id": inputs.region_id,
        "sources": [{
            "source_id": source.source_id,
            "source_sha256": source.source_sha256,
            "asset_sha256": source.asset_sha256,
            "source_crs": source.source_crs,
            "native_crs": source.native_crs,
            "geometry_family": source.geometry_family,
            "data_representation": source.data_representation,
            "original_feature_count": source.original_feature_count,
            "asset_feature_count": source.asset_feature_count,
            "geometry_sha256": source.geometry_sha256,
            "provenance": json.loads(source.provenance_json),
        } for source in inputs.sources],
        "domains": [{
            "domain_id": domain.domain_id,
            "role": domain.role,
            "resolution": domain.resolution,
            "source_sha256": domain.source_sha256,
            "area_unit": domain.area_unit,
            "cell_count": len(domain.cells),
            "cell_ids_sha256": domain.cell_ids_sha256,
            "geometry_sha256": domain.geometry_sha256,
            "cells_sha256": domain.cells_sha256,
            **({"display_metadata": json.loads(domain.display_metadata_json)}
               if domain.display_metadata_json else {}),
        } for domain in inputs.domains],
        "observations": [{
            "source_id": item.source_id,
            "domain_id": item.domain_id,
            "resolution": item.resolution,
            "artifact_sha256": item.artifact_sha256,
            "input_row_count": item.input_row_count,
            "row_count": len(item.rows),
            "rows_sha256": item.rows_sha256,
            "distance_semantics": item.distance_semantics,
            "intersection_semantics": item.intersection_semantics,
            # Empty context preserves the metadata of complete earlier inputs.
            **({
                "context_row_count": len(item.context_rows),
                "context_rows_sha256": item.context_rows_sha256,
            } if item.context_rows else {}),
        } for item in inputs.observation_sets],
    }


def validate_runtime_inputs(inputs: RoadRuntimeInputs) -> None:
    _identifier(inputs.region_id, "region id")
    source_ids = tuple(item.source_id for item in inputs.sources)
    domain_keys = tuple((item.domain_id, item.resolution) for item in inputs.domains)
    observation_keys = tuple((item.source_id, item.domain_id, item.resolution) for item in inputs.observation_sets)
    for keys, label in ((source_ids, "sources"), (domain_keys, "domains"), (observation_keys, "observations")):
        if not keys or keys != tuple(sorted(set(keys))):
            raise ValueError(f"Runtime {label} must be nonempty, sorted and unique")
    for source in inputs.sources:
        _identifier(source.source_id, "source id")
        _digest(source.source_sha256, "source digest")
        _digest(source.asset_sha256, "source asset digest")
        if source.source_crs != "EPSG:4326" or source.geometry_family not in _REPRESENTATION_FAMILIES.get(source.data_representation, set()):
            raise ValueError("Runtime input requires a supported WGS84 geometry/representation pair")
        metric = CRS.from_user_input(source.native_crs)
        if not metric.is_projected or any(axis.unit_conversion_factor != 1 for axis in metric.axis_info):
            raise ValueError("Road distance CRS must be projected in metres")
        if isinstance(source.original_feature_count, bool) or not isinstance(source.original_feature_count, int) or source.original_feature_count <= 0 or not source.feature_wkb:
            raise ValueError("Road source feature counts must be positive")
        provenance = json.loads(source.provenance_json)
        if not isinstance(provenance, dict) or provenance.get("group_id") not in STANDARD_GROUP_IDS:
            raise ValueError("Source provenance must identify a declared standard group")
        if provenance["group_id"] == "roads" and (source.geometry_family, source.data_representation) != ("line", "network"):
            raise ValueError("Road inputs require line/network sources")
        if "analysis_declared_feature_count" in provenance:
            source.analysis_declared_feature_count
        source_geometry_policies(source)
        from .paths import repo_root
        from .source_catalog import validate_source_display_access

        validate_source_display_access(
            provenance.get("public_display_status"),
            provenance.get("local_review_authorization"),
            repo_root=repo_root(), region_id=inputs.region_id,
        )
        for part in source.feature_wkb:
            if not _canonical_geometry_has_type(part, source.geometry_family):
                raise ValueError("Runtime source geometry is not canonical WKB of its declared family")
    from .postgis_domain_inputs import validate_domain_display_metadata
    for domain in inputs.domains:
        validate_domain_display_metadata(domain)
        _identifier(domain.domain_id, "domain id")
        _digest(domain.source_sha256, "domain source digest")
        if domain.role not in {"standard_analysis", "standard_result_surface", "technology_support"}:
            raise ValueError("Unsupported runtime domain role")
        if isinstance(domain.resolution, bool) or not isinstance(domain.resolution, int) or not 0 <= domain.resolution <= 15:
            raise ValueError("Invalid domain H3 resolution")
        if domain.area_unit not in {"m2", "km2"}:
            raise ValueError("Invalid domain area unit")
        ids = tuple(cell.cell_id for cell in domain.cells)
        if not ids or ids != tuple(sorted(set(ids))):
            raise ValueError("Domain cells must be nonempty, sorted and unique")
        for cell in domain.cells:
            if h3.get_resolution(cell.cell_id) != domain.resolution:
                raise ValueError("Domain cell has the wrong H3 resolution")
            if isinstance(cell.area_value, bool) or not math.isfinite(cell.area_value) or cell.area_value <= 0:
                raise ValueError("Domain cell area must be finite and positive")
            if not _canonical_geometry_has_type(cell.geometry_wkb, {"Polygon", "MultiPolygon"}):
                raise ValueError("Domain cell must contain canonical polygon WKB")
    for domain_id in {item.domain_id for item in inputs.domains}:
        semantics = {(item.role, item.area_unit) for item in inputs.domains if item.domain_id == domain_id}
        if len(semantics) != 1:
            raise ValueError("Domain levels must share one role and area unit")
    for item in inputs.observation_sets:
        if item.source_id not in source_ids or (item.domain_id, item.resolution) not in domain_keys:
            raise ValueError("Observations reference an undeclared source or domain")
        _digest(item.artifact_sha256, "observation artifact digest")
        if isinstance(item.input_row_count, bool) or not isinstance(item.input_row_count, int) or item.input_row_count != len(item.rows) + len(item.context_rows):
            raise ValueError("Observation input count is invalid")
        if not item.distance_semantics or not item.intersection_semantics:
            raise ValueError("Observation semantics are required")
        domain = inputs.domain(item.domain_id, item.resolution)
        if domain.role == "standard_result_surface":
            raise ValueError("Standard result area is not a distance-observation domain")
        if tuple(row.cell_id for row in item.rows) != tuple(cell.cell_id for cell in domain.cells):
            raise ValueError("Observations must cover the exact domain once, in order")
        context_ids = tuple(row.cell_id for row in item.context_rows)
        if not isinstance(item.context_rows, tuple) or context_ids != tuple(sorted(set(context_ids))):
            raise ValueError("Context observations must be sorted and unique")
        if set(context_ids).intersection(row.cell_id for row in item.rows):
            raise ValueError("Context observations must stay outside the canonical domain")
        if domain.role == "technology_support" and item.context_rows:
            raise ValueError("Technology-support observations cannot contain context rows")
        for row in item.all_rows:
            if not h3.is_valid_cell(row.cell_id) or h3.get_resolution(row.cell_id) != item.resolution:
                raise ValueError("Observation cell has an invalid H3 identity or resolution")
            if isinstance(row.distance_m, bool) or not math.isfinite(row.distance_m) or row.distance_m < 0 or not isinstance(row.intersects, bool):
                raise ValueError("Observation distance/intersection is invalid")
    for domain_id, role in {(item.domain_id, item.role) for item in inputs.domains}:
        if role == "standard_result_surface":
            continue
        resolution = max(item.resolution for item in inputs.domains if item.domain_id == domain_id)
        if any((source_id, domain_id, resolution) not in observation_keys for source_id in source_ids):
            raise ValueError("Every road source needs complete base-domain observations")


def _builtin_fingerprint_rows(inputs: RoadRuntimeInputs) -> bool:
    """Only reuse fingerprint work that cannot invoke foreign scalar callbacks."""
    return (
        all(type(part) is bytes for source in inputs.sources for part in source.feature_wkb)
        and all(type(cell.cell_id) is str and type(cell.area_value) in (int, float)
                and type(cell.geometry_wkb) is bytes
                for domain in inputs.domains for cell in domain.cells)
        and all(type(row.distance_m) in (int, float)
                for item in inputs.observation_sets for row in chain(item.rows, item.context_rows))
    )


def _read_validated_runtime_metadata(cursor: Any, binding: RuntimeBinding) -> dict[str, Any]:
    from .postgis_revision_metadata import read_analysis_revision_metadata_with_digest
    revisions, metadata_digest = read_analysis_revision_metadata_with_digest(cursor, binding)
    if len(revisions) != 1 or revisions[0][0] != binding.region_id:
        raise ValueError("Runtime revision is missing or belongs to another region")
    metadata = revisions[0][1]
    if not isinstance(metadata, dict) or metadata.get("format") != FORMAT_VERSION or metadata.get("region_id") != binding.region_id:
        raise ValueError("Runtime revision metadata is invalid")
    if metadata_digest is None:
        metadata_digest = hashlib.sha256(canonical_json(metadata).encode("utf-8")).hexdigest()
    if metadata_digest != binding.revision_sha256:
        raise ValueError("Runtime revision metadata digest drifted")
    return metadata


def _read_road_runtime_rows(cursor: Any, binding: RuntimeBinding) -> RoadRuntimeInputs:
    """Shared decoding; the offline importer also verifies before its commit."""
    def select(columns: str, view: str, order: str = "") -> list[tuple[Any, ...]]:
        # All SQL fragments are internal constants; only the schema varies.
        query = sql.SQL("select " + columns + " from {}.{} where revision_sha256 = %s" + order).format(sql.Identifier(binding.database_schema), sql.Identifier(view))
        cursor.execute(query, (binding.revision_sha256,))
        return cursor.fetchall()
    metadata = _read_validated_runtime_metadata(cursor, binding)
    parts: dict[str, list[bytes]] = {}
    for source_id, feature_index, geometry, srid in select("source_id, feature_index, ST_AsBinary(geom, 'NDR'), ST_SRID(geom)", "analysis_runtime_sources", " order by source_id, feature_index"):
        rows = parts.setdefault(source_id, [])
        if feature_index != len(rows) or srid != 4326:
            raise ValueError("Runtime source feature sequence or CRS drifted")
        rows.append(bytes(geometry))
    sources = tuple(LayerGeometryInput(item["source_id"], item["source_sha256"], item["asset_sha256"], item["source_crs"], item["native_crs"], item["geometry_family"], item["data_representation"], item["original_feature_count"], canonical_json(item["provenance"]), tuple(parts.pop(item["source_id"], ()))) for item in metadata["sources"])
    if parts:
        raise ValueError("Runtime has undeclared source rows")
    cells: dict[tuple[str, int], list[DomainCell]] = {}
    for domain_id, resolution, cell_id, area, geometry, srid in select("domain_id, resolution, cell_id, area_value, ST_AsBinary(geom, 'NDR'), ST_SRID(geom)", "analysis_runtime_cells", " order by domain_id, resolution, cell_id"):
        if srid != 4326:
            raise ValueError("Runtime cell CRS drifted")
        cells.setdefault((domain_id, resolution), []).append(DomainCell(cell_id, area, bytes(geometry)))
    domains = tuple(DomainCellsInput(item["domain_id"], item["role"], item["resolution"], item["source_sha256"], item["area_unit"], tuple(cells.pop((item["domain_id"], item["resolution"]), ())), canonical_json(item["display_metadata"]) if "display_metadata" in item else "") for item in metadata["domains"])
    if cells:
        raise ValueError("Runtime has undeclared domain rows")
    observations: dict[tuple[str, str, int], list[DistanceObservation]] = {}
    for source_id, domain_id, resolution, cell_id, distance, intersects in select("source_id, domain_id, resolution, cell_id, distance_m, intersects", "analysis_runtime_observations", " order by source_id, domain_id, resolution, cell_id"):
        observations.setdefault((source_id, domain_id, resolution), []).append(DistanceObservation(cell_id, distance, intersects))
    context: dict[tuple[str, str, int], list[DistanceObservation]] = {}
    for source_id, domain_id, resolution, cell_id, distance, intersects in select("source_id, domain_id, resolution, cell_id, distance_m, intersects", "analysis_runtime_context_observations", " order by source_id, domain_id, resolution, cell_id"):
        context.setdefault((source_id, domain_id, resolution), []).append(DistanceObservation(cell_id, distance, intersects))
    sets = tuple(LayerObservationsInput(
        item["source_id"], item["domain_id"], item["resolution"],
        item["artifact_sha256"], item["input_row_count"],
        item["distance_semantics"], item["intersection_semantics"],
        tuple(observations.pop((item["source_id"], item["domain_id"], item["resolution"]), ())),
        tuple(context.pop((item["source_id"], item["domain_id"], item["resolution"]), ())),
    ) for item in metadata["observations"])
    if observations or context:
        raise ValueError("Runtime has undeclared observation rows")
    inputs = RoadRuntimeInputs(binding.region_id, sources, domains, sets)
    validate_runtime_inputs(inputs)
    rebuilt_metadata = runtime_metadata(inputs)
    if rebuilt_metadata != metadata:
        raise ValueError("Runtime input content drifted from its pinned revision")
    # The ordinary reader owns builtin rows. Hash its checked descriptor once;
    # public revision properties and foreign-scalar fixtures retain full rebuilds.
    revision = (hashlib.sha256(canonical_json(rebuilt_metadata).encode("utf-8")).hexdigest()
                if _builtin_fingerprint_rows(inputs) else inputs.revision_sha256)
    del rebuilt_metadata
    if revision != binding.revision_sha256:
        raise ValueError("Runtime input content drifted from its pinned revision")
    from .postgis_domain_inputs import validate_runtime_coverage_from_cursor
    validate_runtime_coverage_from_cursor(cursor, inputs)
    return inputs


def read_road_runtime_from_cursor(cursor: Any, binding: RuntimeBinding) -> RoadRuntimeInputs:
    """Read pinned app views using an already read-only transaction."""
    cursor.execute("show transaction_read_only")
    if cursor.fetchone() != ("on",):
        raise ValueError("Runtime reads require a read-only transaction")
    return _read_road_runtime_rows(cursor, binding)


def read_road_runtime(database_url: str, binding: RuntimeBinding) -> RoadRuntimeInputs:
    """Load a coherent snapshot without local files or credential-bearing errors."""
    if not database_url.strip():
        raise ValueError("A runtime database connection is required")
    import psycopg
    try:
        with psycopg.connect(database_url, connect_timeout=5, options="-c default_transaction_read_only=on -c statement_timeout=30000") as connection:
            # Transfer WKB bytea directly instead of its hexadecimal text form.
            with connection.cursor(binary=True) as cursor:
                cursor.execute("set transaction isolation level repeatable read, read only")
                from .postgis_runtime_cache import read_runtime_with_content_reuse
                return read_runtime_with_content_reuse(cursor, binding)
    except psycopg.Error:
        raise RuntimeError("PostGIS runtime input read failed") from None
