from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
import hashlib
import json
import math
import re
from typing import Any, Iterable, Mapping
from types import MappingProxyType

import h3

from .allocation import (
    known_sum,
    AllocationCandidate,
    AllocatedCell,
    TechnologyAllocationResult,
    TechnologyDemand,
    _allocate_ranked_technology_area,
)
from .combined_ranking import (
    TECHNICAL_RANKING_MODEL_ID,
    TechnicalRankingWeights,
    outside_ring_distances,
    technical_priority_score,
    wind_core_metrics,
    wind_potential_class_index,
)
from .rooftop import (
    ROOFTOP_RESULT_SCHEMA_VERSION,
    RooftopCapabilityResult,
    RooftopUnavailableResult,
    validate_unavailable_rooftop_result,
    parse_rooftop_request,
)
from .scenarios import ScenarioResult, parse_scenario_result
from .social_acceptance import (
    SocialAcceptanceResult,
    parse_social_acceptance_result,
    social_acceptance_calculation_result_signature,
)
from .technology_context import (
    TechnologyContextResult,
    parse_technology_context_result,
    validate_technology_context_result,
)
from .workspace_area import (
    WorkspaceAreaExecutionResult,
    validate_workspace_area_execution_result,
)


COMBINED_RESULT_SCHEMA_VERSION = "1.0"
COMBINED_RESULT_CAPABILITY_ID = "workspace.combined_result"
COMBINED_ALLOCATION_POLICY_SCHEMA_VERSION = "1.2"

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FLOAT_TOLERANCE = 1e-9

_BASE_SCORE_MODELS = {
    "declared_unit_interval_v1",
    "landscape_potential_core_v1",
}
_CO_USE_POLICIES = {
    "allow_with_reservation_tiebreak",
    "disallow_shared_cells",
}
_OUTSIDE_POTENTIAL_POLICIES = {
    "disabled",
    "allocate_declared_eligible_area",
}
_OUTSIDE_RING_MODELS = {
    "none",
    "declared_non_negative_integer",
    "selected_inside_h3_graph_distance_v1",
}
_ROLLUP_MODELS = {"sum_finalized_children_without_reranking"}
_ALLOCATION_PHASES = {"inside_potential", "outside_potential"}
_PRIORITY_VALUE_SOURCES = {
    "base_score",
    "outside_ring",
    "potential_fraction",
    "potential_area_km2",
    "reservation_state",
    "declared_value",
    "stable_cell_id",
    "wind_zone_size",
}
_PRIORITY_DIRECTIONS = {"ascending", "descending"}


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


def _id_digest(values: Iterable[str]) -> str:
    return hashlib.sha256(
        "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    ).hexdigest()


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a normalized identifier")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be an exact non-empty string")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _resolution(value: Any, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 15
    ):
        raise ValueError(f"{label} must be an H3 resolution from 0 to 15")
    return value


def _non_negative_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _positive_integer(value: Any, label: str) -> int:
    number = _non_negative_integer(value, label)
    if number == 0:
        raise ValueError(f"{label} must be a positive integer")
    return number


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _optional_boolean(value: Any, label: str) -> bool | None:
    return None if value is None else _boolean(value, label)


def _finite_non_negative(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite non-negative number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return number


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _unit_interval(value: Any, label: str) -> float:
    number = _finite_non_negative(value, label)
    if number > 1.0:
        raise ValueError(f"{label} must be between 0 and 1")
    return number


def _optional_finite_non_negative(value: Any, label: str) -> float | None:
    return None if value is None else _finite_non_negative(value, label)


def _optional_unit_interval(value: Any, label: str) -> float | None:
    return None if value is None else _unit_interval(value, label)


def _optional_positive_integer(value: Any, label: str) -> int | None:
    return None if value is None else _positive_integer(value, label)


def _close(left: float, right: float, *, tolerance: float = _FLOAT_TOLERANCE) -> bool:
    if left is None or right is None:
        return left is right
    return math.isclose(left, right, rel_tol=0.0, abs_tol=tolerance)


@dataclass(frozen=True)
class CombinedBaseScore:
    technology_id: str
    cell_id: str
    score: float
    outside_ring: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "technology_id": self.technology_id,
            "cell_id": self.cell_id,
            "score": self.score,
            "outside_ring": self.outside_ring,
        }


@dataclass(frozen=True)
class CombinedModelParameter:
    parameter_id: str
    value: float

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.parameter_id, "value": self.value}


@dataclass(frozen=True)
class CombinedPriorityComponent:
    component_id: str
    value_source: str
    direction: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "component_id": self.component_id,
            "value_source": self.value_source,
            "direction": self.direction,
        }


@dataclass(frozen=True)
class CombinedAllocationPhasePolicy:
    phase_id: str
    entry_residual_threshold_km2: float
    stop_tolerance_km2: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "entry_residual_threshold_km2": (
                self.entry_residual_threshold_km2
            ),
            "stop_tolerance_km2": self.stop_tolerance_km2,
        }


@dataclass(frozen=True)
class CombinedTechnologyPriority:
    technology_id: str
    phase_order: tuple[str, ...]
    phase_policies: tuple[CombinedAllocationPhasePolicy, ...]
    inside_components: tuple[CombinedPriorityComponent, ...]
    outside_components: tuple[CombinedPriorityComponent, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "technology_id": self.technology_id,
            "phase_order": list(self.phase_order),
            "phase_policies": [
                item.as_dict() for item in self.phase_policies
            ],
            "inside_components": [
                item.as_dict() for item in self.inside_components
            ],
            "outside_components": [
                item.as_dict() for item in self.outside_components
            ],
        }


@dataclass(frozen=True)
class CombinedPriorityValue:
    technology_id: str
    cell_id: str
    component_id: str
    value: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "technology_id": self.technology_id,
            "cell_id": self.cell_id,
            "component_id": self.component_id,
            "value": self.value,
        }


@dataclass(frozen=True)
class CombinedAllocationPolicy:
    """An explicit, signed policy boundary; this module defines no default."""

    schema_version: str
    policy_id: str
    finalization_resolution: int
    base_score_model: str
    base_score_input_id: str
    model_parameters: tuple[CombinedModelParameter, ...]
    base_scores: tuple[CombinedBaseScore, ...]
    technology_order: tuple[str, ...]
    technology_priorities: tuple[CombinedTechnologyPriority, ...]
    priority_values: tuple[CombinedPriorityValue, ...]
    co_use_policy: str
    outside_potential_policy: str
    outside_ring_model: str
    rollup_model: str
    rollup_resolutions: tuple[int, ...]
    base_score_input_signature_sha256: str
    policy_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "finalization_resolution": self.finalization_resolution,
            "base_score_model": self.base_score_model,
            "base_score_input_id": self.base_score_input_id,
            "model_parameters": [
                item.as_dict() for item in self.model_parameters
            ],
            "base_scores": [item.as_dict() for item in self.base_scores],
            "technology_order": list(self.technology_order),
            "technology_priorities": [
                item.as_dict() for item in self.technology_priorities
            ],
            "priority_values": [item.as_dict() for item in self.priority_values],
            "co_use_policy": self.co_use_policy,
            "outside_potential_policy": self.outside_potential_policy,
            "outside_ring_model": self.outside_ring_model,
            "rollup_model": self.rollup_model,
            "rollup_resolutions": list(self.rollup_resolutions),
            "base_score_input_signature_sha256": (
                self.base_score_input_signature_sha256
            ),
            "policy_signature_sha256": self.policy_signature_sha256,
        }


def _base_score_signature_payload(
    policy: CombinedAllocationPolicy,
) -> dict[str, Any]:
    return {
        "model": policy.base_score_model,
        "input_id": policy.base_score_input_id,
        "finalization_resolution": policy.finalization_resolution,
        "model_parameters": [
            item.as_dict() for item in policy.model_parameters
        ],
        "scores": [item.as_dict() for item in policy.base_scores],
    }


def _allocation_policy_signature_payload(
    policy: CombinedAllocationPolicy,
) -> dict[str, Any]:
    payload = policy.as_dict()
    payload.pop("policy_signature_sha256")
    return payload


def _validate_priority_components(
    components: tuple[CombinedPriorityComponent, ...],
    *,
    label: str,
    outside: bool,
    co_use_policy: str,
    outside_enabled: bool,
) -> tuple[str, ...]:
    if not isinstance(components, tuple) or not components:
        raise ValueError(f"{label} must declare an immutable priority order")
    component_ids: list[str] = []
    sources: list[str] = []
    for component in components:
        if not isinstance(component, CombinedPriorityComponent):
            raise TypeError(f"{label} contains an invalid priority component")
        component_ids.append(
            _identifier(component.component_id, f"{label} component id")
        )
        if component.value_source not in _PRIORITY_VALUE_SOURCES:
            raise NotImplementedError(
                f"Unsupported {label} value source: {component.value_source}"
            )
        if component.direction not in _PRIORITY_DIRECTIONS:
            raise NotImplementedError(
                f"Unsupported {label} direction: {component.direction}"
            )
        if (
            component.value_source == "stable_cell_id"
            and component.direction != "ascending"
        ):
            raise ValueError("Stable cell ids must be ordered ascending")
        if (
            component.value_source == "reservation_state"
            and component.direction != "ascending"
        ):
            raise ValueError("Reservation state must put unreserved cells first")
        if (
            component.value_source == "base_score"
            and component.direction != "descending"
        ):
            raise ValueError("Combined base scores must be ordered descending")
        if (
            component.value_source == "outside_ring"
            and component.direction != "ascending"
        ):
            raise ValueError("Outside rings must be ordered ascending")
        if component.value_source in {
            "potential_fraction",
            "potential_area_km2",
            "wind_zone_size",
        } and component.direction != "descending":
            raise ValueError(
                f"{component.value_source} must be ordered descending"
            )
        sources.append(component.value_source)
    if len(component_ids) != len(set(component_ids)):
        raise ValueError(f"{label} component ids must be unique")
    if sources.count("base_score") != 1:
        raise ValueError(f"{label} must use the declared base score exactly once")
    if sources.count("stable_cell_id") != 1 or sources[-1] != "stable_cell_id":
        raise ValueError(f"{label} must end with one stable-cell-id component")
    if outside:
        if not outside_enabled or sources.count("outside_ring") != 1:
            raise ValueError(
                f"{label} must use one declared outside ring when enabled"
            )
    elif "outside_ring" in sources:
        raise ValueError(f"{label} cannot use an outside ring")
    if co_use_policy == "allow_with_reservation_tiebreak" and not outside:
        if sources.count("reservation_state") != 1:
            raise ValueError(
                f"{label} must explicitly order inside reservation state"
            )
    elif co_use_policy == "disallow_shared_cells" and "reservation_state" in sources:
        raise ValueError(
            f"{label} cannot order reservations when shared cells are disallowed"
        )
    if sources.count("reservation_state") > 1:
        raise ValueError(f"{label} can order reservation state only once")
    return tuple(
        component.component_id
        for component in components
        if component.value_source == "declared_value"
    )


