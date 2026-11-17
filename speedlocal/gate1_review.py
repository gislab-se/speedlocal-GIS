from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from psycopg import sql

from .catalogs import load_region_geography
from .gate1_geography import (
    AREA_BINDING_TOLERANCE_M2,
    fingerprint_gate1_wkb,
    gate1_binding_evidence,
    select_gate1_geography_binding,
)
from .gate1_geography_scope import (
    Gate1GeographyScopeBinding,
    assert_gate1_geography_scope,
)
from .region_profile import (
    DELIVERY_REGION_IDS,
    load_region_profile,
    profile_path,
    profile_schema_path,
    validate_profile_payload,
)


GATE1_REVIEW_ENV = "SPEEDLOCAL_GATE1_REVIEW"
GATE1_REVIEW_GATE_VALUE = "1"
GATE1_REVIEW_VIEW = "gate1"
GATE1_EVIDENCE_DIGEST_KEY = "evidence_sha256"
_GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Gate1RegionReview:
    region_id: str
    name: str
    country_code: str
    native_crs: str
    database_schema: str
    boundary_view: str
    analysis_surface_view: str
    gate_state: str
    review_commit: str
    automated_evidence_sha256: str
    owner_reviewed_at: datetime | None
    owner_review_note: str | None
    profile_sha256: str
    geography_sha256: str
    boundary_sha256: str
    boundary_label: str
    boundary_role: str
    boundary_area_km2: float
    boundary_geometry_sha256: str
    boundary_geometry: Mapping[str, Any]
    analysis_surface_sha256: str
    analysis_surface_label: str
    analysis_surface_role: str
    analysis_surface_water_policy: str | None
    analysis_surface_area_km2: float
    analysis_surface_geometry_sha256: str
    analysis_surface_geometry: Mapping[str, Any]
    identity_binding_status: str
    analysis_surface_binding_status: str
    identity_analysis_same_source: bool
    identity_analysis_source_relation: str
    identity_analysis_same_geometry: bool
    observed_outside_identity_m2: float
    observed_excluded_area_m2: float
    observed_symmetric_difference_m2: float
    current_profile_sha256: str = ""
    landscape_selection_changed: bool = False
    current_geography_sha256: str = ""
    technology_support_added: bool = False


@dataclass(frozen=True)
class Gate1ProfileBinding:
    """Keep reviewed profile provenance separate from later landscape selection."""

    reviewed_profile_sha256: str
    current_profile_sha256: str
    landscape_selection_changed: bool


@dataclass(frozen=True)
class _LiveReviewGeography:
    geography_id: str
    geography_role: str
    water_policy: str | None
    label: str
    source_sha256: str
    area_km2: float
    database_area_km2: float
    geometry_sha256: str
    geometry_type: str
    geometry: Mapping[str, Any]


def gate1_review_enabled(*, query_view: str | None, environment_value: str | None) -> bool:
    return (
        str(query_view or "").strip().lower() == GATE1_REVIEW_VIEW
        and str(environment_value or "").strip() == GATE1_REVIEW_GATE_VALUE
    )


def validate_delivery_gate_states(region_id: str, states: Mapping[int, str]) -> None:
    """Accept later delivery progress only after each predecessor is approved."""

    allowed_states = {"incomplete", "automatically_validated", "localhost_approved"}
    if (
        set(states) != set(range(1, 8))
        or any(type(gate_id) is not int for gate_id in states)
        or any(state not in allowed_states for state in states.values())
    ):
        raise ValueError(f"{region_id}: delivery-gate states are invalid")
    for gate_id in range(2, 8):
        if (
            states[gate_id] != "incomplete"
            and states[gate_id - 1] != "localhost_approved"
        ):
            raise ValueError(
                f"{region_id}: Gate {gate_id} requires an approved Gate {gate_id - 1}"
            )


