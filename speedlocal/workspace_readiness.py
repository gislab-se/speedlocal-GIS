from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Mapping

from .access_policy import validate_product_access_dimensions
from .combined_runtime import (
    load_catalog_combined_result_policy,
    load_combined_result_policy_from_region,
    load_combined_result_technical_validation_from_region,
)
from .landscape import probe_catalog_landscape

from .catalogs import (
    load_analysis,
    load_analysis_manifest,
    load_region,
    load_region_geography,
    load_scenario_manifest,
)
from .paths import repo_root
from .rooftop import (
    _run_current_catalog_rooftop_request,
    build_rooftop_request_from_contract,
    build_unavailable_rooftop_result,
    load_catalog_rooftop_contract,
    rooftop_contract_signature,
    validate_unavailable_rooftop_result_from_contract,
)
from .scenarios import (
    build_scenario_request_from_contract,
    load_catalog_scenario_snapshot,
    run_scenario_request,
    scenario_contract,
)
from .social_acceptance import probe_catalog_social_acceptance
from .sources import (
    load_region_analysis_domain_display_artifact,
    resolve_eligible_surface_cell_ids_sha256,
)
from .technology_context import probe_catalog_technology_context
from .validation import validate_contract
from .workspace import (
    CapabilityAvailability,
    ReviewAccessContract,
    ReviewSlicePolicy,
    WorkspaceProfile,
    load_review_access,
    load_workspace_profile,
    validate_workspace_analysis_manifest,
)
from .workspace_view import WorkspaceGroupProbe, probe_catalog_workspace_group


READINESS_STATES = frozenset(
    {
        "missing_manifest",
        "missing_data",
        "not_implemented",
        "not_validated",
        "technically_validated",
        "regionally_accepted",
        "public",
    }
)
EXECUTABLE_READINESS_STATES = frozenset(
    {"technically_validated", "regionally_accepted", "public"}
)
TRUST_READINESS_BY_CLASSIFICATION = {
    "diagnostic_only": "not_validated",
    "candidate": "not_validated",
    "technically_validated": "technically_validated",
    "regionally_accepted": "regionally_accepted",
}
INTERACTIONS = frozenset({"interactive", "read_only", "disabled"})


@dataclass(frozen=True)
class WorkspaceCapabilityProbe:
    """Catalog-derived technical state before review access is applied."""

    capability_id: str
    state: str
    detail: str
    layer_ids: tuple[str, ...] = ()
    operations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.state not in READINESS_STATES:
            raise ValueError(
                f"Unsupported capability probe state: {self.state!r}"
            )
        if not self.capability_id or not self.detail:
            raise ValueError("Capability probe identity and detail are required")


@dataclass(frozen=True)
class WorkspaceCapabilityReadiness:
    """Stable presentation contract for one workspace-profile capability."""

    capability_id: str
    state: str
    detail: str
    interaction: str
    layer_ids: tuple[str, ...] = ()
    operations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.state not in READINESS_STATES:
            raise ValueError(
                f"Unsupported capability readiness state: {self.state!r}"
            )
        if self.interaction not in INTERACTIONS:
            raise ValueError(
                f"Unsupported capability interaction: {self.interaction!r}"
            )
        if (
            self.interaction == "interactive"
            and self.state not in EXECUTABLE_READINESS_STATES
        ):
            raise ValueError(
                "Only a sufficiently ready capability may be interactive: "
                f"{self.capability_id}"
            )


@dataclass(frozen=True)
class WorkspaceReviewSliceBundle:
    """The exact manifest bundle that an allowed review form may request."""

    region_id: str
    analysis_id: str
    group_id: str
    layer_ids: tuple[str, ...]
    operations: tuple[str, ...]
    parameter_ids: tuple[str, ...]


@dataclass(frozen=True)
class WorkspaceReviewSliceReadiness:
    """Access policy and technical state for one allowlisted slice."""

    capability_id: str
    state: str
    detail: str
    interaction: str
    policy: ReviewSlicePolicy
    bundle: WorkspaceReviewSliceBundle

    def __post_init__(self) -> None:
        if self.state not in READINESS_STATES:
            raise ValueError(f"Unsupported review slice state: {self.state!r}")
        if self.interaction not in INTERACTIONS:
            raise ValueError(
                f"Unsupported review slice interaction: {self.interaction!r}"
            )
        if (
            self.interaction == "interactive"
            and self.state not in EXECUTABLE_READINESS_STATES
        ):
            raise ValueError(
                "Only a sufficiently ready review slice may be interactive: "
                f"{self.capability_id}"
            )


@dataclass(frozen=True)
class WorkspaceReviewReadiness:
    """Complete, ordered readiness for one catalog-backed review workspace."""

    region_id: str
    route_authorized: bool
    access_classification: str
    trust_state: str
    access_detail: str
    access: ReviewAccessContract
    capabilities: tuple[WorkspaceCapabilityReadiness, ...]
    allowed_slices: tuple[WorkspaceReviewSliceReadiness, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.route_authorized, bool):
            raise ValueError(
                "Review route authorization must be boolean"
            )
        if self.access.region_id != self.region_id:
            raise ValueError("Review access region identity drifted")
        if self.trust_state not in READINESS_STATES:
            raise ValueError(f"Unsupported review trust state: {self.trust_state!r}")
        capability_ids = tuple(item.capability_id for item in self.capabilities)
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("Review readiness contains duplicate capabilities")
        slice_ids = tuple(item.capability_id for item in self.allowed_slices)
        if len(slice_ids) != len(set(slice_ids)):
            raise ValueError("Review readiness contains duplicate allowed slices")

    def capability(self, capability_id: str) -> WorkspaceCapabilityReadiness:
        normalized = str(capability_id or "").strip()
        try:
            return next(
                item
                for item in self.capabilities
                if item.capability_id == normalized
            )
        except StopIteration as exc:
            raise KeyError(
                f"Workspace capability is not in the active profile: {normalized}"
            ) from exc

    @property
    def slice_states(self) -> dict[str, str]:
        return {
            f"{item.bundle.analysis_id}/{item.bundle.group_id}": item.state
            for item in self.allowed_slices
        }