def validate_combined_allocation_policy(
    policy: CombinedAllocationPolicy,
) -> None:
    if not isinstance(policy, CombinedAllocationPolicy):
        raise TypeError("policy must be a CombinedAllocationPolicy")
    if policy.schema_version != COMBINED_ALLOCATION_POLICY_SCHEMA_VERSION:
        raise NotImplementedError(
            f"Unsupported combined-allocation policy schema: {policy.schema_version}"
        )
    _identifier(policy.policy_id, "combined allocation policy id")
    _resolution(policy.finalization_resolution, "policy finalization resolution")
    if policy.base_score_model not in _BASE_SCORE_MODELS:
        raise NotImplementedError(
            f"Unsupported combined base-score model: {policy.base_score_model}"
        )
    _identifier(policy.base_score_input_id, "combined base-score input id")
    if not isinstance(policy.model_parameters, tuple):
        raise TypeError("Combined model parameters must be immutable")
    parameter_ids: list[str] = []
    for item in policy.model_parameters:
        if not isinstance(item, CombinedModelParameter):
            raise TypeError("Combined model parameter has an invalid type")
        parameter_ids.append(
            _identifier(item.parameter_id, "combined model parameter id")
        )
        _finite_number(item.value, "combined model parameter value")
    if len(parameter_ids) != len(set(parameter_ids)):
        raise ValueError("Combined model parameter ids must be unique")
    if parameter_ids != sorted(parameter_ids):
        raise ValueError("Combined model parameters must use canonical id order")
    if policy.base_score_model == TECHNICAL_RANKING_MODEL_ID:
        expected_parameters = {
            "solar_core_weight",
            "solar_landscape_weight",
            "solar_potential_weight",
            "wind_core_weight",
            "wind_landscape_weight",
            "wind_potential_weight",
        }
        if set(parameter_ids) != expected_parameters:
            raise ValueError(
                "Dynamic technical ranking requires the exact signed "
                "wind/solar weight parameters"
            )
    if not isinstance(policy.technology_order, tuple) or not policy.technology_order:
        raise ValueError("Combined allocation technology order must not be empty")
    for technology_id in policy.technology_order:
        _identifier(technology_id, "combined allocation technology id")
    if len(set(policy.technology_order)) != len(policy.technology_order):
        raise ValueError("Combined allocation technology order must be unique")
    if (
        policy.base_score_model == TECHNICAL_RANKING_MODEL_ID
        and set(policy.technology_order) != {"solar", "wind"}
    ):
        raise ValueError(
            "Dynamic technical ranking requires exactly solar and wind"
        )
    if policy.co_use_policy not in _CO_USE_POLICIES:
        raise NotImplementedError(
            f"Unsupported combined co-use policy: {policy.co_use_policy}"
        )
    if policy.outside_potential_policy not in _OUTSIDE_POTENTIAL_POLICIES:
        raise NotImplementedError(
            "Unsupported combined outside-potential policy: "
            f"{policy.outside_potential_policy}"
        )
    if policy.outside_ring_model not in _OUTSIDE_RING_MODELS:
        raise NotImplementedError(
            f"Unsupported combined outside-ring model: {policy.outside_ring_model}"
        )
    if policy.rollup_model not in _ROLLUP_MODELS:
        raise NotImplementedError(
            f"Unsupported combined rollup model: {policy.rollup_model}"
        )
    if not isinstance(policy.rollup_resolutions, tuple):
        raise TypeError("Combined rollup resolutions must be an immutable tuple")
    for value in policy.rollup_resolutions:
        _resolution(value, "combined rollup resolution")
    if (
        len(set(policy.rollup_resolutions)) != len(policy.rollup_resolutions)
        or tuple(sorted(policy.rollup_resolutions, reverse=True))
        != policy.rollup_resolutions
        or any(
            value >= policy.finalization_resolution
            for value in policy.rollup_resolutions
        )
    ):
        raise ValueError(
            "Combined rollup resolutions must be unique, descending, and coarser"
        )
    if not isinstance(policy.base_scores, tuple) or not policy.base_scores:
        raise ValueError("Combined allocation needs explicit immutable base scores")
    technology_index = {
        technology_id: index
        for index, technology_id in enumerate(policy.technology_order)
    }
    identities: list[tuple[str, str]] = []
    for item in policy.base_scores:
        if not isinstance(item, CombinedBaseScore):
            raise TypeError("Combined base scores have an invalid type")
        technology_id = _identifier(item.technology_id, "base-score technology")
        if technology_id not in technology_index:
            raise ValueError("Base score refers to an undeclared technology")
        if (
            not isinstance(item.cell_id, str)
            or not h3.is_valid_cell(item.cell_id)
            or h3.get_resolution(item.cell_id) != policy.finalization_resolution
        ):
            raise ValueError("Base score refers to an invalid finalization cell")
        _unit_interval(item.score, "combined base score")
        if policy.outside_potential_policy == "disabled":
            if policy.outside_ring_model != "none" or item.outside_ring is not None:
                raise ValueError(
                    "Disabled outside allocation cannot declare a ring model or rings"
                )
        else:
            if policy.outside_ring_model == "declared_non_negative_integer":
                _non_negative_integer(item.outside_ring, "combined outside ring")
            elif policy.outside_ring_model == "selected_inside_h3_graph_distance_v1":
                if item.outside_ring is not None:
                    raise ValueError(
                        "Dynamic outside-ring policy cannot freeze per-cell rings"
                    )
            else:
                raise ValueError(
                    "Outside allocation requires a supported ring model"
                )
        identities.append((technology_id, item.cell_id))
    if len(identities) != len(set(identities)):
        raise ValueError("Combined base-score technology/cell pairs must be unique")
    expected_order = tuple(
        sorted(
            policy.base_scores,
            key=lambda item: (technology_index[item.technology_id], item.cell_id),
        )
    )
    if policy.base_scores != expected_order:
        raise ValueError("Combined base scores must use canonical policy/cell order")
    if (
        not isinstance(policy.technology_priorities, tuple)
        or len(policy.technology_priorities) != len(policy.technology_order)
    ):
        raise ValueError(
            "Combined technology priorities must match the technology order"
        )
    declared_value_components: dict[str, set[str]] = {}
    outside_enabled = policy.outside_potential_policy != "disabled"
    for expected_technology, priority in zip(
        policy.technology_order,
        policy.technology_priorities,
    ):
        if not isinstance(priority, CombinedTechnologyPriority):
            raise TypeError("Combined technology priority has an invalid type")
        if priority.technology_id != expected_technology:
            raise ValueError(
                "Combined technology priorities drifted from technology order"
            )
        expected_phases = (
            ("inside_potential", "outside_potential")
            if outside_enabled
            else ("inside_potential",)
        )
        if (
            not isinstance(priority.phase_order, tuple)
            or priority.phase_order != expected_phases
            or any(value not in _ALLOCATION_PHASES for value in priority.phase_order)
        ):
            raise ValueError(
                "Combined allocation phases must explicitly put inside before outside"
            )
        if (
            not isinstance(priority.phase_policies, tuple)
            or len(priority.phase_policies) != len(expected_phases)
        ):
            raise ValueError(
                "Combined allocation phases need one immutable execution policy each"
            )
        for expected_phase, phase_policy in zip(
            expected_phases,
            priority.phase_policies,
        ):
            if not isinstance(phase_policy, CombinedAllocationPhasePolicy):
                raise TypeError("Combined allocation phase policy has an invalid type")
            if phase_policy.phase_id != expected_phase:
                raise ValueError(
                    "Combined phase execution policies drifted from phase order"
                )
            _finite_non_negative(
                phase_policy.entry_residual_threshold_km2,
                f"{expected_technology} {expected_phase} entry threshold",
            )
            _finite_non_negative(
                phase_policy.stop_tolerance_km2,
                f"{expected_technology} {expected_phase} stop tolerance",
            )
        declared = set(
            _validate_priority_components(
                priority.inside_components,
                label=f"{expected_technology} inside priority",
                outside=False,
                co_use_policy=policy.co_use_policy,
                outside_enabled=outside_enabled,
            )
        )
        if outside_enabled:
            declared.update(
                _validate_priority_components(
                    priority.outside_components,
                    label=f"{expected_technology} outside priority",
                    outside=True,
                    co_use_policy=policy.co_use_policy,
                    outside_enabled=True,
                )
            )
        elif priority.outside_components:
            raise ValueError(
                "Disabled outside allocation cannot declare outside priority"
            )
        declared_value_components[expected_technology] = declared
    if not isinstance(policy.priority_values, tuple):
        raise TypeError("Combined declared priority values must be immutable")
    value_identities: list[tuple[str, str, str]] = []
    for item in policy.priority_values:
        if not isinstance(item, CombinedPriorityValue):
            raise TypeError("Combined declared priority value has an invalid type")
        technology_id = _identifier(
            item.technology_id,
            "combined priority-value technology",
        )
        if technology_id not in technology_index:
            raise ValueError("Priority value refers to an undeclared technology")
        if (
            not isinstance(item.cell_id, str)
            or not h3.is_valid_cell(item.cell_id)
            or h3.get_resolution(item.cell_id) != policy.finalization_resolution
        ):
            raise ValueError("Priority value refers to an invalid finalization cell")
        component_id = _identifier(
            item.component_id,
            "combined priority-value component",
        )
        if component_id not in declared_value_components[technology_id]:
            raise ValueError(
                "Priority value is not registered by its technology priority"
            )
        _finite_number(item.value, "combined declared priority value")
        value_identities.append((technology_id, item.cell_id, component_id))
    if len(value_identities) != len(set(value_identities)):
        raise ValueError("Combined declared priority values must be unique")
    expected_value_identities = {
        (technology_id, cell_id, component_id)
        for technology_id, cell_id in identities
        for component_id in declared_value_components[technology_id]
    }
    if set(value_identities) != expected_value_identities:
        raise ValueError(
            "Combined declared priority-value coverage is incomplete or excessive"
        )
    expected_value_order = tuple(
        sorted(
            policy.priority_values,
            key=lambda item: (
                technology_index[item.technology_id],
                item.cell_id,
                item.component_id,
            ),
        )
    )
    if policy.priority_values != expected_value_order:
        raise ValueError("Combined priority values must use canonical order")
    expected_input_signature = _canonical_sha256(
        _base_score_signature_payload(policy)
    )
    if policy.base_score_input_signature_sha256 != expected_input_signature:
        raise ValueError("Combined base-score input signature drifted")
    expected_policy_signature = _canonical_sha256(
        _allocation_policy_signature_payload(policy)
    )
    if policy.policy_signature_sha256 != expected_policy_signature:
        raise ValueError("Combined allocation policy signature drifted")


def build_combined_allocation_policy(
    *,
    policy_id: str,
    finalization_resolution: int,
    base_score_model: str,
    base_score_input_id: str,
    base_scores: Iterable[CombinedBaseScore],
    technology_order: Iterable[str],
    technology_priorities: Iterable[CombinedTechnologyPriority],
    priority_values: Iterable[CombinedPriorityValue],
    co_use_policy: str,
    outside_potential_policy: str,
    outside_ring_model: str,
    rollup_model: str,
    rollup_resolutions: Iterable[int],
    model_parameters: Iterable[CombinedModelParameter] = (),
) -> CombinedAllocationPolicy:
    ordered_technologies = tuple(technology_order)
    technology_index = {
        technology_id: index
        for index, technology_id in enumerate(ordered_technologies)
    }
    ordered_scores = tuple(
        sorted(
            (
                CombinedBaseScore(
                    technology_id=item.technology_id,
                    cell_id=item.cell_id,
                    score=float(item.score),
                    outside_ring=item.outside_ring,
                )
                for item in base_scores
            ),
            key=lambda item: (
                technology_index.get(item.technology_id, len(technology_index)),
                item.cell_id,
            ),
        )
    )
    source_priority_items = tuple(technology_priorities)
    if not all(
        isinstance(item, CombinedTechnologyPriority)
        for item in source_priority_items
    ):
        raise TypeError("Technology priorities have an invalid type")
    priority_items = tuple(
        CombinedTechnologyPriority(
            technology_id=item.technology_id,
            phase_order=tuple(item.phase_order),
            phase_policies=tuple(
                CombinedAllocationPhasePolicy(
                    phase_id=phase.phase_id,
                    entry_residual_threshold_km2=_finite_non_negative(
                        phase.entry_residual_threshold_km2,
                        f"{item.technology_id} {phase.phase_id} entry threshold",
                    ),
                    stop_tolerance_km2=_finite_non_negative(
                        phase.stop_tolerance_km2,
                        f"{item.technology_id} {phase.phase_id} stop tolerance",
                    ),
                )
                for phase in item.phase_policies
            ),
            inside_components=tuple(item.inside_components),
            outside_components=tuple(item.outside_components),
        )
        for item in source_priority_items
    )
    priority_ids = tuple(item.technology_id for item in priority_items)
    if len(priority_ids) != len(set(priority_ids)):
        raise ValueError("Technology priorities must have unique technology ids")
    if set(priority_ids) != set(ordered_technologies):
        raise ValueError(
            "Technology priorities must exactly cover the technology order"
        )
    priorities_by_technology = {
        item.technology_id: item for item in priority_items
    }
    ordered_priorities = tuple(
        priorities_by_technology.get(technology_id)
        for technology_id in ordered_technologies
    )
    if any(item is None for item in ordered_priorities):
        raise ValueError("Technology priority is missing for a declared technology")
    ordered_values = tuple(
        sorted(
            (
                CombinedPriorityValue(
                    technology_id=item.technology_id,
                    cell_id=item.cell_id,
                    component_id=item.component_id,
                    value=float(item.value),
                )
                for item in priority_values
            ),
            key=lambda item: (
                technology_index.get(item.technology_id, len(technology_index)),
                item.cell_id,
                item.component_id,
            ),
        )
    )
    ordered_model_parameters = tuple(
        sorted(
            (
                CombinedModelParameter(
                    parameter_id=item.parameter_id,
                    value=float(item.value),
                )
                for item in model_parameters
            ),
            key=lambda item: item.parameter_id,
        )
    )
    policy = CombinedAllocationPolicy(
        schema_version=COMBINED_ALLOCATION_POLICY_SCHEMA_VERSION,
        policy_id=policy_id,
        finalization_resolution=finalization_resolution,
        base_score_model=base_score_model,
        base_score_input_id=base_score_input_id,
        model_parameters=ordered_model_parameters,
        base_scores=ordered_scores,
        technology_order=ordered_technologies,
        technology_priorities=tuple(ordered_priorities),
        priority_values=ordered_values,
        co_use_policy=co_use_policy,
        outside_potential_policy=outside_potential_policy,
        outside_ring_model=outside_ring_model,
        rollup_model=rollup_model,
        rollup_resolutions=tuple(rollup_resolutions),
        base_score_input_signature_sha256="0" * 64,
        policy_signature_sha256="0" * 64,
    )
    policy = replace(
        policy,
        base_score_input_signature_sha256=_canonical_sha256(
            _base_score_signature_payload(policy)
        ),
    )
    policy = replace(
        policy,
        policy_signature_sha256=_canonical_sha256(
            _allocation_policy_signature_payload(policy)
        ),
    )
    validate_combined_allocation_policy(policy)
    return policy


_BASE_SCORE_KEYS = {"technology_id", "cell_id", "score", "outside_ring"}
_MODEL_PARAMETER_KEYS = {"id", "value"}
_PRIORITY_COMPONENT_KEYS = {"component_id", "value_source", "direction"}
_PHASE_POLICY_KEYS = {
    "phase_id",
    "entry_residual_threshold_km2",
    "stop_tolerance_km2",
}
_TECHNOLOGY_PRIORITY_KEYS = {
    "technology_id",
    "phase_order",
    "phase_policies",
    "inside_components",
    "outside_components",
}
_PRIORITY_VALUE_KEYS = {"technology_id", "cell_id", "component_id", "value"}
_POLICY_KEYS = {
    "schema_version",
    "policy_id",
    "finalization_resolution",
    "base_score_model",
    "base_score_input_id",
    "model_parameters",
    "base_scores",
    "technology_order",
    "technology_priorities",
    "priority_values",
    "co_use_policy",
    "outside_potential_policy",
    "outside_ring_model",
    "rollup_model",
    "rollup_resolutions",
    "base_score_input_signature_sha256",
    "policy_signature_sha256",
}


def _parse_priority_components(
    value: Any,
    label: str,
) -> tuple[CombinedPriorityComponent, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    components: list[CombinedPriorityComponent] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping) or set(raw) != _PRIORITY_COMPONENT_KEYS:
            raise ValueError(f"{label} component {index} fields are invalid")
        components.append(
            CombinedPriorityComponent(
                component_id=_identifier(
                    raw["component_id"],
                    f"{label} component {index} id",
                ),
                value_source=_identifier(
                    raw["value_source"],
                    f"{label} component {index} value source",
                ),
                direction=_identifier(
                    raw["direction"],
                    f"{label} component {index} direction",
                ),
            )
        )
    return tuple(components)


