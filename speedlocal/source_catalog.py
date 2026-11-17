from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from jsonschema import Draft202012Validator
from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPoint,
    MultiPolygon,
    Point,
    Polygon,
    shape,
)
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .paths import resolve_source_path
from .region_profile import DELIVERY_REGION_IDS, load_region_profile, profile_path


SOURCE_CATALOG_SCHEMA = (
    "schemas/speedlocal/1.0/region-source-catalog.schema.json"
)
SOURCE_CATALOG_GROUPS = (
    "roads",
    "population",
    "nature",
    "culture",
    "grid_infrastructure",
)


@dataclass(frozen=True)
class LocalReviewAuthorization:
    scope: str
    authorized_by: str
    authorized_on: str
    reason: str


def local_review_authorization(payload: object) -> LocalReviewAuthorization | None:
    """Validate an owner instruction without turning it into source permission."""
    if payload is None:
        return None
    keys = {"scope", "authorized_by", "authorized_on", "reason"}
    if (
        not isinstance(payload, Mapping) or set(payload) != keys
        or any(not isinstance(payload[key], str) or not payload[key].strip() for key in keys)
        or payload["scope"] != "local_review"
    ):
        raise ValueError("Source local-review authorization is incomplete or out of scope")
    if date.fromisoformat(payload["authorized_on"]).isoformat() != payload["authorized_on"]:
        raise ValueError("Source local-review authorization requires an ISO date")
    return LocalReviewAuthorization(**payload)


def validate_source_local_review_scope(repo_root: Path, region_id: str) -> None:
    """Require the existing non-public review gate, never a public product route."""
    from .access_policy import validate_review_access_dimensions

    region = _read_object(_repo_path(
        repo_root, f"regions/{region_id}/region.json", label="Local-review region",
    ))
    review = region.get("review_access") or {}
    behavior = region.get("behavior_reference") or {}
    landing = region.get("landing_card") or {}
    if (
        region.get("region_id") != region_id
        or not all(isinstance(value, Mapping) for value in (review, behavior, landing))
        or review.get("enabled") is not True
        or review.get("mode") != "review"
        or review.get("surface") != "shared_workspace"
        or review.get("requires_environment_allowlist") is not True
    ):
        raise ValueError("Source authorization requires a bounded local-review region")
    validate_review_access_dimensions(
        lifecycle=region.get("status"),
        trust_classification=region.get("data_status"),
        behavior_reference_status=behavior.get("status"),
        behavior_frozen_v2_parity=behavior.get("frozen_v2_parity"),
        landing_card_enabled=landing.get("enabled"),
        review_access_classification=review.get("access_classification"),
    )


def validate_source_display_access(
    public_display_status: object, authorization: object, *, repo_root: Path, region_id: str,
) -> None:
    """Validate display scope; licence truth is retained independently."""
    owner_instruction = local_review_authorization(authorization)
    if public_display_status == "eligible_for_delivery_review" and owner_instruction is None:
        return
    if public_display_status != "local_review_only" or owner_instruction is None:
        raise ValueError("Source is not eligible for the selected review scope")
    validate_source_local_review_scope(repo_root, region_id)


@dataclass(frozen=True)
class RegionSource:
    region_id: str
    group_id: str
    id: str
    label: str
    database_view: str
    authority: str
    dataset: str
    snapshot_date: str | None
    license_name: str | None
    license_url: str | None
    license_status: str
    public_display_status: str
    selection: str
    source_feature_count: int
    geometry_family: str
    data_representation: str
    provider: str
    path: str
    sha256: str
    source_crs: str
    expected_feature_count: int
    local_review_authorization: LocalReviewAuthorization | None = None

    @property
    def is_public_review_eligible(self) -> bool:
        return (
            self.license_status == "verified_local_delivery"
            and bool(self.license_name and self.license_url)
            and self.public_display_status == "eligible_for_delivery_review"
            and self.local_review_authorization is None
        )

    @property
    def is_selected_review_eligible(self) -> bool:
        # Region scope is checked separately against the current region manifest.
        return self.is_public_review_eligible or (
            self.public_display_status == "local_review_only"
            and self.local_review_authorization is not None
        )


def source_selection_evidence(source: RegionSource) -> dict[str, Any]:
    evidence = asdict(source)
    if source.local_review_authorization is None:
        # Preserve every existing regional selection digest without an override.
        evidence.pop("local_review_authorization")
    return evidence


