from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from .contracts import (
    STANDARD_GROUP_IDS,
    SUPPORTED_GEOMETRY_FAMILIES,
    SUPPORTED_OPERATIONS,
    AnalysisContract,
    LayerContract,
    RegionGeographyContract,
)
from .sources import (
    LayerAssets,
    detect_geojson_geometry_family,
    detect_geometry_family,
    detect_layer_geometry_family,
    read_layer_geojson,
    resolve_layer_assets,
    resolve_layer_source_assets,
    technology_support_domain_for_eligible_surface,
)


@dataclass(frozen=True)
class ValidatedLayer:
    contract: LayerContract
    assets: LayerAssets
    geometry_family: str
    processing_adapter: str
    geometry_validation: str


def _is_lower_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _is_safe_provider_path(value: str) -> bool:
    if not value.strip() or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts


def validate_region_geography_contract(
    contract: RegionGeographyContract,
) -> None:
    if contract.schema_version != "1.0":
        raise ValueError(
            "Unsupported region geography schema version: "
            f"{contract.schema_version}"
        )
    if not contract.region_id.strip():
        raise ValueError("Region geography region_id is required")
    if not contract.native_crs.strip():
        raise ValueError("Region geography native_crs is required")
    if not contract.geographies:
        raise ValueError("Region geography must declare at least one geography")
    if not contract.analysis_domains and not contract.technology_support_domains:
        raise ValueError(
            "Region geography must declare at least one analysis or technology "
            "support domain"
        )

    supported_roles = {
        "administrative_boundary",
        "regional_identity_surface",
        "analysis_surface",
        "technology_target_surface",
        "hydrographic_exclusion",
        "surface_component",
    }
    supported_formats = {"geojson", "gpkg", "parquet"}
    supported_provenance = {
        "source_snapshot_pinned",
        "processed_snapshot_only",
    }
    supported_water_policies = {
        "exclude_all_water",
        "exclude_sea_retain_inland_water",
        "include_water",
    }
    for geography_id, geography in contract.geographies.items():
        if geography.id != geography_id or not geography_id.strip():
            raise ValueError(
                "Region-geography ids must be non-blank and match their keys"
            )
        for label, value in (
            ("label", geography.label),
            ("provider", geography.provider),
            ("path", geography.path),
            ("source_crs", geography.source_crs),
            ("native_crs", geography.native_crs),
        ):
            if not value.strip():
                raise ValueError(
                    f"Region geography {geography_id} {label} is required"
                )
        if geography.role not in supported_roles:
            raise ValueError(
                f"Region geography {geography_id} has unsupported role: "
                f"{geography.role}"
            )
        if geography.format not in supported_formats:
            raise ValueError(
                f"Region geography {geography_id} has unsupported format: "
                f"{geography.format}"
            )
        if geography.geometry_family != "polygon":
            raise ValueError(
                f"Region geography {geography_id} must be polygonal"
            )
        if geography.native_crs != contract.native_crs:
            raise ValueError(
                f"Region geography {geography_id} native CRS must match the "
                "region geography contract"
            )
        if geography.role in {"analysis_surface", "technology_target_surface"}:
            if geography.water_policy not in supported_water_policies:
                raise ValueError(
                    f"Region geography {geography_id} analysis surface must "
                    "declare a supported water_policy"
                )
        elif geography.water_policy is not None:
            raise ValueError(
                f"Region geography {geography_id} role {geography.role!r} "
                "must not declare water_policy"
            )
        if not _is_safe_provider_path(geography.path):
            raise ValueError(
                f"Region geography {geography_id} path must be a safe "
                "provider-relative path"
            )
        if not _is_lower_sha256(geography.sha256):
            raise ValueError(
                f"Region geography {geography_id} sha256 is invalid"
            )

        metadata = geography.source_metadata
        for label, value in (
            ("authority", metadata.authority),
            ("dataset_name", metadata.dataset_name),
            ("dataset_version", metadata.dataset_version),
            ("snapshot_date", metadata.snapshot_date),
            ("license", metadata.license),
            ("derivation", metadata.derivation),
        ):
            if not value.strip():
                raise ValueError(
                    f"Region geography {geography_id} source {label} is required"
                )
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", metadata.snapshot_date) is None:
            raise ValueError(
                f"Region geography {geography_id} snapshot_date must use YYYY-MM-DD"
            )
        if metadata.provenance_status not in supported_provenance:
            raise ValueError(
                f"Region geography {geography_id} has unsupported provenance status"
            )
        if not metadata.upstream_inputs:
            raise ValueError(
                f"Region geography {geography_id} must declare upstream inputs"
            )
        upstream_names: set[str] = set()
        for upstream in metadata.upstream_inputs:
            if not upstream.dataset_name.strip() or not upstream.role.strip():
                raise ValueError(
                    f"Region geography {geography_id} upstream input identity "
                    "and role are required"
                )
            if upstream.dataset_name in upstream_names:
                raise ValueError(
                    f"Region geography {geography_id} contains duplicate "
                    f"upstream input: {upstream.dataset_name}"
                )
            upstream_names.add(upstream.dataset_name)
            if upstream.checksum_status not in {
                "pinned",
                "pending_source_snapshot",
            }:
                raise ValueError(
                    f"Region geography {geography_id} upstream checksum status "
                    "is unsupported"
                )
            if upstream.checksum_status == "pinned":
                if upstream.sha256 is None or not _is_lower_sha256(
                    upstream.sha256
                ):
                    raise ValueError(
                        f"Region geography {geography_id} pinned upstream input "
                        "requires a valid sha256"
                    )
            elif upstream.sha256 is not None:
                raise ValueError(
                    f"Region geography {geography_id} pending upstream input "
                    "must not claim a sha256"
                )

    for domain_id, domain in contract.analysis_domains.items():
        if domain.id != domain_id or not domain_id.strip():
            raise ValueError(
                "Region analysis-domain ids must be non-blank and match their keys"
            )
        if not domain.label.strip() or not domain.domain_scope.strip():
            raise ValueError(
                f"Region analysis domain {domain_id} label and scope are required"
            )
        if domain.status not in {"candidate", "active"}:
            raise ValueError(
                f"Region analysis domain {domain_id} status is invalid"
            )
        if domain.purpose != "standard_group_analysis":
            raise ValueError(
                f"Region analysis domain {domain_id} purpose is unsupported"
            )
        coverage_geometry = contract.geographies.get(
            domain.coverage_geometry_id
        )
        if coverage_geometry is None:
            raise ValueError(
                f"Region analysis domain {domain_id} references an undeclared "
                "coverage geometry"
            )
        if coverage_geometry.geometry_family != "polygon":
            raise ValueError(
                f"Region analysis domain {domain_id} coverage must be polygonal"
            )
        if coverage_geometry.role != "analysis_surface":
            raise ValueError(
                f"Region analysis domain {domain_id} coverage geometry must "
                "have role analysis_surface"
            )
        if domain.coverage_rule != "positive_area_intersection":
            raise ValueError(
                f"Region analysis domain {domain_id} must use "
                "positive_area_intersection"
            )
        if domain.empty_intersection_policy != "exclude":
            raise ValueError(
                f"Region analysis domain {domain_id} empty intersections must "
                "be excluded"
            )
        if domain.missing_observation_policy != "error":
            raise ValueError(
                f"Region analysis domain {domain_id} missing observations must "
                "fail closed"
            )
        if domain.rollup_strategy != "derive_from_source_children":
            raise ValueError(
                f"Region analysis domain {domain_id} rollups must derive from "
                "source children"
            )
        if (
            not math.isfinite(domain.candidate_buffer_m)
            or domain.candidate_buffer_m <= 0.0
        ):
            raise ValueError(
                f"Region analysis domain {domain_id} candidate buffer must be "
                "positive"
            )
        if domain.metadata_provider != "generated_runtime":
            raise ValueError(
                f"Region analysis domain {domain_id} metadata must use "
                "generated_runtime"
            )
        if not _is_safe_provider_path(domain.metadata_path):
            raise ValueError(
                f"Region analysis domain {domain_id} metadata path is unsafe"
            )
        if not _is_lower_sha256(domain.metadata_sha256):
            raise ValueError(
                f"Region analysis domain {domain_id} metadata sha256 is invalid"
            )

        artifacts = domain.artifacts
        if artifacts.provider != "generated_runtime":
            raise ValueError(
                f"Region analysis domain {domain_id} source artifact must use "
                "generated_runtime"
            )
        if (
            not _is_safe_provider_path(artifacts.path)
            or not artifacts.id_field.strip()
            or not artifacts.area_field.strip()
        ):
            raise ValueError(
                f"Region analysis domain {domain_id} source artifact identity "
                "is incomplete"
            )
        if not _is_lower_sha256(artifacts.sha256):
            raise ValueError(
                f"Region analysis domain {domain_id} source sha256 is invalid"
            )
        if artifacts.cell_kind != "h3" or not 0 <= artifacts.resolution <= 15:
            raise ValueError(
                f"Region analysis domain {domain_id} must use a valid H3 source"
            )
        if artifacts.expected_cell_count <= 0:
            raise ValueError(
                f"Region analysis domain {domain_id} source count must be positive"
            )
        if artifacts.area_unit not in {"m2", "km2"}:
            raise ValueError(
                f"Region analysis domain {domain_id} area unit is unsupported"
            )
        if (
            not math.isfinite(artifacts.expected_total_area_km2)
            or artifacts.expected_total_area_km2 <= 0.0
        ):
            raise ValueError(
                f"Region analysis domain {domain_id} total area must be positive"
            )
        resolutions = {artifacts.resolution, *artifacts.rollups}
        if set(domain.cell_ids_sha256) != resolutions:
            raise ValueError(
                f"Region analysis domain {domain_id} must checksum every H3 "
                "level's id set"
            )
        if any(
            not _is_lower_sha256(digest)
            for digest in domain.cell_ids_sha256.values()
        ):
            raise ValueError(
                f"Region analysis domain {domain_id} has an invalid H3-id digest"
            )
        rollup_resolutions = tuple(sorted(artifacts.rollups, reverse=True))
        if tuple(artifacts.rollups) != rollup_resolutions:
            raise ValueError(
                f"Region analysis domain {domain_id} rollups must be ordered "
                "from finer to coarser resolution"
            )
        for resolution, rollup in artifacts.rollups.items():
            if (
                rollup.resolution != resolution
                or resolution < 0
                or resolution >= artifacts.resolution
            ):
                raise ValueError(
                    f"Region analysis domain {domain_id} R{resolution} rollup "
                    "resolution is invalid"
                )
            if (
                rollup.provider != "generated_runtime"
                or not _is_safe_provider_path(rollup.path)
                or not _is_lower_sha256(rollup.sha256)
            ):
                raise ValueError(
                    f"Region analysis domain {domain_id} R{resolution} source "
                    "is invalid"
                )
            if (
                rollup.id_field != artifacts.id_field
                or rollup.area_field != artifacts.area_field
                or rollup.area_unit != artifacts.area_unit
            ):
                raise ValueError(
                    f"Region analysis domain {domain_id} R{resolution} fields "
                    "must match the source"
                )
            if rollup.expected_cell_count <= 0:
                raise ValueError(
                    f"Region analysis domain {domain_id} R{resolution} count "
                    "must be positive"
                )
            if not math.isclose(
                rollup.expected_total_area_km2,
                artifacts.expected_total_area_km2,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    f"Region analysis domain {domain_id} R{resolution} total "
                    "area must match the source"
                )

    for support_domain_id, support_domain in (
        contract.technology_support_domains.items()
    ):
        if (
            support_domain.id != support_domain_id
            or not support_domain_id.strip()
        ):
            raise ValueError(
                "Technology-support-domain ids must be non-blank and match keys"
            )
        if not support_domain.label.strip():
            raise ValueError(
                f"Technology support domain {support_domain_id} label is required"
            )
        if support_domain.status not in {"candidate", "active"}:
            raise ValueError(
                f"Technology support domain {support_domain_id} status is invalid"
            )
        if (
            not support_domain.technologies
            or len(support_domain.technologies)
            != len(set(support_domain.technologies))
            or any(
                technology not in {"wind", "solar"}
                for technology in support_domain.technologies
            )
        ):
            raise ValueError(
                f"Technology support domain {support_domain_id} technologies "
                "must be unique wind/solar ids"
            )
        coverage_geometry = contract.geographies.get(
            support_domain.coverage_geometry_id
        )
        if coverage_geometry is None:
            raise ValueError(
                f"Technology support domain {support_domain_id} references an "
                "undeclared coverage geometry"
            )
        if coverage_geometry.role != "technology_target_surface":
            raise ValueError(
                f"Technology support domain {support_domain_id} coverage "
                "geometry must have role technology_target_surface"
            )
        if support_domain.coverage_rule != "positive_area_intersection":
            raise ValueError(
                f"Technology support domain {support_domain_id} must use "
                "positive_area_intersection"
            )
        if support_domain.cell_kind != "h3":
            raise ValueError(
                f"Technology support domain {support_domain_id} cell_kind "
                "must be h3"
            )
        if (
            isinstance(support_domain.source_resolution, bool)
            or not isinstance(support_domain.source_resolution, int)
            or support_domain.source_resolution < 0
            or support_domain.source_resolution > 15
        ):
            raise ValueError(
                f"Technology support domain {support_domain_id} source "
                "resolution is invalid"
            )
        if (
            support_domain.native_crs != contract.native_crs
            or support_domain.native_crs != coverage_geometry.native_crs
        ):
            raise ValueError(
                f"Technology support domain {support_domain_id} native CRS "
                "must match its region and coverage geometry"
            )
        if support_domain.empty_intersection_policy != "exclude":
            raise ValueError(
                f"Technology support domain {support_domain_id} empty "
                "intersections must be excluded"
            )
        if support_domain.missing_observation_policy != "error":
            raise ValueError(
                f"Technology support domain {support_domain_id} missing "
                "observations must fail closed with the error policy"
            )
        if support_domain.rollup_strategy != "derive_from_source_children":
            raise ValueError(
                f"Technology support domain {support_domain_id} rollups must "
                "derive from source children"
            )
        rollups = support_domain.rollup_resolutions
        if not rollups or len(rollups) != len(set(rollups)):
            raise ValueError(
                f"Technology support domain {support_domain_id} must declare "
                "unique rollup resolutions"
            )
        if tuple(sorted(rollups, reverse=True)) != rollups:
            raise ValueError(
                f"Technology support domain {support_domain_id} rollups must "
                "be ordered from finer to coarser resolution"
            )
        if any(
            isinstance(resolution, bool)
            or not isinstance(resolution, int)
            or resolution < 0
            or resolution >= support_domain.source_resolution
            for resolution in rollups
        ):
            raise ValueError(
                f"Technology support domain {support_domain_id} rollup "
                "resolutions must be valid and coarser than the source"
            )


