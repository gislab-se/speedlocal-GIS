from __future__ import annotations

from collections import namedtuple
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field, fields
import csv
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from threading import get_ident
from typing import Any, Mapping, Protocol

import h3

from .paths import resolve_source_path


SUPPORTED_ACCEPTANCE_SOURCE_STATUSES = {
    "accepted_regional",
    "provisional_fallback",
}
SUPPORTED_ACCEPTANCE_USES = {
    "regional_planning",
    "behavior_exploration_only",
}
SUPPORTED_IMPACT_MODELS = {"linear_acceptance_weight"}
SUPPORTED_ALLOCATION_PRIORITY_MODELS = {"linear_acceptance_blend"}
SUPPORTED_MISSING_CONTEXT_POLICIES = {"exclude_when_applied"}
SUPPORTED_ALLOCATION_MISSING_POLICIES = {"exclude_when_prioritized"}
REQUIRED_ACCEPTANCE_ASSET_ROLES = {"acceptance_values", "display_geometry"}
REQUIRED_DISPLAY_LANGUAGES = {"sv", "en", "da_no"}
AVAILABLE_ACCEPTANCE_DATA_STATUSES = {
    "measured",
    "observed",
    "synthetic",
}
SOCIAL_ACCEPTANCE_CAPABILITY_ID = "workspace.social_acceptance"
SOCIAL_ACCEPTANCE_CONTRACT_SCHEMA_VERSION = "1.0"
SOCIAL_ACCEPTANCE_REQUEST_SCHEMA_VERSION = "1.0"
SOCIAL_ACCEPTANCE_RESULT_SCHEMA_VERSION = "1.0"
SOCIAL_ACCEPTANCE_SNAPSHOT_SCHEMA_VERSION = "1.0"
SOCIAL_ACCEPTANCE_ACCESS_SCOPE_KINDS = ("product", "review")
SOCIAL_ACCEPTANCE_ROLLUP_RULE = "mean_by_source_cell"
SOCIAL_ACCEPTANCE_COMPILED_STATUS = "compiled_unvalidated"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _required_text(raw: dict[str, Any], key: str, context: str) -> str:
    value = str(raw.get(key) or "").strip()
    if not value:
        raise ValueError(f"{context} {key} is required")
    return value


def _required_positive_int(
    raw: dict[str, Any],
    key: str,
    context: str,
    *,
    allow_zero: bool = False,
) -> int:
    try:
        value = int(raw.get(key))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} {key} must be an integer") from exc
    minimum = 0 if allow_zero else 1
    if value < minimum:
        raise ValueError(f"{context} {key} must be at least {minimum}")
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
class SocialAcceptanceAsset:
    role: str
    path: str
    sha256: str


@dataclass(frozen=True)
class SocialAcceptanceCoverageContract:
    scope: str
    source_hex_count: int
    target_support_hex_count: int
    unassessed_support_hex_count: int


@dataclass(frozen=True)
class SocialAcceptanceBehaviorContract:
    impact_model: str
    allocation_priority_model: str
    low_threshold: float
    high_threshold: float
    missing_context_policy: str
    allocation_missing_context_policy: str


@dataclass(frozen=True)
class SocialAcceptanceSourceContract:
    schema_version: str
    status: str
    intended_region_id: str
    source_region_id: str
    source_dataset_id: str
    source_label: str
    provider: str
    regional_acceptance: bool
    allowed_use: str
    synthetic: bool
    method_id: str
    provenance: str
    limitation: str
    replacement_condition: str
    warning_by_language: dict[str, str]
    assets: dict[str, SocialAcceptanceAsset]
    coverage: SocialAcceptanceCoverageContract
    behavior: SocialAcceptanceBehaviorContract

    @property
    def is_provisional(self) -> bool:
        return self.status == "provisional_fallback"

    @property
    def value_data_status(self) -> str:
        return "synthetic" if self.synthetic else "observed"

    def warning(self, language: str) -> str:
        return self.warning_by_language.get(
            str(language),
            self.warning_by_language["sv"],
        )


