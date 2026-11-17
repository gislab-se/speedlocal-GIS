from __future__ import annotations

import csv
import hashlib
import json
import math
from numbers import Real
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
import struct
import tempfile
from typing import Any, Iterable, Iterator
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

import h3
import shapely
from pyproj import CRS, Transformer
from shapely.geometry import LineString, mapping, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree


SOURCE_CRS = CRS.from_user_input("OGC:CRS84")


@dataclass(frozen=True)
class ShapefileHeader:
    shape_type: int
    bbox: tuple[float, float, float, float]
    record_count: int


@dataclass(frozen=True)
class NormalizedRoadLayer:
    layer_id: str
    source_categories: tuple[str, ...]
    source_feature_count: int
    source_part_count: int
    dissolved_part_count: int
    source_length_m: float
    dissolved_length_m: float
    native_geometry: BaseGeometry
    geojson: dict[str, Any]


@dataclass(frozen=True)
class DomainCell:
    cell_id: str
    area_km2: float
    native_geometry: BaseGeometry


@dataclass(frozen=True)
class DistanceObservation:
    cell_id: str
    distance_m: float
    intersects: bool


@dataclass(frozen=True)
class RoadDiagnosticSourceEvidence:
    authority: str
    dataset_name: str
    delivery_name: str
    snapshot_timestamp: str
    license: str
    license_url: str
    terms_url: str
    license_status: str


@dataclass(frozen=True)
class RoadDiagnosticLayerEvidence:
    layer_id: str
    label: str
    source_categories: tuple[str, ...]
    source_feature_count: int
    dissolved_length_m: float
    observation_count: int
    intersecting_cell_count: int
    distance_rows_sha256: str
    distance_sha256: str


@dataclass(frozen=True)
class RoadDiagnosticLayer:
    evidence: RoadDiagnosticLayerEvidence
    source_feature_collection_json: str = field(repr=False)
    observations: tuple[DistanceObservation, ...] = field(repr=False)


@dataclass(frozen=True)
class RoadDiagnosticDomainCell:
    cell_id: str
    area_km2: float


@dataclass(frozen=True)
class RoadDiagnosticSnapshot:
    snapshot_id: str
    region_id: str
    classification: str
    accepted_public_reference: bool
    product_route_eligible: bool
    metadata_sha256: str
    source: RoadDiagnosticSourceEvidence
    domain_id: str
    resolution: int
    total_area_km2: float
    cells: tuple[RoadDiagnosticDomainCell, ...] = field(repr=False)
    layers: tuple[RoadDiagnosticLayer, ...] = field(repr=False)


@dataclass(frozen=True)
class RoadDiagnosticCellResult:
    cell_id: str
    min_distance_m: float
    any_intersection: bool
    blocked: bool
    area_km2: float


@dataclass(frozen=True)
class RoadDiagnosticSummary:
    cell_count: int
    blocked_cell_count: int
    remaining_cell_count: int
    total_area_km2: float
    blocked_area_km2: float
    remaining_area_km2: float
    blocked_cell_share: float
    remaining_cell_share: float
    blocked_area_share: float
    remaining_area_share: float
    blocked_cell_ids_sha256: str


@dataclass(frozen=True)
class RoadDiagnosticResult:
    snapshot_id: str
    region_id: str
    domain_id: str
    resolution: int
    selected_layer_ids: tuple[str, ...]
    buffer_m: float
    layer_evidence: tuple[RoadDiagnosticLayerEvidence, ...]
    summary: RoadDiagnosticSummary
    cells: tuple[RoadDiagnosticCellResult, ...] = field(repr=False)


def _tuple_of_type(value: Any, expected_type: type, label: str) -> tuple[Any, ...]:
    if not isinstance(value, tuple) or any(
        not isinstance(item, expected_type) for item in value
    ):
        raise ValueError(f"{label} must be an immutable typed tuple")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def id_set_sha256(cell_ids: Iterable[str]) -> str:
    payload = "".join(f"{cell_id}\n" for cell_id in sorted(cell_ids))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def snapshot_build_contract_signature(contract: dict[str, Any]) -> str:
    """Hash build semantics without the post-build metadata pin.

    The generated metadata SHA256 is deliberately excluded so a candidate can
    be built once and then pinned in the repo contract without a circular
    dependency between the contract file and its generated metadata.
    """

    normalized = json.loads(
        json.dumps(contract, ensure_ascii=False)
    )
    output = normalized.get("output")
    if not isinstance(output, dict):
        raise ValueError("Source snapshot output declaration is required")
    output.pop("artifact_status", None)
    output.pop("metadata_sha256", None)
    return canonical_sha256(normalized)


def _safe_identifier(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"[a-z][a-z0-9_]*", text) is None:
        raise ValueError(
            f"{label} must use lowercase ASCII letters, digits and underscores"
        )
    return text


def _safe_output_filename(value: Any, label: str, suffix: str) -> str:
    text = str(value or "").strip()
    if not text or "\\" in text:
        raise ValueError(f"{label} must be a single safe filename")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or len(path.parts) != 1
        or path.name in {".", ".."}
        or path.suffix != suffix
        or re.fullmatch(r"[a-z][a-z0-9_.-]*", path.name) is None
    ):
        raise ValueError(f"{label} must be a single safe {suffix} filename")
    return path.name


def _repo_outside_path(path: Path, repo_root_path: Path, label: str) -> None:
    resolved = path.expanduser().resolve()
    repository = repo_root_path.resolve()
    try:
        resolved.relative_to(repository)
    except ValueError:
        return
    raise ValueError(f"{label} must stay outside the Git workspace")


def _declared_source_files(contract: dict[str, Any]) -> list[dict[str, Any]]:
    inputs = contract["inputs"]
    result: list[dict[str, Any]] = []
    for role_prefix, input_name in (
        ("road_network", "road_network"),
        ("processed_v1_reference", "processed_v1_reference"),
    ):
        for item in inputs[input_name]["components"]:
            result.append(
                {
                    "role": f"{role_prefix}{item['extension']}",
                    "bytes": item["bytes"],
                    "sha256": item["sha256"],
                }
            )
    for role, input_name in (
        ("provenance_document", "provenance_document"),
        ("delivery_metadata", "delivery_metadata"),
    ):
        item = inputs[input_name]
        result.append(
            {
                "role": role,
                "bytes": item["bytes"],
                "sha256": item["sha256"],
            }
        )
    return result


