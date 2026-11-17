"""Immutable, typed regional inputs bound to current GIS and repo contracts.

There is no source-file resolver, engine math, cache or activation here.
Support-observation metadata belongs to the existing GIS domain revision.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Mapping, TYPE_CHECKING

import h3
from psycopg import sql

from .postgis_runtime import DomainCell, DomainCellsInput, RuntimeBinding, canonical_json, canonical_wkb
from .contracts import AnalysisContract
if TYPE_CHECKING:
    from .postgis_technical_inputs import (
        StandardDomainBinding, TechnologyContextSourceSnapshot, RooftopPopulationSnapshot,
    )
    from .landscape import LandscapeContract
    from .postgis_landscape_inputs import LandscapeSourceSnapshot
    from .combined_runtime import CombinedResultPolicyPackage
from .scenarios import (
    SCENARIO_SNAPSHOT_SCHEMA_VERSION, ScenarioContract, ScenarioDataSnapshot,
    ScenarioEnergyObservation, ScenarioAreaFactor, scenario_contract_signature,
    scenario_data_snapshot, scenario_source_assets_signature,
    validate_scenario_snapshot_from_contract,
)
from .social_acceptance import (
    SOCIAL_ACCEPTANCE_SNAPSHOT_SCHEMA_VERSION, SocialAcceptanceContract,
    SocialAcceptanceSnapshot, SocialAcceptanceObservation,
    social_acceptance_contract_signature, social_acceptance_source_assets_signature,
)

FORMAT_VERSION = "regional-context-1"
DATASET_KINDS = (
    "combined_policy", "landscape", "rooftop_population", "scenario",
    "social_acceptance", "technology_context",
)
IMPLEMENTED_DATASET_KINDS = DATASET_KINDS


def _digest(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("Context input requires an exact SHA256 digest")
    return value


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[a-z][a-z0-9_]*", value) is None:
        raise ValueError("Context input identifier is invalid")
    return value


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _ids_sha(ids: tuple[str, ...]) -> str:
    return hashlib.sha256("".join(f"{item}\n" for item in ids).encode("ascii")).hexdigest()


def _keys(value: Any, expected: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("Context payload has missing or unsupported fields")
    return value


def _finite(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError("Context observation must be a finite number")
    return float(value)


@dataclass(frozen=True)
class SupportDomainBinding:
    domain_id: str
    resolution: int
    source_sha256: str
    cell_count: int
    cell_ids_sha256: str
    cells_sha256: str

    @classmethod
    def from_domain(cls, domain: DomainCellsInput) -> SupportDomainBinding:
        if domain.role != "technology_support":
            raise ValueError("Regional context use must name the technology support domain")
        return cls(domain.domain_id, domain.resolution, domain.source_sha256,
                   len(domain.cells), domain.cell_ids_sha256, domain.cells_sha256)


@dataclass(frozen=True)
class RegionalInputScope:
    region_id: str
    analysis_revision_sha256: str
    analysis_contract_signatures: tuple[tuple[str, str], ...]
    support_domain: SupportDomainBinding


def validate_scope(scope: RegionalInputScope) -> None:
    if not isinstance(scope, RegionalInputScope) or not isinstance(scope.support_domain, SupportDomainBinding):
        raise TypeError("Regional input scope has the wrong type")
    _identifier(scope.region_id)
    _digest(scope.analysis_revision_sha256)
    signatures = scope.analysis_contract_signatures
    if (not isinstance(signatures, tuple)
            or any(not isinstance(item, tuple) or len(item) != 2 for item in signatures)
            or tuple(item[0] for item in signatures) != ("solar", "wind")):
        raise ValueError("Scope must bind the exact ordered solar/wind contracts")
    for item in signatures:
        _digest(item[1])
    domain = scope.support_domain
    _identifier(domain.domain_id)
    if (isinstance(domain.resolution, bool) or not isinstance(domain.resolution, int)
            or not 0 <= domain.resolution <= 15 or isinstance(domain.cell_count, bool)
            or not isinstance(domain.cell_count, int) or domain.cell_count <= 0):
        raise ValueError("Support domain resolution/count is invalid")
    for value in (domain.source_sha256, domain.cell_ids_sha256, domain.cells_sha256):
        _digest(value)


def _validate_support_ids(scope: RegionalInputScope, cell_ids: tuple[str, ...]) -> None:
    domain = scope.support_domain
    if (not isinstance(cell_ids, tuple) or cell_ids != tuple(sorted(set(cell_ids)))
            or len(cell_ids) != domain.cell_count or _ids_sha(cell_ids) != domain.cell_ids_sha256
            or any(not h3.is_valid_cell(value) or h3.get_resolution(value) != domain.resolution for value in cell_ids)):
        raise ValueError("Support cell IDs drifted from the bound domain")


@dataclass(frozen=True)
class ContextDataset:
    kind: str
    semantic_contract_sha256: str
    source_assets_signature_sha256: str
    source_asset_sha256: tuple[tuple[str, str], ...]
    payload_json: str

    def descriptor(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "semantic_contract_sha256": self.semantic_contract_sha256,
            "source_assets_signature_sha256": self.source_assets_signature_sha256,
            "source_asset_sha256": [list(item) for item in self.source_asset_sha256],
            "payload_sha256": hashlib.sha256(self.payload_json.encode("utf-8")).hexdigest(),
        }


@dataclass(frozen=True)
class RegionalContextInputs:
    scope: RegionalInputScope
    datasets: tuple[ContextDataset, ...]

    def metadata(self) -> dict[str, Any]:
        # JSON normalization makes Python tuples and PostgreSQL JSON arrays agree.
        return json.loads(canonical_json({"format": FORMAT_VERSION, "scope": asdict(self.scope),
            "datasets": [item.descriptor() for item in self.datasets]}))

    @property
    def revision_sha256(self) -> str:
        return _sha(self.metadata())

    def binding(self) -> RuntimeBinding:
        return RuntimeBinding(self.scope.region_id, self.scope.region_id, self.revision_sha256)


@dataclass(frozen=True)
class ContextRuntimeManifest:
    connection_alias: str
    binding: RuntimeBinding
    scope: RegionalInputScope
    required_datasets: tuple[str, ...]


def parse_context_runtime_manifest(value: bytes | Mapping[str, Any]) -> ContextRuntimeManifest:
    """Parse only configuration evidence; the typed DB read proves its content."""
    raw = json.loads(value) if isinstance(value, bytes) else dict(value)
    _keys(raw, {"schema_version", "region_id", "connection_alias", "database_schema",
                "revision_sha256", "scope", "required_datasets"})
    if raw["schema_version"] != "1.0":
        raise ValueError("Unsupported regional context manifest schema")
    alias = raw["connection_alias"]
    if (not isinstance(alias, str) or re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", alias) is None):
        raise ValueError("Context manifest requires a declared connection alias, never credentials")
    bound = RuntimeBinding(raw["region_id"], raw["database_schema"], raw["revision_sha256"])
    scope_raw = _keys(raw["scope"], set(RegionalInputScope.__dataclass_fields__))
    domain_raw = _keys(scope_raw["support_domain"], set(SupportDomainBinding.__dataclass_fields__))
    signatures = scope_raw["analysis_contract_signatures"]
    if (not isinstance(signatures, list)
            or any(not isinstance(item, list) or len(item) != 2 for item in signatures)):
        raise ValueError("Context scope requires exact ordered analysis-signature pairs")
    scope = RegionalInputScope(scope_raw["region_id"], scope_raw["analysis_revision_sha256"],
        tuple(tuple(item) for item in signatures), SupportDomainBinding(**domain_raw))
    validate_scope(scope)
    if scope.region_id != bound.region_id:
        raise ValueError("Context manifest and scope identify different regions")
    kinds = raw["required_datasets"]
    if (not isinstance(kinds, list) or any(not isinstance(kind, str) for kind in kinds)
            or kinds != sorted(set(kinds)) or not kinds
            or set(kinds) - set(DATASET_KINDS)
            or not {"scenario", "social_acceptance", "technology_context"}.issubset(kinds)):
        raise ValueError("Context manifest has an unsupported or incomplete typed dataset set")
    return ContextRuntimeManifest(alias, bound, scope, tuple(kinds))


def build_context_runtime_manifest(inputs: RegionalContextInputs, connection_alias: str) -> dict[str, Any]:
    payload = {"schema_version": "1.0", "region_id": inputs.scope.region_id,
        "connection_alias": connection_alias, "database_schema": inputs.binding().database_schema,
        "revision_sha256": inputs.revision_sha256,
        "scope": json.loads(canonical_json(asdict(inputs.scope))),
        "required_datasets": [item.kind for item in inputs.datasets]}
    parse_context_runtime_manifest(payload)
    return payload


def _assets(contract) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((asset.role, asset.sha256) for asset in contract.source.assets.values()))


def _scenario_payload(contract: ScenarioContract, snapshot: ScenarioDataSnapshot) -> str:
    if contract.adapter_id == "capacity_area_xlsx_v1":
        from .capacity_scenarios import validate_capacity_snapshot
        validate_capacity_snapshot(contract, snapshot)
        return canonical_json(asdict(snapshot))
    if not isinstance(snapshot, ScenarioDataSnapshot) or snapshot.schema_version != SCENARIO_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("Unsupported scenario snapshot type or schema")
    if not isinstance(snapshot.energy_observations, tuple) or not isinstance(snapshot.area_factors, tuple):
        raise ValueError("Scenario snapshot rows must be immutable")
    rebuilt = scenario_data_snapshot(source_assets_signature_sha256=snapshot.source_assets_signature_sha256,
        energy_observations=snapshot.energy_observations, area_factors=snapshot.area_factors)
    if canonical_json(asdict(rebuilt)) != canonical_json(asdict(snapshot)):
        raise ValueError("Scenario snapshot contains noncanonical values")
    validate_scenario_snapshot_from_contract(contract, rebuilt)
    return canonical_json(asdict(rebuilt))


def _social_payload(contract: SocialAcceptanceContract, snapshot: SocialAcceptanceSnapshot,
                    scope: RegionalInputScope, support_cell_ids: tuple[str, ...]) -> str:
    if (not isinstance(snapshot, SocialAcceptanceSnapshot)
            or snapshot.schema_version != SOCIAL_ACCEPTANCE_SNAPSHOT_SCHEMA_VERSION
            or snapshot.source_assets_signature_sha256 != social_acceptance_source_assets_signature(contract.source)
            or not isinstance(snapshot.observations, tuple)):
        raise ValueError("Social snapshot type/schema/source binding is invalid")
    coverage = contract.source.coverage
    ids = tuple(row.cell_id for row in snapshot.observations)
    if (ids != tuple(sorted(set(ids))) or len(ids) != coverage.source_hex_count
            or scope.support_domain.resolution != contract.source_resolution
            or coverage.target_support_hex_count != len(support_cell_ids)
            or set(ids) - set(support_cell_ids)
            or len(set(support_cell_ids) - set(ids)) != coverage.unassessed_support_hex_count):
        raise ValueError("Social observation coverage differs from the exact support domain")
    expected_scenarios = tuple(item.scenario_id for item in contract.scenarios)
    for row in snapshot.observations:
        if (not isinstance(row, SocialAcceptanceObservation) or not h3.is_valid_cell(row.cell_id)
                or h3.get_resolution(row.cell_id) != contract.source_resolution
                or isinstance(row.source_resolution, bool) or not isinstance(row.source_resolution, int)
                or row.source_resolution != contract.source_resolution
                or row.method_version != contract.source.method_id
                or not isinstance(row.data_status, str) or not row.data_status or row.data_status != row.data_status.strip()
                or not isinstance(row.scenario_values, tuple)
                or any(not isinstance(item, tuple) or len(item) != 2 for item in row.scenario_values)
                or tuple(item[0] for item in row.scenario_values) != expected_scenarios):
            raise ValueError("Social observation identity/method/scenarios drifted")
        for _scenario, value in row.scenario_values:
            number = _finite(value)
            if (not contract.value_minimum <= number <= contract.value_maximum
                    or not math.isclose(number, round(number, contract.max_decimals), rel_tol=0, abs_tol=1e-12)):
                raise ValueError("Social observation violates declared range/precision")
    return canonical_json(asdict(snapshot))


def _build_scenario_social_inputs(scope: RegionalInputScope, *, support_cell_ids: tuple[str, ...],
        scenario_contract: ScenarioContract, scenario_snapshot: ScenarioDataSnapshot,
        social_contract: SocialAcceptanceContract, social_snapshot: SocialAcceptanceSnapshot) -> RegionalContextInputs:
    validate_scope(scope)
    _validate_support_ids(scope, support_cell_ids)
    if scenario_contract.region_id != scope.region_id or social_contract.region_id != scope.region_id:
        raise ValueError("Context contracts belong to another region")
    return RegionalContextInputs(scope, (
        ContextDataset("scenario", scenario_contract_signature(scenario_contract),
            scenario_source_assets_signature(scenario_contract.source), _assets(scenario_contract),
            _scenario_payload(scenario_contract, scenario_snapshot)),
        ContextDataset("social_acceptance", social_acceptance_contract_signature(social_contract),
            social_acceptance_source_assets_signature(social_contract.source), _assets(social_contract),
            _social_payload(social_contract, social_snapshot, scope, support_cell_ids)),
    ))


def _decode_scenario(raw: dict) -> ScenarioDataSnapshot:
    if raw.get("schema_version") == "capacity-1.0":
        from .capacity_scenarios import decode_capacity_snapshot
        return decode_capacity_snapshot(raw)
    _keys(raw, {"schema_version", "source_assets_signature_sha256", "energy_observations", "area_factors"})
    if not isinstance(raw["energy_observations"], list) or not isinstance(raw["area_factors"], list):
        raise ValueError("Scenario payload rows must be arrays")
    energy = tuple(ScenarioEnergyObservation(**_keys(row,
        {"source_scenario", "planning_year", "technology_id", "value_twh"})) for row in raw["energy_observations"])
    factors = tuple(ScenarioAreaFactor(**_keys(row,
        {"area_demand_scenario", "technology_id", "km2_per_twh"})) for row in raw["area_factors"])
    return ScenarioDataSnapshot(raw["schema_version"], raw["source_assets_signature_sha256"], energy, factors)


def _decode_social(raw: dict) -> SocialAcceptanceSnapshot:
    _keys(raw, {"schema_version", "source_assets_signature_sha256", "observations"})
    if not isinstance(raw["observations"], list):
        raise ValueError("Social payload observations must be an array")
    rows = []
    for row in raw["observations"]:
        _keys(row, {"cell_id", "source_resolution", "data_status", "method_version", "scenario_values"})
        values = row["scenario_values"]
        if not isinstance(values, list) or any(not isinstance(value, list) or len(value) != 2 for value in values):
            raise ValueError("Social scenario values must be ordered pairs")
        rows.append(SocialAcceptanceObservation(**{**row, "scenario_values": tuple(tuple(value) for value in values)}))
    return SocialAcceptanceSnapshot(raw["schema_version"], raw["source_assets_signature_sha256"], tuple(rows))


@dataclass(frozen=True)
class RegionalContextReadResult:
    inputs: RegionalContextInputs
    scenario: ScenarioDataSnapshot
    social_acceptance: SocialAcceptanceSnapshot
    technology_context: TechnologyContextSourceSnapshot
    rooftop_population: RooftopPopulationSnapshot | None
    landscape: LandscapeSourceSnapshot | None = None
    combined_policy: CombinedResultPolicyPackage | None = None
    support_cell_ids: tuple[str, ...] = ()
    standard_cell_ids: tuple[str, ...] = ()


def validate_current_analysis_scope(scope: RegionalInputScope,
        analyses: tuple[AnalysisContract, ...]) -> dict[str, AnalysisContract]:
    """Validate current semantics and every source's immutable parent GIS pin."""
    from .postgis_technical_inputs import _current_analyses
    current = _current_analyses(scope, analyses)
    references = tuple(layer.source.postgis_reference
        for analysis in current.values() for layer in analysis.layers.values())
    if not references or any(reference is None or (
            reference.region_id, reference.database_schema, reference.revision_sha256
            ) != (scope.region_id, scope.region_id, scope.analysis_revision_sha256)
            for reference in references):
        raise ValueError("Current analysis sources do not bind the exact context parent GIS revision")
    return current


