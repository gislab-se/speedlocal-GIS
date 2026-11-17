"""Exact compiled-policy input through the existing regional JSONB boundary.

No compiler, source resolver or analysis algorithm runs in this decoder. The
import sequence must first compile and validate a policy against current GIS
inputs, then pin that artifact in the repository manifest and context revision.
"""
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Mapping

from .combined_runtime import CombinedResultPolicyPackage, _load_combined_result_policy_package
from .postgis_context_inputs import (
    ContextDataset, RegionalInputScope, _keys, _sha, _validate_support_ids,
    validate_current_analysis_scope,
)
from .postgis_runtime import canonical_json


def _validated_package(scope: RegionalInputScope, *, analyses, support_cell_ids: tuple[str, ...],
        manifest: Mapping[str, Any], manifest_reference: str, manifest_path: Path,
        allocation_payload: bytes) -> CombinedResultPolicyPackage:
    validate_current_analysis_scope(scope, analyses)
    _validate_support_ids(scope, support_cell_ids)
    package = _load_combined_result_policy_package(manifest, region_id=scope.region_id,
        manifest_reference=manifest_reference, manifest_path=manifest_path,
        allocation_payload=allocation_payload)
    policy = package.policy
    if policy.finalization_resolution != scope.support_domain.resolution:
        raise ValueError('Combined policy resolution differs from current technology support')
    expected = set(support_cell_ids)
    if (set(policy.technology_order) != {'wind', 'solar'} or
            any({row.cell_id for row in policy.base_scores if row.technology_id == technology}
                != expected for technology in policy.technology_order)):
        raise ValueError('Combined policy scores do not cover the current technology support')
    return package


def build_combined_policy_dataset(scope: RegionalInputScope, *, analyses,
        support_cell_ids: tuple[str, ...], manifest: Mapping[str, Any],
        manifest_reference: str, manifest_path: Path, allocation_payload: bytes) -> ContextDataset:
    package = _validated_package(scope, analyses=analyses, support_cell_ids=support_cell_ids,
        manifest=manifest, manifest_reference=manifest_reference, manifest_path=manifest_path,
        allocation_payload=allocation_payload)
    payload = canonical_json({'schema_version': '1.0', 'scope': asdict(scope),
        'manifest_sha256': _sha(manifest),
        'allocation_policy_utf8': allocation_payload.decode('utf-8')})
    return ContextDataset('combined_policy', package.contract_signature_sha256,
        _sha(manifest['allocation_policy_artifact']),
        (('combined_policy', package.artifact_sha256),), payload)


def decode_combined_policy_dataset(dataset: ContextDataset, scope: RegionalInputScope, *,
        analyses, support_cell_ids: tuple[str, ...], manifest: Mapping[str, Any],
        manifest_reference: str, manifest_path: Path) -> CombinedResultPolicyPackage:
    raw = _keys(json.loads(dataset.payload_json),
        {'schema_version', 'scope', 'manifest_sha256', 'allocation_policy_utf8'})
    if (raw['schema_version'] != '1.0' or
            canonical_json(raw['scope']) != canonical_json(asdict(scope)) or
            raw['manifest_sha256'] != _sha(manifest) or
            not isinstance(raw['allocation_policy_utf8'], str)):
        raise ValueError('Combined policy input has a stale scope or current manifest')
    source_bytes = raw['allocation_policy_utf8'].encode('utf-8')
    rebuilt = build_combined_policy_dataset(scope, analyses=analyses,
        support_cell_ids=support_cell_ids, manifest=manifest,
        manifest_reference=manifest_reference, manifest_path=manifest_path,
        allocation_payload=source_bytes)
    if rebuilt != dataset:
        raise ValueError('Combined policy input or source descriptor drifted')
    return _validated_package(scope, analyses=analyses, support_cell_ids=support_cell_ids,
        manifest=manifest, manifest_reference=manifest_reference, manifest_path=manifest_path,
        allocation_payload=source_bytes)
