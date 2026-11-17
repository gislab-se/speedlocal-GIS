from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
import re
from typing import Any, Mapping

import h3

from .workspace_area import (
    WorkspaceAreaExecutionResult,
    validate_workspace_area_execution_result,
    workspace_analysis_request_signature,
)
from .workspace_buffer import (
    WorkspaceBufferPreviewResult,
    validate_workspace_buffer_preview_result,
)
from .workspace_request import (
    WorkspaceAnalysisRequest,
    parse_workspace_analysis_request,
)
from .workspace_view import AppliedWorkspaceSliceView


WORKSPACE_PRESENTATION_SCHEMA_VERSION = "1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DOMAIN_ROLES = {"standard_analysis", "eligible_support"}
_LAYER_ROLES = {"source", "buffer", "primary", "result"}
_GEOMETRY_MODES = {"embedded", "referenced", "unavailable"}
_VALUE_TYPES = {"string", "number", "boolean"}


JsonScalar = str | float | int | bool | None


@dataclass(frozen=True)
class WorkspacePresentationDomain:
    domain_id: str
    role: str
    resolution: int
    source_sha256: str
    cell_ids_sha256: str
    cell_count: int
    total_area_km2: float
    id_field: str
    area_field: str
    area_unit: str
    primary_layer_id: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain_id": self.domain_id,
            "role": self.role,
            "resolution": self.resolution,
            "source_sha256": self.source_sha256,
            "cell_ids_sha256": self.cell_ids_sha256,
            "cell_count": self.cell_count,
            "total_area_km2": self.total_area_km2,
            "id_field": self.id_field,
            "area_field": self.area_field,
            "area_unit": self.area_unit,
            "primary_layer_id": self.primary_layer_id,
        }


@dataclass(frozen=True)
class WorkspacePresentationLayerSpec:
    layer_id: str
    role: str
    label: str | None
    geometry_family: str | None
    processing_adapter: str | None
    result_semantics: str | None
    domain_id: str | None
    geometry_mode: str
    feature_collection_json: str | None
    geometry_reference_layer_id: str | None
    geometry_unavailable_reason: str | None
    source_layer_ids: tuple[str, ...]
    result_id: str | None
    preview_result_signature_sha256: str | None
    source_sha256: str | None
    cell_ids_sha256: str | None
    feature_count: int | None
    operation: str | None
    threshold_m: float | None
    color: str | None
    point_radius: int | None
    quality_flag: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "role": self.role,
            "label": self.label,
            "geometry_family": self.geometry_family,
            "processing_adapter": self.processing_adapter,
            "result_semantics": self.result_semantics,
            "domain_id": self.domain_id,
            "geometry_mode": self.geometry_mode,
            "feature_collection_json": self.feature_collection_json,
            "geometry_reference_layer_id": self.geometry_reference_layer_id,
            "geometry_unavailable_reason": self.geometry_unavailable_reason,
            "source_layer_ids": list(self.source_layer_ids),
            "result_id": self.result_id,
            "preview_result_signature_sha256": (
                self.preview_result_signature_sha256
            ),
            "source_sha256": self.source_sha256,
            "cell_ids_sha256": self.cell_ids_sha256,
            "feature_count": self.feature_count,
            "operation": self.operation,
            "threshold_m": self.threshold_m,
            "color": self.color,
            "point_radius": self.point_radius,
            "quality_flag": self.quality_flag,
        }


@dataclass(frozen=True)
class WorkspacePresentationField:
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
class WorkspacePresentationMetric:
    metric_id: str
    value: float
    unit: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "value": self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class WorkspacePresentationResult:
    result_id: str
    domain_id: str
    fields: tuple[WorkspacePresentationField, ...]
    rows: tuple[tuple[JsonScalar, ...], ...]
    metrics: tuple[WorkspacePresentationMetric, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "result_id": self.result_id,
            "domain_id": self.domain_id,
            "fields": [field.as_dict() for field in self.fields],
            "rows": [list(row) for row in self.rows],
            "metrics": [metric.as_dict() for metric in self.metrics],
        }