def select_processing_adapter(
    group_id: str,
    geometry_family: str,
    data_representation: str = "auto",
) -> str:
    """Select common processing from data shape, never from a region id."""
    if group_id == "population":
        if data_representation == "grid":
            if geometry_family not in {"point", "polygon"}:
                raise ValueError("Population grids must be represented by points or polygons")
            return "population_grid"
        if geometry_family == "point":
            return "population_points"
        if geometry_family == "polygon":
            return "population_polygons"
        raise ValueError(f"Unsupported population geometry: {geometry_family}")
    if group_id == "roads" and geometry_family == "line":
        return "line_distance"
    return f"{geometry_family}_generic"


def validate_contract(contract: AnalysisContract) -> None:
    if contract.default_request is None:
        raise ValueError("Analysis default_request is required")
    selected_layer_ids = contract.default_request.selected_layer_ids
    if len(selected_layer_ids) != len(set(selected_layer_ids)):
        raise ValueError(
            "Analysis default_request selected_layer_ids must not contain duplicates"
        )
    unknown_default_layers = set(selected_layer_ids) - set(contract.layers)
    if unknown_default_layers:
        raise ValueError(
            "Analysis default_request selects undeclared layers: "
            f"{sorted(unknown_default_layers)}"
        )
    if selected_layer_ids and any(
        layer.source.diagnostic_source_snapshot is not None
        or layer.source.requires_explicit_parameters
        for layer in contract.layers.values()
    ):
        raise ValueError(
            "A diagnostic source-snapshot analysis must not select default layers"
        )

    area_result = contract.area_result
    if area_result is not None:
        if area_result.technology not in {"wind", "solar"}:
            raise ValueError(
                "Analysis area_result technology must be 'wind' or 'solar'"
            )
        applicable_group_ids = area_result.applicable_group_ids
        if not applicable_group_ids:
            raise ValueError(
                "Analysis area_result applicable_group_ids must not be empty"
            )
        if len(applicable_group_ids) != len(set(applicable_group_ids)):
            raise ValueError(
                "Analysis area_result applicable_group_ids must not contain duplicates"
            )
        unknown_area_groups = set(applicable_group_ids) - set(contract.groups)
        if unknown_area_groups:
            raise ValueError(
                "Analysis area_result contains undeclared groups: "
                f"{sorted(unknown_area_groups)}"
            )
        if area_result.restriction_combination != "geometry_union":
            raise ValueError(
                "Analysis area_result restriction_combination must be "
                "'geometry_union'"
            )
        if area_result.operation_order != "feasibility_then_exclusion":
            raise ValueError(
                "Analysis area_result operation_order must be "
                "'feasibility_then_exclusion'"
            )
        if area_result.denominator != "eligible_surface":
            raise ValueError(
                "Analysis area_result denominator must be 'eligible_surface'"
            )
        if area_result.geometry_semantics != "exact_vector_clip":
            raise ValueError(
                "Analysis area_result geometry_semantics must be "
                "'exact_vector_clip'"
            )
        if contract.analysis_domain is None:
            raise ValueError(
                "Analysis area_result requires an analysis-domain contract"
            )
        surface_id = area_result.eligible_surface_id.strip()
        if not surface_id:
            raise ValueError(
                "Analysis area_result eligible_surface_id is required"
            )
        surface = contract.eligible_surfaces.get(surface_id)
        if surface is None:
            raise ValueError(
                "Analysis area_result references an undeclared eligible "
                f"surface: {surface_id}"
            )
        if area_result.technology not in surface.technologies:
            raise ValueError(
                f"Eligible surface {surface_id} does not support "
                f"{area_result.technology}"
            )

    distributed_generation = contract.distributed_generation
    if distributed_generation is not None:
        rooftop = distributed_generation.rooftop_solar
        if rooftop is not None:
            if area_result is None or area_result.technology != "solar":
                raise ValueError(
                    "Rooftop solar requires a solar area-result contract"
                )
            if rooftop.status != "planning_proxy":
                raise ValueError(
                    "Rooftop-solar status must be 'planning_proxy'"
                )
            if rooftop.technology_key != "solar":
                raise ValueError(
                    "Rooftop-solar technology_key must be 'solar'"
                )
            if rooftop.panel_area_m2_per_person.unit != "m2/person":
                raise ValueError(
                    "Rooftop-solar panel area must use m2/person"
                )
            if any(
                value is None
                for value in (
                    rooftop.panel_area_m2_per_person.minimum,
                    rooftop.panel_area_m2_per_person.maximum,
                    rooftop.panel_area_m2_per_person.step,
                )
            ):
                raise ValueError(
                    "Rooftop-solar panel area must declare min, max, and step"
                )
            panel_parameter = rooftop.panel_area_m2_per_person
            if (
                float(panel_parameter.minimum) < 0.0
                or float(panel_parameter.default) < 0.0
                or float(panel_parameter.maximum) <= 0.0
                or float(panel_parameter.step) <= 0.0
            ):
                raise ValueError(
                    "Rooftop-solar panel area must use a non-negative range "
                    "and a positive maximum and step"
                )
            if contract.analysis_domain is None:
                raise ValueError(
                    "Rooftop solar requires an analysis-domain contract"
                )
            if (
                rooftop.population_source.analysis_h3_resolution
                != contract.analysis_domain.resolution
            ):
                raise ValueError(
                    "Rooftop-solar population analysis resolution must match "
                    "the solar analysis domain"
                )
            map_review = rooftop.map_review
            if map_review.canonical_group_id not in (
                area_result.applicable_group_ids
            ):
                raise ValueError(
                    "Rooftop-solar map review must reference an applicable "
                    "solar group"
                )
            unknown_review_layers = set(map_review.layer_ids) - set(
                contract.layers
            )
            if unknown_review_layers:
                raise ValueError(
                    "Rooftop-solar map review references unknown layers: "
                    f"{sorted(unknown_review_layers)}"
                )
            for layer_id in map_review.layer_ids:
                layer = contract.layers[layer_id]
                if layer.group_id != map_review.canonical_group_id:
                    raise ValueError(
                        "Rooftop-solar map-review layer belongs to the wrong "
                        f"group: {layer_id}"
                    )
                buffer_parameter = layer.parameters.get("buffer_m")
                if buffer_parameter is None:
                    raise ValueError(
                        "Rooftop-solar map-review layer has no canonical "
                        f"buffer parameter: {layer_id}"
                    )
            expected_domain_resolutions = {
                contract.analysis_domain.resolution,
                *contract.analysis_domain.rollups,
            }
            declared_domain_totals = (
                rooftop.population_source.expected_analysis_domain_totals
            )
            if set(declared_domain_totals) != expected_domain_resolutions:
                raise ValueError(
                    "Rooftop-solar mapped population totals must cover the "
                    "analysis domain and every declared rollup"
                )
            canonical_mapped_total = declared_domain_totals[
                contract.analysis_domain.resolution
            ]
            if any(
                not math.isclose(
                    total,
                    canonical_mapped_total,
                    rel_tol=0.0,
                    abs_tol=1e-6,
                )
                for total in declared_domain_totals.values()
            ):
                raise ValueError(
                    "Rooftop-solar mapped population must clip at the "
                    "canonical analysis resolution before parent rollup"
                )
            accounting = rooftop.accounting
            if not accounting.cap_at_solar_target:
                raise ValueError(
                    "Rooftop-solar accounting must cap output at the solar target"
                )
            if accounting.affects_geographic_potential:
                raise ValueError(
                    "Rooftop solar must not affect geographic potential"
                )
            if accounting.adds_establishment_candidates:
                raise ValueError(
                    "Rooftop solar must not add establishment candidates"
                )

    domain = contract.analysis_domain
    if domain is not None:
        if (
            not domain.provider.strip()
            or not domain.path.strip()
            or not domain.id_field.strip()
        ):
            raise ValueError("Analysis domain provider, path, and id field are required")
        if domain.cell_kind != "h3":
            raise ValueError(
                f"Unsupported analysis-domain cell kind: {domain.cell_kind}"
            )
        if domain.resolution < 0 or domain.resolution > 15:
            raise ValueError(
                f"Invalid H3 analysis-domain resolution: {domain.resolution}"
            )
        if domain.expected_cell_count <= 0:
            raise ValueError("Analysis domain expected cell count must be positive")
        if not _is_lower_sha256(domain.sha256):
            raise ValueError("Analysis domain sha256 is invalid")
        if (
            not math.isfinite(domain.expected_total_area_km2)
            or domain.expected_total_area_km2 <= 0.0
        ):
            raise ValueError(
                "Analysis domain expected total area must be positive"
            )
        if not domain.area_field.strip():
            raise ValueError("Analysis domain area field is required")
        if domain.area_unit not in {"m2", "km2"}:
            raise ValueError(
                f"Unsupported analysis-domain area unit: {domain.area_unit}"
            )
        for resolution, rollup in domain.rollups.items():
            if resolution != rollup.resolution:
                raise ValueError(
                    f"Analysis-domain rollup key R{resolution} does not match "
                    f"its declared R{rollup.resolution}"
                )
            if (
                not rollup.provider.strip()
                or not rollup.path.strip()
                or not rollup.id_field.strip()
            ):
                raise ValueError(
                    f"Analysis-domain R{resolution} rollup provider, path, "
                    "and id field are required"
                )
            if resolution < 0 or resolution > 15:
                raise ValueError(
                    f"Invalid H3 analysis-domain rollup resolution: {resolution}"
                )
            if resolution >= domain.resolution:
                raise ValueError(
                    f"Analysis-domain rollup R{resolution} must be coarser "
                    f"than the R{domain.resolution} source domain"
                )
            if rollup.expected_cell_count <= 0:
                raise ValueError(
                    f"Analysis-domain R{resolution} expected cell count "
                    "must be positive"
                )
            if not _is_lower_sha256(rollup.sha256):
                raise ValueError(
                    f"Analysis-domain R{resolution} sha256 is invalid"
                )
            if (
                not math.isfinite(rollup.expected_total_area_km2)
                or rollup.expected_total_area_km2 <= 0.0
            ):
                raise ValueError(
                    f"Analysis-domain R{resolution} expected total area "
                    "must be positive"
                )
            if not math.isclose(
                rollup.expected_total_area_km2,
                domain.expected_total_area_km2,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    f"Analysis-domain R{resolution} expected total area "
                    "must match the source domain"
                )
            if not rollup.area_field.strip():
                raise ValueError(
                    f"Analysis-domain R{resolution} area field is required"
                )
            if rollup.area_unit not in {"m2", "km2"}:
                raise ValueError(
                    "Unsupported analysis-domain "
                    f"R{resolution} area unit: {rollup.area_unit}"
                )
    standard_surface = contract.standard_result_surface
    if standard_surface is not None:
        if domain is None:
            raise ValueError(
                "Standard result surface requires an analysis domain"
            )
        if standard_surface.purpose != "frozen_standard_group_area_parity":
            raise ValueError(
                "Standard result surface purpose is unsupported"
            )
        if (
            not standard_surface.id.strip()
            or not standard_surface.label.strip()
            or not standard_surface.provider.strip()
            or not _is_safe_provider_path(standard_surface.path)
            or not standard_surface.id_field.strip()
            or not standard_surface.area_field.strip()
        ):
            raise ValueError(
                "Standard result surface identity, source, and fields are required"
            )
        if not _is_lower_sha256(standard_surface.sha256):
            raise ValueError("Standard result surface sha256 is invalid")
        if standard_surface.cell_kind != "h3":
            raise ValueError("Standard result surface cell_kind must be h3")
        if (
            standard_surface.resolution != domain.resolution
            or standard_surface.expected_cell_count
            != domain.expected_cell_count
        ):
            raise ValueError(
                "Standard result surface must match the analysis-domain "
                "source cell universe"
            )
        if standard_surface.area_unit not in {"m2", "km2"}:
            raise ValueError("Standard result surface area unit is unsupported")
        if (
            not math.isfinite(standard_surface.expected_total_area_km2)
            or standard_surface.expected_total_area_km2 <= 0.0
        ):
            raise ValueError(
                "Standard result surface expected total area must be positive"
            )
        if set(standard_surface.rollups) != set(domain.rollups):
            raise ValueError(
                "Standard result surface rollups must match analysis-domain "
                "rollups"
            )
        for resolution, rollup in standard_surface.rollups.items():
            domain_rollup = domain.rollups[resolution]
            if (
                not rollup.provider.strip()
                or not _is_safe_provider_path(rollup.path)
                or not rollup.id_field.strip()
                or not rollup.area_field.strip()
            ):
                raise ValueError(
                    f"Standard result surface R{resolution} source and "
                    "fields are required"
                )
            if not _is_lower_sha256(rollup.sha256):
                raise ValueError(
                    f"Standard result surface R{resolution} sha256 is invalid"
                )
            if (
                rollup.resolution != resolution
                or rollup.expected_cell_count
                != domain_rollup.expected_cell_count
            ):
                raise ValueError(
                    f"Standard result surface R{resolution} does not match "
                    "the analysis-domain rollup"
                )
            if rollup.area_unit not in {"m2", "km2"}:
                raise ValueError(
                    f"Standard result surface R{resolution} area unit is "
                    "unsupported"
                )
            if not math.isclose(
                rollup.expected_total_area_km2,
                standard_surface.expected_total_area_km2,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    f"Standard result surface R{resolution} total area must "
                    "match the source level"
                )
    for surface_id, surface in contract.eligible_surfaces.items():
        if surface.id != surface_id or not surface_id.strip():
            raise ValueError(
                "Eligible-surface ids must be non-blank and match their keys"
            )
        if not surface.label.strip():
            raise ValueError(f"Eligible surface {surface_id} label is required")
        if not surface.support_domain_id.strip():
            raise ValueError(
                f"Eligible surface {surface_id} support_domain_id is required"
            )
        if (
            not surface.technologies
            or len(surface.technologies) != len(set(surface.technologies))
            or any(item not in {"wind", "solar"} for item in surface.technologies)
        ):
            raise ValueError(
                f"Eligible surface {surface_id} technologies must be unique "
                "wind/solar ids"
            )
        if surface.geometry_operation != "intersection":
            raise ValueError(
                f"Eligible surface {surface_id} geometry_operation must be "
                "'intersection'"
            )
        if surface.surface_scope not in {
            "onshore_land",
            "offshore_water",
            "land_and_water",
        }:
            raise ValueError(
                f"Eligible surface {surface_id} has unsupported surface_scope"
            )
        if surface.water_policy not in {
            "exclude_sea_retain_inland_water",
            "exclude_all_water",
            "include_water",
        }:
            raise ValueError(
                f"Eligible surface {surface_id} has unsupported water_policy"
            )
        if surface.outside_region_policy != "exclude":
            raise ValueError(
                f"Eligible surface {surface_id} outside_region_policy must "
                "be 'exclude'"
            )
        if surface.source.geometry_family != "polygon":
            raise ValueError(
                f"Eligible surface {surface_id} source must be polygonal"
            )
        for label, value in (
            ("source provider", surface.source.provider),
            ("source path", surface.source.path),
            (
                "source coverage geometry id",
                surface.source.coverage_geometry_id,
            ),
            ("source derivation", surface.source.derivation),
            ("provider", surface.provider),
            ("path", surface.path),
            ("id field", surface.id_field),
            ("area field", surface.area_field),
        ):
            if not value.strip():
                raise ValueError(
                    f"Eligible surface {surface_id} {label} is required"
                )
        if surface.source.derivation != "reviewed_web_crs_derivative":
            raise ValueError(
                f"Eligible surface {surface_id} source derivation is unsupported"
            )
        for label, digest in (
            ("source", surface.source.sha256),
            ("R" + str(surface.resolution), surface.sha256),
        ):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise ValueError(
                    f"Eligible surface {surface_id} {label} sha256 is invalid"
                )
        if surface.cell_kind != "h3":
            raise ValueError(
                f"Eligible surface {surface_id} cell_kind must be 'h3'"
            )
        if surface.resolution < 0 or surface.resolution > 15:
            raise ValueError(
                f"Eligible surface {surface_id} resolution is invalid"
            )
        if surface.area_unit not in {"m2", "km2"}:
            raise ValueError(
                f"Eligible surface {surface_id} area unit is invalid"
            )
        if surface.expected_cell_count <= 0:
            raise ValueError(
                f"Eligible surface {surface_id} cell count must be positive"
            )
        if (
            not math.isfinite(surface.expected_total_area_km2)
            or surface.expected_total_area_km2 <= 0.0
        ):
            raise ValueError(
                f"Eligible surface {surface_id} total area must be positive"
            )
        context = surface.technology_context
        for label, value in (
            ("technology-context id", context.id),
            ("technology-context provider", context.provider),
            ("technology-context path", context.path),
            ("technology-context id field", context.id_field),
        ):
            if not value.strip():
                raise ValueError(
                    f"Eligible surface {surface_id} {label} is required"
                )
        if not _is_lower_sha256(context.sha256):
            raise ValueError(
                f"Eligible surface {surface_id} technology-context sha256 "
                "is invalid"
            )
        if context.cell_kind != "h3":
            raise ValueError(
                f"Eligible surface {surface_id} technology context must use H3"
            )
        if context.resolution != surface.resolution:
            raise ValueError(
                f"Eligible surface {surface_id} technology context must use "
                f"R{surface.resolution}"
            )
        if context.expected_cell_count < surface.expected_cell_count:
            raise ValueError(
                f"Eligible surface {surface_id} technology context cannot "
                "declare fewer cells than the support domain"
            )
        if not _is_lower_sha256(context.cell_ids_sha256):
            raise ValueError(
                f"Eligible surface {surface_id} technology-context cell-id "
                "digest is invalid"
            )
        if (
            not context.context_fields
            or len(context.context_fields) != len(set(context.context_fields))
            or any(
                re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", field) is None
                for field in context.context_fields
            )
        ):
            raise ValueError(
                f"Eligible surface {surface_id} technology context must "
                "declare unique canonical context_fields"
            )
        if context.missing_policy != "explicit_not_assessed":
            raise ValueError(
                f"Eligible surface {surface_id} technology context must "
                "preserve missing cells as explicit_not_assessed"
            )
        observations = surface.support_observations
        for label, value in (
            ("support-observation provider", observations.provider),
            ("support-observation metadata path", observations.path),
        ):
            if not value.strip():
                raise ValueError(
                    f"Eligible surface {surface_id} {label} is required"
                )
        if not _is_lower_sha256(observations.sha256):
            raise ValueError(
                f"Eligible surface {surface_id} support-observation metadata "
                "sha256 is invalid"
            )
        if observations.resolution != surface.resolution:
            raise ValueError(
                f"Eligible surface {surface_id} support observations must use "
                f"R{surface.resolution}"
            )
        if observations.expected_cell_count != surface.expected_cell_count:
            raise ValueError(
                f"Eligible surface {surface_id} support observations must cover "
                "the complete eligible cell universe"
            )
        if not _is_lower_sha256(observations.cell_ids_sha256):
            raise ValueError(
                f"Eligible surface {surface_id} support-observation cell-id "
                "digest is invalid"
            )
        if observations.missing_policy != "error":
            raise ValueError(
                f"Eligible surface {surface_id} support observations must fail "
                "closed with missing_policy='error'"
            )
        if set(observations.layers) != set(contract.layers):
            missing = set(contract.layers) - set(observations.layers)
            unexpected = set(observations.layers) - set(contract.layers)
            raise ValueError(
                f"Eligible surface {surface_id} support observations must "
                "declare every analysis layer exactly once: "
                f"missing={sorted(missing)}, unexpected={sorted(unexpected)}"
            )
        for layer_id, observation_layer in observations.layers.items():
            if observation_layer.layer_id != layer_id or not layer_id.strip():
                raise ValueError(
                    f"Eligible surface {surface_id} support-observation layer "
                    "ids must be non-blank and match their keys"
                )
            for label, value in (
                ("provider", observation_layer.provider),
                ("path", observation_layer.path),
            ):
                if not value.strip():
                    raise ValueError(
                        f"Eligible surface {surface_id} support-observation "
                        f"layer {layer_id!r} {label} is required"
                    )
            for label, digest in (
                ("sha256", observation_layer.sha256),
                ("rows_sha256", observation_layer.rows_sha256),
            ):
                if not _is_lower_sha256(digest):
                    raise ValueError(
                        f"Eligible surface {surface_id} support-observation "
                        f"layer {layer_id!r} {label} is invalid"
                    )
        if domain is None:
            raise ValueError(
                f"Eligible surface {surface_id} requires an analysis domain"
            )
        if surface.resolution != domain.resolution:
            raise ValueError(
                f"Eligible surface {surface_id} must use the canonical "
                "analysis resolution while retaining its independent cell "
                "universe"
            )
        if set(surface.rollups) != set(domain.rollups):
            raise ValueError(
                f"Eligible surface {surface_id} rollups must match the "
                "analysis domain"
            )
        for resolution, rollup in surface.rollups.items():
            if resolution != rollup.resolution:
                raise ValueError(
                    f"Eligible surface {surface_id} R{resolution} key mismatch"
                )
            if resolution >= surface.resolution:
                raise ValueError(
                    f"Eligible surface {surface_id} rollups must be coarser "
                    f"than R{surface.resolution}"
                )
            for label, value in (
                ("provider", rollup.provider),
                ("path", rollup.path),
                ("id field", rollup.id_field),
                ("area field", rollup.area_field),
            ):
                if not value.strip():
                    raise ValueError(
                        f"Eligible surface {surface_id} R{resolution} "
                        f"{label} is required"
                    )
            if rollup.expected_cell_count <= 0:
                raise ValueError(
                    f"Eligible surface {surface_id} R{resolution} cell count "
                    "must be positive"
                )
            if rollup.area_unit not in {"m2", "km2"}:
                raise ValueError(
                    f"Eligible surface {surface_id} R{resolution} area unit "
                    "is invalid"
                )
            if len(rollup.sha256) != 64 or any(
                character not in "0123456789abcdef"
                for character in rollup.sha256
            ):
                raise ValueError(
                    f"Eligible surface {surface_id} R{resolution} sha256 is "
                    "invalid"
                )
            if (
                not math.isfinite(rollup.expected_total_area_km2)
                or rollup.expected_total_area_km2 <= 0.0
            ):
                raise ValueError(
                    f"Eligible surface {surface_id} R{resolution} total area "
                    "must be positive"
                )
            if not math.isclose(
                rollup.expected_total_area_km2,
                surface.expected_total_area_km2,
                rel_tol=0.0,
                abs_tol=1e-6,
            ):
                raise ValueError(
                    f"Eligible surface {surface_id} R{resolution} total must "
                    f"derive from R{surface.resolution}"
                )
    unknown_groups = set(contract.groups) - set(STANDARD_GROUP_IDS)
    if unknown_groups:
        raise ValueError(f"Unknown standard groups: {sorted(unknown_groups)}")
    if contract.ui is not None:
        unknown_ui_groups = set(contract.ui.groups) - set(contract.groups)
        if unknown_ui_groups:
            raise ValueError(
                "Analysis ui describes undeclared groups: "
                f"{sorted(unknown_ui_groups)}"
            )
        for group_ui in contract.ui.groups.values():
            if not all(
                value.strip()
                for value in (
                    group_ui.label,
                    group_ui.analysis_label,
                    group_ui.interpretation,
                )
            ):
                raise ValueError(
                    f"Analysis ui group {group_ui.id} has blank copy"
                )
            if not 0 <= group_ui.blend_default <= 100:
                raise ValueError(
                    f"Analysis ui group {group_ui.id} blend_default must be 0-100"
                )
            if re.fullmatch(r"#[0-9a-fA-F]{6}", group_ui.group_color) is None:
                raise ValueError(
                    f"Analysis ui group {group_ui.id} has invalid group_color"
                )
    for layer in contract.layers.values():
        if layer.group_id not in contract.groups:
            raise ValueError(f"Layer {layer.id} uses undeclared group {layer.group_id}")
        snapshot_reference = layer.source.diagnostic_source_snapshot
        postgis_reference = layer.source.postgis_reference
        if postgis_reference is not None:
            if postgis_reference.region_id != contract.region_id:
                raise ValueError("PostGIS source belongs to another analysis region")
            if domain is None or postgis_reference.resolution != domain.resolution or layer.source.distance_coverage.expected_source_row_count < domain.expected_cell_count:
                raise ValueError("PostGIS source must cover the base analysis domain and declared context")
        if (
            snapshot_reference is not None
            and snapshot_reference.region_id != contract.region_id
        ):
            raise ValueError(
                f"Layer {layer.id} diagnostic source snapshot belongs to "
                f"{snapshot_reference.region_id}, not {contract.region_id}"
            )
        if layer.operation not in SUPPORTED_OPERATIONS:
            raise ValueError(f"Unsupported operation for {layer.id}: {layer.operation}")
        unknown_families = set(layer.source.expected_geometry_families) - SUPPORTED_GEOMETRY_FAMILIES
        if unknown_families:
            raise ValueError(f"Unsupported geometry families for {layer.id}: {sorted(unknown_families)}")
        coverage = layer.source.distance_coverage
        source_resolution = layer.source.distance_h3_resolution
        if (
            domain is not None
            and source_resolution is not None
            and domain.resolution > source_resolution
        ):
            raise ValueError(
                f"Layer {layer.id} analysis domain R{domain.resolution} is "
                f"finer than its R{source_resolution} distance source"
            )
        if coverage.mode == "declared_sparse":
            if domain is None:
                raise ValueError(
                    f"Layer {layer.id} declares sparse distance coverage "
                    "without an analysis domain"
                )
            if source_resolution is None:
                raise ValueError(
                    f"Layer {layer.id} declares sparse distance coverage "
                    "without distance_h3_resolution"
                )
            expected_targets = {
                domain.resolution: domain.expected_cell_count,
                **{
                    resolution: rollup.expected_cell_count
                    for resolution, rollup in domain.rollups.items()
                },
            }
            if set(coverage.targets) != set(expected_targets):
                raise ValueError(
                    f"Layer {layer.id} sparse coverage targets must exactly "
                    "match the analysis-domain resolutions"
                )
            for resolution, expected_cell_count in expected_targets.items():
                target = coverage.targets[resolution]
                if resolution > source_resolution:
                    raise ValueError(
                        f"Layer {layer.id} sparse coverage R{resolution} is "
                        f"finer than its R{source_resolution} distance source"
                    )
                if target.target_cell_count != expected_cell_count:
                    raise ValueError(
                        f"Layer {layer.id} sparse coverage R{resolution} "
                        "target count does not match the analysis domain"
                    )
        if contract.ui is not None and layer.group_id in contract.ui.groups:
            if layer.ui is None:
                raise ValueError(
                    f"Layer {layer.id} needs ui metadata for described group "
                    f"{layer.group_id}"
                )
            if not layer.ui.note.strip():
                raise ValueError(f"Layer {layer.id} ui note is blank")
            if re.fullmatch(r"#[0-9a-fA-F]{6}", layer.ui.source_color) is None:
                raise ValueError(f"Layer {layer.id} has invalid ui source_color")
            if layer.ui.point_radius <= 0:
                raise ValueError(f"Layer {layer.id} ui point_radius must be positive")
            if layer.ui.quality_flag not in {None, "caution"}:
                raise ValueError(
                    f"Layer {layer.id} ui quality_flag must be 'caution' or null"
                )