def _parse_phase_policies(
    value: Any,
    label: str,
) -> tuple[CombinedAllocationPhasePolicy, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    policies: list[CombinedAllocationPhasePolicy] = []
    for index, raw in enumerate(value):
        if not isinstance(raw, Mapping) or set(raw) != _PHASE_POLICY_KEYS:
            raise ValueError(f"{label} phase {index} fields are invalid")
        policies.append(
            CombinedAllocationPhasePolicy(
                phase_id=_identifier(
                    raw["phase_id"],
                    f"{label} phase {index} id",
                ),
                entry_residual_threshold_km2=_finite_non_negative(
                    raw["entry_residual_threshold_km2"],
                    f"{label} phase {index} entry threshold",
                ),
                stop_tolerance_km2=_finite_non_negative(
                    raw["stop_tolerance_km2"],
                    f"{label} phase {index} stop tolerance",
                ),
            )
        )
    return tuple(policies)


def parse_combined_allocation_policy(value: Any) -> CombinedAllocationPolicy:
    if not isinstance(value, Mapping) or set(value) != _POLICY_KEYS:
        raise ValueError(
            "Combined allocation policy fields do not match schema "
            f"{COMBINED_ALLOCATION_POLICY_SCHEMA_VERSION}"
        )
    schema_version = _text(value["schema_version"], "combined policy schema")
    if schema_version != COMBINED_ALLOCATION_POLICY_SCHEMA_VERSION:
        raise NotImplementedError(
            f"Unsupported combined-allocation policy schema: {schema_version}"
        )
    scores_raw = value["base_scores"]
    model_parameters_raw = value["model_parameters"]
    if not isinstance(scores_raw, list):
        raise TypeError("Combined base scores must be a list")
    if not isinstance(model_parameters_raw, list):
        raise TypeError("Combined model parameters must be a list")
    model_parameters: list[CombinedModelParameter] = []
    for index, raw in enumerate(model_parameters_raw):
        if not isinstance(raw, Mapping) or set(raw) != _MODEL_PARAMETER_KEYS:
            raise ValueError(f"Combined model parameter {index} fields are invalid")
        model_parameters.append(
            CombinedModelParameter(
                parameter_id=_identifier(
                    raw["id"],
                    f"combined model parameter {index} id",
                ),
                value=_finite_number(
                    raw["value"],
                    f"combined model parameter {index} value",
                ),
            )
        )
    scores: list[CombinedBaseScore] = []
    for index, raw in enumerate(scores_raw):
        if not isinstance(raw, Mapping) or set(raw) != _BASE_SCORE_KEYS:
            raise ValueError(f"Combined base score {index} fields are invalid")
        outside_ring = raw["outside_ring"]
        if outside_ring is not None:
            outside_ring = _non_negative_integer(
                outside_ring,
                f"combined base score {index} outside ring",
            )
        scores.append(
            CombinedBaseScore(
                technology_id=_identifier(
                    raw["technology_id"],
                    f"combined base score {index} technology",
                ),
                cell_id=_text(raw["cell_id"], f"combined base score {index} cell"),
                score=_unit_interval(
                    raw["score"],
                    f"combined base score {index} value",
                ),
                outside_ring=outside_ring,
            )
        )
    technology_order = value["technology_order"]
    technology_priorities_raw = value["technology_priorities"]
    priority_values_raw = value["priority_values"]
    rollup_resolutions = value["rollup_resolutions"]
    if not isinstance(technology_order, list) or not isinstance(
        rollup_resolutions,
        list,
    ):
        raise TypeError("Combined policy order and rollups must be lists")
    if not isinstance(technology_priorities_raw, list) or not isinstance(
        priority_values_raw,
        list,
    ):
        raise TypeError("Combined technology priorities and values must be lists")
    technology_priorities: list[CombinedTechnologyPriority] = []
    for index, raw in enumerate(technology_priorities_raw):
        if not isinstance(raw, Mapping) or set(raw) != _TECHNOLOGY_PRIORITY_KEYS:
            raise ValueError(
                f"Combined technology priority {index} fields are invalid"
            )
        phase_order = raw["phase_order"]
        if not isinstance(phase_order, list):
            raise TypeError(
                f"Combined technology priority {index} phases must be a list"
            )
        technology_priorities.append(
            CombinedTechnologyPriority(
                technology_id=_identifier(
                    raw["technology_id"],
                    f"combined technology priority {index} technology",
                ),
                phase_order=tuple(
                    _identifier(
                        item,
                        f"combined technology priority {index} phase",
                    )
                    for item in phase_order
                ),
                phase_policies=_parse_phase_policies(
                    raw["phase_policies"],
                    f"combined technology priority {index} execution",
                ),
                inside_components=_parse_priority_components(
                    raw["inside_components"],
                    f"combined technology priority {index} inside",
                ),
                outside_components=_parse_priority_components(
                    raw["outside_components"],
                    f"combined technology priority {index} outside",
                ),
            )
        )
    priority_values: list[CombinedPriorityValue] = []
    for index, raw in enumerate(priority_values_raw):
        if not isinstance(raw, Mapping) or set(raw) != _PRIORITY_VALUE_KEYS:
            raise ValueError(f"Combined priority value {index} fields are invalid")
        priority_values.append(
            CombinedPriorityValue(
                technology_id=_identifier(
                    raw["technology_id"],
                    f"combined priority value {index} technology",
                ),
                cell_id=_text(
                    raw["cell_id"],
                    f"combined priority value {index} cell",
                ),
                component_id=_identifier(
                    raw["component_id"],
                    f"combined priority value {index} component",
                ),
                value=_finite_number(
                    raw["value"],
                    f"combined priority value {index}",
                ),
            )
        )
    policy = CombinedAllocationPolicy(
        schema_version=schema_version,
        policy_id=_identifier(value["policy_id"], "combined policy id"),
        finalization_resolution=_resolution(
            value["finalization_resolution"],
            "combined policy finalization resolution",
        ),
        base_score_model=_identifier(
            value["base_score_model"],
            "combined policy base-score model",
        ),
        base_score_input_id=_identifier(
            value["base_score_input_id"],
            "combined policy base-score input id",
        ),
        model_parameters=tuple(model_parameters),
        base_scores=tuple(scores),
        technology_order=tuple(
            _identifier(item, "combined policy technology")
            for item in technology_order
        ),
        technology_priorities=tuple(technology_priorities),
        priority_values=tuple(priority_values),
        co_use_policy=_identifier(
            value["co_use_policy"],
            "combined policy co-use policy",
        ),
        outside_potential_policy=_identifier(
            value["outside_potential_policy"],
            "combined policy outside-potential policy",
        ),
        outside_ring_model=_identifier(
            value["outside_ring_model"],
            "combined policy outside-ring model",
        ),
        rollup_model=_identifier(
            value["rollup_model"],
            "combined policy rollup model",
        ),
        rollup_resolutions=tuple(
            _resolution(item, "combined policy rollup resolution")
            for item in rollup_resolutions
        ),
        base_score_input_signature_sha256=_digest(
            value["base_score_input_signature_sha256"],
            "combined policy base-score signature",
        ),
        policy_signature_sha256=_digest(
            value["policy_signature_sha256"],
            "combined policy signature",
        ),
    )
    validate_combined_allocation_policy(policy)
    return policy


@dataclass(frozen=True)
class CombinedAreaResultBinding:
    technology_id: str
    resolution: int
    result_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "technology_id": self.technology_id,
            "resolution": self.resolution,
            "result_signature_sha256": self.result_signature_sha256,
        }


@dataclass(frozen=True)
class CombinedResultRequest:
    schema_version: str
    capability_id: str
    access_scope: str
    region_id: str
    technology_ids: tuple[str, ...]
    finalization_resolution: int
    rollup_resolutions: tuple[int, ...]
    area_result_bindings: tuple[CombinedAreaResultBinding, ...]
    technology_context_result_signature_sha256: str
    scenario_result_signature_sha256: str
    rooftop_result_signature_sha256: str
    social_acceptance_result_signature_sha256: str
    allocation_policy_signature_sha256: str | None
    request_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capability_id": self.capability_id,
            "access_scope": self.access_scope,
            "region_id": self.region_id,
            "technology_ids": list(self.technology_ids),
            "finalization_resolution": self.finalization_resolution,
            "rollup_resolutions": list(self.rollup_resolutions),
            "area_result_bindings": [
                item.as_dict() for item in self.area_result_bindings
            ],
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
            "request_signature_sha256": self.request_signature_sha256,
        }


@dataclass(frozen=True)
class CombinedContextValueSummary:
    field_id: str
    value_kind: str
    value: bool | int | float | str
    observed_child_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "value_kind": self.value_kind,
            "value": self.value,
            "observed_child_count": self.observed_child_count,
        }


@dataclass(frozen=True)
class CombinedTechnologyCellResult:
    technology_id: str
    model_area_km2: float
    potential_area_km2: float
    potential_pct: float
    acceptance_adjusted_potential_area_km2: float
    base_score: float | None
    allocation_priority_score: float | None
    allocation_eligible: bool | None
    allocated_area_km2: float | None
    allocated_twh: float | None
    inside_potential_area_km2: float | None
    outside_potential_area_km2: float | None
    first_selected_rank: int | None
    reserved_by_other_technology: bool | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "technology_id": self.technology_id,
            "model_area_km2": self.model_area_km2,
            "potential_area_km2": self.potential_area_km2,
            "potential_pct": self.potential_pct,
            "acceptance_adjusted_potential_area_km2": (
                self.acceptance_adjusted_potential_area_km2
            ),
            "base_score": self.base_score,
            "allocation_priority_score": self.allocation_priority_score,
            "allocation_eligible": self.allocation_eligible,
            "allocated_area_km2": self.allocated_area_km2,
            "allocated_twh": self.allocated_twh,
            "inside_potential_area_km2": self.inside_potential_area_km2,
            "outside_potential_area_km2": self.outside_potential_area_km2,
            "first_selected_rank": self.first_selected_rank,
            "reserved_by_other_technology": (
                self.reserved_by_other_technology
            ),
        }


@dataclass(frozen=True)
class CombinedCellResult:
    cell_id: str
    resolution: int
    fine_child_count: int
    context_status: str
    context_values: tuple[CombinedContextValueSummary, ...]
    social_data_status: str
    social_acceptance_value: float | None
    social_potential_weight: float | None
    social_source_child_count: int
    available_technology_ids: tuple[str, ...]
    allocated_technology_ids: tuple[str, ...]
    technologies: tuple[CombinedTechnologyCellResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "resolution": self.resolution,
            "fine_child_count": self.fine_child_count,
            "context_status": self.context_status,
            "context_values": [item.as_dict() for item in self.context_values],
            "social_data_status": self.social_data_status,
            "social_acceptance_value": self.social_acceptance_value,
            "social_potential_weight": self.social_potential_weight,
            "social_source_child_count": self.social_source_child_count,
            "available_technology_ids": list(self.available_technology_ids),
            "allocated_technology_ids": list(self.allocated_technology_ids),
            "technologies": [item.as_dict() for item in self.technologies],
        }


@dataclass(frozen=True)
class CombinedResolutionResult:
    resolution: int
    cell_count: int
    cell_ids_sha256: str
    cells: tuple[CombinedCellResult, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "resolution": self.resolution,
            "cell_count": self.cell_count,
            "cell_ids_sha256": self.cell_ids_sha256,
            "cells": [item.as_dict() for item in self.cells],
        }


@dataclass(frozen=True)
class CombinedTechnologySummary:
    technology_id: str
    gross_energy_twh: float | None
    gross_area_need_km2: float
    rooftop_contribution_twh: float
    ground_energy_twh: float | None
    ground_area_need_km2: float
    potential_area_km2: float
    acceptance_adjusted_potential_area_km2: float
    selected_area_km2: float | None
    selected_twh: float | None
    inside_potential_area_km2: float | None
    outside_potential_area_km2: float | None
    unmet_area_km2: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "technology_id": self.technology_id,
            "gross_energy_twh": self.gross_energy_twh,
            "gross_area_need_km2": self.gross_area_need_km2,
            "rooftop_contribution_twh": self.rooftop_contribution_twh,
            "ground_energy_twh": self.ground_energy_twh,
            "ground_area_need_km2": self.ground_area_need_km2,
            "potential_area_km2": self.potential_area_km2,
            "acceptance_adjusted_potential_area_km2": (
                self.acceptance_adjusted_potential_area_km2
            ),
            "selected_area_km2": self.selected_area_km2,
            "selected_twh": self.selected_twh,
            "inside_potential_area_km2": self.inside_potential_area_km2,
            "outside_potential_area_km2": self.outside_potential_area_km2,
            "unmet_area_km2": self.unmet_area_km2,
        }


@dataclass(frozen=True)
class CombinedResult:
    schema_version: str
    capability_id: str
    request: CombinedResultRequest
    allocation_state: str
    allocation_detail: str
    technology_order: tuple[str, ...]
    technology_summaries: tuple[CombinedTechnologySummary, ...]
    resolutions: tuple[CombinedResolutionResult, ...]
    result_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capability_id": self.capability_id,
            "request": self.request.as_dict(),
            "allocation_state": self.allocation_state,
            "allocation_detail": self.allocation_detail,
            "technology_order": list(self.technology_order),
            "technology_summaries": [
                item.as_dict() for item in self.technology_summaries
            ],
            "resolutions": [item.as_dict() for item in self.resolutions],
            "result_signature_sha256": self.result_signature_sha256,
        }

    def resolution_result(self, resolution: int) -> CombinedResolutionResult:
        requested = _resolution(resolution, "combined result resolution")
        try:
            return next(item for item in self.resolutions if item.resolution == requested)
        except StopIteration as exc:
            raise KeyError(f"Combined result has no R{requested} view") from exc


def _request_signature_payload(request: CombinedResultRequest) -> dict[str, Any]:
    payload = request.as_dict()
    payload.pop("request_signature_sha256")
    return payload


def _result_signature_payload(result: CombinedResult) -> dict[str, Any]:
    payload = result.as_dict()
    payload.pop("result_signature_sha256")
    return payload


_AREA_RESULT_BINDING_KEYS = {
    "technology_id",
    "resolution",
    "result_signature_sha256",
}
_COMBINED_REQUEST_KEYS = {
    "schema_version",
    "capability_id",
    "access_scope",
    "region_id",
    "technology_ids",
    "finalization_resolution",
    "rollup_resolutions",
    "area_result_bindings",
    "technology_context_result_signature_sha256",
    "scenario_result_signature_sha256",
    "rooftop_result_signature_sha256",
    "social_acceptance_result_signature_sha256",
    "allocation_policy_signature_sha256",
    "request_signature_sha256",
}


def validate_combined_result_request(request: CombinedResultRequest) -> None:
    if not isinstance(request, CombinedResultRequest):
        raise TypeError("request must be a CombinedResultRequest")
    if (
        request.schema_version != COMBINED_RESULT_SCHEMA_VERSION
        or request.capability_id != COMBINED_RESULT_CAPABILITY_ID
    ):
        raise NotImplementedError("Unsupported combined-result request")
    _text(request.access_scope, "combined request access scope")
    _identifier(request.region_id, "combined request region")
    if not isinstance(request.technology_ids, tuple) or not request.technology_ids:
        raise ValueError("Combined request technologies must be immutable and non-empty")
    for technology_id in request.technology_ids:
        _identifier(technology_id, "combined request technology")
    if len(request.technology_ids) != len(set(request.technology_ids)):
        raise ValueError("Combined request technologies must be unique")
    _resolution(request.finalization_resolution, "combined finalization resolution")
    if not isinstance(request.rollup_resolutions, tuple):
        raise TypeError("Combined request rollups must be immutable")
    for resolution in request.rollup_resolutions:
        _resolution(resolution, "combined request rollup resolution")
    if (
        len(request.rollup_resolutions) != len(set(request.rollup_resolutions))
        or request.rollup_resolutions
        != tuple(sorted(request.rollup_resolutions, reverse=True))
        or any(
            resolution >= request.finalization_resolution
            for resolution in request.rollup_resolutions
        )
    ):
        raise ValueError(
            "Combined request rollups must be unique, descending, and coarser"
        )
    if not isinstance(request.area_result_bindings, tuple):
        raise TypeError("Combined area-result bindings must be immutable")
    expected_pairs = tuple(
        (technology_id, resolution)
        for technology_id in request.technology_ids
        for resolution in (
            request.finalization_resolution,
            *request.rollup_resolutions,
        )
    )
    actual_pairs: list[tuple[str, int]] = []
    for binding in request.area_result_bindings:
        if not isinstance(binding, CombinedAreaResultBinding):
            raise TypeError("Combined area-result binding has an invalid type")
        actual_pairs.append(
            (
                _identifier(
                    binding.technology_id,
                    "combined area-result technology",
                ),
                _resolution(
                    binding.resolution,
                    "combined area-result resolution",
                ),
            )
        )
        _digest(
            binding.result_signature_sha256,
            "combined area-result signature",
        )
    if tuple(actual_pairs) != expected_pairs:
        raise ValueError(
            "Combined area-result bindings must exactly follow technology/R order"
        )
    for value, label in (
        (
            request.technology_context_result_signature_sha256,
            "technology-context result signature",
        ),
        (request.scenario_result_signature_sha256, "scenario result signature"),
        (request.rooftop_result_signature_sha256, "rooftop result signature"),
        (
            request.social_acceptance_result_signature_sha256,
            "social-acceptance result signature",
        ),
    ):
        _digest(value, label)
    if request.allocation_policy_signature_sha256 is not None:
        _digest(
            request.allocation_policy_signature_sha256,
            "combined allocation-policy signature",
        )
    _digest(request.request_signature_sha256, "combined request signature")
    if request.request_signature_sha256 != _canonical_sha256(
        _request_signature_payload(request)
    ):
        raise ValueError("Combined request signature drifted")


