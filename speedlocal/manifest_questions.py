from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator

from .paths import repo_root


QUESTION_CATALOG_SCHEMA_VERSION = "1.0"
QUESTION_CATALOG_VERSION = "1.15.1"
QUESTION_CATALOG_OPERATOR_LANGUAGE = "sv"
QUESTION_CATALOG_SCHEMA_RELATIVE_PATH = Path(
    "schemas/speedlocal/1.0/region-package-questions.schema.json"
)
QUESTION_CATALOG_RELATIVE_PATH = Path(
    "schemas/speedlocal/1.0/region-package.questions.json"
)
_POINTER_SEGMENT_RE = re.compile(r"^(?:[^~/]|~0|~1)+$")
_QUESTION_ID_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")
_SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_REQUIRED_GENERATED_TARGET_PATHS = (
    "/$schema",
    "/form_schema_version",
    "/geography/boundary/asset/integrity/sha256",
    "/geography/technology_support/coverage_geometry/asset/integrity/sha256",
    "/geography/technology_support/technology_context/asset/integrity/sha256",
    "/landscape/source_reference/asset/integrity/sha256",
    "/solar_rooftop/population_source/asset/integrity/sha256",
    "/standard_groups/*/id",
    "/standard_groups/*/layers/*/source/asset/integrity/sha256",
    "/technologies/*/technology_id",
    "/scenario/assets/*/integrity/sha256",
    "/social_acceptance/assets/*/integrity/sha256",
    "/social_acceptance/coverage/source_hex_count",
    "/social_acceptance/coverage/target_support_hex_count",
    "/social_acceptance/coverage/unassessed_support_hex_count",
)


@dataclass(frozen=True)
class ManifestQuestion:
    """One human-facing question mapped to a region-package field."""

    id: str
    question: str
    target_path: str
    type: str
    unit: str | None
    required_when: str
    allowed_values: Any
    example: Any
    help: str
    activates: tuple[str, ...]
    error_if_missing: str
    generated: bool

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ManifestQuestion":
        return cls(
            id=str(value["id"]),
            question=str(value["question"]),
            target_path=str(value["target_path"]),
            type=str(value["type"]),
            unit=(None if value["unit"] is None else str(value["unit"])),
            required_when=str(value["required_when"]),
            allowed_values=value["allowed_values"],
            example=value["example"],
            help=str(value["help"]),
            activates=tuple(str(item) for item in value["activates"]),
            error_if_missing=str(value["error_if_missing"]),
            generated=bool(value["generated"]),
        )


@dataclass(frozen=True)
class ManifestQuestionSection:
    """One versioned operator-facing section in schema order."""

    id: str
    title: str
    description: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ManifestQuestionSection":
        return cls(
            id=str(value["id"]),
            title=str(value["title"]),
            description=str(value["description"]),
        )


@dataclass(frozen=True)
class QuestionCatalogProblem:
    """One deterministic machine-readable defect in the question catalog."""

    code: str
    pointer: str
    message: str
    expected: Any | None = None
    actual: Any | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_question_catalog_schema_path() -> Path:
    return repo_root() / QUESTION_CATALOG_SCHEMA_RELATIVE_PATH


def default_question_catalog_path() -> Path:
    return repo_root() / QUESTION_CATALOG_RELATIVE_PATH


def _json_pointer(parts: Iterable[object]) -> str:
    escaped = [
        str(part).replace("~", "~0").replace("/", "~1")
        for part in parts
    ]
    return "/" + "/".join(escaped) if escaped else "/"


def _pointer_parts(pointer: str) -> tuple[str, ...]:
    if pointer == "/":
        return ()
    if not pointer.startswith("/"):
        raise ValueError(f"Ogiltig JSON-pointer: {pointer!r}")
    return tuple(
        part.replace("~1", "/").replace("~0", "~")
        for part in pointer[1:].split("/")
    )


def _valid_target_path(target_path: str) -> bool:
    if target_path == "/" or not target_path.startswith("/"):
        return False
    return all(
        segment == "*" or _POINTER_SEGMENT_RE.fullmatch(segment)
        for segment in target_path[1:].split("/")
    )


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    source_path = path.resolve()
    try:
        value = json.loads(source_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"{label} saknas: {source_path}") from None
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} kan inte läsas: {source_path}: {exc}") from exc
    if not isinstance(value, dict):
        raise TypeError(f"{label} måste vara ett JSON-objekt")
    return value