def required_context_dataset_kinds(scope: RegionalInputScope,
        analyses: tuple[AnalysisContract, ...], *,
        combined_policy_manifest: Mapping[str, Any] | None,
        landscape_contract: LandscapeContract | None) -> tuple[str, ...]:
    """The caller supplies actual current declarations, including explicit absence."""
    current = validate_current_analysis_scope(scope, analyses)
    if (combined_policy_manifest is not None and (
            not isinstance(combined_policy_manifest, Mapping)
            or combined_policy_manifest.get("region_id") != scope.region_id)):
        raise ValueError("Current combined-policy declaration belongs to another region")
    if landscape_contract is not None and landscape_contract.region_id != scope.region_id:
        raise ValueError("Current landscape declaration belongs to another region")
    distributed = current["solar"].distributed_generation
    has_rooftop = distributed is not None and distributed.rooftop_solar is not None
    return tuple(kind for kind in IMPLEMENTED_DATASET_KINDS
        if (kind != "rooftop_population" or has_rooftop)
        and (kind != "combined_policy" or combined_policy_manifest is not None)
        and (kind != "landscape" or landscape_contract is not None))


def _combined_declaration(manifest, reference, path) -> None:
    if manifest is None:
        if reference is not None or path is not None:
            raise ValueError("Absent combined policy cannot retain a manifest location")
    elif (not isinstance(reference, str) or not reference or reference != reference.strip()
            or not isinstance(path, Path)):
        raise ValueError("Declared combined policy needs its current repository manifest location")