def parse_combined_result_request(value: Any) -> CombinedResultRequest:
    if not isinstance(value, Mapping) or set(value) != _COMBINED_REQUEST_KEYS:
        raise ValueError("Combined result request fields do not match schema 1.0")
    technology_ids_raw = value["technology_ids"]
    rollups_raw = value["rollup_resolutions"]
    bindings_raw = value["area_result_bindings"]
    if not isinstance(technology_ids_raw, list):
        raise TypeError("Combined request technologies must be a list")
    if not isinstance(rollups_raw, list):
        raise TypeError("Combined request rollups must be a list")
    if not isinstance(bindings_raw, list):
        raise TypeError("Combined request area-result bindings must be a list")
    bindings: list[CombinedAreaResultBinding] = []
    for index, raw in enumerate(bindings_raw):
        if not isinstance(raw, Mapping) or set(raw) != _AREA_RESULT_BINDING_KEYS:
            raise ValueError(f"Combined area-result binding {index} is invalid")
        bindings.append(
            CombinedAreaResultBinding(
                technology_id=_identifier(
                    raw["technology_id"],
                    f"combined area-result binding {index} technology",
                ),
                resolution=_resolution(
                    raw["resolution"],
                    f"combined area-result binding {index} resolution",
                ),
                result_signature_sha256=_digest(
                    raw["result_signature_sha256"],
                    f"combined area-result binding {index} signature",
                ),
            )
        )
    policy_signature = value["allocation_policy_signature_sha256"]
    if policy_signature is not None:
        policy_signature = _digest(
            policy_signature,
            "combined request allocation-policy signature",
        )
    request = CombinedResultRequest(
        schema_version=_text(value["schema_version"], "combined request schema"),
        capability_id=_text(
            value["capability_id"],
            "combined request capability",
        ),
        access_scope=_text(
            value["access_scope"],
            "combined request access scope",
        ),
        region_id=_identifier(value["region_id"], "combined request region"),
        technology_ids=tuple(
            _identifier(item, "combined request technology")
            for item in technology_ids_raw
        ),
        finalization_resolution=_resolution(
            value["finalization_resolution"],
            "combined request finalization resolution",
        ),
        rollup_resolutions=tuple(
            _resolution(item, "combined request rollup resolution")
            for item in rollups_raw
        ),
        area_result_bindings=tuple(bindings),
        technology_context_result_signature_sha256=_digest(
            value["technology_context_result_signature_sha256"],
            "combined request technology-context signature",
        ),
        scenario_result_signature_sha256=_digest(
            value["scenario_result_signature_sha256"],
            "combined request scenario signature",
        ),
        rooftop_result_signature_sha256=_digest(
            value["rooftop_result_signature_sha256"],
            "combined request rooftop signature",
        ),
        social_acceptance_result_signature_sha256=_digest(
            value["social_acceptance_result_signature_sha256"],
            "combined request social-acceptance signature",
        ),
        allocation_policy_signature_sha256=policy_signature,
        request_signature_sha256=_digest(
            value["request_signature_sha256"],
            "combined request signature",
        ),
    )
    validate_combined_result_request(request)
    return request


def _strict_upstream_results(
    area_results: Iterable[WorkspaceAreaExecutionResult],
    technology_context_result: TechnologyContextResult,
    scenario_result: ScenarioResult,
    rooftop_result: RooftopCapabilityResult | RooftopUnavailableResult,
    social_acceptance_result: SocialAcceptanceResult,
) -> tuple[
    tuple[WorkspaceAreaExecutionResult, ...],
    TechnologyContextResult,
    ScenarioResult,
    RooftopCapabilityResult | RooftopUnavailableResult,
    SocialAcceptanceResult,
]:
    areas = tuple(area_results)
    if not areas:
        raise ValueError("Combined result needs workspace-area results")
    for result in areas:
        validate_workspace_area_execution_result(result)
    validate_technology_context_result(technology_context_result)
    if (
        parse_technology_context_result(technology_context_result.as_dict())
        != technology_context_result
    ):
        raise ValueError("Technology-context result is not canonical")
    scenario = parse_scenario_result(scenario_result.as_dict())
    if scenario != scenario_result:
        raise ValueError("Scenario result is not canonical")
    social = parse_social_acceptance_result(social_acceptance_result.as_dict())
    if social != social_acceptance_result:
        raise ValueError("Social-acceptance result is not canonical")
    if isinstance(rooftop_result, RooftopUnavailableResult):
        validate_unavailable_rooftop_result(rooftop_result)
    else:
        if not isinstance(rooftop_result, RooftopCapabilityResult):
            raise TypeError("rooftop_result must be an available or unavailable rooftop result")
        if rooftop_result.schema_version != ROOFTOP_RESULT_SCHEMA_VERSION:
            raise NotImplementedError(
                f"Unsupported rooftop result schema: {rooftop_result.schema_version}"
            )
        if parse_rooftop_request(rooftop_result.request.as_dict()) != rooftop_result.request:
            raise ValueError("Rooftop result request is not canonical")
    return areas, technology_context_result, scenario, rooftop_result, social


def _area_matrix(
    areas: tuple[WorkspaceAreaExecutionResult, ...],
) -> tuple[
    dict[tuple[str, int], WorkspaceAreaExecutionResult],
    tuple[str, ...],
    int,
    tuple[int, ...],
]:
    by_key: dict[tuple[str, int], WorkspaceAreaExecutionResult] = {}
    for result in areas:
        key = (result.technology, result.target_resolution)
        if key in by_key:
            raise ValueError("Combined area results contain a duplicate technology/R")
        by_key[key] = result
    technologies = tuple(sorted({item.technology for item in areas}))
    if len(technologies) < 2:
        raise ValueError("Combined result requires at least two technologies")
    levels_by_technology = {
        technology: tuple(
            sorted(
                (resolution for tech, resolution in by_key if tech == technology),
                reverse=True,
            )
        )
        for technology in technologies
    }
    level_sets = set(levels_by_technology.values())
    if len(level_sets) != 1:
        raise ValueError("Combined technologies must declare the same resolutions")
    levels = next(iter(level_sets))
    if not levels:
        raise ValueError("Combined area results have no resolutions")
    final_resolution = levels[0]
    rollups = levels[1:]
    if any(value >= final_resolution for value in rollups):
        raise ValueError("Combined area rollups must be coarser than finalization")
    for technology in technologies:
        final = by_key[(technology, final_resolution)]
        if final.request.source_resolution != final_resolution:
            raise ValueError("Combined area must finalize at its source resolution")
        for resolution in levels:
            item = by_key[(technology, resolution)]
            if (
                item.request.source_resolution != final_resolution
                or item.request.contract_signature_sha256
                != final.request.contract_signature_sha256
                or item.selected_layer_ids != final.selected_layer_ids
                or item.active_group_ids != final.active_group_ids
                or item.eligible_surface_id != final.eligible_surface_id
                or item.support_domain_id != final.support_domain_id
            ):
                raise ValueError("Combined area identity drifted across resolutions")
    for resolution in levels:
        reference = by_key[(technologies[0], resolution)]
        reference_cells = {item.cell_id: item for item in reference.cells}
        for technology in technologies[1:]:
            candidate = by_key[(technology, resolution)]
            candidate_cells = {item.cell_id: item for item in candidate.cells}
            if (
                candidate.access_scope != reference.access_scope
                or candidate.region_id != reference.region_id
                or candidate.eligible_surface_id != reference.eligible_surface_id
                or candidate.support_domain_id != reference.support_domain_id
                or candidate.cell_ids_sha256 != reference.cell_ids_sha256
                or set(candidate_cells) != set(reference_cells)
                or candidate.surface_artifact_provider
                != reference.surface_artifact_provider
                or candidate.surface_artifact_path
                != reference.surface_artifact_path
                or candidate.surface_artifact_sha256
                != reference.surface_artifact_sha256
                or candidate.surface_artifact_bytes
                != reference.surface_artifact_bytes
                or candidate.surface_id_field != reference.surface_id_field
                or candidate.surface_area_field != reference.surface_area_field
                or candidate.surface_area_unit != reference.surface_area_unit
                or candidate.surface_feature_collection_json
                != reference.surface_feature_collection_json
            ):
                raise ValueError(
                    "Combined technology domains or surface artifacts do not match"
                )
            for cell_id, cell in candidate_cells.items():
                if not _close(
                    cell.model_area_km2,
                    reference_cells[cell_id].model_area_km2,
                ):
                    raise ValueError("Combined technology model areas do not match")
    for technology in technologies:
        final_cells = by_key[(technology, final_resolution)].cells
        for resolution in rollups:
            grouped: dict[str, list[Any]] = {}
            for cell in final_cells:
                parent = str(h3.cell_to_parent(cell.cell_id, resolution))
                grouped.setdefault(parent, []).append(cell)
            declared = {
                cell.cell_id: cell
                for cell in by_key[(technology, resolution)].cells
            }
            if set(grouped) != set(declared):
                raise ValueError("Combined coarse area domain is not derived from final cells")
            for parent, children in grouped.items():
                model = math.fsum(item.model_area_km2 for item in children)
                remaining = math.fsum(item.remaining_area_km2 for item in children)
                row = declared[parent]
                if not _close(model, row.model_area_km2) or not _close(
                    remaining,
                    row.remaining_area_km2,
                ):
                    raise ValueError(
                        "Combined coarse area values are not exact final-cell sums"
                    )
    return by_key, technologies, final_resolution, rollups


def _validate_common_identity(
    matrix: Mapping[tuple[str, int], WorkspaceAreaExecutionResult],
    technologies: tuple[str, ...],
    final_resolution: int,
    context: TechnologyContextResult,
    scenario: ScenarioResult,
    rooftop: RooftopCapabilityResult | RooftopUnavailableResult,
    social: SocialAcceptanceResult,
) -> tuple[str, str, tuple[str, ...]]:
    reference = matrix[(technologies[0], final_resolution)]
    region_id = reference.region_id
    access_scope = reference.access_scope
    scenario_technologies = tuple(
        item.technology_id for item in scenario.technologies
    )
    if set(scenario_technologies) != set(technologies):
        raise ValueError("Scenario and area technology identities differ")
    identities = (
        (context.region_id, context.access_scope),
        (scenario.request.region_id, scenario.request.access_scope),
        (rooftop.request.region_id, rooftop.request.access_scope),
        (social.request.region_id, social.request.access_scope),
    )
    if any(value != (region_id, access_scope) for value in identities):
        raise ValueError("Combined upstream region/access identities differ")
    if (
        set(context.request.technologies) != set(technologies)
        or context.request.domain_resolution != final_resolution
        or context.request.eligible_surface_id != reference.eligible_surface_id
        or context.request.support_domain_id != reference.support_domain_id
        or context.target_domain_cell_count != reference.cell_count
        or context.target_domain_cell_ids_sha256 != reference.cell_ids_sha256
    ):
        raise ValueError("Technology context is not bound to the final area domain")
    if (
        social.request.target_resolution != final_resolution
        or social.coverage_target_support_hex_count != reference.cell_count
    ):
        raise ValueError("Social acceptance is not bound to the final area domain")
    if rooftop.request.domain_resolution != final_resolution:
        raise ValueError("Rooftop accounting must be executed at finalization R")
    if rooftop.request.analysis_id not in technologies:
        raise ValueError("Rooftop accounting targets an undeclared technology")
    final_cell_ids = {item.cell_id for item in reference.cells}
    if any(item.cell_id not in final_cell_ids for item in social.cells):
        raise ValueError("Social-acceptance cells fall outside the final area domain")
    if isinstance(rooftop, RooftopUnavailableResult):
        solar_area = matrix[(rooftop.request.analysis_id, final_resolution)]
        request = rooftop.request
        if (
            request.domain_id != solar_area.support_domain_id
            or request.domain_sha256
            != (solar_area.surface_upstream_sha256 or solar_area.surface_artifact_sha256)
            or request.eligible_surface_id != solar_area.eligible_surface_id
            or request.domain_cell_count != solar_area.cell_count
            or request.domain_cell_ids_sha256 != solar_area.cell_ids_sha256
            or request.contract_signature_sha256
            != solar_area.request.contract_signature_sha256
        ):
            raise ValueError("Unavailable rooftop is not bound to the current solar area contract/domain")
    elif any(
        item.cell_id not in final_cell_ids for item in rooftop.population_cells
    ):
        raise ValueError("Rooftop population cells fall outside the final area domain")
    return region_id, access_scope, scenario_technologies


def _validate_rooftop_accounting(
    rooftop: RooftopCapabilityResult | RooftopUnavailableResult,
    scenario: ScenarioResult,
) -> str:
    if isinstance(rooftop, RooftopUnavailableResult):
        validate_unavailable_rooftop_result(rooftop)
        scenario.technology_result(rooftop.request.analysis_id)
        return rooftop.request.analysis_id
    if rooftop.affects_geographic_potential or rooftop.adds_establishment_candidates:
        raise ValueError(
            "Rooftop accounting cannot alter geographic potential or candidates"
        )
    target = rooftop.request.analysis_id
    scenario_row = scenario.technology_result(target)
    request = rooftop.request
    accounting = rooftop.accounting
    if (
        not _close(request.gross_solar_target_twh, scenario_row.energy_twh)
        or not _close(request.ground_km2_per_twh, scenario_row.km2_per_twh)
        or not _close(accounting.gross_solar_target_twh, scenario_row.energy_twh)
        or not _close(accounting.ground_km2_per_twh, scenario_row.km2_per_twh)
        or not _close(
            accounting.gross_ground_area_need_km2,
            scenario_row.area_need_km2,
        )
        or not _close(
            accounting.rooftop_contribution_twh,
            scenario_row.energy_twh - accounting.ground_solar_twh,
        )
        or not _close(
            accounting.ground_solar_twh,
            max(
                0.0,
                accounting.gross_solar_target_twh
                - accounting.rooftop_contribution_twh,
            ),
        )
        or not _close(
            accounting.ground_area_need_km2,
            accounting.ground_solar_twh * accounting.ground_km2_per_twh,
        )
    ):
        raise ValueError("Rooftop accounting does not reconcile with scenario demand")
    cells = rooftop.population_cells
    cell_ids = tuple(item.cell_id for item in cells)
    if (
        len(cell_ids) != len(set(cell_ids))
        or rooftop.mapped_population_cell_count != len(cells)
        or rooftop.mapped_population_cell_ids_sha256 != _id_digest(cell_ids)
        or any(
            not h3.is_valid_cell(cell_id)
            or h3.get_resolution(cell_id) != request.domain_resolution
            for cell_id in cell_ids
        )
        or not _close(
            rooftop.mapped_population_total,
            math.fsum(item.population for item in cells),
        )
        or not _close(
            rooftop.mapped_technical_rooftop_twh,
            math.fsum(item.technical_rooftop_twh for item in cells),
        )
        or not _close(
            rooftop.population_source_total,
            accounting.population,
        )
        or rooftop.accounting_total_policy != "source_total_before_domain_clip"
        or rooftop.mapped_population_total > rooftop.population_source_total + 1e-9
        or rooftop.mapped_technical_rooftop_twh
        > accounting.technical_rooftop_twh + 1e-12
    ):
        raise ValueError("Rooftop result cells or totals do not reconcile")
    for cell in cells:
        values = (
            cell.population,
            cell.panel_area_m2,
            cell.technical_rooftop_twh,
        )
        if any(not math.isfinite(value) or value < 0.0 for value in values):
            raise ValueError("Rooftop result contains invalid population-cell values")
    return target