@dataclass(frozen=True)
class WorkspaceAnalysisPresentation:
    schema_version: str
    access_scope: str
    region_id: str
    analysis_id: str
    target_resolution: int
    request_signature_sha256: str
    request: WorkspaceAnalysisRequest
    area_capability_id: str | None
    area_result_signature_sha256: str | None
    buffer_result_signatures: tuple[tuple[str, str], ...]
    domains: tuple[WorkspacePresentationDomain, ...]
    layers: tuple[WorkspacePresentationLayerSpec, ...]
    results: tuple[WorkspacePresentationResult, ...]
    presentation_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "region_id": self.region_id,
            "analysis_id": self.analysis_id,
            "target_resolution": self.target_resolution,
            "request_signature_sha256": self.request_signature_sha256,
            "request": self.request.as_dict(),
            "area_capability_id": self.area_capability_id,
            "area_result_signature_sha256": self.area_result_signature_sha256,
            "buffer_result_signatures": [
                {
                    "group_id": group_id,
                    "result_signature_sha256": signature,
                }
                for group_id, signature in self.buffer_result_signatures
            ],
            "domains": [domain.as_dict() for domain in self.domains],
            "layers": [layer.as_dict() for layer in self.layers],
            "results": [result.as_dict() for result in self.results],
            "presentation_signature_sha256": (
                self.presentation_signature_sha256
            ),
        }


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _cell_ids_sha256(values: tuple[str, ...] | list[str]) -> str:
    return hashlib.sha256(
        "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    ).hexdigest()


def _exact_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be exact non-empty text")
    return value


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _exact_text(value, label)


def _digest(value: Any, label: str) -> str:
    text = _exact_text(value, label)
    if _SHA256.fullmatch(text) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _optional_digest(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _digest(value, label)


def _integer(value: Any, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < (1 if positive else 0):
        raise ValueError(f"{label} must be {'positive' if positive else 'non-negative'}")
    return value


def _optional_integer(value: Any, label: str) -> int | None:
    if value is None:
        return None
    return _integer(value, label)


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < (math.nextafter(0.0, 1.0) if positive else 0.0):
        raise ValueError(f"{label} must be finite and {'positive' if positive else 'non-negative'}")
    return result


def _optional_number(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number or null")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields do not match schema 1.0")


def _feature_collection(value: str, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be non-empty GeoJSON text")
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not GeoJSON") from exc
    if not isinstance(payload, Mapping) or payload.get("type") != "FeatureCollection":
        raise ValueError(f"{label} must be a FeatureCollection")
    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        raise ValueError(f"{label} features must be a list")
    features: list[Mapping[str, Any]] = []
    for index, item in enumerate(raw_features):
        feature = _mapping(item, f"{label} feature {index}")
        if feature.get("type") != "Feature" or not isinstance(
            feature.get("geometry"), Mapping
        ):
            raise ValueError(f"{label} feature {index} is invalid")
        features.append(feature)
    return tuple(features)


def _domain_geojson_evidence(
    value: str,
    *,
    resolution: int,
    id_field: str,
    area_field: str,
    area_unit: str,
) -> tuple[int, str, float]:
    cell_areas: dict[str, float] = {}
    for index, feature in enumerate(_feature_collection(value, "domain geometry")):
        properties = _mapping(
            feature.get("properties"), f"domain feature {index} properties"
        )
        cell_id = properties.get(id_field)
        if (
            not isinstance(cell_id, str)
            or not h3.is_valid_cell(cell_id)
            or h3.get_resolution(cell_id) != resolution
            or cell_id in cell_areas
        ):
            raise ValueError("Domain geometry has invalid or duplicate H3 ids")
        raw_area = properties.get(area_field)
        if isinstance(raw_area, bool) or not isinstance(raw_area, (int, float)):
            raise ValueError("Domain geometry has an invalid area value")
        area = float(raw_area)
        if area_unit == "m2":
            area /= 1_000_000.0
        elif area_unit != "km2":
            raise NotImplementedError(f"Unsupported domain area unit: {area_unit}")
        if not math.isfinite(area) or area <= 0.0:
            raise ValueError("Domain geometry has a non-positive area")
        cell_areas[cell_id] = area
    return (
        len(cell_areas),
        _cell_ids_sha256(list(cell_areas)),
        math.fsum(cell_areas.values()),
    )


def _presentation_signature_payload(
    presentation: WorkspaceAnalysisPresentation,
) -> dict[str, Any]:
    payload = presentation.as_dict()
    payload.pop("presentation_signature_sha256")
    return payload


def _validate_slice_view(view: AppliedWorkspaceSliceView) -> None:
    if not isinstance(view, AppliedWorkspaceSliceView):
        raise TypeError("slice_view must be an AppliedWorkspaceSliceView")
    request = parse_workspace_analysis_request(view.request.as_dict())
    if request != view.request:
        raise ValueError("Workspace slice request is not canonical")
    scope = request.access_scope.split(":", 1)
    if (
        len(scope) != 2
        or scope[0] not in {"product", "review"}
        or scope[1] != request.region_id
    ):
        raise ValueError("Workspace slice access scope is invalid")
    domain = view.domain
    if (
        domain.region_id != request.region_id
        or domain.analysis_id != request.analysis_id
        or domain.resolution != request.target_resolution
        or (domain.upstream_source_sha256 or domain.source_sha256) != request.domain_sha256
        or domain.cell_count <= 0
        or not math.isfinite(domain.total_area_km2)
        or domain.total_area_km2 <= 0.0
    ):
        raise ValueError("Workspace slice domain identity drifted from request")
    if domain.upstream_source_sha256 or domain.runtime_revision_sha256:
        _digest(domain.upstream_source_sha256, 'domain upstream sha256')
        _digest(domain.runtime_revision_sha256, 'domain runtime revision')
    domain_bytes = domain.feature_collection_json.encode("utf-8")
    if hashlib.sha256(domain_bytes).hexdigest() != domain.source_sha256:
        raise ValueError("Workspace slice domain bytes drifted")
    observed_count, observed_digest, observed_area = _domain_geojson_evidence(
        domain.feature_collection_json,
        resolution=domain.resolution,
        id_field=domain.id_field,
        area_field=domain.area_field,
        area_unit=domain.area_unit,
    )
    if (
        observed_count != domain.cell_count
        or observed_digest != domain.cell_ids_sha256
        or not math.isclose(
            observed_area,
            domain.total_area_km2,
            rel_tol=0.0,
            abs_tol=1e-6,
        )
    ):
        raise ValueError("Workspace slice domain evidence does not reconcile")

    requested_group_by_layer = {
        layer_id: group.group_id
        for group in request.groups
        for layer_id in group.layer_ids
    }
    if (
        not isinstance(view.sources, tuple)
        or tuple(source.layer_id for source in view.sources)
        != request.selected_layer_ids
    ):
        raise ValueError("Workspace slice sources drifted from request")
    for source in view.sources:
        if source.group_id != requested_group_by_layer[source.layer_id]:
            raise ValueError("Workspace source group drifted from request")
        source_bytes = source.feature_collection_json.encode("utf-8")
        if (
            hashlib.sha256(source_bytes).hexdigest() != source.source_sha256
            or len(source_bytes) != source.byte_count
            or len(
                _feature_collection(
                    source.feature_collection_json,
                    f"source {source.layer_id}",
                )
            )
            != source.display_feature_count
            or source.declared_feature_count <= 0
            or source.display_feature_count <= 0
            or source.point_radius <= 0
        ):
            raise ValueError(f"Workspace source {source.layer_id} drifted")

    result = view.result
    if (
        result.region_id != request.region_id
        or result.analysis_id != request.analysis_id
        or tuple(layer.layer_id for layer in result.layers)
        != request.selected_layer_ids
        or tuple(group.group_id for group in result.groups)
        != tuple(group.group_id for group in request.groups)
        or tuple(group.group_id for group in view.groups)
        != tuple(group.group_id for group in request.groups)
    ):
        raise ValueError("Workspace slice result identity drifted from request")
    layer_results = {layer.layer_id: layer for layer in result.layers}
    group_results = {group.group_id: group for group in result.groups}
    expected_domain_ids = tuple(
        sorted(
            str(feature["properties"][domain.id_field])
            for feature in _feature_collection(
                domain.feature_collection_json,
                "standard domain",
            )
        )
    )
    for group_view, group_request in zip(view.groups, request.groups, strict=True):
        group_result = group_results[group_request.group_id]
        operations = {
            layer_results[layer_id].operation for layer_id in group_request.layer_ids
        }
        if len(operations) != 1:
            raise ValueError("Workspace result group mixes operations")
        operation = next(iter(operations))
        semantics = (
            "blocked_means_outside_required_proximity"
            if operation == "proximity_feasibility"
            else "blocked_means_excluded"
            if operation in {"distance_exclusion", "hard_exclusion"}
            else None
        )
        cell_ids = tuple(cell.cell_id for cell in group_result.cells)
        blocked = sum(int(cell.blocked) for cell in group_result.cells)
        missing = sum(int(cell.coverage_missing) for cell in group_result.cells)
        mean_acceptance = math.fsum(
            cell.acceptance for cell in group_result.cells
        ) / len(group_result.cells)
        if any(
            (
                not isinstance(cell.blocked, bool)
                or not isinstance(cell.any_intersection, bool)
                or not isinstance(cell.coverage_missing, bool)
                or not math.isfinite(cell.acceptance)
                or cell.acceptance < 0.0
                or cell.acceptance > 1.0
                or (
                    cell.min_distance_m is not None
                    and (
                        not math.isfinite(cell.min_distance_m)
                        or cell.min_distance_m < 0.0
                    )
                )
            )
            for cell in group_result.cells
        ):
            raise ValueError("Workspace result contains invalid cell values")
        if (
            semantics is None
            or group_result.layer_ids != group_request.layer_ids
            or cell_ids != expected_domain_ids
            or group_result.cell_count != domain.cell_count
            or group_result.blocked_cell_count != blocked
            or not math.isclose(
                group_result.mean_acceptance,
                mean_acceptance,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            or group_view.group_id != group_result.group_id
            or group_view.operation != operation
            or group_view.result_semantics != semantics
            or group_view.layer_ids != group_result.layer_ids
            or group_view.threshold_m != group_result.threshold_m
            or group_view.cell_count != group_result.cell_count
            or group_view.blocked_cell_count != blocked
            or group_view.accepted_cell_count != group_result.cell_count - blocked
            or group_view.coverage_missing_cell_count != missing
            or not math.isclose(
                group_view.mean_acceptance,
                mean_acceptance,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            raise ValueError("Workspace group result view does not reconcile")


_STANDARD_RESULT_FIELDS = (
    WorkspacePresentationField("cell_id", "string", None, False),
    WorkspacePresentationField("min_distance_m", "number", "m", True),
    WorkspacePresentationField("any_intersection", "boolean", None, False),
    WorkspacePresentationField("blocked", "boolean", None, False),
    WorkspacePresentationField("acceptance", "number", "ratio", False),
    WorkspacePresentationField("coverage_missing", "boolean", None, False),
)
_AREA_RESULT_FIELDS = (
    WorkspacePresentationField("cell_id", "string", None, False),
    WorkspacePresentationField("model_area_km2", "number", "km2", False),
    WorkspacePresentationField("remaining_area_km2", "number", "km2", False),
    WorkspacePresentationField("potential_pct", "number", "percent", False),
)


def _metric(metric_id: str, value: int | float, unit: str) -> WorkspacePresentationMetric:
    return WorkspacePresentationMetric(metric_id, float(value), unit)


def _preview_geometry_family(geometry_type: str) -> str:
    normalized = str(geometry_type)
    if "Polygon" in normalized:
        return "polygon"
    if "LineString" in normalized:
        return "line"
    if "Point" in normalized:
        return "point"
    raise NotImplementedError(
        f"Unsupported workspace preview geometry type: {geometry_type}"
    )


def build_workspace_analysis_presentation(
    slice_view: AppliedWorkspaceSliceView,
    area_result: WorkspaceAreaExecutionResult | None = None,
    buffer_previews: tuple[WorkspaceBufferPreviewResult, ...] = (),
) -> WorkspaceAnalysisPresentation:
    """Build one renderer-neutral map/result model from an applied request.

    The standard analysis domain remains the source/buffer-preview domain. An
    optional exact-area capability adds a second eligible-support domain; it
    never replaces or borrows geometry from the standard domain.
    """

    _validate_slice_view(slice_view)
    request = slice_view.request
    request_signature = workspace_analysis_request_signature(request)
    if not isinstance(buffer_previews, tuple):
        raise TypeError("buffer_previews must be an immutable tuple")
    if tuple(preview.group_id for preview in buffer_previews) != tuple(
        group.group_id for group in slice_view.groups
    ):
        raise ValueError(
            "Workspace presentation requires one ordered preview per applied group"
        )
    slice_sources = {source.layer_id: source for source in slice_view.sources}
    preview_by_group: dict[str, WorkspaceBufferPreviewResult] = {}
    for preview in buffer_previews:
        validate_workspace_buffer_preview_result(preview)
        group = next(
            value for value in slice_view.groups if value.group_id == preview.group_id
        )
        if (
            preview.request.applied_request != request
            or preview.request.applied_request_signature_sha256
            != request_signature
            or preview.access_scope != request.access_scope
            or preview.region_id != request.region_id
            or preview.analysis_id != request.analysis_id
            or preview.layer_ids != group.layer_ids
            or preview.operation != group.operation
            or preview.buffer_m != group.threshold_m
            or tuple(source.layer_id for source in preview.request.sources)
            != group.layer_ids
            or any(
                source.source_sha256
                != slice_sources[source.layer_id].source_sha256
                or source.source_bytes
                != slice_sources[source.layer_id].byte_count
                or source.geometry_family
                != slice_sources[source.layer_id].geometry_family
                or source.processing_adapter
                != slice_sources[source.layer_id].processing_adapter
                for source in preview.request.sources
            )
        ):
            raise ValueError(
                "Workspace buffer preview does not match the applied slice"
            )
        preview_by_group[preview.group_id] = preview
    if area_result is not None:
        validate_workspace_area_execution_result(area_result)
        if (
            area_result.request != request
            or area_result.request_signature_sha256 != request_signature
            or area_result.access_scope != request.access_scope
            or area_result.region_id != request.region_id
            or area_result.analysis_id != request.analysis_id
            or area_result.target_resolution != request.target_resolution
        ):
            raise ValueError(
                "Workspace area capability does not match the applied slice request"
            )

    standard_domain_id = (
        f"standard:{request.analysis_id}:r{request.target_resolution}"
    )
    standard_primary_id = "primary:standard"
    domains: list[WorkspacePresentationDomain] = [
        WorkspacePresentationDomain(
            domain_id=standard_domain_id,
            role="standard_analysis",
            resolution=request.target_resolution,
            source_sha256=slice_view.domain.source_sha256,
            cell_ids_sha256=slice_view.domain.cell_ids_sha256,
            cell_count=slice_view.domain.cell_count,
            total_area_km2=slice_view.domain.total_area_km2,
            id_field=slice_view.domain.id_field,
            area_field=slice_view.domain.area_field,
            area_unit=slice_view.domain.area_unit,
            primary_layer_id=standard_primary_id,
        )
    ]
    layers: list[WorkspacePresentationLayerSpec] = [
        WorkspacePresentationLayerSpec(
            layer_id=standard_primary_id,
            role="primary",
            label=None,
            geometry_family="polygon",
            processing_adapter=None,
            result_semantics=None,
            domain_id=standard_domain_id,
            geometry_mode="embedded",
            feature_collection_json=slice_view.domain.feature_collection_json,
            geometry_reference_layer_id=None,
            geometry_unavailable_reason=None,
            source_layer_ids=(),
            result_id=None,
            preview_result_signature_sha256=None,
            source_sha256=slice_view.domain.source_sha256,
            cell_ids_sha256=slice_view.domain.cell_ids_sha256,
            feature_count=slice_view.domain.cell_count,
            operation=None,
            threshold_m=None,
            color=None,
            point_radius=None,
            quality_flag=None,
        )
    ]
    for source in slice_view.sources:
        layers.append(
            WorkspacePresentationLayerSpec(
                layer_id=f"source:{source.layer_id}",
                role="source",
                label=source.label,
                geometry_family=source.geometry_family,
                processing_adapter=source.processing_adapter,
                result_semantics=None,
                domain_id=None,
                geometry_mode="embedded",
                feature_collection_json=source.feature_collection_json,
                geometry_reference_layer_id=None,
                geometry_unavailable_reason=None,
                source_layer_ids=(),
                result_id=None,
                preview_result_signature_sha256=None,
                source_sha256=source.source_sha256,
                cell_ids_sha256=None,
                feature_count=source.display_feature_count,
                operation=None,
                threshold_m=None,
                color=source.source_color,
                point_radius=source.point_radius,
                quality_flag=source.quality_flag,
            )
        )

    results: list[WorkspacePresentationResult] = []
    result_groups = {group.group_id: group for group in slice_view.result.groups}
    for group in slice_view.groups:
        buffer_preview = preview_by_group[group.group_id]
        source_layer_ids = tuple(
            f"source:{layer_id}" for layer_id in group.layer_ids
        )
        layers.append(
            WorkspacePresentationLayerSpec(
                layer_id=f"buffer:{group.group_id}",
                role="buffer",
                label=f"{group.label} · buffert",
                geometry_family=_preview_geometry_family(
                    buffer_preview.geometry_type
                ),
                processing_adapter=None,
                result_semantics=group.result_semantics,
                domain_id=None,
                geometry_mode="embedded",
                feature_collection_json=(
                    buffer_preview.feature_collection_json
                ),
                geometry_reference_layer_id=None,
                geometry_unavailable_reason=None,
                source_layer_ids=source_layer_ids,
                result_id=None,
                preview_result_signature_sha256=(
                    buffer_preview.result_signature_sha256
                ),
                source_sha256=buffer_preview.feature_collection_sha256,
                cell_ids_sha256=None,
                feature_count=buffer_preview.feature_count,
                operation=group.operation,
                threshold_m=group.threshold_m,
                color=None,
                point_radius=None,
                quality_flag=None,
            )
        )
        result_id = f"group:{group.group_id}"
        layers.append(
            WorkspacePresentationLayerSpec(
                layer_id=f"result:{group.group_id}",
                role="result",
                label=f"{group.label} · resultat",
                geometry_family="polygon",
                processing_adapter=None,
                result_semantics=group.result_semantics,
                domain_id=standard_domain_id,
                geometry_mode="referenced",
                feature_collection_json=None,
                geometry_reference_layer_id=standard_primary_id,
                geometry_unavailable_reason=None,
                source_layer_ids=(f"buffer:{group.group_id}",),
                result_id=result_id,
                preview_result_signature_sha256=None,
                source_sha256=None,
                cell_ids_sha256=slice_view.domain.cell_ids_sha256,
                feature_count=slice_view.domain.cell_count,
                operation=group.operation,
                threshold_m=group.threshold_m,
                color=None,
                point_radius=None,
                quality_flag=None,
            )
        )
        engine_group = result_groups[group.group_id]
        results.append(
            WorkspacePresentationResult(
                result_id=result_id,
                domain_id=standard_domain_id,
                fields=_STANDARD_RESULT_FIELDS,
                rows=tuple(
                    (
                        cell.cell_id,
                        cell.min_distance_m,
                        cell.any_intersection,
                        cell.blocked,
                        cell.acceptance,
                        cell.coverage_missing,
                    )
                    for cell in engine_group.cells
                ),
                metrics=(
                    _metric("cell_count", group.cell_count, "count"),
                    _metric(
                        "blocked_cell_count", group.blocked_cell_count, "count"
                    ),
                    _metric(
                        "accepted_cell_count", group.accepted_cell_count, "count"
                    ),
                    _metric(
                        "coverage_missing_cell_count",
                        group.coverage_missing_cell_count,
                        "count",
                    ),
                    _metric("mean_acceptance", group.mean_acceptance, "ratio"),
                    _metric("threshold_m", group.threshold_m, "m"),
                ),
            )
        )

    area_capability_id: str | None = None
    area_result_signature: str | None = None
    if area_result is not None:
        area_capability_id = area_result.capability_id
        area_result_signature = area_result.result_signature_sha256
        support_domain_id = (
            f"support:{area_result.support_domain_id}:"
            f"r{area_result.target_resolution}"
        )
        support_primary_id = "primary:area"
        domains.append(
            WorkspacePresentationDomain(
                domain_id=support_domain_id,
                role="eligible_support",
                resolution=area_result.target_resolution,
                source_sha256=area_result.surface_artifact_sha256,
                cell_ids_sha256=area_result.cell_ids_sha256,
                cell_count=area_result.cell_count,
                total_area_km2=area_result.model_area_km2,
                id_field=area_result.surface_id_field,
                area_field=area_result.surface_area_field,
                area_unit=area_result.surface_area_unit,
                primary_layer_id=support_primary_id,
            )
        )
        layers.extend(
            (
                WorkspacePresentationLayerSpec(
                    layer_id=support_primary_id,
                    role="primary",
                    label=None,
                    geometry_family="polygon",
                    processing_adapter=None,
                    result_semantics=None,
                    domain_id=support_domain_id,
                    geometry_mode="embedded",
                    feature_collection_json=(
                        area_result.surface_feature_collection_json
                    ),
                    geometry_reference_layer_id=None,
                    geometry_unavailable_reason=None,
                    source_layer_ids=(),
                    result_id=None,
                    preview_result_signature_sha256=None,
                    source_sha256=area_result.surface_artifact_sha256,
                    cell_ids_sha256=area_result.cell_ids_sha256,
                    feature_count=area_result.cell_count,
                    operation=None,
                    threshold_m=None,
                    color=None,
                    point_radius=None,
                    quality_flag=None,
                ),
                WorkspacePresentationLayerSpec(
                    layer_id="result:area",
                    role="result",
                    label=None,
                    geometry_family="polygon",
                    processing_adapter=None,
                    result_semantics="remaining_over_eligible_surface",
                    domain_id=support_domain_id,
                    geometry_mode="referenced",
                    feature_collection_json=None,
                    geometry_reference_layer_id=support_primary_id,
                    geometry_unavailable_reason=None,
                    source_layer_ids=(),
                    result_id=area_capability_id,
                    preview_result_signature_sha256=None,
                    source_sha256=None,
                    cell_ids_sha256=area_result.cell_ids_sha256,
                    feature_count=area_result.cell_count,
                    operation="eligible_surface_area",
                    threshold_m=None,
                    color=None,
                    point_radius=None,
                    quality_flag=None,
                ),
            )
        )
        results.append(
            WorkspacePresentationResult(
                result_id=area_capability_id,
                domain_id=support_domain_id,
                fields=_AREA_RESULT_FIELDS,
                rows=tuple(
                    (
                        cell.cell_id,
                        cell.model_area_km2,
                        cell.remaining_area_km2,
                        cell.potential_pct,
                    )
                    for cell in area_result.cells
                ),
                metrics=(
                    _metric("cell_count", area_result.cell_count, "count"),
                    _metric("model_area_km2", area_result.model_area_km2, "km2"),
                    _metric(
                        "remaining_area_km2",
                        area_result.remaining_area_km2,
                        "km2",
                    ),
                    _metric("potential_pct", area_result.potential_pct, "percent"),
                ),
            )
        )

    presentation = WorkspaceAnalysisPresentation(
        schema_version=WORKSPACE_PRESENTATION_SCHEMA_VERSION,
        access_scope=request.access_scope,
        region_id=request.region_id,
        analysis_id=request.analysis_id,
        target_resolution=request.target_resolution,
        request_signature_sha256=request_signature,
        request=request,
        area_capability_id=area_capability_id,
        area_result_signature_sha256=area_result_signature,
        buffer_result_signatures=tuple(
            (preview.group_id, preview.result_signature_sha256)
            for preview in buffer_previews
        ),
        domains=tuple(domains),
        layers=tuple(layers),
        results=tuple(results),
        presentation_signature_sha256="0" * 64,
    )
    presentation = replace(
        presentation,
        presentation_signature_sha256=_canonical_sha256(
            _presentation_signature_payload(presentation)
        ),
    )
    validate_workspace_analysis_presentation(presentation)
    return presentation


def _metric_map(
    result: WorkspacePresentationResult,
) -> dict[str, float]:
    return {metric.metric_id: metric.value for metric in result.metrics}


def _validate_result_rows(
    result: WorkspacePresentationResult,
    domain: WorkspacePresentationDomain,
) -> None:
    if (
        not isinstance(result.fields, tuple)
        or not result.fields
        or not isinstance(result.rows, tuple)
        or not isinstance(result.metrics, tuple)
    ):
        raise TypeError("Presentation result collections must be immutable tuples")
    field_ids = tuple(field.field_id for field in result.fields)
    if len(field_ids) != len(set(field_ids)) or field_ids[0] != "cell_id":
        raise ValueError("Presentation result fields must be unique and cell keyed")
    for field in result.fields:
        _exact_text(field.field_id, "presentation field id")
        if field.value_type not in _VALUE_TYPES:
            raise NotImplementedError(
                f"Unsupported presentation value type: {field.value_type}"
            )
        _optional_text(field.unit, "presentation field unit")
        if not isinstance(field.nullable, bool):
            raise TypeError("Presentation field nullable must be boolean")
    cell_ids: list[str] = []
    for row_index, row in enumerate(result.rows):
        if not isinstance(row, tuple) or len(row) != len(result.fields):
            raise ValueError("Presentation result row width drifted from schema")
        for field, value in zip(result.fields, row, strict=True):
            if value is None:
                if not field.nullable:
                    raise ValueError(
                        f"Presentation row {row_index}/{field.field_id} is null"
                    )
                continue
            if field.value_type == "string":
                _exact_text(value, f"presentation row {field.field_id}")
            elif field.value_type == "boolean":
                if not isinstance(value, bool):
                    raise TypeError(
                        f"Presentation row {field.field_id} must be boolean"
                    )
            elif (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
            ):
                raise TypeError(
                    f"Presentation row {field.field_id} must be finite number"
                )
        cell_ids.append(str(row[0]))
    if (
        tuple(cell_ids) != tuple(sorted(cell_ids))
        or len(cell_ids) != len(set(cell_ids))
        or len(cell_ids) != domain.cell_count
        or _cell_ids_sha256(cell_ids) != domain.cell_ids_sha256
    ):
        raise ValueError("Presentation result rows drifted from their domain")
    metric_ids = tuple(metric.metric_id for metric in result.metrics)
    if len(metric_ids) != len(set(metric_ids)):
        raise ValueError("Presentation result metrics must be unique")
    for metric in result.metrics:
        _exact_text(metric.metric_id, "presentation metric id")
        _exact_text(metric.unit, "presentation metric unit")
        _number(metric.value, f"presentation metric {metric.metric_id}")

    metrics = _metric_map(result)
    if domain.role == "standard_analysis":
        if result.fields != _STANDARD_RESULT_FIELDS or set(metrics) != {
            "cell_count",
            "blocked_cell_count",
            "accepted_cell_count",
            "coverage_missing_cell_count",
            "mean_acceptance",
            "threshold_m",
        }:
            raise ValueError("Standard presentation result schema drifted")
        blocked = sum(int(bool(row[3])) for row in result.rows)
        missing = sum(int(bool(row[5])) for row in result.rows)
        mean_acceptance = math.fsum(float(row[4]) for row in result.rows) / len(
            result.rows
        )
        if any(
            (
                row[1] is not None and float(row[1]) < 0.0
            )
            or float(row[4]) < 0.0
            or float(row[4]) > 1.0
            for row in result.rows
        ) or (
            metrics["cell_count"] != float(domain.cell_count)
            or metrics["blocked_cell_count"] != float(blocked)
            or metrics["accepted_cell_count"]
            != float(domain.cell_count - blocked)
            or metrics["coverage_missing_cell_count"] != float(missing)
            or not math.isclose(
                metrics["mean_acceptance"],
                mean_acceptance,
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            raise ValueError("Standard presentation metrics do not reconcile")
    elif domain.role == "eligible_support":
        if result.fields != _AREA_RESULT_FIELDS or set(metrics) != {
            "cell_count",
            "model_area_km2",
            "remaining_area_km2",
            "potential_pct",
        }:
            raise ValueError("Area presentation result schema drifted")
        model_total = math.fsum(float(row[1]) for row in result.rows)
        remaining_total = math.fsum(float(row[2]) for row in result.rows)
        if any(
            float(row[1]) <= 0.0
            or float(row[2]) < 0.0
            or float(row[2]) > float(row[1])
            or float(row[3]) < 0.0
            or float(row[3]) > 100.0
            or not math.isclose(
                float(row[3]),
                float(row[2]) / float(row[1]) * 100.0,
                rel_tol=0.0,
                abs_tol=1e-10,
            )
            for row in result.rows
        ):
            raise ValueError("Area presentation cells do not reconcile")
        potential_pct = remaining_total / model_total * 100.0
        if (
            metrics["cell_count"] != float(domain.cell_count)
            or not math.isclose(
                metrics["model_area_km2"],
                model_total,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            or not math.isclose(
                metrics["remaining_area_km2"],
                remaining_total,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            or not math.isclose(
                metrics["potential_pct"],
                potential_pct,
                rel_tol=0.0,
                abs_tol=1e-10,
            )
        ):
            raise ValueError("Area presentation metrics do not reconcile")


def validate_workspace_analysis_presentation(
    presentation: WorkspaceAnalysisPresentation,
) -> None:
    if not isinstance(presentation, WorkspaceAnalysisPresentation):
        raise TypeError("presentation must be a WorkspaceAnalysisPresentation")
    if presentation.schema_version != WORKSPACE_PRESENTATION_SCHEMA_VERSION:
        raise NotImplementedError(
            f"Unsupported workspace presentation schema: {presentation.schema_version}"
        )
    request = parse_workspace_analysis_request(presentation.request.as_dict())
    request_signature = workspace_analysis_request_signature(request)
    if (
        presentation.access_scope != request.access_scope
        or presentation.region_id != request.region_id
        or presentation.analysis_id != request.analysis_id
        or presentation.target_resolution != request.target_resolution
        or presentation.request_signature_sha256 != request_signature
    ):
        raise ValueError("Workspace presentation identity drifted from request")
    if (
        not isinstance(presentation.domains, tuple)
        or not isinstance(presentation.layers, tuple)
        or not isinstance(presentation.results, tuple)
        or not isinstance(presentation.buffer_result_signatures, tuple)
    ):
        raise TypeError("Workspace presentation collections must be tuples")
    if tuple(group_id for group_id, _signature in presentation.buffer_result_signatures) != tuple(
        group.group_id for group in request.groups
    ):
        raise ValueError("Workspace presentation buffer identities drifted")
    for group_id, signature in presentation.buffer_result_signatures:
        _exact_text(group_id, "presentation buffer group id")
        _digest(signature, "presentation buffer result signature")
    expected_roles = (
        ("standard_analysis", "eligible_support")
        if presentation.area_capability_id is not None
        else ("standard_analysis",)
    )
    if tuple(domain.role for domain in presentation.domains) != expected_roles:
        raise ValueError("Workspace presentation domain roles drifted")
    if (presentation.area_capability_id is None) != (
        presentation.area_result_signature_sha256 is None
    ):
        raise ValueError("Workspace presentation area identity is incomplete")
    if presentation.area_capability_id is not None:
        _exact_text(presentation.area_capability_id, "area capability id")
        _digest(
            presentation.area_result_signature_sha256,
            "area result signature",
        )

    domains: dict[str, WorkspacePresentationDomain] = {}
    for domain in presentation.domains:
        if not isinstance(domain, WorkspacePresentationDomain):
            raise TypeError("Workspace presentation domain type is invalid")
        _exact_text(domain.domain_id, "presentation domain id")
        if domain.domain_id in domains or domain.role not in _DOMAIN_ROLES:
            raise ValueError("Workspace presentation domain identity is invalid")
        domains[domain.domain_id] = domain
        _integer(domain.resolution, "presentation domain resolution")
        _digest(domain.source_sha256, "presentation domain source sha256")
        _digest(domain.cell_ids_sha256, "presentation domain cell digest")
        _integer(domain.cell_count, "presentation domain cell count", positive=True)
        _number(domain.total_area_km2, "presentation domain area", positive=True)
        _exact_text(domain.id_field, "presentation domain id field")
        _exact_text(domain.area_field, "presentation domain area field")
        _exact_text(domain.area_unit, "presentation domain area unit")
        _exact_text(domain.primary_layer_id, "presentation primary layer id")
        if domain.resolution != request.target_resolution:
            raise ValueError("Presentation domain resolution drifted from request")

    layer_by_id: dict[str, WorkspacePresentationLayerSpec] = {}
    for layer in presentation.layers:
        if not isinstance(layer, WorkspacePresentationLayerSpec):
            raise TypeError("Workspace presentation layer type is invalid")
        _exact_text(layer.layer_id, "presentation layer id")
        if layer.layer_id in layer_by_id or layer.role not in _LAYER_ROLES:
            raise ValueError("Workspace presentation layer identity is invalid")
        layer_by_id[layer.layer_id] = layer
        _optional_text(layer.label, "presentation layer label")
        _optional_text(
            layer.geometry_family, "presentation layer geometry family"
        )
        _optional_text(
            layer.processing_adapter, "presentation processing adapter"
        )
        _optional_text(
            layer.result_semantics, "presentation result semantics"
        )
        if layer.geometry_mode not in _GEOMETRY_MODES:
            raise NotImplementedError(
                f"Unsupported presentation geometry mode: {layer.geometry_mode}"
            )
        if layer.domain_id is not None and layer.domain_id not in domains:
            raise ValueError("Presentation layer references an unknown domain")
        if not isinstance(layer.source_layer_ids, tuple) or len(
            layer.source_layer_ids
        ) != len(set(layer.source_layer_ids)):
            raise ValueError("Presentation source-layer references are invalid")
        _optional_text(layer.result_id, "presentation layer result id")
        _optional_digest(
            layer.preview_result_signature_sha256,
            "presentation preview result signature",
        )
        _optional_digest(layer.source_sha256, "presentation layer source sha256")
        _optional_digest(layer.cell_ids_sha256, "presentation layer cell digest")
        _optional_integer(layer.feature_count, "presentation layer feature count")
        _optional_text(layer.operation, "presentation layer operation")
        threshold = _optional_number(layer.threshold_m, "presentation threshold")
        if threshold is not None and threshold < 0.0:
            raise ValueError("Presentation layer threshold must be non-negative")
        _optional_text(layer.color, "presentation layer color")
        point_radius = _optional_integer(
            layer.point_radius, "presentation point radius"
        )
        if point_radius is not None and point_radius <= 0:
            raise ValueError("Presentation point radius must be positive")
        _optional_text(layer.quality_flag, "presentation quality flag")
        if layer.role == "source" and (
            layer.label is None
            or layer.geometry_family is None
            or layer.processing_adapter is None
            or layer.domain_id is not None
        ):
            raise ValueError("Presentation source layer metadata is incomplete")
        if layer.role == "primary" and layer.geometry_family != "polygon":
            raise ValueError("Presentation primary layer must be polygon geometry")
        if layer.role == "buffer" and (
            layer.geometry_family not in {"point", "line", "polygon"}
            or layer.result_semantics is None
            or layer.preview_result_signature_sha256 is None
        ):
            raise ValueError("Presentation buffer layer metadata is incomplete")
        if layer.role == "result" and (
            layer.geometry_family != "polygon"
            or layer.result_semantics is None
            or layer.preview_result_signature_sha256 is not None
        ):
            raise ValueError("Presentation derived layer semantics are incomplete")
        if layer.role != "buffer" and layer.preview_result_signature_sha256 is not None:
            raise ValueError("Only a buffer layer may bind a preview result")
        if layer.geometry_mode == "embedded":
            if (
                layer.feature_collection_json is None
                or layer.geometry_reference_layer_id is not None
                or layer.geometry_unavailable_reason is not None
                or layer.source_sha256 is None
                or layer.feature_count is None
            ):
                raise ValueError("Embedded presentation geometry is incomplete")
            features = _feature_collection(
                layer.feature_collection_json,
                f"presentation layer {layer.layer_id}",
            )
            if (
                len(features) != layer.feature_count
                or hashlib.sha256(
                    layer.feature_collection_json.encode("utf-8")
                ).hexdigest()
                != layer.source_sha256
            ):
                raise ValueError("Embedded presentation geometry drifted")
        elif layer.geometry_mode == "referenced":
            if (
                layer.feature_collection_json is not None
                or layer.geometry_reference_layer_id is None
                or layer.geometry_unavailable_reason is not None
            ):
                raise ValueError("Referenced presentation geometry is incomplete")
        elif (
            layer.feature_collection_json is not None
            or layer.geometry_reference_layer_id is not None
            or layer.geometry_unavailable_reason is None
        ):
            raise ValueError("Unavailable presentation geometry is incomplete")

    for layer in presentation.layers:
        for source_layer_id in layer.source_layer_ids:
            if source_layer_id not in layer_by_id:
                raise ValueError("Presentation layer references an unknown source")
        if layer.geometry_reference_layer_id is not None:
            referenced = layer_by_id.get(layer.geometry_reference_layer_id)
            if (
                referenced is None
                or referenced.geometry_mode != "embedded"
                or referenced.domain_id != layer.domain_id
            ):
                raise ValueError("Presentation geometry reference is invalid")

    for domain in presentation.domains:
        primary = layer_by_id.get(domain.primary_layer_id)
        if (
            primary is None
            or primary.role != "primary"
            or primary.domain_id != domain.domain_id
            or primary.geometry_mode != "embedded"
            or primary.source_sha256 != domain.source_sha256
            or primary.cell_ids_sha256 != domain.cell_ids_sha256
            or primary.feature_count != domain.cell_count
        ):
            raise ValueError("Presentation domain primary layer drifted")
        observed_count, observed_digest, observed_area = _domain_geojson_evidence(
            primary.feature_collection_json or "",
            resolution=domain.resolution,
            id_field=domain.id_field,
            area_field=domain.area_field,
            area_unit=domain.area_unit,
        )
        if (
            observed_count != domain.cell_count
            or observed_digest != domain.cell_ids_sha256
            or not math.isclose(
                observed_area,
                domain.total_area_km2,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
        ):
            raise ValueError("Presentation primary geometry drifted from domain")

    standard_domain = presentation.domains[0]
    expected_standard_result_ids = tuple(
        f"group:{group.group_id}" for group in request.groups
    )
    expected_result_ids = expected_standard_result_ids + (
        (presentation.area_capability_id,)
        if presentation.area_capability_id is not None
        else ()
    )
    if tuple(result.result_id for result in presentation.results) != expected_result_ids:
        raise ValueError("Presentation result order drifted from request")
    result_by_id: dict[str, WorkspacePresentationResult] = {}
    for result in presentation.results:
        if not isinstance(result, WorkspacePresentationResult):
            raise TypeError("Presentation result type is invalid")
        if result.result_id in result_by_id or result.domain_id not in domains:
            raise ValueError("Presentation result identity is invalid")
        result_by_id[result.result_id] = result
        _validate_result_rows(result, domains[result.domain_id])
    if any(
        result_by_id[result_id].domain_id != standard_domain.domain_id
        for result_id in expected_standard_result_ids
    ):
        raise ValueError("Standard results escaped the standard domain")
    if presentation.area_capability_id is not None:
        support_domain = presentation.domains[1]
        if (
            support_domain.domain_id == standard_domain.domain_id
            or support_domain.primary_layer_id == standard_domain.primary_layer_id
            or result_by_id[presentation.area_capability_id].domain_id
            != support_domain.domain_id
        ):
            raise ValueError("Area result did not retain its support domain")

    result_layers = tuple(
        layer for layer in presentation.layers if layer.role == "result"
    )
    if (
        tuple(layer.result_id for layer in result_layers) != expected_result_ids
        or any(
            layer.result_id not in result_by_id
            or layer.domain_id != result_by_id[layer.result_id].domain_id
            or layer.geometry_mode != "referenced"
            for layer in result_layers
        )
    ):
        raise ValueError("Presentation result layers drifted from result schema")
    source_ids = {f"source:{layer_id}" for layer_id in request.selected_layer_ids}
    if {
        layer.layer_id for layer in presentation.layers if layer.role == "source"
    } != source_ids:
        raise ValueError("Presentation source layers drifted from request")
    buffer_layers = tuple(
        layer for layer in presentation.layers if layer.role == "buffer"
    )
    buffer_signatures = dict(presentation.buffer_result_signatures)
    if tuple(layer.layer_id for layer in buffer_layers) != tuple(
        f"buffer:{group.group_id}" for group in request.groups
    ) or any(
        layer.geometry_mode != "embedded"
        or layer.geometry_unavailable_reason is not None
        or layer.preview_result_signature_sha256
        != buffer_signatures[layer.layer_id.removeprefix("buffer:")]
        for layer in buffer_layers
    ):
        raise ValueError("Presentation buffer geometry identity drifted")

    expected_signature = _canonical_sha256(
        _presentation_signature_payload(presentation)
    )
    if presentation.presentation_signature_sha256 != expected_signature:
        raise ValueError("Workspace presentation signature does not match")


def validate_workspace_analysis_presentation_inputs(
    presentation: WorkspaceAnalysisPresentation,
    slice_view: AppliedWorkspaceSliceView,
    area_result: WorkspaceAreaExecutionResult | None = None,
    buffer_previews: tuple[WorkspaceBufferPreviewResult, ...] = (),
) -> None:
    validate_workspace_analysis_presentation(presentation)
    rebuilt = build_workspace_analysis_presentation(
        slice_view,
        area_result,
        buffer_previews,
    )
    if rebuilt != presentation:
        raise ValueError("Workspace presentation drifted from its typed inputs")


_DOMAIN_KEYS = {
    "domain_id",
    "role",
    "resolution",
    "source_sha256",
    "cell_ids_sha256",
    "cell_count",
    "total_area_km2",
    "id_field",
    "area_field",
    "area_unit",
    "primary_layer_id",
}
_LAYER_KEYS = {
    "layer_id",
    "role",
    "label",
    "geometry_family",
    "processing_adapter",
    "result_semantics",
    "domain_id",
    "geometry_mode",
    "feature_collection_json",
    "geometry_reference_layer_id",
    "geometry_unavailable_reason",
    "source_layer_ids",
    "result_id",
    "preview_result_signature_sha256",
    "source_sha256",
    "cell_ids_sha256",
    "feature_count",
    "operation",
    "threshold_m",
    "color",
    "point_radius",
    "quality_flag",
}
_FIELD_KEYS = {"field_id", "value_type", "unit", "nullable"}
_METRIC_KEYS = {"metric_id", "value", "unit"}
_RESULT_KEYS = {"result_id", "domain_id", "fields", "rows", "metrics"}
_BUFFER_SIGNATURE_KEYS = {"group_id", "result_signature_sha256"}
_PRESENTATION_KEYS = {
    "schema_version",
    "access_scope",
    "region_id",
    "analysis_id",
    "target_resolution",
    "request_signature_sha256",
    "request",
    "area_capability_id",
    "area_result_signature_sha256",
    "buffer_result_signatures",
    "domains",
    "layers",
    "results",
    "presentation_signature_sha256",
}


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    result = tuple(_exact_text(item, f"{label} item") for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must be unique")
    return result


def _parse_domain(value: Any) -> WorkspacePresentationDomain:
    raw = _mapping(value, "presentation domain")
    _keys(raw, _DOMAIN_KEYS, "presentation domain")
    return WorkspacePresentationDomain(
        domain_id=_exact_text(raw["domain_id"], "presentation domain id"),
        role=_exact_text(raw["role"], "presentation domain role"),
        resolution=_integer(raw["resolution"], "presentation domain resolution"),
        source_sha256=_digest(
            raw["source_sha256"], "presentation domain source sha256"
        ),
        cell_ids_sha256=_digest(
            raw["cell_ids_sha256"], "presentation domain cell digest"
        ),
        cell_count=_integer(
            raw["cell_count"], "presentation domain cell count", positive=True
        ),
        total_area_km2=_number(
            raw["total_area_km2"], "presentation domain area", positive=True
        ),
        id_field=_exact_text(raw["id_field"], "presentation domain id field"),
        area_field=_exact_text(
            raw["area_field"], "presentation domain area field"
        ),
        area_unit=_exact_text(raw["area_unit"], "presentation domain area unit"),
        primary_layer_id=_exact_text(
            raw["primary_layer_id"], "presentation primary layer id"
        ),
    )


def _parse_layer(value: Any) -> WorkspacePresentationLayerSpec:
    raw = _mapping(value, "presentation layer")
    _keys(raw, _LAYER_KEYS, "presentation layer")
    feature_collection = raw["feature_collection_json"]
    if feature_collection is not None and (
        not isinstance(feature_collection, str) or not feature_collection
    ):
        raise ValueError("Presentation layer GeoJSON must be non-empty text or null")
    return WorkspacePresentationLayerSpec(
        layer_id=_exact_text(raw["layer_id"], "presentation layer id"),
        role=_exact_text(raw["role"], "presentation layer role"),
        label=_optional_text(raw["label"], "presentation layer label"),
        geometry_family=_optional_text(
            raw["geometry_family"], "presentation layer geometry family"
        ),
        processing_adapter=_optional_text(
            raw["processing_adapter"], "presentation processing adapter"
        ),
        result_semantics=_optional_text(
            raw["result_semantics"], "presentation result semantics"
        ),
        domain_id=_optional_text(raw["domain_id"], "presentation layer domain"),
        geometry_mode=_exact_text(
            raw["geometry_mode"], "presentation geometry mode"
        ),
        feature_collection_json=feature_collection,
        geometry_reference_layer_id=_optional_text(
            raw["geometry_reference_layer_id"],
            "presentation geometry reference",
        ),
        geometry_unavailable_reason=_optional_text(
            raw["geometry_unavailable_reason"],
            "presentation geometry unavailable reason",
        ),
        source_layer_ids=_string_tuple(
            raw["source_layer_ids"], "presentation source layers"
        ),
        result_id=_optional_text(raw["result_id"], "presentation result id"),
        preview_result_signature_sha256=_optional_digest(
            raw["preview_result_signature_sha256"],
            "presentation preview result signature",
        ),
        source_sha256=_optional_digest(
            raw["source_sha256"], "presentation source sha256"
        ),
        cell_ids_sha256=_optional_digest(
            raw["cell_ids_sha256"], "presentation cell digest"
        ),
        feature_count=_optional_integer(
            raw["feature_count"], "presentation feature count"
        ),
        operation=_optional_text(raw["operation"], "presentation operation"),
        threshold_m=_optional_number(
            raw["threshold_m"], "presentation threshold"
        ),
        color=_optional_text(raw["color"], "presentation color"),
        point_radius=_optional_integer(
            raw["point_radius"], "presentation point radius"
        ),
        quality_flag=_optional_text(
            raw["quality_flag"], "presentation quality flag"
        ),
    )


def _parse_field(value: Any) -> WorkspacePresentationField:
    raw = _mapping(value, "presentation field")
    _keys(raw, _FIELD_KEYS, "presentation field")
    nullable = raw["nullable"]
    if not isinstance(nullable, bool):
        raise TypeError("Presentation field nullable must be boolean")
    return WorkspacePresentationField(
        field_id=_exact_text(raw["field_id"], "presentation field id"),
        value_type=_exact_text(raw["value_type"], "presentation value type"),
        unit=_optional_text(raw["unit"], "presentation field unit"),
        nullable=nullable,
    )


def _parse_metric(value: Any) -> WorkspacePresentationMetric:
    raw = _mapping(value, "presentation metric")
    _keys(raw, _METRIC_KEYS, "presentation metric")
    return WorkspacePresentationMetric(
        metric_id=_exact_text(raw["metric_id"], "presentation metric id"),
        value=_number(raw["value"], "presentation metric value"),
        unit=_exact_text(raw["unit"], "presentation metric unit"),
    )


def _parse_result(value: Any) -> WorkspacePresentationResult:
    raw = _mapping(value, "presentation result")
    _keys(raw, _RESULT_KEYS, "presentation result")
    raw_fields = raw["fields"]
    raw_rows = raw["rows"]
    raw_metrics = raw["metrics"]
    if not all(isinstance(item, list) for item in (raw_fields, raw_rows, raw_metrics)):
        raise TypeError("Presentation result collections must be lists")
    rows: list[tuple[JsonScalar, ...]] = []
    for row in raw_rows:
        if not isinstance(row, list):
            raise TypeError("Presentation result row must be a list")
        if any(
            value is not None
            and not isinstance(value, (str, int, float, bool))
            for value in row
        ):
            raise TypeError("Presentation result row contains a non-scalar value")
        if any(
            isinstance(value, float) and not math.isfinite(value) for value in row
        ):
            raise ValueError("Presentation result row contains non-finite number")
        rows.append(tuple(row))
    return WorkspacePresentationResult(
        result_id=_exact_text(raw["result_id"], "presentation result id"),
        domain_id=_exact_text(raw["domain_id"], "presentation result domain"),
        fields=tuple(_parse_field(item) for item in raw_fields),
        rows=tuple(rows),
        metrics=tuple(_parse_metric(item) for item in raw_metrics),
    )


def parse_workspace_analysis_presentation(
    value: Any,
) -> WorkspaceAnalysisPresentation:
    raw = _mapping(value, "workspace presentation")
    _keys(raw, _PRESENTATION_KEYS, "workspace presentation")
    raw_domains = raw["domains"]
    raw_layers = raw["layers"]
    raw_results = raw["results"]
    raw_buffer_signatures = raw["buffer_result_signatures"]
    if not all(
        isinstance(item, list)
        for item in (
            raw_domains,
            raw_layers,
            raw_results,
            raw_buffer_signatures,
        )
    ):
        raise TypeError("Workspace presentation collections must be lists")
    buffer_signatures: list[tuple[str, str]] = []
    for item in raw_buffer_signatures:
        binding = _mapping(item, "presentation buffer signature")
        _keys(
            binding,
            _BUFFER_SIGNATURE_KEYS,
            "presentation buffer signature",
        )
        buffer_signatures.append(
            (
                _exact_text(binding["group_id"], "presentation buffer group"),
                _digest(
                    binding["result_signature_sha256"],
                    "presentation buffer result signature",
                ),
            )
        )
    presentation = WorkspaceAnalysisPresentation(
        schema_version=_exact_text(
            raw["schema_version"], "presentation schema version"
        ),
        access_scope=_exact_text(raw["access_scope"], "presentation access scope"),
        region_id=_exact_text(raw["region_id"], "presentation region"),
        analysis_id=_exact_text(raw["analysis_id"], "presentation analysis"),
        target_resolution=_integer(
            raw["target_resolution"], "presentation target resolution"
        ),
        request_signature_sha256=_digest(
            raw["request_signature_sha256"], "presentation request signature"
        ),
        request=parse_workspace_analysis_request(raw["request"]),
        area_capability_id=_optional_text(
            raw["area_capability_id"], "presentation area capability"
        ),
        area_result_signature_sha256=_optional_digest(
            raw["area_result_signature_sha256"],
            "presentation area result signature",
        ),
        buffer_result_signatures=tuple(buffer_signatures),
        domains=tuple(_parse_domain(item) for item in raw_domains),
        layers=tuple(_parse_layer(item) for item in raw_layers),
        results=tuple(_parse_result(item) for item in raw_results),
        presentation_signature_sha256=_digest(
            raw["presentation_signature_sha256"],
            "presentation signature",
        ),
    )
    validate_workspace_analysis_presentation(presentation)
    return presentation


__all__ = [
    "WORKSPACE_PRESENTATION_SCHEMA_VERSION",
    "WorkspaceAnalysisPresentation",
    "WorkspacePresentationDomain",
    "WorkspacePresentationField",
    "WorkspacePresentationLayerSpec",
    "WorkspacePresentationMetric",
    "WorkspacePresentationResult",
    "build_workspace_analysis_presentation",
    "parse_workspace_analysis_presentation",
    "validate_workspace_analysis_presentation",
    "validate_workspace_analysis_presentation_inputs",
]