def load_snapshot_contract(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Source-snapshot contract cannot be read: {path}") from exc
    return validate_snapshot_contract(value)


def validate_snapshot_contract(value: Any) -> dict[str, Any]:
    """Validate an already decoded diagnostic snapshot contract."""

    if not isinstance(value, dict):
        raise ValueError("Source-snapshot contract must be a JSON object")
    if value.get("schema_version") != "1.0":
        raise ValueError("Unsupported source-snapshot schema version")
    if value.get("classification") != "diagnostic_candidate_only":
        raise ValueError("Source snapshot must remain diagnostic_candidate_only")
    if value.get("accepted_public_reference") is not False:
        raise ValueError("Source snapshot must not claim an accepted public reference")
    if value.get("product_route_eligible") is not False:
        raise ValueError("Source snapshot must not be product-route eligible")
    _safe_identifier(value.get("snapshot_id"), "Source-snapshot id")
    _safe_identifier(value.get("region_id"), "Source-snapshot region id")
    layers = value.get("layers")
    if not isinstance(layers, dict) or not layers:
        raise ValueError("Source snapshot must declare at least one road layer")
    category_groups: list[tuple[str, ...]] = []
    for layer_id, item in layers.items():
        _safe_identifier(layer_id, "Road layer id")
        raw_categories = item.get("source_categories") if isinstance(item, dict) else None
        if (
            not isinstance(raw_categories, list)
            or not raw_categories
            or any(
                not isinstance(category, str) or not category.strip()
                for category in raw_categories
            )
            or len(raw_categories) != len(set(raw_categories))
        ):
            raise ValueError(
                "Each road layer must declare unique, non-empty source_categories"
            )
        if (
            item.get("geometry_family") != "line"
            or isinstance(item.get("expected_source_feature_count"), bool)
            or not isinstance(item.get("expected_source_feature_count"), int)
            or item["expected_source_feature_count"] <= 0
            or not str(item.get("processed_reference_category") or "").strip()
            or not str(item.get("derivation") or "").strip()
        ):
            raise ValueError(f"Road layer {layer_id!r} declaration is incomplete")
        category_groups.append(tuple(raw_categories))
    flattened_categories = [
        category for group in category_groups for category in group
    ]
    if len(flattened_categories) != len(set(flattened_categories)):
        raise ValueError("A source category must not belong to several road layers")
    domain = value.get("analysis_domain")
    if not isinstance(domain, dict):
        raise ValueError("Source snapshot must declare its diagnostic domain")
    resolution = domain.get("resolution")
    cell_count = domain.get("expected_cell_count")
    digest = str(domain.get("cell_ids_sha256") or "")
    if (
        not str(domain.get("domain_id") or "").strip()
        or domain.get("cell_kind") != "h3"
        or isinstance(resolution, bool)
        or not isinstance(resolution, int)
        or not 0 <= resolution <= 15
        or isinstance(cell_count, bool)
        or not isinstance(cell_count, int)
        or cell_count <= 0
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or domain.get("coverage_rule") != "positive_area_intersection"
    ):
        raise ValueError("Diagnostic H3 domain identity is invalid")
    required_properties = domain.get("required_feature_properties")
    if (
        not isinstance(required_properties, dict)
        or required_properties.get("domain_id") != domain.get("domain_id")
        or required_properties.get("source_h3_resolution") != resolution
        or required_properties.get("target_h3_resolution") != resolution
        or required_properties.get("coverage_rule") != domain.get("coverage_rule")
        or required_properties.get("geometry_status")
        != "analysis_domain_intersection"
    ):
        raise ValueError("Diagnostic H3 domain feature binding is incomplete")
    output = value.get("output")
    if not isinstance(output, dict):
        raise ValueError("Source snapshot output declaration is required")
    output_relative = str(output.get("relative_directory") or "")
    metadata_name = _safe_output_filename(
        output.get("metadata_name"),
        "Source-snapshot metadata_name",
        ".json",
    )
    artifact_status = output.get("artifact_status")
    metadata_sha256 = output.get("metadata_sha256")
    if artifact_status not in {"pending_build", "checksum_pinned"}:
        raise ValueError("Source-snapshot artifact_status is invalid")
    if artifact_status == "pending_build" and metadata_sha256 is not None:
        raise ValueError("Pending source-snapshot artifacts must not claim a SHA256")
    if artifact_status == "checksum_pinned":
        _lower_sha256(metadata_sha256)
    if (
        not output_relative
        or "\\" in output_relative
        or PurePosixPath(output_relative).is_absolute()
        or ".." in PurePosixPath(output_relative).parts
        or metadata_name != output.get("metadata_name")
        or not str(output.get("distance_semantics") or "").strip()
        or not str(output.get("intersection_semantics") or "").strip()
    ):
        raise ValueError("Source-snapshot output declaration is unsafe or incomplete")
    blockers = value.get("acceptance_blockers")
    if (
        not isinstance(blockers, list)
        or len(blockers) < 4
        or any(not isinstance(item, str) or not item.strip() for item in blockers)
    ):
        raise ValueError("Source snapshot acceptance blockers are incomplete")
    return value


def load_region_source_snapshot(
    region_id: str,
    snapshot_id: str,
) -> tuple[dict[str, Any], Path]:
    """Load one repo-confined diagnostic snapshot through its region pointer."""

    from .catalogs import load_region
    from .paths import repo_root

    region = load_region(region_id)
    pointers = region.get("diagnostic_source_snapshots")
    if not isinstance(pointers, dict):
        raise KeyError(
            f"Diagnostic source snapshots are not configured for {region_id}"
        )
    relative_value = pointers.get(snapshot_id)
    if not isinstance(relative_value, str) or not relative_value.strip():
        raise KeyError(
            f"Diagnostic source snapshot {snapshot_id!r} is not configured "
            f"for {region_id}"
        )
    if "\\" in relative_value:
        raise ValueError("Diagnostic source-snapshot path must use POSIX separators")
    relative = PurePosixPath(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Diagnostic source-snapshot path is not repo-confined")
    root = repo_root().resolve()
    path = root.joinpath(*relative.parts).resolve()
    if path == root or root not in path.parents:
        raise ValueError("Diagnostic source-snapshot path escapes the repository")
    if not path.is_file():
        raise FileNotFoundError(f"Diagnostic source snapshot is missing: {path}")
    contract = load_snapshot_contract(path)
    if contract.get("region_id") != region_id:
        raise ValueError("Diagnostic source-snapshot region identity mismatch")
    return contract, path


def source_root_from_argument(
    contract: dict[str, Any],
    explicit_root: Path | None,
) -> Path:
    environment_name = str(
        contract.get("source_root_environment_variable") or ""
    ).strip()
    if not environment_name:
        raise ValueError("Source-root environment-variable name is missing")
    configured = (
        str(explicit_root) if explicit_root is not None else os.environ.get(
            environment_name, ""
        )
    ).strip()
    if not configured:
        raise FileNotFoundError(
            f"Pass --source-root or configure {environment_name}; no default "
            "source catalog is allowed"
        )
    root = Path(configured).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    return root


def confined_file(root: Path, relative_value: Any) -> Path:
    if not isinstance(relative_value, str) or not relative_value.strip():
        raise ValueError("Source path must be a non-empty relative POSIX path")
    if "\\" in relative_value:
        raise ValueError(f"Backslashes are not allowed: {relative_value!r}")
    relative = PurePosixPath(relative_value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Source path is not confined: {relative_value!r}")
    candidate = root.joinpath(*relative.parts).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Source path escapes its explicit root: {relative_value}") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"Required source file is missing: {relative_value}")
    return candidate


def _lower_sha256(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"Invalid lowercase SHA256: {value!r}")
    return text


def _verified_file(path: Path, declaration: dict[str, Any]) -> None:
    expected_bytes = declaration.get("bytes")
    if isinstance(expected_bytes, bool) or not isinstance(expected_bytes, int):
        raise ValueError(f"Invalid declared byte size for {path.name}")
    actual_bytes = path.stat().st_size
    if actual_bytes != expected_bytes:
        raise ValueError(
            f"Source byte-size mismatch for {path.name}: "
            f"{actual_bytes} != {expected_bytes}"
        )
    expected_sha256 = _lower_sha256(declaration.get("sha256"))
    actual_sha256 = sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"Source checksum mismatch for {path.name}: "
            f"{actual_sha256} != {expected_sha256}"
        )


def _validate_provenance_docx(
    path: Path,
    declaration: dict[str, Any],
) -> None:
    word_namespace = (
        "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    )
    relationships_namespace = (
        "http://schemas.openxmlformats.org/package/2006/relationships"
    )
    try:
        with ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")
            relationships_xml = archive.read("word/_rels/document.xml.rels")
        document = ElementTree.fromstring(document_xml)
        relationships = ElementTree.fromstring(relationships_xml)
    except (
        BadZipFile,
        KeyError,
        OSError,
        ElementTree.ParseError,
    ) as exc:
        raise ValueError("Pinned provenance DOCX is unreadable") from exc

    paragraphs: list[str] = []
    for paragraph in document.findall(
        f".//{{{word_namespace}}}p"
    ):
        text = "".join(
            node.text or ""
            for node in paragraph.findall(
                f".//{{{word_namespace}}}t"
            )
        ).strip()
        if text:
            paragraphs.append(text)
    dataset_entry = str(declaration.get("dataset_entry") or "").strip()
    matching_indices = [
        index
        for index, text in enumerate(paragraphs)
        if text.endswith(dataset_entry)
    ]
    if len(matching_indices) != 1:
        raise ValueError("Pinned provenance DOCX dataset entry is not unique")
    start = matching_indices[0]
    expected_sequence = [
        dataset_entry,
        "Bornholm (Kommune 0400)",
        "ETRS89 / UTM zone 33N",
        "(EPSG:25833)",
        "GPKG",
        "06/12–2024",
        "23/05–2024",
        "CC BY 4.0 licens",
        "(Klimadatastyrelsen)",
        "Product Specification: Link",
    ]
    actual_sequence = paragraphs[start : start + len(expected_sequence)]
    if (
        len(actual_sequence) != len(expected_sequence)
        or not actual_sequence[0].endswith(expected_sequence[0])
        or actual_sequence[1:] != expected_sequence[1:]
    ):
        raise ValueError("Pinned provenance DOCX dataset semantics drifted")

    expected_date_values = {
        "access_date": "2024-12-06",
        "source_date": "2024-05-23",
        "native_crs": "EPSG:25833",
        "license": "CC BY 4.0",
    }
    if any(
        declaration.get(key) != expected
        for key, expected in expected_date_values.items()
    ):
        raise ValueError("Pinned provenance declaration disagrees with its DOCX row")
    relationship_targets = {
        str(node.attrib.get("Target") or "")
        for node in relationships.findall(
            f"{{{relationships_namespace}}}Relationship"
        )
    }
    if (
        declaration.get("license_url") not in relationship_targets
        or declaration.get("terms_url") not in relationship_targets
    ):
        raise ValueError("Pinned provenance DOCX links drifted")
def _shapefile_header(path: Path) -> ShapefileHeader:
    with path.open("rb") as handle:
        header = handle.read(100)
        if len(header) != 100:
            raise ValueError(f"Shapefile header is incomplete: {path}")
        if struct.unpack(">i", header[0:4])[0] != 9994:
            raise ValueError(f"Shapefile file code is invalid: {path}")
        declared_bytes = struct.unpack(">i", header[24:28])[0] * 2
        if declared_bytes != path.stat().st_size:
            raise ValueError(
                f"Shapefile length header does not match file size: {path}"
            )
        if struct.unpack("<i", header[28:32])[0] != 1000:
            raise ValueError(f"Shapefile version is invalid: {path}")
        shape_type = struct.unpack("<i", header[32:36])[0]
        bbox = struct.unpack("<4d", header[36:68])
        record_count = 0
        expected_record_number = 1
        while True:
            record_header = handle.read(8)
            if not record_header:
                break
            if len(record_header) != 8:
                raise ValueError(f"Truncated shapefile record header: {path}")
            record_number, word_length = struct.unpack(">2i", record_header)
            if record_number != expected_record_number or word_length < 2:
                raise ValueError(f"Invalid shapefile record {record_number}: {path}")
            content = handle.read(word_length * 2)
            if len(content) != word_length * 2:
                raise ValueError(f"Truncated shapefile record {record_number}: {path}")
            record_count += 1
            expected_record_number += 1
    return ShapefileHeader(
        shape_type=shape_type,
        bbox=tuple(float(value) for value in bbox),
        record_count=record_count,
    )


def _dbf_header(path: Path) -> tuple[int, int, list[tuple[str, str, int, int]]]:
    with path.open("rb") as handle:
        header = handle.read(32)
        if len(header) != 32:
            raise ValueError(f"DBF header is incomplete: {path}")
        record_count = struct.unpack("<I", header[4:8])[0]
        header_length = struct.unpack("<H", header[8:10])[0]
        record_length = struct.unpack("<H", header[10:12])[0]
        fields: list[tuple[str, str, int, int]] = []
        offset = 1
        while handle.tell() < header_length:
            descriptor = handle.read(32)
            if not descriptor:
                raise ValueError(f"DBF field table is truncated: {path}")
            if descriptor[0] == 0x0D:
                break
            name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
            field_type = chr(descriptor[11])
            length = int(descriptor[16])
            fields.append((name, field_type, offset, length))
            offset += length
        if offset != record_length:
            raise ValueError(f"DBF record layout does not match its header: {path}")
    return record_count, record_length, fields


def _dbf_text_values(
    path: Path,
    field_name: str,
    encoding: str,
) -> tuple[list[str], int]:
    record_count, record_length, fields = _dbf_header(path)
    matching = [field for field in fields if field[0] == field_name]
    if len(matching) != 1:
        raise ValueError(f"DBF must contain exactly one {field_name!r} field")
    _name, field_type, offset, length = matching[0]
    if field_type != "C":
        raise ValueError(f"DBF field {field_name!r} must be character data")
    values: list[str] = []
    with path.open("rb") as handle:
        header = handle.read(32)
        header_length = struct.unpack("<H", header[8:10])[0]
        handle.seek(header_length)
        for index in range(record_count):
            record = handle.read(record_length)
            if len(record) != record_length:
                raise ValueError(f"DBF record {index + 1} is truncated")
            if record[0:1] == b"*":
                raise ValueError(f"DBF record {index + 1} is marked deleted")
            if record[0:1] != b" ":
                raise ValueError(f"DBF record {index + 1} has an invalid status byte")
            value = record[offset : offset + length].rstrip(b" \0")
            values.append(value.decode(encoding).strip())
    return values, record_count


def _shx_record_count(path: Path) -> int:
    size = path.stat().st_size
    if size < 100 or (size - 100) % 8:
        raise ValueError(f"SHX length is invalid: {path}")
    with path.open("rb") as handle:
        header = handle.read(100)
        if len(header) != 100 or struct.unpack(">i", header[0:4])[0] != 9994:
            raise ValueError(f"SHX header is invalid: {path}")
        declared_bytes = struct.unpack(">i", header[24:28])[0] * 2
        if declared_bytes != size:
            raise ValueError(f"SHX length header does not match file size: {path}")
        if struct.unpack("<i", header[32:36])[0] != 13:
            raise ValueError(f"SHX shape type is not PolyLineZ: {path}")
    return (size - 100) // 8


def _polyline_records(path: Path) -> Iterator[tuple[BaseGeometry, int]]:
    with path.open("rb") as handle:
        handle.seek(100)
        expected_record_number = 1
        while True:
            record_header = handle.read(8)
            if not record_header:
                break
            if len(record_header) != 8:
                raise ValueError(f"Truncated shapefile record header: {path}")
            record_number, word_length = struct.unpack(">2i", record_header)
            if record_number != expected_record_number:
                raise ValueError(f"Unexpected shapefile record number: {record_number}")
            content = handle.read(word_length * 2)
            if len(content) != word_length * 2:
                raise ValueError(f"Truncated shapefile record {record_number}")
            shape_type = struct.unpack("<i", content[0:4])[0]
            if shape_type == 0:
                raise ValueError(f"Null road geometry at record {record_number}")
            if shape_type != 13:
                raise ValueError(
                    f"Road record {record_number} has shape type {shape_type}, expected 13"
                )
            if len(content) < 44:
                raise ValueError(f"Road record {record_number} is incomplete")
            part_count, point_count = struct.unpack("<2i", content[36:44])
            if part_count <= 0 or point_count < 2:
                raise ValueError(f"Road record {record_number} has no usable line")
            part_start = 44
            point_start = part_start + 4 * part_count
            xy_end = point_start + 16 * point_count
            if xy_end > len(content):
                raise ValueError(f"Road record {record_number} XY payload is truncated")
            part_indices = list(
                struct.unpack(
                    f"<{part_count}i",
                    content[part_start:point_start],
                )
            )
            if part_indices[0] != 0 or part_indices != sorted(set(part_indices)):
                raise ValueError(f"Road record {record_number} has invalid part indices")
            coordinates = [
                struct.unpack("<2d", content[offset : offset + 16])
                for offset in range(point_start, xy_end, 16)
            ]
            geometries: list[BaseGeometry] = []
            for part_index, first in enumerate(part_indices):
                last = (
                    part_indices[part_index + 1]
                    if part_index + 1 < part_count
                    else point_count
                )
                if last - first < 2:
                    raise ValueError(
                        f"Road record {record_number} contains a one-point part"
                    )
                geometry = LineString(coordinates[first:last])
                if geometry.is_empty or not geometry.is_valid:
                    raise ValueError(f"Road record {record_number} is invalid")
                geometries.append(geometry)
            record_geometry = (
                geometries[0]
                if len(geometries) == 1
                else unary_union(geometries)
            )
            yield record_geometry, len(geometries)
            expected_record_number += 1


def _line_parts(geometry: BaseGeometry) -> list[BaseGeometry]:
    if geometry.geom_type == "LineString":
        return [geometry]
    if geometry.geom_type in {"MultiLineString", "GeometryCollection"}:
        result: list[BaseGeometry] = []
        for part in geometry.geoms:
            result.extend(_line_parts(part))
        return result
    raise ValueError(f"Expected line geometry, got {geometry.geom_type}")


def validate_snapshot_inputs(
    contract: dict[str, Any],
    source_root: Path,
) -> dict[str, Any]:
    inputs = contract.get("inputs")
    road = inputs.get("road_network") if isinstance(inputs, dict) else None
    processed_reference = (
        inputs.get("processed_v1_reference") if isinstance(inputs, dict) else None
    )
    provenance_document = (
        inputs.get("provenance_document") if isinstance(inputs, dict) else None
    )
    metadata = inputs.get("delivery_metadata") if isinstance(inputs, dict) else None
    if (
        not isinstance(road, dict)
        or not isinstance(processed_reference, dict)
        or not isinstance(provenance_document, dict)
        or not isinstance(metadata, dict)
    ):
        raise ValueError(
            "Road-network, processed-reference, provenance-document and "
            "delivery-metadata inputs are required"
        )
    base_value = road.get("base_path")
    if not isinstance(base_value, str) or not base_value.strip():
        raise ValueError("Road-network base_path is required")
    components = road.get("components")
    if not isinstance(components, list):
        raise ValueError("Road-network components must be a list")
    expected_extensions = {".shp", ".shx", ".dbf", ".prj", ".cpg"}
    declared_extensions = {
        item.get("extension") for item in components if isinstance(item, dict)
    }
    if declared_extensions != expected_extensions or len(components) != len(
        expected_extensions
    ):
        raise ValueError("Road-network component set is incomplete or duplicated")
    paths: dict[str, Path] = {}
    for item in components:
        extension = str(item.get("extension") or "")
        path = confined_file(source_root, f"{base_value}{extension}")
        _verified_file(path, item)
        paths[extension] = path

    header = _shapefile_header(paths[".shp"])
    expected_bbox = road.get("expected_bbox")
    if (
        header.shape_type != road.get("shape_type")
        or header.record_count != road.get("expected_record_count")
        or not isinstance(expected_bbox, list)
        or len(expected_bbox) != 4
        or any(
            not math.isclose(actual, float(expected), rel_tol=0.0, abs_tol=1e-8)
            for actual, expected in zip(header.bbox, expected_bbox, strict=True)
        )
    ):
        raise ValueError("Road shapefile structure or bounds drifted")

    declared_crs = CRS.from_user_input(str(road.get("native_crs") or ""))
    source_crs = CRS.from_wkt(paths[".prj"].read_text(encoding="utf-8-sig"))
    if not source_crs.equals(declared_crs, ignore_axis_order=True):
        raise ValueError("Road shapefile CRS does not match the snapshot contract")
    encoding = paths[".cpg"].read_text(encoding="ascii").strip()
    if encoding.upper().replace("-", "") != "UTF8":
        raise ValueError(f"Unsupported road DBF encoding: {encoding!r}")
    categories, dbf_record_count = _dbf_text_values(
        paths[".dbf"],
        str(road.get("category_field") or ""),
        "utf-8",
    )
    shx_record_count = _shx_record_count(paths[".shx"])
    if (
        len(categories) != dbf_record_count
        or dbf_record_count != header.record_count
        or shx_record_count != header.record_count
        or header.record_count != road.get("expected_record_count")
    ):
        raise ValueError(
            "Road DBF, SHP and SHX record counts do not match the snapshot"
        )

    reference_base = processed_reference.get("base_path")
    if not isinstance(reference_base, str) or not reference_base.strip():
        raise ValueError("Processed V1 reference base_path is required")
    reference_components = processed_reference.get("components")
    if not isinstance(reference_components, list):
        raise ValueError("Processed V1 reference components must be a list")
    reference_extensions = {
        item.get("extension")
        for item in reference_components
        if isinstance(item, dict)
    }
    if (
        reference_extensions != expected_extensions
        or len(reference_components) != len(expected_extensions)
    ):
        raise ValueError(
            "Processed V1 reference component set is incomplete or duplicated"
        )
    reference_paths: dict[str, Path] = {}
    for item in reference_components:
        extension = str(item.get("extension") or "")
        path = confined_file(source_root, f"{reference_base}{extension}")
        _verified_file(path, item)
        reference_paths[extension] = path
    reference_header = _shapefile_header(reference_paths[".shp"])
    reference_categories, reference_dbf_count = _dbf_text_values(
        reference_paths[".dbf"],
        str(processed_reference.get("category_field") or ""),
        "utf-8",
    )
    reference_shx_count = _shx_record_count(reference_paths[".shx"])
    expected_reference_count = processed_reference.get("expected_record_count")
    if (
        reference_header.shape_type != processed_reference.get("shape_type")
        or reference_header.record_count != expected_reference_count
        or reference_dbf_count != expected_reference_count
        or reference_shx_count != expected_reference_count
        or len(reference_categories) != expected_reference_count
        or len(reference_categories) != len(set(reference_categories))
    ):
        raise ValueError("Processed V1 reference structure or categories drifted")
    reference_crs = CRS.from_wkt(
        reference_paths[".prj"].read_text(encoding="utf-8-sig")
    )
    if not reference_crs.equals(declared_crs, ignore_axis_order=True):
        raise ValueError("Processed V1 reference CRS drifted")
    reference_encoding = reference_paths[".cpg"].read_text(
        encoding="ascii"
    ).strip()
    if reference_encoding.upper().replace("-", "") != "UTF8":
        raise ValueError("Processed V1 reference DBF encoding drifted")
    reference_records = list(_polyline_records(reference_paths[".shp"]))
    if len(reference_records) != expected_reference_count:
        raise ValueError("Processed V1 reference geometry count drifted")
    reference_geometries = {
        category: geometry
        for (geometry, _part_count), category in zip(
            reference_records,
            reference_categories,
            strict=True,
        )
    }
    expected_reference_categories = {
        str(item.get("processed_reference_category") or "")
        for item in contract["layers"].values()
    }
    if set(reference_geometries) != expected_reference_categories:
        raise ValueError("Processed V1 reference layer labels drifted")

    provenance_path = confined_file(source_root, provenance_document.get("path"))
    _verified_file(provenance_path, provenance_document)
    _validate_provenance_docx(provenance_path, provenance_document)
    identity = contract.get("source_identity")
    expected_provenance = {
        "native_crs": identity.get("native_crs") if isinstance(identity, dict) else None,
        "license": identity.get("license") if isinstance(identity, dict) else None,
        "license_url": identity.get("license_url") if isinstance(identity, dict) else None,
        "terms_url": identity.get("terms_url") if isinstance(identity, dict) else None,
        "verification_status": (
            identity.get("license_status") if isinstance(identity, dict) else None
        ),
    }
    if (
        provenance_document.get("format") != "docx"
        or provenance_document.get("dataset_entry")
        != "GeoDanmark60_GPKG_HF_Bornholm-0400_25833"
        or provenance_document.get("access_date") != "2024-12-06"
        or provenance_document.get("source_date") != "2024-05-23"
        or any(
            provenance_document.get(key) != expected
            for key, expected in expected_provenance.items()
        )
    ):
        raise ValueError("Pinned GeoDanmark provenance semantics drifted")
    actual_counts = dict(sorted(Counter(categories).items()))
    expected_counts = road.get("expected_category_counts")
    if actual_counts != expected_counts:
        raise ValueError(
            "Road category counts drifted: "
            f"expected {expected_counts!r}, got {actual_counts!r}"
        )

    metadata_path = confined_file(source_root, metadata.get("path"))
    _verified_file(metadata_path, metadata)
    try:
        metadata_payload = json.loads(
            metadata_path.read_text(encoding="utf-8-sig")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("GeoDanmark delivery metadata is unreadable") from exc
    if not isinstance(metadata_payload, dict):
        raise ValueError("GeoDanmark delivery metadata must be a JSON object")
    public_fields = metadata.get("required_public_fields")
    if not isinstance(public_fields, dict) or any(
        metadata_payload.get(key) != expected
        for key, expected in public_fields.items()
    ):
        raise ValueError("GeoDanmark delivery metadata identity drifted")

    return {
        "paths": paths,
        "reference_paths": reference_paths,
        "reference_geometries": reference_geometries,
        "provenance_path": provenance_path,
        "metadata_path": metadata_path,
        "metadata_public_fields": dict(public_fields),
        "categories": categories,
        "category_counts": actual_counts,
        "header": header,
        "native_crs": declared_crs,
    }


def build_normalized_road_layers(
    contract: dict[str, Any],
    validated_inputs: dict[str, Any],
) -> dict[str, NormalizedRoadLayer]:
    layers = contract["layers"]
    categories = validated_inputs["categories"]
    selected_categories = {
        str(source_category): layer_id
        for layer_id, item in layers.items()
        for source_category in item["source_categories"]
    }
    source_geometries: dict[str, list[BaseGeometry]] = {
        layer_id: [] for layer_id in layers
    }
    source_part_counts = {layer_id: 0 for layer_id in layers}
    record_count = 0
    for record_count, ((geometry, part_count), category) in enumerate(
        zip(
            _polyline_records(validated_inputs["paths"][".shp"]),
            categories,
            strict=True,
        ),
        start=1,
    ):
        layer_id = selected_categories.get(category)
        if layer_id is not None:
            source_geometries[layer_id].append(geometry)
            source_part_counts[layer_id] += part_count
    if record_count != len(categories):
        raise ValueError("Road SHP and DBF iteration did not remain aligned")

    to_web = Transformer.from_crs(
        validated_inputs["native_crs"],
        SOURCE_CRS,
        always_xy=True,
    )
    normalized: dict[str, NormalizedRoadLayer] = {}
    for layer_id, declaration in layers.items():
        geometries = source_geometries[layer_id]
        expected_count = declaration.get("expected_source_feature_count")
        if len(geometries) != expected_count:
            raise ValueError(
                f"{layer_id} source count {len(geometries)} != {expected_count}"
            )
        dissolved = unary_union(geometries)
        parts = _line_parts(dissolved)
        if not parts or dissolved.is_empty or not dissolved.is_valid:
            raise ValueError(f"{layer_id} did not produce a valid line union")
        reference_category = str(declaration["processed_reference_category"])
        reference_geometry = validated_inputs["reference_geometries"].get(
            reference_category
        )
        if reference_geometry is None:
            raise ValueError(
                f"{layer_id} has no processed reference {reference_category!r}"
            )
        if (
            not dissolved.equals(reference_geometry)
            or float(dissolved.difference(reference_geometry).length) != 0.0
            or float(reference_geometry.difference(dissolved).length) != 0.0
            or float(dissolved.hausdorff_distance(reference_geometry)) != 0.0
        ):
            raise ValueError(
                f"{layer_id} raw-class union does not reproduce the processed V1 geometry"
            )
        source_length_m = math.fsum(float(item.length) for item in geometries)
        dissolved_length_m = float(dissolved.length)
        web_geometry = transform(to_web.transform, dissolved)
        if web_geometry.is_empty or not web_geometry.is_valid:
            raise ValueError(f"{layer_id} could not be normalized to CRS84")
        source_categories = tuple(
            str(value) for value in declaration["source_categories"]
        )
        properties = {
            "layer_id": layer_id,
            "source_categories": list(source_categories),
            "source_feature_count": len(geometries),
            "processed_reference_category": reference_category,
            "processed_reference_equivalent": True,
            "derivation": declaration["derivation"],
            "source_snapshot_id": contract["snapshot_id"],
        }
        geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": mapping(web_geometry),
                }
            ],
        }
        normalized[layer_id] = NormalizedRoadLayer(
            layer_id=layer_id,
            source_categories=source_categories,
            source_feature_count=len(geometries),
            source_part_count=source_part_counts[layer_id],
            dissolved_part_count=len(parts),
            source_length_m=source_length_m,
            dissolved_length_m=dissolved_length_m,
            native_geometry=dissolved,
            geojson=geojson,
        )
    return normalized


def _metadata_level(metadata: dict[str, Any], resolution: int) -> dict[str, Any]:
    levels = metadata.get("levels")
    if not isinstance(levels, list):
        raise ValueError("Analysis-domain metadata has no levels list")
    matching = [
        item
        for item in levels
        if isinstance(item, dict) and item.get("resolution") == resolution
    ]
    if len(matching) != 1:
        raise ValueError(
            f"Analysis-domain metadata must declare exactly one R{resolution} level"
        )
    return matching[0]


def load_verified_domain_cells(
    contract: dict[str, Any],
    *,
    generated_root: Path,
    metadata_path: Path,
    geojson_path: Path,
    expected_metadata_sha256: str,
    expected_geojson_sha256: str,
) -> tuple[list[DomainCell], dict[str, Any]]:
    root = generated_root.resolve()
    for label, path in (
        ("metadata", metadata_path.resolve()),
        ("GeoJSON", geojson_path.resolve()),
    ):
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"Analysis-domain {label} must stay within --generated-root"
            ) from exc
        if not path.is_file():
            raise FileNotFoundError(f"Analysis-domain {label} is missing: {path}")
    if sha256_file(metadata_path) != _lower_sha256(expected_metadata_sha256):
        raise ValueError(
            "Analysis-domain metadata checksum does not match the repo "
            "geography contract"
        )
    if sha256_file(geojson_path) != _lower_sha256(expected_geojson_sha256):
        raise ValueError(
            "Analysis-domain R9 checksum does not match the repo geography "
            "contract"
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Analysis-domain metadata is unreadable") from exc
    if not isinstance(metadata, dict):
        raise ValueError("Analysis-domain metadata must be a JSON object")
    domain = contract["analysis_domain"]
    resolution = int(domain["resolution"])
    if (
        metadata.get("domain_id") != domain["domain_id"]
        or metadata.get("coverage_rule") != domain["coverage_rule"]
        or metadata.get("source_h3_resolution") != resolution
    ):
        raise ValueError("Analysis-domain metadata identity drifted")
    level = _metadata_level(metadata, resolution)
    expected_sha256 = _lower_sha256(level.get("sha256"))
    actual_sha256 = sha256_file(geojson_path)
    level_digest = level.get("id_digest", level.get("cell_ids_sha256"))
    level_relative = _safe_generated_relative_path(
        level.get("path"),
        "Analysis-domain R9 metadata path",
    )
    declared_geojson_path = root.joinpath(*level_relative.parts).resolve()
    if (
        level.get("cell_count") != domain["expected_cell_count"]
        or level_digest != domain["cell_ids_sha256"]
        or level.get("bytes") != geojson_path.stat().st_size
        or actual_sha256 != expected_sha256
        or declared_geojson_path != geojson_path.resolve()
    ):
        raise ValueError("Analysis-domain R9 metadata does not match its artifact")
    try:
        payload = json.loads(geojson_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Analysis-domain GeoJSON is unreadable") from exc
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError("Analysis-domain GeoJSON must be a FeatureCollection")
    crs_declaration = payload.get("crs")
    if crs_declaration is not None:
        if (
            not isinstance(crs_declaration, dict)
            or crs_declaration.get("type") != "name"
            or not isinstance(crs_declaration.get("properties"), dict)
        ):
            raise ValueError("Analysis-domain GeoJSON CRS declaration is invalid")
        crs_name = crs_declaration["properties"].get("name")
        try:
            declared_source_crs = CRS.from_user_input(crs_name)
        except Exception as exc:
            raise ValueError(
                "Analysis-domain GeoJSON CRS declaration is unreadable"
            ) from exc
        if not declared_source_crs.equals(SOURCE_CRS, ignore_axis_order=True):
            raise ValueError("Analysis-domain GeoJSON must use CRS84/EPSG:4326")
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("Analysis-domain GeoJSON has no feature list")
    native_crs = CRS.from_user_input(contract["source_identity"]["native_crs"])
    to_native = Transformer.from_crs(SOURCE_CRS, native_crs, always_xy=True)
    required = domain.get("required_feature_properties")
    if not isinstance(required, dict):
        raise ValueError("Analysis-domain required properties are missing")
    cells: list[DomainCell] = []
    ids: list[str] = []
    seen_ids: set[str] = set()
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(f"Analysis-domain feature {index} is invalid")
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            raise ValueError(f"Analysis-domain feature {index} has no properties")
        cell_id = str(properties.get("hex_id") or "").strip()
        if not h3.is_valid_cell(cell_id) or h3.get_resolution(cell_id) != resolution:
            raise ValueError(f"Analysis-domain feature {index} has an invalid R9 id")
        if any(properties.get(key) != value for key, value in required.items()):
            raise ValueError(
                f"Analysis-domain cell {cell_id} has unexpected domain properties"
            )
        area_value = properties.get("area_km2")
        if isinstance(area_value, bool):
            raise ValueError(f"Analysis-domain cell {cell_id} has invalid area_km2")
        try:
            area_km2 = float(area_value)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"Analysis-domain cell {cell_id} has invalid area_km2"
            ) from exc
        if not math.isfinite(area_km2) or area_km2 <= 0.0:
            raise ValueError(f"Analysis-domain cell {cell_id} has invalid area_km2")
        if cell_id in seen_ids:
            raise ValueError(f"Analysis-domain cell {cell_id} is duplicated")
        geometry_value = feature.get("geometry")
        try:
            web_geometry = shape(geometry_value)
            native_geometry = transform(to_native.transform, web_geometry)
        except Exception as exc:
            raise ValueError(
                f"Analysis-domain cell {cell_id} has unreadable geometry"
            ) from exc
        if (
            native_geometry.is_empty
            or not native_geometry.is_valid
            or native_geometry.geom_type not in {"Polygon", "MultiPolygon"}
            or float(native_geometry.area) <= 0.0
        ):
            raise ValueError(f"Analysis-domain cell {cell_id} is not usable")
        ids.append(cell_id)
        seen_ids.add(cell_id)
        cells.append(
            DomainCell(
                cell_id=cell_id,
                area_km2=area_km2,
                native_geometry=native_geometry,
            )
        )
    if (
        len(cells) != domain["expected_cell_count"]
        or len(ids) != len(set(ids))
        or id_set_sha256(ids) != domain["cell_ids_sha256"]
    ):
        raise ValueError("Analysis-domain cell coverage is incomplete or drifted")
    cells.sort(key=lambda item: item.cell_id)
    evidence = {
        "domain_id": domain["domain_id"],
        "resolution": resolution,
        "cell_count": len(cells),
        "cell_ids_sha256": id_set_sha256(ids),
        "path": geojson_path.name,
        "bytes": geojson_path.stat().st_size,
        "sha256": actual_sha256,
        "metadata_path": metadata_path.name,
        "metadata_bytes": metadata_path.stat().st_size,
        "metadata_sha256": sha256_file(metadata_path),
    }
    return cells, evidence


def _safe_generated_relative_path(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        raise ValueError(f"{label} must be a non-empty relative POSIX path")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"{label} is not confined")
    return relative


def build_distance_observations(
    layer: NormalizedRoadLayer,
    cells: list[DomainCell],
) -> tuple[DistanceObservation, ...]:
    parts = _line_parts(layer.native_geometry)
    source_index = STRtree(parts)
    rows: list[DistanceObservation] = []
    for cell in cells:
        representative_point = cell.native_geometry.representative_point()
        nearest_index = int(source_index.nearest(representative_point))
        distance = float(representative_point.distance(parts[nearest_index]))
        if not math.isfinite(distance) or distance < 0.0:
            raise ValueError(f"{layer.layer_id} produced an invalid distance")
        intersects = bool(
            len(source_index.query(cell.native_geometry, predicate="intersects"))
        )
        rows.append(
            DistanceObservation(
                cell_id=cell.cell_id,
                distance_m=distance,
                intersects=intersects,
            )
        )
    return tuple(rows)


def format_distance(value: float) -> str:
    text = f"{value:.12f}".rstrip("0").rstrip(".")
    return text or "0"


def rows_sha256(rows: Iterable[DistanceObservation]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(
            (
                f"{row.cell_id},{format_distance(row.distance_m)},"
                f"{'true' if row.intersects else 'false'}\n"
            ).encode("utf-8")
        )
    return digest.hexdigest()


def _write_geojson(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )


def _write_distance_csv(
    path: Path,
    rows: tuple[DistanceObservation, ...],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(("hex_id", "distance_m", "intersects"))
        for row in rows:
            writer.writerow(
                (
                    row.cell_id,
                    format_distance(row.distance_m),
                    "true" if row.intersects else "false",
                )
            )


def build_road_source_snapshot(
    contract: dict[str, Any],
    *,
    contract_path: Path,
    source_root: Path,
    generated_root: Path,
    domain_metadata_path: Path,
    domain_geojson_path: Path,
    domain_metadata_sha256: str,
    domain_geojson_sha256: str,
    repo_root: Path,
    overwrite: bool = False,
) -> Path:
    root = generated_root.expanduser().resolve()
    workspace = repo_root.resolve()
    _repo_outside_path(root, workspace, "Generated source-snapshot artifacts")
    root.mkdir(parents=True, exist_ok=True)
    output = contract.get("output")
    if not isinstance(output, dict):
        raise ValueError("Source snapshot output contract is missing")
    relative_output = PurePosixPath(str(output.get("relative_directory") or ""))
    if relative_output.is_absolute() or ".." in relative_output.parts:
        raise ValueError("Source-snapshot output path is not confined")
    target = root.joinpath(*relative_output.parts).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Source-snapshot output escapes --generated-root") from exc

    validated_inputs = validate_snapshot_inputs(contract, source_root)
    normalized = build_normalized_road_layers(contract, validated_inputs)
    cells, domain_evidence = load_verified_domain_cells(
        contract,
        generated_root=root,
        metadata_path=domain_metadata_path.expanduser().resolve(),
        geojson_path=domain_geojson_path.expanduser().resolve(),
        expected_metadata_sha256=domain_metadata_sha256,
        expected_geojson_sha256=domain_geojson_sha256,
    )
    observations = {
        layer_id: build_distance_observations(layer, cells)
        for layer_id, layer in normalized.items()
    }

    expected_names = {
        *(f"{layer_id}.geojson" for layer_id in normalized),
        *(f"{layer_id}.csv" for layer_id in normalized),
        str(output["metadata_name"]),
    }
    if len(expected_names) != 2 * len(normalized) + 1:
        raise ValueError("Generated road-snapshot output filenames collide")
    existing = [target / name for name in expected_names if (target / name).exists()]
    if existing and not overwrite:
        raise FileExistsError(
            f"Output already exists: {existing[0]}. Pass --overwrite to replace it."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="speedlocal-road-source-snapshot-",
        dir=target.parent,
    ) as temporary:
        staging = Path(temporary)
        layer_metadata: list[dict[str, Any]] = []
        for layer_id in sorted(normalized):
            layer = normalized[layer_id]
            rows = observations[layer_id]
            geojson_path = staging / f"{layer_id}.geojson"
            csv_path = staging / f"{layer_id}.csv"
            _write_geojson(geojson_path, layer.geojson)
            _write_distance_csv(csv_path, rows)
            layer_metadata.append(
                {
                    "layer_id": layer_id,
                    "source_categories": list(layer.source_categories),
                    "source_feature_count": layer.source_feature_count,
                    "source_part_count": layer.source_part_count,
                    "dissolved_part_count": layer.dissolved_part_count,
                    "source_length_m": layer.source_length_m,
                    "dissolved_length_m": layer.dissolved_length_m,
                    "geojson_path": geojson_path.name,
                    "geojson_bytes": geojson_path.stat().st_size,
                    "geojson_sha256": sha256_file(geojson_path),
                    "distance_path": csv_path.name,
                    "distance_bytes": csv_path.stat().st_size,
                    "distance_sha256": sha256_file(csv_path),
                    "distance_rows_sha256": rows_sha256(rows),
                    "row_count": len(rows),
                    "cell_ids_sha256": id_set_sha256(row.cell_id for row in rows),
                    "intersecting_cell_count": sum(
                        int(row.intersects) for row in rows
                    ),
                }
            )
        source_files = _declared_source_files(contract)
        build_inputs = {
            "snapshot_id": contract["snapshot_id"],
            "contract_signature_sha256": snapshot_build_contract_signature(
                contract
            ),
            "source_files": source_files,
            "domain_sha256": domain_evidence["sha256"],
            "domain_cell_ids_sha256": domain_evidence["cell_ids_sha256"],
            "layers": [
                {
                    "layer_id": item["layer_id"],
                    "source_categories": item["source_categories"],
                    "source_feature_count": item["source_feature_count"],
                }
                for item in layer_metadata
            ],
        }
        metadata = {
            "schema_version": "1.0",
            "snapshot_id": contract["snapshot_id"],
            "region_id": contract["region_id"],
            "classification": contract["classification"],
            "accepted_public_reference": False,
            "product_route_eligible": False,
            "source_identity": {
                key: contract["source_identity"][key]
                for key in (
                    "authority",
                    "dataset_name",
                    "delivery_name",
                    "snapshot_timestamp",
                    "native_crs",
                    "delivery_format",
                    "recovered_processing_format",
                    "provenance_status",
                    "license",
                    "license_url",
                    "terms_url",
                    "license_status",
                )
            },
            "delivery_metadata_public_fields": validated_inputs[
                "metadata_public_fields"
            ],
            "contract_path": contract_path.relative_to(repo_root).as_posix(),
            "contract_signature_sha256": snapshot_build_contract_signature(
                contract
            ),
            "source_files": source_files,
            "analysis_domain": domain_evidence,
            "distance_semantics": output["distance_semantics"],
            "intersection_semantics": output["intersection_semantics"],
            "runtime_versions": {
                "shapely": str(shapely.__version__),
                "geos": str(shapely.geos_version_string),
            },
            "coverage_evidence": {
                "mode": "complete",
                "missing_observation_policy": "error",
                "expected_layer_count": len(normalized),
                "complete_layer_count": len(layer_metadata),
                "expected_rows_per_layer": contract["analysis_domain"][
                    "expected_cell_count"
                ],
                "all_layers_complete": all(
                    item["row_count"]
                    == contract["analysis_domain"]["expected_cell_count"]
                    for item in layer_metadata
                ),
            },
            "build_input_signature_sha256": canonical_sha256(build_inputs),
            "layers": layer_metadata,
            "acceptance_blockers": contract["acceptance_blockers"],
        }
        metadata_path = staging / str(output["metadata_name"])
        metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        pinned_metadata_sha256 = output.get("metadata_sha256")
        if pinned_metadata_sha256 is not None:
            actual_metadata_sha256 = sha256_file(metadata_path)
            if actual_metadata_sha256 != _lower_sha256(
                pinned_metadata_sha256
            ):
                raise ValueError(
                    "Generated road-snapshot metadata does not match the "
                    "repo-pinned checksum; existing artifacts were not replaced"
                )
        target.mkdir(parents=True, exist_ok=True)
        metadata_name = str(output["metadata_name"])
        for name in sorted(expected_names - {metadata_name}):
            os.replace(staging / name, target / name)
        os.replace(staging / metadata_name, target / metadata_name)
    return target / str(output["metadata_name"])


def validate_generated_road_snapshot(
    contract: dict[str, Any],
    *,
    contract_path: Path,
    generated_root: Path,
) -> dict[str, Any]:
    output = contract["output"]
    relative_output = PurePosixPath(output["relative_directory"])
    root = generated_root.expanduser().resolve(strict=True)
    from .paths import repo_root

    _repo_outside_path(root, repo_root(), "Generated road snapshot")
    target = root.joinpath(*relative_output.parts).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Generated snapshot path escapes its root") from exc
    metadata_path = target / output["metadata_name"]
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Generated road-snapshot metadata is unreadable") from exc
    if not isinstance(metadata, dict):
        raise ValueError("Generated road-snapshot metadata must be an object")
    if output.get("artifact_status") != "checksum_pinned":
        raise ValueError(
            "Generated road-snapshot metadata is not checksum-pinned in the "
            "repo contract"
        )
    expected_metadata_sha256 = _lower_sha256(output.get("metadata_sha256"))
    actual_metadata_sha256 = sha256_file(metadata_path)
    if actual_metadata_sha256 != expected_metadata_sha256:
        raise ValueError(
            "Generated road-snapshot metadata checksum does not match the "
            "repo contract"
        )
    if (
        metadata.get("schema_version") != "1.0"
        or metadata.get("snapshot_id") != contract["snapshot_id"]
        or metadata.get("classification") != "diagnostic_candidate_only"
        or metadata.get("accepted_public_reference") is not False
        or metadata.get("product_route_eligible") is not False
        or metadata.get("contract_signature_sha256")
        != snapshot_build_contract_signature(contract)
    ):
        raise ValueError("Generated road-snapshot identity or contract binding drifted")
    if (
        metadata.get("region_id") != contract["region_id"]
        or metadata.get("contract_path")
        != contract_path.relative_to(repo_root()).as_posix()
        or metadata.get("distance_semantics") != output["distance_semantics"]
        or metadata.get("intersection_semantics")
        != output["intersection_semantics"]
        or metadata.get("runtime_versions")
        != {
            "shapely": str(shapely.__version__),
            "geos": str(shapely.geos_version_string),
        }
    ):
        raise ValueError("Generated road-snapshot semantics or runtime drifted")
    domain = metadata.get("analysis_domain")
    expected_domain = contract["analysis_domain"]
    if (
        not isinstance(domain, dict)
        or domain.get("cell_count") != expected_domain["expected_cell_count"]
        or domain.get("cell_ids_sha256") != expected_domain["cell_ids_sha256"]
        or domain.get("resolution") != expected_domain["resolution"]
    ):
        raise ValueError("Generated road snapshot is not bound to its declared H3 domain")
    expected_source_files = _declared_source_files(contract)
    if metadata.get("source_files") != expected_source_files:
        raise ValueError("Generated road-snapshot source signatures drifted")
    expected_identity = {
        key: contract["source_identity"][key]
        for key in (
            "authority",
            "dataset_name",
            "delivery_name",
            "snapshot_timestamp",
            "native_crs",
            "delivery_format",
            "recovered_processing_format",
            "provenance_status",
            "license",
            "license_url",
            "terms_url",
            "license_status",
        )
    }
    if (
        metadata.get("source_identity") != expected_identity
        or metadata.get("delivery_metadata_public_fields")
        != contract["inputs"]["delivery_metadata"]["required_public_fields"]
        or metadata.get("acceptance_blockers") != contract["acceptance_blockers"]
    ):
        raise ValueError("Generated road-snapshot sanitized provenance drifted")
    layer_rows = metadata.get("layers")
    layer_ids = [
        item.get("layer_id")
        for item in layer_rows
        if isinstance(item, dict)
    ] if isinstance(layer_rows, list) else []
    if (
        not isinstance(layer_rows, list)
        or len(layer_rows) != len(contract["layers"])
        or len(layer_ids) != len(set(layer_ids))
        or set(layer_ids) != set(contract["layers"])
    ):
        raise ValueError("Generated road-snapshot layer set drifted")
    coverage = metadata.get("coverage_evidence")
    if (
        not isinstance(coverage, dict)
        or coverage.get("mode") != "complete"
        or coverage.get("missing_observation_policy") != "error"
        or coverage.get("expected_layer_count") != len(contract["layers"])
        or coverage.get("complete_layer_count") != len(contract["layers"])
        or coverage.get("expected_rows_per_layer")
        != expected_domain["expected_cell_count"]
        or coverage.get("all_layers_complete") is not True
    ):
        raise ValueError("Generated road-snapshot coverage semantics drifted")
    expected_directory_names = {
        output["metadata_name"],
        *(f"{layer_id}.geojson" for layer_id in contract["layers"]),
        *(f"{layer_id}.csv" for layer_id in contract["layers"]),
    }
    actual_directory_names = {
        item.name for item in target.iterdir() if item.is_file()
    }
    if actual_directory_names != expected_directory_names:
        raise ValueError("Generated road-snapshot directory contains unexpected files")
    expected_ids_digest = expected_domain["cell_ids_sha256"]
    for item in layer_rows:
        if not isinstance(item, dict):
            raise ValueError("Generated road-snapshot layer metadata is invalid")
        layer_id = item["layer_id"]
        declaration = contract["layers"][layer_id]
        if (
            item.get("geojson_path") != f"{layer_id}.geojson"
            or item.get("distance_path") != f"{layer_id}.csv"
        ):
            raise ValueError(f"{layer_id} generated paths drifted")
        geojson_path = target / f"{layer_id}.geojson"
        csv_path = target / f"{layer_id}.csv"
        for path, bytes_field, hash_field in (
            (geojson_path, "geojson_bytes", "geojson_sha256"),
            (csv_path, "distance_bytes", "distance_sha256"),
        ):
            if (
                not path.is_file()
                or path.stat().st_size != item.get(bytes_field)
                or sha256_file(path) != item.get(hash_field)
            ):
                raise ValueError(f"Generated artifact failed integrity: {path.name}")
        payload = json.loads(geojson_path.read_text(encoding="utf-8"))
        features = payload.get("features") if isinstance(payload, dict) else None
        if not isinstance(features, list) or len(features) != 1:
            raise ValueError(f"{layer_id} GeoJSON must contain one dissolved feature")
        properties = features[0].get("properties")
        try:
            generated_geometry = shape(features[0].get("geometry"))
        except Exception as exc:
            raise ValueError(f"{layer_id} GeoJSON geometry is unreadable") from exc
        if (
            generated_geometry.is_empty
            or not generated_geometry.is_valid
            or generated_geometry.geom_type not in {"LineString", "MultiLineString"}
        ):
            raise ValueError(f"{layer_id} GeoJSON geometry is not a valid line")
        if (
            not isinstance(properties, dict)
            or properties.get("layer_id") != layer_id
            or properties.get("source_categories")
            != declaration["source_categories"]
            or properties.get("source_feature_count")
            != declaration["expected_source_feature_count"]
            or properties.get("processed_reference_category")
            != declaration["processed_reference_category"]
            or properties.get("processed_reference_equivalent") is not True
        ):
            raise ValueError(f"{layer_id} GeoJSON source semantics drifted")
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != ["hex_id", "distance_m", "intersects"]:
                raise ValueError(f"{layer_id} distance CSV header drifted")
            rows = list(reader)
        if [str(row.get("hex_id") or "") for row in rows] != sorted(
            str(row.get("hex_id") or "") for row in rows
        ):
            raise ValueError(f"{layer_id} distance rows are not canonical-order")
        ids = [str(row.get("hex_id") or "") for row in rows]
        if (
            len(rows) != expected_domain["expected_cell_count"]
            or len(ids) != len(set(ids))
            or id_set_sha256(ids) != expected_ids_digest
            or item.get("row_count") != len(rows)
            or item.get("cell_ids_sha256") != expected_ids_digest
        ):
            raise ValueError(f"{layer_id} distance coverage is incomplete")
        reconstructed = tuple(
            DistanceObservation(
                cell_id=row["hex_id"],
                distance_m=float(row["distance_m"]),
                intersects=row["intersects"] == "true",
            )
            for row in rows
        )
        if any(
            not math.isfinite(row.distance_m)
            or row.distance_m < 0.0
            or str(raw["intersects"]) not in {"true", "false"}
            for row, raw in zip(reconstructed, rows, strict=True)
        ):
            raise ValueError(f"{layer_id} contains invalid distance observations")
        if rows_sha256(reconstructed) != item.get("distance_rows_sha256"):
            raise ValueError(f"{layer_id} row signature drifted")
        if sum(int(row.intersects) for row in reconstructed) != item.get(
            "intersecting_cell_count"
        ):
            raise ValueError(f"{layer_id} intersection count drifted")
    build_input_layers = [
        {
            "layer_id": item["layer_id"],
            "source_categories": item["source_categories"],
            "source_feature_count": item["source_feature_count"],
        }
        for item in layer_rows
    ]
    expected_build_inputs = {
        "snapshot_id": contract["snapshot_id"],
        "contract_signature_sha256": snapshot_build_contract_signature(
            contract
        ),
        "source_files": expected_source_files,
        "domain_sha256": domain["sha256"],
        "domain_cell_ids_sha256": domain["cell_ids_sha256"],
        "layers": build_input_layers,
    }
    if metadata.get("build_input_signature_sha256") != canonical_sha256(
        expected_build_inputs
    ):
        raise ValueError("Generated road-snapshot build-input signature drifted")
    return metadata


def _generated_artifact_path(
    generated_root: Path,
    relative_value: Any,
    label: str,
) -> Path:
    relative = _safe_generated_relative_path(relative_value, label)
    candidate = generated_root.joinpath(*relative.parts).resolve()
    try:
        candidate.relative_to(generated_root)
    except ValueError as exc:
        raise ValueError(f"{label} escapes the generated-runtime root") from exc
    return candidate


def _load_diagnostic_distance_observations(
    path: Path,
    *,
    layer_id: str,
    layer_metadata: dict[str, Any],
    expected_cell_ids: tuple[str, ...],
    expected_cell_ids_sha256: str,
) -> tuple[DistanceObservation, ...]:
    if (
        not path.is_file()
        or path.stat().st_size != layer_metadata.get("distance_bytes")
        or sha256_file(path) != layer_metadata.get("distance_sha256")
    ):
        raise ValueError(f"{layer_id} diagnostic distance artifact drifted")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["hex_id", "distance_m", "intersects"]:
            raise ValueError(f"{layer_id} diagnostic distance header drifted")
        raw_rows = list(reader)
    observations: list[DistanceObservation] = []
    for line_number, raw in enumerate(raw_rows, start=2):
        cell_id = str(raw.get("hex_id") or "").strip()
        intersects_text = str(raw.get("intersects") or "").strip()
        if intersects_text not in {"true", "false"}:
            raise ValueError(
                f"{layer_id} has invalid intersects at CSV line {line_number}"
            )
        try:
            distance_m = float(str(raw.get("distance_m") or ""))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError(
                f"{layer_id} has invalid distance at CSV line {line_number}"
            ) from exc
        if not math.isfinite(distance_m) or distance_m < 0.0:
            raise ValueError(
                f"{layer_id} has invalid distance at CSV line {line_number}"
            )
        observations.append(
            DistanceObservation(
                cell_id=cell_id,
                distance_m=distance_m,
                intersects=intersects_text == "true",
            )
        )
    result = tuple(observations)
    ids = tuple(row.cell_id for row in result)
    if (
        ids != expected_cell_ids
        or len(ids) != len(set(ids))
        or id_set_sha256(ids) != expected_cell_ids_sha256
        or layer_metadata.get("row_count") != len(result)
        or layer_metadata.get("cell_ids_sha256") != expected_cell_ids_sha256
        or rows_sha256(result) != layer_metadata.get("distance_rows_sha256")
        or sum(int(row.intersects) for row in result)
        != layer_metadata.get("intersecting_cell_count")
    ):
        raise ValueError(f"{layer_id} diagnostic observations drifted")
    return result


def load_road_diagnostic_snapshot(
    region_id: str,
    snapshot_id: str = "roads",
    *,
    generated_root: Path | None = None,
) -> RoadDiagnosticSnapshot:
    """Load one checksum-bound, diagnostic-only road calculation snapshot.

    Both the road metadata/CSVs and the exact regional domain artifact are
    verified against repo-owned contracts. The returned object is immutable
    calculation input; it does not imply product readiness or regional
    acceptance.
    """

    from .catalogs import load_region_geography
    from .paths import provider_root, repo_root

    contract, contract_path = load_region_source_snapshot(region_id, snapshot_id)
    root = (
        provider_root("generated_runtime")
        if generated_root is None
        else generated_root.expanduser().resolve(strict=True)
    )
    _repo_outside_path(root, repo_root(), "Generated road diagnostic")
    metadata = validate_generated_road_snapshot(
        contract,
        contract_path=contract_path,
        generated_root=root,
    )
    if (
        contract.get("classification") != "diagnostic_candidate_only"
        or contract.get("accepted_public_reference") is not False
        or contract.get("product_route_eligible") is not False
        or metadata.get("classification") != "diagnostic_candidate_only"
        or metadata.get("accepted_public_reference") is not False
        or metadata.get("product_route_eligible") is not False
    ):
        raise ValueError("Road diagnostic snapshot made an acceptance claim")

    expected_domain = contract["analysis_domain"]
    geography = load_region_geography(region_id)
    domain_id = str(expected_domain["domain_id"])
    domain_contract = geography.analysis_domains.get(domain_id)
    if domain_contract is None:
        raise ValueError("Road diagnostic domain is not region-declared")
    artifact = domain_contract.artifacts
    resolution = int(expected_domain["resolution"])
    if (
        domain_contract.metadata_provider != "generated_runtime"
        or artifact.provider != "generated_runtime"
        or domain_contract.coverage_rule != expected_domain["coverage_rule"]
        or artifact.cell_kind != expected_domain["cell_kind"]
        or artifact.id_field != "hex_id"
        or artifact.area_field != "area_km2"
        or artifact.area_unit != "km2"
        or artifact.resolution != resolution
        or artifact.expected_cell_count != expected_domain["expected_cell_count"]
        or domain_contract.cell_ids_sha256.get(resolution)
        != expected_domain["cell_ids_sha256"]
    ):
        raise ValueError("Road diagnostic domain contract binding drifted")
    domain_metadata_path = _generated_artifact_path(
        root,
        domain_contract.metadata_path,
        "Road diagnostic domain metadata path",
    )
    domain_geojson_path = _generated_artifact_path(
        root,
        artifact.path,
        "Road diagnostic domain GeoJSON path",
    )
    domain_cells, domain_evidence = load_verified_domain_cells(
        contract,
        generated_root=root,
        metadata_path=domain_metadata_path,
        geojson_path=domain_geojson_path,
        expected_metadata_sha256=domain_contract.metadata_sha256,
        expected_geojson_sha256=artifact.sha256,
    )
    metadata_domain = metadata.get("analysis_domain")
    if (
        not isinstance(metadata_domain, dict)
        or metadata_domain.get("domain_id") != domain_id
        or metadata_domain.get("resolution") != resolution
        or metadata_domain.get("cell_count") != len(domain_cells)
        or metadata_domain.get("cell_ids_sha256")
        != expected_domain["cell_ids_sha256"]
        or metadata_domain.get("sha256") != artifact.sha256
        or metadata_domain.get("metadata_sha256")
        != domain_contract.metadata_sha256
        or domain_evidence["sha256"] != artifact.sha256
        or domain_evidence["metadata_sha256"]
        != domain_contract.metadata_sha256
    ):
        raise ValueError("Road observations are not bound to the regional domain")
    domain_cells_by_id = tuple(
        RoadDiagnosticDomainCell(
            cell_id=cell.cell_id,
            area_km2=cell.area_km2,
        )
        for cell in domain_cells
    )
    total_area_km2 = math.fsum(cell.area_km2 for cell in domain_cells_by_id)
    if not math.isclose(
        total_area_km2,
        artifact.expected_total_area_km2,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise ValueError("Road diagnostic domain total area drifted")

    output = contract["output"]
    output_directory = _generated_artifact_path(
        root,
        output["relative_directory"],
        "Road diagnostic output directory",
    )
    metadata_layers = metadata.get("layers")
    if not isinstance(metadata_layers, list):
        raise ValueError("Road diagnostic layer metadata is missing")
    metadata_by_id = {
        str(item.get("layer_id")): item
        for item in metadata_layers
        if isinstance(item, dict)
    }
    expected_cell_ids = tuple(cell.cell_id for cell in domain_cells_by_id)
    layers: list[RoadDiagnosticLayer] = []
    for layer_id, declaration in contract["layers"].items():
        item = metadata_by_id.get(layer_id)
        if not isinstance(item, dict):
            raise ValueError(f"Road diagnostic layer is missing: {layer_id}")
        source_path = output_directory / str(item["geojson_path"])
        try:
            source_bytes = source_path.read_bytes()
            if (
                len(source_bytes) != int(item["geojson_bytes"])
                or hashlib.sha256(source_bytes).hexdigest()
                != str(item["geojson_sha256"])
            ):
                raise ValueError(
                    f"Road diagnostic source geometry checksum drifted: {layer_id}"
                )
            source_feature_collection_json = source_bytes.decode("utf-8")
            source_feature_collection = json.loads(
                source_feature_collection_json
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Road diagnostic source geometry is unreadable: {layer_id}"
            ) from exc
        source_features = (
            source_feature_collection.get("features")
            if isinstance(source_feature_collection, dict)
            else None
        )
        source_properties = (
            source_features[0].get("properties")
            if isinstance(source_features, list)
            and len(source_features) == 1
            and isinstance(source_features[0], dict)
            else None
        )
        if (
            not isinstance(source_feature_collection, dict)
            or source_feature_collection.get("type") != "FeatureCollection"
            or not isinstance(source_features, list)
            or len(source_features) != 1
            or not isinstance(source_features[0], dict)
            or not isinstance(source_properties, dict)
            or str(source_properties.get("layer_id") or "") != layer_id
        ):
            raise ValueError(
                f"Road diagnostic source geometry identity drifted: {layer_id}"
            )
        distance_path = output_directory / str(item["distance_path"])
        observations = _load_diagnostic_distance_observations(
            distance_path,
            layer_id=layer_id,
            layer_metadata=item,
            expected_cell_ids=expected_cell_ids,
            expected_cell_ids_sha256=expected_domain["cell_ids_sha256"],
        )
        layers.append(
            RoadDiagnosticLayer(
                evidence=RoadDiagnosticLayerEvidence(
                    layer_id=layer_id,
                    label=str(declaration["label"]),
                    source_categories=tuple(declaration["source_categories"]),
                    source_feature_count=int(item["source_feature_count"]),
                    dissolved_length_m=float(item["dissolved_length_m"]),
                    observation_count=int(item["row_count"]),
                    intersecting_cell_count=int(
                        item["intersecting_cell_count"]
                    ),
                    distance_rows_sha256=str(item["distance_rows_sha256"]),
                    distance_sha256=str(item["distance_sha256"]),
                ),
                source_feature_collection_json=source_feature_collection_json,
                observations=observations,
            )
        )
    source_identity = metadata["source_identity"]
    return RoadDiagnosticSnapshot(
        snapshot_id=str(metadata["snapshot_id"]),
        region_id=str(metadata["region_id"]),
        classification=str(metadata["classification"]),
        accepted_public_reference=False,
        product_route_eligible=False,
        metadata_sha256=sha256_file(
            output_directory / str(output["metadata_name"])
        ),
        source=RoadDiagnosticSourceEvidence(
            authority=str(source_identity["authority"]),
            dataset_name=str(source_identity["dataset_name"]),
            delivery_name=str(source_identity["delivery_name"]),
            snapshot_timestamp=str(source_identity["snapshot_timestamp"]),
            license=str(source_identity["license"]),
            license_url=str(source_identity["license_url"]),
            terms_url=str(source_identity["terms_url"]),
            license_status=str(source_identity["license_status"]),
        ),
        domain_id=domain_id,
        resolution=resolution,
        total_area_km2=total_area_km2,
        cells=domain_cells_by_id,
        layers=tuple(layers),
    )


def calculate_road_diagnostic(
    snapshot: RoadDiagnosticSnapshot,
    selected_layer_ids: Iterable[str],
    buffer_m: Real,
) -> RoadDiagnosticResult:
    """Calculate the isolated road distance-exclusion diagnostic.

    A cell is blocked when any selected layer intersects the cell geometry or
    its representative-point distance is less than or equal to ``buffer_m``.
    The result covers only the road filter and must not be interpreted as a
    wind/solar potential result.
    """

    if (
        not isinstance(snapshot, RoadDiagnosticSnapshot)
        or not isinstance(snapshot.source, RoadDiagnosticSourceEvidence)
        or snapshot.classification != "diagnostic_candidate_only"
        or snapshot.accepted_public_reference is not False
        or snapshot.product_route_eligible is not False
    ):
        raise ValueError("Road calculation input is not diagnostic-only")
    snapshot_cells = _tuple_of_type(
        snapshot.cells,
        RoadDiagnosticDomainCell,
        "Road diagnostic cells",
    )
    snapshot_layers = _tuple_of_type(
        snapshot.layers,
        RoadDiagnosticLayer,
        "Road diagnostic layers",
    )
    if any(
        not isinstance(layer.evidence, RoadDiagnosticLayerEvidence)
        or not isinstance(layer.observations, tuple)
        or any(
            not isinstance(row, DistanceObservation)
            for row in layer.observations
        )
        for layer in snapshot_layers
    ):
        raise ValueError("Road diagnostic layers are not immutable typed input")
    if isinstance(selected_layer_ids, (str, bytes)):
        raise ValueError("Selected road layers must be a non-empty iterable")
    requested = tuple(selected_layer_ids)
    if (
        not requested
        or any(not isinstance(layer_id, str) or not layer_id for layer_id in requested)
        or len(requested) != len(set(requested))
    ):
        raise ValueError("Selected road layers must be unique, non-empty ids")
    if isinstance(buffer_m, bool) or not isinstance(buffer_m, Real):
        raise ValueError("Road diagnostic buffer must be a finite number")
    threshold = float(buffer_m)
    if not math.isfinite(threshold) or threshold < 0.0:
        raise ValueError("Road diagnostic buffer must be finite and non-negative")

    layers_by_id = {layer.evidence.layer_id: layer for layer in snapshot_layers}
    if (
        not layers_by_id
        or len(layers_by_id) != len(snapshot_layers)
        or any(
            not isinstance(layer_id, str) or not layer_id
            for layer_id in layers_by_id
        )
    ):
        raise ValueError("Road diagnostic layer coverage drifted")
    unknown = set(requested) - layers_by_id.keys()
    if unknown:
        raise ValueError(f"Unknown road diagnostic layers: {sorted(unknown)}")
    selected = tuple(
        layer
        for layer in snapshot_layers
        if layer.evidence.layer_id in requested
    )
    canonical_selected_ids = tuple(
        layer.evidence.layer_id for layer in selected
    )
    cell_ids = tuple(cell.cell_id for cell in snapshot_cells)
    if (
        len(cell_ids) != len(set(cell_ids))
        or cell_ids != tuple(sorted(cell_ids))
        or any(
            tuple(row.cell_id for row in layer.observations) != cell_ids
            for layer in selected
        )
    ):
        raise ValueError("Road diagnostic calculation coverage drifted")

    cells: list[RoadDiagnosticCellResult] = []
    blocked_ids: list[str] = []
    blocked_areas: list[float] = []
    remaining_areas: list[float] = []
    for index, domain_cell in enumerate(snapshot_cells):
        observations = tuple(layer.observations[index] for layer in selected)
        min_distance_m = min(row.distance_m for row in observations)
        any_intersection = any(row.intersects for row in observations)
        blocked = any_intersection or min_distance_m <= threshold
        if (
            not math.isfinite(min_distance_m)
            or min_distance_m < 0.0
            or not math.isfinite(domain_cell.area_km2)
            or domain_cell.area_km2 <= 0.0
        ):
            raise ValueError("Road diagnostic calculation input is invalid")
        cells.append(
            RoadDiagnosticCellResult(
                cell_id=domain_cell.cell_id,
                min_distance_m=min_distance_m,
                any_intersection=any_intersection,
                blocked=blocked,
                area_km2=domain_cell.area_km2,
            )
        )
        if blocked:
            blocked_ids.append(domain_cell.cell_id)
            blocked_areas.append(domain_cell.area_km2)
        else:
            remaining_areas.append(domain_cell.area_km2)
    cell_count = len(cells)
    blocked_cell_count = len(blocked_ids)
    remaining_cell_count = cell_count - blocked_cell_count
    total_area_km2 = math.fsum(cell.area_km2 for cell in snapshot_cells)
    blocked_area_km2 = math.fsum(blocked_areas)
    remaining_area_km2 = math.fsum(remaining_areas)
    if (
        cell_count <= 0
        or total_area_km2 <= 0.0
        or not math.isclose(
            total_area_km2,
            blocked_area_km2 + remaining_area_km2,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    ):
        raise ValueError("Road diagnostic result coverage is invalid")
    summary = RoadDiagnosticSummary(
        cell_count=cell_count,
        blocked_cell_count=blocked_cell_count,
        remaining_cell_count=remaining_cell_count,
        total_area_km2=total_area_km2,
        blocked_area_km2=blocked_area_km2,
        remaining_area_km2=remaining_area_km2,
        blocked_cell_share=blocked_cell_count / cell_count,
        remaining_cell_share=remaining_cell_count / cell_count,
        blocked_area_share=blocked_area_km2 / total_area_km2,
        remaining_area_share=remaining_area_km2 / total_area_km2,
        blocked_cell_ids_sha256=id_set_sha256(blocked_ids),
    )
    return RoadDiagnosticResult(
        snapshot_id=snapshot.snapshot_id,
        region_id=snapshot.region_id,
        domain_id=snapshot.domain_id,
        resolution=snapshot.resolution,
        selected_layer_ids=canonical_selected_ids,
        buffer_m=threshold,
        layer_evidence=tuple(layer.evidence for layer in selected),
        summary=summary,
        cells=tuple(cells),
    )