def _combined_request(
    *,
    matrix: Mapping[tuple[str, int], WorkspaceAreaExecutionResult],
    technology_order: tuple[str, ...],
    final_resolution: int,
    rollups: tuple[int, ...],
    context: TechnologyContextResult,
    scenario: ScenarioResult,
    rooftop: RooftopCapabilityResult | RooftopUnavailableResult,
    social: SocialAcceptanceResult,
    policy: CombinedAllocationPolicy | None,
) -> CombinedResultRequest:
    reference = matrix[(technology_order[0], final_resolution)]
    bindings = tuple(
        CombinedAreaResultBinding(
            technology_id=technology,
            resolution=resolution,
            result_signature_sha256=matrix[
                (technology, resolution)
            ].result_signature_sha256,
        )
        for technology in technology_order
        for resolution in (final_resolution, *rollups)
    )
    request = CombinedResultRequest(
        schema_version=COMBINED_RESULT_SCHEMA_VERSION,
        capability_id=COMBINED_RESULT_CAPABILITY_ID,
        access_scope=reference.access_scope,
        region_id=reference.region_id,
        technology_ids=technology_order,
        finalization_resolution=final_resolution,
        rollup_resolutions=rollups,
        area_result_bindings=bindings,
        technology_context_result_signature_sha256=(
            context.result_signature_sha256
        ),
        scenario_result_signature_sha256=_canonical_sha256(scenario.as_dict()),
        rooftop_result_signature_sha256=_canonical_sha256(rooftop.as_dict()),
        social_acceptance_result_signature_sha256=(
            social_acceptance_calculation_result_signature(social)
        ),
        allocation_policy_signature_sha256=(
            None if policy is None else policy.policy_signature_sha256
        ),
        request_signature_sha256="0" * 64,
    )
    return replace(
        request,
        request_signature_sha256=_canonical_sha256(
            _request_signature_payload(request)
        ),
    )


def _context_value_summaries(
    context_cells: Iterable[Any],
    field_order: tuple[str, ...],
) -> tuple[CombinedContextValueSummary, ...]:
    counts: dict[tuple[str, str, str], tuple[Any, int]] = {}
    for cell in context_cells:
        for value in cell.values:
            key = (value.field_id, value.value_kind, _canonical_json(value.value))
            source, count = counts.get(key, (value.value, 0))
            counts[key] = (source, count + 1)
    field_index = {field: index for index, field in enumerate(field_order)}
    return tuple(
        CombinedContextValueSummary(
            field_id=field_id,
            value_kind=value_kind,
            value=value,
            observed_child_count=count,
        )
        for (field_id, value_kind, encoded), (value, count) in sorted(
            counts.items(),
            key=lambda item: (
                field_index[item[0][0]],
                item[0][1],
                item[0][2],
            ),
        )
    )


def _context_status(context_cells: tuple[Any, ...]) -> str:
    statuses = tuple(item.status for item in context_cells)
    if statuses and all(value == "complete" for value in statuses):
        return "complete"
    if statuses and all(value == "not_assessed" for value in statuses):
        return "not_assessed"
    return "partial"


def _social_rollup(
    social_cells: tuple[Any | None, ...],
    social: SocialAcceptanceResult,
) -> tuple[str, float | None, float | None, int]:
    assessed = tuple(item for item in social_cells if item is not None)
    child_count = sum(item.source_child_count for item in assessed)
    if not assessed:
        weight = (
            0.0
            if social.request.impact_pct > 0.0
            and social.missing_context_policy == "exclude_when_applied"
            else 1.0
        )
        return "not_assessed", None, weight, 0
    acceptance = math.fsum(
        item.acceptance_value * item.source_child_count for item in assessed
    ) / child_count
    status = (
        social.value_data_status
        if len(assessed) == len(social_cells)
        else "partial"
    )
    weight = (
        (1.0 - social.request.impact_pct / 100.0)
        + social.request.impact_pct / 100.0 * acceptance
        if status != "partial"
        else None
    )
    return status, acceptance, weight, child_count


def _demand_by_technology(
    scenario: ScenarioResult,
    rooftop: RooftopCapabilityResult | RooftopUnavailableResult,
    rooftop_technology: str,
) -> dict[str, tuple[float, float, float, float, float, float]]:
    result: dict[str, tuple[float, float, float, float, float, float]] = {}
    for item in scenario.technologies:
        rooftop_contribution = 0.0
        ground_energy = item.energy_twh
        ground_area = item.area_need_km2
        if (
            item.technology_id == rooftop_technology
            and isinstance(rooftop, RooftopCapabilityResult)
        ):
            rooftop_contribution = max(
                0.0,
                item.energy_twh - rooftop.accounting.ground_solar_twh,
            )
            ground_energy = rooftop.accounting.ground_solar_twh
            ground_area = rooftop.accounting.ground_area_need_km2
        result[item.technology_id] = (
            item.energy_twh,
            item.area_need_km2,
            item.km2_per_twh,
            rooftop_contribution,
            ground_energy,
            ground_area,
        )
    return result


def _priority_order_key(
    components: tuple[CombinedPriorityComponent, ...],
    *,
    cell_id: str,
    base_score: CombinedBaseScore,
    allocation_priority_score: float,
    reserved_by_other_technology: bool,
    declared_values: Mapping[tuple[str, str, str], float],
    runtime_outside_ring: int | None = None,
    potential_fraction: float | None = None,
    potential_area_km2: float | None = None,
    wind_zone_size: int | None = None,
) -> tuple[float | str, ...]:
    """Materialize one fully declared order; no component is inferred."""

    values: list[float | str] = []
    for component in components:
        if component.value_source == "base_score":
            value: float | str = allocation_priority_score
        elif component.value_source == "outside_ring":
            ring = (
                runtime_outside_ring
                if runtime_outside_ring is not None
                else base_score.outside_ring
            )
            if ring is None:
                raise ValueError("Outside priority lacks a declared ring value")
            value = float(ring)
        elif component.value_source == "potential_fraction":
            if potential_fraction is None:
                raise ValueError("Priority lacks current potential fraction")
            value = potential_fraction
        elif component.value_source == "potential_area_km2":
            if potential_area_km2 is None:
                raise ValueError("Priority lacks current potential area")
            value = potential_area_km2
        elif component.value_source == "reservation_state":
            value = 1.0 if reserved_by_other_technology else 0.0
        elif component.value_source == "declared_value":
            key = (base_score.technology_id, cell_id, component.component_id)
            if key not in declared_values:
                raise ValueError("Combined priority lacks a declared component value")
            value = declared_values[key]
        elif component.value_source == "stable_cell_id":
            value = cell_id
        elif component.value_source == "wind_zone_size":
            if wind_zone_size is None:
                raise ValueError("Priority lacks current wind-zone size")
            value = float(wind_zone_size)
        else:
            raise NotImplementedError(
                f"Unsupported combined priority source: {component.value_source}"
            )
        if component.direction == "descending":
            if isinstance(value, str):
                raise ValueError("String priority components cannot be descending")
            value = -value
        values.append(value)
    return tuple(values)


def _technical_ranking_weights(
    policy: CombinedAllocationPolicy,
) -> Mapping[str, TechnicalRankingWeights]:
    parameters = {item.parameter_id: item.value for item in policy.model_parameters}
    return {
        technology_id: TechnicalRankingWeights(
            technology_id=technology_id,
            landscape=parameters[f"{technology_id}_landscape_weight"],
            potential=parameters[f"{technology_id}_potential_weight"],
            core=parameters[f"{technology_id}_core_weight"],
        )
        for technology_id in policy.technology_order
    }


@lru_cache(maxsize=3)
def _final_cell_neighbor_map(
    cell_ids: tuple[str, ...],
) -> Mapping[str, tuple[str, ...]]:
    domain = set(cell_ids)
    return MappingProxyType({
        cell_id: tuple(
            sorted(
                str(neighbor)
                for neighbor in h3.grid_disk(cell_id, 1)
                if str(neighbor) != cell_id and str(neighbor) in domain
            )
        )
        for cell_id in cell_ids
    })


def _execute_allocation(
    *,
    policy: CombinedAllocationPolicy,
    technology_order: tuple[str, ...],
    final_cells_by_technology: Mapping[str, Mapping[str, Any]],
    social_by_cell: Mapping[str, Any],
    social: SocialAcceptanceResult,
    demands: Mapping[str, tuple[float, float, float, float, float, float]],
) -> tuple[
    dict[str, TechnologyAllocationResult],
    dict[tuple[str, str], tuple[float, float | None, bool]],
]:
    validate_combined_allocation_policy(policy)
    cell_ids = tuple(sorted(next(iter(final_cells_by_technology.values()))))
    expected_pairs = {
        (technology, cell_id)
        for technology in technology_order
        for cell_id in cell_ids
    }
    score_by_key = {
        (item.technology_id, item.cell_id): item for item in policy.base_scores
    }
    priority_by_technology = {
        item.technology_id: item for item in policy.technology_priorities
    }
    declared_priority_values = {
        (item.technology_id, item.cell_id, item.component_id): item.value
        for item in policy.priority_values
    }
    if set(score_by_key) != expected_pairs:
        missing = sorted(expected_pairs.difference(score_by_key))
        extra = sorted(set(score_by_key).difference(expected_pairs))
        raise ValueError(
            "Combined allocation base-score coverage is incomplete: "
            f"missing={missing[:3]}, extra={extra[:3]}"
        )
    dynamic_model = policy.base_score_model == TECHNICAL_RANKING_MODEL_ID
    neighbor_map = _final_cell_neighbor_map(cell_ids) if dynamic_model else {}
    weights = _technical_ranking_weights(policy) if dynamic_model else {}
    wind_metrics = {}
    if dynamic_model and "wind" in technology_order:
        wind_metrics = {
            item.cell_id: item
            for item in wind_core_metrics(
                {
                    cell_id: wind_potential_class_index(
                        final_cells_by_technology["wind"][cell_id].potential_pct
                    )
                    for cell_id in cell_ids
                },
                neighbor_map,
            )
        }
    technical_score_by_key: dict[tuple[str, str], float] = {}
    potential_fraction_by_key: dict[tuple[str, str], float] = {}
    potential_area_by_key: dict[tuple[str, str], float] = {}
    wind_zone_size_by_cell = {
        cell_id: item.zone_size for cell_id, item in wind_metrics.items()
    }
    for key, item in score_by_key.items():
        technology, cell_id = key
        area_cell = final_cells_by_technology[technology][cell_id]
        potential_fraction = area_cell.remaining_area_km2 / area_cell.model_area_km2
        potential_fraction_by_key[key] = potential_fraction
        potential_area_by_key[key] = area_cell.remaining_area_km2
        technical_score_by_key[key] = (
            technical_priority_score(
                landscape_score=item.score,
                potential_fraction=potential_fraction,
                core_score=(
                    wind_metrics[cell_id].core_score
                    if technology == "wind"
                    else 0.0
                ),
                weights=weights[technology],
            )
            if dynamic_model
            else item.score
        )
    priority_fraction = social.request.allocation_priority_pct / 100.0
    priorities: dict[tuple[str, str], tuple[float, float | None, bool]] = {}
    for key, item in score_by_key.items():
        acceptance = social_by_cell.get(item.cell_id)
        eligible = not (
            priority_fraction > 0.0
            and acceptance is None
            and social.allocation_missing_context_policy
            == "exclude_when_prioritized"
        )
        if not eligible:
            score = None
        elif acceptance is None:
            score = technical_score_by_key[key]
        elif social.allocation_priority_model == "linear_acceptance_blend":
            score = (
                (1.0 - priority_fraction) * technical_score_by_key[key]
                + priority_fraction * acceptance.acceptance_value
            )
        else:
            raise NotImplementedError(
                "Unsupported social allocation-priority model: "
                f"{social.allocation_priority_model}"
            )
        priorities[key] = (technical_score_by_key[key], score, eligible)
    results: dict[str, TechnologyAllocationResult] = {}
    reserved: set[str] = set()
    for technology in policy.technology_order:
        _, _, factor, _, ground_energy, ground_area = demands[technology]
        demand = TechnologyDemand(
            technology=technology,
            twh=ground_energy,
            km2_per_twh=factor,
            area_need_km2=ground_area,
        )
        technology_priority = priority_by_technology[technology]
        phase_policy_by_id = {
            item.phase_id: item for item in technology_priority.phase_policies
        }
        candidate_rows: list[
            tuple[
                AllocationCandidate,
                CombinedBaseScore,
                float,
                tuple[CombinedPriorityComponent, ...],
            ]
        ] = []
        for cell_id in cell_ids:
            area_cell = final_cells_by_technology[technology][cell_id]
            score_item = score_by_key[(technology, cell_id)]
            _, priority, eligible = priorities[(technology, cell_id)]
            if not eligible or priority is None:
                continue
            is_reserved = cell_id in reserved
            if policy.co_use_policy == "disallow_shared_cells" and is_reserved:
                continue
            if area_cell.remaining_area_km2 > 0.0:
                candidate_rows.append(
                    (
                        AllocationCandidate(
                            cell_id=cell_id,
                            eligible_area_km2=area_cell.model_area_km2,
                            potential_area_km2=area_cell.remaining_area_km2,
                            outside_potential=False,
                            reserved_by_other_technology=is_reserved,
                        ),
                        score_item,
                        priority,
                        technology_priority.inside_components,
                    )
                )
            elif policy.outside_potential_policy == "allocate_declared_eligible_area":
                candidate_rows.append(
                    (
                        AllocationCandidate(
                            cell_id=cell_id,
                            eligible_area_km2=area_cell.model_area_km2,
                            potential_area_km2=0.0,
                            outside_potential=True,
                            reserved_by_other_technology=is_reserved,
                        ),
                        score_item,
                        priority,
                        technology_priority.outside_components,
                    )
                )
        phase_rows = {
            phase_id: [
                row
                for row in candidate_rows
                if (
                    "outside_potential"
                    if row[0].outside_potential
                    else "inside_potential"
                )
                == phase_id
            ]
            for phase_id in technology_priority.phase_order
        }
        available_potential_area_km2 = math.fsum(
            row[0].potential_area_km2
            for row in phase_rows["inside_potential"]
        )
        available_outside_area_km2 = math.fsum(
            row[0].eligible_area_km2
            for row in phase_rows.get("outside_potential", ())
        )
        selected_cells: list[AllocatedCell] = []
        remaining_area_km2 = demand.area_need_km2
        runtime_rings: Mapping[str, int] = {}
        for phase_id in technology_priority.phase_order:
            phase_policy = phase_policy_by_id[phase_id]
            if (
                remaining_area_km2
                <= phase_policy.entry_residual_threshold_km2
            ):
                continue
            current_phase_rows = phase_rows[phase_id]
            if (
                phase_id == "outside_potential"
                and policy.outside_ring_model
                == "selected_inside_h3_graph_distance_v1"
                and current_phase_rows
            ):
                anchors = tuple(
                    item.cell_id
                    for item in selected_cells
                    if not item.outside_potential
                )
                runtime_rings = outside_ring_distances(
                    eligible_cell_ids=cell_ids,
                    potential_cell_ids=anchors,
                    neighbor_map=neighbor_map,
                )
                current_phase_rows = [
                    row
                    for row in current_phase_rows
                    if row[0].cell_id in runtime_rings
                ]
                available_outside_area_km2 = math.fsum(
                    row[0].eligible_area_km2 for row in current_phase_rows
                )
            ordered_rows = sorted(
                current_phase_rows,
                key=lambda row: _priority_order_key(
                    row[3],
                    cell_id=row[0].cell_id,
                    base_score=row[1],
                    allocation_priority_score=row[2],
                    reserved_by_other_technology=(
                        row[0].reserved_by_other_technology
                    ),
                    declared_values=declared_priority_values,
                    runtime_outside_ring=runtime_rings.get(row[0].cell_id),
                    potential_fraction=potential_fraction_by_key[
                        (technology, row[0].cell_id)
                    ],
                    potential_area_km2=potential_area_by_key[
                        (technology, row[0].cell_id)
                    ],
                    wind_zone_size=(
                        wind_zone_size_by_cell.get(row[0].cell_id)
                        if technology == "wind"
                        else None
                    ),
                ),
            )
            # The phase's declared ranking already fixes every tie. Pass that
            # order directly rather than copying candidates into artificial
            # priorities and sorting them a second time.
            phase_allocation = _allocate_ranked_technology_area(
                TechnologyDemand(
                    technology=technology,
                    twh=None if factor is None else remaining_area_km2 / factor,
                    km2_per_twh=factor,
                    area_need_km2=remaining_area_km2,
                ),
                (row[0] for row in ordered_rows),
                stop_tolerance_km2=phase_policy.stop_tolerance_km2,
            )
            rank_offset = len(selected_cells)
            selected_cells.extend(
                replace(
                    cell,
                    selected_rank=rank_offset + cell.selected_rank,
                )
                for cell in phase_allocation.cells
            )
            remaining_area_km2 = phase_allocation.unmet_area_km2
        allocation = TechnologyAllocationResult(
            demand=demand,
            cells=tuple(selected_cells),
            selected_area_km2=math.fsum(
                cell.allocated_area_km2 for cell in selected_cells
            ),
            selected_twh=(None if ground_energy is None else math.fsum(
                cell.allocated_twh for cell in selected_cells
            )),
            unmet_area_km2=remaining_area_km2,
            available_potential_area_km2=available_potential_area_km2,
            available_outside_area_km2=available_outside_area_km2,
        )
        results[technology] = allocation
        reserved.update(item.cell_id for item in allocation.cells)
    return results, priorities


