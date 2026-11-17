from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .social_acceptance import (
    ResolvedSocialAcceptanceAsset,
    SOCIAL_ACCEPTANCE_COMPILED_STATUS,
    build_social_acceptance_request_from_contract,
    load_social_acceptance_snapshot_from_paths,
    run_social_acceptance_request,
    social_acceptance_contract,
    social_acceptance_contract_signature,
)


SOCIAL_ACCEPTANCE_COMPILER_VERSION = "1.0"


@dataclass(frozen=True)
class SocialAcceptanceCompilation:
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


def _asset_payload(asset: ResolvedSocialAcceptanceAsset) -> dict[str, Any]:
    return {
        "path": str(asset.provider_path),
        "sha256": str(asset.sha256),
    }


def _validate_asset_binding(
    declaration: Mapping[str, Any],
    resolved: ResolvedSocialAcceptanceAsset,
    *,
    role: str,
    expected_format: str,
) -> None:
    if (
        str(declaration.get("provider") or "") != str(resolved.provider)
        or str(declaration.get("path") or "") != str(resolved.provider_path)
        or str(declaration.get("format") or "") != str(resolved.format)
        or str(resolved.format) != expected_format
    ):
        raise ValueError(
            f"Social-acceptance {role} asset drifted after resolution"
        )
    if not Path(resolved.path).is_file():
        raise FileNotFoundError(resolved.path)
    if _sha256_path(Path(resolved.path)) != str(resolved.sha256):
        raise ValueError(
            f"Social-acceptance {role} checksum drifted after resolution"
        )


