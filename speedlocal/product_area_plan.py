"""Exact product area authority, independent of optional source/buffer display.

Only trusted area factories construct this internal immutable plan. External
execution graphs retain their complete public parsers and validation.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable

from .workspace_execution import (
    WorkspaceAnalysisExecutionInput,
    WorkspaceAreaExecution,
    WorkspaceExecutionState,
    parse_workspace_analysis_execution_input,
    retarget_catalog_workspace_execution_inputs,
)
from .workspace_area import WorkspaceAreaExecutionResult


@dataclass(frozen=True)
class ProductAreaBinding:
    execution_input: WorkspaceAnalysisExecutionInput
    area_result: WorkspaceAreaExecutionResult

    @property
    def request(self):
        return self.execution_input.request


@dataclass(frozen=True)
class ProductAreaBundle:
    region_id: str
    access_scope: str
    target_resolution: int
    bindings: tuple[ProductAreaBinding, ...]

    def binding(self, analysis_id: str) -> ProductAreaBinding:
        matches = tuple(b for b in self.bindings if b.request.analysis_id == analysis_id)
        if len(matches) != 1:
            raise ValueError("Area bundle requires one exact analysis binding")
        return matches[0]


@dataclass(frozen=True)
class ProductAreaResolutionPlan:
    region_id: str
    access_scope: str
    display_resolution: int
    analysis_resolution: int
    execution_inputs: tuple[WorkspaceAnalysisExecutionInput, ...]
    analysis_bundle: ProductAreaBundle
    display_bundle: ProductAreaBundle

    @property
    def analysis_ids(self) -> tuple[str, ...]:
        return tuple(value.request.analysis_id for value in self.execution_inputs)

    @property
    def reuses_analysis_bundle(self) -> bool:
        return self.analysis_bundle is self.display_bundle


def validate_product_area_bundle(bundle, expected_inputs, resolution):
    """Check cached trusted bindings against the current authorized inputs."""
    if not isinstance(bundle, ProductAreaBundle) or not expected_inputs:
        raise ValueError("Expected an immutable product area bundle")
    first = expected_inputs[0].request
    if (bundle.region_id != first.region_id or bundle.access_scope != first.access_scope
            or bundle.target_resolution != resolution
            or tuple(b.execution_input for b in bundle.bindings) != expected_inputs):
        raise ValueError("Product area bundle escaped its current inputs")
    for binding in bundle.bindings:
        result = binding.area_result
        if (not isinstance(result, WorkspaceAreaExecutionResult)
                or result.request != binding.request
                or result.technology != binding.request.analysis_id
                or result.target_resolution != resolution):
            raise ValueError("Product area result escaped its current request")


def build_product_area_plan(
    input_jsons: tuple[str, ...],
    display_resolution: int,
    analysis_resolution: int,
    runtime_token: str,
    area_factory: Callable[[str, str], WorkspaceAreaExecutionResult],
) -> ProductAreaResolutionPlan:
    if (type(runtime_token) is not str or len(runtime_token) != 64
            or any(c not in "0123456789abcdef" for c in runtime_token)):
        raise ValueError("Area plan requires a current runtime identity")
    if type(input_jsons) is not tuple or not input_jsons:
        raise ValueError("Area plan requires immutable execution inputs")
    inputs = tuple(parse_workspace_analysis_execution_input(json.loads(v)) for v in input_jsons)
    if any(v.execution_state is not WorkspaceExecutionState.APPLIED
           or v.area_execution is not WorkspaceAreaExecution.EXECUTE for v in inputs):
        raise ValueError("Product area plan requires applied authorized analyses")
    # Retargeting validates unique analyses, region/scope, H3 resolutions and
    # current catalog authorization before any area factory is called.
    analysis_inputs = retarget_catalog_workspace_execution_inputs(inputs, analysis_resolution)
    display_inputs = (analysis_inputs if display_resolution == analysis_resolution
                      else retarget_catalog_workspace_execution_inputs(inputs, display_resolution))
    first = inputs[0].request

    def bundle(values, resolution):
        bindings = tuple(ProductAreaBinding(value, area_factory(
            json.dumps(value.request.as_dict(), ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")), runtime_token)) for value in values)
        result = ProductAreaBundle(first.region_id, first.access_scope, resolution, bindings)
        validate_product_area_bundle(result, values, resolution)
        return result

    analysis_bundle = bundle(analysis_inputs, analysis_resolution)
    display_bundle = (analysis_bundle if display_inputs is analysis_inputs
                      else bundle(display_inputs, display_resolution))
    return ProductAreaResolutionPlan(first.region_id, first.access_scope,
        display_resolution, analysis_resolution, inputs, analysis_bundle, display_bundle)
