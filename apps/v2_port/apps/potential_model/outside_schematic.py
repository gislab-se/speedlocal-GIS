"""Compact, area-faithful comparison hexagons beside a region.

These polygons illustrate an amount of land; they are not H3 observations or
proposed locations. Layout depends only on the region extent and area amounts,
never on the current browser zoom or pan position.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from pyproj import CRS, Geod, Transformer


_TECHNOLOGIES = ("wind", "solar")
_MAX_BASE_CELLS = 50_000
_AREA_STEP = 7.0
_FULL_LEVELS = 3
_LAYOUT_MARGIN = 1.002
_VIEW_ASPECT = 1.5
_GEOD = Geod(ellps="WGS84")


def _mixed_cell_areas(total_area: float, nominal_area: float) -> list[float]:
    """Use three discrete area levels, followed by one exact remainder.

    Seven is an area ratio inspired by the H3 hierarchy. These are schematic
    regular hexagons, not H3 cells, parents or a geometric H3 compaction.
    """
    exponent = math.floor(math.log(total_area / nominal_area, _AREA_STEP))
    cell_area = nominal_area * _AREA_STEP ** exponent
    if cell_area <= 0 or not math.isfinite(cell_area):
        raise ValueError("Schematic area is outside numeric display precision")
    # Correct floating-point boundaries at exact powers of seven.
    while cell_area > total_area:
        cell_area /= _AREA_STEP
    while cell_area * _AREA_STEP <= total_area:
        cell_area *= _AREA_STEP
    result = []
    for _ in range(_FULL_LEVELS):
        remaining = total_area - math.fsum(result)
        if remaining <= 0:
            break
        if cell_area <= 0:
            raise ValueError("Schematic area is outside numeric display precision")
        count = min(6, math.floor(remaining / cell_area))
        result.extend([cell_area] * count)
        cell_area /= _AREA_STEP
    remaining = total_area - math.fsum(result)
    if remaining > 0:
        result.append(remaining)
    return result


def _compact_layout(areas: list[float]) -> list[tuple[float, float, float]]:
    """Pack descending regular hexagons at deterministic tangent candidates."""
    normals = [
        (math.cos(math.radians(60 * index)), math.sin(math.radians(60 * index)))
        for index in range(6)
    ]
    apothem_factor = math.sqrt(3.0) / 2.0
    placed: list[tuple[float, float, float]] = []
    bounds = None
    for area in areas:
        radius = math.sqrt(area * 1_000_000 / (1.5 * math.sqrt(3.0)))
        padded_radius = radius * _LAYOUT_MARGIN
        candidates = [(0.0, 0.0)] if not placed else []
        for x, y, previous_radius in placed:
            combined_radius = (radius + previous_radius) * _LAYOUT_MARGIN
            for nx, ny in normals:
                for offset in (
                    -combined_radius / 2.0, 0.0, combined_radius / 2.0,
                    (previous_radius - radius) * _LAYOUT_MARGIN / 2.0,
                    (radius - previous_radius) * _LAYOUT_MARGIN / 2.0,
                ):
                    candidates.append((
                        x + nx * apothem_factor * combined_radius - ny * offset,
                        y + ny * apothem_factor * combined_radius + nx * offset,
                    ))
        choices = []
        for x, y in candidates:
            if any(
                all(
                    abs((x - px) * nx + (y - py) * ny)
                    < apothem_factor * (radius + pr) * _LAYOUT_MARGIN - 1e-7
                    for nx, ny in normals[:3]
                )
                for px, py, pr in placed
            ):
                continue
            cell_bounds = (
                x - apothem_factor * padded_radius, y - padded_radius,
                x + apothem_factor * padded_radius, y + padded_radius,
            )
            combined = cell_bounds if bounds is None else (
                min(bounds[0], cell_bounds[0]), min(bounds[1], cell_bounds[1]),
                max(bounds[2], cell_bounds[2]), max(bounds[3], cell_bounds[3]),
            )
            width, height = combined[2] - combined[0], combined[3] - combined[1]
            choices.append(((max(width, height), width * height, x * x + y * y, x, y), combined))
        if not choices:
            raise ValueError("Schematic hexagons could not form a separated layout")
        score, bounds = min(choices, key=lambda choice: choice[0])
        placed.append((score[-2], score[-1], radius))
    return placed


def _projected_region_bounds(
    bbox: tuple[float, float, float, float], transformer: Transformer,
) -> tuple[float, float, float, float]:
    west, south, east, north = bbox
    # Include curved projected edges, not just the four WGS84 corners.
    points = []
    for index in range(65):
        fraction = index / 64.0
        lng = west + (east - west) * fraction
        lat = south + (north - south) * fraction
        points.extend(((lng, south), (lng, north), (west, lat), (east, lat)))
    xs, ys = transformer.transform(*zip(*points))
    return min(xs), min(ys), max(xs), max(ys)


def _place_groups(
    bounds: tuple[float, float, float, float],
    sizes: dict[str, tuple[float, float]],
    gap: float,
) -> dict[str, tuple[float, float]]:
    west, south, east, north = bounds
    center_x, center_y = (west + east) / 2.0, (south + north) / 2.0
    candidates = []
    for side in ("west", "east", "north", "south"):
        vertical = side in {"west", "east"}
        along = 1 if vertical else 0
        across = 0 if vertical else 1
        length = sum(size[along] for size in sizes.values()) + gap * (len(sizes) - 1)
        depth = max(size[across] for size in sizes.values())
        cursor = (center_y if vertical else center_x) - length / 2.0
        centers = {}
        combined = list(bounds)
        for technology, (width, height) in sizes.items():
            along_size = height if vertical else width
            position = cursor + along_size / 2.0
            if side == "west":
                x, y = west - gap - depth / 2.0, position
            elif side == "east":
                x, y = east + gap + depth / 2.0, position
            elif side == "north":
                x, y = position, north + gap + depth / 2.0
            else:
                x, y = position, south - gap - depth / 2.0
            centers[technology] = (x, y)
            combined = [
                min(combined[0], x - width / 2.0),
                min(combined[1], y - height / 2.0),
                max(combined[2], x + width / 2.0),
                max(combined[3], y + height / 2.0),
            ]
            cursor += along_size + gap
        width, height = combined[2] - combined[0], combined[3] - combined[1]
        candidates.append(((max(width / _VIEW_ASPECT, height), width * height), centers))
    # Stable iteration order resolves ties without regional special cases.
    return min(candidates, key=lambda candidate: candidate[0])[1]


def _area_faithful_hex(
    center_x: float, center_y: float, radius: float,
    area_m2: float, to_wgs84: Transformer,
) -> dict[str, Any]:
    offsets = [
        (math.cos(math.radians(30 + 60 * index)), math.sin(math.radians(30 + 60 * index)))
        for index in range(6)
    ]
    for _ in range(3):
        xs = [center_x + radius * x for x, _ in offsets]
        ys = [center_y + radius * y for _, y in offsets]
        lngs, lats = to_wgs84.transform(xs, ys)
        actual_area = abs(_GEOD.polygon_area_perimeter(lngs, lats)[0])
        if not math.isfinite(actual_area) or actual_area <= 0:
            raise ValueError("Schematic hexagon could not preserve its geographic area")
        if abs(actual_area - area_m2) <= max(0.01, area_m2 * 1e-9):
            break
        radius *= math.sqrt(area_m2 / actual_area)
    else:
        raise ValueError("Schematic hexagon geographic area did not converge")
    ring = [[float(lng), float(lat)] for lng, lat in zip(lngs, lats)]
    return {"type": "Polygon", "coordinates": [ring + [ring[0]]]}


def build_schematic_polygons(
    land_bbox: tuple[float, float, float, float],
    areas_km2: Mapping[str, float],
    cell_area_km2: float,
) -> list[dict[str, Any]]:
    """Return fixed wind/solar hex polygons with exact represented ground area.

    ``land_bbox`` is WGS84 (west, south, east, north). Cell areas use a fixed
    hierarchy of nominal area times powers of seven. The largest fitting
    level is drawn first, followed by two smaller levels and an exact remainder.
    Geodesic area error is bounded by max(0.01 m², one part per billion) per
    polygon. Each technology needs at most 19 polygons, independent of zoom.
    """
    west, south, east, north = (float(value) for value in land_bbox)
    if not all(math.isfinite(value) for value in (west, south, east, north)) or not (
        -180 <= west < east <= 180 and -90 < south < north < 90
    ):
        raise ValueError("Schematic region bounds must be a valid WGS84 extent")
    nominal_area = float(cell_area_km2)
    if not math.isfinite(nominal_area) or not 0 < nominal_area <= 10_000_000:
        raise ValueError("Schematic cell area must be positive, finite and within the display limit")
    areas = {technology: float(areas_km2.get(technology, 0.0)) for technology in _TECHNOLOGIES}
    if any(not math.isfinite(area) or area < 0 for area in areas.values()):
        raise ValueError("Schematic areas must be nonnegative and finite")
    areas = {technology: area for technology, area in areas.items() if area > 0}
    if not areas:
        return []
    if sum(areas.values()) > min(10_000_000, nominal_area * _MAX_BASE_CELLS):
        raise ValueError("Schematic area request exceeds the safe display size")
    cell_areas = {technology: _mixed_cell_areas(area, nominal_area) for technology, area in areas.items()}
    layouts = {technology: _compact_layout(values) for technology, values in cell_areas.items()}

    local_crs = CRS.from_proj4(
        f"+proj=laea +lat_0={(south + north) / 2.0} "
        f"+lon_0={(west + east) / 2.0} +datum=WGS84 +units=m"
    )
    to_local = Transformer.from_crs("EPSG:4326", local_crs, always_xy=True)
    to_wgs84 = Transformer.from_crs(local_crs, "EPSG:4326", always_xy=True)
    region_bounds = _projected_region_bounds((west, south, east, north), to_local)
    if not all(math.isfinite(value) for value in region_bounds):
        raise ValueError("Schematic region extent cannot use a local equal-area projection")
    group_origins, sizes = {}, {}
    for technology, layout in layouts.items():
        xmin = min(x - math.sqrt(3.0) * radius * _LAYOUT_MARGIN / 2 for x, _, radius in layout)
        xmax = max(x + math.sqrt(3.0) * radius * _LAYOUT_MARGIN / 2 for x, _, radius in layout)
        ymin = min(y - radius * _LAYOUT_MARGIN for _, y, radius in layout)
        ymax = max(y + radius * _LAYOUT_MARGIN for _, y, radius in layout)
        sizes[technology] = (xmax - xmin, ymax - ymin)
        group_origins[technology] = ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0)
    region_width = region_bounds[2] - region_bounds[0]
    region_height = region_bounds[3] - region_bounds[1]
    nominal_radius = math.sqrt(nominal_area * 1_000_000 / (1.5 * math.sqrt(3.0)))
    gap = max(2.0 * nominal_radius, min(region_width, region_height) * 0.02)
    group_positions = _place_groups(region_bounds, sizes, gap)

    records = []
    for technology, layout in layouts.items():
        origin_x, origin_y = group_origins[technology]
        position_x, position_y = group_positions[technology]
        for (x, y, radius), area in zip(layout, cell_areas[technology]):
            geometry = _area_faithful_hex(
                x - origin_x + position_x, y - origin_y + position_y,
                radius, area * 1_000_000, to_wgs84,
            )
            records.append({"technology": technology, "geometry": geometry, "area_km2": area})
    return records
