from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .scenarios import (
    SCENARIO_ADAPTER_NORMALIZED_JSON,
    SCENARIO_ADAPTER_TIMES_AREA_DEMAND,
    ResolvedScenarioAsset,
    build_scenario_request_from_contract,
    load_normalized_scenario_snapshot_from_paths,
    run_scenario_request,
    scenario_contract,
    scenario_contract_signature,
)


SCENARIO_COMPILER_VERSION = "1.1"
SCENARIO_COMPILED_STATUS = "compiled_unvalidated"


@dataclass(frozen=True)
class ScenarioCompilation:
    manifest: Mapping[str, Any]
    evidence: Mapping[str, Any]
    readiness_state: str
    readiness_detail: str


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_payload(asset: ResolvedScenarioAsset) -> dict[str, Any]:
    return {
        "path": str(asset.provider_path),
        "format": str(asset.format),
        "sha256": str(asset.sha256),
    }


def _validate_asset_binding(
    declaration: Mapping[str, Any],
    resolved: ResolvedScenarioAsset,
    *,
    role: str,
) -> None:
    if (
        str(declaration.get("provider") or "") != str(resolved.provider)
        or str(declaration.get("path") or "") != str(resolved.provider_path)
        or str(declaration.get("format") or "") != str(resolved.format)
    ):
        raise ValueError(f"Scenario {role} asset drifted after resolution")
    if not Path(resolved.path).is_file():
        raise FileNotFoundError(resolved.path)
    observed = _sha256_path(Path(resolved.path))
    if observed != str(resolved.sha256):
        raise ValueError(f"Scenario {role} asset checksum drifted after resolution")


def _planning_payload(section: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "default_scenario": section["default_scenario"],
        "area_demand_options": [
            {
                "id": item["id"],
                "label": item["label"],
            }
            for item in section["area_demand_options"]
        ],
        "default_area_demand_scenario": section[
            "default_area_demand_scenario"
        ],
        "technology_mix": {
            "share_step_pct": section["technology_mix"]["share_step_pct"],
            "default_shares": [
                {
                    "technology_id": item["technology_id"],
                    "share_pct": item["share_pct"],
                }
                for item in section["technology_mix"]["default_shares"]
            ],
        },
        "scenarios": [
            {
                "id": item["id"],
                "label": item["label"],
                "source_scenario": item["source_scenario"],
                "planning_year": item["planning_year"],
                "energy_scale": item["energy_scale"],
                "area_demand_scenario": item["area_demand_scenario"],
            }
            for item in section["planning_scenarios"]
        ],
    }