def social_acceptance_source_contract(
    manifest: dict[str, Any] | None,
) -> SocialAcceptanceSourceContract:
    raw_manifest = manifest or {}
    raw = raw_manifest.get("source_contract")
    if not isinstance(raw, dict):
        raise ValueError("Social-acceptance manifest source_contract is required")

    context = "Social-acceptance source contract"
    schema_version = _required_text(raw, "schema_version", context)
    if schema_version != "1.0":
        raise ValueError(
            "Unsupported social-acceptance source schema version: "
            f"{schema_version}"
        )

    status = _required_text(raw, "status", context)
    if status not in SUPPORTED_ACCEPTANCE_SOURCE_STATUSES:
        raise ValueError(f"Unsupported social-acceptance source status: {status}")
    if str(raw_manifest.get("status") or "").strip() != status:
        raise ValueError(
            "Social-acceptance manifest status must match source_contract status"
        )

    intended_region_id = _required_text(raw, "intended_region_id", context)
    if str(raw_manifest.get("region_id") or "").strip() != intended_region_id:
        raise ValueError(
            "Social-acceptance intended_region_id must match manifest region_id"
        )

    source_region_id = _required_text(raw, "source_region_id", context)
    source_dataset_id = _required_text(raw, "source_dataset_id", context)
    source_label = _required_text(raw, "source_label", context)
    provider = _required_text(raw, "provider", context)
    allowed_use = _required_text(raw, "allowed_use", context)
    if allowed_use not in SUPPORTED_ACCEPTANCE_USES:
        raise ValueError(
            f"Unsupported social-acceptance allowed_use: {allowed_use}"
        )

    regional_acceptance = raw.get("regional_acceptance")
    if not isinstance(regional_acceptance, bool):
        raise ValueError(
            "Social-acceptance regional_acceptance must be a boolean"
        )
    synthetic = raw.get("synthetic")
    if not isinstance(synthetic, bool):
        raise ValueError("Social-acceptance synthetic must be a boolean")
    if raw_manifest.get("synthetic") is not synthetic:
        raise ValueError(
            "Social-acceptance manifest synthetic must match source_contract"
        )

    method_id = _required_text(raw, "method_id", context)
    provenance = _required_text(raw, "provenance", context)
    limitation = _required_text(raw, "limitation", context)
    replacement_condition = _required_text(raw, "replacement_condition", context)

    if status == "accepted_regional":
        if synthetic:
            raise ValueError(
                "Accepted regional social acceptance cannot be synthetic"
            )
        if not regional_acceptance or allowed_use != "regional_planning":
            raise ValueError(
                "Accepted social acceptance requires regional acceptance and "
                "regional_planning use"
            )
    else:
        if regional_acceptance:
            raise ValueError(
                "A provisional social-acceptance fallback cannot claim "
                "regional acceptance"
            )
        if allowed_use != "behavior_exploration_only":
            raise ValueError(
                "A provisional social-acceptance fallback is limited to "
                "behavior exploration"
            )

    raw_warnings = raw.get("display_warning")
    if not isinstance(raw_warnings, dict):
        raise ValueError("Social-acceptance display_warning is required")
    warning_by_language = {
        str(language): str(message).strip()
        for language, message in raw_warnings.items()
        if str(message).strip()
    }
    missing_languages = REQUIRED_DISPLAY_LANGUAGES - set(warning_by_language)
    if missing_languages:
        raise ValueError(
            "Social-acceptance display_warning is missing languages: "
            + ", ".join(sorted(missing_languages))
        )

    raw_assets = raw.get("assets")
    if not isinstance(raw_assets, dict):
        raise ValueError("Social-acceptance source assets are required")
    assets: dict[str, SocialAcceptanceAsset] = {}
    for role, item in raw_assets.items():
        role_text = str(role).strip()
        if not isinstance(item, dict):
            raise ValueError(
                f"Social-acceptance asset {role_text} must be an object"
            )
        path = _required_text(
            item,
            "path",
            f"Social-acceptance asset {role_text}",
        )
        sha256 = _required_text(
            item,
            "sha256",
            f"Social-acceptance asset {role_text}",
        )
        if not _is_safe_provider_path(path):
            raise ValueError(
                f"Social-acceptance asset {role_text} path must be "
                "provider-relative"
            )
        if not _is_lower_sha256(sha256):
            raise ValueError(
                f"Social-acceptance asset {role_text} sha256 is invalid"
            )
        assets[role_text] = SocialAcceptanceAsset(
            role=role_text,
            path=path,
            sha256=sha256,
        )
    missing_roles = REQUIRED_ACCEPTANCE_ASSET_ROLES - set(assets)
    if missing_roles:
        raise ValueError(
            "Social-acceptance assets are missing roles: "
            + ", ".join(sorted(missing_roles))
        )

    configured_paths = {
        "acceptance_values": str(
            raw_manifest.get("acceptance_csv") or ""
        ).strip(),
        "display_geometry": str(
            raw_manifest.get("hex_geometry_path") or ""
        ).strip(),
    }
    for role, configured_path in configured_paths.items():
        if configured_path != assets[role].path:
            raise ValueError(
                f"Social-acceptance {role} path must match source asset"
            )
    source_geometry = str(
        raw_manifest.get("source_hex_geojson") or ""
    ).strip()
    if source_geometry != assets["display_geometry"].path:
        raise ValueError(
            "Social-acceptance source_hex_geojson must match display geometry"
        )

    coverage_raw = raw_manifest.get("coverage_contract")
    if not isinstance(coverage_raw, dict):
        raise ValueError("Social-acceptance coverage_contract is required")
    coverage = SocialAcceptanceCoverageContract(
        scope=_required_text(
            coverage_raw,
            "scope",
            "Social-acceptance coverage contract",
        ),
        source_hex_count=_required_positive_int(
            coverage_raw,
            "source_hex_count",
            "Social-acceptance coverage contract",
        ),
        target_support_hex_count=_required_positive_int(
            coverage_raw,
            "target_support_hex_count",
            "Social-acceptance coverage contract",
        ),
        unassessed_support_hex_count=_required_positive_int(
            coverage_raw,
            "unassessed_support_hex_count",
            "Social-acceptance coverage contract",
            allow_zero=True,
        ),
    )
    if (
        coverage.source_hex_count + coverage.unassessed_support_hex_count
        != coverage.target_support_hex_count
    ):
        raise ValueError(
            "Social-acceptance coverage counts must reconcile to the target "
            "support domain"
        )

    behavior_raw = raw_manifest.get("behavior_contract")
    if not isinstance(behavior_raw, dict):
        raise ValueError("Social-acceptance behavior_contract is required")
    impact_model = _required_text(
        behavior_raw,
        "impact_model",
        "Social-acceptance behavior contract",
    )
    if impact_model not in SUPPORTED_IMPACT_MODELS:
        raise ValueError(f"Unsupported social-acceptance impact model: {impact_model}")
    allocation_priority_model = _required_text(
        behavior_raw,
        "allocation_priority_model",
        "Social-acceptance behavior contract",
    )
    if (
        allocation_priority_model
        not in SUPPORTED_ALLOCATION_PRIORITY_MODELS
    ):
        raise ValueError(
            "Unsupported social-acceptance allocation priority model: "
            f"{allocation_priority_model}"
        )
    try:
        low_threshold = float(behavior_raw.get("low_threshold"))
        high_threshold = float(behavior_raw.get("high_threshold"))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Social-acceptance thresholds must be numeric"
        ) from exc
    if not 0.0 <= low_threshold < high_threshold <= 1.0:
        raise ValueError(
            "Social-acceptance thresholds must satisfy 0 <= low < high <= 1"
        )
    missing_context_policy = _required_text(
        behavior_raw,
        "missing_context_policy",
        "Social-acceptance behavior contract",
    )
    if missing_context_policy not in SUPPORTED_MISSING_CONTEXT_POLICIES:
        raise ValueError(
            "Unsupported social-acceptance missing-context policy: "
            f"{missing_context_policy}"
        )
    allocation_missing_context_policy = _required_text(
        behavior_raw,
        "allocation_missing_context_policy",
        "Social-acceptance behavior contract",
    )
    if (
        allocation_missing_context_policy
        not in SUPPORTED_ALLOCATION_MISSING_POLICIES
    ):
        raise ValueError(
            "Unsupported social-acceptance allocation missing-context policy: "
            f"{allocation_missing_context_policy}"
        )
    behavior = SocialAcceptanceBehaviorContract(
        impact_model=impact_model,
        allocation_priority_model=allocation_priority_model,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        missing_context_policy=missing_context_policy,
        allocation_missing_context_policy=allocation_missing_context_policy,
    )

    hex_resolution = _required_positive_int(
        raw_manifest,
        "hex_resolution",
        "Social-acceptance manifest",
    )
    if hex_resolution > 15:
        raise ValueError("Social-acceptance H3 resolution is invalid")
    levels = tuple(
        str(value).strip()
        for value in raw_manifest.get("scenario_levels") or []
        if str(value).strip()
    )
    scenarios = raw_manifest.get("scenarios") or []
    if not isinstance(scenarios, list):
        raise ValueError("Social-acceptance scenarios must be a list")
    scenario_ids: list[str] = []
    value_columns: list[str] = []
    for item in scenarios:
        if not isinstance(item, dict):
            raise ValueError("Social-acceptance scenario entries must be objects")
        scenario_ids.append(
            _required_text(item, "id", "Social-acceptance scenario")
        )
        _required_text(item, "label", "Social-acceptance scenario")
        value_columns.append(
            _required_text(
                item,
                "value_column",
                "Social-acceptance scenario",
            )
        )
    if (
        not levels
        or levels != tuple(scenario_ids)
        or len(set(scenario_ids)) != len(scenario_ids)
        or len(set(value_columns)) != len(value_columns)
    ):
        raise ValueError(
            "Social-acceptance scenario levels, ids, and value columns must be "
            "unique and ordered consistently"
        )
    if str(raw_manifest.get("default_scenario") or "") not in scenario_ids:
        raise ValueError(
            "Social-acceptance default_scenario must be a declared level"
        )
    value_range = raw_manifest.get("value_range")
    if value_range != [0, 1]:
        raise ValueError("Social-acceptance value_range must be [0, 1]")
    max_decimals = _required_positive_int(
        raw_manifest,
        "max_decimals",
        "Social-acceptance manifest",
        allow_zero=True,
    )
    if max_decimals > 6:
        raise ValueError("Social-acceptance max_decimals must be at most 6")

    return SocialAcceptanceSourceContract(
        schema_version=schema_version,
        status=status,
        intended_region_id=intended_region_id,
        source_region_id=source_region_id,
        source_dataset_id=source_dataset_id,
        source_label=source_label,
        provider=provider,
        regional_acceptance=regional_acceptance,
        allowed_use=allowed_use,
        synthetic=synthetic,
        method_id=method_id,
        provenance=provenance,
        limitation=limitation,
        replacement_condition=replacement_condition,
        warning_by_language=warning_by_language,
        assets=assets,
        coverage=coverage,
        behavior=behavior,
    )


def social_acceptance_asset_paths(
    manifest: dict[str, Any],
    *,
    verify_checksums: bool = False,
) -> dict[str, Path]:
    contract = social_acceptance_source_contract(manifest)
    paths: dict[str, Path] = {}
    for role, asset in contract.assets.items():
        path = social_acceptance_asset_path(manifest, role)
        if verify_checksums:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != asset.sha256:
                raise ValueError(
                    f"Social-acceptance asset {role} checksum drifted: {path}"
                )
        paths[role] = path
    return paths


def social_acceptance_asset_path(
    manifest: dict[str, Any],
    role: str,
) -> Path:
    contract = social_acceptance_source_contract(manifest)
    role_text = str(role).strip()
    asset = contract.assets.get(role_text)
    if asset is None:
        raise KeyError(f"Social-acceptance asset role is not declared: {role_text}")
    path = resolve_source_path(contract.provider, asset.path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Social-acceptance asset {role_text} does not exist: {path}"
        )
    return path


def social_acceptance_data_status_is_available(value: Any) -> bool:
    return str(value or "").strip() in AVAILABLE_ACCEPTANCE_DATA_STATUSES


@dataclass(frozen=True)
class SocialAcceptanceScenario:
    scenario_id: str
    label: str
    value_column: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "label": self.label,
            "value_column": self.value_column,
        }


@dataclass(frozen=True)
class SocialAcceptanceControl:
    parameter_id: str
    minimum: float
    maximum: float
    step: float
    technical_initial_value: float
    recommendation_state: str
    recommendation_reason: str


@dataclass(frozen=True)
class SocialAcceptanceContract:
    schema_version: str
    region_id: str
    acceptance_id: str
    display_name: str
    source: SocialAcceptanceSourceContract
    source_resolution: int
    rollup_resolutions: tuple[int, ...]
    rollup_rule: str
    scenarios: tuple[SocialAcceptanceScenario, ...]
    default_scenario_id: str
    impact_control: SocialAcceptanceControl
    allocation_priority_control: SocialAcceptanceControl
    value_minimum: float
    value_maximum: float
    max_decimals: int
    random_seed: int | None
    method_note: str

    def scenario(self, scenario_id: str) -> SocialAcceptanceScenario:
        normalized = _exact_identifier(scenario_id, "social-acceptance scenario id")
        try:
            return next(
                item for item in self.scenarios if item.scenario_id == normalized
            )
        except StopIteration as exc:
            raise KeyError(
                f"Unknown social-acceptance scenario: {normalized}"
            ) from exc


@dataclass(frozen=True)
class SocialAcceptanceRequest:
    schema_version: str
    access_scope: str
    capability_id: str
    region_id: str
    acceptance_id: str
    scenario_id: str
    value_column: str
    source_resolution: int
    target_resolution: int
    layer_visible: bool
    impact_pct: float
    allocation_priority_pct: float
    source_assets_signature_sha256: str
    contract_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SocialAcceptanceObservation:
    cell_id: str
    source_resolution: int
    data_status: str
    method_version: str
    scenario_values: tuple[tuple[str, float], ...]

    def value(self, scenario_id: str) -> float:
        try:
            return dict(self.scenario_values)[scenario_id]
        except KeyError as exc:
            raise KeyError(
                f"Social-acceptance observation lacks scenario {scenario_id!r}"
            ) from exc


@dataclass(frozen=True)
class SocialAcceptanceSnapshot:
    schema_version: str
    source_assets_signature_sha256: str
    observations: tuple[SocialAcceptanceObservation, ...]


