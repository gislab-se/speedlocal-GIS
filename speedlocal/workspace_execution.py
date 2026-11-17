from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
import re
from typing import Any, Mapping

from .catalogs import load_analysis
from .workspace_app_adapter import (
    WORKSPACE_APP_MAP_LAYER_PROFILES,
    WorkspaceAppAdapter,
    build_workspace_app_adapter,
    parse_workspace_app_adapter,
    validate_workspace_app_adapter_from_presentations,
)
from .workspace_area import (
    WorkspaceAreaExecutionResult,
    parse_workspace_area_execution_result,
    run_catalog_workspace_area_request,
    validate_workspace_area_execution_result,
    validate_workspace_area_execution_result_from_contract,
)
from .workspace_buffer import (
    WorkspacePreparedBufferPreview,
    WorkspaceBufferPreviewResult,
    build_catalog_workspace_buffer_preview_request,
    derive_catalog_workspace_buffer_preview,
    parse_workspace_buffer_preview_result,
    run_catalog_workspace_buffer_preview_request,
    validate_workspace_buffer_preview_result,
)
from .workspace_presentation import (
    WorkspaceAnalysisPresentation,
    build_workspace_analysis_presentation,
    parse_workspace_analysis_presentation,
    validate_workspace_analysis_presentation,
)
from .workspace_request import (
    WorkspaceAnalysisRequest,
    parse_workspace_analysis_request,
    authorize_catalog_workspace_analysis_request,
    retarget_workspace_analysis_request_from_contract,
    validate_workspace_analysis_request_from_contract,
)
from .workspace_view import (
    build_catalog_workspace_slice_view,
    build_workspace_slice_view_from_contract,
)


WORKSPACE_EXECUTION_SCHEMA_VERSION = "1.1"
WORKSPACE_EXECUTION_RESOLUTION_PLAN_SCHEMA_VERSION = "1.0"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


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
        raise ValueError(f"{label} must be a non-empty exact string")
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields do not match the current schema")


class WorkspaceExecutionState(str, Enum):
    """Explicit lifecycle state for one analysis execution input."""

    NEUTRAL_PREVIEW = "neutral_preview"
    APPLIED = "applied"


class WorkspaceAreaExecution(str, Enum):
    """Explicit area-capability authority for one analysis input."""

    NOT_AVAILABLE = "not_available"
    EXECUTE = "execute"


@dataclass(frozen=True)
class WorkspaceAnalysisExecutionInput:
    """One immutable request plus its explicit execution authority."""

    request: WorkspaceAnalysisRequest
    execution_state: WorkspaceExecutionState
    area_execution: WorkspaceAreaExecution

    @property
    def is_applied(self) -> bool:
        return self.execution_state is WorkspaceExecutionState.APPLIED

    def as_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.as_dict(),
            "execution_state": self.execution_state.value,
            "area_execution": self.area_execution.value,
        }


@dataclass(frozen=True)
class WorkspaceExecutionBinding:
    """One analysis execution retained from request through presentation."""

    execution_input: WorkspaceAnalysisExecutionInput
    buffer_previews: tuple[WorkspaceBufferPreviewResult, ...]
    area_result: WorkspaceAreaExecutionResult | None
    presentation: WorkspaceAnalysisPresentation

    @property
    def request(self) -> WorkspaceAnalysisRequest:
        return self.execution_input.request

    @property
    def execution_state(self) -> WorkspaceExecutionState:
        return self.execution_input.execution_state

    def as_dict(self) -> dict[str, Any]:
        return {
            "execution_input": self.execution_input.as_dict(),
            "buffer_previews": [value.as_dict() for value in self.buffer_previews],
            "area_result": (
                None if self.area_result is None else self.area_result.as_dict()
            ),
            "presentation": self.presentation.as_dict(),
        }


@dataclass(frozen=True)
class WorkspaceExecutionBundle:
    """One immutable analysis-to-renderer result for an access surface."""

    schema_version: str
    access_scope: str
    region_id: str
    target_resolution: int
    bindings: tuple[WorkspaceExecutionBinding, ...]
    app_adapter: WorkspaceAppAdapter
    execution_signature_sha256: str

    @property
    def analysis_ids(self) -> tuple[str, ...]:
        return tuple(value.request.analysis_id for value in self.bindings)

    @property
    def execution_inputs(self) -> tuple[WorkspaceAnalysisExecutionInput, ...]:
        return tuple(value.execution_input for value in self.bindings)

    @property
    def area_results(self) -> tuple[WorkspaceAreaExecutionResult, ...]:
        return tuple(
            value.area_result
            for value in self.bindings
            if value.area_result is not None
        )

    def binding(self, analysis_id: str) -> WorkspaceExecutionBinding:
        normalized = _exact_text(analysis_id, "workspace execution analysis")
        try:
            return next(
                value
                for value in self.bindings
                if value.request.analysis_id == normalized
            )
        except StopIteration as exc:
            raise KeyError(
                f"Workspace execution has no analysis {normalized!r}"
            ) from exc

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "region_id": self.region_id,
            "target_resolution": self.target_resolution,
            "bindings": [value.as_dict() for value in self.bindings],
            "app_adapter": self.app_adapter.as_dict(),
            "execution_signature_sha256": self.execution_signature_sha256,
        }


@dataclass(frozen=True)
class WorkspaceExecutionResolutionPlan:
    """One signed display/analysis execution plan over applied inputs."""

    schema_version: str
    access_scope: str
    region_id: str
    display_resolution: int
    analysis_resolution: int
    execution_inputs: tuple[WorkspaceAnalysisExecutionInput, ...]
    analysis_bundle: WorkspaceExecutionBundle
    display_bundle: WorkspaceExecutionBundle
    plan_signature_sha256: str

    @property
    def reuses_analysis_bundle(self) -> bool:
        return self.display_bundle is self.analysis_bundle

    @property
    def analysis_ids(self) -> tuple[str, ...]:
        return tuple(value.request.analysis_id for value in self.execution_inputs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "region_id": self.region_id,
            "display_resolution": self.display_resolution,
            "analysis_resolution": self.analysis_resolution,
            "execution_inputs": [
                value.as_dict() for value in self.execution_inputs
            ],
            "analysis_bundle": self.analysis_bundle.as_dict(),
            "display_bundle": self.display_bundle.as_dict(),
            "plan_signature_sha256": self.plan_signature_sha256,
        }