def materialize_scenario_manifest(
    section: Mapping[str, Any],
    *,
    region_id: str,
    energy_asset: ResolvedScenarioAsset,
    area_demand_asset: ResolvedScenarioAsset,
) -> ScenarioCompilation:
    """Materialize one scenario form section without publishing the region.

    The output records technical compiler evidence but deliberately remains
    ``not_validated``. Source trust (including ``provisional_fallback``) is a
    separate dimension and is copied exactly, never promoted by compilation.
    """

    raw = _mapping(section, "scenario form section")
    if raw.get("state") != "declared":
        raise ValueError("Scenario form section is not declared")
    adapter = _mapping(raw.get("adapter"), "scenario adapter declaration")
    adapter_id = str(adapter.get("id") or "")
    if adapter_id not in {
        SCENARIO_ADAPTER_NORMALIZED_JSON,
        SCENARIO_ADAPTER_TIMES_AREA_DEMAND,
    }:
        raise NotImplementedError(f"Unsupported scenario adapter: {adapter_id}")
    assets = _mapping(raw.get("assets"), "scenario assets")
    energy_declaration = _mapping(assets.get("energy_model"), "scenario energy asset")
    area_declaration = _mapping(assets.get("area_demand"), "scenario area asset")
    _validate_asset_binding(
        energy_declaration,
        energy_asset,
        role="energy_model",
    )
    _validate_asset_binding(
        area_declaration,
        area_demand_asset,
        role="area_demand",
    )
    if str(energy_declaration.get("provider")) != str(
        area_declaration.get("provider")
    ):
        raise ValueError("Scenario source assets must use one declared provider")
    provider = str(energy_declaration["provider"])
    if str(raw.get("provider")) != provider:
        raise ValueError("Scenario section provider must match both source assets")

    status = str(raw.get("status") or "")
    regional_acceptance = raw.get("regional_acceptance")
    allowed_use = str(raw.get("allowed_use") or "")
    if status == "accepted_regional":
        if regional_acceptance is not True or allowed_use != "regional_planning":
            raise ValueError(
                "Accepted scenario data requires regional acceptance and "
                "regional_planning use"
            )
        if str(raw.get("source_region_id") or "") != region_id:
            raise ValueError(
                "Accepted scenario evidence must belong to the package region"
            )
    elif status == "provisional_fallback":
        if (
            regional_acceptance is not False
            or allowed_use != "planning_exploration_only"
        ):
            raise ValueError(
                "Provisional scenario data cannot claim regional acceptance"
            )
    else:
        raise ValueError(f"Unsupported scenario data status: {status}")

    source_contract = {
        "schema_version": "1.0",
        "status": status,
        "intended_region_id": region_id,
        "source_region_id": raw["source_region_id"],
        "source_dataset_id": raw["source_dataset_id"],
        "source_label": raw["source_label"],
        "provider": provider,
        "regional_acceptance": regional_acceptance,
        "allowed_use": allowed_use,
        "provenance": raw["provenance"],
        "limitation": raw["limitation"],
        "replacement_condition": raw["replacement_condition"],
        "display_warning": dict(raw["display_warning"]),
        "assets": {
            "energy_model": _asset_payload(energy_asset),
            "area_demand": _asset_payload(area_demand_asset),
        },
    }
    technology_ids = list(adapter["technology_ids"])
    planning = _planning_payload(raw)
    if adapter_id == SCENARIO_ADAPTER_NORMALIZED_JSON:
        if energy_asset.format != "json" or area_demand_asset.format != "json":
            raise ValueError("normalized_json_v1 requires two JSON assets")
        energy_model = {
            "adapter_id": adapter_id,
            "technology_ids": technology_ids,
            "energy_source": {"path": energy_asset.provider_path},
            "area_demand": {"path": area_demand_asset.provider_path},
            "planning": planning,
        }
    else:
        if energy_asset.format != "duckdb" or area_demand_asset.format != "xlsx":
            raise ValueError(
                "times_duckdb_area_demand_xlsx_v1 requires DuckDB and XLSX"
            )
        configuration = _mapping(
            adapter.get("configuration"),
            "TIMES/AreaDemand adapter configuration",
        )
        duckdb_configuration = dict(
            _mapping(configuration.get("duckdb"), "scenario DuckDB configuration")
        )
        area_configuration = dict(
            _mapping(
                configuration.get("area_demand"),
                "scenario AreaDemand configuration",
            )
        )
        duckdb_configuration["path"] = energy_asset.provider_path
        area_configuration["path"] = area_demand_asset.provider_path
        energy_model = {
            "adapter_id": adapter_id,
            "technology_ids": technology_ids,
            "duckdb": duckdb_configuration,
            "area_demand": area_configuration,
            "planning": planning,
        }

    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "region_id": region_id,
        "scenario_set_id": raw["scenario_set_id"],
        "status": status,
        "materialization_status": SCENARIO_COMPILED_STATUS,
        "scenario_levels": list(raw["scenario_levels"]),
        "layers": [],
        "source_contract": source_contract,
        "energy_model": energy_model,
    }
    contract = scenario_contract(manifest)
    if tuple(technology_ids) != contract.technology_ids:
        raise ValueError(
            "Scenario adapter technology_ids differ from the executable contract"
        )
    result_signatures: list[dict[str, Any]] = []
    observation_count: int | None = None
    factor_count: int | None = None
    if adapter_id == SCENARIO_ADAPTER_NORMALIZED_JSON:
        snapshot = load_normalized_scenario_snapshot_from_paths(
            contract,
            energy_path=Path(energy_asset.path),
            area_demand_path=Path(area_demand_asset.path),
        )
        observation_count = len(snapshot.energy_observations)
        factor_count = len(snapshot.area_factors)
        for planning_level in contract.planning_levels:
            request = build_scenario_request_from_contract(
                contract,
                access_scope=f"review:{region_id}",
                scenario_id=planning_level.scenario_id,
            )
            result = run_scenario_request(contract, request, snapshot)
            result_signatures.append(
                {
                    "scenario_id": planning_level.scenario_id,
                    "result_sha256": _canonical_sha256(result.as_dict()),
                    "total_energy_twh": result.total_energy_twh,
                    "total_area_need_km2": result.total_area_need_km2,
                }
            )

    evidence = {
        "schema_version": "1.0",
        "compiler_id": "speedlocal_scenario_compiler",
        "compiler_version": SCENARIO_COMPILER_VERSION,
        "materialization_status": SCENARIO_COMPILED_STATUS,
        "region_id": region_id,
        "capability_id": "workspace.scenario",
        "scenario_set_id": contract.scenario_set_id,
        "adapter_id": contract.adapter_id,
        "data_status": contract.source.status,
        "regional_acceptance": contract.source.regional_acceptance,
        "allowed_use": contract.source.allowed_use,
        "contract_signature_sha256": scenario_contract_signature(contract),
        "technology_ids": list(contract.technology_ids),
        "planning_scenario_ids": [
            item.scenario_id for item in contract.planning_levels
        ],
        "area_demand_option_ids": [
            item.scenario_id for item in contract.area_demand_options
        ],
        "default_area_demand_scenario": (
            contract.default_area_demand_scenario
        ),
        "technology_share_step_pct": contract.technology_share_step_pct,
        "default_technology_shares": [
            item.as_dict() for item in contract.default_technology_shares
        ],
        "energy_observation_count": observation_count,
        "area_factor_count": factor_count,
        "assets": {
            "energy_model": {
                "bytes": int(energy_asset.bytes),
                **_asset_payload(energy_asset),
            },
            "area_demand": {
                "bytes": int(area_demand_asset.bytes),
                **_asset_payload(area_demand_asset),
            },
        },
        "scenario_results": result_signatures,
        "landing_card_enabled": False,
    }
    manifest["generated_evidence"] = evidence
    # Reparse with evidence present to prove that no evidence value can alter
    # the executable contract or its source-trust classification.
    reparsed = scenario_contract(manifest)
    if scenario_contract_signature(reparsed) != evidence["contract_signature_sha256"]:
        raise ValueError("Scenario generated evidence changed the contract")
    return ScenarioCompilation(
        manifest=manifest,
        evidence=evidence,
        readiness_state="not_validated",
        readiness_detail=(
            "Scenariomanifest, källintegritet och generisk request/result-kedja "
            "är materialiserade; den fristående tekniska och regionala gaten "
            "återstår."
        ),
    )


__all__ = [
    "SCENARIO_COMPILED_STATUS",
    "SCENARIO_COMPILER_VERSION",
    "ScenarioCompilation",
    "materialize_scenario_manifest",
]
