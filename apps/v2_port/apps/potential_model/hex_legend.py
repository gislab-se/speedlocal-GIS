"""Language-neutral area references for the hexagons a map can display.

H3 references describe complete cells, not clipped land, remaining potential or
allocated area. Schematic comparison polygons instead carry their own exact
represented areas and do not belong to an H3 resolution family.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import math
from typing import Any

import h3


def _has_drawn_polygon(feature: Any) -> bool:
    if not isinstance(feature, Mapping):
        return False
    geometry = feature.get("geometry")
    if not isinstance(geometry, Mapping):
        return False
    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, (list, tuple)) or not coordinates:
        return False
    polygons = [coordinates] if geometry.get("type") == "Polygon" else (
        coordinates if geometry.get("type") == "MultiPolygon" else []
    )
    return any(
        isinstance(polygon, (list, tuple)) and polygon
        and isinstance(polygon[0], (list, tuple)) and len(polygon[0]) >= 4
        for polygon in polygons
    )


def _resolution(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(numeric) or not numeric.is_integer() or not 0 <= numeric <= 15:
        return None
    return int(numeric)


def hex_area_legend_metadata(layers: list[dict[str, Any]]) -> list[dict[str, Any] | None]:
    """Return one optional reference per input layer without changing inputs.

    The H3 value is the arithmetic mean of distinct full cells represented by
    polygon features in that layer. Areas are memoized across layers in this
    call. No global H3 mean or potential-area property is substituted for a
    missing cell. Schematic sizes retain their exact positive declared values.
    """
    metadata: list[dict[str, Any] | None] = []
    cell_areas: dict[str, float] = {}
    for spec in layers:
        if not isinstance(spec, Mapping):
            metadata.append(None)
            continue
        collection = spec.get("feature_collection")
        features = collection.get("features", []) if isinstance(collection, Mapping) else []
        if not isinstance(features, (list, tuple)):
            features = []

        if spec.get("legend_id") == "outside_lp_need":
            sizes: Counter[float] = Counter()
            for feature in features:
                if not _has_drawn_polygon(feature):
                    continue
                props = feature.get("properties")
                if not isinstance(props, Mapping):
                    continue
                value = props.get("represented_area_km2")
                if isinstance(value, bool):
                    continue
                try:
                    area = float(value)
                except (TypeError, ValueError, OverflowError):
                    continue
                if math.isfinite(area) and area > 0:
                    sizes[area] += 1
            metadata.append({
                "kind": "schematic",
                "sizes": [{"area_km2": area, "count": sizes[area]} for area in sorted(sizes, reverse=True)],
            } if sizes else None)
            continue

        resolution = _resolution(spec.get("auto_resolution"))
        if resolution is None or not (
            spec.get("layer_kind") == "hex" or spec.get("auto_resolution_group")
        ):
            metadata.append(None)
            continue
        cells: set[str] = set()
        for feature in features:
            if not _has_drawn_polygon(feature):
                continue
            props = feature.get("properties")
            cell_id = props.get("hex_id") if isinstance(props, Mapping) else None
            if not isinstance(cell_id, str):
                continue
            cell_id = cell_id.lower()
            if not h3.is_valid_cell(cell_id) or h3.get_resolution(cell_id) != resolution:
                continue
            if cell_id not in cell_areas:
                area = float(h3.cell_area(cell_id, unit="km^2"))
                if not math.isfinite(area) or area <= 0:
                    continue
                cell_areas[cell_id] = area
            cells.add(cell_id)
        metadata.append({
            "kind": "h3", "resolution": resolution,
            "area_km2": math.fsum(cell_areas[cell_id] for cell_id in sorted(cells)) / len(cells),
            "cell_count": len(cells),
        } if cells else None)
    return metadata
