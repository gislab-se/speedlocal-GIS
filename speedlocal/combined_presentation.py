from __future__ import annotations

from .allocation import known_sum

from dataclasses import dataclass, replace
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping

import h3
from pyproj import CRS
from shapely.geometry import Polygon, shape

from .combined_result import (
    CombinedResult,
    parse_combined_result,
    validate_combined_result,
)
from .workspace_area import (
    WorkspaceAreaExecutionResult,
    parse_workspace_area_execution_result,
)


COMBINED_PRESENTATION_SCHEMA_VERSION = "1.0"
COMBINED_PRESENTATION_CAPABILITY_ID = "workspace.combined_result.presentation"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9_.:-]*$")
_VALUE_TYPES = {"string", "integer", "number", "boolean"}
_UNITS = {None, "count", "km2", "percent", "ratio", "twh"}
_ALLOCATION_STATES = {"blocked_missing_policy", "executed"}
_CONTEXT_STATUSES = {"complete", "partial", "not_assessed"}
_SOCIAL_DATA_STATUSES = {"observed", "synthetic", "partial", "not_assessed"}
_FLOAT_TOLERANCE = 1e-9
_GEOMETRY_AREA_ABSOLUTE_TOLERANCE = 1e-16
_GEOMETRY_AREA_RELATIVE_TOLERANCE = 1e-10
# Eligible surfaces are clipped in their declared projected CRS and then
# transformed to CRS84. Curved projection edges no longer coincide exactly
# with H3's straight CRS84 chords; keep that bounded representation drift
# separate from the much tighter intrinsic polygon-area tolerance.
_GEOMETRY_CELL_AREA_RELATIVE_TOLERANCE = 5e-5
_GEOMETRY_COORDINATE_TOLERANCE = 1e-12


JsonScalar = str | float | int | bool | None


@dataclass(frozen=True)
class CombinedPresentationAreaBinding:
    technology_id: str
    resolution: int
    request_signature_sha256: str
    result_signature_sha256: str
    support_domain_id: str
    surface_artifact_sha256: str
    cell_ids_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "technology_id": self.technology_id,
            "resolution": self.resolution,
            "request_signature_sha256": self.request_signature_sha256,
            "result_signature_sha256": self.result_signature_sha256,
            "support_domain_id": self.support_domain_id,
            "surface_artifact_sha256": self.surface_artifact_sha256,
            "cell_ids_sha256": self.cell_ids_sha256,
        }


@dataclass(frozen=True)
class CombinedPresentationField:
    field_id: str
    value_type: str
    unit: str | None
    nullable: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "value_type": self.value_type,
            "unit": self.unit,
            "nullable": self.nullable,
        }


@dataclass(frozen=True)
class CombinedPresentationMapLayer:
    layer_id: str
    resolution: int
    allocation_state: str
    support_domain_id: str
    geometry_source_sha256: str
    cell_ids_sha256: str
    feature_count: int
    hover_fields: tuple[CombinedPresentationField, ...]
    feature_collection_json: str
    feature_collection_sha256: str
    layer_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "resolution": self.resolution,
            "allocation_state": self.allocation_state,
            "support_domain_id": self.support_domain_id,
            "geometry_source_sha256": self.geometry_source_sha256,
            "cell_ids_sha256": self.cell_ids_sha256,
            "feature_count": self.feature_count,
            "hover_fields": [field.as_dict() for field in self.hover_fields],
            "feature_collection_json": self.feature_collection_json,
            "feature_collection_sha256": self.feature_collection_sha256,
            "layer_signature_sha256": self.layer_signature_sha256,
        }


@dataclass(frozen=True)
class CombinedPresentationTable:
    table_id: str
    kind: str
    resolution: int | None
    fields: tuple[CombinedPresentationField, ...]
    rows: tuple[tuple[JsonScalar, ...], ...]
    table_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "table_id": self.table_id,
            "kind": self.kind,
            "resolution": self.resolution,
            "fields": [field.as_dict() for field in self.fields],
            "rows": [list(row) for row in self.rows],
            "table_signature_sha256": self.table_signature_sha256,
        }


@dataclass(frozen=True)
class CombinedPresentationMetric:
    metric_id: str
    technology_id: str
    field_id: str
    value: float
    unit: str
    metric_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "technology_id": self.technology_id,
            "field_id": self.field_id,
            "value": self.value,
            "unit": self.unit,
            "metric_signature_sha256": self.metric_signature_sha256,
        }


@dataclass(frozen=True)
class CombinedResultPresentation:
    schema_version: str
    capability_id: str
    access_scope: str
    region_id: str
    finalization_resolution: int
    rollup_resolutions: tuple[int, ...]
    technology_order: tuple[str, ...]
    allocation_state: str
    allocation_detail: str
    combined_request_signature_sha256: str
    combined_result_signature_sha256: str
    technology_context_result_signature_sha256: str
    scenario_result_signature_sha256: str
    rooftop_result_signature_sha256: str
    social_acceptance_result_signature_sha256: str
    allocation_policy_signature_sha256: str | None
    area_result_bindings: tuple[CombinedPresentationAreaBinding, ...]
    map_layers: tuple[CombinedPresentationMapLayer, ...]
    tables: tuple[CombinedPresentationTable, ...]
    metrics: tuple[CombinedPresentationMetric, ...]
    presentation_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capability_id": self.capability_id,
            "access_scope": self.access_scope,
            "region_id": self.region_id,
            "finalization_resolution": self.finalization_resolution,
            "rollup_resolutions": list(self.rollup_resolutions),
            "technology_order": list(self.technology_order),
            "allocation_state": self.allocation_state,
            "allocation_detail": self.allocation_detail,
            "combined_request_signature_sha256": (
                self.combined_request_signature_sha256
            ),
            "combined_result_signature_sha256": (
                self.combined_result_signature_sha256
            ),
            "technology_context_result_signature_sha256": (
                self.technology_context_result_signature_sha256
            ),
            "scenario_result_signature_sha256": (
                self.scenario_result_signature_sha256
            ),
            "rooftop_result_signature_sha256": (
                self.rooftop_result_signature_sha256
            ),
            "social_acceptance_result_signature_sha256": (
                self.social_acceptance_result_signature_sha256
            ),
            "allocation_policy_signature_sha256": (
                self.allocation_policy_signature_sha256
            ),
            "area_result_bindings": [
                binding.as_dict() for binding in self.area_result_bindings
            ],
            "map_layers": [layer.as_dict() for layer in self.map_layers],
            "tables": [table.as_dict() for table in self.tables],
            "metrics": [metric.as_dict() for metric in self.metrics],
            "presentation_signature_sha256": (
                self.presentation_signature_sha256
            ),
        }


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