@dataclass(frozen=True)
class SocialAcceptanceCellResult:
    cell_id: str
    acceptance_value: float
    potential_weight: float
    source_child_count: int
    data_status: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SocialAcceptanceResult:
    schema_version: str
    request: SocialAcceptanceRequest
    scenario_label: str
    source_status: str
    source_dataset_id: str
    source_label: str
    allowed_use: str
    synthetic: bool
    regional_acceptance: bool
    warning_by_language: tuple[tuple[str, str], ...]
    provenance: str
    limitation: str
    replacement_condition: str
    value_data_status: str
    missing_context_policy: str
    allocation_priority_model: str
    allocation_missing_context_policy: str
    low_threshold: float
    high_threshold: float
    method_note: str
    coverage_source_hex_count: int
    coverage_target_support_hex_count: int
    coverage_unassessed_support_hex_count: int
    assessed_cell_count: int
    low_acceptance_cell_count: int
    high_acceptance_cell_count: int
    minimum_acceptance: float
    maximum_acceptance: float
    mean_acceptance: float
    median_acceptance: float
    cells: tuple[SocialAcceptanceCellResult, ...]

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
            "synthetic": self.synthetic,
            "regional_acceptance": self.regional_acceptance,
            "warning_by_language": dict(self.warning_by_language),
            "provenance": self.provenance,
            "limitation": self.limitation,
            "replacement_condition": self.replacement_condition,
            "value_data_status": self.value_data_status,
            "missing_context_policy": self.missing_context_policy,
            "allocation_priority_model": self.allocation_priority_model,
            "allocation_missing_context_policy": (
                self.allocation_missing_context_policy
            ),
            "low_threshold": self.low_threshold,
            "high_threshold": self.high_threshold,
            "method_note": self.method_note,
            "coverage_source_hex_count": self.coverage_source_hex_count,
            "coverage_target_support_hex_count": (
                self.coverage_target_support_hex_count
            ),
            "coverage_unassessed_support_hex_count": (
                self.coverage_unassessed_support_hex_count
            ),
            "assessed_cell_count": self.assessed_cell_count,
            "low_acceptance_cell_count": self.low_acceptance_cell_count,
            "high_acceptance_cell_count": self.high_acceptance_cell_count,
            "minimum_acceptance": self.minimum_acceptance,
            "maximum_acceptance": self.maximum_acceptance,
            "mean_acceptance": self.mean_acceptance,
            "median_acceptance": self.median_acceptance,
            "cells": [cell.as_dict() for cell in self.cells],
        }


@dataclass(frozen=True)
class SocialAcceptanceProbe:
    state: str
    detail: str


class ResolvedSocialAcceptanceAsset(Protocol):
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


def _exact_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be an exact non-empty string")
    return value


def _exact_identifier(value: Any, label: str) -> str:
    text = _exact_text(value, label)
    if _IDENTIFIER.fullmatch(text) is None:
        raise ValueError(f"{label} must be a canonical identifier")
    return text


def _exact_sha256(value: Any, label: str) -> str:
    text = _exact_text(value, label)
    if _SHA256.fullmatch(text) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _h3_resolution(value: Any, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 15
    ):
        raise ValueError(f"{label} must be an H3 integer from 0 to 15")
    return value


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
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


def _control_contract(value: Any, parameter_id: str) -> SocialAcceptanceControl:
    raw = _mapping(value, f"social-acceptance control {parameter_id}")
    _exact_keys(
        raw,
        {
            "type",
            "unit",
            "minimum",
            "maximum",
            "step",
            "technical_initial_value",
            "accepted_recommended_default",
        },
        f"social-acceptance control {parameter_id}",
    )
    if raw["type"] != "number" or raw["unit"] != "percent":
        raise ValueError(
            f"Social-acceptance control {parameter_id} must be numeric percent"
        )
    minimum = _finite_number(raw["minimum"], f"{parameter_id} minimum")
    maximum = _finite_number(raw["maximum"], f"{parameter_id} maximum")
    step = _finite_number(raw["step"], f"{parameter_id} step")
    initial = _finite_number(
        raw["technical_initial_value"],
        f"{parameter_id} technical initial value",
    )
    if minimum != 0.0 or maximum != 100.0 or step <= 0.0:
        raise ValueError(
            f"Social-acceptance control {parameter_id} must cover 0-100 percent"
        )
    if not minimum <= initial <= maximum:
        raise ValueError(f"{parameter_id} technical initial value is outside range")
    recommendation = _mapping(
        raw["accepted_recommended_default"],
        f"{parameter_id} accepted recommendation",
    )
    _exact_keys(
        recommendation,
        {"state", "reason"},
        f"{parameter_id} accepted recommendation",
    )
    state = _exact_identifier(
        recommendation["state"],
        f"{parameter_id} recommendation state",
    )
    reason = _exact_text(
        recommendation["reason"],
        f"{parameter_id} recommendation reason",
    )
    return SocialAcceptanceControl(
        parameter_id=parameter_id,
        minimum=minimum,
        maximum=maximum,
        step=step,
        technical_initial_value=initial,
        recommendation_state=state,
        recommendation_reason=reason,
    )


def social_acceptance_contract(
    manifest: Mapping[str, Any],
) -> SocialAcceptanceContract:
    """Parse the complete manifest-owned acceptance capability contract."""

    raw = _mapping(manifest, "social-acceptance manifest")
    source = social_acceptance_source_contract(dict(raw))
    schema_version = _exact_text(
        raw.get("schema_version"),
        "social-acceptance schema version",
    )
    if schema_version != SOCIAL_ACCEPTANCE_CONTRACT_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported social-acceptance schema version: {schema_version}"
        )
    region_id = _exact_identifier(
        raw.get("region_id"),
        "social-acceptance region id",
    )
    if region_id != source.intended_region_id:
        raise ValueError("Social-acceptance region identity drifted from source")
    acceptance_id = _exact_identifier(
        raw.get("acceptance_id"),
        "social-acceptance contract id",
    )
    display_name = _exact_text(
        raw.get("display_name"),
        "social-acceptance display name",
    )
    source_resolution = _h3_resolution(
        raw.get("hex_resolution"),
        "social-acceptance source resolution",
    )
    raw_rollups = raw.get("rollup_resolutions")
    if not isinstance(raw_rollups, list):
        raise ValueError("Social-acceptance rollup_resolutions must be a list")
    rollup_resolutions = tuple(
        _h3_resolution(value, "social-acceptance rollup resolution")
        for value in raw_rollups
    )
    if (
        len(set(rollup_resolutions)) != len(rollup_resolutions)
        or any(value >= source_resolution for value in rollup_resolutions)
        or tuple(sorted(rollup_resolutions, reverse=True)) != rollup_resolutions
    ):
        raise ValueError(
            "Social-acceptance rollups must be unique descending parent resolutions"
        )
    rollup_rule = _exact_identifier(
        raw.get("rollup_rule"),
        "social-acceptance rollup rule",
    )
    if rollup_rule != SOCIAL_ACCEPTANCE_ROLLUP_RULE:
        raise NotImplementedError(
            f"Unsupported social-acceptance rollup rule: {rollup_rule}"
        )
    raw_scenarios = raw.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ValueError("Social-acceptance scenarios must be a non-empty list")
    scenarios: list[SocialAcceptanceScenario] = []
    for index, item in enumerate(raw_scenarios):
        scenario = _mapping(item, f"social-acceptance scenario {index}")
        _exact_keys(
            scenario,
            {"id", "label", "value_column"},
            f"social-acceptance scenario {index}",
        )
        scenarios.append(
            SocialAcceptanceScenario(
                scenario_id=_exact_identifier(
                    scenario["id"],
                    f"social-acceptance scenario {index} id",
                ),
                label=_exact_text(
                    scenario["label"],
                    f"social-acceptance scenario {index} label",
                ),
                value_column=_exact_identifier(
                    scenario["value_column"],
                    f"social-acceptance scenario {index} value column",
                ),
            )
        )
    scenario_ids = tuple(item.scenario_id for item in scenarios)
    value_columns = tuple(item.value_column for item in scenarios)
    declared_levels = tuple(raw.get("scenario_levels") or ())
    if (
        scenario_ids != declared_levels
        or len(set(scenario_ids)) != len(scenario_ids)
        or len(set(value_columns)) != len(value_columns)
    ):
        raise ValueError(
            "Social-acceptance scenario ids, levels and columns must be unique "
            "and ordered consistently"
        )
    default_scenario_id = _exact_identifier(
        raw.get("default_scenario"),
        "social-acceptance default scenario",
    )
    if default_scenario_id not in scenario_ids:
        raise ValueError("Social-acceptance default scenario is not declared")
    controls = _mapping(
        raw.get("control_contract"),
        "social-acceptance control contract",
    )
    _exact_keys(
        controls,
        {"impact_pct", "allocation_priority_pct"},
        "social-acceptance control contract",
    )
    impact_control = _control_contract(controls["impact_pct"], "impact_pct")
    allocation_control = _control_contract(
        controls["allocation_priority_pct"],
        "allocation_priority_pct",
    )
    value_range = raw.get("value_range")
    if value_range != [0, 1]:
        raise ValueError("Social-acceptance value_range must be [0, 1]")
    max_decimals = _non_negative_int(
        raw.get("max_decimals"),
        "social-acceptance max decimals",
    )
    if max_decimals > 6:
        raise ValueError("Social-acceptance max_decimals must be at most 6")
    random_seed_raw = raw.get("random_seed")
    random_seed = (
        _non_negative_int(random_seed_raw, "social-acceptance random seed")
        if random_seed_raw is not None
        else None
    )
    if source.synthetic and random_seed is None:
        raise ValueError("Synthetic social acceptance requires a random_seed")
    if not source.synthetic and random_seed is not None:
        raise ValueError("Observed social acceptance cannot declare a random_seed")
    method_note = _exact_text(
        raw.get("method_note"),
        "social-acceptance method note",
    )
    return SocialAcceptanceContract(
        schema_version=schema_version,
        region_id=region_id,
        acceptance_id=acceptance_id,
        display_name=display_name,
        source=source,
        source_resolution=source_resolution,
        rollup_resolutions=rollup_resolutions,
        rollup_rule=rollup_rule,
        scenarios=tuple(scenarios),
        default_scenario_id=default_scenario_id,
        impact_control=impact_control,
        allocation_priority_control=allocation_control,
        value_minimum=0.0,
        value_maximum=1.0,
        max_decimals=max_decimals,
        random_seed=random_seed,
        method_note=method_note,
    )


