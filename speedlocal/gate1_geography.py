from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from typing import Any

from pyproj import CRS, Transformer
import shapely
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union

from .contracts import RegionGeographyAssetContract, RegionGeographyContract
from .paths import resolve_source_path
from .sources import verify_source_sha256


IDENTITY_ROLES = frozenset(
    {
        "administrative_boundary",
        "regional_identity_surface",
    }
)
ANALYSIS_SURFACE_ROLES = frozenset(
    {
        "analysis_surface",
        "technology_target_surface",
    }
)
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
GPKG_ENVELOPE_BYTES = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
AREA_BINDING_TOLERANCE_M2 = 1.0


@dataclass(frozen=True)
class Gate1GeographyBinding:
    """The two explicit, manifest-owned geography roles used by Gate 1."""

    identity: RegionGeographyAssetContract
    analysis_surface: RegionGeographyAssetContract
    identity_binding_status: str
    analysis_surface_binding_status: str
    identity_analysis_same_source: bool
    identity_analysis_source_relation: str
    positive_exclusion_required: bool


@dataclass(frozen=True)
class Gate1GeometryFingerprint:
    geometry: MultiPolygon
    geometry_sha256: str
    area_km2: float
    geometry_type: str


@dataclass(frozen=True)
class Gate1SourceGeometry:
    path: Path
    source_feature_count: int
    fingerprint: Gate1GeometryFingerprint


def _materialization_source_key(
    asset: RegionGeographyAssetContract,
) -> tuple[str, ...]:
    """Include every manifest field that can change materialized coordinates."""

    return (
        asset.provider,
        asset.path,
        asset.sha256,
        asset.format,
        asset.source_crs,
        asset.native_crs,
    )


def select_gate1_geography_binding(
    geography: RegionGeographyContract,
) -> Gate1GeographyBinding:
    identities = tuple(
        asset
        for asset in geography.geographies.values()
        if asset.role in IDENTITY_ROLES
    )
    analysis_surfaces = tuple(
        asset
        for asset in geography.geographies.values()
        if asset.role in ANALYSIS_SURFACE_ROLES
    )
    if len(analysis_surfaces) > 1:
        # Technology support may name the already reviewed analysis source
        # again. Only the standard-domain declaration can select that source;
        # every additional target must remain an exact materialization alias.
        standard_ids = {
            domain.coverage_geometry_id
            for domain in getattr(geography, "analysis_domains", {}).values()
        }
        selected = tuple(asset for asset in analysis_surfaces if asset.id in standard_ids)
        if len(standard_ids) == 1 and len(selected) == 1 and all(
            asset.id == selected[0].id
            or (
                asset.role == "technology_target_surface"
                and _materialization_source_key(asset)
                == _materialization_source_key(selected[0])
                and asset.water_policy == selected[0].water_policy
            )
            for asset in analysis_surfaces
        ):
            analysis_surfaces = selected
    if len(identities) != 1:
        raise ValueError(
            f"{geography.region_id}: Gate 1 requires exactly one explicit "
            "identity geography with role administrative_boundary or "
            f"regional_identity_surface; got {len(identities)}"
        )
    if len(analysis_surfaces) != 1:
        raise ValueError(
            f"{geography.region_id}: Gate 1 requires exactly one analysis "
            "geography with role analysis_surface or "
            f"technology_target_surface; got {len(analysis_surfaces)}"
        )

    identity = identities[0]
    analysis_surface = analysis_surfaces[0]
    same_source = _materialization_source_key(
        identity
    ) == _materialization_source_key(analysis_surface)
    if (
        same_source
        and identity.role == "administrative_boundary"
        and analysis_surface.water_policy in {
            "exclude_all_water",
            "exclude_sea_retain_inland_water",
        }
    ):
        raise ValueError(
            f"{geography.region_id}: an administrative identity cannot be "
            "relabelled as a water-excluding analysis surface over the same "
            "materialized source; declare a separately derived, checksum-pinned "
            "analysis geography"
        )
    return Gate1GeographyBinding(
        identity=identity,
        analysis_surface=analysis_surface,
        identity_binding_status=f"declared_{identity.role}",
        analysis_surface_binding_status=f"declared_{analysis_surface.role}",
        identity_analysis_same_source=same_source,
        identity_analysis_source_relation=(
            "same_manifest_source" if same_source else "distinct_manifest_sources"
        ),
        positive_exclusion_required=(
            not same_source
            and analysis_surface.water_policy == "exclude_all_water"
        ),
    )


