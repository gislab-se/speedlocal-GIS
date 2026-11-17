from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Protocol

import h3


class ResolvedRooftopAsset(Protocol):
    provider: str
    provider_path: str
    format: str
    path: Path
    bytes: int
    sha256: str


@dataclass(frozen=True)
class RooftopSolarCompilation:
    """One complete manifest fragment and its generated integrity evidence."""

    contract: Mapping[str, Any]
    evidence: Mapping[str, Any]


def _id_digest(values: set[str] | tuple[str, ...] | list[str]) -> str:
    return hashlib.sha256(
        "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    ).hexdigest()


def _field_digest(values: tuple[str, ...]) -> str:
    return hashlib.sha256(
        "".join(f"{value}\n" for value in values).encode("utf-8")
    ).hexdigest()


def _domain_cell_ids(
    path: Path,
    artifact: Mapping[str, Any],
    expected_cell_ids_sha256: str,
) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Taksolens standarddomän kan inte läsas: {exc}"
        ) from exc
    features = payload.get("features") if isinstance(payload, Mapping) else None
    if not isinstance(features, list) or not features:
        raise ValueError(
            "Taksolens standarddomän måste vara en GeoJSON FeatureCollection "
            "med minst en H3-cell"
        )
    id_field = str(artifact["id_field"])
    resolution = int(artifact["resolution"])
    cell_ids: list[str] = []
    for index, feature in enumerate(features):
        properties = (
            feature.get("properties")
            if isinstance(feature, Mapping)
            else None
        )
        cell_id = (
            str(properties.get(id_field) or "").strip()
            if isinstance(properties, Mapping)
            else ""
        )
        if (
            not cell_id
            or not h3.is_valid_cell(cell_id)
            or h3.get_resolution(cell_id) != resolution
        ):
            raise ValueError(
                f"Taksolens standarddomän har ogiltigt R{resolution}-id på rad {index}"
            )
        cell_ids.append(cell_id)
    if len(cell_ids) != len(set(cell_ids)):
        raise ValueError("Taksolens standarddomän innehåller duplicerade H3-id:n")
    if len(cell_ids) != int(artifact["expected_cell_count"]):
        raise ValueError(
            "Taksolens standarddomän har fel cellantal: "
            f"{len(cell_ids)} != {artifact['expected_cell_count']}"
        )
    actual_digest = _id_digest(cell_ids)
    if actual_digest != expected_cell_ids_sha256:
        raise ValueError(
            "Taksolens standarddomän har fel cell-id-digest: "
            f"{actual_digest} != {expected_cell_ids_sha256}"
        )
    return set(cell_ids)


def _population_rows(
    asset: ResolvedRooftopAsset,
    declaration: Mapping[str, Any],
) -> tuple[tuple[str, ...], list[tuple[str, float]]]:
    if asset.format != "csv":
        raise NotImplementedError(
            "Den generella taksolsadaptern stöder ännu inte "
            f"format={asset.format}; capabilityn förblir låst."
        )
    try:
        with asset.path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            field_names = tuple(str(value) for value in (reader.fieldnames or ()))
            raw_rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValueError(
            f"Taksolens befolknings-CSV kan inte läsas: {exc}"
        ) from exc
    id_field = str(declaration["h3_id_field"])
    value_field = str(declaration["value_field"])
    missing_fields = {id_field, value_field}.difference(field_names)
    if missing_fields:
        raise ValueError(
            "Taksolens befolkningskälla saknar kolumner: "
            f"{sorted(missing_fields)}"
        )
    if not raw_rows:
        raise ValueError("Taksolens befolkningskälla är tom")
    resolution = int(declaration["source_h3_resolution"])
    rows: list[tuple[str, float]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_rows, start=2):
        cell_id = str(raw.get(id_field) or "").strip()
        if (
            not cell_id
            or not h3.is_valid_cell(cell_id)
            or h3.get_resolution(cell_id) != resolution
        ):
            raise ValueError(
                f"Taksolens befolkningskälla har ogiltigt R{resolution}-id på CSV-rad {index}"
            )
        if cell_id in seen:
            raise ValueError(
                f"Taksolens befolkningskälla har duplicerat H3-id: {cell_id}"
            )
        seen.add(cell_id)
        try:
            population = float(raw.get(value_field) or "")
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Taksolens befolkningsvärde är inte numeriskt på CSV-rad {index}"
            ) from exc
        if not math.isfinite(population) or population < 0.0:
            raise ValueError(
                f"Taksolens befolkningsvärde måste vara ändligt och icke-negativt på CSV-rad {index}"
            )
        rows.append((cell_id, population))
    return field_names, rows


