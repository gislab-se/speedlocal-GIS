from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable


WHOLE_METRE_SLIDER_FORMAT = "%.0f m"


@dataclass(frozen=True)
class FilterSourceControl:
    """One source checkbox in the shared wind/solar presentation model."""

    id: str
    label: str
    key: str
    ready: bool
    help_text: str = ""


@dataclass(frozen=True)
class FilterGroupControl:
    """Technology-neutral presentation facts for one geographic filter."""

    id: str
    label: str
    interpretation: str
    analysis_label: str
    analysis_min_m: float | int
    analysis_max_m: float | int
    analysis_step_m: float | int
    analysis_key: str
    analysis_help: str
    sources: tuple[FilterSourceControl, ...]

    @property
    def primary_sources(self) -> tuple[FilterSourceControl, ...]:
        return self.sources[:1]

    @property
    def additional_sources(self) -> tuple[FilterSourceControl, ...]:
        return self.sources[1:]

def filter_group_control(
    *,
    group_id: str,
    label: str,
    interpretation: str,
    analysis_label: str,
    analysis_min_m: float | int,
    analysis_max_m: float | int,
    analysis_step_m: float | int,
    analysis_key: str,
    analysis_help: str,
    sources: Iterable[FilterSourceControl],
) -> FilterGroupControl:
    """Validate and freeze the common native filter-group UI contract."""

    source_tuple = tuple(sources)
    source_ids = [source.id for source in source_tuple]
    source_keys = [source.key for source in source_tuple]
    if not str(group_id) or not str(label) or not str(analysis_label):
        raise ValueError("Filter control requires group, display, and analysis labels")
    if not str(interpretation) or not str(analysis_key):
        raise ValueError("Filter control requires interpretation and a stable analysis key")
    if any(not source_id for source_id in source_ids):
        raise ValueError("Filter source ids must be non-empty")
    if len(source_ids) != len(set(source_ids)):
        raise ValueError(f"Filter source ids must be unique for {group_id}")
    if any(not key for key in source_keys) or len(source_keys) != len(set(source_keys)):
        raise ValueError(f"Filter source keys must be non-empty and unique for {group_id}")
    minimum = float(analysis_min_m)
    maximum = float(analysis_max_m)
    step = float(analysis_step_m)
    if not all(math.isfinite(value) for value in (minimum, maximum, step)):
        raise ValueError(f"Filter distance values must be finite for {group_id}")
    if minimum > maximum or step <= 0:
        raise ValueError(f"Invalid filter distance range for {group_id}")
    return FilterGroupControl(
        id=str(group_id),
        label=str(label),
        interpretation=str(interpretation),
        analysis_label=str(analysis_label),
        analysis_min_m=analysis_min_m,
        analysis_max_m=analysis_max_m,
        analysis_step_m=analysis_step_m,
        analysis_key=str(analysis_key),
        analysis_help=str(analysis_help),
        sources=source_tuple,
    )