def build_regional_context_inputs(scope: RegionalInputScope, *,
        analyses: tuple[AnalysisContract, ...], support_cell_ids: tuple[str, ...],
        scenario_contract: ScenarioContract, scenario_snapshot: ScenarioDataSnapshot,
        social_contract: SocialAcceptanceContract, social_snapshot: SocialAcceptanceSnapshot,
        technology_snapshot: TechnologyContextSourceSnapshot,
        combined_policy_manifest: Mapping[str, Any] | None,
        combined_policy_manifest_reference: str | None,
        combined_policy_manifest_path: Path | None,
        landscape_contract: LandscapeContract | None,
        standard_domain: StandardDomainBinding | None = None,
        standard_cell_ids: tuple[str, ...] = (),
        rooftop_snapshot: RooftopPopulationSnapshot | None = None,
        landscape_domain: DomainCellsInput | None = None,
        landscape_snapshot: LandscapeSourceSnapshot | None = None,
        combined_policy_payload: bytes | None = None) -> RegionalContextInputs:
    """Build exactly the typed datasets required by current capability declarations."""
    from .postgis_technical_inputs import build_technology_context_dataset, build_rooftop_population_dataset
    required = required_context_dataset_kinds(scope, analyses,
        combined_policy_manifest=combined_policy_manifest, landscape_contract=landscape_contract)
    _combined_declaration(combined_policy_manifest, combined_policy_manifest_reference, combined_policy_manifest_path)
    base = _build_scenario_social_inputs(scope, support_cell_ids=support_cell_ids,
        scenario_contract=scenario_contract, scenario_snapshot=scenario_snapshot,
        social_contract=social_contract, social_snapshot=social_snapshot)
    datasets = list(base.datasets)
    datasets.append(build_technology_context_dataset(scope, analyses=analyses,
        support_cell_ids=support_cell_ids, snapshot=technology_snapshot))
    population = build_rooftop_population_dataset(scope, analyses=analyses,
        standard_domain=standard_domain, standard_cell_ids=standard_cell_ids, snapshot=rooftop_snapshot)
    if population is not None:
        datasets.append(population)
    if "landscape" in required:
        from .postgis_landscape_inputs import build_landscape_dataset
        datasets.append(build_landscape_dataset(scope, contract=landscape_contract,
            analyses=analyses, standard_domain=landscape_domain, snapshot=landscape_snapshot))
    elif landscape_snapshot is not None or landscape_domain is not None:
        raise ValueError("Undeclared landscape cannot have a dataset or source domain")
    if "combined_policy" in required:
        from .postgis_combined_policy_inputs import build_combined_policy_dataset
        datasets.append(build_combined_policy_dataset(scope, analyses=analyses,
            support_cell_ids=support_cell_ids, manifest=combined_policy_manifest,
            manifest_reference=combined_policy_manifest_reference,
            manifest_path=combined_policy_manifest_path, allocation_payload=combined_policy_payload))
    elif combined_policy_payload is not None:
        raise ValueError("Undeclared combined policy cannot have a payload")
    ordered = tuple(sorted(datasets, key=lambda item: item.kind))
    if tuple(item.kind for item in ordered) != required:
        raise ValueError("Context builder does not match the current required dataset set")
    return RegionalContextInputs(scope, ordered)


