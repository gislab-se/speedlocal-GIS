from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from .catalogs import load_analysis, load_region
from .contracts import AnalysisContract, ParameterContract, omit_default_source_base_buffer
from .engine import AnalysisResult, run_analysis_contract
from .validation import validate_contract


REQUEST_SCHEMA_VERSION = "1.0"
ACCESS_SCOPE_KINDS = ("product", "review")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class AppliedGroupRequest:
    group_id: str
    layer_ids: tuple[str, ...]
    parameters: tuple[tuple[str, float], ...]

    def parameter_map(self) -> dict[str, float]:
        return dict(self.parameters)

    def as_dict(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "layer_ids": list(self.layer_ids),
            "parameters": self.parameter_map(),
        }


@dataclass(frozen=True)
class WorkspaceAnalysisRequest:
    schema_version: str
    access_scope: str
    region_id: str
    analysis_id: str
    source_resolution: int
    target_resolution: int
    domain_sha256: str
    contract_signature_sha256: str
    groups: tuple[AppliedGroupRequest, ...]

    @property
    def selected_layer_ids(self) -> tuple[str, ...]:
        return tuple(
            layer_id
            for group in self.groups
            for layer_id in group.layer_ids
        )

    def engine_parameters(self) -> dict[str, dict[str, float]]:
        return {
            layer_id: group.parameter_map()
            for group in self.groups
            for layer_id in group.layer_ids
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "region_id": self.region_id,
            "analysis_id": self.analysis_id,
            "source_resolution": self.source_resolution,
            "target_resolution": self.target_resolution,
            "domain_sha256": self.domain_sha256,
            "contract_signature_sha256": self.contract_signature_sha256,
            "groups": [group.as_dict() for group in self.groups],
        }


