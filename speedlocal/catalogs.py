from __future__ import annotations

import json
import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

from .contracts import (
    AnalysisContract,
    RegionGeographyContract,
    analysis_contract,
    canonical_contract_evidence,
    source_contract,
    region_geography_contract,
)
from .paths import repo_root
from .scenarios import scenario_source_contract
from .social_acceptance import social_acceptance_contract


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_region(region_id: str) -> dict[str, Any]:
    index = _read_json(repo_root() / "regions" / "index.json")
    indexed = [str(item) for item in index.get("regions") or []]
    if region_id not in indexed:
        raise KeyError(f"Region is not in the public catalog: {region_id}")
    region = _read_json(repo_root() / "regions" / region_id / "region.json")
    if str(region.get("region_id")) != region_id:
        raise ValueError(f"Region manifest id mismatch: {region_id}")
    return region


def list_regions() -> list[dict[str, Any]]:
    index = _read_json(repo_root() / "regions" / "index.json")
    return [load_region(str(region_id)) for region_id in index.get("regions") or []]


def load_region_geography(region_id: str) -> RegionGeographyContract:
    from .validation import validate_region_geography_contract

    region = load_region(region_id)
    manifest_rel = region.get("geography_manifest")
    if not isinstance(manifest_rel, str) or not manifest_rel.strip():
        raise KeyError(f"Region geography is not configured for {region_id}")
    path = (repo_root() / manifest_rel).resolve()
    root = repo_root().resolve()
    if path == root or root not in path.parents:
        raise ValueError(f"Region geography manifest escapes repository: {manifest_rel}")
    contract = region_geography_contract(_read_json(path))
    if contract.region_id != region_id:
        raise ValueError(f"Region geography manifest identity mismatch: {path}")
    if contract.native_crs != str(region.get("native_crs") or ""):
        raise ValueError(
            f"Region geography native CRS does not match region manifest: {path}"
        )
    validate_region_geography_contract(contract)
    return contract


def load_scenario_manifest(region_id: str) -> dict[str, Any]:
    region = load_region(region_id)
    manifest_rel = region.get("scenario_manifest")
    if not isinstance(manifest_rel, str) or not manifest_rel.strip():
        raise KeyError(f"Scenario manifest is not configured for {region_id}")
    root = repo_root().resolve()
    path = (root / manifest_rel).resolve()
    if path == root or root not in path.parents:
        raise ValueError(f"Scenario manifest escapes repository: {manifest_rel}")
    if not path.is_file():
        raise FileNotFoundError(f"Scenario manifest does not exist: {path}")
    manifest = _read_json(path)
    contract = scenario_source_contract(manifest)
    if contract.intended_region_id != region_id:
        raise ValueError(f"Scenario manifest identity mismatch: {path}")
    result = dict(manifest)
    result["_manifest_path"] = str(path)
    return result


def load_social_acceptance_manifest(region_id: str) -> dict[str, Any]:
    region = load_region(region_id)
    manifest_rel = region.get("social_acceptance_manifest")
    if not isinstance(manifest_rel, str) or not manifest_rel.strip():
        raise KeyError(
            f"Social-acceptance manifest is not configured for {region_id}"
        )
    root = repo_root().resolve()
    path = (root / manifest_rel).resolve()
    if path == root or root not in path.parents:
        raise ValueError(
            f"Social-acceptance manifest escapes repository: {manifest_rel}"
        )
    if not path.is_file():
        raise FileNotFoundError(
            f"Social-acceptance manifest does not exist: {path}"
        )
    manifest = _read_json(path)
    contract = social_acceptance_contract(manifest)
    if contract.region_id != region_id:
        raise ValueError(
            f"Social-acceptance manifest identity mismatch: {path}"
        )
    result = dict(manifest)
    result["_manifest_path"] = str(path)
    return result


