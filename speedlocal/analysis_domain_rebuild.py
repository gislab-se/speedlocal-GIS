from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

import h3
from pyproj import CRS
from shapely import normalize, union_all
from shapely.geometry import mapping, shape
from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class RebuiltAnalysisDomainDisplay:
    """Deterministic bytes and evidence for one rebuilt H3 display rollup."""

    payload_bytes: bytes
    sha256: str
    byte_count: int
    feature_count: int
    cell_ids_sha256: str
    total_area_km2: float
    repaired_reference_cell_ids: tuple[str, ...]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _lower_sha256(value: Any, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if (
        len(normalized) != 64
        or any(character not in "0123456789abcdef" for character in normalized)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return normalized


def _parse_feature_collection(value: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(value.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable UTF-8 GeoJSON") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("type") != "FeatureCollection"
        or not isinstance(payload.get("features"), list)
    ):
        raise ValueError(f"{label} must be a GeoJSON FeatureCollection")
    crs_declaration = payload.get("crs")
    if crs_declaration is not None:
        if (
            not isinstance(crs_declaration, dict)
            or crs_declaration.get("type") != "name"
            or not isinstance(crs_declaration.get("properties"), dict)
        ):
            raise ValueError(f"{label} has an invalid CRS declaration")
        try:
            declared_crs = CRS.from_user_input(
                crs_declaration["properties"].get("name")
            )
        except Exception as exc:
            raise ValueError(f"{label} has an invalid CRS declaration") from exc
        if not declared_crs.equals(CRS.from_epsg(4326), ignore_axis_order=True):
            raise ValueError(f"{label} must use CRS84/EPSG:4326")
    return payload


def _feature_index(
    payload: Mapping[str, Any],
    *,
    id_field: str,
    resolution: int,
    label: str,
    require_valid: bool,
) -> tuple[dict[str, tuple[dict[str, Any], BaseGeometry]], tuple[str, ...]]:
    if not str(id_field or "").strip():
        raise ValueError(f"{label} id_field is required")
    if isinstance(resolution, bool) or not isinstance(resolution, int):
        raise TypeError(f"{label} resolution must be an integer")
    if resolution < 0 or resolution > 15:
        raise ValueError(f"{label} resolution must be between 0 and 15")
    indexed: dict[str, tuple[dict[str, Any], BaseGeometry]] = {}
    invalid_ids: list[str] = []
    for index, feature in enumerate(payload["features"]):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"{label} feature {index} is not a GeoJSON Feature")
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(f"{label} feature {index} has no properties")
        cell_id = str(properties.get(id_field) or "").strip().lower()
        if (
            not cell_id
            or cell_id in indexed
            or not h3.is_valid_cell(cell_id)
            or h3.get_resolution(cell_id) != resolution
        ):
            raise ValueError(
                f"{label} feature {index} has an invalid or duplicate R"
                f"{resolution} H3 id"
            )
        raw_geometry = feature.get("geometry")
        if (
            not isinstance(raw_geometry, dict)
            or raw_geometry.get("type") not in {"Polygon", "MultiPolygon"}
        ):
            raise ValueError(f"{label} feature {cell_id} is not polygonal")
        try:
            geometry = shape(raw_geometry)
        except Exception as exc:
            raise ValueError(
                f"{label} feature {cell_id} geometry is unreadable"
            ) from exc
        if geometry.is_empty:
            raise ValueError(f"{label} feature {cell_id} geometry is empty")
        if not all(math.isfinite(value) for value in geometry.bounds):
            raise ValueError(f"{label} feature {cell_id} has non-finite bounds")
        min_x, min_y, max_x, max_y = geometry.bounds
        if min_x < -180.0 or max_x > 180.0 or min_y < -90.0 or max_y > 90.0:
            raise ValueError(f"{label} feature {cell_id} is outside CRS84")
        if not geometry.is_valid:
            invalid_ids.append(cell_id)
            if require_valid:
                raise ValueError(f"{label} feature {cell_id} geometry is invalid")
        indexed[cell_id] = (feature, geometry)
    return indexed, tuple(invalid_ids)


def _area_to_km2(
    value: Any,
    *,
    area_unit: str,
    cell_id: str,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Reference feature {cell_id} has an invalid area")
    area = float(value)
    if area_unit == "m2":
        area /= 1_000_000.0
    elif area_unit != "km2":
        raise ValueError(f"Unsupported reference area unit: {area_unit}")
    if not math.isfinite(area) or area <= 0.0:
        raise ValueError(f"Reference feature {cell_id} has a non-positive area")
    return area


def rebuild_h3_rollup_display(
    *,
    source_bytes: bytes,
    source_sha256: str,
    reference_bytes: bytes,
    reference_sha256: str,
    source_resolution: int,
    target_resolution: int,
    id_field: str,
    area_field: str,
    area_unit: str,
    expected_reference_invalid_cell_ids: Iterable[str],
    expected_feature_count: int,
    expected_total_area_km2: float,
    expected_output_sha256: str | None = None,
) -> RebuiltAnalysisDomainDisplay:
    """Rebuild a rollup's geometry from exact valid child geometries.

    The reference artifact remains the authority for feature order and
    properties. Its geometries are never repaired or emitted. Every output
    geometry is a normalized union of the checksum-bound source children.
    """

    if not isinstance(source_bytes, bytes) or not isinstance(reference_bytes, bytes):
        raise TypeError("Analysis-domain rebuild inputs must be bytes")
    if _sha256_bytes(source_bytes) != _lower_sha256(
        source_sha256, "Source SHA-256"
    ):
        raise ValueError("Analysis-domain source checksum changed")
    if _sha256_bytes(reference_bytes) != _lower_sha256(
        reference_sha256, "Reference SHA-256"
    ):
        raise ValueError("Analysis-domain reference checksum changed")
    if (
        isinstance(source_resolution, bool)
        or not isinstance(source_resolution, int)
        or isinstance(target_resolution, bool)
        or not isinstance(target_resolution, int)
    ):
        raise TypeError("Analysis-domain resolutions must be integers")
    if target_resolution < 0 or source_resolution > 15 or target_resolution >= source_resolution:
        raise ValueError("Target resolution must be coarser than source resolution")
    if (
        isinstance(expected_feature_count, bool)
        or not isinstance(expected_feature_count, int)
        or expected_feature_count <= 0
    ):
        raise ValueError("Expected feature count must be a positive integer")
    if (
        isinstance(expected_total_area_km2, bool)
        or not isinstance(expected_total_area_km2, (int, float))
        or not math.isfinite(float(expected_total_area_km2))
        or float(expected_total_area_km2) <= 0.0
    ):
        raise ValueError("Expected total area must be positive and finite")

    source_payload = _parse_feature_collection(source_bytes, "Source artifact")
    reference_payload = _parse_feature_collection(
        reference_bytes, "Reference artifact"
    )
    source, _ = _feature_index(
        source_payload,
        id_field=id_field,
        resolution=source_resolution,
        label="Source artifact",
        require_valid=True,
    )
    reference, reference_invalid_ids = _feature_index(
        reference_payload,
        id_field=id_field,
        resolution=target_resolution,
        label="Reference artifact",
        require_valid=False,
    )
    expected_invalid = tuple(
        str(value or "").strip().lower()
        for value in expected_reference_invalid_cell_ids
    )
    if (
        any(not value for value in expected_invalid)
        or len(expected_invalid) != len(set(expected_invalid))
        or tuple(reference_invalid_ids) != expected_invalid
    ):
        raise ValueError(
            "Reference invalid-cell set differs from the declared migration"
        )
    if len(reference) != expected_feature_count:
        raise ValueError(
            f"Reference has {len(reference)} features; expected "
            f"{expected_feature_count}"
        )

    children_by_parent: dict[str, list[tuple[str, BaseGeometry]]] = {}
    for child_id, (_, child_geometry) in source.items():
        parent_id = h3.cell_to_parent(child_id, target_resolution)
        children_by_parent.setdefault(parent_id, []).append(
            (child_id, child_geometry)
        )
    if set(children_by_parent) != set(reference):
        raise ValueError(
            "Source children and reference parent H3 ids do not reconcile"
        )

    rebuilt_features: list[dict[str, Any]] = []
    cell_areas: dict[str, float] = {}
    for raw_reference_feature in reference_payload["features"]:
        reference_feature = deepcopy(raw_reference_feature)
        properties = reference_feature["properties"]
        cell_id = str(properties[id_field]).strip().lower()
        children = sorted(children_by_parent[cell_id], key=lambda item: item[0])
        declared_child_count = properties.get("child_hex_count")
        if declared_child_count is not None and (
            isinstance(declared_child_count, bool)
            or not isinstance(declared_child_count, int)
            or declared_child_count != len(children)
        ):
            raise ValueError(
                f"Reference feature {cell_id} child count does not reconcile"
            )
        rebuilt_geometry = normalize(
            union_all([geometry for _, geometry in children])
        )
        if (
            rebuilt_geometry.is_empty
            or not rebuilt_geometry.is_valid
            or rebuilt_geometry.geom_type not in {"Polygon", "MultiPolygon"}
        ):
            raise ValueError(
                f"Rebuilt feature {cell_id} is not a valid polygonal geometry"
            )
        _, reference_geometry = reference[cell_id]
        if reference_geometry.is_valid:
            difference_area = reference_geometry.symmetric_difference(
                rebuilt_geometry
            ).area
            tolerance = max(1e-12, reference_geometry.area * 1e-10)
            if not math.isfinite(difference_area) or difference_area > tolerance:
                raise ValueError(
                    f"Rebuilt feature {cell_id} differs from its valid reference"
                )
        reference_feature["geometry"] = mapping(rebuilt_geometry)
        rebuilt_features.append(reference_feature)
        if area_field not in properties:
            raise ValueError(
                f"Reference feature {cell_id} has no {area_field}"
            )
        cell_areas[cell_id] = _area_to_km2(
            properties[area_field],
            area_unit=area_unit,
            cell_id=cell_id,
        )

    total_area_km2 = math.fsum(cell_areas.values())
    if not math.isclose(
        total_area_km2,
        float(expected_total_area_km2),
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise ValueError("Rebuilt analysis-domain total area changed")
    rebuilt_payload = deepcopy(reference_payload)
    rebuilt_payload["features"] = rebuilt_features
    payload_bytes = (
        json.dumps(
            rebuilt_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    output_sha256 = _sha256_bytes(payload_bytes)
    if expected_output_sha256 is not None and output_sha256 != _lower_sha256(
        expected_output_sha256, "Expected output SHA-256"
    ):
        raise ValueError("Rebuilt analysis-domain output checksum changed")
    cell_ids_sha256 = hashlib.sha256(
        "".join(f"{cell_id}\n" for cell_id in sorted(cell_areas)).encode("utf-8")
    ).hexdigest()
    return RebuiltAnalysisDomainDisplay(
        payload_bytes=payload_bytes,
        sha256=output_sha256,
        byte_count=len(payload_bytes),
        feature_count=len(rebuilt_features),
        cell_ids_sha256=cell_ids_sha256,
        total_area_km2=total_area_km2,
        repaired_reference_cell_ids=reference_invalid_ids,
    )


def write_rebuilt_analysis_domain_display(
    result: RebuiltAnalysisDomainDisplay,
    *,
    generated_root: Path,
    relative_output_path: str,
    overwrite: bool = False,
) -> Path:
    """Atomically write one already validated artifact outside the repo."""

    if not isinstance(result, RebuiltAnalysisDomainDisplay):
        raise TypeError("result must be a RebuiltAnalysisDomainDisplay")
    root = generated_root.expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Generated runtime root does not exist: {root}")
    relative = Path(str(relative_output_path or ""))
    if not str(relative) or relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Generated output path must be a safe relative path")
    output_path = (root / relative).resolve()
    try:
        output_path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Generated output path escapes its root") from exc
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite generated artifact: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f"{output_path.name}.tmp")
    try:
        temporary_path.write_bytes(result.payload_bytes)
        if _sha256_bytes(temporary_path.read_bytes()) != result.sha256:
            raise ValueError("Written analysis-domain artifact checksum changed")
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return output_path


__all__ = [
    "RebuiltAnalysisDomainDisplay",
    "rebuild_h3_rollup_display",
    "write_rebuilt_analysis_domain_display",
]
