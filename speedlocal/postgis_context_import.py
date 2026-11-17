"""Offline preparation and atomic import of the fixed regional context inputs.

This module never activates a region or overwrites an immutable revision.
Source-file reads in the combined executor are offline import evidence only.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from .postgis_context_inputs import (
    ContextRuntimeManifest, RegionalContextInputs, RegionalContextReadResult,
    SupportDomainBinding, _keys, _read_regional_context_rows,
    build_context_runtime_manifest, decode_regional_context_inputs,
    parse_context_runtime_manifest, read_regional_context,
)
from .postgis_runtime import (
    RoadRuntimeInputs, RuntimeBinding, _read_road_runtime_rows,
    canonical_json, read_road_runtime,
)


def _captured_json(path: Path, expected_sha256: str) -> dict:
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("Prepared context file differs from its declared checksum")
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Prepared context file must contain a JSON object")
    return parsed


def write_prepared_context_inputs(inputs: RegionalContextInputs, directory: Path, *,
        connection_alias: str) -> Path:
    """Write exact typed-preparer output to a new directory; no DB or activation."""
    if directory.exists():
        raise FileExistsError("Prepared context output directory must be new")
    manifest = build_context_runtime_manifest(inputs, connection_alias)
    directory.mkdir(parents=True)
    (directory / "datasets").mkdir()

    def write(relative: str, payload: dict) -> dict[str, str]:
        raw = (canonical_json(payload) + "\n").encode("utf-8")
        with (directory / relative).open("xb") as handle:
            handle.write(raw)
        return {"path": relative, "sha256": hashlib.sha256(raw).hexdigest()}

    metadata = write("metadata.json", inputs.metadata())
    datasets = [{"kind": item.kind, **write(f"datasets/{item.kind}.json", json.loads(item.payload_json))}
        for item in inputs.datasets]
    descriptor = {"schema_version": "1.0", "runtime_manifest": manifest,
        "metadata": metadata, "datasets": datasets}
    path = directory / "prepared-context.json"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(descriptor, ensure_ascii=False, indent=2) + "\n")
    return path


def read_prepared_context_descriptor(path: Path) -> tuple[ContextRuntimeManifest, dict, tuple[tuple[str, dict], ...]]:
    """Checksum and parse one captured descriptor; runtime meaning is checked next."""
    raw = json.loads(path.read_bytes())
    _keys(raw, {"schema_version", "runtime_manifest", "metadata", "datasets"})
    if raw["schema_version"] != "1.0":
        raise ValueError("Unsupported prepared context descriptor schema")
    manifest = parse_context_runtime_manifest(raw["runtime_manifest"])
    root = path.parent.resolve(strict=True)

    def read(reference: dict) -> dict:
        _keys(reference, {"path", "sha256"})
        relative = reference["path"]
        if (not isinstance(relative, str) or not relative or "\\" in relative
                or Path(relative).is_absolute() or any(part in {"", ".", ".."} for part in relative.split("/"))):
            raise ValueError("Prepared context asset must stay inside its descriptor directory")
        target = (root / relative).resolve(strict=True)
        if target == root or not target.is_relative_to(root):
            raise ValueError("Prepared context asset escapes its descriptor directory")
        return _captured_json(target, reference["sha256"])

    metadata = read(raw["metadata"])
    if not isinstance(raw["datasets"], list):
        raise ValueError("Prepared context datasets must be an ordered array")
    rows = []
    for dataset in raw["datasets"]:
        _keys(dataset, {"kind", "path", "sha256"})
        rows.append((dataset["kind"], read({key: dataset[key] for key in ("path", "sha256")})))
    if tuple(kind for kind, _ in rows) != manifest.required_datasets:
        raise ValueError("Prepared context dataset set/order differs from its manifest")
    return manifest, metadata, tuple(rows)


def decode_prepared_context_inputs(metadata: dict, rows: tuple[tuple[str, dict], ...],
        binding: RuntimeBinding, *, parent_inputs: RoadRuntimeInputs, **current) -> RegionalContextReadResult:
    """Validate prepared data against an already verified complete GIS snapshot."""
    from .postgis_technical_inputs import StandardDomainBinding
    scope = current["expected_scope"]
    if parent_inputs.binding() != RuntimeBinding(scope.region_id, scope.region_id, scope.analysis_revision_sha256):
        raise ValueError("Prepared context does not bind the exact verified parent GIS input")
    domain = parent_inputs.domain(scope.support_domain.domain_id, scope.support_domain.resolution)
    if SupportDomainBinding.from_domain(domain) != scope.support_domain:
        raise ValueError("Prepared context support differs from the verified parent domain")
    support_ids = tuple(cell.cell_id for cell in domain.cells)
    solar = next(analysis for analysis in current["analyses"] if analysis.id == "solar")
    distributed = solar.distributed_generation
    has_roof = distributed is not None and distributed.rooftop_solar is not None
    has_landscape = current["landscape_contract"] is not None
    standard, ids, landscape_domain = None, (), None
    if has_roof or has_landscape:
        candidates = [item for item in parent_inputs.domains if item.role == "standard_analysis"
            and item.resolution == solar.analysis_domain.resolution]
        if len(candidates) != 1:
            raise ValueError("Prepared context needs one canonical standard domain")
        standard = StandardDomainBinding.from_domain(candidates[0])
        ids = tuple(cell.cell_id for cell in candidates[0].cells)
        if has_landscape:
            landscape_domain = candidates[0]
    return decode_regional_context_inputs(metadata, rows, binding,
        support_cell_ids=support_ids, standard_domain=standard, standard_cell_ids=ids,
        landscape_domain=landscape_domain, **current)


def verify_current_combined_recompilation(result: RegionalContextReadResult, *, analyses) -> dict | None:
    """Re-execute the existing model; never re-stamp old compiled scores."""
    if result.combined_policy is None:
        return None
    from .catalogs import load_analysis
    from .combined_result_compiler import ResolvedCombinedScoreSurface, _SCORE_EXECUTORS
    from .paths import resolve_source_path
    from .workspace_request import analysis_contract_signature
    package = result.combined_policy
    surfaces = {}
    for analysis in analyses:
        actual = load_analysis(result.inputs.scope.region_id, analysis.id)
        if analysis_contract_signature(actual) != analysis_contract_signature(analysis):
            raise ValueError("Current combined executor would consume another analysis contract")
        if analysis.area_result is None:
            raise ValueError("Combined import requires the current exact-area contract")
        eligible = analysis.eligible_surfaces[analysis.area_result.eligible_surface_id]
        surfaces[analysis.id] = ResolvedCombinedScoreSurface(analysis.id, eligible.provider,
            eligible.path, resolve_source_path(eligible.provider, eligible.path),
            eligible.sha256, eligible.id_field, eligible.resolution)
    executor = _SCORE_EXECUTORS.get(package.contract.score_input.executor_id)
    if executor is None:
        raise ValueError("Combined import requires the existing registered score executor")
    scores, priorities = executor(package.contract, surfaces, result.inputs.scope.region_id)
    if scores != package.policy.base_scores or priorities != package.policy.priority_values:
        raise ValueError("Compiled combined policy differs from current GIS/support recomputation")
    return {"executor_id": package.contract.score_input.executor_id,
        "scope": json.loads(canonical_json(asdict(result.inputs.scope))),
        "allocation_policy_artifact_sha256": package.artifact_sha256,
        "policy_signature_sha256": package.policy.policy_signature_sha256,
        "base_score_count": len(scores), "priority_value_count": len(priorities),
        "exact_current_executor_output": True}


def check_regional_context_inputs(database_url: str, inputs: RegionalContextInputs, **current) -> RegionalContextReadResult:
    """Read-only dry-run against the actual pinned parent; no context pin needed."""
    scope = current["expected_scope"]
    parent = read_road_runtime(database_url,
        RuntimeBinding(scope.region_id, scope.region_id, scope.analysis_revision_sha256))
    return decode_prepared_context_inputs(inputs.metadata(),
        tuple((item.kind, json.loads(item.payload_json)) for item in inputs.datasets),
        inputs.binding(), parent_inputs=parent, **current)


def import_regional_context_inputs(database_url: str, inputs: RegionalContextInputs, **current) -> dict[str, Any]:
    """Insert one full immutable region revision and prove both DB roundtrips."""
    if not isinstance(database_url, str) or not database_url.strip():
        raise ValueError("A private database connection is required")
    checked = check_regional_context_inputs(database_url, inputs, **current)
    if checked.inputs != inputs:
        raise ValueError("Prepared context normalization changed its immutable input identity")
    compilation = verify_current_combined_recompilation(checked, analyses=current["analyses"])
    binding, scope = inputs.binding(), inputs.scope
    import psycopg
    try:
        with psycopg.connect(database_url, connect_timeout=5, options="-c statement_timeout=60000") as connection:
            with connection.cursor() as cursor:
                cursor.execute("set transaction isolation level repeatable read")
                cursor.execute("select gate_state from meta.region_delivery_gates where region_id = %s and gate_id = 1", (scope.region_id,))
                if cursor.fetchone() != ("localhost_approved",):
                    raise ValueError("Context import requires the existing Gate 1 approval")
                cursor.execute("select 1 from meta.schema_migrations where migration_id = %s", ("013_regional_context_inputs",))
                if cursor.fetchone() is None:
                    raise ValueError("Migration 013 must precede regional context import")
                parent = _read_road_runtime_rows(cursor,
                    RuntimeBinding(scope.region_id, scope.region_id, scope.analysis_revision_sha256))
                repeated = decode_prepared_context_inputs(inputs.metadata(),
                    tuple((item.kind, json.loads(item.payload_json)) for item in inputs.datasets),
                    binding, parent_inputs=parent, **current)
                if repeated.inputs != checked.inputs:
                    raise ValueError("Prepared context changed before the atomic import")
                cursor.execute(sql.SQL("select 1 from {}.regional_context_revisions where revision_sha256 = %s").format(sql.Identifier(binding.database_schema)), (binding.revision_sha256,))
                present = cursor.fetchone() is not None
                if not present:
                    cursor.execute(sql.SQL("insert into {}.regional_context_revision_data (revision_sha256, region_id, analysis_revision_sha256, metadata) values (%s, %s, %s, %s)").format(sql.Identifier(binding.database_schema)),
                        (binding.revision_sha256, scope.region_id, scope.analysis_revision_sha256, Jsonb(inputs.metadata())))
                    cursor.executemany(sql.SQL("insert into {}.regional_context_dataset_data (revision_sha256, dataset_kind, payload) values (%s, %s, %s)").format(sql.Identifier(binding.database_schema)),
                        ((binding.revision_sha256, item.kind, Jsonb(json.loads(item.payload_json))) for item in inputs.datasets))
                # Same typed decoder in the write transaction; only this private
                # helper omits SHOW read_only. The public reader never does.
                if _read_regional_context_rows(cursor, binding, **current).inputs != inputs:
                    raise ValueError("Context JSONB roundtrip changed the prepared inputs")
        fresh = read_regional_context(database_url, binding, **current)
        if fresh.inputs != inputs:
            raise ValueError("Fresh read-only context roundtrip changed the imported inputs")
        return {"status": "already_present" if present else "imported",
            "binding": asdict(binding), "required_datasets": [item.kind for item in inputs.datasets],
            "transaction_roundtrip": True, "fresh_readonly_roundtrip": True,
            "combined_recompilation": compilation}
    except psycopg.Error:
        raise RuntimeError("PostGIS regional context import failed") from None
