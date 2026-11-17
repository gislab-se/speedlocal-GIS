"""Area-weighted categorical map rollups, separate from analytical results."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
import html
import math
from typing import Any

import h3

from .i18n import translate

# Resolve exact area ties deterministically, without inventing joint suitability.
CLASS_ORDER = ("not_suitable", "wind_only", "solar_only", "wind_and_solar")


def class_areas_by_parent(
    source_cells: Iterable[tuple[str, str, float]], target_resolution: int,
) -> dict[str, dict[str, float]]:
    """Sum original model areas by native colour and H3 parent, never by votes."""
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    seen: set[str] = set()
    for cell_id, class_id, area in source_cells:
        if cell_id in seen or class_id not in CLASS_ORDER:
            raise ValueError("Duplicate cell or unknown rollup colour")
        seen.add(cell_id)
        area = float(area)
        if not math.isfinite(area) or area <= 0:
            raise ValueError("Rollup colour requires a positive known model area")
        parent = h3.cell_to_parent(cell_id, target_resolution)
        grouped[parent][class_id].append(area)
    return {
        parent: {key: math.fsum(values.get(key, ())) for key in CLASS_ORDER}
        for parent, values in grouped.items()
    }


def colour_rollup_layers(
    layers: list[dict[str, Any]],
    source_cells: Iterable[tuple[str, str, float]],
    source_resolution: int,
    palette: Mapping[str, Mapping[str, str]],
) -> list[dict[str, Any]]:
    """Colour each coarse feature once; retain geometry and analytical facts.

    Every level uses native cells directly, avoiding majority-of-majorities.
    The dominant share in the popup makes the categorical simplification visible.
    Layer objects belong to this presentation call; cached result frames are not
    modified. Native display is unchanged.
    """
    source_cells = tuple(source_cells)
    for layer in layers:
        resolution = int(layer["auto_resolution"])
        if resolution >= source_resolution:
            continue
        areas = class_areas_by_parent(source_cells, resolution)
        for feature in layer["feature_collection"]["features"]:
            props = feature["properties"]
            by_class = areas[str(props["hex_id"])]
            dominant = max(CLASS_ORDER, key=by_class.__getitem__)
            total = math.fsum(by_class.values())
            share = by_class[dominant] / total * 100.0
            style = palette[dominant]
            label = str(style["label"])
            props.update(
                display_establishment_class=dominant,
                display_class_share_pct=share,
                display_class_areas_km2=by_class,
                fill=style["color"], stroke=style["stroke"], tooltip_title=label,
            )
            explanation = translate(
                "map.rollup.dominant", "sv", label=label, share=f"{share:.1f}",
            )
            old_class = f"Klass: {props['establishment_label']}<br>"
            props["popup"] = props["popup"].replace(
                old_class, html.escape(explanation) + "<br>", 1,
            )
    return layers