def _binding_signature_payload(
    binding: WorkspaceExecutionBinding,
) -> dict[str, Any]:
    return {
        "analysis_id": binding.request.analysis_id,
        "execution_input": binding.execution_input.as_dict(),
        "presentation_signature_sha256": (
            binding.presentation.presentation_signature_sha256
        ),
        "buffer_result_signatures": [
            {
                "group_id": value.group_id,
                "result_signature_sha256": value.result_signature_sha256,
            }
            for value in binding.buffer_previews
        ],
        "area_result_signature_sha256": (
            None
            if binding.area_result is None
            else binding.area_result.result_signature_sha256
        ),
    }


def _execution_signature_payload(bundle: WorkspaceExecutionBundle) -> dict[str, Any]:
    return {
        "schema_version": bundle.schema_version,
        "access_scope": bundle.access_scope,
        "region_id": bundle.region_id,
        "target_resolution": bundle.target_resolution,
        "bindings": [
            _binding_signature_payload(value) for value in bundle.bindings
        ],
        "app_adapter_signature_sha256": (
            bundle.app_adapter.adapter_signature_sha256
        ),
    }


def _resolution_plan_signature_payload(
    plan: WorkspaceExecutionResolutionPlan,
) -> dict[str, Any]:
    return {
        "schema_version": plan.schema_version,
        "access_scope": plan.access_scope,
        "region_id": plan.region_id,
        "display_resolution": plan.display_resolution,
        "analysis_resolution": plan.analysis_resolution,
        "execution_inputs": [value.as_dict() for value in plan.execution_inputs],
        "analysis_bundle_signature_sha256": (
            plan.analysis_bundle.execution_signature_sha256
        ),
        "display_bundle_signature_sha256": (
            plan.display_bundle.execution_signature_sha256
        ),
    }


def validate_workspace_analysis_execution_input(
    execution_input: WorkspaceAnalysisExecutionInput,
) -> None:
    if not isinstance(execution_input, WorkspaceAnalysisExecutionInput):
        raise TypeError("workspace analysis execution input has an invalid type")
    request = parse_workspace_analysis_request(execution_input.request.as_dict())
    if request != execution_input.request:
        raise ValueError("Workspace execution request is not strict-roundtrip safe")
    if not isinstance(execution_input.execution_state, WorkspaceExecutionState):
        raise TypeError("Workspace execution state has an invalid type")
    if not isinstance(execution_input.area_execution, WorkspaceAreaExecution):
        raise TypeError("Workspace area execution authority has an invalid type")
    if (
        execution_input.execution_state is WorkspaceExecutionState.NEUTRAL_PREVIEW
        and request.groups
    ):
        raise ValueError("A neutral workspace preview cannot contain applied groups")
    if (
        execution_input.execution_state is WorkspaceExecutionState.NEUTRAL_PREVIEW
        and execution_input.area_execution is WorkspaceAreaExecution.EXECUTE
    ):
        raise ValueError("A neutral workspace preview cannot execute area analysis")


_EXECUTION_INPUT_KEYS = {"request", "execution_state", "area_execution"}


def parse_workspace_analysis_execution_input(
    value: Any,
) -> WorkspaceAnalysisExecutionInput:
    raw = _mapping(value, "workspace analysis execution input")
    _exact_keys(
        raw,
        _EXECUTION_INPUT_KEYS,
        "workspace analysis execution input",
    )
    raw_state = _exact_text(raw["execution_state"], "workspace execution state")
    try:
        execution_state = WorkspaceExecutionState(raw_state)
    except ValueError as exc:
        raise ValueError(
            f"Unsupported workspace execution state: {raw_state!r}"
        ) from exc
    raw_area_execution = _exact_text(
        raw["area_execution"],
        "workspace area execution authority",
    )
    try:
        area_execution = WorkspaceAreaExecution(raw_area_execution)
    except ValueError as exc:
        raise ValueError(
            "Unsupported workspace area execution authority: "
            f"{raw_area_execution!r}"
        ) from exc
    execution_input = WorkspaceAnalysisExecutionInput(
        request=parse_workspace_analysis_request(raw["request"]),
        execution_state=execution_state,
        area_execution=area_execution,
    )
    validate_workspace_analysis_execution_input(execution_input)
    return execution_input