def _analysis_population(
    rows: list[tuple[str, float]],
    *,
    source_resolution: int,
    analysis_resolution: int,
) -> dict[str, float]:
    if source_resolution < analysis_resolution:
        raise ValueError(
            "Taksolens befolkningskälla är grövre än analysdomänen"
        )
    values: dict[str, list[float]] = {}
    for source_cell_id, population in rows:
        cell_id = (
            source_cell_id
            if source_resolution == analysis_resolution
            else h3.cell_to_parent(source_cell_id, analysis_resolution)
        )
        values.setdefault(cell_id, []).append(population)
    return {
        cell_id: math.fsum(items)
        for cell_id, items in values.items()
    }


def materialize_rooftop_solar(
    declaration: Mapping[str, Any],
    *,
    region_id: str,
    source_asset: ResolvedRooftopAsset,
    domain_artifact: Mapping[str, Any],
    domain_cell_ids_sha256: str,
    domain_path: Path,
    rollup_resolutions: tuple[int, ...],
) -> RooftopSolarCompilation:
    """Materialize one complete rooftop contract from human choices and bytes."""

    if declaration.get("state") != "declared":
        raise ValueError("Taksolens blankett måste vara declared")
    analysis_resolution = int(
        declaration["population_source"]["analysis_h3_resolution"]
    )
    if analysis_resolution != int(domain_artifact["resolution"]):
        raise ValueError(
            "Taksolens befolkningskälla och standarddomän har olika analysupplösning"
        )
    domain_ids = _domain_cell_ids(
        domain_path,
        domain_artifact,
        domain_cell_ids_sha256,
    )
    population_declaration = declaration["population_source"]
    field_names, rows = _population_rows(
        source_asset,
        population_declaration,
    )
    source_total = math.fsum(population for _, population in rows)
    if not math.isfinite(source_total) or source_total <= 0.0:
        raise ValueError(
            "Taksolens befolkningskälla måste ha en positiv, ändlig totalsumma"
        )
    analysis_population = _analysis_population(
        rows,
        source_resolution=int(population_declaration["source_h3_resolution"]),
        analysis_resolution=analysis_resolution,
    )
    analysis_source_ids = set(analysis_population)
    covered_ids = analysis_source_ids.intersection(domain_ids)
    uncovered_ids = domain_ids.difference(analysis_source_ids)
    outside_ids = analysis_source_ids.difference(domain_ids)
    mapped_population = {
        cell_id: analysis_population[cell_id]
        for cell_id in covered_ids
    }
    mapped_total = math.fsum(mapped_population.values())
    if not math.isfinite(mapped_total) or mapped_total <= 0.0:
        raise ValueError(
            "Taksolens befolkningskälla saknar positiv överlapp med standarddomänen"
        )

    target_resolutions = (analysis_resolution, *rollup_resolutions)
    if (
        len(target_resolutions) != len(set(target_resolutions))
        or any(value >= analysis_resolution for value in rollup_resolutions)
    ):
        raise ValueError("Taksolens rollupnivåer är inte giltiga parentnivåer")
    expected_totals: list[dict[str, Any]] = []
    rollup_evidence: list[dict[str, Any]] = []
    for target_resolution in target_resolutions:
        grouped: dict[str, list[float]] = {}
        for cell_id, population in mapped_population.items():
            target_cell_id = (
                cell_id
                if target_resolution == analysis_resolution
                else h3.cell_to_parent(cell_id, target_resolution)
            )
            grouped.setdefault(target_cell_id, []).append(population)
        values = {
            cell_id: math.fsum(items)
            for cell_id, items in grouped.items()
        }
        total = math.fsum(values.values())
        if not math.isclose(total, mapped_total, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                f"Taksolens R{target_resolution}-rollup ändrar befolkningssumman"
            )
        expected_totals.append(
            {"resolution": target_resolution, "total": total}
        )
        rollup_evidence.append(
            {
                "resolution": target_resolution,
                "mapped_cell_count": len(values),
                "mapped_cell_ids_sha256": _id_digest(set(values)),
                "mapped_population_total": total,
            }
        )

    panel = declaration["panel_area_m2_per_person"]
    annual = declaration["annual_yield"]
    expected_kwh_per_m2 = (
        float(annual["specific_yield_kwh_per_kwp"])
        * float(annual["module_efficiency_stc_fraction"])
    )
    if not math.isfinite(expected_kwh_per_m2) or expected_kwh_per_m2 <= 0.0:
        raise ValueError("Taksolens härledda kWh/m2 måste vara positiv och ändlig")
    trust = declaration["trust"]
    population_contract = {
        "provider": source_asset.provider,
        "path": source_asset.provider_path,
        "sha256": source_asset.sha256,
        "format": source_asset.format,
        "h3_id_field": population_declaration["h3_id_field"],
        "value_field": population_declaration["value_field"],
        "source_h3_resolution": population_declaration[
            "source_h3_resolution"
        ],
        "analysis_h3_resolution": analysis_resolution,
        "aggregation": population_declaration["aggregation"],
        "expected_row_count": len(rows),
        "expected_total": source_total,
        "accounting_total_policy": population_declaration[
            "accounting_total_policy"
        ],
        "expected_analysis_domain_totals": expected_totals,
        "semantics": population_declaration["semantics"],
        "missing_domain_cell_policy": population_declaration[
            "missing_domain_cell_policy"
        ],
        "provenance": dict(population_declaration["provenance"]),
    }
    annual_contract = {
        key: value
        for key, value in annual.items()
        if key != "provenance"
    }
    annual_contract["expected_kwh_per_m2"] = expected_kwh_per_m2
    annual_contract["provenance"] = dict(annual["provenance"])
    contract = {
        "status": "planning_proxy",
        "technology_key": "solar",
        "domain_reference": dict(declaration["domain_reference"]),
        "population_source": population_contract,
        "map_review": dict(declaration["map_review"]),
        "panel_area_m2_per_person": {
            "type": panel["type"],
            "unit": panel["unit"],
            "default": panel["technical_initial_value"],
            "minimum": panel["minimum"],
            "maximum": panel["maximum"],
            "step": panel["step"],
            "accepted_recommended_default": dict(
                panel["accepted_recommended_default"]
            ),
            "default_semantics": (
                "technical_initial_value_not_regional_recommendation"
            ),
        },
        "annual_yield": annual_contract,
        "accounting": dict(declaration["accounting"]),
        "trust": dict(trust),
        "limitation": declaration["limitation"],
        "replacement_condition": declaration["replacement_condition"],
    }
    evidence = {
        "status": "compiled_unvalidated",
        "capability_id": "solar.rooftop",
        "region_id": region_id,
        "source": {
            "provider": source_asset.provider,
            "path": source_asset.provider_path,
            "format": source_asset.format,
            "bytes": source_asset.bytes,
            "sha256": source_asset.sha256,
            "field_names": list(field_names),
            "field_names_sha256": _field_digest(field_names),
            "row_count": len(rows),
            "source_cell_count": len(rows),
            "source_cell_ids_sha256": _id_digest(
                [cell_id for cell_id, _ in rows]
            ),
            "source_population_total": source_total,
        },
        "domain": {
            "domain_id": declaration["domain_reference"]["domain_id"],
            "resolution": analysis_resolution,
            "cell_count": len(domain_ids),
            "cell_ids_sha256": domain_cell_ids_sha256,
        },
        "coverage": {
            "analysis_source_cell_count": len(analysis_source_ids),
            "analysis_source_cell_ids_sha256": _id_digest(analysis_source_ids),
            "covered_domain_cell_count": len(covered_ids),
            "covered_domain_cell_ids_sha256": _id_digest(covered_ids),
            "uncovered_domain_cell_count": len(uncovered_ids),
            "uncovered_domain_cell_ids_sha256": _id_digest(uncovered_ids),
            "outside_domain_source_cell_count": len(outside_ids),
            "outside_domain_source_cell_ids_sha256": _id_digest(outside_ids),
            "coverage_fraction": len(covered_ids) / len(domain_ids),
            "missing_domain_cell_policy": population_declaration[
                "missing_domain_cell_policy"
            ],
        },
        "rollups": rollup_evidence,
        "annual_yield": {
            "expected_kwh_per_m2": expected_kwh_per_m2,
            "calculation": (
                "specific_yield_kwh_per_kwp_times_"
                "module_efficiency_stc_fraction"
            ),
        },
        "parameter": {
            "technical_initial_value": panel["technical_initial_value"],
            "accepted_recommended_default": dict(
                panel["accepted_recommended_default"]
            ),
            "materialized_engine_default": panel["technical_initial_value"],
            "materialized_engine_default_semantics": (
                "technical_initial_value_not_regional_recommendation"
            ),
        },
        "trust": dict(trust),
    }
    return RooftopSolarCompilation(contract=contract, evidence=evidence)


__all__ = [
    "ResolvedRooftopAsset",
    "RooftopSolarCompilation",
    "materialize_rooftop_solar",
]
