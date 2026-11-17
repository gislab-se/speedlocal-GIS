from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

import h3
import numpy as np
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import Polygon, mapping, shape

from .paths import repo_root


CHUNK_BYTES = 1024 * 1024
OUTPUT_COORDINATE_DECIMALS = 12
OUTPUT_PRECISION_GRID_DEGREES = 10.0**-OUTPUT_COORDINATE_DECIMALS
TOPOLOGY_TOLERANCE_M2 = 0.01
MINIMUM_CANDIDATE_BUFFER_EDGE_RATIO = 10.0


@dataclass(frozen=True)
class H3DomainLevel:
    resolution: int
    cell_ids: np.ndarray[Any, Any]
    geometries_native: np.ndarray[Any, Any]
    areas_km2: np.ndarray[Any, Any]


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def h3_id_set_sha256(cell_ids: Iterable[str]) -> str:
    payload = "".join(f"{cell_id}\n" for cell_id in sorted(cell_ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _safe_relative_path(value: str, label: str) -> PurePosixPath:
    if not value.strip() or "\\" in value:
        raise ValueError(f"{label} must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must stay within generated-root")
    return path


def _external_generated_root(value: Path) -> Path:
    root = value.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Generated runtime root does not exist: {root}")
    repository = repo_root().resolve()
    try:
        root.relative_to(repository)
    except ValueError:
        return root
    raise ValueError("H3 domain artifacts must stay outside the Git repository")


def _output_path(root: Path, value: str, label: str) -> Path:
    relative = _safe_relative_path(value, label)
    resolved = (root / Path(*relative.parts)).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes generated-root") from exc
    return resolved


def _read_boundary(
    path: Path,
    expected_sha256: str,
    source_crs: CRS,
    native_crs: CRS,
) -> tuple[Any, np.ndarray[Any, Any]]:
    normalized_sha256 = expected_sha256.strip().lower()
    if not _is_sha256(normalized_sha256):
        raise ValueError("Boundary sha256 must be a lowercase SHA256 digest")
    if not path.is_file():
        raise FileNotFoundError(f"Boundary source is missing: {path}")
    actual_sha256 = sha256_path(path)
    if actual_sha256 != normalized_sha256:
        raise ValueError(
            "Boundary checksum does not match its contract: "
            f"{path} ({actual_sha256} != {normalized_sha256})"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Boundary source is unreadable: {path}") from exc
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("Boundary source must be a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Boundary source must contain at least one feature")

    source_parts: list[Any] = []
    for index, feature in enumerate(features):
        raw_geometry = feature.get("geometry") if isinstance(feature, dict) else None
        if not isinstance(raw_geometry, dict):
            raise ValueError(f"Boundary feature {index} has no geometry")
        try:
            geometry = shapely.force_2d(shape(raw_geometry))
        except (TypeError, ValueError, shapely.GEOSException) as exc:
            raise ValueError(f"Boundary feature {index} is unreadable") from exc
        if geometry.is_empty or geometry.geom_type not in {
            "Polygon",
            "MultiPolygon",
        }:
            raise ValueError(f"Boundary feature {index} is not a polygon")
        if not geometry.is_valid:
            raise ValueError(f"Boundary feature {index} is topologically invalid")
        source_parts.extend(_polygon_parts(geometry))
    if not source_parts:
        raise ValueError("Boundary source has no polygonal area")

    native_parts = np.asarray(source_parts, dtype=object)
    if source_crs != native_crs:
        transformer = Transformer.from_crs(
            source_crs,
            native_crs,
            always_xy=True,
        )
        native_parts = shapely.transform(
            native_parts,
            transformer.transform,
            interleaved=False,
        )
    if not bool(np.all(shapely.is_valid(native_parts))):
        raise ValueError("Boundary transform produced invalid polygon geometry")
    boundary = shapely.union_all(native_parts)
    if boundary.is_empty or not boundary.is_valid:
        raise ValueError("Boundary dissolve produced invalid or empty geometry")
    boundary_parts = np.asarray(_polygon_parts(boundary), dtype=object)
    if not len(boundary_parts):
        raise ValueError("Boundary dissolve has no polygonal area")
    boundary = shapely.union_all(boundary_parts)
    area_m2 = float(shapely.area(boundary))
    if not math.isfinite(area_m2) or area_m2 <= 0.0:
        raise ValueError("Boundary must have positive projected area")
    return boundary, boundary_parts


def _polygon_parts(geometry: Any) -> list[Any]:
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type in {"MultiPolygon", "GeometryCollection"}:
        result: list[Any] = []
        for part in geometry.geoms:
            result.extend(_polygon_parts(part))
        return result
    return []


def _cell_polygon(cell_id: str) -> Polygon:
    return Polygon(
        [
            (longitude, latitude)
            for latitude, longitude in h3.cell_to_boundary(cell_id)
        ]
    )


def _candidate_cells(
    boundary_native: Any,
    source_resolution: int,
    candidate_buffer_m: float,
    native_crs: CRS,
) -> tuple[np.ndarray[Any, Any], float]:
    if isinstance(source_resolution, bool) or not 0 <= source_resolution <= 15:
        raise ValueError("source_resolution must be an H3 resolution from 0 to 15")
    average_edge_m = float(
        h3.average_hexagon_edge_length(source_resolution, unit="m")
    )
    buffer_edge_ratio = candidate_buffer_m / average_edge_m
    if (
        not math.isfinite(candidate_buffer_m)
        or candidate_buffer_m <= 0.0
        or not math.isfinite(buffer_edge_ratio)
        or buffer_edge_ratio < MINIMUM_CANDIDATE_BUFFER_EDGE_RATIO
    ):
        raise ValueError(
            "candidate_buffer_m must be at least ten average source-cell edges"
        )
    buffered_native = shapely.buffer(
        boundary_native,
        candidate_buffer_m,
        quad_segs=8,
    )
    to_web = Transformer.from_crs(native_crs, "EPSG:4326", always_xy=True)
    buffered_web = shapely.transform(
        buffered_native,
        to_web.transform,
        interleaved=False,
    )
    try:
        center_cells = {
            str(cell_id)
            for cell_id in h3.geo_to_cells(
                mapping(buffered_web),
                source_resolution,
            )
        }
    except (TypeError, ValueError, h3.H3BaseException) as exc:
        raise ValueError("H3 candidate enumeration failed") from exc
    if not center_cells:
        raise ValueError("H3 candidate enumeration produced no cells")
    candidates = set(center_cells)
    for cell_id in center_cells:
        candidates.update(str(item) for item in h3.grid_disk(cell_id, 1))
    invalid = [
        cell_id
        for cell_id in candidates
        if not h3.is_valid_cell(cell_id)
        or int(h3.get_resolution(cell_id)) != source_resolution
    ]
    if invalid:
        raise ValueError(f"Candidate generation produced invalid H3 ids: {invalid[:3]}")
    return np.asarray(sorted(candidates), dtype=str), buffer_edge_ratio


def _clip_candidates(
    candidate_ids: np.ndarray[Any, Any],
    boundary_native: Any,
    native_crs: CRS,
) -> H3DomainLevel:
    cells_web = np.asarray(
        [_cell_polygon(str(cell_id)) for cell_id in candidate_ids],
        dtype=object,
    )
    to_native = Transformer.from_crs("EPSG:4326", native_crs, always_xy=True)
    cells_native = shapely.transform(
        cells_web,
        to_native.transform,
        interleaved=False,
    )
    boundary_parts = np.asarray(_polygon_parts(boundary_native), dtype=object)
    if not len(boundary_parts):
        raise ValueError("Boundary has no polygonal parts for exact clipping")
    tree = shapely.STRtree(boundary_parts)
    pairs = np.asarray(
        tree.query(cells_native, predicate="intersects"),
        dtype=np.int64,
    )
    if pairs.size == 0:
        raise ValueError("No H3 candidate intersects the boundary")
    cell_indexes, boundary_indexes = pairs
    pair_intersections = np.asarray(
        shapely.intersection(
            cells_native[cell_indexes],
            boundary_parts[boundary_indexes],
        ),
        dtype=object,
    )
    pair_areas = np.asarray(shapely.area(pair_intersections), dtype=float)
    positive_pairs = np.isfinite(pair_areas) & (pair_areas > 0.0)
    grouped: dict[int, list[Any]] = {}
    for cell_index, geometry in zip(
        cell_indexes[positive_pairs],
        pair_intersections[positive_pairs],
        strict=True,
    ):
        grouped.setdefault(int(cell_index), []).append(geometry)

    intersecting_ids: list[str] = []
    intersections: list[Any] = []
    for cell_index in sorted(grouped):
        geometry = shapely.union_all(
            np.asarray(grouped[cell_index], dtype=object)
        )
        polygon_parts = _polygon_parts(geometry)
        if not polygon_parts:
            continue
        intersecting_ids.append(str(candidate_ids[cell_index]))
        intersections.append(
            shapely.union_all(np.asarray(polygon_parts, dtype=object))
        )
    intersections_array = np.asarray(intersections, dtype=object)
    selected_ids: list[str] = []
    selected_geometries: list[Any] = []
    selected_areas_km2: list[float] = []
    for cell_id, geometry in zip(
        intersecting_ids,
        intersections_array,
        strict=True,
    ):
        polygon_parts = _polygon_parts(geometry)
        if not polygon_parts:
            continue
        polygonal = shapely.union_all(np.asarray(polygon_parts, dtype=object))
        area_m2 = float(shapely.area(polygonal))
        if not math.isfinite(area_m2) or area_m2 <= 0.0:
            continue
        if not polygonal.is_valid:
            raise ValueError(f"Clipped H3 cell {cell_id} is invalid")
        selected_ids.append(str(cell_id))
        selected_geometries.append(polygonal)
        selected_areas_km2.append(area_m2 / 1_000_000.0)
    if not selected_ids:
        raise ValueError("Exact clipping produced no positive-area H3 cells")
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("Exact clipping produced duplicate H3 ids")
    return H3DomainLevel(
        resolution=int(h3.get_resolution(selected_ids[0])),
        cell_ids=np.asarray(selected_ids, dtype=str),
        geometries_native=np.asarray(selected_geometries, dtype=object),
        areas_km2=np.asarray(selected_areas_km2, dtype=float),
    )


def _rollup(source: H3DomainLevel, resolution: int) -> H3DomainLevel:
    if resolution < 0 or resolution >= source.resolution:
        raise ValueError(
            f"Rollup R{resolution} must be coarser than source R{source.resolution}"
        )
    geometries_by_parent: dict[str, list[Any]] = {}
    areas_by_parent: dict[str, list[float]] = {}
    for cell_id, geometry, area_km2 in zip(
        source.cell_ids,
        source.geometries_native,
        source.areas_km2,
        strict=True,
    ):
        parent = str(h3.cell_to_parent(str(cell_id), resolution))
        geometries_by_parent.setdefault(parent, []).append(geometry)
        areas_by_parent.setdefault(parent, []).append(float(area_km2))
    parent_ids = np.asarray(sorted(geometries_by_parent), dtype=str)
    return H3DomainLevel(
        resolution=resolution,
        cell_ids=parent_ids,
        geometries_native=np.asarray(
            [
                shapely.union_all(
                    np.asarray(geometries_by_parent[parent], dtype=object)
                )
                for parent in parent_ids
            ],
            dtype=object,
        ),
        areas_km2=np.asarray(
            [math.fsum(areas_by_parent[parent]) for parent in parent_ids],
            dtype=float,
        ),
    )


def _validate_level_topology(
    level: H3DomainLevel,
    boundary_native: Any,
) -> dict[str, float]:
    if not len(level.cell_ids):
        raise ValueError(f"R{level.resolution} domain is empty")
    geometry_areas_m2 = np.asarray(
        shapely.area(level.geometries_native),
        dtype=float,
    )
    declared_areas_m2 = level.areas_km2 * 1_000_000.0
    if not bool(np.all(np.isfinite(geometry_areas_m2) & (geometry_areas_m2 > 0))):
        raise ValueError(f"R{level.resolution} geometries must have positive area")
    if not bool(np.all(np.isfinite(declared_areas_m2) & (declared_areas_m2 > 0))):
        raise ValueError(f"R{level.resolution} declared areas must be positive")
    if not bool(
        np.allclose(
            geometry_areas_m2,
            declared_areas_m2,
            rtol=0.0,
            atol=1e-4,
        )
    ):
        raise ValueError(f"R{level.resolution} geometry and declared areas disagree")
    level_union = shapely.union_all(level.geometries_native)
    union_area_m2 = float(shapely.area(level_union))
    declared_total_m2 = math.fsum(float(value) for value in declared_areas_m2)
    overlap_m2 = max(0.0, declared_total_m2 - union_area_m2)
    uncovered_m2 = float(shapely.area(shapely.difference(boundary_native, level_union)))
    outside_m2 = float(shapely.area(shapely.difference(level_union, boundary_native)))
    if max(overlap_m2, uncovered_m2, outside_m2) > TOPOLOGY_TOLERANCE_M2:
        raise ValueError(
            f"R{level.resolution} does not reconstruct the boundary: "
            f"overlap={overlap_m2}, uncovered={uncovered_m2}, outside={outside_m2}"
        )
    return {
        "geometry_union_area_km2": union_area_m2 / 1_000_000.0,
        "overlap_area_m2": overlap_m2,
        "uncovered_target_m2": uncovered_m2,
        "outside_target_m2": outside_m2,
    }


def _round_coordinates(value: Any) -> Any:
    if isinstance(value, (tuple, list)):
        if value and all(isinstance(item, (int, float)) for item in value):
            return [round(float(item), OUTPUT_COORDINATE_DECIMALS) for item in value]
        return [_round_coordinates(item) for item in value]
    return value


def _serialized_geometry(geometry: Any) -> dict[str, Any]:
    raw = mapping(geometry)
    result = {
        "type": str(raw["type"]),
        "coordinates": _round_coordinates(raw["coordinates"]),
    }
    serialized = shape(result)
    if (
        serialized.is_empty
        or not serialized.is_valid
        or serialized.geom_type not in {"Polygon", "MultiPolygon"}
    ):
        raise ValueError("Coordinate serialization produced invalid geometry")
    return result


def _level_payload(
    level: H3DomainLevel,
    source_resolution: int,
    domain_id: str,
    domain_scope: str,
    coverage_geometry_id: str,
    native_crs: CRS,
) -> bytes:
    to_web = Transformer.from_crs(native_crs, "EPSG:4326", always_xy=True)
    web_geometries = np.asarray(
        shapely.transform(
            level.geometries_native,
            to_web.transform,
            interleaved=False,
        ),
        dtype=object,
    )
    web_geometries = np.asarray(
        shapely.set_precision(
            web_geometries,
            OUTPUT_PRECISION_GRID_DEGREES,
            mode="valid_output",
        ),
        dtype=object,
    )
    features = [
        {
            "type": "Feature",
            "properties": {
                "hex_id": str(cell_id),
                "area_km2": float(area_km2),
                "domain_id": domain_id,
                "domain_scope": domain_scope,
                "coverage_geometry_id": coverage_geometry_id,
                "coverage_rule": "positive_area_intersection",
                "source_h3_resolution": source_resolution,
                "target_h3_resolution": level.resolution,
                "geometry_status": "analysis_domain_intersection",
            },
            "geometry": _serialized_geometry(geometry),
        }
        for cell_id, geometry, area_km2 in zip(
            level.cell_ids,
            web_geometries,
            level.areas_km2,
            strict=True,
        )
    ]
    payload = {
        "type": "FeatureCollection",
        "name": f"{domain_id}_r{level.resolution}",
        "crs": {
            "type": "name",
            "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
        },
        "features": features,
    }
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _write_artifacts(
    payloads: Mapping[Path, bytes],
    overwrite: bool,
) -> None:
    existing = [path for path in payloads if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"Refusing to overwrite generated artifact: {existing[0]}")
    temporary_paths: list[Path] = []
    try:
        for path, payload in payloads.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f"{path.name}.tmp")
            temporary.write_bytes(payload)
            temporary_paths.append(temporary)
        for path in payloads:
            temporary = path.with_name(f"{path.name}.tmp")
            temporary.replace(path)
            temporary_paths.remove(temporary)
    finally:
        for temporary in temporary_paths:
            temporary.unlink(missing_ok=True)


def build_positive_intersection_h3_domain(
    *,
    boundary_path: Path,
    boundary_sha256: str,
    boundary_provider: str,
    boundary_reference: str,
    source_crs_value: str,
    native_crs_value: str,
    generated_root: Path,
    level_paths: Mapping[int, str],
    metadata_path: str,
    domain_id: str,
    domain_scope: str,
    coverage_geometry_id: str,
    source_resolution: int,
    rollup_resolutions: Iterable[int],
    candidate_buffer_m: float,
    status: str,
    expected_cell_counts: Mapping[int, int] | None = None,
    expected_cell_ids_sha256: Mapping[int, str] | None = None,
    expected_level_sha256: Mapping[int, str] | None = None,
    expected_metadata_sha256: str | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    if not domain_id.strip() or not domain_scope.strip():
        raise ValueError("domain_id and domain_scope are required")
    if not coverage_geometry_id.strip():
        raise ValueError("coverage_geometry_id is required")
    if status not in {"candidate", "active"}:
        raise ValueError("Domain status must be candidate or active")
    source_crs = CRS.from_user_input(source_crs_value)
    native_crs = CRS.from_user_input(native_crs_value)
    if not native_crs.is_projected:
        raise ValueError("native_crs must be projected for deterministic area")
    root = _external_generated_root(generated_root)
    rollups = tuple(int(value) for value in rollup_resolutions)
    if (
        len(rollups) != len(set(rollups))
        or tuple(sorted(rollups, reverse=True)) != rollups
        or any(value < 0 or value >= source_resolution for value in rollups)
    ):
        raise ValueError(
            "rollup_resolutions must be unique, descending, and coarser than source"
        )
    resolutions = (source_resolution, *rollups)
    if set(level_paths) != set(resolutions):
        raise ValueError("level_paths must declare exactly the source and rollup levels")
    resolved_level_paths = {
        resolution: _output_path(
            root,
            level_paths[resolution],
            f"R{resolution} output path",
        )
        for resolution in resolutions
    }
    resolved_metadata_path = _output_path(root, metadata_path, "metadata path")
    all_outputs = {*resolved_level_paths.values(), resolved_metadata_path}
    if len(all_outputs) != len(resolutions) + 1:
        raise ValueError("Every generated artifact must use a distinct path")

    boundary_native, _ = _read_boundary(
        boundary_path.expanduser().resolve(),
        boundary_sha256,
        source_crs,
        native_crs,
    )
    candidate_ids, buffer_edge_ratio = _candidate_cells(
        boundary_native,
        source_resolution,
        float(candidate_buffer_m),
        native_crs,
    )
    source_level = _clip_candidates(candidate_ids, boundary_native, native_crs)
    if source_level.resolution != source_resolution:
        raise ValueError("Exact clipping returned the wrong H3 source resolution")
    levels = {source_resolution: source_level}
    for resolution in rollups:
        levels[resolution] = _rollup(source_level, resolution)

    counts = dict(expected_cell_counts or {})
    digests = {
        int(resolution): str(value).lower()
        for resolution, value in (expected_cell_ids_sha256 or {}).items()
    }
    expected_hashes = {
        int(resolution): str(value).lower()
        for resolution, value in (expected_level_sha256 or {}).items()
    }
    for expected_mapping, label in (
        (counts, "expected_cell_counts"),
        (digests, "expected_cell_ids_sha256"),
        (expected_hashes, "expected_level_sha256"),
    ):
        if expected_mapping and set(expected_mapping) != set(resolutions):
            raise ValueError(f"{label} must cover every declared level")

    level_payloads: dict[int, bytes] = {}
    level_summaries: list[dict[str, Any]] = []
    for resolution in resolutions:
        level = levels[resolution]
        if resolution in counts and len(level.cell_ids) != counts[resolution]:
            raise ValueError(
                f"R{resolution} count drifted: "
                f"{len(level.cell_ids)} != {counts[resolution]}"
            )
        digest = h3_id_set_sha256(str(value) for value in level.cell_ids)
        if resolution in digests:
            expected_digest = digests[resolution]
            if not _is_sha256(expected_digest) or digest != expected_digest:
                raise ValueError(
                    f"R{resolution} H3-id digest does not match its contract"
                )
        topology = _validate_level_topology(level, boundary_native)
        payload = _level_payload(
            level,
            source_resolution,
            domain_id,
            domain_scope,
            coverage_geometry_id,
            native_crs,
        )
        artifact_sha256 = _sha256_bytes(payload)
        if resolution in expected_hashes:
            expected_hash = expected_hashes[resolution]
            if not _is_sha256(expected_hash) or artifact_sha256 != expected_hash:
                raise ValueError(
                    f"R{resolution} artifact checksum does not match its contract"
                )
        level_payloads[resolution] = payload
        level_summaries.append(
            {
                "resolution": resolution,
                "path": level_paths[resolution],
                "cell_count": int(len(level.cell_ids)),
                "cell_ids_sha256": digest,
                "total_area_km2": math.fsum(
                    float(value) for value in level.areas_km2
                ),
                "bytes": len(payload),
                "sha256": artifact_sha256,
                **topology,
            }
        )

    source_total_area_km2 = math.fsum(
        float(value) for value in source_level.areas_km2
    )
    metadata: dict[str, Any] = {
        "schema_version": "1.0",
        "domain_id": domain_id,
        "domain_scope": domain_scope,
        "status": status,
        "geometry_operation": "intersection",
        "coverage_rule": "positive_area_intersection",
        "empty_intersection_policy": "exclude",
        "missing_observation_policy": "error",
        "rollup_strategy": "derive_from_source_children",
        "source_h3_resolution": source_resolution,
        "rollup_resolutions": list(rollups),
        "native_crs": native_crs.to_string(),
        "area_field": "area_km2",
        "area_unit": "km2",
        "coverage_geometry": {
            "id": coverage_geometry_id,
            "provider": boundary_provider,
            "path": boundary_reference,
            "bytes": boundary_path.stat().st_size,
            "sha256": boundary_sha256.lower(),
            "source_crs": source_crs.to_string(),
        },
        "candidate_generation": {
            "method": "native_boundary_buffer_polyfill_plus_one_h3_ring",
            "candidate_buffer_m": float(candidate_buffer_m),
            "candidate_buffer_to_average_h3_edge_ratio": buffer_edge_ratio,
            "candidate_cell_count": int(len(candidate_ids)),
            "selection_rule": (
                "strictly_positive_projected_intersection_area"
            ),
        },
        "topology": {
            "tolerance_m2": TOPOLOGY_TOLERANCE_M2,
            "output_coordinate_decimals": OUTPUT_COORDINATE_DECIMALS,
            "target_area_km2": float(shapely.area(boundary_native)) / 1_000_000.0,
            "source_area_sum_km2": source_total_area_km2,
        },
        "id_digest_canonicalization": (
            "lowercase H3 ids sorted lexicographically, one id plus LF per row"
        ),
        "levels": level_summaries,
    }
    metadata_payload = (
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    metadata_sha256 = _sha256_bytes(metadata_payload)
    if expected_metadata_sha256 is not None:
        normalized_expected_metadata = expected_metadata_sha256.lower()
        if (
            not _is_sha256(normalized_expected_metadata)
            or metadata_sha256 != normalized_expected_metadata
        ):
            raise ValueError("Domain metadata checksum does not match its contract")

    payloads = {
        resolved_level_paths[resolution]: level_payloads[resolution]
        for resolution in resolutions
    }
    payloads[resolved_metadata_path] = metadata_payload
    _write_artifacts(payloads, overwrite)
    return {
        **metadata,
        "metadata": {
            "path": metadata_path,
            "bytes": len(metadata_payload),
            "sha256": metadata_sha256,
        },
    }