def validate_workspace_execution_binding(
    binding: WorkspaceExecutionBinding,
) -> None:
    if not isinstance(binding, WorkspaceExecutionBinding):
        raise TypeError("workspace execution binding has an invalid type")
    validate_workspace_analysis_execution_input(binding.execution_input)
    request = binding.request
    if not isinstance(binding.buffer_previews, tuple):
        raise TypeError("Workspace execution buffer previews must be immutable")
    for preview in binding.buffer_previews:
        validate_workspace_buffer_preview_result(preview)
    validate_workspace_analysis_presentation(binding.presentation)
    presentation = binding.presentation
    if (
        presentation.request != request
        or presentation.access_scope != request.access_scope
        or presentation.region_id != request.region_id
        or presentation.analysis_id != request.analysis_id
        or presentation.target_resolution != request.target_resolution
    ):
        raise ValueError("Workspace execution presentation escaped its request")

    expected_group_ids = tuple(group.group_id for group in request.groups)
    actual_group_ids = tuple(value.group_id for value in binding.buffer_previews)
    if actual_group_ids != expected_group_ids:
        raise ValueError("Workspace execution buffer order drifted from its request")
    for preview in binding.buffer_previews:
        if (
            preview.access_scope != request.access_scope
            or preview.region_id != request.region_id
            or preview.analysis_id != request.analysis_id
            or preview.request.applied_request != request
        ):
            raise ValueError("Workspace execution buffer escaped its request")
    if presentation.buffer_result_signatures != tuple(
        (value.group_id, value.result_signature_sha256)
        for value in binding.buffer_previews
    ):
        raise ValueError("Workspace execution presentation drifted from its buffers")

    area = binding.area_result
    if area is None:
        if binding.execution_input.area_execution is WorkspaceAreaExecution.EXECUTE:
            raise ValueError("An area-enabled workspace execution omitted its result")
        if (
            presentation.area_capability_id is not None
            or presentation.area_result_signature_sha256 is not None
        ):
            raise ValueError("Workspace execution omitted its presented area result")
    else:
        if binding.execution_input.area_execution is not WorkspaceAreaExecution.EXECUTE:
            raise ValueError("An area-disabled workspace execution produced a result")
        validate_workspace_area_execution_result(area)
        if (
            area.request != request
            or area.access_scope != request.access_scope
            or area.region_id != request.region_id
            or area.analysis_id != request.analysis_id
            or area.target_resolution != request.target_resolution
            or presentation.area_capability_id != area.capability_id
            or presentation.area_result_signature_sha256
            != area.result_signature_sha256
        ):
            raise ValueError("Workspace execution area result escaped its request")


def _validate_constructed_workspace_execution_binding(
    binding: WorkspaceExecutionBinding,
) -> None:
    """Check links between values returned by the trusted builders.

    Each source value has already passed its complete public validator in the
    builder that returned it. Replaying those validators here would parse and
    hash the same large geometry payloads without adding a new trust boundary.
    """

    if not isinstance(binding, WorkspaceExecutionBinding):
        raise TypeError("workspace execution binding has an invalid type")
    if not isinstance(binding.execution_input, WorkspaceAnalysisExecutionInput):
        raise TypeError("Workspace execution input has an invalid type")
    if not isinstance(binding.buffer_previews, tuple) or any(
        not isinstance(value, WorkspaceBufferPreviewResult)
        for value in binding.buffer_previews
    ):
        raise TypeError("Workspace execution buffer previews must be immutable")
    if not isinstance(binding.presentation, WorkspaceAnalysisPresentation):
        raise TypeError("Workspace execution presentation has an invalid type")

    request = binding.request
    presentation = binding.presentation
    if (
        presentation.request != request
        or presentation.access_scope != request.access_scope
        or presentation.region_id != request.region_id
        or presentation.analysis_id != request.analysis_id
        or presentation.target_resolution != request.target_resolution
    ):
        raise ValueError("Workspace execution presentation escaped its request")

    expected_group_ids = tuple(group.group_id for group in request.groups)
    if tuple(value.group_id for value in binding.buffer_previews) != (
        expected_group_ids
    ):
        raise ValueError("Workspace execution buffer order drifted from its request")
    if any(
        preview.access_scope != request.access_scope
        or preview.region_id != request.region_id
        or preview.analysis_id != request.analysis_id
        or preview.request.applied_request != request
        for preview in binding.buffer_previews
    ):
        raise ValueError("Workspace execution buffer escaped its request")
    if presentation.buffer_result_signatures != tuple(
        (value.group_id, value.result_signature_sha256)
        for value in binding.buffer_previews
    ):
        raise ValueError("Workspace execution presentation drifted from its buffers")

    area = binding.area_result
    if area is None:
        if binding.execution_input.area_execution is WorkspaceAreaExecution.EXECUTE:
            raise ValueError("An area-enabled workspace execution omitted its result")
        if (
            presentation.area_capability_id is not None
            or presentation.area_result_signature_sha256 is not None
        ):
            raise ValueError("Workspace execution omitted its presented area result")
        return
    if not isinstance(area, WorkspaceAreaExecutionResult):
        raise TypeError("Workspace execution area result has an invalid type")
    if binding.execution_input.area_execution is not WorkspaceAreaExecution.EXECUTE:
        raise ValueError("An area-disabled workspace execution produced a result")
    if (
        area.request != request
        or area.access_scope != request.access_scope
        or area.region_id != request.region_id
        or area.analysis_id != request.analysis_id
        or area.target_resolution != request.target_resolution
        or presentation.area_capability_id != area.capability_id
        or presentation.area_result_signature_sha256
        != area.result_signature_sha256
    ):
        raise ValueError("Workspace execution area result escaped its request")


def _validate_constructed_workspace_execution_bundle(
    bundle: WorkspaceExecutionBundle,
) -> None:
    """Validate a bundle assembled only from trusted, validated builders."""

    if not isinstance(bundle, WorkspaceExecutionBundle):
        raise TypeError("workspace execution bundle has an invalid type")
    if bundle.schema_version != WORKSPACE_EXECUTION_SCHEMA_VERSION:
        raise NotImplementedError("Unsupported workspace execution schema")
    access_scope = _exact_text(bundle.access_scope, "workspace execution access")
    region_id = _exact_text(bundle.region_id, "workspace execution region")
    if access_scope not in {f"product:{region_id}", f"review:{region_id}"}:
        raise ValueError("Workspace execution access is not bound to its region")
    if (
        isinstance(bundle.target_resolution, bool)
        or not isinstance(bundle.target_resolution, int)
        or bundle.target_resolution < 0
        or bundle.target_resolution > 15
    ):
        raise ValueError("Workspace execution target must be an H3 resolution")
    if not isinstance(bundle.bindings, tuple) or not bundle.bindings:
        raise ValueError("Workspace execution requires immutable analysis bindings")
    for binding in bundle.bindings:
        _validate_constructed_workspace_execution_binding(binding)
    if len(bundle.analysis_ids) != len(set(bundle.analysis_ids)):
        raise ValueError("Workspace execution analyses must be unique")
    if any(
        binding.request.access_scope != access_scope
        or binding.request.region_id != region_id
        or binding.request.target_resolution != bundle.target_resolution
        for binding in bundle.bindings
    ):
        raise ValueError("Workspace execution bindings escaped one access surface")

    adapter = bundle.app_adapter
    if not isinstance(adapter, WorkspaceAppAdapter):
        raise TypeError("Workspace execution app adapter has an invalid type")
    expected_presentations = tuple(
        (
            binding.presentation.analysis_id,
            binding.presentation.presentation_signature_sha256,
        )
        for binding in bundle.bindings
    )
    actual_presentations = tuple(
        (value.analysis_id, value.presentation_signature_sha256)
        for value in adapter.presentations
    )
    if (
        adapter.access_scope != access_scope
        or adapter.region_id != region_id
        or adapter.target_resolution != bundle.target_resolution
        or actual_presentations != expected_presentations
    ):
        raise ValueError("Workspace execution app adapter escaped its bindings")
    if not isinstance(bundle.execution_signature_sha256, str) or _SHA256.fullmatch(
        bundle.execution_signature_sha256
    ) is None:
        raise ValueError("Workspace execution signature must be a lowercase SHA-256")
    if bundle.execution_signature_sha256 != _canonical_sha256(
        _execution_signature_payload(bundle)
    ):
        raise ValueError("Workspace execution signature does not match")


