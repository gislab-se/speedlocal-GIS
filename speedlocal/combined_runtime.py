from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from .catalogs import load_region
from .combined_presentation import (
    CombinedResultPresentation,
    build_combined_result_presentation_from_validated_inputs,
    parse_combined_result_presentation,
    validate_combined_result_presentation,
)
from .combined_result import (
    COMBINED_RESULT_CAPABILITY_ID,
    CombinedAllocationPolicy,
    CombinedAreaResultBinding,
    CombinedModelParameter,
    CombinedResult,
    build_combined_result,
    parse_combined_allocation_policy,
    parse_combined_result,
    validate_combined_allocation_policy,
    validate_combined_result,
)
from .combined_result_compiler import (
    CombinedResultPolicyContract,
    combined_result_policy_contract_signature,
    parse_combined_result_policy_contract,
    registered_combined_score_executor_ids,
)
from .paths import repo_root, resolve_source_path
from .rooftop import RooftopCapabilityResult, RooftopUnavailableResult
from .scenarios import ScenarioResult
from .social_acceptance import SocialAcceptanceResult
from .technology_context import TechnologyContextResult
from .workspace_area import WorkspaceAreaExecutionResult


COMBINED_EXECUTION_SCHEMA_VERSION = "1.0"
COMBINED_EXECUTION_CAPABILITY_ID = "workspace.combined_result.execution"
COMBINED_POLICY_MANIFEST_SCHEMA_VERSION = "1.0"
COMBINED_POLICY_MATERIALIZATION_STATUS = "compiled_unvalidated"
COMBINED_TECHNICAL_VALIDATION_SCHEMA_VERSION = "1.0"
COMBINED_TECHNICAL_VALIDATION_STATUS = "technically_validated"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_KEYS = {
    "schema_version",
    "capability_id",
    "region_id",
    "materialization_status",
    "policy_contract",
    "policy_contract_signature_sha256",
    "allocation_policy_artifact",
}
_ARTIFACT_KEYS = {
    "provider",
    "path",
    "format",
    "sha256",
    "bytes",
    "base_score_count",
    "priority_value_count",
    "base_score_input_signature_sha256",
    "policy_signature_sha256",
}
_TECHNICAL_VALIDATION_KEYS = {
    "schema_version",
    "capability_id",
    "region_id",
    "validation_status",
    "validator_id",
    "validator_version",
    "validated_utc_date",
    "check_count",
    "reference_scope",
    "policy_contract_signature_sha256",
    "allocation_policy_artifact_sha256",
    "allocation_policy_signature_sha256",
    "validated_default_execution_signature_sha256",
}
_EXECUTION_KEYS = {
    "schema_version",
    "capability_id",
    "access_scope",
    "region_id",
    "policy_contract_signature_sha256",
    "allocation_policy_signature_sha256",
    "area_result_bindings",
    "technology_context_result_signature_sha256",
    "scenario_result_signature_sha256",
    "rooftop_result_signature_sha256",
    "social_acceptance_result_signature_sha256",
    "combined_result",
    "presentation",
    "execution_signature_sha256",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _signature(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be an object")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


@dataclass(frozen=True)
class CombinedResultPolicyPackage:
    region_id: str
    manifest_reference: str
    manifest_path: Path
    contract: CombinedResultPolicyContract
    contract_signature_sha256: str
    artifact_provider: str
    artifact_path: Path | None
    artifact_sha256: str
    policy: CombinedAllocationPolicy


@dataclass(frozen=True)
class CombinedResultTechnicalValidation:
    region_id: str
    evidence_reference: str
    evidence_path: Path
    validator_id: str
    validator_version: str
    validated_utc_date: str
    check_count: int
    reference_scope: str
    policy_contract_signature_sha256: str
    allocation_policy_artifact_sha256: str
    allocation_policy_signature_sha256: str
    validated_default_execution_signature_sha256: str


def _load_combined_result_policy_package(
    raw_manifest: Mapping[str, Any],
    *,
    region_id: str,
    manifest_reference: str,
    manifest_path: Path,
    allocation_payload: bytes | None = None,
) -> CombinedResultPolicyPackage:
    if set(raw_manifest) != _MANIFEST_KEYS:
        raise ValueError("Combined-result manifest does not follow exact schema 1.0")
    if (
        raw_manifest["schema_version"] != COMBINED_POLICY_MANIFEST_SCHEMA_VERSION
        or raw_manifest["capability_id"] != COMBINED_RESULT_CAPABILITY_ID
        or raw_manifest["region_id"] != region_id
        or raw_manifest["materialization_status"]
        != COMBINED_POLICY_MATERIALIZATION_STATUS
    ):
        raise ValueError("Combined-result manifest identity or status drifted")

    contract = parse_combined_result_policy_contract(raw_manifest["policy_contract"])
    contract_signature = combined_result_policy_contract_signature(contract)
    if raw_manifest["policy_contract_signature_sha256"] != contract_signature:
        raise ValueError("Combined-result policy-contract signature drifted")
    if contract.score_input.executor_id not in registered_combined_score_executor_ids():
        raise NotImplementedError(
            "Combined score-input executor is not registered: "
            f"{contract.score_input.executor_id}"
        )

    artifact = _mapping(
        raw_manifest["allocation_policy_artifact"],
        "combined-result allocation-policy artifact",
    )
    if set(artifact) != _ARTIFACT_KEYS:
        raise ValueError("Combined-result policy artifact does not follow exact schema 1.0")
    if artifact["provider"] != "generated_runtime" or artifact["format"] != "json":
        raise ValueError("Combined-result policy artifact must be generated JSON")
    if allocation_payload is None:
        artifact_path = resolve_source_path(str(artifact["provider"]), str(artifact["path"]))
        payload = artifact_path.read_bytes()
    else:
        if not isinstance(allocation_payload, bytes):
            raise TypeError("Combined policy input must be immutable bytes")
        artifact_path = None
        payload = allocation_payload
    declared_bytes = artifact["bytes"]
    if (
        isinstance(declared_bytes, bool)
        or not isinstance(declared_bytes, int)
        or declared_bytes != len(payload)
        or hashlib.sha256(payload).hexdigest() != artifact["sha256"]
    ):
        raise ValueError("Combined-result policy artifact failed integrity validation")
    policy = parse_combined_allocation_policy(json.loads(payload.decode("utf-8")))
    if (
        policy.policy_id != contract.policy_id
        or policy.finalization_resolution != contract.finalization_resolution
        or policy.base_score_model != contract.score_input.base_score_model
        or policy.base_score_input_id != contract.score_input.input_id
        or policy.model_parameters
        != tuple(
            sorted(
                (
                    CombinedModelParameter(
                        parameter_id=item.parameter_id,
                        value=item.value,
                    )
                    for item in contract.score_input.numeric_parameters
                ),
                key=lambda item: item.parameter_id,
            )
        )
        or policy.technology_order != contract.technology_order
        or policy.technology_priorities != contract.technology_priorities
        or policy.co_use_policy != contract.co_use_policy
        or policy.outside_potential_policy != contract.outside_potential_policy
        or policy.outside_ring_model != contract.outside_ring_model
        or policy.rollup_model != contract.rollup_model
        or policy.rollup_resolutions != contract.rollup_resolutions
        or len(policy.base_scores) != artifact["base_score_count"]
        or len(policy.priority_values) != artifact["priority_value_count"]
        or policy.base_score_input_signature_sha256
        != artifact["base_score_input_signature_sha256"]
        or policy.policy_signature_sha256 != artifact["policy_signature_sha256"]
    ):
        raise ValueError("Combined-result generated policy drifted from its contract")
    return CombinedResultPolicyPackage(
        region_id=region_id,
        manifest_reference=manifest_reference,
        manifest_path=manifest_path,
        contract=contract,
        contract_signature_sha256=contract_signature,
        artifact_provider=str(artifact["provider"]),
        artifact_path=artifact_path,
        artifact_sha256=str(artifact["sha256"]),
        policy=policy,
    )


def load_combined_result_policy_from_region(
    region: Mapping[str, object],
    region_id: str,
    *,
    repository_root: Path | None = None,
    allocation_payload: bytes | None = None,
) -> CombinedResultPolicyPackage:
    """Load one fail-closed policy from an already validated region mapping."""

    reference = region.get("combined_result_manifest")
    if not isinstance(reference, str) or not reference.strip():
        raise KeyError("Region manifest does not declare combined_result_manifest")
    root = (repository_root or repo_root()).resolve()
    manifest_path = (root / reference).resolve()
    try:
        manifest_path.relative_to(root)
    except ValueError:
        raise ValueError("combined_result_manifest escapes the repository") from None
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return _load_combined_result_policy_package(
        _mapping(raw, "combined-result manifest"),
        region_id=region_id,
        manifest_reference=reference,
        manifest_path=manifest_path,
        allocation_payload=allocation_payload,
    )


def load_catalog_combined_result_policy(
    region_id: str,
) -> CombinedResultPolicyPackage:
    """Load one fail-closed, checksum-bound catalog policy package."""

    region = load_region(region_id)
    normalized_region = str(region.get("region_id") or "")
    if normalized_region != region_id:
        raise ValueError("Combined-result catalog region identity drifted")
    if "context_runtime_manifest" in region:
        from .context_runtime import load_catalog_context_inputs

        package = load_catalog_context_inputs(region_id).combined_policy
        if package is None:
            raise ValueError("Declared combined policy is missing from the current runtime")
        return package
    return load_combined_result_policy_from_region(region, region_id)


def validate_combined_result_technical_validation(
    value: Any,
    *,
    region_id: str,
    policy_package: CombinedResultPolicyPackage,
    evidence_reference: str = "<memory>",
    evidence_path: Path | None = None,
) -> CombinedResultTechnicalValidation:
    """Bind independent execution evidence to one exact compiled package.

    The compiler cannot create or imply this state. Product readiness is
    granted only when a separately tracked attestation matches the exact
    contract, generated artifact and parsed allocation policy.
    """

    raw = _mapping(value, "combined-result technical validation")
    if set(raw) != _TECHNICAL_VALIDATION_KEYS:
        raise ValueError(
            "Combined-result technical validation does not follow exact schema 1.0"
        )
    normalized_region = str(region_id or "").strip().lower()
    if (
        not normalized_region
        or raw["schema_version"] != COMBINED_TECHNICAL_VALIDATION_SCHEMA_VERSION
        or raw["capability_id"] != COMBINED_RESULT_CAPABILITY_ID
        or raw["region_id"] != normalized_region
        or raw["validation_status"] != COMBINED_TECHNICAL_VALIDATION_STATUS
        or policy_package.region_id != normalized_region
    ):
        raise ValueError("Combined-result technical-validation identity drifted")
    validator_id = str(raw["validator_id"] or "")
    validator_version = str(raw["validator_version"] or "")
    validated_date = str(raw["validated_utc_date"] or "")
    reference_scope = str(raw["reference_scope"] or "")
    check_count = raw["check_count"]
    if (
        not validator_id
        or validator_id.strip() != validator_id
        or not validator_version
        or validator_version.strip() != validator_version
        or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", validated_date)
        or not reference_scope
        or reference_scope.strip() != reference_scope
        or isinstance(check_count, bool)
        or not isinstance(check_count, int)
        or check_count <= 0
    ):
        raise ValueError("Combined-result technical-validation metadata is invalid")
    contract_signature = _digest(
        raw["policy_contract_signature_sha256"],
        "validated combined policy-contract signature",
    )
    artifact_signature = _digest(
        raw["allocation_policy_artifact_sha256"],
        "validated combined allocation-policy artifact signature",
    )
    policy_signature = _digest(
        raw["allocation_policy_signature_sha256"],
        "validated combined allocation-policy signature",
    )
    execution_signature = _digest(
        raw["validated_default_execution_signature_sha256"],
        "validated default combined execution signature",
    )
    if (
        contract_signature != policy_package.contract_signature_sha256
        or artifact_signature != policy_package.artifact_sha256
        or policy_signature != policy_package.policy.policy_signature_sha256
    ):
        raise ValueError(
            "Combined-result technical validation belongs to another policy package"
        )
    return CombinedResultTechnicalValidation(
        region_id=normalized_region,
        evidence_reference=evidence_reference,
        evidence_path=(evidence_path or Path(evidence_reference)),
        validator_id=validator_id,
        validator_version=validator_version,
        validated_utc_date=validated_date,
        check_count=check_count,
        reference_scope=reference_scope,
        policy_contract_signature_sha256=contract_signature,
        allocation_policy_artifact_sha256=artifact_signature,
        allocation_policy_signature_sha256=policy_signature,
        validated_default_execution_signature_sha256=execution_signature,
    )


def load_combined_result_technical_validation_from_region(
    region: Mapping[str, object],
    region_id: str,
    policy_package: CombinedResultPolicyPackage,
    *,
    repository_root: Path | None = None,
) -> CombinedResultTechnicalValidation:
    reference = region.get("combined_result_validation")
    if not isinstance(reference, str) or not reference.strip():
        raise KeyError("Region manifest does not declare combined_result_validation")
    expected_sha256 = _digest(
        region.get("combined_result_validation_sha256"),
        "combined-result technical-validation artifact signature",
    )
    root = (repository_root or repo_root()).resolve()
    evidence_path = (root / reference).resolve()
    try:
        evidence_path.relative_to(root)
    except ValueError:
        raise ValueError(
            "combined_result_validation escapes the repository"
        ) from None
    payload = evidence_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError(
            "Combined-result technical-validation artifact failed integrity validation"
        )
    raw = json.loads(payload.decode("utf-8"))
    return validate_combined_result_technical_validation(
        raw,
        region_id=region_id,
        policy_package=policy_package,
        evidence_reference=reference,
        evidence_path=evidence_path,
    )


def load_catalog_validated_combined_result_policy(
    region_id: str,
) -> tuple[CombinedResultPolicyPackage, CombinedResultTechnicalValidation]:
    """Load an exact policy only after separate technical evidence binds it."""

    region = load_region(region_id)
    normalized_region = str(region.get("region_id") or "")
    if normalized_region != region_id:
        raise ValueError("Combined-result catalog region identity drifted")
    policy_package = load_catalog_combined_result_policy(region_id)
    evidence = load_combined_result_technical_validation_from_region(
        region,
        region_id,
        policy_package,
    )
    return policy_package, evidence


@dataclass(frozen=True)
class CombinedResultExecutionBundle:
    schema_version: str
    capability_id: str
    access_scope: str
    region_id: str
    policy_contract_signature_sha256: str
    allocation_policy_signature_sha256: str
    area_result_bindings: tuple[CombinedAreaResultBinding, ...]
    technology_context_result_signature_sha256: str
    scenario_result_signature_sha256: str
    rooftop_result_signature_sha256: str
    social_acceptance_result_signature_sha256: str
    combined_result: CombinedResult
    presentation: CombinedResultPresentation
    execution_signature_sha256: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "capability_id": self.capability_id,
            "access_scope": self.access_scope,
            "region_id": self.region_id,
            "policy_contract_signature_sha256": self.policy_contract_signature_sha256,
            "allocation_policy_signature_sha256": self.allocation_policy_signature_sha256,
            "area_result_bindings": [item.as_dict() for item in self.area_result_bindings],
            "technology_context_result_signature_sha256": (
                self.technology_context_result_signature_sha256
            ),
            "scenario_result_signature_sha256": self.scenario_result_signature_sha256,
            "rooftop_result_signature_sha256": self.rooftop_result_signature_sha256,
            "social_acceptance_result_signature_sha256": (
                self.social_acceptance_result_signature_sha256
            ),
            "combined_result": self.combined_result.as_dict(),
            "presentation": self.presentation.as_dict(),
            "execution_signature_sha256": self.execution_signature_sha256,
        }


def _execution_signature_payload(bundle: CombinedResultExecutionBundle) -> dict[str, Any]:
    payload = bundle.as_dict()
    payload.pop("execution_signature_sha256")
    return payload


def validate_combined_result_execution_bundle(
    bundle: CombinedResultExecutionBundle,
) -> None:
    _validate_combined_result_execution_envelope(bundle)
    validate_combined_result(bundle.combined_result)
    validate_combined_result_presentation(bundle.presentation)


def _validate_combined_result_execution_envelope(
    bundle: CombinedResultExecutionBundle,
) -> None:
    """Validate the signed execution envelope without replaying large payloads."""

    if not isinstance(bundle, CombinedResultExecutionBundle):
        raise TypeError("bundle must be a CombinedResultExecutionBundle")
    if (
        bundle.schema_version != COMBINED_EXECUTION_SCHEMA_VERSION
        or bundle.capability_id != COMBINED_EXECUTION_CAPABILITY_ID
    ):
        raise ValueError("Combined-result execution identity is invalid")
    _digest(bundle.policy_contract_signature_sha256, "combined policy-contract signature")
    _digest(bundle.allocation_policy_signature_sha256, "combined allocation-policy signature")
    request = bundle.combined_result.request
    if (
        bundle.access_scope != request.access_scope
        or bundle.region_id != request.region_id
        or bundle.area_result_bindings != request.area_result_bindings
        or bundle.technology_context_result_signature_sha256
        != request.technology_context_result_signature_sha256
        or bundle.scenario_result_signature_sha256
        != request.scenario_result_signature_sha256
        or bundle.rooftop_result_signature_sha256
        != request.rooftop_result_signature_sha256
        or bundle.social_acceptance_result_signature_sha256
        != request.social_acceptance_result_signature_sha256
        or bundle.allocation_policy_signature_sha256
        != request.allocation_policy_signature_sha256
        or bundle.combined_result.allocation_state != "executed"
        or bundle.presentation.combined_result_signature_sha256
        != bundle.combined_result.result_signature_sha256
    ):
        raise ValueError("Combined-result execution escaped its signed dependency chain")
    expected_signature = _signature(_execution_signature_payload(bundle))
    if bundle.execution_signature_sha256 != expected_signature:
        raise ValueError("Combined-result execution signature drifted")


def parse_combined_result_execution_bundle(value: Any) -> CombinedResultExecutionBundle:
    raw = _mapping(value, "combined-result execution bundle")
    if set(raw) != _EXECUTION_KEYS:
        raise ValueError("Combined-result execution bundle has unexpected fields")
    bindings_raw = raw["area_result_bindings"]
    if not isinstance(bindings_raw, list):
        raise TypeError("Combined-result execution area bindings must be a list")
    bindings = tuple(
        CombinedAreaResultBinding(
            technology_id=str(
                _mapping(item, "combined area binding")["technology_id"]
            ),
            resolution=int(
                _mapping(item, "combined area binding")["resolution"]
            ),
            result_signature_sha256=_digest(
                _mapping(item, "combined area binding")["result_signature_sha256"],
                "combined area-result signature",
            ),
        )
        for item in bindings_raw
        if set(_mapping(item, "combined area binding"))
        == {"technology_id", "resolution", "result_signature_sha256"}
    )
    if len(bindings) != len(bindings_raw):
        raise ValueError("Combined-result execution area binding has unexpected fields")
    bundle = CombinedResultExecutionBundle(
        schema_version=str(raw["schema_version"]),
        capability_id=str(raw["capability_id"]),
        access_scope=str(raw["access_scope"]),
        region_id=str(raw["region_id"]),
        policy_contract_signature_sha256=_digest(
            raw["policy_contract_signature_sha256"],
            "combined policy-contract signature",
        ),
        allocation_policy_signature_sha256=_digest(
            raw["allocation_policy_signature_sha256"],
            "combined allocation-policy signature",
        ),
        area_result_bindings=bindings,
        technology_context_result_signature_sha256=_digest(
            raw["technology_context_result_signature_sha256"],
            "combined technology-context result signature",
        ),
        scenario_result_signature_sha256=_digest(
            raw["scenario_result_signature_sha256"],
            "combined scenario result signature",
        ),
        rooftop_result_signature_sha256=_digest(
            raw["rooftop_result_signature_sha256"],
            "combined rooftop result signature",
        ),
        social_acceptance_result_signature_sha256=_digest(
            raw["social_acceptance_result_signature_sha256"],
            "combined social-acceptance result signature",
        ),
        combined_result=parse_combined_result(raw["combined_result"]),
        presentation=parse_combined_result_presentation(raw["presentation"]),
        execution_signature_sha256=_digest(
            raw["execution_signature_sha256"],
            "combined execution signature",
        ),
    )
    validate_combined_result_execution_bundle(bundle)
    return bundle


def run_combined_result_execution(
    *,
    area_results: Iterable[WorkspaceAreaExecutionResult],
    technology_context_result: TechnologyContextResult,
    scenario_result: ScenarioResult,
    rooftop_result: RooftopCapabilityResult | RooftopUnavailableResult,
    social_acceptance_result: SocialAcceptanceResult,
    policy_package: CombinedResultPolicyPackage,
) -> CombinedResultExecutionBundle:
    """Execute the pure combined engine and presentation from exact signed inputs."""

    if not isinstance(policy_package, CombinedResultPolicyPackage):
        raise TypeError("policy_package must be a CombinedResultPolicyPackage")
    validate_combined_allocation_policy(policy_package.policy)
    if policy_package.region_id != technology_context_result.region_id:
        raise ValueError(
            "Combined-result policy package belongs to another region"
        )
    areas = tuple(area_results)
    result = build_combined_result(
        area_results=areas,
        technology_context_result=technology_context_result,
        scenario_result=scenario_result,
        rooftop_result=rooftop_result,
        social_acceptance_result=social_acceptance_result,
        allocation_policy=policy_package.policy,
    )
    presentation = build_combined_result_presentation_from_validated_inputs(
        result,
        areas,
    )
    request = result.request
    if policy_package.region_id != request.region_id:
        raise ValueError(
            "Combined-result policy package belongs to another region"
        )
    draft = CombinedResultExecutionBundle(
        schema_version=COMBINED_EXECUTION_SCHEMA_VERSION,
        capability_id=COMBINED_EXECUTION_CAPABILITY_ID,
        access_scope=request.access_scope,
        region_id=request.region_id,
        policy_contract_signature_sha256=(
            policy_package.contract_signature_sha256
        ),
        allocation_policy_signature_sha256=(
            policy_package.policy.policy_signature_sha256
        ),
        area_result_bindings=request.area_result_bindings,
        technology_context_result_signature_sha256=(
            request.technology_context_result_signature_sha256
        ),
        scenario_result_signature_sha256=request.scenario_result_signature_sha256,
        rooftop_result_signature_sha256=request.rooftop_result_signature_sha256,
        social_acceptance_result_signature_sha256=(
            request.social_acceptance_result_signature_sha256
        ),
        combined_result=result,
        presentation=presentation,
        execution_signature_sha256="0" * 64,
    )
    bundle = replace(
        draft,
        execution_signature_sha256=_signature(
            _execution_signature_payload(draft)
        ),
    )
    _validate_combined_result_execution_envelope(bundle)
    return bundle


__all__ = [
    "COMBINED_EXECUTION_CAPABILITY_ID",
    "COMBINED_EXECUTION_SCHEMA_VERSION",
    "CombinedResultExecutionBundle",
    "CombinedResultPolicyPackage",
    "CombinedResultTechnicalValidation",
    "load_catalog_combined_result_policy",
    "load_catalog_validated_combined_result_policy",
    "load_combined_result_policy_from_region",
    "load_combined_result_technical_validation_from_region",
    "parse_combined_result_execution_bundle",
    "run_combined_result_execution",
    "validate_combined_result_execution_bundle",
    "validate_combined_result_technical_validation",
]
