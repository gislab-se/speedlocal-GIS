from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
import hashlib
import json
import math
import re
import sys
from typing import Any, Iterator, Mapping

from pyproj import CRS, Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union

from .area_result import build_area_group_preview
from .catalogs import load_analysis, load_region_geography
from .contracts import AnalysisContract
from .geometry import (
    SUPPORTED_VECTOR_FAMILIES,
    VectorBufferPreview,
    build_vector_buffer_preview,
)
from .sources import read_layer_geojson_bytes
from .validation import validate_contract, validate_layer
from .workspace_area import workspace_analysis_request_signature
from .workspace_request import (
    WorkspaceAnalysisRequest,
    authorize_catalog_workspace_analysis_request,
    build_workspace_analysis_request_from_contract,
    parse_workspace_analysis_request,
    validate_workspace_analysis_request_from_contract,
)


WORKSPACE_BUFFER_REQUEST_SCHEMA_VERSION = "1.0"
WORKSPACE_BUFFER_RESULT_SCHEMA_VERSION = "1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SUPPORTED_OPERATIONS = {
    "distance_exclusion",
    "hard_exclusion",
    "proximity_feasibility",
}
_SOURCE_PREVIEW_STRATEGY = "source_metric_buffer"
_EXACT_PREVIEW_STRATEGY = "analysis_domain_exact_clip"
_GEOMETRY_TYPE_FAMILIES = {
    "Point": "point",
    "MultiPoint": "point",
    "LineString": "line",
    "LinearRing": "line",
    "MultiLineString": "line",
    "Polygon": "polygon",
    "MultiPolygon": "polygon",
}


@dataclass(frozen=True)
class WorkspaceBufferSourceBinding:
    layer_id: str
    geometry_family: str
    processing_adapter: str
    source_sha256: str
    source_bytes: int
    declared_feature_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "geometry_family": self.geometry_family,
            "processing_adapter": self.processing_adapter,
            "source_sha256": self.source_sha256,
            "source_bytes": self.source_bytes,
            "declared_feature_count": self.declared_feature_count,
        }


@dataclass(frozen=True)
class WorkspaceBufferPreviewRequest:
    schema_version: str
    access_scope: str
    region_id: str
    analysis_id: str
    capability_id: str
    group_id: str
    layer_ids: tuple[str, ...]
    operation: str
    parameter_id: str
    parameter_value: float
    native_crs: str
    preview_strategy: str
    preview_resolution: int
    preview_domain_cell_count: int
    applied_request_signature_sha256: str
    applied_request: WorkspaceAnalysisRequest
    sources: tuple[WorkspaceBufferSourceBinding, ...]
    request_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "region_id": self.region_id,
            "analysis_id": self.analysis_id,
            "capability_id": self.capability_id,
            "group_id": self.group_id,
            "layer_ids": list(self.layer_ids),
            "operation": self.operation,
            "parameter_id": self.parameter_id,
            "parameter_value": self.parameter_value,
            "native_crs": self.native_crs,
            "preview_strategy": self.preview_strategy,
            "preview_resolution": self.preview_resolution,
            "preview_domain_cell_count": self.preview_domain_cell_count,
            "applied_request_signature_sha256": (
                self.applied_request_signature_sha256
            ),
            "applied_request": self.applied_request.as_dict(),
            "sources": [source.as_dict() for source in self.sources],
            "request_signature_sha256": self.request_signature_sha256,
        }


@dataclass(frozen=True)
class WorkspaceBufferPreviewResult:
    schema_version: str
    access_scope: str
    region_id: str
    analysis_id: str
    capability_id: str
    group_id: str
    operation: str
    request_signature_sha256: str
    request: WorkspaceBufferPreviewRequest
    layer_ids: tuple[str, ...]
    native_crs: str
    buffer_m: float
    semantics: str
    geometry_type: str
    source_feature_count: int
    declared_feature_count: int
    area_m2: float
    model_area_m2: float | None
    zero_cell_count: int | None
    partial_cell_count: int | None
    full_cell_count: int | None
    feature_count: int
    feature_collection_json: str
    feature_collection_sha256: str
    result_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "region_id": self.region_id,
            "analysis_id": self.analysis_id,
            "capability_id": self.capability_id,
            "group_id": self.group_id,
            "operation": self.operation,
            "request_signature_sha256": self.request_signature_sha256,
            "request": self.request.as_dict(),
            "layer_ids": list(self.layer_ids),
            "native_crs": self.native_crs,
            "buffer_m": self.buffer_m,
            "semantics": self.semantics,
            "geometry_type": self.geometry_type,
            "source_feature_count": self.source_feature_count,
            "declared_feature_count": self.declared_feature_count,
            "area_m2": self.area_m2,
            "model_area_m2": self.model_area_m2,
            "zero_cell_count": self.zero_cell_count,
            "partial_cell_count": self.partial_cell_count,
            "full_cell_count": self.full_cell_count,
            "feature_count": self.feature_count,
            "feature_collection_json": self.feature_collection_json,
            "feature_collection_sha256": self.feature_collection_sha256,
            "result_signature_sha256": self.result_signature_sha256,
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


def _exact_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be exact non-empty text")
    return value


def _digest(value: Any, label: str) -> str:
    text = _exact_text(value, label)
    if _SHA256.fullmatch(text) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


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


def _number(value: Any, label: str, *, non_negative: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result) or (non_negative and result < 0.0):
        raise ValueError(f"{label} must be finite and non-negative")
    return result


def _optional_number(value: Any, label: str) -> float | None:
    if value is None:
        return None
    return _number(value, label)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields drifted from schema")


