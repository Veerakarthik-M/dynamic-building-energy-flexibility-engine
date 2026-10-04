import numpy as np
import pytest

from models.baseline_controller import (hvac_schedule, run_baseline, run_closed_loop)
from models.load_model import (comfort_violation_minutes, cop, electrical_load, energy_kwh, peak_kw)
from models.thermal_model import ThermalParams
from scenarios.college import COLLEGE, college_data


@pytest.fixture(scope="module")
def hot():
    d = college_data("hot", "normal")
    return d, run_baseline(d)


def test_baseline_deterministic_and_unchanged_without_event(hot):
    d, t1 = hot
    t2 = run_baseline(d)
    assert np.array_equal(t1.q_hvac_th, t2.q_hvac_th)
    # scale == 1 closed loop equals baseline exactly (no event => nothing changes)
    P = ThermalParams.from_spec(COLLEGE)
    en = hvac_schedule(d.n_steps, d.dt_h)
    plain = run_closed_loop(t1.T[0], d.t_out_c, d.q_internal_kw, d.q_solar_kw, en,
                            d.hvac_cap_th_kw, P, d.dt_h, scale=1.0)
    assert np.allclose(plain.T, t1.T) and np.allclose(plain.q_hvac_th, t1.q_hvac_th)


def test_baseline_keeps_comfort_when_occupied(hot):
    d, t = hot
    cv = comfort_violation_minutes(t.T_series, d.occupancy, d.dt_h)
    assert cv["building_minutes"] == 0, cv


@pytest.mark.parametrize("weather", ["hot", "mild"])
@pytest.mark.parametrize("occ", ["low", "normal", "high"])
def test_baseline_comfort_all_selectors(weather, occ):
    d = college_data(weather, occ)
    t = run_baseline(d)
    assert comfort_violation_minutes(t.T_series, d.occupancy, d.dt_h)["building_minutes"] == 0


def test_hvac_never_exceeds_capacity_and_off_at_night(hot):
    d, t = hot
    assert (t.q_hvac_th <= d.hvac_cap_th_kw + 1e-9).all() and (t.q_hvac_th >= 0).all()
    assert t.q_hvac_th[d.index_at(2)].sum() == 0


def test_hot_uses_more_energy_than_mild():
    e = {}
    for w in ("hot", "mild"):
        d = college_data(w)
        e[w] = energy_kwh(electrical_load(d, run_baseline(d).q_hvac_th).total_kw, d.dt_h)
    assert e["hot"] > e["mild"]


def test_high_occupancy_uses_more_energy_than_low():
    e = {}
    for o in ("low", "high"):
        d = college_data("hot", o)
        e[o] = energy_kwh(electrical_load(d, run_baseline(d).q_hvac_th).total_kw, d.dt_h)
    assert e["high"] > e["low"]


def test_cop_falls_when_hotter():
    assert cop(40.0, 2.8) < cop(30.0, 2.8)


def test_reduced_hvac_raises_temperature_in_closed_loop(hot):
    d, t = hot
    P = ThermalParams.from_spec(COLLEGE)
    i = d.index_at(14 + 20 / 60)
    sl = slice(i, i + 4)  # 20 minutes
    en = hvac_schedule(d.n_steps, d.dt_h)[sl]
    kw = dict(t_out=d.t_out_c[sl], q_internal=d.q_internal_kw[sl], q_solar=d.q_solar_kw[sl],
              enabled=en, cap_kw=d.hvac_cap_th_kw, params=P, dt_h=d.dt_h)
    base = run_closed_loop(t.T[i], scale=1.0, **kw)
    cut = run_closed_loop(t.T[i], scale=0.5, **kw)
    assert (cut.T[-1] > base.T[-1]).all()
    assert cut.q_hvac_th.sum() < base.q_hvac_th.sum()


def test_load_components_sum_and_metrics(hot):
    d, t = hot
    L = electrical_load(d, t.q_hvac_th)
    assert np.allclose(L.total_kw, L.hvac_kw + L.lighting_kw + L.base_kw)
    pk, i = peak_kw(L.total_kw)
    assert pk == L.total_kw.max() and 8 <= i * d.dt_h <= 20