def validate_technology_support_binding(
    contract: AnalysisContract,
) -> None:
    """Validate the analysis and its explicit region support-domain binding."""

    validate_contract(contract)
    if contract.area_result is None:
        raise ValueError(
            f"{contract.region_id}/{contract.id} has no area-result contract"
        )
    technology_support_domain_for_eligible_surface(contract)


def _validate_protected_source_payload(layer: LayerContract, assets: LayerAssets) -> None:
    """Fail before a source view can serialize private points or attributes."""
    if layer.source.data_representation != "privacy_protected_surface":
        return
    payload = read_layer_geojson(assets)
    if set(payload) != {"type", "features"} or payload.get("type") != "FeatureCollection":
        raise ValueError("Protected source payload must contain only polygon features")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Protected source payload must contain polygon features")
    for feature in features:
        if (not isinstance(feature, dict)
                or set(feature) != {"type", "geometry", "properties"}
                or feature.get("type") != "Feature" or feature.get("properties") != {}):
            raise ValueError("Protected source features must have no attributes or identifiers")
        geometry = feature.get("geometry")
        if (not isinstance(geometry, dict) or set(geometry) != {"type", "coordinates"}
                or geometry.get("type") not in {"Polygon", "MultiPolygon"}):
            raise ValueError("Protected source geometry must be polygonal; raw points are forbidden")


