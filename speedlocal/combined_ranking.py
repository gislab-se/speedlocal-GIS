from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
from typing import Iterable, Mapping


TECHNICAL_RANKING_MODEL_ID = "landscape_potential_core_v1"
WIND_POTENTIAL_CLASS_MAX_PCT = (
    0.0,
    5.0,
    10.0,
    15.0,
    25.0,
    35.0,
    50.0,
    65.0,
    80.0,
    100.0,
)


def _unit_interval(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        raise ValueError(f"{label} must be between 0 and 1")
    return number


@dataclass(frozen=True)
class TechnicalRankingWeights:
    """Signed, region-neutral weights for one technology ranking model."""

    technology_id: str
    landscape: float
    potential: float
    core: float

    def __post_init__(self) -> None:
        if self.technology_id not in {"wind", "solar"}:
            raise ValueError("Technical ranking supports wind or solar")
        values = (
            _unit_interval(self.landscape, "landscape weight"),
            _unit_interval(self.potential, "potential weight"),
            _unit_interval(self.core, "core weight"),
        )
        if not math.isclose(math.fsum(values), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("Technical ranking weights must sum to exactly 1")
        if self.technology_id == "solar" and self.core != 0.0:
            raise ValueError("Solar technical ranking cannot use wind-core weight")


@dataclass(frozen=True)
class WindCoreMetric:
    cell_id: str
    zone_id: str
    zone_size: int
    core_distance: int
    core_score: float
    center_mass_rank: int


def technical_priority_score(
    *,
    landscape_score: float,
    potential_fraction: float,
    core_score: float,
    weights: TechnicalRankingWeights,
) -> float:
    """Apply one explicit ranking formula without hidden regional defaults."""

    landscape = _unit_interval(landscape_score, "landscape score")
    potential = _unit_interval(potential_fraction, "potential fraction")
    core = _unit_interval(core_score, "core score")
    return min(
        1.0,
        max(
            0.0,
            (weights.landscape * landscape)
            + (weights.potential * potential)
            + (weights.core * core),
        ),
    )


def wind_potential_class_index(potential_pct: float) -> int:
    """Return the versioned wind-potential class used by core topology."""

    if isinstance(potential_pct, bool) or not isinstance(
        potential_pct, (int, float)
    ):
        raise TypeError("Wind potential percentage must be a finite number")
    value = float(potential_pct)
    if not math.isfinite(value) or value < 0.0 or value > 100.0:
        raise ValueError("Wind potential percentage must be between 0 and 100")
    for index, maximum in enumerate(WIND_POTENTIAL_CLASS_MAX_PCT):
        if value <= maximum:
            return index
    raise AssertionError("Validated wind potential did not match a class")


def landscape_group_score(
    *,
    analysis_kind: str,
    distance_m: float,
    intersects: bool,
    distance_cap_m: float,
) -> float:
    """Score one complete support observation using declared group semantics."""

    if isinstance(distance_m, bool) or not isinstance(distance_m, (int, float)):
        raise TypeError("Landscape distance must be a finite number")
    distance = float(distance_m)
    cap = float(distance_cap_m)
    if not math.isfinite(distance) or distance < 0.0:
        raise ValueError("Landscape distance must be finite and non-negative")
    if not math.isfinite(cap) or cap <= 0.0:
        raise ValueError("Landscape distance cap must be finite and positive")
    if not isinstance(intersects, bool):
        raise TypeError("Landscape intersection must be boolean")
    normalized = min(1.0, max(0.0, distance / cap))
    if analysis_kind == "proximity_feasibility":
        return 1.0 if intersects else 1.0 - normalized
    if analysis_kind in {"distance_conflict", "hard_exclusion"}:
        return 0.0 if intersects else normalized
    raise NotImplementedError(
        f"Unsupported landscape ranking analysis kind: {analysis_kind}"
    )


def wind_core_metrics(
    class_by_cell: Mapping[str, int],
    neighbor_map: Mapping[str, Iterable[str]],
) -> tuple[WindCoreMetric, ...]:
    """Derive the accepted same-class connected-zone/core ranking exactly."""

    if not class_by_cell:
        return ()
    ordered_cells = tuple(class_by_cell)
    if any(not isinstance(cell_id, str) or not cell_id for cell_id in ordered_cells):
        raise ValueError("Wind-core cells must use non-empty string ids")
    if len(ordered_cells) != len(set(ordered_cells)):
        raise ValueError("Wind-core cells must be unique")
    classes: dict[str, int] = {}
    for cell_id, value in class_by_cell.items():
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("Wind-core class indices must be non-negative integers")
        classes[cell_id] = value
    neighbors = {
        cell_id: tuple(str(neighbor) for neighbor in neighbor_map.get(cell_id, ()))
        for cell_id in ordered_cells
    }

    result: dict[str, WindCoreMetric] = {}
    visited: set[str] = set()
    zone_counter = 0
    for cell_id in ordered_cells:
        if cell_id in visited:
            continue
        class_index = classes[cell_id]
        queue: deque[str] = deque([cell_id])
        component: list[str] = []
        visited.add(cell_id)
        while queue:
            current = queue.popleft()
            component.append(current)
            for neighbor in neighbors.get(current, ()):
                if neighbor in visited or classes.get(neighbor) != class_index:
                    continue
                visited.add(neighbor)
                queue.append(neighbor)

        component_set = set(component)
        boundary = [
            cell
            for cell in component
            if any(
                neighbor not in component_set
                for neighbor in neighbors.get(cell, ())
            )
        ] or list(component)
        distance_by_cell: dict[str, int | None] = {
            cell: None for cell in component
        }
        frontier: deque[str] = deque()
        for cell in boundary:
            distance_by_cell[cell] = 0
            frontier.append(cell)
        while frontier:
            current = frontier.popleft()
            distance = int(distance_by_cell[current] or 0)
            for neighbor in neighbors.get(current, ()):
                if (
                    neighbor not in component_set
                    or distance_by_cell[neighbor] is not None
                ):
                    continue
                distance_by_cell[neighbor] = distance + 1
                frontier.append(neighbor)

        max_distance = max(
            (int(distance_by_cell[cell] or 0) for cell in component),
            default=0,
        )
        ranked = sorted(
            component,
            key=lambda cell: (-int(distance_by_cell[cell] or 0), cell),
        )
        rank_by_cell = {cell: index + 1 for index, cell in enumerate(ranked)}
        zone_id = f"class_{class_index}_{zone_counter}"
        zone_counter += 1
        for cell in component:
            core_distance = int(distance_by_cell[cell] or 0)
            core_score = (
                0.0
                if max_distance <= 0
                else float(core_distance) / float(max_distance)
            )
            result[cell] = WindCoreMetric(
                cell_id=cell,
                zone_id=zone_id,
                zone_size=len(component),
                core_distance=core_distance,
                core_score=round(core_score, 3),
                center_mass_rank=rank_by_cell[cell],
            )
    return tuple(result[cell_id] for cell_id in ordered_cells)


def outside_ring_distances(
    *,
    eligible_cell_ids: Iterable[str],
    potential_cell_ids: Iterable[str],
    neighbor_map: Mapping[str, Iterable[str]],
) -> Mapping[str, int]:
    """Return deterministic rings for cells reachable from the supplied anchors."""

    eligible = tuple(dict.fromkeys(str(value) for value in eligible_cell_ids))
    eligible_set = set(eligible)
    potential = tuple(dict.fromkeys(str(value) for value in potential_cell_ids))
    if not eligible or any(not value for value in eligible):
        raise ValueError("Outside-ring eligible cells must not be empty")
    if any(not value or value not in eligible_set for value in potential):
        raise ValueError(
            "Outside-ring anchors must be inside the eligible domain"
        )
    if not potential:
        return {}
    distances = {cell_id: 0 for cell_id in potential}
    frontier: deque[str] = deque(potential)
    while frontier:
        current = frontier.popleft()
        for neighbor_value in neighbor_map.get(current, ()):
            neighbor = str(neighbor_value)
            if neighbor not in eligible_set or neighbor in distances:
                continue
            distances[neighbor] = distances[current] + 1
            frontier.append(neighbor)
    # A technology-support domain may contain islands or other disconnected
    # components. Components without a selected inside-potential anchor are
    # deliberately absent: they are not valid outside-expansion candidates.
    return {
        cell_id: distances[cell_id]
        for cell_id in eligible
        if cell_id in distances
    }


__all__ = [
    "TECHNICAL_RANKING_MODEL_ID",
    "WIND_POTENTIAL_CLASS_MAX_PCT",
    "TechnicalRankingWeights",
    "WindCoreMetric",
    "landscape_group_score",
    "outside_ring_distances",
    "technical_priority_score",
    "wind_potential_class_index",
    "wind_core_metrics",
]
