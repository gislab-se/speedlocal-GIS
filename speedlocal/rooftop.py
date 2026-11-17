from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping

from . import catalogs
from .access_policy import validate_product_access_dimensions
from .contracts import AnalysisContract, RooftopSolarContract
from .distributed_generation import (
    RooftopSolarAccountingResult,
    calculate_rooftop_solar_accounting,
    load_rooftop_population_counts,
    rooftop_population_counts_from_raw_frame,
)
from .sources import resolve_analysis_domain_cell_ids
from .validation import validate_contract


ROOFTOP_CAPABILITY_ID = "solar.rooftop"
ROOFTOP_ANALYSIS_ID = "solar"
ROOFTOP_SELECTION_SCHEMA_VERSION = "1.0"
ROOFTOP_REQUEST_SCHEMA_VERSION = "1.0"
ROOFTOP_RESULT_SCHEMA_VERSION = "1.0"
ROOFTOP_ACCESS_SCOPE_KINDS = ("product", "review")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class RooftopCapabilityContract:
    """The typed rooftop contract together with its exact analysis domain."""

    analysis: AnalysisContract
    domain_id: str
    rooftop: RooftopSolarContract

    @property
    def region_id(self) -> str:
        return self.analysis.region_id

    @property
    def analysis_id(self) -> str:
        return self.analysis.id


@dataclass(frozen=True)
class RooftopSelectionRequest:
    """Applied UI selection without scenario-dependent execution inputs."""

    schema_version: str
    access_scope: str
    capability_id: str
    region_id: str
    analysis_id: str
    domain_id: str
    domain_sha256: str
    domain_resolution: int
    contract_signature_sha256: str
    enabled: bool
    panel_area_m2_per_person: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "capability_id": self.capability_id,
            "region_id": self.region_id,
            "analysis_id": self.analysis_id,
            "domain_id": self.domain_id,
            "domain_sha256": self.domain_sha256,
            "domain_resolution": self.domain_resolution,
            "contract_signature_sha256": self.contract_signature_sha256,
            "enabled": self.enabled,
            "panel_area_m2_per_person": self.panel_area_m2_per_person,
        }


@dataclass(frozen=True)
class RooftopCapabilityRequest:
    schema_version: str
    access_scope: str
    capability_id: str
    region_id: str
    analysis_id: str
    domain_id: str
    domain_sha256: str
    domain_resolution: int
    contract_signature_sha256: str
    panel_area_m2_per_person: float
    gross_solar_target_twh: float
    ground_km2_per_twh: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "access_scope": self.access_scope,
            "capability_id": self.capability_id,
            "region_id": self.region_id,
            "analysis_id": self.analysis_id,
            "domain_id": self.domain_id,
            "domain_sha256": self.domain_sha256,
            "domain_resolution": self.domain_resolution,
            "contract_signature_sha256": self.contract_signature_sha256,
            "panel_area_m2_per_person": self.panel_area_m2_per_person,
            "gross_solar_target_twh": self.gross_solar_target_twh,
            "ground_km2_per_twh": self.ground_km2_per_twh,
        }


@dataclass(frozen=True)
class RooftopPopulationCell:
    cell_id: str
    population: float
    panel_area_m2: float
    technical_rooftop_twh: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "cell_id": self.cell_id,
            "population": self.population,
            "panel_area_m2": self.panel_area_m2,
            "technical_rooftop_twh": self.technical_rooftop_twh,
        }


@dataclass(frozen=True)
class RooftopCapabilityResult:
    schema_version: str
    request: RooftopCapabilityRequest
    contract_status: str
    population_semantics: str
    accounting_total_policy: str
    cap_at_solar_target: bool
    affects_geographic_potential: bool
    adds_establishment_candidates: bool
    population_source_total: float
    mapped_population_total: float
    mapped_population_cell_count: int
    mapped_population_cell_ids_sha256: str
    mapped_technical_rooftop_twh: float
    population_cells: tuple[RooftopPopulationCell, ...]
    accounting: RooftopSolarAccountingResult

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request": self.request.as_dict(),
            "contract_status": self.contract_status,
            "population_semantics": self.population_semantics,
            "accounting_total_policy": self.accounting_total_policy,
            "cap_at_solar_target": self.cap_at_solar_target,
            "affects_geographic_potential": self.affects_geographic_potential,
            "adds_establishment_candidates": self.adds_establishment_candidates,
            "population_source_total": self.population_source_total,
            "mapped_population_total": self.mapped_population_total,
            "mapped_population_cell_count": self.mapped_population_cell_count,
            "mapped_population_cell_ids_sha256": (
                self.mapped_population_cell_ids_sha256
            ),
            "mapped_technical_rooftop_twh": (
                self.mapped_technical_rooftop_twh
            ),
            "population_cells": [cell.as_dict() for cell in self.population_cells],
            "accounting": asdict(self.accounting),
        }


