"""Bind source review approval to the existing delivery-gate registry.

Recording is an explicit operation. Reading approval never promotes a gate and
compares the selected live views with the original reviewed observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

import psycopg
from psycopg.types.json import Jsonb
from shapely import wkb

from .gate1_review import (
    assert_gate1_approval_binding,
    gate1_evidence_sha256,
    gate1_review_commit,
    load_gate1_region_reviews,
    validate_delivery_gate_states,
)
from .gate2_review import _load_source_row
from .region_profile import DELIVERY_REGION_IDS, load_region_profile
from .source_catalog import DeliverySourceSelection, load_delivery_source_selection


@dataclass(frozen=True)
class Gate2SourceApproval:
    region_id: str
    review_commit: str
    profile_sha256: str
    selection_sha256: str
    evidence_sha256: str
    owner_reviewed_at: datetime
    owner_review_note: str
    source_observations: tuple[Mapping[str, Any], ...]


def _seal(payload: Mapping[str, Any]) -> str:
    return gate1_evidence_sha256(payload)


def _region_binding(selection: DeliverySourceSelection) -> dict[str, Any]:
    return {
        "region_id": selection.region_id,
        "profile_sha256": selection.profile_sha256,
        "selection_sha256": selection.selection_sha256,
        "groups": {
            group.id: [source.database_view for source in group.sources]
            for group in selection.groups
        },
    }


def _by_region(values: Any, label: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(values, list) or any(not isinstance(value, dict) for value in values):
        raise ValueError(f"Gate 2 {label} must be a list of region objects")
    result = {value.get("region_id"): value for value in values}
    if set(result) != set(DELIVERY_REGION_IDS) or len(values) != len(result):
        raise ValueError(f"Gate 2 {label} must cover each delivery region exactly once")
    return result


def validate_gate2_review_evidence(
    evidence: Mapping[str, Any],
    *,
    reviewed_commit: str,
    evidence_sha256: str,
    review_receipt: Mapping[str, Any],
    browser_evidence: Mapping[str, Any],
) -> None:
    """Validate review provenance against the caller's exact external seal."""
    if re.fullmatch(r"[0-9a-f]{40}", reviewed_commit) is None:
        raise ValueError("Gate 2 needs the full reviewed Git commit")
    if (
        re.fullmatch(r"[0-9a-f]{64}", evidence_sha256) is None
        or evidence.get("evidence_sha256") != evidence_sha256
        or _seal(evidence) != evidence_sha256
    ):
        raise ValueError("Gate 2 original source-evidence seal is invalid")
    if (
        evidence.get("schema_version") != "1.0"
        or evidence.get("gate_id") != 2
        or evidence.get("scope") != "profile_selected_sources"
        or evidence.get("validator") != "scripts/validate_delivery_source_database.py"
        or evidence.get("checked_commit") != reviewed_commit
        or type(evidence.get("dirty_path_count")) is not int
        or evidence["dirty_path_count"] != 0
        or evidence.get("owner_approved") is not False
    ):
        raise ValueError("Gate 2 source evidence is not the clean automated review")
    regions = _by_region(evidence.get("regions"), "source selection")
    geography = _by_region(evidence.get("gate1_provenance"), "Gate 1 provenance")
    if any(value.get("gate_state") != "localhost_approved" for value in geography.values()):
        raise ValueError("Gate 2 review requires three approved Gate 1 records")
    observations = evidence.get("source_observations")
    if not isinstance(observations, list) or any(not isinstance(value, dict) for value in observations):
        raise ValueError("Gate 2 source observations are invalid")
    observed_keys = [(item.get("region_id"), str(item.get("database_view", "")).rsplit(".", 1)[-1]) for item in observations]
    expected_keys = [
        (region_id, view)
        for region_id, region in regions.items()
        for views in region["groups"].values()
        for view in views
    ]
    if len(set(observed_keys)) != len(observed_keys) or sorted(observed_keys) != sorted(expected_keys):
        raise ValueError("Gate 2 evidence does not cover exactly the reviewed selected views")
    if (
        review_receipt.get("commit") != reviewed_commit
        or type(review_receipt.get("dirty_path_count")) is not int
        or review_receipt["dirty_path_count"] != 0
        or review_receipt.get("review_mode") != "gate2_source_views"
        or type(review_receipt.get("port")) is not int
        or not 1 <= review_receipt["port"] <= 65535
        or not str(review_receipt.get("entrypoint", "")).replace("\\", "/").endswith("/apps/v2_port/app.py")
    ):
        raise ValueError("Gate 2 localhost receipt does not bind the clean reviewed app")
    if (
        browser_evidence.get("checked_commit") != reviewed_commit
        or browser_evidence.get("owner_approved") is not False
    ):
        raise ValueError("Gate 2 browser evidence has invalid provenance")
    browser_views = _by_region(browser_evidence.get("views"), "browser observations")
    for region_id, view in browser_views.items():
        url = urlparse(str(view.get("url", "")))
        query = parse_qs(url.query)
        group_id = view.get("group_id")
        if (
            view.get("checked_commit") != reviewed_commit
            or url.scheme != "http" or url.hostname != "127.0.0.1"
            or url.port != review_receipt["port"]
            or query.get("view") != ["gate2"] or query.get("scope") != ["delivery"]
            or query.get("region") != [region_id] or query.get("group") != [group_id]
            or group_id not in regions[region_id]["groups"]
            or len(view.get("labels", [])) != len(regions[region_id]["groups"][group_id])
        ):
            raise ValueError(f"{region_id}: browser observation is outside the reviewed selection")


