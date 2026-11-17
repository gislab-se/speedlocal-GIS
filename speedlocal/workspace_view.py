from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from pyproj import CRS
from shapely.geometry import shape

from .catalogs import load_analysis
from .contracts import SUPPORTED_OPERATIONS, AnalysisContract
from .engine import AnalysisResult
from .sources import (
    load_analysis_contract_domain_display_artifact,
    read_layer_geojson_bytes,
)
from .validation import validate_contract, validate_layer
from .workspace_request import (
    WorkspaceAnalysisRequest,
    authorize_catalog_workspace_analysis_request,
    build_workspace_analysis_request_from_contract,
    run_workspace_analysis_request_from_contract,
    validate_workspace_analysis_request_from_contract,
)


@dataclass(frozen=True)
class WorkspaceDomainView:
    """Exact analysis-domain bytes used by one applied workspace slice."""

    region_id: str
    analysis_id: str
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


@dataclass(frozen=True)
class WorkspaceSourceView:
    """One selected, validated source geometry ready for the shared map."""

    layer_id: str
    group_id: str
    label: str
    geometry_family: str
    processing_adapter: str
    source_sha256: str
    byte_count: int
    declared_feature_count: int
    display_feature_count: int
    feature_collection_json: str
    source_color: str
    point_radius: int
    quality_flag: str | None


@dataclass(frozen=True)
class WorkspaceGroupResultView:
    """Operation-aware summary for one applied standard group."""

    group_id: str
    label: str
    operation: str
    result_semantics: str
    layer_ids: tuple[str, ...]
    threshold_m: float
    cell_count: int
    blocked_cell_count: int
    accepted_cell_count: int
    coverage_missing_cell_count: int
    mean_acceptance: float


@dataclass(frozen=True)
class WorkspaceGroupProbe:
    """Machine-readable readiness for one shared workspace group."""

    region_id: str
    analysis_id: str
    group_id: str
    status: str
    detail: str
    layer_ids: tuple[str, ...]
    operations: tuple[str, ...]


@dataclass(frozen=True)
class AppliedWorkspaceSliceView:
    """Single-source-of-truth payload for shared map and result consumers."""

    request: WorkspaceAnalysisRequest
    domain: WorkspaceDomainView
    sources: tuple[WorkspaceSourceView, ...]
    result: AnalysisResult
    groups: tuple[WorkspaceGroupResultView, ...]


def _validate_crs84(payload: dict[str, Any], *, label: str) -> None:
    declaration = payload.get("crs")
    if declaration is None:
        # RFC 7946 GeoJSON without an explicit CRS is WGS84 longitude/latitude.
        return
    if (
        not isinstance(declaration, dict)
        or declaration.get("type") != "name"
        or not isinstance(declaration.get("properties"), dict)
    ):
        raise ValueError(f"{label} CRS declaration is invalid")
    try:
        declared = CRS.from_user_input(declaration["properties"].get("name"))
    except Exception as exc:
        raise ValueError(f"{label} CRS declaration is invalid") from exc
    if not declared.equals(CRS.from_epsg(4326), ignore_axis_order=True):
        raise ValueError(f"{label} must use CRS84/EPSG:4326 for map display")


