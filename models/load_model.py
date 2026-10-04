"""Phase 4 — Electrical load model + KPI metrics.

HVAC electrical kW = cooling thermal kW / COP(T_out)
COP(T_out) = cop_ref * (1 - 0.01 * (T_out - 35))   (prototype assumption:
chiller efficiency falls ~1 %/degC above 35 degC; floor at 50 % of cop_ref).

Total electrical kW = HVAC + lighting + base (base = essential, never curtailed).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from data.synthetic_building import COMFORT_BAND_C, SimulationData

COP_DERATE_PER_C = 0.01
COP_REF_T_C = 35.0


def cop(t_out, cop_ref: float):
    factor = np.maximum(1.0 - COP_DERATE_PER_C * (np.asarray(t_out) - COP_REF_T_C), 0.5)
    return cop_ref * factor


@dataclass
class ElectricalLoad:
    hvac_kw: np.ndarray       # (n,)
    lighting_kw: np.ndarray   # (n,)
    base_kw: np.ndarray       # (n,)

    @property
    def total_kw(self) -> np.ndarray:
        return self.hvac_kw + self.lighting_kw + self.base_kw


def electrical_load(data: SimulationData, q_hvac_th: np.ndarray, lighting_kw=None) -> ElectricalLoad:
    """q_hvac_th (n, z) thermal -> building electrical kW. lighting_kw (n,) optional override."""
    hvac = q_hvac_th.sum(axis=1) / cop(data.t_out_c, data.spec.hvac_cop)
    light = data.lighting_kw.sum(axis=1) if lighting_kw is None else np.asarray(lighting_kw)
    return ElectricalLoad(hvac, light, data.base_load_kw)


# ---------------- KPI metrics ----------------

def energy_kwh(total_kw: np.ndarray, dt_h: float) -> float:
    return float(np.sum(total_kw) * dt_h)


def peak_kw(total_kw: np.ndarray) -> tuple[float, int]:
    i = int(np.argmax(total_kw))
    return float(total_kw[i]), i


def comfort_violation_minutes(T_series: np.ndarray, occupancy: np.ndarray, dt_h: float,
                              band=COMFORT_BAND_C, occ_threshold: float = 0.02) -> dict:
    """Violations counted only while a zone is occupied.

    Returns building minutes (any occupied zone out of band) and zone-minutes (sum).
    """
    lo, hi = band
    out = (T_series < lo - 1e-9) | (T_series > hi + 1e-9)
    bad = out & (occupancy > occ_threshold)
    minutes = dt_h * 60
    return {
        "building_minutes": float(bad.any(axis=1).sum() * minutes),
        "zone_minutes": float(bad.sum() * minutes),
    }
