from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .paths import GENERATED_RUNTIME_ROOT_ENV, V2_SOURCE_ROOT_ENV, repo_root


RUNTIME_SNAPSHOT_SCHEMA_VERSION = "1.0"
MAX_SMALL_MANIFEST_BYTES = 16 * 1024 * 1024
_REGION_ID = re.compile(r"[a-z0-9]+(?:[_-][a-z0-9]+)*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_PROVIDER_ENVIRONMENTS = {
    "v2_archive": V2_SOURCE_ROOT_ENV,
    "generated_runtime": GENERATED_RUNTIME_ROOT_ENV,
}
_SUPPORTED_PROVIDERS = {"repo", *_PROVIDER_ENVIRONMENTS}
_WINDOWS_REPARSE_POINT = 0x0400


class RuntimeSnapshotError(ValueError):
    """A readiness snapshot could not be built without escaping its contract."""


@dataclass(frozen=True)
class RuntimeReadinessSnapshot:
    """Cheap immutable identity for all inputs used by workspace readiness."""

    region_id: str
    token_sha256: str
    provider_root_states: tuple[tuple[str, str], ...]
    repository_manifest_count: int
    provider_path_count: int
    runtime_marker_count: int
    hashed_manifest_bytes: int

    def __post_init__(self) -> None:
        if not _REGION_ID.fullmatch(self.region_id):
            raise RuntimeSnapshotError("Runtime snapshot region id is invalid")
        if not _SHA256.fullmatch(self.token_sha256):
            raise RuntimeSnapshotError("Runtime snapshot token is not SHA-256")


@dataclass(frozen=True)
class _ProviderRoot:
    provider: str
    state: str
    normalized_path: str | None
    path: Path | None = field(compare=False, repr=False)

    def payload(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "state": self.state,
            "normalized_path": self.normalized_path,
        }


@dataclass(frozen=True)
class _AssetManifestRequest:
    provider: str
    path: str
    layer_id: str
    distance_provider: str | None
    distance_path: str | None
    origin: str


@dataclass
class _ProviderReference:
    provider: str
    path: str
    roles: set[str] = field(default_factory=set)
    origins: set[str] = field(default_factory=set)
    declarations: set[str] = field(default_factory=set)


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _duplicate_safe_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise RuntimeSnapshotError(f"Duplicate JSON field in runtime input: {key}")
        value[key] = item
    return value


