from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Callable, Iterable, Mapping

import h3

from .combined_result import (
    COMBINED_RESULT_CAPABILITY_ID,
    CombinedAllocationPhasePolicy,
    CombinedAllocationPolicy,
    CombinedBaseScore,
    CombinedModelParameter,
    CombinedPriorityComponent,
    CombinedPriorityValue,
    CombinedTechnologyPriority,
    build_combined_allocation_policy,
    parse_combined_allocation_policy,
)
from .combined_ranking import TechnicalRankingWeights, landscape_group_score
from .catalogs import load_analysis
from .sources import resolve_support_observations


COMBINED_RESULT_POLICY_CONTRACT_SCHEMA_VERSION = "1.2"
COMBINED_RESULT_COMPILER_VERSION = "1.2"
COMBINED_RESULT_COMPILED_STATUS = "compiled_unvalidated"

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]*$")
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


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    label: str,
) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields do not match the current schema")


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a normalized identifier")
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


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a finite number")
    return number


def _finite_non_negative(value: Any, label: str) -> float:
    number = _finite_number(value, label)
    if number < 0.0:
        raise ValueError(f"{label} must be non-negative")
    return number


@dataclass(frozen=True)
class CombinedScoreInputParameter:
    parameter_id: str
    value: float

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.parameter_id, "value": self.value}


@dataclass(frozen=True)
class CombinedScoreLayerSelection:
    technology_id: str
    analysis_id: str
    group_id: str
    layer_ids: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "technology_id": self.technology_id,
            "analysis_id": self.analysis_id,
            "group_id": self.group_id,
            "layer_ids": list(self.layer_ids),
        }


@dataclass(frozen=True)
class CombinedScoreInputContract:
    input_id: str
    base_score_model: str
    executor_id: str
    numeric_parameters: tuple[CombinedScoreInputParameter, ...]
    layer_selections: tuple[CombinedScoreLayerSelection, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_id": self.input_id,
            "base_score_model": self.base_score_model,
            "executor_id": self.executor_id,
            "numeric_parameters": [
                item.as_dict() for item in self.numeric_parameters
            ],
            "layer_selections": [
                item.as_dict() for item in self.layer_selections
            ],
        }


@dataclass(frozen=True)
class CombinedResultPolicyContract:
    schema_version: str
    capability_id: str
    policy_id: str
    technology_order: tuple[str, ...]
    finalization_resolution: int
    rollup_resolutions: tuple[int, ...]
    co_use_policy: str
    outside_potential_policy: str
    outside_ring_model: str
    rollup_model: str
    score_input: CombinedScoreInputContract
    technology_priorities: tuple[CombinedTechnologyPriority, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capability_id": self.capability_id,
            "policy_id": self.policy_id,
            "technology_order": list(self.technology_order),
            "finalization_resolution": self.finalization_resolution,
            "rollup_resolutions": list(self.rollup_resolutions),
            "co_use_policy": self.co_use_policy,
            "outside_potential_policy": self.outside_potential_policy,
            "outside_ring_model": self.outside_ring_model,
            "rollup_model": self.rollup_model,
            "score_input": self.score_input.as_dict(),
            "technology_priorities": [
                item.as_dict() for item in self.technology_priorities
            ],
        }


@dataclass(frozen=True)
class ResolvedCombinedScoreSurface:
    technology_id: str
    provider: str
    provider_path: str
    path: Path
    sha256: str
    id_field: str
    resolution: int


@dataclass(frozen=True)
class CombinedResultCompilation:
    manifest: Mapping[str, Any]
    evidence: Mapping[str, Any]
    generated_paths: tuple[str, ...]
    readiness_state: str
    readiness_detail: str


_CONTRACT_KEYS = {
    "schema_version",
    "capability_id",
    "policy_id",
    "technology_order",
    "finalization_resolution",
    "rollup_resolutions",
    "co_use_policy",
    "outside_potential_policy",
    "outside_ring_model",
    "rollup_model",
    "score_input",
    "technology_priorities",
}
_SCORE_INPUT_KEYS = {
    "input_id",
    "base_score_model",
    "executor_id",
    "numeric_parameters",
    "layer_selections",
}
_NUMERIC_PARAMETER_KEYS = {"id", "value"}
_LAYER_SELECTION_KEYS = {
    "technology_id",
    "analysis_id",
    "group_id",
    "layer_ids",
}
_TECHNOLOGY_PRIORITY_KEYS = {
    "technology_id",
    "phase_order",
    "phase_policies",
    "inside_components",
    "outside_components",
}
_PRIORITY_COMPONENT_KEYS = {"component_id", "value_source", "direction"}
_PHASE_POLICY_KEYS = {
    "phase_id",
    "entry_residual_threshold_km2",
    "stop_tolerance_km2",
}


