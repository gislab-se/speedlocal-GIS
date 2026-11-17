from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

from .access_policy import (
    ACCESS_TRUST_CLASSIFICATIONS,
    PRODUCT_LIFECYCLE,
    PRODUCT_TRUST_CLASSIFICATION,
    REVIEW_LIFECYCLE,
    product_route_request_is_valid,
)
from .combined_result_compiler import (
    combined_result_policy_contract_from_form,
)
from .manifest_questions import (
    ManifestQuestion,
    load_region_package_questions,
    match_question_for_pointer,
)
from .paths import repo_root
from .workspace import STANDARD_CAPABILITY_IDS


REGION_PACKAGE_FORM_VERSION = "1.0"
REGION_PACKAGE_SCHEMA_RELATIVE_PATH = Path(
    "schemas/speedlocal/1.0/region-package-form.schema.json"
)
STANDARD_GROUP_IDS = (
    "roads",
    "population",
    "nature",
    "culture",
    "grid_infrastructure",
)
TECHNOLOGY_IDS = ("wind", "solar")


@dataclass(frozen=True)
class ManifestProblem:
    """One stable, serializable problem from manifest validation."""

    code: str
    severity: str
    source: str
    pointer: str
    message: str
    help: str
    validator: str | None = None
    expected: Any | None = None
    actual: Any | None = None
    question_id: str | None = None
    question: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_region_package_schema_path() -> Path:
    return repo_root() / REGION_PACKAGE_SCHEMA_RELATIVE_PATH


def _json_pointer(parts: Iterable[object]) -> str:
    escaped = [
        str(part).replace("~", "~0").replace("/", "~1")
        for part in parts
    ]
    return "/" + "/".join(escaped) if escaped else "/"


def _problem(
    *,
    code: str,
    source: str,
    pointer: str,
    message: str,
    help_text: str,
    validator: str | None = None,
    expected: Any | None = None,
    actual: Any | None = None,
) -> ManifestProblem:
    return ManifestProblem(
        code=code,
        severity="error",
        source=source,
        pointer=pointer,
        message=message,
        help=help_text,
        validator=validator,
        expected=expected,
        actual=actual,
    )


def attach_manifest_problem_questions(
    problems: Iterable[ManifestProblem],
    *,
    schema: Mapping[str, Any] | None = None,
    questions: Sequence[ManifestQuestion] | None = None,
) -> tuple[ManifestProblem, ...]:
    """Attach the uniquely matching operator question to manifest problems."""

    active_schema = schema or load_region_package_schema()
    active_questions = tuple(questions) if questions is not None else (
        load_region_package_questions(
            form_schema=active_schema,
            expected_form_schema_version=REGION_PACKAGE_FORM_VERSION,
        )
    )
    attached: list[ManifestProblem] = []
    for problem in problems:
        question = match_question_for_pointer(problem.pointer, active_questions)
        if question is None:
            attached.append(problem)
            continue
        attached.append(
            replace(
                problem,
                question_id=question.id,
                question=question.question,
            )
        )
    return tuple(attached)


def load_region_package_schema(
    path: Path | None = None,
) -> dict[str, Any]:
    """Load and validate the repository-owned Draft 2020-12 schema."""

    schema_path = (path or default_region_package_schema_path()).resolve()
    try:
        payload = json.loads(schema_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Regionblankettens schema saknas: {schema_path}"
        ) from None
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Regionblankettens schema kan inte läsas: {schema_path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise TypeError("Regionblankettens schema måste vara ett JSON-objekt")
    Draft202012Validator.check_schema(payload)
    return payload


def _schema_problem(error: Any, source: str) -> ManifestProblem:
    validator = str(error.validator or "schema")
    path = list(error.absolute_path)
    expected = error.validator_value
    actual = error.instance

    if validator == "required":
        match = re.search(r"'([^']+)' is a required property", error.message)
        missing = match.group(1) if match else "okänt fält"
        pointer = _json_pointer((*path, missing))
        return _problem(
            code="MF-SCHEMA-001",
            source=source,
            pointer=pointer,
            message=f"Obligatoriskt fält saknas: {missing}.",
            help_text="Fyll i fältet enligt regionblankettens guide eller välj explicit state=unavailable där det stöds.",
            validator=validator,
            expected=missing,
            actual=None,
        )
    if validator == "type":
        return _problem(
            code="MF-SCHEMA-002",
            source=source,
            pointer=_json_pointer(path),
            message=f"Värdet har fel typ; förväntad typ är {expected}.",
            help_text="Byt värdet till den typ som anges i schemat. Skriv inte tal eller booleaner som text.",
            validator=validator,
            expected=expected,
            actual=actual,
        )
    if validator in {"enum", "const"}:
        allowed = expected if validator == "enum" else [expected]
        return _problem(
            code="MF-SCHEMA-003",
            source=source,
            pointer=_json_pointer(path),
            message="Värdet är inte ett tillåtet alternativ.",
            help_text=f"Välj ett av de deklarerade alternativen: {allowed!r}.",
            validator=validator,
            expected=allowed,
            actual=actual,
        )
    if validator == "additionalProperties":
        match = re.search(r"\('([^']+)' was unexpected\)", error.message)
        field = match.group(1) if match else "okänt fält"
        return _problem(
            code="MF-SCHEMA-004",
            source=source,
            pointer=_json_pointer((*path, field)),
            message=f"Fältet stöds inte av denna blankettversion: {field}.",
            help_text="Ta bort fältet eller migrera blanketten till en schema-version som uttryckligen stöder det.",
            validator=validator,
            expected="endast deklarerade fält",
            actual=field,
        )
    if validator in {"oneOf", "anyOf"}:
        return _problem(
            code="MF-SCHEMA-005",
            source=source,
            pointer=_json_pointer(path),
            message="Deklarationen matchar inte någon tillåten formulärvariant.",
            help_text="Kontrollera state. unavailable kräver en orsak; declared kräver det kompletta kontraktet för delen.",
            validator=validator,
            expected="en giltig deklarationsvariant",
            actual=actual,
        )
    if validator in {
        "pattern",
        "format",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "minItems",
        "maxItems",
        "uniqueItems",
        "items",
    }:
        return _problem(
            code="MF-SCHEMA-006",
            source=source,
            pointer=_json_pointer(path),
            message=f"Värdet bryter mot regeln {validator}: {error.message}",
            help_text="Följ intervallet, formatet, ordningen eller unikhetskravet som visas i fältguiden.",
            validator=validator,
            expected=expected,
            actual=actual,
        )
    return _problem(
        code="MF-SCHEMA-099",
        source=source,
        pointer=_json_pointer(path),
        message=f"Schemafel: {error.message}",
        help_text="Kontrollera fältet mot JSON Schema och den svenska fältguiden.",
        validator=validator,
        expected=expected,
        actual=actual,
    )


def _schema_problems(
    value: Mapping[str, Any],
    *,
    schema: Mapping[str, Any],
    source: str,
) -> list[ManifestProblem]:
    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    )
    errors = sorted(
        validator.iter_errors(value),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            str(error.validator),
            error.message,
        ),
    )
    problems: list[ManifestProblem] = []
    seen: set[tuple[str, str, str]] = set()
    for error in errors:
        problem = _schema_problem(error, source)
        identity = (problem.code, problem.pointer, problem.message)
        if identity not in seen:
            problems.append(problem)
            seen.add(identity)
    return problems


def _safe_provider_path(value: object) -> bool:
    text = str(value or "")
    if not text or "\\" in text or re.match(r"^[A-Za-z]:", text):
        return False
    path = PurePosixPath(text)
    return (
        not path.is_absolute()
        and path.as_posix() == text
        and text != "."
        and ".." not in path.parts
        and not any(":" in part for part in path.parts)
    )


