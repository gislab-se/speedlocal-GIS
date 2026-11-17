from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, replace
import hashlib
import html
import json
import math
from operator import itemgetter
import re
import sys
from threading import RLock
from typing import Any, Mapping

from .workspace_presentation import (
    WorkspaceAnalysisPresentation,
    WorkspacePresentationDomain,
    WorkspacePresentationField,
    WorkspacePresentationLayerSpec,
    WorkspacePresentationResult,
    validate_workspace_analysis_presentation,
)


WORKSPACE_APP_ADAPTER_SCHEMA_VERSION = "1.0"
WORKSPACE_SOURCE_BUFFER_APP_ADAPTER_SCHEMA_VERSION = "1.1"
WORKSPACE_APP_MAP_LAYER_PROFILES = frozenset({"full", "source_buffer"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ROLES = {"source", "buffer", "primary", "result"}
_RENDERABLE_GEOMETRY_MODES = {"embedded", "referenced"}
_DOMAIN_ROLES = {"standard_analysis", "eligible_support"}
_VALUE_TYPES = {"string", "number", "boolean"}
_ROLE_LEGEND_LABELS = {
    "source": "Datakälla",
    "buffer": "Buffertområde",
    "primary": "Område",
    "result": "Resultat",
}
_RESULT_STATUS_LABELS = {
    "coverage_missing": "Saknad täckning",
    "blocked": "Utesluten",
    "accepted": "Kvar efter filter",
    "zero": "Ingen etableringsyta",
    "low": "Låg etableringsyta",
    "medium": "Medelhög etableringsyta",
    "high": "Hög etableringsyta",
    "full": "Full etableringsyta",
    "result": "Resultat",
}
_RESULT_SEMANTICS_NOTES = {
    "blocked_means_excluded": "Blockerade celler utesluts.",
    "blocked_means_outside_required_proximity": (
        "Blockerade celler ligger utanför krävt närhetsavstånd."
    ),
    "remaining_over_eligible_surface": (
        "Återstående andel av den lämpliga stödytan."
    ),
}
_RENDERER_LAYER_KEYS = {
    "name",
    "feature_collection",
    "fill_property",
    "stroke_property",
    "legend_items",
    "legend_id",
    "legend_title",
    "legend_note",
    "default_visible",
    "stroke",
    "weight",
    "fill_opacity",
    "stroke_opacity",
    "fill_color",
    "stroke_color",
    "point_radius",
    "use_global_opacity",
    "interaction_role",
    "layer_kind",
    "z_index",
    "opacity_family",
    "source_layer_id",
    "buffer_layer_id",
    "workspace_layer_id",
    "workspace_source_layer_id",
    "workspace_role",
    "workspace_domain_key",
    "workspace_result_id",
    "workspace_geometry_mode",
    "workspace_geometry_reference_layer_id",
    "workspace_preview_result_signature_sha256",
    "workspace_presentation_signature_sha256",
}


JsonScalar = str | float | int | bool | None


def _analysis_display_label(analysis_id: str) -> str:
    return analysis_id.replace("_", " ").capitalize()


def _result_status_label(status: str) -> str:
    try:
        return _RESULT_STATUS_LABELS[status]
    except KeyError as exc:
        raise ValueError("Workspace result status has no display label") from exc


def _result_semantics_note(result_semantics: str | None) -> str:
    if result_semantics is None:
        return ""
    try:
        return _RESULT_SEMANTICS_NOTES[result_semantics]
    except KeyError as exc:
        raise ValueError(
            "Workspace result semantics has no display note"
        ) from exc


@dataclass(frozen=True)
class WorkspaceAppPresentationBinding:
    analysis_id: str
    presentation_signature_sha256: str

    def as_dict(self) -> dict[str, str]:
        return {
            "analysis_id": self.analysis_id,
            "presentation_signature_sha256": (
                self.presentation_signature_sha256
            ),
        }


@dataclass(frozen=True)
class WorkspaceAppDomainBinding:
    domain_key: str
    role: str
    resolution: int
    source_sha256: str
    cell_ids_sha256: str
    cell_count: int
    total_area_km2: float
    id_field: str
    area_field: str
    area_unit: str
    primary_map_layer_id: str
    presentation_domain_refs: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "domain_key": self.domain_key,
            "role": self.role,
            "resolution": self.resolution,
            "source_sha256": self.source_sha256,
            "cell_ids_sha256": self.cell_ids_sha256,
            "cell_count": self.cell_count,
            "total_area_km2": self.total_area_km2,
            "id_field": self.id_field,
            "area_field": self.area_field,
            "area_unit": self.area_unit,
            "primary_map_layer_id": self.primary_map_layer_id,
            "presentation_domain_refs": list(
                self.presentation_domain_refs
            ),
        }


@dataclass(frozen=True)
class WorkspaceAppMapLayer:
    layer_id: str
    analysis_id: str
    source_layer_id: str
    role: str
    geometry_mode: str
    domain_key: str | None
    geometry_reference_layer_id: str | None
    source_layer_ids: tuple[str, ...]
    result_id: str | None
    operation: str | None
    result_semantics: str | None
    preview_result_signature_sha256: str | None
    presentation_signature_sha256: str
    geometry_source_sha256: str
    feature_count: int
    feature_collection_sha256: str
    renderer_payload_json: str
    renderer_payload_sha256: str
    layer_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "analysis_id": self.analysis_id,
            "source_layer_id": self.source_layer_id,
            "role": self.role,
            "geometry_mode": self.geometry_mode,
            "domain_key": self.domain_key,
            "geometry_reference_layer_id": (
                self.geometry_reference_layer_id
            ),
            "source_layer_ids": list(self.source_layer_ids),
            "result_id": self.result_id,
            "operation": self.operation,
            "result_semantics": self.result_semantics,
            "preview_result_signature_sha256": (
                self.preview_result_signature_sha256
            ),
            "presentation_signature_sha256": (
                self.presentation_signature_sha256
            ),
            "geometry_source_sha256": self.geometry_source_sha256,
            "feature_count": self.feature_count,
            "feature_collection_sha256": self.feature_collection_sha256,
            "renderer_payload_json": self.renderer_payload_json,
            "renderer_payload_sha256": self.renderer_payload_sha256,
            "layer_signature_sha256": self.layer_signature_sha256,
        }

    def renderer_dict(self) -> dict[str, Any]:
        value = json.loads(self.renderer_payload_json)
        if not isinstance(value, dict):
            raise ValueError("Workspace renderer layer payload is not an object")
        return value


@dataclass(frozen=True)
class WorkspaceAppTableColumn:
    field_id: str
    value_type: str
    unit: str | None
    nullable: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "value_type": self.value_type,
            "unit": self.unit,
            "nullable": self.nullable,
        }


@dataclass(frozen=True)
class WorkspaceAppResultTable:
    table_id: str
    analysis_id: str
    source_result_id: str
    domain_key: str
    presentation_signature_sha256: str
    columns: tuple[WorkspaceAppTableColumn, ...]
    rows: tuple[tuple[JsonScalar, ...], ...]
    row_count: int
    table_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "table_id": self.table_id,
            "analysis_id": self.analysis_id,
            "source_result_id": self.source_result_id,
            "domain_key": self.domain_key,
            "presentation_signature_sha256": (
                self.presentation_signature_sha256
            ),
            "columns": [column.as_dict() for column in self.columns],
            "rows": [list(row) for row in self.rows],
            "row_count": self.row_count,
            "table_signature_sha256": self.table_signature_sha256,
        }

    def renderer_dict(self) -> dict[str, Any]:
        field_ids = tuple(column.field_id for column in self.columns)
        return {
            "table_id": self.table_id,
            "result_id": self.source_result_id,
            "domain_key": self.domain_key,
            "columns": [column.as_dict() for column in self.columns],
            "rows": [
                dict(zip(field_ids, row, strict=True)) for row in self.rows
            ],
        }


