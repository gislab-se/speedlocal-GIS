from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import hashlib
import json
import re
from typing import Any

from .workspace_app_adapter import (
    WorkspaceAppAdapter, WorkspaceAppMapLayer, _decode_renderer_payload_json,
)
from .workspace_execution import (
    WorkspaceExecutionBundle,
    validate_workspace_execution_bundle,
)


WORKSPACE_SOURCE_BUFFER_MAP_SCHEMA_VERSION = "1.0"

_DISPLAY_ROLES = frozenset({"source", "buffer"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SIGNED_LAYER_METADATA_KEYS = frozenset(
    {
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
        "renderer_payload_sha256",
    }
)


@dataclass(frozen=True)
class WorkspaceMapAnalysisVisibility:
    """Explicit source/buffer group visibility for one typed analysis."""

    analysis_id: str
    source_group_ids: tuple[str, ...]
    buffer_group_ids: tuple[str, ...]


@dataclass(frozen=True)
class BoundWorkspaceSourceBufferLayer:
    """Compact signed metadata and deferred renderer payload for one layer."""

    layer_id: str
    analysis_id: str
    source_layer_id: str
    group_id: str
    role: str
    source_layer_ids: tuple[str, ...]
    signed_metadata_json: str
    layer_signature_sha256: str
    renderer_payload_json: str
    renderer_payload_sha256: str


@dataclass(frozen=True)
class BoundWorkspaceSourceBufferMap:
    """Validated, compact source/buffer boundary for repeated map toggles."""

    schema_version: str
    execution_signature_sha256: str
    adapter_signature_sha256: str
    analysis_ids: tuple[str, ...]
    group_topology: tuple[tuple[str, tuple[str, ...]], ...]
    layers: tuple[BoundWorkspaceSourceBufferLayer, ...]
    binding_signature_sha256: str


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


def _exact_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty exact string")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _exact_ids(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{label} must be an immutable tuple")
    normalized = tuple(
        _exact_text(item, f"{label} item")
        for item in value
    )
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"{label} contains duplicate ids")
    return normalized


def normalize_workspace_map_group_visibility(
    value: Any,
    *,
    allowed_group_ids: tuple[str, ...],
    label: str,
) -> tuple[str, ...]:
    """Normalize ordered UI visibility without hiding invalid declarations.

    A mapping is accepted for form-like input, but every declared key is
    validated before disabled values are filtered. Values must be real bools;
    truthy strings and integers are never accepted as map policy.
    """

    normalized_label = _exact_text(label, "workspace visibility label")
    allowed = _exact_ids(
        allowed_group_ids,
        f"{normalized_label} allowed group ids",
    )
    if not allowed:
        raise ValueError(f"{normalized_label} has no allowed group ids")

    if isinstance(value, Mapping):
        declared = _exact_ids(
            tuple(value),
            f"{normalized_label} declared group ids",
        )
        for group_id in declared:
            if type(value[group_id]) is not bool:
                raise TypeError(
                    f"{normalized_label} value for {group_id!r} must be bool"
                )
        enabled = tuple(group_id for group_id in declared if value[group_id])
    elif isinstance(value, (list, tuple)):
        declared = _exact_ids(
            tuple(value),
            f"{normalized_label} declared group ids",
        )
        enabled = declared
    else:
        raise TypeError(
            f"{normalized_label} must be an ordered collection or bool mapping"
        )

    unknown = set(declared) - set(allowed)
    if unknown:
        raise ValueError(
            f"{normalized_label} contains unsupported group ids: "
            f"{sorted(unknown)}"
        )
    return enabled


