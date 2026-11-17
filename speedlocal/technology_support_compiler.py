from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Protocol

import h3

from .contracts import (
    AnalysisContract,
    analysis_contract,
    canonical_contract_evidence,
    region_geography_contract,
)
from .geography import build_positive_intersection_h3_domain, sha256_path
from .geometry import DirectDistanceGeometryLevel, build_direct_distance_artifact
from .paths import GENERATED_RUNTIME_ROOT_ENV
from .validation import (
    validate_contract,
    validate_layer,
    validate_region_geography_contract,
)


class ResolvedAsset(Protocol):
    provider: str
    provider_path: str
    format: str
    path: Path
    bytes: int
    sha256: str


@dataclass(frozen=True)
class TechnologySupportCompilation:
    geography_manifest: dict[str, Any]
    analysis_manifest: dict[str, Any]
    area_results: Mapping[str, Mapping[str, Any]]
    generated_paths: tuple[str, ...]
    evidence: Mapping[str, Any]


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _format_number(value: float) -> str:
    text = f"{float(value):.12f}".rstrip("0").rstrip(".")
    return text or "0"


def _rows_sha256(rows: Any) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(
            (
                f"{row.cell_id},{_format_number(row.distance_m)},"
                f"{'true' if row.intersects else 'false'}\n"
            ).encode("utf-8")
        )
    return digest.hexdigest()


def _h3_id_digest(values: list[str]) -> str:
    return hashlib.sha256(
        "".join(f"{value}\n" for value in sorted(values)).encode("utf-8")
    ).hexdigest()


def _context_evidence(
    asset: ResolvedAsset,
    declaration: Mapping[str, Any],
) -> dict[str, Any]:
    if asset.format != "geojson":
        raise NotImplementedError(
            "Den generella compileradaptern för teknikkontext stödjer ännu "
            f"inte format={asset.format}; deklarationen förblir låst."
        )
    try:
        payload = json.loads(asset.path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Teknikkontextens GeoJSON kan inte läsas: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("Teknikkontexten måste vara en GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Teknikkontexten måste innehålla minst en H3-feature")
    id_field = str(declaration["id_field"])
    resolution = int(declaration["resolution"])
    context_fields = tuple(str(value) for value in declaration["context_fields"])
    cell_ids: list[str] = []
    observed_cell_ids: list[str] = []
    observed_counts = {field: 0 for field in context_fields}
    for index, feature in enumerate(features):
        if not isinstance(feature, Mapping):
            raise ValueError(f"Teknikkontextfeature {index} är inte ett objekt")
        properties = feature.get("properties")
        if not isinstance(properties, Mapping):
            raise ValueError(f"Teknikkontextfeature {index} saknar properties")
        cell_id = str(properties.get(id_field) or "").strip()
        if not cell_id or not h3.is_valid_cell(cell_id):
            raise ValueError(f"Teknikkontextfeature {index} har ogiltigt H3-id")
        if h3.get_resolution(cell_id) != resolution:
            raise ValueError(
                f"Teknikkontextcell {cell_id!r} är inte R{resolution}"
            )
        cell_ids.append(cell_id)
        observed = False
        for field in context_fields:
            value = properties.get(field)
            available = value is not None and (
                not isinstance(value, str) or bool(value.strip())
            )
            if available:
                observed_counts[field] += 1
                observed = True
        if observed:
            observed_cell_ids.append(cell_id)
    if len(cell_ids) != len(set(cell_ids)):
        raise ValueError("Teknikkontexten innehåller duplicerade H3-id:n")
    empty_fields = [
        field for field, count in observed_counts.items() if count == 0
    ]
    if empty_fields:
        raise ValueError(
            "Teknikkontexten saknar observerade värden i deklarerade fält: "
            f"{empty_fields}"
        )
    return {
        "expected_cell_count": len(cell_ids),
        "cell_ids_sha256": _h3_id_digest(cell_ids),
        "context_fields": list(context_fields),
        "observed_counts": observed_counts,
        "observed_cell_count": len(observed_cell_ids),
        "unobserved_cell_count": len(cell_ids) - len(observed_cell_ids),
        "observed_cell_ids_sha256": _h3_id_digest(observed_cell_ids),
        # Kept only while compiling so coverage against the generated support
        # universe can be measured.  The raw ids are never written to the
        # readiness report; its generated counts and digests are sufficient.
        "_cell_ids": cell_ids,
        "_observed_cell_ids": observed_cell_ids,
    }


def _generated_surface_cell_ids(
    path: Path,
    *,
    resolution: int,
    expected_cell_count: int,
    expected_cell_ids_sha256: str,
) -> set[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Den genererade teknikytan kan inte läsas: {exc}") from exc
    features = payload.get("features") if isinstance(payload, Mapping) else None
    if not isinstance(features, list):
        raise ValueError("Den genererade teknikytan saknar GeoJSON-features")
    cell_ids: list[str] = []
    for index, feature in enumerate(features):
        properties = feature.get("properties") if isinstance(feature, Mapping) else None
        cell_id = (
            str(properties.get("hex_id") or "").strip()
            if isinstance(properties, Mapping)
            else ""
        )
        if not cell_id or not h3.is_valid_cell(cell_id):
            raise ValueError(
                f"Den genererade teknikytans feature {index} har ogiltigt H3-id"
            )
        if h3.get_resolution(cell_id) != resolution:
            raise ValueError(
                f"Den genererade teknikytans cell {cell_id!r} är inte R{resolution}"
            )
        cell_ids.append(cell_id)
    if len(cell_ids) != len(set(cell_ids)):
        raise ValueError("Den genererade teknikytan innehåller duplicerade H3-id:n")
    if len(cell_ids) != expected_cell_count:
        raise ValueError("Den genererade teknikytans cellantal har driftat")
    if _h3_id_digest(cell_ids) != expected_cell_ids_sha256:
        raise ValueError("Den genererade teknikytans H3-id-digest har driftat")
    return set(cell_ids)


def _source_metadata(provenance: Mapping[str, Any], sha256: str) -> dict[str, Any]:
    value = {
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
                "role": "declared_technology_target_surface",
                "checksum_status": "pinned",
                "sha256": sha256,
            }
        ],
    }
    if provenance.get("license_url"):
        value["license_url"] = provenance["license_url"]
    return value


