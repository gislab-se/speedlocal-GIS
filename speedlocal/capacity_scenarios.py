"""Capacity-based scenarios: MW and land area, with production explicitly unknown.

Workbook parsing is offline import only. Runtime uses the revision-pinned
PostGIS context, just like the energy scenario adapter.
"""
from dataclasses import dataclass, asdict
import math
from pathlib import Path

from .scenarios import (
    ScenarioDataSnapshot, ScenarioTechnologyResult, ScenarioTechnologyShare,
    _non_negative_number, _positive_number, _sha256_path,
    scenario_source_assets_signature,
)

ADAPTER = "capacity_area_xlsx_v1"


@dataclass(frozen=True)
class CapacityObservation:
    source_scenario: str
    planning_year: int
    technology_id: str
    existing_mw: float
    new_mw: float
    km2_per_mw: float

    @property
    def capacity_mw(self):
        return self.existing_mw + self.new_mw


@dataclass(frozen=True)
class CapacitySnapshot(ScenarioDataSnapshot):
    capacity_observations: tuple[CapacityObservation, ...]


def decode_capacity_snapshot(raw):
    if set(raw) != {"schema_version", "source_assets_signature_sha256",
                    "energy_observations", "area_factors", "capacity_observations"}:
        raise ValueError("Capacity snapshot fields differ from schema")
    if raw["schema_version"] != "capacity-1.0" or raw["energy_observations"] or raw["area_factors"]:
        raise ValueError("Capacity snapshot cannot declare energy observations")
    rows = []
    for item in raw["capacity_observations"]:
        row = CapacityObservation(**item)
        if not row.source_scenario or not row.technology_id or type(row.planning_year) is not int or row.planning_year <= 0:
            raise ValueError("Invalid capacity observation identity")
        rows.append(CapacityObservation(row.source_scenario, row.planning_year, row.technology_id,
            _non_negative_number(row.existing_mw, "existing MW"),
            _non_negative_number(row.new_mw, "new MW"),
            _positive_number(row.km2_per_mw, "km2/MW")))
    return CapacitySnapshot("capacity-1.0", raw["source_assets_signature_sha256"], (), (), tuple(rows))


def model_shares(contract, scenario_id):
    values = contract.adapter_configuration()["capacity"]["model_shares"][scenario_id]
    if set(values) != set(contract.technology_ids):
        raise ValueError("Model mix must cover all declared technologies")
    result = tuple(ScenarioTechnologyShare(t, _non_negative_number(values[t], "model share"))
                   for t in contract.technology_ids)
    if not math.isclose(math.fsum(x.share_pct for x in result), 100, abs_tol=1e-9):
        raise ValueError("Model shares must sum to 100 percent")
    return result


def _capacity_scales(contract):
    """Validate every configured MW scale, including currently unselected levels."""
    config = contract.adapter_configuration()["capacity"]
    scenario_ids = tuple(level.scenario_id for level in contract.planning_levels)
    if "capacity_scale_by_scenario" not in config:
        scale = _positive_number(config.get("capacity_scale", 1.0), "capacity scale")
        return dict.fromkeys(scenario_ids, scale)
    if "capacity_scale" in config:
        raise ValueError("Capacity scalar and per-scenario scales are mutually exclusive")
    values = config["capacity_scale_by_scenario"]
    if not isinstance(values, dict) or set(values) != set(scenario_ids):
        raise ValueError("Capacity scales must cover the exact planning scenario ids")
    return {scenario_id: _positive_number(values[scenario_id],
                                         f"capacity scale for {scenario_id}")
            for scenario_id in scenario_ids}


def capacity_scale(contract, scenario_id):
    """Return a level's MW scale while retaining its exact source observations."""
    level = contract.planning_level(scenario_id)
    return _capacity_scales(contract)[level.scenario_id]