def _fine_cells(
    *,
    matrix: Mapping[tuple[str, int], WorkspaceAreaExecutionResult],
    final_resolution: int,
    technology_order: tuple[str, ...],
    context: TechnologyContextResult,
    social: SocialAcceptanceResult,
    allocations: Mapping[str, TechnologyAllocationResult] | None,
    priorities: Mapping[tuple[str, str], tuple[float, float | None, bool]] | None,
) -> tuple[CombinedCellResult, ...]:
    area_by_technology = {
        technology: {
            item.cell_id: item
            for item in matrix[(technology, final_resolution)].cells
        }
        for technology in technology_order
    }
    context_by_cell = {item.cell_id: item for item in context.cells}
    social_by_cell = {item.cell_id: item for item in social.cells}
    allocation_by_key = (
        {
            (technology, item.cell_id): item
            for technology, result in allocations.items()
            for item in result.cells
        }
        if allocations is not None
        else {}
    )
    cell_ids = tuple(sorted(next(iter(area_by_technology.values()))))
    result: list[CombinedCellResult] = []
    for cell_id in cell_ids:
        context_cell = context_by_cell[cell_id]
        social_cell = social_by_cell.get(cell_id)
        social_status, acceptance, weight, social_child_count = _social_rollup(
            (social_cell,),
            social,
        )
        technology_cells: list[CombinedTechnologyCellResult] = []
        for technology in technology_order:
            area = area_by_technology[technology][cell_id]
            allocated = allocation_by_key.get((technology, cell_id))
            if priorities is None:
                base_score = None
                priority_score = None
                allocation_eligible = None
                allocated_area = None
                allocated_twh = None
                inside_area = None
                outside_area = None
                rank = None
                reserved = None
            else:
                base_score, priority_score, allocation_eligible = priorities[
                    (technology, cell_id)
                ]
                allocated_area = 0.0 if allocated is None else allocated.allocated_area_km2
                allocated_twh = (None if allocations[technology].demand.twh is None
                                 else 0.0 if allocated is None else allocated.allocated_twh)
                inside_area = (
                    0.0
                    if allocated is None or allocated.outside_potential
                    else allocated.allocated_area_km2
                )
                outside_area = (
                    0.0
                    if allocated is None or not allocated.outside_potential
                    else allocated.allocated_area_km2
                )
                rank = None if allocated is None else allocated.selected_rank
                reserved = (
                    False
                    if allocated is None
                    else allocated.reserved_by_other_technology
                )
            technology_cells.append(
                CombinedTechnologyCellResult(
                    technology_id=technology,
                    model_area_km2=area.model_area_km2,
                    potential_area_km2=area.remaining_area_km2,
                    potential_pct=area.potential_pct,
                    acceptance_adjusted_potential_area_km2=(
                        area.remaining_area_km2 * (1.0 if weight is None else weight)
                    ),
                    base_score=base_score,
                    allocation_priority_score=priority_score,
                    allocation_eligible=allocation_eligible,
                    allocated_area_km2=allocated_area,
                    allocated_twh=allocated_twh,
                    inside_potential_area_km2=inside_area,
                    outside_potential_area_km2=outside_area,
                    first_selected_rank=rank,
                    reserved_by_other_technology=reserved,
                )
            )
        available = tuple(
            item.technology_id
            for item in technology_cells
            if item.potential_area_km2 > 0.0
        )
        allocated_ids = tuple(
            item.technology_id
            for item in technology_cells
            if item.allocated_area_km2 is not None
            and item.allocated_area_km2 > 0.0
        )
        result.append(
            CombinedCellResult(
                cell_id=cell_id,
                resolution=final_resolution,
                fine_child_count=1,
                context_status=context_cell.status,
                context_values=_context_value_summaries(
                    (context_cell,),
                    context.request.context_fields,
                ),
                social_data_status=social_status,
                social_acceptance_value=acceptance,
                social_potential_weight=weight,
                social_source_child_count=social_child_count,
                available_technology_ids=available,
                allocated_technology_ids=allocated_ids,
                technologies=tuple(technology_cells),
            )
        )
    return tuple(result)


def _rollup_cells(
    *,
    fine_cells: tuple[CombinedCellResult, ...],
    resolution: int,
    technology_order: tuple[str, ...],
    declared_area: Mapping[str, Mapping[str, Any]],
    context: TechnologyContextResult,
    social: SocialAcceptanceResult,
    context_by_fine_id: Mapping[str, Any],
    social_by_fine_id: Mapping[str, Any],
) -> tuple[CombinedCellResult, ...]:
    grouped: dict[str, list[CombinedCellResult]] = {}
    for cell in fine_cells:
        parent = str(h3.cell_to_parent(cell.cell_id, resolution))
        grouped.setdefault(parent, []).append(cell)
    output: list[CombinedCellResult] = []
    for parent, children in sorted(grouped.items()):
        fine_ids = tuple(child.cell_id for child in children)
        context_cells = tuple(context_by_fine_id[cell_id] for cell_id in fine_ids)
        social_cells = tuple(social_by_fine_id.get(cell_id) for cell_id in fine_ids)
        social_status, acceptance, weight, social_child_count = _social_rollup(
            social_cells,
            social,
        )
        technology_cells: list[CombinedTechnologyCellResult] = []
        for technology in technology_order:
            child_technology = tuple(
                next(
                    item
                    for item in child.technologies
                    if item.technology_id == technology
                )
                for child in children
            )
            declared = declared_area[technology][parent]
            model = math.fsum(item.model_area_km2 for item in child_technology)
            potential = math.fsum(
                item.potential_area_km2 for item in child_technology
            )
            if not _close(model, declared.model_area_km2) or not _close(
                potential,
                declared.remaining_area_km2,
            ):
                raise ValueError("Combined rollup drifted from exact area result")
            executed = child_technology[0].allocated_area_km2 is not None
            ranks = tuple(
                item.first_selected_rank
                for item in child_technology
                if item.first_selected_rank is not None
            )
            technology_cells.append(
                CombinedTechnologyCellResult(
                    technology_id=technology,
                    model_area_km2=model,
                    potential_area_km2=potential,
                    potential_pct=potential / model * 100.0,
                    acceptance_adjusted_potential_area_km2=math.fsum(
                        item.acceptance_adjusted_potential_area_km2
                        for item in child_technology
                    ),
                    base_score=None,
                    allocation_priority_score=None,
                    allocation_eligible=(
                        any(bool(item.allocation_eligible) for item in child_technology)
                        if executed
                        else None
                    ),
                    allocated_area_km2=(
                        math.fsum(
                            float(item.allocated_area_km2 or 0.0)
                            for item in child_technology
                        )
                        if executed
                        else None
                    ),
                    allocated_twh=(
                        known_sum(item.allocated_twh for item in child_technology)
                        if executed
                        else None
                    ),
                    inside_potential_area_km2=(
                        math.fsum(
                            float(item.inside_potential_area_km2 or 0.0)
                            for item in child_technology
                        )
                        if executed
                        else None
                    ),
                    outside_potential_area_km2=(
                        math.fsum(
                            float(item.outside_potential_area_km2 or 0.0)
                            for item in child_technology
                        )
                        if executed
                        else None
                    ),
                    first_selected_rank=min(ranks) if ranks else None,
                    reserved_by_other_technology=(
                        any(
                            bool(item.reserved_by_other_technology)
                            for item in child_technology
                        )
                        if executed
                        else None
                    ),
                )
            )
        available = tuple(
            item.technology_id
            for item in technology_cells
            if item.potential_area_km2 > 0.0
        )
        allocated = tuple(
            item.technology_id
            for item in technology_cells
            if item.allocated_area_km2 is not None
            and item.allocated_area_km2 > 0.0
        )
        output.append(
            CombinedCellResult(
                cell_id=parent,
                resolution=resolution,
                fine_child_count=len(children),
                context_status=_context_status(context_cells),
                context_values=_context_value_summaries(
                    context_cells,
                    context.request.context_fields,
                ),
                social_data_status=social_status,
                social_acceptance_value=acceptance,
                social_potential_weight=weight,
                social_source_child_count=social_child_count,
                available_technology_ids=available,
                allocated_technology_ids=allocated,
                technologies=tuple(technology_cells),
            )
        )
    return tuple(output)


def _resolution_result(
    resolution: int,
    cells: tuple[CombinedCellResult, ...],
) -> CombinedResolutionResult:
    cell_ids = tuple(item.cell_id for item in cells)
    if cell_ids != tuple(sorted(cell_ids)) or len(cell_ids) != len(set(cell_ids)):
        raise ValueError("Combined resolution cells must be sorted and unique")
    return CombinedResolutionResult(
        resolution=resolution,
        cell_count=len(cells),
        cell_ids_sha256=_id_digest(cell_ids),
        cells=cells,
    )


_CONTEXT_VALUE_SUMMARY_KEYS = {
    "field_id",
    "value_kind",
    "value",
    "observed_child_count",
}
_TECHNOLOGY_CELL_RESULT_KEYS = {
    "technology_id",
    "model_area_km2",
    "potential_area_km2",
    "potential_pct",
    "acceptance_adjusted_potential_area_km2",
    "base_score",
    "allocation_priority_score",
    "allocation_eligible",
    "allocated_area_km2",
    "allocated_twh",
    "inside_potential_area_km2",
    "outside_potential_area_km2",
    "first_selected_rank",
    "reserved_by_other_technology",
}
_COMBINED_CELL_RESULT_KEYS = {
    "cell_id",
    "resolution",
    "fine_child_count",
    "context_status",
    "context_values",
    "social_data_status",
    "social_acceptance_value",
    "social_potential_weight",
    "social_source_child_count",
    "available_technology_ids",
    "allocated_technology_ids",
    "technologies",
}
_COMBINED_RESOLUTION_RESULT_KEYS = {
    "resolution",
    "cell_count",
    "cell_ids_sha256",
    "cells",
}
_TECHNOLOGY_SUMMARY_KEYS = {
    "technology_id",
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
}
_COMBINED_RESULT_KEYS = {
    "schema_version",
    "capability_id",
    "request",
    "allocation_state",
    "allocation_detail",
    "technology_order",
    "technology_summaries",
    "resolutions",
    "result_signature_sha256",
}
_CONTEXT_STATUSES = {"complete", "partial", "not_assessed"}
_CONTEXT_VALUE_KINDS = {"boolean", "integer", "number", "string"}
_SOCIAL_DATA_STATUSES = {"observed", "synthetic", "partial", "not_assessed"}


def _parse_context_value_summary(
    value: Any,
    label: str,
) -> CombinedContextValueSummary:
    if not isinstance(value, Mapping) or set(value) != _CONTEXT_VALUE_SUMMARY_KEYS:
        raise ValueError(f"{label} fields are invalid")
    value_kind = _identifier(value["value_kind"], f"{label} kind")
    if value_kind not in _CONTEXT_VALUE_KINDS:
        raise ValueError(f"{label} kind is unsupported")
    raw_value = value["value"]
    if value_kind == "boolean":
        parsed_value: bool | int | float | str = _boolean(
            raw_value,
            f"{label} value",
        )
    elif value_kind == "integer":
        if isinstance(raw_value, bool) or not isinstance(raw_value, int):
            raise ValueError(f"{label} value must be an integer")
        parsed_value = raw_value
    elif value_kind == "number":
        parsed_value = _finite_number(raw_value, f"{label} value")
    else:
        parsed_value = _text(raw_value, f"{label} value")
    return CombinedContextValueSummary(
        field_id=_text(value["field_id"], f"{label} field id"),
        value_kind=value_kind,
        value=parsed_value,
        observed_child_count=_positive_integer(
            value["observed_child_count"],
            f"{label} observed child count",
        ),
    )


