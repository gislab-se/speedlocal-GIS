from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

import h3

from . import catalogs
from .access_policy import validate_product_access_dimensions
from .contracts import (
    AnalysisContract,
    TechnologyContextContract,
    canonical_contract_evidence,
)
from .paths import resolve_source_path
from .sources import eligible_surface_contract_for_analysis
from .validation import validate_contract


TECHNOLOGY_CONTEXT_CONTRACT_SCHEMA_VERSION = "1.0"
TECHNOLOGY_CONTEXT_REQUEST_SCHEMA_VERSION = "1.0"
TECHNOLOGY_CONTEXT_RESULT_SCHEMA_VERSION = "1.0"
TECHNOLOGY_CONTEXT_CAPABILITY_ID = "workspace.technology_context"
TECHNOLOGY_CONTEXT_ACCESS_SCOPE_KINDS = ("product", "review")
TECHNOLOGY_CONTEXT_CELL_STATUSES = (
    "complete",
    "partial",
    "not_assessed",
)
TECHNOLOGY_CONTEXT_VALUE_KINDS = (
    "boolean",
    "integer",
    "number",
    "string",
)
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_FIELD_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class TechnologyContextDomainContract:
    domain_id: str
    eligible_surface_id: str
    provider: str
    path: str
    sha256: str
    id_field: str
    cell_kind: str
    resolution: int
    expected_cell_count: int
    cell_ids_sha256: str


@dataclass(frozen=True)
class TechnologyContextCapabilityContract:
    schema_version: str
    region_id: str
    capability_id: str
    technologies: tuple[str, ...]
    domain: TechnologyContextDomainContract
    source: TechnologyContextContract


@dataclass(frozen=True)
class TechnologyContextRequest:
    schema_version: str
    access_scope: str
    capability_id: str
    region_id: str
    technologies: tuple[str, ...]
    eligible_surface_id: str
    support_domain_id: str
    domain_provider: str
    domain_path: str
    domain_sha256: str
    domain_id_field: str
    domain_cell_kind: str
    domain_resolution: int
    domain_expected_cell_count: int
    domain_cell_ids_sha256: str
    source_context_id: str
    source_provider: str
    source_path: str
    source_sha256: str
    source_id_field: str
    source_cell_kind: str
    source_resolution: int
    source_expected_cell_count: int
    source_cell_ids_sha256: str
    context_fields: tuple[str, ...]
    missing_policy: str
    contract_signature_sha256: str
    request_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "capability_id": self.capability_id,
            "region_id": self.region_id,
            "technologies": list(self.technologies),
            "eligible_surface_id": self.eligible_surface_id,
            "support_domain_id": self.support_domain_id,
            "domain_provider": self.domain_provider,
            "domain_path": self.domain_path,
            "domain_sha256": self.domain_sha256,
            "domain_id_field": self.domain_id_field,
            "domain_cell_kind": self.domain_cell_kind,
            "domain_resolution": self.domain_resolution,
            "domain_expected_cell_count": self.domain_expected_cell_count,
            "domain_cell_ids_sha256": self.domain_cell_ids_sha256,
            "source_context_id": self.source_context_id,
            "source_provider": self.source_provider,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "source_id_field": self.source_id_field,
            "source_cell_kind": self.source_cell_kind,
            "source_resolution": self.source_resolution,
            "source_expected_cell_count": self.source_expected_cell_count,
            "source_cell_ids_sha256": self.source_cell_ids_sha256,
            "context_fields": list(self.context_fields),
            "missing_policy": self.missing_policy,
            "contract_signature_sha256": self.contract_signature_sha256,
            "request_signature_sha256": self.request_signature_sha256,
        }


@dataclass(frozen=True)
class TechnologyContextFieldValue:
    field_id: str
    value_kind: str
    value: bool | int | float | str

    def as_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "value_kind": self.value_kind,
            "value": self.value,
        }


@dataclass(frozen=True)
class TechnologyContextCell:
    cell_id: str
    status: str
    observed_field_count: int
    values: tuple[TechnologyContextFieldValue, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "status": self.status,
            "observed_field_count": self.observed_field_count,
            "values": [value.as_dict() for value in self.values],
        }


@dataclass(frozen=True)
class TechnologyContextFieldEvidence:
    field_id: str
    value_kinds: tuple[str, ...]
    source_observed_cell_count: int
    target_observed_cell_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "field_id": self.field_id,
            "value_kinds": list(self.value_kinds),
            "source_observed_cell_count": self.source_observed_cell_count,
            "target_observed_cell_count": self.target_observed_cell_count,
        }


@dataclass(frozen=True)
class TechnologyContextResult:
    schema_version: str
    access_scope: str
    capability_id: str
    region_id: str
    contract_signature_sha256: str
    request_signature_sha256: str
    request: TechnologyContextRequest
    source_cell_count: int
    source_cell_ids_sha256: str
    source_complete_cell_count: int
    source_complete_cell_ids_sha256: str
    source_partial_cell_count: int
    source_partial_cell_ids_sha256: str
    source_unobserved_cell_count: int
    source_unobserved_cell_ids_sha256: str
    source_declared_values_sha256: str
    target_domain_cell_count: int
    target_domain_cell_ids_sha256: str
    complete_cell_count: int
    complete_cell_ids_sha256: str
    partial_cell_count: int
    partial_cell_ids_sha256: str
    not_assessed_cell_count: int
    not_assessed_cell_ids_sha256: str
    outside_domain_source_cell_count: int
    outside_domain_source_cell_ids_sha256: str
    target_declared_values_sha256: str
    field_evidence: tuple[TechnologyContextFieldEvidence, ...]
    cells: tuple[TechnologyContextCell, ...]
    result_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "capability_id": self.capability_id,
            "region_id": self.region_id,
            "contract_signature_sha256": self.contract_signature_sha256,
            "request_signature_sha256": self.request_signature_sha256,
            "request": self.request.as_dict(),
            "source_cell_count": self.source_cell_count,
            "source_cell_ids_sha256": self.source_cell_ids_sha256,
            "source_complete_cell_count": self.source_complete_cell_count,
            "source_complete_cell_ids_sha256": (
                self.source_complete_cell_ids_sha256
            ),
            "source_partial_cell_count": self.source_partial_cell_count,
            "source_partial_cell_ids_sha256": self.source_partial_cell_ids_sha256,
            "source_unobserved_cell_count": self.source_unobserved_cell_count,
            "source_unobserved_cell_ids_sha256": (
                self.source_unobserved_cell_ids_sha256
            ),
            "source_declared_values_sha256": self.source_declared_values_sha256,
            "target_domain_cell_count": self.target_domain_cell_count,
            "target_domain_cell_ids_sha256": self.target_domain_cell_ids_sha256,
            "complete_cell_count": self.complete_cell_count,
            "complete_cell_ids_sha256": self.complete_cell_ids_sha256,
            "partial_cell_count": self.partial_cell_count,
            "partial_cell_ids_sha256": self.partial_cell_ids_sha256,
            "not_assessed_cell_count": self.not_assessed_cell_count,
            "not_assessed_cell_ids_sha256": self.not_assessed_cell_ids_sha256,
            "outside_domain_source_cell_count": (
                self.outside_domain_source_cell_count
            ),
            "outside_domain_source_cell_ids_sha256": (
                self.outside_domain_source_cell_ids_sha256
            ),
            "target_declared_values_sha256": self.target_declared_values_sha256,
            "field_evidence": [item.as_dict() for item in self.field_evidence],
            "cells": [cell.as_dict() for cell in self.cells],
            "result_signature_sha256": self.result_signature_sha256,
        }