def validate_workspace_execution_bundle(bundle: WorkspaceExecutionBundle) -> None:
    if not isinstance(bundle, WorkspaceExecutionBundle):
        raise TypeError("workspace execution bundle has an invalid type")
    if bundle.schema_version != WORKSPACE_EXECUTION_SCHEMA_VERSION:
        raise NotImplementedError("Unsupported workspace execution schema")
    access_scope = _exact_text(bundle.access_scope, "workspace execution access")
    region_id = _exact_text(bundle.region_id, "workspace execution region")
    if access_scope not in {f"product:{region_id}", f"review:{region_id}"}:
        raise ValueError("Workspace execution access is not bound to its region")
    if (
        isinstance(bundle.target_resolution, bool)
        or not isinstance(bundle.target_resolution, int)
        or bundle.target_resolution < 0
        or bundle.target_resolution > 15
    ):
        raise ValueError("Workspace execution target must be an H3 resolution")
    if not isinstance(bundle.bindings, tuple) or not bundle.bindings:
        raise ValueError("Workspace execution requires immutable analysis bindings")
    for binding in bundle.bindings:
        validate_workspace_execution_binding(binding)
    if len(bundle.analysis_ids) != len(set(bundle.analysis_ids)):
        raise ValueError("Workspace execution analyses must be unique")
    if any(
        binding.request.access_scope != access_scope
        or binding.request.region_id != region_id
        or binding.request.target_resolution != bundle.target_resolution
        for binding in bundle.bindings
    ):
        raise ValueError("Workspace execution bindings escaped one access surface")
    validate_workspace_app_adapter_from_presentations(
        bundle.app_adapter,
        tuple(binding.presentation for binding in bundle.bindings),
    )
    if (
        bundle.app_adapter.access_scope != access_scope
        or bundle.app_adapter.region_id != region_id
        or bundle.app_adapter.target_resolution != bundle.target_resolution
        or tuple(value.analysis_id for value in bundle.app_adapter.presentations)
        != bundle.analysis_ids
    ):
        raise ValueError("Workspace execution app adapter escaped its bindings")
    if not isinstance(bundle.execution_signature_sha256, str) or _SHA256.fullmatch(
        bundle.execution_signature_sha256
    ) is None:
        raise ValueError("Workspace execution signature must be a lowercase SHA-256")
    if bundle.execution_signature_sha256 != _canonical_sha256(
        _execution_signature_payload(bundle)
    ):
        raise ValueError("Workspace execution signature does not match")


def _validated_resolution_plan_inputs(
    execution_inputs: tuple[WorkspaceAnalysisExecutionInput, ...],
) -> tuple[str, str]:
    if not isinstance(execution_inputs, tuple):
        raise TypeError("Workspace resolution-plan inputs must be immutable")
    if not execution_inputs:
        raise ValueError("Workspace resolution plan requires at least one input")
    if any(
        not isinstance(value, WorkspaceAnalysisExecutionInput)
        for value in execution_inputs
    ):
        raise TypeError("Workspace resolution plan received an invalid input")
    parsed_inputs = tuple(
        parse_workspace_analysis_execution_input(value.as_dict())
        for value in execution_inputs
    )
    if parsed_inputs != execution_inputs:
        raise ValueError(
            "Workspace resolution-plan inputs are not strict-roundtrip safe"
        )
    if any(
        value.execution_state is not WorkspaceExecutionState.APPLIED
        for value in execution_inputs
    ):
        raise ValueError("Workspace resolution plan requires applied inputs")
    analysis_ids = tuple(
        value.request.analysis_id for value in execution_inputs
    )
    if len(analysis_ids) != len(set(analysis_ids)):
        raise ValueError("Workspace resolution-plan analyses must be unique")
    first = execution_inputs[0].request
    if any(
        value.request.access_scope != first.access_scope
        or value.request.region_id != first.region_id
        for value in execution_inputs
    ):
        raise ValueError("Workspace resolution-plan inputs have mixed scope")
    return first.access_scope, first.region_id


def _validated_h3_resolution(value: Any, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 15
    ):
        raise ValueError(f"{label} must be an H3 resolution")
    return value


def _retarget_resolution_plan_inputs(
    execution_inputs: tuple[WorkspaceAnalysisExecutionInput, ...],
    target_resolution: int,
) -> tuple[WorkspaceAnalysisExecutionInput, ...]:
    retargeted: list[WorkspaceAnalysisExecutionInput] = []
    for execution_input in execution_inputs:
        request = execution_input.request
        contract = load_analysis(request.region_id, request.analysis_id)
        target_request = retarget_workspace_analysis_request_from_contract(
            contract,
            request,
            target_resolution,
        )
        target_input = replace(execution_input, request=target_request)
        validate_workspace_analysis_execution_input(target_input)
        retargeted.append(target_input)
    return tuple(retargeted)


