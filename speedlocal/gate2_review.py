from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Mapping

from psycopg import sql
from shapely import wkb
from shapely.geometry import mapping

from .region_profile import DELIVERY_REGION_IDS, load_region_profile
from .source_catalog import (
    RegionSourceCatalog,
    SOURCE_CATALOG_GROUPS,
    load_delivery_source_selection,
    load_region_source_catalog,
    load_source_geometry,
)


GATE2_REVIEW_ENV = "SPEEDLOCAL_GATE2_REVIEW"
GATE2_REVIEW_VIEW = "gate2"


@dataclass(frozen=True)
class Gate2SourceReview:
    region_id: str
    region_name: str
    group_id: str
    source_id: str
    label: str
    database_schema: str
    database_view: str
    authority: str
    dataset: str
    snapshot_date: str | None
    license_name: str | None
    license_status: str
    public_display_status: str
    source_sha256: str
    source_feature_count: int
    asset_feature_count: int
    geometry_family: str
    data_representation: str
    selection: str
    geometry: Mapping[str, Any]


def gate2_review_enabled(*, query_view: str | None, environment_value: str | None) -> bool:
    return (
        str(query_view or "").strip().lower() == GATE2_REVIEW_VIEW
        and str(environment_value or "").strip() == "1"
    )


def _load_source_row(cursor: Any, *, schema: str, view: str) -> tuple[Any, ...]:
    cursor.execute(
        sql.SQL(
            """
            select region_id, group_id, source_id, label, authority,
                   dataset_name, snapshot_date, license_name, license_status,
                   public_display_status, source_sha256,
                   source_feature_count, asset_feature_count, geometry_family,
                   data_representation, selection_rule,
                   ST_SRID(geom), ST_AsBinary(geom)
            from {}.{}
            """
        ).format(sql.Identifier(schema), sql.Identifier(view))
    )
    rows = cursor.fetchall()
    if len(rows) != 1:
        raise ValueError(f"{schema}.{view} must expose exactly one source row")
    row = rows[0]
    if row[-2] != 4326:
        raise ValueError(f"{schema}.{view} must use EPSG:4326")
    return (*row[:-2], row[-1])


def load_gate2_source_catalogs(
    repo_root: Path,
    *,
    delivery_only: bool = False,
) -> tuple[RegionSourceCatalog, ...]:
    catalogs = tuple(
        load_region_source_catalog(repo_root, region_id)
        for region_id in DELIVERY_REGION_IDS
    )
    if not delivery_only:
        return catalogs
    return tuple(
        RegionSourceCatalog(
            region_id=catalog.region_id,
            manifest_path=catalog.manifest_path,
            manifest_sha256=catalog.manifest_sha256,
            groups=load_delivery_source_selection(repo_root, catalog.region_id).groups,
        )
        for catalog in catalogs
    )


