from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import io
import json
import pickle
import re
import sys
import time
import zlib
from typing import Any

from .i18n import normalize_language, translate
from .i18n_catalog import MESSAGES
from .hex_legend import hex_area_legend_metadata


PRIMARY_RESULT_INTERACTION_ROLE = "primary_result"
_MAP_TRANSPORT_FORMAT = "shared_geometry_v1"
_MAP_COLLECTION_FIELDS = ("feature_collection", "reference_outline_feature_collection")
_MAP_BOOTSTRAP_FORMAT = "gzip_classic_map_v1"
_MAP_BOOTSTRAP_PREFIX = "\n    const mapBootstrap = "
_MAX_MAP_SCRIPT_BYTES = 512 * 1024 * 1024
_TRANSPORT_CACHE_MAX_BYTES = 16 * 1024 * 1024
_TRANSPORT_CACHE_TTL_SECONDS = 300
_MAP_CATALOG_PREFIXES = ("map.", "legend.", "result.", "source.", "solar.", "group.")
_MAP_SHARED_MESSAGE_IDS = frozenset({
    "ui.scenario", "ui.landscape", "ui.landscape_types", "ui.landscape_structures",
    "ui.landscape_factors", "ui.factor", "ui.h3_resolution", "ui.hex_display",
    "ui.establishment_area", "ui.acceptance", "ui.acceptance_impact",
    "ui.wind_potential", "ui.solar_potential", "ui.rooftop", "ui.ground_solar",
    "ui.potential_area", "ui.scenario_area", "ui.outside_area", "ui.population",
    "ui.population_points", "ui.panel_area_person", "ui.wind_share", "ui.solar_share",
    "ui.total_energy", "ui.core_areas", "ui.wind", "ui.solar", "ui.population_settlement",
    "ui.wind_hex", "ui.wind_establishment", "ui.solar_polygon", "ui.solar_hex",
    "ui.solar_establishment", "ui.level_middle",
})


def _map_presentation_catalog(language: str) -> dict[str, str]:
    """Export authored map copy, without landing/tutorial/analysis UI aliases.

    Scope is explicit message identity. No geometry/property traversal, provider
    name matching or text corpus inferred from the current GIS inputs is needed.
    Shared source/result namespaces retain map explanations and cached templates.
    Form manifests contribute category labels only, never notes or provenance.
    """
    selected = {
        key: values for key, values in MESSAGES.items()
        if key.startswith(_MAP_CATALOG_PREFIXES) or key in _MAP_SHARED_MESSAGE_IDS
        or (key.startswith("form.manifest.") and key.endswith(".label"))
        or (key.startswith("form.profile.") and key.endswith("_label"))
    }
    aliases = {values[3]: translate(key, language) for key, values in selected.items()}
    # Swedish authored aliases take precedence, as in the shared catalog.
    aliases.update({values[0]: translate(key, language) for key, values in selected.items()})
    return aliases


def _compress_layered_map_html(html: str) -> str:
    """Compress only transport bytes; execute the unchanged classic map script."""
    opening = "  <script>"
    start = html.index(opening + "\n    const mapTransport = ") + len(opening)
    end = html.rindex("</script>")
    script_bytes = html[start:end].encode("utf-8")
    if not 0 < len(script_bytes) <= _MAX_MAP_SCRIPT_BYTES:
        raise ValueError("Map initialization script exceeds the transport bound")
    envelope = {
        "format": _MAP_BOOTSTRAP_FORMAT,
        "script_bytes": len(script_bytes),
        "script_sha256": hashlib.sha256(script_bytes).hexdigest(),
        "script_gzip_base64": base64.b64encode(
            gzip.compress(script_bytes, compresslevel=1, mtime=0)
        ).decode("ascii"),
    }
    language = html.split('<html lang="', 1)[1].split('"', 1)[0] if '<html lang="' in html else "sv"
    messages = {key: translate(value, language) for key, value in {
        "browser": "Den här webbläsaren kan inte läsa kartans komprimerade data",
        "metadata": "Kartans överföring är ogiltig",
        "length": "Kartans datalängd stämmer inte",
        "checksum": "Kartans kontrollsumma stämmer inte",
        "load": "Kartan kunde inte laddas",
    }.items()}
    bootstrap = (_MAP_BOOTSTRAP_PREFIX + json.dumps(envelope, separators=(",", ":"))
                 + ";\n    const mapBootstrapMessages = "
                 + json.dumps(messages, ensure_ascii=False) + """;
    const mapBootstrapReady = (async function() {
      if (typeof DecompressionStream !== 'function' || !globalThis.crypto?.subtle) {
        throw new Error(mapBootstrapMessages.browser);
      }
      if (mapBootstrap.format !== 'gzip_classic_map_v1' ||
          !Number.isSafeInteger(mapBootstrap.script_bytes) ||
          mapBootstrap.script_bytes <= 0 || mapBootstrap.script_bytes > 536870912 ||
          !/^[0-9a-f]{64}$/.test(mapBootstrap.script_sha256)) {
        throw new Error(mapBootstrapMessages.metadata);
      }
      const compressed = Uint8Array.from(atob(mapBootstrap.script_gzip_base64), c => c.charCodeAt(0));
      const stream = new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'));
      const reader = stream.getReader();
      const chunks = [];
      let byteCount = 0;
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        byteCount += chunk.value.byteLength;
        if (byteCount > mapBootstrap.script_bytes) {
          await reader.cancel();
          throw new Error(mapBootstrapMessages.length);
        }
        chunks.push(chunk.value);
      }
      if (byteCount !== mapBootstrap.script_bytes) {
        throw new Error(mapBootstrapMessages.length);
      }
      const bytes = new Uint8Array(byteCount);
      let offset = 0;
      for (const chunk of chunks) {
        bytes.set(chunk, offset);
        offset += chunk.byteLength;
      }
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
        value => value.toString(16).padStart(2, '0')).join('');
      if (digest !== mapBootstrap.script_sha256) {
        throw new Error(mapBootstrapMessages.checksum);
      }
      const script = document.createElement('script');
      script.textContent = new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(bytes);
      // An ordinary script preserves the original global lexical bindings,
      // JavaScript numeric literals, Leaflet initialization and timer behavior.
      document.body.appendChild(script);
    })().catch(function(error) {
      const message = mapBootstrapMessages.load + ': ' + String(error.message || error);
      window.__potentialMapBootstrapError = message;
      const mapElement = document.getElementById('map');
      if (mapElement) mapElement.textContent = message;
      console.error(message);
    });
  """)
    return html[:start] + bootstrap + html[end:]