@dataclass(frozen=True)
class RegionSourceGroup:
    id: str
    status: str
    reason: str | None
    sources: tuple[RegionSource, ...]


@dataclass(frozen=True)
class RegionSourceCatalog:
    region_id: str
    manifest_path: Path
    manifest_sha256: str
    groups: tuple[RegionSourceGroup, ...]

    def group(self, group_id: str) -> RegionSourceGroup:
        for group in self.groups:
            if group.id == group_id:
                return group
        raise KeyError(f"{self.region_id}: unknown source group {group_id!r}")


@dataclass(frozen=True)
class DeliverySourceSelection:
    """The profile-selected subset; catalog candidates remain separate evidence."""

    region_id: str
    profile_sha256: str
    selection_sha256: str
    groups: tuple[RegionSourceGroup, ...]

    @property
    def sources(self) -> tuple[RegionSource, ...]:
        return tuple(source for group in self.groups for source in group.sources)


def _read_object(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def _repo_path(repo_root: Path, relative_path: str, *, label: str) -> Path:
    root = repo_root.resolve()
    path = (root / relative_path).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError(f"{label} escapes the repository: {relative_path}")
    if not path.is_file():
        raise FileNotFoundError(f"{label} is missing: {path}")
    return path


def _validate_source_catalog_schema_uncached(
    region_id: str, payload: Mapping[str, Any], schema: Mapping[str, Any],
) -> None:
    errors = sorted(
        Draft202012Validator(schema).iter_errors(payload),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        detail = "; ".join(
            f"/{'/'.join(str(part) for part in error.absolute_path)}: "
            f"{error.message}"
            for error in errors
        )
        raise ValueError(f"{region_id}: invalid source catalog: {detail}")


def _source_catalog_schema_is_local(schema: Any, *, root: bool = True) -> bool:
    if isinstance(schema, dict):
        for key, value in schema.items():
            # Resource/dialect changes and dynamic resolution keep their existing
            # uncached behavior. A fragment under a nested $id is not root-local.
            if key in {"$dynamicRef", "$recursiveRef", "$dynamicAnchor", "$recursiveAnchor"}:
                return False
            if key in {"$id", "$schema"} and (not root or not isinstance(value, str)):
                return False
            if key == "$ref" and (not isinstance(value, str) or not value.startswith("#")):
                return False
            if not _source_catalog_schema_is_local(value, root=False):
                return False
    elif isinstance(schema, list):
        return all(_source_catalog_schema_is_local(value, root=False) for value in schema)
    return True


@lru_cache(maxsize=8)
def _source_catalog_schema_proof(
    region_id: str, payload_json: str, schema_json: str,
) -> None:
    # Only successful None returns are retained; raised errors are never cached.
    # Immutable strings isolate validation from every caller-owned mapping.
    _validate_source_catalog_schema_uncached(
        region_id, json.loads(payload_json), json.loads(schema_json),
    )


def _validate_source_catalog_schema(
    region_id: str, payload: Mapping[str, Any], schema: Mapping[str, Any],
) -> None:
    """Reuse only the pure schema question after the caller's fresh file reads."""
    try:
        reusable = _source_catalog_schema_is_local(schema)
        if reusable:
            # Keep insertion order for equal-path error ordering and the existing
            # JSON number behavior. ASCII keys bound the retained text size.
            payload_json = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
            schema_json = json.dumps(schema, ensure_ascii=True, separators=(",", ":"))
            reusable = len(payload_json) + len(schema_json) <= 128 * 1024
    except RecursionError:
        # Admission must not reject deeply nested unused metadata that the
        # original validator accepts. Its own errors remain outside this catch.
        reusable = False
    if not reusable:
        return _validate_source_catalog_schema_uncached(region_id, payload, schema)
    return _source_catalog_schema_proof(region_id, payload_json, schema_json)


def load_region_source_catalog(
    repo_root: Path,
    region_id: str,
) -> RegionSourceCatalog:
    if region_id not in DELIVERY_REGION_IDS:
        raise ValueError(f"Region is outside the delivery: {region_id}")
    region_path = _repo_path(
        repo_root,
        f"regions/{region_id}/region.json",
        label="Region manifest",
    )
    region_payload = _read_object(region_path)
    if str(region_payload.get("region_id") or "") != region_id:
        raise ValueError(f"Region manifest identity mismatch: {region_path}")
    manifest_relative = str(
        region_payload.get("source_catalog_manifest") or ""
    ).strip()
    expected_relative = f"regions/{region_id}/source-catalog.json"
    if manifest_relative != expected_relative:
        raise ValueError(
            f"{region_id}: source catalog must be {expected_relative!r}, got "
            f"{manifest_relative!r}"
        )
    manifest_path = _repo_path(
        repo_root,
        manifest_relative,
        label="Source catalog",
    )
    schema_path = _repo_path(
        repo_root,
        SOURCE_CATALOG_SCHEMA,
        label="Source catalog schema",
    )
    payload = _read_object(manifest_path)
    schema = _read_object(schema_path)
    _validate_source_catalog_schema(region_id, payload, schema)
    if str(payload["region_id"]) != region_id:
        raise ValueError(f"Source catalog identity mismatch: {manifest_path}")

    raw_groups = payload["groups"]
    observed_group_ids = tuple(str(group["id"]) for group in raw_groups)
    if observed_group_ids != SOURCE_CATALOG_GROUPS:
        raise ValueError(
            f"{region_id}: source groups must use the canonical order "
            f"{SOURCE_CATALOG_GROUPS!r}"
        )
    seen_source_ids: set[str] = set()
    seen_views: set[str] = set()
    groups: list[RegionSourceGroup] = []
    for raw_group in raw_groups:
        group_id = str(raw_group["id"])
        status = str(raw_group["status"])
        raw_sources = raw_group["sources"]
        if status == "candidate" and not raw_sources:
            raise ValueError(f"{region_id}/{group_id}: candidate group is empty")
        if status != "candidate" and raw_sources:
            raise ValueError(
                f"{region_id}/{group_id}: only candidate groups may declare sources"
            )
        sources: list[RegionSource] = []
        for raw_source in raw_sources:
            source_id = str(raw_source["id"])
            database_view = str(raw_source["database_view"])
            if source_id in seen_source_ids or database_view in seen_views:
                raise ValueError(
                    f"{region_id}: duplicate source id or database view: "
                    f"{source_id}/{database_view}"
                )
            if database_view != source_id:
                raise ValueError(
                    f"{region_id}/{source_id}: database view must equal source id"
                )
            seen_source_ids.add(source_id)
            seen_views.add(database_view)
            license_payload = raw_source["license"]
            asset = raw_source["asset"]
            sources.append(
                RegionSource(
                    region_id=region_id,
                    group_id=group_id,
                    id=source_id,
                    label=str(raw_source["label"]),
                    database_view=database_view,
                    authority=str(raw_source["authority"]),
                    dataset=str(raw_source["dataset"]),
                    snapshot_date=(
                        str(raw_source["snapshot_date"])
                        if raw_source["snapshot_date"] is not None
                        else None
                    ),
                    license_name=(
                        str(license_payload["name"])
                        if license_payload["name"] is not None
                        else None
                    ),
                    license_url=(
                        str(license_payload["url"])
                        if license_payload["url"] is not None
                        else None
                    ),
                    license_status=str(license_payload["status"]),
                    public_display_status=str(
                        raw_source["public_display_status"]
                    ),
                    selection=str(raw_source["selection"]),
                    source_feature_count=int(raw_source["source_feature_count"]),
                    geometry_family=str(raw_source["geometry_family"]),
                    data_representation=str(raw_source["data_representation"]),
                    provider=str(asset["provider"]),
                    path=str(asset["path"]),
                    sha256=str(asset["sha256"]),
                    source_crs=str(asset["source_crs"]),
                    expected_feature_count=int(asset["expected_feature_count"]),
                    local_review_authorization=local_review_authorization(
                        raw_source.get("local_review_authorization")
                    ),
                )
            )
        groups.append(
            RegionSourceGroup(
                id=group_id,
                status=status,
                reason=(
                    str(raw_group["reason"])
                    if raw_group["reason"] is not None
                    else None
                ),
                sources=tuple(sources),
            )
        )
    return RegionSourceCatalog(
        region_id=region_id,
        manifest_path=manifest_path,
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        groups=tuple(groups),
    )


def load_delivery_source_selection(
    repo_root: Path,
    region_id: str,
) -> DeliverySourceSelection:
    """Resolve all five selected groups, rejecting unknown or ineligible views.

    This validates configuration and metadata only. Live database observations,
    analytical policy and owner acceptance are separate delivery gates.
    """
    profile = load_region_profile(repo_root, region_id)
    catalog = load_region_source_catalog(repo_root, region_id)
    groups: list[RegionSourceGroup] = []
    seen_views: set[str] = set()
    for group_id in SOURCE_CATALOG_GROUPS:
        selected_views = profile.landscape_views[group_id]
        if not selected_views:
            raise ValueError(f"{region_id}/{group_id}: delivery selection is empty")
        inventory = catalog.group(group_id)
        if inventory.status != "candidate":
            raise ValueError(f"{region_id}/{group_id}: source inventory is unavailable")
        sources_by_view = {source.database_view: source for source in inventory.sources}
        selected: list[RegionSource] = []
        for view in selected_views:
            if view in seen_views:
                raise ValueError(f"{region_id}: duplicate delivery view {view!r}")
            seen_views.add(view)
            source = sources_by_view.get(view)
            if source is None:
                raise ValueError(
                    f"{region_id}/{group_id}: selected view {view!r} is not in this group"
                )
            if source.region_id != region_id or source.group_id != group_id:
                raise ValueError(f"{region_id}/{view}: source identity mismatch")
            if not source.is_selected_review_eligible:
                raise ValueError(f"{region_id}/{view}: source is not eligible for delivery")
            if source.local_review_authorization is not None:
                validate_source_local_review_scope(repo_root, region_id)
            selected.append(source)
        groups.append(
            RegionSourceGroup(
                id=group_id,
                status=inventory.status,
                reason=None,
                sources=tuple(selected),
            )
        )
    selection_payload = {
        "schema_version": "1.0",
        "region_id": region_id,
        "database_schema": profile.database_schema,
        "connection": profile.connection,
        "groups": [
            {"id": group.id, "sources": [source_selection_evidence(source) for source in group.sources]}
            for group in groups
        ],
    }
    return DeliverySourceSelection(
        region_id=region_id,
        profile_sha256=hashlib.sha256(profile_path(repo_root, region_id).read_bytes()).hexdigest(),
        selection_sha256=hashlib.sha256(
            json.dumps(selection_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        groups=tuple(groups),
    )


def load_source_geometry(source: RegionSource) -> tuple[BaseGeometry, int]:
    path = resolve_source_path(source.provider, source.path)
    if not path.is_file():
        raise FileNotFoundError(f"{source.region_id}/{source.id}: source is missing")
    observed_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed_sha256 != source.sha256:
        raise ValueError(
            f"{source.region_id}/{source.id}: source checksum drifted"
        )
    payload = _read_object(path)
    if payload.get("type") != "FeatureCollection":
        raise ValueError(
            f"{source.region_id}/{source.id}: source must be a FeatureCollection"
        )
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError(f"{source.region_id}/{source.id}: features are invalid")
    if len(features) != source.expected_feature_count:
        raise ValueError(
            f"{source.region_id}/{source.id}: expected "
            f"{source.expected_feature_count} features, got {len(features)}"
        )
    geometries: list[BaseGeometry] = []
    for index, feature in enumerate(features):
        if not isinstance(feature, Mapping) or not isinstance(
            feature.get("geometry"), Mapping
        ):
            raise ValueError(
                f"{source.region_id}/{source.id}: feature {index} has no geometry"
            )
        geometry = shape(feature["geometry"])
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError(
                f"{source.region_id}/{source.id}: feature {index} is empty or invalid"
            )
        accepted_types = {
            "line": {"LineString", "MultiLineString"},
            "point": {"Point", "MultiPoint"},
            "polygon": {"Polygon", "MultiPolygon"},
        }[source.geometry_family]
        if geometry.geom_type not in accepted_types:
            raise ValueError(
                f"{source.region_id}/{source.id}: feature {index} is "
                f"{geometry.geom_type}, expected {source.geometry_family} geometry"
            )
        geometries.append(geometry)
    merged = unary_union(geometries)
    if source.geometry_family == "line" and isinstance(merged, LineString):
        merged = MultiLineString([merged])
    elif source.geometry_family == "point" and isinstance(merged, Point):
        merged = MultiPoint([merged])
    elif source.geometry_family == "polygon" and isinstance(merged, Polygon):
        merged = MultiPolygon([merged])
    expected_merged_types = {
        "line": (MultiLineString,),
        "point": (MultiPoint,),
        "polygon": (MultiPolygon,),
    }[source.geometry_family]
    if not isinstance(merged, expected_merged_types) or merged.is_empty:
        raise ValueError(
            f"{source.region_id}/{source.id}: union is not a valid "
            f"multi-{source.geometry_family} geometry"
        )
    return merged, len(features)