def materialize_social_acceptance_manifest(
    section: Mapping[str, Any],
    *,
    region_id: str,
    acceptance_values_asset: ResolvedSocialAcceptanceAsset,
    display_geometry_asset: ResolvedSocialAcceptanceAsset,
) -> SocialAcceptanceCompilation:
    """Compile one form section without publishing or upgrading data trust."""

    raw = _mapping(section, "social-acceptance form section")
    if raw.get("state") != "declared":
        raise ValueError("Social-acceptance form section is not declared")
    assets = _mapping(raw.get("assets"), "social-acceptance assets")
    values_declaration = _mapping(
        assets.get("acceptance_values"),
        "social-acceptance values asset",
    )
    geometry_declaration = _mapping(
        assets.get("display_geometry"),
        "social-acceptance display asset",
    )
    _validate_asset_binding(
        values_declaration,
        acceptance_values_asset,
        role="acceptance_values",
        expected_format="csv",
    )
    _validate_asset_binding(
        geometry_declaration,
        display_geometry_asset,
        role="display_geometry",
        expected_format="geojson",
    )
    providers = {
        str(values_declaration.get("provider") or ""),
        str(geometry_declaration.get("provider") or ""),
        str(raw.get("provider") or ""),
    }
    if len(providers) != 1 or "" in providers:
        raise ValueError(
            "Social-acceptance section and assets must use one provider"
        )
    provider = providers.pop()

    status = str(raw.get("status") or "")
    synthetic = raw.get("synthetic")
    regional_acceptance = raw.get("regional_acceptance")
    allowed_use = str(raw.get("allowed_use") or "")
    if not isinstance(synthetic, bool) or not isinstance(
        regional_acceptance,
        bool,
    ):
        raise ValueError(
            "Social-acceptance trust flags must be explicit booleans"
        )
    if status == "accepted_regional":
        if (
            synthetic
            or not regional_acceptance
            or allowed_use != "regional_planning"
            or str(raw.get("source_region_id") or "") != region_id
        ):
            raise ValueError(
                "Accepted social acceptance requires observed data owned and "
                "accepted by the package region"
            )
    elif status == "provisional_fallback":
        if regional_acceptance or allowed_use != "behavior_exploration_only":
            raise ValueError(
                "Provisional social acceptance cannot claim regional acceptance"
            )
    else:
        raise ValueError(f"Unsupported social-acceptance status: {status}")

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
        "synthetic": synthetic,
        "method_id": raw["method_id"],
        "provenance": raw["provenance"],
        "limitation": raw["limitation"],
        "replacement_condition": raw["replacement_condition"],
        "display_warning": dict(raw["display_warning"]),
        "assets": {
            "acceptance_values": _asset_payload(acceptance_values_asset),
            "display_geometry": _asset_payload(display_geometry_asset),
        },
    }
    coverage = _mapping(raw.get("coverage"), "social-acceptance coverage")
    behavior = _mapping(raw.get("behavior"), "social-acceptance behavior")
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "acceptance_id": raw["acceptance_id"],
        "display_name": raw["display_name"],
        "region_id": region_id,
        "status": status,
        "materialization_status": SOCIAL_ACCEPTANCE_COMPILED_STATUS,
        "synthetic": synthetic,
        "scenario_levels": list(raw["scenario_levels"]),
        "default_scenario": raw["default_scenario"],
        "source_contract": source_contract,
        "coverage_contract": {
            "scope": coverage["scope"],
            "source_hex_count": coverage["source_hex_count"],
            "target_support_hex_count": coverage["target_support_hex_count"],
            "unassessed_support_hex_count": coverage[
                "unassessed_support_hex_count"
            ],
        },
        "behavior_contract": {
            "impact_model": behavior["impact_model"],
            "allocation_priority_model": behavior[
                "allocation_priority_model"
            ],
            "low_threshold": behavior["low_threshold"],
            "high_threshold": behavior["high_threshold"],
            "missing_context_policy": behavior["missing_context_policy"],
            "allocation_missing_context_policy": behavior[
                "allocation_missing_context_policy"
            ],
        },
        "hex_resolution": raw["hex_resolution"],
        "rollup_resolutions": list(raw["rollup_resolutions"]),
        "rollup_rule": raw["rollup_rule"],
        "control_contract": dict(raw["control_contract"]),
        "source_hex_geojson": display_geometry_asset.provider_path,
        "hex_geometry_path": display_geometry_asset.provider_path,
        "acceptance_csv": acceptance_values_asset.provider_path,
        "random_seed": raw.get("random_seed"),
        "scenarios": [dict(item) for item in raw["scenarios"]],
        "value_range": list(raw["value_range"]),
        "max_decimals": raw["max_decimals"],
        "method_note": raw["method_note"],
    }
    if manifest["random_seed"] is None:
        manifest.pop("random_seed")
    contract = social_acceptance_contract(manifest)
    snapshot = load_social_acceptance_snapshot_from_paths(
        contract,
        values_path=Path(acceptance_values_asset.path),
        display_geometry_path=Path(display_geometry_asset.path),
    )
    scenario_results: list[dict[str, Any]] = []
    for scenario in contract.scenarios:
        request = build_social_acceptance_request_from_contract(
            contract,
            access_scope=f"review:{region_id}",
            layer_visible=False,
            scenario_id=scenario.scenario_id,
        )
        result = run_social_acceptance_request(contract, request, snapshot)
        scenario_results.append(
            {
                "scenario_id": scenario.scenario_id,
                "layer_visible": request.layer_visible,
                "result_sha256": _canonical_sha256(result.as_dict()),
                "minimum": result.minimum_acceptance,
                "maximum": result.maximum_acceptance,
                "mean": result.mean_acceptance,
                "median": result.median_acceptance,
            }
        )
    evidence = {
        "schema_version": "1.0",
        "compiler_id": "speedlocal_social_acceptance_compiler",
        "compiler_version": SOCIAL_ACCEPTANCE_COMPILER_VERSION,
        "materialization_status": SOCIAL_ACCEPTANCE_COMPILED_STATUS,
        "region_id": region_id,
        "capability_id": "workspace.social_acceptance",
        "acceptance_id": contract.acceptance_id,
        "data_status": contract.source.status,
        "synthetic": contract.source.synthetic,
        "regional_acceptance": contract.source.regional_acceptance,
        "allowed_use": contract.source.allowed_use,
        "behavior": {
            "impact_model": contract.source.behavior.impact_model,
            "allocation_priority_model": (
                contract.source.behavior.allocation_priority_model
            ),
            "low_threshold": contract.source.behavior.low_threshold,
            "high_threshold": contract.source.behavior.high_threshold,
            "missing_context_policy": (
                contract.source.behavior.missing_context_policy
            ),
            "allocation_missing_context_policy": (
                contract.source.behavior.allocation_missing_context_policy
            ),
            "method_note": contract.method_note,
        },
        "contract_signature_sha256": social_acceptance_contract_signature(
            contract
        ),
        "source_hex_count": len(snapshot.observations),
        "target_support_hex_count": (
            contract.source.coverage.target_support_hex_count
        ),
        "unassessed_support_hex_count": (
            contract.source.coverage.unassessed_support_hex_count
        ),
        "assets": {
            "acceptance_values": {
                "bytes": int(acceptance_values_asset.bytes),
                "format": str(acceptance_values_asset.format),
                **_asset_payload(acceptance_values_asset),
            },
            "display_geometry": {
                "bytes": int(display_geometry_asset.bytes),
                "format": str(display_geometry_asset.format),
                **_asset_payload(display_geometry_asset),
            },
        },
        "scenario_results": scenario_results,
        "landing_card_enabled": False,
    }
    manifest["generated_evidence"] = evidence
    reparsed = social_acceptance_contract(manifest)
    if social_acceptance_contract_signature(reparsed) != evidence[
        "contract_signature_sha256"
    ]:
        raise ValueError(
            "Social-acceptance generated evidence changed the contract"
        )
    return SocialAcceptanceCompilation(
        manifest=manifest,
        evidence=evidence,
        readiness_state="not_validated",
        readiness_detail=(
            "Social-acceptansmanifest, källintegritet och generisk "
            "request/result-kedja är materialiserade; fristående teknisk och "
            "regional validering återstår."
        ),
    )


__all__ = [
    "SOCIAL_ACCEPTANCE_COMPILER_VERSION",
    "SocialAcceptanceCompilation",
    "materialize_social_acceptance_manifest",
]
