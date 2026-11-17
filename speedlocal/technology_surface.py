from __future__ import annotations

import math
from collections.abc import Iterable
import h3
import pandas as pd

from .social_acceptance import social_acceptance_data_status_is_available


EXACT_AREA_COLUMNS = (
    "display_area_km2",
    "potential_area_km2",
    "potential_area_share_pct",
)


def apply_allocation_context_completeness(
    frame: pd.DataFrame,
    *,
    required_observed_columns: Iterable[str],
    optional_observed_columns: Iterable[str],
) -> pd.DataFrame:
    """Classify complete required and optional allocation observations."""

    work = frame.copy()
    required = tuple(str(column) for column in required_observed_columns)
    optional = tuple(str(column) for column in optional_observed_columns)
    missing = (set(required) | set(optional)) - set(work.columns)
    if missing:
        raise ValueError(
            "Allocation context is missing observation flags: "
            f"{sorted(missing)}"
        )

    if required:
        required_count = work[list(required)].fillna(False).astype(bool).sum(
            axis=1
        )
        work["allocation_context_observation_count"] = required_count.astype(
            int
        )
        work["allocation_context_required_count"] = len(required)
        work["allocation_context_status"] = "missing"
        work.loc[required_count.gt(0), "allocation_context_status"] = "partial"
        work.loc[
            required_count.eq(len(required)),
            "allocation_context_status",
        ] = "complete"
        work["allocation_context_complete"] = work[
            "allocation_context_status"
        ].eq("complete")
    else:
        work["allocation_context_observation_count"] = 0
        work["allocation_context_required_count"] = 0
        work["allocation_context_status"] = "missing"
        work["allocation_context_complete"] = False

    if optional:
        optional_count = work[list(optional)].fillna(False).astype(bool).sum(
            axis=1
        )
        work["allocation_optional_context_observation_count"] = (
            optional_count.astype(int)
        )
        work["allocation_optional_context_layer_count"] = len(optional)
        work["allocation_optional_context_status"] = "missing"
        work.loc[
            optional_count.gt(0),
            "allocation_optional_context_status",
        ] = "partial"
        work.loc[
            optional_count.eq(len(optional)),
            "allocation_optional_context_status",
        ] = "complete"
    else:
        work["allocation_optional_context_observation_count"] = 0
        work["allocation_optional_context_layer_count"] = 0
        work["allocation_optional_context_status"] = "not_requested"
    return work


