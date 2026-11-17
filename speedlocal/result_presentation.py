from __future__ import annotations

from .allocation import known_sum

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence


RESULT_PRESENTATION_SCHEMA_VERSION = "1.0"
RESULT_PRESENTATION_EXACT_SCHEMA_VERSION = "2.0"
RESULT_AREA_SEMANTICS = "technology_sum"
RESULT_DISPLAY_TOLERANCE_KM2 = 1e-6
_RECONCILIATION_TOLERANCE = 1e-9
_FIT_STATUSES = {"no_demand", "within_potential", "shortage"}


@dataclass(frozen=True)
class ResultTechnologyInput:
    technology_id: str
    label: str
    energy_twh: float | None
    need_area_km2: float
    filtered_potential_area_km2: float
    potential_acceptance_ratio: float = 1.0


@dataclass(frozen=True)
class ResultTechnologyFacts:
    technology_id: str
    label: str
    energy_twh: float | None
    need_area_km2: float
    filtered_potential_area_km2: float
    potential_acceptance_ratio: float
    potential_after_acceptance_km2: float
    inside_potential_km2: float
    outside_need_km2: float
    unused_potential_km2: float
    coverage_pct: float


@dataclass(frozen=True)
class ResultTotalFacts:
    energy_twh: float | None
    need_area_km2: float
    filtered_potential_area_km2: float
    potential_after_acceptance_km2: float
    inside_potential_km2: float
    outside_need_km2: float
    unused_potential_km2: float
    coverage_pct: float


@dataclass(frozen=True)
class ResultPresentation:
    schema_version: str
    area_semantics: str
    fit_status: str
    display_tolerance_km2: float
    technologies: tuple[ResultTechnologyFacts, ...]
    total: ResultTotalFacts


