from __future__ import annotations

import json
import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from speedlocal.paths import provider_root, resolve_source_path


REGIONAL_LANDSCAPE_PIPELINE_ROOT_ENV = "REGIONAL_LANDSCAPE_PIPELINE_ROOT"
DEFAULT_REGIONAL_LANDSCAPE_PIPELINE_ROOT = Path(r"C:\gislab\regional-landscape-pipeline")
DELIVERY_REGION_KEYS = {
    "behavior_reference",
    "country",
    "data_status",
    "display_name",
    "landing_card",
    "review_access",
    "native_crs",
    "outside_lp_schematic",
    "readiness_requirements",
    "workspace_profile",
    "region_id",
    "runtime",
    "runtime_note",
    "status",
    "web_crs",
}

# The historical V2 archive still contains a landscape manifest used by the
# not-yet-migrated numerical potential chain.  It is compatibility input, not
# a workspace capability declaration.  Keep that distinction explicit and do
# not copy the archive reference into the merged public region manifest.
LEGACY_NUMERICAL_LANDSCAPE_CONTEXT_KEY = (
    "_legacy_numerical_landscape_manifest"
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def port_root() -> Path:
    return Path(__file__).resolve().parents[2]


def package_root() -> Path:
    return Path(__file__).resolve().parent


def manifests_root() -> Path:
    return package_root() / "manifests"


def regions_root() -> Path:
    return repo_root() / "regions"


def region_index_path() -> Path:
    return regions_root() / "index.json"


def _regional_landscape_pipeline_root() -> Path:
    return Path(
        os.environ.get(
            REGIONAL_LANDSCAPE_PIPELINE_ROOT_ENV,
            str(DEFAULT_REGIONAL_LANDSCAPE_PIPELINE_ROOT),
        )
    )


def v2_source_root() -> Path | None:
    try:
        return provider_root("v2_archive")
    except FileNotFoundError:
        return None


def _path_within(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def resolve_v2_source_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    try:
        candidate = resolve_source_path("v2_archive", str(path_value).strip())
    except (FileNotFoundError, ValueError):
        return None
    return candidate


def _expand_path_tokens(path_value: str) -> str:
    value = str(path_value).strip()
    token_values = [
        f"${{{REGIONAL_LANDSCAPE_PIPELINE_ROOT_ENV}}}",
        f"%{REGIONAL_LANDSCAPE_PIPELINE_ROOT_ENV}%",
    ]
    for token in token_values:
        if value == token or value.startswith(f"{token}/") or value.startswith(f"{token}\\"):
            suffix = value[len(token) :].lstrip("/\\")
            root = _regional_landscape_pipeline_root()
            return str(root / suffix) if suffix else str(root)
    return os.path.expandvars(value)


def resolve_repo_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path_value = _expand_path_tokens(path_value)
    path = Path(path_value)
    if path.is_absolute():
        return path
    repo_path = repo_root() / path
    if repo_path.exists():
        return repo_path
    port_path = port_root() / path
    if port_path.exists():
        return port_path
    source_path = resolve_v2_source_path(path_value)
    if source_path is not None:
        return source_path
    return repo_path


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


@lru_cache(maxsize=128)
def _read_manifest_revision(
    path_str: str,
    modified_ns: int,
    size_bytes: int,
) -> dict[str, Any]:
    del modified_ns, size_bytes
    return _read_json(Path(path_str))


def read_manifest(path_str: str) -> dict[str, Any]:
    path = Path(path_str).resolve()
    stat = path.stat()
    return _read_manifest_revision(
        str(path),
        int(stat.st_mtime_ns),
        int(stat.st_size),
    )


def _region_id_from_manifest_path(path: Path) -> str:
    if path.name == "region.json":
        return path.parent.name
    return path.stem


def _region_manifest_path_from_index(region_id: str) -> Path:
    return regions_root() / region_id / "region.json"


@lru_cache(maxsize=8)
def load_region_index() -> dict[str, Any]:
    index_path = region_index_path()
    if not index_path.exists():
        return {"regions": []}
    return _read_json(index_path).copy()


def default_region_id() -> str:
    index = load_region_index()
    value = str(index.get("default_region_id") or "").strip()
    if value:
        return value.lower()
    regions = index.get("regions") or []
    if regions:
        return str(regions[0]).strip().lower()
    raise ValueError(
        "Region index must declare default_region_id or at least one region"
    )


def _indexed_region_manifest_paths() -> list[Path]:
    index = load_region_index()
    region_ids = index.get("regions") or []
    paths: list[Path] = []
    for region_id in region_ids:
        path = _region_manifest_path_from_index(str(region_id))
        if path.exists():
            paths.append(path)
    return paths


def list_region_manifest_paths() -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for path in _indexed_region_manifest_paths():
        region_id = _region_id_from_manifest_path(path).lower()
        if region_id in seen:
            continue
        seen.add(region_id)
        paths.append(path)
    return paths


def _with_legacy_region_aliases(manifest: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "native_crs": ("crs", "native"),
        "web_crs": ("crs", "web"),
        "default_map_center": ("map", "default_center"),
        "default_zoom": ("map", "default_zoom"),
        "available_h3_resolutions": ("h3", "available_display_resolutions"),
        "default_h3_resolution": ("h3", "default_analysis_resolution"),
        "default_display_h3_resolution": ("h3", "default_display_resolution"),
        "h3_display_geometries": ("h3", "display_geometries"),
        "h3_display_geometry_counts": ("h3", "display_geometry_counts"),
    }
    for alias, (section_key, nested_key) in aliases.items():
        section = manifest.get(section_key)
        if alias not in manifest and isinstance(section, dict) and nested_key in section:
            manifest[alias] = section.get(nested_key)

    linked = manifest.get("manifests")
    if isinstance(linked, dict):
        linked_aliases = {
            "landscape_manifest": "landscape",
            "potential_manifest": "potential",
            "scenario_manifest": "scenarios",
            "social_acceptance_manifest": "social_acceptance",
            "acceptance_registry": "acceptance_registry",
            "layer_catalog": "layer_catalog",
        }
        for alias, linked_key in linked_aliases.items():
            if alias not in manifest and linked_key in linked:
                manifest[alias] = linked.get(linked_key)
    return manifest


def _load_region_manifest(path: Path) -> dict[str, Any]:
    manifest = read_manifest(str(path)).copy()
    manifest["_manifest_path"] = str(path)
    manifest["_region_package_dir"] = str(path.parent) if path.name == "region.json" else ""
    manifest = _with_legacy_region_aliases(manifest)
    # Delivery metadata and capability declarations are repository authority.
    # The archive remains available only to explicit historical readers below.
    manifest["_speedlocal_manifest_path"] = str(path)
    manifest["_metadata_authority"] = "repo_delivery"
    if "context_runtime_manifest" in manifest:
        binding_path = resolve_metadata_manifest_path(manifest["context_runtime_manifest"])
        if binding_path is None:
            raise ValueError("Declared context runtime requires a repository binding")
        binding_bytes = binding_path.read_bytes()
        binding = json.loads(binding_bytes)
        revision = binding.get("revision_sha256") if isinstance(binding, dict) else None
        if (not isinstance(binding, dict) or binding.get("region_id") != manifest.get("region_id")
                or not isinstance(revision, str) or len(revision) != 64
                or any(char not in "0123456789abcdef" for char in revision)):
            raise ValueError("Context runtime metadata identity/revision is invalid")
        # Existing Streamlit consumers hash this region dictionary. Read the
        # small binding on every invocation so a pin swap changes their keys.
        manifest["_context_runtime_revision_sha256"] = revision
        manifest["_context_runtime_manifest_sha256"] = hashlib.sha256(binding_bytes).hexdigest()
    return manifest


def load_legacy_numerical_landscape_manifest(
    region: dict[str, Any],
) -> dict[str, Any] | None:
    """Load the archived landscape input for legacy numerical consumers only.

    The reference is intentionally rediscovered from the archived region
    manifest instead of being attached to the merged public region object.
    This prevents it from becoming a canonical workspace.landscape fallback or
    appearing in the program's manifest/status presentation.
    """

    if region.get("_v2_source_available") is not True:
        return None
    region_id = str(region.get("region_id") or "").strip().lower()
    if not region_id:
        return None
    source_region_path = resolve_v2_source_path(
        f"regions/{region_id}/region.json"
    )
    if source_region_path is None or not source_region_path.is_file():
        return None
    source_region = _with_legacy_region_aliases(
        read_manifest(str(source_region_path)).copy()
    )
    if str(source_region.get("region_id") or "").strip().lower() != region_id:
        raise ValueError(
            "Archived numerical landscape region identity mismatch: "
            f"{source_region_path}"
        )
    manifest_value = source_region.get("landscape_manifest")
    if not isinstance(manifest_value, str) or not manifest_value.strip():
        return None
    manifest_path = resolve_v2_source_path(manifest_value)
    if manifest_path is None or not manifest_path.is_file():
        return None
    legacy_manifest = read_manifest(str(manifest_path)).copy()
    if str(legacy_manifest.get("region_id") or "").strip().lower() != region_id:
        raise ValueError(
            "Archived numerical landscape manifest identity mismatch: "
            f"{manifest_path}"
        )
    legacy_manifest["_manifest_path"] = str(manifest_path)
    legacy_manifest["_compatibility_role"] = "legacy_numerical_only"
    legacy_manifest["_source_provider"] = "v2_archive"
    return legacy_manifest


def list_regions() -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for path in list_region_manifest_paths():
        regions.append(_load_region_manifest(path))
    return regions


def load_region(region_id: str) -> dict[str, Any]:
    wanted = str(region_id).lower()
    for path in list_region_manifest_paths():
        if _region_id_from_manifest_path(path).lower() == wanted:
            return _load_region_manifest(path)
    package_path = _region_manifest_path_from_index(str(region_id))
    raise FileNotFoundError(f"Region manifest not found in SpeedLocal index: {package_path}")


def resolve_region_path(region: dict[str, Any], path_value: str | None) -> Path | None:
    if not path_value:
        return None
    expanded = _expand_path_tokens(path_value)
    path = Path(expanded)
    if any(key.endswith("_manifest") and path_value == value for key, value in region.items()):
        return resolve_metadata_manifest_path(path_value)
    if path.is_absolute():
        source_root = region.get("_v2_source_root")
        if source_root and not _path_within(Path(str(source_root)), path):
            return None
        return path
    source_root = region.get("_v2_source_root")
    if source_root:
        source_path = (Path(str(source_root)) / path).resolve()
        if _path_within(Path(str(source_root)), source_path):
            return source_path
    package_dir = region.get("_region_package_dir")
    if package_dir:
        package_path = Path(str(package_dir)) / path
        if package_path.exists():
            return package_path
    repo_path = repo_root() / path
    if repo_path.exists():
        return repo_path
    port_path = port_root() / path
    if port_path.exists():
        return port_path
    return repo_path


def resolve_metadata_manifest_path(reference: str | None) -> Path | None:
    """Resolve explicit small runtime metadata inside the repository only."""
    if reference is None:
        return None
    if (not isinstance(reference, str) or not reference or reference.strip() != reference
            or "\\" in reference or ":" in reference
            or any(part in {"", ".", ".."} for part in reference.split("/"))):
        raise ValueError("Runtime metadata requires an exact repository-relative path")
    path = Path(reference)
    root = repo_root().resolve()
    candidate = (root / path).resolve()
    if path.is_absolute() or candidate == root or not _path_within(root, candidate):
        raise ValueError("Runtime metadata escapes the repository")
    return candidate


def load_linked_manifest(region: dict[str, Any], key: str) -> dict[str, Any] | None:
    path = resolve_metadata_manifest_path(region.get(key))
    if path is None or not path.exists():
        return None
    raw = read_manifest(str(path))
    if not isinstance(raw, dict):
        raise ValueError("Runtime metadata must be a JSON object")
    manifest = raw.copy()
    manifest["_manifest_path"] = str(path)
    manifest["_authority"] = "repo_delivery"
    return manifest