def _assert_ancestor(repo_root: Path, reviewed_commit: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", reviewed_commit, "HEAD"],
        capture_output=True, check=False,
    )
    if result.returncode != 0:
        raise ValueError("Gate 2 reviewed commit is not an ancestor of the current repository")


def _live_observations(cursor: Any, repo_root: Path, selection: DeliverySourceSelection) -> list[dict[str, Any]]:
    """Read sealed views without opening any source GIS files."""
    profile = load_region_profile(repo_root, selection.region_id)
    observations = []
    for source in selection.sources:
        row = _load_source_row(cursor, schema=profile.database_schema, view=source.database_view)
        expected = (
            source.region_id, source.group_id, source.id, source.label, source.authority,
            source.dataset, source.snapshot_date, source.license_name, source.license_status,
            source.public_display_status, source.sha256, source.source_feature_count,
            source.expected_feature_count, source.geometry_family, source.data_representation,
            source.selection,
        )
        observed = tuple(value.isoformat() if index == 6 and value is not None else value for index, value in enumerate(row[:-1]))
        if observed != expected:
            raise ValueError(f"{selection.region_id}/{source.id}: approved source metadata drifted")
        geometry = wkb.loads(bytes(row[-1]))
        if geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"{selection.region_id}/{source.id}: approved source geometry is invalid")
        observations.append({
            "region_id": selection.region_id,
            "group_id": source.group_id,
            "source_id": source.id,
            "database_view": f"{profile.database_schema}.{source.database_view}",
            "source_sha256": source.sha256,
            "geometry_sha256": hashlib.sha256(geometry.normalize().wkb).hexdigest(),
            "license_status": source.license_status,
            "public_display_status": source.public_display_status,
            "asset_feature_count": source.expected_feature_count,
        })
    return observations


def _assert_current_selection(
    selection: DeliverySourceSelection,
    evidence: Mapping[str, Any],
    live_observations: list[dict[str, Any]],
) -> None:
    regions = _by_region(evidence["regions"], "source selection")
    if regions[selection.region_id] != _region_binding(selection):
        raise ValueError(f"{selection.region_id}: reviewed profile or selected-source revision changed")
    expected = [item for item in evidence["source_observations"] if item["region_id"] == selection.region_id]
    if expected != live_observations:
        raise ValueError(f"{selection.region_id}: live source observations changed since review")


def assert_gate2_approval_binding(
    *,
    selection: DeliverySourceSelection,
    gate_states: Mapping[int, str],
    recorded_profile_sha256: str,
    automated_evidence: Mapping[str, Any],
    owner_reviewed_at: Any,
    owner_review_note: Any,
    live_observations: list[dict[str, Any]],
) -> Gate2SourceApproval:
    """Pure fail-closed check; callers separately verify Gate 1 and Git ancestry."""
    region_id = selection.region_id
    validate_delivery_gate_states(region_id, gate_states)
    if gate_states[2] != "localhost_approved":
        raise ValueError(f"{region_id}: Gate 2 is not owner-approved")
    if (
        not isinstance(owner_reviewed_at, datetime) or owner_reviewed_at.tzinfo is None
        or owner_reviewed_at.utcoffset() is None
        or not isinstance(owner_review_note, str) or not owner_review_note.strip()
        or owner_review_note != automated_evidence.get("owner_review_note")
        or owner_reviewed_at != datetime.fromisoformat(str(automated_evidence.get("owner_reviewed_at", "")))
    ):
        raise ValueError(f"{region_id}: Gate 2 owner fields are missing or differ from sealed evidence")
    if automated_evidence.get("evidence_sha256") != _seal(automated_evidence):
        raise ValueError(f"{region_id}: Gate 2 approval seal is invalid")
    original = automated_evidence.get("reviewed_source_evidence", {})
    validate_gate2_review_evidence(
        original, reviewed_commit=automated_evidence.get("review_commit", ""),
        evidence_sha256=automated_evidence.get("reviewed_source_evidence_sha256", ""),
        review_receipt=automated_evidence.get("review_receipt", {}),
        browser_evidence=automated_evidence.get("browser_evidence", {}),
    )
    _assert_current_selection(selection, original, live_observations)
    if (
        automated_evidence.get("schema_version") != "1.0"
        or automated_evidence.get("gate_id") != 2
        or automated_evidence.get("scope") != "profile_selected_sources"
        or automated_evidence.get("region_binding") != _region_binding(selection)
        or automated_evidence.get("source_observations") != live_observations
        or recorded_profile_sha256 != selection.profile_sha256
    ):
        raise ValueError(f"{region_id}: Gate 2 regional approval differs from its reviewed inputs")
    return Gate2SourceApproval(
        region_id, automated_evidence["review_commit"], selection.profile_sha256,
        selection.selection_sha256, automated_evidence["evidence_sha256"],
        owner_reviewed_at, owner_review_note, tuple(live_observations),
    )