def validate_workspace_execution_resolution_plan(
    plan: WorkspaceExecutionResolutionPlan,
) -> None:
    if not isinstance(plan, WorkspaceExecutionResolutionPlan):
        raise TypeError("workspace execution resolution plan has an invalid type")
    if plan.schema_version != WORKSPACE_EXECUTION_RESOLUTION_PLAN_SCHEMA_VERSION:
        raise NotImplementedError("Unsupported workspace resolution-plan schema")
    access_scope = _exact_text(
        plan.access_scope,
        "workspace resolution-plan access",
    )
    region_id = _exact_text(plan.region_id, "workspace resolution-plan region")
    expected_access, expected_region = _validated_resolution_plan_inputs(
        plan.execution_inputs
    )
    if access_scope != expected_access or region_id != expected_region:
        raise ValueError("Workspace resolution plan escaped its input scope")
    display_resolution = _validated_h3_resolution(
        plan.display_resolution,
        "Workspace display resolution",
    )
    analysis_resolution = _validated_h3_resolution(
        plan.analysis_resolution,
        "Workspace analysis resolution",
    )

    expected_analysis_inputs = _retarget_resolution_plan_inputs(
        plan.execution_inputs,
        analysis_resolution,
    )
    expected_display_inputs = (
        expected_analysis_inputs
        if display_resolution == analysis_resolution
        else _retarget_resolution_plan_inputs(
            plan.execution_inputs,
            display_resolution,
        )
    )
    validate_workspace_execution_bundle(plan.analysis_bundle)
    if plan.display_bundle is not plan.analysis_bundle:
        validate_workspace_execution_bundle(plan.display_bundle)
    if (
        plan.analysis_bundle.access_scope != access_scope
        or plan.analysis_bundle.region_id != region_id
        or plan.analysis_bundle.target_resolution != analysis_resolution
        or plan.analysis_bundle.execution_inputs != expected_analysis_inputs
    ):
        raise ValueError("Workspace analysis bundle escaped its resolution plan")
    if (
        plan.display_bundle.access_scope != access_scope
        or plan.display_bundle.region_id != region_id
        or plan.display_bundle.target_resolution != display_resolution
        or plan.display_bundle.execution_inputs != expected_display_inputs
    ):
        raise ValueError("Workspace display bundle escaped its resolution plan")
    if display_resolution == analysis_resolution:
        if plan.display_bundle is not plan.analysis_bundle:
            raise ValueError(
                "Equal workspace resolutions must reuse one execution bundle"
            )
    elif plan.display_bundle is plan.analysis_bundle:
        raise ValueError(
            "Distinct workspace resolutions require distinct execution bundles"
        )
    if not isinstance(plan.plan_signature_sha256, str) or _SHA256.fullmatch(
        plan.plan_signature_sha256
    ) is None:
        raise ValueError("Workspace resolution-plan signature must be a SHA-256")
    if plan.plan_signature_sha256 != _canonical_sha256(
        _resolution_plan_signature_payload(plan)
    ):
        raise ValueError("Workspace resolution-plan signature does not match")


def _validate_constructed_workspace_execution_resolution_plan(
    plan: WorkspaceExecutionResolutionPlan,
    *,
    expected_analysis_inputs: tuple[WorkspaceAnalysisExecutionInput, ...],
    expected_display_inputs: tuple[WorkspaceAnalysisExecutionInput, ...],
) -> None:
    """Check one plan assembled from already validated execution bundles."""

    if not isinstance(plan, WorkspaceExecutionResolutionPlan):
        raise TypeError("workspace execution resolution plan has an invalid type")
    if plan.schema_version != WORKSPACE_EXECUTION_RESOLUTION_PLAN_SCHEMA_VERSION:
        raise NotImplementedError("Unsupported workspace resolution-plan schema")
    access_scope = _exact_text(
        plan.access_scope,
        "workspace resolution-plan access",
    )
    region_id = _exact_text(plan.region_id, "workspace resolution-plan region")
    if (
        not isinstance(plan.execution_inputs, tuple)
        or not plan.execution_inputs
        or any(
            not isinstance(value, WorkspaceAnalysisExecutionInput)
            for value in plan.execution_inputs
        )
    ):
        raise TypeError("Workspace resolution-plan inputs must be immutable")
    display_resolution = _validated_h3_resolution(
        plan.display_resolution,
        "Workspace display resolution",
    )
    analysis_resolution = _validated_h3_resolution(
        plan.analysis_resolution,
        "Workspace analysis resolution",
    )
    analysis_bundle = plan.analysis_bundle
    display_bundle = plan.display_bundle
    if (
        analysis_bundle.access_scope != access_scope
        or analysis_bundle.region_id != region_id
        or analysis_bundle.target_resolution != analysis_resolution
        or analysis_bundle.execution_inputs != expected_analysis_inputs
    ):
        raise ValueError("Workspace analysis bundle escaped its resolution plan")
    if (
        display_bundle.access_scope != access_scope
        or display_bundle.region_id != region_id
        or display_bundle.target_resolution != display_resolution
        or display_bundle.execution_inputs != expected_display_inputs
    ):
        raise ValueError("Workspace display bundle escaped its resolution plan")
    if display_resolution == analysis_resolution:
        if display_bundle is not analysis_bundle:
            raise ValueError(
                "Equal workspace resolutions must reuse one execution bundle"
            )
    elif display_bundle is analysis_bundle:
        raise ValueError(
            "Distinct workspace resolutions require distinct execution bundles"
        )
    if not isinstance(plan.plan_signature_sha256, str) or _SHA256.fullmatch(
        plan.plan_signature_sha256
    ) is None:
        raise ValueError("Workspace resolution-plan signature must be a SHA-256")
    if plan.plan_signature_sha256 != _canonical_sha256(
        _resolution_plan_signature_payload(plan)
    ):
        raise ValueError("Workspace resolution-plan signature does not match")


