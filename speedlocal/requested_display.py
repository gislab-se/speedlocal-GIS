"""Validated source/buffer display roles without a complete presentation graph.

The independent binding identifies the complete authorized request and current
runtime. It does not claim the signature of an unbuilt full presentation.
"""
from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import sys
from threading import RLock
import time
from typing import Callable
from .catalogs import load_analysis
from .workspace_request import authorize_catalog_workspace_analysis_request
from .workspace_area import workspace_analysis_request_signature
from .workspace_view import _load_source_view
from .workspace_buffer import build_catalog_workspace_buffer_preview_request, derive_catalog_workspace_buffer_preview, validate_workspace_buffer_preview_result, validate_workspace_buffer_preview_result_from_contract
from .workspace_presentation import WorkspacePresentationLayerSpec, _preview_geometry_family
from .workspace_app_adapter import _feature_collection, _renderer_layer_payload
TRACE_KEYS = frozenset({'workspace_presentation_signature_sha256', 'workspace_display_binding_signature_sha256'})

def canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))

def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()

@dataclass(frozen=True)
class RequestedDisplayLayer:
    binding_json: str
    binding_sha256: str
    renderer_json: str
    renderer_sha256: str

def build_requested_display_layer(request, group_id, role, source_id, runtime_token, prepared=None):
    if role not in ('source', 'buffer'):
        raise ValueError('Only source/buffer display roles are supported')
    if type(runtime_token) is not str or len(runtime_token) != 64 or any((c not in '0123456789abcdef' for c in runtime_token)):
        raise ValueError('Display requires the current runtime identity')
    authorize_catalog_workspace_analysis_request(request)
    contract = load_analysis(request.region_id, request.analysis_id)
    groups = tuple((group for group in request.groups if group.group_id == group_id))
    if len(groups) != 1:
        raise ValueError('Display group is not present in the applied request')
    group = groups[0]
    common = dict(domain_id=None, geometry_mode='embedded', geometry_reference_layer_id=None, geometry_unavailable_reason=None, result_id=None, cell_ids_sha256=None)
    if role == 'source':
        if source_id not in group.layer_ids or prepared is not None:
            raise ValueError('Source display escaped its declared group')
        source = _load_source_view(contract, source_id)
        if source.group_id != group_id:
            raise ValueError('Source group ownership changed')
        spec = WorkspacePresentationLayerSpec(
            layer_id='source:' + source_id,
            role=role,
            label=source.label,
            geometry_family=source.geometry_family,
            processing_adapter=source.processing_adapter,
            result_semantics=None,
            feature_collection_json=source.feature_collection_json,
            source_layer_ids=(),
            preview_result_signature_sha256=None,
            source_sha256=source.source_sha256,
            feature_count=source.display_feature_count,
            operation=None,
            threshold_m=None,
            color=source.source_color,
            point_radius=source.point_radius,
            quality_flag=source.quality_flag,
            **common,
        )
        order = 1 + request.selected_layer_ids.index(source_id)
    else:
        if source_id is not None or prepared is None:
            raise ValueError('Buffer display requires its exact prepared group')
        buffer_request = build_catalog_workspace_buffer_preview_request(request, group_id)
        preview = derive_catalog_workspace_buffer_preview(buffer_request, prepared, runtime_token)
        validate_workspace_buffer_preview_result(preview)
        validate_workspace_buffer_preview_result_from_contract(contract, preview, native_crs=preview.native_crs)
        if preview.request.applied_request != request or preview.layer_ids != group.layer_ids or preview.request.applied_request_signature_sha256 != workspace_analysis_request_signature(request):
            raise ValueError('Buffer display escaped the complete applied request')
        semantics = {'distance_exclusion': 'blocked_means_excluded', 'hard_exclusion': 'blocked_means_excluded', 'proximity_feasibility': 'blocked_means_outside_required_proximity'}[preview.operation]
        ui_group = contract.ui.groups.get(group_id) if contract.ui is not None else None
        label = ui_group.label if ui_group is not None else group_id
        spec = WorkspacePresentationLayerSpec(
            layer_id='buffer:' + group_id,
            role=role,
            label=label + ' · buffert',
            geometry_family=_preview_geometry_family(preview.geometry_type),
            processing_adapter=None,
            result_semantics=semantics,
            feature_collection_json=preview.feature_collection_json,
            source_layer_ids=tuple(('source:' + value for value in group.layer_ids)),
            preview_result_signature_sha256=preview.result_signature_sha256,
            source_sha256=preview.feature_collection_sha256,
            feature_count=preview.feature_count,
            operation=preview.operation,
            threshold_m=preview.buffer_m,
            color=None,
            point_radius=None,
            quality_flag=None,
            **common,
        )
        order = 1 + len(request.selected_layer_ids) + 2 * tuple((g.group_id for g in request.groups)).index(group_id)
    collection = _feature_collection(spec.feature_collection_json, 'Requested display geometry')
    if len(collection['features']) != spec.feature_count:
        raise ValueError('Display geometry count changed after validation')
    output_id = request.analysis_id + '::' + spec.layer_id
    renderer = _renderer_layer_payload(
        output_layer_id=output_id,
        analysis_id=request.analysis_id,
        layer=spec,
        domain_key=None,
        output_reference_id=None,
        output_result_id=None,
        presentation_signature=None,
        feature_collection=collection,
        result=None,
        result_count_for_domain=0,
        area_result_id=None,
        order=order,
    )
    renderer['default_visible'] = True
    binding = {'schema': 'requested-display-1', 'request': request.as_dict(), 'runtime_token': runtime_token, 'group_id': group_id, 'role': role, 'source_id': source_id, 'layer_id': output_id, 'geometry_sha256': digest(collection), 'feature_count': spec.feature_count, 'source_sha256': spec.source_sha256, 'preview_signature': spec.preview_result_signature_sha256, 'renderer_content_sha256': digest({k: v for k, v in renderer.items() if k not in TRACE_KEYS})}
    binding_json = canonical(binding)
    binding_sha = hashlib.sha256(binding_json.encode('utf-8')).hexdigest()
    renderer['workspace_display_binding_signature_sha256'] = binding_sha
    renderer_json = canonical(renderer)
    return RequestedDisplayLayer(binding_json, binding_sha, renderer_json, hashlib.sha256(renderer_json.encode('utf-8')).hexdigest())

