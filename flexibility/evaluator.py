"""Phase 8 — Candidate simulation + evaluation (batched over candidates with NumPy).

For every candidate we simulate the event window + a recovery window with the
thermostat in the loop, then compute: reduction achieved, HVAC/lighting split,
rebound, energy delta, comfort margin, peak.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from data.synthetic_building import COMFORT_BAND_C, SimulationData
from flexibility.constraints import OCC_THRESHOLD
from flexibility.rebound import rebound_metrics
from models.baseline_controller import thermostat_cooling
from models.load_model import cop
from models.thermal_model import ThermalParams, step


@dataclass
class Context:
    data: SimulationData
    i0: int
    T0: np.ndarray
    params: ThermalParams
    n_hor: int
    enabled: np.ndarray
    t_out: np.ndarray
    q_int: np.ndarray
    q_sol: np.ndarray
    lighting_zone: np.ndarray
    cap: np.ndarray
    cop_h: np.ndarray
    base_kw: np.ndarray
    occupancy: np.ndarray
    times: list


@dataclass
class BatchSim:
    T: np.ndarray          # (C, h+1, z)
    q_th: np.ndarray       # (C, h, z)
    hvac_kw: np.ndarray    # (C, h)
    light_kw: np.ndarray   # (C, h)
    total_kw: np.ndarray   # (C, h)


def make_context(data: SimulationData, i0: int, T0, params: ThermalParams, n_hor: int,
                 enabled_full: np.ndarray, solar_mult: float = 1.0) -> Context:
    n_hor = min(n_hor, data.n_steps - i0)
    sl = slice(i0, i0 + n_hor)
    times = [f"{(data.time[k] + pd.Timedelta(minutes=5)):%H:%M}" for k in range(i0, i0 + n_hor)]
    return Context(
        data=data, i0=i0, T0=np.asarray(T0, dtype=float), params=params, n_hor=n_hor,
        enabled=enabled_full[sl], t_out=data.t_out_c[sl], q_int=data.q_internal_kw[sl],
        q_sol=data.q_solar_kw[sl] * solar_mult, lighting_zone=data.lighting_kw[sl],
        cap=data.hvac_cap_th_kw, cop_h=cop(data.t_out_c[sl], data.spec.hvac_cop),
        base_kw=data.base_load_kw[sl], occupancy=data.occupancy[sl], times=times,
    )


def simulate_batch(ctx: Context, scales: np.ndarray, light_cuts: np.ndarray, n_event: int) -> BatchSim:
    C, z = scales.shape
    h = ctx.n_hor
    T = np.empty((C, h + 1, z))
    T[:, 0, :] = ctx.T0
    q = np.empty((C, h, z))
    for k in range(h):
        if k < n_event:
            s, lc = scales, light_cuts[:, None]
        else:
            s, lc = 1.0, 0.0
        cool = np.minimum(thermostat_cooling(T[:, k, :], ctx.cap, ctx.enabled[k]) * s, ctx.cap)
        q_int = ctx.q_int[k] - lc * ctx.lighting_zone[k]   # dimmed lights also emit less heat
        q[:, k, :] = cool
        T[:, k + 1, :] = step(T[:, k, :], ctx.t_out[k], q_int, ctx.q_sol[k], cool, ctx.params, ctx.data.dt_h)
    light = np.tile(ctx.lighting_zone.sum(axis=1), (C, 1))
    light[:, :min(n_event, h)] *= (1.0 - light_cuts)[:, None]
    hvac = q.sum(axis=2) / ctx.cop_h[None, :]
    total = hvac + light + ctx.base_kw[None, :]
    return BatchSim(T, q, hvac, light, total)


def evaluate(ctx: Context, sim: BatchSim, base: BatchSim, n_event: int, band=COMFORT_BAND_C) -> dict:
    dt = ctx.data.dt_h
    ev = slice(0, min(n_event, ctx.n_hor))
    red = (base.total_kw[0, ev][None] - sim.total_kw[:, ev]).mean(axis=1)
    hvac_red = (base.hvac_kw[0, ev][None] - sim.hvac_kw[:, ev]).mean(axis=1)
    light_red = (base.light_kw[0, ev][None] - sim.light_kw[:, ev]).mean(axis=1)
    reb = rebound_metrics(base.total_kw[0], sim.total_kw, n_event, ctx.n_hor - n_event, dt)
    occ = (ctx.occupancy > OCC_THRESHOLD)[None, :, :]
    Tn = sim.T[:, 1:, :]
    margin = np.where(occ, np.minimum(band[1] - Tn, Tn - band[0]), np.inf).min(axis=(1, 2))
    return {
        "reduction_kw": red, "hvac_kw": hvac_red, "light_kw": light_red,
        "rebound_kw": reb["rebound_peak_kw"], "rebound_kwh": reb["rebound_kwh"],
        "rebound_min": reb["rebound_minutes"],
        "energy_delta_kwh": (sim.total_kw - base.total_kw[0][None]).sum(axis=1) * dt,
        "min_margin_c": margin, "peak_kw": sim.total_kw.max(axis=1),
    }