def _exact_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{label} must be a normalized identifier")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _h3_resolution(value: Any, label: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > 15
    ):
        raise ValueError(f"{label} must be an H3 integer from 0 to 15")
    return value


def _finite_non_negative(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite non-negative number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return number


def _canonical_id_digest(values: tuple[str, ...]) -> str:
    return hashlib.sha256(
        "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    ).hexdigest()


def _validate_panel_step(
    rooftop: RooftopSolarContract,
    value: float,
) -> float:
    parameter = rooftop.panel_area_m2_per_person
    normalized = parameter.validate_value(value)
    if parameter.step is not None:
        origin = parameter.minimum if parameter.minimum is not None else 0.0
        step_count = (normalized - origin) / parameter.step
        if not math.isclose(
            step_count,
            round(step_count),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError(
                "panel_area_m2_per_person must align to its manifest step "
                f"{parameter.step} from {origin}"
            )
    return normalized


def build_rooftop_capability_contract(
    analysis: AnalysisContract,
    *,
    domain_id: str | None = None,
) -> RooftopCapabilityContract:
    """Bind the existing typed rooftop contract to one exact solar domain."""

    if not isinstance(analysis, AnalysisContract):
        raise TypeError("analysis must be an AnalysisContract")
    validate_contract(analysis)
    if analysis.id != ROOFTOP_ANALYSIS_ID:
        raise ValueError("Rooftop capability requires the solar analysis")
    domain = analysis.analysis_domain
    if domain is None:
        raise ValueError("Rooftop capability requires an analysis domain")
    distributed_generation = analysis.distributed_generation
    rooftop = (
        distributed_generation.rooftop_solar
        if distributed_generation is not None
        else None
    )
    if rooftop is None:
        raise ValueError("Solar analysis has no rooftop-solar contract")
    normalized_domain_id = _exact_identifier(
        domain_id or f"{analysis.id}_analysis_domain",
        "rooftop domain id",
    )
    return RooftopCapabilityContract(
        analysis=analysis,
        domain_id=normalized_domain_id,
        rooftop=rooftop,
    )


def rooftop_contract_signature(contract: RooftopCapabilityContract) -> str:
    """Sign exactly the typed policy and domain consumed by this capability."""

    if not isinstance(contract, RooftopCapabilityContract):
        raise TypeError("contract must be a RooftopCapabilityContract")
    domain = contract.analysis.analysis_domain
    if domain is None:
        raise ValueError("Rooftop capability contract lost its analysis domain")
    payload = {
        "capability_id": ROOFTOP_CAPABILITY_ID,
        "region_id": contract.region_id,
        "analysis_id": contract.analysis_id,
        "domain_id": contract.domain_id,
        "domain": asdict(domain),
        "rooftop": asdict(contract.rooftop),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_rooftop_selection_from_contract(
    contract: RooftopCapabilityContract,
    *,
    access_scope: str,
    enabled: bool,
    panel_area_m2_per_person: float,
) -> RooftopSelectionRequest:
    """Build the immutable, manifest-bound selection persisted by the UI."""

    if not isinstance(contract, RooftopCapabilityContract):
        raise TypeError("contract must be a RooftopCapabilityContract")
    if not isinstance(enabled, bool):
        raise TypeError("rooftop enabled must be a boolean")
    domain = contract.analysis.analysis_domain
    if domain is None:
        raise ValueError("Rooftop capability contract lost its analysis domain")
    # Reuse the complete request builder for access, domain, signature, and
    # parameter validation. Scenario inputs are deliberately neutral here and
    # are never persisted as part of an applied UI selection.
    request = build_rooftop_request_from_contract(
        contract,
        access_scope=access_scope,
        panel_area_m2_per_person=panel_area_m2_per_person,
        gross_solar_target_twh=0.0,
        ground_km2_per_twh=0.0,
        domain_resolution=domain.resolution,
    )
    return RooftopSelectionRequest(
        schema_version=ROOFTOP_SELECTION_SCHEMA_VERSION,
        access_scope=request.access_scope,
        capability_id=request.capability_id,
        region_id=request.region_id,
        analysis_id=request.analysis_id,
        domain_id=request.domain_id,
        domain_sha256=request.domain_sha256,
        domain_resolution=request.domain_resolution,
        contract_signature_sha256=request.contract_signature_sha256,
        enabled=enabled,
        panel_area_m2_per_person=request.panel_area_m2_per_person,
    )


def parse_rooftop_selection(
    value: Mapping[str, Any],
) -> RooftopSelectionRequest:
    """Parse applied UI state without accepting compatibility fields."""

    if not isinstance(value, Mapping):
        raise TypeError("Rooftop selection must be an object")
    expected_keys = {
        "schema_version",
        "access_scope",
        "capability_id",
        "region_id",
        "analysis_id",
        "domain_id",
        "domain_sha256",
        "domain_resolution",
        "contract_signature_sha256",
        "enabled",
        "panel_area_m2_per_person",
    }
    if set(value) != expected_keys:
        raise ValueError("Rooftop selection fields do not match schema 1.0")
    if value["schema_version"] != ROOFTOP_SELECTION_SCHEMA_VERSION:
        raise ValueError("Unsupported rooftop selection schema version")
    enabled = value["enabled"]
    if not isinstance(enabled, bool):
        raise ValueError("Rooftop selection enabled must be a boolean")
    # The request parser owns the strict identity/access/numerical grammar.
    request = parse_rooftop_request(
        {
            key: value[key]
            for key in (
                "schema_version",
                "access_scope",
                "capability_id",
                "region_id",
                "analysis_id",
                "domain_id",
                "domain_sha256",
                "domain_resolution",
                "contract_signature_sha256",
                "panel_area_m2_per_person",
            )
        }
        | {
            "gross_solar_target_twh": 0.0,
            "ground_km2_per_twh": 0.0,
        }
    )
    return RooftopSelectionRequest(
        schema_version=ROOFTOP_SELECTION_SCHEMA_VERSION,
        access_scope=request.access_scope,
        capability_id=request.capability_id,
        region_id=request.region_id,
        analysis_id=request.analysis_id,
        domain_id=request.domain_id,
        domain_sha256=request.domain_sha256,
        domain_resolution=request.domain_resolution,
        contract_signature_sha256=request.contract_signature_sha256,
        enabled=enabled,
        panel_area_m2_per_person=request.panel_area_m2_per_person,
    )


def validate_rooftop_selection_from_contract(
    contract: RooftopCapabilityContract,
    selection: RooftopSelectionRequest,
) -> RooftopSelectionRequest:
    """Reject replay, signature, domain, or parameter drift in UI state."""

    if not isinstance(selection, RooftopSelectionRequest):
        raise TypeError("selection must be a RooftopSelectionRequest")
    rebuilt = build_rooftop_selection_from_contract(
        contract,
        access_scope=selection.access_scope,
        enabled=selection.enabled,
        panel_area_m2_per_person=selection.panel_area_m2_per_person,
    )
    if rebuilt != selection:
        raise ValueError("Rooftop selection drifted from its manifest contract")
    return selection


def build_rooftop_request_from_selection(
    contract: RooftopCapabilityContract,
    selection: RooftopSelectionRequest,
    *,
    gross_solar_target_twh: float,
    ground_km2_per_twh: float,
    domain_resolution: int | None = None,
) -> RooftopCapabilityRequest:
    """Bind current scenario inputs to one already-applied typed selection."""

    validate_rooftop_selection_from_contract(contract, selection)
    return build_rooftop_request_from_contract(
        contract,
        access_scope=selection.access_scope,
        panel_area_m2_per_person=(
            selection.panel_area_m2_per_person if selection.enabled else 0.0
        ),
        gross_solar_target_twh=gross_solar_target_twh,
        ground_km2_per_twh=ground_km2_per_twh,
        domain_resolution=(
            selection.domain_resolution
            if domain_resolution is None
            else domain_resolution
        ),
    )


def build_rooftop_request_from_contract(
    contract: RooftopCapabilityContract,
    *,
    access_scope: str,
    panel_area_m2_per_person: float,
    gross_solar_target_twh: float,
    ground_km2_per_twh: float,
    domain_resolution: int | None = None,
) -> RooftopCapabilityRequest:
    """Build one immutable, manifest-bound rooftop accounting request."""

    if not isinstance(contract, RooftopCapabilityContract):
        raise TypeError("contract must be a RooftopCapabilityContract")
    # Rebuild the wrapper so callers cannot construct an unsupported policy by
    # instantiating the dataclass directly.
    verified = build_rooftop_capability_contract(
        contract.analysis,
        domain_id=contract.domain_id,
    )
    if verified != contract:
        raise ValueError("Rooftop capability contract drifted from its analysis")
    scope = str(access_scope).strip().lower()
    scope_parts = scope.split(":", 1)
    if (
        len(scope_parts) != 2
        or scope_parts[0] not in ROOFTOP_ACCESS_SCOPE_KINDS
        or scope_parts[1] != contract.region_id.lower()
    ):
        raise ValueError(
            "Rooftop access_scope must be product:<region> or review:<region>"
        )
    domain = contract.analysis.analysis_domain
    if domain is None:
        raise ValueError("Rooftop capability contract lost its analysis domain")
    requested_resolution = (
        int(domain.resolution)
        if domain_resolution is None
        else _h3_resolution(domain_resolution, "rooftop domain resolution")
    )
    if requested_resolution == domain.resolution:
        domain_sha256 = domain.sha256
    else:
        rollup = domain.rollups.get(requested_resolution)
        if rollup is None:
            raise ValueError(
                f"Rooftop analysis has no R{requested_resolution} domain"
            )
        domain_sha256 = rollup.sha256
    panel_area = _validate_panel_step(
        contract.rooftop,
        _finite_non_negative(
            panel_area_m2_per_person,
            "panel_area_m2_per_person",
        ),
    )
    return RooftopCapabilityRequest(
        schema_version=ROOFTOP_REQUEST_SCHEMA_VERSION,
        access_scope=scope,
        capability_id=ROOFTOP_CAPABILITY_ID,
        region_id=contract.region_id,
        analysis_id=contract.analysis_id,
        domain_id=contract.domain_id,
        domain_sha256=domain_sha256,
        domain_resolution=requested_resolution,
        contract_signature_sha256=rooftop_contract_signature(contract),
        panel_area_m2_per_person=panel_area,
        gross_solar_target_twh=_finite_non_negative(
            gross_solar_target_twh,
            "gross_solar_target_twh",
        ),
        ground_km2_per_twh=_finite_non_negative(
            ground_km2_per_twh,
            "ground_km2_per_twh",
        ),
    )


def parse_rooftop_request(
    value: Mapping[str, Any],
) -> RooftopCapabilityRequest:
    """Parse persisted applied state without accepting compatibility fields."""

    if not isinstance(value, Mapping):
        raise TypeError("Rooftop request must be an object")
    expected_keys = {
        "schema_version",
        "access_scope",
        "capability_id",
        "region_id",
        "analysis_id",
        "domain_id",
        "domain_sha256",
        "domain_resolution",
        "contract_signature_sha256",
        "panel_area_m2_per_person",
        "gross_solar_target_twh",
        "ground_km2_per_twh",
    }
    if set(value) != expected_keys:
        raise ValueError("Rooftop request fields do not match schema 1.0")
    if value["schema_version"] != ROOFTOP_REQUEST_SCHEMA_VERSION:
        raise ValueError("Unsupported rooftop request schema version")
    region_id = _exact_identifier(value["region_id"], "rooftop region id")
    access_scope = value["access_scope"]
    if not isinstance(access_scope, str) or access_scope != access_scope.strip():
        raise ValueError("Rooftop access scope must be an exact string")
    scope_parts = access_scope.split(":", 1)
    if (
        len(scope_parts) != 2
        or scope_parts[0] not in ROOFTOP_ACCESS_SCOPE_KINDS
        or scope_parts[1] != region_id
    ):
        raise ValueError("Rooftop request access scope is not region-bound")
    if value["capability_id"] != ROOFTOP_CAPABILITY_ID:
        raise ValueError(
            f"Rooftop request capability must be {ROOFTOP_CAPABILITY_ID}"
        )
    analysis_id = _exact_identifier(
        value["analysis_id"],
        "rooftop analysis id",
    )
    if analysis_id != ROOFTOP_ANALYSIS_ID:
        raise ValueError("Rooftop request analysis must be solar")
    return RooftopCapabilityRequest(
        schema_version=ROOFTOP_REQUEST_SCHEMA_VERSION,
        access_scope=access_scope,
        capability_id=ROOFTOP_CAPABILITY_ID,
        region_id=region_id,
        analysis_id=analysis_id,
        domain_id=_exact_identifier(value["domain_id"], "rooftop domain id"),
        domain_sha256=_digest(
            value["domain_sha256"],
            "rooftop domain sha256",
        ),
        domain_resolution=_h3_resolution(
            value["domain_resolution"],
            "rooftop domain resolution",
        ),
        contract_signature_sha256=_digest(
            value["contract_signature_sha256"],
            "rooftop contract signature",
        ),
        panel_area_m2_per_person=_finite_non_negative(
            value["panel_area_m2_per_person"],
            "panel_area_m2_per_person",
        ),
        gross_solar_target_twh=_finite_non_negative(
            value["gross_solar_target_twh"],
            "gross_solar_target_twh",
        ),
        ground_km2_per_twh=_finite_non_negative(
            value["ground_km2_per_twh"],
            "ground_km2_per_twh",
        ),
    )


def validate_rooftop_request_from_contract(
    contract: RooftopCapabilityContract,
    request: RooftopCapabilityRequest,
) -> RooftopCapabilityRequest:
    """Rebuild the request and reject identity, domain, input or policy drift."""

    if not isinstance(request, RooftopCapabilityRequest):
        raise TypeError("request must be a RooftopCapabilityRequest")
    rebuilt = build_rooftop_request_from_contract(
        contract,
        access_scope=request.access_scope,
        panel_area_m2_per_person=request.panel_area_m2_per_person,
        gross_solar_target_twh=request.gross_solar_target_twh,
        ground_km2_per_twh=request.ground_km2_per_twh,
        domain_resolution=request.domain_resolution,
    )
    if rebuilt != request:
        raise ValueError("Rooftop request drifted from its manifest contract")
    return request


def run_rooftop_request_from_contract(
    contract: RooftopCapabilityContract,
    request: RooftopCapabilityRequest,
) -> RooftopCapabilityResult:
    """Execute the immutable request through the generic population/accounting path."""

    validate_rooftop_request_from_contract(contract, request)
    canonical_domain_ids = resolve_analysis_domain_cell_ids(
        contract.analysis,
        contract.analysis.analysis_domain.resolution,
    )
    population = load_rooftop_population_counts(
        contract.rooftop.population_source,
        canonical_domain_ids,
        request.domain_resolution,
    )
    return _rooftop_result_from_population(contract, request, population)


def run_rooftop_request_from_inputs(
    contract: RooftopCapabilityContract,
    request: RooftopCapabilityRequest, *,
    canonical_domain_ids: tuple[str, ...], raw_population: Any,
) -> RooftopCapabilityResult:
    """Execute unchanged accounting from decoded raw rows and canonical IDs."""
    validate_rooftop_request_from_contract(contract, request)
    population = rooftop_population_counts_from_raw_frame(
        contract.rooftop.population_source, raw_population,
        canonical_domain_ids, request.domain_resolution,
    )
    return _rooftop_result_from_population(contract, request, population)


def _rooftop_result_from_population(
    contract: RooftopCapabilityContract, request: RooftopCapabilityRequest,
    population: Any,
) -> RooftopCapabilityResult:
    annual_yield = (
        contract.rooftop.annual_yield.specific_yield_kwh_per_kwp
        * contract.rooftop.annual_yield.module_efficiency_stc_fraction
    )
    cells = tuple(
        RooftopPopulationCell(
            cell_id=str(row.hex_id),
            population=float(row.population),
            panel_area_m2=(
                float(row.population) * request.panel_area_m2_per_person
            ),
            technical_rooftop_twh=(
                float(row.population)
                * request.panel_area_m2_per_person
                * annual_yield
                / 1_000_000_000.0
            ),
        )
        for row in population.itertuples(index=False)
    )
    cell_ids = tuple(cell.cell_id for cell in cells)
    mapped_population = math.fsum(cell.population for cell in cells)
    mapped_technical = math.fsum(
        cell.technical_rooftop_twh for cell in cells
    )
    source = contract.rooftop.population_source
    accounting = calculate_rooftop_solar_accounting(
        contract.rooftop,
        source.expected_total,
        request.panel_area_m2_per_person,
        request.gross_solar_target_twh,
        request.ground_km2_per_twh,
    )
    return RooftopCapabilityResult(
        schema_version=ROOFTOP_RESULT_SCHEMA_VERSION,
        request=request,
        contract_status=contract.rooftop.status,
        population_semantics=source.semantics,
        accounting_total_policy=source.accounting_total_policy,
        cap_at_solar_target=contract.rooftop.accounting.cap_at_solar_target,
        affects_geographic_potential=(
            contract.rooftop.accounting.affects_geographic_potential
        ),
        adds_establishment_candidates=(
            contract.rooftop.accounting.adds_establishment_candidates
        ),
        population_source_total=source.expected_total,
        mapped_population_total=mapped_population,
        mapped_population_cell_count=len(cells),
        mapped_population_cell_ids_sha256=_canonical_id_digest(cell_ids),
        mapped_technical_rooftop_twh=mapped_technical,
        population_cells=cells,
        accounting=accounting,
    )


def _catalog_domain_id(region_id: str) -> str:
    raw = catalogs.load_analysis_manifest(region_id, ROOFTOP_ANALYSIS_ID)
    reference = raw.get("analysis_domain_reference")
    if reference is None:
        return f"{ROOFTOP_ANALYSIS_ID}_analysis_domain"
    if not isinstance(reference, Mapping):
        raise ValueError("Rooftop analysis domain reference must be an object")
    if set(reference) != {"type", "domain_id"}:
        raise ValueError("Rooftop analysis domain reference fields are invalid")
    if reference.get("type") != "region_geography":
        raise ValueError("Unsupported rooftop analysis domain reference")
    return _exact_identifier(reference.get("domain_id"), "rooftop domain id")


def load_catalog_rooftop_contract(region_id: str) -> RooftopCapabilityContract:
    normalized = _exact_identifier(region_id, "rooftop catalog region")
    analysis = catalogs.load_analysis(normalized, ROOFTOP_ANALYSIS_ID)
    return build_rooftop_capability_contract(
        analysis,
        domain_id=_catalog_domain_id(normalized),
    )


def build_catalog_rooftop_request(
    region_id: str,
    **kwargs: Any,
) -> RooftopCapabilityRequest:
    return build_rooftop_request_from_contract(
        load_catalog_rooftop_contract(region_id),
        **kwargs,
    )


def build_catalog_rooftop_selection(
    region_id: str,
    **kwargs: Any,
) -> RooftopSelectionRequest:
    return build_rooftop_selection_from_contract(
        load_catalog_rooftop_contract(region_id),
        **kwargs,
    )


def _authorize_catalog_rooftop_request(
    contract: RooftopCapabilityContract,
    request: RooftopCapabilityRequest,
) -> RooftopCapabilityRequest:
    validate_rooftop_request_from_contract(contract, request)
    region = catalogs.load_region(request.region_id)
    if str(region.get("region_id") or "").strip().lower() != request.region_id:
        raise PermissionError("Rooftop request region is not catalog-authorized")
    from .workspace import load_review_access, load_workspace_profile

    profile = load_workspace_profile(request.region_id)
    if request.capability_id not in profile.capabilities:
        raise PermissionError("Rooftop capability is not declared by the workspace")
    scope_kind, scope_region_id = request.access_scope.split(":", 1)
    if scope_region_id != request.region_id:
        raise PermissionError("Rooftop request scope belongs to another region")
    if scope_kind == "product":
        landing_card = region.get("landing_card")
        behavior_reference = region.get("behavior_reference")
        if not isinstance(landing_card, Mapping) or not isinstance(
            behavior_reference,
            Mapping,
        ):
            raise PermissionError(
                f"Product rooftop access is disabled for {request.region_id}"
            )
        try:
            validate_product_access_dimensions(
                lifecycle=region.get("status"),
                behavior_reference_status=behavior_reference.get("status"),
                landing_card_enabled=landing_card.get("enabled"),
            )
        except (TypeError, ValueError) as exc:
            raise PermissionError(
                f"Product rooftop access is disabled for {request.region_id}"
            ) from exc
        return request
    if scope_kind != "review":
        raise PermissionError(f"Unsupported rooftop access mode: {scope_kind}")
    try:
        access = load_review_access(request.region_id)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        raise PermissionError(
            f"Review rooftop access is disabled for {request.region_id}"
        ) from exc
    if (
        access.mode != "review"
        or access.surface != "shared_workspace"
        or access.requires_environment_allowlist is not True
        or request.capability_id not in access.allowed_capabilities
    ):
        raise PermissionError("Rooftop capability is not allowed by review access")
    return request


def _run_current_catalog_rooftop_request(
    contract: RooftopCapabilityContract, request: RooftopCapabilityRequest,
) -> RooftopCapabilityResult:
    from .context_runtime import catalog_context_runtime_declared, load_catalog_context_inputs

    if catalog_context_runtime_declared(request.region_id):
        inputs = load_catalog_context_inputs(request.region_id)
        if inputs.rooftop_population is None:
            raise ValueError("Declared rooftop population is missing from the current runtime")
        return run_rooftop_request_from_inputs(contract, request,
            canonical_domain_ids=inputs.standard_cell_ids,
            raw_population=inputs.rooftop_population.raw_frame(contract.rooftop.population_source))
    return run_rooftop_request_from_contract(contract, request)


def run_catalog_rooftop_request(
    request: RooftopCapabilityRequest,
) -> RooftopCapabilityResult:
    if not isinstance(request, RooftopCapabilityRequest):
        raise TypeError("request must be a RooftopCapabilityRequest")
    contract = load_catalog_rooftop_contract(request.region_id)
    _authorize_catalog_rooftop_request(contract, request)
    return _run_current_catalog_rooftop_request(contract, request)


__all__ = [
    "ROOFTOP_ACCESS_SCOPE_KINDS",
    "ROOFTOP_ANALYSIS_ID",
    "ROOFTOP_CAPABILITY_ID",
    "ROOFTOP_REQUEST_SCHEMA_VERSION",
    "ROOFTOP_RESULT_SCHEMA_VERSION",
    "ROOFTOP_SELECTION_SCHEMA_VERSION",
    "RooftopCapabilityContract",
    "RooftopCapabilityRequest",
    "RooftopCapabilityResult",
    "RooftopPopulationCell",
    "RooftopSelectionRequest",
    "build_catalog_rooftop_request",
    "build_catalog_rooftop_selection",
    "build_rooftop_capability_contract",
    "build_rooftop_request_from_contract",
    "build_rooftop_request_from_selection",
    "build_rooftop_selection_from_contract",
    "load_catalog_rooftop_contract",
    "parse_rooftop_request",
    "parse_rooftop_selection",
    "rooftop_contract_signature",
    "run_catalog_rooftop_request",
    "run_rooftop_request_from_contract",
    "validate_rooftop_request_from_contract",
    "validate_rooftop_selection_from_contract",
]


@dataclass(frozen=True)
class RooftopUnavailableRequest:
    """No-credit identity only; missing population is never represented as zero."""

    schema_version: str
    access_scope: str
    capability_id: str
    region_id: str
    analysis_id: str
    domain_id: str
    domain_sha256: str
    domain_resolution: int
    contract_signature_sha256: str
    eligible_surface_id: str
    domain_cell_count: int
    domain_cell_ids_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RooftopUnavailableResult:
    schema_version: str
    request: RooftopUnavailableRequest
    status: str
    accounting_policy: str
    reason: str
    result_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unavailable_rooftop_signature(result: RooftopUnavailableResult) -> str:
    payload = result.as_dict()
    payload.pop("result_signature_sha256")
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, allow_nan=False, sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def validate_unavailable_rooftop_result(
    result: RooftopUnavailableResult,
) -> RooftopUnavailableResult:
    if not isinstance(result, RooftopUnavailableResult):
        raise TypeError("result must be a RooftopUnavailableResult")
    request = result.request
    if not isinstance(request, RooftopUnavailableRequest):
        raise TypeError("Unavailable rooftop request has the wrong type")
    if (result.schema_version != "1.0" or request.schema_version != "1.0"
            or request.capability_id != ROOFTOP_CAPABILITY_ID
            or request.analysis_id != ROOFTOP_ANALYSIS_ID
            or result.status != "unavailable" or result.accounting_policy != "no_credit"
            or result.reason != "missing_rooftop_population_contract"):
        raise ValueError("Unsupported unavailable rooftop policy or identity")
    for value, label in ((request.region_id, "region"), (request.domain_id, "domain"),
                         (request.eligible_surface_id, "eligible surface")):
        _exact_identifier(value, label)
    scope = request.access_scope
    if not isinstance(scope, str) or scope != scope.strip():
        raise ValueError("Unavailable rooftop access scope must be an exact string")
    parts = scope.split(":", 1)
    if (len(parts) != 2 or parts[0] not in ROOFTOP_ACCESS_SCOPE_KINDS
            or parts[1] != request.region_id):
        raise ValueError("Unavailable rooftop access scope is not region-bound")
    _h3_resolution(request.domain_resolution, "Unavailable rooftop resolution")
    if (isinstance(request.domain_cell_count, bool)
            or not isinstance(request.domain_cell_count, int)
            or request.domain_cell_count <= 0):
        raise ValueError("Unavailable rooftop requires a positive support-cell count")
    for value in (request.domain_sha256, request.contract_signature_sha256,
                  request.domain_cell_ids_sha256, result.result_signature_sha256):
        _digest(value, "Unavailable rooftop digest")
    if result.result_signature_sha256 != _unavailable_rooftop_signature(result):
        raise ValueError("Unavailable rooftop result signature drifted")
    return result


def build_unavailable_rooftop_result(
    analysis: AnalysisContract, *, access_scope: str,
) -> RooftopUnavailableResult:
    """Bind the approved missing-input policy to the actual solar support domain.

    This is available only when the typed analysis has no rooftop contract.
    A declared but broken/stale rooftop input must continue to fail closed.
    """
    from dataclasses import replace
    from .sources import eligible_surface_contract_for_analysis
    from .workspace_request import analysis_contract_signature

    if not isinstance(analysis, AnalysisContract):
        raise TypeError("analysis must be an AnalysisContract")
    validate_contract(analysis)
    if analysis.id != ROOFTOP_ANALYSIS_ID:
        raise ValueError("Unavailable rooftop requires the solar analysis")
    distributed = analysis.distributed_generation
    if distributed is not None and distributed.rooftop_solar is not None:
        raise ValueError("A declared rooftop contract cannot silently become unavailable")
    surface = eligible_surface_contract_for_analysis(analysis)
    request = RooftopUnavailableRequest(
        schema_version="1.0", access_scope=access_scope,
        capability_id=ROOFTOP_CAPABILITY_ID, region_id=analysis.region_id,
        analysis_id=analysis.id, domain_id=surface.support_domain_id,
        domain_sha256=surface.sha256, domain_resolution=surface.resolution,
        contract_signature_sha256=analysis_contract_signature(analysis),
        eligible_surface_id=surface.id,
        domain_cell_count=surface.expected_cell_count,
        domain_cell_ids_sha256=surface.support_observations.cell_ids_sha256,
    )
    result = RooftopUnavailableResult(
        schema_version="1.0", request=request, status="unavailable",
        accounting_policy="no_credit", reason="missing_rooftop_population_contract",
        result_signature_sha256="0" * 64,
    )
    result = replace(result, result_signature_sha256=_unavailable_rooftop_signature(result))
    return validate_unavailable_rooftop_result(result)


def validate_unavailable_rooftop_result_from_contract(
    analysis: AnalysisContract, result: RooftopUnavailableResult,
) -> RooftopUnavailableResult:
    validate_unavailable_rooftop_result(result)
    expected = build_unavailable_rooftop_result(analysis, access_scope=result.request.access_scope)
    if result != expected:
        raise ValueError("Unavailable rooftop result does not match the current analysis")
    return result
