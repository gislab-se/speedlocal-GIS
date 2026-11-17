"""Current regional input declarations and bounded immutable PostGIS reads."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from threading import RLock
import time
from typing import Any

from ._input_refresh_cache import cache_input_windows
from .catalogs import load_analysis, load_region
from .landscape import landscape_contract_signature, load_landscape_contract
from .paths import repo_root
from .postgis_context_inputs import (
    ContextRuntimeManifest, RegionalContextReadResult, parse_context_runtime_manifest,
    read_regional_context, required_context_dataset_kinds,
    validate_current_analysis_scope,
)
from .postgis_runtime import canonical_json
from .region_profile import load_region_profile, profile_path
from .scenarios import load_catalog_scenario_contract, scenario_contract_signature
from .social_acceptance import (
    load_catalog_social_acceptance_contract, social_acceptance_contract_signature,
)
from .sources import _current_postgis_operation, _postgis_database_url
from .workspace_request import analysis_contract_signature


@dataclass(frozen=True)
class CatalogContextDeclarations:
    manifest: ContextRuntimeManifest
    fingerprint: str
    analyses: tuple
    scenario_contract: Any
    social_contract: Any
    landscape_contract: Any
    combined_manifest: dict | None
    combined_manifest_reference: str | None
    combined_manifest_path: Path | None

    def reader_arguments(self) -> dict:
        return {'expected_scope': self.manifest.scope, 'analyses': self.analyses,
            'scenario_contract': self.scenario_contract, 'social_contract': self.social_contract,
            'combined_policy_manifest': self.combined_manifest,
            'combined_policy_manifest_reference': self.combined_manifest_reference,
            'combined_policy_manifest_path': self.combined_manifest_path,
            'landscape_contract': self.landscape_contract}


def catalog_context_runtime_declared(region_id: str) -> bool:
    return 'context_runtime_manifest' in load_region(region_id)


def _repo_document(reference: str) -> tuple[Path, bytes]:
    if not isinstance(reference, str) or not reference or reference.strip() != reference:
        raise ValueError('Regional context manifest reference must be exact')
    root = repo_root().resolve()
    path = (root / reference).resolve()
    if root not in path.parents:
        raise ValueError('Regional context manifest escapes the repository')
    return path, path.read_bytes()


def load_catalog_context_declarations(region_id: str, *,
        context_manifest_payload: bytes | None = None) -> CatalogContextDeclarations:
    region = load_region(region_id)
    reference = region.get('context_runtime_manifest')
    if context_manifest_payload is None:
        if reference != f'regions/{region_id}/context-runtime.json':
            raise ValueError('Regional context must declare its canonical generated binding')
        _, binding_bytes = _repo_document(reference)
    else:
        if not isinstance(context_manifest_payload, bytes):
            raise TypeError('Prepared context manifest must be immutable bytes')
        binding_bytes = context_manifest_payload
    manifest = parse_context_runtime_manifest(binding_bytes)
    profile = load_region_profile(repo_root(), region_id)
    if (manifest.binding.region_id != region_id or
            manifest.binding.database_schema != profile.database_schema or
            manifest.connection_alias != profile.connection):
        raise ValueError('Regional context binding differs from the current profile')
    analyses = tuple(load_analysis(region_id, key) for key in ('solar', 'wind'))
    validate_current_analysis_scope(manifest.scope, analyses)
    # The binding is checked against current declarations here. The SQL reader
    # independently compares the full support identity/IDs with the parent GIS
    # revision in its read-only repeatable-read transaction.
    for analysis in analyses:
        if analysis.area_result is None:
            raise ValueError('Regional context requires the current eligible support')
        surface = analysis.eligible_surfaces[analysis.area_result.eligible_surface_id]
        support = manifest.scope.support_domain
        if (support.domain_id, support.resolution, support.source_sha256, support.cell_count) != (
                surface.support_domain_id, surface.resolution, surface.sha256,
                surface.expected_cell_count):
            raise ValueError('Regional context support differs from the current analysis')
        if any(layer.source.postgis_reference.connection_alias != profile.connection
               for layer in analysis.layers.values()):
            raise ValueError('Regional context and analysis use different connections')
    scenario = load_catalog_scenario_contract(region_id)
    social = load_catalog_social_acceptance_contract(region_id)
    landscape = load_landscape_contract(region_id) if 'landscape_manifest' in region else None
    combined_reference = region.get('combined_result_manifest')
    combined_path, combined_bytes = _repo_document(combined_reference) if combined_reference is not None else (None, None)
    combined = json.loads(combined_bytes) if combined_bytes is not None else None
    required = required_context_dataset_kinds(manifest.scope, analyses,
        combined_policy_manifest=combined, landscape_contract=landscape)
    if manifest.required_datasets != required:
        raise ValueError('Regional context dataset set differs from current capabilities')
    identity = {'binding_sha256': hashlib.sha256(binding_bytes).hexdigest(),
        'profile_sha256': hashlib.sha256(profile_path(repo_root(), region_id).read_bytes()).hexdigest(),
        'analyses': [analysis_contract_signature(value) for value in analyses],
        'scenario': scenario_contract_signature(scenario),
        'social_acceptance': social_acceptance_contract_signature(social),
        'landscape': landscape_contract_signature(landscape) if landscape else None,
        'combined_manifest_sha256': hashlib.sha256(combined_bytes).hexdigest() if combined_bytes else None}
    fingerprint = hashlib.sha256(canonical_json(identity).encode('utf-8')).hexdigest()
    return CatalogContextDeclarations(manifest, fingerprint, analyses, scenario, social,
        landscape, combined, combined_reference, combined_path)


def current_regional_context_arguments(region_id: str, *,
        context_manifest_payload: bytes | None = None) -> dict:
    """Read current contracts without DB access, optionally for an explicit import.

    The preparer supplies its freshly generated context binding bytes before
    that binding is installed. Current GIS pins and regional contracts are
    still the repository authority; this cannot substitute candidate analyses.
    """
    return load_catalog_context_declarations(region_id,
        context_manifest_payload=context_manifest_payload).reader_arguments()


_context_cache_generation = 0
_context_cache_lock = RLock()


@cache_input_windows(window_index=2)
def _cached_context_inputs(region_id: str, fingerprint: str, window: int,
        generation: int, connection_identity: str) -> RegionalContextReadResult:
    # Generation remains in the input identity. Clearing also prevents
    # older in-flight reads from restoring cache-owned objects.
    del window, generation
    declarations = load_catalog_context_declarations(region_id)
    if declarations.fingerprint != fingerprint:
        raise ValueError('Regional context declarations changed during input acquisition')
    database_url = _postgis_database_url(declarations.manifest.connection_alias)
    if hashlib.sha256(database_url.encode('utf-8')).hexdigest() != connection_identity:
        raise ValueError('Regional context connection changed during input acquisition')
    return read_regional_context(database_url,
        declarations.manifest.binding, **declarations.reader_arguments())


def load_catalog_context_inputs(region_id: str) -> RegionalContextReadResult:
    declarations = load_catalog_context_declarations(region_id)
    database_url = _postgis_database_url(declarations.manifest.connection_alias)
    operation = _current_postgis_operation()
    with _context_cache_lock:
        generation = _context_cache_generation
        if operation is not None:
            previous = operation.context_snapshots.get(region_id)
            if previous is not None and previous[0] != generation:
                del operation.context_snapshots[region_id]
                previous = None
            if previous is not None:
                _, previous_url, previous_fingerprint, snapshot = previous
                if previous_url != database_url or previous_fingerprint != declarations.fingerprint:
                    raise ValueError('Regional context binding changed during the current operation')
                return snapshot
    snapshot = _cached_context_inputs(region_id, declarations.fingerprint,
        int(time.monotonic() // 30), generation,
        hashlib.sha256(database_url.encode('utf-8')).hexdigest())
    with _context_cache_lock:
        if generation != _context_cache_generation:
            raise ValueError('Regional context cache invalidated during input acquisition')
        if operation is not None:
            operation.context_snapshots[region_id] = (
                generation, database_url, declarations.fingerprint, snapshot)
    return snapshot


def clear_context_runtime_cache() -> None:
    global _context_cache_generation
    with _context_cache_lock:
        _context_cache_generation += 1
        _cached_context_inputs.cache_clear()
        from .postgis_context_payloads import clear_context_payload_cache
        clear_context_payload_cache()
        from .postgis_context_cache import clear_validated_context_cache
        clear_validated_context_cache()