def _bytes_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _id_digest(values: Iterable[str]) -> str:
    return hashlib.sha256(
        "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    ).hexdigest()


def _exact_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be exact non-empty text")
    return value


def _identifier(value: Any, label: str) -> str:
    text = _exact_text(value, label)
    if _IDENTIFIER.fullmatch(text) is None:
        raise ValueError(f"{label} must be a lowercase identifier")
    return text


def _digest(value: Any, label: str) -> str:
    text = _exact_text(value, label)
    if _SHA256.fullmatch(text) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _optional_digest(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _digest(value, label)


def _resolution(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 15:
        raise ValueError(f"{label} must be an H3 resolution")
    return value


def _integer(value: Any, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < (1 if positive else 0):
        raise ValueError(f"{label} is outside its range")
    return value


def _number(value: Any, label: str, *, non_negative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric) or (non_negative and numeric < 0.0):
        raise ValueError(f"{label} must be finite and in range")
    return numeric


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields do not match schema 1.0")


def _json_scalar(value: Any, label: str) -> JsonScalar:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError(f"{label} must be a finite JSON scalar")


def _close(left: float, right: float, *, tolerance: float = _FLOAT_TOLERANCE) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)


def _validate_feature_collection_crs(value: Any, label: str) -> None:
    if value is None:
        return
    declaration = _mapping(value, f"{label} CRS")
    if (
        declaration.get("type") != "name"
        or not isinstance(declaration.get("properties"), Mapping)
    ):
        raise ValueError(f"{label} CRS is invalid")
    try:
        declared = CRS.from_user_input(declaration["properties"].get("name"))
    except Exception as exc:
        raise ValueError(f"{label} CRS is invalid") from exc
    if not declared.equals(CRS.from_epsg(4326), ignore_axis_order=True):
        raise ValueError(f"{label} must use CRS84/EPSG:4326")


def _validate_feature_collection_bbox(
    value: Any,
    label: str,
) -> tuple[float, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) not in {4, 6}:
        raise ValueError(f"{label} bbox must contain four or six coordinates")
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        for item in value
    ):
        raise ValueError(f"{label} bbox coordinates must be finite numbers")
    bbox = tuple(float(item) for item in value)
    west, south = bbox[0], bbox[1]
    east, north = bbox[len(bbox) // 2], bbox[len(bbox) // 2 + 1]
    if (
        not -180.0 <= west <= 180.0
        or not -180.0 <= east <= 180.0
        or not -90.0 <= south <= 90.0
        or not -90.0 <= north <= 90.0
        or south > north
        or (len(bbox) == 6 and bbox[2] > bbox[5])
    ):
        raise ValueError(f"{label} bbox is invalid for CRS84")
    return bbox


def _geometry_positions(
    value: Any,
    label: str,
) -> tuple[tuple[float, ...], ...]:
    positions: list[tuple[float, ...]] = []

    def visit(node: Any) -> None:
        if not isinstance(node, list):
            raise ValueError(f"{label} coordinates are invalid")
        if node and all(
            not isinstance(item, bool) and isinstance(item, (int, float))
            for item in node
        ):
            if len(node) not in {2, 3} or not all(
                math.isfinite(float(item)) for item in node
            ):
                raise ValueError(f"{label} position is invalid")
            positions.append(tuple(float(item) for item in node))
            return
        for child in node:
            visit(child)

    visit(value)
    if not positions or len({len(position) for position in positions}) != 1:
        raise ValueError(f"{label} coordinate dimensions are invalid")
    return tuple(positions)


def _validate_bbox_coverage(
    bbox: tuple[float, ...] | None,
    positions: tuple[tuple[float, ...], ...],
    label: str,
) -> None:
    if bbox is None:
        return
    dimensions = {len(position) for position in positions}
    if len(dimensions) != 1:
        raise ValueError(f"{label} bbox geometry dimensions are inconsistent")
    dimension = next(iter(dimensions))
    if len(bbox) != dimension * 2:
        raise ValueError(f"{label} bbox dimension does not match its geometry")
    west, south = bbox[0], bbox[1]
    east, north = bbox[dimension], bbox[dimension + 1]
    tolerance = _GEOMETRY_COORDINATE_TOLERANCE
    if any(
        position[1] < south - tolerance
        or position[1] > north + tolerance
        or (
            west <= east
            and (
                position[0] < west - tolerance
                or position[0] > east + tolerance
            )
        )
        or (
            west > east
            and not (
                position[0] >= west - tolerance
                or position[0] <= east + tolerance
            )
        )
        for position in positions
    ):
        raise ValueError(f"{label} bbox does not cover its geometry")
    if dimension == 3 and any(
        position[2] < bbox[2] - tolerance
        or position[2] > bbox[5] + tolerance
        for position in positions
    ):
        raise ValueError(f"{label} bbox does not cover its geometry elevation")


def _validate_feature_collection_keys(
    value: Mapping[str, Any],
    label: str,
) -> None:
    required = {"type", "features"}
    allowed = {*required, "bbox", "crs", "name"}
    if not required.issubset(value) or set(value).difference(allowed):
        raise ValueError(f"{label} fields do not match GeoJSON")
    if "name" in value and (
        not isinstance(value["name"], str) or not value["name"].strip()
    ):
        raise ValueError(f"{label} name must be a non-empty string")
    _validate_feature_collection_crs(value.get("crs"), label)
    _validate_feature_collection_bbox(value.get("bbox"), label)


def _field(
    field_id: str,
    value_type: str,
    unit: str | None = None,
    *,
    nullable: bool = False,
) -> CombinedPresentationField:
    return CombinedPresentationField(field_id, value_type, unit, nullable)


def _summary_fields(*, capacity=False) -> tuple[CombinedPresentationField, ...]:
    return (
        _field("technology_id", "string"),
        _field("allocation_state", "string"),
        _field("gross_energy_twh", "number", "twh", nullable=capacity),
        _field("gross_area_need_km2", "number", "km2"),
        _field("rooftop_contribution_twh", "number", "twh"),
        _field("ground_energy_twh", "number", "twh", nullable=capacity),
        _field("ground_area_need_km2", "number", "km2"),
        _field("potential_area_km2", "number", "km2"),
        _field(
            "acceptance_adjusted_potential_area_km2",
            "number",
            "km2",
        ),
        _field("selected_area_km2", "number", "km2", nullable=True),
        _field("selected_twh", "number", "twh", nullable=True),
        _field(
            "inside_potential_area_km2",
            "number",
            "km2",
            nullable=True,
        ),
        _field(
            "outside_potential_area_km2",
            "number",
            "km2",
            nullable=True,
        ),
        _field("unmet_area_km2", "number", "km2", nullable=True),
    )


def _detail_fields(
    technology_order: tuple[str, ...],
) -> tuple[CombinedPresentationField, ...]:
    fields: list[CombinedPresentationField] = [
        _field("cell_id", "string"),
        _field("resolution", "integer"),
        _field("model_area_km2", "number", "km2"),
        _field("context_status", "string"),
        _field("social_data_status", "string"),
        _field("social_acceptance_value", "number", "ratio", nullable=True),
        _field("allocation_state", "string"),
        _field("allocation_executed", "boolean"),
    ]
    for technology_id in technology_order:
        fields.extend(
            (
                _field(
                    f"{technology_id}.potential_area_km2",
                    "number",
                    "km2",
                ),
                _field(
                    f"{technology_id}.potential_pct",
                    "number",
                    "percent",
                ),
                _field(
                    f"{technology_id}.acceptance_adjusted_potential_area_km2",
                    "number",
                    "km2",
                ),
                _field(
                    f"{technology_id}.allocation_priority_score",
                    "number",
                    "ratio",
                    nullable=True,
                ),
                _field(
                    f"{technology_id}.allocation_eligible",
                    "boolean",
                    nullable=True,
                ),
                _field(
                    f"{technology_id}.allocated_area_km2",
                    "number",
                    "km2",
                    nullable=True,
                ),
                _field(
                    f"{technology_id}.allocated_twh",
                    "number",
                    "twh",
                    nullable=True,
                ),
            )
        )
    return tuple(fields)


def _summary_row(result: CombinedResult, technology_id: str) -> tuple[JsonScalar, ...]:
    summary = next(
        item
        for item in result.technology_summaries
        if item.technology_id == technology_id
    )
    return (
        technology_id,
        result.allocation_state,
        summary.gross_energy_twh,
        summary.gross_area_need_km2,
        summary.rooftop_contribution_twh,
        summary.ground_energy_twh,
        summary.ground_area_need_km2,
        summary.potential_area_km2,
        summary.acceptance_adjusted_potential_area_km2,
        summary.selected_area_km2,
        summary.selected_twh,
        summary.inside_potential_area_km2,
        summary.outside_potential_area_km2,
        summary.unmet_area_km2,
    )


def _detail_row(
    result: CombinedResult,
    cell: Any,
) -> tuple[JsonScalar, ...]:
    technologies = {
        item.technology_id: item for item in cell.technologies
    }
    first = technologies[result.technology_order[0]]
    values: list[JsonScalar] = [
        cell.cell_id,
        cell.resolution,
        first.model_area_km2,
        cell.context_status,
        cell.social_data_status,
        cell.social_acceptance_value,
        result.allocation_state,
        result.allocation_state == "executed",
    ]
    for technology_id in result.technology_order:
        technology = technologies[technology_id]
        values.extend(
            (
                technology.potential_area_km2,
                technology.potential_pct,
                technology.acceptance_adjusted_potential_area_km2,
                technology.allocation_priority_score,
                technology.allocation_eligible,
                technology.allocated_area_km2,
                technology.allocated_twh,
            )
        )
    return tuple(values)


def _layer_signature_payload(
    layer: CombinedPresentationMapLayer,
) -> dict[str, Any]:
    value = layer.as_dict()
    value.pop("layer_signature_sha256")
    return value


def _table_signature_payload(
    table: CombinedPresentationTable,
) -> dict[str, Any]:
    value = table.as_dict()
    value.pop("table_signature_sha256")
    return value


def _metric_signature_payload(
    metric: CombinedPresentationMetric,
) -> dict[str, Any]:
    value = metric.as_dict()
    value.pop("metric_signature_sha256")
    return value


def _presentation_signature_payload(
    presentation: CombinedResultPresentation,
) -> dict[str, Any]:
    value = presentation.as_dict()
    value.pop("presentation_signature_sha256")
    return value


def _signed_table(
    *,
    table_id: str,
    kind: str,
    resolution: int | None,
    fields: tuple[CombinedPresentationField, ...],
    rows: tuple[tuple[JsonScalar, ...], ...],
) -> CombinedPresentationTable:
    table = CombinedPresentationTable(
        table_id=table_id,
        kind=kind,
        resolution=resolution,
        fields=fields,
        rows=rows,
        table_signature_sha256="0" * 64,
    )
    return replace(
        table,
        table_signature_sha256=_canonical_sha256(
            _table_signature_payload(table)
        ),
    )


_SUMMARY_METRIC_FIELDS = (
    "gross_energy_twh",
    "gross_area_need_km2",
    "rooftop_contribution_twh",
    "ground_energy_twh",
    "ground_area_need_km2",
    "potential_area_km2",
    "acceptance_adjusted_potential_area_km2",
    "selected_area_km2",
    "selected_twh",
    "inside_potential_area_km2",
    "outside_potential_area_km2",
    "unmet_area_km2",
)


def _metrics_from_summary(
    table: CombinedPresentationTable,
) -> tuple[CombinedPresentationMetric, ...]:
    field_index = {
        field.field_id: index for index, field in enumerate(table.fields)
    }
    metrics: list[CombinedPresentationMetric] = []
    for row in table.rows:
        technology_id = str(row[field_index["technology_id"]])
        for field_id in _SUMMARY_METRIC_FIELDS:
            value = row[field_index[field_id]]
            if value is None:
                continue
            unit = table.fields[field_index[field_id]].unit
            if unit is None:
                raise ValueError("Combined summary metric lacks a unit")
            metric = CombinedPresentationMetric(
                metric_id=f"{technology_id}.{field_id}",
                technology_id=technology_id,
                field_id=field_id,
                value=float(value),
                unit=unit,
                metric_signature_sha256="0" * 64,
            )
            metrics.append(
                replace(
                    metric,
                    metric_signature_sha256=_canonical_sha256(
                        _metric_signature_payload(metric)
                    ),
                )
            )
    return tuple(metrics)


def _strict_inputs(
    combined_result: CombinedResult,
    area_results: tuple[WorkspaceAreaExecutionResult, ...],
) -> tuple[CombinedResult, tuple[WorkspaceAreaExecutionResult, ...]]:
    if not isinstance(combined_result, CombinedResult):
        raise TypeError("combined_result must be a CombinedResult")
    validate_combined_result(combined_result)
    parsed_result = parse_combined_result(combined_result.as_dict())
    if parsed_result != combined_result:
        raise ValueError("Combined result is not canonical")
    if not isinstance(area_results, tuple):
        raise TypeError("area_results must be an immutable tuple")
    parsed_areas: list[WorkspaceAreaExecutionResult] = []
    for area_result in area_results:
        if not isinstance(area_result, WorkspaceAreaExecutionResult):
            raise TypeError("area_results contains an invalid result")
        parsed = parse_workspace_area_execution_result(area_result.as_dict())
        if parsed != area_result:
            raise ValueError("Workspace area result is not canonical")
        parsed_areas.append(parsed)
    return _ordered_bound_inputs(parsed_result, tuple(parsed_areas))


def _ordered_bound_inputs(
    combined_result: CombinedResult,
    area_results: tuple[WorkspaceAreaExecutionResult, ...],
) -> tuple[CombinedResult, tuple[WorkspaceAreaExecutionResult, ...]]:
    """Order already validated immutable inputs by their signed request bindings."""

    if not isinstance(combined_result, CombinedResult):
        raise TypeError("combined_result must be a CombinedResult")
    if not isinstance(area_results, tuple):
        raise TypeError("area_results must be an immutable tuple")
    if any(
        not isinstance(area_result, WorkspaceAreaExecutionResult)
        for area_result in area_results
    ):
        raise TypeError("area_results contains an invalid result")
    by_pair: dict[tuple[str, int], WorkspaceAreaExecutionResult] = {}
    for area_result in area_results:
        pair = (area_result.technology, area_result.target_resolution)
        if pair in by_pair:
            raise ValueError("Workspace area results contain a duplicate binding")
        by_pair[pair] = area_result
    expected_pairs = tuple(
        (binding.technology_id, binding.resolution)
        for binding in combined_result.request.area_result_bindings
    )
    if set(by_pair) != set(expected_pairs) or len(by_pair) != len(expected_pairs):
        raise ValueError("Workspace area results do not exactly cover the request")
    ordered = tuple(by_pair[pair] for pair in expected_pairs)
    for binding, area_result in zip(
        combined_result.request.area_result_bindings,
        ordered,
    ):
        if (
            area_result.result_signature_sha256
            != binding.result_signature_sha256
            or area_result.access_scope != combined_result.request.access_scope
            or area_result.region_id != combined_result.request.region_id
            or area_result.technology != binding.technology_id
            or area_result.target_resolution != binding.resolution
        ):
            raise ValueError("Workspace area result escaped its combined binding")
    return combined_result, ordered


def _area_matrix(
    result: CombinedResult,
    area_results: tuple[WorkspaceAreaExecutionResult, ...],
) -> dict[tuple[str, int], WorkspaceAreaExecutionResult]:
    matrix = {
        (item.technology, item.target_resolution): item
        for item in area_results
    }
    for resolution_result in result.resolutions:
        resolution = resolution_result.resolution
        reference = matrix[(result.technology_order[0], resolution)]
        reference_identity = (
            reference.eligible_surface_id,
            reference.support_domain_id,
            reference.surface_artifact_provider,
            reference.surface_artifact_path,
            reference.surface_artifact_sha256,
            reference.surface_artifact_bytes,
            reference.surface_id_field,
            reference.surface_area_field,
            reference.surface_area_unit,
            reference.surface_feature_collection_json,
            reference.declared_surface_cell_count,
            reference.declared_surface_total_area_km2,
            reference.cell_ids_sha256,
        )
        combined_by_id = {
            cell.cell_id: cell for cell in resolution_result.cells
        }
        if (
            reference.cell_count != resolution_result.cell_count
            or reference.cell_ids_sha256 != resolution_result.cell_ids_sha256
            or tuple(cell.cell_id for cell in reference.cells)
            != tuple(combined_by_id)
        ):
            raise ValueError("Combined resolution escaped its support geometry")
        for technology_id in result.technology_order:
            area = matrix[(technology_id, resolution)]
            identity = (
                area.eligible_surface_id,
                area.support_domain_id,
                area.surface_artifact_provider,
                area.surface_artifact_path,
                area.surface_artifact_sha256,
                area.surface_artifact_bytes,
                area.surface_id_field,
                area.surface_area_field,
                area.surface_area_unit,
                area.surface_feature_collection_json,
                area.declared_surface_cell_count,
                area.declared_surface_total_area_km2,
                area.cell_ids_sha256,
            )
            if identity != reference_identity:
                raise ValueError(
                    "Technologies do not share one support-domain GeoJSON"
                )
            if tuple(cell.cell_id for cell in area.cells) != tuple(combined_by_id):
                raise ValueError("Area-result cells escaped the combined domain")
            area_by_id = {cell.cell_id: cell for cell in area.cells}
            for cell_id, combined_cell in combined_by_id.items():
                technology = next(
                    item
                    for item in combined_cell.technologies
                    if item.technology_id == technology_id
                )
                area_cell = area_by_id[cell_id]
                if (
                    not _close(
                        technology.model_area_km2,
                        area_cell.model_area_km2,
                    )
                    or not _close(
                        technology.potential_area_km2,
                        area_cell.remaining_area_km2,
                    )
                    or not _close(
                        technology.potential_pct,
                        area_cell.potential_pct,
                    )
                ):
                    raise ValueError(
                        "Combined potential escaped its signed area result"
                    )
    return matrix


def _geometry_by_cell(
    area_result: WorkspaceAreaExecutionResult,
) -> dict[str, Mapping[str, Any]]:
    try:
        collection = json.loads(area_result.surface_feature_collection_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Support-domain GeoJSON is unreadable") from exc
    if not isinstance(collection, Mapping):
        raise ValueError("Support-domain GeoJSON must be a FeatureCollection")
    _validate_feature_collection_keys(collection, "Support-domain GeoJSON")
    features = collection.get("features")
    if collection.get("type") != "FeatureCollection" or not isinstance(
        features,
        list,
    ):
        raise ValueError("Support-domain GeoJSON must contain features")
    by_cell: dict[str, Mapping[str, Any]] = {}
    for feature in features:
        if not isinstance(feature, Mapping):
            raise TypeError("Support-domain feature must be an object")
        properties = feature.get("properties")
        geometry = feature.get("geometry")
        if not isinstance(properties, Mapping) or not isinstance(geometry, Mapping):
            raise TypeError("Support-domain feature is incomplete")
        cell_id = properties.get(area_result.surface_id_field)
        if not isinstance(cell_id, str) or cell_id in by_cell:
            raise ValueError("Support-domain feature identity is invalid")
        by_cell[cell_id] = geometry
    if set(by_cell) != {cell.cell_id for cell in area_result.cells}:
        raise ValueError("Support-domain geometry cells drifted from area result")
    return by_cell


def _map_layer(
    result: CombinedResult,
    resolution: int,
    area_result: WorkspaceAreaExecutionResult,
) -> tuple[CombinedPresentationMapLayer, tuple[tuple[JsonScalar, ...], ...]]:
    resolution_result = result.resolution_result(resolution)
    fields = _detail_fields(result.technology_order)
    geometries = _geometry_by_cell(area_result)
    rows = tuple(_detail_row(result, cell) for cell in resolution_result.cells)
    field_ids = tuple(field.field_id for field in fields)
    features = []
    for row in rows:
        properties = dict(zip(field_ids, row))
        cell_id = str(properties["cell_id"])
        features.append(
            {
                "type": "Feature",
                "properties": properties,
                "geometry": geometries[cell_id],
            }
        )
    feature_collection_json = _canonical_json(
        {"type": "FeatureCollection", "features": features}
    )
    layer = CombinedPresentationMapLayer(
        layer_id=f"combined:r{resolution}",
        resolution=resolution,
        allocation_state=result.allocation_state,
        support_domain_id=area_result.support_domain_id,
        geometry_source_sha256=area_result.surface_artifact_sha256,
        cell_ids_sha256=resolution_result.cell_ids_sha256,
        feature_count=resolution_result.cell_count,
        hover_fields=fields,
        feature_collection_json=feature_collection_json,
        feature_collection_sha256=_bytes_sha256(feature_collection_json),
        layer_signature_sha256="0" * 64,
    )
    layer = replace(
        layer,
        layer_signature_sha256=_canonical_sha256(
            _layer_signature_payload(layer)
        ),
    )
    return layer, rows


_AREA_BINDING_KEYS = {
    "technology_id",
    "resolution",
    "request_signature_sha256",
    "result_signature_sha256",
    "support_domain_id",
    "surface_artifact_sha256",
    "cell_ids_sha256",
}
_FIELD_KEYS = {"field_id", "value_type", "unit", "nullable"}
_MAP_LAYER_KEYS = {
    "layer_id",
    "resolution",
    "allocation_state",
    "support_domain_id",
    "geometry_source_sha256",
    "cell_ids_sha256",
    "feature_count",
    "hover_fields",
    "feature_collection_json",
    "feature_collection_sha256",
    "layer_signature_sha256",
}
_TABLE_KEYS = {
    "table_id",
    "kind",
    "resolution",
    "fields",
    "rows",
    "table_signature_sha256",
}
_METRIC_KEYS = {
    "metric_id",
    "technology_id",
    "field_id",
    "value",
    "unit",
    "metric_signature_sha256",
}
_PRESENTATION_KEYS = {
    "schema_version",
    "capability_id",
    "access_scope",
    "region_id",
    "finalization_resolution",
    "rollup_resolutions",
    "technology_order",
    "allocation_state",
    "allocation_detail",
    "combined_request_signature_sha256",
    "combined_result_signature_sha256",
    "technology_context_result_signature_sha256",
    "scenario_result_signature_sha256",
    "rooftop_result_signature_sha256",
    "social_acceptance_result_signature_sha256",
    "allocation_policy_signature_sha256",
    "area_result_bindings",
    "map_layers",
    "tables",
    "metrics",
    "presentation_signature_sha256",
}


def _parse_area_binding(value: Any) -> CombinedPresentationAreaBinding:
    raw = _mapping(value, "combined presentation area binding")
    _keys(raw, _AREA_BINDING_KEYS, "combined presentation area binding")
    return CombinedPresentationAreaBinding(
        technology_id=_identifier(
            raw["technology_id"],
            "combined presentation area technology",
        ),
        resolution=_resolution(
            raw["resolution"],
            "combined presentation area resolution",
        ),
        request_signature_sha256=_digest(
            raw["request_signature_sha256"],
            "combined presentation area request signature",
        ),
        result_signature_sha256=_digest(
            raw["result_signature_sha256"],
            "combined presentation area result signature",
        ),
        support_domain_id=_identifier(
            raw["support_domain_id"],
            "combined presentation support domain",
        ),
        surface_artifact_sha256=_digest(
            raw["surface_artifact_sha256"],
            "combined presentation surface artifact",
        ),
        cell_ids_sha256=_digest(
            raw["cell_ids_sha256"],
            "combined presentation area cell digest",
        ),
    )


def _parse_field(value: Any) -> CombinedPresentationField:
    raw = _mapping(value, "combined presentation field")
    _keys(raw, _FIELD_KEYS, "combined presentation field")
    nullable = raw["nullable"]
    if not isinstance(nullable, bool):
        raise TypeError("Combined presentation field nullable must be boolean")
    unit = raw["unit"]
    if unit is not None:
        unit = _exact_text(unit, "combined presentation field unit")
    return CombinedPresentationField(
        field_id=_identifier(
            raw["field_id"],
            "combined presentation field id",
        ),
        value_type=_identifier(
            raw["value_type"],
            "combined presentation field value type",
        ),
        unit=unit,
        nullable=nullable,
    )


def _parse_map_layer(value: Any) -> CombinedPresentationMapLayer:
    raw = _mapping(value, "combined presentation map layer")
    _keys(raw, _MAP_LAYER_KEYS, "combined presentation map layer")
    fields = raw["hover_fields"]
    if not isinstance(fields, list):
        raise TypeError("Combined presentation hover fields must be a list")
    return CombinedPresentationMapLayer(
        layer_id=_identifier(raw["layer_id"], "combined presentation layer id"),
        resolution=_resolution(
            raw["resolution"],
            "combined presentation layer resolution",
        ),
        allocation_state=_identifier(
            raw["allocation_state"],
            "combined presentation layer allocation state",
        ),
        support_domain_id=_identifier(
            raw["support_domain_id"],
            "combined presentation layer support domain",
        ),
        geometry_source_sha256=_digest(
            raw["geometry_source_sha256"],
            "combined presentation layer geometry source",
        ),
        cell_ids_sha256=_digest(
            raw["cell_ids_sha256"],
            "combined presentation layer cell digest",
        ),
        feature_count=_integer(
            raw["feature_count"],
            "combined presentation layer feature count",
            positive=True,
        ),
        hover_fields=tuple(_parse_field(item) for item in fields),
        feature_collection_json=_exact_text(
            raw["feature_collection_json"],
            "combined presentation feature collection",
        ),
        feature_collection_sha256=_digest(
            raw["feature_collection_sha256"],
            "combined presentation feature collection digest",
        ),
        layer_signature_sha256=_digest(
            raw["layer_signature_sha256"],
            "combined presentation layer signature",
        ),
    )


def _parse_table(value: Any) -> CombinedPresentationTable:
    raw = _mapping(value, "combined presentation table")
    _keys(raw, _TABLE_KEYS, "combined presentation table")
    fields = raw["fields"]
    rows = raw["rows"]
    if not isinstance(fields, list) or not isinstance(rows, list):
        raise TypeError("Combined presentation table collections must be lists")
    parsed_rows: list[tuple[JsonScalar, ...]] = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, list):
            raise TypeError("Combined presentation table row must be a list")
        parsed_rows.append(
            tuple(
                _json_scalar(
                    item,
                    f"combined presentation table row {row_index} value",
                )
                for item in row
            )
        )
    raw_resolution = raw["resolution"]
    resolution = (
        None
        if raw_resolution is None
        else _resolution(
            raw_resolution,
            "combined presentation table resolution",
        )
    )
    return CombinedPresentationTable(
        table_id=_identifier(raw["table_id"], "combined presentation table id"),
        kind=_identifier(raw["kind"], "combined presentation table kind"),
        resolution=resolution,
        fields=tuple(_parse_field(item) for item in fields),
        rows=tuple(parsed_rows),
        table_signature_sha256=_digest(
            raw["table_signature_sha256"],
            "combined presentation table signature",
        ),
    )


def _parse_metric(value: Any) -> CombinedPresentationMetric:
    raw = _mapping(value, "combined presentation metric")
    _keys(raw, _METRIC_KEYS, "combined presentation metric")
    return CombinedPresentationMetric(
        metric_id=_identifier(
            raw["metric_id"],
            "combined presentation metric id",
        ),
        technology_id=_identifier(
            raw["technology_id"],
            "combined presentation metric technology",
        ),
        field_id=_identifier(
            raw["field_id"],
            "combined presentation metric field",
        ),
        value=_number(raw["value"], "combined presentation metric value"),
        unit=_exact_text(raw["unit"], "combined presentation metric unit"),
        metric_signature_sha256=_digest(
            raw["metric_signature_sha256"],
            "combined presentation metric signature",
        ),
    )


def parse_combined_result_presentation(value: Any) -> CombinedResultPresentation:
    raw = _mapping(value, "combined result presentation")
    _keys(raw, _PRESENTATION_KEYS, "combined result presentation")
    rollups = raw["rollup_resolutions"]
    technologies = raw["technology_order"]
    area_bindings = raw["area_result_bindings"]
    map_layers = raw["map_layers"]
    tables = raw["tables"]
    metrics = raw["metrics"]
    if not all(
        isinstance(item, list)
        for item in (
            rollups,
            technologies,
            area_bindings,
            map_layers,
            tables,
            metrics,
        )
    ):
        raise TypeError("Combined presentation collections must be lists")
    presentation = CombinedResultPresentation(
        schema_version=_exact_text(
            raw["schema_version"],
            "combined presentation schema version",
        ),
        capability_id=_identifier(
            raw["capability_id"],
            "combined presentation capability",
        ),
        access_scope=_exact_text(
            raw["access_scope"],
            "combined presentation access scope",
        ),
        region_id=_identifier(
            raw["region_id"],
            "combined presentation region",
        ),
        finalization_resolution=_resolution(
            raw["finalization_resolution"],
            "combined presentation finalization resolution",
        ),
        rollup_resolutions=tuple(
            _resolution(item, "combined presentation rollup resolution")
            for item in rollups
        ),
        technology_order=tuple(
            _identifier(item, "combined presentation technology")
            for item in technologies
        ),
        allocation_state=_identifier(
            raw["allocation_state"],
            "combined presentation allocation state",
        ),
        allocation_detail=_exact_text(
            raw["allocation_detail"],
            "combined presentation allocation detail",
        ),
        combined_request_signature_sha256=_digest(
            raw["combined_request_signature_sha256"],
            "combined presentation request signature",
        ),
        combined_result_signature_sha256=_digest(
            raw["combined_result_signature_sha256"],
            "combined presentation result signature",
        ),
        technology_context_result_signature_sha256=_digest(
            raw["technology_context_result_signature_sha256"],
            "combined presentation technology-context signature",
        ),
        scenario_result_signature_sha256=_digest(
            raw["scenario_result_signature_sha256"],
            "combined presentation scenario signature",
        ),
        rooftop_result_signature_sha256=_digest(
            raw["rooftop_result_signature_sha256"],
            "combined presentation rooftop signature",
        ),
        social_acceptance_result_signature_sha256=_digest(
            raw["social_acceptance_result_signature_sha256"],
            "combined presentation social-acceptance signature",
        ),
        allocation_policy_signature_sha256=_optional_digest(
            raw["allocation_policy_signature_sha256"],
            "combined presentation allocation-policy signature",
        ),
        area_result_bindings=tuple(
            _parse_area_binding(item) for item in area_bindings
        ),
        map_layers=tuple(_parse_map_layer(item) for item in map_layers),
        tables=tuple(_parse_table(item) for item in tables),
        metrics=tuple(_parse_metric(item) for item in metrics),
        presentation_signature_sha256=_digest(
            raw["presentation_signature_sha256"],
            "combined presentation signature",
        ),
    )
    validate_combined_result_presentation(presentation)
    return presentation


def _validate_field(field: CombinedPresentationField) -> None:
    if not isinstance(field, CombinedPresentationField):
        raise TypeError("Combined presentation field has an invalid type")
    _identifier(field.field_id, "combined presentation field id")
    if field.value_type not in _VALUE_TYPES:
        raise NotImplementedError(
            f"Unsupported combined presentation value type: {field.value_type}"
        )
    if field.unit not in _UNITS:
        raise NotImplementedError(
            f"Unsupported combined presentation unit: {field.unit}"
        )
    if not isinstance(field.nullable, bool):
        raise TypeError("Combined presentation nullable flag must be boolean")


def _validate_field_value(
    field: CombinedPresentationField,
    value: JsonScalar,
    label: str,
) -> None:
    if value is None:
        if not field.nullable:
            raise ValueError(f"{label} must not be null")
        return
    if field.value_type == "string":
        if not isinstance(value, str):
            raise TypeError(f"{label} must be text")
        return
    if field.value_type == "boolean":
        if not isinstance(value, bool):
            raise TypeError(f"{label} must be boolean")
        return
    if field.value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{label} must be an integer")
        return
    _number(value, label)


def _validate_table_rows(table: CombinedPresentationTable) -> None:
    if not isinstance(table.fields, tuple) or not isinstance(table.rows, tuple):
        raise TypeError("Combined presentation table collections must be tuples")
    if not table.fields:
        raise ValueError("Combined presentation table must declare fields")
    field_ids: list[str] = []
    for field in table.fields:
        _validate_field(field)
        field_ids.append(field.field_id)
    if len(field_ids) != len(set(field_ids)):
        raise ValueError("Combined presentation table fields must be unique")
    for row_index, row in enumerate(table.rows):
        if not isinstance(row, tuple):
            raise TypeError("Combined presentation rows must be tuples")
        if len(row) != len(table.fields):
            raise ValueError("Combined presentation row width drifted")
        for field, value in zip(table.fields, row, strict=True):
            _validate_field_value(
                field,
                value,
                f"combined presentation row {row_index} field {field.field_id}",
            )


def _feature_rows(
    layer: CombinedPresentationMapLayer,
    *,
    finalization_resolution: int,
) -> tuple[tuple[JsonScalar, ...], ...]:
    try:
        collection = json.loads(layer.feature_collection_json)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Combined presentation feature collection is unreadable"
        ) from exc
    collection = _mapping(collection, "combined presentation feature collection")
    _validate_feature_collection_keys(
        collection,
        "combined presentation feature collection",
    )
    features = collection["features"]
    if collection["type"] != "FeatureCollection" or not isinstance(
        features,
        list,
    ):
        raise ValueError(
            "Combined presentation geometry must be a FeatureCollection"
        )
    if _canonical_json(collection) != layer.feature_collection_json:
        raise ValueError("Combined presentation GeoJSON must be canonical")
    field_ids = tuple(field.field_id for field in layer.hover_fields)
    rows: list[tuple[JsonScalar, ...]] = []
    cell_ids: list[str] = []
    collection_positions: list[tuple[float, ...]] = []
    for feature_index, feature in enumerate(features):
        feature = _mapping(feature, "combined presentation feature")
        _keys(
            feature,
            {"type", "properties", "geometry"},
            "combined presentation feature",
        )
        if feature["type"] != "Feature":
            raise ValueError("Combined presentation feature type is invalid")
        properties = _mapping(
            feature["properties"],
            "combined presentation feature properties",
        )
        if set(properties) != set(field_ids):
            raise ValueError(
                "Combined presentation feature properties drifted from fields"
            )
        row = tuple(
            _json_scalar(
                properties[field_id],
                f"combined presentation feature {feature_index} {field_id}",
            )
            for field_id in field_ids
        )
        for field, item in zip(layer.hover_fields, row, strict=True):
            _validate_field_value(
                field,
                item,
                f"combined presentation feature {feature_index} {field.field_id}",
            )
        geometry = _mapping(
            feature["geometry"],
            "combined presentation feature geometry",
        )
        if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Combined presentation feature geometry is invalid")
        positions = _geometry_positions(
            geometry.get("coordinates"),
            "combined presentation feature geometry",
        )
        collection_positions.extend(positions)
        try:
            polygon = shape(geometry)
        except Exception as exc:
            raise ValueError(
                "Combined presentation feature geometry is unreadable"
            ) from exc
        bounds = polygon.bounds
        if (
            polygon.is_empty
            or not polygon.is_valid
            or len(bounds) != 4
            or not all(math.isfinite(value) for value in bounds)
            or bounds[0] < -180.0
            or bounds[2] > 180.0
            or bounds[1] < -90.0
            or bounds[3] > 90.0
        ):
            raise ValueError(
                "Combined presentation feature geometry is empty, invalid, "
                "non-finite, or outside CRS84"
            )
        cell_id = properties.get("cell_id")
        if (
            not isinstance(cell_id, str)
            or not h3.is_valid_cell(cell_id)
            or h3.get_resolution(cell_id) != layer.resolution
        ):
            raise ValueError("Combined presentation feature H3 identity is invalid")
        cell_boundary = h3.cell_to_boundary(cell_id)
        cell_polygon = Polygon(
            (longitude, latitude) for latitude, longitude in cell_boundary
        )
        # H3 parent identity is topological, not a polygon-containment promise:
        # exact unions of finalized children can cross, or at a clipped edge
        # even sit outside, the parent's drawn CRS84 chord polygon. Spatial
        # containment is therefore meaningful only at finalization; coarser
        # geometry is instead bound byte-for-byte to the signed area result by
        # validate_combined_result_presentation_from_result().
        if layer.resolution == finalization_resolution:
            overlap_area = polygon.intersection(cell_polygon).area
            outside_area = polygon.difference(cell_polygon).area
            outside_tolerance = max(
                _GEOMETRY_AREA_ABSOLUTE_TOLERANCE,
                polygon.area * _GEOMETRY_AREA_RELATIVE_TOLERANCE,
                cell_polygon.area * _GEOMETRY_CELL_AREA_RELATIVE_TOLERANCE,
            )
            if overlap_area <= 0.0 or outside_area > outside_tolerance:
                raise ValueError(
                    "Combined finalization geometry must have positive area "
                    "inside and no material area outside its H3 cell"
                )
        if properties.get("resolution") != layer.resolution:
            raise ValueError("Combined presentation feature resolution drifted")
        if properties.get("allocation_state") != layer.allocation_state:
            raise ValueError("Combined presentation feature allocation state drifted")
        cell_ids.append(cell_id)
        rows.append(row)
    if (
        len(features) != layer.feature_count
        or len(cell_ids) != len(set(cell_ids))
        or tuple(cell_ids) != tuple(sorted(cell_ids))
        or _id_digest(cell_ids) != layer.cell_ids_sha256
    ):
        raise ValueError("Combined presentation feature domain drifted")
    _validate_bbox_coverage(
        _validate_feature_collection_bbox(
            collection.get("bbox"),
            "combined presentation feature collection",
        ),
        tuple(collection_positions),
        "combined presentation feature collection",
    )
    return tuple(rows)


def validate_combined_result_presentation(
    presentation: CombinedResultPresentation,
) -> None:
    if not isinstance(presentation, CombinedResultPresentation):
        raise TypeError("presentation must be a CombinedResultPresentation")
    if presentation.schema_version != COMBINED_PRESENTATION_SCHEMA_VERSION:
        raise NotImplementedError(
            "Unsupported combined presentation schema: "
            f"{presentation.schema_version}"
        )
    if presentation.capability_id != COMBINED_PRESENTATION_CAPABILITY_ID:
        raise ValueError("Combined presentation capability identity drifted")
    region_id = _identifier(presentation.region_id, "combined presentation region")
    access_scope = _exact_text(
        presentation.access_scope,
        "combined presentation access scope",
    )
    if access_scope not in {f"product:{region_id}", f"review:{region_id}"}:
        raise ValueError("Combined presentation access escaped its region")
    finalization_resolution = _resolution(
        presentation.finalization_resolution,
        "combined presentation finalization resolution",
    )
    if not isinstance(presentation.rollup_resolutions, tuple):
        raise TypeError("Combined presentation rollups must be a tuple")
    rollups = tuple(
        _resolution(value, "combined presentation rollup resolution")
        for value in presentation.rollup_resolutions
    )
    if (
        len(rollups) != len(set(rollups))
        or rollups != tuple(sorted(rollups, reverse=True))
        or any(value >= finalization_resolution for value in rollups)
    ):
        raise ValueError("Combined presentation rollup resolutions are invalid")
    resolutions = (finalization_resolution, *rollups)
    if not isinstance(presentation.technology_order, tuple):
        raise TypeError("Combined presentation technologies must be a tuple")
    technologies = tuple(
        _identifier(value, "combined presentation technology")
        for value in presentation.technology_order
    )
    if len(technologies) < 2 or len(technologies) != len(set(technologies)):
        raise ValueError("Combined presentation technologies are invalid")
    if presentation.allocation_state not in _ALLOCATION_STATES:
        raise NotImplementedError(
            "Unsupported combined presentation allocation state: "
            f"{presentation.allocation_state}"
        )
    _exact_text(
        presentation.allocation_detail,
        "combined presentation allocation detail",
    )
    for value, label in (
        (
            presentation.combined_request_signature_sha256,
            "combined presentation request signature",
        ),
        (
            presentation.combined_result_signature_sha256,
            "combined presentation result signature",
        ),
        (
            presentation.technology_context_result_signature_sha256,
            "combined presentation technology-context signature",
        ),
        (
            presentation.scenario_result_signature_sha256,
            "combined presentation scenario signature",
        ),
        (
            presentation.rooftop_result_signature_sha256,
            "combined presentation rooftop signature",
        ),
        (
            presentation.social_acceptance_result_signature_sha256,
            "combined presentation social-acceptance signature",
        ),
        (
            presentation.presentation_signature_sha256,
            "combined presentation signature",
        ),
    ):
        _digest(value, label)
    policy_signature = _optional_digest(
        presentation.allocation_policy_signature_sha256,
        "combined presentation allocation-policy signature",
    )
    if (presentation.allocation_state == "executed") != (
        policy_signature is not None
    ):
        raise ValueError("Combined presentation allocation-policy state drifted")
    if any(
        not isinstance(value, tuple)
        for value in (
            presentation.area_result_bindings,
            presentation.map_layers,
            presentation.tables,
            presentation.metrics,
        )
    ):
        raise TypeError("Combined presentation collections must be tuples")

    expected_pairs = tuple(
        (technology_id, resolution)
        for technology_id in technologies
        for resolution in resolutions
    )
    if len(presentation.area_result_bindings) != len(expected_pairs):
        raise ValueError("Combined presentation area binding count drifted")
    area_by_pair: dict[
        tuple[str, int], CombinedPresentationAreaBinding
    ] = {}
    for binding in presentation.area_result_bindings:
        if not isinstance(binding, CombinedPresentationAreaBinding):
            raise TypeError("Combined presentation area binding is invalid")
        pair = (
            _identifier(binding.technology_id, "combined area technology"),
            _resolution(binding.resolution, "combined area resolution"),
        )
        if pair in area_by_pair:
            raise ValueError("Combined presentation area binding is duplicated")
        area_by_pair[pair] = binding
        _digest(binding.request_signature_sha256, "combined area request signature")
        _digest(binding.result_signature_sha256, "combined area result signature")
        _identifier(binding.support_domain_id, "combined area support domain")
        _digest(binding.surface_artifact_sha256, "combined area surface artifact")
        _digest(binding.cell_ids_sha256, "combined area cell digest")
    if tuple(area_by_pair) != expected_pairs:
        raise ValueError("Combined presentation area binding order drifted")
    support_domain_ids = {
        binding.support_domain_id
        for binding in presentation.area_result_bindings
    }
    if len(support_domain_ids) != 1:
        raise ValueError("Combined presentation support domains drifted")
    support_domain_id = next(iter(support_domain_ids))
    for resolution in resolutions:
        resolution_bindings = tuple(
            area_by_pair[(technology_id, resolution)]
            for technology_id in technologies
        )
        if (
            len(
                {
                    binding.surface_artifact_sha256
                    for binding in resolution_bindings
                }
            )
            != 1
            or len(
                {binding.cell_ids_sha256 for binding in resolution_bindings}
            )
            != 1
        ):
            raise ValueError(
                "Combined presentation technology domains drifted"
            )

    if len(presentation.map_layers) != len(resolutions):
        raise ValueError("Combined presentation map-layer count drifted")
    layer_rows: dict[int, tuple[tuple[JsonScalar, ...], ...]] = {}
    for expected_resolution, layer in zip(
        resolutions,
        presentation.map_layers,
        strict=True,
    ):
        if not isinstance(layer, CombinedPresentationMapLayer):
            raise TypeError("Combined presentation map layer is invalid")
        if (
            layer.layer_id != f"combined:r{expected_resolution}"
            or layer.resolution != expected_resolution
            or layer.allocation_state != presentation.allocation_state
            or layer.support_domain_id != support_domain_id
        ):
            raise ValueError("Combined presentation map-layer identity drifted")
        _identifier(layer.layer_id, "combined presentation layer id")
        _resolution(layer.resolution, "combined presentation layer resolution")
        _identifier(
            layer.allocation_state,
            "combined presentation layer allocation state",
        )
        _identifier(
            layer.support_domain_id,
            "combined presentation layer support domain",
        )
        _digest(
            layer.geometry_source_sha256,
            "combined presentation layer geometry source",
        )
        _digest(
            layer.cell_ids_sha256,
            "combined presentation layer cell digest",
        )
        _exact_text(
            layer.feature_collection_json,
            "combined presentation feature collection",
        )
        _digest(
            layer.feature_collection_sha256,
            "combined presentation feature collection digest",
        )
        reference = area_by_pair[(technologies[0], expected_resolution)]
        if (
            layer.geometry_source_sha256
            != reference.surface_artifact_sha256
            or layer.cell_ids_sha256 != reference.cell_ids_sha256
        ):
            raise ValueError("Combined presentation map geometry drifted")
        _integer(
            layer.feature_count,
            "combined presentation feature count",
            positive=True,
        )
        if not isinstance(layer.hover_fields, tuple):
            raise TypeError("Combined presentation hover fields must be a tuple")
        for field in layer.hover_fields:
            _validate_field(field)
        if layer.hover_fields != _detail_fields(technologies):
            raise ValueError("Combined presentation hover schema drifted")
        if _bytes_sha256(layer.feature_collection_json) != (
            layer.feature_collection_sha256
        ):
            raise ValueError("Combined presentation feature digest drifted")
        rows = _feature_rows(
            layer,
            finalization_resolution=presentation.finalization_resolution,
        )
        if len(rows) != layer.feature_count:
            raise ValueError("Combined presentation feature count drifted")
        layer_rows[expected_resolution] = rows
        _digest(layer.layer_signature_sha256, "combined layer signature")
        if layer.layer_signature_sha256 != _canonical_sha256(
            _layer_signature_payload(layer)
        ):
            raise ValueError("Combined presentation layer signature drifted")

    if not presentation.tables or not isinstance(presentation.tables[0], CombinedPresentationTable):
        raise ValueError("Combined presentation summary table is missing")
    summary = presentation.tables[0]
    _validate_table_rows(summary)
    if len(summary.rows) != len(technologies) or any(len(row) < 3 for row in summary.rows):
        raise ValueError("Combined presentation summary row count or width drifted")
    expected_table_specs = (
        ("technology_summary", "summary", None, _summary_fields(capacity=presentation.tables[0].rows[0][2] is None)),
        *tuple(
            (
                f"cell_detail:r{resolution}",
                "detail",
                resolution,
                _detail_fields(technologies),
            )
            for resolution in resolutions
        ),
    )
    if len(presentation.tables) != len(expected_table_specs):
        raise ValueError("Combined presentation table count drifted")
    for table, expected in zip(
        presentation.tables,
        expected_table_specs,
        strict=True,
    ):
        if not isinstance(table, CombinedPresentationTable):
            raise TypeError("Combined presentation table is invalid")
        table_id, kind, resolution, fields = expected
        _validate_table_rows(table)
        if (
            table.table_id != table_id
            or table.kind != kind
            or table.resolution != resolution
            or table.fields != fields
        ):
            raise ValueError("Combined presentation table schema drifted")
        _digest(table.table_signature_sha256, "combined table signature")
        if table.table_signature_sha256 != _canonical_sha256(
            _table_signature_payload(table)
        ):
            raise ValueError("Combined presentation table signature drifted")
        if resolution is not None and table.rows != layer_rows[resolution]:
            raise ValueError("Combined presentation map and table rows drifted")

    summary = presentation.tables[0]
    if len(summary.rows) != len(technologies):
        raise ValueError("Combined presentation summary row count drifted")
    for technology_id, row in zip(technologies, summary.rows, strict=True):
        if row[0] != technology_id or row[1] != presentation.allocation_state:
            raise ValueError("Combined presentation summary identity drifted")
        for field, value in zip(summary.fields[2:], row[2:], strict=True):
            if value is not None and _number(
                value,
                f"combined summary {technology_id} {field.field_id}",
            ) < 0.0:
                raise ValueError("Combined presentation summary value is negative")
        if presentation.allocation_state == "blocked_missing_policy" and any(
            value is not None
            for field, value in zip(summary.fields, row, strict=True)
            if field.nullable and field.field_id not in {"gross_energy_twh", "ground_energy_twh"}
        ):
            raise ValueError("Blocked combined summary contains allocation values")

    for resolution, rows in layer_rows.items():
        fields = _detail_fields(technologies)
        field_index = {
            field.field_id: index for index, field in enumerate(fields)
        }
        for row in rows:
            model_area = float(row[field_index["model_area_km2"]])
            if model_area <= 0.0:
                raise ValueError("Combined presentation model area is not positive")
            if row[field_index["resolution"]] != resolution:
                raise ValueError("Combined presentation detail resolution drifted")
            if row[field_index["allocation_state"]] != (
                presentation.allocation_state
            ) or row[field_index["allocation_executed"]] != (
                presentation.allocation_state == "executed"
            ):
                raise ValueError("Combined presentation detail allocation drifted")
            context_status = row[field_index["context_status"]]
            social_status = row[field_index["social_data_status"]]
            if context_status not in _CONTEXT_STATUSES:
                raise ValueError("Combined presentation context status is invalid")
            if social_status not in _SOCIAL_DATA_STATUSES:
                raise ValueError("Combined presentation social status is invalid")
            social_value = row[field_index["social_acceptance_value"]]
            if (social_status == "not_assessed") != (social_value is None):
                raise ValueError(
                    "Combined presentation social status and value drifted"
                )
            if social_value is not None and not 0.0 <= float(social_value) <= 1.0:
                raise ValueError("Combined presentation social value is invalid")
            for technology_id in technologies:
                potential_area = float(
                    row[field_index[f"{technology_id}.potential_area_km2"]]
                )
                potential_pct = float(
                    row[field_index[f"{technology_id}.potential_pct"]]
                )
                adjusted_area = float(
                    row[
                        field_index[
                            f"{technology_id}.acceptance_adjusted_potential_area_km2"
                        ]
                    ]
                )
                if (
                    potential_area < 0.0
                    or potential_area > model_area + _FLOAT_TOLERANCE
                    or potential_pct < 0.0
                    or potential_pct > 100.0
                    or not _close(
                        potential_pct,
                        potential_area / model_area * 100.0,
                        tolerance=1e-10,
                    )
                    or adjusted_area < 0.0
                    or adjusted_area > potential_area + _FLOAT_TOLERANCE
                ):
                    raise ValueError(
                        "Combined presentation potential values do not reconcile"
                    )
                priority_score = row[
                    field_index[f"{technology_id}.allocation_priority_score"]
                ]
                allocation_eligible = row[
                    field_index[f"{technology_id}.allocation_eligible"]
                ]
                allocated_area = row[
                    field_index[f"{technology_id}.allocated_area_km2"]
                ]
                allocated_twh = row[
                    field_index[f"{technology_id}.allocated_twh"]
                ]
                if presentation.allocation_state == "blocked_missing_policy":
                    if any(
                        value is not None
                        for value in (
                            priority_score,
                            allocation_eligible,
                            allocated_area,
                            allocated_twh,
                        )
                    ):
                        raise ValueError(
                            "Blocked combined detail contains allocation values"
                        )
                    continue
                if (
                    not isinstance(allocation_eligible, bool)
                    or allocated_area is None
                    or float(allocated_area) < 0.0
                    or (allocated_twh is not None and float(allocated_twh) < 0.0)
                    or float(allocated_area) > model_area + _FLOAT_TOLERANCE
                ):
                    raise ValueError(
                        "Executed combined detail lacks valid allocation values"
                    )
                if resolution == finalization_resolution:
                    if (priority_score is None) == allocation_eligible:
                        raise ValueError(
                            "Executed final allocation priority drifted"
                        )
                    if priority_score is not None and float(priority_score) < 0.0:
                        raise ValueError(
                            "Executed final allocation priority is negative"
                        )
                elif priority_score is not None:
                    raise ValueError(
                        "Combined rollup contains reranked allocation evidence"
                    )

    detail_fields = _detail_fields(technologies)
    detail_index = {
        field.field_id: index for index, field in enumerate(detail_fields)
    }
    final_rows = layer_rows[finalization_resolution]
    summary_index = {
        field.field_id: index for index, field in enumerate(summary.fields)
    }
    for technology_id, summary_row in zip(
        technologies,
        summary.rows,
        strict=True,
    ):
        summary_values = {
            field_id: summary_row[index]
            for field_id, index in summary_index.items()
        }
        gross_energy = summary_values["gross_energy_twh"]
        gross_area = float(summary_values["gross_area_need_km2"])
        rooftop_energy = float(summary_values["rooftop_contribution_twh"])
        ground_energy = summary_values["ground_energy_twh"]
        ground_area = float(summary_values["ground_area_need_km2"])
        if gross_energy is None:
            if ground_energy is not None or rooftop_energy != 0 or not _close(gross_area, ground_area):
                raise ValueError("Area-only summary fabricated energy or rooftop credit")
        else:
            if not _close(gross_energy, rooftop_energy + ground_energy):
                raise ValueError(
                    "Combined presentation summary energy does not reconcile"
                )
            if gross_energy == 0.0:
                if gross_area != 0.0 or ground_energy != 0.0 or ground_area != 0.0:
                    raise ValueError(
                        "Combined presentation zero demand contains ground demand"
                    )
            else:
                gross_factor = gross_area / gross_energy
                if gross_factor <= 0.0 or not _close(
                    ground_area,
                    ground_energy * gross_factor,
                ):
                    raise ValueError(
                        "Combined presentation ground demand does not reconcile"
                    )
        potential = math.fsum(
            float(
                row[
                    detail_index[f"{technology_id}.potential_area_km2"]
                ]
            )
            for row in final_rows
        )
        adjusted = math.fsum(
            float(
                row[
                    detail_index[
                        f"{technology_id}.acceptance_adjusted_potential_area_km2"
                    ]
                ]
            )
            for row in final_rows
        )
        if not _close(
            float(summary_values["potential_area_km2"]),
            potential,
        ) or not _close(
            float(summary_values["acceptance_adjusted_potential_area_km2"]),
            adjusted,
        ):
            raise ValueError(
                "Combined presentation summary potential drifted from final rows"
            )
        if presentation.allocation_state != "executed":
            continue
        allocation_summary_fields = (
            "selected_area_km2",
            *(("selected_twh",) if gross_energy is not None else ()),
            "inside_potential_area_km2",
            "outside_potential_area_km2",
            "unmet_area_km2",
        )
        if any(
            summary_values[field_id] is None
            for field_id in allocation_summary_fields
        ):
            raise ValueError(
                "Executed combined presentation summary is incomplete"
            )
        selected_area = math.fsum(
            float(
                row[
                    detail_index[f"{technology_id}.allocated_area_km2"]
                ]
            )
            for row in final_rows
        )
        selected_twh = known_sum(row[detail_index[f"{technology_id}.allocated_twh"]] for row in final_rows)
        if (selected_twh is None) != (gross_energy is None):
            raise ValueError("Allocation production availability differs from scenario")
        summary_selected_area = float(summary_values["selected_area_km2"])
        summary_selected_twh = summary_values["selected_twh"]
        inside_area = float(summary_values["inside_potential_area_km2"])
        outside_area = float(summary_values["outside_potential_area_km2"])
        unmet_area = float(summary_values["unmet_area_km2"])
        if (
            not _close(summary_selected_area, selected_area)
            or not _close(summary_selected_twh, selected_twh)
            or not _close(summary_selected_area, inside_area + outside_area)
            or not _close(summary_selected_area + unmet_area, ground_area)
        ):
            raise ValueError(
                "Combined presentation allocation summary drifted from final rows"
            )
        if ground_energy is None:
            if selected_twh is not None or summary_selected_twh is not None:
                raise ValueError("Area-only allocation invented energy")
        elif ground_energy == 0.0:
            if ground_area != 0.0 or selected_twh != 0.0:
                raise ValueError(
                    "Combined presentation zero ground demand was allocated"
                )
        else:
            ground_factor = ground_area / ground_energy
            if ground_factor <= 0.0 or not _close(
                selected_twh,
                selected_area / ground_factor,
            ):
                raise ValueError(
                    "Combined presentation selected energy does not reconcile"
                )

    final_by_id = {
        str(row[detail_index["cell_id"]]): row for row in final_rows
    }
    for resolution in rollups:
        grouped: dict[str, list[tuple[JsonScalar, ...]]] = {}
        for cell_id, row in final_by_id.items():
            parent_id = str(h3.cell_to_parent(cell_id, resolution))
            grouped.setdefault(parent_id, []).append(row)
        rollup_rows = {
            str(row[detail_index["cell_id"]]): row
            for row in layer_rows[resolution]
        }
        if set(grouped) != set(rollup_rows):
            raise ValueError(
                "Combined presentation rollup domain is not derived from final rows"
            )
        for parent_id, parent_row in rollup_rows.items():
            children = grouped[parent_id]
            context_statuses = tuple(
                row[detail_index["context_status"]] for row in children
            )
            expected_context_status = (
                "complete"
                if all(value == "complete" for value in context_statuses)
                else "not_assessed"
                if all(value == "not_assessed" for value in context_statuses)
                else "partial"
            )
            if parent_row[detail_index["context_status"]] != (
                expected_context_status
            ):
                raise ValueError(
                    "Combined presentation context rollup drifted"
                )
            assessed_children = tuple(
                row
                for row in children
                if row[detail_index["social_data_status"]] != "not_assessed"
            )
            parent_social_status = parent_row[
                detail_index["social_data_status"]
            ]
            parent_social_value = parent_row[
                detail_index["social_acceptance_value"]
            ]
            if not assessed_children:
                expected_social_status = "not_assessed"
            elif len(assessed_children) != len(children):
                expected_social_status = "partial"
            else:
                assessed_statuses = {
                    row[detail_index["social_data_status"]]
                    for row in assessed_children
                }
                expected_social_status = (
                    next(iter(assessed_statuses))
                    if len(assessed_statuses) == 1
                    else "partial"
                )
            if parent_social_status != expected_social_status:
                raise ValueError("Combined presentation social rollup drifted")
            if assessed_children:
                child_social_values = tuple(
                    float(row[detail_index["social_acceptance_value"]])
                    for row in assessed_children
                )
                if parent_social_value is None or not (
                    min(child_social_values) - _FLOAT_TOLERANCE
                    <= float(parent_social_value)
                    <= max(child_social_values) + _FLOAT_TOLERANCE
                ):
                    raise ValueError(
                        "Combined presentation social rollup value is invalid"
                    )
            elif parent_social_value is not None:
                raise ValueError(
                    "Combined presentation unassessed rollup has a social value"
                )
            for technology_id in technologies:
                for field_id in (
                    "potential_area_km2",
                    "acceptance_adjusted_potential_area_km2",
                ):
                    parent_value = float(
                        parent_row[
                            detail_index[f"{technology_id}.{field_id}"]
                        ]
                    )
                    child_total = math.fsum(
                        float(
                            row[
                                detail_index[f"{technology_id}.{field_id}"]
                            ]
                        )
                        for row in children
                    )
                    if not _close(parent_value, child_total):
                        raise ValueError(
                            "Combined presentation potential rollup is not a "
                            "final-row sum"
                        )
                parent_model = float(
                    parent_row[detail_index["model_area_km2"]]
                )
                child_model = math.fsum(
                    float(row[detail_index["model_area_km2"]])
                    for row in children
                )
                if not _close(parent_model, child_model):
                    raise ValueError(
                        "Combined presentation model-area rollup is not a "
                        "final-row sum"
                    )
                if presentation.allocation_state != "executed":
                    continue
                parent_eligible = parent_row[
                    detail_index[f"{technology_id}.allocation_eligible"]
                ]
                child_eligible = any(
                    bool(
                        row[
                            detail_index[
                                f"{technology_id}.allocation_eligible"
                            ]
                        ]
                    )
                    for row in children
                )
                if parent_eligible != child_eligible:
                    raise ValueError(
                        "Combined presentation allocation eligibility rollup drifted"
                    )
                for field_id in ("allocated_area_km2", "allocated_twh"):
                    parent_value = parent_row[detail_index[f"{technology_id}.{field_id}"]]
                    child_total = known_sum(row[detail_index[f"{technology_id}.{field_id}"]] for row in children)
                    if not _close(parent_value, child_total):
                        raise ValueError(
                            "Combined presentation allocation rollup is not a "
                            "final-row sum"
                        )

    if not isinstance(presentation.metrics, tuple):
        raise TypeError("Combined presentation metrics must be a tuple")
    metric_ids: set[str] = set()
    for metric in presentation.metrics:
        if not isinstance(metric, CombinedPresentationMetric):
            raise TypeError("Combined presentation metric is invalid")
        metric_id = _identifier(metric.metric_id, "combined metric id")
        if metric_id in metric_ids or metric.technology_id not in technologies:
            raise ValueError("Combined presentation metric identity is invalid")
        metric_ids.add(metric_id)
        _identifier(metric.field_id, "combined metric field id")
        if metric.unit not in _UNITS or metric.unit is None:
            raise NotImplementedError(
                f"Unsupported combined presentation metric unit: {metric.unit}"
            )
        if _number(metric.value, "combined metric value") < 0.0:
            raise ValueError("Combined presentation metric value is negative")
        _digest(metric.metric_signature_sha256, "combined metric signature")
        if metric.metric_signature_sha256 != _canonical_sha256(
            _metric_signature_payload(metric)
        ):
            raise ValueError("Combined presentation metric signature drifted")
    if presentation.metrics != _metrics_from_summary(summary):
        raise ValueError("Combined presentation metrics drifted from summary")
    if presentation.presentation_signature_sha256 != _canonical_sha256(
        _presentation_signature_payload(presentation)
    ):
        raise ValueError("Combined presentation signature drifted")


def _build_combined_result_presentation_unvalidated(
    combined_result: CombinedResult,
    area_results: tuple[WorkspaceAreaExecutionResult, ...],
) -> CombinedResultPresentation:
    result, ordered_areas = _strict_inputs(combined_result, area_results)
    return _assemble_combined_result_presentation(result, ordered_areas)


def _assemble_combined_result_presentation(
    result: CombinedResult,
    ordered_areas: tuple[WorkspaceAreaExecutionResult, ...],
) -> CombinedResultPresentation:
    matrix = _area_matrix(result, ordered_areas)
    resolutions = (
        result.request.finalization_resolution,
        *result.request.rollup_resolutions,
    )
    map_layers: list[CombinedPresentationMapLayer] = []
    detail_tables: list[CombinedPresentationTable] = []
    for resolution in resolutions:
        reference = matrix[(result.technology_order[0], resolution)]
        layer, rows = _map_layer(result, resolution, reference)
        map_layers.append(layer)
        detail_tables.append(
            _signed_table(
                table_id=f"cell_detail:r{resolution}",
                kind="detail",
                resolution=resolution,
                fields=layer.hover_fields,
                rows=rows,
            )
        )
    summary = _signed_table(
        table_id="technology_summary",
        kind="summary",
        resolution=None,
        fields=_summary_fields(capacity=result.technology_summaries[0].gross_energy_twh is None),
        rows=tuple(
            _summary_row(result, technology_id)
            for technology_id in result.technology_order
        ),
    )
    area_bindings = tuple(
        CombinedPresentationAreaBinding(
            technology_id=area.technology,
            resolution=area.target_resolution,
            request_signature_sha256=area.request_signature_sha256,
            result_signature_sha256=area.result_signature_sha256,
            support_domain_id=area.support_domain_id,
            surface_artifact_sha256=area.surface_artifact_sha256,
            cell_ids_sha256=area.cell_ids_sha256,
        )
        for area in ordered_areas
    )
    request = result.request
    presentation = CombinedResultPresentation(
        schema_version=COMBINED_PRESENTATION_SCHEMA_VERSION,
        capability_id=COMBINED_PRESENTATION_CAPABILITY_ID,
        access_scope=request.access_scope,
        region_id=request.region_id,
        finalization_resolution=request.finalization_resolution,
        rollup_resolutions=request.rollup_resolutions,
        technology_order=result.technology_order,
        allocation_state=result.allocation_state,
        allocation_detail=result.allocation_detail,
        combined_request_signature_sha256=request.request_signature_sha256,
        combined_result_signature_sha256=result.result_signature_sha256,
        technology_context_result_signature_sha256=(
            request.technology_context_result_signature_sha256
        ),
        scenario_result_signature_sha256=(
            request.scenario_result_signature_sha256
        ),
        rooftop_result_signature_sha256=request.rooftop_result_signature_sha256,
        social_acceptance_result_signature_sha256=(
            request.social_acceptance_result_signature_sha256
        ),
        allocation_policy_signature_sha256=(
            request.allocation_policy_signature_sha256
        ),
        area_result_bindings=area_bindings,
        map_layers=tuple(map_layers),
        tables=(summary, *detail_tables),
        metrics=_metrics_from_summary(summary),
        presentation_signature_sha256="0" * 64,
    )
    presentation = replace(
        presentation,
        presentation_signature_sha256=_canonical_sha256(
            _presentation_signature_payload(presentation)
        ),
    )
    return presentation


def build_combined_result_presentation_from_validated_inputs(
    combined_result: CombinedResult,
    area_results: tuple[WorkspaceAreaExecutionResult, ...],
) -> CombinedResultPresentation:
    """Build once from upstream results already validated by their engines.

    The normal public builder and parser retain their exhaustive canonical
    replay checks.  This execution-path builder verifies the exact signed
    bindings and shared geometry/value matrix, then assembles the same
    deterministic presentation without serializing and rebuilding it again.
    """

    result, ordered_areas = _ordered_bound_inputs(combined_result, area_results)
    presentation = _assemble_combined_result_presentation(result, ordered_areas)
    if (
        presentation.combined_request_signature_sha256
        != result.request.request_signature_sha256
        or presentation.combined_result_signature_sha256
        != result.result_signature_sha256
        or presentation.presentation_signature_sha256
        != _canonical_sha256(_presentation_signature_payload(presentation))
    ):
        raise ValueError("Combined presentation escaped its validated inputs")
    return presentation


def _surface_geometry_by_cell(
    area_result: WorkspaceAreaExecutionResult,
) -> dict[str, Mapping[str, Any]]:
    try:
        collection = json.loads(area_result.surface_feature_collection_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Signed support-domain GeoJSON is unreadable") from exc
    collection = _mapping(collection, "signed support-domain GeoJSON")
    _validate_feature_collection_keys(collection, "signed support-domain GeoJSON")
    features = collection.get("features")
    if collection.get("type") != "FeatureCollection" or not isinstance(
        features,
        list,
    ):
        raise ValueError("Signed support-domain GeoJSON has no features")
    result: dict[str, Mapping[str, Any]] = {}
    for feature in features:
        feature = _mapping(feature, "signed support-domain feature")
        properties = _mapping(
            feature.get("properties"),
            "signed support-domain feature properties",
        )
        geometry = _mapping(
            feature.get("geometry"),
            "signed support-domain feature geometry",
        )
        cell_id = properties.get(area_result.surface_id_field)
        if not isinstance(cell_id, str) or cell_id in result:
            raise ValueError("Signed support-domain feature id is invalid")
        result[cell_id] = geometry
    if set(result) != {cell.cell_id for cell in area_result.cells}:
        raise ValueError("Signed support-domain geometry coverage drifted")
    return result


def _presentation_geometry_by_cell(
    layer: CombinedPresentationMapLayer,
) -> dict[str, Mapping[str, Any]]:
    try:
        collection = json.loads(layer.feature_collection_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Combined presentation GeoJSON is unreadable") from exc
    collection = _mapping(collection, "combined presentation GeoJSON")
    features = collection.get("features")
    if not isinstance(features, list):
        raise ValueError("Combined presentation GeoJSON has no features")
    result: dict[str, Mapping[str, Any]] = {}
    for feature in features:
        feature = _mapping(feature, "combined presentation feature")
        properties = _mapping(
            feature.get("properties"),
            "combined presentation feature properties",
        )
        geometry = _mapping(
            feature.get("geometry"),
            "combined presentation feature geometry",
        )
        cell_id = properties.get("cell_id")
        if not isinstance(cell_id, str) or cell_id in result:
            raise ValueError("Combined presentation feature id is invalid")
        result[cell_id] = geometry
    return result


def validate_combined_result_presentation_from_result(
    presentation: CombinedResultPresentation,
    combined_result: CombinedResult,
    area_results: tuple[WorkspaceAreaExecutionResult, ...],
) -> None:
    """Bind one standalone presentation to its exact signed upstream values."""

    validate_combined_result_presentation(presentation)
    result, ordered_areas = _strict_inputs(combined_result, area_results)
    matrix = _area_matrix(result, ordered_areas)
    request = result.request
    if (
        presentation.access_scope != request.access_scope
        or presentation.region_id != request.region_id
        or presentation.finalization_resolution
        != request.finalization_resolution
        or presentation.rollup_resolutions != request.rollup_resolutions
        or presentation.technology_order != result.technology_order
        or presentation.allocation_state != result.allocation_state
        or presentation.allocation_detail != result.allocation_detail
        or presentation.combined_request_signature_sha256
        != request.request_signature_sha256
        or presentation.combined_result_signature_sha256
        != result.result_signature_sha256
        or presentation.technology_context_result_signature_sha256
        != request.technology_context_result_signature_sha256
        or presentation.scenario_result_signature_sha256
        != request.scenario_result_signature_sha256
        or presentation.rooftop_result_signature_sha256
        != request.rooftop_result_signature_sha256
        or presentation.social_acceptance_result_signature_sha256
        != request.social_acceptance_result_signature_sha256
        or presentation.allocation_policy_signature_sha256
        != request.allocation_policy_signature_sha256
    ):
        raise ValueError(
            "Combined presentation escaped its signed combined result"
        )
    expected_bindings = tuple(
        CombinedPresentationAreaBinding(
            technology_id=area.technology,
            resolution=area.target_resolution,
            request_signature_sha256=area.request_signature_sha256,
            result_signature_sha256=area.result_signature_sha256,
            support_domain_id=area.support_domain_id,
            surface_artifact_sha256=area.surface_artifact_sha256,
            cell_ids_sha256=area.cell_ids_sha256,
        )
        for area in ordered_areas
    )
    if presentation.area_result_bindings != expected_bindings:
        raise ValueError(
            "Combined presentation escaped its signed area-result bindings"
        )
    layers_by_resolution = {
        layer.resolution: layer for layer in presentation.map_layers
    }
    for resolution in (
        request.finalization_resolution,
        *request.rollup_resolutions,
    ):
        area_result = matrix[(result.technology_order[0], resolution)]
        source_geometry = _surface_geometry_by_cell(area_result)
        presented_geometry = _presentation_geometry_by_cell(
            layers_by_resolution[resolution]
        )
        if set(presented_geometry) != set(source_geometry) or any(
            _canonical_json(presented_geometry[cell_id])
            != _canonical_json(source_geometry[cell_id])
            for cell_id in source_geometry
        ):
            raise ValueError(
                "Combined presentation geometry escaped its signed surface"
            )
    expected = _build_combined_result_presentation_unvalidated(
        result,
        ordered_areas,
    )
    if presentation != expected:
        raise ValueError(
            "Combined presentation drifted from its exact upstream results"
        )


def build_combined_result_presentation(
    combined_result: CombinedResult,
    area_results: tuple[WorkspaceAreaExecutionResult, ...],
) -> CombinedResultPresentation:
    """Build one renderer-neutral view from one signed combined result.

    Geometry comes only from the exact workspace-area results bound by the
    combined request. Every technology at one resolution must carry the same
    support-domain GeoJSON; no catalog, region branch, or fallback is read.
    """

    presentation = _build_combined_result_presentation_unvalidated(
        combined_result,
        area_results,
    )
    validate_combined_result_presentation_from_result(
        presentation,
        combined_result,
        area_results,
    )
    return presentation


__all__ = [
    "COMBINED_PRESENTATION_CAPABILITY_ID",
    "COMBINED_PRESENTATION_SCHEMA_VERSION",
    "CombinedPresentationAreaBinding",
    "CombinedPresentationField",
    "CombinedPresentationMapLayer",
    "CombinedPresentationMetric",
    "CombinedPresentationTable",
    "CombinedResultPresentation",
    "build_combined_result_presentation",
    "build_combined_result_presentation_from_validated_inputs",
    "parse_combined_result_presentation",
    "validate_combined_result_presentation",
    "validate_combined_result_presentation_from_result",
]
