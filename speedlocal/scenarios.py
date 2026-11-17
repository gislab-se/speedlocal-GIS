from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from statistics import median
from typing import Any, Mapping, Protocol

from .allocation import TechnologyEnergy, rebalance_energy_mix


SUPPORTED_SCENARIO_SOURCE_STATUSES = {
    "accepted_regional",
    "provisional_fallback",
}
SUPPORTED_SCENARIO_USES = {
    "regional_planning",
    "planning_exploration_only",
}
REQUIRED_SCENARIO_ASSET_ROLES = {"energy_model", "area_demand"}
REQUIRED_DISPLAY_LANGUAGES = {"sv", "en", "da_no"}
SCENARIO_CAPABILITY_ID = "workspace.scenario"
SCENARIO_CONTRACT_SCHEMA_VERSION = "1.0"
SCENARIO_REQUEST_SCHEMA_VERSION = "1.1"
SCENARIO_RESULT_SCHEMA_VERSION = "1.1"
SCENARIO_SNAPSHOT_SCHEMA_VERSION = "1.0"
SCENARIO_ACCESS_SCOPE_KINDS = ("product", "review")
SCENARIO_ADAPTER_NORMALIZED_JSON = "normalized_json_v1"
SCENARIO_ADAPTER_TIMES_AREA_DEMAND = "times_duckdb_area_demand_xlsx_v1"
SCENARIO_ADAPTER_CAPACITY = "capacity_area_xlsx_v1"
SUPPORTED_SCENARIO_ADAPTERS = {
    SCENARIO_ADAPTER_CAPACITY,
    SCENARIO_ADAPTER_NORMALIZED_JSON,
    SCENARIO_ADAPTER_TIMES_AREA_DEMAND,
}
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SCENARIO_UNIT_TO_TWH = {
    "twh": 1.0,
    "gwh": 1e-3,
    "mwh": 1e-6,
    "pj": 1.0 / 3.6,
    "tj": 1.0 / 3600.0,
}
_HOURS_PER_YEAR = 8760.0
_TIMES_AREA_FACTOR_COLUMNS = {
    "low": "low_km2_per_twh",
    "mid": "mid_km2_per_twh",
    "high": "high_km2_per_twh",
}


def _required_text(raw: dict[str, Any], key: str, context: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"{context} {key} is required")
    return value


def _is_safe_provider_path(value: str) -> bool:
    if not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts


def _is_lower_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


@dataclass(frozen=True)
class ScenarioSourceAsset:
    role: str
    path: str
    sha256: str
    format: str


@dataclass(frozen=True)
class ScenarioSourceContract:
    schema_version: str
    status: str
    intended_region_id: str
    source_region_id: str
    source_dataset_id: str
    source_label: str
    provider: str
    regional_acceptance: bool
    allowed_use: str
    provenance: str
    limitation: str
    replacement_condition: str
    warning_by_language: dict[str, str]
    assets: dict[str, ScenarioSourceAsset]

    @property
    def is_provisional(self) -> bool:
        return self.status == "provisional_fallback"

    def warning(self, language: str) -> str:
        return self.warning_by_language.get(
            str(language),
            self.warning_by_language["sv"],
        )


@dataclass(frozen=True)
class ScenarioPlanningLevel:
    scenario_id: str
    label: str
    source_scenario: str
    planning_year: int
    energy_scale: float
    area_demand_scenario: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "label": self.label,
            "source_scenario": self.source_scenario,
            "planning_year": self.planning_year,
            "energy_scale": self.energy_scale,
            "area_demand_scenario": self.area_demand_scenario,
        }


@dataclass(frozen=True)
class ScenarioAreaDemandOption:
    scenario_id: str
    label: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScenarioTechnologyShare:
    technology_id: str
    share_pct: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScenarioContract:
    schema_version: str
    region_id: str
    scenario_set_id: str
    adapter_id: str
    adapter_configuration_json: str
    technology_ids: tuple[str, ...]
    default_scenario_id: str
    planning_levels: tuple[ScenarioPlanningLevel, ...]
    area_demand_options: tuple[ScenarioAreaDemandOption, ...]
    default_area_demand_scenario: str
    technology_share_step_pct: float
    default_technology_shares: tuple[ScenarioTechnologyShare, ...]
    source: ScenarioSourceContract

    def adapter_configuration(self) -> Mapping[str, Any]:
        value = json.loads(self.adapter_configuration_json)
        return _mapping(value, "scenario adapter configuration")

    def planning_level(self, scenario_id: str) -> ScenarioPlanningLevel:
        normalized = _identifier(scenario_id, "scenario id")
        try:
            return next(
                item
                for item in self.planning_levels
                if item.scenario_id == normalized
            )
        except StopIteration as exc:
            raise KeyError(f"Unknown planning scenario: {normalized}") from exc

    def area_demand_option(
        self,
        scenario_id: str,
    ) -> ScenarioAreaDemandOption:
        normalized = _identifier(scenario_id, "area-demand scenario id")
        try:
            return next(
                item
                for item in self.area_demand_options
                if item.scenario_id == normalized
            )
        except StopIteration as exc:
            raise KeyError(
                f"Unknown area-demand scenario: {normalized}"
            ) from exc


@dataclass(frozen=True)
class ScenarioRequest:
    schema_version: str
    access_scope: str
    capability_id: str
    region_id: str
    scenario_set_id: str
    scenario_id: str
    source_scenario: str
    planning_year: int
    energy_scale: float
    area_demand_scenario: str
    technology_shares: tuple[ScenarioTechnologyShare, ...]
    adapter_id: str
    source_assets_signature_sha256: str
    contract_signature_sha256: str
    capacity_mw_by_technology: tuple[tuple[str, float], ...] | None = None

    def as_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "capability_id": self.capability_id,
            "region_id": self.region_id,
            "scenario_set_id": self.scenario_set_id,
            "scenario_id": self.scenario_id,
            "source_scenario": self.source_scenario,
            "planning_year": self.planning_year,
            "energy_scale": self.energy_scale,
            "area_demand_scenario": self.area_demand_scenario,
            "technology_shares": [
                item.as_dict() for item in self.technology_shares
            ],
            "adapter_id": self.adapter_id,
            "source_assets_signature_sha256": (
                self.source_assets_signature_sha256
            ),
            "contract_signature_sha256": self.contract_signature_sha256,
        }
        if self.capacity_mw_by_technology is not None:
            result["capacity_mw_by_technology"] = dict(self.capacity_mw_by_technology)
        return result


@dataclass(frozen=True)
class ScenarioEnergyObservation:
    source_scenario: str
    planning_year: int
    technology_id: str
    value_twh: float


@dataclass(frozen=True)
class ScenarioAreaFactor:
    area_demand_scenario: str
    technology_id: str
    km2_per_twh: float


@dataclass(frozen=True)
class ScenarioDataSnapshot:
    schema_version: str
    source_assets_signature_sha256: str
    energy_observations: tuple[ScenarioEnergyObservation, ...]
    area_factors: tuple[ScenarioAreaFactor, ...]


@dataclass(frozen=True)
class ScenarioTechnologyResult:
    technology_id: str
    energy_twh: float | None
    km2_per_twh: float | None
    area_need_km2: float
    capacity_mw: float | None = None
    km2_per_mw: float | None = None

    def as_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        if self.capacity_mw is None:
            raw.pop("capacity_mw")
            raw.pop("km2_per_mw")
        return raw


@dataclass(frozen=True)
class ScenarioResult:
    schema_version: str
    request: ScenarioRequest
    scenario_label: str
    source_status: str
    source_dataset_id: str
    source_label: str
    allowed_use: str
    regional_acceptance: bool
    warning_by_language: tuple[tuple[str, str], ...]
    technologies: tuple[ScenarioTechnologyResult, ...]
    total_energy_twh: float | None
    total_area_need_km2: float

    def technology_result(
        self,
        technology_id: str,
    ) -> ScenarioTechnologyResult:
        normalized = _identifier(
            technology_id,
            "scenario result technology id",
        )
        try:
            return next(
                item
                for item in self.technologies
                if item.technology_id == normalized
            )
        except StopIteration as exc:
            raise KeyError(
                f"Unknown scenario result technology: {normalized}"
            ) from exc

    def warning(self, language: str) -> str:
        warnings = dict(self.warning_by_language)
        return warnings.get(str(language), warnings["sv"])

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request": self.request.as_dict(),
            "scenario_label": self.scenario_label,
            "source_status": self.source_status,
            "source_dataset_id": self.source_dataset_id,
            "source_label": self.source_label,
            "allowed_use": self.allowed_use,
            "regional_acceptance": self.regional_acceptance,
            "warning_by_language": dict(self.warning_by_language),
            "technologies": [item.as_dict() for item in self.technologies],
            "total_energy_twh": self.total_energy_twh,
            "total_area_need_km2": self.total_area_need_km2,
        }


class ResolvedScenarioAsset(Protocol):
    provider: str
    provider_path: str
    format: str
    path: Path
    bytes: int
    sha256: str


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
        raise ValueError(
            f"{label} keys drifted: expected={sorted(expected)}, "
            f"actual={sorted(value)}"
        )


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be an exact non-empty string")
    return value


def _identifier(value: Any, label: str) -> str:
    text = _text(value, label)
    if _IDENTIFIER.fullmatch(text) is None:
        raise ValueError(f"{label} must be a canonical identifier")
    return text


def _sha256(value: Any, label: str) -> str:
    text = _text(value, label)
    if _SHA256.fullmatch(text) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _positive_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a positive number")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise ValueError(f"{label} must be finite and positive")
    return result


def _non_negative_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a non-negative number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite and non-negative")
    return result


def _percentage(value: Any, label: str) -> float:
    result = _non_negative_number(value, label)
    if result > 100.0:
        raise ValueError(f"{label} must be between 0 and 100")
    return result


def _is_step_aligned(value: float, step: float) -> bool:
    ratio = float(value) / float(step)
    return math.isclose(ratio, round(ratio), rel_tol=0.0, abs_tol=1e-9)