def _load_analysis_raw(path: Path, seen: tuple[Path, ...] = ()) -> dict[str, Any]:
    resolved = path.resolve()
    root = repo_root().resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"Analysis manifest escapes repository: {path}")
    if resolved in seen:
        chain = " -> ".join(item.as_posix() for item in (*seen, resolved))
        raise ValueError(f"Analysis manifest inheritance cycle: {chain}")
    raw = _read_json(resolved)
    base_rel = raw.get("extends")
    if base_rel is None:
        return raw
    if not isinstance(base_rel, str) or not base_rel.strip():
        raise ValueError("Analysis manifest extends must be a repository path")
    base_path = (root / base_rel).resolve()
    base = _load_analysis_raw(base_path, (*seen, resolved))
    merged = dict(base)
    merged.update({key: value for key, value in raw.items() if key != "extends"})
    return merged


def source_storage_evidence_sha256(source) -> str:
    encoded = json.dumps(
        canonical_contract_evidence(source), sort_keys=True,
        separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_analysis_runtime_overlay(raw: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Replace only explicitly scoped source storage, retaining all semantics."""
    if not isinstance(overlay, dict) or set(overlay) != {"schema_version", "region_id", "selection_sha256", "group_ids", "sources"}:
        raise ValueError("Analysis runtime binding must contain exactly its declared fields")
    if overlay["schema_version"] != "1.0" or overlay["region_id"] != raw.get("region_id"):
        raise ValueError("Analysis runtime binding identity mismatch")
    groups = overlay["group_ids"]
    bindings = overlay["sources"]
    if not isinstance(groups, list) or not groups or any(not isinstance(item, str) or not item for item in groups) or len(groups) != len(set(groups)):
        raise ValueError("Analysis runtime groups must be nonempty and unique")
    if not isinstance(bindings, dict):
        raise ValueError("Analysis runtime source bindings must be an object")
    required = {item["id"] for item in raw.get("layers", ()) if item["group_id"] in groups}
    if not required or set(bindings) != required:
        raise ValueError("Analysis runtime bindings must cover exactly every source in their declared groups")
    layers = []
    for layer in raw["layers"]:
        if layer["id"] not in required:
            layers.append(layer)
            continue
        entry = bindings[layer["id"]]
        if not isinstance(entry, dict) or set(entry) != {"replaced_source_contract_sha256", "postgis_reference", "distance_coverage"}:
            raise ValueError("Source runtime binding has unsupported fields")
        original = source_contract(layer["source"])
        if original.postgis_reference is not None or source_storage_evidence_sha256(original) != entry["replaced_source_contract_sha256"]:
            raise ValueError("Source runtime binding does not match its original source contract")
        reference = entry["postgis_reference"]
        replacement = {key: value for key, value in layer["source"].items() if key not in {
            "provider", "asset_manifest", "diagnostic_source_snapshot",
            "distance_provider", "distance_path", "distance_h3_resolution", "distance_coverage",
        }}
        replacement.update(postgis_reference=reference,
            distance_h3_resolution=reference.get("resolution") if isinstance(reference, dict) else None,
            distance_coverage=entry["distance_coverage"],
            requires_explicit_parameters=(original.requires_explicit_parameters or original.diagnostic_source_snapshot is not None))
        parsed = source_contract(replacement)
        if parsed.postgis_reference.region_id != raw["region_id"]:
            raise ValueError("Source runtime binding belongs to another region")
        layers.append({**layer, "source": replacement})
    return {**raw, "layers": layers}


def validate_analysis_runtime_selection(overlay, region_id: str, *, repository_root: Path | None = None) -> None:
    """Bind generated storage choices to current human source selection."""
    from .region_profile import load_region_profile
    from .source_catalog import load_delivery_source_selection
    root = repo_root() if repository_root is None else repository_root
    selection = load_delivery_source_selection(root, region_id)
    profile = load_region_profile(root, region_id)
    if not isinstance(overlay, dict) or overlay.get("region_id") != region_id or overlay.get("selection_sha256") != selection.selection_sha256:
        raise ValueError("Analysis runtime binding is stale against delivery source selection")
    selected_ids = {source.id for group in selection.groups if group.id in overlay.get("group_ids", ()) for source in group.sources}
    if set(overlay.get("sources", {})) != selected_ids:
        raise ValueError("Analysis runtime binding does not cover its selected sources")
    for entry in overlay["sources"].values():
        reference = entry.get("postgis_reference", {})
        if reference.get("connection_alias") != profile.connection or reference.get("database_schema") != profile.database_schema:
            raise ValueError("Analysis runtime connection differs from the region profile")


def load_analysis_manifest(region_id: str, analysis_id: str, *, use_runtime_bindings: bool = True) -> dict[str, Any]:
    """Load one repo-owned analysis manifest without resolving runtime data."""

    region = load_region(region_id)
    manifest_rel = (region.get("analysis_manifests") or {}).get(analysis_id)
    if not manifest_rel:
        raise KeyError(f"Analysis {analysis_id} is not configured for {region_id}")
    path = (repo_root() / str(manifest_rel)).resolve()
    if repo_root().resolve() not in path.parents:
        raise ValueError(f"Analysis manifest escapes repository: {manifest_rel}")
    raw = _load_analysis_raw(path)
    if (
        str(raw.get("region_id") or "") != region_id
        or str(raw.get("analysis_id") or "") != analysis_id
    ):
        raise ValueError(f"Analysis manifest identity mismatch: {path}")
    result = dict(raw)
    overlay_path = region.get("analysis_runtime_manifest")
    if use_runtime_bindings and overlay_path is not None:
        expected = f"regions/{region_id}/analysis-runtime.json"
        if overlay_path != expected:
            raise ValueError("Analysis runtime binding must use the canonical regional path")
        overlay = _read_json(repo_root() / expected)
        validate_analysis_runtime_selection(overlay, region_id)
        result = apply_analysis_runtime_overlay(result, overlay)
    result["_manifest_path"] = str(path)
    return result


def load_analysis(region_id: str, analysis_id: str, *, use_runtime_bindings: bool = True) -> AnalysisContract:
    raw = load_analysis_manifest(region_id, analysis_id, use_runtime_bindings=use_runtime_bindings)
    domain_reference = raw.get("analysis_domain_reference")
    contract = analysis_contract(raw)
    if domain_reference is not None:
        if not isinstance(domain_reference, dict):
            raise ValueError("Analysis domain reference must be an object")
        if set(domain_reference) != {"type", "domain_id"}:
            raise ValueError(
                "Analysis domain reference must contain only type and domain_id"
            )
        if domain_reference.get("type") != "region_geography":
            raise ValueError("Unsupported analysis domain reference type")
        if raw.get("analysis_domain") is not None:
            raise ValueError(
                "Analysis may not declare both analysis_domain and "
                "analysis_domain_reference"
            )
        domain_id = str(domain_reference.get("domain_id") or "").strip()
        if not domain_id:
            raise ValueError("Analysis domain reference id is required")
        geography = load_region_geography(region_id)
        region_domain = geography.analysis_domains.get(domain_id)
        if region_domain is None:
            raise KeyError(
                f"Region analysis domain {domain_id!r} is not configured for "
                f"{region_id}"
            )
        if (
            region_domain.purpose != "standard_group_analysis"
            or region_domain.missing_observation_policy != "error"
        ):
            raise ValueError(
                "A standard analysis must reference a standard_group_analysis "
                "domain with fail-closed observations"
            )
        contract = replace(contract, analysis_domain=region_domain.artifacts)
    if contract.region_id != region_id or contract.id != analysis_id:
        raise ValueError(
            f"Analysis manifest identity mismatch: {raw.get('_manifest_path')}"
        )
    return contract