def _analysis_group_topology(
    adapter: WorkspaceAppAdapter,
    analysis_ids: tuple[str, ...],
) -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    """Recover group ownership without reading unrelated renderer objects."""

    if tuple(
        _exact_text(value.analysis_id, "workspace map presentation analysis")
        for value in adapter.presentations
    ) != analysis_ids:
        raise ValueError("Workspace map analyses escaped execution order")

    source_layers = {
        layer.layer_id: layer
        for layer in adapter.map_layers
        if layer.role == "source"
    }
    groups_by_analysis: dict[str, list[str]] = {
        analysis_id: [] for analysis_id in analysis_ids
    }
    group_by_layer_id: dict[str, str] = {}
    assigned_source_ids: set[str] = set()

    for layer in adapter.map_layers:
        if layer.role not in _DISPLAY_ROLES:
            continue
        analysis_id = _exact_text(
            layer.analysis_id,
            "workspace map layer analysis id",
        )
        local_id = _exact_text(
            layer.source_layer_id,
            "workspace map local layer id",
        )
        if analysis_id not in groups_by_analysis:
            raise ValueError("Workspace map layer has an unknown analysis")
        if layer.layer_id != f"{analysis_id}::{local_id}":
            raise ValueError("Workspace map layer escaped its analysis namespace")
        if layer.role == "source":
            if not local_id.startswith("source:") or not local_id.removeprefix(
                "source:"
            ):
                raise ValueError("Workspace source layer has an invalid local id")
            continue

        if not local_id.startswith("buffer:"):
            raise ValueError("Workspace buffer layer has an invalid local id")
        group_id = _exact_text(
            local_id.removeprefix("buffer:"),
            "workspace map canonical group id",
        )
        if group_id in groups_by_analysis[analysis_id]:
            raise ValueError("Workspace map analysis contains a duplicate group")
        if not isinstance(layer.source_layer_ids, tuple) or not layer.source_layer_ids:
            raise ValueError("Workspace buffer group has no source layers")
        groups_by_analysis[analysis_id].append(group_id)
        group_by_layer_id[layer.layer_id] = group_id
        for source_layer_id in layer.source_layer_ids:
            source_id = _exact_text(
                source_layer_id,
                "workspace buffer source layer id",
            )
            source = source_layers.get(source_id)
            if source is None or source.analysis_id != analysis_id:
                raise ValueError(
                    "Workspace buffer references an unknown or foreign source"
                )
            if source_id in assigned_source_ids:
                raise ValueError("Workspace source belongs to multiple groups")
            assigned_source_ids.add(source_id)
            group_by_layer_id[source_id] = group_id

    if assigned_source_ids != set(source_layers):
        raise ValueError("Workspace source is not owned by exactly one group")
    return (
        {
            analysis_id: tuple(group_ids)
            for analysis_id, group_ids in groups_by_analysis.items()
        },
        group_by_layer_id,
    )


def _signed_layer_metadata_json(layer: WorkspaceAppMapLayer) -> str:
    value = layer.as_dict()
    value.pop("renderer_payload_json")
    value.pop("layer_signature_sha256")
    metadata_json = _canonical_json(value)
    if hashlib.sha256(metadata_json.encode("utf-8")).hexdigest() != (
        layer.layer_signature_sha256
    ):
        raise ValueError("Workspace map layer signature does not match metadata")
    return metadata_json


def _bound_layer_signature_payload(
    layer: BoundWorkspaceSourceBufferLayer,
) -> dict[str, Any]:
    return {
        "layer_id": layer.layer_id,
        "analysis_id": layer.analysis_id,
        "source_layer_id": layer.source_layer_id,
        "group_id": layer.group_id,
        "role": layer.role,
        "source_layer_ids": list(layer.source_layer_ids),
        "signed_metadata_json": layer.signed_metadata_json,
        "layer_signature_sha256": layer.layer_signature_sha256,
        "renderer_payload_sha256": layer.renderer_payload_sha256,
    }


def _binding_signature_payload(
    bound: BoundWorkspaceSourceBufferMap,
) -> dict[str, Any]:
    return {
        "schema_version": bound.schema_version,
        "execution_signature_sha256": bound.execution_signature_sha256,
        "adapter_signature_sha256": bound.adapter_signature_sha256,
        "analysis_ids": list(bound.analysis_ids),
        "group_topology": [
            {
                "analysis_id": analysis_id,
                "group_ids": list(group_ids),
            }
            for analysis_id, group_ids in bound.group_topology
        ],
        "layers": [
            _bound_layer_signature_payload(layer) for layer in bound.layers
        ],
    }