def _finite_number(value: Any, field: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a finite number") from exc
    if not math.isfinite(number) or number < minimum:
        raise ValueError(f"{field} must be finite and at least {minimum}")
    return number


def _optional_energy(value, field):
    return None if value is None else _finite_number(value, field)


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _coverage_pct(inside_area_km2: float, need_area_km2: float) -> float:
    return inside_area_km2 / need_area_km2 * 100.0 if need_area_km2 > 0.0 else 0.0


def _technology_facts(value: ResultTechnologyInput) -> ResultTechnologyFacts:
    technology_id = _required_text(value.technology_id, "technology_id")
    label = _required_text(value.label, f"{technology_id}.label")
    energy_twh = _optional_energy(value.energy_twh, f"{technology_id}.energy_twh")
    need_area_km2 = _finite_number(
        value.need_area_km2,
        f"{technology_id}.need_area_km2",
    )
    filtered_potential_area_km2 = _finite_number(
        value.filtered_potential_area_km2,
        f"{technology_id}.filtered_potential_area_km2",
    )
    potential_acceptance_ratio = _finite_number(
        value.potential_acceptance_ratio,
        f"{technology_id}.potential_acceptance_ratio",
    )
    if potential_acceptance_ratio > 1.0:
        raise ValueError(
            f"{technology_id}.potential_acceptance_ratio must be at most 1.0"
        )
    potential_after_acceptance_km2 = (
        filtered_potential_area_km2 * potential_acceptance_ratio
    )
    inside_potential_km2 = min(
        need_area_km2,
        potential_after_acceptance_km2,
    )
    outside_need_km2 = max(0.0, need_area_km2 - inside_potential_km2)
    unused_potential_km2 = max(
        0.0,
        potential_after_acceptance_km2 - inside_potential_km2,
    )
    return ResultTechnologyFacts(
        technology_id=technology_id,
        label=label,
        energy_twh=energy_twh,
        need_area_km2=need_area_km2,
        filtered_potential_area_km2=filtered_potential_area_km2,
        potential_acceptance_ratio=potential_acceptance_ratio,
        potential_after_acceptance_km2=potential_after_acceptance_km2,
        inside_potential_km2=inside_potential_km2,
        outside_need_km2=outside_need_km2,
        unused_potential_km2=unused_potential_km2,
        coverage_pct=_coverage_pct(inside_potential_km2, need_area_km2),
    )


def build_result_presentation(
    technologies: Sequence[ResultTechnologyInput],
    *,
    display_tolerance_km2: float = RESULT_DISPLAY_TOLERANCE_KM2,
) -> ResultPresentation:
    if not technologies:
        raise ValueError("At least one result technology is required")
    tolerance = _finite_number(
        display_tolerance_km2,
        "display_tolerance_km2",
    )
    facts = tuple(_technology_facts(value) for value in technologies)
    technology_ids = [value.technology_id for value in facts]
    if len(set(technology_ids)) != len(technology_ids):
        raise ValueError("Result technology ids must be unique")

    total_need = sum(value.need_area_km2 for value in facts)
    total_inside = sum(value.inside_potential_km2 for value in facts)
    total = ResultTotalFacts(
        energy_twh=known_sum(value.energy_twh for value in facts),
        need_area_km2=total_need,
        filtered_potential_area_km2=sum(
            value.filtered_potential_area_km2 for value in facts
        ),
        potential_after_acceptance_km2=sum(
            value.potential_after_acceptance_km2 for value in facts
        ),
        inside_potential_km2=total_inside,
        outside_need_km2=sum(value.outside_need_km2 for value in facts),
        unused_potential_km2=sum(value.unused_potential_km2 for value in facts),
        coverage_pct=_coverage_pct(total_inside, total_need),
    )
    if total_need <= tolerance:
        fit_status = "no_demand"
    elif total.outside_need_km2 > tolerance:
        fit_status = "shortage"
    else:
        fit_status = "within_potential"
    return ResultPresentation(
        schema_version=RESULT_PRESENTATION_SCHEMA_VERSION,
        area_semantics=RESULT_AREA_SEMANTICS,
        fit_status=fit_status,
        display_tolerance_km2=tolerance,
        technologies=facts,
        total=total,
    )


def build_result_presentation_from_combined_summary(
    combined_presentation: Any,
    *,
    labels: Mapping[str, str],
    display_tolerance_km2: float = RESULT_DISPLAY_TOLERANCE_KM2,
) -> ResultPresentation:
    """Adapt the exact signed combined summary without recalculating allocation.

    The combined presentation is the authority for potential, accepted
    potential, inside allocation, outside allocation and unmet demand.  This
    adapter only supplies product labels and the existing compact table shape.
    """

    tolerance = _finite_number(
        display_tolerance_km2,
        "display_tolerance_km2",
    )
    try:
        summary = next(
            table
            for table in combined_presentation.tables
            if table.table_id == "technology_summary" and table.kind == "summary"
        )
    except (AttributeError, StopIteration) as exc:
        raise ValueError(
            "Combined presentation lacks its signed technology summary"
        ) from exc
    field_ids = tuple(field.field_id for field in summary.fields)
    required = {
        "technology_id",
        "allocation_state",
        "gross_energy_twh",
        "ground_area_need_km2",
        "potential_area_km2",
        "acceptance_adjusted_potential_area_km2",
        "selected_area_km2",
        "inside_potential_area_km2",
        "outside_potential_area_km2",
        "unmet_area_km2",
    }
    if not required.issubset(field_ids):
        raise ValueError("Combined summary omits required result fields")
    facts: list[ResultTechnologyFacts] = []
    for raw_row in summary.rows:
        if len(raw_row) != len(field_ids):
            raise ValueError("Combined summary row width drifted")
        row = dict(zip(field_ids, raw_row))
        technology_id = _required_text(row["technology_id"], "technology_id")
        if row["allocation_state"] != "executed":
            raise ValueError("Combined summary is not an executed allocation")
        label = _required_text(labels.get(technology_id), f"{technology_id}.label")
        energy = _optional_energy(
            row["gross_energy_twh"],
            f"{technology_id}.gross_energy_twh",
        )
        need = _finite_number(
            row["ground_area_need_km2"],
            f"{technology_id}.ground_area_need_km2",
        )
        potential = _finite_number(
            row["potential_area_km2"],
            f"{technology_id}.potential_area_km2",
        )
        accepted = _finite_number(
            row["acceptance_adjusted_potential_area_km2"],
            f"{technology_id}.acceptance_adjusted_potential_area_km2",
        )
        selected = _finite_number(
            row["selected_area_km2"],
            f"{technology_id}.selected_area_km2",
        )
        inside = _finite_number(
            row["inside_potential_area_km2"],
            f"{technology_id}.inside_potential_area_km2",
        )
        outside_selected = _finite_number(
            row["outside_potential_area_km2"],
            f"{technology_id}.outside_potential_area_km2",
        )
        unmet = _finite_number(
            row["unmet_area_km2"],
            f"{technology_id}.unmet_area_km2",
        )
        if (
            accepted > potential + _RECONCILIATION_TOLERANCE
            or not math.isclose(
                selected,
                inside + outside_selected,
                rel_tol=1e-12,
                abs_tol=_RECONCILIATION_TOLERANCE,
            )
            or not math.isclose(
                need,
                selected + unmet,
                rel_tol=1e-12,
                abs_tol=_RECONCILIATION_TOLERANCE,
            )
        ):
            raise ValueError("Combined summary allocation does not reconcile")
        acceptance_ratio = accepted / potential if potential > 0.0 else 1.0
        outside_need = outside_selected + unmet
        facts.append(
            ResultTechnologyFacts(
                technology_id=technology_id,
                label=label,
                energy_twh=energy,
                need_area_km2=need,
                filtered_potential_area_km2=potential,
                potential_acceptance_ratio=acceptance_ratio,
                potential_after_acceptance_km2=accepted,
                inside_potential_km2=inside,
                outside_need_km2=outside_need,
                unused_potential_km2=max(0.0, accepted - inside),
                coverage_pct=_coverage_pct(inside, need),
            )
        )
    if not facts or len({item.technology_id for item in facts}) != len(facts):
        raise ValueError("Combined summary technologies are empty or duplicated")
    total_need = math.fsum(item.need_area_km2 for item in facts)
    total_inside = math.fsum(item.inside_potential_km2 for item in facts)
    total = ResultTotalFacts(
        energy_twh=known_sum(item.energy_twh for item in facts),
        need_area_km2=total_need,
        filtered_potential_area_km2=math.fsum(
            item.filtered_potential_area_km2 for item in facts
        ),
        potential_after_acceptance_km2=math.fsum(
            item.potential_after_acceptance_km2 for item in facts
        ),
        inside_potential_km2=total_inside,
        outside_need_km2=math.fsum(item.outside_need_km2 for item in facts),
        unused_potential_km2=math.fsum(
            item.unused_potential_km2 for item in facts
        ),
        coverage_pct=_coverage_pct(total_inside, total_need),
    )
    fit_status = (
        "no_demand"
        if total_need <= tolerance
        else "shortage"
        if total.outside_need_km2 > tolerance
        else "within_potential"
    )
    return ResultPresentation(
        schema_version=RESULT_PRESENTATION_EXACT_SCHEMA_VERSION,
        area_semantics=RESULT_AREA_SEMANTICS,
        fit_status=fit_status,
        display_tolerance_km2=tolerance,
        technologies=tuple(facts),
        total=total,
    )


def result_technology(
    presentation: ResultPresentation,
    technology_id: str,
) -> ResultTechnologyFacts:
    normalized = _required_text(technology_id, "technology_id")
    for value in presentation.technologies:
        if value.technology_id == normalized:
            return value
    raise ValueError(f"Result presentation is missing technology {normalized!r}")


def serialize_result_presentation(presentation: ResultPresentation) -> dict[str, Any]:
    def technology_dict(value: ResultTechnologyFacts) -> dict[str, Any]:
        return {
            "technology_id": value.technology_id,
            "label": value.label,
            "energy_twh": value.energy_twh,
            "need_area_km2": value.need_area_km2,
            "filtered_potential_area_km2": value.filtered_potential_area_km2,
            "potential_acceptance_ratio": value.potential_acceptance_ratio,
            "potential_after_acceptance_km2": value.potential_after_acceptance_km2,
            "inside_potential_km2": value.inside_potential_km2,
            "outside_need_km2": value.outside_need_km2,
            "unused_potential_km2": value.unused_potential_km2,
            "coverage_pct": value.coverage_pct,
        }

    return {
        "schema_version": presentation.schema_version,
        "area_semantics": presentation.area_semantics,
        "fit_status": presentation.fit_status,
        "display_tolerance_km2": presentation.display_tolerance_km2,
        "technologies": [
            technology_dict(value) for value in presentation.technologies
        ],
        "total": {
            "energy_twh": presentation.total.energy_twh,
            "need_area_km2": presentation.total.need_area_km2,
            "filtered_potential_area_km2": presentation.total.filtered_potential_area_km2,
            "potential_after_acceptance_km2": presentation.total.potential_after_acceptance_km2,
            "inside_potential_km2": presentation.total.inside_potential_km2,
            "outside_need_km2": presentation.total.outside_need_km2,
            "unused_potential_km2": presentation.total.unused_potential_km2,
            "coverage_pct": presentation.total.coverage_pct,
        },
    }


def parse_result_presentation(raw: Mapping[str, Any]) -> ResultPresentation:
    if not isinstance(raw, Mapping):
        raise ValueError("Result presentation must be an object")
    schema_version = raw.get("schema_version")
    if schema_version not in {
        RESULT_PRESENTATION_SCHEMA_VERSION,
        RESULT_PRESENTATION_EXACT_SCHEMA_VERSION,
    }:
        raise ValueError("Unsupported result-presentation schema version")
    if raw.get("area_semantics") != RESULT_AREA_SEMANTICS:
        raise ValueError("Result area semantics must be technology_sum")
    raw_technologies = raw.get("technologies")
    if not isinstance(raw_technologies, list) or not raw_technologies:
        raise ValueError("Result presentation technologies must be a non-empty list")

    inputs: list[ResultTechnologyInput] = []
    for index, value in enumerate(raw_technologies):
        if not isinstance(value, Mapping):
            raise ValueError(f"Result technology {index} must be an object")
        inputs.append(
            ResultTechnologyInput(
                technology_id=value.get("technology_id", ""),
                label=value.get("label", ""),
                energy_twh=value.get("energy_twh"),
                need_area_km2=value.get("need_area_km2"),
                filtered_potential_area_km2=value.get(
                    "filtered_potential_area_km2"
                ),
                potential_acceptance_ratio=value.get(
                    "potential_acceptance_ratio"
                ),
            )
        )
    if schema_version == RESULT_PRESENTATION_SCHEMA_VERSION:
        rebuilt = build_result_presentation(
            inputs,
            display_tolerance_km2=raw.get("display_tolerance_km2"),
        )
    else:
        tolerance = _finite_number(
            raw.get("display_tolerance_km2"),
            "display_tolerance_km2",
        )
        facts = tuple(
            ResultTechnologyFacts(
                technology_id=_required_text(value.get("technology_id"), "technology_id"),
                label=_required_text(value.get("label"), "label"),
                energy_twh=_optional_energy(value.get("energy_twh"), "energy_twh"),
                need_area_km2=_finite_number(value.get("need_area_km2"), "need_area_km2"),
                filtered_potential_area_km2=_finite_number(value.get("filtered_potential_area_km2"), "filtered_potential_area_km2"),
                potential_acceptance_ratio=_finite_number(value.get("potential_acceptance_ratio"), "potential_acceptance_ratio"),
                potential_after_acceptance_km2=_finite_number(value.get("potential_after_acceptance_km2"), "potential_after_acceptance_km2"),
                inside_potential_km2=_finite_number(value.get("inside_potential_km2"), "inside_potential_km2"),
                outside_need_km2=_finite_number(value.get("outside_need_km2"), "outside_need_km2"),
                unused_potential_km2=_finite_number(value.get("unused_potential_km2"), "unused_potential_km2"),
                coverage_pct=_finite_number(value.get("coverage_pct"), "coverage_pct"),
            )
            for value in raw_technologies
        )
        if len({item.technology_id for item in facts}) != len(facts):
            raise ValueError("Result technology ids must be unique")
        for item in facts:
            if (
                item.potential_acceptance_ratio > 1.0
                or not math.isclose(
                    item.potential_after_acceptance_km2,
                    item.filtered_potential_area_km2
                    * item.potential_acceptance_ratio,
                    rel_tol=1e-12,
                    abs_tol=_RECONCILIATION_TOLERANCE,
                )
                or not math.isclose(
                    item.need_area_km2,
                    item.inside_potential_km2 + item.outside_need_km2,
                    rel_tol=1e-12,
                    abs_tol=_RECONCILIATION_TOLERANCE,
                )
                or not math.isclose(
                    item.unused_potential_km2,
                    max(
                        0.0,
                        item.potential_after_acceptance_km2
                        - item.inside_potential_km2,
                    ),
                    rel_tol=1e-12,
                    abs_tol=_RECONCILIATION_TOLERANCE,
                )
                or not math.isclose(
                    item.coverage_pct,
                    _coverage_pct(
                        item.inside_potential_km2,
                        item.need_area_km2,
                    ),
                    rel_tol=1e-12,
                    abs_tol=_RECONCILIATION_TOLERANCE,
                )
            ):
                raise ValueError(
                    "Exact result-presentation technology does not reconcile"
                )
        total_need = math.fsum(item.need_area_km2 for item in facts)
        total_inside = math.fsum(item.inside_potential_km2 for item in facts)
        rebuilt = ResultPresentation(
            schema_version=RESULT_PRESENTATION_EXACT_SCHEMA_VERSION,
            area_semantics=RESULT_AREA_SEMANTICS,
            fit_status=(
                "no_demand"
                if total_need <= tolerance
                else "shortage"
                if math.fsum(item.outside_need_km2 for item in facts) > tolerance
                else "within_potential"
            ),
            display_tolerance_km2=tolerance,
            technologies=facts,
            total=ResultTotalFacts(
                energy_twh=known_sum(item.energy_twh for item in facts),
                need_area_km2=total_need,
                filtered_potential_area_km2=math.fsum(item.filtered_potential_area_km2 for item in facts),
                potential_after_acceptance_km2=math.fsum(item.potential_after_acceptance_km2 for item in facts),
                inside_potential_km2=total_inside,
                outside_need_km2=math.fsum(item.outside_need_km2 for item in facts),
                unused_potential_km2=math.fsum(item.unused_potential_km2 for item in facts),
                coverage_pct=_coverage_pct(total_inside, total_need),
            ),
        )
    if raw.get("fit_status") not in _FIT_STATUSES:
        raise ValueError("Unsupported result-presentation fit status")
    if raw.get("fit_status") != rebuilt.fit_status:
        raise ValueError("Result-presentation fit status does not reconcile")

    serialized_rebuilt = serialize_result_presentation(rebuilt)
    for index, value in enumerate(raw_technologies):
        expected = serialized_rebuilt["technologies"][index]
        for field, expected_value in expected.items():
            actual_value = value.get(field)
            if isinstance(expected_value, float):
                actual_number = _finite_number(
                    actual_value,
                    f"technologies[{index}].{field}",
                )
                if not math.isclose(
                    actual_number,
                    expected_value,
                    rel_tol=1e-12,
                    abs_tol=_RECONCILIATION_TOLERANCE,
                ):
                    raise ValueError(
                        f"Result technology {index} field {field} does not reconcile"
                    )
            elif actual_value != expected_value:
                raise ValueError(
                    f"Result technology {index} field {field} does not reconcile"
                )

    raw_total = raw.get("total")
    if not isinstance(raw_total, Mapping):
        raise ValueError("Result presentation total must be an object")
    for field, expected_value in serialized_rebuilt["total"].items():
        if expected_value is None:
            if raw_total.get(field) is not None:
                raise ValueError(f"Result total field {field} does not reconcile")
            continue
        actual_number = _finite_number(raw_total.get(field), f"total.{field}")
        if not math.isclose(
            actual_number,
            expected_value,
            rel_tol=1e-12,
            abs_tol=_RECONCILIATION_TOLERANCE,
        ):
            raise ValueError(f"Result total field {field} does not reconcile")
    return rebuilt