def _as_epsg(value: str) -> int:
    authority = CRS.from_user_input(value).to_authority()
    if authority is None or authority[0].upper() != "EPSG":
        raise ValueError(f"CRS must resolve to EPSG: {value!r}")
    return int(authority[1])


def _geojson_geometries(path: Path) -> tuple[list[BaseGeometry], int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Gate 1 GeoJSON must be an object: {path}")
    payload_type = str(payload.get("type") or "")
    if payload_type == "FeatureCollection":
        features = payload.get("features")
        if not isinstance(features, list):
            raise ValueError(f"Gate 1 GeoJSON features must be a list: {path}")
        raw_geometries = [
            feature.get("geometry")
            for feature in features
            if isinstance(feature, dict)
        ]
    elif payload_type == "Feature":
        raw_geometries = [payload.get("geometry")]
    else:
        raw_geometries = [payload]
    geometries = [shape(item) for item in raw_geometries if item]
    return geometries, len(geometries)


def _gpkg_wkb(blob: bytes) -> bytes:
    if len(blob) < 8 or blob[:2] != b"GP":
        raise ValueError("GeoPackage geometry has no valid GP header")
    envelope_code = (blob[3] >> 1) & 0b111
    envelope_bytes = GPKG_ENVELOPE_BYTES.get(envelope_code)
    if envelope_bytes is None:
        raise ValueError(f"Unsupported GeoPackage envelope code: {envelope_code}")
    header_bytes = 8 + envelope_bytes
    if len(blob) <= header_bytes:
        raise ValueError("GeoPackage geometry contains no WKB payload")
    return blob[header_bytes:]


def _gpkg_geometries(path: Path) -> tuple[list[BaseGeometry], int, int]:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            """
            select table_name, column_name, srs_id
            from gpkg_geometry_columns
            order by table_name
            """
        ).fetchall()
        if len(rows) != 1:
            raise ValueError(
                "Gate 1 GeoPackage must contain exactly one geometry table; "
                f"got {rows!r}"
            )
        table_name, column_name, srs_id = rows[0]
        if not IDENTIFIER_PATTERN.fullmatch(str(table_name)):
            raise ValueError(f"Unsafe GeoPackage table name: {table_name!r}")
        if not IDENTIFIER_PATTERN.fullmatch(str(column_name)):
            raise ValueError(
                f"Unsafe GeoPackage geometry column: {column_name!r}"
            )
        quoted_table = '"' + str(table_name).replace('"', '""') + '"'
        quoted_column = '"' + str(column_name).replace('"', '""') + '"'
        blobs = connection.execute(
            f"select {quoted_column} from {quoted_table} "
            f"where {quoted_column} is not null"
        ).fetchall()
        geometries = [
            shapely.from_wkb(_gpkg_wkb(bytes(row[0]))) for row in blobs
        ]
        return geometries, len(geometries), int(srs_id)
    finally:
        connection.close()


def canonical_gate1_polygon(geometry: BaseGeometry) -> MultiPolygon:
    if geometry.is_empty or not geometry.is_valid:
        raise ValueError("Gate 1 geometry is empty or invalid")
    geometry = shapely.force_2d(geometry)
    if geometry.geom_type == "Polygon":
        geometry = MultiPolygon([geometry])
    if geometry.geom_type != "MultiPolygon":
        raise ValueError(
            "Gate 1 geometry must be Polygon or MultiPolygon, got "
            f"{geometry.geom_type}"
        )
    if not all(math.isfinite(float(value)) for value in geometry.bounds):
        raise ValueError("Gate 1 geometry has non-finite bounds")
    normalized = shapely.normalize(geometry)
    if normalized.is_empty or not normalized.is_valid:
        raise ValueError("Canonical Gate 1 geometry is empty or invalid")
    return normalized


def canonical_gate1_geometry_wkb(geometry: BaseGeometry) -> bytes:
    canonical = canonical_gate1_polygon(geometry)
    result = shapely.to_wkb(
        canonical,
        byte_order=1,
        output_dimension=2,
        include_srid=False,
        flavor="iso",
    )
    return bytes(result)