def load_question_catalog_schema(path: Path | None = None) -> dict[str, Any]:
    """Load and meta-validate the versioned catalog schema."""

    value = _load_json_object(
        path or default_question_catalog_schema_path(),
        label="Frågekatalogens schema",
    )
    Draft202012Validator.check_schema(value)
    return value


def load_question_catalog_payload(path: Path | None = None) -> dict[str, Any]:
    """Load the raw versioned question-catalog payload."""

    return _load_json_object(
        path or default_question_catalog_path(),
        label="Regionblankettens frågekatalog",
    )


def _resolve_schema_node(
    node: Mapping[str, Any],
    root: Mapping[str, Any],
) -> Mapping[str, Any]:
    reference = node.get("$ref")
    if not isinstance(reference, str):
        return node
    if not reference.startswith("#/"):
        raise ValueError(f"Endast lokala schema-$ref stöds: {reference!r}")
    current: Any = root
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or part not in current:
            raise ValueError(f"Schema-$ref kan inte lösas: {reference!r}")
        current = current[part]
    if not isinstance(current, Mapping):
        raise ValueError(f"Schema-$ref pekar inte på ett objekt: {reference!r}")
    return current


def schema_leaf_target_paths(schema: Mapping[str, Any]) -> tuple[str, ...]:
    """Return every user-visible leaf path allowed by the form schema.

    Array positions that contain objects use ``*`` so one question covers every
    repeated group, layer, scenario, or asset declaration. Arrays of scalar
    answers remain one list-valued question at their containing path.
    """

    leaves: set[str] = set()
    active_refs: set[tuple[str, tuple[str, ...]]] = set()

    def visit(raw_node: Mapping[str, Any], path: tuple[str, ...]) -> None:
        reference = raw_node.get("$ref")
        if isinstance(reference, str):
            marker = (reference, path)
            if marker in active_refs:
                raise ValueError(f"Cirkulär schema-$ref: {reference!r}")
            active_refs.add(marker)
            visit(_resolve_schema_node(raw_node, schema), path)
            active_refs.remove(marker)
            return

        composite = False
        for keyword in ("allOf", "oneOf", "anyOf"):
            variants = raw_node.get(keyword)
            if isinstance(variants, Sequence) and not isinstance(
                variants, (str, bytes)
            ):
                composite = True
                for variant in variants:
                    if isinstance(variant, Mapping):
                        visit(variant, path)

        properties = raw_node.get("properties")
        if isinstance(properties, Mapping):
            composite = True
            for name, child in properties.items():
                if isinstance(child, Mapping):
                    visit(child, (*path, str(name)))

        node_type = raw_node.get("type")
        prefix_items = raw_node.get("prefixItems")
        items = raw_node.get("items")
        if node_type == "array" or prefix_items is not None or items is not None:
            composite = True
            object_children: list[Mapping[str, Any]] = []
            if isinstance(prefix_items, Sequence) and not isinstance(
                prefix_items, (str, bytes)
            ):
                object_children.extend(
                    child for child in prefix_items if isinstance(child, Mapping)
                )
            if isinstance(items, Mapping):
                object_children.append(items)
            contains_structured_item = any(
                _schema_node_is_structured(child, schema) for child in object_children
            )
            if contains_structured_item:
                for child in object_children:
                    if _schema_node_is_structured(child, schema):
                        visit(child, (*path, "*"))
            elif path:
                leaves.add(_json_pointer(path))

        if not composite and path:
            leaves.add(_json_pointer(path))

    visit(schema, ())
    return tuple(sorted(leaves))


def _schema_node_is_structured(
    raw_node: Mapping[str, Any],
    root: Mapping[str, Any],
) -> bool:
    node = _resolve_schema_node(raw_node, root)
    if node.get("type") == "object" or isinstance(node.get("properties"), Mapping):
        return True
    for keyword in ("allOf", "oneOf", "anyOf"):
        variants = node.get(keyword)
        if isinstance(variants, Sequence) and not isinstance(variants, (str, bytes)):
            if any(
                isinstance(item, Mapping) and _schema_node_is_structured(item, root)
                for item in variants
            ):
                return True
    return False


