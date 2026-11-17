from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from threading import RLock
from typing import Any, Mapping

import h3
from pyproj import CRS
from shapely.geometry import shape

from .area_result import (
    AreaCellResult, TechnologyAreaResult, rollup_native_area_result, run_area_analysis,
)
from . import area_result as area_engine
from .catalogs import load_analysis
from .contracts import AnalysisContract
from .sources import (
    eligible_surface_contract_for_analysis,
    eligible_surface_level,
    read_analysis_domain_input,
)
from .validation import validate_contract
from .workspace_request import (
    WorkspaceAnalysisRequest,
    authorize_catalog_workspace_analysis_request,
    parse_workspace_analysis_request,
    retarget_workspace_analysis_request_from_contract,
    validate_workspace_analysis_request_from_contract,
)


WORKSPACE_AREA_RESULT_SCHEMA_VERSION = "1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class WorkspaceAreaCellResult:
    cell_id: str
    model_area_km2: float
    remaining_area_km2: float
    potential_pct: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "model_area_km2": self.model_area_km2,
            "remaining_area_km2": self.remaining_area_km2,
            "potential_pct": self.potential_pct,
        }


@dataclass(frozen=True)
class WorkspaceAreaExecutionResult:
    schema_version: str
    capability_id: str
    access_scope: str
    region_id: str
    analysis_id: str
    technology: str
    request_signature_sha256: str
    request: WorkspaceAnalysisRequest
    eligible_surface_id: str
    support_domain_id: str
    target_resolution: int
    surface_artifact_provider: str
    surface_artifact_path: str
    surface_artifact_sha256: str
    surface_artifact_bytes: int
    surface_id_field: str
    surface_area_field: str
    surface_area_unit: str
    surface_feature_collection_json: str
    declared_surface_cell_count: int
    declared_surface_total_area_km2: float
    cell_count: int
    cell_ids_sha256: str
    selected_layer_ids: tuple[str, ...]
    active_group_ids: tuple[str, ...]
    model_area_km2: float
    remaining_area_km2: float
    potential_pct: float
    cells: tuple[WorkspaceAreaCellResult, ...]
    result_signature_sha256: str
    surface_upstream_sha256: str = ''
    surface_runtime_revision_sha256: str = ''

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "capability_id": self.capability_id,
            "access_scope": self.access_scope,
            "region_id": self.region_id,
            "analysis_id": self.analysis_id,
            "technology": self.technology,
            "request_signature_sha256": self.request_signature_sha256,
            "request": self.request.as_dict(),
            "eligible_surface_id": self.eligible_surface_id,
            "support_domain_id": self.support_domain_id,
            "target_resolution": self.target_resolution,
            "surface_artifact_provider": self.surface_artifact_provider,
            "surface_artifact_path": self.surface_artifact_path,
            "surface_artifact_sha256": self.surface_artifact_sha256,
            "surface_artifact_bytes": self.surface_artifact_bytes,
            "surface_id_field": self.surface_id_field,
            "surface_area_field": self.surface_area_field,
            "surface_area_unit": self.surface_area_unit,
            "surface_feature_collection_json": (
                self.surface_feature_collection_json
            ),
            "declared_surface_cell_count": self.declared_surface_cell_count,
            "declared_surface_total_area_km2": (
                self.declared_surface_total_area_km2
            ),
            "cell_count": self.cell_count,
            "cell_ids_sha256": self.cell_ids_sha256,
            "selected_layer_ids": list(self.selected_layer_ids),
            "active_group_ids": list(self.active_group_ids),
            "model_area_km2": self.model_area_km2,
            "remaining_area_km2": self.remaining_area_km2,
            "potential_pct": self.potential_pct,
            "cells": [cell.as_dict() for cell in self.cells],
            "result_signature_sha256": self.result_signature_sha256,
        }
        # Empty file-reference evidence retains its original JSON/signature.
        if self.surface_upstream_sha256 or self.surface_runtime_revision_sha256:
            payload.update(surface_upstream_sha256=self.surface_upstream_sha256,
                           surface_runtime_revision_sha256=self.surface_runtime_revision_sha256)
        return payload