def validate_layer(layer: LayerContract) -> ValidatedLayer:
    assets = resolve_layer_assets(layer)
    _validate_protected_source_payload(layer, assets)
    if assets.manifest_status != "ok":
        raise ValueError(f"Layer {layer.id} asset status is {assets.manifest_status!r}")
    if assets.runtime_identity is None:
        if not assets.geojson_path.is_file() or not assets.distance_path.is_file():
            raise FileNotFoundError(f"Layer {layer.id} runtime assets are incomplete")
    elif assets.geojson_payload is None or not assets.distance_observations:
        raise ValueError(f"Layer {layer.id} PostGIS runtime inputs are incomplete")
    try:
        detected = (
            detect_layer_geometry_family(assets, layer.source.geometry_collection_policy)
            if assets.runtime_identity is not None
            else detect_geojson_geometry_family(assets.geojson_path, layer.source.geometry_collection_policy)
        )
        geometry_validation = "detected"
    except ValueError:
        if layer.source.source_geometry_required:
            raise
        if len(layer.source.expected_geometry_families) != 1:
            raise ValueError(
                f"Layer {layer.id} needs exactly one declared geometry family "
                "when source geometry is optional"
            )
        detected = layer.source.expected_geometry_families[0]
        geometry_validation = "declared_from_validated_distance_artifact"
    if detected not in layer.source.expected_geometry_families:
        raise ValueError(
            f"Layer {layer.id} geometry is {detected}; expected {layer.source.expected_geometry_families}"
        )
    if assets.declared_geometry_family not in {"unknown", detected}:
        raise ValueError(
            f"Layer {layer.id} asset manifest says {assets.declared_geometry_family}, data says {detected}"
        )
    adapter = select_processing_adapter(
        layer.group_id,
        detected,
        layer.source.data_representation,
    )
    return ValidatedLayer(
        contract=layer,
        assets=assets,
        geometry_family=detected,
        processing_adapter=adapter,
        geometry_validation=geometry_validation,
    )