def validate_capacity_snapshot(contract, snapshot):
    _capacity_scales(contract)
    rebuilt = decode_capacity_snapshot(asdict(snapshot))
    if rebuilt != snapshot or snapshot.source_assets_signature_sha256 != scenario_source_assets_signature(contract.source):
        raise ValueError("Capacity source identity drifted")
    expected = {(l.source_scenario, l.planning_year, t)
                for l in contract.planning_levels for t in contract.technology_ids}
    keys = [(r.source_scenario, r.planning_year, r.technology_id) for r in snapshot.capacity_observations]
    if set(keys) != expected or len(keys) != len(expected):
        raise ValueError("Capacity observations must cover the exact scenario/year/technology matrix")
    for level in contract.planning_levels:
        if level.energy_scale != 1:
            raise ValueError("Capacity model does not use energy scaling")
        selected = [r for r in snapshot.capacity_observations
                    if (r.source_scenario, r.planning_year) == (level.source_scenario, level.planning_year)]
        total = math.fsum(r.capacity_mw for r in selected)
        if total <= 0:
            raise ValueError("Model capacity total must be positive")
        shares = {r.technology_id:r.share_pct for r in model_shares(contract, level.scenario_id)}
        if any(not math.isclose(r.capacity_mw / total * 100, shares[r.technology_id], abs_tol=1e-10) for r in selected):
            raise ValueError("Declared default mix differs from imported capacities")
    return snapshot


def load_capacity_snapshot(contract, path: Path):
    from openpyxl import load_workbook
    for asset in contract.source.assets.values():
        if _sha256_path(path) != asset.sha256:
            raise ValueError("Capacity workbook checksum differs from its declaration")
    config = contract.adapter_configuration()["capacity"]
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        config = contract.adapter_configuration()["capacity"]
        sheet = workbook[config["sheet"]]
        rows = []
        for level in contract.planning_levels:
            column = config["year_columns"][level.scenario_id]
            if sheet[f"{column}{config['year_row']}"].value != level.planning_year:
                raise ValueError("Capacity worksheet year differs from its declaration")
            for tech in contract.technology_ids:
                rule = config["technologies"][tech]
                if sheet[rule["capacity_unit_cell"]].value != "MW":
                    raise ValueError("Capacity worksheet must declare MW")
                if sheet[rule["factor_unit_cell"]].value != rule["factor_unit"]:
                    raise ValueError("Capacity area factor unit differs from its declaration")
                existing = _non_negative_number(sheet[f"{column}{rule['existing_row']}"].value, "existing MW")
                new = _non_negative_number(sheet[f"{column}{rule['new_row']}"].value, "new MW")
                factor = _positive_number(sheet[rule["factor_cell"]].value, "area factor")
                if rule["factor_unit"] == "MW/km2":
                    factor = 1 / factor
                elif rule["factor_unit"] == "m2/MW":
                    factor /= 1_000_000
                else:
                    raise ValueError("Unsupported capacity area unit")
                rows.append(CapacityObservation(level.source_scenario, level.planning_year, tech, existing, new, factor))
        return validate_capacity_snapshot(contract, CapacitySnapshot("capacity-1.0",
            scenario_source_assets_signature(contract.source), (), (), tuple(rows)))
    finally:
        workbook.close()


def capacity_technology_results(contract, request, snapshot):
    rows = {r.technology_id:r for r in snapshot.capacity_observations
            if r.source_scenario == request.source_scenario and r.planning_year == request.planning_year}
    if request.capacity_mw_by_technology is not None:
        capacities = dict(request.capacity_mw_by_technology)
        return tuple(ScenarioTechnologyResult(technology_id, None, None,
            capacities[technology_id] * rows[technology_id].km2_per_mw,
            capacities[technology_id], rows[technology_id].km2_per_mw)
            for technology_id in contract.technology_ids)
    scale = capacity_scale(contract, request.scenario_id)
    total = math.fsum(r.capacity_mw for r in rows.values()) * scale
    original = model_shares(contract, request.scenario_id)
    is_model = request.technology_shares == original
    result = []
    for share in request.technology_shares:
        row = rows[share.technology_id]
        mw = row.capacity_mw * scale if is_model else total * share.share_pct / 100
        result.append(ScenarioTechnologyResult(row.technology_id, None, None,
            mw * row.km2_per_mw, mw, row.km2_per_mw))
    return tuple(result)
