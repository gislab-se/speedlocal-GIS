from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final, Literal

from .access_policy import (
    normalize_access_trust,
    validate_product_access_dimensions,
    validate_review_access_dimensions,
)
from .catalogs import list_regions
from .workspace import load_review_access


WorkspaceRouteKind = Literal[
    "landing",
    "product",
    "review",
    "invalid_explicit",
]

LANDING_VIEW: Final[str] = "landing"
REVIEW_MODE: Final[str] = "review"
SHARED_WORKSPACE_SURFACE: Final[str] = "shared_workspace"


@dataclass(frozen=True)
class WorkspaceReviewRouteAccess:
    """The route-relevant projection of one fully validated review contract."""

    region_id: str
    mode: str
    surface: str
    access_classification: str
    requires_environment_allowlist: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.region_id, str)
            or not self.region_id
            or self.region_id != self.region_id.strip().lower()
        ):
            raise ValueError("Review route region id must be canonical")
        if self.mode != REVIEW_MODE:
            raise ValueError("Review route mode must be canonical")
        if self.surface != SHARED_WORKSPACE_SURFACE:
            raise ValueError("Review route surface must be the shared workspace")
        if self.requires_environment_allowlist is not True:
            raise ValueError("Review route must require an operator allowlist")
        if normalize_access_trust(self.access_classification) != (
            self.access_classification
        ):
            raise ValueError("Review route access classification must be canonical")


@dataclass(frozen=True)
class WorkspaceRouteDecision:
    """One closed routing decision with no implicit region fallback."""

    kind: WorkspaceRouteKind
    region_id: str | None
    access_scope: str | None
    reason: str

    def __post_init__(self) -> None:
        if self.kind not in {
            "landing",
            "product",
            "review",
            "invalid_explicit",
        }:
            raise ValueError(f"Unsupported workspace route kind: {self.kind!r}")
        if self.region_id is not None and (
            not isinstance(self.region_id, str)
            or not self.region_id
            or self.region_id != self.region_id.strip().lower()
        ):
            raise ValueError("Workspace route region id must be canonical")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Workspace route reason is required")
        if self.kind in {"product", "review"}:
            if self.region_id is None:
                raise ValueError("Workspace routes require a region")
            if self.access_scope != f"{self.kind}:{self.region_id}":
                raise ValueError("Workspace route access scope drifted")
        elif self.access_scope is not None:
            raise ValueError("A closed or landing route cannot carry access scope")

    def as_dict(self) -> dict[str, str | None]:
        return {
            "kind": self.kind,
            "region_id": self.region_id,
            "access_scope": self.access_scope,
            "reason": self.reason,
        }


def _decision(
    kind: WorkspaceRouteKind,
    *,
    region_id: str | None,
    reason: str,
) -> WorkspaceRouteDecision:
    access_scope = (
        f"{kind}:{region_id}" if kind in {"product", "review"} else None
    )
    return WorkspaceRouteDecision(
        kind=kind,
        region_id=region_id,
        access_scope=access_scope,
        reason=reason,
    )


def _query_value(value: object, field: str) -> tuple[str | None, str | None]:
    if value is None:
        return None, None
    if not isinstance(value, str) or not value.strip():
        return None, f"invalid_{field}_parameter"
    return value.strip().lower(), None