def _dataset_from_row(kind: str, payload: dict, descriptor: dict) -> ContextDataset:
    """Validate transport evidence only; a concrete decoder still checks meaning."""
    _keys(descriptor, {"kind", "semantic_contract_sha256", "source_assets_signature_sha256",
                       "source_asset_sha256", "payload_sha256"})
    if descriptor["kind"] != kind or not isinstance(payload, dict):
        raise ValueError("Context payload and descriptor identities differ")
    for key in ("semantic_contract_sha256", "source_assets_signature_sha256", "payload_sha256"):
        _digest(descriptor[key])
    assets = descriptor["source_asset_sha256"]
    if (not isinstance(assets, list)
            or any(not isinstance(item, list) or len(item) != 2 for item in assets)):
        raise ValueError("Context asset evidence must be ordered role/digest pairs")
    for role, digest in assets:
        _identifier(role)
        _digest(digest)
    dataset = ContextDataset(kind, descriptor["semantic_contract_sha256"],
        descriptor["source_assets_signature_sha256"], tuple(tuple(item) for item in assets), canonical_json(payload))
    if dataset.descriptor() != descriptor:
        raise ValueError("Context JSONB payload differs from its immutable descriptor")
    return dataset


def decode_regional_context_inputs(metadata: dict, rows: tuple[tuple[str, dict], ...],
        binding: RuntimeBinding, *, expected_scope: RegionalInputScope, support_cell_ids: tuple[str, ...],
        analyses: tuple[AnalysisContract, ...],
        scenario_contract: ScenarioContract, social_contract: SocialAcceptanceContract,
        combined_policy_manifest: Mapping[str, Any] | None,
        combined_policy_manifest_reference: str | None,
        combined_policy_manifest_path: Path | None,
        landscape_contract: LandscapeContract | None,
        standard_domain: StandardDomainBinding | None = None,
        standard_cell_ids: tuple[str, ...] = (),
        landscape_domain: DomainCellsInput | None = None) -> RegionalContextReadResult:
    from .postgis_technical_inputs import decode_technology_context_dataset, decode_rooftop_population_dataset
    validate_scope(expected_scope)
    if binding.region_id != expected_scope.region_id:
        raise ValueError("Context revision belongs to another region")
    _keys(metadata, {"format", "scope", "datasets"})
    if (metadata["format"] != FORMAT_VERSION or _sha(metadata) != binding.revision_sha256
            or metadata["scope"] != json.loads(canonical_json(asdict(expected_scope)))):
        raise ValueError("Context revision or current analysis/domain binding drifted")
    required = required_context_dataset_kinds(expected_scope, analyses,
        combined_policy_manifest=combined_policy_manifest, landscape_contract=landscape_contract)
    _combined_declaration(combined_policy_manifest, combined_policy_manifest_reference, combined_policy_manifest_path)
    if (not isinstance(rows, tuple)
            or any(not isinstance(row, tuple) or len(row) != 2 for row in rows)
            or tuple(row[0] for row in rows) != required):
        raise ValueError("Context dataset set is missing, duplicated, unknown or not implemented")
    descriptors = metadata["datasets"]
    if (not isinstance(descriptors, list) or len(descriptors) != len(required)
            or any(not isinstance(item, dict) for item in descriptors)
            or tuple(item.get("kind") for item in descriptors) != required):
        raise ValueError("Context descriptor set/order differs from current contracts")
    datasets = {kind: _dataset_from_row(kind, payload, descriptor)
                for (kind, payload), descriptor in zip(rows, descriptors, strict=True)}
    payloads = dict(rows)
    scenario, social = _decode_scenario(payloads["scenario"]), _decode_social(payloads["social_acceptance"])
    technology = decode_technology_context_dataset(datasets["technology_context"], expected_scope,
        analyses=analyses, support_cell_ids=support_cell_ids)
    population = None
    if "rooftop_population" in required:
        population = decode_rooftop_population_dataset(datasets["rooftop_population"], expected_scope,
            analyses=analyses, standard_domain=standard_domain, standard_cell_ids=standard_cell_ids)
    base = _build_scenario_social_inputs(expected_scope, support_cell_ids=support_cell_ids,
        scenario_contract=scenario_contract, scenario_snapshot=scenario,
        social_contract=social_contract, social_snapshot=social)
    if any(item != datasets[item.kind] for item in base.datasets):
        raise ValueError("Scenario/social semantic contract or upstream source descriptor drifted")
    landscape, combined = None, None
    if "landscape" in required:
        from .postgis_landscape_inputs import decode_landscape_dataset
        landscape = decode_landscape_dataset(datasets["landscape"], expected_scope,
            contract=landscape_contract, analyses=analyses, standard_domain=landscape_domain)
    elif landscape_domain is not None:
        raise ValueError("Undeclared landscape cannot supply a source domain")
    if "combined_policy" in required:
        from .postgis_combined_policy_inputs import decode_combined_policy_dataset
        combined = decode_combined_policy_dataset(datasets["combined_policy"], expected_scope,
            analyses=analyses, support_cell_ids=support_cell_ids, manifest=combined_policy_manifest,
            manifest_reference=combined_policy_manifest_reference, manifest_path=combined_policy_manifest_path)
    rebuilt = RegionalContextInputs(expected_scope, tuple(datasets[kind] for kind in required))
    if rebuilt.metadata() != metadata:
        raise ValueError("Context payload, semantic contract or upstream asset signature drifted")
    return RegionalContextReadResult(rebuilt, scenario, social, technology, population,
        landscape, combined, support_cell_ids, standard_cell_ids)