@dataclass(frozen=True)
class _EligibleSurfaceSnapshot:
    provider: str
    path: str
    sha256: str
    byte_count: int
    id_field: str
    area_field: str
    area_unit: str
    feature_collection_json: str
    resolution: int
    expected_cell_count: int
    expected_total_area_km2: float
    cell_ids_sha256: str
    cell_areas_km2: tuple[tuple[str, float], ...]
    upstream_sha256: str = ''
    runtime_revision_sha256: str = ''

    def area_map(self) -> dict[str, float]:
        return dict(self.cell_areas_km2)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _cell_ids_sha256(values: tuple[str, ...] | list[str]) -> str:
    return hashlib.sha256(
        "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    ).hexdigest()


def workspace_analysis_request_signature(
    request: WorkspaceAnalysisRequest,
) -> str:
    if not isinstance(request, WorkspaceAnalysisRequest):
        raise TypeError("request must be a WorkspaceAnalysisRequest")
    parsed = parse_workspace_analysis_request(request.as_dict())
    if parsed != request:
        raise ValueError("Workspace area request is not canonical")
    return _canonical_sha256(request.as_dict())


def _exact_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be an exact non-empty string")
    return value


def _payload_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty text")
    return value


def _digest(value: Any, label: str) -> str:
    text = _exact_text(value, label)
    if _SHA256.fullmatch(text) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _integer(value: Any, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{label} must be {qualifier}")
    return value


def _float(value: Any, label: str, *, positive: bool = False) -> float:
    if not isinstance(value, float) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite JSON float")
    if value < (0.0 if not positive else math.nextafter(0.0, 1.0)):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{label} must be {qualifier}")
    return value


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    result = tuple(_exact_text(item, f"{label} item") for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must be unique")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(
            f"{label} keys drifted: expected={sorted(expected)}, "
            f"actual={sorted(value)}"
        )


_SURFACE_VALIDATION_MAX_ENTRIES = 16
_SURFACE_VALIDATION_MAX_BYTES = 64 * 1024 * 1024
_surface_validation_cache: OrderedDict = OrderedDict()
_surface_validation_bytes = 0
_surface_validation_generation = 0
_surface_validation_lock = RLock()


def clear_workspace_surface_validation_cache() -> None:
    """Release content-only geometry evidence; no source readiness is cached."""
    global _surface_validation_bytes, _surface_validation_generation
    with _surface_validation_lock:
        _surface_validation_cache.clear()
        _surface_validation_bytes = 0
        _surface_validation_generation += 1


def _surface_cells_from_feature_collection(
    payload_text: str,
    *,
    resolution: int,
    id_field: str,
    area_field: str,
    area_unit: str,
) -> dict[str, float]:
    """Reuse pure validation of exact text/fields and return a fresh area map.

    Current source, request, artifact, result-cell and signature checks remain
    in their callers. The cache contains only immutable cell-id/area pairs.
    """
    global _surface_validation_bytes
    arguments = (payload_text, resolution, id_field, area_field, area_unit)
    cacheable = (type(payload_text) is str and type(resolution) is int
                 and all(type(value) is str for value in arguments[2:]))
    with _surface_validation_lock:
        entry = _surface_validation_cache.get(arguments) if cacheable else None
        if entry is not None:
            _surface_validation_cache.move_to_end(arguments)
            return dict(entry[0])
        generation = _surface_validation_generation
    areas = _validate_surface_cells_from_feature_collection(
        payload_text, resolution=resolution, id_field=id_field,
        area_field=area_field, area_unit=area_unit,
    )
    if not cacheable:
        return areas
    cells = tuple(areas.items())
    # Charge retained text, key, immutable pairs, scalar referents and entry.
    # Shared values are deliberately counted separately for each entry.
    charge = (sys.getsizeof(arguments) + sum(sys.getsizeof(value) for value in arguments)
              + sys.getsizeof(cells) + sum(sys.getsizeof(pair)
                  + sum(sys.getsizeof(value) for value in pair) for pair in cells)
              + sys.getsizeof((cells, 0)) + sys.getsizeof(0))
    with _surface_validation_lock:
        if (generation != _surface_validation_generation
                or charge + sys.getsizeof(OrderedDict()) > _SURFACE_VALIDATION_MAX_BYTES):
            return areas
        previous = _surface_validation_cache.pop(arguments, None)
        if previous is not None:
            _surface_validation_bytes -= previous[1]
        _surface_validation_cache[arguments] = (cells, charge)
        _surface_validation_bytes += charge
        while (_surface_validation_cache and
               (len(_surface_validation_cache) > _SURFACE_VALIDATION_MAX_ENTRIES
                or _surface_validation_bytes + sys.getsizeof(_surface_validation_cache)
                > _SURFACE_VALIDATION_MAX_BYTES)):
            _, removed = _surface_validation_cache.popitem(last=False)
            _surface_validation_bytes -= removed[1]
        if not _surface_validation_cache:
            _surface_validation_cache.clear()
    return areas


def _validate_surface_cells_from_feature_collection(
    payload_text: str,
    *,
    resolution: int,
    id_field: str,
    area_field: str,
    area_unit: str,
) -> dict[str, float]:
    """Validate one map-ready eligible-surface byte payload exactly once."""

    if not isinstance(payload_text, str) or not payload_text:
        raise ValueError("Eligible-surface GeoJSON text must be non-empty")
    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise ValueError("Eligible-surface artifact is not GeoJSON") from exc
    if not isinstance(payload, Mapping) or payload.get("type") != "FeatureCollection":
        raise ValueError("Eligible-surface artifact must be a FeatureCollection")
    declaration = payload.get("crs")
    if declaration is not None:
        if (
            not isinstance(declaration, Mapping)
            or declaration.get("type") != "name"
            or not isinstance(declaration.get("properties"), Mapping)
        ):
            raise ValueError("Eligible-surface artifact CRS is invalid")
        try:
            declared_crs = CRS.from_user_input(
                declaration["properties"].get("name")
            )
        except Exception as exc:
            raise ValueError("Eligible-surface artifact CRS is invalid") from exc
        if not declared_crs.equals(CRS.from_epsg(4326), ignore_axis_order=True):
            raise ValueError(
                "Eligible-surface artifact must use CRS84/EPSG:4326"
            )
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("Eligible-surface artifact must contain features")
    cell_areas: dict[str, float] = {}
    for index, feature in enumerate(features):
        feature_value = _mapping(feature, f"Eligible-surface feature {index}")
        if feature_value.get("type") != "Feature":
            raise ValueError(f"Eligible-surface feature {index} has invalid type")
        geometry_raw = feature_value.get("geometry")
        if (
            not isinstance(geometry_raw, Mapping)
            or geometry_raw.get("type") not in {"Polygon", "MultiPolygon"}
        ):
            raise ValueError(
                f"Eligible-surface feature {index} has invalid polygon geometry"
            )
        try:
            geometry = shape(geometry_raw)
        except Exception as exc:
            raise ValueError(
                f"Eligible-surface feature {index} geometry cannot be read"
            ) from exc
        bounds = geometry.bounds
        if (
            geometry.is_empty
            or not geometry.is_valid
            or len(bounds) != 4
            or not all(math.isfinite(value) for value in bounds)
            or bounds[0] < -180.0
            or bounds[2] > 180.0
            or bounds[1] < -90.0
            or bounds[3] > 90.0
        ):
            raise ValueError(
                f"Eligible-surface feature {index} geometry is empty, invalid, "
                "or outside CRS84"
            )
        properties = _mapping(
            feature_value.get("properties"),
            f"Eligible-surface feature {index} properties",
        )
        cell_id = properties.get(id_field)
        if not isinstance(cell_id, str) or not h3.is_valid_cell(cell_id):
            raise ValueError(f"Eligible-surface feature {index} has invalid H3 id")
        if h3.get_resolution(cell_id) != resolution:
            raise ValueError(
                f"Eligible-surface feature {index} is not R{resolution}"
            )
        if cell_id in cell_areas:
            raise ValueError("Eligible-surface artifact contains duplicate H3 ids")
        raw_area = properties.get(area_field)
        if isinstance(raw_area, bool) or not isinstance(raw_area, (int, float)):
            raise ValueError(f"Eligible-surface feature {index} has invalid area")
        area = float(raw_area)
        if area_unit == "m2":
            area /= 1_000_000.0
        elif area_unit != "km2":
            raise NotImplementedError(
                f"Unsupported eligible-surface area unit: {area_unit}"
            )
        if not math.isfinite(area) or area <= 0.0:
            raise ValueError(f"Eligible-surface feature {index} area is not positive")
        cell_areas[cell_id] = area
    return cell_areas


def _read_surface_level(
    contract: AnalysisContract,
    resolution: int,
) -> _EligibleSurfaceSnapshot:
    surface = eligible_surface_contract_for_analysis(contract)
    level = eligible_surface_level(contract, resolution)
    provider = str(level.provider)
    path_value = str(level.path)
    if Path(path_value).suffix.lower() not in {".geojson", ".json"}:
        raise NotImplementedError(
            "Workspace area execution supports GeoJSON eligible surfaces"
        )
    domain_input = read_analysis_domain_input(
        contract, 'technology_support', resolution, geometry_use='display')
    payload_bytes = domain_input.geojson_bytes
    actual_sha256 = domain_input.payload_sha256
    if domain_input.upstream_source_sha256 != level.sha256:
        raise ValueError('Eligible-surface upstream contract checksum drifted')
    try:
        payload_text = payload_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Eligible-surface artifact is not UTF-8 GeoJSON") from exc
    cell_areas = _surface_cells_from_feature_collection(
        payload_text,
        resolution=resolution,
        id_field=level.id_field,
        area_field=level.area_field,
        area_unit=level.area_unit,
    )
    if len(cell_areas) != level.expected_cell_count:
        raise ValueError("Eligible-surface cell count drifted")
    total_area = math.fsum(cell_areas.values())
    if not math.isclose(
        total_area,
        level.expected_total_area_km2,
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError("Eligible-surface total area drifted")
    cell_ids_sha256 = _cell_ids_sha256(list(cell_areas))
    if resolution == surface.resolution and (
        cell_ids_sha256 != surface.support_observations.cell_ids_sha256
    ):
        raise ValueError(
            "Eligible-surface source cell digest drifted from support observations"
        )
    snapshot = _EligibleSurfaceSnapshot(
        provider=provider,
        path=path_value,
        sha256=actual_sha256,
        upstream_sha256=domain_input.upstream_source_sha256,
        runtime_revision_sha256=domain_input.runtime_revision_sha256,
        byte_count=len(payload_bytes),
        id_field=level.id_field,
        area_field=level.area_field,
        area_unit=level.area_unit,
        feature_collection_json=payload_text,
        resolution=resolution,
        expected_cell_count=int(level.expected_cell_count),
        expected_total_area_km2=float(level.expected_total_area_km2),
        cell_ids_sha256=cell_ids_sha256,
        cell_areas_km2=tuple(sorted(cell_areas.items())),
    )
    if resolution < surface.resolution:
        source = _read_surface_level(contract, surface.resolution)
        rolled: dict[str, float] = {}
        for cell_id, area_km2 in source.cell_areas_km2:
            parent_id = str(h3.cell_to_parent(cell_id, resolution))
            rolled[parent_id] = rolled.get(parent_id, 0.0) + area_km2
        if set(rolled) != set(cell_areas) or any(
            not math.isclose(
                cell_areas[cell_id],
                area_km2,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
            for cell_id, area_km2 in rolled.items()
        ):
            raise ValueError(
                f"Eligible-surface R{resolution} does not derive from "
                f"R{surface.resolution}"
            )
    return snapshot


def _expected_active_groups(
    contract: AnalysisContract,
    request: WorkspaceAnalysisRequest,
) -> tuple[str, ...]:
    area_contract = contract.area_result
    if area_contract is None:
        raise ValueError(f"{contract.region_id}/{contract.id} has no area result")
    requested = {group.group_id for group in request.groups}
    return tuple(
        group_id
        for group_id in area_contract.applicable_group_ids
        if group_id in requested
    )


def validate_workspace_area_request_from_contract(
    contract: AnalysisContract,
    request: WorkspaceAnalysisRequest,
) -> WorkspaceAnalysisRequest:
    """Constrain an analysis request to the declared area-result capability."""

    validate_workspace_analysis_request_from_contract(contract, request)
    area_contract = contract.area_result
    if area_contract is None:
        raise ValueError(f"{contract.region_id}/{contract.id} has no area result")
    requested_groups = {group.group_id for group in request.groups}
    non_applicable = requested_groups.difference(
        area_contract.applicable_group_ids
    )
    if non_applicable:
        raise ValueError(
            "Workspace area request selects groups outside the declared area "
            f"capability: {sorted(non_applicable)}"
        )
    return request


def _validate_area_engine_result(
    contract: AnalysisContract,
    request: WorkspaceAnalysisRequest,
    result: TechnologyAreaResult,
    snapshot: _EligibleSurfaceSnapshot,
) -> tuple[WorkspaceAreaCellResult, ...]:
    if not isinstance(result, TechnologyAreaResult):
        raise TypeError("area_result must be a TechnologyAreaResult")
    area_contract = contract.area_result
    if area_contract is None:
        raise ValueError(f"{contract.region_id}/{contract.id} has no area result")
    if (
        result.region_id != request.region_id
        or result.analysis_id != request.analysis_id
        or result.technology != area_contract.technology
        or result.resolution != request.target_resolution
        or result.selected_layer_ids != request.selected_layer_ids
        or result.active_group_ids != _expected_active_groups(contract, request)
    ):
        raise ValueError("Workspace area engine result identity drifted")
    if len(result.cells) != len({cell.cell_id for cell in result.cells}):
        raise ValueError("Workspace area engine returned duplicate H3 ids")
    areas = snapshot.area_map()
    if {cell.cell_id for cell in result.cells} != set(areas):
        raise ValueError("Workspace area result does not cover the eligible surface")
    cells: list[WorkspaceAreaCellResult] = []
    for cell in sorted(result.cells, key=lambda item: item.cell_id):
        if not isinstance(cell, AreaCellResult):
            raise TypeError("Workspace area engine cell has an invalid type")
        model_area = float(cell.model_area_km2)
        remaining_area = float(cell.remaining_area_km2)
        potential_pct = float(cell.potential_pct)
        if not all(
            math.isfinite(value)
            for value in (model_area, remaining_area, potential_pct)
        ):
            raise ValueError("Workspace area engine cell contains non-finite values")
        if (
            model_area <= 0.0
            or remaining_area < 0.0
            or remaining_area > model_area
            or potential_pct < 0.0
            or potential_pct > 100.0
        ):
            raise ValueError("Workspace area engine cell violates area bounds")
        expected_pct = remaining_area / model_area * 100.0
        if (
            not math.isclose(
                model_area,
                areas[cell.cell_id],
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or not math.isclose(
                potential_pct,
                expected_pct,
                rel_tol=0.0,
                abs_tol=1e-10,
            )
        ):
            raise ValueError("Workspace area engine cell does not reconcile")
        cells.append(
            WorkspaceAreaCellResult(
                cell_id=cell.cell_id,
                model_area_km2=model_area,
                remaining_area_km2=remaining_area,
                potential_pct=potential_pct,
            )
        )
    model_total = math.fsum(cell.model_area_km2 for cell in cells)
    remaining_total = math.fsum(cell.remaining_area_km2 for cell in cells)
    expected_pct = remaining_total / model_total * 100.0
    if (
        not math.isclose(
            model_total,
            snapshot.expected_total_area_km2,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        or not math.isclose(
            result.model_area_km2, model_total, rel_tol=0.0, abs_tol=1e-9
        )
        or not math.isclose(
            result.remaining_area_km2,
            remaining_total,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        or not math.isclose(
            result.potential_pct, expected_pct, rel_tol=0.0, abs_tol=1e-10
        )
    ):
        raise ValueError("Workspace area engine totals do not reconcile")
    return tuple(cells)


def _result_signature_payload(
    result: WorkspaceAreaExecutionResult,
) -> dict[str, Any]:
    payload = result.as_dict()
    payload.pop("result_signature_sha256")
    return payload


def build_workspace_area_execution_result_from_contract(
    contract: AnalysisContract,
    request: WorkspaceAnalysisRequest,
    area_result: TechnologyAreaResult,
) -> WorkspaceAreaExecutionResult:
    validate_contract(contract)
    validate_workspace_area_request_from_contract(contract, request)
    if contract.area_result is None:
        raise ValueError(f"{contract.region_id}/{contract.id} has no area result")
    surface = eligible_surface_contract_for_analysis(contract)
    snapshot = _read_surface_level(contract, request.target_resolution)
    cells = _validate_area_engine_result(contract, request, area_result, snapshot)
    result = WorkspaceAreaExecutionResult(
        schema_version=WORKSPACE_AREA_RESULT_SCHEMA_VERSION,
        capability_id=f"{request.analysis_id}.area",
        access_scope=request.access_scope,
        region_id=request.region_id,
        analysis_id=request.analysis_id,
        technology=contract.area_result.technology,
        request_signature_sha256=workspace_analysis_request_signature(request),
        request=request,
        eligible_surface_id=surface.id,
        support_domain_id=surface.support_domain_id,
        target_resolution=request.target_resolution,
        surface_artifact_provider=snapshot.provider,
        surface_artifact_path=snapshot.path,
        surface_artifact_sha256=snapshot.sha256,
        surface_upstream_sha256=(snapshot.upstream_sha256 if snapshot.runtime_revision_sha256 else ''),
        surface_runtime_revision_sha256=snapshot.runtime_revision_sha256,
        surface_artifact_bytes=snapshot.byte_count,
        surface_id_field=snapshot.id_field,
        surface_area_field=snapshot.area_field,
        surface_area_unit=snapshot.area_unit,
        surface_feature_collection_json=snapshot.feature_collection_json,
        declared_surface_cell_count=snapshot.expected_cell_count,
        declared_surface_total_area_km2=snapshot.expected_total_area_km2,
        cell_count=len(cells),
        cell_ids_sha256=snapshot.cell_ids_sha256,
        selected_layer_ids=area_result.selected_layer_ids,
        active_group_ids=area_result.active_group_ids,
        model_area_km2=float(area_result.model_area_km2),
        remaining_area_km2=float(area_result.remaining_area_km2),
        potential_pct=float(area_result.potential_pct),
        cells=cells,
        result_signature_sha256="0" * 64,
    )
    result = replace(
        result,
        result_signature_sha256=_canonical_sha256(
            _result_signature_payload(result)
        ),
    )
    validate_workspace_area_execution_result(result)
    return result


_CELL_KEYS = {
    "cell_id",
    "model_area_km2",
    "remaining_area_km2",
    "potential_pct",
}
_RESULT_KEYS = {
    "schema_version",
    "capability_id",
    "access_scope",
    "region_id",
    "analysis_id",
    "technology",
    "request_signature_sha256",
    "request",
    "eligible_surface_id",
    "support_domain_id",
    "target_resolution",
    "surface_artifact_provider",
    "surface_artifact_path",
    "surface_artifact_sha256",
    "surface_artifact_bytes",
    "surface_id_field",
    "surface_area_field",
    "surface_area_unit",
    "surface_feature_collection_json",
    "declared_surface_cell_count",
    "declared_surface_total_area_km2",
    "cell_count",
    "cell_ids_sha256",
    "selected_layer_ids",
    "active_group_ids",
    "model_area_km2",
    "remaining_area_km2",
    "potential_pct",
    "cells",
    "result_signature_sha256",
}


_RESULT_STORAGE_KEYS = {'surface_upstream_sha256', 'surface_runtime_revision_sha256'}


def _parse_cell(value: Any) -> WorkspaceAreaCellResult:
    raw = _mapping(value, "workspace area cell")
    _exact_keys(raw, _CELL_KEYS, "workspace area cell")
    return WorkspaceAreaCellResult(
        cell_id=_exact_text(raw["cell_id"], "workspace area cell id"),
        model_area_km2=_float(
            raw["model_area_km2"], "workspace area model cell area", positive=True
        ),
        remaining_area_km2=_float(
            raw["remaining_area_km2"], "workspace area remaining cell area"
        ),
        potential_pct=_float(
            raw["potential_pct"], "workspace area cell potential"
        ),
    )


def parse_workspace_area_execution_result(
    value: Any,
) -> WorkspaceAreaExecutionResult:
    raw = _mapping(value, "workspace area result")
    _exact_keys(raw, _RESULT_KEYS | (_RESULT_STORAGE_KEYS if _RESULT_STORAGE_KEYS & set(raw) else set()), "workspace area result")
    cells_raw = raw["cells"]
    if not isinstance(cells_raw, list):
        raise TypeError("Workspace area result cells must be a list")
    result = WorkspaceAreaExecutionResult(
        schema_version=_exact_text(raw["schema_version"], "area result schema"),
        capability_id=_exact_text(raw["capability_id"], "area result capability"),
        access_scope=_exact_text(raw["access_scope"], "area result access scope"),
        region_id=_exact_text(raw["region_id"], "area result region"),
        analysis_id=_exact_text(raw["analysis_id"], "area result analysis"),
        technology=_exact_text(raw["technology"], "area result technology"),
        request_signature_sha256=_digest(
            raw["request_signature_sha256"], "area request signature"
        ),
        request=parse_workspace_analysis_request(raw["request"]),
        eligible_surface_id=_exact_text(
            raw["eligible_surface_id"], "eligible surface id"
        ),
        support_domain_id=_exact_text(raw["support_domain_id"], "support domain id"),
        target_resolution=_integer(raw["target_resolution"], "target resolution"),
        surface_artifact_provider=_exact_text(
            raw["surface_artifact_provider"], "surface provider"
        ),
        surface_artifact_path=_exact_text(
            raw["surface_artifact_path"], "surface path"
        ),
        surface_artifact_sha256=_digest(
            raw["surface_artifact_sha256"], "surface artifact sha256"
        ),
        surface_upstream_sha256=(_digest(raw['surface_upstream_sha256'], 'surface upstream sha256') if _RESULT_STORAGE_KEYS & set(raw) else ''),
        surface_runtime_revision_sha256=(_digest(raw['surface_runtime_revision_sha256'], 'surface runtime revision') if _RESULT_STORAGE_KEYS & set(raw) else ''),
        surface_artifact_bytes=_integer(
            raw["surface_artifact_bytes"], "surface artifact bytes", positive=True
        ),
        surface_id_field=_exact_text(
            raw["surface_id_field"], "surface id field"
        ),
        surface_area_field=_exact_text(
            raw["surface_area_field"], "surface area field"
        ),
        surface_area_unit=_exact_text(
            raw["surface_area_unit"], "surface area unit"
        ),
        surface_feature_collection_json=_payload_text(
            raw["surface_feature_collection_json"],
            "surface feature collection JSON",
        ),
        declared_surface_cell_count=_integer(
            raw["declared_surface_cell_count"],
            "declared surface cell count",
            positive=True,
        ),
        declared_surface_total_area_km2=_float(
            raw["declared_surface_total_area_km2"],
            "declared surface total area",
            positive=True,
        ),
        cell_count=_integer(raw["cell_count"], "area cell count", positive=True),
        cell_ids_sha256=_digest(raw["cell_ids_sha256"], "area cell-id digest"),
        selected_layer_ids=_string_tuple(
            raw["selected_layer_ids"], "selected area layers"
        ),
        active_group_ids=_string_tuple(raw["active_group_ids"], "active area groups"),
        model_area_km2=_float(raw["model_area_km2"], "model area", positive=True),
        remaining_area_km2=_float(
            raw["remaining_area_km2"], "remaining area"
        ),
        potential_pct=_float(raw["potential_pct"], "area potential"),
        cells=tuple(_parse_cell(item) for item in cells_raw),
        result_signature_sha256=_digest(
            raw["result_signature_sha256"], "area result signature"
        ),
    )
    validate_workspace_area_execution_result(result)
    return result


def validate_workspace_area_execution_result(
    result: WorkspaceAreaExecutionResult,
) -> None:
    if not isinstance(result, WorkspaceAreaExecutionResult):
        raise TypeError("result must be a WorkspaceAreaExecutionResult")
    if result.schema_version != WORKSPACE_AREA_RESULT_SCHEMA_VERSION:
        raise NotImplementedError(
            f"Unsupported workspace area result schema: {result.schema_version}"
        )
    request = parse_workspace_analysis_request(result.request.as_dict())
    scope_parts = request.access_scope.split(":", 1)
    if (
        len(scope_parts) != 2
        or scope_parts[0] not in {"product", "review"}
        or scope_parts[1] != request.region_id
    ):
        raise ValueError("Workspace area request access scope is invalid")
    for value, label, positive in (
        (result.declared_surface_total_area_km2, "declared surface area", True),
        (result.model_area_km2, "model area", True),
        (result.remaining_area_km2, "remaining area", False),
        (result.potential_pct, "potential percentage", False),
    ):
        _float(value, label, positive=positive)
    for value, label, positive in (
        (result.target_resolution, "target resolution", False),
        (result.surface_artifact_bytes, "surface artifact bytes", True),
        (result.declared_surface_cell_count, "declared surface cells", True),
        (result.cell_count, "area cells", True),
    ):
        _integer(value, label, positive=positive)
    if not isinstance(result.cells, tuple) or any(
        not isinstance(cell, WorkspaceAreaCellResult) for cell in result.cells
    ):
        raise TypeError("Workspace area result cells must be an immutable tuple")
    if (
        result.capability_id != f"{request.analysis_id}.area"
        or result.access_scope != request.access_scope
        or result.region_id != request.region_id
        or result.analysis_id != request.analysis_id
        or result.target_resolution != request.target_resolution
        or result.request_signature_sha256
        != workspace_analysis_request_signature(request)
        or result.selected_layer_ids != request.selected_layer_ids
        or len(result.active_group_ids) != len(request.groups)
        or set(result.active_group_ids)
        != {group.group_id for group in request.groups}
    ):
        raise ValueError("Workspace area result identity drifted from request")
    if result.target_resolution < 0 or result.target_resolution > 15:
        raise ValueError("Workspace area target resolution is invalid")
    if result.cell_count != result.declared_surface_cell_count:
        raise ValueError("Workspace area cell count drifted from declaration")
    if len(result.cells) != result.cell_count:
        raise ValueError("Workspace area result cell count is invalid")
    cell_ids = tuple(cell.cell_id for cell in result.cells)
    if cell_ids != tuple(sorted(cell_ids)) or len(cell_ids) != len(set(cell_ids)):
        raise ValueError("Workspace area result H3 ids must be sorted and unique")
    if any(
        not h3.is_valid_cell(cell_id)
        or h3.get_resolution(cell_id) != result.target_resolution
        for cell_id in cell_ids
    ):
        raise ValueError("Workspace area result contains invalid target H3 ids")
    if _cell_ids_sha256(list(cell_ids)) != result.cell_ids_sha256:
        raise ValueError("Workspace area result H3 digest drifted")
    for cell in result.cells:
        _float(cell.model_area_km2, "cell model area", positive=True)
        _float(cell.remaining_area_km2, "cell remaining area")
        _float(cell.potential_pct, "cell potential percentage")
        if (
            not all(
                math.isfinite(value)
                for value in (
                    cell.model_area_km2,
                    cell.remaining_area_km2,
                    cell.potential_pct,
                )
            )
            or cell.model_area_km2 <= 0.0
            or cell.remaining_area_km2 < 0.0
            or cell.remaining_area_km2 > cell.model_area_km2
            or cell.potential_pct < 0.0
            or cell.potential_pct > 100.0
            or not math.isclose(
                cell.potential_pct,
                cell.remaining_area_km2 / cell.model_area_km2 * 100.0,
                rel_tol=0.0,
                abs_tol=1e-10,
            )
        ):
            raise ValueError("Workspace area result cell does not reconcile")
    model_total = math.fsum(cell.model_area_km2 for cell in result.cells)
    remaining_total = math.fsum(
        cell.remaining_area_km2 for cell in result.cells
    )
    expected_pct = remaining_total / model_total * 100.0
    if (
        not math.isclose(
            result.model_area_km2, model_total, rel_tol=0.0, abs_tol=1e-9
        )
        or not math.isclose(
            result.declared_surface_total_area_km2,
            model_total,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        or not math.isclose(
            result.remaining_area_km2,
            remaining_total,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        or not math.isclose(
            result.potential_pct, expected_pct, rel_tol=0.0, abs_tol=1e-10
        )
    ):
        raise ValueError("Workspace area result totals do not reconcile")
    _digest(result.surface_artifact_sha256, "surface artifact sha256")
    if result.surface_upstream_sha256 or result.surface_runtime_revision_sha256:
        _digest(result.surface_upstream_sha256, "surface upstream sha256")
        _digest(result.surface_runtime_revision_sha256, "surface runtime revision")
    if result.surface_artifact_bytes <= 0:
        raise ValueError("Workspace area surface artifact bytes must be positive")
    _exact_text(result.surface_id_field, "surface id field")
    _exact_text(result.surface_area_field, "surface area field")
    _exact_text(result.surface_area_unit, "surface area unit")
    surface_bytes = _payload_text(
        result.surface_feature_collection_json,
        "surface feature collection JSON",
    ).encode("utf-8")
    if (
        len(surface_bytes) != result.surface_artifact_bytes
        or hashlib.sha256(surface_bytes).hexdigest()
        != result.surface_artifact_sha256
    ):
        raise ValueError(
            "Workspace area embedded surface bytes drifted from artifact identity"
        )
    embedded_areas = _surface_cells_from_feature_collection(
        result.surface_feature_collection_json,
        resolution=result.target_resolution,
        id_field=result.surface_id_field,
        area_field=result.surface_area_field,
        area_unit=result.surface_area_unit,
    )
    if (
        len(embedded_areas) != result.declared_surface_cell_count
        or _cell_ids_sha256(list(embedded_areas)) != result.cell_ids_sha256
        or set(embedded_areas) != set(cell_ids)
        or any(
            not math.isclose(
                embedded_areas[cell.cell_id],
                cell.model_area_km2,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            for cell in result.cells
        )
    ):
        raise ValueError(
            "Workspace area embedded surface does not reconcile with result cells"
        )
    expected_signature = _canonical_sha256(_result_signature_payload(result))
    if result.result_signature_sha256 != expected_signature:
        raise ValueError("Workspace area result signature does not match")


def validate_workspace_area_execution_result_from_contract(
    contract: AnalysisContract,
    result: WorkspaceAreaExecutionResult,
) -> None:
    validate_workspace_area_execution_result(result)
    validate_workspace_area_request_from_contract(contract, result.request)
    surface = eligible_surface_contract_for_analysis(contract)
    snapshot = _read_surface_level(contract, result.target_resolution)
    if contract.area_result is None:
        raise ValueError(f"{contract.region_id}/{contract.id} has no area result")
    if (
        result.technology != contract.area_result.technology
        or result.eligible_surface_id != surface.id
        or result.support_domain_id != surface.support_domain_id
        or result.surface_artifact_provider != snapshot.provider
        or result.surface_artifact_path != snapshot.path
        or result.surface_artifact_sha256 != snapshot.sha256
        or (result.surface_upstream_sha256 or result.surface_artifact_sha256) != snapshot.upstream_sha256
        or result.surface_runtime_revision_sha256 != snapshot.runtime_revision_sha256
        or result.surface_artifact_bytes != snapshot.byte_count
        or result.surface_id_field != snapshot.id_field
        or result.surface_area_field != snapshot.area_field
        or result.surface_area_unit != snapshot.area_unit
        or result.surface_feature_collection_json
        != snapshot.feature_collection_json
        or result.declared_surface_cell_count != snapshot.expected_cell_count
        or not math.isclose(
            result.declared_surface_total_area_km2,
            snapshot.expected_total_area_km2,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        or result.cell_ids_sha256 != snapshot.cell_ids_sha256
        or result.active_group_ids
        != _expected_active_groups(contract, result.request)
    ):
        raise ValueError("Workspace area result drifted from its current contract")
    declared_areas = snapshot.area_map()
    if {cell.cell_id for cell in result.cells} != set(declared_areas):
        raise ValueError("Workspace area cells drifted from the declared artifact")
    if any(
        not math.isclose(
            cell.model_area_km2,
            declared_areas[cell.cell_id],
            rel_tol=0.0,
            abs_tol=1e-12,
        )
        for cell in result.cells
    ):
        raise ValueError("Workspace area cell model areas drifted from artifact")


def run_catalog_workspace_area_request(
    request: WorkspaceAnalysisRequest,
) -> WorkspaceAreaExecutionResult:
    if not isinstance(request, WorkspaceAnalysisRequest):
        raise TypeError("request must be a WorkspaceAnalysisRequest")
    capability_id = f"{request.analysis_id}.area"
    contract = load_analysis(request.region_id, request.analysis_id)
    validate_workspace_area_request_from_contract(contract, request)
    authorize_catalog_workspace_analysis_request(
        request,
        required_capability_id=capability_id,
    )
    area_result = run_area_analysis(
        region=request.region_id,
        analysis=request.analysis_id,
        layers=request.selected_layer_ids,
        parameters=request.engine_parameters(),
        target_resolution=request.target_resolution,
    )
    return build_workspace_area_execution_result_from_contract(
        contract,
        request,
        area_result,
    )



@dataclass(frozen=True)
class WorkspaceNativeAreaExecution:
    """Prepared native cells retain engine order, separate from sorted wire cells."""

    request: WorkspaceAnalysisRequest
    runtime_snapshot_token: str
    native_result: TechnologyAreaResult
    workspace_result: WorkspaceAreaExecutionResult
    preparation_sha256: str


def _native_preparation_sha256(prepared: WorkspaceNativeAreaExecution) -> str:
    return _canonical_sha256({
        "request": prepared.request.as_dict(),
        "runtime_snapshot_token": prepared.runtime_snapshot_token,
        "native_result": asdict(prepared.native_result),
        "workspace_result_signature_sha256": prepared.workspace_result.result_signature_sha256,
    })


def native_workspace_area_request(
    request: WorkspaceAnalysisRequest,
) -> WorkspaceAnalysisRequest:
    """Authorize the actual target before selecting its declared native input."""

    if not isinstance(request, WorkspaceAnalysisRequest):
        raise TypeError("request must be a WorkspaceAnalysisRequest")
    contract = load_analysis(request.region_id, request.analysis_id)
    validate_workspace_area_request_from_contract(contract, request)
    authorize_catalog_workspace_analysis_request(
        request, required_capability_id=f"{request.analysis_id}.area",
    )
    surface = eligible_surface_contract_for_analysis(contract)
    native_request = retarget_workspace_analysis_request_from_contract(
        contract, request, int(surface.resolution),
    )
    validate_workspace_area_request_from_contract(contract, native_request)
    authorize_catalog_workspace_analysis_request(
        native_request, required_capability_id=f"{native_request.analysis_id}.area",
    )
    return native_request


def prepare_catalog_workspace_native_area(
    request: WorkspaceAnalysisRequest,
    runtime_snapshot_token: str,
    *,
    force_recompute: bool = False,
) -> WorkspaceNativeAreaExecution:
    """Calculate one authorized native request; the caller supplies its live token."""

    token = _digest(runtime_snapshot_token, "Native area runtime snapshot token")
    native_request = native_workspace_area_request(request)
    contract = load_analysis(native_request.region_id, native_request.analysis_id)
    from . import native_area_store
    stored = native_area_store.prepare(contract, native_request)
    native_result = (native_area_store.read(stored[0], native_request, stored[1])
                     if stored and not force_recompute else None)
    cache_miss = native_result is None
    if cache_miss:
        from . import feasibility_store
        with feasibility_store.request_scope(contract, native_request):
            native_result = run_area_analysis(
                region=native_request.region_id,
                analysis=native_request.analysis_id,
                layers=native_request.selected_layer_ids,
                parameters=native_request.engine_parameters(),
                target_resolution=native_request.target_resolution,
            )
    workspace_result = build_workspace_area_execution_result_from_contract(
        contract, native_request, native_result,
    )
    if stored and cache_miss:
        native_area_store.write(stored[0], native_request, stored[1], native_result)
    prepared = WorkspaceNativeAreaExecution(
        request=native_request,
        runtime_snapshot_token=token,
        native_result=native_result,
        workspace_result=workspace_result,
        preparation_sha256="0" * 64,
    )
    return replace(prepared, preparation_sha256=_native_preparation_sha256(prepared))


def derive_catalog_workspace_area_request(
    request: WorkspaceAnalysisRequest,
    prepared: WorkspaceNativeAreaExecution,
    runtime_snapshot_token: str,
) -> WorkspaceAreaExecutionResult:
    """Validate current identity and derive a target without new native geometry."""

    token = _digest(runtime_snapshot_token, "Native area runtime snapshot token")
    native_request = native_workspace_area_request(request)
    if not isinstance(prepared, WorkspaceNativeAreaExecution):
        raise TypeError("prepared must be a WorkspaceNativeAreaExecution")
    if (
        prepared.request != native_request
        or prepared.runtime_snapshot_token != token
        or prepared.workspace_result.request != native_request
        or prepared.preparation_sha256 != _native_preparation_sha256(prepared)
    ):
        raise ValueError("Prepared native area escaped its request or runtime")
    contract = load_analysis(request.region_id, request.analysis_id)
    validate_workspace_area_execution_result_from_contract(
        contract, prepared.workspace_result,
    )
    _reconcile_native_area_preparation(contract, prepared)
    if request == native_request:
        return prepared.workspace_result
    area_result = rollup_native_area_result(
        contract, prepared.native_result, request.target_resolution,
    )
    return build_workspace_area_execution_result_from_contract(
        contract, request, area_result,
    )


def _reconcile_native_area_preparation(
    contract: AnalysisContract,
    prepared: WorkspaceNativeAreaExecution,
) -> None:
    """Bind the ordered raw cells to independently validated signed authority.

    The preparation digest is an integrity check, not an authority boundary:
    a reconstructed dataclass must also match native membership/order and the
    exact values already present in the signed workspace result.
    """

    raw = prepared.native_result
    signed = prepared.workspace_result
    if not isinstance(raw, TechnologyAreaResult) or not isinstance(raw.cells, tuple):
        raise TypeError("Prepared native area must contain immutable engine cells")
    if (
        raw.region_id != signed.region_id
        or raw.analysis_id != signed.analysis_id
        or raw.technology != signed.technology
        or raw.resolution != signed.target_resolution
        or raw.selected_layer_ids != signed.selected_layer_ids
        or raw.active_group_ids != signed.active_group_ids
        or any(
            float(getattr(raw, name)).hex() != float(getattr(signed, name)).hex()
            for name in ("model_area_km2", "remaining_area_km2", "potential_pct")
        )
    ):
        raise ValueError("Prepared native metadata differs from its signed result")
    expected_order = tuple(area_engine.resolve_eligible_surface_cell_areas_km2(
        contract, raw.resolution,
    ))
    if (
        any(not isinstance(cell, AreaCellResult) for cell in raw.cells)
        or tuple(cell.cell_id for cell in raw.cells) != expected_order
        or len(raw.cells) != len(signed.cells)
    ):
        raise ValueError("Prepared native cells differ from current native membership/order")
    for source, target in zip(sorted(raw.cells, key=lambda cell: cell.cell_id), signed.cells):
        if source.cell_id != target.cell_id or any(
            float(getattr(source, name)).hex() != float(getattr(target, name)).hex()
            for name in ("model_area_km2", "remaining_area_km2", "potential_pct")
        ):
            raise ValueError("Prepared native cell differs from its signed result")


def replay_catalog_workspace_area_result(
    result: WorkspaceAreaExecutionResult,
) -> WorkspaceAreaExecutionResult:
    parsed = parse_workspace_area_execution_result(result.as_dict())
    replayed = run_catalog_workspace_area_request(parsed.request)
    if replayed != parsed:
        raise ValueError("Workspace area result does not match canonical replay")
    return replayed


__all__ = [
    "WORKSPACE_AREA_RESULT_SCHEMA_VERSION",
    "WorkspaceNativeAreaExecution",
    "native_workspace_area_request",
    "prepare_catalog_workspace_native_area",
    "derive_catalog_workspace_area_request",
    "WorkspaceAreaCellResult",
    "WorkspaceAreaExecutionResult",
    "build_workspace_area_execution_result_from_contract",
    "parse_workspace_area_execution_result",
    "replay_catalog_workspace_area_result",
    "run_catalog_workspace_area_request",
    "validate_workspace_area_execution_result",
    "validate_workspace_area_execution_result_from_contract",
    "validate_workspace_area_request_from_contract",
    "workspace_analysis_request_signature",
]