def _walk_assets(value: Any, path: Sequence[object] = ()) -> Iterable[tuple[tuple[object, ...], Mapping[str, Any]]]:
    if isinstance(value, Mapping):
        if {"provider", "path", "format", "integrity"}.issubset(value):
            yield tuple(path), value
        for key, child in value.items():
            yield from _walk_assets(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_assets(child, (*path, index))


def _semantic_problems(
    value: Mapping[str, Any],
    *,
    source: str,
) -> list[ManifestProblem]:
    problems: list[ManifestProblem] = []
    region = value["region"]
    access = value["access"]
    map_h3 = value["map_h3"]
    geography = value["geography"]
    landscape = value["landscape"]
    groups = value["standard_groups"]
    technologies = value["technologies"]
    solar_rooftop = value["solar_rooftop"]
    combined_result = value["combined_result"]

    if access["product_route_requested"] and not product_route_request_is_valid(
        lifecycle=access["lifecycle"],
        trust_classification=access["trust_classification"],
        behavior_reference_declared=(
            region["behavior_reference"]["state"] == "declared"
        ),
    ):
        problems.append(
            _problem(
                code="MF-ACCESS-001",
                source=source,
                pointer="/access/product_route_requested",
                message="Produktrutten kan inte begäras för denna lifecycle, trust classification eller beteendereferens.",
                help_text=f"Behåll false tills regionen är {PRODUCT_LIFECYCLE}, {PRODUCT_TRUST_CLASSIFICATION} och har en deklarerad beteendereferens. En giltig begäran aktiverar fortfarande inte rutten utan genererade readiness- och acceptansgates.",
                expected=(
                    f"{PRODUCT_LIFECYCLE} + {PRODUCT_TRUST_CLASSIFICATION} + "
                    "declared behavior reference"
                ),
                actual=True,
            )
        )

    declared_groups = {
        str(group["id"])
        for group in groups
        if group["state"] == "declared"
    }
    review = access["local_review"]
    review_capabilities = review["allowed_capabilities"]
    if review["enabled"] and access["lifecycle"] != REVIEW_LIFECYCLE:
        problems.append(
            _problem(
                code="MF-ACCESS-004",
                source=source,
                pointer="/access/lifecycle",
                message="Lokal review kan endast aktiveras under onboarding.",
                help_text="Använd lifecycle=onboarding för en icke-publik lokal review. Planned saknar en körbar grind och active använder den separata produkt-/publiceringskedjan.",
                expected=REVIEW_LIFECYCLE,
                actual=access["lifecycle"],
            )
        )
    if (
        access["trust_classification"] != "diagnostic_only"
        and region["behavior_reference"]["state"] != "declared"
    ):
        problems.append(
            _problem(
                code="MF-ACCESS-005",
                source=source,
                pointer="/region/behavior_reference",
                message="Den valda tillitsnivån kräver en deklarerad beteendereferens.",
                help_text="Deklarera referenskälla, etikett och referens, eller sänk trust_classification till diagnostic_only tills evidensen finns.",
                expected="declared behavior reference",
                actual=region["behavior_reference"]["state"],
            )
        )
    if (review["enabled"] and not review_capabilities) or (
        not review["enabled"] and review_capabilities
    ):
        problems.append(
            _problem(
                code="MF-ACCESS-002",
                source=source,
                pointer="/access/local_review/allowed_capabilities",
                message="Local review och dess capability-lista motsäger varandra.",
                help_text="En aktiverad review kräver minst en deklarerad capability; en avstängd review ska ha en tom lista.",
                expected="enabled motsvarar en icke-tom capability-lista",
                actual=review_capabilities,
            )
        )
    for index, capability_id in enumerate(review_capabilities):
        if capability_id not in STANDARD_CAPABILITY_IDS:
            # The JSON Schema reports the actionable enum error. Avoid
            # interpreting an unknown id as a technology/group reference.
            continue
        if ".group." not in capability_id:
            # Non-group capabilities are legitimate review intentions. Their
            # live generic probe, not the form, decides whether interaction is
            # executable.
            continue
        technology_id, _, group_id = capability_id.partition(".group.")
        technology = technologies[technology_id]
        if (
            technology["state"] != "declared"
            or group_id not in declared_groups
            or group_id not in technology["applicable_group_ids"]
        ):
            problems.append(
                _problem(
                    code="MF-ACCESS-003",
                    source=source,
                    pointer=f"/access/local_review/allowed_capabilities/{index}",
                    message=f"Review-capabilityn {capability_id!r} saknar ett komplett deklarerat teknik-/gruppkontrakt.",
                    help_text="Deklarera gruppen och tekniken först, eller ta bort capabilityn från review-listan.",
                    expected="declared technology and group",
                    actual=capability_id,
                )
            )

    boundary = geography["boundary"]
    domain = geography["standard_analysis_domain"]
    geography_complete = (
        boundary["state"] == "declared" and domain["state"] == "declared"
    )
    if boundary["state"] == "declared":
        if boundary["native_crs"] != region["native_crs"]:
            problems.append(
                _problem(
                    code="MF-GEO-001",
                    source=source,
                    pointer="/geography/boundary/native_crs",
                    message="Gränsgeometrins native_crs matchar inte regionens native_crs.",
                    help_text="Använd samma regionala arbets-CRS i båda fälten.",
                    expected=region["native_crs"],
                    actual=boundary["native_crs"],
                )
            )
    if domain["state"] == "declared":
        if boundary["state"] != "declared" or domain["coverage_geometry_id"] != boundary.get("id"):
            problems.append(
                _problem(
                    code="MF-GEO-002",
                    source=source,
                    pointer="/geography/standard_analysis_domain/coverage_geometry_id",
                    message="Analysdomänen refererar inte till den deklarerade gränsgeometrin.",
                    help_text="Deklarera gränsen och använd exakt dess id som coverage_geometry_id.",
                    expected=boundary.get("id") if boundary["state"] == "declared" else "declared boundary",
                    actual=domain["coverage_geometry_id"],
                )
            )
        if domain["resolution"] != map_h3["analysis_resolution"]:
            problems.append(
                _problem(
                    code="MF-H3-001",
                    source=source,
                    pointer="/geography/standard_analysis_domain/resolution",
                    message="Analysdomänens H3-upplösning matchar inte kartans analysupplösning.",
                    help_text="Använd samma kanoniska analysupplösning i map_h3 och standard_analysis_domain.",
                    expected=map_h3["analysis_resolution"],
                    actual=domain["resolution"],
                )
            )
        if domain["rollup_resolutions"] != map_h3["rollup_resolutions"]:
            problems.append(
                _problem(
                    code="MF-H3-002",
                    source=source,
                    pointer="/geography/standard_analysis_domain/rollup_resolutions",
                    message="Analysdomänens rollups matchar inte map_h3.",
                    help_text="Deklarera en enda identisk rollup-lista, ordnad från finare till grövre upplösning.",
                    expected=map_h3["rollup_resolutions"],
                    actual=domain["rollup_resolutions"],
                )
            )
    technology_support = geography["technology_support"]
    declared_area_technologies = {
        technology_id
        for technology_id in TECHNOLOGY_IDS
        if technologies[technology_id]["state"] == "declared"
        and technologies[technology_id]["area_result"]["state"] == "declared"
    }
    if technology_support["state"] == "declared":
        support_technologies = set(technology_support["technologies"])
        coverage = technology_support["coverage_geometry"]
        context = technology_support["technology_context"]
        if not geography_complete:
            problems.append(
                _problem(
                    code="MF-TECH-SUPPORT-001",
                    source=source,
                    pointer="/geography/technology_support/state",
                    message="Teknikstödsdomänen kräver en deklarerad regiongräns och standardanalysdomän.",
                    help_text="Deklarera boundary och standard_analysis_domain först eller markera technology_support unavailable.",
                    expected="declared boundary and standard analysis domain",
                    actual={"boundary": boundary["state"], "domain": domain["state"]},
                )
            )
        if support_technologies != declared_area_technologies:
            problems.append(
                _problem(
                    code="MF-TECH-SUPPORT-002",
                    source=source,
                    pointer="/geography/technology_support/technologies",
                    message="Teknikstödsdomänens tekniklista matchar inte teknikerna med deklarerat area_result.",
                    help_text="Lista exakt de vind-/soltekniker vars area_result är declared; lämna ingen teknik implicit.",
                    expected=sorted(declared_area_technologies),
                    actual=technology_support["technologies"],
                )
            )
        if coverage["native_crs"] != value["region"]["native_crs"]:
            problems.append(
                _problem(
                    code="MF-TECH-SUPPORT-003",
                    source=source,
                    pointer="/geography/technology_support/coverage_geometry/native_crs",
                    message="Teknikmålytans native CRS matchar inte regionens analys-CRS.",
                    help_text="Använd region.native_crs för exakt area och H3-klippning.",
                    expected=value["region"]["native_crs"],
                    actual=coverage["native_crs"],
                )
            )
        if boundary["state"] == "declared" and coverage["id"] == boundary["id"]:
            problems.append(
                _problem(
                    code="MF-TECH-SUPPORT-004",
                    source=source,
                    pointer="/geography/technology_support/coverage_geometry/id",
                    message="Teknikmålytan behöver ett eget geografi-id och en egen technology_target_surface-roll.",
                    help_text="Använd ett separat id även om samma checksummebundna polygonfil återanvänds.",
                    expected="id distinct from geography.boundary.id",
                    actual=coverage["id"],
                )
            )
        if context["state"] == "declared" and context["resolution"] != map_h3["analysis_resolution"]:
            problems.append(
                _problem(
                    code="MF-TECH-SUPPORT-005",
                    source=source,
                    pointer="/geography/technology_support/technology_context/resolution",
                    message="Teknikkontextens H3-upplösning matchar inte teknikstödsdomänens källupplösning.",
                    help_text="Använd samma kanoniska H3-upplösning som map_h3.analysis_resolution.",
                    expected=map_h3["analysis_resolution"],
                    actual=context["resolution"],
                )
            )
        surface_id = technology_support["eligible_surface"]["id"]
        area_policies: set[tuple[str, str]] = set()
        for technology_id in sorted(declared_area_technologies):
            area = technologies[technology_id]["area_result"]
            if area["eligible_surface_id"] != surface_id:
                problems.append(
                    _problem(
                        code="MF-TECH-SUPPORT-006",
                        source=source,
                        pointer=f"/technologies/{technology_id}/area_result/eligible_surface_id",
                        message="Teknikens area_result refererar inte till regionpaketets deklarerade eligible surface.",
                        help_text="Använd exakt id:t från geography.technology_support.eligible_surface.id.",
                        expected=surface_id,
                        actual=area["eligible_surface_id"],
                    )
                )
            area_policies.add((str(area["surface_scope"]), str(area["water_policy"])))
        if len(area_policies) > 1:
            problems.append(
                _problem(
                    code="MF-TECH-SUPPORT-007",
                    source=source,
                    pointer="/geography/technology_support/eligible_surface/id",
                    message="Tekniker som delar samma eligible-surface-id deklarerar olika fysisk yta eller vattenpolicy.",
                    help_text="Använd samma surface_scope och water_policy eller deklarera separata ytkontrakt i en framtida schema-version.",
                    expected="one shared surface policy",
                    actual=sorted(area_policies),
                )
            )
    elif declared_area_technologies:
        problems.append(
            _problem(
                code="MF-TECH-SUPPORT-008",
                source=source,
                pointer="/geography/technology_support/state",
                message="Ett deklarerat area_result saknar en deklarerad teknikstödsdomän.",
                help_text="Deklarera geography.technology_support komplett eller markera area_result unavailable.",
                expected="declared",
                actual=technology_support["state"],
            )
        )
    if landscape["state"] == "declared":
        domain_reference = landscape["domain_reference"]
        if (
            domain["state"] != "declared"
            or domain_reference["domain_id"] != domain.get("domain_id")
        ):
            problems.append(
                _problem(
                    code="MF-LANDSCAPE-001",
                    source=source,
                    pointer="/landscape/domain_reference/domain_id",
                    message="Landskapet refererar inte till den deklarerade standardanalysdomänen.",
                    help_text="Deklarera standard_analysis_domain och använd exakt dess domain_id; landskapsvisning får inte låna en annan domän.",
                    expected=(
                        domain.get("domain_id")
                        if domain["state"] == "declared"
                        else "declared standard analysis domain"
                    ),
                    actual=domain_reference["domain_id"],
                )
            )
        if landscape["resolution"] != map_h3["analysis_resolution"]:
            problems.append(
                _problem(
                    code="MF-LANDSCAPE-002",
                    source=source,
                    pointer="/landscape/resolution",
                    message="Landskapets H3-upplösning matchar inte standarddomänens källupplösning.",
                    help_text="Använd map_h3.analysis_resolution för landskapets källceller.",
                    expected=map_h3["analysis_resolution"],
                    actual=landscape["resolution"],
                )
            )
        if landscape["rollup_resolutions"] != map_h3["rollup_resolutions"]:
            problems.append(
                _problem(
                    code="MF-LANDSCAPE-003",
                    source=source,
                    pointer="/landscape/rollup_resolutions",
                    message="Landskapets tillåtna visningsrollups matchar inte workspace-kartan.",
                    help_text="Använd exakt map_h3.rollup_resolutions; programmet väljer ingen regionberoende rollupfamilj.",
                    expected=map_h3["rollup_resolutions"],
                    actual=landscape["rollup_resolutions"],
                )
            )
        landscape_trust = landscape["trust"]["classification"]
        package_trust = access["trust_classification"]
        if ACCESS_TRUST_CLASSIFICATIONS.index(
            landscape_trust
        ) > ACCESS_TRUST_CLASSIFICATIONS.index(package_trust):
            problems.append(
                _problem(
                    code="MF-LANDSCAPE-004",
                    source=source,
                    pointer="/landscape/trust/classification",
                    message="Landskapets tillitsklassificering överstiger regionpaketets tillit.",
                    help_text="Behåll landskapet på samma eller lägre tillitsnivå; ett displaylager får inte uppgradera regionens evidens.",
                    expected=f"at most {package_trust}",
                    actual=landscape_trust,
                )
            )
        expected_acceptance = (
            landscape["trust"]["classification"] == "regionally_accepted"
        )
        if landscape["trust"]["regional_acceptance"] is not expected_acceptance:
            problems.append(
                _problem(
                    code="MF-LANDSCAPE-005",
                    source=source,
                    pointer="/landscape/trust/regional_acceptance",
                    message="Landskapets regional_acceptance motsäger dess tillitsklassificering.",
                    help_text="Sätt true endast för classification=regionally_accepted; display-only är inte acceptansevidens.",
                    expected=expected_acceptance,
                    actual=landscape["trust"]["regional_acceptance"],
                )
            )
        source_reference = landscape["source_reference"]
        if source_reference["kind"] == "technology_context":
            context = (
                technology_support.get("technology_context")
                if technology_support["state"] == "declared"
                else None
            )
            if (
                not isinstance(context, Mapping)
                or context.get("state") != "declared"
                or source_reference["context_id"] != context.get("id")
            ):
                problems.append(
                    _problem(
                        code="MF-LANDSCAPE-006",
                        source=source,
                        pointer="/landscape/source_reference/context_id",
                        message="Landskapets technology_context-referens är inte exakt deklarerad i regionpaketet.",
                        help_text="Deklarera teknikkontexten och använd exakt dess id, eller välj independent_asset med en egen checksummebunden källa.",
                        expected=(
                            context.get("id")
                            if isinstance(context, Mapping)
                            and context.get("state") == "declared"
                            else "declared technology context"
                        ),
                        actual=source_reference["context_id"],
                    )
                )
            elif landscape["resolution"] != context["resolution"]:
                problems.append(
                    _problem(
                        code="MF-LANDSCAPE-007",
                        source=source,
                        pointer="/landscape/resolution",
                        message="Landskapets återanvända kontextkälla har en annan H3-upplösning.",
                        help_text="Bind displaykontraktet till källans exakta upplösning eller använd en egen deklarerad källa.",
                        expected=context["resolution"],
                        actual=landscape["resolution"],
                    )
                )
        view_ids = [str(item["view_id"]) for item in landscape["views"]]
        value_fields = [str(item["value_field"]) for item in landscape["views"]]
        duplicate_view_ids = sorted(
            {item for item in view_ids if view_ids.count(item) > 1}
        )
        if duplicate_view_ids:
            problems.append(
                _problem(
                    code="MF-LANDSCAPE-008",
                    source=source,
                    pointer="/landscape/views",
                    message="Landskapets view_id:n är inte unika.",
                    help_text="Ge varje synlig semantisk vy ett stabilt unikt id.",
                    expected="unique view ids",
                    actual=duplicate_view_ids,
                )
            )
        if landscape["default_view_id"] not in set(view_ids):
            problems.append(
                _problem(
                    code="MF-LANDSCAPE-011",
                    source=source,
                    pointer="/landscape/default_view_id",
                    message="Landskapets uttryckliga produktstartvy är inte deklarerad.",
                    help_text="Använd exakt ett view_id från landscape.views; programmet får inte välja första vy implicit.",
                    expected=view_ids,
                    actual=landscape["default_view_id"],
                )
            )
        for view_index, view in enumerate(landscape["views"]):
            legend_ids = [str(item["value_id"]) for item in view["legend"]]
            duplicates = sorted(
                {item for item in legend_ids if legend_ids.count(item) > 1}
            )
            if duplicates:
                problems.append(
                    _problem(
                        code="MF-LANDSCAPE-009",
                        source=source,
                        pointer=f"/landscape/views/{view_index}/legend",
                        message="En landskapsvy har dubbla legendvärden.",
                        help_text="Deklarera varje value_id exakt en gång per vy.",
                        expected="unique legend value ids",
                        actual=duplicates,
                    )
                )
        if len(set(value_fields)) != len(value_fields):
            problems.append(
                _problem(
                    code="MF-LANDSCAPE-010",
                    source=source,
                    pointer="/landscape/views",
                    message="Flera landskapsvyer använder samma semantiska värdefält.",
                    help_text="Deklarera ett eget value_field per view_id i schema 1.0.",
                    expected="one semantic field per view",
                    actual=value_fields,
                )
            )
    rollups = map_h3["rollup_resolutions"]
    if rollups != sorted(rollups, reverse=True) or any(
        resolution >= map_h3["analysis_resolution"] for resolution in rollups
    ):
        problems.append(
            _problem(
                code="MF-H3-003",
                source=source,
                pointer="/map_h3/rollup_resolutions",
                message="H3-rollups måste vara unika, grövre än analysnivån och ordnade finast till grövast.",
                help_text="Exempel för R9: [8, 7, 6].",
                expected=f"descending values below R{map_h3['analysis_resolution']}",
                actual=rollups,
            )
        )

    layer_ids: set[str] = set()
    for group_index, group in enumerate(groups):
        if group["state"] != "declared":
            continue
        for layer_index, layer in enumerate(group["layers"]):
            layer_pointer = f"/standard_groups/{group_index}/layers/{layer_index}"
            layer_id = str(layer["id"])
            if layer_id in layer_ids:
                problems.append(
                    _problem(
                        code="MF-LAYER-001",
                        source=source,
                        pointer=f"{layer_pointer}/id",
                        message=f"Lager-id {layer_id!r} används mer än en gång.",
                        help_text="Ge varje regional källa ett unikt, stabilt lager-id.",
                        expected="unique layer id",
                        actual=layer_id,
                    )
                )
            layer_ids.add(layer_id)
            source_contract = layer["source"]
            if source_contract["geometry_family"] != layer["geometry_family"]:
                problems.append(
                    _problem(
                        code="MF-LAYER-002",
                        source=source,
                        pointer=f"{layer_pointer}/source/geometry_family",
                        message="Källans geometrifamilj matchar inte lagrets deklaration.",
                        help_text="Korrigera källmappningen eller lagrets geometry_family; programmet får inte gissa.",
                        expected=layer["geometry_family"],
                        actual=source_contract["geometry_family"],
                    )
                )
            if source_contract["data_representation"] != layer["data_representation"]:
                problems.append(
                    _problem(
                        code="MF-LAYER-003",
                        source=source,
                        pointer=f"{layer_pointer}/source/data_representation",
                        message="Källans datarepresentation matchar inte lagrets deklaration.",
                        help_text="Ange samma representation på lagret och källan.",
                        expected=layer["data_representation"],
                        actual=source_contract["data_representation"],
                    )
                )
            parameter = layer["parameters"]["buffer_m"]
            minimum = float(parameter["minimum"])
            maximum = float(parameter["maximum"])
            step = float(parameter["step"])
            if minimum > maximum:
                problems.append(
                    _problem(
                        code="MF-PARAM-001",
                        source=source,
                        pointer=f"{layer_pointer}/parameters/buffer_m",
                        message="Parameterintervallet är omvänt: minimum är större än maximum.",
                        help_text="Sätt minimum <= maximum.",
                        expected="minimum <= maximum",
                        actual={"minimum": minimum, "maximum": maximum},
                    )
                )
            technical_initial = float(parameter["technical_initial_value"])
            if not minimum <= technical_initial <= maximum:
                problems.append(
                    _problem(
                        code="MF-PARAM-002",
                        source=source,
                        pointer=f"{layer_pointer}/parameters/buffer_m/technical_initial_value",
                        message="Det tekniska startvärdet ligger utanför parameterintervallet.",
                        help_text="Välj ett körbart startvärde mellan minimum och maximum. Värdet är inte en regional rekommendation.",
                        expected=f"{minimum} <= value <= {maximum}",
                        actual=technical_initial,
                    )
                )
            technical_step_count = (technical_initial - minimum) / step
            if not math.isclose(
                technical_step_count,
                round(technical_step_count),
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                problems.append(
                    _problem(
                        code="MF-PARAM-003",
                        source=source,
                        pointer=f"{layer_pointer}/parameters/buffer_m/technical_initial_value",
                        message="Det tekniska startvärdet följer inte parameterns steg från minimum.",
                        help_text=f"Välj minimum + n × {step:g}. Värdet är endast kontrollens tekniska startläge.",
                        expected=f"step aligned from {minimum}",
                        actual=technical_initial,
                    )
                )

            recommendation = parameter["accepted_recommended_default"]
            if recommendation["state"] == "defined":
                recommended_value = float(recommendation["value"])
                if not minimum <= recommended_value <= maximum:
                    problems.append(
                        _problem(
                            code="MF-PARAM-004",
                            source=source,
                            pointer=f"{layer_pointer}/parameters/buffer_m/accepted_recommended_default/value",
                            message="Den accepterade regionala rekommendationen ligger utanför parameterintervallet.",
                            help_text="Välj ett accepterat rekommenderat värde mellan minimum och maximum eller markera rekommendationen unavailable.",
                            expected=f"{minimum} <= value <= {maximum}",
                            actual=recommended_value,
                        )
                    )
                step_count = (recommended_value - minimum) / step
                if not math.isclose(
                    step_count,
                    round(step_count),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                ):
                    problems.append(
                        _problem(
                            code="MF-PARAM-005",
                            source=source,
                            pointer=f"{layer_pointer}/parameters/buffer_m/accepted_recommended_default/value",
                            message="Den accepterade regionala rekommendationen följer inte parameterns steg från minimum.",
                            help_text=f"Välj minimum + n × {step:g}.",
                            expected=f"step aligned from {minimum}",
                            actual=recommended_value,
                        )
                    )

    for technology_id in TECHNOLOGY_IDS:
        technology = technologies[technology_id]
        if technology["state"] != "declared":
            continue
        for group_index, group_id in enumerate(technology["applicable_group_ids"]):
            if group_id not in declared_groups:
                problems.append(
                    _problem(
                        code="MF-TECH-001",
                        source=source,
                        pointer=f"/technologies/{technology_id}/applicable_group_ids/{group_index}",
                        message=f"Tekniken refererar till unavailable-gruppen {group_id!r}.",
                        help_text="Deklarera gruppens lager eller ta bort gruppen från teknikens applicable_group_ids.",
                        expected=sorted(declared_groups),
                        actual=group_id,
                    )
                )

    if solar_rooftop["state"] == "declared":
        solar = technologies["solar"]
        if solar["state"] != "declared":
            problems.append(
                _problem(
                    code="MF-ROOFTOP-001",
                    source=source,
                    pointer="/solar_rooftop/state",
                    message="Taksol kan inte deklareras utan ett deklarerat solkontrakt.",
                    help_text="Deklarera technologies.solar först eller behåll solar_rooftop unavailable.",
                    expected="declared technologies.solar",
                    actual=solar["state"],
                )
            )
        elif solar["area_result"]["state"] != "declared":
            problems.append(
                _problem(
                    code="MF-ROOFTOP-013",
                    source=source,
                    pointer="/technologies/solar/area_result/state",
                    message="Taksolsredovisningen kräver solens deklarerade markarearesultat.",
                    help_text="Deklarera solar.area_result komplett eller behåll solar_rooftop unavailable; taksol minskar endast det kvarvarande markbehovet.",
                    expected="declared solar area_result",
                    actual=solar["area_result"]["state"],
                )
            )
        elif "population" not in solar["applicable_group_ids"]:
            problems.append(
                _problem(
                    code="MF-ROOFTOP-014",
                    source=source,
                    pointer="/technologies/solar/applicable_group_ids",
                    message="Taksolens kartgranskning kräver population som tillämplig solgrupp.",
                    help_text="Lägg till population endast när dess regionala lager är deklarerade, eller behåll taksol unavailable.",
                    expected="population in solar applicable_group_ids",
                    actual=solar["applicable_group_ids"],
                )
            )
        rooftop_domain = solar_rooftop["domain_reference"]
        if (
            domain["state"] != "declared"
            or rooftop_domain["domain_id"] != domain.get("domain_id")
        ):
            problems.append(
                _problem(
                    code="MF-ROOFTOP-002",
                    source=source,
                    pointer="/solar_rooftop/domain_reference/domain_id",
                    message="Taksolens befolkningsredovisning refererar inte till regionens standardanalysdomän.",
                    help_text="Deklarera standard_analysis_domain och använd exakt dess domain_id; låna aldrig en annan regions domän.",
                    expected=(
                        domain.get("domain_id")
                        if domain["state"] == "declared"
                        else "declared standard analysis domain"
                    ),
                    actual=rooftop_domain["domain_id"],
                )
            )
        population_source = solar_rooftop["population_source"]
        analysis_resolution = int(
            population_source["analysis_h3_resolution"]
        )
        source_resolution = int(population_source["source_h3_resolution"])
        if analysis_resolution != map_h3["analysis_resolution"]:
            problems.append(
                _problem(
                    code="MF-ROOFTOP-003",
                    source=source,
                    pointer="/solar_rooftop/population_source/analysis_h3_resolution",
                    message="Taksolens analysupplösning matchar inte standardanalysdomänen.",
                    help_text="Använd exakt map_h3.analysis_resolution; compilern verifierar källans celler mot den domänen.",
                    expected=map_h3["analysis_resolution"],
                    actual=analysis_resolution,
                )
            )
        if source_resolution < analysis_resolution:
            problems.append(
                _problem(
                    code="MF-ROOFTOP-004",
                    source=source,
                    pointer="/solar_rooftop/population_source/source_h3_resolution",
                    message="Taksolens befolkningskälla är grövre än den deklarerade analysdomänen.",
                    help_text="Använd en källa på samma eller finare H3-nivå; programmet får inte fördela grövre värden med en dold regional modell.",
                    expected=f">= R{analysis_resolution}",
                    actual=source_resolution,
                )
            )

        population_group = next(
            (group for group in groups if group["id"] == "population"),
            None,
        )
        population_layer_ids = {
            str(layer["id"])
            for layer in (
                population_group.get("layers", [])
                if isinstance(population_group, Mapping)
                and population_group.get("state") == "declared"
                else []
            )
        }
        requested_review_layers = tuple(
            str(layer_id)
            for layer_id in solar_rooftop["map_review"]["layer_ids"]
        )
        if (
            not population_layer_ids
            or not set(requested_review_layers).issubset(population_layer_ids)
        ):
            problems.append(
                _problem(
                    code="MF-ROOFTOP-005",
                    source=source,
                    pointer="/solar_rooftop/map_review/layer_ids",
                    message="Taksolens kartgranskning refererar inte enbart till deklarerade befolkningslager.",
                    help_text="Deklarera population-gruppen och välj exakta lager-id:n därifrån; filnärvaro öppnar aldrig ett kartlager implicit.",
                    expected=sorted(population_layer_ids),
                    actual=list(requested_review_layers),
                )
            )

        parameter = solar_rooftop["panel_area_m2_per_person"]
        minimum = float(parameter["minimum"])
        maximum = float(parameter["maximum"])
        step = float(parameter["step"])
        technical_initial = float(parameter["technical_initial_value"])
        if minimum > maximum:
            problems.append(
                _problem(
                    code="MF-ROOFTOP-006",
                    source=source,
                    pointer="/solar_rooftop/panel_area_m2_per_person",
                    message="Taksolens panelyteintervall är omvänt.",
                    help_text="Sätt minimum <= maximum; värdena anges i m2/person.",
                    expected="minimum <= maximum",
                    actual={"minimum": minimum, "maximum": maximum},
                )
            )
        if not minimum <= technical_initial <= maximum:
            problems.append(
                _problem(
                    code="MF-ROOFTOP-007",
                    source=source,
                    pointer="/solar_rooftop/panel_area_m2_per_person/technical_initial_value",
                    message="Taksolens tekniska startvärde ligger utanför parameterintervallet.",
                    help_text="Välj ett körbart värde inom intervallet; regional rekommendation deklareras separat.",
                    expected=f"{minimum} <= value <= {maximum}",
                    actual=technical_initial,
                )
            )
        elif not math.isclose(
            (technical_initial - minimum) / step,
            round((technical_initial - minimum) / step),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            problems.append(
                _problem(
                    code="MF-ROOFTOP-008",
                    source=source,
                    pointer="/solar_rooftop/panel_area_m2_per_person/technical_initial_value",
                    message="Taksolens tekniska startvärde följer inte parameterns steg från minimum.",
                    help_text=f"Välj minimum + n × {step:g}; värdet är inte en regional rekommendation.",
                    expected=f"step aligned from {minimum}",
                    actual=technical_initial,
                )
            )
        recommendation = parameter["accepted_recommended_default"]
        if recommendation["state"] == "defined":
            recommended = float(recommendation["value"])
            if not minimum <= recommended <= maximum:
                problems.append(
                    _problem(
                        code="MF-ROOFTOP-009",
                        source=source,
                        pointer="/solar_rooftop/panel_area_m2_per_person/accepted_recommended_default/value",
                        message="Taksolens accepterade regionala rekommendation ligger utanför intervallet.",
                        help_text="Välj ett granskat värde inom intervallet eller markera rekommendationen unavailable.",
                        expected=f"{minimum} <= value <= {maximum}",
                        actual=recommended,
                    )
                )
            elif not math.isclose(
                (recommended - minimum) / step,
                round((recommended - minimum) / step),
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                problems.append(
                    _problem(
                        code="MF-ROOFTOP-010",
                        source=source,
                        pointer="/solar_rooftop/panel_area_m2_per_person/accepted_recommended_default/value",
                        message="Taksolens accepterade rekommendation följer inte parameterns steg.",
                        help_text=f"Välj minimum + n × {step:g}.",
                        expected=f"step aligned from {minimum}",
                        actual=recommended,
                    )
                )

        rooftop_trust = solar_rooftop["trust"]
        capability_trust = str(rooftop_trust["classification"])
        package_trust = str(access["trust_classification"])
        if ACCESS_TRUST_CLASSIFICATIONS.index(
            capability_trust
        ) > ACCESS_TRUST_CLASSIFICATIONS.index(package_trust):
            problems.append(
                _problem(
                    code="MF-ROOFTOP-011",
                    source=source,
                    pointer="/solar_rooftop/trust/classification",
                    message="Taksolens tillit överstiger regionpaketets tillitsnivå.",
                    help_text="Behåll capabilityn på samma eller lägre tillitsnivå; ett delkontrakt får inte uppgradera regionens evidens.",
                    expected=f"at most {package_trust}",
                    actual=capability_trust,
                )
            )
        accepted = capability_trust == "regionally_accepted"
        expected_use = (
            "regional_planning" if accepted else "planning_exploration_only"
        )
        if (
            rooftop_trust["regional_acceptance"] is not accepted
            or rooftop_trust["allowed_use"] != expected_use
        ):
            problems.append(
                _problem(
                    code="MF-ROOFTOP-012",
                    source=source,
                    pointer="/solar_rooftop/trust",
                    message="Taksolens tillitsklassificering, regional_acceptance och allowed_use är inkonsekventa.",
                    help_text="Endast regionally_accepted får använda true/regional_planning; övriga nivåer använder false/planning_exploration_only.",
                    expected={
                        "regional_acceptance": accepted,
                        "allowed_use": expected_use,
                    },
                    actual=rooftop_trust,
                )
            )

    for asset_path, asset in _walk_assets(value):
        if not _safe_provider_path(asset["path"]):
            problems.append(
                _problem(
                    code="MF-PATH-001",
                    source=source,
                    pointer=_json_pointer((*asset_path, "path")),
                    message="Källsökvägen är inte en säker provider-relativ POSIX-sökväg.",
                    help_text="Ta bort enhetsbokstav, inledande snedstreck, bakstreck och alla ..-segment.",
                    expected="safe provider-relative POSIX path",
                    actual=asset["path"],
                )
            )

    scenario = value["scenario"]
    if scenario["state"] == "declared":
        accepted = scenario["status"] == "accepted_regional"
        if accepted != scenario["regional_acceptance"] or scenario["allowed_use"] != (
            "regional_planning" if accepted else "planning_exploration_only"
        ):
            problems.append(
                _problem(
                    code="MF-SCENARIO-001",
                    source=source,
                    pointer="/scenario/status",
                    message="Scenariots status, regional_acceptance och allowed_use är inkonsekventa.",
                    help_text="accepted_regional kräver true/regional_planning; provisional_fallback kräver false/planning_exploration_only.",
                    expected="consistent scenario trust contract",
                    actual={
                        "status": scenario["status"],
                        "regional_acceptance": scenario["regional_acceptance"],
                        "allowed_use": scenario["allowed_use"],
                    },
                )
            )
        scenario_ids = [item["id"] for item in scenario["planning_scenarios"]]
        if scenario["scenario_levels"] != scenario_ids or scenario["default_scenario"] not in scenario_ids or len(set(scenario_ids)) != len(scenario_ids):
            problems.append(
                _problem(
                    code="MF-SCENARIO-002",
                    source=source,
                    pointer="/scenario/scenario_levels",
                    message="Scenarioordning, planerings-id:n och default stämmer inte överens.",
                    help_text="Använd unika id:n i samma ordning och välj en deklarerad default_scenario.",
                    expected=scenario_ids,
                    actual=scenario["scenario_levels"],
                )
            )
        adapter = scenario["adapter"]
        adapter_id = adapter["id"]
        expected_formats = (
            ("json", "json")
            if adapter_id == "normalized_json_v1"
            else ("duckdb", "xlsx")
        )
        actual_formats = (
            scenario["assets"]["energy_model"]["format"],
            scenario["assets"]["area_demand"]["format"],
        )
        if actual_formats != expected_formats:
            problems.append(
                _problem(
                    code="MF-SCENARIO-003",
                    source=source,
                    pointer="/scenario/adapter/id",
                    message="Scenarioadaptern och de två källformaten stämmer inte överens.",
                    help_text="normalized_json_v1 kräver JSON+JSON; times_duckdb_area_demand_xlsx_v1 kräver DuckDB+XLSX.",
                    expected=expected_formats,
                    actual=actual_formats,
                )
            )
        declared_technology_ids = [
            technology_id
            for technology_id, technology in value["technologies"].items()
            if technology["state"] == "declared"
        ]
        if adapter["technology_ids"] != declared_technology_ids:
            problems.append(
                _problem(
                    code="MF-SCENARIO-004",
                    source=source,
                    pointer="/scenario/adapter/technology_ids",
                    message="Scenariots teknikordning avviker från regionens deklarerade tekniker.",
                    help_text="Ange exakt de deklarerade teknikerna i workspace-profilens ordning; lägg inte till en regional specialteknik.",
                    expected=declared_technology_ids,
                    actual=adapter["technology_ids"],
                )
            )
        asset_providers = {
            scenario["assets"][role]["provider"]
            for role in ("energy_model", "area_demand")
        }
        if asset_providers != {scenario["provider"]}:
            problems.append(
                _problem(
                    code="MF-SCENARIO-005",
                    source=source,
                    pointer="/scenario/provider",
                    message="Scenariots provider och de två källartefakternas provider skiljer sig.",
                    help_text="Lägg energimodell och areabehov under samma uttryckligen deklarerade providerrot.",
                    expected=scenario["provider"],
                    actual=sorted(asset_providers),
                )
            )
        configuration = adapter.get("configuration")
        if isinstance(configuration, Mapping):
            configured_paths = [
                key
                for section_name in ("duckdb", "area_demand")
                for key in configuration[section_name].keys()
                if key == "path"
            ]
            if configured_paths:
                problems.append(
                    _problem(
                        code="MF-SCENARIO-006",
                        source=source,
                        pointer="/scenario/adapter/configuration",
                        message="Scenarioadaptern får inte deklarera en andra källsökväg i sin avancerade konfiguration.",
                        help_text="Ange sökvägar endast under scenario.assets; compilern binder dem till adapterkontraktet.",
                        expected="no path keys",
                        actual=configured_paths,
                    )
                )
        area_option_ids = [
            item["id"] for item in scenario["area_demand_options"]
        ]
        planning_area_ids = {
            item["area_demand_scenario"]
            for item in scenario["planning_scenarios"]
        }
        if (
            len(area_option_ids) != len(set(area_option_ids))
            or scenario["default_area_demand_scenario"]
            not in area_option_ids
            or not planning_area_ids.issubset(set(area_option_ids))
        ):
            problems.append(
                _problem(
                    code="MF-SCENARIO-007",
                    source=source,
                    pointer="/scenario/area_demand_options",
                    message="Areabehovsalternativen, deras default eller planeringsscenariernas referenser är inkonsekventa.",
                    help_text="Använd unika alternativ-id:n, välj ett deklarerat default och låt varje planning_scenario referera till ett deklarerat areabehovsalternativ.",
                    expected={
                        "unique_ids": area_option_ids,
                        "declared_default": True,
                        "planning_refs_declared": True,
                    },
                    actual={
                        "default": scenario[
                            "default_area_demand_scenario"
                        ],
                        "planning_refs": sorted(planning_area_ids),
                    },
                )
            )
        technology_mix = scenario["technology_mix"]
        default_shares = technology_mix["default_shares"]
        share_ids = [item["technology_id"] for item in default_shares]
        share_values = [float(item["share_pct"]) for item in default_shares]
        share_step = float(technology_mix["share_step_pct"])
        if (
            share_ids != adapter["technology_ids"]
            or not math.isclose(
                math.fsum(share_values),
                100.0,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            or any(
                not math.isclose(
                    value / share_step,
                    round(value / share_step),
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                for value in share_values
            )
        ):
            problems.append(
                _problem(
                    code="MF-SCENARIO-008",
                    source=source,
                    pointer="/scenario/technology_mix",
                    message="Scenariots standardandelar följer inte teknikordningen, steget eller summan 100 procent.",
                    help_text="Ange varje deklarerad teknik exakt en gång i adapterordning, använd stegjusterade värden mellan 0 och 100 och låt summan bli exakt 100.",
                    expected={
                        "technology_ids": adapter["technology_ids"],
                        "sum_pct": 100.0,
                        "step_pct": share_step,
                    },
                    actual={
                        "technology_ids": share_ids,
                        "sum_pct": math.fsum(share_values),
                    },
                )
            )

    social = value["social_acceptance"]
    if social["state"] == "declared":
        accepted = social["status"] == "accepted_regional"
        if (
            accepted != social["regional_acceptance"]
            or social["allowed_use"]
            != ("regional_planning" if accepted else "behavior_exploration_only")
            or (accepted and social["synthetic"])
        ):
            problems.append(
                _problem(
                    code="MF-SOCIAL-001",
                    source=source,
                    pointer="/social_acceptance/status",
                    message="Social-acceptansstatusen motsäger acceptance, allowed_use eller synthetic.",
                    help_text="Accepted regional data måste vara icke-syntetiskt och använda regional_planning; fallback får inte påstå regional acceptans.",
                    expected="consistent social-acceptance trust contract",
                    actual={
                        "status": social["status"],
                        "regional_acceptance": social["regional_acceptance"],
                        "allowed_use": social["allowed_use"],
                        "synthetic": social["synthetic"],
                    },
                )
            )
        coverage = social["coverage"]
        if coverage["source_hex_count"] + coverage["unassessed_support_hex_count"] != coverage["target_support_hex_count"]:
            problems.append(
                _problem(
                    code="MF-SOCIAL-002",
                    source=source,
                    pointer="/social_acceptance/coverage",
                    message="Täckningsantalen summerar inte till teknikdomänen.",
                    help_text="source_hex_count + unassessed_support_hex_count måste vara target_support_hex_count.",
                    expected=coverage["target_support_hex_count"],
                    actual=coverage["source_hex_count"] + coverage["unassessed_support_hex_count"],
                )
            )
        behavior = social["behavior"]
        if behavior["allocation_priority_model"] != "linear_acceptance_blend":
            problems.append(
                _problem(
                    code="MF-SOCIAL-010",
                    source=source,
                    pointer="/social_acceptance/behavior/allocation_priority_model",
                    message="Allokeringsprioriteringen använder inte programmets registrerade generella modell.",
                    help_text="Använd linear_acceptance_blend; region-id får aldrig välja en annan algoritm.",
                    expected="linear_acceptance_blend",
                    actual=behavior["allocation_priority_model"],
                )
            )
        if not behavior["low_threshold"] < behavior["high_threshold"]:
            problems.append(
                _problem(
                    code="MF-SOCIAL-003",
                    source=source,
                    pointer="/social_acceptance/behavior",
                    message="Acceptanströsklarna måste uppfylla low_threshold < high_threshold.",
                    help_text="Välj två värden i [0, 1] där low är strikt lägre än high.",
                    expected="low < high",
                    actual={
                        "low": behavior["low_threshold"],
                        "high": behavior["high_threshold"],
                    },
                )
            )
        social_ids = [item["id"] for item in social["scenarios"]]
        value_columns = [item["value_column"] for item in social["scenarios"]]
        if (
            social["scenario_levels"] != social_ids
            or social["default_scenario"] not in social_ids
            or len(set(social_ids)) != len(social_ids)
            or len(set(value_columns)) != len(value_columns)
        ):
            problems.append(
                _problem(
                    code="MF-SOCIAL-004",
                    source=source,
                    pointer="/social_acceptance/scenario_levels",
                    message="Acceptansscenariernas ordning, id:n, värdekolumner eller default är inkonsekventa.",
                    help_text="Använd unika id:n och värdekolumner i samma ordning som scenario_levels och välj en deklarerad default.",
                    expected=social_ids,
                    actual=social["scenario_levels"],
                )
            )
        if accepted and social["source_region_id"] != value["region"]["region_id"]:
            problems.append(
                _problem(
                    code="MF-SOCIAL-005",
                    source=source,
                    pointer="/social_acceptance/source_region_id",
                    message="Regionalt accepterad social acceptans tillhör inte regionpaketets region.",
                    help_text="Använd paketets eget region-id för accepted_regional; en annan regions underlag får endast deklareras som synlig provisional fallback.",
                    expected=value["region"]["region_id"],
                    actual=social["source_region_id"],
                )
            )
        if social["synthetic"] != (social.get("random_seed") is not None):
            problems.append(
                _problem(
                    code="MF-SOCIAL-006",
                    source=source,
                    pointer="/social_acceptance/random_seed",
                    message="Synthetic och random_seed är inkonsekventa.",
                    help_text="Ange ett reproducerbart seed endast för syntetiska värden; observerade data får inte deklarera seed.",
                    expected="integer when synthetic=true, otherwise omitted",
                    actual=social.get("random_seed"),
                )
            )
        rollups = social["rollup_resolutions"]
        if (
            rollups != sorted(rollups, reverse=True)
            or any(item >= social["hex_resolution"] for item in rollups)
            or any(
                item not in value["map_h3"]["rollup_resolutions"]
                for item in rollups
            )
        ):
            problems.append(
                _problem(
                    code="MF-SOCIAL-007",
                    source=source,
                    pointer="/social_acceptance/rollup_resolutions",
                    message="Acceptanslagrets rollups är inte deklarerade för regionens karta.",
                    help_text="Ange unika fallande parent-resolutioner under källans H3-resolution och endast värden som finns i map_h3.rollup_resolutions.",
                    expected=value["map_h3"]["rollup_resolutions"],
                    actual=rollups,
                )
            )
        asset_formats = {
            role: social["assets"][role]["format"]
            for role in ("acceptance_values", "display_geometry")
        }
        asset_providers = {
            social["assets"][role]["provider"]
            for role in ("acceptance_values", "display_geometry")
        }
        if asset_formats != {
            "acceptance_values": "csv",
            "display_geometry": "geojson",
        } or asset_providers != {social["provider"]}:
            problems.append(
                _problem(
                    code="MF-SOCIAL-008",
                    source=source,
                    pointer="/social_acceptance/assets",
                    message="Acceptansartefakternas format eller provider matchar inte den generella adaptern.",
                    help_text="Använd CSV för värden, GeoJSON för visningsgeometri och samma deklarerade provider för båda.",
                    expected={"provider": social["provider"], "formats": {"acceptance_values": "csv", "display_geometry": "geojson"}},
                    actual={"providers": sorted(asset_providers), "formats": asset_formats},
                )
            )
        for parameter_id, parameter in social["control_contract"].items():
            initial = parameter["technical_initial_value"]
            step_count = (initial - parameter["minimum"]) / parameter["step"]
            recommendation = parameter["accepted_recommended_default"]
            recommendation_value = recommendation.get("value")
            if (
                not parameter["minimum"] <= initial <= parameter["maximum"]
                or not math.isclose(step_count, round(step_count), rel_tol=0.0, abs_tol=1e-9)
                or (
                    recommendation["state"] == "defined"
                    and (
                        recommendation_value is None
                        or not parameter["minimum"] <= recommendation_value <= parameter["maximum"]
                    )
                )
            ):
                problems.append(
                    _problem(
                        code="MF-SOCIAL-009",
                        source=source,
                        pointer=f"/social_acceptance/control_contract/{parameter_id}",
                        message="Acceptanskontrollens start- eller rekommendationsvärde bryter mot intervallet.",
                        help_text="Välj ett tekniskt startvärde i 0–100 som följer step; regional rekommendation ska deklareras separat.",
                        expected={"minimum": parameter["minimum"], "maximum": parameter["maximum"], "step": parameter["step"]},
                        actual={"technical_initial_value": initial, "accepted_recommended_default": recommendation},
                    )
                )

    if combined_result["state"] == "declared":
        technical_validation = combined_result.get("technical_validation")
        if isinstance(technical_validation, Mapping) and (
            technical_validation.get("provider") != "repo"
            or technical_validation.get("format") != "json"
        ):
            problems.append(
                _problem(
                    code="MF-COMBINED-007",
                    source=source,
                    pointer="/combined_result/technical_validation",
                    message="Kombinerat resultats separata valideringsevidens måste vara repoägd JSON.",
                    help_text="Deklarera en checksumspinnad repo/JSON-artefakt; kompilatorn skapar eller uppgraderar aldrig teknisk evidens.",
                    expected={"provider": "repo", "format": "json"},
                    actual={
                        "provider": technical_validation.get("provider"),
                        "format": technical_validation.get("format"),
                    },
                )
            )
        try:
            combined_contract = combined_result_policy_contract_from_form(
                combined_result
            )
        except (KeyError, NotImplementedError, TypeError, ValueError) as exc:
            problems.append(
                _problem(
                    code="MF-COMBINED-001",
                    source=source,
                    pointer="/combined_result",
                    message="Det kombinerade resultatets policykontrakt är inte komplett eller körbart.",
                    help_text="Deklarera varje policyval, teknikfas och prioriteringskomponent explicit; skriv inga cellpoäng eller signaturer i blanketten.",
                    expected="a strict combined-result policy contract",
                    actual=str(exc),
                )
            )
        else:
            declared_area_technology_ids = tuple(
                technology_id
                for technology_id in TECHNOLOGY_IDS
                if technologies[technology_id]["state"] == "declared"
                and technologies[technology_id]["area_result"]["state"]
                == "declared"
            )
            if set(combined_contract.technology_order) != set(
                declared_area_technology_ids
            ):
                problems.append(
                    _problem(
                        code="MF-COMBINED-002",
                        source=source,
                        pointer="/combined_result/technology_order",
                        message="Det kombinerade resultatets teknikordning täcker inte exakt teknikerna med deklarerat area-resultat.",
                        help_text="Lista varje teknik med ett komplett area_result exakt en gång; ordningen är ett mänskligt policyval.",
                        expected=declared_area_technology_ids,
                        actual=combined_contract.technology_order,
                    )
                )
            if (
                combined_contract.finalization_resolution
                != map_h3["analysis_resolution"]
            ):
                problems.append(
                    _problem(
                        code="MF-COMBINED-003",
                        source=source,
                        pointer="/combined_result/finalization_resolution",
                        message="Kombinerat resultat finaliseras inte på regionens analysupplösning.",
                        help_text="Använd exakt map_h3.analysis_resolution; parentresultat ska summeras utan ny finalisering.",
                        expected=map_h3["analysis_resolution"],
                        actual=combined_contract.finalization_resolution,
                    )
                )
            if list(combined_contract.rollup_resolutions) != map_h3[
                "rollup_resolutions"
            ]:
                problems.append(
                    _problem(
                        code="MF-COMBINED-004",
                        source=source,
                        pointer="/combined_result/rollup_resolutions",
                        message="Kombinerat resultat använder inte kartans exakta rollupupplösningar.",
                        help_text="Använd map_h3.rollup_resolutions i samma fallande ordning; ranka aldrig om på parentnivå.",
                        expected=map_h3["rollup_resolutions"],
                        actual=list(combined_contract.rollup_resolutions),
                    )
                )
            scenario_section = value["scenario"]
            if scenario_section["state"] == "declared" and set(
                scenario_section["adapter"]["technology_ids"]
            ) != set(combined_contract.technology_order):
                problems.append(
                    _problem(
                        code="MF-COMBINED-006",
                        source=source,
                        pointer="/combined_result/technology_order",
                        message="Kombinerat resultat och scenario deklarerar olika teknikmängder.",
                        help_text="Använd samma exakta teknik-id:n; allokeringsordningen får vara policyvald men ingen teknik får tillkomma eller saknas.",
                        expected=scenario_section["adapter"]["technology_ids"],
                        actual=list(combined_contract.technology_order),
                    )
                )

    return problems


def validate_region_package(
    value: Mapping[str, Any],
    *,
    source: str = "<memory>",
    schema: Mapping[str, Any] | None = None,
    questions: Sequence[ManifestQuestion] | None = None,
) -> tuple[ManifestProblem, ...]:
    """Return every structural and semantic problem in deterministic order."""

    active_schema = schema or load_region_package_schema()
    active_questions = tuple(questions) if questions is not None else (
        load_region_package_questions(
            form_schema=active_schema,
            expected_form_schema_version=REGION_PACKAGE_FORM_VERSION,
        )
    )
    structural = _schema_problems(
        value,
        schema=active_schema,
        source=source,
    )
    if structural:
        return attach_manifest_problem_questions(
            structural,
            schema=active_schema,
            questions=active_questions,
        )
    semantic = _semantic_problems(value, source=source)
    return attach_manifest_problem_questions(
        sorted(
            semantic,
            key=lambda problem: (problem.pointer, problem.code, problem.message),
        ),
        schema=active_schema,
        questions=active_questions,
    )


def validate_region_package_file(
    path: Path,
    *,
    schema_path: Path | None = None,
) -> tuple[dict[str, Any] | None, tuple[ManifestProblem, ...]]:
    """Read one form and return its payload plus all actionable problems."""

    source_path = path.resolve()
    source = str(source_path)
    try:
        value = json.loads(source_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, (
            _problem(
                code="MF-JSON-001",
                source=source,
                pointer="/",
                message="Regionblanketten finns inte.",
                help_text="Kontrollera sökvägen eller kopiera regions/templates/region-package.form.json.",
                expected="existing JSON file",
                actual=None,
            ),
        )
    except json.JSONDecodeError as exc:
        return None, (
            _problem(
                code="MF-JSON-002",
                source=source,
                pointer="/",
                message=f"Regionblanketten innehåller ogiltig JSON vid rad {exc.lineno}, kolumn {exc.colno}.",
                help_text="Rätta kommatecken, citationstecken eller klamrar och kör validatorn igen.",
                validator="json",
                expected="valid JSON object",
                actual=exc.msg,
            ),
        )
    except OSError as exc:
        return None, (
            _problem(
                code="MF-JSON-003",
                source=source,
                pointer="/",
                message=f"Regionblanketten kan inte läsas: {exc}",
                help_text="Kontrollera filbehörighet och sökväg.",
                expected="readable JSON file",
                actual=str(exc),
            ),
        )
    if not isinstance(value, dict):
        return None, (
            _problem(
                code="MF-JSON-004",
                source=source,
                pointer="/",
                message="Regionblankettens rot måste vara ett JSON-objekt.",
                help_text="Börja från den repoägda mallen och behåll dess objektstruktur.",
                expected="object",
                actual=type(value).__name__,
            ),
        )
    schema = load_region_package_schema(schema_path)
    return value, validate_region_package(value, source=source, schema=schema)


__all__ = [
    "ManifestProblem",
    "REGION_PACKAGE_FORM_VERSION",
    "REGION_PACKAGE_SCHEMA_RELATIVE_PATH",
    "attach_manifest_problem_questions",
    "default_region_package_schema_path",
    "load_region_package_schema",
    "validate_region_package",
    "validate_region_package_file",
]