def _read_context_revision_metadata(cursor: Any, binding: RuntimeBinding,
        expected_scope: RegionalInputScope) -> tuple[dict, dict]:
    """Common small metadata checks for full reads, imports and cache probes."""
    validate_scope(expected_scope)
    if binding.region_id != expected_scope.region_id:
        raise ValueError("Context revision belongs to another region")
    query = sql.SQL("select region_id, analysis_revision_sha256, metadata from {}.regional_context_revisions where revision_sha256 = %s").format(sql.Identifier(binding.database_schema))
    cursor.execute(query, (binding.revision_sha256,))
    records = cursor.fetchall()
    if len(records) != 1 or records[0][:2] != (expected_scope.region_id, expected_scope.analysis_revision_sha256):
        raise ValueError("Context revision is missing or its region/analysis pin drifted")
    metadata = records[0][2]
    _keys(metadata, {"format", "scope", "datasets"})
    if (metadata["format"] != FORMAT_VERSION or _sha(metadata) != binding.revision_sha256
            or metadata["scope"] != json.loads(canonical_json(asdict(expected_scope)))):
        raise ValueError("Context revision metadata or current scope drifted")
    descriptors = metadata["datasets"]
    if not isinstance(descriptors, list) or any(not isinstance(item, dict) for item in descriptors):
        raise ValueError("Context revision descriptors are invalid")
    kinds = [item.get("kind") for item in descriptors]
    if (any(not isinstance(kind, str) for kind in kinds) or kinds != sorted(set(kinds))
            or set(kinds) - set(DATASET_KINDS)
            or not {"scenario", "social_acceptance", "technology_context"}.issubset(kinds)):
        raise ValueError("Context revision descriptor membership is invalid")
    for descriptor in descriptors:
        _keys(descriptor, {"kind", "semantic_contract_sha256", "source_assets_signature_sha256",
                           "source_asset_sha256", "payload_sha256"})
        for key in ("semantic_contract_sha256", "source_assets_signature_sha256", "payload_sha256"):
            _digest(descriptor[key])
        assets = descriptor["source_asset_sha256"]
        if not isinstance(assets, list) or any(not isinstance(item, list) or len(item) != 2 for item in assets):
            raise ValueError("Context upstream asset descriptor is invalid")
        for role, digest in assets:
            _identifier(role)
            _digest(digest)
    from .postgis_revision_metadata import read_analysis_revision_metadata_with_digest
    parents, parent_digest = read_analysis_revision_metadata_with_digest(cursor, RuntimeBinding(
        expected_scope.region_id, binding.database_schema, expected_scope.analysis_revision_sha256))
    if (len(parents) != 1 or parents[0][0] != expected_scope.region_id
            or not isinstance(parents[0][1], dict)
            or parents[0][1].get("format") != "roads-postgis-1"
            or parents[0][1].get("region_id") != expected_scope.region_id
            or (parent_digest if parent_digest is not None else _sha(parents[0][1])) != expected_scope.analysis_revision_sha256):
        raise ValueError("Referenced immutable analysis revision is missing or changed")
    domain = expected_scope.support_domain
    matches = [value for value in parents[0][1].get("domains", ())
        if (value.get("domain_id"), value.get("resolution")) == (domain.domain_id, domain.resolution)]
    if len(matches) != 1 or matches[0].get("role") != "technology_support" or any(
            matches[0].get(key) != value for key, value in asdict(domain).items()):
        raise ValueError("Context support binding differs from its immutable analysis domain")
    return metadata, parents[0][1]


