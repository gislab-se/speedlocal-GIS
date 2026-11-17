from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Protocol

import h3

from . import catalogs
from .access_policy import ACCESS_TRUST_CLASSIFICATIONS
from .contracts import analysis_domain_contract
from .paths import resolve_source_path


LANDSCAPE_SCHEMA_VERSION = "1.0"
LANDSCAPE_VIEW_REQUEST_SCHEMA_VERSION = "1.0"
LANDSCAPE_VIEW_RESULT_SCHEMA_VERSION = "1.0"
LANDSCAPE_CAPABILITY_ID = "workspace.landscape"
LANDSCAPE_ACCESS_SCOPE_KINDS = ("product", "review")
LANDSCAPE_COMPILED_STATUS = "compiled_unvalidated"
LANDSCAPE_COMPATIBILITY_STATUS = "hand_maintained_compatibility"
LANDSCAPE_PURPOSE = "display_review_only"
LANDSCAPE_NUMERICAL_USE = "forbidden"
LANDSCAPE_ROLLUP_RULE = "dominant_area_then_legend_order"
LANDSCAPE_COMPATIBILITY_ROLLUP_RULE = (
    "dominant_child_count_then_legend_order"
)
LANDSCAPE_ROLLUP_RULES = (
    LANDSCAPE_ROLLUP_RULE,
    LANDSCAPE_COMPATIBILITY_ROLLUP_RULE,
)
LANDSCAPE_MISSING_POLICY = "explicit_not_assessed"
LANDSCAPE_OUTSIDE_DOMAIN_POLICY = "ignore_with_evidence"
LANDSCAPE_TRUST_CLASSIFICATIONS = ACCESS_TRUST_CLASSIFICATIONS
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ResolvedLandscapeAsset(Protocol):
    provider: str
    provider_path: str
    format: str
    path: Path
    bytes: int
    sha256: str


@dataclass(frozen=True)
class LandscapeSourceReference:
    kind: str
    context_id: str
    relationship: str


@dataclass(frozen=True)
class LandscapeAssetContract:
    provider: str
    path: str
    format: str
    sha256: str
    id_field: str
    cell_kind: str
    resolution: int


@dataclass(frozen=True)
class LandscapeDomainContract:
    role: str
    domain_id: str
    provider: str
    path: str
    format: str
    sha256: str
    id_field: str
    area_field: str
    area_unit: str
    cell_kind: str
    resolution: int
    expected_cell_count: int
    cell_ids_sha256: str


@dataclass(frozen=True)
class LandscapeLegendItem:
    value_id: str
    label: str
    color: str

    def as_dict(self) -> dict[str, str]:
        return {
            "value_id": self.value_id,
            "label": self.label,
            "color": self.color,
        }


@dataclass(frozen=True)
class LandscapeViewContract:
    view_id: str
    label: str
    value_field: str
    value_semantics: str
    legend: tuple[LandscapeLegendItem, ...]


@dataclass(frozen=True)
class LandscapeTrustContract:
    classification: str
    regional_acceptance: bool
    allowed_use: str
    decision_support: bool


@dataclass(frozen=True)
class LandscapeReviewAsset:
    provider: str
    path: str
    sha256: str


@dataclass(frozen=True)
class LandscapeReviewViewEvidence:
    view_id: str
    value_counts: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class LandscapeReviewEvidence:
    status: str
    method: str
    review_date: str
    source_manifest: LandscapeReviewAsset
    handoff: LandscapeReviewAsset
    accepted_scope: str
    accepted_cell_count: int
    full_reference_cell_count: int
    excluded_reference_cell_count: int
    views: tuple[LandscapeReviewViewEvidence, ...]
    boundary_gap_behavior_accepted: bool
    decision: str


@dataclass(frozen=True)
class LandscapeViewEvidence:
    view_id: str
    observed_cell_count: int
    not_assessed_cell_count: int
    observed_cell_ids_sha256: str
    observed_value_ids: tuple[str, ...]
    observed_value_ids_sha256: str


@dataclass(frozen=True)
class LandscapeCoverageEvidence:
    domain_cell_count: int
    domain_cell_ids_sha256: str
    covered_domain_cell_count: int
    uncovered_domain_cell_count: int
    outside_domain_source_cell_count: int
    covered_domain_cell_ids_sha256: str
    uncovered_domain_cell_ids_sha256: str
    outside_domain_source_cell_ids_sha256: str
    coverage_fraction: float


@dataclass(frozen=True)
class LandscapeGeneratedEvidence:
    source_bytes: int
    field_names: tuple[str, ...]
    field_names_sha256: str
    feature_count: int
    source_cell_count: int
    source_cell_ids_sha256: str
    view_ids_sha256: str
    views: tuple[LandscapeViewEvidence, ...]
    coverage: LandscapeCoverageEvidence


@dataclass(frozen=True)
class LandscapeContract:
    schema_version: str
    region_id: str
    landscape_id: str
    label: str
    status: str
    purpose: str
    numerical_use: str
    source_reference: LandscapeSourceReference
    source: LandscapeAssetContract
    domain: LandscapeDomainContract
    views: tuple[LandscapeViewContract, ...]
    default_view_id: str
    product_default_visible: bool
    rollup_resolutions: tuple[int, ...]
    rollup_rule: str
    missing_policy: str
    outside_domain_policy: str
    missing_label: str
    provenance: tuple[tuple[str, str], ...]
    trust: LandscapeTrustContract
    review_evidence: LandscapeReviewEvidence | None
    generated_evidence: LandscapeGeneratedEvidence


@dataclass(frozen=True)
class LandscapeViewRequest:
    schema_version: str
    access_scope: str
    capability_id: str
    region_id: str
    landscape_id: str
    view_id: str
    source_resolution: int
    target_resolution: int
    domain_sha256: str
    contract_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "capability_id": self.capability_id,
            "region_id": self.region_id,
            "landscape_id": self.landscape_id,
            "view_id": self.view_id,
            "source_resolution": self.source_resolution,
            "target_resolution": self.target_resolution,
            "domain_sha256": self.domain_sha256,
            "contract_signature_sha256": self.contract_signature_sha256,
        }


@dataclass(frozen=True)
class LandscapeViewCell:
    cell_id: str
    value_id: str | None
    label: str
    color: str | None
    source_child_count: int
    assessed_child_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "value_id": self.value_id,
            "label": self.label,
            "color": self.color,
            "source_child_count": self.source_child_count,
            "assessed_child_count": self.assessed_child_count,
        }


@dataclass(frozen=True)
class LandscapeViewResult:
    schema_version: str
    request: LandscapeViewRequest
    landscape_label: str
    view_label: str
    value_semantics: str
    legend: tuple[LandscapeLegendItem, ...]
    missing_label: str
    source_resolution: int
    purpose: str
    numerical_use: str
    trust_classification: str
    missing_policy: str
    cells: tuple[LandscapeViewCell, ...]
    feature_collection_json: str
    assessed_cell_count: int
    not_assessed_cell_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request": self.request.as_dict(),
            "landscape_label": self.landscape_label,
            "view_label": self.view_label,
            "value_semantics": self.value_semantics,
            "legend": [item.as_dict() for item in self.legend],
            "missing_label": self.missing_label,
            "source_resolution": self.source_resolution,
            "purpose": self.purpose,
            "numerical_use": self.numerical_use,
            "trust_classification": self.trust_classification,
            "missing_policy": self.missing_policy,
            "cells": [cell.as_dict() for cell in self.cells],
            "feature_collection_json": self.feature_collection_json,
            "assessed_cell_count": self.assessed_cell_count,
            "not_assessed_cell_count": self.not_assessed_cell_count,
        }


@dataclass(frozen=True)
class LandscapeProbe:
    state: str
    detail: str


def _canonical_digest(values: tuple[str, ...] | list[str] | set[str]) -> str:
    return hashlib.sha256(
        "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    ).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    label: str,
    *,
    optional: set[str] | None = None,
) -> None:
    optional = optional or set()
    keys = set(value)
    if not expected.issubset(keys) or keys.difference(expected | optional):
        raise ValueError(
            f"{label} keys drifted: expected={sorted(expected)}, "
            f"optional={sorted(optional)}, actual={sorted(keys)}"
        )


def _text(value: Any, label: str, *, identifier: bool = False) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be an exact non-empty string")
    if identifier and _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a canonical identifier")
    return value


def _digest(value: Any, label: str) -> str:
    text = _text(value, label)
    if _SHA256.fullmatch(text) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return text


def _non_negative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _relative_path(value: Any, label: str) -> str:
    text = _text(value, label)
    if "\\" in text:
        raise ValueError(f"{label} must be a POSIX path")
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} escapes its provider root")
    return text


def _h3_resolution(value: Any, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 15
    ):
        raise ValueError(f"{label} must be an H3 integer from 0 to 15")
    return value