def _load_source_view(
    contract: AnalysisContract,
    layer_id: str,
) -> WorkspaceSourceView:
    layer = contract.layers[layer_id]
    validated = validate_layer(layer)
    if layer.ui is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id}/{layer_id} has no shared-map "
            "UI contract"
        )
    try:
        source_bytes = read_layer_geojson_bytes(validated.assets)
    except OSError as exc:
        raise ValueError(f"Layer {layer_id} source geometry is unreadable") from exc
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if (
        source_sha256 != validated.assets.geojson_sha256
        or len(source_bytes) != validated.assets.geojson_bytes
    ):
        raise ValueError(
            f"Layer {layer_id} source geometry changed after validation"
        )
    try:
        source_text = source_bytes.decode("utf-8")
        payload = json.loads(source_text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Layer {layer_id} source geometry is unreadable") from exc
    features = payload.get("features") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("type") != "FeatureCollection"
        or not isinstance(features, list)
        or not features
    ):
        raise ValueError(
            f"Layer {layer_id} source geometry must be a non-empty "
            "FeatureCollection"
        )
    _validate_crs84(payload, label=f"Layer {layer_id} source geometry")
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(
                f"Layer {layer_id} source feature {index} is invalid"
            )
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            raise ValueError(
                f"Layer {layer_id} source feature {index} has no geometry"
            )
        try:
            value = shape(geometry)
        except Exception as exc:
            raise ValueError(
                f"Layer {layer_id} source feature {index} is unreadable"
            ) from exc
        if value.is_empty:
            raise ValueError(
                f"Layer {layer_id} source feature {index} is empty"
            )
        if (
            not value.is_valid
            and layer.source.geometry_validity_policy != "make_valid"
        ):
            raise ValueError(
                f"Layer {layer_id} source feature {index} is invalid"
            )
        bounds = value.bounds
        if (
            len(bounds) != 4
            or not all(math.isfinite(coordinate) for coordinate in bounds)
            or bounds[0] < -180.0
            or bounds[2] > 180.0
            or bounds[1] < -90.0
            or bounds[3] > 90.0
        ):
            raise ValueError(
                f"Layer {layer_id} source feature {index} is outside CRS84"
            )

    return WorkspaceSourceView(
        layer_id=layer.id,
        group_id=layer.group_id,
        label=layer.label,
        geometry_family=validated.geometry_family,
        processing_adapter=validated.processing_adapter,
        source_sha256=source_sha256,
        byte_count=len(source_bytes),
        declared_feature_count=validated.assets.feature_count,
        display_feature_count=len(features),
        feature_collection_json=source_text,
        source_color=layer.ui.source_color,
        point_radius=layer.ui.point_radius,
        quality_flag=layer.ui.quality_flag,
    )


