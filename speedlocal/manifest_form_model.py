from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Final

from jsonschema import Draft202012Validator

from .manifest_questions import (
    ManifestQuestion,
    ManifestQuestionSection,
    load_region_package_questions,
    load_region_package_question_sections,
    match_question_for_pointer,
)
from .manifest_schema import (
    ManifestProblem,
    REGION_PACKAGE_FORM_VERSION,
    load_region_package_schema,
    validate_region_package,
)
from .paths import repo_root


ONBOARDING_FORM_SECTIONS: Final[tuple[str, ...]] = (
    "region",
    "access",
    "map_h3",
    "geography",
    "landscape",
)
DEFERRED_FORM_OBJECTS: Final[frozenset[str]] = frozenset(
    {"/geography/technology_support"}
)
STATE_REASON_ONLY_FORM_OBJECTS: Final[frozenset[str]] = frozenset(
    {"/landscape"}
)
IMPORT_REQUIRED_BRANCH_OBJECTS: Final[frozenset[str]] = frozenset(
    {
        "/geography/boundary",
        "/geography/standard_analysis_domain",
    }
)
REGION_PACKAGE_TEMPLATE_RELATIVE_PATH: Final[Path] = Path(
    "regions/templates/region-package.form.json"
)

_MISSING = object()


class ManifestFormModelError(ValueError):
    """A deterministic, operator-safe failure in the UI-free form model."""


class ManifestFormFieldError(ManifestFormModelError):
    """One catalog-backed field failure from an atomic form submission."""

    def __init__(
        self,
        *,
        question_id: str,
        pointer: str,
        label: str,
        help_text: str,
        example: Any,
        cause: str,
    ) -> None:
        self.question_id = question_id
        self.pointer = pointer
        self.label = label
        self.help_text = help_text
        self.example = _json_copy(example)
        self.cause = cause
        super().__init__(
            f"Fältet {pointer} kunde inte tillämpas. {help_text}"
        )


@dataclass(frozen=True)
class ManifestFormFieldSpec:
    """One concrete, question-backed field in the bounded onboarding form."""

    section: str
    pointer: str
    question_id: str
    label: str
    help: str
    required_when_text: str
    value_type: str
    unit: str | None
    allowed_values: Any
    example: Any
    required: bool
    present: bool
    value: Any
    generated: bool
    has_const: bool
    const_value: Any
    branch_selector: bool
    branch_values: tuple[Any, ...]
    locked: bool
    lock_reason: str | None


@dataclass(frozen=True)
class ManifestFormSectionView:
    """One question-catalog section with its schema-derived visible fields."""

    id: str
    title: str
    description: str
    fields: tuple[ManifestFormFieldSpec, ...]


@dataclass(frozen=True)
class BranchSwitchResult:
    """A branch-pruned draft plus an out-of-payload reversible value stash."""

    form: dict[str, Any]
    stash: dict[str, dict[str, dict[str, Any]]]
    object_pointer: str
    discriminator_pointer: str
    previous_value: Any
    selected_value: Any


@dataclass(frozen=True)
class FormSubmissionResult:
    """One atomic first-form submission and its session-only branch stash."""

    form: dict[str, Any]
    stash: dict[str, dict[str, dict[str, Any]]]
    applied_pointers: tuple[str, ...]
    branch_switches: tuple[str, ...]


@dataclass(frozen=True)
class FormDiffEntry:
    """One semantic leaf change in the bounded onboarding form."""

    pointer: str
    change: str
    before_present: bool
    after_present: bool
    before: Any
    after: Any


@dataclass(frozen=True)
class FormInspection:
    """One non-mutating imported-form preview with actionable validation."""

    form: dict[str, Any]
    json_bytes: bytes
    diff: tuple[FormDiffEntry, ...]
    problems: tuple[ManifestProblem, ...]


def _pointer(parts: Sequence[object]) -> str:
    return "/" + "/".join(
        str(part).replace("~", "~0").replace("/", "~1")
        for part in parts
    )


def _pointer_parts(pointer: str) -> tuple[str, ...]:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ManifestFormModelError(
            f"JSON pointer must be absolute: {pointer!r}"
        )
    if pointer == "/":
        raise ManifestFormModelError("The document root is not an editable field")
    parts: list[str] = []
    for raw_part in pointer[1:].split("/"):
        if not raw_part:
            raise ManifestFormModelError(
                f"JSON pointer has an empty segment: {pointer!r}"
            )
        index = 0
        while index < len(raw_part):
            if raw_part[index] == "~":
                if index + 1 >= len(raw_part) or raw_part[index + 1] not in {
                    "0",
                    "1",
                }:
                    raise ManifestFormModelError(
                        f"JSON pointer has invalid escaping: {pointer!r}"
                    )
                index += 2
                continue
            index += 1
        parts.append(raw_part.replace("~1", "/").replace("~0", "~"))
    return tuple(parts)


def _assert_onboarding_form_pointer(pointer: str) -> tuple[str, ...]:
    parts = _pointer_parts(pointer)
    if parts[0] not in ONBOARDING_FORM_SECTIONS:
        raise ManifestFormModelError(
            "The active onboarding form may edit only region, access, map_h3, "
            "bounded geography, and bounded landscape fields"
        )
    return parts


def _json_copy(value: Any) -> Any:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ManifestFormModelError(
            f"Form values must be finite JSON values: {exc}"
        ) from exc
    return json.loads(encoded)


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ManifestFormModelError(f"{label} must be a JSON object")
    return value


