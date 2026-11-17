from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Any, Iterable, Mapping

from pyproj import CRS, Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform

from .access_policy import (
    PRODUCT_TRUST_CLASSIFICATION,
    behavior_status_for_trust,
)
from .combined_result_compiler import (
    ResolvedCombinedScoreSurface,
    materialize_combined_result_policy,
)
from .contracts import analysis_contract, region_geography_contract
from .geography import build_positive_intersection_h3_domain, sha256_path
from .geometry import build_direct_distance_artifact
from .landscape import materialize_landscape_manifest
from .manifest_schema import (
    ManifestProblem,
    attach_manifest_problem_questions,
    validate_region_package_file,
)
from .paths import GENERATED_RUNTIME_ROOT_ENV, repo_root, resolve_source_path
from .rooftop_compiler import materialize_rooftop_solar
from .scenario_compiler import materialize_scenario_manifest
from .social_acceptance_compiler import materialize_social_acceptance_manifest
from .technology_support_compiler import materialize_technology_support
from .validation import (
    validate_contract,
    validate_layer,
    validate_region_geography_contract,
)


COMPILER_VERSION = "1.1"
WORKSPACE_PROFILE_PATH = "regions/workspace_profiles/v2_final_standard.json"
READINESS_FILE_NAME = "region-package.readiness.json"
STANDARD_ANALYSIS_FILE = "analyses/standard_constraints.json"
READINESS_STATES = (
    "missing_manifest",
    "missing_data",
    "not_implemented",
    "not_validated",
    "technically_validated",
    "regionally_accepted",
    "public",
)


@dataclass(frozen=True)
class CompiledRegionPackage:
    """Paths and deterministic evidence emitted by one successful compile."""

    region_id: str
    output_root: Path
    generated_root: Path
    manifest_paths: tuple[Path, ...]
    generated_paths: tuple[Path, ...]
    readiness: Mapping[str, Any]
    materialized: bool


class RegionPackageCompilationError(ValueError):
    """A fail-closed, serializable region-package compilation failure."""

    def __init__(self, problems: Iterable[ManifestProblem]):
        self.problems = attach_manifest_problem_questions(problems)
        summary = ", ".join(
            f"{problem.code}{problem.pointer}" for problem in self.problems
        )
        super().__init__(summary or "Region package compilation failed")


@dataclass(frozen=True)
class _ResolvedAsset:
    pointer: str
    provider: str
    provider_path: str
    format: str
    integrity_mode: str
    path: Path
    bytes: int
    sha256: str


def _problem(
    *,
    code: str,
    source: str,
    pointer: str,
    message: str,
    help_text: str,
    expected: Any | None = None,
    actual: Any | None = None,
) -> ManifestProblem:
    return ManifestProblem(
        code=code,
        severity="error",
        source=source,
        pointer=pointer,
        message=message,
        help=help_text,
        expected=expected,
        actual=actual,
    )


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_relative_path(value: str, label: str) -> PurePosixPath:
    if not value.strip() or "\\" in value:
        raise ValueError(f"{label} must be a non-empty POSIX path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} escapes its provider root")
    return relative


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _generated_path(root: Path, value: str) -> Path:
    relative = _safe_relative_path(value, "generated asset path")
    candidate = root.joinpath(*relative.parts).resolve()
    if not _within(root.resolve(), candidate):
        raise ValueError(f"Generated asset escapes generated root: {value}")
    return candidate


def _walk_assets(
    value: Any,
    path: tuple[object, ...] = (),
) -> Iterable[tuple[tuple[object, ...], Mapping[str, Any]]]:
    if isinstance(value, Mapping):
        if {"provider", "path", "format", "integrity"}.issubset(value):
            yield path, value
        for key, child in value.items():
            yield from _walk_assets(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_assets(child, (*path, index))


def _pointer(parts: Iterable[object]) -> str:
    encoded = [
        str(part).replace("~", "~0").replace("/", "~1")
        for part in parts
    ]
    return "/" + "/".join(encoded) if encoded else "/"


def _resolve_declared_assets(
    form: Mapping[str, Any],
    *,
    source: str,
    generated_root: Path,
) -> tuple[dict[int, _ResolvedAsset], tuple[ManifestProblem, ...]]:
    resolved: dict[int, _ResolvedAsset] = {}
    problems: list[ManifestProblem] = []
    for parts, asset in _walk_assets(form):
        pointer = _pointer(parts)
        provider = str(asset["provider"])
        provider_path = str(asset["path"])
        try:
            if provider == "generated_runtime":
                path = _generated_path(generated_root, provider_path)
            else:
                path = resolve_source_path(provider, provider_path)
        except (FileNotFoundError, OSError, ValueError) as exc:
            problems.append(
                _problem(
                    code="MF-DATA-001",
                    source=source,
                    pointer=f"{pointer}/path",
                    message="Den deklarerade källfilen kan inte lösas genom sin provider.",
                    help_text="Kontrollera provider, miljövariabel och den provider-relativa sökvägen.",
                    expected="a resolvable provider asset",
                    actual=str(exc),
                )
            )
            continue
        if not path.is_file():
            problems.append(
                _problem(
                    code="MF-DATA-002",
                    source=source,
                    pointer=f"{pointer}/path",
                    message="Den deklarerade källfilen saknas.",
                    help_text="Lägg filen på den deklarerade provider-sökvägen eller markera delen unavailable.",
                    expected="existing regular file",
                    actual=provider_path,
                )
            )
            continue
        actual_sha256 = sha256_path(path)
        integrity = asset["integrity"]
        mode = str(integrity["mode"])
        if mode == "pinned" and actual_sha256 != str(integrity["sha256"]):
            problems.append(
                _problem(
                    code="MF-INTEGRITY-001",
                    source=source,
                    pointer=f"{pointer}/integrity/sha256",
                    message="Källfilens checksumma matchar inte den pinnade deklarationen.",
                    help_text="Återställ den granskade filen eller granska ändringen och uppdatera digesten uttryckligen.",
                    expected=integrity["sha256"],
                    actual=actual_sha256,
                )
            )
            continue
        resolved[id(asset)] = _ResolvedAsset(
            pointer=pointer,
            provider=provider,
            provider_path=provider_path,
            format=str(asset["format"]),
            integrity_mode=mode,
            path=path,
            bytes=path.stat().st_size,
            sha256=actual_sha256,
        )
    return resolved, tuple(problems)


def _workspace_profile() -> dict[str, Any]:
    path = repo_root() / WORKSPACE_PROFILE_PATH
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Workspace profile must be a JSON object")
    return value


def _geometry_family(geometry: Any) -> str:
    name = str(geometry.geom_type).lower()
    if "point" in name:
        return "point"
    if "line" in name:
        return "line"
    if "polygon" in name:
        return "polygon"
    raise ValueError(f"Unsupported geometry type: {geometry.geom_type}")


def _normalized_source_payload(
    layer: Mapping[str, Any],
    resolved: _ResolvedAsset,
) -> tuple[dict[str, Any], int]:
    source = layer["source"]
    if source["source_kind"] != "vector_file":
        raise NotImplementedError(
            "The first compiler increment materializes source_kind=vector_file; "
            f"received {source['source_kind']!r}"
        )
    if resolved.format != "geojson":
        raise NotImplementedError(
            "The current generic vector loader requires GeoJSON materialization; "
            f"received {resolved.format!r}"
        )
    value = json.loads(resolved.path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("type") != "FeatureCollection":
        raise ValueError("Vector source must be a GeoJSON FeatureCollection")
    features = value.get("features")
    if not isinstance(features, list):
        raise ValueError("GeoJSON FeatureCollection features must be a list")
    selection = source.get("selection")
    if selection is not None:
        field = str(selection["field"])
        allowed = set(selection["values"])
        features = [
            feature
            for feature in features
            if isinstance(feature, dict)
            and isinstance(feature.get("properties"), dict)
            and feature["properties"].get(field) in allowed
        ]
    if not features:
        raise ValueError("Vector selection produced no source features")

    declared_family = str(layer["geometry_family"])
    if declared_family == "grid":
        raise NotImplementedError(
            "Grid materialization requires the population capability compiler"
        )
    source_crs = CRS.from_user_input(source["source_crs"])
    web_crs = CRS.from_epsg(4326)
    transformer = Transformer.from_crs(source_crs, web_crs, always_xy=True)
    normalized_features: list[dict[str, Any]] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"Source feature {index} is not a GeoJSON Feature")
        raw_geometry = feature.get("geometry")
        if not isinstance(raw_geometry, dict):
            raise ValueError(f"Source feature {index} has no geometry")
        geometry = shape(raw_geometry)
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"Source feature {index} geometry is empty or invalid")
        if _geometry_family(geometry) != declared_family:
            raise ValueError(
                f"Source feature {index} is {_geometry_family(geometry)}, "
                f"expected {declared_family}"
            )
        if not source_crs.equals(web_crs, ignore_axis_order=True):
            geometry = transform(transformer.transform, geometry)
        normalized_features.append(
            {
                "type": "Feature",
                # Selection happens against the declared source before this
                # point. Runtime previews need geometry, not an undeclared
                # copy of arbitrary source attributes.
                "properties": {},
                "geometry": mapping(geometry),
            }
        )
    return (
        {
            "type": "FeatureCollection",
            **({"crs": {
                "type": "name",
                "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"},
            }} if source.get("data_representation") != "privacy_protected_surface" else {}),
            "features": normalized_features,
        },
        len(normalized_features),
    )


