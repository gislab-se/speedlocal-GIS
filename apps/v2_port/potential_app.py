from __future__ import annotations

from collections import deque
from dataclasses import fields
from datetime import datetime, timezone
from functools import wraps
import hashlib
import html
from io import StringIO
import h3
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping
from uuid import uuid4

import pandas as pd
import folium
import streamlit as st
from streamlit.runtime.scriptrunner import StopException

try:
    import streamlit.components.v1 as components
except Exception:
    components = None


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
APPS_DIR = ROOT / "apps"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(APPS_DIR) not in sys.path:
    sys.path.insert(0, str(APPS_DIR))

from speedlocal.allocation import (  # noqa: E402
    AllocatedCell,
    AllocationCandidate,
    FLOAT_TOLERANCE,
    TechnologyDemand,
    allocate_technology_area,
    rollup_allocated_cells,
)
from speedlocal.catalogs import (  # noqa: E402
    load_analysis as load_delivery_analysis,
    load_region as load_delivery_region_manifest,
    load_scenario_manifest as load_delivery_scenario_manifest,
)
from speedlocal.combined_ranking import (  # noqa: E402
    TechnicalRankingWeights,
    landscape_group_score,
    technical_priority_score,
    wind_core_metrics,
)
from speedlocal.combined_runtime import (  # noqa: E402
    CombinedResultExecutionBundle,
    load_catalog_validated_combined_result_policy,
    run_combined_result_execution,
)
from speedlocal.landscape import (  # noqa: E402
    LANDSCAPE_CAPABILITY_ID,
    LandscapeLegendItem,
    LandscapeViewCell,
    LandscapeViewRequest,
    LandscapeViewResult,
    build_catalog_landscape_view,
    build_landscape_view_request_from_contract,
    load_landscape_contract,
    parse_landscape_view_request,
    parse_landscape_view_result,
)
from speedlocal.gate1_review import (  # noqa: E402
    GATE1_REVIEW_ENV,
    GATE1_REVIEW_VIEW,
    gate1_review_enabled,
    load_gate1_region_reviews,
)
from speedlocal.gate2_review import (  # noqa: E402
    GATE2_REVIEW_ENV,
    gate2_review_enabled,
    load_gate2_region_bounds,
    load_gate2_source_catalogs,
    load_gate2_source_reviews,
)
from speedlocal.source_catalog import load_delivery_source_selection  # noqa: E402
from speedlocal.startup_parameters import load_workspace_start_parameters  # noqa: E402
from speedlocal.region_profile import (  # noqa: E402
    DELIVERY_REGION_IDS,
    load_region_profile,
)
from speedlocal.rooftop import (  # noqa: E402
    ROOFTOP_CAPABILITY_ID,
    RooftopCapabilityRequest,
    RooftopCapabilityResult,
    RooftopSelectionRequest,
    build_rooftop_request_from_selection,
    build_rooftop_selection_from_contract,
    load_catalog_rooftop_contract,
    parse_rooftop_request,
    parse_rooftop_selection,
    run_catalog_rooftop_request,
    validate_rooftop_selection_from_contract,
)
from speedlocal.workspace import (  # noqa: E402
    CapabilityAvailability,
    ReviewAccessContract,
    load_review_access,
    load_workspace_profile,
    resolve_group_availability,
    validate_workspace_analysis_manifest,
)
from speedlocal.workspace_access import (  # noqa: E402
    WorkspaceAccessReadiness,
    resolve_catalog_workspace_access_readiness,
)
from speedlocal.workspace_area import (  # noqa: E402
    WorkspaceAreaExecutionResult,
    WorkspaceNativeAreaExecution,
    derive_catalog_workspace_area_request,
    native_workspace_area_request,
    prepare_catalog_workspace_native_area,
    run_catalog_workspace_area_request,
)
from speedlocal.workspace_app_adapter import (  # noqa: E402
    WorkspaceAppAdapter,
    workspace_app_map_layer_dicts,
    workspace_app_metric_dicts,
    workspace_region_domain_map_layer_dict,
    workspace_app_result_table_dicts,
)
from speedlocal.workspace_buffer import (  # noqa: E402
    WorkspacePreparedBufferPreview,
    build_catalog_workspace_buffer_preview_request,
    parse_workspace_buffer_preview_request,
    prepare_catalog_workspace_buffer_preview,
    reusable_catalog_workspace_buffer_request,
    workspace_buffer_geometry_validation_scope,
)
from speedlocal.product_area_plan import ProductAreaResolutionPlan, validate_product_area_bundle
from speedlocal.requested_display import RequestedDisplayLayer, requested_display_cache
from speedlocal.workspace_execution import (  # noqa: E402
    WorkspaceAnalysisExecutionInput,
    WorkspaceAreaExecution,
    WorkspaceExecutionBinding,
    WorkspaceExecutionBundle,
    WorkspaceExecutionResolutionPlan,
    WorkspaceExecutionState,
    parse_workspace_analysis_execution_input,
    run_catalog_workspace_analysis_binding,
    retarget_catalog_workspace_execution_inputs,
    compose_catalog_workspace_execution_resolution_plan,
    run_catalog_workspace_execution,
    run_catalog_workspace_execution_resolution_plan,
)
from speedlocal.workspace_map_policy import (  # noqa: E402
    BoundWorkspaceSourceBufferMap,
    WorkspaceMapAnalysisVisibility,
    bind_workspace_source_buffer_map,
    normalize_workspace_map_group_visibility,
    select_workspace_source_buffer_layers,
)
from speedlocal.workspace_route import (  # noqa: E402
    WorkspaceRouteDecision,
    resolve_catalog_workspace_route,
)
from speedlocal.workspace_request import (  # noqa: E402
    WorkspaceAnalysisRequest,
    authorize_catalog_workspace_analysis_request,
    build_workspace_analysis_request_from_contract,
    parse_workspace_analysis_request,
    retarget_workspace_analysis_request_from_contract,
    run_workspace_analysis_request,
    validate_workspace_analysis_request_from_contract,
)
from speedlocal.paths import resolve_source_path  # noqa: E402
from speedlocal.runtime_snapshot import (  # noqa: E402
    runtime_readiness_snapshot_token,
)
from speedlocal.result_presentation import (  # noqa: E402
    build_result_presentation_from_combined_summary,
    parse_result_presentation,
    result_technology,
    serialize_result_presentation,
)
from speedlocal.capacity_scenarios import ADAPTER as CAPACITY_ADAPTER, capacity_scale, model_shares

from speedlocal.scenarios import (  # noqa: E402
    SCENARIO_CAPABILITY_ID,
    ScenarioContract,
    ScenarioRequest,
    ScenarioResult,
    build_scenario_request_from_contract,
    load_catalog_scenario_contract,
    parse_scenario_request,
    parse_scenario_result,
    run_catalog_scenario_request,
    validate_scenario_request_from_contract,
    validate_scenario_result_from_contract,
    scenario_contract_signature,
)
from speedlocal.social_acceptance import (  # noqa: E402
    SOCIAL_ACCEPTANCE_CAPABILITY_ID,
    SocialAcceptanceContract,
    SocialAcceptanceRequest,
    SocialAcceptanceResult,
    build_social_acceptance_request_from_contract,
    load_catalog_social_acceptance_contract,
    parse_social_acceptance_request,
    parse_social_acceptance_result,
    run_catalog_social_acceptance_request,
    social_acceptance_calculation_result_signature,
    social_acceptance_signature_operation,
    social_acceptance_data_status_is_available,
    validate_social_acceptance_request_from_contract,
)
from speedlocal.technology_context import (  # noqa: E402
    TechnologyContextResult,
    build_catalog_technology_context_request,
    run_catalog_technology_context_request,
)
from speedlocal.workspace_readiness import (  # noqa: E402
    WorkspaceCapabilityReadiness,
    WorkspaceReviewReadiness,
)
from speedlocal.technology_surface import (  # noqa: E402
    apply_allocation_context_completeness,
    filter_allocation_ready_context as _allocation_ready_context_frame,
    merge_exact_area_with_optional_context,
)
from speedlocal.postgis_domain_inputs import DomainDisplayPayload
from speedlocal.context_runtime import catalog_context_runtime_declared, load_catalog_context_inputs
from speedlocal.rooftop import RooftopUnavailableResult, build_unavailable_rooftop_result
from potential_model.landscape import (
    landscape_frame_from_records, landscape_frame_for_resolution_from_frame,
    technology_context_frame_from_records, TECHNOLOGY_CONTEXT_COLUMNS,
)
from speedlocal.area_result import area_clipping_operation
from speedlocal.sources import postgis_input_operation, read_analysis_domain_input
from potential_model.geometry import geometry_for_hex, load_h3_display_geometries  # noqa: E402
from potential_model.rollup_colours import colour_rollup_layers  # noqa: E402
from potential_model.parent_display import use_h3_parent_boundaries  # noqa: E402
from potential_model.filter_controls import (  # noqa: E402
    FilterGroupControl,
    FilterSourceControl,
    WHOLE_METRE_SLIDER_FORMAT,
    filter_group_control,
)
import potential_model.landscape as landscape_model  # noqa: E402
from potential_model.landing import LandingRegion, render_landing  # noqa: E402
from potential_model.loading_feedback import (  # noqa: E402
    LoadingFeedback,
    active_loading,
    current_loading,
)
from potential_model.i18n import (  # noqa: E402
    LANGUAGE_LABELS,
    normalize_language,
    translate,
    translate_rendered,
)
from potential_model.presentation_snapshot import (  # noqa: E402
    MissingPresentationDependency,
    PresentationSnapshot,
    build_presentation_binding,
    capture_presentation_dependencies,
    create_presentation_snapshot,
    presentation_dependency,
    replay_presentation_dependencies,
)
from potential_model.manifests import (  # noqa: E402
    LEGACY_NUMERICAL_LANDSCAPE_CONTEXT_KEY,
    default_region_id,
    load_linked_manifest,
    load_region,
    list_regions,
    read_manifest,
    resolve_repo_path,
)
from potential_model.region_status import (  # noqa: E402
    available_h3_resolutions as region_available_h3_resolutions,
    load_region_context,
    region_data_status_rows,
)
from potential_model.map_rendering import (  # noqa: E402
    PRIMARY_RESULT_INTERACTION_ROLE,
    build_layered_hex_map_html,
)
from potential_model.workspace_map import (  # noqa: E402
    resolve_workspace_map_view,
)
from potential_model.workspace_controls import (  # noqa: E402
    WorkspaceUiIdentity,
    workspace_state_key,
    workspace_state_prefix,
)
from potential_model.energy_modeling import (  # noqa: E402
    allocate_wind_area_from_core_hexes,
    h3_hex_area_km2,
)
from potential_model.potential import (  # noqa: E402
    potential_feature_collection,
    potential_summary,
    rollup_frame_for_entry,
    rollup_potential_frame,
    solar_capacity_frame,
    solar_capacity_summary,
)
from potential_model.speedlocal_bridge import (  # noqa: E402
    CANONICAL_CULTURE_GROUP_ID,
    CANONICAL_GRID_GROUP_ID,
    CANONICAL_NATURE_GROUP_ID,
    CANONICAL_POPULATION_GROUP_ID,
    CANONICAL_ROADS_GROUP_ID,
    WORKSPACE_AREA_FRAME_SCHEMA_LEGACY_WIND,
    WORKSPACE_AREA_FRAME_SCHEMA_WORKSPACE,
    WindGroupControlContract,
    WindLayerControlContract,
    adapt_workspace_area_execution_result_frame,
    analysis_area_group_preview,
    analysis_group_controls as _load_analysis_group_controls,
    analysis_group_control_contract,
    analysis_source_geojson,
    canonical_wind_group_layer_ids as _load_canonical_wind_group_layer_ids,
    canonical_wind_group_is_declared as _load_canonical_wind_group_is_declared,
    default_wind_layer_selection,
    public_wind_group_ids as _load_public_wind_group_ids,
    shared_technology_context_manifest_overlay,
    shared_area_display_geometry_path,
    vector_buffer_preview,
    vector_preview_layer_ids,
    standard_result_surface_cell_areas_km2,
    technology_support_domain_cell_areas_km2,
    technology_support_domain_resolution,
    technology_support_observation_frame,
    wind_analysis_domain_cell_areas_km2,
    wind_analysis_domain_resolution,
    wind_group_acceptance_frame,
)
from potential_model.wind_acceptance import (  # noqa: E402
    GROUP_LABELS,
    GROUP_PARAM_MAP,
    SOURCE_RESOLUTION as WIND_SOURCE_RESOLUTION,
    WIND_GROUP_LAYER_DEFAULTS,
    normalize_group_layer_map as normalize_legacy_group_layer_map,
    runtime_combined_hex_frame,
    wind_acceptance_potential_frame,
    wind_acceptance_rollup_frame,
    wind_candidate_summary,
    wind_vector_feature_collection,
)
from acceptance_model.layers import (  # noqa: E402
    distance_table_for_layer,
    layer_status_table as acceptance_layer_status_table,
    load_registry as load_acceptance_registry,
    ordered_groups,
    ordered_layers,
    source_geojson_for_layer,
)
from acceptance_model.runtime_geometry import run_geometry_runtime  # noqa: E402
from acceptance_model.i18n import (  # noqa: E402
    group_analysis_label,
    group_interpretation,
    group_label,
    layer_label,
    layer_note,
    source_warning,
    ui_text,
)


landscape_frame_for_resolution = landscape_model.landscape_frame_for_resolution
landscape_source_resolution = landscape_model.landscape_source_resolution
technology_context_frame_for_resolution = (
    landscape_model.technology_context_frame_for_resolution
)


PAGE_TITLE = "Sol- och vindpotential"
APP_RELEASE_STAGE = "BETA"
APP_LANGUAGE_KEY = "potential_app_language"
APP_LANGUAGES = LANGUAGE_LABELS
MAP_VIEW_RESET_TOKEN_KEY = "potential_map_view_reset_token"
MAP_STATE_VERSION = "establishment-start-v6"
LEFT_PANEL_OPEN_KEY = "potential_left_panel_open"
SIDEBAR_ENTRY_KEY = "potential_sidebar_entry_v1"
RIGHT_PANEL_OPEN_KEY = "potential_right_panel_open"
RIGHT_PANEL_WIDTH_KEY = "potential_right_panel_width_pct"
RIGHT_PANEL_WIDTH_DEFAULT_VERSION_KEY = "potential_right_panel_width_default_version"
RIGHT_PANEL_WIDTH_DEFAULT_VERSION = "map_balance_v2"
RIGHT_PANEL_WIDTH_DEFAULT = 42.0
RIGHT_PANEL_WIDTH_LEGACY_DEFAULTS = (34.0, 60.0, 66.0)
PERFORMANCE_HISTORY_KEY = "potential_performance_history_v1"
UI_ONLY_RERUN_KEY = "potential_ui_only_rerun"
UI_ONLY_RERUN_REASON_KEY = "potential_ui_only_rerun_reason"
PRESENTATION_ONLY_RERUN_REASONS = frozenset({
    "language", "area_unit", "panelbredd", "opacitet", "hexopacitet",
})
WORKSPACE_RENDER_CACHE_KEY = "potential_workspace_render_cache_v2"
WORKSPACE_PRESENTATION_SNAPSHOT_KEY = "potential_presentation_snapshot_v1"
WORKSPACE_PRESENTATION_BUILD_KEY = "potential_presentation_build_v1"
WORKSPACE_CALCULATION_VERSION = "result_presentation_contract_v1"
TUTORIAL_FORCE_OPEN_KEY = "potential_tutorial_force_open"
TUTORIAL_FORCE_OPEN_TOKEN_KEY = "potential_tutorial_force_open_token"
TUTORIAL_STORAGE_KEY = "potential_tutorial_manifest_program_dismissed"
# Kept only while untouched compatibility helpers still resolve the external
# acceptance registry. Migrated capabilities never select it by region id.
REGION_SELECT_KEY = "potential_selected_region_id"
REGION_LANDING_VIEW = "landing"
DEFAULT_REGION_ID = default_region_id()
LOCAL_REVIEW_REGIONS_ENV = "SPEEDLOCAL_LOCAL_REVIEW_REGIONS"
LOCAL_REVIEW_MODE = "review"
REGION_SESSION_SCOPE_KEY = "potential_region_session_scope"
WORKSPACE_FILTER_APPLIED_STATE_KEY = "workspace_filter_applied_state_v1"
REGION_SESSION_PRESERVE_KEYS = {
    APP_LANGUAGE_KEY,
    REGION_SELECT_KEY,
    LEFT_PANEL_OPEN_KEY,
    RIGHT_PANEL_OPEN_KEY,
    RIGHT_PANEL_WIDTH_KEY,
    RIGHT_PANEL_WIDTH_DEFAULT_VERSION_KEY,
    PERFORMANCE_HISTORY_KEY,
    TUTORIAL_FORCE_OPEN_KEY,
    TUTORIAL_FORCE_OPEN_TOKEN_KEY,
}
WIND_LAYER_SELECTION_KEY = "wind_builder_selected_layers"
START_DEFAULT_VERSION_KEY = "potential_start_default_version"
# Reset pre-migration browser sessions once so removed population and culture
# adapter state cannot reach their canonical manifest boundaries.
START_DEFAULT_VERSION = "manifest_grid_group_v1"
WIND_EMPTY_SELECTION_ACTIVE_KEY = "wind_empty_selection_active"
WIND_CONTROL_LANGUAGE = "sv"
WIND_RUNTIME_BASE_RESOLUTION = 10
WIND_LANDSCAPE_POTENTIAL_LABEL = "Landskapspotential Vind"
WIND_POTENTIAL_HEX_LABEL = "Landskapspotential Vind hexagon"
WIND_ESTABLISHMENT_LAYER_LABEL = "Potentiell etableringsyta Vind"
COMBINED_ESTABLISHMENT_LAYER_LABEL = "Potentiell etableringsyta"
SCENARIO_ALLOCATION_LAYER_LABEL = "Scenarioyta inom potentialen"
SOLAR_LANDSCAPE_POTENTIAL_LABEL = "Landskapspotential Sol"
SOLAR_SMALL_SCALE_LABEL = "Småskalig anläggning på tak"
SOLAR_LARGE_SCALE_LABEL = "Storskalig anläggning på land"
SOLAR_POTENTIAL_POLYGON_LABEL = "Landskapspotential Sol polygon"
SOLAR_POTENTIAL_HEX_LABEL = "Landskapspotential Sol hexagon"
SOLAR_ESTABLISHMENT_LAYER_LABEL = "Potentiell etableringsyta Sol"
OUTSIDE_LP_NEED_LAYER_LABEL = "Ytbehov utanför landskapets potential"
OUTSIDE_LP_NEED_DISPLAY_MIN_KM2 = 0.005
SOLAR_POPULATION_SOURCE_LABEL = "Sol källa: Befolkningsunderlag"
SOLAR_POPULATION_BUFFER_LABEL = "Solbuffert: Befolkningsunderlag"
PROTECTED_NATURE_LABEL = "Skyddad natur"
SOLAR_PROTECTED_SOURCE_LABEL = f"Sol källa: {PROTECTED_NATURE_LABEL}"
SOLAR_PROTECTED_BUFFER_LABEL = f"Solbuffert: {PROTECTED_NATURE_LABEL}"
WIND_POPULATION_GROUP_ID = CANONICAL_POPULATION_GROUP_ID
WIND_POPULATION_GROUP_LABEL = "Befolkning och bebyggelse"
SOLAR_POPULATION_GROUP_ID = "settlement"
WIND_POPULATION_SOURCE_LAYER_ID = "population_points"
WIND_POPULATION_PARAM_KEY = "settlement_distance_m"
# `settlement_distance_m` remains an internal saved-state/model key until a
# versioned state migration can rename it. It is not a public wind group id;
# the public and manifest group id is canonical `population`.
WIND_ROADS_GROUP_ID = CANONICAL_ROADS_GROUP_ID
WIND_ROADS_PARAM_KEY = "road_distance_m"
WIND_NATURE_GROUP_ID = CANONICAL_NATURE_GROUP_ID
WIND_NATURE_PARAM_KEY = "protected_buffer_m"
WIND_CULTURE_GROUP_ID = CANONICAL_CULTURE_GROUP_ID
WIND_CULTURE_GROUP_LABEL = "kulturmiljöer"
WIND_GRID_GROUP_ID = CANONICAL_GRID_GROUP_ID
WIND_GRID_PARAM_KEY = "grid_max_distance_m"
WIND_REINDEER_GROUP_ID = "reindeer"
WIND_REINDEER_GROUP_LABEL = "rennäring / reindrift"
SOLAR_PROTECTED_GROUP_ID = "protected"
SOLAR_PROTECTED_LAYER_IDS = tuple(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_PROTECTED_GROUP_ID, []))
SOLAR_ROAD_GROUP_ID = "transport"
SOLAR_ELECTRICAL_GROUP_ID = "electrical"
SOLAR_CULTURE_GROUP_ID = "culture"
SOLAR_REINDEER_GROUP_ID = "reindeer"
SOLAR_COASTAL_GROUP_ID = "coastal"
WIND_ESTABLISHMENT_INTERSECTION_BLOCK_GROUP_IDS = {SOLAR_COASTAL_GROUP_ID}
SOLAR_LAND_USE_GROUP_ID = "land_use"
SOLAR_FOREST_LAYER_ID = "forest_land_cover"
SOLAR_AREA_CANONICAL_GROUP_IDS = {
    SOLAR_PROTECTED_GROUP_ID: CANONICAL_NATURE_GROUP_ID,
    SOLAR_ROAD_GROUP_ID: CANONICAL_ROADS_GROUP_ID,
    SOLAR_ELECTRICAL_GROUP_ID: CANONICAL_GRID_GROUP_ID,
    SOLAR_CULTURE_GROUP_ID: CANONICAL_CULTURE_GROUP_ID,
}
SOLAR_FILTER_GROUP_SPECS: dict[str, dict[str, Any]] = {
    SOLAR_PROTECTED_GROUP_ID: {
        "label": PROTECTED_NATURE_LABEL,
        "source_label": SOLAR_PROTECTED_SOURCE_LABEL,
        "buffer_label": SOLAR_PROTECTED_BUFFER_LABEL,
        "layer_ids": SOLAR_PROTECTED_LAYER_IDS,
        "active_key": "large_protected_active",
        "layer_ids_key": "large_protected_layer_ids",
        "buffer_key": "protected_buffer_m",
        "draft_active_key": "solar_draft_protected_active",
        "draft_buffer_key": "solar_draft_protected_buffer_m",
        "buffer_default_m": 0.0,
        "buffer_min_m": 0.0,
        "buffer_max_m": 2000.0,
        "buffer_step_m": 50.0,
        "source_color": "#16a34a",
        "buffer_color": "#16a34a",
        "caption": f"{PROTECTED_NATURE_LABEL} används som avdrag i storskalig solpotential.",
    },
    SOLAR_LAND_USE_GROUP_ID: {
        "label": "Markanvändning: skog",
        "source_label": "Sol källa: skog",
        "buffer_label": "Solavdrag: skog",
        "layer_ids": (SOLAR_FOREST_LAYER_ID,),
        "default_layer_ids": (SOLAR_FOREST_LAYER_ID,),
        "layer_ids_key": "large_land_use_layer_ids",
        "active_key": "large_land_use_active",
        "buffer_key": "forest_buffer_m",
        "draft_active_key": "solar_draft_land_use_active",
        "draft_buffer_key": "solar_draft_forest_buffer_m",
        "buffer_default_m": 0.0,
        "buffer_min_m": 0.0,
        "buffer_max_m": 1000.0,
        "buffer_step_m": 50.0,
        "source_color": "#166534",
        "buffer_color": "#14532d",
        "active_help": (
            "Tar bort markdekke/arealdekke skog från storskalig solpotential med samma polygon-, buffert- och H3-aggregeringslogik som skyddad natur och kultur."
        ),
        "caption": "Skogsfiltret ligger separat från skyddad natur och bygger på N500 markdekke där `objtype = Skog`.",
    },
    SOLAR_ROAD_GROUP_ID: {
        "label": "Vägar",
        "source_label": "Sol källa: Vägar",
        "buffer_label": "Solbuffert: Vägar",
        # Standard solar layer ids resolve from the solar analysis manifest.
        "layer_ids": (),
        "active_key": "large_road_active",
        "layer_ids_key": "large_road_layer_ids",
        "buffer_key": "road_buffer_m",
        "draft_active_key": "solar_draft_road_active",
        "draft_buffer_key": "solar_draft_road_buffer_m",
        # Canonical controls use the solar analysis manifest. These mirrored
        # values keep the disabled/missing-data presentation consistent.
        "buffer_default_m": 300.0,
        "buffer_min_m": 100.0,
        "buffer_max_m": 2000.0,
        "buffer_step_m": 25.0,
        "source_color": "#b45309",
        "buffer_color": "#f97316",
        "caption": "Vägfiltret prövar respektavstånd till större vägar och allmänna vägstråk.",
    },
    SOLAR_ELECTRICAL_GROUP_ID: {
        "label": "Elinfrastruktur / nätanslutning",
        "source_label": "Sol källa: Elinfrastruktur",
        "buffer_label": "Sol nära nät: Elinfrastruktur",
        "layer_ids": tuple(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_ELECTRICAL_GROUP_ID, [])),
        "active_key": "large_electrical_active",
        "layer_ids_key": "large_electrical_layer_ids",
        "buffer_key": "solar_grid_max_distance_m",
        "draft_active_key": "solar_draft_electrical_active",
        "draft_buffer_key": "solar_draft_grid_max_distance_m",
        "buffer_default_m": 2000.0,
        "buffer_min_m": 500.0,
        "buffer_max_m": 15000.0,
        "buffer_step_m": 250.0,
        "source_color": "#0f766e",
        "buffer_color": "#14b8a6",
        "effect": "feasibility",
        "slider_label": "Max avstånd till elinfrastruktur",
        "slider_help": "Yta räknas som storskalig solpotential bara inom valt avstånd till valda nätobjekt.",
        "active_help": f"Valda nätlager används som positiv närhetsregel i {SOLAR_LARGE_SCALE_LABEL}.",
        "buffer_legend_label": "Inom maxavstånd till elinfrastruktur",
        "caption": "Nära nät används som en positiv mask: yta räknas som solpotential bara inom valt avstånd till elinfrastruktur.",
    },
    SOLAR_CULTURE_GROUP_ID: {
        "label": "Kulturmiljö",
        "source_label": "Sol källa: Kulturmiljö",
        "buffer_label": "Solbuffert: Kulturmiljö",
        "layer_ids": tuple(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_CULTURE_GROUP_ID, [])),
        "active_key": "large_culture_active",
        "layer_ids_key": "large_culture_layer_ids",
        "buffer_key": "culture_buffer_m",
        "draft_active_key": "solar_draft_culture_active",
        "draft_buffer_key": "solar_draft_culture_buffer_m",
        "buffer_default_m": 0.0,
        "buffer_min_m": 0.0,
        "buffer_max_m": 1500.0,
        "buffer_step_m": 50.0,
        "source_color": "#9333ea",
        "buffer_color": "#a855f7",
        "caption": "Kulturmiljöfiltret tar bort ytor som träffar valda kulturmiljölager och eventuell buffert.",
    },
    SOLAR_REINDEER_GROUP_ID: {
        "label": "Rennäring / reindrift",
        "source_label": "Sol källa: Rennäring",
        "buffer_label": "Solbuffert: Rennäring",
        "layer_ids": tuple(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_REINDEER_GROUP_ID, [])),
        "active_key": "large_reindeer_active",
        "layer_ids_key": "large_reindeer_layer_ids",
        "buffer_key": "reindeer_buffer_m",
        "draft_active_key": "solar_draft_reindeer_active",
        "draft_buffer_key": "solar_draft_reindeer_buffer_m",
        "buffer_default_m": 0.0,
        "buffer_min_m": 0.0,
        "buffer_max_m": 5000.0,
        "buffer_step_m": 100.0,
        "source_color": "#be4952",
        "buffer_color": "#dc645d",
        "caption": "Rennäringsfiltret tar bort ytor som träffar valda reindriftslager och eventuell buffert.",
    },
    SOLAR_COASTAL_GROUP_ID: {
        "label": "Strandskydd / kust",
        "source_label": "Sol källa: Strandskydd / kust",
        "buffer_label": "Solbuffert: Strandskydd / kust",
        "layer_ids": tuple(WIND_GROUP_LAYER_DEFAULTS.get(SOLAR_COASTAL_GROUP_ID, [])),
        "default_layer_ids": ("strand_protection",),
        "active_key": "large_coastal_active",
        "layer_ids_key": "large_coastal_layer_ids",
        "buffer_key": "coastal_buffer_m",
        "draft_active_key": "solar_draft_coastal_active",
        "draft_buffer_key": "solar_draft_coastal_buffer_m",
        "buffer_default_m": 0.0,
        "buffer_min_m": 0.0,
        "buffer_max_m": 1000.0,
        "buffer_step_m": 50.0,
        "source_color": "#0e7490",
        "buffer_color": "#06b6d4",
        "caption": "Strandskydd och kustzon kan användas som ett försiktigt kustnära avdrag.",
    },
}
SOLAR_FILTER_GROUP_IDS = tuple(SOLAR_FILTER_GROUP_SPECS)
SOLAR_VISUAL_SOURCE_GROUPS_KEY = "visible_source_groups"
SOLAR_VISUAL_BUFFER_GROUPS_KEY = "visible_buffer_groups"
SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID = "small_population"
SOLAR_LARGE_POPULATION_VISUAL_GROUP_ID = "large_population"
SOLAR_STANDARD_VISUAL_CANONICAL_GROUP_IDS = {
    SOLAR_LARGE_POPULATION_VISUAL_GROUP_ID: CANONICAL_POPULATION_GROUP_ID,
    **SOLAR_AREA_CANONICAL_GROUP_IDS,
}
SOLAR_LARGE_POPULATION_LAYER_IDS_KEY = "large_population_layer_ids"
DEFAULT_SOLAR_PRESENTATION_PROJECTION = {
    "small_population_active": False,
    "large_unfiltered_land_active": False,
    "large_scale_active": True,
    SOLAR_LARGE_POPULATION_LAYER_IDS_KEY: [],
    "large_population_active": False,
    "large_protected_layer_ids": [],
    "large_protected_active": False,
    "large_land_use_layer_ids": [],
    "large_land_use_active": False,
    "large_road_layer_ids": [],
    "large_road_active": False,
    "large_electrical_layer_ids": [],
    "large_electrical_active": False,
    "large_culture_layer_ids": [],
    "large_culture_active": False,
    "large_reindeer_layer_ids": [],
    "large_reindeer_active": False,
    "large_coastal_layer_ids": [],
    "large_coastal_active": False,
    "population_buffer_m": 100.0,
    "protected_buffer_m": 0.0,
    "forest_buffer_m": 0.0,
    "road_buffer_m": 300.0,
    "solar_grid_max_distance_m": 2000.0,
    "culture_buffer_m": 0.0,
    "reindeer_buffer_m": 100.0,
    "coastal_buffer_m": 0.0,
    SOLAR_VISUAL_SOURCE_GROUPS_KEY: [],
    SOLAR_VISUAL_BUFFER_GROUPS_KEY: [],
}
ENERGY_PROPOSAL_LAYER_LABEL = WIND_ESTABLISHMENT_LAYER_LABEL
WIND_AUTO_RESOLUTION_MIN_ZOOM: dict[int, int] = {10: 11, 9: 9, 8: 7, 7: 5, 6: 0}
EML_PROVIDER_URL = "https://energymodellinglab.com/"
IVL_PROVIDER_URL = "https://www.ivl.se/"
SOCIAL_ACCEPTANCE_IMPACT_TINT_COLOR = "#991b1b"




def _language() -> str:
    return normalize_language(st.session_state.get(APP_LANGUAGE_KEY, "sv"))


def _t(text: str, **kwargs: Any) -> str:
    if kwargs:
        return translate(str(text), _language(), **kwargs)
    return translate_rendered(str(text), _language())


def _display_dataframe(frame: Any) -> Any:
    """Translate a small display projection without mutating result data."""
    if not isinstance(frame, pd.DataFrame):
        return frame
    display = frame.copy(deep=False)
    authored_value_columns = {
        "teknik", "Teknik", "klass", "Status", "status", "mått", "steg",
        "detalj", "notering", "manifest", "del", "beskrivning", "kategori", "motsvarar", "Resultat", "Mått", "default",
    }
    for column in frame.columns:
        if column in authored_value_columns and frame[column].dtype == object:
            display[column] = frame[column].map(
                lambda value: _t("Av" if column == "default" and value == "av" else "På" if column == "default" and value == "på" else value) if isinstance(value, str) else value,
            )
    display.columns = [_t(column) if isinstance(column, str) else column for column in frame.columns]
    return display


def _wind_control_language() -> str:
    return _language()


def _language_formatter() -> Any:
    """Capture the displayed locale for widget serialization outside rendering."""
    language = _language()
    return lambda text, **parameters: translate(str(text), language, **parameters)


def _render_localized_choice(
    label: str, *, options: tuple[str, ...], key: str,
    format_func: Any, persist_state: str = "session",
) -> str:
    """Use numeric wire values so translated labels cannot reset form drafts.

    Streamlit 1.60 serializes selectbox/radio/pill choices as displayed strings.
    A small ordered scale retains native unsent form state through localization;
    canonical scenario IDs remain the application and analysis boundary.
    """
    if not options or len(set(options)) != len(options):
        raise ValueError("Presentation choices require unique canonical IDs")
    canonical = str(st.session_state.get(key, options[0]))
    if canonical not in options:
        raise ValueError("Presentation choice is not declared in the current contract")
    position_key, projection_key = f"{key}:position", f"{key}:projection"
    if position_key not in st.session_state or st.session_state.get(projection_key) != canonical:
        st.session_state[position_key] = options.index(canonical) + 1
    if len(options) == 1:
        selected = canonical
        st.caption(f"{label}: {format_func(selected)}")
    else:
        legend = " · ".join(f"{index + 1}: {format_func(value)}" for index, value in enumerate(options))
        position = st.slider(label, min_value=1, max_value=len(options), step=1,
                             format="%d", key=position_key, help=legend,
                             persist_state=persist_state)
        selected = options[int(position) - 1]
        st.caption(legend)
    st.session_state[key] = selected
    st.session_state[projection_key] = selected
    return selected


def _model_level_source(value: Any) -> str:
    """Human labels for prototype levels; provider/scenario names stay verbatim."""
    source = str(value)
    return {"low": "Låg", "mid": "Mellan", "medium": "Mellan", "high": "Hög"}.get(source, source)


def _presentation_input(name: str) -> Any:
    """Replay only this session's verified control inputs during language rendering."""
    def decorate(loader: Any) -> Any:
        @wraps(loader)
        def resolve(*args: Any, **kwargs: Any) -> Any:
            return presentation_dependency(
                name, (args, kwargs), lambda: loader(*args, **kwargs),
            )
        return resolve
    return decorate


@_presentation_input("analysis_group_controls")
def analysis_group_controls(region_id: str, analysis_id: str) -> Any:
    return _load_analysis_group_controls(region_id, analysis_id)


@_presentation_input("public_wind_group_ids")
def public_wind_group_ids(region_id: str) -> Any:
    return _load_public_wind_group_ids(region_id)


@_presentation_input("canonical_wind_group_layer_ids")
def canonical_wind_group_layer_ids(region_id: str, group_id: str) -> Any:
    return _load_canonical_wind_group_layer_ids(region_id, group_id)


@_presentation_input("canonical_wind_group_is_declared")
def canonical_wind_group_is_declared(region_id: str, group_id: str) -> bool:
    return _load_canonical_wind_group_is_declared(region_id, group_id)


def _set_app_language(code: str) -> None:
    st.session_state[APP_LANGUAGE_KEY] = normalize_language(code)
    _request_ui_only_rerun("language")


def _render_language_switcher(panel: Any | None = None) -> None:
    target = panel or st.sidebar
    current = _language()
    target.caption(_t("Språk"))
    for idx, (code, label) in enumerate(APP_LANGUAGES.items()):
        if idx % 2 == 0:
            cols = target.columns(2)
        cols[idx % 2].button(
            label,
            key=f"app_language_{code}",
            type="primary" if code == current else "secondary",
            disabled=code == current,
            help=label,
            width="stretch",
            on_click=_set_app_language,
            args=(code,),
        )


def _render_workspace_intro(region: dict[str, Any]) -> None:
    """Opt-in presentation metadata; guide navigation never submits app state."""
    guide_kind = region.get("workspace_guide")
    if guide_kind not in {"capacity_intro_v1", "energy_film_v1"}:
        return
    if guide_kind == "energy_film_v1" and _language() != "sv":
        return
    from potential_model.workspace_guide import render_workspace_guide

    if guide_kind == "capacity_intro_v1":
        render_workspace_guide(str(region["region_id"]), language=_language())
        return
    from potential_model.workspace_guide_content import load_instruction_steps

    content_path = (REPO_ROOT / str(region.get("workspace_guide_content", ""))).resolve()
    if REPO_ROOT not in content_path.parents or content_path.suffix != ".json":
        raise ValueError("Guide content must be a repository-owned JSON file")
    steps = load_instruction_steps(content_path, region_id=str(region["region_id"]))
    render_workspace_guide(
        str(region["region_id"]), language="sv", steps=steps,
        launch_label="Starta guide",
    )


def _tutorial_available(region: dict[str, Any]) -> bool:
    _ = region
    # Priority one has no manifest-declared tutorial capability yet. Keep the
    # shared tutorial fail-closed for every region until that contract exists;
    # a region id must never select tutorial layout or behavior.
    return False


def _render_tutorial_launcher(region: dict[str, Any], panel: Any | None = None) -> bool:
    if not _tutorial_available(region):
        return False

    target = panel or st.sidebar
    target.divider()
    clicked = target.button(
        _t("Visa guide"),
        key="potential_tutorial_open_button",
        help=_t("Öppna en kort genomgång av arbetsytan."),
        width="stretch",
    )
    if clicked:
        st.session_state[TUTORIAL_FORCE_OPEN_KEY] = True
        st.session_state[TUTORIAL_FORCE_OPEN_TOKEN_KEY] = int(st.session_state.get(TUTORIAL_FORCE_OPEN_TOKEN_KEY, 0) or 0) + 1
    return bool(st.session_state.pop(TUTORIAL_FORCE_OPEN_KEY, False))


def _tutorial_text(key: str, **kwargs: Any) -> str:
    texts = {'prototype_title': 'Hitta potential för ny vind och sol',
     'prototype_body': 'Det här är en prototyp som hjälper dig att utforska var ny vind- och solenergi '
                       'kan passa. Du kan pröva olika energibehov och se hur landskap, avstånd och '
                       'social acceptans påverkar möjliga etableringar, så att viktiga vägval blir '
                       'lättare att förstå.',
     'geography_title': 'Börja med geografin',
     'geography_body': 'Startläget visar analysens resultat: den potentiella etableringsytan för vind '
                       'och sol. Alla GIS-lager som används i analysen visas inte i kartan från start, '
                       'men de kan öppnas under avancerade inställningar när du vill se vilka '
                       'antaganden som påverkar ytan.',
     'energy_title': 'Koppla yta till energi',
     'energy_body': 'Energimixen i huvudytan låter dig pröva balansen mellan vind och sol. '
                    'Energimodelleringen översätter valt scenario till ett ytanspråk.',
     'scenario_title': 'Energiscenario och markintensitet',
     'scenario_body': 'Energiscenario styr hur mycket energi som ska testas i modellen. Markintensitet '
                      'styr hur mycket mark som behövs per TWh och kan väljas låg, mellan eller hög '
                      'oberoende av energiscenariot. Därför kan du till exempel testa hög energinivå '
                      'med mellan markintensitet.',
     'acceptance_title': 'Lägg till social acceptans',
     'acceptance_body': 'Social acceptans hjälper dig förstå var potentialen kan vara mer eller mindre '
                        'realistisk utifrån landskapets användning, värden och möjliga konflikter. '
                        'Syntetiskt eller provisoriskt underlag ska alltid framgå av den aktiva '
                        'regionens manifest och datastatus.',
     'acceptance_suggestion': 'Dra i reglaget Acceptanspåverkan och följ hur energilandskapet '
                              'förändras i kartan och i tabellen till höger.',
     'establishment_body': 'Kartan visar den sammanvägda etableringspotentialen: grön betyder både '
                           'vind och sol, gul bara sol, blå bara vind och röd ej lämpligt. Det är '
                           'potential utifrån de geografiska antaganden och filter som är aktiva just '
                           'nu.',
     'allocation_body': 'Scenarioyta inom potentialen visar var modellens vind- och solyta placeras. Blått är vind och gulorange är sol. Mörkgrön betyder att båda teknikerna har yta i samma visningshex, inte att exakt fysisk överlappning har beräknats.',
     'outside_body': 'Ytbehov utanför landskapets potential visar schematisk vind- eller solyta som '
                     'behövs när scenariot inte ryms i den beräknade potentialen. Det gör skillnaden '
                     'mellan landskapets möjliga yta och scenariots efterfrågan synlig.',
     'green_title': 'Startläget är försiktigt',
     'green_body': 'Kartan startar med ett restriktivt potentialläge så att antaganden och bortval '
                   'syns direkt. Grönt betyder möjligt enligt nuvarande filter, inte ett färdigt '
                   'rekommenderat område.',
     'wind_solar_title': 'Vind och sol styrs under Geografier',
     'wind_solar_body': 'Under Geografier finns Landskapspotential Vind och Landskapspotential Sol. '
                        'Där kan du ändra de förvalda filtren, buffertarna och nätantagandena. '
                        'Analysen använder valen även när GIS-lagren är dolda i kartan.',
     'wind_apply_title': 'Ändra vindantaganden och använd dem',
     'wind_apply_body': 'Öppna vindpotentialen om du vill ändra startlägets filter, till exempel '
                        'Befolkning och bebyggelse eller vägar. Klicka sedan Använd ändringar för att '
                        'räkna om kartan och resultatet med de valda antagandena.',
     'action_open_geography_todo': 'Öppna Geografier och Landskap för att se vilka antaganden som '
                                   'formar kartan.',
     'action_open_geography_done': 'Bra, nu är landskapsvalen synliga. Fortsätt med '
                                   'energimodelleringen eller testa egna filter.',
     'action_open_wind_todo': 'Öppna vind- och solpotentialen för att se vilka antaganden du kan '
                              'ändra.',
     'action_open_wind_done': 'Bra, nu är potentialkontrollerna synliga. Testa ett filter eller '
                              'fortsätt till omräkningen.',
     'action_apply_wind_todo': 'Klicka på Använd ändringar när du vill räkna om kartan och resultatet '
                               'med filtervalen.',
     'action_apply_wind_done': 'Bra, appen har fått en apply-signal. Kontrollera kartan och '
                               'resultatpanelen innan du går vidare.',
     'table_title': 'Läs resultatet i tabellen',
     'table_body': 'Tabellen visar om energimixen ryms inom den beräknade potentialen. Totalraden är '
                   'en tekniksumma: samma fysiska hex kan räknas för både vind och sol när ytan kan '
                   'samnyttjas.',
     'right_geographies_title': 'Geografier visar antagandena',
     'right_geographies_body': 'Här sammanfattas vilka GIS-lager och filter som formar kartan, till '
                               'exempel befolkning, vägar, naturvärden och kulturmiljöer.',
     'landscape_distribution_title': 'Potential per landskapstyp',
     'landscape_distribution_body': 'De två expandrarna visar hur vind- och solpotentialen fördelas '
                                    'mellan landskapstyper. Det hjälper dig se vilken typ av landskap '
                                    'potentialen hamnar i.',
     'reopen_title': 'Du kan alltid öppna guiden igen',
     'reopen_body': 'Starta om den korta guiden med Visa guide. Kryssa i Öppna inte automatiskt igen '
                    'om du vill att appen ska hoppa över introduktionen nästa gång.'}
    return _t(texts.get(str(key), str(key)), **kwargs)


def _tutorial_steps(region: dict[str, Any]) -> list[dict[str, Any]]:
    region_label = str(region.get("display_name", _t("Region")) or _t("Region"))
    geography_label = _t("Geografier")
    landscape_label = _t("Landskap")
    wind_label = _t(WIND_LANDSCAPE_POTENTIAL_LABEL)
    solar_label = _t(SOLAR_LANDSCAPE_POTENTIAL_LABEL)
    guide_label = _t("Visa guide")
    wind_apply_label = ui_text("apply_changes", _wind_control_language())
    return [
        {
            "selector": ".workspace-header",
            "title": _tutorial_text("prototype_title"),
            "body": _tutorial_text("prototype_body", region_label=region_label),
        },
        {
            "selector": "section[data-testid=\"stSidebar\"]",
            "title": _tutorial_text("geography_title"),
            "body": _tutorial_text("geography_body"),
            "openTexts": [geography_label, landscape_label],
            "showActionStatus": False,
            "action": {
                "kind": "detailsOpen",
                "texts": [geography_label, landscape_label],
                "todo": _tutorial_text("action_open_geography_todo"),
                "done": _tutorial_text("action_open_geography_done"),
            },
        },
        {
            "anchor": "energy-mix",
            "title": _tutorial_text("energy_title"),
            "body": _tutorial_text("energy_body"),
        },
        {
            "selector": "section[data-testid=\"stSidebar\"]",
            "title": _tutorial_text("scenario_title"),
            "body": _tutorial_text("scenario_body"),
            "openTexts": [_t("Energimodellering")],
        },
        {
            "selector": "section[data-testid=\"stSidebar\"]",
            "title": _tutorial_text("acceptance_title"),
            "body": _tutorial_text("acceptance_body"),
            "suggestion": _tutorial_text("acceptance_suggestion"),
            "openTexts": [_t("Social acceptans")],
        },
        {
            "anchor": "map",
            "target": "iframeLegendSection",
            "legendSectionTitle": COMBINED_ESTABLISHMENT_LAYER_LABEL,
            "fallbackTarget": "iframeSelector",
            "iframeSelectors": [".map-legend"],
            "scrollWindowToTarget": True,
            "title": _t(COMBINED_ESTABLISHMENT_LAYER_LABEL),
            "body": _tutorial_text("establishment_body"),
        },
        {
            "anchor": "map",
            "target": "iframeLegendSection",
            "legendSectionTitle": SCENARIO_ALLOCATION_LAYER_LABEL,
            "fallbackTarget": "iframeSelector",
            "iframeSelectors": [".map-legend"],
            "scrollWindowToTarget": True,
            "title": _t(SCENARIO_ALLOCATION_LAYER_LABEL),
            "mapLayers": [SCENARIO_ALLOCATION_LAYER_LABEL],
            "body": _tutorial_text("allocation_body"),
        },
        {
            "anchor": "map",
            "target": "iframeLegendSection",
            "legendSectionTitle": OUTSIDE_LP_NEED_LAYER_LABEL,
            "fallbackTarget": "iframeSelector",
            "iframeSelectors": [".map-legend"],
            "scrollWindowToTarget": True,
            "mapLayers": [OUTSIDE_LP_NEED_LAYER_LABEL],
            "title": _t(OUTSIDE_LP_NEED_LAYER_LABEL),
            "body": _tutorial_text("outside_body"),
        },
        {
            "anchor": "map",
            "target": "iframeGreenArea",
            "fallbackTarget": "nextIframe",
            "closeAllExpanders": True,
            "sidebarScrollTop": True,
            "scrollWindowToTarget": True,
            "stableHighlight": True,
            "title": _tutorial_text("green_title"),
            "body": _tutorial_text("green_body"),
        },
        {
            "selector": "section[data-testid=\"stSidebar\"]",
            "title": _tutorial_text("wind_solar_title"),
            "body": _tutorial_text("wind_solar_body"),
            "closeAllExpanders": True,
            "sidebarScrollTop": True,
            "openTexts": [geography_label],
            "highlightTexts": [wind_label, solar_label],
            "action": {
                "kind": "detailsOpen",
                "texts": [wind_label, solar_label],
                "todo": _tutorial_text("action_open_wind_todo"),
                "done": _tutorial_text("action_open_wind_done"),
            },
        },
        {
            "selector": "section[data-testid=\"stSidebar\"]",
            "title": _tutorial_text("wind_apply_title"),
            "body": _tutorial_text("wind_apply_body"),
            "closeAllExpanders": True,
            "sidebarScrollTop": True,
            "openTexts": [geography_label, wind_label, WIND_POPULATION_GROUP_LABEL],
            "scrollToText": wind_apply_label,
            "scrollAlign": 0.58,
            "highlightTexts": [wind_apply_label],
            "action": {
                "kind": "buttonClick",
                "id": "wind_apply",
                "text": wind_apply_label,
                "todo": _tutorial_text("action_apply_wind_todo"),
                "done": _tutorial_text("action_apply_wind_done"),
            },
        },
        {
            "selector": ".change-table-wrap",
            "anchor": "right-panel",
            "scrollWindowToTarget": True,
            "title": _tutorial_text("table_title"),
            "body": _tutorial_text("table_body"),
        },
        {
            "selector": "[data-potential-tutorial-anchor=\"right-geographies\"]",
            "scrollWindowToTarget": True,
            "title": _tutorial_text("right_geographies_title"),
            "body": _tutorial_text("right_geographies_body"),
        },
        {
            "selector": "[data-potential-tutorial-anchor=\"landscape-distribution\"]",
            "scrollWindowToTarget": True,
            "title": _tutorial_text("landscape_distribution_title"),
            "body": _tutorial_text("landscape_distribution_body"),
        },
        {
            "target": "buttonText",
            "buttonText": guide_label,
            "closeAllExpanders": True,
            "title": _tutorial_text("reopen_title"),
            "body": _tutorial_text("reopen_body"),
        },
    ]


def _render_tutorial_component(region: dict[str, Any], force_open: bool = False) -> None:
    if not _tutorial_available(region):
        return
    if components is None:
        if force_open:
            st.warning(_t("Guiden kräver Streamlit components och kan inte visas i den här miljön."))
        return

    payload = json.dumps(
        {
            "forceOpen": bool(force_open),
            "openToken": int(st.session_state.get(TUTORIAL_FORCE_OPEN_TOKEN_KEY, 0) or 0),
            "storageKey": TUTORIAL_STORAGE_KEY,
            "steps": _tutorial_steps(region),
            "labels": {
                "previous": _t("Föregående"),
                "next": _t("Nästa"),
                "skip": _t("Hoppa över"),
                "pause": _t("Pausa"),
                "resume": _t("Fortsätt guide"),
                "close": _t("Stäng"),
                "done": _t("Klar"),
                "actionTodo": _t("Testa detta"),
                "actionDone": _t("Klart"),
                "doNotAutoOpen": _t("Öppna inte automatiskt igen"),
                "step": _t("Steg"),
                "of": _t("av"),
            },
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")

    component_html = """
<div id="potential-tutorial-component-root" aria-hidden="true"></div>
<script>
(() => {
  const payload = __PAYLOAD__;
  let parentWindow;
  let parentDocument;
  try {
    parentWindow = window.parent;
    parentDocument = parentWindow.document;
  } catch (error) {
    return;
  }
  if (!parentWindow || !parentDocument || !Array.isArray(payload.steps) || payload.steps.length === 0) {
    return;
  }

  const storage = (() => {
    try {
      return parentWindow.localStorage;
    } catch (error) {
      try {
        return window.localStorage;
      } catch (innerError) {
        return null;
      }
    }
  })();

  const progressKey = `${payload.storageKey}:progress`;
  const pausedKey = `${payload.storageKey}:paused`;
  const actionKey = `${payload.storageKey}:actions`;
  const shouldAutoOpen = !storage || storage.getItem(payload.storageKey) !== "1";
  const hasPausedProgress = storage && storage.getItem(pausedKey) === "1";
  if (!payload.forceOpen && !shouldAutoOpen && !hasPausedProgress) {
    return;
  }

  if (typeof parentWindow.__potentialTutorialCleanup === "function") {
    parentWindow.__potentialTutorialCleanup();
  }

  const styleId = "potential-tutorial-style";
  const existingStyle = parentDocument.getElementById(styleId);
  const style = existingStyle || parentDocument.createElement("style");
  style.id = styleId;
  style.textContent = `
      #potential-tutorial-root {
        position: fixed;
        inset: 0;
        z-index: 2147483000;
        pointer-events: none;
        font-family: "Source Sans Pro", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      #potential-tutorial-root .pt-dim {
        display: none;
      }
      #potential-tutorial-root .pt-highlight {
        position: fixed;
        border: 2px solid #f8fafc;
        box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.82), 0 14px 34px rgba(15, 23, 42, 0.28);
        border-radius: 8px;
        pointer-events: none;
        transition: top 140ms ease, left 140ms ease, width 140ms ease, height 140ms ease;
        z-index: 1;
      }
      #potential-tutorial-root .pt-popover {
        position: fixed;
        width: min(360px, calc(100vw - 32px));
        max-height: calc(100vh - 32px);
        overflow: auto;
        border: 1px solid rgba(15, 23, 42, 0.14);
        border-radius: 8px;
        background: #ffffff;
        color: #111827;
        box-shadow: 0 18px 50px rgba(15, 23, 42, 0.26);
        padding: 0.95rem;
        pointer-events: auto;
        z-index: 2;
      }
      #potential-tutorial-root .pt-topline {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        margin-bottom: 0.35rem;
      }
      #potential-tutorial-root .pt-count {
        color: #4b5563;
        font-size: 0.78rem;
        font-weight: 700;
      }
      #potential-tutorial-root .pt-close {
        width: 2rem;
        height: 2rem;
        border: 0;
        border-radius: 6px;
        background: #f3f4f6;
        color: #111827;
        cursor: pointer;
        font-size: 1.05rem;
        line-height: 1;
      }
      #potential-tutorial-root h2 {
        margin: 0 0 0.42rem 0;
        color: #111827;
        font-size: 1.05rem;
        line-height: 1.22;
        letter-spacing: 0;
      }
      #potential-tutorial-root p {
        margin: 0;
        color: #374151;
        font-size: 0.92rem;
        line-height: 1.42;
      }
      #potential-tutorial-root .pt-action-status {
        margin-top: 0.72rem;
        border: 1px solid rgba(22, 101, 52, 0.18);
        border-radius: 6px;
        background: #f0fdf4;
        color: #166534;
        padding: 0.55rem 0.65rem;
        font-size: 0.84rem;
        line-height: 1.32;
      }
      #potential-tutorial-root .pt-action-status[data-state="todo"] {
        border-color: rgba(146, 64, 14, 0.18);
        background: #fffbeb;
        color: #92400e;
      }
      #potential-tutorial-root .pt-checkbox {
        display: flex;
        align-items: flex-start;
        gap: 0.48rem;
        margin: 0.82rem 0 0.9rem 0;
        color: #374151;
        font-size: 0.86rem;
        line-height: 1.25;
      }
      #potential-tutorial-root .pt-checkbox input {
        width: 1rem;
        height: 1rem;
        margin-top: 0.05rem;
      }
      #potential-tutorial-root .pt-actions {
        display: flex;
        justify-content: space-between;
        gap: 0.45rem;
        flex-wrap: wrap;
      }
      #potential-tutorial-root button {
        font: inherit;
      }
      #potential-tutorial-root .pt-button {
        min-height: 2rem;
        border: 1px solid rgba(15, 23, 42, 0.16);
        border-radius: 6px;
        background: #ffffff;
        color: #111827;
        padding: 0.38rem 0.65rem;
        cursor: pointer;
        font-size: 0.86rem;
        font-weight: 650;
      }
      #potential-tutorial-root .pt-button:disabled {
        cursor: not-allowed;
        opacity: 0.45;
      }
      #potential-tutorial-root .pt-button-primary {
        border-color: #166534;
        background: #166534;
        color: #ffffff;
      }
      #potential-tutorial-resume {
        position: fixed;
        right: 18px;
        bottom: 74px;
        z-index: 2147483001;
        min-height: 2.35rem;
        border: 1px solid rgba(22, 101, 52, 0.26);
        border-radius: 6px;
        background: #166534;
        color: #ffffff;
        box-shadow: 0 12px 32px rgba(15, 23, 42, 0.24);
        cursor: pointer;
        font: 650 0.9rem "Source Sans Pro", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        padding: 0.48rem 0.78rem;
      }
      @media (max-width: 680px) {
        #potential-tutorial-root .pt-popover {
          left: 16px !important;
          right: 16px !important;
          width: auto;
        }
      }
    `;
  if (!existingStyle) {
    parentDocument.head.appendChild(style);
  }

  const root = parentDocument.createElement("div");
  root.id = "potential-tutorial-root";
  const stableHighlightCache = parentWindow.__potentialTutorialStableHighlightCache || new Map();
  parentWindow.__potentialTutorialStableHighlightCache = stableHighlightCache;
  root.innerHTML = `
    <div class="pt-dim" data-dim="top"></div>
    <div class="pt-dim" data-dim="left"></div>
    <div class="pt-dim" data-dim="right"></div>
    <div class="pt-dim" data-dim="bottom"></div>
    <div class="pt-highlight"></div>
    <section class="pt-popover" role="dialog" aria-live="polite" aria-label="Tutorial">
      <div class="pt-topline">
        <div class="pt-count"></div>
        <button type="button" class="pt-close" aria-label="${payload.labels.close}">&times;</button>
      </div>
      <h2></h2>
      <p></p>
      <div class="pt-action-status" hidden></div>
      <label class="pt-checkbox">
        <input type="checkbox" />
        <span></span>
      </label>
      <div class="pt-actions">
        <span>
          <button type="button" class="pt-button pt-skip"></button>
          <button type="button" class="pt-button pt-pause"></button>
        </span>
        <span>
          <button type="button" class="pt-button pt-prev"></button>
          <button type="button" class="pt-button pt-button-primary pt-next"></button>
        </span>
      </div>
    </section>
  `;
  parentDocument.body.appendChild(root);

  const dims = {
    top: root.querySelector('[data-dim="top"]'),
    left: root.querySelector('[data-dim="left"]'),
    right: root.querySelector('[data-dim="right"]'),
    bottom: root.querySelector('[data-dim="bottom"]'),
  };
  const highlight = root.querySelector(".pt-highlight");
  const popover = root.querySelector(".pt-popover");
  const count = root.querySelector(".pt-count");
  const title = root.querySelector("h2");
  const body = root.querySelector("p");
  const actionStatus = root.querySelector(".pt-action-status");
  const remember = root.querySelector(".pt-checkbox input");
  const rememberLabel = root.querySelector(".pt-checkbox span");
  const closeButton = root.querySelector(".pt-close");
  const skipButton = root.querySelector(".pt-skip");
  const pauseButton = root.querySelector(".pt-pause");
  const prevButton = root.querySelector(".pt-prev");
  const nextButton = root.querySelector(".pt-next");
  let index = 0;
  let activeTarget = null;
  let resumeButton = null;
  let actionInterval = null;
  if (payload.forceOpen && storage) {
    storage.removeItem(pausedKey);
    storage.removeItem(progressKey);
    storage.removeItem(actionKey);
  }
  if (storage) {
    const savedIndex = Number.parseInt(storage.getItem(progressKey) || "", 10);
    if (Number.isFinite(savedIndex)) {
      index = Math.min(Math.max(savedIndex, 0), payload.steps.length - 1);
    }
  }

  rememberLabel.textContent = payload.labels.doNotAutoOpen;
  skipButton.textContent = payload.labels.skip;
  pauseButton.textContent = payload.labels.pause;
  prevButton.textContent = payload.labels.previous;
  if (storage && storage.getItem(payload.storageKey) === "1") {
    remember.checked = true;
  }

  const cleanup = () => {
    parentWindow.removeEventListener("resize", updatePosition);
    parentWindow.removeEventListener("scroll", updatePosition, true);
    parentDocument.removeEventListener("keydown", onKeyDown, true);
    parentDocument.removeEventListener("click", onDocumentClick, true);
    if (actionInterval) {
      parentWindow.clearInterval(actionInterval);
    }
    if (resumeButton && resumeButton.parentNode) {
      resumeButton.parentNode.removeChild(resumeButton);
    }
    if (root.parentNode) {
      root.parentNode.removeChild(root);
    }
    parentWindow.__potentialTutorialCleanup = null;
  };

  const persistPreference = () => {
    if (!storage) {
      return;
    }
    if (remember.checked) {
      storage.setItem(payload.storageKey, "1");
    } else {
      storage.removeItem(payload.storageKey);
    }
  };

  const saveProgress = () => {
    if (storage) {
      storage.setItem(progressKey, String(index));
    }
  };

  const close = () => {
    persistPreference();
    if (storage) {
      storage.removeItem(pausedKey);
      storage.removeItem(progressKey);
      storage.removeItem(actionKey);
    }
    cleanup();
  };

  const showResumeButton = () => {
    if (resumeButton && resumeButton.parentNode) {
      return;
    }
    resumeButton = parentDocument.createElement("button");
    resumeButton.id = "potential-tutorial-resume";
    resumeButton.type = "button";
    resumeButton.textContent = payload.labels.resume;
    resumeButton.addEventListener("click", resume);
    parentDocument.body.appendChild(resumeButton);
  };

  const hideResumeButton = () => {
    if (resumeButton && resumeButton.parentNode) {
      resumeButton.parentNode.removeChild(resumeButton);
    }
    resumeButton = null;
  };

  const pause = () => {
    saveProgress();
    if (storage) {
      storage.setItem(pausedKey, "1");
    }
    root.style.display = "none";
    showResumeButton();
  };

  const resume = () => {
    if (storage) {
      storage.removeItem(pausedKey);
    }
    hideResumeButton();
    root.style.display = "";
    render();
  };

  const markerFor = (anchor) => {
    if (!anchor) {
      return null;
    }
    return parentDocument.querySelector(`[data-potential-tutorial-anchor="${anchor}"]`) || parentDocument.getElementById(anchor);
  };

  const resolveSelector = (selector) => {
    if (!selector) {
      return null;
    }
    try {
      return parentDocument.querySelector(selector);
    } catch (error) {
      return null;
    }
  };

  const iframeForContainer = (container) => {
    if (!container) {
      return null;
    }
    return container.tagName && container.tagName.toLowerCase() === "iframe"
      ? container
      : container.querySelector("iframe");
  };

  const visibleMapFrames = () => Array.from(parentDocument.querySelectorAll("iframe"))
    .map((iframe) => {
      const container = iframe.closest('div[data-testid="stIFrame"]') || iframe;
      const rect = container.getBoundingClientRect();
      const visibleLeft = Math.max(0, rect.left);
      const visibleTop = Math.max(0, rect.top);
      const visibleRight = Math.min(parentWindow.innerWidth, rect.right);
      const visibleBottom = Math.min(parentWindow.innerHeight, rect.bottom);
      const visibleArea = Math.max(0, visibleRight - visibleLeft) * Math.max(0, visibleBottom - visibleTop);
      return { iframe, container, rect, visibleArea };
    })
    .filter((item) => (
      item.rect.width > 220 &&
      item.rect.height > 220 &&
      item.visibleArea > 50000 &&
      !item.container.closest('section[data-testid="stSidebar"]')
    ))
    .sort((a, b) => b.visibleArea - a.visibleArea);

  const findNextIframe = (anchor) => {
    const marker = markerFor(anchor);
    const frames = visibleMapFrames();
    if (!frames.length) {
      return null;
    }
    if (!marker) {
      return frames[0].container;
    }
    const markerTop = marker.getBoundingClientRect().top;
    const afterMarker = frames
      .filter((item) => item.rect.top >= markerTop - 24)
      .sort((a, b) => b.visibleArea - a.visibleArea);
    return (afterMarker[0] || frames[0]).container;
  };

    const normalizedText = (value) => String(value || "").replace(/\\s+/g, " ").trim().toLowerCase();
  const rightPanelScope = () => parentDocument.querySelector('div[data-testid="column"]:has(#right-panel-content-anchor)') || parentDocument;
  const scopeForStep = (step) => (step && step.scope === "rightPanel" ? rightPanelScope() : parentDocument);
  const isVisible = (node) => {
    if (!node || !node.getBoundingClientRect) {
      return false;
    }
    const rect = node.getBoundingClientRect();
    return rect.width > 2 && rect.height > 2;
  };

  const virtualRect = (rectProvider) => ({
    __virtual: true,
    getBoundingClientRect: rectProvider,
  });

  const combineRects = (nodes) => {
    const rects = nodes
      .filter((node) => node && (node.__virtual || isVisible(node)))
      .map((node) => node.getBoundingClientRect());
    if (!rects.length) {
      return null;
    }
    return virtualRect(() => {
      const liveRects = nodes
        .filter((node) => node && (node.__virtual || isVisible(node)))
        .map((node) => node.getBoundingClientRect());
      const source = liveRects.length ? liveRects : rects;
      const left = Math.min(...source.map((rect) => rect.left));
      const top = Math.min(...source.map((rect) => rect.top));
      const right = Math.max(...source.map((rect) => rect.right));
      const bottom = Math.max(...source.map((rect) => rect.bottom));
      return { left, top, right, bottom, width: right - left, height: bottom - top };
    });
  };

  const iframeElementTarget = (iframe, element) => {
    if (!iframe || !element || !isVisible(element)) {
      return null;
    }
    return virtualRect(() => {
      const frameRect = iframe.getBoundingClientRect();
      const rect = element.getBoundingClientRect();
      const left = frameRect.left + rect.left;
      const top = frameRect.top + rect.top;
      const right = left + rect.width;
      const bottom = top + rect.height;
      return { left, top, right, bottom, width: rect.width, height: rect.height };
    });
  };

  const iframeDocumentForStep = (step) => {
    const frameContainer = findNextIframe(step.anchor);
    const iframe = iframeForContainer(frameContainer);
    try {
      return iframe && iframe.contentDocument ? { iframe, doc: iframe.contentDocument } : null;
    } catch (error) {
      return null;
    }
  };

  const activateMapLayersForStep = (step) => {
    const layerNames = Array.isArray(step.mapLayers) ? step.mapLayers : [];
    if (!layerNames.length) {
      return;
    }
    const iframeInfo = iframeDocumentForStep(step);
    if (!iframeInfo || !iframeInfo.iframe || !iframeInfo.iframe.contentWindow) {
      return;
    }
    const mapWindow = iframeInfo.iframe.contentWindow;
    const setter = mapWindow.__potentialMapSetOverlayVisibility;
    if (typeof setter !== "function") {
      return;
    }
    layerNames.forEach((layerName) => {
      try {
        setter(String(layerName), true);
      } catch (error) {
        // The guide can still highlight the legend if the map is re-rendering.
      }
    });
  };

  const findIframeSelectorTarget = (step) => {
    const iframeInfo = iframeDocumentForStep(step);
    if (!iframeInfo) {
      return null;
    }
    const selectors = Array.isArray(step.iframeSelectors) ? step.iframeSelectors : [];
    for (const selector of selectors) {
      try {
        const element = iframeInfo.doc.querySelector(selector);
        const target = iframeElementTarget(iframeInfo.iframe, element);
        if (target) {
          return target;
        }
      } catch (error) {
        continue;
      }
    }
    return null;
  };

  const findIframeLegendSectionTarget = (step) => {
    const iframeInfo = iframeDocumentForStep(step);
    if (!iframeInfo) {
      return null;
    }
    const wanted = normalizedText(step.legendSectionTitle);
    if (!wanted) {
      return null;
    }
    const sections = Array.from(iframeInfo.doc.querySelectorAll(".map-legend-section"));
    const heading = sections.find((node) => normalizedText(node.textContent) === wanted);
    if (!heading) {
      return null;
    }
    const legend = heading.closest(".map-legend");
    if (legend && legend.scrollHeight > legend.clientHeight + 4) {
      legend.scrollTop = Math.max(0, heading.offsetTop - 8);
    }
    const nodes = [heading];
    let next = heading.nextElementSibling;
    while (next && !next.classList.contains("map-legend-section")) {
      if (next.classList.contains("map-legend-row")) {
        nodes.push(next);
      }
      next = next.nextElementSibling;
    }
    const target = combineRects(nodes);
    if (!target) {
      return null;
    }
    return virtualRect(() => {
      const frameRect = iframeInfo.iframe.getBoundingClientRect();
      const rect = target.getBoundingClientRect();
      const left = frameRect.left + rect.left;
      const top = frameRect.top + rect.top;
      const right = left + rect.width;
      const bottom = top + rect.height;
      return { left, top, right, bottom, width: rect.width, height: rect.height };
    });
  };

  const findGreenMapAreaTarget = (step) => {
    const iframeInfo = iframeDocumentForStep(step);
    if (!iframeInfo) {
      return null;
    }
    return virtualRect(() => {
      const frameRect = iframeInfo.iframe.getBoundingClientRect();
      const width = Math.min(parentWindow.innerWidth * 0.24, 520, Math.max(24, frameRect.width - 24));
      const height = Math.min(parentWindow.innerHeight * 0.35, 460, Math.max(24, frameRect.height - 24));
      const preferredLeft = parentWindow.innerWidth * 0.38;
      const preferredTop = parentWindow.innerHeight * 0.48;
      const left = Math.min(Math.max(preferredLeft, frameRect.left + 12), frameRect.right - width - 12);
      const top = Math.min(Math.max(preferredTop, frameRect.top + 12), frameRect.bottom - height - 12);
      const right = left + width;
      const bottom = top + height;
      return { left, top, right, bottom, width: right - left, height: bottom - top };
    });
  };

  const findExpanderForLabel = (label, scope = parentDocument) => {
    const wanted = normalizedText(label);
    if (!wanted) {
      return null;
    }
    const searchScope = scope || parentDocument;
    const details = Array.from(searchScope.querySelectorAll("details"));
    const matches = details.filter((node) => {
      const summary = node.querySelector("summary");
      const text = normalizedText(summary ? summary.textContent : node.textContent);
      return text === wanted || text.includes(wanted);
    });
    return (
      matches.find((node) => isVisible(node) && node.closest('section[data-testid="stSidebar"]')) ||
      matches.find((node) => isVisible(node)) ||
      matches.find((node) => node.closest('section[data-testid="stSidebar"]')) ||
      matches[0] ||
      null
    );
  };

  const findButtonByText = (label, scope = parentDocument) => {
    const wanted = normalizedText(label);
    if (!wanted) {
      return null;
    }
    const searchScope = scope || parentDocument;
    return Array.from(searchScope.querySelectorAll("button")).find((button) => {
      const text = normalizedText(button.textContent);
      return isVisible(button) && (text === wanted || text.includes(wanted));
    }) || null;
  };

  const findTextBlockByText = (label, scope = parentDocument) => {
    const wanted = normalizedText(label);
    if (!wanted) {
      return null;
    }
    const searchScope = scope || parentDocument;
    return Array.from(searchScope.querySelectorAll("h1,h2,h3,h4,h5,h6,summary,p,li")).find((node) => {
      const text = normalizedText(node.textContent);
      return isVisible(node) && (text === wanted || text.includes(wanted));
    }) || null;
  };

  const findElementByText = (label, scope = parentDocument) => (
    findExpanderForLabel(label, scope) || findButtonByText(label, scope) || findTextBlockByText(label, scope)
  );

  const actionIdentity = (action) => String((action && (action.id || action.text)) || "");

  const readActionState = () => {
    if (!storage) {
      return {};
    }
    try {
      const value = JSON.parse(storage.getItem(actionKey) || "{}");
      return value && typeof value === "object" ? value : {};
    } catch (error) {
      return {};
    }
  };

  const markActionDone = (action) => {
    const id = actionIdentity(action);
    if (!storage || !id) {
      return;
    }
    const actions = readActionState();
    actions[id] = true;
    storage.setItem(actionKey, JSON.stringify(actions));
  };

  const actionIsComplete = (action) => {
    if (!action || !action.kind) {
      return false;
    }
    if (action.kind === "detailsOpen") {
      const labels = Array.isArray(action.texts) ? action.texts : [];
      return labels.length > 0 && labels.every((label) => {
        const match = findExpanderForLabel(label);
        return Boolean(match && match.open);
      });
    }
    if (action.kind === "buttonClick") {
      const actions = readActionState();
      return Boolean(actions[actionIdentity(action)]);
    }
    return false;
  };

  const updateActionStatus = () => {
    const step = payload.steps[index] || {};
    const action = step.action || null;
    if (!action && step.showActionStatus !== false && step.suggestion) {
      actionStatus.hidden = false;
      actionStatus.dataset.state = "todo";
      actionStatus.textContent = `${payload.labels.actionTodo}: ${step.suggestion || ""}`;
      return;
    }
    if (!action || step.showActionStatus === false) {
      actionStatus.hidden = true;
      actionStatus.textContent = "";
      return;
    }
    const complete = actionIsComplete(action);
    actionStatus.hidden = false;
    actionStatus.dataset.state = complete ? "done" : "todo";
    const prefix = complete ? payload.labels.actionDone : payload.labels.actionTodo;
    const message = complete ? action.done : action.todo;
    actionStatus.textContent = `${prefix}: ${message || ""}`;
  };

  const onDocumentClick = (event) => {
    const target = event.target && event.target.closest
      ? event.target.closest("button,[role='button'],summary,label,input")
      : null;
    const clickedText = normalizedText(
      target ? (target.textContent || target.getAttribute("aria-label") || target.value || "") : ""
    );
    if (clickedText) {
      payload.steps.forEach((step) => {
        const action = step.action || null;
        if (!action || action.kind !== "buttonClick") {
          return;
        }
        const wanted = normalizedText(action.text);
        if (wanted && (clickedText === wanted || clickedText.includes(wanted))) {
          markActionDone(action);
        }
      });
    }
    parentWindow.setTimeout(updateActionStatus, 120);
  };

  const combinedTextTarget = (labels, scope = parentDocument) => {
    const nodes = (Array.isArray(labels) ? labels : [])
      .map((label) => findElementByText(label, scope))
      .filter(Boolean);
    return combineRects(nodes);
  };

  const firstStepExpander = (step) => {
    const labels = Array.isArray(step.openTexts) ? step.openTexts.map(normalizedText).filter(Boolean) : [];
    for (const label of labels) {
      const match = findExpanderForLabel(label);
      if (match) {
        return match;
      }
    }
    return null;
  };

  const openExpandersForStep = (step) => {
    const labels = Array.isArray(step.openTexts) ? step.openTexts.map(normalizedText).filter(Boolean) : [];
    if (!labels.length) {
      return;
    }
    labels.forEach((label) => {
      const match = findExpanderForLabel(label);
      if (match && !match.open) {
        match.open = true;
        match.dispatchEvent(new Event("toggle", { bubbles: true }));
      }
    });
  };

  const closeSidebarExpanders = () => {
    const sidebar = parentDocument.querySelector('section[data-testid="stSidebar"]');
    const scope = sidebar || parentDocument;
    Array.from(scope.querySelectorAll("details")).forEach((node) => {
      if (node.open) {
        node.open = false;
        node.dispatchEvent(new Event("toggle", { bubbles: true }));
      }
    });
  };

  const sidebarScrollContainers = () => {
    const sidebar = parentDocument.querySelector('section[data-testid="stSidebar"]');
    if (!sidebar) {
      return [];
    }
    const candidates = [sidebar, ...Array.from(sidebar.querySelectorAll("*"))].filter((node) => {
      const rect = node.getBoundingClientRect ? node.getBoundingClientRect() : null;
      if (!rect || rect.height < 80) {
        return false;
      }
      const style = parentWindow.getComputedStyle(node);
      return (
        node.scrollHeight > node.clientHeight + 8 &&
        ["auto", "scroll", "overlay"].includes(style.overflowY)
      );
    });
    return candidates.length ? candidates : [sidebar];
  };

  const setSidebarScrollTop = (top = 0) => {
    sidebarScrollContainers().forEach((node) => {
      node.scrollTop = top;
    });
  };

  const scrollSidebarToElement = (element, align = 0.5) => {
    if (!element || !element.getBoundingClientRect) {
      return;
    }
    sidebarScrollContainers().forEach((node) => {
      if (!node.contains(element)) {
        return;
      }
      const containerRect = node.getBoundingClientRect();
      const elementRect = element.getBoundingClientRect();
      const desiredTop = containerRect.top + containerRect.height * clamp(align, 0.1, 0.9);
      node.scrollTop += elementRect.top - desiredTop;
    });
  };

  const scrollSidebarToText = (label, align = 0.5) => {
    const target = findElementByText(label);
    if (target) {
      scrollSidebarToElement(target, align);
    }
  };

  const scrollTargetIntoViewport = (target) => {
    if (!target || !target.getBoundingClientRect) {
      return;
    }
    const rect = target.getBoundingClientRect();
    const margin = 24;
    let deltaY = 0;
    if (rect.bottom > parentWindow.innerHeight - margin) {
      deltaY = rect.bottom - parentWindow.innerHeight + margin;
    } else if (rect.top < margin) {
      deltaY = rect.top - margin;
    }
    if (Math.abs(deltaY) > 1) {
      parentWindow.scrollBy(0, deltaY);
      const sidebar = parentDocument.querySelector('section[data-testid="stSidebar"]');
      const candidates = [
        parentDocument.scrollingElement,
        parentDocument.documentElement,
        parentDocument.body,
        ...Array.from(parentDocument.querySelectorAll("*")),
      ].filter((node, index, nodes) => {
        if (!node || nodes.indexOf(node) !== index || (sidebar && sidebar.contains(node))) {
          return false;
        }
        const nodeRect = node.getBoundingClientRect ? node.getBoundingClientRect() : null;
        return (
          nodeRect &&
          nodeRect.height > 200 &&
          node.scrollHeight > node.clientHeight + 8
        );
      });
      candidates.forEach((node) => {
        node.scrollTop += deltaY;
      });
    }
  };

  const resolveTarget = (step) => {
    if (step.target === "iframeSelector") {
      return findIframeSelectorTarget(step) || (step.fallbackTarget === "nextIframe" ? findNextIframe(step.anchor) : null);
    }
    if (step.target === "iframeLegendSection") {
      return findIframeLegendSectionTarget(step) || (step.fallbackTarget === "iframeSelector" ? findIframeSelectorTarget(step) : null);
    }
    if (step.target === "iframeGreenArea") {
      return findGreenMapAreaTarget(step) || (step.fallbackTarget === "nextIframe" ? findNextIframe(step.anchor) : null);
    }
    if (step.target === "buttonText") {
      return findButtonByText(step.buttonText);
    }
    if (Array.isArray(step.highlightTexts)) {
      const textTarget = combinedTextTarget(step.highlightTexts, scopeForStep(step));
      if (textTarget) {
        return textTarget;
      }
    }
    if (step.target === "nextIframe") {
      return findNextIframe(step.anchor);
    }
    const stepExpander = firstStepExpander(step);
    if (stepExpander) {
      return stepExpander;
    }
    const selected = resolveSelector(step.selector);
    if (selected) {
      return selected;
    }
    const marker = markerFor(step.anchor);
    if (!marker) {
      return null;
    }
    return (
      marker.closest("section[data-testid='stSidebar']") ||
      marker.closest("div[data-testid='column']") ||
      marker.closest("div[data-testid='stVerticalBlock']") ||
      marker.closest("div[data-testid='stElementContainer']") ||
      marker.parentElement
    );
  };

  const setBox = (node, top, left, width, height) => {
    node.style.top = `${Math.max(0, top)}px`;
    node.style.left = `${Math.max(0, left)}px`;
    node.style.width = `${Math.max(0, width)}px`;
    node.style.height = `${Math.max(0, height)}px`;
  };

  const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

  function updatePosition() {
    const viewportWidth = parentWindow.innerWidth;
    const viewportHeight = parentWindow.innerHeight;
    let top = 72;
    let left = 24;
    let width = Math.min(420, viewportWidth - 48);
    let height = 160;

    if (activeTarget && (activeTarget.__virtual || parentDocument.body.contains(activeTarget))) {
      const rect = activeTarget.getBoundingClientRect();
      const pad = 8;
      top = clamp(rect.top - pad, 8, viewportHeight - 24);
      left = clamp(rect.left - pad, 8, viewportWidth - 24);
      width = clamp(rect.width + pad * 2, 24, viewportWidth - left - 8);
      height = clamp(rect.height + pad * 2, 24, viewportHeight - top - 8);
    }

    const seamOverlap = 2;
    const holeTop = Math.floor(top);
    const holeLeft = Math.floor(left);
    const holeRight = Math.ceil(left + width);
    const holeBottom = Math.ceil(top + height);
    const holeWidth = Math.max(0, holeRight - holeLeft);
    const holeHeight = Math.max(0, holeBottom - holeTop);
    setBox(dims.top, 0, 0, viewportWidth, holeTop + seamOverlap);
    setBox(dims.left, Math.max(0, holeTop - seamOverlap), 0, holeLeft + seamOverlap, holeHeight + seamOverlap * 2);
    setBox(
      dims.right,
      Math.max(0, holeTop - seamOverlap),
      Math.max(0, holeRight - seamOverlap),
      viewportWidth - holeRight + seamOverlap,
      holeHeight + seamOverlap * 2
    );
    setBox(
      dims.bottom,
      Math.max(0, holeBottom - seamOverlap),
      0,
      viewportWidth,
      viewportHeight - holeBottom + seamOverlap
    );
    setBox(highlight, holeTop, holeLeft, holeWidth, holeHeight);

    const popoverWidth = Math.min(360, viewportWidth - 32);
    const popoverHeight = popover.offsetHeight || 240;
    let popoverLeft = left + width + 16;
    if (popoverLeft + popoverWidth > viewportWidth - 16) {
      popoverLeft = left - popoverWidth - 16;
    }
    if (popoverLeft < 16) {
      popoverLeft = clamp(left + 8, 16, viewportWidth - popoverWidth - 16);
    }
    let popoverTop = clamp(top + 8, 16, viewportHeight - popoverHeight - 16);
    if (viewportWidth <= 680) {
      popoverLeft = 16;
      popoverTop = clamp(top + height + 12, 16, viewportHeight - popoverHeight - 16);
    }
    popover.style.left = `${popoverLeft}px`;
    popover.style.top = `${popoverTop}px`;
  }

  const render = () => {
    const step = payload.steps[index];
    if (step.closeAllExpanders) {
      closeSidebarExpanders();
    }
    openExpandersForStep(step);
    if (step.sidebarScrollTop) {
      setSidebarScrollTop(0);
    }
    if (step.scrollToText) {
      scrollSidebarToText(step.scrollToText, Number(step.scrollAlign || 0.5));
    }
    activateMapLayersForStep(step);
    activeTarget = resolveTarget(step);
    if (step.scrollWindowToTarget) {
      scrollTargetIntoViewport(activeTarget);
      activeTarget = resolveTarget(step);
    }
    if (step.stableHighlight && activeTarget && activeTarget.getBoundingClientRect) {
      const key = `${index}:${step.title || ""}`;
      const viewport = `${parentWindow.innerWidth}x${parentWindow.innerHeight}`;
      const cached = stableHighlightCache.get(key);
      if (cached && cached.viewport === viewport) {
        const cachedRect = cached.rect;
        activeTarget = virtualRect(() => ({ ...cachedRect }));
      } else {
        const rect = activeTarget.getBoundingClientRect();
        const stableRect = {
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        };
        stableHighlightCache.set(key, { viewport, rect: stableRect });
        activeTarget = virtualRect(() => ({ ...stableRect }));
      }
    }
    title.textContent = step.title || "";
    body.textContent = step.body || "";
    saveProgress();
    updateActionStatus();
    count.textContent = `${payload.labels.step} ${index + 1} ${payload.labels.of} ${payload.steps.length}`;
    prevButton.disabled = index === 0;
    nextButton.textContent = index === payload.steps.length - 1 ? payload.labels.done : payload.labels.next;
    if (activeTarget && typeof activeTarget.scrollIntoView === "function") {
      try {
        activeTarget.scrollIntoView({ block: "center", inline: "nearest", behavior: "smooth" });
      } catch (error) {
        activeTarget.scrollIntoView();
      }
    }
    parentWindow.setTimeout(updatePosition, 180);
    parentWindow.requestAnimationFrame(updatePosition);
    nextButton.focus({ preventScroll: true });
  };

  const go = (delta) => {
    index = clamp(index + delta, 0, payload.steps.length - 1);
    render();
  };

  const onKeyDown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      if (index === payload.steps.length - 1) {
        close();
      } else {
        go(1);
      }
    } else if (event.key === "ArrowLeft" && index > 0) {
      event.preventDefault();
      go(-1);
    }
  };

  closeButton.addEventListener("click", close);
  skipButton.addEventListener("click", close);
  pauseButton.addEventListener("click", pause);
  prevButton.addEventListener("click", () => go(-1));
  nextButton.addEventListener("click", () => {
    if (index === payload.steps.length - 1) {
      close();
    } else {
      go(1);
    }
  });
  parentWindow.addEventListener("resize", updatePosition);
  parentWindow.addEventListener("scroll", updatePosition, true);
  parentDocument.addEventListener("keydown", onKeyDown, true);
  parentDocument.addEventListener("click", onDocumentClick, true);
  actionInterval = parentWindow.setInterval(updateActionStatus, 800);
  parentWindow.__potentialTutorialCleanup = cleanup;

  if (payload.forceOpen && storage) {
    storage.removeItem(pausedKey);
  }
  if (!payload.forceOpen && storage && storage.getItem(pausedKey) === "1") {
    root.style.display = "none";
    showResumeButton();
  } else {
    parentWindow.setTimeout(render, 350);
  }
})();
</script>
""".replace("__PAYLOAD__", payload)
    components.html(component_html, height=0)


def _request_ui_only_rerun(reason: str) -> None:
    st.session_state[UI_ONLY_RERUN_KEY] = True
    st.session_state[UI_ONLY_RERUN_REASON_KEY] = str(reason)


def _ui_only_rerun_requested() -> bool:
    return bool(st.session_state.get(UI_ONLY_RERUN_KEY, False))


def _ui_only_rerun_reason() -> str:
    return str(st.session_state.get(UI_ONLY_RERUN_REASON_KEY, "visning"))


def _presentation_only_rerun_requested() -> bool:
    """Only existing presentation settings can replay without acquiring inputs."""
    return (
        _ui_only_rerun_requested()
        and _ui_only_rerun_reason() in PRESENTATION_ONLY_RERUN_REASONS
    )


def _clear_ui_only_rerun() -> None:
    st.session_state[UI_ONLY_RERUN_KEY] = False
    st.session_state[UI_ONLY_RERUN_REASON_KEY] = ""


def _workspace_calculation_fingerprint(
    region: dict[str, Any],
    h3_resolution: int,
    analysis_h3_resolution: int,
    zoom_family_enabled: bool,
    show_user_solar: bool,
    show_solar_v1: bool,
    show_user_wind: bool,
    social_acceptance_result: SocialAcceptanceResult | None,
    applied_solar_config: dict[str, Any],
    solar_params: dict[str, Any],
    solar_large_filter_configs: list[dict[str, Any]],
    wind_selected_layers: dict[str, list[str]],
    wind_ui_params: dict[str, Any],
    wind_workspace_request: Mapping[str, Any],
    energy_model_state: dict[str, Any],
    runtime_snapshot_token: str,
) -> str:
    """Hash the calculation inputs, deliberately excluding UI language."""
    social_result_signature = (
        social_acceptance_calculation_result_signature(
            social_acceptance_result
        )
        if social_acceptance_result is not None
        else None
    )
    payload = {
        "calculation_version": WORKSPACE_CALCULATION_VERSION,
        "region_id": str(region.get("region_id", "region")),
        "scenario_result": energy_model_state.get("scenario_result"),
        "h3_resolution": int(h3_resolution),
        "analysis_h3_resolution": int(analysis_h3_resolution),
        "zoom_family_enabled": bool(zoom_family_enabled),
        "show_user_solar": bool(show_user_solar),
        "show_solar_v1": bool(show_solar_v1),
        "show_user_wind": bool(show_user_wind),
        "social_acceptance_calculation_result_signature": (
            social_result_signature
        ),
        "applied_solar_config": {
            key: value
            for key, value in applied_solar_config.items()
            if key not in {
                SOLAR_VISUAL_SOURCE_GROUPS_KEY,
                SOLAR_VISUAL_BUFFER_GROUPS_KEY,
            }
        },
        "solar_params": solar_params,
        "solar_large_filter_configs": [
            {key: value for key, value in config.items()
             if key not in {"label", "layer_labels"}}
            for config in solar_large_filter_configs
        ],
        "wind_selected_layers": normalize_group_layer_map(wind_selected_layers),
        "wind_ui_params": wind_ui_params,
        "wind_workspace_request": dict(wind_workspace_request),
        "energy_available": bool(energy_model_state.get("available")),
        "runtime_snapshot_token": str(runtime_snapshot_token),
    }
    return _short_hash(payload)


def _cached_workspace_payload(fingerprint: str) -> dict[str, Any] | None:
    cached = st.session_state.get(WORKSPACE_RENDER_CACHE_KEY)
    if not isinstance(cached, dict):
        return None
    if str(cached.get("fingerprint", "")) != str(fingerprint):
        return None
    return cached


def _invalidate_workspace_cache(reason: str = "") -> None:
    st.session_state.pop(WORKSPACE_RENDER_CACHE_KEY, None)
    st.session_state.pop(WORKSPACE_PRESENTATION_SNAPSHOT_KEY, None)
    _clear_ui_only_rerun()
    if reason:
        st.session_state["workspace_cache_invalidated_reason"] = str(reason)


WIND_SHARE_CLASS_SPECS: list[dict[str, Any]] = [
    {"id": "share_0", "label": "0%", "max_pct": 0.0, "legend_label": "0%", "base_color": "#d7301f", "core_color": "#7f0000"},
    {"id": "share_1", "label": ">0-5%", "max_pct": 5.0, "legend_label": "<=5%", "base_color": "#ef4444", "core_color": "#991b1b"},
    {"id": "share_2", "label": ">5-10%", "max_pct": 10.0, "legend_label": None, "base_color": "#f87171", "core_color": "#b91c1c"},
    {"id": "share_3", "label": ">10-15%", "max_pct": 15.0, "legend_label": None, "base_color": "#fecaca", "core_color": "#ef4444"},
    {"id": "share_4", "label": ">15-25%", "max_pct": 25.0, "legend_label": "~25%", "base_color": "#dbeafe", "core_color": "#93c5fd"},
    {"id": "share_5", "label": ">25-35%", "max_pct": 35.0, "legend_label": None, "base_color": "#bfdbfe", "core_color": "#60a5fa"},
    {"id": "share_6", "label": ">35-50%", "max_pct": 50.0, "legend_label": "~50%", "base_color": "#93c5fd", "core_color": "#3b82f6"},
    {"id": "share_7", "label": ">50-65%", "max_pct": 65.0, "legend_label": None, "base_color": "#60a5fa", "core_color": "#2563eb"},
    {"id": "share_8", "label": ">65-80%", "max_pct": 80.0, "legend_label": None, "base_color": "#2563eb", "core_color": "#1d4ed8"},
    {"id": "share_9", "label": ">80-100%", "max_pct": 100.0, "legend_label": "100%", "base_color": "#1d4ed8", "core_color": "#1e3a8a"},
]
ESTABLISHMENT_CLASS_SPECS: dict[str, dict[str, str]] = {
    "not_suitable": {"label": "Inte lämplig", "color": "#991b1b", "stroke": "#fee2e2"},
    "wind_only": {"label": "Endast vind", "color": "#2563eb", "stroke": "#dbeafe"},
    "solar_only": {"label": "Endast sol", "color": "#facc15", "stroke": "#fef3c7"},
    "wind_and_solar": {"label": "Vind och sol", "color": "#15803d", "stroke": "#dcfce7"},
}
def _map_view_reset_token() -> int:
    try:
        return int(st.session_state.get(MAP_VIEW_RESET_TOKEN_KEY, 0))
    except Exception:
        return 0


def _init_panel_state() -> None:
    st.session_state.setdefault(LEFT_PANEL_OPEN_KEY, True)
    st.session_state.setdefault(RIGHT_PANEL_OPEN_KEY, True)
    if RIGHT_PANEL_WIDTH_KEY not in st.session_state:
        st.session_state[RIGHT_PANEL_WIDTH_KEY] = RIGHT_PANEL_WIDTH_DEFAULT
    elif st.session_state.get(RIGHT_PANEL_WIDTH_DEFAULT_VERSION_KEY) != RIGHT_PANEL_WIDTH_DEFAULT_VERSION:
        try:
            current_width = float(st.session_state.get(RIGHT_PANEL_WIDTH_KEY, RIGHT_PANEL_WIDTH_DEFAULT) or RIGHT_PANEL_WIDTH_DEFAULT)
        except Exception:
            current_width = RIGHT_PANEL_WIDTH_DEFAULT
        if any(abs(current_width - legacy_default) < 0.01 for legacy_default in RIGHT_PANEL_WIDTH_LEGACY_DEFAULTS):
            st.session_state[RIGHT_PANEL_WIDTH_KEY] = RIGHT_PANEL_WIDTH_DEFAULT
    st.session_state[RIGHT_PANEL_WIDTH_DEFAULT_VERSION_KEY] = RIGHT_PANEL_WIDTH_DEFAULT_VERSION


def _right_panel_width_pct() -> float:
    try:
        value = float(st.session_state.get(RIGHT_PANEL_WIDTH_KEY, RIGHT_PANEL_WIDTH_DEFAULT) or RIGHT_PANEL_WIDTH_DEFAULT)
    except Exception:
        value = RIGHT_PANEL_WIDTH_DEFAULT
    return max(0.0, min(100.0, value))


def _render_right_panel_width_control(panel: Any | None = None) -> None:
    target = panel or st
    target.caption(_t("Panelbredd"))
    target.slider(
        _t("Panelbredd"),
        min_value=0.0,
        max_value=100.0,
        step=1.0,
        key=RIGHT_PANEL_WIDTH_KEY,
        format="%.0f%%",
        label_visibility="collapsed",
        on_change=_request_ui_only_rerun,
        args=("panelbredd",),
        persist_state="session",
    )
    target.caption(
        _t("0% gör panelen minimal. 100% ger nästan hela arbetsytan till panelen.")
    )


def _toggle_panel(key: str) -> None:
    was_open = bool(st.session_state.get(key, True))
    st.session_state[key] = not was_open
    if key == RIGHT_PANEL_OPEN_KEY and was_open is False and _right_panel_width_pct() <= 0.0:
        st.session_state[RIGHT_PANEL_WIDTH_KEY] = RIGHT_PANEL_WIDTH_DEFAULT
    _request_ui_only_rerun("panel")


def _panel_shell() -> tuple[Any | None, Any | None]:
    _init_panel_state()
    left_open = bool(st.session_state.get(LEFT_PANEL_OPEN_KEY, True))
    right_open = bool(st.session_state.get(RIGHT_PANEL_OPEN_KEY, True))
    left_width = "min(20rem, 28vw)"
    right_width = "min(20rem, 28vw)"
    left_padding = f"calc({left_width} + 1.25rem)" if left_open else "1.5rem"
    right_padding = f"calc({right_width} + 1.25rem)" if right_open else "1.5rem"
    left_toggle_left = f"calc({left_width} + 0.45rem)" if left_open else "0.65rem"
    right_toggle_right = f"calc({right_width} + 0.45rem)" if right_open else "0.65rem"

    panel_css = f"""
        <style>
        div[data-testid="stAppViewContainer"] section.main .block-container,
        div[data-testid="stAppViewContainer"] .main .block-container {{
          max-width: none;
          padding-left: {left_padding};
          padding-right: {right_padding};
          padding-top: 0.7rem;
        }}
        div[data-testid="column"]:has(#left-panel-content-anchor) {{
          position: fixed !important;
          top: 0;
          left: 0;
          bottom: 0;
          width: {left_width} !important;
          min-width: {left_width} !important;
          max-width: {left_width} !important;
          flex: 0 0 {left_width} !important;
          z-index: 999;
          overflow-y: auto;
          overflow-x: hidden;
          background: rgb(244, 246, 249);
          border-right: 1px solid rgba(49, 51, 63, 0.16);
          padding: 3.3rem 1.05rem 2rem 1.05rem !important;
        }}
        div[data-testid="column"]:has(#right-panel-content-anchor) {{
          position: fixed !important;
          top: 0;
          right: 0;
          bottom: 0;
          width: {right_width} !important;
          min-width: {right_width} !important;
          max-width: {right_width} !important;
          flex: 0 0 {right_width} !important;
          z-index: 999;
          overflow-y: auto;
          overflow-x: hidden;
          background: rgb(244, 246, 249);
          border-left: 1px solid rgba(49, 51, 63, 0.16);
          padding: 3.3rem 1.05rem 2rem 1.05rem !important;
        }}
        div[data-testid="column"]:has(#left-panel-content-anchor) #left-panel-content-anchor,
        div[data-testid="column"]:has(#right-panel-content-anchor) #right-panel-content-anchor {{
          display: none;
        }}
        div[data-testid="column"]:has(#left-panel-toggle-anchor),
        div[data-testid="column"]:has(#right-panel-toggle-anchor) {{
          min-width: 1.75rem !important;
          width: 1.75rem !important;
          max-width: 1.75rem !important;
          flex: 0 0 1.75rem !important;
          padding-left: 0 !important;
          padding-right: 0 !important;
        }}
        div[data-testid="column"]:has(#left-panel-toggle-anchor) div[data-testid="stButton"],
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] {{
          position: fixed;
          top: 0.65rem;
          z-index: 1001;
          width: 1.75rem;
          margin: 0 !important;
          padding: 0 !important;
        }}
        div[data-testid="column"]:has(#left-panel-toggle-anchor) div[data-testid="stButton"] {{
          left: {left_toggle_left};
        }}
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] {{
          right: {right_toggle_right};
        }}
        div[data-testid="column"]:has(#left-panel-toggle-anchor) div[data-testid="stButton"] button,
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] button {{
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 1.75rem;
          min-width: 1.75rem;
          height: 1.75rem;
          min-height: 1.75rem;
          padding: 0;
          border: 0;
          border-radius: 0.25rem;
          background: rgba(255, 255, 255, 0.72);
          box-shadow: 0 1px 4px rgba(15, 23, 42, 0.15);
          color: rgba(49, 51, 63, 0.68);
          font-size: 1rem;
          font-weight: 700;
          line-height: 1;
        }}
        div[data-testid="column"]:has(#left-panel-toggle-anchor) div[data-testid="stButton"] button:hover,
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] button:hover {{
          background: rgba(255, 255, 255, 0.95);
          color: rgba(49, 51, 63, 0.9);
        }}
        div[data-testid="column"]:has(#left-panel-toggle-anchor) div[data-testid="stButton"] p,
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] p {{
          margin: 0;
          line-height: 1;
        }}
        .workspace-header {{
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 1rem;
          margin: 0.1rem 0 0.45rem 0;
        }}
        .workspace-header h1 {{
          font-size: 1.42rem;
          line-height: 1.15;
          margin: 0;
        }}
        .workspace-title-row {{
          display: flex;
          align-items: center;
          gap: 0.55rem;
          flex-wrap: wrap;
        }}
        .workspace-beta-badge {{
          display: inline-flex;
          align-items: center;
          min-height: 1.35rem;
          padding: 0.16rem 0.45rem;
          border-radius: 0.28rem;
          background: #7f1d1d;
          color: #fff;
          font-size: 0.72rem;
          font-weight: 700;
          letter-spacing: 0;
        }}
        .workspace-beta-note {{
          margin-top: 0.18rem;
          color: rgba(127, 29, 29, 0.88);
          font-size: 0.82rem;
          font-weight: 600;
        }}
        .workspace-eyebrow {{
          color: rgba(49, 51, 63, 0.68);
          font-size: 0.86rem;
          margin-bottom: 0.25rem;
        }}
        .workspace-pill {{
          border: 1px solid rgba(49, 51, 63, 0.16);
          border-radius: 8px;
          padding: 0.45rem 0.65rem;
          background: rgba(255, 255, 255, 0.72);
          color: rgba(49, 51, 63, 0.78);
          font-size: 0.86rem;
          white-space: nowrap;
        }}
        div[data-testid="stIFrame"] {{
          max-width: min(1320px, 100%);
          margin-left: auto !important;
          margin-right: auto !important;
          border: 1px solid rgba(49, 51, 63, 0.18);
          border-radius: 6px;
          overflow: hidden;
          box-shadow: 0 2px 8px rgba(15, 23, 42, 0.12);
          background: #fff;
        }}
        div[data-testid="stIFrame"] iframe {{
          width: 100% !important;
        }}
        </style>
        """
    st.markdown(panel_css, unsafe_allow_html=True)

    left_col, left_toggle_col, right_toggle_col, right_col = st.columns([1, 0.05, 0.05, 1], gap="small")
    with left_toggle_col:
        st.markdown('<span id="left-panel-toggle-anchor"></span>', unsafe_allow_html=True)
        st.button(
            "<" if left_open else ">",
            key="left_panel_edge_toggle",
            help="Visa/dölj kartlager",
            on_click=_toggle_panel,
            args=(LEFT_PANEL_OPEN_KEY,),
        )
    with right_toggle_col:
        st.markdown('<span id="right-panel-toggle-anchor"></span>', unsafe_allow_html=True)
        st.button(
            ">" if right_open else "<",
            key="right_panel_edge_toggle",
            help=_t("Visa/dölj kontext"),
            on_click=_toggle_panel,
            args=(RIGHT_PANEL_OPEN_KEY,),
        )

    left_panel = None
    right_panel = None
    if left_open:
        with left_col:
            st.markdown('<span id="left-panel-content-anchor"></span>', unsafe_allow_html=True)
            left_panel = st.container()
    if right_open:
        with right_col:
            st.markdown('<span id="right-panel-content-anchor"></span>', unsafe_allow_html=True)
            right_panel = st.container()
    return left_panel, right_panel


def _workspace_shell() -> tuple[Any | None, Any, Any | None]:
    _init_panel_state()
    right_panel_width_pct = _right_panel_width_pct()
    if right_panel_width_pct <= 0.0:
        main_ratio = 1.0
        right_ratio = 0.035
    elif right_panel_width_pct >= 99.5:
        main_ratio = 0.015
        right_ratio = 1.0
    else:
        main_ratio = max(0.015, 100.0 - right_panel_width_pct)
        right_ratio = max(0.035, right_panel_width_pct)
    panel_css = """
        <style>
        div[data-testid="stAppViewContainer"] section.main .block-container,
        div[data-testid="stAppViewContainer"] .main .block-container {
          max-width: none;
          padding: 0.75rem 0.9rem 1rem 0.9rem;
        }
        .workspace-header {
          display: flex;
          align-items: flex-end;
          justify-content: space-between;
          gap: 1rem;
          margin: 0.1rem 0 0.45rem 0;
        }
        .workspace-header h1 {
          font-size: 1.42rem;
          line-height: 1.15;
          margin: 0;
        }
        .workspace-title-row {
          display: flex;
          align-items: center;
          gap: 0.55rem;
          flex-wrap: wrap;
        }
        .workspace-beta-badge {
          display: inline-flex;
          align-items: center;
          min-height: 1.35rem;
          padding: 0.16rem 0.45rem;
          border-radius: 0.28rem;
          background: #7f1d1d;
          color: #fff;
          font-size: 0.72rem;
          font-weight: 700;
          letter-spacing: 0;
        }
        .workspace-beta-note {
          margin-top: 0.18rem;
          color: rgba(127, 29, 29, 0.88);
          font-size: 0.82rem;
          font-weight: 600;
        }
        .workspace-eyebrow {
          color: rgba(49, 51, 63, 0.68);
          font-size: 0.86rem;
          margin-bottom: 0.25rem;
        }
        .workspace-pill {
          border: 1px solid rgba(49, 51, 63, 0.16);
          border-radius: 8px;
          padding: 0.45rem 0.65rem;
          background: rgba(255, 255, 255, 0.72);
          color: rgba(49, 51, 63, 0.78);
          font-size: 0.86rem;
          white-space: nowrap;
        }
        div[data-testid="stIFrame"] {
          max-width: 100%;
          margin-left: auto !important;
          margin-right: auto !important;
          border: 1px solid rgba(49, 51, 63, 0.18);
          border-radius: 6px;
          overflow: hidden;
          box-shadow: 0 2px 8px rgba(15, 23, 42, 0.12);
          background: #fff;
        }
        div[data-testid="stIFrame"] iframe {
          width: 100% !important;
        }
        div[data-testid="column"]:has(#right-panel-toggle-anchor) {
          resize: horizontal;
          overflow: auto;
          border-left: 1px solid rgba(49, 51, 63, 0.14);
          padding-left: 0.75rem !important;
        }
        div[data-testid="column"]:has(#right-panel-toggle-anchor)::before {
          content: "";
          position: absolute;
          top: 0;
          left: 0;
          bottom: 0;
          width: 0.55rem;
          cursor: ew-resize;
          background: linear-gradient(90deg, rgba(15, 23, 42, 0.12), rgba(15, 23, 42, 0));
        }
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] {
          width: 1.75rem;
          margin: 0 !important;
          padding: 0 !important;
        }
        div[data-testid="column"]:has(#right-panel-toggle-anchor) div[data-testid="stButton"] button {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          width: 1.75rem;
          min-width: 1.75rem;
          height: 1.75rem;
          min-height: 1.75rem;
          padding: 0;
          border-radius: 0.25rem;
          background: rgba(255, 255, 255, 0.86);
          box-shadow: 0 1px 4px rgba(15, 23, 42, 0.15);
          color: rgba(49, 51, 63, 0.78);
          font-weight: 700;
        }
        div[data-testid="column"]:has(#right-panel-content-anchor) div[data-testid="stDataFrame"],
        div[data-testid="column"]:has(#right-panel-content-anchor) div[data-testid="stTable"] {
          overflow-x: auto;
        }
        div[data-testid="column"]:has(#right-panel-content-anchor) [data-testid="stMetricValue"] {
          font-size: clamp(1.15rem, 1.6vw, 1.75rem);
          line-height: 1.1;
        }
        /* Only the outer context expander controls workspace width. Nested
           result expanders must not collapse the column. Follow the native
           content's inert state so its 500 ms height animation adds no wait. */
        .st-key-workspace_context_panel details:not(details details) {
          height: auto !important;
          overflow: visible !important;
        }
        .st-key-workspace_context_panel [data-testid="stExpanderDetails"][inert]:not(details details *) {
          display: none !important;
        }
        @media (min-width: 641px) {
          [data-testid="stHorizontalBlock"]:has(.st-key-workspace_context_panel [data-testid="stExpanderDetails"][inert]:not(details details *)) > [data-testid="stColumn"]:first-child {
            flex: 1 1 0% !important;
            min-width: 0 !important;
            width: auto !important;
          }
          [data-testid="stHorizontalBlock"]:has(.st-key-workspace_context_panel [data-testid="stExpanderDetails"][inert]:not(details details *)) > [data-testid="stColumn"]:last-child {
            flex: 0 0 3rem !important;
            min-width: 3rem !important;
            width: 3rem !important;
          }
          .st-key-workspace_context_panel details:has(> [data-testid="stExpanderDetails"][inert]):not(details details) > summary [data-testid="stMarkdownContainer"] {
            position: absolute;
            width: 1px;
            height: 1px;
            overflow: hidden;
            clip-path: inset(50%);
            white-space: nowrap;
          }
        }
        </style>
        """
    st.markdown(_t(panel_css), unsafe_allow_html=True)

    main_col, right_col = st.columns([main_ratio, right_ratio], gap="medium")
    left_panel = st.sidebar

    with right_col:
        st.markdown('<span id="right-panel-toggle-anchor"></span>', unsafe_allow_html=True)
        # A visibility change needs no server request or analysis rerun. Keep
        # the content mounted so results and controls survive reopening.
        right_panel = st.expander(
            _t("Visa/dölj kontext"),
            expanded=False,
            key="workspace_context_panel",
            on_change="ignore",
        )
        with right_panel:
            st.markdown('<span id="right-panel-content-anchor"></span>', unsafe_allow_html=True)

    return left_panel, main_col, right_panel


def _query_param_value(key: str) -> str | None:
    try:
        value = st.query_params.get(key)
    except Exception:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value) if value not in {None, ""} else None


def _set_query_param(key: str, value: str) -> None:
    try:
        st.query_params[key] = value
    except Exception:
        return


def _clear_query_param(key: str) -> None:
    try:
        del st.query_params[key]
    except Exception:
        return


def _region_sort_key(region: dict[str, Any]) -> tuple[int, str]:
    card = region.get("landing_card") or {}
    try:
        order = int(card.get("sort_order", 999))
    except Exception:
        order = 999
    return order, str(region.get("display_name", region.get("region_id", "")))


def _landing_regions() -> list[dict[str, Any]]:
    return sorted(
        [region for region in list_regions() if isinstance(region.get("landing_card"), dict)],
        key=_region_sort_key,
    )


def _region_lookup() -> dict[str, dict[str, Any]]:
    return {str(region.get("region_id", "")).lower(): region for region in _landing_regions()}


def _region_display_name(region: dict[str, Any]) -> str:
    """Use canonical local names without changing pinned manifest identities."""
    if str(region.get("region_id", "")).lower() == "trondelag":
        return "Trøndelag"
    return str(region.get("display_name") or region.get("region_id", ""))


def _region_card_enabled(region: dict[str, Any]) -> bool:
    card = region.get("landing_card") or {}
    if "enabled" in card:
        return bool(card.get("enabled"))
    return str(region.get("status", "")).lower() in {"active", "ready", "app_ready"}


def _local_review_allowlist() -> set[str]:
    return {
        value.strip().lower()
        for value in os.environ.get(LOCAL_REVIEW_REGIONS_ENV, "").split(",")
        if value.strip()
    }


def _local_review_default_h3_resolution(region_id: str) -> int | None:
    """Return only a valid repo-declared default; never use archive fallback."""

    try:
        manifest = load_delivery_region_manifest(
            str(region_id or "").strip().lower()
        )
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError):
        return None
    raw_default = manifest.get("default_h3_resolution")
    raw_available = manifest.get("available_h3_resolutions")
    if (
        not isinstance(raw_default, (int, float))
        or isinstance(raw_default, bool)
        or not math.isfinite(float(raw_default))
        or not float(raw_default).is_integer()
        or not isinstance(raw_available, list)
    ):
        return None
    available: list[int] = []
    for value in raw_available:
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(float(value))
            or not float(value).is_integer()
        ):
            return None
        available.append(int(value))
    default_resolution = int(raw_default)
    return default_resolution if default_resolution in available else None


def _local_review_config(
    region: dict[str, Any],
) -> ReviewAccessContract | None:
    region_id = str(region.get("region_id") or "").strip().lower()
    if not region_id:
        return None
    try:
        return load_review_access(region_id)
    except (FileNotFoundError, KeyError, OSError, TypeError, ValueError):
        return None


def _review_access_presentation(
    config: ReviewAccessContract,
) -> dict[str, str]:
    """Present manifest trust without deriving behavior from a region id."""

    presentations = {
        "diagnostic_only": {
            "label": "Endast diagnostik",
            "color": "blue",
            "icon": ":material/science:",
            "note": "Underlaget är inte regionalt accepterat beslutstöd.",
        },
        "candidate": {
            "label": "Kandidat",
            "color": "orange",
            "icon": ":material/experiment:",
            "note": "Underlaget är kandidatmaterial och väntar på teknisk validering.",
        },
        "technically_validated": {
            "label": "Tekniskt validerad",
            "color": "blue",
            "icon": ":material/verified:",
            "note": "Teknisk validering är klar; regional acceptans är en separat gate.",
        },
        "regionally_accepted": {
            "label": "Regionalt accepterad",
            "color": "green",
            "icon": ":material/verified_user:",
            "note": "Underlaget är regionalt accepterat enligt åtkomstkontraktet.",
        },
    }
    try:
        return dict(presentations[config.access_classification])
    except KeyError as exc:
        raise ValueError(
            "Review access has an unsupported trust classification: "
            f"{config.access_classification!r}"
        ) from exc




def _local_review_landing_enabled(region: dict[str, Any]) -> bool:
    region_id = str(region.get("region_id") or "").strip().lower()
    return bool(
        region_id
        and _local_review_config(region) is not None
        and region_id in _local_review_allowlist()
    )




def _reset_session_for_region(
    region_id: str,
    access_mode: str = "product",
) -> None:
    normalized_region_id = str(region_id or "").strip().lower()
    normalized_access_mode = str(access_mode or "").strip().lower()
    if not normalized_region_id or normalized_access_mode not in {
        "product",
        "review",
    }:
        raise ValueError("Region session reset requires a valid access scope")
    next_map_token = (
        int(st.session_state.get(MAP_VIEW_RESET_TOKEN_KEY, 0) or 0) + 1
    )
    preserved = {
        key: st.session_state[key]
        for key in REGION_SESSION_PRESERVE_KEYS
        if key in st.session_state
    }
    for key in list(st.session_state):
        del st.session_state[key]
    for key, value in preserved.items():
        st.session_state[key] = value
    st.session_state[MAP_VIEW_RESET_TOKEN_KEY] = next_map_token
    st.session_state[REGION_SESSION_SCOPE_KEY] = (
        f"{normalized_access_mode}:{normalized_region_id}"
    )


def _select_region(region_id: str) -> None:
    st.session_state[REGION_SELECT_KEY] = str(region_id)
    _set_query_param("region", str(region_id))
    _clear_query_param("view")
    _clear_query_param("mode")
    st.rerun()


def _select_local_review_region(region_id: str, mode: str) -> None:
    st.session_state[REGION_SELECT_KEY] = str(region_id)
    _set_query_param("region", str(region_id))
    _clear_query_param("mode")
    _clear_query_param("view")
    st.rerun()


def _open_region_landing() -> None:
    st.session_state.pop(SIDEBAR_ENTRY_KEY, None)
    _set_query_param("view", REGION_LANDING_VIEW)
    _clear_query_param("mode")


def _render_region_landing() -> None:
    regions = _landing_regions()
    if not regions:
        st.error(_t("Inga regionmanifest hittades."))
        return

    cards = [
        LandingRegion(
            region_id=str(region["region_id"]),
            title=_region_display_name(region),
            enabled=_region_card_enabled(region) or _local_review_landing_enabled(region),
        )
        for region in regions
    ]
    selected_id = render_landing(
        cards, lambda: _render_language_switcher(st), language=_language(),
    )
    if selected_id is None:
        return
    region = next(region for region in regions if region["region_id"] == selected_id)
    if _region_card_enabled(region):
        _select_region(selected_id)
    elif _local_review_landing_enabled(region):
        review_config = _local_review_config(region)
        if review_config is not None:
            _select_local_review_region(selected_id, review_config.mode)


def _active_region(route: WorkspaceRouteDecision) -> dict[str, Any]:
    """Load only the exact region selected by the pure route contract."""

    if route.kind not in {"product", "review"}:
        raise ValueError("A closed route cannot activate a workspace region")
    region_id = str(route.region_id or "").strip().lower()
    if not region_id or route.access_scope is None:
        raise ValueError("An active workspace route requires region and scope")
    try:
        region = load_region(region_id)
    except Exception as exc:
        st.error(
            _t("Det valda regionmanifestet kunde inte läsas. Ingen annan "
            "region öppnas automatiskt.")
        )
        st.caption(_t('Teknisk orsak: {p0}', p0=exc))
        st.stop()
    resolved_region_id = str(region.get("region_id", region_id)).strip().lower()
    if resolved_region_id != region_id:
        st.error(
            _t("Regionens identitet stämmer inte med det inlästa "
            "manifestet. Arbetsytan förblir stängd.")
        )
        st.stop()
    active_scope = str(
        st.session_state.get(REGION_SESSION_SCOPE_KEY, "") or ""
    ).strip().lower()
    expected_scope = route.access_scope
    if active_scope != expected_scope:
        _reset_session_for_region(resolved_region_id, route.kind)
    st.session_state[REGION_SELECT_KEY] = resolved_region_id
    return region


def _render_region_switcher(
    region: dict[str, Any],
    *,
    show_region_caption: bool = True,
) -> None:
    if show_region_caption:
        st.sidebar.caption(
            f"{_t('Region')}: "
            f"{_region_display_name(region)}"
        )
    st.sidebar.button(
        _t("Till SpeedLocal-översikten"),
        key="potential_region_landing_button",
        width="stretch",
        on_click=_open_region_landing,
    )




def _workspace_header() -> None:
    st.markdown(
        f"""
        <div class="workspace-header" data-potential-tutorial-anchor="workspace-header" data-workspace-guide="region">
          <div>
            <div class="workspace-title-row">
              <h1>{_t(PAGE_TITLE)}</h1>
              <span class="workspace-beta-badge">{APP_RELEASE_STAGE}</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _load_context(region: dict[str, Any]) -> dict[str, Any]:
    context = load_region_context(region)
    if not bool(context.get("runtime_ready")):
        return context
    landscape_manifest = context.get(
        LEGACY_NUMERICAL_LANDSCAPE_CONTEXT_KEY
    )
    if not isinstance(landscape_manifest, dict):
        return context
    region_id = str(region.get("region_id") or "").strip().lower()
    if not region_id:
        raise ValueError("Region id is required for technology context")
    bound_manifest = dict(landscape_manifest)
    bound_manifest.update(
        shared_technology_context_manifest_overlay(region_id)
    )
    bound_context = dict(context)
    bound_context[LEGACY_NUMERICAL_LANDSCAPE_CONTEXT_KEY] = (
        bound_manifest
    )
    return bound_context


def _review_workspace_context(
    readiness: WorkspaceReviewReadiness,
) -> dict[str, Any]:
    """Build the shared UI context without authorizing product computation."""

    rows = _review_readiness_rows(readiness)
    blocked_rows = [
        row
        for row in rows
        if str(row.get("Årsagskode") or "")
        not in {
            "technically_validated",
            "regionally_accepted",
            "public",
        }
    ]
    return {
        "landscape_manifest": None,
        "potential_manifest": None,
        "scenario_manifest": None,
        "social_acceptance_manifest": None,
        "solar_rules": None,
        "wind_rules": None,
        "missing_data": blocked_rows,
        "review_status_rows": rows,
        "runtime_ready": False,
    }


def _available_h3_resolutions(region: dict[str, Any]) -> list[int]:
    return region_available_h3_resolutions(region)


def _preferred_h3_resolution(region: dict[str, Any], preferred: int = 10) -> int:
    available = _available_h3_resolutions(region)
    return int(preferred) if int(preferred) in available else int(available[0])


def _workspace_analysis_h3_resolution(
    region: dict[str, Any],
    preferred: int | None = None,
) -> int:
    available = _available_h3_resolutions(region)
    try:
        default_resolution = int(region.get("default_h3_resolution") or 9)
    except Exception:
        default_resolution = 9
    if default_resolution in available:
        return int(default_resolution)
    if preferred is not None and int(preferred) in available:
        return int(preferred)
    return _preferred_h3_resolution(region, default_resolution)


def _wind_analysis_h3_resolution(region: dict[str, Any]) -> int:
    available = _available_h3_resolutions(region)
    region_id = str(region.get("region_id") or "")
    resolution = int(
        technology_support_domain_resolution(region_id, "wind")
    )
    if resolution not in available:
        raise ValueError(
            f"{region_id}/wind analysis domain is R{resolution}, but no "
            "matching display geometry is available"
        )
    return resolution


def _h3_display_geometry_path(
    region: dict[str, Any], resolution: int,
) -> str | DomainDisplayPayload | None:
    analysis = load_delivery_analysis(str(region.get("region_id") or ""), "wind")
    if any(layer.source.postgis_reference is not None for layer in analysis.layers.values()):
        return read_analysis_domain_input(analysis, "standard_analysis", int(resolution))
    geometry_paths = region.get("h3_display_geometries") or {}
    path_value = geometry_paths.get(str(resolution))
    path = resolve_repo_path(path_value) if path_value else None
    if path is None or not path.exists():
        return None
    return str(path)


def _area_display_geometry_path(
    region: dict[str, Any],
    resolution: int,
) -> str:
    region_id = str(region.get("region_id") or "").strip()
    if not region_id:
        raise ValueError("Combined area display requires a region id")
    return shared_area_display_geometry_path(region_id, int(resolution))


@st.cache_data(show_spinner=False)
def _h3_display_hex_ids(display_geometry_path: str | DomainDisplayPayload) -> frozenset[str]:
    return frozenset(load_h3_display_geometries(display_geometry_path))


def _review_readiness_rows(
    readiness: WorkspaceReviewReadiness,
) -> list[dict[str, str]]:
    """Build one presentation table from stable readiness fields."""

    status_labels = {
        "missing_manifest": "Saknas i manifestet",
        "missing_data": "Data saknas",
        "not_implemented": "Inte implementerad",
        "not_validated": "Inte validerad",
        "technically_validated": "Tekniskt validerad",
        "regionally_accepted": "Regionalt accepterad",
        "public": "Publik",
    }
    return [
        {
            "Område": "Arbetsyta",
            "Kontrol": item.capability_id,
            "Status": status_labels[item.state],
            "Årsagskode": item.state,
            "Detalje": item.detail,
            "capability_id": item.capability_id,
            "state": item.state,
            "interaction": item.interaction,
        }
        for item in readiness.capabilities
    ]




@st.cache_data(show_spinner=False, max_entries=8)
def _workspace_access_readiness(
    region_id: str,
    access_scope: str,
    runtime_snapshot_token: str,
) -> WorkspaceAccessReadiness:
    """Resolve product and review through one catalog-backed contract."""

    if (
        len(runtime_snapshot_token) != 64
        or any(character not in "0123456789abcdef" for character in runtime_snapshot_token)
    ):
        raise ValueError("Workspace runtime snapshot token must be SHA-256")

    return resolve_catalog_workspace_access_readiness(
        str(region_id or "").strip().lower(),
        str(access_scope or "").strip().lower(),
        route_authorized=True,
    )


def _workspace_access_analysis_bundles(
    readiness: WorkspaceAccessReadiness,
    analysis_id: str,
) -> tuple[Mapping[str, Any], ...]:
    """Select executable groups for one product-or-review analysis form."""

    bundles = tuple(
        {
            "region_id": state.bundle.region_id,
            "analysis_id": state.bundle.analysis_id,
            "group_id": state.bundle.group_id,
            "layer_ids": state.bundle.layer_ids,
            "operations": state.bundle.operations,
            "parameter_ids": state.bundle.parameter_ids,
        }
        for state in readiness.analysis_slices(
            str(analysis_id),
            interactive_only=True,
        )
    )
    if not bundles:
        return ()
    identities = {
        (str(bundle["region_id"]), str(bundle["analysis_id"]))
        for bundle in bundles
    }
    group_ids = [str(bundle["group_id"]) for bundle in bundles]
    if len(identities) != 1 or len(group_ids) != len(set(group_ids)):
        raise ValueError("Workspace slice identities are ambiguous")
    return bundles


def _workspace_analysis_request_for_view(
    identity: WorkspaceUiIdentity,
    bundles: tuple[Mapping[str, Any], ...],
) -> WorkspaceAnalysisRequest | None:
    """Return the exact applied request for all allowed groups in one form."""

    if not bundles:
        raise ValueError("The active workspace analysis has no allowed slices")
    analysis_id = _workspace_analysis_id(identity)
    bundle_analysis_id = str(bundles[0]["analysis_id"])
    if bundle_analysis_id != analysis_id:
        raise ValueError("Review slice does not match its analysis UI scope")
    request = _read_applied_workspace_request(identity)
    if request is None:
        return None
    region_id = str(bundles[0]["region_id"])
    allowed_group_ids = {str(bundle["group_id"]) for bundle in bundles}
    if (
        request.access_scope != identity.access_scope
        or request.region_id != region_id
        or request.analysis_id != analysis_id
        or any(
            group.group_id not in allowed_group_ids
            for group in request.groups
        )
    ):
        st.session_state.pop(_workspace_applied_request_key(identity), None)
        return None
    return request


def _workspace_analysis_empty_request(
    identity: WorkspaceUiIdentity,
    bundles: tuple[Mapping[str, Any], ...],
) -> WorkspaceAnalysisRequest:
    """Build an empty request; the execution owner resolves its exact state."""

    if not bundles:
        raise ValueError("The active review analysis has no allowed slices")
    bundle = bundles[0]
    analysis_id = _workspace_analysis_id(identity)
    if str(bundle["analysis_id"]) != analysis_id:
        raise ValueError("Review slice does not match its analysis UI scope")
    contract = load_delivery_analysis(
        str(bundle["region_id"]),
        analysis_id,
    )
    return build_workspace_analysis_request_from_contract(
        contract,
        access_scope=identity.access_scope,
        selected_group_layers={},
        group_parameters={},
    )


def _workspace_analysis_execution_input_for_view(
    identity: WorkspaceUiIdentity,
    bundles: tuple[Mapping[str, Any], ...],
    access_readiness: WorkspaceAccessReadiness,
) -> WorkspaceAnalysisExecutionInput:
    """Bind one UI namespace to explicit apply and area authorities."""

    applied_request = _workspace_analysis_request_for_view(identity, bundles)
    request = (
        applied_request
        if applied_request is not None
        else _workspace_analysis_empty_request(identity, bundles)
    )
    execution_state = (
        WorkspaceExecutionState.APPLIED
        if applied_request is not None or identity.access_kind == "product"
        else WorkspaceExecutionState.NEUTRAL_PREVIEW
    )
    area_capability = next(
        (
            capability
            for capability in access_readiness.capabilities
            if capability.capability_id == f"{request.analysis_id}.area"
        ),
        None,
    )
    area_execution = (
        WorkspaceAreaExecution.EXECUTE
        if execution_state is WorkspaceExecutionState.APPLIED
        and area_capability is not None
        and area_capability.interaction == "interactive"
        else WorkspaceAreaExecution.NOT_AVAILABLE
    )
    return WorkspaceAnalysisExecutionInput(
        request=request,
        execution_state=execution_state,
        area_execution=area_execution,
    )


def _build_workspace_execution_payload(
    execution_input_jsons: tuple[str, ...],
) -> WorkspaceExecutionBundle:
    """Run the pure typed chain without copying its large renderer payload."""

    if not execution_input_jsons:
        raise ValueError("Workspace presentation requires at least one input")
    execution_inputs = tuple(
        parse_workspace_analysis_execution_input(json.loads(input_json))
        for input_json in execution_input_jsons
    )
    return run_catalog_workspace_execution(execution_inputs)


def _workspace_execution_bundle(
    execution_inputs: tuple[WorkspaceAnalysisExecutionInput, ...],
    access_readiness: WorkspaceAccessReadiness,
) -> WorkspaceExecutionBundle:
    """Resolve the exact common execution/map/result payload for one access."""

    if not execution_inputs:
        raise ValueError("Workspace presentation requires at least one input")
    if any(
        execution_input.request.region_id != access_readiness.region_id
        or execution_input.request.access_scope != access_readiness.access_scope
        for execution_input in execution_inputs
    ):
        raise ValueError("Workspace presentation escaped its access contract")
    execution_input_jsons = tuple(
        json.dumps(
            execution_input.as_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for execution_input in execution_inputs
    )
    bundle = _build_workspace_execution_payload(
        execution_input_jsons,
    )
    if (
        bundle.region_id != access_readiness.region_id
        or bundle.access_scope != access_readiness.access_scope
        or bundle.execution_inputs != execution_inputs
    ):
        raise ValueError("Workspace execution identity drifted")
    return bundle


@st.cache_resource(show_spinner=False, max_entries=8)
def _cached_workspace_native_area(
    native_request_json: str,
    runtime_snapshot_token: str,
) -> WorkspaceNativeAreaExecution:
    """Retain ordered native cells under their complete request and live revision."""

    _workspace_sha256(runtime_snapshot_token, "Native area runtime snapshot token")
    request = parse_workspace_analysis_request(json.loads(native_request_json))
    prepared = prepare_catalog_workspace_native_area(request, runtime_snapshot_token)
    if prepared.request != request:
        raise ValueError("Cached native area requires its exact native request")
    return prepared


def _workspace_area_result_from_native(
    request: WorkspaceAnalysisRequest,
    runtime_snapshot_token: str,
) -> WorkspaceAreaExecutionResult:
    # Current target/native authorization stays outside the reusable native cache.
    native_request = native_workspace_area_request(request)
    prepared = _cached_workspace_native_area(
        json.dumps(native_request.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        runtime_snapshot_token,
    )
    return derive_catalog_workspace_area_request(request, prepared, runtime_snapshot_token)


@st.cache_resource(show_spinner=False, max_entries=8)
def _cached_workspace_analysis_binding(
    execution_input_json: str,
    target_resolution: int,
    runtime_snapshot_token: str,
) -> WorkspaceExecutionBinding:
    """Retain one technology's immutable area/preview/presentation components.

    The complete current runtime token remains an ordinary cache key. The
    combined adapter is constructed once outside this cache; its large JSON
    is not duplicated in a per-technology plan or copied on cache hits.
    """

    _workspace_sha256(runtime_snapshot_token, "Workspace runtime snapshot token")
    execution_input = parse_workspace_analysis_execution_input(json.loads(execution_input_json))
    if execution_input.request.target_resolution != target_resolution:
        raise ValueError("Workspace cached binding escaped its target resolution")
    area_result = (
        _workspace_area_result_from_native(execution_input.request, runtime_snapshot_token)
        if execution_input.area_execution is WorkspaceAreaExecution.EXECUTE
        else None
    )
    try:
        prepared_buffers = tuple(
            _cached_workspace_group_buffer_preview(
                json.dumps(
                    reusable_catalog_workspace_buffer_request(
                        build_catalog_workspace_buffer_preview_request(
                            execution_input.request, group.group_id,
                        )
                    ).as_dict(),
                    ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                ),
                runtime_snapshot_token,
            )
            for group in execution_input.request.groups
        )
        return run_catalog_workspace_analysis_binding(
            execution_input, prepared_area_result=area_result,
            prepared_buffer_previews=prepared_buffers,
            runtime_snapshot_token=runtime_snapshot_token,
        )
    except Exception:
        _cached_workspace_group_buffer_preview.clear()
        raise


@st.cache_resource(show_spinner=False, max_entries=32)
def _cached_workspace_group_buffer_preview(
    preview_request_json: str,
    runtime_snapshot_token: str,
) -> WorkspacePreparedBufferPreview:
    """Reuse immutable group geometry under complete current input identity."""

    _workspace_sha256(runtime_snapshot_token, "Buffer runtime snapshot token")
    request = parse_workspace_buffer_preview_request(json.loads(preview_request_json))
    return prepare_catalog_workspace_buffer_preview(request, runtime_snapshot_token)


@st.cache_resource(show_spinner=False, max_entries=8)
@workspace_buffer_geometry_validation_scope()
def _cached_workspace_execution_resolution_plan(
    execution_input_jsons: tuple[str, ...],
    display_resolution: int,
    analysis_resolution: int,
    runtime_snapshot_token: str,
) -> WorkspaceExecutionResolutionPlan:
    """Run one immutable display/analysis plan per runtime snapshot.

    The complete plan graph is frozen and contains only tuples and scalar or
    string payloads, so sharing the cached object avoids copying its large
    signed renderer payload on every Streamlit rerun.
    """

    if (
        not isinstance(runtime_snapshot_token, str)
        or len(runtime_snapshot_token) != 64
        or any(
            character not in "0123456789abcdef"
            for character in runtime_snapshot_token
        )
    ):
        raise ValueError("Workspace runtime snapshot token must be SHA-256")
    if not isinstance(execution_input_jsons, tuple) or not execution_input_jsons:
        raise ValueError("Workspace resolution plan requires immutable inputs")
    execution_inputs = tuple(
        parse_workspace_analysis_execution_input(json.loads(input_json))
        for input_json in execution_input_jsons
    )
    analysis_inputs = retarget_catalog_workspace_execution_inputs(
        execution_inputs, analysis_resolution
    )
    display_inputs = (
        analysis_inputs
        if display_resolution == analysis_resolution
        else retarget_catalog_workspace_execution_inputs(execution_inputs, display_resolution)
    )
    analysis_bindings = tuple(
        _cached_workspace_analysis_binding(
            json.dumps(value.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            analysis_resolution, runtime_snapshot_token
        )
        for value in analysis_inputs
    )
    display_bindings = (
        analysis_bindings
        if display_resolution == analysis_resolution
        else tuple(
            _cached_workspace_analysis_binding(
                json.dumps(value.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                display_resolution, runtime_snapshot_token
            )
            for value in display_inputs
        )
    )
    return compose_catalog_workspace_execution_resolution_plan(
        execution_inputs,
        display_resolution=display_resolution,
        analysis_resolution=analysis_resolution,
        analysis_bindings=analysis_bindings,
        display_bindings=display_bindings,
        map_layer_profile="source_buffer",
    )


def _workspace_sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _canonical_payload_signature(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


@st.cache_resource(show_spinner=False, max_entries=8)
def _cached_workspace_source_buffer_map(
    display_execution_signature_sha256: str,
    display_adapter_signature_sha256: str,
    runtime_snapshot_token: str,
    _display_bundle: WorkspaceExecutionBundle,
) -> BoundWorkspaceSourceBufferMap:
    """Strictly bind one immutable display bundle per runtime snapshot."""

    execution_signature = _workspace_sha256(
        display_execution_signature_sha256,
        "Workspace display execution signature",
    )
    adapter_signature = _workspace_sha256(
        display_adapter_signature_sha256,
        "Workspace display adapter signature",
    )
    _workspace_sha256(
        runtime_snapshot_token,
        "Workspace runtime snapshot token",
    )
    if not isinstance(_display_bundle, WorkspaceExecutionBundle):
        raise TypeError("Workspace source/buffer map requires a display bundle")
    if (
        _display_bundle.execution_signature_sha256 != execution_signature
        or _display_bundle.app_adapter.adapter_signature_sha256
        != adapter_signature
    ):
        raise ValueError("Workspace display bundle signature drifted before bind")

    bound = bind_workspace_source_buffer_map(_display_bundle)
    if (
        bound.execution_signature_sha256 != execution_signature
        or bound.adapter_signature_sha256 != adapter_signature
        or bound.analysis_ids != _display_bundle.analysis_ids
    ):
        raise ValueError("Workspace source/buffer binding identity drifted")
    return bound


@st.cache_resource(show_spinner=False, max_entries=8, ttl=300)
def _cached_product_area_resolution_plan(
    execution_input_jsons: tuple[str, ...], display_resolution: int,
    analysis_resolution: int, runtime_snapshot_token: str,
) -> ProductAreaResolutionPlan:
    from speedlocal.product_area_plan import build_product_area_plan
    return build_product_area_plan(execution_input_jsons, display_resolution, analysis_resolution,
                                   runtime_snapshot_token, _cached_catalog_workspace_area_result)


def _product_workspace_execution_resolution_plan(
    *,
    wind_request: WorkspaceAnalysisRequest,
    solar_request: WorkspaceAnalysisRequest,
    wind_active: bool,
    solar_active: bool,
    display_resolution: int,
    analysis_resolution: int,
    runtime_snapshot_token: str,
    source_buffer_required: bool = True,
) -> WorkspaceExecutionResolutionPlan | ProductAreaResolutionPlan | None:
    """Build one typed area authority for the product or complete local review."""

    execution_inputs: list[WorkspaceAnalysisExecutionInput] = []
    expected_analysis_ids: list[str] = []
    request_region_ids: set[str] = set()
    request_access_scopes: set[str] = set()
    for expected_analysis_id, request, active in (
        ("wind", wind_request, bool(wind_active)),
        ("solar", solar_request, bool(solar_active)),
    ):
        if not isinstance(request, WorkspaceAnalysisRequest):
            raise TypeError("Product workspace request has an invalid type")
        if request.analysis_id != expected_analysis_id:
            raise ValueError(
                "Product workspace request has the wrong analysis identity"
            )
        if not (
            request.access_scope == f"product:{request.region_id}"
            or (
                request.access_scope == f"review:{request.region_id}"
                and catalog_context_runtime_declared(request.region_id)
            )
        ):
            raise ValueError(
                "Workspace request escaped its product or complete review surface"
            )
        request_region_ids.add(request.region_id)
        request_access_scopes.add(request.access_scope)
        if not active:
            continue
        expected_analysis_ids.append(expected_analysis_id)
        execution_inputs.append(
            WorkspaceAnalysisExecutionInput(
                request=request,
                execution_state=WorkspaceExecutionState.APPLIED,
                area_execution=WorkspaceAreaExecution.EXECUTE,
            )
        )
    if len(request_region_ids) != 1:
        raise ValueError("Product workspace requests have mixed regions")
    if len(request_access_scopes) != 1:
        raise ValueError("Workspace requests have mixed access scopes")
    if not execution_inputs:
        return None

    input_jsons = tuple(
        json.dumps(
            execution_input.as_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        for execution_input in execution_inputs
    )
    plan_builder = (_cached_workspace_execution_resolution_plan
                    if source_buffer_required else _cached_product_area_resolution_plan)
    plan = plan_builder(
        input_jsons,
        display_resolution,
        analysis_resolution,
        runtime_snapshot_token,
    )
    if (
        plan.analysis_ids != tuple(expected_analysis_ids)
        or plan.execution_inputs != tuple(execution_inputs)
    ):
        raise ValueError("Product workspace resolution-plan identity drifted")
    return plan


def _workspace_visual_group_ids(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple, set)):
        raise TypeError(f"{label} must be a collection of canonical group ids")
    group_ids: list[str] = []
    for value_id in value:
        if (
            not isinstance(value_id, str)
            or not value_id
            or value_id.strip() != value_id
        ):
            raise ValueError(f"{label} contains an invalid group id")
        if value_id in group_ids:
            raise ValueError(f"{label} contains a duplicate group id")
        group_ids.append(value_id)
    return tuple(group_ids)


def _solar_standard_visual_alias_ids(
    config: Mapping[str, Any],
    kind: str,
) -> tuple[str, ...]:
    if kind not in {"source", "buffer"}:
        raise ValueError("Solar workspace map visibility has an invalid kind")
    key = (
        SOLAR_VISUAL_SOURCE_GROUPS_KEY
        if kind == "source"
        else SOLAR_VISUAL_BUFFER_GROUPS_KEY
    )
    allowed = (
        *SOLAR_STANDARD_VISUAL_CANONICAL_GROUP_IDS,
        SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID,
    )
    aliases = normalize_workspace_map_group_visibility(
        config.get(key, []),
        allowed_group_ids=allowed,
        label=f"Solar {kind} visibility",
    )
    return tuple(
        alias
        for alias in aliases
        if alias != SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID
    )


def _product_workspace_map_visibility(
    plan: WorkspaceExecutionResolutionPlan | ProductAreaResolutionPlan,
    *,
    wind_request: WorkspaceAnalysisRequest,
    solar_request: WorkspaceAnalysisRequest,
    wind_visual_options: Mapping[str, Any],
    solar_config: Mapping[str, Any],
) -> tuple[WorkspaceMapAnalysisVisibility, ...]:
    """Translate product-only visual aliases into canonical request groups."""

    requests = {"wind": wind_request, "solar": solar_request}
    if any(analysis_id not in requests for analysis_id in plan.analysis_ids):
        raise ValueError("Product workspace map contains an unknown analysis")
    if tuple(
        execution_input.request for execution_input in plan.execution_inputs
    ) != tuple(requests[analysis_id] for analysis_id in plan.analysis_ids):
        raise ValueError("Product workspace map requests drifted from its plan")

    wind_selected = {
        "source": _workspace_visual_group_ids(
            wind_visual_options.get("source_group_ids", []),
            "Wind source visibility",
        ),
        "buffer": _workspace_visual_group_ids(
            wind_visual_options.get("buffer_group_ids", []),
            "Wind buffer visibility",
        ),
    }
    solar_aliases = {
        kind: _solar_standard_visual_alias_ids(solar_config, kind)
        for kind in ("source", "buffer")
    }
    solar_selected = {
        kind: tuple(
            SOLAR_STANDARD_VISUAL_CANONICAL_GROUP_IDS[alias]
            for alias in aliases
        )
        for kind, aliases in solar_aliases.items()
    }

    visibility: list[WorkspaceMapAnalysisVisibility] = []
    for analysis_id in plan.analysis_ids:
        request = requests[analysis_id]
        request_group_ids = tuple(group.group_id for group in request.groups)
        if len(request_group_ids) != len(set(request_group_ids)):
            raise ValueError("Product workspace request duplicates a group")
        selected = wind_selected if analysis_id == "wind" else solar_selected
        if analysis_id == "wind" and any(
            set(selected[kind]) - set(request_group_ids)
            for kind in ("source", "buffer")
        ):
            raise ValueError(
                "Product workspace map visibility references an inactive group"
            )
        if analysis_id == "solar":
            unknown_active_groups = set(request_group_ids) - set(
                SOLAR_STANDARD_VISUAL_CANONICAL_GROUP_IDS.values()
            )
            if unknown_active_groups:
                raise ValueError(
                    "Solar workspace request has no visual alias for active "
                    f"groups: {sorted(unknown_active_groups)}"
                )
        visibility.append(
            WorkspaceMapAnalysisVisibility(
                analysis_id=analysis_id,
                source_group_ids=tuple(
                    group_id
                    for group_id in request_group_ids
                    if group_id in set(selected["source"])
                ),
                buffer_group_ids=tuple(
                    group_id
                    for group_id in request_group_ids
                    if group_id in set(selected["buffer"])
                ),
            )
        )
    return tuple(visibility)


@workspace_buffer_geometry_validation_scope()
def _cached_requested_display_layer(
    request_json: str, group_id: str, role: str, source_id: str | None,
    runtime_snapshot_token: str,
) -> RequestedDisplayLayer:
    from speedlocal.requested_display import build_requested_display_layer
    request = parse_workspace_analysis_request(json.loads(request_json))
    # Current authorization precedes reuse; the cache key contains the complete
    # request, region/scope, contract revision and runtime identity.
    authorize_catalog_workspace_analysis_request(request)

    def build():
        prepared = None
        if role == "buffer":
            preview_request = build_catalog_workspace_buffer_preview_request(request, group_id)
            prepared = _cached_workspace_group_buffer_preview(
                json.dumps(reusable_catalog_workspace_buffer_request(preview_request).as_dict(),
                           ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                runtime_snapshot_token)
        return build_requested_display_layer(request, group_id, role, source_id,
                                             runtime_snapshot_token, prepared)
    return requested_display_cache.get_or_build(
        (request_json, group_id, role, source_id, runtime_snapshot_token), build)


def _product_workspace_source_buffer_layers(
    plan: WorkspaceExecutionResolutionPlan | ProductAreaResolutionPlan | None,
    *, wind_request: WorkspaceAnalysisRequest, solar_request: WorkspaceAnalysisRequest,
    wind_visual_options: Mapping[str, Any], solar_config: Mapping[str, Any],
    runtime_snapshot_token: str,
) -> tuple[dict[str, Any], ...]:
    from speedlocal.requested_display import decode_requested_display_layer
    if plan is None:
        return ()
    if isinstance(plan, WorkspaceExecutionResolutionPlan):
        return _complete_workspace_source_buffer_layers(
            plan, wind_request=wind_request, solar_request=solar_request,
            wind_visual_options=wind_visual_options, solar_config=solar_config,
            runtime_snapshot_token=runtime_snapshot_token)
    if not isinstance(plan, ProductAreaResolutionPlan):
        raise TypeError("Product display requires a typed area plan")
    visibility = _product_workspace_map_visibility(
        plan, wind_request=wind_request, solar_request=solar_request,
        wind_visual_options=wind_visual_options, solar_config=solar_config)
    if not any(item.source_group_ids or item.buffer_group_ids for item in visibility):
        return ()
    display_inputs = retarget_catalog_workspace_execution_inputs(
        plan.execution_inputs, plan.display_resolution)
    validate_product_area_bundle(plan.display_bundle, display_inputs, plan.display_resolution)
    visible = {item.analysis_id: item for item in visibility}
    result = []
    for execution_input in display_inputs:
        request = execution_input.request
        selection = visible[request.analysis_id]
        request_json = json.dumps(request.as_dict(), ensure_ascii=False,
                                  sort_keys=True, separators=(",", ":"))
        owners = {layer_id: group.group_id for group in request.groups
                  for layer_id in group.layer_ids}
        selected = [(owners[layer_id], "source", layer_id)
                    for layer_id in request.selected_layer_ids
                    if owners[layer_id] in selection.source_group_ids]
        selected.extend((group.group_id, "buffer", None) for group in request.groups
                        if group.group_id in selection.buffer_group_ids)
        for group_id, role, source_id in selected:
            layer = _cached_requested_display_layer(
                request_json, group_id, role, source_id, runtime_snapshot_token)
            result.append(decode_requested_display_layer(
                layer, request, group_id, role, source_id, runtime_snapshot_token))
    return tuple(result)


def _complete_workspace_source_buffer_layers(
    plan: WorkspaceExecutionResolutionPlan | None,
    *,
    wind_request: WorkspaceAnalysisRequest,
    solar_request: WorkspaceAnalysisRequest,
    wind_visual_options: Mapping[str, Any],
    solar_config: Mapping[str, Any],
    runtime_snapshot_token: str,
) -> tuple[dict[str, Any], ...]:
    """Select current typed review layers from the signed display bundle."""

    if plan is None:
        return ()
    workspace_map_visibility = _product_workspace_map_visibility(
        plan,
        wind_request=wind_request,
        solar_request=solar_request,
        wind_visual_options=wind_visual_options,
        solar_config=solar_config,
    )
    if not any(
        item.source_group_ids or item.buffer_group_ids
        for item in workspace_map_visibility
    ):
        return ()

    display_bundle = plan.display_bundle
    if (
        not isinstance(display_bundle, WorkspaceExecutionBundle)
        or display_bundle.analysis_ids != plan.analysis_ids
        or display_bundle.access_scope != plan.access_scope
        or display_bundle.region_id != plan.region_id
        or display_bundle.target_resolution != plan.display_resolution
        or not isinstance(display_bundle.app_adapter, WorkspaceAppAdapter)
        or display_bundle.app_adapter.access_scope != plan.access_scope
        or display_bundle.app_adapter.region_id != plan.region_id
        or display_bundle.app_adapter.target_resolution
        != plan.display_resolution
    ):
        raise ValueError("Workspace display bundle escaped its resolution plan")
    display_execution_inputs = display_bundle.execution_inputs
    if len(display_execution_inputs) != len(plan.execution_inputs) or any(
        display_input.execution_state != plan_input.execution_state
        or display_input.area_execution != plan_input.area_execution
        or display_input.request.schema_version
        != plan_input.request.schema_version
        or display_input.request.access_scope
        != plan_input.request.access_scope
        or display_input.request.region_id != plan_input.request.region_id
        or display_input.request.analysis_id != plan_input.request.analysis_id
        or display_input.request.source_resolution
        != plan_input.request.source_resolution
        or display_input.request.target_resolution != plan.display_resolution
        or display_input.request.contract_signature_sha256
        != plan_input.request.contract_signature_sha256
        or display_input.request.groups != plan_input.request.groups
        for display_input, plan_input in zip(
            display_execution_inputs,
            plan.execution_inputs,
        )
    ):
        raise ValueError("Workspace display bundle requests escaped its plan")
    display_execution_signature = _workspace_sha256(
        display_bundle.execution_signature_sha256,
        "Workspace display execution signature",
    )
    display_adapter_signature = _workspace_sha256(
        display_bundle.app_adapter.adapter_signature_sha256,
        "Workspace display adapter signature",
    )
    workspace_map_snapshot_token = _workspace_sha256(
        runtime_snapshot_token,
        "Workspace runtime snapshot token",
    )
    bound_source_buffer_map = _cached_workspace_source_buffer_map(
        display_execution_signature,
        display_adapter_signature,
        workspace_map_snapshot_token,
        _display_bundle=display_bundle,
    )
    if (
        bound_source_buffer_map.execution_signature_sha256
        != display_execution_signature
        or bound_source_buffer_map.adapter_signature_sha256
        != display_adapter_signature
        or bound_source_buffer_map.analysis_ids != plan.analysis_ids
    ):
        raise ValueError(
            "Cached workspace source/buffer map escaped its display plan"
        )
    selected = select_workspace_source_buffer_layers(
        bound_source_buffer_map,
        workspace_map_visibility,
    )
    if any(
        layer.get("workspace_role") not in {"source", "buffer"}
        for layer in selected
    ):
        raise ValueError("Workspace map policy emitted a non-review layer")
    return tuple(selected)


def _rebase_workspace_review_layers(
    cache: dict[str, Any],
    selected_layers: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    """Replace only typed source/buffer layers in a cached product result."""

    if not isinstance(cache, dict):
        raise TypeError("Workspace render cache must be an object")
    seen_ids: set[str] = set()
    for layer in selected_layers:
        if not isinstance(layer, dict):
            raise TypeError("Workspace review layer must be an object")
        role = str(layer.get("workspace_role") or "")
        layer_id = str(layer.get("workspace_layer_id") or "")
        if (
            role not in {"source", "buffer"}
            or f"::{role}:" not in layer_id
            or layer_id in seen_ids
        ):
            raise ValueError("Workspace review layer identity is invalid")
        seen_ids.add(layer_id)

    def rebased(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise ValueError("Workspace render cache layers must be a list")
        retained: list[dict[str, Any]] = []
        for layer in value:
            if not isinstance(layer, dict):
                raise TypeError("Cached workspace layer must be an object")
            role = layer.get("workspace_role")
            if role in {"source", "buffer"}:
                layer_id = str(layer.get("workspace_layer_id") or "")
                if f"::{role}:" not in layer_id:
                    raise ValueError(
                        "Cached workspace review layer identity is invalid"
                    )
                continue
            retained.append(layer)
        return _dedupe_layers([*selected_layers, *retained])

    updated = dict(cache)
    updated["layers"] = rebased(cache.get("layers"))
    raw_map_state = cache.get("map_state")
    if not isinstance(raw_map_state, dict):
        raise ValueError("Workspace render cache map_state must be an object")
    map_state = dict(raw_map_state)
    map_state["layers"] = rebased(raw_map_state.get("layers"))
    updated["map_state"] = map_state
    return updated


def _workspace_execution_area_frames(
    plan: WorkspaceExecutionResolutionPlan | ProductAreaResolutionPlan,
    analysis_id: str,
    *,
    output_schema: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Adapt signed display/analysis results without rerunning the engine."""

    analysis_result = plan.analysis_bundle.binding(analysis_id).area_result
    if analysis_result is None:
        raise ValueError(
            f"Workspace resolution plan omitted {analysis_id!r} area analysis"
        )
    analysis_frame = adapt_workspace_area_execution_result_frame(
        analysis_result,
        output_schema=output_schema,
    )
    if plan.reuses_analysis_bundle:
        return analysis_frame, analysis_frame

    display_result = plan.display_bundle.binding(analysis_id).area_result
    if display_result is None:
        raise ValueError(
            f"Workspace resolution plan omitted {analysis_id!r} display area"
        )
    display_frame = adapt_workspace_area_execution_result_frame(
        display_result,
        output_schema=output_schema,
    )
    return display_frame, analysis_frame


@st.cache_resource(show_spinner=False, max_entries=8)
def _cached_catalog_technology_context_result(
    region_id: str,
    access_scope: str,
    runtime_snapshot_token: str,
) -> TechnologyContextResult:
    """Execute one immutable context request per runtime snapshot."""

    _workspace_sha256(
        runtime_snapshot_token,
        "Technology-context runtime snapshot token",
    )
    request = build_catalog_technology_context_request(
        region_id,
        access_scope=access_scope,
    )
    result = run_catalog_technology_context_request(request)
    if result.request != request:
        raise ValueError("Technology-context result escaped its current request")
    return result


@st.cache_resource(show_spinner=False, max_entries=24)
def _cached_catalog_workspace_area_result(
    request_json: str,
    runtime_snapshot_token: str,
) -> WorkspaceAreaExecutionResult:
    """Execute only the area contract needed by combined rollup views."""

    _workspace_sha256(
        runtime_snapshot_token,
        "Combined area runtime snapshot token",
    )
    request = parse_workspace_analysis_request(json.loads(request_json))
    result = _workspace_area_result_from_native(request, runtime_snapshot_token)
    if result.request != request:
        raise ValueError("Combined area result escaped its current request")
    return result


def _combined_area_results_for_plan(
    plan: WorkspaceExecutionResolutionPlan | ProductAreaResolutionPlan,
    *,
    technology_order: tuple[str, ...],
    finalization_resolution: int,
    rollup_resolutions: tuple[int, ...],
    runtime_snapshot_token: str,
) -> tuple[WorkspaceAreaExecutionResult, ...]:
    """Collect the exact signed area matrix required by one combined policy."""

    if (
        len(plan.analysis_ids) != len(technology_order)
        or set(plan.analysis_ids) != set(technology_order)
    ):
        raise ValueError(
            "Combined-result execution requires every declared technology"
        )
    results: list[WorkspaceAreaExecutionResult] = []
    for resolution in (finalization_resolution, *rollup_resolutions):
        if resolution == plan.analysis_resolution:
            bundle = plan.analysis_bundle
        elif resolution == plan.display_resolution:
            bundle = plan.display_bundle
        else:
            for technology_id in technology_order:
                source_input = next(
                    item
                    for item in plan.execution_inputs
                    if item.request.analysis_id == technology_id
                )
                contract = load_delivery_analysis(
                    source_input.request.region_id,
                    technology_id,
                )
                request = retarget_workspace_analysis_request_from_contract(
                    contract,
                    source_input.request,
                    int(resolution),
                )
                request_json = json.dumps(
                    request.as_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                results.append(
                    _cached_catalog_workspace_area_result(
                        request_json,
                        runtime_snapshot_token,
                    )
                )
            continue
        for technology_id in technology_order:
            area_result = bundle.binding(technology_id).area_result
            if (
                area_result is None
                or area_result.technology != technology_id
                or area_result.target_resolution != int(resolution)
            ):
                raise ValueError(
                    "Combined-result area matrix is incomplete or mismatched"
                )
            results.append(area_result)
    return tuple(results)


@st.cache_resource(show_spinner=False, max_entries=16)
def _cached_combined_result_execution(
    policy_contract_signature_sha256: str,
    validation_execution_signature_sha256: str,
    area_result_signatures: tuple[str, ...],
    technology_context_result_signature_sha256: str,
    scenario_result_signature_sha256: str,
    rooftop_result_signature_sha256: str,
    social_acceptance_result_signature_sha256: str,
    runtime_snapshot_token: str,
    *,
    _area_results: tuple[Any, ...],
    _technology_context_result: TechnologyContextResult,
    _scenario_result: ScenarioResult,
    _rooftop_result: RooftopCapabilityResult,
    _social_acceptance_result: SocialAcceptanceResult,
    _policy_package: Any,
) -> CombinedResultExecutionBundle:
    """Cache only an exact immutable dependency chain and verify every key."""

    for value, label in (
        (policy_contract_signature_sha256, "Combined policy contract"),
        (validation_execution_signature_sha256, "Combined validation execution"),
        (
            technology_context_result_signature_sha256,
            "Combined technology-context result",
        ),
        (scenario_result_signature_sha256, "Combined scenario result"),
        (rooftop_result_signature_sha256, "Combined rooftop result"),
        (
            social_acceptance_result_signature_sha256,
            "Combined social-acceptance result",
        ),
        (runtime_snapshot_token, "Combined runtime snapshot token"),
    ):
        _workspace_sha256(value, label)
    if tuple(item.result_signature_sha256 for item in _area_results) != (
        area_result_signatures
    ):
        raise ValueError("Combined area-result cache identity drifted")
    if (
        _policy_package.contract_signature_sha256
        != policy_contract_signature_sha256
        or _technology_context_result.result_signature_sha256
        != technology_context_result_signature_sha256
        or _canonical_payload_signature(_scenario_result.as_dict())
        != scenario_result_signature_sha256
        or _canonical_payload_signature(_rooftop_result.as_dict())
        != rooftop_result_signature_sha256
        or social_acceptance_calculation_result_signature(
            _social_acceptance_result
        )
        != social_acceptance_result_signature_sha256
    ):
        raise ValueError("Combined-result cache dependencies drifted")
    bundle = run_combined_result_execution(
        area_results=_area_results,
        technology_context_result=_technology_context_result,
        scenario_result=_scenario_result,
        rooftop_result=_rooftop_result,
        social_acceptance_result=_social_acceptance_result,
        policy_package=_policy_package,
    )
    return bundle


def _workspace_combined_result_execution(
    plan: WorkspaceExecutionResolutionPlan | ProductAreaResolutionPlan,
    *,
    scenario_result: ScenarioResult,
    rooftop_selection: RooftopSelectionRequest | None,
    social_acceptance_result: SocialAcceptanceResult,
    runtime_snapshot_token: str,
) -> CombinedResultExecutionBundle:
    """Bind the product to one separately validated combined execution."""

    region_id = scenario_result.request.region_id
    policy_package, validation = (
        load_catalog_validated_combined_result_policy(region_id)
    )
    area_results = _combined_area_results_for_plan(
        plan,
        technology_order=policy_package.contract.technology_order,
        finalization_resolution=policy_package.contract.finalization_resolution,
        rollup_resolutions=policy_package.contract.rollup_resolutions,
        runtime_snapshot_token=runtime_snapshot_token,
    )
    context_result = _cached_catalog_technology_context_result(
        region_id,
        scenario_result.request.access_scope,
        runtime_snapshot_token,
    )
    rooftop_result = _workspace_rooftop_result(
        rooftop_selection,
        scenario_result=scenario_result,
        domain_resolution=policy_package.contract.finalization_resolution,
    )
    bundle = _cached_combined_result_execution(
        policy_package.contract_signature_sha256,
        validation.validated_default_execution_signature_sha256,
        tuple(item.result_signature_sha256 for item in area_results),
        context_result.result_signature_sha256,
        _canonical_payload_signature(scenario_result.as_dict()),
        _canonical_payload_signature(rooftop_result.as_dict()),
        social_acceptance_calculation_result_signature(
            social_acceptance_result
        ),
        runtime_snapshot_token,
        _area_results=area_results,
        _technology_context_result=context_result,
        _scenario_result=scenario_result,
        _rooftop_result=rooftop_result,
        _social_acceptance_result=social_acceptance_result,
        _policy_package=policy_package,
    )
    if (
        bundle.region_id != region_id
        or bundle.access_scope != scenario_result.request.access_scope
    ):
        raise ValueError("Combined-result execution escaped product access")
    return bundle


@st.cache_resource(show_spinner=False, max_entries=24)
def _cached_combined_result_compatibility_frame(
    execution_signature_sha256: str,
    resolution: int,
    social_result_signature_sha256: str,
    *,
    _bundle: CombinedResultExecutionBundle,
    _social_acceptance_result: SocialAcceptanceResult,
) -> pd.DataFrame:
    """Adapt one signed combined resolution to the existing map renderer."""

    _workspace_sha256(execution_signature_sha256, "Combined execution")
    _workspace_sha256(social_result_signature_sha256, "Combined social result")
    bundle = _bundle
    social_acceptance_result = _social_acceptance_result
    if bundle.execution_signature_sha256 != execution_signature_sha256:
        raise ValueError("Combined map adapter received another execution")
    if (
        social_acceptance_calculation_result_signature(
            social_acceptance_result
        )
        != social_result_signature_sha256
        or social_result_signature_sha256
        != bundle.social_acceptance_result_signature_sha256
    ):
        raise ValueError("Combined map adapter received another social result")
    result = bundle.combined_result
    resolution_result = result.resolution_result(int(resolution))
    social_request = social_acceptance_result.request
    rows: list[dict[str, Any]] = []
    for cell in resolution_result.cells:
        technologies = {
            item.technology_id: item for item in cell.technologies
        }
        row: dict[str, Any] = {
            "hex_id": cell.cell_id,
            "social_acceptance_value": cell.social_acceptance_value,
            "social_acceptance_weight": cell.social_potential_weight,
            "social_acceptance_data_status": cell.social_data_status,
            "social_acceptance_source_hex_count": cell.social_source_child_count,
            "social_acceptance_impact_pct": float(social_request.impact_pct),
        }
        for technology_id in ("wind", "solar"):
            value = technologies[technology_id]
            allocated_area = float(value.allocated_area_km2 or 0.0)
            inside_area = float(value.inside_potential_area_km2 or 0.0)
            outside_area = float(value.outside_potential_area_km2 or 0.0)
            row.update(
                {
                    f"{technology_id}_suitable": value.potential_area_km2
                    > FLOAT_TOLERANCE,
                    f"{technology_id}_rank": int(value.first_selected_rank or 0),
                    f"{technology_id}_potential_score": float(value.potential_pct),
                    f"{technology_id}_potential_area_km2": float(
                        value.potential_area_km2
                    ),
                    f"{technology_id}_allocated_area_km2": allocated_area,
                    f"{technology_id}_allocated_gwh": (None if value.allocated_twh is None else value.allocated_twh * 1000.0),
                    f"{technology_id}_allocated_hex_share_pct": (
                        allocated_area / max(float(value.model_area_km2), 1e-12) * 100.0
                    ),
                    f"{technology_id}_landscape_priority_score": float(
                        value.base_score or 0.0
                    ),
                    f"{technology_id}_allocation_priority_score": float(
                        value.allocation_priority_score or 0.0
                    ),
                    f"{technology_id}_allocation_priority_reason": "",
                    f"{technology_id}_social_acceptance_priority_score": float(
                        value.allocation_priority_score or 0.0
                    ),
                    f"{technology_id}_social_acceptance_allocation_priority_pct": float(
                        social_request.allocation_priority_pct
                    ),
                    f"{technology_id}_last_resort_overlap": bool(
                        value.reserved_by_other_technology or False
                    ),
                    f"{technology_id}_outside_lp": outside_area > FLOAT_TOLERANCE,
                    f"{technology_id}_conflict_area_km2": outside_area,
                    f"{technology_id}_conflict": outside_area > FLOAT_TOLERANCE,
                    f"{technology_id}_expansion_ring": 0,
                    f"{technology_id}_phase": (
                        "Utanför LP" if outside_area > FLOAT_TOLERANCE else "Inom LP"
                    ),
                    f"{technology_id}_context_status": cell.context_status,
                    f"{technology_id}_inside_area_km2": inside_area,
                }
            )
        row["establishment_class"] = _combined_establishment_class(
            bool(row["wind_suitable"]),
            bool(row["solar_suitable"]),
        )
        row["wind_outside_lp_area_km2"] = row["wind_conflict_area_km2"]
        row["solar_outside_lp_area_km2"] = row["solar_conflict_area_km2"]
        row["outside_lp_shortage"] = bool(
            row["wind_conflict"] or row["solar_conflict"]
        )
        row["outside_lp_reason"] = (
            "vind + sol"
            if row["wind_conflict"] and row["solar_conflict"]
            else "vind"
            if row["wind_conflict"]
            else "sol"
            if row["solar_conflict"]
            else ""
        )
        rows.append(row)
    frame = pd.DataFrame(rows)
    return _apply_establishment_style_columns(frame)


def _combined_result_compatibility_frame(
    bundle: CombinedResultExecutionBundle,
    resolution: int,
    social_acceptance_result: SocialAcceptanceResult,
) -> pd.DataFrame:
    return _cached_combined_result_compatibility_frame(
        bundle.execution_signature_sha256,
        int(resolution),
        social_acceptance_calculation_result_signature(
            social_acceptance_result
        ),
        _bundle=bundle,
        _social_acceptance_result=social_acceptance_result,
    )


def _combined_result_summary_stats(
    bundle: CombinedResultExecutionBundle,
    technology_id: str,
) -> dict[str, Any]:
    summary = next(
        item
        for item in bundle.combined_result.technology_summaries
        if item.technology_id == technology_id
    )
    selected_cells = [
        cell
        for cell in bundle.combined_result.resolutions[0].cells
        if next(
            value
            for value in cell.technologies
            if value.technology_id == technology_id
        ).allocated_area_km2
        not in {None, 0.0}
    ]
    return {
        "selected_area_km2": float(summary.selected_area_km2 or 0.0),
        "selected_twh": summary.selected_twh,
        "unmet_area_km2": float(summary.unmet_area_km2 or 0.0),
        "available_candidate_area_km2": float(summary.potential_area_km2),
        "selected_hex_count": len(selected_cells),
        "outside_selected_area_km2": float(
            summary.outside_potential_area_km2 or 0.0
        ),
    }


_WORKSPACE_RESULT_FIELD_LABELS = {
    "cell_id": "H3-cell",
    "min_distance_m": "Minsta avstånd (m)",
    "any_intersection": "Skärning",
    "blocked": "Avvisad",
    "acceptance": "Godkännande",
    "coverage_missing": "Saknad täckning",
    "model_area_km2": "Modellareal (km²)",
    "remaining_area_km2": "Återstående areal (km²)",
    "potential_pct": "Potential (%)",
    "cell_count": "Celler",
    "blocked_cell_count": "Avvisade celler",
    "accepted_cell_count": "Godkända celler",
    "coverage_missing_cell_count": "Celler med saknad täckning",
    "mean_acceptance": "Genomsnittligt godkännande",
    "threshold_m": "Gräns (m)",
}


def _workspace_result_label(
    region_id: str,
    analysis_id: str,
    result_id: str,
) -> str:
    """Use manifest labels while keeping the presentation schema generic."""

    if result_id.startswith("group:"):
        group_id = result_id.removeprefix("group:")
        labels = {
            control.id: control.label
            for control in analysis_group_controls(region_id, analysis_id)
        }
        return labels.get(group_id, group_id)
    if result_id == f"{analysis_id}.area":
        return "Etableringsyta"
    return result_id


def _render_workspace_app_results(adapter: WorkspaceAppAdapter) -> None:
    """Render compact summaries from the same typed payload as the map."""

    tables = workspace_app_result_table_dicts(adapter)
    metrics = workspace_app_metric_dicts(adapter)
    if not tables:
        return
    table_meta = {
        str(table["table_id"]): table
        for table in tables
    }
    area_table_ids = {
        str(table["table_id"])
        for table in tables
        if any(column["field_id"] == "potential_pct" for column in table["columns"])
    }
    rows: list[dict[str, Any]] = []
    diagnostic_rows: list[dict[str, Any]] = []
    for metric in metrics:
        table = table_meta.get(str(metric["table_id"]))
        if table is None:
            raise ValueError("Workspace metric references an unknown result table")
        table_id = str(table["table_id"])
        analysis_id = table_id.split("::", 1)[0]
        result_id = str(table["result_id"])
        unit = str(metric["unit"])
        value = float(metric["value"])
        if unit == "count":
            display_value: str = f"{int(value):,}".replace(",", ".")
        elif unit == "ratio":
            display_value = f"{100.0 * value:.1f} %".replace(".", ",")
        elif unit == "percent":
            display_value = f"{value:.1f} %".replace(".", ",")
        elif unit == "km2":
            display_value = f"{value:.2f} km²".replace(".", ",")
        elif unit == "m":
            display_value = f"{value:.0f} m".replace(".", ",")
        else:
            display_value = f"{value:g} {unit}".strip()
        target_rows = (
            diagnostic_rows
            if area_table_ids and table_id not in area_table_ids
            else rows
        )
        target_rows.append(
            {
                "Analys": analysis_id,
                "Resultat": _workspace_result_label(
                    adapter.region_id,
                    analysis_id,
                    result_id,
                ),
                "Mått": _WORKSPACE_RESULT_FIELD_LABELS.get(
                    str(metric["label"]),
                    str(metric["label"]),
                ),
                "Värde": display_value,
            }
        )
    st.subheader(_t("Tekniska resultat"))
    if area_table_ids:
        st.caption(
            _t("Etableringsytan visar hur stor del av den modellerade landytan som "
            "återstår efter valda filter. Delvis täckta celler behåller sin "
            "återstående andel; överlappande buffertar räknas en gång.")
        )
    st.dataframe(
        _display_dataframe(pd.DataFrame(rows)),
        key=(
            f"workspace__typed_results__{adapter.region_id}__"
            f"r{adapter.target_resolution}"
        ),
        hide_index=True,
        width="stretch",
    )
    if diagnostic_rows:
        with st.expander(_t("Teknisk filterdiagnostik"), expanded=False):
            st.caption(
                _t("Dessa mått klassar hela celler efter filtervillkor och avstånd. "
                "De visar inte hur mycket etableringsyta som återstår.")
            )
            st.dataframe(
                _display_dataframe(pd.DataFrame(diagnostic_rows)),
                key=(
                    f"workspace__typed_diagnostics__{adapter.region_id}__"
                    f"r{adapter.target_resolution}"
                ),
                hide_index=True,
                width="stretch",
            )
    with st.expander(_t("Resultatens celltabeller"), expanded=False):
        st.caption(
            _t("Tabellerna är signerade mot samma request och geometri som kartan. "
            "Detaljvyn visar ett begränsat utsnitt; totalsiffrorna ovan bygger på "
            "hela resultatet.")
        )
        for table in tables:
            table_id = str(table["table_id"])
            analysis_id = table_id.split("::", 1)[0]
            result_id = str(table["result_id"])
            st.markdown(
                f"**{analysis_id} · "
                f"{_workspace_result_label(adapter.region_id, analysis_id, result_id)}**"
            )
            columns = [
                str(column["field_id"])
                for column in table["columns"]
            ]
            display_rows = list(table["rows"][:200])
            frame = pd.DataFrame(display_rows).reindex(columns=columns)
            frame = frame.rename(columns=_WORKSPACE_RESULT_FIELD_LABELS)
            st.dataframe(
                _display_dataframe(frame),
                key=f"workspace__typed_table__{table_id}",
                hide_index=True,
                width="stretch",
                height=min(360, 72 + 28 * max(len(frame), 1)),
            )


def _render_workspace_analysis_surface(
    access_readiness: WorkspaceAccessReadiness,
    region: dict[str, Any] | None = None,
    *,
    landscape_result: LandscapeViewResult | None = None,
    target_resolution: int | None = None,
) -> tuple[int, WorkspaceExecutionBundle | None]:
    """Render all profile analyses through one request/map/result surface."""

    region_config = region if isinstance(region, dict) else {}
    region_label = str(
        region_config.get("display_name")
        or region_config.get("region_id")
        or "Region"
    )
    st.subheader(_t("Karta"))
    with st.container(border=True):
        try:
            region_id = str(region_config.get("region_id") or "").strip().lower()
            if region_id != access_readiness.region_id:
                raise ValueError("Workspace map and access region do not match")
            profile = load_workspace_profile(region_id)
            map_capability = access_readiness.capability("workspace.map")
            map_is_executable = map_capability.state in {
                "technically_validated",
                "regionally_accepted",
                "public",
            }
            if not map_is_executable or map_capability.interaction not in {
                "read_only",
                "interactive",
            }:
                st.info(
                    _t("Regionens kartdomän är inte tekniskt klar för den här "
                    "arbetsytan. Kartan förblir låst.")
                )
                st.caption(_t('Teknisk orsak: {p0}', p0=map_capability.detail))
                return 0, None
            analysis_inputs: list[
                tuple[
                    WorkspaceUiIdentity,
                    tuple[Mapping[str, Any], ...],
                    WorkspaceAnalysisExecutionInput,
                ]
            ] = []
            for analysis_id in profile.technologies:
                identity = _workspace_ui_identity(region_id, analysis_id)
                bundles = _workspace_access_analysis_bundles(
                    access_readiness,
                    analysis_id,
                )
                if not bundles:
                    st.session_state.pop(
                        _workspace_applied_request_key(identity),
                        None,
                    )
                    continue
                execution_input = _workspace_analysis_execution_input_for_view(
                    identity,
                    bundles,
                    access_readiness,
                )
                if target_resolution is not None:
                    contract = load_delivery_analysis(region_id, analysis_id)
                    execution_input = WorkspaceAnalysisExecutionInput(
                        request=retarget_workspace_analysis_request_from_contract(
                            contract,
                            execution_input.request,
                            int(target_resolution),
                        ),
                        execution_state=execution_input.execution_state,
                        area_execution=execution_input.area_execution,
                    )
                analysis_inputs.append((identity, bundles, execution_input))

            execution_bundle = (
                _workspace_execution_bundle(
                    tuple(
                        execution_input
                        for _identity, _bundles, execution_input in analysis_inputs
                    ),
                    access_readiness,
                )
                if analysis_inputs
                else None
            )
            adapter = (
                execution_bundle.app_adapter
                if execution_bundle is not None
                else None
            )
            map_layers = (
                list(workspace_app_map_layer_dicts(adapter))
                if adapter is not None
                else []
            )
            read_only_domain_resolution: int | None = None
            if not analysis_inputs and landscape_result is None:
                domain_layer, read_only_domain_resolution = (
                    workspace_region_domain_map_layer_dict(region_id)
                )
                domain_layer["name"] = (
                    f"{region_label} · analysdomän "
                    f"R{read_only_domain_resolution}"
                )
                domain_layer["legend_items"] = [
                    {
                        "label": "Tekniskt verifierad analysdomän",
                        "color": "#2f855a",
                    }
                ]
                domain_layer["legend_title"] = "Analysdomän"
                domain_layer["legend_note"] = str(
                    domain_layer["legend_note"]
                ).replace("Read-only geometry", "Skrivskyddad geometri").replace(
                    "H3 cells", "H3-celler"
                )
                map_layers.append(domain_layer)
            any_applied = any(
                execution_input.is_applied
                for _identity, _bundles, execution_input in analysis_inputs
            )

            if landscape_result is not None:
                map_layers.append(
                    _workspace_landscape_map_layer(landscape_result)
                )
                any_applied = True
            first_request = (
                analysis_inputs[0][2].request if analysis_inputs else None
            )
            map_resolution = (
                first_request.target_resolution
                if first_request is not None
                else (
                    landscape_result.request.target_resolution
                    if landscape_result is not None
                    else read_only_domain_resolution
                )
            )
            if map_resolution is None:
                raise ValueError("Kartans H3-upplösning kan inte fastställas")
            visible_layer_count = _render_layers(
                region_config,
                map_layers,
                0.76 if any_applied else 0.42,
                map_state_key=(
                    f"workspace:{access_readiness.access_scope}:"
                    f"profile:r{map_resolution}"
                ),
                note_title=f"{region_label} · stegvis geometrigranskning",
                note_body=(
                    "Basdomänen visas när kontraktet är giltigt. "
                    "Oskickade formulärändringar påverkar inte kartan. "
                    "Källor och tekniskt H3-resultat visas först efter "
                    "Använd ändringar."
                ),
                pan_mode_label="Panorera kartan",
                inspect_mode_label="Granska geometri",
            )
        except (
            FileNotFoundError,
            KeyError,
            OSError,
            PermissionError,
            NotImplementedError,
            TypeError,
            ValueError,
        ) as exc:
            st.info(
                _t("Den deklarerade arbetsytevyn kunde inte valideras. Ingen "
                "annan regions geometri eller standardberäkning används.")
            )
            st.caption(_t('Teknisk orsak: {p0}', p0=exc))
            return 0, None

        applied_descriptions: list[str] = []
        for identity, _bundles, execution_input in analysis_inputs:
            if not execution_input.is_applied:
                continue
            request = execution_input.request
            analysis_id = _workspace_analysis_id(identity)
            group_labels = {
                group.id: group.label
                for group in analysis_group_controls(
                    identity.region_id,
                    analysis_id,
                )
            }
            for group in request.groups:
                parameter_values = group.parameter_map()
                parameter_text = " · ".join(
                    f"{parameter_id}: {float(value):g}"
                    for parameter_id, value in parameter_values.items()
                )
                applied_descriptions.append(
                    f"{analysis_id}: "
                    f"{_t(group_labels.get(group.group_id, group.group_id))}"
                    + (f" · {parameter_text}" if parameter_text else "")
                )
            if not request.groups:
                applied_descriptions.append(_t(
                    "{p0}: inga aktiva filter (hela analysdomänen)",
                    p0=analysis_id,
                ))
        if applied_descriptions:
            st.caption(
                _t("Steg 3 av 3: {p0} har tillämpats. Resultatet är tekniskt och inte regional lämplighet.",
                   p0="; ".join(applied_descriptions))
            )
        else:
            st.caption(
                _t('Steg 1 av 3: kartan visar den neutrala R{p0}-domänen. Steg 2 är att fylla i formuläret; kartan ändras först när Använd ändringar skickar en manifestbunden request.', p0=map_resolution)
            )

        # Evidence status intentionally follows the map so it never displaces
        # the program's primary workspace surface.
        config = (
            access_readiness.review.access
            if access_readiness.review is not None
            else None
        )
        with st.expander(
            _t(":material/warning: Granskningsstatus"),
            expanded=False,
        ):
            if config is not None:
                trust = _review_access_presentation(config)
                st.badge(
                    _t(trust["label"]),
                    color=trust["color"],
                    icon=trust["icon"],
                )
                st.caption(_t(trust["note"]))
                st.caption(f"{_t(config.warning_title)} {_t(config.warning_body)}")
                st.caption(_t(config.allowed_use))
                st.caption(_t(config.forbidden_use))
            st.caption(
                _t("Källor och resultat kommer från samma manifestbundna "
                "request-, motor- och kartkedja som programytan i övrigt.")
            )

        if adapter is not None:
            _render_workspace_app_results(adapter)
        return visible_layer_count, execution_bundle


def _render_local_review_sidebar(region: dict[str, Any]) -> None:
    config = _local_review_config(region)
    if config is None:
        raise ValueError("The active review route has no access contract")
    _render_region_switcher(region, show_region_caption=False)


def _h3_option_label(region: dict[str, Any], resolution: int) -> str:
    counts = region.get("h3_display_geometry_counts") or {}
    count_value = counts.get(str(resolution)) if isinstance(counts, dict) else None
    if count_value is not None:
        try:
            count_int = int(count_value)
            return f"R{resolution} ({count_int} landceller)"
        except Exception:
            return f"R{resolution} ({count_value} landceller)"
    return f"R{resolution}"


def _opacity_key(key_prefix: str) -> str:
    return f"{key_prefix}_vector_opacity"


def _current_opacity(key_prefix: str) -> float:
    try:
        opacity = float(st.session_state.get(_opacity_key(key_prefix), 0.78))
    except Exception:
        opacity = 0.78
    return max(0.1, min(0.9, opacity))


def _hex_opacity_key(key_prefix: str, opacity_key: str) -> str:
    safe_key = "".join(ch if ch.isalnum() else "_" for ch in str(opacity_key))
    return f"{key_prefix}_hex_opacity_{safe_key}"


def _hex_opacity_value(key_prefix: str, opacity_key: str, default: float = 0.78) -> float:
    if opacity_key == SCENARIO_ALLOCATION_LAYER_LABEL:
        return 1.0
    try:
        opacity = float(st.session_state.get(_hex_opacity_key(key_prefix, opacity_key), default))
    except Exception:
        opacity = default
    return max(0.1, min(0.9, opacity))


def _render_opacity_control(key_prefix: str) -> None:
    st.session_state[_opacity_key(key_prefix)] = _current_opacity(key_prefix)
    control_left, control_center, control_right = st.columns([0.22, 0.56, 0.22], gap="small")
    with control_center:
        st.slider(
            _t("Opacitet polygoner och linjer"),
            min_value=0.1,
            max_value=0.9,
            step=0.05,
            key=_opacity_key(key_prefix),
            help=_t("0.1 är nästan genomskinligt. 0.9 är nästan helt fyllt."),
            on_change=_request_ui_only_rerun,
            args=("opacitet",),
            persist_state="session",
        )


def _hex_opacity_controls(layers: list[dict[str, Any]], key_prefix: str) -> list[dict[str, Any]]:
    families: dict[str, dict[str, Any]] = {}
    for layer in layers:
        if str(layer.get("layer_kind", "")) != "hex":
            continue
        if layer.get("default_visible") is False:
            continue
        family_key = str(layer.get("opacity_family") or layer.get("control_name") or layer.get("name"))
        if family_key == SCENARIO_ALLOCATION_LAYER_LABEL:
            continue
        if family_key in families:
            continue
        families[family_key] = {
            "key": family_key,
            "label": str(layer.get("opacity_label") or layer.get("control_name") or layer.get("name")),
            "default": float(layer.get("fill_opacity", 0.78) or 0.78),
        }

    if not families:
        return []

    st.caption(_t("Opacitet hexlager"))
    for family in families.values():
        control_key = _hex_opacity_key(key_prefix, family["key"])
        st.session_state[control_key] = _hex_opacity_value(key_prefix, family["key"], family["default"])
        st.slider(
            _t(family["label"]),
            min_value=0.1,
            max_value=0.9,
            step=0.05,
            key=control_key,
            help=_t('Styr opaciteten för hexlagret {p0}. 0.1 är nästan genomskinligt, 0.9 nästan helt fyllt.', p0=family['label']),
            on_change=_request_ui_only_rerun,
            args=("hexopacitet",),
            persist_state="session",
        )
    return list(families.values())


def _apply_layer_opacity_state(layers: list[dict[str, Any]], key_prefix: str) -> list[dict[str, Any]]:
    adjusted_layers: list[dict[str, Any]] = []
    for layer in layers:
        spec = dict(layer)
        if str(spec.get("layer_kind", "")) == "hex":
            family_key = str(spec.get("opacity_family") or spec.get("control_name") or spec.get("name"))
            spec["fill_opacity"] = _hex_opacity_value(key_prefix, family_key, float(spec.get("fill_opacity", 0.78) or 0.78))
            if str(spec.get("fill_opacity_property", "")) == "fill_opacity":
                spec.pop("fill_opacity_property", None)
        adjusted_layers.append(spec)
    return adjusted_layers


def _layer_control_rows(layers: list[dict[str, Any]], key_prefix: str) -> list[dict[str, Any]]:
    rows_by_control: dict[str, dict[str, Any]] = {}
    for layer in layers:
        control_name = str(layer.get("control_name") or layer.get("name") or "Lager")
        kind = str(layer.get("layer_kind") or "lager")
        resolution = layer.get("auto_resolution")
        row = rows_by_control.setdefault(
            control_name,
            {
                "lager": control_name,
                "typ": "Hex" if kind == "hex" else "Polygon/linje" if kind == "vector" else kind.title(),
                "visning": "",
                "opacitet": "",
            },
        )
        if kind == "hex":
            family_key = str(layer.get("opacity_family") or control_name)
            row["opacitet"] = f"{_hex_opacity_value(key_prefix, family_key, float(layer.get('fill_opacity', 0.78) or 0.78)):.2f}"
        elif not row["opacitet"]:
            row["opacitet"] = f"{_current_opacity(key_prefix):.2f}"
        if resolution is not None:
            values = str(row["visning"]).split(", ") if row["visning"] else []
            label = f"R{int(resolution)}"
            if label not in values:
                values.append(label)
            row["visning"] = ", ".join(values)
        elif not row["visning"]:
            row["visning"] = "Direkt"
    return list(rows_by_control.values())


def _count_enabled(*values: bool) -> int:
    return sum(1 for value in values if bool(value))


def _perf_start() -> float:
    return time.perf_counter()


def _add_perf_timing(performance_log: list[dict[str, Any]], step: str, started_at: float, detail: str = "") -> None:
    performance_log.append(
        {
            "steg": step,
            "tid_s": round(max(0.0, time.perf_counter() - float(started_at)), 3),
            "detalj": detail,
        }
    )


def _calculation_progress_steps(
    show_user_solar: bool,
    show_solar_v1: bool,
    show_user_wind: bool,
    energy_model_state: dict[str, Any],
) -> list[str]:
    steps: list[str] = []
    if show_user_solar:
        steps.append("Sol storskalig")
    if show_solar_v1:
        steps.append("Sol småskalig")
    if show_user_solar or show_solar_v1:
        steps.append("Sol samlad etablering")
    if show_user_wind:
        steps.append("Vindpotential och vindetablering")
    if energy_model_state.get("available"):
        steps.append("Gemensam etableringsyta")
        steps.append("Etableringsstatistik")
    steps.append("Karta HTML och rendering")
    return steps


def _median_seconds(values: list[float]) -> float | None:
    clean = sorted(float(value) for value in values if float(value) > 0)
    if not clean:
        return None
    midpoint = len(clean) // 2
    if len(clean) % 2:
        return float(clean[midpoint])
    return float((clean[midpoint - 1] + clean[midpoint]) / 2.0)


def _performance_history_bucket(region: dict[str, Any], h3_resolution: int, zoom_family_enabled: bool) -> str:
    mode = "zoom" if bool(zoom_family_enabled) else "fast"
    return f"{region.get('region_id', 'region')}:R{int(h3_resolution)}:{mode}"


def _performance_step_estimates(bucket: str, steps: list[str]) -> dict[str, float]:
    history = st.session_state.get(PERFORMANCE_HISTORY_KEY)
    if not isinstance(history, dict):
        return {}
    estimates: dict[str, float] = {}
    global_history = history.get("global") if isinstance(history.get("global"), dict) else {}
    bucket_history = history.get(bucket) if isinstance(history.get(bucket), dict) else {}
    for step in steps:
        specific_values = bucket_history.get(step) if isinstance(bucket_history, dict) else None
        global_values = global_history.get(step) if isinstance(global_history, dict) else None
        median = _median_seconds([float(value) for value in specific_values]) if isinstance(specific_values, list) else None
        if median is None and isinstance(global_values, list):
            median = _median_seconds([float(value) for value in global_values])
        if median is not None:
            estimates[step] = median
    return estimates


def _record_performance_history(bucket: str, performance_log: list[dict[str, Any]]) -> None:
    if not performance_log:
        return
    history = st.session_state.get(PERFORMANCE_HISTORY_KEY)
    if not isinstance(history, dict):
        history = {}
    for scope in ("global", bucket):
        scope_history = history.setdefault(scope, {})
        if not isinstance(scope_history, dict):
            scope_history = {}
            history[scope] = scope_history
        for row in performance_log:
            step = str(row.get("steg", ""))
            if not step:
                continue
            try:
                seconds = float(row.get("tid_s", 0.0) or 0.0)
            except Exception:
                continue
            if seconds <= 0:
                continue
            values = scope_history.setdefault(step, [])
            if not isinstance(values, list):
                values = []
                scope_history[step] = values
            values.append(round(seconds, 3))
            del values[:-12]
    st.session_state[PERFORMANCE_HISTORY_KEY] = history


def _loading_phase(message_id: str, **kwargs: Any) -> None:
    feedback = current_loading()
    if feedback is not None:
        feedback.phase(message_id, **kwargs)


def _start_calculation_progress(steps: list[str]) -> dict[str, Any] | None:
    if not steps:
        return None
    _loading_phase("loading.map", completed=0, total=len(steps))
    return {
        "steps": list(steps),
        "completed": set(),
    }


def _advance_calculation_progress(progress: dict[str, Any] | None, step: str) -> None:
    if not progress:
        return
    steps = list(progress.get("steps") or [])
    if step not in steps:
        return
    completed = progress.setdefault("completed", set())
    completed.add(step)
    done = sum(1 for item in steps if item in completed)
    total = max(1, len(steps))
    _loading_phase("loading.map", completed=done, total=total)


def _performance_diagnostic_rows(performance_log: list[dict[str, Any]], estimates: dict[str, float]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in performance_log:
        step = str(row.get("steg", ""))
        actual = float(row.get("tid_s", 0.0) or 0.0)
        expected = estimates.get(step)
        rows.append(
            {
                "steg": step,
                "tid_s": round(actual, 3),
                "historisk_median_s": round(float(expected), 3) if expected is not None else None,
                "avvikelse_s": round(actual - float(expected), 3) if expected is not None else None,
                "detalj": str(row.get("detalj", "")),
            }
        )
    return sorted(rows, key=lambda item: float(item.get("tid_s", 0.0) or 0.0), reverse=True)


def _short_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()[:10]


def _feature_count(feature_collection: dict[str, Any] | None) -> int:
    if not isinstance(feature_collection, dict):
        return 0
    features = feature_collection.get("features")
    return len(features) if isinstance(features, list) else 0


def _map_layer_debug_rows(layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for layer in layers:
        rows.append(
            {
                "lager": str(layer.get("control_name") or layer.get("name") or "Lager"),
                "namn": str(layer.get("name") or "-"),
                "typ": str(layer.get("layer_kind") or "-"),
                "features": _feature_count(layer.get("feature_collection")),
                "default": "på" if layer.get("default_visible", True) is not False else "av",
                "z": int(layer.get("z_index", 0) or 0),
            }
        )
    return rows


def _preview_labels(labels: list[str], limit: int = 3) -> str:
    clean = [str(label) for label in labels if str(label)]
    if not clean:
        return ""
    suffix = "..." if len(clean) > int(limit) else ""
    return ", ".join(clean[: int(limit)]) + suffix


def _wind_group_display_label(groups: dict[str, Any], group_id: str) -> str:
    if str(group_id) in {
        WIND_POPULATION_GROUP_ID,
        WIND_NATURE_GROUP_ID,
        WIND_ROADS_GROUP_ID,
    }:
        group = _wind_control_group(_wind_region_id(), group_id)
        return str(group.label) if group is not None else str(group_id)
    group = groups.get(str(group_id))
    if group is None:
        return GROUP_LABELS.get(str(group_id), str(group_id))
    if isinstance(group, WindGroupControlContract):
        return str(group.label)
    return group_label(group, WIND_CONTROL_LANGUAGE, group.label)


def _geography_filter_notes(
    *,
    show_user_wind: bool,
    wind_selected_layers: dict[str, list[str]],
    wind_ui_params: dict[str, Any],
    wind_unfiltered_land: bool,
    show_user_solar: bool,
    show_solar_v1: bool,
    solar_large_population_active: bool,
    solar_large_population_layer_ids: list[str],
    solar_large_unfiltered_land_active: bool,
    solar_params: dict[str, Any],
    solar_large_filter_configs: list[dict[str, Any]],
    solar_v1_area_m2_per_person: float | None,
) -> list[str]:
    notes: list[str] = []
    region_id = _wind_region_id()
    selected_wind = normalize_group_layer_map(
        wind_selected_layers or {},
        region_id,
    )
    if show_user_wind:
        if wind_unfiltered_land or not any(selected_wind.values()):
            notes.append(_t("Vind: inga avgränsande lager är valda, så vindpotentialen används som ett öppet startläge."))
        else:
            controls = _wind_control_groups(region_id)
            if all(isinstance(group, WindGroupControlContract) for group in controls):
                groups = {str(group.id): group for group in controls}
                layers = {str(layer.id): layer for group in controls for layer in group.layers}
            else:
                groups, layers, _ = load_acceptance_registry()
            for group in _wind_control_groups(region_id):
                group_id = str(group.id)
                layer_ids = [str(layer_id) for layer_id in selected_wind.get(group_id, [])]
                if not layer_ids:
                    continue
                threshold_key = _wind_group_param_key(group_id)
                threshold_m = (
                    float(wind_ui_params.get(threshold_key, group.analysis_default_m))
                    if threshold_key
                    else float(group.analysis_default_m)
                )
                selected_labels = (
                    [
                        _t(layer.label)
                        for layer in _wind_control_layers(region_id, group)
                        if layer.id in layer_ids
                    ]
                    if isinstance(group, WindGroupControlContract)
                    else [
                        layer_label(
                            layers[layer_id],
                            _wind_control_language(),
                            layers[layer_id].label,
                        )
                        for layer_id in layer_ids
                        if layer_id in layers
                    ]
                )
                layer_text = _preview_labels(selected_labels)
                effect_text = _t("maxavstånd" if str(group.analysis_kind) == "proximity_feasibility" else "buffert/avstånd")
                source_text = f" ({layer_text})" if layer_text else ""
                notes.append(
                    _t("Vind: {p0} använder {p1} källager med {p2:.0f} m {p3}{p4}.",
                       p0=_t(_wind_group_display_label(groups, group_id)), p1=len(layer_ids),
                       p2=threshold_m, p3=effect_text, p4=source_text)
                )

    if show_user_solar:
        has_solar_filters = bool(solar_large_population_active or solar_large_filter_configs)
        if solar_large_population_active:
            population_labels = [
                _t(layer.label)
                for layer in _solar_large_population_contract(region_id).layers
                if layer.id in set(solar_large_population_layer_ids)
            ]
            population_source_text = _preview_labels(population_labels)
            notes.append(
                _t("Sol: Befolkning använder {p0} källager med {p1:.0f} m buffert/avstånd{p2}.",
                   p0=len(solar_large_population_layer_ids),
                   p1=float(solar_params.get('population_buffer_m', 250.0) or 250.0),
                   p2=f" ({population_source_text})" if population_source_text else "")
            )
        for filter_config in solar_large_filter_configs:
            group_id = str(filter_config.get("group_id", ""))
            spec = SOLAR_FILTER_GROUP_SPECS.get(group_id, {})
            label = _t(_solar_filter_display_label(group_id))
            layer_ids = list(filter_config.get("layer_ids") or [])
            layer_labels = [_t(label) for label in _solar_filter_layer_labels(group_id, layer_ids)]
            layer_text = _preview_labels(layer_labels)
            source_text = f" ({layer_text})" if layer_text else ""
            distance_m = float(filter_config.get("buffer_m", 0.0) or 0.0)
            if str(filter_config.get("effect", spec.get("effect", "exclusion"))) == "feasibility":
                notes.append(_t("Sol: {p0} kräver närhet inom {p1:.0f} m från {p2} källager{p3}.", p0=label, p1=distance_m, p2=len(layer_ids), p3=source_text))
            else:
                notes.append(_t("Sol: {p0} drar av yta med {p1:.0f} m buffert från {p2} källager{p3}.", p0=label, p1=distance_m, p2=len(layer_ids), p3=source_text))
        if not has_solar_filters and solar_large_unfiltered_land_active:
            notes.append(_t("Sol: storskalig sol använder landskapsunderlaget utan aktiva avdragsfilter."))

    if show_solar_v1:
        notes.append(
            _t("Sol: småskalig takschablon använder {p0:.0f} m² panelyta per person.", p0=float(solar_v1_area_m2_per_person or 0.0))
        )

    return notes


def _geography_effect_notes(energy_model_state: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    solar_filter_impact = energy_model_state.get("solar_filter_impact") if isinstance(energy_model_state, dict) else None
    if isinstance(solar_filter_impact, dict) and int(solar_filter_impact.get("active_filter_count", 0) or 0) > 0:
        removed_area = float(solar_filter_impact.get("removed_area_km2", 0.0) or 0.0)
        removed_share = float(solar_filter_impact.get("removed_share_pct", 0.0) or 0.0)
        if removed_area > 1e-6:
            notes.append(
                f"Solfiltereffekt: {_format_area_primary(removed_area, 'km²')} tas bort från den storskaliga solbasen ({removed_share:.1f}%)."
            )
        else:
            notes.append("Solfilter är aktiva men tar inte bort någon mätbar yta med nuvarande inställningar.")
    return notes


def _establishment_color_summary_text(stats: dict[str, Any] | None) -> str:
    if not isinstance(stats, dict):
        return ""
    values = {
        "gröna": int(stats.get("wind_and_solar_hex_count", 0) or 0),
        "blå": int(stats.get("wind_only_hex_count", 0) or 0),
        "gula": int(stats.get("solar_only_hex_count", 0) or 0),
        "röda": int(stats.get("red_hex_count", 0) or 0),
    }
    total = int(stats.get("total_hex_count", 0) or 0)
    if total <= 0:
        total = sum(values.values())
    if total <= 0:
        return ""
    parts = [
        f"{_count_text(count)} {_t(label)} ({count / max(total, 1) * 100.0:.1f}%)"
        for label, count in values.items()
    ]
    black_count = int(stats.get("black_hex_count", 0) or 0)
    suffix = _t(" Svarta schematiska fält: {p0}.", p0=_count_text(black_count)) if black_count > 0 else ""
    return _t("Färgfördelning i kartan: {p0} av {p1} hexagoner.{p2}", p0=', '.join(parts), p1=_count_text(total), p2=suffix)


def _render_geography_user_summary(map_state: dict[str, Any]) -> None:
    st.caption(
        _t("Kartan visar hur aktiva geografiska antaganden formar möjlig etableringsyta och hur scenariot placeras i landskapet.")
    )
    filter_notes = [str(note) for note in (map_state.get("geography_filter_notes") or []) if str(note)]
    if filter_notes:
        st.markdown("\n".join(f"- {_t(note)}" for note in filter_notes))
    else:
        st.caption(_t("Inga aktiva geografiska filter kunde sammanfattas för den senaste kartkörningen."))
    color_text = _establishment_color_summary_text(map_state.get("establishment_hex_stats"))
    if color_text:
        st.caption(_t(color_text))
    for note in [str(value) for value in (map_state.get("geography_effect_notes") or []) if str(value)]:
        st.caption(_t(note))


def _protected_group_label() -> str:
    return PROTECTED_NATURE_LABEL


def _apply_wind_layer_selection_state(
    layer_selection: dict[str, list[str]],
    region_id: str | None = None,
) -> dict[str, list[str]]:
    region_id = _wind_region_id(region_id)
    selected = normalize_group_layer_map(layer_selection, region_id)
    st.session_state[WIND_LAYER_SELECTION_KEY] = selected
    for group in _wind_control_groups(region_id):
        for layer in _wind_control_layers(region_id, group):
            st.session_state[_wind_control_key("layer", layer.id)] = bool(
                layer.id in selected.get(group.id, [])
            )
    for group_id in selected:
        group_enabled = bool(selected.get(group_id))
        st.session_state[_wind_control_key("group", group_id)] = group_enabled
        st.session_state[
            _wind_control_key("group_sync", group_id)
        ] = group_enabled
    return selected


def _reset_wind_filter_state(region_id: str | None = None) -> None:
    """Clear wind widgets before Streamlit instantiates them on the rerun."""
    normalized_region_id = _wind_region_id(region_id)
    _apply_wind_layer_selection_state({}, normalized_region_id)
    for group in _wind_control_groups(normalized_region_id):
        st.session_state[_wind_control_key("analysis", group.id)] = int(
            group.analysis_default_m
        )
    for group_id in public_wind_group_ids(normalized_region_id):
        st.session_state[_wind_control_key("visual_source", group_id)] = False
        st.session_state[_wind_control_key("visual_buffer", group_id)] = False
    st.session_state.pop(WORKSPACE_FILTER_APPLIED_STATE_KEY, None)
    st.session_state[WIND_EMPTY_SELECTION_ACTIVE_KEY] = True
    _invalidate_workspace_cache("wind filters reset")


def _region_start_default_key(region: dict[str, Any]) -> str:
    region_id = str(region.get("region_id", "region") or "region")
    return f"{START_DEFAULT_VERSION_KEY}_{region_id}"


def _solar_rooftop_panel_area_parameter(
    region_id: str | None = None,
) -> Any:
    selected_region_id = str(
        region_id
        or st.session_state.get(REGION_SELECT_KEY)
        or DEFAULT_REGION_ID
    )
    return load_catalog_rooftop_contract(
        selected_region_id
    ).rooftop.panel_area_m2_per_person


def _solar_rooftop_panel_area_default(
    region_id: str | None = None,
) -> float:
    return float(
        _solar_rooftop_panel_area_parameter(region_id).default
    )


def _ensure_default_start_state(region: dict[str, Any], force: bool = False) -> None:
    start_default_key = _region_start_default_key(region)
    if not force and st.session_state.get(start_default_key) == START_DEFAULT_VERSION:
        return
    selected_wind = _apply_wind_layer_selection_state(
        _default_wind_layer_selection()
    )
    for group_id in public_wind_group_ids(_wind_region_id()):
        st.session_state[_wind_control_key("visual_source", str(group_id))] = False
        st.session_state[_wind_control_key("visual_buffer", str(group_id))] = False
    st.session_state[WIND_EMPTY_SELECTION_ACTIVE_KEY] = not any(
        selected_wind.values()
    )
    region_id = str(region.get("region_id", "region") or "region")
    default_solar_config = _default_solar_presentation_projection(region_id)
    st.session_state["show_user_solar"] = bool(default_solar_config.get("large_scale_active", True))
    for group_id in _solar_visual_group_order():
        st.session_state[
            _solar_visual_control_key("source", group_id, region_id)
        ] = False
        st.session_state[
            _solar_visual_control_key("buffer", group_id, region_id)
        ] = False
    st.session_state[start_default_key] = START_DEFAULT_VERSION


def _solar_filter_spec(group_id: str) -> dict[str, Any]:
    return SOLAR_FILTER_GROUP_SPECS[str(group_id)]


@_presentation_input('_solar_manifest_group_contract')
@st.cache_data(show_spinner=False, max_entries=16)
def _solar_manifest_group_contract(
    region_id: str,
    visual_group_id: str,
    canonical_group_id: str,
) -> WindGroupControlContract:
    return analysis_group_control_contract(
        str(region_id),
        "solar",
        str(canonical_group_id),
        public_group_id=str(visual_group_id),
    )


def _solar_large_population_contract(
    region_id: str | None = None,
) -> WindGroupControlContract:
    return _solar_manifest_group_contract(
        str(region_id or _wind_region_id()),
        SOLAR_LARGE_POPULATION_VISUAL_GROUP_ID,
        CANONICAL_POPULATION_GROUP_ID,
    )


def _solar_filter_distance_contract(
    group_id: str,
    region_id: str | None = None,
) -> tuple[float, float, float, float]:
    """Return min, max, step, and default from the canonical authority."""

    spec = _solar_filter_spec(group_id)
    canonical_group_id = SOLAR_AREA_CANONICAL_GROUP_IDS.get(str(group_id))
    if canonical_group_id is not None:
        contract = _solar_manifest_group_contract(
            str(region_id or _wind_region_id()),
            str(group_id),
            canonical_group_id,
        )
        return (
            float(contract.analysis_min_m),
            float(contract.analysis_max_m),
            float(contract.analysis_step_m),
            float(contract.analysis_default_m),
        )
    return (
        float(spec.get("buffer_min_m", 0.0)),
        float(spec.get("buffer_max_m", 1000.0)),
        float(spec.get("buffer_step_m", 50.0)),
        float(spec.get("buffer_default_m", 0.0)),
    )


def _solar_population_distance_contract(
    region_id: str | None = None,
) -> tuple[float, float, float, float]:
    contract = _solar_large_population_contract(region_id)
    return (
        float(contract.analysis_min_m),
        float(contract.analysis_max_m),
        float(contract.analysis_step_m),
        float(contract.analysis_default_m),
    )


def _solar_distance_value(
    value: Any,
    contract: tuple[float, float, float, float],
) -> float:
    """Keep persisted values inside a manifest-declared slider interval."""

    minimum, maximum, step, default = contract
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        candidate = default
    candidate = min(max(candidate, minimum), maximum)
    if step > 0:
        step_count = math.floor(((candidate - minimum) / step) + 0.5)
        candidate = minimum + (step_count * step)
    return min(max(candidate, minimum), maximum)


def _default_solar_presentation_projection(
    region_id: str | None = None,
) -> dict[str, Any]:
    """Build fresh/reset defaults from manifests for all shared groups."""

    config = dict(DEFAULT_SOLAR_PRESENTATION_PROJECTION)
    config["population_buffer_m"] = _solar_population_distance_contract(
        region_id
    )[3]
    for group_id in SOLAR_AREA_CANONICAL_GROUP_IDS:
        spec = _solar_filter_spec(group_id)
        config[str(spec["buffer_key"])] = _solar_filter_distance_contract(
            group_id,
            region_id,
        )[3]
    return config


def _solar_large_population_layer_ids(
    region_id: str | None = None,
) -> tuple[str, ...]:
    return tuple(
        layer.id
        for layer in _solar_large_population_contract(region_id).layers
    )


def _solar_large_population_default_layer_ids(
    region_id: str | None = None,
) -> tuple[str, ...]:
    return tuple(
        layer.id
        for layer in _solar_large_population_contract(region_id).layers
        if layer.ready
    )


def _solar_large_population_layer_control_key(layer_id: str) -> str:
    return f"solar_draft_large_population_layer__{layer_id}"


def _solar_available_large_population_layer_ids(
    layer_ids: list[str] | tuple[str, ...] | set[str] | None = None,
    region_id: str | None = None,
) -> tuple[str, ...]:
    requested = (
        set(_solar_large_population_layer_ids(region_id))
        if layer_ids is None
        else {str(layer_id) for layer_id in layer_ids}
    )
    return tuple(
        layer.id
        for layer in _solar_large_population_contract(region_id).layers
        if layer.ready and layer.id in requested
    )


def _solar_control_selected_large_population_layer_ids(
    config: dict[str, Any],
    region_id: str | None = None,
) -> list[str]:
    if (
        "large_population_active" in config
        and not bool(config.get("large_population_active", False))
    ):
        return []
    raw_ids = config.get(SOLAR_LARGE_POPULATION_LAYER_IDS_KEY)
    if isinstance(raw_ids, (list, tuple, set)):
        requested = [str(layer_id) for layer_id in raw_ids]
    elif bool(config.get("large_population_active", False)):
        requested = list(
            _solar_large_population_default_layer_ids(region_id)
        )
    else:
        requested = []
    return list(
        _solar_available_large_population_layer_ids(
            requested,
            region_id,
        )
    )


def _solar_filter_display_label(
    group_id: str,
    region_id: str | None = None,
) -> str:
    canonical_group_id = SOLAR_AREA_CANONICAL_GROUP_IDS.get(str(group_id))
    if canonical_group_id is not None:
        return str(
            _solar_manifest_group_contract(
                str(region_id or _wind_region_id()),
                str(group_id),
                canonical_group_id,
            ).label
        )
    return str(_solar_filter_spec(group_id)["label"])


@_presentation_input('_solar_rooftop_map_review_config')
@st.cache_data(show_spinner=False, max_entries=16)
def _solar_rooftop_map_review_config(
    region_id: str,
) -> tuple[str, tuple[str, ...], float]:
    """Resolve rooftop review source and buffer from validated manifests."""

    review = load_catalog_rooftop_contract(str(region_id)).rooftop.map_review
    group_contract = _solar_manifest_group_contract(
        str(region_id),
        SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID,
        review.canonical_group_id,
    )
    ready_ids = {layer.id for layer in group_contract.layers if layer.ready}
    requested_ids = tuple(review.layer_ids)
    if not requested_ids or not set(requested_ids).issubset(ready_ids):
        raise ValueError(
            "Rooftop-solar map-review layers are not ready in the solar "
            "analysis manifest"
        )
    return (
        review.canonical_group_id,
        requested_ids,
        float(group_contract.analysis_default_m),
    )


def _solar_filter_layer_ids(group_id: str) -> tuple[str, ...]:
    canonical_group_id = SOLAR_AREA_CANONICAL_GROUP_IDS.get(str(group_id))
    if canonical_group_id is not None:
        contract = _solar_manifest_group_contract(
            _wind_region_id(),
            str(group_id),
            canonical_group_id,
        )
        return tuple(layer.id for layer in contract.layers)
    return tuple(str(layer_id) for layer_id in (_solar_filter_spec(group_id).get("layer_ids") or ()))


def _solar_default_filter_layer_ids(group_id: str) -> tuple[str, ...]:
    spec = _solar_filter_spec(group_id)
    requested = spec.get("default_layer_ids")
    if requested is None:
        requested = _solar_filter_layer_ids(group_id)
    allowed = set(_solar_filter_layer_ids(group_id))
    return tuple(str(layer_id) for layer_id in (requested or ()) if str(layer_id) in allowed)


def _solar_filter_layer_control_key(group_id: str, layer_id: str) -> str:
    if str(group_id) == SOLAR_PROTECTED_GROUP_ID:
        return _solar_protected_layer_control_key(str(layer_id))
    return f"solar_draft_{group_id}_layer__{layer_id}"


def _solar_visual_control_key(
    kind: str,
    group_id: str,
    region_id: str | None = None,
) -> str:
    """Keep rooftop previews inside the same region/access capability scope."""

    if str(group_id) == SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID:
        identity = _workspace_ui_identity(
            str(region_id or _wind_region_id()),
            ROOFTOP_CAPABILITY_ID,
        )
        return workspace_state_key(identity, "visual", str(kind))
    return f"solar_draft_visual_{kind}__{group_id}"


def _solar_visual_config_key(kind: str) -> str:
    return SOLAR_VISUAL_SOURCE_GROUPS_KEY if str(kind) == "source" else SOLAR_VISUAL_BUFFER_GROUPS_KEY


def _solar_visual_group_order() -> tuple[str, ...]:
    return (
        SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID,
        SOLAR_LARGE_POPULATION_VISUAL_GROUP_ID,
        *SOLAR_FILTER_GROUP_IDS,
    )


def _solar_visible_group_ids(config: dict[str, Any], kind: str) -> list[str]:
    raw = config.get(_solar_visual_config_key(kind), [])
    if isinstance(raw, dict):
        requested = {str(group_id) for group_id, enabled in raw.items() if bool(enabled)}
    elif isinstance(raw, (list, tuple, set)):
        requested = {str(group_id) for group_id in raw}
    else:
        requested = set()
    return [group_id for group_id in _solar_visual_group_order() if group_id in requested]


def _solar_visual_enabled(config: dict[str, Any], kind: str, group_id: str) -> bool:
    return str(group_id) in set(_solar_visible_group_ids(config, kind))


def _solar_visible_group_ids_from_session(
    kind: str,
    region_id: str | None = None,
) -> list[str]:
    return [
        group_id
        for group_id in _solar_visual_group_order()
        if bool(
            st.session_state.get(
                _solar_visual_control_key(kind, group_id, region_id),
                False,
            )
        )
    ]


def _preserve_solar_map_review_widget_state(
    region_id: str | None = None,
) -> None:
    """Keep map-only widget values across an early form-triggered rerun.

    Solar and rooftop Apply deliberately restart the script before the map
    review controls below the forms are rendered. Re-saving an existing
    widget value detaches it from Streamlit's omitted-widget cleanup for that
    interrupted run. The next complete render still clears any group that is
    no longer active in ``_render_solar_map_review_controls``.
    """

    for group_id in _solar_visual_group_order():
        for kind in ("source", "buffer"):
            key = _solar_visual_control_key(kind, group_id, region_id)
            if key in st.session_state:
                st.session_state[key] = bool(st.session_state[key])


def _solar_control_selected_filter_layer_ids(config: dict[str, Any], group_id: str) -> list[str]:
    spec = _solar_filter_spec(group_id)
    active_key = str(spec["active_key"])
    if active_key in config and not bool(config.get(active_key, False)):
        return []
    raw_ids = config.get(str(spec["layer_ids_key"]))
    if isinstance(raw_ids, (list, tuple, set)):
        requested = [str(layer_id) for layer_id in raw_ids]
    elif bool(config.get(str(spec["active_key"]), False)):
        requested = list(_solar_default_filter_layer_ids(group_id))
    else:
        requested = []
    return list(_solar_available_filter_layer_ids(group_id, requested))


def _solar_control_selected_protected_layer_ids(config: dict[str, Any]) -> list[str]:
    return _solar_control_selected_filter_layer_ids(config, SOLAR_PROTECTED_GROUP_ID)


def _solar_filter_layer_labels(
    group_id: str,
    layer_ids: list[str] | tuple[str, ...],
) -> list[str]:
    canonical_group_id = SOLAR_AREA_CANONICAL_GROUP_IDS.get(str(group_id))
    if canonical_group_id is not None:
        controls = {
            layer.id: layer
            for layer in _solar_manifest_group_contract(
                _wind_region_id(),
                str(group_id),
                canonical_group_id,
            ).layers
        }
        return [
            str(controls[str(layer_id)].label)
            if str(layer_id) in controls
            else str(layer_id)
            for layer_id in layer_ids
        ]
    _, layers, _ = load_acceptance_registry()
    labels: list[str] = []
    for layer_id in layer_ids:
        layer_spec = layers.get(str(layer_id))
        if layer_spec is None:
            labels.append(str(layer_id))
            continue
        labels.append(layer_label(layer_spec, WIND_CONTROL_LANGUAGE, layer_spec.label))
    return labels


def _solar_active_filter_configs(config: dict[str, Any]) -> list[dict[str, Any]]:
    active: list[dict[str, Any]] = []
    for group_id in SOLAR_FILTER_GROUP_IDS:
        spec = _solar_filter_spec(group_id)
        layer_ids = _solar_control_selected_filter_layer_ids(config, group_id)
        if not layer_ids:
            continue
        active.append(
            {
                "group_id": group_id,
                "layer_ids": layer_ids,
                "layer_labels": _solar_filter_layer_labels(
                    group_id,
                    layer_ids,
                ),
                "buffer_m": _solar_distance_value(
                    config.get(str(spec["buffer_key"])),
                    _solar_filter_distance_contract(group_id),
                ),
                "label": _solar_filter_display_label(group_id),
                "effect": str(spec.get("effect", "exclusion")),
            }
        )
    return active


def _solar_exact_area_request(
    population_layer_ids: list[str] | tuple[str, ...],
    population_buffer_m: float,
    filter_configs: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> tuple[
    tuple[tuple[str, tuple[str, ...]], ...],
    tuple[tuple[str, float], ...],
]:
    """Translate public solar controls to canonical shared constraints."""

    selected: dict[str, tuple[str, ...]] = {}
    buffers: dict[str, float] = {}
    selected_population_layer_ids = tuple(
        dict.fromkeys(
            str(layer_id)
            for layer_id in population_layer_ids
        )
    )
    if selected_population_layer_ids:
        selected[CANONICAL_POPULATION_GROUP_ID] = selected_population_layer_ids
        buffers[CANONICAL_POPULATION_GROUP_ID] = float(
            population_buffer_m
        )
    for config in filter_configs:
        public_group_id = str(config.get("group_id") or "")
        canonical_group_id = SOLAR_AREA_CANONICAL_GROUP_IDS.get(
            public_group_id
        )
        if canonical_group_id is None:
            raise ValueError(
                "Exact solar area does not support active legacy group "
                f"{public_group_id!r}"
            )
        layer_ids = tuple(
            dict.fromkeys(
                str(layer_id)
                for layer_id in (config.get("layer_ids") or ())
            )
        )
        if not layer_ids:
            continue
        selected[canonical_group_id] = layer_ids
        buffers[canonical_group_id] = float(
            config.get("buffer_m", 0.0) or 0.0
        )
    order = (
        CANONICAL_ROADS_GROUP_ID,
        CANONICAL_POPULATION_GROUP_ID,
        CANONICAL_NATURE_GROUP_ID,
        CANONICAL_CULTURE_GROUP_ID,
        CANONICAL_GRID_GROUP_ID,
    )
    selected_groups = tuple(
        (group_id, selected[group_id])
        for group_id in order
        if group_id in selected
    )
    group_buffers = tuple(
        (group_id, buffers[group_id])
        for group_id in order
        if group_id in selected
    )
    return selected_groups, group_buffers


def _solar_large_scale_is_active(
    base_active: bool,
    population_active: bool,
    protected_layer_ids: list[str] | tuple[str, ...],
) -> bool:
    _ = base_active
    _ = population_active
    _ = protected_layer_ids
    return True


def _solar_protected_layer_control_key(layer_id: str) -> str:
    return f"solar_draft_protected_layer__{layer_id}"


def _solar_default_filter_config_values(config: dict[str, Any] | None = None) -> dict[str, Any]:
    source = config if isinstance(config, dict) else {}
    values: dict[str, Any] = {}
    for group_id, spec in SOLAR_FILTER_GROUP_SPECS.items():
        layer_ids = _solar_control_selected_filter_layer_ids(source, group_id) if source else []
        active = bool(source.get(str(spec["active_key"]), bool(layer_ids)))
        if not active:
            layer_ids = []
        values[str(spec["layer_ids_key"])] = layer_ids
        values[str(spec["active_key"])] = bool(active and layer_ids)
        values[str(spec["buffer_key"])] = _solar_distance_value(
            source.get(str(spec["buffer_key"])),
            _solar_filter_distance_contract(group_id),
        )
    return values


def _solar_config_from_workspace_request(
    request: WorkspaceAnalysisRequest,
    rooftop_selection: RooftopSelectionRequest | None = None,
) -> dict[str, Any]:
    """Project the common solar request into untouched presentation code.

    The returned mapping is never persisted and cannot select a layer or
    distance that is absent from the applied request.  It is a temporary
    adapter for the remaining rooftop/scenario presentation, not a second
    analysis authority.
    """

    contract = load_delivery_analysis(request.region_id, "solar")
    validate_workspace_analysis_request_from_contract(contract, request)
    authorize_catalog_workspace_analysis_request(request)
    if request.analysis_id != "solar":
        raise ValueError("Solar presentation requires a solar request")

    if rooftop_selection is not None:
        rooftop_contract = load_catalog_rooftop_contract(request.region_id)
        validate_rooftop_selection_from_contract(
            rooftop_contract,
            rooftop_selection,
        )
        if (
            rooftop_selection.region_id != request.region_id
            or rooftop_selection.access_scope != request.access_scope
        ):
            raise ValueError(
                "Rooftop selection does not match the solar workspace request"
            )
    config = _default_solar_presentation_projection(request.region_id)
    if rooftop_selection is not None:
        config["panel_area_m2_per_person"] = float(
            rooftop_selection.panel_area_m2_per_person
        )
    elif (
        catalog_context_runtime_declared(request.region_id)
        and (
            contract.distributed_generation is None
            or contract.distributed_generation.rooftop_solar is None
        )
    ):
        # Missing rooftop input is not a zero population or panel parameter.
        config.pop("panel_area_m2_per_person", None)
    else:
        config["panel_area_m2_per_person"] = float(
            _solar_rooftop_panel_area_default(request.region_id)
        )
    config.update(
        {
            "small_population_active": bool(
                rooftop_selection is not None and rooftop_selection.enabled
            ),
            SOLAR_VISUAL_SOURCE_GROUPS_KEY: list(
                _solar_visible_group_ids_from_session(
                    "source",
                    request.region_id,
                )
            ),
            SOLAR_VISUAL_BUFFER_GROUPS_KEY: list(
                _solar_visible_group_ids_from_session(
                    "buffer",
                    request.region_id,
                )
            ),
            "large_scale_active": True,
            "large_unfiltered_land_active": not bool(request.groups),
        }
    )

    groups = {group.group_id: group for group in request.groups}

    def group_value(group_id: str) -> float:
        group = groups[group_id]
        values = group.parameter_map()
        if len(values) != 1:
            raise ValueError(
                f"Solar group {group_id} must have one explicit parameter"
            )
        return float(next(iter(values.values())))

    population = groups.get(CANONICAL_POPULATION_GROUP_ID)
    if population is not None:
        population_layers = list(population.layer_ids)
        config[SOLAR_LARGE_POPULATION_LAYER_IDS_KEY] = population_layers
        config["large_population_active"] = bool(population_layers)
        config["population_buffer_m"] = group_value(
            CANONICAL_POPULATION_GROUP_ID
        )

    public_group_by_canonical = {
        canonical_id: public_id
        for public_id, canonical_id in SOLAR_AREA_CANONICAL_GROUP_IDS.items()
    }
    for canonical_id, public_id in public_group_by_canonical.items():
        group = groups.get(canonical_id)
        if group is None:
            continue
        spec = _solar_filter_spec(public_id)
        layer_ids = list(group.layer_ids)
        config[str(spec["layer_ids_key"])] = layer_ids
        config[str(spec["active_key"])] = bool(layer_ids)
        config[str(spec["buffer_key"])] = group_value(canonical_id)

    config["large_protected_layer_ids"] = list(
        config.get("large_protected_layer_ids", [])
    )
    config["large_protected_active"] = bool(
        config["large_protected_layer_ids"]
    )
    return config


def _filter_group_sync_key(group_key: str) -> str:
    return f"{group_key}__source_sync"


def _filter_source_display_label(source: FilterSourceControl) -> str:
    return str(source.label).split(" :orange", 1)[0]


def _filter_source_help(source: FilterSourceControl) -> str:
    detail = _t(str(source.help_text or "").strip())
    source_text = _t("Datakälla: {p0}.", p0=_filter_source_display_label(source))
    return f"{source_text} {detail}" if detail else source_text


def _filter_group_default_sources(
    control: FilterGroupControl,
    default_source_ids: tuple[str, ...],
) -> tuple[FilterSourceControl, ...]:
    """Resolve defaults from the active UI binding, not the imported class."""

    default_ids = {str(source_id) for source_id in default_source_ids}
    if not default_ids:
        return tuple(control.sources[:1])
    return tuple(
        source for source in control.sources if source.id in default_ids
    )


def _filter_group_default_caption(
    control: FilterGroupControl,
    default_source_ids: tuple[str, ...],
    *,
    auto_select_sources: bool = True,
) -> str | None:
    if not auto_select_sources:
        return _t(
            "Ingen datakälla väljs automatiskt. Öppna Datakällor och välj "
            "minst en datakälla tillsammans med gruppen innan du använder "
            "ändringarna."
        )
    labels = [
        _filter_source_display_label(source)
        for source in _filter_group_default_sources(
            control,
            default_source_ids,
        )
        if source.ready
    ]
    if not labels:
        return _t(
            "Ingen ordinarie datakälla är tillgänglig. "
            "Här kan du granska de källor som är kopplade till gruppen."
        )
    return None


def _sync_filter_group_controls_on_apply(
    bindings: tuple[tuple[Any, ...], ...],
    feedback_key: str | None = None,
) -> None:
    """Resolve simple group choices and detailed source edits on form submit."""

    # A prior interrupted presentation must never turn Apply into snapshot replay.
    _clear_ui_only_rerun()
    groups_missing_explicit_sources: list[str] = []
    for binding in bindings:
        if len(binding) not in {4, 5}:
            raise ValueError("Filter binding must contain four or five values")
        control, group_key, sync_key, default_source_ids = binding[:4]
        auto_select_sources = (
            bool(binding[4]) if len(binding) == 5 else True
        )
        group_enabled = bool(st.session_state.get(group_key, False))
        prior_group_enabled = bool(
            st.session_state.get(sync_key, group_enabled)
        )
        ready_sources = tuple(
            source for source in control.sources if source.ready
        )
        selected_sources = [
            source
            for source in ready_sources
            if bool(st.session_state.get(source.key, False))
        ]

        if group_enabled and not selected_sources and not auto_select_sources:
            groups_missing_explicit_sources.append(str(control.label))

        if group_enabled != prior_group_enabled:
            if group_enabled and not selected_sources and auto_select_sources:
                selected_sources = [
                    source
                    for source in _filter_group_default_sources(
                        control,
                        default_source_ids,
                    )
                    if source.ready
                ]
                if not selected_sources and ready_sources:
                    selected_sources = [ready_sources[0]]
            elif not group_enabled:
                selected_sources = []

        selected_ids = {source.id for source in selected_sources}
        for source in control.sources:
            st.session_state[source.key] = bool(
                source.ready and source.id in selected_ids
            )
        st.session_state[group_key] = bool(selected_ids)
        st.session_state[sync_key] = bool(selected_ids)

    if feedback_key:
        if groups_missing_explicit_sources:
            st.session_state[feedback_key] = tuple(
                groups_missing_explicit_sources
            )
        else:
            st.session_state.pop(feedback_key, None)


def _render_native_filter_group_control(
    control: FilterGroupControl,
    *,
    group_key: str,
    sync_key: str,
    default_source_ids: tuple[str, ...],
    auto_select_sources: bool = True,
) -> list[str]:
    """Render one native, one-click filter group with optional source detail."""

    selected_before_render = [
        source.id
        for source in control.sources
        if source.ready and bool(st.session_state.get(source.key, False))
    ]
    st.session_state.setdefault(group_key, bool(selected_before_render))
    st.session_state.setdefault(
        sync_key,
        bool(st.session_state.get(group_key, False)),
    )

    ready = any(source.ready for source in control.sources)
    if control.id != "roads":
        st.caption(_t(control.interpretation))
    st.checkbox(
        _t('Använd {p0}', p0=control.label.lower()),
        key=group_key,
        disabled=not ready,
        help=(
            (
                _t('Aktiverar {p0} med gruppens ordinarie datakälla eller datakällor. Öppna Datakällor om du vill granska eller ändra urvalet.', p0=control.label.lower())
            )
            if auto_select_sources
            else (
                _t('Aktiverar {p0} först när minst en datakälla också är vald. Öppna Datakällor och välj källa innan du använder ändringarna.', p0=control.label.lower())
            )
        ),
        persist_state="session",
    )
    st.slider(
        _t(control.analysis_label),
        min_value=control.analysis_min_m,
        max_value=control.analysis_max_m,
        step=control.analysis_step_m,
        key=control.analysis_key,
        format=WHOLE_METRE_SLIDER_FORMAT,
        help=_t(control.analysis_help),
        disabled=not ready,
        persist_state="session",
    )
    with st.expander(_t("Datakällor"), expanded=False, key=f"{group_key}:sources_panel"):
        notice = _filter_group_default_caption(
            control, default_source_ids, auto_select_sources=auto_select_sources,
        )
        if notice:
            st.caption(notice)
        for source in control.sources:
            st.checkbox(
                _t(source.label),
                key=source.key,
                disabled=not source.ready,
                help=_filter_source_help(source),
                persist_state="session",
            )
        if not control.sources:
            st.caption(
                _t('Inga källager är kopplade till {p0}.', p0=control.label.lower())
            )
    return [
        source.id
        for source in control.sources
        if source.ready and bool(st.session_state.get(source.key, False))
    ]


def _solar_filter_group_control(group_id: str) -> FilterGroupControl:
    spec = _solar_filter_spec(group_id)
    canonical_group_id = SOLAR_AREA_CANONICAL_GROUP_IDS.get(str(group_id))
    group_contract = (
        _solar_manifest_group_contract(
            _wind_region_id(),
            str(group_id),
            canonical_group_id,
        )
        if canonical_group_id is not None
        else None
    )
    label = _solar_filter_display_label(group_id)
    interpretation = str(
        group_contract.interpretation
        if group_contract is not None
        else spec.get("caption")
        or f"Valda källager används i {SOLAR_LARGE_SCALE_LABEL}."
    )
    analysis_label = str(
        group_contract.analysis_label
        if group_contract is not None
        else spec.get("slider_label")
        or f"Buffert {label.lower()}"
    )
    analysis_min_m, analysis_max_m, analysis_step_m, _ = (
        _solar_filter_distance_contract(group_id)
    )
    return filter_group_control(
        group_id=str(group_id),
        label=label,
        interpretation=interpretation,
        analysis_label=analysis_label,
        analysis_min_m=analysis_min_m,
        analysis_max_m=analysis_max_m,
        analysis_step_m=analysis_step_m,
        analysis_key=str(spec["draft_buffer_key"]),
        analysis_help=str(
            spec.get("slider_help")
            or "0 m tar bort själva källgeometrin. Högre värden lägger till buffert."
        ),
        sources=(
            FilterSourceControl(
                id=str(option["id"]),
                label=str(option["label"]),
                key=_solar_filter_layer_control_key(group_id, str(option["id"])),
                ready=bool(option["ready"]),
                help_text=str(option.get("message", "") or ""),
            )
            for option in _solar_filter_layer_options(group_id)
        ),
    )


def _solar_large_population_filter_control() -> FilterGroupControl:
    group_contract = _solar_large_population_contract()
    sources: list[FilterSourceControl] = []
    for layer in group_contract.layers:
        source_label = str(layer.label)
        if layer.quality_flag == "caution":
            source_label = (
                f"{source_label} :orange[:material/warning:]"
            )
        sources.append(
            FilterSourceControl(
                id=str(layer.id),
                label=source_label,
                key=_solar_large_population_layer_control_key(
                    str(layer.id)
                ),
                ready=bool(layer.ready),
                help_text=str(layer.message or layer.note),
            )
        )
    return filter_group_control(
        group_id=SOLAR_LARGE_POPULATION_VISUAL_GROUP_ID,
        label="Befolkning",
        interpretation=(
            "För nära befolkning är olämpligt för storskalig sol. "
            "Valda grid-, polygon- och punktkällor kombineras till en "
            "gemensam avståndsrestriktion."
        ),
        analysis_label=str(group_contract.analysis_label),
        analysis_min_m=float(group_contract.analysis_min_m),
        analysis_max_m=float(group_contract.analysis_max_m),
        analysis_step_m=float(group_contract.analysis_step_m),
        analysis_key="solar_draft_population_buffer_m",
        analysis_help=(
            "Totalt avstånd från valda befolknings- och "
            "bebyggelseunderlag."
        ),
        sources=sources,
    )


def _render_solar_large_population_filter_control(
) -> tuple[FilterGroupControl, str, str, tuple[str, ...]]:
    control = _solar_large_population_filter_control()
    group_key = "solar_draft_large_population_active"
    sync_key = _filter_group_sync_key(group_key)
    default_source_ids = _solar_large_population_default_layer_ids()
    with st.expander(control.label, expanded=False):
        selected_layer_ids = _render_native_filter_group_control(
            control,
            group_key=group_key,
            sync_key=sync_key,
            default_source_ids=default_source_ids,
        )
        if not selected_layer_ids:
            st.caption(ui_text("group_inactive", WIND_CONTROL_LANGUAGE))
    return control, group_key, sync_key, default_source_ids


def _render_solar_filter_control(
    group_id: str,
) -> tuple[FilterGroupControl, str, str, tuple[str, ...]]:
    spec = _solar_filter_spec(group_id)
    control = _solar_filter_group_control(group_id)
    group_key = str(spec["draft_active_key"])
    sync_key = _filter_group_sync_key(group_key)
    default_source_ids = _solar_default_filter_layer_ids(group_id)
    with st.expander(control.label, expanded=False):
        selected_layer_ids = _render_native_filter_group_control(
            control,
            group_key=group_key,
            sync_key=sync_key,
            default_source_ids=default_source_ids,
        )
        if not selected_layer_ids:
            st.caption(ui_text("group_inactive", WIND_CONTROL_LANGUAGE))
    return control, group_key, sync_key, default_source_ids


def _render_solar_map_review_controls(
    region: dict[str, Any],
    config: dict[str, Any],
) -> None:
    """Render map-only solar controls for the currently applied filters."""
    region_id = str(region.get("region_id") or "")
    active_groups: list[dict[str, Any]] = []
    if bool(config.get("small_population_active", False)):
        try:
            (
                rooftop_review_group_id,
                rooftop_review_layer_ids,
                _,
            ) = _solar_rooftop_map_review_config(region_id)
            rooftop_review_error = ""
        except (KeyError, OSError, ValueError) as exc:
            rooftop_review_group_id = None
            rooftop_review_layer_ids = ()
            rooftop_review_error = str(exc)
        active_groups.append(
            {
                "visual_group_id": SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID,
                "canonical_group_id": rooftop_review_group_id,
                "label": str(SOLAR_SMALL_SCALE_LABEL),
                "layer_ids": list(rooftop_review_layer_ids),
                "preview_error": rooftop_review_error,
            }
        )
    if bool(config.get("large_population_active", False)):
        active_groups.append(
            {
                "visual_group_id": SOLAR_LARGE_POPULATION_VISUAL_GROUP_ID,
                "canonical_group_id": CANONICAL_POPULATION_GROUP_ID,
                "label": "Befolkning",
                "layer_ids": _solar_control_selected_large_population_layer_ids(
                    config,
                    region_id,
                ),
            }
        )
    for filter_config in _solar_active_filter_configs(config):
        group_id = str(filter_config.get("group_id", ""))
        active_groups.append(
            {
                "visual_group_id": group_id,
                "canonical_group_id": SOLAR_AREA_CANONICAL_GROUP_IDS.get(
                    group_id
                ),
                "label": str(
                    filter_config.get("label")
                    or _solar_filter_display_label(group_id, region_id)
                ),
                "layer_ids": [
                    str(value)
                    for value in filter_config.get("layer_ids", [])
                ],
            }
        )

    active_group_ids = {
        str(item["visual_group_id"]) for item in active_groups
    }
    for group_id in _solar_visual_group_order():
        if group_id not in active_group_ids:
            st.session_state[
                _solar_visual_control_key("source", group_id, region_id)
            ] = False
            st.session_state[
                _solar_visual_control_key("buffer", group_id, region_id)
            ] = False

    if active_groups:
        expanded = any(
            bool(
                st.session_state.get(
                    _solar_visual_control_key(kind, group_id, region_id),
                    False,
                )
            )
            for group_id in active_group_ids
            for kind in ("source", "buffer")
        )
        with st.expander(_t("Kartgranskning"), expanded=expanded, key=f"workspace_{region_id}:solar_map_review_panel"):
            st.caption(
                _t("Dessa val ändrar bara kartan. De påverkar inte analysen "
                "eller resultattabellen.")
            )
            for item in active_groups:
                group_id = str(item["visual_group_id"])
                canonical_group_id = item.get("canonical_group_id")
                label = str(item["label"])
                layer_ids = [str(value) for value in item.get("layer_ids", [])]
                preview_error = str(item.get("preview_error", "") or "")
                preview_supported = False
                if canonical_group_id is not None and not preview_error:
                    try:
                        manifest_group = _solar_manifest_group_contract(
                            region_id,
                            group_id,
                            str(canonical_group_id),
                        )
                        ready_layer_ids = {
                            layer.id
                            for layer in manifest_group.layers
                            if layer.ready
                        }
                        preview_supported = (
                            bool(layer_ids)
                            and set(layer_ids).issubset(ready_layer_ids)
                            and _vector_preview_supported(
                                region_id,
                                layer_ids,
                                "solar",
                                str(canonical_group_id),
                            )
                        )
                    except (KeyError, OSError, ValueError):
                        preview_supported = False
                st.markdown(f"**{label}**")
                if not preview_supported:
                    st.session_state[
                        _solar_visual_control_key("source", group_id, region_id)
                    ] = False
                    st.session_state[
                        _solar_visual_control_key("buffer", group_id, region_id)
                    ] = False
                review_change_callback = (
                    _invalidate_workspace_cache
                    if group_id == SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID
                    else _request_ui_only_rerun
                )
                st.toggle(
                    _t("Visa källa i kartan"),
                    key=_solar_visual_control_key(
                        "source", group_id, region_id
                    ),
                    disabled=not preview_supported,
                    on_change=review_change_callback,
                    args=("solar source preview changed",),
                    help=(
                        _t("Källan läses från solanalysens manifest.")
                        if preview_supported
                        else preview_error
                        or _t("Källvisning saknar ett komplett "
                              "manifestdeklarerat vektorkontrakt.")
                    ),
                    persist_state="session",
                )
                st.toggle(
                    _t("Visa buffert i kartan"),
                    key=_solar_visual_control_key(
                        "buffer", group_id, region_id
                    ),
                    disabled=not preview_supported,
                    on_change=review_change_callback,
                    args=("solar buffer preview changed",),
                    help=(
                        _t("Bufferten byggs från solmanifestets tillämpade "
                        "källor och analysavstånd.")
                        if preview_supported
                        else preview_error
                        or _t("Buffertvisning saknar ett komplett "
                              "manifestdeklarerat vektorkontrakt.")
                    ),
                    persist_state="session",
                )

    config[SOLAR_VISUAL_SOURCE_GROUPS_KEY] = [
        group_id
        for group_id in _solar_visual_group_order()
        if group_id in active_group_ids
        and bool(
            st.session_state.get(
                _solar_visual_control_key("source", group_id, region_id),
                False,
            )
        )
    ]
    config[SOLAR_VISUAL_BUFFER_GROUPS_KEY] = [
        group_id
        for group_id in _solar_visual_group_order()
        if group_id in active_group_ids
        and bool(
            st.session_state.get(
                _solar_visual_control_key("buffer", group_id, region_id),
                False,
            )
        )
    ]
    # ``config`` is a non-persisted projection of the applied workspace
    # request. Preview toggles already persist under their own widget keys;
    # writing the projection here would recreate a second analysis authority.


def _has_selected_wind_layers(layer_selection: dict[str, list[str]] | None = None) -> bool:
    selected = normalize_group_layer_map(_selected_wind_layers() if layer_selection is None else layer_selection)
    return any(len(layer_ids) > 0 for layer_ids in selected.values())


def _wind_empty_selection_is_active(layer_selection: dict[str, list[str]] | None = None) -> bool:
    return bool(st.session_state.get(WIND_EMPTY_SELECTION_ACTIVE_KEY, False)) and not _has_selected_wind_layers(layer_selection)


def _wind_potential_is_active(layer_selection: dict[str, list[str]] | None = None) -> bool:
    return _has_selected_wind_layers(layer_selection) or _wind_empty_selection_is_active(layer_selection)


def _zoom_adapted_map_panel_state(
    region: dict[str, Any],
    key_prefix: str,
) -> tuple[int, bool, float, bool, int]:
    """Return the product's one zoom-adapted map policy without UI state."""

    return (
        int(_zoom_family_base_resolution(region)),
        True,
        _current_opacity(key_prefix),
        True,
        _map_view_reset_token(),
    )


def _filter_frame_to_display_geometries(frame: pd.DataFrame, display_geometry_path: str | None) -> pd.DataFrame:
    if not display_geometry_path or "hex_id" not in frame.columns:
        return frame
    visible_hex_ids = _h3_display_hex_ids(display_geometry_path)
    return frame[frame["hex_id"].astype(str).isin(visible_hex_ids)].copy()


def _display_family_resolutions(region: dict[str, Any], preferred_resolution: int) -> list[int]:
    preferred = int(preferred_resolution)
    available = [value for value in _available_h3_resolutions(region) if int(value) <= preferred]
    return available or [preferred]


def _zoom_family_base_resolution(region: dict[str, Any]) -> int:
    available = _available_h3_resolutions(region)
    try:
        default_resolution = int(region.get("default_display_h3_resolution") or region.get("default_h3_resolution") or max(available))
    except Exception:
        default_resolution = max(available)
    return _preferred_h3_resolution(region, default_resolution)


def _zoom_family_resolutions(region: dict[str, Any]) -> list[int]:
    return _display_family_resolutions(region, _zoom_family_base_resolution(region))


def _hex_display_rule(region: dict[str, Any], selected_resolution: int, zoom_family_enabled: bool) -> dict[str, str]:
    selected = _zoom_family_base_resolution(region) if bool(zoom_family_enabled) else int(selected_resolution)
    family_resolutions = _zoom_family_resolutions(region) if bool(zoom_family_enabled) else _display_family_resolutions(region, selected)
    min_resolution = min(int(value) for value in family_resolutions) if family_resolutions else selected
    if not bool(zoom_family_enabled):
        return {
            "selected_label": f"R{selected}",
            "display_label": f"R{selected}",
            "mode_label": "Snabb",
            "item_note": f"Snabb hexvisning i R{selected}.",
        }
    if min_resolution == selected:
        return {
            "selected_label": f"R{selected}",
            "display_label": f"R{selected}",
            "mode_label": "Fast",
            "item_note": f"Hexvisning i R{selected}.",
        }
    return {
        "selected_label": f"R{selected}",
        "display_label": f"R{selected} till R{min_resolution}",
        "mode_label": "Zoomanpassad",
        "item_note": f"Hexvisning zoomanpassas från R{selected} till R{min_resolution}.",
    }


def _hex_family_layers(
    region: dict[str, Any],
    selected_resolution: int,
    zoom_family_enabled: bool,
    family_key: str,
    control_name: str,
    build_layer: Any,
    family_resolutions: list[int] | None = None,
) -> list[dict[str, Any]]:
    layers: list[dict[str, Any]] = []
    selected_for_map = _zoom_family_base_resolution(region) if bool(zoom_family_enabled) else int(selected_resolution)
    resolutions = (
        [int(value) for value in family_resolutions]
        if family_resolutions is not None
        else (
            _zoom_family_resolutions(region)
            if bool(zoom_family_enabled)
            else [int(selected_resolution)]
        )
    )
    for resolution in resolutions:
        layer = build_layer(int(resolution))
        if layer is None:
            continue
        layer["name"] = f"{control_name} R{int(resolution)}"
        layer["control_name"] = control_name
        layer["auto_resolution_group"] = str(family_key)
        layer["auto_resolution"] = int(resolution)
        layer["selected_resolution"] = int(selected_for_map)
        layer["lock_selected_resolution"] = not bool(zoom_family_enabled)
        layers.append(layer)
    return layers


def _class_breaks(solar_rules: dict[str, Any]) -> list[dict[str, Any]]:
    return list((solar_rules.get("score_model") or {}).get("class_breaks") or [])


def _solar_rollup_entry(potential_manifest: dict[str, Any], resolution: int) -> dict[str, Any] | None:
    for entry in potential_manifest.get("h3_rollups") or []:
        if entry.get("technology") == "solar" and int(entry.get("h3_resolution", -1)) == int(resolution):
            return entry
    return None


def _default_solar_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    potential_manifest: dict[str, Any],
    solar_rules: dict[str, Any],
    resolution: int,
) -> pd.DataFrame:
    display_rules = _solar_rules_with_display_palette(solar_rules)
    source_resolution = landscape_source_resolution(landscape_manifest)
    entry = _solar_rollup_entry(potential_manifest, resolution)
    if entry is not None and int(entry.get("source_resolution", -1)) == source_resolution:
        frame = rollup_frame_for_entry(entry)
        class_colors = {
            str(item.get("id")): str(item.get("color", "#999999"))
            for item in _class_breaks(display_rules)
        }
        if "solar_class" in frame.columns:
            frame = frame.copy()
            frame["solar_color"] = frame["solar_class"].astype(str).map(class_colors).fillna(frame.get("solar_color", "#999999"))
    else:
        frame = rollup_potential_frame(
            solar_capacity_frame(landscape_manifest, display_rules),
            resolution,
            _class_breaks(display_rules),
            "solar",
            source_resolution=source_resolution,
        )
    return _filter_frame_to_display_geometries(frame, _h3_display_geometry_path(region, resolution))


def _solar_v1_class(area_m2: float) -> dict[str, str]:
    value = max(0.0, float(area_m2 or 0.0))
    if value <= 0:
        return {"id": "none", "label": "0 m2", "color": "#991b1b"}
    if value <= 25:
        return {"id": "very_low", "label": ">0-25 m2", "color": "#f87171"}
    if value <= 100:
        return {"id": "low", "label": "25-100 m2", "color": "#fef08a"}
    if value <= 250:
        return {"id": "medium", "label": "100-250 m2", "color": "#fde047"}
    if value <= 1000:
        return {"id": "high", "label": "250-1 000 m2", "color": "#facc15"}
    return {"id": "very_high", "label": ">1 000 m2", "color": "#ca8a04"}


def _solar_v1_legend_items() -> list[dict[str, str]]:
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for value in [10, 50, 150, 500, 1500]:
        item = _solar_v1_class(float(value))
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        items.append({"label": item["label"], "color": item["color"]})
    return items


@st.cache_data(show_spinner=False)
def _canonical_rooftop_population_count_frame(
    region_id: str,
    access_scope: str,
    target_resolution: int,
) -> pd.DataFrame:
    contract = load_catalog_rooftop_contract(str(region_id))
    selection = build_rooftop_selection_from_contract(
        contract,
        access_scope=str(access_scope),
        enabled=False,
        panel_area_m2_per_person=float(
            contract.rooftop.panel_area_m2_per_person.default
        ),
    )
    result = _validate_workspace_rooftop_selection_execution(
        selection,
        domain_resolution=int(target_resolution),
    )
    return pd.DataFrame(
        {
            "hex_id": [cell.cell_id for cell in result.population_cells],
            "population": [cell.population for cell in result.population_cells],
        }
    )


def _solar_v1_population_count_frame(region: dict[str, Any], target_resolution: int) -> pd.DataFrame:
    region_id = str(region.get("region_id") or "")
    identity = _workspace_ui_identity(region_id, ROOFTOP_CAPABILITY_ID)
    return _canonical_rooftop_population_count_frame(
        region_id,
        identity.access_scope,
        int(target_resolution),
    )


def _solar_v1_population_source_available(region: dict[str, Any]) -> bool:
    try:
        source = load_catalog_rooftop_contract(
            str(region.get("region_id") or "")
        ).rooftop.population_source
        return not _solar_v1_population_count_frame(
            region,
            int(source.analysis_h3_resolution),
        ).empty
    except (FileNotFoundError, KeyError, ValueError):
        return False


def _solar_v1_population_source_status(region: dict[str, Any]) -> str:
    try:
        source = load_catalog_rooftop_contract(
            str(region.get("region_id") or "")
        ).rooftop.population_source
    except (KeyError, ValueError) as exc:
        return f"Manifeststyrt befolkningsunderlag saknas: {exc}"
    mapped_population = source.expected_analysis_domain_totals[
        source.analysis_h3_resolution
    ]
    outside_population = max(
        0.0,
        source.expected_total - mapped_population,
    )
    return (
        f"Befolkningsunderlag: {source.semantics} på H3 R{source.source_h3_resolution}, "
        f"aggregerat direkt till R{source.analysis_h3_resolution}. "
        f"Energibokföringen använder källtotalen {source.expected_total:,.0f} personer; "
        f"kartschablonen visar {mapped_population:,.0f} inom analysdomänen "
        f"({outside_population:,.0f} ligger utanför kartdomänen)."
    ).replace(",", " ")


def _solar_v1_panel_area_label(region: dict[str, Any]) -> str:
    return _t("Panelyta per person")


def _solar_v1_formula_text(region: dict[str, Any], panel_area_m2_per_person: float) -> str:
    return (
        "Småskalig taksol beräknas från det manifestdeklarerade "
        f"befolkningsunderlaget × {float(panel_area_m2_per_person or 0.0):.0f} m2 panelyta/person."
    )


def _solar_v1_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    resolution: int,
    panel_area_m2_per_person: float,
) -> pd.DataFrame:
    columns = [
        "hex_id",
        "class_km",
        "landscape_type",
        "population",
        "solar_v1_area_m2",
        "solar_v1_area_km2",
        "solar_v1_score",
        "solar_v1_class",
        "solar_v1_class_label",
        "solar_v1_color",
        "solar_v1_population_label",
    ]
    resolution = int(resolution)
    display_geometry_path = _h3_display_geometry_path(region, resolution)
    landscape = _landscape_frame(region, landscape_manifest, resolution)
    if landscape.empty:
        return pd.DataFrame(columns=columns)
    population = _solar_v1_population_count_frame(region, resolution)
    frame = landscape[["hex_id", "class_km", "landscape_type"]].copy()
    frame = frame.merge(population, on="hex_id", how="left")
    frame["population"] = pd.to_numeric(frame["population"], errors="coerce").fillna(0.0).clip(lower=0.0)
    rooftop_contract = load_catalog_rooftop_contract(
        str(region.get("region_id") or "")
    ).rooftop
    mapped_population = float(frame["population"].sum())
    if not math.isclose(
        mapped_population,
        rooftop_contract.population_source.expected_analysis_domain_totals[
            resolution
        ],
        rel_tol=0.0,
        abs_tol=1e-6,
    ):
        raise ValueError(
            "Rooftop-solar mapped population does not match its manifest: "
            f"{mapped_population:g} != "
            f"{rooftop_contract.population_source.expected_analysis_domain_totals[resolution]:g}"
        )
    frame["solar_v1_area_m2"] = frame["population"] * max(0.0, float(panel_area_m2_per_person or 0.0))
    frame["solar_v1_area_km2"] = frame["solar_v1_area_m2"] / 1_000_000.0
    max_area = float(frame["solar_v1_area_m2"].max() or 0.0)
    if max_area > 0:
        frame["solar_v1_score"] = (frame["solar_v1_area_m2"].map(math.log1p) / math.log1p(max_area) * 100.0).clip(lower=0.0, upper=100.0).round(1)
    else:
        frame["solar_v1_score"] = 0.0
    classes = [_solar_v1_class(float(value)) for value in frame["solar_v1_area_m2"]]
    frame["solar_v1_class"] = [item["id"] for item in classes]
    frame["solar_v1_class_label"] = [item["label"] for item in classes]
    frame["solar_v1_color"] = [item["color"] for item in classes]
    frame["solar_v1_population_label"] = "personer (manifestproxy)"
    return _filter_frame_to_display_geometries(frame, display_geometry_path).reindex(columns=columns)


@st.cache_data(show_spinner=False)
def _solar_v1_feature_collection(frame_json: str, target_resolution: int) -> dict[str, Any]:
    frame = pd.read_json(StringIO(frame_json), orient="records")
    if frame.empty:
        return {"type": "FeatureCollection", "features": []}
    features: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        hex_id = str(row.hex_id)
        area_m2 = float(getattr(row, "solar_v1_area_m2", 0.0) or 0.0)
        if area_m2 <= 0:
            continue
        population_label = str(getattr(row, "solar_v1_population_label", "personer") or "personer")
        try:
            source_resolution = int(h3.get_resolution(hex_id))
        except Exception:
            source_resolution = int(target_resolution)
        child_resolution = min(15, max(int(target_resolution), source_resolution) + 1)
        try:
            display_hex = str(h3.cell_to_center_child(hex_id, child_resolution))
        except Exception:
            display_hex = hex_id
        geometry = _h3_polygon_geometry(display_hex)
        if geometry is None:
            continue
        population = float(getattr(row, "population", 0.0) or 0.0)
        popup = (
            f"<strong>{hex_id}</strong><br>"
            f"{SOLAR_SMALL_SCALE_LABEL}: {area_m2:.0f} m2<br>"
            f"{population_label}: {population:.1f}<br>"
            f"Landskapstyp: {int(row.class_km)} - {row.landscape_type}<br>"
            "Visas som liten schablonhex, inte som faktisk takpolygon."
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": hex_id,
                    "display_hex_id": display_hex,
                    "score": float(getattr(row, "solar_v1_score", 0.0) or 0.0),
                    "class": str(getattr(row, "solar_v1_class", "none")),
                    "class_label": str(getattr(row, "solar_v1_class_label", "0 m2")),
                    "fill": str(getattr(row, "solar_v1_color", "#fde68a")),
                    "stroke": "#7c2d12",
                    "stroke_weight": 0.55,
                    "fill_opacity": 0.9,
                    "tooltip_title": f"{SOLAR_SMALL_SCALE_LABEL}: {area_m2:.0f} m2",
                    "tooltip_body": f"Schablon från {population_label} per hex",
                    "popup": popup,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _solar_v1_layer(
    name: str,
    frame: pd.DataFrame,
    target_resolution: int,
) -> dict[str, Any]:
    if frame.empty:
        map_frame = pd.DataFrame(
            columns=[
                "hex_id",
                "class_km",
                "landscape_type",
                "population",
                "solar_v1_area_m2",
                "solar_v1_score",
                "solar_v1_class",
                "solar_v1_class_label",
                "solar_v1_color",
                "solar_v1_population_label",
            ]
        )
    else:
        map_frame = frame[
            [
                "hex_id",
                "class_km",
                "landscape_type",
                "population",
                "solar_v1_area_m2",
                "solar_v1_score",
                "solar_v1_class",
                "solar_v1_class_label",
                "solar_v1_color",
                "solar_v1_population_label",
            ]
        ].copy()
    return {
        "name": name,
        "feature_collection": _solar_v1_feature_collection(map_frame.to_json(orient="records", force_ascii=False), int(target_resolution)),
        "fill_property": "fill",
        "fill_opacity_property": "fill_opacity",
        "stroke_property": "stroke",
        "stroke_weight_property": "stroke_weight",
        "legend_items": _solar_v1_legend_items(),
        "legend_id": "solar_v1_schematic",
        "legend_title": "Småskalig solyta (schablon)",
        "default_visible": True,
        "stroke": True,
        "stroke_opacity": 0.82,
        "fill_opacity": 0.9,
        "weight": 0.55,
        "z_index": 530,
        "layer_kind": "hex",
        "opacity_family": name,
        "opacity_label": name,
    }


def _solar_score_class(score: float) -> dict[str, str]:
    value = max(0.0, min(100.0, float(score or 0.0)))
    if value <= 0:
        return {"id": "none", "label": "0%", "color": "#991b1b"}
    if value < 25:
        return {"id": "low", "label": "0-25%", "color": "#f87171"}
    if value < 50:
        return {"id": "medium_low", "label": "25-50%", "color": "#fef08a"}
    if value < 75:
        return {"id": "medium_high", "label": "50-75%", "color": "#facc15"}
    return {"id": "high", "label": "75-100%", "color": "#ca8a04"}


def _solar_score_legend_items() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in [0, 10, 35, 60, 90]:
        item = _solar_score_class(float(value))
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        items.append({"label": item["label"], "color": item["color"]})
    return items


def _h3_edge_length_m(resolution: int) -> float:
    try:
        return float(h3.average_hexagon_edge_length(int(resolution), unit="m"))
    except Exception:
        return 75.0


def _population_buffer_ring_count(resolution: int, buffer_m: float) -> int:
    edge_m = max(1.0, _h3_edge_length_m(int(resolution)))
    return max(1, int(math.ceil(max(0.0, float(buffer_m or 0.0)) / edge_m)))


def _append_unique_layer(layers: list[dict[str, Any]], layer: dict[str, Any] | None) -> None:
    if layer is None:
        return
    source_layer_id = str(layer.get("source_layer_id", "") or "")
    if source_layer_id and any(str(existing.get("source_layer_id", "") or "") == source_layer_id for existing in layers):
        return
    buffer_layer_id = str(layer.get("buffer_layer_id", "") or "")
    if buffer_layer_id and any(str(existing.get("buffer_layer_id", "") or "") == buffer_layer_id for existing in layers):
        return
    name = str(layer.get("name", ""))
    if name and not source_layer_id and not buffer_layer_id and any(str(existing.get("name", "")) == name for existing in layers):
        return
    layers.append(layer)


def _layer_visible_by_default(layer: dict[str, Any] | None) -> dict[str, Any] | None:
    if layer is None:
        return None
    visible_layer = dict(layer)
    visible_layer["default_visible"] = True
    return visible_layer


def _dedupe_layers(layers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_source_ids: set[str] = set()
    seen_names: set[str] = set()
    for layer in layers:
        source_layer_id = str(layer.get("source_layer_id", "") or "")
        if source_layer_id:
            if source_layer_id in seen_source_ids:
                continue
            seen_source_ids.add(source_layer_id)
        buffer_layer_id = str(layer.get("buffer_layer_id", "") or "")
        if buffer_layer_id:
            if buffer_layer_id in seen_source_ids:
                continue
            seen_source_ids.add(buffer_layer_id)
        name = str(layer.get("name", "") or "")
        if name:
            if not source_layer_id and not buffer_layer_id and name in seen_names:
                continue
            seen_names.add(name)
        deduped.append(layer)
    return deduped


def _solar_filter_source_layers(
    region_id: str,
    visual_group_id: str,
    canonical_group_id: str,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Build one solar source review layer from the solar manifest."""

    spec = SOLAR_FILTER_GROUP_SPECS.get(str(visual_group_id), {})
    group_contract = _solar_manifest_group_contract(
        str(region_id),
        str(visual_group_id),
        str(canonical_group_id),
    )
    layer_contracts = {layer.id: layer for layer in group_contract.layers}
    requested = tuple(dict.fromkeys(str(value) for value in (layer_ids or ())))
    unknown = set(requested) - set(layer_contracts)
    if not requested or unknown:
        raise ValueError(
            f"Solar source review has invalid {canonical_group_id} layers: "
            f"{sorted(unknown) if unknown else 'empty selection'}"
        )
    selected_layer_ids = tuple(
        layer.id for layer in group_contract.layers if layer.id in set(requested)
    )
    source_label = f"Solkälla: {group_contract.label}"
    features: list[dict[str, Any]] = []
    source_colors: list[str] = []
    for layer_id in selected_layer_ids:
        layer_contract = layer_contracts[layer_id]
        if not layer_contract.ready:
            raise ValueError(
                f"Solar source review layer is not ready: {layer_id}"
            )
        geojson = _cached_analysis_source_geojson(
            str(region_id),
            "solar",
            str(canonical_group_id),
            layer_id,
        )
        source_color = _rgb_to_hex(layer_contract.source_color)
        label = str(layer_contract.label)
        source_colors.append(source_color)
        for feature in geojson.get("features") or []:
            if not isinstance(feature, dict) or not feature.get("geometry"):
                continue
            copied = json.loads(json.dumps(feature))
            props = copied.setdefault("properties", {})
            props["fill"] = source_color
            props["source_layer_id"] = layer_id
            props["analysis_id"] = "solar"
            props["canonical_group_id"] = str(canonical_group_id)
            props["tooltip_title"] = source_label
            props["tooltip_body"] = label
            props.setdefault("popup", f"<strong>{source_label}</strong><br>{label}")
            features.append(copied)
    if not features:
        return []
    return [
        {
            "name": source_label,
            "source_layer_id": (
                f"solar:{canonical_group_id}:{'_'.join(selected_layer_ids)}"
            ),
            "feature_collection": {"type": "FeatureCollection", "features": features},
            "fill_property": "fill",
            "legend_items": [
                {
                    "label": str(group_contract.label),
                    "color": source_colors[0]
                    if source_colors
                    else _rgb_to_hex(group_contract.group_color),
                }
            ],
            "legend_id": f"solar_{visual_group_id}_source",
            "legend_title": "",
            "default_visible": False,
            "stroke_color": source_colors[0] if source_colors else "#15803d",
            "fill_color": source_colors[0] if source_colors else "#15803d",
            "stroke_opacity": 0.82,
            "fill_opacity": 0.22,
            "weight": 1.4,
            "point_radius": 4,
            "use_global_opacity": False,
            "z_index": 456,
            "layer_kind": "vector",
        }
    ]


def _solar_available_filter_layer_ids(
    group_id: str,
    layer_ids: list[str] | tuple[str, ...] | set[str] | None = None,
) -> tuple[str, ...]:
    canonical_group_id = SOLAR_AREA_CANONICAL_GROUP_IDS.get(str(group_id))
    if canonical_group_id is not None:
        contract = _solar_manifest_group_contract(
            _wind_region_id(),
            str(group_id),
            canonical_group_id,
        )
        requested = (
            [layer.id for layer in contract.layers]
            if layer_ids is None
            else [str(layer_id) for layer_id in layer_ids]
        )
        ready = {layer.id for layer in contract.layers if layer.ready}
        return tuple(
            layer.id
            for layer in contract.layers
            if layer.id in set(requested) and layer.id in ready
        )
    _, layers, registry_meta = load_acceptance_registry()
    requested = list(_solar_filter_layer_ids(group_id)) if layer_ids is None else [str(layer_id) for layer_id in layer_ids]
    allowed = set(_solar_filter_layer_ids(group_id))
    available: list[str] = []
    for layer_id in requested:
        if layer_id not in allowed or layer_id in available:
            continue
        if layer_id not in layers:
            continue
        if source_geojson_for_layer(registry_meta, layer_id):
            available.append(layer_id)
    return tuple(available)


def _solar_filter_layer_options(group_id: str) -> list[dict[str, Any]]:
    canonical_group_id = SOLAR_AREA_CANONICAL_GROUP_IDS.get(str(group_id))
    if canonical_group_id is not None:
        contract = _solar_manifest_group_contract(
            _wind_region_id(),
            str(group_id),
            canonical_group_id,
        )
        return [
            {
                "id": layer.id,
                "label": layer.label,
                "ready": bool(layer.ready),
                "message": str(layer.message or layer.note),
            }
            for layer in contract.layers
        ]
    _, layers, registry_meta = load_acceptance_registry()
    availability = _wind_layer_status_lookup(registry_meta)
    options: list[dict[str, Any]] = []
    for layer_id in _solar_filter_layer_ids(group_id):
        layer_spec = layers.get(layer_id)
        if layer_spec is None:
            continue
        ready = _wind_layer_is_ready(layer_id, availability)
        status = availability.get(layer_id, {})
        message = str(status.get("message", "") or layer_note(layer_spec, WIND_CONTROL_LANGUAGE, layer_spec.note) or "")
        options.append(
            {
                "id": layer_id,
                "label": layer_label(layer_spec, WIND_CONTROL_LANGUAGE, layer_spec.label),
                "ready": bool(ready),
                "message": message,
            }
        )
    return options


def _solar_filter_runtime_result(
    group_id: str,
    buffer_m: float,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    selected_layer_ids = _solar_available_filter_layer_ids(group_id, layer_ids)
    if not selected_layer_ids:
        return None
    try:
        config = {
            "groups": {
                str(group_id): {
                    "active_layer_ids": list(selected_layer_ids),
                    "analysis_value_m": int(round(max(0.0, float(buffer_m or 0.0)))),
                }
            }
        }
        return run_geometry_runtime(json.dumps(config, sort_keys=True, ensure_ascii=False))
    except Exception:
        return None


def _solar_filter_buffer_geojson(
    group_id: str,
    buffer_m: float,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    runtime_result = _solar_filter_runtime_result(group_id, float(buffer_m or 0.0), layer_ids)
    runtime_group = (runtime_result or {}).get("groups", {}).get(str(group_id)) if isinstance(runtime_result, dict) else None
    if not isinstance(runtime_group, dict):
        return None
    geojson = runtime_group.get("geojson")
    return geojson if isinstance(geojson, dict) else None


@st.cache_data(show_spinner=False, max_entries=64)
def _cached_analysis_source_geojson(
    region_id: str,
    analysis_id: str,
    canonical_group_id: str,
    layer_id: str,
) -> dict[str, Any]:
    """Return one manifest/provider-resolved source for map review."""

    return analysis_source_geojson(
        str(region_id),
        str(analysis_id),
        str(canonical_group_id),
        str(layer_id),
    )


@st.cache_data(show_spinner=False, max_entries=32)
def _cached_vector_buffer_preview(
    region_id: str,
    layer_ids: tuple[str, ...],
    buffer_m: float,
    analysis_id: str = "wind",
    canonical_group_id: str | None = None,
) -> dict[str, Any]:
    """Return a serializable manifest-resolved preview for map inspection."""

    if canonical_group_id is None:
        if str(analysis_id) != "wind":
            raise ValueError(
                "A non-wind preview requires one canonical area group"
            )
        preview = vector_buffer_preview(
            str(region_id),
            tuple(str(layer_id) for layer_id in layer_ids),
            float(buffer_m),
        )
    else:
        preview = analysis_area_group_preview(
            str(region_id),
            str(analysis_id),
            str(canonical_group_id),
            tuple(str(layer_id) for layer_id in layer_ids),
            float(buffer_m),
        )
    return {
        "geojson": preview.geojson,
        "layer_ids": list(preview.layer_ids),
        "buffer_m": float(preview.buffer_m),
        "semantics": str(preview.semantics),
        "geometry_type": str(preview.geometry_type),
        "source_feature_count": int(preview.source_feature_count),
        "area_m2": float(preview.area_m2),
        "model_area_m2": float(
            preview.model_area_m2
            if preview.model_area_m2 is not None
            else preview.area_m2
        ),
        "zero_cell_count": preview.zero_cell_count,
        "partial_cell_count": preview.partial_cell_count,
        "full_cell_count": preview.full_cell_count,
    }


@_presentation_input('_vector_preview_supported')
def _vector_preview_supported(
    region_id: str,
    layer_ids: list[str] | tuple[str, ...] | None,
    analysis_id: str = "wind",
    canonical_group_id: str | None = None,
) -> bool:
    requested = {str(layer_id) for layer_id in (layer_ids or ())}
    if not requested:
        return False
    supported = set(
        vector_preview_layer_ids(
            str(region_id),
            str(analysis_id),
            canonical_group_id,
        )
    )
    return requested.issubset(supported)


def _safe_preview_error_code(error: Exception) -> str:
    code = str(getattr(error, "code", "preview_failed") or "preview_failed")
    return code if code.replace("_", "").isalnum() else "preview_failed"


def _h3_resolution_from_hex_ids(hex_ids: pd.Series) -> int | None:
    for value in hex_ids.dropna().astype(str).head(250):
        try:
            return int(h3.get_resolution(str(value)))
        except Exception:
            continue
    return None


def _expand_share_frame_to_resolution(frame: pd.DataFrame, target_resolution: int) -> pd.DataFrame:
    if frame.empty or "hex_id" not in frame.columns:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    source_resolution = _h3_resolution_from_hex_ids(frame["hex_id"])
    if source_resolution is None or int(source_resolution) == int(target_resolution):
        out = frame[["hex_id", "filter_buffer_share_pct"]].copy()
        out["hex_id"] = out["hex_id"].astype(str)
        return out
    work = frame[["hex_id", "filter_buffer_share_pct"]].copy()
    work["hex_id"] = work["hex_id"].astype(str)
    if int(source_resolution) > int(target_resolution):
        work["hex_id"] = work["hex_id"].map(lambda value: str(h3.cell_to_parent(str(value), int(target_resolution))))
        return work.groupby("hex_id", as_index=False)["filter_buffer_share_pct"].max()
    rows: list[dict[str, Any]] = []
    for row in work.itertuples(index=False):
        try:
            children = h3.cell_to_children(str(row.hex_id), int(target_resolution))
        except Exception:
            children = []
        for child in children:
            rows.append({"hex_id": str(child), "filter_buffer_share_pct": float(row.filter_buffer_share_pct or 0.0)})
    if not rows:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    return pd.DataFrame(rows).groupby("hex_id", as_index=False)["filter_buffer_share_pct"].max()


def _distance_table_filter_share_frame(
    region: dict[str, Any],
    target_resolution: int,
    filter_configs: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> pd.DataFrame:
    _ = region
    if not filter_configs:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    _, _, registry_meta = load_acceptance_registry()
    status_lookup = _wind_layer_status_lookup(registry_meta)
    frames: list[pd.DataFrame] = []
    for filter_config in filter_configs:
        group_id = str(filter_config.get("group_id", ""))
        buffer_m = max(0.0, float(filter_config.get("buffer_m", 0.0) or 0.0))
        layer_ids = (
            _solar_available_large_population_layer_ids(
                filter_config.get("layer_ids") or []
            )
            if group_id == "population"
            else _solar_available_filter_layer_ids(
                group_id,
                filter_config.get("layer_ids") or [],
            )
        )
        layer_frames: list[pd.DataFrame] = []
        for layer_id in layer_ids:
            distance_df = distance_table_for_layer(registry_meta, layer_id)
            if distance_df.empty or "hex_id" not in distance_df.columns:
                continue
            source_resolution = _h3_resolution_from_hex_ids(distance_df["hex_id"])
            if source_resolution is None:
                continue
            cell_area_m2 = float(h3_hex_area_km2(source_resolution) * 1_000_000.0)
            equivalent_radius_m = math.sqrt(max(cell_area_m2, 1e-9) / math.pi)
            geometry_family = str((status_lookup.get(str(layer_id), {}) or {}).get("geometry_family", "") or "").lower()
            distance = pd.to_numeric(distance_df.get("distance_m"), errors="coerce")
            intersects = distance_df.get("intersects", pd.Series(False, index=distance_df.index)).fillna(False).astype(bool)
            if "line" in geometry_family:
                if buffer_m <= 0:
                    share = pd.Series(0.0, index=distance_df.index, dtype="float64")
                else:
                    line_cap_pct = min(100.0, (4.0 * buffer_m * equivalent_radius_m / max(cell_area_m2, 1e-9)) * 100.0)
                    proximity = ((buffer_m - distance) / max(buffer_m, 1.0)).clip(lower=0.0, upper=1.0).fillna(0.0)
                    share = proximity * line_cap_pct
                    share.loc[intersects] = line_cap_pct
            elif "point" in geometry_family:
                if buffer_m <= 0:
                    share = pd.Series(0.0, index=distance_df.index, dtype="float64")
                else:
                    point_cap_pct = min(100.0, (math.pi * buffer_m * buffer_m / max(cell_area_m2, 1e-9)) * 100.0)
                    proximity = ((buffer_m - distance) / max(buffer_m, 1.0)).clip(lower=0.0, upper=1.0).fillna(0.0)
                    share = proximity * point_cap_pct
                    share.loc[intersects] = max(point_cap_pct, 1.0)
            else:
                if buffer_m <= 0:
                    share = intersects.astype(float) * 100.0
                else:
                    proximity = ((buffer_m - distance) / max(buffer_m, 1.0)).clip(lower=0.0, upper=1.0).fillna(0.0) * 100.0
                    share = proximity
                    share.loc[intersects] = 100.0
            layer_frame = pd.DataFrame(
                {
                    "hex_id": distance_df["hex_id"].astype(str),
                    "filter_buffer_share_pct": pd.to_numeric(share, errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0),
                }
            )
            layer_frame = layer_frame[layer_frame["filter_buffer_share_pct"].gt(0.0)].copy()
            if not layer_frame.empty:
                layer_frames.append(layer_frame)
        if not layer_frames:
            continue
        combined = pd.concat(layer_frames, ignore_index=True, sort=False)
        combined = combined.groupby("hex_id", as_index=False)["filter_buffer_share_pct"].max()
        combined = _expand_share_frame_to_resolution(combined, int(target_resolution))
        if not combined.empty:
            frames.append(combined)
    if not frames:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    out = pd.concat(frames, ignore_index=True, sort=False)
    out = out.groupby("hex_id", as_index=False)["filter_buffer_share_pct"].max()
    out["filter_buffer_share_pct"] = pd.to_numeric(out["filter_buffer_share_pct"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
    return out[out["filter_buffer_share_pct"].gt(0.0)][["hex_id", "filter_buffer_share_pct"]].copy()


def _solar_filter_buffer_frame(
    region: dict[str, Any],
    target_resolution: int,
    group_id: str,
    buffer_m: float,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame(columns=["hex_id", "filter_group_id", "filter_buffer_m", "filter_buffer_share_pct"])
    buffer_geojson = _solar_filter_buffer_geojson(group_id, float(buffer_m or 0.0), layer_ids)
    if not buffer_geojson:
        return pd.DataFrame(columns=["hex_id", "filter_group_id", "filter_buffer_m", "filter_buffer_share_pct"])
    share = runtime_combined_hex_frame(buffer_geojson, int(target_resolution), [])
    if share.empty:
        return pd.DataFrame(columns=["hex_id", "filter_group_id", "filter_buffer_m", "filter_buffer_share_pct"])
    share = _filter_frame_to_display_geometries(share, display_geometry_path)
    if share.empty:
        return pd.DataFrame(columns=["hex_id", "filter_group_id", "filter_buffer_m", "filter_buffer_share_pct"])
    score_col = "wind_score" if "wind_score" in share.columns else "potential_area_share_pct"
    share["filter_buffer_share_pct"] = pd.to_numeric(share.get(score_col), errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
    share = share[share["filter_buffer_share_pct"].gt(0.0)].copy()
    share["filter_group_id"] = str(group_id)
    share["filter_buffer_m"] = float(buffer_m or 0.0)
    return share[["hex_id", "filter_group_id", "filter_buffer_m", "filter_buffer_share_pct"]].copy()


def _solar_filter_union_buffer_frame(
    region: dict[str, Any],
    target_resolution: int,
    filter_configs: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None,
) -> pd.DataFrame:
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    features: list[dict[str, Any]] = []
    fallback_configs: list[dict[str, Any]] = []
    for filter_config in filter_configs or []:
        group_id = str(filter_config.get("group_id", ""))
        layer_ids = filter_config.get("layer_ids") or []
        buffer_m = float(filter_config.get("buffer_m", 0.0) or 0.0)
        if group_id == "population":
            fallback_configs.append(
                {
                    **dict(filter_config),
                    "layer_ids": list(
                        _solar_available_large_population_layer_ids(
                            layer_ids,
                            str(region.get("region_id") or ""),
                        )
                    ),
                }
            )
            continue
        else:
            geojson = _solar_filter_buffer_geojson(group_id, buffer_m, layer_ids)
        if not isinstance(geojson, dict):
            fallback_configs.append(dict(filter_config))
            continue
        for feature in geojson.get("features") or []:
            if isinstance(feature, dict) and feature.get("geometry"):
                features.append(feature)
    fallback_share = _distance_table_filter_share_frame(region, int(target_resolution), fallback_configs)
    extra_share_frames: list[pd.DataFrame] = []
    if not fallback_share.empty:
        extra_share_frames.append(fallback_share)
    if extra_share_frames and not features:
        combined = pd.concat(extra_share_frames, ignore_index=True, sort=False)
        combined = (
            combined.groupby("hex_id", as_index=False)["filter_buffer_share_pct"]
            .max()
            .reset_index(drop=True)
        )
        return combined[["hex_id", "filter_buffer_share_pct"]]
    if not features:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    combined_geojson = {"type": "FeatureCollection", "features": features}
    share = runtime_combined_hex_frame(combined_geojson, int(target_resolution), [])
    if share.empty:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    share = _filter_frame_to_display_geometries(share, display_geometry_path)
    if share.empty:
        return pd.DataFrame(columns=["hex_id", "filter_buffer_share_pct"])
    score_col = "wind_score" if "wind_score" in share.columns else "potential_area_share_pct"
    share["filter_buffer_share_pct"] = pd.to_numeric(share.get(score_col), errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
    share = share[share["filter_buffer_share_pct"].gt(0.0)].copy()
    if extra_share_frames:
        share = pd.concat([share[["hex_id", "filter_buffer_share_pct"]], *extra_share_frames], ignore_index=True, sort=False)
        share = share.groupby("hex_id", as_index=False)["filter_buffer_share_pct"].max()
    return share[["hex_id", "filter_buffer_share_pct"]].copy()


def _solar_filter_buffer_layer(
    region_id: str,
    visual_group_id: str,
    canonical_group_id: str,
    buffer_m: float,
    layer_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any] | None:
    """Build the exact solar area-group geometry for map review."""

    spec = SOLAR_FILTER_GROUP_SPECS.get(str(visual_group_id), {})
    group_contract = _solar_manifest_group_contract(
        str(region_id),
        str(visual_group_id),
        str(canonical_group_id),
    )
    allowed = {layer.id for layer in group_contract.layers if layer.ready}
    requested = tuple(dict.fromkeys(str(value) for value in (layer_ids or ())))
    unknown = set(requested) - allowed
    if not requested or unknown:
        raise ValueError(
            f"Solar buffer review has invalid {canonical_group_id} layers: "
            f"{sorted(unknown) if unknown else 'empty selection'}"
        )
    selected_layer_ids = tuple(
        layer.id for layer in group_contract.layers if layer.id in set(requested)
    )
    preview = _cached_vector_buffer_preview(
        str(region_id),
        selected_layer_ids,
        float(buffer_m or 0.0),
        "solar",
        str(canonical_group_id),
    )
    buffer_geojson = preview.get("geojson")
    if not buffer_geojson:
        return None
    features = buffer_geojson.get("features") if isinstance(buffer_geojson, dict) else None
    if not isinstance(features, list) or not features:
        return None
    buffer_color = str(
        spec.get("buffer_color") or _rgb_to_hex(group_contract.group_color)
    )
    group_label_text = str(group_contract.label)
    buffer_label = str(
        f"Sol nära nät: {group_contract.label}"
        if group_contract.analysis_kind == "proximity_feasibility"
        else f"Solbuffert: {group_contract.label}"
    )
    is_feasibility = (
        group_contract.analysis_kind == "proximity_feasibility"
    )
    measure_label = "Max avstånd" if is_feasibility else "Buffert"
    preview_model_area_m2 = float(
        preview.get("model_area_m2", preview["area_m2"])
    )
    preview_area_label = (
        "Genomförbar modellarea inom analysdomänen"
        if is_feasibility
        else "Buffertyta inom analysdomänen"
    )
    tooltip_body = (
        f"Inom {float(buffer_m or 0.0):.0f} m · "
        f"{preview_model_area_m2 / 1_000_000.0:.1f} km²"
        if is_feasibility
        else f"{float(buffer_m or 0.0):.0f} m buffert · "
        f"{preview_model_area_m2 / 1_000_000.0:.1f} km²"
    )
    legend_label = str(
        spec.get("buffer_legend_label")
        or (
            f"Inom maxavstånd till {group_label_text.lower()}"
            if is_feasibility
            else f"Buffert runt {group_label_text.lower()}"
        )
    )
    for feature in features:
        props = feature.setdefault("properties", {})
        props["fill"] = buffer_color
        props["popup"] = (
            f"<strong>{buffer_label}</strong><br>"
            f"{measure_label}: {float(buffer_m or 0.0):.0f} m<br>"
            f"{preview_area_label}: "
            f"{preview_model_area_m2 / 1_000_000.0:.1f} km²<br>"
            f"{group_contract.interpretation}"
        )
        props["tooltip_title"] = buffer_label
        props["tooltip_body"] = tooltip_body
    return {
        "name": buffer_label,
        "buffer_layer_id": (
            f"solar:{canonical_group_id}:buffer:"
            f"{int(round(float(buffer_m or 0.0)))}:"
            f"{'_'.join(selected_layer_ids) if selected_layer_ids else 'none'}"
        ),
        "feature_collection": buffer_geojson,
        "fill_property": "fill",
        "legend_items": [{"label": legend_label, "color": buffer_color}],
        "legend_id": f"solar_{visual_group_id}_buffer",
        "legend_title": "",
        "default_visible": False,
        "stroke_color": str(spec.get("source_color") or buffer_color),
        "fill_color": buffer_color,
        "stroke_opacity": 0.56,
        "fill_opacity": 0.18,
        "weight": 0.75,
        "point_radius": 4,
        "use_global_opacity": False,
        "z_index": 458,
        "layer_kind": "vector",
    }


@st.cache_data(show_spinner=False, max_entries=24)
def _solar_large_scale_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    resolution: int,
    population_buffer_m: float,
    population_layer_ids: list[str] | tuple[str, ...] | None = None,
    protected_buffer_m: float | None = None,
    protected_layer_ids: list[str] | tuple[str, ...] | None = None,
    unfiltered_land_active: bool = False,
    filter_configs: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
) -> pd.DataFrame:
    target_resolution = int(resolution)
    landscape = _landscape_frame(region, landscape_manifest, target_resolution)
    columns = [
        "hex_id",
        "class_km",
        "landscape_type",
        "potential_area_m2",
        "potential_area_km2",
        "potential_area_share_pct",
        "protected_buffer_share_pct",
        "solar_score",
        "solar_class",
        "solar_class_label",
        "solar_color",
    ]
    if landscape.empty:
        return pd.DataFrame(columns=columns)

    active_filter_configs: list[dict[str, Any]] = []
    if float(population_buffer_m or 0.0) > 0:
        active_filter_configs.append(
            {
                "group_id": "population",
                "layer_ids": list(population_layer_ids or []),
                "buffer_m": float(population_buffer_m or 0.0),
                "label": "Befolkning",
                "effect": "exclusion",
            }
        )
    if filter_configs:
        active_filter_configs.extend(dict(item) for item in filter_configs if isinstance(item, dict))
    elif protected_buffer_m is not None:
        active_filter_configs.append(
            {
                "group_id": SOLAR_PROTECTED_GROUP_ID,
                "layer_ids": list(protected_layer_ids or []),
                "buffer_m": float(protected_buffer_m or 0.0),
                "label": PROTECTED_NATURE_LABEL,
                "effect": "exclusion",
            }
        )

    if unfiltered_land_active and not active_filter_configs:
        target_hex_area_m2 = float(h3_hex_area_km2(target_resolution) * 1_000_000.0)
        work = landscape[["hex_id", "class_km", "landscape_type"]].copy()
        work["potential_area_m2"] = target_hex_area_m2
        work["potential_area_km2"] = target_hex_area_m2 / 1_000_000.0
        work["potential_area_share_pct"] = 100.0
        work["protected_buffer_share_pct"] = 0.0
        work["solar_score"] = 100.0
        classes = [_solar_score_class(float(value)) for value in work["solar_score"]]
        work["solar_class"] = [item["id"] for item in classes]
        work["solar_class_label"] = [item["label"] for item in classes]
        work["solar_color"] = [item["color"] for item in classes]
        return work.reindex(columns=columns)

    region_id = str(region.get("region_id") or "").strip()
    solar_analysis = load_delivery_analysis(region_id, "solar")
    analysis_domain = solar_analysis.analysis_domain
    if analysis_domain is None:
        raise ValueError(f"{region_id}/solar has no declared analysis domain")
    declared_resolutions = {
        int(analysis_domain.resolution),
        *(int(value) for value in analysis_domain.rollups),
    }
    if target_resolution not in declared_resolutions:
        raise ValueError(
            f"{region_id}/solar has no R{target_resolution} analysis-domain "
            "target"
        )
    source_resolution = target_resolution
    source_landscape = _landscape_frame(region, landscape_manifest, source_resolution)

    source = source_landscape[["hex_id"]].copy()
    work = source.copy()
    work["potential_area_share_pct"] = 100.0
    if work.empty:
        return pd.DataFrame(columns=columns)

    work["protected_buffer_share_pct"] = 0.0
    exclusion_filter_configs = [
        dict(config)
        for config in active_filter_configs
        if str(config.get("effect", "exclusion")) != "feasibility"
    ]
    feasibility_filter_configs = [
        dict(config)
        for config in active_filter_configs
        if str(config.get("effect", "exclusion")) == "feasibility"
    ]
    if exclusion_filter_configs:
        filters = _solar_filter_union_buffer_frame(region, source_resolution, exclusion_filter_configs)
        if not filters.empty:
            filters = filters[["hex_id", "filter_buffer_share_pct"]].copy()
            work = work.merge(filters, on="hex_id", how="left")
            work["protected_buffer_share_pct"] = pd.to_numeric(
                work.get("filter_buffer_share_pct"),
                errors="coerce",
            ).fillna(0.0).clip(lower=0.0, upper=100.0)
            if "filter_buffer_share_pct" in work.columns:
                work = work.drop(columns=["filter_buffer_share_pct"])
        work["potential_area_share_pct"] = (
            work["potential_area_share_pct"] - work["protected_buffer_share_pct"]
        ).clip(lower=0.0, upper=100.0)
    if feasibility_filter_configs:
        work["feasibility_share_pct"] = 0.0
        feasible = _solar_filter_union_buffer_frame(region, source_resolution, feasibility_filter_configs)
        if not feasible.empty:
            feasible = feasible[["hex_id", "filter_buffer_share_pct"]].rename(
                columns={"filter_buffer_share_pct": "feasibility_share_pct"}
            )
            work = work.merge(feasible, on="hex_id", how="left", suffixes=("", "_from_filter"))
            work["feasibility_share_pct"] = pd.to_numeric(
                work.get("feasibility_share_pct_from_filter", work.get("feasibility_share_pct")),
                errors="coerce",
            ).fillna(0.0).clip(lower=0.0, upper=100.0)
            for extra_col in ["feasibility_share_pct_from_filter"]:
                if extra_col in work.columns:
                    work = work.drop(columns=[extra_col])
        work["potential_area_share_pct"] = (
            work["potential_area_share_pct"] * work["feasibility_share_pct"] / 100.0
        ).clip(lower=0.0, upper=100.0)

    source_hex_area_m2 = float(h3_hex_area_km2(source_resolution) * 1_000_000.0)
    work["potential_area_m2"] = (work["potential_area_share_pct"] / 100.0 * source_hex_area_m2).clip(lower=0.0, upper=source_hex_area_m2)
    work["protected_buffer_area_m2"] = (work["protected_buffer_share_pct"] / 100.0 * source_hex_area_m2).clip(lower=0.0, upper=source_hex_area_m2)

    if target_resolution < source_resolution:
        work["hex_id"] = work["hex_id"].map(lambda value: str(h3.cell_to_parent(str(value), target_resolution)))
        work = (
            work.groupby("hex_id", as_index=False)
            .agg(
                potential_area_m2=("potential_area_m2", "sum"),
                protected_buffer_area_m2=("protected_buffer_area_m2", "sum"),
            )
            .sort_values("hex_id")
            .reset_index(drop=True)
        )

    source = landscape[["hex_id", "class_km", "landscape_type"]].copy()
    work = source.merge(work[["hex_id", "potential_area_m2", "protected_buffer_area_m2"]], on="hex_id", how="left")
    work["potential_area_m2"] = pd.to_numeric(work["potential_area_m2"], errors="coerce").fillna(0.0).clip(lower=0.0)
    work["protected_buffer_area_m2"] = pd.to_numeric(work["protected_buffer_area_m2"], errors="coerce").fillna(0.0).clip(lower=0.0)

    target_hex_area_m2 = float(h3_hex_area_km2(target_resolution) * 1_000_000.0)
    work["potential_area_m2"] = work["potential_area_m2"].clip(lower=0.0, upper=target_hex_area_m2)
    work["potential_area_km2"] = work["potential_area_m2"] / 1_000_000.0
    work["potential_area_share_pct"] = (work["potential_area_m2"] / max(target_hex_area_m2, 1e-9) * 100.0).clip(lower=0.0, upper=100.0)
    work["protected_buffer_share_pct"] = (work["protected_buffer_area_m2"] / max(target_hex_area_m2, 1e-9) * 100.0).clip(lower=0.0, upper=100.0)
    work["solar_score"] = work["potential_area_share_pct"].round(1)
    classes = [_solar_score_class(float(value)) for value in work["solar_score"]]
    work["solar_class"] = [item["id"] for item in classes]
    work["solar_class_label"] = [item["label"] for item in classes]
    work["solar_color"] = [item["color"] for item in classes]
    return _filter_frame_to_display_geometries(work.reindex(columns=columns), _h3_display_geometry_path(region, target_resolution))


def _solar_establishment_potential_source_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    resolution: int,
    large_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Return ground-solar candidates without rooftop schematic area."""

    display_geometry_path = _area_display_geometry_path(
        region,
        int(resolution),
    )
    if not display_geometry_path:
        return pd.DataFrame()
    display_geometries = load_h3_display_geometries(display_geometry_path)
    base = pd.DataFrame(
        {"hex_id": sorted(str(cell_id) for cell_id in display_geometries)}
    )
    if base.empty:
        return pd.DataFrame()
    base["display_area_km2"] = _technology_support_cell_area_km2_series(
        base,
        str(region.get("region_id") or ""),
        "solar",
        int(resolution),
    )
    standard_context = _landscape_frame(
        region,
        landscape_manifest,
        int(resolution),
    )
    context_columns = [
        column
        for column in ["hex_id", "class_km", "landscape_type"]
        if column in standard_context.columns
    ]
    if len(context_columns) > 1:
        standard_context = standard_context[context_columns].copy()
        standard_context["_app_extent_context"] = True
        base = base.merge(
            standard_context,
            on="hex_id",
            how="left",
            validate="one_to_one",
        )
    else:
        base["_app_extent_context"] = False
    app_context = base.pop("_app_extent_context").fillna(False).astype(bool)
    base["technology_context_status"] = app_context.map(
        {True: "app_extent", False: "not_assessed"}
    )
    base["technology_context_available"] = app_context
    base = _attach_full_lablab_technology_context(
        base,
        region,
        landscape_manifest,
        int(resolution),
    )
    if large_frame.empty:
        frame = base
        frame["potential_area_m2"] = 0.0
        frame["potential_area_km2"] = 0.0
        frame["potential_area_share_pct"] = 0.0
        frame["solar_score"] = 0.0
        classes = [_solar_score_class(0.0) for _ in range(len(frame))]
        frame["solar_class"] = [item["id"] for item in classes]
        frame["solar_class_label"] = [item["label"] for item in classes]
        frame["solar_color"] = [item["color"] for item in classes]
    else:
        required = {
            "hex_id",
            "potential_area_m2",
            "potential_area_km2",
            "potential_area_share_pct",
            "solar_score",
            "solar_class",
            "solar_class_label",
            "solar_color",
        }
        missing = required - set(large_frame.columns)
        if missing:
            raise ValueError(
                "Ground-solar candidate frame is missing exact-area columns: "
                f"{sorted(missing)}"
            )
        if large_frame["hex_id"].astype(str).duplicated().any():
            raise ValueError(
                "Ground-solar candidate frame contains duplicate H3 ids"
            )
        prohibited_rooftop_columns = {
            str(column)
            for column in large_frame.columns
            if str(column).startswith("solar_v1")
            or str(column) in {"small_score", "small_area_m2"}
        }
        if prohibited_rooftop_columns:
            raise ValueError(
                "Ground-solar candidate frame contains rooftop schematic "
                f"columns: {sorted(prohibited_rooftop_columns)}"
            )
        base_ids = set(base["hex_id"].astype(str))
        large_ids = set(large_frame["hex_id"].astype(str))
        if base_ids != large_ids:
            raise ValueError(
                "Ground-solar candidate frame does not cover the technology "
                "support domain"
            )
        frame = large_frame.copy()
        frame["display_area_km2"] = frame["hex_id"].astype(str).map(
            base.set_index("hex_id")["display_area_km2"]
        )
        if frame["display_area_km2"].isna().any():
            raise ValueError(
                "Ground-solar candidate frame has no declared eligible area "
                "for every support-domain cell"
            )
        missing_context_columns = [
            column
            for column in [
                "class_km",
                "landscape_type",
                "technology_context_status",
                "technology_context_available",
            ]
            if column not in frame.columns and column in base.columns
        ]
        if missing_context_columns:
            frame = frame.merge(
                base[["hex_id", *missing_context_columns]],
                on="hex_id",
                how="left",
                validate="one_to_one",
            )
    frame["solar_group"] = "Ingen aktiv solpotential"
    frame.loc[
        pd.to_numeric(
            frame["potential_area_km2"],
            errors="raise",
        ).gt(0.0),
        "solar_group",
    ] = SOLAR_LARGE_SCALE_LABEL
    return _filter_frame_to_display_geometries(
        frame.sort_values("hex_id").reset_index(drop=True),
        display_geometry_path,
    )


def _solar_potential_polygon_layer(
    large_frame: pd.DataFrame,
    large_polygon_geojson: dict[str, Any] | None,
) -> dict[str, Any] | None:
    features: list[dict[str, Any]] = []
    if not large_frame.empty and isinstance(large_polygon_geojson, dict):
        has_large_score = pd.to_numeric(large_frame.get("solar_score"), errors="coerce").fillna(0.0).gt(0.0).any()
        if has_large_score:
            for feature in large_polygon_geojson.get("features") or []:
                if not isinstance(feature, dict) or not feature.get("geometry"):
                    continue
                copied = json.loads(json.dumps(feature))
                props = copied.setdefault("properties", {})
                props.setdefault("fill", "#ca8a04")
                props.setdefault(
                    "popup",
                    (
                        f"<strong>{SOLAR_POTENTIAL_POLYGON_LABEL}</strong><br>"
                        f"Grupp: {SOLAR_LARGE_SCALE_LABEL}<br>"
                        "Polygonkälla: kandidatmark v0"
                    ),
                )
                props["tooltip_title"] = SOLAR_POTENTIAL_POLYGON_LABEL
                props["tooltip_body"] = SOLAR_LARGE_SCALE_LABEL
                features.append(copied)

    if not features:
        return None
    legend_items = []
    if isinstance(large_polygon_geojson, dict) and large_polygon_geojson.get("features"):
        legend_items.append({"label": SOLAR_LARGE_SCALE_LABEL, "color": "#ca8a04"})
    if not legend_items:
        legend_items = [
            {"label": SOLAR_LARGE_SCALE_LABEL, "color": "#ca8a04"},
        ]
    return {
        "name": SOLAR_POTENTIAL_POLYGON_LABEL,
        "feature_collection": {"type": "FeatureCollection", "features": features},
        "fill_property": "fill",
        "legend_items": legend_items,
        "legend_id": "solar_potential_polygon",
        "legend_title": SOLAR_POTENTIAL_POLYGON_LABEL,
        "default_visible": False,
        "stroke_color": "#854d0e",
        "fill_color": "#facc15",
        "stroke_opacity": 0.72,
        "fill_opacity": 0.18,
        "weight": 1.3,
        "point_radius": 6,
        "dash_array": "6 4",
        "use_global_opacity": False,
        "z_index": 442,
        "layer_kind": "vector",
    }


def _generic_allocation_rollup_frame(
    selected: pd.DataFrame,
    technology: str,
    target_resolution: int,
    source_resolution: int,
    source_cell_areas_km2: Mapping[str, float] | None,
) -> pd.DataFrame:
    columns = [
        "hex_id",
        "allocated_area_km2",
        "allocated_twh",
        "inside_area_km2",
        "outside_area_km2",
        "selected_child_count",
    ]
    if selected.empty:
        return pd.DataFrame(columns=columns)
    if int(target_resolution) >= int(source_resolution):
        raise ValueError(
            f"{technology} allocation rollup requires a coarser target resolution"
        )
    if source_cell_areas_km2 is None:
        raise ValueError(
            f"{technology} allocation rollup requires manifest-declared "
            "source cell areas"
        )
    required = {
        "hex_id",
        "allocated_area_km2",
        "allocated_twh",
        "potential_area_km2",
        "selected_rank",
    }
    missing = sorted(required - set(selected.columns))
    if missing:
        raise ValueError(
            f"{technology} allocation rollup is missing columns: "
            + ", ".join(missing)
        )

    work = selected.copy()
    work["hex_id"] = work["hex_id"].astype(str).str.strip()
    if work["hex_id"].eq("").any() or work["hex_id"].duplicated().any():
        raise ValueError(
            f"{technology} allocation rollup requires unique non-blank cell ids"
        )
    resolutions: list[int] = []
    try:
        resolutions = [h3.get_resolution(cell_id) for cell_id in work["hex_id"]]
    except Exception as exc:
        raise ValueError(
            f"{technology} allocation rollup contains an invalid H3 cell"
        ) from exc
    if any(value != int(source_resolution) for value in resolutions):
        raise ValueError(
            f"{technology} allocation rollup requires R{source_resolution} cells"
        )

    numeric_columns = [
        "allocated_area_km2",
        "allocated_twh",
        "potential_area_km2",
        "selected_rank",
    ]
    for column in numeric_columns:
        try:
            work[column] = pd.to_numeric(work[column], errors="raise")
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"{technology} allocation rollup has invalid {column}"
            ) from exc
    ranks = work["selected_rank"].astype(float)
    if ranks.duplicated().any():
        raise ValueError(
            f"{technology} allocation rollup requires unique selected ranks"
        )
    if "outside_et" not in work.columns:
        work["outside_et"] = False

    def _strict_bool(value: Any, label: str) -> bool:
        if pd.isna(value) or value not in (True, False, 0, 1):
            raise ValueError(
                f"{technology} allocation rollup has invalid {label}"
            )
        return bool(value)

    outside = [
        _strict_bool(value, "outside_et") for value in work["outside_et"]
    ]
    if "reserved_by_other_technology" in work.columns:
        reserved = [
            _strict_bool(value, "reserved_by_other_technology")
            for value in work["reserved_by_other_technology"]
        ]
    else:
        reserved = [False] * len(work)
    source_area = _establishment_cell_area_km2_series(
        work,
        source_cell_areas_km2,
        h3_hex_area_km2(int(source_resolution)),
        f"{technology} allocation R{source_resolution}",
    )

    allocated_cells = tuple(
        AllocatedCell(
            cell_id=str(row.hex_id),
            allocated_area_km2=float(row.allocated_area_km2),
            allocated_twh=float(row.allocated_twh),
            eligible_area_km2=float(eligible_area),
            potential_area_km2=float(row.potential_area_km2),
            selected_rank=row.selected_rank,
            outside_potential=outside_value,
            reserved_by_other_technology=reserved_value,
        )
        for row, eligible_area, outside_value, reserved_value in zip(
            work.itertuples(index=False),
            source_area,
            outside,
            reserved,
        )
    )
    parent_by_cell: dict[str, str] = {}
    try:
        parent_by_cell = {
            cell.cell_id: str(
                h3.cell_to_parent(cell.cell_id, int(target_resolution))
            )
            for cell in allocated_cells
        }
    except Exception as exc:
        raise ValueError(
            f"{technology} allocation rollup could not resolve an H3 parent"
        ) from exc
    rollup = rollup_allocated_cells(allocated_cells, parent_by_cell)
    return pd.DataFrame(
        [
            {
                "hex_id": cell.cell_id,
                "allocated_area_km2": cell.allocated_area_km2,
                "allocated_twh": cell.allocated_twh,
                "inside_area_km2": cell.inside_potential_area_km2,
                "outside_area_km2": cell.outside_potential_area_km2,
                "selected_child_count": cell.selected_child_count,
            }
            for cell in rollup
        ],
        columns=columns,
    )


def _rollup_solar_establishment_frame(
    selected: pd.DataFrame,
    target_resolution: int,
    source_resolution: int,
    target_cell_areas_km2: Mapping[str, float] | None = None,
    source_cell_areas_km2: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    if selected.empty or int(target_resolution) >= int(source_resolution):
        return selected.copy()

    work = selected.copy()
    allocation_rollup = _generic_allocation_rollup_frame(
        work,
        "solar",
        int(target_resolution),
        int(source_resolution),
        source_cell_areas_km2,
    )

    def _numeric_column(column: str, default: float = 0.0) -> pd.Series:
        if column in work.columns:
            return pd.to_numeric(work[column], errors="coerce").fillna(default)
        return pd.Series(default, index=work.index, dtype="float64")

    work["allocated_area_km2"] = _numeric_column("allocated_area_km2", 0.0)
    work["potential_area_km2"] = _numeric_column("potential_area_km2", 0.0)
    work["allocated_twh"] = _numeric_column("allocated_twh", 0.0)
    work["selected_rank"] = _numeric_column("selected_rank", 0.0).astype(int)
    work["potential_score"] = _numeric_column("potential_score", 0.0)
    work["landscape_priority_score"] = _numeric_column("landscape_priority_score", 0.0)
    work["allocation_priority_score"] = _numeric_column("allocation_priority_score", 0.0)
    work["social_acceptance_priority_score"] = _numeric_column("social_acceptance_priority_score", 0.0)
    work["social_acceptance_value"] = _numeric_column(
        "social_acceptance_value",
        math.nan,
    )
    work["social_acceptance_allocation_priority_pct"] = _numeric_column("social_acceptance_allocation_priority_pct", 0.0)
    work["expansion_ring"] = _numeric_column("expansion_ring", 0.0).astype(int)
    if "outside_et" not in work.columns:
        work["outside_et"] = False
    if "source_group" not in work.columns:
        work["source_group"] = ""
    if "allocation_priority_reason" not in work.columns:
        work["allocation_priority_reason"] = ""
    if "social_acceptance_data_status" not in work.columns:
        work["social_acceptance_data_status"] = "not_assessed"
    work["outside_et"] = work["outside_et"].fillna(False).astype(bool)
    work["hex_id"] = work["hex_id"].astype(str)
    work = work.sort_values(["selected_rank", "hex_id"]).reset_index(drop=True)
    work["hex_id"] = work["hex_id"].astype(str).map(
        lambda value: h3.cell_to_parent(value, int(target_resolution))
    )

    def _source_group_label(values: pd.Series) -> str:
        labels = [str(value) for value in values.dropna().tolist() if str(value)]
        unique = list(dict.fromkeys(labels))
        return ", ".join(unique[:3])

    rolled = (
        work.groupby("hex_id", as_index=False)
        .agg(
            selected_rank=("selected_rank", "min"),
            source_group=("source_group", _source_group_label),
            potential_score=("potential_score", "max"),
            landscape_priority_score=("landscape_priority_score", "max"),
            allocation_priority_score=("allocation_priority_score", "max"),
            allocation_priority_reason=("allocation_priority_reason", _source_group_label),
            social_acceptance_priority_score=("social_acceptance_priority_score", "max"),
            social_acceptance_value=("social_acceptance_value", "mean"),
            social_acceptance_data_status=(
                "social_acceptance_data_status",
                _source_group_label,
            ),
            social_acceptance_allocation_priority_pct=("social_acceptance_allocation_priority_pct", "max"),
            potential_area_km2=(
                "potential_area_km2",
                lambda values: math.fsum(float(value) for value in values),
            ),
            expansion_ring=("expansion_ring", "max"),
        )
        .reset_index(drop=True)
    )
    rolled = rolled.merge(
        allocation_rollup,
        on="hex_id",
        how="inner",
        validate="one_to_one",
    )
    rolled = rolled.sort_values(["selected_rank", "hex_id"]).reset_index(
        drop=True
    )
    if target_cell_areas_km2 is None:
        raise ValueError(
            "Solar allocation rollup requires manifest-declared target "
            "cell areas"
        )
    hex_area = h3_hex_area_km2(int(target_resolution))
    target_area_capacity = _establishment_cell_area_km2_series(
        rolled,
        target_cell_areas_km2,
        hex_area,
        f"solar allocation R{target_resolution}",
    )
    rolled["display_area_km2"] = target_area_capacity.astype(float)
    rolled["potential_area_km2"] = pd.concat(
        [rolled["potential_area_km2"].clip(lower=0.0), target_area_capacity],
        axis=1,
    ).min(axis=1)
    excess_area = rolled["allocated_area_km2"] - target_area_capacity
    if bool(excess_area.gt(1e-9).any()):
        invalid = rolled.loc[excess_area.gt(1e-9), "hex_id"].astype(str).tolist()
        raise ValueError(
            "Solar allocation rollup exceeds manifest-declared target "
            "capacity for: "
            + ", ".join(invalid[:5])
        )
    rolled["allocated_area_km2"] = rolled["allocated_area_km2"].clip(
        lower=0.0
    )
    rolled["outside_et"] = rolled["outside_area_km2"].gt(0.0)
    rolled["allocation_phase"] = rolled["outside_et"].map(lambda value: "Utanför LP" if value else "Inom LP")
    rolled["allocated_hex_share_pct"] = (
        rolled["allocated_area_km2"] / target_area_capacity * 100.0
    ).clip(lower=0.0, upper=100.0)
    rolled["remaining_area_after_km2"] = 0.0
    rolled["allocated_gwh"] = rolled["allocated_twh"] * 1000.0
    return rolled


def _expand_solar_area_outside_lp(
    source_frame: pd.DataFrame,
    selected_frame: pd.DataFrame,
    proposal_stats: dict[str, Any],
    display_geometry_path: str | None,
    hex_area_km2: float,
    solar_twh_need: float,
    solar_area_need_km2: float,
    solar_km2_per_twh: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if source_frame.empty or not display_geometry_path:
        return selected_frame, proposal_stats

    shortage = float(proposal_stats.get("unmet_area_km2", 0.0) or 0.0)
    proposal_stats["lp_selected_area_km2"] = float(proposal_stats.get("selected_area_km2", 0.0) or 0.0)
    proposal_stats["lp_unmet_area_km2"] = max(0.0, shortage)
    if shortage <= 1e-9:
        proposal_stats.setdefault("outside_selected_area_km2", 0.0)
        proposal_stats.setdefault("outside_hex_count", 0)
        proposal_stats.setdefault("max_expansion_ring", 0)
        return selected_frame, proposal_stats

    display_hexes = set(load_h3_display_geometries(display_geometry_path))
    if not display_hexes:
        return selected_frame, proposal_stats

    work = source_frame.copy()
    work["hex_id"] = work["hex_id"].astype(str)
    work["solar_score"] = pd.to_numeric(work.get("solar_score"), errors="coerce").fillna(0.0)
    if "display_area_km2" not in work.columns:
        raise ValueError(
            "Solar outside-LP allocation requires declared eligible "
            "display_area_km2"
        )
    work["allocation_cell_area_km2"] = pd.to_numeric(
        work["display_area_km2"],
        errors="coerce",
    )
    valid_cell_area = work["allocation_cell_area_km2"].notna() & work[
        "allocation_cell_area_km2"
    ].map(lambda value: math.isfinite(float(value)) and float(value) > 0.0)
    if not bool(valid_cell_area.all()):
        invalid_ids = work.loc[~valid_cell_area, "hex_id"].head(5).tolist()
        raise ValueError(
            "Solar outside-LP allocation has no positive finite eligible "
            "area for: "
            + ", ".join(str(cell_id) for cell_id in invalid_ids)
        )
    candidate_hexes = set(work["hex_id"].astype(str)) & display_hexes
    lp_hexes = (
        set(
            work.loc[
                work["solar_score"].gt(0.0),
                "hex_id",
            ].astype(str)
        )
        & candidate_hexes
    )
    selected_hexes = set(selected_frame.get("hex_id", pd.Series(dtype=str)).astype(str)) if not selected_frame.empty else set()
    anchor_hexes = (selected_hexes or lp_hexes) & candidate_hexes

    neighbor_map = _wind_runtime_hex_neighbor_map(display_geometry_path)
    distance_lookup: dict[str, int] = {}
    if anchor_hexes:
        visited = set(anchor_hexes)
        frontier: deque[tuple[str, int]] = deque((hex_id, 0) for hex_id in anchor_hexes)
        while frontier:
            current, distance = frontier.popleft()
            for neighbor in neighbor_map.get(current, []):
                neighbor = str(neighbor)
                if neighbor not in candidate_hexes or neighbor in visited:
                    continue
                visited.add(neighbor)
                distance_lookup[neighbor] = distance + 1
                frontier.append((neighbor, distance + 1))

    outside_hexes = sorted(candidate_hexes - lp_hexes)
    outside = pd.DataFrame({"hex_id": outside_hexes})
    if outside.empty:
        return selected_frame, proposal_stats
    priority_cols = [
        column
        for column in [
            "hex_id",
            "landscape_priority_score",
            "allocation_priority_score",
            "allocation_priority_reason",
            "social_acceptance_priority_score",
            "social_acceptance_value",
            "social_acceptance_data_status",
            "social_acceptance_allocation_priority_pct",
            "allocation_cell_area_km2",
        ]
        if column in work.columns
    ]
    if len(priority_cols) > 1:
        outside = outside.merge(work[priority_cols].drop_duplicates(subset=["hex_id"]), on="hex_id", how="left")
    outside["expansion_ring"] = outside["hex_id"].map(distance_lookup).fillna(999999).astype(int)
    outside = outside[outside["expansion_ring"].lt(999999)].copy()
    if outside.empty:
        return selected_frame, proposal_stats
    outside["allocation_priority_score"] = pd.to_numeric(
        outside.get("allocation_priority_score", pd.Series(0.0, index=outside.index)),
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0, upper=1.0)
    outside = outside.sort_values(
        ["expansion_ring", "allocation_priority_score", "hex_id"],
        ascending=[True, False, True],
    ).reset_index(drop=True)

    if not math.isfinite(float(solar_km2_per_twh)) or solar_km2_per_twh <= 0:
        raise ValueError(
            "Solar outside-LP allocation requires a positive finite "
            "km2/TWh factor"
        )
    declared_demand = TechnologyDemand(
        technology="solar",
        twh=float(solar_twh_need),
        km2_per_twh=float(solar_km2_per_twh),
        area_need_km2=float(solar_area_need_km2),
    )
    if shortage > declared_demand.area_need_km2 + 1e-9:
        raise ValueError(
            "Solar outside-LP shortage cannot exceed declared area demand"
        )
    outside_allocation = allocate_technology_area(
        TechnologyDemand(
            technology="solar",
            twh=shortage / float(solar_km2_per_twh),
            km2_per_twh=float(solar_km2_per_twh),
            area_need_km2=shortage,
        ),
        tuple(
            AllocationCandidate(
                cell_id=str(row.hex_id),
                eligible_area_km2=float(row.allocation_cell_area_km2),
                potential_area_km2=0.0,
                priority=(
                    -float(row.expansion_ring),
                    float(row.allocation_priority_score),
                ),
                outside_potential=True,
            )
            for row in outside.itertuples(index=False)
        ),
    )
    source_rows = {
        str(row.hex_id): row._asdict()
        for row in outside.itertuples(index=False)
    }
    remaining = shortage
    start_rank = int(len(selected_frame)) + 1
    rows: list[dict[str, Any]] = []
    for cell in outside_allocation.cells:
        record = source_rows[cell.cell_id]
        remaining = max(0.0, remaining - cell.allocated_area_km2)
        rows.append(
            {
                "hex_id": cell.cell_id,
                "selected_rank": start_rank + cell.selected_rank - 1,
                "source_group": "Utanför LP",
                "potential_score": 0.0,
                "potential_area_km2": cell.potential_area_km2,
                "allocated_area_km2": cell.allocated_area_km2,
                "allocated_twh": cell.allocated_twh,
                "allocated_gwh": cell.allocated_twh * 1000.0,
                "allocated_hex_share_pct": (
                    cell.allocated_area_km2
                    / cell.eligible_area_km2
                    * 100.0
                ),
                "remaining_area_after_km2": remaining,
                "outside_et": cell.outside_potential,
                "expansion_ring": int(record.get("expansion_ring", 0) or 0),
                "allocation_phase": "Utanför LP",
                "landscape_priority_score": float(record.get("landscape_priority_score", 0.0) or 0.0),
                "allocation_priority_score": float(record.get("allocation_priority_score", 0.0) or 0.0),
                "allocation_priority_reason": str(record.get("allocation_priority_reason", "") or ""),
                "social_acceptance_priority_score": float(record.get("social_acceptance_priority_score", 0.0) or 0.0),
                "social_acceptance_value": _nullable_social_acceptance(
                    record.get("social_acceptance_value", math.nan)
                ),
                "social_acceptance_data_status": str(
                    record.get(
                        "social_acceptance_data_status", "not_assessed"
                    )
                    or "not_assessed"
                ),
                "social_acceptance_allocation_priority_pct": float(
                    record.get(
                        "social_acceptance_allocation_priority_pct", 0.0
                    )
                    or 0.0
                ),
            }
        )

    if not rows:
        return selected_frame, proposal_stats

    outside_frame = pd.DataFrame(rows)
    if "outside_et" not in selected_frame.columns and not selected_frame.empty:
        selected_frame = selected_frame.copy()
        selected_frame["outside_et"] = False
    combined = pd.concat([selected_frame, outside_frame], ignore_index=True, sort=False)
    outside_area = float(outside_frame["allocated_area_km2"].sum())
    proposal_stats.update(
        {
            "selected_area_km2": float(proposal_stats.get("lp_selected_area_km2", 0.0) or 0.0) + outside_area,
            "unmet_area_km2": outside_allocation.unmet_area_km2,
            "selected_hex_count": int(len(combined)),
            "outside_selected_area_km2": outside_area,
            "outside_hex_count": int(len(outside_frame)),
            "outside_candidate_hex": int(len(outside)),
            "outside_candidate_area_km2": (
                outside_allocation.available_outside_area_km2
            ),
            "max_expansion_ring": int(outside_frame["expansion_ring"].max()),
            "selected_twh": float(combined.get("allocated_twh", pd.Series(dtype=float)).sum()),
        }
    )
    return combined, proposal_stats


def _solar_v1_stats(frame: pd.DataFrame, energy_model_state: dict[str, Any]) -> dict[str, float]:
    rooftop = energy_model_state.get("rooftop_solar")
    if not isinstance(rooftop, dict):
        return {
            "total_area_km2": 0.0,
            "mapped_area_km2": 0.0,
            "solar_area_need_km2": 0.0,
            "gross_solar_area_need_km2": 0.0,
            "covered_area_km2": 0.0,
            "covered_share_pct": 0.0,
            "remaining_area_km2": 0.0,
            "covered_twh": 0.0,
            "remaining_twh": 0.0,
            "population": 0.0,
            "mapped_population": 0.0,
        }
    panel_area_m2 = float(rooftop.get("panel_area_m2", 0.0) or 0.0)
    mapped_area_km2 = (
        float(
            pd.to_numeric(
                frame.get("solar_v1_area_km2", pd.Series(dtype=float)),
                errors="coerce",
            ).fillna(0.0).sum()
        )
        if not frame.empty
        else 0.0
    )
    gross_area_need = float(
        rooftop.get("gross_ground_area_need_km2", 0.0) or 0.0
    )
    remaining_area = float(
        rooftop.get("ground_area_need_km2", 0.0) or 0.0
    )
    covered_twh = float(
        rooftop.get("rooftop_contribution_twh", 0.0) or 0.0
    )
    gross_twh = float(rooftop.get("gross_solar_target_twh", 0.0) or 0.0)
    return {
        "total_area_km2": panel_area_m2 / 1_000_000.0,
        "mapped_area_km2": mapped_area_km2,
        "solar_area_need_km2": remaining_area,
        "gross_solar_area_need_km2": gross_area_need,
        "covered_area_km2": max(0.0, gross_area_need - remaining_area),
        "covered_share_pct": (
            covered_twh / gross_twh * 100.0 if gross_twh > 0 else 0.0
        ),
        "remaining_area_km2": remaining_area,
        "covered_twh": covered_twh,
        "remaining_twh": float(rooftop.get("ground_solar_twh", 0.0) or 0.0),
        "population": float(rooftop.get("population", 0.0) or 0.0),
        "mapped_population": float(
            rooftop.get("mapped_population", 0.0) or 0.0
        ),
    }


def _combined_establishment_stats(energy_model_state: dict[str, Any]) -> dict[str, float]:
    proposal_stats = energy_model_state.get("proposal_stats") if isinstance(energy_model_state, dict) else None
    solar_v1_stats = energy_model_state.get("solar_v1_stats") if isinstance(energy_model_state, dict) else None
    solar_proposal_stats = energy_model_state.get("solar_proposal_stats") if isinstance(energy_model_state, dict) else None
    wind_area_need = float(energy_model_state.get("wind_area_need_km2", 0.0) or 0.0)
    solar_area_need = float(energy_model_state.get("solar_area_need_km2", 0.0) or 0.0)
    wind_selected_area = float((proposal_stats or {}).get("selected_area_km2", 0.0) or 0.0) if isinstance(proposal_stats, dict) else 0.0
    wind_unmet_area = float((proposal_stats or {}).get("unmet_area_km2", wind_area_need) or 0.0) if isinstance(proposal_stats, dict) else wind_area_need
    if isinstance(solar_proposal_stats, dict):
        solar_v1_area = float(solar_proposal_stats.get("selected_area_km2", 0.0) or 0.0)
        solar_unmet_area = float(solar_proposal_stats.get("unmet_area_km2", max(0.0, solar_area_need - solar_v1_area)) or 0.0)
    else:
        solar_v1_area = 0.0
        solar_unmet_area = solar_area_need
    total_need = wind_area_need + solar_area_need
    total_covered = min(wind_selected_area, wind_area_need) + min(solar_v1_area, solar_area_need)
    return {
        "wind_selected_area_km2": wind_selected_area,
        "wind_unmet_area_km2": wind_unmet_area,
        "solar_v1_covered_area_km2": solar_v1_area,
        "solar_unmet_area_km2": solar_unmet_area,
        "total_need_area_km2": total_need,
        "total_covered_area_km2": total_covered,
        "total_covered_share_pct": (total_covered / total_need * 100.0) if total_need > 0 else 0.0,
    }


def _count_text(value: int | float) -> str:
    return f"{int(value):,}".replace(",", " ")


AREA_DISPLAY_UNITS = ["km²", "ha", "m²", "hex"]


def _format_measure_number(value: float, decimals: int = 0) -> str:
    return f"{float(value):,.{int(decimals)}f}".replace(",", " ")


def _format_area_primary(area_km2: float, unit: str, hex_area_km2: float = 0.0) -> str:
    area = max(0.0, float(area_km2 or 0.0))
    selected_unit = str(unit or "km²")
    hex_area = max(0.0, float(hex_area_km2 or 0.0))
    if selected_unit == "hex":
        if hex_area <= 0:
            return "0 hex"
        return f"{_format_measure_number(area / hex_area, 0)} hex"
    if selected_unit == "ha":
        return f"{_format_measure_number(area * 100.0, 0)} ha"
    if selected_unit == "m²":
        return f"{_format_measure_number(area * 1_000_000.0, 0)} m²"
    return f"{area:.2f} km²"


def _format_area_context(area_km2: float, unit: str, hex_area_km2: float = 0.0) -> str:
    area = max(0.0, float(area_km2 or 0.0))
    selected_unit = str(unit or "km²")
    hex_area = max(0.0, float(hex_area_km2 or 0.0))
    if selected_unit == "km²":
        return f"{_format_measure_number(area * 100.0, 0)} ha"
    if selected_unit == "ha":
        return f"{area:.2f} km²"
    if selected_unit == "m²":
        return f"{area:.2f} km²"
    if selected_unit == "hex" and hex_area > 0:
        return f"{area:.2f} km²"
    return ""


def _format_area_with_context(area_km2: float, unit: str, hex_area_km2: float = 0.0) -> str:
    primary = _format_area_primary(area_km2, unit, hex_area_km2)
    context = _format_area_context(area_km2, unit, hex_area_km2)
    return f"{primary} ({context})" if context else primary


def _percent_change(current: float, previous: float | None) -> float | None:
    if previous is None:
        return 0.0
    current_value = float(current or 0.0)
    previous_value = float(previous or 0.0)
    if abs(previous_value) < 1e-9:
        return 0.0 if abs(current_value) < 1e-9 else None
    return (current_value - previous_value) / abs(previous_value) * 100.0


def _change_delta_text(current: float, previous: float | None) -> str | None:
    if previous is not None and abs(float(previous or 0.0)) < 1e-9 and abs(float(current or 0.0)) >= 1e-9:
        return _t("+nytt")
    change = _percent_change(current, previous)
    if change is None:
        return None
    if abs(change) < 0.05:
        return "0.0%"
    return f"{change:+.1f}%"


def _change_delta_color(current: float, previous: float | None) -> str:
    if previous is not None and abs(float(previous or 0.0)) < 1e-9 and abs(float(current or 0.0)) >= 1e-9:
        return "normal"
    change = _percent_change(current, previous)
    if change is None or abs(change) < 0.05:
        return "off"
    return "normal"


def _change_badge_html(current: float, previous: float | None) -> str:
    if previous is not None and abs(float(previous or 0.0)) < 1e-9 and abs(float(current or 0.0)) >= 1e-9:
        return (
            "<span style='display:inline-block;margin-top:0.12rem;padding:0.08rem 0.32rem;"
            "border-radius:999px;background:#dcfce7;color:#15803d;font-size:0.72rem;font-weight:650;"
            f"white-space:nowrap;'>↑ {html.escape(_t('nytt'))}</span>"
        )
    change = _percent_change(current, previous)
    if change is None:
        return ""
    if abs(change) < 0.05:
        arrow = "→"
        text = "0.0%"
        color = "#92400e"
        background = "#fef3c7"
    elif change > 0:
        arrow = "↑"
        text = f"{change:.1f}%"
        color = "#15803d"
        background = "#dcfce7"
    else:
        arrow = "↓"
        text = f"{abs(change):.1f}%"
        color = "#b91c1c"
        background = "#fee2e2"
    return (
        f"<span style='display:inline-block;margin-top:0.12rem;padding:0.08rem 0.32rem;"
        f"border-radius:999px;background:{background};color:{color};font-size:0.72rem;font-weight:650;"
        f"white-space:nowrap;'>{arrow} {text}</span>"
    )


def _value_with_change_html(value: str, current: float, previous: float | None) -> str:
    return (
        "<div style='display:flex;flex-direction:column;align-items:flex-start;gap:0.04rem;'>"
        f"<span>{html.escape(str(value))}</span>"
        f"{_change_badge_html(current, previous)}"
        "</div>"
    )


def _establishment_change_snapshot_key(energy_model_state: dict[str, Any]) -> str:
    region_id = str(energy_model_state.get("region_id", "region") or "region")
    return f"establishment_change_snapshot_{region_id}"


def _snapshot_fingerprint(snapshot: dict[str, float]) -> tuple[tuple[str, float], ...]:
    return tuple((str(key), round(float(value or 0.0), 9)) for key, value in sorted(snapshot.items()))


def _previous_snapshot_value(snapshot: dict[str, Any], key: str) -> float | None:
    if key not in snapshot:
        return None
    try:
        return float(snapshot.get(key))
    except Exception:
        return None


def _render_impact_change_table(
    rows: list[dict[str, str]], *, quantity_label: str = "energi",
) -> None:
    if not rows:
        return
    headers = [
        "teknik",
        "energi",
        "ytbehov",
        "potential efter filter",
        "potential efter acceptanspåverkan",
        "inom potential",
        "outnyttjad potential",
        "ytbehov utanför potential",
        "andel inom potential",
    ]

    def _header_html(header: str) -> str:
        if header == "energi":
            return html.escape(_t(quantity_label))
        wrapped_headers = {
            "potential efter filter": "potential<br>efter filter",
            "potential efter acceptanspåverkan": "potential<br>efter acceptans-<br>påverkan",
            "inom potential": "inom<br>potential",
            "outnyttjad potential": "outnyttjad<br>potential",
            "ytbehov utanför potential": "ytbehov utanför<br>potential",
            "andel inom potential": "andel inom<br>potential",
        }
        if header not in wrapped_headers:
            return html.escape(_t(header))
        return html.escape(_t(header)).replace(" ", "<wbr> ")

    header_classes = {
        "teknik": "change-col-tech",
        "energi": "change-col-energy",
        "ytbehov": "change-col-area",
        "potential efter filter": "change-col-filter",
        "potential efter acceptanspåverkan": "change-col-acceptance",
        "inom potential": "change-col-area",
        "outnyttjad potential": "change-col-unused",
        "ytbehov utanför potential": "change-col-outside",
        "andel inom potential": "change-col-share",
    }
    colgroup_html = (
        "<colgroup>"
        + "".join(f"<col class='{header_classes.get(header, 'change-col-value')}'>" for header in headers)
        + "</colgroup>"
    )
    header_html = "".join(
        f"<th class='{header_classes.get(header, 'change-col-value')}'>{_header_html(header)}</th>"
        for header in headers
    )
    row_html = ""
    for row in rows:
        row_html += (
            "<tr>"
            + "".join(
                f"<td class='{header_classes.get(header, 'change-col-value')}'>{html.escape(_t(row.get(header, ''))) if header == 'teknik' else row.get(header, '')}</td>"
                for header in headers
            )
            + "</tr>"
        )
    st.markdown(
        "<div class='change-table-wrap' data-potential-tutorial-anchor='results-table' data-workspace-guide='results'>"
        "<table class='change-table'>"
        f"{colgroup_html}"
        "<thead><tr>"
        f"{header_html}"
        "</tr></thead><tbody>"
        f"{row_html}"
        "</tbody></table></div>"
        "<style>"
        ".change-table-wrap{display:block;width:100%;max-width:100%;overflow-x:auto;border:1px solid rgba(49,51,63,0.14);border-radius:6px;margin-top:0.35rem;}"
        ".change-table{width:100%;min-width:645px;border-collapse:collapse;font-size:0.68rem;line-height:1.12;table-layout:fixed;}"
        ".change-table .change-col-tech{width:6%;}"
        ".change-table .change-col-energy{width:10%;}"
        ".change-table .change-col-area{width:10%;}"
        ".change-table .change-col-filter{width:13%;}"
        ".change-table .change-col-acceptance{width:15%;}"
        ".change-table .change-col-unused{width:13%;}"
        ".change-table .change-col-outside{width:13%;}"
        ".change-table .change-col-share{width:10%;}"
        ".change-table th{background:#f8fafc;color:#475569;text-align:left;font-weight:600;padding:0.22rem 0.3rem;border-bottom:1px solid rgba(49,51,63,0.12);white-space:normal;overflow-wrap:anywhere;line-height:1.12;}"
        ".change-table td{padding:0.22rem 0.3rem;border-top:1px solid rgba(49,51,63,0.08);vertical-align:top;white-space:normal;overflow-wrap:anywhere;}"
        ".change-table td div{gap:0!important;min-width:0;}"
        ".change-table td span:first-child{white-space:nowrap;}"
        "@media (max-width:900px){.change-table{font-size:0.66rem;}.change-table-wrap{width:100%;}}"
        "</style>",
        unsafe_allow_html=True,
    )


def _format_hex_size_caption(h3_resolution: int | None, hex_area_km2: float) -> str:
    area = max(0.0, float(hex_area_km2 or 0.0))
    resolution_label = f"R{int(h3_resolution)}" if h3_resolution is not None else _t("vald H3")
    return (
        f"1 {resolution_label}-hex ≈ {area:.4f} km² = "
        f"{area * 100.0:.2f} ha = {_format_measure_number(area * 1_000_000.0, 0)} m²."
    )


def _outside_need_stats_from_areas(wind_area_km2: float, solar_area_km2: float, hex_area_km2: float) -> dict[str, float]:
    hex_area = max(float(hex_area_km2 or 0.0), 1e-9)
    wind_area = max(0.0, float(wind_area_km2 or 0.0))
    solar_area = max(0.0, float(solar_area_km2 or 0.0))
    if wind_area < OUTSIDE_LP_NEED_DISPLAY_MIN_KM2:
        wind_area = 0.0
    if solar_area < OUTSIDE_LP_NEED_DISPLAY_MIN_KM2:
        solar_area = 0.0
    wind_count = int(math.ceil(wind_area / hex_area)) if wind_area > 0 else 0
    solar_count = int(math.ceil(solar_area / hex_area)) if solar_area > 0 else 0
    return {
        "wind_hex_count": wind_count,
        "solar_hex_count": solar_count,
        "both_hex_count": 0,
        "total_shortage_hex_count": wind_count + solar_count,
        "wind_area_km2": wind_area,
        "solar_area_km2": solar_area,
        "hex_area_km2": float(hex_area_km2 or 0.0),
    }


def _render_shortage_hex_stack_card(stats: dict[str, Any], unit: str = "km²") -> None:
    total_count = int(stats.get("total_shortage_hex_count", 0) or 0)
    wind_count = int(stats.get("wind_hex_count", 0) or 0)
    solar_count = int(stats.get("solar_hex_count", 0) or 0)
    both_count = int(stats.get("both_hex_count", 0) or 0)
    wind_area = float(stats.get("wind_area_km2", 0.0) or 0.0)
    solar_area = float(stats.get("solar_area_km2", 0.0) or 0.0)
    hex_area = float(stats.get("hex_area_km2", 0.0) or 0.0)
    max_count = max(total_count, wind_count, solar_count, 1)
    symbol_scale = max(1, int(math.ceil(max_count / 64)))

    def _hex_symbols(count: int, fill: str) -> str:
        symbol_count = int(math.ceil(max(0, count) / symbol_scale)) if count > 0 else 0
        hexes = "".join(
            f"<span style='display:inline-block;width:0.46rem;height:0.40rem;margin:0.035rem;background:{fill};"
            "border:1px solid #111111;clip-path:polygon(25% 0,75% 0,100% 50%,75% 100%,25% 100%,0 50%);'></span>"
            for _ in range(min(symbol_count, 64))
        )
        if symbol_count > 64:
            hexes += "<span style='font-size:0.72rem;color:#6b7280;margin-left:0.2rem;'>+</span>"
        return hexes or f"<span style='font-size:0.74rem;color:#6b7280;'>{html.escape(_t('Inga bristhex'))}</span>"

    def _row(label: str, count: int, area: float, accent: str) -> str:
        area_text = _format_area_with_context(area, unit, hex_area)
        outside_text = _t("{p0} utanför landskapets potential", p0=area_text)
        return (
            "<div style='border-left:4px solid "
            f"{accent};padding:0.42rem 0.5rem;margin:0.35rem 0;border-radius:6px;"
            "background:rgba(255,255,255,0.68);border-top:1px solid rgba(49,51,63,0.12);"
            "border-right:1px solid rgba(49,51,63,0.12);border-bottom:1px solid rgba(49,51,63,0.12);'>"
            "<div style='display:flex;justify-content:space-between;gap:0.5rem;font-size:0.82rem;font-weight:700;'>"
            f"<span>{html.escape(_t(label))}</span><span>{_count_text(count)} hex</span></div>"
            f"<div style='font-size:0.74rem;color:#6b7280;margin:0.08rem 0 0.25rem;'>{html.escape(outside_text)}</div>"
            f"<div style='line-height:0.5rem;'>{_hex_symbols(count, accent)}</div>"
            "</div>"
        )

    with st.container(border=True):
        st.markdown(
            f"<div style='font-size:0.86rem;font-weight:750;margin-bottom:0.2rem;'>{html.escape(_t(OUTSIDE_LP_NEED_LAYER_LABEL))}</div>"
            "<div style='font-size:0.75rem;color:#6b7280;margin-bottom:0.35rem;'>"
            + html.escape(_t("Samma ytbudget visas schematiskt i separata fält utanför regionen, inte som faktisk placering."))
            + "</div>"
            + _row("Vind behöver yta", wind_count, wind_area, ESTABLISHMENT_CLASS_SPECS["wind_only"]["color"])
            + _row("Sol behöver yta", solar_count, solar_area, ESTABLISHMENT_CLASS_SPECS["solar_only"]["color"])
            + (
                f"<div style='font-size:0.74rem;color:#6b7280;margin-top:0.2rem;'>"
                + html.escape(_t("Unika ytbehovshex: {p0}. Både vind och sol i samma hex: {p1}. 1 symbol ≈ {p2} hex.",
                                 p0=_count_text(total_count), p1=_count_text(both_count), p2=_count_text(symbol_scale)))
                + "</div>"
            ),
            unsafe_allow_html=True,
        )


def _wind_source_frame(
    landscape_manifest: dict[str, Any],
    solar_rules: dict[str, Any],
    ui_params: dict[str, float],
    group_layer_selection: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    return wind_acceptance_potential_frame(
        landscape_manifest,
        _class_breaks(solar_rules),
        _wind_score_params_from_ui(ui_params),
        ui_params,
        group_layer_map=group_layer_selection,
    )


def _wind_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    solar_rules: dict[str, Any],
    resolution: int,
    ui_params: dict[str, float],
    group_layer_selection: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    base = _wind_source_frame(landscape_manifest, solar_rules, ui_params, group_layer_selection=group_layer_selection)
    frame = wind_acceptance_rollup_frame(base, resolution, _class_breaks(solar_rules))
    return _filter_frame_to_display_geometries(frame, _h3_display_geometry_path(region, resolution))


@st.cache_data(show_spinner=False)
def _landscape_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    resolution: int,
) -> pd.DataFrame:
    if catalog_context_runtime_declared(str(region["region_id"])):
        runtime = load_catalog_context_inputs(str(region["region_id"]))
        snapshot = runtime.landscape
        # This helper serves numerical compatibility consumers. An optional
        # display classification does not authorize technology ranking fields.
        has_technology_context = any(
            field.field_id in TECHNOLOGY_CONTEXT_COLUMNS
            for cell in runtime.technology_context.cells
            for field in cell.values
        )
        if snapshot is None or not has_technology_context:
            return pd.DataFrame(columns=["hex_id", "class_km", "landscape_type"])
        frame = landscape_frame_for_resolution_from_frame(landscape_manifest, resolution,
            landscape_frame_from_records(snapshot.source_records()))
    else:
        frame = landscape_frame_for_resolution(landscape_manifest, resolution)
    return _filter_frame_to_display_geometries(frame, _h3_display_geometry_path(region, resolution))


def _technology_landscape_context_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    resolution: int,
) -> pd.DataFrame:
    """Resolve optional LABLAB context on the technology support domain."""

    if catalog_context_runtime_declared(str(region["region_id"])):
        snapshot = load_catalog_context_inputs(str(region["region_id"])).technology_context
        records = [{"hex_id": cell.cell_id,
                    **{field.field_id: field.value for field in cell.values}}
                   for cell in snapshot.cells]
        if not any(field in record for record in records for field in TECHNOLOGY_CONTEXT_COLUMNS):
            return pd.DataFrame(columns=["hex_id"])
        ids_sha = hashlib.sha256("".join(f"{cell.cell_id}\n" for cell in snapshot.cells).encode()).hexdigest()
        frame = technology_context_frame_from_records(landscape_manifest, int(resolution), records,
            source_signature=(snapshot.source_sha256, len(records), ids_sha))
    else:
        frame = technology_context_frame_for_resolution(landscape_manifest, int(resolution))
    if frame.empty:
        return frame
    return _filter_frame_to_display_geometries(
        frame,
        _area_display_geometry_path(region, int(resolution)),
    )


def _solar_legend_items(solar_rules: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"label": str(item.get("label", item.get("id", "Okänd"))), "color": str(item.get("color", "#999999"))}
        for item in _solar_class_breaks_for_display(solar_rules)
    ]


def _solar_class_breaks_for_display(solar_rules: dict[str, Any]) -> list[dict[str, Any]]:
    breaks = [dict(item) for item in _class_breaks(solar_rules)]
    palette = {
        "very_low": "#991b1b",
        "low": "#f87171",
        "medium": "#fef08a",
        "high": "#facc15",
        "very_high": "#ca8a04",
    }
    for item in breaks:
        class_id = str(item.get("id", ""))
        if class_id in palette:
            item["color"] = palette[class_id]
    return breaks


def _solar_rules_with_display_palette(solar_rules: dict[str, Any]) -> dict[str, Any]:
    rules = read_manifest(str(resolve_repo_path(solar_rules.get("_manifest_path")))) if solar_rules.get("_manifest_path") else solar_rules.copy()
    rules = {
        **rules,
        "score_model": {
            **(rules.get("score_model") or {}),
            "cluster_terms": [dict(item) for item in (rules.get("score_model") or {}).get("cluster_terms") or []],
            "role_terms": [dict(item) for item in (rules.get("score_model") or {}).get("role_terms") or []],
        },
    }
    rules["score_model"]["class_breaks"] = _solar_class_breaks_for_display(rules)
    return rules


def _default_wind_params() -> dict[str, float]:
    return {
        WIND_POPULATION_PARAM_KEY: 100.0,
        "road_distance_m": 100.0,
        "grid_max_distance_m": 2000.0,
        "protected_buffer_m": 0.0,
        "coastal_buffer_m": 0.0,
        "culture_buffer_m": 0.0,
        "reindeer_buffer_m": 0.0,
        "aviation_approach_buffer_m": 0.0,
        "aviation_bird_distance_m": 0.0,
        "military_buffer_m": 0.0,
        "landscape_sensitivity_percent": 60.0,
    }


def _reference_default_wind_params() -> dict[str, float]:
    params = _default_wind_params()
    params.update(
        {
            WIND_POPULATION_PARAM_KEY: 500.0,
            "road_distance_m": 300.0,
            "grid_max_distance_m": 1000.0,
            "protected_buffer_m": 250.0,
            "culture_buffer_m": 100.0,
            "reindeer_buffer_m": 100.0,
        }
    )
    return params


def _reference_default_wind_layer_selection(
    region_id: str,
) -> dict[str, list[str]]:
    normalized_region_id = _wind_region_id(region_id)
    population_layer_ids = canonical_wind_group_layer_ids(
        normalized_region_id,
        CANONICAL_POPULATION_GROUP_ID,
    )
    if not population_layer_ids:
        raise ValueError(
            f"{normalized_region_id}/wind declares no canonical population "
            "layers"
        )
    return normalize_group_layer_map(
        {
            WIND_POPULATION_GROUP_ID: [population_layer_ids[0]],
            WIND_ROADS_GROUP_ID: list(
                canonical_wind_group_layer_ids(
                    normalized_region_id,
                    CANONICAL_ROADS_GROUP_ID,
                )
            ),
            "electrical": [],
            WIND_NATURE_GROUP_ID: list(
                canonical_wind_group_layer_ids(
                    normalized_region_id,
                    CANONICAL_NATURE_GROUP_ID,
                )
            ),
            "coastal": [],
            WIND_CULTURE_GROUP_ID: list(
                canonical_wind_group_layer_ids(
                    normalized_region_id,
                    CANONICAL_CULTURE_GROUP_ID,
                )
            ),
            "reindeer": [
                layer_id
                for layer_id in ("reindeer_grazing_merged",)
                if layer_id in WIND_GROUP_LAYER_DEFAULTS.get(WIND_REINDEER_GROUP_ID, [])
            ],
            "aviation_approach": [],
            "aviation_bird": [],
            "military": [],
        },
        normalized_region_id,
    )


def _apply_reference_default_wind_to_controls() -> None:
    params = _reference_default_wind_params()
    region_id = _wind_region_id()
    selected = _reference_default_wind_layer_selection(region_id)
    st.session_state[WIND_LAYER_SELECTION_KEY] = selected
    for group in _wind_control_groups(region_id):
        group_id = str(group.id)
        layer_ids = _wind_control_layers(region_id, group)
        param_key = _wind_group_param_key(group_id)
        group_param_value = params.get(param_key) if param_key else None
        if group_param_value is not None:
            st.session_state[_wind_control_key("analysis", group_id)] = int(round(float(group_param_value)))
        selected_ids = set(selected.get(group_id, []))
        for layer_id in layer_ids:
            st.session_state[_wind_control_key("layer", layer_id.id)] = (
                layer_id.id in selected_ids
            )
    for group_id in selected:
        group_enabled = bool(selected.get(group_id))
        st.session_state[_wind_control_key("group", group_id)] = group_enabled
        st.session_state[
            _wind_control_key("group_sync", group_id)
        ] = group_enabled


def _wind_score_params_from_ui(ui_params: dict[str, float]) -> dict[str, float]:
    return {
        "base_score": 55.0,
        "everyday_matrix_bonus": 12.0,
        "infrastructure_bonus": min(float(ui_params["grid_max_distance_m"]) / 15000.0, 1.0) * 18.0,
        "settlement_penalty": min(float(ui_params[WIND_POPULATION_PARAM_KEY]) / 3000.0, 1.0) * 35.0,
        "road_penalty": min(float(ui_params["road_distance_m"]) / 2000.0, 1.0) * 12.0,
        "protected_penalty": 10.0 + min(float(ui_params["protected_buffer_m"]) / 2000.0, 1.0) * 25.0,
        "coastal_penalty": 8.0 + min(float(ui_params["coastal_buffer_m"]) / 1000.0, 1.0) * 18.0,
        "terrain_penalty": 10.0,
        "landscape_sensitivity": max(0.0, min(2.0, float(ui_params["landscape_sensitivity_percent"]) / 60.0)),
        "factor_positive_cap": 2.0,
    }


def _render_html_map(map_html: str, height: int = 820) -> None:
    iframe = getattr(st, "iframe", None)
    if callable(iframe):
        iframe(map_html, width="stretch", height=height)
        return
    if components is None:
        st.error(
            _t("Kartan kan inte renderas med den installerade Streamlit-versionen. "
            "Uppgradera Streamlit eller använd en version med st.iframe.")
        )
        return
    components.html(map_html, height=height)


def _render_gate1_review(query_region: str | None) -> None:
    st.title("Gate 1 · region och geografi")
    st.caption(
        "Gemensam, skrivskyddad localhost-granskning av de tre korta "
        "regionprofilerna, deras identitetsgränser och checksum-pinnade "
        "PostGIS-analysytor."
    )
    requested_region_id = str(query_region or "").strip().lower()
    if requested_region_id and requested_region_id not in DELIVERY_REGION_IDS:
        st.error(
            "Gate 1 kunde inte öppnas: den explicit angivna regionen "
            f"{requested_region_id!r} finns inte i den validerade "
            "tre-regionsleveransen."
        )
        return
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        st.error("Gate 1 kan inte granskas eftersom DATABASE_URL saknas.")
        return
    try:
        reviews = load_gate1_region_reviews(REPO_ROOT, database_url)
    except Exception as exc:
        st.error(f"Gate 1 kunde inte läsas fail-closed: {exc}")
        return
    review_by_id = {review.region_id: review for review in reviews}
    region_ids = tuple(review_by_id)
    if requested_region_id and requested_region_id not in review_by_id:
        st.error(
            "Gate 1 kunde inte öppnas: den explicit angivna regionen "
            f"{requested_region_id!r} finns inte i den validerade "
            "tre-regionsleveransen."
        )
        return
    query_region_id = requested_region_id or None
    default_region_id = query_region_id or region_ids[0]
    review_region_key = "gate1_review_region"
    query_region_state_key = "gate1_review_query_region"
    if (
        query_region_id is not None
        and st.session_state.get(query_region_state_key) != query_region_id
    ):
        st.session_state[review_region_key] = query_region_id
        st.session_state[query_region_state_key] = query_region_id
    segmented_kwargs: dict[str, Any] = {}
    if review_region_key not in st.session_state:
        segmented_kwargs["default"] = default_region_id
    selected_region_id = st.segmented_control(
        "Region",
        region_ids,
        required=True,
        format_func=lambda region_id: review_by_id[str(region_id)].name,
        key=review_region_key,
        width="stretch",
        **segmented_kwargs,
        persist_state="session",
    )
    selected = review_by_id[str(selected_region_id)]

    approved_count = sum(
        review.gate_state == "localhost_approved" for review in reviews
    )
    if approved_count == len(reviews):
        st.success("Gate 1 är localhost-godkänd för alla tre regioner.")
    elif approved_count:
        st.warning(
            f"Gate 1 är localhost-godkänd för {approved_count} av "
            f"{len(reviews)} regioner. Övriga är endast automatiskt validerade."
        )
    else:
        st.info(
            "Alla tre regioner är automatiskt validerade. Det här är "
            "granskningsunderlaget; inget localhost-godkännande eller "
            "produktaktivering har gjorts."
        )

    status_rows = [
        {
            "Region": review.name,
            "Land": review.country_code,
            "Databasschema": review.database_schema,
            "Identitetsvy": review.boundary_view,
            "Analysvy": review.analysis_surface_view,
            "Gate 1": review.gate_state,
            "CRS": review.native_crs,
            "Identitetsyta (km²)": round(review.boundary_area_km2, 2),
            "Analysyta (km²)": round(review.analysis_surface_area_km2, 2),
            "Källrelation": (
                "Samma granskade källa"
                if review.identity_analysis_same_source
                else "Separat härledd analysyta"
            ),
        }
        for review in reviews
    ]
    st.dataframe(
        _display_dataframe(pd.DataFrame(status_rows)),
        hide_index=True,
        key="gate1_region_status",
    )

    with st.container(border=True):
        st.subheader(selected.name)
        metric_columns = st.columns(4, vertical_alignment="center")
        metric_columns[0].metric("Regionalt CRS", selected.native_crs)
        metric_columns[1].metric(
            "Identitetsyta",
            f"{selected.boundary_area_km2:,.2f} km²",
        )
        metric_columns[2].metric(
            "Analysyta",
            f"{selected.analysis_surface_area_km2:,.2f} km²",
        )
        metric_columns[3].metric(
            "Vattenpolicy",
            {
                "exclude_all_water": "Karterade vattenytor borttagna",
                "exclude_sea_retain_inland_water": "Hav borttaget",
                "include_water": "Vatten inkluderat",
            }.get(
                selected.analysis_surface_water_policy,
                selected.analysis_surface_water_policy or "Ej deklarerad",
            ),
        )
        st.caption(
            f"Identitet: {selected.boundary_label} "
            f"({selected.database_schema}.{selected.boundary_view})."
        )
        st.caption(
            f"Analys: {selected.analysis_surface_label} "
            f"({selected.database_schema}.{selected.analysis_surface_view})."
        )
        if (
            selected.identity_analysis_same_source
            and selected.identity_analysis_same_geometry
        ):
            st.caption(
                "Identitets- och analysytan använder avsiktligt samma "
                "checksumspinnade, granskade geometri."
            )
        else:
            st.caption(
                "Analysytan är härledd separat från identitetsgränsen. "
                f"Exkluderad yta: "
                f"{selected.observed_excluded_area_m2 / 1_000_000.0:,.2f} km²."
            )
        st.caption(
            "Granskningsunderlag: commit "
            f"{selected.review_commit[:12]} · evidens "
            f"{selected.automated_evidence_sha256[:12]}."
        )
        if selected.gate_state == "localhost_approved":
            st.caption(
                "Ägargodkänd "
                f"{selected.owner_reviewed_at.isoformat()} · "
                f"{selected.owner_review_note}"
            )

        boundary_map = folium.Map(tiles="OpenStreetMap", control_scale=True)
        boundary_layer = folium.GeoJson(
            data=dict(selected.boundary_geometry),
            name="Identitetsgräns",
            style_function=lambda _feature: {
                "color": "#b42318",
                "weight": 3,
                "fillOpacity": 0.0,
            },
        )
        boundary_layer.add_to(boundary_map)
        analysis_layer = folium.GeoJson(
            data=dict(selected.analysis_surface_geometry),
            name="Analysyta",
            style_function=lambda _feature: {
                "color": "#067647",
                "weight": 1.5,
                "fillColor": "#12b76a",
                "fillOpacity": 0.28,
            },
        )
        analysis_layer.add_to(boundary_map)
        folium.LayerControl(collapsed=False).add_to(boundary_map)
        boundary_map.fit_bounds(boundary_layer.get_bounds(), padding=(20, 20))
        _render_html_map(boundary_map.get_root().render(), height=620)

    details = st.expander("Teknisk integritet", on_change="rerun")
    if details.open:
        with details:
            st.code(
                "\n".join(
                    (
                        f"profile_sha256={selected.profile_sha256}",
                        f"geography_sha256={selected.geography_sha256}",
                        f"boundary_sha256={selected.boundary_sha256}",
                        "analysis_surface_sha256="
                        f"{selected.analysis_surface_sha256}",
                        "analysis_surface_water_policy="
                        f"{selected.analysis_surface_water_policy}",
                        "identity_binding_status="
                        f"{selected.identity_binding_status}",
                        "analysis_surface_binding_status="
                        f"{selected.analysis_surface_binding_status}",
                        "identity_analysis_source_relation="
                        f"{selected.identity_analysis_source_relation}",
                        "identity_analysis_same_geometry="
                        f"{selected.identity_analysis_same_geometry}",
                        "boundary_geometry_sha256="
                        f"{selected.boundary_geometry_sha256}",
                        "analysis_surface_geometry_sha256="
                        f"{selected.analysis_surface_geometry_sha256}",
                        "observed_outside_identity_m2="
                        f"{selected.observed_outside_identity_m2}",
                        "observed_excluded_area_m2="
                        f"{selected.observed_excluded_area_m2}",
                        f"review_commit={selected.review_commit}",
                        "automated_evidence_sha256="
                        f"{selected.automated_evidence_sha256}",
                        f"gate_state={selected.gate_state}",
                    )
                ),
                language="text",
            )


def _render_gate2_review(query_region: str | None) -> None:
    st.title("Gate 2 · datakällor och PostGIS-vyer")
    st.caption(
        "Gemensam, skrivskyddad localhostgranskning av standardiserade "
        "källvyer för alla fem landskapsgrupper. Leveransurvalet kommer "
        "från regionprofilerna; hela inventeringen finns kvar som underlag."
    )
    requested_region_id = str(query_region or "").strip().lower()
    if requested_region_id and requested_region_id not in DELIVERY_REGION_IDS:
        st.error(
            "Gate 2 kunde inte öppnas: regionen "
            f"{requested_region_id!r} ingår inte i tre-regionsleveransen."
        )
        return
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        st.error("Gate 2 kan inte granskas eftersom DATABASE_URL saknas.")
        return
    requested_scope = str(_query_param_value("scope") or "inventory").strip().lower()
    if requested_scope not in {"inventory", "delivery"}:
        st.error("Gate 2 kunde inte öppnas: okänt granskningsurval.")
        return
    scope_key = "gate2_review_delivery_only"
    scope_query_key = "gate2_review_query_scope"
    if st.session_state.get(scope_query_key) != requested_scope:
        st.session_state[scope_key] = requested_scope == "delivery"
        st.session_state[scope_query_key] = requested_scope
    delivery_only = st.toggle(
        "Visa endast leveransurvalet",
        key=scope_key,
        help="Urvalet är sparat i regionprofilerna. Reglaget ändrar bara granskningen.",
        persist_state="session",
    )
    current_scope = "delivery" if delivery_only else "inventory"
    if current_scope != requested_scope:
        _set_query_param("scope", current_scope)
        st.session_state[scope_query_key] = current_scope
    try:
        catalogs = load_gate2_source_catalogs(REPO_ROOT, delivery_only=delivery_only)
    except Exception as exc:
        st.error(f"Gate 2-katalogerna kunde inte läsas fail-closed: {exc}")
        return
    catalog_by_id = {catalog.region_id: catalog for catalog in catalogs}
    names = {
        region_id: load_region_profile(REPO_ROOT, region_id).name
        for region_id in catalog_by_id
    }
    region_ids = tuple(catalog_by_id)
    default_region_id = requested_region_id or region_ids[0]
    review_region_key = "gate2_review_region"
    query_region_state_key = "gate2_review_query_region"
    if (
        requested_region_id
        and st.session_state.get(query_region_state_key) != requested_region_id
    ):
        st.session_state[review_region_key] = requested_region_id
        st.session_state[query_region_state_key] = requested_region_id
    segmented_kwargs: dict[str, Any] = {}
    if review_region_key not in st.session_state:
        segmented_kwargs["default"] = default_region_id
    selected_region_id = str(
        st.segmented_control(
            "Region",
            region_ids,
            required=True,
            format_func=lambda region_id: names[str(region_id)],
            key=review_region_key,
            width="stretch",
            **segmented_kwargs,
            persist_state="session",
        )
    )
    selected_catalog = catalog_by_id[selected_region_id]
    candidate_group_ids = tuple(
        group.id for group in selected_catalog.groups if group.status == "candidate"
    )
    requested_group_id = str(_query_param_value("group") or "").strip().lower()
    if requested_group_id and requested_group_id not in candidate_group_ids:
        st.error(
            "Gate 2 kunde inte öppnas: gruppen "
            f"{requested_group_id!r} är inte granskningsbar för regionen."
        )
        return

    st.info(
        "Granskningen gäller källurval och geometri. "
        "Den godkänner inte nya buffertar eller beräkningar och aktiverar ingen region."
    )
    if delivery_only:
        selected_count = sum(len(group.sources) for catalog in catalogs for group in catalog.groups)
        st.caption(
            f"Leveransurval: {selected_count} källor i tre regioner och fem grupper per region. "
            "Blockerade eller enbart interna källor ingår inte."
        )
    status_labels = {
        "candidate": "Kandidat för granskning",
        "pending_inventory": "Inventering återstår",
        "unavailable": "Data saknas",
    }
    group_labels = {
        "roads": "Vägar",
        "population": "Befolkning och bebyggelse",
        "nature": "Natur",
        "culture": "Kulturmiljöer",
        "grid_infrastructure": "Elinfrastruktur",
    }
    group_key = "gate2_review_group"
    query_group_state_key = "gate2_review_query_group"
    if (
        requested_group_id
        and st.session_state.get(query_group_state_key) != requested_group_id
    ):
        st.session_state[group_key] = requested_group_id
        st.session_state[query_group_state_key] = requested_group_id
    if st.session_state.get(group_key) not in candidate_group_ids:
        st.session_state[group_key] = requested_group_id or candidate_group_ids[0]
    selected_group_id = str(
        st.segmented_control(
            "Landskapsgrupp",
            candidate_group_ids,
            required=True,
            format_func=lambda group_id: group_labels[str(group_id)],
            key=group_key,
            width="stretch",
            persist_state="session",
        )
    )
    try:
        _catalogs, source_reviews = load_gate2_source_reviews(
            REPO_ROOT,
            database_url,
            region_id=selected_region_id,
            group_id=selected_group_id,
            delivery_only=delivery_only,
        )
        region_bounds = load_gate2_region_bounds(
            REPO_ROOT,
            database_url,
            region_id=selected_region_id,
        )
    except Exception as exc:
        st.error(f"Gate 2 kunde inte läsas fail-closed: {exc}")
        return
    selected_sources = tuple(
        review
        for review in source_reviews
        if review.region_id == selected_region_id
        and review.group_id == selected_group_id
    )
    status_rows = []
    for catalog in catalogs:
        for group in catalog.groups:
            status_rows.append(
                {
                    "Region": names[catalog.region_id],
                    "Grupp": group_labels[group.id],
                    "Status": status_labels[group.status],
                    "Källor": len(group.sources),
                    "Kommentar": "Valt i regionprofilen" if delivery_only else (group.reason or ""),
                }
            )
    st.dataframe(
        _display_dataframe(pd.DataFrame(status_rows)),
        hide_index=True,
        key="gate2_group_status",
    )

    if any(
        source.public_display_status == "blocked" for source in selected_sources
    ):
        st.warning(
            "Källgeometrin visas endast i denna interna localhostgranskning. "
            "Publik visning är spärrad tills exakt licens och snapshot är "
            "verifierade."
        )
    elif any(
        source.public_display_status == "local_review_only"
        for source in selected_sources
    ):
        st.warning(
            "Minst en källa är enligt sitt manifest begränsad till intern "
            "localhostgranskning och exponeras inte som ett publikt rådatalager."
        )
    else:
        st.success(
            "Den lokala leveransen innehåller verifierad licensinformation för "
            "dessa granskningskällor."
        )

    with st.container(border=True):
        st.subheader(
            f"{names[selected_region_id]} · {group_labels[selected_group_id]}"
        )
        source_rows = [
            {
                "Lager": source.label,
                "PostGIS-vy": (
                    f"{source.database_schema}.{source.database_view}"
                ),
                "Källa": f"{source.authority} – {source.dataset}",
                "Urval": source.selection,
                "Snapshot": source.snapshot_date or "Ej verifierad",
                "Licens": source.license_name or "Ej verifierad",
                "Licensstatus": source.license_status,
                "Visning": source.public_display_status,
                "Källobjekt": source.source_feature_count,
                "Importerade features": source.asset_feature_count,
                "Geometri": source.geometry_family,
                "Representation": source.data_representation,
            }
            for source in selected_sources
        ]
        st.dataframe(
            _display_dataframe(pd.DataFrame(source_rows)),
            hide_index=True,
            key="gate2_source_status",
        )
        st.markdown("**Lager som visas**")
        st.caption(
            "Kryssa i de källor som ska visas. Valet påverkar bara "
            "granskningskartan."
        )
        visible_source_ids: set[str] = set()
        with st.container(horizontal=True):
            for source in selected_sources:
                if st.checkbox(
                    source.label,
                    value=True,
                    key=(
                        f"gate2_map_layer_{selected_region_id}_"
                        f"{selected_group_id}_{source.source_id}"
                    ),
                    persist_state="session",
                ):
                    visible_source_ids.add(source.source_id)
        source_map = folium.Map(tiles="OpenStreetMap", control_scale=True)
        group_palettes = {
            "roads": ("#855913", "#b18421", "#d4a72c", "#f2c14e"),
            "population": ("#7f3c8d", "#0f766e", "#2563eb", "#d97706"),
            "nature": (
                "#14532d",
                "#7e22ce",
                "#65a30d",
                "#15803d",
                "#db2777",
                "#ea580c",
                "#0891b2",
            ),
        }
        palette = group_palettes.get(
            selected_group_id,
            ("#475569", "#0f766e", "#2563eb", "#d97706"),
        )
        colors = {
            source.source_id: palette[index % len(palette)]
            for index, source in enumerate(selected_sources)
        }
        for source in selected_sources:
            if source.source_id not in visible_source_ids:
                continue
            if source.geometry_family == "point":
                geometry = dict(source.geometry)
                geometry_type = str(geometry.get("type", ""))
                raw_coordinates = geometry.get("coordinates")
                if geometry_type == "Point":
                    point_coordinates = (raw_coordinates,)
                elif geometry_type == "MultiPoint":
                    point_coordinates = tuple(raw_coordinates or ())
                else:
                    raise ValueError(
                        f"{source.source_id}: unsupported point geometry "
                        f"{geometry_type!r}"
                    )
                point_layer = folium.FeatureGroup(name=source.label)
                for coordinate in point_coordinates:
                    if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
                        raise ValueError(
                            f"{source.source_id}: invalid point coordinate"
                        )
                    longitude = float(coordinate[0])
                    latitude = float(coordinate[1])
                    if not math.isfinite(longitude) or not math.isfinite(latitude):
                        raise ValueError(
                            f"{source.source_id}: non-finite point coordinate"
                        )
                    is_substation = source.source_id == "power_substations"
                    folium.CircleMarker(
                        location=(latitude, longitude),
                        radius=7 if is_substation else 4,
                        color=colors[source.source_id],
                        weight=2 if is_substation else 1,
                        opacity=0.95,
                        fill=True,
                        fill_color=colors[source.source_id],
                        fill_opacity=0.3 if is_substation else 0.9,
                        tooltip=f"{source.label} · {source.dataset}",
                    ).add_to(point_layer)
                point_layer.add_to(source_map)
                continue
            layer = folium.GeoJson(
                data={
                    "type": "Feature",
                    "properties": {
                        "lager": source.label,
                        "källa": source.dataset,
                        "urval": source.selection,
                    },
                    "geometry": dict(source.geometry),
                },
                name=source.label,
                style_function=(
                    lambda _feature, color=colors[source.source_id],
                    family=source.geometry_family: {
                        "color": color,
                        "weight": 3 if family == "line" else 1,
                        "opacity": 0.85,
                        "fillColor": color,
                        "fillOpacity": 0.36 if family == "polygon" else 0.8,
                    }
                ),
                tooltip=folium.GeoJsonTooltip(
                    fields=["lager", "källa", "urval"],
                    aliases=["Lager", "Källa", "Urval"],
                ),
            )
            layer.add_to(source_map)
        source_map.fit_bounds(region_bounds, padding=(20, 20))
        if not visible_source_ids:
            st.info(
                "Inga källager visas. Välj minst ett lager ovanför kartan "
                "för att fortsätta granskningen."
            )
        _render_html_map(source_map.get_root().render(), height=650)
        st.caption(
            "Kartlagren kommer från de regionägda PostGIS-vyerna och jämförs "
            "vid start mot exakt checksummebundna källfiler."
        )

    details = st.expander("Teknisk integritet", on_change="rerun")
    if details.open:
        with details:
            st.code(
                "\n".join(
                    [
                        f"catalog_sha256={selected_catalog.manifest_sha256}",
                        *(
                            [
                                "delivery_selection_sha256="
                                + load_delivery_source_selection(REPO_ROOT, selected_region_id).selection_sha256
                            ]
                            if delivery_only else []
                        ),
                        *(
                            f"{source.database_schema}.{source.database_view}="
                            f"{source.source_sha256}"
                            for source in selected_sources
                        ),
                    ]
                ),
                language="text",
            )


def _render_layers(
    region: dict[str, Any],
    layers: list[dict[str, Any]],
    opacity: float,
    map_state_key: str | None = None,
    map_reset_token: int = 0,
    opacity_key_prefix: str | None = None,
    note_title: str = "Samlad potential",
    note_body: str = "Aktiva lager styrs i appen och kan även slås av/på i kartkontrollen.",
    after_map_renderer: Any | None = None,
    pan_mode_label: str = "Panorera kartan",
    inspect_mode_label: str = "Granska potentiell etableringsyta",
    height: int = 820,
) -> int:
    if not layers:
        st.info(_t("Välj minst ett kartlager."))
        return 0
    try:
        map_view = resolve_workspace_map_view(region)
    except (TypeError, ValueError) as exc:
        st.error(
            _t("Kartvyn saknar ett giltigt manifestdeklarerat centrum eller "
            "zoomläge. Inget kartlager visas.")
        )
        st.caption(_t('Teknisk orsak: {p0}', p0=exc))
        return 0
    adjusted_layers = (
        _apply_layer_opacity_state(layers, opacity_key_prefix)
        if opacity_key_prefix
        else [dict(layer) for layer in layers]
    )
    transport_scope = (region.get("region_id"), map_state_key, opacity_key_prefix)
    transport_owner = st.session_state.get("_workspace_map_transport")
    if not isinstance(transport_owner, dict) or transport_owner.get("scope") != transport_scope:
        transport_owner = {"scope": transport_scope, "cache": {}}
        st.session_state["_workspace_map_transport"] = transport_owner
    map_html = build_layered_hex_map_html(
        adjusted_layers,
        center=map_view.center_list(),
        zoom=map_view.zoom,
        bounds=map_view.bounds_list(),
        fill_opacity=opacity,
        map_state_key=map_state_key,
        map_reset_token=map_reset_token,
        note_title=note_title,
        note_body=note_body,
        pan_mode_label=pan_mode_label,
        inspect_mode_label=inspect_mode_label,
        language=_language(),
        transport_cache=transport_owner["cache"],
    )
    feedback = current_loading()
    if feedback is not None:
        map_html = feedback.map_html(map_html)
    map_left, map_center, map_right = st.columns([0.02, 0.96, 0.02], gap="small")
    with map_center:
        st.markdown('<span data-potential-tutorial-anchor="map" data-workspace-guide="map" data-workspace-guide-kind="map"></span>', unsafe_allow_html=True)
        _render_html_map(map_html, height=height)
        if callable(after_map_renderer):
            after_map_renderer()
        if opacity_key_prefix:
            with st.expander(_t("Avancerade kartinställningar"), expanded=False):
                st.caption(_t("Justera kartopacitet när lager behöver jämföras mer tekniskt."))
                _hex_opacity_controls(adjusted_layers, opacity_key_prefix)
                _render_opacity_control(opacity_key_prefix)
    return len(adjusted_layers)


def _potential_layer(
    name: str,
    frame: pd.DataFrame,
    technology: str,
    display_geometry_path: str | None,
    legend_items: list[dict[str, str]],
) -> dict[str, Any]:
    land_frame = _filter_frame_to_display_geometries(frame, display_geometry_path)
    return {
        "name": name,
        "feature_collection": potential_feature_collection(land_frame, technology, None),
        "fill_property": "fill",
        "legend_items": legend_items,
        "legend_id": "potential_classes",
        "legend_title": "Potentialklasser",
        "default_visible": False,
        "stroke": False,
        "weight": 0.0,
        "layer_kind": "hex",
        "opacity_family": name,
        "opacity_label": name,
    }


def _solar_polygon_feature_collection(
    frame: pd.DataFrame,
    display_geometry_path: str | None,
    label: str,
) -> dict[str, Any] | None:
    if frame.empty:
        return None
    selected = frame[frame["solar_class"].astype(str).isin(["high", "very_high"])].copy()
    if selected.empty:
        return None
    display_geometries = load_h3_display_geometries(display_geometry_path) if display_geometry_path else {}
    multipolygon_parts: list[Any] = []
    for row in selected.itertuples(index=False):
        geometry = geometry_for_hex(str(row.hex_id), display_geometries)
        if geometry is None:
            continue
        geometry_type = str(geometry.get("type", ""))
        coordinates = geometry.get("coordinates") or []
        if geometry_type == "Polygon" and coordinates:
            multipolygon_parts.append(coordinates)
        elif geometry_type == "MultiPolygon" and coordinates:
            multipolygon_parts.extend(coordinates)
    if not multipolygon_parts:
        return None

    selected_share = (len(selected) / len(frame)) * 100.0
    popup = (
        f"<strong>{label}</strong><br>"
        f"Hex med hög/mycket hög LP Sol: {len(selected)}<br>"
        f"Andel av visad yta: {selected_share:.1f}%<br>"
        f"Medelpoäng i polygonlagret: {float(selected['solar_score'].mean()):.1f}"
    )
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "MultiPolygon", "coordinates": multipolygon_parts},
                "properties": {"fill": "#d97706", "popup": popup},
            }
        ],
    }


def _solar_polygon_layer(
    name: str,
    frame: pd.DataFrame,
    display_geometry_path: str | None,
    stroke_color: str = "#d97706",
    fill_color: str = "#d97706",
) -> dict[str, Any] | None:
    feature_collection = _solar_polygon_feature_collection(frame, display_geometry_path, name)
    if feature_collection is None:
        return None
    return {
        "name": name,
        "feature_collection": feature_collection,
        "fill_property": "fill",
        "legend_items": [],
        "legend_id": f"solar_polygon_{name.lower().replace(' ', '_')}",
        "legend_title": "",
        "default_visible": False,
        "stroke_color": stroke_color,
        "fill_color": fill_color,
        "stroke_opacity": 0.74,
        "fill_opacity": 0.08,
        "weight": 1.6,
        "point_radius": 6,
        "dash_array": "6 4",
        "use_global_opacity": False,
        "z_index": 430,
        "layer_kind": "vector",
    }


def _wind_vector_layer(
    name: str,
    source_frame: pd.DataFrame,
    display_geometry_path: str | None,
    legend_items: list[dict[str, str]],
) -> dict[str, Any]:
    land_frame = _filter_frame_to_display_geometries(source_frame, display_geometry_path)
    return {
        "name": name,
        "feature_collection": wind_vector_feature_collection(land_frame, None, only_potential_area=True),
        "fill_property": "fill",
        "legend_items": legend_items,
        "legend_id": "potential_classes",
        "legend_title": "Potentialklasser",
        "default_visible": True,
        "layer_kind": "vector",
    }


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % tuple(int(value) for value in rgb)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    color = str(value).strip().lstrip("#")
    if len(color) != 6:
        return (153, 153, 153)
    return tuple(int(color[idx : idx + 2], 16) for idx in (0, 2, 4))


def _mix_hex_colors(left: str, right: str, amount: float) -> str:
    amount = max(0.0, min(1.0, float(amount)))
    left_rgb = _hex_to_rgb(left)
    right_rgb = _hex_to_rgb(right)
    mixed = tuple(int(round(left_rgb[idx] + ((right_rgb[idx] - left_rgb[idx]) * amount))) for idx in range(3))
    return _rgb_to_hex(mixed)


def _social_acceptance_result_frame(
    result: SocialAcceptanceResult | None,
    target_resolution: int | None = None,
) -> pd.DataFrame:
    """Adapt exact typed result cells without reopening manifest assets."""

    columns = [
        "hex_id",
        "acceptance_value",
        "potential_weight",
        "source_hex_count",
        "social_acceptance_data_status",
    ]
    if result is None:
        return pd.DataFrame(columns=columns)
    resolution = (
        result.request.target_resolution
        if target_resolution is None
        else int(target_resolution)
    )
    if resolution > result.request.target_resolution:
        raise ValueError(
            "A SocialAcceptanceResult cannot be expanded to a finer resolution"
        )
    rows = [
        {
            "hex_id": (
                cell.cell_id
                if resolution == result.request.target_resolution
                else h3.cell_to_parent(cell.cell_id, resolution)
            ),
            "acceptance_value": cell.acceptance_value,
            "potential_weight": cell.potential_weight,
            "source_hex_count": cell.source_child_count,
            "social_acceptance_data_status": cell.data_status,
        }
        for cell in result.cells
    ]
    frame = pd.DataFrame(rows, columns=columns)
    if resolution == result.request.target_resolution:
        return frame.sort_values("hex_id").reset_index(drop=True)
    return (
        frame.groupby("hex_id", as_index=False)
        .agg(
            acceptance_value=("acceptance_value", "mean"),
            potential_weight=("potential_weight", "mean"),
            source_hex_count=("source_hex_count", "sum"),
            social_acceptance_data_status=(
                "social_acceptance_data_status",
                "first",
            ),
        )
        .sort_values("hex_id")
        .reset_index(drop=True)
    )


def _nullable_social_acceptance(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return math.nan
    if not math.isfinite(numeric):
        return math.nan
    return max(0.0, min(1.0, numeric))


def _apply_social_acceptance_impact_to_establishment_frame(
    frame: pd.DataFrame,
    result: SocialAcceptanceResult | None,
    target_resolution: int,
) -> pd.DataFrame:
    if frame.empty:
        return frame
    if result is None:
        return frame
    impact_fraction = result.request.impact_pct / 100.0
    if impact_fraction <= 0.0:
        return frame
    acceptance_resolution = min(
        int(target_resolution),
        result.request.target_resolution,
    )
    acceptance_frame = _social_acceptance_result_frame(
        result,
        acceptance_resolution,
    )
    if acceptance_frame.empty:
        return frame

    work = frame.copy()
    work["hex_id"] = work["hex_id"].astype(str)
    if int(target_resolution) > acceptance_resolution:
        work["social_acceptance_join_id"] = work["hex_id"].map(
            lambda cell_id: h3.cell_to_parent(
                cell_id,
                acceptance_resolution,
            )
        )
        work = work.merge(
            acceptance_frame.rename(
                columns={"hex_id": "social_acceptance_join_id"}
            ),
            on="social_acceptance_join_id",
            how="left",
        ).drop(columns=["social_acceptance_join_id"])
    else:
        work = work.merge(acceptance_frame, on="hex_id", how="left")
    work["acceptance_value"] = pd.to_numeric(
        work["acceptance_value"],
        errors="coerce",
    ).clip(lower=0.0, upper=1.0)
    social_observed = work["acceptance_value"].notna()
    work["social_acceptance_data_status"] = work[
        "social_acceptance_data_status"
    ].where(
        social_observed,
        "not_assessed",
    )
    work["source_hex_count"] = pd.to_numeric(work["source_hex_count"], errors="coerce").fillna(0).astype(int)
    work["social_acceptance_value"] = work["acceptance_value"].round(3)
    work["social_acceptance_source_hex_count"] = work["source_hex_count"]
    work["social_acceptance_impact_pct"] = float(impact_fraction * 100.0)
    work["social_acceptance_tint_amount"] = (
        1.0 - pd.to_numeric(work["potential_weight"], errors="coerce")
    ).clip(lower=0.0, upper=1.0).where(social_observed, 1.0)
    work["social_acceptance_weight"] = pd.to_numeric(
        work["potential_weight"],
        errors="coerce",
    ).clip(
        lower=0.0,
        upper=1.0,
    ).where(
        social_observed,
        0.0,
    )
    fill_values = work["fill"] if "fill" in work.columns else pd.Series("#999999", index=work.index)
    stroke_values = work["stroke"] if "stroke" in work.columns else pd.Series("#999999", index=work.index)
    work["fill"] = [
        _mix_hex_colors(str(color), SOCIAL_ACCEPTANCE_IMPACT_TINT_COLOR, float(tint_amount))
        for color, tint_amount in zip(fill_values, work["social_acceptance_tint_amount"])
    ]
    work["stroke"] = [
        _mix_hex_colors(str(color), SOCIAL_ACCEPTANCE_IMPACT_TINT_COLOR, float(tint_amount))
        for color, tint_amount in zip(stroke_values, work["social_acceptance_tint_amount"])
    ]
    return work.drop(
        columns=[
            "acceptance_value",
            "potential_weight",
            "source_hex_count",
        ],
        errors="ignore",
    )


def _merge_social_acceptance_for_priority(
    frame: pd.DataFrame,
    result: SocialAcceptanceResult | None,
    target_resolution: int,
) -> tuple[pd.DataFrame, float]:
    if result is None:
        return frame, 0.0
    if result.allocation_priority_model != "linear_acceptance_blend":
        raise ValueError(
            "Unsupported SocialAcceptanceResult allocation priority model"
        )
    priority_fraction = result.request.allocation_priority_pct / 100.0
    if frame.empty or priority_fraction <= 0.0:
        return frame, 0.0
    acceptance_resolution = min(
        int(target_resolution),
        result.request.target_resolution,
    )
    acceptance_frame = _social_acceptance_result_frame(
        result,
        acceptance_resolution,
    )
    if acceptance_frame.empty:
        return frame, 0.0
    work = frame.copy()
    work["hex_id"] = work["hex_id"].astype(str)
    acceptance_columns = acceptance_frame[
        [
            "hex_id",
            "acceptance_value",
            "social_acceptance_data_status",
        ]
    ]
    if int(target_resolution) > acceptance_resolution:
        work["social_acceptance_join_id"] = work["hex_id"].map(
            lambda cell_id: h3.cell_to_parent(
                cell_id,
                acceptance_resolution,
            )
        )
        work = work.merge(
            acceptance_columns.rename(
                columns={"hex_id": "social_acceptance_join_id"}
            ),
            on="social_acceptance_join_id",
            how="left",
        ).drop(columns=["social_acceptance_join_id"])
    else:
        work = work.merge(acceptance_columns, on="hex_id", how="left")
    work["social_acceptance_value"] = pd.to_numeric(
        work["acceptance_value"],
        errors="coerce",
    ).clip(lower=0.0, upper=1.0)
    work["social_acceptance_data_status"] = work[
        "social_acceptance_data_status"
    ].where(
        work["social_acceptance_value"].notna(),
        "not_assessed",
    )
    work["social_acceptance_allocation_priority_pct"] = float(priority_fraction * 100.0)
    return work.drop(columns=["acceptance_value"], errors="ignore"), priority_fraction


def _apply_social_acceptance_priority_to_wind_allocation_frame(
    frame: pd.DataFrame,
    result: SocialAcceptanceResult | None,
    target_resolution: int,
) -> pd.DataFrame:
    work, priority_fraction = _merge_social_acceptance_for_priority(
        frame,
        result,
        target_resolution,
    )
    if priority_fraction <= 0.0 or work.empty:
        return work
    if "allocation_priority_score" in work.columns:
        technical_score = pd.to_numeric(work["allocation_priority_score"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    else:
        core_source = work["core_score"] if "core_score" in work.columns else pd.Series(0.0, index=work.index)
        share_source = work["potential_area_share_pct"] if "potential_area_share_pct" in work.columns else pd.Series(0.0, index=work.index)
        core_score = pd.to_numeric(core_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
        potential_share = pd.to_numeric(share_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0).div(100.0)
        technical_score = ((0.7 * core_score) + (0.3 * potential_share)).clip(lower=0.0, upper=1.0)
    acceptance = pd.to_numeric(
        work["social_acceptance_value"],
        errors="coerce",
    ).clip(lower=0.0, upper=1.0)
    work["technical_priority_score"] = technical_score
    core_before_source = work["core_score"] if "core_score" in work.columns else pd.Series(0.0, index=work.index)
    work["core_score_before_acceptance"] = pd.to_numeric(core_before_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    blended = ((1.0 - priority_fraction) * technical_score + priority_fraction * acceptance).clip(
        lower=0.0,
        upper=1.0,
    )
    work["social_acceptance_priority_score"] = blended.where(
        acceptance.notna()
    )
    work["allocation_priority_score"] = work["social_acceptance_priority_score"]
    work["core_score"] = work["allocation_priority_score"]
    return work


def _apply_social_acceptance_priority_to_solar_candidates(
    frame: pd.DataFrame,
    result: SocialAcceptanceResult | None,
    target_resolution: int,
) -> pd.DataFrame:
    work, priority_fraction = _merge_social_acceptance_for_priority(
        frame,
        result,
        target_resolution,
    )
    if priority_fraction <= 0.0 or work.empty:
        return work
    if "allocation_priority_score" in work.columns:
        technical_score = pd.to_numeric(work["allocation_priority_score"], errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
    else:
        score_source = work["potential_score"] if "potential_score" in work.columns else pd.Series(0.0, index=work.index)
        technical_score = pd.to_numeric(score_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0).div(100.0)
    acceptance = pd.to_numeric(
        work["social_acceptance_value"],
        errors="coerce",
    ).clip(lower=0.0, upper=1.0)
    work["technical_priority_score"] = technical_score
    blended = ((1.0 - priority_fraction) * technical_score + priority_fraction * acceptance).clip(
        lower=0.0,
        upper=1.0,
    )
    work["social_acceptance_priority_score"] = blended.where(
        acceptance.notna()
    )
    work["allocation_priority_score"] = work["social_acceptance_priority_score"]
    return work


def _social_acceptance_establishment_summary(
    establishment_frame: pd.DataFrame,
    result: SocialAcceptanceResult | None,
    hex_area_km2: float,
) -> dict[str, Any]:
    if establishment_frame.empty or result is None:
        return {}
    acceptance_frame = _social_acceptance_result_frame(result)

    work = establishment_frame.copy()
    work["hex_id"] = work["hex_id"].astype(str)
    if "establishment_class" in work.columns:
        potential_mask = work["establishment_class"].astype(str).ne("not_suitable")
    else:
        wind_suitable = work["wind_suitable"].astype(bool) if "wind_suitable" in work.columns else pd.Series(False, index=work.index)
        solar_suitable = work["solar_suitable"].astype(bool) if "solar_suitable" in work.columns else pd.Series(False, index=work.index)
        potential_mask = wind_suitable | solar_suitable
    potential_hexes = work.loc[potential_mask, ["hex_id"]].drop_duplicates().copy()
    if potential_hexes.empty:
        return {}

    joined = potential_hexes.merge(acceptance_frame, on="hex_id", how="left")
    joined["acceptance_value"] = pd.to_numeric(joined.get("acceptance_value"), errors="coerce")
    measured = joined.dropna(subset=["acceptance_value"]).copy()
    measured["acceptance_value"] = measured["acceptance_value"].clip(lower=0.0, upper=1.0)
    low_mask = measured["acceptance_value"].lt(
        result.low_threshold
    )
    high_mask = measured["acceptance_value"].ge(
        result.high_threshold
    )
    potential_hex_count = int(len(potential_hexes))
    measured_hex_count = int(len(measured))
    low_hex_count = int(low_mask.sum())
    high_hex_count = int(high_mask.sum())
    hex_area = max(0.0, float(hex_area_km2 or 0.0))
    impact_fraction = result.request.impact_pct / 100.0

    def _technology_potential_area(column_prefix: str) -> pd.Series:
        area_col = f"{column_prefix}_potential_area_km2"
        if area_col in work.columns:
            return pd.to_numeric(work[area_col], errors="coerce").fillna(0.0).clip(lower=0.0)
        suitable_col = f"{column_prefix}_suitable"
        if suitable_col in work.columns and hex_area > 0:
            return work[suitable_col].map(lambda value: False if pd.isna(value) else bool(value)).astype(float) * hex_area
        return pd.Series(0.0, index=work.index, dtype="float64")

    tech_area = work[["hex_id"]].copy()
    tech_area["wind_potential_area_km2"] = _technology_potential_area("wind")
    tech_area["solar_potential_area_km2"] = _technology_potential_area("solar")
    tech_area = (
        tech_area.groupby("hex_id", as_index=False)
        .agg(
            wind_potential_area_km2=("wind_potential_area_km2", "sum"),
            solar_potential_area_km2=("solar_potential_area_km2", "sum"),
        )
        .merge(acceptance_frame, on="hex_id", how="left")
    )
    tech_area["acceptance_value"] = pd.to_numeric(
        tech_area.get("acceptance_value"),
        errors="coerce",
    ).clip(lower=0.0, upper=1.0)
    acceptance_observed = tech_area["acceptance_value"].notna()
    tech_area["social_acceptance_data_status"] = tech_area[
        "social_acceptance_data_status"
    ].where(
        acceptance_observed,
        "not_assessed",
    )
    measured_weight = (
        (1.0 - impact_fraction)
        + (impact_fraction * tech_area["acceptance_value"])
    ).clip(lower=0.0, upper=1.0)
    unknown_weight = (
        0.0
        if impact_fraction > 0.0
        and result.missing_context_policy == "exclude_when_applied"
        else 1.0
    )
    tech_area["acceptance_weight"] = measured_weight.where(
        acceptance_observed,
        unknown_weight,
    )
    combined_cell_potential = tech_area[
        ["wind_potential_area_km2", "solar_potential_area_km2"]
    ].max(axis=1)
    unknown_potential = ~acceptance_observed & combined_cell_potential.gt(0.0)
    unknown_wind_area = float(
        tech_area.loc[unknown_potential, "wind_potential_area_km2"].sum()
    )
    unknown_solar_area = float(
        tech_area.loc[unknown_potential, "solar_potential_area_km2"].sum()
    )
    unknown_unique_area = float(combined_cell_potential.loc[unknown_potential].sum())

    def _weighted_potential_stats(column_prefix: str) -> dict[str, float]:
        area_col = f"{column_prefix}_potential_area_km2"
        raw_area = float(pd.to_numeric(tech_area.get(area_col), errors="coerce").fillna(0.0).clip(lower=0.0).sum())
        weighted_area = float((pd.to_numeric(tech_area.get(area_col), errors="coerce").fillna(0.0).clip(lower=0.0) * tech_area["acceptance_weight"]).sum())
        return {
            f"{column_prefix}_potential_after_acceptance_km2": max(0.0, weighted_area),
            f"{column_prefix}_potential_acceptance_reduction_km2": max(0.0, raw_area - weighted_area),
            f"{column_prefix}_potential_acceptance_ratio": (weighted_area / raw_area) if raw_area > 1e-9 else 1.0,
        }

    wind_acceptance_stats = _weighted_potential_stats("wind")
    solar_acceptance_stats = _weighted_potential_stats("solar")
    total_potential_after_acceptance = (
        wind_acceptance_stats["wind_potential_after_acceptance_km2"]
        + solar_acceptance_stats["solar_potential_after_acceptance_km2"]
    )
    total_raw_potential = float(tech_area["wind_potential_area_km2"].sum() + tech_area["solar_potential_area_km2"].sum())
    return {
        "scenario_id": result.request.scenario_id,
        "scenario_label": result.scenario_label,
        "impact_pct": float(impact_fraction * 100.0),
        "allocation_priority_pct": result.request.allocation_priority_pct,
        "h3_resolution": result.request.target_resolution,
        "hex_area_km2": hex_area,
        "potential_hex_count": potential_hex_count,
        "assessed_hex_count": measured_hex_count,
        "measured_hex_count": measured_hex_count,
        "unknown_hex_count": int(unknown_potential.sum()),
        "missing_hex_count": int(unknown_potential.sum()),
        "unknown_potential_area_km2": max(0.0, unknown_unique_area),
        "unknown_wind_potential_area_km2": max(0.0, unknown_wind_area),
        "unknown_solar_potential_area_km2": max(0.0, unknown_solar_area),
        "unknown_technology_potential_area_km2": max(
            0.0,
            unknown_wind_area + unknown_solar_area,
        ),
        "unknown_acceptance_weight": float(unknown_weight),
        "mean_acceptance": (
            float(measured["acceptance_value"].mean())
            if measured_hex_count > 0
            else math.nan
        ),
        "median_acceptance": (
            float(measured["acceptance_value"].median())
            if measured_hex_count > 0
            else math.nan
        ),
        "source_status": result.source_status,
        "source_label": result.source_label,
        "source_synthetic": result.synthetic,
        "regional_acceptance": result.regional_acceptance,
        "allowed_use": result.allowed_use,
        "value_data_status": result.value_data_status,
        "low_threshold": result.low_threshold,
        "high_threshold": result.high_threshold,
        "method_note": result.method_note,
        "low_acceptance_hex_count": low_hex_count,
        "low_acceptance_area_km2": float(low_hex_count * hex_area),
        "low_acceptance_share_pct": (low_hex_count / measured_hex_count * 100.0) if measured_hex_count > 0 else 0.0,
        "high_acceptance_hex_count": high_hex_count,
        "high_acceptance_area_km2": float(high_hex_count * hex_area),
        "high_acceptance_share_pct": (high_hex_count / measured_hex_count * 100.0) if measured_hex_count > 0 else 0.0,
        **wind_acceptance_stats,
        **solar_acceptance_stats,
        "total_potential_after_acceptance_km2": max(0.0, total_potential_after_acceptance),
        "total_potential_acceptance_reduction_km2": max(0.0, total_raw_potential - total_potential_after_acceptance),
        "total_potential_acceptance_ratio": (total_potential_after_acceptance / total_raw_potential) if total_raw_potential > 1e-9 else 1.0,
    }


def _wind_region_id(region_id: str | None = None) -> str:
    candidate = (
        region_id
        if region_id is not None
        else st.session_state.get(REGION_SELECT_KEY)
    )
    normalized = str(candidate or "").strip().lower()
    if not normalized:
        raise ValueError("A wind region id is required")
    return normalized


def normalize_group_layer_map(
    group_layer_map: dict[str, list[str]] | None,
    region_id: str | None = None,
) -> dict[str, list[str]]:
    """Normalize mixed migrated/unmigrated groups without a roads adapter."""
    source = group_layer_map or {}
    if not isinstance(source, dict):
        raise TypeError("A wind layer selection must be an object")
    normalized_region_id = _wind_region_id(region_id)
    public_group_ids = public_wind_group_ids(normalized_region_id)
    population_is_migrated = canonical_wind_group_is_declared(
        normalized_region_id,
        WIND_POPULATION_GROUP_ID,
    )
    nature_is_migrated = WIND_NATURE_GROUP_ID in public_group_ids
    culture_is_migrated = canonical_wind_group_is_declared(
        normalized_region_id,
        WIND_CULTURE_GROUP_ID,
    )
    grid_is_migrated = canonical_wind_group_is_declared(
        normalized_region_id,
        WIND_GRID_GROUP_ID,
    )
    canonical_culture_ids = (
        canonical_wind_group_layer_ids(
            normalized_region_id,
            CANONICAL_CULTURE_GROUP_ID,
        )
        if culture_is_migrated
        else ()
    )
    canonical_grid_ids = (
        canonical_wind_group_layer_ids(
            normalized_region_id,
            CANONICAL_GRID_GROUP_ID,
        )
        if grid_is_migrated
        else ()
    )
    legacy_roads = source.get(SOLAR_ROAD_GROUP_ID, [])
    if legacy_roads:
        raise ValueError(
            "Legacy transport road selections are no longer supported; "
            "use the canonical roads group"
        )
    legacy_population = source.get("settlement", [])
    if legacy_population:
        raise ValueError(
            "Legacy settlement population selections are no longer supported; "
            "use the canonical population group"
        )
    legacy_nature = source.get(SOLAR_PROTECTED_GROUP_ID, [])
    if legacy_nature and nature_is_migrated:
        raise ValueError(
            "Legacy protected nature selections are no longer supported; "
            "use the canonical nature group"
        )
    legacy_grid = source.get(SOLAR_ELECTRICAL_GROUP_ID, [])
    if legacy_grid and grid_is_migrated:
        raise ValueError(
            "Legacy electrical grid selections are no longer supported; "
            "use the canonical grid_infrastructure group"
        )

    available_road_ids = canonical_wind_group_layer_ids(
        normalized_region_id,
        CANONICAL_ROADS_GROUP_ID,
    )
    raw_roads = source.get(WIND_ROADS_GROUP_ID, [])
    if raw_roads is None:
        raw_roads = []
    if isinstance(raw_roads, (str, bytes)):
        raise TypeError("A V2 Final road selection must be a list of layer ids")
    requested_roads = tuple(str(layer_id).strip() for layer_id in raw_roads)
    if any(not layer_id for layer_id in requested_roads):
        raise ValueError("A V2 Final road selection contains a blank layer id")
    if len(requested_roads) != len(set(requested_roads)):
        raise ValueError("A V2 Final road selection contains duplicate layer ids")
    unknown_roads = set(requested_roads) - set(available_road_ids)
    if unknown_roads:
        raise ValueError(
            f"{normalized_region_id}/wind selected undeclared road layers: "
            f"{sorted(unknown_roads)}"
        )
    requested_road_set = set(requested_roads)

    canonical_population_ids = (
        canonical_wind_group_layer_ids(
            normalized_region_id,
            CANONICAL_POPULATION_GROUP_ID,
        )
        if population_is_migrated
        else ()
    )
    raw_population = source.get(WIND_POPULATION_GROUP_ID, [])
    if raw_population is None:
        raw_population = []
    if isinstance(raw_population, (str, bytes)):
        raise TypeError(
            "A V2 Final population selection must be a list of layer ids"
        )
    requested_population = tuple(
        str(layer_id).strip() for layer_id in raw_population
    )
    if any(not layer_id for layer_id in requested_population):
        raise ValueError(
            "A V2 Final population selection contains a blank layer id"
        )
    if len(requested_population) != len(set(requested_population)):
        raise ValueError(
            "A V2 Final population selection contains duplicate layer ids"
        )
    unknown_population = set(requested_population) - set(
        canonical_population_ids
    )
    if unknown_population:
        raise ValueError(
            f"{normalized_region_id}/wind selected undeclared population "
            f"layers: {sorted(unknown_population)}"
        )
    requested_population_set = set(requested_population)

    canonical_nature_ids = (
        canonical_wind_group_layer_ids(
            normalized_region_id,
            CANONICAL_NATURE_GROUP_ID,
        )
        if nature_is_migrated
        else ()
    )
    raw_nature = source.get(WIND_NATURE_GROUP_ID, [])
    if raw_nature is None:
        raw_nature = []
    if isinstance(raw_nature, (str, bytes)):
        raise TypeError(
            "A V2 Final nature selection must be a list of layer ids"
        )
    requested_nature = tuple(
        str(layer_id).strip() for layer_id in raw_nature
    )
    if any(not layer_id for layer_id in requested_nature):
        raise ValueError("A V2 Final nature selection contains a blank layer id")
    if len(requested_nature) != len(set(requested_nature)):
        raise ValueError(
            "A V2 Final nature selection contains duplicate layer ids"
        )
    unknown_nature = set(requested_nature) - set(canonical_nature_ids)
    if unknown_nature:
        raise ValueError(
            f"{normalized_region_id}/wind selected undeclared nature layers: "
            f"{sorted(unknown_nature)}"
        )
    requested_nature_set = set(requested_nature)

    raw_culture = source.get(WIND_CULTURE_GROUP_ID, [])
    if raw_culture is None:
        raw_culture = []
    if isinstance(raw_culture, (str, bytes)):
        raise TypeError(
            "A V2 Final culture selection must be a list of layer ids"
        )
    requested_culture = tuple(
        str(layer_id).strip() for layer_id in raw_culture
    )
    if culture_is_migrated:
        if any(not layer_id for layer_id in requested_culture):
            raise ValueError(
                "A V2 Final culture selection contains a blank layer id"
            )
        if len(requested_culture) != len(set(requested_culture)):
            raise ValueError(
                "A V2 Final culture selection contains duplicate layer ids"
            )
        unknown_culture = set(requested_culture) - set(
            canonical_culture_ids
        )
        if unknown_culture:
            raise ValueError(
                f"{normalized_region_id}/wind selected undeclared culture "
                f"layers: {sorted(unknown_culture)}"
            )
    requested_culture_set = set(requested_culture)

    raw_grid = source.get(WIND_GRID_GROUP_ID, [])
    if raw_grid is None:
        raw_grid = []
    if isinstance(raw_grid, (str, bytes)):
        raise TypeError(
            "A V2 Final grid-infrastructure selection must be a list of layer ids"
        )
    requested_grid = tuple(str(layer_id).strip() for layer_id in raw_grid)
    if grid_is_migrated:
        if any(not layer_id for layer_id in requested_grid):
            raise ValueError(
                "A V2 Final grid-infrastructure selection contains a blank layer id"
            )
        if len(requested_grid) != len(set(requested_grid)):
            raise ValueError(
                "A V2 Final grid-infrastructure selection contains duplicate layer ids"
            )
        unknown_grid = set(requested_grid) - set(canonical_grid_ids)
        if unknown_grid:
            raise ValueError(
                f"{normalized_region_id}/wind selected undeclared "
                f"grid-infrastructure layers: {sorted(unknown_grid)}"
            )
    requested_grid_set = set(requested_grid)

    legacy_selection = normalize_legacy_group_layer_map(source)
    normalized: dict[str, list[str]] = {}
    for group_id in public_group_ids:
        if group_id == WIND_ROADS_GROUP_ID:
            normalized[group_id] = [
                layer_id
                for layer_id in available_road_ids
                if layer_id in requested_road_set
            ]
        elif group_id == WIND_POPULATION_GROUP_ID:
            normalized[group_id] = [
                layer_id
                for layer_id in canonical_population_ids
                if layer_id in requested_population_set
            ]
        elif group_id == WIND_NATURE_GROUP_ID:
            normalized[group_id] = [
                layer_id
                for layer_id in canonical_nature_ids
                if layer_id in requested_nature_set
            ]
        elif group_id == WIND_CULTURE_GROUP_ID and culture_is_migrated:
            normalized[group_id] = [
                layer_id
                for layer_id in canonical_culture_ids
                if layer_id in requested_culture_set
            ]
        elif group_id == WIND_GRID_GROUP_ID and grid_is_migrated:
            normalized[group_id] = [
                layer_id
                for layer_id in canonical_grid_ids
                if layer_id in requested_grid_set
            ]
        else:
            normalized[group_id] = list(legacy_selection.get(group_id, []))
    # Hidden legacy groups remain available to the frozen-reference oracle
    # until their own complete behavior slice is migrated. They are not
    # exposed by public_wind_group_ids() or the V2 Final controls.
    for group_id in WIND_GROUP_LAYER_DEFAULTS:
        if group_id in {"settlement", SOLAR_ELECTRICAL_GROUP_ID} or (
            group_id == SOLAR_PROTECTED_GROUP_ID and nature_is_migrated
        ):
            continue
        normalized.setdefault(
            group_id,
            list(legacy_selection.get(group_id, [])),
        )
    return normalized


def _wind_group_param_key(group_id: str) -> str | None:
    if str(group_id) == WIND_ROADS_GROUP_ID:
        return WIND_ROADS_PARAM_KEY
    if str(group_id) == WIND_POPULATION_GROUP_ID:
        return WIND_POPULATION_PARAM_KEY
    if str(group_id) == WIND_NATURE_GROUP_ID:
        return WIND_NATURE_PARAM_KEY
    if str(group_id) == WIND_GRID_GROUP_ID:
        return WIND_GRID_PARAM_KEY
    return GROUP_PARAM_MAP.get(str(group_id))


@_presentation_input('_wind_control_groups')
def _wind_control_groups(region_id: str) -> list[Any]:
    """Build controls from the active manifest before any legacy adapter."""

    normalized_region_id = _wind_region_id(region_id)
    legacy_groups: dict[str, Any] | None = None
    controls: list[Any] = []
    for group_id in public_wind_group_ids(normalized_region_id):
        if canonical_wind_group_is_declared(normalized_region_id, group_id):
            group = analysis_group_control_contract(
                normalized_region_id,
                "wind",
                group_id,
            )
        else:
            if legacy_groups is None:
                legacy_groups, _, _ = load_acceptance_registry(
                    normalized_region_id
                )
            group = legacy_groups.get(group_id)
        if group is not None:
            controls.append(group)
    return controls


def _wind_control_group(region_id: str, group_id: str) -> Any | None:
    return next(
        (
            group
            for group in _wind_control_groups(region_id)
            if str(group.id) == str(group_id)
        ),
        None,
    )


def _wind_control_layers(region_id: str, group: Any) -> list[Any]:
    if isinstance(group, WindGroupControlContract):
        return list(group.layers)
    return [
        layer
        for layer in ordered_layers(region_id)
        if str(layer.group_id) == str(group.id)
    ]


def _default_wind_layer_selection(
    region_id: str | None = None,
) -> dict[str, list[str]]:
    normalized_region_id = _wind_region_id(region_id)
    return normalize_group_layer_map(
        default_wind_layer_selection(normalized_region_id),
        normalized_region_id,
    )


def _selected_wind_layers(
    region_id: str | None = None,
) -> dict[str, list[str]]:
    normalized_region_id = _wind_region_id(region_id)
    raw = st.session_state.get(WIND_LAYER_SELECTION_KEY)
    if not isinstance(raw, dict):
        selected = normalize_group_layer_map(
            _default_wind_layer_selection(normalized_region_id),
            normalized_region_id,
        )
        st.session_state[WIND_LAYER_SELECTION_KEY] = selected
        return selected
    selected = normalize_group_layer_map(raw, normalized_region_id)
    st.session_state[WIND_LAYER_SELECTION_KEY] = selected
    return selected


def _wind_control_key(prefix: str, item_id: str) -> str:
    return f"wind_control__{prefix}__{item_id}"


def _wind_visual_options_from_state(layer_selection: dict[str, list[str]] | None = None) -> dict[str, Any]:
    selected = normalize_group_layer_map(layer_selection or _selected_wind_layers())
    active_group_ids = [group_id for group_id, layer_ids in selected.items() if layer_ids]
    return {
        "source_group_ids": [
            group_id
            for group_id in active_group_ids
            if bool(st.session_state.get(_wind_control_key("visual_source", group_id), False))
        ],
        "buffer_group_ids": [
            group_id
            for group_id in active_group_ids
            if bool(st.session_state.get(_wind_control_key("visual_buffer", group_id), False))
        ],
    }


def _init_wind_control_state(region_id: str | None = None) -> None:
    normalized_region_id = _wind_region_id(region_id)
    for group in _wind_control_groups(normalized_region_id):
        _, _, _, default_m = _wind_group_control_contract(
            group,
            normalized_region_id,
        )
        st.session_state.setdefault(
            _wind_control_key("analysis", group.id),
            default_m,
        )
        st.session_state.setdefault(_wind_control_key("blend", group.id), int(group.blend_default))
        st.session_state.setdefault(_wind_control_key("visual_source", group.id), False)
        st.session_state.setdefault(_wind_control_key("visual_buffer", group.id), False)
        for layer in _wind_control_layers(normalized_region_id, group):
            st.session_state.setdefault(
                _wind_control_key("layer", layer.id),
                False,
            )


def _wind_group_control_contract(
    group: Any,
    region_id: str,
) -> tuple[int, int, int, int]:
    _ = region_id
    return (
        int(group.analysis_min_m),
        int(group.analysis_max_m),
        int(group.analysis_step_m),
        int(group.analysis_default_m),
    )


def _prime_wind_builder_state(
    saved_ui_params: dict[str, float] | None = None,
    saved_layer_selection: dict[str, list[str]] | None = None,
    region_id: str | None = None,
) -> None:
    normalized_region_id = _wind_region_id(region_id)
    _init_wind_control_state(normalized_region_id)
    selected = normalize_group_layer_map(
        saved_layer_selection or {},
        normalized_region_id,
    )
    for group in _wind_control_groups(normalized_region_id):
        param_key = _wind_group_param_key(group.id)
        if param_key and isinstance(saved_ui_params, dict) and param_key in saved_ui_params:
            st.session_state.setdefault(
                _wind_control_key("analysis", group.id),
                int(round(float(saved_ui_params[param_key]))),
            )
        for layer in _wind_control_layers(normalized_region_id, group):
            st.session_state.setdefault(
                _wind_control_key("layer", layer.id),
                bool(layer.id in selected.get(group.id, [])),
            )


def _wind_layer_status_lookup(registry_meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    status_df = acceptance_layer_status_table(registry_meta)
    if status_df.empty:
        return {}
    return {str(row["layer_id"]): row.to_dict() for _, row in status_df.iterrows()}


def _wind_layer_is_ready(layer_id: str, availability: dict[str, dict[str, Any]]) -> bool:
    status = availability.get(str(layer_id), {})
    return (
        bool(status.get("geojson_ready"))
        and bool(status.get("distance_ready"))
        and bool(status.get("source_exists"))
        and int(status.get("feature_count", 0) or 0) > 0
        and str(status.get("status", "")) == "ok"
    )


def _wind_control_layer_is_ready(
    group_id: str,
    layer: Any,
    availability: dict[str, dict[str, Any]],
) -> bool:
    if isinstance(layer, WindLayerControlContract):
        return bool(layer.ready)
    return _wind_layer_is_ready(str(layer.id), availability)


def _wind_group_has_ready_layers(group_id: str, group_layers: list[Any], availability: dict[str, dict[str, Any]]) -> bool:
    return any(
        _wind_control_layer_is_ready(group_id, layer, availability)
        for layer in group_layers
    )


def _wind_filter_group_control(
    group: Any,
    group_layers: list[Any],
    availability: dict[str, dict[str, Any]],
    region_id: str,
    language: str,
) -> FilterGroupControl:
    (
        analysis_min_m,
        analysis_max_m,
        analysis_step_m,
        _,
    ) = _wind_group_control_contract(group, region_id)
    is_manifest_group = isinstance(group, WindGroupControlContract)
    label = (
        str(group.label)
        if is_manifest_group
        else group_label(group, language, group.label)
    )
    interpretation = (
        str(group.interpretation)
        if is_manifest_group
        else group_interpretation(group, language, group.interpretation)
    )
    analysis_label = (
        str(group.analysis_label)
        if is_manifest_group
        else group_analysis_label(group, language, group.analysis_label)
    )
    sources: list[FilterSourceControl] = []
    for layer in group_layers:
        status = availability.get(layer.id, {})
        ready = _wind_control_layer_is_ready(
            group.id,
            layer,
            availability,
        )
        is_manifest_layer = isinstance(layer, WindLayerControlContract)
        message = str(
            layer.message
            if is_manifest_layer
            else status.get("message", "")
            or layer_note(layer, language, layer.note)
            or ""
        )
        source_label = (
            str(layer.label)
            if is_manifest_layer
            else layer_label(layer, language, layer.label)
        )
        if is_manifest_layer and layer.quality_flag == "caution":
            source_label = f"{source_label} :orange[:material/warning:]"
        sources.append(
            FilterSourceControl(
                id=str(layer.id),
                label=source_label,
                key=_wind_control_key("layer", layer.id),
                ready=bool(ready),
                help_text=message,
            )
        )
    return filter_group_control(
        group_id=str(group.id),
        label=label,
        interpretation=interpretation,
        analysis_label=analysis_label,
        analysis_min_m=analysis_min_m,
        analysis_max_m=analysis_max_m,
        analysis_step_m=analysis_step_m,
        analysis_key=_wind_control_key("analysis", group.id),
        analysis_help=ui_text("analysis_slider_help", language),
        sources=sources,
    )


def _build_applied_wind_workspace_request(
    region_id: str,
    selected_group_layers: Mapping[str, list[str]],
    control_by_id: Mapping[str, Any],
    *,
    review_access: ReviewAccessContract | None,
    target_resolution: int | None = None,
) -> WorkspaceAnalysisRequest:
    """Bind one submitted form to the active typed analysis manifest."""

    contract = load_delivery_analysis(region_id, "wind")
    selected = {
        group_id: tuple(selected_group_layers.get(group_id) or ())
        for group_id in contract.groups
        if selected_group_layers.get(group_id)
    }
    if review_access is not None:
        allowed = {
            (str(policy.analysis_id), str(policy.group_id))
            for policy in review_access.allowed_slices
            if policy.apply_required
        }
        rejected = {
            group_id
            for group_id in selected
            if ("wind", group_id) not in allowed
        }
        if rejected:
            raise ValueError(
                f"Review request selected groups outside its manifest: "
                f"{sorted(rejected)}"
            )

    group_parameters: dict[str, dict[str, float]] = {}
    for group_id, layer_ids in selected.items():
        control = control_by_id.get(group_id)
        if control is None:
            raise ValueError(f"The manifest has no UI control for {group_id}")
        parameter_ids = tuple(contract.layers[layer_ids[0]].parameters)
        if len(parameter_ids) != 1:
            raise ValueError(
                f"{region_id}/wind {group_id} does not match the shared "
                "single-parameter group control"
            )
        parameter_id = parameter_ids[0]
        if review_access is not None:
            policy = next(
                (
                    item
                    for item in review_access.allowed_slices
                    if str(item.analysis_id) == "wind"
                    and str(item.group_id) == group_id
                ),
                None,
            )
            if policy is None or tuple(policy.explicit_parameters) != parameter_ids:
                raise ValueError(
                    f"Review request parameters for wind/{group_id} do not "
                    "match its manifest policy"
                )
        group_parameters[group_id] = {
            parameter_id: float(
                st.session_state.get(
                    _wind_control_key("analysis", group_id),
                    control.analysis_default_m,
                )
            )
        }

    access_scope = str(
        st.session_state.get(REGION_SESSION_SCOPE_KEY) or ""
    ).strip().lower()
    return build_workspace_analysis_request_from_contract(
        contract,
        access_scope=access_scope,
        selected_group_layers=selected,
        group_parameters=group_parameters,
        target_resolution=target_resolution,
    )


def _validated_applied_wind_workspace_request(
    region_id: str,
) -> WorkspaceAnalysisRequest | None:
    """Read wind through the same namespaced request authority as solar."""

    return _read_applied_workspace_request(
        _workspace_ui_identity(region_id, "wind")
    )


def _wind_workspace_request_values(
    request: WorkspaceAnalysisRequest,
) -> tuple[dict[str, list[str]], dict[str, float]]:
    """Adapt an immutable request to legacy presentation values only."""

    selected = normalize_group_layer_map(
        {
            group.group_id: list(group.layer_ids)
            for group in request.groups
        },
        request.region_id,
    )
    ui_params = _default_wind_params()
    for group in request.groups:
        parameter_values = group.parameter_map()
        if len(parameter_values) != 1:
            raise ValueError(
                f"{request.region_id}/wind {group.group_id} does not match "
                "the shared single-parameter control"
            )
        param_key = _wind_group_param_key(group.group_id)
        if not param_key:
            raise ValueError(
                f"{request.region_id}/wind has no UI parameter binding for "
                f"{group.group_id}"
            )
        ui_params[param_key] = float(next(iter(parameter_values.values())))
    return selected, ui_params


def _wind_workspace_request_at_resolution(
    request: WorkspaceAnalysisRequest,
    target_resolution: int,
) -> WorkspaceAnalysisRequest:
    """Rebind one applied request to an explicitly declared domain rollup."""

    contract = load_delivery_analysis(request.region_id, request.analysis_id)
    validate_workspace_analysis_request_from_contract(contract, request)
    return build_workspace_analysis_request_from_contract(
        contract,
        access_scope=request.access_scope,
        selected_group_layers={
            group.group_id: group.layer_ids for group in request.groups
        },
        group_parameters={
            group.group_id: group.parameter_map() for group in request.groups
        },
        target_resolution=int(target_resolution),
    )


def _wind_group_controls(
    widget_prefix: str,
    language: str = WIND_CONTROL_LANGUAGE,
    *,
    region_id: str | None = None,
    group_availability: tuple[Any, ...] | None = None,
    review_access: ReviewAccessContract | None = None,
) -> tuple[dict[str, list[str]], dict[str, float], bool]:
    """Render the one shared wind filter form for every access scope."""

    normalized_region_id = _wind_region_id(region_id)
    _init_wind_control_state(normalized_region_id)
    control_groups = _wind_control_groups(normalized_region_id)
    control_by_id = {str(group.id): group for group in control_groups}
    legacy_controls = [
        group
        for group in control_groups
        if not isinstance(group, WindGroupControlContract)
    ]
    if legacy_controls:
        _, _, registry_meta = load_acceptance_registry(normalized_region_id)
        layer_availability = _wind_layer_status_lookup(registry_meta)
    else:
        layer_availability = {}
    availability_by_group = {
        str(item.capability_id).removeprefix("wind.group."): item
        for item in (group_availability or ())
    }
    request_policy_by_group = {
        str(policy.group_id): policy
        for policy in (review_access.allowed_slices if review_access else ())
        if str(policy.analysis_id) == "wind"
    }
    selected: dict[str, list[str]] = {group.id: [] for group in control_groups}
    applied_request = _validated_applied_wind_workspace_request(
        normalized_region_id
    )
    if applied_request is None:
        initial_selection = _default_wind_layer_selection(normalized_region_id)
        applied_request = _build_applied_wind_workspace_request(
            normalized_region_id,
            initial_selection,
            control_by_id,
            review_access=review_access,
        )
        # Product defaults are an applied manifest request. Review starts
        # deliberately without an applied request so source preview/result
        # cannot appear until the operator submits the form.
        if applied_request.access_scope.startswith("product:"):
            st.session_state[WORKSPACE_FILTER_APPLIED_STATE_KEY] = (
                applied_request.as_dict()
            )
    applied_selection, applied_ui_params = _wind_workspace_request_values(
        applied_request
    )
    # This selection mirror remains a temporary presentation adapter for
    # untouched code and is always derived from the immutable request above.
    st.session_state[WIND_LAYER_SELECTION_KEY] = applied_selection

    st.header(ui_text("groups_header", language))
    applied_count_slot = st.empty()
    filter_bindings: list[
        tuple[FilterGroupControl, str, str, tuple[str, ...], bool]
    ] = []
    with st.form(f"{widget_prefix}_group_controls", clear_on_submit=False):
        display_group_ids = (
            [
                str(item.capability_id).removeprefix("wind.group.")
                for item in group_availability
            ]
            if group_availability is not None
            else [str(group.id) for group in control_groups]
        )
        for group_id in display_group_ids:
            availability_item = availability_by_group.get(group_id)
            if (
                availability_item is not None
                and availability_item.interaction != "interactive"
            ):
                label, color, icon = _workspace_availability_presentation(
                    availability_item.state
                )
                with st.expander(availability_item.label, expanded=False):
                    st.caption(availability_item.interpretation)
                    st.badge(label, color=color, icon=icon)
                    st.caption(availability_item.detail)
                    st.checkbox(
                        f"Använd {availability_item.label.lower()}",
                        value=False,
                        key=(
                            "workspace_capability__"
                            f"{availability_item.capability_id}"
                        ),
                        disabled=True,
                        help=f"Orsak: {availability_item.state}.",
                        persist_state="session",
                    )
                continue
            group = control_by_id.get(group_id)
            if group is None:
                raise ValueError(
                    f"{normalized_region_id}/wind has no control for {group_id}"
                )
            is_manifest_group = isinstance(group, WindGroupControlContract)
            group_layers = _wind_control_layers(normalized_region_id, group)
            group_available = _wind_group_has_ready_layers(
                group.id,
                group_layers,
                layer_availability,
            )
            if not group_available:
                continue
            control = _wind_filter_group_control(
                group,
                group_layers,
                layer_availability,
                normalized_region_id,
                language,
            )
            expanded_by_default = bool(
                group.expanded_by_default
                if is_manifest_group
                else group.id == "electrical"
            )
            group_key = _wind_control_key("group", group.id)
            sync_key = _wind_control_key("group_sync", group.id)
            request_policy = request_policy_by_group.get(group_id)
            auto_select_sources = (
                bool(request_policy.auto_select_sources)
                if request_policy is not None
                else review_access is None
            )
            default_source_ids = (
                tuple(
                    source.id for source in control.sources
                    if source.ready and (
                        request_policy is None
                        or request_policy.selects_source_by_default(source.id)
                    )
                )
                if auto_select_sources
                else ()
            )
            auto_select_sources = auto_select_sources and bool(default_source_ids)
            filter_bindings.append(
                (
                    control,
                    group_key,
                    sync_key,
                    default_source_ids,
                    auto_select_sources,
                )
            )
            with st.expander(control.label, expanded=expanded_by_default):
                selected[group.id] = _render_native_filter_group_control(
                    control,
                    group_key=group_key,
                    sync_key=sync_key,
                    default_source_ids=default_source_ids,
                    auto_select_sources=auto_select_sources,
                )
                if not selected[group.id]:
                    st.caption(ui_text("group_inactive", language))
        applied = st.form_submit_button(
            ui_text("apply_changes", language),
            type="primary",
            width="stretch",
            on_click=_sync_filter_group_controls_on_apply,
            args=(tuple(filter_bindings),),
        )

    st.button(
        "Nollställ filter",
        key=f"{widget_prefix}_reset_filters",
        icon=":material/filter_alt_off:",
        width="stretch",
        on_click=_reset_wind_filter_state,
        args=(normalized_region_id,),
    )

    draft_ui_params = _default_wind_params()
    for group in control_groups:
        param_key = _wind_group_param_key(group.id)
        if not param_key:
            continue
        _, _, _, analysis_default_m = _wind_group_control_contract(
            group,
            normalized_region_id,
        )
        draft_ui_params[param_key] = float(
            st.session_state.get(
                _wind_control_key("analysis", group.id),
                analysis_default_m,
            )
        )
    draft_normalized = normalize_group_layer_map(
        selected,
        normalized_region_id,
    )
    if applied:
        normalized = draft_normalized
        ui_params = draft_ui_params
        try:
            workspace_request = _build_applied_wind_workspace_request(
                normalized_region_id,
                normalized,
                control_by_id,
                review_access=review_access,
            )
        except (FileNotFoundError, KeyError, OSError, TypeError, ValueError) as exc:
            st.error(
                "Ändringarna kunde inte bindas till regionens analysmanifest. "
                "Den senast tillämpade konfigurationen behålls."
            )
            st.caption(f"Teknisk orsak: {exc}")
            normalized = applied_selection
            ui_params = applied_ui_params
            applied = False
        else:
            normalized, ui_params = _wind_workspace_request_values(
                workspace_request
            )
            st.session_state[WIND_LAYER_SELECTION_KEY] = normalized
            if review_access is not None and not workspace_request.groups:
                st.session_state.pop(
                    WORKSPACE_FILTER_APPLIED_STATE_KEY,
                    None,
                )
            else:
                st.session_state[WORKSPACE_FILTER_APPLIED_STATE_KEY] = (
                    workspace_request.as_dict()
                )
            _invalidate_workspace_cache("wind controls applied")
            st.session_state[WIND_EMPTY_SELECTION_ACTIVE_KEY] = (
                not _has_selected_wind_layers(normalized)
            )
    else:
        normalized = applied_selection
        ui_params = applied_ui_params
    current_selected_count = sum(
        len(layer_ids) for layer_ids in normalized.values()
    )
    applied_count_slot.caption(
        "Inga aktiva filter – hela analysdomänen visas."
        if current_selected_count == 0
        else f"{current_selected_count} aktiva filter."
    )
    return normalized, ui_params, bool(applied)


def _render_wind_map_review_controls(
    region: dict[str, Any],
    layer_selection: dict[str, list[str]],
) -> None:
    """Render map-only controls outside the analysis form."""
    region_id = str(region.get("region_id") or "")
    selected = normalize_group_layer_map(layer_selection, region_id)
    active_group_ids = [
        group_id for group_id, layer_ids in selected.items() if layer_ids
    ]
    if not active_group_ids:
        return

    expanded = any(
        bool(st.session_state.get(_wind_control_key(kind, group_id), False))
        for group_id in active_group_ids
        for kind in ("visual_source", "visual_buffer")
    )
    with st.expander(_t("Kartgranskning"), expanded=expanded, key=f"workspace_{region_id}:wind_map_review_panel"):
        st.caption(
            _t("Dessa val ändrar bara kartan. De påverkar inte analysen eller "
            "resultattabellen.")
        )
        for group_id in active_group_ids:
            group = _wind_control_group(region_id, group_id)
            label = (
                str(group.label)
                if isinstance(group, WindGroupControlContract)
                else group_label(
                    group,
                    WIND_CONTROL_LANGUAGE,
                    group.label,
                )
                if group is not None
                else str(group_id)
            )
            selected_layer_ids = selected.get(group_id, [])
            st.markdown(f"**{label}**")
            st.toggle(
                _t("Visa källa i kartan"),
                key=_wind_control_key("visual_source", group_id),
                on_change=_request_ui_only_rerun,
                args=("wind source preview changed",),
                persist_state="session",
            )
            buffer_supported = _vector_preview_supported(
                region_id,
                selected_layer_ids,
            )
            if not buffer_supported:
                st.session_state[_wind_control_key(
                    "visual_buffer", group_id
                )] = False
            st.toggle(
                _t("Visa buffert i kartan"),
                key=_wind_control_key("visual_buffer", group_id),
                disabled=not buffer_supported,
                on_change=_request_ui_only_rerun,
                args=("wind buffer preview changed",),
                help=(
                    _t("Bufferten byggs direkt från de manifestdeklarerade "
                    "vektorkällorna i regionens meterbaserade CRS.")
                    if buffer_supported
                    else _t("Buffertvisning aktiveras när gruppens "
                    "vektorkontrakt har migrerats.")
                ),
                persist_state="session",
            )


def _wind_active_group_ids(
    ui_params: dict[str, float],
    layer_selection: dict[str, list[str]] | None = None,
) -> list[str]:
    _ = ui_params
    selected = normalize_group_layer_map(layer_selection or _selected_wind_layers())
    active: list[str] = []
    for group_id, layer_ids in selected.items():
        if not layer_ids:
            continue
        active.append(group_id)
    return active


def _wind_share_class_spec(area_share_pct: float) -> dict[str, Any]:
    share_value = max(0.0, min(100.0, float(area_share_pct)))
    for spec in WIND_SHARE_CLASS_SPECS:
        if share_value <= float(spec["max_pct"]):
            return spec
    return WIND_SHARE_CLASS_SPECS[-1]


def _wind_share_legend_items() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for spec in WIND_SHARE_CLASS_SPECS:
        if not spec.get("legend_label"):
            continue
        if str(spec.get("id")) == "share_0":
            items.append({"label": "Mörkare röd = djupare kärnområde", "color": "#7f0000"})
        items.append({"label": str(spec["legend_label"]), "color": str(spec["base_color"])})
        if str(spec.get("id")) == "share_9":
            items.append({"label": "Mörkare blå = djupare kärnområde", "color": "#1e3a8a"})
    return items


def _wind_core_label(core_score: float, zone_size: int) -> str:
    core_value = max(0.0, min(1.0, float(core_score)))
    zone_size_value = max(0, int(zone_size))
    if zone_size_value <= 1:
        return "Enskild hex"
    if core_value >= 0.72:
        return "Djup kärna"
    if core_value >= 0.36:
        return "Mellanläge"
    return "Kantzon"


@st.cache_data(show_spinner=False)
def _wind_runtime_hex_neighbor_map(display_geometry_path: str) -> dict[str, list[str]]:
    land_hexes = set(load_h3_display_geometries(display_geometry_path))
    neighbor_map: dict[str, list[str]] = {}
    for hex_id in land_hexes:
        neighbor_map[str(hex_id)] = [str(neighbor) for neighbor in h3.grid_disk(str(hex_id), 1) if str(neighbor) != str(hex_id)]
    return neighbor_map


def _wind_runtime_hex_core_scores(frame: pd.DataFrame, neighbor_map: dict[str, list[str]]) -> pd.DataFrame:
    if frame.empty:
        return frame

    work = frame.copy()
    class_lookup = {
        str(row.hex_id): int(row.share_class_index)
        for row in work[["hex_id", "share_class_index"]].itertuples(index=False)
    }
    metrics = {
        item.cell_id: item
        for item in wind_core_metrics(class_lookup, neighbor_map)
    }
    work["zone_id"] = work["hex_id"].astype(str).map(
        lambda value: metrics[value].zone_id
    )
    work["zone_size"] = work["hex_id"].astype(str).map(
        lambda value: metrics[value].zone_size
    ).astype(int)
    work["core_distance"] = work["hex_id"].astype(str).map(
        lambda value: metrics[value].core_distance
    ).astype(int)
    work["core_score"] = work["hex_id"].astype(str).map(
        lambda value: metrics[value].core_score
    ).astype(float)
    work["center_mass_rank"] = work["hex_id"].astype(str).map(
        lambda value: metrics[value].center_mass_rank
    ).astype(int)

    return work


def _wind_runtime_hex_color(area_share_pct: float, core_score: float, zone_size: int) -> str:
    class_spec = _wind_share_class_spec(area_share_pct)
    share_value = float(area_share_pct)
    core_value = max(0.0, min(1.0, float(core_score)))
    zone_size_value = max(0, int(zone_size))
    if zone_size_value <= 1:
        return str(class_spec["base_color"])

    if share_value <= 0.0:
        core_target = _mix_hex_colors(str(class_spec["core_color"]), "#180000", min(1.0, float(zone_size_value) / 150.0))
        intensity = (core_value ** 0.82) * min(1.0, 0.48 + (float(zone_size_value) / 120.0))
        return _mix_hex_colors(str(class_spec["base_color"]), core_target, intensity)

    if share_value >= 80.0:
        core_target = _mix_hex_colors(str(class_spec["core_color"]), "#082f6f", min(1.0, max(0.0, float(zone_size_value - 4)) / 40.0))
        intensity = (core_value ** 0.86) * min(0.82, 0.36 + (float(zone_size_value) / 70.0))
        return _mix_hex_colors(str(class_spec["base_color"]), core_target, intensity)

    intensity = (core_value ** 0.9) * min(0.56, 0.16 + (float(zone_size_value) / 52.0))
    return _mix_hex_colors(str(class_spec["base_color"]), str(class_spec["core_color"]), intensity)


@st.cache_data(show_spinner=False)
def _build_wind_runtime_hex_layer_data(
    combined_geojson_json: str,
    display_geometry_path: str,
    target_resolution: int,
) -> pd.DataFrame:
    combined_geojson = json.loads(combined_geojson_json)
    base_share = runtime_combined_hex_frame(combined_geojson, WIND_RUNTIME_BASE_RESOLUTION, [])
    raw_share = pd.DataFrame(columns=["hex_id", "potential_area_share_pct", "potential_area_km2"])
    if not base_share.empty and "hex_id" in base_share.columns:
        raw_share = base_share[["hex_id", "wind_score"]].rename(columns={"wind_score": "potential_area_share_pct"}).copy()
        raw_share["hex_id"] = raw_share["hex_id"].astype(str)
        raw_share["potential_area_share_pct"] = raw_share["potential_area_share_pct"].fillna(0.0).astype(float).clip(lower=0.0, upper=100.0)
        base_hex_area = float(h3_hex_area_km2(WIND_RUNTIME_BASE_RESOLUTION))
        raw_share["potential_area_km2"] = raw_share["potential_area_share_pct"].div(100.0) * base_hex_area
        if int(target_resolution) < WIND_RUNTIME_BASE_RESOLUTION:
            raw_share["hex_id"] = raw_share["hex_id"].map(lambda value: str(h3.cell_to_parent(str(value), int(target_resolution))))
            raw_share = (
                raw_share.groupby("hex_id", as_index=False)
                .agg(potential_area_km2=("potential_area_km2", "sum"))
            )
            target_hex_area = float(h3_hex_area_km2(int(target_resolution)))
            raw_share["potential_area_share_pct"] = (
                raw_share["potential_area_km2"] / max(target_hex_area, 1e-9) * 100.0
            ).clip(lower=0.0, upper=100.0)
    display_geometries = load_h3_display_geometries(display_geometry_path)
    frame = pd.DataFrame({"hex_id": list(display_geometries.keys())})
    if not raw_share.empty and "hex_id" in raw_share.columns:
        frame = frame.merge(
            raw_share[["hex_id", "potential_area_share_pct", "potential_area_km2"]],
            on="hex_id",
            how="left",
        )
    frame["potential_area_share_pct"] = frame["potential_area_share_pct"].fillna(0.0).astype(float).clip(lower=0.0, upper=100.0)
    if "potential_area_km2" not in frame.columns:
        frame["potential_area_km2"] = 0.0
    frame["potential_area_km2"] = pd.to_numeric(frame["potential_area_km2"], errors="coerce").fillna(0.0).clip(lower=0.0)
    frame["potential_area_share"] = frame["potential_area_share_pct"].div(100.0).round(4)

    class_specs = []
    for share_value in frame["potential_area_share_pct"]:
        class_spec = _wind_share_class_spec(float(share_value))
        class_specs.append((class_spec["id"], class_spec["label"], WIND_SHARE_CLASS_SPECS.index(class_spec)))
    frame["share_class_id"] = [item[0] for item in class_specs]
    frame["share_class_label"] = [item[1] for item in class_specs]
    frame["share_class_index"] = [item[2] for item in class_specs]

    frame = _wind_runtime_hex_core_scores(frame, _wind_runtime_hex_neighbor_map(display_geometry_path))
    frame["fill"] = [
        _wind_runtime_hex_color(share_value, core_value, zone_size)
        for share_value, core_value, zone_size in zip(
            frame["potential_area_share_pct"],
            frame["core_score"],
            frame["zone_size"],
        )
    ]
    frame["core_label"] = [
        _wind_core_label(core_value, zone_size)
        for core_value, zone_size in zip(frame["core_score"], frame["zone_size"])
    ]
    frame["stroke"] = frame["fill"].map(lambda value: _mix_hex_colors(str(value), "#3a3a3a", 0.28))
    return frame.sort_values("hex_id").reset_index(drop=True)


def _target_resolution_distance_frame(
    distance_frame: pd.DataFrame,
    target_resolution: int,
    display_geometry_path: str,
) -> pd.DataFrame:
    if distance_frame.empty or "hex_id" not in distance_frame.columns:
        return pd.DataFrame(columns=["hex_id", "distance_m", "intersects"])
    work = distance_frame[["hex_id", "distance_m", "intersects"]].copy()
    work["hex_id"] = work["hex_id"].astype(str)
    try:
        source_resolution = int(h3.get_resolution(str(work["hex_id"].iloc[0])))
    except Exception:
        source_resolution = int(target_resolution)
    if source_resolution > int(target_resolution):
        work["hex_id"] = work["hex_id"].map(lambda value: str(h3.cell_to_parent(str(value), int(target_resolution))))
        work = (
            work.groupby("hex_id", as_index=False)
            .agg(distance_m=("distance_m", "min"), intersects=("intersects", "max"))
        )
    elif source_resolution < int(target_resolution):
        work["source_hex_id"] = work["hex_id"].astype(str)
        display_geometries = load_h3_display_geometries(display_geometry_path)
        target = pd.DataFrame({"hex_id": list(display_geometries.keys())})
        if not target.empty:
            target["source_hex_id"] = target["hex_id"].map(lambda value: str(h3.cell_to_parent(str(value), source_resolution)))
            source_work = work[["source_hex_id", "distance_m", "intersects"]].copy()
            work = target.merge(source_work, on="source_hex_id", how="left")[["hex_id", "distance_m", "intersects"]]
    work["distance_m"] = pd.to_numeric(work["distance_m"], errors="coerce")
    work["intersects"] = work["intersects"].fillna(False).astype(bool)
    return work[["hex_id", "distance_m", "intersects"]].copy()


def _wind_establishment_intersection_block_frame(
    region: dict[str, Any],
    runtime_result: dict[str, Any],
    target_resolution: int,
) -> pd.DataFrame:
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame(columns=["hex_id", "wind_hard_exclusion_intersects"])
    groups_meta = runtime_result.get("groups") if isinstance(runtime_result, dict) else None
    if not isinstance(groups_meta, dict):
        return pd.DataFrame(columns=["hex_id", "wind_hard_exclusion_intersects"])
    if not any(isinstance(groups_meta.get(group_id), dict) and
               groups_meta[group_id].get("active_layer_ids")
               for group_id in WIND_ESTABLISHMENT_INTERSECTION_BLOCK_GROUP_IDS):
        return pd.DataFrame(columns=["hex_id", "wind_hard_exclusion_intersects"])
    _, _, registry_meta = load_acceptance_registry()
    frames: list[pd.DataFrame] = []
    for group_id in WIND_ESTABLISHMENT_INTERSECTION_BLOCK_GROUP_IDS:
        group_meta = groups_meta.get(group_id)
        if not isinstance(group_meta, dict):
            continue
        layer_ids = [str(layer_id) for layer_id in (group_meta.get("active_layer_ids") or [])]
        for layer_id in _solar_available_filter_layer_ids(group_id, layer_ids):
            distance_frame = _target_resolution_distance_frame(
                distance_table_for_layer(registry_meta, layer_id),
                int(target_resolution),
                display_geometry_path,
            )
            if distance_frame.empty:
                continue
            blocked = distance_frame.loc[distance_frame["intersects"].astype(bool), ["hex_id"]].copy()
            if not blocked.empty:
                frames.append(blocked)
    if not frames:
        return pd.DataFrame(columns=["hex_id", "wind_hard_exclusion_intersects"])
    combined = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["hex_id"])
    combined["wind_hard_exclusion_intersects"] = True
    return combined[["hex_id", "wind_hard_exclusion_intersects"]]


def _allocation_priority_distance_cap_m(group: Any) -> float:
    candidates = [
        float(getattr(group, "analysis_max_m", 0.0) or 0.0),
        float(getattr(group, "analysis_default_m", 0.0) or 0.0) * 2.0,
        float(getattr(group, "analysis_step_m", 0.0) or 0.0) * 20.0,
    ]
    cap = max([value for value in candidates if math.isfinite(value) and value > 0.0] or [1000.0])
    return max(cap, 1.0)


def _allocation_priority_layer_groups(
    region_id: str,
    technology: str,
) -> list[dict[str, Any]]:
    groups, layers, registry_meta = load_acceptance_registry(region_id)
    availability = _wind_layer_status_lookup(registry_meta)
    canonical_roads_group: WindGroupControlContract | None = None
    canonical_roads_ids: tuple[str, ...] = ()
    canonical_population_group: WindGroupControlContract | None = None
    canonical_population_ids: tuple[str, ...] = ()
    canonical_nature_group: WindGroupControlContract | None = None
    canonical_nature_ids: tuple[str, ...] = ()
    canonical_culture_group: WindGroupControlContract | None = None
    canonical_culture_ids: tuple[str, ...] = ()
    canonical_grid_group: WindGroupControlContract | None = None
    canonical_grid_ids: tuple[str, ...] = ()
    raw_groups: list[tuple[str, list[str]]] = []
    if str(technology) == "solar":
        raw_groups.append((SOLAR_POPULATION_GROUP_ID, [WIND_POPULATION_SOURCE_LAYER_ID]))
        for group_id in SOLAR_FILTER_GROUP_IDS:
            canonical_group_id = SOLAR_AREA_CANONICAL_GROUP_IDS.get(
                str(group_id)
            )
            if canonical_group_id is not None:
                canonical_group = analysis_group_control_contract(
                    str(region_id),
                    "solar",
                    canonical_group_id,
                    public_group_id=str(group_id),
                )
                layer_ids = [layer.id for layer in canonical_group.layers]
            else:
                layer_ids = list(_solar_filter_layer_ids(group_id))
            raw_groups.append((group_id, layer_ids))
    else:
        canonical_roads_group = analysis_group_control_contract(
            region_id,
            "wind",
            CANONICAL_ROADS_GROUP_ID,
        )
        unavailable_roads_ids = [
            layer.id
            for layer in canonical_roads_group.layers
            if not layer.ready
        ]
        if unavailable_roads_ids:
            raise ValueError(
                f"{region_id}/wind canonical roads ranking layers are not "
                f"ready: {unavailable_roads_ids}"
            )
        canonical_roads_ids = tuple(
            layer.id for layer in canonical_roads_group.layers
        )
        raw_groups.append(
            (WIND_ROADS_GROUP_ID, list(canonical_roads_ids))
        )
        canonical_population_group = analysis_group_control_contract(
            region_id,
            "wind",
            CANONICAL_POPULATION_GROUP_ID,
        )
        unavailable_population_ids = [
            layer.id
            for layer in canonical_population_group.layers
            if not layer.ready
        ]
        if unavailable_population_ids:
            raise ValueError(
                f"{region_id}/wind canonical population ranking layers are not "
                f"ready: {unavailable_population_ids}"
            )
        canonical_population_ids = tuple(
            layer.id for layer in canonical_population_group.layers
        )
        raw_groups.append(
            (WIND_POPULATION_GROUP_ID, list(canonical_population_ids))
        )
        canonical_nature_group = analysis_group_control_contract(
            region_id,
            "wind",
            CANONICAL_NATURE_GROUP_ID,
        )
        unavailable_nature_ids = [
            layer.id
            for layer in canonical_nature_group.layers
            if not layer.ready
        ]
        if unavailable_nature_ids:
            raise ValueError(
                f"{region_id}/wind canonical nature ranking layers are not "
                f"ready: {unavailable_nature_ids}"
            )
        canonical_nature_ids = tuple(
            layer.id for layer in canonical_nature_group.layers
        )
        raw_groups.append(
            (WIND_NATURE_GROUP_ID, list(canonical_nature_ids))
        )
        canonical_culture_group = analysis_group_control_contract(
            region_id,
            "wind",
            CANONICAL_CULTURE_GROUP_ID,
        )
        unavailable_culture_ids = [
            layer.id
            for layer in canonical_culture_group.layers
            if not layer.ready
        ]
        if unavailable_culture_ids:
            raise ValueError(
                f"{region_id}/wind canonical culture ranking layers are not "
                f"ready: {unavailable_culture_ids}"
            )
        canonical_culture_ids = tuple(
            layer.id for layer in canonical_culture_group.layers
        )
        raw_groups.append(
            (WIND_CULTURE_GROUP_ID, list(canonical_culture_ids))
        )
        canonical_grid_group = analysis_group_control_contract(
            region_id,
            "wind",
            CANONICAL_GRID_GROUP_ID,
        )
        unavailable_grid_ids = [
            layer.id
            for layer in canonical_grid_group.layers
            if not layer.ready
        ]
        if unavailable_grid_ids:
            raise ValueError(
                f"{region_id}/wind canonical grid-infrastructure ranking "
                f"layers are not ready: {unavailable_grid_ids}"
            )
        canonical_grid_ids = tuple(
            layer.id for layer in canonical_grid_group.layers
        )
        raw_groups.append(
            (WIND_GRID_GROUP_ID, list(canonical_grid_ids))
        )
        for group_id, layer_ids in WIND_GROUP_LAYER_DEFAULTS.items():
            if group_id in {
                SOLAR_POPULATION_GROUP_ID,
                SOLAR_PROTECTED_GROUP_ID,
                WIND_CULTURE_GROUP_ID,
                SOLAR_ELECTRICAL_GROUP_ID,
            }:
                continue
            raw_groups.append((group_id, list(layer_ids)))

    specs: list[dict[str, Any]] = []
    seen_group_ids: set[str] = set()
    for group_id, layer_ids in raw_groups:
        if group_id in seen_group_ids:
            continue
        seen_group_ids.add(group_id)
        canonical_layer_ids: list[str] = []
        canonical_group_id: str | None = None
        if str(technology) == "wind" and group_id in {
            WIND_ROADS_GROUP_ID,
            WIND_POPULATION_GROUP_ID,
            WIND_NATURE_GROUP_ID,
            WIND_CULTURE_GROUP_ID,
            WIND_GRID_GROUP_ID,
        }:
            canonical_group = (
                canonical_roads_group
                if group_id == WIND_ROADS_GROUP_ID
                else canonical_population_group
                if group_id == WIND_POPULATION_GROUP_ID
                else canonical_nature_group
                if group_id == WIND_NATURE_GROUP_ID
                else canonical_culture_group
                if group_id == WIND_CULTURE_GROUP_ID
                else canonical_grid_group
            )
            canonical_ids = (
                canonical_roads_ids
                if group_id == WIND_ROADS_GROUP_ID
                else canonical_population_ids
                if group_id == WIND_POPULATION_GROUP_ID
                else canonical_nature_ids
                if group_id == WIND_NATURE_GROUP_ID
                else canonical_culture_ids
                if group_id == WIND_CULTURE_GROUP_ID
                else canonical_grid_ids
            )
            if canonical_group is None or not canonical_ids:
                raise ValueError(
                    f"{region_id}/wind declares no canonical {group_id} "
                    "ranking layers"
                )
            group = canonical_group
            canonical_group_id = str(group_id)
            canonical_layer_ids = list(canonical_ids)
            layer_ids = [
                str(layer_id)
                for layer_id in layer_ids
                if str(layer_id) not in set(canonical_ids)
            ]
        elif str(technology) == "solar":
            canonical_group_id = (
                CANONICAL_POPULATION_GROUP_ID
                if group_id == SOLAR_POPULATION_GROUP_ID
                else SOLAR_AREA_CANONICAL_GROUP_IDS.get(str(group_id))
            )
            if canonical_group_id is not None:
                group = analysis_group_control_contract(
                    str(region_id),
                    "solar",
                    canonical_group_id,
                    public_group_id=str(group_id),
                )
                available_canonical_ids = {
                    layer.id for layer in group.layers if layer.ready
                }
                requested_canonical_ids = [
                    str(layer_id)
                    for layer_id in layer_ids
                    if str(layer_id) in available_canonical_ids
                ]
                if not requested_canonical_ids:
                    raise ValueError(
                        f"{region_id}/solar declares no ready canonical "
                        f"{canonical_group_id} ranking layers for {group_id}"
                    )
                canonical_layer_ids = requested_canonical_ids
                layer_ids = [
                    str(layer_id)
                    for layer_id in layer_ids
                    if str(layer_id) not in set(canonical_layer_ids)
                ]
            else:
                group = groups.get(group_id)
        else:
            group = groups.get(group_id)
        if group is None:
            continue
        ready_layer_ids = [
            str(layer_id)
            for layer_id in layer_ids
            if str(layer_id) in layers and _wind_layer_is_ready(str(layer_id), availability)
        ]
        if not ready_layer_ids and not canonical_layer_ids:
            continue
        specs.append(
            {
                "group_id": str(group_id),
                "group": group,
                "layer_ids": ready_layer_ids,
                "canonical_group_id": (
                    canonical_group_id
                    if canonical_layer_ids
                    else None
                ),
                "canonical_layer_ids": canonical_layer_ids,
                "label": group_label(group, WIND_CONTROL_LANGUAGE, group.label),
                "analysis_kind": str(group.analysis_kind),
                "required_for_allocation": bool(canonical_layer_ids),
            }
        )
    return specs


def _allocation_priority_group_score(
    analysis_kind: str,
    min_distance_m: pd.Series,
    any_intersection: pd.Series,
    cap_m: float,
) -> tuple[pd.Series, str]:
    distance = pd.to_numeric(min_distance_m, errors="coerce")
    intersects = any_intersection.fillna(False).astype(bool)
    cap = max(float(cap_m or 0.0), 1.0)
    score = pd.Series(
        [
            (
                landscape_group_score(
                    analysis_kind=str(analysis_kind),
                    distance_m=float(value),
                    intersects=bool(intersection),
                    distance_cap_m=cap,
                )
                if pd.notna(value)
                else 0.0
            )
            for value, intersection in zip(distance, intersects)
        ],
        index=distance.index,
        dtype=float,
    )
    return score, (
        "proximity"
        if str(analysis_kind) == "proximity_feasibility"
        else "clearance"
    )


def _allocation_priority_reason(row: Any, components: list[dict[str, str]]) -> str:
    strengths: list[str] = []
    compromises: list[str] = []
    for component in components:
        try:
            value = float(getattr(row, component["column"], 0.0) or 0.0)
        except Exception:
            value = 0.0
        label = str(component["label"]).lower()
        if component["role"] == "proximity":
            if value >= 0.67:
                strengths.append(f"nära {label}")
            elif value <= 0.33:
                compromises.append(f"långt från {label}")
        else:
            if value >= 0.67:
                strengths.append(f"långt från {label}")
            elif value <= 0.33:
                compromises.append(f"nära {label}")
    parts: list[str] = []
    if strengths:
        parts.append("Styrkor: " + ", ".join(strengths[:3]))
    if compromises:
        parts.append("Kompromiss: " + ", ".join(compromises[:2]))
    return ". ".join(parts) if parts else "Balanserad placering enligt landskaps- och teknikranking."


@st.cache_data(show_spinner=False, max_entries=24)
def _cached_technology_support_observation_frame(
    region_id: str,
    technology: str,
    layer_ids: tuple[str, ...],
    target_resolution: int,
) -> pd.DataFrame:
    return technology_support_observation_frame(
        str(region_id),
        str(technology),
        tuple(layer_ids),
        int(target_resolution),
    )


def _apply_landscape_priority_to_allocation_frame(
    frame: pd.DataFrame,
    region: dict[str, Any],
    technology: str,
    target_resolution: int,
) -> pd.DataFrame:
    if frame.empty or "hex_id" not in frame.columns:
        return frame
    display_geometry_path = _area_display_geometry_path(
        region,
        int(target_resolution),
    )
    if not display_geometry_path:
        raise ValueError(
            "Teknikallokering kräver en verifierad etableringsgeometri."
        )

    work = frame.copy()
    work["hex_id"] = work["hex_id"].astype(str)
    region_id = str(region.get("region_id") or "").strip().lower()
    _, _, registry_meta = load_acceptance_registry(region_id)
    component_cols: list[str] = []
    component_observed_cols: list[str] = []
    required_component_cols: list[str] = []
    required_observed_cols: list[str] = []
    required_component_meta: list[dict[str, str]] = []
    optional_component_cols: list[str] = []
    optional_observed_cols: list[str] = []
    for spec in _allocation_priority_layer_groups(region_id, str(technology)):
        group_id = str(spec["group_id"])
        group = spec["group"]
        if group is None:
            continue
        parts: list[pd.DataFrame] = []
        canonical_layer_ids = [
            str(layer_id)
            for layer_id in spec.get("canonical_layer_ids", [])
        ]
        if canonical_layer_ids:
            canonical_group_id = str(spec.get("canonical_group_id") or "")
            if canonical_group_id not in {
                CANONICAL_ROADS_GROUP_ID,
                CANONICAL_POPULATION_GROUP_ID,
                CANONICAL_NATURE_GROUP_ID,
                CANONICAL_CULTURE_GROUP_ID,
                CANONICAL_GRID_GROUP_ID,
            }:
                raise ValueError(
                    "Unsupported canonical allocation-ranking group: "
                    f"{canonical_group_id or '<blank>'}"
                )
            canonical_frame = _cached_technology_support_observation_frame(
                region_id,
                str(technology),
                tuple(canonical_layer_ids),
                int(target_resolution),
            )
            parts.append(canonical_frame)
        for layer_id in spec["layer_ids"]:
            layer_frame = _target_resolution_distance_frame(
                distance_table_for_layer(registry_meta, str(layer_id)),
                int(target_resolution),
                display_geometry_path,
            )
            if not layer_frame.empty:
                parts.append(layer_frame)
        if not parts:
            continue
        merged = work[["hex_id"]].copy()
        distance_cols: list[str] = []
        intersect_cols: list[str] = []
        for idx, part in enumerate(parts):
            distance_col = f"distance_{idx}"
            intersect_col = f"intersects_{idx}"
            merged = merged.merge(
                part.rename(columns={"distance_m": distance_col, "intersects": intersect_col}),
                on="hex_id",
                how="left",
            )
            distance_cols.append(distance_col)
            intersect_cols.append(intersect_col)
        if not distance_cols:
            continue
        intersection_frame = pd.DataFrame(
            {
                column: merged[column].where(merged[column].notna(), False).astype(bool)
                for column in intersect_cols
            }
        )
        score, role = _allocation_priority_group_score(
            str(spec["analysis_kind"]),
            merged[distance_cols].min(axis=1, skipna=True),
            intersection_frame.any(axis=1),
            _allocation_priority_distance_cap_m(group),
        )
        column = f"allocation_priority_component_{group_id}"
        observed_column = f"{column}__observed"
        observed = merged[distance_cols].notna().any(axis=1)
        work[column] = score.astype(float).where(observed).clip(
            lower=0.0,
            upper=1.0,
        )
        work[observed_column] = observed.astype(bool)
        component_cols.append(column)
        component_observed_cols.append(observed_column)
        metadata = {
            "column": column,
            "label": str(spec["label"]),
            "role": role,
        }
        if bool(spec.get("required_for_allocation", False)):
            required_component_cols.append(column)
            required_observed_cols.append(observed_column)
            required_component_meta.append(metadata)
        else:
            optional_component_cols.append(column)
            optional_observed_cols.append(observed_column)

    work = apply_allocation_context_completeness(
        work,
        required_observed_columns=required_observed_cols,
        optional_observed_columns=optional_observed_cols,
    )
    if required_component_cols:
        work["landscape_priority_score"] = work[
            required_component_cols
        ].mean(
            axis=1,
            skipna=True,
        ).clip(lower=0.0, upper=1.0)
        reason_frame = work[required_component_cols].copy()
        work["allocation_priority_reason"] = [
            _allocation_priority_reason(row, required_component_meta)
            for row in reason_frame.itertuples(index=False)
        ]
        work.loc[
            work["allocation_context_status"].eq("missing"),
            "allocation_priority_reason",
        ] = "Teknisk ranking saknas för teknikdomänens cell."
        work.loc[
            work["allocation_context_status"].eq("partial"),
            "allocation_priority_reason",
        ] = "Teknisk ranking är ofullständig för teknikdomänens cell."
    else:
        work["landscape_priority_score"] = math.nan
        work["allocation_priority_reason"] = "Teknisk ranking saknas."
    optional_unknown = work["allocation_optional_context_status"].isin(
        {"missing", "partial"}
    )
    work.loc[optional_unknown, "allocation_priority_reason"] = (
        work.loc[optional_unknown, "allocation_priority_reason"].astype(str)
        + " Valfri kompletterande kontext är ofullständig och påverkar inte "
        "rankingen."
    )

    if str(technology) == "wind":
        share_source = work["potential_area_share_pct"] if "potential_area_share_pct" in work.columns else pd.Series(0.0, index=work.index)
        core_source = work["core_score"] if "core_score" in work.columns else pd.Series(0.0, index=work.index)
        share = pd.to_numeric(share_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0).div(100.0)
        core = pd.to_numeric(core_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=1.0)
        weights = TechnicalRankingWeights(
            technology_id="wind",
            landscape=0.65,
            potential=0.20,
            core=0.15,
        )
        work["allocation_priority_score"] = [
            technical_priority_score(
                landscape_score=float(landscape),
                potential_fraction=float(potential),
                core_score=float(core_value),
                weights=weights,
            )
            for landscape, potential, core_value in zip(
                work["landscape_priority_score"], share, core
            )
        ]
        work["core_score_before_allocation_priority"] = core
        work["core_score"] = work["allocation_priority_score"]
    else:
        if "potential_score" in work.columns:
            potential_source = work["potential_score"]
        elif "solar_score" in work.columns:
            potential_source = work["solar_score"]
        else:
            potential_source = work.get("potential_area_share_pct", pd.Series(0.0, index=work.index))
        potential = pd.to_numeric(potential_source, errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0).div(100.0)
        weights = TechnicalRankingWeights(
            technology_id="solar",
            landscape=0.75,
            potential=0.25,
            core=0.0,
        )
        work["allocation_priority_score"] = [
            technical_priority_score(
                landscape_score=float(landscape),
                potential_fraction=float(potential_value),
                core_score=0.0,
                weights=weights,
            )
            for landscape, potential_value in zip(
                work["landscape_priority_score"], potential
            )
        ]
    work["technical_priority_score"] = work["allocation_priority_score"]
    return work.drop(
        columns=[*component_cols, *component_observed_cols],
        errors="ignore",
    )


def _acceptance_series_for_group(
    analysis_kind: str,
    min_distance_m: pd.Series,
    any_intersection: pd.Series,
    threshold_m: float,
    distance_conflict_semantics: str,
) -> pd.Series:
    distance = pd.to_numeric(min_distance_m, errors="coerce")
    intersects = any_intersection.fillna(False).astype(bool)
    threshold = float(threshold_m or 0.0)
    if str(analysis_kind) == "proximity_feasibility":
        capped = max(threshold, 1.0)
        acceptance = (1.0 - (distance / capped)).clip(lower=0.0, upper=1.0).fillna(0.0)
        acceptance.loc[intersects] = 1.0
        return acceptance
    if str(analysis_kind) == "hard_exclusion":
        blocked = intersects if threshold <= 0 else (intersects | distance.le(threshold).fillna(False))
        return (~blocked).astype(float)
    if threshold <= 0:
        return (~intersects).astype(float)
    if str(distance_conflict_semantics) != "soft_ramp":
        raise ValueError(
            "Unsupported distance-conflict semantics: "
            f"{distance_conflict_semantics}"
        )
    ramp_end = max(float(threshold * 2.0), float(threshold + 1.0))
    acceptance = ((distance - threshold) / (ramp_end - threshold)).clip(lower=0.0, upper=1.0).fillna(0.0)
    acceptance.loc[intersects] = 0.0
    return acceptance


@st.cache_data(show_spinner=False, max_entries=12)
def _cached_standard_result_surface_cell_areas_km2(
    region_id: str,
    resolution: int,
) -> dict[str, float]:
    return standard_result_surface_cell_areas_km2(
        str(region_id),
        int(resolution),
    )


@st.cache_data(show_spinner=False, max_entries=12)
def _cached_technology_support_cell_areas_km2(
    region_id: str,
    technology: str,
    resolution: int,
) -> dict[str, float]:
    return technology_support_domain_cell_areas_km2(
        str(region_id),
        str(technology),
        int(resolution),
    )


def _cached_wind_analysis_domain_cell_areas_km2(
    region_id: str,
    resolution: int,
) -> dict[str, float]:
    """Compatibility wrapper for the frozen standard result surface."""

    return _cached_standard_result_surface_cell_areas_km2(
        region_id,
        resolution,
    )


def _technology_support_cell_area_km2_series(
    frame: pd.DataFrame,
    region_id: str,
    technology: str,
    resolution: int,
) -> pd.Series:
    if "hex_id" not in frame.columns:
        raise ValueError("An analysis-domain area lookup requires hex_id")
    area_lookup = _cached_technology_support_cell_areas_km2(
        str(region_id),
        str(technology),
        int(resolution),
    )
    areas = frame["hex_id"].astype(str).map(area_lookup)
    if areas.isna().any():
        missing = frame.loc[areas.isna(), "hex_id"].astype(str).head(5).tolist()
        raise ValueError(
            "Analysis-domain cell area is missing for: " + ", ".join(missing)
        )
    return pd.to_numeric(areas, errors="raise").astype(float)


def _wind_analysis_domain_cell_area_km2_series(
    frame: pd.DataFrame,
    region_id: str,
    resolution: int,
) -> pd.Series:
    """Return frozen standard-group result areas for the frame cells."""

    if "hex_id" not in frame.columns:
        raise ValueError("A standard-result area lookup requires hex_id")
    area_lookup = _cached_standard_result_surface_cell_areas_km2(
        str(region_id),
        int(resolution),
    )
    areas = frame["hex_id"].astype(str).map(area_lookup)
    if areas.isna().any():
        missing = frame.loc[areas.isna(), "hex_id"].astype(str).head(5).tolist()
        raise ValueError(
            "Standard-result cell area is missing for: " + ", ".join(missing)
        )
    return pd.to_numeric(areas, errors="raise").astype(float)


def _finalize_fast_wind_share_frame(
    frame: pd.DataFrame,
    display_geometry_path: str,
    region_id: str,
    target_resolution: int,
    compute_core: bool = True,
    area_scope: str = "standard_result",
) -> pd.DataFrame:
    work = frame.copy()
    work["potential_area_share_pct"] = pd.to_numeric(work["potential_area_share_pct"], errors="coerce").fillna(0.0).clip(
        lower=0.0,
        upper=100.0,
    )
    if area_scope == "standard_result":
        work["display_area_km2"] = (
            _wind_analysis_domain_cell_area_km2_series(
                work,
                region_id,
                int(target_resolution),
            )
        )
    elif area_scope == "technology_support":
        work["display_area_km2"] = _technology_support_cell_area_km2_series(
            work,
            region_id,
            "wind",
            int(target_resolution),
        )
    else:
        raise ValueError(f"Unsupported wind area scope: {area_scope}")
    if "potential_area_km2" not in work.columns:
        work["potential_area_km2"] = (
            work["potential_area_share_pct"].div(100.0)
            * work["display_area_km2"]
        )
    work["potential_area_km2"] = pd.to_numeric(work["potential_area_km2"], errors="coerce").fillna(0.0).clip(lower=0.0)
    work["potential_area_share"] = work["potential_area_share_pct"].div(100.0).round(4)
    class_specs = [_wind_share_class_spec(float(value)) for value in work["potential_area_share_pct"]]
    work["share_class_id"] = [str(item["id"]) for item in class_specs]
    work["share_class_label"] = [str(item["label"]) for item in class_specs]
    work["share_class_index"] = [WIND_SHARE_CLASS_SPECS.index(item) for item in class_specs]
    if compute_core:
        work = _wind_runtime_hex_core_scores(work, _wind_runtime_hex_neighbor_map(display_geometry_path))
    else:
        work["core_score"] = 0.0
        work["zone_size"] = 1
        work["center_mass_rank"] = 1
    work["fill"] = [
        _wind_runtime_hex_color(share_value, core_value, zone_size)
        for share_value, core_value, zone_size in zip(work["potential_area_share_pct"], work["core_score"], work["zone_size"])
    ]
    work["core_label"] = [_wind_core_label(core_value, zone_size) for core_value, zone_size in zip(work["core_score"], work["zone_size"])]
    work["stroke"] = work["fill"].map(lambda value: _mix_hex_colors(str(value), "#3a3a3a", 0.28))
    return work.sort_values("hex_id").reset_index(drop=True)


def _workspace_bundle_presentation_signature(
    bundle: WorkspaceExecutionBundle,
    request: WorkspaceAnalysisRequest,
) -> str:
    """Link one trusted bundle binding to its independently built adapter."""

    if not isinstance(bundle, WorkspaceExecutionBundle):
        raise TypeError("Workspace execution bundle has an invalid type")
    if (
        bundle.access_scope != request.access_scope
        or bundle.region_id != request.region_id
        or bundle.target_resolution != request.target_resolution
        or bundle.app_adapter.access_scope != request.access_scope
        or bundle.app_adapter.region_id != request.region_id
        or bundle.app_adapter.target_resolution != request.target_resolution
    ):
        raise ValueError("Workspace execution bundle escaped its request")
    adapter_analysis_ids = tuple(
        value.analysis_id for value in bundle.app_adapter.presentations
    )
    if (
        not bundle.analysis_ids
        or len(bundle.analysis_ids) != len(set(bundle.analysis_ids))
        or adapter_analysis_ids != bundle.analysis_ids
    ):
        raise ValueError("Workspace execution bundle analyses drifted")
    binding = bundle.binding(request.analysis_id)
    if binding.request != request:
        raise ValueError("Workspace execution binding escaped its request")
    adapter_binding = next(
        value
        for value in bundle.app_adapter.presentations
        if value.analysis_id == request.analysis_id
    )
    if (
        adapter_binding.presentation_signature_sha256
        != binding.presentation.presentation_signature_sha256
    ):
        raise ValueError("Workspace execution presentation signature drifted")
    standard_domains = tuple(
        value
        for value in binding.presentation.domains
        if value.role == "standard_analysis"
    )
    if len(standard_domains) != 1:
        raise ValueError("Workspace execution standard domain drifted")
    standard_domain = standard_domains[0]
    presentation_domain_ref = (
        f"{request.analysis_id}::{standard_domain.domain_id}"
    )
    adapter_domains = tuple(
        value
        for value in bundle.app_adapter.domains
        if presentation_domain_ref in value.presentation_domain_refs
    )
    if (
        len(adapter_domains) != 1
        or adapter_domains[0].role != "standard_analysis"
        or adapter_domains[0].resolution != request.target_resolution
        or adapter_domains[0].source_sha256 != standard_domain.source_sha256
        or adapter_domains[0].cell_ids_sha256
        != standard_domain.cell_ids_sha256
        or adapter_domains[0].cell_count != standard_domain.cell_count
    ):
        raise ValueError("Workspace execution adapter domain drifted")
    adapter_domain = adapter_domains[0]
    group_results = tuple(
        value
        for value in binding.presentation.results
        if value.result_id.startswith("group:")
    )
    group_tables = tuple(
        value
        for value in bundle.app_adapter.result_tables
        if value.analysis_id == request.analysis_id
        and value.source_result_id.startswith("group:")
    )
    if tuple(value.result_id for value in group_results) != tuple(
        f"group:{group.group_id}" for group in request.groups
    ) or tuple(value.source_result_id for value in group_tables) != tuple(
        value.result_id for value in group_results
    ):
        raise ValueError("Workspace execution group result order drifted")
    for result, table in zip(group_results, group_tables, strict=True):
        table_metrics = tuple(
            value
            for value in bundle.app_adapter.metrics
            if value.table_id == table.table_id
        )
        if (
            table.table_id
            != f"{request.analysis_id}::{result.result_id}"
            or table.analysis_id != request.analysis_id
            or table.source_result_id != result.result_id
            or result.domain_id != standard_domain.domain_id
            or table.domain_key != adapter_domain.domain_key
            or table.presentation_signature_sha256
            != binding.presentation.presentation_signature_sha256
            or table.row_count != len(result.rows)
            or tuple(value.field_id for value in table.columns)
            != tuple(value.field_id for value in result.fields)
            or not (table.rows is result.rows or table.rows == result.rows)
            or any(
                value.presentation_signature_sha256
                != binding.presentation.presentation_signature_sha256
                for value in table_metrics
            )
            or tuple(
                (
                    value.source_metric_id,
                    float(value.value),
                    value.unit,
                )
                for value in table_metrics
            )
            != tuple(
                (value.metric_id, float(value.value), value.unit)
                for value in result.metrics
            )
        ):
            raise ValueError("Workspace execution adapter table drifted")
    return adapter_binding.presentation_signature_sha256


def _workspace_wind_group_frames_from_binding(
    binding: WorkspaceExecutionBinding,
    request: WorkspaceAnalysisRequest,
    expected_presentation_signature_sha256: str,
) -> tuple[tuple[str, tuple[str, ...], float, int, pd.DataFrame], ...]:
    """Adapt signed standard-result rows without recreating engine cells."""

    if not isinstance(binding, WorkspaceExecutionBinding):
        raise TypeError("Wind workspace binding has an invalid type")
    if binding.execution_state is not WorkspaceExecutionState.APPLIED:
        raise ValueError("Wind workspace binding is not applied")
    presentation = binding.presentation
    if (
        not isinstance(expected_presentation_signature_sha256, str)
        or len(expected_presentation_signature_sha256) != 64
        or any(
            value not in "0123456789abcdef"
            for value in expected_presentation_signature_sha256
        )
        or presentation.presentation_signature_sha256
        != expected_presentation_signature_sha256
    ):
        raise ValueError("Wind workspace presentation signature drifted")
    if (
        binding.request != request
        or presentation.request != request
        or presentation.access_scope != request.access_scope
        or presentation.region_id != request.region_id
        or presentation.analysis_id != request.analysis_id
        or presentation.target_resolution != request.target_resolution
    ):
        raise ValueError("Wind workspace binding escaped its request")

    expected_result_ids = tuple(
        f"group:{group.group_id}" for group in request.groups
    )
    group_presentations = tuple(
        value
        for value in presentation.results
        if value.result_id.startswith("group:")
    )
    if tuple(value.result_id for value in group_presentations) != (
        expected_result_ids
    ):
        raise ValueError("Wind workspace group presentation order drifted")
    result_by_id = {
        value.result_id: value for value in group_presentations
    }
    expected_fields = (
        "cell_id",
        "min_distance_m",
        "any_intersection",
        "blocked",
        "acceptance",
        "coverage_missing",
    )
    expected_metrics = (
        "cell_count",
        "blocked_cell_count",
        "accepted_cell_count",
        "coverage_missing_cell_count",
        "mean_acceptance",
        "threshold_m",
    )
    groups: list[
        tuple[str, tuple[str, ...], float, int, pd.DataFrame]
    ] = []
    for applied_group in request.groups:
        result = result_by_id[f"group:{applied_group.group_id}"]
        if tuple(value.field_id for value in result.fields) != expected_fields:
            raise ValueError("Wind workspace group fields drifted")
        if tuple(value.metric_id for value in result.metrics) != expected_metrics:
            raise ValueError("Wind workspace group metrics drifted")
        metrics = {value.metric_id: float(value.value) for value in result.metrics}
        if any(not math.isfinite(value) for value in metrics.values()):
            raise ValueError("Wind workspace group metrics are not finite")

        count_metrics = {
            key: metrics[key]
            for key in (
                "cell_count",
                "blocked_cell_count",
                "accepted_cell_count",
                "coverage_missing_cell_count",
            )
        }
        if any(
            value < 0.0 or not value.is_integer()
            for value in count_metrics.values()
        ):
            raise ValueError("Wind workspace group counts are invalid")
        threshold_m = metrics["threshold_m"]
        if threshold_m < 0.0:
            raise ValueError("Wind workspace group threshold is invalid")

        cell_ids: list[str] = []
        acceptance_values: list[float] = []
        blocked_values: list[bool] = []
        missing_values: list[bool] = []
        for row in result.rows:
            if not isinstance(row, tuple) or len(row) != len(expected_fields):
                raise ValueError("Wind workspace group row shape drifted")
            cell_id, distance, intersects, blocked, acceptance, missing = row
            if not isinstance(cell_id, str) or not cell_id:
                raise ValueError("Wind workspace group cell id is invalid")
            if distance is not None and (
                isinstance(distance, bool)
                or not isinstance(distance, (int, float))
                or not math.isfinite(float(distance))
                or float(distance) < 0.0
            ):
                raise ValueError("Wind workspace group distance is invalid")
            if (
                not isinstance(intersects, bool)
                or not isinstance(blocked, bool)
                or not isinstance(missing, bool)
                or isinstance(acceptance, bool)
                or not isinstance(acceptance, (int, float))
                or not math.isfinite(float(acceptance))
                or float(acceptance) < 0.0
                or float(acceptance) > 1.0
            ):
                raise ValueError("Wind workspace group values are invalid")
            cell_ids.append(cell_id)
            acceptance_values.append(float(acceptance))
            blocked_values.append(blocked)
            missing_values.append(missing)

        cell_count = int(count_metrics["cell_count"])
        blocked_cell_count = int(count_metrics["blocked_cell_count"])
        accepted_cell_count = int(count_metrics["accepted_cell_count"])
        coverage_missing_cell_count = int(
            count_metrics["coverage_missing_cell_count"]
        )
        mean_acceptance = (
            math.fsum(acceptance_values) / len(acceptance_values)
            if acceptance_values
            else 0.0
        )
        if (
            len(cell_ids) != cell_count
            or len(cell_ids) != len(set(cell_ids))
            or sum(blocked_values) != blocked_cell_count
            or cell_count - blocked_cell_count != accepted_cell_count
            or sum(missing_values) != coverage_missing_cell_count
            or not math.isclose(
                mean_acceptance,
                metrics["mean_acceptance"],
                rel_tol=0.0,
                abs_tol=1e-12,
            )
        ):
            raise ValueError("Wind workspace group result values drifted")
        groups.append(
            (
                applied_group.group_id,
                applied_group.layer_ids,
                threshold_m,
                cell_count,
                pd.DataFrame(
                    {
                        "hex_id": cell_ids,
                        "acceptance": acceptance_values,
                    }
                ),
            )
        )
    return tuple(groups)


def _workspace_wind_runtime_result_from_group_frames(
    region: dict[str, Any],
    request: WorkspaceAnalysisRequest,
    group_frames: tuple[
        tuple[str, tuple[str, ...], float, int, pd.DataFrame], ...
    ],
) -> dict[str, Any]:
    """Feed engine or signed-presentation rows through one renderer path."""

    region_id = str(region.get("region_id", "")).strip().lower()
    if request.region_id != region_id or request.analysis_id != "wind":
        raise ValueError("Wind workspace request identity drifted")
    contract = load_delivery_analysis(region_id, "wind")
    if tuple(value[0] for value in group_frames) != tuple(
        group.group_id for group in request.groups
    ):
        raise ValueError("Wind workspace result identity drifted")

    domain = contract.analysis_domain
    if domain is None:
        raise ValueError(f"{region_id}/wind has no analysis domain")
    domain_artifact = (
        domain
        if int(request.target_resolution) == int(domain.resolution)
        else domain.rollups.get(int(request.target_resolution))
    )
    if domain_artifact is None:
        raise ValueError(
            f"{region_id}/wind has no R{request.target_resolution} domain"
        )
    display_geometry_path = read_analysis_domain_input(
        contract, "standard_analysis", int(request.target_resolution)
    )
    display_geometries = load_h3_display_geometries(display_geometry_path)
    frame = pd.DataFrame({"hex_id": sorted(display_geometries)})
    if frame.empty:
        raise ValueError("Wind workspace request resolved an empty domain")

    acceptance_columns: list[str] = []
    group_meta: dict[str, dict[str, Any]] = {}
    request_by_group = {group.group_id: group for group in request.groups}
    for (
        group_id,
        layer_ids,
        threshold_m,
        cell_count,
        group_frame,
    ) in group_frames:
        applied_group = request_by_group[group_id]
        if (
            tuple(layer_ids) != tuple(applied_group.layer_ids)
            or int(cell_count) != len(frame)
            or len(group_frame) != len(frame)
        ):
            raise ValueError(
                f"Wind workspace result drifted for {group_id}"
            )
        acceptance_col = f"acceptance__{group_id}"
        group_frame = group_frame.rename(
            columns={"acceptance": acceptance_col}
        )[["hex_id", acceptance_col]].copy()
        if group_frame["hex_id"].duplicated().any():
            raise ValueError(
                f"Wind workspace result duplicates {group_id} cells"
            )
        frame = frame.merge(
            group_frame,
            on="hex_id",
            how="left",
            validate="one_to_one",
        )
        if frame[acceptance_col].isna().any():
            raise ValueError(
                f"Wind workspace result is incomplete for {group_id}"
            )
        acceptance_columns.append(acceptance_col)
        group_contract = _wind_control_group(region_id, group_id)
        if group_contract is None:
            raise ValueError(
                f"Wind workspace has no control for {group_id}"
            )
        operations = {
            contract.layers[layer_id].operation
            for layer_id in applied_group.layer_ids
        }
        if len(operations) != 1:
            raise ValueError(
                f"Wind workspace group {group_id} has mixed operations"
            )
        operation = next(iter(operations))
        role = "feasible" if operation == "proximity_feasibility" else "conflict"
        acceptance = frame[acceptance_col].astype(float)
        share_series = acceptance.mul(100.0) if role == "feasible" else (1.0 - acceptance).mul(100.0)
        group_meta[group_id] = {
            "label": str(group_contract.label),
            "analysis_kind": str(group_contract.analysis_kind),
            "role": role,
            "active_layer_ids": list(applied_group.layer_ids),
            "selected_sources": [
                str(contract.layers[layer_id].label)
                for layer_id in applied_group.layer_ids
            ],
            "analysis_value_m": float(threshold_m),
            "land_share_pct": float(share_series.mean()),
        }

    if acceptance_columns:
        frame["potential_area_share_pct"] = (
            frame[acceptance_columns].min(axis=1).mul(100.0)
        )
        frame = frame.drop(columns=acceptance_columns)
    else:
        frame["potential_area_share_pct"] = 100.0
    frame = _finalize_fast_wind_share_frame(
        frame,
        display_geometry_path,
        region_id,
        int(request.target_resolution),
        compute_core=False,
    )
    total_model_area_km2 = float(frame["display_area_km2"].sum())
    potential_model_area_km2 = float(frame["potential_area_km2"].sum())
    request_digest = hashlib.sha256(
        json.dumps(
            request.as_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return {
        "cache_key": f"workspace_request_{request_digest}",
        "groups": group_meta,
        "combined": {
            "land_share_pct": float(frame["potential_area_share_pct"].mean()),
            "area_weighted_land_share_pct": (
                potential_model_area_km2
                / max(total_model_area_km2, 1e-9)
                * 100.0
            ),
            "model_area_km2": total_model_area_km2,
            "potential_model_area_km2": potential_model_area_km2,
            "area_basis": "display_area_m2",
            "h3_resolution": int(request.target_resolution),
        },
        "fast_distance_frame": frame,
        "fast_distance": True,
        "unfiltered_land": not bool(request.groups),
        "canonical_layer_ids": list(request.selected_layer_ids),
        "display_geometry_path": display_geometry_path,
        "workspace_request": request.as_dict(),
    }


def _workspace_wind_runtime_result(
    region: dict[str, Any],
    request: WorkspaceAnalysisRequest,
) -> dict[str, Any]:
    """Run the generic engine fallback and adapt it to the product renderer."""

    result = run_workspace_analysis_request(request)
    if (
        result.region_id != request.region_id
        or result.analysis_id != request.analysis_id
        or tuple(value.group_id for value in result.groups)
        != tuple(value.group_id for value in request.groups)
    ):
        raise ValueError("Wind workspace result identity drifted")
    group_frames = tuple(
        (
            group.group_id,
            group.layer_ids,
            float(group.threshold_m),
            int(group.cell_count),
            pd.DataFrame(
                {
                    "hex_id": [str(cell.cell_id) for cell in group.cells],
                    "acceptance": [
                        float(cell.acceptance) for cell in group.cells
                    ],
                }
            ),
        )
        for group in result.groups
    )
    return _workspace_wind_runtime_result_from_group_frames(
        region,
        request,
        group_frames,
    )


@st.cache_data(show_spinner=False, max_entries=16)
def _cached_workspace_wind_runtime_result(
    bundle_execution_signature_sha256: str,
    presentation_signature_sha256: str,
    *,
    _binding: WorkspaceExecutionBinding,
) -> dict[str, Any]:
    """Cache one direct signed-presentation adaptation by compact SHA keys."""

    if (
        not isinstance(bundle_execution_signature_sha256, str)
        or len(bundle_execution_signature_sha256) != 64
        or any(
            value not in "0123456789abcdef"
            for value in bundle_execution_signature_sha256
        )
        or not isinstance(presentation_signature_sha256, str)
        or len(presentation_signature_sha256) != 64
        or any(
            value not in "0123456789abcdef"
            for value in presentation_signature_sha256
        )
        or _binding.presentation.presentation_signature_sha256
        != presentation_signature_sha256
    ):
        raise ValueError("Cached wind workspace signatures drifted")
    request = _binding.request
    group_frames = _workspace_wind_group_frames_from_binding(
        _binding,
        request,
        presentation_signature_sha256,
    )
    return _workspace_wind_runtime_result_from_group_frames(
        {"region_id": request.region_id},
        request,
        group_frames,
    )


def _workspace_wind_runtime_result_from_bundle(
    region: dict[str, Any],
    request: WorkspaceAnalysisRequest,
    bundle: WorkspaceExecutionBundle,
) -> dict[str, Any]:
    """Resolve and verify a binding before every compact adapter-cache hit."""

    bundle_signature = bundle.execution_signature_sha256
    if (
        not isinstance(bundle_signature, str)
        or len(bundle_signature) != 64
        or any(value not in "0123456789abcdef" for value in bundle_signature)
    ):
        raise ValueError("Wind workspace bundle signature is invalid")
    region_id = str(region.get("region_id", "")).strip().lower()
    if region_id != request.region_id:
        raise ValueError("Wind workspace region escaped its request")
    presentation_signature = _workspace_bundle_presentation_signature(
        bundle,
        request,
    )
    binding = bundle.binding(request.analysis_id)
    runtime_result = _cached_workspace_wind_runtime_result(
        bundle_signature,
        presentation_signature,
        _binding=binding,
    )
    combined = runtime_result.get("combined")
    if (
        runtime_result.get("workspace_request") != request.as_dict()
        or runtime_result.get("canonical_layer_ids")
        != list(request.selected_layer_ids)
        or not isinstance(combined, dict)
        or combined.get("h3_resolution") != request.target_resolution
        or runtime_result.get("fast_distance") is not True
    ):
        raise ValueError("Cached wind workspace result escaped its bundle")
    return runtime_result


def _wind_fast_distance_runtime_result(
    region: dict[str, Any],
    ui_params: dict[str, float],
    layer_selection: dict[str, list[str]],
    target_resolution: int,
    *,
    workspace_request: WorkspaceAnalysisRequest | None = None,
    workspace_bundle: WorkspaceExecutionBundle | None = None,
) -> dict[str, Any] | None:
    if workspace_request is not None:
        execution_request = _wind_workspace_request_at_resolution(
            workspace_request,
            int(target_resolution),
        )
        request_selection, request_ui_params = _wind_workspace_request_values(
            execution_request
        )
        if normalize_group_layer_map(
            layer_selection,
            execution_request.region_id,
        ) != request_selection:
            raise ValueError("Wind selection drifted from the applied request")
        for group in execution_request.groups:
            param_key = _wind_group_param_key(group.group_id)
            if (
                not param_key
                or not math.isclose(
                    float(ui_params.get(param_key, math.nan)),
                    float(request_ui_params[param_key]),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            ):
                raise ValueError("Wind parameters drifted from the applied request")
        return (
            _workspace_wind_runtime_result(region, execution_request)
            if workspace_bundle is None
            else _workspace_wind_runtime_result_from_bundle(
                region,
                execution_request,
                workspace_bundle,
            )
        )

    if workspace_bundle is not None:
        raise ValueError(
            "A workspace bundle requires an explicit workspace request"
        )

    region_id = str(region.get("region_id", "")).strip().lower()
    if not region_id:
        return None
    selected = normalize_group_layer_map(layer_selection, region_id)
    if not any(selected.values()):
        return None
    groups, layers, registry_meta = load_acceptance_registry(region_id)
    manifest_groups = {
        str(group.id): group
        for group in _wind_control_groups(region_id)
        if isinstance(group, WindGroupControlContract)
    }
    manifest_layers_by_group = {
        group_id: {str(layer.id): layer for layer in group.layers}
        for group_id, group in manifest_groups.items()
    }
    manifest_layers = {
        layer_id: layer
        for group_layers in manifest_layers_by_group.values()
        for layer_id, layer in group_layers.items()
    }
    if str(registry_meta.get("_runtime_strategy") or "") != "fast_distance":
        return None
    distance_conflict_semantics = str(
        registry_meta["_distance_conflict_semantics"]
    )
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return None
    display_geometries = load_h3_display_geometries(display_geometry_path)
    frame = pd.DataFrame({"hex_id": list(display_geometries.keys())})
    if frame.empty:
        return None
    frame["potential_area_share_pct"] = 100.0
    active_groups: list[str] = []
    group_meta: dict[str, dict[str, Any]] = {}
    canonical_layer_ids: list[str] = []
    for group_id, layer_ids in selected.items():
        group = manifest_groups.get(group_id) or groups.get(group_id)
        if group is None or not layer_ids:
            continue
        distance_parts: list[pd.DataFrame] = []
        canonical_acceptance_parts: list[pd.Series] = []
        threshold_key = _wind_group_param_key(group_id)
        threshold_m = (
            float(ui_params.get(threshold_key, group.analysis_default_m))
            if threshold_key
            else float(group.analysis_default_m)
        )
        canonical_ids: list[str] = []
        group_manifest_layers = manifest_layers_by_group.get(group_id, {})
        canonical_ids = [
            layer_id for layer_id in layer_ids if layer_id in group_manifest_layers
        ]
        canonical_frame = (
            wind_group_acceptance_frame(
                region_id,
                group_id,
                canonical_ids,
                threshold_m,
                frame["hex_id"].astype(str),
                int(target_resolution),
            )
            if canonical_ids
            else None
        )
        if canonical_frame is not None:
            canonical_merged = frame[["hex_id"]].merge(
                canonical_frame[
                    ["hex_id", "acceptance", "coverage_missing"]
                ],
                on="hex_id",
                how="left",
                validate="one_to_one",
            )
            if canonical_merged["acceptance"].isna().any():
                raise ValueError(
                    f"Canonical {group_id} result is incomplete for the "
                    f"R{int(target_resolution)} display domain"
                )
            canonical_acceptance_parts.append(
                canonical_merged["acceptance"].astype(float).mask(
                    canonical_merged["coverage_missing"].astype(bool)
                )
            )
            canonical_layer_ids.extend(canonical_ids)
        for layer_id in layer_ids:
            if layer_id not in canonical_ids:
                layer_df = _target_resolution_distance_frame(
                    distance_table_for_layer(registry_meta, layer_id),
                    int(target_resolution),
                    display_geometry_path,
                )
                if not layer_df.empty:
                    distance_parts.append(layer_df)
        if not distance_parts and not canonical_acceptance_parts:
            continue
        acceptance_parts = list(canonical_acceptance_parts)
        if distance_parts:
            merged = frame[["hex_id"]].copy()
            distance_cols: list[str] = []
            intersect_cols: list[str] = []
            for idx, part in enumerate(distance_parts):
                distance_col = f"distance_{idx}"
                intersect_col = f"intersects_{idx}"
                renamed = part.rename(
                    columns={
                        "distance_m": distance_col,
                        "intersects": intersect_col,
                    }
                )
                merged = merged.merge(renamed, on="hex_id", how="left")
                distance_cols.append(distance_col)
                intersect_cols.append(intersect_col)
            min_distance = merged[distance_cols].min(axis=1, skipna=True)
            any_intersection = (
                merged[intersect_cols]
                .fillna(False)
                .astype(bool)
                .any(axis=1)
            )
            observed = min_distance.notna() | any_intersection
            acceptance_parts.append(
                _acceptance_series_for_group(
                    group.analysis_kind,
                    min_distance,
                    any_intersection,
                    threshold_m,
                    distance_conflict_semantics,
                ).where(observed)
            )
        group_acceptance = pd.concat(acceptance_parts, axis=1).min(
            axis=1,
            skipna=True,
        ).fillna(0.0)
        frame["potential_area_share_pct"] = frame["potential_area_share_pct"].combine(
            group_acceptance.mul(100.0),
            min,
        )
        active_groups.append(group_id)
        role = "feasible" if group.analysis_kind == "proximity_feasibility" else "conflict"
        share_series = group_acceptance.mul(100.0) if role == "feasible" else (1.0 - group_acceptance).mul(100.0)
        selected_labels = [
            manifest_layers[layer_id].label
            if layer_id in manifest_layers
            else layer_label(
                layers[layer_id],
                WIND_CONTROL_LANGUAGE,
                layers[layer_id].label,
            )
            for layer_id in layer_ids
            if layer_id in manifest_layers or layer_id in layers
        ]
        group_meta[group_id] = {
            "label": group.label,
            "analysis_kind": group.analysis_kind,
            "role": role,
            "active_layer_ids": list(layer_ids),
            "selected_sources": selected_labels,
            "analysis_value_m": float(threshold_m),
            "land_share_pct": float(share_series.fillna(0.0).mean()),
        }
    if not active_groups:
        return None
    frame = _finalize_fast_wind_share_frame(
        frame,
        display_geometry_path,
        region_id,
        int(target_resolution),
        compute_core=False,
    )
    total_model_area_km2 = float(frame["display_area_km2"].sum())
    potential_model_area_km2 = float(frame["potential_area_km2"].sum())
    return {
        "cache_key": (
            f"{region_id}_{distance_conflict_semantics}_"
            f"fast_distance_r{int(target_resolution)}"
        ),
        "groups": group_meta,
        "combined": {
            "land_share_pct": float(frame["potential_area_share_pct"].mean()),
            "area_weighted_land_share_pct": (
                potential_model_area_km2
                / max(total_model_area_km2, 1e-9)
                * 100.0
            ),
            "model_area_km2": total_model_area_km2,
            "potential_model_area_km2": potential_model_area_km2,
            "area_basis": "display_area_m2",
            "h3_resolution": int(target_resolution),
        },
        "fast_distance_frame": frame,
        "fast_distance": True,
        "canonical_layer_ids": sorted(set(canonical_layer_ids)),
    }


def _wind_runtime_hex_layer_frame(
    region: dict[str, Any],
    runtime_result: dict[str, Any],
    target_resolution: int,
) -> pd.DataFrame:
    fast_frame = runtime_result.get("fast_distance_frame")
    if isinstance(fast_frame, pd.DataFrame):
        return fast_frame.copy()
    combined = runtime_result.get("combined")
    if not isinstance(combined, dict) or combined.get("geojson") is None:
        return pd.DataFrame()
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame()
    return _build_wind_runtime_hex_layer_data(
        json.dumps(combined["geojson"], sort_keys=True, ensure_ascii=False),
        display_geometry_path,
        int(target_resolution),
    )


def _wind_runtime_hex_feature_collection(
    frame: pd.DataFrame,
    display_geometry_path: str,
    target_resolution: int,
) -> dict[str, Any]:
    display_geometries = load_h3_display_geometries(display_geometry_path)
    features: list[dict[str, Any]] = []
    for row in frame.itertuples(index=False):
        geometry = display_geometries.get(str(row.hex_id))
        if geometry is None:
            continue
        popup = (
            f"<strong>{WIND_LANDSCAPE_POTENTIAL_LABEL}</strong><br>"
            f"Hex: {row.hex_id}<br>"
            f"LP-andel: {float(row.potential_area_share_pct):.1f}%<br>"
            f"Klass: {row.share_class_label}<br>"
            f"Kärnläge: {row.core_label}<br>"
            f"Kärnscore: {float(row.core_score):.2f}<br>"
            f"Sammanhängande zon: {int(row.zone_size)} hex<br>"
            f"Kärnrank i zon: {int(row.center_mass_rank)} av {int(row.zone_size)}<br>"
            f"<em>Mörkare nyans betyder längre in i en sammanhängande zon av samma potentialklass.</em>"
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": str(row.hex_id),
                    "fill": str(row.fill),
                    "stroke": str(row.stroke),
                    "core_score": float(row.core_score),
                    "core_label": str(row.core_label),
                    "zone_size": int(row.zone_size),
                    "tooltip_title": f"{WIND_LANDSCAPE_POTENTIAL_LABEL} {float(row.potential_area_share_pct):.1f}%",
                    "tooltip_body": f"{row.share_class_label} · {row.core_label}",
                    "popup": popup,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _wind_runtime_hex_layer(
    region: dict[str, Any],
    runtime_result: dict[str, Any],
    target_resolution: int,
    control_name: str | None = None,
) -> dict[str, Any] | None:
    request_bound_path = runtime_result.get("display_geometry_path")
    if runtime_result.get("workspace_request") is not None:
        if not isinstance(request_bound_path, DomainDisplayPayload) and (
            not isinstance(request_bound_path, str) or not request_bound_path.strip()
        ):
            raise ValueError("Workspace wind result has no request-bound geometry")
        display_geometry_path = request_bound_path
    else:
        display_geometry_path = _h3_display_geometry_path(
            region,
            int(target_resolution),
        )
    if not display_geometry_path:
        return None
    frame = _wind_runtime_hex_layer_frame(region, runtime_result, int(target_resolution))
    if frame.empty:
        return None
    return {
        "name": str(control_name or WIND_LANDSCAPE_POTENTIAL_LABEL),
        "feature_collection": _wind_runtime_hex_feature_collection(frame, display_geometry_path, int(target_resolution)),
        "fill_property": "fill",
        "stroke_property": "stroke",
        "legend_items": _wind_share_legend_items(),
        "legend_id": "wind_polygon_hex_share",
        "legend_title": WIND_POTENTIAL_HEX_LABEL,
        "default_visible": True,
        "stroke": False,
        "weight": 0.0,
        "point_radius": 4,
        "z_index": 410,
        "layer_kind": "hex",
        "opacity_family": str(control_name or WIND_LANDSCAPE_POTENTIAL_LABEL),
        "opacity_label": str(control_name or WIND_LANDSCAPE_POTENTIAL_LABEL),
    }


def _rollup_energy_area_proposal_frame(
    selected: pd.DataFrame,
    target_resolution: int,
    source_resolution: int,
    target_cell_areas_km2: Mapping[str, float] | None = None,
    source_cell_areas_km2: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    if selected.empty or int(target_resolution) >= int(source_resolution):
        return selected.copy()

    work = selected.copy()
    allocation_rollup = _generic_allocation_rollup_frame(
        work,
        "wind",
        int(target_resolution),
        int(source_resolution),
        source_cell_areas_km2,
    )

    def _numeric_column(column: str, default: float = 0.0) -> pd.Series:
        if column in work.columns:
            return pd.to_numeric(work[column], errors="coerce").fillna(default)
        return pd.Series(default, index=work.index, dtype="float64")

    work["allocated_area_km2"] = _numeric_column("allocated_area_km2", 0.0)
    work["potential_area_km2"] = _numeric_column("potential_area_km2", 0.0)
    work["allocated_twh"] = _numeric_column("allocated_twh", 0.0)
    work["selected_rank"] = _numeric_column("selected_rank", 0.0).astype(int)
    work["core_score"] = _numeric_column("core_score", 0.0)
    work["landscape_priority_score"] = _numeric_column("landscape_priority_score", 0.0)
    work["allocation_priority_score"] = _numeric_column("allocation_priority_score", 0.0)
    work["social_acceptance_priority_score"] = _numeric_column("social_acceptance_priority_score", 0.0)
    work["social_acceptance_value"] = _numeric_column(
        "social_acceptance_value",
        math.nan,
    )
    work["social_acceptance_allocation_priority_pct"] = _numeric_column("social_acceptance_allocation_priority_pct", 0.0)
    work["zone_size"] = _numeric_column("zone_size", 0.0).astype(int)
    work["expansion_ring"] = _numeric_column("expansion_ring", 0.0).astype(int)
    if "allocation_priority_reason" not in work.columns:
        work["allocation_priority_reason"] = ""
    if "social_acceptance_data_status" not in work.columns:
        work["social_acceptance_data_status"] = "not_assessed"
    if "outside_et" not in work.columns:
        work["outside_et"] = False
    if "reserved_by_other_technology" not in work.columns:
        work["reserved_by_other_technology"] = False
    work["outside_et"] = work["outside_et"].fillna(False).astype(bool)
    work["reserved_by_other_technology"] = work["reserved_by_other_technology"].fillna(False).astype(bool)
    work["hex_id"] = work["hex_id"].astype(str)
    work = work.sort_values(["selected_rank", "hex_id"]).reset_index(drop=True)
    work["hex_id"] = work["hex_id"].map(
        lambda value: h3.cell_to_parent(value, int(target_resolution))
    )

    def _first_text(values: pd.Series) -> str:
        labels = [str(value) for value in values.dropna().tolist() if str(value)]
        unique = list(dict.fromkeys(labels))
        return ", ".join(unique[:3])

    rolled = (
        work.groupby("hex_id", as_index=False)
        .agg(
            selected_rank=("selected_rank", "min"),
            potential_area_km2=(
                "potential_area_km2",
                lambda values: math.fsum(float(value) for value in values),
            ),
            core_score=("core_score", "max"),
            landscape_priority_score=("landscape_priority_score", "max"),
            allocation_priority_score=("allocation_priority_score", "max"),
            allocation_priority_reason=("allocation_priority_reason", _first_text),
            social_acceptance_priority_score=("social_acceptance_priority_score", "max"),
            social_acceptance_value=("social_acceptance_value", "mean"),
            social_acceptance_data_status=(
                "social_acceptance_data_status",
                _first_text,
            ),
            social_acceptance_allocation_priority_pct=("social_acceptance_allocation_priority_pct", "max"),
            zone_size=("zone_size", "sum"),
            expansion_ring=("expansion_ring", "max"),
            reserved_by_other_technology=("reserved_by_other_technology", "max"),
        )
        .reset_index(drop=True)
    )
    rolled = rolled.merge(
        allocation_rollup,
        on="hex_id",
        how="inner",
        validate="one_to_one",
    )
    rolled = rolled.sort_values(["selected_rank", "hex_id"]).reset_index(
        drop=True
    )
    if target_cell_areas_km2 is None:
        raise ValueError(
            "Wind allocation rollup requires manifest-declared target "
            "cell areas"
        )
    hex_area = h3_hex_area_km2(int(target_resolution))
    target_area_capacity = _establishment_cell_area_km2_series(
        rolled,
        target_cell_areas_km2,
        hex_area,
        f"wind allocation R{target_resolution}",
    )
    rolled["display_area_km2"] = target_area_capacity.astype(float)
    rolled["potential_area_km2"] = pd.concat(
        [rolled["potential_area_km2"].clip(lower=0.0), target_area_capacity],
        axis=1,
    ).min(axis=1)
    excess_area = rolled["allocated_area_km2"] - target_area_capacity
    if bool(excess_area.gt(1e-9).any()):
        invalid = rolled.loc[excess_area.gt(1e-9), "hex_id"].astype(str).tolist()
        raise ValueError(
            "Wind allocation rollup exceeds manifest-declared target "
            "capacity for: "
            + ", ".join(invalid[:5])
        )
    rolled["allocated_area_km2"] = rolled["allocated_area_km2"].clip(
        lower=0.0
    )
    rolled["outside_et"] = rolled["outside_area_km2"].gt(0.0)
    rolled["allocation_phase"] = rolled["outside_et"].map(lambda value: "Utanför LP" if value else "Inom LP")
    rolled["potential_area_share_pct"] = (
        rolled["potential_area_km2"] / target_area_capacity * 100.0
    ).clip(lower=0.0, upper=100.0)
    rolled["allocated_hex_share_pct"] = (
        rolled["allocated_area_km2"] / target_area_capacity * 100.0
    ).clip(lower=0.0, upper=100.0)
    rolled["remaining_area_after_km2"] = 0.0
    rolled["allocated_gwh"] = rolled["allocated_twh"] * 1000.0
    return rolled


def _combined_establishment_legend_items() -> list[dict[str, str]]:
    order = ["wind_and_solar", "wind_only", "solar_only", "not_suitable"]
    return [
        {"label": ESTABLISHMENT_CLASS_SPECS[class_id]["label"], "color": ESTABLISHMENT_CLASS_SPECS[class_id]["color"]}
        for class_id in order
    ]


def _establishment_source_frame(
    selected: pd.DataFrame,
    technology: str,
    target_resolution: int,
    source_resolution: int,
    target_cell_areas_km2: Mapping[str, float] | None = None,
    source_cell_areas_km2: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    columns = [
        "hex_id",
        f"{technology}_suitable",
        f"{technology}_rank",
        f"{technology}_potential_score",
        f"{technology}_potential_area_km2",
        f"{technology}_allocated_area_km2",
        f"{technology}_allocated_gwh",
        f"{technology}_allocated_hex_share_pct",
        f"{technology}_landscape_priority_score",
        f"{technology}_allocation_priority_score",
        f"{technology}_allocation_priority_reason",
        f"{technology}_social_acceptance_priority_score",
        f"{technology}_social_acceptance_value",
        f"{technology}_social_acceptance_data_status",
        f"{technology}_social_acceptance_allocation_priority_pct",
        f"{technology}_last_resort_overlap",
        f"{technology}_outside_lp",
        f"{technology}_conflict_area_km2",
        f"{technology}_conflict",
        f"{technology}_expansion_ring",
        f"{technology}_phase",
    ]
    if selected.empty:
        return pd.DataFrame(columns=columns)

    if technology == "wind":
        rolled = _rollup_energy_area_proposal_frame(
            selected,
            int(target_resolution),
            int(source_resolution),
            target_cell_areas_km2=target_cell_areas_km2,
            source_cell_areas_km2=source_cell_areas_km2,
        )
        score_column = "potential_area_share_pct"
    else:
        rolled = _rollup_solar_establishment_frame(
            selected,
            int(target_resolution),
            int(source_resolution),
            target_cell_areas_km2=target_cell_areas_km2,
            source_cell_areas_km2=source_cell_areas_km2,
        )
        score_column = "potential_score"
    if rolled.empty or "hex_id" not in rolled.columns:
        return pd.DataFrame(columns=columns)

    work = rolled.copy()
    work["hex_id"] = work["hex_id"].astype(str)

    def _numeric_source(column: str, default: float = 0.0) -> pd.Series:
        if column in work.columns:
            return pd.to_numeric(work[column], errors="coerce").fillna(default)
        return pd.Series(default, index=work.index, dtype="float64")

    work[f"{technology}_rank"] = _numeric_source("selected_rank", 0.0).astype(int)
    work[f"{technology}_potential_score"] = _numeric_source(score_column, 0.0).clip(lower=0.0, upper=100.0)
    work[f"{technology}_potential_area_km2"] = _numeric_source("potential_area_km2", 0.0).clip(lower=0.0)
    work[f"{technology}_allocated_area_km2"] = _numeric_source("allocated_area_km2", 0.0).clip(lower=0.0)
    if "allocated_gwh" in work.columns:
        allocated_gwh = _numeric_source("allocated_gwh", 0.0)
    else:
        allocated_gwh = _numeric_source("allocated_twh", 0.0) * 1000.0
    work[f"{technology}_allocated_gwh"] = allocated_gwh.clip(lower=0.0)
    work[f"{technology}_allocated_hex_share_pct"] = _numeric_source("allocated_hex_share_pct", 0.0).clip(lower=0.0, upper=100.0)
    work[f"{technology}_landscape_priority_score"] = _numeric_source("landscape_priority_score", 0.0).clip(lower=0.0, upper=1.0)
    work[f"{technology}_allocation_priority_score"] = _numeric_source("allocation_priority_score", 0.0).clip(lower=0.0, upper=1.0)
    work[f"{technology}_social_acceptance_priority_score"] = _numeric_source("social_acceptance_priority_score", 0.0).clip(
        lower=0.0,
        upper=1.0,
    )
    work[f"{technology}_social_acceptance_value"] = _numeric_source(
        "social_acceptance_value",
        math.nan,
    ).clip(lower=0.0, upper=1.0)
    if "social_acceptance_data_status" in work.columns:
        work[f"{technology}_social_acceptance_data_status"] = (
            work["social_acceptance_data_status"]
            .fillna("not_assessed")
            .astype(str)
        )
    else:
        work[f"{technology}_social_acceptance_data_status"] = "not_assessed"
    work[f"{technology}_social_acceptance_allocation_priority_pct"] = _numeric_source(
        "social_acceptance_allocation_priority_pct",
        0.0,
    ).clip(lower=0.0, upper=100.0)
    if "reserved_by_other_technology" in work.columns:
        work[f"{technology}_last_resort_overlap"] = work["reserved_by_other_technology"].fillna(False).astype(bool)
    else:
        work[f"{technology}_last_resort_overlap"] = False
    if "allocation_priority_reason" in work.columns:
        work[f"{technology}_allocation_priority_reason"] = work["allocation_priority_reason"].fillna("").astype(str)
    else:
        work[f"{technology}_allocation_priority_reason"] = ""
    if "outside_et" in work.columns:
        work[f"{technology}_outside_lp"] = work["outside_et"].fillna(False).astype(bool)
    else:
        work[f"{technology}_outside_lp"] = False
    if "inside_area_km2" in work.columns:
        inside_area = _numeric_source("inside_area_km2", 0.0).clip(lower=0.0)
    else:
        inside_area = work[f"{technology}_allocated_area_km2"].where(
            ~work[f"{technology}_outside_lp"],
            0.0,
        )
    work[f"{technology}_suitable"] = inside_area.gt(FLOAT_TOLERANCE)
    if "outside_area_km2" in work.columns:
        conflict_area = _numeric_source("outside_area_km2", 0.0).clip(
            lower=0.0
        )
    else:
        conflict_area = work[f"{technology}_allocated_area_km2"].where(
            work[f"{technology}_outside_lp"],
            0.0,
        )
    work[f"{technology}_conflict_area_km2"] = conflict_area
    work[f"{technology}_conflict"] = work[f"{technology}_conflict_area_km2"].gt(0.0)
    work[f"{technology}_expansion_ring"] = _numeric_source("expansion_ring", 0.0).astype(int)
    if "allocation_phase" in work.columns:
        work[f"{technology}_phase"] = work["allocation_phase"].fillna("").astype(str)
    else:
        work[f"{technology}_phase"] = work[f"{technology}_outside_lp"].map(lambda value: "Utanför LP" if value else "Inom LP")
    return work.reindex(columns=columns)


def _establishment_cell_area_km2_series(
    frame: pd.DataFrame,
    cell_areas_km2: Mapping[str, float] | None,
    fallback_area_km2: float,
    contract_label: str,
) -> pd.Series:
    if cell_areas_km2 is None:
        fallback = float(fallback_area_km2)
        if not math.isfinite(fallback) or fallback <= 0.0:
            raise ValueError(f"{contract_label} fallback cell area must be positive")
        return pd.Series(fallback, index=frame.index, dtype="float64")
    if "hex_id" not in frame.columns:
        raise ValueError(f"{contract_label} cell-area lookup requires hex_id")
    values = pd.to_numeric(
        frame["hex_id"].astype(str).map(cell_areas_km2),
        errors="coerce",
    )
    valid = values.notna() & values.map(
        lambda value: math.isfinite(float(value)) and float(value) > 0.0
    )
    if not bool(valid.all()):
        missing = (
            frame.loc[~valid, "hex_id"]
            .astype(str)
            .head(5)
            .tolist()
        )
        raise ValueError(
            f"{contract_label} has no positive finite cell area for: "
            + ", ".join(missing)
        )
    return values.astype(float)


def _potential_establishment_source_frame(
    source: pd.DataFrame,
    technology: str,
    target_resolution: int,
    source_resolution: int,
    source_cell_areas_km2: Mapping[str, float] | None = None,
    target_cell_areas_km2: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    columns = [
        "hex_id",
        f"{technology}_suitable",
        f"{technology}_potential_score",
        f"{technology}_potential_area_km2",
        f"{technology}_context_status",
    ]
    if technology == "wind":
        columns.append("wind_model_area_km2")
    if source.empty or "hex_id" not in source.columns:
        return pd.DataFrame(columns=columns)

    work = source.copy()
    work["hex_id"] = work["hex_id"].astype(str)
    source_hex_area = float(h3_hex_area_km2(int(source_resolution)))
    target_hex_area = float(h3_hex_area_km2(int(target_resolution)))
    source_area_capacity = _establishment_cell_area_km2_series(
        work,
        source_cell_areas_km2,
        source_hex_area,
        f"{technology} R{source_resolution}",
    )

    if technology == "wind":
        score_col = "potential_area_share_pct" if "potential_area_share_pct" in work.columns else "wind_score"
        if "potential_area_km2" in work.columns:
            potential_area = pd.to_numeric(
                work["potential_area_km2"],
                errors="coerce",
            ).fillna(0.0).clip(lower=0.0)
            work["potential_area_km2"] = pd.concat(
                [potential_area, source_area_capacity],
                axis=1,
            ).min(axis=1)
            if score_col in work.columns:
                work["potential_score"] = pd.to_numeric(work[score_col], errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
            else:
                work["potential_score"] = (
                    work["potential_area_km2"]
                    / source_area_capacity
                    * 100.0
                ).clip(lower=0.0, upper=100.0)
        else:
            work["potential_score"] = pd.to_numeric(work.get(score_col), errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
            work["potential_area_km2"] = (
                work["potential_score"]
                / 100.0
                * source_area_capacity
            )
    else:
        if "potential_area_km2" in work.columns:
            area = pd.to_numeric(work["potential_area_km2"], errors="coerce").fillna(0.0)
        elif "potential_area_m2" in work.columns:
            area = pd.to_numeric(work["potential_area_m2"], errors="coerce").fillna(0.0) / 1_000_000.0
        else:
            area = pd.Series(0.0, index=work.index, dtype="float64")
        work["potential_area_km2"] = area.clip(lower=0.0, upper=source_hex_area)
        score_col = "potential_area_share_pct" if "potential_area_share_pct" in work.columns else "solar_score"
        if score_col in work.columns:
            work["potential_score"] = pd.to_numeric(work[score_col], errors="coerce").fillna(0.0).clip(lower=0.0, upper=100.0)
        else:
            work["potential_score"] = (work["potential_area_km2"] / max(source_hex_area, 1e-9) * 100.0).clip(lower=0.0, upper=100.0)
    if int(target_resolution) < int(source_resolution):
        work["hex_id"] = work["hex_id"].map(lambda value: str(h3.cell_to_parent(str(value), int(target_resolution))))
        agg_spec: dict[str, Any] = {"potential_area_km2": ("potential_area_km2", "sum")}
        work = (
            work.groupby("hex_id", as_index=False)
            .agg(**agg_spec)
            .sort_values("hex_id")
            .reset_index(drop=True)
        )
        target_area_capacity = _establishment_cell_area_km2_series(
            work,
            target_cell_areas_km2,
            target_hex_area,
            f"{technology} R{target_resolution}",
        )
        work["potential_area_km2"] = pd.concat(
            [work["potential_area_km2"].clip(lower=0.0), target_area_capacity],
            axis=1,
        ).min(axis=1)
        work["potential_score"] = (
            work["potential_area_km2"]
            / target_area_capacity
            * 100.0
        ).clip(lower=0.0, upper=100.0)
    else:
        target_area_capacity = _establishment_cell_area_km2_series(
            work,
            target_cell_areas_km2,
            target_hex_area,
            f"{technology} R{target_resolution}",
        )
        work["potential_area_km2"] = pd.concat(
            [work["potential_area_km2"].clip(lower=0.0), target_area_capacity],
            axis=1,
        ).min(axis=1)
        work["potential_score"] = (
            work["potential_area_km2"]
            / target_area_capacity
            * 100.0
        ).clip(lower=0.0, upper=100.0)

    out = work[["hex_id", "potential_score", "potential_area_km2"]].copy()
    suitable = out["potential_area_km2"].gt(FLOAT_TOLERANCE)
    out[f"{technology}_suitable"] = suitable
    out[f"{technology}_potential_score"] = out["potential_score"].round(1)
    out[f"{technology}_potential_area_km2"] = out["potential_area_km2"].clip(lower=0.0)
    if "technology_context_status" in work.columns:
        context_status = work["technology_context_status"].fillna(
            "not_assessed"
        ).astype(str)
        out[f"{technology}_context_status"] = context_status.values
    else:
        out[f"{technology}_context_status"] = "not_assessed"
    if technology == "wind":
        out["wind_model_area_km2"] = target_area_capacity.astype(float)
    return out.reindex(columns=columns)


def _combined_establishment_class(wind_suitable: bool, solar_suitable: bool) -> str:
    if wind_suitable and solar_suitable:
        return "wind_and_solar"
    if wind_suitable:
        return "wind_only"
    if solar_suitable:
        return "solar_only"
    return "not_suitable"


def _apply_establishment_style_columns(frame: pd.DataFrame) -> pd.DataFrame:
    frame["establishment_label"] = frame["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["label"]
    )
    frame["fill"] = frame["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["color"]
    )
    frame["stroke"] = frame["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["stroke"]
    )
    frame["stroke_weight"] = 0.12
    frame["fill_opacity"] = 0.58
    return frame


def _combined_establishment_frame(
    region: dict[str, Any],
    wind_selected: pd.DataFrame,
    solar_selected: pd.DataFrame,
    target_resolution: int,
    source_resolution: int,
) -> pd.DataFrame:
    display_geometry_path = _area_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame()
    display_geometries = load_h3_display_geometries(
        display_geometry_path,
        preserve_source_geometry=True,
    )
    base = pd.DataFrame({"hex_id": sorted(str(hex_id) for hex_id in display_geometries)})
    if base.empty:
        return base

    wind_source_cell_areas: Mapping[str, float] | None = None
    wind_target_cell_areas: Mapping[str, float] | None = None
    solar_source_cell_areas: Mapping[str, float] | None = None
    solar_target_cell_areas: Mapping[str, float] | None = None
    region_id = str(region.get("region_id") or "")
    if not wind_selected.empty:
        wind_target_cell_areas = _cached_technology_support_cell_areas_km2(
            region_id,
            "wind",
            int(target_resolution),
        )
        wind_source_cell_areas = (
            wind_target_cell_areas
            if int(target_resolution) == int(source_resolution)
            else _cached_technology_support_cell_areas_km2(
                region_id,
                "wind",
                int(source_resolution),
            )
        )
    if not solar_selected.empty:
        solar_target_cell_areas = _cached_technology_support_cell_areas_km2(
            region_id,
            "solar",
            int(target_resolution),
        )
        solar_source_cell_areas = (
            solar_target_cell_areas
            if int(target_resolution) == int(source_resolution)
            else _cached_technology_support_cell_areas_km2(
                region_id,
                "solar",
                int(source_resolution),
            )
        )
    wind = _establishment_source_frame(
        wind_selected,
        "wind",
        int(target_resolution),
        int(source_resolution),
        target_cell_areas_km2=wind_target_cell_areas,
        source_cell_areas_km2=wind_source_cell_areas,
    )
    solar = _establishment_source_frame(
        solar_selected,
        "solar",
        int(target_resolution),
        int(source_resolution),
        target_cell_areas_km2=solar_target_cell_areas,
        source_cell_areas_km2=solar_source_cell_areas,
    )
    declared_parent_ids = set(base["hex_id"].astype(str))
    for technology, frame in (("wind", wind), ("solar", solar)):
        undeclared = sorted(
            set(frame.get("hex_id", pd.Series(dtype=str)).astype(str))
            - declared_parent_ids
        )
        if undeclared:
            raise ValueError(
                f"{technology} allocation rollup contains parents outside "
                "the declared display domain: "
                + ", ".join(undeclared[:5])
            )
    if not wind.empty:
        base = base.merge(wind, on="hex_id", how="left")
    if not solar.empty:
        base = base.merge(solar, on="hex_id", how="left")

    for technology in ["wind", "solar"]:
        bool_col = f"{technology}_suitable"
        if bool_col not in base.columns:
            base[bool_col] = False
        base[bool_col] = base[bool_col].map(lambda value: False if pd.isna(value) else bool(value))
        context_col = f"{technology}_context_status"
        if context_col not in base.columns:
            base[context_col] = "not_assessed"
        else:
            base[context_col] = base[context_col].fillna(
                "not_assessed"
            ).astype(str)
        for column in [
            f"{technology}_rank",
            f"{technology}_potential_score",
            f"{technology}_potential_area_km2",
            f"{technology}_allocated_area_km2",
            f"{technology}_allocated_gwh",
            f"{technology}_allocated_hex_share_pct",
            f"{technology}_conflict_area_km2",
            f"{technology}_expansion_ring",
        ]:
            if column not in base.columns:
                base[column] = 0.0
            base[column] = pd.to_numeric(base[column], errors="coerce").fillna(0.0)
        outside_col = f"{technology}_outside_lp"
        if outside_col not in base.columns:
            base[outside_col] = False
        base[outside_col] = base[outside_col].map(lambda value: False if pd.isna(value) else bool(value))
        overlap_col = f"{technology}_last_resort_overlap"
        if overlap_col not in base.columns:
            base[overlap_col] = False
        base[overlap_col] = base[overlap_col].map(lambda value: False if pd.isna(value) else bool(value))
        conflict_col = f"{technology}_conflict"
        if conflict_col not in base.columns:
            base[conflict_col] = False
        base[conflict_col] = base[conflict_col].map(lambda value: False if pd.isna(value) else bool(value))
        phase_col = f"{technology}_phase"
        if phase_col not in base.columns:
            base[phase_col] = ""
        base[phase_col] = base[phase_col].fillna("").astype(str)

    base["establishment_class"] = [
        _combined_establishment_class(bool(wind), bool(solar))
        for wind, solar in zip(base["wind_suitable"], base["solar_suitable"])
    ]
    base["wind_outside_lp_area_km2"] = pd.to_numeric(base.get("wind_conflict_area_km2"), errors="coerce").fillna(0.0).clip(lower=0.0)
    base["solar_outside_lp_area_km2"] = pd.to_numeric(base.get("solar_conflict_area_km2"), errors="coerce").fillna(0.0).clip(lower=0.0)
    base["outside_lp_shortage"] = base["wind_outside_lp_area_km2"].gt(0.0) | base["solar_outside_lp_area_km2"].gt(0.0)
    base["outside_lp_reason"] = [
        "vind + sol" if wind_area > 0 and solar_area > 0 else "vind" if wind_area > 0 else "sol" if solar_area > 0 else ""
        for wind_area, solar_area in zip(base["wind_outside_lp_area_km2"], base["solar_outside_lp_area_km2"])
    ]
    base["establishment_label"] = base["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["label"]
    )
    base["fill"] = base["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["color"]
    )
    base["stroke"] = base["establishment_class"].map(
        lambda class_id: ESTABLISHMENT_CLASS_SPECS.get(str(class_id), ESTABLISHMENT_CLASS_SPECS["not_suitable"])["stroke"]
    )
    base["stroke_weight"] = 0.12
    base["fill_opacity"] = 0.58
    return base


def _rollup_potential_establishment_frame(
    region: dict[str, Any],
    source_frame: pd.DataFrame,
    target_resolution: int,
    source_resolution: int,
    target_cell_areas_km2: Mapping[str, float],
) -> pd.DataFrame:
    display_geometry_path = _area_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame()
    display_geometries = load_h3_display_geometries(
        display_geometry_path,
        preserve_source_geometry=True,
    )
    base = pd.DataFrame({"hex_id": sorted(str(hex_id) for hex_id in display_geometries)})
    if base.empty:
        return base
    if source_frame.empty or "hex_id" not in source_frame.columns:
        base["establishment_class"] = "not_suitable"
        for technology in ["wind", "solar"]:
            base[f"{technology}_suitable"] = False
            base[f"{technology}_potential_score"] = 0.0
            base[f"{technology}_potential_area_km2"] = 0.0
        base["wind_outside_lp_area_km2"] = 0.0
        base["solar_outside_lp_area_km2"] = 0.0
        base["outside_lp_shortage"] = False
        base["outside_lp_reason"] = ""
        return _apply_establishment_style_columns(base)

    work = source_frame.copy()
    work["hex_id"] = work["hex_id"].astype(str).map(lambda value: str(h3.cell_to_parent(str(value), int(target_resolution))))
    target_hex_area_km2 = float(h3_hex_area_km2(int(target_resolution)))
    agg_spec: dict[str, Any] = {}

    def _context_rollup(values: pd.Series) -> str:
        statuses = set(values.fillna("not_assessed").astype(str))
        assessed = statuses - {"not_assessed"}
        if not assessed:
            return "not_assessed"
        if "not_assessed" in statuses or len(assessed) > 1:
            return "partial"
        return next(iter(assessed))

    for technology in ["wind", "solar"]:
        column = f"{technology}_potential_area_km2"
        if column in work.columns:
            work[column] = pd.to_numeric(
                work[column],
                errors="coerce",
            ).fillna(0.0)
            agg_spec[column] = (
                column,
                lambda values: math.fsum(float(value) for value in values),
            )
        context_col = f"{technology}_context_status"
        if context_col in work.columns:
            agg_spec[context_col] = (context_col, _context_rollup)

    rolled = (
        work.groupby("hex_id", as_index=False)
        .agg(**agg_spec)
        .sort_values("hex_id")
        .reset_index(drop=True)
    )
    base = base.merge(rolled, on="hex_id", how="left")

    for technology in ["wind", "solar"]:
        area_col = f"{technology}_potential_area_km2"
        if area_col not in base.columns:
            base[area_col] = 0.0
        potential_area = pd.to_numeric(
            base[area_col],
            errors="coerce",
        ).fillna(0.0).clip(lower=0.0)
        target_area_capacity = _establishment_cell_area_km2_series(
            base,
            target_cell_areas_km2,
            target_hex_area_km2,
            f"{technology} R{target_resolution}",
        )
        base[area_col] = pd.concat(
            [potential_area, target_area_capacity],
            axis=1,
        ).min(axis=1)
        base[f"{technology}_model_area_km2"] = (
            target_area_capacity.astype(float)
        )
        base[f"{technology}_potential_score"] = (
            base[area_col]
            / target_area_capacity
            * 100.0
        ).clip(lower=0.0, upper=100.0).round(1)
        context_col = f"{technology}_context_status"
        if context_col not in base.columns:
            base[context_col] = "not_assessed"
        else:
            base[context_col] = base[context_col].fillna(
                "not_assessed"
            ).astype(str)

    base["wind_suitable"] = pd.to_numeric(
        base["wind_potential_area_km2"],
        errors="coerce",
    ).fillna(0.0).gt(FLOAT_TOLERANCE)
    base["solar_suitable"] = pd.to_numeric(
        base["solar_potential_area_km2"],
        errors="coerce",
    ).fillna(0.0).gt(FLOAT_TOLERANCE)
    base["establishment_class"] = [
        _combined_establishment_class(bool(wind), bool(solar))
        for wind, solar in zip(
            base["wind_suitable"],
            base["solar_suitable"],
        )
    ]

    base["wind_outside_lp_area_km2"] = 0.0
    base["solar_outside_lp_area_km2"] = 0.0
    base["outside_lp_shortage"] = False
    base["outside_lp_reason"] = ""
    return _apply_establishment_style_columns(base)


def _merge_allocation_into_potential_establishment_frame(
    base: pd.DataFrame,
    allocation: pd.DataFrame,
) -> pd.DataFrame:
    result = base.copy()
    allocation_columns: list[str] = []
    for technology in ["wind", "solar"]:
        allocation_columns.extend(
            [
                f"{technology}_rank",
                f"{technology}_allocated_area_km2",
                f"{technology}_allocated_gwh",
                f"{technology}_allocated_hex_share_pct",
                f"{technology}_outside_lp",
                f"{technology}_conflict_area_km2",
                f"{technology}_conflict",
                f"{technology}_expansion_ring",
                f"{technology}_phase",
                f"{technology}_last_resort_overlap",
            ]
        )
    if not allocation.empty:
        allocation_ids = set(allocation["hex_id"].astype(str))
        base_ids = set(result["hex_id"].astype(str))
        undeclared = sorted(allocation_ids - base_ids)
        if undeclared:
            raise ValueError(
                "Potential-map allocation contains cells outside the "
                "declared display domain: "
                + ", ".join(undeclared[:5])
            )
        available_columns = ["hex_id"] + [
            column for column in allocation_columns if column in allocation.columns
        ]
        allocation_values = allocation[available_columns].copy()
        allocation_values["hex_id"] = allocation_values["hex_id"].astype(str)
        if allocation_values["hex_id"].duplicated().any():
            raise ValueError("Potential-map allocation cell ids must be unique")
        result = result.merge(
            allocation_values.rename(
                columns={
                    column: f"{column}__allocation"
                    for column in available_columns
                    if column != "hex_id"
                }
            ),
            on="hex_id",
            how="left",
            validate="one_to_one",
        )

    for technology in ["wind", "solar"]:
        context_col = f"{technology}_context_status"
        if context_col not in result.columns:
            result[context_col] = "not_assessed"
        else:
            result[context_col] = result[context_col].fillna(
                "not_assessed"
            ).astype(str)
        for column in [
            f"{technology}_potential_score",
            f"{technology}_potential_area_km2",
        ]:
            if column not in result.columns:
                result[column] = 0.0
            result[column] = pd.to_numeric(
                result[column],
                errors="coerce",
            ).fillna(0.0).clip(lower=0.0)
        for column in [
            f"{technology}_rank",
            f"{technology}_allocated_area_km2",
            f"{technology}_allocated_gwh",
            f"{technology}_allocated_hex_share_pct",
            f"{technology}_conflict_area_km2",
            f"{technology}_expansion_ring",
        ]:
            allocation_col = f"{column}__allocation"
            if allocation_col in result.columns:
                result[column] = pd.to_numeric(
                    result[allocation_col],
                    errors="coerce",
                ).fillna(0.0)
            elif column not in result.columns:
                result[column] = 0.0
            result[column] = pd.to_numeric(
                result[column],
                errors="coerce",
            ).fillna(0.0)
        for column in [
            f"{technology}_outside_lp",
            f"{technology}_conflict",
            f"{technology}_last_resort_overlap",
        ]:
            allocation_col = f"{column}__allocation"
            if allocation_col in result.columns:
                result[column] = result[allocation_col].map(
                    lambda value: False if pd.isna(value) else bool(value)
                )
            elif column not in result.columns:
                result[column] = False
            result[column] = result[column].map(
                lambda value: False if pd.isna(value) else bool(value)
            )
        phase_col = f"{technology}_phase"
        allocation_phase_col = f"{phase_col}__allocation"
        if allocation_phase_col in result.columns:
            result[phase_col] = result[allocation_phase_col].fillna("").astype(
                str
            )
        elif phase_col not in result.columns:
            result[phase_col] = ""
        else:
            result[phase_col] = result[phase_col].fillna("").astype(str)

    result["wind_suitable"] = result["wind_potential_area_km2"].gt(
        FLOAT_TOLERANCE
    )
    result["solar_suitable"] = result["solar_potential_area_km2"].gt(
        FLOAT_TOLERANCE
    )
    result["establishment_class"] = [
        _combined_establishment_class(bool(wind), bool(solar))
        for wind, solar in zip(
            result["wind_suitable"],
            result["solar_suitable"],
        )
    ]
    result["wind_outside_lp_area_km2"] = pd.to_numeric(
        result["wind_conflict_area_km2"],
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    result["solar_outside_lp_area_km2"] = pd.to_numeric(
        result["solar_conflict_area_km2"],
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    result["outside_lp_shortage"] = (
        result["wind_outside_lp_area_km2"].gt(0.0)
        | result["solar_outside_lp_area_km2"].gt(0.0)
    )
    result["outside_lp_reason"] = [
        (
            "vind + sol"
            if wind_area > 0.0 and solar_area > 0.0
            else "vind"
            if wind_area > 0.0
            else "sol"
            if solar_area > 0.0
            else ""
        )
        for wind_area, solar_area in zip(
            result["wind_outside_lp_area_km2"],
            result["solar_outside_lp_area_km2"],
        )
    ]
    result = result.drop(
        columns=[
            column for column in result.columns if column.endswith("__allocation")
        ],
        errors="ignore",
    )
    return _apply_establishment_style_columns(result)


def _combined_potential_establishment_frame(
    region: dict[str, Any],
    wind_potential: pd.DataFrame,
    solar_potential: pd.DataFrame,
    wind_selected: pd.DataFrame,
    solar_selected: pd.DataFrame,
    target_resolution: int,
    source_resolution: int,
    *,
    precomputed_allocation: pd.DataFrame | None = None,
    precomputed_source_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if (
        int(target_resolution) == int(source_resolution)
        and isinstance(precomputed_source_frame, pd.DataFrame)
    ):
        if "hex_id" not in precomputed_source_frame.columns:
            raise ValueError(
                "Precomputed combined establishment source requires hex_id"
            )
        return precomputed_source_frame.copy()
    display_geometry_path = _area_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame()
    display_geometries = load_h3_display_geometries(
        display_geometry_path,
        preserve_source_geometry=True,
    )
    base = pd.DataFrame({"hex_id": sorted(str(hex_id) for hex_id in display_geometries)})
    if base.empty:
        return base
    region_id = str(region.get("region_id") or "")
    source_cell_areas: Mapping[str, float] | None = None
    target_cell_areas: Mapping[str, float] | None = None
    if not wind_potential.empty or not solar_potential.empty:
        source_cell_areas = _cached_technology_support_cell_areas_km2(
            region_id,
            "wind",
            int(source_resolution),
        )
        target_cell_areas = _cached_technology_support_cell_areas_km2(
            region_id,
            "wind",
            int(target_resolution),
        )
    if (
        (not wind_potential.empty or not solar_potential.empty)
        and int(target_resolution) < int(source_resolution)
    ):
        source_frame = (
            precomputed_source_frame.copy()
            if isinstance(precomputed_source_frame, pd.DataFrame)
            else _combined_potential_establishment_frame(
                region,
                wind_potential,
                solar_potential,
                wind_selected,
                solar_selected,
                int(source_resolution),
                int(source_resolution),
                precomputed_allocation=precomputed_allocation,
            )
        )
        if target_cell_areas is None:
            raise ValueError(
                "Potential rollup requires manifest-declared target areas"
            )
        potential_rollup = _rollup_potential_establishment_frame(
            region,
            source_frame,
            int(target_resolution),
            int(source_resolution),
            target_cell_areas,
        )
        allocation = _combined_establishment_frame(
            region,
            wind_selected,
            solar_selected,
            int(target_resolution),
            int(source_resolution),
        )
        return _merge_allocation_into_potential_establishment_frame(
            potential_rollup,
            allocation,
        )

    wind = _potential_establishment_source_frame(
        wind_potential,
        "wind",
        int(target_resolution),
        int(source_resolution),
        source_cell_areas_km2=source_cell_areas,
        target_cell_areas_km2=target_cell_areas,
    )
    solar = _potential_establishment_source_frame(
        solar_potential,
        "solar",
        int(target_resolution),
        int(source_resolution),
        source_cell_areas_km2=source_cell_areas,
        target_cell_areas_km2=target_cell_areas,
    )
    if not wind.empty:
        base = base.merge(wind, on="hex_id", how="left")
    if not solar.empty:
        base = base.merge(solar, on="hex_id", how="left")

    allocation = (
        precomputed_allocation.copy()
        if isinstance(precomputed_allocation, pd.DataFrame)
        else _combined_establishment_frame(
            region,
            wind_selected,
            solar_selected,
            int(target_resolution),
            int(source_resolution),
        )
    )
    return _merge_allocation_into_potential_establishment_frame(
        base,
        allocation,
    )


def _h3_polygon_geometry(hex_id: str) -> dict[str, Any] | None:
    try:
        boundary = h3.cell_to_boundary(str(hex_id))
    except Exception:
        return None
    ring = [[float(lng), float(lat)] for lat, lng in boundary]
    if ring and ring[0] != ring[-1]:
        ring.append(ring[0])
    if not ring:
        return None
    return {"type": "Polygon", "coordinates": [ring]}


def _geometry_bbox_from_geometries(geometries: dict[str, Any]) -> tuple[float, float, float, float] | None:
    coords: list[tuple[float, float]] = []

    def _collect(value: Any) -> None:
        if isinstance(value, (list, tuple)) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            coords.append((float(value[0]), float(value[1])))
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                _collect(item)

    for geometry in geometries.values():
        if isinstance(geometry, dict):
            _collect(geometry.get("coordinates"))
    if not coords:
        return None
    lngs = [lng for lng, _ in coords]
    lats = [lat for _, lat in coords]
    return min(lngs), min(lats), max(lngs), max(lats)


def _region_bounds_tuple(region: dict[str, Any], fallback_bbox: tuple[float, float, float, float] | None) -> tuple[float, float, float, float] | None:
    raw = region.get("default_map_bounds")
    if isinstance(raw, list) and len(raw) == 2:
        try:
            south = float(raw[0][0])
            west = float(raw[0][1])
            north = float(raw[1][0])
            east = float(raw[1][1])
            if south < north and west < east:
                return west, south, east, north
        except Exception:
            pass
    if fallback_bbox is None:
        return None
    west, south, east, north = fallback_bbox
    lon_pad = max(0.05, (east - west) * 0.45)
    lat_pad = max(0.04, (north - south) * 0.25)
    return west - lon_pad, south - lat_pad, east + lon_pad, north + lat_pad


def _outside_lp_need_feature_collection(
    region: dict[str, Any],
    frame: pd.DataFrame,
    target_resolution: int,
    wind_area_override_km2: float | None = None,
    solar_area_override_km2: float | None = None,
) -> dict[str, Any]:
    """Draw area-faithful comparison hexagons beside the region, independent of zoom."""
    from potential_model.outside_schematic import build_schematic_polygons

    features: list[dict[str, Any]] = []
    if frame.empty or "outside_lp_shortage" not in frame.columns:
        if wind_area_override_km2 is None and solar_area_override_km2 is None:
            return {"type": "FeatureCollection", "features": features}
        selected = pd.DataFrame()
    else:
        selected = frame[frame["outside_lp_shortage"].fillna(False).astype(bool)]
    areas: dict[str, float] = {}
    for technology, override in (
        ("wind", wind_area_override_km2), ("solar", solar_area_override_km2)
    ):
        area = (
            float(pd.to_numeric(
                selected.get(f"{technology}_outside_lp_area_km2", pd.Series(dtype=float)),
                errors="coerce",
            ).fillna(0.0).clip(lower=0.0).sum())
            if override is None else max(0.0, float(override))
        )
        areas[technology] = area if area >= OUTSIDE_LP_NEED_DISPLAY_MIN_KM2 else 0.0
    if not any(areas.values()):
        return {"type": "FeatureCollection", "features": features}

    # The comparison uses a fixed, modest display mesh. Neither its location nor
    # its shape follows the main map's automatic H3 resolution changes.
    base_resolution = _zoom_family_base_resolution(region)
    display_resolution = min(7, base_resolution)
    display_path = _area_display_geometry_path(region, base_resolution)
    display_geometries = load_h3_display_geometries(
        display_path, preserve_source_geometry=True,
    )
    land_bbox = _geometry_bbox_from_geometries(display_geometries)
    if land_bbox is None:
        return {"type": "FeatureCollection", "features": features}
    polygons = build_schematic_polygons(
        land_bbox, areas, float(h3_hex_area_km2(display_resolution)),
    )
    for index, item in enumerate(polygons):
        technology = item["technology"]
        label = "Vind" if technology == "wind" else "Sol"
        area = float(item["area_km2"])
        features.append({
            "type": "Feature", "geometry": item["geometry"],
            "properties": {
                "hex_id": f"schematic-{technology}-{index}",
                "schematic_technology": technology,
                "schematic_label": label,
                "represented_area_km2": area,
                "fill": "#2563eb" if technology == "wind" else "#facc15",
                "stroke": "#dbeafe", "stroke_weight": 0.26,
                "fill_opacity": 0.76 if technology == "wind" else 0.82,
                "tooltip_title": f"Schematisk jämförelseyta: {label}",
                "tooltip_body": f"{area:.2f} km² · inte föreslagen placering",
                "popup": (
                    f"<strong>{OUTSIDE_LP_NEED_LAYER_LABEL}</strong><br>"
                    f"Teknik: {label}<br>Schematisk yta: {area:.3f} km²<br>"
                    "Schematisk jämförelseyta – visar ytbehov, inte föreslagen placering."
                ),
            },
        })
    schematic_bbox = _geometry_bbox_from_geometries(
        {str(i): feature["geometry"] for i, feature in enumerate(features)}
    )
    west, south, east, north = land_bbox
    if schematic_bbox is not None:
        sw, ss, se, sn = schematic_bbox
        west, south, east, north = min(west, sw), min(south, ss), max(east, se), max(north, sn)
    return {
        "type": "FeatureCollection", "features": features,
        "initial_bounds": [[south, west], [north, east]],
    }


def _outside_lp_need_layer(
    region: dict[str, Any],
    frame: pd.DataFrame,
    target_resolution: int,
    wind_area_km2: float | None = None,
    solar_area_km2: float | None = None,
) -> dict[str, Any] | None:
    if frame.empty and wind_area_km2 is None and solar_area_km2 is None:
        return None
    feature_collection = _outside_lp_need_feature_collection(region, frame, int(target_resolution), wind_area_km2, solar_area_km2)
    if not feature_collection.get("features"):
        return None
    return {
        "name": OUTSIDE_LP_NEED_LAYER_LABEL,
        "feature_collection": feature_collection,
        "fill_property": "fill",
        "fill_opacity_property": "fill_opacity",
        "stroke_property": "stroke",
        "stroke_weight_property": "stroke_weight",
        "legend_items": [
            {"label": "Schematisk vindyta utanför potential", "color": "#2563eb"},
            {"label": "Schematisk solyta utanför potential", "color": "#facc15"},
        ],
        "legend_id": "outside_lp_need",
        "legend_title": OUTSIDE_LP_NEED_LAYER_LABEL,
        "legend_note": "Schematisk jämförelseyta – visar ytbehov, inte föreslagen placering.",
        "initial_bounds": feature_collection["initial_bounds"],
        "default_visible": True,
        "stroke": True,
        "stroke_opacity": 0.55,
        "fill_opacity": 0.76,
        "weight": 0.28,
        "z_index": 486,
        "layer_kind": "hex",
        "opacity_family": OUTSIDE_LP_NEED_LAYER_LABEL,
        "opacity_label": OUTSIDE_LP_NEED_LAYER_LABEL,
    }


def _outside_lp_need_family_layers(
    region: dict[str, Any],
    wind_selected: pd.DataFrame,
    solar_selected: pd.DataFrame,
    selected_resolution: int,
    zoom_family_enabled: bool,
    source_resolution: int | None = None,
    wind_area_km2: float | None = None,
    solar_area_km2: float | None = None,
) -> list[dict[str, Any]]:
    if (
        (wind_area_km2 is None or max(0.0, float(wind_area_km2 or 0.0)) < OUTSIDE_LP_NEED_DISPLAY_MIN_KM2)
        and (solar_area_km2 is None or max(0.0, float(solar_area_km2 or 0.0)) < OUTSIDE_LP_NEED_DISPLAY_MIN_KM2)
    ):
        wind_area_km2 = 0.0 if wind_area_km2 is not None else None
        solar_area_km2 = 0.0 if solar_area_km2 is not None else None
    if wind_selected.empty and solar_selected.empty and wind_area_km2 is None and solar_area_km2 is None:
        return []
    source_resolution = int(source_resolution or selected_resolution)
    source_frame = _combined_establishment_frame(
        region,
        wind_selected,
        solar_selected,
        int(source_resolution),
        int(source_resolution),
    )
    if source_frame.empty and wind_area_km2 is None and solar_area_km2 is None:
        return []
    layer = _outside_lp_need_layer(
        region, source_frame, _zoom_family_base_resolution(region),
        wind_area_km2, solar_area_km2,
    )
    return [layer] if layer is not None else []


SCENARIO_ALLOCATION_SPECS: dict[str, dict[str, Any]] = {
    "wind": {
        "label": "Scenarioyta: vind",
        "legend_label": "Vind",
        "fill": "#005A8D",
    },
    "solar": {
        "label": "Scenarioyta: sol",
        "legend_label": "Sol",
        "fill": "#F2B01E",
    },
    "both": {
        "label": "Scenarioyta: vind + sol i samma kartcell",
        "legend_label": "Vind och sol",
        "fill": "#145A32",
    },
}


def _scenario_allocation_class(
    wind_allocated: bool,
    solar_allocated: bool,
) -> str:
    if wind_allocated and solar_allocated:
        return "both"
    if wind_allocated:
        return "wind"
    if solar_allocated:
        return "solar"
    return ""


def _scenario_allocation_marker_feature_collection(
    frame: pd.DataFrame,
    target_resolution: int,
    *,
    display_geometries: dict[str, dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    if frame.empty:
        return {"type": "FeatureCollection", "features": features}

    def _priority_html(row: Any, technology: str, label: str) -> str:
        allocated_area = max(
            0.0,
            float(
                getattr(row, f"{technology}_allocated_area_km2", 0.0)
                or 0.0
            )
            - float(
                getattr(row, f"{technology}_conflict_area_km2", 0.0)
                or 0.0
            ),
        )
        if allocated_area <= FLOAT_TOLERANCE:
            return ""
        landscape_score = float(getattr(row, f"{technology}_landscape_priority_score", 0.0) or 0.0)
        allocation_score = float(getattr(row, f"{technology}_allocation_priority_score", 0.0) or 0.0)
        social_pct = float(getattr(row, f"{technology}_social_acceptance_allocation_priority_pct", 0.0) or 0.0)
        social_score = float(getattr(row, f"{technology}_social_acceptance_priority_score", 0.0) or 0.0)
        reason = html.escape(str(getattr(row, f"{technology}_allocation_priority_reason", "") or ""))
        lines = [
            f"<strong>{label}: varför här?</strong>",
            f"Landskaps-/teknikranking: {landscape_score * 100.0:.0f}%",
        ]
        if social_pct > 0.0:
            lines.append(f"Slutlig ranking efter social acceptans ({social_pct:.0f}%): {social_score * 100.0:.0f}%")
        else:
            lines.append(f"Slutlig ranking: {allocation_score * 100.0:.0f}%")
        if reason:
            lines.append(f"Förklaring: {reason}")
        return "<br>".join(lines) + "<br>"

    for row in frame.itertuples(index=False):
        wind_total_area = float(
            getattr(row, "wind_allocated_area_km2", 0.0) or 0.0
        )
        solar_total_area = float(
            getattr(row, "solar_allocated_area_km2", 0.0) or 0.0
        )
        wind_conflict_area = float(
            getattr(row, "wind_conflict_area_km2", 0.0) or 0.0
        )
        solar_conflict_area = float(
            getattr(row, "solar_conflict_area_km2", 0.0) or 0.0
        )
        wind_area = max(
            0.0,
            wind_total_area - wind_conflict_area,
        )
        solar_area = max(
            0.0,
            solar_total_area - solar_conflict_area,
        )
        parent_hex = str(getattr(row, "hex_id", "") or "")
        parent_class = str(
            getattr(row, "establishment_class", "") or ""
        )
        wind_in_parent = bool(getattr(row, "wind_suitable", False))
        solar_in_parent = bool(getattr(row, "solar_suitable", False))
        # Allocation totals remain exact. Marker visibility uses the same
        # numerical floor as the potential-parent class so floating-point
        # slivers cannot create a full-size child marker in another class.
        wind_allocated = wind_area > FLOAT_TOLERANCE
        solar_allocated = solar_area > FLOAT_TOLERANCE
        if wind_allocated and not wind_in_parent:
            raise ValueError(
                "Scenario marker wind allocation is incompatible with "
                f"potential parent R{int(target_resolution)} {parent_hex} "
                f"({parent_class or 'missing class'})"
            )
        if solar_allocated and not solar_in_parent:
            raise ValueError(
                "Scenario marker solar allocation is incompatible with "
                f"potential parent R{int(target_resolution)} {parent_hex} "
                f"({parent_class or 'missing class'})"
            )
        expected_parent_class = _combined_establishment_class(
            wind_in_parent,
            solar_in_parent,
        )
        if parent_class != expected_parent_class:
            raise ValueError(
                "Scenario marker potential parent class is inconsistent for "
                f"R{int(target_resolution)} {parent_hex}: "
                f"{parent_class or 'missing'} != {expected_parent_class}"
            )
        class_id = _scenario_allocation_class(
            wind_allocated,
            solar_allocated,
        )
        if not class_id:
            continue
        spec = SCENARIO_ALLOCATION_SPECS[class_id]
        if display_geometries is None:
            geometry = _h3_polygon_geometry(parent_hex)
            if geometry is None:
                continue
        else:
            if parent_hex not in display_geometries:
                raise ValueError(
                    f"Scenario marker lacks potential display geometry for {parent_hex}"
                )
            # The ordinary route supplies the final potential outlines, including
            # clipped MultiPolygons and null outlines. None means non-drawn,
            # rather than permission to invent a full un-clipped H3 polygon.
            geometry = display_geometries[parent_hex]
        if class_id == "both":
            note = (
                "Mörkgrön fyllning visar att både vind och sol "
                "har scenarioyta i samma visningshex. Markören visar inte "
                "exakt fysisk överlappning inom hexen."
            )
        else:
            note = "Markören visar scenariots placering från den mest lämpade ytan först enligt aktiva filter och prioriteringar."
        popup = (
            f"<strong>{SCENARIO_ALLOCATION_LAYER_LABEL}</strong><br>"
            f"{spec['label']}<br>"
            f"Parent-hex: R{int(target_resolution)} {parent_hex}<br>"
            f"Vindyta inom landskapspotential: {wind_area:.3f} km²<br>"
            f"Solyta inom landskapspotential: {solar_area:.3f} km²<br>"
            f"{_priority_html(row, 'wind', 'Vind')}"
            f"{_priority_html(row, 'solar', 'Sol')}"
            f"{note}"
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": parent_hex,
                    "parent_hex_id": parent_hex,
                    "parent_establishment_class": parent_class,
                    "allocation_class": class_id,
                    "allocation_label": spec["label"],
                    "wind_allocated_area_km2": wind_area,
                    "solar_allocated_area_km2": solar_area,
                    "fill": spec["fill"],
                    "stroke_weight": 0.0,
                    "fill_opacity": 1.0,
                    "tooltip_title": spec["label"],
                    "tooltip_body": f"Vind {wind_area:.2f} km² · sol {solar_area:.2f} km²",
                    "popup": popup,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _scenario_allocation_marker_layer(
    frame: pd.DataFrame,
    target_resolution: int,
    default_visible: bool | None = None,
    *,
    display_geometries: dict[str, dict[str, Any] | None] | None = None,
) -> dict[str, Any] | None:
    if frame.empty:
        return None
    feature_collection = _scenario_allocation_marker_feature_collection(
        frame, int(target_resolution), display_geometries=display_geometries,
    )
    feature_count = len(feature_collection.get("features", []))
    # A nonempty parent frame keeps its resolution member even when no marker
    # crosses the display tolerance. This prevents the marker family from
    # falling back to a coarser parent than the visible potential family.
    return {
        "name": SCENARIO_ALLOCATION_LAYER_LABEL,
        "feature_collection": feature_collection,
        "fill_property": "fill",
        "fill_opacity_property": "fill_opacity",
        "legend_items": [
            {
                "label": str(spec["legend_label"]),
                "color": str(spec["fill"]),
            }
            for spec in SCENARIO_ALLOCATION_SPECS.values()
        ],
        "legend_id": "scenario_allocation",
        "legend_title": SCENARIO_ALLOCATION_LAYER_LABEL,
        "legend_note": (
            "Båda teknikerna i samma visningshex, inte säkerställd "
            "fysisk överlappning. Cellens storlek visar "
            "inte allokerad yta."
        ),
        "default_visible": bool(default_visible) if default_visible is not None else int(target_resolution) <= 9 and feature_count <= 12000,
        "stroke": False,
        "stroke_opacity": 0.0,
        "fill_opacity": 1.0,
        "weight": 0.0,
        "z_index": 540,
        "layer_kind": "hex",
        "opacity_family": SCENARIO_ALLOCATION_LAYER_LABEL,
        "opacity_label": SCENARIO_ALLOCATION_LAYER_LABEL,
    }


def _scenario_allocation_marker_family_layers(
    region: dict[str, Any],
    wind_potential: pd.DataFrame,
    solar_potential: pd.DataFrame,
    wind_selected: pd.DataFrame,
    solar_selected: pd.DataFrame,
    selected_resolution: int,
    zoom_family_enabled: bool,
    source_resolution: int | None = None,
    precomputed_source_frame: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    if wind_selected.empty and solar_selected.empty:
        return []
    source_resolution = int(source_resolution or selected_resolution)
    layers = _hex_family_layers(
        region,
        int(selected_resolution),
        bool(zoom_family_enabled),
        "scenario_allocation",
        SCENARIO_ALLOCATION_LAYER_LABEL,
        lambda resolution: _scenario_allocation_marker_layer(
            _combined_potential_establishment_frame(
                region,
                wind_potential,
                solar_potential,
                wind_selected,
                solar_selected,
                int(resolution),
                int(source_resolution),
                precomputed_source_frame=precomputed_source_frame,
            ),
            int(resolution),
            default_visible=False,
        ),
    )
    if not any(
        layer.get("feature_collection", {}).get("features", [])
        for layer in layers
    ):
        return []
    return layers


def _potential_popup_percent(
    potential_score: float,
    potential_area_km2: float,
) -> str:
    score = float(potential_score or 0.0)
    area = float(potential_area_km2 or 0.0)
    if not math.isfinite(score):
        score = 0.0
    if not math.isfinite(area):
        area = 0.0
    score = max(0.0, min(100.0, score))
    if area > 0.0 and score < 0.1:
        return "&lt;0.1%"
    return f"{score:.1f}%"


def _potential_popup_area(potential_area_km2: float) -> str:
    area = float(potential_area_km2 or 0.0)
    if not math.isfinite(area) or area <= 0.0:
        return "0.000 km²"
    if area < 0.001:
        return "&lt;0.001 km²"
    return f"{area:.3f} km²"


def _combined_establishment_feature_collection(
    frame: pd.DataFrame,
    display_geometry_path: str,
    target_resolution: int,
) -> dict[str, Any]:
    display_geometries = load_h3_display_geometries(
        display_geometry_path,
        preserve_source_geometry=True,
    )
    features: list[dict[str, Any]] = []

    def _potential_score(
        row: Any,
        technology: str,
    ) -> float:
        try:
            value = float(
                getattr(row, f"{technology}_potential_score", 0.0) or 0.0
            )
        except (TypeError, ValueError):
            value = 0.0
        if not math.isfinite(value):
            value = 0.0
        value = max(0.0, min(100.0, value))
        return value

    def _tech_html(
        row: Any,
        technology: str,
        label: str,
        score_label: str,
        acceptance_weight: float | None,
    ) -> tuple[str, bool, int]:
        suitable = bool(getattr(row, f"{technology}_suitable", False))
        potential_score = _potential_score(row, technology)
        potential_area = float(getattr(row, f"{technology}_potential_area_km2", 0.0) or 0.0)
        allocated_area = float(getattr(row, f"{technology}_allocated_area_km2", 0.0) or 0.0)
        allocated_share = float(getattr(row, f"{technology}_allocated_hex_share_pct", 0.0) or 0.0)
        allocated_gwh = getattr(row, f"{technology}_allocated_gwh", None)
        conflict_area = float(getattr(row, f"{technology}_conflict_area_km2", 0.0) or 0.0)
        rank = int(float(getattr(row, f"{technology}_rank", 0.0) or 0.0))
        lines = [
            f"<strong>{label}</strong>",
            f"Potential efter filter: {'ja' if suitable else 'nej'}",
            f"{score_label}: {_potential_popup_percent(potential_score, potential_area)}",
            f"Potentiell yta: {_potential_popup_area(potential_area)}",
        ]
        if acceptance_weight is not None:
            adjusted_score = potential_score * max(0.0, min(1.0, float(acceptance_weight)))
            adjusted_area = potential_area * acceptance_weight
            lines.extend(
                [
                    "Efter acceptanspåverkan: "
                    f"{_potential_popup_percent(adjusted_score, adjusted_area)}",
                    "Acceptansjusterad potentiell yta: "
                    f"{_potential_popup_area(adjusted_area)}",
                ]
            )
        if allocated_area > 0:
            rank_label = f" · prioritet {rank}" if rank > 0 else ""
            lines.append(f"Scenarioyta i hex: {allocated_area:.3f} km² ({allocated_share:.1f}% av hex){rank_label}")
            if allocated_gwh is not None and pd.notna(allocated_gwh):
                lines.append(f"Scenarioenergi: {float(allocated_gwh):.2f} GWh")
        if conflict_area > 0:
            lines.append(f"Scenarioyta utanför potential: {conflict_area:.3f} km²")
        tooltip_score = adjusted_score if acceptance_weight is not None else potential_score
        return "<br>".join(lines) + "<br>", suitable, int(round(tooltip_score))

    context_labels = {
        "app_extent": "appens standardutbredning",
        "full_lablab": "full LABLAB-källa",
        "partial": "delvis bedömd",
        "not_assessed": "inte bedömd",
    }

    for row in frame.itertuples(index=False):
        geometry = display_geometries.get(str(row.hex_id))
        if geometry is None:
            continue
        class_id = str(getattr(row, "establishment_class", "not_suitable") or "not_suitable")
        label = str(getattr(row, "establishment_label", ESTABLISHMENT_CLASS_SPECS["not_suitable"]["label"]))
        outside_lp_shortage = bool(getattr(row, "outside_lp_shortage", False))
        outside_lp_reason = str(getattr(row, "outside_lp_reason", "") or "")
        social_acceptance_impact = float(getattr(row, "social_acceptance_impact_pct", 0.0) or 0.0)
        social_acceptance_status = str(
            getattr(row, "social_acceptance_data_status", "not_requested")
            or "not_requested"
        )
        raw_social_value = getattr(row, "social_acceptance_value", math.nan)
        raw_social_weight = getattr(row, "social_acceptance_weight", math.nan)
        try:
            social_acceptance_value = float(raw_social_value)
        except (TypeError, ValueError):
            social_acceptance_value = math.nan
        try:
            social_acceptance_weight = float(raw_social_weight)
        except (TypeError, ValueError):
            social_acceptance_weight = math.nan
        social_acceptance_available = (
            social_acceptance_data_status_is_available(
                social_acceptance_status
            )
            and math.isfinite(social_acceptance_value)
        )
        applied_acceptance_weight = (
            max(0.0, min(1.0, social_acceptance_weight))
            if social_acceptance_impact > 0.0
            and math.isfinite(social_acceptance_weight)
            else None
        )
        social_acceptance_source_hex_count = int(float(getattr(row, "social_acceptance_source_hex_count", 0.0) or 0.0))
        social_acceptance_popup = ""
        if social_acceptance_impact > 0.0 and social_acceptance_available:
            social_acceptance_popup = (
                "<br><strong>Social acceptans</strong><br>"
                f"Acceptansvärde: {social_acceptance_value:.3f}<br>"
                f"Datastatus: {html.escape(social_acceptance_status)}<br>"
                f"Acceptanspåverkan: {social_acceptance_impact:.0f}%<br>"
                f"Färgvikt: {social_acceptance_weight:.3f}<br>"
                f"Källhex: {social_acceptance_source_hex_count}"
            )
        elif social_acceptance_impact > 0.0:
            social_acceptance_popup = (
                "<br><strong>Social acceptans</strong><br>"
                "Kontextdata saknas för denna teknikcell."
            )
        wind_context_status = str(
            getattr(row, "wind_context_status", "not_assessed")
            or "not_assessed"
        )
        solar_context_status = str(
            getattr(row, "solar_context_status", "not_assessed")
            or "not_assessed"
        )
        technology_context_popup = (
            "<br><strong>Landskapskontext</strong><br>"
            f"Vind: {context_labels.get(wind_context_status, wind_context_status)}<br>"
            f"Sol: {context_labels.get(solar_context_status, solar_context_status)}"
        )
        wind_html, wind_suitable, wind_percent = _tech_html(
            row, 'wind', 'Vind', 'Vindpotential', applied_acceptance_weight,
        )
        solar_html, solar_suitable, solar_percent = _tech_html(
            row, 'solar', 'Sol', 'Solpotential', applied_acceptance_weight,
        )
        popup = (
            f"<strong>{COMBINED_ESTABLISHMENT_LAYER_LABEL}</strong><br>"
            "Klassning: potential efter aktiva filter<br>"
            f"Klass: {label}<br>"
            f"Hex: {row.hex_id}<br>"
            f"{wind_html}"
            f"{solar_html}"
            f"H3: R{int(target_resolution)}"
            f"{technology_context_popup}"
            f"{social_acceptance_popup}"
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": {
                    "hex_id": str(row.hex_id),
                    "establishment_class": class_id,
                    "establishment_label": label,
                    "outside_lp_shortage": outside_lp_shortage,
                    "outside_lp_reason": outside_lp_reason,
                    "wind_outside_lp_area_km2": float(getattr(row, "wind_outside_lp_area_km2", 0.0) or 0.0),
                    "solar_outside_lp_area_km2": float(getattr(row, "solar_outside_lp_area_km2", 0.0) or 0.0),
                    "wind_suitable": wind_suitable,
                    "solar_suitable": solar_suitable,
                    "wind_context_status": wind_context_status,
                    "solar_context_status": solar_context_status,
                    "fill": str(getattr(row, "fill", ESTABLISHMENT_CLASS_SPECS["not_suitable"]["color"])),
                    "stroke": str(getattr(row, "stroke", ESTABLISHMENT_CLASS_SPECS["not_suitable"]["stroke"])),
                    "stroke_weight": float(getattr(row, "stroke_weight", 0.38) or 0.38),
                    "fill_opacity": float(getattr(row, "fill_opacity", 0.58) or 0.58),
                    "social_acceptance_value": (
                        social_acceptance_value
                        if social_acceptance_available
                        else None
                    ),
                    "social_acceptance_data_status": social_acceptance_status,
                    "social_acceptance_impact_pct": social_acceptance_impact,
                    "social_acceptance_weight": (
                        social_acceptance_weight
                        if math.isfinite(social_acceptance_weight)
                        else None
                    ),
                    "social_acceptance_source_hex_count": social_acceptance_source_hex_count,
                    "tooltip_title": label,
                    "tooltip_body": (
                        "Efter acceptanspåverkan: "
                        f"vind {wind_percent} % · "
                        f"sol {solar_percent} %"
                        if applied_acceptance_weight is not None
                        else (
                            f"Vindpotential: {wind_percent} % · "
                            f"Solpotential: {solar_percent} %"
                        )
                    ),
                    "popup": popup,
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def _combined_establishment_layer(
    frame: pd.DataFrame,
    display_geometry_path: str | None,
    target_resolution: int,
) -> dict[str, Any] | None:
    if frame.empty or not display_geometry_path:
        return None
    reference_outline_features: list[dict[str, Any]] = []
    if len(frame) <= 5_000:
        for hex_id in frame["hex_id"].astype(str):
            geometry = _h3_polygon_geometry(str(hex_id))
            if geometry is not None:
                reference_outline_features.append(
                    {
                        "type": "Feature",
                        "geometry": geometry,
                        "properties": {"hex_id": str(hex_id)},
                    }
                )
    return {
        "name": COMBINED_ESTABLISHMENT_LAYER_LABEL,
        "feature_collection": _combined_establishment_feature_collection(frame, display_geometry_path, int(target_resolution)),
        "reference_outline_feature_collection": {
            "type": "FeatureCollection",
            "features": reference_outline_features,
        },
        "reference_outline_color": "#f8fafc",
        "reference_outline_opacity": 0.72,
        "reference_outline_weight": 0.58,
        "fill_property": "fill",
        "fill_opacity_property": "fill_opacity",
        "stroke_property": "stroke",
        "stroke_weight_property": "stroke_weight",
        "legend_items": _combined_establishment_legend_items(),
        "legend_id": "combined_establishment",
        "legend_title": COMBINED_ESTABLISHMENT_LAYER_LABEL,
        "default_visible": True,
        "stroke": True,
        "stroke_opacity": 0.72,
        "fill_opacity": 0.58,
        "weight": 0.12,
        "z_index": 476,
        "layer_kind": "hex",
        "interaction_role": PRIMARY_RESULT_INTERACTION_ROLE,
        "opacity_family": COMBINED_ESTABLISHMENT_LAYER_LABEL,
        "opacity_label": COMBINED_ESTABLISHMENT_LAYER_LABEL,
    }


def _combined_establishment_family_layers(
    region: dict[str, Any],
    wind_selected: pd.DataFrame,
    solar_selected: pd.DataFrame,
    selected_resolution: int,
    zoom_family_enabled: bool,
    social_acceptance_result: SocialAcceptanceResult | None = None,
) -> list[dict[str, Any]]:
    if wind_selected.empty and solar_selected.empty:
        return []

    def build_layer(resolution: int) -> dict[str, Any] | None:
        frame = _combined_establishment_frame(
            region,
            wind_selected,
            solar_selected,
            int(resolution),
            int(selected_resolution),
        )
        frame = _apply_social_acceptance_impact_to_establishment_frame(
            frame,
            social_acceptance_result,
            int(resolution),
        )
        return _combined_establishment_layer(
            frame,
            _area_display_geometry_path(region, int(resolution)),
            int(resolution),
        )

    return _hex_family_layers(
        region,
        int(selected_resolution),
        bool(zoom_family_enabled),
        "combined_establishment",
        COMBINED_ESTABLISHMENT_LAYER_LABEL,
        build_layer,
    )


def _combined_potential_establishment_family_layers(
    region: dict[str, Any],
    wind_potential: pd.DataFrame,
    solar_potential: pd.DataFrame,
    wind_selected: pd.DataFrame,
    solar_selected: pd.DataFrame,
    selected_resolution: int,
    zoom_family_enabled: bool,
    source_resolution: int | None = None,
    social_acceptance_result: SocialAcceptanceResult | None = None,
    precomputed_source_frame: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    if wind_potential.empty and solar_potential.empty:
        return []
    source_resolution = int(source_resolution or selected_resolution)

    def build_layer(resolution: int) -> dict[str, Any] | None:
        frame = _combined_potential_establishment_frame(
            region,
            wind_potential,
            solar_potential,
            wind_selected,
            solar_selected,
            int(resolution),
            int(source_resolution),
            precomputed_source_frame=precomputed_source_frame,
        )
        frame = _apply_social_acceptance_impact_to_establishment_frame(
            frame,
            social_acceptance_result,
            int(resolution),
        )
        return _combined_establishment_layer(
            frame,
            _area_display_geometry_path(region, int(resolution)),
            int(resolution),
        )

    return _hex_family_layers(
        region,
        int(selected_resolution),
        bool(zoom_family_enabled),
        "combined_establishment",
        COMBINED_ESTABLISHMENT_LAYER_LABEL,
        build_layer,
    )


def _signed_combined_establishment_family_layers(
    region: dict[str, Any],
    bundle: CombinedResultExecutionBundle,
    social_acceptance_result: SocialAcceptanceResult,
    selected_resolution: int,
    zoom_family_enabled: bool,
) -> list[dict[str, Any]]:
    """Retain signed facts, with one area-dominant display colour per parent."""

    layers = _hex_family_layers(
        region,
        int(selected_resolution),
        bool(zoom_family_enabled),
        "combined_establishment",
        COMBINED_ESTABLISHMENT_LAYER_LABEL,
        lambda resolution: _combined_establishment_layer(
            _combined_result_compatibility_frame(
                bundle,
                int(resolution),
                social_acceptance_result,
            ),
            _area_display_geometry_path(region, int(resolution)),
            int(resolution),
        ),
    )
    source_resolution = bundle.combined_result.request.finalization_resolution
    source_frame = _combined_result_compatibility_frame(
        bundle, source_resolution, social_acceptance_result,
    )
    source_areas = {
        cell.cell_id: cell.technologies[0].model_area_km2
        for cell in bundle.combined_result.resolution_result(source_resolution).cells
    }
    layers = colour_rollup_layers(
        layers,
        ((str(row.hex_id), str(row.establishment_class), source_areas[str(row.hex_id)])
         for row in source_frame.itertuples(index=False)),
        source_resolution,
        ESTABLISHMENT_CLASS_SPECS,
    )
    return use_h3_parent_boundaries(layers, source_resolution, str(region["region_id"]))


def _signed_scenario_allocation_marker_family_layers(
    region: dict[str, Any],
    bundle: CombinedResultExecutionBundle,
    social_acceptance_result: SocialAcceptanceResult,
    selected_resolution: int,
    zoom_family_enabled: bool,
    *,
    potential_layers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # Reuse the already-finalized potential geometry, after parent clipping.
    # Rebuilding a footprint from scenario-only cells would change the outline.
    display_by_resolution = {
        int(layer.get("auto_resolution", selected_resolution)): {
            str(feature["properties"]["hex_id"]): feature["geometry"]
            for feature in layer["feature_collection"]["features"]
        }
        for layer in potential_layers
        if layer.get("legend_id") == "combined_establishment"
    }

    def layer_at_resolution(resolution: int) -> dict[str, Any] | None:
        if resolution not in display_by_resolution:
            raise ValueError(
                f"Scenario markers lack potential display resolution R{resolution}"
            )
        return _scenario_allocation_marker_layer(
            _combined_result_compatibility_frame(
                bundle, int(resolution), social_acceptance_result,
            ),
            int(resolution),
            default_visible=False,
            display_geometries=display_by_resolution[resolution],
        )

    layers = _hex_family_layers(
        region,
        int(selected_resolution),
        bool(zoom_family_enabled),
        "scenario_allocation",
        SCENARIO_ALLOCATION_LAYER_LABEL,
        layer_at_resolution,
    )
    return layers if any(
        layer.get("feature_collection", {}).get("features", []) for layer in layers
    ) else []


def _wind_runtime_hex_layers(
    region: dict[str, Any],
    runtime_result: dict[str, Any],
    preferred_resolution: int,
    zoom_family_enabled: bool,
    family_key: str = "wind_runtime_share",
    control_name: str = WIND_POTENTIAL_HEX_LABEL,
) -> list[dict[str, Any]]:
    preferred = min(int(preferred_resolution), WIND_RUNTIME_BASE_RESOLUTION)
    return _hex_family_layers(
        region,
        preferred,
        bool(zoom_family_enabled),
        family_key,
        control_name,
        lambda resolution: _wind_runtime_hex_layer(region, runtime_result, int(resolution), control_name),
    )


@st.cache_data(show_spinner=False, max_entries=16)
def _wind_polygon_preview_state(
    region: dict[str, Any],
    ui_params: dict[str, float],
    layer_selection: dict[str, list[str]],
    target_resolution: int,
    zoom_family_enabled: bool,
    *,
    workspace_request: WorkspaceAnalysisRequest,
    workspace_bundle_signature_sha256: str,
    _workspace_bundle: WorkspaceExecutionBundle,
    family_key: str = "wind_runtime_share",
    control_name: str = WIND_POTENTIAL_HEX_LABEL,
) -> dict[str, Any]:
    if (
        not isinstance(workspace_bundle_signature_sha256, str)
        or len(workspace_bundle_signature_sha256) != 64
        or any(
            value not in "0123456789abcdef"
            for value in workspace_bundle_signature_sha256
        )
        or _workspace_bundle.execution_signature_sha256
        != workspace_bundle_signature_sha256
    ):
        raise ValueError("Wind workspace bundle signature drifted")
    runtime_error: str | None = None
    preview_errors: list[str] = []
    selected = normalize_group_layer_map(
        layer_selection,
        str(region.get("region_id") or ""),
    )
    runtime_result: dict[str, Any] | None = None
    try:
        runtime_result = _wind_fast_distance_runtime_result(
            region,
            ui_params,
            selected,
            int(target_resolution),
            workspace_request=workspace_request,
            workspace_bundle=_workspace_bundle,
        )
        if runtime_result is None:
            raise ValueError(
                "The applied wind workspace request did not produce a "
                "validated manifest result"
            )
    except Exception as exc:
        runtime_error = str(exc)
    if not isinstance(runtime_result, dict):
        runtime_result = {"groups": {}, "combined": None, "cache_key": None}

    layers: list[dict[str, Any]] = []
    hex_layers: list[dict[str, Any]] = []
    if not runtime_error and bool(runtime_result.get("fast_distance")):
        def build_fast_distance_layer(resolution: int) -> dict[str, Any] | None:
            layer_result = runtime_result
            if int(resolution) != int(target_resolution):
                layer_result = _wind_fast_distance_runtime_result(
                    region,
                    ui_params,
                    selected,
                    int(resolution),
                    workspace_request=workspace_request,
                )
            if layer_result is None:
                return None
            return _wind_runtime_hex_layer(region, layer_result, int(resolution), control_name)

        hex_layers = _hex_family_layers(
            region,
            int(target_resolution),
            bool(zoom_family_enabled),
            family_key,
            control_name,
            build_fast_distance_layer,
        )
        layers.extend(hex_layers)

    return {
        "layers": layers,
        "runtime_error": runtime_error,
        "preview_errors": preview_errors,
        "runtime_result": runtime_result,
        "active_source_count": sum(len(layer_ids) for layer_ids in selected.values()),
        "active_group_count": len(runtime_result.get("groups") or {}) or sum(1 for layer_ids in selected.values() if layer_ids),
        "combined_land_share_pct": (runtime_result.get("combined") or {}).get("land_share_pct"),
        "hex_layer_available": bool(hex_layers),
        "unfiltered_land": bool(runtime_result.get("unfiltered_land")),
    }


def _wind_preview_layers_for_map(
    energy_model_state: dict[str, Any] | None,
    preview_layers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return (
        []
        if (energy_model_state or {}).get("available")
        else list(preview_layers)
    )


def _unfiltered_wind_summary_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    target_resolution: int,
) -> pd.DataFrame:
    display_geometry_path = _h3_display_geometry_path(region, int(target_resolution))
    if not display_geometry_path:
        return pd.DataFrame()
    frame = _landscape_frame(region, landscape_manifest, int(target_resolution)).copy()
    if frame.empty:
        return pd.DataFrame()

    frame["potential_area_share_pct"] = 100.0
    frame["potential_area_share"] = 1.0
    frame["display_area_km2"] = _wind_analysis_domain_cell_area_km2_series(
        frame,
        str(region.get("region_id") or ""),
        int(target_resolution),
    )
    frame["potential_area_km2"] = frame["display_area_km2"]
    class_spec = _wind_share_class_spec(100.0)
    frame["share_class_id"] = str(class_spec["id"])
    frame["share_class_label"] = str(class_spec["label"])
    frame["share_class_index"] = WIND_SHARE_CLASS_SPECS.index(class_spec)
    frame = _wind_runtime_hex_core_scores(frame, _wind_runtime_hex_neighbor_map(display_geometry_path))
    frame["fill"] = [
        _wind_runtime_hex_color(100.0, core_value, zone_size)
        for core_value, zone_size in zip(frame["core_score"], frame["zone_size"])
    ]
    frame["core_label"] = [
        _wind_core_label(core_value, zone_size)
        for core_value, zone_size in zip(frame["core_score"], frame["zone_size"])
    ]
    frame["stroke"] = frame["fill"].map(lambda value: _mix_hex_colors(str(value), "#3a3a3a", 0.28))
    frame["wind_score"] = 100.0
    frame["wind_class"] = frame["share_class_id"].astype(str)
    frame["wind_class_label"] = frame["share_class_label"].astype(str)
    frame["wind_color"] = frame["fill"].astype(str)
    if "class_km" not in frame.columns:
        frame["class_km"] = ""
    else:
        frame["class_km"] = frame["class_km"].fillna("").astype(str)
    if "landscape_type" not in frame.columns:
        frame["landscape_type"] = ""
    else:
        frame["landscape_type"] = frame["landscape_type"].fillna("").astype(str)
    return frame.sort_values("hex_id").reset_index(drop=True)


def _wind_polygon_summary_frame(
    region: dict[str, Any],
    landscape_manifest: dict[str, Any],
    runtime_result: dict[str, Any],
    target_resolution: int,
) -> pd.DataFrame:
    if bool(runtime_result.get("unfiltered_land")):
        return _unfiltered_wind_summary_frame(region, landscape_manifest, int(target_resolution))

    frame = _wind_runtime_hex_layer_frame(region, runtime_result, int(target_resolution)).copy()
    if frame.empty:
        return pd.DataFrame(
            columns=[
                "hex_id",
                "potential_area_share_pct",
                "share_class_id",
                "share_class_label",
                "fill",
                "potential_area_km2",
                "wind_score",
                "wind_class",
                "wind_class_label",
                "wind_color",
                "core_score",
                "core_label",
                "zone_size",
                "center_mass_rank",
                "class_km",
                "landscape_type",
                "wind_hard_exclusion_intersects",
            ]
        )

    frame["display_area_km2"] = _wind_analysis_domain_cell_area_km2_series(
        frame,
        str(region.get("region_id") or ""),
        int(target_resolution),
    )
    if "potential_area_km2" not in frame.columns:
        frame["potential_area_km2"] = (
            pd.to_numeric(
                frame["potential_area_share_pct"],
                errors="coerce",
            )
            .fillna(0.0)
            .clip(lower=0.0, upper=100.0)
            .div(100.0)
            * frame["display_area_km2"]
        )
    else:
        potential_area = pd.to_numeric(
            frame["potential_area_km2"],
            errors="coerce",
        ).fillna(0.0).clip(lower=0.0)
        frame["potential_area_km2"] = pd.concat(
            [potential_area, frame["display_area_km2"]],
            axis=1,
        ).min(axis=1)
    frame["wind_score"] = frame["potential_area_share_pct"].astype(float)
    frame["wind_class"] = frame["share_class_id"].astype(str)
    frame["wind_class_label"] = frame["share_class_label"].astype(str)
    frame["wind_color"] = frame["fill"].astype(str)
    frame["core_score"] = pd.to_numeric(frame.get("core_score"), errors="coerce").fillna(0.0)
    frame["core_label"] = frame.get("core_label", "").fillna("").astype(str)
    frame["zone_size"] = pd.to_numeric(frame.get("zone_size"), errors="coerce").fillna(0).astype(int)
    frame["center_mass_rank"] = pd.to_numeric(frame.get("center_mass_rank"), errors="coerce").fillna(1).astype(int)

    landscape = _landscape_frame(region, landscape_manifest, int(target_resolution))
    context_cols = [column for column in ["hex_id", "class_km", "landscape_type"] if column in landscape.columns]
    if context_cols:
        context = landscape[context_cols].drop_duplicates(subset=["hex_id"])
        frame = frame.merge(context, on="hex_id", how="left")

    if "class_km" not in frame.columns:
        frame["class_km"] = ""
    else:
        frame["class_km"] = frame["class_km"].fillna("").astype(str)
    if "landscape_type" not in frame.columns:
        frame["landscape_type"] = ""
    else:
        frame["landscape_type"] = frame["landscape_type"].fillna("").astype(str)
    block_frame = _wind_establishment_intersection_block_frame(region, runtime_result, int(target_resolution))
    if not block_frame.empty:
        frame = frame.merge(block_frame, on="hex_id", how="left")
    if "wind_hard_exclusion_intersects" not in frame.columns:
        frame["wind_hard_exclusion_intersects"] = False
    frame["wind_hard_exclusion_intersects"] = frame["wind_hard_exclusion_intersects"].fillna(False).astype(bool)

    return frame.sort_values("hex_id").reset_index(drop=True)


def _attach_full_lablab_technology_context(
    frame: pd.DataFrame,
    region: dict[str, Any],
    landscape_manifest: dict[str, Any] | None,
    target_resolution: int,
) -> pd.DataFrame:
    """Fill optional context from the declared full LABLAB source only."""

    work = frame.copy()
    if "technology_context_status" not in work.columns:
        work["technology_context_status"] = "not_assessed"
    if "technology_context_available" not in work.columns:
        work["technology_context_available"] = False
    if not isinstance(landscape_manifest, dict):
        return work
    full_context = _technology_landscape_context_frame(
        region,
        landscape_manifest,
        int(target_resolution),
    )
    if full_context.empty:
        return work
    context_columns = [
        column
        for column in [
            "class_km",
            "class_k8",
            "landscape_type",
            "landscape_type_id",
            "landscape_type_name_sv",
            "v10_type_id",
            "v10_type_name",
            "assignment_method",
            "source_model",
        ]
        if column in full_context.columns
    ]
    if "_technology_context_observed" not in full_context.columns:
        raise ValueError(
            "Full LABLAB-källan saknar verifierad kontextstatus."
        )
    supplement = full_context[
        ["hex_id", "_technology_context_observed", *context_columns]
    ].copy()
    supplement["hex_id"] = supplement["hex_id"].astype(str)
    supplement["_full_lablab_context"] = supplement[
        "_technology_context_observed"
    ].fillna(False).astype(bool)
    supplement = supplement.drop(columns=["_technology_context_observed"])
    supplement = supplement.rename(
        columns={
            column: f"{column}__full_lablab"
            for column in context_columns
        }
    )
    work = work.merge(
        supplement,
        on="hex_id",
        how="left",
        validate="one_to_one",
    )
    has_full_context = (
        work.pop("_full_lablab_context").fillna(False).astype(bool)
    )
    for column in context_columns:
        supplement_column = f"{column}__full_lablab"
        if column not in work.columns:
            work[column] = work[supplement_column]
        else:
            missing = work[column].isna()
            if pd.api.types.is_string_dtype(work[column].dtype):
                target_values = work[column].astype("string")
                supplement_values = work[supplement_column].astype("string")
                missing = missing | target_values.fillna("").str.strip().eq("")
                work[column] = target_values.mask(
                    missing,
                    supplement_values,
                )
            else:
                work[column] = work[column].where(
                    ~missing,
                    work[supplement_column],
                )
        work = work.drop(columns=[supplement_column])
    app_extent = work["technology_context_status"].eq("app_extent")
    full_only = ~app_extent & has_full_context
    work.loc[full_only, "technology_context_status"] = "full_lablab"
    work["technology_context_available"] = app_extent | has_full_context
    return work


def _technology_context_review(
    frame: pd.DataFrame,
) -> dict[str, Any]:
    if (
        frame.empty
        or "technology_context_status" not in frame.columns
        or "display_area_km2" not in frame.columns
    ):
        return {}
    status = frame["technology_context_status"].fillna(
        "not_assessed"
    ).astype(str)
    areas = pd.to_numeric(
        frame["display_area_km2"],
        errors="coerce",
    ).fillna(0.0)
    return {
        "total_cell_count": int(len(frame)),
        "app_extent_cell_count": int(status.eq("app_extent").sum()),
        "full_lablab_cell_count": int(status.eq("full_lablab").sum()),
        "not_assessed_cell_count": int(status.eq("not_assessed").sum()),
        "not_assessed_area_km2": float(
            areas.loc[status.eq("not_assessed")].sum()
        ),
    }


def _exact_wind_area_summary_frame(
    region: dict[str, Any],
    proxy_frame: pd.DataFrame,
    exact_area_frame: pd.DataFrame,
    target_resolution: int,
    landscape_manifest: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Keep contextual ranking fields but replace proxy area with exact area."""

    area_columns = [
        "display_area_km2",
        "potential_area_km2",
        "potential_area_share_pct",
        "potential_area_share",
    ]
    frame = merge_exact_area_with_optional_context(
        exact_area_frame,
        proxy_frame,
        replaced_area_columns=area_columns,
    )
    frame = _attach_full_lablab_technology_context(
        frame,
        region,
        landscape_manifest,
        int(target_resolution),
    )
    display_geometry_path = _area_display_geometry_path(
        region,
        int(target_resolution),
    )
    if not display_geometry_path:
        raise ValueError("Exact wind area result has no display geometry")
    frame = _finalize_fast_wind_share_frame(
        frame,
        display_geometry_path,
        str(region.get("region_id") or ""),
        int(target_resolution),
        compute_core=False,
        area_scope="technology_support",
    )
    frame["wind_score"] = frame["potential_area_share_pct"].astype(float)
    frame["wind_class"] = frame["share_class_id"].astype(str)
    frame["wind_class_label"] = frame["share_class_label"].astype(str)
    frame["wind_color"] = frame["fill"].astype(str)
    return frame.sort_values("hex_id").reset_index(drop=True)


def _exact_solar_area_summary_frame(
    region: dict[str, Any],
    proxy_frame: pd.DataFrame,
    exact_area_frame: pd.DataFrame,
    target_resolution: int,
    landscape_manifest: dict[str, Any] | None = None,
) -> pd.DataFrame:
    """Keep solar context while replacing every public area value."""

    area_columns = [
        "display_area_km2",
        "potential_area_m2",
        "potential_area_km2",
        "potential_area_share_pct",
    ]
    frame = merge_exact_area_with_optional_context(
        exact_area_frame,
        proxy_frame,
        replaced_area_columns=area_columns,
    )
    frame = _attach_full_lablab_technology_context(
        frame,
        region,
        landscape_manifest,
        int(target_resolution),
    )
    frame["potential_area_m2"] = (
        frame["potential_area_km2"].astype(float) * 1_000_000.0
    )
    frame["solar_score"] = frame["potential_area_share_pct"].astype(float)
    classes = [
        _solar_score_class(float(value))
        for value in frame["solar_score"]
    ]
    frame["solar_class"] = [item["id"] for item in classes]
    frame["solar_class_label"] = [item["label"] for item in classes]
    frame["solar_color"] = [item["color"] for item in classes]
    display_geometry_path = _area_display_geometry_path(
        region,
        int(target_resolution),
    )
    if not display_geometry_path:
        raise ValueError("Exact solar area result has no display geometry")
    return _filter_frame_to_display_geometries(
        frame.sort_values("hex_id").reset_index(drop=True),
        display_geometry_path,
    )


def _wind_source_status_frame() -> pd.DataFrame:
    groups, _, registry_meta = load_acceptance_registry()
    status_df = acceptance_layer_status_table(registry_meta).copy()
    if status_df.empty:
        return status_df

    status_df["group_id"] = status_df["group"].map(
        lambda label: next((group_id for group_id, spec in groups.items() if spec.label == label), label)
    )
    status_df["regelgrupp"] = status_df["group_id"].map(lambda value: GROUP_LABELS.get(str(value), str(value)))
    status_df["klar"] = (
        status_df["geojson_ready"].astype(bool)
        & status_df["source_exists"].astype(bool)
        & status_df["status"].astype(str).eq("ok")
    )
    output = status_df[
        ["regelgrupp", "label", "geometry_family", "feature_count", "status", "klar", "message"]
    ].rename(
        columns={
            "label": "källager",
            "geometry_family": "geometri",
            "feature_count": "objekt",
            "status": "status",
            "message": "notering",
        }
    )
    return output.sort_values(["regelgrupp", "källager"], ascending=[True, True]).reset_index(drop=True)


def _render_establishment_focus(energy_model_state: dict[str, Any], geography_renderer: Any | None = None) -> None:
    def _render_establishment_heading() -> None:
        st.subheader(_t("Vind/sol och landskapspåverkan"))

    if not energy_model_state.get("available"):
        _render_establishment_heading()
        st.caption(_t("Etableringsytan visas när energimodelleringen är aktiv."))
        return
    if not bool(energy_model_state.get("establishment_layer_visible", False)):
        _render_establishment_heading()
        st.caption(_t("Etableringsytan visas när vind- och/eller solpotential finns aktiv i kartan."))
        return

    if not isinstance(energy_model_state.get("combined_establishment_stats"), dict):
        _render_establishment_heading()
        st.caption(_t("Etableringsytan beräknas när vind- och/eller solpotential finns aktiv i kartan."))
        return

    proposal_stats = energy_model_state.get("proposal_stats") if isinstance(energy_model_state, dict) else None
    solar_stats = energy_model_state.get("solar_proposal_stats") if isinstance(energy_model_state, dict) else None
    solar_v1_stats = energy_model_state.get("solar_v1_stats") if isinstance(energy_model_state, dict) else None
    proposal_stats = proposal_stats if isinstance(proposal_stats, dict) else {}
    solar_stats = solar_stats if isinstance(solar_stats, dict) else {}
    social_summary = energy_model_state.get("social_acceptance_summary")
    result_presentation = parse_result_presentation(
        energy_model_state.get("result_presentation")
    )
    wind_result = result_technology(result_presentation, "wind")
    solar_result = result_technology(result_presentation, "solar")
    total_result = result_presentation.total

    capacity_based = bool(energy_model_state.get("capacity_based"))
    wind_need = wind_result.need_area_km2
    solar_need = solar_result.need_area_km2
    total_need = total_result.need_area_km2
    wind_available_area = wind_result.filtered_potential_area_km2
    solar_available_area = solar_result.filtered_potential_area_km2
    total_available_area = total_result.filtered_potential_area_km2
    wind_after_acceptance_area = wind_result.potential_after_acceptance_km2
    solar_after_acceptance_area = solar_result.potential_after_acceptance_km2
    total_after_acceptance_area = total_result.potential_after_acceptance_km2
    wind_inside = wind_result.inside_potential_km2
    solar_inside = solar_result.inside_potential_km2
    inside_total = total_result.inside_potential_km2
    wind_outside_need = wind_result.outside_need_km2
    solar_outside_need = solar_result.outside_need_km2
    outside_total = total_result.outside_need_km2
    wind_unused_potential = wind_result.unused_potential_km2
    solar_unused_potential = solar_result.unused_potential_km2
    total_unused_potential = total_result.unused_potential_km2
    total_covered = inside_total
    covered_share = total_result.coverage_pct
    wind_coverage_pct = wind_result.coverage_pct
    solar_coverage_pct = solar_result.coverage_pct
    hex_area = float(energy_model_state.get("hex_area_km2", 0.0) or 0.0)
    h3_resolution = energy_model_state.get("h3_resolution")
    try:
        h3_resolution = int(h3_resolution)
    except Exception:
        h3_resolution = None
    display_h3_resolution = energy_model_state.get("display_h3_resolution")
    try:
        display_h3_resolution = int(display_h3_resolution)
    except Exception:
        display_h3_resolution = h3_resolution

    quantity_unit = "MW" if capacity_based else "TWh"
    quantity_key = "mw" if capacity_based else "twh"
    wind_quantity = (
        float(energy_model_state["capacity_mw"]["wind"])
        if capacity_based else wind_result.energy_twh
    )
    solar_quantity = (
        float(energy_model_state["capacity_mw"]["solar"])
        if capacity_based else solar_result.energy_twh
    )
    total_quantity = (
        math.fsum((wind_quantity, solar_quantity))
        if capacity_based else total_result.energy_twh
    )
    solar_ground_twh = energy_model_state.get("solar_ground_twh", solar_result.energy_twh)
    solar_rooftop_twh = float(
        energy_model_state.get("solar_rooftop_twh", 0.0) or 0.0
    )
    rooftop_solar = energy_model_state.get("rooftop_solar")
    rooftop_solar = rooftop_solar if isinstance(rooftop_solar, dict) else {}
    wind_share_pct = float(energy_model_state.get("wind_share_pct", 0.0) or 0.0)
    solar_share_pct = float(energy_model_state.get("solar_share_pct", 0.0) or 0.0)
    snapshot_key = _establishment_change_snapshot_key(energy_model_state)
    current_snapshot = {
        "total_covered_area_km2": total_covered,
        "total_need_area_km2": total_need,
        "inside_total_km2": inside_total,
        "outside_total_km2": outside_total,
        f"wind_{quantity_key}": wind_quantity,
        f"solar_{quantity_key}": solar_quantity,
        f"total_{quantity_key}": total_quantity,
        "wind_need_km2": wind_need,
        "solar_need_km2": solar_need,
        "wind_available_km2": wind_available_area,
        "solar_available_km2": solar_available_area,
        "total_available_km2": total_available_area,
        "wind_inside_km2": wind_inside,
        "solar_inside_km2": solar_inside,
        "wind_unused_potential_km2": wind_unused_potential,
        "solar_unused_potential_km2": solar_unused_potential,
        "total_unused_potential_km2": total_unused_potential,
        "wind_outside_km2": wind_outside_need,
        "solar_outside_km2": solar_outside_need,
        "wind_coverage_pct": wind_coverage_pct,
        "solar_coverage_pct": solar_coverage_pct,
        "total_coverage_pct": covered_share,
    }
    if not capacity_based:
        current_snapshot.update(
            solar_ground_twh=solar_ground_twh,
            solar_rooftop_twh=solar_rooftop_twh,
        )
    current_fingerprint = _snapshot_fingerprint(current_snapshot)
    snapshot_state_raw = st.session_state.get(snapshot_key)
    snapshot_state = snapshot_state_raw if isinstance(snapshot_state_raw, dict) else {}
    stored_current = snapshot_state.get("current") if isinstance(snapshot_state.get("current"), dict) else {}
    stored_previous = snapshot_state.get("previous") if isinstance(snapshot_state.get("previous"), dict) else {}
    if stored_current and snapshot_state.get("fingerprint") != current_fingerprint:
        previous_snapshot = stored_current
    else:
        previous_snapshot = stored_previous
    scenario_label = str(energy_model_state.get("scenario_label", energy_model_state.get("scenario", "-")) or "-")
    if not capacity_based or scenario_label == "Egen kapacitet":
        scenario_label = _t(_model_level_source(scenario_label))
    source_label = str(energy_model_state.get("source_scenario_label", "-") or "-")
    source_year = str(energy_model_state.get("source_year", "-") or "-")
    energy_scale = float(energy_model_state.get("energy_scale", 1.0) or 1.0)
    st.session_state.setdefault("establishment_area_display_unit", "km²")
    unit = str(st.session_state.get("establishment_area_display_unit", "km²") or "km²")
    if unit not in AREA_DISPLAY_UNITS:
        unit = "km²"
        st.session_state["establishment_area_display_unit"] = unit
    outside_summary_sentence = (
        (_t('{p0} behöver hanteras utanför potentialområdet.', p0=_format_area_primary(outside_total, unit, hex_area)) if outside_total > 1e-6 else _t('Ingen yta behöver lösas utanför potentialområdet.'))
    )
    quantity_summary = (
        (_t('Scenariot omfattar {p0:.2f} MW installerad effekt', p0=total_quantity) if capacity_based else _t('Scenariot motsvarar {p0:.2f} TWh', p0=total_quantity))
    )
    energy_total_summary_text = (
        _t('{p0} och ger ett teknikspecifikt ytanspråk på {p1}. Efter geografiska filter finns {p2} möjlig etableringsyta som tekniksumma (vindpotential + solpotential). Det är alltså inte unik fysisk markyta: samma hex kan räknas en gång för vind och en gång för sol när teknikerna kan samnyttja ytan. Efter eventuell social acceptanspåverkan är motsvarande tekniksumma {p3}. Av ytanspråket placeras {p4} inom potentialområdet, vilket motsvarar {p5:.1f}% av behovet. {p6} När scenariot är placerat återstår {p7} outnyttjad teknikpotential.', p0=quantity_summary, p1=_format_area_primary(total_need, unit, hex_area), p2=_format_area_primary(total_available_area, unit, hex_area), p3=_format_area_primary(total_after_acceptance_area, unit, hex_area), p4=_format_area_primary(inside_total, unit, hex_area), p5=covered_share, p6=outside_summary_sentence, p7=_format_area_primary(total_unused_potential, unit, hex_area))
    )
    if not capacity_based and solar_rooftop_twh > 0.0:
        energy_total_summary_text += (
            _t(' Av solmålets {p0:.2f} TWh bokförs {p1:.2f} TWh som manifeststyrd taksolschablon och {p2:.2f} TWh återstår för marksol.', p0=solar_quantity, p1=solar_rooftop_twh, p2=solar_ground_twh)
        )

    impact_rows = [
        {
            "teknik": "Vind",
            "energi": _value_with_change_html(f"{wind_quantity:.2f} {quantity_unit}", wind_quantity, _previous_snapshot_value(previous_snapshot, f"wind_{quantity_key}")),
            "ytbehov": _value_with_change_html(_format_area_primary(wind_need, unit, hex_area), wind_need, _previous_snapshot_value(previous_snapshot, "wind_need_km2")),
            "potential efter filter": _value_with_change_html(
                _format_area_primary(wind_available_area, unit, hex_area),
                wind_available_area,
                _previous_snapshot_value(previous_snapshot, "wind_available_km2"),
            ),
            "potential efter acceptanspåverkan": _value_with_change_html(
                _format_area_primary(wind_after_acceptance_area, unit, hex_area),
                wind_after_acceptance_area,
                wind_available_area,
            ),
            "inom potential": _value_with_change_html(_format_area_primary(wind_inside, unit, hex_area), wind_inside, _previous_snapshot_value(previous_snapshot, "wind_inside_km2")),
            "outnyttjad potential": _value_with_change_html(
                _format_area_primary(wind_unused_potential, unit, hex_area),
                wind_unused_potential,
                _previous_snapshot_value(previous_snapshot, "wind_unused_potential_km2"),
            ),
            "ytbehov utanför potential": _value_with_change_html(
                _format_area_primary(wind_outside_need, unit, hex_area),
                wind_outside_need,
                _previous_snapshot_value(previous_snapshot, "wind_outside_km2"),
            ),
            "andel inom potential": _value_with_change_html(f"{wind_coverage_pct:.1f}%", wind_coverage_pct, _previous_snapshot_value(previous_snapshot, "wind_coverage_pct")),
        },
        {
            "teknik": "Sol",
            "energi": _value_with_change_html(f"{solar_quantity:.2f} {quantity_unit}", solar_quantity, _previous_snapshot_value(previous_snapshot, f"solar_{quantity_key}")),
            "ytbehov": _value_with_change_html(_format_area_primary(solar_need, unit, hex_area), solar_need, _previous_snapshot_value(previous_snapshot, "solar_need_km2")),
            "potential efter filter": _value_with_change_html(
                _format_area_primary(solar_available_area, unit, hex_area),
                solar_available_area,
                _previous_snapshot_value(previous_snapshot, "solar_available_km2"),
            ),
            "potential efter acceptanspåverkan": _value_with_change_html(
                _format_area_primary(solar_after_acceptance_area, unit, hex_area),
                solar_after_acceptance_area,
                solar_available_area,
            ),
            "inom potential": _value_with_change_html(_format_area_primary(solar_inside, unit, hex_area), solar_inside, _previous_snapshot_value(previous_snapshot, "solar_inside_km2")),
            "outnyttjad potential": _value_with_change_html(
                _format_area_primary(solar_unused_potential, unit, hex_area),
                solar_unused_potential,
                _previous_snapshot_value(previous_snapshot, "solar_unused_potential_km2"),
            ),
            "ytbehov utanför potential": _value_with_change_html(
                _format_area_primary(solar_outside_need, unit, hex_area),
                solar_outside_need,
                _previous_snapshot_value(previous_snapshot, "solar_outside_km2"),
            ),
            "andel inom potential": _value_with_change_html(f"{solar_coverage_pct:.1f}%", solar_coverage_pct, _previous_snapshot_value(previous_snapshot, "solar_coverage_pct")),
        },
        {
            "teknik": "Totalt",
            "energi": _value_with_change_html(f"{total_quantity:.2f} {quantity_unit}", total_quantity, _previous_snapshot_value(previous_snapshot, f"total_{quantity_key}")),
            "ytbehov": _value_with_change_html(_format_area_primary(total_need, unit, hex_area), total_need, _previous_snapshot_value(previous_snapshot, "total_need_area_km2")),
            "potential efter filter": _value_with_change_html(
                _format_area_primary(total_available_area, unit, hex_area),
                total_available_area,
                _previous_snapshot_value(previous_snapshot, "total_available_km2"),
            ),
            "potential efter acceptanspåverkan": _value_with_change_html(
                _format_area_primary(total_after_acceptance_area, unit, hex_area),
                total_after_acceptance_area,
                total_available_area,
            ),
            "inom potential": _value_with_change_html(_format_area_primary(inside_total, unit, hex_area), inside_total, _previous_snapshot_value(previous_snapshot, "inside_total_km2")),
            "outnyttjad potential": _value_with_change_html(
                _format_area_primary(total_unused_potential, unit, hex_area),
                total_unused_potential,
                _previous_snapshot_value(previous_snapshot, "total_unused_potential_km2"),
            ),
            "ytbehov utanför potential": _value_with_change_html(
                _format_area_primary(outside_total, unit, hex_area),
                outside_total,
                _previous_snapshot_value(previous_snapshot, "outside_total_km2"),
            ),
            "andel inom potential": _value_with_change_html(f"{covered_share:.1f}%", covered_share, _previous_snapshot_value(previous_snapshot, "total_coverage_pct")),
        },
    ]
    _render_establishment_heading()
    st.caption(
        _t("Tabellen visar hur mycket teknikspecifik yta scenariot kräver, hur mycket möjlig teknikpotential som finns efter filter, och om något behöver lösas utanför potentialen.")
    )
    if capacity_based:
        st.caption(f"{scenario_label} · {energy_model_state['source_scenario']}")
        st.caption(source_warning(
            parse_scenario_result(energy_model_state["scenario_result"]),
            _language(),
        ))
        st.caption(
            _t("Preliminära värden från energimodelleringen. Befintlig kapacitet ingår i modellscenariot. "
            "MW visar installerad effekt; årsproduktion saknas. Solvärdena avser marksol, utan taksolsavdrag.")
        )
        st.caption(_t("Schematisk jämförelse av scenariots totala ytbehov med landskapets potential. Visar inte föreslagna etableringar."))
    elif rooftop_solar:
        st.caption(
            _t("Solradens energi är hela solmålet. Solradens ytbehov är endast "
            "det kvarvarande markbehovet efter aktiv taksolschablon; taksol "
            "ändrar inte kartans geografiska solpotential.")
        )
    _render_impact_change_table(
        impact_rows, quantity_label="kapacitet" if capacity_based else "energi",
    )

    if result_presentation.fit_status == "shortage":
        st.warning(
            _t('Vald mix ryms inte helt inom landskapets potential. {p0} behöver lösas utanför landskapets potential.', p0=_format_area_with_context(outside_total, unit, hex_area))
        )
    elif result_presentation.fit_status == "within_potential":
        st.success(_t("Vald mix ryms inom landskapets potential med nuvarande urval."))

    st.caption(
        " · ".join(
            [
                _t("Ryms: {p0:.1f}%", p0=covered_share),
                _t("Inom potential: {p0}", p0=_format_area_with_context(inside_total, unit, hex_area)),
                _t("Utanför potential: {p0}", p0=_format_area_with_context(outside_total, unit, hex_area)),
            ]
        )
    )
    with st.expander(_t("Så läses tabellen"), expanded=False):
        st.caption(
            _t("Tabellen jämför scenariots teknikspecifika ytbehov med möjlig yta efter aktiva filter. Totalraden summerar vind och sol och kan därför vara större än den unika fysiska markytan.")
        )
        st.caption(
            _t('En grön potentialhex kan bära både vind- och solscenarioyta. Mörkgrön scenariomarkör betyder att båda finns i samma visningshex; exakt fysisk överlappning beräknas inte.')
        )
        st.caption(_t("Pilarna visar förändring sedan föregående beräknade läge."))

    if callable(geography_renderer):
        geography_renderer()

    st.subheader(_t("Energimodellering"))
    st.markdown(f"**{_t('Sammanfattning')}**")
    st.markdown(_t(energy_total_summary_text))

    if isinstance(social_summary, dict) and social_summary:
        st.subheader(_t("Social acceptans"))
        social_scenario_label = _t(_model_level_source(social_summary.get("scenario_label", social_summary.get("scenario_id", "-")) or "-"))
        impact_pct = float(social_summary.get("impact_pct", 0.0) or 0.0)
        assessed_hex_count = int(
            social_summary.get(
                "assessed_hex_count",
                social_summary.get("measured_hex_count", 0),
            )
            or 0
        )
        potential_hex_count = int(social_summary.get("potential_hex_count", 0) or 0)
        st.caption(
            _t('Scenario: {p0}. Beräknas på {p1:,} av {p2:,} potentiella etableringshex.', p0=social_scenario_label, p1=assessed_hex_count, p2=potential_hex_count)
            .replace(",", " ")
        )
        source_status = str(social_summary.get("source_status", "") or "")
        social_source_label = str(social_summary.get("source_label", "") or "")
        source_synthetic = bool(social_summary.get("source_synthetic", False))
        regional_acceptance = bool(
            social_summary.get("regional_acceptance", False)
        )
        source_notice = (
            _t('Datakälla: {p0} · status {p1} · syntetisk: {p2} · regionalt accepterad: {p3}.', p0=social_source_label or 'okänd', p1=source_status or 'okänd', p2=_t('ja') if source_synthetic else _t('nej'), p3=_t('ja') if regional_acceptance else _t('nej'))
        )
        allocation_priority_pct = float(energy_model_state.get("social_acceptance_allocation_priority_pct", 0.0) or 0.0)
        if source_status == "provisional_fallback" and (
            impact_pct > 0.0 or allocation_priority_pct > 0.0
        ):
            st.badge(
                _t("Provisorisk datakälla"),
                color="orange",
                icon=":material/warning:",
            )
        st.caption(_t(source_notice))
        metric_cols = st.columns(3)
        mean_acceptance = pd.to_numeric(
            social_summary.get("mean_acceptance"),
            errors="coerce",
        )
        median_acceptance = pd.to_numeric(
            social_summary.get("median_acceptance"),
            errors="coerce",
        )
        metric_cols[0].metric(
            _t("Medelacceptans"),
            f"{float(mean_acceptance):.2f}"
            if pd.notna(mean_acceptance)
            else "–",
        )
        metric_cols[1].metric(
            _t("Medianacceptans"),
            f"{float(median_acceptance):.2f}"
            if pd.notna(median_acceptance)
            else "–",
        )
        metric_cols[2].metric(_t("Acceptanspåverkan"), f"{impact_pct:.0f}%")
        if allocation_priority_pct > 0.0:
            st.caption(
                _t('Scenarioytan inom potentialen prioriteras med {p0:.0f}% social acceptansstyrning.', p0=allocation_priority_pct)
            )
        low_threshold = float(social_summary["low_threshold"])
        high_threshold = float(social_summary["high_threshold"])
        acceptance_rows = [
            {
                "klass": f"Låg < {low_threshold:.1f}",
                "yta": _format_area_primary(float(social_summary.get("low_acceptance_area_km2", 0.0) or 0.0), unit, hex_area),
                "andel": f"{float(social_summary.get('low_acceptance_share_pct', 0.0) or 0.0):.1f}%",
                "hex": _count_text(int(social_summary.get("low_acceptance_hex_count", 0) or 0)),
            },
            {
                "klass": f"Hög ≥ {high_threshold:.1f}",
                "yta": _format_area_primary(float(social_summary.get("high_acceptance_area_km2", 0.0) or 0.0), unit, hex_area),
                "andel": f"{float(social_summary.get('high_acceptance_share_pct', 0.0) or 0.0):.1f}%",
                "hex": _count_text(int(social_summary.get("high_acceptance_hex_count", 0) or 0)),
            },
        ]
        st.dataframe(_display_dataframe(pd.DataFrame(acceptance_rows)), width="stretch", hide_index=True, height=124)
        unknown_hex_count = int(
            social_summary.get(
                "unknown_hex_count",
                social_summary.get("missing_hex_count", 0),
            )
            or 0
        )
        if unknown_hex_count > 0:
            unknown_area_km2 = float(
                social_summary.get("unknown_potential_area_km2", 0.0)
                or 0.0
            )
            unknown_effect = (
                (_t('bidrar med noll till den acceptansjusterade potentialen') if impact_pct > 0.0 else _t('behåller sin potential eftersom acceptanspåverkan är 0%'))
            )
            st.caption(
                (
                    _t('Acceptansdata saknas för {p0:,} potentiella hex ({p1:.3f} km²). De förblir okända och {p2}.', p0=unknown_hex_count, p1=unknown_area_km2, p2=unknown_effect)
                ).replace(",", " ")
            )

    with st.expander(_t("Avancerade inställningar"), expanded=False):
        _render_right_panel_width_control(st)
        st.radio(
            _t("Enhet"),
            options=AREA_DISPLAY_UNITS,
            index=AREA_DISPLAY_UNITS.index(unit),
            horizontal=True,
            key="establishment_area_display_unit",
            on_change=_request_ui_only_rerun,
            args=("area_unit",),
            persist_state="session",
        )
        st.caption(_t("Byte av enhet ändrar bara hur ytor visas i panelen, inte modellresultatet."))
        st.caption(
            _t("Panelen visar om vald mix av vind och sol ryms i de landskap som modellen bedömer som möjliga efter aktiva filter. "
            "Kartan färgsätter platser som möjliga för vind, sol, båda teknikerna eller ingen av dem.")
        )
        if capacity_based and energy_model_state["scenario_request"].get("capacity_mw_by_technology") is not None:
            st.caption(_t("Vald kapacitet · {p0:g} MW vind / {p1:g} MW marksol · källa {p2}",
                          p0=wind_quantity, p1=solar_quantity, p2=source_label))
        elif capacity_based:
            st.caption(
                _t('Preliminära kapaciteter · {p0} · mix {p1:.1f}% vind / {p2:.1f}% sol av total MW · källa {p3}', p0=scenario_label, p1=wind_share_pct, p2=solar_share_pct, p3=source_label)
            )
        else:
            st.caption(
                _t('Dummy/prototypdata · {p0}: {p1:g}x energi · markintensitet {p2} · mix {p3:.0f}% vind / {p4:.0f}% sol · källa {p5} {p6}', p0=scenario_label, p1=energy_scale, p2=_t(_model_level_source(energy_model_state.get('area_scenario_label', '-'))), p3=wind_share_pct, p4=solar_share_pct, p5=source_label, p6=source_year)
            )
        st.caption(
            _t("Ytorna summeras från cellernas deklarerade etableringsyta efter filter. "
            "Hav ingår inte. Hexmarkörer är en schematisk visning av dessa ytor.")
        )
        if display_h3_resolution is not None and h3_resolution is not None and display_h3_resolution != h3_resolution:
            st.caption(
                _t('Kartan visas som R{p0}. Ytbalans, täckning och scenarioallokering beräknas i R{p1}.', p0=display_h3_resolution, p1=h3_resolution)
            )
        with st.expander(_t("Hexdetaljer och kartmarkörer"), expanded=False):
            st.caption(_t("Tekniska kartmått för granskning av hexmarkörer och färgklasser."))
            st.caption(_t("Globalt H3-medel") + ": " + _format_hex_size_caption(h3_resolution, hex_area))
            hex_stats = energy_model_state.get("establishment_hex_stats")
            if isinstance(hex_stats, dict):
                total_hex = int(hex_stats.get("total_hex_count", 0) or 0)
                black_hex = int(hex_stats.get("black_hex_count", 0) or 0)
                red_hex = int(hex_stats.get("red_hex_count", 0) or 0)
                wind_only_hex = int(hex_stats.get("wind_only_hex_count", 0) or 0)
                solar_only_hex = int(hex_stats.get("solar_only_hex_count", 0) or 0)
                wind_and_solar_hex = int(hex_stats.get("wind_and_solar_hex_count", 0) or 0)
                hex_rows = [
                    {
                        "kategori": f"Totalt antal R{h3_resolution}-hex" if h3_resolution is not None else "Totalt antal H3-hex",
                        "antal hex": _count_text(total_hex),
                        "motsvarar": _format_area_with_context(total_hex * hex_area, unit, hex_area),
                    },
                    {
                        "kategori": "Schematiska ytbudgethex",
                        "antal hex": _count_text(black_hex),
                        "motsvarar": f"{_format_area_with_context(outside_total, unit, hex_area)} ytbehov",
                    },
                    {
                        "kategori": "Röda hex i etableringslagret",
                        "antal hex": _count_text(red_hex),
                        "motsvarar": _format_area_with_context(red_hex * hex_area, unit, hex_area),
                    },
                    {
                        "kategori": "Potentialhex: endast vind",
                        "antal hex": _count_text(wind_only_hex),
                        "motsvarar": "synlig potentialklass",
                    },
                    {
                        "kategori": "Potentialhex: endast sol",
                        "antal hex": _count_text(solar_only_hex),
                        "motsvarar": "synlig potentialklass",
                    },
                    {
                        "kategori": "Potentialhex: vind och sol",
                        "antal hex": _count_text(wind_and_solar_hex),
                        "motsvarar": "synlig potentialklass",
                    },
                ]
                st.dataframe(_display_dataframe(pd.DataFrame(hex_rows)), width="stretch", hide_index=True, height=246)
                st.caption(
                    _t('Ytbudgethex visar extra ytbehov i separata schematiska fält utanför regionen. Potentiallagret är blått för vind, gult för sol och grönt för vind och sol. Scenariomarkören är blå för vind, gulorange för sol och mörkgrön när båda har yta i samma visningshex; det betyder inte exakt fysisk överlappning.')
                )
            else:
                st.caption(_t("Hexstatistik saknas för denna vy."))

            shortage_stats = energy_model_state.get("outside_lp_shortage_stats")
            if isinstance(shortage_stats, dict) and outside_total > 1e-6:
                _render_shortage_hex_stack_card(shortage_stats, unit)

        with st.expander(_t("Urval och ytdetaljer"), expanded=False):
            if not capacity_based and isinstance(solar_v1_stats, dict):
                small_cols = st.columns(3)
                small_cols[0].metric(
                    _t("Taksolel"),
                    f"{float(solar_v1_stats.get('covered_twh', 0.0) or 0.0):.2f} TWh",
                )
                small_cols[1].metric(
                    _t("Andel av solmålet"),
                    f"{float(solar_v1_stats.get('covered_share_pct', 0.0) or 0.0):.1f}%",
                )
                small_cols[2].metric(
                    _t("Markbehov efter tak"),
                    f"{float(solar_v1_stats.get('remaining_area_km2', 0.0) or 0.0):.2f} km²",
                )
                st.caption(
                    (
                        _t('Planeringsproxy: {p0:,.0f} personer i källtotalen, {p1:.0f} m² panelyta/person och {p2:.1f} kWh/m²/år.', p0=float(solar_v1_stats.get('population', 0.0) or 0.0), p1=float(rooftop_solar.get('panel_area_m2_per_person', 0.0) or 0.0), p2=float(rooftop_solar.get('annual_yield_kwh_per_m2', 0.0) or 0.0))
                    ).replace(",", " ")
                )
            if proposal_stats:
                selected_twh = float(proposal_stats.get("selected_twh", 0.0) or 0.0)
                if selected_twh > 0:
                    st.metric(_t("Fördelad vindproduktion"), f"{selected_twh:.2f} TWh")
                needed_hex = int(proposal_stats.get("needed_hex", 0) or 0)
                selected_count = int(proposal_stats.get("selected_hex_count", 0) or 0)
                if selected_count <= 0:
                    selected_count = len(energy_model_state.get("proposal_frame", pd.DataFrame()))
                detail_cols = st.columns(3)
                detail_cols[0].metric(_t("Globalt H3-medel"), f"{hex_area:.4f} km²")
                detail_cols[1].metric(_t("Hela hex behövs"), f"{needed_hex:,}".replace(",", " "))
                detail_cols[2].metric(_t("Valda vindhex"), f"{selected_count:,}".replace(",", " "))
                available_hex = int(proposal_stats.get("available_candidate_hex", 0) or 0)
                available_area = float(proposal_stats.get("available_candidate_area_km2", 0.0) or 0.0)
                primary_candidates = int(proposal_stats.get("primary_candidate_hex", 0) or 0)
                extension_candidates = int(proposal_stats.get("extension_candidate_hex", 0) or 0)
                selected_primary = int(proposal_stats.get("selected_primary_hex", 0) or 0)
                selected_extension = int(proposal_stats.get("selected_extension_hex", 0) or 0)
                min_share = float(proposal_stats.get("min_share_pct", energy_model_state.get("auto_min_potential_share_pct", 65.0)) or 65.0)
                mean_share = float(proposal_stats.get("mean_selected_share_pct", 0.0) or 0.0)
                selected_potential_area = float(proposal_stats.get("selected_potential_area_km2", 0.0) or 0.0)
                selected_hex_footprint = float(proposal_stats.get("selected_hex_footprint_km2", 0.0) or 0.0)
                st.caption(
                    _t('Vindurvalet innehåller {p0:.2f} km² potentiell yta inom {p1:.2f} km² hexavtryck. Valbara LP-hex: {p2:,} med {p3:.2f} km² potentiell yta; medelandel i urvalet {p4:.1f}%.', p0=selected_potential_area, p1=selected_hex_footprint, p2=available_hex, p3=available_area, p4=mean_share).replace(",", " ")
                )
                st.caption(
                    _t('Urvalsordning: först kärn-LP med LP ≥ {p0:.0f}% ({p1:,}/{p2:,} valda), sedan kompletterande LP ({p3:,}/{p4:,} valda).', p0=min_share, p1=selected_primary, p2=primary_candidates, p3=selected_extension, p4=extension_candidates).replace(",", " ")
                )
                if selected_count > needed_hex:
                    st.caption(_t("Area-share gör att fler hex behövs än den teoretiska jämförelsen med helt fyllda hex."))
                if wind_outside_need > 1e-6:
                    st.warning(
                        _t("Vindbehovet ryms inte helt inom landskapets potential. Planeringsval behövs: sänk potentialkrav, "
                        "släpp in kantzoner, ändra restriktioner, välj ett lägre framtidsscenario eller minska ytbehovet.")
                    )
            warning_table = energy_model_state.get("area_warnings")
            if isinstance(warning_table, pd.DataFrame) and not warning_table.empty:
                st.caption(_t("AreaDemand har datakvalitetsvarningar. Se Energimodellering-panelen för detaljer."))
            st.caption(
                _t('{p0} visar vind och sol tillsammans. {p1} visar den extra etableringsyta som krävs när scenariot inte ryms.', p0=COMBINED_ESTABLISHMENT_LAYER_LABEL, p1=OUTSIDE_LP_NEED_LAYER_LABEL)
            )
    if stored_current and snapshot_state.get("fingerprint") != current_fingerprint:
        snapshot_previous = stored_current
    else:
        snapshot_previous = previous_snapshot
    st.session_state[snapshot_key] = {
        "previous": snapshot_previous,
        "current": current_snapshot,
        "fingerprint": current_fingerprint,
    }


def _render_performance_log(performance_log: list[dict[str, Any]]) -> None:
    if not performance_log:
        return
    with st.expander(_t("Prestanda"), expanded=False):
        total_seconds = sum(float(row.get("tid_s", 0.0) or 0.0) for row in performance_log)
        slowest = max(performance_log, key=lambda row: float(row.get("tid_s", 0.0) or 0.0))
        st.caption(
            _t("Tidslogg för den senaste körningen. Den mäter Python- och HTML-byggsteg; webbläsarens egen ritning kan tillkomma.")
        )
        frame = pd.DataFrame(performance_log)
        frame["tid"] = frame["tid_s"].map(lambda value: f"{float(value):.2f} s")
        st.dataframe(_display_dataframe(frame[["steg", "tid", "detalj"]]), width="stretch", hide_index=True, height=min(360, 72 + 34 * len(frame)))
        st.caption(_t('Summa mätta steg: {p0:.2f} s. Långsammast: {p1} ({p2:.2f} s).', p0=total_seconds, p1=_t(slowest.get('steg', '-')), p2=float(slowest.get('tid_s', 0.0) or 0.0)))


def _render_wind_preview_diagnostics(value: Any) -> None:
    if not isinstance(value, Mapping):
        return
    active_source_count = int(value.get("active_source_count", 0) or 0)
    active_group_count = int(value.get("active_group_count", 0) or 0)
    combined_share = value.get("combined_land_share_pct")
    left_metric, right_metric = st.columns(2)
    left_metric.metric(_t("Vind: aktiva källager"), active_source_count)
    right_metric.metric(_t("Vind: buffertgrupper"), active_group_count)
    st.metric(
        _t("Vind: genomsnittlig potential per analyscell"),
        "-" if combined_share is None else f"{float(combined_share):.1f}%",
    )


def _workspace_map_note(energy_model_state: dict[str, Any], layer_control_count: int) -> str:
    """Build current-language prose from the same immutable numerical facts."""
    note = _t("Kartan visar möjlig etableringsyta och scenarioyta inom potentialen utifrån nuvarande val.") if layer_control_count else _t("Kartan uppdateras när minst ett potentiallager är aktivt.")
    raw = energy_model_state.get("result_presentation")
    if not isinstance(raw, Mapping):
        return note
    result = parse_result_presentation(raw)
    outside = [
        f"{_t(value.label).lower()} {_potential_popup_area(value.outside_need_km2)}"
        for value in result.technologies
        if value.outside_need_km2 > result.display_tolerance_km2
    ] if result.fit_status == "shortage" else []
    if outside:
        note = (
            f"<strong style='color:#be123c;'>{html.escape(_t('Varning:'))}</strong> "
            + html.escape(_t("map.shortage_note",
                             area=_potential_popup_area(result.total.outside_need_km2), parts=', '.join(outside)))
        )
    return note


def _render_reused_workspace_outputs(
    cache: dict[str, Any],
    region: dict[str, Any],
    opacity: float,
    preserve_map_view: bool,
    map_reset_token: int,
    right_panel: Any | None,
    access_readiness: WorkspaceAccessReadiness,
    landscape_display_layers: list[dict[str, Any]] | None = None,
    social_acceptance_display_layer: dict[str, Any] | None = None,
    review_readiness: WorkspaceReviewReadiness | None = None,
    *,
    show_scenario_mix: bool = True,
) -> None:
    _loading_phase("loading.map")
    base_layers = (
        cache.get("layers") if isinstance(cache.get("layers"), list) else []
    )
    layers = _dedupe_layers(
        [
            *base_layers,
            *(landscape_display_layers or []),
            *(
                [social_acceptance_display_layer]
                if social_acceptance_display_layer is not None
                else []
            ),
        ]
    )
    map_state = cache.get("map_state") if isinstance(cache.get("map_state"), dict) else {}
    energy_model_state = cache.get("energy_model_state") if isinstance(cache.get("energy_model_state"), dict) else {"available": False}
    if isinstance(map_state, dict):
        map_state = dict(map_state)
        map_state.setdefault("establishment_hex_stats", energy_model_state.get("establishment_hex_stats"))
        map_state["geography_effect_notes"] = _geography_effect_notes(energy_model_state)
        arguments = map_state.get("geography_filter_arguments")
        if isinstance(arguments, dict):
            map_state["geography_filter_notes"] = _geography_filter_notes(**arguments)
    performance_log = cache.get("performance_log") if isinstance(cache.get("performance_log"), list) else []
    note_body = _workspace_map_note(energy_model_state, int(cache.get("layer_control_count", len(layers))))

    _render_layers(
        region,
        layers,
        opacity,
        map_state_key=f"{region.get('region_id', 'region')}:workspace:{MAP_STATE_VERSION}" if preserve_map_view else None,
        map_reset_token=map_reset_token,
        opacity_key_prefix="combined",
        note_title="Gemensam potentialvy",
        note_body=note_body,
    )
    if show_scenario_mix:
        _render_workspace_scenario_mix_control(
            region, review_readiness, access_readiness=access_readiness,
        )

    summary_target = right_panel or st.container()
    _loading_phase("loading.results")
    with summary_target:
        _render_establishment_focus(
            energy_model_state,
            lambda: _combined_summary(map_state),
        )
        with st.expander(_t("Debug och prestanda"), expanded=False):
            _render_workspace_debug_status(region)
            _data_method(region)
            _render_performance_log(performance_log)
            st.markdown(f"**{_t('Aktiva beräkningar')}**")
            st.caption(
                _t("Den senaste visningsändringen återanvände redan beräknade resultat. "
                "Samma princip används nu för språk, paneler, kartvy och opacitet.")
            )
            performance_diagnostics = energy_model_state.get("performance_diagnostics") if isinstance(energy_model_state, dict) else None
            if isinstance(performance_diagnostics, list) and performance_diagnostics:
                st.dataframe(
                    _display_dataframe(pd.DataFrame(performance_diagnostics).head(8)),
                    width="stretch",
                    hide_index=True,
                    height=min(344, 72 + 32 * min(8, len(performance_diagnostics))),
                )
            _render_wind_preview_diagnostics(
                energy_model_state.get("wind_preview_diagnostics")
            )


def _combined_summary(map_state: dict[str, Any]) -> None:
    st.markdown(
        f"<h3 data-potential-tutorial-anchor='right-geographies'>{html.escape(_t('Geografier'))}</h3>",
        unsafe_allow_html=True,
    )
    _render_geography_user_summary(map_state)


def _delivery_manifest_rows(
    region_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Describe only repo-owned contracts for the selected delivery region."""

    delivery = load_delivery_region_manifest(region_id)
    rows: list[dict[str, Any]] = []

    def add_row(contract: str, declared_path: Any) -> None:
        path_value = str(declared_path or "").strip()
        if not path_value:
            rows.append(
                {
                    "Kontrakt": contract,
                    "Status": "Saknas i manifestet",
                    "Repo-sökväg": "",
                }
            )
            return
        resolved = (REPO_ROOT / path_value).resolve()
        repo_owned = resolved != REPO_ROOT and REPO_ROOT in resolved.parents
        rows.append(
            {
                "Kontrakt": contract,
                "Status": (
                    "Deklarerat"
                    if repo_owned and resolved.is_file()
                    else "Ogiltig eller saknad repo-fil"
                ),
                "Repo-sökväg": path_value if repo_owned else "",
            }
        )

    add_row("region", f"regions/{region_id}/region.json")
    add_row("workspace_profile", delivery.get("workspace_profile"))
    add_row("geography_manifest", delivery.get("geography_manifest"))

    analysis_manifests = delivery.get("analysis_manifests")
    if not isinstance(analysis_manifests, dict):
        analysis_manifests = {}
    try:
        profile = load_workspace_profile(region_id)
        technology_ids = tuple(profile.technologies)
    except (FileNotFoundError, KeyError, TypeError, ValueError):
        technology_ids = tuple(sorted(str(key) for key in analysis_manifests))
    for technology_id in technology_ids:
        add_row(
            f"analysis_manifests.{technology_id}",
            analysis_manifests.get(technology_id),
        )

    add_row("landscape_manifest", delivery.get("landscape_manifest"))
    add_row("scenario_manifest", delivery.get("scenario_manifest"))
    add_row(
        "social_acceptance_manifest",
        delivery.get("social_acceptance_manifest"),
    )

    active_keys = (
        "schema_version",
        "region_id",
        "display_name",
        "country",
        "status",
        "data_status",
        "behavior_reference",
        "native_crs",
        "web_crs",
        "available_h3_resolutions",
        "default_h3_resolution",
        "default_map_center",
        "default_zoom",
        "workspace_profile",
        "analysis_manifests",
        "geography_manifest",
        "landscape_manifest",
        "scenario_manifest",
        "social_acceptance_manifest",
        "review_access",
    )
    active_delivery = {
        key: delivery[key]
        for key in active_keys
        if key in delivery
    }
    return active_delivery, rows


def _data_method(
    region: dict[str, Any],
    *,
    delivery_contract_only: bool = False,
) -> None:
    with st.expander(_t("Data och metod"), expanded=False):
        if delivery_contract_only:
            region_id = str(region.get("region_id") or "").strip().lower()
            delivery, rows = _delivery_manifest_rows(region_id)
            status_frame = pd.DataFrame(rows)
            st.caption(
                _t("Aktiva kontrakt läses endast från regionens repoägda "
                "delivery-manifest. Äldre arkivmanifest visas inte som "
                "använda och kan inte aktivera en arbetsytefunktion.")
            )
            st.dataframe(
                _display_dataframe(status_frame[["Kontrakt", "Status"]]),
                width="stretch",
                hide_index=True,
            )
            with st.expander(
                _t("Manifest och tekniska sökvägar"),
                expanded=False,
            ):
                st.caption(
                    _t("Repo-sökvägarna och JSON-vyn nedan är regionens aktiva "
                    "arbetsyte- och analysdeklaration för denna körning. "
                    "Legacy- och runtimeproveniens redovisas separat och "
                    "aktiverar inga funktioner här.")
                )
                st.dataframe(
                    _display_dataframe(status_frame),
                    width="stretch",
                    hide_index=True,
                )
                st.json(delivery)
            return

        rows = _presentation_method_rows(region)
        status_frame = pd.DataFrame(rows)
        st.caption(_t("Datakällor och modellmanifest som används i denna region."))
        st.dataframe(_display_dataframe(status_frame[["manifest", "exists"]]), width="stretch", hide_index=True)
        with st.expander(_t("Manifest och tekniska sökvägar"), expanded=False):
            st.dataframe(_display_dataframe(status_frame), width="stretch", hide_index=True)
            st.json(region)


@_presentation_input("method_rows")
def _presentation_method_rows(region: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, label in (
        ("scenario_manifest", "Scenarier"),
        ("landscape_manifest", "Landskapsanalys"),
        ("potential_manifest", "Potential"),
    ):
        path = resolve_repo_path(region.get(key))
        rows.append({"manifest": label, "path": str(path) if path is not None else "",
                     "exists": bool(path and path.exists())})
    return rows


def _status_for_part(status_rows: list[dict[str, Any]], label: str) -> str:
    for row in status_rows:
        if str(row.get("del")) == str(label):
            return str(row.get("status", "saknas"))
    return "saknas"


def _disabled_note(label: str, status_rows: list[dict[str, Any]]) -> str:
    status = _status_for_part(status_rows, label)
    return "Data kopplad." if status == "klar" else f"Data saknas: {label}."


def _workspace_availability_presentation(state: str) -> tuple[str, str, str]:
    return {
        "available": ("Tillgänglig lokalt", "green", ":material/check_circle:"),
        "missing_manifest": ("Saknas i manifestet", "red", ":material/error:"),
        "missing_data": ("Data saknas", "red", ":material/database_off:"),
        "not_implemented": ("Inte implementerad", "orange", ":material/code_off:"),
        "not_validated": ("Inte validerad", "orange", ":material/warning:"),
        "technically_validated": (
            "Tekniskt validerad",
            "blue",
            ":material/verified:",
        ),
        "regionally_accepted": (
            "Regionalt accepterad",
            "green",
            ":material/verified_user:",
        ),
        "public": ("Publik", "green", ":material/public:"),
    }[str(state)]


def _review_capability_state(
    readiness: WorkspaceReviewReadiness | None,
    capability_id: str,
    *,
    fallback: str = "not_validated",
) -> str:
    if readiness is None:
        return fallback
    try:
        return readiness.capability(capability_id).state
    except KeyError:
        return fallback


def _workspace_access_group_availability(
    readiness: WorkspaceAccessReadiness,
    analysis_id: str,
) -> tuple[CapabilityAvailability, ...]:
    """Adapt canonical readiness to the single shared group form."""

    profile = load_workspace_profile(readiness.region_id)
    rows: list[CapabilityAvailability] = []
    for group in profile.standard_groups:
        capability = readiness.capability(
            f"{str(analysis_id)}.group.{group.id}"
        )
        rows.append(
            CapabilityAvailability(
                capability_id=capability.capability_id,
                state=capability.state,
                interaction=capability.interaction,
                label=group.label,
                analysis_label=group.analysis_label,
                interpretation=group.interpretation,
                layer_ids=capability.layer_ids,
                detail=capability.detail,
            )
        )
    return tuple(rows)


def _workspace_ui_identity(
    region_id: str,
    scope_id: str,
) -> WorkspaceUiIdentity:
    """Bind one workspace UI scope to the active region and access scope."""

    normalized_region_id = str(region_id or "").strip().lower()
    normalized_scope_id = str(scope_id or "").strip().lower()
    access_scope = str(
        st.session_state.get(REGION_SESSION_SCOPE_KEY) or ""
    ).strip().lower()
    return WorkspaceUiIdentity(
        region_id=normalized_region_id,
        access_scope=access_scope,
        scope_id=normalized_scope_id,
    )


def _workspace_capability_readiness(
    region_id: str,
    capability_id: str,
    review_readiness: WorkspaceReviewReadiness | None,
    access_readiness: WorkspaceAccessReadiness,
) -> WorkspaceCapabilityReadiness:
    """Reuse this render's token-bound checks for every capability panel."""

    if (
        access_readiness.region_id != str(region_id or "").strip().lower()
        or access_readiness.review != review_readiness
    ):
        raise ValueError("Capability readiness does not match the active workspace")
    return access_readiness.capability(capability_id)


def _workspace_scenario_readiness(
    region_id: str,
    review_readiness: WorkspaceReviewReadiness | None,
    access_readiness: WorkspaceAccessReadiness,
) -> WorkspaceCapabilityReadiness:
    """Resolve the same typed scenario capability for product and review."""

    return _workspace_capability_readiness(
        region_id, SCENARIO_CAPABILITY_ID, review_readiness, access_readiness,
    )


def _clear_workspace_scenario_state(identity: WorkspaceUiIdentity) -> None:
    """Clear only one region/access/workspace.scenario namespace."""

    prefix = workspace_state_prefix(identity)
    for key in tuple(st.session_state):
        if str(key).startswith(prefix):
            st.session_state.pop(key, None)


def _read_applied_workspace_scenario_request(
    identity: WorkspaceUiIdentity,
) -> ScenarioRequest | None:
    """Read strict applied scenario state without a compatibility fallback."""

    raw = st.session_state.get(_workspace_applied_request_key(identity))
    if raw is None:
        return None
    request = parse_scenario_request(raw)
    contract = load_catalog_scenario_contract(identity.region_id)
    if request.contract_signature_sha256 != scenario_contract_signature(contract):
        _clear_workspace_scenario_state(identity)
        return None
    validate_scenario_request_from_contract(contract, request)
    if (
        identity.scope_id != SCENARIO_CAPABILITY_ID
        or request.region_id != identity.region_id
        or request.access_scope != identity.access_scope
        or request.capability_id != SCENARIO_CAPABILITY_ID
    ):
        raise ValueError(
            "Applied scenario request does not match its workspace UI identity"
        )
    return request


def _ensure_workspace_scenario_request(
    identity: WorkspaceUiIdentity,
    contract: ScenarioContract,
) -> ScenarioRequest | None:
    """Create only the manifest default for product; review starts empty."""

    request = _read_applied_workspace_scenario_request(identity)
    if request is not None or not _workspace_uses_complete_runtime(identity):
        return request
    request = build_scenario_request_from_contract(
        contract,
        access_scope=identity.access_scope,
    )
    st.session_state[_workspace_applied_request_key(identity)] = request.as_dict()
    return request


def _prime_workspace_scenario_draft(
    identity: WorkspaceUiIdentity,
    contract: ScenarioContract,
    request: ScenarioRequest | None,
) -> None:
    """Initialize form widgets once without overwriting unsubmitted edits."""

    st.session_state.setdefault(
        _workspace_draft_key(identity, "scenario"),
        request.scenario_id if request is not None else contract.default_scenario_id,
    )
    st.session_state.setdefault(
        _workspace_draft_key(identity, "area_demand"),
        (
            request.area_demand_scenario
            if request is not None
            else contract.default_area_demand_scenario
        ),
    )
    request_shares = (
        {item.technology_id: item.share_pct for item in request.technology_shares}
        if request is not None
        else {
            item.technology_id: item.share_pct
            for item in (model_shares(contract, contract.default_scenario_id)
                         if contract.adapter_id == CAPACITY_ADAPTER else contract.default_technology_shares)
        }
    )
    for technology_id in contract.technology_ids:
        st.session_state.setdefault(
            _workspace_draft_key(
                identity,
                "technology_share",
                technology_id,
            ),
            float(request_shares[technology_id]),
        )


def _reset_workspace_scenario_state(identity: WorkspaceUiIdentity) -> None:
    """Reset only scenario request and draft state before the next rerun."""

    _clear_workspace_scenario_state(identity)
    _invalidate_workspace_cache("scenario controls reset")
    _request_ui_only_rerun("energiscenario nollställt")


def _scenario_technology_label(technology_id: str) -> str:
    return {
        "wind": _t("Vind"),
        "solar": _t("Sol"),
    }.get(str(technology_id), str(technology_id).replace("_", " ").capitalize())


@st.cache_data(show_spinner=False, max_entries=32)
def _cached_catalog_scenario_result(request_json: str) -> dict[str, Any]:
    """Execute one strict catalog request behind a bounded data cache."""

    request = parse_scenario_request(json.loads(request_json))
    return run_catalog_scenario_request(request).as_dict()


def _workspace_scenario_result(
    request: ScenarioRequest | None,
) -> ScenarioResult | None:
    if request is None:
        return None
    request_json = json.dumps(
        request.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    result = parse_scenario_result(
        _cached_catalog_scenario_result(request_json)
    )
    if result.request != request:
        raise ValueError("Scenario result does not match the applied request")
    return result


def _apply_workspace_scenario_draft(
    identity: WorkspaceUiIdentity,
    contract: ScenarioContract,
    previous_request: ScenarioRequest | None,
    *,
    error_state_key: str | None = None,
    restore_capacity_defaults: bool = False,
    capacity_references: list[dict[str, Any]] | None = None,
) -> tuple[ScenarioRequest | None, bool]:
    """Return the validated request and acceptance, including unchanged Apply."""

    scenario_key = _workspace_draft_key(identity, "scenario")
    area_key = _workspace_draft_key(identity, "area_demand")
    share_keys = {
        technology_id: _workspace_draft_key(
            identity,
            "technology_share",
            technology_id,
        )
        for technology_id in contract.technology_ids
    }
    independent_capacity = _uses_independent_capacity(contract)
    if not independent_capacity and contract.adapter_id == CAPACITY_ADAPTER and (
        previous_request is None or previous_request.scenario_id != str(st.session_state[scenario_key])
    ):
        for share in model_shares(contract, str(st.session_state[scenario_key])):
            st.session_state[share_keys[share.technology_id]] = share.share_pct
    try:
        if independent_capacity:
            capacities = None if restore_capacity_defaults else {
                technology_id: float(st.session_state[_workspace_draft_key(identity, "capacity_mw", technology_id)])
                for technology_id in contract.technology_ids
            }
            if capacities is not None and any(not math.isfinite(value) or not 0.0 <= value <= 200.0
                                               for value in capacities.values()):
                raise ValueError("Installed capacities must be between 0 and 200 MW")
            # Exact source pairs retain the original request and its cached result.
            # Other pairs are explicit user input, never a rescaled model forecast.
            reference_id = None
            if capacities is not None:
                if capacity_references is None:
                    raise ValueError("Current capacity references are unavailable")
                reference_id = next((row["scenario_id"] for row in capacity_references
                                     if row["capacity_mw"] == capacities), None)
            submitted_request = build_scenario_request_from_contract(
                contract, access_scope=identity.access_scope,
                scenario_id=reference_id,
                capacity_mw_by_technology=None if reference_id is not None else capacities,
            )
        else:
            submitted_request = build_scenario_request_from_contract(
                contract,
                access_scope=identity.access_scope,
                scenario_id=str(st.session_state[scenario_key]),
                area_demand_scenario=str(st.session_state[area_key]),
                technology_shares_pct={
                    technology_id: float(st.session_state[share_key])
                    for technology_id, share_key in share_keys.items()
                },
            )
        submitted_result = _workspace_scenario_result(submitted_request)
        if submitted_result is None or submitted_result.request != submitted_request:
            raise ValueError("Scenario executor did not return the submitted request")
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ) as exc:
        if error_state_key:
            st.session_state[error_state_key] = str(exc)
        else:
            st.error(
                _t("Scenarioändringarna kunde inte bindas till manifestet. "
                "Det senast tillämpade scenariot behålls.")
            )
            st.caption(_t('Teknisk orsak: {p0}', p0=exc))
        return previous_request, False

    if error_state_key:
        st.session_state.pop(error_state_key, None)
    if submitted_request == previous_request:
        # Apply still takes the ordinary input-verification path. Only the
        # later, current-fingerprint cache gate may reuse the rendered result.
        _request_ui_only_rerun("unchanged controls applied")
        return submitted_request, True
    st.session_state[_workspace_applied_request_key(identity)] = (
        submitted_request.as_dict()
    )
    _invalidate_workspace_cache("scenario controls applied")
    return submitted_request, True


def _apply_workspace_scenario_mix_callback(
    identity: WorkspaceUiIdentity,
    contract: ScenarioContract,
) -> None:
    """Queue the mix for validation inside the next verified input operation."""

    wind_key = _workspace_draft_key(
        identity,
        "technology_share",
        "wind",
    )
    solar_key = _workspace_draft_key(
        identity,
        "technology_share",
        "solar",
    )
    st.session_state[solar_key] = 100.0 - float(st.session_state[wind_key])
    _queue_workspace_scenario_mix(identity)


def _queue_workspace_scenario_mix(identity: WorkspaceUiIdentity, *, restore_capacity_defaults: bool = False) -> None:
    _clear_ui_only_rerun()
    st.session_state["potential_pending_scenario_mix"] = (
        identity.region_id, identity.access_scope,
    ) + (("restore_capacity_defaults",) if restore_capacity_defaults else ())


def _apply_pending_workspace_scenario_mix(
    region_id: str, access_scope: str, *, capacity_references: list[dict[str, Any]] | None = None,
) -> None:
    pending = st.session_state.pop("potential_pending_scenario_mix", None)
    restore_defaults = pending == (region_id, access_scope, "restore_capacity_defaults")
    if not restore_defaults and pending != (region_id, access_scope):
        return
    identity = _workspace_ui_identity(region_id, SCENARIO_CAPABILITY_ID)
    if identity.access_scope != access_scope:
        raise ValueError("Pending mix escaped its current access scope")
    contract = load_catalog_scenario_contract(region_id)
    previous_request = _read_applied_workspace_scenario_request(identity)
    error_state_key = workspace_state_key(identity, "mix_error")
    _, applied = _apply_workspace_scenario_draft(
        identity,
        contract,
        previous_request,
        error_state_key=error_state_key,
        restore_capacity_defaults=restore_defaults,
        capacity_references=capacity_references,
    )
    if not applied:
        _request_ui_only_rerun("energimix kunde inte tillämpas")


def _render_workspace_scenario_controls(
    identity: WorkspaceUiIdentity,
    readiness: WorkspaceCapabilityReadiness,
) -> tuple[ScenarioRequest | None, bool]:
    """Return the applied scenario and whether the accepted request changed."""

    st.markdown('<span data-workspace-guide="scenario" data-workspace-guide-kind="panel"></span>', unsafe_allow_html=True)

    if (
        identity.scope_id != SCENARIO_CAPABILITY_ID
        or readiness.capability_id != SCENARIO_CAPABILITY_ID
    ):
        raise ValueError("Scenario renderer received the wrong capability identity")
    state_label, state_color, state_icon = _workspace_availability_presentation(
        readiness.state
    )
    st.badge(_t(state_label), color=state_color, icon=state_icon)
    if readiness.interaction != "interactive":
        st.caption(_t(readiness.detail))
        _clear_workspace_scenario_state(identity)
        st.selectbox(
            _t("Energiscenario"),
            options=(_t("Saknas i manifestet"),),
            key=workspace_state_key(identity, "capability"),
            disabled=True,
            help=_t('Orsak: {p0}.', p0=readiness.state),
            persist_state="session",
        )
        st.caption(
            _t("Scenario, markintensitet och teknikandelar förblir låsta tills "
            "regionens kontrakt är komplett och validerat.")
        )
        return None, False

    try:
        contract = load_catalog_scenario_contract(identity.region_id)
        request = _ensure_workspace_scenario_request(identity, contract)
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ) as exc:
        st.error(
            _t("Det sparade scenariovalet kunde inte valideras. "
            "Ingen beräkning eller fallback används.")
        )
        st.caption(_t('Teknisk orsak: {p0}', p0=exc))
        st.button(
            _t("Nollställ scenario"),
            key=workspace_state_key(identity, "reset"),
            icon=":material/filter_alt_off:",
            width="stretch",
            on_click=_reset_workspace_scenario_state,
            args=(identity,),
        )
        return None, False

    if _uses_independent_capacity(contract):
        return request, False
    _prime_workspace_scenario_draft(identity, contract, request)
    scenario_key = _workspace_draft_key(identity, "scenario")
    area_key = _workspace_draft_key(identity, "area_demand")
    level_by_id = {
        item.scenario_id: item for item in contract.planning_levels
    }
    area_by_id = {
        item.scenario_id: item for item in contract.area_demand_options
    }
    format_text = _language_formatter()
    capacity = contract.adapter_id == CAPACITY_ADAPTER
    demonstration_levels = capacity and "capacity_scale_by_scenario" in contract.adapter_configuration()["capacity"]
    with st.form(
        workspace_state_key(identity, "form"),
        clear_on_submit=False,
        enter_to_submit=False,
    ):
        scenario_choice = st.selectbox if capacity else _render_localized_choice
        scenario_choice(
            (_t("Demonstrationsnivå") if demonstration_levels else _t("Årtal") if capacity else _t("Energiscenario")),
            options=tuple(level_by_id),
            key=scenario_key,
            format_func=lambda value: (
                level_by_id[str(value)].label if capacity else
                format_text("{p0} · {p1:g}× energi", p0=format_text(level_by_id[str(value)].label),
                   p1=level_by_id[str(value)].energy_scale)
            ),
            persist_state="session",
        )
        if capacity:
            st.caption(
                _t("Årtalen är källmodellens referensår. Skalningen är vald för att visa ytbehov och ytbrist, inte som en regional prognos.")
                if demonstration_levels else
                _t("Årtalet laddar modellens kapacitet och vind/sol-fördelning. Reglaget under kartan låter dig prova en egen mix.")
            )
        else:
            _render_localized_choice(
                _t("Markintensitet"),
                options=tuple(area_by_id),
                key=area_key,
                format_func=lambda value: format_text(area_by_id[str(value)].label),
                persist_state="session",
            )
            st.caption(
                _t("Energimixen styrs med reglaget direkt under kartan. Vind och sol "
                "är kopplade och summerar alltid till exakt 100 %.")
            )
        submitted = st.form_submit_button(
            ui_text("apply_changes", _wind_control_language()),
            key=workspace_state_key(identity, "apply"),
            type="primary",
            width="stretch",
            on_click=_clear_ui_only_rerun,
        )

    st.button(
        _t("Nollställ scenario"),
        key=workspace_state_key(identity, "reset"),
        icon=":material/filter_alt_off:",
        width="stretch",
        on_click=_reset_workspace_scenario_state,
        args=(identity,),
    )
    if not submitted:
        return request, False
    applied_request, accepted = _apply_workspace_scenario_draft(
        identity, contract, request
    )
    return applied_request, accepted and applied_request != request


def _restore_capacity_model_mix(identity, contract):
    previous = _read_applied_workspace_scenario_request(identity)
    scenario_id = previous.scenario_id if previous else contract.default_scenario_id
    st.session_state[_workspace_draft_key(identity, "scenario")] = scenario_id
    for share in model_shares(contract, scenario_id):
        st.session_state[_workspace_draft_key(identity, "technology_share", share.technology_id)] = share.share_pct
    _queue_workspace_scenario_mix(identity)


def _uses_independent_capacity(contract: ScenarioContract) -> bool:
    """The owner-selected Bornholm experiment leaves other regional controls intact."""
    return contract.region_id == "bornholm" and contract.adapter_id == CAPACITY_ADAPTER


def _capacity_reference_values(contract: ScenarioContract, snapshot: Any) -> list[dict[str, Any]]:
    """Project already verified source data without another read/declaration pass."""
    return [
        {"scenario_id": level.scenario_id, "label": level.label, "year": level.planning_year,
         "capacity_mw": {row.technology_id: row.capacity_mw * capacity_scale(contract, level.scenario_id)
                         for row in snapshot.capacity_observations
                         if (row.source_scenario, row.planning_year) == (level.source_scenario, level.planning_year)}}
        for level in contract.planning_levels
    ]


def _restore_workspace_capacity_defaults(identity: WorkspaceUiIdentity) -> None:
    for technology_id in ("wind", "solar"):
        st.session_state.pop(_workspace_draft_key(identity, "capacity_mw", technology_id), None)
    _queue_workspace_scenario_mix(identity, restore_capacity_defaults=True)


def _render_capacity_reference_marks(references: list[dict[str, Any]], technology_id: str) -> None:
    # A passive scale avoids a custom widget, JS events and internal slider CSS.
    marks = []
    for index, reference in enumerate(references):
        mw = float(reference["capacity_mw"][technology_id])
        if not 0.0 <= mw <= 200.0:
            continue
        title = html.escape(f"{reference['label']}: {mw:g} MW", quote=True)
        marks.append(
            f'<span title="{title}" style="position:absolute;left:{mw / 2:g}%;top:0;'
            'border-left:1px solid currentColor;height:6px">'
            f'<span style="position:absolute;top:{8 + (index % 2) * 13}px;'
            'transform:translateX(-50%);font-size:11px;white-space:nowrap">'
            f'{int(reference["year"])}</span></span>'
        )
    st.markdown('<div style="position:relative;height:40px;margin:0 8px;opacity:.65" '
                'data-capacity-reference-marks="' + technology_id + '">' + "".join(marks) + '</div>',
                unsafe_allow_html=True)


def _render_workspace_capacity_controls(identity, energy_model_state) -> None:
    """Submit both browser drafts together through the existing verified Apply path."""
    capacities = energy_model_state["capacity_mw"]
    references = energy_model_state["capacity_references"]
    with st.container(border=False, key="workspace_mix_panel"):
        st.markdown('<span data-workspace-guide="mix" data-workspace-guide-kind="block"></span>', unsafe_allow_html=True)
        st.subheader(_t("Installerad effekt"))
        st.caption(_t("Välj total effekt för vindkraft och marksol oberoende av varandra. Befintlig kapacitet ingår i referensvärdena."))
        with st.form(workspace_state_key(identity, "capacity_form"), clear_on_submit=False, enter_to_submit=False):
            for technology_id, label, step in (("wind", "Vindkraft (MW)", 1.0), ("solar", "Marksol (MW)", 0.1)):
                key = _workspace_draft_key(identity, "capacity_mw", technology_id)
                st.session_state.setdefault(key, float(capacities[technology_id]))
                st.slider(_t(label), min_value=0.0, max_value=200.0, step=step,
                          format="%.1f MW", key=key, persist_state="session")
                _render_capacity_reference_marks(references, technology_id)
            st.form_submit_button(ui_text("apply_changes", _wind_control_language()),
                                  key=workspace_state_key(identity, "capacity_apply"),
                                  type="primary", width="stretch",
                                  on_click=_queue_workspace_scenario_mix, args=(identity,))
        st.caption(_t("Markeringarna visar EML:s referensår. Resultaten uppdateras när du tillämpar värdena."))
        st.caption(_t("Tillämpat: {p0:g} MW vind · {p1:g} MW marksol · totalt {p2:g} MW.",
                      p0=capacities["wind"], p1=capacities["solar"], p2=math.fsum(capacities.values())))
        if not any(capacities.values()):
            st.caption(_t("Ingen kapacitet vald – inget ytbehov. Årsproduktion saknas i underlaget."))
        st.button(_t("Återställ standardvärden"), key=workspace_state_key(identity, "restore_model_capacity"),
                  on_click=_restore_workspace_capacity_defaults, args=(identity,))
        if st.session_state.get(workspace_state_key(identity, "mix_error")):
            st.error(_t("Kapacitetsändringarna kunde inte tillämpas. De senast tillämpade värdena behålls."))


def _render_workspace_scenario_mix_control(
    region: dict[str, Any],
    review_readiness: WorkspaceReviewReadiness | None = None,
    *,
    access_readiness: WorkspaceAccessReadiness,
) -> None:
    """Render the coupled mix and apply it before the calculation rerun."""

    region_id = str(region.get("region_id") or "").strip().lower()
    identity = _workspace_ui_identity(region_id, SCENARIO_CAPABILITY_ID)
    try:
        readiness = _workspace_scenario_readiness(
            region_id,
            review_readiness,
            access_readiness,
        )
        if readiness.interaction != "interactive":
            return
        contract = load_catalog_scenario_contract(region_id)
        request = _ensure_workspace_scenario_request(identity, contract)
        if _uses_independent_capacity(contract):
            # Its independent MW form belongs to the EML panel, including replay.
            return
        if tuple(contract.technology_ids) != ("wind", "solar"):
            raise ValueError(
                "The coupled energy-mix control requires ordered wind and solar technologies"
            )
        _prime_workspace_scenario_draft(identity, contract, request)
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ) as exc:
        with st.container(border=True):
            st.subheader(_t("Energimix"))
            st.error(_t("Energimixen är inte tillgänglig för den valda regionen."))
            st.caption(_t('Teknisk orsak: {p0}', p0=exc))
        return

    wind_key = _workspace_draft_key(
        identity,
        "technology_share",
        "wind",
    )
    solar_key = _workspace_draft_key(
        identity,
        "technology_share",
        "solar",
    )
    capacity = contract.adapter_id == CAPACITY_ADAPTER
    with st.container(border=True, key="workspace_mix_panel"):
        st.markdown('<span data-workspace-guide="mix" data-workspace-guide-kind="block"></span>', unsafe_allow_html=True)
        st.subheader(_t("Kapacitetsmix") if capacity else _t("Energimix"))
        st.caption(
            _t("Fördela årets totala installerade effekt mellan vind och sol. Årsproduktion saknas i underlaget.") if capacity else
            _t("Fördela scenariots totala energimängd mellan vind och sol. "
            "Andelarna är kopplade och summerar alltid till 100 %.")
        )
        with st.form(
            workspace_state_key(identity, "mix_form"),
            clear_on_submit=False,
            enter_to_submit=False,
        ):
            wind_share = st.slider(
                _t("Vindandel av installerad effekt (%)") if capacity else _t("Vindandel (%)"),
                min_value=0.0,
                max_value=100.0,
                step=float(contract.technology_share_step_pct),
                key=wind_key,
                help=_t("När vindandelen ökar minskar solandelen lika mycket."),
                persist_state="session",
            )
            solar_share = 100.0 - float(wind_share)
            st.session_state[solar_key] = solar_share
            mix_columns = st.columns(2)
            mix_columns[0].metric(_t("Vind"), f"{float(wind_share):g} %")
            mix_columns[1].metric(_t("Sol"), f"{solar_share:g} %")
            st.form_submit_button(
                _t("Använd egen mix") if capacity else _t("Använd energimix"),
                key=workspace_state_key(identity, "mix_apply"),
                type="primary",
                width="stretch",
                on_click=_apply_workspace_scenario_mix_callback,
                args=(identity, contract),
            )
        if capacity and request is not None:
            if "capacity_scale_by_scenario" in contract.adapter_configuration()["capacity"]:
                st.caption(_t("Tillämpat: {p0} · skalning ×{p1:g} av källmodellens kapacitet.",
                              p0=contract.planning_level(request.scenario_id).label,
                              p1=capacity_scale(contract, request.scenario_id)))
            is_model = request.technology_shares == model_shares(contract, request.scenario_id)
            st.caption(_t("Modellens fördelning") if is_model else _t("Egen mix – årets totala MW är oförändrat."))
            st.button(_t("Återställ modellens mix"), key=workspace_state_key(identity, "restore_model_mix"),
                      on_click=_restore_capacity_model_mix, args=(identity, contract))
        mix_error = st.session_state.get(
            workspace_state_key(identity, "mix_error")
        )
        if mix_error:
            st.error(
                _t("Scenarioändringarna kunde inte bindas till manifestet. "
                "Det senast tillämpade scenariot behålls.")
            )
            st.caption(_t('Teknisk orsak: {p0}', p0=mix_error))


def _render_workspace_scenario_result_summary(result: ScenarioResult) -> None:
    """Render only values from the current immutable ScenarioResult."""

    if result.source_status == "provisional_fallback":
        st.badge(
            _t("Provisorisk datakälla"),
            color="orange",
            icon=":material/warning:",
        )
    if result.request.adapter_id == CAPACITY_ADAPTER:
        st.warning(source_warning(result, _language()))
        contract = load_catalog_scenario_contract(result.request.region_id)
        if "capacity_scale_by_scenario" in contract.adapter_configuration()["capacity"]:
            st.caption(_t("Tillämpat: {p0} · skalning ×{p1:g} av källmodellens kapacitet.",
                          p0=contract.planning_level(result.request.scenario_id).label,
                          p1=capacity_scale(contract, result.request.scenario_id)))
        is_model = result.request.technology_shares == model_shares(contract, result.request.scenario_id)
        if result.request.capacity_mw_by_technology is not None:
            st.caption(_t("Egen kapacitet · modellens arealfaktorer används. Årsproduktion saknas."))
        else:
            st.caption(f"{result.request.source_scenario} · {result.request.planning_year} · "
                       + (_t("Modellens fördelning") if is_model else _t("Egen mix")))
        st.dataframe(_display_dataframe(pd.DataFrame([{"Teknik": _scenario_technology_label(t.technology_id),
            "Kapacitet (MW)": t.capacity_mw, "Ytbehov (km²)": t.area_need_km2}
            for t in result.technologies]).round(3)), hide_index=True, width="stretch")
        st.caption(_t('Vind: {p0:g} MW/km². Marksol: {p1:g} m²/MW. Årsproduktion saknas i underlaget.', p0=1 / result.technology_result('wind').km2_per_mw, p1=result.technology_result('solar').km2_per_mw * 1_000_000))
    else:
        st.caption(
            _t('Valt: {p0} · markintensitet {p1} · modellkälla {p2}, {p3}.', p0=_t(_model_level_source(result.scenario_label)), p1=_t(_model_level_source(result.request.area_demand_scenario)), p2=result.request.source_scenario, p3=result.request.planning_year)
        )
        st.dataframe(
            _display_dataframe(pd.DataFrame(
                [
                    {
                        "Teknik": _scenario_technology_label(item.technology_id),
                        "Andel (%)": next(
                            share.share_pct
                            for share in result.request.technology_shares
                            if share.technology_id == item.technology_id
                        ),
                        "Energi (TWh)": item.energy_twh,
                        "km²/TWh": item.km2_per_twh,
                        "Ytbehov (km²)": item.area_need_km2,
                    }
                    for item in result.technologies
                ]
            ).round(3)),
            width="stretch",
            hide_index=True,
        )
        st.caption(
            _t('Totalt: {p0:.2f} TWh · bruttoytbehov {p1:.2f} km².', p0=result.total_energy_twh, p1=result.total_area_need_km2)
        )
    with st.expander(
        _t(":material/warning: Källstatus och begränsningar"),
        expanded=False,
    ):
        st.caption(source_warning(result, _language()))
        st.caption(
            _t('Status: {p0} · användning: {p1} · regionalt accepterad: {p2}.', p0=_t(result.source_status), p1=_t(result.allowed_use), p2=_t('ja') if result.regional_acceptance else _t('nej'))
        )
        st.caption(
            _t('Källa: {p0} (`{p1}`).', p0=result.source_label, p1=result.source_dataset_id)
        )


def _workspace_scenario_header_state(
    region: dict[str, Any],
    review_readiness: WorkspaceReviewReadiness | None,
    access_readiness: WorkspaceAccessReadiness,
) -> dict[str, Any]:
    """Return header state from the same namespaced applied request."""

    region_id = str(region.get("region_id") or "").strip().lower()
    identity = _workspace_ui_identity(region_id, SCENARIO_CAPABILITY_ID)
    try:
        readiness = _workspace_scenario_readiness(
            region_id, review_readiness, access_readiness,
        )
        if readiness.interaction != "interactive":
            return {"scenario": None, "request": None}
        contract = load_catalog_scenario_contract(region_id)
        request = _ensure_workspace_scenario_request(identity, contract)
        if request is None:
            return {"scenario": None, "request": None}
        return {
            "scenario": ("Egen kapacitet" if request.capacity_mw_by_technology is not None
                         else contract.planning_level(request.scenario_id).label),
            "scenario_id": request.scenario_id,
            "year": request.planning_year,
            "request": request.as_dict(),
        }
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ):
        return {"scenario": None, "request": None}


def _workspace_energy_model_state(
    scenario_result: ScenarioResult,
    *,
    h3_resolution: int,
    rooftop_selection: RooftopSelectionRequest | None,
) -> dict[str, Any]:
    """Adapt only the applied ScenarioResult to existing map/result consumers."""

    profile = load_workspace_profile(scenario_result.request.region_id)
    if tuple(item.technology_id for item in scenario_result.technologies) != (
        profile.technologies
    ):
        raise ValueError(
            "ScenarioResult technologies do not match the workspace profile"
        )
    typed_rooftop_result = _workspace_rooftop_result(
        rooftop_selection,
        scenario_result=scenario_result,
    )
    unavailable = isinstance(typed_rooftop_result, RooftopUnavailableResult)
    rooftop = None if unavailable else typed_rooftop_result.accounting
    solar_input = scenario_result.technology_result("solar")
    rooftop_credit = 0.0 if unavailable else float(rooftop.rooftop_contribution_twh)
    ground_twh = solar_input.energy_twh if unavailable else float(rooftop.ground_solar_twh)
    ground_area = float(solar_input.area_need_km2) if unavailable else float(rooftop.ground_area_need_km2)
    shares = {
        item.technology_id: item.share_pct
        for item in scenario_result.request.technology_shares
    }
    rows = [
        {
            "energy_key": item.technology_id,
            "Teknik": _scenario_technology_label(item.technology_id),
            "twh": item.energy_twh,
            "gross_twh": item.energy_twh,
            "rooftop_twh": 0.0,
            "ground_twh": item.energy_twh,
            "km2_per_twh": item.km2_per_twh,
            "gross_area_need_km2": item.area_need_km2,
            "area_need_km2": item.area_need_km2,
        }
        for item in scenario_result.technologies
    ]
    area_demand = pd.DataFrame(rows)
    solar_mask = area_demand["energy_key"].astype(str).eq("solar")
    area_demand.loc[solar_mask, "rooftop_twh"] = rooftop_credit
    area_demand.loc[solar_mask, "ground_twh"] = ground_twh
    area_demand.loc[solar_mask, "area_need_km2"] = ground_area
    wind_result = scenario_result.technology_result("wind")
    solar_result = scenario_result.technology_result("solar")
    debug_payload = {
        "scenario_result": scenario_result.as_dict(),
        "rooftop_request": typed_rooftop_result.request.as_dict(),
    }
    return {
        "available": True,
        "debug_run_id": _short_hash(debug_payload),
        "debug_payload": debug_payload,
        "scenario_request": scenario_result.request.as_dict(),
        "scenario_result": scenario_result.as_dict(),
        "scenario": scenario_result.request.scenario_id,
        "scenario_label": ("Egen kapacitet" if scenario_result.request.capacity_mw_by_technology is not None
                           else scenario_result.scenario_label),
        "source_scenario": scenario_result.request.source_scenario,
        "source_scenario_label": scenario_result.source_label,
        "source_year": scenario_result.request.planning_year,
        "energy_scale": scenario_result.request.energy_scale,
        "area_scenario_id": scenario_result.request.area_demand_scenario,
        "area_scenario_label": scenario_result.request.area_demand_scenario,
        "area_demand": area_demand,
        "wind_share_pct": float(shares["wind"]) if shares else None,
        "solar_share_pct": float(shares["solar"]) if shares else None,
        "wind_area_need_km2": float(wind_result.area_need_km2),
        "wind_km2_per_twh": wind_result.km2_per_twh,
        "solar_area_need_km2": ground_area,
        "solar_gross_area_need_km2": float(solar_result.area_need_km2),
        "solar_km2_per_twh": solar_result.km2_per_twh,
        "wind_twh": wind_result.energy_twh,
        "solar_twh": solar_result.energy_twh,
        "solar_ground_twh": ground_twh,
        "solar_rooftop_twh": rooftop_credit,
        "rooftop_solar": ({
            "status": "unavailable", "active": False,
            "accounting_total_policy": "no_credit",
            "reason": typed_rooftop_result.reason,
            "rooftop_contribution_twh": 0.0,
            "gross_solar_target_twh": solar_result.energy_twh,
            "ground_solar_twh": ground_twh,
            "gross_ground_area_need_km2": float(solar_result.area_need_km2),
            "ground_area_need_km2": ground_area,
            "selection": None, "request": typed_rooftop_result.request.as_dict(),
        } if unavailable else {
            "status": typed_rooftop_result.contract_status,
            "active": bool(rooftop_selection.enabled),
            "population": float(rooftop.population),
            "mapped_population": float(
                typed_rooftop_result.mapped_population_total
            ),
            "mapped_population_cell_count": int(
                typed_rooftop_result.mapped_population_cell_count
            ),
            "mapped_population_cell_ids_sha256": (
                typed_rooftop_result.mapped_population_cell_ids_sha256
            ),
            "panel_area_m2_per_person": float(
                rooftop.panel_area_m2_per_person
            ),
            "panel_area_m2": float(rooftop.panel_area_m2),
            "installed_capacity_kwp": float(rooftop.installed_capacity_kwp),
            "annual_yield_kwh_per_m2": float(
                rooftop.annual_yield_kwh_per_m2
            ),
            "technical_rooftop_twh": float(rooftop.technical_rooftop_twh),
            "rooftop_contribution_twh": float(
                rooftop.rooftop_contribution_twh
            ),
            "gross_solar_target_twh": solar_result.energy_twh,
            "ground_solar_twh": ground_twh,
            "gross_ground_area_need_km2": float(solar_result.area_need_km2),
            "ground_area_need_km2": ground_area,
            "accounting_total_policy": (
                typed_rooftop_result.accounting_total_policy
            ),
            "selection": rooftop_selection.as_dict(),
            "request": typed_rooftop_result.request.as_dict(),
        }),
        "hex_area_km2": float(h3_hex_area_km2(int(h3_resolution))),
        "h3_resolution": int(h3_resolution),
        # This remains a program-wide allocation invariant until a typed
        # allocation-policy capability replaces it; it is not region state.
        "auto_min_potential_share_pct": 65.0,
        "source_status": scenario_result.source_status,
        "capacity_based": scenario_result.request.adapter_id == CAPACITY_ADAPTER,
        "capacity_mw": {t.technology_id: t.capacity_mw for t in scenario_result.technologies},
        "area_warnings": pd.DataFrame(),
    }


def _render_applied_workspace_scenario(
    request: ScenarioRequest | None,
    *,
    h3_resolution: int | None,
    rooftop_selection: RooftopSelectionRequest | None,
) -> tuple[ScenarioResult | None, dict[str, Any]]:
    """Render one result and optionally adapt it to combined-map consumers."""

    if request is None:
        st.caption(
            _t("Inget scenario är tillämpat. Gör färdigt formuläret och välj "
            "Använd ändringar.")
        )
        return None, {"available": False}
    try:
        result = _workspace_scenario_result(request)
        if result is None:
            raise ValueError("Applied scenario request returned no result")
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ) as exc:
        st.error(
            _t("Det tillämpade scenariot kunde inte köras. Ingen äldre state "
            "eller regional fallback används.")
        )
        st.caption(_t('Teknisk orsak: {p0}', p0=exc))
        return None, {"available": False}
    _render_workspace_scenario_result_summary(result)
    if h3_resolution is None:
        return result, {"available": False, "scenario_result": result.as_dict()}
    try:
        energy_state = _workspace_energy_model_state(
            result,
            h3_resolution=int(h3_resolution),
            rooftop_selection=rooftop_selection,
        )
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ) as exc:
        st.error(
            _t("Scenariot kunde inte bindas till den tillämpade taksolsselectionen. "
            "Etableringsberäkningen stoppas.")
        )
        st.caption(_t('Teknisk orsak: {p0}', p0=exc))
        return result, {"available": False, "scenario_result": result.as_dict()}
    if (
        not energy_state.get("capacity_based")
        and energy_state.get("rooftop_solar", {}).get("status") == "unavailable"
    ):
        st.caption(_t("Taksol: data saknas. Hela solbehovet räknas därför som marksol; inget taksolsbidrag dras av."))
    rooftop_twh = float(energy_state.get("solar_rooftop_twh", 0.0) or 0.0)
    if rooftop_twh > 0.0:
        st.caption(
            _t('Taksolschablonen bidrar med {p0:.2f} TWh. Kvar för marksol: {p1:.2f} TWh och {p2:.2f} km².', p0=rooftop_twh, p1=float(energy_state['solar_ground_twh']), p2=float(energy_state['solar_area_need_km2']))
        )
    return result, energy_state


def _workspace_social_acceptance_readiness(
    region_id: str,
    review_readiness: WorkspaceReviewReadiness | None,
    access_readiness: WorkspaceAccessReadiness,
) -> WorkspaceCapabilityReadiness:
    """Resolve one social-acceptance capability for product and review."""

    return _workspace_capability_readiness(
        region_id, SOCIAL_ACCEPTANCE_CAPABILITY_ID, review_readiness, access_readiness,
    )


def _clear_workspace_social_acceptance_state(
    identity: WorkspaceUiIdentity,
) -> None:
    """Clear only one region/access/workspace.social_acceptance namespace."""

    prefix = workspace_state_prefix(identity)
    for key in tuple(st.session_state):
        if str(key).startswith(prefix):
            st.session_state.pop(key, None)


def _read_applied_workspace_social_acceptance_request(
    identity: WorkspaceUiIdentity,
) -> SocialAcceptanceRequest | None:
    """Read strict applied state without a legacy or region fallback."""

    raw = st.session_state.get(_workspace_applied_request_key(identity))
    if raw is None:
        return None
    request = parse_social_acceptance_request(raw)
    contract = load_catalog_social_acceptance_contract(identity.region_id)
    validate_social_acceptance_request_from_contract(contract, request)
    if (
        identity.scope_id != SOCIAL_ACCEPTANCE_CAPABILITY_ID
        or request.region_id != identity.region_id
        or request.access_scope != identity.access_scope
        or request.capability_id != SOCIAL_ACCEPTANCE_CAPABILITY_ID
    ):
        raise ValueError(
            "Applied social-acceptance request does not match its workspace "
            "UI identity"
        )
    return request


def _ensure_workspace_social_acceptance_request(
    identity: WorkspaceUiIdentity,
    contract: SocialAcceptanceContract,
    *,
    target_resolution: int | None,
) -> SocialAcceptanceRequest | None:
    """Create a technical product default; review always starts unapplied."""

    request = _read_applied_workspace_social_acceptance_request(identity)
    if request is not None and (
        target_resolution is None
        or request.target_resolution == int(target_resolution)
    ):
        return request
    if request is not None:
        request = build_social_acceptance_request_from_contract(
            contract,
            access_scope=identity.access_scope,
            layer_visible=request.layer_visible,
            scenario_id=request.scenario_id,
            target_resolution=int(target_resolution),
            impact_pct=request.impact_pct,
            allocation_priority_pct=request.allocation_priority_pct,
        )
        st.session_state[_workspace_applied_request_key(identity)] = (
            request.as_dict()
        )
        return request
    if not _workspace_uses_complete_runtime(identity):
        return None
    request = build_social_acceptance_request_from_contract(
        contract,
        access_scope=identity.access_scope,
        layer_visible=False,
        target_resolution=target_resolution,
    )
    st.session_state[_workspace_applied_request_key(identity)] = request.as_dict()
    return request


def _prime_workspace_social_acceptance_draft(
    identity: WorkspaceUiIdentity,
    contract: SocialAcceptanceContract,
    request: SocialAcceptanceRequest | None,
) -> None:
    """Initialize social form widgets without overwriting draft edits."""

    st.session_state.setdefault(
        _workspace_draft_key(identity, "layer_visible"),
        bool(request.layer_visible) if request is not None else False,
    )
    st.session_state.setdefault(
        _workspace_draft_key(identity, "scenario"),
        request.scenario_id if request is not None else contract.default_scenario_id,
    )
    st.session_state.setdefault(
        _workspace_draft_key(identity, "impact_pct"),
        float(
            request.impact_pct
            if request is not None
            else contract.impact_control.technical_initial_value
        ),
    )
    st.session_state.setdefault(
        _workspace_draft_key(identity, "allocation_priority_pct"),
        float(
            request.allocation_priority_pct
            if request is not None
            else contract.allocation_priority_control.technical_initial_value
        ),
    )


def _reset_workspace_social_acceptance_state(
    identity: WorkspaceUiIdentity,
) -> None:
    _clear_workspace_social_acceptance_state(identity)
    _invalidate_workspace_cache("social-acceptance controls reset")
    _request_ui_only_rerun("social acceptans nollställd")


@st.cache_data(show_spinner=False, max_entries=32)
def _cached_catalog_social_acceptance_result(
    request_json: str,
) -> dict[str, Any]:
    """Execute one strict social request behind a bounded data cache."""

    request = parse_social_acceptance_request(json.loads(request_json))
    return run_catalog_social_acceptance_request(request).as_dict()


def _workspace_social_acceptance_result(
    request: SocialAcceptanceRequest | None,
) -> SocialAcceptanceResult | None:
    if request is None:
        return None
    calculation_request_payload = request.as_dict()
    calculation_request_payload["layer_visible"] = False
    request_json = json.dumps(
        calculation_request_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    result_payload = dict(
        _cached_catalog_social_acceptance_result(request_json)
    )
    # Visibility is a typed request field, but never a calculation input. The
    # cached calculation is therefore rebound to the exact applied request and
    # parsed again before any UI or downstream consumer receives it.
    result_payload["request"] = request.as_dict()
    result = parse_social_acceptance_result(result_payload)
    if result.request != request:
        raise ValueError(
            "Social-acceptance result does not match the applied request"
        )
    return result


def _social_acceptance_calculation_request_payload(
    request: SocialAcceptanceRequest,
) -> dict[str, Any]:
    """Exclude the map-only toggle from the calculation identity."""

    payload = request.as_dict()
    payload.pop("layer_visible", None)
    return payload


def _render_workspace_social_acceptance_controls(
    identity: WorkspaceUiIdentity,
    readiness: WorkspaceCapabilityReadiness,
    *,
    target_resolution: int | None,
) -> tuple[SocialAcceptanceRequest | None, bool]:
    """Render the same manifest-bound form in product and review."""

    st.markdown('<span data-workspace-guide="social" data-workspace-guide-kind="panel"></span>', unsafe_allow_html=True)

    if (
        identity.scope_id != SOCIAL_ACCEPTANCE_CAPABILITY_ID
        or readiness.capability_id != SOCIAL_ACCEPTANCE_CAPABILITY_ID
    ):
        raise ValueError(
            "Social-acceptance renderer received the wrong capability identity"
        )
    state_label, state_color, state_icon = _workspace_availability_presentation(
        readiness.state
    )
    st.badge(_t(state_label), color=state_color, icon=state_icon)
    st.caption(_t(readiness.detail))
    if readiness.interaction != "interactive":
        _clear_workspace_social_acceptance_state(identity)
        with st.form(
            workspace_state_key(identity, "form"),
            clear_on_submit=False,
            enter_to_submit=False,
        ):
            st.checkbox(
                _t("Visa social acceptanslager"),
                value=False,
                key=workspace_state_key(identity, "capability"),
                disabled=True,
                help=_t('Orsak: {p0}.', p0=readiness.state),
                persist_state="session",
            )
            st.selectbox(
                _t("Acceptansscenario"),
                options=(_t("Saknas i manifestet"),),
                key=workspace_state_key(identity, "disabled_scenario"),
                disabled=True,
                persist_state="session",
            )
            st.slider(
                _t("Acceptanspåverkan"),
                min_value=0,
                max_value=100,
                value=0,
                step=5,
                format="%d%%",
                key=workspace_state_key(identity, "disabled_impact"),
                disabled=True,
                persist_state="session",
            )
            st.slider(
                _t("Acceptansstyrning av scenarioyta inom potentialen"),
                min_value=0,
                max_value=100,
                value=0,
                step=5,
                format="%d%%",
                key=workspace_state_key(identity, "disabled_priority"),
                disabled=True,
                persist_state="session",
            )
            st.form_submit_button(
                _t("Använd ändringar"),
                key=workspace_state_key(identity, "apply"),
                disabled=True,
                width="stretch",
            )
        st.caption(
            _t("Social acceptans förblir låst tills regionen deklarerar och "
            "validerar sitt eget datakontrakt.")
        )
        return None, False

    try:
        contract = load_catalog_social_acceptance_contract(identity.region_id)
        request = _ensure_workspace_social_acceptance_request(
            identity,
            contract,
            target_resolution=target_resolution,
        )
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ) as exc:
        st.error(
            _t("Det sparade acceptansvalet kunde inte valideras. Ingen äldre "
            "state eller fallback används.")
        )
        st.caption(_t('Teknisk orsak: {p0}', p0=exc))
        st.button(
            _t("Nollställ social acceptans"),
            key=workspace_state_key(identity, "reset"),
            icon=":material/filter_alt_off:",
            width="stretch",
            on_click=_reset_workspace_social_acceptance_state,
            args=(identity,),
        )
        return None, False

    _prime_workspace_social_acceptance_draft(identity, contract, request)
    layer_key = _workspace_draft_key(identity, "layer_visible")
    scenario_key = _workspace_draft_key(identity, "scenario")
    impact_key = _workspace_draft_key(identity, "impact_pct")
    priority_key = _workspace_draft_key(
        identity,
        "allocation_priority_pct",
    )
    scenarios = {item.scenario_id: item for item in contract.scenarios}
    format_text = _language_formatter()
    with st.form(
        workspace_state_key(identity, "form"),
        clear_on_submit=False,
        enter_to_submit=False,
    ):
        st.checkbox(
            _t("Visa social acceptanslager"),
            key=layer_key,
            persist_state="session",
        )
        _render_localized_choice(
            _t("Acceptansscenario"),
            options=tuple(scenarios),
            key=scenario_key,
            format_func=lambda value: format_text(_model_level_source(scenarios[str(value)].label)),
            persist_state="session",
        )
        st.slider(
            _t("Acceptanspåverkan"),
            min_value=float(contract.impact_control.minimum),
            max_value=float(contract.impact_control.maximum),
            step=float(contract.impact_control.step),
            format="%.0f%%",
            key=impact_key,
            help=_t(contract.impact_control.recommendation_reason),
            persist_state="session",
        )
        st.slider(
            _t("Acceptansstyrning av scenarioyta inom potentialen"),
            min_value=float(contract.allocation_priority_control.minimum),
            max_value=float(contract.allocation_priority_control.maximum),
            step=float(contract.allocation_priority_control.step),
            format="%.0f%%",
            key=priority_key,
            help=_t(contract.allocation_priority_control.recommendation_reason),
            persist_state="session",
        )
        submitted = st.form_submit_button(
            _t("Använd ändringar"),
            key=workspace_state_key(identity, "apply"),
            type="primary",
            width="stretch",
            on_click=_clear_ui_only_rerun,
        )
    st.button(
        _t("Nollställ social acceptans"),
        key=workspace_state_key(identity, "reset"),
        icon=":material/filter_alt_off:",
        width="stretch",
        on_click=_reset_workspace_social_acceptance_state,
        args=(identity,),
    )
    if not submitted:
        return request, False

    try:
        submitted_request = build_social_acceptance_request_from_contract(
            contract,
            access_scope=identity.access_scope,
            layer_visible=bool(st.session_state[layer_key]),
            scenario_id=str(st.session_state[scenario_key]),
            target_resolution=target_resolution,
            impact_pct=float(st.session_state[impact_key]),
            allocation_priority_pct=float(st.session_state[priority_key]),
        )
        submitted_result = _workspace_social_acceptance_result(
            submitted_request
        )
        if submitted_result is None or submitted_result.request != submitted_request:
            raise ValueError(
                "Social-acceptance executor did not return the submitted request"
            )
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ) as exc:
        st.error(
            _t("Acceptansändringarna kunde inte bindas till manifestet. Det "
            "senast tillämpade valet behålls.")
        )
        st.caption(_t('Teknisk orsak: {p0}', p0=exc))
        return request, False

    if submitted_request == request:
        _request_ui_only_rerun("unchanged controls applied")
        return submitted_request, False
    previous_calculation = (
        _social_acceptance_calculation_request_payload(request)
        if request is not None
        else None
    )
    st.session_state[_workspace_applied_request_key(identity)] = (
        submitted_request.as_dict()
    )
    if (
        previous_calculation is not None
        and previous_calculation
        == _social_acceptance_calculation_request_payload(submitted_request)
    ):
        _request_ui_only_rerun("social acceptanslager")
    else:
        _invalidate_workspace_cache("social-acceptance controls applied")
    return submitted_request, True


def _render_workspace_social_acceptance_result_summary(
    result: SocialAcceptanceResult,
) -> None:
    """Render only claims carried by the immutable result."""

    if result.source_status == "provisional_fallback":
        st.badge(
            _t("Provisorisk datakälla"),
            color="orange",
            icon=":material/warning:",
        )
    st.caption(
        _t('Valt: {p0} · bedömda celler {p1:,} av {p2:,}.', p0=_t(_model_level_source(result.scenario_label)), p1=result.assessed_cell_count, p2=result.coverage_target_support_hex_count).replace(",", " ")
    )
    with st.expander(
        _t(":material/warning: Källstatus och begränsningar"),
        expanded=False,
    ):
        st.caption(source_warning(result, _language()))
        st.caption(
            _t('Status: {p0} · användning: {p1} · regionalt accepterad: {p2}.', p0=_t(result.source_status), p1=_t(result.allowed_use), p2=_t('ja') if result.regional_acceptance else _t('nej'))
        )
        st.caption(
            _t('Källa: {p0} (`{p1}`).', p0=result.source_label, p1=result.source_dataset_id)
        )
        st.caption(_t(result.method_note))
        st.caption(_t(result.provenance))
        st.caption(_t(result.limitation))
        st.caption(_t('Ersättningsvillkor: {p0}', p0=_t(result.replacement_condition)))


def _render_applied_workspace_social_acceptance(
    request: SocialAcceptanceRequest | None,
) -> SocialAcceptanceResult | None:
    if request is None:
        st.caption(
            _t("Inget acceptansval är tillämpat. Gör färdigt formuläret och "
            "välj Använd ändringar.")
        )
        return None
    try:
        result = _workspace_social_acceptance_result(request)
        if result is None:
            raise ValueError("Applied social-acceptance request returned no result")
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ) as exc:
        st.error(
            _t("Det tillämpade acceptansvalet kunde inte köras. Ingen äldre "
            "state eller regional fallback används.")
        )
        st.caption(_t('Teknisk orsak: {p0}', p0=exc))
        return None
    _render_workspace_social_acceptance_result_summary(result)
    return result


def _workspace_social_acceptance_map_layer(
    result: SocialAcceptanceResult | None,
) -> dict[str, Any] | None:
    """Build the optional map overlay from the exact typed result cells."""

    if result is None or not result.request.layer_visible:
        return None
    validated = parse_social_acceptance_result(result.as_dict())
    if validated != result:
        raise ValueError("SocialAcceptanceResult changed during map validation")
    if any(
        h3.get_resolution(cell.cell_id) != result.request.target_resolution
        for cell in result.cells
    ):
        raise ValueError(
            "SocialAcceptanceResult map cells differ from target_resolution"
        )
    wind_domain_ids = set(
        technology_support_domain_cell_areas_km2(
            result.request.region_id,
            "wind",
            result.request.target_resolution,
        )
    )
    solar_domain_ids = set(
        technology_support_domain_cell_areas_km2(
            result.request.region_id,
            "solar",
            result.request.target_resolution,
        )
    )
    result_cell_ids = {cell.cell_id for cell in result.cells}
    if (
        wind_domain_ids != solar_domain_ids
        or len(wind_domain_ids)
        != result.coverage_target_support_hex_count
        or not result_cell_ids.issubset(wind_domain_ids)
    ):
        raise ValueError(
            "SocialAcceptanceResult cells do not match the current shared "
            "technology-support map domain"
        )
    features: list[dict[str, Any]] = []
    for cell in result.cells:
        if cell.acceptance_value < result.low_threshold:
            class_label, fill = "Låg acceptans", "#dc2626"
        elif cell.acceptance_value >= result.high_threshold:
            class_label, fill = "Hög acceptans", "#16a34a"
        else:
            class_label, fill = "Mellanacceptans", "#eab308"
        boundary = h3.cell_to_boundary(cell.cell_id)
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[float(lng), float(lat)] for lat, lng in boundary]
                        + [[float(boundary[0][1]), float(boundary[0][0])]]
                    ],
                },
                "properties": {
                    "hex_id": cell.cell_id,
                    "acceptance_value": cell.acceptance_value,
                    "potential_weight": cell.potential_weight,
                    "data_status": cell.data_status,
                    "fill": fill,
                    "stroke": "#ffffff",
                    "tooltip_title": f"Social acceptans · {class_label}",
                    "tooltip_body": (
                        f"{result.scenario_label}: "
                        f"{cell.acceptance_value:.3f}"
                    ),
                    "popup": (
                        "<strong>Social acceptans</strong><br>"
                        f"Scenario: {html.escape(result.scenario_label)}<br>"
                        f"Värde: {cell.acceptance_value:.3f}<br>"
                        f"Datastatus: {html.escape(cell.data_status)}"
                    ),
                },
            }
        )
    return {
        "name": f"Social acceptans: {result.scenario_label}",
        "feature_collection": {
            "type": "FeatureCollection",
            "features": features,
        },
        "fill_property": "fill",
        "stroke_property": "stroke",
        "legend_items": [
            {"label": "Låg acceptans", "color": "#dc2626"},
            {"label": "Mellanacceptans", "color": "#eab308"},
            {"label": "Hög acceptans", "color": "#16a34a"},
        ],
        "legend_id": "social_acceptance",
        "legend_title": "Social acceptans",
        "default_visible": True,
        "fill_opacity": 0.48,
        "stroke_opacity": 0.35,
        "weight": 0.4,
        "z_index": 468,
        "layer_kind": "hex",
    }


def _workspace_landscape_readiness(
    region_id: str,
    review_readiness: WorkspaceReviewReadiness | None,
    access_readiness: WorkspaceAccessReadiness,
) -> WorkspaceCapabilityReadiness:
    """Resolve the same non-group capability for product and review."""

    return _workspace_capability_readiness(
        region_id, LANDSCAPE_CAPABILITY_ID, review_readiness, access_readiness,
    )


def _validate_cached_landscape_result_immutability(
    result: LandscapeViewResult,
) -> None:
    """Admit only the exact immutable result graph to the shared resource cache."""

    field_names = {
        cls: tuple(field.name for field in fields(cls))
        for cls in (
            LandscapeViewResult, LandscapeViewRequest,
            LandscapeViewCell, LandscapeLegendItem,
        )
    }
    scalar_types = {str, int, bool, type(None)}
    pending: list[Any] = [result]
    while pending:
        value = pending.pop()
        value_type = type(value)
        if value_type in scalar_types:
            continue
        if value_type is tuple:
            pending.extend(value)
        elif value_type in field_names:
            pending.extend(getattr(value, name) for name in field_names[value_type])
        else:
            raise TypeError("Cached landscape result must be recursively immutable")


@st.cache_resource(show_spinner=False, max_entries=24, ttl=300)
def _cached_workspace_landscape_result(
    request_json: str,
) -> LandscapeViewResult:
    """Validate once and retain an immutable, scope- and contract-bound result."""

    raw_request = json.loads(request_json)
    request = parse_landscape_view_request(raw_request)
    result = parse_landscape_view_result(
        build_catalog_landscape_view(request).as_dict()
    )
    _validate_cached_landscape_result_immutability(result)
    return result


def _workspace_landscape_result(
    request: LandscapeViewRequest | None,
) -> LandscapeViewResult | None:
    if request is None:
        return None
    request_json = json.dumps(
        request.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    result = _cached_workspace_landscape_result(request_json)
    if result.request != request:
        raise ValueError("Landscape result does not match the applied request")
    return result


def _workspace_landscape_map_layer(
    result: LandscapeViewResult,
) -> dict[str, Any]:
    """Adapt the strict display result to the one shared map renderer."""

    feature_collection = json.loads(result.feature_collection_json)
    if (
        not isinstance(feature_collection, dict)
        or feature_collection.get("type") != "FeatureCollection"
        or not isinstance(feature_collection.get("features"), list)
    ):
        raise ValueError("Landscape result is not a GeoJSON FeatureCollection")
    styled_features: list[dict[str, Any]] = []
    for raw_feature in feature_collection["features"]:
        if not isinstance(raw_feature, dict):
            raise ValueError("Landscape result contains an invalid GeoJSON feature")
        feature = dict(raw_feature)
        properties = dict(feature.get("properties") or {})
        cell_id = str(properties.get("cell_id") or "")
        label = str(properties.get("label") or result.missing_label)
        value_id = properties.get("value_id")
        value_text = (
            f"{html.escape(str(value_id))} · {html.escape(label)}"
            if value_id is not None
            else html.escape(label)
        )
        properties.update(
            {
                "hex_id": cell_id,
                "landscape_fill": str(properties.get("color") or "#9ca3af"),
                "tooltip_title": html.escape(result.view_label),
                "tooltip_body": value_text,
                "popup": (
                    f"<strong>{html.escape(result.view_label)}</strong><br>"
                    f"H3: {html.escape(cell_id)}<br>"
                    f"{value_text}<br>"
                    "<em>Visnings- och granskningslager; används inte "
                    "numeriskt.</em>"
                ),
            }
        )
        feature["properties"] = properties
        styled_features.append(feature)

    legend_items = [
        {
            "label": item.label,
            "color": item.color,
        }
        for item in result.legend
    ]
    if result.not_assessed_cell_count:
        legend_items.append(
            {"label": result.missing_label, "color": "#9ca3af"}
        )
    layer_name = (
        f"{result.landscape_label} · {result.view_label} · "
        f"R{result.request.target_resolution}"
    )
    return {
        "name": layer_name,
        "feature_collection": {
            "type": "FeatureCollection",
            "features": styled_features,
        },
        "fill_property": "landscape_fill",
        "legend_items": legend_items,
        "legend_id": (
            f"workspace_landscape_{result.request.landscape_id}_"
            f"{result.request.view_id}"
        ),
        "legend_title": result.view_label,
        "legend_note": (
            "Manifestbundet visningslager; används inte i beräkningen."
        ),
        "default_visible": True,
        "stroke": True,
        "stroke_color": "#ffffff",
        "stroke_opacity": 0.45,
        "fill_opacity": 0.64,
        "weight": 0.25,
        "z_index": 445,
        "layer_kind": "hex",
        "opacity_family": layer_name,
        "opacity_label": layer_name,
    }


def _workspace_landscape_family_layers(
    identity: WorkspaceUiIdentity,
    readiness: WorkspaceCapabilityReadiness,
    region: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build one map-controlled LT family with no duplicate sidebar state."""

    if readiness.capability_id != LANDSCAPE_CAPABILITY_ID:
        raise ValueError("Landscape readiness has the wrong capability identity")
    if readiness.interaction not in {"read_only", "interactive"}:
        return []
    contract = load_landscape_contract(identity.region_id)
    allowed_resolutions = {
        int(contract.source.resolution),
        *(int(value) for value in contract.rollup_resolutions),
    }
    family_resolutions = [
        int(value)
        for value in _zoom_family_resolutions(region)
        if int(value) in allowed_resolutions
    ]
    if not family_resolutions:
        return []
    view_label = next(
        view.label
        for view in contract.views
        if view.view_id == contract.default_view_id
    )

    def build_layer(resolution: int) -> dict[str, Any] | None:
        request = build_landscape_view_request_from_contract(
            contract,
            access_scope=identity.access_scope,
            view_id=contract.default_view_id,
            target_resolution=int(resolution),
        )
        result = _workspace_landscape_result(request)
        if result is None:
            return None
        layer = _workspace_landscape_map_layer(result)
        layer["default_visible"] = bool(
            identity.access_kind == "product"
            and contract.product_default_visible
        )
        return layer

    return _hex_family_layers(
        region,
        _zoom_family_base_resolution(region),
        True,
        (
            f"workspace_landscape_{contract.landscape_id}_"
            f"{contract.default_view_id}"
        ),
        view_label,
        build_layer,
        family_resolutions=family_resolutions,
    )


def _workspace_rooftop_readiness(
    region_id: str,
    review_readiness: WorkspaceReviewReadiness | None,
    access_readiness: WorkspaceAccessReadiness,
) -> WorkspaceCapabilityReadiness:
    """Resolve the same rooftop capability for product and review."""

    return _workspace_capability_readiness(
        region_id, ROOFTOP_CAPABILITY_ID, review_readiness, access_readiness,
    )


def _clear_workspace_rooftop_state(identity: WorkspaceUiIdentity) -> None:
    """Clear only one region/access/solar.rooftop namespace."""

    prefix = workspace_state_prefix(identity)
    for key in tuple(st.session_state):
        if str(key).startswith(prefix):
            st.session_state.pop(key, None)


def _read_applied_workspace_rooftop_selection(
    identity: WorkspaceUiIdentity,
) -> RooftopSelectionRequest | None:
    """Read strict applied rooftop state without a compatibility fallback."""

    raw = st.session_state.get(_workspace_applied_request_key(identity))
    if raw is None:
        return None
    selection = parse_rooftop_selection(raw)
    contract = load_catalog_rooftop_contract(identity.region_id)
    validate_rooftop_selection_from_contract(contract, selection)
    if (
        identity.scope_id != ROOFTOP_CAPABILITY_ID
        or selection.region_id != identity.region_id
        or selection.access_scope != identity.access_scope
        or selection.capability_id != ROOFTOP_CAPABILITY_ID
    ):
        raise ValueError(
            "Applied rooftop selection does not match its workspace UI identity"
        )
    return selection


def _ensure_workspace_rooftop_selection(
    identity: WorkspaceUiIdentity,
) -> RooftopSelectionRequest | None:
    """Create only the explicit inactive product default; review stays empty."""

    selection = _read_applied_workspace_rooftop_selection(identity)
    if selection is not None or not _workspace_uses_complete_runtime(identity):
        return selection
    contract = load_catalog_rooftop_contract(identity.region_id)
    selection = build_rooftop_selection_from_contract(
        contract,
        access_scope=identity.access_scope,
        enabled=False,
        panel_area_m2_per_person=float(
            contract.rooftop.panel_area_m2_per_person.default
        ),
    )
    st.session_state[_workspace_applied_request_key(identity)] = (
        selection.as_dict()
    )
    return selection


def _prime_workspace_rooftop_draft(
    identity: WorkspaceUiIdentity,
    selection: RooftopSelectionRequest | None,
) -> None:
    """Initialize rooftop draft widgets without overwriting unsent edits."""

    contract = load_catalog_rooftop_contract(identity.region_id)
    st.session_state.setdefault(
        _workspace_draft_key(identity, "enabled"),
        bool(selection.enabled) if selection is not None else False,
    )
    st.session_state.setdefault(
        _workspace_draft_key(
            identity,
            "parameter",
            "panel_area_m2_per_person",
        ),
        float(
            selection.panel_area_m2_per_person
            if selection is not None
            else contract.rooftop.panel_area_m2_per_person.default
        ),
    )


def _reset_workspace_rooftop_state(identity: WorkspaceUiIdentity) -> None:
    """Reset only rooftop selection, draft, and preview state before rerun."""

    _clear_workspace_rooftop_state(identity)
    _invalidate_workspace_cache("rooftop solar controls reset")
    _request_ui_only_rerun("taksol nollställd")


@st.cache_data(show_spinner=False, max_entries=32)
def _cached_catalog_rooftop_result(
    request_json: str,
) -> RooftopCapabilityResult:
    """Run one immutable typed rooftop request behind a bounded data cache."""

    request = parse_rooftop_request(json.loads(request_json))
    return run_catalog_rooftop_request(request)


def _workspace_rooftop_result(
    selection: RooftopSelectionRequest | None,
    *,
    scenario_result: ScenarioResult,
    domain_resolution: int | None = None,
) -> RooftopCapabilityResult | RooftopUnavailableResult:
    """Rebuild execution from applied selection and the current scenario."""

    if selection is None:
        analysis = load_delivery_analysis(scenario_result.request.region_id, "solar")
        return build_unavailable_rooftop_result(analysis, access_scope=scenario_result.request.access_scope)
    contract = load_catalog_rooftop_contract(selection.region_id)
    scenario_contract = load_catalog_scenario_contract(selection.region_id)
    validate_scenario_result_from_contract(scenario_contract, scenario_result)
    if (
        scenario_result.request.region_id != selection.region_id
        or scenario_result.request.access_scope != selection.access_scope
    ):
        raise ValueError(
            "Rooftop selection and ScenarioResult belong to different scopes"
        )
    solar_result = scenario_result.technology_result("solar")
    request = build_rooftop_request_from_selection(
        contract,
        selection,
        gross_solar_target_twh=solar_result.energy_twh,
        ground_km2_per_twh=solar_result.km2_per_twh,
        domain_resolution=domain_resolution,
    )
    request_json = json.dumps(
        request.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    result = _cached_catalog_rooftop_result(request_json)
    if result.request != request:
        raise ValueError("Rooftop result does not match its current execution request")
    return result


def _validate_workspace_rooftop_selection_execution(
    selection: RooftopSelectionRequest,
    *,
    domain_resolution: int | None = None,
) -> RooftopCapabilityResult:
    """Probe only provider-backed rooftop selection inputs before Apply."""

    contract = load_catalog_rooftop_contract(selection.region_id)
    request = build_rooftop_request_from_selection(
        contract,
        selection,
        gross_solar_target_twh=0.0,
        ground_km2_per_twh=0.0,
        domain_resolution=domain_resolution,
    )
    request_json = json.dumps(
        request.as_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    result = _cached_catalog_rooftop_result(request_json)
    if result.request != request:
        raise ValueError("Rooftop selection probe returned a stale request")
    return result


def _render_workspace_rooftop_controls(
    identity: WorkspaceUiIdentity,
    readiness: WorkspaceCapabilityReadiness,
) -> tuple[RooftopSelectionRequest | None, bool]:
    """Render one manifest-bound rooftop form for product or review."""

    if (
        identity.scope_id != ROOFTOP_CAPABILITY_ID
        or readiness.capability_id != ROOFTOP_CAPABILITY_ID
    ):
        raise ValueError("Rooftop renderer received the wrong capability identity")
    state_label, state_color, state_icon = _workspace_availability_presentation(
        readiness.state
    )
    st.badge(_t(state_label), color=state_color, icon=state_icon)
    st.caption(_t(readiness.detail))

    if readiness.interaction != "interactive":
        _clear_workspace_rooftop_state(identity)
        st.checkbox(
            _t(SOLAR_SMALL_SCALE_LABEL),
            value=False,
            key=workspace_state_key(identity, "capability"),
            disabled=True,
            help=_t('Orsak: {p0}.', p0=readiness.state),
            persist_state="session",
        )
        return None, False

    try:
        contract = load_catalog_rooftop_contract(identity.region_id)
        selection = _ensure_workspace_rooftop_selection(identity)
        review = contract.rooftop.map_review
        group_contract = _solar_manifest_group_contract(
            identity.region_id,
            SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID,
            review.canonical_group_id,
        )
        layers_by_id = {layer.id: layer for layer in group_contract.layers}
        source_layers = [layers_by_id[layer_id] for layer_id in review.layer_ids]
        if len(source_layers) != len(review.layer_ids) or any(
            not layer.ready for layer in source_layers
        ):
            raise ValueError(
                "Rooftop map review references unavailable manifest sources"
            )
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ) as exc:
        st.error(
            _t("Det sparade taksolvalet kunde inte valideras. "
            "Ingen beräkning eller fallback används.")
        )
        st.caption(_t('Teknisk orsak: {p0}', p0=exc))
        st.button(
            _t("Nollställ taksol"),
            key=workspace_state_key(identity, "reset"),
            icon=":material/filter_alt_off:",
            width="stretch",
            on_click=_reset_workspace_rooftop_state,
            args=(identity,),
        )
        return None, False

    _prime_workspace_rooftop_draft(identity, selection)
    enabled_key = _workspace_draft_key(identity, "enabled")
    panel_key = _workspace_draft_key(
        identity,
        "parameter",
        "panel_area_m2_per_person",
    )
    panel_parameter = contract.rooftop.panel_area_m2_per_person
    population_label = " / ".join(layer.label for layer in source_layers)
    population_help = " ".join(layer.note for layer in source_layers)
    with st.form(workspace_state_key(identity, "form"), clear_on_submit=False):
        enabled = st.checkbox(
            _t(population_label),
            key=enabled_key,
            help=_t(population_help),
            persist_state="session",
        )
        st.slider(
            _solar_v1_panel_area_label({"region_id": identity.region_id}),
            min_value=float(panel_parameter.minimum),
            max_value=float(panel_parameter.maximum),
            step=float(panel_parameter.step),
            key=panel_key,
            format="%.0f m²/person",
            help=_solar_v1_formula_text(
                {"region_id": identity.region_id},
                float(
                    st.session_state.get(panel_key, panel_parameter.default)
                    or 0.0
                ),
            ),
            persist_state="session",
        )
        submitted = st.form_submit_button(
            _t("Använd ändringar för taksol"),
            type="primary",
            width="stretch",
            on_click=_clear_ui_only_rerun,
        )
    st.button(
        _t("Nollställ taksol"),
        key=workspace_state_key(identity, "reset"),
        icon=":material/filter_alt_off:",
        width="stretch",
        on_click=_reset_workspace_rooftop_state,
        args=(identity,),
    )
    if enabled:
        st.caption(_solar_v1_population_source_status({"region_id": identity.region_id}))
        st.info(
            _t('{p0} Småskalig sol är en schablon från befolkning per hex. Den visas som små gula schablonhexar, inte som faktiska takpolygoner eller sammanhängande markyta.', p0=population_help)
        )
    st.caption(
        _t("Kartlager: schablonhexar och gemensam potentiell etableringsyta.")
    )
    if not submitted:
        return selection, False

    try:
        submitted_selection = build_rooftop_selection_from_contract(
            contract,
            access_scope=identity.access_scope,
            enabled=bool(st.session_state.get(enabled_key, False)),
            panel_area_m2_per_person=float(
                st.session_state.get(panel_key, panel_parameter.default) or 0.0
            ),
        )
        # Apply is accepted only if the exact provider-backed executor can
        # replay the submitted selection. Scenario inputs are added later.
        _validate_workspace_rooftop_selection_execution(submitted_selection)
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ) as exc:
        st.error(
            _t("Taksoländringarna kunde inte bindas till manifestet. "
            "Det senast tillämpade valet behålls.")
        )
        st.caption(_t('Teknisk orsak: {p0}', p0=exc))
        return selection, False

    if submitted_selection == selection:
        _request_ui_only_rerun("unchanged controls applied")
        return submitted_selection, False
    st.session_state[_workspace_applied_request_key(identity)] = (
        submitted_selection.as_dict()
    )
    _invalidate_workspace_cache("rooftop solar controls applied")
    return submitted_selection, True


def _workspace_analysis_id(identity: WorkspaceUiIdentity) -> str:
    """Return a scope only when the active profile declares it as an analysis."""

    if not isinstance(identity, WorkspaceUiIdentity):
        raise TypeError("identity must be a WorkspaceUiIdentity")
    profile = load_workspace_profile(identity.region_id)
    if identity.scope_id not in profile.technologies:
        raise ValueError(
            "Workspace UI scope is not a profile-declared analysis: "
            f"{identity.scope_id!r}"
        )
    return identity.scope_id


def _workspace_applied_request_key(identity: WorkspaceUiIdentity) -> str:
    return workspace_state_key(identity, "applied_request")


def _workspace_draft_key(
    identity: WorkspaceUiIdentity,
    kind: str,
    *parts: str,
) -> str:
    return workspace_state_key(identity, "draft", kind, *parts)


def _read_applied_workspace_request(
    identity: WorkspaceUiIdentity,
) -> WorkspaceAnalysisRequest | None:
    """Read one namespaced applied request without compatibility fallback."""

    analysis_id = _workspace_analysis_id(identity)
    raw = st.session_state.get(_workspace_applied_request_key(identity))
    if raw is None:
        return None
    request = parse_workspace_analysis_request(raw)
    contract = load_delivery_analysis(identity.region_id, analysis_id)
    validate_workspace_analysis_request_from_contract(contract, request)
    authorize_catalog_workspace_analysis_request(request)
    if (
        request.region_id != identity.region_id
        or request.analysis_id != analysis_id
        or request.access_scope != identity.access_scope
    ):
        raise ValueError("Applied request does not match its workspace UI identity")
    return request


def _reset_workspace_analysis_state(
    identity: WorkspaceUiIdentity,
) -> None:
    """Clear only one region/access/analysis namespace before rerun."""

    analysis_id = _workspace_analysis_id(identity)
    prefix = workspace_state_prefix(identity)
    for key in tuple(st.session_state):
        if str(key).startswith(prefix):
            st.session_state.pop(key, None)
    _invalidate_workspace_cache(
        f"{analysis_id} workspace controls reset"
    )


def _clear_workspace_analysis_filters(
    identity: WorkspaceUiIdentity,
    access_readiness: WorkspaceAccessReadiness,
) -> None:
    """Apply an explicit unfiltered request before widgets are recreated."""

    analysis_id = _workspace_analysis_id(identity)
    controls = analysis_group_controls(identity.region_id, analysis_id)
    request = _workspace_request_from_draft(
        identity,
        {str(control.id): control for control in controls},
        {},
        access_readiness,
    )
    authorize_catalog_workspace_analysis_request(request)
    for control in controls:
        group_id = str(control.id)
        for kind in ("group", "group_sync"):
            st.session_state[_workspace_draft_key(identity, kind, group_id)] = False
        for layer in control.layers:
            st.session_state[
                _workspace_draft_key(identity, "layer", group_id, str(layer.id))
            ] = False
    st.session_state[_workspace_applied_request_key(identity)] = request.as_dict()
    _invalidate_workspace_cache(f"{analysis_id} filters removed")


def _source_control_help(layer: Any) -> str:
    """Localize authored help separately from a verbatim technical exception."""
    message = str(layer.message or layer.note or "")
    note, marker, technical_detail = message.partition(" Datakällan är inte redo: ")
    if marker:
        return _t(note) + " " + _t("Datakällan är inte redo: {p0}", p0=technical_detail)
    return _t(message)


def _workspace_filter_group_control(
    identity: WorkspaceUiIdentity,
    group: WindGroupControlContract,
) -> FilterGroupControl:
    """Adapt one typed manifest group to the common native form model."""

    _workspace_analysis_id(identity)
    sources = tuple(
        FilterSourceControl(
            id=str(layer.id),
            label=(
                f"{_t(layer.label)} :orange[:material/warning:]"
                if layer.quality_flag == "caution"
                else _t(layer.label)
            ),
            key=_workspace_draft_key(
                identity,
                "layer",
                str(group.id),
                str(layer.id),
            ),
            ready=bool(layer.ready),
            help_text=_source_control_help(layer),
        )
        for layer in group.layers
    )
    return filter_group_control(
        group_id=str(group.id),
        label=_t(group.label),
        interpretation=_t(group.interpretation),
        analysis_label=_t(group.analysis_label),
        analysis_min_m=int(group.analysis_min_m),
        analysis_max_m=int(group.analysis_max_m),
        analysis_step_m=int(group.analysis_step_m),
        analysis_key=_workspace_draft_key(
            identity,
            "parameter",
            str(group.id),
            "buffer_m",
        ),
        analysis_help=ui_text("analysis_slider_help", _wind_control_language()),
        sources=sources,
    )


def _workspace_request_from_draft(
    identity: WorkspaceUiIdentity,
    controls: Mapping[str, WindGroupControlContract],
    selected_group_layers: Mapping[str, list[str]],
    access_readiness: WorkspaceAccessReadiness,
    *,
    target_resolution: int | None = None,
) -> WorkspaceAnalysisRequest:
    """Bind submitted native controls to one exact analysis contract."""

    analysis_id = _workspace_analysis_id(identity)
    if (
        access_readiness.region_id != identity.region_id
        or access_readiness.access_scope != identity.access_scope
    ):
        raise ValueError("Workspace controls and access readiness do not match")
    contract = load_delivery_analysis(identity.region_id, analysis_id)
    selected = {
        group_id: tuple(selected_group_layers.get(group_id) or ())
        for group_id in contract.groups
        if selected_group_layers.get(group_id)
    }
    policy_by_group = {
        str(item.policy.group_id): item.policy
        for item in access_readiness.analysis_slices(
            analysis_id,
            interactive_only=True,
        )
        if bool(item.policy.apply_required)
    }
    rejected = set(selected) - set(policy_by_group)
    if rejected:
        raise ValueError(
            "Workspace request selected groups outside its access contract: "
            f"{sorted(rejected)}"
        )

    group_parameters: dict[str, dict[str, float]] = {}
    for group_id, layer_ids in selected.items():
        control = controls.get(group_id)
        if control is None:
            raise ValueError(
                f"{identity.region_id}/{analysis_id} has no UI "
                f"control for {group_id}"
            )
        parameter_ids = tuple(contract.layers[layer_ids[0]].parameters)
        if len(parameter_ids) != 1:
            raise ValueError(
                f"{identity.region_id}/{analysis_id} {group_id} "
                "does not match the shared single-parameter control"
            )
        parameter_id = parameter_ids[0]
        policy = policy_by_group.get(group_id)
        if (
            policy is None
            or tuple(policy.explicit_parameters) != parameter_ids
        ):
            raise ValueError(
                f"Workspace request parameters do not match "
                f"{analysis_id}/{group_id}"
            )
        group_parameters[group_id] = {
            parameter_id: float(
                st.session_state.get(
                    _workspace_draft_key(
                        identity,
                        "parameter",
                        group_id,
                        parameter_id,
                    ),
                    control.analysis_default_m,
                )
            )
        }

    request = build_workspace_analysis_request_from_contract(
        contract,
        access_scope=identity.access_scope,
        selected_group_layers=selected,
        group_parameters=group_parameters,
        target_resolution=target_resolution,
    )
    if request.groups or _workspace_uses_complete_runtime(identity):
        authorize_catalog_workspace_analysis_request(request)
    return request


def _prime_workspace_analysis_draft(
    identity: WorkspaceUiIdentity,
    controls: tuple[WindGroupControlContract, ...],
    applied_request: WorkspaceAnalysisRequest | None,
) -> None:
    """Create widget defaults once without overwriting a user's draft."""

    _workspace_analysis_id(identity)
    selected = {
        group.group_id: set(group.layer_ids)
        for group in (applied_request.groups if applied_request else ())
    }
    parameters = {
        group.group_id: group.parameter_map()
        for group in (applied_request.groups if applied_request else ())
    }
    for control in controls:
        group_id = str(control.id)
        group_selected = bool(selected.get(group_id))
        st.session_state.setdefault(
            _workspace_draft_key(identity, "group", group_id),
            group_selected,
        )
        st.session_state.setdefault(
            _workspace_draft_key(identity, "group_sync", group_id),
            group_selected,
        )
        for layer in control.layers:
            st.session_state.setdefault(
                _workspace_draft_key(
                    identity,
                    "layer",
                    group_id,
                    str(layer.id),
                ),
                str(layer.id) in selected.get(group_id, set()),
            )
        parameter_value = parameters.get(group_id, {}).get(
            "buffer_m",
            float(control.analysis_default_m),
        )
        st.session_state.setdefault(
            _workspace_draft_key(
                identity,
                "parameter",
                group_id,
                "buffer_m",
            ),
            int(parameter_value),
        )


def _workspace_uses_complete_runtime(identity: WorkspaceUiIdentity) -> bool:
    return identity.access_kind == "product" or catalog_context_runtime_declared(identity.region_id)


def _ensure_workspace_analysis_request(
    identity: WorkspaceUiIdentity,
    access_readiness: WorkspaceAccessReadiness,
    controls: tuple[WindGroupControlContract, ...] | None = None,
) -> WorkspaceAnalysisRequest | None:
    """Create the product default or the explicitly configured review selection."""

    analysis_id = _workspace_analysis_id(identity)
    applied_request = _read_applied_workspace_request(identity)
    if applied_request is not None or not _workspace_uses_complete_runtime(identity):
        return applied_request
    resolved_controls = controls or analysis_group_controls(
        identity.region_id,
        analysis_id,
    )
    control_by_id = {
        str(control.id): control for control in resolved_controls
    }
    contract = load_delivery_analysis(
        identity.region_id,
        analysis_id,
    )
    default_layer_ids = tuple(
        contract.default_request.selected_layer_ids
        if contract.default_request is not None
        else ()
    )
    if (
        identity.access_kind == "review"
        and catalog_context_runtime_declared(identity.region_id)
    ):
        selectable_groups = {
            str(item.bundle.group_id): item.policy
            for item in access_readiness.analysis_slices(analysis_id)
            if item.interaction == "interactive" and item.policy.auto_select_sources
        }
        default_layer_ids = tuple(dict.fromkeys([
            *default_layer_ids,
            *(layer.id for control in resolved_controls if control.id in selectable_groups
              for layer in control.layers if layer.ready
              and selectable_groups[control.id].selects_source_by_default(layer.id)),
        ]))
    default_selected: dict[str, list[str]] = {}
    for layer_id in default_layer_ids:
        layer = contract.layers.get(layer_id)
        if layer is None:
            raise ValueError(
                f"Default request references an unknown layer: {layer_id}"
            )
        default_selected.setdefault(layer.group_id, []).append(layer_id)
    start_parameters = load_workspace_start_parameters(contract)
    for group_id, value in start_parameters.items():
        st.session_state.setdefault(
            _workspace_draft_key(identity, "parameter", group_id, "buffer_m"),
            int(value),
        )
    applied_request = _workspace_request_from_draft(
        identity,
        control_by_id,
        default_selected,
        access_readiness,
    )
    st.session_state[_workspace_applied_request_key(identity)] = (
        applied_request.as_dict()
    )
    return applied_request


def _render_workspace_analysis_controls(
    identity: WorkspaceUiIdentity,
    access_readiness: WorkspaceAccessReadiness,
) -> tuple[WorkspaceAnalysisRequest | None, bool]:
    """Render a shared analysis form; report whether Apply changed its request."""

    analysis_id = _workspace_analysis_id(identity)
    if (
        access_readiness.region_id != identity.region_id
        or access_readiness.access_scope != identity.access_scope
    ):
        raise ValueError("Workspace controls received another access scope")
    availability = _workspace_access_group_availability(
        access_readiness,
        analysis_id,
    )
    controls = analysis_group_controls(
        identity.region_id,
        analysis_id,
    )
    control_by_id = {str(control.id): control for control in controls}
    availability_by_group = {
        str(item.capability_id).removeprefix(
            f"{analysis_id}.group."
        ): item
        for item in availability
    }
    applied_request = _ensure_workspace_analysis_request(
        identity,
        access_readiness,
        controls,
    )
    interactive_group_ids = {
        str(item.capability_id).removeprefix(
            f"{analysis_id}.group."
        )
        for item in availability
        if item.interaction == "interactive"
    }
    if applied_request is not None and any(
        group.group_id not in interactive_group_ids
        for group in applied_request.groups
    ):
        st.session_state.pop(_workspace_applied_request_key(identity), None)
        applied_request = None
        if identity.access_kind == "product":
            applied_request = _workspace_request_from_draft(
                identity,
                control_by_id,
                {},
                access_readiness,
            )
            st.session_state[_workspace_applied_request_key(identity)] = (
                applied_request.as_dict()
            )
    _prime_workspace_analysis_draft(identity, controls, applied_request)

    selected: dict[str, list[str]] = {
        group.id: [] for group in controls
    }
    filter_bindings: list[
        tuple[FilterGroupControl, str, str, tuple[str, ...], bool]
    ] = []
    count_slot = st.empty()
    form_key = workspace_state_key(identity, "form")
    apply_feedback_key = workspace_state_key(identity, "apply_feedback")
    with st.form(form_key, clear_on_submit=False):
        for item in availability:
            group_id = str(item.capability_id).removeprefix(
                f"{analysis_id}.group."
            )
            if item.interaction != "interactive":
                label, color, icon = _workspace_availability_presentation(
                    item.state
                )
                with st.expander(_t(item.label), expanded=False, key=workspace_state_key(identity, "group_panel", group_id)):
                    st.caption(_t(item.interpretation))
                    st.badge(_t(label), color=color, icon=icon)
                    st.caption(_t(item.detail))
                    st.checkbox(
                        _t('Använd {p0}', p0=_t(item.label).lower()),
                        value=False,
                        key=workspace_state_key(
                            identity,
                            "capability",
                            group_id,
                        ),
                        disabled=True,
                        help=_t('Orsak: {p0}.', p0=_t(label)),
                        persist_state="session",
                    )
                continue
            control_contract = control_by_id.get(group_id)
            if control_contract is None:
                raise ValueError(
                    f"{identity.region_id}/{analysis_id} has no "
                    f"declared control for interactive group {group_id}"
                )
            control = _workspace_filter_group_control(
                identity,
                control_contract,
            )
            group_key = _workspace_draft_key(
                identity,
                "group",
                group_id,
            )
            sync_key = _workspace_draft_key(
                identity,
                "group_sync",
                group_id,
            )
            slice_readiness = next(
                (
                    value
                    for value in access_readiness.analysis_slices(analysis_id)
                    if str(value.bundle.group_id) == group_id
                ),
                None,
            )
            if slice_readiness is None:
                raise ValueError(
                    f"Interactive group lacks an access slice: {group_id}"
                )
            auto_select_sources = bool(
                slice_readiness.policy.auto_select_sources
            )
            default_source_ids = (
                tuple(
                    source.id for source in control.sources
                    if source.ready
                    and slice_readiness.policy.selects_source_by_default(source.id)
                )
                if auto_select_sources
                else ()
            )
            auto_select_sources = auto_select_sources and bool(default_source_ids)
            filter_bindings.append(
                (
                    control,
                    group_key,
                    sync_key,
                    default_source_ids,
                    auto_select_sources,
                )
            )
            with st.expander(
                _t(control.label),
                expanded=bool(control_contract.expanded_by_default),
                key=workspace_state_key(identity, "group_panel", group_id),
            ):
                guide_target = {
                    ("wind", "nature"): "wind-nature",
                    ("wind", "grid_infrastructure"): "wind-grid-apply",
                }.get((analysis_id, group_id))
                if guide_target:
                    st.markdown(
                        f'<span data-workspace-guide="{guide_target}" data-workspace-guide-kind="panel"></span>',
                        unsafe_allow_html=True,
                    )
                selected[group_id] = _render_native_filter_group_control(
                    control,
                    group_key=group_key,
                    sync_key=sync_key,
                    default_source_ids=default_source_ids,
                    auto_select_sources=auto_select_sources,
                )
                if not selected[group_id]:
                    st.caption(ui_text("group_inactive", _wind_control_language()))
        submitted = st.form_submit_button(
            ui_text("apply_changes", _wind_control_language()),
            type="primary",
            width="stretch",
            on_click=_sync_filter_group_controls_on_apply,
            args=(tuple(filter_bindings), apply_feedback_key),
        )

    if _workspace_uses_complete_runtime(identity):
        st.button(
            _t("Ta bort alla vindfilter") if analysis_id == "wind"
            else _t("Ta bort alla solfilter"),
            key=workspace_state_key(identity, "clear_filters"),
            icon=":material/filter_alt_off:",
            width="stretch",
            on_click=_clear_workspace_analysis_filters,
            args=(identity, access_readiness),
        )
    st.button(
        _t("Återställ startvärden"),
        key=workspace_state_key(identity, "reset"),
        icon=":material/restart_alt:",
        width="stretch",
        on_click=_reset_workspace_analysis_state,
        args=(identity,),
    )
    if submitted:
        groups_missing_explicit_sources = tuple(
            str(value)
            for value in st.session_state.pop(apply_feedback_key, ())
            if str(value).strip()
        )
        try:
            submitted_request = _workspace_request_from_draft(
                identity,
                control_by_id,
                selected,
                access_readiness,
            )
        except (
            FileNotFoundError,
            KeyError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            st.error(
                _t("Ändringarna kunde inte bindas till analysmanifestet. "
                "Den senast tillämpade konfigurationen behålls.")
            )
            st.caption(_t('Teknisk orsak: {p0}', p0=exc))
            submitted = False
        else:
            if submitted_request == applied_request:
                _request_ui_only_rerun("unchanged controls applied")
                submitted = False
            elif submitted_request.groups or _workspace_uses_complete_runtime(identity):
                st.session_state[_workspace_applied_request_key(identity)] = (
                    submitted_request.as_dict()
                )
                applied_request = submitted_request
            else:
                st.session_state.pop(
                    _workspace_applied_request_key(identity),
                    None,
                )
                applied_request = None
                if groups_missing_explicit_sources:
                    group_labels = ", ".join(
                        groups_missing_explicit_sources
                    )
                    st.warning(
                        _t('Ingen datakälla valdes för {p0}. Öppna Datakällor i gruppen, välj minst en datakälla och tryck sedan på Använd ändringar.', p0=group_labels)
                    )
                else:
                    st.warning(
                        _t("Inga ändringar tillämpades. Välj minst en grupp och "
                        "minst en datakälla i gruppen innan du använder "
                        "ändringarna.")
                    )
            if submitted:
                _invalidate_workspace_cache(
                    f"{analysis_id} controls applied"
                )

    selected_count = (
        len(applied_request.selected_layer_ids)
        if applied_request is not None
        else 0
    )
    count_slot.caption(
        (
            _t("Välj minst en grupp och dess datakälla för att skapa ett "
            "tekniskt analysresultat.")
            if selected_count == 0 and applied_request is None
            else _t("Inga aktiva filter – hela analysdomänen visas.")
        )
        if selected_count == 0
        else _t('{p0} aktiva filter.', p0=selected_count)
    )
    return applied_request, bool(submitted)


def _missing_wind_controls(
    region: dict[str, Any],
    status_rows: list[dict[str, Any]],
    access_readiness: WorkspaceAccessReadiness,
) -> None:
    """Render unavailable and available groups through the shared form."""

    _ = status_rows
    region_id = str(region.get("region_id") or "").strip().lower()
    availability = _workspace_access_group_availability(
        access_readiness,
        "wind",
    )
    st.caption(
        _t("Vindpanelens struktur kommer från arbetsyteprofilen; regionens "
        "analysmanifest avgör lager och interaktion.")
    )
    st.caption(
        _t("De fem standardgrupperna kommer från den gemensamma arbetsyteprofilen. "
        "Endast grupper som både deklareras av regionen och klarar sin egen "
        "readiness-gate kan användas.")
    )
    if any(
        item.interaction == "interactive" for item in availability
    ):
        identity = _workspace_ui_identity(region_id, "wind")
        _render_workspace_analysis_controls(
            identity,
            access_readiness,
        )
        return
    identity = _workspace_ui_identity(region_id, "wind")
    for item in availability:
        label, color, icon = _workspace_availability_presentation(item.state)
        with st.expander(_t(item.label), expanded=False):
            st.caption(_t(item.interpretation))
            st.badge(_t(label), color=color, icon=icon)
            st.caption(_t(item.detail))
            st.checkbox(
                _t('Använd {p0}', p0=_t(item.label).lower()),
                value=False,
                key=workspace_state_key(
                    identity,
                    "capability",
                    item.capability_id.removeprefix("wind.group."),
                ),
                disabled=True,
                help=_t('Orsak: {p0}.', p0=_t(label)),
                persist_state="session",
            )


def _missing_solar_controls(
    region: dict[str, Any],
    access_readiness: WorkspaceAccessReadiness,
) -> RooftopSelectionRequest | None:
    region_id = str(region.get("region_id") or "").strip().lower()
    availability = _workspace_access_group_availability(
        access_readiness,
        "solar",
    )
    st.caption(
        _t("Solpanelen använder samma fem grupper från arbetsyteprofilen. "
        "Kontroller utan regionspecifikt manifest visas utan påhittade värden.")
    )
    rooftop_identity = _workspace_ui_identity(
        region_id,
        ROOFTOP_CAPABILITY_ID,
    )
    rooftop_selection = _ensure_workspace_rooftop_selection(rooftop_identity)
    identity = _workspace_ui_identity(region_id, "solar")
    if any(
        item.interaction == "interactive" for item in availability
    ):
        _render_workspace_analysis_controls(
            identity,
            access_readiness,
        )
        return rooftop_selection
    for item in availability:
        label, color, icon = _workspace_availability_presentation(item.state)
        with st.expander(_t(item.label), expanded=False):
            st.caption(_t(item.interpretation))
            st.badge(_t(label), color=color, icon=icon)
            st.caption(_t(item.detail))
            st.checkbox(
                _t('Använd {p0}', p0=_t(item.label).lower()),
                value=False,
                key=workspace_state_key(
                    identity,
                    "capability",
                    item.capability_id.removeprefix("solar.group."),
                ),
                disabled=True,
                help=_t('Orsak: {p0}.', p0=_t(label)),
                persist_state="session",
            )
    return rooftop_selection


def _missing_energy_controls(
    region: dict[str, Any],
    review_readiness: WorkspaceReviewReadiness | None,
    access_readiness: WorkspaceAccessReadiness,
) -> ScenarioResult | None:
    region_id = str(region.get("region_id") or "").strip().lower()
    identity = _workspace_ui_identity(region_id, SCENARIO_CAPABILITY_ID)
    readiness = _workspace_scenario_readiness(
        region_id,
        review_readiness,
        access_readiness,
    )
    request, applied = _render_workspace_scenario_controls(identity, readiness)
    if applied:
        st.rerun()
    result, _energy_state = _render_applied_workspace_scenario(
        request,
        h3_resolution=None,
        rooftop_selection=None,
    )
    combined_state = _review_capability_state(
        review_readiness,
        "workspace.combined_result",
        fallback="missing_manifest",
    )
    st.checkbox(
        _t("Visa föreslagen etableringsyta"),
        value=False,
        key="workspace_capability__workspace.combined_result",
        disabled=True,
        help=(
            _t('Status: {p0}. Gemensam resultatpresentation är inte aktiverad i den här granskningsytan.', p0=combined_state)
        ),
        persist_state="session",
    )
    if readiness.interaction != "interactive":
        st.info(
            _t("Energimodellering aktiveras först när regionen deklarerar och "
            "validerar scenario-, efterfråge- och teknikytkontrakten.")
        )
    return result


def _missing_potential_summary(label: str, missing_text: str) -> None:
    with st.expander(_t(label), expanded=False):
        left, right = st.columns(2)
        left.metric(_t("Medelpoäng"), "-")
        right.metric(_t("Hög potential"), "-")
        st.info(_t(missing_text))


def _render_missing_data_workspace(
    region: dict[str, Any],
    context: dict[str, Any],
    left_panel: Any | None,
    right_panel: Any | None,
    review_readiness: WorkspaceReviewReadiness | None = None,
    access_readiness: WorkspaceAccessReadiness | None = None,
    target_resolution: int | None = None,
) -> None:
    if access_readiness is None:
        raise ValueError("The shared workspace requires access readiness")
    status_rows = region_data_status_rows(region, context)
    review_status_rows = (
        _review_readiness_rows(review_readiness)
        if review_readiness is not None
        else []
    )
    displayed_status_rows = review_status_rows or status_rows
    missing_rows = (
        [
            row
            for row in review_status_rows
            if str(row.get("Årsagskode") or "")
            not in {
                "technically_validated",
                "regionally_accepted",
                "public",
            }
        ]
        if review_status_rows
        else [row for row in status_rows if str(row.get("status")) != "klar"]
    )
    region_label = str(region.get("display_name", region.get("region_id", "region")))
    is_local_review = review_readiness is not None
    region_id = str(region.get("region_id") or "").strip().lower()
    landscape_target_resolution = (
        int(target_resolution)
        if target_resolution is not None
        else
        _local_review_default_h3_resolution(region_id)
        if is_local_review
        else int(
            region.get("default_display_h3_resolution")
            or region.get("default_h3_resolution")
            or 8
        )
    )
    landscape_result: LandscapeViewResult | None = None
    scenario_result: ScenarioResult | None = None
    social_acceptance_result: SocialAcceptanceResult | None = None

    try:
        landscape_readiness = _workspace_landscape_readiness(
            region_id,
            review_readiness,
            access_readiness,
        )
        if landscape_readiness.interaction in {"read_only", "interactive"}:
            landscape_contract = load_landscape_contract(region_id)
            landscape_request = build_landscape_view_request_from_contract(
                landscape_contract,
                access_scope=access_readiness.access_scope,
                view_id=landscape_contract.default_view_id,
                target_resolution=int(landscape_target_resolution),
            )
            landscape_result = _workspace_landscape_result(
                landscape_request
            )
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        NotImplementedError,
        TypeError,
        ValueError,
    ) as exc:
        st.error(
            _t("Det deklarerade landskapslagret kunde inte valideras. Ingen "
            "annan regions landskap eller standardlager används.")
        )
        st.caption(_t('Teknisk orsak: {p0}', p0=exc))

    if left_panel is not None:
        try:
            wind_availability = _workspace_access_group_availability(
                access_readiness,
                "wind",
            )
            wind_panel_expanded = any(
                item.interaction == "interactive"
                for item in wind_availability
            )
        except (FileNotFoundError, KeyError, TypeError, ValueError):
            wind_panel_expanded = False
        with left_panel.expander(_t("Geografier"), expanded=True):
            st.caption(
                _t('{p0}: gemensam manifeststyrd arbetsyta. Varje regiondel aktiveras endast av sitt eget kontrakt.', p0=region_label)
            )
            st.caption(
                _t("Landskapstyper styrs i kartans lagerkontroll när ett "
                "validerat landskapskontrakt finns. Hexvisningen är alltid "
                "zoomanpassad.")
            )
            with st.expander(
                _t(WIND_LANDSCAPE_POTENTIAL_LABEL),
                expanded=wind_panel_expanded,
            ):
                _missing_wind_controls(
                    region,
                    status_rows,
                    access_readiness,
                )
            with st.expander(_t(SOLAR_LANDSCAPE_POTENTIAL_LABEL), expanded=False):
                _missing_solar_controls(
                    region,
                    access_readiness,
                )
        with left_panel.expander(_t("Energimodellering"), expanded=False):
            scenario_result = _missing_energy_controls(
                region,
                review_readiness,
                access_readiness,
            )
        with left_panel.expander(_t("Social acceptans"), expanded=False):
            social_identity = _workspace_ui_identity(
                region_id,
                SOCIAL_ACCEPTANCE_CAPABILITY_ID,
            )
            social_readiness = _workspace_social_acceptance_readiness(
                region_id,
                review_readiness,
                access_readiness,
            )
            social_request, social_applied = (
                _render_workspace_social_acceptance_controls(
                    social_identity,
                    social_readiness,
                    target_resolution=(
                        int(landscape_target_resolution)
                        if landscape_target_resolution is not None
                        else None
                    ),
                )
            )
            if social_applied:
                st.rerun()
            social_acceptance_result = (
                _render_applied_workspace_social_acceptance(social_request)
            )

    review_map_layer_count = 0
    review_execution_bundle: WorkspaceExecutionBundle | None = None

    if is_local_review:
        review_map_layer_count, review_execution_bundle = (
            _render_workspace_analysis_surface(
                access_readiness,
                region,
                landscape_result=landscape_result,
                target_resolution=landscape_target_resolution,
            )
        )
    elif landscape_result is not None:
        review_map_layer_count, review_execution_bundle = (
            _render_workspace_analysis_surface(
                access_readiness,
                region,
                landscape_result=landscape_result,
                target_resolution=landscape_target_resolution,
            )
        )
    else:
        st.caption(
            _t("Kartan visar inte potentiallager förrän minst H3-geometrier och "
            "relevant sol-/vindunderlag finns. Regionens standardcenter och "
            "zoom används när kartlager saknas.")
        )
        st.code(
            json.dumps(
                {
                    "region_id": region.get("region_id"),
                    "default_map_center": region.get("default_map_center"),
                    "default_zoom": region.get("default_zoom"),
                    "available_h3_resolutions": _available_h3_resolutions(region),
                },
                ensure_ascii=False,
                indent=2,
            ),
            language="json",
        )

    with st.expander(
        _t(":material/warning: Manifest- och granskningsstatus"),
        expanded=False,
    ):
        st.caption(
            _t('{p0} använder den gemensamma manifeststyrda arbetsytan. Endast deklarerade och validerade delar är aktiva.', p0=region_label)
        )
        if review_readiness is not None:
            trust = _review_access_presentation(review_readiness.access)
            st.badge(
                _t(trust["label"]),
                color=trust["color"],
                icon=trust["icon"],
            )
            st.caption(
                _t('Tillitsstatus: {p0}. {p1}', p0=review_readiness.trust_state, p1=review_readiness.access_detail)
            )
        if missing_rows:
            st.caption(
                _t("Vissa delar saknar manifest, data, implementation eller "
                "regional validering och förblir därför låsta.")
            )
            if not is_local_review:
                st.dataframe(
                    _display_dataframe(pd.DataFrame(displayed_status_rows)),
                    width="stretch",
                    hide_index=True,
                    height=min(420, 72 + 32 * len(displayed_status_rows)),
                )
        else:
            st.caption(_t("Alla grundmanifest och H3-geometrier finns."))

    summary_target = right_panel or st.container()
    with summary_target:
        map_layer_count = review_map_layer_count
        st.markdown('<span data-potential-tutorial-anchor="right-panel"></span>', unsafe_allow_html=True)
        st.subheader(_t("Vind/sol och landskapspåverkan"))
        st.caption(
            _t("Vind och sol visas som separata tekniska resultat när respektive "
            "analys har tillämpats. Det gemensamma scenarioresultatet ingår "
            "inte i den här granskningsytan.")
            if is_local_review
            else _t("Etableringsytan visas när H3-geometrier, teknikytor och scenario finns.")
        )
        with st.expander(
            f"{_t('Lager som visas')} ({map_layer_count})",
            expanded=False,
        ):
            if map_layer_count:
                trust_classification = (
                    review_readiness.access.access_classification
                    if review_readiness is not None
                    else "not_validated"
                )
                st.caption(
                    _t('Validerad granskningsgeometri · tillitsnivå: {p0}.', p0=trust_classification)
                )
            else:
                st.caption(_t("Inga kartlager är tända."))
        applied_analysis_ids = (
            {
                binding.request.analysis_id
                for binding in review_execution_bundle.bindings
                if binding.execution_input.is_applied
                and binding.area_result is not None
            }
            if review_execution_bundle is not None
            else set()
        )
        missing_analysis_inputs = [
            label
            for analysis_id, label in (("wind", "vind"), ("solar", "sol"))
            if analysis_id not in applied_analysis_ids
        ]
        if is_local_review:
            if missing_analysis_inputs:
                st.info(
                    _t("För att slutföra den tekniska granskningen, tillämpa: {p0}.",
                       p0=", ".join(_t(label) for label in missing_analysis_inputs))
                )
            else:
                st.success(
                    _t("Vind och sol har tillämpats och visas som separata "
                    "tekniska resultat.")
                )
        if "wind" not in applied_analysis_ids:
            _missing_potential_summary(WIND_LANDSCAPE_POTENTIAL_LABEL, "Vindpotential väntar på H3-/landskapsunderlag och vindregler.")
        if "solar" not in applied_analysis_ids:
            _missing_potential_summary(SOLAR_LANDSCAPE_POTENTIAL_LABEL, "Solpotential väntar på H3-/landskapsunderlag och solregler.")
        st.markdown(
            f"<h3 data-potential-tutorial-anchor='right-geographies'>"
            f"{html.escape(_t('Geografier'))}</h3>",
            unsafe_allow_html=True,
        )
        st.caption(
            _t("Arbetsyteprofilen är gemensam; varje geografi och analysdomän "
            "måste komma från den aktiva regionens manifest.")
        )
        st.subheader(_t("Energimodellering"))
        st.caption(
            (
                _t("Scenariokontraktet är tillämpat. Den här avgränsade "
                "granskningen visar inget gemensamt scenarioresultat.")
                if scenario_result is not None
                else _t("Inget energiscenario är tillämpat. Energipanelen visar "
                "vilka underlag som är tillgängliga.")
            )
        )
        st.subheader(_t("Social acceptans"))
        st.caption(
            (
                _t("Kontraktet för social acceptans är tillämpat. Den här "
                "avgränsade granskningen kopplar det inte till ett gemensamt "
                "scenarioresultat.")
                if social_acceptance_result is not None
                else _t("Inget acceptansresultat är tillämpat. Acceptanspanelen "
                "visar vilka underlag som är tillgängliga.")
            )
        )
        with st.expander(_t("Regionstatus"), expanded=False):
            st.caption(
                _t("Samma appstruktur används för alla regioner. Saknade delar "
                "visas som status, inte som krasch.")
            )
            st.dataframe(
                _display_dataframe(pd.DataFrame(displayed_status_rows)),
                key="workspace_region_status",
                width="stretch",
                hide_index=True,
                height=min(420, 72 + 32 * len(displayed_status_rows)),
            )
        with st.expander(_t("Nästa datapaket"), expanded=True):
            st.caption(
                _t("Ett manifest räcker inte för att visa potential. Varje "
                "aktiverad del behöver ett komplett, reproducerbart och "
                "validerat kontrakt från källa till UI.")
            )
            st.markdown(
                _t("- `workspace_profile` för den gemensamma UI-strukturen\n"
                "- `geography_manifest` med analysdomän och H3-identitet\n"
                "- `analysis_manifests` med regionspecifika källor, operationer och parametrar\n"
                "- checksumspinnade källartefakter och kompletta observationer bundna till exakt domän\n"
                "- implementerad generisk konsument samt teknisk och regional validering\n"
                "- `scenario_manifest` och `social_acceptance_manifest` först när de kapabiliteterna ska aktiveras")
            )
        _data_method(region, delivery_contract_only=is_local_review)


def _unified_workspace_tab(
    region: dict[str, Any],
    context: dict[str, Any],
    left_panel: Any | None = None,
    right_panel: Any | None = None,
    review_readiness: WorkspaceReviewReadiness | None = None,
    access_readiness: WorkspaceAccessReadiness | None = None,
    target_resolution: int | None = None,
    runtime_snapshot_token: str = "",
) -> None:
    _loading_phase("loading.preparing")
    if access_readiness is None:
        raise ValueError("The workspace requires one explicit access contract")
    if not bool(context.get("runtime_ready")):
        _cached_workspace_native_area.clear()
        _cached_workspace_group_buffer_preview.clear()
        _cached_workspace_analysis_binding.clear()
        _invalidate_workspace_cache("runtime inputs unavailable")
        _render_missing_data_workspace(
            region,
            context,
            left_panel,
            right_panel,
            review_readiness,
            access_readiness,
            target_resolution,
        )
        return

    # Numerical V2-parity consumers remain temporarily bound to the explicit
    # private compatibility adapter. The canonical `landscape_manifest` is
    # reserved for the typed, display-only workspace.landscape contract and
    # must never be interpreted by this legacy calculation chain.
    landscape_manifest = context.get(
        LEGACY_NUMERICAL_LANDSCAPE_CONTEXT_KEY
    )
    if landscape_manifest is None and catalog_context_runtime_declared(str(region["region_id"])):
        landscape_manifest = {}
    if not isinstance(landscape_manifest, dict):
        raise ValueError(
            "The legacy numerical landscape compatibility context is missing"
        )
    potential_manifest = context["potential_manifest"]
    solar_rules = context["solar_rules"]

    _ensure_default_start_state(region)

    _prime_wind_builder_state(_default_wind_params(), _selected_wind_layers())
    h3_resolution, zoom_family_enabled, opacity, preserve_map_view, map_reset_token = _zoom_adapted_map_panel_state(
        region,
        "combined",
    )
    region_id = str(region.get("region_id") or "").strip().lower()
    scenario_identity = _workspace_ui_identity(
        region_id,
        SCENARIO_CAPABILITY_ID,
    )
    scenario_readiness = _workspace_scenario_readiness(region_id, review_readiness, access_readiness)

    st.session_state["show_default_solar"] = False
    st.session_state.setdefault("show_user_solar", False)
    st.session_state.setdefault("solar_large_scale_active", False)
    st.session_state.setdefault("solar_large_population_active", False)
    st.session_state.setdefault("solar_protected_buffer_m", 0.0)
    st.session_state["show_default_wind"] = False
    st.session_state["show_user_wind"] = False
    solar_identity = _workspace_ui_identity(region_id, "solar")
    solar_applied_request = _ensure_workspace_analysis_request(
        solar_identity,
        access_readiness,
    )
    if solar_applied_request is None:
        raise ValueError("The product workspace has no applied solar request")
    rooftop_identity = _workspace_ui_identity(
        region_id,
        ROOFTOP_CAPABILITY_ID,
    )
    try:
        rooftop_selection = _ensure_workspace_rooftop_selection(
            rooftop_identity
        )
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ):
        # The energy renderer exposes an invalid selection; calculation
        # stays fail-closed without showing the retired rooftop form.
        rooftop_selection = None
    applied_solar_config = _solar_config_from_workspace_request(
        solar_applied_request,
        rooftop_selection,
    )
    landscape_identity = _workspace_ui_identity(
        region_id,
        LANDSCAPE_CAPABILITY_ID,
    )
    landscape_readiness = _workspace_landscape_readiness(region_id, review_readiness, access_readiness)
    landscape_display_layers: list[dict[str, Any]] = []
    landscape_display_error: str | None = None
    try:
        landscape_display_layers = _workspace_landscape_family_layers(
            landscape_identity,
            landscape_readiness,
            region,
        )
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        PermissionError,
        TypeError,
        ValueError,
    ) as exc:
        landscape_display_error = str(exc)
    social_identity = _workspace_ui_identity(
        region_id,
        SOCIAL_ACCEPTANCE_CAPABILITY_ID,
    )
    social_readiness = _workspace_social_acceptance_readiness(
        region_id,
        review_readiness,
        access_readiness,
    )
    social_acceptance_request: SocialAcceptanceRequest | None = None
    social_acceptance_result: SocialAcceptanceResult | None = None
    social_acceptance_display_layer: dict[str, Any] | None = None
    active_solar_count = _count_enabled(
        bool(applied_solar_config.get("large_scale_active", False)),
        bool(applied_solar_config.get("small_population_active", False)),
    )
    wind_selected_layers = _selected_wind_layers()
    wind_ui_params = _default_wind_params()
    wind_controls_applied = False
    solar_controls_applied = False
    energy_model_state: dict[str, Any] = {"available": False}
    scenario_result: ScenarioResult | None = None
    performance_log: list[dict[str, Any]] = []
    analysis_h3_resolution = _workspace_analysis_h3_resolution(region)
    wind_analysis_h3_resolution = _wind_analysis_h3_resolution(region)
    if wind_analysis_h3_resolution != analysis_h3_resolution:
        raise ValueError(
            "The wind analysis domain and the transitional combined "
            "workspace must use the same H3 resolution until solar "
            "has its own canonical analysis contract"
        )
    analysis_hex_area_km2 = float(h3_hex_area_km2(analysis_h3_resolution))
    if left_panel is not None:
        with left_panel.expander(_t("Geografier"), expanded=False, key='workspace_geographies_panel'):
            if landscape_display_error is not None:
                st.info(
                    _t("Landskapstyper kunde inte valideras och visas inte i kartan.")
                )
                st.caption(_t('Teknisk orsak: {p0}', p0=landscape_display_error))
            with st.expander(_t(WIND_LANDSCAPE_POTENTIAL_LABEL), expanded=False, key='workspace_wind_panel'):
                wind_identity = _workspace_ui_identity(region_id, "wind")
                wind_applied_request, wind_controls_applied = (
                    _render_workspace_analysis_controls(
                        wind_identity,
                        access_readiness,
                    )
                )
                if wind_applied_request is None:
                    raise ValueError(
                        "The product workspace has no applied wind request"
                    )
                wind_selected_layers, wind_ui_params = (
                    _wind_workspace_request_values(wind_applied_request)
                )
                if not wind_applied_request.groups:
                    st.caption(_t("Inga vindfilter är valda: ofiltrerad vindpotential används som startläge."))
                _render_wind_map_review_controls(region, wind_selected_layers)

            with st.expander(
                _t(SOLAR_LANDSCAPE_POTENTIAL_LABEL),
                expanded=active_solar_count > 0,
                key="workspace_solar_panel",
            ):
                solar_applied_request, solar_controls_applied = (
                    _render_workspace_analysis_controls(
                        solar_identity,
                        access_readiness,
                    )
                )
                if solar_applied_request is None:
                    raise ValueError(
                        "The product workspace has no applied solar request"
                    )
                if solar_controls_applied:
                    _preserve_solar_map_review_widget_state(region_id)

                applied_solar_config = _solar_config_from_workspace_request(
                    solar_applied_request,
                    rooftop_selection,
                )
                _render_solar_map_review_controls(region, applied_solar_config)

        with left_panel.expander(_t("Energimodellering"), expanded=False, key='workspace_energy_panel'):
            st.caption(_t("Levereras av EML"))
            st.markdown(_t('[Energy Modelling Lab]({p0})', p0=EML_PROVIDER_URL))
            capacity_controls_panel = st.container() if "capacity_references" in context else None
            perf_started = _perf_start()
            scenario_request, scenario_controls_applied = (
                _render_workspace_scenario_controls(
                    scenario_identity,
                    scenario_readiness,
                )
            )
            # Use the validated request in this pass; final scenario metadata
            # is captured after the controls and results have been prepared.
            scenario_result, energy_model_state = (
                _render_applied_workspace_scenario(
                    scenario_request,
                    h3_resolution=analysis_h3_resolution,
                    rooftop_selection=rooftop_selection,
                )
            )
            if energy_model_state.get("available") and "capacity_references" in context:
                energy_model_state["capacity_references"] = context["capacity_references"]
                if capacity_controls_panel is not None and energy_model_state.get("capacity_based"):
                    with capacity_controls_panel:
                        _render_workspace_capacity_controls(scenario_identity, energy_model_state)
            _add_perf_timing(performance_log, "Energimodellering", perf_started, f"analys R{analysis_h3_resolution}")
        with left_panel.expander(_t("Social acceptans"), expanded=False, key='workspace_social_panel'):
            social_acceptance_request, social_controls_applied = (
                _render_workspace_social_acceptance_controls(
                    social_identity,
                    social_readiness,
                    target_resolution=int(analysis_h3_resolution),
                )
            )
            # The form returned the validated current request; all social
            # result and allocation preparation follows in this verified pass.
            social_acceptance_result = (
                _render_applied_workspace_social_acceptance(
                    social_acceptance_request
                )
            )
            social_acceptance_display_layer = (
                _workspace_social_acceptance_map_layer(
                    social_acceptance_result
                )
            )

    if left_panel is None and social_readiness.interaction == "interactive":
        contract = load_catalog_social_acceptance_contract(region_id)
        social_acceptance_request = _ensure_workspace_social_acceptance_request(
            social_identity,
            contract,
            target_resolution=int(analysis_h3_resolution),
        )
        social_acceptance_result = _workspace_social_acceptance_result(
            social_acceptance_request
        )
        social_acceptance_display_layer = _workspace_social_acceptance_map_layer(
            social_acceptance_result
        )

    # Forms have returned their validated requests and map-review controls
    # have reconciled preview state. Derive solar values from that final config.
    show_solar_v1 = bool(applied_solar_config.get("small_population_active", False))
    show_user_solar = bool(applied_solar_config.get("large_scale_active", False))
    solar_small_population_active = bool(applied_solar_config.get("small_population_active", False))
    solar_large_population_layer_ids = (
        _solar_control_selected_large_population_layer_ids(
            applied_solar_config,
            str(region.get("region_id") or ""),
        )
    )
    solar_large_population_active = bool(
        applied_solar_config.get("large_population_active", False)
        and solar_large_population_layer_ids
    )
    solar_large_protected_layer_ids = list(applied_solar_config.get("large_protected_layer_ids", []))
    solar_large_protected_active = bool(solar_large_protected_layer_ids)
    solar_large_filter_configs = _solar_active_filter_configs(applied_solar_config)
    solar_params: dict[str, float] = {}
    solar_params["population_buffer_m"] = _solar_distance_value(
        applied_solar_config.get("population_buffer_m"),
        _solar_population_distance_contract(),
    )
    for group_id, spec in SOLAR_FILTER_GROUP_SPECS.items():
        solar_params[str(spec["buffer_key"])] = _solar_distance_value(
            applied_solar_config.get(str(spec["buffer_key"])),
            _solar_filter_distance_contract(group_id),
        )
    solar_v1_area_m2_per_person = (
        float(applied_solar_config["panel_area_m2_per_person"])
        if "panel_area_m2_per_person" in applied_solar_config
        else None
    )

    social_layer_visible = bool(
        social_acceptance_result is not None
        and social_acceptance_result.request.layer_visible
    )
    social_acceptance_impact_pct = float(
        social_acceptance_result.request.impact_pct
        if social_acceptance_result is not None
        else 0.0
    )
    social_acceptance_allocation_priority_pct = float(
        social_acceptance_result.request.allocation_priority_pct
        if social_acceptance_result is not None
        else 0.0
    )
    wind_applied_request = _validated_applied_wind_workspace_request(
        str(region.get("region_id") or "")
    )
    if wind_applied_request is None:
        raise ValueError("The product workspace has no applied wind request")
    wind_selected_layers, wind_ui_params = _wind_workspace_request_values(
        wind_applied_request
    )
    # A validated applied request remains an active technology with no filters.
    show_user_wind = True

    display_geometry_path = _h3_display_geometry_path(region, h3_resolution)
    analysis_display_geometry_path = _h3_display_geometry_path(region, analysis_h3_resolution)
    resolution_info = _hex_display_rule(region, h3_resolution, zoom_family_enabled)
    wind_visual_options = _wind_visual_options_from_state(wind_selected_layers)
    if energy_model_state.get("available"):
        energy_model_state["region_id"] = str(region.get("region_id", "region") or "region")
        energy_model_state["analysis_h3_resolution"] = int(analysis_h3_resolution)
        energy_model_state["analysis_hex_area_km2"] = float(analysis_hex_area_km2)
        energy_model_state["display_h3_resolution"] = int(h3_resolution)
        energy_model_state["display_hex_area_km2"] = float(h3_hex_area_km2(h3_resolution))
        energy_model_state["social_acceptance_allocation_priority_pct"] = float(social_acceptance_allocation_priority_pct or 0.0)
        energy_model_state["social_acceptance_result"] = (
            social_acceptance_result.as_dict()
            if social_acceptance_result is not None
            else None
        )
        energy_model_state["wind_ui_params"] = dict(wind_ui_params)
        energy_model_state["wind_visual_options"] = dict(wind_visual_options)
        energy_model_state["wind_active_source_count"] = sum(
            len(layer_ids) for layer_ids in normalize_group_layer_map(wind_selected_layers).values()
        )
        energy_model_state["solar_params"] = dict(solar_params)
        energy_model_state["solar_large_population_active"] = bool(solar_large_population_active)
        energy_model_state["solar_large_population_layer_ids"] = list(
            solar_large_population_layer_ids
        )
        energy_model_state["solar_large_population_layer_count"] = len(
            solar_large_population_layer_ids
        )
        energy_model_state["solar_large_unfiltered_land_active"] = bool(applied_solar_config.get("large_unfiltered_land_active", False))
        energy_model_state["solar_large_protected_active"] = bool(solar_large_protected_active)
        energy_model_state["solar_large_protected_layer_count"] = int(len(solar_large_protected_layer_ids))
        energy_model_state["solar_large_filter_configs"] = list(solar_large_filter_configs)

    # Presentation keeps references to verified immutable results and display
    # geometry. It never stores a second, language-specific GIS payload.
    st.session_state[WORKSPACE_PRESENTATION_BUILD_KEY] = {
        "analysis_h3_resolution": analysis_h3_resolution,
        "landscape_display_layers": landscape_display_layers,
        "landscape_display_error": landscape_display_error,
        "social_acceptance_display_layer": social_acceptance_display_layer,
        "scenario_result": scenario_result,
        "social_acceptance_result": social_acceptance_result,
        "rooftop_selection": rooftop_selection,
        "applied_solar_config": dict(applied_solar_config),
    }
    workspace_fingerprint = _workspace_calculation_fingerprint(
        region,
        h3_resolution,
        analysis_h3_resolution,
        zoom_family_enabled,
        show_user_solar,
        show_solar_v1,
        show_user_wind,
        social_acceptance_result,
        applied_solar_config,
        solar_params,
        solar_large_filter_configs,
        wind_selected_layers,
        wind_ui_params,
        wind_applied_request.as_dict(),
        energy_model_state,
        runtime_snapshot_token,
    )
    _loading_phase("loading.geography")
    perf_started = _perf_start()
    area_resolution_plan = _product_workspace_execution_resolution_plan(
        wind_request=wind_applied_request,
        solar_request=solar_applied_request,
        wind_active=show_user_wind,
        solar_active=show_user_solar,
        display_resolution=h3_resolution,
        analysis_resolution=analysis_h3_resolution,
        runtime_snapshot_token=runtime_snapshot_token,
        source_buffer_required=False,
    )
    _add_perf_timing(
        performance_log,
        "Signerad analysmatris",
        perf_started,
        f"analys R{analysis_h3_resolution}; visning R{h3_resolution}",
    )
    combined_execution_bundle: CombinedResultExecutionBundle | None = None
    if energy_model_state.get("available"):
        if (
            area_resolution_plan is None
            or scenario_result is None
            or social_acceptance_result is None
        ):
            raise ValueError(
                "Combined-result execution requires complete applied inputs"
            )
        _loading_phase("loading.allocation")
        perf_started = _perf_start()
        combined_execution_bundle = _workspace_combined_result_execution(
            area_resolution_plan,
            scenario_result=scenario_result,
            rooftop_selection=rooftop_selection,
            social_acceptance_result=social_acceptance_result,
            runtime_snapshot_token=runtime_snapshot_token,
        )
        _add_perf_timing(
            performance_log,
            "Signerad kombinationsmotor",
            perf_started,
            "resultat, allokering och renderer-neutral presentation",
        )
        energy_model_state["combined_execution_signature_sha256"] = (
            combined_execution_bundle.execution_signature_sha256
        )
        energy_model_state["combined_result_signature_sha256"] = (
            combined_execution_bundle.combined_result.result_signature_sha256
        )
        energy_model_state["combined_presentation_signature_sha256"] = (
            combined_execution_bundle.presentation.presentation_signature_sha256
        )
    _loading_phase("loading.map")
    selected_source_buffer_layers = _product_workspace_source_buffer_layers(
        area_resolution_plan,
        wind_request=wind_applied_request,
        solar_request=solar_applied_request,
        wind_visual_options=wind_visual_options,
        solar_config=applied_solar_config,
        runtime_snapshot_token=runtime_snapshot_token,
    )
    if _ui_only_rerun_requested():
        cached_workspace = _cached_workspace_payload(workspace_fingerprint)
        if cached_workspace is not None:
            cached_workspace = _rebase_workspace_review_layers(
                cached_workspace,
                selected_source_buffer_layers,
            )
            cached_energy_state = (
                dict(cached_workspace.get("energy_model_state"))
                if isinstance(cached_workspace.get("energy_model_state"), dict)
                else {}
            )
            cached_energy_state["wind_visual_options"] = dict(
                wind_visual_options
            )
            if social_acceptance_result is not None:
                cached_energy_state["social_acceptance_result"] = (
                    social_acceptance_result.as_dict()
                )
            cached_workspace["energy_model_state"] = cached_energy_state
            st.session_state[WORKSPACE_RENDER_CACHE_KEY] = cached_workspace
            _render_reused_workspace_outputs(
                cached_workspace,
                region,
                opacity,
                preserve_map_view,
                map_reset_token,
                right_panel,
                access_readiness,
                landscape_display_layers,
                social_acceptance_display_layer,
                review_readiness,
            )
            _clear_ui_only_rerun()
            return
        _clear_ui_only_rerun()

    calc_steps = _calculation_progress_steps(
        show_user_solar,
        show_solar_v1,
        show_user_wind,
        energy_model_state,
    )
    performance_bucket = _performance_history_bucket(region, h3_resolution, zoom_family_enabled)
    performance_estimates = _performance_step_estimates(performance_bucket, calc_steps)
    calc_progress = _start_calculation_progress(calc_steps)

    workspace_area_frames: dict[
        str,
        tuple[pd.DataFrame, pd.DataFrame],
    ] = {}
    if area_resolution_plan is not None:
        if show_user_wind:
            workspace_area_frames["wind"] = _workspace_execution_area_frames(
                area_resolution_plan,
                "wind",
                output_schema=WORKSPACE_AREA_FRAME_SCHEMA_LEGACY_WIND,
            )
        if show_user_solar:
            workspace_area_frames["solar"] = _workspace_execution_area_frames(
                area_resolution_plan,
                "solar",
                output_schema=WORKSPACE_AREA_FRAME_SCHEMA_WORKSPACE,
            )

    layers: list[dict[str, Any]] = list(selected_source_buffer_layers)
    potential_frames: list[dict[str, Any]] = []
    unified_notes: list[str] = []
    user_solar_frame = pd.DataFrame()
    user_solar_analysis_frame = pd.DataFrame()
    solar_v1_frame = pd.DataFrame()
    solar_v1_analysis_frame = pd.DataFrame()
    custom_wind_analysis_frame = pd.DataFrame()
    solar_large_polygon_geojson: dict[str, Any] | None = None

    if show_user_solar:
        perf_started = _perf_start()
        solar_unfiltered_land_active = bool(applied_solar_config.get("large_unfiltered_land_active", False))
        large_population_buffer_m = float(solar_params.get("population_buffer_m", 250.0) or 250.0) if solar_large_population_active else 0.0
        large_protected_buffer_m = float(solar_params.get("protected_buffer_m", 0.0) or 0.0) if solar_large_protected_layer_ids else None
        # The workspace already computed exact solar areas. Only contextual
        # labels survive this adapter; do not repeat the retired proxy filters.
        user_solar_frame = _landscape_frame(
            region, landscape_manifest, h3_resolution,
        ).reindex(columns=["hex_id", "class_km", "landscape_type"])
        user_solar_analysis_frame = (
            user_solar_frame.copy()
            if int(h3_resolution) == int(analysis_h3_resolution)
            else _landscape_frame(
                region, landscape_manifest, analysis_h3_resolution,
            ).reindex(columns=["hex_id", "class_km", "landscape_type"])
        )
        energy_model_state["solar_area_selected_groups"] = {
            group.group_id: list(group.layer_ids)
            for group in solar_applied_request.groups
        }
        try:
            exact_solar_area_frame, exact_solar_analysis_frame = (
                workspace_area_frames["solar"]
            )
        except KeyError as exc:
            raise ValueError(
                "The product workspace omitted its active solar area result"
            ) from exc
        user_solar_frame = _exact_solar_area_summary_frame(
            region,
            user_solar_frame,
            exact_solar_area_frame,
            int(h3_resolution),
            landscape_manifest,
        )
        user_solar_analysis_frame = _exact_solar_area_summary_frame(
            region,
            user_solar_analysis_frame,
            exact_solar_analysis_frame,
            int(analysis_h3_resolution),
            landscape_manifest,
        )
        exact_solar_model_area_km2 = float(
            pd.to_numeric(
                exact_solar_analysis_frame["display_area_km2"],
                errors="raise",
            ).sum()
        )
        exact_solar_potential_area_km2 = float(
            pd.to_numeric(
                exact_solar_analysis_frame["potential_area_km2"],
                errors="raise",
            ).sum()
        )
        energy_model_state["solar_area_result_stats"] = {
            "model_area_km2": exact_solar_model_area_km2,
            "potential_area_km2": exact_solar_potential_area_km2,
            "potential_pct": (
                exact_solar_potential_area_km2
                / max(exact_solar_model_area_km2, 1e-9)
                * 100.0
            ),
            "potential_hex_count": int(
                exact_solar_analysis_frame["potential_area_km2"].gt(0.0).sum()
            ),
            "resolution": int(analysis_h3_resolution),
        }
        active_solar_filter_count = int(bool(solar_large_population_active)) + len(solar_large_filter_configs)
        if active_solar_filter_count > 0:
            unfiltered_solar_area_km2 = exact_solar_model_area_km2
            filtered_solar_area_km2 = exact_solar_potential_area_km2
            removed_solar_area_km2 = max(0.0, unfiltered_solar_area_km2 - filtered_solar_area_km2)
            energy_model_state["solar_filter_impact"] = {
                "active_filter_count": active_solar_filter_count,
                "unfiltered_area_km2": unfiltered_solar_area_km2,
                "filtered_area_km2": filtered_solar_area_km2,
                "removed_area_km2": removed_solar_area_km2,
                "removed_share_pct": (
                    removed_solar_area_km2 / max(unfiltered_solar_area_km2, 1e-9) * 100.0
                    if unfiltered_solar_area_km2 > 0
                    else 0.0
                ),
            }
        solar_large_polygon_geojson = None
        if solar_unfiltered_land_active:
            unified_notes.append(
                _t('Startläge: {p0} är ofiltrerad över kartans landskapsunderlag för att visa gemensam sol- och vindpotential.', p0=_t(SOLAR_LARGE_SCALE_LABEL))
            )
        else:
            unified_notes.append(
                _t('{p0} använder hela landskapsunderlaget som kandidatbas. Aktiva filter drar bort yta från den basen.', p0=_t(SOLAR_LARGE_SCALE_LABEL))
            )
        if solar_large_population_active:
            unified_notes.append(
                _t('Befolkningsgruppen tar bort potential inom {p0:.0f} m från {p1} källager.', p0=large_population_buffer_m, p1=len(solar_large_population_layer_ids))
            )
        for filter_config in solar_large_filter_configs:
            group_id = str(filter_config.get("group_id", ""))
            spec = SOLAR_FILTER_GROUP_SPECS.get(group_id, {})
            label = str(
                filter_config.get("label")
                or _solar_filter_display_label(group_id)
            )
            layer_labels = [str(value) for value in (filter_config.get("layer_labels") or [])]
            layer_text = f" ({', '.join(layer_labels[:3])}{'...' if len(layer_labels) > 3 else ''})" if layer_labels else ""
            if str(filter_config.get("effect", spec.get("effect", "exclusion"))) == "feasibility":
                unified_notes.append(
                    _t('{p0}{p1} begränsar solpotentialen till yta inom {p2:.0f} m från nätobjekt.', p0=_t(label), p1=layer_text, p2=float(filter_config.get('buffer_m', 0.0) or 0.0))
                )
            else:
                unified_notes.append(
                    _t('{p0}{p1} drar av potential med {p2:.0f} m buffert.', p0=_t(label), p1=layer_text, p2=float(filter_config.get('buffer_m', 0.0) or 0.0))
                )
        _add_perf_timing(
            performance_log,
            "Sol storskalig",
            perf_started,
            f"visning R{h3_resolution}: {len(user_solar_frame)} hex; analys R{analysis_h3_resolution}: {len(user_solar_analysis_frame)} hex",
        )
        _advance_calculation_progress(calc_progress, "Sol storskalig")

    if show_solar_v1:
        perf_started = _perf_start()
        solar_v1_frame = _solar_v1_frame(region, landscape_manifest, h3_resolution, solar_v1_area_m2_per_person)
        solar_v1_analysis_frame = (
            solar_v1_frame.copy()
            if int(h3_resolution) == int(analysis_h3_resolution)
            else _solar_v1_frame(region, landscape_manifest, analysis_h3_resolution, solar_v1_area_m2_per_person)
        )
        if solar_small_population_active:
            rooftop_review_source_enabled = _solar_visual_enabled(
                applied_solar_config,
                "source",
                SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID,
            )
            rooftop_review_buffer_enabled = _solar_visual_enabled(
                applied_solar_config,
                "buffer",
                SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID,
            )
            if rooftop_review_source_enabled or rooftop_review_buffer_enabled:
                (
                    rooftop_review_group_id,
                    rooftop_review_layer_ids,
                    rooftop_review_buffer_m,
                ) = _solar_rooftop_map_review_config(
                    str(region.get("region_id") or "")
                )
            if rooftop_review_source_enabled:
                for review_layer in _solar_filter_source_layers(
                    str(region.get("region_id") or ""),
                    SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID,
                    rooftop_review_group_id,
                    rooftop_review_layer_ids,
                ):
                    _append_unique_layer(
                        layers,
                        _layer_visible_by_default(review_layer),
                    )
            if rooftop_review_buffer_enabled:
                _append_unique_layer(
                    layers,
                    _layer_visible_by_default(
                        _solar_filter_buffer_layer(
                            str(region.get("region_id") or ""),
                            SOLAR_SMALL_POPULATION_VISUAL_GROUP_ID,
                            rooftop_review_group_id,
                            rooftop_review_buffer_m,
                            rooftop_review_layer_ids,
                        )
                    ),
                )
        layers.extend(
            _hex_family_layers(
                region,
                h3_resolution,
                zoom_family_enabled,
                "solar_v1_schematic",
                f"{SOLAR_SMALL_SCALE_LABEL} (schablonhex)",
                lambda resolution: _solar_v1_layer(
                    f"{SOLAR_SMALL_SCALE_LABEL} (schablonhex)",
                    solar_v1_frame if int(resolution) == int(h3_resolution) else _solar_v1_frame(region, landscape_manifest, int(resolution), solar_v1_area_m2_per_person),
                    int(resolution),
                ),
            )
        )
        energy_model_state["solar_v1_stats"] = _solar_v1_stats(solar_v1_analysis_frame, energy_model_state)
        unified_notes.append(_solar_v1_formula_text(region, solar_v1_area_m2_per_person))
        unified_notes.append(
            _t('{p0} visas som separata gula schablonhexar för att inte läsas som sammanhängande markyta.', p0=_t(SOLAR_SMALL_SCALE_LABEL))
        )
        unified_notes.append(_solar_v1_population_source_status(region))
        _add_perf_timing(
            performance_log,
            "Sol småskalig",
            perf_started,
            f"visning R{h3_resolution}: {len(solar_v1_frame)} hex; analys R{analysis_h3_resolution}: {len(solar_v1_analysis_frame)} hex",
        )
        _advance_calculation_progress(calc_progress, "Sol småskalig")

    if show_solar_v1 or show_user_solar:
        perf_started = _perf_start()
        solar_establishment_potential_frame = _solar_establishment_potential_source_frame(
            region,
            landscape_manifest,
            analysis_h3_resolution,
            user_solar_analysis_frame if show_user_solar else pd.DataFrame(),
        )
        solar_establishment_display_frame = _solar_establishment_potential_source_frame(
            region,
            landscape_manifest,
            h3_resolution,
            user_solar_frame if show_user_solar else pd.DataFrame(),
        )
        _append_unique_layer(
            layers,
            _solar_potential_polygon_layer(
                user_solar_frame if show_user_solar else pd.DataFrame(),
                solar_large_polygon_geojson,
            ),
        )
        potential_frames.append(
            {
                "label": SOLAR_LANDSCAPE_POTENTIAL_LABEL,
                "technology": "solar",
                "frame": solar_establishment_display_frame,
                "resolution": h3_resolution,
            }
        )
        if energy_model_state.get("available"):
            if combined_execution_bundle is None or social_acceptance_result is None:
                raise ValueError("Signed solar allocation is unavailable")
            combined_analysis_frame = _combined_result_compatibility_frame(
                combined_execution_bundle,
                int(analysis_h3_resolution),
                social_acceptance_result,
            )
            solar_proposal_frame = combined_analysis_frame[
                combined_analysis_frame["solar_allocated_area_km2"].gt(
                    FLOAT_TOLERANCE
                )
            ].copy()
            solar_proposal_frame = solar_proposal_frame.rename(
                columns={
                    "solar_potential_area_km2": "potential_area_km2",
                    "solar_potential_score": "potential_score",
                    "solar_allocated_area_km2": "allocated_area_km2",
                    "solar_allocated_gwh": "allocated_gwh",
                    "solar_allocated_hex_share_pct": "allocated_hex_share_pct",
                    "solar_rank": "selected_rank",
                    "solar_outside_lp": "outside_et",
                    "solar_conflict_area_km2": "outside_area_km2",
                    "solar_inside_area_km2": "inside_area_km2",
                    "solar_last_resort_overlap": "reserved_by_other_technology",
                    "solar_allocation_priority_score": "allocation_priority_score",
                    "solar_landscape_priority_score": "landscape_priority_score",
                }
            )
            solar_proposal_frame["allocated_twh"] = (
                solar_proposal_frame["allocated_gwh"] / 1000.0
            )
            solar_proposal_stats = _combined_result_summary_stats(
                combined_execution_bundle,
                "solar",
            )
            energy_model_state["solar_proposal_frame"] = solar_proposal_frame
            energy_model_state["solar_proposal_stats"] = solar_proposal_stats
            if not solar_proposal_frame.empty:
                unified_notes.append(
                    _t('Solens scenarioyta använder en intern landskaps-/teknikranking inom etableringshex; placeringen visas med potentiallagrets hexagoner.')
                )
        _add_perf_timing(
            performance_log,
            "Sol samlad etablering",
            perf_started,
            f"markpotential R{h3_resolution}: {len(solar_establishment_display_frame)} hex; analys R{analysis_h3_resolution}: {len(solar_establishment_potential_frame)} hex",
        )
        _advance_calculation_progress(calc_progress, "Sol samlad etablering")

    custom_wind_preview_state: dict[str, Any] | None = None
    energy_model_state.pop("wind_preview_diagnostics", None)
    if show_user_wind:
        if area_resolution_plan is None:
            raise ValueError(
                "The product workspace omitted its active wind execution plan"
            )
        perf_started = _perf_start()
        # Area frames and selected-source previews already belong to the
        # validated workspace. The historical standard-domain proxy is not
        # an additional prerequisite for the exact technology result.
        custom_wind_preview_state = {
            "active_source_count": len(wind_applied_request.selected_layer_ids),
            "active_group_count": len(wind_applied_request.groups),
            "unfiltered_land": not bool(wind_applied_request.groups),
        }
        energy_model_state["wind_preview_diagnostics"] = {
            "active_source_count": custom_wind_preview_state["active_source_count"],
            "active_group_count": custom_wind_preview_state["active_group_count"],
        }
        custom_wind_summary = _landscape_frame(
            region, landscape_manifest, h3_resolution,
        ).reindex(columns=["hex_id", "class_km", "landscape_type"])
        custom_wind_analysis_frame = (
            custom_wind_summary.copy()
            if int(h3_resolution) == int(analysis_h3_resolution)
            else _landscape_frame(
                region, landscape_manifest, analysis_h3_resolution,
            ).reindex(columns=["hex_id", "class_km", "landscape_type"])
        )
        try:
            exact_wind_display_area_frame, exact_wind_area_frame = workspace_area_frames["wind"]
        except KeyError as exc:
            raise ValueError("The product workspace omitted its active wind area result") from exc
        custom_wind_analysis_frame = _exact_wind_area_summary_frame(
            region,
            custom_wind_analysis_frame,
            exact_wind_area_frame,
            int(analysis_h3_resolution),
            landscape_manifest,
        )
        if int(h3_resolution) == int(analysis_h3_resolution):
            custom_wind_summary = custom_wind_analysis_frame.copy()
        else:
            custom_wind_summary = _exact_wind_area_summary_frame(
                region,
                custom_wind_summary,
                exact_wind_display_area_frame,
                int(h3_resolution),
                landscape_manifest,
            )
        exact_model_area_km2 = float(
            pd.to_numeric(
                exact_wind_area_frame["display_area_km2"],
                errors="raise",
            ).sum()
        )
        exact_potential_area_km2 = float(
            pd.to_numeric(
                exact_wind_area_frame["potential_area_km2"],
                errors="raise",
            ).sum()
        )
        energy_model_state["wind_area_result_stats"] = {
            "model_area_km2": exact_model_area_km2,
            "potential_area_km2": exact_potential_area_km2,
            "potential_pct": (
                exact_potential_area_km2
                / max(exact_model_area_km2, 1e-9)
                * 100.0
            ),
            "potential_hex_count": int(
                exact_wind_area_frame["potential_area_km2"].gt(0.0).sum()
            ),
            "resolution": int(analysis_h3_resolution),
        }
        # The user-facing diagnostic belongs to the signed technology-
        # support result, whose denominator is the eligible surface.  The
        # earlier polygon preview intentionally uses the standard analysis
        # domain and must not override this product metric.
        energy_model_state["wind_preview_diagnostics"][
            "combined_land_share_pct"
        ] = energy_model_state["wind_area_result_stats"]["potential_pct"]
        potential_frames.append(
            {
                "label": WIND_LANDSCAPE_POTENTIAL_LABEL,
                "technology": "wind",
                "frame": custom_wind_summary,
                "resolution": h3_resolution,
            }
        )
        if zoom_family_enabled:
            unified_notes.append(
                _t('{p0} beräknas i R{p1}. Hexvisningen är zoomanpassad för granskning.', p0=WIND_LANDSCAPE_POTENTIAL_LABEL, p1=analysis_h3_resolution)
            )
        else:
            unified_notes.append(
                _t('{p0} beräknas i R{p1}. Kartan visar vald H3-upplösning.', p0=WIND_LANDSCAPE_POTENTIAL_LABEL, p1=analysis_h3_resolution)
            )
        unified_notes.append(
            _t("Vindens interna hexberäkning används för att prioritera kärnområden i den gemensamma etableringsytan.")
        )
        if energy_model_state.get("available"):
            if combined_execution_bundle is None or social_acceptance_result is None:
                raise ValueError("Signed wind allocation is unavailable")
            combined_analysis_frame = _combined_result_compatibility_frame(
                combined_execution_bundle,
                int(analysis_h3_resolution),
                social_acceptance_result,
            )
            proposal_frame = combined_analysis_frame[
                combined_analysis_frame["wind_allocated_area_km2"].gt(
                    FLOAT_TOLERANCE
                )
            ].copy()
            proposal_frame = proposal_frame.rename(
                columns={
                    "wind_potential_area_km2": "potential_area_km2",
                    "wind_potential_score": "potential_area_share_pct",
                    "wind_allocated_area_km2": "allocated_area_km2",
                    "wind_allocated_gwh": "allocated_gwh",
                    "wind_allocated_hex_share_pct": "allocated_hex_share_pct",
                    "wind_rank": "selected_rank",
                    "wind_outside_lp": "outside_et",
                    "wind_conflict_area_km2": "outside_area_km2",
                    "wind_inside_area_km2": "inside_area_km2",
                    "wind_last_resort_overlap": "reserved_by_other_technology",
                    "wind_allocation_priority_score": "allocation_priority_score",
                    "wind_landscape_priority_score": "landscape_priority_score",
                }
            )
            proposal_frame["allocated_twh"] = (
                proposal_frame["allocated_gwh"] / 1000.0
            )
            proposal_frame["allocated_share_of_need_pct"] = (
                proposal_frame["allocated_area_km2"]
                / max(
                    float(energy_model_state.get("wind_area_need_km2", 0.0) or 0.0),
                    1e-9,
                )
                * 100.0
            )
            proposal_stats = _combined_result_summary_stats(
                combined_execution_bundle,
                "wind",
            )
            energy_model_state["proposal_frame"] = proposal_frame
            energy_model_state["proposal_stats"] = proposal_stats
            if not proposal_frame.empty:
                unified_notes.append(
                    _t("Inom landskapspotentialen använder vindens scenarioyta "
                    "en intern landskaps-/teknikranking och kan välja starka "
                    "vindlägen även när sol redan valt samma hex; separata "
                    "ytor vinner där vid lika lämplighet. Vid expansion utanför "
                    "landskapspotentialen prioriteras i stället celler som sol "
                    "inte reserverat, följt av närmaste expansionsring och "
                    "vindrankingen.")
                )
            elif float(
                energy_model_state.get("wind_area_need_km2", 0.0) or 0.0
            ) > 0:
                unified_notes.append(_t("Energimodelleringen hittade inga vindceller som uppfyller minsta kärn-/potentialkrav."))
        _add_perf_timing(
            performance_log,
            "Vindpotential och vindetablering",
            perf_started,
            f"visning R{h3_resolution}, analys R{analysis_h3_resolution}; {int(custom_wind_preview_state.get('active_source_count', 0) or 0)} källager",
        )
        _advance_calculation_progress(calc_progress, "Vindpotential och vindetablering")

    if energy_model_state.get("available"):
        if combined_execution_bundle is None or social_acceptance_result is None:
            raise ValueError("Signed combined result is unavailable")
        energy_model_state["establishment_layer_visible"] = False
        perf_started = _perf_start()
        selected_establishment_frame = _combined_result_compatibility_frame(
            combined_execution_bundle,
            int(analysis_h3_resolution),
            social_acceptance_result,
        )
        wind_stats_for_outside = energy_model_state.get("proposal_stats") if isinstance(energy_model_state.get("proposal_stats"), dict) else {}
        solar_stats_for_outside = energy_model_state.get("solar_proposal_stats") if isinstance(energy_model_state.get("solar_proposal_stats"), dict) else {}
        class_counts = selected_establishment_frame.get("establishment_class", pd.Series(dtype=str)).astype(str).value_counts()
        potential_establishment_frame = selected_establishment_frame
        if not potential_establishment_frame.empty:
            class_counts = potential_establishment_frame.get("establishment_class", pd.Series(dtype=str)).astype(str).value_counts()
        energy_model_state["social_acceptance_summary"] = _social_acceptance_establishment_summary(
            potential_establishment_frame if not potential_establishment_frame.empty else selected_establishment_frame,
            social_acceptance_result,
            analysis_hex_area_km2,
        )
        wind_area_result_stats = energy_model_state.get("wind_area_result_stats")
        exact_wind_available_area = (
            float(wind_area_result_stats.get("potential_area_km2", 0.0) or 0.0)
            if isinstance(wind_area_result_stats, dict)
            else float(wind_stats_for_outside.get("available_candidate_area_km2", 0.0) or 0.0)
        )
        solar_area_result_stats = energy_model_state.get(
            "solar_area_result_stats"
        )
        exact_solar_available_area = (
            float(
                solar_area_result_stats.get("potential_area_km2", 0.0)
                or 0.0
            )
            if isinstance(solar_area_result_stats, dict)
            else float(
                solar_stats_for_outside.get(
                    "available_candidate_area_km2",
                    0.0,
                )
                or 0.0
            )
        )
        social_effect = (
            energy_model_state.get("social_acceptance_summary")
            if isinstance(
                energy_model_state.get("social_acceptance_summary"),
                dict,
            )
            else {}
        )
        wind_acceptance_ratio = social_effect.get(
            "wind_potential_acceptance_ratio",
            1.0,
        )
        solar_acceptance_ratio = social_effect.get(
            "solar_potential_acceptance_ratio",
            1.0,
        )
        combined_summaries = {
            item.technology_id: item
            for item in combined_execution_bundle.combined_result.technology_summaries
        }
        combined_wind_summary = combined_summaries["wind"]
        combined_solar_summary = combined_summaries["solar"]
        exact_wind_available_area = float(
            combined_wind_summary.potential_area_km2
        )
        exact_solar_available_area = float(
            combined_solar_summary.potential_area_km2
        )
        wind_acceptance_ratio = (
            float(combined_wind_summary.acceptance_adjusted_potential_area_km2)
            / max(exact_wind_available_area, 1e-12)
            if exact_wind_available_area > 0.0
            else 1.0
        )
        solar_acceptance_ratio = (
            float(combined_solar_summary.acceptance_adjusted_potential_area_km2)
            / max(exact_solar_available_area, 1e-12)
            if exact_solar_available_area > 0.0
            else 1.0
        )
        result_presentation = build_result_presentation_from_combined_summary(
            combined_execution_bundle.presentation,
            labels={"wind": "Vind", "solar": "Sol"},
        )
        energy_model_state["result_presentation"] = (
            serialize_result_presentation(result_presentation)
        )
        result_wind = result_technology(result_presentation, "wind")
        result_solar = result_technology(result_presentation, "solar")
        wind_outside_need_area = result_wind.outside_need_km2
        solar_outside_need_area = result_solar.outside_need_km2
        energy_model_state["outside_lp_shortage_stats"] = _outside_need_stats_from_areas(
            wind_outside_need_area,
            solar_outside_need_area,
            analysis_hex_area_km2,
        )
        energy_model_state["establishment_hex_stats"] = {
            "total_hex_count": int(len(selected_establishment_frame)),
            "black_hex_count": int(energy_model_state["outside_lp_shortage_stats"].get("total_shortage_hex_count", 0) or 0),
            "red_hex_count": int(class_counts.get("not_suitable", 0)),
            "wind_and_solar_hex_count": int(class_counts.get("wind_and_solar", 0)),
            "wind_only_hex_count": int(class_counts.get("wind_only", 0)),
            "solar_only_hex_count": int(class_counts.get("solar_only", 0)),
            "hex_area_km2": float(analysis_hex_area_km2),
            "h3_resolution": int(analysis_h3_resolution),
            "display_h3_resolution": int(h3_resolution),
        }
        combined_establishment_layers = _signed_combined_establishment_family_layers(
            region,
            combined_execution_bundle,
            social_acceptance_result,
            h3_resolution,
            zoom_family_enabled,
        )
        if combined_establishment_layers:
            energy_model_state["establishment_layer_visible"] = True
            layers.extend(combined_establishment_layers)
            combined_default_visible = any(
                layer.get("default_visible") is not False
                for layer in combined_establishment_layers
            )
            unified_notes.append(
                _t('{p0} visar potential efter aktiva filter: blå = vind, gul = sol, grön = båda, röd = inte lämplig.', p0=_t(COMBINED_ESTABLISHMENT_LAYER_LABEL))
            )
            if energy_model_state.get("available"):
                visibility_note = (
                    "visas från start"
                    if combined_default_visible
                    else "finns i lagerkontrollen men är släckt från start"
                )
                unified_notes.append(
                    _t('Vind- och solberäkningarna presenteras gemensamt genom {p0}, som {p1}.', p0=_t(COMBINED_ESTABLISHMENT_LAYER_LABEL), p1=_t(visibility_note))
                )
            if social_acceptance_result is not None and float(social_acceptance_impact_pct or 0.0) > 0.0:
                unified_notes.append(
                    _t('Acceptanspåverkan {p0:.0f}% tonar samma etableringsyta mot rött där syntetisk social acceptans är låg.', p0=float(social_acceptance_impact_pct))
                )
            if social_acceptance_result is not None and float(social_acceptance_allocation_priority_pct or 0.0) > 0.0:
                unified_notes.append(
                    _t('Acceptansstyrning {p0:.0f}% prioriterar scenarioytan inom potentialen där syntetisk social acceptans är hög.', p0=float(social_acceptance_allocation_priority_pct))
                )
        allocation_marker_layers = _signed_scenario_allocation_marker_family_layers(
            region,
            combined_execution_bundle,
            social_acceptance_result,
            h3_resolution,
            zoom_family_enabled,
            potential_layers=combined_establishment_layers,
        )
        if allocation_marker_layers:
            layers.extend(allocation_marker_layers)
            allocation_default_visible = any(
                layer.get("default_visible") is not False
                for layer in allocation_marker_layers
            )
            allocation_visibility_note = (
                "visas från start"
                if allocation_default_visible
                else "finns i lagerkontrollen men är släckt från start"
            )
            scenario_label = str(
                energy_model_state.get("scenario_label")
                or energy_model_state.get("scenario")
                or "valt scenario"
            )
            if not energy_model_state.get("capacity_based") or scenario_label == "Egen kapacitet":
                scenario_label = _t(_model_level_source(scenario_label))
            unified_notes.append(
                _t('{p0} {p1} för {p2}. Lagret visar scenariots placering som teknikfärgade kartceller: blå markerar vind, gulorange markerar sol och mörkgrön markerar båda i samma visningshex utan att påstå exakt fysisk överlappning.', p0=_t(SCENARIO_ALLOCATION_LAYER_LABEL), p1=_t(allocation_visibility_note), p2=scenario_label)
            )
        outside_lp_need_layers = _outside_lp_need_family_layers(
            region,
            energy_model_state.get("proposal_frame", pd.DataFrame()),
            energy_model_state.get("solar_proposal_frame", pd.DataFrame()),
            h3_resolution,
            zoom_family_enabled,
            analysis_h3_resolution,
            wind_outside_need_area,
            solar_outside_need_area,
        )
        if outside_lp_need_layers:
            layers.extend(outside_lp_need_layers)
            unified_notes.append(
                _t('{p0} visas som separata schematiska jämförelseytor utanför regionen när scenariot inte ryms inom landskapets potential.', p0=_t(OUTSIDE_LP_NEED_LAYER_LABEL))
            )
        _add_perf_timing(
            performance_log,
            "Gemensam etableringsyta",
            perf_started,
            f"visning R{h3_resolution}; analys R{analysis_h3_resolution}: {len(selected_establishment_frame)} hex",
        )
        _advance_calculation_progress(calc_progress, "Gemensam etableringsyta")

    if energy_model_state.get("available") and energy_model_state.get("establishment_layer_visible"):
        perf_started = _perf_start()
        energy_model_state["combined_establishment_stats"] = _combined_establishment_stats(energy_model_state)
        _add_perf_timing(performance_log, "Etableringsstatistik", perf_started)
        _advance_calculation_progress(calc_progress, "Etableringsstatistik")

    if social_layer_visible and social_acceptance_result is not None:
        unified_notes.append(
            _t("Det sociala acceptanslagret visar den tillämpade resultatkällans "
            "tillitsstatus och är inte regional acceptansevidens när källan "
            "är provisorisk.")
        )

    layers = _dedupe_layers(layers)
    if isinstance(energy_model_state, dict) and energy_model_state.get("available"):
        energy_model_state["map_layer_debug_rows"] = _map_layer_debug_rows(layers)
        energy_model_state["debug_layer_count"] = int(len(layers))
        energy_model_state["debug_counts"] = {
            "wind_proposal_hex": int(len(energy_model_state.get("proposal_frame", pd.DataFrame()))),
            "solar_proposal_hex": int(len(energy_model_state.get("solar_proposal_frame", pd.DataFrame()))),
            "solar_schematic_hex": int(len(solar_v1_analysis_frame)) if show_solar_v1 else 0,
            "solar_schematic_features": _feature_count(
                _solar_v1_layer(
                    f"{SOLAR_SMALL_SCALE_LABEL} (schablonhex)",
                    solar_v1_frame if show_solar_v1 else pd.DataFrame(),
                    h3_resolution,
                ).get("feature_collection")
            )
            if show_solar_v1
            else 0,
        }
    context_review_frame = (
        custom_wind_analysis_frame
        if not custom_wind_analysis_frame.empty
        else user_solar_analysis_frame
    )
    technology_context_review = _technology_context_review(
        context_review_frame
    )
    if technology_context_review:
        technology_context_review["resolution"] = int(
            analysis_h3_resolution
        )
        energy_model_state["technology_context_review"] = (
            technology_context_review
        )
        supplementary_count = int(
            technology_context_review.get("full_lablab_cell_count", 0)
            or 0
        )
        unknown_count = int(
            technology_context_review.get("not_assessed_cell_count", 0)
            or 0
        )
        if supplementary_count or unknown_count:
            unknown_area = float(
                technology_context_review.get(
                    "not_assessed_area_km2",
                    0.0,
                )
                or 0.0
            )
            unified_notes.append(
                _t('Teknikdomänen i R{p0} går ända till den verifierade regionsgränsen. {p1} celler har kompletterande landskapskontext och {p2} celler ({p3:.3f} km²) saknar teknisk landskapskontext. Den separata kartan med landskapstyper kan ha annan täckning. Standardtabeller och femgruppsmått behåller sin deklarerade standarddomän.', p0=analysis_h3_resolution, p1=supplementary_count, p2=unknown_count, p3=unknown_area)
            )
    display_layers = _dedupe_layers(
        [
            *layers,
            *landscape_display_layers,
            *(
                [social_acceptance_display_layer]
                if social_acceptance_display_layer is not None
                else []
            ),
        ]
    )
    layer_control_count = len(
        _layer_control_rows(display_layers, "combined")
    )
    note_body = _workspace_map_note(energy_model_state, layer_control_count)
    perf_started = _perf_start()
    _render_layers(
        region,
        display_layers,
        opacity,
        map_state_key=f"{region.get('region_id', 'region')}:workspace:{MAP_STATE_VERSION}" if preserve_map_view else None,
        map_reset_token=map_reset_token,
        opacity_key_prefix="combined",
        note_title="Gemensam potentialvy",
        note_body=note_body,
    )
    _render_workspace_scenario_mix_control(
        region, review_readiness, access_readiness=access_readiness,
    )
    _add_perf_timing(
        performance_log,
        "Karta HTML och rendering",
        perf_started,
        f"{len(display_layers)} lager",
    )
    _advance_calculation_progress(calc_progress, "Karta HTML och rendering")
    _loading_phase("loading.results")
    _record_performance_history(performance_bucket, performance_log)
    energy_model_state["performance_diagnostics"] = _performance_diagnostic_rows(performance_log, performance_estimates)
    geography_filter_arguments = dict(
        show_user_wind=bool(show_user_wind),
        wind_selected_layers=wind_selected_layers,
        wind_ui_params=wind_ui_params,
        wind_unfiltered_land=bool(custom_wind_preview_state.get("unfiltered_land", False)) if isinstance(custom_wind_preview_state, dict) else False,
        show_user_solar=bool(show_user_solar),
        show_solar_v1=bool(show_solar_v1),
        solar_large_population_active=bool(solar_large_population_active),
        solar_large_population_layer_ids=list(
            solar_large_population_layer_ids
        ),
        solar_large_unfiltered_land_active=bool(applied_solar_config.get("large_unfiltered_land_active", False)),
        solar_params=solar_params,
        solar_large_filter_configs=solar_large_filter_configs,
        solar_v1_area_m2_per_person=solar_v1_area_m2_per_person,
    )
    geography_filter_notes = _geography_filter_notes(**geography_filter_arguments)
    geography_effect_notes = _geography_effect_notes(energy_model_state)
    st.session_state[WORKSPACE_RENDER_CACHE_KEY] = {
        "fingerprint": workspace_fingerprint,
        "layers": layers,
        "note_body": note_body,
        "layer_control_count": layer_control_count,
        "performance_log": performance_log,
        "energy_model_state": energy_model_state,
        "map_state": {
            "layers": layers,
            "potential_frames": potential_frames,
            "resolution": h3_resolution,
            "analysis_resolution": analysis_h3_resolution,
            "resolution_info": resolution_info,
            "opacity_key_prefix": "combined",
            "geography_filter_notes": geography_filter_notes,
            "geography_filter_arguments": geography_filter_arguments,
            "geography_effect_notes": geography_effect_notes,
            "establishment_hex_stats": energy_model_state.get("establishment_hex_stats"),
        },
    }

    summary_target = right_panel or st.container()
    with summary_target:
        st.markdown('<span data-potential-tutorial-anchor="right-panel"></span>', unsafe_allow_html=True)
        _render_establishment_focus(
            energy_model_state,
            lambda: _combined_summary(
                {
                    "layers": layers,
                    "potential_frames": potential_frames,
                    "resolution": h3_resolution,
                    "analysis_resolution": analysis_h3_resolution,
                    "resolution_info": resolution_info,
                    "opacity_key_prefix": "combined",
                    "geography_filter_notes": geography_filter_notes,
                    "geography_effect_notes": geography_effect_notes,
                    "establishment_hex_stats": energy_model_state.get("establishment_hex_stats"),
                }
            ),
        )
        with st.expander(_t("Debug och prestanda"), expanded=False):
            _render_workspace_debug_status(region)
            _data_method(region)
            _render_performance_log(performance_log)
            st.markdown(f"**{_t('Aktiva beräkningar')}**")
            performance_diagnostics = energy_model_state.get("performance_diagnostics") if isinstance(energy_model_state, dict) else None
            if isinstance(performance_diagnostics, list) and performance_diagnostics:
                diagnostic_frame = pd.DataFrame(performance_diagnostics)
                st.caption(
                    _t("Prestandadiagnostik för optimering. Faktisk tid visas per steg och jämförs med historisk median när appen har hunnit samla körhistorik.")
                )
                st.dataframe(
                    _display_dataframe(diagnostic_frame.head(8)),
                    width="stretch",
                    hide_index=True,
                    height=min(344, 72 + 32 * min(8, len(diagnostic_frame))),
                )
                slowest_step = performance_diagnostics[0]
                st.caption(
                    _t('Långsammaste steg denna körning: {p0} ({p1:.1f} s).', p0=_t(slowest_step.get('steg', '-')), p1=float(slowest_step.get('tid_s', 0.0) or 0.0))
                )
            if isinstance(energy_model_state, dict) and energy_model_state.get("available"):
                if energy_model_state["scenario_request"].get("capacity_mw_by_technology") is not None:
                    st.caption(_t("Senaste kapacitetsberäkning: {p0} · {p1:g} MW vind / {p2:g} MW marksol.",
                                  p0=energy_model_state.get("debug_run_id", "-"),
                                  p1=energy_model_state["capacity_mw"]["wind"],
                                  p2=energy_model_state["capacity_mw"]["solar"]))
                else:
                    st.caption(
                        _t('Senaste energiberäkning: {p0} · scenario {p1} · mix {p2:.0f}% vind / {p3:.0f}% sol.', p0=energy_model_state.get('debug_run_id', '-'), p1=energy_model_state.get('scenario', '-') if energy_model_state.get('capacity_based') else _t(_model_level_source(energy_model_state.get('scenario', '-'))), p2=float(energy_model_state.get('wind_share_pct', 0.0) or 0.0), p3=float(energy_model_state.get('solar_share_pct', 0.0) or 0.0))
                    )
                debug_counts = energy_model_state.get("debug_counts")
                if isinstance(debug_counts, dict):
                    count_rows = [
                        {"mått": "vindförslag hex", "antal": int(debug_counts.get("wind_proposal_hex", 0) or 0)},
                        {"mått": "solförslag hex", "antal": int(debug_counts.get("solar_proposal_hex", 0) or 0)},
                        {"mått": "småskalig schablon rader", "antal": int(debug_counts.get("solar_schematic_hex", 0) or 0)},
                        {"mått": "småskalig schablon features i karta", "antal": int(debug_counts.get("solar_schematic_features", 0) or 0)},
                    ]
                    st.dataframe(_display_dataframe(pd.DataFrame(count_rows)), width="stretch", hide_index=True, height=176)
                layer_debug_rows = energy_model_state.get("map_layer_debug_rows")
                if isinstance(layer_debug_rows, list) and layer_debug_rows:
                    debug_frame = pd.DataFrame(layer_debug_rows)
                    st.caption(_t("Kartlager i senaste HTML-renderingen."))
                    st.dataframe(_display_dataframe(debug_frame), width="stretch", hide_index=True, height=min(360, 72 + 32 * len(debug_frame)))
            if show_user_solar:
                st.metric(_t('Aktiv {p0}', p0=_t(SOLAR_LARGE_SCALE_LABEL)), _t("På"))
                st.caption(_t('{p0} visas som solpolygon och kan ingå i {p1}.', p0=_t(SOLAR_LARGE_SCALE_LABEL), p1=_t(COMBINED_ESTABLISHMENT_LAYER_LABEL)))
            if show_solar_v1:
                stats = energy_model_state.get("solar_v1_stats") if isinstance(energy_model_state, dict) else None
                st.metric(_t('Aktiv {p0}', p0=_t(SOLAR_SMALL_SCALE_LABEL)), _t("På"))
                st.caption(_t(_solar_v1_formula_text(region, solar_v1_area_m2_per_person)))
                st.caption(_t(_solar_v1_population_source_status(region)))
                if isinstance(stats, dict):
                    st.caption(
                        _t('Total småskalig solyta: {p0:.2f} km²; solbehov efter tak: {p1:.2f} km².', p0=float(stats.get('total_area_km2', 0.0) or 0.0), p1=float(stats.get('remaining_area_km2', 0.0) or 0.0))
                    )
            if show_user_solar:
                if solar_large_population_active:
                    st.caption(
                        _t('Avstånd till befolkning är {p0:.0f} m för storskalig sol.', p0=float(solar_params.get('population_buffer_m', 250.0) or 250.0))
                    )
                for filter_config in solar_large_filter_configs:
                    group_id = str(filter_config.get("group_id", ""))
                    label = str(
                        filter_config.get("label")
                        or _solar_filter_display_label(group_id)
                    )
                    layer_count = len(list(filter_config.get("layer_ids") or []))
                    layer_labels = [str(value) for value in (filter_config.get("layer_labels") or [])]
                    layer_text = f": {', '.join(layer_labels[:4])}{'...' if len(layer_labels) > 4 else ''}" if layer_labels else ""
                    st.caption(
                        _t('{p0}: {p1} del-lager är aktiva med {p2:.0f} m buffert{p3}.', p0=_t(label), p1=layer_count, p2=float(filter_config.get('buffer_m', 0.0) or 0.0), p3=layer_text)
                    )
            if show_user_wind and custom_wind_preview_state is not None:
                _render_wind_preview_diagnostics(
                    energy_model_state.get("wind_preview_diagnostics")
                )
                if wind_controls_applied:
                    st.caption(ui_text("controls_applied", _wind_control_language()))
            for note in unified_notes:
                st.caption(_t(note))


def _presentation_configuration(region_id: str) -> dict[str, Any]:
    """Cheap local configuration identity; never probes or acquires GIS inputs."""
    pending = [
        REPO_ROOT / "regions" / region_id / "region.json",
        REPO_ROOT / "regions" / region_id / "region-profile.json",
        REPO_ROOT / "regions" / "index.json",
    ]
    files: dict[str, str] = {}
    while pending:
        path = pending.pop().resolve()
        if REPO_ROOT not in path.parents or not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative in files:
            continue
        data = path.read_bytes()
        files[relative] = hashlib.sha256(data).hexdigest()
        try:
            document = json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        values = [document]
        while values:
            value = values.pop()
            if isinstance(value, dict):
                values.extend(value.values())
            elif isinstance(value, list):
                values.extend(value)
            elif isinstance(value, str) and value.endswith(".json"):
                pending.append(REPO_ROOT / value)
    connection_fields = sorted(
        (key, value) for key, value in os.environ.items()
        if key == "DATABASE_URL" or key.startswith("SPEEDLOCAL_DATABASE_URL_")
    )
    # A one-way identity detects connection changes without retaining credentials.
    connection_identity = _canonical_payload_signature(connection_fields)
    return {"repository_files": files, "connection_identity": connection_identity}


def _presentation_binding(
    route: WorkspaceRouteDecision,
    region_id: str,
    configuration: dict[str, Any] | None = None,
) -> Any:
    requests = {
        str(key): st.session_state[key]
        for key in st.session_state
        if str(key).startswith("workspace_ui:") and ":applied_request" in str(key)
    }
    return build_presentation_binding(
        region_id, str(route.access_scope), WORKSPACE_CALCULATION_VERSION,
        configuration=configuration if configuration is not None else _presentation_configuration(region_id),
        applied_state=requests,
    )


def _refresh_workspace_inputs() -> None:
    _clear_ui_only_rerun()
    st.session_state.pop(WORKSPACE_PRESENTATION_SNAPSHOT_KEY, None)


def _preserve_presentation_drafts() -> None:
    """Keep scoped drafts when an old/configuration-changed view omits widgets."""
    for key in list(st.session_state):
        name = str(key)
        if name.startswith("workspace_ui:") and (
            ":draft:" in name or ":technology_share:" in name
        ):
            st.session_state[key] = st.session_state[key]


def _render_workspace_debug_status(region: dict[str, Any]) -> None:
    """Expose cached diagnostic facts without acquiring or verifying inputs."""
    cache = st.session_state.get(WORKSPACE_RENDER_CACHE_KEY)
    map_state = cache.get("map_state", {}) if isinstance(cache, dict) else {}
    resolution = map_state.get("analysis_resolution", region.get("default_h3_resolution"))
    st.caption(_t("debug.coordinates", resolution=resolution, crs=region.get("native_crs", "TBD")))
    energy = cache.get("energy_model_state", {}) if isinstance(cache, dict) else {}
    model_resolution = energy.get("analysis_h3_resolution", resolution) if isinstance(energy, dict) else resolution
    st.caption(_t("analysis.exact_area", p0=model_resolution))
    access = region.get("review_access")
    if isinstance(access, dict):
        st.caption(_t("debug.access", classification=access.get("access_classification", "-")))
    snapshot = st.session_state.get(WORKSPACE_PRESENTATION_SNAPSHOT_KEY)
    if isinstance(snapshot, PresentationSnapshot):
        verified = datetime.fromisoformat(snapshot.verified_at_utc).strftime("%Y-%m-%d %H:%M UTC")
        st.caption(_t("Senast verifierat: {p0}.", p0=verified))
    st.button(_t("Uppdatera underlag"), key="presentation_refresh", on_click=_refresh_workspace_inputs)
    st.markdown(_t('Planerad framtida regional dataleverantör: [IVL Svenska Miljöinstitutet]({p0})', p0=IVL_PROVIDER_URL))


def _render_presentation_workspace(
    route: WorkspaceRouteDecision, region: dict[str, Any],
) -> None:
    """Change presentation only, retaining the original verification age."""
    snapshot = st.session_state.get(WORKSPACE_PRESENTATION_SNAPSHOT_KEY)
    binding = _presentation_binding(route, str(region["region_id"]))
    freshness = snapshot.freshness(binding) if isinstance(snapshot, PresentationSnapshot) else None
    if freshness is None or not freshness.can_render:
        _preserve_presentation_drafts()
        st.warning(_t("freshness.open_analysis"))
        st.button(_t("Uppdatera underlag"), key="presentation_refresh",
                  on_click=_refresh_workspace_inputs, type="primary")
        _clear_ui_only_rerun()
        return
    previous_region = snapshot.payload["region"]
    left_panel, main_panel, right_panel = _workspace_shell()
    with main_panel:
        # Match the ordinary path's header/status slots so an Apply rerun
        # replaces the old header before streaming calculation progress.
        _workspace_header()
        _render_workspace_intro(previous_region)
        with st.container(key="workspace_presentation_status"):
            if freshness.status == "configuration_changed":
                st.warning(_t("Underlaget har ändrats sedan resultatet beräknades. Uppdatera underlaget innan du använder resultatet som aktuellt."))
                st.button(_t("Uppdatera underlag"), key="presentation_refresh_required",
                          on_click=_refresh_workspace_inputs)
            elif freshness.status == "expired":
                st.warning(_t("freshness.expired"))
                st.button(_t("Uppdatera underlag"), key="presentation_refresh_expired",
                          on_click=_refresh_workspace_inputs)
        try:
            if freshness.status == "configuration_changed":
                _preserve_presentation_drafts()
                with replay_presentation_dependencies(snapshot.dependencies):
                    _render_reused_workspace_outputs(
                        snapshot.payload["workspace_cache"], previous_region,
                        _current_opacity("combined"), True, _map_view_reset_token(),
                        right_panel, snapshot.payload["access_readiness"],
                        snapshot.payload.get("landscape_display_layers"),
                        snapshot.payload.get("social_acceptance_display_layer"),
                        snapshot.payload["review_readiness"], show_scenario_mix=False,
                    )
            else:
                _render_presentation_workspace_snapshot(snapshot, previous_region, left_panel, right_panel)
        except MissingPresentationDependency:
            _preserve_presentation_drafts()
            feedback = current_loading()
            if feedback is not None:
                feedback.unavailable()
            # A missing display dependency must never fall through to an input reader.
            st.warning(_t("freshness.open_analysis"))
            st.button(_t("Uppdatera underlag"), key="presentation_refresh_missing_dependency",
                      on_click=_refresh_workspace_inputs)
        finally:
            _clear_ui_only_rerun()
    if snapshot.payload["review_readiness"] is None:
        force_tutorial_open = _render_tutorial_launcher(previous_region, st.sidebar)
        _render_tutorial_component(previous_region, force_open=force_tutorial_open)


def _render_presentation_workspace_snapshot(
    snapshot: PresentationSnapshot,
    region: dict[str, Any],
    left_panel: Any | None,
    right_panel: Any | None,
) -> None:
    render = snapshot.payload
    access_readiness = render["access_readiness"]
    review_readiness = render["review_readiness"]
    analysis_h3_resolution = int(render["analysis_h3_resolution"])
    region_id = str(region["region_id"])
    scenario_identity = _workspace_ui_identity(region_id, SCENARIO_CAPABILITY_ID)
    solar_identity = _workspace_ui_identity(region_id, "solar")
    social_identity = _workspace_ui_identity(region_id, SOCIAL_ACCEPTANCE_CAPABILITY_ID)
    scenario_readiness = _workspace_scenario_readiness(region_id, review_readiness, access_readiness)
    social_readiness = _workspace_social_acceptance_readiness(region_id, review_readiness, access_readiness)
    scenario_result = render["scenario_result"]
    social_acceptance_result = render["social_acceptance_result"]
    applied_solar_config = dict(render["applied_solar_config"])
    active_solar_count = _count_enabled(
        bool(applied_solar_config.get("large_scale_active")),
        bool(applied_solar_config.get("small_population_active")),
    )
    landscape_display_error = render.get("landscape_display_error")
    cache = render["workspace_cache"]
    energy_model_state = cache["energy_model_state"]
    with replay_presentation_dependencies(snapshot.dependencies):
        if left_panel is not None:
            with left_panel.expander(_t('Geografier'), expanded=False, key='workspace_geographies_panel'):
                if landscape_display_error is not None:
                    st.info(_t('Landskapstyper kunde inte valideras och visas inte i kartan.'))
                    st.caption(_t('Teknisk orsak: {p0}', p0=landscape_display_error))
                with st.expander(_t(WIND_LANDSCAPE_POTENTIAL_LABEL), expanded=False, key='workspace_wind_panel'):
                    wind_identity = _workspace_ui_identity(region_id, 'wind')
                    wind_applied_request, wind_controls_applied = _render_workspace_analysis_controls(wind_identity, access_readiness)
                    if wind_applied_request is None:
                        raise ValueError('The product workspace has no applied wind request')
                    wind_selected_layers, wind_ui_params = _wind_workspace_request_values(wind_applied_request)
                    if not wind_applied_request.groups:
                        st.caption(_t('Inga vindfilter är valda: ofiltrerad vindpotential används som startläge.'))
                    _render_wind_map_review_controls(region, wind_selected_layers)
                with st.expander(_t(SOLAR_LANDSCAPE_POTENTIAL_LABEL), expanded=active_solar_count > 0, key='workspace_solar_panel'):
                    solar_applied_request, solar_controls_applied = _render_workspace_analysis_controls(solar_identity, access_readiness)
                    if solar_applied_request is None:
                        raise ValueError('The product workspace has no applied solar request')
                    if solar_controls_applied:
                        _preserve_solar_map_review_widget_state(region_id)
                        st.rerun()
                    applied_solar_config = dict(render['applied_solar_config'])
                    _render_solar_map_review_controls(region, applied_solar_config)
            with left_panel.expander(_t('Energimodellering'), expanded=False, key='workspace_energy_panel'):
                st.caption(_t('Levereras av EML'))
                st.markdown(_t('[Energy Modelling Lab]({p0})', p0=EML_PROVIDER_URL))
                if 'capacity_references' in energy_model_state and energy_model_state.get('available') and energy_model_state.get('capacity_based'):
                    _render_workspace_capacity_controls(scenario_identity, energy_model_state)
                scenario_request, scenario_controls_applied = _render_workspace_scenario_controls(scenario_identity, scenario_readiness)
                if scenario_controls_applied:
                    st.rerun()
                if scenario_result is not None:
                    _render_workspace_scenario_result_summary(scenario_result)
                if (
                    not energy_model_state.get('capacity_based')
                    and energy_model_state.get('rooftop_solar', {}).get('status') == 'unavailable'
                ):
                    st.caption(_t('Taksol: data saknas. Hela solbehovet räknas därför som marksol; inget taksolsbidrag dras av.'))
                rooftop_twh = float(energy_model_state.get('solar_rooftop_twh', 0.0) or 0.0)
                if rooftop_twh > 0.0:
                    st.caption(_t('Taksolschablonen bidrar med {p0:.2f} TWh. Kvar för marksol: {p1:.2f} TWh och {p2:.2f} km².', p0=rooftop_twh, p1=float(energy_model_state['solar_ground_twh']), p2=float(energy_model_state['solar_area_need_km2'])))
            with left_panel.expander(_t('Social acceptans'), expanded=False, key='workspace_social_panel'):
                social_acceptance_request, social_controls_applied = _render_workspace_social_acceptance_controls(social_identity, social_readiness, target_resolution=int(analysis_h3_resolution))
                if social_controls_applied:
                    st.rerun()
                if social_acceptance_result is not None:
                    _render_workspace_social_acceptance_result_summary(social_acceptance_result)

        _render_reused_workspace_outputs(
            cache,
            region,
            _current_opacity("combined"),
            True,
            _map_view_reset_token(),
            right_panel,
            access_readiness,
            render.get("landscape_display_layers"),
            render.get("social_acceptance_display_layer"),
            review_readiness,
        )


def main() -> None:
    st.session_state[APP_LANGUAGE_KEY] = _language()
    st.set_page_config(page_title=f"{_t(PAGE_TITLE)} · {APP_RELEASE_STAGE}", layout="wide", initial_sidebar_state="collapsed")
    # A fixed slot precedes workspace acquisition and is reserved on every route.
    loading_slot = st.empty()
    query_region = _query_param_value("region")
    query_mode = _query_param_value("mode")
    query_view = _query_param_value("view")
    if gate1_review_enabled(
        query_view=query_view,
        environment_value=os.environ.get(GATE1_REVIEW_ENV),
    ):
        _render_gate1_review(query_region)
        return
    if gate2_review_enabled(
        query_view=query_view,
        environment_value=os.environ.get(GATE2_REVIEW_ENV),
    ):
        _render_gate2_review(query_region)
        return
    route = resolve_catalog_workspace_route(
        review_allowlist=_local_review_allowlist(),
        query_region=query_region,
        query_mode=query_mode,
        query_view=query_view,
        session_region=st.session_state.get(REGION_SELECT_KEY),
    )
    if route.kind in {"landing", "invalid_explicit"}:
        st.session_state.pop("potential_pending_scenario_mix", None)
        _render_region_landing()
        return

    if (_presentation_only_rerun_requested()
            and st.session_state.get(REGION_SESSION_SCOPE_KEY) == route.access_scope):
        _render_workspace_operation(route, None)
        return
    feedback = LoadingFeedback(loading_slot, _language())
    with active_loading(feedback):
        try:
            _render_workspace_operation(route, feedback)
        except StopException:
            feedback.unavailable()
            raise
        except Exception:
            feedback.error()
            raise


def _collapse_sidebar_on_workspace_entry() -> None:
    """Override a saved browser preference once, retaining manual changes afterward."""
    if SIDEBAR_ENTRY_KEY not in st.session_state:
        st.session_state[SIDEBAR_ENTRY_KEY] = uuid4().hex
    entry_token = json.dumps(st.session_state[SIDEBAR_ENTRY_KEY])
    st.sidebar.html(
        """<script>
(() => {
  const token = __ENTRY_TOKEN__;
  const previous = window.__speedlocalSidebarEntry;
  if (previous?.token === token) return;
  previous?.stop();
  let observer;
  let timeout;
  const entry = {token, stop: () => {
    observer?.disconnect();
    clearTimeout(timeout);
  }};
  window.__speedlocalSidebarEntry = entry;
  const collapse = () => {
    const sidebar = document.querySelector('[data-testid="stSidebar"]');
    if (!sidebar) return;
    if (sidebar.getAttribute('aria-expanded') === 'true') {
      const button = sidebar.querySelector('[data-testid="stSidebarCollapseButton"] button');
      if (!button) return;
      button.click();
    } else if (sidebar.getAttribute('aria-expanded') !== 'false') {
      return;
    }
    entry.stop();
    return true;
  };
  if (collapse()) return;
  observer = new MutationObserver(collapse);
  observer.observe(document.body, {childList: true, subtree: true, attributes: true,
    attributeFilter: ['aria-expanded']});
  timeout = setTimeout(entry.stop, 10000);
})();
</script>""".replace("__ENTRY_TOKEN__", entry_token),
        unsafe_allow_javascript=True,
    )


def _render_workspace_operation(
    route: WorkspaceRouteDecision, feedback: LoadingFeedback | None,
) -> None:
    presentation_only = feedback is None
    region = _active_region(route)
    region_id = str(region.get("region_id") or "").strip().lower()
    _collapse_sidebar_on_workspace_entry()
    if route.kind == "review":
        _render_local_review_sidebar(region)
    else:
        _render_region_switcher(region)
    _render_language_switcher(st.sidebar)

    if presentation_only:
        _render_presentation_workspace(route, region)
        return
    if feedback is None:
        raise ValueError("An analysis operation requires loading feedback")
    # A failed ordinary verification must not leave an older snapshot available
    # for a later presentation change. A completed operation stores its own snapshot.
    st.session_state.pop(WORKSPACE_PRESENTATION_SNAPSHOT_KEY, None)
    with capture_presentation_dependencies() as dependencies:
        configuration = _presentation_configuration(region_id)
        payload = _render_verified_workspace(route, region)
        if payload is not None:
            binding = _presentation_binding(route, region_id, configuration)
            st.session_state[WORKSPACE_PRESENTATION_SNAPSHOT_KEY] = create_presentation_snapshot(
                binding, dependencies, payload,
                verified_at_monotonic=payload["verified_at_monotonic"],
                verified_at_utc=payload["verified_at_utc"],
            )
    if payload is None:
        feedback.unavailable()
    else:
        feedback.finish()


def _render_verified_workspace(
    route: WorkspaceRouteDecision, region: dict[str, Any],
) -> dict[str, Any] | None:
    """Ordinary analysis path; source freshness and GIS checks stay intact."""
    region_id = str(region.get("region_id") or "").strip().lower()
    st.session_state.pop(WORKSPACE_PRESENTATION_BUILD_KEY, None)
    access_scope = str(route.access_scope or "")
    readiness_snapshot_token = runtime_readiness_snapshot_token(region_id)
    verified_at_monotonic = time.monotonic()
    verified_at_utc = datetime.now(timezone.utc).isoformat()
    access_readiness = _workspace_access_readiness(
        region_id,
        access_scope,
        readiness_snapshot_token,
    )
    review_readiness = access_readiness.review
    if region_id != "bornholm":
        _apply_pending_workspace_scenario_mix(region_id, access_scope)
    context = (
        _review_workspace_context(review_readiness)
        if review_readiness is not None and not catalog_context_runtime_declared(region_id)
        else _load_context(region)
    )
    if region_id == "bornholm":
        # The existing loader verifies current region, source and runtime identity.
        # Use that same operation's snapshot for both Apply and reference marks.
        if context.get("runtime_ready"):
            contract = load_catalog_scenario_contract(region_id)
            if _uses_independent_capacity(contract):
                context["capacity_references"] = _capacity_reference_values(
                    contract, context["context_inputs"].scenario,
                )
        _apply_pending_workspace_scenario_mix(
            region_id, access_scope, capacity_references=context.get("capacity_references"),
        )
    left_panel, main_panel, right_panel = _workspace_shell()

    if review_readiness is not None:
        h3_resolution = _local_review_default_h3_resolution(
            str(region.get("region_id") or "").strip().lower()
        )
    else:
        h3_resolution = _zoom_family_base_resolution(region)
    with main_panel:
        _workspace_header()
        _render_workspace_intro(region)
        # Reserve the same slot used for language-snapshot freshness feedback.
        st.container(key="workspace_presentation_status")
        _unified_workspace_tab(
            region,
            context,
            left_panel,
            right_panel,
            review_readiness,
            access_readiness,
            target_resolution=h3_resolution,
            runtime_snapshot_token=readiness_snapshot_token,
        )
    # Forms have now applied their validated requests. Bind presentation metadata
    # to the resulting scenario/year, including the current capacity-model mix.
    scenario_state = _workspace_scenario_header_state(
        region,
        review_readiness,
        access_readiness,
    )
    force_tutorial_open = False
    if review_readiness is None:
        force_tutorial_open = _render_tutorial_launcher(region, st.sidebar)
    if review_readiness is None:
        _render_tutorial_component(region, force_open=force_tutorial_open)

    prepared = st.session_state.pop(WORKSPACE_PRESENTATION_BUILD_KEY, None)
    cache = st.session_state.get(WORKSPACE_RENDER_CACHE_KEY)
    if not isinstance(prepared, dict) or not isinstance(cache, dict):
        return None
    return {
        **prepared,
        "region": region,
        "access_readiness": access_readiness,
        "review_readiness": review_readiness,
        "scenario_state": scenario_state,
        "h3_resolution": h3_resolution,
        "workspace_cache": cache,
        "verified_at_monotonic": verified_at_monotonic,
        "verified_at_utc": verified_at_utc,
    }


if __name__ == "__main__":
    with postgis_input_operation(), social_acceptance_signature_operation(), area_clipping_operation():
        main()
