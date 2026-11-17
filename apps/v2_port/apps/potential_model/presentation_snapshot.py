"""Session-owned presentation inputs, with operation-local capture and replay.

Only successful, already validated input objects belong here. Replaying a
presentation change cannot acquire a missing input. The caller keeps the snapshot
in session state and rechecks route authorization before using it. A snapshot
records when its inputs were verified; rendering never advances that time.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import re
from threading import get_ident
import time
from typing import Any, TypeVar


INPUT_FRESHNESS_SECONDS = 30.0
_REGION = re.compile(r"[a-z0-9]+(?:[_-][a-z0-9]+)*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_T = TypeVar("_T")
DependencyKey = tuple[str, str]


class MissingPresentationDependency(RuntimeError):
    """The verified snapshot does not contain an input needed for rendering."""


def presentation_identity(value: Any) -> str:
    """Hash JSON state/configuration without retaining or printing its contents.

    Inputs must be explicit JSON values, not display labels or arbitrary reprs.
    The application chooses the complete relevant configuration/state boundary.
    """
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PresentationBinding:
    region_id: str
    access_scope: str
    calculation_version: str
    configuration_sha256: str
    applied_state_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.region_id, str) or not _REGION.fullmatch(self.region_id):
            raise ValueError("Presentation region must be an exact normalized id")
        if self.access_scope not in {f"product:{self.region_id}", f"review:{self.region_id}"}:
            raise ValueError("Presentation access scope must belong to its region")
        if (not isinstance(self.calculation_version, str)
                or not self.calculation_version
                or self.calculation_version != self.calculation_version.strip()):
            raise ValueError("Presentation calculation version is required")
        for value in (self.configuration_sha256, self.applied_state_sha256):
            if not isinstance(value, str) or not _SHA256.fullmatch(value):
                raise ValueError("Presentation state and configuration identities must be SHA-256")


def build_presentation_binding(
    region_id: str,
    access_scope: str,
    calculation_version: str,
    *,
    configuration: Any,
    applied_state: Any,
) -> PresentationBinding:
    return PresentationBinding(region_id, access_scope, calculation_version,
                               presentation_identity(configuration),
                               presentation_identity(applied_state))


@dataclass(frozen=True)
class PresentationFreshness:
    status: str
    age_seconds: float

    @property
    def is_current(self) -> bool:
        return self.status == "current"

    @property
    def can_render(self) -> bool:
        # Expiry/configuration drift allow an explicitly labelled old result.
        # A different scope, applied request or engine version cannot reuse it.
        return self.status in {"current", "expired", "configuration_changed"}


@dataclass(frozen=True)
class PresentationSnapshot:
    binding: PresentationBinding
    verified_at_monotonic: float
    verified_at_utc: str
    dependencies: Mapping[DependencyKey, Any]
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.binding, PresentationBinding):
            raise TypeError("Presentation snapshot requires a typed binding")
        if not math.isfinite(self.verified_at_monotonic) or self.verified_at_monotonic < 0:
            raise ValueError("Presentation verification time must be finite and nonnegative")
        try:
            verified = datetime.fromisoformat(self.verified_at_utc)
        except (TypeError, ValueError) as exc:
            raise ValueError("Presentation UTC verification time is invalid") from exc
        if verified.tzinfo is None or verified.utcoffset().total_seconds() != 0:
            raise ValueError("Presentation verification time must be UTC")
        if not isinstance(self.dependencies, Mapping) or not isinstance(self.payload, Mapping):
            raise TypeError("Presentation dependencies and payload must be mappings")

    def freshness(
        self,
        binding: PresentationBinding,
        *,
        now: float | None = None,
        max_age_seconds: float = INPUT_FRESHNESS_SECONDS,
    ) -> PresentationFreshness:
        if not isinstance(binding, PresentationBinding):
            raise TypeError("Presentation freshness requires a typed current binding")
        clock = time.monotonic() if now is None else float(now)
        limit = float(max_age_seconds)
        if not math.isfinite(clock) or not math.isfinite(limit) or limit <= 0:
            raise ValueError("Presentation clock and positive freshness limit must be finite")
        age = clock - self.verified_at_monotonic
        if binding.region_id != self.binding.region_id or binding.access_scope != self.binding.access_scope:
            status = "scope_changed"
        elif binding.calculation_version != self.binding.calculation_version:
            status = "calculation_changed"
        elif binding.applied_state_sha256 != self.binding.applied_state_sha256:
            status = "applied_state_changed"
        elif age < 0:
            status = "clock_reset"
        elif binding.configuration_sha256 != self.binding.configuration_sha256:
            status = "configuration_changed"
        elif age >= limit:
            status = "expired"
        else:
            status = "current"
        return PresentationFreshness(status, max(0.0, age))


def create_presentation_snapshot(
    binding: PresentationBinding,
    dependencies: Mapping[DependencyKey, Any],
    payload: Mapping[str, Any],
    *,
    verified_at_monotonic: float | None = None,
    verified_at_utc: str | None = None,
) -> PresentationSnapshot:
    """Store a completed verified operation, never call this while replaying.

    Supply the acquisition timestamp if validation/calculation took time. An
    omitted timestamp means the caller verified the inputs just before storing.
    Mapping shells are copied; immutable inputs/large geometry are shared within
    this session. Renderers must copy any UI projection they intend to mutate.
    """
    scope = _active_scope()
    if scope is not None and scope.replay:
        raise RuntimeError("Presentation replay cannot renew a snapshot")
    return PresentationSnapshot(
        binding,
        time.monotonic() if verified_at_monotonic is None else verified_at_monotonic,
        datetime.now(timezone.utc).isoformat() if verified_at_utc is None else verified_at_utc,
        dict(dependencies), dict(payload),
    )


@dataclass
class _DependencyScope:
    values: Mapping[DependencyKey, Any]
    replay: bool
    thread_id: int
    active: bool = True


_dependency_scope: ContextVar[_DependencyScope | None] = ContextVar(
    "speedlocal_presentation_dependencies", default=None,
)


def _active_scope() -> _DependencyScope | None:
    scope = _dependency_scope.get()
    if scope is not None and (not scope.active or scope.thread_id != get_ident()):
        raise RuntimeError("Presentation dependencies escaped their render operation")
    return scope


@contextmanager
def capture_presentation_dependencies() -> Iterator[dict[DependencyKey, Any]]:
    """Capture successful dependency acquisitions in one verified operation."""
    if _active_scope() is not None:
        raise RuntimeError("Presentation dependency operations cannot be nested")
    values: dict[DependencyKey, Any] = {}
    scope = _DependencyScope(values, False, get_ident())
    token = _dependency_scope.set(scope)
    try:
        yield values
    finally:
        scope.active = False
        _dependency_scope.reset(token)


@contextmanager
def replay_presentation_dependencies(
    dependencies: Mapping[DependencyKey, Any],
) -> Iterator[None]:
    """Replay the caller's session snapshot; a missing dependency fails closed."""
    if _active_scope() is not None:
        raise RuntimeError("Presentation dependency operations cannot be nested")
    if not isinstance(dependencies, Mapping):
        raise TypeError("Presentation replay requires a dependency mapping")
    scope = _DependencyScope(dependencies, True, get_ident())
    token = _dependency_scope.set(scope)
    try:
        yield
    finally:
        scope.active = False
        _dependency_scope.reset(token)


def presentation_dependency(
    name: str,
    arguments: Any,
    loader: Callable[[], _T],
) -> _T:
    """Capture/replay one exact dependency; outside an operation call normally."""
    if not isinstance(name, str) or not name or name != name.strip():
        raise ValueError("Presentation dependency name must be exact and nonempty")
    key = (name, presentation_identity(arguments))
    scope = _active_scope()
    if scope is None:
        return loader()
    if key in scope.values:
        return scope.values[key]
    if scope.replay:
        raise MissingPresentationDependency(f"Verified presentation input is missing: {name}")
    value = loader()
    # Capture owns a dict; replay is allowed to use any read-only mapping.
    assert isinstance(scope.values, dict)
    scope.values[key] = value
    return value