def _executable_analysis(
    manifest: Mapping[str, Any],
    *,
    analysis_id: str,
    area_result: Mapping[str, Any] | None,
    eligible_surface: Mapping[str, Any] | None,
) -> AnalysisContract:
    raw = dict(manifest)
    raw.pop("analysis_domain_reference", None)
    raw["analysis_id"] = analysis_id
    if area_result is not None:
        raw["area_result"] = dict(area_result)
    if eligible_surface is not None:
        raw["eligible_surfaces"] = {
            str(eligible_surface["id"]): dict(eligible_surface["contract"])
        }
    contract = analysis_contract(raw)
    validate_contract(contract)
    return contract


def _analysis_bindings(
    contracts: tuple[AnalysisContract, ...],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for contract in contracts:
        area_result = contract.area_result
        if area_result is None:
            raise ValueError("Teknikanalysen saknar area_result")
        surface = contract.eligible_surfaces[area_result.eligible_surface_id]
        area_semantics = asdict(area_result)
        area_semantics.pop("technology", None)
        surface_evidence = asdict(surface)
        surface_evidence.pop("support_observations", None)
        technology_context = surface_evidence.get("technology_context")
        if isinstance(technology_context, dict):
            # The context consumer signs this declaration independently; it
            # does not alter distance/intersection observation rows.
            technology_context.pop("context_fields", None)
        ordered_layers = [
            contract.layers[layer_id] for layer_id in sorted(contract.layers)
        ]
        result.append(
            {
                "analysis_id": contract.id,
                "technology": area_result.technology,
                "eligible_surface_id": area_result.eligible_surface_id,
                "group_ids": list(contract.groups),
                "layer_ids": [layer.id for layer in ordered_layers],
                "area_result_semantics_sha256": _canonical_sha256(area_semantics),
                "eligible_surface_contract_sha256": _canonical_sha256(
                    surface_evidence
                ),
                "layer_contracts_sha256": _canonical_sha256(
                    [canonical_contract_evidence(layer) for layer in ordered_layers]
                ),
                "source_contracts_sha256": _canonical_sha256(
                    [
                        canonical_contract_evidence(layer.source)
                        for layer in ordered_layers
                    ]
                ),
            }
        )
    return result


def _area_result(
    technology_id: str,
    declaration: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "technology": technology_id,
        "applicable_group_ids": list(declaration["applicable_group_ids"]),
        "restriction_combination": declaration["area_result"][
            "restriction_combination"
        ],
        "operation_order": declaration["area_result"]["operation_order"],
        "denominator": declaration["area_result"]["denominator"],
        "geometry_semantics": declaration["area_result"][
            "geometry_semantics"
        ],
        "eligible_surface_id": declaration["area_result"][
            "eligible_surface_id"
        ],
    }


def materialize_technology_support(
    form: Mapping[str, Any],
    *,
    geography_manifest: Mapping[str, Any],
    analysis_manifest: Mapping[str, Any],
    coverage_asset: ResolvedAsset,
    context_asset: ResolvedAsset,
    generated_root: Path,
) -> TechnologySupportCompilation:
    support = form["geography"]["technology_support"]
    if support["state"] != "declared":
        raise ValueError("Teknikstödsdomänen är inte deklarerad")
    context_declaration = support["technology_context"]
    if context_declaration["state"] != "declared":
        raise NotImplementedError(
            "Teknikkontexten är unavailable; area- och contextkontrakten "
            "materialiseras inte förrän en verklig H3-källa deklareras."
        )
    if coverage_asset.format not in {"geojson", "gpkg"}:
        raise NotImplementedError(
            "Den generella compileradaptern för teknikmålyta stödjer ännu "
            f"inte format={coverage_asset.format}."
        )
    context_evidence = _context_evidence(context_asset, context_declaration)
    region = form["region"]
    region_id = str(region["region_id"])
    source_resolution = int(form["map_h3"]["analysis_resolution"])
    rollups = tuple(int(value) for value in form["map_h3"]["rollup_resolutions"])
    support_domain_id = str(support["support_domain_id"])
    coverage = support["coverage_geometry"]
    surface_declaration = support["eligible_surface"]
    surface_id = str(surface_declaration["id"])
    level_paths = {
        resolution: (
            f"data/generated/eligible_surface/{region_id}_{surface_id}_r"
            f"{resolution}.geojson"
        )
        for resolution in (source_resolution, *rollups)
    }
    surface_metadata_path = (
        f"data/generated/eligible_surface/{region_id}_{surface_id}_metadata.json"
    )
    generated_surface = build_positive_intersection_h3_domain(
        boundary_path=coverage_asset.path,
        boundary_sha256=coverage_asset.sha256,
        boundary_provider=coverage_asset.provider,
        boundary_reference=coverage_asset.provider_path,
        source_crs_value=str(coverage["source_crs"]),
        native_crs_value=str(region["native_crs"]),
        generated_root=generated_root,
        level_paths=level_paths,
        metadata_path=surface_metadata_path,
        domain_id=support_domain_id,
        domain_scope="technology_support",
        coverage_geometry_id=str(coverage["id"]),
        source_resolution=source_resolution,
        rollup_resolutions=rollups,
        candidate_buffer_m=float(support["candidate_buffer_m"]),
        status="candidate",
    )
    levels = {
        int(item["resolution"]): item for item in generated_surface["levels"]
    }
    source_level = levels[source_resolution]
    context_count = int(context_evidence["expected_cell_count"])
    if context_count < int(source_level["cell_count"]):
        raise ValueError(
            "Teknikkontexten deklarerar färre H3-celler än den genererade "
            "teknikstödsdomänen"
        )

    geography_value = json.loads(json.dumps(geography_manifest))
    geography_value["geographies"][coverage["id"]] = {
        "label": coverage["label"],
        "role": "technology_target_surface",
        "provider": coverage_asset.provider,
        "path": coverage_asset.provider_path,
        "sha256": coverage_asset.sha256,
        "format": coverage_asset.format,
        "geometry_family": "polygon",
        "source_crs": coverage["source_crs"],
        "native_crs": coverage["native_crs"],
        "water_policy": form["technologies"][support["technologies"][0]][
            "area_result"
        ]["water_policy"],
        "source_metadata": _source_metadata(
            coverage["provenance"], coverage_asset.sha256
        ),
    }
    geography_value["technology_support_domains"][support_domain_id] = {
        "label": support["label"],
        "status": "candidate",
        "technologies": list(support["technologies"]),
        "coverage_geometry_id": coverage["id"],
        "coverage_rule": "positive_area_intersection",
        "cell_kind": "h3",
        "source_resolution": source_resolution,
        "native_crs": region["native_crs"],
        "empty_intersection_policy": "exclude",
        "missing_observation_policy": "error",
        "rollup_strategy": "derive_from_source_children",
        "rollup_resolutions": list(rollups),
    }
    geography_contract = region_geography_contract(geography_value)
    validate_region_geography_contract(geography_contract)
    support_domain = geography_contract.technology_support_domains[
        support_domain_id
    ]

    analysis_value = json.loads(json.dumps(analysis_manifest))
    standard_domain = next(iter(geography_value["analysis_domains"].values()))
    analysis_value.pop("analysis_domain_reference", None)
    analysis_value["analysis_domain"] = standard_domain["artifacts"]
    base_contract = _executable_analysis(
        analysis_value,
        analysis_id="standard_constraints",
        area_result=None,
        eligible_surface=None,
    )
    surface_path = generated_root.joinpath(*Path(level_paths[source_resolution]).parts)
    surface_sha256 = str(source_level["sha256"])
    surface_cell_ids_sha256 = str(source_level["cell_ids_sha256"])
    surface_cell_ids = _generated_surface_cell_ids(
        surface_path,
        resolution=source_resolution,
        expected_cell_count=int(source_level["cell_count"]),
        expected_cell_ids_sha256=surface_cell_ids_sha256,
    )
    context_cell_ids = set(context_evidence.pop("_cell_ids"))
    observed_context_cell_ids = set(
        context_evidence.pop("_observed_cell_ids")
    )
    assessed_support_ids = surface_cell_ids.intersection(
        observed_context_cell_ids
    )
    if not assessed_support_ids:
        raise ValueError(
            "Teknikkontexten överlappar inte den genererade teknikstödsdomänen"
        )
    missing_support_ids = surface_cell_ids.difference(
        observed_context_cell_ids
    )
    outside_support_ids = context_cell_ids.difference(surface_cell_ids)
    context_evidence["support_domain_coverage"] = {
        "support_cell_count": len(surface_cell_ids),
        "assessed_support_cell_count": len(assessed_support_ids),
        "not_assessed_support_cell_count": len(missing_support_ids),
        "outside_support_context_cell_count": len(outside_support_ids),
        "assessed_support_cell_ids_sha256": _h3_id_digest(
            list(assessed_support_ids)
        ),
        "not_assessed_support_cell_ids_sha256": _h3_id_digest(
            list(missing_support_ids)
        ),
        "support_coverage_fraction": (
            len(assessed_support_ids) / len(surface_cell_ids)
        ),
        "missing_policy": context_declaration["missing_policy"],
    }
    domain_level = DirectDistanceGeometryLevel(
        domain_id=support_domain_id,
        path=surface_path,
        sha256=surface_sha256,
        id_field="hex_id",
        cell_kind="h3",
        resolution=source_resolution,
        expected_cell_count=int(source_level["cell_count"]),
        required_properties=(
            ("domain_id", support_domain_id),
            ("domain_scope", "technology_support"),
            ("coverage_geometry_id", str(coverage["id"])),
        ),
    )
    observation_root = (
        f"data/generated/support_observations/{region_id}_{surface_id}_r"
        f"{source_resolution}"
    )
    layer_rows: list[dict[str, Any]] = []
    support_layers: list[dict[str, Any]] = []
    generated_paths = [
        surface_metadata_path,
        *(level_paths[resolution] for resolution in (source_resolution, *rollups)),
    ]
    previous_generated_root = os.environ.get(GENERATED_RUNTIME_ROOT_ENV)
    os.environ[GENERATED_RUNTIME_ROOT_ENV] = str(generated_root)
    try:
        group_order = {
            group_id: index for index, group_id in enumerate(base_contract.groups)
        }
        layers = sorted(
            base_contract.layers.values(),
            key=lambda layer: (group_order[layer.group_id], layer.id),
        )
        for layer in layers:
            validated = validate_layer(layer)
            artifact = build_direct_distance_artifact(
                layer,
                analysis_domain=domain_level,
                native_crs=str(region["native_crs"]),
            )
            if len(artifact.rows) != int(source_level["cell_count"]):
                raise ValueError(
                    f"Supportobservationerna för {layer.id!r} täcker inte "
                    "hela teknikstödsdomänen"
                )
            row_ids = [row.cell_id for row in artifact.rows]
            if _h3_id_digest(row_ids) != surface_cell_ids_sha256:
                raise ValueError(
                    f"Supportobservationerna för {layer.id!r} har fel H3-universum"
                )
            relative_path = f"{observation_root}/{layer.id}.csv"
            target = generated_root.joinpath(*Path(relative_path).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(("hex_id", "distance_m", "intersects"))
                for row in artifact.rows:
                    writer.writerow(
                        (
                            row.cell_id,
                            _format_number(row.distance_m),
                            "true" if row.intersects else "false",
                        )
                    )
            item = {
                "layer_id": layer.id,
                "group_id": layer.group_id,
                "resolution": source_resolution,
                "row_count": len(artifact.rows),
                "cell_ids_sha256": surface_cell_ids_sha256,
                "missing_cell_count": 0,
                "unexpected_cell_count": 0,
                "intersecting_cell_count": sum(
                    int(row.intersects) for row in artifact.rows
                ),
                "source_geometry_count": artifact.source_geometry_count,
                "source_part_count": artifact.source_part_count,
                "declared_feature_count": artifact.declared_feature_count,
                "source_geometry_bytes": validated.assets.geojson_path.stat().st_size,
                "source_geometry_sha256": sha256_path(
                    validated.assets.geojson_path
                ),
                "path": Path(relative_path).name,
                "bytes": target.stat().st_size,
                "sha256": sha256_path(target),
                "rows_sha256": _rows_sha256(artifact.rows),
            }
            layer_rows.append(item)
            support_layers.append(
                {
                    "layer_id": layer.id,
                    "provider": "generated_runtime",
                    "path": relative_path,
                    "sha256": item["sha256"],
                    "rows_sha256": item["rows_sha256"],
                }
            )
            generated_paths.append(relative_path)
    finally:
        if previous_generated_root is None:
            os.environ.pop(GENERATED_RUNTIME_ROOT_ENV, None)
        else:
            os.environ[GENERATED_RUNTIME_ROOT_ENV] = previous_generated_root

    declared_areas = {
        technology_id: _area_result(technology_id, form["technologies"][technology_id])
        for technology_id in support["technologies"]
    }
    policy_source = form["technologies"][support["technologies"][0]][
        "area_result"
    ]
    placeholder_observations = {
        "provider": "generated_runtime",
        "path": f"{observation_root}/support_domain_observations.json",
        "sha256": "0" * 64,
        "resolution": source_resolution,
        "expected_cell_count": int(source_level["cell_count"]),
        "cell_ids_sha256": surface_cell_ids_sha256,
        "missing_policy": "error",
        "layers": support_layers,
    }
    surface_contract = {
        "label": surface_declaration["label"],
        "support_domain_id": support_domain_id,
        "technologies": list(support["technologies"]),
        "surface_scope": policy_source["surface_scope"],
        "water_policy": policy_source["water_policy"],
        "outside_region_policy": surface_declaration["outside_region_policy"],
        "geometry_operation": surface_declaration["geometry_operation"],
        "source": {
            "provider": coverage_asset.provider,
            "path": coverage_asset.provider_path,
            "sha256": coverage_asset.sha256,
            "geometry_family": "polygon",
            "coverage_geometry_id": coverage["id"],
            "derivation": surface_declaration["source_derivation"],
        },
        "provider": "generated_runtime",
        "path": level_paths[source_resolution],
        "sha256": surface_sha256,
        "id_field": "hex_id",
        "area_field": "area_km2",
        "area_unit": "km2",
        "cell_kind": "h3",
        "resolution": source_resolution,
        "expected_cell_count": int(source_level["cell_count"]),
        "expected_total_area_km2": float(source_level["total_area_km2"]),
        "technology_context": {
            "id": context_declaration["id"],
            "provider": context_asset.provider,
            "path": context_asset.provider_path,
            "sha256": context_asset.sha256,
            "id_field": context_declaration["id_field"],
            "cell_kind": context_declaration["cell_kind"],
            "resolution": context_declaration["resolution"],
            "expected_cell_count": context_evidence["expected_cell_count"],
            "cell_ids_sha256": context_evidence["cell_ids_sha256"],
            "context_fields": list(context_evidence["context_fields"]),
            "missing_policy": context_declaration["missing_policy"],
        },
        "support_observations": placeholder_observations,
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
                "expected_total_area_km2": float(
                    levels[resolution]["total_area_km2"]
                ),
            }
            for resolution in rollups
        ],
    }
    surface_wrapper = {"id": surface_id, "contract": surface_contract}
    contracts = tuple(
        _executable_analysis(
            analysis_value,
            analysis_id=technology_id,
            area_result=declared_areas[technology_id],
            eligible_surface=surface_wrapper,
        )
        for technology_id in support["technologies"]
    )
    analysis_bindings = _analysis_bindings(contracts)
    support_domain_contract_sha256 = _canonical_sha256(asdict(support_domain))
    surface_metadata_file = generated_root.joinpath(
        *Path(surface_metadata_path).parts
    )
    surface_metadata_sha256 = sha256_path(surface_metadata_file)
    build_inputs = {
        "region_id": region_id,
        "support_domain_id": support_domain_id,
        "technologies": list(support_domain.technologies),
        "analysis_bindings": analysis_bindings,
        "support_domain_contract_sha256": support_domain_contract_sha256,
        "native_crs": support_domain.native_crs,
        "coverage_rule": support_domain.coverage_rule,
        "resolution": source_resolution,
        "cell_count": int(source_level["cell_count"]),
        "cell_ids_sha256": surface_cell_ids_sha256,
        "surface_geojson_sha256": surface_sha256,
        "surface_metadata_sha256": surface_metadata_sha256,
        "sources": [
            {
                "layer_id": item["layer_id"],
                "source_geometry_sha256": item["source_geometry_sha256"],
            }
            for item in layer_rows
        ],
    }
    artifact_signature = [
        {
            "layer_id": item["layer_id"],
            "sha256": item["sha256"],
            "rows_sha256": item["rows_sha256"],
        }
        for item in layer_rows
    ]
    metadata = {
        "schema_version": "2.0",
        "region_id": region_id,
        "support_domain_id": support_domain_id,
        "technologies": list(support_domain.technologies),
        "analysis_bindings": analysis_bindings,
        "support_domain_contract_sha256": support_domain_contract_sha256,
        "groups": list(base_contract.groups),
        "layer_ids": [item["layer_id"] for item in layer_rows],
        "native_crs": support_domain.native_crs,
        "distance_semantics": "support_surface_representative_point_to_source",
        "intersection_semantics": "support_surface_geometry_intersects_source",
        "support_surface": {
            "path": Path(level_paths[source_resolution]).name,
            "metadata_path": Path(surface_metadata_path).name,
            "resolution": source_resolution,
            "cell_count": int(source_level["cell_count"]),
            "cell_ids_sha256": surface_cell_ids_sha256,
            "bytes": surface_path.stat().st_size,
            "sha256": surface_sha256,
            "metadata_bytes": surface_metadata_file.stat().st_size,
            "metadata_sha256": surface_metadata_sha256,
        },
        "coverage_evidence": {
            "mode": "complete",
            "missing_observation_policy": "error",
            "expected_layer_count": len(layer_rows),
            "complete_layer_count": len(layer_rows),
            "expected_rows_per_layer": int(source_level["cell_count"]),
            "missing_cell_count": 0,
            "unexpected_cell_count": 0,
            "all_layers_complete": True,
        },
        "build_input_signature_sha256": _canonical_sha256(build_inputs),
        "artifact_set_signature_sha256": _canonical_sha256(artifact_signature),
        "layers": layer_rows,
    }
    metadata_path = generated_root.joinpath(
        *Path(placeholder_observations["path"]).parts
    )
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    placeholder_observations["sha256"] = sha256_path(metadata_path)
    generated_paths.append(str(placeholder_observations["path"]))
    analysis_value["eligible_surfaces"] = {surface_id: surface_contract}
    final_contracts = tuple(
        _executable_analysis(
            analysis_value,
            analysis_id=technology_id,
            area_result=declared_areas[technology_id],
            eligible_surface={"id": surface_id, "contract": surface_contract},
        )
        for technology_id in support["technologies"]
    )
    if _analysis_bindings(final_contracts) != analysis_bindings:
        raise ValueError("Supportobservationsmetadata skapade en kontraktdrift")
    analysis_output = json.loads(json.dumps(analysis_manifest))
    analysis_output["eligible_surfaces"] = {surface_id: surface_contract}
    return TechnologySupportCompilation(
        geography_manifest=geography_value,
        analysis_manifest=analysis_output,
        area_results=declared_areas,
        generated_paths=tuple(sorted(set(generated_paths))),
        evidence={
            "support_domain_id": support_domain_id,
            "eligible_surface_id": surface_id,
            "resolution": source_resolution,
            "cell_count": int(source_level["cell_count"]),
            "cell_ids_sha256": surface_cell_ids_sha256,
            "total_area_km2": float(source_level["total_area_km2"]),
            "technology_context": context_evidence,
            "support_observation_layer_count": len(layer_rows),
            "support_observation_rows_per_layer": int(
                source_level["cell_count"]
            ),
            "support_observation_metadata_sha256": (
                placeholder_observations["sha256"]
            ),
        },
    )


__all__ = [
    "TechnologySupportCompilation",
    "materialize_technology_support",
]