def _probe(
    capability_id: str,
    state: str,
    detail: str,
    *,
    layer_ids: tuple[str, ...] = (),
    operations: tuple[str, ...] = (),
) -> WorkspaceCapabilityProbe:
    return WorkspaceCapabilityProbe(
        capability_id=capability_id,
        state=state,
        detail=" ".join(str(detail).split()),
        layer_ids=tuple(layer_ids),
        operations=tuple(operations),
    )


def _missing_manifest(capability_id: str, detail: str) -> WorkspaceCapabilityProbe:
    return _probe(capability_id, "missing_manifest", detail)


def _compiler_failure_probes(
    profile: WorkspaceProfile,
    state: str,
    detail: str,
) -> dict[str, WorkspaceCapabilityProbe]:
    return {
        capability_id: _probe(capability_id, state, detail)
        for capability_id in profile.capabilities
    }


def parse_compiler_workspace_readiness(
    payload: object,
    *,
    region_id: str,
    profile: WorkspaceProfile,
) -> dict[str, WorkspaceCapabilityProbe]:
    """Parse the compiler's exact 19-row evidence into canonical probes."""

    normalized_region_id = str(region_id or "").strip().lower()
    if not normalized_region_id:
        raise ValueError("Compiler readiness requires a region id")
    if not isinstance(payload, Mapping):
        raise TypeError("Readinessrapporten måste vara ett JSON-objekt")
    if str(payload.get("schema_version") or "") != "1.0":
        raise ValueError("Readinessrapportens schema_version måste vara 1.0")
    if (
        str(payload.get("region_id") or "").strip().lower()
        != normalized_region_id
    ):
        raise ValueError("Readinessrapportens regionidentitet matchar inte")
    rows = payload.get("capabilities")
    if not isinstance(rows, list):
        raise TypeError("Readinessrapportens capabilities måste vara en lista")
    capability_ids = tuple(
        str(row.get("capability_id") or "")
        if isinstance(row, Mapping)
        else ""
        for row in rows
    )
    if capability_ids != profile.capabilities:
        raise ValueError(
            "Readinessrapporten måste följa workspace-profilens exakta ordning"
        )
    probes: dict[str, WorkspaceCapabilityProbe] = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {
            "capability_id",
            "state",
            "reason",
            "next_action",
        }:
            raise TypeError(
                "Varje compiler-readinessrad måste ha exakt capability_id, "
                "state, reason och next_action"
            )
        capability_id = str(row["capability_id"])
        state = str(row["state"])
        reason = " ".join(str(row["reason"]).split())
        next_action = " ".join(str(row["next_action"]).split())
        if state not in READINESS_STATES or not reason or not next_action:
            raise ValueError(
                f"Compiler-readiness är ofullständig för {capability_id}"
            )
        probes[capability_id] = _probe(
            capability_id,
            state,
            f"{reason} Nästa steg: {next_action}",
        )
    return probes