def filter_allocation_ready_context(
    frame: pd.DataFrame,
    *,
    social_priority_pct: float = 0.0,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Fail closed on missing required technical or requested social data."""

    if frame.empty:
        return frame, {
            "candidate_count_before_context_gate": 0,
            "candidate_count_after_context_gate": 0,
            "context_blocked_cell_count": 0,
            "social_context_blocked_cell_count": 0,
        }
    ready = pd.Series(True, index=frame.index, dtype=bool)
    if "allocation_context_complete" in frame.columns:
        ready &= frame["allocation_context_complete"].fillna(False).eq(True)
    else:
        # A caller that skipped required-context classification must never
        # turn an unknown technology cell into an allocation candidate.
        ready &= False
    technical_ready = ready.copy()
    social_blocked = pd.Series(False, index=frame.index, dtype=bool)
    if float(social_priority_pct or 0.0) > 0.0:
        social_ready = (
            frame["social_acceptance_data_status"].map(
                social_acceptance_data_status_is_available
            )
            if "social_acceptance_data_status" in frame.columns
            else pd.Series(False, index=frame.index, dtype=bool)
        )
        social_blocked = ready & ~social_ready
        ready &= social_ready
    filtered = frame.loc[ready].copy()
    return filtered, {
        "candidate_count_before_context_gate": len(frame),
        "candidate_count_after_context_gate": len(filtered),
        "context_blocked_cell_count": int((~technical_ready).sum()),
        "social_context_blocked_cell_count": int(social_blocked.sum()),
    }


def merge_exact_area_with_optional_context(
    exact_area_frame: pd.DataFrame,
    context_frame: pd.DataFrame,
    *,
    replaced_area_columns: Iterable[str],
) -> pd.DataFrame:
    """Keep every exact support cell and attach context without inventing it.

    The eligible-surface result is the row and area authority. Context may
    cover fewer cells and is therefore joined left onto that exact universe.
    Missing context stays null and receives an explicit status.
    """

    required = {"hex_id", *EXACT_AREA_COLUMNS}
    missing = required - set(exact_area_frame.columns)
    if missing:
        raise ValueError(
            "Exact technology area is missing required columns: "
            f"{sorted(missing)}"
        )
    if exact_area_frame.empty:
        raise ValueError("Exact technology area must not be empty")

    exact = exact_area_frame[["hex_id", *EXACT_AREA_COLUMNS]].copy()
    if exact["hex_id"].isna().any():
        raise ValueError("Exact technology area contains null H3 ids")
    exact["hex_id"] = exact["hex_id"].astype(str).str.strip()
    if exact["hex_id"].eq("").any() or exact["hex_id"].duplicated().any():
        raise ValueError(
            "Exact technology area contains blank or duplicate H3 ids"
        )
    if not exact["hex_id"].map(h3.is_valid_cell).all():
        raise ValueError("Exact technology area contains invalid H3 ids")
    exact_resolutions = set(exact["hex_id"].map(h3.get_resolution))
    if len(exact_resolutions) != 1:
        raise ValueError(
            "Exact technology area mixes H3 resolutions"
        )
    exact_resolution = next(iter(exact_resolutions))
    for column in EXACT_AREA_COLUMNS:
        exact[column] = pd.to_numeric(exact[column], errors="coerce")
    finite = exact[list(EXACT_AREA_COLUMNS)].map(
        lambda value: math.isfinite(float(value))
    )
    if not bool(finite.all(axis=None)):
        raise ValueError("Exact technology area contains non-finite values")
    if bool(exact["display_area_km2"].le(0.0).any()):
        raise ValueError("Exact technology display areas must be positive")
    if bool(exact["potential_area_km2"].lt(0.0).any()):
        raise ValueError("Exact technology potential areas must be non-negative")
    if bool(
        exact["potential_area_km2"].gt(
            exact["display_area_km2"] + 1e-9
        ).any()
    ):
        raise ValueError(
            "Exact technology potential area exceeds its eligible area"
        )
    if bool(
        (
            exact["potential_area_share_pct"].lt(0.0)
            | exact["potential_area_share_pct"].gt(100.0)
        ).any()
    ):
        raise ValueError(
            "Exact technology potential shares must be between 0 and 100"
        )
    expected_share = (
        exact["potential_area_km2"]
        / exact["display_area_km2"]
        * 100.0
    )
    if bool(
        (expected_share - exact["potential_area_share_pct"])
        .abs()
        .gt(1e-8)
        .any()
    ):
        raise ValueError(
            "Exact technology potential shares do not use eligible area as "
            "their denominator"
        )

    if context_frame.empty:
        context = pd.DataFrame({"hex_id": pd.Series(dtype="string")})
    else:
        if "hex_id" not in context_frame.columns:
            raise ValueError("Technology context requires hex_id")
        context = context_frame.copy()
        if context["hex_id"].isna().any():
            raise ValueError("Technology context contains null H3 ids")
        context["hex_id"] = context["hex_id"].astype(str).str.strip()
        if context["hex_id"].eq("").any() or context["hex_id"].duplicated().any():
            raise ValueError(
                "Technology context contains blank or duplicate H3 ids"
            )
        if not context["hex_id"].map(h3.is_valid_cell).all():
            raise ValueError("Technology context contains invalid H3 ids")
        if not context["hex_id"].map(h3.get_resolution).eq(
            exact_resolution
        ).all():
            raise ValueError(
                "Technology context does not match exact H3 resolution"
            )
    context = context.drop(
        columns=[
            column
            for column in replaced_area_columns
            if column in context.columns
        ],
        errors="ignore",
    )
    context["_app_extent_context"] = True
    merged = exact.merge(
        context,
        on="hex_id",
        how="left",
        validate="one_to_one",
    )
    available = merged.pop("_app_extent_context").fillna(False).astype(bool)
    merged["technology_context_status"] = available.map(
        {True: "app_extent", False: "not_assessed"}
    )
    merged["technology_context_available"] = available
    return merged
