from __future__ import annotations

from typing import Any

from speedlocal.catalogs import (
    load_analysis,
    load_region as load_delivery_region,
    load_scenario_manifest as load_delivery_scenario_manifest,
    load_social_acceptance_manifest as load_delivery_social_acceptance_manifest,
)
from speedlocal.landscape import load_landscape_contract
from speedlocal.paths import repo_root as speedlocal_repo_root

from .manifests import (
    LEGACY_NUMERICAL_LANDSCAPE_CONTEXT_KEY,
    load_linked_manifest,
    read_manifest,
    resolve_repo_path,
)


def repo_path_exists(path_value: object) -> tuple[str, bool]:
    path = resolve_repo_path(str(path_value)) if path_value else None
    return (str(path) if path is not None else "", bool(path and path.exists()))


def read_optional_manifest(path_value: object) -> dict[str, Any] | None:
    path = resolve_repo_path(str(path_value)) if path_value else None
    if path is None or not path.exists():
        return None
    return read_manifest(str(path)).copy()


def _canonical_landscape_manifest(
    region_id: str,
    delivery_region: dict[str, Any],
) -> dict[str, Any] | None:
    """Read the repo-owned typed workspace.landscape declaration."""

    path_value = delivery_region.get("landscape_manifest")
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    root = speedlocal_repo_root().resolve()
    path = (root / path_value).resolve()
    if path == root or root not in path.parents or not path.is_file():
        return None
    # Validate typed identity, trust ceiling and exact domain binding before
    # handing raw presentation metadata to the remaining monolith adapter.
    contract = load_landscape_contract(region_id)
    manifest = read_manifest(str(path)).copy()
    if (
        contract.region_id != region_id
        or str(manifest.get("region_id") or "").strip().lower() != region_id
    ):
        raise ValueError("Canonical landscape manifest identity mismatch")
    manifest["_manifest_path"] = str(path)
    manifest["_authority"] = "repo_delivery"
    return manifest


def status_row(label: str, path_value: object) -> dict[str, Any]:
    path, exists = repo_path_exists(path_value)
    return {
        "del": label,
        "status": "klar" if exists else "saknas",
        "path": path or str(path_value or ""),
    }


def available_h3_resolutions(region: dict[str, Any]) -> list[int]:
    values: list[int] = []
    for value in region.get("available_h3_resolutions", []) or []:
        try:
            values.append(int(value))
        except Exception:
            continue
    if values:
        return sorted(set(values), reverse=True)
    try:
        default_resolution = int(region.get("default_h3_resolution") or 9)
    except Exception:
        default_resolution = 9
    return [default_resolution]


def runtime_blockers(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any] | None,
    legacy_numerical_landscape_manifest: dict[str, Any] | None,
    potential_manifest: dict[str, Any] | None,
    scenario_manifest: dict[str, Any] | None,
    social_acceptance_manifest: dict[str, Any] | None,
    solar_rules: dict[str, Any] | None,
    *,
    wind_rules: dict[str, Any] | None = None,
    context_inputs: Any = None,
    domain_display_payload: Any = None,
    runtime_error: str | None = None,
) -> list[dict[str, str]]:
    blockers: list[dict[str, str]] = []

    for key, label, value, required in (
        ("landscape_manifest", "Kanoniskt landskapskontrakt", landscape_manifest, False),
        ("legacy_landscape_display_manifest", "Landskapets visningsmetadata", legacy_numerical_landscape_manifest, False),
        ("potential_manifest", "Potentialregler", potential_manifest, True),
        ("solar_rules_manifest", "Solregler", solar_rules, True),
        ("wind_rules_manifest", "Vindregler", wind_rules, False),
        ("scenario_manifest", "Energimodell", scenario_manifest, True),
        ("social_acceptance_manifest", "Social acceptans", social_acceptance_manifest, True),
    ):
        if (required or key in region) and not isinstance(value, dict):
            blockers.append({"del": label, "typ": "manifest", "path": str(region.get(key) or "")})
    if runtime_error or context_inputs is None or domain_display_payload is None:
        blockers.append({"del": "Deklarerade databasindata", "typ": "data",
            "path": runtime_error or "Aktuella kontrakt, indata och visningsdomän är inte verifierade."})
    return blockers