def _technology_shares(
    values: Any,
    *,
    technology_ids: tuple[str, ...],
    step_pct: float,
    label: str,
) -> tuple[ScenarioTechnologyShare, ...]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{label} must be a non-empty ordered array")
    shares: list[ScenarioTechnologyShare] = []
    for index, value in enumerate(values):
        raw = _mapping(value, f"{label} {index}")
        _exact_keys(
            raw,
            {"technology_id", "share_pct"},
            f"{label} {index}",
        )
        share = ScenarioTechnologyShare(
            technology_id=_identifier(
                raw.get("technology_id"),
                f"{label} {index} technology id",
            ),
            share_pct=_percentage(
                raw.get("share_pct"),
                f"{label} {index} share",
            ),
        )
        if step_pct is not None and not _is_step_aligned(share.share_pct, step_pct):
            raise ValueError(
                f"{label} {index} share must align to the declared step"
            )
        shares.append(share)
    if tuple(item.technology_id for item in shares) != technology_ids:
        raise ValueError(
            f"{label} technology identity and order must match technology_ids"
        )
    if not math.isclose(
        math.fsum(item.share_pct for item in shares),
        100.0,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise ValueError(f"{label} must sum to exactly 100 percent")
    return tuple(shares)


def _capacity_mw_values(value: Any) -> tuple[tuple[str, float], ...]:
    """Keep explicit installed MW immutable and independent of JSON key order."""
    raw = _mapping(value, "scenario capacity MW")
    if not raw:
        raise ValueError("Scenario capacity MW must declare technologies")
    values = tuple(sorted(
        (_identifier(technology_id, "capacity technology id"),
         _non_negative_number(mw, "capacity MW"))
        for technology_id, mw in raw.items()
    ))
    try:
        total = math.fsum(mw for _, mw in values)
    except OverflowError as exc:
        raise ValueError("Total capacity MW must be finite") from exc
    if not math.isfinite(total):
        raise ValueError("Total capacity MW must be finite")
    return values


def _capacity_mw_shares(
    values: tuple[tuple[str, float], ...],
    technology_ids: tuple[str, ...],
) -> tuple[ScenarioTechnologyShare, ...]:
    capacities = dict(values)
    if set(capacities) != set(technology_ids):
        raise ValueError("Capacity MW must declare every technology exactly once")
    total = math.fsum(capacities.values())
    # A zero target has no mix; it is not a fictitious 50/50 allocation.
    if total == 0.0:
        return ()
    return tuple(ScenarioTechnologyShare(technology_id, capacities[technology_id] / total * 100.0)
                 for technology_id in technology_ids)


def _canonical_sha256(value: Any) -> str:
    payload = _canonical_json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scenario_source_assets_signature(contract: ScenarioSourceContract) -> str:
    return _canonical_sha256(
        [
            {
                "role": asset.role,
                "provider": contract.provider,
                "path": asset.path,
                "format": asset.format,
                "sha256": asset.sha256,
            }
            for asset in sorted(contract.assets.values(), key=lambda item: item.role)
        ]
    )


def scenario_source_contract(
    manifest: dict[str, Any] | None,
) -> ScenarioSourceContract:
    raw_manifest = manifest or {}
    raw = raw_manifest.get("source_contract")
    if not isinstance(raw, dict):
        raise ValueError("Scenario manifest source_contract is required")

    context = "Scenario source contract"
    schema_version = _required_text(raw, "schema_version", context)
    if schema_version != "1.0":
        raise ValueError(
            f"Unsupported scenario source schema version: {schema_version}"
        )

    status = _required_text(raw, "status", context)
    if status not in SUPPORTED_SCENARIO_SOURCE_STATUSES:
        raise ValueError(f"Unsupported scenario source status: {status}")
    manifest_status = str(raw_manifest.get("status") or "").strip()
    if manifest_status != status:
        raise ValueError(
            "Scenario manifest status must match source_contract status"
        )

    intended_region_id = _required_text(raw, "intended_region_id", context)
    manifest_region_id = str(raw_manifest.get("region_id") or "").strip()
    if intended_region_id != manifest_region_id:
        raise ValueError(
            "Scenario source intended_region_id must match manifest region_id"
        )

    source_region_id = _required_text(raw, "source_region_id", context)
    source_dataset_id = _required_text(raw, "source_dataset_id", context)
    source_label = _required_text(raw, "source_label", context)
    provider = _required_text(raw, "provider", context)
    allowed_use = _required_text(raw, "allowed_use", context)
    if allowed_use not in SUPPORTED_SCENARIO_USES:
        raise ValueError(f"Unsupported scenario source allowed_use: {allowed_use}")

    regional_acceptance = raw.get("regional_acceptance")
    if not isinstance(regional_acceptance, bool):
        raise ValueError(
            "Scenario source regional_acceptance must be a boolean"
        )

    provenance = _required_text(raw, "provenance", context)
    limitation = _required_text(raw, "limitation", context)
    replacement_condition = _required_text(raw, "replacement_condition", context)

    if status == "accepted_regional":
        if not regional_acceptance or allowed_use != "regional_planning":
            raise ValueError(
                "Accepted regional scenarios require regional acceptance and "
                "regional_planning use"
            )
    else:
        if regional_acceptance:
            raise ValueError(
                "A provisional scenario fallback cannot claim regional acceptance"
            )
        if allowed_use != "planning_exploration_only":
            raise ValueError(
                "A provisional scenario fallback is limited to planning exploration"
            )

    raw_warnings = raw.get("display_warning")
    if not isinstance(raw_warnings, dict):
        raise ValueError("Scenario source display_warning is required")
    warning_by_language = {
        str(language): str(message).strip()
        for language, message in raw_warnings.items()
        if str(message).strip()
    }
    missing_languages = REQUIRED_DISPLAY_LANGUAGES - set(warning_by_language)
    if missing_languages:
        raise ValueError(
            "Scenario source display_warning is missing languages: "
            + ", ".join(sorted(missing_languages))
        )

    energy_model = raw_manifest.get("energy_model")
    if not isinstance(energy_model, dict):
        raise ValueError("Scenario manifest energy_model is required")
    adapter_id = _required_text(energy_model, "adapter_id", "Scenario energy model")
    if adapter_id not in SUPPORTED_SCENARIO_ADAPTERS:
        raise NotImplementedError(f"Unsupported scenario adapter: {adapter_id}")

    raw_assets = raw.get("assets")
    if not isinstance(raw_assets, dict):
        raise ValueError("Scenario source assets are required")
    assets: dict[str, ScenarioSourceAsset] = {}
    for role, item in raw_assets.items():
        if not isinstance(item, dict):
            raise ValueError(f"Scenario source asset {role} must be an object")
        role_text = str(role).strip()
        path = _required_text(item, "path", f"Scenario source asset {role_text}")
        sha256 = _required_text(
            item,
            "sha256",
            f"Scenario source asset {role_text}",
        )
        asset_format = _required_text(
            item,
            "format",
            f"Scenario source asset {role_text}",
        )
        if not _is_safe_provider_path(path):
            raise ValueError(
                f"Scenario source asset {role_text} path must be provider-relative"
            )
        if not _is_lower_sha256(sha256):
            raise ValueError(
                f"Scenario source asset {role_text} sha256 is invalid"
            )
        assets[role_text] = ScenarioSourceAsset(
            role=role_text,
            path=path,
            sha256=sha256,
            format=asset_format,
        )
    missing_roles = REQUIRED_SCENARIO_ASSET_ROLES - set(assets)
    if missing_roles:
        raise ValueError(
            "Scenario source assets are missing roles: "
            + ", ".join(sorted(missing_roles))
        )
    unexpected_roles = set(assets) - REQUIRED_SCENARIO_ASSET_ROLES
    if unexpected_roles:
        raise ValueError(
            "Scenario source assets contain undeclared roles: "
            + ", ".join(sorted(unexpected_roles))
        )

    if adapter_id in {SCENARIO_ADAPTER_NORMALIZED_JSON, SCENARIO_ADAPTER_CAPACITY}:
        configured_paths = {
            "energy_model": str(
                ((energy_model.get("energy_source") or {}).get("path")) or ""
            ).strip(),
            "area_demand": str(
                ((energy_model.get("area_demand") or {}).get("path")) or ""
            ).strip(),
        }
        expected_formats = {"energy_model": "json", "area_demand": "json"}
        if adapter_id == SCENARIO_ADAPTER_CAPACITY:
            expected_formats = {"energy_model": "xlsx", "area_demand": "xlsx"}
    else:
        configured_paths = {
            "energy_model": str(
                ((energy_model.get("duckdb") or {}).get("path")) or ""
            ).strip(),
            "area_demand": str(
                ((energy_model.get("area_demand") or {}).get("path")) or ""
            ).strip(),
        }
        expected_formats = {"energy_model": "duckdb", "area_demand": "xlsx"}
    for role, configured_path in configured_paths.items():
        if configured_path != assets[role].path:
            raise ValueError(
                f"Scenario {role} path must match source_contract asset path"
            )
        if assets[role].format != expected_formats[role]:
            raise ValueError(
                f"Scenario {role} format must match adapter {adapter_id}"
            )

    levels = tuple(str(value) for value in raw_manifest.get("scenario_levels") or [])
    planning = energy_model.get("planning") or {}
    scenarios = planning.get("scenarios") or []
    scenario_ids = tuple(
        str(item.get("id"))
        for item in scenarios
        if isinstance(item, dict) and item.get("id")
    )
    if not levels or levels != scenario_ids or len(set(levels)) != len(levels):
        raise ValueError(
            "Scenario levels must be unique and match planning scenario order"
        )
    if str(planning.get("default_scenario") or "") not in scenario_ids:
        raise ValueError("Scenario planning default must be a declared level")
    for item in scenarios:
        if not isinstance(item, dict):
            raise ValueError("Planning scenario entries must be objects")
        for key in ("source_scenario", "area_demand_scenario"):
            _required_text(item, key, f"Planning scenario {item.get('id')}")
        try:
            planning_year = int(item.get("planning_year"))
            energy_scale = float(item.get("energy_scale"))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Planning scenario {item.get('id')} has invalid year or scale"
            ) from exc
        if planning_year <= 0 or energy_scale <= 0.0:
            raise ValueError(
                f"Planning scenario {item.get('id')} year and scale must be positive"
            )

    return ScenarioSourceContract(
        schema_version=schema_version,
        status=status,
        intended_region_id=intended_region_id,
        source_region_id=source_region_id,
        source_dataset_id=source_dataset_id,
        source_label=source_label,
        provider=provider,
        regional_acceptance=regional_acceptance,
        allowed_use=allowed_use,
        provenance=provenance,
        limitation=limitation,
        replacement_condition=replacement_condition,
        warning_by_language=warning_by_language,
        assets=assets,
    )


