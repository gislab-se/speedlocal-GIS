from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


@dataclass(frozen=True)
class WorkspaceMapView:
    """Validated, manifest-owned map viewport for the shared workspace."""

    region_id: str
    center: tuple[float, float]
    zoom: int
    bounds: tuple[tuple[float, float], tuple[float, float]] | None

    def center_list(self) -> list[float]:
        return [self.center[0], self.center[1]]

    def bounds_list(self) -> list[list[float]] | None:
        if self.bounds is None:
            return None
        return [list(self.bounds[0]), list(self.bounds[1])]


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def resolve_workspace_map_view(region: Mapping[str, Any]) -> WorkspaceMapView:
    """Resolve one fail-closed viewport without a default-region fallback."""

    if not isinstance(region, Mapping):
        raise TypeError("Workspace map region contract must be an object")
    region_id = str(region.get("region_id") or "").strip().lower()
    if not region_id:
        raise ValueError("Workspace map region_id is missing")

    raw_center = region.get("default_map_center")
    if (
        not isinstance(raw_center, (list, tuple))
        or len(raw_center) != 2
        or not all(_finite_number(value) for value in raw_center)
    ):
        raise ValueError(f"{region_id} default_map_center is invalid")
    center = (float(raw_center[0]), float(raw_center[1]))
    if not (-90.0 <= center[0] <= 90.0 and -180.0 <= center[1] <= 180.0):
        raise ValueError(f"{region_id} default_map_center is outside WGS84")

    raw_zoom = region.get("default_zoom")
    if (
        not _finite_number(raw_zoom)
        or not float(raw_zoom).is_integer()
        or not 0 <= int(raw_zoom) <= 22
    ):
        raise ValueError(f"{region_id} default_zoom is invalid")
    zoom = int(raw_zoom)

    raw_bounds = region.get("default_map_bounds")
    bounds: tuple[tuple[float, float], tuple[float, float]] | None = None
    if raw_bounds is not None:
        if (
            not isinstance(raw_bounds, (list, tuple))
            or len(raw_bounds) != 2
            or not all(
                isinstance(corner, (list, tuple))
                and len(corner) == 2
                and all(_finite_number(value) for value in corner)
                for corner in raw_bounds
            )
        ):
            raise ValueError(f"{region_id} default_map_bounds is invalid")
        south_west = (float(raw_bounds[0][0]), float(raw_bounds[0][1]))
        north_east = (float(raw_bounds[1][0]), float(raw_bounds[1][1]))
        if not (
            -90.0 <= south_west[0] < north_east[0] <= 90.0
            and -180.0 <= south_west[1] < north_east[1] <= 180.0
        ):
            raise ValueError(f"{region_id} default_map_bounds is outside WGS84")
        bounds = (south_west, north_east)

    return WorkspaceMapView(
        region_id=region_id,
        center=center,
        zoom=zoom,
        bounds=bounds,
    )