def build_workspace_slice_view_from_contract(
    contract: AnalysisContract,
    request: WorkspaceAnalysisRequest,
) -> AppliedWorkspaceSliceView:
    """Build a region-neutral applied map/result view from one exact request.

    The caller supplies a typed analysis contract, which keeps this function
    independent of the public catalog and allows a non-indexed portability
    fixture to exercise the production data path. Contract, request, domain,
    selected sources, and engine result all fail closed before a view is
    returned.
    """

    validate_contract(contract)
    validate_workspace_analysis_request_from_contract(contract, request)
    domain_artifact = load_analysis_contract_domain_display_artifact(
        contract,
        request.target_resolution,
    )
    if (domain_artifact.upstream_source_sha256 or domain_artifact.source_sha256) != request.domain_sha256:
        raise ValueError("Workspace domain bytes do not match the applied request")
    sources = tuple(
        _load_source_view(contract, layer_id)
        for layer_id in request.selected_layer_ids
    )
    result = run_workspace_analysis_request_from_contract(contract, request)
    if (
        result.region_id != request.region_id
        or result.analysis_id != request.analysis_id
    ):
        raise ValueError("Workspace engine result identity drifted from request")
    if tuple(layer.layer_id for layer in result.layers) != request.selected_layer_ids:
        raise ValueError("Workspace engine result layers drifted from request")
    if tuple(group.group_id for group in result.groups) != tuple(
        group.group_id for group in request.groups
    ):
        raise ValueError("Workspace engine result groups drifted from request")
    domain_payload = json.loads(domain_artifact.feature_collection_json)
    domain_cell_ids = tuple(
        sorted(
            str(feature["properties"][domain_artifact.id_field])
            for feature in domain_payload["features"]
        )
    )
    domain_cell_ids_sha256 = hashlib.sha256(
        "".join(f"{cell_id}\n" for cell_id in domain_cell_ids).encode("utf-8")
    ).hexdigest()
    if (
        len(domain_cell_ids) != domain_artifact.cell_count
        or domain_cell_ids_sha256 != domain_artifact.cell_ids_sha256
    ):
        raise ValueError("Workspace domain identity drifted after validation")
    domain_cell_id_set = frozenset(domain_cell_ids)
    for group in result.groups:
        result_cell_ids = tuple(cell.cell_id for cell in group.cells)
        result_cell_id_set = frozenset(result_cell_ids)
        result_cell_ids_sha256 = hashlib.sha256(
            "".join(
                f"{cell_id}\n" for cell_id in sorted(result_cell_id_set)
            ).encode("utf-8")
        ).hexdigest()
        if (
            len(result_cell_ids) != len(result_cell_id_set)
            or group.cell_count != domain_artifact.cell_count
            or result_cell_id_set != domain_cell_id_set
            or result_cell_ids_sha256 != domain_artifact.cell_ids_sha256
        ):
            raise ValueError(
                f"Workspace result group {group.group_id} does not match the "
                "applied domain identity"
            )

    group_views: list[WorkspaceGroupResultView] = []
    for group in result.groups:
        operations = {
            contract.layers[layer_id].operation for layer_id in group.layer_ids
        }
        if len(operations) != 1:
            raise ValueError(
                f"Workspace result group {group.group_id} mixes operations"
            )
        operation = operations.pop()
        if operation in {"distance_exclusion", "hard_exclusion"}:
            semantics = "blocked_means_excluded"
        elif operation == "proximity_feasibility":
            semantics = "blocked_means_outside_required_proximity"
        else:
            raise ValueError(
                f"Workspace result group {group.group_id} has unsupported "
                f"operation: {operation}"
            )
        group_ui = (
            contract.ui.groups.get(group.group_id)
            if contract.ui is not None
            else None
        )
        group_views.append(
            WorkspaceGroupResultView(
                group_id=group.group_id,
                label=(
                    str(group_ui.label)
                    if group_ui is not None
                    else str(group.group_id)
                ),
                operation=operation,
                result_semantics=semantics,
                layer_ids=group.layer_ids,
                threshold_m=group.threshold_m,
                cell_count=group.cell_count,
                blocked_cell_count=group.blocked_cell_count,
                accepted_cell_count=group.cell_count - group.blocked_cell_count,
                coverage_missing_cell_count=sum(
                    int(cell.coverage_missing) for cell in group.cells
                ),
                mean_acceptance=group.mean_acceptance,
            )
        )

    return AppliedWorkspaceSliceView(
        request=request,
        domain=WorkspaceDomainView(
            region_id=domain_artifact.region_id,
            analysis_id=contract.id,
            resolution=domain_artifact.resolution,
            source_sha256=domain_artifact.source_sha256,
            upstream_source_sha256=domain_artifact.upstream_source_sha256,
            runtime_revision_sha256=domain_artifact.runtime_revision_sha256,
            cell_ids_sha256=domain_artifact.cell_ids_sha256,
            cell_count=domain_artifact.cell_count,
            total_area_km2=domain_artifact.total_area_km2,
            id_field=domain_artifact.id_field,
            area_field=domain_artifact.area_field,
            area_unit=domain_artifact.area_unit,
            feature_collection_json=domain_artifact.feature_collection_json,
        ),
        sources=sources,
        result=result,
        groups=tuple(group_views),
    )


def build_catalog_workspace_slice_view(
    request: WorkspaceAnalysisRequest,
) -> AppliedWorkspaceSliceView:
    """Authorize a catalog route, then build the same generic slice view."""

    authorize_catalog_workspace_analysis_request(request)
    contract = load_analysis(request.region_id, request.analysis_id)
    return build_workspace_slice_view_from_contract(contract, request)


def _group_probe(
    contract: AnalysisContract,
    group_id: str,
    *,
    status: str,
    detail: str,
    layer_ids: tuple[str, ...] = (),
    operations: tuple[str, ...] = (),
) -> WorkspaceGroupProbe:
    return WorkspaceGroupProbe(
        region_id=contract.region_id,
        analysis_id=contract.id,
        group_id=group_id,
        status=status,
        detail=detail,
        layer_ids=layer_ids,
        operations=operations,
    )


