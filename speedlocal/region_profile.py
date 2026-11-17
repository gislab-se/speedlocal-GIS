from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator


STANDARD_LANDSCAPE_GROUPS = (
    "roads",
    "nature",
    "culture",
    "population",
    "grid_infrastructure",
)
DELIVERY_REGION_IDS = ("bornholm", "skaraborg", "trondelag")


@dataclass(frozen=True)
class RegionProfile:
    region_id: str
    name: str
    country_code: str
    connection: str
    database_schema: str
    boundary_view: str
    analysis_surface_view: str
    landscape_views: Mapping[str, tuple[str, ...]]
    energy_source_id: str
    energy_evidence: str
    social_source_id: str
    social_evidence: str
    extra_landscape_groups: tuple[Mapping[str, Any], ...]
    contracts: Mapping[str, str]


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def profile_schema_path(repo_root: Path) -> Path:
    return repo_root / "schemas" / "speedlocal" / "1.0" / "region-profile.schema.json"


def profile_path(repo_root: Path, region_id: str) -> Path:
    if region_id not in DELIVERY_REGION_IDS:
        raise ValueError(f"Region is outside the three-region delivery: {region_id}")
    return repo_root / "regions" / region_id / "region-profile.json"


def validate_profile_payload(
    payload: Mapping[str, Any],
    *,
    schema: Mapping[str, Any],
) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        detail = "; ".join(
            f"/{'/'.join(str(part) for part in error.absolute_path)}: {error.message}"
            for error in errors
        )
        raise ValueError(detail)


def validate_profile_contract_bindings(
    repo_root: Path,
    region_id: str,
    payload: Mapping[str, Any],
) -> None:
    """Bind a concise profile to the canonical region/geography chain."""

    root = repo_root.resolve()
    contracts = payload["contracts"]
    expected_region_path = f"regions/{region_id}/region.json"
    observed_region_path = str(contracts["region"])
    if observed_region_path != expected_region_path:
        raise ValueError(
            f"Profile region contract {observed_region_path!r} must be "
            f"{expected_region_path!r}"
        )

    region_manifest_path = (root / expected_region_path).resolve()
    if (
        not region_manifest_path.is_relative_to(root)
        or not region_manifest_path.is_file()
    ):
        raise ValueError(
            f"Canonical region contract is missing or escapes the repository: "
            f"{expected_region_path}"
        )
    region_manifest = _read_json(region_manifest_path)
    if str(region_manifest.get("region_id") or "") != region_id:
        raise ValueError(
            f"Canonical region contract does not belong to {region_id!r}"
        )

    expected_geography_path = str(
        region_manifest.get("geography_manifest") or ""
    ).strip()
    if not expected_geography_path:
        raise ValueError(
            f"Canonical region contract for {region_id!r} has no geography_manifest"
        )
    observed_geography_path = str(contracts["geography"])
    if observed_geography_path != expected_geography_path:
        raise ValueError(
            f"Profile geography contract {observed_geography_path!r} must match "
            f"region.json geography_manifest {expected_geography_path!r}"
        )

    geography_manifest_path = (root / expected_geography_path).resolve()
    if (
        not geography_manifest_path.is_relative_to(root)
        or not geography_manifest_path.is_file()
    ):
        raise ValueError(
            "Canonical geography contract is missing or escapes the repository: "
            f"{expected_geography_path}"
        )
    geography_manifest = _read_json(geography_manifest_path)
    if str(geography_manifest.get("region_id") or "") != region_id:
        raise ValueError(
            f"Canonical geography contract does not belong to {region_id!r}"
        )


def load_region_profile(repo_root: Path, region_id: str) -> RegionProfile:
    schema = _read_json(profile_schema_path(repo_root))
    payload = _read_json(profile_path(repo_root, region_id))
    validate_profile_payload(payload, schema=schema)

    region = payload["region"]
    database = payload["database"]
    landscape = payload["landscape"]
    energy = payload["energy"]
    social = payload["social_acceptance"]

    if region["id"] != region_id:
        raise ValueError(
            f"Profile id {region['id']!r} does not match directory {region_id!r}"
        )
    if database["schema"] != region_id:
        raise ValueError(
            f"Database schema {database['schema']!r} must match {region_id!r}"
        )
    validate_profile_contract_bindings(repo_root, region_id, payload)
    return RegionProfile(
        region_id=region_id,
        name=str(region["name"]),
        country_code=str(region["country_code"]),
        connection=str(database["connection"]),
        database_schema=str(database["schema"]),
        boundary_view=str(database["boundary_view"]),
        analysis_surface_view=str(database["analysis_surface_view"]),
        landscape_views={
            group_id: tuple(str(view) for view in landscape[group_id])
            for group_id in STANDARD_LANDSCAPE_GROUPS
        },
        energy_source_id=str(energy["source_id"]),
        energy_evidence=str(energy["evidence"]),
        social_source_id=str(social["source_id"]),
        social_evidence=str(social["evidence"]),
        extra_landscape_groups=tuple(payload["extra_landscape_groups"]),
        contracts={str(key): str(value) for key, value in payload["contracts"].items()},
    )