def social_acceptance_source_assets_signature(
    contract: SocialAcceptanceSourceContract,
) -> str:
    return _canonical_sha256(
        [
            {
                "role": asset.role,
                "provider": contract.provider,
                "path": asset.path,
                "sha256": asset.sha256,
            }
            for asset in sorted(
                contract.assets.values(),
                key=lambda item: item.role,
            )
        ]
    )


def social_acceptance_contract_signature(
    contract: SocialAcceptanceContract,
) -> str:
    if not isinstance(contract, SocialAcceptanceContract):
        raise TypeError("contract must be a SocialAcceptanceContract")
    payload = {
        "schema_version": contract.schema_version,
        "capability_id": SOCIAL_ACCEPTANCE_CAPABILITY_ID,
        "region_id": contract.region_id,
        "acceptance_id": contract.acceptance_id,
        "display_name": contract.display_name,
        "source": asdict(contract.source),
        "source_resolution": contract.source_resolution,
        "rollup_resolutions": contract.rollup_resolutions,
        "rollup_rule": contract.rollup_rule,
        "scenarios": [item.as_dict() for item in contract.scenarios],
        "default_scenario_id": contract.default_scenario_id,
        "impact_control": asdict(contract.impact_control),
        "allocation_priority_control": asdict(
            contract.allocation_priority_control
        ),
        "value_minimum": contract.value_minimum,
        "value_maximum": contract.value_maximum,
        "max_decimals": contract.max_decimals,
        "random_seed": contract.random_seed,
        "method_note": contract.method_note,
    }
    return _canonical_sha256(payload)


def _validate_control_value(
    control: SocialAcceptanceControl,
    value: Any,
) -> float:
    normalized = _finite_number(value, control.parameter_id)
    if not control.minimum <= normalized <= control.maximum:
        raise ValueError(
            f"{control.parameter_id} is outside its manifest range"
        )
    step_count = (normalized - control.minimum) / control.step
    if not math.isclose(
        step_count,
        round(step_count),
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise ValueError(
            f"{control.parameter_id} must align to manifest step {control.step}"
        )
    return normalized


def build_social_acceptance_request_from_contract(
    contract: SocialAcceptanceContract,
    *,
    access_scope: str,
    layer_visible: bool,
    scenario_id: str | None = None,
    target_resolution: int | None = None,
    impact_pct: float | None = None,
    allocation_priority_pct: float | None = None,
) -> SocialAcceptanceRequest:
    if not isinstance(contract, SocialAcceptanceContract):
        raise TypeError("contract must be a SocialAcceptanceContract")
    if not isinstance(layer_visible, bool):
        raise TypeError("social-acceptance layer_visible must be a boolean")
    scope = _exact_text(access_scope, "social-acceptance access scope")
    scope_parts = scope.split(":", 1)
    if (
        len(scope_parts) != 2
        or scope_parts[0] not in SOCIAL_ACCEPTANCE_ACCESS_SCOPE_KINDS
        or scope_parts[1] != contract.region_id
    ):
        raise ValueError(
            "Social-acceptance access_scope must be product:<region> or "
            "review:<region>"
        )
    selected = contract.scenario(
        scenario_id or contract.default_scenario_id
    )
    resolution = (
        contract.source_resolution
        if target_resolution is None
        else _h3_resolution(
            target_resolution,
            "social-acceptance target resolution",
        )
    )
    if resolution not in {
        contract.source_resolution,
        *contract.rollup_resolutions,
    }:
        raise ValueError(
            f"Social-acceptance contract has no R{resolution} result"
        )
    impact = _validate_control_value(
        contract.impact_control,
        contract.impact_control.technical_initial_value
        if impact_pct is None
        else impact_pct,
    )
    priority = _validate_control_value(
        contract.allocation_priority_control,
        contract.allocation_priority_control.technical_initial_value
        if allocation_priority_pct is None
        else allocation_priority_pct,
    )
    return SocialAcceptanceRequest(
        schema_version=SOCIAL_ACCEPTANCE_REQUEST_SCHEMA_VERSION,
        access_scope=scope,
        capability_id=SOCIAL_ACCEPTANCE_CAPABILITY_ID,
        region_id=contract.region_id,
        acceptance_id=contract.acceptance_id,
        scenario_id=selected.scenario_id,
        value_column=selected.value_column,
        source_resolution=contract.source_resolution,
        target_resolution=resolution,
        layer_visible=layer_visible,
        impact_pct=impact,
        allocation_priority_pct=priority,
        source_assets_signature_sha256=(
            social_acceptance_source_assets_signature(contract.source)
        ),
        contract_signature_sha256=(
            social_acceptance_contract_signature(contract)
        ),
    )


def parse_social_acceptance_request(
    value: Mapping[str, Any],
) -> SocialAcceptanceRequest:
    raw = _mapping(value, "social-acceptance request")
    _exact_keys(
        raw,
        {
            "schema_version",
            "access_scope",
            "capability_id",
            "region_id",
            "acceptance_id",
            "scenario_id",
            "value_column",
            "source_resolution",
            "target_resolution",
            "layer_visible",
            "impact_pct",
            "allocation_priority_pct",
            "source_assets_signature_sha256",
            "contract_signature_sha256",
        },
        "social-acceptance request",
    )
    if raw["schema_version"] != SOCIAL_ACCEPTANCE_REQUEST_SCHEMA_VERSION:
        raise ValueError("Unsupported social-acceptance request schema version")
    region_id = _exact_identifier(
        raw["region_id"],
        "social-acceptance request region id",
    )
    access_scope = _exact_text(
        raw["access_scope"],
        "social-acceptance request access scope",
    )
    scope_parts = access_scope.split(":", 1)
    if (
        len(scope_parts) != 2
        or scope_parts[0] not in SOCIAL_ACCEPTANCE_ACCESS_SCOPE_KINDS
        or scope_parts[1] != region_id
    ):
        raise ValueError("Social-acceptance request scope is not region-bound")
    if raw["capability_id"] != SOCIAL_ACCEPTANCE_CAPABILITY_ID:
        raise ValueError(
            "Social-acceptance request capability identity is invalid"
        )
    layer_visible = raw["layer_visible"]
    if not isinstance(layer_visible, bool):
        raise TypeError(
            "Social-acceptance request layer_visible must be a boolean"
        )
    return SocialAcceptanceRequest(
        schema_version=SOCIAL_ACCEPTANCE_REQUEST_SCHEMA_VERSION,
        access_scope=access_scope,
        capability_id=SOCIAL_ACCEPTANCE_CAPABILITY_ID,
        region_id=region_id,
        acceptance_id=_exact_identifier(
            raw["acceptance_id"],
            "social-acceptance request contract id",
        ),
        scenario_id=_exact_identifier(
            raw["scenario_id"],
            "social-acceptance request scenario id",
        ),
        value_column=_exact_identifier(
            raw["value_column"],
            "social-acceptance request value column",
        ),
        source_resolution=_h3_resolution(
            raw["source_resolution"],
            "social-acceptance request source resolution",
        ),
        target_resolution=_h3_resolution(
            raw["target_resolution"],
            "social-acceptance request target resolution",
        ),
        layer_visible=layer_visible,
        impact_pct=_finite_number(
            raw["impact_pct"],
            "social-acceptance request impact",
        ),
        allocation_priority_pct=_finite_number(
            raw["allocation_priority_pct"],
            "social-acceptance request allocation priority",
        ),
        source_assets_signature_sha256=_exact_sha256(
            raw["source_assets_signature_sha256"],
            "social-acceptance request source asset signature",
        ),
        contract_signature_sha256=_exact_sha256(
            raw["contract_signature_sha256"],
            "social-acceptance request contract signature",
        ),
    )


def validate_social_acceptance_request_from_contract(
    contract: SocialAcceptanceContract,
    request: SocialAcceptanceRequest,
) -> SocialAcceptanceRequest:
    if not isinstance(request, SocialAcceptanceRequest):
        raise TypeError("request must be a SocialAcceptanceRequest")
    rebuilt = build_social_acceptance_request_from_contract(
        contract,
        access_scope=request.access_scope,
        layer_visible=request.layer_visible,
        scenario_id=request.scenario_id,
        target_resolution=request.target_resolution,
        impact_pct=request.impact_pct,
        allocation_priority_pct=request.allocation_priority_pct,
    )
    if rebuilt != request:
        raise ValueError(
            "Social-acceptance request drifted from its manifest contract"
        )
    return request


def _display_geometry_cell_ids(path: Path) -> tuple[str, ...]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Social-acceptance display geometry cannot be read: {exc}"
        ) from exc
    if not isinstance(raw, Mapping) or raw.get("type") != "FeatureCollection":
        raise ValueError(
            "Social-acceptance display geometry must be a FeatureCollection"
        )
    features = raw.get("features")
    if not isinstance(features, list):
        raise ValueError("Social-acceptance display features must be a list")
    cell_ids: list[str] = []
    for index, feature in enumerate(features):
        item = _mapping(feature, f"social-acceptance display feature {index}")
        properties = _mapping(
            item.get("properties"),
            f"social-acceptance display feature {index} properties",
        )
        cell_id = _exact_text(
            properties.get("hex_id"),
            f"social-acceptance display feature {index} hex id",
        )
        if not h3.is_valid_cell(cell_id):
            raise ValueError(
                f"Social-acceptance display feature has invalid H3 id: {cell_id}"
            )
        cell_ids.append(cell_id)
    if len(cell_ids) != len(set(cell_ids)):
        raise ValueError("Social-acceptance display geometry has duplicate H3 ids")
    return tuple(sorted(cell_ids))


