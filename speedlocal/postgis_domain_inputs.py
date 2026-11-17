"""Preserve declared domain geometry, display fields and original input seals.

Offline capture reads original inputs; runtime checks current repository contracts
and the existing Gate 1 evidence through its caller's database transaction.
No geometry repair, H3 generation or analytical area calculation is introduced.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, fields
from functools import lru_cache
import hashlib
import json
import math
import sys
from threading import RLock
from typing import Any

import h3
from shapely import from_wkb
from shapely.geometry import mapping

from .postgis_runtime import DomainCell, DomainCellsInput, RoadRuntimeInputs


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def capture_domain_display_metadata(payload: dict, level: Any, *, parent: bool) -> str:
    """Offline-only pure capture after the original artifact SHA is verified."""
    if payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError("Domain display requires a FeatureCollection")
    return canonical_json({
        "schema_version": "domain-display-1",
        "geometry_use": "declared_parent_display" if parent else "base_analysis_and_display",
        "level_contract_sha256": _sha(asdict(level)),
        "id_field": level.id_field,
        "area_field": level.area_field,
        "feature_collection_members": {k: v for k, v in payload.items() if k != "features"},
        "features": [{k: v for k, v in feature.items() if k != "geometry"}
                     for feature in payload["features"]],
        "area_only_rollups": {},
    })


def capture_area_only_rollups(domain: Any, levels_and_payloads: list[tuple[Any, dict]]) -> str:
    """Capture consumed legacy parent areas; do not import their unused geometry."""
    metadata = json.loads(domain.display_metadata_json)
    for level, payload in levels_and_payloads:
        metadata["area_only_rollups"][str(level.resolution)] = {
            "source_sha256": level.sha256,
            "level_contract_sha256": _sha(asdict(level)),
            "area_unit": level.area_unit,
            "rows": sorted([[feature["properties"][level.id_field], feature["properties"][level.area_field]]
                            for feature in payload["features"]]),
        }
    return canonical_json(metadata)


def _validate_area_only_rollups(domain: Any, rollups: Any) -> None:
    if not isinstance(rollups, dict) or (rollups and domain.role != "standard_result_surface"):
        raise ValueError("Area-only rollups require a standard-result surface")
    for key, value in rollups.items():
        if not key.isdigit() or str(int(key)) != key or not 0 <= int(key) < domain.resolution:
            raise ValueError("Area-only rollup has invalid parent resolution")
        if not isinstance(value, dict) or set(value) != {"source_sha256", "level_contract_sha256", "area_unit", "rows"}:
            raise ValueError("Area-only rollup has unsupported metadata")
        for field in ("source_sha256", "level_contract_sha256"):
            digest = value[field]
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Area-only rollup digest is invalid")
        if value['area_unit'] not in {'m2', 'km2'} or not isinstance(value['rows'], list):
            raise ValueError("Area-only rollup unit/rows are invalid")
        expected = {}
        for cell_id, area in domain.cell_areas_km2().items():
            parent = h3.cell_to_parent(cell_id, int(key))
            expected[parent] = expected.get(parent, 0.0) + area
        rows = value['rows']
        if any(not isinstance(row, list) or len(row) != 2 for row in rows):
            raise ValueError("Area-only rollup row is invalid")
        if [row[0] for row in rows] != sorted(expected):
            raise ValueError("Area-only rollup does not contain the exact parent IDs once")
        divisor = 1_000_000.0 if value['area_unit'] == 'm2' else 1.0
        for cell_id, area in rows:
            if (isinstance(area, bool) or not isinstance(area, (int, float)) or not math.isfinite(area)
                    or area <= 0 or not math.isclose(area / divisor, expected[cell_id], rel_tol=0.0, abs_tol=1e-6)):
                raise ValueError("Area-only rollup differs from the original base-area sum")


def validate_domain_display_metadata(domain: Any) -> dict | None:
    """Validate optional metadata without changing legacy empty-metadata inputs."""
    text = domain.display_metadata_json
    if not text:
        return None
    payload = json.loads(text)
    expected = {"schema_version", "geometry_use", "level_contract_sha256", "id_field",
                "area_field", "feature_collection_members", "features", "area_only_rollups"}
    if not isinstance(payload, dict) or (set(payload) - set(_ORIGINAL_METADATA_ROLES) - {"coverage_geography"}) != expected or canonical_json(payload) != text:
        raise ValueError("Domain display metadata must have its exact canonical schema")
    if payload["schema_version"] != "domain-display-1" or payload["geometry_use"] not in {
        "base_analysis_and_display", "declared_parent_display",
    }:
        raise ValueError("Domain display metadata has unsupported semantics")
    _validate_area_only_rollups(domain, payload['area_only_rollups'])
    _validate_original_domain_metadata(domain, payload)
    _validate_coverage_metadata(domain, payload)
    digest = payload["level_contract_sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Domain display contract digest is invalid")
    id_field, area_field = payload["id_field"], payload["area_field"]
    if not all(isinstance(v, str) and v.strip() == v and v for v in (id_field, area_field)) or id_field == area_field:
        raise ValueError("Domain display ID/area field declarations are invalid")
    header = payload["feature_collection_members"]
    if not isinstance(header, dict) or header.get("type") != "FeatureCollection" or "features" in header:
        raise ValueError("Domain display header is invalid")
    if "crs" in header:
        from pyproj import CRS
        crs = header["crs"]
        if not isinstance(crs, dict) or crs.get("type") != "name" or not isinstance(crs.get("properties"), dict):
            raise ValueError("Domain display CRS is invalid")
        if not CRS.from_user_input(crs["properties"].get("name")).equals(CRS.from_epsg(4326), ignore_axis_order=True):
            raise ValueError("Domain display coordinates must remain WGS84")
    features = payload["features"]
    if not isinstance(features, list) or len(features) != len(domain.cells):
        raise ValueError("Domain display metadata lost source features")
    for feature, cell in zip(features, domain.cells):
        if not isinstance(feature, dict) or feature.get("type") != "Feature" or "geometry" in feature:
            raise ValueError("Domain display metadata cannot supply alternative geometry")
        props = feature.get("properties")
        if not isinstance(props, dict) or props.get(id_field) != cell.cell_id:
            raise ValueError("Domain display feature order/IDs disagree with stored domain")
        area = props.get(area_field)
        if isinstance(area, bool) or not isinstance(area, (int, float)) or not math.isfinite(area) or area != cell.area_value:
            raise ValueError("Domain display area differs from the stored area")
    return payload


@dataclass(frozen=True, slots=True)
class _DomainValidationReceipt:
    level_contract_sha256: str
    geometry_use: str
    original_metadata: tuple
    coverage: tuple | None

    def metadata(self) -> dict:
        # Runtime consumers need only these seals. No mutable decoded feature
        # tree escapes the cache, and offline capture keeps its fresh full dict.
        result = {"level_contract_sha256": self.level_contract_sha256,
                  "geometry_use": self.geometry_use}
        result.update((key, dict(value)) for key, value in self.original_metadata)
        if self.coverage is not None:
            result["coverage_geography"] = dict(self.coverage)
        return result


_DOMAIN_VALIDATION_MAX_ENTRIES = 8
_DOMAIN_VALIDATION_MAX_BYTES = 64 * 1024 * 1024
_domain_validation_cache: OrderedDict = OrderedDict()
_domain_validation_bytes = 0
_domain_validation_generation = 0
_domain_validation_lock = RLock()


def _validation_retained_bytes(value, seen=None) -> int:
    """Conservatively charge the exact immutable key/receipt object graph.

    Count shared values once within an entry but again across entries; include
    ordinary dataclass dictionaries. OrderedDict storage is charged separately.
    Unknown or mutable field types never enter this cache.
    """
    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    size = sys.getsizeof(value)
    if type(value) in (str, bytes, int, float, bool, type(None)):
        return size
    if type(value) is tuple:
        return size + sum(_validation_retained_bytes(item, seen) for item in value)
    if type(value) in (DomainCellsInput, DomainCell, _DomainValidationReceipt):
        namespace = getattr(value, "__dict__", None)
        if namespace is not None:
            size += sys.getsizeof(namespace)
            size += sum(_validation_retained_bytes(key, seen) for key in namespace)
        return size + sum(_validation_retained_bytes(getattr(value, item.name), seen)
                          for item in fields(value))
    raise TypeError("Domain validation reuse requires immutable typed input")


def _runtime_domain_metadata(domain: DomainCellsInput) -> dict | None:
    """Reuse only successful pure validation of exact immutable domain data.

    Current revision, contract, coverage binding and live database checks remain
    with the caller. Oversized entries still validate and simply bypass reuse.
    """
    global _domain_validation_bytes
    with _domain_validation_lock:
        entry = _domain_validation_cache.get(domain)
        if entry is not None:
            _domain_validation_cache.move_to_end(domain)
            return entry[0].metadata()
        generation = _domain_validation_generation
    payload = validate_domain_display_metadata(domain)
    if payload is None:
        return None
    receipt = _DomainValidationReceipt(
        payload["level_contract_sha256"], payload["geometry_use"],
        tuple((key, tuple(payload[key].items())) for key in _ORIGINAL_METADATA_ROLES
              if key in payload),
        tuple(payload["coverage_geography"].items()) if payload.get("coverage_geography") is not None else None,
    )
    charge = (_validation_retained_bytes((domain, receipt))
              + sys.getsizeof((receipt, 0)) + sys.getsizeof(0))
    with _domain_validation_lock:
        if (generation != _domain_validation_generation
                or charge + sys.getsizeof(OrderedDict()) > _DOMAIN_VALIDATION_MAX_BYTES):
            return receipt.metadata()
        previous = _domain_validation_cache.pop(domain, None)
        if previous is not None:
            _domain_validation_bytes -= previous[1]
        _domain_validation_cache[domain] = (receipt, charge)
        _domain_validation_bytes += charge
        while (_domain_validation_cache and
               (len(_domain_validation_cache) > _DOMAIN_VALIDATION_MAX_ENTRIES
                or _domain_validation_bytes + sys.getsizeof(_domain_validation_cache)
                > _DOMAIN_VALIDATION_MAX_BYTES)):
            _, removed = _domain_validation_cache.popitem(last=False)
            _domain_validation_bytes -= removed[1]
        if not _domain_validation_cache:
            _domain_validation_cache.clear()
    return receipt.metadata()


def standard_result_area_rollup(inputs: Any, binding: Any, contract: Any,
                               resolution: int) -> dict[str, float]:
    """Return original declared parent values, with their current level binding."""
    base = contract.standard_result_surface
    if base is None or isinstance(resolution, bool) or not isinstance(resolution, int):
        raise ValueError("Area-only rollup requires a declared standard-result surface")
    # This validates current region/revision, original base artifact and semantics.
    domain_payload(inputs, binding, contract, 'standard_result_surface', base.resolution)
    level = base.rollups.get(resolution)
    if level is None:
        raise ValueError("Undeclared standard-result area rollup")
    domain = inputs.domain(base.id, base.resolution)
    metadata = validate_domain_display_metadata(domain)
    value = metadata['area_only_rollups'].get(str(resolution))
    if (value is None or value['source_sha256'] != level.sha256
            or value['level_contract_sha256'] != _sha(asdict(level)) or value['area_unit'] != level.area_unit
            or len(value['rows']) != level.expected_cell_count):
        raise ValueError("Area-only rollup differs from the current declared artifact")
    divisor = 1_000_000.0 if value['area_unit'] == 'm2' else 1.0
    areas = {cell_id: area / divisor for cell_id, area in value['rows']}
    if not math.isclose(math.fsum(areas.values()), level.expected_total_area_km2, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError("Area-only rollup total differs from its declared total")
    return areas


@dataclass(frozen=True)
class DomainPayload:
    region_id: str
    domain_id: str
    role: str
    resolution: int
    runtime_revision_sha256: str
    upstream_source_sha256: str
    payload_sha256: str
    cell_ids_sha256: str
    cells_sha256: str
    geojson_bytes: bytes


@lru_cache(maxsize=4)
def _snapshot_revision(inputs: Any) -> str:
    # Frozen records contain tuples, immutable WKB bytes and metadata strings.
    # The value-key rejects mutable list/bytearray input instead of caching it.
    # Replacing any domain/source/observation creates a different cache key.
    return inputs.revision_sha256


def _operation_snapshot_revision(inputs: Any) -> str:
    """Avoid rehashing one already admitted immutable snapshot in an operation.

    The original value-key cache remains the first-admission authority and the
    fallback for offline or unregistered inputs. Current binding and domain
    checks still run in the caller; this slot holds no validation decision.
    """
    from .sources import _current_postgis_operation

    operation = _current_postgis_operation()
    if (operation is None or type(inputs) is not RoadRuntimeInputs
            or not any(saved[2] is inputs for saved in operation.snapshots.values())):
        return _snapshot_revision(inputs)
    if operation.snapshot_revision is not None and operation.snapshot_revision[0] is inputs:
        return operation.snapshot_revision[1]
    generation = operation.generation
    revision = _snapshot_revision(inputs)
    # A runtime clear may occur while the full admission is in progress. Never
    # publish its old result as reusable evidence in the new generation.
    if (_current_postgis_operation() is operation and operation.generation == generation
            and any(saved[2] is inputs for saved in operation.snapshots.values())):
        operation.snapshot_revision = (inputs, revision)
    return revision


def _current_domain_input(inputs: Any, binding: Any, contract: Any, role: str,
                   resolution: int, *, geometry_use: str = "display") -> tuple[Any, dict, str]:
    """Read one current declared level from an already verified typed snapshot.