def _gate_rows(cursor: Any, *, lock: bool = False) -> dict[str, dict[int, tuple[Any, ...]]]:
    cursor.execute(
        "select region_id, gate_id, gate_state, profile_sha256, automated_evidence, "
        "owner_reviewed_at, owner_review_note from meta.region_delivery_gates "
        "where region_id = any(%s) order by region_id, gate_id" + (" for update" if lock else ""),
        (list(DELIVERY_REGION_IDS),),
    )
    result = {region_id: {} for region_id in DELIVERY_REGION_IDS}
    for region_id, gate_id, *row in cursor.fetchall():
        result[region_id][gate_id] = tuple(row)
    for region_id, rows in result.items():
        validate_delivery_gate_states(region_id, {gate_id: row[0] for gate_id, row in rows.items()})
    return result


def _verify_gate1_rows(repo_root: Path, rows: Mapping[str, Any], geography: tuple[Any, ...]) -> None:
    current_commit = gate1_review_commit(repo_root)
    if {review.region_id for review in geography} != set(DELIVERY_REGION_IDS):
        raise ValueError("All three sealed Gate 1 reviews are required")
    for review in geography:
        state, profile_sha, evidence, reviewed_at, note = rows[review.region_id][1]
        _, seal = assert_gate1_approval_binding(
            region_id=review.region_id, gate_state=state, automated_evidence=evidence,
            expected_review_commit=current_commit, owner_reviewed_at=reviewed_at,
            owner_review_note=note, repo_root=repo_root,
        )
        if state != "localhost_approved" or seal != review.automated_evidence_sha256 or profile_sha != review.profile_sha256:
            raise ValueError(f"{review.region_id}: sealed Gate 1 approval changed")


def _assert_gate1_provenance(evidence: Mapping[str, Any], geography: tuple[Any, ...]) -> None:
    expected = _by_region(evidence["gate1_provenance"], "Gate 1 provenance")
    for review in geography:
        observed = {
            "region_id": review.region_id, "gate_state": review.gate_state,
            "review_commit": review.review_commit,
            "automated_evidence_sha256": review.automated_evidence_sha256,
            "reviewed_profile_sha256": review.profile_sha256,
            "current_profile_sha256": review.current_profile_sha256,
            "landscape_selection_changed": review.landscape_selection_changed,
        }
        if expected[review.region_id] != observed:
            raise ValueError(f"{review.region_id}: reviewed Gate 1 provenance changed")


def load_gate2_source_approvals(
    repo_root: Path, database_url: str, *, region_id: str | None = None,
) -> tuple[Gate2SourceApproval, ...]:
    """Verify recorded approval and current live inputs without modifying gates."""
    if region_id is not None and region_id not in DELIVERY_REGION_IDS:
        raise ValueError(f"Region is outside the delivery: {region_id}")
    if not database_url.strip():
        raise ValueError("DATABASE_URL is required for Gate 2 approval verification")
    geography = load_gate1_region_reviews(repo_root, database_url)
    approved = []
    with psycopg.connect(database_url, connect_timeout=5, options="-c default_transaction_read_only=on") as connection:
        with connection.cursor() as cursor:
            rows = _gate_rows(cursor)
            _verify_gate1_rows(repo_root, rows, geography)
            for selected_id in DELIVERY_REGION_IDS:
                if region_id is not None and selected_id != region_id:
                    continue
                selection = load_delivery_source_selection(repo_root, selected_id)
                state, profile_sha, evidence, reviewed_at, note = rows[selected_id][2]
                approval = assert_gate2_approval_binding(
                    selection=selection, gate_states={key: value[0] for key, value in rows[selected_id].items()},
                    recorded_profile_sha256=profile_sha, automated_evidence=evidence,
                    owner_reviewed_at=reviewed_at, owner_review_note=note,
                    live_observations=_live_observations(cursor, repo_root, selection),
                )
                _assert_ancestor(repo_root, approval.review_commit)
                _assert_gate1_provenance(
                    evidence["reviewed_source_evidence"],
                    tuple(review for review in geography if review.region_id == selected_id),
                )
                approved.append(approval)
    return tuple(approved)


