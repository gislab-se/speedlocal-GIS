from __future__ import annotations

from dataclasses import dataclass
import re


_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SCOPE_IDENTIFIER_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$"
)
_ACCESS_KINDS = frozenset({"product", "review"})
_STATE_KEY_PREFIX = "workspace_ui:v1"


def _validated_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(
            f"{field_name} must be a normalized lowercase identifier"
        )
    return value


def _validated_scope_identifier(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("scope_id must be a string")
    if not _SCOPE_IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(
            "scope_id must be a normalized lowercase identifier or a "
            "dot-separated canonical capability id"
        )
    return value


@dataclass(frozen=True, slots=True)
class WorkspaceUiIdentity:
    """Immutable identity for one capability-isolated workspace UI scope."""

    region_id: str
    access_scope: str
    scope_id: str

    def __post_init__(self) -> None:
        region_id = _validated_identifier(self.region_id, "region_id")
        _validated_scope_identifier(self.scope_id)
        if not isinstance(self.access_scope, str):
            raise TypeError("access_scope must be a string")
        access_kind, separator, scope_region_id = self.access_scope.partition(":")
        if separator != ":" or access_kind not in _ACCESS_KINDS:
            raise ValueError(
                "access_scope must be product:<region_id> or review:<region_id>"
            )
        _validated_identifier(scope_region_id, "access_scope region_id")
        if scope_region_id != region_id:
            raise ValueError("access_scope must be bound to region_id")

    @property
    def access_kind(self) -> str:
        """Return the validated product/review part of ``access_scope``."""

        return self.access_scope.partition(":")[0]


def workspace_state_key(
    identity: WorkspaceUiIdentity,
    kind: str,
    *parts: str,
) -> str:
    """Build one stable Streamlit state key isolated by workspace identity."""

    if not isinstance(identity, WorkspaceUiIdentity):
        raise TypeError("identity must be a WorkspaceUiIdentity")
    key_parts = (
        _STATE_KEY_PREFIX,
        identity.region_id,
        identity.access_kind,
        identity.scope_id,
        _validated_identifier(kind, "kind"),
        *(
            _validated_identifier(part, f"parts[{index}]")
            for index, part in enumerate(parts)
        ),
    )
    return ":".join(key_parts)


def workspace_state_prefix(identity: WorkspaceUiIdentity) -> str:
    """Return the exclusive prefix for all state owned by one UI scope."""

    if not isinstance(identity, WorkspaceUiIdentity):
        raise TypeError("identity must be a WorkspaceUiIdentity")
    return ":".join(
        (
            _STATE_KEY_PREFIX,
            identity.region_id,
            identity.access_kind,
            identity.scope_id,
        )
    ) + ":"