def unwrap_layered_map_html(html: str) -> str:
    """Recover the exact original HTML for validators, with bounded integrity checks.

    Older uncompressed maps pass through unchanged. This decodes the classic
    script as UTF-8, not JSON: legacy non-coordinate NaN literals retain their
    existing JavaScript meaning.
    """
    if _MAP_BOOTSTRAP_PREFIX not in html:
        return html
    if html.count(_MAP_BOOTSTRAP_PREFIX) != 1:
        raise ValueError("Ambiguous compressed map bootstrap")
    start = html.index(_MAP_BOOTSTRAP_PREFIX)
    if html[max(0, start - len("<script>")):start] != "<script>":
        raise ValueError("Invalid compressed map script boundary")
    end = html.find("</script>", start)
    if end < 0:
        raise ValueError("Missing compressed map script boundary")
    try:
        envelope, _ = json.JSONDecoder().raw_decode(html[start + len(_MAP_BOOTSTRAP_PREFIX):])
        if (
            not isinstance(envelope, dict)
            or set(envelope) != {"format", "script_bytes", "script_sha256", "script_gzip_base64"}
            or envelope["format"] != _MAP_BOOTSTRAP_FORMAT
            or type(envelope["script_bytes"]) is not int
            or not 0 < envelope["script_bytes"] <= _MAX_MAP_SCRIPT_BYTES
            or not isinstance(envelope["script_sha256"], str)
            or len(envelope["script_sha256"]) != 64
            or any(char not in "0123456789abcdef" for char in envelope["script_sha256"])
            or not isinstance(envelope["script_gzip_base64"], str)
            or len(envelope["script_gzip_base64"]) > ((_MAX_MAP_SCRIPT_BYTES + 1048576) * 4 // 3 + 4)
        ):
            raise ValueError("Invalid compressed map envelope")
        compressed = base64.b64decode(envelope["script_gzip_base64"], validate=True)
        with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
            script_bytes = stream.read(envelope["script_bytes"] + 1)
        if len(script_bytes) != envelope["script_bytes"]:
            raise ValueError("Map transport decompressed length mismatch")
        if hashlib.sha256(script_bytes).hexdigest() != envelope["script_sha256"]:
            raise ValueError("Map transport checksum mismatch")
        script = script_bytes.decode("utf-8")
    except (OSError, EOFError, UnicodeError, binascii.Error, ValueError, zlib.error) as exc:
        raise ValueError("Invalid compressed map transport: " + str(exc)) from exc
    return html[:start] + script + html[end:]


def _map_collection_features(collection: Any) -> list[dict[str, Any]]:
    if (
        not isinstance(collection, dict)
        or collection.get("type") != "FeatureCollection"
        or not isinstance(collection.get("features"), list)
        or any(not isinstance(feature, dict) for feature in collection["features"])
    ):
        raise ValueError("Map transport requires a GeoJSON FeatureCollection")
    return collection["features"]


def encode_layered_map_transport(layers: list[dict[str, Any]]) -> dict[str, Any]:
    """Share exact geometry bytes in transport; retain every logical map layer.

    No coordinate rounding, geometry processing, property removal or mutation
    of the caller's layers occurs. The browser restores the full layerSpecs
    before any existing Leaflet code runs.
    """
    if not isinstance(layers, list) or any(not isinstance(layer, dict) for layer in layers):
        raise TypeError("Map transport layers must be a list of objects")
    geometries: list[dict[str, Any]] = []
    geometry_indices: dict[str, int] = {}
    geometry_objects: dict[int, int] = {}
    packed_layers = []
    for layer in layers:
        packed = dict(layer)
        for field in _MAP_COLLECTION_FIELDS:
            collection = layer.get(field)
            if collection is None:
                continue
            features = []
            for feature in _map_collection_features(collection):
                geometry = feature.get("geometry")
                if geometry is None:
                    features.append(dict(feature))
                    continue
                if not isinstance(geometry, dict):
                    raise ValueError("Map feature geometry must be an object or null")
                # Call-scoped references remain alive in layers, so identities
                # cannot be recycled. Equal independent objects still use the
                # canonical content identity below.
                known_index = geometry_objects.get(id(geometry))
                if known_index is not None:
                    features.append(dict(feature, geometry=known_index))
                    continue
                canonical = json.dumps(
                    geometry, ensure_ascii=False, sort_keys=True,
                    separators=(",", ":"), allow_nan=False,
                )
                index = geometry_indices.get(canonical)
                if index is None:
                    index = len(geometries)
                    geometry_indices[canonical] = index
                    geometries.append(geometry)
                features.append(dict(feature, geometry=index))
                geometry_objects[id(geometry)] = index
            packed[field] = dict(collection, features=features)
        packed_layers.append(packed)
    return {"format": _MAP_TRANSPORT_FORMAT, "geometries": geometries, "layers": packed_layers}


def _layered_map_transport_json(layers, transport_cache=None):
    """Cache only packed collections; presentation attributes stay independent.

    The session owns at most one compressed entry for five non-sliding minutes.
    Every lookup hashes all collection content, including properties, outlines,
    order, missing fields and exact numeric types. No object-identity shortcut
    crosses calls. Region/scope ownership belongs to the presentation caller.
    """
    def dumps(value):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    if transport_cache is None:
        return dumps(encode_layered_map_transport(layers))
    collections = tuple(tuple((field, layer[field]) for field in _MAP_COLLECTION_FIELDS
                              if layer.get(field) is not None) for layer in layers)
    identity = hashlib.sha256(pickle.dumps(collections, protocol=5)).digest()
    entry = transport_cache.get('entry') if transport_cache is not None else None
    if entry is not None and entry[0] == identity and entry[1] > time.monotonic():
        geometry_json = zlib.decompress(entry[2]).decode('utf-8')
        packed_collections = tuple(tuple((field, zlib.decompress(encoded).decode('utf-8'))
                                        for field, encoded in fields) for fields in entry[3])
    else:
        packed = encode_layered_map_transport(layers)
        geometry_json = dumps(packed['geometries'])
        packed_collections = tuple(tuple((field, dumps(packed_layer[field]))
                                        for field, _collection in fields)
                                  for packed_layer, fields in zip(packed['layers'], collections))
        if transport_cache is not None:
            encoded = (identity, time.monotonic() + _TRANSPORT_CACHE_TTL_SECONDS,
                       zlib.compress(geometry_json.encode('utf-8'), level=1),
                       tuple(tuple((field, zlib.compress(value.encode('utf-8'), level=1))
                                   for field, value in fields) for fields in packed_collections))
            def size(value):
                return sys.getsizeof(value) + (sum(size(item) for item in value)
                                              if isinstance(value, tuple) else 0)
            transport_cache.clear()
            if size(encoded) + sys.getsizeof({'entry': None}) + sys.getsizeof('entry') <= _TRANSPORT_CACHE_MAX_BYTES:
                transport_cache['entry'] = encoded
    layer_json = []
    for layer, fields in zip(layers, packed_collections):
        metadata = dict(layer)
        for field, _value in fields:
            del metadata[field]
        members = dumps(metadata)[1:-1]
        collection_members = ','.join(dumps(field) + ':' + value for field, value in fields)
        layer_json.append('{' + members + (',' if members and collection_members else '')
                          + collection_members + '}')
    return ('{"format":' + dumps(_MAP_TRANSPORT_FORMAT) + ',"geometries":' + geometry_json
            + ',"layers":[' + ','.join(layer_json) + ']}')


def decode_layered_map_transport(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Mirror browser hydration for validation of the actual transport format."""
    if (
        not isinstance(payload, dict)
        or set(payload) != {"format", "geometries", "layers"}
        or payload["format"] != _MAP_TRANSPORT_FORMAT
        or not isinstance(payload["geometries"], list)
        or any(not isinstance(geometry, dict) for geometry in payload["geometries"])
        or not isinstance(payload["layers"], list)
        or any(not isinstance(layer, dict) for layer in payload["layers"])
    ):
        raise ValueError("Invalid map transport envelope")
    geometries = payload["geometries"]
    layers = []
    for packed in payload["layers"]:
        layer = dict(packed)
        for field in _MAP_COLLECTION_FIELDS:
            collection = packed.get(field)
            if collection is None:
                continue
            features = []
            for feature in _map_collection_features(collection):
                index = feature.get("geometry")
                if index is None:
                    features.append(dict(feature))
                    continue
                if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(geometries):
                    raise ValueError("Invalid map transport geometry reference")
                features.append(dict(feature, geometry=geometries[index]))
            layer[field] = dict(collection, features=features)
        layers.append(layer)
    return layers


def build_landscape_map_html(
    feature_collection: dict[str, Any],
    center: list[float],
    zoom: int,
    mode: str,
    title: str,
    bounds: list[list[float]] | None = None,
    fill_opacity: float = 0.72,
    legend_items: list[dict[str, str]] | None = None,
) -> str:
    payload = json.dumps(feature_collection, ensure_ascii=False)
    center_payload = json.dumps(center)
    bounds_payload = json.dumps(bounds)
    mode_payload = json.dumps(mode)
    title_payload = json.dumps(title, ensure_ascii=False)
    opacity_payload = json.dumps(max(0.0, min(1.0, float(fill_opacity))))
    legend_payload = json.dumps(legend_items or [], ensure_ascii=False)
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    html, body, #map {{ height: 100%; margin: 0; }}
    #map {{ min-height: 800px; border-radius: 4px; overflow: hidden; }}
    .leaflet-control-layers, .map-note, .map-legend {{ font-family: sans-serif; font-size: 12px; }}
    .map-note {{ background: rgba(255,255,255,0.94); padding: 8px 10px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.2); max-width: 240px; }}
    .map-legend {{ background: rgba(255,255,255,0.94); padding: 9px 10px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.2); line-height: 1.25; max-width: 260px; }}
    .map-legend-title {{ font-weight: 700; margin-bottom: 6px; }}
    .map-legend-row {{ display: flex; align-items: center; gap: 6px; margin: 4px 0; }}
    .map-legend-swatch {{ width: 14px; height: 14px; border: 1px solid rgba(0,0,0,0.22); flex: 0 0 auto; }}
    .map-legend-swatch.circle {{ width: 10px; height: 10px; border-radius: 999px; margin: 2px; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const data = {payload};
    const defaultCenter = {center_payload};
    const defaultBounds = {bounds_payload};
    const mode = {mode_payload};
    const mapTitle = {title_payload};
    const vectorLayerOpacity = {opacity_payload};
    const legendItems = {legend_payload};
    const map = L.map('map', {{ preferCanvas: true }}).setView(defaultCenter, {int(zoom)});

    const osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 20,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      maxZoom: 20,
      attribution: 'Tiles &copy; Esri'
    }});

    function styleFeature(feature) {{
      const props = feature.properties || {{}};
      const fill = mode === 'factor' ? props.factor_fill : props.cluster_fill;
      return {{
        color: mode === 'factor' ? '#666666' : '#444444',
        weight: mode === 'factor' ? 0.25 : 0.35,
        opacity: Math.min(0.85, hexFillOpacity + 0.1),
        fillColor: fill || '#999999',
        fillOpacity: hexFillOpacity
      }};
    }}

    const landscape = L.geoJSON(data, {{
      style: styleFeature,
      onEachFeature: function(feature, layer) {{
        const props = feature.properties || {{}};
        layer.bindPopup(props.popup || props.hex_id || mapTitle);
      }}
    }}).addTo(map);

    const overlays = {{}};
    overlays[mapTitle] = landscape;
    L.control.layers({{ 'OSM': osm, 'Satellite': satellite }}, overlays, {{ collapsed: true }}).addTo(map);
    L.control.scale({{ metric: true, imperial: false, maxWidth: 160 }}).addTo(map);

    const note = L.control({{ position: 'topright' }});
    note.onAdd = function() {{
      const div = L.DomUtil.create('div', 'map-note');
      div.innerHTML = '<strong>' + mapTitle + '</strong><br>' + (mode === 'factor' ? 'Faktorscore från manifest.' : 'Kluster från manifest.');
      L.DomEvent.disableClickPropagation(div);
      return div;
    }};
    note.addTo(map);

    if (legendItems.length > 0) {{
      const legend = L.control({{ position: 'bottomright' }});
      legend.onAdd = function() {{
        const div = L.DomUtil.create('div', 'map-legend');
        div.innerHTML = '<div class="map-legend-title">' + mapTitle + '</div>' +
          legendItems.map(function(item) {{
            const shapeClass = item.shape === 'circle' ? ' circle' : '';
            return '<div class="map-legend-row"><span class="map-legend-swatch' + shapeClass + '" style="background:' + item.color + '"></span><span>' + item.label + '</span></div>';
          }}).join('');
        L.DomEvent.disableClickPropagation(div);
        return div;
      }};
      legend.addTo(map);
    }}

    function fitInitialBounds() {{
      map.invalidateSize();
      if (defaultBounds && defaultBounds.length === 2) {{
        map.fitBounds(defaultBounds, {{ padding: [18, 18] }});
        return;
      }}
      const dataBounds = landscape.getBounds();
      if (dataBounds && dataBounds.isValid()) {{
        map.fitBounds(dataBounds.pad(0.04));
      }}
    }}
    setTimeout(fitInitialBounds, 80);
  </script>
</body>
</html>
"""


def _map_overlay_identity(spec: dict[str, Any]) -> str:
    """Persist overlay choices using source/role identity, never display text.

    Automatic resolutions represent one control. Explicit producer IDs take
    precedence for other layers; older producers use their neutral renderer
    contract. Ambiguous older layers are disambiguated in presentation metadata.
    """
    if spec.get("auto_resolution_group"):
        return "family:" + str(spec["auto_resolution_group"])
    for field in ("overlay_id", "workspace_layer_id", "layer_id", "id"):
        if spec.get(field):
            return "layer:" + str(spec[field])
    identity = {
        field: spec[field]
        for field in (
            "source_layer_id", "workspace_source_layer_id", "source_id",
            "legend_id", "layer_kind", "interaction_role", "technology",
            "algorithm", "role", "fill_property", "stroke_property",
            "stroke_weight_ratio_property", "factor", "group_id",
        )
        if spec.get(field) is not None
    }
    canonical = json.dumps(identity, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "renderer:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _map_layer_presentation(layers: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    """Small translated labels beside one unchanged geometry/property payload."""
    metadata: list[dict[str, Any]] = []
    used_ids: dict[str, int] = {}
    for spec in layers:
        overlay_id = _map_overlay_identity(spec)
        if not spec.get("auto_resolution_group"):
            occurrence = used_ids.get(overlay_id, 0)
            used_ids[overlay_id] = occurrence + 1
            if occurrence:
                if any(spec.get(field) for field in ("overlay_id", "workspace_layer_id", "layer_id", "id")):
                    raise ValueError(f"Map overlay ID is repeated: {overlay_id}")
                overlay_id += ":" + str(occurrence)
        metadata.append({
            "overlay_id": overlay_id,
            "legacy_names": list(dict.fromkeys(
                [str(spec["name"]), str(spec.get("control_name") or spec["name"])]
                + [translate(str(label), code)
                   for label in (spec["name"], spec.get("control_name") or spec["name"])
                   for code in ("sv", "nb", "da", "en")]
            )),
            "name": translate(str(spec.get("display_name") or spec["name"]), language),
            "control_name": translate(str(spec.get("display_control_name") or spec.get("control_name") or spec["name"]), language),
            "legend_title": translate(str(spec.get("legend_title") or spec.get("control_name") or spec["name"]), language),
            "legend_note": translate(str(spec.get("legend_note") or ""), language),
            "legend_items": [dict(item, label=translate(str(item.get("label") or ""), language))
                             for item in spec.get("legend_items") or []],
        })
    return metadata


def build_layered_hex_map_html(
    layers: list[dict[str, Any]],
    center: list[float],
    zoom: int,
    bounds: list[list[float]] | None = None,
    fill_opacity: float = 0.78,
    map_state_key: str | None = None,
    map_reset_token: int | str = 0,
    note_title: str = "Samlad potential",
    note_body: str = "Aktiva lager styrs i appen och kan även slås av/på i kartkontrollen.",
    pan_mode_label: str = "Panorera kartan",
    inspect_mode_label: str = "Granska potentiell etableringsyta",
    language: str = "sv",
    transport_cache: dict | None = None,
) -> str:
    language = normalize_language(language)
    overlay_keys: list[str] = []
    auto_family_controls: dict[str, str] = {}
    for index, layer in enumerate(layers):
        if not isinstance(layer, dict):
            raise TypeError(f"Map layer {index} must be an object")
        name = layer.get("name")
        if not isinstance(name, str) or not name or name != name.strip():
            raise ValueError(f"Map layer {index} has no exact display name")
        auto_group = layer.get("auto_resolution_group")
        if auto_group:
            if not isinstance(auto_group, str) or auto_group != auto_group.strip():
                raise ValueError(f"Map layer {name!r} has an invalid auto family")
            control_name = layer.get("control_name", name)
            if (
                not isinstance(control_name, str)
                or not control_name
                or control_name != control_name.strip()
            ):
                raise ValueError(f"Map layer {name!r} has no exact control name")
            existing = auto_family_controls.setdefault(auto_group, control_name)
            if existing != control_name:
                raise ValueError(
                    f"Map auto family {auto_group!r} has inconsistent control names"
                )
        else:
            overlay_keys.append(name)
    overlay_keys.extend(auto_family_controls.values())
    duplicate_overlay_keys = sorted(
        key for key in set(overlay_keys) if overlay_keys.count(key) > 1
    )
    if duplicate_overlay_keys:
        raise ValueError(
            "Map overlay names must be unique: "
            + ", ".join(duplicate_overlay_keys)
        )

    presentation = _map_layer_presentation(layers, language)
    display_controls: dict[str, str] = {}
    for spec, label in zip(layers, presentation):
        display_name = label["control_name"] if spec.get("auto_resolution_group") else label["name"]
        existing = display_controls.setdefault(display_name, label["overlay_id"])
        if existing != label["overlay_id"]:
            raise ValueError(f"Localized map overlay names must be unique: {display_name}")

    layers_payload = _layered_map_transport_json(layers, transport_cache)
    presentation_payload = json.dumps(presentation, ensure_ascii=False, separators=(",", ":"))
    hex_area_payload = json.dumps(hex_area_legend_metadata(layers), separators=(",", ":"))
    hex_labels_payload = json.dumps({
        key: translate("map.hex_size." + key, language)
        for key in ("title", "cell", "reference", "schematic", "schematic_sizes")
    }, ensure_ascii=False)
    catalog = _map_presentation_catalog(language)
    catalog_payload = json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
    templates = []
    for source, target in catalog.items():
        source = source.strip()
        fields = list(re.finditer(r"\{([A-Za-z_]\w*)\}", source))
        if not fields:
            continue
        fixed_text = re.sub(r"\{[A-Za-z_]\w*\}", "", source)
        if len(fixed_text.strip()) < 8 and source != "{label} R{resolution}":
            continue
        pattern = "^"
        end = 0
        for field in fields:
            pattern += re.escape(source[end:field.start()]) + "(.*?)"
            end = field.end()
        pattern += re.escape(source[end:]) + "$"
        templates.append({"pattern": pattern, "fields": [field[1] for field in fields], "target": target.strip()})
    templates_payload = json.dumps(templates, ensure_ascii=False, separators=(",", ":"))
    center_payload = json.dumps(center)
    bounds_payload = json.dumps(bounds)
    opacity_payload = json.dumps(max(0.0, min(1.0, float(fill_opacity))))
    map_state_key_payload = json.dumps(map_state_key or "")
    map_reset_token_payload = json.dumps(str(map_reset_token))
    note_title_payload = json.dumps(translate(str(note_title), language), ensure_ascii=False)
    note_body_payload = json.dumps(translate(str(note_body), language), ensure_ascii=False)
    pan_mode_label_payload = json.dumps(translate(str(pan_mode_label), language), ensure_ascii=False)
    inspect_mode_label_payload = json.dumps(
        translate(str(inspect_mode_label), language),
        ensure_ascii=False,
    )
    primary_interaction_role_payload = json.dumps(PRIMARY_RESULT_INTERACTION_ROLE)
    legend_title_payload = json.dumps(translate("Teckenförklaring", language), ensure_ascii=False)
    satellite_label_payload = json.dumps(translate("Satellit", language), ensure_ascii=False)
    zoom_in_label_payload = json.dumps(translate("Zooma in", language), ensure_ascii=False)
    zoom_out_label_payload = json.dumps(translate("Zooma ut", language), ensure_ascii=False)
    html = f"""
<!DOCTYPE html>
<html lang="{language}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <script>window.__potentialMapReady = false;</script>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    html, body, #map {{ height: 100%; margin: 0; }}
    #map {{ min-height: 800px; border-radius: 4px; overflow: hidden; }}
    .leaflet-control-layers, .map-note, .map-legend {{ font-family: sans-serif; font-size: 12px; }}
    .map-note, .map-legend {{ background: rgba(255,255,255,0.94); padding: 9px 10px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.2); max-width: 280px; }}
    .map-legend {{ line-height: 1.25; max-height: 420px; overflow-y: auto; }}
    .map-legend-title {{ font-weight: 700; margin-bottom: 7px; }}
    .map-legend-section {{ font-weight: 700; margin: 7px 0 4px; }}
    .map-legend-row {{ display: flex; align-items: center; gap: 6px; margin: 4px 0; }}
    .map-legend-note {{ color: #4b5563; font-size: 11px; line-height: 1.35; margin: 5px 0 7px; max-width: 250px; }}
    .map-legend-swatch {{ width: 14px; height: 14px; border: 1px solid rgba(0,0,0,0.22); flex: 0 0 auto; }}
    .map-legend-swatch.circle {{ width: 10px; height: 10px; border-radius: 999px; margin: 2px; }}
    .map-legend-hex {{ width: 18px; height: 20px; flex: 0 0 auto; color: #475569; }}
    .map-hex-size-row {{ align-items: center; gap: 8px; }}
    .scenario-marker-label {{ background: transparent; border: 0; font: 700 11px/18px sans-serif; text-align: center; white-space: nowrap; pointer-events: none; }}
    .map-interaction-control a {{
      align-items: center;
      color: #333;
      display: flex;
      height: 30px;
      justify-content: center;
      line-height: 30px;
      width: 30px;
    }}
    .map-interaction-control a.is-active {{
      background: #e8f0fe;
      box-shadow: inset 3px 0 0 #2563eb;
      color: #1d4ed8;
    }}
    .map-interaction-control svg {{
      fill: none;
      height: 18px;
      pointer-events: none;
      stroke: currentColor;
      stroke-linecap: round;
      stroke-linejoin: round;
      stroke-width: 1.8;
      width: 18px;
    }}
    #map .map-vector-pane,
    #map .map-vector-pane canvas,
    #map .map-vector-pane svg,
    #map .map-vector-pane .leaflet-interactive {{ pointer-events: none !important; }}
    #map.map-inspect-mode .map-primary-result-pane.map-primary-result-active,
    #map.map-inspect-mode .map-primary-result-pane.map-primary-result-active canvas,
    #map.map-inspect-mode .map-primary-result-pane.map-primary-result-active svg,
    #map.map-inspect-mode .map-primary-result-pane.map-primary-result-active .leaflet-interactive {{ pointer-events: auto !important; }}
    #map.map-inspect-mode,
    #map.map-inspect-mode .map-primary-result-pane.map-primary-result-active .leaflet-interactive {{ cursor: crosshair; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const mapTransport = {layers_payload};
    function hydrateLayerGeometries(payload) {{
      if (!payload || payload.format !== 'shared_geometry_v1'
          || Object.keys(payload).sort().join(',') !== 'format,geometries,layers'
          || !Array.isArray(payload.geometries) || !Array.isArray(payload.layers)
          || payload.geometries.some(geometry => !geometry || typeof geometry !== 'object' || Array.isArray(geometry))) {{
        throw new Error('Invalid map transport envelope');
      }}
      return payload.layers.map(packed => {{
        if (!packed || typeof packed !== 'object' || Array.isArray(packed)) {{
          throw new Error('Invalid map transport layer');
        }}
        const layer = {{...packed}};
        for (const field of ['feature_collection', 'reference_outline_feature_collection']) {{
          const collection = packed[field];
          if (collection === null || collection === undefined) continue;
          if (!collection || collection.type !== 'FeatureCollection' || !Array.isArray(collection.features)) {{
            throw new Error('Invalid map transport FeatureCollection');
          }}
          layer[field] = {{...collection, features: collection.features.map(feature => {{
            if (!feature || typeof feature !== 'object' || Array.isArray(feature)) {{
              throw new Error('Invalid map transport feature');
            }}
            const index = feature.geometry;
            if (index === null || index === undefined) return {{...feature}};
            if (!Number.isInteger(index) || index < 0 || index >= payload.geometries.length) {{
              throw new Error('Invalid map transport geometry reference');
            }}
            return {{...feature, geometry: payload.geometries[index]}};
          }})}};
        }}
        return layer;
      }});
    }}
    const layerSpecs = hydrateLayerGeometries(mapTransport);
    const defaultCenter = {center_payload};
    const defaultBounds = {bounds_payload};
    const vectorLayerOpacity = {opacity_payload};
    const mapStateKey = {map_state_key_payload};
    const mapResetToken = {map_reset_token_payload};
    const noteTitle = {note_title_payload};
    const noteBody = {note_body_payload};
    const panModeLabel = {pan_mode_label_payload};
    const inspectModeLabel = {inspect_mode_label_payload};
    const primaryInteractionRole = {primary_interaction_role_payload};
    const layerPresentation = {presentation_payload};
    const hexAreaMetadata = {hex_area_payload};
    const hexSizeLabels = {hex_labels_payload};
    const mapTextCatalog = {catalog_payload};
    const mapTextTemplates = {templates_payload}.map(function(item) {{
      return {{ pattern: new RegExp(item.pattern), fields: item.fields, target: item.target }};
    }});
    const legendTitle = {legend_title_payload};
    const satelliteLabel = {satellite_label_payload};

    function localizeMapText(value, depth) {{
      const text = String(value || '');
      const trimmed = text.trim();
      if (!trimmed || (depth || 0) > 3) return text;
      const padding = text.slice(0, text.indexOf(trimmed));
      const ending = text.slice(text.indexOf(trimmed) + trimmed.length);
      if (Object.prototype.hasOwnProperty.call(mapTextCatalog, trimmed)) {{
        return padding + mapTextCatalog[trimmed] + ending;
      }}
      for (const template of mapTextTemplates) {{
        const match = template.pattern.exec(trimmed);
        if (!match) continue;
        const params = {{}};
        template.fields.forEach(function(field, index) {{
          const captured = match[index + 1];
          params[field] = field === 'parts'
            ? captured.split(', ').map(function(part) {{ return localizeMapText(part, (depth || 0) + 1); }}).join(', ')
            : (['label', 'class_label', 'technology', 'context', 'priority'].includes(field)
              ? localizeMapText(captured, (depth || 0) + 1) : captured);
        }});
        return padding + template.target.replace(/\\{{([A-Za-z_]\\w*)\\}}/g,
          function(_all, field) {{ return params[field] === undefined ? _all : params[field]; }}) + ending;
      }}
      // Only authored field labels are localized. Numerical values, identifiers,
      // official source/scenario names and units remain byte-for-byte unchanged.
      const colon = trimmed.indexOf(': ');
      if (colon > 0) {{
        const label = trimmed.slice(0, colon);
        if (Object.prototype.hasOwnProperty.call(mapTextCatalog, label)) {{
          const rawValue = trimmed.slice(colon + 2);
          const localValue = ['Klass', 'Klassning', 'Teknik', 'Potential efter filter', 'Vind', 'Sol'].includes(label)
            ? localizeMapText(rawValue, (depth || 0) + 1) : rawValue;
          return padding + mapTextCatalog[label] + ': ' + localValue + ending;
        }}
      }}
      return text;
    }}

    function localizeFeatureText(value, spec) {{
      const text = String(value || '');
      // The contract-bound landscape layer presents its stable value ID beside
      // an authored category label. Keep that ID and source payload untouched.
      if (spec && String(spec.legend_id || '').startsWith('workspace_landscape_')) {{
        const trimmed = text.trim();
        const category = /^([A-Za-z0-9_.:-]+)( · )(.+)$/.exec(trimmed);
        if (category && (spec.legend_items || []).some(function(item) {{
          return item.label === category[3];
        }})) {{
          const prefix = text.slice(0, text.indexOf(trimmed));
          const ending = text.slice(text.indexOf(trimmed) + trimmed.length);
          return prefix + category[1] + category[2] + localizeMapText(category[3]) + ending;
        }}
      }}
      // The synthetic social-acceptance layer owns these scenario levels.
      // Capacity/provider scenario names retain their source identity elsewhere.
      if (spec && spec.legend_id === 'social_acceptance') {{
        const trimmed = text.trim();
        if (trimmed.startsWith('Scenario: ')) {{
          const prefix = text.slice(0, text.indexOf(trimmed));
          const ending = text.slice(text.indexOf(trimmed) + trimmed.length);
          return prefix + localizeMapText('Scenario') + ': '
            + localizeMapText(trimmed.slice('Scenario: '.length)) + ending;
        }}
      }}
      return localizeMapText(text);
    }}

    function localizeMapHtml(value, spec) {{
      const template = document.createElement('template');
      template.innerHTML = String(value || '');
      const walker = document.createTreeWalker(template.content, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = walker.nextNode())) {{
        node.nodeValue = localizeFeatureText(node.nodeValue, spec);
      }}
      return template.innerHTML;
    }}

    layerPresentation.forEach(function(item) {{
      item.name = localizeMapText(item.name);
      item.control_name = localizeMapText(item.control_name);
      item.legend_title = localizeMapText(item.legend_title);
      item.legend_note = localizeMapText(item.legend_note);
      item.legend_items.forEach(function(entry) {{ entry.label = localizeMapText(entry.label); }});
    }});

    function browserStorage() {{
      try {{
        const storage = window.localStorage;
        const testKey = '__regional_energy_potential_map_test__';
        storage.setItem(testKey, '1');
        storage.removeItem(testKey);
        return storage;
      }} catch (err) {{
        return null;
      }}
    }}

    const viewStorage = browserStorage();

    function storageKey(kind) {{
      return 'regional-energy-potential:' + mapStateKey + ':' + kind;
    }}

    function applyResetToken() {{
      if (!viewStorage || !mapStateKey) {{
        return false;
      }}
      const tokenKey = storageKey('reset-token');
      const previousToken = viewStorage.getItem(tokenKey);
      if (previousToken !== String(mapResetToken)) {{
        viewStorage.removeItem(storageKey('view'));
        viewStorage.removeItem(storageKey('overlays'));
        viewStorage.setItem(tokenKey, String(mapResetToken));
        return true;
      }}
      return false;
    }}

    const resetRequested = applyResetToken();

    function readSavedView() {{
      if (!viewStorage || !mapStateKey || resetRequested) {{
        return null;
      }}
      try {{
        const raw = viewStorage.getItem(storageKey('view'));
        if (!raw) {{
          return null;
        }}
        const parsed = JSON.parse(raw);
        const lat = Number(parsed.lat);
        const lng = Number(parsed.lng);
        const viewZoom = Number(parsed.zoom);
        if (
          Number.isFinite(lat) && Number.isFinite(lng) && Number.isFinite(viewZoom) &&
          lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180 &&
          viewZoom >= 0 && viewZoom <= 22
        ) {{
          return {{ lat, lng, zoom: viewZoom }};
        }}
      }} catch (err) {{}}
      return null;
    }}

    function readSavedOverlayVisibility() {{
      if (!viewStorage || !mapStateKey) {{
        return null;
      }}
      try {{
        const raw = viewStorage.getItem(storageKey('overlays'));
        if (!raw) {{
          return null;
        }}
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object') {{
          return null;
        }}
        return parsed;
      }} catch (err) {{}}
      return null;
    }}

    function restoredOverlayVisibility(record, fallback) {{
      if (!savedOverlayVisibility) return fallback;
      const keys = [record.id].concat(record.legacyNames || []);
      for (const key of keys) {{
        if (Object.prototype.hasOwnProperty.call(savedOverlayVisibility, key)) {{
          return Boolean(savedOverlayVisibility[key]);
        }}
      }}
      return fallback;
    }}

    function readSavedInteractionMode() {{
      if (!viewStorage || !mapStateKey) {{
        return 'pan';
      }}
      const storedMode = viewStorage.getItem(storageKey('interaction-mode'));
      return storedMode === 'inspect' ? 'inspect' : 'pan';
    }}

    function storeMapView() {{
      if (!viewStorage || !mapStateKey) {{
        return;
      }}
      const currentCenter = map.getCenter();
      viewStorage.setItem(
        storageKey('view'),
        JSON.stringify({{
          lat: currentCenter.lat,
          lng: currentCenter.lng,
          zoom: map.getZoom()
        }})
      );
    }}

    const savedView = readSavedView();
    const savedOverlayVisibility = readSavedOverlayVisibility();
    const mapStartCenter = savedView ? [savedView.lat, savedView.lng] : defaultCenter;
    const mapStartZoom = savedView ? savedView.zoom : {int(zoom)};
    const map = L.map('map', {{ preferCanvas: true, zoomControl: false }}).setView(mapStartCenter, mapStartZoom);
    L.control.zoom({{ zoomInTitle: {zoom_in_label_payload}, zoomOutTitle: {zoom_out_label_payload} }}).addTo(map);
    let interactionMode = readSavedInteractionMode();
    let panModeButton = null;
    let inspectModeButton = null;

    function storeInteractionMode() {{
      if (viewStorage && mapStateKey) {{
        viewStorage.setItem(storageKey('interaction-mode'), interactionMode);
      }}
    }}

    function closeOpenLayerDetails() {{
      const layers = [];
      map.eachLayer(function(layer) {{ layers.push(layer); }});
      layers.forEach(function(layer) {{
        try {{
          if (
            typeof layer.isTooltipOpen === 'function'
            && layer.isTooltipOpen()
            && typeof layer.closeTooltip === 'function'
          ) {{
            layer.closeTooltip();
          }}
          if (
            typeof layer.isPopupOpen === 'function'
            && layer.isPopupOpen()
            && typeof layer.closePopup === 'function'
          ) {{
            layer.closePopup();
          }}
        }} catch (error) {{
          console.warn('Could not close an open map detail.', error);
        }}
      }});
    }}

    function setInteractionMode(nextMode) {{
      interactionMode = nextMode === 'inspect' ? 'inspect' : 'pan';
      const inspectEnabled = interactionMode === 'inspect';
      const mapContainer = map.getContainer();
      mapContainer.classList.toggle('map-pan-mode', !inspectEnabled);
      mapContainer.classList.toggle('map-inspect-mode', inspectEnabled);
      if (inspectEnabled) {{
        map.dragging.disable();
      }} else {{
        map.dragging.enable();
      }}
      if (panModeButton) {{
        panModeButton.classList.toggle('is-active', !inspectEnabled);
        panModeButton.setAttribute('aria-pressed', String(!inspectEnabled));
      }}
      if (inspectModeButton) {{
        inspectModeButton.classList.toggle('is-active', inspectEnabled);
        inspectModeButton.setAttribute('aria-pressed', String(inspectEnabled));
      }}
      storeInteractionMode();
      if (!inspectEnabled) {{
        closeOpenLayerDetails();
      }}
      return interactionMode;
    }}

    function interactionSnapshot() {{
      const mapContainer = map.getContainer();
      const primaryPanes = Array.from(
        mapContainer.querySelectorAll('.map-primary-result-pane')
      );
      const visibleAutoFamilyResolutions = {{}};
      Object.values(autoFamilies).forEach(function(family) {{
        if (map.hasLayer(family.controller)) {{
          visibleAutoFamilyResolutions[family.controlName] =
            family.activeResolution;
        }}
      }});
      return {{
        mode: interactionMode,
        mapPanMode: mapContainer.classList.contains('map-pan-mode'),
        mapInspectMode: mapContainer.classList.contains('map-inspect-mode'),
        draggingEnabled: map.dragging.enabled(),
        panButtonPressed: panModeButton
          ? panModeButton.getAttribute('aria-pressed') === 'true'
          : null,
        inspectButtonPressed: inspectModeButton
          ? inspectModeButton.getAttribute('aria-pressed') === 'true'
          : null,
        primaryActivePaneCount: primaryPanes.filter(function(pane) {{
          return pane.classList.contains('map-primary-result-active');
        }}).length,
        primaryPointerEvents: primaryPanes.map(function(pane) {{
          return window.getComputedStyle(pane).pointerEvents;
        }}),
        visibleAutoFamilyResolutions: visibleAutoFamilyResolutions
      }};
    }}

    const osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 20,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      maxZoom: 20,
      attribution: 'Tiles &copy; Esri'
    }});

    function clamp01(value, fallbackValue) {{
      const parsed = Number(value);
      if (!Number.isFinite(parsed)) {{
        return fallbackValue;
      }}
      return Math.max(0.0, Math.min(1.0, parsed));
    }}

    function firstFiniteNumber(values, fallbackValue) {{
      for (const value of values) {{
        const parsed = Number(value);
        if (Number.isFinite(parsed)) {{
          return parsed;
        }}
      }}
      return fallbackValue;
    }}

    function layerFillOpacity(spec, feature) {{
      const props = (feature && feature.properties) || {{}};
      const defaultOpacity = spec.layer_kind === 'vector' ? 1.0 : 0.78;
      let baseOpacity = spec.fill_opacity != null ? clamp01(spec.fill_opacity, defaultOpacity) : defaultOpacity;
      if (spec.fill_opacity_property && props[spec.fill_opacity_property] != null) {{
        baseOpacity = clamp01(props[spec.fill_opacity_property], defaultOpacity);
      }}
      if (spec.layer_kind === 'vector') {{
        return clamp01(baseOpacity * vectorLayerOpacity, vectorLayerOpacity);
      }}
      return baseOpacity;
    }}

    function layerFillColor(spec, feature) {{
      const props = (feature && feature.properties) || {{}};
      if (spec.fill_property && props[spec.fill_property]) {{
        return props[spec.fill_property];
      }}
      return spec.fill_color || props.fill || props.cluster_fill || props.factor_fill || '#999999';
    }}

    function layerStrokeColor(spec, feature) {{
      const props = (feature && feature.properties) || {{}};
      if (spec.stroke_property && props[spec.stroke_property]) {{
        return props[spec.stroke_property];
      }}
      return spec.stroke_color || '#555555';
    }}

    function geometryPixelSpan(feature) {{
      const geometry = feature && feature.geometry;
      if (!geometry || !Array.isArray(geometry.coordinates)) {{
        return NaN;
      }}
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;

      function collectCoordinates(value) {{
        if (!Array.isArray(value)) {{
          return;
        }}
        if (
          value.length >= 2
          && Number.isFinite(Number(value[0]))
          && Number.isFinite(Number(value[1]))
        ) {{
          const point = map.latLngToLayerPoint([
            Number(value[1]),
            Number(value[0])
          ]);
          minX = Math.min(minX, point.x);
          minY = Math.min(minY, point.y);
          maxX = Math.max(maxX, point.x);
          maxY = Math.max(maxY, point.y);
          return;
        }}
        value.forEach(collectCoordinates);
      }}

      collectCoordinates(geometry.coordinates);
      if (![minX, minY, maxX, maxY].every(Number.isFinite)) {{
        return NaN;
      }}
      return Math.max(0.0, Math.min(maxX - minX, maxY - minY));
    }}

    function layerStrokeWeight(spec, feature, isPointLayer) {{
      const props = (feature && feature.properties) || {{}};
      const featureValue = spec.stroke_weight_property ? Number(props[spec.stroke_weight_property]) : NaN;
      let parsed = Number.isFinite(featureValue) ? featureValue : Number(spec.weight);
      const ratioValue = spec.stroke_weight_ratio_property
        ? Number(props[spec.stroke_weight_ratio_property])
        : Number(spec.stroke_weight_ratio);
      if (!isPointLayer && Number.isFinite(ratioValue) && ratioValue > 0.0) {{
        const pixelSpan = geometryPixelSpan(feature);
        if (Number.isFinite(pixelSpan) && pixelSpan > 0.0) {{
          const minimum = firstFiniteNumber([
            spec.stroke_weight_min_property
              ? props[spec.stroke_weight_min_property]
              : undefined,
            spec.stroke_weight_min
          ], 0.0);
          const maximum = Math.max(
            minimum,
            firstFiniteNumber([
              spec.stroke_weight_max_property
                ? props[spec.stroke_weight_max_property]
                : undefined,
              spec.stroke_weight_max
            ], Number.POSITIVE_INFINITY)
          );
          parsed = Math.max(
            minimum,
            Math.min(maximum, pixelSpan * ratioValue)
          );
        }}
      }}
      if (Number.isFinite(parsed)) {{
        return isPointLayer ? Math.max(parsed, 1.0) : parsed;
      }}
      return isPointLayer ? 1.0 : 0.25;
    }}

    function layerStrokeOpacity(spec, fillOpacity) {{
      const defaultOpacity = Math.min(0.85, fillOpacity + 0.1);
      const baseOpacity = spec.stroke_opacity != null
        ? clamp01(spec.stroke_opacity, defaultOpacity)
        : defaultOpacity;
      if (spec.layer_kind === 'vector') {{
        return clamp01(baseOpacity * vectorLayerOpacity, baseOpacity);
      }}
      if (spec.stroke_opacity != null) {{
        return clamp01(spec.stroke_opacity, defaultOpacity);
      }}
      return defaultOpacity;
    }}

    function layerStrokeEnabled(spec, strokeWeight, strokeOpacity) {{
      if (spec.stroke === false) {{
        return false;
      }}
      return strokeWeight > 0.01 && strokeOpacity > 0.01;
    }}

    function layerPointRadiusMetersAtScale(spec, feature) {{
      const props = (feature && feature.properties) || {{}};
      const radius = firstFiniteNumber([props.point_radius_m_at_scale, spec.point_radius_m_at_scale], NaN);
      return Number.isFinite(radius) && radius > 0 ? radius : null;
    }}

    function layerPointRadiusPixels(spec, feature, latlng) {{
      const props = (feature && feature.properties) || {{}};
      const fallbackRadius = firstFiniteNumber([props.point_radius, spec.point_radius], 4.0);
      const radiusMeters = layerPointRadiusMetersAtScale(spec, feature);
      if (radiusMeters === null) {{
        return fallbackRadius;
      }}
      const lat = Number.isFinite(Number(latlng && latlng.lat)) ? Number(latlng.lat) : Number(map.getCenter().lat);
      const cosLat = Math.max(0.05, Math.cos(lat * Math.PI / 180.0));
      const metersPerPixel = Math.max(0.0001, (40075016.686 * cosLat) / Math.pow(2, map.getZoom() + 8));
      const minRadius = Math.max(0.5, firstFiniteNumber([props.point_min_radius, spec.point_min_radius], 2.2));
      const maxRadius = Math.max(minRadius, firstFiniteNumber([props.point_max_radius, spec.point_max_radius], 4.6));
      return Math.max(minRadius, Math.min(maxRadius, radiusMeters / metersPerPixel));
    }}

    function popupHtml(spec, feature) {{
      const props = (feature && feature.properties) || {{}};
      if (props.popup) {{
        return localizeMapHtml(props.popup, spec);
      }}
      const title = props.tooltip_title || props.layer_label || spec.name;
      const body = props.tooltip_body || '';
      return localizeMapHtml(body ? ('<strong>' + title + '</strong><br>' + body) : (props.hex_id || title), spec);
    }}

    const overlays = {{}};
    const renderedLayers = [];
    const layerRecords = [];
    const legendSourceRecords = [];
    const scalablePointMarkers = [];
    const zoomScaledStyleRecords = [];
    const scenarioMarkerLayerRecords = [];
    const autoFamilies = {{}};

    function setPrimaryLayerInputActive(layer, active) {{
      const paneName = layer && layer.options ? layer.options.pane : null;
      const pane = paneName ? map.getPane(paneName) : null;
      if (pane && pane.classList.contains('map-primary-result-pane')) {{
        pane.classList.toggle('map-primary-result-active', Boolean(active));
      }}
    }}

    function layerFeatureStyle(spec, feature) {{
      const fillOpacity = layerFillOpacity(spec, feature);
      const strokeWeight = layerStrokeWeight(spec, feature, false);
      const strokeOpacity = layerStrokeOpacity(spec, fillOpacity);
      const strokeEnabled = layerStrokeEnabled(
        spec,
        strokeWeight,
        strokeOpacity
      );
      return {{
        stroke: strokeEnabled,
        color: layerStrokeColor(spec, feature),
        weight: strokeEnabled ? strokeWeight : 0,
        opacity: strokeEnabled ? strokeOpacity : 0,
        dashArray: spec.dash_array || null,
        fillColor: layerFillColor(spec, feature),
        fillOpacity: fillOpacity
      }};
    }}

    function refreshScenarioMarkerMetrics(record) {{
      const zoom = map.getZoom();
      if (record.zoom === zoom) return;
      record.zoom = zoom;
      record.markers.forEach(function(marker) {{
        // Source polygons already match the potential layer. Measure their
        // projected bounds for labels without changing any displayed geometry.
        const bounds = marker.path.getBounds();
        if (!bounds.isValid()) return;
        const northwest = map.project(bounds.getNorthWest(), zoom);
        const southeast = map.project(bounds.getSouthEast(), zoom);
        const center = L.point((northwest.x + southeast.x) / 2,
          (northwest.y + southeast.y) / 2);
        marker.center = map.unproject(center, zoom);
        marker.pixelSpan = Math.min(Math.abs(southeast.x - northwest.x),
          Math.abs(southeast.y - northwest.y));
      }});
    }}

    function refreshScenarioMarkerLabels(record) {{
      const spec = record.spec;
      const visibleBounds = map.getBounds().pad(0.1);
      const labelThreshold = firstFiniteNumber([spec.scenario_marker_label_min_pixels], 18);
      record.markers.forEach(function(marker) {{
        const props = marker.feature.properties || {{}};
        if (props.marker_label && marker.pixelSpan >= labelThreshold
            && marker.center && visibleBounds.contains(marker.center)) {{
          if (!marker.label) {{
            const text = document.createElement('span');
            text.textContent = String(props.marker_label);
            text.style.color = props.marker_label_color || '#ffffff';
            if (String(props.marker_label).length > 1) text.style.fontSize = '9px';
            marker.label = L.marker(marker.center, {{
              pane: record.paneName, interactive: false, keyboard: false,
              opacity: layerFillOpacity(spec, marker.feature),
              icon: L.divIcon({{ className: 'scenario-marker-label', html: text,
                iconSize: [30, 18], iconAnchor: [15, 9] }})
            }});
          }}
          marker.label.setLatLng(marker.center);
          record.decorations.addLayer(marker.label);
        }} else if (marker.label) {{
          record.decorations.removeLayer(marker.label);
        }}
      }});
    }}

    function refreshScenarioMarkers() {{
      scenarioMarkerLayerRecords.forEach(function(record) {{
        if (map.hasLayer(record.layer)) {{
          refreshScenarioMarkerMetrics(record);
          refreshScenarioMarkerLabels(record);
        }}
      }});
    }}

    function refreshVisibleScenarioMarkerLabels() {{
      scenarioMarkerLayerRecords.forEach(function(record) {{
        if (map.hasLayer(record.layer)) refreshScenarioMarkerLabels(record);
      }});
    }}

    function buildGeoJsonLayer(spec, index) {{
      const paneName = 'overlay-pane-' + index;
      const pane = map.createPane(paneName);
      const zIndex = Number.isFinite(Number(spec.z_index)) ? Number(spec.z_index) : (400 + index);
      const inspectable = spec.interaction_role === primaryInteractionRole;
      pane.style.zIndex = String(zIndex);
      pane.classList.add('map-vector-pane');
      if (inspectable) {{
        pane.classList.add('map-primary-result-pane');
      }}

      const scenarioMarkers = Number(spec.scenario_marker_label_min_pixels) > 0
        ? {{ spec, paneName, markers: [], decorations: L.layerGroup(), zoom: null }}
        : null;

      // Keep a lightweight GeoJSON shell for controls and resolution families.
      // Feature paths, styles, outlines and popups are created on first display.
      const layer = L.geoJSON(null, {{
        pane: paneName,
        interactive: inspectable,
        style: function(feature) {{
          return layerFeatureStyle(spec, feature);
        }},
        pointToLayer: function(feature, latlng) {{
          const fillOpacity = layerFillOpacity(spec, feature);
          const strokeWeight = layerStrokeWeight(spec, feature, true);
          const strokeOpacity = layerStrokeOpacity(spec, fillOpacity);
          const strokeEnabled = layerStrokeEnabled(spec, strokeWeight, strokeOpacity);
          const marker = L.circleMarker(latlng, {{
            radius: layerPointRadiusPixels(spec, feature, latlng),
            pane: paneName,
            interactive: inspectable,
            stroke: strokeEnabled,
            color: layerStrokeColor(spec, feature),
            weight: strokeEnabled ? strokeWeight : 0,
            opacity: strokeEnabled ? strokeOpacity : 0,
            dashArray: spec.dash_array || null,
            fillColor: layerFillColor(spec, feature),
            fillOpacity: Math.max(fillOpacity, 0.22)
          }});
          if (layerPointRadiusMetersAtScale(spec, feature) !== null) {{
            scalablePointMarkers.push({{ marker, spec, feature, latlng }});
          }}
          return marker;
        }},
        onEachFeature: function(feature, itemLayer) {{
          if (scenarioMarkers && feature.geometry
              && ['Polygon', 'MultiPolygon'].includes(feature.geometry.type)) {{
            scenarioMarkers.markers.push({{ feature, path: itemLayer, label: null }});
          }}
          if (!inspectable) {{
            return;
          }}
          const props = (feature && feature.properties) || {{}};
          if (props.tooltip_title || props.tooltip_body) {{
            const tooltipTitle = props.tooltip_title || props.hex_id || spec.name;
            const tooltipBody = props.tooltip_body || '';
            itemLayer.bindTooltip(
              function() {{ return localizeMapHtml(tooltipBody ? ('<strong>' + tooltipTitle + '</strong><br>' + tooltipBody) : tooltipTitle, spec); }},
              {{ sticky: true, direction: 'top', opacity: 0.92 }}
            );
          }}
          itemLayer.bindPopup(function() {{ return popupHtml(spec, feature); }});
        }}
      }});
      let materialized = false;
      function materialize() {{
        if (materialized) return;
        materialized = true;
        layer.addData(spec.feature_collection);
        const referenceOutline = spec.reference_outline_feature_collection;
        // Potential features already have thin class-coloured edges. Adding the
        // regular H3 reference grid adds heavier edges at coarser resolutions.
        if (spec.legend_id !== 'combined_establishment' && referenceOutline && Array.isArray(referenceOutline.features)) {{
          layer.addLayer(L.geoJSON(referenceOutline, {{
            pane: paneName,
            interactive: false,
            style: function() {{
              return {{
                stroke: true,
                color: spec.reference_outline_color || '#f8fafc',
                weight: firstFiniteNumber([spec.reference_outline_weight], 0.58),
                opacity: clamp01(spec.reference_outline_opacity, 0.72),
                fill: false,
                fillOpacity: 0
              }};
            }}
          }}));
        }}
      }}
      layer.on('add', materialize);
      if (scenarioMarkers) {{
        scenarioMarkers.layer = layer;
        scenarioMarkerLayerRecords.push(scenarioMarkers);
        layer.on('add', function() {{
          refreshScenarioMarkerMetrics(scenarioMarkers);
          refreshScenarioMarkerLabels(scenarioMarkers);
          scenarioMarkers.decorations.addTo(map);
        }});
        layer.on('remove', function() {{ map.removeLayer(scenarioMarkers.decorations); }});
      }}
      return layer;
    }}

    function layerDataBounds(spec) {{
      // Fitting the initial view must not materialize hidden/native layers.
      let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
      function coordinates(value) {{
        if (!Array.isArray(value) || !value.length) return;
        if (typeof value[0] === 'number') {{
          west = Math.min(west, value[0]); east = Math.max(east, value[0]);
          south = Math.min(south, value[1]); north = Math.max(north, value[1]);
        }} else value.forEach(coordinates);
      }}
      function geometry(value) {{
        if (!value) return;
        if (value.type === 'GeometryCollection') (value.geometries || []).forEach(geometry);
        else coordinates(value.coordinates);
      }}
      [spec.feature_collection, spec.legend_id === 'combined_establishment'
        ? null : spec.reference_outline_feature_collection].forEach(function(collection) {{
        if (collection) (collection.features || []).forEach(function(feature) {{ geometry(feature.geometry); }});
      }});
      return Number.isFinite(west) ? L.latLngBounds([[south, west], [north, east]]) : L.latLngBounds([]);
    }}

    function refreshScalablePointMarkers() {{
      scalablePointMarkers.forEach(function(record) {{
        record.marker.setRadius(layerPointRadiusPixels(record.spec, record.feature, record.latlng));
      }});
    }}

    layerSpecs.forEach(function(spec, index) {{
      const presentation = layerPresentation[index];
      const layer = buildGeoJsonLayer(spec, index);
      renderedLayers.push(layer);
      if (
        spec.stroke_weight_ratio_property
        || Number.isFinite(Number(spec.stroke_weight_ratio))
      ) {{
        zoomScaledStyleRecords.push({{ spec, layer }});
      }}
      if (spec.legend_items && spec.legend_items.length > 0) {{
        legendSourceRecords.push({{ spec, layer, presentation, hexArea: hexAreaMetadata[index] }});
      }}

      const autoGroupId = spec.auto_resolution_group || '';
      if (autoGroupId) {{
        if (!autoFamilies[autoGroupId]) {{
          autoFamilies[autoGroupId] = {{
            id: autoGroupId,
            controlName: presentation.control_name,
            overlayId: presentation.overlay_id,
            legacyNames: presentation.legacy_names,
            selectedResolution: Number(spec.selected_resolution),
            lockSelectedResolution: Boolean(spec.lock_selected_resolution),
            defaultVisible: spec.default_visible !== false,
            controller: L.layerGroup(),
            activeResolution: null,
            activeLayer: null,
            layers: []
          }};
        }}
        autoFamilies[autoGroupId].layers.push({{
          resolution: Number(spec.auto_resolution),
          minZoom: Number.isFinite(Number(spec.auto_min_zoom)) ? Number(spec.auto_min_zoom) : 0,
          layer: layer
        }});
        return;
      }}

      overlays[presentation.name] = layer;
      const record = {{ id: presentation.overlay_id, name: presentation.name, legacyNames: presentation.legacy_names, layer: layer, spec: spec }};
      layerRecords.push(record);
      const shouldShow = restoredOverlayVisibility(record, spec.default_visible !== false);
      if (shouldShow) {{
        layer.addTo(map);
        setPrimaryLayerInputActive(layer, true);
      }}
    }});

    const autoFamilyRecords = Object.values(autoFamilies);

    function refreshZoomScaledLayerStyles() {{
      zoomScaledStyleRecords.forEach(function(record) {{
        if (map.hasLayer(record.layer)) {{
          record.layer.setStyle(function(feature) {{
            return layerFeatureStyle(record.spec, feature);
          }});
        }}
      }});
      refreshScenarioMarkers();
    }}

    function roundScaleValue(num) {{
      const digits = Math.pow(10, String(Math.floor(num)).length - 1);
      const normalized = num / digits;
      let rounded = digits;
      if (normalized >= 10) {{
        rounded = 10 * digits;
      }} else if (normalized >= 5) {{
        rounded = 5 * digits;
      }} else if (normalized >= 3) {{
        rounded = 3 * digits;
      }} else if (normalized >= 2) {{
        rounded = 2 * digits;
      }}
      return rounded;
    }}

    function currentMetricScaleValue() {{
      const maxWidth = 160;
      const centerY = map.getSize().y / 2;
      const leftPoint = map.containerPointToLatLng([0, centerY]);
      const rightPoint = map.containerPointToLatLng([maxWidth, centerY]);
      const maxMeters = map.distance(leftPoint, rightPoint);
      if (!Number.isFinite(maxMeters) || maxMeters <= 0) {{
        return 0;
      }}
      return roundScaleValue(maxMeters);
    }}

    function autoResolutionFromScale(selectedResolution, scaleMeters) {{
      let desiredResolution = 10;
      if (scaleMeters >= 100000) {{
        desiredResolution = 5;
      }} else if (scaleMeters >= 50000) {{
        desiredResolution = 6;
      }} else if (scaleMeters >= 20000) {{
        desiredResolution = 7;
      }} else if (scaleMeters >= 10000) {{
        desiredResolution = 8;
      }} else if (scaleMeters >= 5000) {{
        desiredResolution = 9;
      }}
      return Math.min(Number(selectedResolution), desiredResolution);
    }}

    function desiredAutoFamilyEntry(family) {{
      const sortedLayers = family.layers
        .slice()
        .sort(function(left, right) {{ return right.resolution - left.resolution; }});
      if (sortedLayers.length === 0) {{
        return null;
      }}

      if (family.lockSelectedResolution) {{
        const locked = sortedLayers.find(function(entry) {{ return entry.resolution === family.selectedResolution; }});
        return locked || sortedLayers[0];
      }}

      const selectedResolution = Number.isFinite(family.selectedResolution)
        ? family.selectedResolution
        : sortedLayers[0].resolution;
      const scaleMeters = currentMetricScaleValue();
      const desiredResolution = autoResolutionFromScale(selectedResolution, scaleMeters);
      const eligible = sortedLayers.filter(function(entry) {{ return entry.resolution <= desiredResolution; }});
      return eligible[0] || sortedLayers[sortedLayers.length - 1];
    }}

    function syncAutoFamily(family) {{
      const desired = desiredAutoFamilyEntry(family);
      if (!desired) {{
        return;
      }}

      family.layers.forEach(function(entry) {{
        setPrimaryLayerInputActive(entry.layer, false);
      }});

      if (family.activeLayer && family.activeLayer !== desired.layer) {{
        family.controller.removeLayer(family.activeLayer);
      }}

      family.activeLayer = desired.layer;
      family.activeResolution = desired.resolution;

      if (!map.hasLayer(family.controller)) {{
        family.controller.clearLayers();
        return;
      }}

      if (!family.controller.hasLayer(desired.layer)) {{
        family.controller.clearLayers();
        family.controller.addLayer(desired.layer);
      }}
      setPrimaryLayerInputActive(desired.layer, true);
    }}

    autoFamilyRecords.forEach(function(family) {{
      overlays[family.controlName] = family.controller;
      const record = {{ id: family.overlayId, name: family.controlName, legacyNames: family.legacyNames, layer: family.controller, family: family }};
      layerRecords.push(record);
      const shouldShow = restoredOverlayVisibility(record, family.defaultVisible);
      if (shouldShow) {{
        family.controller.addTo(map);
        syncAutoFamily(family);
      }}
    }});

    const baseLayers = {{ 'OSM': osm }};
    baseLayers[satelliteLabel] = satellite;
    L.control.layers(baseLayers, overlays, {{ collapsed: true }}).addTo(map);
    L.control.scale({{ metric: true, imperial: false, maxWidth: 160 }}).addTo(map);

    function createInteractionButton(container, modeValue, label, iconHtml) {{
      const button = L.DomUtil.create('a', 'map-interaction-button', container);
      button.href = '#';
      button.innerHTML = iconHtml;
      button.title = label;
      button.setAttribute('aria-label', label);
      button.setAttribute('aria-pressed', 'false');
      button.setAttribute('role', 'button');
      L.DomEvent.on(button, 'click', function(event) {{
        L.DomEvent.stop(event);
        setInteractionMode(modeValue);
      }});
      L.DomEvent.on(button, 'keydown', function(event) {{
        if (event.key === ' ' || event.key === 'Enter') {{
          L.DomEvent.stop(event);
          setInteractionMode(modeValue);
        }}
      }});
      return button;
    }}

    const interactionControl = L.control({{ position: 'topleft' }});
    interactionControl.onAdd = function() {{
      const container = L.DomUtil.create('div', 'leaflet-bar map-interaction-control');
      panModeButton = createInteractionButton(
        container,
        'pan',
        panModeLabel,
        '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7.5 11V7a1.5 1.5 0 0 1 3 0v3M10.5 10V5.5a1.5 1.5 0 0 1 3 0V10M13.5 10V7a1.5 1.5 0 0 1 3 0v4M7.5 10.5 6 9.5a1.6 1.6 0 0 0-2.1 2.4l4.5 6.2A4.5 4.5 0 0 0 12 20h1.5a5 5 0 0 0 5-5v-4.5a1.5 1.5 0 0 0-3 0V12"/></svg>'
      );
      inspectModeButton = createInteractionButton(
        container,
        'inspect',
        inspectModeLabel,
        '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M12 10.5V16M12 7.5h.01"/></svg>'
      );
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.disableScrollPropagation(container);
      return container;
    }};
    interactionControl.addTo(map);
    setInteractionMode(interactionMode);

    function storeOverlayVisibility() {{
      if (!viewStorage || !mapStateKey) {{
        return;
      }}
      const payload = {{}};
      layerRecords.forEach(function(record) {{
        payload[record.id] = map.hasLayer(record.layer);
      }});
      viewStorage.setItem(storageKey('overlays'), JSON.stringify(payload));
    }}
    map.on('overlayadd', function(event) {{
      setPrimaryLayerInputActive(event.layer, true);
      autoFamilyRecords.forEach(function(family) {{
        if (event.layer === family.controller) {{
          syncAutoFamily(family);
        }}
      }});
      refreshZoomScaledLayerStyles();
      storeOverlayVisibility();
      updateLegendContent();
    }});
    map.on('overlayremove', function(event) {{
      setPrimaryLayerInputActive(event.layer, false);
      autoFamilyRecords.forEach(function(family) {{
        if (event.layer === family.controller) {{
          family.controller.clearLayers();
        }}
      }});
      storeOverlayVisibility();
      updateLegendContent();
    }});
    map.on('moveend', function() {{
      refreshVisibleScenarioMarkerLabels();
      storeMapView();
    }});
    map.on('zoomend', function() {{
      autoFamilyRecords.forEach(syncAutoFamily);
      refreshZoomScaledLayerStyles();
      refreshScalablePointMarkers();
      storeMapView();
      updateLegendContent();
    }});
    storeOverlayVisibility();

    function recordLayerFeatureCount(layer) {{
      if (!layer || typeof layer.getLayers !== 'function') {{
        return 0;
      }}
      const children = layer.getLayers();
      if (!children || children.length === 0) {{
        return 0;
      }}
      return children.reduce(function(total, child) {{
        if (child && typeof child.getLayers === 'function') {{
          return total + recordLayerFeatureCount(child);
        }}
        return total + 1;
      }}, 0);
    }}

    function resolveLayerRecord(name) {{
      const wanted = String(name || '');
      return layerRecords.find(function(item) {{
        return item.id === wanted || item.name === wanted || (item.legacyNames || []).includes(wanted);
      }});
    }}

    function setOverlayVisibilityByName(name, visible) {{
      const wanted = String(name || '');
      const record = resolveLayerRecord(wanted);
      if (!record) {{
        return false;
      }}
      const shouldShow = Boolean(visible);
      if (shouldShow && !map.hasLayer(record.layer)) {{
        record.layer.addTo(map);
      }} else if (!shouldShow && map.hasLayer(record.layer)) {{
        map.removeLayer(record.layer);
      }}
      if (record.family) {{
        if (shouldShow) {{
          syncAutoFamily(record.family);
        }} else {{
          record.family.layers.forEach(function(entry) {{
            setPrimaryLayerInputActive(entry.layer, false);
          }});
          record.family.controller.clearLayers();
        }}
      }} else {{
        setPrimaryLayerInputActive(record.layer, shouldShow);
      }}
      refreshZoomScaledLayerStyles();
      storeOverlayVisibility();
      updateLegendContent();
      return true;
    }}

    window.__potentialMapSetOverlayVisibility = setOverlayVisibilityByName;
    window.__potentialMapOverlayVisible = function(name) {{
      const wanted = String(name || '');
      const record = resolveLayerRecord(wanted);
      return Boolean(record && map.hasLayer(record.layer));
    }};
    window.__potentialMapOverlayKnown = function(name) {{
      const wanted = String(name || '');
      return Boolean(resolveLayerRecord(wanted));
    }};
    window.__potentialMapOverlayFeatureCount = function(name) {{
      const wanted = String(name || '');
      const record = resolveLayerRecord(wanted);
      return record ? recordLayerFeatureCount(record.layer) : 0;
    }};
    window.__potentialMapSetZoom = function(zoomValue) {{
      const requested = Number(zoomValue);
      if (!Number.isFinite(requested)) {{
        return map.getZoom();
      }}
      map.setZoom(requested);
      return map.getZoom();
    }};
    window.__potentialMapScaleMeters = currentMetricScaleValue;
    window.__potentialMapZoomScaledStyleState = function() {{
      return zoomScaledStyleRecords
        .filter(function(record) {{ return map.hasLayer(record.layer); }})
        .map(function(record) {{
          const classes = {{}};
          record.layer.eachLayer(function(item) {{
            const props = item && item.feature && item.feature.properties
              ? item.feature.properties
              : {{}};
            const classId = String(props.allocation_class || 'unclassified');
            const weight = Number(item && item.options ? item.options.weight : NaN);
            if (!Number.isFinite(weight)) {{
              return;
            }}
            if (!classes[classId]) {{
              classes[classId] = {{ count: 0, min: weight, max: weight }};
            }}
            classes[classId].count += 1;
            classes[classId].min = Math.min(classes[classId].min, weight);
            classes[classId].max = Math.max(classes[classId].max, weight);
          }});
          return {{
            name: record.spec.control_name || record.spec.name,
            resolution: Number(record.spec.auto_resolution),
            scaleMeters: currentMetricScaleValue(),
            classes: classes
          }};
        }});
    }};
    window.__potentialMapSetInteractionMode = setInteractionMode;
    window.__potentialMapInteractionMode = function() {{ return interactionMode; }};
    window.__potentialMapInteractionState = interactionSnapshot;
    window.__potentialMapOverlayIds = function() {{
      return layerRecords.map(function(record) {{ return {{ id: record.id, name: record.name }}; }});
    }};

    const note = L.control({{ position: 'topright' }});
    note.onAdd = function() {{
      const div = L.DomUtil.create('div', 'map-note');
      div.innerHTML = '<strong>' + localizeMapHtml(noteTitle) + '</strong><br>' + localizeMapHtml(noteBody);
      L.DomEvent.disableClickPropagation(div);
      return div;
    }};
    note.addTo(map);

    let legendDiv = null;
    function legendSwatchStyle(item) {{
      const fill = item && item.color ? item.color : '#999999';
      const border = item && item.border_color
        ? item.border_color
        : 'rgba(0,0,0,0.22)';
      const requestedWidth = item && item.border_width != null ? Number(item.border_width) : NaN;
      const borderWidth = Number.isFinite(requestedWidth)
        ? Math.max(0, Math.min(4, requestedWidth))
        : 1;
      return 'background:' + fill + ';border:' + borderWidth +
        'px solid ' + border + ';box-sizing:border-box';
    }}
    function legendSwatchHtml(item) {{
      const shapeClass = item.shape === 'circle' ? ' circle' : '';
      const swatch = document.createElement('span');
      swatch.className = 'map-legend-swatch' + shapeClass;
      swatch.setAttribute('style', legendSwatchStyle(item));
      return swatch.outerHTML;
    }}
    function legendRecordVisible(record) {{
      const family = autoFamilies[record.spec.auto_resolution_group || ''];
      return family
        ? map.hasLayer(family.controller) && family.activeLayer === record.layer
        : map.hasLayer(record.layer);
    }}

    const hexAreaNumber = new Intl.NumberFormat({json.dumps(language)}, {{ maximumSignificantDigits: 3 }});
    function hexAreaRow(label, area, count, kind, resolution) {{
      const row = document.createElement('div');
      row.className = 'map-legend-row map-hex-size-row';
      row.dataset.hexKind = kind;
      row.dataset.hexAreaKm2 = String(area);
      if (resolution != null) row.dataset.hexResolution = String(resolution);
      row.innerHTML = '<svg class="map-legend-hex" viewBox="0 0 20 22" aria-hidden="true"><polygon points="10,1 19,6 19,16 10,21 1,16 1,6" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';
      const text = document.createElement('span');
      const heading = document.createElement('span');
      heading.textContent = label;
      const value = document.createElement('span');
      const measure = hexAreaNumber.format(area) + ' km² · ' + hexAreaNumber.format(area * 100) + ' ha';
      value.textContent = kind === 'h3' ? '≈ ' + measure
        : (count > 1 ? count + ' × (' + measure + ')' : measure);
      if (label) text.append(heading, document.createElement('br'));
      text.appendChild(value);
      row.appendChild(text);
      return row.outerHTML;
    }}

    function hexAreaLegendContent(records) {{
      // Potential cells are the primary reference when scenario cells at the
      // same resolution are also visible. These are regional full-cell means,
      // independent of clipped outlines and allocated/potential area.
      const byResolution = new Map();
      records.filter(function(record) {{ return record.hexArea?.kind === 'h3'; }})
        .sort(function(a, b) {{
          return Number(b.spec.legend_id === 'combined_establishment')
            - Number(a.spec.legend_id === 'combined_establishment');
        }}).forEach(function(record) {{
          if (!byResolution.has(record.hexArea.resolution)) byResolution.set(record.hexArea.resolution, record.hexArea);
        }});
      if (!byResolution.size) return '';
      let html = '<div class="map-legend-section">' + hexSizeLabels.title + '</div>';
      [...byResolution.values()].sort(function(a, b) {{ return b.resolution - a.resolution; }}).forEach(function(meta) {{
        html += hexAreaRow(hexSizeLabels.cell.replace('{{resolution}}', meta.resolution),
          meta.area_km2, 1, 'h3', meta.resolution);
      }});
      return html + '<div class="map-legend-note">' + hexSizeLabels.reference + '</div>';
    }}

    if (legendSourceRecords.length > 0) {{
      const legend = L.control({{ position: 'bottomright' }});
      legend.onAdd = function() {{
        const div = L.DomUtil.create('div', 'map-legend');
        legendDiv = div;
        L.DomEvent.disableClickPropagation(div);
        L.DomEvent.disableScrollPropagation(div);
        updateLegendContent();
        return div;
      }};
      legend.addTo(map);
      updateLegendContent();
    }}

    function updateLegendContent() {{
      if (!legendDiv) {{
        return;
      }}
      const activeLegendById = {{}};
      const activeRecords = legendSourceRecords.filter(legendRecordVisible);
      activeRecords.forEach(function(record) {{
        const spec = record.spec || {{}};
        const presentation = record.presentation || {{}};
        if (!(spec.legend_items && spec.legend_items.length > 0)) {{
          return;
        }}
        const legendId = spec.legend_id || spec.control_name || spec.name;
        if (!activeLegendById[legendId]) {{
          activeLegendById[legendId] = {{
            title: presentation.legend_title,
            items: presentation.legend_items,
            note: presentation.legend_note,
            hexArea: record.hexArea
          }};
        }}
      }});
      const activeLegendSections = Object.values(activeLegendById);
      if (activeLegendSections.length === 0) {{
        legendDiv.style.display = 'none';
        legendDiv.innerHTML = '';
        return;
      }}
      legendDiv.style.display = '';
      let html = '<div class="map-legend-title">' + legendTitle + '</div>'
        + hexAreaLegendContent(activeRecords);
      activeLegendSections.forEach(function(section) {{
        html += '<div class="map-legend-section">' + section.title + '</div>';
        html += section.items.map(function(item) {{
          return '<div class="map-legend-row">' + legendSwatchHtml(item) + '<span>' + item.label + '</span></div>';
        }}).join('');
        if (section.hexArea?.kind === 'schematic') {{
          html += '<div class="map-legend-section">' + hexSizeLabels.schematic_sizes + '</div>';
          section.hexArea.sizes.forEach(function(size) {{
            html += hexAreaRow('', size.area_km2, size.count, 'schematic', null);
          }});
        }}
        if (section.note) {{
          html += '<div class="map-legend-note">' + section.note + '</div>';
        }}
      }});
      legendDiv.innerHTML = html;
    }}

    function fitInitialBounds() {{
      map.invalidateSize();
      if (savedView) {{
        storeMapView();
        return;
      }}
      // A schematic comparison carries the tight region + area bounds. Saved
      // views still take precedence on scenario/panel reruns.
      const comparisonBounds = L.latLngBounds([]);
      layerSpecs.forEach(function(spec) {{
        if (spec.initial_bounds && spec.default_visible !== false) {{
          comparisonBounds.extend(spec.initial_bounds);
        }}
      }});
      if (comparisonBounds.isValid()) {{
        map.fitBounds(comparisonBounds, {{ padding: [28, 28] }});
        storeMapView();
        return;
      }}
      // With no outside demand, frame the actual potential domain. Regional
      // overview bounds can include much wider offshore source coverage.
      const potentialLayers = layerSpecs.map(function(spec, index) {{
        return {{ spec, layer: renderedLayers[index] }};
      }}).filter(function(record) {{
        return record.spec.legend_id === 'combined_establishment'
          && record.spec.default_visible !== false;
      }}).sort(function(a, b) {{
        return Number(b.spec.auto_resolution || 0) - Number(a.spec.auto_resolution || 0);
      }});
      if (potentialLayers.length) {{
        const potentialBounds = layerDataBounds(potentialLayers[0].spec);
        if (potentialBounds.isValid()) {{
          map.fitBounds(potentialBounds, {{ padding: [28, 28] }});
          storeMapView();
          return;
        }}
      }}
      if (defaultBounds && defaultBounds.length === 2) {{
        map.fitBounds(defaultBounds, {{ padding: [18, 18] }});
        storeMapView();
        return;
      }}
      const dataBounds = L.latLngBounds([]);
      layerSpecs.forEach(function(spec) {{ dataBounds.extend(layerDataBounds(spec)); }});
      if (dataBounds && dataBounds.isValid()) {{
        map.fitBounds(dataBounds.pad(0.04));
      }}
      storeMapView();
    }}
    setTimeout(function() {{
      fitInitialBounds();
      refreshZoomScaledLayerStyles();
      refreshScalablePointMarkers();
      map.whenReady(function() {{
        requestAnimationFrame(function() {{
          requestAnimationFrame(function() {{
            if (!window.__potentialMapBootstrapError) window.__potentialMapReady = true;
          }});
        }});
      }});
    }}, 80);
  </script>
