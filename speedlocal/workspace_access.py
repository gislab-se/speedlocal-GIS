from __future__ import annotations

from dataclasses import dataclass

from .catalogs import load_analysis
from .workspace import ReviewSlicePolicy, load_workspace_profile
from .workspace_readiness import (
    WorkspaceCapabilityReadiness,
    WorkspaceReviewReadiness,
    WorkspaceReviewSliceBundle,
    _resolve_catalog_workspace_product_capabilities_readiness,
    resolve_catalog_workspace_product_group_availability,
    resolve_catalog_workspace_review_readiness,
)


@dataclass(frozen=True)
class WorkspaceAccessSliceReadiness:
    """One executable analysis slice, independent of the access kind."""

    capability_id: str
    state: str
    detail: str
    interaction: str
    policy: ReviewSlicePolicy
    bundle: WorkspaceReviewSliceBundle

    def __post_init__(self) -> None:
        expected_capability_id = (
            f"{self.bundle.analysis_id}.group.{self.bundle.group_id}"
        )
        if self.capability_id != expected_capability_id:
            raise ValueError("Workspace slice capability identity drifted")
        if (
            self.policy.analysis_id != self.bundle.analysis_id
            or self.policy.group_id != self.bundle.group_id
            or self.policy.explicit_parameters != self.bundle.parameter_ids
        ):
            raise ValueError("Workspace slice policy drifted from its bundle")
        if self.interaction not in {"interactive", "read_only", "disabled"}:
            raise ValueError("Workspace slice interaction is invalid")
        if self.interaction == "read_only":
            raise ValueError("Analysis group slices cannot be read-only")


@dataclass(frozen=True)
class WorkspaceAccessReadiness:
    """The complete profile-ordered workspace for product or local review.

    Route resolution remains outside this data contract.  Callers must pass
    the already resolved access scope explicitly; no region, session or
    default fallback may select another surface.
    """

    region_id: str
    access_scope: str
    access_kind: str
    route_authorized: bool
    access_classification: str
    trust_state: str
    capabilities: tuple[WorkspaceCapabilityReadiness, ...]
    slices: tuple[WorkspaceAccessSliceReadiness, ...]
    review: WorkspaceReviewReadiness | None = None

    def __post_init__(self) -> None:
        if self.access_kind not in {"product", "review"}:
            raise ValueError("Workspace access kind must be product or review")
        if self.access_scope != f"{self.access_kind}:{self.region_id}":
            raise ValueError("Workspace access scope is not bound to its region")
        if not self.route_authorized:
            raise PermissionError("Workspace route is not authorized")
        if self.access_kind == "review":
            if self.review is None or self.review.region_id != self.region_id:
                raise ValueError("Review workspace is missing its access contract")
        elif self.review is not None:
            raise ValueError("Product workspace may not carry a review contract")
        capability_ids = tuple(item.capability_id for item in self.capabilities)
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("Workspace readiness contains duplicate capabilities")
        slice_ids = tuple(item.capability_id for item in self.slices)
        if len(slice_ids) != len(set(slice_ids)):
            raise ValueError("Workspace readiness contains duplicate slices")
        if any(item.capability_id not in capability_ids for item in self.slices):
            raise ValueError("Workspace slice is absent from capability readiness")

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

    def analysis_slices(
        self,
        analysis_id: str,
        *,
        interactive_only: bool = False,
    ) -> tuple[WorkspaceAccessSliceReadiness, ...]:
        normalized = str(analysis_id or "").strip().lower()
        return tuple(
            item
            for item in self.slices
            if item.bundle.analysis_id == normalized
            and (not interactive_only or item.interaction == "interactive")
        )


def _scope(region_id: str, access_scope: str) -> tuple[str, str]:
    normalized_region_id = str(region_id or "").strip().lower()
    raw_scope = str(access_scope or "").strip().lower()
    parts = raw_scope.split(":", 1)
    if (
        not normalized_region_id
        or len(parts) != 2
        or parts[0] not in {"product", "review"}
        or parts[1] != normalized_region_id
    ):
        raise ValueError("Workspace access scope must exactly bind kind and region")
    return normalized_region_id, parts[0]


def _review_access_readiness(
    region_id: str,
    access_scope: str,
) -> WorkspaceAccessReadiness:
    review = resolve_catalog_workspace_review_readiness(
        region_id,
        route_authorized=True,
    )
    slices = tuple(
        WorkspaceAccessSliceReadiness(
            capability_id=item.capability_id,
            state=item.state,
            detail=item.detail,
            interaction=item.interaction,
            policy=item.policy,
            bundle=item.bundle,
        )
        for item in review.allowed_slices
    )
    return WorkspaceAccessReadiness(
        region_id=region_id,
        access_scope=access_scope,
        access_kind="review",
        route_authorized=True,
        access_classification=review.access_classification,
        trust_state=review.trust_state,
        capabilities=review.capabilities,
        slices=slices,
        review=review,
    )