def _parse_technology_cell_result(
    value: Any,
    label: str,
) -> CombinedTechnologyCellResult:
    if not isinstance(value, Mapping) or set(value) != _TECHNOLOGY_CELL_RESULT_KEYS:
        raise ValueError(f"{label} fields are invalid")
    return CombinedTechnologyCellResult(
        technology_id=_identifier(
            value["technology_id"],
            f"{label} technology",
        ),
        model_area_km2=_finite_non_negative(
            value["model_area_km2"],
            f"{label} model area",
        ),
        potential_area_km2=_finite_non_negative(
            value["potential_area_km2"],
            f"{label} potential area",
        ),
        potential_pct=_finite_non_negative(
            value["potential_pct"],
            f"{label} potential percent",
        ),
        acceptance_adjusted_potential_area_km2=_finite_non_negative(
            value["acceptance_adjusted_potential_area_km2"],
            f"{label} acceptance-adjusted potential area",
        ),
        base_score=_optional_unit_interval(
            value["base_score"],
            f"{label} base score",
        ),
        allocation_priority_score=_optional_unit_interval(
            value["allocation_priority_score"],
            f"{label} allocation-priority score",
        ),
        allocation_eligible=_optional_boolean(
            value["allocation_eligible"],
            f"{label} allocation eligibility",
        ),
        allocated_area_km2=_optional_finite_non_negative(
            value["allocated_area_km2"],
            f"{label} allocated area",
        ),
        allocated_twh=_optional_finite_non_negative(
            value["allocated_twh"],
            f"{label} allocated energy",
        ),
        inside_potential_area_km2=_optional_finite_non_negative(
            value["inside_potential_area_km2"],
            f"{label} inside-potential area",
        ),
        outside_potential_area_km2=_optional_finite_non_negative(
            value["outside_potential_area_km2"],
            f"{label} outside-potential area",
        ),
        first_selected_rank=_optional_positive_integer(
            value["first_selected_rank"],
            f"{label} first selected rank",
        ),
        reserved_by_other_technology=_optional_boolean(
            value["reserved_by_other_technology"],
            f"{label} reservation",
        ),
    )


def _parse_combined_cell_result(value: Any, label: str) -> CombinedCellResult:
    if not isinstance(value, Mapping) or set(value) != _COMBINED_CELL_RESULT_KEYS:
        raise ValueError(f"{label} fields are invalid")
    context_values_raw = value["context_values"]
    available_raw = value["available_technology_ids"]
    allocated_raw = value["allocated_technology_ids"]
    technologies_raw = value["technologies"]
    if not isinstance(context_values_raw, list):
        raise TypeError(f"{label} context values must be a list")
    if not isinstance(available_raw, list) or not isinstance(allocated_raw, list):
        raise TypeError(f"{label} technology-id collections must be lists")
    if not isinstance(technologies_raw, list):
        raise TypeError(f"{label} technology results must be a list")
    context_status = _identifier(value["context_status"], f"{label} context status")
    if context_status not in _CONTEXT_STATUSES:
        raise ValueError(f"{label} context status is invalid")
    social_status = _identifier(
        value["social_data_status"],
        f"{label} social status",
    )
    if social_status not in _SOCIAL_DATA_STATUSES:
        raise ValueError(f"{label} social status is invalid")
    return CombinedCellResult(
        cell_id=_text(value["cell_id"], f"{label} cell id"),
        resolution=_resolution(value["resolution"], f"{label} resolution"),
        fine_child_count=_positive_integer(
            value["fine_child_count"],
            f"{label} fine child count",
        ),
        context_status=context_status,
        context_values=tuple(
            _parse_context_value_summary(item, f"{label} context value {index}")
            for index, item in enumerate(context_values_raw)
        ),
        social_data_status=social_status,
        social_acceptance_value=_optional_unit_interval(
            value["social_acceptance_value"],
            f"{label} social acceptance",
        ),
        social_potential_weight=_optional_unit_interval(
            value["social_potential_weight"],
            f"{label} social potential weight",
        ),
        social_source_child_count=_non_negative_integer(
            value["social_source_child_count"],
            f"{label} social source child count",
        ),
        available_technology_ids=tuple(
            _identifier(item, f"{label} available technology")
            for item in available_raw
        ),
        allocated_technology_ids=tuple(
            _identifier(item, f"{label} allocated technology")
            for item in allocated_raw
        ),
        technologies=tuple(
            _parse_technology_cell_result(
                item,
                f"{label} technology result {index}",
            )
            for index, item in enumerate(technologies_raw)
        ),
    )


def _parse_resolution_result(
    value: Any,
    label: str,
) -> CombinedResolutionResult:
    if not isinstance(value, Mapping) or set(value) != _COMBINED_RESOLUTION_RESULT_KEYS:
        raise ValueError(f"{label} fields are invalid")
    cells_raw = value["cells"]
    if not isinstance(cells_raw, list):
        raise TypeError(f"{label} cells must be a list")
    return CombinedResolutionResult(
        resolution=_resolution(value["resolution"], f"{label} resolution"),
        cell_count=_non_negative_integer(
            value["cell_count"],
            f"{label} cell count",
        ),
        cell_ids_sha256=_digest(
            value["cell_ids_sha256"],
            f"{label} cell-id signature",
        ),
        cells=tuple(
            _parse_combined_cell_result(item, f"{label} cell {index}")
            for index, item in enumerate(cells_raw)
        ),
    )


def _parse_technology_summary(
    value: Any,
    label: str,
) -> CombinedTechnologySummary:
    if not isinstance(value, Mapping) or set(value) != _TECHNOLOGY_SUMMARY_KEYS:
        raise ValueError(f"{label} fields are invalid")
    return CombinedTechnologySummary(
        technology_id=_identifier(
            value["technology_id"],
            f"{label} technology",
        ),
        gross_energy_twh=_optional_finite_non_negative(
            value["gross_energy_twh"],
            f"{label} gross energy",
        ),
        gross_area_need_km2=_finite_non_negative(
            value["gross_area_need_km2"],
            f"{label} gross area need",
        ),
        rooftop_contribution_twh=_finite_non_negative(
            value["rooftop_contribution_twh"],
            f"{label} rooftop contribution",
        ),
        ground_energy_twh=_optional_finite_non_negative(
            value["ground_energy_twh"],
            f"{label} ground energy",
        ),
        ground_area_need_km2=_finite_non_negative(
            value["ground_area_need_km2"],
            f"{label} ground area need",
        ),
        potential_area_km2=_finite_non_negative(
            value["potential_area_km2"],
            f"{label} potential area",
        ),
        acceptance_adjusted_potential_area_km2=_finite_non_negative(
            value["acceptance_adjusted_potential_area_km2"],
            f"{label} acceptance-adjusted potential area",
        ),
        selected_area_km2=_optional_finite_non_negative(
            value["selected_area_km2"],
            f"{label} selected area",
        ),
        selected_twh=_optional_finite_non_negative(
            value["selected_twh"],
            f"{label} selected energy",
        ),
        inside_potential_area_km2=_optional_finite_non_negative(
            value["inside_potential_area_km2"],
            f"{label} inside-potential area",
        ),
        outside_potential_area_km2=_optional_finite_non_negative(
            value["outside_potential_area_km2"],
            f"{label} outside-potential area",
        ),
        unmet_area_km2=_optional_finite_non_negative(
            value["unmet_area_km2"],
            f"{label} unmet area",
        ),
    )


def parse_combined_result(value: Any) -> CombinedResult:
    if not isinstance(value, Mapping) or set(value) != _COMBINED_RESULT_KEYS:
        raise ValueError("Combined result fields do not match schema 1.0")
    request_raw = value["request"]
    technology_order_raw = value["technology_order"]
    summaries_raw = value["technology_summaries"]
    resolutions_raw = value["resolutions"]
    if not isinstance(request_raw, Mapping):
        raise TypeError("Combined result request must be an object")
    if not isinstance(technology_order_raw, list):
        raise TypeError("Combined result technology order must be a list")
    if not isinstance(summaries_raw, list):
        raise TypeError("Combined result technology summaries must be a list")
    if not isinstance(resolutions_raw, list):
        raise TypeError("Combined result resolutions must be a list")
    result = CombinedResult(
        schema_version=_text(value["schema_version"], "combined result schema"),
        capability_id=_text(
            value["capability_id"],
            "combined result capability",
        ),
        request=parse_combined_result_request(request_raw),
        allocation_state=_identifier(
            value["allocation_state"],
            "combined result allocation state",
        ),
        allocation_detail=_text(
            value["allocation_detail"],
            "combined result allocation detail",
        ),
        technology_order=tuple(
            _identifier(item, "combined result technology")
            for item in technology_order_raw
        ),
        technology_summaries=tuple(
            _parse_technology_summary(
                item,
                f"combined technology summary {index}",
            )
            for index, item in enumerate(summaries_raw)
        ),
        resolutions=tuple(
            _parse_resolution_result(item, f"combined resolution {index}")
            for index, item in enumerate(resolutions_raw)
        ),
        result_signature_sha256=_digest(
            value["result_signature_sha256"],
            "combined result signature",
        ),
    )
    validate_combined_result(result)
    return result