def form_leaf_target_paths(value: Mapping[str, Any]) -> tuple[str, ...]:
    """Return normalized leaf paths present in one concrete region form."""

    leaves: set[str] = set()

    def visit(node: Any, path: tuple[str, ...]) -> None:
        if isinstance(node, Mapping):
            if not node and path:
                leaves.add(_json_pointer(path))
                return
            for name, child in node.items():
                visit(child, (*path, str(name)))
            return
        if isinstance(node, list):
            if not node or all(not isinstance(item, Mapping) for item in node):
                leaves.add(_json_pointer(path))
                return
            for item in node:
                if isinstance(item, Mapping):
                    visit(item, (*path, "*"))
                else:
                    leaves.add(_json_pointer(path))
            return
        leaves.add(_json_pointer(path))

    visit(value, ())
    return tuple(sorted(leaves))


def _question_matches_pointer(question_path: str, pointer: str) -> bool:
    question_parts = _pointer_parts(question_path)
    pointer_parts = _pointer_parts(pointer)
    return len(question_parts) == len(pointer_parts) and all(
        expected == "*" or expected == actual
        for expected, actual in zip(question_parts, pointer_parts)
    )


def match_question_for_pointer(
    pointer: str,
    questions: Sequence[ManifestQuestion],
) -> ManifestQuestion | None:
    """Return the uniquely matching question for one concrete JSON pointer."""

    matches = [
        question
        for question in questions
        if _question_matches_pointer(question.target_path, pointer)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def validate_question_catalog(
    payload: Mapping[str, Any],
    *,
    form_schema: Mapping[str, Any],
    form: Mapping[str, Any] | None = None,
    catalog_schema: Mapping[str, Any] | None = None,
    expected_form_schema_version: str,
) -> tuple[QuestionCatalogProblem, ...]:
    """Validate metadata, versions, uniqueness, and complete form coverage."""

    active_catalog_schema = catalog_schema or load_question_catalog_schema()
    validator = Draft202012Validator(active_catalog_schema)
    structural_errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if structural_errors:
        return tuple(
            QuestionCatalogProblem(
                code="MQ-SCHEMA-001",
                pointer=_json_pointer(error.absolute_path),
                message=f"Frågekatalogen följer inte sitt schema: {error.message}",
                expected=error.validator_value,
                actual=error.instance,
            )
            for error in structural_errors
        )

    problems: list[QuestionCatalogProblem] = []
    if payload["catalog_schema_version"] != QUESTION_CATALOG_SCHEMA_VERSION:
        problems.append(
            QuestionCatalogProblem(
                code="MQ-VERSION-001",
                pointer="/catalog_schema_version",
                message="Frågekatalogens schemaversion stöds inte.",
                expected=QUESTION_CATALOG_SCHEMA_VERSION,
                actual=payload["catalog_schema_version"],
            )
        )
    if payload["form_schema_version"] != expected_form_schema_version:
        problems.append(
            QuestionCatalogProblem(
                code="MQ-VERSION-002",
                pointer="/form_schema_version",
                message="Frågekatalogen beskriver inte den aktiva blankettversionen.",
                expected=expected_form_schema_version,
                actual=payload["form_schema_version"],
            )
        )
    if (
        not _SEMVER_RE.fullmatch(payload["questions_version"])
        or payload["questions_version"] != QUESTION_CATALOG_VERSION
    ):
        problems.append(
            QuestionCatalogProblem(
                code="MQ-VERSION-003",
                pointer="/questions_version",
                message="Frågekatalogens innehållsversion måste vara SemVer x.y.z.",
                expected=QUESTION_CATALOG_VERSION,
                actual=payload["questions_version"],
            )
        )

    if payload["operator_language"] != QUESTION_CATALOG_OPERATOR_LANGUAGE:
        problems.append(
            QuestionCatalogProblem(
                code="MQ-LANGUAGE-001",
                pointer="/operator_language",
                message="Frågekatalogens operatörsspråk stöds inte.",
                expected=QUESTION_CATALOG_OPERATOR_LANGUAGE,
                actual=payload["operator_language"],
            )
        )

    raw_sections = payload["sections"]
    sections = [
        ManifestQuestionSection.from_mapping(item) for item in raw_sections
    ]
    section_ids = [section.id for section in sections]
    schema_properties = form_schema.get("properties")
    if not isinstance(schema_properties, Mapping):
        raise TypeError("Regionblankettens schema saknar properties")
    expected_section_ids = [
        str(name)
        for name in schema_properties
        if name not in {"$schema", "form_schema_version"}
    ]
    duplicate_section_ids = sorted(
        section_id
        for section_id in set(section_ids)
        if section_ids.count(section_id) > 1
    )
    if duplicate_section_ids:
        problems.append(
            QuestionCatalogProblem(
                code="MQ-SECTION-001",
                pointer="/sections",
                message="Varje sektions-id måste vara unikt.",
                expected="unika sektions-id",
                actual=duplicate_section_ids,
            )
        )
    if section_ids != expected_section_ids:
        problems.append(
            QuestionCatalogProblem(
                code="MQ-SECTION-002",
                pointer="/sections",
                message=(
                    "Frågekatalogens sektioner måste motsvara blankettens "
                    "schemaordning exakt."
                ),
                expected=expected_section_ids,
                actual=section_ids,
            )
        )

    raw_questions = payload["questions"]
    ids: dict[str, int] = {}
    paths: dict[str, int] = {}
    questions: list[ManifestQuestion] = []
    for index, raw_question in enumerate(raw_questions):
        question = ManifestQuestion.from_mapping(raw_question)
        questions.append(question)
        if not _QUESTION_ID_RE.fullmatch(question.id):
            problems.append(
                QuestionCatalogProblem(
                    code="MQ-ID-001",
                    pointer=f"/questions/{index}/id",
                    message="Fråge-id har ogiltigt format.",
                    expected="^[a-z][a-z0-9_.-]*$",
                    actual=question.id,
                )
            )
        if question.id in ids:
            problems.append(
                QuestionCatalogProblem(
                    code="MQ-ID-002",
                    pointer=f"/questions/{index}/id",
                    message="Fråge-id är inte unikt.",
                    expected=f"unikt; första förekomst {ids[question.id]}",
                    actual=question.id,
                )
            )
        else:
            ids[question.id] = index
        if not _valid_target_path(question.target_path):
            problems.append(
                QuestionCatalogProblem(
                    code="MQ-PATH-001",
                    pointer=f"/questions/{index}/target_path",
                    message="Frågans target_path är inte en giltig JSON-pointermall.",
                    expected="absolut JSON-pointer; * för en upprepad deklarationsplats",
                    actual=question.target_path,
                )
            )
        if question.target_path in paths:
            problems.append(
                QuestionCatalogProblem(
                    code="MQ-PATH-002",
                    pointer=f"/questions/{index}/target_path",
                    message="Frågans target_path är inte unik.",
                    expected=f"unikt; första förekomst {paths[question.target_path]}",
                    actual=question.target_path,
                )
            )
        else:
            paths[question.target_path] = index

    expected_paths = set(schema_leaf_target_paths(form_schema))
    actual_paths = set(paths)
    for schema_path in sorted(expected_paths):
        matching_paths = [
            target_path
            for target_path in actual_paths
            if _question_matches_pointer(target_path, schema_path)
        ]
        if len(matching_paths) != 1:
            problems.append(
                QuestionCatalogProblem(
                    code="MQ-COVERAGE-001",
                    pointer=schema_path,
                    message="Ett schemafält måste täckas av exakt en formulärfråga.",
                    expected=1,
                    actual=len(matching_paths),
                )
            )
    for target_path in sorted(actual_paths):
        if not any(
            _question_matches_pointer(target_path, schema_path)
            for schema_path in expected_paths
        ):
            problems.append(
                QuestionCatalogProblem(
                    code="MQ-COVERAGE-002",
                    pointer=target_path,
                    message="Frågan pekar på ett fält som inte finns i blankettens schema.",
                    expected="ett schemafält i aktiv version",
                    actual=target_path,
                )
            )

    question_by_path = {
        question.target_path: question for question in questions
    }
    review_capability_question = question_by_path.get(
        "/access/local_review/allowed_capabilities"
    )
    access_schema = (form_schema.get("$defs") or {}).get("access") or {}
    access_properties = access_schema.get("properties") or {}
    local_review_schema = access_properties.get("local_review") or {}
    local_review_properties = local_review_schema.get("properties") or {}
    capability_schema = local_review_properties.get("allowed_capabilities") or {}
    expected_review_capabilities = (capability_schema.get("items") or {}).get(
        "enum"
    )
    if (
        review_capability_question is not None
        and isinstance(expected_review_capabilities, list)
        and review_capability_question.allowed_values
        != expected_review_capabilities
    ):
        problems.append(
            QuestionCatalogProblem(
                code="MQ-ALLOWED-001",
                pointer="/access/local_review/allowed_capabilities",
                message=(
                    "Reviewfrågans val måste vara exakt capability-id:na i "
                    "blankettens workspace-profilkontrakt."
                ),
                expected=expected_review_capabilities,
                actual=review_capability_question.allowed_values,
            )
        )
    for target_path in _REQUIRED_GENERATED_TARGET_PATHS:
        question = question_by_path.get(target_path)
        if question is not None and not question.generated:
            problems.append(
                QuestionCatalogProblem(
                    code="MQ-GENERATED-001",
                    pointer=target_path,
                    message="Ett tekniskt integritets- eller profilfält måste vara verktygsgenererat.",
                    expected=True,
                    actual=False,
                )
            )

    if form is not None:
        for pointer in form_leaf_target_paths(form):
            matching = [
                question
                for question in questions
                if _question_matches_pointer(question.target_path, pointer)
            ]
            if len(matching) != 1:
                problems.append(
                    QuestionCatalogProblem(
                        code="MQ-TEMPLATE-001",
                        pointer=pointer,
                        message="Mallfältet måste matcha exakt en formulärfråga.",
                        expected=1,
                        actual=len(matching),
                    )
                )

    return tuple(
        sorted(problems, key=lambda item: (item.pointer, item.code, item.message))
    )


def load_region_package_questions(
    path: Path | None = None,
    *,
    form_schema: Mapping[str, Any],
    form: Mapping[str, Any] | None = None,
    expected_form_schema_version: str,
) -> tuple[ManifestQuestion, ...]:
    """Load a valid catalog or raise with every deterministic defect."""

    payload = load_question_catalog_payload(path)
    problems = validate_question_catalog(
        payload,
        form_schema=form_schema,
        form=form,
        expected_form_schema_version=expected_form_schema_version,
    )
    if problems:
        details = "; ".join(
            f"{problem.code} {problem.pointer}: {problem.message}"
            for problem in problems
        )
        raise ValueError(f"Regionblankettens frågekatalog är ogiltig: {details}")
    return tuple(
        ManifestQuestion.from_mapping(item) for item in payload["questions"]
    )


def load_region_package_question_sections(
    path: Path | None = None,
    *,
    form_schema: Mapping[str, Any],
    expected_form_schema_version: str,
) -> tuple[ManifestQuestionSection, ...]:
    """Load schema-ordered section copy from the validated catalog."""

    payload = load_question_catalog_payload(path)
    problems = validate_question_catalog(
        payload,
        form_schema=form_schema,
        expected_form_schema_version=expected_form_schema_version,
    )
    if problems:
        details = "; ".join(
            f"{problem.code} {problem.pointer}: {problem.message}"
            for problem in problems
        )
        raise ValueError(f"Regionblankettens frågekatalog är ogiltig: {details}")
    return tuple(
        ManifestQuestionSection.from_mapping(item) for item in payload["sections"]
    )


__all__ = [
    "ManifestQuestion",
    "ManifestQuestionSection",
    "QUESTION_CATALOG_OPERATOR_LANGUAGE",
    "QUESTION_CATALOG_RELATIVE_PATH",
    "QUESTION_CATALOG_SCHEMA_RELATIVE_PATH",
    "QUESTION_CATALOG_SCHEMA_VERSION",
    "QUESTION_CATALOG_VERSION",
    "QuestionCatalogProblem",
    "default_question_catalog_path",
    "default_question_catalog_schema_path",
    "form_leaf_target_paths",
    "load_question_catalog_payload",
    "load_question_catalog_schema",
    "load_region_package_questions",
    "load_region_package_question_sections",
    "match_question_for_pointer",
    "schema_leaf_target_paths",
    "validate_question_catalog",
]
