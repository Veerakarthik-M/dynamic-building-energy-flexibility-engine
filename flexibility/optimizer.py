"""Phase 9 — Decision engine: search -> constrain -> score -> pick best.

Score (lower is better; weights are prototype assumptions):
    10 * shortfall_kw           (not meeting the request is the worst outcome)
  +  1 * overshoot_kw           (do not curtail more than asked)
  + 0.3 * rebound_peak_kw       (avoid shifting demand into recovery)
  +  40 * max(0, 0.6 - margin)  (stay away from the comfort edge)
The goal is NOT to maximise reduction: it is to meet the request safely with minimum side effects.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from data.synthetic_building import COMFORT_BAND_C
from flexibility.candidate_actions import CandidateSet, generate_candidates
from flexibility.constraints import CATEGORY, static_violations, trajectory_violations
from flexibility.evaluator import Context, BatchSim, evaluate, make_context, simulate_batch
from flexibility.event import RECOVERY_MIN
from models.thermal_model import ThermalParams, hold_cooling

W_SHORTFALL, W_OVERSHOOT, W_REBOUND, W_MARGIN, MARGIN_TARGET_C = 10.0, 1.0, 0.3, 40.0, 0.6


@dataclass
class SearchResult:
    duration_min: int
    requested_kw: float
    n_event: int
    ctx: Context
    cands: CandidateSet
    sim: BatchSim
    base: BatchSim
    table: pd.DataFrame
    best_idx: int
    upper_bound_kw: float       # max reduction ignoring comfort/peak (total controllable capacity)
    minutes_to_limit: np.ndarray


def score(reduction, requested, rebound_kw, margin):
    shortfall = np.maximum(0.0, requested - reduction)
    overshoot = np.maximum(0.0, reduction - requested)
    return (W_SHORTFALL * shortfall + W_OVERSHOOT * overshoot + W_REBOUND * rebound_kw
            + W_MARGIN * np.maximum(0.0, MARGIN_TARGET_C - np.minimum(margin, 5.0)))


def search(data, i0, T0, params: ThermalParams, duration_min: int, requested_kw: float,
           enabled_full, baseline_peak_kw: float, solar_mult: float = 1.0,
           recovery_min: int = RECOVERY_MIN) -> SearchResult:
    n_event = duration_min // 5
    ctx = make_context(data, i0, T0, params, n_event + recovery_min // 5, enabled_full, solar_mult)
    hold = hold_cooling(ctx.T0, ctx.t_out[0], ctx.q_int[0], ctx.q_sol[0], params)
    mtl = np.clip((COMFORT_BAND_C[1] - ctx.T0) * params.c_kwh_per_k / np.maximum(hold, 1e-6) * 60, 0, 999)
    cands = generate_candidates(mtl)
    z = data.spec.n_zones
    base = simulate_batch(ctx, np.ones((1, z)), np.zeros(1), n_event)
    sim = simulate_batch(ctx, cands.scales, cands.light_cuts, n_event)
    ev = evaluate(ctx, sim, base, n_event)

    rows, upper = [], 0.0
    for c, cand in enumerate(cands.candidates):
        viol = static_violations(cand, duration_min)
        if not viol:
            upper = max(upper, ev["reduction_kw"][c])
        viol += trajectory_violations(sim.T[c, 1:, :], ctx.occupancy, sim.q_th[c], ctx.cap,
                                      sim.total_kw[c], baseline_peak_kw, data.spec.zone_names, ctx.times)
        if c == 0:
            viol = []   # no-action is the baseline: always the fallback
        rows.append({
            "action": cand.label, "strategy": cand.strategy, "hvac_level": cand.hvac_level,
            "light_cut": cand.light_cut, "reduction_kw": ev["reduction_kw"][c],
            "hvac_kw": ev["hvac_kw"][c], "light_kw": ev["light_kw"][c],
            "rebound_kw": ev["rebound_kw"][c], "rebound_kwh": ev["rebound_kwh"][c],
            "rebound_min": ev["rebound_min"][c],
            "energy_delta_kwh": ev["energy_delta_kwh"][c], "min_margin_c": ev["min_margin_c"][c],
            "feasible": not viol, "rejected_by": ", ".join(sorted({CATEGORY[k] for k, _ in viol})),
            "reason": "; ".join(m for _, m in viol),
        })
    table = pd.DataFrame(rows)
    table["score"] = score(table["reduction_kw"].to_numpy(), requested_kw,
                           table["rebound_kw"].to_numpy(), table["min_margin_c"].to_numpy())
    feas = table[table["feasible"]]
    best = int(feas["score"].idxmin())
    return SearchResult(duration_min, requested_kw, n_event, ctx, cands, sim, base, table, best, upper, mtl)


def max_feasible_kw(res: SearchResult) -> float:
    t = res.table
    return float(max(0.0, t.loc[t["feasible"], "reduction_kw"].max()))