def load_social_acceptance_snapshot_from_paths(
    contract: SocialAcceptanceContract,
    *,
    values_path: Path,
    display_geometry_path: Path,
) -> SocialAcceptanceSnapshot:
    """Load and verify one generic CSV/H3 acceptance source snapshot."""

    if not isinstance(contract, SocialAcceptanceContract):
        raise TypeError("contract must be a SocialAcceptanceContract")
    expected_paths = {
        "acceptance_values": values_path,
        "display_geometry": display_geometry_path,
    }
    for role, path in expected_paths.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        if _sha256_path(path) != contract.source.assets[role].sha256:
            raise ValueError(f"Social-acceptance {role} checksum drifted")
    expected_columns = {
        "hex_id",
        "h3_resolution",
        "data_status",
        "method_version",
        *(scenario.value_column for scenario in contract.scenarios),
    }
    observations: list[SocialAcceptanceObservation] = []
    seen: set[str] = set()
    try:
        with values_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or set(reader.fieldnames) != expected_columns:
                raise ValueError(
                    "Social-acceptance CSV columns differ from the manifest contract"
                )
            for row_index, row in enumerate(reader, start=2):
                cell_id = _exact_text(
                    row.get("hex_id"),
                    f"social-acceptance CSV row {row_index} hex id",
                )
                if not h3.is_valid_cell(cell_id):
                    raise ValueError(
                        f"Social-acceptance CSV row {row_index} has invalid H3 id"
                    )
                if cell_id in seen:
                    raise ValueError(
                        f"Social-acceptance CSV has duplicate H3 id: {cell_id}"
                    )
                seen.add(cell_id)
                try:
                    resolution = int(row.get("h3_resolution") or "")
                except ValueError as exc:
                    raise ValueError(
                        f"Social-acceptance CSV row {row_index} resolution is invalid"
                    ) from exc
                if (
                    resolution != contract.source_resolution
                    or h3.get_resolution(cell_id) != contract.source_resolution
                ):
                    raise ValueError(
                        f"Social-acceptance CSV row {row_index} resolution drifted"
                    )
                data_status = _exact_text(
                    row.get("data_status"),
                    f"social-acceptance CSV row {row_index} data status",
                )
                method_version = _exact_text(
                    row.get("method_version"),
                    f"social-acceptance CSV row {row_index} method version",
                )
                if method_version != contract.source.method_id:
                    raise ValueError(
                        "Social-acceptance CSV method version differs from manifest"
                    )
                values: list[tuple[str, float]] = []
                for scenario in contract.scenarios:
                    raw_value = row.get(scenario.value_column)
                    try:
                        acceptance = float(raw_value)  # type: ignore[arg-type]
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            "Social-acceptance CSV value is not numeric: "
                            f"row={row_index}, scenario={scenario.scenario_id}"
                        ) from exc
                    if (
                        not math.isfinite(acceptance)
                        or not contract.value_minimum
                        <= acceptance
                        <= contract.value_maximum
                        or not math.isclose(
                            acceptance,
                            round(acceptance, contract.max_decimals),
                            rel_tol=0.0,
                            abs_tol=1e-12,
                        )
                    ):
                        raise ValueError(
                            "Social-acceptance CSV value violates range or precision: "
                            f"row={row_index}, scenario={scenario.scenario_id}"
                        )
                    values.append((scenario.scenario_id, acceptance))
                observations.append(
                    SocialAcceptanceObservation(
                        cell_id=cell_id,
                        source_resolution=resolution,
                        data_status=data_status,
                        method_version=method_version,
                        scenario_values=tuple(values),
                    )
                )
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ValueError(f"Social-acceptance CSV cannot be read: {exc}") from exc
    if len(observations) != contract.source.coverage.source_hex_count:
        raise ValueError(
            "Social-acceptance CSV row count differs from coverage contract"
        )
    geometry_ids = _display_geometry_cell_ids(display_geometry_path)
    observation_ids = tuple(sorted(item.cell_id for item in observations))
    if geometry_ids != observation_ids:
        raise ValueError(
            "Social-acceptance display geometry differs from observation ids"
        )
    return SocialAcceptanceSnapshot(
        schema_version=SOCIAL_ACCEPTANCE_SNAPSHOT_SCHEMA_VERSION,
        source_assets_signature_sha256=(
            social_acceptance_source_assets_signature(contract.source)
        ),
        observations=tuple(sorted(observations, key=lambda item: item.cell_id)),
    )


def _median(values: tuple[float, ...]) -> float:
    ordered = tuple(sorted(values))
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


def run_social_acceptance_request(
    contract: SocialAcceptanceContract,
    request: SocialAcceptanceRequest,
    snapshot: SocialAcceptanceSnapshot,
) -> SocialAcceptanceResult:
    """Execute a manifest-bound acceptance view without scenario-data trust."""

    validate_social_acceptance_request_from_contract(contract, request)
    if not isinstance(snapshot, SocialAcceptanceSnapshot):
        raise TypeError("snapshot must be a SocialAcceptanceSnapshot")
    if snapshot.schema_version != SOCIAL_ACCEPTANCE_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Unsupported social-acceptance snapshot schema version")
    if (
        snapshot.source_assets_signature_sha256
        != request.source_assets_signature_sha256
    ):
        raise ValueError(
            "Social-acceptance snapshot is not bound to the request assets"
        )
    if len(snapshot.observations) != contract.source.coverage.source_hex_count:
        raise ValueError(
            "Social-acceptance snapshot coverage drifted from the manifest"
        )
    buckets: dict[str, list[SocialAcceptanceObservation]] = {}
    for observation in snapshot.observations:
        if observation.source_resolution != request.source_resolution:
            raise ValueError(
                "Social-acceptance observation resolution drifted from request"
            )
        target_id = (
            observation.cell_id
            if request.target_resolution == request.source_resolution
            else str(
                h3.cell_to_parent(
                    observation.cell_id,
                    request.target_resolution,
                )
            )
        )
        buckets.setdefault(target_id, []).append(observation)
    impact_fraction = request.impact_pct / 100.0
    cells: list[SocialAcceptanceCellResult] = []
    for cell_id in sorted(buckets):
        children = buckets[cell_id]
        acceptance = math.fsum(
            child.value(request.scenario_id) for child in children
        ) / len(children)
        potential_weight = (
            (1.0 - impact_fraction) + impact_fraction * acceptance
        )
        cells.append(
            SocialAcceptanceCellResult(
                cell_id=cell_id,
                acceptance_value=acceptance,
                potential_weight=potential_weight,
                source_child_count=len(children),
                data_status=contract.source.value_data_status,
            )
        )
    if not cells:
        raise ValueError("Social-acceptance request returned no assessed cells")
    values = tuple(item.acceptance_value for item in cells)
    scenario = contract.scenario(request.scenario_id)
    result = SocialAcceptanceResult(
        schema_version=SOCIAL_ACCEPTANCE_RESULT_SCHEMA_VERSION,
        request=request,
        scenario_label=scenario.label,
        source_status=contract.source.status,
        source_dataset_id=contract.source.source_dataset_id,
        source_label=contract.source.source_label,
        allowed_use=contract.source.allowed_use,
        synthetic=contract.source.synthetic,
        regional_acceptance=contract.source.regional_acceptance,
        warning_by_language=tuple(
            (language, contract.source.warning_by_language[language])
            for language in sorted(contract.source.warning_by_language)
        ),
        provenance=contract.source.provenance,
        limitation=contract.source.limitation,
        replacement_condition=contract.source.replacement_condition,
        value_data_status=contract.source.value_data_status,
        missing_context_policy=contract.source.behavior.missing_context_policy,
        allocation_priority_model=(
            contract.source.behavior.allocation_priority_model
        ),
        allocation_missing_context_policy=(
            contract.source.behavior.allocation_missing_context_policy
        ),
        low_threshold=contract.source.behavior.low_threshold,
        high_threshold=contract.source.behavior.high_threshold,
        method_note=contract.method_note,
        coverage_source_hex_count=contract.source.coverage.source_hex_count,
        coverage_target_support_hex_count=(
            contract.source.coverage.target_support_hex_count
        ),
        coverage_unassessed_support_hex_count=(
            contract.source.coverage.unassessed_support_hex_count
        ),
        assessed_cell_count=len(cells),
        low_acceptance_cell_count=sum(
            value < contract.source.behavior.low_threshold for value in values
        ),
        high_acceptance_cell_count=sum(
            value >= contract.source.behavior.high_threshold for value in values
        ),
        minimum_acceptance=min(values),
        maximum_acceptance=max(values),
        mean_acceptance=math.fsum(values) / len(values),
        median_acceptance=_median(values),
        cells=tuple(cells),
    )
    return parse_social_acceptance_result(result.as_dict())