def _resolve_local_ref(
    root_schema: Mapping[str, Any],
    reference: object,
    *,
    active_refs: tuple[str, ...] = (),
) -> Mapping[str, Any]:
    if not isinstance(reference, str) or not reference.startswith("#/"):
        raise ManifestFormModelError(
            f"Only strict local schema references are supported: {reference!r}"
        )
    if reference in active_refs:
        raise ManifestFormModelError(
            f"Circular local schema reference: {reference!r}"
        )
    current: Any = root_schema
    for raw_part in reference[2:].split("/"):
        if not raw_part:
            raise ManifestFormModelError(
                f"Local schema reference has an empty segment: {reference!r}"
            )
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or part not in current:
            raise ManifestFormModelError(
                f"Local schema reference cannot be resolved: {reference!r}"
            )
        current = current[part]
    if not isinstance(current, Mapping):
        raise ManifestFormModelError(
            f"Local schema reference does not resolve to an object: {reference!r}"
        )
    return current


def _merge_schema_nodes(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge the structural subset needed by this bounded schema traversal."""

    result = deepcopy(dict(left))
    for key, raw_value in right.items():
        value = deepcopy(raw_value)
        if key not in result:
            result[key] = value
            continue
        current = result[key]
        if current == value:
            continue
        if key == "properties":
            current_properties = _mapping(
                current,
                label="allOf properties",
            )
            next_properties = _mapping(value, label="allOf properties")
            merged_properties = deepcopy(dict(current_properties))
            for property_name, property_schema in next_properties.items():
                if property_name in merged_properties:
                    merged_properties[property_name] = _merge_schema_nodes(
                        _mapping(
                            merged_properties[property_name],
                            label=f"schema property {property_name}",
                        ),
                        _mapping(
                            property_schema,
                            label=f"schema property {property_name}",
                        ),
                    )
                else:
                    merged_properties[property_name] = deepcopy(property_schema)
            result[key] = merged_properties
            continue
        if key == "required":
            if not isinstance(current, list) or not isinstance(value, list):
                raise ManifestFormModelError("allOf required must be arrays")
            result[key] = list(dict.fromkeys([*current, *value]))
            continue
        if key in {"minimum", "exclusiveMinimum", "minLength", "minItems"}:
            result[key] = max(current, value)
            continue
        if key in {"maximum", "exclusiveMaximum", "maxLength", "maxItems"}:
            result[key] = min(current, value)
            continue
        if key == "enum":
            if not isinstance(current, list) or not isinstance(value, list):
                raise ManifestFormModelError("allOf enum must be arrays")
            result[key] = [item for item in current if item in value]
            if not result[key]:
                raise ManifestFormModelError("allOf enum intersection is empty")
            continue
        if key == "additionalProperties" and (
            current is False or value is False
        ):
            result[key] = False
            continue
        if key in {"description", "examples", "title"}:
            # Presentation metadata never changes validation behavior.
            continue
        raise ManifestFormModelError(
            f"Unsupported conflicting allOf keyword in first slice: {key!r}"
        )
    return result


def _normalize_schema_node(
    root_schema: Mapping[str, Any],
    raw_node: Mapping[str, Any],
    *,
    active_refs: tuple[str, ...] = (),
) -> dict[str, Any]:
    node = deepcopy(dict(raw_node))
    reference = node.pop("$ref", None)
    if reference is not None:
        resolved = _resolve_local_ref(
            root_schema,
            reference,
            active_refs=active_refs,
        )
        normalized_reference = _normalize_schema_node(
            root_schema,
            resolved,
            active_refs=(*active_refs, str(reference)),
        )
        node = _merge_schema_nodes(normalized_reference, node)

    all_of = node.pop("allOf", None)
    if all_of is not None:
        if (
            not isinstance(all_of, Sequence)
            or isinstance(all_of, (str, bytes))
            or not all_of
        ):
            raise ManifestFormModelError("allOf must be a non-empty array")
        merged = node
        for item in all_of:
            merged = _merge_schema_nodes(
                merged,
                _normalize_schema_node(
                    root_schema,
                    _mapping(item, label="allOf item"),
                    active_refs=active_refs,
                ),
            )
        node = merged
    return node


def _validation_schema(
    root_schema: Mapping[str, Any],
    node: Mapping[str, Any],
) -> dict[str, Any]:
    value = deepcopy(dict(node))
    value.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
    if "$defs" not in value and isinstance(root_schema.get("$defs"), Mapping):
        value["$defs"] = deepcopy(root_schema["$defs"])
    return value


def _schema_accepts(
    root_schema: Mapping[str, Any],
    node: Mapping[str, Any],
    value: Any,
) -> bool:
    return Draft202012Validator(
        _validation_schema(root_schema, node)
    ).is_valid(value)


def _one_of_branch_details(
    root_schema: Mapping[str, Any],
    node: Mapping[str, Any],
) -> tuple[tuple[dict[str, Any], ...], str, tuple[Any, ...]]:
    raw_branches = node.get("oneOf")
    if (
        not isinstance(raw_branches, Sequence)
        or isinstance(raw_branches, (str, bytes))
        or len(raw_branches) < 2
    ):
        raise ManifestFormModelError(
            "Branch switching requires a schema oneOf with at least two branches"
        )
    branches = tuple(
        _normalize_schema_node(
            root_schema,
            _mapping(item, label="oneOf branch"),
        )
        for item in raw_branches
    )
    const_names: set[str] | None = None
    const_by_branch: list[dict[str, Any]] = []
    for branch in branches:
        properties = _mapping(
            branch.get("properties", {}),
            label="oneOf branch properties",
        )
        constants = {
            str(name): property_schema["const"]
            for name, property_schema in properties.items()
            if isinstance(property_schema, Mapping)
            and "const" in property_schema
        }
        const_by_branch.append(constants)
        names = set(constants)
        const_names = names if const_names is None else const_names.intersection(names)
    candidates = sorted(const_names or ())
    unique_discriminators = [
        name
        for name in candidates
        if len(
            {
                json.dumps(
                    constants[name],
                    ensure_ascii=False,
                    sort_keys=True,
                    allow_nan=False,
                )
                for constants in const_by_branch
            }
        )
        == len(branches)
    ]
    if len(unique_discriminators) != 1:
        raise ManifestFormModelError(
            "The onboarding-form oneOf must have one unique const discriminator"
        )
    discriminator = unique_discriminators[0]
    values = tuple(constants[discriminator] for constants in const_by_branch)
    return branches, discriminator, values


def _selected_one_of_branch(
    root_schema: Mapping[str, Any],
    node: Mapping[str, Any],
    current_value: Any,
) -> tuple[dict[str, Any], str, tuple[Any, ...]]:
    branches, discriminator, values = _one_of_branch_details(root_schema, node)
    if isinstance(current_value, Mapping) and discriminator in current_value:
        selected = [
            branch
            for branch, expected in zip(branches, values)
            if current_value[discriminator] == expected
        ]
        if len(selected) == 1:
            return selected[0], discriminator, values
        raise ManifestFormModelError(
            f"Unsupported {discriminator!r} branch value: "
            f"{current_value[discriminator]!r}"
        )
    valid = [
        branch
        for branch in branches
        if _schema_accepts(root_schema, branch, current_value)
    ]
    if len(valid) == 1:
        return valid[0], discriminator, values
    raise ManifestFormModelError(
        f"Cannot select oneOf branch without {discriminator!r}"
    )


def _effective_schema_node(
    root_schema: Mapping[str, Any],
    raw_node: Mapping[str, Any],
    current_value: Any,
) -> tuple[dict[str, Any], dict[str, tuple[Any, ...]]]:
    node = _normalize_schema_node(root_schema, raw_node)
    selectors: dict[str, tuple[Any, ...]] = {}
    while "oneOf" in node:
        branch, discriminator, values = _selected_one_of_branch(
            root_schema,
            node,
            current_value,
        )
        selectors[discriminator] = values
        base = {key: value for key, value in node.items() if key != "oneOf"}
        node = _merge_schema_nodes(base, branch)
    return node, selectors


def _strict_object_properties(
    value: Any,
    node: Mapping[str, Any],
    *,
    pointer: str,
) -> Mapping[str, Any]:
    current = _mapping(value, label=f"form object {pointer}")
    properties = _mapping(
        node.get("properties", {}),
        label=f"schema properties {pointer}",
    )
    if node.get("additionalProperties") is False:
        hidden = sorted(set(current).difference(properties))
        if hidden:
            raise ManifestFormModelError(
                f"Form object {pointer} contains forbidden hidden fields: "
                + ", ".join(hidden)
            )
    return current


def _question_for_pointer(
    pointer: str,
    questions: Sequence[ManifestQuestion],
) -> ManifestQuestion:
    question = match_question_for_pointer(pointer, questions)
    if question is None:
        raise ManifestFormModelError(
            f"Field {pointer} must match exactly one manifest question"
        )
    return question


def _inferred_schema_type(node: Mapping[str, Any]) -> str | None:
    node_type = node.get("type")
    if isinstance(node_type, str):
        return node_type
    if "const" not in node:
        return None
    value = node["const"]
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return None


def _assert_question_type(
    question: ManifestQuestion,
    node: Mapping[str, Any],
    pointer: str,
) -> None:
    node_type = _inferred_schema_type(node)
    expected_types = {
        "text": {"string"},
        "file_reference": {"string"},
        "date": {"string"},
        "uri": {"string"},
        "boolean": {"boolean"},
        "number": {"number", "integer"},
        "integer": {"integer"},
        "choice": {"string", "number", "integer"},
        "list": {"array"},
    }
    if question.type not in expected_types:
        raise ManifestFormModelError(
            f"Unsupported question type for {pointer}: {question.type!r}"
        )
    if node_type not in expected_types[question.type]:
        raise ManifestFormModelError(
            f"Question type and schema type disagree for {pointer}: "
            f"{question.type!r} versus {node_type!r}"
        )


def _is_structured_node(
    root_schema: Mapping[str, Any],
    raw_node: Mapping[str, Any],
    current_value: Any,
) -> bool:
    node, _selectors = _effective_schema_node(
        root_schema,
        raw_node,
        current_value,
    )
    return node.get("type") == "object" or isinstance(
        node.get("properties"),
        Mapping,
    )


def _field_specs_for_object(
    *,
    root_schema: Mapping[str, Any],
    raw_node: Mapping[str, Any],
    current_value: Any,
    parts: tuple[str, ...],
    section: str,
    questions: Sequence[ManifestQuestion],
    allowed_property_names: frozenset[str] | None = None,
) -> list[ManifestFormFieldSpec]:
    object_pointer = _pointer(parts)
    node, selectors = _effective_schema_node(
        root_schema,
        raw_node,
        current_value,
    )
    current = _strict_object_properties(
        current_value,
        node,
        pointer=object_pointer,
    )
    properties = _mapping(
        node.get("properties", {}),
        label=f"schema properties {object_pointer}",
    )
    required_names = set(node.get("required", ()))
    specs: list[ManifestFormFieldSpec] = []
    for property_name, property_schema in properties.items():
        if (
            allowed_property_names is not None
            and property_name not in allowed_property_names
        ):
            continue
        if not isinstance(property_name, str) or not isinstance(
            property_schema,
            Mapping,
        ):
            raise ManifestFormModelError(
                f"Invalid schema property in {object_pointer}"
            )
        child_parts = (*parts, property_name)
        child_pointer = _pointer(child_parts)
        present = property_name in current
        child_value = current.get(property_name)
        if _is_structured_node(root_schema, property_schema, child_value):
            if not present:
                if property_name in required_names:
                    raise ManifestFormModelError(
                        f"Required form object is missing: {child_pointer}"
                    )
                continue
            specs.extend(
                _field_specs_for_object(
                    root_schema=root_schema,
                    raw_node=property_schema,
                    current_value=child_value,
                    parts=child_parts,
                    section=section,
                    questions=questions,
                    allowed_property_names=(
                        frozenset({"state", "reason"})
                        if child_pointer
                        in DEFERRED_FORM_OBJECTS
                        | STATE_REASON_ONLY_FORM_OBJECTS
                        else None
                    ),
                )
            )
            continue

        leaf_node, leaf_selectors = _effective_schema_node(
            root_schema,
            property_schema,
            child_value,
        )
        if leaf_node.get("type") == "array":
            items = leaf_node.get("items")
            prefix_items = leaf_node.get("prefixItems")
            structured_items = (
                isinstance(items, Mapping)
                and _is_structured_node(root_schema, items, None)
            ) or (
                isinstance(prefix_items, Sequence)
                and not isinstance(prefix_items, (str, bytes))
                and any(
                    isinstance(item, Mapping)
                    and _is_structured_node(root_schema, item, None)
                    for item in prefix_items
                )
            )
            if structured_items:
                raise ManifestFormModelError(
                    f"Structured arrays are outside the first form slice: {child_pointer}"
                )
        elif leaf_node.get("type") == "object" or isinstance(
            leaf_node.get("properties"),
            Mapping,
        ):
            raise ManifestFormModelError(
                f"Unresolved object field in first form slice: {child_pointer}"
            )

        question = _question_for_pointer(child_pointer, questions)
        _assert_question_type(question, leaf_node, child_pointer)
        branch_values = selectors.get(
            property_name,
            leaf_selectors.get(property_name, ()),
        )
        has_const = "const" in leaf_node
        branch_selector = bool(branch_values)
        lock_reason = (
            "deferred_section"
            if object_pointer in DEFERRED_FORM_OBJECTS
            and property_name == "state"
            else "state_reason_only"
            if object_pointer in STATE_REASON_ONLY_FORM_OBJECTS
            and property_name == "state"
            else "complete_import_required"
            if object_pointer in IMPORT_REQUIRED_BRANCH_OBJECTS
            and property_name == "state"
            else "generated"
            if question.generated
            else "branch_selector"
            if branch_selector
            else "const"
            if has_const
            else None
        )
        specs.append(
            ManifestFormFieldSpec(
                section=section,
                pointer=child_pointer,
                question_id=question.id,
                label=question.question,
                help=question.help,
                required_when_text=question.required_when,
                value_type=question.type,
                unit=question.unit,
                allowed_values=_json_copy(question.allowed_values),
                example=_json_copy(question.example),
                required=property_name in required_names,
                present=present,
                value=_json_copy(child_value) if present else None,
                generated=question.generated,
                has_const=has_const,
                const_value=(
                    _json_copy(leaf_node["const"])
                    if has_const
                    else None
                ),
                branch_selector=branch_selector,
                branch_values=tuple(_json_copy(item) for item in branch_values),
                locked=lock_reason is not None,
                lock_reason=lock_reason,
            )
        )
    return specs


def build_onboarding_form_field_specs(
    form: Mapping[str, Any],
    *,
    schema: Mapping[str, Any] | None = None,
    questions: Sequence[ManifestQuestion] | None = None,
) -> tuple[ManifestFormFieldSpec, ...]:
    """Build deterministic fields for the active bounded onboarding sections.

    JSON Schema is the sole source of structure, required fields, constraints,
    and active ``oneOf`` branches. ``required_when`` remains presentation text
    only and is deliberately never parsed or evaluated.
    """

    active_schema = schema if schema is not None else load_region_package_schema()
    active_questions = tuple(questions) if questions is not None else (
        load_region_package_questions(
            form_schema=active_schema,
            expected_form_schema_version=REGION_PACKAGE_FORM_VERSION,
        )
    )
    value = _mapping(form, label="region form")
    root_node, _root_selectors = _effective_schema_node(
        active_schema,
        active_schema,
        value,
    )
    root_properties = _mapping(
        root_node.get("properties", {}),
        label="region form schema properties",
    )
    specs: list[ManifestFormFieldSpec] = []
    for section in ONBOARDING_FORM_SECTIONS:
        raw_section_schema = root_properties.get(section)
        if not isinstance(raw_section_schema, Mapping):
            raise ManifestFormModelError(
                f"Onboarding-form schema section is missing: {section}"
            )
        if section not in value:
            raise ManifestFormModelError(
                f"Onboarding-form section is missing: /{section}"
            )
        specs.extend(
            _field_specs_for_object(
                root_schema=active_schema,
                raw_node=raw_section_schema,
                current_value=value[section],
                parts=(section,),
                section=section,
                questions=active_questions,
                allowed_property_names=(
                    frozenset({"state", "reason"})
                    if f"/{section}" in STATE_REASON_ONLY_FORM_OBJECTS
                    else None
                ),
            )
        )
    pointers = [item.pointer for item in specs]
    if len(set(pointers)) != len(pointers):
        raise ManifestFormModelError("First-slice field pointers are not unique")
    return tuple(specs)


def build_onboarding_form_view(
    form: Mapping[str, Any],
    *,
    schema: Mapping[str, Any] | None = None,
    questions: Sequence[ManifestQuestion] | None = None,
    sections: Sequence[ManifestQuestionSection] | None = None,
) -> tuple[ManifestFormSectionView, ...]:
    """Project the active catalog sections without UI behavior."""

    active_schema = schema if schema is not None else load_region_package_schema()
    active_questions = tuple(questions) if questions is not None else (
        load_region_package_questions(
            form_schema=active_schema,
            expected_form_schema_version=REGION_PACKAGE_FORM_VERSION,
        )
    )
    active_sections = tuple(sections) if sections is not None else (
        load_region_package_question_sections(
            form_schema=active_schema,
            expected_form_schema_version=REGION_PACKAGE_FORM_VERSION,
        )
    )
    section_ids = tuple(section.id for section in active_sections)
    if section_ids[: len(ONBOARDING_FORM_SECTIONS)] != ONBOARDING_FORM_SECTIONS:
        raise ManifestFormModelError(
            "Question sections do not match the onboarding-form schema order"
        )
    fields = build_onboarding_form_field_specs(
        form,
        schema=active_schema,
        questions=active_questions,
    )
    section_by_id = {section.id: section for section in active_sections}
    return tuple(
        ManifestFormSectionView(
            id=section_id,
            title=section_by_id[section_id].title,
            description=section_by_id[section_id].description,
            fields=tuple(field for field in fields if field.section == section_id),
        )
        for section_id in ONBOARDING_FORM_SECTIONS
    )


def _schema_node_for_field(
    form: Mapping[str, Any],
    pointer: str,
    *,
    schema: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    parts = _assert_onboarding_form_pointer(pointer)
    current_value: Any = form
    raw_node: Mapping[str, Any] = schema
    required = False
    for index, part in enumerate(parts):
        node, _selectors = _effective_schema_node(
            schema,
            raw_node,
            current_value,
        )
        properties = _mapping(
            node.get("properties", {}),
            label=f"schema properties {_pointer(parts[:index]) if index else '/'}",
        )
        child = properties.get(part)
        if not isinstance(child, Mapping):
            raise ManifestFormModelError(f"Unknown form field: {pointer}")
        required = part in set(node.get("required", ()))
        if isinstance(current_value, Mapping):
            current_value = current_value.get(part)
        else:
            current_value = None
        raw_node = child
    node, _selectors = _effective_schema_node(schema, raw_node, current_value)
    return node, required


def _spec_by_pointer(
    form: Mapping[str, Any],
    pointer: str,
    *,
    schema: Mapping[str, Any],
    questions: Sequence[ManifestQuestion],
) -> ManifestFormFieldSpec:
    matches = [
        item
        for item in build_onboarding_form_field_specs(
            form,
            schema=schema,
            questions=questions,
        )
        if item.pointer == pointer
    ]
    if len(matches) != 1:
        raise ManifestFormModelError(
            f"Field is not editable in the active onboarding branch: {pointer}"
        )
    return matches[0]


def _set_pointer_value(
    document: MutableMapping[str, Any],
    parts: Sequence[str],
    value: Any,
) -> None:
    current: Any = document
    for part in parts[:-1]:
        if not isinstance(current, MutableMapping) or part not in current:
            raise ManifestFormModelError(
                f"Cannot traverse missing object at {_pointer(parts)}"
            )
        current = current[part]
    if not isinstance(current, MutableMapping):
        raise ManifestFormModelError(
            f"Pointer parent is not an object: {_pointer(parts)}"
        )
    current[parts[-1]] = _json_copy(value)


def set_form_value(
    form: Mapping[str, Any],
    pointer: str,
    value: Any,
    *,
    schema: Mapping[str, Any] | None = None,
    questions: Sequence[ManifestQuestion] | None = None,
) -> dict[str, Any]:
    """Safely set one active human field and validate its local schema node."""

    active_schema = schema or load_region_package_schema()
    active_questions = tuple(questions) if questions is not None else (
        load_region_package_questions(
            form_schema=active_schema,
            expected_form_schema_version=REGION_PACKAGE_FORM_VERSION,
        )
    )
    parts = _assert_onboarding_form_pointer(pointer)
    spec = _spec_by_pointer(
        form,
        pointer,
        schema=active_schema,
        questions=active_questions,
    )
    if spec.locked:
        raise ManifestFormModelError(
            f"Field {pointer} is locked ({spec.lock_reason}); "
            "use branch switching for a oneOf discriminator"
        )
    node, _required = _schema_node_for_field(
        form,
        pointer,
        schema=active_schema,
    )
    errors = sorted(
        Draft202012Validator(
            _validation_schema(active_schema, node)
        ).iter_errors(value),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        raise ManifestFormModelError(
            f"Value for {pointer} does not satisfy its schema: "
            f"{errors[0].message}"
        )
    result = _json_copy(form)
    _set_pointer_value(result, parts, value)
    return result


def remove_form_value(
    form: Mapping[str, Any],
    pointer: str,
    *,
    schema: Mapping[str, Any] | None = None,
    questions: Sequence[ManifestQuestion] | None = None,
) -> dict[str, Any]:
    """Remove one optional active human field without relaxing schema rules."""

    active_schema = schema or load_region_package_schema()
    active_questions = tuple(questions) if questions is not None else (
        load_region_package_questions(
            form_schema=active_schema,
            expected_form_schema_version=REGION_PACKAGE_FORM_VERSION,
        )
    )
    parts = _assert_onboarding_form_pointer(pointer)
    spec = _spec_by_pointer(
        form,
        pointer,
        schema=active_schema,
        questions=active_questions,
    )
    if spec.locked:
        raise ManifestFormModelError(
            f"Field {pointer} is locked ({spec.lock_reason})"
        )
    if spec.required:
        raise ManifestFormModelError(f"Required field cannot be removed: {pointer}")
    result = _json_copy(form)
    current: Any = result
    for part in parts[:-1]:
        if not isinstance(current, MutableMapping) or part not in current:
            raise ManifestFormModelError(f"Cannot traverse field: {pointer}")
        current = current[part]
    if not isinstance(current, MutableMapping) or parts[-1] not in current:
        raise ManifestFormModelError(f"Field is not present: {pointer}")
    del current[parts[-1]]
    return result


def _raw_schema_node_at_object_pointer(
    form: Mapping[str, Any],
    pointer: str,
    *,
    schema: Mapping[str, Any],
) -> tuple[dict[str, Any], Any]:
    parts = _assert_onboarding_form_pointer(pointer)
    current_value: Any = form
    raw_node: Mapping[str, Any] = schema
    for index, part in enumerate(parts):
        node = _normalize_schema_node(schema, raw_node)
        if "oneOf" in node:
            branch, _discriminator, _values = _selected_one_of_branch(
                schema,
                node,
                current_value,
            )
            base = {key: value for key, value in node.items() if key != "oneOf"}
            node = _merge_schema_nodes(base, branch)
        properties = _mapping(
            node.get("properties", {}),
            label=f"schema properties {_pointer(parts[:index]) if index else '/'}",
        )
        child = properties.get(part)
        if not isinstance(child, Mapping):
            raise ManifestFormModelError(f"Unknown form object: {pointer}")
        if not isinstance(current_value, Mapping) or part not in current_value:
            raise ManifestFormModelError(f"Form object is missing: {pointer}")
        current_value = current_value[part]
        raw_node = child
    return _normalize_schema_node(schema, raw_node), current_value


def _stash_key(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def switch_one_of_branch(
    form: Mapping[str, Any],
    object_pointer: str,
    selected_value: Any,
    *,
    schema: Mapping[str, Any] | None = None,
    stash: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
) -> BranchSwitchResult:
    """Switch one object branch and prune every property forbidden there.

    Values from the old branch may be retained only in the returned, explicit
    out-of-payload stash. They can never remain hidden in exported form JSON.
    """

    active_schema = schema or load_region_package_schema()
    parts = _assert_onboarding_form_pointer(object_pointer)
    raw_node, current_value = _raw_schema_node_at_object_pointer(
        form,
        object_pointer,
        schema=active_schema,
    )
    current = _mapping(current_value, label=f"form object {object_pointer}")
    branches, discriminator, values = _one_of_branch_details(
        active_schema,
        raw_node,
    )
    if selected_value not in values:
        raise ManifestFormModelError(
            f"Unsupported {discriminator!r} branch value: {selected_value!r}"
        )
    previous_value = current.get(discriminator, _MISSING)
    if previous_value is _MISSING or previous_value not in values:
        raise ManifestFormModelError(
            f"Current form branch lacks a supported {discriminator!r} value"
        )

    next_stash: dict[str, dict[str, dict[str, Any]]] = _json_copy(stash or {})
    object_stash = next_stash.setdefault(object_pointer, {})
    object_stash[_stash_key(previous_value)] = _json_copy(current)

    target_index = values.index(selected_value)
    target_branch = branches[target_index]
    target_properties = _mapping(
        target_branch.get("properties", {}),
        label=f"target branch properties {object_pointer}",
    )
    restored = object_stash.get(_stash_key(selected_value))
    candidate_source = restored if isinstance(restored, Mapping) else current
    candidate = {
        name: _json_copy(candidate_source[name])
        for name in target_properties
        if name in candidate_source
    }
    for name, property_schema in target_properties.items():
        if isinstance(property_schema, Mapping) and "const" in property_schema:
            candidate[name] = _json_copy(property_schema["const"])
    # Enforce the selected discriminator even if a malformed stash attempted
    # to provide a different value.
    candidate[discriminator] = _json_copy(selected_value)

    result = _json_copy(form)
    _set_pointer_value(result, parts, candidate)
    return BranchSwitchResult(
        form=result,
        stash=next_stash,
        object_pointer=object_pointer,
        discriminator_pointer=f"{object_pointer}/{discriminator}",
        previous_value=_json_copy(previous_value),
        selected_value=_json_copy(selected_value),
    )


def apply_onboarding_form_submission(
    form: Mapping[str, Any],
    submitted_values: Mapping[str, Any],
    *,
    schema: Mapping[str, Any] | None = None,
    questions: Sequence[ManifestQuestion] | None = None,
    sections: Sequence[ManifestQuestionSection] | None = None,
    stash: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
) -> FormSubmissionResult:
    """Apply all visible bounded onboarding fields as one immutable draft edit.

    A oneOf selector is switched before ordinary fields are applied. Values
    belonging to the branch that just became inactive are ignored and may be
    retained only in the explicit returned stash. Any failure aborts the whole
    operation because neither input object is ever mutated.
    """

    if not isinstance(submitted_values, Mapping) or any(
        not isinstance(pointer, str) for pointer in submitted_values
    ):
        raise ManifestFormModelError(
            "Submitted form values must be a JSON-pointer object"
        )
    active_schema = schema or load_region_package_schema()
    active_questions = tuple(questions) if questions is not None else (
        load_region_package_questions(
            form_schema=active_schema,
            expected_form_schema_version=REGION_PACKAGE_FORM_VERSION,
        )
    )
    active_sections = tuple(sections) if sections is not None else (
        load_region_package_question_sections(
            form_schema=active_schema,
            expected_form_schema_version=REGION_PACKAGE_FORM_VERSION,
        )
    )
    visible_fields = tuple(
        field
        for section in build_onboarding_form_view(
            form,
            schema=active_schema,
            questions=active_questions,
            sections=active_sections,
        )
        for field in section.fields
    )
    expected_pointers = {field.pointer for field in visible_fields}
    submitted_pointers = set(submitted_values)
    if submitted_pointers != expected_pointers:
        missing = sorted(expected_pointers - submitted_pointers)
        unknown = sorted(submitted_pointers - expected_pointers)
        raise ManifestFormModelError(
            "Submitted fields do not match the active onboarding-form view: "
            f"missing={missing}, unknown={unknown}"
        )

    submitted = _json_copy(dict(submitted_values))
    for field in visible_fields:
        raw_value = submitted[field.pointer]
        if field.value_type != "list" or not isinstance(raw_value, str):
            continue
        try:
            parsed_value = json.loads(
                raw_value,
                parse_constant=_reject_json_constant,
            )
        except (json.JSONDecodeError, ManifestFormModelError) as exc:
            raise ManifestFormFieldError(
                question_id=field.question_id,
                pointer=field.pointer,
                label=field.label,
                help_text=field.help,
                example=field.example,
                cause=f"List values must use valid JSON array syntax: {exc}",
            ) from exc
        if not isinstance(parsed_value, list):
            raise ManifestFormFieldError(
                question_id=field.question_id,
                pointer=field.pointer,
                label=field.label,
                help_text=field.help,
                example=field.example,
                cause="List values must use valid JSON array syntax",
            )
        submitted[field.pointer] = parsed_value
    candidate = _json_copy(form)
    next_stash: dict[str, dict[str, dict[str, Any]]] = _json_copy(stash or {})
    branch_switches: list[str] = []
    for field in visible_fields:
        if not field.branch_selector:
            continue
        selected_value = submitted[field.pointer]
        if selected_value == field.value:
            continue
        if field.lock_reason in {
            "deferred_section",
            "complete_import_required",
            "state_reason_only",
        }:
            raise ManifestFormModelError(
                f"Submitted value attempted to change locked field: "
                f"{field.pointer}"
            )
        object_pointer, _separator, _discriminator = field.pointer.rpartition(
            "/"
        )
        switched = switch_one_of_branch(
            candidate,
            object_pointer,
            selected_value,
            schema=active_schema,
            stash=next_stash,
        )
        candidate = switched.form
        next_stash = switched.stash
        branch_switches.append(field.pointer)

    next_fields = {
        field.pointer: field
        for section in build_onboarding_form_view(
            candidate,
            schema=active_schema,
            questions=active_questions,
            sections=active_sections,
        )
        for field in section.fields
    }
    applied_pointers: list[str] = []
    for original_field in visible_fields:
        pointer = original_field.pointer
        if original_field.branch_selector or pointer not in next_fields:
            continue
        field = next_fields[pointer]
        value = submitted[pointer]
        if field.locked:
            if value != field.value:
                raise ManifestFormModelError(
                    f"Submitted value attempted to change locked field: {pointer}"
                )
            continue
        if not field.required and (value is None or value == ""):
            if field.present:
                candidate = remove_form_value(
                    candidate,
                    pointer,
                    schema=active_schema,
                    questions=active_questions,
                )
                applied_pointers.append(pointer)
            continue
        try:
            candidate = set_form_value(
                candidate,
                pointer,
                value,
                schema=active_schema,
                questions=active_questions,
            )
        except ManifestFormModelError as exc:
            raise ManifestFormFieldError(
                question_id=field.question_id,
                pointer=pointer,
                label=field.label,
                help_text=field.help,
                example=field.example,
                cause=str(exc),
            ) from exc
        applied_pointers.append(pointer)

    return FormSubmissionResult(
        form=candidate,
        stash=next_stash,
        applied_pointers=tuple(applied_pointers),
        branch_switches=tuple(branch_switches),
    )


def _reject_json_constant(value: str) -> None:
    raise ManifestFormModelError(f"Non-standard JSON constant is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ManifestFormModelError(f"Duplicate JSON object key: {key!r}")
        value[key] = item
    return value


def import_form_json(payload: str | bytes | bytearray) -> dict[str, Any]:
    """Parse one untrusted form document without touching the filesystem."""

    if isinstance(payload, (bytes, bytearray)):
        try:
            text = bytes(payload).decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ManifestFormModelError("Form JSON must be UTF-8") from exc
    elif isinstance(payload, str):
        text = payload.removeprefix("\ufeff")
    else:
        raise ManifestFormModelError("Form JSON must be text or UTF-8 bytes")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except ManifestFormModelError:
        raise
    except json.JSONDecodeError as exc:
        raise ManifestFormModelError(
            f"Invalid form JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    if not isinstance(value, dict):
        raise ManifestFormModelError("Form JSON root must be an object")
    schema = load_region_package_schema()
    schema_properties = _mapping(
        schema.get("properties", {}),
        label="region form schema properties",
    )
    for field_name in ("$schema", "form_schema_version"):
        field_schema = _mapping(
            schema_properties.get(field_name),
            label=f"schema field {field_name}",
        )
        expected = field_schema.get("const", _MISSING)
        if expected is _MISSING or value.get(field_name, _MISSING) != expected:
            raise ManifestFormModelError(
                f"Unsupported locked form metadata /{field_name}: "
                f"expected {expected!r}, got {value.get(field_name)!r}"
            )
    return _json_copy(value)


def default_region_package_template_path() -> Path:
    return repo_root() / REGION_PACKAGE_TEMPLATE_RELATIVE_PATH


def load_region_package_form_template(
    path: Path | None = None,
) -> dict[str, Any]:
    """Load the version-locked starter template without mutating repository state."""

    source = (path or default_region_package_template_path()).resolve()
    try:
        payload = source.read_bytes()
    except FileNotFoundError:
        raise FileNotFoundError(f"Region form template is missing: {source}") from None
    except OSError as exc:
        raise ManifestFormModelError(
            f"Region form template cannot be read: {source}: {exc}"
        ) from exc
    return import_form_json(payload)


def export_form_json(form: Mapping[str, Any]) -> bytes:
    """Serialize one form deterministically; never write or publish it."""

    _mapping(form, label="region form")
    try:
        return (
            json.dumps(
                form,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ManifestFormModelError(
            f"Form cannot be exported as finite JSON: {exc}"
        ) from exc


def _semantic_token(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def semantic_form_diff(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    section_ids: Sequence[str] = ONBOARDING_FORM_SECTIONS,
) -> tuple[FormDiffEntry, ...]:
    """Return deterministic leaf changes for the bounded onboarding form."""

    before_form = _mapping(before, label="before form")
    after_form = _mapping(after, label="after form")
    active_sections = tuple(section_ids)
    if not active_sections:
        raise ManifestFormModelError("At least one diff section is required")
    if len(set(active_sections)) != len(active_sections):
        raise ManifestFormModelError("Diff sections must be unique")
    unsupported_sections = tuple(
        section
        for section in active_sections
        if section not in ONBOARDING_FORM_SECTIONS
    )
    if unsupported_sections:
        raise ManifestFormModelError(
            "Diff sections are outside the bounded onboarding form: "
            + ", ".join(unsupported_sections)
        )
    changes: list[FormDiffEntry] = []

    def visit(
        before_value: Any,
        after_value: Any,
        parts: tuple[str, ...],
        before_present: bool,
        after_present: bool,
    ) -> None:
        if before_present and after_present and isinstance(
            before_value,
            Mapping,
        ) and isinstance(after_value, Mapping):
            keys = sorted(set(before_value).union(after_value))
            for key in keys:
                visit(
                    before_value.get(key),
                    after_value.get(key),
                    (*parts, str(key)),
                    key in before_value,
                    key in after_value,
                )
            return
        if before_present and after_present:
            if _semantic_token(before_value) == _semantic_token(after_value):
                return
            change = "changed"
        elif before_present:
            change = "removed"
        else:
            change = "added"
        changes.append(
            FormDiffEntry(
                pointer=_pointer(parts),
                change=change,
                before_present=before_present,
                after_present=after_present,
                before=_json_copy(before_value) if before_present else None,
                after=_json_copy(after_value) if after_present else None,
            )
        )

    for section in active_sections:
        visit(
            before_form.get(section),
            after_form.get(section),
            (section,),
            section in before_form,
            section in after_form,
        )
    return tuple(sorted(changes, key=lambda item: item.pointer))


def inspect_form(
    form: Mapping[str, Any],
    *,
    baseline: Mapping[str, Any],
    source: str = "<memory>",
    schema: Mapping[str, Any] | None = None,
    questions: Sequence[ManifestQuestion] | None = None,
    section_ids: Sequence[str] = ONBOARDING_FORM_SECTIONS,
) -> FormInspection:
    """Inspect one form in process without compiling, writing, or activating it."""

    candidate = _json_copy(_mapping(form, label="region form"))
    active_schema = schema if schema is not None else load_region_package_schema()
    active_questions = tuple(questions) if questions is not None else (
        load_region_package_questions(
            form_schema=active_schema,
            expected_form_schema_version=REGION_PACKAGE_FORM_VERSION,
        )
    )
    return FormInspection(
        form=candidate,
        json_bytes=export_form_json(candidate),
        diff=semantic_form_diff(
            baseline,
            candidate,
            section_ids=section_ids,
        ),
        problems=validate_region_package(
            candidate,
            source=source,
            schema=active_schema,
            questions=active_questions,
        ),
    )


def inspect_form_json(
    payload: str | bytes | bytearray,
    *,
    baseline: Mapping[str, Any],
    source: str = "<import>",
    schema: Mapping[str, Any] | None = None,
    questions: Sequence[ManifestQuestion] | None = None,
    section_ids: Sequence[str] = ONBOARDING_FORM_SECTIONS,
) -> FormInspection:
    """Strictly import and inspect one untrusted form without filesystem writes."""

    return inspect_form(
        import_form_json(payload),
        baseline=baseline,
        source=source,
        schema=schema,
        questions=questions,
        section_ids=section_ids,
    )


__all__ = [
    "BranchSwitchResult",
    "DEFERRED_FORM_OBJECTS",
    "IMPORT_REQUIRED_BRANCH_OBJECTS",
    "ONBOARDING_FORM_SECTIONS",
    "STATE_REASON_ONLY_FORM_OBJECTS",
    "FormDiffEntry",
    "FormInspection",
    "FormSubmissionResult",
    "ManifestFormFieldSpec",
    "ManifestFormFieldError",
    "ManifestFormSectionView",
    "ManifestFormModelError",
    "build_onboarding_form_field_specs",
    "build_onboarding_form_view",
    "apply_onboarding_form_submission",
    "default_region_package_template_path",
    "export_form_json",
    "inspect_form",
    "inspect_form_json",
    "import_form_json",
    "load_region_package_form_template",
    "remove_form_value",
    "semantic_form_diff",
    "set_form_value",
    "switch_one_of_branch",
]