def validate_combined_result(result: CombinedResult) -> None:
    if not isinstance(result, CombinedResult):
        raise TypeError("result must be a CombinedResult")
    if (
        result.schema_version != COMBINED_RESULT_SCHEMA_VERSION
        or result.capability_id != COMBINED_RESULT_CAPABILITY_ID
    ):
        raise NotImplementedError("Unsupported combined-result schema or capability")
    validate_combined_result_request(result.request)
    _text(result.allocation_detail, "combined allocation detail")
    if result.allocation_state not in {"blocked_missing_policy", "executed"}:
        raise ValueError("Combined allocation state is invalid")
    if (
        not isinstance(result.technology_order, tuple)
        or result.technology_order != result.request.technology_ids
    ):
        raise ValueError("Combined result technology order drifted from request")
    if (
        not isinstance(result.technology_summaries, tuple)
        or tuple(item.technology_id for item in result.technology_summaries)
        != result.technology_order
    ):
        raise ValueError("Combined technology summaries drifted from result order")
    expected_resolutions = (
        result.request.finalization_resolution,
        *result.request.rollup_resolutions,
    )
    if (
        not isinstance(result.resolutions, tuple)
        or tuple(item.resolution for item in result.resolutions)
        != expected_resolutions
    ):
        raise ValueError("Combined result resolution order drifted from request")
    if not result.resolutions:
        raise ValueError("Combined result has no resolution views")
    for resolution in result.resolutions:
        if not isinstance(resolution, CombinedResolutionResult) or not isinstance(
            resolution.cells,
            tuple,
        ):
            raise TypeError("Combined resolution result has an invalid type")
        cell_ids = tuple(item.cell_id for item in resolution.cells)
        if (
            resolution.cell_count != len(resolution.cells)
            or cell_ids != tuple(sorted(cell_ids))
            or len(cell_ids) != len(set(cell_ids))
            or resolution.cell_ids_sha256 != _id_digest(cell_ids)
        ):
            raise ValueError("Combined result resolution evidence drifted")
        for cell in resolution.cells:
            if (
                not isinstance(cell, CombinedCellResult)
                or cell.resolution != resolution.resolution
                or not h3.is_valid_cell(cell.cell_id)
                or h3.get_resolution(cell.cell_id) != resolution.resolution
                or cell.fine_child_count <= 0
            ):
                raise ValueError("Combined result contains an invalid H3 cell")
            if cell.context_status not in _CONTEXT_STATUSES:
                raise ValueError("Combined cell context status is invalid")
            if cell.social_data_status not in _SOCIAL_DATA_STATUSES:
                raise ValueError("Combined cell social status is invalid")
            if not isinstance(cell.context_values, tuple) or not isinstance(
                cell.technologies,
                tuple,
            ):
                raise TypeError("Combined cell nested results must be immutable")
            context_keys = tuple(
                (item.field_id, item.value_kind, _canonical_json(item.value))
                for item in cell.context_values
            )
            if len(context_keys) != len(set(context_keys)) or any(
                item.observed_child_count <= 0 for item in cell.context_values
            ):
                raise ValueError("Combined context summaries are invalid")
            if cell.social_data_status == "not_assessed":
                if (
                    cell.social_acceptance_value is not None
                    or cell.social_source_child_count != 0
                ):
                    raise ValueError("Unassessed social context contains observations")
            elif (
                cell.social_acceptance_value is None
                or cell.social_source_child_count <= 0
            ):
                raise ValueError("Assessed social context lacks observations")
            if cell.social_data_status == "partial":
                if cell.social_potential_weight is not None:
                    raise ValueError("Partial social context cannot expose one weight")
            elif cell.social_potential_weight is None:
                raise ValueError("Non-partial social context must expose a weight")
            technology_ids = tuple(item.technology_id for item in cell.technologies)
            if technology_ids != result.technology_order:
                raise ValueError("Combined cell technologies drifted from result order")
            if len({item.model_area_km2 for item in cell.technologies}) != 1:
                raise ValueError("Combined cell technology model areas differ")
            expected_available = tuple(
                item.technology_id
                for item in cell.technologies
                if item.potential_area_km2 > 0.0
            )
            expected_allocated = tuple(
                item.technology_id
                for item in cell.technologies
                if item.allocated_area_km2 is not None
                and item.allocated_area_km2 > 0.0
            )
            if (
                cell.available_technology_ids != expected_available
                or cell.allocated_technology_ids != expected_allocated
            ):
                raise ValueError("Combined cell technology classifications drifted")
            for item in cell.technologies:
                if (
                    item.model_area_km2 <= 0.0
                    or item.potential_area_km2
                    > item.model_area_km2 + _FLOAT_TOLERANCE
                    or item.acceptance_adjusted_potential_area_km2
                    > item.potential_area_km2 + _FLOAT_TOLERANCE
                    or not _close(
                        item.potential_pct,
                        item.potential_area_km2 / item.model_area_km2 * 100.0,
                        tolerance=1e-8,
                    )
                ):
                    raise ValueError("Combined technology-cell areas do not reconcile")
                energy_known = next(t for t in result.technology_summaries if t.technology_id == item.technology_id).gross_energy_twh is not None
                if result.allocation_state == "executed" and (item.allocated_twh is not None) != energy_known:
                    raise ValueError("Cell production availability differs from its scenario")
                allocation_values = (
                    item.allocated_area_km2,
                    item.allocated_twh,
                    item.inside_potential_area_km2,
                    item.outside_potential_area_km2,
                )
                if result.allocation_state == "blocked_missing_policy":
                    if any(
                        value is not None
                        for value in (
                            item.base_score,
                            item.allocation_priority_score,
                            item.allocation_eligible,
                            *allocation_values,
                            item.first_selected_rank,
                            item.reserved_by_other_technology,
                        )
                    ):
                        raise ValueError(
                            "Blocked combined cell fabricated allocation fields"
                        )
                elif resolution.resolution == result.request.finalization_resolution:
                    if (
                        item.base_score is None
                        or item.allocation_eligible is None
                        or any(value is None for index, value in enumerate(allocation_values) if index != 1 or energy_known)
                        or item.reserved_by_other_technology is None
                        or (
                            item.allocation_eligible
                            and item.allocation_priority_score is None
                        )
                        or (
                            not item.allocation_eligible
                            and item.allocation_priority_score is not None
                        )
                    ):
                        raise ValueError("Executed final cell lacks allocation evidence")
                else:
                    if (
                        item.base_score is not None
                        or item.allocation_priority_score is not None
                        or item.allocation_eligible is None
                        or any(value is None for index, value in enumerate(allocation_values) if index != 1 or energy_known)
                        or item.reserved_by_other_technology is None
                    ):
                        raise ValueError("Combined rollup contains reranked evidence")
                if allocation_values[0] is not None:
                    allocated_area = float(allocation_values[0])
                    if not _close(
                        allocated_area,
                        float(allocation_values[2]) + float(allocation_values[3]),
                    ):
                        raise ValueError("Combined allocated area phases do not reconcile")
                    if (allocated_area > 0.0) != (item.first_selected_rank is not None):
                        raise ValueError("Combined selected rank drifted from allocation")
    if result.allocation_state == "blocked_missing_policy":
        if result.request.allocation_policy_signature_sha256 is not None:
            raise ValueError("Blocked combined result cannot carry a policy signature")
        if any(
            any(
                value is not None
                for value in (
                    summary.selected_area_km2,
                    summary.selected_twh,
                    summary.inside_potential_area_km2,
                    summary.outside_potential_area_km2,
                    summary.unmet_area_km2,
                )
            )
            for summary in result.technology_summaries
        ):
            raise ValueError("Blocked combined result cannot fabricate allocation")
    elif result.request.allocation_policy_signature_sha256 is None:
        raise ValueError("Executed combined result requires a policy signature")
    final = result.resolutions[0]
    if any(item.fine_child_count != 1 for item in final.cells):
        raise ValueError("Combined finalization cells must represent one fine child")
    for summary in result.technology_summaries:
        if not isinstance(summary, CombinedTechnologySummary):
            raise TypeError("Combined technology summary has an invalid type")
        energy_known = summary.gross_energy_twh is not None
        if not energy_known:
            if summary.ground_energy_twh is not None or summary.selected_twh is not None or summary.rooftop_contribution_twh != 0 or not _close(summary.gross_area_need_km2, summary.ground_area_need_km2):
                raise ValueError("Area-only summary invented energy or rooftop credit")
        else:
            if not _close(
                summary.gross_energy_twh,
                summary.ground_energy_twh + summary.rooftop_contribution_twh,
            ):
                raise ValueError("Combined technology energy accounting does not reconcile")
            if summary.gross_energy_twh == 0.0:
                if (
                    summary.gross_area_need_km2 != 0.0
                    or summary.ground_energy_twh != 0.0
                    or summary.ground_area_need_km2 != 0.0
                ):
                    raise ValueError("Zero gross demand contains non-zero ground demand")
            else:
                gross_factor = (
                    summary.gross_area_need_km2 / summary.gross_energy_twh
                )
                if gross_factor <= 0.0 or not _close(
                    summary.ground_area_need_km2,
                    summary.ground_energy_twh * gross_factor,
                ):
                    raise ValueError("Ground demand drifted from the gross area factor")
        potential = math.fsum(
            next(
                item
                for item in cell.technologies
                if item.technology_id == summary.technology_id
            ).potential_area_km2
            for cell in final.cells
        )
        adjusted = math.fsum(
            next(
                item
                for item in cell.technologies
                if item.technology_id == summary.technology_id
            ).acceptance_adjusted_potential_area_km2
            for cell in final.cells
        )
        if not _close(summary.potential_area_km2, potential) or not _close(
            summary.acceptance_adjusted_potential_area_km2,
            adjusted,
        ):
            raise ValueError("Combined technology summary potential drifted")
        if result.allocation_state == "executed":
            selected_cells = tuple(
                next(
                    item
                    for item in cell.technologies
                    if item.technology_id == summary.technology_id
                )
                for cell in final.cells
            )
            selected_area = math.fsum(
                float(item.allocated_area_km2) for item in selected_cells
            )
            selected_twh = known_sum(item.allocated_twh for item in selected_cells)
            inside_area = math.fsum(
                float(item.inside_potential_area_km2) for item in selected_cells
            )
            outside_area = math.fsum(
                float(item.outside_potential_area_km2) for item in selected_cells
            )
            if any(
                value is None
                for value in (
                    summary.selected_area_km2,
                    *((summary.selected_twh,) if energy_known else ()),
                    summary.inside_potential_area_km2,
                    summary.outside_potential_area_km2,
                    summary.unmet_area_km2,
                )
            ):
                raise ValueError("Executed combined summary lacks allocation values")
            if (
                not _close(float(summary.selected_area_km2), selected_area)
                or not _close(summary.selected_twh, selected_twh)
                or not _close(
                    float(summary.inside_potential_area_km2),
                    inside_area,
                )
                or not _close(
                    float(summary.outside_potential_area_km2),
                    outside_area,
                )
                or not _close(selected_area, inside_area + outside_area)
                or not _close(
                    selected_area + float(summary.unmet_area_km2),
                    summary.ground_area_need_km2,
                )
            ):
                raise ValueError("Combined technology allocation summary drifted")
            if not energy_known:
                if selected_twh is not None:
                    raise ValueError("Area-only cells fabricated production")
            elif summary.ground_energy_twh == 0.0:
                if summary.ground_area_need_km2 != 0.0 or selected_twh != 0.0:
                    raise ValueError("Zero ground demand has non-zero area or energy")
            else:
                factor = summary.ground_area_need_km2 / summary.ground_energy_twh
                if factor <= 0.0 or not _close(selected_twh, selected_area / factor):
                    raise ValueError("Combined selected energy drifted from area factor")
    for resolution in result.resolutions[1:]:
        grouped: dict[str, list[CombinedCellResult]] = {}
        for child in final.cells:
            parent = str(h3.cell_to_parent(child.cell_id, resolution.resolution))
            grouped.setdefault(parent, []).append(child)
        if set(grouped) != {item.cell_id for item in resolution.cells}:
            raise ValueError("Combined rollup domain is not derived from final cells")
        for parent in resolution.cells:
            children = grouped[parent.cell_id]
            if parent.fine_child_count != len(children):
                raise ValueError("Combined rollup child count drifted")
            for technology_id in result.technology_order:
                parent_item = next(
                    item
                    for item in parent.technologies
                    if item.technology_id == technology_id
                )
                child_items = tuple(
                    next(
                        item
                        for item in child.technologies
                        if item.technology_id == technology_id
                    )
                    for child in children
                )
                for field_name in (
                    "model_area_km2",
                    "potential_area_km2",
                    "acceptance_adjusted_potential_area_km2",
                ):
                    if not _close(
                        float(getattr(parent_item, field_name)),
                        math.fsum(
                            float(getattr(item, field_name)) for item in child_items
                        ),
                    ):
                        raise ValueError("Combined rollup area is not a final-cell sum")
                if result.allocation_state == "executed":
                    for field_name in (
                        "allocated_area_km2",
                        "allocated_twh",
                        "inside_potential_area_km2",
                        "outside_potential_area_km2",
                    ):
                        if not _close(
                            getattr(parent_item, field_name),
                            known_sum(getattr(item, field_name) for item in child_items),
                        ):
                            raise ValueError(
                                "Combined rollup allocation is not a final-cell sum"
                            )
                    child_ranks = tuple(
                        item.first_selected_rank
                        for item in child_items
                        if item.first_selected_rank is not None
                    )
                    if parent_item.first_selected_rank != (
                        min(child_ranks) if child_ranks else None
                    ):
                        raise ValueError("Combined rollup rank was reranked")
    _digest(result.result_signature_sha256, "combined result signature")
    if result.result_signature_sha256 != _canonical_sha256(
        _result_signature_payload(result)
    ):
        raise ValueError("Combined result signature drifted")


def build_combined_result(
    *,
    area_results: Iterable[WorkspaceAreaExecutionResult],
    technology_context_result: TechnologyContextResult,
    scenario_result: ScenarioResult,
    rooftop_result: RooftopCapabilityResult | RooftopUnavailableResult,
    social_acceptance_result: SocialAcceptanceResult,
    allocation_policy: CombinedAllocationPolicy | None = None,
) -> CombinedResult:
    """Build one immutable map/hover/table/allocation result from exact inputs.

    The combined request is always derived from the supplied upstream results.
    It is not a separately persisted user selection. Without an explicit policy,
    potential, context, demand, rooftop accounting, and rollups are still exact,
    while allocation remains visibly and structurally blocked.
    """

    areas, context, scenario, rooftop, social = _strict_upstream_results(
        area_results,
        technology_context_result,
        scenario_result,
        rooftop_result,
        social_acceptance_result,
    )
    matrix, sorted_technologies, final_resolution, rollups = _area_matrix(areas)
    _, _, scenario_order = _validate_common_identity(
        matrix,
        sorted_technologies,
        final_resolution,
        context,
        scenario,
        rooftop,
        social,
    )
    rooftop_technology = _validate_rooftop_accounting(rooftop, scenario)
    technology_order = (
        scenario_order if allocation_policy is None else allocation_policy.technology_order
    )
    if allocation_policy is not None:
        validate_combined_allocation_policy(allocation_policy)
        if (
            allocation_policy.finalization_resolution != final_resolution
            or allocation_policy.rollup_resolutions != rollups
            or set(allocation_policy.technology_order) != set(sorted_technologies)
        ):
            raise ValueError("Combined allocation policy does not match upstream domain")
    request = _combined_request(
        matrix=matrix,
        technology_order=technology_order,
        final_resolution=final_resolution,
        rollups=rollups,
        context=context,
        scenario=scenario,
        rooftop=rooftop,
        social=social,
        policy=allocation_policy,
    )
    demands = _demand_by_technology(scenario, rooftop, rooftop_technology)
    final_cells_by_technology = {
        technology: {
            item.cell_id: item
            for item in matrix[(technology, final_resolution)].cells
        }
        for technology in technology_order
    }
    social_by_cell = {item.cell_id: item for item in social.cells}
    if allocation_policy is None:
        allocations = None
        priorities = None
        allocation_state = "blocked_missing_policy"
        allocation_detail = (
            "Allocation requires an explicit signed CombinedAllocationPolicy; "
            "no product or fallback policy is inferred."
        )
    else:
        allocations, priorities = _execute_allocation(
            policy=allocation_policy,
            technology_order=technology_order,
            final_cells_by_technology=final_cells_by_technology,
            social_by_cell=social_by_cell,
            social=social,
            demands=demands,
        )
        allocation_state = "executed"
        allocation_detail = (
            f"Allocation executed from explicit policy {allocation_policy.policy_id}."
        )
    fine_cells = _fine_cells(
        matrix=matrix,
        final_resolution=final_resolution,
        technology_order=technology_order,
        context=context,
        social=social,
        allocations=allocations,
        priorities=priorities,
    )
    resolution_results: list[CombinedResolutionResult] = [
        _resolution_result(final_resolution, fine_cells)
    ]
    context_by_fine_id = {item.cell_id: item for item in context.cells}
    social_by_fine_id = {item.cell_id: item for item in social.cells}
    for resolution in rollups:
        declared_area = {
            technology: {
                item.cell_id: item
                for item in matrix[(technology, resolution)].cells
            }
            for technology in technology_order
        }
        rolled = _rollup_cells(
            fine_cells=fine_cells,
            resolution=resolution,
            technology_order=technology_order,
            declared_area=declared_area,
            context=context,
            social=social,
            context_by_fine_id=context_by_fine_id,
            social_by_fine_id=social_by_fine_id,
        )
        resolution_results.append(_resolution_result(resolution, rolled))
    summaries: list[CombinedTechnologySummary] = []
    for technology in technology_order:
        (
            gross_energy,
            gross_area,
            _,
            rooftop_contribution,
            ground_energy,
            ground_area,
        ) = demands[technology]
        area_result = matrix[(technology, final_resolution)]
        accepted_area = math.fsum(
            next(
                item
                for item in cell.technologies
                if item.technology_id == technology
            ).acceptance_adjusted_potential_area_km2
            for cell in fine_cells
        )
        allocation = None if allocations is None else allocations[technology]
        summaries.append(
            CombinedTechnologySummary(
                technology_id=technology,
                gross_energy_twh=gross_energy,
                gross_area_need_km2=gross_area,
                rooftop_contribution_twh=rooftop_contribution,
                ground_energy_twh=ground_energy,
                ground_area_need_km2=ground_area,
                potential_area_km2=area_result.remaining_area_km2,
                acceptance_adjusted_potential_area_km2=accepted_area,
                selected_area_km2=(
                    None if allocation is None else allocation.selected_area_km2
                ),
                selected_twh=(
                    None if allocation is None else allocation.selected_twh
                ),
                inside_potential_area_km2=(
                    None
                    if allocation is None
                    else math.fsum(
                        item.allocated_area_km2
                        for item in allocation.cells
                        if not item.outside_potential
                    )
                ),
                outside_potential_area_km2=(
                    None
                    if allocation is None
                    else math.fsum(
                        item.allocated_area_km2
                        for item in allocation.cells
                        if item.outside_potential
                    )
                ),
                unmet_area_km2=(
                    None if allocation is None else allocation.unmet_area_km2
                ),
            )
        )
    result = CombinedResult(
        schema_version=COMBINED_RESULT_SCHEMA_VERSION,
        capability_id=COMBINED_RESULT_CAPABILITY_ID,
        request=request,
        allocation_state=allocation_state,
        allocation_detail=allocation_detail,
        technology_order=technology_order,
        technology_summaries=tuple(summaries),
        resolutions=tuple(resolution_results),
        result_signature_sha256="0" * 64,
    )
    result = replace(
        result,
        result_signature_sha256=_canonical_sha256(
            _result_signature_payload(result)
        ),
    )
    validate_combined_result(result)
    return result


__all__ = [
    "COMBINED_ALLOCATION_POLICY_SCHEMA_VERSION",
    "COMBINED_RESULT_CAPABILITY_ID",
    "COMBINED_RESULT_SCHEMA_VERSION",
    "CombinedAllocationPhasePolicy",
    "CombinedAllocationPolicy",
    "CombinedAreaResultBinding",
    "CombinedBaseScore",
    "CombinedModelParameter",
    "CombinedCellResult",
    "CombinedContextValueSummary",
    "CombinedPriorityComponent",
    "CombinedPriorityValue",
    "CombinedResolutionResult",
    "CombinedResult",
    "CombinedResultRequest",
    "CombinedTechnologyPriority",
    "CombinedTechnologyCellResult",
    "CombinedTechnologySummary",
    "build_combined_allocation_policy",
    "build_combined_result",
    "parse_combined_allocation_policy",
    "parse_combined_result",
    "parse_combined_result_request",
    "validate_combined_allocation_policy",
    "validate_combined_result",
    "validate_combined_result_request",
]