def landscape_contract_signature(contract: LandscapeContract) -> str:
    """Return the deterministic signature of every consumed contract field."""

    if not isinstance(contract, LandscapeContract):
        raise TypeError("contract must be a LandscapeContract")
    payload = json.dumps(
        asdict(contract),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_landscape_view_request_from_contract(
    contract: LandscapeContract,
    *,
    access_scope: str,
    view_id: str | None = None,
    target_resolution: int | None = None,
) -> LandscapeViewRequest:
    """Build one immutable display request from the typed manifest contract.

    ``domain_sha256`` binds the request to the exact declared source domain.
    The target resolution and the full contract signature additionally bind
    every deterministic rollup choice, so persisted requests cannot be
    replayed after either the domain or rollup contract changes.
    """

    if not isinstance(contract, LandscapeContract):
        raise TypeError("contract must be a LandscapeContract")
    scope = str(access_scope).strip().lower()
    scope_parts = scope.split(":", 1)
    if (
        len(scope_parts) != 2
        or scope_parts[0] not in LANDSCAPE_ACCESS_SCOPE_KINDS
        or scope_parts[1] != contract.region_id.lower()
    ):
        raise ValueError(
            "Landscape access_scope must be product:<region> or review:<region>"
        )
    normalized_view_id = _text(
        contract.default_view_id if view_id is None else view_id,
        "landscape request view id",
        identifier=True,
    )
    if normalized_view_id not in {view.view_id for view in contract.views}:
        raise KeyError(f"Unknown landscape view: {normalized_view_id}")
    source_resolution = _h3_resolution(
        contract.source.resolution,
        "landscape source resolution",
    )
    target = (
        source_resolution
        if target_resolution is None
        else _h3_resolution(
            target_resolution,
            "landscape target resolution",
        )
    )
    allowed_resolutions = {
        source_resolution,
        *(int(value) for value in contract.rollup_resolutions),
    }
    if target not in allowed_resolutions:
        raise ValueError(f"Unsupported landscape resolution: {target}")
    if target > source_resolution:
        raise ValueError("Landscape target resolution cannot be finer than source")
    return LandscapeViewRequest(
        schema_version=LANDSCAPE_VIEW_REQUEST_SCHEMA_VERSION,
        access_scope=scope,
        capability_id=LANDSCAPE_CAPABILITY_ID,
        region_id=contract.region_id,
        landscape_id=contract.landscape_id,
        view_id=normalized_view_id,
        source_resolution=source_resolution,
        target_resolution=target,
        domain_sha256=contract.domain.sha256,
        contract_signature_sha256=landscape_contract_signature(contract),
    )


def parse_landscape_view_request(
    value: Mapping[str, Any],
) -> LandscapeViewRequest:
    """Parse persisted landscape state without accepting compatibility fields."""

    raw = _mapping(value, "landscape view request")
    _exact_keys(
        raw,
        {
            "schema_version",
            "access_scope",
            "capability_id",
            "region_id",
            "landscape_id",
            "view_id",
            "source_resolution",
            "target_resolution",
            "domain_sha256",
            "contract_signature_sha256",
        },
        "landscape view request",
    )
    if raw["schema_version"] != LANDSCAPE_VIEW_REQUEST_SCHEMA_VERSION:
        raise ValueError("Unsupported landscape view request schema version")
    access_scope = _text(raw["access_scope"], "landscape access scope")
    region_id = _text(
        raw["region_id"],
        "landscape request region id",
        identifier=True,
    )
    if access_scope != access_scope.lower() or region_id != region_id.lower():
        raise ValueError("Landscape request scope and region must be normalized")
    scope_parts = access_scope.split(":", 1)
    if (
        len(scope_parts) != 2
        or scope_parts[0] not in LANDSCAPE_ACCESS_SCOPE_KINDS
        or scope_parts[1] != region_id
    ):
        raise ValueError("Landscape request access scope is not region-bound")
    capability_id = _text(
        raw["capability_id"],
        "landscape capability id",
    )
    if capability_id != LANDSCAPE_CAPABILITY_ID:
        raise ValueError(
            f"Landscape request capability must be {LANDSCAPE_CAPABILITY_ID}"
        )
    source_resolution = _h3_resolution(
        raw["source_resolution"],
        "landscape request source resolution",
    )
    target_resolution = _h3_resolution(
        raw["target_resolution"],
        "landscape request target resolution",
    )
    if target_resolution > source_resolution:
        raise ValueError("Landscape target resolution cannot be finer than source")
    return LandscapeViewRequest(
        schema_version=LANDSCAPE_VIEW_REQUEST_SCHEMA_VERSION,
        access_scope=access_scope,
        capability_id=capability_id,
        region_id=region_id,
        landscape_id=_text(
            raw["landscape_id"],
            "landscape request landscape id",
            identifier=True,
        ),
        view_id=_text(
            raw["view_id"],
            "landscape request view id",
            identifier=True,
        ),
        source_resolution=source_resolution,
        target_resolution=target_resolution,
        domain_sha256=_digest(
            raw["domain_sha256"],
            "landscape request domain sha256",
        ),
        contract_signature_sha256=_digest(
            raw["contract_signature_sha256"],
            "landscape request contract signature",
        ),
    )


def validate_landscape_view_request_from_contract(
    contract: LandscapeContract,
    request: LandscapeViewRequest,
) -> LandscapeViewRequest:
    """Rebuild a request and reject any identity, domain or signature drift."""

    if not isinstance(request, LandscapeViewRequest):
        raise TypeError("request must be a LandscapeViewRequest")
    rebuilt = build_landscape_view_request_from_contract(
        contract,
        access_scope=request.access_scope,
        view_id=request.view_id,
        target_resolution=request.target_resolution,
    )
    if rebuilt != request:
        raise ValueError("Landscape view request drifted from its manifest contract")
    return request


def _landscape_feature_collection_json(
    cells: tuple[LandscapeViewCell, ...],
) -> str:
    features: list[dict[str, Any]] = []
    for cell in cells:
        boundary = list(h3.cell_to_boundary(cell.cell_id))
        ring = [[float(lng), float(lat)] for lat, lng in boundary]
        if ring:
            ring.append(list(ring[0]))
        features.append(
            {
                "type": "Feature",
                "properties": cell.as_dict(),
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )
    return json.dumps(
        {"type": "FeatureCollection", "features": features},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def parse_landscape_view_result(
    value: Mapping[str, Any],
) -> LandscapeViewResult:
    """Parse one presentation-complete immutable result strictly."""

    raw = _mapping(value, "landscape view result")
    _exact_keys(
        raw,
        {
            "schema_version",
            "request",
            "landscape_label",
            "view_label",
            "value_semantics",
            "legend",
            "missing_label",
            "source_resolution",
            "purpose",
            "numerical_use",
            "trust_classification",
            "missing_policy",
            "cells",
            "feature_collection_json",
            "assessed_cell_count",
            "not_assessed_cell_count",
        },
        "landscape view result",
    )
    if raw["schema_version"] != LANDSCAPE_VIEW_RESULT_SCHEMA_VERSION:
        raise ValueError("Unsupported landscape view result schema version")
    request = parse_landscape_view_request(
        _mapping(raw["request"], "landscape result request")
    )
    source_resolution = _h3_resolution(
        raw["source_resolution"],
        "landscape result source resolution",
    )
    if source_resolution != request.source_resolution:
        raise ValueError("Landscape result source resolution drifted from request")
    semantics = _text(raw["value_semantics"], "landscape result semantics")
    if semantics != "categorical_id":
        raise ValueError(f"Unsupported landscape value semantics: {semantics}")
    legend = _parse_legend(raw["legend"], request.view_id)
    legend_by_id = {item.value_id: item for item in legend}
    missing_label = _text(raw["missing_label"], "landscape missing label")
    purpose = _text(raw["purpose"], "landscape result purpose")
    numerical_use = _text(
        raw["numerical_use"],
        "landscape result numerical use",
    )
    missing_policy = _text(
        raw["missing_policy"],
        "landscape result missing policy",
    )
    if purpose != LANDSCAPE_PURPOSE:
        raise ValueError("Landscape result must remain display/review only")
    if numerical_use != LANDSCAPE_NUMERICAL_USE:
        raise ValueError("Landscape result numerical use must remain forbidden")
    if missing_policy != LANDSCAPE_MISSING_POLICY:
        raise ValueError("Landscape result missing policy drifted")
    trust_classification = _text(
        raw["trust_classification"],
        "landscape result trust classification",
    )
    if trust_classification not in LANDSCAPE_TRUST_CLASSIFICATIONS:
        raise ValueError("Landscape result trust classification is not canonical")
    raw_cells = raw["cells"]
    if not isinstance(raw_cells, list) or not raw_cells:
        raise ValueError("Landscape result cells must be a non-empty list")
    cells: list[LandscapeViewCell] = []
    seen_cell_ids: set[str] = set()
    for index, value_cell in enumerate(raw_cells):
        cell = _mapping(value_cell, f"landscape result cell {index}")
        _exact_keys(
            cell,
            {
                "cell_id",
                "value_id",
                "label",
                "color",
                "source_child_count",
                "assessed_child_count",
            },
            f"landscape result cell {index}",
        )
        cell_id = _text(cell["cell_id"], "landscape result cell id")
        if (
            cell_id in seen_cell_ids
            or not h3.is_valid_cell(cell_id)
            or int(h3.get_resolution(cell_id)) != request.target_resolution
        ):
            raise ValueError("Landscape result cell identity/resolution is invalid")
        seen_cell_ids.add(cell_id)
        value_id_raw = cell["value_id"]
        if value_id_raw is None:
            value_id = None
            expected_label = missing_label
            expected_color = None
        else:
            value_id = _text(value_id_raw, "landscape result value id")
            legend_item = legend_by_id.get(value_id)
            if legend_item is None:
                raise ValueError("Landscape result value is absent from the legend")
            expected_label = legend_item.label
            expected_color = legend_item.color
        label = _text(cell["label"], "landscape result cell label")
        color = cell["color"]
        if color is not None and (
            not isinstance(color, str) or _COLOR.fullmatch(color) is None
        ):
            raise ValueError("Landscape result cell color must be null or #RRGGBB")
        source_children = _non_negative_int(
            cell["source_child_count"],
            "landscape result source child count",
        )
        assessed_children = _non_negative_int(
            cell["assessed_child_count"],
            "landscape result assessed child count",
        )
        if (
            source_children < 1
            or assessed_children > source_children
            or (value_id is None) != (assessed_children == 0)
            or label != expected_label
            or color != expected_color
        ):
            raise ValueError("Landscape result cell presentation/counts drifted")
        cells.append(
            LandscapeViewCell(
                cell_id=cell_id,
                value_id=value_id,
                label=label,
                color=color,
                source_child_count=source_children,
                assessed_child_count=assessed_children,
            )
        )
    if tuple(cell.cell_id for cell in cells) != tuple(
        sorted(cell.cell_id for cell in cells)
    ):
        raise ValueError("Landscape result cells must use deterministic order")
    feature_collection_json = _text(
        raw["feature_collection_json"],
        "landscape feature collection",
    )
    if feature_collection_json != _landscape_feature_collection_json(tuple(cells)):
        raise ValueError("Landscape result geometry/presentation payload drifted")
    assessed_count = _non_negative_int(
        raw["assessed_cell_count"],
        "landscape assessed cell count",
    )
    not_assessed_count = _non_negative_int(
        raw["not_assessed_cell_count"],
        "landscape not-assessed cell count",
    )
    expected_assessed = sum(cell.value_id is not None for cell in cells)
    if (
        assessed_count != expected_assessed
        or not_assessed_count != len(cells) - expected_assessed
    ):
        raise ValueError("Landscape result summary counts drifted from cells")
    return LandscapeViewResult(
        schema_version=LANDSCAPE_VIEW_RESULT_SCHEMA_VERSION,
        request=request,
        landscape_label=_text(
            raw["landscape_label"],
            "landscape result label",
        ),
        view_label=_text(raw["view_label"], "landscape result view label"),
        value_semantics=semantics,
        legend=legend,
        missing_label=missing_label,
        source_resolution=source_resolution,
        purpose=purpose,
        numerical_use=numerical_use,
        trust_classification=trust_classification,
        missing_policy=missing_policy,
        cells=tuple(cells),
        feature_collection_json=feature_collection_json,
        assessed_cell_count=assessed_count,
        not_assessed_cell_count=not_assessed_count,
    )


def _parse_legend(value: Any, view_id: str) -> tuple[LandscapeLegendItem, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"Landscape view {view_id!r} needs a legend")
    items: list[LandscapeLegendItem] = []
    for index, raw in enumerate(value):
        item = _mapping(raw, f"landscape legend {view_id}/{index}")
        _exact_keys(
            item,
            {"value_id", "label", "color"},
            f"landscape legend {view_id}/{index}",
        )
        color = _text(item["color"], "landscape legend color")
        if _COLOR.fullmatch(color) is None:
            raise ValueError("Landscape legend color must be #RRGGBB")
        items.append(
            LandscapeLegendItem(
                value_id=_text(item["value_id"], "landscape legend value"),
                label=_text(item["label"], "landscape legend label"),
                color=color,
            )
        )
    if len({item.value_id for item in items}) != len(items):
        raise ValueError(f"Landscape view {view_id!r} has duplicate legend values")
    return tuple(items)


def _parse_view(value: Any) -> LandscapeViewContract:
    raw = _mapping(value, "landscape view")
    _exact_keys(
        raw,
        {"view_id", "label", "value_field", "value_semantics", "legend"},
        "landscape view",
    )
    view_id = _text(raw["view_id"], "landscape view id", identifier=True)
    semantics = _text(raw["value_semantics"], "landscape value semantics")
    if semantics != "categorical_id":
        raise ValueError(f"Unsupported landscape value semantics: {semantics}")
    return LandscapeViewContract(
        view_id=view_id,
        label=_text(raw["label"], "landscape view label"),
        value_field=_text(raw["value_field"], "landscape value field"),
        value_semantics=semantics,
        legend=_parse_legend(raw["legend"], view_id),
    )


def _parse_view_evidence(value: Any) -> LandscapeViewEvidence:
    raw = _mapping(value, "landscape view evidence")
    _exact_keys(
        raw,
        {
            "view_id",
            "observed_cell_count",
            "not_assessed_cell_count",
            "observed_cell_ids_sha256",
            "observed_value_ids",
            "observed_value_ids_sha256",
        },
        "landscape view evidence",
    )
    observed_values = raw["observed_value_ids"]
    if not isinstance(observed_values, list) or any(
        not isinstance(item, str) or not item or item != item.strip()
        for item in observed_values
    ):
        raise ValueError("Landscape observed value ids must be exact strings")
    values = tuple(observed_values)
    if values != tuple(sorted(set(values))):
        raise ValueError("Landscape observed value ids must be unique and sorted")
    return LandscapeViewEvidence(
        view_id=_text(raw["view_id"], "landscape evidence view id", identifier=True),
        observed_cell_count=_non_negative_int(
            raw["observed_cell_count"], "landscape observed cell count"
        ),
        not_assessed_cell_count=_non_negative_int(
            raw["not_assessed_cell_count"], "landscape not-assessed cell count"
        ),
        observed_cell_ids_sha256=_digest(
            raw["observed_cell_ids_sha256"], "landscape observed cell digest"
        ),
        observed_value_ids=values,
        observed_value_ids_sha256=_digest(
            raw["observed_value_ids_sha256"], "landscape value id digest"
        ),
    )


def _parse_coverage(value: Any) -> LandscapeCoverageEvidence:
    raw = _mapping(value, "landscape coverage evidence")
    _exact_keys(
        raw,
        {
            "domain_cell_count",
            "domain_cell_ids_sha256",
            "covered_domain_cell_count",
            "uncovered_domain_cell_count",
            "outside_domain_source_cell_count",
            "covered_domain_cell_ids_sha256",
            "uncovered_domain_cell_ids_sha256",
            "outside_domain_source_cell_ids_sha256",
            "coverage_fraction",
        },
        "landscape coverage evidence",
    )
    fraction = raw["coverage_fraction"]
    if (
        isinstance(fraction, bool)
        or not isinstance(fraction, (int, float))
        or not math.isfinite(float(fraction))
        or not 0.0 <= float(fraction) <= 1.0
    ):
        raise ValueError("Landscape coverage fraction must be within 0..1")
    return LandscapeCoverageEvidence(
        domain_cell_count=_non_negative_int(
            raw["domain_cell_count"], "landscape domain count"
        ),
        domain_cell_ids_sha256=_digest(
            raw["domain_cell_ids_sha256"], "landscape domain id digest"
        ),
        covered_domain_cell_count=_non_negative_int(
            raw["covered_domain_cell_count"], "landscape covered-domain count"
        ),
        uncovered_domain_cell_count=_non_negative_int(
            raw["uncovered_domain_cell_count"],
            "landscape uncovered-domain count",
        ),
        outside_domain_source_cell_count=_non_negative_int(
            raw["outside_domain_source_cell_count"],
            "landscape outside-domain count",
        ),
        covered_domain_cell_ids_sha256=_digest(
            raw["covered_domain_cell_ids_sha256"],
            "landscape covered-domain digest",
        ),
        uncovered_domain_cell_ids_sha256=_digest(
            raw["uncovered_domain_cell_ids_sha256"],
            "landscape uncovered-domain digest",
        ),
        outside_domain_source_cell_ids_sha256=_digest(
            raw["outside_domain_source_cell_ids_sha256"],
            "landscape outside-domain digest",
        ),
        coverage_fraction=float(fraction),
    )


def _parse_evidence(value: Any) -> LandscapeGeneratedEvidence:
    raw = _mapping(value, "landscape generated evidence")
    _exact_keys(
        raw,
        {
            "source_bytes",
            "field_names",
            "field_names_sha256",
            "feature_count",
            "source_cell_count",
            "source_cell_ids_sha256",
            "view_ids_sha256",
            "views",
            "coverage",
        },
        "landscape generated evidence",
    )
    field_names_raw = raw["field_names"]
    if not isinstance(field_names_raw, list) or any(
        not isinstance(item, str) or not item or item != item.strip()
        for item in field_names_raw
    ):
        raise ValueError("Landscape field inventory must contain exact strings")
    field_names = tuple(field_names_raw)
    if field_names != tuple(sorted(set(field_names))):
        raise ValueError("Landscape field inventory must be unique and sorted")
    views_raw = raw["views"]
    if not isinstance(views_raw, list) or not views_raw:
        raise ValueError("Landscape evidence needs per-view rows")
    return LandscapeGeneratedEvidence(
        source_bytes=_non_negative_int(raw["source_bytes"], "landscape source bytes"),
        field_names=field_names,
        field_names_sha256=_digest(
            raw["field_names_sha256"], "landscape field inventory digest"
        ),
        feature_count=_non_negative_int(
            raw["feature_count"], "landscape feature count"
        ),
        source_cell_count=_non_negative_int(
            raw["source_cell_count"], "landscape source cell count"
        ),
        source_cell_ids_sha256=_digest(
            raw["source_cell_ids_sha256"], "landscape source id digest"
        ),
        view_ids_sha256=_digest(
            raw["view_ids_sha256"], "landscape view id digest"
        ),
        views=tuple(_parse_view_evidence(item) for item in views_raw),
        coverage=_parse_coverage(raw["coverage"]),
    )


def _parse_review_asset(value: Any, label: str) -> LandscapeReviewAsset:
    raw = _mapping(value, label)
    _exact_keys(raw, {"provider", "path", "sha256"}, label)
    provider = _text(raw["provider"], f"{label} provider")
    if provider not in {"repo", "v2_archive"}:
        raise ValueError(f"{label} provider must be repo or v2_archive")
    return LandscapeReviewAsset(
        provider=provider,
        path=_relative_path(raw["path"], f"{label} path"),
        sha256=_digest(raw["sha256"], f"{label} sha256"),
    )


def _parse_review_view(value: Any) -> LandscapeReviewViewEvidence:
    raw = _mapping(value, "landscape review view evidence")
    _exact_keys(
        raw,
        {"view_id", "value_counts"},
        "landscape review view evidence",
    )
    view_id = _text(
        raw["view_id"], "landscape review view id", identifier=True
    )
    counts_raw = _mapping(
        raw["value_counts"], f"landscape review {view_id} value counts"
    )
    if not counts_raw:
        raise ValueError(f"Landscape review view {view_id!r} needs value counts")
    counts: list[tuple[str, int]] = []
    for value_id, count in counts_raw.items():
        exact_value_id = _text(value_id, "landscape review value id")
        exact_count = _non_negative_int(
            count, f"landscape review count for {exact_value_id}"
        )
        if exact_count < 1:
            raise ValueError("Landscape review value counts must be positive")
        counts.append((exact_value_id, exact_count))
    counts.sort(key=lambda item: item[0])
    return LandscapeReviewViewEvidence(
        view_id=view_id,
        value_counts=tuple(counts),
    )


def _parse_review_evidence(value: Any) -> LandscapeReviewEvidence:
    raw = _mapping(value, "landscape review evidence")
    _exact_keys(
        raw,
        {
            "status",
            "method",
            "review_date",
            "source_manifest",
            "handoff",
            "accepted_scope",
            "accepted_cell_count",
            "full_reference_cell_count",
            "excluded_reference_cell_count",
            "views",
            "boundary_gap_behavior_accepted",
            "decision",
        },
        "landscape review evidence",
    )
    if raw["status"] != "accepted_display_behavior":
        raise ValueError("Landscape review evidence is not accepted display behavior")
    if raw["method"] != "qgis_visual_review":
        raise ValueError("Landscape review evidence method is unsupported")
    review_date = _text(raw["review_date"], "landscape review date")
    if _ISO_DATE.fullmatch(review_date) is None:
        raise ValueError("Landscape review date must be YYYY-MM-DD")
    accepted_count = _non_negative_int(
        raw["accepted_cell_count"], "landscape accepted review count"
    )
    full_count = _non_negative_int(
        raw["full_reference_cell_count"], "landscape full reference count"
    )
    excluded_count = _non_negative_int(
        raw["excluded_reference_cell_count"],
        "landscape excluded reference count",
    )
    if (
        accepted_count < 1
        or full_count < accepted_count
        or accepted_count + excluded_count != full_count
    ):
        raise ValueError("Landscape review extent counts are inconsistent")
    views_raw = raw["views"]
    if not isinstance(views_raw, list) or not views_raw:
        raise ValueError("Landscape review evidence needs view counts")
    views = tuple(_parse_review_view(item) for item in views_raw)
    if len({item.view_id for item in views}) != len(views):
        raise ValueError("Landscape review evidence duplicates view ids")
    boundary_accepted = raw["boundary_gap_behavior_accepted"]
    if boundary_accepted is not True:
        raise ValueError("Landscape boundary/gap review must be explicitly accepted")
    return LandscapeReviewEvidence(
        status="accepted_display_behavior",
        method="qgis_visual_review",
        review_date=review_date,
        source_manifest=_parse_review_asset(
            raw["source_manifest"], "landscape review source manifest"
        ),
        handoff=_parse_review_asset(
            raw["handoff"], "landscape review handoff"
        ),
        accepted_scope=_text(
            raw["accepted_scope"],
            "landscape accepted review scope",
            identifier=True,
        ),
        accepted_cell_count=accepted_count,
        full_reference_cell_count=full_count,
        excluded_reference_cell_count=excluded_count,
        views=views,
        boundary_gap_behavior_accepted=True,
        decision=_text(raw["decision"], "landscape review decision"),
    )


def landscape_contract(value: Mapping[str, Any]) -> LandscapeContract:
    raw = _mapping(value, "landscape manifest")
    _exact_keys(
        raw,
        {
            "schema_version",
            "region_id",
            "landscape_id",
            "label",
            "status",
            "purpose",
            "numerical_use",
            "source_reference",
            "source",
            "domain",
            "views",
            "default_view_id",
            "product_default_visible",
            "rollup_resolutions",
            "rollup_rule",
            "missing_policy",
            "outside_domain_policy",
            "missing_label",
            "provenance",
            "trust",
            "generated_evidence",
        },
        "landscape manifest",
        optional={"review_evidence"},
    )
    if raw["schema_version"] != LANDSCAPE_SCHEMA_VERSION:
        raise ValueError("Unsupported landscape manifest schema version")
    status = _text(raw["status"], "landscape status")
    if status not in {
        LANDSCAPE_COMPILED_STATUS,
        LANDSCAPE_COMPATIBILITY_STATUS,
    }:
        raise ValueError("Landscape status is unsupported")
    if raw["purpose"] != LANDSCAPE_PURPOSE:
        raise ValueError("Landscape purpose must remain display/review-only")
    if raw["numerical_use"] != LANDSCAPE_NUMERICAL_USE:
        raise ValueError("Landscape may not become numerical context authority")

    source_reference_raw = _mapping(
        raw["source_reference"], "landscape source reference"
    )
    _exact_keys(
        source_reference_raw,
        {"kind", "context_id", "relationship"},
        "landscape source reference",
    )
    source_kind = _text(source_reference_raw["kind"], "landscape source kind")
    if source_kind not in {"technology_context", "independent_asset"}:
        raise ValueError(f"Unsupported landscape source kind: {source_kind}")
    if source_reference_raw["relationship"] != "display_projection_only":
        raise ValueError("Landscape source relationship must be display-only")
    source_reference = LandscapeSourceReference(
        kind=source_kind,
        context_id=_text(
            source_reference_raw["context_id"],
            "landscape context id",
            identifier=True,
        ),
        relationship="display_projection_only",
    )

    source_raw = _mapping(raw["source"], "landscape source")
    _exact_keys(
        source_raw,
        {"provider", "path", "format", "sha256", "id_field", "cell_kind", "resolution"},
        "landscape source",
    )
    if source_raw["format"] != "geojson":
        raise NotImplementedError("Landscape source format is not implemented")
    if source_raw["id_field"] != "hex_id" or source_raw["cell_kind"] != "h3":
        raise ValueError("Landscape source must use hex_id H3 cells")
    resolution = source_raw["resolution"]
    if isinstance(resolution, bool) or not isinstance(resolution, int) or not 0 <= resolution <= 15:
        raise ValueError("Landscape source resolution is invalid")
    source = LandscapeAssetContract(
        provider=_text(source_raw["provider"], "landscape source provider"),
        path=_relative_path(source_raw["path"], "landscape source path"),
        format="geojson",
        sha256=_digest(source_raw["sha256"], "landscape source sha256"),
        id_field="hex_id",
        cell_kind="h3",
        resolution=resolution,
    )
    if source.provider not in {"repo", "v2_archive", "generated_runtime"}:
        raise ValueError("Landscape source provider is not registered")

    domain_raw = _mapping(raw["domain"], "landscape domain")
    _exact_keys(
        domain_raw,
        {
            "role",
            "domain_id",
            "provider",
            "path",
            "format",
            "sha256",
            "id_field",
            "area_field",
            "area_unit",
            "cell_kind",
            "resolution",
            "expected_cell_count",
            "cell_ids_sha256",
        },
        "landscape domain",
    )
    if domain_raw["role"] != "standard_analysis_domain":
        raise ValueError("Landscape must bind the standard display domain")
    if (
        domain_raw["format"] != "geojson"
        or domain_raw["id_field"] != "hex_id"
        or domain_raw["cell_kind"] != "h3"
    ):
        raise ValueError("Landscape domain needs the exact H3 area contract")
    area_field = _text(domain_raw["area_field"], "landscape domain area field")
    area_unit = _text(domain_raw["area_unit"], "landscape domain area unit")
    if area_unit not in {"m2", "km2"}:
        raise ValueError("Landscape domain area unit must be m2 or km2")
    if domain_raw["resolution"] != resolution:
        raise ValueError("Landscape source and domain resolutions differ")
    domain = LandscapeDomainContract(
        role="standard_analysis_domain",
        domain_id=_text(domain_raw["domain_id"], "landscape domain id", identifier=True),
        provider=_text(domain_raw["provider"], "landscape domain provider"),
        path=_relative_path(domain_raw["path"], "landscape domain path"),
        format="geojson",
        sha256=_digest(domain_raw["sha256"], "landscape domain sha256"),
        id_field="hex_id",
        area_field=area_field,
        area_unit=area_unit,
        cell_kind="h3",
        resolution=resolution,
        expected_cell_count=_non_negative_int(
            domain_raw["expected_cell_count"], "landscape domain cell count"
        ),
        cell_ids_sha256=_digest(
            domain_raw["cell_ids_sha256"], "landscape domain cell digest"
        ),
    )
    if domain.provider not in {"repo", "v2_archive", "generated_runtime"}:
        raise ValueError("Landscape domain provider is not registered")
    if domain.expected_cell_count < 1:
        raise ValueError("Landscape domain must contain at least one cell")

    views_raw = raw["views"]
    if not isinstance(views_raw, list) or not views_raw:
        raise ValueError("Landscape needs at least one declared view")
    views = tuple(_parse_view(item) for item in views_raw)
    if len({view.view_id for view in views}) != len(views):
        raise ValueError("Landscape view ids must be unique")
    default_view_id = _text(
        raw["default_view_id"],
        "landscape default view id",
        identifier=True,
    )
    if default_view_id not in {view.view_id for view in views}:
        raise ValueError("Landscape default view must be explicitly declared")
    product_default_visible = raw["product_default_visible"]
    if not isinstance(product_default_visible, bool):
        raise TypeError("Landscape product_default_visible must be boolean")

    rollups_raw = raw["rollup_resolutions"]
    if not isinstance(rollups_raw, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in rollups_raw
    ):
        raise ValueError("Landscape rollup resolutions must be integers")
    rollups = tuple(rollups_raw)
    if (
        len(set(rollups)) != len(rollups)
        or rollups != tuple(sorted(rollups, reverse=True))
        or any(item < 0 or item >= resolution for item in rollups)
    ):
        raise ValueError("Landscape rollups must be unique descending parents")
    if raw["rollup_rule"] not in LANDSCAPE_ROLLUP_RULES:
        raise NotImplementedError("Landscape rollup rule is not implemented")
    rollup_rule = str(raw["rollup_rule"])
    if raw["missing_policy"] != LANDSCAPE_MISSING_POLICY:
        raise ValueError("Landscape missing policy must be explicit_not_assessed")
    if raw["outside_domain_policy"] != LANDSCAPE_OUTSIDE_DOMAIN_POLICY:
        raise ValueError("Landscape outside-domain policy drifted")

    provenance_raw = _mapping(raw["provenance"], "landscape provenance")
    required_provenance = {
        "authority",
        "dataset_name",
        "dataset_version",
        "snapshot_date",
        "license",
        "provenance_status",
        "derivation",
    }
    _exact_keys(
        provenance_raw,
        required_provenance,
        "landscape provenance",
        optional={"license_url"},
    )
    provenance: list[tuple[str, str]] = []
    for key in sorted(provenance_raw):
        provenance.append((key, _text(provenance_raw[key], f"landscape provenance {key}")))

    trust_raw = _mapping(raw["trust"], "landscape trust")
    _exact_keys(
        trust_raw,
        {"classification", "regional_acceptance", "allowed_use", "decision_support"},
        "landscape trust",
    )
    classification = _text(
        trust_raw["classification"], "landscape trust classification"
    )
    if classification not in LANDSCAPE_TRUST_CLASSIFICATIONS:
        raise ValueError("Landscape trust classification is not canonical")
    regional_acceptance = trust_raw["regional_acceptance"]
    if not isinstance(regional_acceptance, bool):
        raise TypeError("Landscape regional_acceptance must be boolean")
    if regional_acceptance != (classification == "regionally_accepted"):
        raise ValueError("Landscape trust and regional acceptance disagree")
    if (
        trust_raw["allowed_use"] != LANDSCAPE_PURPOSE
        or trust_raw["decision_support"] is not False
    ):
        raise ValueError("Landscape trust may authorize display review only")
    trust = LandscapeTrustContract(
        classification=classification,
        regional_acceptance=regional_acceptance,
        allowed_use=LANDSCAPE_PURPOSE,
        decision_support=False,
    )
    review_evidence = (
        _parse_review_evidence(raw["review_evidence"])
        if "review_evidence" in raw
        else None
    )
    if status == LANDSCAPE_COMPATIBILITY_STATUS and review_evidence is None:
        raise ValueError(
            "A hand-maintained landscape compatibility contract needs review evidence"
        )
    evidence = _parse_evidence(raw["generated_evidence"])
    if tuple(item.view_id for item in evidence.views) != tuple(
        view.view_id for view in views
    ):
        raise ValueError("Landscape view evidence order or identity drifted")
    if evidence.view_ids_sha256 != _canonical_digest(
        tuple(view.view_id for view in views)
    ):
        raise ValueError("Landscape view id digest drifted")
    if evidence.field_names_sha256 != _canonical_digest(evidence.field_names):
        raise ValueError("Landscape field inventory digest drifted")
    if evidence.source_cell_count != evidence.feature_count:
        raise ValueError("Landscape source feature and cell counts differ")
    coverage = evidence.coverage
    if (
        coverage.domain_cell_count != domain.expected_cell_count
        or coverage.domain_cell_ids_sha256 != domain.cell_ids_sha256
        or coverage.covered_domain_cell_count
        + coverage.uncovered_domain_cell_count
        != coverage.domain_cell_count
    ):
        raise ValueError("Landscape generated domain coverage drifted")
    expected_fraction = (
        coverage.covered_domain_cell_count / coverage.domain_cell_count
    )
    if not math.isclose(
        coverage.coverage_fraction,
        expected_fraction,
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise ValueError("Landscape coverage fraction drifted")
    for item in evidence.views:
        if (
            item.observed_cell_count + item.not_assessed_cell_count
            != domain.expected_cell_count
            or item.observed_value_ids_sha256
            != _canonical_digest(item.observed_value_ids)
        ):
            raise ValueError(f"Landscape view evidence drifted: {item.view_id}")
    if review_evidence is not None:
        if review_evidence.accepted_cell_count != domain.expected_cell_count:
            raise ValueError("Landscape review extent differs from its domain")
        if tuple(item.view_id for item in review_evidence.views) != tuple(
            view.view_id for view in views
        ):
            raise ValueError("Landscape review view identity/order drifted")
        review_views = {
            item.view_id: item for item in review_evidence.views
        }
        for view in views:
            reviewed_counts = review_views[view.view_id].value_counts
            if tuple(value_id for value_id, _count in reviewed_counts) != tuple(
                sorted(item.value_id for item in view.legend)
            ):
                raise ValueError(
                    f"Landscape review legend values drifted: {view.view_id}"
                )
            if sum(count for _value_id, count in reviewed_counts) != (
                review_evidence.accepted_cell_count
            ):
                raise ValueError(
                    f"Landscape review value counts drifted: {view.view_id}"
                )

    return LandscapeContract(
        schema_version=LANDSCAPE_SCHEMA_VERSION,
        region_id=_text(raw["region_id"], "landscape region id", identifier=True),
        landscape_id=_text(
            raw["landscape_id"], "landscape contract id", identifier=True
        ),
        label=_text(raw["label"], "landscape label"),
        status=status,
        purpose=LANDSCAPE_PURPOSE,
        numerical_use=LANDSCAPE_NUMERICAL_USE,
        source_reference=source_reference,
        source=source,
        domain=domain,
        views=views,
        default_view_id=default_view_id,
        product_default_visible=product_default_visible,
        rollup_resolutions=rollups,
        rollup_rule=rollup_rule,
        missing_policy=LANDSCAPE_MISSING_POLICY,
        outside_domain_policy=LANDSCAPE_OUTSIDE_DOMAIN_POLICY,
        missing_label=_text(raw["missing_label"], "landscape missing label"),
        provenance=tuple(provenance),
        trust=trust,
        review_evidence=review_evidence,
        generated_evidence=evidence,
    )


def _read_feature_rows(
    path: Path,
    *,
    expected_sha256: str,
    id_field: str,
    resolution: int,
    value_fields: tuple[str, ...] = (),
    area_field: str | None = None,
) -> tuple[dict[str, Mapping[str, Any]], tuple[str, ...]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    if _sha256_path(path) != expected_sha256:
        raise ValueError(f"Landscape artifact checksum drifted: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Landscape GeoJSON cannot be read: {exc}") from exc
    return landscape_feature_rows_from_payload(
        payload, id_field=id_field, resolution=resolution,
        value_fields=value_fields, area_field=area_field,
    )


def landscape_feature_rows_from_payload(
    payload: Mapping[str, Any],
    *,
    id_field: str,
    resolution: int,
    value_fields: tuple[str, ...] = (),
    area_field: str | None = None,
) -> tuple[dict[str, Mapping[str, Any]], tuple[str, ...]]:
    """Validate original property rows with the same rules as the file reader."""
    if not isinstance(payload, Mapping) or payload.get("type") != "FeatureCollection":
        raise ValueError("Landscape artifact must be a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Landscape artifact must contain features")
    rows: dict[str, Mapping[str, Any]] = {}
    field_names: set[str] = set()
    for index, feature in enumerate(features):
        properties = (
            feature.get("properties") if isinstance(feature, Mapping) else None
        )
        if not isinstance(properties, Mapping):
            raise ValueError(f"Landscape feature {index} has no properties")
        field_names.update(str(key) for key in properties)
        raw_id = properties.get(id_field)
        if (
            not isinstance(raw_id, str)
            or not raw_id
            or raw_id != raw_id.strip()
            or raw_id != raw_id.lower()
            or not h3.is_valid_cell(raw_id)
        ):
            raise ValueError(f"Landscape feature {index} has an invalid H3 id")
        if h3.get_resolution(raw_id) != resolution:
            raise ValueError(f"Landscape cell {raw_id!r} is not R{resolution}")
        if raw_id in rows:
            raise ValueError(f"Landscape artifact duplicates H3 id {raw_id}")
        for field in value_fields:
            if field not in properties:
                raise ValueError(f"Landscape source is missing field {field!r}")
            raw_value = properties.get(field)
            if raw_value is not None and (
                not isinstance(raw_value, str)
                or not raw_value
                or raw_value != raw_value.strip()
            ):
                raise ValueError(
                    f"Landscape field {field!r} must use exact string ids or null"
                )
        if area_field is not None:
            area = properties.get(area_field)
            if (
                isinstance(area, bool)
                or not isinstance(area, (int, float))
                or not math.isfinite(float(area))
                or float(area) <= 0.0
            ):
                raise ValueError(f"Landscape domain cell {raw_id} has invalid area")
        rows[raw_id] = properties
    return rows, tuple(sorted(field_names))


def _evidence_mapping(value: LandscapeGeneratedEvidence) -> dict[str, Any]:
    return {
        "source_bytes": value.source_bytes,
        "field_names": list(value.field_names),
        "field_names_sha256": value.field_names_sha256,
        "feature_count": value.feature_count,
        "source_cell_count": value.source_cell_count,
        "source_cell_ids_sha256": value.source_cell_ids_sha256,
        "view_ids_sha256": value.view_ids_sha256,
        "views": [
            {
                "view_id": item.view_id,
                "observed_cell_count": item.observed_cell_count,
                "not_assessed_cell_count": item.not_assessed_cell_count,
                "observed_cell_ids_sha256": item.observed_cell_ids_sha256,
                "observed_value_ids": list(item.observed_value_ids),
                "observed_value_ids_sha256": item.observed_value_ids_sha256,
            }
            for item in value.views
        ],
        "coverage": {
            "domain_cell_count": value.coverage.domain_cell_count,
            "domain_cell_ids_sha256": value.coverage.domain_cell_ids_sha256,
            "covered_domain_cell_count": value.coverage.covered_domain_cell_count,
            "uncovered_domain_cell_count": value.coverage.uncovered_domain_cell_count,
            "outside_domain_source_cell_count": value.coverage.outside_domain_source_cell_count,
            "covered_domain_cell_ids_sha256": value.coverage.covered_domain_cell_ids_sha256,
            "uncovered_domain_cell_ids_sha256": value.coverage.uncovered_domain_cell_ids_sha256,
            "outside_domain_source_cell_ids_sha256": value.coverage.outside_domain_source_cell_ids_sha256,
            "coverage_fraction": value.coverage.coverage_fraction,
        },
    }


def _compute_evidence(
    *,
    source_path: Path,
    source: LandscapeAssetContract,
    domain_path: Path,
    domain: LandscapeDomainContract,
    views: tuple[LandscapeViewContract, ...],
) -> tuple[
    LandscapeGeneratedEvidence,
    dict[str, Mapping[str, Any]],
    dict[str, Mapping[str, Any]],
]:
    value_fields = tuple(view.value_field for view in views)
    source_rows, field_names = _read_feature_rows(
        source_path,
        expected_sha256=source.sha256,
        id_field=source.id_field,
        resolution=source.resolution,
        value_fields=value_fields,
    )
    domain_rows, _domain_fields = _read_feature_rows(
        domain_path,
        expected_sha256=domain.sha256,
        id_field=domain.id_field,
        resolution=domain.resolution,
        area_field=domain.area_field,
    )
    evidence = landscape_evidence_from_rows(
        source_bytes=source_path.stat().st_size,
        source_rows=source_rows, field_names=field_names,
        domain_rows=domain_rows, domain=domain, views=views,
    )
    return evidence, source_rows, domain_rows


def landscape_evidence_from_rows(
    *,
    source_bytes: int,
    source_rows: Mapping[str, Mapping[str, Any]],
    field_names: tuple[str, ...],
    domain_rows: Mapping[str, Mapping[str, Any]],
    domain: LandscapeDomainContract,
    views: tuple[LandscapeViewContract, ...],
) -> LandscapeGeneratedEvidence:
    """Compute existing landscape coverage/view evidence from verified rows."""
    domain_ids = set(domain_rows)
    source_ids = set(source_rows)
    if len(domain_ids) != domain.expected_cell_count:
        raise ValueError("Landscape domain cell count drifted")
    if _canonical_digest(domain_ids) != domain.cell_ids_sha256:
        raise ValueError("Landscape domain cell id digest drifted")
    covered = domain_ids.intersection(source_ids)
    uncovered = domain_ids.difference(source_ids)
    outside = source_ids.difference(domain_ids)
    if not covered:
        raise ValueError("Landscape source does not overlap its declared domain")

    view_evidence: list[LandscapeViewEvidence] = []
    for view in views:
        legend_ids = {item.value_id for item in view.legend}
        observed_ids = {
            cell_id
            for cell_id in domain_ids
            if cell_id in source_rows
            and source_rows[cell_id].get(view.value_field) is not None
        }
        observed_values = tuple(
            sorted(
                {
                    str(source_rows[cell_id][view.value_field])
                    for cell_id in observed_ids
                }
            )
        )
        unknown_values = set(observed_values).difference(legend_ids)
        if unknown_values:
            raise ValueError(
                f"Landscape view {view.view_id!r} has values outside its legend: "
                f"{sorted(unknown_values)}"
            )
        if not observed_values:
            raise ValueError(
                f"Landscape view {view.view_id!r} has no observed values"
            )
        view_evidence.append(
            LandscapeViewEvidence(
                view_id=view.view_id,
                observed_cell_count=len(observed_ids),
                not_assessed_cell_count=len(domain_ids) - len(observed_ids),
                observed_cell_ids_sha256=_canonical_digest(observed_ids),
                observed_value_ids=observed_values,
                observed_value_ids_sha256=_canonical_digest(observed_values),
            )
        )
    evidence = LandscapeGeneratedEvidence(
        source_bytes=source_bytes,
        field_names=field_names,
        field_names_sha256=_canonical_digest(field_names),
        feature_count=len(source_rows),
        source_cell_count=len(source_rows),
        source_cell_ids_sha256=_canonical_digest(source_ids),
        view_ids_sha256=_canonical_digest(tuple(view.view_id for view in views)),
        views=tuple(view_evidence),
        coverage=LandscapeCoverageEvidence(
            domain_cell_count=len(domain_ids),
            domain_cell_ids_sha256=_canonical_digest(domain_ids),
            covered_domain_cell_count=len(covered),
            uncovered_domain_cell_count=len(uncovered),
            outside_domain_source_cell_count=len(outside),
            covered_domain_cell_ids_sha256=_canonical_digest(covered),
            uncovered_domain_cell_ids_sha256=_canonical_digest(uncovered),
            outside_domain_source_cell_ids_sha256=_canonical_digest(outside),
            coverage_fraction=len(covered) / len(domain_ids),
        ),
    )
    return evidence


def materialize_landscape_manifest(
    declaration: Mapping[str, Any],
    *,
    region_id: str,
    source_asset: ResolvedLandscapeAsset,
    domain_artifact: Mapping[str, Any],
    domain_cell_ids_sha256: str,
    domain_path: Path,
) -> dict[str, Any]:
    """Build one complete display-only manifest from human policy and data."""

    if declaration.get("state") != "declared":
        raise ValueError("Landscape declaration is unavailable")
    if source_asset.format != "geojson":
        raise NotImplementedError(
            f"Landscape source format={source_asset.format} is not implemented"
        )
    domain_reference = _mapping(
        declaration["domain_reference"], "landscape domain reference"
    )
    if domain_reference.get("role") != "standard_analysis_domain":
        raise NotImplementedError("Only the standard display domain is implemented")
    if domain_artifact.get("format", "geojson") != "geojson":
        raise NotImplementedError("Landscape domain format is not implemented")
    views = tuple(_parse_view(item) for item in declaration["views"])
    source = LandscapeAssetContract(
        provider=source_asset.provider,
        path=source_asset.provider_path,
        format="geojson",
        sha256=source_asset.sha256,
        id_field=str(declaration["h3_id_field"]),
        cell_kind=str(declaration["cell_kind"]),
        resolution=int(declaration["resolution"]),
    )
    domain = LandscapeDomainContract(
        role="standard_analysis_domain",
        domain_id=str(domain_reference["domain_id"]),
        provider=str(domain_artifact["provider"]),
        path=str(domain_artifact["path"]),
        format="geojson",
        sha256=str(domain_artifact["sha256"]),
        id_field=str(domain_artifact["id_field"]),
        area_field=str(domain_artifact["area_field"]),
        area_unit=str(domain_artifact["area_unit"]),
        cell_kind=str(domain_artifact["cell_kind"]),
        resolution=int(domain_artifact["resolution"]),
        expected_cell_count=int(domain_artifact["expected_cell_count"]),
        cell_ids_sha256=str(domain_cell_ids_sha256),
    )
    evidence, _source_rows, _domain_rows = _compute_evidence(
        source_path=source_asset.path,
        source=source,
        domain_path=domain_path,
        domain=domain,
        views=views,
    )
    source_reference = _mapping(
        declaration["source_reference"], "landscape source reference"
    )
    value = {
        "schema_version": LANDSCAPE_SCHEMA_VERSION,
        "region_id": region_id,
        "landscape_id": declaration["landscape_id"],
        "label": declaration["label"],
        "status": LANDSCAPE_COMPILED_STATUS,
        "purpose": declaration["purpose"],
        "numerical_use": declaration["numerical_use"],
        "source_reference": {
            "kind": source_reference["kind"],
            "context_id": source_reference["context_id"],
            "relationship": "display_projection_only",
        },
        "source": {
            "provider": source.provider,
            "path": source.path,
            "format": source.format,
            "sha256": source.sha256,
            "id_field": source.id_field,
            "cell_kind": source.cell_kind,
            "resolution": source.resolution,
        },
        "domain": {
            "role": domain.role,
            "domain_id": domain.domain_id,
            "provider": domain.provider,
            "path": domain.path,
            "format": domain.format,
            "sha256": domain.sha256,
            "id_field": domain.id_field,
            "area_field": domain.area_field,
            "area_unit": domain.area_unit,
            "cell_kind": domain.cell_kind,
            "resolution": domain.resolution,
            "expected_cell_count": domain.expected_cell_count,
            "cell_ids_sha256": domain.cell_ids_sha256,
        },
        "views": [
            {
                "view_id": view.view_id,
                "label": view.label,
                "value_field": view.value_field,
                "value_semantics": view.value_semantics,
                "legend": [
                    {
                        "value_id": item.value_id,
                        "label": item.label,
                        "color": item.color,
                    }
                    for item in view.legend
                ],
            }
            for view in views
        ],
        "default_view_id": declaration["default_view_id"],
        "product_default_visible": declaration["product_default_visible"],
        "rollup_resolutions": list(declaration["rollup_resolutions"]),
        "rollup_rule": declaration["rollup_rule"],
        "missing_policy": declaration["missing_policy"],
        "outside_domain_policy": declaration["outside_domain_policy"],
        "missing_label": declaration["missing_label"],
        "provenance": dict(declaration["provenance"]),
        "trust": dict(declaration["trust"]),
        "generated_evidence": _evidence_mapping(evidence),
    }
    landscape_contract(value)
    return value


def _resolved_data_paths(
    contract: LandscapeContract,
) -> tuple[Path, Path]:
    return (
        resolve_source_path(contract.source.provider, contract.source.path),
        resolve_source_path(contract.domain.provider, contract.domain.path),
    )


def validate_landscape_data(
    contract: LandscapeContract,
    *,
    source_path: Path | None = None,
    domain_path: Path | None = None,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    if source_path is None or domain_path is None:
        resolved_source, resolved_domain = _resolved_data_paths(contract)
        source_path = source_path or resolved_source
        domain_path = domain_path or resolved_domain
    evidence, source_rows, domain_rows = _compute_evidence(
        source_path=source_path,
        source=contract.source,
        domain_path=domain_path,
        domain=contract.domain,
        views=contract.views,
    )
    validate_landscape_generated_evidence(contract, evidence)
    review = contract.review_evidence
    if review is not None:
        for label, asset in (
            ("source manifest", review.source_manifest),
            ("handoff", review.handoff),
        ):
            review_path = resolve_source_path(asset.provider, asset.path)
            if not review_path.is_file():
                raise FileNotFoundError(review_path)
            if _sha256_path(review_path) != asset.sha256:
                raise ValueError(
                    f"Landscape review {label} checksum drifted: {review_path}"
                )
        validate_landscape_review_counts(contract, source_rows, domain_rows)
    return source_rows, domain_rows


def validate_landscape_generated_evidence(
    contract: LandscapeContract, evidence: LandscapeGeneratedEvidence,
) -> None:
    if _evidence_mapping(evidence) != _evidence_mapping(contract.generated_evidence):
        raise ValueError("Landscape generated evidence drifted from live data")


def validate_landscape_review_counts(
    contract: LandscapeContract,
    source_rows: Mapping[str, Mapping[str, Any]],
    domain_rows: Mapping[str, Mapping[str, Any]],
) -> None:
    """Retain the accepted class counts without resolving archived documents."""
    review = contract.review_evidence
    if review is not None:
        views = {view.view_id: view for view in contract.views}
        domain_ids = set(domain_rows)
        for reviewed_view in review.views:
            view = views[reviewed_view.view_id]
            live_counts: dict[str, int] = {}
            for cell_id in domain_ids:
                raw_value = source_rows.get(cell_id, {}).get(view.value_field)
                if raw_value is not None:
                    value_id = str(raw_value)
                    live_counts[value_id] = live_counts.get(value_id, 0) + 1
            if tuple(sorted(live_counts.items())) != reviewed_view.value_counts:
                raise ValueError(
                    f"Landscape reviewed value counts drifted: {view.view_id}"
                )


def build_landscape_view_from_contract(
    contract: LandscapeContract,
    request: LandscapeViewRequest,
) -> LandscapeViewResult:
    validate_landscape_view_request_from_contract(contract, request)
    views = {view.view_id: view for view in contract.views}
    view = views.get(request.view_id)
    if view is None:
        raise KeyError(f"Unknown landscape view: {request.view_id}")
    source_rows, domain_rows = validate_landscape_data(contract)
    return build_landscape_view_from_validated_rows(
        contract, request, source_rows=source_rows, domain_rows=domain_rows,
    )


def build_landscape_view_from_validated_rows(
    contract: LandscapeContract,
    request: LandscapeViewRequest,
    *,
    source_rows: Mapping[str, Mapping[str, Any]],
    domain_rows: Mapping[str, Mapping[str, Any]],
) -> LandscapeViewResult:
    """Use the existing view/rollup algorithm after input validation."""
    validate_landscape_view_request_from_contract(contract, request)
    views = {view.view_id: view for view in contract.views}
    view = views.get(request.view_id)
    if view is None:
        raise KeyError(f"Unknown landscape view: {request.view_id}")
    legend = {item.value_id: item for item in view.legend}
    legend_order = {
        item.value_id: index for index, item in enumerate(view.legend)
    }
    buckets: dict[str, list[str]] = {}
    for cell_id in domain_rows:
        target_id = (
            cell_id
            if request.target_resolution == contract.source.resolution
            else str(h3.cell_to_parent(cell_id, request.target_resolution))
        )
        buckets.setdefault(target_id, []).append(cell_id)
    cells: list[LandscapeViewCell] = []
    for target_id in sorted(buckets):
        child_ids = tuple(sorted(buckets[target_id]))
        score_by_value: dict[str, float] = {}
        assessed_children = 0
        for child_id in child_ids:
            raw_value = (
                source_rows.get(child_id, {}).get(view.value_field)
                if child_id in source_rows
                else None
            )
            if raw_value is None:
                continue
            value_id = str(raw_value)
            assessed_children += 1
            weight = (
                float(domain_rows[child_id][contract.domain.area_field])
                if contract.rollup_rule == LANDSCAPE_ROLLUP_RULE
                else 1.0
            )
            score_by_value[value_id] = score_by_value.get(value_id, 0.0) + weight
        selected_value = (
            min(
                score_by_value,
                key=lambda value_id: (
                    -score_by_value[value_id],
                    legend_order[value_id],
                    value_id,
                ),
            )
            if score_by_value
            else None
        )
        legend_item = legend.get(selected_value) if selected_value else None
        cells.append(
            LandscapeViewCell(
                cell_id=target_id,
                value_id=selected_value,
                label=(
                    legend_item.label
                    if legend_item is not None
                    else contract.missing_label
                ),
                color=legend_item.color if legend_item is not None else None,
                source_child_count=len(child_ids),
                assessed_child_count=assessed_children,
            )
        )
    assessed = sum(cell.value_id is not None for cell in cells)
    return LandscapeViewResult(
        schema_version=LANDSCAPE_VIEW_RESULT_SCHEMA_VERSION,
        request=request,
        landscape_label=contract.label,
        view_label=view.label,
        value_semantics=view.value_semantics,
        legend=view.legend,
        missing_label=contract.missing_label,
        source_resolution=contract.source.resolution,
        purpose=contract.purpose,
        numerical_use=contract.numerical_use,
        trust_classification=contract.trust.classification,
        missing_policy=contract.missing_policy,
        cells=tuple(cells),
        feature_collection_json=_landscape_feature_collection_json(tuple(cells)),
        assessed_cell_count=assessed,
        not_assessed_cell_count=len(cells) - assessed,
    )


def _domain_artifact_matches(
    domain: LandscapeDomainContract,
    artifact: Any,
) -> bool:
    return bool(
        artifact is not None
        and domain.provider == artifact.provider
        and domain.path == artifact.path
        and domain.sha256 == artifact.sha256
        and domain.id_field == artifact.id_field
        and domain.area_field == artifact.area_field
        and domain.area_unit == artifact.area_unit
        and domain.cell_kind == artifact.cell_kind
        and domain.resolution == artifact.resolution
        and domain.expected_cell_count == artifact.expected_cell_count
    )


def _manifest_declares_compatibility_domain(
    *,
    root: Path,
    manifest_path: Path,
    region_id: str,
    domain: LandscapeDomainContract,
) -> bool:
    """Follow repo-owned analysis inheritance to an exact domain declaration."""

    seen: set[Path] = set()
    current = manifest_path.resolve()
    while True:
        if current == root or root not in current.parents or current in seen:
            raise ValueError("Landscape analysis-domain declaration is unsafe")
        seen.add(current)
        try:
            raw = json.loads(current.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Landscape analysis-domain declaration cannot be read: {exc}"
            ) from exc
        manifest = _mapping(raw, "landscape analysis-domain declaration")
        declared_raw = manifest.get("analysis_domain")
        if declared_raw is not None:
            if (
                manifest.get("region_id") != region_id
                or manifest.get("analysis_id") != domain.domain_id
            ):
                return False
            return _domain_artifact_matches(
                domain,
                analysis_domain_contract(declared_raw),
            )
        extends = manifest.get("extends")
        if not isinstance(extends, str) or not extends or extends != extends.strip():
            return False
        current = (root / _relative_path(
            extends, "landscape analysis manifest inheritance"
        )).resolve()


def _catalog_declares_landscape_domain(
    region_id: str,
    region: Mapping[str, Any],
    domain: LandscapeDomainContract,
) -> bool:
    geography = catalogs.load_region_geography(region_id)
    declared_domain = geography.analysis_domains.get(domain.domain_id)
    if declared_domain is not None:
        return bool(
            declared_domain.purpose == "standard_group_analysis"
            and declared_domain.domain_scope == "standard_constraints"
            and _domain_artifact_matches(domain, declared_domain.artifacts)
            and domain.cell_ids_sha256
            == declared_domain.cell_ids_sha256.get(domain.resolution)
        )

    analysis_manifests = region.get("analysis_manifests")
    if not isinstance(analysis_manifests, Mapping) or not analysis_manifests:
        return False
    root = catalogs.repo_root().resolve()
    matched = False
    for manifest_value in analysis_manifests.values():
        if (
            not isinstance(manifest_value, str)
            or not manifest_value
            or manifest_value != manifest_value.strip()
        ):
            raise ValueError("Landscape analysis manifest path must be exact")
        manifest_path = (
            root / _relative_path(
                manifest_value, "landscape analysis manifest path"
            )
        ).resolve()
        matched = _manifest_declares_compatibility_domain(
            root=root,
            manifest_path=manifest_path,
            region_id=region_id,
            domain=domain,
        ) or matched
    return matched


def _region_landscape_trust_ceiling(
    region: Mapping[str, Any],
    contract: LandscapeContract,
) -> str:
    declared = str(region.get("data_status") or "")
    if declared in LANDSCAPE_TRUST_CLASSIFICATIONS:
        return declared
    reference = region.get("behavior_reference")
    if (
        contract.review_evidence is not None
        and isinstance(reference, Mapping)
        and reference.get("status") == "authoritative"
        and reference.get("source") == "frozen_v2"
        and reference.get("frozen_v2_parity") is True
    ):
        return "regionally_accepted"
    raise ValueError("Region trust is not canonical")


def load_landscape_contract(region_id: str) -> LandscapeContract:
    normalized = _text(region_id, "landscape catalog region", identifier=True)
    region = catalogs.load_region(normalized)
    manifest_value = region.get("landscape_manifest")
    if not isinstance(manifest_value, str) or not manifest_value:
        raise KeyError(f"Landscape manifest is not configured for {normalized}")
    if manifest_value != manifest_value.strip():
        raise ValueError("Landscape manifest path must be exact")
    root = catalogs.repo_root().resolve()
    path = (root / _relative_path(manifest_value, "landscape manifest path")).resolve()
    if path == root or root not in path.parents:
        raise ValueError("Landscape manifest escapes repository")
    if not path.is_file():
        raise FileNotFoundError(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Landscape manifest cannot be read: {exc}") from exc
    contract = landscape_contract(_mapping(raw, "landscape manifest"))
    if contract.region_id != normalized:
        raise ValueError("Landscape manifest region identity mismatch")
    region_trust = _region_landscape_trust_ceiling(region, contract)
    if LANDSCAPE_TRUST_CLASSIFICATIONS.index(
        contract.trust.classification
    ) > LANDSCAPE_TRUST_CLASSIFICATIONS.index(region_trust):
        raise ValueError("Landscape trust exceeds region trust")
    if not _catalog_declares_landscape_domain(
        normalized,
        region,
        contract.domain,
    ):
        raise ValueError(
            "Landscape domain binding differs from the exact standard analysis domain"
        )
    return contract


def _current_catalog_landscape_rows(
    contract: LandscapeContract,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    """Acquire only the current verified context and standard display inputs."""
    from .context_runtime import catalog_context_runtime_declared, load_catalog_context_inputs
    from .sources import read_analysis_domain_input

    if not catalog_context_runtime_declared(contract.region_id):
        raise ValueError("Landscape catalog requires the declared regional context runtime")
    inputs = load_catalog_context_inputs(contract.region_id)
    scope = inputs.inputs.scope
    if scope.region_id != contract.region_id or inputs.landscape is None:
        raise ValueError("Current landscape context belongs to another region or is missing")
    datasets = tuple(item for item in inputs.inputs.datasets if item.kind == "landscape")
    if len(datasets) != 1 or datasets[0].semantic_contract_sha256 != landscape_contract_signature(contract):
        raise ValueError("Current landscape context differs from the requested semantic contract")
    analysis = catalogs.load_analysis(contract.region_id, "wind")
    if not _domain_artifact_matches(contract.domain, analysis.analysis_domain):
        raise ValueError("Current landscape standard-domain contract drifted")
    display = read_analysis_domain_input(analysis, "standard_analysis", contract.domain.resolution,
        geometry_use="display")
    if (display.region_id, display.role, display.resolution, display.upstream_source_sha256,
            display.runtime_revision_sha256) != (
            contract.region_id, "standard_analysis", contract.domain.resolution,
            contract.domain.sha256, scope.analysis_revision_sha256):
        raise ValueError("Current landscape display belongs to another GIS/domain scope")
    snapshot = inputs.landscape
    if (snapshot.source_sha256 != contract.source.sha256
            or snapshot.source_bytes != contract.generated_evidence.source_bytes):
        raise ValueError("Current accepted landscape source drifted")
    source_rows, fields = landscape_feature_rows_from_payload(
        {"type": "FeatureCollection", "features": [
            {"properties": record} for record in snapshot.source_records()
        ]}, id_field=contract.source.id_field, resolution=contract.source.resolution,
        value_fields=tuple(view.value_field for view in contract.views),
    )
    domain_rows, _ = landscape_feature_rows_from_payload(
        json.loads(display.feature_collection_json), id_field=contract.domain.id_field,
        resolution=contract.domain.resolution, area_field=contract.domain.area_field,
    )
    evidence = landscape_evidence_from_rows(source_bytes=snapshot.source_bytes,
        source_rows=source_rows, field_names=fields, domain_rows=domain_rows,
        domain=contract.domain, views=contract.views)
    validate_landscape_generated_evidence(contract, evidence)
    validate_landscape_review_counts(contract, source_rows, domain_rows)
    return source_rows, domain_rows


def build_catalog_landscape_view(
    request: LandscapeViewRequest,
) -> LandscapeViewResult:
    if not isinstance(request, LandscapeViewRequest):
        raise TypeError("request must be a LandscapeViewRequest")
    contract = load_landscape_contract(request.region_id)
    region = catalogs.load_region(request.region_id)
    validate_landscape_view_request_from_contract(contract, request)
    if (
        str(region.get("region_id") or "").strip().lower()
        != request.region_id
    ):
        raise PermissionError("Landscape request region is not catalog-authorized")
    scope_kind, scope_region_id = request.access_scope.split(":", 1)
    if scope_region_id != request.region_id:
        raise PermissionError("Landscape request scope belongs to another region")
    if request.capability_id != LANDSCAPE_CAPABILITY_ID:
        raise PermissionError("Landscape request capability is not authorized")
    if scope_kind == "product":
        landing_card = region.get("landing_card")
        behavior_reference = region.get("behavior_reference")
        if not isinstance(landing_card, Mapping) or not isinstance(
            behavior_reference,
            Mapping,
        ):
            raise PermissionError(
                f"Product landscape access is disabled for {request.region_id}"
            )
        from .access_policy import validate_product_access_dimensions

        try:
            validate_product_access_dimensions(
                lifecycle=region.get("status"),
                behavior_reference_status=behavior_reference.get("status"),
                landing_card_enabled=landing_card.get("enabled"),
            )
        except (TypeError, ValueError) as exc:
            raise PermissionError(
                f"Product landscape access is disabled for {request.region_id}"
            ) from exc
    elif scope_kind == "review":
        from .workspace import load_review_access

        try:
            access = load_review_access(request.region_id)
        except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
            raise PermissionError(
                f"Review landscape access is disabled for {request.region_id}"
            ) from exc
        if (
            access.mode != "review"
            or access.surface != "shared_workspace"
            or access.requires_environment_allowlist is not True
            or request.capability_id not in access.allowed_capabilities
        ):
            raise PermissionError(
                "Landscape capability is not allowed by review access"
            )
    else:
        raise PermissionError(f"Unsupported landscape access mode: {scope_kind}")
    source_rows, domain_rows = _current_catalog_landscape_rows(contract)
    return build_landscape_view_from_validated_rows(
        contract, request, source_rows=source_rows, domain_rows=domain_rows,
    )


def probe_catalog_landscape(region_id: str) -> LandscapeProbe:
    try:
        contract = load_landscape_contract(region_id)
    except (FileNotFoundError, KeyError) as exc:
        return LandscapeProbe("missing_manifest", str(exc))
    except NotImplementedError as exc:
        return LandscapeProbe("not_implemented", str(exc))
    except (OSError, TypeError, ValueError) as exc:
        return LandscapeProbe("not_validated", str(exc))
    try:
        source_rows, domain_rows = _current_catalog_landscape_rows(contract)
        for view in contract.views:
            for resolution in (
                contract.source.resolution,
                *contract.rollup_resolutions,
            ):
                result = build_landscape_view_from_validated_rows(
                    contract,
                    build_landscape_view_request_from_contract(
                        contract,
                        access_scope=f"review:{contract.region_id}",
                        view_id=view.view_id,
                        target_resolution=resolution,
                    ),
                    source_rows=source_rows,
                    domain_rows=domain_rows,
                )
                if not result.cells:
                    raise ValueError("Landscape view returned no domain cells")
    except NotImplementedError as exc:
        return LandscapeProbe("not_implemented", str(exc))
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        return LandscapeProbe("missing_data", str(exc))
    return LandscapeProbe(
        "technically_validated",
        "Det typade display-only-landskapskontraktet, dess källa, domän, "
        "legend och deterministiska rollups är verifierade.",
    )


__all__ = [
    "LANDSCAPE_ACCESS_SCOPE_KINDS",
    "LANDSCAPE_CAPABILITY_ID",
    "LANDSCAPE_MISSING_POLICY",
    "LANDSCAPE_COMPILED_STATUS",
    "LANDSCAPE_COMPATIBILITY_STATUS",
    "LANDSCAPE_NUMERICAL_USE",
    "LANDSCAPE_OUTSIDE_DOMAIN_POLICY",
    "LANDSCAPE_PURPOSE",
    "LANDSCAPE_COMPATIBILITY_ROLLUP_RULE",
    "LANDSCAPE_ROLLUP_RULE",
    "LANDSCAPE_ROLLUP_RULES",
    "LANDSCAPE_SCHEMA_VERSION",
    "LANDSCAPE_VIEW_REQUEST_SCHEMA_VERSION",
    "LANDSCAPE_VIEW_RESULT_SCHEMA_VERSION",
    "LandscapeContract",
    "LandscapeLegendItem",
    "LandscapeProbe",
    "LandscapeViewCell",
    "LandscapeViewRequest",
    "LandscapeViewResult",
    "build_catalog_landscape_view",
    "build_landscape_view_request_from_contract",
    "build_landscape_view_from_contract",
    "build_landscape_view_from_validated_rows",
    "landscape_contract",
    "landscape_contract_signature",
    "load_landscape_contract",
    "materialize_landscape_manifest",
    "parse_landscape_view_request",
    "parse_landscape_view_result",
    "probe_catalog_landscape",
    "validate_landscape_data",
    "validate_landscape_view_request_from_contract",
]
