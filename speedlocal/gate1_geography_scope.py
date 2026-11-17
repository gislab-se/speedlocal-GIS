"""Preserve a reviewed Gate 1 geography while later technology inputs are added."""
from __future__ import annotations

from dataclasses import dataclass
import base64
import binascii
import hashlib
import json
from pathlib import Path
from typing import Any

from .contracts import region_geography_contract
from .gate1_geography import select_gate1_geography_binding
from .region_profile import load_region_profile
from .validation import validate_region_geography_contract


@dataclass(frozen=True)
class Gate1GeographyScopeBinding:
    reviewed_geography_sha256: str
    current_geography_sha256: str
    technology_support_added: bool


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate geography evidence field: {key!r}")
        result[key] = value
    return result


def _git_object_id(kind: str, payload: bytes) -> str:
    return hashlib.sha1(f"{kind} {len(payload)}\0".encode("ascii") + payload).hexdigest()


def _tree_entry(payload: bytes, expected_name: str) -> tuple[bytes, str]:
    """Read one exact entry while rejecting ambiguous or malformed tree bytes."""
    entries: dict[str, tuple[bytes, str]] = {}
    offset = 0
    while offset < len(payload):
        separator = payload.find(b" ", offset)
        terminator = payload.find(b"\0", separator + 1)
        if separator < offset or terminator < separator or terminator + 21 > len(payload):
            raise ValueError("Malformed reviewed geography Git tree")
        mode = payload[offset:separator]
        name = payload[separator + 1:terminator].decode("utf-8")
        if not name or name in {".", ".."} or "/" in name or name in entries:
            raise ValueError("Ambiguous reviewed geography Git tree entry")
        entries[name] = (mode, payload[terminator + 1:terminator + 21].hex())
        offset = terminator + 21
    if expected_name not in entries:
        raise ValueError("Reviewed geography Git tree lacks the declared path")
    return entries[expected_name]


def _assert_reviewed_commit_blob(
    evidence: dict[str, Any], original_bytes: bytes, *, region_id: str, review_commit: str,
) -> None:
    """Verify only the approved commit's regions/<id>/geography.json inclusion.

    The historical worktree digest remains separate provenance. This proves
    committed reference content; it does not reconstruct the worktree bytes.
    """
    proof = evidence.get("git_object_proof")
    if not isinstance(proof, dict) or set(proof) != {"commit_base64", "tree_objects_base64"}:
        raise ValueError("Reviewed geography Git object proof is invalid")
    trees = proof["tree_objects_base64"]
    if not isinstance(trees, list) or len(trees) != 3:
        raise ValueError("Reviewed geography proof requires exactly three path trees")
    try:
        commit = base64.b64decode(proof["commit_base64"], validate=True)
        tree_bytes = [base64.b64decode(item, validate=True) for item in trees]
    except (binascii.Error, ValueError, TypeError) as exc:
        raise ValueError("Reviewed geography Git object encoding is invalid") from exc
    if _git_object_id("commit", commit) != review_commit:
        raise ValueError("Reviewed geography commit differs from the existing approval")
    first_line = commit.split(b"\n", 1)[0]
    if not first_line.startswith(b"tree ") or len(first_line) != 45:
        raise ValueError("Reviewed geography commit has no valid root tree")
    expected_oid = first_line[5:].decode("ascii")
    for index, (name, payload) in enumerate(zip(("regions", region_id, "geography.json"), tree_bytes)):
        if _git_object_id("tree", payload) != expected_oid:
            raise ValueError("Reviewed geography tree differs from its approved parent")
        mode, expected_oid = _tree_entry(payload, name)
        if mode != (b"100644" if index == 2 else b"40000"):
            raise ValueError("Reviewed geography path has an unsupported Git object mode")
    if _git_object_id("blob", original_bytes) != expected_oid:
        raise ValueError("Reviewed geography blob differs from the approved path")
    if hashlib.sha256(original_bytes).hexdigest() != evidence.get("geography_blob_sha256"):
        raise ValueError("Reviewed geography blob checksum is invalid")