def scenario_contract(manifest: Mapping[str, Any]) -> ScenarioContract:
    """Parse the complete immutable scenario capability contract.

    Data trust is deliberately kept inside ``source``. A successful technical
    parse or execution never upgrades a provisional source to regional
    acceptance.
    """

    raw = _mapping(manifest, "scenario manifest")
    source = scenario_source_contract(dict(raw))
    schema_version = _text(raw.get("schema_version"), "scenario schema version")
    if schema_version != SCENARIO_CONTRACT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported scenario schema version: {schema_version}")
    region_id = _identifier(raw.get("region_id"), "scenario region id")
    scenario_set_id = _identifier(
        raw.get("scenario_set_id"),
        "scenario set id",
    )
    energy_model = _mapping(raw.get("energy_model"), "scenario energy model")
    adapter_id = _text(energy_model.get("adapter_id"), "scenario adapter id")
    if adapter_id not in SUPPORTED_SCENARIO_ADAPTERS:
        raise NotImplementedError(f"Unsupported scenario adapter: {adapter_id}")

    if adapter_id in {SCENARIO_ADAPTER_NORMALIZED_JSON, SCENARIO_ADAPTER_CAPACITY}:
        raw_technology_ids = energy_model.get("technology_ids")
        if not isinstance(raw_technology_ids, list) or not raw_technology_ids:
            raise ValueError(
                "Normalized scenario adapter requires explicit technology_ids"
            )
        technology_ids = tuple(
            _identifier(value, "scenario technology id")
            for value in raw_technology_ids
        )
        adapter_configuration_json = _canonical_json(
            {"capacity": _mapping(energy_model.get("capacity"), "capacity configuration")}
            if adapter_id == SCENARIO_ADAPTER_CAPACITY else {})
    else:
        duckdb_config = _mapping(
            energy_model.get("duckdb"),
            "scenario DuckDB adapter",
        )
        technology_map = _mapping(
            duckdb_config.get("technology_map"),
            "scenario technology map",
        )
        technology_ids = tuple(
            dict.fromkeys(
                _identifier(value, "scenario technology id")
                for value in technology_map.values()
            )
        )
        area_demand = _mapping(
            energy_model.get("area_demand"),
            "scenario area-demand adapter",
        )
        times_map = _mapping(
            area_demand.get("times_technology_map"),
            "scenario area-demand technology map",
        )
        area_technology_ids = tuple(
            dict.fromkeys(
                _identifier(
                    _mapping(value, "scenario area-demand rule").get("energy_key"),
                    "scenario area-demand technology id",
                )
                for value in times_map.values()
            )
        )
        if set(area_technology_ids) != set(technology_ids):
            raise ValueError(
                "Scenario energy and area-demand technology identities disagree"
            )
        adapter_configuration_json = _canonical_json(
            {
                "duckdb": {
                    key: value
                    for key, value in duckdb_config.items()
                    if key != "path"
                },
                "area_demand": {
                    key: value
                    for key, value in area_demand.items()
                    if key != "path"
                },
            }
        )
    if len(technology_ids) != len(set(technology_ids)) or not technology_ids:
        raise ValueError("Scenario technology ids must be unique and non-empty")

    raw_levels = raw.get("scenario_levels")
    if not isinstance(raw_levels, list) or not raw_levels:
        raise ValueError("Scenario levels must be a non-empty ordered array")
    scenario_level_ids = tuple(
        _identifier(value, "scenario level id") for value in raw_levels
    )
    if len(scenario_level_ids) != len(set(scenario_level_ids)):
        raise ValueError("Scenario level ids must be unique")
    planning = _mapping(
        energy_model.get("planning"),
        "scenario planning contract",
    )
    raw_planning_levels = planning.get("scenarios")
    if not isinstance(raw_planning_levels, list) or not raw_planning_levels:
        raise ValueError("Scenario planning levels must be declared")
    planning_levels: list[ScenarioPlanningLevel] = []
    for index, item in enumerate(raw_planning_levels):
        level = _mapping(item, f"scenario planning level {index}")
        planning_levels.append(
            ScenarioPlanningLevel(
                scenario_id=_identifier(
                    level.get("id"),
                    f"scenario planning level {index} id",
                ),
                label=_text(
                    level.get("label"),
                    f"scenario planning level {index} label",
                ),
                source_scenario=_text(
                    level.get("source_scenario"),
                    f"scenario planning level {index} source scenario",
                ),
                planning_year=_positive_int(
                    level.get("planning_year"),
                    f"scenario planning level {index} year",
                ),
                energy_scale=_positive_number(
                    level.get("energy_scale"),
                    f"scenario planning level {index} energy scale",
                ),
                area_demand_scenario=_text(
                    level.get("area_demand_scenario"),
                    f"scenario planning level {index} area-demand scenario",
                ),
            )
        )
    if tuple(item.scenario_id for item in planning_levels) != scenario_level_ids:
        raise ValueError(
            "Scenario planning level order must match scenario_levels exactly"
        )
    default_scenario_id = _identifier(
        planning.get("default_scenario"),
        "scenario default id",
    )
    if default_scenario_id not in scenario_level_ids:
        raise ValueError("Scenario default must be an explicitly declared level")
    raw_area_options = planning.get("area_demand_options")
    if not isinstance(raw_area_options, list) or not raw_area_options:
        raise ValueError("Scenario area-demand options must be declared")
    area_demand_options: list[ScenarioAreaDemandOption] = []
    for index, value in enumerate(raw_area_options):
        option = _mapping(value, f"scenario area-demand option {index}")
        _exact_keys(
            option,
            {"id", "label"},
            f"scenario area-demand option {index}",
        )
        area_demand_options.append(
            ScenarioAreaDemandOption(
                scenario_id=_identifier(
                    option.get("id"),
                    f"scenario area-demand option {index} id",
                ),
                label=_text(
                    option.get("label"),
                    f"scenario area-demand option {index} label",
                ),
            )
        )
    area_option_ids = tuple(item.scenario_id for item in area_demand_options)
    if len(area_option_ids) != len(set(area_option_ids)):
        raise ValueError("Scenario area-demand option ids must be unique")
    planning_area_ids = {
        item.area_demand_scenario for item in planning_levels
    }
    if not planning_area_ids.issubset(set(area_option_ids)):
        raise ValueError(
            "Planning levels reference undeclared area-demand scenarios"
        )
    default_area_demand_scenario = _identifier(
        planning.get("default_area_demand_scenario"),
        "scenario default area-demand id",
    )
    if default_area_demand_scenario not in area_option_ids:
        raise ValueError(
            "Scenario default area-demand id must be a declared option"
        )
    technology_mix = _mapping(
        planning.get("technology_mix"),
        "scenario technology-mix control",
    )
    _exact_keys(
        technology_mix,
        {"share_step_pct", "default_shares"},
        "scenario technology-mix control",
    )
    technology_share_step_pct = _positive_number(
        technology_mix.get("share_step_pct"),
        "scenario technology-share step",
    )
    if technology_share_step_pct > 100.0:
        raise ValueError(
            "Scenario technology-share step must be at most 100 percent"
        )
    default_technology_shares = _technology_shares(
        technology_mix.get("default_shares"),
        technology_ids=technology_ids,
        step_pct=technology_share_step_pct,
        label="scenario default technology shares",
    )
    return ScenarioContract(
        schema_version=schema_version,
        region_id=region_id,
        scenario_set_id=scenario_set_id,
        adapter_id=adapter_id,
        adapter_configuration_json=adapter_configuration_json,
        technology_ids=technology_ids,
        default_scenario_id=default_scenario_id,
        planning_levels=tuple(planning_levels),
        area_demand_options=tuple(area_demand_options),
        default_area_demand_scenario=default_area_demand_scenario,
        technology_share_step_pct=technology_share_step_pct,
        default_technology_shares=default_technology_shares,
        source=source,
    )


def scenario_contract_signature(contract: ScenarioContract) -> str:
    if not isinstance(contract, ScenarioContract):
        raise TypeError("contract must be a ScenarioContract")
    return _canonical_sha256(asdict(contract))