def _read_regional_context_rows(cursor: Any, binding: RuntimeBinding, *,
        expected_scope: RegionalInputScope, scenario_contract: ScenarioContract,
        social_contract: SocialAcceptanceContract,
        analyses: tuple[AnalysisContract, ...],
        combined_policy_manifest: Mapping[str, Any] | None,
        combined_policy_manifest_reference: str | None,
        combined_policy_manifest_path: Path | None,
        landscape_contract: LandscapeContract | None) -> RegionalContextReadResult:
    """Read declared views only; current scope/contracts must come from the caller."""
    required = required_context_dataset_kinds(expected_scope, analyses,
        combined_policy_manifest=combined_policy_manifest, landscape_contract=landscape_contract)
    metadata, parent_metadata = _read_context_revision_metadata(cursor, binding, expected_scope)
    domain = expected_scope.support_domain
    query = sql.SQL("select cell_id from {}.analysis_runtime_cells where revision_sha256 = %s and domain_id = %s and resolution = %s order by cell_id").format(sql.Identifier(binding.database_schema))
    cursor.execute(query, (expected_scope.analysis_revision_sha256, domain.domain_id, domain.resolution))
    cell_ids = tuple(row[0] for row in cursor.fetchall())
    # The support domain is not the canonical population clipping domain.
    # Derive its independent binding from the referenced parent revision,
    # never from the context payload that is about to be validated.
    standard_domain, standard_ids, landscape_domain = None, (), None
    if "rooftop_population" in required or "landscape" in required:
        from .postgis_technical_inputs import StandardDomainBinding, _validate_standard_domain
        solar = next(analysis for analysis in analyses if analysis.id == "solar")
        standard_contract = solar.analysis_domain
        if standard_contract is None:
            raise ValueError("Declared rooftop input requires a canonical solar domain")
        matches = [value for value in parent_metadata.get("domains", ())
            if value.get("role") == "standard_analysis"
            and value.get("resolution") == standard_contract.resolution]
        if len(matches) != 1:
            raise ValueError("Parent GIS revision lacks one exact canonical standard domain")
        standard_domain = StandardDomainBinding(**{
            key: matches[0].get(key) for key in StandardDomainBinding.__dataclass_fields__})
        parameters = (expected_scope.analysis_revision_sha256, standard_domain.domain_id, standard_domain.resolution)
        if "landscape" in required:
            query = sql.SQL("select cell_id, area_value, ST_AsBinary(geom, 'NDR'), ST_SRID(geom) from {}.analysis_runtime_cells where revision_sha256 = %s and domain_id = %s and resolution = %s order by cell_id").format(sql.Identifier(binding.database_schema))
            cursor.execute(query, parameters)
            values = cursor.fetchall()
            if any(row[3] != 4326 for row in values):
                raise ValueError("Landscape canonical domain geometry has an invalid CRS")
            domain_metadata = matches[0]
            cells = tuple(DomainCell(row[0], float(row[1]), canonical_wkb(bytes(row[2]))) for row in values)
            landscape_domain = DomainCellsInput(domain_metadata["domain_id"], domain_metadata["role"],
                domain_metadata["resolution"], domain_metadata["source_sha256"], domain_metadata["area_unit"], cells)
            if (len(cells) != domain_metadata["cell_count"]
                    or landscape_domain.cell_ids_sha256 != domain_metadata["cell_ids_sha256"]
                    or landscape_domain.cells_sha256 != domain_metadata["cells_sha256"]
                    or landscape_domain.geometry_sha256 != domain_metadata["geometry_sha256"]):
                raise ValueError("Landscape canonical domain rows differ from their immutable GIS descriptor")
            standard_ids = tuple(cell.cell_id for cell in cells)
        else:
            query = sql.SQL("select cell_id from {}.analysis_runtime_cells where revision_sha256 = %s and domain_id = %s and resolution = %s order by cell_id").format(sql.Identifier(binding.database_schema))
            cursor.execute(query, parameters)
            standard_ids = tuple(row[0] for row in cursor.fetchall())
        _validate_standard_domain(solar, standard_domain, standard_ids)
    from .postgis_context_payloads import read_context_dataset_rows
    rows = read_context_dataset_rows(cursor, binding)
    return decode_regional_context_inputs(metadata, rows, binding,
        expected_scope=expected_scope, support_cell_ids=cell_ids,
        analyses=analyses, scenario_contract=scenario_contract, social_contract=social_contract,
        standard_domain=standard_domain, standard_cell_ids=standard_ids, landscape_domain=landscape_domain,
        landscape_contract=landscape_contract, combined_policy_manifest=combined_policy_manifest,
        combined_policy_manifest_reference=combined_policy_manifest_reference,
        combined_policy_manifest_path=combined_policy_manifest_path)