def analysis_contract_signature(contract: AnalysisContract) -> str:
    """Return a deterministic signature of the consumed typed contract."""

    payload = json.dumps(
        omit_default_source_base_buffer(contract),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalized_parameter_contracts(
    contract: AnalysisContract,
    layer_ids: Sequence[str],
) -> dict[str, ParameterContract]:
    first = contract.layers[layer_ids[0]].parameters
    for layer_id in layer_ids[1:]:
        if contract.layers[layer_id].parameters != first:
            raise ValueError(
                f"{contract.region_id}/{contract.id} group layers must share "
                "one parameter contract"
            )
    return first


def build_workspace_analysis_request_from_contract(
    contract: AnalysisContract,
    *,
    access_scope: str,
    selected_group_layers: Mapping[str, Sequence[str]],
    group_parameters: Mapping[str, Mapping[str, Any]],
    target_resolution: int | None = None,
) -> WorkspaceAnalysisRequest:
    """Validate one applied UI selection against its manifest contract."""

    validate_contract(contract)
    scope = str(access_scope).strip().lower()
    scope_parts = scope.split(":", 1)
    if (
        len(scope_parts) != 2
        or scope_parts[0] not in ACCESS_SCOPE_KINDS
        or scope_parts[1] != contract.region_id.lower()
    ):
        raise ValueError(
            "Workspace access_scope must be product:<region> or review:<region>"
        )
    if not isinstance(selected_group_layers, Mapping):
        raise TypeError("selected_group_layers must be an object")
    if not isinstance(group_parameters, Mapping):
        raise TypeError("group_parameters must be an object")
    unknown_groups = set(selected_group_layers) - set(contract.groups)
    if unknown_groups:
        raise ValueError(
            f"{contract.region_id}/{contract.id} request has unknown groups: "
            f"{sorted(unknown_groups)}"
        )
    unknown_parameter_groups = set(group_parameters) - set(contract.groups)
    if unknown_parameter_groups:
        raise ValueError(
            f"{contract.region_id}/{contract.id} parameters have unknown groups: "
            f"{sorted(unknown_parameter_groups)}"
        )
    selected_group_ids = {
        str(group_id)
        for group_id, layer_ids in selected_group_layers.items()
        if layer_ids
    }
    if set(group_parameters) != selected_group_ids:
        raise ValueError(
            "Applied group parameters must exist exactly for selected groups"
        )
    domain = contract.analysis_domain
    if domain is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no analysis domain"
        )
    if target_resolution is None:
        normalized_resolution = int(domain.resolution)
    else:
        if isinstance(target_resolution, bool) or not isinstance(
            target_resolution,
            int,
        ):
            raise TypeError("target_resolution must be an integer")
        normalized_resolution = target_resolution
    available_resolutions = {int(domain.resolution), *domain.rollups.keys()}
    if normalized_resolution not in available_resolutions:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no R"
            f"{normalized_resolution} analysis domain"
        )

    applied_groups: list[AppliedGroupRequest] = []
    for group_id in contract.groups:
        raw_layer_ids = selected_group_layers.get(group_id) or ()
        if isinstance(raw_layer_ids, (str, bytes)):
            raise TypeError(f"{group_id} layer selection must be a list")
        requested = tuple(str(value).strip() for value in raw_layer_ids)
        if not requested:
            continue
        if any(not value for value in requested):
            raise ValueError(f"{group_id} selection contains a blank layer id")
        if len(requested) != len(set(requested)):
            raise ValueError(f"{group_id} selection contains duplicate layer ids")
        declared_order = tuple(
            layer.id
            for layer in contract.layers.values()
            if layer.group_id == group_id
        )
        unknown_layers = set(requested) - set(declared_order)
        if unknown_layers:
            raise ValueError(
                f"{contract.region_id}/{contract.id} {group_id} request has "
                f"unknown layers: {sorted(unknown_layers)}"
            )
        ordered = tuple(
            layer_id for layer_id in declared_order if layer_id in set(requested)
        )
        operations = {contract.layers[layer_id].operation for layer_id in ordered}
        if len(operations) != 1:
            raise ValueError(f"{group_id} layers must share one operation")
        parameter_contracts = _normalized_parameter_contracts(contract, ordered)
        raw_parameters = group_parameters.get(group_id)
        if not isinstance(raw_parameters, Mapping):
            raise ValueError(f"{group_id} applied parameters are missing")
        if set(raw_parameters) != set(parameter_contracts):
            raise ValueError(
                f"{group_id} applied parameters do not match its manifest"
            )
        normalized_parameters: list[tuple[str, float]] = []
        for parameter_id, parameter in parameter_contracts.items():
            value = parameter.validate_value(raw_parameters[parameter_id])
            if not math.isfinite(value):
                raise ValueError(f"{group_id}/{parameter_id} must be finite")
            if parameter.step is not None:
                origin = parameter.minimum if parameter.minimum is not None else 0.0
                step_count = (value - origin) / parameter.step
                if not math.isclose(
                    step_count,
                    round(step_count),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                ):
                    raise ValueError(
                        f"{group_id}/{parameter_id} must align to step "
                        f"{parameter.step} from {origin}"
                    )
            normalized_parameters.append((parameter_id, value))
        applied_groups.append(
            AppliedGroupRequest(
                group_id=group_id,
                layer_ids=ordered,
                parameters=tuple(normalized_parameters),
            )
        )

    return WorkspaceAnalysisRequest(
        schema_version=REQUEST_SCHEMA_VERSION,
        access_scope=scope,
        region_id=contract.region_id,
        analysis_id=contract.id,
        source_resolution=int(domain.resolution),
        target_resolution=normalized_resolution,
        domain_sha256=str(
            domain.sha256
            if normalized_resolution == domain.resolution
            else domain.rollups[normalized_resolution].sha256
        ),
        contract_signature_sha256=analysis_contract_signature(contract),
        groups=tuple(applied_groups),
    )