def build_scenario_request_from_contract(
    contract: ScenarioContract,
    *,
    access_scope: str,
    scenario_id: str | None = None,
    area_demand_scenario: str | None = None,
    technology_shares_pct: Mapping[str, Any] | None = None,
    capacity_mw_by_technology: Mapping[str, Any] | None = None,
) -> ScenarioRequest:
    if not isinstance(contract, ScenarioContract):
        raise TypeError("contract must be a ScenarioContract")
    scope = _text(access_scope, "scenario access scope").lower()
    parts = scope.split(":", 1)
    if (
        len(parts) != 2
        or parts[0] not in SCENARIO_ACCESS_SCOPE_KINDS
        or parts[1] != contract.region_id
    ):
        raise ValueError(
            "Scenario access_scope must be product:<region> or review:<region>"
        )
    level = contract.planning_level(
        contract.default_scenario_id if scenario_id is None else scenario_id
    )
    selected_area_demand = contract.area_demand_option(
        contract.default_area_demand_scenario
        if area_demand_scenario is None
        else area_demand_scenario
    ).scenario_id
    capacities = None
    if capacity_mw_by_technology is not None:
        if contract.adapter_id != SCENARIO_ADAPTER_CAPACITY:
            raise ValueError("Explicit capacity MW requires the capacity adapter")
        if technology_shares_pct is not None:
            raise ValueError("Explicit capacity MW derives its shares; do not submit both")
        capacities = _capacity_mw_values(capacity_mw_by_technology)
        technology_shares = _capacity_mw_shares(capacities, contract.technology_ids)
    elif technology_shares_pct is None:
        if contract.adapter_id == SCENARIO_ADAPTER_CAPACITY:
            from .capacity_scenarios import model_shares
            technology_shares = model_shares(contract, level.scenario_id)
        else:
            technology_shares = contract.default_technology_shares
    else:
        raw_shares = _mapping(
            technology_shares_pct,
            "scenario technology shares",
        )
        if set(raw_shares) != set(contract.technology_ids):
            raise ValueError(
                "Scenario technology shares must declare every contract "
                "technology exactly once"
            )
        technology_shares = _technology_shares(
            [
                {
                    "technology_id": technology_id,
                    "share_pct": raw_shares[technology_id],
                }
                for technology_id in contract.technology_ids
            ],
            technology_ids=contract.technology_ids,
            step_pct=(None if contract.adapter_id == SCENARIO_ADAPTER_CAPACITY else contract.technology_share_step_pct),
            label="scenario technology shares",
        )
    return ScenarioRequest(
        schema_version=SCENARIO_REQUEST_SCHEMA_VERSION,
        access_scope=scope,
        capability_id=SCENARIO_CAPABILITY_ID,
        region_id=contract.region_id,
        scenario_set_id=contract.scenario_set_id,
        scenario_id=level.scenario_id,
        source_scenario=level.source_scenario,
        planning_year=level.planning_year,
        energy_scale=level.energy_scale,
        area_demand_scenario=selected_area_demand,
        technology_shares=technology_shares,
        adapter_id=contract.adapter_id,
        source_assets_signature_sha256=scenario_source_assets_signature(
            contract.source
        ),
        contract_signature_sha256=scenario_contract_signature(contract),
        capacity_mw_by_technology=capacities,
    )