@dataclass(frozen=True)
class TechnologyContextProbe:
    state: str
    detail: str


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


def _id_digest(values: Iterable[str]) -> str:
    return hashlib.sha256(
        "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    ).hexdigest()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(
            f"{label} keys drifted: expected={sorted(expected)}, "
            f"actual={sorted(value)}"
        )


def _exact_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be an exact non-empty string")
    return value


def _identifier(value: Any, label: str) -> str:
    text = _exact_text(value, label)
    if _IDENTIFIER.fullmatch(text) is None:
        raise ValueError(f"{label} must be a canonical identifier")
    return text


def _field_identifier(value: Any, label: str) -> str:
    text = _exact_text(value, label)
    if _FIELD_IDENTIFIER.fullmatch(text) is None:
        raise ValueError(f"{label} must be a canonical field identifier")
    return text


def _digest(value: Any, label: str) -> str:
    text = _exact_text(value, label)
    if _SHA256.fullmatch(text) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _count(value: Any, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise ValueError(f"{label} must be {qualifier}")
    return value


def _resolution(value: Any, label: str) -> int:
    number = _count(value, label)
    if number > 15:
        raise ValueError(f"{label} must be an H3 resolution")
    return number


def _exact_string_tuple(
    value: Any,
    label: str,
    *,
    field_names: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list")
    parser = _field_identifier if field_names else _identifier
    result = tuple(parser(item, f"{label} item") for item in value)
    if not result or len(result) != len(set(result)):
        raise ValueError(f"{label} must be non-empty and unique")
    return result


def _validate_asset_identity(
    *,
    provider: str,
    path: str,
    sha256: str,
    id_field: str,
    cell_kind: str,
    resolution: int,
    expected_cell_count: int,
    cell_ids_sha256: str,
    label: str,
) -> None:
    _identifier(provider, f"{label} provider")
    _exact_text(path, f"{label} path")
    _digest(sha256, f"{label} sha256")
    _field_identifier(id_field, f"{label} id field")
    if cell_kind != "h3":
        raise NotImplementedError(f"{label} supports only H3 cells")
    _resolution(resolution, f"{label} resolution")
    _count(expected_cell_count, f"{label} expected cell count", positive=True)
    _digest(cell_ids_sha256, f"{label} cell-id digest")
    if Path(path).suffix.lower() not in {".geojson", ".json"}:
        raise NotImplementedError(f"{label} supports only GeoJSON artifacts")


def validate_technology_context_capability_contract(
    contract: TechnologyContextCapabilityContract,
) -> None:
    if not isinstance(contract, TechnologyContextCapabilityContract):
        raise TypeError("contract must be a TechnologyContextCapabilityContract")
    if contract.schema_version != TECHNOLOGY_CONTEXT_CONTRACT_SCHEMA_VERSION:
        raise NotImplementedError(
            "Unsupported technology-context contract schema version: "
            f"{contract.schema_version}"
        )
    _identifier(contract.region_id, "technology-context region")
    if contract.capability_id != TECHNOLOGY_CONTEXT_CAPABILITY_ID:
        raise ValueError("Technology-context capability id drifted")
    technologies = tuple(
        _identifier(value, "technology-context technology")
        for value in contract.technologies
    )
    if not technologies or len(technologies) != len(set(technologies)):
        raise ValueError("Technology-context technologies must be non-empty and unique")
    domain = contract.domain
    _identifier(domain.domain_id, "technology-context support domain")
    _identifier(domain.eligible_surface_id, "technology-context eligible surface")
    _validate_asset_identity(
        provider=domain.provider,
        path=domain.path,
        sha256=domain.sha256,
        id_field=domain.id_field,
        cell_kind=domain.cell_kind,
        resolution=domain.resolution,
        expected_cell_count=domain.expected_cell_count,
        cell_ids_sha256=domain.cell_ids_sha256,
        label="technology-context domain",
    )
    source = contract.source
    _identifier(source.id, "technology-context source id")
    _validate_asset_identity(
        provider=source.provider,
        path=source.path,
        sha256=source.sha256,
        id_field=source.id_field,
        cell_kind=source.cell_kind,
        resolution=source.resolution,
        expected_cell_count=source.expected_cell_count,
        cell_ids_sha256=source.cell_ids_sha256,
        label="technology-context source",
    )
    if source.resolution != domain.resolution:
        raise ValueError("Technology-context source and domain resolution differ")
    fields = tuple(
        _field_identifier(value, "technology-context field")
        for value in source.context_fields
    )
    if not fields or len(fields) != len(set(fields)):
        raise ValueError("Technology-context fields must be non-empty and unique")
    if source.missing_policy != "explicit_not_assessed":
        raise NotImplementedError(
            "Technology-context missing policy must be explicit_not_assessed"
        )


def technology_context_contract_signature(
    contract: TechnologyContextCapabilityContract,
) -> str:
    validate_technology_context_capability_contract(contract)
    return _canonical_sha256(canonical_contract_evidence(contract))


def build_technology_context_capability_contract(
    analyses: Iterable[AnalysisContract],
) -> TechnologyContextCapabilityContract:
    contracts = tuple(analyses)
    if not contracts:
        raise ValueError("Technology context requires at least one analysis")
    for contract in contracts:
        validate_contract(contract)
    region_id = contracts[0].region_id
    if any(contract.region_id != region_id for contract in contracts):
        raise ValueError("Technology-context analyses belong to different regions")
    technologies = tuple(contract.id for contract in contracts)
    if len(technologies) != len(set(technologies)):
        raise ValueError("Technology-context analysis ids must be unique")
    surfaces = tuple(
        eligible_surface_contract_for_analysis(contract) for contract in contracts
    )
    surface = surfaces[0]
    if any(candidate != surface for candidate in surfaces[1:]):
        raise ValueError(
            "Technology-context analyses must share one exact eligible surface"
        )
    if surface.technologies != technologies:
        raise ValueError(
            "Technology-context analysis order must match surface technologies"
        )
    observations = surface.support_observations
    result = TechnologyContextCapabilityContract(
        schema_version=TECHNOLOGY_CONTEXT_CONTRACT_SCHEMA_VERSION,
        region_id=region_id,
        capability_id=TECHNOLOGY_CONTEXT_CAPABILITY_ID,
        technologies=technologies,
        domain=TechnologyContextDomainContract(
            domain_id=surface.support_domain_id,
            eligible_surface_id=surface.id,
            provider=surface.provider,
            path=surface.path,
            sha256=surface.sha256,
            id_field=surface.id_field,
            cell_kind=surface.cell_kind,
            resolution=surface.resolution,
            expected_cell_count=surface.expected_cell_count,
            cell_ids_sha256=observations.cell_ids_sha256,
        ),
        source=surface.technology_context,
    )
    validate_technology_context_capability_contract(result)
    return result


def load_catalog_technology_context_contract(
    region_id: str,
) -> TechnologyContextCapabilityContract:
    normalized = _identifier(region_id, "technology-context catalog region")
    from .workspace import load_workspace_profile

    profile = load_workspace_profile(normalized)
    if TECHNOLOGY_CONTEXT_CAPABILITY_ID not in profile.capabilities:
        raise KeyError(
            f"{normalized} does not declare {TECHNOLOGY_CONTEXT_CAPABILITY_ID}"
        )
    return build_technology_context_capability_contract(
        catalogs.load_analysis(normalized, technology)
        for technology in profile.technologies
    )


def _request_signature_payload(request: TechnologyContextRequest) -> dict[str, Any]:
    payload = request.as_dict()
    payload.pop("request_signature_sha256")
    return payload


def _validate_access_scope(access_scope: str, region_id: str) -> str:
    text = _exact_text(access_scope, "technology-context access scope")
    if text.count(":") != 1:
        raise ValueError("Technology-context access scope is invalid")
    kind, scope_region = text.split(":", 1)
    if kind not in TECHNOLOGY_CONTEXT_ACCESS_SCOPE_KINDS:
        raise ValueError(f"Unsupported technology-context access mode: {kind}")
    if scope_region != region_id:
        raise ValueError("Technology-context access scope belongs to another region")
    return text


def build_technology_context_request_from_contract(
    contract: TechnologyContextCapabilityContract,
    *,
    access_scope: str,
) -> TechnologyContextRequest:
    validate_technology_context_capability_contract(contract)
    access = _validate_access_scope(access_scope, contract.region_id)
    domain = contract.domain
    source = contract.source
    request = TechnologyContextRequest(
        schema_version=TECHNOLOGY_CONTEXT_REQUEST_SCHEMA_VERSION,
        access_scope=access,
        capability_id=contract.capability_id,
        region_id=contract.region_id,
        technologies=contract.technologies,
        eligible_surface_id=domain.eligible_surface_id,
        support_domain_id=domain.domain_id,
        domain_provider=domain.provider,
        domain_path=domain.path,
        domain_sha256=domain.sha256,
        domain_id_field=domain.id_field,
        domain_cell_kind=domain.cell_kind,
        domain_resolution=domain.resolution,
        domain_expected_cell_count=domain.expected_cell_count,
        domain_cell_ids_sha256=domain.cell_ids_sha256,
        source_context_id=source.id,
        source_provider=source.provider,
        source_path=source.path,
        source_sha256=source.sha256,
        source_id_field=source.id_field,
        source_cell_kind=source.cell_kind,
        source_resolution=source.resolution,
        source_expected_cell_count=source.expected_cell_count,
        source_cell_ids_sha256=source.cell_ids_sha256,
        context_fields=source.context_fields,
        missing_policy=source.missing_policy,
        contract_signature_sha256=technology_context_contract_signature(contract),
        request_signature_sha256="0" * 64,
    )
    return replace(
        request,
        request_signature_sha256=_canonical_sha256(
            _request_signature_payload(request)
        ),
    )


_REQUEST_KEYS = {
    "schema_version",
    "access_scope",
    "capability_id",
    "region_id",
    "technologies",
    "eligible_surface_id",
    "support_domain_id",
    "domain_provider",
    "domain_path",
    "domain_sha256",
    "domain_id_field",
    "domain_cell_kind",
    "domain_resolution",
    "domain_expected_cell_count",
    "domain_cell_ids_sha256",
    "source_context_id",
    "source_provider",
    "source_path",
    "source_sha256",
    "source_id_field",
    "source_cell_kind",
    "source_resolution",
    "source_expected_cell_count",
    "source_cell_ids_sha256",
    "context_fields",
    "missing_policy",
    "contract_signature_sha256",
    "request_signature_sha256",
}


def parse_technology_context_request(value: Any) -> TechnologyContextRequest:
    raw = _mapping(value, "technology-context request")
    _exact_keys(raw, _REQUEST_KEYS, "technology-context request")
    request = TechnologyContextRequest(
        schema_version=_exact_text(raw["schema_version"], "request schema"),
        access_scope=_exact_text(raw["access_scope"], "request access scope"),
        capability_id=_exact_text(raw["capability_id"], "request capability"),
        region_id=_identifier(raw["region_id"], "request region"),
        technologies=_exact_string_tuple(
            raw["technologies"], "request technologies"
        ),
        eligible_surface_id=_identifier(
            raw["eligible_surface_id"], "request eligible surface"
        ),
        support_domain_id=_identifier(
            raw["support_domain_id"], "request support domain"
        ),
        domain_provider=_identifier(raw["domain_provider"], "request domain provider"),
        domain_path=_exact_text(raw["domain_path"], "request domain path"),
        domain_sha256=_digest(raw["domain_sha256"], "request domain sha256"),
        domain_id_field=_field_identifier(
            raw["domain_id_field"], "request domain id field"
        ),
        domain_cell_kind=_exact_text(
            raw["domain_cell_kind"], "request domain cell kind"
        ),
        domain_resolution=_resolution(
            raw["domain_resolution"], "request domain resolution"
        ),
        domain_expected_cell_count=_count(
            raw["domain_expected_cell_count"],
            "request domain expected cell count",
            positive=True,
        ),
        domain_cell_ids_sha256=_digest(
            raw["domain_cell_ids_sha256"], "request domain cell-id digest"
        ),
        source_context_id=_identifier(
            raw["source_context_id"], "request source context"
        ),
        source_provider=_identifier(raw["source_provider"], "request source provider"),
        source_path=_exact_text(raw["source_path"], "request source path"),
        source_sha256=_digest(raw["source_sha256"], "request source sha256"),
        source_id_field=_field_identifier(
            raw["source_id_field"], "request source id field"
        ),
        source_cell_kind=_exact_text(
            raw["source_cell_kind"], "request source cell kind"
        ),
        source_resolution=_resolution(
            raw["source_resolution"], "request source resolution"
        ),
        source_expected_cell_count=_count(
            raw["source_expected_cell_count"],
            "request source expected cell count",
            positive=True,
        ),
        source_cell_ids_sha256=_digest(
            raw["source_cell_ids_sha256"], "request source cell-id digest"
        ),
        context_fields=_exact_string_tuple(
            raw["context_fields"], "request context fields", field_names=True
        ),
        missing_policy=_exact_text(raw["missing_policy"], "request missing policy"),
        contract_signature_sha256=_digest(
            raw["contract_signature_sha256"], "request contract signature"
        ),
        request_signature_sha256=_digest(
            raw["request_signature_sha256"], "request signature"
        ),
    )
    if request.schema_version != TECHNOLOGY_CONTEXT_REQUEST_SCHEMA_VERSION:
        raise NotImplementedError(
            "Unsupported technology-context request schema version: "
            f"{request.schema_version}"
        )
    if request.capability_id != TECHNOLOGY_CONTEXT_CAPABILITY_ID:
        raise ValueError("Technology-context request capability drifted")
    _validate_access_scope(request.access_scope, request.region_id)
    if request.domain_cell_kind != "h3" or request.source_cell_kind != "h3":
        raise NotImplementedError("Technology-context request supports only H3")
    if request.domain_resolution != request.source_resolution:
        raise ValueError("Technology-context request resolutions differ")
    if request.missing_policy != "explicit_not_assessed":
        raise NotImplementedError(
            "Technology-context request missing policy is unsupported"
        )
    expected_signature = _canonical_sha256(_request_signature_payload(request))
    if request.request_signature_sha256 != expected_signature:
        raise ValueError("Technology-context request signature does not match")
    return request


def validate_technology_context_request_from_contract(
    contract: TechnologyContextCapabilityContract,
    request: TechnologyContextRequest,
) -> None:
    if not isinstance(request, TechnologyContextRequest):
        raise TypeError("request must be a TechnologyContextRequest")
    parsed = parse_technology_context_request(request.as_dict())
    expected = build_technology_context_request_from_contract(
        contract,
        access_scope=parsed.access_scope,
    )
    if parsed != expected:
        raise ValueError(
            "Technology-context request does not match the current contract"
        )


def build_catalog_technology_context_request(
    region_id: str,
    *,
    access_scope: str,
) -> TechnologyContextRequest:
    return build_technology_context_request_from_contract(
        load_catalog_technology_context_contract(region_id),
        access_scope=access_scope,
    )


def _resolved_geojson(
    *,
    provider: str,
    path_value: str,
    expected_sha256: str,
    label: str,
) -> Mapping[str, Any]:
    if Path(path_value).suffix.lower() not in {".geojson", ".json"}:
        raise NotImplementedError(f"{label} supports only GeoJSON artifacts")
    path = resolve_source_path(provider, path_value)
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    try:
        payload_bytes = path.read_bytes()
        actual_sha256 = hashlib.sha256(payload_bytes).hexdigest()
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"{label} checksum does not match its manifest: "
                f"{actual_sha256} != {expected_sha256}"
            )
        raw = json.loads(payload_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} cannot be read as UTF-8 GeoJSON: {exc}") from exc
    payload = _mapping(raw, label)
    if payload.get("type") != "FeatureCollection":
        raise ValueError(f"{label} must be a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError(f"{label} must contain a feature list")
    return payload


def _cell_id(
    properties: Mapping[str, Any],
    *,
    id_field: str,
    resolution: int,
    label: str,
) -> str:
    value = properties.get(id_field)
    if not isinstance(value, str) or not h3.is_valid_cell(value):
        raise ValueError(f"{label} has an invalid H3 id")
    if h3.get_resolution(value) != resolution:
        raise ValueError(f"{label} is not R{resolution}")
    return value


def _load_domain_ids(contract: TechnologyContextDomainContract) -> tuple[str, ...]:
    payload = _resolved_geojson(
        provider=contract.provider,
        path_value=contract.path,
        expected_sha256=contract.sha256,
        label="Technology-context domain",
    )
    cell_ids: list[str] = []
    for index, feature in enumerate(payload["features"]):
        feature_map = _mapping(feature, f"Technology-context domain feature {index}")
        properties = _mapping(
            feature_map.get("properties"),
            f"Technology-context domain feature {index} properties",
        )
        cell_ids.append(
            _cell_id(
                properties,
                id_field=contract.id_field,
                resolution=contract.resolution,
                label=f"Technology-context domain feature {index}",
            )
        )
    if len(cell_ids) != len(set(cell_ids)):
        raise ValueError("Technology-context domain contains duplicate H3 ids")
    if len(cell_ids) != contract.expected_cell_count:
        raise ValueError("Technology-context domain cell count does not match")
    if _id_digest(cell_ids) != contract.cell_ids_sha256:
        raise ValueError("Technology-context domain cell-id digest does not match")
    return tuple(sorted(cell_ids))


def _typed_value(field_id: str, value: Any) -> TechnologyContextFieldValue | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        kind = "boolean"
    elif isinstance(value, int):
        kind = "integer"
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"Technology-context field {field_id} is non-finite")
        kind = "number"
    elif isinstance(value, str):
        kind = "string"
    else:
        raise NotImplementedError(
            f"Technology-context field {field_id} has unsupported JSON value "
            f"type {type(value).__name__}"
        )
    return TechnologyContextFieldValue(field_id, kind, value)


def _load_source_values(
    contract: TechnologyContextContract,
) -> dict[str, tuple[TechnologyContextFieldValue, ...]]:
    payload = _resolved_geojson(
        provider=contract.provider,
        path_value=contract.path,
        expected_sha256=contract.sha256,
        label="Technology-context source",
    )
    return technology_context_source_values_from_payload(contract, payload)


def technology_context_source_values_from_payload(
    contract: TechnologyContextContract, payload: Mapping[str, Any],
) -> dict[str, tuple[TechnologyContextFieldValue, ...]]:
    """Apply the existing source interpretation to already captured GeoJSON."""
    values: dict[str, tuple[TechnologyContextFieldValue, ...]] = {}
    for index, feature in enumerate(payload["features"]):
        feature_map = _mapping(feature, f"Technology-context source feature {index}")
        properties = _mapping(
            feature_map.get("properties"),
            f"Technology-context source feature {index} properties",
        )
        cell_id = _cell_id(
            properties,
            id_field=contract.id_field,
            resolution=contract.resolution,
            label=f"Technology-context source feature {index}",
        )
        if cell_id in values:
            raise ValueError("Technology-context source contains duplicate H3 ids")
        cell_values = tuple(
            typed
            for field in contract.context_fields
            if (typed := _typed_value(field, properties.get(field))) is not None
        )
        values[cell_id] = cell_values
    if len(values) != contract.expected_cell_count:
        raise ValueError("Technology-context source cell count does not match")
    if _id_digest(values) != contract.cell_ids_sha256:
        raise ValueError("Technology-context source cell-id digest does not match")
    empty_fields = tuple(
        field
        for field in contract.context_fields
        if not any(value.field_id == field for row in values.values() for value in row)
    )
    if empty_fields:
        raise ValueError(
            "Technology-context source has no observations for declared fields: "
            f"{list(empty_fields)}"
        )
    return values


def _status(values: tuple[TechnologyContextFieldValue, ...], field_count: int) -> str:
    if len(values) == field_count:
        return "complete"
    if values:
        return "partial"
    return "not_assessed"


def _declared_values_digest(
    rows: Iterable[tuple[str, tuple[TechnologyContextFieldValue, ...]]],
) -> str:
    return _canonical_sha256(
        [
            {
                "cell_id": cell_id,
                "values": [value.as_dict() for value in values],
            }
            for cell_id, values in sorted(rows)
        ]
    )


def _result_signature_payload(result: TechnologyContextResult) -> dict[str, Any]:
    payload = result.as_dict()
    payload.pop("result_signature_sha256")
    return payload


def run_technology_context_request_from_contract(
    contract: TechnologyContextCapabilityContract,
    request: TechnologyContextRequest,
) -> TechnologyContextResult:
    validate_technology_context_request_from_contract(contract, request)
    domain_ids = _load_domain_ids(contract.domain)
    source_values = _load_source_values(contract.source)
    return run_technology_context_request_from_values(
        contract, request, domain_ids=domain_ids, source_values=source_values,
    )


def run_technology_context_request_from_values(
    contract: TechnologyContextCapabilityContract,
    request: TechnologyContextRequest, *, domain_ids: tuple[str, ...],
    source_values: Mapping[str, tuple[TechnologyContextFieldValue, ...]],
) -> TechnologyContextResult:
    """Execute unchanged context math from validated domain/source snapshots."""
    validate_technology_context_request_from_contract(contract, request)
    field_count = len(contract.source.context_fields)
    source_by_status = {status: [] for status in TECHNOLOGY_CONTEXT_CELL_STATUSES}
    for cell_id, values in source_values.items():
        source_by_status[_status(values, field_count)].append(cell_id)
    domain_set = set(domain_ids)
    cells = tuple(
        TechnologyContextCell(
            cell_id=cell_id,
            status=_status(source_values.get(cell_id, ()), field_count),
            observed_field_count=len(source_values.get(cell_id, ())),
            values=source_values.get(cell_id, ()),
        )
        for cell_id in domain_ids
    )
    target_by_status = {
        status: tuple(cell.cell_id for cell in cells if cell.status == status)
        for status in TECHNOLOGY_CONTEXT_CELL_STATUSES
    }
    outside = tuple(sorted(set(source_values).difference(domain_set)))
    field_evidence = tuple(
        TechnologyContextFieldEvidence(
            field_id=field,
            value_kinds=tuple(
                kind
                for kind in TECHNOLOGY_CONTEXT_VALUE_KINDS
                if any(
                    value.field_id == field and value.value_kind == kind
                    for row in source_values.values()
                    for value in row
                )
            ),
            source_observed_cell_count=sum(
                any(value.field_id == field for value in row)
                for row in source_values.values()
            ),
            target_observed_cell_count=sum(
                any(value.field_id == field for value in cell.values)
                for cell in cells
            ),
        )
        for field in contract.source.context_fields
    )
    result = TechnologyContextResult(
        schema_version=TECHNOLOGY_CONTEXT_RESULT_SCHEMA_VERSION,
        access_scope=request.access_scope,
        capability_id=request.capability_id,
        region_id=request.region_id,
        contract_signature_sha256=request.contract_signature_sha256,
        request_signature_sha256=request.request_signature_sha256,
        request=request,
        source_cell_count=len(source_values),
        source_cell_ids_sha256=_id_digest(source_values),
        source_complete_cell_count=len(source_by_status["complete"]),
        source_complete_cell_ids_sha256=_id_digest(
            source_by_status["complete"]
        ),
        source_partial_cell_count=len(source_by_status["partial"]),
        source_partial_cell_ids_sha256=_id_digest(source_by_status["partial"]),
        source_unobserved_cell_count=len(source_by_status["not_assessed"]),
        source_unobserved_cell_ids_sha256=_id_digest(
            source_by_status["not_assessed"]
        ),
        source_declared_values_sha256=_declared_values_digest(
            source_values.items()
        ),
        target_domain_cell_count=len(domain_ids),
        target_domain_cell_ids_sha256=_id_digest(domain_ids),
        complete_cell_count=len(target_by_status["complete"]),
        complete_cell_ids_sha256=_id_digest(target_by_status["complete"]),
        partial_cell_count=len(target_by_status["partial"]),
        partial_cell_ids_sha256=_id_digest(target_by_status["partial"]),
        not_assessed_cell_count=len(target_by_status["not_assessed"]),
        not_assessed_cell_ids_sha256=_id_digest(
            target_by_status["not_assessed"]
        ),
        outside_domain_source_cell_count=len(outside),
        outside_domain_source_cell_ids_sha256=_id_digest(outside),
        target_declared_values_sha256=_declared_values_digest(
            (cell.cell_id, cell.values) for cell in cells
        ),
        field_evidence=field_evidence,
        cells=cells,
        result_signature_sha256="0" * 64,
    )
    result = replace(
        result,
        result_signature_sha256=_canonical_sha256(
            _result_signature_payload(result)
        ),
    )
    validate_technology_context_result(result)
    return result


_VALUE_KEYS = {"field_id", "value_kind", "value"}
_CELL_KEYS = {"cell_id", "status", "observed_field_count", "values"}
_FIELD_EVIDENCE_KEYS = {
    "field_id",
    "value_kinds",
    "source_observed_cell_count",
    "target_observed_cell_count",
}
_RESULT_KEYS = {
    "schema_version",
    "access_scope",
    "capability_id",
    "region_id",
    "contract_signature_sha256",
    "request_signature_sha256",
    "request",
    "source_cell_count",
    "source_cell_ids_sha256",
    "source_complete_cell_count",
    "source_complete_cell_ids_sha256",
    "source_partial_cell_count",
    "source_partial_cell_ids_sha256",
    "source_unobserved_cell_count",
    "source_unobserved_cell_ids_sha256",
    "source_declared_values_sha256",
    "target_domain_cell_count",
    "target_domain_cell_ids_sha256",
    "complete_cell_count",
    "complete_cell_ids_sha256",
    "partial_cell_count",
    "partial_cell_ids_sha256",
    "not_assessed_cell_count",
    "not_assessed_cell_ids_sha256",
    "outside_domain_source_cell_count",
    "outside_domain_source_cell_ids_sha256",
    "target_declared_values_sha256",
    "field_evidence",
    "cells",
    "result_signature_sha256",
}


def _parse_field_value(value: Any) -> TechnologyContextFieldValue:
    raw = _mapping(value, "technology-context field value")
    _exact_keys(raw, _VALUE_KEYS, "technology-context field value")
    field_id = _field_identifier(raw["field_id"], "field value id")
    kind = _exact_text(raw["value_kind"], "field value kind")
    if kind not in TECHNOLOGY_CONTEXT_VALUE_KINDS:
        raise NotImplementedError(f"Unsupported technology-context value kind: {kind}")
    parsed = _typed_value(field_id, raw["value"])
    if parsed is None or parsed.value_kind != kind:
        raise ValueError("Technology-context field value type does not match")
    return parsed


def _parse_cell(value: Any) -> TechnologyContextCell:
    raw = _mapping(value, "technology-context cell")
    _exact_keys(raw, _CELL_KEYS, "technology-context cell")
    values_raw = raw["values"]
    if not isinstance(values_raw, list):
        raise TypeError("Technology-context cell values must be a list")
    values = tuple(_parse_field_value(item) for item in values_raw)
    return TechnologyContextCell(
        cell_id=_exact_text(raw["cell_id"], "technology-context cell id"),
        status=_exact_text(raw["status"], "technology-context cell status"),
        observed_field_count=_count(
            raw["observed_field_count"], "cell observed field count"
        ),
        values=values,
    )


def _parse_field_evidence(value: Any) -> TechnologyContextFieldEvidence:
    raw = _mapping(value, "technology-context field evidence")
    _exact_keys(raw, _FIELD_EVIDENCE_KEYS, "technology-context field evidence")
    kinds_raw = raw["value_kinds"]
    if not isinstance(kinds_raw, list):
        raise TypeError("Technology-context value kinds must be a list")
    kinds = tuple(_exact_text(item, "value kind") for item in kinds_raw)
    if (
        not kinds
        or len(kinds) != len(set(kinds))
        or any(kind not in TECHNOLOGY_CONTEXT_VALUE_KINDS for kind in kinds)
        or kinds != tuple(
            kind for kind in TECHNOLOGY_CONTEXT_VALUE_KINDS if kind in kinds
        )
    ):
        raise ValueError("Technology-context value kinds are not canonical")
    return TechnologyContextFieldEvidence(
        field_id=_field_identifier(raw["field_id"], "field evidence id"),
        value_kinds=kinds,
        source_observed_cell_count=_count(
            raw["source_observed_cell_count"], "source observed field count"
        ),
        target_observed_cell_count=_count(
            raw["target_observed_cell_count"], "target observed field count"
        ),
    )


def parse_technology_context_result(value: Any) -> TechnologyContextResult:
    raw = _mapping(value, "technology-context result")
    _exact_keys(raw, _RESULT_KEYS, "technology-context result")
    cells_raw = raw["cells"]
    evidence_raw = raw["field_evidence"]
    if not isinstance(cells_raw, list) or not isinstance(evidence_raw, list):
        raise TypeError("Technology-context result arrays are invalid")
    result = TechnologyContextResult(
        schema_version=_exact_text(raw["schema_version"], "result schema"),
        access_scope=_exact_text(raw["access_scope"], "result access scope"),
        capability_id=_exact_text(raw["capability_id"], "result capability"),
        region_id=_identifier(raw["region_id"], "result region"),
        contract_signature_sha256=_digest(
            raw["contract_signature_sha256"], "result contract signature"
        ),
        request_signature_sha256=_digest(
            raw["request_signature_sha256"], "result request signature"
        ),
        request=parse_technology_context_request(raw["request"]),
        source_cell_count=_count(raw["source_cell_count"], "source cell count"),
        source_cell_ids_sha256=_digest(
            raw["source_cell_ids_sha256"], "source cell-id digest"
        ),
        source_complete_cell_count=_count(
            raw["source_complete_cell_count"], "source complete cell count"
        ),
        source_complete_cell_ids_sha256=_digest(
            raw["source_complete_cell_ids_sha256"],
            "source complete cell-id digest",
        ),
        source_partial_cell_count=_count(
            raw["source_partial_cell_count"], "source partial cell count"
        ),
        source_partial_cell_ids_sha256=_digest(
            raw["source_partial_cell_ids_sha256"],
            "source partial cell-id digest",
        ),
        source_unobserved_cell_count=_count(
            raw["source_unobserved_cell_count"], "source unobserved cell count"
        ),
        source_unobserved_cell_ids_sha256=_digest(
            raw["source_unobserved_cell_ids_sha256"],
            "source unobserved cell-id digest",
        ),
        source_declared_values_sha256=_digest(
            raw["source_declared_values_sha256"], "source values digest"
        ),
        target_domain_cell_count=_count(
            raw["target_domain_cell_count"], "target domain cell count"
        ),
        target_domain_cell_ids_sha256=_digest(
            raw["target_domain_cell_ids_sha256"], "target domain cell-id digest"
        ),
        complete_cell_count=_count(raw["complete_cell_count"], "complete cell count"),
        complete_cell_ids_sha256=_digest(
            raw["complete_cell_ids_sha256"], "complete cell-id digest"
        ),
        partial_cell_count=_count(raw["partial_cell_count"], "partial cell count"),
        partial_cell_ids_sha256=_digest(
            raw["partial_cell_ids_sha256"], "partial cell-id digest"
        ),
        not_assessed_cell_count=_count(
            raw["not_assessed_cell_count"], "not-assessed cell count"
        ),
        not_assessed_cell_ids_sha256=_digest(
            raw["not_assessed_cell_ids_sha256"], "not-assessed cell-id digest"
        ),
        outside_domain_source_cell_count=_count(
            raw["outside_domain_source_cell_count"],
            "outside-domain source cell count",
        ),
        outside_domain_source_cell_ids_sha256=_digest(
            raw["outside_domain_source_cell_ids_sha256"],
            "outside-domain source cell-id digest",
        ),
        target_declared_values_sha256=_digest(
            raw["target_declared_values_sha256"], "target values digest"
        ),
        field_evidence=tuple(_parse_field_evidence(item) for item in evidence_raw),
        cells=tuple(_parse_cell(item) for item in cells_raw),
        result_signature_sha256=_digest(
            raw["result_signature_sha256"], "result signature"
        ),
    )
    validate_technology_context_result(result)
    return result


def validate_technology_context_result(result: TechnologyContextResult) -> None:
    if not isinstance(result, TechnologyContextResult):
        raise TypeError("result must be a TechnologyContextResult")
    if result.schema_version != TECHNOLOGY_CONTEXT_RESULT_SCHEMA_VERSION:
        raise NotImplementedError(
            "Unsupported technology-context result schema version: "
            f"{result.schema_version}"
        )
    request = parse_technology_context_request(result.request.as_dict())
    if (
        result.access_scope != request.access_scope
        or result.capability_id != request.capability_id
        or result.region_id != request.region_id
        or result.contract_signature_sha256
        != request.contract_signature_sha256
        or result.request_signature_sha256 != request.request_signature_sha256
    ):
        raise ValueError("Technology-context result identity does not match request")
    if result.source_cell_count != (
        result.source_complete_cell_count
        + result.source_partial_cell_count
        + result.source_unobserved_cell_count
    ):
        raise ValueError("Technology-context source coverage does not balance")
    if result.source_cell_count != request.source_expected_cell_count:
        raise ValueError("Technology-context source count drifted from request")
    if result.source_cell_ids_sha256 != request.source_cell_ids_sha256:
        raise ValueError("Technology-context source cell digest drifted from request")
    if result.target_domain_cell_count != (
        result.complete_cell_count
        + result.partial_cell_count
        + result.not_assessed_cell_count
    ):
        raise ValueError("Technology-context target coverage does not balance")
    if result.target_domain_cell_count != request.domain_expected_cell_count:
        raise ValueError("Technology-context target count drifted from request")
    if result.target_domain_cell_ids_sha256 != request.domain_cell_ids_sha256:
        raise ValueError("Technology-context target digest drifted from request")
    if len(result.cells) != result.target_domain_cell_count:
        raise ValueError("Technology-context result cell count is invalid")
    cell_ids = tuple(cell.cell_id for cell in result.cells)
    if cell_ids != tuple(sorted(cell_ids)) or len(cell_ids) != len(set(cell_ids)):
        raise ValueError("Technology-context result cells must be unique and sorted")
    if _id_digest(cell_ids) != result.target_domain_cell_ids_sha256:
        raise ValueError("Technology-context result cell ids do not match evidence")
    by_status = {status: [] for status in TECHNOLOGY_CONTEXT_CELL_STATUSES}
    field_target_counts = {field: 0 for field in request.context_fields}
    field_kinds = {field: set() for field in request.context_fields}
    for cell in result.cells:
        if not h3.is_valid_cell(cell.cell_id) or h3.get_resolution(
            cell.cell_id
        ) != request.domain_resolution:
            raise ValueError("Technology-context result contains invalid H3 ids")
        if cell.status not in TECHNOLOGY_CONTEXT_CELL_STATUSES:
            raise ValueError("Technology-context result cell status is invalid")
        value_fields = tuple(value.field_id for value in cell.values)
        canonical_fields = tuple(
            field for field in request.context_fields if field in value_fields
        )
        if (
            value_fields != canonical_fields
            or len(value_fields) != len(set(value_fields))
            or cell.observed_field_count != len(cell.values)
            or cell.status != _status(cell.values, len(request.context_fields))
        ):
            raise ValueError("Technology-context cell values are not canonical")
        for value in cell.values:
            parsed_value = _typed_value(value.field_id, value.value)
            if parsed_value != value or value.value_kind not in TECHNOLOGY_CONTEXT_VALUE_KINDS:
                raise ValueError("Technology-context cell value is invalid")
            field_target_counts[value.field_id] += 1
            field_kinds[value.field_id].add(value.value_kind)
        by_status[cell.status].append(cell.cell_id)
    status_evidence = (
        ("complete", result.complete_cell_count, result.complete_cell_ids_sha256),
        ("partial", result.partial_cell_count, result.partial_cell_ids_sha256),
        (
            "not_assessed",
            result.not_assessed_cell_count,
            result.not_assessed_cell_ids_sha256,
        ),
    )
    for status, expected_count, expected_digest in status_evidence:
        if len(by_status[status]) != expected_count or _id_digest(
            by_status[status]
        ) != expected_digest:
            raise ValueError(f"Technology-context {status} evidence drifted")
    if result.target_declared_values_sha256 != _declared_values_digest(
        (cell.cell_id, cell.values) for cell in result.cells
    ):
        raise ValueError("Technology-context target value digest drifted")
    if tuple(item.field_id for item in result.field_evidence) != request.context_fields:
        raise ValueError("Technology-context field evidence order drifted")
    for item in result.field_evidence:
        if item.target_observed_cell_count != field_target_counts[item.field_id]:
            raise ValueError("Technology-context target field count drifted")
        target_kinds = tuple(
            kind
            for kind in TECHNOLOGY_CONTEXT_VALUE_KINDS
            if kind in field_kinds[item.field_id]
        )
        if any(kind not in item.value_kinds for kind in target_kinds):
            raise ValueError("Technology-context target value kinds drifted")
        if (
            item.source_observed_cell_count < item.target_observed_cell_count
            or item.source_observed_cell_count > result.source_cell_count
        ):
            raise ValueError("Technology-context source field count is invalid")
    for value in (
        result.source_complete_cell_ids_sha256,
        result.source_partial_cell_ids_sha256,
        result.source_unobserved_cell_ids_sha256,
        result.source_declared_values_sha256,
        result.outside_domain_source_cell_ids_sha256,
    ):
        _digest(value, "technology-context result evidence digest")
    if result.outside_domain_source_cell_count > result.source_cell_count:
        raise ValueError("Technology-context outside-domain count is invalid")
    expected_signature = _canonical_sha256(_result_signature_payload(result))
    if result.result_signature_sha256 != expected_signature:
        raise ValueError("Technology-context result signature does not match")


def _authorize_catalog_request(
    contract: TechnologyContextCapabilityContract,
    request: TechnologyContextRequest,
) -> None:
    validate_technology_context_request_from_contract(contract, request)
    region = catalogs.load_region(request.region_id)
    if str(region.get("region_id") or "").strip().lower() != request.region_id:
        raise PermissionError(
            "Technology-context request region is not catalog-authorized"
        )
    from .workspace import load_review_access, load_workspace_profile

    profile = load_workspace_profile(request.region_id)
    if request.capability_id not in profile.capabilities:
        raise PermissionError(
            "Technology-context capability is not declared by the workspace"
        )
    scope_kind, _ = request.access_scope.split(":", 1)
    if scope_kind == "product":
        landing_card = region.get("landing_card")
        behavior_reference = region.get("behavior_reference")
        if not isinstance(landing_card, Mapping) or not isinstance(
            behavior_reference, Mapping
        ):
            raise PermissionError(
                f"Product technology-context access is disabled for {request.region_id}"
            )
        try:
            validate_product_access_dimensions(
                lifecycle=region.get("status"),
                behavior_reference_status=behavior_reference.get("status"),
                landing_card_enabled=landing_card.get("enabled"),
            )
        except (TypeError, ValueError) as exc:
            raise PermissionError(
                f"Product technology-context access is disabled for {request.region_id}"
            ) from exc
        return
    try:
        access = load_review_access(request.region_id)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        raise PermissionError(
            f"Review technology-context access is disabled for {request.region_id}"
        ) from exc
    if (
        access.mode != "review"
        or access.surface != "shared_workspace"
        or access.requires_environment_allowlist is not True
        or request.capability_id not in access.allowed_capabilities
    ):
        raise PermissionError(
            "Technology-context capability is not allowed by review access"
        )


def _run_current_catalog_technology_context(contract, request) -> TechnologyContextResult:
    from .context_runtime import catalog_context_runtime_declared, load_catalog_context_inputs

    if catalog_context_runtime_declared(contract.region_id):
        inputs = load_catalog_context_inputs(contract.region_id)
        return run_technology_context_request_from_values(contract, request,
            domain_ids=inputs.support_cell_ids,
            source_values=inputs.technology_context.source_values())
    return run_technology_context_request_from_contract(contract, request)


def run_catalog_technology_context_request(
    request: TechnologyContextRequest,
) -> TechnologyContextResult:
    if not isinstance(request, TechnologyContextRequest):
        raise TypeError("request must be a TechnologyContextRequest")
    contract = load_catalog_technology_context_contract(request.region_id)
    _authorize_catalog_request(contract, request)
    return _run_current_catalog_technology_context(contract, request)


def probe_catalog_technology_context(region_id: str) -> TechnologyContextProbe:
    try:
        contract = load_catalog_technology_context_contract(region_id)
    except (FileNotFoundError, KeyError) as exc:
        return TechnologyContextProbe("missing_manifest", str(exc))
    except NotImplementedError as exc:
        return TechnologyContextProbe("not_implemented", str(exc))
    except (OSError, TypeError, ValueError) as exc:
        return TechnologyContextProbe("not_validated", str(exc))
    try:
        request = build_technology_context_request_from_contract(
            contract,
            access_scope=f"review:{contract.region_id}",
        )
        result = _run_current_catalog_technology_context(contract, request)
    except NotImplementedError as exc:
        return TechnologyContextProbe("not_implemented", str(exc))
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        return TechnologyContextProbe("missing_data", str(exc))
    observed = result.complete_cell_count + result.partial_cell_count
    if observed == 0:
        return TechnologyContextProbe(
            "not_validated",
            "Technology-context consumer ran, but no target cell has declared values.",
        )
    return TechnologyContextProbe(
        "technically_validated",
        "Technology-context contract, request, source, coverage and typed result "
        f"are verified ({observed}/{result.target_domain_cell_count} observed cells; "
        f"{result.contract_signature_sha256[:12]}).",
    )


__all__ = [
    "TECHNOLOGY_CONTEXT_ACCESS_SCOPE_KINDS",
    "TECHNOLOGY_CONTEXT_CAPABILITY_ID",
    "TECHNOLOGY_CONTEXT_CELL_STATUSES",
    "TECHNOLOGY_CONTEXT_CONTRACT_SCHEMA_VERSION",
    "TECHNOLOGY_CONTEXT_REQUEST_SCHEMA_VERSION",
    "TECHNOLOGY_CONTEXT_RESULT_SCHEMA_VERSION",
    "TECHNOLOGY_CONTEXT_VALUE_KINDS",
    "TechnologyContextCapabilityContract",
    "TechnologyContextCell",
    "TechnologyContextDomainContract",
    "TechnologyContextFieldEvidence",
    "TechnologyContextFieldValue",
    "TechnologyContextProbe",
    "TechnologyContextRequest",
    "TechnologyContextResult",
    "build_catalog_technology_context_request",
    "build_technology_context_capability_contract",
    "build_technology_context_request_from_contract",
    "load_catalog_technology_context_contract",
    "parse_technology_context_request",
    "parse_technology_context_result",
    "probe_catalog_technology_context",
    "run_catalog_technology_context_request",
    "run_technology_context_request_from_contract",
    "technology_context_contract_signature",
    "validate_technology_context_capability_contract",
    "validate_technology_context_request_from_contract",
    "validate_technology_context_result",
]
