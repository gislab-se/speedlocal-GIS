from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping
from urllib.parse import urlencode


GENERATED_RUNTIME_ROOT_ENV = "SPEEDLOCAL_GENERATED_ROOT"
LOCAL_REVIEW_REGIONS_ENV = "SPEEDLOCAL_LOCAL_REVIEW_REGIONS"
REQUIRED_MATERIALIZATION_STATUS = "compiled_unvalidated"
REQUIRED_READINESS_FILE = "region-package.readiness.json"
DEFAULT_REVIEW_BASE_URL = "http://127.0.0.1:8502/"

_REGION_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class RegionPackageInstallError(ValueError):
    """A bounded, operator-facing catalog-install failure."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        expected: object | None = None,
        actual: object | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.expected = expected
        self.actual = actual
        super().__init__(f"{code}: {message}")

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "code": self.code,
            "message": self.message,
        }
        if self.expected is not None:
            result["expected"] = self.expected
        if self.actual is not None:
            result["actual"] = self.actual
        return result


@dataclass(frozen=True)
class RuntimeLaunchHandoff:
    """Values an operator may apply after installation; no process is mutated."""

    generated_root_env: str
    generated_root_value: str
    review_allowlist_env: str
    review_allowlist_value: str
    review_url: str
    review_access_enabled: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "environment": {
                self.generated_root_env: self.generated_root_value,
                self.review_allowlist_env: self.review_allowlist_value,
            },
            "review_url": self.review_url,
            "review_access_enabled": self.review_access_enabled,
            "action": (
                "Set the returned environment values explicitly, start the app "
                "separately, then open review_url. This installer does neither."
            ),
        }


@dataclass(frozen=True)
class RegionPackageInstallResult:
    region_id: str
    repository_root: Path
    catalog_root: Path
    package_root: Path
    index_path: Path
    schema_version: str
    default_region_id: str
    registered_region_ids: tuple[str, ...]
    changed: bool
    applied: bool
    handoff: RuntimeLaunchHandoff

    @property
    def mode(self) -> str:
        if not self.applied:
            return "dry_run"
        return "applied" if self.changed else "already_registered"

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "PASS",
            "mode": self.mode,
            "region_id": self.region_id,
            "repository_root": str(self.repository_root),
            "catalog_root": str(self.catalog_root),
            "package_root": str(self.package_root),
            "index_path": str(self.index_path),
            "catalog_schema_version": self.schema_version,
            "default_region_id": self.default_region_id,
            "registered_region_ids": list(self.registered_region_ids),
            "changed": self.changed,
            "applied": self.applied,
            "runtime_launch_handoff": self.handoff.as_dict(),
        }


def _fail(
    code: str,
    message: str,
    *,
    expected: object | None = None,
    actual: object | None = None,
) -> RegionPackageInstallError:
    return RegionPackageInstallError(
        code,
        message,
        expected=expected,
        actual=actual,
    )


def _read_json(path: Path, *, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise _fail(
            "RI-FILE-001",
            f"{label} does not exist.",
            expected="existing JSON file",
            actual=str(path),
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _fail(
            "RI-JSON-001",
            f"{label} is not readable JSON.",
            actual=f"{type(exc).__name__}: {exc}",
        ) from exc
    if not isinstance(value, dict):
        raise _fail(
            "RI-JSON-002",
            f"{label} must be a JSON object.",
            expected="object",
            actual=type(value).__name__,
        )
    return value


def _normalized_region_id(value: object, *, label: str) -> str:
    if not isinstance(value, str):
        raise _fail(
            "RI-ID-001",
            f"{label} must be a string.",
            actual=type(value).__name__,
        )
    normalized = value.strip().lower()
    if value != normalized or not _REGION_ID_PATTERN.fullmatch(normalized):
        raise _fail(
            "RI-ID-002",
            f"{label} must already be a normalized SpeedLocal region id.",
            expected="lowercase letters, digits and single underscores",
            actual=value,
        )
    return normalized


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_index(index: Mapping[str, Any]) -> tuple[str, str, tuple[str, ...]]:
    schema_version = index.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version.strip():
        raise _fail(
            "RI-INDEX-001",
            "Catalog schema_version must be a non-empty string.",
            actual=schema_version,
        )
    raw_regions = index.get("regions")
    if not isinstance(raw_regions, list):
        raise _fail(
            "RI-INDEX-002",
            "Catalog regions must be a list of normalized string ids.",
            actual=type(raw_regions).__name__,
        )
    region_ids = tuple(
        _normalized_region_id(value, label="Catalog region id")
        for value in raw_regions
    )
    if len(set(region_ids)) != len(region_ids):
        raise _fail(
            "RI-INDEX-003",
            "Catalog region ids must be unique after normalization.",
            actual=list(region_ids),
        )
    default_region_id = _normalized_region_id(
        index.get("default_region_id"),
        label="Catalog default_region_id",
    )
    if default_region_id not in region_ids:
        raise _fail(
            "RI-INDEX-004",
            "Catalog default_region_id must reference an indexed region.",
            expected=list(region_ids),
            actual=default_region_id,
        )
    return schema_version, default_region_id, region_ids


def _validate_roots(
    repository_root: Path,
    catalog_root: Path,
    package_root: Path,
    generated_root: Path,
) -> None:
    if not repository_root.is_dir():
        raise _fail(
            "RI-ROOT-001",
            "Repository root does not exist.",
            actual=str(repository_root),
        )
    expected_catalog = repository_root / "regions"
    if catalog_root != expected_catalog:
        raise _fail(
            "RI-ROOT-002",
            "Catalog root must be the explicit repository regions directory.",
            expected=str(expected_catalog),
            actual=str(catalog_root),
        )
    if not catalog_root.is_dir():
        raise _fail(
            "RI-ROOT-003",
            "Catalog root does not exist.",
            actual=str(catalog_root),
        )
    if package_root.parent != catalog_root or not package_root.is_dir():
        raise _fail(
            "RI-ROOT-004",
            "Package root must be an existing direct child of the catalog root.",
            expected=str(catalog_root / "<region_id>"),
            actual=str(package_root),
        )
    if not generated_root.is_dir():
        raise _fail(
            "RI-ROOT-005",
            "Generated runtime root does not exist.",
            actual=str(generated_root),
        )
    if _within(repository_root, generated_root):
        raise _fail(
            "RI-ROOT-006",
            "Generated runtime root must remain outside the repository.",
            expected="external directory",
            actual=str(generated_root),
        )


def _validate_manifest_integrity(
    package_root: Path,
    readiness: Mapping[str, Any],
) -> None:
    manifests = readiness.get("manifests")
    if not isinstance(manifests, dict) or not manifests:
        raise _fail(
            "RI-INTEGRITY-001",
            "Readiness must declare integrity for every materialized manifest.",
            expected="non-empty manifests object",
            actual=manifests,
        )
    package = package_root.resolve()
    recorded_paths = set(manifests)
    materialized_paths = {
        path.relative_to(package).as_posix()
        for path in package.rglob("*.json")
        if path.is_file()
        and path.name
        not in {REQUIRED_READINESS_FILE, "region-package.form.json"}
    }
    if recorded_paths != materialized_paths:
        raise _fail(
            "RI-INTEGRITY-007",
            "Readiness manifest evidence must cover every materialized manifest "
            "and no undeclared file.",
            expected=sorted(materialized_paths),
            actual=sorted(recorded_paths),
        )
    for relative_value, evidence in manifests.items():
        if (
            not isinstance(relative_value, str)
            or not relative_value
            or "\\" in relative_value
        ):
            raise _fail(
                "RI-INTEGRITY-002",
                "Readiness manifest paths must be non-empty POSIX paths.",
                actual=relative_value,
            )
        relative = Path(relative_value)
        target = (package / relative).resolve()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or not _within(package, target)
            or not target.is_file()
        ):
            raise _fail(
                "RI-INTEGRITY-003",
                "A readiness manifest path is missing or escapes the package.",
                expected=str(package / "<manifest>"),
                actual=str(target),
            )
        if not isinstance(evidence, dict):
            raise _fail(
                "RI-INTEGRITY-004",
                "Manifest integrity evidence must be an object.",
                actual=evidence,
            )
        expected_bytes = evidence.get("bytes")
        expected_sha256 = evidence.get("sha256")
        if (
            isinstance(expected_bytes, bool)
            or not isinstance(expected_bytes, int)
            or expected_bytes < 0
            or not isinstance(expected_sha256, str)
            or not _SHA256_PATTERN.fullmatch(expected_sha256)
        ):
            raise _fail(
                "RI-INTEGRITY-005",
                "Manifest integrity evidence has invalid bytes or SHA-256.",
                actual=evidence,
            )
        actual_bytes = target.stat().st_size
        actual_sha256 = _sha256(target)
        if actual_bytes != expected_bytes or actual_sha256 != expected_sha256:
            raise _fail(
                "RI-INTEGRITY-006",
                "A materialized manifest no longer matches readiness evidence.",
                expected={
                    "path": relative_value,
                    "bytes": expected_bytes,
                    "sha256": expected_sha256,
                },
                actual={
                    "path": relative_value,
                    "bytes": actual_bytes,
                    "sha256": actual_sha256,
                },
            )


def _validate_package(
    package_root: Path,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    region = _read_json(package_root / "region.json", label="Region manifest")
    region_id = _normalized_region_id(
        region.get("region_id"),
        label="Region manifest region_id",
    )
    if package_root.name != region_id:
        raise _fail(
            "RI-PACKAGE-001",
            "Package directory name and region manifest identity differ.",
            expected=package_root.name,
            actual=region_id,
        )

    landing_card = region.get("landing_card")
    if not isinstance(landing_card, dict) or landing_card.get("enabled") is not False:
        raise _fail(
            "RI-PUBLIC-001",
            "Catalog installation requires landing_card.enabled=false.",
            expected=False,
            actual=(landing_card or {}).get("enabled")
            if isinstance(landing_card, dict)
            else landing_card,
        )

    expected_readiness_reference = (
        f"regions/{region_id}/{REQUIRED_READINESS_FILE}"
    )
    if region.get("region_package_readiness") != expected_readiness_reference:
        raise _fail(
            "RI-READINESS-001",
            "Region manifest readiness reference is missing or non-canonical.",
            expected=expected_readiness_reference,
            actual=region.get("region_package_readiness"),
        )
    readiness = _read_json(
        package_root / REQUIRED_READINESS_FILE,
        label="Region-package readiness",
    )
    readiness_region_id = _normalized_region_id(
        readiness.get("region_id"),
        label="Readiness region_id",
    )
    if readiness_region_id != region_id:
        raise _fail(
            "RI-READINESS-002",
            "Readiness identity does not match the region package.",
            expected=region_id,
            actual=readiness_region_id,
        )
    if readiness.get("materialization_status") != REQUIRED_MATERIALIZATION_STATUS:
        raise _fail(
            "RI-READINESS-003",
            "Region package is not in the required materialized install state.",
            expected=REQUIRED_MATERIALIZATION_STATUS,
            actual=readiness.get("materialization_status"),
        )
    publication_gate = readiness.get("publication_gate")
    if (
        not isinstance(publication_gate, dict)
        or publication_gate.get("materialized_landing_card_enabled") is not False
        or publication_gate.get("state") != "not_validated"
    ):
        raise _fail(
            "RI-PUBLIC-002",
            "Readiness publication gate must remain closed during installation.",
            expected={
                "materialized_landing_card_enabled": False,
                "state": "not_validated",
            },
            actual=publication_gate,
        )
    _validate_manifest_integrity(package_root, readiness)
    return region_id, region, readiness


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def install_region_package(
    *,
    repository_root: Path,
    catalog_root: Path,
    package_root: Path,
    generated_root: Path,
    apply: bool = False,
    review_base_url: str = DEFAULT_REVIEW_BASE_URL,
) -> RegionPackageInstallResult:
    """Validate and optionally register one already materialized package.

    Dry-run is the default. Applying changes only ``regions/index.json`` and
    uses a same-directory atomic replacement. The function never changes the
    process environment and never starts or contacts the application.
    """

    repository = repository_root.resolve()
    catalog = catalog_root.resolve()
    package = package_root.resolve()
    generated = generated_root.resolve()
    _validate_roots(repository, catalog, package, generated)

    index_path = catalog / "index.json"
    index = _read_json(index_path, label="Region catalog index")
    schema_version, default_region_id, region_ids = _validate_index(index)
    region_id, region, _readiness = _validate_package(package)

    if region_id in region_ids:
        proposed_region_ids = region_ids
        changed = False
    else:
        proposed_region_ids = (*region_ids, region_id)
        changed = True
    proposed_index = dict(index)
    proposed_index["regions"] = list(proposed_region_ids)
    proposed_schema, proposed_default, validated_region_ids = _validate_index(
        proposed_index
    )
    if proposed_schema != schema_version or proposed_default != default_region_id:
        raise _fail(
            "RI-INDEX-005",
            "Installation may not change catalog schema_version or default_region_id.",
            expected={
                "schema_version": schema_version,
                "default_region_id": default_region_id,
            },
            actual={
                "schema_version": proposed_schema,
                "default_region_id": proposed_default,
            },
        )

    if apply and changed:
        try:
            _atomic_write_json(index_path, proposed_index)
        except OSError as exc:
            raise _fail(
                "RI-WRITE-001",
                "Atomic catalog index replacement failed; the original index "
                "remains authoritative.",
                actual=f"{type(exc).__name__}: {exc}",
            ) from exc

    review_access = region.get("review_access")
    review_enabled = (
        isinstance(review_access, dict)
        and review_access.get("enabled") is True
        and review_access.get("mode") == "review"
        and review_access.get("surface") == "shared_workspace"
    )
    query = urlencode({"region": region_id, "mode": "review"})
    separator = "&" if "?" in review_base_url else "?"
    review_url = f"{review_base_url}{separator}{query}"
    handoff = RuntimeLaunchHandoff(
        generated_root_env=GENERATED_RUNTIME_ROOT_ENV,
        generated_root_value=str(generated),
        review_allowlist_env=LOCAL_REVIEW_REGIONS_ENV,
        review_allowlist_value=region_id,
        review_url=review_url,
        review_access_enabled=review_enabled,
    )
    return RegionPackageInstallResult(
        region_id=region_id,
        repository_root=repository,
        catalog_root=catalog,
        package_root=package,
        index_path=index_path,
        schema_version=schema_version,
        default_region_id=default_region_id,
        registered_region_ids=validated_region_ids,
        changed=changed,
        applied=apply,
        handoff=handoff,
    )


__all__ = [
    "DEFAULT_REVIEW_BASE_URL",
    "GENERATED_RUNTIME_ROOT_ENV",
    "LOCAL_REVIEW_REGIONS_ENV",
    "REQUIRED_MATERIALIZATION_STATUS",
    "RegionPackageInstallError",
    "RegionPackageInstallResult",
    "RuntimeLaunchHandoff",
    "install_region_package",
]
