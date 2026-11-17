"""Regular H3 parent outlines for maps; analytical support stays untouched."""
from __future__ import annotations

import json
from typing import Any

import streamlit as st
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from .geometry import _full_h3_geometry
from .i18n import translate


def _polygons(geometry):
    if geometry.geom_type == "Polygon":
        return [] if geometry.is_empty else [geometry]
    if hasattr(geometry, "geoms"):
        return [polygon for part in geometry.geoms for polygon in _polygons(part)]
    return []


@st.cache_data(show_spinner=False, max_entries=6, ttl=3600)
def _parent_geometries(
    region_id: str, footprint_json: str, parent_ids: tuple[str, ...],
) -> dict[str, dict[str, Any] | None]:
    # The explicit region and exact geometry bytes isolate cache entries. Input
    # freshness/revision checks still run upstream; only display geometry is held.
    footprint = unary_union([shape(g) for g in json.loads(footprint_json)])
    if footprint.is_empty or not footprint.is_valid:
        raise ValueError("Parent display requires a valid nonempty domain footprint")
    result = {}
    for cell_id in parent_ids:
        full = _full_h3_geometry(cell_id)
        if full is None:
            raise ValueError("Parent display received an invalid H3 cell")
        polygon = shape(full)
        if footprint.covers(polygon):
            result[cell_id] = full
        else:
            clipped = unary_union(_polygons(polygon.intersection(footprint)))
            # An analytical child can lie outside its geometric parent. Keep
            # its feature/values, using GeoJSON null for an empty display clip.
            result[cell_id] = None if clipped.is_empty else mapping(clipped)
    return result


def use_h3_parent_boundaries(
    layers: list[dict[str, Any]], source_resolution: int, region_id: str,
) -> list[dict[str, Any]]:
    """Draw parent boundaries clipped to the existing whole-domain footprint.

    A union of logical children has a serrated boundary rather than the parent's
    H3 boundary. Its whole-domain union remains the exact clipping footprint.
    Native features, parent IDs, classifications and numerical facts are retained.
    """
    coarse = [layer for layer in layers if int(layer["auto_resolution"]) < source_resolution]
    if not coarse:
        return layers
    footprint_layer = min(layers, key=lambda layer: int(layer["auto_resolution"]))
    footprint_json = json.dumps(
        [f["geometry"] for f in footprint_layer["feature_collection"]["features"]],
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    )
    cell_ids = tuple(sorted(
        str(f["properties"]["hex_id"])
        for layer in coarse for f in layer["feature_collection"]["features"]
    ))
    geometries = _parent_geometries(region_id, footprint_json, cell_ids)
    explanation = translate("map.rollup.geometry", "sv")
    for layer in coarse:
        empty_count = 0
        for feature in layer["feature_collection"]["features"]:
            feature["geometry"] = geometries[str(feature["properties"]["hex_id"])]
            empty_count += feature["geometry"] is None
            feature["properties"]["popup"] += "<br>" + explanation
        layer["display_geometry_policy"] = "h3_parent_clipped_to_domain"
        layer["display_geometry_empty_count"] = empty_count
    return layers