def gate1_geometry_sha256(geometry: BaseGeometry) -> str:
    return hashlib.sha256(canonical_gate1_geometry_wkb(geometry)).hexdigest()


def _projected_area_km2(geometry: BaseGeometry, native_crs: str) -> float:
    target = CRS.from_user_input(native_crs)
    if not target.is_projected:
        raise ValueError(f"Gate 1 native CRS must be projected: {native_crs!r}")
    axes = target.axis_info[:2]
    if len(axes) != 2 or any(
        axis.unit_conversion_factor is None
        or not math.isclose(
            float(axis.unit_conversion_factor),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for axis in axes
    ):
        raise ValueError(
            f"Gate 1 native CRS must use metres: {native_crs!r}"
        )
    transformer = Transformer.from_crs(4326, target, always_xy=True)
    native_geometry = transform(transformer.transform, geometry)
    area_km2 = float(native_geometry.area) / 1_000_000.0
    if not math.isfinite(area_km2) or area_km2 <= 0.0:
        raise ValueError("Gate 1 geometry area must be finite and positive")
    return area_km2


def fingerprint_gate1_geometry(
    geometry: BaseGeometry,
    *,
    native_crs: str,
) -> Gate1GeometryFingerprint:
    canonical = canonical_gate1_polygon(geometry)
    return Gate1GeometryFingerprint(
        geometry=canonical,
        geometry_sha256=gate1_geometry_sha256(canonical),
        area_km2=_projected_area_km2(canonical, native_crs),
        geometry_type=canonical.geom_type,
    )


def fingerprint_gate1_wkb(
    geometry_wkb: bytes | bytearray | memoryview,
    *,
    native_crs: str,
) -> Gate1GeometryFingerprint:
    try:
        geometry = shapely.from_wkb(bytes(geometry_wkb))
    except Exception as exc:
        raise ValueError("Gate 1 database geometry WKB is invalid") from exc
    return fingerprint_gate1_geometry(geometry, native_crs=native_crs)


def load_gate1_source_geometry(
    asset: RegionGeographyAssetContract,
) -> Gate1SourceGeometry:
    path = resolve_source_path(asset.provider, asset.path)
    if not path.is_file():
        raise FileNotFoundError(f"Gate 1 geography source is missing: {path}")
    verify_source_sha256(path, asset.sha256, f"Gate 1 {asset.role}")
    expected_epsg = _as_epsg(asset.source_crs)
    if asset.format == "geojson":
        geometries, source_feature_count = _geojson_geometries(path)
        observed_epsg = expected_epsg
    elif asset.format == "gpkg":
        geometries, source_feature_count, observed_epsg = _gpkg_geometries(path)
    else:
        raise ValueError(f"Unsupported Gate 1 geography format: {asset.format!r}")
    if not geometries:
        raise ValueError(f"Gate 1 geography source is empty: {path}")
    if observed_epsg != expected_epsg:
        raise ValueError(
            "Gate 1 geography CRS mismatch: contract "
            f"EPSG:{expected_epsg}, source EPSG:{observed_epsg}"
        )
    if any(geometry.is_empty or not geometry.is_valid for geometry in geometries):
        raise ValueError(
            f"Gate 1 source contains empty or invalid geometry: {path}"
        )
    merged = unary_union(geometries)
    if expected_epsg != 4326:
        transformer = Transformer.from_crs(expected_epsg, 4326, always_xy=True)
        merged = transform(transformer.transform, merged)
    fingerprint = fingerprint_gate1_geometry(
        merged,
        native_crs=asset.native_crs,
    )
    return Gate1SourceGeometry(
        path=path,
        source_feature_count=source_feature_count,
        fingerprint=fingerprint,
    )


def gate1_binding_evidence(binding: Gate1GeographyBinding) -> dict[str, Any]:
    return {
        "identity_binding_status": binding.identity_binding_status,
        "analysis_surface_binding_status": (
            binding.analysis_surface_binding_status
        ),
        "identity_analysis_same_source": (
            binding.identity_analysis_same_source
        ),
        "identity_analysis_source_relation": (
            binding.identity_analysis_source_relation
        ),
        "positive_exclusion_required": binding.positive_exclusion_required,
    }