_BINDING_KEYS = {
    "execution_input",
    "buffer_previews",
    "area_result",
    "presentation",
}
_BUNDLE_KEYS = {
    "schema_version",
    "access_scope",
    "region_id",
    "target_resolution",
    "bindings",
    "app_adapter",
    "execution_signature_sha256",
}
_RESOLUTION_PLAN_KEYS = {
    "schema_version",
    "access_scope",
    "region_id",
    "display_resolution",
    "analysis_resolution",
    "execution_inputs",
    "analysis_bundle",
    "display_bundle",
    "plan_signature_sha256",
}


def _parse_binding(value: Any) -> WorkspaceExecutionBinding:
    raw = _mapping(value, "workspace execution binding")
    _exact_keys(raw, _BINDING_KEYS, "workspace execution binding")
    previews = raw["buffer_previews"]
    if not isinstance(previews, list):
        raise TypeError("Workspace execution buffer previews must be a list")
    area = raw["area_result"]
    binding = WorkspaceExecutionBinding(
        execution_input=parse_workspace_analysis_execution_input(
            raw["execution_input"]
        ),
        buffer_previews=tuple(
            parse_workspace_buffer_preview_result(item) for item in previews
        ),
        area_result=(
            None if area is None else parse_workspace_area_execution_result(area)
        ),
        presentation=parse_workspace_analysis_presentation(raw["presentation"]),
    )
    validate_workspace_execution_binding(binding)
    return binding


def parse_workspace_execution_bundle(value: Any) -> WorkspaceExecutionBundle:
    raw = _mapping(value, "workspace execution bundle")
    _exact_keys(raw, _BUNDLE_KEYS, "workspace execution bundle")
    bindings = raw["bindings"]
    if not isinstance(bindings, list):
        raise TypeError("Workspace execution bindings must be a list")
    bundle = WorkspaceExecutionBundle(
        schema_version=_exact_text(
            raw["schema_version"], "workspace execution schema"
        ),
        access_scope=_exact_text(raw["access_scope"], "workspace execution access"),
        region_id=_exact_text(raw["region_id"], "workspace execution region"),
        target_resolution=raw["target_resolution"],
        bindings=tuple(_parse_binding(item) for item in bindings),
        app_adapter=parse_workspace_app_adapter(raw["app_adapter"]),
        execution_signature_sha256=_exact_text(
            raw["execution_signature_sha256"], "workspace execution signature"
        ),
    )
    validate_workspace_execution_bundle(bundle)
    return bundle


def parse_workspace_execution_resolution_plan(
    value: Any,
) -> WorkspaceExecutionResolutionPlan:
    raw = _mapping(value, "workspace execution resolution plan")
    _exact_keys(
        raw,
        _RESOLUTION_PLAN_KEYS,
        "workspace execution resolution plan",
    )
    raw_inputs = raw["execution_inputs"]
    if not isinstance(raw_inputs, list):
        raise TypeError("Workspace resolution-plan inputs must be a list")
    analysis_bundle = parse_workspace_execution_bundle(raw["analysis_bundle"])
    parsed_display_bundle = parse_workspace_execution_bundle(
        raw["display_bundle"]
    )
    display_resolution = raw["display_resolution"]
    analysis_resolution = raw["analysis_resolution"]
    if display_resolution == analysis_resolution:
        if parsed_display_bundle != analysis_bundle:
            raise ValueError(
                "Equal workspace resolutions contain different bundles"
            )
        display_bundle = analysis_bundle
    else:
        display_bundle = parsed_display_bundle
    plan = WorkspaceExecutionResolutionPlan(
        schema_version=_exact_text(
            raw["schema_version"],
            "workspace resolution-plan schema",
        ),
        access_scope=_exact_text(
            raw["access_scope"],
            "workspace resolution-plan access",
        ),
        region_id=_exact_text(
            raw["region_id"],
            "workspace resolution-plan region",
        ),
        display_resolution=display_resolution,
        analysis_resolution=analysis_resolution,
        execution_inputs=tuple(
            parse_workspace_analysis_execution_input(item)
            for item in raw_inputs
        ),
        analysis_bundle=analysis_bundle,
        display_bundle=display_bundle,
        plan_signature_sha256=_exact_text(
            raw["plan_signature_sha256"],
            "workspace resolution-plan signature",
        ),
    )
    validate_workspace_execution_resolution_plan(plan)
    return plan


def run_catalog_workspace_execution(
    execution_inputs: tuple[WorkspaceAnalysisExecutionInput, ...],
) -> WorkspaceExecutionBundle:
    """Execute one explicit input/presentation/app-adapter chain.

    Area results are retained in the returned bundle so later consumers can use
    the same signed values as the map and result tables without re-execution.
    """

    if not isinstance(execution_inputs, tuple):
        raise TypeError("Workspace execution inputs must be an immutable tuple")
    if not execution_inputs:
        raise ValueError("Workspace execution requires at least one input")
    if any(
        not isinstance(value, WorkspaceAnalysisExecutionInput)
        for value in execution_inputs
    ):
        raise TypeError("Workspace execution received an invalid analysis input")
    parsed_inputs = tuple(
        parse_workspace_analysis_execution_input(value.as_dict())
        for value in execution_inputs
    )
    if parsed_inputs != execution_inputs:
        raise ValueError("Workspace execution inputs are not strict-roundtrip safe")
    first = execution_inputs[0].request
    if any(
        value.request.access_scope != first.access_scope
        or value.request.region_id != first.region_id
        or value.request.target_resolution != first.target_resolution
        for value in execution_inputs
    ):
        raise ValueError("Workspace execution inputs escaped one access surface")
    analysis_ids = tuple(
        value.request.analysis_id for value in execution_inputs
    )
    if len(analysis_ids) != len(set(analysis_ids)):
        raise ValueError("Workspace execution analyses must be unique")

    bindings = tuple(
        run_catalog_workspace_analysis_binding(execution_input)
        for execution_input in execution_inputs
    )
    return _build_workspace_execution_bundle_from_bindings(bindings)