def parse_workspace_analysis_request(
    value: Mapping[str, Any],
) -> WorkspaceAnalysisRequest:
    """Parse persisted UI state without accepting undeclared compatibility data."""

    if not isinstance(value, Mapping):
        raise TypeError("Workspace request must be an object")
    expected_keys = {
        "schema_version",
        "access_scope",
        "region_id",
        "analysis_id",
        "source_resolution",
        "target_resolution",
        "domain_sha256",
        "contract_signature_sha256",
        "groups",
    }
    if set(value) != expected_keys:
        raise ValueError("Workspace request fields do not match schema 1.0")

    schema_version = value["schema_version"]
    if schema_version != REQUEST_SCHEMA_VERSION:
        raise ValueError("Unsupported workspace request schema version")
    access_scope = value["access_scope"]
    region_id = value["region_id"]
    analysis_id = value["analysis_id"]
    if not all(
        isinstance(item, str) and item.strip() == item and item
        for item in (access_scope, region_id, analysis_id)
    ):
        raise ValueError("Workspace request identities must be non-empty strings")
    if access_scope != access_scope.lower() or region_id != region_id.lower():
        raise ValueError("Workspace request scope and region id must be normalized")

    source_resolution = value["source_resolution"]
    target_resolution = value["target_resolution"]
    if any(
        isinstance(item, bool)
        or not isinstance(item, int)
        or item < 0
        or item > 15
        for item in (source_resolution, target_resolution)
    ):
        raise ValueError("Workspace request resolutions must be H3 integers 0-15")
    domain_sha256 = value["domain_sha256"]
    contract_signature_sha256 = value["contract_signature_sha256"]
    if not all(
        isinstance(item, str) and _SHA256_PATTERN.fullmatch(item)
        for item in (domain_sha256, contract_signature_sha256)
    ):
        raise ValueError("Workspace request hashes must be lowercase SHA-256")

    raw_groups = value["groups"]
    if not isinstance(raw_groups, list):
        raise TypeError("Workspace request groups must be a list")
    groups: list[AppliedGroupRequest] = []
    seen_group_ids: set[str] = set()
    seen_layer_ids: set[str] = set()
    for raw_group in raw_groups:
        if not isinstance(raw_group, Mapping):
            raise TypeError("Workspace request group must be an object")
        if set(raw_group) != {"group_id", "layer_ids", "parameters"}:
            raise ValueError("Workspace request group fields are invalid")
        group_id = raw_group["group_id"]
        if (
            not isinstance(group_id, str)
            or not group_id
            or group_id.strip() != group_id
            or group_id in seen_group_ids
        ):
            raise ValueError("Workspace request group ids must be unique strings")
        seen_group_ids.add(group_id)
        raw_layer_ids = raw_group["layer_ids"]
        if not isinstance(raw_layer_ids, list) or not raw_layer_ids:
            raise ValueError("Selected workspace groups require at least one layer")
        layer_ids: list[str] = []
        for layer_id in raw_layer_ids:
            if (
                not isinstance(layer_id, str)
                or not layer_id
                or layer_id.strip() != layer_id
                or layer_id in seen_layer_ids
            ):
                raise ValueError(
                    "Workspace request layer ids must be unique non-empty strings"
                )
            seen_layer_ids.add(layer_id)
            layer_ids.append(layer_id)
        raw_parameters = raw_group["parameters"]
        if not isinstance(raw_parameters, Mapping):
            raise TypeError("Workspace request parameters must be an object")
        parameters: list[tuple[str, float]] = []
        for parameter_id, raw_value in raw_parameters.items():
            if (
                not isinstance(parameter_id, str)
                or not parameter_id
                or parameter_id.strip() != parameter_id
                or isinstance(raw_value, bool)
                or not isinstance(raw_value, (int, float))
                or not math.isfinite(float(raw_value))
            ):
                raise ValueError("Workspace request parameters must be finite numbers")
            parameters.append((parameter_id, float(raw_value)))
        groups.append(
            AppliedGroupRequest(
                group_id=group_id,
                layer_ids=tuple(layer_ids),
                parameters=tuple(parameters),
            )
        )
    return WorkspaceAnalysisRequest(
        schema_version=schema_version,
        access_scope=access_scope,
        region_id=region_id,
        analysis_id=analysis_id,
        source_resolution=source_resolution,
        target_resolution=target_resolution,
        domain_sha256=domain_sha256,
        contract_signature_sha256=contract_signature_sha256,
        groups=tuple(groups),
    )


def validate_workspace_analysis_request_from_contract(
    contract: AnalysisContract,
    request: WorkspaceAnalysisRequest,
) -> WorkspaceAnalysisRequest:
    """Rebuild an immutable request and reject any persisted-state drift."""

    rebuilt = build_workspace_analysis_request_from_contract(
        contract,
        access_scope=request.access_scope,
        selected_group_layers={
            group.group_id: group.layer_ids for group in request.groups
        },
        group_parameters={
            group.group_id: group.parameter_map() for group in request.groups
        },
        target_resolution=request.target_resolution,
    )
    if rebuilt != request:
        raise ValueError("Workspace request drifted from its manifest contract")
    return request