def read_regional_context_from_cursor(cursor: Any, binding: RuntimeBinding, **current) -> RegionalContextReadResult:
    """The public cursor seam always enforces the read-only transaction."""
    cursor.execute("show transaction_read_only")
    if cursor.fetchone() != ("on",):
        raise ValueError("Context reads require a read-only transaction")
    return _read_regional_context_rows(cursor, binding, **current)


def probe_regional_context_revision(database_url: str, binding: RuntimeBinding, *,
        expected_scope: RegionalInputScope) -> dict[str, Any]:
    """Small live cache gate: metadata and row membership, never payload values."""
    if not isinstance(database_url, str) or not database_url.strip():
        raise ValueError("A private database connection is required")
    import psycopg
    try:
        with psycopg.connect(database_url, connect_timeout=5,
                options="-c default_transaction_read_only=on -c statement_timeout=5000") as connection:
            with connection.cursor() as cursor:
                cursor.execute("set transaction isolation level repeatable read, read only")
                metadata, _parent = _read_context_revision_metadata(cursor, binding, expected_scope)
                cursor.execute(sql.SQL("select dataset_kind from {}.regional_context_datasets where revision_sha256 = %s order by dataset_kind").format(sql.Identifier(binding.database_schema)), (binding.revision_sha256,))
                kinds = tuple(row[0] for row in cursor.fetchall())
                if kinds != tuple(item["kind"] for item in metadata["datasets"]):
                    raise ValueError("Context payload membership differs from its immutable descriptor")
                domain = expected_scope.support_domain
                cursor.execute(sql.SQL("select count(*) from {}.analysis_runtime_cells where revision_sha256 = %s and domain_id = %s and resolution = %s").format(sql.Identifier(binding.database_schema)),
                    (expected_scope.analysis_revision_sha256, domain.domain_id, domain.resolution))
                if cursor.fetchone() != (domain.cell_count,):
                    raise ValueError("Context support row coverage drifted")
    except psycopg.Error:
        raise ValueError("PostGIS regional context revision is unavailable") from None
    return {"region_id": binding.region_id, "database_schema": binding.database_schema,
        "revision_sha256": binding.revision_sha256,
        "analysis_revision_sha256": expected_scope.analysis_revision_sha256,
        "domain_id": expected_scope.support_domain.domain_id,
        "required_datasets": list(kinds), "state": "available_revision"}