def _parse_json(data: bytes, label: str) -> Any:
    try:
        return json.loads(
            data.decode("utf-8-sig"),
            object_pairs_hook=_duplicate_safe_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeSnapshotError(f"Invalid JSON runtime input: {label}") from exc


def _stat_payload(stat: os.stat_result) -> dict[str, int]:
    return {
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "ctime_ns": int(stat.st_ctime_ns),
        "inode": int(stat.st_ino),
        "device": int(stat.st_dev),
        "mode": int(stat.st_mode),
    }


def _stable_small_file(path: Path, label: str) -> tuple[bytes, dict[str, int]]:
    for _attempt in range(2):
        _reject_reparse_point(path, label)
        try:
            before = path.stat()
        except OSError as exc:
            raise RuntimeSnapshotError(f"Unreadable runtime manifest: {label}") from exc
        if not path.is_file():
            raise RuntimeSnapshotError(f"Runtime manifest is not a file: {label}")
        if before.st_size > MAX_SMALL_MANIFEST_BYTES:
            raise RuntimeSnapshotError(f"Runtime manifest is unexpectedly large: {label}")
        try:
            data = path.read_bytes()
            after = path.stat()
        except OSError as exc:
            raise RuntimeSnapshotError(f"Unreadable runtime manifest: {label}") from exc
        before_payload = _stat_payload(before)
        after_payload = _stat_payload(after)
        if before_payload == after_payload and len(data) == after.st_size:
            return data, after_payload
    raise RuntimeSnapshotError(f"Runtime manifest changed while being read: {label}")


def _safe_relative_path(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise RuntimeSnapshotError(f"{label} must be a relative POSIX path string")
    raw_text = value
    text = raw_text.strip()
    if not text or "\x00" in text or "\\" in text:
        raise RuntimeSnapshotError(f"{label} must be a relative POSIX path")
    pure = PurePosixPath(text)
    if (
        pure.is_absolute()
        or text.endswith("/")
        or any(part in {"", ".", ".."} for part in pure.parts)
        or any(":" in part for part in pure.parts)
        or raw_text != text
        or pure.as_posix() != text
    ):
        raise RuntimeSnapshotError(f"{label} escapes its declared root")
    return pure.as_posix()


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _reject_reparse_point(path: Path, label: str) -> None:
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise RuntimeSnapshotError(f"Unreadable runtime path: {label}") from exc
    if path.is_symlink() or (
        int(getattr(stat, "st_file_attributes", 0)) & _WINDOWS_REPARSE_POINT
    ):
        raise RuntimeSnapshotError(f"Runtime path is a link or reparse point: {label}")


def _safe_join(root: Path, relative_path: str, label: str) -> Path:
    normalized = _safe_relative_path(relative_path, label)
    resolved_root = root.resolve()
    _reject_reparse_point(resolved_root, f"{label} root")
    unresolved_candidate = resolved_root
    for part in PurePosixPath(normalized).parts:
        unresolved_candidate = unresolved_candidate / part
        _reject_reparse_point(unresolved_candidate, label)
    try:
        candidate = unresolved_candidate.resolve()
    except OSError as exc:
        raise RuntimeSnapshotError(f"{label} could not be resolved") from exc
    if candidate == resolved_root or not _within(resolved_root, candidate):
        raise RuntimeSnapshotError(f"{label} escapes its declared root")
    return candidate


def _normalized_root(
    provider: str,
    repository_root: Path,
    environ: Mapping[str, str],
) -> _ProviderRoot:
    if provider == "repo":
        root = repository_root.resolve()
        _reject_reparse_point(root, "repository root")
        return _ProviderRoot(
            provider="repo",
            state="ready" if root.is_dir() else "not_directory",
            normalized_path=os.path.normcase(str(root)),
            path=root if root.is_dir() else None,
        )
    environment_name = _PROVIDER_ENVIRONMENTS[provider]
    configured = str(environ.get(environment_name, "") or "").strip()
    if not configured:
        return _ProviderRoot(provider, "missing", None, None)
    try:
        configured_path = Path(configured).expanduser()
        _reject_reparse_point(configured_path, f"{provider} provider root")
        root = configured_path.resolve()
    except OSError:
        return _ProviderRoot(provider, "invalid", configured, None)
    return _ProviderRoot(
        provider=provider,
        state="ready" if root.is_dir() else "not_directory",
        normalized_path=os.path.normcase(str(root)),
        path=root if root.is_dir() else None,
    )


def _file_state(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {"state": "missing"}
    except OSError:
        return {"state": "unreadable"}
    if path.is_file():
        kind = "file"
    elif path.is_dir():
        kind = "directory"
    else:
        kind = "other"
    return {"state": kind, "stat": _stat_payload(stat)}


def _declaration_signature(value: Mapping[str, Any]) -> str | None:
    declaration = {
        key: value[key]
        for key in (
            "sha256",
            "bytes",
            "cell_ids_sha256",
            "rows_sha256",
            "metadata_sha256",
        )
        if key in value
    }
    return _canonical_sha256(declaration) if declaration else None


def _add_provider_reference(
    references: MutableMapping[tuple[str, str], _ProviderReference],
    provider: Any,
    path: Any,
    *,
    role: str,
    origin: str,
    declaration: Mapping[str, Any] | None = None,
) -> None:
    provider_id = str(provider or "").strip()
    if provider_id not in _SUPPORTED_PROVIDERS:
        raise RuntimeSnapshotError(f"Unsupported runtime provider: {provider_id!r}")
    normalized_path = _safe_relative_path(path, f"{provider_id} provider path")
    reference = references.setdefault(
        (provider_id, normalized_path),
        _ProviderReference(provider_id, normalized_path),
    )
    reference.roles.add(str(role))
    reference.origins.add(str(origin))
    if declaration is not None:
        signature = _declaration_signature(declaration)
        if signature is not None:
            reference.declarations.add(signature)


def _json_pointer(parent: str, key: Any) -> str:
    escaped = str(key).replace("~", "~0").replace("/", "~1")
    return f"{parent}/{escaped}"


def _collect_provider_references(
    value: Any,
    *,
    origin_file: str,
    pointer: str,
    references: MutableMapping[tuple[str, str], _ProviderReference],
    asset_requests: set[_AssetManifestRequest],
) -> None:
    if isinstance(value, Mapping):
        provider = value.get("provider")
        if provider is not None and value.get("path") is not None:
            _add_provider_reference(
                references,
                provider,
                value["path"],
                role="declared_asset",
                origin=f"{origin_file}#{pointer or '/'}",
                declaration=value,
            )
        if provider is not None and value.get("asset_manifest") is not None:
            manifest_path = _safe_relative_path(
                value["asset_manifest"],
                "asset-manifest provider path",
            )
            layer_id = str(value.get("layer_id") or "").strip()
            _add_provider_reference(
                references,
                provider,
                manifest_path,
                role="asset_manifest",
                origin=f"{origin_file}#{pointer or '/'}",
                declaration=value,
            )
            if layer_id:
                distance_provider = (
                    str(value.get("distance_provider") or "").strip() or None
                )
                distance_path = (
                    _safe_relative_path(
                        value["distance_path"],
                        "distance provider path",
                    )
                    if value.get("distance_path") is not None
                    else None
                )
                if (distance_provider is None) != (distance_path is None):
                    raise RuntimeSnapshotError(
                        "Distance provider and path must be declared together"
                    )
                if distance_provider is not None:
                    _add_provider_reference(
                        references,
                        distance_provider,
                        distance_path,
                        role="distance_observations",
                        origin=f"{origin_file}#{pointer or '/'}",
                        declaration=value,
                    )
                asset_requests.add(
                    _AssetManifestRequest(
                        provider=str(provider).strip(),
                        path=manifest_path,
                        layer_id=layer_id,
                        distance_provider=distance_provider,
                        distance_path=distance_path,
                        origin=f"{origin_file}#{pointer or '/'}",
                    )
                )
        assets = value.get("assets")
        if provider is not None and isinstance(assets, Mapping):
            for asset_id, asset in assets.items():
                if not isinstance(asset, Mapping) or asset.get("path") is None:
                    continue
                _add_provider_reference(
                    references,
                    asset.get("provider", provider),
                    asset["path"],
                    role=f"contract_asset:{str(asset_id).strip()}",
                    origin=(
                        f"{origin_file}#"
                        f"{_json_pointer(_json_pointer(pointer, 'assets'), asset_id)}"
                    ),
                    declaration=asset,
                )
        for key, item in value.items():
            _collect_provider_references(
                item,
                origin_file=origin_file,
                pointer=_json_pointer(pointer, key),
                references=references,
                asset_requests=asset_requests,
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _collect_provider_references(
                item,
                origin_file=origin_file,
                pointer=_json_pointer(pointer, index),
                references=references,
                asset_requests=asset_requests,
            )


def _collect_diagnostic_snapshot_references(
    document: Any,
    *,
    origin_file: str,
    references: MutableMapping[tuple[str, str], _ProviderReference],
    migrated_source_ids: frozenset[str] = frozenset(),
) -> None:
    if not isinstance(document, Mapping):
        return
    output = document.get("output")
    layers = document.get("layers")
    if (
        not isinstance(output, Mapping)
        or not isinstance(layers, Mapping)
        or not str(document.get("snapshot_id") or "").strip()
    ):
        return
    remaining_layers = set(str(value) for value in layers) - migrated_source_ids
    if not remaining_layers:
        return
    relative_directory = output.get("relative_directory")
    metadata_name = output.get("metadata_name")
    if relative_directory is None or metadata_name is None:
        return
    directory = _safe_relative_path(
        relative_directory,
        "diagnostic snapshot output directory",
    )
    metadata = _safe_relative_path(
        f"{directory}/{metadata_name}",
        "diagnostic snapshot metadata path",
    )
    _add_provider_reference(
        references,
        "generated_runtime",
        metadata,
        role="diagnostic_metadata",
        origin=origin_file,
        declaration=output,
    )
    for layer_id in sorted(remaining_layers):
        if not _REGION_ID.fullmatch(layer_id):
            raise RuntimeSnapshotError("Diagnostic snapshot layer id is unsafe")
        for suffix, role in (
            ("geojson", "diagnostic_geometry"),
            ("csv", "diagnostic_distance"),
        ):
            _add_provider_reference(
                references,
                "generated_runtime",
                f"{directory}/{layer_id}.{suffix}",
                role=role,
                origin=origin_file,
            )


def _resolve_provider_path(
    roots: Mapping[str, _ProviderRoot],
    provider: str,
    relative_path: str,
) -> tuple[Path | None, str]:
    root = roots[provider]
    if root.state != "ready" or root.path is None:
        return None, f"provider_{root.state}"
    return (
        _safe_join(root.path, relative_path, f"{provider} provider path"),
        "resolved",
    )


def _asset_manifest_rows(data: bytes, label: str) -> list[dict[str, str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise RuntimeSnapshotError(f"Invalid asset-manifest encoding: {label}") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames or "layer_id" not in reader.fieldnames:
        raise RuntimeSnapshotError(f"Asset manifest lacks layer_id: {label}")
    return [dict(row) for row in reader]


def _runtime_marker_candidates(
    root: _ProviderRoot,
    region_id: str,
) -> tuple[tuple[str, Path], ...]:
    if root.state != "ready" or root.path is None:
        return ()
    candidates: list[tuple[str, Path]] = [
        (
            "root_complete",
            _safe_join(
                root.path,
                "complete.json",
                f"{root.provider} root-complete marker",
            ),
        ),
        (
            "region_package_readiness",
            _safe_join(
                root.path,
                f"regions/{region_id}/region-package.readiness.json",
                f"{root.provider} region-readiness marker",
            ),
        ),
    ]
    if root.path.name.casefold() == "data":
        candidates.append(("cache_parent_complete", root.path.parent / "complete.json"))
    seen: set[str] = set()
    result: list[tuple[str, Path]] = []
    for role, path in candidates:
        key = os.path.normcase(str(path.resolve()))
        if key not in seen:
            seen.add(key)
            result.append((role, path))
    return tuple(result)


def _repo_linked_paths(region: Mapping[str, Any]) -> tuple[tuple[str, Any], ...]:
    linked: list[tuple[str, Any]] = []
    for key, value in region.items():
        if (
            key in {"workspace_profile", "combined_result_validation"}
            or key.endswith("_manifest")
            or key.endswith("_readiness")
        ):
            linked.append((key, value))
        elif key in {
            "analysis_manifests",
            "diagnostic_source_snapshots",
        }:
            if not isinstance(value, Mapping):
                raise RuntimeSnapshotError(
                    f"Repository {key} links must be a JSON object"
                )
            linked.extend(
                (f"{key}.{item_key}", item) for item_key, item in value.items()
            )
    return tuple(linked)


def build_runtime_readiness_snapshot(
    region_id: str,
    *,
    repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> RuntimeReadinessSnapshot:
    """Fingerprint readiness inputs without reading or hashing large geodata.

    Repository-owned JSON manifests and small integrity markers are hashed by
    content. Manifest-declared provider artifacts contribute only their safe
    resolved existence and stat identity; their declared checksum fields are
    already bound through the small manifest bytes. This keeps Streamlit rerun
    cost small while invalidating readiness after atomic materialization.
    """

    normalized_region_id = str(region_id or "").strip().lower()
    if not _REGION_ID.fullmatch(normalized_region_id):
        raise RuntimeSnapshotError("Runtime snapshot requires a safe region id")
    repository_path = Path(repository_root or repo_root()).expanduser()
    _reject_reparse_point(repository_path, "repository root")
    root = repository_path.resolve()
    if not root.is_dir():
        raise RuntimeSnapshotError("Runtime snapshot repository root is unavailable")
    environment = os.environ if environ is None else environ

    repo_roles: dict[str, set[str]] = {}
    repo_queue: list[str] = []
    repo_records: dict[str, dict[str, Any]] = {}
    repo_documents: dict[str, Any] = {}
    hashed_paths: set[str] = set()
    hashed_manifest_bytes = 0

    def enqueue_repo(path_value: Any, role: str) -> str:
        relative = _safe_relative_path(path_value, f"Repository {role} path")
        repo_roles.setdefault(relative, set()).add(role)
        if relative not in repo_records and relative not in repo_queue:
            repo_queue.append(relative)
        return relative

    def read_required_repo(relative: str, label: str) -> Any:
        nonlocal hashed_manifest_bytes
        path = _safe_join(root, relative, label)
        if not path.is_file():
            raise RuntimeSnapshotError(f"Required repository JSON is missing: {relative}")
        data, _stat = _stable_small_file(path, relative)
        path_key = os.path.normcase(str(path))
        if path_key not in hashed_paths:
            hashed_paths.add(path_key)
            hashed_manifest_bytes += len(data)
        document = _parse_json(data, relative)
        repo_records[relative] = {
            "path": relative,
            "state": "file",
            "bytes": len(data),
            "content_sha256": hashlib.sha256(data).hexdigest(),
        }
        repo_documents[relative] = document
        return document

    index_relative = enqueue_repo("regions/index.json", "catalog")
    index = read_required_repo(index_relative, "Region catalog")
    if not isinstance(index, Mapping):
        raise RuntimeSnapshotError("Region catalog must be a JSON object")
    indexed_regions = tuple(str(value).strip().lower() for value in index.get("regions") or ())
    if normalized_region_id not in indexed_regions:
        raise RuntimeSnapshotError(
            f"Region is not in the public catalog: {normalized_region_id}"
        )

    region_relative = enqueue_repo(
        f"regions/{normalized_region_id}/region.json",
        "region",
    )
    region = read_required_repo(region_relative, "Region manifest")
    if (
        not isinstance(region, Mapping)
        or str(region.get("region_id") or "").strip().lower() != normalized_region_id
    ):
        raise RuntimeSnapshotError("Region manifest identity mismatch")
    database_only = "context_runtime_manifest" in region
    roots = {
        provider: _normalized_root(provider, root, environment)
        for provider in (("repo",) if database_only else sorted(_SUPPORTED_PROVIDERS))
    }
    for role, linked_path in _repo_linked_paths(region):
        enqueue_repo(linked_path, role)
    if region.get("analysis_runtime_manifest") is not None:
        enqueue_repo(f"regions/{normalized_region_id}/region-profile.json", "runtime_source_selection")

    references: dict[tuple[str, str], _ProviderReference] = {}
    asset_requests: set[_AssetManifestRequest] = set()
    processed_repo: set[str] = {index_relative, region_relative}
    position = 0
    while position < len(repo_queue):
        relative = repo_queue[position]
        position += 1
        if relative in processed_repo:
            continue
        processed_repo.add(relative)
        path = _safe_join(root, relative, "Linked repository manifest")
        if not path.is_file():
            repo_records[relative] = {"path": relative, "state": "missing"}
            continue
        data, _stat = _stable_small_file(path, relative)
        path_key = os.path.normcase(str(path))
        if path_key not in hashed_paths:
            hashed_paths.add(path_key)
            hashed_manifest_bytes += len(data)
        try:
            document = _parse_json(data, relative)
        except RuntimeSnapshotError:
            repo_records[relative] = {
                "path": relative,
                "state": "invalid_json",
                "bytes": len(data),
                "content_sha256": hashlib.sha256(data).hexdigest(),
            }
            continue
        repo_records[relative] = {
            "path": relative,
            "state": "file",
            "bytes": len(data),
            "content_sha256": hashlib.sha256(data).hexdigest(),
        }
        repo_documents[relative] = document
        if isinstance(document, Mapping) and document.get("extends") is not None:
            enqueue_repo(document["extends"], f"extends:{relative}")

    postgis_records = []
    overlay = None
    migrated_source_ids = frozenset()
    overlay_relative = region.get("analysis_runtime_manifest")
    if overlay_relative is not None:
        from .catalogs import apply_analysis_runtime_overlay, validate_analysis_runtime_selection
        from .contracts import PostgisSourceReferenceContract
        from .sources import clear_postgis_runtime_cache, probe_postgis_runtime_revisions
        expected_overlay = f"regions/{normalized_region_id}/analysis-runtime.json"
        if overlay_relative != expected_overlay or expected_overlay not in repo_documents:
            raise RuntimeSnapshotError("Declared analysis runtime binding is unavailable")
        overlay = repo_documents[expected_overlay]
        validate_analysis_runtime_selection(overlay, normalized_region_id, repository_root=root)
        migrated_source_ids = frozenset(overlay["sources"])
        references_to_probe = tuple(PostgisSourceReferenceContract(**entry["postgis_reference"])
                                    for entry in overlay["sources"].values())
        try:
            postgis_records.extend(
                probe_postgis_runtime_revisions(references_to_probe, environ=environment)
            )
        except ValueError:
            clear_postgis_runtime_cache()
            # A failed live probe is a changed readiness input, never a
            # substitute for the strict revision/source/domain reader.
            postgis_records.extend({
                "region_id": reference.region_id,
                "database_schema": reference.database_schema,
                "revision_sha256": reference.revision_sha256,
                "source_id": reference.source_id,
                "domain_id": reference.domain_id,
                "state": "unavailable_revision",
            } for reference in references_to_probe)

    if database_only:
        if overlay is None or root != repo_root().resolve():
            raise RuntimeSnapshotError("Database readiness requires the active repository and GIS bindings")
        from .context_runtime import clear_context_runtime_cache, load_catalog_context_declarations
        from .postgis_context_inputs import probe_regional_context_revision
        from .sources import _postgis_database_url

        declarations = load_catalog_context_declarations(normalized_region_id)
        try:
            context_record = probe_regional_context_revision(
                _postgis_database_url(declarations.manifest.connection_alias, environment),
                declarations.manifest.binding, expected_scope=declarations.manifest.scope)
        except ValueError:
            clear_context_runtime_cache()
            # Include configuration failure in the token, without exposing
            # connection values or changing the actual context read contract.
            binding = declarations.manifest.binding
            context_record = {
                "region_id": binding.region_id,
                "database_schema": binding.database_schema,
                "revision_sha256": binding.revision_sha256,
                "analysis_revision_sha256": declarations.manifest.scope.analysis_revision_sha256,
                "domain_id": declarations.manifest.scope.support_domain.domain_id,
                "state": "unavailable_revision",
            }
        repository_payload = []
        for relative in sorted(repo_records):
            record = dict(repo_records[relative])
            record["roles"] = sorted(repo_roles.get(relative, ()))
            repository_payload.append(record)
        payload = {
            "schema_version": RUNTIME_SNAPSHOT_SCHEMA_VERSION,
            "region_id": normalized_region_id,
            "storage": "regional_postgis",
            "repository_manifests": repository_payload,
            "postgis_revisions": postgis_records,
            "regional_context": context_record,
            "current_context_contracts": declarations.fingerprint,
        }
        return RuntimeReadinessSnapshot(
            region_id=normalized_region_id, token_sha256=_canonical_sha256(payload),
            provider_root_states=(("repo", roots["repo"].state),),
            repository_manifest_count=len(repository_payload), provider_path_count=0,
            runtime_marker_count=0, hashed_manifest_bytes=hashed_manifest_bytes)

    def active_storage_document(value):
        if isinstance(value, Mapping):
            result = dict(value)
            if result.get("id") in migrated_source_ids and isinstance(result.get("asset"), Mapping):
                result.pop("asset")
            if result.get("layer_id") in migrated_source_ids and "provider" in result and "path" in result:
                # Old support CSVs remain signed import evidence, not runtime.
                result.pop("provider")
                result.pop("path")
            return {key: active_storage_document(child) for key, child in result.items()}
        if isinstance(value, list):
            return [active_storage_document(child) for child in value]
        return value

    for relative, document in sorted(repo_documents.items()):
        if overlay is not None:
            if isinstance(document, Mapping) and document.get("analysis_id") and isinstance(document.get("layers"), list) and document.get("region_id") == normalized_region_id:
                document = apply_analysis_runtime_overlay(dict(document), overlay)
            document = active_storage_document(document)
        _collect_provider_references(
            document,
            origin_file=relative,
            pointer="",
            references=references,
            asset_requests=asset_requests,
        )
        _collect_diagnostic_snapshot_references(
            document,
            origin_file=relative,
            references=references,
            migrated_source_ids=migrated_source_ids,
        )

    small_provider_files: dict[tuple[str, str], tuple[bytes, dict[str, int]]] = {}
    for request in sorted(
        asset_requests,
        key=lambda item: (item.provider, item.path, item.layer_id, item.origin),
    ):
        candidate, state = _resolve_provider_path(roots, request.provider, request.path)
        if candidate is None or state != "resolved" or not candidate.is_file():
            continue
        data, stat = _stable_small_file(
            candidate,
            f"{request.provider}:{request.path}",
        )
        small_provider_files[(request.provider, request.path)] = (data, stat)
        path_key = os.path.normcase(str(candidate))
        if path_key not in hashed_paths:
            hashed_paths.add(path_key)
            hashed_manifest_bytes += len(data)
        rows = _asset_manifest_rows(data, request.path)
        matches = [row for row in rows if str(row.get("layer_id") or "") == request.layer_id]
        if len(matches) > 1:
            raise RuntimeSnapshotError(
                f"Asset manifest contains duplicate layer_id: {request.layer_id}"
            )
        if not matches:
            continue
        row = matches[0]
        geojson_path = row.get("geojson_path")
        if geojson_path:
            _add_provider_reference(
                references,
                request.provider,
                geojson_path,
                role="source_geometry",
                origin=f"{request.provider}:{request.path}#{request.layer_id}",
                declaration=row,
            )
        if request.distance_provider is None and row.get("distance_path"):
            _add_provider_reference(
                references,
                request.provider,
                row["distance_path"],
                role="distance_observations",
                origin=f"{request.provider}:{request.path}#{request.layer_id}",
                declaration=row,
            )

    provider_records: list[dict[str, Any]] = []
    for key in sorted(references):
        reference = references[key]
        candidate, resolution_state = _resolve_provider_path(
            roots,
            reference.provider,
            reference.path,
        )
        record: dict[str, Any] = {
            "provider": reference.provider,
            "path": reference.path,
            "roles": sorted(reference.roles),
            "origins": sorted(reference.origins),
            "declarations": sorted(reference.declarations),
        }
        if candidate is None:
            record["state"] = resolution_state
        else:
            record.update(_file_state(candidate))
            should_hash = (
                any(
                    role in {"asset_manifest", "diagnostic_metadata"}
                    for role in reference.roles
                )
            )
            if should_hash and candidate.is_file():
                cached = small_provider_files.get(key)
                if cached is None:
                    cached = _stable_small_file(
                        candidate,
                        f"{reference.provider}:{reference.path}",
                    )
                    small_provider_files[key] = cached
                data, stable_stat = cached
                record["stat"] = stable_stat
                record["manifest_bytes"] = len(data)
                record["manifest_sha256"] = hashlib.sha256(data).hexdigest()
                path_key = os.path.normcase(str(candidate))
                if path_key not in hashed_paths:
                    hashed_paths.add(path_key)
                    hashed_manifest_bytes += len(data)
        provider_records.append(record)

    marker_records: list[dict[str, Any]] = []
    for provider in ("v2_archive", "generated_runtime"):
        provider_root = roots[provider]
        for role, marker_path in _runtime_marker_candidates(
            provider_root,
            normalized_region_id,
        ):
            _reject_reparse_point(marker_path, f"{provider}:{role}")
            marker_record: dict[str, Any] = {
                "provider": provider,
                "role": role,
            }
            marker_record.update(_file_state(marker_path))
            if marker_path.is_file():
                data, stat = _stable_small_file(marker_path, f"{provider}:{role}")
                marker_record.update(
                    {
                        "state": "file",
                        "stat": stat,
                        "bytes": len(data),
                        "content_sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
                path_key = os.path.normcase(str(marker_path.resolve()))
                if path_key not in hashed_paths:
                    hashed_paths.add(path_key)
                    hashed_manifest_bytes += len(data)
            marker_records.append(marker_record)

    repository_payload = []
    for relative in sorted(repo_records):
        record = dict(repo_records[relative])
        record["roles"] = sorted(repo_roles.get(relative, ()))
        repository_payload.append(record)
    payload = {
        "schema_version": RUNTIME_SNAPSHOT_SCHEMA_VERSION,
        "region_id": normalized_region_id,
        "provider_roots": [roots[key].payload() for key in sorted(roots)],
        "repository_manifests": repository_payload,
        "provider_paths": provider_records,
        "runtime_markers": marker_records,
    }
    if postgis_records:
        payload["postgis_revisions"] = sorted(postgis_records, key=lambda item: (item["region_id"], item["revision_sha256"]))
    token = _canonical_sha256(payload)
    return RuntimeReadinessSnapshot(
        region_id=normalized_region_id,
        token_sha256=token,
        provider_root_states=tuple(
            (key, roots[key].state) for key in sorted(roots)
        ),
        repository_manifest_count=len(repository_payload),
        provider_path_count=len(provider_records),
        runtime_marker_count=len(marker_records),
        hashed_manifest_bytes=hashed_manifest_bytes,
    )


def runtime_readiness_snapshot_token(
    region_id: str,
    *,
    repository_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Return the SHA-256 cache key for one region's readiness inputs."""

    return build_runtime_readiness_snapshot(
        region_id,
        repository_root=repository_root,
        environ=environ,
    ).token_sha256


__all__ = [
    "MAX_SMALL_MANIFEST_BYTES",
    "RUNTIME_SNAPSHOT_SCHEMA_VERSION",
    "RuntimeReadinessSnapshot",
    "RuntimeSnapshotError",
    "build_runtime_readiness_snapshot",
    "runtime_readiness_snapshot_token",
]