def retarget_workspace_analysis_request_from_contract(
    contract: AnalysisContract,
    request: WorkspaceAnalysisRequest,
    target_resolution: int,
) -> WorkspaceAnalysisRequest:
    """Rebind one valid request to an explicitly declared domain level.

    The current request is validated before any new request is built. Only the
    target-domain identity may change; access, region, analysis, contract
    signature, source resolution, selected groups, layers and parameters stay
    bound to the supplied analysis contract.
    """

    if not isinstance(contract, AnalysisContract):
        raise TypeError("contract must be an AnalysisContract")
    if not isinstance(request, WorkspaceAnalysisRequest):
        raise TypeError("request must be a WorkspaceAnalysisRequest")
    validate_workspace_analysis_request_from_contract(contract, request)
    if isinstance(target_resolution, bool) or not isinstance(
        target_resolution,
        int,
    ):
        raise TypeError("target_resolution must be an integer")
    domain = contract.analysis_domain
    if domain is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no analysis domain"
        )
    declared_resolutions = {
        int(domain.resolution),
        *(int(resolution) for resolution in domain.rollups),
    }
    if target_resolution not in declared_resolutions:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no R"
            f"{target_resolution} analysis domain"
        )
    retargeted = build_workspace_analysis_request_from_contract(
        contract,
        access_scope=request.access_scope,
        selected_group_layers={
            group.group_id: group.layer_ids for group in request.groups
        },
        group_parameters={
            group.group_id: group.parameter_map() for group in request.groups
        },
        target_resolution=target_resolution,
    )
    if (
        retargeted.schema_version != request.schema_version
        or retargeted.access_scope != request.access_scope
        or retargeted.region_id != request.region_id
        or retargeted.analysis_id != request.analysis_id
        or retargeted.source_resolution != request.source_resolution
        or retargeted.contract_signature_sha256
        != request.contract_signature_sha256
        or retargeted.groups != request.groups
    ):
        raise ValueError(
            "Retargeted workspace request changed a non-domain identity"
        )
    return retargeted


def _authorize_catalog_workspace_analysis_request(
    contract: AnalysisContract,
    request: WorkspaceAnalysisRequest,
    *,
    region: Mapping[str, Any],
    required_capability_id: str | None = None,
) -> WorkspaceAnalysisRequest:
    """Authorize a manifest-valid request against repo-owned route policy."""

    validate_workspace_analysis_request_from_contract(contract, request)
    if required_capability_id is not None and (
        not isinstance(required_capability_id, str)
        or not required_capability_id
        or required_capability_id != required_capability_id.strip()
    ):
        raise PermissionError(
            "Workspace consumer capability must be an exact non-empty id"
        )
    if str(region.get("region_id") or "").strip().lower() != request.region_id:
        raise PermissionError("Workspace request region is not catalog-authorized")

    scope_kind, scope_region_id = request.access_scope.split(":", 1)
    if scope_region_id != request.region_id:
        raise PermissionError("Workspace request scope is bound to another region")

    if scope_kind == "product":
        landing_card = region.get("landing_card")
        behavior_reference = region.get("behavior_reference")
        if not isinstance(landing_card, Mapping) or not isinstance(
            behavior_reference,
            Mapping,
        ):
            raise PermissionError(
                f"Product access is disabled for region: {request.region_id}"
            )
        from .access_policy import validate_product_access_dimensions

        try:
            validate_product_access_dimensions(
                lifecycle=region.get("status"),
                behavior_reference_status=behavior_reference.get("status"),
                landing_card_enabled=landing_card.get("enabled"),
            )
        except (TypeError, ValueError) as exc:
            raise PermissionError(
                f"Product access is disabled for region: {request.region_id}"
            ) from exc
        return request

    if scope_kind != "review":
        raise PermissionError(
            f"Unsupported workspace access mode: {scope_kind or '<blank>'}"
        )

    # Imported lazily so the generic from-contract fixture runner has no
    # dependency on the public catalog or the workspace access model.
    from .access_policy import ACCESS_TRUST_CLASSIFICATION_SET
    from .workspace import load_review_access

    try:
        review_access = load_review_access(request.region_id)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        raise PermissionError(
            f"Review access is disabled for region: {request.region_id}"
        ) from exc

    if (
        review_access.mode != "review"
        or review_access.surface != "shared_workspace"
        or review_access.access_classification
        not in ACCESS_TRUST_CLASSIFICATION_SET
        or review_access.requires_environment_allowlist is not True
    ):
        raise PermissionError("Review access policy is not valid for execution")
    if (
        required_capability_id is not None
        and required_capability_id not in review_access.allowed_capabilities
    ):
        raise PermissionError(
            "Workspace consumer capability is not allowed in review: "
            f"{required_capability_id}"
        )
    # Complete review workspaces may explicitly remove every filter. Their
    # validated base surface and area capability remain required; incomplete
    # slice-only reviews retain the existing neutral-preview boundary.
    if not request.groups and not (
        "context_runtime_manifest" in region
        and f"{request.analysis_id}.area" in review_access.allowed_capabilities
    ):
        raise PermissionError("Review execution requires an applied slice")

    allowed_slices = {
        (policy.analysis_id, policy.group_id): policy
        for policy in review_access.allowed_slices
    }
    for group in request.groups:
        identity = (request.analysis_id, group.group_id)
        policy = allowed_slices.get(identity)
        if policy is None:
            raise PermissionError(
                "Workspace request contains a slice that review access does "
                f"not allow: {request.analysis_id}/{group.group_id}"
            )
        if (
            policy.apply_required is not True
            or not isinstance(policy.auto_select_sources, bool)
            or tuple(parameter_id for parameter_id, _value in group.parameters)
            != policy.explicit_parameters
        ):
            raise PermissionError(
                "Workspace request does not match the declared review policy: "
                f"{request.analysis_id}/{group.group_id}"
            )
    return request