def probe_workspace_group_from_contract(
    contract: AnalysisContract,
    group_id: str,
) -> WorkspaceGroupProbe:
    """Probe one group through the same domain/source/engine view chain.

    The probe is diagnostic state, not route authorization. It turns expected
    contract and runtime failures into the shared readiness vocabulary while
    leaving programming errors visible.
    """

    normalized_group_id = str(group_id or "").strip()
    if (
        not normalized_group_id
        or normalized_group_id not in contract.groups
        or contract.analysis_domain is None
    ):
        return _group_probe(
            contract,
            normalized_group_id,
            status="missing_manifest",
            detail="Analysis domain or requested group is not declared.",
        )
    layers = tuple(
        layer
        for layer in contract.layers.values()
        if layer.group_id == normalized_group_id
    )
    layer_ids = tuple(layer.id for layer in layers)
    operations = tuple(dict.fromkeys(layer.operation for layer in layers))
    if (
        not layers
        or contract.ui is None
        or normalized_group_id not in contract.ui.groups
        or any(layer.ui is None for layer in layers)
    ):
        return _group_probe(
            contract,
            normalized_group_id,
            status="missing_manifest",
            detail="Group layers or shared UI metadata are not declared.",
            layer_ids=layer_ids,
            operations=operations,
        )
    unsupported = tuple(
        operation
        for operation in operations
        if operation not in SUPPORTED_OPERATIONS
    )
    if unsupported:
        return _group_probe(
            contract,
            normalized_group_id,
            status="not_implemented",
            detail=f"Unsupported operations: {', '.join(unsupported)}.",
            layer_ids=layer_ids,
            operations=operations,
        )
    try:
        validate_contract(contract)
    except (TypeError, ValueError) as exc:
        return _group_probe(
            contract,
            normalized_group_id,
            status="missing_manifest",
            detail=str(exc),
            layer_ids=layer_ids,
            operations=operations,
        )

    parameter_contracts = layers[0].parameters
    selected = {normalized_group_id: layer_ids}
    parameters = {
        normalized_group_id: {
            parameter_id: parameter.default
            for parameter_id, parameter in parameter_contracts.items()
        }
    }
    try:
        request = build_workspace_analysis_request_from_contract(
            contract,
            access_scope=f"review:{contract.region_id}",
            selected_group_layers=selected,
            group_parameters=parameters,
            target_resolution=contract.analysis_domain.resolution,
        )
        build_workspace_slice_view_from_contract(contract, request)
    except (FileNotFoundError, KeyError, OSError) as exc:
        return _group_probe(
            contract,
            normalized_group_id,
            status="missing_data",
            detail=str(exc),
            layer_ids=layer_ids,
            operations=operations,
        )
    except NotImplementedError as exc:
        return _group_probe(
            contract,
            normalized_group_id,
            status="not_implemented",
            detail=str(exc),
            layer_ids=layer_ids,
            operations=operations,
        )
    except (TypeError, ValueError) as exc:
        return _group_probe(
            contract,
            normalized_group_id,
            status="not_validated",
            detail=str(exc),
            layer_ids=layer_ids,
            operations=operations,
        )
    return _group_probe(
        contract,
        normalized_group_id,
        status="available",
        detail="Domain, selected sources, operation, map bytes, and result passed.",
        layer_ids=layer_ids,
        operations=operations,
    )


def probe_catalog_workspace_group(
    region_id: str,
    analysis_id: str,
    group_id: str,
) -> WorkspaceGroupProbe:
    """Load an indexed contract and run the pure group-readiness probe."""

    normalized_region_id = str(region_id or "").strip().lower()
    normalized_analysis_id = str(analysis_id or "").strip()
    normalized_group_id = str(group_id or "").strip()
    try:
        contract = load_analysis(normalized_region_id, normalized_analysis_id)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        return WorkspaceGroupProbe(
            region_id=normalized_region_id,
            analysis_id=normalized_analysis_id,
            group_id=normalized_group_id,
            status="missing_manifest",
            detail=str(exc),
            layer_ids=(),
            operations=(),
        )
    return probe_workspace_group_from_contract(contract, normalized_group_id)


__all__ = [
    "AppliedWorkspaceSliceView",
    "WorkspaceDomainView",
    "WorkspaceGroupResultView",
    "WorkspaceGroupProbe",
    "WorkspaceSourceView",
    "build_catalog_workspace_slice_view",
    "build_workspace_slice_view_from_contract",
    "probe_catalog_workspace_group",
    "probe_workspace_group_from_contract",
]