def _validated_metadata(
    layer: BoundWorkspaceSourceBufferLayer,
) -> dict[str, Any]:
    if not isinstance(layer.signed_metadata_json, str):
        raise TypeError("Workspace bound layer metadata must be JSON text")
    try:
        value = json.loads(layer.signed_metadata_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Workspace bound layer metadata is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Workspace bound layer metadata must be an object")
    if set(value) != _SIGNED_LAYER_METADATA_KEYS:
        raise ValueError("Workspace bound layer metadata has an invalid schema")
    if _canonical_json(value) != layer.signed_metadata_json:
        raise ValueError("Workspace bound layer metadata is not canonical JSON")
    if hashlib.sha256(layer.signed_metadata_json.encode("utf-8")).hexdigest() != (
        layer.layer_signature_sha256
    ):
        raise ValueError("Workspace bound layer metadata signature does not match")
    expected = {
        "layer_id": layer.layer_id,
        "analysis_id": layer.analysis_id,
        "source_layer_id": layer.source_layer_id,
        "role": layer.role,
        "source_layer_ids": list(layer.source_layer_ids),
        "renderer_payload_sha256": layer.renderer_payload_sha256,
    }
    if any(value[key] != expected_value for key, expected_value in expected.items()):
        raise ValueError("Workspace bound layer metadata escaped its binding")
    return value


def _validate_bound_source_buffer_map(
    bound: BoundWorkspaceSourceBufferMap,
) -> tuple[dict[str, tuple[str, ...]], dict[str, str]]:
    """Validate only compact metadata; renderer JSON remains deferred."""

    if not isinstance(bound, BoundWorkspaceSourceBufferMap):
        raise TypeError("Workspace source/buffer map binding has an invalid type")
    if bound.schema_version != WORKSPACE_SOURCE_BUFFER_MAP_SCHEMA_VERSION:
        raise NotImplementedError("Unsupported workspace source/buffer map schema")
    _digest(bound.execution_signature_sha256, "workspace execution signature")
    _digest(bound.adapter_signature_sha256, "workspace adapter signature")
    analysis_ids = _exact_ids(bound.analysis_ids, "workspace bound analysis ids")
    if not analysis_ids:
        raise ValueError("Workspace source/buffer map requires analyses")

    if not isinstance(bound.group_topology, tuple):
        raise TypeError("Workspace group topology must be an immutable tuple")
    topology: dict[str, tuple[str, ...]] = {}
    topology_order: list[str] = []
    for item in bound.group_topology:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("Workspace group topology item has an invalid type")
        analysis_id = _exact_text(item[0], "workspace topology analysis id")
        if analysis_id in topology:
            raise ValueError("Workspace group topology duplicates an analysis")
        group_ids = _exact_ids(item[1], f"{analysis_id} topology group ids")
        topology_order.append(analysis_id)
        topology[analysis_id] = group_ids
    if tuple(topology_order) != analysis_ids:
        raise ValueError("Workspace group topology escaped analysis order")

    if not isinstance(bound.layers, tuple):
        raise TypeError("Workspace bound map layers must be an immutable tuple")
    layer_ids: set[str] = set()
    source_ids: set[str] = set()
    source_group_by_id: dict[str, str] = {}
    buffer_source_groups: dict[str, str] = {}
    buffer_groups: dict[str, list[str]] = {
        analysis_id: [] for analysis_id in analysis_ids
    }
    for layer in bound.layers:
        if not isinstance(layer, BoundWorkspaceSourceBufferLayer):
            raise TypeError("Workspace bound map layer has an invalid type")
        layer_id = _exact_text(layer.layer_id, "workspace bound layer id")
        analysis_id = _exact_text(
            layer.analysis_id,
            "workspace bound layer analysis id",
        )
        local_id = _exact_text(
            layer.source_layer_id,
            "workspace bound local layer id",
        )
        group_id = _exact_text(layer.group_id, "workspace bound group id")
        role = _exact_text(layer.role, "workspace bound layer role")
        source_layer_ids = _exact_ids(
            layer.source_layer_ids,
            "workspace bound source layer ids",
        )
        _digest(layer.layer_signature_sha256, "workspace layer signature")
        _digest(layer.renderer_payload_sha256, "workspace renderer digest")
        if not isinstance(layer.renderer_payload_json, str):
            raise TypeError("Workspace bound renderer payload must be JSON text")
        if layer_id in layer_ids:
            raise ValueError("Workspace bound map layers contain duplicate ids")
        layer_ids.add(layer_id)
        if analysis_id not in topology or group_id not in topology[analysis_id]:
            raise ValueError("Workspace bound layer has an unknown canonical group")
        if role not in _DISPLAY_ROLES:
            raise ValueError("Workspace bound layer has an unsupported role")
        if layer_id != f"{analysis_id}::{local_id}":
            raise ValueError("Workspace bound layer escaped its analysis namespace")
        if role == "source":
            if (
                not local_id.startswith("source:")
                or not local_id.removeprefix("source:")
                or source_layer_ids
            ):
                raise ValueError("Workspace bound source layer contract is invalid")
            source_ids.add(layer_id)
            source_group_by_id[layer_id] = group_id
        else:
            if local_id != f"buffer:{group_id}" or not source_layer_ids:
                raise ValueError("Workspace bound buffer layer contract is invalid")
            buffer_groups[analysis_id].append(group_id)
            for source_id in source_layer_ids:
                if not source_id.startswith(f"{analysis_id}::source:"):
                    raise ValueError(
                        "Workspace buffer source escaped its analysis namespace"
                    )
                if source_id in buffer_source_groups:
                    raise ValueError("Workspace source belongs to multiple groups")
                buffer_source_groups[source_id] = group_id
        _validated_metadata(layer)

    if any(tuple(buffer_groups[value]) != topology[value] for value in analysis_ids):
        raise ValueError("Workspace buffer layers escaped canonical group topology")
    if source_ids != set(buffer_source_groups):
        raise ValueError("Workspace source is not owned by exactly one group")
    if any(
        source_group_by_id[source_id] != group_id
        for source_id, group_id in buffer_source_groups.items()
    ):
        raise ValueError("Workspace source group ownership does not match")
    if bound.binding_signature_sha256 != _canonical_sha256(
        _binding_signature_payload(bound)
    ):
        raise ValueError("Workspace source/buffer map binding signature does not match")
    return topology, source_group_by_id | {
        f"{analysis_id}::buffer:{group_id}": group_id
        for analysis_id, group_ids in topology.items()
        for group_id in group_ids
    }


def bind_workspace_source_buffer_map(
    bundle: WorkspaceExecutionBundle,
) -> BoundWorkspaceSourceBufferMap:
    """Strictly validate once, then freeze the compact map-toggle boundary."""

    if not isinstance(bundle, WorkspaceExecutionBundle):
        raise TypeError("Workspace source/buffer binding requires an execution bundle")
    validate_workspace_execution_bundle(bundle)

    analysis_ids = tuple(
        _exact_text(binding.request.analysis_id, "workspace execution analysis id")
        for binding in bundle.bindings
    )
    adapter = bundle.app_adapter
    groups_by_analysis, group_by_layer_id = _analysis_group_topology(
        adapter,
        analysis_ids,
    )
    layers: list[BoundWorkspaceSourceBufferLayer] = []
    for layer in adapter.map_layers:
        if layer.role not in _DISPLAY_ROLES:
            continue
        group_id = group_by_layer_id.get(layer.layer_id)
        if group_id is None:
            raise ValueError("Workspace map layer has no canonical group")
        layers.append(
            BoundWorkspaceSourceBufferLayer(
                layer_id=layer.layer_id,
                analysis_id=layer.analysis_id,
                source_layer_id=layer.source_layer_id,
                group_id=group_id,
                role=layer.role,
                source_layer_ids=layer.source_layer_ids,
                signed_metadata_json=_signed_layer_metadata_json(layer),
                layer_signature_sha256=layer.layer_signature_sha256,
                renderer_payload_json=layer.renderer_payload_json,
                renderer_payload_sha256=layer.renderer_payload_sha256,
            )
        )

    bound = BoundWorkspaceSourceBufferMap(
        schema_version=WORKSPACE_SOURCE_BUFFER_MAP_SCHEMA_VERSION,
        execution_signature_sha256=bundle.execution_signature_sha256,
        adapter_signature_sha256=adapter.adapter_signature_sha256,
        analysis_ids=analysis_ids,
        group_topology=tuple(
            (analysis_id, groups_by_analysis[analysis_id])
            for analysis_id in analysis_ids
        ),
        layers=tuple(layers),
        binding_signature_sha256="0" * 64,
    )
    bound = replace(
        bound,
        binding_signature_sha256=_canonical_sha256(
            _binding_signature_payload(bound)
        ),
    )
    _validate_bound_source_buffer_map(bound)
    return bound


def _verified_renderer_dict(
    layer: BoundWorkspaceSourceBufferLayer,
) -> dict[str, Any]:
    try:
        value, integrity = _decode_renderer_payload_json(layer.renderer_payload_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Workspace selected renderer payload is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("Workspace selected renderer payload is not canonical")
    if integrity.payload_sha256 != layer.renderer_payload_sha256:
        raise ValueError("Workspace selected renderer payload digest does not match")
    if (
        value.get("workspace_layer_id") != layer.layer_id
        or value.get("workspace_source_layer_id") != layer.source_layer_id
        or value.get("workspace_role") != layer.role
        or not isinstance(value.get("default_visible"), bool)
    ):
        raise ValueError("Workspace selected renderer payload escaped its binding")
    expected_role_id = value.get(
        "source_layer_id" if layer.role == "source" else "buffer_layer_id"
    )
    if expected_role_id != layer.layer_id:
        raise ValueError("Workspace selected renderer role identity does not match")
    return value


def select_workspace_source_buffer_layers(
    bound: BoundWorkspaceSourceBufferMap,
    visibility: tuple[WorkspaceMapAnalysisVisibility, ...],
) -> tuple[dict[str, Any], ...]:
    """Select signed renderer payloads without revisiting the execution bundle."""

    topology, group_by_layer_id = _validate_bound_source_buffer_map(bound)
    if not isinstance(visibility, tuple):
        raise TypeError("Workspace map visibility must be an immutable tuple")

    selected_by_analysis: dict[str, dict[str, set[str]]] = {}
    for item in visibility:
        if not isinstance(item, WorkspaceMapAnalysisVisibility):
            raise TypeError("Workspace map visibility item has an invalid type")
        analysis_id = _exact_text(
            item.analysis_id,
            "workspace map visibility analysis id",
        )
        if analysis_id in selected_by_analysis:
            raise ValueError("Workspace map visibility duplicates an analysis")
        source_group_ids = _exact_ids(
            item.source_group_ids,
            f"{analysis_id} source group ids",
        )
        buffer_group_ids = _exact_ids(
            item.buffer_group_ids,
            f"{analysis_id} buffer group ids",
        )
        available = set(topology.get(analysis_id, ()))
        stale = (set(source_group_ids) | set(buffer_group_ids)) - available
        if analysis_id not in topology or stale:
            raise ValueError(
                "Workspace map visibility references an unknown analysis or "
                f"stale group: {analysis_id!r}/{sorted(stale)}"
            )
        selected_by_analysis[analysis_id] = {
            "source": set(source_group_ids),
            "buffer": set(buffer_group_ids),
        }

    if set(selected_by_analysis) != set(bound.analysis_ids):
        raise ValueError(
            "Workspace map visibility must explicitly cover every analysis"
        )

    selected_layers: list[dict[str, Any]] = []
    for layer in bound.layers:
        group_id = group_by_layer_id[layer.layer_id]
        if group_id not in selected_by_analysis[layer.analysis_id][layer.role]:
            continue
        renderer = _verified_renderer_dict(layer)
        selected_layers.append({**renderer, "default_visible": True})
    return tuple(selected_layers)


__all__ = [
    "WORKSPACE_SOURCE_BUFFER_MAP_SCHEMA_VERSION",
    "BoundWorkspaceSourceBufferLayer",
    "BoundWorkspaceSourceBufferMap",
    "WorkspaceMapAnalysisVisibility",
    "bind_workspace_source_buffer_map",
    "normalize_workspace_map_group_visibility",
    "select_workspace_source_buffer_layers",
]