def read_regional_context(database_url: str, binding: RuntimeBinding, *,
        expected_scope: RegionalInputScope, scenario_contract: ScenarioContract,
        social_contract: SocialAcceptanceContract,
        analyses: tuple[AnalysisContract, ...],
        combined_policy_manifest: Mapping[str, Any] | None,
        combined_policy_manifest_reference: str | None,
        combined_policy_manifest_path: Path | None,
        landscape_contract: LandscapeContract | None) -> RegionalContextReadResult:
    """Coherent path-free read; credentials are never serialized or reported."""
    if not isinstance(database_url, str) or not database_url.strip():
        raise ValueError("A private database connection is required")
    import psycopg
    try:
        with psycopg.connect(database_url, connect_timeout=5,
                options="-c default_transaction_read_only=on -c statement_timeout=30000") as connection:
            with connection.cursor() as cursor:
                cursor.execute("set transaction isolation level repeatable read, read only")
                from .postgis_context_cache import read_context_with_content_reuse
                return read_context_with_content_reuse(cursor, binding, expected_scope=expected_scope,
                    scenario_contract=scenario_contract, social_contract=social_contract, analyses=analyses,
                    landscape_contract=landscape_contract, combined_policy_manifest=combined_policy_manifest,
                    combined_policy_manifest_reference=combined_policy_manifest_reference,
                    combined_policy_manifest_path=combined_policy_manifest_path)
    except psycopg.Error:
        raise RuntimeError("PostGIS regional context read failed") from None
