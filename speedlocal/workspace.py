from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping

from .access_policy import (
    ACCESS_TRUST_CLASSIFICATION_SET,
    validate_review_access_dimensions,
)
from .catalogs import load_analysis_manifest, load_region
from .paths import repo_root


AVAILABILITY_STATES = frozenset(
    {
        "available",
        "missing_manifest",
        "missing_data",
        "not_implemented",
        "not_validated",
        "technically_validated",
        "regionally_accepted",
        "public",
    }
)
READY_AVAILABILITY_STATES = frozenset(
    {
        "available",
        "technically_validated",
        "regionally_accepted",
        "public",
    }
)
WORKSPACE_PROFILE_SCHEMA_VERSION = "1.0"
WORKSPACE_PROFILE_ID = "v2_final_standard"
STANDARD_TECHNOLOGIES = ("wind", "solar")
STANDARD_GROUP_IDS = (
    "roads",
    "population",
    "nature",
    "culture",
    "grid_infrastructure",
)
STANDARD_CAPABILITY_IDS = (
    "workspace.map",
    "workspace.landscape",
    "wind.area",
    *(f"wind.group.{group_id}" for group_id in STANDARD_GROUP_IDS),
    "solar.area",
    *(f"solar.group.{group_id}" for group_id in STANDARD_GROUP_IDS),
    "solar.rooftop",
    "workspace.technology_context",
    "workspace.scenario",
    "workspace.social_acceptance",
    "workspace.combined_result",
)


@dataclass(frozen=True)
class WorkspaceGroupProfile:
    id: str
    label: str
    analysis_label: str
    interpretation: str
    source_map_default_visible: bool


@dataclass(frozen=True)
class WorkspaceProfile:
    id: str
    missing_policy: str
    technologies: tuple[str, ...]
    standard_groups: tuple[WorkspaceGroupProfile, ...]
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class ReviewSlicePolicy:
    analysis_id: str
    group_id: str
    apply_required: bool
    auto_select_sources: bool
    explicit_parameters: tuple[str, ...]
    default_source_ids: tuple[str, ...] | None = None

    def selects_source_by_default(self, layer_id: str) -> bool:
        return self.auto_select_sources and (
            self.default_source_ids is None or layer_id in self.default_source_ids
        )


@dataclass(frozen=True)
class ReviewAccessContract:
    region_id: str
    mode: str
    surface: str
    access_classification: str
    requires_environment_allowlist: bool
    entry_label: str
    entry_note: str
    warning_title: str
    warning_body: str
    status_intro: str
    allowed_use: str
    forbidden_use: str
    allowed_capabilities: tuple[str, ...]
    allowed_slices: tuple[ReviewSlicePolicy, ...]


@dataclass(frozen=True)
class CapabilityAvailability:
    capability_id: str
    state: str
    interaction: str
    label: str
    analysis_label: str
    interpretation: str
    layer_ids: tuple[str, ...]
    detail: str

    def __post_init__(self) -> None:
        if self.state not in AVAILABILITY_STATES:
            raise ValueError(
                f"Unsupported workspace availability state: {self.state}"
            )
        if self.interaction not in {"interactive", "read_only", "disabled"}:
            raise ValueError(
                f"Unsupported workspace interaction: {self.interaction}"
            )
        if (
            self.state not in READY_AVAILABILITY_STATES
            and self.interaction == "interactive"
        ):
            raise ValueError(
                f"Unavailable capability cannot be interactive: {self.capability_id}"
            )


