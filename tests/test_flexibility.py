"""Phase 14 — Comprehensive test suite for flexibility engine and edge cases."""
from __future__ import annotations

import numpy as np
import pytest

from scenarios import SCENARIOS
from scenarios.college import COLLEGE, college_data
from scenarios.office import OFFICE, office_data
from flexibility.engine import assess, _plan
from flexibility.event import DemandResponseEvent
from flexibility.optimizer import search, max_feasible_kw
from flexibility.constraints import static_violations
from flexibility.candidate_actions import Candidate
from models.thermal_model import ThermalParams
from models.baseline_controller import run_baseline, hvac_schedule
from models.load_model import electrical_load


@pytest.fixture(scope="module")
def college_hot():
    d = college_data("hot", "normal")
    params = ThermalParams.from_spec(COLLEGE)
    base = run_baseline(d, params)
    load = electrical_load(d, base.q_hvac_th)
    return d, params, base, load


def test_no_event_baseline_unchanged(college_hot):
    d, params, base, load = college_hot
    i0 = d.index_at(14 + 20 / 60)
    en = hvac_schedule(d.n_steps, d.dt_h)
    # Event with 0 kW request or no action candidate index 0
    res = search(d, i0, base.T_series[i0], params, 20, 10.0, en, load.total_kw.max())
    no_act = res.table.iloc[0]
    assert no_act["reduction_kw"] == 0.0
    assert no_act["rebound_kw"] == 0.0
    assert no_act["feasible"] == True


def test_essential_load_constraint():
    cand_viol = Candidate("uniform", 0.5, 0.0, (0.5, 0.5, 0.5, 0.5, 0.5), base_cut_kw=10.0)
    v = static_violations(cand_viol, 20)
    assert any(cat == "essential" for cat, _ in v)

    cand_ok = Candidate("uniform", 0.5, 0.0, (0.5, 0.5, 0.5, 0.5, 0.5), base_cut_kw=0.0)
    v_ok = static_violations(cand_ok, 20)
    assert not any(cat == "essential" for cat, _ in v_ok)


def test_lighting_minimum_constraint():
    cand_dim_bad = Candidate("uniform", 0.8, 0.50, (0.8, 0.8, 0.8, 0.8, 0.8))  # 50% cut > allowed 30% cut
    v = static_violations(cand_dim_bad, 20)
    assert any(cat == "lighting" for cat, _ in v)


def test_event_duration_limit():
    cand = Candidate("uniform", 0.8, 0.15, (0.8, 0.8, 0.8, 0.8, 0.8))
    v_long = static_violations(cand, 90)  # > 60 min
    assert any(cat == "duration" for cat, _ in v_long)


def test_rebound_increases_with_more_aggressive_reduction(college_hot):
    d, params, base, load = college_hot
    i0 = d.index_at(14 + 20 / 60)
    en = hvac_schedule(d.n_steps, d.dt_h)
    res = search(d, i0, base.T_series[i0], params, 20, 50.0, en, load.total_kw.max())
    t = res.table[res.table["feasible"]]
    
    # Compare mild cut vs aggressive cut rebound
    hvac_mild = t[t["hvac_level"] == 0.90]
    hvac_aggr = t[t["hvac_level"] == 0.80]
    if len(hvac_mild) and len(hvac_aggr):
        reb_mild = hvac_mild.iloc[0]["rebound_kw"]
        reb_aggr = hvac_aggr.iloc[0]["rebound_kw"]
        assert reb_aggr >= reb_mild


def test_small_request_easier_than_large(college_hot):
    d, _, _, _ = college_hot
    a30 = assess(d, 14.33, 20, 30.0)
    a70 = assess(d, 14.33, 20, 70.0)
    assert a30.status in ("full", "partial")
    assert a70.shortfall_kw >= a30.shortfall_kw


def test_office_scenario_execution():
    d = office_data("mild", "normal")
    a = assess(d, 14.0, 20, 20.0)
    assert a.feasible_kw > 0
    assert len(a.kpis) > 0


def test_edge_cases_zero_occupancy():
    import dataclasses
    zones = tuple(dataclasses.replace(z, occupancy_keypoints=((0, 0), (24, 0))) for z in COLLEGE.zones)
    spec = dataclasses.replace(COLLEGE, zones=zones)
    from data.synthetic_building import generate_building_data
    d = generate_building_data(spec)
    a = assess(d, 14.0, 20, 30.0)
    assert a.state["occupancy"] == 0.0


def test_edge_case_request_larger_than_capacity(college_hot):
    d, _, _, _ = college_hot
    a = assess(d, 14.33, 20, 200.0)  # 200 kW exceeds total flexible load
    assert a.status == "infeasible"
    assert "exceeds" in a.limiting_reason or "rejected" in a.limiting_reason