def parse_scenario_request(value: Mapping[str, Any]) -> ScenarioRequest:
    raw = _mapping(value, "scenario request")
    _exact_keys(
        raw,
        {
            "schema_version",
            "access_scope",
            "capability_id",
            "region_id",
            "scenario_set_id",
            "scenario_id",
            "source_scenario",
            "planning_year",
            "energy_scale",
            "area_demand_scenario",
            "technology_shares",
            "adapter_id",
            "source_assets_signature_sha256",
            "contract_signature_sha256",
        } | ({"capacity_mw_by_technology"} if "capacity_mw_by_technology" in raw else set()),
        "scenario request",
    )
    if raw["schema_version"] != SCENARIO_REQUEST_SCHEMA_VERSION:
        raise ValueError("Unsupported scenario request schema version")
    region_id = _identifier(raw["region_id"], "scenario request region id")
    access_scope = _text(raw["access_scope"], "scenario request access scope")
    if access_scope != access_scope.lower():
        raise ValueError("Scenario access scope must be normalized")
    scope_parts = access_scope.split(":", 1)
    if (
        len(scope_parts) != 2
        or scope_parts[0] not in SCENARIO_ACCESS_SCOPE_KINDS
        or scope_parts[1] != region_id
    ):
        raise ValueError("Scenario request access scope is not region-bound")
    if raw["capability_id"] != SCENARIO_CAPABILITY_ID:
        raise ValueError(
            f"Scenario request capability must be {SCENARIO_CAPABILITY_ID}"
        )
    adapter_id = _text(raw["adapter_id"], "scenario request adapter id")
    if adapter_id not in SUPPORTED_SCENARIO_ADAPTERS:
        raise NotImplementedError(f"Unsupported scenario adapter: {adapter_id}")
    capacities = None
    if "capacity_mw_by_technology" in raw:
        if adapter_id != SCENARIO_ADAPTER_CAPACITY:
            raise ValueError("Explicit capacity MW requires the capacity adapter")
        capacities = _capacity_mw_values(raw["capacity_mw_by_technology"])
    raw_technology_shares = raw.get("technology_shares")
    if (
        not isinstance(raw_technology_shares, list)
        or (not raw_technology_shares and capacities is None)
    ):
        raise ValueError(
            "Scenario request technology_shares must be a non-empty array"
        )
    technology_shares: list[ScenarioTechnologyShare] = []
    for index, value in enumerate(raw_technology_shares):
        item = _mapping(value, f"scenario request technology share {index}")
        _exact_keys(
            item,
            {"technology_id", "share_pct"},
            f"scenario request technology share {index}",
        )
        technology_shares.append(
            ScenarioTechnologyShare(
                technology_id=_identifier(
                    item.get("technology_id"),
                    f"scenario request technology share {index} id",
                ),
                share_pct=_percentage(
                    item.get("share_pct"),
                    f"scenario request technology share {index}",
                ),
            )
        )
    if len({item.technology_id for item in technology_shares}) != len(
        technology_shares
    ):
        raise ValueError(
            "Scenario request technology share ids must be unique"
        )
    if capacities is not None:
        technology_ids = tuple(item.technology_id for item in technology_shares)
        if not technology_ids and all(mw == 0.0 for _, mw in capacities):
            technology_ids = tuple(technology_id for technology_id, _ in capacities)
        if tuple(technology_shares) != _capacity_mw_shares(capacities, technology_ids):
            raise ValueError("Scenario shares differ from explicit capacity MW")
    elif not math.isclose(
        math.fsum(item.share_pct for item in technology_shares),
        100.0,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise ValueError(
            "Scenario request technology shares must sum to 100 percent"
        )
    return ScenarioRequest(
        schema_version=SCENARIO_REQUEST_SCHEMA_VERSION,
        access_scope=access_scope,
        capability_id=SCENARIO_CAPABILITY_ID,
        region_id=region_id,
        scenario_set_id=_identifier(
            raw["scenario_set_id"],
            "scenario request set id",
        ),
        scenario_id=_identifier(raw["scenario_id"], "scenario request level id"),
        source_scenario=_text(
            raw["source_scenario"],
            "scenario request source scenario",
        ),
        planning_year=_positive_int(
            raw["planning_year"],
            "scenario request planning year",
        ),
        energy_scale=_positive_number(
            raw["energy_scale"],
            "scenario request energy scale",
        ),
        area_demand_scenario=_text(
            raw["area_demand_scenario"],
            "scenario request area-demand scenario",
        ),
        technology_shares=tuple(technology_shares),
        adapter_id=adapter_id,
        source_assets_signature_sha256=_sha256(
            raw["source_assets_signature_sha256"],
            "scenario request source asset signature",
        ),
        contract_signature_sha256=_sha256(
            raw["contract_signature_sha256"],
            "scenario request contract signature",
        ),
        capacity_mw_by_technology=capacities,
    )


def validate_scenario_request_from_contract(
    contract: ScenarioContract,
    request: ScenarioRequest,
) -> ScenarioRequest:
    if not isinstance(request, ScenarioRequest):
        raise TypeError("request must be a ScenarioRequest")
    rebuilt = build_scenario_request_from_contract(
        contract,
        access_scope=request.access_scope,
        scenario_id=request.scenario_id,
        area_demand_scenario=request.area_demand_scenario,
        technology_shares_pct=({
            item.technology_id: item.share_pct
            for item in request.technology_shares
        } if request.capacity_mw_by_technology is None else None),
        capacity_mw_by_technology=(dict(request.capacity_mw_by_technology)
                                   if request.capacity_mw_by_technology is not None else None),
    )
    if rebuilt != request:
        raise ValueError("Scenario request drifted from its manifest contract")
    return request


def scenario_data_snapshot(
    *,
    source_assets_signature_sha256: str,
    energy_observations: tuple[ScenarioEnergyObservation, ...],
    area_factors: tuple[ScenarioAreaFactor, ...],
) -> ScenarioDataSnapshot:
    signature = _sha256(
        source_assets_signature_sha256,
        "scenario snapshot source signature",
    )
    if not energy_observations:
        raise ValueError("Scenario snapshot needs energy observations")
    if not area_factors:
        raise ValueError("Scenario snapshot needs area-demand factors")
    normalized_energy: list[ScenarioEnergyObservation] = []
    for index, item in enumerate(energy_observations):
        if not isinstance(item, ScenarioEnergyObservation):
            raise TypeError(
                f"Scenario energy observation {index} has the wrong type"
            )
        normalized_energy.append(
            ScenarioEnergyObservation(
                source_scenario=_text(
                    item.source_scenario,
                    f"scenario energy observation {index} source scenario",
                ),
                planning_year=_positive_int(
                    item.planning_year,
                    f"scenario energy observation {index} planning year",
                ),
                technology_id=_identifier(
                    item.technology_id,
                    f"scenario energy observation {index} technology",
                ),
                value_twh=_non_negative_number(
                    item.value_twh,
                    f"scenario energy observation {index} TWh",
                ),
            )
        )
    normalized_factors: list[ScenarioAreaFactor] = []
    seen_factors: set[tuple[str, str]] = set()
    for index, item in enumerate(area_factors):
        if not isinstance(item, ScenarioAreaFactor):
            raise TypeError(f"Scenario area factor {index} has the wrong type")
        normalized = ScenarioAreaFactor(
            area_demand_scenario=_text(
                item.area_demand_scenario,
                f"scenario area factor {index} area-demand scenario",
            ),
            technology_id=_identifier(
                item.technology_id,
                f"scenario area factor {index} technology",
            ),
            km2_per_twh=_positive_number(
                item.km2_per_twh,
                f"scenario area factor {index} km2/TWh",
            ),
        )
        key = (normalized.area_demand_scenario, normalized.technology_id)
        if key in seen_factors:
            raise ValueError(f"Duplicate scenario area factor: {key}")
        seen_factors.add(key)
        normalized_factors.append(normalized)
    return ScenarioDataSnapshot(
        schema_version=SCENARIO_SNAPSHOT_SCHEMA_VERSION,
        source_assets_signature_sha256=signature,
        energy_observations=tuple(normalized_energy),
        area_factors=tuple(normalized_factors),
    )


def _load_json_object(path: Path, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} cannot be read: {exc}") from exc
    return _mapping(value, label)


def _configured_text_array(
    value: Any,
    label: str,
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty ordered array")
    result = tuple(_text(item, f"{label} item") for item in value)
    if len(result) != len(set(result)):
        raise ValueError(f"{label} must not contain duplicates")
    return result


def _first_configured_column(
    available: tuple[str, ...],
    aliases: Any,
    label: str,
) -> str:
    candidates = _configured_text_array(aliases, f"{label} aliases")
    lookup = {column.lower(): column for column in available}
    for candidate in candidates:
        match = lookup.get(candidate.lower())
        if match is not None:
            return match
    raise ValueError(f"Scenario source lacks a configured {label} column")


def _quote_sql_identifier(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def _resolve_duckdb_table(connection: Any, candidates: Any) -> tuple[str, str]:
    for candidate in _configured_text_array(
        candidates,
        "scenario DuckDB source tables",
    ):
        matches = connection.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
              AND lower(table_name) = lower(?)
            ORDER BY table_schema, table_name
            """,
            [candidate],
        ).fetchall()
        if len(matches) > 1:
            raise ValueError(
                f"Scenario DuckDB table name is ambiguous: {candidate}"
            )
        if matches:
            return str(matches[0][0]), str(matches[0][1])
    raise ValueError("Scenario DuckDB lacks every declared source table")


def _duckdb_table_columns(
    connection: Any,
    schema_name: str,
    table_name: str,
) -> tuple[str, ...]:
    rows = connection.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = ? AND table_name = ?
        ORDER BY ordinal_position
        """,
        [schema_name, table_name],
    ).fetchall()
    columns = tuple(str(row[0]) for row in rows)
    if not columns:
        raise ValueError("Scenario DuckDB source table has no columns")
    return columns


def _load_times_energy_observations(
    contract: ScenarioContract,
    path: Path,
    configuration: Mapping[str, Any],
) -> tuple[ScenarioEnergyObservation, ...]:
    try:
        import duckdb
    except Exception as exc:  # pragma: no cover - optional runtime dependency
        raise RuntimeError(
            "The TIMES scenario adapter requires the duckdb package"
        ) from exc

    columns_config = _mapping(
        configuration.get("columns"),
        "scenario DuckDB column configuration",
    )
    technology_map_raw = _mapping(
        configuration.get("technology_map"),
        "scenario DuckDB technology map",
    )
    technology_map = {
        _text(key, "scenario source technology").upper(): _identifier(
            value,
            "scenario mapped technology",
        )
        for key, value in technology_map_raw.items()
    }
    if set(technology_map.values()) != set(contract.technology_ids):
        raise ValueError(
            "Scenario DuckDB technology map drifted from the contract"
        )

    connection = duckdb.connect(str(path), read_only=True)
    try:
        schema_name, table_name = _resolve_duckdb_table(
            connection,
            configuration.get("source_tables"),
        )
        available = _duckdb_table_columns(
            connection,
            schema_name,
            table_name,
        )
        scenario_column = _first_configured_column(
            available,
            columns_config.get("scenario"),
            "scenario",
        )
        year_column = _first_configured_column(
            available,
            columns_config.get("year"),
            "year",
        )
        value_column = _first_configured_column(
            available,
            columns_config.get("value"),
            "value",
        )
        unit_column = _first_configured_column(
            available,
            columns_config.get("unit"),
            "unit",
        )
        technology_columns = tuple(
            dict.fromkeys(
                _first_configured_column(
                    available,
                    [alias],
                    "technology",
                )
                for alias in _configured_text_array(
                    columns_config.get("technology"),
                    "scenario technology-column aliases",
                )
                if alias.lower() in {column.lower() for column in available}
            )
        )
        if not technology_columns:
            raise ValueError(
                "Scenario DuckDB lacks every configured technology column"
            )

        filters_raw = configuration.get("filters", {})
        filters = _mapping(filters_raw, "scenario DuckDB filters")
        filter_columns: list[tuple[str, frozenset[str]]] = []
        for filter_id, raw_values in filters.items():
            filter_key = _text(filter_id, "scenario DuckDB filter id")
            filter_column = _first_configured_column(
                available,
                columns_config.get(filter_key),
                f"{filter_key} filter",
            )
            allowed = frozenset(
                value.lower()
                for value in _configured_text_array(
                    raw_values,
                    f"scenario DuckDB {filter_key} filter values",
                )
            )
            filter_columns.append((filter_column, allowed))

        selected_columns = tuple(
            dict.fromkeys(
                (
                    scenario_column,
                    year_column,
                    value_column,
                    unit_column,
                    *technology_columns,
                    *(column for column, _ in filter_columns),
                )
            )
        )
        select_sql = ", ".join(
            _quote_sql_identifier(column) for column in selected_columns
        )
        table_sql = (
            f"{_quote_sql_identifier(schema_name)}."
            f"{_quote_sql_identifier(table_name)}"
        )
        rows = connection.execute(
            f"SELECT {select_sql} FROM {table_sql}"
        ).fetchall()
    finally:
        connection.close()

    positions = {
        column: index for index, column in enumerate(selected_columns)
    }
    aggregated: dict[tuple[str, int, str], float] = {}
    for row in rows:
        if any(
            str(row[positions[column]]).strip().lower() not in allowed
            for column, allowed in filter_columns
        ):
            continue
        mapped_technology = ""
        for column in technology_columns:
            raw_technology = str(row[positions[column]] or "").strip().upper()
            if raw_technology in technology_map:
                mapped_technology = technology_map[raw_technology]
                break
        if not mapped_technology:
            continue
        source_scenario = _text(
            str(row[positions[scenario_column]]),
            "scenario DuckDB source scenario",
        )
        try:
            raw_year = float(row[positions[year_column]])
            raw_value = float(row[positions[value_column]])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Scenario DuckDB contains a non-numeric year or value"
            ) from exc
        if not raw_year.is_integer():
            raise ValueError("Scenario DuckDB planning years must be integers")
        planning_year = _positive_int(
            int(raw_year),
            "scenario DuckDB planning year",
        )
        unit = str(row[positions[unit_column]] or "").strip().lower()
        if unit not in _SCENARIO_UNIT_TO_TWH:
            raise ValueError(f"Unsupported scenario energy unit: {unit!r}")
        value_twh = raw_value * _SCENARIO_UNIT_TO_TWH[unit]
        if not math.isfinite(value_twh):
            raise ValueError("Scenario DuckDB contains a non-finite value")
        key = (source_scenario, planning_year, mapped_technology)
        aggregated[key] = aggregated.get(key, 0.0) + value_twh
    return tuple(
        ScenarioEnergyObservation(
            source_scenario=source_scenario,
            planning_year=planning_year,
            technology_id=technology_id,
            value_twh=value_twh,
        )
        for (
            source_scenario,
            planning_year,
            technology_id,
        ), value_twh in sorted(aggregated.items())
    )


def _clean_area_text(value: Any) -> str:
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return ""
    return (
        text.replace("\u00a0", " ")
        .replace("±", "+/-")
        .replace("–", "-")
        .replace("−", "-")
    )


def _area_metric_kind(metric: Any) -> str | None:
    normalized = _clean_area_text(metric).lower()
    if "gwh/km" in normalized:
        return "gwh_per_km2"
    if "w/m" in normalized:
        return "w_per_m2"
    return None


def _area_numbers(value: Any) -> tuple[float, ...]:
    normalized = _clean_area_text(value).replace(",", ".")
    return tuple(
        float(token)
        for token in re.findall(r"\d+(?:\.\d+)?", normalized)
    )


def _source_value_to_km2_per_twh(
    source_value: float,
    metric_kind: str,
) -> float | None:
    if source_value <= 0.0:
        return None
    if metric_kind == "gwh_per_km2":
        return 1000.0 / source_value
    if metric_kind == "w_per_m2":
        return 1000.0 / (source_value * (_HOURS_PER_YEAR / 1000.0))
    return None


def _parse_area_value(value: Any, metric_kind: str) -> Mapping[str, Any] | None:
    text = _clean_area_text(value)
    if not text:
        return None
    numbers = _area_numbers(text)
    if not numbers:
        return None
    if any(character in text for character in ("<", ">", "≤", "≥")):
        return {
            "used": False,
            "source_values": (numbers[0],),
            "low": None,
            "mid": _source_value_to_km2_per_twh(numbers[0], metric_kind),
            "high": None,
        }
    if "+/-" in text and len(numbers) >= 2:
        center, spread = numbers[:2]
        source_values = [center]
        if center - spread > 0.0:
            source_values.append(center - spread)
        source_values.append(center + spread)
        converted = tuple(
            converted_value
            for source_value in source_values
            for converted_value in (
                _source_value_to_km2_per_twh(source_value, metric_kind),
            )
            if converted_value is not None
        )
        mid = _source_value_to_km2_per_twh(center, metric_kind)
        return {
            "used": bool(converted and mid is not None),
            "source_values": tuple(source_values),
            "low": min(converted) if converted else None,
            "mid": mid,
            "high": max(converted) if converted else None,
        }
    if "-" in text and len(numbers) >= 2:
        lower, upper = min(numbers[:2]), max(numbers[:2])
        midpoint = (
            math.sqrt(lower * upper)
            if lower > 0.0 and upper > 0.0
            else (lower + upper) / 2.0
        )
        source_values = (lower, midpoint, upper)
        converted = tuple(
            converted_value
            for source_value in source_values
            for converted_value in (
                _source_value_to_km2_per_twh(source_value, metric_kind),
            )
            if converted_value is not None
        )
        mid = _source_value_to_km2_per_twh(midpoint, metric_kind)
        return {
            "used": bool(converted and mid is not None),
            "source_values": source_values,
            "low": min(converted) if converted else None,
            "mid": mid,
            "high": max(converted) if converted else None,
        }
    converted = _source_value_to_km2_per_twh(numbers[0], metric_kind)
    return {
        "used": converted is not None,
        "source_values": (numbers[0],),
        "low": converted,
        "mid": converted,
        "high": converted,
    }


def _quality_bounds(
    configuration: Mapping[str, Any],
    metric_kind: str,
    technology_id: str,
) -> tuple[float, float]:
    quality_rules = _mapping(
        configuration.get("quality_rules"),
        "scenario area-demand quality rules",
    )
    metric_rules = _mapping(
        quality_rules.get(metric_kind),
        f"scenario {metric_kind} quality rules",
    )
    technology_rule = _mapping(
        metric_rules.get(technology_id),
        f"scenario {metric_kind}/{technology_id} quality rule",
    )
    lower = _non_negative_number(
        technology_rule.get("min"),
        f"scenario {metric_kind}/{technology_id} quality minimum",
    )
    upper = _positive_number(
        technology_rule.get("max"),
        f"scenario {metric_kind}/{technology_id} quality maximum",
    )
    if lower > upper:
        raise ValueError("Scenario area-demand quality bounds are reversed")
    return lower, upper


def _factor_cap(
    configuration: Mapping[str, Any],
    factor_column: str,
    technology_id: str,
    source_technology: str,
    literature_key: str,
) -> float | None:
    raw_caps = configuration.get("scenario_factor_caps", {})
    caps = _mapping(raw_caps, "scenario area-demand factor caps")
    raw_column_caps = caps.get(factor_column)
    if raw_column_caps is None:
        return None
    column_caps = _mapping(
        raw_column_caps,
        f"scenario area-demand {factor_column} caps",
    )
    for key in (technology_id, source_technology, literature_key):
        if key in column_caps:
            return _positive_number(
                column_caps[key],
                f"scenario area-demand {factor_column} cap",
            )
    return None


def _load_times_area_factors(
    contract: ScenarioContract,
    path: Path,
    configuration: Mapping[str, Any],
) -> tuple[ScenarioAreaFactor, ...]:
    try:
        import pandas as pd
    except Exception as exc:  # pragma: no cover - runtime dependency
        raise RuntimeError(
            "The TIMES area-demand adapter requires pandas and an XLSX engine"
        ) from exc

    frame = pd.read_excel(
        path,
        sheet_name=configuration.get("sheet_name", 0),
    )
    if len(frame) < 2 or len(frame.columns) < 3:
        raise ValueError("Scenario area-demand workbook is structurally incomplete")
    metric_row = frame.iloc[0]
    column_definitions: list[tuple[int, str]] = []
    for column_index in range(2, len(frame.columns)):
        metric_kind = _area_metric_kind(metric_row.iloc[column_index])
        if metric_kind is not None:
            column_definitions.append((column_index, metric_kind))
    if not column_definitions:
        raise ValueError("Scenario area-demand workbook has no supported metrics")

    raw_technology_rows = _mapping(
        configuration.get("technology_rows"),
        "scenario area-demand technology rows",
    )
    technology_rows = {
        _identifier(key, "scenario literature technology id"): _text(
            value,
            "scenario literature technology label",
        )
        for key, value in raw_technology_rows.items()
    }
    row_lookup: dict[str, int] = {}
    for row_index in range(1, len(frame)):
        label = _clean_area_text(frame.iloc[row_index, 0])
        if not label:
            continue
        if label.lower().startswith("sources:"):
            break
        for literature_key, expected_label in technology_rows.items():
            if label == _clean_area_text(expected_label):
                row_lookup.setdefault(literature_key, row_index)

    raw_mapping = _mapping(
        configuration.get("times_technology_map"),
        "scenario area-demand technology map",
    )
    factors: list[ScenarioAreaFactor] = []
    produced_technologies: list[str] = []
    for source_technology, raw_rule in raw_mapping.items():
        source_id = _text(
            source_technology,
            "scenario TIMES technology id",
        )
        rule = _mapping(
            raw_rule,
            f"scenario area-demand rule {source_id}",
        )
        technology_id = _identifier(
            rule.get("energy_key"),
            f"scenario area-demand rule {source_id} energy key",
        )
        literature_key = _identifier(
            rule.get("literature_key", technology_id),
            f"scenario area-demand rule {source_id} literature key",
        )
        if literature_key not in row_lookup:
            raise ValueError(
                "Scenario area-demand workbook lacks declared row "
                f"{literature_key!r}"
            )
        used: list[Mapping[str, Any]] = []
        row_index = row_lookup[literature_key]
        for column_index, metric_kind in column_definitions:
            parsed = _parse_area_value(
                frame.iloc[row_index, column_index],
                metric_kind,
            )
            if parsed is None or not parsed["used"]:
                continue
            lower, upper = _quality_bounds(
                configuration,
                metric_kind,
                technology_id,
            )
            if any(
                value < lower or value > upper
                for value in parsed["source_values"]
            ):
                continue
            used.append(parsed)
        if not used:
            raise ValueError(
                "Scenario area-demand workbook has no valid observation for "
                f"{technology_id!r}"
            )
        values = {
            "low_km2_per_twh": min(
                float(item["low"])
                for item in used
                if item["low"] is not None
            ),
            "mid_km2_per_twh": float(
                median(
                    float(item["mid"])
                    for item in used
                    if item["mid"] is not None
                )
            ),
            "high_km2_per_twh": max(
                float(item["high"])
                for item in used
                if item["high"] is not None
            ),
        }
        for area_scenario, factor_column in _TIMES_AREA_FACTOR_COLUMNS.items():
            factor = values[factor_column]
            cap = _factor_cap(
                configuration,
                factor_column,
                technology_id,
                source_id,
                literature_key,
            )
            if cap is not None:
                factor = min(factor, cap)
            factors.append(
                ScenarioAreaFactor(
                    area_demand_scenario=area_scenario,
                    technology_id=technology_id,
                    km2_per_twh=factor,
                )
            )
        produced_technologies.append(technology_id)
    if (
        set(produced_technologies) != set(contract.technology_ids)
        or len(produced_technologies) != len(contract.technology_ids)
    ):
        raise ValueError(
            "Scenario area-demand technology identity drifted from contract"
        )
    factor_by_identity = {
        (item.area_demand_scenario, item.technology_id): item
        for item in factors
    }
    return tuple(
        factor_by_identity[(option.scenario_id, technology_id)]
        for option in contract.area_demand_options
        for technology_id in contract.technology_ids
        if (option.scenario_id, technology_id) in factor_by_identity
    )


def validate_scenario_snapshot_from_contract(
    contract: ScenarioContract,
    snapshot: ScenarioDataSnapshot,
) -> ScenarioDataSnapshot:
    if not isinstance(contract, ScenarioContract):
        raise TypeError("contract must be a ScenarioContract")
    if not isinstance(snapshot, ScenarioDataSnapshot):
        raise TypeError("snapshot must be a ScenarioDataSnapshot")
    if contract.adapter_id == SCENARIO_ADAPTER_CAPACITY:
        from .capacity_scenarios import validate_capacity_snapshot
        return validate_capacity_snapshot(contract, snapshot)
    if snapshot.schema_version != SCENARIO_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Unsupported scenario snapshot schema version")
    if snapshot.source_assets_signature_sha256 != (
        scenario_source_assets_signature(contract.source)
    ):
        raise ValueError("Scenario snapshot drifted from contract source assets")
    declared_technologies = set(contract.technology_ids)
    observed_technologies = {
        item.technology_id for item in snapshot.energy_observations
    }
    if observed_technologies != declared_technologies:
        raise ValueError(
            "Scenario energy technologies differ from the manifest contract"
        )
    for level in contract.planning_levels:
        selected_technologies = {
            item.technology_id
            for item in snapshot.energy_observations
            if item.source_scenario == level.source_scenario
            and item.planning_year == level.planning_year
        }
        if selected_technologies != declared_technologies:
            raise ValueError(
                "Scenario energy observations are incomplete for declared "
                f"planning level {level.scenario_id!r}"
            )
    factor_pairs = {
        (item.area_demand_scenario, item.technology_id)
        for item in snapshot.area_factors
    }
    expected_factor_pairs = {
        (option.scenario_id, technology_id)
        for option in contract.area_demand_options
        for technology_id in contract.technology_ids
    }
    if factor_pairs != expected_factor_pairs or len(snapshot.area_factors) != len(
        expected_factor_pairs
    ):
        raise ValueError(
            "Scenario area-demand factors do not cover the exact manifest matrix"
        )
    return snapshot


def load_normalized_scenario_snapshot_from_paths(
    contract: ScenarioContract,
    *,
    energy_path: Path,
    area_demand_path: Path,
) -> ScenarioDataSnapshot:
    """Load the small canonical JSON adapter without region-specific policy."""

    if contract.adapter_id != SCENARIO_ADAPTER_NORMALIZED_JSON:
        raise NotImplementedError(
            "Normalized snapshot loader requires normalized_json_v1"
        )
    expected_assets = contract.source.assets
    for role, path in {
        "energy_model": energy_path,
        "area_demand": area_demand_path,
    }.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        observed_sha256 = _sha256_path(path)
        if observed_sha256 != expected_assets[role].sha256:
            raise ValueError(f"Normalized scenario {role} checksum drifted")
    energy_raw = _load_json_object(energy_path, "normalized scenario energy asset")
    area_raw = _load_json_object(
        area_demand_path,
        "normalized scenario area-demand asset",
    )
    _exact_keys(
        energy_raw,
        {"schema_version", "observations"},
        "normalized scenario energy asset",
    )
    _exact_keys(
        area_raw,
        {"schema_version", "factors"},
        "normalized scenario area-demand asset",
    )
    if (
        energy_raw["schema_version"] != SCENARIO_SNAPSHOT_SCHEMA_VERSION
        or area_raw["schema_version"] != SCENARIO_SNAPSHOT_SCHEMA_VERSION
    ):
        raise ValueError("Unsupported normalized scenario asset schema version")
    raw_observations = energy_raw["observations"]
    raw_factors = area_raw["factors"]
    if not isinstance(raw_observations, list) or not isinstance(raw_factors, list):
        raise TypeError("Normalized scenario observations and factors must be arrays")
    observations: list[ScenarioEnergyObservation] = []
    for index, value in enumerate(raw_observations):
        item = _mapping(value, f"normalized energy observation {index}")
        _exact_keys(
            item,
            {"source_scenario", "planning_year", "technology_id", "value_twh"},
            f"normalized energy observation {index}",
        )
        observations.append(
            ScenarioEnergyObservation(
                source_scenario=item["source_scenario"],
                planning_year=item["planning_year"],
                technology_id=item["technology_id"],
                value_twh=item["value_twh"],
            )
        )
    factors: list[ScenarioAreaFactor] = []
    for index, value in enumerate(raw_factors):
        item = _mapping(value, f"normalized area factor {index}")
        _exact_keys(
            item,
            {"area_demand_scenario", "technology_id", "km2_per_twh"},
            f"normalized area factor {index}",
        )
        factors.append(
            ScenarioAreaFactor(
                area_demand_scenario=item["area_demand_scenario"],
                technology_id=item["technology_id"],
                km2_per_twh=item["km2_per_twh"],
            )
        )
    snapshot = scenario_data_snapshot(
        source_assets_signature_sha256=scenario_source_assets_signature(
            contract.source
        ),
        energy_observations=tuple(observations),
        area_factors=tuple(factors),
    )
    return validate_scenario_snapshot_from_contract(contract, snapshot)


def load_times_area_demand_scenario_snapshot_from_paths(
    contract: ScenarioContract,
    *,
    energy_path: Path,
    area_demand_path: Path,
) -> ScenarioDataSnapshot:
    """Normalize the manifest-configured TIMES/XLSX adapter into one snapshot."""

    if contract.adapter_id != SCENARIO_ADAPTER_TIMES_AREA_DEMAND:
        raise NotImplementedError(
            "TIMES snapshot loader requires "
            "times_duckdb_area_demand_xlsx_v1"
        )
    expected_assets = contract.source.assets
    paths = {
        "energy_model": Path(energy_path),
        "area_demand": Path(area_demand_path),
    }
    for role, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        if _sha256_path(path) != expected_assets[role].sha256:
            raise ValueError(f"TIMES scenario {role} checksum drifted")
    configuration = contract.adapter_configuration()
    duckdb_configuration = _mapping(
        configuration.get("duckdb"),
        "scenario TIMES DuckDB configuration",
    )
    area_configuration = _mapping(
        configuration.get("area_demand"),
        "scenario TIMES area-demand configuration",
    )
    snapshot = scenario_data_snapshot(
        source_assets_signature_sha256=scenario_source_assets_signature(
            contract.source
        ),
        energy_observations=_load_times_energy_observations(
            contract,
            paths["energy_model"],
            duckdb_configuration,
        ),
        area_factors=_load_times_area_factors(
            contract,
            paths["area_demand"],
            area_configuration,
        ),
    )
    return validate_scenario_snapshot_from_contract(contract, snapshot)


def load_scenario_snapshot_from_paths(
    contract: ScenarioContract,
    *,
    energy_path: Path,
    area_demand_path: Path,
) -> ScenarioDataSnapshot:
    """Dispatch only on the manifest-bound adapter identity."""

    if contract.adapter_id == SCENARIO_ADAPTER_CAPACITY:
        from .capacity_scenarios import load_capacity_snapshot
        if Path(energy_path).resolve() != Path(area_demand_path).resolve():
            raise ValueError("Capacity and area must use the same declared workbook")
        return load_capacity_snapshot(contract, Path(energy_path))
    if contract.adapter_id == SCENARIO_ADAPTER_NORMALIZED_JSON:
        return load_normalized_scenario_snapshot_from_paths(
            contract,
            energy_path=Path(energy_path),
            area_demand_path=Path(area_demand_path),
        )
    if contract.adapter_id == SCENARIO_ADAPTER_TIMES_AREA_DEMAND:
        return load_times_area_demand_scenario_snapshot_from_paths(
            contract,
            energy_path=Path(energy_path),
            area_demand_path=Path(area_demand_path),
        )
    raise NotImplementedError(
        f"Unsupported scenario adapter: {contract.adapter_id}"
    )


def run_scenario_request(
    contract: ScenarioContract,
    request: ScenarioRequest,
    snapshot: ScenarioDataSnapshot,
) -> ScenarioResult:
    """Execute one deterministic technology-energy/area scenario."""

    validate_scenario_request_from_contract(contract, request)
    validate_scenario_snapshot_from_contract(contract, snapshot)
    if (
        snapshot.source_assets_signature_sha256
        != request.source_assets_signature_sha256
    ):
        raise ValueError("Scenario snapshot is not bound to the request assets")

    if contract.adapter_id == SCENARIO_ADAPTER_CAPACITY:
        from .capacity_scenarios import capacity_technology_results
        rows = capacity_technology_results(contract, request, snapshot)
    else:
        selected = tuple(
            item
            for item in snapshot.energy_observations
            if item.source_scenario == request.source_scenario
            and item.planning_year == request.planning_year
        )
        if not selected:
            raise ValueError(
                "Scenario energy source has no observations for the requested "
                "source scenario and planning year"
            )
        unexpected_technologies = {
            item.technology_id for item in selected
        }.difference(contract.technology_ids)
        if unexpected_technologies:
            raise ValueError(
                "Scenario energy source contains undeclared technologies: "
                + ", ".join(sorted(unexpected_technologies))
            )
        factor_by_technology = {
            item.technology_id: item.km2_per_twh
            for item in snapshot.area_factors
            if item.area_demand_scenario == request.area_demand_scenario
        }
        source_energies: list[TechnologyEnergy] = []
        for technology_id in contract.technology_ids:
            matching = tuple(
                item for item in selected if item.technology_id == technology_id
            )
            if not matching:
                raise ValueError(
                    f"Scenario energy source lacks technology {technology_id!r}"
                )
            if technology_id not in factor_by_technology:
                raise ValueError(
                    "Scenario area-demand source lacks factor for "
                    f"{request.area_demand_scenario!r}/{technology_id!r}"
                )
            source_energies.append(
                TechnologyEnergy(
                    technology=technology_id,
                    twh=(
                        math.fsum(item.value_twh for item in matching)
                        * request.energy_scale
                    ),
                )
            )
        mix = rebalance_energy_mix(
            tuple(source_energies),
            {
                item.technology_id: item.share_pct
                for item in request.technology_shares
            },
        )
        rows: list[ScenarioTechnologyResult] = []
        for technology_id in contract.technology_ids:
            energy_twh = mix.energy_twh(technology_id)
            factor = factor_by_technology[technology_id]
            rows.append(
                ScenarioTechnologyResult(
                    technology_id=technology_id,
                    energy_twh=energy_twh,
                    km2_per_twh=factor,
                    area_need_km2=energy_twh * factor,
                )
            )
    level = contract.planning_level(request.scenario_id)
    result = ScenarioResult(
        schema_version=SCENARIO_RESULT_SCHEMA_VERSION,
        request=request,
        scenario_label=level.label,
        source_status=contract.source.status,
        source_dataset_id=contract.source.source_dataset_id,
        source_label=contract.source.source_label,
        allowed_use=contract.source.allowed_use,
        regional_acceptance=contract.source.regional_acceptance,
        warning_by_language=tuple(
            (language, contract.source.warning_by_language[language])
            for language in sorted(contract.source.warning_by_language)
        ),
        technologies=tuple(rows),
        total_energy_twh=(None if contract.adapter_id == SCENARIO_ADAPTER_CAPACITY
                          else math.fsum(item.energy_twh for item in rows)),
        total_area_need_km2=math.fsum(item.area_need_km2 for item in rows),
    )
    return validate_scenario_result_from_contract(
        contract,
        parse_scenario_result(result.as_dict()),
    )


def parse_scenario_result(value: Mapping[str, Any]) -> ScenarioResult:
    raw = _mapping(value, "scenario result")
    _exact_keys(
        raw,
        {
            "schema_version",
            "request",
            "scenario_label",
            "source_status",
            "source_dataset_id",
            "source_label",
            "allowed_use",
            "regional_acceptance",
            "warning_by_language",
            "technologies",
            "total_energy_twh",
            "total_area_need_km2",
        },
        "scenario result",
    )
    if raw["schema_version"] != SCENARIO_RESULT_SCHEMA_VERSION:
        raise ValueError("Unsupported scenario result schema version")
    request = parse_scenario_request(
        _mapping(raw["request"], "scenario result request")
    )
    capacity = request.adapter_id == SCENARIO_ADAPTER_CAPACITY
    status = _text(raw["source_status"], "scenario result source status")
    allowed_use = _text(raw["allowed_use"], "scenario result allowed use")
    if status not in SUPPORTED_SCENARIO_SOURCE_STATUSES:
        raise ValueError("Scenario result source status is unsupported")
    if allowed_use not in SUPPORTED_SCENARIO_USES:
        raise ValueError("Scenario result allowed use is unsupported")
    regional_acceptance = raw["regional_acceptance"]
    if not isinstance(regional_acceptance, bool):
        raise TypeError("Scenario result regional_acceptance must be boolean")
    if status == "provisional_fallback" and (
        regional_acceptance or allowed_use != "planning_exploration_only"
    ):
        raise ValueError("Provisional scenario result cannot claim acceptance")
    if status == "accepted_regional" and (
        not regional_acceptance or allowed_use != "regional_planning"
    ):
        raise ValueError("Accepted scenario result requires regional acceptance")
    raw_warnings = _mapping(
        raw["warning_by_language"],
        "scenario result warnings",
    )
    if set(raw_warnings) != REQUIRED_DISPLAY_LANGUAGES:
        raise ValueError("Scenario result warnings must cover every language")
    warnings = tuple(
        (language, _text(raw_warnings[language], f"scenario warning {language}"))
        for language in sorted(raw_warnings)
    )
    raw_rows = raw["technologies"]
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError("Scenario result needs technology rows")
    technologies: list[ScenarioTechnologyResult] = []
    for index, value in enumerate(raw_rows):
        item = _mapping(value, f"scenario result technology {index}")
        _exact_keys(
            item,
            ({"technology_id", "energy_twh", "km2_per_twh", "area_need_km2"}
             | ({"capacity_mw", "km2_per_mw"} if capacity else set())),
            f"scenario result technology {index}",
        )
        if capacity:
            if item["energy_twh"] is not None or item["km2_per_twh"] is not None:
                raise ValueError("Capacity result must leave production unknown")
            energy_twh = factor = None
            mw = _non_negative_number(item["capacity_mw"], "capacity MW")
            mw_factor = _positive_number(item["km2_per_mw"], "km2/MW")
        else:
            energy_twh = _non_negative_number(
                item["energy_twh"],
                f"scenario result technology {index} TWh",
            )
            factor = _positive_number(
                item["km2_per_twh"],
                f"scenario result technology {index} km2/TWh",
            )
        area_need = _non_negative_number(
            item["area_need_km2"],
            f"scenario result technology {index} area",
        )
        if not math.isclose(
            area_need,
            mw * mw_factor if capacity else energy_twh * factor,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("Scenario result area does not equal energy * factor")
        technologies.append(
            ScenarioTechnologyResult(
                technology_id=_identifier(
                    item["technology_id"],
                    f"scenario result technology {index} id",
                ),
                energy_twh=energy_twh,
                km2_per_twh=factor,
                area_need_km2=area_need,
                capacity_mw=mw if capacity else None,
                km2_per_mw=mw_factor if capacity else None,
            )
        )
    if len({item.technology_id for item in technologies}) != len(technologies):
        raise ValueError("Scenario result technology ids must be unique")
    if request.capacity_mw_by_technology is not None and (
        dict(request.capacity_mw_by_technology)
        != {item.technology_id: item.capacity_mw for item in technologies}
    ):
        raise ValueError("Scenario result capacity differs from requested MW")
    if capacity:
        if raw["total_energy_twh"] is not None:
            raise ValueError("Capacity result must not invent total production")
        total_energy = None
    else:
        total_energy = _non_negative_number(
            raw["total_energy_twh"],
            "scenario result total energy",
        )
    total_area = _non_negative_number(
        raw["total_area_need_km2"],
        "scenario result total area",
    )
    if (not capacity and not math.isclose(
        total_energy,
        math.fsum(item.energy_twh for item in technologies),
        rel_tol=1e-12,
        abs_tol=1e-12,
    )) or not math.isclose(
        total_area,
        math.fsum(item.area_need_km2 for item in technologies),
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise ValueError("Scenario result totals drifted from technology rows")
    return ScenarioResult(
        schema_version=SCENARIO_RESULT_SCHEMA_VERSION,
        request=request,
        scenario_label=_text(raw["scenario_label"], "scenario result label"),
        source_status=status,
        source_dataset_id=_identifier(
            raw["source_dataset_id"],
            "scenario result source dataset id",
        ),
        source_label=_text(raw["source_label"], "scenario result source label"),
        allowed_use=allowed_use,
        regional_acceptance=regional_acceptance,
        warning_by_language=warnings,
        technologies=tuple(technologies),
        total_energy_twh=total_energy,
        total_area_need_km2=total_area,
    )


def validate_scenario_result_from_contract(
    contract: ScenarioContract,
    result: ScenarioResult,
) -> ScenarioResult:
    """Bind a persisted result to the exact manifest and request identities."""

    if not isinstance(contract, ScenarioContract):
        raise TypeError("contract must be a ScenarioContract")
    if not isinstance(result, ScenarioResult):
        raise TypeError("result must be a ScenarioResult")
    validate_scenario_request_from_contract(contract, result.request)
    level = contract.planning_level(result.request.scenario_id)
    expected_warnings = tuple(
        (language, contract.source.warning_by_language[language])
        for language in sorted(contract.source.warning_by_language)
    )
    if (
        result.scenario_label != level.label
        or result.source_status != contract.source.status
        or result.source_dataset_id != contract.source.source_dataset_id
        or result.source_label != contract.source.source_label
        or result.allowed_use != contract.source.allowed_use
        or result.regional_acceptance != contract.source.regional_acceptance
        or result.warning_by_language != expected_warnings
    ):
        raise ValueError("Scenario result trust or provenance drifted from contract")
    if tuple(item.technology_id for item in result.technologies) != (
        contract.technology_ids
    ):
        raise ValueError(
            "Scenario result technology identity or order drifted from contract"
        )
    return result


def load_catalog_scenario_contract(region_id: str) -> ScenarioContract:
    normalized = _identifier(region_id, "scenario catalog region")
    from .catalogs import load_scenario_manifest

    contract = scenario_contract(load_scenario_manifest(normalized))
    if contract.region_id != normalized:
        raise ValueError("Scenario catalog contract region identity drifted")
    return contract


def build_catalog_scenario_request(
    region_id: str,
    **kwargs: Any,
) -> ScenarioRequest:
    return build_scenario_request_from_contract(
        load_catalog_scenario_contract(region_id),
        **kwargs,
    )


def _load_catalog_scenario_snapshot(
    contract: ScenarioContract,
) -> ScenarioDataSnapshot:
    from .context_runtime import catalog_context_runtime_declared, load_catalog_context_inputs

    if catalog_context_runtime_declared(contract.region_id):
        return load_catalog_context_inputs(contract.region_id).scenario
    from .paths import resolve_source_path

    energy_asset = contract.source.assets["energy_model"]
    area_asset = contract.source.assets["area_demand"]
    return load_scenario_snapshot_from_paths(
        contract,
        energy_path=resolve_source_path(
            contract.source.provider,
            energy_asset.path,
        ),
        area_demand_path=resolve_source_path(
            contract.source.provider,
            area_asset.path,
        ),
    )


def load_catalog_scenario_snapshot(region_id: str) -> ScenarioDataSnapshot:
    return _load_catalog_scenario_snapshot(
        load_catalog_scenario_contract(region_id)
    )


def _authorize_catalog_scenario_request(
    contract: ScenarioContract,
    request: ScenarioRequest,
) -> ScenarioRequest:
    validate_scenario_request_from_contract(contract, request)
    from .access_policy import validate_product_access_dimensions
    from .catalogs import load_region
    from .workspace import load_review_access, load_workspace_profile

    region = load_region(request.region_id)
    if str(region.get("region_id") or "").strip().lower() != request.region_id:
        raise PermissionError("Scenario request region is not catalog-authorized")
    profile = load_workspace_profile(request.region_id)
    if request.capability_id not in profile.capabilities:
        raise PermissionError("Scenario capability is not declared by the workspace")
    scope_kind, scope_region_id = request.access_scope.split(":", 1)
    if scope_region_id != request.region_id:
        raise PermissionError("Scenario request scope belongs to another region")
    if scope_kind == "product":
        landing_card = region.get("landing_card")
        behavior_reference = region.get("behavior_reference")
        if not isinstance(landing_card, Mapping) or not isinstance(
            behavior_reference,
            Mapping,
        ):
            raise PermissionError(
                f"Product scenario access is disabled for {request.region_id}"
            )
        try:
            validate_product_access_dimensions(
                lifecycle=region.get("status"),
                behavior_reference_status=behavior_reference.get("status"),
                landing_card_enabled=landing_card.get("enabled"),
            )
        except (TypeError, ValueError) as exc:
            raise PermissionError(
                f"Product scenario access is disabled for {request.region_id}"
            ) from exc
        return request
    if scope_kind != "review":
        raise PermissionError(f"Unsupported scenario access mode: {scope_kind}")
    try:
        access = load_review_access(request.region_id)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        raise PermissionError(
            f"Review scenario access is disabled for {request.region_id}"
        ) from exc
    if (
        access.mode != "review"
        or access.surface != "shared_workspace"
        or access.requires_environment_allowlist is not True
        or request.capability_id not in access.allowed_capabilities
    ):
        raise PermissionError("Scenario capability is not allowed by review access")
    return request


def run_catalog_scenario_request(request: ScenarioRequest) -> ScenarioResult:
    if not isinstance(request, ScenarioRequest):
        raise TypeError("request must be a ScenarioRequest")
    contract = load_catalog_scenario_contract(request.region_id)
    _authorize_catalog_scenario_request(contract, request)
    return run_scenario_request(
        contract,
        request,
        _load_catalog_scenario_snapshot(contract),
    )


__all__ = [
    "REQUIRED_DISPLAY_LANGUAGES",
    "SCENARIO_ACCESS_SCOPE_KINDS",
    "SCENARIO_ADAPTER_NORMALIZED_JSON",
    "SCENARIO_ADAPTER_TIMES_AREA_DEMAND",
    "SCENARIO_CAPABILITY_ID",
    "SCENARIO_CONTRACT_SCHEMA_VERSION",
    "SCENARIO_REQUEST_SCHEMA_VERSION",
    "SCENARIO_RESULT_SCHEMA_VERSION",
    "SCENARIO_SNAPSHOT_SCHEMA_VERSION",
    "SUPPORTED_SCENARIO_ADAPTERS",
    "SUPPORTED_SCENARIO_SOURCE_STATUSES",
    "SUPPORTED_SCENARIO_USES",
    "ScenarioAreaFactor",
    "ScenarioAreaDemandOption",
    "ScenarioContract",
    "ScenarioDataSnapshot",
    "ScenarioEnergyObservation",
    "ScenarioPlanningLevel",
    "ScenarioRequest",
    "ScenarioResult",
    "ScenarioSourceAsset",
    "ScenarioSourceContract",
    "ScenarioTechnologyShare",
    "ScenarioTechnologyResult",
    "build_catalog_scenario_request",
    "build_scenario_request_from_contract",
    "load_catalog_scenario_contract",
    "load_catalog_scenario_snapshot",
    "load_normalized_scenario_snapshot_from_paths",
    "load_scenario_snapshot_from_paths",
    "load_times_area_demand_scenario_snapshot_from_paths",
    "parse_scenario_request",
    "parse_scenario_result",
    "run_catalog_scenario_request",
    "run_scenario_request",
    "scenario_contract",
    "scenario_contract_signature",
    "scenario_data_snapshot",
    "scenario_source_assets_signature",
    "scenario_source_contract",
    "validate_scenario_request_from_contract",
    "validate_scenario_result_from_contract",
    "validate_scenario_snapshot_from_contract",
]
