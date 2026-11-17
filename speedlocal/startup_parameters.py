"""Configured initial workspace choices, separate from analytical defaults."""

from __future__ import annotations

import json
from dataclasses import replace

from .catalogs import load_region
from .contracts import AnalysisContract
from .paths import resolve_source_path


def load_workspace_start_parameters(
    contract: AnalysisContract,
) -> dict[str, float]:
    """Validate initial group distances without changing sources or contracts.

    Callers seed only absent draft values. Existing applied requests and user
    edits retain their values. A declared but invalid configuration fails closed.
    """

    region = load_region(contract.region_id)
    reference = region.get("workspace_start_parameters")
    if reference is None:
        return {}
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("Workspace start parameters require a repository path")
    path = resolve_source_path("repo", reference)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(raw, dict)
        or set(raw) != {"schema_version", "technologies"}
        or raw["schema_version"] != "1.0"
        or not isinstance(raw["technologies"], dict)
        or set(raw["technologies"]) != {"wind", "solar"}
    ):
        raise ValueError("Invalid workspace start parameter configuration")
    values = raw["technologies"].get(contract.id)
    if not isinstance(values, dict) or set(values) != set(contract.groups):
        raise ValueError("Start distances must match the declared analysis groups")
    result = {}
    for group_id, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Workspace start distances must be numeric metres")
        layers = [layer for layer in contract.layers.values()
                  if layer.group_id == group_id]
        if not layers:
            raise ValueError("Workspace start group has no declared layers")
        for layer in layers:
            parameter = layer.parameters.get("buffer_m")
            if parameter is None or parameter.unit != "m":
                raise ValueError("Workspace start group requires a metric buffer")
            # Parameter construction checks finite values, bounds and step
            # alignment, while retaining the original analytical contract.
            replace(parameter, default=float(value))
        result[group_id] = float(value)
    return result