def parse_social_acceptance_result(
    value: Mapping[str, Any],
) -> SocialAcceptanceResult:
    raw = _mapping(value, "social-acceptance result")
    expected = {
        "schema_version",
        "request",
        "scenario_label",
        "source_status",
        "source_dataset_id",
        "source_label",
        "allowed_use",
        "synthetic",
        "regional_acceptance",
        "warning_by_language",
        "provenance",
        "limitation",
        "replacement_condition",
        "value_data_status",
        "missing_context_policy",
        "allocation_priority_model",
        "allocation_missing_context_policy",
        "low_threshold",
        "high_threshold",
        "method_note",
        "coverage_source_hex_count",
        "coverage_target_support_hex_count",
        "coverage_unassessed_support_hex_count",
        "assessed_cell_count",
        "low_acceptance_cell_count",
        "high_acceptance_cell_count",
        "minimum_acceptance",
        "maximum_acceptance",
        "mean_acceptance",
        "median_acceptance",
        "cells",
    }
    _exact_keys(raw, expected, "social-acceptance result")
    if raw["schema_version"] != SOCIAL_ACCEPTANCE_RESULT_SCHEMA_VERSION:
        raise ValueError("Unsupported social-acceptance result schema version")
    request = parse_social_acceptance_request(
        _mapping(raw["request"], "social-acceptance result request")
    )
    source_status = _exact_identifier(
        raw["source_status"],
        "social-acceptance result source status",
    )
    allowed_use = _exact_identifier(
        raw["allowed_use"],
        "social-acceptance result allowed use",
    )
    if source_status not in SUPPORTED_ACCEPTANCE_SOURCE_STATUSES:
        raise ValueError("Social-acceptance result source status is unsupported")
    if allowed_use not in SUPPORTED_ACCEPTANCE_USES:
        raise ValueError("Social-acceptance result allowed use is unsupported")
    synthetic = raw["synthetic"]
    regional_acceptance = raw["regional_acceptance"]
    if not isinstance(synthetic, bool) or not isinstance(
        regional_acceptance, bool
    ):
        raise TypeError(
            "Social-acceptance result trust flags must be booleans"
        )
    if source_status == "provisional_fallback" and (
        regional_acceptance
        or allowed_use != "behavior_exploration_only"
    ):
        raise ValueError(
            "Provisional social-acceptance result cannot claim acceptance"
        )
    if source_status == "accepted_regional" and (
        synthetic
        or not regional_acceptance
        or allowed_use != "regional_planning"
    ):
        raise ValueError(
            "Accepted social-acceptance result requires observed regional data"
        )
    warnings_raw = _mapping(
        raw["warning_by_language"],
        "social-acceptance result warnings",
    )
    if set(warnings_raw) != REQUIRED_DISPLAY_LANGUAGES:
        raise ValueError(
            "Social-acceptance result warnings must cover every language"
        )
    warnings = tuple(
        (
            language,
            _exact_text(
                warnings_raw[language],
                f"social-acceptance result warning {language}",
            ),
        )
        for language in sorted(warnings_raw)
    )
    value_data_status = _exact_identifier(
        raw["value_data_status"],
        "social-acceptance result data status",
    )
    if value_data_status != ("synthetic" if synthetic else "observed"):
        raise ValueError(
            "Social-acceptance result data status drifted from source trust"
        )
    missing_policy = _exact_identifier(
        raw["missing_context_policy"],
        "social-acceptance result missing policy",
    )
    allocation_priority_model = _exact_identifier(
        raw["allocation_priority_model"],
        "social-acceptance result allocation priority model",
    )
    allocation_missing_policy = _exact_identifier(
        raw["allocation_missing_context_policy"],
        "social-acceptance result allocation missing policy",
    )
    if missing_policy not in SUPPORTED_MISSING_CONTEXT_POLICIES:
        raise ValueError("Social-acceptance result missing policy is unsupported")
    if allocation_priority_model not in SUPPORTED_ALLOCATION_PRIORITY_MODELS:
        raise ValueError(
            "Social-acceptance result allocation priority model is unsupported"
        )
    if allocation_missing_policy not in SUPPORTED_ALLOCATION_MISSING_POLICIES:
        raise ValueError(
            "Social-acceptance result allocation missing policy is unsupported"
        )
    raw_cells = raw["cells"]
    if not isinstance(raw_cells, list) or not raw_cells:
        raise ValueError("Social-acceptance result needs assessed cells")
    cells: list[SocialAcceptanceCellResult] = []
    seen: set[str] = set()
    impact_fraction = request.impact_pct / 100.0
    for index, value in enumerate(raw_cells):
        item = _mapping(value, f"social-acceptance result cell {index}")
        _exact_keys(
            item,
            {
                "cell_id",
                "acceptance_value",
                "potential_weight",
                "source_child_count",
                "data_status",
            },
            f"social-acceptance result cell {index}",
        )
        cell_id = _exact_text(
            item["cell_id"],
            f"social-acceptance result cell {index} id",
        )
        if (
            cell_id in seen
            or not h3.is_valid_cell(cell_id)
            or h3.get_resolution(cell_id) != request.target_resolution
        ):
            raise ValueError(
                f"Social-acceptance result cell {index} identity is invalid"
            )
        seen.add(cell_id)
        acceptance = _finite_number(
            item["acceptance_value"],
            f"social-acceptance result cell {index} value",
        )
        weight = _finite_number(
            item["potential_weight"],
            f"social-acceptance result cell {index} weight",
        )
        if not 0.0 <= acceptance <= 1.0 or not math.isclose(
            weight,
            (1.0 - impact_fraction) + impact_fraction * acceptance,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                f"Social-acceptance result cell {index} weight drifted"
            )
        child_count = _non_negative_int(
            item["source_child_count"],
            f"social-acceptance result cell {index} source child count",
        )
        if child_count < 1:
            raise ValueError(
                "Social-acceptance result source child count must be positive"
            )
        data_status = _exact_identifier(
            item["data_status"],
            f"social-acceptance result cell {index} data status",
        )
        if data_status != value_data_status:
            raise ValueError(
                "Social-acceptance cell status drifted from result source"
            )
        cells.append(
            SocialAcceptanceCellResult(
                cell_id=cell_id,
                acceptance_value=acceptance,
                potential_weight=weight,
                source_child_count=child_count,
                data_status=data_status,
            )
        )
    if tuple(cell.cell_id for cell in cells) != tuple(sorted(seen)):
        raise ValueError("Social-acceptance result cells must be sorted")
    coverage_source = _non_negative_int(
        raw["coverage_source_hex_count"],
        "social-acceptance result source coverage",
    )
    coverage_target = _non_negative_int(
        raw["coverage_target_support_hex_count"],
        "social-acceptance result target coverage",
    )
    coverage_unassessed = _non_negative_int(
        raw["coverage_unassessed_support_hex_count"],
        "social-acceptance result unassessed coverage",
    )
    if coverage_source + coverage_unassessed != coverage_target:
        raise ValueError("Social-acceptance result coverage does not reconcile")
    assessed_count = _non_negative_int(
        raw["assessed_cell_count"],
        "social-acceptance result assessed count",
    )
    low_count = _non_negative_int(
        raw["low_acceptance_cell_count"],
        "social-acceptance result low count",
    )
    high_count = _non_negative_int(
        raw["high_acceptance_cell_count"],
        "social-acceptance result high count",
    )
    if assessed_count != len(cells) or low_count > assessed_count or high_count > assessed_count:
        raise ValueError("Social-acceptance result counts are inconsistent")
    values = tuple(cell.acceptance_value for cell in cells)
    low_threshold = _finite_number(
        raw["low_threshold"],
        "social-acceptance result low threshold",
    )
    high_threshold = _finite_number(
        raw["high_threshold"],
        "social-acceptance result high threshold",
    )
    if not 0.0 <= low_threshold < high_threshold <= 1.0:
        raise ValueError(
            "Social-acceptance result thresholds must satisfy "
            "0 <= low < high <= 1"
        )
    if (
        low_count != sum(value < low_threshold for value in values)
        or high_count != sum(value >= high_threshold for value in values)
    ):
        raise ValueError(
            "Social-acceptance result threshold counts drifted from cells"
        )
    minimum = _finite_number(
        raw["minimum_acceptance"],
        "social-acceptance result minimum",
    )
    maximum = _finite_number(
        raw["maximum_acceptance"],
        "social-acceptance result maximum",
    )
    mean = _finite_number(
        raw["mean_acceptance"],
        "social-acceptance result mean",
    )
    median = _finite_number(
        raw["median_acceptance"],
        "social-acceptance result median",
    )
    if not all(
        (
            math.isclose(minimum, min(values), rel_tol=0.0, abs_tol=1e-12),
            math.isclose(maximum, max(values), rel_tol=0.0, abs_tol=1e-12),
            math.isclose(
                mean,
                math.fsum(values) / len(values),
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            math.isclose(median, _median(values), rel_tol=0.0, abs_tol=1e-12),
        )
    ):
        raise ValueError("Social-acceptance result statistics drifted from cells")
    return SocialAcceptanceResult(
        schema_version=SOCIAL_ACCEPTANCE_RESULT_SCHEMA_VERSION,
        request=request,
        scenario_label=_exact_text(
            raw["scenario_label"],
            "social-acceptance result scenario label",
        ),
        source_status=source_status,
        source_dataset_id=_exact_identifier(
            raw["source_dataset_id"],
            "social-acceptance result source dataset id",
        ),
        source_label=_exact_text(
            raw["source_label"],
            "social-acceptance result source label",
        ),
        allowed_use=allowed_use,
        synthetic=synthetic,
        regional_acceptance=regional_acceptance,
        warning_by_language=warnings,
        provenance=_exact_text(
            raw["provenance"],
            "social-acceptance result provenance",
        ),
        limitation=_exact_text(
            raw["limitation"],
            "social-acceptance result limitation",
        ),
        replacement_condition=_exact_text(
            raw["replacement_condition"],
            "social-acceptance result replacement condition",
        ),
        value_data_status=value_data_status,
        missing_context_policy=missing_policy,
        allocation_priority_model=allocation_priority_model,
        allocation_missing_context_policy=allocation_missing_policy,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        method_note=_exact_text(
            raw["method_note"],
            "social-acceptance result method note",
        ),
        coverage_source_hex_count=coverage_source,
        coverage_target_support_hex_count=coverage_target,
        coverage_unassessed_support_hex_count=coverage_unassessed,
        assessed_cell_count=assessed_count,
        low_acceptance_cell_count=low_count,
        high_acceptance_cell_count=high_count,
        minimum_acceptance=minimum,
        maximum_acceptance=maximum,
        mean_acceptance=mean,
        median_acceptance=median,
        cells=tuple(cells),
    )


_SOCIAL_SIGNATURE_MAX_ENTRIES = 8
_SOCIAL_SIGNATURE_MAX_KEY_BYTES = 2 * 1024 * 1024
_SOCIAL_SIGNATURE_MAX_TUPLE_ITEMS = 32768
_SOCIAL_SIGNATURE_TYPES = (
    SocialAcceptanceResult, SocialAcceptanceRequest, SocialAcceptanceCellResult,
)
_SOCIAL_SIGNATURE_FIELDS = {
    kind: tuple(item.name for item in fields(kind)) for kind in _SOCIAL_SIGNATURE_TYPES
}
_SOCIAL_SIGNATURE_FIELD_SETS = {
    kind: frozenset(names) for kind, names in _SOCIAL_SIGNATURE_FIELDS.items()
}
_SOCIAL_SIGNATURE_METHODS = {kind: kind.as_dict for kind in _SOCIAL_SIGNATURE_TYPES}
_SocialSignatureCacheInfo = namedtuple(
    'SocialSignatureCacheInfo', 'hits misses bypasses currsize',
)


@dataclass
class _SocialSignatureOperation:
    thread_id: int
    active: bool = True
    proofs: dict[tuple[str, int], str] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0
    bypasses: int = 0


_social_signature_operation: ContextVar[_SocialSignatureOperation | None] = ContextVar(
    'speedlocal_social_signature_operation', default=None,
)


def _current_social_signature_operation() -> _SocialSignatureOperation | None:
    operation = _social_signature_operation.get()
    if operation is None or not operation.active or operation.thread_id != get_ident():
        return None
    return operation


@contextmanager
def social_acceptance_signature_operation():
    """Reuse exact successful signatures within one synchronous app operation.

    Nested calls share the owner's bounded proof table. No result, frame or
    serialized payload is retained, and every outer exit releases all proofs.
    """
    if _current_social_signature_operation() is not None:
        yield
        return
    operation = _SocialSignatureOperation(get_ident())
    token = _social_signature_operation.set(operation)
    try:
        yield
    finally:
        operation.active = False
        operation.proofs.clear()
        _social_signature_operation.reset(token)


def social_acceptance_signature_cache_info():
    """Return current owner-operation counters, or None outside that scope."""
    operation = _current_social_signature_operation()
    if operation is None:
        return None
    return _SocialSignatureCacheInfo(
        operation.hits, operation.misses, operation.bypasses, len(operation.proofs),
    )


def _social_acceptance_result_proof_key(
    result: SocialAcceptanceResult,
) -> tuple[str, int] | None:
    """Hash complete current immutable field values without trusting identity.

    Exact types and length-prefixed scalar encodings keep bool/int, signed
    zero, tuple order and every field distinct. Unsupported values bypass only
    reuse; the original parser still owns all successful answers and errors.
    """
    if type(result) is not SocialAcceptanceResult or any(
        getattr(kind, 'as_dict', None) is not _SOCIAL_SIGNATURE_METHODS[kind]
        for kind in _SOCIAL_SIGNATURE_TYPES
    ):
        return None
    digest = hashlib.sha256()
    size = 0

    def emit(tag: bytes, content: bytes = b'') -> bool:
        nonlocal size
        header = tag + str(len(content)).encode('ascii') + b':'
        size += len(header) + len(content)
        if size > _SOCIAL_SIGNATURE_MAX_KEY_BYTES:
            return False
        digest.update(header)
        digest.update(content)
        return True

    def visit(value: Any) -> bool:
        kind = type(value)
        if kind is str:
            return len(value) <= _SOCIAL_SIGNATURE_MAX_KEY_BYTES and emit(
                b's', value.encode('utf-8', errors='surrogatepass'),
            )
        if kind is bool:
            return emit(b'b', b'1' if value else b'0')
        if kind is int:
            return emit(b'i', str(value).encode('ascii'))
        if kind is float:
            return math.isfinite(value) and emit(b'f', value.hex().encode('ascii'))
        if value is None:
            return emit(b'n')
        if kind is tuple:
            return (len(value) <= _SOCIAL_SIGNATURE_MAX_TUPLE_ITEMS
                    and emit(b't', str(len(value)).encode('ascii'))
                    and all(visit(item) for item in value))
        if kind is SocialAcceptanceCellResult:
            current = vars(value)
            if type(current) is not dict or current.keys() != _SOCIAL_SIGNATURE_FIELD_SETS[kind]:
                return False
            cell_id, acceptance, weight, count, status = (
                current[name] for name in _SOCIAL_SIGNATURE_FIELDS[kind]
            )
            if (type(cell_id) is not str or type(status) is not str or type(count) is not int
                    or len(cell_id) + len(status) > _SOCIAL_SIGNATURE_MAX_KEY_BYTES
                    or not (type(acceptance) is int or type(acceptance) is float)
                    or not (type(weight) is int or type(weight) is float)
                    or not math.isfinite(acceptance) or not math.isfinite(weight)):
                return False
            # One flat scalar record avoids a retained or temporary nested key
            # graph per cell; repr is unambiguous for these exact builtin types.
            record = (cell_id, 'f' if type(acceptance) is float else 'i',
                      acceptance.hex() if type(acceptance) is float else str(acceptance),
                      'f' if type(weight) is float else 'i',
                      weight.hex() if type(weight) is float else str(weight), count, status)
            return emit(b'c', repr(record).encode('utf-8', errors='surrogatepass'))
        names = next((_SOCIAL_SIGNATURE_FIELDS[known] for known in _SOCIAL_SIGNATURE_TYPES
                      if kind is known), None)
        if names is None:
            return False
        current = vars(value)
        if type(current) is not dict or current.keys() != _SOCIAL_SIGNATURE_FIELD_SETS[kind]:
            return False
        return emit(b'd', kind.__name__.encode('ascii')) and all(
            visit(current[name]) for name in names
        )

    try:
        policy = (
            SOCIAL_ACCEPTANCE_RESULT_SCHEMA_VERSION,
            SOCIAL_ACCEPTANCE_REQUEST_SCHEMA_VERSION,
            SOCIAL_ACCEPTANCE_CAPABILITY_ID,
            SOCIAL_ACCEPTANCE_ACCESS_SCOPE_KINDS,
            tuple(sorted(SUPPORTED_ACCEPTANCE_SOURCE_STATUSES)),
            tuple(sorted(SUPPORTED_ACCEPTANCE_USES)),
            tuple(sorted(REQUIRED_DISPLAY_LANGUAGES)),
            tuple(sorted(SUPPORTED_MISSING_CONTEXT_POLICIES)),
            tuple(sorted(SUPPORTED_ALLOCATION_PRIORITY_MODELS)),
            tuple(sorted(SUPPORTED_ALLOCATION_MISSING_POLICIES)),
            _IDENTIFIER.pattern, _IDENTIFIER.flags, _SHA256.pattern, _SHA256.flags,
        )
        if not visit(policy) or not visit(result):
            return None
    except (RecursionError, TypeError, ValueError, OverflowError):
        # Admission must not introduce an error before the strict parser.
        return None
    return digest.hexdigest(), size


def _social_acceptance_calculation_result_signature_uncached(
    result: SocialAcceptanceResult,
) -> str:
    """Return the canonical calculation identity, excluding map visibility.

    The complete result is strictly replay-validated first. Only the
    request's ``layer_visible`` field is omitted; scenario, controls, source
    identity, trust, coverage, statistics and every result cell remain signed.
    """

    if not isinstance(result, SocialAcceptanceResult):
        raise TypeError("result must be a SocialAcceptanceResult")
    validated = parse_social_acceptance_result(result.as_dict())
    payload = validated.as_dict()
    request_payload = dict(payload["request"])
    request_payload.pop("layer_visible")
    payload["request"] = request_payload
    return _canonical_sha256(payload)


def social_acceptance_calculation_result_signature(
    result: SocialAcceptanceResult,
) -> str:
    """Return the unchanged strict signature, reusing only an exact success."""
    operation = _current_social_signature_operation()
    if operation is None:
        return _social_acceptance_calculation_result_signature_uncached(result)
    key = _social_acceptance_result_proof_key(result)
    if key is None:
        operation.bypasses += 1
        return _social_acceptance_calculation_result_signature_uncached(result)
    if key in operation.proofs:
        operation.hits += 1
        return operation.proofs[key]
    operation.misses += 1
    signature = _social_acceptance_calculation_result_signature_uncached(result)
    if _social_acceptance_result_proof_key(result) == key:
        if len(operation.proofs) >= _SOCIAL_SIGNATURE_MAX_ENTRIES:
            del operation.proofs[next(iter(operation.proofs))]
        operation.proofs[key] = signature
    return signature


def load_catalog_social_acceptance_contract(
    region_id: str,
) -> SocialAcceptanceContract:
    from .catalogs import load_social_acceptance_manifest

    normalized = _exact_identifier(
        region_id,
        "social-acceptance catalog region",
    )
    contract = social_acceptance_contract(
        load_social_acceptance_manifest(normalized)
    )
    if contract.region_id != normalized:
        raise ValueError("Social-acceptance catalog identity drifted")
    return contract


def build_catalog_social_acceptance_request(
    region_id: str,
    **kwargs: Any,
) -> SocialAcceptanceRequest:
    return build_social_acceptance_request_from_contract(
        load_catalog_social_acceptance_contract(region_id),
        **kwargs,
    )


def _authorize_catalog_social_acceptance_request(
    contract: SocialAcceptanceContract,
    request: SocialAcceptanceRequest,
) -> SocialAcceptanceRequest:
    from .access_policy import validate_product_access_dimensions
    from .catalogs import load_region
    from .workspace import load_review_access, load_workspace_profile

    validate_social_acceptance_request_from_contract(contract, request)
    region = load_region(request.region_id)
    if str(region.get("region_id") or "").strip().lower() != request.region_id:
        raise PermissionError(
            "Social-acceptance request region is not catalog-authorized"
        )
    profile = load_workspace_profile(request.region_id)
    if request.capability_id not in profile.capabilities:
        raise PermissionError(
            "Social-acceptance capability is not declared by the workspace"
        )
    scope_kind, scope_region_id = request.access_scope.split(":", 1)
    if scope_region_id != request.region_id:
        raise PermissionError(
            "Social-acceptance request scope belongs to another region"
        )
    if scope_kind == "product":
        landing_card = region.get("landing_card")
        behavior_reference = region.get("behavior_reference")
        if not isinstance(landing_card, Mapping) or not isinstance(
            behavior_reference,
            Mapping,
        ):
            raise PermissionError(
                "Product social-acceptance access is disabled for "
                f"{request.region_id}"
            )
        try:
            validate_product_access_dimensions(
                lifecycle=region.get("status"),
                behavior_reference_status=behavior_reference.get("status"),
                landing_card_enabled=landing_card.get("enabled"),
            )
        except (TypeError, ValueError) as exc:
            raise PermissionError(
                "Product social-acceptance access is disabled for "
                f"{request.region_id}"
            ) from exc
        return request
    if scope_kind != "review":
        raise PermissionError(
            f"Unsupported social-acceptance access mode: {scope_kind}"
        )
    try:
        access = load_review_access(request.region_id)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        raise PermissionError(
            "Review social-acceptance access is disabled for "
            f"{request.region_id}"
        ) from exc
    if (
        access.mode != "review"
        or access.surface != "shared_workspace"
        or access.requires_environment_allowlist is not True
        or request.capability_id not in access.allowed_capabilities
    ):
        raise PermissionError(
            "Social-acceptance capability is not allowed by review access"
        )
    return request


def load_catalog_social_acceptance_snapshot(region_id: str) -> SocialAcceptanceSnapshot:
    from .context_runtime import catalog_context_runtime_declared, load_catalog_context_inputs
    from .catalogs import load_social_acceptance_manifest

    if catalog_context_runtime_declared(region_id):
        return load_catalog_context_inputs(region_id).social_acceptance
    contract = load_catalog_social_acceptance_contract(region_id)
    paths = social_acceptance_asset_paths(load_social_acceptance_manifest(region_id), verify_checksums=True)
    return load_social_acceptance_snapshot_from_paths(contract,
        values_path=paths["acceptance_values"], display_geometry_path=paths["display_geometry"])


def run_catalog_social_acceptance_request(
    request: SocialAcceptanceRequest,
) -> SocialAcceptanceResult:
    if not isinstance(request, SocialAcceptanceRequest):
        raise TypeError("request must be a SocialAcceptanceRequest")
    contract = load_catalog_social_acceptance_contract(request.region_id)
    _authorize_catalog_social_acceptance_request(contract, request)
    snapshot = load_catalog_social_acceptance_snapshot(request.region_id)
    return run_social_acceptance_request(contract, request, snapshot)


def probe_catalog_social_acceptance(region_id: str) -> SocialAcceptanceProbe:
    try:
        contract = load_catalog_social_acceptance_contract(region_id)
    except (FileNotFoundError, KeyError) as exc:
        return SocialAcceptanceProbe("missing_manifest", str(exc))
    except NotImplementedError as exc:
        return SocialAcceptanceProbe("not_implemented", str(exc))
    except (OSError, TypeError, ValueError) as exc:
        return SocialAcceptanceProbe("not_validated", str(exc))
    try:
        snapshot = load_catalog_social_acceptance_snapshot(contract.region_id)
        request = build_social_acceptance_request_from_contract(
            contract,
            access_scope=f"review:{contract.region_id}",
            layer_visible=False,
        )
        result = run_social_acceptance_request(contract, request, snapshot)
    except NotImplementedError as exc:
        return SocialAcceptanceProbe("not_implemented", str(exc))
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        return SocialAcceptanceProbe("missing_data", str(exc))
    trust_note = (
        "Källan är fortfarande provisional_fallback och utgör inte regional "
        "acceptansevidens."
        if result.source_status == "provisional_fallback"
        else "Källans regionala acceptans framgår separat av kontraktet."
    )
    return SocialAcceptanceProbe(
        "technically_validated",
        "Det manifestbundna social-acceptanskontraktet, dess källor och "
        f"request/result-kedja är verifierade ({result.assessed_cell_count} "
        f"celler). {trust_note}",
    )


__all__ = [
    "AVAILABLE_ACCEPTANCE_DATA_STATUSES",
    "REQUIRED_DISPLAY_LANGUAGES",
    "SOCIAL_ACCEPTANCE_ACCESS_SCOPE_KINDS",
    "SOCIAL_ACCEPTANCE_CAPABILITY_ID",
    "SOCIAL_ACCEPTANCE_COMPILED_STATUS",
    "SOCIAL_ACCEPTANCE_CONTRACT_SCHEMA_VERSION",
    "SOCIAL_ACCEPTANCE_REQUEST_SCHEMA_VERSION",
    "SOCIAL_ACCEPTANCE_RESULT_SCHEMA_VERSION",
    "SOCIAL_ACCEPTANCE_ROLLUP_RULE",
    "SOCIAL_ACCEPTANCE_SNAPSHOT_SCHEMA_VERSION",
    "SUPPORTED_ACCEPTANCE_SOURCE_STATUSES",
    "SUPPORTED_ACCEPTANCE_USES",
    "SUPPORTED_ALLOCATION_PRIORITY_MODELS",
    "SocialAcceptanceAsset",
    "SocialAcceptanceBehaviorContract",
    "SocialAcceptanceCellResult",
    "SocialAcceptanceContract",
    "SocialAcceptanceControl",
    "SocialAcceptanceCoverageContract",
    "SocialAcceptanceObservation",
    "SocialAcceptanceProbe",
    "SocialAcceptanceRequest",
    "SocialAcceptanceResult",
    "SocialAcceptanceScenario",
    "SocialAcceptanceSnapshot",
    "SocialAcceptanceSourceContract",
    "build_catalog_social_acceptance_request",
    "build_social_acceptance_request_from_contract",
    "load_catalog_social_acceptance_contract",
    "load_social_acceptance_snapshot_from_paths",
    "parse_social_acceptance_request",
    "parse_social_acceptance_result",
    "probe_catalog_social_acceptance",
    "run_catalog_social_acceptance_request",
    "run_social_acceptance_request",
    "social_acceptance_asset_path",
    "social_acceptance_asset_paths",
    "social_acceptance_contract",
    "social_acceptance_contract_signature",
    "social_acceptance_calculation_result_signature",
    "social_acceptance_signature_operation",
    "social_acceptance_signature_cache_info",
    "social_acceptance_data_status_is_available",
    "social_acceptance_source_assets_signature",
    "social_acceptance_source_contract",
    "validate_social_acceptance_request_from_contract",
]