def _product_slice(
    region_id: str,
    analysis_id: str,
    capability: WorkspaceCapabilityReadiness,
) -> WorkspaceAccessSliceReadiness | None:
    group_prefix = f"{analysis_id}.group."
    if not capability.capability_id.startswith(group_prefix):
        raise ValueError("Product group capability has the wrong analysis identity")
    if not capability.layer_ids:
        return None
    group_id = capability.capability_id.removeprefix(group_prefix)
    contract = load_analysis(region_id, analysis_id)
    layers = tuple(contract.layers.get(layer_id) for layer_id in capability.layer_ids)
    if any(layer is None for layer in layers):
        raise ValueError("Product readiness references an undeclared analysis layer")
    typed_layers = tuple(layer for layer in layers if layer is not None)
    if any(layer.group_id != group_id for layer in typed_layers):
        raise ValueError("Product readiness mixes layers from different groups")
    operations = tuple(dict.fromkeys(layer.operation for layer in typed_layers))
    if len(operations) != 1:
        raise ValueError("A workspace control group must use one operation")
    parameter_sets = tuple(tuple(layer.parameters) for layer in typed_layers)
    parameter_ids = parameter_sets[0]
    if any(value != parameter_ids for value in parameter_sets[1:]):
        raise ValueError("A workspace control group must share one parameter contract")
    policy = ReviewSlicePolicy(
        analysis_id=analysis_id,
        group_id=group_id,
        apply_required=True,
        auto_select_sources=True,
        explicit_parameters=parameter_ids,
    )
    return WorkspaceAccessSliceReadiness(
        capability_id=capability.capability_id,
        state=capability.state,
        detail=capability.detail,
        interaction=capability.interaction,
        policy=policy,
        bundle=WorkspaceReviewSliceBundle(
            region_id=region_id,
            analysis_id=analysis_id,
            group_id=group_id,
            layer_ids=capability.layer_ids,
            operations=operations,
            parameter_ids=parameter_ids,
        ),
    )


def _product_access_readiness(
    region_id: str,
    access_scope: str,
) -> WorkspaceAccessReadiness:
    profile = load_workspace_profile(region_id)
    group_capabilities: dict[str, WorkspaceCapabilityReadiness] = {}
    for analysis_id in profile.technologies:
        for item in resolve_catalog_workspace_product_group_availability(
            region_id,
            analysis_id,
        ):
            canonical_state = "public" if item.state == "available" else item.state
            group_capabilities[item.capability_id] = WorkspaceCapabilityReadiness(
                capability_id=item.capability_id,
                state=canonical_state,
                detail=item.detail,
                interaction=item.interaction,
                layer_ids=item.layer_ids,
            )

    capabilities: list[WorkspaceCapabilityReadiness] = []
    slices: list[WorkspaceAccessSliceReadiness] = []
    non_group_capabilities: dict[str, WorkspaceCapabilityReadiness] | None = None
    for capability_id in profile.capabilities:
        if ".group." in capability_id:
            capability = group_capabilities.get(capability_id)
            if capability is None:
                raise ValueError(
                    f"Product group readiness omitted {capability_id}"
                )
            analysis_id = capability_id.split(".group.", 1)[0]
            slice_readiness = _product_slice(
                region_id,
                analysis_id,
                capability,
            )
            if slice_readiness is not None:
                slices.append(slice_readiness)
        else:
            if non_group_capabilities is None:
                non_group_capabilities = {
                    item.capability_id: item
                    for item in _resolve_catalog_workspace_product_capabilities_readiness(
                        region_id,
                        tuple(
                            item for item in profile.capabilities
                            if ".group." not in item
                        ),
                    )
                }
            capability = non_group_capabilities[capability_id]
        capabilities.append(capability)

    capability_ids = tuple(item.capability_id for item in capabilities)
    if capability_ids != profile.capabilities:
        raise ValueError("Product readiness drifted from workspace-profile order")
    return WorkspaceAccessReadiness(
        region_id=region_id,
        access_scope=access_scope,
        access_kind="product",
        route_authorized=True,
        access_classification="public_product",
        trust_state="public",
        capabilities=tuple(capabilities),
        slices=tuple(slices),
    )


def resolve_catalog_workspace_access_readiness(
    region_id: str,
    access_scope: str,
    *,
    route_authorized: bool,
) -> WorkspaceAccessReadiness:
    """Resolve one explicit route through a single profile-ordered contract."""

    normalized_region_id, access_kind = _scope(region_id, access_scope)
    if not isinstance(route_authorized, bool):
        raise TypeError("Workspace route authorization must be boolean")
    if not route_authorized:
        raise PermissionError("Workspace route is not authorized")
    if access_kind == "review":
        return _review_access_readiness(normalized_region_id, access_scope)
    return _product_access_readiness(normalized_region_id, access_scope)


__all__ = [
    "WorkspaceAccessReadiness",
    "WorkspaceAccessSliceReadiness",
    "resolve_catalog_workspace_access_readiness",
]