def _domain_manifest(
    form: Mapping[str, Any],
    *,
    boundary: _ResolvedAsset,
    generated_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], tuple[str, ...]]:
    region = form["region"]
    geography = form["geography"]
    boundary_form = geography["boundary"]
    domain = geography["standard_analysis_domain"]
    region_id = str(region["region_id"])
    identity_geometry_id = str(boundary_form["id"])
    analysis_surface_id = f"{identity_geometry_id}_analysis_surface"
    source_resolution = int(domain["resolution"])
    rollups = tuple(int(value) for value in domain["rollup_resolutions"])
    level_paths = {
        resolution: (
            f"data/generated/analysis_domain/{region_id}_standard_r"
            f"{resolution}.geojson"
        )
        for resolution in (source_resolution, *rollups)
    }
    metadata_path = (
        f"data/generated/analysis_domain/{region_id}_standard_metadata.json"
    )
    generated = build_positive_intersection_h3_domain(
        boundary_path=boundary.path,
        boundary_sha256=boundary.sha256,
        boundary_provider=boundary.provider,
        boundary_reference=boundary.provider_path,
        source_crs_value=str(boundary_form["source_crs"]),
        native_crs_value=str(region["native_crs"]),
        generated_root=generated_root,
        level_paths=level_paths,
        metadata_path=metadata_path,
        domain_id=str(domain["domain_id"]),
        domain_scope="standard_constraints",
        coverage_geometry_id=analysis_surface_id,
        source_resolution=source_resolution,
        rollup_resolutions=rollups,
        candidate_buffer_m=float(domain["candidate_buffer_m"]),
        status="candidate",
    )
    levels = {
        int(item["resolution"]): item for item in generated["levels"]
    }
    source_level = levels[source_resolution]
    total_area_km2 = float(source_level["total_area_km2"])
    artifacts = {
        "provider": "generated_runtime",
        "path": level_paths[source_resolution],
        "sha256": source_level["sha256"],
        "id_field": "hex_id",
        "area_field": "area_km2",
        "area_unit": "km2",
        "cell_kind": "h3",
        "resolution": source_resolution,
        "expected_cell_count": int(source_level["cell_count"]),
        "expected_total_area_km2": total_area_km2,
        "rollups": [
            {
                "provider": "generated_runtime",
                "path": level_paths[resolution],
                "sha256": levels[resolution]["sha256"],
                "id_field": "hex_id",
                "area_field": "area_km2",
                "area_unit": "km2",
                "resolution": resolution,
                "expected_cell_count": int(levels[resolution]["cell_count"]),
                "expected_total_area_km2": total_area_km2,
            }
            for resolution in rollups
        ],
    }
    provenance = boundary_form["provenance"]
    source_metadata = {
        "authority": provenance["authority"],
        "dataset_name": provenance["dataset_name"],
        "dataset_version": provenance["dataset_version"],
        "snapshot_date": provenance["snapshot_date"],
        "license": provenance["license"],
        "provenance_status": provenance["provenance_status"],
        "derivation": provenance["derivation"],
        "upstream_inputs": [
            {
                "dataset_name": provenance["dataset_name"],
                "role": "declared_boundary_asset",
                "checksum_status": "pinned",
                "sha256": boundary.sha256,
            }
        ],
    }
    geography_manifest = {
        "schema_version": "1.0",
        "region_id": region_id,
        "native_crs": region["native_crs"],
        "geographies": {
            identity_geometry_id: {
                "label": boundary_form["label"],
                "role": "administrative_boundary",
                "provider": boundary.provider,
                "path": boundary.provider_path,
                "sha256": boundary.sha256,
                "format": boundary.format,
                "geometry_family": "polygon",
                "source_crs": boundary_form["source_crs"],
                "native_crs": boundary_form["native_crs"],
                "source_metadata": source_metadata,
            },
            analysis_surface_id: {
                "label": f"{boundary_form['label']} — unreviewed analysis surface",
                "role": "analysis_surface",
                "provider": boundary.provider,
                "path": boundary.provider_path,
                "sha256": boundary.sha256,
                "format": boundary.format,
                "geometry_family": "polygon",
                "source_crs": boundary_form["source_crs"],
                "native_crs": boundary_form["native_crs"],
                "water_policy": "include_water",
                "source_metadata": {
                    **source_metadata,
                    "derivation": (
                        f"{provenance['derivation']} Transitional onboarding "
                        "reuses the declared boundary bytes without a hydrology "
                        "operation and therefore records include_water. This "
                        "candidate surface cannot establish product readiness."
                    ),
                },
            },
        },
        "analysis_domains": {
            domain["domain_id"]: {
                "label": f"{region['display_name']} standard analysis domain",
                "status": "candidate",
                "purpose": "standard_group_analysis",
                "domain_scope": "standard_constraints",
                "coverage_geometry_id": analysis_surface_id,
                "coverage_rule": domain["coverage_rule"],
                "empty_intersection_policy": "exclude",
                "missing_observation_policy": domain[
                    "missing_observation_policy"
                ],
                "rollup_strategy": "derive_from_source_children",
                "candidate_buffer_m": domain["candidate_buffer_m"],
                "metadata": {
                    "provider": "generated_runtime",
                    "path": metadata_path,
                    "sha256": generated["metadata"]["sha256"],
                },
                "cell_ids_sha256": {
                    str(resolution): levels[resolution]["cell_ids_sha256"]
                    for resolution in (source_resolution, *rollups)
                },
                "artifacts": artifacts,
            }
        },
        "technology_support_domains": {},
    }
    contract = region_geography_contract(geography_manifest)
    validate_region_geography_contract(contract)
    generated_paths = tuple(
        [metadata_path]
        + [level_paths[resolution] for resolution in (source_resolution, *rollups)]
    )
    return geography_manifest, generated, generated_paths