def _canonical_metric_crs(value: str) -> str:
    try:
        crs = CRS.from_user_input(_exact_text(value, "native CRS"))
    except Exception as exc:
        raise ValueError("Workspace buffer native CRS is invalid") from exc
    if not crs.is_projected:
        raise ValueError("Workspace buffer native CRS must be projected")
    axes = crs.axis_info[:2]
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
        raise ValueError("Workspace buffer native CRS must use metres")
    return crs.to_string()


def _request_signature_payload(
    request: WorkspaceBufferPreviewRequest,
) -> dict[str, Any]:
    payload = request.as_dict()
    payload.pop("request_signature_sha256")
    return payload


def _result_signature_payload(
    result: WorkspaceBufferPreviewResult,
) -> dict[str, Any]:
    payload = result.as_dict()
    payload.pop("result_signature_sha256")
    return payload


def _source_binding(contract: AnalysisContract, layer_id: str) -> WorkspaceBufferSourceBinding:
    layer = contract.layers[layer_id]
    validated = validate_layer(layer)
    if validated.geometry_family not in SUPPORTED_VECTOR_FAMILIES:
        raise NotImplementedError(
            f"Unsupported workspace buffer geometry: {validated.geometry_family}"
        )
    try:
        payload_bytes = read_layer_geojson_bytes(validated.assets)
    except OSError as exc:
        raise ValueError(f"Workspace buffer source {layer_id} is unreadable") from exc
    source_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    if (
        source_sha256 != validated.assets.geojson_sha256
        or len(payload_bytes) != validated.assets.geojson_bytes
    ):
        raise ValueError(f"Workspace buffer source {layer_id} bytes drifted")
    return WorkspaceBufferSourceBinding(
        layer_id=layer_id,
        geometry_family=validated.geometry_family,
        processing_adapter=validated.processing_adapter,
        source_sha256=source_sha256,
        source_bytes=len(payload_bytes),
        declared_feature_count=int(validated.assets.feature_count),
    )


