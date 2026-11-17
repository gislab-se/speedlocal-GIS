from __future__ import annotations

from types import MappingProxyType
from typing import Final


ACCESS_TRUST_CLASSIFICATIONS: Final[tuple[str, ...]] = (
    "diagnostic_only",
    "candidate",
    "technically_validated",
    "regionally_accepted",
)
ACCESS_TRUST_CLASSIFICATION_SET: Final[frozenset[str]] = frozenset(
    ACCESS_TRUST_CLASSIFICATIONS
)
REVIEW_LIFECYCLE: Final[str] = "onboarding"
PRODUCT_LIFECYCLE: Final[str] = "active"
PRODUCT_TRUST_CLASSIFICATION: Final[str] = "regionally_accepted"

# The behavior-reference status is related to, but deliberately not identical
# to, package trust. A technically validated package still has a candidate
# behavior reference until the region's own acceptance evidence is approved.
BEHAVIOR_STATUS_BY_TRUST: Final = MappingProxyType(
    {
        "diagnostic_only": "diagnostic_only",
        "candidate": "candidate",
        "technically_validated": "candidate",
        "regionally_accepted": "authoritative",
    }
)


def normalize_access_trust(value: object) -> str:
    """Return one canonical access-trust identity or fail closed."""

    normalized = str(value or "").strip().lower()
    if normalized not in ACCESS_TRUST_CLASSIFICATION_SET:
        raise ValueError(
            "Unsupported access trust classification: "
            f"{normalized or '<blank>'}"
        )
    return normalized


def behavior_status_for_trust(value: object) -> str:
    """Map package trust to the only compatible behavior-reference status."""

    return str(BEHAVIOR_STATUS_BY_TRUST[normalize_access_trust(value)])


def product_route_request_is_valid(
    *,
    lifecycle: object,
    trust_classification: object,
    behavior_reference_declared: bool,
) -> bool:
    """Whether a human may request a future product route.

    A valid request remains only an intent. It never enables a landing card.
    """

    try:
        trust = normalize_access_trust(trust_classification)
    except ValueError:
        return False
    return (
        str(lifecycle or "").strip().lower() == PRODUCT_LIFECYCLE
        and trust == PRODUCT_TRUST_CLASSIFICATION
        and behavior_reference_declared is True
    )


def validate_product_access_dimensions(
    *,
    lifecycle: object,
    behavior_reference_status: object,
    landing_card_enabled: object,
) -> None:
    """Validate the runtime product gate independently of a region id."""

    if str(lifecycle or "").strip().lower() != PRODUCT_LIFECYCLE:
        raise ValueError("Product access requires lifecycle/status=active")
    if str(behavior_reference_status or "").strip().lower() != "authoritative":
        raise ValueError(
            "Product access requires an authoritative regional behavior reference"
        )
    if landing_card_enabled is not True:
        raise ValueError("Product access requires landing_card.enabled=true")


def validate_review_access_dimensions(
    *,
    lifecycle: object,
    trust_classification: object,
    behavior_reference_status: object,
    behavior_frozen_v2_parity: object,
    landing_card_enabled: object,
    review_access_classification: object,
) -> str:
    """Validate the canonical non-public local-review trust/lifecycle gate.

    Review is available only during onboarding, always with a disabled public
    landing card. All four trust levels may be reviewed, but the materialized
    region and review gate must agree exactly and must use the compatible
    behavior-reference status.
    """

    if str(lifecycle or "").strip().lower() != REVIEW_LIFECYCLE:
        raise ValueError("Local review requires lifecycle=onboarding")
    trust = normalize_access_trust(trust_classification)
    if landing_card_enabled is not False:
        raise ValueError("Local review requires landing_card.enabled=false")
    if normalize_access_trust(review_access_classification) != trust:
        raise ValueError(
            "Local review access classification must match region data trust"
        )
    expected_behavior_status = behavior_status_for_trust(trust)
    actual_behavior_status = str(
        behavior_reference_status or ""
    ).strip().lower()
    if actual_behavior_status != expected_behavior_status:
        raise ValueError(
            "Behavior-reference status is incompatible with access trust: "
            f"expected {expected_behavior_status}, received "
            f"{actual_behavior_status or '<blank>'}"
        )
    if not isinstance(behavior_frozen_v2_parity, bool):
        raise TypeError("Behavior-reference frozen_v2_parity must be boolean")
    if trust != PRODUCT_TRUST_CLASSIFICATION and behavior_frozen_v2_parity:
        raise ValueError(
            "Non-regional trust cannot claim frozen V2 behavior parity"
        )
    return trust


__all__ = [
    "ACCESS_TRUST_CLASSIFICATIONS",
    "ACCESS_TRUST_CLASSIFICATION_SET",
    "BEHAVIOR_STATUS_BY_TRUST",
    "PRODUCT_LIFECYCLE",
    "PRODUCT_TRUST_CLASSIFICATION",
    "REVIEW_LIFECYCLE",
    "behavior_status_for_trust",
    "normalize_access_trust",
    "product_route_request_is_valid",
    "validate_review_access_dimensions",
    "validate_product_access_dimensions",
]