@dataclass(frozen=True)
class WorkspaceAppMetric:
    metric_id: str
    table_id: str
    source_metric_id: str
    value: float
    unit: str
    presentation_signature_sha256: str
    metric_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "table_id": self.table_id,
            "source_metric_id": self.source_metric_id,
            "value": self.value,
            "unit": self.unit,
            "presentation_signature_sha256": (
                self.presentation_signature_sha256
            ),
            "metric_signature_sha256": self.metric_signature_sha256,
        }

    def renderer_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "table_id": self.table_id,
            "label": self.source_metric_id,
            "value": self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class WorkspaceAppAdapter:
    schema_version: str
    access_scope: str
    region_id: str
    target_resolution: int
    presentations: tuple[WorkspaceAppPresentationBinding, ...]
    domains: tuple[WorkspaceAppDomainBinding, ...]
    map_layers: tuple[WorkspaceAppMapLayer, ...]
    result_tables: tuple[WorkspaceAppResultTable, ...]
    metrics: tuple[WorkspaceAppMetric, ...]
    adapter_signature_sha256: str
    map_layer_profile: str = "full"
    # The compact profile retains authenticated original domain geometry,
    # rather than producing unused primary/result renderer copies of it.
    domain_geometry: tuple[tuple[str, str], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        value = {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "region_id": self.region_id,
            "target_resolution": self.target_resolution,
            "presentations": [value.as_dict() for value in self.presentations],
            "domains": [value.as_dict() for value in self.domains],
            "map_layers": [value.as_dict() for value in self.map_layers],
            "result_tables": [value.as_dict() for value in self.result_tables],
            "metrics": [value.as_dict() for value in self.metrics],
            "adapter_signature_sha256": self.adapter_signature_sha256,
        }
        if self.map_layer_profile != "full":
            value["map_layer_profile"] = self.map_layer_profile
            value["domain_geometry"] = [list(pair) for pair in self.domain_geometry]
        return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _serialized_renderer_geometry(
    payload: dict[str, Any],
    feature_collection: dict[str, Any],
    *,
    plain_metadata: bool,
) -> tuple[str, str]:
    """Serialize normalized geometry once without changing canonical JSON.

    The builder has freshly decoded the geometry and checked its externally
    inserted metadata. Split only the top-level string keys, keeping the same
    recursive JSON encoder for both geometry and metadata. Non-plain input
    retains the original two-serialization path and its validation behavior.
    """
    if (not plain_metadata or type(payload) is not dict
            or payload.get("feature_collection") is not feature_collection
            or any(type(key) is not str for key in payload)):
        return _canonical_json(payload), _canonical_sha256(feature_collection)
    geometry_json = _canonical_json(feature_collection)
    geometry_digest = hashlib.sha256(geometry_json.encode("utf-8")).hexdigest()
    before = _canonical_json({key: value for key, value in payload.items()
                              if key < "feature_collection"})[1:-1]
    after = _canonical_json({key: value for key, value in payload.items()
                             if key > "feature_collection"})[1:-1]
    parts = ["{"]
    if before:
        parts.extend((before, ","))
    parts.extend(('"feature_collection":', geometry_json))
    if after:
        parts.extend((",", after))
    parts.append("}")
    return "".join(parts), geometry_digest


@dataclass(frozen=True, slots=True)
class _RendererIntegrityEvidence:
    payload_sha256: str
    feature_collection_sha256: str | None
    feature_count: int | None


_RENDERER_INTEGRITY_MAX_ENTRIES = 64
_RENDERER_INTEGRITY_MAX_BYTES = 64 * 1024 * 1024
_renderer_integrity_cache: OrderedDict = OrderedDict()
_renderer_integrity_bytes = 0
_renderer_integrity_generation = 0
_renderer_integrity_lock = RLock()


def clear_workspace_renderer_integrity_cache() -> None:
    """Release bounded content-only evidence; no live readiness is cached."""
    global _renderer_integrity_bytes, _renderer_integrity_generation
    with _renderer_integrity_lock:
        _renderer_integrity_cache.clear()
        _renderer_integrity_bytes = 0
        _renderer_integrity_generation += 1


def _decode_renderer_payload_json(text: str) -> tuple[Any, _RendererIntegrityEvidence | None]:
    """Decode freshly while reusing only canonical/digest proof of exact text.

    Evidence is not adapter/layer validation: each caller still checks its
    claimed digests, types, metadata and current cross-layer relationships.
    No mutable renderer dictionary is retained or returned from a cache.
    """
    global _renderer_integrity_bytes
    payload = json.loads(text)
    if not isinstance(payload, dict):
        return payload, None  # Callers retain their existing type rejection.
    with _renderer_integrity_lock:
        entry = _renderer_integrity_cache.get(text) if type(text) is str else None
        if entry is not None:
            _renderer_integrity_cache.move_to_end(text)
            return payload, entry[0]
        generation = _renderer_integrity_generation
    if _canonical_json(payload) != text:
        raise ValueError("Workspace renderer payload is not canonical")
    collection = payload.get("feature_collection")
    valid_collection = (isinstance(collection, dict)
                        and collection.get("type") == "FeatureCollection"
                        and isinstance(collection.get("features"), list))
    evidence = _RendererIntegrityEvidence(
        hashlib.sha256(text.encode("utf-8")).hexdigest(),
        _canonical_sha256(collection) if valid_collection else None,
        len(collection["features"]) if valid_collection else None,
    )
    # Count the retained string, slots record, scalar referents, entry tuple
    # and charge integer. Shared values are deliberately charged per entry.
    charge = (sys.getsizeof(text) + sys.getsizeof(evidence)
              + sum(sys.getsizeof(value) for value in (
                  evidence.payload_sha256, evidence.feature_collection_sha256,
                  evidence.feature_count))
              + sys.getsizeof((evidence, 0)) + sys.getsizeof(0))
    with _renderer_integrity_lock:
        if (type(text) is not str or generation != _renderer_integrity_generation
                or charge + sys.getsizeof(OrderedDict()) > _RENDERER_INTEGRITY_MAX_BYTES):
            return payload, evidence
        previous = _renderer_integrity_cache.pop(text, None)
        if previous is not None:
            _renderer_integrity_bytes -= previous[1]
        _renderer_integrity_cache[text] = (evidence, charge)
        _renderer_integrity_bytes += charge
        while (_renderer_integrity_cache and
               (len(_renderer_integrity_cache) > _RENDERER_INTEGRITY_MAX_ENTRIES
                or _renderer_integrity_bytes + sys.getsizeof(_renderer_integrity_cache)
                > _RENDERER_INTEGRITY_MAX_BYTES)):
            _, removed = _renderer_integrity_cache.popitem(last=False)
            _renderer_integrity_bytes -= removed[1]
        if not _renderer_integrity_cache:
            _renderer_integrity_cache.clear()
    return payload, evidence


@dataclass(frozen=True, slots=True)
class _ConstructedRendererIntegrity:
    # The strong reference prevents id reuse; only this exact immutable text
    # may consume the proof. No decoded geometry or layer claims are retained.
    text: str
    evidence: _RendererIntegrityEvidence


_CONSTRUCTED_RENDERER_MAX_ENTRIES = 256


def _plain_json_value(value: Any) -> bool:
    if type(value) in (str, int, float, bool, type(None)):
        return True
    if type(value) is list:
        return all(_plain_json_value(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _plain_json_value(item)
                   for key, item in value.items())
    return False


def _constructed_renderer_values_are_plain(
    payload: dict[str, Any], result: WorkspacePresentationResult | None,
) -> bool:
    # Geometry and existing properties are freshly decoded by
    # _feature_collection. Primary/result constructors add only literal or
    # f-string keys. Check every externally supplied insertion point without
    # traversing those already normalized coordinate trees a second time.
    try:
        if type(payload) is not dict or not all(
            type(key) is str and (key == "feature_collection" or _plain_json_value(value))
            for key, value in payload.items()
        ):
            return False
        if result is not None and (
            type(result.rows) is not tuple or not all(
                type(row) is tuple and all(type(value) in (str, int, float, bool, type(None))
                                          for value in row)
                for row in result.rows
            )
        ):
            return False
        return True
    except RecursionError:
        return False


def _decode_constructed_renderer_payload(
    text: str,
    proofs: dict[int, _ConstructedRendererIntegrity] | None,
) -> tuple[Any, _RendererIntegrityEvidence | None]:
    proof = proofs.get(id(text)) if proofs is not None and type(text) is str else None
    if proof is not None and proof.text is text:
        # No shared-cache insertion/lookup or mutable payload reuse. Current
        # claimed hashes, metadata, domains, tables and signatures are checked
        # by the same validator body after this fresh decode.
        return json.loads(text), proof.evidence
    return _decode_renderer_payload_json(text)


def _exact_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or value != value.strip() or not value:
        raise ValueError(f"{label} must be a non-empty exact string")
    return value


def _optional_text(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _exact_text(value, label)


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _optional_digest(value: Any, label: str) -> str | None:
    if value is None:
        return None
    return _digest(value, label)


def _integer(value: Any, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if positive and value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    if positive and number <= 0.0:
        raise ValueError(f"{label} must be positive")
    return number


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise ValueError(
            f"{label} fields drifted; missing={missing}, extra={extra}"
        )


def _namespace(analysis_id: str, local_id: str) -> str:
    return f"{analysis_id}::{local_id}"


def _domain_identity_payload(domain: WorkspacePresentationDomain) -> dict[str, Any]:
    return {
        "role": domain.role,
        "resolution": domain.resolution,
        "source_sha256": domain.source_sha256,
        "cell_ids_sha256": domain.cell_ids_sha256,
        "cell_count": domain.cell_count,
        "total_area_km2": domain.total_area_km2,
        "id_field": domain.id_field,
        "area_field": domain.area_field,
        "area_unit": domain.area_unit,
    }


def _domain_key(domain: WorkspacePresentationDomain) -> str:
    return _canonical_sha256(_domain_identity_payload(domain))


def _feature_collection(value: str, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(value)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON") from exc
    features = payload.get("features") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("type") != "FeatureCollection"
        or not isinstance(features, list)
    ):
        raise ValueError(f"{label} is not a GeoJSON FeatureCollection")
    for index, feature in enumerate(features):
        if (
            not isinstance(feature, dict)
            or feature.get("type") != "Feature"
            or not isinstance(feature.get("properties"), dict)
            or not isinstance(feature.get("geometry"), dict)
        ):
            raise ValueError(f"{label} feature {index} is invalid")
    return payload


def _primary_feature_collection(
    payload: Mapping[str, Any],
    domain: WorkspacePresentationDomain,
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    for raw in payload["features"]:
        properties = dict(raw["properties"])
        cell_id = _exact_text(
            str(properties.get(domain.id_field) or ""),
            "primary domain cell id",
        )
        properties.update(
            {
                "hex_id": cell_id,
                "fill": "#dbeafe",
                "stroke": "#64748b",
                "tooltip_title": f"{domain.role} · R{domain.resolution}",
                "tooltip_body": cell_id,
                "popup": (
                    f"<strong>{html.escape(domain.role)}</strong><br>"
                    f"{html.escape(cell_id)}"
                ),
            }
        )
        feature = dict(raw)
        feature["properties"] = properties
        features.append(feature)
    return {"type": "FeatureCollection", "features": features}


def _result_colors(row: Mapping[str, JsonScalar]) -> tuple[str, str, str]:
    if row.get("coverage_missing") is True:
        return "#9ca3af", "#4b5563", "coverage_missing"
    blocked = row.get("blocked")
    if isinstance(blocked, bool):
        return (
            ("#b91c1c", "#7f1d1d", "blocked")
            if blocked
            else ("#2f855a", "#166534", "accepted")
        )
    potential = row.get("potential_pct")
    if isinstance(potential, (int, float)) and not isinstance(potential, bool):
        value = float(potential)
        if value <= 0.0:
            return "#b91c1c", "#7f1d1d", "zero"
        if value < 33.3333333333:
            return "#f59e0b", "#b45309", "low"
        if value < 66.6666666667:
            return "#eab308", "#a16207", "medium"
        if value < 100.0:
            return "#65a30d", "#3f6212", "high"
        return "#166534", "#14532d", "full"
    return "#2563eb", "#1e3a8a", "result"


def _result_feature_collection(
    payload: Mapping[str, Any],
    domain: WorkspacePresentationDomain,
    result: WorkspacePresentationResult,
) -> dict[str, Any]:
    field_ids = tuple(field.field_id for field in result.fields)
    if field_ids.count("cell_id") != 1:
        raise ValueError("Workspace result table has no unique cell identity")
    cell_index = field_ids.index("cell_id")
    rows: dict[str, dict[str, JsonScalar]] = {}
    for raw_row in result.rows:
        row = dict(zip(field_ids, raw_row, strict=True))
        cell_id = _exact_text(str(raw_row[cell_index]), "result cell id")
        if cell_id in rows:
            raise ValueError("Workspace result table contains duplicate cells")
        rows[cell_id] = row
    field_formats = None
    popup_heading = None
    if (
        type(result) is WorkspacePresentationResult
        and type(result.result_id) is str
        and type(result.fields) is tuple
        and all(
            type(field) is WorkspacePresentationField
            and type(field.field_id) is str
            and (field.unit is None or type(field.unit) is str)
            for field in result.fields
        )
        and _constructed_renderer_values_are_plain({}, result)
    ):
        # Only immutable builtin metadata is prepared once. Values are still
        # converted and escaped per cell; unusual types keep the precise path.
        field_formats = tuple(
            (
                f"result_{field.field_id}",
                f"{html.escape(field.field_id)}: ",
                html.escape(f" {field.unit}" if field.unit else ""),
            )
            for field in result.fields
        )
        popup_heading = f"<strong>{html.escape(result.result_id)}</strong><br>"
    features: list[dict[str, Any]] = []
    observed_ids: set[str] = set()
    for raw in payload["features"]:
        properties = dict(raw["properties"])
        cell_id = _exact_text(
            str(properties.get(domain.id_field) or ""),
            "referenced result cell id",
        )
        row = rows.get(cell_id)
        if row is None or cell_id in observed_ids:
            raise ValueError("Referenced result geometry does not match its table")
        observed_ids.add(cell_id)
        fill, stroke, status = _result_colors(row)
        values = []
        for index, field in enumerate(result.fields):
            value = row[field.field_id]
            if field_formats is None:
                properties[f"result_{field.field_id}"] = value
                if field.field_id != "cell_id":
                    suffix = f" {field.unit}" if field.unit else ""
                    values.append(
                        f"{html.escape(field.field_id)}: "
                        f"{html.escape(str(value))}{html.escape(suffix)}"
                    )
            else:
                property_key, prefix, suffix = field_formats[index]
                properties[property_key] = value
                if field.field_id != "cell_id":
                    values.append(f"{prefix}{html.escape(str(value))}{suffix}")
        properties.update(
            {
                "hex_id": cell_id,
                "fill": fill,
                "stroke": stroke,
                "tooltip_title": (
                    f"{result.result_id} · {_result_status_label(status)}"
                ),
                "tooltip_body": " · ".join(values),
                "popup": (
                    (popup_heading if popup_heading is not None else
                     f"<strong>{html.escape(result.result_id)}</strong><br>")
                    + f"{html.escape(cell_id)}<br>" + "<br>".join(values)
                ),
            }
        )
        feature = dict(raw)
        feature["properties"] = properties
        features.append(feature)
    if observed_ids != set(rows):
        raise ValueError("Referenced result table escaped its exact domain")
    return {"type": "FeatureCollection", "features": features}


def _role_color(role: str, layer: WorkspacePresentationLayerSpec) -> str:
    if layer.color:
        return layer.color
    return {
        "source": "#2563eb",
        "buffer": "#f59e0b",
        "primary": "#dbeafe",
        "result": "#2f855a",
    }[role]


def _legend_items(
    role: str,
    result: WorkspacePresentationResult | None,
    color: str,
) -> list[dict[str, str]]:
    if role != "result" or result is None:
        return [{"label": _ROLE_LEGEND_LABELS[role], "color": color}]
    fields = {field.field_id for field in result.fields}
    if "blocked" in fields:
        return [
            {"label": "Utesluten", "color": "#b91c1c"},
            {"label": "Kvar efter filter", "color": "#2f855a"},
            {"label": "Saknad täckning", "color": "#9ca3af"},
        ]
    if "potential_pct" in fields:
        return [
            {"label": "Ingen (0 %)", "color": "#b91c1c"},
            {"label": "Låg (>0–<33,3 %)", "color": "#f59e0b"},
            {"label": "Medel (33,3–<66,7 %)", "color": "#eab308"},
            {"label": "Hög (66,7–<100 %)", "color": "#65a30d"},
            {"label": "Full (100 %)", "color": "#166534"},
        ]
    return [{"label": _ROLE_LEGEND_LABELS["result"], "color": color}]


def _renderer_layer_payload(
    *,
    output_layer_id: str,
    analysis_id: str,
    layer: WorkspacePresentationLayerSpec,
    domain_key: str | None,
    output_reference_id: str | None,
    output_result_id: str | None,
    presentation_signature: str,
    feature_collection: dict[str, Any],
    result: WorkspacePresentationResult | None,
    result_count_for_domain: int,
    area_result_id: str | None,
    order: int,
) -> dict[str, Any]:
    color = _role_color(layer.role, layer)
    role_index = {"primary": 0, "source": 1, "buffer": 2, "result": 3}[
        layer.role
    ]
    default_visible = (
        True
        if layer.role in {"primary", "source"}
        else layer.role == "result"
        and (
            layer.result_id == area_result_id
            if area_result_id is not None
            else result_count_for_domain == 1
        )
    )
    layer_kind = "hex" if layer.role in {"primary", "result"} else "vector"
    if layer.label:
        label = layer.label
    elif layer.role == "primary":
        label = "Analysdomän" if layer.domain_id and layer.domain_id.startswith(
            "standard:"
        ) else "Teknisk stödyta"
    elif layer.role == "buffer":
        label = "Buffertgeometri"
    elif layer.role == "result":
        label = (
            "Etableringsyta"
            if layer.result_id and layer.result_id.endswith(".area")
            else "Tekniskt filterresultat"
        )
    else:
        label = layer.layer_id.removeprefix("source:")
    return {
        "name": f"{_analysis_display_label(analysis_id)} · {label}",
        "feature_collection": feature_collection,
        "fill_property": "fill",
        "stroke_property": "stroke",
        "legend_items": _legend_items(layer.role, result, color),
        "legend_id": f"workspace::{output_layer_id}",
        "legend_title": label,
        "legend_note": (
            "Teknisk cellklassning. Återstående area visas i Etableringsyta."
            if layer.role == "result"
            and area_result_id is not None
            and layer.result_id != area_result_id
            else _result_semantics_note(layer.result_semantics)
        ),
        "default_visible": default_visible,
        "stroke": True,
        "weight": 0.45 if layer_kind == "hex" else 2.0,
        "fill_opacity": 0.76 if layer.role == "result" else 0.32,
        "stroke_opacity": 0.88,
        "fill_color": color,
        "stroke_color": color,
        "point_radius": layer.point_radius or 5,
        "use_global_opacity": layer_kind == "vector",
        "interaction_role": (
            "primary_result"
            if layer.role in {"primary", "result"}
            else None
        ),
        "layer_kind": layer_kind,
        "z_index": 400 + role_index * 100 + order,
        "opacity_family": output_layer_id,
        "source_layer_id": output_layer_id if layer.role == "source" else None,
        "buffer_layer_id": output_layer_id if layer.role == "buffer" else None,
        "workspace_layer_id": output_layer_id,
        "workspace_source_layer_id": layer.layer_id,
        "workspace_role": layer.role,
        "workspace_domain_key": domain_key,
        "workspace_result_id": output_result_id,
        "workspace_geometry_mode": layer.geometry_mode,
        "workspace_geometry_reference_layer_id": output_reference_id,
        "workspace_preview_result_signature_sha256": (
            layer.preview_result_signature_sha256
        ),
        "workspace_presentation_signature_sha256": presentation_signature,
    }


def _layer_signature_payload(layer: WorkspaceAppMapLayer) -> dict[str, Any]:
    value = layer.as_dict()
    value.pop("layer_signature_sha256")
    value.pop("renderer_payload_json")
    return value


def _plain_source_decode_inputs(presentation: WorkspaceAnalysisPresentation) -> bool:
    """Exclude foreign callbacks before sharing an operation-owned JSON tree."""
    def plain_metadata(model: Any, expected: type) -> bool:
        return type(model) is expected and all(
            type(value) in (str, int, float, bool, type(None))
            or (type(value) is tuple and all(type(item) is str for item in value))
            for value in vars(model).values()
        )

    return (
        type(presentation) is WorkspaceAnalysisPresentation
        and all(type(value) in (str, int, float, bool, type(None)) for value in (
            presentation.analysis_id, presentation.presentation_signature_sha256,
            presentation.area_capability_id,
        ))
        and type(presentation.layers) is tuple
        and all(plain_metadata(layer, WorkspacePresentationLayerSpec)
                for layer in presentation.layers)
        and type(presentation.domains) is tuple
        and all(plain_metadata(domain, WorkspacePresentationDomain)
                for domain in presentation.domains)
        and type(presentation.results) is tuple
        and all(
            type(result) is WorkspacePresentationResult
            and type(result.result_id) is str and type(result.domain_id) is str
            and type(result.fields) is tuple
            and all(plain_metadata(field, WorkspacePresentationField) for field in result.fields)
            and _constructed_renderer_values_are_plain({}, result)
            for result in presentation.results
        )
    )


_SOURCE_DECODE_CONSTRUCTORS = (
    _feature_collection, _primary_feature_collection, _result_feature_collection,
    _renderer_layer_payload, _serialized_renderer_geometry,
    json.loads, json.dumps, html.escape,
)


@contextmanager
def _primary_source_decode_scope(presentation: WorkspaceAnalysisPresentation):
    # One primary tree only, within this presentation. Source/buffer payloads
    # never occupy the slot. No shared cache or mutable renderer output escapes.
    slot: list[Any] = []
    try:
        yield slot if _plain_source_decode_inputs(presentation) else None
    finally:
        # Release the slot's reference on errors too; tracebacks may retain
        # their own payload locals independently.
        slot.clear()


def _decode_renderer_source(
    source: WorkspacePresentationLayerSpec, label: str, slot: list[Any] | None,
) -> dict[str, Any]:
    text = source.feature_collection_json
    reusable = (
        slot is not None and source.role == "primary" and type(text) is str
        and all(current is original for current, original in zip((
            _feature_collection, _primary_feature_collection, _result_feature_collection,
            _renderer_layer_payload, _serialized_renderer_geometry,
            json.loads, json.dumps, html.escape,
        ), _SOURCE_DECODE_CONSTRUCTORS, strict=True))
    )
    if reusable and slot and slot[0] is text:
        return slot[1]
    payload = _feature_collection(text, label)
    if reusable:
        slot[:] = (text, payload)
    return payload


def _table_signature_payload(table: WorkspaceAppResultTable) -> dict[str, Any]:
    value = table.as_dict()
    value.pop("table_signature_sha256")
    return value


def _metric_signature_payload(metric: WorkspaceAppMetric) -> dict[str, Any]:
    value = metric.as_dict()
    value.pop("metric_signature_sha256")
    return value


def _adapter_signature_payload(adapter: WorkspaceAppAdapter) -> dict[str, Any]:
    value = {
        "schema_version": adapter.schema_version,
        "access_scope": adapter.access_scope,
        "region_id": adapter.region_id,
        "target_resolution": adapter.target_resolution,
        "presentations": [value.as_dict() for value in adapter.presentations],
        "domains": [value.as_dict() for value in adapter.domains],
        "map_layer_signatures": [
            value.layer_signature_sha256 for value in adapter.map_layers
        ],
        "result_table_signatures": [
            value.table_signature_sha256 for value in adapter.result_tables
        ],
        "metric_signatures": [
            value.metric_signature_sha256 for value in adapter.metrics
        ],
    }
    if adapter.map_layer_profile != "full":
        value["map_layer_profile"] = adapter.map_layer_profile
        # Each text is independently checked against the domain's source
        # digest; bind its ordered domain identity without serializing it again.
        value["domain_geometry_keys"] = [pair[0] for pair in adapter.domain_geometry]
    return value


def _table_from_result(
    presentation: WorkspaceAnalysisPresentation,
    result: WorkspacePresentationResult,
    domain_key: str,
) -> WorkspaceAppResultTable:
    table = WorkspaceAppResultTable(
        table_id=_namespace(presentation.analysis_id, result.result_id),
        analysis_id=presentation.analysis_id,
        source_result_id=result.result_id,
        domain_key=domain_key,
        presentation_signature_sha256=(
            presentation.presentation_signature_sha256
        ),
        columns=tuple(
            WorkspaceAppTableColumn(
                field.field_id,
                field.value_type,
                field.unit,
                field.nullable,
            )
            for field in result.fields
        ),
        rows=result.rows,
        row_count=len(result.rows),
        table_signature_sha256="0" * 64,
    )
    return replace(
        table,
        table_signature_sha256=_canonical_sha256(
            _table_signature_payload(table)
        ),
    )


def _metrics_from_result(
    presentation: WorkspaceAnalysisPresentation,
    result: WorkspacePresentationResult,
    table_id: str,
) -> tuple[WorkspaceAppMetric, ...]:
    values: list[WorkspaceAppMetric] = []
    for source in result.metrics:
        metric = WorkspaceAppMetric(
            metric_id=_namespace(
                presentation.analysis_id,
                f"{result.result_id}/{source.metric_id}",
            ),
            table_id=table_id,
            source_metric_id=source.metric_id,
            value=source.value,
            unit=source.unit,
            presentation_signature_sha256=(
                presentation.presentation_signature_sha256
            ),
            metric_signature_sha256="0" * 64,
        )
        values.append(
            replace(
                metric,
                metric_signature_sha256=_canonical_sha256(
                    _metric_signature_payload(metric)
                ),
            )
        )
    return tuple(values)


def build_workspace_app_adapter(
    presentations: tuple[WorkspaceAnalysisPresentation, ...],
    *,
    map_layer_profile: str = "full",
) -> WorkspaceAppAdapter:
    """Convert validated presentation models into one pure app view.

    Domain geometry is deduplicated only when its complete typed identity is
    byte-equivalent. Source, operation-preview, primary and result roles remain
    separately addressable map layers in the default full profile. The explicit
    source_buffer profile retains every authenticated typed fact and original
    domain geometry, but materializes only the source/buffer renderer layers.
    No source file, manifest or app state is read here.
    """

    if type(map_layer_profile) is not str or map_layer_profile not in WORKSPACE_APP_MAP_LAYER_PROFILES:
        raise ValueError("Unsupported workspace app map-layer profile")
    proofs: dict[int, _ConstructedRendererIntegrity] = {}
    try:
        if map_layer_profile == "full":
            return _build_workspace_app_adapter(presentations, proofs)
        return _build_workspace_app_adapter(
            presentations, proofs, map_layer_profile=map_layer_profile,
        )
    finally:
        proofs.clear()


def _build_workspace_app_adapter(
    presentations: tuple[WorkspaceAnalysisPresentation, ...],
    constructed_renderer_integrity: dict[int, _ConstructedRendererIntegrity],
    *,
    map_layer_profile: str = "full",
) -> WorkspaceAppAdapter:
    if type(map_layer_profile) is not str or map_layer_profile not in WORKSPACE_APP_MAP_LAYER_PROFILES:
        raise ValueError("Unsupported workspace app map-layer profile")
    if not isinstance(presentations, tuple):
        raise TypeError("Workspace app presentations must be an immutable tuple")
    if not presentations:
        raise ValueError("Workspace app adapter requires at least one presentation")
    for presentation in presentations:
        validate_workspace_analysis_presentation(presentation)
    first = presentations[0]
    if any(
        presentation.access_scope != first.access_scope
        or presentation.region_id != first.region_id
        or presentation.target_resolution != first.target_resolution
        for presentation in presentations
    ):
        raise ValueError("Workspace app presentations escaped one access surface")
    analysis_ids = tuple(presentation.analysis_id for presentation in presentations)
    if len(analysis_ids) != len(set(analysis_ids)):
        raise ValueError("Workspace app presentation analyses must be unique")

    bindings = tuple(
        WorkspaceAppPresentationBinding(
            presentation.analysis_id,
            presentation.presentation_signature_sha256,
        )
        for presentation in presentations
    )
    domain_by_key: dict[str, WorkspaceAppDomainBinding] = {}
    domain_geometry_by_key: dict[str, str] = {}
    domain_key_by_ref: dict[str, str] = {}
    for presentation in presentations:
        for domain in presentation.domains:
            key = _domain_key(domain)
            domain_ref = _namespace(presentation.analysis_id, domain.domain_id)
            domain_key_by_ref[domain_ref] = key
            existing = domain_by_key.get(key)
            if existing is None:
                if map_layer_profile == "source_buffer":
                    primary = next(layer for layer in presentation.layers
                                   if layer.layer_id == domain.primary_layer_id)
                    domain_geometry_by_key[key] = primary.feature_collection_json
                domain_by_key[key] = WorkspaceAppDomainBinding(
                    domain_key=key,
                    role=domain.role,
                    resolution=domain.resolution,
                    source_sha256=domain.source_sha256,
                    cell_ids_sha256=domain.cell_ids_sha256,
                    cell_count=domain.cell_count,
                    total_area_km2=domain.total_area_km2,
                    id_field=domain.id_field,
                    area_field=domain.area_field,
                    area_unit=domain.area_unit,
                    primary_map_layer_id=_namespace(
                        presentation.analysis_id,
                        domain.primary_layer_id,
                    ),
                    presentation_domain_refs=(domain_ref,),
                )
            else:
                domain_by_key[key] = replace(
                    existing,
                    presentation_domain_refs=(
                        *existing.presentation_domain_refs,
                        domain_ref,
                    ),
                )

    layer_id_maps: dict[str, dict[str, str]] = {}
    result_id_maps: dict[str, dict[str, str]] = {}
    for presentation in presentations:
        domains = {domain.domain_id: domain for domain in presentation.domains}
        output_ids: dict[str, str] = {}
        for layer in presentation.layers:
            if layer.role == "primary":
                if layer.domain_id is None:
                    raise ValueError("Primary presentation layer has no domain")
                key = domain_key_by_ref[
                    _namespace(presentation.analysis_id, layer.domain_id)
                ]
                output_ids[layer.layer_id] = domain_by_key[
                    key
                ].primary_map_layer_id
            else:
                output_ids[layer.layer_id] = _namespace(
                    presentation.analysis_id,
                    layer.layer_id,
                )
        if len(set(output_ids.values())) != len(output_ids):
            duplicate_ids = {
                output_id for output_id in output_ids.values()
                if tuple(output_ids.values()).count(output_id) > 1
            }
            if any(
                domains[layer.domain_id].primary_layer_id != layer.layer_id
                for layer in presentation.layers
                if layer.layer_id in output_ids
                and output_ids[layer.layer_id] in duplicate_ids
                and layer.role == "primary"
            ):
                raise ValueError("Workspace app layer namespace collided")
        layer_id_maps[presentation.analysis_id] = output_ids
        result_id_maps[presentation.analysis_id] = {
            result.result_id: _namespace(
                presentation.analysis_id,
                result.result_id,
            )
            for result in presentation.results
        }

    result_tables: list[WorkspaceAppResultTable] = []
    metrics: list[WorkspaceAppMetric] = []
    for presentation in presentations:
        domain_keys = {
            domain.domain_id: domain_key_by_ref[
                _namespace(presentation.analysis_id, domain.domain_id)
            ]
            for domain in presentation.domains
        }
        for result in presentation.results:
            table = _table_from_result(
                presentation,
                result,
                domain_keys[result.domain_id],
            )
            result_tables.append(table)
            metrics.extend(
                _metrics_from_result(
                    presentation,
                    result,
                    table.table_id,
                )
            )

    map_layers: list[WorkspaceAppMapLayer] = []
    emitted_layer_ids: set[str] = set()
    for presentation in presentations:
        layer_by_id = {layer.layer_id: layer for layer in presentation.layers}
        domain_by_id = {domain.domain_id: domain for domain in presentation.domains}
        result_by_id = {result.result_id: result for result in presentation.results}
        result_counts: dict[str, int] = {}
        for result in presentation.results:
            result_counts[result.domain_id] = result_counts.get(result.domain_id, 0) + 1
        output_ids = layer_id_maps[presentation.analysis_id]
        output_result_ids = result_id_maps[presentation.analysis_id]
        with _primary_source_decode_scope(presentation) as source_decode_slot:
            for order, layer in enumerate(presentation.layers):
                if map_layer_profile == "source_buffer" and layer.role not in {"source", "buffer"}:
                    continue
                if layer.role not in _ROLES:
                    raise NotImplementedError(
                        f"Unsupported workspace app layer role: {layer.role}"
                    )
                if layer.geometry_mode not in _RENDERABLE_GEOMETRY_MODES:
                    raise NotImplementedError(
                        "Workspace app adapter cannot render geometry mode: "
                        f"{layer.geometry_mode}"
                    )
                expected_mode = "referenced" if layer.role == "result" else "embedded"
                if layer.geometry_mode != expected_mode:
                    raise ValueError("Workspace app layer role and geometry mode drifted")
                output_layer_id = output_ids[layer.layer_id]
                if output_layer_id in emitted_layer_ids:
                    if layer.role != "primary":
                        raise ValueError("Workspace app layer namespace collided")
                    continue
                emitted_layer_ids.add(output_layer_id)
                domain = domain_by_id.get(layer.domain_id or "")
                domain_key = (
                    None
                    if domain is None
                    else domain_key_by_ref[
                        _namespace(presentation.analysis_id, domain.domain_id)
                    ]
                )
                reference = (
                    None
                    if layer.geometry_reference_layer_id is None
                    else layer_by_id.get(layer.geometry_reference_layer_id)
                )
                if layer.geometry_mode == "embedded":
                    if layer.feature_collection_json is None or layer.source_sha256 is None:
                        raise ValueError("Embedded workspace app geometry is incomplete")
                    source = layer
                else:
                    if reference is None or reference.geometry_mode != "embedded":
                        raise ValueError("Workspace app geometry reference is invalid")
                    source = reference
                if source.feature_collection_json is None or source.source_sha256 is None:
                    raise ValueError("Workspace app geometry source is incomplete")
                payload = _decode_renderer_source(
                    source, f"workspace app layer {layer.layer_id}", source_decode_slot,
                )
                result = result_by_id.get(layer.result_id or "")
                if layer.role == "primary":
                    if domain is None:
                        raise ValueError("Primary workspace app layer has no domain")
                    output_feature_collection = _primary_feature_collection(
                        payload,
                        domain,
                    )
                elif layer.role == "result":
                    if domain is None or result is None:
                        raise ValueError("Result workspace app layer is incomplete")
                    output_feature_collection = _result_feature_collection(
                        payload,
                        domain,
                        result,
                    )
                else:
                    output_feature_collection = payload
                output_reference_id = (
                    None
                    if layer.geometry_reference_layer_id is None
                    else output_ids[layer.geometry_reference_layer_id]
                )
                output_result_id = (
                    None
                    if layer.result_id is None
                    else output_result_ids[layer.result_id]
                )
                renderer_payload = _renderer_layer_payload(
                    output_layer_id=output_layer_id,
                    analysis_id=presentation.analysis_id,
                    layer=layer,
                    domain_key=domain_key,
                    output_reference_id=output_reference_id,
                    output_result_id=output_result_id,
                    presentation_signature=(
                        presentation.presentation_signature_sha256
                    ),
                    feature_collection=output_feature_collection,
                    result=result,
                    result_count_for_domain=(
                        0 if domain is None else result_counts.get(domain.domain_id, 0)
                    ),
                    area_result_id=presentation.area_capability_id,
                    order=order,
                )
                plain_metadata = _constructed_renderer_values_are_plain(renderer_payload, result)
                renderer_payload_json, output_fc_sha256 = _serialized_renderer_geometry(
                    renderer_payload, output_feature_collection,
                    plain_metadata=plain_metadata,
                )
                renderer_payload_sha256 = hashlib.sha256(
                    renderer_payload_json.encode("utf-8")
                ).hexdigest()
                if (type(renderer_payload_json) is str
                        and renderer_payload.get("feature_collection") is output_feature_collection
                        and len(constructed_renderer_integrity) < _CONSTRUCTED_RENDERER_MAX_ENTRIES
                        and plain_metadata):
                    constructed_renderer_integrity[id(renderer_payload_json)] = _ConstructedRendererIntegrity(
                        renderer_payload_json,
                        _RendererIntegrityEvidence(renderer_payload_sha256, output_fc_sha256,
                                                   len(output_feature_collection["features"])),
                    )
                app_layer = WorkspaceAppMapLayer(
                    layer_id=output_layer_id,
                    analysis_id=presentation.analysis_id,
                    source_layer_id=layer.layer_id,
                    role=layer.role,
                    geometry_mode=layer.geometry_mode,
                    domain_key=domain_key,
                    geometry_reference_layer_id=output_reference_id,
                    source_layer_ids=tuple(
                        output_ids[source_id] for source_id in layer.source_layer_ids
                    ),
                    result_id=output_result_id,
                    operation=layer.operation,
                    result_semantics=layer.result_semantics,
                    preview_result_signature_sha256=(
                        layer.preview_result_signature_sha256
                    ),
                    presentation_signature_sha256=(
                        presentation.presentation_signature_sha256
                    ),
                    geometry_source_sha256=source.source_sha256,
                    feature_count=len(output_feature_collection["features"]),
                    feature_collection_sha256=output_fc_sha256,
                    renderer_payload_json=renderer_payload_json,
                    renderer_payload_sha256=renderer_payload_sha256,
                    layer_signature_sha256="0" * 64,
                )
                app_layer = replace(
                    app_layer,
                    layer_signature_sha256=_canonical_sha256(
                        _layer_signature_payload(app_layer)
                    ),
                )
                map_layers.append(app_layer)

    adapter = WorkspaceAppAdapter(
        schema_version=(WORKSPACE_APP_ADAPTER_SCHEMA_VERSION if map_layer_profile == "full"
                        else WORKSPACE_SOURCE_BUFFER_APP_ADAPTER_SCHEMA_VERSION),
        access_scope=first.access_scope,
        region_id=first.region_id,
        target_resolution=first.target_resolution,
        presentations=bindings,
        domains=tuple(domain_by_key.values()),
        map_layers=tuple(map_layers),
        result_tables=tuple(result_tables),
        metrics=tuple(metrics),
        adapter_signature_sha256="0" * 64,
        map_layer_profile=map_layer_profile,
        domain_geometry=tuple(domain_geometry_by_key.items()),
    )
    adapter = replace(
        adapter,
        adapter_signature_sha256=_canonical_sha256(
            _adapter_signature_payload(adapter)
        ),
    )
    _validate_workspace_app_adapter(adapter, constructed_renderer_integrity)
    return adapter


def adapt_workspace_analysis_presentation(
    presentation: WorkspaceAnalysisPresentation,
) -> WorkspaceAppAdapter:
    return build_workspace_app_adapter((presentation,))


def workspace_app_map_layer_dicts(
    adapter: WorkspaceAppAdapter,
) -> tuple[dict[str, Any], ...]:
    validate_workspace_app_adapter(adapter)
    return tuple(layer.renderer_dict() for layer in adapter.map_layers)


def workspace_region_domain_map_layer_dict(
    region_id: str,
) -> tuple[dict[str, Any], int]:
    """Build one exact neutral map layer for geography-only review.

    The caller remains responsible for access authorization. This adapter only
    consumes a validated region geography contract and its checksum-bound
    standard-domain artifact; ambiguous or incomplete geography fails closed.
    """

    from .catalogs import load_region_geography
    from .sources import load_region_analysis_domain_display_artifact

    normalized_region_id = str(region_id or "").strip().lower()
    if not normalized_region_id:
        raise ValueError("Workspace domain map layer requires a region id")
    geography = load_region_geography(normalized_region_id)
    standard_domains = tuple(
        domain
        for domain in geography.analysis_domains.values()
        if domain.purpose == "standard_group_analysis"
    )
    if len(standard_domains) != 1:
        raise ValueError(
            "A read-only workspace map requires exactly one declared "
            "standard analysis domain"
        )
    domain = standard_domains[0]
    artifact = load_region_analysis_domain_display_artifact(
        normalized_region_id,
        domain.id,
        domain.artifacts.resolution,
    )
    feature_collection = json.loads(artifact.feature_collection_json)
    if (
        not isinstance(feature_collection, dict)
        or feature_collection.get("type") != "FeatureCollection"
        or not isinstance(feature_collection.get("features"), list)
    ):
        raise ValueError("Workspace domain map artifact is not GeoJSON")
    layer = {
        "name": f"{normalized_region_id} · analysis domain R{artifact.resolution}",
        "feature_collection": feature_collection,
        "fill_property": "fill",
        "legend_items": [
            {
                "label": "Technically validated analysis domain",
                "color": "#2f855a",
            }
        ],
        "legend_id": f"workspace::domain::{domain.id}",
        "legend_title": "Analysis domain",
        "legend_note": (
            f"Read-only geometry · {artifact.cell_count} H3 cells · "
            f"R{artifact.resolution}"
        ),
        "default_visible": True,
        "stroke": True,
        "weight": 0.45,
        "fill_opacity": 0.24,
        "stroke_opacity": 0.72,
        "fill_color": "#2f855a",
        "stroke_color": "#276749",
        "use_global_opacity": False,
        "interaction_role": "primary_result",
        "layer_kind": "hex",
        "z_index": 400,
        "workspace_layer_id": f"domain::{domain.id}",
        "workspace_role": "primary",
        "workspace_geometry_mode": "embedded",
    }
    return layer, artifact.resolution


def workspace_app_result_table_dicts(
    adapter: WorkspaceAppAdapter,
) -> tuple[dict[str, Any], ...]:
    validate_workspace_app_adapter(adapter)
    return tuple(table.renderer_dict() for table in adapter.result_tables)


def workspace_app_metric_dicts(
    adapter: WorkspaceAppAdapter,
) -> tuple[dict[str, Any], ...]:
    validate_workspace_app_adapter(adapter)
    return tuple(metric.renderer_dict() for metric in adapter.metrics)


def _cell_ids_sha256(values: list[str]) -> str:
    return hashlib.sha256(
        "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    ).hexdigest()


def _renderer_domain_evidence(
    payload: Mapping[str, Any],
    domain: WorkspaceAppDomainBinding,
) -> tuple[list[str], float]:
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("Workspace app domain renderer has no feature list")
    cell_ids: list[str] = []
    areas_km2: list[float] = []
    for index, feature in enumerate(features):
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(properties, dict):
            raise ValueError(
                f"Workspace app domain renderer feature {index} is invalid"
            )
        cell_id = _exact_text(
            str(properties.get(domain.id_field) or ""),
            "workspace app rendered domain cell id",
        )
        raw_area = properties.get(domain.area_field)
        area = _number(
            raw_area,
            f"workspace app rendered domain area for {cell_id}",
            positive=True,
        )
        cell_ids.append(cell_id)
        areas_km2.append(area / 1_000_000.0 if domain.area_unit == "m2" else area)
    return cell_ids, math.fsum(areas_km2)


def validate_workspace_app_adapter(adapter: WorkspaceAppAdapter) -> None:
    _validate_workspace_app_adapter(adapter)


def _validate_result_features(
    layer: WorkspaceAppMapLayer,
    table: WorkspaceAppResultTable,
    domain: WorkspaceAppDomainBinding,
) -> None:
    field_ids = tuple(column.field_id for column in table.columns)
    cell_index = field_ids.index("cell_id")
    # Builtin immutable rows can be compared directly. Other collections keep
    # the original strict zip/dictionary behavior, including error ordering.
    plain_rows = (
        type(table) is WorkspaceAppResultTable
        and type(table.columns) is tuple
        and all(type(column) is WorkspaceAppTableColumn for column in table.columns)
        and all(type(field_id) is str for field_id in field_ids)
        and len(field_ids) == len(set(field_ids))
        and type(table.rows) is tuple
        and all(type(row) is tuple and len(row) == len(field_ids) for row in table.rows)
    )
    if plain_rows:
        result_keys = tuple(f"result_{field_id}" for field_id in field_ids)
        rows_by_id = {str(row[cell_index]): row for row in table.rows}
    else:
        rows_by_id = {
            str(row[cell_index]): dict(zip(field_ids, row, strict=True))
            for row in table.rows
        }
    payload = layer.renderer_dict()["feature_collection"]
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("Workspace app result geometry has no features")
    observed_ids: set[str] = set()
    for feature in features:
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(properties, dict):
            raise ValueError("Workspace app result geometry is invalid")
        cell_id = _exact_text(
            str(properties.get(domain.id_field) or ""),
            "workspace app rendered result cell id",
        )
        row = rows_by_id.get(cell_id)
        if row is None or cell_id in observed_ids:
            raise ValueError("Workspace app result geometry escaped its table")
        observed_ids.add(cell_id)
        if plain_rows:
            drifted = any(
                properties.get(key) != value
                for key, value in zip(result_keys, row, strict=True)
            )
        else:
            drifted = any(
                properties.get(f"result_{field_id}") != value
                for field_id, value in row.items()
            )
        if drifted:
            raise ValueError("Workspace app rendered result values drifted")
    if observed_ids != set(rows_by_id):
        raise ValueError("Workspace app result geometry coverage drifted")


_RESULT_EVIDENCE_LIMIT_BYTES = 64 * 1024 * 1024
_RESULT_EVIDENCE_SCALARS = (str, int, float, bool, type(None))
_RESULT_RENDERER_METHOD = WorkspaceAppMapLayer.renderer_dict


@dataclass(frozen=True, slots=True)
class _ResultFeatureEvidence:
    text: str
    id_field: str
    property_keys: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    charge: int


def _derive_result_feature_evidence(
    text: str, id_field: str, payload: Any, budget: int,
) -> _ResultFeatureEvidence | None:
    """Retain actual rendered scalars, never table values or decoded geometry.

    Unsupported input declines reuse without moving its semantic error ahead
    of the original late comparison. Charge scalar referents per occurrence,
    even shared constants, plus tuple/key storage and construction allowance.
    Text and id_field already belong to the adapter; the caller budgets its map.
    """
    if type(text) is not str or type(id_field) is not str or type(payload) is not dict:
        return None
    collection = payload.get("feature_collection")
    if type(collection) is not dict or collection.get("type") != "FeatureCollection":
        return None
    features = collection.get("features")
    if type(features) is not list or not features or type(features[0]) is not dict:
        return None
    first = features[0].get("properties")
    if type(first) is not dict or not all(type(key) is str for key in first):
        return None
    keys = tuple(key for key in first if key.startswith("result_"))
    if not keys:
        return None
    get_values = itemgetter(id_field, *keys)
    # Prepare one tuple projection; retain both original positions and values.
    cell_index = keys.index("result_cell_id") + 1 if "result_cell_id" in keys else None
    share_row = (itemgetter(*(0 if index == cell_index else index
                              for index in range(len(keys) + 1)))
                 if cell_index is not None else None)
    charge = (
        sys.getsizeof(_ResultFeatureEvidence(text, id_field, (), (), 0))
        + sys.getsizeof(keys) + sum(sys.getsizeof(key) for key in keys)
        + sys.getsizeof(()) + sys.getsizeof([]) + sys.getsizeof(0)
    )
    rows = []
    for feature in features:
        if type(feature) is not dict:
            return None
        properties = feature.get("properties")
        if type(properties) is not dict:
            return None
        try:
            row = get_values(properties)
        except KeyError:
            return None
        if not all(type(value) in _RESULT_EVIDENCE_SCALARS for value in row):
            return None
        charge += sys.getsizeof(row) + sum(sys.getsizeof(value) for value in row) + 24
        if charge > budget:
            return None
        # Charge the original values per occurrence, exactly as before.
        # No decoded payload mutation and no cross-row/string-global pool.
        if (cell_index is not None and type(row[0]) is str
                and type(row[cell_index]) is str
                and row[0] is not row[cell_index] and row[0] == row[cell_index]):
            row = share_row(row)
        rows.append(row)
    return _ResultFeatureEvidence(text, id_field, keys, tuple(rows), charge)


def _validate_result_feature_evidence(
    layer: WorkspaceAppMapLayer,
    table: WorkspaceAppResultTable,
    domain: WorkspaceAppDomainBinding,
    evidence: _ResultFeatureEvidence | None,
) -> None:
    """Compare current table values at the original late validation position."""
    try:
        if (
            type(evidence) is not _ResultFeatureEvidence
            or type(layer) is not WorkspaceAppMapLayer
            or WorkspaceAppMapLayer.renderer_dict is not _RESULT_RENDERER_METHOD
            or "renderer_dict" in vars(layer)
            or evidence.text is not layer.renderer_payload_json
            or type(domain) is not WorkspaceAppDomainBinding
            or type(domain.id_field) is not str or evidence.id_field != domain.id_field
            or type(table) is not WorkspaceAppResultTable
            or type(table.columns) is not tuple
            or any(type(column) is not WorkspaceAppTableColumn
                   or type(column.field_id) is not str for column in table.columns)
            or type(table.rows) is not tuple
            or any(type(row) is not tuple for row in table.rows)
        ):
            return _validate_result_features(layer, table, domain)
        field_ids = tuple(column.field_id for column in table.columns)
        if (
            len(field_ids) != len(set(field_ids)) or field_ids.count("cell_id") != 1
            or any(len(row) != len(field_ids)
                   or any(type(value) not in _RESULT_EVIDENCE_SCALARS for value in row)
                   for row in table.rows)
        ):
            return _validate_result_features(layer, table, domain)
        keys = tuple(f"result_{field_id}" for field_id in field_ids)
        index_by_key = {key: index + 1 for index, key in enumerate(evidence.property_keys)}
        if any(key not in index_by_key for key in keys):
            return _validate_result_features(layer, table, domain)
        indices = tuple(index_by_key[key] for key in keys)
        cell_index = field_ids.index("cell_id")
        rows_by_id = {str(row[cell_index]): row for row in table.rows}
        observed_ids: set[str] = set()
        for values in evidence.rows:
            cell_id = _exact_text(
                str(values[0] or ""), "workspace app rendered result cell id",
            )
            row = rows_by_id.get(cell_id)
            if row is None or cell_id in observed_ids:
                raise ValueError("Workspace app result geometry escaped its table")
            observed_ids.add(cell_id)
            if any(values[index] != value for index, value in zip(indices, row, strict=True)):
                raise ValueError("Workspace app rendered result values drifted")
        if observed_ids != set(rows_by_id):
            raise ValueError("Workspace app result geometry coverage drifted")
    finally:
        # A retained exception traceback must not keep an entire scalar record.
        evidence = None
        values = None


def _validate_workspace_app_adapter(
    adapter: WorkspaceAppAdapter,
    constructed_renderer_integrity: dict[int, _ConstructedRendererIntegrity] | None = None,
) -> None:
    # Only construction uses these operation-local records. Public validation
    # keeps its complete independent decode path; nothing crosses calls.
    result_evidence = {} if constructed_renderer_integrity is not None else None
    try:
        _validate_workspace_app_adapter_contents(
            adapter, constructed_renderer_integrity, result_evidence,
        )
    finally:
        if result_evidence is not None:
            result_evidence.clear()


def _validate_workspace_app_adapter_contents(
    adapter: WorkspaceAppAdapter,
    constructed_renderer_integrity: dict[int, _ConstructedRendererIntegrity] | None,
    result_evidence: dict[str, _ResultFeatureEvidence | None] | None,
) -> None:
    if not isinstance(adapter, WorkspaceAppAdapter):
        raise TypeError("adapter must be a WorkspaceAppAdapter")
    if adapter.schema_version not in {
        WORKSPACE_APP_ADAPTER_SCHEMA_VERSION, WORKSPACE_SOURCE_BUFFER_APP_ADAPTER_SCHEMA_VERSION,
    }:
        raise NotImplementedError(
            f"Unsupported workspace app adapter schema: {adapter.schema_version}"
        )
    compact = adapter.schema_version == WORKSPACE_SOURCE_BUFFER_APP_ADAPTER_SCHEMA_VERSION
    if (type(adapter.map_layer_profile) is not str
            or adapter.map_layer_profile != ("source_buffer" if compact else "full")
            or (not compact and adapter.domain_geometry != ())):
        raise ValueError("Workspace app schema and map-layer profile drifted")
    _exact_text(adapter.access_scope, "workspace app access scope")
    _exact_text(adapter.region_id, "workspace app region id")
    resolution = _integer(
        adapter.target_resolution,
        "workspace app target resolution",
    )
    if resolution < 0 or resolution > 15:
        raise ValueError("Workspace app target resolution is outside H3 bounds")
    if any(
        not isinstance(value, tuple)
        for value in (
            adapter.presentations,
            adapter.domains,
            adapter.map_layers,
            adapter.result_tables,
            adapter.metrics,
        )
    ):
        raise TypeError("Workspace app adapter collections must be tuples")
    if not adapter.presentations:
        raise ValueError("Workspace app adapter has no presentation binding")
    presentation_signatures: dict[str, str] = {}
    for binding in adapter.presentations:
        if not isinstance(binding, WorkspaceAppPresentationBinding):
            raise TypeError("Workspace app presentation binding is invalid")
        analysis_id = _exact_text(binding.analysis_id, "workspace app analysis id")
        signature = _digest(
            binding.presentation_signature_sha256,
            "workspace app presentation signature",
        )
        if analysis_id in presentation_signatures:
            raise ValueError("Workspace app analysis binding is duplicated")
        presentation_signatures[analysis_id] = signature

    domains: dict[str, WorkspaceAppDomainBinding] = {}
    domain_refs: set[str] = set()
    for domain in adapter.domains:
        if not isinstance(domain, WorkspaceAppDomainBinding):
            raise TypeError("Workspace app domain binding is invalid")
        key = _digest(domain.domain_key, "workspace app domain key")
        if key in domains or domain.role not in _DOMAIN_ROLES:
            raise ValueError("Workspace app domain identity is invalid")
        domains[key] = domain
        if domain.resolution != resolution:
            raise ValueError("Workspace app domain resolution drifted")
        _digest(domain.source_sha256, "workspace app domain source digest")
        _digest(domain.cell_ids_sha256, "workspace app domain cell digest")
        _integer(domain.cell_count, "workspace app domain count", positive=True)
        _number(domain.total_area_km2, "workspace app domain area", positive=True)
        _exact_text(domain.id_field, "workspace app domain id field")
        _exact_text(domain.area_field, "workspace app domain area field")
        _exact_text(domain.area_unit, "workspace app domain area unit")
        _exact_text(domain.primary_map_layer_id, "workspace app primary layer id")
        if (
            not isinstance(domain.presentation_domain_refs, tuple)
            or not domain.presentation_domain_refs
            or len(domain.presentation_domain_refs)
            != len(set(domain.presentation_domain_refs))
        ):
            raise ValueError("Workspace app domain references are invalid")
        for reference in domain.presentation_domain_refs:
            _exact_text(reference, "workspace app presentation domain reference")
            analysis_id = reference.split("::", 1)[0]
            if analysis_id not in presentation_signatures or reference in domain_refs:
                raise ValueError("Workspace app domain reference is unauthorized")
            domain_refs.add(reference)
        if compact:
            primary_analysis, separator, primary_id = domain.primary_map_layer_id.partition("::")
            if (not separator or not primary_id
                    or primary_analysis != domain.presentation_domain_refs[0].split("::", 1)[0]):
                raise ValueError("Workspace app compact primary reference escaped its presentation")
        expected_key = _canonical_sha256(
            {
                "role": domain.role,
                "resolution": domain.resolution,
                "source_sha256": domain.source_sha256,
                "cell_ids_sha256": domain.cell_ids_sha256,
                "cell_count": domain.cell_count,
                "total_area_km2": domain.total_area_km2,
                "id_field": domain.id_field,
                "area_field": domain.area_field,
                "area_unit": domain.area_unit,
            }
        )
        if key != expected_key:
            raise ValueError("Workspace app domain key does not match its identity")

    # Avoid an extra hash/equality callback through foreign domain-key objects.
    plain_domain_keys = result_evidence is not None and all(type(key) is str for key in domains)
    evidence_charge = 0
    map_layers: dict[str, WorkspaceAppMapLayer] = {}
    for layer in adapter.map_layers:
        if not isinstance(layer, WorkspaceAppMapLayer):
            raise TypeError("Workspace app map layer is invalid")
        layer_id = _exact_text(layer.layer_id, "workspace app layer id")
        if (layer_id in map_layers or layer.role not in _ROLES
                or (compact and layer.role not in {"source", "buffer"})):
            raise ValueError("Workspace app layer identity is invalid")
        map_layers[layer_id] = layer
        _exact_text(layer.source_layer_id, "workspace app source layer id")
        if layer.geometry_mode not in _RENDERABLE_GEOMETRY_MODES:
            raise NotImplementedError(
                f"Unsupported workspace app geometry mode: {layer.geometry_mode}"
            )
        expected_mode = "referenced" if layer.role == "result" else "embedded"
        if layer.geometry_mode != expected_mode:
            raise ValueError("Workspace app layer role and mode drifted")
        expected_presentation_signature = presentation_signatures.get(
            layer.analysis_id
        )
        if (
            expected_presentation_signature is None
            or layer.presentation_signature_sha256
            != expected_presentation_signature
        ):
            raise ValueError("Workspace app layer escaped its presentation")
        if layer.domain_key is not None and layer.domain_key not in domains:
            raise ValueError("Workspace app layer references an unknown domain")
        if (layer.role in {"primary", "result"}) != (
            layer.domain_key is not None
        ):
            raise ValueError("Workspace app layer domain binding drifted")
        if not isinstance(layer.source_layer_ids, tuple) or len(
            layer.source_layer_ids
        ) != len(set(layer.source_layer_ids)):
            raise ValueError("Workspace app source-layer references are invalid")
        _optional_text(layer.result_id, "workspace app result id")
        _optional_text(layer.operation, "workspace app operation")
        _optional_text(layer.result_semantics, "workspace app result semantics")
        _optional_digest(
            layer.preview_result_signature_sha256,
            "workspace app preview result signature",
        )
        if (layer.role == "buffer") != (
            layer.preview_result_signature_sha256 is not None
        ):
            raise ValueError("Workspace app preview signature escaped its buffer")
        _digest(layer.geometry_source_sha256, "workspace app geometry source")
        _integer(layer.feature_count, "workspace app feature count")
        _digest(
            layer.feature_collection_sha256,
            "workspace app feature collection digest",
        )
        _digest(layer.renderer_payload_sha256, "workspace app renderer digest")
        _digest(layer.layer_signature_sha256, "workspace app layer signature")
        if not isinstance(layer.renderer_payload_json, str):
            raise TypeError("Workspace app renderer payload must be JSON text")
        try:
            renderer_text = layer.renderer_payload_json
            renderer_payload, integrity = _decode_constructed_renderer_payload(
                renderer_text, constructed_renderer_integrity,
            )
        except json.JSONDecodeError as exc:
            raise ValueError("Workspace app renderer payload is unreadable") from exc
        renderer_payload = _mapping(renderer_payload, "workspace renderer payload")
        _exact_keys(
            renderer_payload,
            _RENDERER_LAYER_KEYS,
            "workspace renderer payload",
        )
        if integrity.payload_sha256 != layer.renderer_payload_sha256:
            raise ValueError("Workspace app renderer payload digest drifted")
        payload_fc = renderer_payload["feature_collection"]
        if (
            not isinstance(payload_fc, dict)
            or payload_fc.get("type") != "FeatureCollection"
            or not isinstance(payload_fc.get("features"), list)
            or integrity.feature_count != layer.feature_count
            or integrity.feature_collection_sha256 != layer.feature_collection_sha256
        ):
            raise ValueError("Workspace app renderer geometry drifted")
        if (
            renderer_payload["workspace_layer_id"] != layer.layer_id
            or renderer_payload["workspace_source_layer_id"]
            != layer.source_layer_id
            or renderer_payload["workspace_role"] != layer.role
            or renderer_payload["workspace_domain_key"] != layer.domain_key
            or renderer_payload["workspace_result_id"] != layer.result_id
            or renderer_payload["workspace_geometry_mode"]
            != layer.geometry_mode
            or renderer_payload["workspace_geometry_reference_layer_id"]
            != layer.geometry_reference_layer_id
            or renderer_payload[
                "workspace_preview_result_signature_sha256"
            ]
            != layer.preview_result_signature_sha256
            or renderer_payload["workspace_presentation_signature_sha256"]
            != layer.presentation_signature_sha256
        ):
            raise ValueError("Workspace app renderer metadata drifted")
        for text_key in (
            "name",
            "fill_property",
            "stroke_property",
            "legend_id",
            "legend_title",
            "legend_note",
            "layer_kind",
            "opacity_family",
            "workspace_layer_id",
            "workspace_source_layer_id",
            "workspace_role",
            "workspace_geometry_mode",
            "workspace_presentation_signature_sha256",
        ):
            if not isinstance(renderer_payload[text_key], str):
                raise TypeError(
                    f"Workspace renderer {text_key} must be text"
                )
        for optional_text_key in (
            "interaction_role",
            "source_layer_id",
            "buffer_layer_id",
            "workspace_domain_key",
            "workspace_result_id",
            "workspace_geometry_reference_layer_id",
            "workspace_preview_result_signature_sha256",
        ):
            if renderer_payload[optional_text_key] is not None and not isinstance(
                renderer_payload[optional_text_key], str
            ):
                raise TypeError(
                    f"Workspace renderer {optional_text_key} must be text or null"
                )
        for boolean_key in (
            "default_visible",
            "stroke",
            "use_global_opacity",
        ):
            if not isinstance(renderer_payload[boolean_key], bool):
                raise TypeError(
                    f"Workspace renderer {boolean_key} must be boolean"
                )
        for number_key in (
            "weight",
            "fill_opacity",
            "stroke_opacity",
            "point_radius",
            "z_index",
        ):
            _number(
                renderer_payload[number_key],
                f"workspace renderer {number_key}",
            )
        for color_key in ("fill_color", "stroke_color"):
            _exact_text(
                renderer_payload[color_key],
                f"workspace renderer {color_key}",
            )
        legend_items = renderer_payload["legend_items"]
        if not isinstance(legend_items, list) or not legend_items:
            raise ValueError("Workspace renderer legend items are incomplete")
        for item in legend_items:
            if (
                not isinstance(item, dict)
                or set(item) != {"label", "color"}
                or not isinstance(item["label"], str)
                or not isinstance(item["color"], str)
            ):
                raise ValueError("Workspace renderer legend item is invalid")
        expected_layer_kind = (
            "hex" if layer.role in {"primary", "result"} else "vector"
        )
        if (
            renderer_payload["layer_kind"] != expected_layer_kind
            or renderer_payload["interaction_role"]
            != (
                "primary_result"
                if layer.role in {"primary", "result"}
                else None
            )
        ):
            raise ValueError("Workspace app renderer role semantics drifted")
        if (layer.role == "result") != (layer.result_id is not None):
            raise ValueError("Workspace app result identity escaped its layer")
        if _canonical_sha256(
            _layer_signature_payload(layer)
        ) != layer.layer_signature_sha256:
            raise ValueError("Workspace app layer signature does not match")
        if (
            result_evidence is not None
            and plain_domain_keys
            and type(layer) is WorkspaceAppMapLayer
            and type(layer.role) is str and layer.role == "result"
            and type(layer_id) is str and type(layer.domain_key) is str
            and type(domains[layer.domain_key]) is WorkspaceAppDomainBinding
            and WorkspaceAppMapLayer.renderer_dict is _RESULT_RENDERER_METHOD
            and "renderer_dict" not in vars(layer)
            and renderer_text is layer.renderer_payload_json
        ):
            # Existing validated string keys need no new allocation. Reserve
            # the dictionary slot first so its actual capacity is budgeted.
            result_evidence[layer_id] = None
            if evidence_charge + sys.getsizeof(result_evidence) > _RESULT_EVIDENCE_LIMIT_BYTES:
                # Dictionary growth itself can exhaust the remaining budget.
                # Discard the optional records; all comparisons still run.
                result_evidence.clear()
                evidence_charge = 0
                continue
            result_evidence[layer_id] = _derive_result_feature_evidence(
                renderer_text, domains[layer.domain_key].id_field, renderer_payload,
                _RESULT_EVIDENCE_LIMIT_BYTES - evidence_charge - sys.getsizeof(result_evidence),
            )
            if result_evidence[layer_id] is None:
                result_evidence.pop(layer_id)
            else:
                evidence_charge += result_evidence[layer_id].charge

    if not compact and set(domain.primary_map_layer_id for domain in domains.values()) != {
        layer.layer_id for layer in map_layers.values() if layer.role == "primary"
    }:
        raise ValueError("Workspace app domain primary layers drifted")
    if compact:
        if (not isinstance(adapter.domain_geometry, tuple)
                or any(not isinstance(pair, tuple) or len(pair) != 2
                       or not isinstance(pair[0], str) or not isinstance(pair[1], str)
                       for pair in adapter.domain_geometry)
                or tuple(pair[0] for pair in adapter.domain_geometry) != tuple(domains)):
            raise ValueError("Workspace app compact domain geometry drifted")
        domain_geometry = dict(adapter.domain_geometry)
    for domain in domains.values():
        if compact:
            source_json = domain_geometry[domain.domain_key]
            if hashlib.sha256(source_json.encode("utf-8")).hexdigest() != domain.source_sha256:
                raise ValueError("Workspace app compact domain source digest drifted")
            primary_payload = _feature_collection(source_json, "workspace app compact domain")
        else:
            primary = map_layers[domain.primary_map_layer_id]
            if (
                primary.role != "primary"
                or primary.domain_key != domain.domain_key
                or primary.geometry_source_sha256 != domain.source_sha256
                or primary.feature_count != domain.cell_count
            ):
                raise ValueError("Workspace app primary layer escaped its domain")
            primary_payload = primary.renderer_dict()["feature_collection"]
        cell_ids, total_area_km2 = _renderer_domain_evidence(
            primary_payload,
            domain,
        )
        if (
            (compact and len(cell_ids) != domain.cell_count)
            or len(cell_ids) != len(set(cell_ids))
            or _cell_ids_sha256(cell_ids) != domain.cell_ids_sha256
            or not math.isclose(
                total_area_km2,
                domain.total_area_km2,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
        ):
            raise ValueError("Workspace app primary geometry drifted from domain")
    for layer in map_layers.values():
        for source_layer_id in layer.source_layer_ids:
            if source_layer_id not in map_layers:
                raise ValueError("Workspace app layer references an unknown source")
        if layer.geometry_mode == "referenced":
            reference = map_layers.get(layer.geometry_reference_layer_id or "")
            if (
                reference is None
                or reference.role != "primary"
                or reference.geometry_mode != "embedded"
                or reference.domain_key != layer.domain_key
                or reference.geometry_source_sha256
                != layer.geometry_source_sha256
            ):
                raise ValueError("Workspace app geometry reference drifted")
        elif layer.geometry_reference_layer_id is not None:
            raise ValueError("Embedded workspace app layer retained a reference")

    tables: dict[str, WorkspaceAppResultTable] = {}
    for table in adapter.result_tables:
        if not isinstance(table, WorkspaceAppResultTable):
            raise TypeError("Workspace app result table is invalid")
        table_id = _exact_text(table.table_id, "workspace app table id")
        if table_id in tables or table.domain_key not in domains:
            raise ValueError("Workspace app result table identity is invalid")
        tables[table_id] = table
        if presentation_signatures.get(table.analysis_id) != (
            table.presentation_signature_sha256
        ):
            raise ValueError("Workspace app result table escaped its presentation")
        _exact_text(table.source_result_id, "workspace app source result id")
        if not isinstance(table.columns, tuple) or not isinstance(table.rows, tuple):
            raise TypeError("Workspace app result table collections must be tuples")
        if not table.columns:
            raise ValueError("Workspace app result table has no columns")
        field_ids: list[str] = []
        for column in table.columns:
            if not isinstance(column, WorkspaceAppTableColumn):
                raise TypeError("Workspace app table column is invalid")
            field_ids.append(_exact_text(column.field_id, "workspace app field id"))
            if column.value_type not in _VALUE_TYPES:
                raise NotImplementedError(
                    f"Unsupported workspace app value type: {column.value_type}"
                )
            _optional_text(column.unit, "workspace app field unit")
            if not isinstance(column.nullable, bool):
                raise TypeError("Workspace app field nullable flag must be boolean")
        if len(field_ids) != len(set(field_ids)) or field_ids.count("cell_id") != 1:
            raise ValueError("Workspace app result table fields are invalid")
        if table.row_count != len(table.rows) or table.row_count != domains[
            table.domain_key
        ].cell_count:
            raise ValueError("Workspace app result table count drifted")
        cell_index = field_ids.index("cell_id")
        cell_ids: list[str] = []
        for row in table.rows:
            if not isinstance(row, tuple) or len(row) != len(table.columns):
                raise ValueError("Workspace app result row width drifted")
            for column, value in zip(table.columns, row, strict=True):
                if value is None:
                    if not column.nullable:
                        raise ValueError("Workspace app result row contains null")
                    continue
                if column.value_type == "string" and not isinstance(value, str):
                    raise TypeError("Workspace app result string type drifted")
                if column.value_type == "boolean" and not isinstance(value, bool):
                    raise TypeError("Workspace app result boolean type drifted")
                if column.value_type == "number":
                    _number(value, "workspace app result number")
            cell_ids.append(_exact_text(str(row[cell_index]), "workspace app cell id"))
        if (
            len(cell_ids) != len(set(cell_ids))
            or _cell_ids_sha256(cell_ids)
            != domains[table.domain_key].cell_ids_sha256
        ):
            raise ValueError("Workspace app result table domain drifted")
        if _canonical_sha256(
            _table_signature_payload(table)
        ) != table.table_signature_sha256:
            raise ValueError("Workspace app result table signature does not match")

    result_layer_ids = {
        layer.result_id for layer in map_layers.values() if layer.role == "result"
    }
    if not compact and result_layer_ids != set(tables):
        raise ValueError("Workspace app result layers and tables drifted")
    for layer in map_layers.values():
        if layer.role != "result":
            continue
        table = tables[layer.result_id or ""]
        domain = domains[table.domain_key]
        if result_evidence is None:
            _validate_result_features(layer, table, domain)
        else:
            _validate_result_feature_evidence(
                layer, table, domain,
                result_evidence.pop(layer.layer_id, None)
                if type(layer) is WorkspaceAppMapLayer and type(layer.layer_id) is str
                else None,
            )

    metric_ids: set[str] = set()
    for metric in adapter.metrics:
        if not isinstance(metric, WorkspaceAppMetric):
            raise TypeError("Workspace app metric is invalid")
        metric_id = _exact_text(metric.metric_id, "workspace app metric id")
        if metric_id in metric_ids or metric.table_id not in tables:
            raise ValueError("Workspace app metric identity is invalid")
        metric_ids.add(metric_id)
        _exact_text(metric.source_metric_id, "workspace app source metric id")
        _number(metric.value, "workspace app metric value")
        _exact_text(metric.unit, "workspace app metric unit")
        table = tables[metric.table_id]
        if metric.presentation_signature_sha256 != (
            table.presentation_signature_sha256
        ):
            raise ValueError("Workspace app metric escaped its result table")
        if _canonical_sha256(
            _metric_signature_payload(metric)
        ) != metric.metric_signature_sha256:
            raise ValueError("Workspace app metric signature does not match")

    if _canonical_sha256(
        _adapter_signature_payload(adapter)
    ) != adapter.adapter_signature_sha256:
        raise ValueError("Workspace app adapter signature does not match")


def validate_workspace_app_adapter_from_presentations(
    adapter: WorkspaceAppAdapter,
    presentations: tuple[WorkspaceAnalysisPresentation, ...],
) -> None:
    validate_workspace_app_adapter(adapter)
    rebuilt = (
        build_workspace_app_adapter(presentations)
        if adapter.map_layer_profile == "full"
        else build_workspace_app_adapter(presentations, map_layer_profile=adapter.map_layer_profile)
    )
    if rebuilt != adapter:
        raise ValueError("Workspace app adapter drifted from its presentations")


_PRESENTATION_BINDING_KEYS = {
    "analysis_id",
    "presentation_signature_sha256",
}
_DOMAIN_KEYS = {
    "domain_key",
    "role",
    "resolution",
    "source_sha256",
    "cell_ids_sha256",
    "cell_count",
    "total_area_km2",
    "id_field",
    "area_field",
    "area_unit",
    "primary_map_layer_id",
    "presentation_domain_refs",
}
_MAP_LAYER_KEYS = {
    "layer_id",
    "analysis_id",
    "source_layer_id",
    "role",
    "geometry_mode",
    "domain_key",
    "geometry_reference_layer_id",
    "source_layer_ids",
    "result_id",
    "operation",
    "result_semantics",
    "preview_result_signature_sha256",
    "presentation_signature_sha256",
    "geometry_source_sha256",
    "feature_count",
    "feature_collection_sha256",
    "renderer_payload_json",
    "renderer_payload_sha256",
    "layer_signature_sha256",
}
_COLUMN_KEYS = {"field_id", "value_type", "unit", "nullable"}
_TABLE_KEYS = {
    "table_id",
    "analysis_id",
    "source_result_id",
    "domain_key",
    "presentation_signature_sha256",
    "columns",
    "rows",
    "row_count",
    "table_signature_sha256",
}
_METRIC_KEYS = {
    "metric_id",
    "table_id",
    "source_metric_id",
    "value",
    "unit",
    "presentation_signature_sha256",
    "metric_signature_sha256",
}
_ADAPTER_KEYS = {
    "schema_version",
    "access_scope",
    "region_id",
    "target_resolution",
    "presentations",
    "domains",
    "map_layers",
    "result_tables",
    "metrics",
    "adapter_signature_sha256",
}


def _parse_presentation_binding(value: Any) -> WorkspaceAppPresentationBinding:
    raw = _mapping(value, "workspace app presentation binding")
    _exact_keys(raw, _PRESENTATION_BINDING_KEYS, "presentation binding")
    return WorkspaceAppPresentationBinding(
        analysis_id=raw["analysis_id"],
        presentation_signature_sha256=raw[
            "presentation_signature_sha256"
        ],
    )


def _parse_domain(value: Any) -> WorkspaceAppDomainBinding:
    raw = _mapping(value, "workspace app domain")
    _exact_keys(raw, _DOMAIN_KEYS, "workspace app domain")
    refs = raw["presentation_domain_refs"]
    if not isinstance(refs, list):
        raise TypeError("Workspace app domain references must be a list")
    return WorkspaceAppDomainBinding(
        domain_key=raw["domain_key"],
        role=raw["role"],
        resolution=raw["resolution"],
        source_sha256=raw["source_sha256"],
        cell_ids_sha256=raw["cell_ids_sha256"],
        cell_count=raw["cell_count"],
        total_area_km2=raw["total_area_km2"],
        id_field=raw["id_field"],
        area_field=raw["area_field"],
        area_unit=raw["area_unit"],
        primary_map_layer_id=raw["primary_map_layer_id"],
        presentation_domain_refs=tuple(refs),
    )


def _parse_map_layer(value: Any) -> WorkspaceAppMapLayer:
    raw = _mapping(value, "workspace app map layer")
    _exact_keys(raw, _MAP_LAYER_KEYS, "workspace app map layer")
    source_ids = raw["source_layer_ids"]
    if not isinstance(source_ids, list):
        raise TypeError("Workspace app source layer ids must be a list")
    return WorkspaceAppMapLayer(
        layer_id=raw["layer_id"],
        analysis_id=raw["analysis_id"],
        source_layer_id=raw["source_layer_id"],
        role=raw["role"],
        geometry_mode=raw["geometry_mode"],
        domain_key=raw["domain_key"],
        geometry_reference_layer_id=raw["geometry_reference_layer_id"],
        source_layer_ids=tuple(source_ids),
        result_id=raw["result_id"],
        operation=raw["operation"],
        result_semantics=raw["result_semantics"],
        preview_result_signature_sha256=raw[
            "preview_result_signature_sha256"
        ],
        presentation_signature_sha256=raw[
            "presentation_signature_sha256"
        ],
        geometry_source_sha256=raw["geometry_source_sha256"],
        feature_count=raw["feature_count"],
        feature_collection_sha256=raw["feature_collection_sha256"],
        renderer_payload_json=raw["renderer_payload_json"],
        renderer_payload_sha256=raw["renderer_payload_sha256"],
        layer_signature_sha256=raw["layer_signature_sha256"],
    )


def _parse_column(value: Any) -> WorkspaceAppTableColumn:
    raw = _mapping(value, "workspace app table column")
    _exact_keys(raw, _COLUMN_KEYS, "workspace app table column")
    return WorkspaceAppTableColumn(
        field_id=raw["field_id"],
        value_type=raw["value_type"],
        unit=raw["unit"],
        nullable=raw["nullable"],
    )


def _parse_table(value: Any) -> WorkspaceAppResultTable:
    raw = _mapping(value, "workspace app result table")
    _exact_keys(raw, _TABLE_KEYS, "workspace app result table")
    columns = raw["columns"]
    rows = raw["rows"]
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise TypeError("Workspace app result table arrays are invalid")
    if not all(isinstance(row, list) for row in rows):
        raise TypeError("Workspace app result rows must be lists")
    return WorkspaceAppResultTable(
        table_id=raw["table_id"],
        analysis_id=raw["analysis_id"],
        source_result_id=raw["source_result_id"],
        domain_key=raw["domain_key"],
        presentation_signature_sha256=raw[
            "presentation_signature_sha256"
        ],
        columns=tuple(_parse_column(column) for column in columns),
        rows=tuple(tuple(row) for row in rows),
        row_count=raw["row_count"],
        table_signature_sha256=raw["table_signature_sha256"],
    )


def _parse_metric(value: Any) -> WorkspaceAppMetric:
    raw = _mapping(value, "workspace app metric")
    _exact_keys(raw, _METRIC_KEYS, "workspace app metric")
    return WorkspaceAppMetric(
        metric_id=raw["metric_id"],
        table_id=raw["table_id"],
        source_metric_id=raw["source_metric_id"],
        value=raw["value"],
        unit=raw["unit"],
        presentation_signature_sha256=raw[
            "presentation_signature_sha256"
        ],
        metric_signature_sha256=raw["metric_signature_sha256"],
    )


def parse_workspace_app_adapter(value: Any) -> WorkspaceAppAdapter:
    raw = _mapping(value, "workspace app adapter")
    compact = raw.get("schema_version") == WORKSPACE_SOURCE_BUFFER_APP_ADAPTER_SCHEMA_VERSION
    _exact_keys(raw, _ADAPTER_KEYS | {"map_layer_profile", "domain_geometry"}
                if compact else _ADAPTER_KEYS, "workspace app adapter")
    geometry = raw["domain_geometry"] if compact else []
    if (not isinstance(geometry, list)
            or any(not isinstance(pair, list) or len(pair) != 2 for pair in geometry)):
        raise TypeError("Workspace app compact domain geometry must be pairs")
    presentations = raw["presentations"]
    domains = raw["domains"]
    map_layers = raw["map_layers"]
    tables = raw["result_tables"]
    metrics = raw["metrics"]
    if not all(
        isinstance(values, list)
        for values in (presentations, domains, map_layers, tables, metrics)
    ):
        raise TypeError("Workspace app adapter collections must be lists")
    adapter = WorkspaceAppAdapter(
        schema_version=raw["schema_version"],
        access_scope=raw["access_scope"],
        region_id=raw["region_id"],
        target_resolution=raw["target_resolution"],
        presentations=tuple(
            _parse_presentation_binding(value) for value in presentations
        ),
        domains=tuple(_parse_domain(value) for value in domains),
        map_layers=tuple(_parse_map_layer(value) for value in map_layers),
        result_tables=tuple(_parse_table(value) for value in tables),
        metrics=tuple(_parse_metric(value) for value in metrics),
        adapter_signature_sha256=raw["adapter_signature_sha256"],
        map_layer_profile=raw["map_layer_profile"] if compact else "full",
        domain_geometry=tuple(tuple(pair) for pair in geometry),
    )
    validate_workspace_app_adapter(adapter)
    return adapter