The binding must come from the caller's current manifest. It is deliberately
explicit so offline parity fixtures cannot activate an implicit file fallback.
"""
    revision = _operation_snapshot_revision(inputs)
    if (binding.region_id != contract.region_id or inputs.region_id != contract.region_id
            or binding.revision_sha256 != revision):
        raise ValueError("Domain snapshot does not match the current region/revision")
    if isinstance(resolution, bool) or not isinstance(resolution, int):
        raise ValueError("Domain resolution must be an integer")
    if role == "standard_analysis":
        base, domain_id = contract.analysis_domain, "standard_analysis"
    elif role == "technology_support":
        if contract.area_result is None:
            raise ValueError("Analysis has no technology area contract")
        base = contract.eligible_surfaces[contract.area_result.eligible_surface_id]
        domain_id = base.support_domain_id
    elif role == "standard_result_surface":
        base = contract.standard_result_surface
        domain_id = base.id if base is not None else ""
    else:
        raise ValueError("Undeclared domain role")
    if base is None:
        raise ValueError("Analysis does not declare the requested domain")
    level = base if resolution == base.resolution else base.rollups.get(resolution)
    if level is None:
        raise ValueError("Analysis does not declare this domain resolution")
    try:
        domain = inputs.domain(domain_id, resolution)
    except StopIteration:
        raise ValueError("Pinned runtime lacks the declared domain level") from None
    if (domain.role != role or domain.source_sha256 != level.sha256
            or domain.area_unit != level.area_unit or len(domain.cells) != level.expected_cell_count):
        raise ValueError("Runtime domain differs from the current declared artifact")
    metadata = _runtime_domain_metadata(domain)
    if metadata is None or metadata["level_contract_sha256"] != _sha(asdict(level)):
        raise ValueError("Pinned runtime lacks matching display metadata")
    expected_use = "base_analysis_and_display" if resolution == base.resolution else "declared_parent_display"
    if metadata["geometry_use"] != expected_use:
        raise ValueError("Base and parent display geometries cannot exchange authority")
    if geometry_use not in {"display", "base_analysis"} or (geometry_use == "base_analysis" and resolution != base.resolution):
        raise ValueError("Exact geometry calculations require the declared base level")
    return domain, metadata, revision


@lru_cache(maxsize=8)
def _serialized_domain_payload(domain: DomainCellsInput) -> tuple[bytes, str, str, str]:
    # The caller validates the current contract/revision before every lookup.
    # A frozen domain key includes actual WKB, cell values and original metadata;
    # cache only immutable emitted bytes/digests, never the parent snapshot.
    metadata = json.loads(domain.display_metadata_json)
    payload = dict(metadata["feature_collection_members"])
    payload["features"] = [dict(feature, geometry=mapping(from_wkb(cell.geometry_wkb)))
                           for feature, cell in zip(metadata["features"], domain.cells)]
    blob = canonical_json(payload).encode("utf-8")
    return (blob, hashlib.sha256(blob).hexdigest(), domain.cell_ids_sha256,
            domain.cells_sha256)


def clear_domain_payload_cache() -> None:
    """Release derived immutable domain bytes through the shared runtime clear."""
    global _domain_validation_bytes, _domain_validation_generation
    _serialized_domain_payload.cache_clear()
    with _domain_validation_lock:
        _domain_validation_cache.clear()
        _domain_validation_bytes = 0
        _domain_validation_generation += 1


def domain_payload(inputs: Any, binding: Any, contract: Any, role: str,
                   resolution: int, *, geometry_use: str = "display") -> DomainPayload:
    domain, metadata, revision = _current_domain_input(
        inputs, binding, contract, role, resolution, geometry_use=geometry_use)
    blob, payload_sha, ids_sha, cells_sha = _serialized_domain_payload(domain)
    return DomainPayload(inputs.region_id, domain.domain_id, role, resolution,
                         revision, domain.source_sha256,
                         payload_sha, ids_sha, cells_sha, blob)


@dataclass(frozen=True)
class DomainDisplayPayload:
    """Exact consumed bytes with separately named original-file provenance.

    This small input value is shared by existing geometry consumers. It does
    not choose display geometry policy or replace current-contract validation.
    """

    region_id: str
    domain_id: str
    role: str
    resolution: int
    upstream_source_sha256: str
    payload_sha256: str
    runtime_revision_sha256: str
    geojson_bytes: bytes

    def __post_init__(self):
        import re
        if (any(not isinstance(value, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value) is None
                for value in (self.region_id, self.domain_id))
                or self.role not in {"standard_analysis", "technology_support", "standard_result_surface"}
                or isinstance(self.resolution, bool) or not isinstance(self.resolution, int)
                or not 0 <= self.resolution <= 15):
            raise ValueError("Domain payload identity is invalid")
        for digest in (self.upstream_source_sha256, self.payload_sha256):
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Domain payload checksum is invalid")
        revision = self.runtime_revision_sha256
        if (not isinstance(revision, str) or (revision and
                (len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision)))):
            raise ValueError("Domain payload runtime revision is invalid")
        if not revision and self.payload_sha256 != self.upstream_source_sha256:
            raise ValueError("File domain payload must retain its exact original bytes")
        if (not isinstance(self.geojson_bytes, bytes) or not self.geojson_bytes
                or hashlib.sha256(self.geojson_bytes).hexdigest() != self.payload_sha256):
            raise ValueError("Domain payload bytes differ from their consumed checksum")

    @property
    def feature_collection_json(self) -> str:
        return self.geojson_bytes.decode("utf-8")


"""Append to the existing domain input module; two explicit metadata artifacts."""

_ORIGINAL_METADATA_ROLES = {
    "regional_analysis_metadata": "standard_analysis",
    "support_observation_metadata": "technology_support",
}
_ORIGINAL_METADATA_KEYS = {
    "provider", "path", "sha256", "byte_count", "payload_json", "contract_sha256",
}


def _validate_original_domain_metadata(domain, display):
    for field, role in _ORIGINAL_METADATA_ROLES.items():
        if field not in display:
            continue
        value = display[field]
        if (domain.role != role or display["geometry_use"] != "base_analysis_and_display"
                or not isinstance(value, dict) or set(value) != _ORIGINAL_METADATA_KEYS):
            raise ValueError("Original input metadata has an unsupported role or schema")
        for name in ("provider", "path"):
            if not isinstance(value[name], str) or not value[name] or value[name] != value[name].strip():
                raise ValueError("Original input metadata provenance is invalid")
        for name in ("sha256", "contract_sha256"):
            digest = value[name]
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Original input metadata checksum is invalid")
        if (not isinstance(value["payload_json"], str)
                or type(value["byte_count"]) is not int or value["byte_count"] <= 0):
            raise ValueError("Original input metadata payload is invalid")
        blob = value["payload_json"].encode("utf-8")
        if len(blob) != value["byte_count"] or hashlib.sha256(blob).hexdigest() != value["sha256"]:
            raise ValueError("Original input metadata bytes differ from their original checksum")
        if not isinstance(json.loads(value["payload_json"]), dict):
            raise ValueError("Original input metadata must remain a JSON object")


def capture_original_domain_metadata(domain, field, *, provider, path, sha256, contract, blob):
    """Offline capture of exact original UTF-8 bytes, after semantic validation."""
    if field not in _ORIGINAL_METADATA_ROLES or not isinstance(blob, bytes):
        raise ValueError("Unsupported original metadata capture")
    display = validate_domain_display_metadata(domain)
    if display is None or field in display:
        raise ValueError("Original metadata requires one fresh declared base-domain slot")
    display[field] = {
        "provider": provider, "path": path, "sha256": sha256,
        "byte_count": len(blob), "payload_json": blob.decode("utf-8"),
        "contract_sha256": _sha(asdict(contract)),
    }
    _validate_original_domain_metadata(domain, display)
    return canonical_json(display)


def _original_domain_metadata_bytes(domain, display, field, *, provider, path, sha256, contract):
    value = display.get(field)
    if value is None:
        raise ValueError("Pinned runtime lacks required original metadata; file fallback is forbidden")
    if (value["provider"] != provider or value["path"] != path or value["sha256"] != sha256
            or value["contract_sha256"] != _sha(asdict(contract))):
        raise ValueError("Original metadata differs from the current declared contract")
    # Internal bytes/SHA/schema were verified by _current_domain_input.
    return value["payload_json"].encode("utf-8")


def regional_domain_metadata_bytes(inputs, binding, analysis, regional_domain):
    """Map a repo-declared regional domain to its exact canonical runtime domain."""
    if analysis.analysis_domain is None or regional_domain.artifacts != analysis.analysis_domain:
        raise ValueError("Regional geography alias does not bind this analysis domain")
    domain, display, _ = _current_domain_input(
        inputs, binding, analysis, "standard_analysis", analysis.analysis_domain.resolution,
        geometry_use="base_analysis")
    return _original_domain_metadata_bytes(
        domain, display, "regional_analysis_metadata", provider=regional_domain.metadata_provider,
        path=regional_domain.metadata_path, sha256=regional_domain.metadata_sha256, contract=regional_domain)


def support_observation_metadata_bytes(inputs, binding, analysis):
    """Read original observation metadata; existing source consumer checks all semantics."""
    if analysis.area_result is None:
        raise ValueError("Support metadata requires an area-result contract")
    surface = analysis.eligible_surfaces[analysis.area_result.eligible_surface_id]
    domain, display, _ = _current_domain_input(
        inputs, binding, analysis, "technology_support", surface.resolution,
        geometry_use="base_analysis")
    declared = surface.support_observations
    return _original_domain_metadata_bytes(
        domain, display, "support_observation_metadata", provider=declared.provider,
        path=declared.path, sha256=declared.sha256, contract=declared)


"""Existing Gate 1 approval and geometry evidence, bound to one support domain."""

_COVERAGE_KEYS = {
    "region_id", "coverage_geometry_id", "coverage_asset_contract_sha256",
    "gate_state", "review_commit", "automated_evidence_sha256",
    "owner_reviewed_at", "owner_review_note", "profile_sha256", "current_profile_sha256",
    "geography_sha256", "current_geography_sha256", "database_schema", "boundary_view",
    "analysis_surface_view", "boundary_geometry_sha256", "analysis_surface_geometry_sha256",
    "gate1_binding_sha256",
}


def _validate_coverage_metadata(domain, display):
    from datetime import datetime
    import re
    value = display.get("coverage_geography")
    if value is None:
        return
    if (domain.role != "technology_support" or display["geometry_use"] != "base_analysis_and_display"
            or not isinstance(value, dict) or set(value) != _COVERAGE_KEYS
            or value["gate_state"] != "localhost_approved"):
        raise ValueError("Coverage must reference an approved Gate 1 support-base geography")
    for field, data in value.items():
        if not isinstance(data, str) or not data:
            raise ValueError("Coverage evidence must contain nonempty original identity fields")
        if field.endswith("sha256") and re.fullmatch(r"[0-9a-f]{64}", data) is None:
            raise ValueError("Coverage evidence checksum is invalid")
    if re.fullmatch(r"[0-9a-f]{40}", value["review_commit"]) is None:
        raise ValueError("Coverage original review commit is invalid")
    for field in ("region_id", "coverage_geometry_id", "database_schema", "boundary_view", "analysis_surface_view"):
        if re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value[field]) is None:
            raise ValueError("Coverage evidence identifier is invalid")
    moment = datetime.fromisoformat(value["owner_reviewed_at"])
    if moment.tzinfo is None or moment.utcoffset() is None or not value["owner_review_note"].strip():
        raise ValueError("Coverage evidence has no original owner receipt")


def _coverage_asset(geography, coverage_id):
    from .gate1_geography import select_gate1_geography_binding
    binding = select_gate1_geography_binding(geography)
    asset = geography.geographies.get(coverage_id)
    exact_source_fields = ("provider", "path", "sha256", "format", "geometry_family",
                           "source_crs", "native_crs", "water_policy")
    if (asset is None or asset.role not in {"analysis_surface", "technology_target_surface"}
            or any(getattr(asset, key) != getattr(binding.analysis_surface, key) for key in exact_source_fields)):
        raise ValueError("Coverage geometry is not the exact current Gate 1 analysis surface or its declared alias")
    return asset, binding


def capture_coverage_geography_metadata(domain, analysis, review):
    """Offline only, after the existing full Gate 1 review has succeeded."""
    from .catalogs import load_region_geography
    from .gate1_geography import gate1_binding_evidence
    from .paths import repo_root
    from .region_profile import profile_path
    root = repo_root()
    surface = analysis.eligible_surfaces[analysis.area_result.eligible_surface_id]
    geography = load_region_geography(analysis.region_id)
    asset, binding = _coverage_asset(geography, surface.source.coverage_geometry_id)
    display = validate_domain_display_metadata(domain)
    if (display is None or "coverage_geography" in display or review.region_id != analysis.region_id
            or domain.domain_id != surface.support_domain_id or domain.resolution != surface.resolution
            or review.gate_state != "localhost_approved"):
        raise ValueError("Coverage capture requires the approved current region and a fresh support base")
    from .region_profile import load_region_profile
    profile = load_region_profile(root, analysis.region_id)
    if (hashlib.sha256(profile_path(root, analysis.region_id).read_bytes()).hexdigest() != review.current_profile_sha256
            or hashlib.sha256((root / profile.contracts["geography"]).read_bytes()).hexdigest() != review.current_geography_sha256):
        raise ValueError("Current profile/geography changed after full offline Gate 1 review")
    display["coverage_geography"] = {
        "region_id": review.region_id,
        "coverage_geometry_id": asset.id,
        "coverage_asset_contract_sha256": _sha(asdict(asset)),
        "gate_state": review.gate_state, "review_commit": review.review_commit,
        "automated_evidence_sha256": review.automated_evidence_sha256,
        "owner_reviewed_at": review.owner_reviewed_at.isoformat(),
        "owner_review_note": review.owner_review_note,
        "profile_sha256": review.profile_sha256, "current_profile_sha256": review.current_profile_sha256,
        "geography_sha256": review.geography_sha256, "current_geography_sha256": review.current_geography_sha256,
        "database_schema": review.database_schema, "boundary_view": review.boundary_view,
        "analysis_surface_view": review.analysis_surface_view,
        "boundary_geometry_sha256": review.boundary_geometry_sha256,
        "analysis_surface_geometry_sha256": review.analysis_surface_geometry_sha256,
        "gate1_binding_sha256": _sha(gate1_binding_evidence(binding)),
    }
    _validate_coverage_metadata(domain, display)
    return canonical_json(display)


def _coverage_current_binding(region_id, evidence):
    from .catalogs import load_region_geography
    from .gate1_geography import gate1_binding_evidence
    from .paths import repo_root
    from .region_profile import load_region_profile, profile_path
    root = repo_root()
    profile = load_region_profile(root, region_id)
    geography = load_region_geography(region_id)
    asset, binding = _coverage_asset(geography, evidence["coverage_geometry_id"])
    if (evidence["region_id"] != region_id or evidence["database_schema"] != profile.database_schema
            or evidence["boundary_view"] != profile.boundary_view
            or evidence["analysis_surface_view"] != profile.analysis_surface_view
            or _sha(asdict(asset)) != evidence["coverage_asset_contract_sha256"]
            or _sha(gate1_binding_evidence(binding)) != evidence["gate1_binding_sha256"]
            or hashlib.sha256(profile_path(root, region_id).read_bytes()).hexdigest() != evidence["current_profile_sha256"]
            or hashlib.sha256((root / profile.contracts["geography"]).read_bytes()).hexdigest() != evidence["current_geography_sha256"]):
        raise ValueError("Coverage differs from the current repo profile/geography or exact approved source")
    return profile, geography, binding


def validate_live_coverage_geography(cursor, region_id, evidence):
    """Recheck original receipt and live views in the caller's current transaction.

    The imported evidence identifies the existing approval; it cannot approve
    anything. The same live Gate 1 row and geometry evidence must still match.
    Offline import established ancestry and original-profile proof using the
    existing full reviewer. Runtime retains those digests and compares exact
    current repo profile/geography bytes, without executing Git or source I/O.
    """
    from .gate1_geography import AREA_BINDING_TOLERANCE_M2, gate1_binding_evidence
    from .gate1_review import (
        assert_gate1_approval_binding, _load_review_view, _assert_recorded_geometry_evidence,
        _load_geometry_relationship, _assert_recorded_relationship,
    )
    profile, geography, binding = _coverage_current_binding(region_id, evidence)
    cursor.execute("""
        select gate_state, profile_sha256, automated_evidence, owner_reviewed_at, owner_review_note
        from meta.region_delivery_gates where region_id = %s and gate_id = 1
    """, (region_id,))
    rows = cursor.fetchall()
    if len(rows) != 1:
        raise ValueError("Coverage requires exactly one existing Gate 1 approval")
    state, profile_sha, sealed, reviewed_at, note = rows[0]
    if not isinstance(sealed, dict):
        raise ValueError("Current Gate 1 evidence is invalid")
    commit, digest = assert_gate1_approval_binding(
        region_id=region_id, gate_state=state, automated_evidence=sealed,
        expected_review_commit=evidence["review_commit"], owner_reviewed_at=reviewed_at,
        owner_review_note=note)
    if (state != evidence["gate_state"] or profile_sha != evidence["profile_sha256"]
            or sealed.get("profile_sha256") != profile_sha
            or sealed.get("geography_sha256") != evidence["geography_sha256"]
            or commit != evidence["review_commit"] or digest != evidence["automated_evidence_sha256"]
            or reviewed_at.isoformat() != evidence["owner_reviewed_at"]
            or str(note).strip() != evidence["owner_review_note"]):
        raise ValueError("Original Gate 1 approval, owner receipt or sealed geography changed")
    assets = sealed.get("geographies")
    if (not isinstance(assets, dict) or assets.get("binding") != gate1_binding_evidence(binding)
            or assets.get("boundary_sha256") != binding.identity.sha256
            or assets.get("analysis_surface_sha256") != binding.analysis_surface.sha256
            or assets.get("analysis_surface_water_policy") != binding.analysis_surface.water_policy):
        raise ValueError("Current Gate 1 geography binding differs from its original seal")
    native_epsg = int(geography.native_crs.removeprefix("EPSG:"))
    live = {}
    for key, view_name, expected_asset in (
        ("identity", profile.boundary_view, binding.identity),
        ("analysis_surface", profile.analysis_surface_view, binding.analysis_surface),
    ):
        row = _load_review_view(cursor, region_id=region_id, database_schema=profile.database_schema,
                                view_name=view_name, expected_asset=expected_asset, native_epsg=native_epsg)
        recorded = assets.get(key)
        if not isinstance(recorded, dict):
            raise ValueError("Current Gate 1 geometry has no original sealed evidence")
        _assert_recorded_geometry_evidence(region_id=region_id, evidence=recorded, live=row,
                                          expected_asset=expected_asset)
        field = "boundary_geometry_sha256" if key == "identity" else "analysis_surface_geometry_sha256"
        if row.geometry_sha256 != evidence[field]:
            raise ValueError("Coverage live geometry differs from the original imported Gate 1 evidence")
        live[key] = row
    outside, excluded, difference = _load_geometry_relationship(
        cursor, database_schema=profile.database_schema, boundary_view=profile.boundary_view,
        analysis_surface_view=profile.analysis_surface_view, native_epsg=native_epsg)
    relationship = sealed.get("geometry_relationship")
    if not isinstance(relationship, dict):
        raise ValueError("Current Gate 1 has no original geography relationship evidence")
    _assert_recorded_relationship(region_id=region_id, evidence=relationship,
                                 outside_m2=outside, excluded_m2=excluded, symmetric_difference_m2=difference)
    if (outside > AREA_BINDING_TOLERANCE_M2
            or (binding.identity_analysis_same_source and
                (live["identity"].geometry_sha256 != live["analysis_surface"].geometry_sha256
                 or difference > AREA_BINDING_TOLERANCE_M2))
            or (binding.positive_exclusion_required and excluded <= 1.0)):
        raise ValueError("Coverage no longer satisfies the approved Gate 1 geography relationship")


def validate_runtime_coverage_from_cursor(cursor, inputs):
    """One region, one transaction; old empty-metadata revisions stay unchanged."""
    for domain in inputs.domains:
        display = validate_domain_display_metadata(domain)
        if (display is not None and domain.role == "technology_support"
                and display["geometry_use"] == "base_analysis_and_display"):
            evidence = display.get("coverage_geography")
            if evidence is None:
                raise ValueError("Typed support runtime lacks its original approved coverage evidence")
            validate_live_coverage_geography(cursor, inputs.region_id, evidence)


def require_support_coverage(inputs, binding, analysis, support_domain):
    """Current source consumer checks its alias against the live-verified snapshot."""
    surface = analysis.eligible_surfaces[analysis.area_result.eligible_surface_id]
    domain, display, _ = _current_domain_input(inputs, binding, analysis, "technology_support",
                                               surface.resolution, geometry_use="base_analysis")
    evidence = display.get("coverage_geography")
    if (evidence is None or evidence["region_id"] != analysis.region_id
            or evidence["coverage_geometry_id"] != support_domain.coverage_geometry_id
            or surface.source.coverage_geometry_id != support_domain.coverage_geometry_id):
        raise ValueError("Support coverage does not bind the live-verified current declared geography")
    _coverage_current_binding(analysis.region_id, evidence)


def domain_cell_ids_sha256(inputs, binding, analysis, role, resolution):
    domain, _, _ = _current_domain_input(inputs, binding, analysis, role, resolution)
    return domain.cell_ids_sha256
