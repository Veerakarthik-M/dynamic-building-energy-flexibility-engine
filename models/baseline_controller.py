"""Phase 3 — Baseline thermostat (conventional, grid-unaware).

Per zone, proportional thermostat (prototype assumption):
    cooling = capacity * clip((T - 23.5) / (25.5 - 23.5), 0, 1)       [only when schedule ON]
HVAC schedule ON 05:00-20:00 (pre-cool before classes), OFF otherwise.

The same closed loop is reused by the flexibility engine: an HVAC *override
multiplier* `scale` (1.0 = normal) is applied to the thermostat output. This
means "HVAC 60 %" = 60 % of what the thermostat would have commanded, and with
scale == 1 the result is IDENTICAL to the baseline (tested).

The baseline is simulated for 1 spin-up day + 1 reported day so the reported
day starts from a periodic steady state (no artificial cold start).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from data.synthetic_building import SimulationData
from models.thermal_model import ThermalParams, step

THERMOSTAT_ZERO_C = 23.5   # cooling = 0 at/below this
THERMOSTAT_FULL_C = 25.5   # cooling = capacity at/above this
HVAC_ON_HOUR = 5.0
HVAC_OFF_HOUR = 20.0


@dataclass
class Trajectory:
    """Closed-loop result over n steps. T has n+1 rows (T[0] = initial state)."""
    T: np.ndarray            # (n+1, z) indoor temperature, degC
    q_hvac_th: np.ndarray    # (n, z) cooling delivered, kW thermal

    @property
    def T_series(self) -> np.ndarray:
        """Temperature at the start of each step (aligned with time index)."""
        return self.T[:-1]


def thermostat_cooling(T, cap_kw, enabled):
    frac = np.clip((T - THERMOSTAT_ZERO_C) / (THERMOSTAT_FULL_C - THERMOSTAT_ZERO_C), 0.0, 1.0)
    return cap_kw * frac * enabled


def hvac_schedule(n_steps: int, dt_h: float) -> np.ndarray:
    hours = (np.arange(n_steps) * dt_h) % 24.0
    return ((hours >= HVAC_ON_HOUR) & (hours < HVAC_OFF_HOUR)).astype(float)


def run_closed_loop(T0, t_out, q_internal, q_solar, enabled, cap_kw,
                    params: ThermalParams, dt_h: float, scale=1.0) -> Trajectory:
    """Thermostat + thermal model. `scale`: scalar, (n,) or (n, z) HVAC override multiplier."""
    n = len(t_out)
    z = len(cap_kw)
    s = np.asarray(scale, dtype=float)
    if s.ndim == 1:
        s = s[:, None]
    scale = np.broadcast_to(s, (n, z))
    T = np.empty((n + 1, z))
    q = np.empty((n, z))
    T[0] = T0
    for k in range(n):
        q[k] = np.minimum(thermostat_cooling(T[k], cap_kw, enabled[k]) * scale[k], cap_kw)
        T[k + 1] = step(T[k], t_out[k], q_internal[k], q_solar[k], q[k], params, dt_h)
    return Trajectory(T, q)


def run_baseline(data: SimulationData, params: ThermalParams | None = None,
                 spinup_days: int = 1) -> Trajectory:
    """Baseline day (periodic steady state). No awareness of any grid event."""
    params = params or ThermalParams.from_spec(data.spec)
    reps = spinup_days + 1
    n = data.n_steps
    tile = lambda a: np.concatenate([a] * reps, axis=0)
    enabled = hvac_schedule(n * reps, data.dt_h)
    traj = run_closed_loop(
        np.full(data.spec.n_zones, data.spec.setpoint_c),
        tile(data.t_out_c), tile(data.q_internal_kw), tile(data.q_solar_kw),
        enabled, data.hvac_cap_th_kw, params, data.dt_h,
    )
    s = spinup_days * n
    return Trajectory(traj.T[s:], traj.q_hvac_th[s:])