def build_workspace_buffer_preview_request_from_contract(
    contract: AnalysisContract,
    applied_request: WorkspaceAnalysisRequest,
    group_id: str,
    *,
    native_crs: str,
) -> WorkspaceBufferPreviewRequest:
    """Bind one applied group to its exact vector sources and operation."""

    validate_contract(contract)
    validate_workspace_analysis_request_from_contract(contract, applied_request)
    canonical_group_id = _exact_text(group_id, "workspace buffer group id")
    groups = {
        group.group_id: group for group in applied_request.groups
    }
    group = groups.get(canonical_group_id)
    if group is None:
        raise ValueError("Workspace buffer group is not applied in the request")
    if not group.layer_ids:
        raise ValueError("Workspace buffer group has no applied layers")
    operations = {contract.layers[layer_id].operation for layer_id in group.layer_ids}
    if len(operations) != 1:
        raise ValueError("Workspace buffer group must declare one operation")
    operation = next(iter(operations))
    if operation not in _SUPPORTED_OPERATIONS:
        raise NotImplementedError(
            f"Unsupported workspace buffer operation: {operation}"
        )
    parameters = group.parameter_map()
    if "buffer_m" not in parameters:
        raise ValueError("Workspace buffer group has no applied buffer_m parameter")
    parameter_value = float(parameters["buffer_m"])
    if not math.isfinite(parameter_value) or parameter_value < 0.0:
        raise ValueError("Workspace buffer_m must be finite and non-negative")
    for layer_id in group.layer_ids:
        parameter = contract.layers[layer_id].parameters.get("buffer_m")
        if parameter is None or parameter.unit != "m":
            raise ValueError(
                f"Workspace buffer layer {layer_id} has no metre parameter"
            )
        if not math.isclose(
            parameter.validate_value(parameter_value),
            parameter_value,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("Workspace buffer parameter did not validate exactly")
    domain = contract.analysis_domain
    if domain is None:
        raise ValueError("Workspace buffer analysis domain is missing")
    canonical_crs = _canonical_metric_crs(native_crs)
    sources = tuple(_source_binding(contract, layer_id) for layer_id in group.layer_ids)
    preview_strategy = (
        _EXACT_PREVIEW_STRATEGY
        if operation == "proximity_feasibility"
        else _SOURCE_PREVIEW_STRATEGY
    )
    request = WorkspaceBufferPreviewRequest(
        schema_version=WORKSPACE_BUFFER_REQUEST_SCHEMA_VERSION,
        access_scope=applied_request.access_scope,
        region_id=applied_request.region_id,
        analysis_id=applied_request.analysis_id,
        capability_id=(
            f"{applied_request.analysis_id}.group.{canonical_group_id}"
        ),
        group_id=canonical_group_id,
        layer_ids=group.layer_ids,
        operation=operation,
        parameter_id="buffer_m",
        parameter_value=parameter_value,
        native_crs=canonical_crs,
        preview_strategy=preview_strategy,
        preview_resolution=int(domain.resolution),
        preview_domain_cell_count=int(domain.expected_cell_count),
        applied_request_signature_sha256=(
            workspace_analysis_request_signature(applied_request)
        ),
        applied_request=applied_request,
        sources=sources,
        request_signature_sha256="0" * 64,
    )
    request = replace(
        request,
        request_signature_sha256=_canonical_sha256(
            _request_signature_payload(request)
        ),
    )
    validate_workspace_buffer_preview_request(request)
    return request


def build_catalog_workspace_buffer_preview_request(
    applied_request: WorkspaceAnalysisRequest,
    group_id: str,
) -> WorkspaceBufferPreviewRequest:
    contract = load_analysis(
        applied_request.region_id,
        applied_request.analysis_id,
    )
    geography = load_region_geography(applied_request.region_id)
    return build_workspace_buffer_preview_request_from_contract(
        contract,
        applied_request,
        group_id,
        native_crs=geography.native_crs,
    )


def validate_workspace_buffer_preview_request(
    request: WorkspaceBufferPreviewRequest,
) -> None:
    if not isinstance(request, WorkspaceBufferPreviewRequest):
        raise TypeError("request must be a WorkspaceBufferPreviewRequest")
    if request.schema_version != WORKSPACE_BUFFER_REQUEST_SCHEMA_VERSION:
        raise NotImplementedError(
            f"Unsupported workspace buffer request schema: {request.schema_version}"
        )
    applied = parse_workspace_analysis_request(request.applied_request.as_dict())
    group = next(
        (value for value in applied.groups if value.group_id == request.group_id),
        None,
    )
    scope = applied.access_scope.split(":", 1)
    expected_strategy = (
        _EXACT_PREVIEW_STRATEGY
        if request.operation == "proximity_feasibility"
        else _SOURCE_PREVIEW_STRATEGY
    )
    if (
        len(scope) != 2
        or scope[0] not in {"product", "review"}
        or scope[1] != applied.region_id
        or group is None
        or request.access_scope != applied.access_scope
        or request.region_id != applied.region_id
        or request.analysis_id != applied.analysis_id
        or request.capability_id
        != f"{applied.analysis_id}.group.{request.group_id}"
        or request.layer_ids != group.layer_ids
        or request.operation not in _SUPPORTED_OPERATIONS
        or request.parameter_id != "buffer_m"
        or "buffer_m" not in group.parameter_map()
        or request.parameter_value != float(group.parameter_map()["buffer_m"])
        or request.preview_strategy != expected_strategy
        or request.preview_resolution != applied.source_resolution
        or request.preview_domain_cell_count <= 0
        or request.applied_request_signature_sha256
        != workspace_analysis_request_signature(applied)
    ):
        raise ValueError("Workspace buffer request identity drifted from applied request")
    _number(request.parameter_value, "workspace buffer parameter")
    _integer(request.preview_resolution, "workspace buffer resolution")
    _integer(
        request.preview_domain_cell_count,
        "workspace buffer domain cell count",
        positive=True,
    )
    if request.native_crs != _canonical_metric_crs(request.native_crs):
        raise ValueError("Workspace buffer native CRS is not canonical")
    if not isinstance(request.sources, tuple) or tuple(
        source.layer_id for source in request.sources
    ) != request.layer_ids:
        raise ValueError("Workspace buffer source order drifted from applied layers")
    for source in request.sources:
        if not isinstance(source, WorkspaceBufferSourceBinding):
            raise TypeError("Workspace buffer source binding type is invalid")
        _exact_text(source.layer_id, "workspace buffer source layer id")
        if source.geometry_family not in SUPPORTED_VECTOR_FAMILIES:
            raise NotImplementedError(
                f"Unsupported workspace buffer geometry: {source.geometry_family}"
            )
        _exact_text(source.processing_adapter, "workspace processing adapter")
        _digest(source.source_sha256, "workspace buffer source sha256")
        _integer(source.source_bytes, "workspace buffer source bytes", positive=True)
        _integer(
            source.declared_feature_count,
            "workspace buffer declared feature count",
            positive=True,
        )
    expected_signature = _canonical_sha256(_request_signature_payload(request))
    if request.request_signature_sha256 != expected_signature:
        raise ValueError("Workspace buffer request signature does not match")


def validate_workspace_buffer_preview_request_from_contract(
    contract: AnalysisContract,
    request: WorkspaceBufferPreviewRequest,
    *,
    native_crs: str,
) -> None:
    validate_workspace_buffer_preview_request(request)
    validate_workspace_analysis_request_from_contract(
        contract,
        request.applied_request,
    )
    rebuilt = build_workspace_buffer_preview_request_from_contract(
        contract,
        request.applied_request,
        request.group_id,
        native_crs=native_crs,
    )
    if rebuilt != request:
        raise ValueError("Workspace buffer request drifted from current contract")


def _validate_preview_identity(
    request: WorkspaceBufferPreviewRequest,
    preview: VectorBufferPreview,
) -> None:
    if not isinstance(preview, VectorBufferPreview):
        raise TypeError("preview must be a VectorBufferPreview")
    expected_semantics = (
        "exact_area_clip"
        if request.preview_strategy == _EXACT_PREVIEW_STRATEGY
        else "dissolved_source_footprint"
        if request.parameter_value == 0.0
        else "metric_buffer"
    )
    expected_family = _expected_preview_geometry_family(request)
    if (
        expected_family is not None
        and _geometry_type_family(preview.geometry_type) != expected_family
    ):
        raise ValueError("Workspace buffer engine preview geometry family drifted")
    if (
        preview.layer_ids != request.layer_ids
        or preview.native_crs != request.native_crs
        or preview.buffer_m != request.parameter_value
        or preview.semantics != expected_semantics
        or preview.source_feature_count <= 0
        or preview.declared_feature_count
        != sum(source.declared_feature_count for source in request.sources)
        or not math.isfinite(preview.area_m2)
        or preview.area_m2 < 0.0
    ):
        raise ValueError("Workspace buffer engine preview identity drifted")
    counts = (
        preview.zero_cell_count,
        preview.partial_cell_count,
        preview.full_cell_count,
    )
    if request.preview_strategy == _EXACT_PREVIEW_STRATEGY:
        if (
            preview.model_area_m2 is None
            or not math.isfinite(preview.model_area_m2)
            or preview.model_area_m2 <= 0.0
            or any(value is None for value in counts)
            or sum(int(value or 0) for value in counts)
            != request.preview_domain_cell_count
        ):
            raise ValueError("Exact workspace operation preview is incomplete")
    elif preview.model_area_m2 is not None or any(value is not None for value in counts):
        raise ValueError("Source buffer preview contains undeclared domain metrics")


def _geometry_type_family(geometry_type: Any) -> str | None:
    if not isinstance(geometry_type, str):
        return None
    return _GEOMETRY_TYPE_FAMILIES.get(geometry_type)


def _expected_preview_geometry_family(
    request: WorkspaceBufferPreviewRequest,
) -> str | None:
    if (
        request.preview_strategy == _EXACT_PREVIEW_STRATEGY
        or request.parameter_value > 0.0
    ):
        return "polygon"
    source_families = {source.geometry_family for source in request.sources}
    if len(source_families) == 1:
        return next(iter(source_families))
    return None


def build_workspace_buffer_preview_result(
    request: WorkspaceBufferPreviewRequest,
    preview: VectorBufferPreview,
) -> WorkspaceBufferPreviewResult:
    validate_workspace_buffer_preview_request(request)
    _validate_preview_identity(request, preview)
    feature_collection_json = _canonical_json(preview.geojson)
    payload = json.loads(feature_collection_json)
    features = payload.get("features") if isinstance(payload, Mapping) else None
    if (
        not isinstance(payload, Mapping)
        or payload.get("type") != "FeatureCollection"
        or not isinstance(features, list)
        or not features
    ):
        raise ValueError("Workspace buffer engine did not return a FeatureCollection")
    result = WorkspaceBufferPreviewResult(
        schema_version=WORKSPACE_BUFFER_RESULT_SCHEMA_VERSION,
        access_scope=request.access_scope,
        region_id=request.region_id,
        analysis_id=request.analysis_id,
        capability_id=request.capability_id,
        group_id=request.group_id,
        operation=request.operation,
        request_signature_sha256=request.request_signature_sha256,
        request=request,
        layer_ids=preview.layer_ids,
        native_crs=preview.native_crs,
        buffer_m=float(preview.buffer_m),
        semantics=str(preview.semantics),
        geometry_type=str(preview.geometry_type),
        source_feature_count=int(preview.source_feature_count),
        declared_feature_count=int(preview.declared_feature_count),
        area_m2=float(preview.area_m2),
        model_area_m2=(
            None
            if preview.model_area_m2 is None
            else float(preview.model_area_m2)
        ),
        zero_cell_count=preview.zero_cell_count,
        partial_cell_count=preview.partial_cell_count,
        full_cell_count=preview.full_cell_count,
        feature_count=len(features),
        feature_collection_json=feature_collection_json,
        feature_collection_sha256=hashlib.sha256(
            feature_collection_json.encode("utf-8")
        ).hexdigest(),
        result_signature_sha256="0" * 64,
    )
    result = replace(
        result,
        result_signature_sha256=_canonical_sha256(
            _result_signature_payload(result)
        ),
    )
    validate_workspace_buffer_preview_result(result)
    return result


def _preview_geometries(
    feature_collection_json: str,
) -> tuple[Mapping[str, Any], tuple[Any, ...]]:
    if not isinstance(feature_collection_json, str) or not feature_collection_json:
        raise ValueError("Workspace buffer GeoJSON must be non-empty text")
    try:
        payload = json.loads(feature_collection_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Workspace buffer result is not GeoJSON") from exc
    if not isinstance(payload, Mapping) or payload.get("type") != "FeatureCollection":
        raise ValueError("Workspace buffer result must be a FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Workspace buffer result has no features")
    geometries: list[Any] = []
    for index, item in enumerate(features):
        feature = _mapping(item, f"workspace buffer feature {index}")
        geometry_raw = feature.get("geometry")
        if feature.get("type") != "Feature" or not isinstance(
            geometry_raw, Mapping
        ):
            raise ValueError(f"Workspace buffer feature {index} is invalid")
        try:
            geometry = shape(geometry_raw)
        except Exception as exc:
            raise ValueError(
                f"Workspace buffer feature {index} geometry is unreadable"
            ) from exc
        bounds = geometry.bounds
        if (
            geometry.is_empty
            or not geometry.is_valid
            or len(bounds) != 4
            or not all(math.isfinite(float(value)) for value in bounds)
            or bounds[0] < -180.0
            or bounds[2] > 180.0
            or bounds[1] < -90.0
            or bounds[3] > 90.0
        ):
            raise ValueError(
                f"Workspace buffer feature {index} geometry is invalid"
            )
        geometries.append(geometry)
    return payload, tuple(geometries)


@dataclass(frozen=True, slots=True)
class _BufferGeometryEvidence:
    key: tuple[str, str, str, str]
    feature_count: int
    geometry_type: str
    area_m2: float
    charge: int


_BUFFER_GEOMETRY_MAX_ENTRIES = 16
_BUFFER_GEOMETRY_MAX_BYTES = 64 * 1024 * 1024
_buffer_geometry_scope: ContextVar[tuple[_BufferGeometryEvidence, ...] | None] = (
    ContextVar("workspace_buffer_geometry_evidence", default=None)
)


@contextmanager
def workspace_buffer_geometry_validation_scope() -> Iterator[None]:
    """Reuse exact geometry proofs only during one synchronous analysis plan.

    Nested builders share the current scope. The root drops all strong text
    references on success or failure. Immutable context values avoid sharing
    mutations with copied contexts; no geometry or live input verdict is stored.
    Standalone public validation always takes the precise path.
    """
    if _buffer_geometry_scope.get() is not None:
        yield
        return
    token = _buffer_geometry_scope.set(())
    try:
        yield
    finally:
        _buffer_geometry_scope.reset(token)


def _buffer_geometry_key(
    result: WorkspaceBufferPreviewResult,
) -> tuple[str, str, str, str]:
    # Exact text equality, not a caller's claimed digest, selects the proof.
    # The namespace prevents reuse across region/access surfaces even in a
    # manually nested scope. Request/source/revision checks remain per caller.
    return (result.region_id, result.access_scope, result.native_crs,
            result.feature_collection_json)


def _remember_buffer_geometry(
    key: tuple[str, str, str, str], feature_count: int,
    geometry_type: str, area_m2: float,
) -> None:
    entries = _buffer_geometry_scope.get()
    if entries is None or any(type(value) is not str for value in key):
        return
    evidence = _BufferGeometryEvidence(key, feature_count, geometry_type, area_m2, 0)
    # Charge retained text, tuples, record and scalar referents conservatively;
    # decoded JSON and Shapely geometry are never retained by this scope.
    charge = (sys.getsizeof(evidence) + sys.getsizeof(key)
              + sum(sys.getsizeof(value) for value in key)
              + sum(sys.getsizeof(value) for value in
                    (feature_count, geometry_type, area_m2, 0)))
    if charge + sys.getsizeof((evidence,)) > _BUFFER_GEOMETRY_MAX_BYTES:
        return
    evidence = replace(evidence, charge=charge)
    retained = (*entries, evidence)
    total = sum(value.charge for value in retained)
    while retained and (len(retained) > _BUFFER_GEOMETRY_MAX_ENTRIES
                        or total + sys.getsizeof(retained) > _BUFFER_GEOMETRY_MAX_BYTES):
        total -= retained[0].charge
        retained = retained[1:]
    _buffer_geometry_scope.set(retained)


def validate_workspace_buffer_preview_result(
    result: WorkspaceBufferPreviewResult,
) -> None:
    if not isinstance(result, WorkspaceBufferPreviewResult):
        raise TypeError("result must be a WorkspaceBufferPreviewResult")
    if result.schema_version != WORKSPACE_BUFFER_RESULT_SCHEMA_VERSION:
        raise NotImplementedError(
            f"Unsupported workspace buffer result schema: {result.schema_version}"
        )
    validate_workspace_buffer_preview_request(result.request)
    request = result.request
    if (
        result.access_scope != request.access_scope
        or result.region_id != request.region_id
        or result.analysis_id != request.analysis_id
        or result.capability_id != request.capability_id
        or result.group_id != request.group_id
        or result.operation != request.operation
        or result.request_signature_sha256 != request.request_signature_sha256
        or result.layer_ids != request.layer_ids
        or result.native_crs != request.native_crs
        or result.buffer_m != request.parameter_value
    ):
        raise ValueError("Workspace buffer result identity drifted from request")
    if result.native_crs != _canonical_metric_crs(result.native_crs):
        raise ValueError("Workspace buffer result native CRS is not canonical")
    expected_semantics = (
        "exact_area_clip"
        if request.preview_strategy == _EXACT_PREVIEW_STRATEGY
        else "dissolved_source_footprint"
        if request.parameter_value == 0.0
        else "metric_buffer"
    )
    if result.semantics != expected_semantics:
        raise ValueError("Workspace buffer result semantics drifted from operation")
    _exact_text(result.geometry_type, "workspace buffer geometry type")
    expected_family = _expected_preview_geometry_family(request)
    if (
        expected_family is not None
        and _geometry_type_family(result.geometry_type) != expected_family
    ):
        raise ValueError("Workspace buffer result geometry family drifted")
    _integer(
        result.source_feature_count,
        "workspace buffer source feature count",
        positive=True,
    )
    _integer(
        result.declared_feature_count,
        "workspace buffer declared feature count",
        positive=True,
    )
    _number(result.area_m2, "workspace buffer area")
    _integer(result.feature_count, "workspace buffer feature count", positive=True)
    _digest(
        result.feature_collection_sha256,
        "workspace buffer feature collection sha256",
    )
    if (
        result.declared_feature_count
        != sum(source.declared_feature_count for source in request.sources)
        or result.feature_collection_sha256
        != hashlib.sha256(result.feature_collection_json.encode("utf-8")).hexdigest()
    ):
        raise ValueError("Workspace buffer result evidence drifted")
    key = _buffer_geometry_key(result)
    entries = _buffer_geometry_scope.get()
    evidence = next((value for value in entries if value.key == key), None) if (
        entries is not None and all(type(value) is str for value in key)
    ) else None
    if evidence is None:
        payload, geometries = _preview_geometries(result.feature_collection_json)
        feature_count = len(geometries)
    else:
        # Metadata is decoded anew; the proof certifies only geometry facts.
        payload = json.loads(result.feature_collection_json)
        feature_count = evidence.feature_count
    if result.feature_count != feature_count:
        raise ValueError("Workspace buffer result feature count drifted")
    if evidence is None:
        dissolved = unary_union(geometries)
        geometry_type = dissolved.geom_type
    else:
        geometry_type = evidence.geometry_type
    if geometry_type != result.geometry_type:
        raise ValueError("Workspace buffer geometry type drifted")
    properties = payload["features"][0].get("properties")
    if not isinstance(properties, Mapping) or (
        tuple(str(value) for value in properties.get("layer_ids") or ())
        != request.layer_ids
        or str(properties.get("native_crs") or "") != request.native_crs
        or float(properties.get("buffer_m")) != request.parameter_value
        or str(properties.get("semantics") or "") != result.semantics
    ):
        raise ValueError("Workspace buffer GeoJSON properties drifted")
    if request.preview_strategy == _EXACT_PREVIEW_STRATEGY and (
        str(properties.get("analysis_id") or "") != request.analysis_id
        or str(properties.get("group_id") or "") != request.group_id
        or str(properties.get("operation") or "") != request.operation
        or int(properties.get("source_h3_resolution"))
        != request.preview_resolution
    ):
        raise ValueError("Exact operation-preview properties drifted")
    if evidence is None:
        try:
            transformer = Transformer.from_crs(
                "EPSG:4326",
                result.native_crs,
                always_xy=True,
            )
            native_geometry = transform(transformer.transform, dissolved)
            serialized_area_m2 = float(native_geometry.area)
        except Exception as exc:
            raise ValueError("Workspace buffer result cannot be measured") from exc
    else:
        serialized_area_m2 = evidence.area_m2
    if not math.isclose(
        serialized_area_m2,
        result.area_m2,
        rel_tol=1e-8,
        abs_tol=1.0,
    ):
        raise ValueError("Workspace buffer serialized geometry area drifted")
    counts = (
        result.zero_cell_count,
        result.partial_cell_count,
        result.full_cell_count,
    )
    if request.preview_strategy == _EXACT_PREVIEW_STRATEGY:
        if (
            result.model_area_m2 is None
            or _number(result.model_area_m2, "workspace buffer model area") <= 0.0
            or any(value is None for value in counts)
            or any(int(value or 0) < 0 for value in counts)
            or sum(int(value or 0) for value in counts)
            != request.preview_domain_cell_count
        ):
            raise ValueError("Exact workspace operation result is incomplete")
    elif result.model_area_m2 is not None or any(value is not None for value in counts):
        raise ValueError("Source buffer result contains exact-domain metrics")
    expected_signature = _canonical_sha256(_result_signature_payload(result))
    if result.result_signature_sha256 != expected_signature:
        raise ValueError("Workspace buffer result signature does not match")
    if evidence is None:
        _remember_buffer_geometry(key, feature_count, geometry_type, serialized_area_m2)


def _current_source_bindings(
    contract: AnalysisContract,
    request: WorkspaceBufferPreviewRequest,
) -> tuple[WorkspaceBufferSourceBinding, ...]:
    return tuple(_source_binding(contract, layer_id) for layer_id in request.layer_ids)


def _current_workspace_buffer_contract(
    request: WorkspaceBufferPreviewRequest,
) -> AnalysisContract:
    if not isinstance(request, WorkspaceBufferPreviewRequest):
        raise TypeError("request must be a WorkspaceBufferPreviewRequest")
    parsed = parse_workspace_buffer_preview_request(request.as_dict())
    if parsed != request:
        raise ValueError("Workspace buffer request is not canonical")
    contract = load_analysis(request.region_id, request.analysis_id)
    geography = load_region_geography(request.region_id)
    validate_workspace_buffer_preview_request_from_contract(
        contract,
        request,
        native_crs=geography.native_crs,
    )
    authorize_catalog_workspace_analysis_request(
        request.applied_request,
        required_capability_id=request.capability_id,
    )
    if _current_source_bindings(contract, request) != request.sources:
        raise ValueError("Workspace buffer sources changed before execution")
    return contract


@dataclass(frozen=True)
class WorkspacePreparedBufferPreview:
    """One immutable native/group preview under the caller's live snapshot."""

    runtime_snapshot_token: str
    result: WorkspaceBufferPreviewResult


def reusable_catalog_workspace_buffer_request(
    request: WorkspaceBufferPreviewRequest,
) -> WorkspaceBufferPreviewRequest:
    """Authorize the actual request, then isolate this group's engine inputs.

    Both preview engines consume this group's layers/parameter and the native
    domain. Other groups and the displayed parent level do not select geometry.
    Contract, domain, source, CRS, region, analysis and access identities remain.
    """

    contract = _current_workspace_buffer_contract(request)
    group = next(value for value in request.applied_request.groups
                 if value.group_id == request.group_id)
    applied = build_workspace_analysis_request_from_contract(
        contract,
        access_scope=request.access_scope,
        selected_group_layers={group.group_id: group.layer_ids},
        group_parameters={group.group_id: group.parameter_map()},
        target_resolution=request.applied_request.source_resolution,
    )
    return build_workspace_buffer_preview_request_from_contract(
        contract, applied, request.group_id, native_crs=request.native_crs,
    )


def prepare_catalog_workspace_buffer_preview(
    request: WorkspaceBufferPreviewRequest,
    runtime_snapshot_token: str,
) -> WorkspacePreparedBufferPreview:
    token = _digest(runtime_snapshot_token, "Buffer runtime snapshot token")
    if request != reusable_catalog_workspace_buffer_request(request):
        raise ValueError("Prepared buffer requires its isolated native group request")
    return WorkspacePreparedBufferPreview(
        token, run_catalog_workspace_buffer_preview_request(request),
    )


def derive_catalog_workspace_buffer_preview(
    request: WorkspaceBufferPreviewRequest,
    prepared: WorkspacePreparedBufferPreview,
    runtime_snapshot_token: str,
) -> WorkspaceBufferPreviewResult:
    """Retain exact geometry while signing the current complete applied request."""

    token = _digest(runtime_snapshot_token, "Buffer runtime snapshot token")
    reusable_request = reusable_catalog_workspace_buffer_request(request)
    if not isinstance(prepared, WorkspacePreparedBufferPreview):
        raise TypeError("prepared must be a WorkspacePreparedBufferPreview")
    if not isinstance(prepared.result, WorkspaceBufferPreviewResult):
        raise TypeError("Prepared buffer result has an invalid type")
    if (prepared.runtime_snapshot_token != token
            or prepared.result.request != reusable_request):
        raise ValueError("Prepared buffer escaped its group, inputs or runtime")
    # Full public geometry, metadata, area and signature validation remains.
    validate_workspace_buffer_preview_result(prepared.result)
    result = replace(
        prepared.result, request=request,
        request_signature_sha256=request.request_signature_sha256,
        result_signature_sha256="0" * 64,
    )
    result = replace(result, result_signature_sha256=_canonical_sha256(
        _result_signature_payload(result)))
    contract = load_analysis(request.region_id, request.analysis_id)
    if _current_source_bindings(contract, request) != request.sources:
        raise ValueError("Workspace buffer sources changed during execution")
    return result


def run_catalog_workspace_buffer_preview_request(
    request: WorkspaceBufferPreviewRequest,
) -> WorkspaceBufferPreviewResult:
    contract = _current_workspace_buffer_contract(request)
    if request.preview_strategy == _EXACT_PREVIEW_STRATEGY:
        preview = build_area_group_preview(
            region=request.region_id,
            analysis=request.analysis_id,
            group_id=request.group_id,
            layers=request.layer_ids,
            buffer_m=request.parameter_value,
        )
    elif request.preview_strategy == _SOURCE_PREVIEW_STRATEGY:
        preview = build_vector_buffer_preview(
            tuple(contract.layers[layer_id] for layer_id in request.layer_ids),
            native_crs=request.native_crs,
            buffer_m=request.parameter_value,
        )
    else:
        raise NotImplementedError(
            f"Unsupported workspace buffer strategy: {request.preview_strategy}"
        )
    if _current_source_bindings(contract, request) != request.sources:
        raise ValueError("Workspace buffer sources changed during execution")
    return build_workspace_buffer_preview_result(request, preview)


def validate_workspace_buffer_preview_result_from_contract(
    contract: AnalysisContract,
    result: WorkspaceBufferPreviewResult,
    *,
    native_crs: str,
) -> None:
    validate_workspace_buffer_preview_result(result)
    validate_workspace_buffer_preview_request_from_contract(
        contract,
        result.request,
        native_crs=native_crs,
    )


def replay_catalog_workspace_buffer_preview_result(
    result: WorkspaceBufferPreviewResult,
) -> WorkspaceBufferPreviewResult:
    parsed = parse_workspace_buffer_preview_result(result.as_dict())
    replayed = run_catalog_workspace_buffer_preview_request(parsed.request)
    if replayed != parsed:
        raise ValueError("Workspace buffer result does not match canonical replay")
    return replayed


_SOURCE_KEYS = {
    "layer_id",
    "geometry_family",
    "processing_adapter",
    "source_sha256",
    "source_bytes",
    "declared_feature_count",
}
_REQUEST_KEYS = {
    "schema_version",
    "access_scope",
    "region_id",
    "analysis_id",
    "capability_id",
    "group_id",
    "layer_ids",
    "operation",
    "parameter_id",
    "parameter_value",
    "native_crs",
    "preview_strategy",
    "preview_resolution",
    "preview_domain_cell_count",
    "applied_request_signature_sha256",
    "applied_request",
    "sources",
    "request_signature_sha256",
}
_RESULT_KEYS = {
    "schema_version",
    "access_scope",
    "region_id",
    "analysis_id",
    "capability_id",
    "group_id",
    "operation",
    "request_signature_sha256",
    "request",
    "layer_ids",
    "native_crs",
    "buffer_m",
    "semantics",
    "geometry_type",
    "source_feature_count",
    "declared_feature_count",
    "area_m2",
    "model_area_m2",
    "zero_cell_count",
    "partial_cell_count",
    "full_cell_count",
    "feature_count",
    "feature_collection_json",
    "feature_collection_sha256",
    "result_signature_sha256",
}


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    result = tuple(_exact_text(item, f"{label} item") for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must be unique")
    return result


def _parse_source(value: Any) -> WorkspaceBufferSourceBinding:
    raw = _mapping(value, "workspace buffer source")
    _keys(raw, _SOURCE_KEYS, "workspace buffer source")
    return WorkspaceBufferSourceBinding(
        layer_id=_exact_text(raw["layer_id"], "workspace buffer source layer"),
        geometry_family=_exact_text(
            raw["geometry_family"], "workspace buffer geometry family"
        ),
        processing_adapter=_exact_text(
            raw["processing_adapter"], "workspace processing adapter"
        ),
        source_sha256=_digest(
            raw["source_sha256"], "workspace buffer source sha256"
        ),
        source_bytes=_integer(
            raw["source_bytes"], "workspace buffer source bytes", positive=True
        ),
        declared_feature_count=_integer(
            raw["declared_feature_count"],
            "workspace buffer declared feature count",
            positive=True,
        ),
    )


def parse_workspace_buffer_preview_request(
    value: Any,
) -> WorkspaceBufferPreviewRequest:
    raw = _mapping(value, "workspace buffer request")
    _keys(raw, _REQUEST_KEYS, "workspace buffer request")
    raw_sources = raw["sources"]
    if not isinstance(raw_sources, list):
        raise TypeError("Workspace buffer sources must be a list")
    request = WorkspaceBufferPreviewRequest(
        schema_version=_exact_text(
            raw["schema_version"], "workspace buffer request schema"
        ),
        access_scope=_exact_text(raw["access_scope"], "workspace buffer access"),
        region_id=_exact_text(raw["region_id"], "workspace buffer region"),
        analysis_id=_exact_text(raw["analysis_id"], "workspace buffer analysis"),
        capability_id=_exact_text(
            raw["capability_id"], "workspace buffer capability"
        ),
        group_id=_exact_text(raw["group_id"], "workspace buffer group"),
        layer_ids=_string_tuple(raw["layer_ids"], "workspace buffer layers"),
        operation=_exact_text(raw["operation"], "workspace buffer operation"),
        parameter_id=_exact_text(
            raw["parameter_id"], "workspace buffer parameter id"
        ),
        parameter_value=_number(
            raw["parameter_value"], "workspace buffer parameter"
        ),
        native_crs=_exact_text(raw["native_crs"], "workspace buffer native CRS"),
        preview_strategy=_exact_text(
            raw["preview_strategy"], "workspace buffer strategy"
        ),
        preview_resolution=_integer(
            raw["preview_resolution"], "workspace buffer resolution"
        ),
        preview_domain_cell_count=_integer(
            raw["preview_domain_cell_count"],
            "workspace buffer domain cell count",
            positive=True,
        ),
        applied_request_signature_sha256=_digest(
            raw["applied_request_signature_sha256"],
            "workspace applied request signature",
        ),
        applied_request=parse_workspace_analysis_request(raw["applied_request"]),
        sources=tuple(_parse_source(item) for item in raw_sources),
        request_signature_sha256=_digest(
            raw["request_signature_sha256"], "workspace buffer request signature"
        ),
    )
    validate_workspace_buffer_preview_request(request)
    return request


def parse_workspace_buffer_preview_result(
    value: Any,
) -> WorkspaceBufferPreviewResult:
    raw = _mapping(value, "workspace buffer result")
    _keys(raw, _RESULT_KEYS, "workspace buffer result")
    result = WorkspaceBufferPreviewResult(
        schema_version=_exact_text(
            raw["schema_version"], "workspace buffer result schema"
        ),
        access_scope=_exact_text(raw["access_scope"], "workspace buffer access"),
        region_id=_exact_text(raw["region_id"], "workspace buffer region"),
        analysis_id=_exact_text(raw["analysis_id"], "workspace buffer analysis"),
        capability_id=_exact_text(
            raw["capability_id"], "workspace buffer capability"
        ),
        group_id=_exact_text(raw["group_id"], "workspace buffer group"),
        operation=_exact_text(raw["operation"], "workspace buffer operation"),
        request_signature_sha256=_digest(
            raw["request_signature_sha256"], "workspace buffer request signature"
        ),
        request=parse_workspace_buffer_preview_request(raw["request"]),
        layer_ids=_string_tuple(raw["layer_ids"], "workspace buffer layers"),
        native_crs=_exact_text(raw["native_crs"], "workspace buffer native CRS"),
        buffer_m=_number(raw["buffer_m"], "workspace buffer distance"),
        semantics=_exact_text(raw["semantics"], "workspace buffer semantics"),
        geometry_type=_exact_text(
            raw["geometry_type"], "workspace buffer geometry type"
        ),
        source_feature_count=_integer(
            raw["source_feature_count"],
            "workspace buffer source feature count",
            positive=True,
        ),
        declared_feature_count=_integer(
            raw["declared_feature_count"],
            "workspace buffer declared feature count",
            positive=True,
        ),
        area_m2=_number(raw["area_m2"], "workspace buffer area"),
        model_area_m2=_optional_number(
            raw["model_area_m2"], "workspace buffer model area"
        ),
        zero_cell_count=_optional_integer(
            raw["zero_cell_count"], "workspace zero-cell count"
        ),
        partial_cell_count=_optional_integer(
            raw["partial_cell_count"], "workspace partial-cell count"
        ),
        full_cell_count=_optional_integer(
            raw["full_cell_count"], "workspace full-cell count"
        ),
        feature_count=_integer(
            raw["feature_count"], "workspace buffer feature count", positive=True
        ),
        feature_collection_json=_exact_text(
            raw["feature_collection_json"], "workspace buffer GeoJSON"
        ),
        feature_collection_sha256=_digest(
            raw["feature_collection_sha256"],
            "workspace buffer GeoJSON sha256",
        ),
        result_signature_sha256=_digest(
            raw["result_signature_sha256"], "workspace buffer result signature"
        ),
    )
    validate_workspace_buffer_preview_result(result)
    return result


__all__ = [
    "WORKSPACE_BUFFER_REQUEST_SCHEMA_VERSION",
    "WORKSPACE_BUFFER_RESULT_SCHEMA_VERSION",
    "WorkspaceBufferPreviewRequest",
    "WorkspaceBufferPreviewResult",
    "WorkspaceBufferSourceBinding",
    "build_catalog_workspace_buffer_preview_request",
    "build_workspace_buffer_preview_request_from_contract",
    "build_workspace_buffer_preview_result",
    "parse_workspace_buffer_preview_request",
    "parse_workspace_buffer_preview_result",
    "replay_catalog_workspace_buffer_preview_result",
    "run_catalog_workspace_buffer_preview_request",
    "validate_workspace_buffer_preview_request",
    "validate_workspace_buffer_preview_request_from_contract",
    "validate_workspace_buffer_preview_result",
    "validate_workspace_buffer_preview_result_from_contract",
]