def gate1_review_commit(repo_root: Path) -> str:
    """Return the exact repository commit that a Gate 1 review can approve."""

    completed = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    commit = completed.stdout.strip().lower()
    if completed.returncode != 0 or _GIT_COMMIT_PATTERN.fullmatch(commit) is None:
        raise ValueError("Gate 1 review commit could not be resolved")
    return commit


def gate1_evidence_sha256(evidence: Mapping[str, Any]) -> str:
    """Fingerprint an automated-evidence payload, excluding its own seal."""

    payload = dict(evidence)
    payload.pop(GATE1_EVIDENCE_DIGEST_KEY, None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def gate1_evidence_contract_sha256(evidence: Mapping[str, Any]) -> str:
    """Fingerprint only the Gate 1 inputs and observations under review.

    The review commit and evidence seal are provenance metadata. Excluding
    them lets a later validation prove that the reviewed Gate 1 contract is
    unchanged without moving the original owner approval to a new commit.
    """

    payload = dict(evidence)
    payload.pop("review_commit", None)
    payload.pop(GATE1_EVIDENCE_DIGEST_KEY, None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _git_commit_is_ancestor(
    repo_root: Path,
    *,
    ancestor: str,
    descendant: str,
) -> bool:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "merge-base",
            "--is-ancestor",
            ancestor,
            descendant,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.returncode == 0


def seal_gate1_automated_evidence(
    evidence: Mapping[str, Any],
    *,
    review_commit: str,
) -> dict[str, Any]:
    """Bind deterministic Gate 1 evidence to one exact review commit."""

    normalized_commit = str(review_commit).strip().lower()
    if _GIT_COMMIT_PATTERN.fullmatch(normalized_commit) is None:
        raise ValueError("Gate 1 automated evidence needs a full Git commit")
    sealed = dict(evidence)
    sealed["review_commit"] = normalized_commit
    sealed.pop(GATE1_EVIDENCE_DIGEST_KEY, None)
    sealed[GATE1_EVIDENCE_DIGEST_KEY] = gate1_evidence_sha256(sealed)
    return sealed


def assert_gate1_approval_binding(
    *,
    region_id: str,
    gate_state: str,
    automated_evidence: Mapping[str, Any],
    expected_review_commit: str,
    owner_reviewed_at: Any,
    owner_review_note: Any,
    repo_root: Path | None = None,
) -> tuple[str, str]:
    """Fail closed unless state, evidence, provenance and owner fields agree."""

    review_commit = str(automated_evidence.get("review_commit") or "").strip().lower()
    current_commit = str(expected_review_commit or "").strip().lower()
    if _GIT_COMMIT_PATTERN.fullmatch(review_commit) is None:
        raise ValueError(
            f"{region_id}: Gate 1 automated evidence has no valid review commit"
        )
    if _GIT_COMMIT_PATTERN.fullmatch(current_commit) is None:
        raise ValueError(f"{region_id}: current repository commit is invalid")
    if review_commit != current_commit:
        if repo_root is None:
            raise ValueError(
                f"{region_id}: Gate 1 review commit ancestry cannot be verified"
            )
        if not _git_commit_is_ancestor(
            repo_root,
            ancestor=review_commit,
            descendant=current_commit,
        ):
            raise ValueError(
                f"{region_id}: Gate 1 review commit is not an ancestor of "
                "the current repository commit"
            )
    recorded_digest = str(
        automated_evidence.get(GATE1_EVIDENCE_DIGEST_KEY) or ""
    ).strip().lower()
    expected_digest = gate1_evidence_sha256(automated_evidence)
    if recorded_digest != expected_digest:
        raise ValueError(
            f"{region_id}: Gate 1 automated evidence seal is invalid"
        )

    note = str(owner_review_note or "").strip()
    if gate_state == "localhost_approved":
        if (
            not isinstance(owner_reviewed_at, datetime)
            or owner_reviewed_at.tzinfo is None
            or owner_reviewed_at.utcoffset() is None
        ):
            raise ValueError(
                f"{region_id}: localhost approval has no real owner_reviewed_at"
            )
        if not note:
            raise ValueError(
                f"{region_id}: localhost approval has no owner_review_note"
            )
    elif gate_state == "automatically_validated":
        if owner_reviewed_at is not None or owner_review_note is not None:
            raise ValueError(
                f"{region_id}: automatically validated Gate 1 retains stale "
                "owner approval fields"
            )
    else:
        raise ValueError(f"{region_id}: unsupported Gate 1 state {gate_state!r}")
    return review_commit, recorded_digest


def assert_gate1_profile_binding(
    repo_root: Path,
    region_id: str,
    *,
    review_commit: str,
    reviewed_profile_sha256: str,
    current_profile_bytes: bytes | None = None,
) -> Gate1ProfileBinding:
    """Verify the original Git bytes and permit only later landscape selection.

    Call after ``assert_gate1_approval_binding`` has verified the evidence seal,
    review-commit ancestry and owner fields. The original profile digest stays
    immutable evidence; current landscape values acquire no Gate 1 approval.
    """

    current_path = profile_path(repo_root, region_id)
    if _GIT_COMMIT_PATTERN.fullmatch(review_commit) is None:
        raise ValueError(f"{region_id}: reviewed profile commit is invalid")
    if re.fullmatch(r"[0-9a-f]{64}", reviewed_profile_sha256) is None:
        raise ValueError(f"{region_id}: reviewed profile digest is invalid")
    completed = subprocess.run(
        [
            "git", "-C", str(repo_root), "show",
            f"{review_commit}:regions/{region_id}/region-profile.json",
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise ValueError(f"{region_id}: original reviewed profile is unavailable in Git")
    reviewed_bytes = completed.stdout
    if hashlib.sha256(reviewed_bytes).hexdigest() != reviewed_profile_sha256:
        raise ValueError(
            f"{region_id}: original Git profile does not match its sealed digest"
        )
    current_bytes = (
        current_path.read_bytes()
        if current_profile_bytes is None
        else current_profile_bytes
    )

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"{region_id}: duplicate profile field {key!r}")
            result[key] = value
        return result

    try:
        reviewed = json.loads(reviewed_bytes, object_pairs_hook=unique_object)
        current = json.loads(current_bytes, object_pairs_hook=unique_object)
        schema = json.loads(profile_schema_path(repo_root).read_text(encoding="utf-8"))
        validate_profile_payload(reviewed, schema=schema)
        validate_profile_payload(current, schema=schema)
    except (UnicodeError, TypeError, ValueError) as exc:
        raise ValueError(f"{region_id}: invalid Gate 1 profile binding: {exc}") from exc
    if reviewed["region"]["id"] != region_id:
        raise ValueError(f"{region_id}: original reviewed profile region is invalid")
    if {key: value for key, value in reviewed.items() if key != "landscape"} != {
        key: value for key, value in current.items() if key != "landscape"
    }:
        raise ValueError(
            f"{region_id}: profile changed outside the later landscape selection"
        )
    return Gate1ProfileBinding(
        reviewed_profile_sha256=reviewed_profile_sha256,
        current_profile_sha256=hashlib.sha256(current_bytes).hexdigest(),
        landscape_selection_changed=current["landscape"] != reviewed["landscape"],
    )


def gate1_candidate_matches_approved_evidence(
    approved_evidence: Mapping[str, Any],
    candidate_evidence: Mapping[str, Any],
    profile_binding: Gate1ProfileBinding,
    geography_binding: Gate1GeographyScopeBinding | None = None,
) -> bool:
    """Compare new observations without rewriting the original signed evidence.

    The caller must first validate the original approval and profile binding.
    Every observation and evidence field except the proven-compatible profile
    bytes and provenance commit remains part of the exact comparison.
    """

    for evidence in (approved_evidence, candidate_evidence):
        if evidence.get(GATE1_EVIDENCE_DIGEST_KEY) != gate1_evidence_sha256(evidence):
            return False
    if (
        approved_evidence.get("profile_sha256") != profile_binding.reviewed_profile_sha256
        or candidate_evidence.get("profile_sha256") != profile_binding.current_profile_sha256
    ):
        return False
    comparison = dict(candidate_evidence)
    comparison["profile_sha256"] = profile_binding.reviewed_profile_sha256
    if geography_binding is not None:
        if (
            approved_evidence.get("geography_sha256") != geography_binding.reviewed_geography_sha256
            or candidate_evidence.get("geography_sha256") != geography_binding.current_geography_sha256
        ):
            return False
        comparison["geography_sha256"] = geography_binding.reviewed_geography_sha256
    return gate1_evidence_contract_sha256(approved_evidence) == (
        gate1_evidence_contract_sha256(comparison)
    )


def _contract_digest(repo_root: Path, relative_path: str) -> str:
    path = (repo_root / relative_path).resolve()
    try:
        path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError("Gate 1 geography contract escapes the repository") from exc
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_review_view(
    cursor: Any,
    *,
    region_id: str,
    database_schema: str,
    view_name: str,
    expected_asset: Any,
    native_epsg: int,
) -> _LiveReviewGeography:
    view_query = sql.SQL(
        """
        select region_id, geography_id, geography_role, water_policy, label,
               source_sha256, st_isvalid(geom), st_isempty(geom),
               st_srid(geom), st_geometrytype(geom), st_asbinary(geom),
               st_area(st_transform(geom, %s)) / 1000000.0,
               st_asgeojson(geom)
        from {}.{}
        """
    ).format(sql.Identifier(database_schema), sql.Identifier(view_name))
    cursor.execute(view_query, (native_epsg,))
    rows = cursor.fetchall()
    if len(rows) != 1:
        raise ValueError(
            f"{region_id}: Gate 1 view {database_schema}.{view_name} must "
            "contain exactly one row"
        )
    (
        database_region_id,
        geography_id,
        geography_role,
        water_policy,
        label,
        source_sha256,
        geometry_is_valid,
        geometry_is_empty,
        srid,
        database_geometry_type,
        geometry_wkb,
        database_area_km2,
        geometry_json,
    ) = rows[0]
    if str(database_region_id) != region_id:
        raise ValueError(f"{region_id}: Gate 1 view region id drifted")
    observed_water_policy = (
        str(water_policy) if water_policy is not None else None
    )
    if any(
        (
            str(geography_id) != expected_asset.id,
            str(geography_role) != expected_asset.role,
            observed_water_policy != expected_asset.water_policy,
            str(label) != expected_asset.label,
            str(source_sha256) != expected_asset.sha256,
            not bool(geometry_is_valid),
            bool(geometry_is_empty),
            int(srid) != 4326,
            str(database_geometry_type) != "ST_MultiPolygon",
            geometry_wkb is None,
        )
    ):
        raise ValueError(
            f"{region_id}: Gate 1 view {database_schema}.{view_name} "
            "drifted from its exact manifest binding"
        )
    fingerprint = fingerprint_gate1_wkb(
        bytes(geometry_wkb),
        native_crs=expected_asset.native_crs,
    )
    database_area_km2 = float(database_area_km2)
    if not math.isfinite(database_area_km2) or database_area_km2 <= 0.0:
        raise ValueError(f"{region_id}: Gate 1 database area is not usable")
    database_area_delta_m2 = abs(
        database_area_km2 - fingerprint.area_km2
    ) * 1_000_000.0
    if database_area_delta_m2 > AREA_BINDING_TOLERANCE_M2:
        raise ValueError(
            f"{region_id}: Gate 1 database area differs from live geometry"
        )
    geometry = json.loads(str(geometry_json))
    if (
        not isinstance(geometry, Mapping)
        or geometry.get("type") != "MultiPolygon"
    ):
        raise ValueError(f"{region_id}: Gate 1 geometry is not a MultiPolygon")
    return _LiveReviewGeography(
        geography_id=str(geography_id),
        geography_role=str(geography_role),
        water_policy=observed_water_policy,
        label=str(label),
        source_sha256=str(source_sha256),
        area_km2=fingerprint.area_km2,
        database_area_km2=database_area_km2,
        geometry_sha256=fingerprint.geometry_sha256,
        geometry_type=fingerprint.geometry_type,
        geometry=geometry,
    )


def _mapping(value: Any, label: str, region_id: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{region_id}: Gate 1 {label} evidence is invalid")
    return value


def _evidence_float(
    evidence: Mapping[str, Any],
    key: str,
    *,
    region_id: str,
) -> float:
    try:
        value = float(evidence[key])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            f"{region_id}: Gate 1 evidence {key!r} is missing or invalid"
        ) from exc
    if not math.isfinite(value):
        raise ValueError(
            f"{region_id}: Gate 1 evidence {key!r} is non-finite"
        )
    return value


def _assert_recorded_geometry_evidence(
    *,
    region_id: str,
    evidence: Mapping[str, Any],
    live: _LiveReviewGeography,
    expected_asset: Any,
) -> None:
    exact_fields = {
        "geography_id": expected_asset.id,
        "role": expected_asset.role,
        "water_policy": expected_asset.water_policy,
        "label": expected_asset.label,
        "provider": expected_asset.provider,
        "path": expected_asset.path,
        "source_sha256": expected_asset.sha256,
        "source_geometry_sha256": live.geometry_sha256,
        "live_geometry_sha256": live.geometry_sha256,
        "geometry_type": live.geometry_type,
        "database_geometry_type": "ST_MultiPolygon",
        "srid": 4326,
    }
    drifted = {
        key: (evidence.get(key), expected)
        for key, expected in exact_fields.items()
        if evidence.get(key) != expected
    }
    if drifted:
        raise ValueError(
            f"{region_id}: Gate 1 live geometry evidence drifted: {drifted!r}"
        )
    for key, expected_area_km2 in (
        ("source_area_km2", live.area_km2),
        ("live_area_km2", live.area_km2),
        ("database_area_km2", live.database_area_km2),
    ):
        recorded = _evidence_float(evidence, key, region_id=region_id)
        if abs(recorded - expected_area_km2) * 1_000_000.0 > (
            AREA_BINDING_TOLERANCE_M2
        ):
            raise ValueError(
                f"{region_id}: Gate 1 evidence {key!r} drifted from live geometry"
            )
    for key in (
        "source_live_area_delta_m2",
        "database_live_area_delta_m2",
    ):
        if _evidence_float(evidence, key, region_id=region_id) > (
            AREA_BINDING_TOLERANCE_M2
        ):
            raise ValueError(
                f"{region_id}: Gate 1 evidence {key!r} exceeds tolerance"
            )
    if _evidence_float(
        evidence,
        "area_binding_tolerance_m2",
        region_id=region_id,
    ) != AREA_BINDING_TOLERANCE_M2:
        raise ValueError(f"{region_id}: Gate 1 area tolerance drifted")


def _load_geometry_relationship(
    cursor: Any,
    *,
    database_schema: str,
    boundary_view: str,
    analysis_surface_view: str,
    native_epsg: int,
) -> tuple[float, float, float]:
    # Prove zero from valid, byte-identical projected polygons in this statement.
    # Every other input retains the three precise operations below.
    query = sql.SQL(
        """
        with projected as materialized (
            select st_transform(a.geom, %s) as analysis_geom,
                   st_transform(b.geom, %s) as boundary_geom
            from {}.{} a cross join {}.{} b
        ), relationship as materialized (
            select case when
                case when st_geometrytype(analysis_geom) = 'ST_MultiPolygon'
                          and st_ndims(analysis_geom) = 2
                          and not st_isempty(analysis_geom)
                     then case when st_asewkb(analysis_geom, 'NDR') = st_asewkb(boundary_geom, 'NDR')
                               then st_isvalid(analysis_geom, 0)
                               else false end
                     else false end
                then array[0.0::double precision, 0.0::double precision, 0.0::double precision]
                else array[st_area(st_difference(analysis_geom, boundary_geom)),
                           st_area(st_difference(boundary_geom, analysis_geom)),
                           st_area(st_symdifference(analysis_geom, boundary_geom))]
                end as areas
            from projected
        )
        select areas[1], areas[2], areas[3] from relationship
        """
    ).format(
        sql.Identifier(database_schema),
        sql.Identifier(analysis_surface_view),
        sql.Identifier(database_schema),
        sql.Identifier(boundary_view),
    )
    cursor.execute(query, (native_epsg, native_epsg))
    row = cursor.fetchone()
    if row is None:
        raise ValueError("Gate 1 identity/analysis relationship is missing")
    values = tuple(float(value) for value in row)
    if any(not math.isfinite(value) or value < 0.0 for value in values):
        raise ValueError(
            "Gate 1 identity/analysis differences are non-finite or negative"
        )
    return values


def _assert_recorded_relationship(
    *,
    region_id: str,
    evidence: Mapping[str, Any],
    outside_m2: float,
    excluded_m2: float,
    symmetric_difference_m2: float,
) -> None:
    expected = {
        "outside_identity_tolerance_m2": AREA_BINDING_TOLERANCE_M2,
        "observed_outside_identity_m2": outside_m2,
        "observed_excluded_area_m2": excluded_m2,
        "observed_symmetric_difference_m2": symmetric_difference_m2,
        "difference_sum_delta_m2": abs(
            symmetric_difference_m2 - outside_m2 - excluded_m2
        ),
    }
    for key, expected_value in expected.items():
        recorded = _evidence_float(evidence, key, region_id=region_id)
        if abs(recorded - expected_value) > AREA_BINDING_TOLERANCE_M2:
            raise ValueError(
                f"{region_id}: Gate 1 relationship evidence {key!r} drifted"
            )


def load_gate1_region_reviews(
    repo_root: Path,
    database_url: str,
) -> tuple[Gate1RegionReview, ...]:
    if not database_url.strip():
        raise ValueError("DATABASE_URL is required for Gate 1 review")
    try:
        import psycopg
    except Exception as exc:
        raise RuntimeError(f"psycopg is unavailable: {exc}") from exc

    expected_review_commit = gate1_review_commit(repo_root)
    reviews: list[Gate1RegionReview] = []
    with psycopg.connect(
        database_url,
        connect_timeout=5,
        options="-c default_transaction_read_only=on",
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("show transaction_read_only")
            read_only_state = cursor.fetchone()
            if read_only_state is None or str(read_only_state[0]).lower() != "on":
                raise ValueError("Gate 1 review database connection is not read-only")
            for region_id in DELIVERY_REGION_IDS:
                profile = load_region_profile(repo_root, region_id)
                geography = load_region_geography(region_id)
                cursor.execute(
                    """
                    select gate_state, profile_sha256, automated_evidence,
                           owner_reviewed_at, owner_review_note
                    from meta.region_delivery_gates
                    where region_id = %s and gate_id = 1
                    """,
                    (region_id,),
                )
                gate_row = cursor.fetchone()
                if gate_row is None:
                    raise ValueError(f"{region_id}: Gate 1 status is missing")
                gate_state = str(gate_row[0])
                recorded_profile_sha256 = str(gate_row[1])
                recorded_evidence = gate_row[2]
                owner_reviewed_at = gate_row[3]
                owner_review_note = gate_row[4]
                if gate_state not in {"automatically_validated", "localhost_approved"}:
                    raise ValueError(
                        f"{region_id}: Gate 1 is not automatically validated: {gate_state}"
                    )
                if not isinstance(recorded_evidence, Mapping):
                    raise ValueError(f"{region_id}: Gate 1 automated evidence is invalid")
                review_commit, automated_evidence_sha256 = (
                    assert_gate1_approval_binding(
                        region_id=region_id,
                        gate_state=gate_state,
                        automated_evidence=recorded_evidence,
                        expected_review_commit=expected_review_commit,
                        owner_reviewed_at=owner_reviewed_at,
                        owner_review_note=owner_review_note,
                        repo_root=repo_root,
                    )
                )
                if recorded_evidence.get("profile_sha256") != recorded_profile_sha256:
                    raise ValueError(f"{region_id}: recorded profile digest differs from sealed evidence")
                profile_binding = assert_gate1_profile_binding(
                    repo_root,
                    region_id,
                    review_commit=review_commit,
                    reviewed_profile_sha256=recorded_profile_sha256,
                )
                geography_scope = assert_gate1_geography_scope(
                    repo_root,
                    region_id,
                    review_commit=review_commit,
                    reviewed_geography_sha256=str(recorded_evidence.get("geography_sha256") or ""),
                )
                if not geography.native_crs.startswith("EPSG:"):
                    raise ValueError(f"{region_id}: native CRS is not EPSG-declared")
                native_epsg = int(geography.native_crs.removeprefix("EPSG:"))

                binding = select_gate1_geography_binding(geography)
                boundary_asset = binding.identity
                analysis_surface_asset = binding.analysis_surface
                boundary_row = _load_review_view(
                    cursor,
                    region_id=region_id,
                    database_schema=profile.database_schema,
                    view_name=profile.boundary_view,
                    expected_asset=boundary_asset,
                    native_epsg=native_epsg,
                )
                analysis_surface_row = _load_review_view(
                    cursor,
                    region_id=region_id,
                    database_schema=profile.database_schema,
                    view_name=profile.analysis_surface_view,
                    expected_asset=analysis_surface_asset,
                    native_epsg=native_epsg,
                )
                evidence_assets = _mapping(
                    recorded_evidence.get("geographies"),
                    "geographies",
                    region_id,
                )
                if any(
                    (
                        evidence_assets.get("boundary_sha256")
                        != boundary_asset.sha256,
                        evidence_assets.get("analysis_surface_sha256")
                        != analysis_surface_asset.sha256,
                        evidence_assets.get("analysis_surface_water_policy")
                        != analysis_surface_asset.water_policy,
                    )
                ):
                    raise ValueError(
                        f"{region_id}: Gate 1 geography evidence drifted"
                    )
                _assert_recorded_geometry_evidence(
                    region_id=region_id,
                    evidence=_mapping(
                        evidence_assets.get("identity"),
                        "identity geography",
                        region_id,
                    ),
                    live=boundary_row,
                    expected_asset=boundary_asset,
                )
                _assert_recorded_geometry_evidence(
                    region_id=region_id,
                    evidence=_mapping(
                        evidence_assets.get("analysis_surface"),
                        "analysis geography",
                        region_id,
                    ),
                    live=analysis_surface_row,
                    expected_asset=analysis_surface_asset,
                )
                expected_binding_evidence = gate1_binding_evidence(binding)
                if dict(
                    _mapping(
                        evidence_assets.get("binding"),
                        "geography binding",
                        region_id,
                    )
                ) != expected_binding_evidence:
                    raise ValueError(
                        f"{region_id}: Gate 1 binding evidence drifted"
                    )
                (
                    outside_m2,
                    excluded_m2,
                    symmetric_difference_m2,
                ) = _load_geometry_relationship(
                    cursor,
                    database_schema=profile.database_schema,
                    boundary_view=profile.boundary_view,
                    analysis_surface_view=profile.analysis_surface_view,
                    native_epsg=native_epsg,
                )
                _assert_recorded_relationship(
                    region_id=region_id,
                    evidence=_mapping(
                        recorded_evidence.get("geometry_relationship"),
                        "geometry relationship",
                        region_id,
                    ),
                    outside_m2=outside_m2,
                    excluded_m2=excluded_m2,
                    symmetric_difference_m2=symmetric_difference_m2,
                )
                if outside_m2 > AREA_BINDING_TOLERANCE_M2:
                    raise ValueError(
                        f"{region_id}: analysis surface extends outside identity"
                    )
                same_geometry = (
                    boundary_row.geometry_sha256
                    == analysis_surface_row.geometry_sha256
                )
                if binding.identity_analysis_same_source and (
                    not same_geometry
                    or symmetric_difference_m2 > AREA_BINDING_TOLERANCE_M2
                ):
                    raise ValueError(
                        f"{region_id}: same-source Gate 1 views have drifted"
                    )
                if binding.positive_exclusion_required and excluded_m2 <= 1.0:
                    raise ValueError(
                        f"{region_id}: derived water-excluding analysis surface "
                        "does not exclude identity area"
                    )
                reviews.append(
                    Gate1RegionReview(
                        region_id=region_id,
                        name=profile.name,
                        country_code=profile.country_code,
                        native_crs=geography.native_crs,
                        database_schema=profile.database_schema,
                        boundary_view=profile.boundary_view,
                        analysis_surface_view=profile.analysis_surface_view,
                        gate_state=gate_state,
                        review_commit=review_commit,
                        automated_evidence_sha256=automated_evidence_sha256,
                        owner_reviewed_at=owner_reviewed_at,
                        owner_review_note=(
                            str(owner_review_note).strip()
                            if owner_review_note is not None
                            else None
                        ),
                        profile_sha256=profile_binding.reviewed_profile_sha256,
                        current_profile_sha256=profile_binding.current_profile_sha256,
                        landscape_selection_changed=profile_binding.landscape_selection_changed,
                        geography_sha256=geography_scope.reviewed_geography_sha256,
                        current_geography_sha256=geography_scope.current_geography_sha256,
                        technology_support_added=geography_scope.technology_support_added,
                        boundary_sha256=boundary_row.source_sha256,
                        boundary_label=boundary_row.label,
                        boundary_role=boundary_row.geography_role,
                        boundary_area_km2=boundary_row.database_area_km2,
                        boundary_geometry_sha256=(
                            boundary_row.geometry_sha256
                        ),
                        boundary_geometry=boundary_row.geometry,
                        analysis_surface_sha256=(
                            analysis_surface_row.source_sha256
                        ),
                        analysis_surface_label=analysis_surface_row.label,
                        analysis_surface_role=(
                            analysis_surface_row.geography_role
                        ),
                        analysis_surface_water_policy=(
                            analysis_surface_row.water_policy
                        ),
                        analysis_surface_area_km2=(
                            analysis_surface_row.database_area_km2
                        ),
                        analysis_surface_geometry_sha256=(
                            analysis_surface_row.geometry_sha256
                        ),
                        analysis_surface_geometry=analysis_surface_row.geometry,
                        identity_binding_status=(
                            binding.identity_binding_status
                        ),
                        analysis_surface_binding_status=(
                            binding.analysis_surface_binding_status
                        ),
                        identity_analysis_same_source=(
                            binding.identity_analysis_same_source
                        ),
                        identity_analysis_source_relation=(
                            binding.identity_analysis_source_relation
                        ),
                        identity_analysis_same_geometry=same_geometry,
                        observed_outside_identity_m2=outside_m2,
                        observed_excluded_area_m2=excluded_m2,
                        observed_symmetric_difference_m2=(
                            symmetric_difference_m2
                        ),
                    )
                )
    return tuple(reviews)
