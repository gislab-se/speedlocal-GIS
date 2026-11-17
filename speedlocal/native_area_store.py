"""Optional disk reuse of exact initial-area results after live input validation.

This is derived-result storage, never an alternative GIS input provider. The
workspace owns current authorization before calling here. Input/contract errors
propagate; only unusable stored artifacts and failed writes become cache misses.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from functools import lru_cache
import hashlib
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import re
import time

from .area_result import AreaCellResult, TechnologyAreaResult
from .catalogs import load_region
from .paths import repo_root
from .sources import (
    _current_postgis_operation, _postgis_database_url, eligible_surface_contract_for_analysis,
    read_analysis_domain_input, resolve_eligible_surface_cell_areas_km2,
)
from .startup_parameters import load_workspace_start_parameters
from .validation import validate_contract, validate_layer

ROOT_ENV = "SPEEDLOCAL_NATIVE_AREA_CACHE_ROOT"
MAX_ENTRY_BYTES = 2 * 1024 * 1024
MAX_AGE_SECONDS = 24 * 60 * 60
SCHEMA = "native-initial-area-1"
_NAME = re.compile(r"[a-z][a-z0-9_]{0,62}")


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _sha(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


@lru_cache(maxsize=1)
def _implementation_identity():
    import pyproj
    import shapely

    root = repo_root()
    paths = [*sorted((root / "speedlocal").glob("*.py")),
             root / "requirements.txt", root / "requirements-linux.lock"]
    return _sha({
        "source": {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in paths},
        "python": platform.python_version(), "platform": platform.platform(),
        "packages": {name: version(name) for name in ("numpy", "shapely", "pyproj", "h3")},
        "geos": shapely.geos_version_string, "proj": pyproj.proj_version_str,
        "proj_database": hashlib.sha256((Path(pyproj.datadir.get_data_dir()) / "proj.db").read_bytes()).hexdigest(),
    })


def initial_distances_match(contract, request):
    values = load_workspace_start_parameters(contract)
    return bool(values) and {group.group_id: group.parameter_map()
                             for group in request.groups} == {
        group: {"buffer_m": value} for group, value in values.items()
    }


def validated_input_key(contract, request):
    """Read actual validated sources and base surfaces before checking the store.

    The normal PostGIS operation/30-second source refresh remains authoritative.
    These bytes come from its complete reader, including current permissions,
    revision/content checks and live approved coverage, not metadata-only probes.
    """
    validate_contract(contract)
    sources = []
    connections = set()
    for layer_id in request.selected_layer_ids:
        layer = contract.layers[layer_id]
        # File/archive and unsupported source modes keep the original engine.
        reference = layer.source.postgis_reference
        if reference is None:
            return None
        validated = validate_layer(layer)
        assets = validated.assets
        connections.add(hashlib.sha256(_postgis_database_url(reference.connection_alias).encode()).hexdigest())
        sources.append((layer_id, assets.runtime_identity, assets.geojson_sha256,
                        assets.distance_sha256, assets.feature_count, validated.geometry_family))
    surface = eligible_surface_contract_for_analysis(contract)
    domain = read_analysis_domain_input(contract, "technology_support", int(surface.resolution),
                                      geometry_use="base_analysis")
    if not domain.runtime_revision_sha256:
        return None
    areas = resolve_eligible_surface_cell_areas_km2(contract, int(surface.resolution))
    return _sha({"schema": SCHEMA, "implementation": _implementation_identity(),
                 "request": request.as_dict(), "contract": asdict(contract),
                 "native_crs": load_region(contract.region_id)["native_crs"],
                 "connections": sorted(connections), "sources": sources,
                 "surface": [domain.payload_sha256, domain.runtime_revision_sha256,
                             domain.upstream_source_sha256],
                 "ordered_model_areas": [(cell, float(area).hex()) for cell, area in areas.items()]})


def _slot(folder, request):
    region, analysis = request.region_id, request.analysis_id
    if not _NAME.fullmatch(region) or analysis not in {"wind", "solar"}:
        raise ValueError("Invalid initial area store identity")
    load_region(region)  # Only current catalog regions can create slots.
    return folder / f"{region}-{analysis}.json"


def _decode(raw):
    if set(raw) != set(TechnologyAreaResult.__dataclass_fields__):
        raise ValueError("Stored native result fields differ")
    cells = []
    for cell in raw["cells"]:
        if set(cell) != set(AreaCellResult.__dataclass_fields__):
            raise ValueError("Stored native cell fields differ")
        for name in ("model_area_km2", "remaining_area_km2", "potential_pct"):
            if isinstance(cell[name], bool) or not isinstance(cell[name], (int, float)) or not math.isfinite(cell[name]):
                raise ValueError("Stored cell values must be finite numbers")
        if (not isinstance(cell["cell_id"], str) or not cell["cell_id"]
                or cell["model_area_km2"] <= 0 or cell["remaining_area_km2"] < 0
                or cell["remaining_area_km2"] > cell["model_area_km2"] + 1e-9
                or not 0 <= cell["potential_pct"] <= 100
                or not math.isclose(cell["potential_pct"],
                    cell["remaining_area_km2"] / cell["model_area_km2"] * 100,
                    rel_tol=0, abs_tol=1e-9)):
            raise ValueError("Stored cell area facts are invalid")
        cells.append(AreaCellResult(**cell))
    if not cells or len({cell.cell_id for cell in cells}) != len(cells):
        raise ValueError("Stored native cells must be nonempty and unique")
    for name, value in (("model_area_km2", math.fsum(cell.model_area_km2 for cell in cells)),
                        ("remaining_area_km2", math.fsum(cell.remaining_area_km2 for cell in cells))):
        if (isinstance(raw[name], bool) or not isinstance(raw[name], (int, float))
                or not math.isfinite(raw[name]) or float(raw[name]).hex() != value.hex()):
            raise ValueError("Stored native totals differ from exact cell totals")
    return TechnologyAreaResult(**{**raw, "cells": tuple(cells),
        "selected_layer_ids": tuple(raw["selected_layer_ids"]),
        "active_group_ids": tuple(raw["active_group_ids"])})


def read(folder, request, key):
    """Decode independent native cells; an expired/corrupt artifact is a miss."""
    path = _slot(folder, request)
    try:
        if path.is_symlink() or path.stat().st_size > MAX_ENTRY_BYTES:
            return None
        with path.open("rb") as stream:
            payload = stream.read(MAX_ENTRY_BYTES + 1)
        if len(payload) > MAX_ENTRY_BYTES:
            return None
        entry = json.loads(payload)
        if set(entry) != {"schema", "key", "created", "result_sha256", "result"}:
            return None
        age = time.time() - entry["created"]
        if entry["schema"] != SCHEMA or entry["key"] != key or not 0 <= age <= MAX_AGE_SECONDS:
            return None
        if _sha(entry["result"]) != entry["result_sha256"]:
            return None
        result = _decode(entry["result"])
        if (result.region_id != request.region_id or result.analysis_id != request.analysis_id
                or result.resolution != request.target_resolution
                or result.selected_layer_ids != request.selected_layer_ids):
            return None
        return result
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        return None


@contextmanager
def _writer_lock(path):
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def write(folder, request, key, result):
    """One fixed slot/temp/OS lock per region and technology; no growing index."""
    raw = asdict(result)
    payload = _encoded({"schema": SCHEMA, "key": key, "created": time.time(),
                        "result_sha256": _sha(raw), "result": raw})
    if len(payload) > MAX_ENTRY_BYTES:
        return False
    path = _slot(folder, request)
    temporary = path.with_suffix(".tmp")
    lock = path.with_suffix(".lock")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if any(p.is_symlink() for p in (folder, path, temporary, lock)):
            return False
        with _writer_lock(lock):
            with temporary.open("wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        return True
    except OSError:
        return False


def prepare(contract, request):
    """Return a current input-bound lookup context only for initial distances."""
    configured = os.environ.get(ROOT_ENV, "").strip()
    if (not configured or _current_postgis_operation() is None
            or not initial_distances_match(contract, request)):
        return None
    folder = Path(configured).expanduser()
    if folder.is_symlink():
        return None
    key = validated_input_key(contract, request)
    return (folder.resolve() / SCHEMA, key) if key is not None else None
