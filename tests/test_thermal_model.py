import numpy as np

from models.thermal_model import (ThermalParams, hold_cooling, required_cooling, simulate, step)
from scenarios.college import COLLEGE, college_data

P = ThermalParams.from_spec(COLLEGE)
DT = 5 / 60
Z = COLLEGE.n_zones


def test_energy_balance_one_step():
    T = np.full(Z, 24.5)
    qi, qs, qh = np.full(Z, 30.0), np.full(Z, 5.0), np.full(Z, 20.0)
    Tn = step(T, 35.0, qi, qs, qh, P, DT)
    stored_kw = P.c_kwh_per_k * (Tn - T) / DT
    expected = P.ua_kw_per_k * (35.0 - T) + qi + qs - qh
    assert np.allclose(stored_kw, expected)


def test_steady_state_no_drift_when_balanced():
    T = np.full(Z, 24.5)
    qi, qs = np.full(Z, 10.0), np.full(Z, 4.0)
    qh = hold_cooling(T, 33.0, qi, qs, P)
    assert np.allclose(step(T, 33.0, qi, qs, qh, P, DT), T)


def test_hotter_outdoor_needs_more_cooling():
    T = np.full(Z, 24.5)
    qi, qs = np.full(Z, 20.0), np.full(Z, 5.0)
    cool = required_cooling(T, 24.5, 30.0, qi, qs, P, DT)
    hot = required_cooling(T, 24.5, 40.0, qi, qs, P, DT)
    assert (hot > cool).all()


def test_more_internal_gain_needs_more_cooling():
    T = np.full(Z, 24.5)
    lo = required_cooling(T, 24.5, 35.0, np.full(Z, 10.0), np.zeros(Z), P, DT)
    hi = required_cooling(T, 24.5, 35.0, np.full(Z, 40.0), np.zeros(Z), P, DT)
    assert (hi > lo).all()


def test_less_hvac_raises_indoor_temperature():
    n = 12
    t_out = np.full(n, 36.0)
    qi, qs = np.full((n, Z), 30.0), np.full((n, Z), 5.0)
    full = hold_cooling(np.full(Z, 24.5), 36.0, qi[0], qs[0], P)
    T_full = simulate(np.full(Z, 24.5), t_out, qi, qs, np.tile(full, (n, 1)), P, DT)
    T_low = simulate(np.full(Z, 24.5), t_out, qi, qs, np.tile(0.6 * full, (n, 1)), P, DT)
    assert np.allclose(T_full[-1], 24.5)
    assert (T_low[-1] > T_full[-1] + 0.1).all()


def test_explicit_euler_stable():
    assert (DT * P.ua_kw_per_k / P.c_kwh_per_k < 0.05).all()


def test_design_capacity_covers_hot_afternoon_load():
    """At setpoint, cooling load must be below HVAC capacity for every zone, all day."""
    d = college_data("hot", "high")
    T = np.full((d.n_steps, Z), COLLEGE.setpoint_c)
    load = hold_cooling(T, d.t_out_c[:, None], d.q_internal_kw, d.q_solar_kw, P)
    assert (load <= d.hvac_cap_th_kw[None, :]).all(), (load.max(axis=0), d.hvac_cap_th_kw)


def test_headroom_exists_but_is_finite_at_demo_time():
    """Event time: HVAC-off drift must reach the comfort limit within a plausible window."""
    d = college_data("hot", "normal")
    i = d.index_at(14 + 20 / 60)
    load = hold_cooling(np.full(Z, 24.5), d.t_out_c[i], d.q_internal_kw[i], d.q_solar_kw[i], P)
    minutes_to_limit = (26.0 - 24.5) * P.c_kwh_per_k / load * 60
    assert (minutes_to_limit > 5).all() and (minutes_to_limit < 240).all(), minutes_to_limit