def _profile_group_descriptors(
    profile: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    return {
        str(item["id"]): item
        for item in profile.get("standard_groups") or []
    }


def _source_color(group_index: int, layer_index: int) -> str:
    palette = (
        "#b18421",
        "#b7532d",
        "#407749",
        "#844e94",
        "#227371",
    )
    base = palette[group_index % len(palette)]
    if layer_index == 0:
        return base
    digest = hashlib.sha256(f"{base}:{layer_index}".encode("ascii")).hexdigest()
    return f"#{digest[:6]}"


def _analysis_manifest(
    form: Mapping[str, Any],
    *,
    domain_artifacts: Mapping[str, Any],
    generated_root: Path,
    resolved_assets: Mapping[int, _ResolvedAsset],
) -> tuple[dict[str, Any], list[dict[str, Any]], tuple[str, ...]]:
    region_id = str(form["region"]["region_id"])
    resolution = int(domain_artifacts["resolution"])
    expected_count = int(domain_artifacts["expected_cell_count"])
    domain_id_digest = next(
        value
        for key, value in form["_generated_domain_digests"].items()
        if int(key) == resolution
    )
    profile = _workspace_profile()
    profile_groups = _profile_group_descriptors(profile)
    declared_groups = [
        group for group in form["standard_groups"] if group["state"] == "declared"
    ]
    manifest_path = (
        f"data/generated/region_package/{region_id}/source_assets.csv"
    )
    layer_rows: list[dict[str, Any]] = []
    layer_manifests: list[dict[str, Any]] = []
    parameter_evidence_by_layer_id: dict[str, dict[str, Any]] = {}
    generated_paths: list[str] = []
    for group_index, group in enumerate(form["standard_groups"]):
        if group["state"] != "declared":
            continue
        for layer_index, layer in enumerate(group["layers"]):
            source = layer["source"]
            resolved = resolved_assets[id(source["asset"])]
            normalized, feature_count = _normalized_source_payload(layer, resolved)
            source_path = (
                f"data/generated/region_package/{region_id}/sources/"
                f"{layer['id']}.geojson"
            )
            distance_path = (
                f"data/generated/region_package/{region_id}/observations/"
                f"{layer['id']}.csv"
            )
            normalized_path = _generated_path(generated_root, source_path)
            normalized_path.parent.mkdir(parents=True, exist_ok=True)
            normalized_path.write_bytes(
                (
                    json.dumps(
                        normalized,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
            )
            placeholder_path = _generated_path(generated_root, distance_path)
            placeholder_path.parent.mkdir(parents=True, exist_ok=True)
            placeholder_path.write_text(
                "hex_id,distance_m,intersects\n",
                encoding="utf-8",
                newline="",
            )
            layer_rows.append(
                {
                    "layer_id": layer["id"],
                    "status": "ok",
                    "geojson_path": source_path,
                    "distance_path": distance_path,
                    "geometry_family": layer["geometry_family"],
                    "feature_count": feature_count,
                    "geojson_bytes": "",
                    "geojson_sha256": "",
                    "distance_bytes": "",
                    "distance_sha256": "",
                }
            )
            parameter = layer["parameters"]["buffer_m"]
            technical_initial_value = parameter["technical_initial_value"]
            accepted_recommendation = parameter[
                "accepted_recommended_default"
            ]
            parameter_evidence_by_layer_id[str(layer["id"])] = {
                "technical_initial_value": technical_initial_value,
                "accepted_recommended_default": accepted_recommendation,
                "materialized_engine_default": technical_initial_value,
                "materialized_engine_default_semantics": (
                    "technical_initial_value_not_regional_recommendation"
                ),
            }
            if accepted_recommendation["state"] == "defined":
                recommendation_note = (
                    "Accepterad regional rekommendation: "
                    f"{accepted_recommendation['value']:g} m."
                )
            else:
                recommendation_note = (
                    "Ingen accepterad regional rekommendation: "
                    f"{accepted_recommendation['reason']}"
                )
            base_note = (
                layer.get("note")
                or source["provenance"]["derivation"]
            )
            layer_manifests.append(
                {
                    "id": layer["id"],
                    "label": layer["label"],
                    "group_id": group["id"],
                    "source": {
                        "provider": "generated_runtime",
                        "asset_manifest": manifest_path,
                        "layer_id": layer["id"],
                        "expected_geometry_families": [
                            layer["geometry_family"]
                        ],
                        "data_representation": layer["data_representation"],
                        **({"analysis_base_buffer_m": source["analysis_base_buffer_m"]}
                           if source.get("analysis_base_buffer_m", 0) else {}),
                        "distance_provider": "generated_runtime",
                        "distance_path": distance_path,
                        "distance_h3_resolution": resolution,
                        "distance_coverage": {
                            "mode": "complete",
                            "missing_policy": "error",
                            "expected_source_row_count": expected_count,
                            "source_ids_sha256": domain_id_digest,
                        },
                    },
                    "operation": layer["operation"],
                    "parameters": {
                        "buffer_m": {
                            "type": parameter["type"],
                            "unit": parameter["unit"],
                            # The current engine contract requires a numeric
                            # default. It is deliberately sourced from the
                            # technical control value, never from an absent or
                            # unaccepted regional recommendation.
                            "default": technical_initial_value,
                            "minimum": parameter["minimum"],
                            "maximum": parameter["maximum"],
                            "step": parameter["step"],
                        }
                    },
                    "ui": {
                        "note": (
                            f"{base_note} Tekniskt startvärde: "
                            f"{technical_initial_value:g} m; detta är inte "
                            f"en regional rekommendation. {recommendation_note}"
                        ),
                        "source_color": _source_color(
                            group_index,
                            layer_index,
                        ),
                        "point_radius": 4
                        if layer["geometry_family"] == "point"
                        else 40,
                    },
                }
            )
            generated_paths.extend((source_path, distance_path))

    asset_manifest_path = _generated_path(generated_root, manifest_path)
    asset_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    asset_fields = (
        "layer_id",
        "status",
        "geojson_path",
        "distance_path",
        "geometry_family",
        "feature_count",
        "geojson_bytes",
        "geojson_sha256",
        "distance_bytes",
        "distance_sha256",
    )

    def write_asset_manifest() -> None:
        with asset_manifest_path.open(
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=asset_fields,
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(layer_rows)

    # The first pass gives the existing generic geometry builder a resolvable
    # placeholder. The final pass below pins both generated artifacts.
    write_asset_manifest()
    generated_paths.append(manifest_path)

    ui_groups = []
    for group_index, group in enumerate(form["standard_groups"]):
        if group["state"] != "declared":
            continue
        profile_group = profile_groups[str(group["id"])]
        ui_groups.append(
            {
                "id": group["id"],
                "label": profile_group["label"],
                "analysis_label": profile_group["analysis_label"],
                "interpretation": profile_group["interpretation"],
                "expanded_by_default": group["id"] == "roads",
                "blend_default": 50,
                "group_color": _source_color(group_index, 0),
                "source_map_default_visible": bool(
                    profile_group.get("source_map_default_visible", False)
                ),
            }
        )
    raw = {
        "schema_version": "1.0",
        "analysis_id": "standard_constraints",
        "region_id": region_id,
        "groups": [group["id"] for group in declared_groups],
        "ui": {"groups": ui_groups},
        "default_request": {"selected_layer_ids": []},
        "analysis_domain_reference": {
            "type": "region_geography",
            "domain_id": form["geography"]["standard_analysis_domain"][
                "domain_id"
            ],
        },
        "layers": layer_manifests,
    }
    executable = dict(raw)
    executable.pop("analysis_domain_reference")
    executable["analysis_domain"] = dict(domain_artifacts)
    contract = analysis_contract(executable)
    validate_contract(contract)

    evidence: list[dict[str, Any]] = []
    previous_generated_root = os.environ.get(GENERATED_RUNTIME_ROOT_ENV)
    os.environ[GENERATED_RUNTIME_ROOT_ENV] = str(generated_root)
    try:
        for layer_id in sorted(contract.layers):
            layer = contract.layers[layer_id]
            validated = validate_layer(layer)
            artifact = build_direct_distance_artifact(
                layer,
                analysis_domain=contract.analysis_domain,
                native_crs=str(form["region"]["native_crs"]),
            )
            distance_path_value = str(layer.source.distance_path)
            distance_path = _generated_path(generated_root, distance_path_value)
            with distance_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(("hex_id", "distance_m", "intersects"))
                for row in artifact.rows:
                    distance = f"{row.distance_m:.12f}".rstrip("0").rstrip(".")
                    writer.writerow(
                        (
                            row.cell_id,
                            distance or "0",
                            "true" if row.intersects else "false",
                        )
                    )
            if not validated.processing_adapter.strip():
                raise ValueError(
                    "The generic processing adapter resolved to a blank identity"
                )
            evidence.append(
                {
                    "layer_id": layer_id,
                    "operation": layer.operation,
                    "geometry_family": validated.geometry_family,
                    "data_representation": layer.source.data_representation,
                    "processing_adapter": validated.processing_adapter,
                    "source_feature_count": validated.assets.feature_count,
                    "observation_row_count": len(artifact.rows),
                    "cell_ids_sha256": domain_id_digest,
                    "source_sha256": sha256_path(validated.assets.geojson_path),
                    "observations_sha256": sha256_path(distance_path),
                    **parameter_evidence_by_layer_id[layer_id],
                }
            )
        rows_by_id = {str(row["layer_id"]): row for row in layer_rows}
        for layer_id, layer in contract.layers.items():
            row = rows_by_id[layer_id]
            source_path = _generated_path(
                generated_root,
                str(row["geojson_path"]),
            )
            distance_path = _generated_path(
                generated_root,
                str(row["distance_path"]),
            )
            row.update(
                {
                    "geojson_bytes": source_path.stat().st_size,
                    "geojson_sha256": sha256_path(source_path),
                    "distance_bytes": distance_path.stat().st_size,
                    "distance_sha256": sha256_path(distance_path),
                }
            )
        write_asset_manifest()
        for layer in contract.layers.values():
            validate_layer(layer)
    finally:
        if previous_generated_root is None:
            os.environ.pop(GENERATED_RUNTIME_ROOT_ENV, None)
        else:
            os.environ[GENERATED_RUNTIME_ROOT_ENV] = previous_generated_root
    return raw, evidence, tuple(sorted(set(generated_paths)))


def _region_manifest(
    form: Mapping[str, Any],
    *,
    has_geography: bool,
    has_landscape: bool,
    has_scenario: bool,
    has_social_acceptance: bool,
    has_combined_result: bool,
    technologies: Iterable[str],
) -> dict[str, Any]:
    region = form["region"]
    access = form["access"]
    region_id = str(region["region_id"])
    behavior = region["behavior_reference"]
    trust_classification = str(access["trust_classification"])
    profile_capabilities = tuple(
        str(value) for value in _workspace_profile()["capabilities"]
    )
    requested_review_capabilities = tuple(
        str(value)
        for value in access["local_review"]["allowed_capabilities"]
    )
    requested_review_capability_set = set(requested_review_capabilities)
    if (
        len(requested_review_capabilities)
        != len(requested_review_capability_set)
        or requested_review_capability_set.difference(profile_capabilities)
    ):
        raise ValueError(
            "Local review capabilities must be unique workspace-profile ids"
        )
    allowed_review_capabilities = tuple(
        capability_id
        for capability_id in profile_capabilities
        if capability_id in requested_review_capability_set
    )
    if behavior["state"] == "declared":
        behavior_reference = {
            "status": behavior_status_for_trust(trust_classification),
            "source": behavior["source"],
            "label": behavior["label"],
            "reference": behavior.get("reference", ""),
            "frozen_v2_parity": (
                trust_classification == PRODUCT_TRUST_CLASSIFICATION
                and behavior["source"] == "frozen_reference"
            ),
        }
    else:
        behavior_reference = {
            "status": "diagnostic_only",
            "source": "unavailable",
            "reason": behavior["reason"],
            "frozen_v2_parity": False,
        }
    technology_ids = tuple(technologies)
    value: dict[str, Any] = {
        "schema_version": "2026-08-14",
        "region_id": region_id,
        "display_name": region["display_name"],
        "country": region["country_name"],
        "country_code": region["country_code"],
        "status": access["lifecycle"],
        "data_status": trust_classification,
        "behavior_reference": behavior_reference,
        "native_crs": region["native_crs"],
        "web_crs": region["web_crs"],
        "available_h3_resolutions": [
            form["map_h3"]["analysis_resolution"],
            *form["map_h3"]["rollup_resolutions"],
        ],
        "default_h3_resolution": form["map_h3"]["analysis_resolution"],
        "default_map_center": form["map_h3"]["center"],
        "default_zoom": form["map_h3"]["zoom"],
        "workspace_profile": WORKSPACE_PROFILE_PATH,
        "analysis_manifests": {
            technology_id: f"regions/{region_id}/analyses/{technology_id}.json"
            for technology_id in technology_ids
        },
        "landing_card": {
            **access["landing_card"],
            # A human request never publishes a route. This first compiler
            # intentionally emits compiled_unvalidated readiness, so the
            # publication gate remains closed even for an accepted form.
            "enabled": False,
        },
        "review_access": {
            "enabled": access["local_review"]["enabled"],
            "mode": "review",
            "surface": "shared_workspace",
            "access_classification": trust_classification,
            "requires_environment_allowlist": True,
            "entry_label": "Öppna lokal arbetsyta",
            "entry_note": "Gemensam manifeststyrd arbetsyta för lokal, operatörstillåten granskning.",
            "warning_title": "Regionpaketet är öppnat i lokal review.",
            "warning_body": f"Tillitsnivån är {trust_classification}. Landingkortet är avstängt; denna vy är inte en publicerad produktrutt.",
            "status_intro": "Status kommer från den kompilerade regionblanketten och dess integritetsevidens.",
            "allowed_use": "Lokal granskning av uttryckligen deklarerade capabilities.",
            "forbidden_use": "Offentlig produktåtkomst; review får inte tolkas som publicering.",
            "allowed_capabilities": list(allowed_review_capabilities),
            "allowed_slices": [
                {
                    "analysis_id": capability.split(".group.", 1)[0],
                    "group_id": capability.split(".group.", 1)[1],
                    "apply_required": True,
                    "auto_select_sources": False,
                    "explicit_parameters": ["buffer_m"],
                }
                for capability in allowed_review_capabilities
                if ".group." in capability
            ],
        },
        "region_package_readiness": (
            f"regions/{region_id}/{READINESS_FILE_NAME}"
        ),
    }
    if has_geography:
        value["geography_manifest"] = f"regions/{region_id}/geography.json"
    if has_landscape:
        value["landscape_manifest"] = f"regions/{region_id}/landscape.json"
    if has_scenario:
        value["scenario_manifest"] = f"regions/{region_id}/scenarios.json"
    if has_social_acceptance:
        value["social_acceptance_manifest"] = (
            f"regions/{region_id}/social_acceptance.json"
        )
    if has_combined_result:
        value["combined_result_manifest"] = (
            f"regions/{region_id}/combined_result.json"
        )
        technical_validation = form["combined_result"].get(
            "technical_validation"
        )
        if isinstance(technical_validation, Mapping):
            value["combined_result_validation"] = str(
                technical_validation["path"]
            )
            value["combined_result_validation_sha256"] = str(
                technical_validation["integrity"]["sha256"]
            )
    return value


def _technology_manifests(
    form: Mapping[str, Any],
    *,
    analysis_manifest: Mapping[str, Any] | None,
    area_results: Mapping[str, Mapping[str, Any]] | None = None,
    rooftop_solar: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    if analysis_manifest is None:
        return {}
    region_id = str(form["region"]["region_id"])
    declared_groups = {
        str(group["id"])
        for group in form["standard_groups"]
        if group["state"] == "declared"
    }
    values: dict[str, dict[str, Any]] = {}
    for technology_id, technology in form["technologies"].items():
        if technology["state"] != "declared":
            continue
        applicable_group_ids = tuple(
            str(group_id) for group_id in technology["applicable_group_ids"]
        )
        applicable = set(applicable_group_ids)
        if not applicable or not applicable.issubset(declared_groups):
            continue
        layers_by_group: dict[str, list[dict[str, Any]]] = {
            group_id: [] for group_id in applicable_group_ids
        }
        for layer in analysis_manifest.get("layers") or ():
            if not isinstance(layer, Mapping):
                continue
            group_id = str(layer.get("group_id") or "")
            if group_id in layers_by_group:
                layers_by_group[group_id].append(dict(layer))
        ui_by_group = {
            str(item.get("id") or ""): dict(item)
            for item in ((analysis_manifest.get("ui") or {}).get("groups") or ())
            if isinstance(item, Mapping)
        }
        if any(
            not layers_by_group[group_id] or group_id not in ui_by_group
            for group_id in applicable_group_ids
        ):
            continue
        value = {
            "schema_version": "1.0",
            "analysis_id": technology_id,
            "region_id": region_id,
            "extends": f"regions/{region_id}/{STANDARD_ANALYSIS_FILE}",
            # Inheritance supplies the shared domain/default contract only.
            # These three fields deliberately replace, rather than append to,
            # the base collections so one technology cannot inherit another
            # technology's groups or sources.
            "groups": list(applicable_group_ids),
            "ui": {
                "groups": [
                    ui_by_group[group_id]
                    for group_id in applicable_group_ids
                ]
            },
            "layers": [
                layer
                for group_id in applicable_group_ids
                for layer in layers_by_group[group_id]
            ],
        }
        if area_results and technology_id in area_results:
            value["area_result"] = dict(area_results[technology_id])
        if technology_id == "solar" and rooftop_solar is not None:
            value["distributed_generation"] = {
                "rooftop_solar": dict(rooftop_solar)
            }
        values[technology_id] = value
    return values


def _capability_readiness(
    form: Mapping[str, Any],
    *,
    compiled_technologies: set[str],
    has_geography: bool,
    has_landscape: bool = False,
    landscape_failure: tuple[str, str] | None = None,
    compiled_area_technologies: set[str] | None = None,
    technology_support_failure: tuple[str, str] | None = None,
    compiled_rooftop: bool = False,
    rooftop_failure: tuple[str, str] | None = None,
    compiled_scenario: bool = False,
    scenario_failure: tuple[str, str] | None = None,
    compiled_social_acceptance: bool = False,
    social_acceptance_failure: tuple[str, str] | None = None,
    compiled_combined_result: bool = False,
    combined_result_failure: tuple[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Build the sole readiness authority in workspace-profile order.

    Successful compilation proves that declared bytes can be read and
    materialized. It does not prove a technical gate, regional acceptance, or
    publication. Runnable compiler output therefore stops at
    ``not_validated`` and undeclared contracts remain ``missing_manifest``.
    """

    profile = _workspace_profile()
    compiled_areas = set(compiled_area_technologies or ())
    raw_capability_ids = profile.get("capabilities")
    if not isinstance(raw_capability_ids, list):
        raise TypeError("Workspace-profile capabilities must be a JSON array")
    if any(
        not isinstance(value, str) or not value.strip()
        for value in raw_capability_ids
    ):
        raise TypeError(
            "Workspace-profile capability ids must be non-empty strings"
        )
    capability_ids = tuple(raw_capability_ids)
    if (
        not capability_ids
        or len(capability_ids) != len(set(capability_ids))
    ):
        raise ValueError(
            "Workspace-profile capabilities must be non-empty and unique"
        )

    groups = {str(group["id"]): group for group in form["standard_groups"]}
    result: list[dict[str, Any]] = []
    rows_by_id: dict[str, dict[str, Any]] = {}

    def add(
        capability_id: str,
        state: str,
        reason: str,
        next_action: str,
    ) -> None:
        if state not in READINESS_STATES:
            raise ValueError(f"Unsupported readiness state: {state!r}")
        row = {
            "capability_id": capability_id,
            "state": state,
            "reason": " ".join(str(reason).split()),
            "next_action": " ".join(str(next_action).split()),
        }
        result.append(row)
        rows_by_id[capability_id] = row

    def dependency_state(
        dependencies: tuple[str, ...],
    ) -> tuple[str, str] | None:
        for state in READINESS_STATES[:4]:
            dependency = next(
                (
                    rows_by_id[dependency_id]
                    for dependency_id in dependencies
                    if rows_by_id[dependency_id]["state"] == state
                ),
                None,
            )
            if dependency is not None:
                return (
                    state,
                    f"Beroendet {dependency['capability_id']} är inte klart: "
                    f"{dependency['reason']}",
                )
        return None

    for capability_id in capability_ids:
        if capability_id == "workspace.map":
            if has_geography:
                add(
                    capability_id,
                    "not_validated",
                    "Geografimanifest, domän och genererad integritet är materialiserade men den tekniska kartgrinden återstår.",
                    "Kör geografins och kartans tekniska gates innan capabilityn promoveras.",
                )
            else:
                boundary = form["geography"]["boundary"]
                domain = form["geography"]["standard_analysis_domain"]
                reason = (
                    str(boundary["reason"])
                    if boundary["state"] != "declared"
                    else str(domain["reason"])
                )
                add(
                    capability_id,
                    "missing_manifest",
                    reason,
                    "Deklarera både regiongräns och standardanalysdomän.",
                )
            continue

        if capability_id == "workspace.landscape":
            landscape = form["landscape"]
            if landscape["state"] != "declared":
                add(
                    capability_id,
                    "missing_manifest",
                    str(landscape["reason"]),
                    "Deklarera ett komplett display-only-landskapskontrakt; använd ingen annan regions data.",
                )
            elif landscape_failure is not None:
                state, reason = landscape_failure
                add(
                    capability_id,
                    state,
                    reason,
                    "Korrigera landskapets källa, domänbindning eller implementera den saknade generella adaptern.",
                )
            elif has_landscape:
                add(
                    capability_id,
                    "not_validated",
                    "Display-only-landskapsmanifest, checksumma, fältinventering, H3-täckning, legend och rollupkontrakt är materialiserade; den fristående tekniska gaten återstår.",
                    "Kör landskapets rena load-, coverage- och view-gate före teknisk promotion.",
                )
            else:
                add(
                    capability_id,
                    "not_implemented",
                    "Landskapet är deklarerat men kunde inte materialiseras av den generella konsumenten.",
                    "Slutför den generella landskapsadaptern utan regionundantag.",
                )
            continue

        if ".group." in capability_id:
            technology_id, group_id = capability_id.split(".group.", 1)
            technology = form["technologies"].get(technology_id)
            group = groups.get(group_id)
            if not isinstance(technology, Mapping):
                add(
                    capability_id,
                    "missing_manifest",
                    "Tekniken saknas i regionblanketten.",
                    "Deklarera teknikens kontrakt i regionblanketten.",
                )
            elif technology["state"] != "declared":
                add(
                    capability_id,
                    "missing_manifest",
                    str(technology["reason"]),
                    "Deklarera teknikens kontrakt i regionblanketten.",
                )
            elif not isinstance(group, Mapping) or group["state"] != "declared":
                add(
                    capability_id,
                    "missing_manifest",
                    str(
                        (group or {}).get("reason")
                        or "Gruppen saknas i regionblanketten."
                    ),
                    "Deklarera gruppens källor eller behåll capabilityn låst.",
                )
            elif group_id not in technology["applicable_group_ids"]:
                add(
                    capability_id,
                    "missing_manifest",
                    "Gruppen är inte deklarerad som tillämplig för tekniken.",
                    "Lägg till gruppen endast om regional policy stöder den.",
                )
            elif technology_id not in compiled_technologies:
                add(
                    capability_id,
                    "not_implemented",
                    "Teknikmanifestet kunde inte materialiseras av den nuvarande generiska konsumenten.",
                    "Implementera den saknade generiska konsumenten; skapa ingen regiongren.",
                )
            else:
                add(
                    capability_id,
                    "not_validated",
                    "Manifest, data och genererad integritet är kompletta men capabilityns tekniska gate återstår.",
                    "Kör capabilityns tekniska gate och därefter regionens egen acceptansjämförelse.",
                )
            continue

        if capability_id in {"wind.area", "solar.area"}:
            technology_id = capability_id.split(".", 1)[0]
            technology = form["technologies"][technology_id]
            if technology["state"] != "declared":
                add(
                    capability_id,
                    "missing_manifest",
                    str(technology["reason"]),
                    "Deklarera teknikens kontrakt och etableringsyta.",
                )
            elif technology["area_result"]["state"] != "declared":
                add(
                    capability_id,
                    "missing_manifest",
                    str(technology["area_result"]["reason"]),
                    "Deklarera teknikens area_result och berättigade yta.",
                )
            elif form["geography"]["technology_support"]["state"] != "declared":
                support = form["geography"]["technology_support"]
                add(
                    capability_id,
                    "missing_manifest",
                    str(support["reason"]),
                    "Deklarera geography.technology_support med målyta, eligible surface och teknikkontext.",
                )
            elif technology_support_failure is not None:
                state, reason = technology_support_failure
                add(
                    capability_id,
                    state,
                    reason,
                    "Korrigera den deklarerade teknikytans källa eller implementera den saknade generella adaptern.",
                )
            elif technology_id not in compiled_areas:
                add(
                    capability_id,
                    "not_implemented",
                    "Area-resultatet är deklarerat men kunde inte bindas till ett komplett generiskt teknikytkontrakt.",
                    "Slutför den generella compilerkonsumenten utan regionundantag.",
                )
            else:
                add(
                    capability_id,
                    "not_validated",
                    "Area-resultat, eligible surface, teknikkontext och kompletta supportobservationer är materialiserade; den fristående tekniska gaten återstår.",
                    "Kör area-, teknikstöds- och regionspecifika acceptansgater innan capabilityn promoveras.",
                )
            continue

        if capability_id == "solar.rooftop":
            declaration = form["solar_rooftop"]
            if declaration["state"] != "declared":
                add(
                    capability_id,
                    "missing_manifest",
                    str(declaration["reason"]),
                    "Deklarera taksolens domän, befolkningskälla, parameter, solutbyte, redovisningspolicy, provenance och tillit komplett.",
                )
            elif rooftop_failure is not None:
                state, reason = rooftop_failure
                add(
                    capability_id,
                    state,
                    reason,
                    "Korrigera taksolens deklarerade källa eller slutför den saknade generella adaptern; använd ingen annan regions data.",
                )
            elif not compiled_rooftop:
                add(
                    capability_id,
                    "not_implemented",
                    "Taksolskontraktet är deklarerat men kunde inte bindas till solens kompletta generiska area- och domänkontrakt.",
                    "Slutför den generella capabilitykonsumenten utan regionundantag.",
                )
            else:
                add(
                    capability_id,
                    "not_validated",
                    "Taksolens typade kontrakt, checksumma, källantal, domäntäckning, rollups och generiska redovisningsoperation är materialiserade; den fristående tekniska gaten återstår.",
                    "Kör taksolens request-, executor-, integritets- och regionspecifika acceptansgater före promotion.",
                )
            continue

        if capability_id == "workspace.technology_context":
            blocked = dependency_state(("wind.area", "solar.area"))
            if blocked is not None:
                state, reason = blocked
                add(
                    capability_id,
                    state,
                    reason,
                    "Slutför båda teknikernas deklarerade etableringsytor först.",
                )
            else:
                add(
                    capability_id,
                    "not_validated",
                    "Vind och sol refererar till samma materialiserade, checksummebundna H3-teknikkontext; den fristående tekniska gaten återstår.",
                    "Kör teknikkontextens integritets- och konsumtionsgate innan capabilityn promoveras.",
                )
            continue

        if capability_id == "workspace.scenario":
            section = form["scenario"]
            if section["state"] != "declared":
                add(
                    capability_id,
                    "missing_manifest",
                    str(section["reason"]),
                    "Deklarera scenariots källor, adapter, nivåer och tillitsvillkor komplett eller behåll capabilityn låst.",
                )
            elif scenario_failure is not None:
                state, reason = scenario_failure
                add(
                    capability_id,
                    state,
                    reason,
                    "Korrigera scenariots deklarerade källa eller slutför den saknade generella adaptern; använd ingen regiongren eller annan regions data implicit.",
                )
            elif not compiled_scenario:
                add(
                    capability_id,
                    "not_implemented",
                    "Scenariokontraktet är deklarerat men kunde inte bindas till den generella request/result-kedjan.",
                    "Slutför den generella scenariokonsumenten utan regionundantag.",
                )
            else:
                add(
                    capability_id,
                    "not_validated",
                    "Scenariots typade kontrakt, checksummebundna källor och deterministiska request/result-evidens är materialiserade; datatillit och de fristående tekniska och regionala gaterna förblir separata.",
                    "Kör scenariots request-, executor-, integritets- och regionspecifika acceptansgater före promotion.",
                )
            continue

        if capability_id == "workspace.social_acceptance":
            section = form["social_acceptance"]
            if section["state"] != "declared":
                add(
                    capability_id,
                    "missing_manifest",
                    str(section["reason"]),
                    "Deklarera capabilityns regionala kontrakt eller behåll den låst.",
                )
            elif social_acceptance_failure is not None:
                state, reason = social_acceptance_failure
                add(
                    capability_id,
                    state,
                    reason,
                    "Korrigera social-acceptansens deklarerade källa eller slutför den saknade generella adaptern; använd ingen annan regions data implicit.",
                )
            elif not compiled_social_acceptance:
                add(
                    capability_id,
                    "not_implemented",
                    "Social-acceptanskontraktet är deklarerat men kunde inte bindas till den generella request/result-kedjan.",
                    "Slutför den generella social-acceptanskonsumenten utan regionundantag.",
                )
            else:
                add(
                    capability_id,
                    "not_validated",
                    "Social-acceptansens typade kontrakt, checksummebundna H3-källor, explicita ej bedömda celler och deterministiska request/result-evidens är materialiserade; datatillit och teknisk readiness förblir separata.",
                    "Kör social-acceptansens request-, executor-, integritets- och regionspecifika acceptansgater före promotion.",
                )
            continue

        if capability_id == "workspace.combined_result":
            section = form["combined_result"]
            if section["state"] != "declared":
                add(
                    capability_id,
                    "missing_manifest",
                    str(section["reason"]),
                    "Declare the complete combined policy or keep the capability locked.",
                )
                continue
            if combined_result_failure is not None:
                state, reason = combined_result_failure
                add(
                    capability_id,
                    state,
                    reason,
                    "Correct the explicit policy or register its region-neutral score-input executor; do not add a hidden default.",
                )
                continue
            if compiled_combined_result:
                add(
                    capability_id,
                    "not_validated",
                    "The policy contract, registered score executor, generated cell values and signatures are materialized; the independent request/result gate remains.",
                    "Run the pure combined-result gate against exact upstream results before technical promotion.",
                )
                continue
            blocked = dependency_state(
                (
                    "wind.area",
                    "solar.area",
                    "workspace.technology_context",
                    "workspace.scenario",
                    "solar.rooftop",
                    "workspace.social_acceptance",
                )
            )
            if blocked is not None:
                state, reason = blocked
                add(
                    capability_id,
                    state,
                    reason,
                    "Slutför det saknade beroendet innan kombinerat resultat kan valideras.",
                )
            else:
                add(
                    capability_id,
                    "not_implemented",
                    "Regioncompilern materialiserar ännu inte den generiska konsumenten för kombinerat resultat.",
                    "Implementera den generiska kombinerade resultatkonsumenten.",
                )
            continue

        add(
            capability_id,
            "not_implemented",
            "Workspace-profilen deklarerar capabilityn men regioncompilern saknar en registrerad generell readinesskonsument.",
            "Implementera en regionsneutral compilerkonsument och dess tekniska gate.",
        )

    if tuple(row["capability_id"] for row in result) != capability_ids:
        raise ValueError(
            "Compiler readiness drifted from workspace-profile capability order"
        )
    return result


def _copy_generated_files(
    stage_root: Path,
    target_root: Path,
    relative_paths: Iterable[str],
    *,
    overwrite: bool,
) -> tuple[Path, ...]:
    relative = tuple(sorted(set(relative_paths)))
    targets = tuple(_generated_path(target_root, value) for value in relative)
    existing = [path for path in targets if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"Generated output already exists: {existing[0]}")
    for value, target in zip(relative, targets, strict=True):
        source = _generated_path(stage_root, value)
        if not source.is_file():
            raise FileNotFoundError(f"Staged generated output is missing: {value}")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.name}.tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(target)
    return targets


def _write_manifests(
    output_root: Path,
    values: Mapping[str, Mapping[str, Any]],
    *,
    overwrite: bool,
) -> tuple[Path, ...]:
    targets = {
        relative: output_root.joinpath(*PurePosixPath(relative).parts).resolve()
        for relative in values
    }
    if any(not _within(output_root.resolve(), path) for path in targets.values()):
        raise ValueError("Manifest output escapes output root")
    existing = [path for path in targets.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(f"Manifest output already exists: {existing[0]}")
    written: list[Path] = []
    for relative in sorted(values):
        target = targets[relative]
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f"{target.name}.tmp")
        temporary.write_bytes(_json_bytes(values[relative]))
        temporary.replace(target)
        written.append(target)
    return tuple(written)


def compile_region_package_file(
    form_path: Path,
    *,
    output_root: Path,
    generated_root: Path,
    overwrite: bool = False,
    dry_run: bool = False,
) -> CompiledRegionPackage:
    """Validate and deterministically materialize one human region form.

    Large derived geometry and observation artifacts are written only beneath
    ``generated_root``. Repository-owned submanifests are written beneath the
    explicit ``output_root``. Structural or standard-analysis failures abort
    before either publication step. A declared but incomplete optional
    technology-support, display-landscape, or rooftop-solar slice is instead
    omitted from the materialized manifests and reported with its exact
    fail-closed state; it can never create partial area/context/landscape/
    rooftop references or open the landing card.
    """

    source_path = form_path.resolve()
    source = str(source_path)
    value, validation_problems = validate_region_package_file(source_path)
    if validation_problems or value is None:
        raise RegionPackageCompilationError(validation_problems)
    generated_target = generated_root.resolve()
    if not generated_target.is_dir():
        raise RegionPackageCompilationError(
            (
                _problem(
                    code="MF-OUTPUT-001",
                    source=source,
                    pointer="/",
                    message="Generated-runtime-roten finns inte.",
                    help_text="Skapa en uttrycklig katalog utanför Git-repot och ange den med --generated-root.",
                    expected="existing external directory",
                    actual=str(generated_target),
                ),
            )
        )
    repository = repo_root().resolve()
    if _within(repository, generated_target):
        raise RegionPackageCompilationError(
            (
                _problem(
                    code="MF-OUTPUT-002",
                    source=source,
                    pointer="/",
                    message="Genererade runtimeartefakter får inte skrivas i Git-repot.",
                    help_text="Välj en separat generated-runtime-katalog utanför arbetsytan.",
                    expected="path outside repository",
                    actual=str(generated_target),
                ),
            )
        )

    resolved_assets, asset_problems = _resolve_declared_assets(
        value,
        source=source,
        generated_root=generated_target,
    )
    technology_asset_problems = tuple(
        problem
        for problem in asset_problems
        if problem.pointer.startswith("/geography/technology_support/")
    )
    landscape_asset_problems = tuple(
        problem
        for problem in asset_problems
        if problem.pointer.startswith("/landscape/")
    )
    rooftop_asset_problems = tuple(
        problem
        for problem in asset_problems
        if problem.pointer.startswith("/solar_rooftop/")
    )
    scenario_asset_problems = tuple(
        problem
        for problem in asset_problems
        if problem.pointer.startswith("/scenario/")
    )
    social_acceptance_asset_problems = tuple(
        problem
        for problem in asset_problems
        if problem.pointer.startswith("/social_acceptance/")
    )
    fatal_asset_problems = tuple(
        problem
        for problem in asset_problems
        if problem not in technology_asset_problems
        and problem not in landscape_asset_problems
        and problem not in rooftop_asset_problems
        and problem not in scenario_asset_problems
        and problem not in social_acceptance_asset_problems
    )
    if fatal_asset_problems:
        raise RegionPackageCompilationError(fatal_asset_problems)
    technology_support_failure: tuple[str, str] | None = None
    if technology_asset_problems:
        technology_support_failure = (
            "missing_data",
            " ".join(problem.message for problem in technology_asset_problems),
        )
    rooftop_failure: tuple[str, str] | None = (
        (
            "missing_data",
            " ".join(problem.message for problem in rooftop_asset_problems),
        )
        if rooftop_asset_problems
        else None
    )
    scenario_failure: tuple[str, str] | None = (
        (
            "missing_data",
            " ".join(problem.message for problem in scenario_asset_problems),
        )
        if scenario_asset_problems
        else None
    )
    social_acceptance_failure: tuple[str, str] | None = (
        (
            "missing_data",
            " ".join(
                problem.message
                for problem in social_acceptance_asset_problems
            ),
        )
        if social_acceptance_asset_problems
        else None
    )

    boundary_form = value["geography"]["boundary"]
    domain_form = value["geography"]["standard_analysis_domain"]
    geography_complete = (
        boundary_form["state"] == "declared"
        and domain_form["state"] == "declared"
    )
    declared_groups = [
        group for group in value["standard_groups"] if group["state"] == "declared"
    ]
    compiler_problems: list[ManifestProblem] = []
    for section_name in ("scenario", "social_acceptance"):
        section = value[section_name]
        if (
            section["state"] == "declared"
            and section["status"] == "accepted_regional"
            and section["source_region_id"] != value["region"]["region_id"]
        ):
            compiler_problems.append(
                _problem(
                    code="MF-ACCEPTANCE-001",
                    source=source,
                    pointer=f"/{section_name}/source_region_id",
                    message="Regionalt accepterad evidens tillhör inte regionpaketets egen region.",
                    help_text="Använd samma region_id för accepterad evidens. Data från en annan region måste klassificeras som provisional_fallback.",
                    expected=value["region"]["region_id"],
                    actual=section["source_region_id"],
                )
            )
    if declared_groups and not geography_complete:
        compiler_problems.append(
            _problem(
                code="MF-DOMAIN-001",
                source=source,
                pointer="/geography/standard_analysis_domain",
                message="Deklarerade analyslager saknar en komplett analysdomän.",
                help_text="Deklarera både boundary och standard_analysis_domain eller markera grupperna unavailable.",
                expected="declared boundary and domain",
                actual=domain_form["state"],
            )
        )
    for group_index, group in enumerate(value["standard_groups"]):
        if group["state"] != "declared":
            continue
        group_id = str(group["id"])
        capability_ids = tuple(
            f"{technology_id}.group.{group_id}"
            for technology_id, technology in value["technologies"].items()
            if technology["state"] == "declared"
            and group_id in technology["applicable_group_ids"]
        )
        capability_label = ", ".join(capability_ids) or (
            f"standard_group.{group_id}"
        )
        for layer_index, layer in enumerate(group["layers"]):
            source_kind = layer["source"]["source_kind"]
            source_format = layer["source"]["asset"]["format"]
            pointer = f"/standard_groups/{group_index}/layers/{layer_index}"
            if source_kind != "vector_file":
                compiler_problems.append(
                    _problem(
                        code="MF-CONSUMER-001",
                        source=source,
                        pointer=f"{pointer}/source/source_kind",
                        message=f"{capability_label} saknar ännu en generell compilerkonsument för den deklarerade källtypen.",
                        help_text="Implementera källadaptern generellt eller använd en stödd vector_file; skapa ingen regiongren.",
                        expected={
                            "capability_ids": capability_ids,
                            "source_kind": "vector_file",
                        },
                        actual={
                            "capability_ids": capability_ids,
                            "source_kind": source_kind,
                        },
                    )
                )
            if source_format != "geojson":
                compiler_problems.append(
                    _problem(
                        code="MF-CONSUMER-003",
                        source=source,
                        pointer=f"{pointer}/source/asset/format",
                        message=f"{capability_label} saknar ännu en generell compilerkonsument för det deklarerade källformatet.",
                        help_text="Implementera formatadaptern generellt eller använd det stödda formatet geojson; skapa ingen regiongren.",
                        expected={
                            "capability_ids": capability_ids,
                            "format": "geojson",
                        },
                        actual={
                            "capability_ids": capability_ids,
                            "format": source_format,
                        },
                    )
                )
            if (
                layer["geometry_family"] == "grid"
                or layer["source"]["geometry_family"] == "grid"
            ):
                compiler_problems.append(
                    _problem(
                        code="MF-CONSUMER-002",
                        source=source,
                        pointer=f"{pointer}/geometry_family",
                        message=f"{capability_label} saknar ännu en generell compileradapter för geometry_family=grid.",
                        help_text="Behåll grid-deklarationen i blanketten och implementera dess generella materialiseringsadapter; ersätt den inte med en regiongren eller en falsk vektorgeometri.",
                        expected={
                            "capability_ids": capability_ids,
                            "implemented_geometry_families": [
                                "point",
                                "line",
                                "polygon",
                            ],
                        },
                        actual={
                            "capability_ids": capability_ids,
                            "geometry_family": "grid",
                        },
                    )
                )
    if compiler_problems:
        raise RegionPackageCompilationError(compiler_problems)

    output = output_root.resolve()
    manifests: dict[str, dict[str, Any]] = {}
    all_generated_paths: list[str] = []
    geography_manifest: dict[str, Any] | None = None
    domain_evidence: dict[str, Any] | None = None
    analysis_manifest: dict[str, Any] | None = None
    layer_evidence: list[dict[str, Any]] = []
    area_results: Mapping[str, Mapping[str, Any]] = {}
    technology_support_evidence: Mapping[str, Any] | None = None
    landscape_manifest: dict[str, Any] | None = None
    landscape_evidence: Mapping[str, Any] | None = None
    rooftop_solar_contract: Mapping[str, Any] | None = None
    rooftop_evidence: Mapping[str, Any] | None = None
    scenario_manifest: dict[str, Any] | None = None
    scenario_evidence: Mapping[str, Any] | None = None
    social_acceptance_manifest: dict[str, Any] | None = None
    social_acceptance_evidence: Mapping[str, Any] | None = None
    combined_result_manifest: dict[str, Any] | None = None
    combined_result_evidence: Mapping[str, Any] | None = None
    combined_result_failure: tuple[str, str] | None = None
    combined_result_generated_paths: tuple[str, ...] = ()
    landscape_failure: tuple[str, str] | None = (
        (
            "missing_data",
            " ".join(problem.message for problem in landscape_asset_problems),
        )
        if landscape_asset_problems
        else None
    )
    try:
        with tempfile.TemporaryDirectory(prefix="speedlocal-region-compile-") as temp:
            stage_generated = Path(temp).resolve()
            if geography_complete:
                boundary = resolved_assets[id(boundary_form["asset"])]
                (
                    geography_manifest,
                    domain_evidence,
                    domain_paths,
                ) = _domain_manifest(
                    value,
                    boundary=boundary,
                    generated_root=stage_generated,
                )
                all_generated_paths.extend(domain_paths)
                domain_contract = next(
                    iter(geography_manifest["analysis_domains"].values())
                )
                value_with_evidence = dict(value)
                value_with_evidence["_generated_domain_digests"] = dict(
                    domain_contract["cell_ids_sha256"]
                )
                if declared_groups:
                    analysis_manifest, layer_evidence, layer_paths = (
                        _analysis_manifest(
                            value_with_evidence,
                            domain_artifacts=domain_contract["artifacts"],
                            generated_root=stage_generated,
                            resolved_assets=resolved_assets,
                        )
                    )
                    all_generated_paths.extend(layer_paths)

                support_form = value["geography"]["technology_support"]
                if (
                    support_form["state"] == "declared"
                    and analysis_manifest is not None
                    and technology_support_failure is None
                ):
                    context_form = support_form["technology_context"]
                    if context_form["state"] != "declared":
                        technology_support_failure = (
                            "missing_manifest",
                            str(context_form["reason"]),
                        )
                    else:
                        try:
                            support_compilation = materialize_technology_support(
                                value,
                                geography_manifest=geography_manifest,
                                analysis_manifest=analysis_manifest,
                                coverage_asset=resolved_assets[
                                    id(support_form["coverage_geometry"]["asset"])
                                ],
                                context_asset=resolved_assets[
                                    id(context_form["asset"])
                                ],
                                generated_root=stage_generated,
                            )
                        except NotImplementedError as exc:
                            technology_support_failure = (
                                "not_implemented",
                                str(exc),
                            )
                        except (KeyError, OSError, TypeError, ValueError) as exc:
                            technology_support_failure = (
                                "missing_data",
                                f"Teknikstödsdata klarar inte den generiska integritetskontrollen: {exc}",
                            )
                        else:
                            geography_manifest = (
                                support_compilation.geography_manifest
                            )
                            analysis_manifest = (
                                support_compilation.analysis_manifest
                            )
                            area_results = support_compilation.area_results
                            technology_support_evidence = (
                                support_compilation.evidence
                            )
                            all_generated_paths.extend(
                                support_compilation.generated_paths
                            )

                landscape_form = value["landscape"]
                if landscape_form["state"] == "declared":
                    source_reference = landscape_form["source_reference"]
                    if source_reference["kind"] == "technology_context":
                        support = value["geography"]["technology_support"]
                        context = (
                            support.get("technology_context")
                            if support["state"] == "declared"
                            else None
                        )
                        if (
                            not isinstance(context, Mapping)
                            or context.get("state") != "declared"
                            or context.get("id")
                            != source_reference.get("context_id")
                        ):
                            landscape_failure = (
                                "missing_manifest",
                                "Landskapets technology_context-referens är inte komplett deklarerad.",
                            )
                            landscape_source_asset = None
                        else:
                            landscape_source_asset = resolved_assets.get(
                                id(context["asset"])
                            )
                            if landscape_source_asset is None:
                                landscape_failure = (
                                    "missing_data",
                                    "Landskapets deklarerade technology_context-källa kan inte läsas eller verifieras.",
                                )
                    else:
                        landscape_source_asset = resolved_assets.get(
                            id(source_reference["asset"])
                        )
                        if landscape_source_asset is None:
                            landscape_failure = (
                                "missing_data",
                                "Landskapets självständiga källa kan inte läsas eller verifieras.",
                            )
                    domain_reference = landscape_form["domain_reference"]
                    standard_domains = geography_manifest["analysis_domains"]
                    domain_value = standard_domains.get(
                        domain_reference["domain_id"]
                    )
                    if not isinstance(domain_value, Mapping):
                        landscape_failure = (
                            "missing_manifest",
                            "Landskapets standarddomänreferens saknas i det materialiserade geografimanifestet.",
                        )
                    if (
                        landscape_failure is None
                        and landscape_source_asset is not None
                        and isinstance(domain_value, Mapping)
                    ):
                        domain_artifact = dict(domain_value["artifacts"])
                        domain_artifact["format"] = "geojson"
                        resolution = int(domain_artifact["resolution"])
                        domain_digest = str(
                            domain_value["cell_ids_sha256"][str(resolution)]
                        )
                        domain_path = _generated_path(
                            stage_generated,
                            str(domain_artifact["path"]),
                        )
                        try:
                            landscape_manifest = materialize_landscape_manifest(
                                landscape_form,
                                region_id=str(value["region"]["region_id"]),
                                source_asset=landscape_source_asset,
                                domain_artifact=domain_artifact,
                                domain_cell_ids_sha256=domain_digest,
                                domain_path=domain_path,
                            )
                        except NotImplementedError as exc:
                            landscape_failure = (
                                "not_implemented",
                                str(exc),
                            )
                        except (KeyError, OSError, TypeError, ValueError) as exc:
                            landscape_failure = (
                                "missing_data",
                                "Landskapsdata klarar inte den generiska "
                                f"integritetskontrollen: {exc}",
                            )
                        else:
                            landscape_evidence = landscape_manifest[
                                "generated_evidence"
                            ]
            elif value["landscape"]["state"] == "declared":
                landscape_failure = (
                    "missing_manifest",
                    "Landskapets deklarerade standarddomän kunde inte materialiseras.",
                )

            rooftop_form = value["solar_rooftop"]
            if rooftop_form["state"] == "declared" and rooftop_failure is None:
                if geography_manifest is None or analysis_manifest is None:
                    rooftop_failure = (
                        "missing_manifest",
                        "Taksolens deklarerade standarddomän kunde inte materialiseras.",
                    )
                elif "solar" not in area_results:
                    rooftop_failure = technology_support_failure or (
                        "not_implemented",
                        "Solens kompletta area-resultat kunde inte bindas till taksolens generiska redovisning.",
                    )
                else:
                    rooftop_domain_reference = rooftop_form["domain_reference"]
                    rooftop_domain_value = geography_manifest[
                        "analysis_domains"
                    ].get(rooftop_domain_reference["domain_id"])
                    rooftop_source_asset = resolved_assets.get(
                        id(rooftop_form["population_source"]["asset"])
                    )
                    if not isinstance(rooftop_domain_value, Mapping):
                        rooftop_failure = (
                            "missing_manifest",
                            "Taksolens standarddomänreferens saknas i geografimanifestet.",
                        )
                    elif rooftop_source_asset is None:
                        rooftop_failure = (
                            "missing_data",
                            "Taksolens deklarerade befolkningskälla kan inte läsas eller verifieras.",
                        )
                    else:
                        rooftop_domain_artifact = dict(
                            rooftop_domain_value["artifacts"]
                        )
                        rooftop_domain_artifact["format"] = "geojson"
                        rooftop_resolution = int(
                            rooftop_domain_artifact["resolution"]
                        )
                        rooftop_domain_digest = str(
                            rooftop_domain_value["cell_ids_sha256"][
                                str(rooftop_resolution)
                            ]
                        )
                        rooftop_domain_path = _generated_path(
                            stage_generated,
                            str(rooftop_domain_artifact["path"]),
                        )
                        try:
                            rooftop_compilation = materialize_rooftop_solar(
                                rooftop_form,
                                region_id=str(value["region"]["region_id"]),
                                source_asset=rooftop_source_asset,
                                domain_artifact=rooftop_domain_artifact,
                                domain_cell_ids_sha256=rooftop_domain_digest,
                                domain_path=rooftop_domain_path,
                                rollup_resolutions=tuple(
                                    int(item)
                                    for item in value["map_h3"][
                                        "rollup_resolutions"
                                    ]
                                ),
                            )
                        except NotImplementedError as exc:
                            rooftop_failure = ("not_implemented", str(exc))
                        except (KeyError, OSError, TypeError, ValueError) as exc:
                            rooftop_failure = (
                                "missing_data",
                                "Taksolens data klarar inte den generiska "
                                f"integritetskontrollen: {exc}",
                            )
                        else:
                            rooftop_solar_contract = rooftop_compilation.contract
                            rooftop_evidence = rooftop_compilation.evidence

            scenario_form = value["scenario"]
            if scenario_form["state"] == "declared" and scenario_failure is None:
                scenario_assets = scenario_form["assets"]
                energy_asset = resolved_assets.get(
                    id(scenario_assets["energy_model"])
                )
                area_demand_asset = resolved_assets.get(
                    id(scenario_assets["area_demand"])
                )
                if energy_asset is None or area_demand_asset is None:
                    scenario_failure = (
                        "missing_data",
                        "Scenariots deklarerade källartefakter kan inte läsas eller verifieras.",
                    )
                else:
                    try:
                        scenario_compilation = materialize_scenario_manifest(
                            scenario_form,
                            region_id=str(value["region"]["region_id"]),
                            energy_asset=energy_asset,
                            area_demand_asset=area_demand_asset,
                        )
                    except NotImplementedError as exc:
                        scenario_failure = ("not_implemented", str(exc))
                    except (KeyError, OSError, TypeError, ValueError) as exc:
                        scenario_failure = (
                            "missing_data",
                            "Scenariodata klarar inte den generiska "
                            f"integritets- och request/result-kontrollen: {exc}",
                        )
                    else:
                        scenario_manifest = dict(scenario_compilation.manifest)
                        scenario_evidence = scenario_compilation.evidence

            social_acceptance_form = value["social_acceptance"]
            if (
                social_acceptance_form["state"] == "declared"
                and social_acceptance_failure is None
            ):
                social_assets = social_acceptance_form["assets"]
                acceptance_values_asset = resolved_assets.get(
                    id(social_assets["acceptance_values"])
                )
                display_geometry_asset = resolved_assets.get(
                    id(social_assets["display_geometry"])
                )
                if (
                    acceptance_values_asset is None
                    or display_geometry_asset is None
                ):
                    social_acceptance_failure = (
                        "missing_data",
                        "Social-acceptansens deklarerade källartefakter kan inte läsas eller verifieras.",
                    )
                else:
                    try:
                        social_compilation = (
                            materialize_social_acceptance_manifest(
                                social_acceptance_form,
                                region_id=str(value["region"]["region_id"]),
                                acceptance_values_asset=(
                                    acceptance_values_asset
                                ),
                                display_geometry_asset=display_geometry_asset,
                            )
                        )
                    except NotImplementedError as exc:
                        social_acceptance_failure = (
                            "not_implemented",
                            str(exc),
                        )
                    except (KeyError, OSError, TypeError, ValueError) as exc:
                        social_acceptance_failure = (
                            "missing_data",
                            "Social-acceptansdata klarar inte den generella "
                            f"integritets- och request/result-kontrollen: {exc}",
                        )
                    else:
                        social_acceptance_manifest = dict(
                            social_compilation.manifest
                        )
                        social_acceptance_evidence = social_compilation.evidence

            combined_form = value["combined_result"]
            combined_order = tuple(
                str(item)
                for item in combined_form.get("technology_order", ())
            )
            combined_prerequisites_compiled = (
                combined_form["state"] == "declared"
                and analysis_manifest is not None
                and all(item in area_results for item in combined_order)
                and rooftop_solar_contract is not None
                and scenario_manifest is not None
                and social_acceptance_manifest is not None
            )
            if combined_prerequisites_compiled:
                try:
                    surface_contracts = analysis_manifest.get(
                        "eligible_surfaces"
                    )
                    if not isinstance(surface_contracts, Mapping):
                        raise KeyError(
                            "Combined result has no materialized eligible surfaces"
                        )
                    score_surfaces: dict[
                        str, ResolvedCombinedScoreSurface
                    ] = {}
                    for technology_id in combined_order:
                        area_contract = area_results[technology_id]
                        surface_id = str(area_contract["eligible_surface_id"])
                        surface = surface_contracts.get(surface_id)
                        if not isinstance(surface, Mapping):
                            raise KeyError(
                                f"Combined result has no surface {surface_id}"
                            )
                        provider = str(surface["provider"])
                        provider_path = str(surface["path"])
                        surface_path = (
                            _generated_path(stage_generated, provider_path)
                            if provider == "generated_runtime"
                            else resolve_source_path(provider, provider_path)
                        )
                        score_surfaces[technology_id] = (
                            ResolvedCombinedScoreSurface(
                                technology_id=technology_id,
                                provider=provider,
                                provider_path=provider_path,
                                path=surface_path,
                                sha256=str(surface["sha256"]),
                                id_field=str(surface["id_field"]),
                                resolution=int(surface["resolution"]),
                            )
                        )
                    combined_compilation = materialize_combined_result_policy(
                        combined_form,
                        region_id=str(value["region"]["region_id"]),
                        surfaces=score_surfaces,
                        generated_root=stage_generated,
                    )
                except NotImplementedError as exc:
                    combined_result_failure = (
                        "not_implemented",
                        str(exc),
                    )
                except (KeyError, OSError, TypeError, ValueError) as exc:
                    combined_result_failure = (
                        "missing_data",
                        "Combined-result policy data failed its generic "
                        f"materialization gate: {exc}",
                    )
                else:
                    combined_result_manifest = dict(
                        combined_compilation.manifest
                    )
                    combined_result_evidence = (
                        combined_compilation.evidence
                    )
                    combined_result_generated_paths = (
                        combined_compilation.generated_paths
                    )
                    all_generated_paths.extend(
                        combined_result_generated_paths
                    )

            technology_values = _technology_manifests(
                value,
                analysis_manifest=analysis_manifest,
                area_results=area_results,
                rooftop_solar=rooftop_solar_contract,
            )
            if (
                rooftop_solar_contract is not None
                and analysis_manifest is not None
                and geography_manifest is not None
                and "solar" in technology_values
            ):
                executable_solar = dict(analysis_manifest)
                executable_solar.update(
                    {
                        key: item
                        for key, item in technology_values["solar"].items()
                        if key != "extends"
                    }
                )
                executable_solar.pop("analysis_domain_reference", None)
                executable_solar["analysis_domain"] = dict(
                    geography_manifest["analysis_domains"][
                        rooftop_form["domain_reference"]["domain_id"]
                    ]["artifacts"]
                )
                try:
                    validate_contract(analysis_contract(executable_solar))
                except (KeyError, TypeError, ValueError) as exc:
                    rooftop_failure = (
                        "not_implemented",
                        "Taksolens materialiserade kontrakt klarar inte den "
                        f"generiska konsumentgrinden: {exc}",
                    )
                    rooftop_solar_contract = None
                    rooftop_evidence = None
                    technology_values = _technology_manifests(
                        value,
                        analysis_manifest=analysis_manifest,
                        area_results=area_results,
                    )
            compiled_technologies = set(technology_values)
            compiled_area_technologies = set(area_results).intersection(
                compiled_technologies
            )
            compiled_rooftop = (
                rooftop_solar_contract is not None
                and "solar" in compiled_technologies
            )
            compiled_scenario = scenario_manifest is not None
            compiled_social_acceptance = social_acceptance_manifest is not None
            compiled_combined_result = (
                combined_result_manifest is not None
                and compiled_rooftop
                and compiled_scenario
                and compiled_social_acceptance
                and set(combined_order).issubset(compiled_area_technologies)
            )
            if not compiled_combined_result and combined_result_manifest is not None:
                combined_result_manifest = None
                combined_result_evidence = None
                all_generated_paths = [
                    path
                    for path in all_generated_paths
                    if path not in combined_result_generated_paths
                ]
            region_manifest = _region_manifest(
                value,
                has_geography=geography_manifest is not None,
                has_landscape=landscape_manifest is not None,
                has_scenario=compiled_scenario,
                has_social_acceptance=compiled_social_acceptance,
                has_combined_result=compiled_combined_result,
                technologies=compiled_technologies,
            )
            manifests["region.json"] = region_manifest
            if geography_manifest is not None:
                manifests["geography.json"] = geography_manifest
            if landscape_manifest is not None:
                manifests["landscape.json"] = landscape_manifest
            if scenario_manifest is not None:
                manifests["scenarios.json"] = scenario_manifest
            if social_acceptance_manifest is not None:
                manifests["social_acceptance.json"] = social_acceptance_manifest
            if combined_result_manifest is not None:
                manifests["combined_result.json"] = combined_result_manifest
            if analysis_manifest is not None:
                manifests[STANDARD_ANALYSIS_FILE] = analysis_manifest
            for technology_id, technology_value in technology_values.items():
                manifests[f"analyses/{technology_id}.json"] = technology_value

            declared_asset_evidence = [
                {
                    "pointer": asset.pointer,
                    "provider": asset.provider,
                    "path": asset.provider_path,
                    "format": asset.format,
                    "integrity_mode": asset.integrity_mode,
                    "bytes": asset.bytes,
                    "sha256": asset.sha256,
                }
                for asset in sorted(
                    resolved_assets.values(),
                    key=lambda item: item.pointer,
                )
            ]
            output_manifest_evidence = {
                relative: {
                    "bytes": len(_json_bytes(manifest)),
                    "sha256": _sha256_bytes(_json_bytes(manifest)),
                }
                for relative, manifest in sorted(manifests.items())
            }
            readiness = {
                "schema_version": "1.0",
                "compiler": {
                    "id": "speedlocal_region_package_compiler",
                    "version": COMPILER_VERSION,
                },
                "region_id": value["region"]["region_id"],
                "form_schema_version": value["form_schema_version"],
                "form_canonical_sha256": _canonical_sha256(value),
                "materialization_status": "compiled_unvalidated",
                "publication_gate": {
                    "requested_by_form": value["access"][
                        "product_route_requested"
                    ],
                    "request_field": "product_route_requested",
                    "materialized_landing_card_enabled": False,
                    "state": "not_validated",
                    "reason": "En mänsklig blankett kan inte själv aktivera publicering; tekniska och regionala gates måste först vara uppfyllda.",
                },
                "generated_values_policy": {
                    "checksums": "computed_or_verified",
                    "domain_cell_counts": "computed",
                    "domain_cell_id_digests": "computed",
                    "domain_areas": "computed",
                    "distance_observation_counts": "computed",
                    "technology_surface_cell_counts": "computed",
                    "technology_surface_cell_id_digests": "computed",
                    "technology_surface_areas": "computed",
                    "technology_context_cell_counts": "computed",
                    "technology_context_cell_id_digests": "computed",
                    "landscape_field_inventory": "computed",
                    "landscape_cell_counts": "computed",
                    "landscape_cell_id_digests": "computed",
                    "landscape_domain_coverage": "computed",
                    "rooftop_source_row_count": "computed",
                    "rooftop_source_population_total": "computed",
                    "rooftop_source_cell_id_digest": "computed",
                    "rooftop_domain_coverage": "computed",
                    "rooftop_rollup_totals": "computed",
                    "rooftop_annual_yield_kwh_per_m2": "computed",
                    "scenario_source_asset_integrity": "computed_or_verified",
                    "scenario_observation_count": "computed_when_normalized_json",
                    "scenario_area_factor_count": "computed_when_normalized_json",
                    "scenario_result_signatures": "computed_when_normalized_json",
                    "social_acceptance_source_asset_integrity": "computed_or_verified",
                    "social_acceptance_observation_count": "computed",
                    "social_acceptance_explicit_unassessed_count": "computed_or_verified",
                    "social_acceptance_result_signatures": "computed",
                    "combined_result_policy_contract_signature": "computed",
                    "combined_result_cell_scores": "computed_by_registered_executor",
                    "combined_result_cell_score_input_signature": "computed",
                    "combined_result_allocation_policy_signature": "computed",
                    "support_observation_coverage": "computed",
                    "human_authored_integrity_values_required": False,
                    "engine_parameter_default": "technical_initial_value_not_regional_recommendation",
                },
                "declared_assets": declared_asset_evidence,
                "analysis_domain": domain_evidence,
                "technology_support": technology_support_evidence,
                "landscape": landscape_evidence,
                "solar_rooftop": rooftop_evidence,
                "scenario": scenario_evidence,
                "social_acceptance": social_acceptance_evidence,
                "combined_result": combined_result_evidence,
                "layers": layer_evidence,
                "manifests": output_manifest_evidence,
                "capabilities": _capability_readiness(
                    value,
                    compiled_technologies=compiled_technologies,
                    has_geography=geography_manifest is not None,
                    has_landscape=landscape_manifest is not None,
                    landscape_failure=landscape_failure,
                    compiled_area_technologies=compiled_area_technologies,
                    technology_support_failure=technology_support_failure,
                    compiled_rooftop=compiled_rooftop,
                    rooftop_failure=rooftop_failure,
                    compiled_scenario=compiled_scenario,
                    scenario_failure=scenario_failure,
                    compiled_social_acceptance=compiled_social_acceptance,
                    social_acceptance_failure=social_acceptance_failure,
                    compiled_combined_result=compiled_combined_result,
                    combined_result_failure=combined_result_failure,
                ),
            }
            manifests[READINESS_FILE_NAME] = readiness

            expected_generated_paths = tuple(
                _generated_path(generated_target, relative)
                for relative in sorted(set(all_generated_paths))
            )
            expected_manifest_paths = tuple(
                output.joinpath(*PurePosixPath(relative).parts).resolve()
                for relative in sorted(manifests)
            )
            if not dry_run and not overwrite:
                existing_targets = tuple(
                    path
                    for path in (
                        *expected_generated_paths,
                        *expected_manifest_paths,
                    )
                    if path.exists()
                )
                if existing_targets:
                    raise FileExistsError(
                        "Compiler output already exists: "
                        f"{existing_targets[0]}"
                    )
            if dry_run:
                generated_paths = expected_generated_paths
                manifest_paths = expected_manifest_paths
            else:
                generated_paths = _copy_generated_files(
                    stage_generated,
                    generated_target,
                    all_generated_paths,
                    overwrite=overwrite,
                )
                manifest_paths = _write_manifests(
                    output,
                    manifests,
                    overwrite=overwrite,
                )
    except RegionPackageCompilationError:
        raise
    except (FileExistsError, FileNotFoundError, OSError, TypeError, ValueError) as exc:
        raise RegionPackageCompilationError(
            (
                _problem(
                    code="MF-COMPILE-001",
                    source=source,
                    pointer="/",
                    message="Regionpaketet kunde inte materialiseras deterministiskt.",
                    help_text="Rätta det angivna data-, geometri- eller outputfelet och kör om; inga fallbackvärden används.",
                    expected="complete deterministic materialization",
                    actual=str(exc),
                ),
            )
        ) from exc
    return CompiledRegionPackage(
        region_id=str(value["region"]["region_id"]),
        output_root=output,
        generated_root=generated_target,
        manifest_paths=manifest_paths,
        generated_paths=generated_paths,
        readiness=readiness,
        materialized=not dry_run,
    )


def probe_region_package_file(
    form_path: Path,
    *,
    output_root: Path,
    generated_root: Path,
) -> CompiledRegionPackage:
    """Run the complete compiler without granting target-write authority.

    The compiler still resolves and verifies declared inputs and stages its
    deterministic intermediate artifacts in its private temporary directory.
    This deliberately narrower entry point cannot request materialization or
    overwrite an existing target.
    """

    result = compile_region_package_file(
        form_path,
        output_root=output_root,
        generated_root=generated_root,
        overwrite=False,
        dry_run=True,
    )
    if result.materialized:
        raise AssertionError(
            "Region-package probe unexpectedly materialized output"
        )
    return result


__all__ = [
    "COMPILER_VERSION",
    "CompiledRegionPackage",
    "READINESS_FILE_NAME",
    "READINESS_STATES",
    "RegionPackageCompilationError",
    "compile_region_package_file",
    "probe_region_package_file",
]