def load_region_context(region: dict[str, Any]) -> dict[str, Any]:
    region_id = str(region.get("region_id") or "").strip()
    try:
        delivery_region = load_delivery_region(region_id)
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        delivery_region = {}

    def metadata(key: str) -> dict[str, Any] | None:
        try:
            return load_linked_manifest(delivery_region, key)
        except (FileNotFoundError, OSError, TypeError, ValueError):
            return None

    potential_manifest = metadata("potential_manifest")
    # Explicit top-level refs also bind every consumed rule to runtime_snapshot.
    # Historical nested rule paths in the byte-exact copies are provenance only.
    solar_rules = metadata("solar_rules_manifest")
    wind_rules = metadata("wind_rules_manifest")
    try:
        landscape_manifest = _canonical_landscape_manifest(
            region_id,
            delivery_region,
        )
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError):
        landscape_manifest = None
    legacy_numerical_landscape_manifest = metadata("legacy_landscape_display_manifest")
    if legacy_numerical_landscape_manifest is not None:
        if legacy_numerical_landscape_manifest.get("region_id") != region_id:
            legacy_numerical_landscape_manifest = None
        else:
            legacy_numerical_landscape_manifest["_compatibility_role"] = "legacy_numerical_only"
            legacy_numerical_landscape_manifest["_source_provider"] = "repo"
    try:
        scenario_manifest = (
            load_delivery_scenario_manifest(region_id)
            if delivery_region.get("scenario_manifest")
            else None
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        scenario_manifest = None
    try:
        social_acceptance_manifest = (
            load_delivery_social_acceptance_manifest(region_id)
            if delivery_region.get("social_acceptance_manifest")
            else None
        )
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        social_acceptance_manifest = None
    context_inputs, domain_display_payload, runtime_error = None, None, None
    try:
        from speedlocal.context_runtime import (
            catalog_context_runtime_declared, load_catalog_context_inputs,
        )
        from speedlocal.sources import read_analysis_domain_input

        if not catalog_context_runtime_declared(region_id):
            raise ValueError("Regionen deklarerar inget context_runtime_manifest.")
        try:
            context_inputs = load_catalog_context_inputs(region_id)
        except RuntimeError as exc:
            # The strict SQL reader deliberately wraps only psycopg errors.
            # Other runtime errors must remain visible as programming faults.
            if str(exc) != "PostGIS regional context read failed":
                raise
            raise ValueError("Regional database inputs are unavailable") from None
        if context_inputs.inputs.scope.region_id != region_id:
            raise ValueError("Databasindata tillhör en annan region.")
        if any(getattr(context_inputs, key) is None for key in (
            "scenario", "social_acceptance", "technology_context",
        )):
            raise ValueError("Obligatoriska kontextindata saknas.")
        if "landscape_manifest" in delivery_region and context_inputs.landscape is None:
            raise ValueError("Deklarerade landskapsindata saknas.")
        if "combined_result_manifest" in delivery_region and context_inputs.combined_policy is None:
            raise ValueError("Deklarerad kombinerad policy saknas.")
        resolution = delivery_region.get("default_h3_resolution")
        if isinstance(resolution, bool) or not isinstance(resolution, int):
            raise ValueError("Regionen kräver en explicit H3 standardupplösning.")
        domain_display_payload = read_analysis_domain_input(
            load_analysis(region_id, "wind"), "standard_analysis", resolution,
            geometry_use="display",
        )
        if (domain_display_payload.region_id, domain_display_payload.role,
                domain_display_payload.resolution) != (region_id, "standard_analysis", resolution):
            raise ValueError("Visningsdomänen tillhör ett annat regionalt kontrakt.")
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError, NotImplementedError) as exc:
        runtime_error = str(exc)
        context_inputs, domain_display_payload = None, None
    if legacy_numerical_landscape_manifest is not None and context_inputs is not None:
        legacy_numerical_landscape_manifest["_context_runtime_revision_sha256"] = (
            context_inputs.inputs.binding().revision_sha256
        )
    missing = runtime_blockers(
        delivery_region,
        landscape_manifest,
        legacy_numerical_landscape_manifest,
        potential_manifest,
        scenario_manifest,
        social_acceptance_manifest,
        solar_rules,
        wind_rules=wind_rules,
        context_inputs=context_inputs,
        domain_display_payload=domain_display_payload,
        runtime_error=runtime_error,
    )
    return {
        "landscape_manifest": landscape_manifest,
        LEGACY_NUMERICAL_LANDSCAPE_CONTEXT_KEY: (
            legacy_numerical_landscape_manifest
        ),
        "potential_manifest": potential_manifest,
        "scenario_manifest": scenario_manifest,
        "social_acceptance_manifest": social_acceptance_manifest,
        "solar_rules": solar_rules,
        "wind_rules": wind_rules,
        "context_inputs": context_inputs,
        "domain_display_payload": domain_display_payload,
        "missing_data": missing,
        "runtime_ready": not missing,
    }


def region_data_status_rows(region: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    """Report consumed repo metadata and verified DB inputs, without file probes."""
    rows: list[dict[str, Any]] = []
    for key, label in [
        ("landscape_manifest", "Landskapsanalys"),
        ("potential_manifest", "Potential"),
        ("scenario_manifest", "Scenarier/energimodell"),
        ("social_acceptance_manifest", "Social acceptans"),
        ("solar_rules", "Solregler"),
        ("wind_rules", "Vindregler"),
    ]:
        value = context.get(key)
        reference_key = f"{key}_manifest" if key in {"solar_rules", "wind_rules"} else key
        rows.append({"del": label, "status": "klar" if isinstance(value, dict) else (
            "ej deklarerad" if reference_key not in region else "saknas"),
            "path": str(value.get("_manifest_path") or region.get(reference_key) or "") if isinstance(value, dict) else str(region.get(reference_key) or "")})
    inputs = context.get("context_inputs")
    display = context.get("domain_display_payload")
    rows.append({"del": "Regionala databasindata", "status": "klar" if inputs is not None and not any(
        row.get("del") == "Deklarerade databasindata" for row in context.get("missing_data", [])) else "saknas",
        "path": str(region.get("context_runtime_manifest") or "")})
    if display is not None:
        rows.append({"del": f"H3 R{display.resolution}", "status": "klar",
            "path": f"PostGIS {display.domain_id} · {display.runtime_revision_sha256[:12]}"})
    return rows
