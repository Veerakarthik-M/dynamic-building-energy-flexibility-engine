"""Phase 2 — Physics-informed building thermal model (first-order RC per zone).

    T_next = T + dt/C * [ UA*(T_out - T) + Q_internal + Q_solar - Q_hvac ]

T [degC], C [kWh/degC], UA [kW/degC], Q [kW thermal], dt [h].
Zones are independent (no inter-zone coupling) — prototype simplification.
Parameters are SIMULATION assumptions, not measured. Not a digital twin.

Explicit Euler is stable here because dt*UA/C << 1 (checked in tests).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from data.synthetic_building import BuildingSpec


@dataclass(frozen=True)
class ThermalParams:
    c_kwh_per_k: np.ndarray   # (z,)
    ua_kw_per_k: np.ndarray   # (z,)

    @classmethod
    def from_spec(cls, spec: BuildingSpec) -> "ThermalParams":
        return cls(
            np.array([z.c_kwh_per_k for z in spec.zones], dtype=float),
            np.array([z.ua_kw_per_k for z in spec.zones], dtype=float),
        )

    def perturbed(self, ua_factor: float = 1.0, c_factor: float = 1.0) -> "ThermalParams":
        """Return a copy with scaled UA / C (used later for plant-vs-model mismatch)."""
        return ThermalParams(self.c_kwh_per_k * c_factor, self.ua_kw_per_k * ua_factor)


def step(T, t_out, q_internal, q_solar, q_hvac, params: ThermalParams, dt_h: float):
    """One timestep. Inputs broadcast over zones. Returns T_next (z,)."""
    net_kw = (params.ua_kw_per_k * (t_out - T) + q_internal + q_solar - q_hvac)
    return T + dt_h / params.c_kwh_per_k * net_kw


def required_cooling(T, t_set, t_out, q_internal, q_solar, params: ThermalParams, dt_h: float):
    """Thermal cooling kW that lands exactly on t_set next step (unclipped; may be <0)."""
    return (q_internal + q_solar + params.ua_kw_per_k * (t_out - T)
            - params.c_kwh_per_k / dt_h * (t_set - T))


def hold_cooling(T, t_out, q_internal, q_solar, params: ThermalParams):
    """Steady cooling kW that keeps T constant (the instantaneous cooling load)."""
    return q_internal + q_solar + params.ua_kw_per_k * (t_out - T)


def simulate(T0, t_out, q_internal, q_solar, q_hvac, params: ThermalParams, dt_h: float):
    """Open-loop trajectory for a given HVAC schedule.

    t_out (n,), q_* (n, z) -> returns T (n+1, z) with T[0] = T0.
    """
    n = len(t_out)
    z = len(params.c_kwh_per_k)
    T = np.empty((n + 1, z))
    T[0] = T0
    for k in range(n):
        T[k + 1] = step(T[k], t_out[k], q_internal[k], q_solar[k], q_hvac[k], params, dt_h)
    return T
