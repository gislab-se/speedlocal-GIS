"""Small, presentation-only catalogs; language is never a calculation input.

New copy uses semantic message IDs. Existing Swedish copy remains an exact alias
while the large analysis view is migrated. Unknown provider names and data values
are returned unchanged; coverage checks identify unknown authored UI copy.
"""
from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
import re
from string import Formatter
from typing import Any

from .i18n_catalog import MESSAGES, SOURCE_TEXT_ALIASES

LANGUAGE_LABELS = {"sv": "Svenska", "nb": "Norsk", "da": "Dansk", "en": "English"}
_ALIASES = {**{values[0]: key for key, values in MESSAGES.items()}, **SOURCE_TEXT_ALIASES}
_EN_ALIASES = {values[3]: key for key, values in MESSAGES.items()}
_LANGUAGE_INDEX = {code: index for index, code in enumerate(LANGUAGE_LABELS)}


def normalize_language(language: str | None) -> str:
    """Keep old sessions readable; the former mixed locale was Danish copy."""
    code = str(language or "sv").strip().lower()
    code = {"no": "nb", "nb-no": "nb", "da_no": "da", "sv-se": "sv", "da-dk": "da", "en-gb": "en", "en-us": "en"}.get(code, code)
    return code if code in LANGUAGE_LABELS else "sv"


def translate(text: str, language: str = "sv", **kwargs: Any) -> str:
    """Resolve an ID or exact authored Swedish template, then format parameters.

    A missing locale consistently falls back to English. No substring or word
    replacement is performed, and supplied names/values are never translated.
    """
    source = str(text)
    message_id = source if source in MESSAGES else _ALIASES.get(source, _EN_ALIASES.get(source))
    if message_id is None:
        return source.format(**kwargs) if kwargs else source
    values = MESSAGES[message_id]
    translated = values[_LANGUAGE_INDEX[normalize_language(language)]] or values[3]
    return translated.format(**kwargs) if kwargs else translated


translate_text = translate


@lru_cache(maxsize=1)
def _rendered_templates() -> tuple[tuple[re.Pattern[str], str], ...]:
    """Compile only complete authored messages with meaningful literal anchors."""
    templates = []
    formatter = Formatter()
    for key, values in MESSAGES.items():
        for template in dict.fromkeys(values):
            if not template:
                continue
            parts = list(formatter.parse(template))
            literal = "".join(part[0] for part in parts)
            if not any(part[1] for part in parts) or len(re.sub(r"[^\w]", "", literal)) < 8:
                continue
            pattern = []
            seen = set()
            for prefix, field, _, _ in parts:
                pattern.append(re.escape(prefix))
                if field:
                    if field in seen:
                        pattern.append(f"(?P={field})")
                    else:
                        pattern.append(f"(?P<{field}>.*?)")
                        seen.add(field)
            templates.append((len(literal), re.compile("^" + "".join(pattern) + "$", re.DOTALL), key))
    templates.sort(key=lambda row: row[0], reverse=True)
    return tuple((pattern, key) for _, pattern, key in templates)


def translate_rendered(text: str, language: str = "sv") -> str:
    """Relabel cached authored prose without formatting or altering its values.

    Exact copy takes precedence. Templates match the entire authored message,
    never a word or substring. Captured numbers retain their displayed precision;
    names, units and technical data remain verbatim.
    """
    source = str(text)
    if source in MESSAGES or source in _ALIASES or source in _EN_ALIASES:
        return translate(source, language)
    for pattern, key in _rendered_templates():
        match = pattern.fullmatch(source)
        if match:
            captured = match.groupdict()
            template = translate(key, language)
            return "".join(prefix + (captured[field] if field else "")
                           for prefix, field, _, _ in Formatter().parse(template))
    return source


def presentation_catalog(language: str = "sv") -> dict[str, str]:
    """Exact authored text catalog for cached browser popup/legend presentation."""
    aliases = {**_EN_ALIASES, **_ALIASES}
    return {source: translate(message_id, language) for source, message_id in aliases.items()}


def message_id(text: str) -> str | None:
    return str(text) if str(text) in MESSAGES else _ALIASES.get(str(text), _EN_ALIASES.get(str(text)))


def missing_messages(texts: Iterable[str]) -> list[str]:
    """Used by focused checks; source names and units must be excluded by caller."""
    return sorted({str(text) for text in texts if message_id(str(text)) is None})


def _fields(template: str) -> set[tuple[str, str, str | None]]:
    fields = set()
    for _, field, format_spec, conversion in Formatter().parse(template):
        if field is not None:
            if not field.isidentifier():
                raise ValueError(f"Only named presentation parameters are allowed: {field!r}")
            fields.add((field, format_spec, conversion))
    return fields


def catalog_issues() -> list[str]:
    """Report absent translations, ambiguous aliases and parameter mismatches."""
    issues = []
    aliases: dict[str, str] = {}
    for key, values in MESSAGES.items():
        if len(values) != 4:
            issues.append(f"{key}: expected sv, nb, da, en")
            continue
        source = values[0]
        if source in aliases and MESSAGES[aliases[source]] != values:
            issues.append(f"{key}: ambiguous Swedish alias with {aliases[source]}")
        aliases[source] = key
        try:
            expected = _fields(source)
            for code, value in zip(LANGUAGE_LABELS, values):
                if not value:
                    issues.append(f"{key}: missing {code}")
                elif _fields(value) != expected:
                    issues.append(f"{key}: {code} parameter mismatch")
        except ValueError as exc:
            issues.append(f"{key}: {exc}")
    for source, key in SOURCE_TEXT_ALIASES.items():
        if key not in MESSAGES:
            issues.append(f"{key}: source alias has no catalog message")
        elif source in aliases and MESSAGES[aliases[source]] != MESSAGES[key]:
            issues.append(f"{key}: ambiguous explicit source alias with {aliases[source]}")
        elif _fields(source) != _fields(MESSAGES[key][0]):
            issues.append(f"{key}: source alias parameter mismatch")
    return issues