def load_gate2_region_bounds(
    repo_root: Path,
    database_url: str,
    *,
    region_id: str,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Load a stable WGS84 review extent from the approved region boundary."""
    if not database_url.strip():
        raise ValueError("DATABASE_URL is required for Gate 2 source review")
    if region_id not in DELIVERY_REGION_IDS:
        raise ValueError(f"Region is outside the delivery: {region_id}")
    try:
        import psycopg
    except Exception as exc:
        raise RuntimeError(f"psycopg is unavailable: {exc}") from exc

    profile = load_region_profile(repo_root, region_id)
    with psycopg.connect(
        database_url,
        connect_timeout=5,
        options="-c default_transaction_read_only=on",
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("show transaction_read_only")
            read_only_row = cursor.fetchone()
            if read_only_row is None or str(read_only_row[0]).lower() != "on":
                raise ValueError("Gate 2 review database connection is not read-only")
            cursor.execute(
                sql.SQL(
                    """
                    select min(ST_SRID(geom)), max(ST_SRID(geom)),
                           ST_XMin(ST_Extent(geom)), ST_YMin(ST_Extent(geom)),
                           ST_XMax(ST_Extent(geom)), ST_YMax(ST_Extent(geom))
                    from {}.{}
                    """
                ).format(
                    sql.Identifier(profile.database_schema),
                    sql.Identifier(profile.boundary_view),
                )
            )
            row = cursor.fetchone()
    if row is None or len(row) != 6:
        raise ValueError(f"{region_id}: region boundary extent is unavailable")
    minimum_srid, maximum_srid, west, south, east, north = row
    if minimum_srid != 4326 or maximum_srid != 4326:
        raise ValueError(f"{region_id}: region boundary must use EPSG:4326")
    coordinates = tuple(float(value) for value in (west, south, east, north))
    if not all(math.isfinite(value) for value in coordinates):
        raise ValueError(f"{region_id}: region boundary extent is not finite")
    west_value, south_value, east_value, north_value = coordinates
    if west_value >= east_value or south_value >= north_value:
        raise ValueError(f"{region_id}: region boundary extent is invalid")
    return ((south_value, west_value), (north_value, east_value))


def load_gate2_source_reviews(
    repo_root: Path,
    database_url: str,
    *,
    region_id: str | None = None,
    group_id: str | None = None,
    delivery_only: bool = False,
) -> tuple[tuple[RegionSourceCatalog, ...], tuple[Gate2SourceReview, ...]]:
    if not database_url.strip():
        raise ValueError("DATABASE_URL is required for Gate 2 source review")
    try:
        import psycopg
    except Exception as exc:
        raise RuntimeError(f"psycopg is unavailable: {exc}") from exc

    if region_id is not None and region_id not in DELIVERY_REGION_IDS:
        raise ValueError(f"Region is outside the delivery: {region_id}")
    if group_id is not None and group_id not in SOURCE_CATALOG_GROUPS:
        raise ValueError(f"Group is outside the source contract: {group_id}")
    catalogs = load_gate2_source_catalogs(repo_root, delivery_only=delivery_only)
    if delivery_only:
        # A source selection must not bypass the sealed geography observations.
        # Full local-file checks belong to review/import, never production reads.
        from .gate1_review import load_gate1_region_reviews

        geography_reviews = load_gate1_region_reviews(repo_root, database_url)
        if any(review.gate_state != "localhost_approved" for review in geography_reviews):
            raise ValueError("All three approved geographies are required for delivery review")
    reviews: list[Gate2SourceReview] = []
    with psycopg.connect(
        database_url,
        connect_timeout=5,
        options="-c default_transaction_read_only=on",
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("show transaction_read_only")
            row = cursor.fetchone()
            if row is None or str(row[0]).lower() != "on":
                raise ValueError("Gate 2 review database connection is not read-only")
            for catalog in catalogs:
                profile = load_region_profile(repo_root, catalog.region_id)
                cursor.execute(
                    """
                    select gate_state from meta.region_delivery_gates
                    where region_id = %s and gate_id = 1
                    """,
                    (catalog.region_id,),
                )
                gate_row = cursor.fetchone()
                if gate_row is None or str(gate_row[0]) != "localhost_approved":
                    raise ValueError(
                        f"{catalog.region_id}: Gate 1 approval is required"
                    )
                if region_id is not None and catalog.region_id != region_id:
                    continue
                candidate_sources = tuple(
                    source
                    for group in catalog.groups
                    if group.status == "candidate"
                    and (group_id is None or group.id == group_id)
                    for source in group.sources
                )
                for source in candidate_sources:
                    source_row = _load_source_row(
                        cursor,
                        schema=profile.database_schema,
                        view=source.database_view,
                    )
                    expected = (
                        source.region_id,
                        source.group_id,
                        source.id,
                        source.label,
                        source.authority,
                        source.dataset,
                        source.snapshot_date,
                        source.license_name,
                        source.license_status,
                        source.public_display_status,
                        source.sha256,
                        source.source_feature_count,
                        source.expected_feature_count,
                        source.geometry_family,
                        source.data_representation,
                        source.selection,
                    )
                    observed = tuple(
                        value.isoformat() if index == 6 and value is not None else value
                        for index, value in enumerate(source_row[:-1])
                    )
                    if observed != expected:
                        raise ValueError(
                            f"{catalog.region_id}/{source.id}: database metadata drifted"
                        )
                    database_geometry = wkb.loads(bytes(source_row[-1]))
                    source_geometry, feature_count = load_source_geometry(source)
                    if feature_count != source.expected_feature_count:
                        raise ValueError(
                            f"{catalog.region_id}/{source.id}: feature count drifted"
                        )
                    if not database_geometry.equals(source_geometry):
                        raise ValueError(
                            f"{catalog.region_id}/{source.id}: database geometry drifted"
                        )
                    reviews.append(
                        Gate2SourceReview(
                            region_id=catalog.region_id,
                            region_name=profile.name,
                            group_id=source.group_id,
                            source_id=source.id,
                            label=source.label,
                            database_schema=profile.database_schema,
                            database_view=source.database_view,
                            authority=source.authority,
                            dataset=source.dataset,
                            snapshot_date=source.snapshot_date,
                            license_name=source.license_name,
                            license_status=source.license_status,
                            public_display_status=source.public_display_status,
                            source_sha256=source.sha256,
                            source_feature_count=source.source_feature_count,
                            asset_feature_count=source.expected_feature_count,
                            geometry_family=source.geometry_family,
                            data_representation=source.data_representation,
                            selection=source.selection,
                            geometry=mapping(database_geometry),
                        )
                    )
    return catalogs, tuple(reviews)
