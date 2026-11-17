from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal


ONBOARDING_FORM_ENV: Final[str] = "SPEEDLOCAL_REGION_FORM_ENABLED"
ONBOARDING_FORM_VIEW: Final[str] = "onboarding"
ONBOARDING_FORM_GATE_VALUE: Final[str] = "1"

OnboardingFormRouteKind = Literal["not_requested", "denied", "open"]


@dataclass(frozen=True)
class OnboardingFormRouteDecision:
    """Pure fail-closed decision for the local operator form surface."""

    kind: OnboardingFormRouteKind
    reason: str

    def __post_init__(self) -> None:
        if self.kind not in {"not_requested", "denied", "open"}:
            raise ValueError(f"Unsupported onboarding route kind: {self.kind!r}")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Onboarding route reason is required")

    @property
    def is_open(self) -> bool:
        return self.kind == "open"


def onboarding_form_gate_enabled(environment_value: object) -> bool:
    """Require the one exact local opt-in value; truthy aliases stay closed."""

    return environment_value == ONBOARDING_FORM_GATE_VALUE


def resolve_onboarding_form_route(
    *,
    query_view: object,
    environment_value: object,
    query_region: object = None,
    query_mode: object = None,
) -> OnboardingFormRouteDecision:
    """Resolve only the exact operator view and never select a product region."""

    if query_view is None:
        return OnboardingFormRouteDecision(
            kind="not_requested",
            reason="operator_view_not_requested",
        )
    if not isinstance(query_view, str) or not query_view.strip():
        return OnboardingFormRouteDecision(
            kind="not_requested",
            reason="operator_view_invalid",
        )
    if query_view.strip().lower() != ONBOARDING_FORM_VIEW:
        return OnboardingFormRouteDecision(
            kind="not_requested",
            reason="different_view_requested",
        )
    if query_region is not None or query_mode is not None:
        return OnboardingFormRouteDecision(
            kind="denied",
            reason="operator_view_conflicts_with_workspace_parameters",
        )
    if not onboarding_form_gate_enabled(environment_value):
        return OnboardingFormRouteDecision(
            kind="denied",
            reason="operator_environment_gate_closed",
        )
    return OnboardingFormRouteDecision(
        kind="open",
        reason="explicit_local_operator_access",
    )


__all__ = [
    "ONBOARDING_FORM_ENV",
    "ONBOARDING_FORM_GATE_VALUE",
    "ONBOARDING_FORM_VIEW",
    "OnboardingFormRouteDecision",
    "OnboardingFormRouteKind",
    "onboarding_form_gate_enabled",
    "resolve_onboarding_form_route",
]