def run_catalog_workspace_analysis_binding(
    execution_input: WorkspaceAnalysisExecutionInput,
    *,
    prepared_area_result: WorkspaceAreaExecutionResult | None = None,
    prepared_buffer_previews: tuple[WorkspacePreparedBufferPreview, ...] | None = None,
    runtime_snapshot_token: str | None = None,
) -> WorkspaceExecutionBinding:
    """Execute one strictly parsed input and retain its validated components."""

    validate_workspace_analysis_execution_input(execution_input)
    request = execution_input.request
    if prepared_area_result is not None:
        if (
            execution_input.area_execution is not WorkspaceAreaExecution.EXECUTE
            or prepared_area_result.request != request
        ):
            raise ValueError("Prepared area result escaped its execution input")
        authorize_catalog_workspace_analysis_request(
            request, required_capability_id=f"{request.analysis_id}.area",
        )
        validate_workspace_area_execution_result_from_contract(
            load_analysis(request.region_id, request.analysis_id), prepared_area_result,
        )
    if (
        execution_input.execution_state
        is WorkspaceExecutionState.APPLIED
    ):
        slice_view = build_catalog_workspace_slice_view(request)
    else:
        contract = load_analysis(request.region_id, request.analysis_id)
        validate_workspace_analysis_request_from_contract(contract, request)
        slice_view = build_workspace_slice_view_from_contract(contract, request)
    if prepared_buffer_previews is None:
        previews = tuple(
            run_catalog_workspace_buffer_preview_request(
                build_catalog_workspace_buffer_preview_request(request, group.group_id)
            )
            for group in request.groups
        )
    else:
        if (not isinstance(prepared_buffer_previews, tuple)
                or len(prepared_buffer_previews) != len(request.groups)):
            raise ValueError("Prepared buffers must match the complete ordered group inventory")
        previews = tuple(
            derive_catalog_workspace_buffer_preview(
                build_catalog_workspace_buffer_preview_request(request, group.group_id),
                prepared, runtime_snapshot_token,
            )
            for group, prepared in zip(request.groups, prepared_buffer_previews, strict=True)
        )
    area = prepared_area_result
    if area is None and execution_input.area_execution is WorkspaceAreaExecution.EXECUTE:
        area = run_catalog_workspace_area_request(request)
    presentation = build_workspace_analysis_presentation(
        slice_view,
        area,
        previews,
    )
    binding = WorkspaceExecutionBinding(
        execution_input=execution_input,
        buffer_previews=previews,
        area_result=area,
        presentation=presentation,
    )
    _validate_constructed_workspace_execution_binding(binding)
    return binding


def _build_workspace_execution_bundle_from_bindings(
    bindings: tuple[WorkspaceExecutionBinding, ...],
    *,
    map_layer_profile: str = "full",
) -> WorkspaceExecutionBundle:
    """Assemble components returned by the validated binding builder."""

    if type(map_layer_profile) is not str or map_layer_profile not in WORKSPACE_APP_MAP_LAYER_PROFILES:
        raise ValueError("Unsupported workspace app map-layer profile")
    if not isinstance(bindings, tuple) or not bindings:
        raise ValueError("Workspace execution requires immutable analysis bindings")
    for binding in bindings:
        _validate_constructed_workspace_execution_binding(binding)
    first = bindings[0].request
    if map_layer_profile == "full":
        adapter = build_workspace_app_adapter(
            tuple(binding.presentation for binding in bindings)
        )
    else:
        adapter = build_workspace_app_adapter(
            tuple(binding.presentation for binding in bindings),
            map_layer_profile=map_layer_profile,
        )
    bundle = WorkspaceExecutionBundle(
        schema_version=WORKSPACE_EXECUTION_SCHEMA_VERSION,
        access_scope=first.access_scope,
        region_id=first.region_id,
        target_resolution=first.target_resolution,
        bindings=tuple(bindings),
        app_adapter=adapter,
        execution_signature_sha256="0" * 64,
    )
    bundle = replace(
        bundle,
        execution_signature_sha256=_canonical_sha256(
            _execution_signature_payload(bundle)
        ),
    )
    _validate_constructed_workspace_execution_bundle(bundle)
    return bundle


def run_catalog_workspace_execution_resolution_plan(
    execution_inputs: tuple[WorkspaceAnalysisExecutionInput, ...],
    *,
    display_resolution: int,
    analysis_resolution: int,
) -> WorkspaceExecutionResolutionPlan:
    """Execute one signed display/analysis plan over applied inputs.

    Both target levels are resolved against every input's manifest before the
    first bundle runs. Equal target levels retain one shared bundle object;
    distinct levels execute exactly one analysis and one display bundle.
    """

    access_scope, region_id = _validated_resolution_plan_inputs(execution_inputs)
    normalized_display = _validated_h3_resolution(
        display_resolution,
        "Workspace display resolution",
    )
    normalized_analysis = _validated_h3_resolution(
        analysis_resolution,
        "Workspace analysis resolution",
    )
    analysis_inputs = _retarget_resolution_plan_inputs(
        execution_inputs,
        normalized_analysis,
    )
    display_inputs = (
        analysis_inputs
        if normalized_display == normalized_analysis
        else _retarget_resolution_plan_inputs(
            execution_inputs,
            normalized_display,
        )
    )

    analysis_bundle = run_catalog_workspace_execution(analysis_inputs)
    display_bundle = (
        analysis_bundle
        if normalized_display == normalized_analysis
        else run_catalog_workspace_execution(display_inputs)
    )
    return _build_workspace_execution_resolution_plan(
        execution_inputs,
        access_scope=access_scope,
        region_id=region_id,
        normalized_display=normalized_display,
        normalized_analysis=normalized_analysis,
        analysis_inputs=analysis_inputs,
        display_inputs=display_inputs,
        analysis_bundle=analysis_bundle,
        display_bundle=display_bundle,
    )


