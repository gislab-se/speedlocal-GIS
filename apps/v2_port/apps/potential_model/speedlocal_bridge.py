from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

import h3
import pandas as pd

from speedlocal.area_result import (
    TechnologyAreaResult,
    build_area_group_preview,
    run_area_analysis,
)
from speedlocal.catalogs import load_analysis, load_region
from speedlocal.contracts import (
    AnalysisContract,
    ParameterContract,
    RooftopSolarContract,
)
from speedlocal.distributed_generation import (
    RooftopSolarAccountingResult,
    calculate_rooftop_solar_accounting,
    load_rooftop_population_counts,
)
from speedlocal.engine import run_analysis
from speedlocal.geometry import (
    VectorBufferPreview,
    build_vector_buffer_preview,
)
from speedlocal.postgis_domain_inputs import DomainDisplayPayload
from speedlocal.sources import (
    read_analysis_domain_input,
    eligible_surface_level,
    read_layer_geojson,
    resolve_analysis_domain_cell_areas_km2,
    resolve_analysis_domain_cell_ids,
    resolve_eligible_surface_cell_areas_km2,
    resolve_eligible_surface_path,
    resolve_standard_result_surface_cell_areas_km2,
    resolve_support_observations,
    resolve_technology_context_path,
)
from speedlocal.validation import (
    validate_contract,
    validate_layer,
    validate_technology_support_binding,
)
from speedlocal.workspace import load_workspace_profile
from speedlocal.workspace_area import (
    WorkspaceAreaExecutionResult,
    validate_workspace_area_execution_result,
)
from speedlocal.workspace_request import (
    WorkspaceAnalysisRequest,
    authorize_catalog_workspace_analysis_request,
)


CANONICAL_ROADS_GROUP_ID = "roads"
CANONICAL_POPULATION_GROUP_ID = "population"
CANONICAL_NATURE_GROUP_ID = "nature"
CANONICAL_CULTURE_GROUP_ID = "culture"
CANONICAL_GRID_GROUP_ID = "grid_infrastructure"
CANONICAL_DISTANCE_OPERATIONS = {
    "distance_exclusion",
    "hard_exclusion",
    "proximity_feasibility",
}
CANONICAL_TO_TRANSITIONAL_GROUP_ID = {
    "nature": "protected",
    "culture": "culture",
    "grid_infrastructure": "electrical",
}
WORKSPACE_AREA_FRAME_SCHEMA_LEGACY_WIND = "legacy_wind_frame"
WORKSPACE_AREA_FRAME_SCHEMA_WORKSPACE = "workspace_frame"
_WORKSPACE_AREA_FRAME_COLUMNS = (
    "hex_id",
    "display_area_km2",
    "potential_area_km2",
    "potential_area_share_pct",
)
_WORKSPACE_AREA_FRAME_DTYPES = {
    "hex_id": pd.StringDtype(na_value=float("nan")),
    "display_area_km2": pd.api.types.pandas_dtype("float64"),
    "potential_area_km2": pd.api.types.pandas_dtype("float64"),
    "potential_area_share_pct": pd.api.types.pandas_dtype("float64"),
}


@dataclass(frozen=True)
class WindLayerControlContract:
    id: str
    group_id: str
    label: str
    note: str
    source_color: tuple[int, int, int]
    point_radius: int
    quality_flag: str | None
    ready: bool
    message: str


@dataclass(frozen=True)
class WindGroupControlContract:
    id: str
    canonical_id: str
    label: str
    analysis_kind: str
    analysis_label: str
    analysis_min_m: int
    analysis_max_m: int
    analysis_step_m: int
    analysis_default_m: int
    blend_default: int
    group_color: tuple[int, int, int]
    interpretation: str
    expanded_by_default: bool
    source_map_default_visible: bool
    layers: tuple[WindLayerControlContract, ...]


# Compatibility names for downstream code that imported the roads-only bridge.
RoadLayerControlContract = WindLayerControlContract
RoadGroupControlContract = WindGroupControlContract


def _hex_color_to_rgb(value: str) -> tuple[int, int, int]:
    normalized = str(value).strip().removeprefix("#")
    if len(normalized) != 6:
        raise ValueError(f"Invalid manifest UI color: {value!r}")
    return tuple(
        int(normalized[offset : offset + 2], 16)
        for offset in (0, 2, 4)
    )


def _validated_analysis(
    region_id: str,
    analysis_id: str,
) -> AnalysisContract:
    analysis = load_analysis(str(region_id), str(analysis_id))
    validate_contract(analysis)
    return analysis


def _validated_wind_analysis(region_id: str) -> AnalysisContract:
    return _validated_analysis(region_id, "wind")


def _validated_area_analysis(
    region_id: str,
    technology: str,
) -> AnalysisContract:
    analysis = _validated_analysis(region_id, technology)
    if analysis.area_result is None:
        raise ValueError(
            f"{region_id}/{technology} has no area-result contract"
        )
    if analysis.area_result.technology != str(technology):
        raise ValueError(
            f"{region_id}/{technology} declares area technology "
            f"{analysis.area_result.technology}"
        )
    validate_technology_support_binding(analysis)
    return analysis


def technology_support_domain_resolution(
    region_id: str,
    technology: str,
) -> int:
    """Return one technology's explicit eligible-support resolution."""

    analysis = _validated_area_analysis(region_id, technology)
    if analysis.area_result is None:
        raise ValueError(
            f"{region_id}/{technology} has no area-result contract"
        )
    surface = analysis.eligible_surfaces.get(
        analysis.area_result.eligible_surface_id
    )
    if surface is None:
        raise ValueError(
            f"{region_id}/{technology} has no eligible-surface contract"
        )
    return int(surface.resolution)