def _catalog_compiler_capability_probes(
    region_id: str,
    region: Mapping[str, object],
    profile: WorkspaceProfile,
) -> dict[str, WorkspaceCapabilityProbe]:
    """Read optional compiler evidence without making it a runtime shortcut."""

    reference = region.get("region_package_readiness")
    if reference is None:
        return {}
    if not isinstance(reference, str) or not reference.strip():
        return _compiler_failure_probes(
            profile,
            "missing_manifest",
            "Regionmanifestets readinessreferens är strukturellt ogiltig.",
        )
    root = repo_root().resolve()
    path = (root / reference).resolve()
    if path == root or root not in path.parents:
        return _compiler_failure_probes(
            profile,
            "missing_manifest",
            "Regionpaketets readinessreferens lämnar repositoryt.",
        )
    if not path.is_file():
        return _compiler_failure_probes(
            profile,
            "missing_data",
            f"Den deklarerade readinessrapporten saknas: {reference}.",
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return _compiler_failure_probes(
            profile,
            "missing_manifest",
            f"Den deklarerade readinessrapporten kan inte läsas: {exc}",
        )
    try:
        return parse_compiler_workspace_readiness(
            raw,
            region_id=region_id,
            profile=profile,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return _compiler_failure_probes(
            profile,
            "missing_manifest",
            f"Den deklarerade readinessrapporten är ogiltig: {exc}",
        )


def _merge_compiler_evidence(
    runtime: WorkspaceCapabilityProbe,
    compiler: WorkspaceCapabilityProbe | None,
) -> WorkspaceCapabilityProbe:
    """Combine installed compiler evidence with a live generic runtime gate."""

    if compiler is None:
        return runtime
    if compiler.capability_id != runtime.capability_id:
        raise ValueError("Compiler and runtime capability identity drifted")
    runtime_state = runtime.state
    compiler_state = compiler.state
    if runtime_state not in EXECUTABLE_READINESS_STATES:
        state = runtime_state
        detail = runtime.detail
    elif compiler_state in {
        "missing_manifest",
        "missing_data",
        "not_implemented",
    }:
        state = compiler_state
        detail = compiler.detail
    elif compiler_state == "not_validated":
        state = runtime_state
        detail = runtime.detail
    else:
        progression = (
            "technically_validated",
            "regionally_accepted",
            "public",
        )
        state = progression[
            max(progression.index(runtime_state), progression.index(compiler_state))
        ]
        detail = compiler.detail if state == compiler_state else runtime.detail
    return _probe(
        runtime.capability_id,
        state,
        detail,
        layer_ids=runtime.layer_ids,
        operations=runtime.operations,
    )


def _catalog_analysis_manifests(
    region_id: str,
    profile: WorkspaceProfile,
) -> tuple[
    dict[str, Mapping[str, object] | None],
    dict[str, str | None],
]:
    manifests: dict[str, Mapping[str, object] | None] = {}
    errors: dict[str, str | None] = {}
    for analysis_id in profile.technologies:
        try:
            raw = load_analysis_manifest(region_id, analysis_id)
            validate_workspace_analysis_manifest(
                raw,
                region_id=region_id,
                analysis_id=analysis_id,
                profile=profile,
            )
        except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
            manifests[analysis_id] = None
            errors[analysis_id] = " ".join(str(exc).split()) or type(exc).__name__
        else:
            manifests[analysis_id] = raw
            errors[analysis_id] = None
    return manifests, errors


def _group_manifest_declaration(
    manifest: Mapping[str, object] | None,
    group_id: str,
) -> tuple[bool, tuple[str, ...]]:
    if manifest is None:
        return False, ()
    groups = tuple(str(value) for value in manifest.get("groups") or ())
    layer_ids = tuple(
        str(item.get("id") or "")
        for item in manifest.get("layers") or ()
        if isinstance(item, Mapping)
        and str(item.get("group_id") or "") == group_id
        and str(item.get("id") or "")
    )
    return group_id in groups and bool(layer_ids), layer_ids


def _exact_geography_probe(region_id: str) -> WorkspaceCapabilityProbe:
    capability_id = "workspace.map"
    try:
        geography = load_region_geography(region_id)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        return _missing_manifest(
            capability_id,
            "Regionens geografimanifest eller standarddomän är ogiltig: "
            f"{exc}",
        )
    standard_domains = tuple(
        domain
        for domain in geography.analysis_domains.values()
        if domain.purpose == "standard_group_analysis"
    )
    if not standard_domains:
        return _missing_manifest(
            capability_id,
            "Geografimanifestet deklarerar ingen standardanalysdomän.",
        )
    artifacts = []
    try:
        for domain in standard_domains:
            artifact = load_region_analysis_domain_display_artifact(
                region_id,
                domain.id,
                domain.artifacts.resolution,
            )
            artifacts.append(
                f"{domain.id}: R{artifact.resolution}, "
                f"{artifact.cell_count} celler, {artifact.cell_ids_sha256[:12]}"
            )
    except (FileNotFoundError, KeyError, OSError) as exc:
        return _probe(
            capability_id,
            "missing_data",
            f"Den deklarerade analysdomänens artefakt saknas: {exc}",
        )
    except (TypeError, ValueError) as exc:
        return _probe(
            capability_id,
            "missing_data",
            f"Den exakta analysdomänen klarar inte integritetskontrollen: {exc}",
        )
    return _probe(
        capability_id,
        "technically_validated",
        "Exakt geografi och analysdomän är verifierade: " + "; ".join(artifacts),
    )


def _repo_declared_manifest_probe(
    region: Mapping[str, object],
    capability_id: str,
    manifest_field: str,
) -> WorkspaceCapabilityProbe:
    path_value = region.get(manifest_field)
    if not isinstance(path_value, str) or not path_value.strip():
        return _missing_manifest(
            capability_id,
            f"Regionmanifestet deklarerar inte {manifest_field}.",
        )
    root = repo_root().resolve()
    path = (root / path_value).resolve()
    if path == root or root not in path.parents:
        return _missing_manifest(
            capability_id,
            f"{manifest_field} lämnar repositoryt.",
        )
    if not path.is_file():
        return _missing_manifest(
            capability_id,
            f"Det deklarerade manifestet finns inte: {path_value}.",
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return _missing_manifest(
            capability_id,
            f"Det deklarerade manifestet kan inte läsas: {exc}",
        )
    if not isinstance(raw, dict):
        return _missing_manifest(
            capability_id,
            "Det deklarerade manifestet måste vara ett JSON-objekt.",
        )
    return _probe(
        capability_id,
        "not_validated",
        f"Det repoägda {manifest_field} är deklarerat och läsbart, men "
        "capabilityns generiska data- och konsumentgate återstår.",
    )


def _analysis_contract(
    region_id: str,
    analysis_id: str,
) -> tuple[object | None, WorkspaceCapabilityProbe | None]:
    capability_id = f"{analysis_id}.area"
    try:
        contract = load_analysis(region_id, analysis_id)
        validate_contract(contract)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        return None, _missing_manifest(
            capability_id,
            f"{analysis_id}-analysens kontrakt är ogiltigt: {exc}",
        )
    return contract, None


def _area_probe(
    region_id: str,
    analysis_id: str,
    manifest: Mapping[str, object] | None,
) -> WorkspaceCapabilityProbe:
    capability_id = f"{analysis_id}.area"
    if manifest is None or not isinstance(manifest.get("area_result"), Mapping):
        return _missing_manifest(
            capability_id,
            f"{analysis_id}-manifestet deklarerar inget area_result-kontrakt.",
        )
    contract, error = _analysis_contract(region_id, analysis_id)
    if error is not None:
        return error
    try:
        digest = resolve_eligible_surface_cell_ids_sha256(contract)  # type: ignore[arg-type]
    except (FileNotFoundError, KeyError, OSError) as exc:
        return _probe(
            capability_id,
            "missing_data",
            f"Etableringsytans deklarerade artefakt saknas: {exc}",
        )
    except (TypeError, ValueError) as exc:
        return _probe(
            capability_id,
            "missing_data",
            f"Etableringsytan klarar inte integritetskontrollen: {exc}",
        )
    return _probe(
        capability_id,
        "technically_validated",
        f"Area-resultat och checksumspinnad etableringsyta är verifierade ({digest[:12]}).",
    )


def _rooftop_probe(
    region_id: str,
    manifest: Mapping[str, object] | None,
) -> WorkspaceCapabilityProbe:
    capability_id = "solar.rooftop"
    declaration = (
        (manifest.get("distributed_generation") or {}).get("rooftop_solar")
        if isinstance(manifest, Mapping)
        and isinstance(manifest.get("distributed_generation"), Mapping)
        else None
    )
    if not isinstance(declaration, Mapping):
        return _missing_manifest(
            capability_id,
            "Solmanifestet deklarerar inget rooftop_solar-kontrakt.",
        )
    try:
        contract = load_catalog_rooftop_contract(region_id)
        request = build_rooftop_request_from_contract(
            contract,
            access_scope=f"review:{region_id}",
            panel_area_m2_per_person=(
                contract.rooftop.panel_area_m2_per_person.default
            ),
            gross_solar_target_twh=0.0,
            ground_km2_per_twh=0.0,
        )
        result = _run_current_catalog_rooftop_request(contract, request)
    except (FileNotFoundError, KeyError, OSError) as exc:
        return _probe(
            capability_id,
            "missing_data",
            f"Tagsolens deklarerade artefakt saknas: {exc}",
        )
    except NotImplementedError as exc:
        return _probe(capability_id, "not_implemented", str(exc))
    except (TypeError, ValueError) as exc:
        return _probe(
            capability_id,
            "missing_data",
            f"Tagsolens kontrakt eller resultat klarar inte integritetskontrollen: {exc}",
        )
    signature = rooftop_contract_signature(contract)
    return _probe(
        capability_id,
        "technically_validated",
        "Tagsolens manifestbundna request/result och befolkningsbokföring är "
        f"verifierade ({result.mapped_population_cell_count} celler; "
        f"{signature[:12]}).",
    )


def _combined_rooftop_dependency_probe(
    region_id: str,
    rooftop: WorkspaceCapabilityProbe,
) -> WorkspaceCapabilityProbe:
    """Validate no-credit accounting without claiming rooftop availability."""
    if rooftop.state != "missing_manifest":
        return rooftop
    try:
        analysis = load_analysis(region_id, "solar")
        result = build_unavailable_rooftop_result(
            analysis, access_scope=f"review:{region_id}",
        )
        validate_unavailable_rooftop_result_from_contract(analysis, result)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        return _probe(
            rooftop.capability_id,
            "missing_data",
            f"Tagsolens unavailable/no-credit-policy kan inte verifieras: {exc}",
        )
    return _probe(
        rooftop.capability_id,
        "technically_validated",
        "Tagsolsunderlag saknas. Den explicit verifierade no-credit-policyn "
        "behåller hela solmålet för marksol utan avdrag för tagsol.",
    )


def _technology_context_probe(
    region_id: str,
    manifests: Mapping[str, Mapping[str, object] | None],
) -> WorkspaceCapabilityProbe:
    # The probe must execute the immutable request/result consumer. Merely
    # finding both source files is not sufficient technical readiness.
    del manifests
    result = probe_catalog_technology_context(region_id)
    return _probe(
        "workspace.technology_context",
        result.state,
        result.detail,
    )


def _scenario_probe(region: Mapping[str, object], region_id: str) -> WorkspaceCapabilityProbe:
    capability_id = "workspace.scenario"
    if not isinstance(region.get("scenario_manifest"), str):
        return _missing_manifest(
            capability_id,
            "Regionmanifestet deklarerar inget scenario_manifest.",
        )
    try:
        manifest = load_scenario_manifest(region_id)
        contract = scenario_contract(manifest)
    except NotImplementedError as exc:
        return _probe(
            capability_id,
            "not_implemented",
            f"Scenariots deklarerade adapter saknar generell konsument: {exc}",
        )
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
        return _missing_manifest(
            capability_id,
            f"Scenariokontraktet är ogiltigt: {exc}",
        )
    try:
        snapshot = load_catalog_scenario_snapshot(region_id)
        requests = tuple(
            build_scenario_request_from_contract(
                contract,
                access_scope=f"review:{region_id}",
                scenario_id=level.scenario_id,
            )
            for level in contract.planning_levels
        )
        tuple(
            run_scenario_request(contract, request, snapshot)
            for request in requests
        )
    except (FileNotFoundError, KeyError, OSError) as exc:
        return _probe(
            capability_id,
            "missing_data",
            f"Scenariots deklarerade artefakt saknas: {exc}",
        )
    except (TypeError, ValueError) as exc:
        return _probe(
            capability_id,
            "missing_data",
            f"Scenarioartefakten klarar inte integritetskontrollen: {exc}",
        )
    return _probe(
        capability_id,
        "technically_validated",
        "Scenariots typade kontrakt, checksumspinnade indata och deterministiska request/result-kedja är verifierade. Datatilliten är en separat, oförändrad dimension.",
    )


def _social_acceptance_probe(
    region: Mapping[str, object],
    region_id: str,
) -> WorkspaceCapabilityProbe:
    capability_id = "workspace.social_acceptance"
    if not isinstance(region.get("social_acceptance_manifest"), str):
        return _missing_manifest(
            capability_id,
            "Regionmanifestet deklarerar inget social_acceptance_manifest.",
        )
    result = probe_catalog_social_acceptance(region_id)
    return _probe(capability_id, result.state, result.detail)


def _combined_result_policy_probe(
    region: Mapping[str, object],
    region_id: str,
) -> WorkspaceCapabilityProbe:
    """Validate the installed policy through the shared runtime loader."""

    capability_id = "workspace.combined_result"
    try:
        policy_package = (
            load_catalog_combined_result_policy(region_id)
            if "context_runtime_manifest" in region
            else load_combined_result_policy_from_region(
                region,
                region_id,
                repository_root=repo_root(),
            )
        )
        load_combined_result_technical_validation_from_region(
            region,
            region_id,
            policy_package,
            repository_root=repo_root(),
        )
    except KeyError as exc:
        return _missing_manifest(capability_id, str(exc))
    except NotImplementedError as exc:
        return _probe(capability_id, "not_implemented", str(exc))
    except (
        FileNotFoundError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as exc:
        return _probe(
            capability_id,
            "missing_data",
            "Combined-resultets installerade policy kan inte verifieras: "
            f"{exc}",
        )
    return _probe(
        capability_id,
        "technically_validated",
        "Det explicita policykontraktet, den checksummebundna "
        "allokeringspolicyn och separat exekverings-/paritetsevidens är "
        "sammanbundna av samma rena runtime-konsument.",
    )

def _first_dependency_failure(
    capability_id: str,
    dependencies: tuple[WorkspaceCapabilityProbe, ...],
) -> WorkspaceCapabilityProbe:
    for state in (
        "missing_manifest",
        "missing_data",
        "not_implemented",
        "not_validated",
    ):
        failed = next((item for item in dependencies if item.state == state), None)
        if failed is not None:
            return _probe(
                capability_id,
                state,
                f"Beroendet {failed.capability_id} är inte klart: {failed.detail}",
            )
    return _probe(
        capability_id,
        "not_implemented",
        "Alla deklarerade beroenden för det kombinerade resultatet är "
        "verifierade, men den rena kombinerade resultatkonsumenten är ännu "
        "inte materialiserad och exekverad.",
    )


def _catalog_non_group_probes(
    region_id: str,
    region: Mapping[str, object],
    manifests: Mapping[str, Mapping[str, object] | None],
) -> dict[str, WorkspaceCapabilityProbe]:
    area_probes = {
        analysis_id: _area_probe(region_id, analysis_id, manifest)
        for analysis_id, manifest in manifests.items()
    }
    technology_context = _technology_context_probe(region_id, manifests)
    scenario = _scenario_probe(region, region_id)
    rooftop = _rooftop_probe(region_id, manifests.get("solar"))
    social = _social_acceptance_probe(region, region_id)
    combined_policy = _combined_result_policy_probe(region, region_id)
    if combined_policy.state in {
        "missing_manifest",
        "missing_data",
        "not_implemented",
    }:
        combined = combined_policy
    else:
        dependency_result = _first_dependency_failure(
            "workspace.combined_result",
            (
                *area_probes.values(),
                technology_context,
                scenario,
                _combined_rooftop_dependency_probe(region_id, rooftop),
                social,
            ),
        )
        combined = (
            combined_policy
            if dependency_result.state == "not_implemented"
            else dependency_result
        )
    landscape = probe_catalog_landscape(region_id)
    return {
        "workspace.map": _exact_geography_probe(region_id),
        "workspace.landscape": _probe(
            "workspace.landscape",
            landscape.state,
            landscape.detail,
        ),
        **{item.capability_id: item for item in area_probes.values()},
        rooftop.capability_id: rooftop,
        technology_context.capability_id: technology_context,
        scenario.capability_id: scenario,
        social.capability_id: social,
        combined.capability_id: combined,
    }


def _policy_parameters(
    manifest: Mapping[str, object] | None,
    policy: ReviewSlicePolicy,
) -> tuple[tuple[str, ...], str | None]:
    if manifest is None:
        return (), "Analysmanifestet kan inte läsas."
    layers = tuple(
        item
        for item in manifest.get("layers") or ()
        if isinstance(item, Mapping)
        and str(item.get("group_id") or "") == policy.group_id
    )
    if not layers:
        return (), "Review-slicen deklarerar inga lager."
    parameter_ids = tuple(
        str(value)
        for value in (layers[0].get("parameters") or {}).keys()
    )
    if any(
        tuple(str(value) for value in (layer.get("parameters") or {}).keys())
        != parameter_ids
        for layer in layers[1:]
    ):
        return parameter_ids, "Review-slicens lager blandar parameterkontrakt."
    if tuple(policy.explicit_parameters) != parameter_ids:
        return parameter_ids, "Review-policyn matchar inte slicens parametrar."
    return parameter_ids, None


def build_workspace_review_readiness(
    *,
    region_id: str,
    profile: WorkspaceProfile,
    access: ReviewAccessContract,
    analysis_manifests: Mapping[str, Mapping[str, object] | None],
    analysis_errors: Mapping[str, str | None],
    group_probes: Mapping[tuple[str, str], WorkspaceGroupProbe],
    capability_probes: Mapping[str, WorkspaceCapabilityProbe],
    compiler_probes: Mapping[str, WorkspaceCapabilityProbe] | None = None,
    route_authorized: bool,
) -> WorkspaceReviewReadiness:
    """Apply one review policy to catalog facts without reading UI state.

    This function is deliberately pure. A validator can provide a neutral
    fixture snapshot, while the catalog wrapper below supplies the same shape
    from installed region manifests and runtime artifacts.
    """

    normalized_region_id = str(region_id or "").strip().lower()
    if not normalized_region_id:
        raise ValueError("Review readiness requires a region id")
    if access.region_id != normalized_region_id:
        raise ValueError("Review access belongs to another region")
    if not isinstance(route_authorized, bool):
        raise TypeError("Review route authorization must be boolean")
    if tuple(analysis_manifests) != profile.technologies:
        raise ValueError("Readiness analyses must follow workspace-profile order")
    allowed_capabilities = tuple(access.allowed_capabilities)
    allowed_capability_set = set(allowed_capabilities)
    canonical_allowed_capabilities = tuple(
        capability_id
        for capability_id in profile.capabilities
        if capability_id in allowed_capability_set
    )
    if (
        len(allowed_capabilities) != len(allowed_capability_set)
        or allowed_capability_set.difference(profile.capabilities)
        or allowed_capabilities != canonical_allowed_capabilities
    ):
        raise ValueError(
            "Review capabilities must be a unique workspace-profile subsequence"
        )
    allowed_by_identity = {
        (policy.analysis_id, policy.group_id): policy
        for policy in access.allowed_slices
    }
    slice_capabilities = tuple(
        f"{policy.analysis_id}.group.{policy.group_id}"
        for policy in access.allowed_slices
    )
    expected_slice_capabilities = tuple(
        capability_id
        for capability_id in allowed_capabilities
        if ".group." in capability_id
    )
    if slice_capabilities != expected_slice_capabilities:
        raise ValueError(
            "Review slices must exactly match allowlisted group capabilities"
        )
    compiler_probes = compiler_probes or {}
    unknown_compiler_capabilities = set(compiler_probes) - set(
        profile.capabilities
    )
    if unknown_compiler_capabilities:
        raise ValueError(
            "Compiler readiness contains capabilities outside the profile: "
            f"{sorted(unknown_compiler_capabilities)}"
        )
    capabilities: list[WorkspaceCapabilityReadiness] = []
    slices: list[WorkspaceReviewSliceReadiness] = []

    group_capability_ids = {
        f"{analysis_id}.group.{group.id}"
        for analysis_id in profile.technologies
        for group in profile.standard_groups
    }
    for capability_id in profile.capabilities:
        if capability_id not in group_capability_ids:
            probe = capability_probes.get(capability_id)
            if probe is None:
                probe = _probe(
                    capability_id,
                    "not_implemented",
                    "Profilen deklarerar capabilityn men ingen generell "
                    "readiness-konsument är registrerad.",
                )
            if probe.capability_id != capability_id:
                raise ValueError(
                    f"Capability probe identity drifted: {capability_id}"
                )
            probe = _merge_compiler_evidence(
                probe,
                compiler_probes.get(capability_id),
            )
            state = probe.state
            if (
                capability_id == "workspace.map"
                and capability_id in allowed_capability_set
                and route_authorized
                and state in EXECUTABLE_READINESS_STATES
            ):
                interaction = "read_only"
            elif (
                capability_id in allowed_capability_set
                and route_authorized
                and state in EXECUTABLE_READINESS_STATES
            ):
                interaction = "interactive"
            else:
                interaction = "disabled"
            detail = probe.detail
            capabilities.append(
                WorkspaceCapabilityReadiness(
                    capability_id=capability_id,
                    state=state,
                    detail=detail,
                    interaction=interaction,
                    layer_ids=probe.layer_ids,
                    operations=probe.operations,
                )
            )
            continue

        analysis_id, _, group_id = capability_id.partition(".group.")
        manifest = analysis_manifests.get(analysis_id)
        declared, declared_layer_ids = _group_manifest_declaration(
            manifest,
            group_id,
        )
        policy = allowed_by_identity.get((analysis_id, group_id))
        probe = group_probes.get((analysis_id, group_id))
        if not declared:
            state = "missing_manifest"
            interaction = "disabled"
            detail = (
                f"{analysis_id}-manifestet deklarerar inga giltiga lager för "
                f"{group_id}."
            )
            analysis_error = analysis_errors.get(analysis_id)
            if analysis_error:
                detail += f" Kontraktet kunde inte läsas ({analysis_error})."
            layer_ids: tuple[str, ...] = ()
            operations: tuple[str, ...] = ()
        elif probe is None:
            state = "not_implemented"
            interaction = "disabled"
            detail = (
                "Gruppen är deklarerad men saknar en registrerad generell "
                "workspace-konsument."
            )
            layer_ids = declared_layer_ids
            operations = ()
        else:
            if (
                probe.region_id != normalized_region_id
                or probe.analysis_id != analysis_id
                or probe.group_id != group_id
            ):
                raise ValueError(
                    f"Group probe identity drifted for {capability_id}"
                )
            layer_ids = tuple(probe.layer_ids)
            operations = tuple(probe.operations)
            state = (
                "technically_validated"
                if probe.status == "available"
                else str(probe.status)
            )
            if state not in READINESS_STATES:
                raise ValueError(
                    f"Unsupported group readiness state for {capability_id}: "
                    f"{state!r}"
                )
            _, policy_error = (
                _policy_parameters(manifest, policy)
                if policy is not None
                else ((), None)
            )
            interaction = (
                "interactive"
                if route_authorized
                and policy is not None
                and policy_error is None
                and state in EXECUTABLE_READINESS_STATES
                else "disabled"
            )
            detail = str(probe.detail)
            merged = _merge_compiler_evidence(
                _probe(
                    capability_id,
                    state,
                    detail,
                    layer_ids=layer_ids,
                    operations=operations,
                ),
                compiler_probes.get(capability_id),
            )
            state = merged.state
            detail = merged.detail
            if state not in EXECUTABLE_READINESS_STATES:
                interaction = "disabled"
        readiness = WorkspaceCapabilityReadiness(
            capability_id=capability_id,
            state=state,
            detail=detail,
            interaction=interaction,
            layer_ids=layer_ids,
            operations=operations,
        )
        capabilities.append(readiness)
        if policy is not None:
            parameter_ids, policy_error = _policy_parameters(manifest, policy)
            slice_state = readiness.state
            slice_interaction = readiness.interaction
            slice_detail = readiness.detail
            if policy_error is not None:
                slice_interaction = "disabled"
                slice_detail = policy_error
            slices.append(
                WorkspaceReviewSliceReadiness(
                    capability_id=capability_id,
                    state=slice_state,
                    detail=slice_detail,
                    interaction=slice_interaction,
                    policy=policy,
                    bundle=WorkspaceReviewSliceBundle(
                        region_id=normalized_region_id,
                        analysis_id=analysis_id,
                        group_id=group_id,
                        layer_ids=layer_ids,
                        operations=operations,
                        parameter_ids=parameter_ids,
                    ),
                )
            )

    if tuple(item.capability_id for item in capabilities) != profile.capabilities:
        raise ValueError("Review readiness drifted from workspace-profile order")
    if {
        (item.bundle.analysis_id, item.bundle.group_id) for item in slices
    } != set(allowed_by_identity):
        raise ValueError("Review readiness omitted an allowlisted slice")
    return WorkspaceReviewReadiness(
        region_id=normalized_region_id,
        route_authorized=route_authorized,
        access_classification=access.access_classification,
        trust_state=TRUST_READINESS_BY_CLASSIFICATION[
            access.access_classification
        ],
        access_detail=(
            f"Review access and trust classification "
            f"{access.access_classification!r} passed the catalog policy."
        ),
        access=access,
        capabilities=tuple(capabilities),
        allowed_slices=tuple(slices),
    )


def resolve_catalog_workspace_review_readiness(
    region_id: str,
    *,
    route_authorized: bool,
    group_probe: Callable[[str, str, str], WorkspaceGroupProbe] = (
        probe_catalog_workspace_group
    ),
) -> WorkspaceReviewReadiness:
    """Resolve review readiness from the indexed region package only."""

    normalized_region_id = str(region_id or "").strip().lower()
    region = load_region(normalized_region_id)
    profile = load_workspace_profile(normalized_region_id)
    access = load_review_access(normalized_region_id)
    manifests, analysis_errors = _catalog_analysis_manifests(
        normalized_region_id,
        profile,
    )
    group_probes: dict[tuple[str, str], WorkspaceGroupProbe] = {}
    for analysis_id in profile.technologies:
        manifest = manifests[analysis_id]
        for group in profile.standard_groups:
            declared, _ = _group_manifest_declaration(manifest, group.id)
            if declared:
                group_probes[(analysis_id, group.id)] = group_probe(
                    normalized_region_id,
                    analysis_id,
                    group.id,
                )
    capability_probes = _catalog_non_group_probes(
        normalized_region_id,
        region,
        manifests,
    )
    compiler_probes = _catalog_compiler_capability_probes(
        normalized_region_id,
        region,
        profile,
    )
    return build_workspace_review_readiness(
        region_id=normalized_region_id,
        profile=profile,
        access=access,
        analysis_manifests=manifests,
        analysis_errors=analysis_errors,
        group_probes=group_probes,
        capability_probes=capability_probes,
        compiler_probes=compiler_probes,
        route_authorized=route_authorized,
    )


def resolve_catalog_workspace_product_group_availability(
    region_id: str,
    analysis_id: str,
    *,
    group_probe: Callable[[str, str, str], WorkspaceGroupProbe] = (
        probe_catalog_workspace_group
    ),
) -> tuple[CapabilityAvailability, ...]:
    """Resolve executable product controls from the indexed package.

    The public route gate is part of this boundary.  A declared group becomes
    interactive only after its domain, sources, operation, map bytes and
    result all pass the same pure group probe used by review readiness.
    """

    normalized_region_id = str(region_id or "").strip().lower()
    normalized_analysis_id = str(analysis_id or "").strip().lower()
    region = load_region(normalized_region_id)
    landing_card = region.get("landing_card")
    behavior_reference = region.get("behavior_reference")
    if not isinstance(landing_card, Mapping) or not isinstance(
        behavior_reference,
        Mapping,
    ):
        raise PermissionError(
            f"Product workspace is not enabled for {normalized_region_id}"
        )
    try:
        validate_product_access_dimensions(
            lifecycle=region.get("status"),
            behavior_reference_status=behavior_reference.get("status"),
            landing_card_enabled=landing_card.get("enabled"),
        )
    except (TypeError, ValueError) as exc:
        raise PermissionError(
            f"Product workspace is not enabled for {normalized_region_id}"
        ) from exc
    profile = load_workspace_profile(normalized_region_id)
    if normalized_analysis_id not in profile.technologies:
        raise ValueError(
            "Workspace analysis is not declared by the shared profile: "
            f"{normalized_analysis_id!r}"
        )
    manifests, analysis_errors = _catalog_analysis_manifests(
        normalized_region_id,
        profile,
    )
    manifest = manifests[normalized_analysis_id]
    rows: list[CapabilityAvailability] = []
    for group in profile.standard_groups:
        capability_id = (
            f"{normalized_analysis_id}.group.{group.id}"
        )
        declared, declared_layer_ids = _group_manifest_declaration(
            manifest,
            group.id,
        )
        if not declared:
            state = "missing_manifest"
            interaction = "disabled"
            layer_ids: tuple[str, ...] = ()
            detail = (
                f"{normalized_analysis_id}-manifestet deklarerar inga "
                f"giltiga lager för {group.id}."
            )
            if analysis_errors[normalized_analysis_id]:
                detail += (
                    " Kontraktet kunde inte läsas ("
                    f"{analysis_errors[normalized_analysis_id]})."
                )
        else:
            probe = group_probe(
                normalized_region_id,
                normalized_analysis_id,
                group.id,
            )
            if (
                probe.region_id != normalized_region_id
                or probe.analysis_id != normalized_analysis_id
                or probe.group_id != group.id
            ):
                raise ValueError(
                    f"Product group probe identity drifted for {capability_id}"
                )
            state = (
                "available" if probe.status == "available" else probe.status
            )
            interaction = (
                "interactive" if state == "available" else "disabled"
            )
            layer_ids = tuple(probe.layer_ids or declared_layer_ids)
            detail = probe.detail
        rows.append(
            CapabilityAvailability(
                capability_id=capability_id,
                state=state,
                interaction=interaction,
                label=group.label,
                analysis_label=group.analysis_label,
                interpretation=group.interpretation,
                layer_ids=layer_ids,
                detail=detail,
            )
        )
    return tuple(rows)


def _resolve_catalog_workspace_product_capabilities_readiness(
    region_id: str,
    capability_ids: tuple[str, ...],
) -> tuple[WorkspaceCapabilityReadiness, ...]:
    """Resolve non-group capabilities from one complete set of live probes.

    The result belongs to this invocation only; later access checks rerun the
    same manifest, artifact and compiler-evidence validation.
    """

    normalized_region_id = str(region_id or "").strip().lower()
    normalized_capability_ids = tuple(
        str(capability_id or "").strip() for capability_id in capability_ids
    )
    if not normalized_region_id or any(
        not capability_id for capability_id in normalized_capability_ids
    ):
        raise ValueError("Product capability readiness requires exact identities")
    region = load_region(normalized_region_id)
    landing_card = region.get("landing_card")
    behavior_reference = region.get("behavior_reference")
    if not isinstance(landing_card, Mapping) or not isinstance(
        behavior_reference,
        Mapping,
    ):
        raise PermissionError(
            f"Product workspace is not enabled for {normalized_region_id}"
        )
    try:
        validate_product_access_dimensions(
            lifecycle=region.get("status"),
            behavior_reference_status=behavior_reference.get("status"),
            landing_card_enabled=landing_card.get("enabled"),
        )
    except (TypeError, ValueError) as exc:
        raise PermissionError(
            f"Product workspace is not enabled for {normalized_region_id}"
        ) from exc
    profile = load_workspace_profile(normalized_region_id)
    for capability_id in normalized_capability_ids:
        if capability_id not in profile.capabilities:
            raise KeyError(
                "Product capability is not declared by the workspace profile: "
                f"{capability_id}"
            )
        if ".group." in capability_id:
            raise ValueError(
                "Group capability readiness uses the shared product group resolver"
            )
    if not normalized_capability_ids:
        return ()
    manifests, _analysis_errors = _catalog_analysis_manifests(
        normalized_region_id,
        profile,
    )
    runtime_probes = _catalog_non_group_probes(
        normalized_region_id,
        region,
        manifests,
    )
    compiler_probes = _catalog_compiler_capability_probes(
        normalized_region_id,
        region,
        profile,
    )
    rows: list[WorkspaceCapabilityReadiness] = []
    for capability_id in normalized_capability_ids:
        runtime = runtime_probes.get(capability_id)
        if runtime is None:
            runtime = _probe(
                capability_id,
                "not_implemented",
                "Profilen deklarerar capabilityn men ingen generell "
                "readiness-konsument är registrerad.",
            )
        merged = _merge_compiler_evidence(
            runtime, compiler_probes.get(capability_id)
        )
        interaction = (
            "read_only"
            if capability_id == "workspace.map"
            and merged.state in EXECUTABLE_READINESS_STATES
            else "interactive"
            if merged.state in EXECUTABLE_READINESS_STATES
            else "disabled"
        )
        rows.append(
            WorkspaceCapabilityReadiness(
                capability_id=capability_id,
                state=merged.state,
                detail=merged.detail,
                interaction=interaction,
                layer_ids=merged.layer_ids,
                operations=merged.operations,
            )
        )
    return tuple(rows)


def resolve_catalog_workspace_product_capability_readiness(
    region_id: str,
    capability_id: str,
) -> WorkspaceCapabilityReadiness:
    """Resolve one non-group product capability through the generic probes.

    This uses the same manifest, artifact and compiler-evidence probes as the
    shared review workspace. Product access changes only authorization and
    interaction; it cannot select another readiness consumer.
    """

    return _resolve_catalog_workspace_product_capabilities_readiness(
        region_id, (capability_id,)
    )[0]


__all__ = [
    "EXECUTABLE_READINESS_STATES",
    "READINESS_STATES",
    "TRUST_READINESS_BY_CLASSIFICATION",
    "WorkspaceCapabilityProbe",
    "WorkspaceCapabilityReadiness",
    "WorkspaceReviewReadiness",
    "WorkspaceReviewSliceBundle",
    "WorkspaceReviewSliceReadiness",
    "build_workspace_review_readiness",
    "parse_compiler_workspace_readiness",
    "resolve_catalog_workspace_review_readiness",
    "resolve_catalog_workspace_product_capability_readiness",
    "resolve_catalog_workspace_product_group_availability",
]