def record_gate2_source_approvals(
    repo_root: Path, database_url: str, *, evidence: Mapping[str, Any],
    reviewed_commit: str, evidence_sha256: str, review_receipt: Mapping[str, Any],
    browser_evidence: Mapping[str, Any], owner_note: str, apply: bool = False,
) -> tuple[dict[str, Any], ...]:
    """Validate all three regions; only explicit apply updates Gate 2 atomically."""
    if not isinstance(owner_note, str) or not owner_note.strip():
        raise ValueError("An explicit owner review note is required")
    if not database_url.strip():
        raise ValueError("DATABASE_URL is required for Gate 2 approval recording")
    validate_gate2_review_evidence(
        evidence, reviewed_commit=reviewed_commit, evidence_sha256=evidence_sha256,
        review_receipt=review_receipt, browser_evidence=browser_evidence,
    )
    _assert_ancestor(repo_root, reviewed_commit)
    geography = load_gate1_region_reviews(repo_root, database_url)
    _assert_gate1_provenance(evidence, geography)
    proposals = []
    recorded_at = datetime.now(timezone.utc)
    options = "-c default_transaction_read_only=off" if apply else "-c default_transaction_read_only=on"
    with psycopg.connect(database_url, connect_timeout=5, options=options) as connection:
        with connection.cursor() as cursor:
            rows = _gate_rows(cursor, lock=apply)
            _verify_gate1_rows(repo_root, rows, geography)
            for region_id in DELIVERY_REGION_IDS:
                selection = load_delivery_source_selection(repo_root, region_id)
                observations = _live_observations(cursor, repo_root, selection)
                _assert_current_selection(selection, evidence, observations)
                state, profile_sha, prior, reviewed_at, note = rows[region_id][2]
                if state == "localhost_approved":
                    assert_gate2_approval_binding(
                        selection=selection, gate_states={key: value[0] for key, value in rows[region_id].items()},
                        recorded_profile_sha256=profile_sha, automated_evidence=prior,
                        owner_reviewed_at=reviewed_at, owner_review_note=note,
                        live_observations=observations,
                    )
                    if prior["reviewed_source_evidence_sha256"] != evidence_sha256 or prior["review_commit"] != reviewed_commit:
                        raise ValueError(f"{region_id}: existing Gate 2 approval cannot be replaced")
                    proposals.append(dict(prior))
                    continue
                if any(rows[region_id][gate][0] != "incomplete" for gate in range(3, 8)):
                    raise ValueError(f"{region_id}: later delivery progress prevents replacing Gate 2 evidence")
                if reviewed_at is not None or note is not None:
                    raise ValueError(f"{region_id}: unapproved Gate 2 contains stale owner fields")
                proposal = {
                    "schema_version": "1.0", "gate_id": 2, "scope": "profile_selected_sources",
                    "review_commit": reviewed_commit, "region_binding": _region_binding(selection),
                    "source_observations": observations,
                    "reviewed_source_evidence_sha256": evidence_sha256,
                    "reviewed_source_evidence": evidence,
                    "review_receipt": review_receipt, "browser_evidence": browser_evidence,
                    "owner_reviewed_at": recorded_at.isoformat(), "owner_review_note": owner_note.strip(),
                }
                proposal["evidence_sha256"] = _seal(proposal)
                proposals.append(proposal)
            if apply:
                for proposal in proposals:
                    region_id = proposal["region_binding"]["region_id"]
                    if rows[region_id][2][0] == "localhost_approved":
                        continue
                    cursor.execute(
                        "update meta.region_delivery_gates set gate_state = 'automatically_validated', "
                        "profile_sha256 = %s, automated_evidence = %s, updated_at = now() "
                        "where region_id = %s and gate_id = 2 and gate_state in ('incomplete', 'automatically_validated')",
                        (proposal["region_binding"]["profile_sha256"], Jsonb(proposal), region_id),
                    )
                    if cursor.rowcount != 1:
                        raise ValueError(f"{region_id}: Gate 2 validation update failed")
                    cursor.execute(
                        "update meta.region_delivery_gates set gate_state = 'localhost_approved', "
                        "owner_reviewed_at = %s, owner_review_note = %s, updated_at = now() "
                        "where region_id = %s and gate_id = 2 and gate_state = 'automatically_validated'",
                        (recorded_at, owner_note.strip(), region_id),
                    )
                    if cursor.rowcount != 1:
                        raise ValueError(f"{region_id}: Gate 2 owner approval update failed")
    return tuple(proposals)