def technology_support_domain_cell_areas_km2(
    region_id: str,
    technology: str,
    resolution: int | None = None,
) -> dict[str, float]:
    """Return exact eligible-support areas in square kilometres."""

    analysis = _validated_area_analysis(region_id, technology)
    return resolve_eligible_surface_cell_areas_km2(analysis, resolution)


def shared_technology_context_manifest_overlay(
    region_id: str,
) -> dict[str, object]:
    """Bind the active app manifest to the typed wind/solar context source."""

    from speedlocal.context_runtime import catalog_context_runtime_declared, load_catalog_context_inputs

    database_bound = catalog_context_runtime_declared(region_id)
    declared_bindings: list[dict[str, object]] = []
    resolved_paths: list[Path] = []
    for technology in ("wind", "solar"):
        analysis = _validated_area_analysis(region_id, technology)
        surface = analysis.eligible_surfaces[
            analysis.area_result.eligible_surface_id  # type: ignore[union-attr]
        ]
        context = surface.technology_context
        if not database_bound:
            resolved_paths.append(resolve_technology_context_path(analysis).resolve())
        declared_bindings.append(
            {
                "id": context.id,
                "provider": context.provider,
                "path": context.path,
                "sha256": context.sha256,
                "id_field": context.id_field,
                "cell_kind": context.cell_kind,
                "resolution": context.resolution,
                "expected_cell_count": context.expected_cell_count,
                "cell_ids_sha256": context.cell_ids_sha256,
                "missing_policy": context.missing_policy,
            }
        )
    if declared_bindings[0] != declared_bindings[1]:
        raise ValueError(
            f"{region_id} combined result requires one shared wind/solar "
            "technology-context contract"
        )
    if resolved_paths and resolved_paths[0] != resolved_paths[1]:
        raise ValueError(
            f"{region_id} combined result resolved different wind/solar "
            "technology-context sources"
        )

    if database_bound:
        snapshot = load_catalog_context_inputs(region_id).technology_context
        if snapshot.source_sha256 != declared_bindings[0]["sha256"]:
            raise ValueError("Current technology context does not match its declaration")
    binding = declared_bindings[0]
    contract_sha256 = hashlib.sha256(
        json.dumps(
            binding,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        **({"full_lablab_source_geojson": str(resolved_paths[0])} if resolved_paths else {}),
        "full_lablab_source_sha256": str(binding["sha256"]),
        "full_lablab_feature_count": int(binding["expected_cell_count"]),
        "full_lablab_cell_ids_sha256": str(binding["cell_ids_sha256"]),
        "full_lablab_source_h3_resolution": int(binding["resolution"]),
        "full_lablab_source_id_field": str(binding["id_field"]),
        "full_lablab_missing_policy": str(binding["missing_policy"]),
        "full_lablab_contract_sha256": contract_sha256,
    }


def technology_support_observation_frame(
    region_id: str,
    technology: str,
    layer_ids: Collection[str],
    target_resolution: int,
) -> pd.DataFrame:
    """Return complete technical observations on the eligible support domain."""

    analysis = _validated_area_analysis(region_id, technology)
    requested = tuple(str(layer_id).strip() for layer_id in layer_ids)
    if not requested or any(not layer_id for layer_id in requested):
        raise ValueError("Technology-support observation layers are required")
    if len(requested) != len(set(requested)):
        raise ValueError(
            "Technology-support observation request contains duplicate layers"
        )
    surface = analysis.eligible_surfaces[
        analysis.area_result.eligible_surface_id  # type: ignore[union-attr]
    ]
    target = int(target_resolution)
    level = eligible_surface_level(analysis, target)
    read_analysis_domain_input(analysis, "technology_support", target)
    frames: list[pd.DataFrame] = []
    for layer_id in requested:
        source = analysis.layers[layer_id].source
        rows = resolve_support_observations(analysis, layer_id)
        layer_frame = pd.DataFrame(
            (
                {
                    "hex_id": row.cell_id,
                    "distance_m": source.total_observation_distance_m(row.distance_m, row.intersects),
                    "intersects": row.intersects,
                }
                for row in rows
            )
        )
        if target < surface.resolution:
            layer_frame["hex_id"] = layer_frame["hex_id"].map(
                lambda value: str(h3.cell_to_parent(str(value), target))
            )
            layer_frame = (
                layer_frame.groupby("hex_id", as_index=False)
                .agg(
                    distance_m=("distance_m", "min"),
                    intersects=("intersects", "max"),
                )
            )
        elif target != surface.resolution:
            raise ValueError(
                f"Technology-support observations cannot expand R"
                f"{surface.resolution} to R{target}"
            )
        frames.append(layer_frame)
    combined = pd.concat(frames, ignore_index=True)
    combined = (
        combined.groupby("hex_id", as_index=False)
        .agg(
            distance_m=("distance_m", "min"),
            intersects=("intersects", "max"),
        )
        .sort_values("hex_id")
        .reset_index(drop=True)
    )
    if len(combined) != level.expected_cell_count:
        raise ValueError(
            f"Technology-support observation rollup has {len(combined)} "
            f"R{target} cells; expected {level.expected_cell_count}"
        )
    if combined["hex_id"].duplicated().any() or combined[
        ["distance_m", "intersects"]
    ].isna().any().any():
        raise ValueError(
            "Technology-support observation rollup is incomplete or duplicated"
        )
    return combined[["hex_id", "distance_m", "intersects"]].copy()


def standard_analysis_domain_cell_ids(
    region_id: str,
    resolution: int | None = None,
) -> tuple[str, ...]:
    """Return the frozen-parity standard-group cell universe."""

    analysis = _validated_wind_analysis(region_id)
    return resolve_analysis_domain_cell_ids(analysis, resolution)


def standard_analysis_domain_cell_areas_km2(
    region_id: str,
    resolution: int | None = None,
) -> dict[str, float]:
    """Return frozen-parity standard-group domain areas."""

    analysis = _validated_wind_analysis(region_id)
    return resolve_analysis_domain_cell_areas_km2(analysis, resolution)


def standard_result_surface_cell_areas_km2(
    region_id: str,
    resolution: int | None = None,
) -> dict[str, float]:
    """Return the checksum-pinned frozen standard-group result areas."""

    analysis = _validated_wind_analysis(region_id)
    return resolve_standard_result_surface_cell_areas_km2(
        analysis,
        resolution,
    )


def wind_analysis_domain_resolution(region_id: str) -> int:
    """Compatibility alias for the wind technology-support resolution."""

    return technology_support_domain_resolution(region_id, "wind")


def wind_analysis_domain_cell_areas_km2(
    region_id: str,
    resolution: int | None = None,
) -> dict[str, float]:
    """Compatibility alias for frozen standard-group result areas."""

    return standard_result_surface_cell_areas_km2(
        region_id,
        resolution,
    )


def shared_area_display_geometry_path(
    region_id: str,
    resolution: int,
) -> str | DomainDisplayPayload:
    """Return one verified eligible geometry shared by wind and solar."""

    analyses = tuple(_validated_area_analysis(region_id, technology)
                     for technology in ("wind", "solar"))
    bound = tuple(any(layer.source.postgis_reference is not None
                      for layer in analysis.layers.values()) for analysis in analyses)
    if any(bound):
        if not all(bound):
            raise ValueError("Combined geometry requires one complete runtime binding")
        payloads = tuple(read_analysis_domain_input(
            analysis, "technology_support", int(resolution)
        ) for analysis in analyses)
        identity = lambda payload: (
            payload.region_id, payload.domain_id, payload.role, payload.resolution,
            payload.upstream_source_sha256, payload.payload_sha256,
            payload.runtime_revision_sha256,
        )
        if identity(payloads[0]) != identity(payloads[1]):
            raise ValueError("Combined technologies resolved different eligible geometry")
        return payloads[0]

    paths: list[Path] = []
    for technology in ("wind", "solar"):
        analysis = _validated_area_analysis(region_id, technology)
        paths.append(
            resolve_eligible_surface_path(analysis, int(resolution)).resolve()
        )
    if paths[0] != paths[1]:
        raise ValueError(
            f"{region_id} combined result requires one shared wind/solar "
            "eligible surface"
        )
    return str(paths[0])


def technology_area_result_frame(
    region_id: str,
    technology: str,
    layer_ids: Collection[str],
    group_buffer_m: dict[str, float],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt one exact manifest-declared technology area to V2 Final."""

    analysis = _validated_area_analysis(region_id, technology)
    requested = tuple(str(layer_id) for layer_id in layer_ids)
    if len(requested) != len(set(requested)):
        raise ValueError("A wind area-result request contains duplicate layers")
    unknown = set(requested) - set(analysis.layers)
    if unknown:
        raise ValueError(
            f"{region_id}/{technology} has no canonical area-result layers: "
            f"{sorted(unknown)}"
        )
    ordered = tuple(
        layer_id for layer_id in analysis.layers if layer_id in set(requested)
    )
    parameters: dict[str, dict[str, float]] = {}
    for layer_id in ordered:
        layer = analysis.layers[layer_id]
        if layer.group_id not in group_buffer_m:
            raise ValueError(
                f"{technology.title()} area-result group {layer.group_id} "
                "has no applied distance"
            )
        parameters[layer_id] = {
            "buffer_m": float(group_buffer_m[layer.group_id]),
        }
    result = run_area_analysis(
        region=str(region_id),
        analysis=str(technology),
        layers=ordered,
        parameters=parameters,
        target_resolution=target_resolution,
    )
    return _technology_area_result_frame(result)


def _technology_area_result_frame(
    result: TechnologyAreaResult,
) -> pd.DataFrame:
    """Adapt one validated ``TechnologyAreaResult`` without changing it."""

    frame = pd.DataFrame(
        (
            {
                "hex_id": cell.cell_id,
                "display_area_km2": cell.model_area_km2,
                "potential_area_km2": cell.remaining_area_km2,
                "potential_area_share_pct": cell.potential_pct,
            }
            for cell in result.cells
        )
    )
    if frame.empty or frame["hex_id"].duplicated().any():
        raise ValueError("Canonical technology area result is empty or duplicated")
    frame.attrs["area_result"] = {
        "technology": result.technology,
        "active_group_ids": result.active_group_ids,
        "selected_layer_ids": result.selected_layer_ids,
        "model_area_km2": result.model_area_km2,
        "remaining_area_km2": result.remaining_area_km2,
        "potential_pct": result.potential_pct,
        "resolution": result.resolution,
    }
    return frame.sort_values("hex_id").reset_index(drop=True)


def adapt_workspace_area_execution_result_frame(
    result: WorkspaceAreaExecutionResult,
    *,
    output_schema: str,
) -> pd.DataFrame:
    """Adapt one signed area result to an exact legacy bridge schema.

    This temporary compatibility boundary copies the immutable engine values;
    it must not recalculate, aggregate, round, or otherwise reinterpret them.
    """

    validate_workspace_area_execution_result(result)
    if not isinstance(output_schema, str):
        raise TypeError("output_schema must be a string")
    if output_schema not in {
        WORKSPACE_AREA_FRAME_SCHEMA_LEGACY_WIND,
        WORKSPACE_AREA_FRAME_SCHEMA_WORKSPACE,
    }:
        raise NotImplementedError(
            f"Unsupported workspace area frame schema: {output_schema!r}"
        )
    if result.technology != result.analysis_id:
        raise ValueError(
            "Workspace area frame technology drifted from its analysis"
        )
    if (
        output_schema == WORKSPACE_AREA_FRAME_SCHEMA_LEGACY_WIND
        and result.technology != "wind"
    ):
        raise ValueError(
            "The legacy wind frame schema requires a signed wind result"
        )

    frame = pd.DataFrame(
        (
            {
                "hex_id": cell.cell_id,
                "display_area_km2": cell.model_area_km2,
                "potential_area_km2": cell.remaining_area_km2,
                "potential_area_share_pct": cell.potential_pct,
            }
            for cell in result.cells
        ),
        columns=_WORKSPACE_AREA_FRAME_COLUMNS,
    ).astype(_WORKSPACE_AREA_FRAME_DTYPES)
    if (
        frame.empty
        or len(frame) != result.cell_count
        or frame["hex_id"].duplicated().any()
    ):
        raise ValueError(
            "Signed workspace area result is empty, incomplete, or duplicated"
        )
    frame.attrs["area_result"] = {
        "technology": result.technology,
        "active_group_ids": result.active_group_ids,
        "selected_layer_ids": result.selected_layer_ids,
        "model_area_km2": result.model_area_km2,
        "remaining_area_km2": result.remaining_area_km2,
        "potential_pct": result.potential_pct,
        "resolution": result.target_resolution,
    }
    if output_schema == WORKSPACE_AREA_FRAME_SCHEMA_WORKSPACE:
        frame.attrs["workspace_request"] = result.request.as_dict()

    frame = frame.sort_values("hex_id").reset_index(drop=True)
    if (
        tuple(frame.columns) != _WORKSPACE_AREA_FRAME_COLUMNS
        or any(
            frame.dtypes[column] != dtype
            for column, dtype in _WORKSPACE_AREA_FRAME_DTYPES.items()
        )
        or not isinstance(frame.index, pd.RangeIndex)
    ):
        raise RuntimeError("Workspace area frame output schema drifted")
    return frame


def workspace_area_result_frame(
    request: WorkspaceAnalysisRequest,
) -> pd.DataFrame:
    """Run one catalog-authorized wind or solar request as an exact area result."""

    if not isinstance(request, WorkspaceAnalysisRequest):
        raise TypeError("request must be a WorkspaceAnalysisRequest")
    authorize_catalog_workspace_analysis_request(
        request,
        required_capability_id=f"{request.analysis_id}.area",
    )
    analysis = _validated_area_analysis(
        request.region_id,
        request.analysis_id,
    )
    area_result = analysis.area_result
    if area_result is None:
        raise ValueError(
            f"{request.region_id}/{request.analysis_id} has no area-result "
            "contract"
        )
    applicable_group_ids = set(area_result.applicable_group_ids)
    outside_area_contract = tuple(
        group.group_id
        for group in request.groups
        if group.group_id not in applicable_group_ids
    )
    if outside_area_contract:
        raise ValueError(
            f"{request.region_id}/{request.analysis_id} request contains "
            "groups outside its area-result contract: "
            f"{list(outside_area_contract)}"
        )
    result = run_area_analysis(
        region=request.region_id,
        analysis=request.analysis_id,
        layers=request.selected_layer_ids,
        parameters=request.engine_parameters(),
        target_resolution=request.target_resolution,
    )
    expected_group_ids = tuple(group.group_id for group in request.groups)
    if (
        result.region_id != request.region_id
        or result.analysis_id != request.analysis_id
        or result.technology != request.analysis_id
        or result.resolution != request.target_resolution
        or result.selected_layer_ids != request.selected_layer_ids
        or result.active_group_ids != expected_group_ids
    ):
        raise ValueError(
            "Workspace area result drifted from its authorized request"
        )
    frame = _technology_area_result_frame(result)
    frame.attrs["workspace_request"] = request.as_dict()
    return frame


def wind_area_result_frame(
    region_id: str,
    layer_ids: Collection[str],
    group_buffer_m: dict[str, float],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt the exact manifest-declared wind area result to V2 Final."""

    return technology_area_result_frame(
        region_id,
        "wind",
        layer_ids,
        group_buffer_m,
        target_resolution,
    )


def solar_area_result_frame(
    region_id: str,
    layer_ids: Collection[str],
    group_buffer_m: dict[str, float],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt the exact manifest-declared solar area result to V2 Final."""

    return technology_area_result_frame(
        region_id,
        "solar",
        layer_ids,
        group_buffer_m,
        target_resolution,
    )


def solar_rooftop_contract(region_id: str) -> RooftopSolarContract:
    """Return the validated manifest-declared rooftop planning proxy."""

    analysis = _validated_area_analysis(region_id, "solar")
    distributed_generation = analysis.distributed_generation
    rooftop = (
        distributed_generation.rooftop_solar
        if distributed_generation is not None
        else None
    )
    if rooftop is None:
        raise ValueError(
            f"{region_id}/solar has no rooftop-solar accounting contract"
        )
    return rooftop


def solar_rooftop_population_frame(
    region_id: str,
    target_resolution: int | None = None,
) -> pd.DataFrame:
    """Load the rooftop proxy's manifest-pinned population counts."""

    analysis = _validated_area_analysis(region_id, "solar")
    distributed_generation = analysis.distributed_generation
    rooftop = (
        distributed_generation.rooftop_solar
        if distributed_generation is not None
        else None
    )
    if rooftop is None:
        raise ValueError(
            f"{region_id}/solar has no rooftop-solar accounting contract"
        )
    canonical_resolution = rooftop.population_source.analysis_h3_resolution
    domain_ids = resolve_analysis_domain_cell_ids(
        analysis,
        canonical_resolution,
    )
    from speedlocal.context_runtime import catalog_context_runtime_declared, load_catalog_context_inputs
    if catalog_context_runtime_declared(region_id):
        from speedlocal.distributed_generation import rooftop_population_counts_from_raw_frame
        snapshot = load_catalog_context_inputs(region_id).rooftop_population
        if snapshot is None:
            raise ValueError("Declared rooftop population is missing from the current runtime")
        return rooftop_population_counts_from_raw_frame(rooftop.population_source,
            snapshot.raw_frame(rooftop.population_source), domain_ids, target_resolution)
    return load_rooftop_population_counts(
        rooftop.population_source,
        domain_ids,
        target_resolution,
    )


def solar_rooftop_accounting(
    region_id: str,
    population: float,
    panel_area_m2_per_person: float,
    gross_solar_target_twh: float,
    ground_km2_per_twh: float,
) -> RooftopSolarAccountingResult:
    """Calculate residual ground-solar demand from the canonical contract."""

    return calculate_rooftop_solar_accounting(
        solar_rooftop_contract(region_id),
        population,
        panel_area_m2_per_person,
        gross_solar_target_twh,
        ground_km2_per_twh,
    )


def area_applicable_group_ids(
    region_id: str,
    technology: str,
) -> tuple[str, ...]:
    """Return one technology's manifest-declared area groups in order."""

    analysis = _validated_area_analysis(region_id, technology)
    return tuple(analysis.area_result.applicable_group_ids)


def analysis_group_layer_ids(
    region_id: str,
    analysis_id: str,
    group_id: str,
) -> tuple[str, ...]:
    """Return preview-compatible layers for one applicable area group."""

    analysis = _validated_area_analysis(region_id, analysis_id)
    canonical_group_id = str(group_id)
    if canonical_group_id not in analysis.area_result.applicable_group_ids:
        raise ValueError(
            f"{region_id}/{analysis_id} does not apply group "
            f"{canonical_group_id!r}"
        )
    layer_ids = tuple(
        layer.id
        for layer in analysis.layers.values()
        if layer.group_id == canonical_group_id
        and layer.operation in CANONICAL_DISTANCE_OPERATIONS
        and layer.source.source_geometry_required
    )
    if not layer_ids:
        raise ValueError(
            f"{region_id}/{analysis_id} declares no preview-compatible "
            f"{canonical_group_id} layers"
        )
    return layer_ids


def _control_group_layer_ids(
    analysis: AnalysisContract,
    canonical_group_id: str,
) -> tuple[str, ...]:
    """Return control-compatible layers without requiring an area result."""

    group_id = str(canonical_group_id)
    if group_id not in analysis.groups:
        raise ValueError(
            f"{analysis.region_id}/{analysis.id} does not declare group "
            f"{group_id!r}"
        )
    layer_ids = tuple(
        layer.id
        for layer in analysis.layers.values()
        if layer.group_id == group_id
        and layer.operation in CANONICAL_DISTANCE_OPERATIONS
        and layer.source.source_geometry_required
    )
    if not layer_ids:
        raise ValueError(
            f"{analysis.region_id}/{analysis.id} declares no "
            f"control-compatible {group_id} layers"
        )
    return layer_ids


def _shared_group_buffer_parameter_contract(
    analysis: AnalysisContract,
    canonical_group_id: str,
    layer_ids: Collection[str],
) -> ParameterContract:
    """Return the one buffer contract shared by a control group's layers."""

    parameters: list[ParameterContract] = []
    for layer_id in layer_ids:
        layer = analysis.layers.get(str(layer_id))
        if layer is None:
            raise KeyError(
                f"{analysis.region_id}/{analysis.id} is missing canonical "
                f"{canonical_group_id} layer: {layer_id}"
            )
        if (
            layer.group_id != canonical_group_id
            or layer.operation not in CANONICAL_DISTANCE_OPERATIONS
        ):
            raise ValueError(
                f"{analysis.region_id}/{analysis.id} layer {layer_id} is not "
                f"a canonical {canonical_group_id} distance-based layer"
            )
        parameter = layer.parameters.get("buffer_m")
        if parameter is None:
            raise KeyError(
                f"{analysis.region_id}/{analysis.id} layer {layer_id} has no "
                "buffer_m"
            )
        parameters.append(parameter)

    signatures = {
        (
            item.value_type,
            item.unit,
            item.default,
            item.minimum,
            item.maximum,
            item.step,
        )
        for item in parameters
    }
    if len(signatures) != 1:
        raise ValueError(
            f"{analysis.region_id}/{analysis.id} {canonical_group_id} layers "
            "do not share one buffer contract"
        )
    return parameters[0]


def public_wind_group_ids(region_id: str) -> tuple[str, ...]:
    """Return canonical ids for migrated groups and adapter ids for the rest."""
    analysis = _validated_wind_analysis(region_id)
    group_ids: list[str] = []
    for group_id in analysis.groups:
        if group_id in {
            CANONICAL_ROADS_GROUP_ID,
            CANONICAL_POPULATION_GROUP_ID,
        }:
            group_ids.append(group_id)
            continue
        if group_id in {
            CANONICAL_NATURE_GROUP_ID,
            CANONICAL_CULTURE_GROUP_ID,
            CANONICAL_GRID_GROUP_ID,
        } and any(
            layer.group_id == group_id for layer in analysis.layers.values()
        ):
            group_ids.append(group_id)
            continue
        transitional_id = CANONICAL_TO_TRANSITIONAL_GROUP_ID.get(group_id)
        if transitional_id is not None:
            group_ids.append(transitional_id)
    return tuple(group_ids)


def canonical_wind_group_is_declared(
    region_id: str,
    group_id: str,
) -> bool:
    """Return whether a canonical group has manifest-declared layers."""
    analysis = _validated_wind_analysis(region_id)
    return any(
        layer.group_id == str(group_id)
        for layer in analysis.layers.values()
    )


def default_wind_layer_selection(region_id: str) -> dict[str, list[str]]:
    """Return the manifest startup request in current public group ids."""
    analysis = _validated_wind_analysis(region_id)
    if analysis.default_request is None:
        raise ValueError(f"{region_id}/wind has no default_request")

    selected: dict[str, list[str]] = {
        group_id: [] for group_id in public_wind_group_ids(region_id)
    }
    for layer_id in analysis.default_request.selected_layer_ids:
        layer = analysis.layers.get(layer_id)
        if layer is None:
            raise ValueError(
                f"{region_id}/wind default request references unknown layer: "
                f"{layer_id}"
            )
        public_group_id = layer.group_id
        if layer.group_id not in {
            CANONICAL_ROADS_GROUP_ID,
            CANONICAL_POPULATION_GROUP_ID,
            CANONICAL_NATURE_GROUP_ID,
            CANONICAL_CULTURE_GROUP_ID,
            CANONICAL_GRID_GROUP_ID,
        }:
            public_group_id = CANONICAL_TO_TRANSITIONAL_GROUP_ID.get(
                layer.group_id
            )
        if public_group_id is None:
            raise ValueError(
                f"{region_id}/wind default layer {layer_id} belongs to an "
                f"unsupported public group: {layer.group_id}"
            )
        selected.setdefault(public_group_id, []).append(layer_id)
    return selected


def vector_preview_layer_ids(
    region_id: str,
    analysis_id: str = "wind",
    group_id: str | None = None,
) -> tuple[str, ...]:
    """Return manifest layers that can produce a dynamic vector preview."""

    analysis = _validated_area_analysis(region_id, analysis_id)
    applicable_group_ids = set(analysis.area_result.applicable_group_ids)
    requested_group_id = str(group_id) if group_id is not None else None
    if (
        requested_group_id is not None
        and requested_group_id not in applicable_group_ids
    ):
        raise ValueError(
            f"{region_id}/{analysis_id} does not apply group "
            f"{requested_group_id!r}"
        )
    return tuple(
        layer.id
        for layer in analysis.layers.values()
        if layer.group_id in applicable_group_ids
        and (
            requested_group_id is None
            or layer.group_id == requested_group_id
        )
        and layer.operation in CANONICAL_DISTANCE_OPERATIONS
        and layer.source.source_geometry_required
    )


def analysis_area_group_preview(
    region_id: str,
    analysis_id: str,
    canonical_group_id: str,
    layer_ids: Collection[str],
    buffer_m: float,
) -> VectorBufferPreview:
    """Build one exact manifest area-group geometry for map review."""

    requested = tuple(str(layer_id) for layer_id in layer_ids)
    if not requested:
        raise ValueError("An area-group preview requires at least one layer")
    allowed = set(
        analysis_group_layer_ids(
            region_id,
            analysis_id,
            canonical_group_id,
        )
    )
    unknown = set(requested) - allowed
    if unknown:
        raise ValueError(
            f"{region_id}/{analysis_id} has no {canonical_group_id} "
            f"preview layers: {sorted(unknown)}"
        )
    return build_area_group_preview(
        region=str(region_id),
        analysis=str(analysis_id),
        group_id=str(canonical_group_id),
        layers=requested,
        buffer_m=float(buffer_m),
    )


def vector_buffer_preview(
    region_id: str,
    layer_ids: Collection[str],
    buffer_m: float,
) -> VectorBufferPreview:
    """Build one manifest-resolved preview for selected canonical layers."""
    analysis = _validated_wind_analysis(region_id)
    requested = tuple(str(layer_id) for layer_id in layer_ids)
    if not requested:
        raise ValueError("A vector preview requires at least one layer")
    unknown = set(requested) - set(analysis.layers)
    if unknown:
        raise ValueError(
            f"{region_id}/wind has no canonical preview layers: "
            f"{sorted(unknown)}"
        )
    region = load_region(str(region_id))
    native_crs = str(region.get("native_crs") or "")
    requested_layers = [analysis.layers[layer_id] for layer_id in requested]
    if all(layer.operation == "proximity_feasibility" for layer in requested_layers):
        group_ids = {layer.group_id for layer in requested_layers}
        if len(group_ids) != 1:
            raise ValueError(
                "A proximity preview requires one manifest-declared group"
            )
        return analysis_area_group_preview(
            region_id=str(region_id),
            analysis_id="wind",
            canonical_group_id=next(iter(group_ids)),
            layer_ids=requested,
            buffer_m=float(buffer_m),
        )
    return build_vector_buffer_preview(
        requested_layers,
        native_crs=native_crs,
        buffer_m=float(buffer_m),
    )


def canonical_wind_group_layer_ids(
    region_id: str,
    group_id: str,
) -> tuple[str, ...]:
    """Return one canonical group's layers in manifest order."""
    analysis = _validated_wind_analysis(region_id)
    layer_ids = tuple(
        layer.id
        for layer in analysis.layers.values()
        if layer.group_id == str(group_id)
        and layer.operation in CANONICAL_DISTANCE_OPERATIONS
    )
    if not layer_ids:
        raise ValueError(
            f"{region_id}/wind declares no canonical {group_id} layers"
        )
    return layer_ids


def analysis_group_control_contract(
    region_id: str,
    analysis_id: str,
    canonical_group_id: str,
    *,
    public_group_id: str | None = None,
) -> WindGroupControlContract:
    """Build one public distance-group control from its analysis manifest."""

    analysis = _validated_analysis(region_id, analysis_id)
    if analysis.ui is None:
        raise ValueError(f"{region_id}/{analysis_id} has no ui contract")
    group_ui = analysis.ui.groups.get(str(canonical_group_id))
    if group_ui is None:
        raise ValueError(
            f"{region_id}/{analysis_id} has no {canonical_group_id} "
            "ui descriptor"
        )
    workspace_profile = load_workspace_profile(region_id)
    workspace_group = next(
        (
            group
            for group in workspace_profile.standard_groups
            if group.id == str(canonical_group_id)
        ),
        None,
    )
    if workspace_group is None:
        raise ValueError(
            f"{region_id}/{analysis_id} {canonical_group_id} has no "
            "workspace group profile"
        )
    if not isinstance(workspace_group.source_map_default_visible, bool):
        raise ValueError(
            f"{workspace_profile.id} {canonical_group_id} must declare "
            "source_map_default_visible"
        )
    control_layer_ids = _control_group_layer_ids(
        analysis,
        canonical_group_id,
    )
    parameter = _shared_group_buffer_parameter_contract(
        analysis,
        canonical_group_id,
        control_layer_ids,
    )
    if (
        parameter.minimum is None
        or parameter.maximum is None
        or parameter.step is None
    ):
        raise ValueError(
            f"{region_id}/{analysis_id} {canonical_group_id} buffer must "
            "declare "
            "minimum, maximum and step"
        )

    public_id = str(public_group_id or canonical_group_id)
    operations = {
        analysis.layers[layer_id].operation
        for layer_id in control_layer_ids
    }
    if len(operations) != 1:
        raise ValueError(
            f"{region_id}/{analysis_id} {canonical_group_id} layers must "
            "use one operation"
        )
    operation = operations.pop()
    analysis_kind = (
        "hard_exclusion"
        if operation == "hard_exclusion"
        else "proximity_feasibility"
        if operation == "proximity_feasibility"
        else "distance_conflict"
    )
    layer_controls: list[WindLayerControlContract] = []
    for layer_id in control_layer_ids:
        layer = analysis.layers[layer_id]
        if layer.ui is None:
            raise ValueError(
                f"{region_id}/{analysis_id} layer {layer_id} has no ui"
            )
        ready = True
        message = layer.ui.note
        try:
            validate_layer(layer)
        except (FileNotFoundError, KeyError, OSError, ValueError) as exc:
            ready = False
            message = f"{layer.ui.note} Datakällan är inte redo: {exc}"
        layer_controls.append(
            WindLayerControlContract(
                id=layer.id,
                group_id=public_id,
                label=layer.label,
                note=layer.ui.note,
                source_color=_hex_color_to_rgb(layer.ui.source_color),
                point_radius=layer.ui.point_radius,
                quality_flag=layer.ui.quality_flag,
                ready=ready,
                message=message,
            )
        )

    return WindGroupControlContract(
        id=public_id,
        canonical_id=str(canonical_group_id),
        label=group_ui.label,
        analysis_kind=analysis_kind,
        analysis_label=group_ui.analysis_label,
        analysis_min_m=int(parameter.minimum),
        analysis_max_m=int(parameter.maximum),
        analysis_step_m=int(parameter.step),
        analysis_default_m=int(parameter.default),
        blend_default=group_ui.blend_default,
        group_color=_hex_color_to_rgb(group_ui.group_color),
        interpretation=group_ui.interpretation,
        expanded_by_default=group_ui.expanded_by_default,
        source_map_default_visible=(
            workspace_group.source_map_default_visible
        ),
        layers=tuple(layer_controls),
    )


def analysis_group_controls(
    region_id: str,
    analysis_id: str,
) -> tuple[WindGroupControlContract, ...]:
    """Return declared standard-group controls in workspace-profile order."""

    analysis = _validated_analysis(region_id, analysis_id)
    workspace_profile = load_workspace_profile(region_id)
    declared_group_ids = set(analysis.groups)
    controls = tuple(
        analysis_group_control_contract(
            region_id,
            analysis_id,
            group.id,
        )
        for group in workspace_profile.standard_groups
        if group.id in declared_group_ids
    )
    if tuple(control.canonical_id for control in controls) != tuple(
        group.id
        for group in workspace_profile.standard_groups
        if group.id in declared_group_ids
    ):
        raise ValueError(
            f"{region_id}/{analysis_id} controls drifted from workspace order"
        )
    return controls


def analysis_source_geojson(
    region_id: str,
    analysis_id: str,
    canonical_group_id: str,
    layer_id: str,
) -> dict:
    """Read one applicable analysis source through the provider resolver."""

    analysis = _validated_analysis(region_id, analysis_id)
    if layer_id not in _control_group_layer_ids(
        analysis,
        canonical_group_id,
    ):
        raise ValueError(
            f"{region_id}/{analysis_id} has no canonical "
            f"{canonical_group_id} "
            f"source: {layer_id}"
        )
    validated = validate_layer(analysis.layers[layer_id])
    payload = read_layer_geojson(validated.assets)
    if not isinstance(payload, dict):
        raise ValueError(
            f"Canonical {canonical_group_id} source is not a GeoJSON "
            f"object: {layer_id}"
        )
    return payload


def analysis_group_buffer_parameter_contract(
    region_id: str,
    analysis_id: str,
    canonical_group_id: str,
) -> ParameterContract:
    """Return one analysis group's shared manifest buffer contract."""

    analysis = _validated_area_analysis(region_id, analysis_id)
    layer_ids = analysis_group_layer_ids(
        region_id,
        analysis_id,
        canonical_group_id,
    )
    return _shared_group_buffer_parameter_contract(
        analysis,
        canonical_group_id,
        layer_ids,
    )


def wind_group_acceptance_frame(
    region_id: str,
    canonical_group_id: str,
    layer_ids: Collection[str],
    buffer_m: float,
    analysis_cell_ids: Collection[str],
    target_resolution: int,
) -> pd.DataFrame:
    """Adapt one manifest-selected distance group to V2 Final."""
    raw_requested_layers = tuple(str(value).strip() for value in layer_ids)
    if not raw_requested_layers:
        raise ValueError(
            f"A canonical {canonical_group_id} request requires at least one layer"
        )
    if any(not value for value in raw_requested_layers):
        raise ValueError(
            f"A canonical {canonical_group_id} request contains a blank layer id"
        )
    if len(raw_requested_layers) != len(set(raw_requested_layers)):
        raise ValueError(
            f"A canonical {canonical_group_id} request contains duplicate layer ids"
        )
    available_layers = canonical_wind_group_layer_ids(
        region_id,
        canonical_group_id,
    )
    requested_layer_set = set(raw_requested_layers)
    unknown_layers = requested_layer_set - set(available_layers)
    if unknown_layers:
        layer_kind = (
            "road"
            if canonical_group_id == CANONICAL_ROADS_GROUP_ID
            else canonical_group_id
        )
        raise ValueError(
            f"{region_id}/wind has no canonical {layer_kind} layers: "
            f"{sorted(unknown_layers)}"
        )
    requested_layers = tuple(
        layer_id
        for layer_id in available_layers
        if layer_id in requested_layer_set
    )

    requested_ids = tuple(str(value).strip() for value in analysis_cell_ids)
    if not requested_ids:
        raise ValueError(
            f"Canonical {canonical_group_id} requires a non-empty "
            "analysis-cell universe"
        )
    if any(not value for value in requested_ids):
        raise ValueError(
            f"Canonical {canonical_group_id} analysis-cell universe contains "
            "a blank id"
        )
    if len(requested_ids) != len(set(requested_ids)):
        raise ValueError(
            f"Canonical {canonical_group_id} analysis-cell universe contains "
            "duplicate ids"
        )

    result = run_analysis(
        str(region_id),
        "wind",
        list(requested_layers),
        {
            layer_id: {
                "buffer_m": float(buffer_m),
            }
            for layer_id in requested_layers
        },
        analysis_cell_ids=requested_ids,
        target_resolution=target_resolution,
    )
    group = next(
        (
            item
            for item in result.groups
            if item.group_id == canonical_group_id
        ),
        None,
    )
    if group is None:
        raise ValueError(
            f"Canonical result has no {canonical_group_id} group"
        )
    if tuple(group.layer_ids) != requested_layers:
        raise ValueError(
            f"Canonical {canonical_group_id} result does not preserve the "
            "requested layers: "
            f"{group.layer_ids}"
        )
    if group.cell_count != len(requested_ids) or len(group.cells) != len(
        requested_ids
    ):
        raise ValueError(
            f"Canonical {canonical_group_id} result does not cover the requested "
            f"analysis domain ({len(group.cells)}/{len(requested_ids)})"
        )

    frame = pd.DataFrame(
        (
            {
                "hex_id": cell.cell_id,
                "distance_m": cell.min_distance_m,
                "intersects": cell.any_intersection,
                "acceptance": cell.acceptance,
                "coverage_missing": cell.coverage_missing,
            }
            for cell in group.cells
        )
    )
    if frame["hex_id"].duplicated().any():
        raise ValueError(
            f"Canonical {canonical_group_id} result contains duplicate cells"
        )
    return frame.sort_values("hex_id").reset_index(drop=True)