def validate_layer_source(layer: LayerContract) -> ValidatedLayer:
    """Validate canonical source geometry without requiring derived distances."""

    assets = resolve_layer_source_assets(layer)
    _validate_protected_source_payload(layer, assets)
    if assets.manifest_status != "ok":
        raise ValueError(f"Layer {layer.id} asset status is {assets.manifest_status!r}")
    if assets.runtime_identity is None and not assets.geojson_path.is_file():
        raise FileNotFoundError(f"Layer {layer.id} source geometry is incomplete")
    detected = (
        detect_geometry_family(read_layer_geojson(assets), layer.source.geometry_collection_policy)
        if assets.runtime_identity is not None
        else detect_geojson_geometry_family(assets.geojson_path, layer.source.geometry_collection_policy)
    )
    if detected not in layer.source.expected_geometry_families:
        raise ValueError(
            f"Layer {layer.id} geometry is {detected}; expected "
            f"{layer.source.expected_geometry_families}"
        )
    if assets.declared_geometry_family not in {"unknown", detected}:
        raise ValueError(
            f"Layer {layer.id} asset manifest says "
            f"{assets.declared_geometry_family}, data says {detected}"
        )
    adapter = select_processing_adapter(
        layer.group_id,
        detected,
        layer.source.data_representation,
    )
    return ValidatedLayer(
        contract=layer,
        assets=assets,
        geometry_family=detected,
        processing_adapter=adapter,
        geometry_validation="detected_source_only",
    )