def _session_value(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().lower()


def _review_allowlist(
    values: Iterable[object],
) -> frozenset[str] | None:
    if isinstance(values, (str, bytes, Mapping)) or not isinstance(
        values,
        Iterable,
    ):
        return None
    normalized: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            return None
        normalized.add(value.strip().lower())
    return frozenset(normalized)


def _region_entry(
    regions_by_id: Mapping[str, Mapping[str, object]],
    region_id: str,
) -> Mapping[str, object] | None:
    region = regions_by_id.get(region_id)
    if not isinstance(region, Mapping):
        return None
    declared_id = region.get("region_id")
    if (
        not isinstance(declared_id, str)
        or declared_id != region_id
        or declared_id != declared_id.strip().lower()
    ):
        return None
    return region


def _product_access_is_valid(region: Mapping[str, object]) -> bool:
    behavior_reference = region.get("behavior_reference")
    landing_card = region.get("landing_card")
    if not isinstance(behavior_reference, Mapping) or not isinstance(
        landing_card,
        Mapping,
    ):
        return False
    try:
        validate_product_access_dimensions(
            lifecycle=region.get("status"),
            behavior_reference_status=behavior_reference.get("status"),
            landing_card_enabled=landing_card.get("enabled"),
        )
    except (TypeError, ValueError):
        return False
    return True


def _review_access_is_valid(
    region: Mapping[str, object],
    access: WorkspaceReviewRouteAccess | None,
) -> bool:
    region_id = str(region.get("region_id") or "")
    raw_access = region.get("review_access")
    behavior_reference = region.get("behavior_reference")
    landing_card = region.get("landing_card")
    if (
        access is None
        or access.region_id != region_id
        or not isinstance(raw_access, Mapping)
        or not isinstance(behavior_reference, Mapping)
        or not isinstance(landing_card, Mapping)
        or raw_access.get("enabled") is not True
        or raw_access.get("mode") != access.mode
        or raw_access.get("surface") != access.surface
        or raw_access.get("access_classification")
        != access.access_classification
        or raw_access.get("requires_environment_allowlist")
        is not access.requires_environment_allowlist
    ):
        return False
    try:
        trust = validate_review_access_dimensions(
            lifecycle=region.get("status"),
            trust_classification=region.get("data_status"),
            behavior_reference_status=behavior_reference.get("status"),
            behavior_frozen_v2_parity=behavior_reference.get(
                "frozen_v2_parity"
            ),
            landing_card_enabled=landing_card.get("enabled"),
            review_access_classification=raw_access.get(
                "access_classification"
            ),
        )
    except (TypeError, ValueError):
        return False
    return trust == access.access_classification


def resolve_workspace_route_from_mappings(
    *,
    regions_by_id: Mapping[str, Mapping[str, object]],
    review_access_by_region: Mapping[str, WorkspaceReviewRouteAccess],
    review_allowlist: Iterable[object],
    query_region: object = None,
    query_mode: object = None,
    query_view: object = None,
    session_region: object = None,
) -> WorkspaceRouteDecision:
    """Resolve query/session input without selecting a default region.

    ``review_access_by_region`` is deliberately separate from the raw region
    mappings.  A catalog caller may add an entry only after the complete review
    contract has validated.  The pure mapping entry point lets neutral fixture
    regions exercise identical routing without repository or UI dependencies.
    An explicit region may use its allowlisted review access without a mode
    parameter; session-only selection never grants review access.
    """

    if not isinstance(regions_by_id, Mapping) or not isinstance(
        review_access_by_region,
        Mapping,
    ):
        raise TypeError("Workspace route catalogs must be mappings")

    explicit_query = any(
        value is not None for value in (query_region, query_mode, query_view)
    )
    normalized_region, region_problem = _query_value(query_region, "region")
    normalized_mode, mode_problem = _query_value(query_mode, "mode")
    normalized_view, view_problem = _query_value(query_view, "view")

    if explicit_query:
        query_problem = region_problem or mode_problem or view_problem
        if query_problem is not None:
            return _decision(
                "invalid_explicit",
                region_id=normalized_region,
                reason=query_problem,
            )
        if normalized_mode is not None and normalized_region is None:
            return _decision(
                "invalid_explicit",
                region_id=None,
                reason="mode_requires_region",
            )
        if normalized_mode is not None and normalized_view is not None:
            return _decision(
                "invalid_explicit",
                region_id=normalized_region,
                reason="mode_and_view_conflict",
            )
        if normalized_view not in {None, LANDING_VIEW}:
            return _decision(
                "invalid_explicit",
                region_id=normalized_region,
                reason="unsupported_view",
            )
        if normalized_mode not in {None, REVIEW_MODE}:
            return _decision(
                "invalid_explicit",
                region_id=normalized_region,
                reason="unsupported_mode",
            )
        if normalized_region is None:
            return _decision(
                "landing",
                region_id=None,
                reason="explicit_landing_view",
            )

        region = _region_entry(regions_by_id, normalized_region)
        if region is None:
            return _decision(
                "invalid_explicit",
                region_id=normalized_region,
                reason="unknown_or_invalid_region",
            )
        if normalized_view == LANDING_VIEW:
            return _decision(
                "landing",
                region_id=normalized_region,
                reason="explicit_landing_view",
            )
        if normalized_mode == REVIEW_MODE:
            allowlist = _review_allowlist(review_allowlist)
            if allowlist is None:
                return _decision(
                    "invalid_explicit",
                    region_id=normalized_region,
                    reason="invalid_review_allowlist",
                )
            if normalized_region not in allowlist:
                return _decision(
                    "invalid_explicit",
                    region_id=normalized_region,
                    reason="review_not_allowlisted",
                )
            access = review_access_by_region.get(normalized_region)
            if not isinstance(access, WorkspaceReviewRouteAccess) or not (
                _review_access_is_valid(region, access)
            ):
                return _decision(
                    "invalid_explicit",
                    region_id=normalized_region,
                    reason="review_access_invalid",
                )
            if normalized_mode != access.mode:
                return _decision(
                    "invalid_explicit",
                    region_id=normalized_region,
                    reason="review_mode_mismatch",
                )
            return _decision(
                "review",
                region_id=normalized_region,
                reason="explicit_review",
            )
        if _product_access_is_valid(region):
            return _decision(
                "product",
                region_id=normalized_region,
                reason="explicit_product",
            )
        allowlist = _review_allowlist(review_allowlist)
        access = review_access_by_region.get(normalized_region)
        if (
            allowlist is not None
            and normalized_region in allowlist
            and isinstance(access, WorkspaceReviewRouteAccess)
            and _review_access_is_valid(region, access)
        ):
            return _decision(
                "review",
                region_id=normalized_region,
                reason="allowlisted_review",
            )
        return _decision(
            "landing",
            region_id=normalized_region,
            reason="region_requires_landing",
        )

    normalized_session_region = _session_value(session_region)
    if normalized_session_region is None:
        return _decision(
            "landing",
            region_id=None,
            reason=(
                "invalid_session_region"
                if session_region is not None
                else "no_region_selected"
            ),
        )
    session_entry = _region_entry(regions_by_id, normalized_session_region)
    if session_entry is None:
        return _decision(
            "landing",
            region_id=None,
            reason="session_region_unavailable",
        )
    if _product_access_is_valid(session_entry):
        return _decision(
            "product",
            region_id=normalized_session_region,
            reason="session_product",
        )
    return _decision(
        "landing",
        region_id=normalized_session_region,
        reason="session_region_requires_landing",
    )


def _catalog_route_mappings() -> tuple[
    dict[str, Mapping[str, object]],
    dict[str, WorkspaceReviewRouteAccess],
]:
    regions: dict[str, Mapping[str, object]] = {}
    review_access: dict[str, WorkspaceReviewRouteAccess] = {}
    for region in list_regions():
        region_id = region.get("region_id")
        if (
            not isinstance(region_id, str)
            or not region_id
            or region_id != region_id.strip().lower()
            or region_id in regions
        ):
            raise ValueError("Public region catalog has an invalid identity")
        regions[region_id] = region
        raw_access = region.get("review_access")
        if not isinstance(raw_access, Mapping) or raw_access.get("enabled") is not True:
            continue
        try:
            validated = load_review_access(region_id)
            review_access[region_id] = WorkspaceReviewRouteAccess(
                region_id=validated.region_id,
                mode=validated.mode,
                surface=validated.surface,
                access_classification=validated.access_classification,
                requires_environment_allowlist=(
                    validated.requires_environment_allowlist
                ),
            )
        except (FileNotFoundError, KeyError, OSError, TypeError, ValueError):
            # An invalid declaration remains visible on the landing page, but
            # it cannot produce a review route.
            continue
    return regions, review_access


def resolve_catalog_workspace_route(
    *,
    review_allowlist: Iterable[object],
    query_region: object = None,
    query_mode: object = None,
    query_view: object = None,
    session_region: object = None,
) -> WorkspaceRouteDecision:
    """Resolve the repository catalog through the same pure route core."""

    regions, review_access = _catalog_route_mappings()
    return resolve_workspace_route_from_mappings(
        regions_by_id=regions,
        review_access_by_region=review_access,
        review_allowlist=review_allowlist,
        query_region=query_region,
        query_mode=query_mode,
        query_view=query_view,
        session_region=session_region,
    )


__all__ = [
    "LANDING_VIEW",
    "REVIEW_MODE",
    "SHARED_WORKSPACE_SURFACE",
    "WorkspaceReviewRouteAccess",
    "WorkspaceRouteDecision",
    "WorkspaceRouteKind",
    "resolve_catalog_workspace_route",
    "resolve_workspace_route_from_mappings",
]