</body>
</html>
"""


    return _compress_layered_map_html(html)


def build_potential_map_html(
    feature_collection: dict[str, Any],
    center: list[float],
    zoom: int,
    title: str,
    bounds: list[list[float]] | None = None,
    fill_opacity: float = 0.78,
    legend_items: list[dict[str, str]] | None = None,
) -> str:
    payload = json.dumps(feature_collection, ensure_ascii=False)
    center_payload = json.dumps(center)
    bounds_payload = json.dumps(bounds)
    title_payload = json.dumps(title, ensure_ascii=False)
    opacity_payload = json.dumps(max(0.0, min(1.0, float(fill_opacity))))
    legend_payload = json.dumps(legend_items or [], ensure_ascii=False)
    return f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <style>
    html, body, #map {{ height: 100%; margin: 0; }}
    #map {{ min-height: 800px; border-radius: 4px; overflow: hidden; }}
    .leaflet-control-layers, .map-note, .map-legend {{ font-family: sans-serif; font-size: 12px; }}
    .map-note {{ background: rgba(255,255,255,0.94); padding: 8px 10px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.2); max-width: 260px; }}
    .map-legend {{ background: rgba(255,255,255,0.94); padding: 9px 10px; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.2); line-height: 1.25; max-width: 260px; }}
    .map-legend-title {{ font-weight: 700; margin-bottom: 6px; }}
    .map-legend-row {{ display: flex; align-items: center; gap: 6px; margin: 4px 0; }}
    .map-legend-swatch {{ width: 14px; height: 14px; border: 1px solid rgba(0,0,0,0.22); flex: 0 0 auto; }}
    .map-legend-swatch.circle {{ width: 10px; height: 10px; border-radius: 999px; margin: 2px; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const data = {payload};
    const defaultCenter = {center_payload};
    const defaultBounds = {bounds_payload};
    const mapTitle = {title_payload};
    const hexFillOpacity = {opacity_payload};
    const legendItems = {legend_payload};
    const map = L.map('map', {{ preferCanvas: true }}).setView(defaultCenter, {int(zoom)});

    const osm = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 20,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      maxZoom: 20,
      attribution: 'Tiles &copy; Esri'
    }});

    function styleFeature(feature) {{
      const props = feature.properties || {{}};
      return {{
        color: '#555555',
        weight: 0.25,
        opacity: Math.min(0.85, hexFillOpacity + 0.1),
        fillColor: props.fill || '#999999',
        fillOpacity: hexFillOpacity
      }};
    }}

    const potential = L.geoJSON(data, {{
      style: styleFeature,
      onEachFeature: function(feature, layer) {{
        const props = feature.properties || {{}};
        layer.bindPopup(props.popup || props.hex_id || mapTitle);
      }}
    }}).addTo(map);

    const overlays = {{}};
    overlays[mapTitle] = potential;
    L.control.layers({{ 'OSM': osm, 'Satellite': satellite }}, overlays, {{ collapsed: true }}).addTo(map);
    L.control.scale({{ metric: true, imperial: false, maxWidth: 160 }}).addTo(map);

    const note = L.control({{ position: 'topright' }});
    note.onAdd = function() {{
      const div = L.DomUtil.create('div', 'map-note');
      div.innerHTML = '<strong>' + mapTitle + '</strong><br>Manifestdriven H3-kapacitetsmodell. Detaljerade vektorer kopplas in senare.';
      L.DomEvent.disableClickPropagation(div);
      return div;
    }};
    note.addTo(map);

    if (legendItems.length > 0) {{
      const legend = L.control({{ position: 'bottomright' }});
      legend.onAdd = function() {{
        const div = L.DomUtil.create('div', 'map-legend');
        div.innerHTML = '<div class="map-legend-title">' + mapTitle + '</div>' +
          legendItems.map(function(item) {{
            const shapeClass = item.shape === 'circle' ? ' circle' : '';
            return '<div class="map-legend-row"><span class="map-legend-swatch' + shapeClass + '" style="background:' + item.color + '"></span><span>' + item.label + '</span></div>';
          }}).join('');
        L.DomEvent.disableClickPropagation(div);
        return div;
      }};
      legend.addTo(map);
    }}

    function fitInitialBounds() {{
      map.invalidateSize();
      if (defaultBounds && defaultBounds.length === 2) {{
        map.fitBounds(defaultBounds, {{ padding: [18, 18] }});
        return;
      }}
      const dataBounds = potential.getBounds();
      if (dataBounds && dataBounds.isValid()) {{
        map.fitBounds(dataBounds.pad(0.04));
      }}
    }}
    setTimeout(fitInitialBounds, 80);
  </script>
</body>
</html>
"""