def _parse_components(
    value: Any,
    label: str,
) -> tuple[CombinedPriorityComponent, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    result: list[CombinedPriorityComponent] = []
    for index, raw_value in enumerate(value):
        raw = _mapping(raw_value, f"{label} component {index}")
        _exact_keys(raw, _PRIORITY_COMPONENT_KEYS, f"{label} component {index}")
        result.append(
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
    return tuple(result)


def _parse_phase_policies(
    value: Any,
    label: str,
) -> tuple[CombinedAllocationPhasePolicy, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    result: list[CombinedAllocationPhasePolicy] = []
    for index, raw_value in enumerate(value):
        raw = _mapping(raw_value, f"{label} phase {index}")
        _exact_keys(raw, _PHASE_POLICY_KEYS, f"{label} phase {index}")
        result.append(
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
    return tuple(result)


def _parse_score_input(value: Any) -> CombinedScoreInputContract:
    raw = _mapping(value, "combined score input")
    _exact_keys(raw, _SCORE_INPUT_KEYS, "combined score input")
    raw_parameters = raw["numeric_parameters"]
    if not isinstance(raw_parameters, list):
        raise TypeError("Combined score-input parameters must be a list")
    parameters: list[CombinedScoreInputParameter] = []
    for index, raw_value in enumerate(raw_parameters):
        parameter = _mapping(raw_value, f"score-input parameter {index}")
        _exact_keys(
            parameter,
            _NUMERIC_PARAMETER_KEYS,
            f"score-input parameter {index}",
        )
        parameters.append(
            CombinedScoreInputParameter(
                parameter_id=_identifier(
                    parameter["id"],
                    f"score-input parameter {index} id",
                ),
                value=_finite_number(
                    parameter["value"],
                    f"score-input parameter {index} value",
                ),
            )
        )
    raw_selections = raw["layer_selections"]
    if not isinstance(raw_selections, list):
        raise TypeError("Combined score-input layer selections must be a list")
    selections: list[CombinedScoreLayerSelection] = []
    for index, raw_value in enumerate(raw_selections):
        selection = _mapping(raw_value, f"score-input selection {index}")
        _exact_keys(
            selection,
            _LAYER_SELECTION_KEYS,
            f"score-input selection {index}",
        )
        raw_layer_ids = selection["layer_ids"]
        if not isinstance(raw_layer_ids, list):
            raise TypeError(
                f"Score-input selection {index} layer ids must be a list"
            )
        selections.append(
            CombinedScoreLayerSelection(
                technology_id=_identifier(
                    selection["technology_id"],
                    f"score-input selection {index} technology",
                ),
                analysis_id=_identifier(
                    selection["analysis_id"],
                    f"score-input selection {index} analysis",
                ),
                group_id=_identifier(
                    selection["group_id"],
                    f"score-input selection {index} group",
                ),
                layer_ids=tuple(
                    _identifier(
                        item,
                        f"score-input selection {index} layer {layer_index}",
                    )
                    for layer_index, item in enumerate(raw_layer_ids)
                ),
            )
        )
    return CombinedScoreInputContract(
        input_id=_identifier(raw["input_id"], "combined score input id"),
        base_score_model=_identifier(
            raw["base_score_model"],
            "combined base-score model",
        ),
        executor_id=_identifier(
            raw["executor_id"],
            "combined score-input executor id",
        ),
        numeric_parameters=tuple(parameters),
        layer_selections=tuple(selections),
    )


def _validate_components(
    components: tuple[CombinedPriorityComponent, ...],
    *,
    label: str,
    outside: bool,
    outside_enabled: bool,
    co_use_policy: str,
) -> None:
    if not components:
        raise ValueError(f"{label} must declare an explicit component order")
    component_ids = tuple(item.component_id for item in components)
    if len(component_ids) != len(set(component_ids)):
        raise ValueError(f"{label} component ids must be unique")
    sources: list[str] = []
    for component in components:
        if component.value_source not in _PRIORITY_VALUE_SOURCES:
            raise NotImplementedError(
                f"Unsupported {label} value source: {component.value_source}"
            )
        if component.direction not in _PRIORITY_DIRECTIONS:
            raise NotImplementedError(
                f"Unsupported {label} direction: {component.direction}"
            )
        required_direction = {
            "base_score": "descending",
            "outside_ring": "ascending",
            "potential_fraction": "descending",
            "potential_area_km2": "descending",
            "reservation_state": "ascending",
            "stable_cell_id": "ascending",
            "wind_zone_size": "descending",
        }.get(component.value_source)
        if required_direction is not None and component.direction != required_direction:
            raise ValueError(
                f"{label} {component.value_source} must be {required_direction}"
            )
        sources.append(component.value_source)
    if sources.count("base_score") != 1:
        raise ValueError(f"{label} must use base_score exactly once")
    if sources.count("stable_cell_id") != 1 or sources[-1] != "stable_cell_id":
        raise ValueError(f"{label} must end with stable_cell_id")
    if outside:
        if not outside_enabled or sources.count("outside_ring") != 1:
            raise ValueError(f"{label} must use one outside_ring when enabled")
    elif "outside_ring" in sources:
        raise ValueError(f"{label} cannot use outside_ring")
    if co_use_policy == "allow_with_reservation_tiebreak" and not outside:
        if sources.count("reservation_state") != 1:
            raise ValueError(
                f"{label} must explicitly include reservation_state"
            )
    elif co_use_policy == "disallow_shared_cells" and "reservation_state" in sources:
        raise ValueError(
            f"{label} cannot include reservation_state when co-use is disallowed"
        )
    if sources.count("reservation_state") > 1:
        raise ValueError(f"{label} may include reservation_state only once")


def validate_combined_result_policy_contract(
    contract: CombinedResultPolicyContract,
) -> None:
    if not isinstance(contract, CombinedResultPolicyContract):
        raise TypeError("contract must be a CombinedResultPolicyContract")
    if contract.schema_version != COMBINED_RESULT_POLICY_CONTRACT_SCHEMA_VERSION:
        raise NotImplementedError(
            "Unsupported combined-result policy contract schema: "
            f"{contract.schema_version}"
        )
    if contract.capability_id != COMBINED_RESULT_CAPABILITY_ID:
        raise ValueError("Combined-result capability identity is invalid")
    _identifier(contract.policy_id, "combined-result policy id")
    if not contract.technology_order:
        raise ValueError("Combined-result technology order must not be empty")
    for technology_id in contract.technology_order:
        _identifier(technology_id, "combined-result technology id")
    if len(contract.technology_order) != len(set(contract.technology_order)):
        raise ValueError("Combined-result technology order must be unique")
    _resolution(
        contract.finalization_resolution,
        "combined-result finalization resolution",
    )
    for resolution in contract.rollup_resolutions:
        _resolution(resolution, "combined-result rollup resolution")
    if (
        len(contract.rollup_resolutions) != len(set(contract.rollup_resolutions))
        or contract.rollup_resolutions
        != tuple(sorted(contract.rollup_resolutions, reverse=True))
        or any(
            value >= contract.finalization_resolution
            for value in contract.rollup_resolutions
        )
    ):
        raise ValueError(
            "Combined-result rollups must be unique, descending and coarser"
        )
    if contract.co_use_policy not in _CO_USE_POLICIES:
        raise NotImplementedError(
            f"Unsupported combined co-use policy: {contract.co_use_policy}"
        )
    if contract.outside_potential_policy not in _OUTSIDE_POTENTIAL_POLICIES:
        raise NotImplementedError(
            "Unsupported combined outside-potential policy: "
            f"{contract.outside_potential_policy}"
        )
    if contract.outside_ring_model not in _OUTSIDE_RING_MODELS:
        raise NotImplementedError(
            f"Unsupported combined outside-ring model: {contract.outside_ring_model}"
        )
    outside_enabled = contract.outside_potential_policy != "disabled"
    if outside_enabled != (contract.outside_ring_model != "none"):
        raise ValueError(
            "Combined outside allocation and ring model are inconsistent"
        )
    if contract.rollup_model not in _ROLLUP_MODELS:
        raise NotImplementedError(
            f"Unsupported combined rollup model: {contract.rollup_model}"
        )
    score_input = contract.score_input
    _identifier(score_input.input_id, "combined score input id")
    _identifier(score_input.executor_id, "combined score executor id")
    if score_input.base_score_model not in _BASE_SCORE_MODELS:
        raise NotImplementedError(
            f"Unsupported combined base-score model: {score_input.base_score_model}"
        )
    parameter_ids = tuple(
        item.parameter_id for item in score_input.numeric_parameters
    )
    if len(parameter_ids) != len(set(parameter_ids)):
        raise ValueError("Combined score-input parameter ids must be unique")
    if parameter_ids != tuple(sorted(parameter_ids)):
        raise ValueError(
            "Combined score-input parameters must use canonical id order"
        )
    selection_ids: list[tuple[str, str]] = []
    for selection in score_input.layer_selections:
        if not isinstance(selection, CombinedScoreLayerSelection):
            raise TypeError("Combined score-input selection has an invalid type")
        if selection.technology_id not in contract.technology_order:
            raise ValueError(
                "Combined score-input selection has an undeclared technology"
            )
        _identifier(selection.analysis_id, "combined score-input analysis id")
        _identifier(selection.group_id, "combined score-input group id")
        if not selection.layer_ids:
            raise ValueError(
                "Combined score-input layer selection must not be empty"
            )
        if (
            len(selection.layer_ids) != len(set(selection.layer_ids))
            or selection.layer_ids != tuple(sorted(selection.layer_ids))
        ):
            raise ValueError(
                "Combined score-input layer ids must be unique and sorted"
            )
        selection_ids.append((selection.technology_id, selection.group_id))
    if len(selection_ids) != len(set(selection_ids)):
        raise ValueError(
            "Combined score-input technology/group selections must be unique"
        )
    technology_index = {
        technology_id: index
        for index, technology_id in enumerate(contract.technology_order)
    }
    if selection_ids != sorted(
        selection_ids,
        key=lambda item: (technology_index[item[0]], item[1]),
    ):
        raise ValueError(
            "Combined score-input selections must use canonical technology/group order"
        )
    if len(contract.technology_priorities) != len(contract.technology_order):
        raise ValueError(
            "Combined technology priorities must match technology order"
        )
    for expected_technology, priority in zip(
        contract.technology_order,
        contract.technology_priorities,
        strict=True,
    ):
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
            priority.phase_order != expected_phases
            or any(item not in _ALLOCATION_PHASES for item in priority.phase_order)
        ):
            raise ValueError(
                "Combined phase order must explicitly put inside before outside"
            )
        if len(priority.phase_policies) != len(expected_phases):
            raise ValueError(
                "Combined phases need one explicit execution policy each"
            )
        for expected_phase, phase_policy in zip(
            expected_phases,
            priority.phase_policies,
            strict=True,
        ):
            if not isinstance(phase_policy, CombinedAllocationPhasePolicy):
                raise TypeError("Combined phase policy has an invalid type")
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
        _validate_components(
            priority.inside_components,
            label=f"{expected_technology} inside priority",
            outside=False,
            outside_enabled=outside_enabled,
            co_use_policy=contract.co_use_policy,
        )
        if outside_enabled:
            _validate_components(
                priority.outside_components,
                label=f"{expected_technology} outside priority",
                outside=True,
                outside_enabled=True,
                co_use_policy=contract.co_use_policy,
            )
        elif priority.outside_components:
            raise ValueError(
                "Disabled outside allocation cannot declare outside components"
            )


def parse_combined_result_policy_contract(
    value: Any,
) -> CombinedResultPolicyContract:
    raw = _mapping(value, "combined-result policy contract")
    _exact_keys(raw, _CONTRACT_KEYS, "combined-result policy contract")
    if raw["schema_version"] != COMBINED_RESULT_POLICY_CONTRACT_SCHEMA_VERSION:
        raise NotImplementedError(
            "Unsupported combined-result policy contract schema: "
            f"{raw['schema_version']}"
        )
    raw_order = raw["technology_order"]
    raw_rollups = raw["rollup_resolutions"]
    raw_priorities = raw["technology_priorities"]
    if not isinstance(raw_order, list):
        raise TypeError("Combined-result technology order must be a list")
    if not isinstance(raw_rollups, list):
        raise TypeError("Combined-result rollups must be a list")
    if not isinstance(raw_priorities, list):
        raise TypeError("Combined-result technology priorities must be a list")
    priorities: list[CombinedTechnologyPriority] = []
    for index, raw_value in enumerate(raw_priorities):
        priority = _mapping(raw_value, f"combined technology priority {index}")
        _exact_keys(
            priority,
            _TECHNOLOGY_PRIORITY_KEYS,
            f"combined technology priority {index}",
        )
        phase_order = priority["phase_order"]
        if not isinstance(phase_order, list):
            raise TypeError(
                f"Combined technology priority {index} phase order must be a list"
            )
        priorities.append(
            CombinedTechnologyPriority(
                technology_id=_identifier(
                    priority["technology_id"],
                    f"combined technology priority {index} technology",
                ),
                phase_order=tuple(
                    _identifier(item, f"combined phase {phase_index}")
                    for phase_index, item in enumerate(phase_order)
                ),
                phase_policies=_parse_phase_policies(
                    priority["phase_policies"],
                    f"combined technology priority {index} execution",
                ),
                inside_components=_parse_components(
                    priority["inside_components"],
                    f"combined technology priority {index} inside",
                ),
                outside_components=_parse_components(
                    priority["outside_components"],
                    f"combined technology priority {index} outside",
                ),
            )
        )
    contract = CombinedResultPolicyContract(
        schema_version=raw["schema_version"],
        capability_id=str(raw["capability_id"]),
        policy_id=_identifier(raw["policy_id"], "combined-result policy id"),
        technology_order=tuple(
            _identifier(item, f"combined technology {index}")
            for index, item in enumerate(raw_order)
        ),
        finalization_resolution=_resolution(
            raw["finalization_resolution"],
            "combined-result finalization resolution",
        ),
        rollup_resolutions=tuple(
            _resolution(item, f"combined rollup {index}")
            for index, item in enumerate(raw_rollups)
        ),
        co_use_policy=str(raw["co_use_policy"]),
        outside_potential_policy=str(raw["outside_potential_policy"]),
        outside_ring_model=str(raw["outside_ring_model"]),
        rollup_model=str(raw["rollup_model"]),
        score_input=_parse_score_input(raw["score_input"]),
        technology_priorities=tuple(priorities),
    )
    validate_combined_result_policy_contract(contract)
    return contract


def combined_result_policy_contract_from_form(
    section: Mapping[str, Any],
) -> CombinedResultPolicyContract:
    raw = _mapping(section, "combined-result form section")
    if raw.get("state") != "declared":
        raise ValueError("Combined-result form section is not declared")
    payload = {
        "schema_version": COMBINED_RESULT_POLICY_CONTRACT_SCHEMA_VERSION,
        "capability_id": raw["capability_id"],
        "policy_id": raw["policy_id"],
        "technology_order": raw["technology_order"],
        "finalization_resolution": raw["finalization_resolution"],
        "rollup_resolutions": raw["rollup_resolutions"],
        "co_use_policy": raw["co_use_policy"],
        "outside_potential_policy": raw["outside_potential_policy"],
        "outside_ring_model": raw["outside_ring_model"],
        "rollup_model": raw["rollup_model"],
        "score_input": raw["score_input"],
        "technology_priorities": raw["technology_priorities"],
    }
    return parse_combined_result_policy_contract(payload)


def combined_result_policy_contract_signature(
    contract: CombinedResultPolicyContract,
) -> str:
    validate_combined_result_policy_contract(contract)
    return _canonical_sha256(contract.as_dict())


ScoreExecutor = Callable[
    [
        CombinedResultPolicyContract,
        Mapping[str, ResolvedCombinedScoreSurface],
        str,
    ],
    tuple[tuple[CombinedBaseScore, ...], tuple[CombinedPriorityValue, ...]],
]


def _surface_cell_ids(surface: ResolvedCombinedScoreSurface) -> tuple[str, ...]:
    path = Path(surface.path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    if _sha256_path(path) != surface.sha256:
        raise ValueError(
            f"Combined score surface checksum drifted for {surface.technology_id}"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping) or raw.get("type") != "FeatureCollection":
        raise ValueError("Combined score surface must be GeoJSON FeatureCollection")
    features = raw.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Combined score surface must contain features")
    cell_ids: list[str] = []
    for index, feature_value in enumerate(features):
        feature = _mapping(feature_value, f"combined score feature {index}")
        properties = _mapping(
            feature.get("properties"),
            f"combined score feature {index} properties",
        )
        cell_id = properties.get(surface.id_field)
        if (
            not isinstance(cell_id, str)
            or not h3.is_valid_cell(cell_id)
            or h3.get_resolution(cell_id) != surface.resolution
        ):
            raise ValueError(
                f"Combined score surface has invalid {surface.id_field}"
            )
        cell_ids.append(cell_id)
    if len(cell_ids) != len(set(cell_ids)):
        raise ValueError("Combined score surface cell ids must be unique")
    return tuple(sorted(cell_ids))


def _uniform_eligible_surface_executor(
    contract: CombinedResultPolicyContract,
    surfaces: Mapping[str, ResolvedCombinedScoreSurface],
    region_id: str,
) -> tuple[tuple[CombinedBaseScore, ...], tuple[CombinedPriorityValue, ...]]:
    del region_id
    parameters = {
        item.parameter_id: item.value
        for item in contract.score_input.numeric_parameters
    }
    if set(parameters) != {"uniform_score"}:
        raise ValueError(
            "uniform_eligible_surface_v1 requires exactly uniform_score"
        )
    if contract.score_input.layer_selections:
        raise ValueError(
            "uniform_eligible_surface_v1 cannot declare layer selections"
        )
    score = parameters["uniform_score"]
    if score < 0.0 or score > 1.0:
        raise ValueError("uniform_score must be between 0 and 1")
    if contract.outside_potential_policy != "disabled":
        raise NotImplementedError(
            "uniform_eligible_surface_v1 cannot generate outside-potential rings"
        )
    declared_value_components = {
        component.component_id
        for priority in contract.technology_priorities
        for component in (
            *priority.inside_components,
            *priority.outside_components,
        )
        if component.value_source == "declared_value"
    }
    if declared_value_components:
        raise NotImplementedError(
            "uniform_eligible_surface_v1 cannot generate declared priority values"
        )
    if set(surfaces) != set(contract.technology_order):
        raise ValueError(
            "Combined score surfaces must exactly cover the technology order"
        )
    cells_by_technology: dict[str, tuple[str, ...]] = {}
    for technology_id in contract.technology_order:
        surface = surfaces[technology_id]
        if (
            surface.technology_id != technology_id
            or surface.resolution != contract.finalization_resolution
        ):
            raise ValueError(
                "Combined score surface identity or resolution drifted"
            )
        cells_by_technology[technology_id] = _surface_cell_ids(surface)
    reference = cells_by_technology[contract.technology_order[0]]
    if any(value != reference for value in cells_by_technology.values()):
        raise ValueError(
            "Combined technologies must share one exact finalization domain"
        )
    return (
        tuple(
            CombinedBaseScore(
                technology_id=technology_id,
                cell_id=cell_id,
                score=score,
                outside_ring=None,
            )
            for technology_id in contract.technology_order
            for cell_id in cells_by_technology[technology_id]
        ),
        (),
    )


_TECHNICAL_WEIGHT_PARAMETER_IDS = {
    "solar_core_weight",
    "solar_landscape_weight",
    "solar_potential_weight",
    "wind_core_weight",
    "wind_landscape_weight",
    "wind_potential_weight",
}


def _technical_weights(
    contract: CombinedResultPolicyContract,
) -> Mapping[str, TechnicalRankingWeights]:
    parameters = {
        item.parameter_id: item.value
        for item in contract.score_input.numeric_parameters
    }
    if set(parameters) != _TECHNICAL_WEIGHT_PARAMETER_IDS:
        raise ValueError(
            "support_observation_landscape_v1 requires exactly the signed "
            "wind/solar landscape, potential and core weights"
        )
    return {
        technology_id: TechnicalRankingWeights(
            technology_id=technology_id,
            landscape=parameters[f"{technology_id}_landscape_weight"],
            potential=parameters[f"{technology_id}_potential_weight"],
            core=parameters[f"{technology_id}_core_weight"],
        )
        for technology_id in contract.technology_order
    }


def _group_distance_cap_m(layers: Iterable[Any]) -> float:
    parameters = []
    for layer in layers:
        parameter = layer.parameters.get("buffer_m")
        if parameter is None:
            raise ValueError(
                f"Combined ranking layer {layer.id} has no buffer_m contract"
            )
        parameters.append(parameter)
    signatures = {
        (
            item.value_type,
            item.unit,
            item.default,
            item.minimum,
            item.maximum,
            item.step,
        )
        for item in parameters
    }
    if len(signatures) != 1:
        raise ValueError(
            "Combined ranking group layers must share one buffer contract"
        )
    parameter = parameters[0]
    values = [
        value
        for value in (
            float(parameter.maximum or 0.0),
            float(parameter.default or 0.0) * 2.0,
            float(parameter.step or 0.0) * 20.0,
        )
        if math.isfinite(value) and value > 0.0
    ]
    return max(values or [1000.0])


def _ranking_analysis_kind(operation: str) -> str:
    if operation == "proximity_feasibility":
        return "proximity_feasibility"
    if operation == "distance_exclusion":
        return "distance_conflict"
    if operation == "hard_exclusion":
        return "hard_exclusion"
    raise NotImplementedError(
        f"Unsupported combined ranking layer operation: {operation}"
    )


def _support_observation_landscape_executor(
    contract: CombinedResultPolicyContract,
    surfaces: Mapping[str, ResolvedCombinedScoreSurface],
    region_id: str,
) -> tuple[tuple[CombinedBaseScore, ...], tuple[CombinedPriorityValue, ...]]:
    if contract.score_input.base_score_model != "landscape_potential_core_v1":
        raise ValueError(
            "support_observation_landscape_v1 requires "
            "landscape_potential_core_v1"
        )
    _technical_weights(contract)
    if contract.outside_ring_model != "selected_inside_h3_graph_distance_v1":
        raise ValueError(
            "support_observation_landscape_v1 requires dynamic selected-inside rings"
        )
    declared_value_components = {
        component.component_id
        for priority in contract.technology_priorities
        for component in (*priority.inside_components, *priority.outside_components)
        if component.value_source == "declared_value"
    }
    if declared_value_components:
        raise NotImplementedError(
            "support_observation_landscape_v1 does not generate declared values"
        )
    if set(surfaces) != set(contract.technology_order):
        raise ValueError(
            "Combined score surfaces must exactly cover the technology order"
        )
    cells_by_technology: dict[str, tuple[str, ...]] = {}
    for technology_id in contract.technology_order:
        surface = surfaces[technology_id]
        if (
            surface.technology_id != technology_id
            or surface.resolution != contract.finalization_resolution
        ):
            raise ValueError("Combined score surface identity or resolution drifted")
        cells_by_technology[technology_id] = _surface_cell_ids(surface)
    reference_cells = cells_by_technology[contract.technology_order[0]]
    if any(
        cell_ids != reference_cells
        for cell_ids in cells_by_technology.values()
    ):
        raise ValueError(
            "Combined technologies must share one exact finalization domain"
        )

    selection_by_technology: dict[
        str, tuple[CombinedScoreLayerSelection, ...]
    ] = {
        technology_id: tuple(
            item
            for item in contract.score_input.layer_selections
            if item.technology_id == technology_id
        )
        for technology_id in contract.technology_order
    }
    scores: list[CombinedBaseScore] = []
    for technology_id in contract.technology_order:
        selections = selection_by_technology[technology_id]
        analysis_ids = {item.analysis_id for item in selections}
        if len(analysis_ids) != 1:
            raise ValueError(
                f"{technology_id} combined ranking must use one analysis contract"
            )
        analysis = load_analysis(region_id, next(iter(analysis_ids)))
        if analysis.region_id != region_id:
            raise ValueError("Combined score-input analysis region drifted")
        if analysis.area_result is None:
            raise ValueError(
                "Combined score-input analysis has no area-result contract"
            )
        if analysis.area_result.technology != technology_id:
            raise ValueError(
                "Combined score-input analysis technology drifted"
            )
        eligible_surface = analysis.eligible_surfaces.get(
            analysis.area_result.eligible_surface_id
        )
        resolved_surface = surfaces[technology_id]
        if (
            eligible_surface is None
            or resolved_surface.provider != eligible_surface.provider
            or resolved_surface.provider_path != eligible_surface.path
            or resolved_surface.sha256 != eligible_surface.sha256
            or resolved_surface.id_field != eligible_surface.id_field
            or resolved_surface.resolution != eligible_surface.resolution
        ):
            raise ValueError(
                "Combined score-input surface drifted from its analysis contract"
            )
        expected_groups = set(analysis.area_result.applicable_group_ids)
        if {item.group_id for item in selections} != expected_groups:
            raise ValueError(
                f"{technology_id} combined ranking must select every applicable group"
            )
        group_scores: list[dict[str, float]] = []
        for selection in selections:
            selected_layers = []
            observations_by_layer = []
            for layer_id in selection.layer_ids:
                layer = analysis.layers.get(layer_id)
                if layer is None or layer.group_id != selection.group_id:
                    raise ValueError(
                        f"Combined ranking layer {layer_id} is not declared in "
                        f"group {selection.group_id}"
                    )
                selected_layers.append(layer)
                observations = resolve_support_observations(analysis, layer_id)
                if tuple(item.cell_id for item in observations) != reference_cells:
                    raise ValueError(
                        f"Combined ranking observations drifted for {layer_id}"
                    )
                observations_by_layer.append(observations)
            operations = {
                _ranking_analysis_kind(layer.operation)
                for layer in selected_layers
            }
            if len(operations) != 1:
                raise ValueError(
                    f"Combined ranking group {selection.group_id} mixes operations"
                )
            analysis_kind = next(iter(operations))
            cap_m = _group_distance_cap_m(selected_layers)
            group_scores.append(
                {
                    cell_id: landscape_group_score(
                        analysis_kind=analysis_kind,
                        distance_m=min(
                            layer.source.total_observation_distance_m(
                                observations[index].distance_m,
                                observations[index].intersects,
                            )
                            for layer, observations in zip(selected_layers, observations_by_layer)
                        ),
                        intersects=any(
                            observations[index].intersects
                            for observations in observations_by_layer
                        ),
                        distance_cap_m=cap_m,
                    )
                    for index, cell_id in enumerate(reference_cells)
                }
            )
        scores.extend(
            CombinedBaseScore(
                technology_id=technology_id,
                cell_id=cell_id,
                score=math.fsum(
                    item[cell_id] for item in group_scores
                )
                / float(len(group_scores)),
                outside_ring=None,
            )
            for cell_id in reference_cells
        )
    return tuple(scores), ()


_SCORE_EXECUTORS: dict[str, ScoreExecutor] = {
    "support_observation_landscape_v1": (
        _support_observation_landscape_executor
    ),
    "uniform_eligible_surface_v1": _uniform_eligible_surface_executor,
}


def registered_combined_score_executor_ids() -> tuple[str, ...]:
    return tuple(sorted(_SCORE_EXECUTORS))


def materialize_combined_result_policy(
    section: Mapping[str, Any],
    *,
    region_id: str,
    surfaces: Mapping[str, ResolvedCombinedScoreSurface],
    generated_root: Path,
) -> CombinedResultCompilation:
    contract = combined_result_policy_contract_from_form(section)
    normalized_region = _identifier(region_id, "combined-result region id")
    executor = _SCORE_EXECUTORS.get(contract.score_input.executor_id)
    if executor is None:
        raise NotImplementedError(
            "Combined score-input executor is not registered: "
            f"{contract.score_input.executor_id}"
        )
    base_scores, priority_values = executor(contract, surfaces, normalized_region)
    policy = build_combined_allocation_policy(
        policy_id=contract.policy_id,
        finalization_resolution=contract.finalization_resolution,
        base_score_model=contract.score_input.base_score_model,
        base_score_input_id=contract.score_input.input_id,
        model_parameters=(
            CombinedModelParameter(
                parameter_id=item.parameter_id,
                value=item.value,
            )
            for item in contract.score_input.numeric_parameters
        ),
        base_scores=base_scores,
        technology_order=contract.technology_order,
        technology_priorities=contract.technology_priorities,
        priority_values=priority_values,
        co_use_policy=contract.co_use_policy,
        outside_potential_policy=contract.outside_potential_policy,
        outside_ring_model=contract.outside_ring_model,
        rollup_model=contract.rollup_model,
        rollup_resolutions=contract.rollup_resolutions,
    )
    if parse_combined_allocation_policy(policy.as_dict()) != policy:
        raise ValueError("Generated combined allocation policy is not canonical")

    relative_path = (
        "data/generated/combined_result/"
        f"{normalized_region}_{contract.policy_id}_allocation_policy.json"
    )
    target = generated_root.joinpath(*relative_path.split("/")).resolve()
    root = generated_root.resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise ValueError("Generated combined policy escapes generated root") from None
    target.parent.mkdir(parents=True, exist_ok=True)
    payload_bytes = (
        json.dumps(policy.as_dict(), ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    target.write_bytes(payload_bytes)
    artifact_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    contract_signature = combined_result_policy_contract_signature(contract)
    manifest = {
        "schema_version": "1.0",
        "capability_id": COMBINED_RESULT_CAPABILITY_ID,
        "region_id": normalized_region,
        "materialization_status": COMBINED_RESULT_COMPILED_STATUS,
        "policy_contract": contract.as_dict(),
        "policy_contract_signature_sha256": contract_signature,
        "allocation_policy_artifact": {
            "provider": "generated_runtime",
            "path": relative_path,
            "format": "json",
            "sha256": artifact_sha256,
            "bytes": len(payload_bytes),
            "base_score_count": len(policy.base_scores),
            "priority_value_count": len(policy.priority_values),
            "base_score_input_signature_sha256": (
                policy.base_score_input_signature_sha256
            ),
            "policy_signature_sha256": policy.policy_signature_sha256,
        },
    }
    evidence = {
        "schema_version": "1.0",
        "compiler_id": "speedlocal_combined_result_compiler",
        "compiler_version": COMBINED_RESULT_COMPILER_VERSION,
        "materialization_status": COMBINED_RESULT_COMPILED_STATUS,
        "capability_id": COMBINED_RESULT_CAPABILITY_ID,
        "region_id": normalized_region,
        "policy_id": contract.policy_id,
        "policy_contract_signature_sha256": contract_signature,
        "score_input": {
            "input_id": contract.score_input.input_id,
            "base_score_model": contract.score_input.base_score_model,
            "executor_id": contract.score_input.executor_id,
            "executor_registered": True,
            "generated_base_score_count": len(policy.base_scores),
            "generated_priority_value_count": len(policy.priority_values),
            "base_score_input_signature_sha256": (
                policy.base_score_input_signature_sha256
            ),
        },
        "resolved_score_surfaces": [
            {
                "technology_id": technology_id,
                "provider": surfaces[technology_id].provider,
                "path": surfaces[technology_id].provider_path,
                "sha256": surfaces[technology_id].sha256,
                "id_field": surfaces[technology_id].id_field,
                "resolution": surfaces[technology_id].resolution,
            }
            for technology_id in contract.technology_order
        ],
        "allocation_policy_artifact": dict(
            manifest["allocation_policy_artifact"]
        ),
        "technology_order": list(contract.technology_order),
        "finalization_resolution": contract.finalization_resolution,
        "rollup_resolutions": list(contract.rollup_resolutions),
        "landing_card_enabled": False,
    }
    return CombinedResultCompilation(
        manifest=manifest,
        evidence=evidence,
        generated_paths=(relative_path,),
        readiness_state="not_validated",
        readiness_detail=(
            "Combined-result policy contract, registered score executor, "
            "generated cell values and signatures are materialized; the "
            "independent request/result gate remains outstanding."
        ),
    )


__all__ = [
    "COMBINED_RESULT_COMPILED_STATUS",
    "COMBINED_RESULT_COMPILER_VERSION",
    "COMBINED_RESULT_POLICY_CONTRACT_SCHEMA_VERSION",
    "CombinedResultCompilation",
    "CombinedResultPolicyContract",
    "CombinedScoreInputContract",
    "CombinedScoreLayerSelection",
    "CombinedScoreInputParameter",
    "ResolvedCombinedScoreSurface",
    "combined_result_policy_contract_from_form",
    "combined_result_policy_contract_signature",
    "materialize_combined_result_policy",
    "parse_combined_result_policy_contract",
    "registered_combined_score_executor_ids",
    "validate_combined_result_policy_contract",
]
