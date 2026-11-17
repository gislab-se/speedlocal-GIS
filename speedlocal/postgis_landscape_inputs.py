"""Exact accepted landscape properties in the existing regional ContextDataset.

Capture accepts explicit upstream bytes. Build/decode use current contracts and
the verified standard-domain snapshot; no files, database calls or new scoring.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Mapping

from .contracts import AnalysisContract
from .landscape import (
    LandscapeContract, _domain_artifact_matches,
    landscape_contract_signature, landscape_feature_rows_from_payload,
    landscape_evidence_from_rows, validate_landscape_generated_evidence,
    validate_landscape_review_counts,
)
from .postgis_context_inputs import (
    ContextDataset, RegionalInputScope, _digest, _identifier, _keys, _sha,
    validate_current_analysis_scope,
)
from .postgis_runtime import DomainCellsInput, canonical_json


@dataclass(frozen=True)
class LandscapeSourceSnapshot:
    source_sha256: str
    source_bytes: int
    records_json: str
    review_assets: tuple[tuple[str, str], ...] = ()

    def source_records(self) -> list[dict[str, Any]]:
        """Return a fresh copy in original feature/property order."""
        value = json.loads(self.records_json)
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise ValueError("Landscape snapshot requires original property records")
        return value


def _records_json(records: list[dict[str, Any]]) -> str:
    # Store this as a string inside JSONB: object-key and feature order must not
    # be rewritten by PostgreSQL's object normalization.
    return json.dumps(records, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _review_assets(contract: LandscapeContract) -> tuple[tuple[str, Any], ...]:
    review = contract.review_evidence
    return () if review is None else (
        ("source_manifest", review.source_manifest), ("handoff", review.handoff),
    )


def _validate_review_assets(contract: LandscapeContract, values: tuple[tuple[str, str], ...]) -> None:
    expected = _review_assets(contract)
    if (not isinstance(values, tuple)
            or any(not isinstance(item, tuple) or len(item) != 2 for item in values)
            or tuple(item[0] for item in values) != tuple(item[0] for item in expected)):
        raise ValueError("Landscape review documents differ from the declared evidence")
    for (name, text), (_, asset) in zip(values, expected):
        if not isinstance(text, str) or hashlib.sha256(text.encode('utf-8')).hexdigest() != asset.sha256:
            raise ValueError(f"Landscape review {name} checksum drifted")


def capture_landscape_source(
    contract: LandscapeContract,
    source_bytes: bytes,
    *,
    review_assets: Mapping[str, bytes] | None = None,
) -> LandscapeSourceSnapshot:
    """Capture the declared accepted source, never the larger context source."""
    if not isinstance(contract, LandscapeContract):
        raise TypeError("Landscape capture requires the current landscape contract")
    if (not isinstance(source_bytes, bytes)
            or hashlib.sha256(source_bytes).hexdigest() != contract.source.sha256
            or len(source_bytes) != contract.generated_evidence.source_bytes):
        raise ValueError("Landscape capture differs from the original source bytes/checksum")
    payload = json.loads(source_bytes.decode('utf-8'))
    rows, _ = landscape_feature_rows_from_payload(
        payload, id_field=contract.source.id_field, resolution=contract.source.resolution,
        value_fields=tuple(view.value_field for view in contract.views),
    )
    supplied = {} if review_assets is None else dict(review_assets)
    expected = _review_assets(contract)
    if set(supplied) != {name for name, _ in expected}:
        raise ValueError("Landscape capture must include exactly its declared review documents")
    documents = []
    for name, _ in expected:
        if not isinstance(supplied[name], bytes):
            raise TypeError("Landscape review capture requires original bytes")
        documents.append((name, supplied[name].decode('utf-8')))
    captured = LandscapeSourceSnapshot(contract.source.sha256, len(source_bytes),
        _records_json([dict(row) for row in rows.values()]), tuple(documents))
    _validate_review_assets(contract, captured.review_assets)
    return captured


def _domain_binding(domain: DomainCellsInput) -> dict[str, Any]:
    return {'domain_id': domain.domain_id, 'role': domain.role,
        'resolution': domain.resolution, 'source_sha256': domain.source_sha256,
        'area_unit': domain.area_unit, 'cell_count': len(domain.cells),
        'cell_ids_sha256': domain.cell_ids_sha256, 'cells_sha256': domain.cells_sha256}


def _validated_rows(scope: RegionalInputScope, *, contract: LandscapeContract,
        analyses: tuple[AnalysisContract, ...], standard_domain: DomainCellsInput,
        snapshot: LandscapeSourceSnapshot):
    validate_current_analysis_scope(scope, analyses)
    if not isinstance(contract, LandscapeContract) or contract.region_id != scope.region_id:
        raise ValueError("Landscape contract belongs to another region")
    for analysis in analyses:
        if not _domain_artifact_matches(contract.domain, analysis.analysis_domain):
            raise ValueError("Landscape domain differs from the current analysis contract")
    if not isinstance(standard_domain, DomainCellsInput) or standard_domain.role != 'standard_analysis':
        raise TypeError("Landscape requires the current typed standard-analysis domain")
    _identifier(standard_domain.domain_id)
    expected = contract.domain
    if ((standard_domain.source_sha256, standard_domain.resolution, standard_domain.area_unit,
         len(standard_domain.cells), standard_domain.cell_ids_sha256) !=
        (expected.sha256, expected.resolution, expected.area_unit,
         expected.expected_cell_count, expected.cell_ids_sha256)):
        raise ValueError("Landscape standard-domain source/coverage drifted")
    ids = tuple(cell.cell_id for cell in standard_domain.cells)
    if ids != tuple(sorted(set(ids))):
        raise ValueError("Landscape standard-domain IDs must be exact and unique")
    domain_rows, _ = landscape_feature_rows_from_payload(
        {'type': 'FeatureCollection', 'features': [
            {'properties': {expected.id_field: cell.cell_id, expected.area_field: cell.area_value}}
            for cell in standard_domain.cells
        ]}, id_field=expected.id_field, resolution=expected.resolution, area_field=expected.area_field,
    )
    if (not isinstance(snapshot, LandscapeSourceSnapshot)
            or snapshot.source_sha256 != contract.source.sha256
            or isinstance(snapshot.source_bytes, bool) or not isinstance(snapshot.source_bytes, int)
            or snapshot.source_bytes != contract.generated_evidence.source_bytes):
        raise ValueError("Landscape snapshot source identity/size is invalid")
    _digest(snapshot.source_sha256)
    records = snapshot.source_records()
    if _records_json(records) != snapshot.records_json:
        raise ValueError("Landscape original records are not canonically encoded in order")
    source_rows, fields = landscape_feature_rows_from_payload(
        {'type': 'FeatureCollection', 'features': [{'properties': record} for record in records]},
        id_field=contract.source.id_field, resolution=contract.source.resolution,
        value_fields=tuple(view.value_field for view in contract.views),
    )
    evidence = landscape_evidence_from_rows(source_bytes=snapshot.source_bytes,
        source_rows=source_rows, field_names=fields, domain_rows=domain_rows,
        domain=contract.domain, views=contract.views)
    validate_landscape_generated_evidence(contract, evidence)
    _validate_review_assets(contract, snapshot.review_assets)
    validate_landscape_review_counts(contract, source_rows, domain_rows)
    return source_rows, domain_rows


def build_landscape_dataset(scope: RegionalInputScope, *, contract: LandscapeContract,
        analyses: tuple[AnalysisContract, ...], standard_domain: DomainCellsInput,
        snapshot: LandscapeSourceSnapshot) -> ContextDataset:
    _validated_rows(scope, contract=contract, analyses=analyses,
        standard_domain=standard_domain, snapshot=snapshot)
    assets = (('landscape_source', contract.source.sha256),) + tuple(
        ('review_' + name, asset.sha256) for name, asset in _review_assets(contract))
    source_signature = _sha({'source': asdict(contract.source), 'domain': asdict(contract.domain),
        'review_assets': assets})
    payload = canonical_json({'schema_version': '1.0', 'scope': asdict(scope),
        'standard_domain': _domain_binding(standard_domain), 'snapshot': asdict(snapshot)})
    return ContextDataset('landscape', landscape_contract_signature(contract),
        source_signature, assets, payload)


def decode_landscape_dataset(dataset: ContextDataset, scope: RegionalInputScope, *,
        contract: LandscapeContract, analyses: tuple[AnalysisContract, ...],
        standard_domain: DomainCellsInput) -> LandscapeSourceSnapshot:
    if not isinstance(dataset, ContextDataset) or dataset.kind != 'landscape':
        raise TypeError("Landscape decoder requires the declared landscape dataset")
    payload = _keys(json.loads(dataset.payload_json),
        {'schema_version', 'scope', 'standard_domain', 'snapshot'})
    if (payload['schema_version'] != '1.0'
            or canonical_json(payload['scope']) != canonical_json(asdict(scope))
            or canonical_json(payload['standard_domain']) != canonical_json(_domain_binding(standard_domain))):
        raise ValueError("Landscape dataset belongs to another current GIS/analysis/domain scope")
    raw = _keys(payload['snapshot'], {'source_sha256', 'source_bytes', 'records_json', 'review_assets'})
    if (not isinstance(raw['records_json'], str) or not isinstance(raw['review_assets'], list)
            or any(not isinstance(item, list) or len(item) != 2 for item in raw['review_assets'])):
        raise ValueError("Landscape snapshot records/review documents are malformed")
    snapshot = LandscapeSourceSnapshot(raw['source_sha256'], raw['source_bytes'], raw['records_json'],
        tuple(tuple(item) for item in raw['review_assets']))
    rebuilt = build_landscape_dataset(scope, contract=contract, analyses=analyses,
        standard_domain=standard_domain, snapshot=snapshot)
    if rebuilt != dataset:
        raise ValueError("Landscape payload/semantic/source descriptor drifted")
    return snapshot