def decode_requested_display_layer(value, request, group_id, role, source_id, runtime_token):
    if type(value) is not RequestedDisplayLayer:
        raise TypeError('Display boundary requires its immutable typed layer')
    if hashlib.sha256(value.binding_json.encode('utf-8')).hexdigest() != value.binding_sha256:
        raise ValueError('Display binding content changed')
    if hashlib.sha256(value.renderer_json.encode('utf-8')).hexdigest() != value.renderer_sha256:
        raise ValueError('Display renderer content changed')
    binding = json.loads(value.binding_json)
    renderer = json.loads(value.renderer_json)
    if canonical(binding) != value.binding_json or canonical(renderer) != value.renderer_json:
        raise ValueError('Display boundary is not canonical')
    if binding.get('schema') != 'requested-display-1' or binding.get('request') != request.as_dict() or binding.get('runtime_token') != runtime_token or (binding.get('group_id') != group_id) or (binding.get('role') != role) or (binding.get('source_id') != source_id):
        raise ValueError('Display boundary escaped current region, scope, request or runtime')
    if renderer.get('workspace_display_binding_signature_sha256') != value.binding_sha256 or renderer.get('workspace_presentation_signature_sha256') is not None or renderer.get('workspace_layer_id') != binding['layer_id'] or (renderer.get('workspace_role') != role) or (digest({k: v for k, v in renderer.items() if k not in TRACE_KEYS}) != binding['renderer_content_sha256']) or (digest(renderer['feature_collection']) != binding['geometry_sha256']) or (len(renderer['feature_collection']['features']) != binding['feature_count']):
        raise ValueError('Display payload does not match its independent binding')
    return renderer

class RequestedDisplayCache:
    """Non-sliding TTL and byte/entry bounds for immutable display capsules.

    Validation/authorization remains outside lookup. No mutable renderer or
    connection is retained. Oversized entries serve their caller without being
    retained; concurrent completions cannot repopulate a cleared cache.
    """

    def __init__(self, *, max_entries=32, max_bytes=32 * 1024 * 1024, ttl=300, clock=time.monotonic):
        self.max_entries, self.max_bytes, self.ttl = (max_entries, max_bytes, ttl)
        self.clock = clock
        self._entries = OrderedDict()
        self._bytes = 0
        self._generation = 0
        self._lock = RLock()

    def clear(self):
        with self._lock:
            self._entries.clear()
            self._bytes = 0
            self._generation += 1

    def _prune(self, now):
        for key, (expires, _, charge) in tuple(self._entries.items()):
            if expires <= now:
                del self._entries[key]
                self._bytes -= charge

    def get_or_build(self, key: tuple, factory: Callable[[], RequestedDisplayLayer]):
        with self._lock:
            self._prune(self.clock())
            previous = self._entries.get(key)
            if previous is not None:
                self._entries.move_to_end(key)
                return previous[1]
            generation = self._generation
        value = factory()
        if type(value) is not RequestedDisplayLayer:
            raise TypeError('Display cache accepts immutable typed capsules only')
        charge = sys.getsizeof(key) + sum((sys.getsizeof(v) for v in key)) + sys.getsizeof(value) + sum((sys.getsizeof(v) for v in (value.binding_json, value.binding_sha256, value.renderer_json, value.renderer_sha256))) + sys.getsizeof((0.0, value, 0))
        with self._lock:
            now = self.clock()
            self._prune(now)
            if generation != self._generation or charge >= self.max_bytes:
                return value
            previous = self._entries.get(key)
            if previous is not None:
                return previous[1]
            self._entries[key] = (now + self.ttl, value, charge)
            self._bytes += charge
            while self._entries and (len(self._entries) > self.max_entries or self._bytes + sys.getsizeof(self._entries) > self.max_bytes):
                _, (_, _, removed) = self._entries.popitem(last=False)
                self._bytes -= removed
        return value
requested_display_cache = RequestedDisplayCache()