def _build_workspace_execution_resolution_plan(
    execution_inputs: tuple[WorkspaceAnalysisExecutionInput, ...],
    *,
    access_scope: str,
    region_id: str,
    normalized_display: int,
    normalized_analysis: int,
    analysis_inputs: tuple[WorkspaceAnalysisExecutionInput, ...],
    display_inputs: tuple[WorkspaceAnalysisExecutionInput, ...],
    analysis_bundle: WorkspaceExecutionBundle,
    display_bundle: WorkspaceExecutionBundle,
) -> WorkspaceExecutionResolutionPlan:
    """Keep the original plan constructor, signature, and link validation."""

    plan = WorkspaceExecutionResolutionPlan(
        schema_version=WORKSPACE_EXECUTION_RESOLUTION_PLAN_SCHEMA_VERSION,
        access_scope=access_scope,
        region_id=region_id,
        display_resolution=normalized_display,
        analysis_resolution=normalized_analysis,
        execution_inputs=execution_inputs,
        analysis_bundle=analysis_bundle,
        display_bundle=display_bundle,
        plan_signature_sha256="0" * 64,
    )
    plan = replace(
        plan,
        plan_signature_sha256=_canonical_sha256(
            _resolution_plan_signature_payload(plan)
        ),
    )
    _validate_constructed_workspace_execution_resolution_plan(
        plan,
        expected_analysis_inputs=analysis_inputs,
        expected_display_inputs=display_inputs,
    )
    return plan


def compose_catalog_workspace_execution_resolution_plan(
    execution_inputs: tuple[WorkspaceAnalysisExecutionInput, ...],
    *,
    display_resolution: int,
    analysis_resolution: int,
    analysis_bindings: tuple[WorkspaceExecutionBinding, ...],
    display_bindings: tuple[WorkspaceExecutionBinding, ...],
    map_layer_profile: str = "full",
) -> WorkspaceExecutionResolutionPlan:
    """Compose immutable bindings returned by the trusted execution builder.

    The current catalog still authorizes every original and retargeted request.
    No caller-provided JSON is trusted here: external graphs continue through
    the complete public parsers/validators. The app supplies frozen bindings
    from its cache keyed by the full request and current runtime snapshot.
    An explicit renderer profile changes only the materialized map roles;
    current request authorization and complete typed presentations remain.
    """

    if type(map_layer_profile) is not str or map_layer_profile not in WORKSPACE_APP_MAP_LAYER_PROFILES:
        raise ValueError("Unsupported workspace app map-layer profile")
    access_scope, region_id = _validated_resolution_plan_inputs(execution_inputs)
    normalized_display = _validated_h3_resolution(
        display_resolution, "Workspace display resolution"
    )
    normalized_analysis = _validated_h3_resolution(
        analysis_resolution, "Workspace analysis resolution"
    )
    analysis_inputs = _retarget_resolution_plan_inputs(
        execution_inputs, normalized_analysis
    )
    display_inputs = (
        analysis_inputs
        if normalized_display == normalized_analysis
        else _retarget_resolution_plan_inputs(execution_inputs, normalized_display)
    )
    for bindings, expected_inputs in (
        (analysis_bindings, analysis_inputs),
        (display_bindings, display_inputs),
    ):
        if not isinstance(bindings, tuple) or any(
            not isinstance(binding, WorkspaceExecutionBinding) for binding in bindings
        ):
            raise TypeError("Workspace prepared bindings must be immutable")
        if tuple(binding.execution_input for binding in bindings) != expected_inputs:
            raise ValueError("Workspace prepared bindings escaped their current inputs")
    if normalized_display == normalized_analysis and display_bindings != analysis_bindings:
        raise ValueError("Equal workspace resolutions require the same prepared bindings")
    analysis_bundle = _build_workspace_execution_bundle_from_bindings(
        analysis_bindings, map_layer_profile=map_layer_profile,
    )
    display_bundle = (
        analysis_bundle
        if normalized_display == normalized_analysis
        else _build_workspace_execution_bundle_from_bindings(
            display_bindings, map_layer_profile=map_layer_profile,
        )
    )
    return _build_workspace_execution_resolution_plan(
        execution_inputs,
        access_scope=access_scope,
        region_id=region_id,
        normalized_display=normalized_display,
        normalized_analysis=normalized_analysis,
        analysis_inputs=analysis_inputs,
        display_inputs=display_inputs,
        analysis_bundle=analysis_bundle,
        display_bundle=display_bundle,
    )


def retarget_catalog_workspace_execution_inputs(
    execution_inputs: tuple[WorkspaceAnalysisExecutionInput, ...],
    target_resolution: int,
) -> tuple[WorkspaceAnalysisExecutionInput, ...]:
    """Authorize all inputs at one target before any component acquisition."""

    _validated_resolution_plan_inputs(execution_inputs)
    target = _validated_h3_resolution(target_resolution, "Workspace target resolution")
    return _retarget_resolution_plan_inputs(execution_inputs, target)


__all__ = [
    "WORKSPACE_EXECUTION_SCHEMA_VERSION",
    "WORKSPACE_EXECUTION_RESOLUTION_PLAN_SCHEMA_VERSION",
    "WorkspaceAnalysisExecutionInput",
    "WorkspaceAreaExecution",
    "WorkspaceExecutionBinding",
    "WorkspaceExecutionBundle",
    "WorkspaceExecutionResolutionPlan",
    "WorkspaceExecutionState",
    "parse_workspace_analysis_execution_input",
    "parse_workspace_execution_bundle",
    "parse_workspace_execution_resolution_plan",
    "run_catalog_workspace_analysis_binding",
    "retarget_catalog_workspace_execution_inputs",
    "compose_catalog_workspace_execution_resolution_plan",
    "run_catalog_workspace_execution",
    "run_catalog_workspace_execution_resolution_plan",
    "validate_workspace_analysis_execution_input",
    "validate_workspace_execution_binding",
    "validate_workspace_execution_bundle",
    "validate_workspace_execution_resolution_plan",
]