def assert_gate1_geography_scope(
    repo_root: Path,
    region_id: str,
    *,
    review_commit: str,
    reviewed_geography_sha256: str,
    current_geography_bytes: bytes | None = None,
    reference_bytes: bytes | None = None,
) -> Gate1GeographyScopeBinding:
    """Bind unchanged Gate 1 inputs without approving later technology domains.

    Call only after verifying the existing approval seal and profile binding.
    Reference content comes from exact sealed bytes or a verified object proof
    for the reviewed commit, never Git at runtime. All original fields and
    domains must remain exact; the historical worktree digest is never replaced.
    """
    profile = load_region_profile(repo_root, region_id)
    path = (repo_root / profile.contracts["geography"]).resolve()
    if not path.is_relative_to(repo_root.resolve()):
        raise ValueError("Gate 1 geography contract escapes the repository")
    current_bytes = path.read_bytes() if current_geography_bytes is None else current_geography_bytes
    current_digest = hashlib.sha256(current_bytes).hexdigest()
    current = json.loads(current_bytes, object_pairs_hook=_unique_object)
    current_contract = region_geography_contract(current)
    validate_region_geography_contract(current_contract)
    if current_contract.region_id != region_id:
        raise ValueError("Current Gate 1 geography belongs to another region")
    if current_digest == reviewed_geography_sha256:
        return Gate1GeographyScopeBinding(reviewed_geography_sha256, current_digest, False)

    reference_path = path.with_name("gate1-geography-reference.json")
    try:
        payload = reference_path.read_bytes() if reference_bytes is None else reference_bytes
    except OSError as exc:
        raise ValueError("Reviewed Gate 1 geography reference is unavailable") from exc
    evidence = json.loads(
        payload,
        object_pairs_hook=_unique_object,
    )
    if not isinstance(evidence, dict) or any((
        evidence.get("region_id") != region_id,
        evidence.get("review_commit") != review_commit,
        not isinstance(evidence.get("geography_json"), str),
    )):
        raise ValueError("Reviewed Gate 1 geography reference identity is invalid")
    original_bytes = evidence["geography_json"].encode("utf-8")
    if evidence.get("schema_version") == "1.0":
        if evidence.get("geography_sha256") != reviewed_geography_sha256 or hashlib.sha256(original_bytes).hexdigest() != reviewed_geography_sha256:
            raise ValueError("Reviewed Gate 1 geography bytes differ from the original seal")
    elif evidence.get("schema_version") == "2.0":
        if (
            evidence.get("reference_kind") != "reviewed_commit_blob"
            or evidence.get("sealed_worktree_sha256") != reviewed_geography_sha256
            or path.relative_to(repo_root.resolve()).as_posix() != f"regions/{region_id}/geography.json"
        ):
            raise ValueError("Reviewed Gate 1 commit reference identity is invalid")
        _assert_reviewed_commit_blob(evidence, original_bytes, region_id=region_id, review_commit=review_commit)
    else:
        raise ValueError("Unsupported reviewed Gate 1 geography reference schema")
    original = json.loads(original_bytes, object_pairs_hook=_unique_object)
    original_contract = region_geography_contract(original)
    validate_region_geography_contract(original_contract)
    if original_contract.region_id != region_id:
        raise ValueError("Reviewed Gate 1 geography belongs to another region")

    extension_keys = {"geographies", "technology_support_domains"}
    if {key: value for key, value in original.items() if key not in extension_keys} != {
        key: value for key, value in current.items() if key not in extension_keys
    }:
        raise ValueError("Geography changed outside later technology-support additions")
    for key in extension_keys:
        if any(current.get(key, {}).get(name) != value for name, value in original.get(key, {}).items()):
            raise ValueError("Previously reviewed geography or domain changed")
    original_binding = select_gate1_geography_binding(original_contract)
    current_binding = select_gate1_geography_binding(current_contract)
    if current_binding != original_binding:
        raise ValueError("Later technology support changed the Gate 1 geography binding")
    added_geographies = current_contract.geographies.keys() - original_contract.geographies.keys()
    added_domains = current_contract.technology_support_domains.keys() - original_contract.technology_support_domains.keys()
    referenced_additions = {
        current_contract.technology_support_domains[name].coverage_geometry_id
        for name in added_domains
    }
    if added_geographies != referenced_additions:
        raise ValueError("Geography additions must be exactly the new technology-domain aliases")
    original_surface = original_binding.analysis_surface
    source_fields = (
        "provider", "path", "sha256", "format", "geometry_family",
        "source_crs", "native_crs", "water_policy",
    )
    for name in added_geographies:
        alias = current_contract.geographies[name]
        if alias.role != "technology_target_surface" or any(
            getattr(alias, field) != getattr(original_surface, field)
            for field in source_fields
        ):
            raise ValueError("New technology geography is not an exact reviewed-source alias")
    return Gate1GeographyScopeBinding(
        reviewed_geography_sha256, current_digest, bool(added_domains),
    )