def validate_workspace_analysis_manifest(
    raw: object,
    *,
    region_id: str,
    analysis_id: str,
    profile: WorkspaceProfile,
) -> None:
    """Validate the manifest shape used to expose workspace group controls."""

    if not isinstance(raw, dict):
        raise TypeError("Workspace analysis manifest must be an object")
    if str(raw.get("region_id") or "").strip().lower() != region_id:
        raise ValueError("Workspace analysis manifest region identity mismatch")
    if str(raw.get("analysis_id") or "").strip().lower() != analysis_id:
        raise ValueError("Workspace analysis manifest analysis identity mismatch")

    raw_groups = raw.get("groups")
    if not isinstance(raw_groups, list):
        raise TypeError("Workspace analysis groups must be a list")
    group_ids = tuple(
        str(value).strip().lower()
        for value in raw_groups
        if isinstance(value, str) and value.strip()
    )
    if len(group_ids) != len(raw_groups):
        raise ValueError("Workspace analysis group ids must be non-empty strings")
    if len(set(group_ids)) != len(group_ids):
        raise ValueError("Workspace analysis group ids must be unique")
    allowed_group_ids = {group.id for group in profile.standard_groups}
    unknown_group_ids = set(group_ids) - allowed_group_ids
    if unknown_group_ids:
        raise ValueError(
            "Workspace analysis declares unsupported groups: "
            + ", ".join(sorted(unknown_group_ids))
        )

    raw_layers = raw.get("layers")
    if not isinstance(raw_layers, list):
        raise TypeError("Workspace analysis layers must be a list")
    layer_ids: list[str] = []
    for item in raw_layers:
        if not isinstance(item, dict):
            raise TypeError("Workspace analysis layers must be objects")
        layer_id = str(item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()
        group_id = str(item.get("group_id") or "").strip().lower()
        operation = str(item.get("operation") or "").strip()
        if not all((layer_id, label, group_id, operation)):
            raise ValueError(
                "Workspace analysis layer identity and presentation are required"
            )
        if group_id not in group_ids:
            raise ValueError(
                f"Workspace analysis layer {layer_id} has undeclared group {group_id}"
            )
        if not isinstance(item.get("source"), dict):
            raise TypeError(
                f"Workspace analysis layer {layer_id} source must be an object"
            )
        if item.get("parameters") is not None and not isinstance(
            item.get("parameters"), dict
        ):
            raise TypeError(
                f"Workspace analysis layer {layer_id} parameters must be an object"
            )
        layer_ids.append(layer_id)
    if len(set(layer_ids)) != len(layer_ids):
        raise ValueError("Workspace analysis layer ids must be unique")


def _repo_json(path_value: object) -> dict[str, Any]:
    if not isinstance(path_value, str) or not path_value.strip():
        raise KeyError("Workspace profile is not configured")
    root = repo_root().resolve()
    path = (root / path_value).resolve()
    if path == root or root not in path.parents:
        raise ValueError(f"Workspace profile escapes repository: {path_value}")
    if not path.is_file():
        raise FileNotFoundError(f"Workspace profile does not exist: {path}")
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise TypeError("Workspace profile must be a JSON object")
    return raw


def load_workspace_profile(region_id: str) -> WorkspaceProfile:
    region = load_region(str(region_id))
    raw = _repo_json(region.get("workspace_profile"))
    if str(raw.get("schema_version") or "").strip() != WORKSPACE_PROFILE_SCHEMA_VERSION:
        raise ValueError(
            "Workspace profile schema version must be "
            f"{WORKSPACE_PROFILE_SCHEMA_VERSION}"
        )
    profile_id = str(raw.get("profile_id") or "").strip()
    if profile_id != WORKSPACE_PROFILE_ID:
        raise ValueError(
            f"Workspace profile id must be {WORKSPACE_PROFILE_ID}"
        )
    if raw.get("missing_policy") != "render_disabled":
        raise ValueError(
            "Workspace profile must render missing capabilities disabled"
        )
    technologies = tuple(str(value) for value in raw.get("technologies") or ())
    if technologies != STANDARD_TECHNOLOGIES:
        raise ValueError(
            "The V2 Final workspace profile must declare wind then solar"
        )
    groups: list[WorkspaceGroupProfile] = []
    for item in raw.get("standard_groups") or ():
        if not isinstance(item, dict):
            raise TypeError("Workspace groups must be objects")
        source_map_default_visible = item.get(
            "source_map_default_visible"
        )
        if not isinstance(source_map_default_visible, bool):
            raise TypeError(
                "Workspace group source_map_default_visible must be boolean"
            )
        group = WorkspaceGroupProfile(
            id=str(item.get("id") or "").strip(),
            label=str(item.get("label") or "").strip(),
            analysis_label=str(item.get("analysis_label") or "").strip(),
            interpretation=str(item.get("interpretation") or "").strip(),
            source_map_default_visible=source_map_default_visible,
        )
        if not all(
            (group.id, group.label, group.analysis_label, group.interpretation)
        ):
            raise ValueError("Workspace group presentation is incomplete")
        groups.append(group)
    if tuple(group.id for group in groups) != STANDARD_GROUP_IDS:
        raise ValueError(
            "Workspace groups must use the five canonical ids in product order"
        )
    capabilities = tuple(str(value) for value in raw.get("capabilities") or ())
    if capabilities != STANDARD_CAPABILITY_IDS:
        raise ValueError(
            "Workspace capabilities must match the standard contract order"
        )
    return WorkspaceProfile(
        id=WORKSPACE_PROFILE_ID,
        missing_policy="render_disabled",
        technologies=technologies,
        standard_groups=tuple(groups),
        capabilities=capabilities,
    )


def load_review_access(region_id: str) -> ReviewAccessContract:
    """Load one bounded local-review gate from the repo-owned region manifest."""

    normalized_region_id = str(region_id or "").strip().lower()
    region = load_region(normalized_region_id)
    raw = region.get("review_access")
    behavior_reference = region.get("behavior_reference") or {}
    landing_card = region.get("landing_card") or {}
    if not isinstance(raw, dict) or raw.get("enabled") is not True:
        raise KeyError(f"{normalized_region_id} has no enabled review access")
    if not isinstance(behavior_reference, dict) or not isinstance(
        landing_card,
        dict,
    ):
        raise TypeError("Review access requires object-shaped region gates")
    if (
        str(region.get("region_id") or "").strip().lower()
        != normalized_region_id
    ):
        raise ValueError("Review access region identity mismatch")
    trust_classification = validate_review_access_dimensions(
        lifecycle=region.get("status"),
        trust_classification=region.get("data_status"),
        behavior_reference_status=behavior_reference.get("status"),
        behavior_frozen_v2_parity=behavior_reference.get("frozen_v2_parity"),
        landing_card_enabled=landing_card.get("enabled"),
        review_access_classification=raw.get("access_classification"),
    )
    if (
        str(raw.get("mode") or "").strip().lower() != "review"
        or str(raw.get("surface") or "").strip().lower()
        != "shared_workspace"
        or trust_classification not in ACCESS_TRUST_CLASSIFICATION_SET
        or raw.get("requires_environment_allowlist") is not True
    ):
        raise ValueError("Review access gate semantics are invalid")

    presentation_keys = (
        "entry_label",
        "entry_note",
        "warning_title",
        "warning_body",
        "status_intro",
        "allowed_use",
        "forbidden_use",
    )
    if any(
        not isinstance(raw.get(key), str) or not raw[key].strip()
        for key in presentation_keys
    ):
        raise ValueError("Review access presentation is incomplete")
    presentation = {key: raw[key].strip() for key in presentation_keys}

    profile = load_workspace_profile(normalized_region_id)
    allowed_technologies = set(profile.technologies)
    allowed_groups = {group.id for group in profile.standard_groups}
    raw_capabilities = raw.get("allowed_capabilities")
    if not isinstance(raw_capabilities, list):
        raise TypeError("Review access allowed_capabilities must be a list")
    allowed_capabilities = tuple(
        str(value) if isinstance(value, str) else ""
        for value in raw_capabilities
    )
    allowed_capability_set = set(allowed_capabilities)
    canonical_capabilities = tuple(
        capability_id
        for capability_id in profile.capabilities
        if capability_id in allowed_capability_set
    )
    if (
        not allowed_capabilities
        or any(not value or value != value.strip() for value in allowed_capabilities)
        or len(allowed_capabilities) != len(allowed_capability_set)
        or allowed_capability_set.difference(profile.capabilities)
        or allowed_capabilities != canonical_capabilities
    ):
        raise ValueError(
            "Review access allowed_capabilities must be a non-empty, unique "
            "workspace-profile subsequence"
        )
    raw_slices = raw.get("allowed_slices")
    if not isinstance(raw_slices, list):
        raise TypeError("Review access allowed_slices must be a list")
    slices: list[ReviewSlicePolicy] = []
    identities: set[tuple[str, str]] = set()
    for item in raw_slices:
        if not isinstance(item, dict):
            raise TypeError("Review access slices must be objects")
        analysis_id = str(item.get("analysis_id") or "").strip().lower()
        group_id = str(item.get("group_id") or "").strip().lower()
        identity = (analysis_id, group_id)
        if (
            analysis_id not in allowed_technologies
            or group_id not in allowed_groups
            or identity in identities
            or item.get("analysis_id") != analysis_id
            or item.get("group_id") != group_id
        ):
            raise ValueError(f"Invalid review slice identity: {identity!r}")
        explicit_parameters = item.get("explicit_parameters")
        if (
            item.get("apply_required") is not True
            or not isinstance(item.get("auto_select_sources"), bool)
            or not isinstance(explicit_parameters, list)
            or not explicit_parameters
            or any(
                not isinstance(value, str)
                or not value
                or value != value.strip()
                for value in explicit_parameters
            )
        ):
            raise ValueError(f"Invalid review request policy: {identity!r}")
        normalized_parameters = tuple(explicit_parameters)
        if len(set(normalized_parameters)) != len(normalized_parameters):
            raise ValueError(f"Duplicate review parameters: {identity!r}")
        analysis_manifest = load_analysis_manifest(
            normalized_region_id,
            analysis_id,
        )
        validate_workspace_analysis_manifest(
            analysis_manifest,
            region_id=normalized_region_id,
            analysis_id=analysis_id,
            profile=profile,
        )
        group_layers = tuple(
            layer
            for layer in analysis_manifest.get("layers") or ()
            if isinstance(layer, dict)
            and str(layer.get("group_id") or "").strip().lower() == group_id
        )
        if not group_layers:
            raise ValueError(
                f"Review slice has no manifest-declared layers: {identity!r}"
            )
        default_source_ids: tuple[str, ...] | None = None
        if "default_source_ids" in item:
            raw_default_source_ids = item["default_source_ids"]
            if (
                not isinstance(raw_default_source_ids, list)
                or any(
                    not isinstance(value, str)
                    or not value
                    or value != value.strip()
                    for value in raw_default_source_ids
                )
            ):
                raise ValueError(f"Invalid review default source IDs: {identity!r}")
            default_source_ids = tuple(raw_default_source_ids)
            group_layer_ids = {layer["id"] for layer in group_layers}
            if (
                len(set(default_source_ids)) != len(default_source_ids)
                or not set(default_source_ids).issubset(group_layer_ids)
            ):
                raise ValueError(
                    f"Review default source IDs must be unique layers in their slice: {identity!r}"
                )
        for parameter_id in normalized_parameters:
            if any(
                not isinstance((layer.get("parameters") or {}).get(parameter_id), dict)
                for layer in group_layers
            ):
                raise ValueError(
                    f"Review parameter is not declared by every slice layer: "
                    f"{identity!r}/{parameter_id}"
                )
        slices.append(
            ReviewSlicePolicy(
                analysis_id=analysis_id,
                group_id=group_id,
                apply_required=True,
                auto_select_sources=item["auto_select_sources"],
                explicit_parameters=normalized_parameters,
                default_source_ids=default_source_ids,
            )
        )
        identities.add(identity)

    slice_capabilities = tuple(
        f"{policy.analysis_id}.group.{policy.group_id}" for policy in slices
    )
    expected_slice_capabilities = tuple(
        capability_id
        for capability_id in allowed_capabilities
        if ".group." in capability_id
    )
    if slice_capabilities != expected_slice_capabilities:
        raise ValueError(
            "Review access allowed_slices must exactly derive from the "
            "allowlisted standard-group capabilities"
        )

    return ReviewAccessContract(
        region_id=normalized_region_id,
        mode="review",
        surface="shared_workspace",
        access_classification=trust_classification,
        requires_environment_allowlist=True,
        entry_label=presentation["entry_label"],
        entry_note=presentation["entry_note"],
        warning_title=presentation["warning_title"],
        warning_body=presentation["warning_body"],
        status_intro=presentation["status_intro"],
        allowed_use=presentation["allowed_use"],
        forbidden_use=presentation["forbidden_use"],
        allowed_capabilities=allowed_capabilities,
        allowed_slices=tuple(slices),
    )


def resolve_group_availability(
    region_id: str,
    analysis_id: str,
    *,
    slice_states: Mapping[str, str] | None = None,
) -> tuple[CapabilityAvailability, ...]:
    """Resolve standard group presentation from repo-owned manifests only."""

    profile = load_workspace_profile(region_id)
    resolved_analysis_id = str(analysis_id).strip().lower()
    if resolved_analysis_id not in profile.technologies:
        raise ValueError(
            "Workspace analysis is not declared by the shared profile: "
            f"{analysis_id!r}"
        )
    states = {str(key): str(value) for key, value in (slice_states or {}).items()}
    analysis_error: str | None = None
    try:
        analysis = load_analysis_manifest(region_id, resolved_analysis_id)
        validate_workspace_analysis_manifest(
            analysis,
            region_id=str(region_id).strip().lower(),
            analysis_id=resolved_analysis_id,
            profile=profile,
        )
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        analysis = None
        analysis_error = type(exc).__name__
    declared_groups = {
        str(value) for value in (analysis or {}).get("groups") or ()
    }
    layers_by_group: dict[str, list[str]] = {}
    for layer in (analysis or {}).get("layers") or ():
        if not isinstance(layer, dict):
            continue
        group_id = str(layer.get("group_id") or "")
        layer_id = str(layer.get("id") or "")
        if group_id and layer_id:
            layers_by_group.setdefault(group_id, []).append(layer_id)

    rows: list[CapabilityAvailability] = []
    for group in profile.standard_groups:
        capability_id = f"{resolved_analysis_id}.group.{group.id}"
        layer_ids = tuple(layers_by_group.get(group.id, ()))
        if analysis is None or group.id not in declared_groups or not layer_ids:
            state = "missing_manifest"
            detail = (
                f"{resolved_analysis_id}-manifestet saknar giltiga deklarerade lager "
                f"för {group.id}."
                + (
                    f" Kontraktet kunde inte läsas ({analysis_error})."
                    if analysis_error
                    else ""
                )
            )
        else:
            state = states.get(
                f"{resolved_analysis_id}/{group.id}", "not_validated"
            )
            if state not in AVAILABILITY_STATES:
                raise ValueError(
                    "Invalid slice state for "
                    f"{resolved_analysis_id}/{group.id}: {state}"
                )
            detail = (
                "Kontrakt och data är validerade för denna lokala interaktion."
                if state == "available"
                else "Deklarationen finns men är inte validerad för denna åtkomstnivå."
                if state == "not_validated"
                else "Deklarerad källdata saknas eller klarar inte integritetskontrollen."
                if state == "missing_data"
                else "Konsumenten är ännu inte implementerad."
                if state == "not_implemented"
                else "Ett obligatoriskt kontraktsfält saknas."
            )
        rows.append(
            CapabilityAvailability(
                capability_id=capability_id,
                state=state,
                interaction="interactive" if state == "available" else "disabled",
                label=group.label,
                analysis_label=group.analysis_label,
                interpretation=group.interpretation,
                layer_ids=layer_ids,
                detail=detail,
            )
        )
    return tuple(rows)


__all__ = [
    "AVAILABILITY_STATES",
    "CapabilityAvailability",
    "ReviewAccessContract",
    "ReviewSlicePolicy",
    "STANDARD_CAPABILITY_IDS",
    "STANDARD_GROUP_IDS",
    "STANDARD_TECHNOLOGIES",
    "WorkspaceGroupProfile",
    "WorkspaceProfile",
    "WORKSPACE_PROFILE_ID",
    "WORKSPACE_PROFILE_SCHEMA_VERSION",
    "load_workspace_profile",
    "load_review_access",
    "resolve_group_availability",
    "validate_workspace_analysis_manifest",
]
