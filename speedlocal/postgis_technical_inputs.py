"""Staged typed technology/population payloads; no I/O or new analytical rules.

Capture functions accept one checksum-verified upstream byte snapshot. Runtime
decoders accept JSONB-compatible ContextDataset values and current GIS scope.
The fixed regional-context reader owns required-kind dispatch and verifies the
current parent GIS revision before handing these typed snapshots to consumers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import json
from typing import Any

import h3
import pandas as pd

from .contracts import AnalysisContract, canonical_contract_evidence
from .distributed_generation import rooftop_population_counts_from_raw_frame
from .postgis_context_inputs import (
    ContextDataset, RegionalInputScope, _digest, _finite, _identifier, _ids_sha,
    _keys, _sha, _validate_support_ids, validate_scope,
)
from .postgis_runtime import DomainCellsInput, canonical_json
from .technology_context import (
    TechnologyContextFieldValue, build_technology_context_capability_contract,
    technology_context_contract_signature,
    technology_context_source_values_from_payload, _parse_field_value,
)
from .workspace_request import analysis_contract_signature

TYPED_DATASET_KINDS = ("technology_context", "rooftop_population")


@dataclass(frozen=True)
class TechnologyContextSourceCell:
    cell_id: str
    values: tuple[TechnologyContextFieldValue, ...]


@dataclass(frozen=True)
class TechnologyContextSourceSnapshot:
    source_sha256: str
    cells: tuple[TechnologyContextSourceCell, ...]

    def source_values(self) -> dict[str, tuple[TechnologyContextFieldValue, ...]]:
        return {cell.cell_id: cell.values for cell in self.cells}


@dataclass(frozen=True)
class StandardDomainBinding:
    domain_id: str
    resolution: int
    source_sha256: str
    cell_count: int
    cell_ids_sha256: str
    cells_sha256: str

    @classmethod
    def from_domain(cls, domain: DomainCellsInput) -> StandardDomainBinding:
        if domain.role != "standard_analysis":
            raise ValueError("Rooftop population requires the canonical standard domain")
        return cls(domain.domain_id, domain.resolution, domain.source_sha256,
                   len(domain.cells), domain.cell_ids_sha256, domain.cells_sha256)


@dataclass(frozen=True)
class RooftopPopulationObservation:
    cell_id: str
    population: int | float


@dataclass(frozen=True)
class RooftopPopulationSnapshot:
    source_sha256: str
    standard_domain: StandardDomainBinding
    observations: tuple[RooftopPopulationObservation, ...]

    def raw_frame(self, contract) -> pd.DataFrame:
        # Preserve upstream order and numeric type before the existing pandas
        # grouping. Canonical clipping must not discard source accounting rows.
        return pd.DataFrame({contract.h3_id_field: [row.cell_id for row in self.observations],
                             contract.value_field: [row.population for row in self.observations]})


def _current_analyses(scope: RegionalInputScope, analyses: tuple[AnalysisContract, ...]):
    validate_scope(scope)
    if (not isinstance(analyses, tuple) or len(analyses) != 2
            or {item.id for item in analyses} != {"wind", "solar"}
            or any(item.region_id != scope.region_id for item in analyses)):
        raise ValueError("Technical inputs require the current regional wind and solar contracts")
    current = {item.id: item for item in analyses}
    signatures = tuple((key, analysis_contract_signature(current[key])) for key in ("solar", "wind"))
    if signatures != scope.analysis_contract_signatures:
        raise ValueError("Technical inputs have stale current analysis semantics")
    return current


def _captured_json(payload: bytes, expected_sha256: str) -> dict[str, Any]:
    if (not isinstance(payload, bytes)
            or hashlib.sha256(payload).hexdigest() != _digest(expected_sha256)):
        raise ValueError("Captured upstream bytes differ from the declared asset checksum")
    parsed = json.loads(payload)
    if not isinstance(parsed, dict) or parsed.get("type") != "FeatureCollection" or not isinstance(parsed.get("features"), list):
        raise ValueError("Technology context source must be a GeoJSON FeatureCollection")
    return parsed


def capture_technology_context_source(contract, source_bytes: bytes) -> TechnologyContextSourceSnapshot:
    values = technology_context_source_values_from_payload(
        contract.source, _captured_json(source_bytes, contract.source.sha256))
    return TechnologyContextSourceSnapshot(contract.source.sha256, tuple(
        TechnologyContextSourceCell(cell_id, values[cell_id]) for cell_id in sorted(values)))


def build_technology_context_dataset(scope: RegionalInputScope, *, analyses,
        support_cell_ids: tuple[str, ...], snapshot: TechnologyContextSourceSnapshot) -> ContextDataset:
    current = _current_analyses(scope, analyses)
    _validate_support_ids(scope, support_cell_ids)
    contract = build_technology_context_capability_contract((current["wind"], current["solar"]))
    domain = scope.support_domain
    if ((contract.domain.domain_id, contract.domain.resolution, contract.domain.sha256,
         contract.domain.expected_cell_count, contract.domain.cell_ids_sha256)
            != (domain.domain_id, domain.resolution, domain.source_sha256,
                domain.cell_count, domain.cell_ids_sha256)):
        raise ValueError("Technology context differs from the current support domain")
    if (not isinstance(snapshot, TechnologyContextSourceSnapshot)
            or snapshot.source_sha256 != contract.source.sha256 or not isinstance(snapshot.cells, tuple)):
        raise ValueError("Technology context snapshot source identity/type is invalid")
    ids = tuple(cell.cell_id for cell in snapshot.cells)
    if (ids != tuple(sorted(set(ids))) or len(ids) != contract.source.expected_cell_count
            or _ids_sha(ids) != contract.source.cell_ids_sha256):
        raise ValueError("Technology context source coverage drifted")
    observed = set()
    for cell in snapshot.cells:
        if (not isinstance(cell, TechnologyContextSourceCell) or not h3.is_valid_cell(cell.cell_id)
                or h3.get_resolution(cell.cell_id) != contract.source.resolution
                or not isinstance(cell.values, tuple)):
            raise ValueError("Technology context cell identity/type is invalid")
        field_ids = tuple(value.field_id for value in cell.values)
        if (field_ids != tuple(field for field in contract.source.context_fields if field in field_ids)
                or len(set(field_ids)) != len(field_ids)):
            raise ValueError("Technology context field order/membership is invalid")
        for value in cell.values:
            if not isinstance(value, TechnologyContextFieldValue) or _parse_field_value(value.as_dict()) != value:
                raise ValueError("Technology context value kind is invalid")
            observed.add(value.field_id)
    if observed != set(contract.source.context_fields):
        raise ValueError("A declared technology context field is entirely unobserved")
    payload = canonical_json({"schema_version": "1.0", "scope": asdict(scope), "snapshot": asdict(snapshot)})
    return ContextDataset("technology_context", technology_context_contract_signature(contract),
        _sha(canonical_contract_evidence(contract.source)), (("technology_context", snapshot.source_sha256),), payload)


def decode_technology_context_dataset(dataset: ContextDataset, scope: RegionalInputScope, *,
        analyses, support_cell_ids: tuple[str, ...]) -> TechnologyContextSourceSnapshot:
    payload = _keys(json.loads(dataset.payload_json), {"schema_version", "scope", "snapshot"})
    if payload["schema_version"] != "1.0" or canonical_json(payload["scope"]) != canonical_json(asdict(scope)):
        raise ValueError("Technology context JSONB is bound to another revision/region/domain")
    raw = _keys(payload["snapshot"], {"source_sha256", "cells"})
    if not isinstance(raw["cells"], list):
        raise ValueError("Technology context cells must be an array")
    cells = []
    for value in raw["cells"]:
        cell = _keys(value, {"cell_id", "values"})
        if not isinstance(cell["values"], list):
            raise ValueError("Technology context values must be an array")
        cells.append(TechnologyContextSourceCell(cell["cell_id"], tuple(_parse_field_value(item) for item in cell["values"])))
    snapshot = TechnologyContextSourceSnapshot(raw["source_sha256"], tuple(cells))
    rebuilt = build_technology_context_dataset(scope, analyses=analyses,
        support_cell_ids=support_cell_ids, snapshot=snapshot)
    if rebuilt != dataset:
        raise ValueError("Technology context payload/semantic/source descriptor drifted")
    return snapshot


def _validate_standard_domain(analysis, binding: StandardDomainBinding, cell_ids: tuple[str, ...]) -> None:
    if not isinstance(binding, StandardDomainBinding):
        raise TypeError("Rooftop population requires a typed standard-domain binding")
    _identifier(binding.domain_id)
    domain = analysis.analysis_domain
    if domain is None or (binding.source_sha256, binding.resolution, binding.cell_count) != (
            domain.sha256, domain.resolution, domain.expected_cell_count):
        raise ValueError("Rooftop standard domain differs from the current solar contract")
    if (isinstance(binding.resolution, bool) or not isinstance(binding.resolution, int)
            or isinstance(binding.cell_count, bool) or not isinstance(binding.cell_count, int)):
        raise ValueError("Rooftop standard-domain resolution/count must be integers")
    for digest in (binding.source_sha256, binding.cell_ids_sha256, binding.cells_sha256):
        _digest(digest)
    if (not isinstance(cell_ids, tuple) or cell_ids != tuple(sorted(set(cell_ids)))
            or len(cell_ids) != binding.cell_count or _ids_sha(cell_ids) != binding.cell_ids_sha256
            or any(not h3.is_valid_cell(value) or h3.get_resolution(value) != binding.resolution for value in cell_ids)):
        raise ValueError("Rooftop canonical domain IDs drifted")


def capture_rooftop_population_source(contract, source_bytes: bytes,
        standard_domain: StandardDomainBinding) -> RooftopPopulationSnapshot:
    if not isinstance(source_bytes, bytes) or hashlib.sha256(source_bytes).hexdigest() != _digest(contract.sha256):
        raise ValueError("Captured rooftop population bytes differ from the declared checksum")
    raw = pd.read_csv(io.BytesIO(source_bytes), dtype={contract.h3_id_field: "string"})
    if {contract.h3_id_field, contract.value_field} - set(raw.columns):
        raise ValueError("Rooftop population is missing its declared columns")
    ids = raw[contract.h3_id_field].astype("string").str.strip()
    values = pd.to_numeric(raw[contract.value_field], errors="coerce")
    return RooftopPopulationSnapshot(contract.sha256, standard_domain,
        tuple(RooftopPopulationObservation(cell_id, value) for cell_id, value in zip(ids, values, strict=True)))


def build_rooftop_population_dataset(scope: RegionalInputScope, *, analyses,
        standard_domain: StandardDomainBinding | None, standard_cell_ids: tuple[str, ...],
        snapshot: RooftopPopulationSnapshot | None) -> ContextDataset | None:
    analysis = _current_analyses(scope, analyses)["solar"]
    rooftop = analysis.distributed_generation.rooftop_solar if analysis.distributed_generation else None
    if rooftop is None:
        if snapshot is not None or standard_domain is not None or standard_cell_ids:
            raise ValueError("Undeclared rooftop capability must not acquire fabricated population inputs")
        return None
    _validate_standard_domain(analysis, standard_domain, standard_cell_ids)
    source = rooftop.population_source
    if (not isinstance(snapshot, RooftopPopulationSnapshot) or snapshot.source_sha256 != source.sha256
            or snapshot.standard_domain != standard_domain or not isinstance(snapshot.observations, tuple)):
        raise ValueError("Rooftop population source/standard-domain binding is invalid")
    for row in snapshot.observations:
        if not isinstance(row, RooftopPopulationObservation) or not isinstance(row.cell_id, str):
            raise ValueError("Rooftop population row identity/type is invalid")
        if _finite(row.population) < 0:
            raise ValueError("Rooftop population cannot be negative")
    raw = snapshot.raw_frame(source)
    # Reuse the exact existing validation, canonical clipping, declared totals
    # and rollup behavior at every declared output resolution.
    for resolution in sorted(source.expected_analysis_domain_totals, reverse=True):
        rooftop_population_counts_from_raw_frame(source, raw, standard_cell_ids, resolution)
    payload = canonical_json({"schema_version": "1.0", "scope": asdict(scope), "snapshot": asdict(snapshot)})
    return ContextDataset("rooftop_population", _sha(canonical_contract_evidence(rooftop)),
        _sha(canonical_contract_evidence(source)), (("rooftop_population", source.sha256),), payload)


def decode_rooftop_population_dataset(dataset: ContextDataset, scope: RegionalInputScope, *,
        analyses, standard_domain: StandardDomainBinding, standard_cell_ids: tuple[str, ...]) -> RooftopPopulationSnapshot:
    payload = _keys(json.loads(dataset.payload_json), {"schema_version", "scope", "snapshot"})
    if payload["schema_version"] != "1.0" or canonical_json(payload["scope"]) != canonical_json(asdict(scope)):
        raise ValueError("Rooftop population JSONB is bound to another revision/region/domain")
    raw = _keys(payload["snapshot"], {"source_sha256", "standard_domain", "observations"})
    bound = _keys(raw["standard_domain"], set(StandardDomainBinding.__dataclass_fields__))
    if not isinstance(raw["observations"], list):
        raise ValueError("Rooftop population rows must be an array")
    observations = tuple(RooftopPopulationObservation(**_keys(row, {"cell_id", "population"})) for row in raw["observations"])
    snapshot = RooftopPopulationSnapshot(raw["source_sha256"], StandardDomainBinding(**bound), observations)
    rebuilt = build_rooftop_population_dataset(scope, analyses=analyses, standard_domain=standard_domain,
        standard_cell_ids=standard_cell_ids, snapshot=snapshot)
    if rebuilt != dataset:
        raise ValueError("Rooftop population payload/semantic/source descriptor drifted")
    return snapshot