def authorize_catalog_workspace_analysis_request(
    request: WorkspaceAnalysisRequest,
    *,
    required_capability_id: str | None = None,
) -> WorkspaceAnalysisRequest:
    """Authorize one request against the indexed region's product/review gate.

    This is deliberately separate from the pure from-contract validator so a
    non-indexed portability fixture can still prove the generic request and
    engine chain without gaining product or review access.
    """

    contract = load_analysis(request.region_id, request.analysis_id)
    region = load_region(request.region_id)
    return _authorize_catalog_workspace_analysis_request(
        contract,
        request,
        region=region,
        required_capability_id=required_capability_id,
    )


def build_workspace_analysis_request(
    region_id: str,
    analysis_id: str,
    **kwargs: Any,
) -> WorkspaceAnalysisRequest:
    return build_workspace_analysis_request_from_contract(
        load_analysis(region_id, analysis_id),
        **kwargs,
    )


def run_workspace_analysis_request_from_contract(
    contract: AnalysisContract,
    request: WorkspaceAnalysisRequest,
) -> AnalysisResult:
    """Run exactly the immutable manifest-bound request through the engine."""

    validate_workspace_analysis_request_from_contract(contract, request)
    return run_analysis_contract(
        contract,
        list(request.selected_layer_ids),
        request.engine_parameters(),
        target_resolution=request.target_resolution,
    )


def run_workspace_analysis_request(
    request: WorkspaceAnalysisRequest,
) -> AnalysisResult:
    contract = load_analysis(request.region_id, request.analysis_id)
    region = load_region(request.region_id)
    _authorize_catalog_workspace_analysis_request(
        contract,
        request,
        region=region,
    )
    return run_workspace_analysis_request_from_contract(contract, request)


__all__ = [
    "ACCESS_SCOPE_KINDS",
    "AppliedGroupRequest",
    "REQUEST_SCHEMA_VERSION",
    "WorkspaceAnalysisRequest",
    "analysis_contract_signature",
    "authorize_catalog_workspace_analysis_request",
    "build_workspace_analysis_request",
    "build_workspace_analysis_request_from_contract",
    "parse_workspace_analysis_request",
    "retarget_workspace_analysis_request_from_contract",
    "run_workspace_analysis_request",
    "run_workspace_analysis_request_from_contract",
    "validate_workspace_analysis_request_from_contract",
]
