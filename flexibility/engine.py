"""Orchestrates the 9 stages: SENSE -> PREDICT -> GENERATE -> CONSTRAIN -> EVALUATE -> DECIDE
-> ACT -> VERIFY -> LEARN.

PLANT vs MODEL: the "plant" (what the simulated building really does) differs from the engine's
model by a few percent (UA, C, solar). Without this the VERIFY/LEARN stages would be theatre.
All of it is SIMULATION; the mismatch values are prototype assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from data.synthetic_building import COMFORT_BAND_C, SimulationData
from flexibility.evaluator import make_context, simulate_batch, evaluate
from flexibility.event import MAX_EVENT_MIN, RECOVERY_MIN, DemandResponseEvent
from flexibility.optimizer import SearchResult, max_feasible_kw, search
from flexibility.rebound import rebound_metrics
from models.baseline_controller import hvac_schedule, run_baseline, run_closed_loop
from models.load_model import (cop, comfort_violation_minutes, electrical_load, energy_kwh, peak_kw)
from models.thermal_model import ThermalParams

PLANT_MISMATCH = {"ua": 1.07, "c": 0.95, "solar": 1.05}   # simulated model error (prototype assumption)
UNCERTAINTY_CORNERS = [(0.9, 1.1, 0.9), (1.1, 0.9, 1.1), (1.1, 1.1, 1.0), (0.9, 0.9, 1.0),
                       (1.0, 1.0, 1.1), (1.0, 1.0, 0.9)]   # (UA, C, solar) multipliers
FULL_FRACTION, INFEASIBLE_FRACTION = 0.97, 0.50
RISK_LOW_C, RISK_MED_C = 0.5, 0.3


@dataclass
class Plan:
    """Everything the engine decides BEFORE acting (model-based)."""
    i0: int
    T0: np.ndarray
    searches: dict           # duration_min -> SearchResult
    envelope: dict           # duration_min -> max feasible kW
    plant_data: SimulationData
    plant_params: ThermalParams
    base_plant: object
    base_load: object
    enabled: np.ndarray
    baseline_peak_model_kw: float


@dataclass
class Assessment:
    # inputs
    spec_name: str = ""
    weather: str = ""
    occupancy_level: str = ""
    start_hour: float = 0.0
    duration_min: int = 0
    requested_kw: float = 0.0
    # sensed state
    state: dict = field(default_factory=dict)
    # decision
    table: pd.DataFrame | None = None
    best: dict = field(default_factory=dict)
    status: str = ""
    available_kw: float = 0.0          # max feasible reduction at the requested duration (corrected)
    feasible_kw: float = 0.0           # recommended action's predicted reduction, capped at request
    shortfall_kw: float = 0.0
    contrib_hvac_kw: float = 0.0
    contrib_light_kw: float = 0.0
    safe_duration_min: int = 0          # longest duration at which the delivered kW stays feasible
    safe_duration_requested_min: int = 0
    envelope: dict = field(default_factory=dict)
    upper_bound_kw: float = 0.0
    comfort_risk: str = ""
    confidence: str = ""
    reduction_range: tuple = (0.0, 0.0)
    worst_margin_c: float = 0.0
    zone_scale: dict = field(default_factory=dict)
    reject_counts: dict = field(default_factory=dict)
    limiting_reason: str = ""
    # actual (simulated plant) result
    time: pd.DatetimeIndex | None = None
    baseline_total: np.ndarray | None = None
    proposed_total: np.ndarray | None = None
    baseline_T: np.ndarray | None = None
    proposed_T: np.ndarray | None = None
    proposed_hvac: np.ndarray | None = None
    proposed_light: np.ndarray | None = None
    baseline_hvac: np.ndarray | None = None
    baseline_light: np.ndarray | None = None
    zone_names: list = field(default_factory=list)
    i0: int = 0
    n_event: int = 0
    n_recovery: int = 0
    actual: dict = field(default_factory=dict)
    kpis: dict = field(default_factory=dict)
    verify: dict = field(default_factory=dict)
    updated_available_kw: float = 0.0
    trace: list = field(default_factory=list)
    mismatch: dict = field(default_factory=dict)


# ----------------------------------------------------------------------------- planning

def _plan(data: SimulationData, start_hour: float, duration_min: int, requested_kw: float,
          mismatch: dict, full_envelope: bool = True) -> Plan:
    n, dt = data.n_steps, data.dt_h
    i0 = data.index_at(start_hour)
    event = DemandResponseEvent(i0, duration_min, requested_kw)
    if event.end_idx + RECOVERY_MIN // 5 > n:
        raise ValueError("event + recovery window must finish before midnight")
    model_params = ThermalParams.from_spec(data.spec)
    plant_params = model_params.perturbed(mismatch["ua"], mismatch["c"])
    plant_data = replace(data, q_solar_kw=data.q_solar_kw * mismatch["solar"])
    base_plant = run_baseline(plant_data, plant_params)
    base_load = electrical_load(plant_data, base_plant.q_hvac_th)
    model_base = run_baseline(data, model_params)
    model_peak = float(electrical_load(data, model_base.q_hvac_th).total_kw.max())
    enabled = hvac_schedule(n, dt)
    T0 = base_plant.T_series[i0]                       # SENSE: measured temperatures
    durations = sorted(set(range(5, MAX_EVENT_MIN + 1, 5)) | {duration_min}) if full_envelope else [duration_min]
    searches = {d: search(data, i0, T0, model_params, d, requested_kw, enabled, model_peak)
                for d in durations}
    envelope = {d: max_feasible_kw(searches[d]) for d in durations if d <= MAX_EVENT_MIN}
    return Plan(i0, T0, searches, envelope, plant_data, plant_params, base_plant, base_load,
                enabled, model_peak)


def _longest_duration(envelope: dict, kw: float) -> int:
    ok = [d for d, v in envelope.items() if v >= kw * FULL_FRACTION and kw > 0]
    return max(ok) if ok else 0


def _uncertainty(plan: Plan, data, res: SearchResult) -> tuple:
    """Re-simulate the chosen action with perturbed model corners -> reduction range + worst margin."""
    cand = res.cands.candidates[res.best_idx]
    base_params = ThermalParams.from_spec(data.spec)
    reds, margins = [], []
    for ua, c, sol in [(1.0, 1.0, 1.0)] + UNCERTAINTY_CORNERS:
        p = base_params.perturbed(ua, c)
        ctx = make_context(data, plan.i0, plan.T0, p, res.n_event + RECOVERY_MIN // 5, plan.enabled, sol)
        base = simulate_batch(ctx, np.ones((1, data.spec.n_zones)), np.zeros(1), res.n_event)
        sim = simulate_batch(ctx, np.array([cand.scale]), np.array([cand.light_cut]), res.n_event)
        ev = evaluate(ctx, sim, base, res.n_event)
        reds.append(float(ev["reduction_kw"][0]))
        margins.append(float(ev["min_margin_c"][0]))
    return min(reds), max(reds), min(margins)


def _risk(margin_c: float) -> str:
    return "Low" if margin_c >= RISK_LOW_C else ("Medium" if margin_c >= RISK_MED_C else "High")


# ----------------------------------------------------------------------------- acting

def _run_actual(plan: Plan, cand, n_event: int):
    """ACT: apply the chosen action to the PLANT from the event start to end of day."""
    pd_, i0, z = plan.plant_data, plan.i0, plan.plant_data.spec.n_zones
    n = pd_.n_steps - i0
    scale = np.ones((n, z))
    scale[:n_event] = cand.scale
    q_int = pd_.q_internal_kw[i0:].copy()
    q_int[:n_event] -= cand.light_cut * pd_.lighting_kw[i0:i0 + n_event]
    traj = run_closed_loop(plan.T0, pd_.t_out_c[i0:], q_int, pd_.q_solar_kw[i0:], plan.enabled[i0:],
                           pd_.hvac_cap_th_kw, plan.plant_params, pd_.dt_h, scale=scale)
    hvac = traj.q_hvac_th.sum(axis=1) / cop(pd_.t_out_c[i0:], pd_.spec.hvac_cop)
    light = pd_.lighting_kw[i0:].sum(axis=1).copy()
    light[:n_event] *= (1 - cand.light_cut)
    return traj, hvac, light


def assess(data: SimulationData, start_hour: float, duration_min: int, requested_kw: float,
           mismatch: dict | None = None, memory_correction: float = 1.0) -> Assessment:
    mismatch = mismatch or PLANT_MISMATCH
    plan = _plan(data, start_hour, duration_min, requested_kw, mismatch)
    res = plan.searches[duration_min]
    i0, n_event, dt = plan.i0, res.n_event, data.dt_h
    best = res.table.loc[res.best_idx]
    cand = res.cands.candidates[res.best_idx]
    a = Assessment(spec_name=data.spec.name, weather=data.weather, occupancy_level=data.occupancy_level,
                   start_hour=start_hour, duration_min=duration_min, requested_kw=requested_kw,
                   mismatch=mismatch, zone_names=data.spec.zone_names, i0=i0, n_event=n_event,
                   n_recovery=RECOVERY_MIN // 5)

    # --- SENSE
    pdta, base_load = plan.plant_data, plan.base_load
    occ_b = float(data.building_occupancy()[i0])
    head = COMFORT_BAND_C[1] - plan.T0
    j = int(np.argmin(head))
    a.state = {
        "occupancy": occ_b, "t_out_c": float(data.t_out_c[i0]), "current_load_kw": float(base_load.total_kw[i0]),
        "hvac_kw": float(base_load.hvac_kw[i0]), "lighting_kw": float(base_load.lighting_kw[i0]),
        "base_kw": float(base_load.base_kw[i0]), "zone_T": plan.T0.copy(), "headroom_c": head,
        "tightest_zone": data.spec.zone_names[j], "tightest_headroom_c": float(head[j]),
        "minutes_to_limit": res.minutes_to_limit.copy(),
        "clock": f"{data.time[i0]:%H:%M}",
    }

    # --- PREDICT / GENERATE / CONSTRAIN / EVALUATE / DECIDE (already done in search)
    tbl = res.table
    a.table = tbl
    a.best = best.to_dict()
    a.envelope = plan.envelope
    a.upper_bound_kw = res.upper_bound_kw
    a.reject_counts = {k: int(v) for k, v in
                       tbl.loc[~tbl["feasible"], "rejected_by"].str.split(", ").explode().value_counts().items()}
    a.available_kw = max_feasible_kw(res) * memory_correction
    pred_red = float(best["reduction_kw"])
    a.feasible_kw = min(pred_red, requested_kw) if best["action"] != "No action (baseline)" else 0.0
    a.shortfall_kw = max(0.0, requested_kw - a.feasible_kw)
    ratio = a.feasible_kw / requested_kw
    a.status = "full" if ratio >= FULL_FRACTION else ("infeasible" if ratio < INFEASIBLE_FRACTION else "partial")
    tot = max(float(best["hvac_kw"] + best["light_kw"]), 1e-9)
    a.contrib_hvac_kw = a.feasible_kw * float(best["hvac_kw"]) / tot
    a.contrib_light_kw = a.feasible_kw * float(best["light_kw"]) / tot
    a.safe_duration_requested_min = _longest_duration(plan.envelope, requested_kw)
    a.safe_duration_min = _longest_duration(plan.envelope, a.feasible_kw)
    a.zone_scale = dict(zip(data.spec.zone_names, cand.scale))
    lo, hi, worst = _uncertainty(plan, data, res)
    a.reduction_range = (lo, hi)
    a.worst_margin_c = worst
    a.comfort_risk = _risk(min(worst, float(best["min_margin_c"]))) if a.feasible_kw > 0 else "Low"
    spread = (hi - lo) / max(abs(pred_red), 1.0)
    a.confidence = "High" if spread < 0.10 and worst >= 0 else ("Medium" if spread < 0.25 and worst >= 0 else "Low")
    a.limiting_reason = _limiting_reason(a, res)

    # --- ACT
    traj, hvac_p, light_p = _run_actual(plan, cand, n_event)
    n = data.n_steps
    prop_total = base_load.total_kw.copy()
    prop_hvac, prop_light = base_load.hvac_kw.copy(), base_load.lighting_kw.copy()
    prop_total[i0:] = hvac_p + light_p + base_load.base_kw[i0:]
    prop_hvac[i0:], prop_light[i0:] = hvac_p, light_p
    prop_T = plan.base_plant.T_series.copy()
    prop_T[i0:] = traj.T_series
    a.time = data.time
    a.baseline_total, a.proposed_total = base_load.total_kw, prop_total
    a.baseline_hvac, a.baseline_light = base_load.hvac_kw, base_load.lighting_kw
    a.proposed_hvac, a.proposed_light = prop_hvac, prop_light
    a.baseline_T, a.proposed_T = plan.base_plant.T_series, prop_T

    # --- VERIFY
    ev = slice(i0, i0 + n_event)
    red_series = base_load.total_kw[ev] - prop_total[ev]
    actual_red = float(red_series.mean())
    reb = rebound_metrics(base_load.total_kw[i0:], prop_total[i0:], n_event, RECOVERY_MIN // 5, dt)
    cv_b = comfort_violation_minutes(plan.base_plant.T_series, data.occupancy, dt)
    cv_p = comfort_violation_minutes(prop_T, data.occupancy, dt)
    window = slice(i0, i0 + n_event + RECOVERY_MIN // 5)
    a.actual = {
        "reduction_kw": actual_red,
        "hvac_kw": float((base_load.hvac_kw[ev] - prop_hvac[ev]).mean()),
        "light_kw": float((base_load.lighting_kw[ev] - prop_light[ev]).mean()),
        "rebound_kw": float(reb["rebound_peak_kw"]), "rebound_kwh": float(reb["rebound_kwh"]),
        "rebound_min": float(reb["rebound_minutes"]),
        "delivered_kw_min": float(red_series.sum() * dt * 60),
        "min_margin_c": float(np.where(data.occupancy[window] > 0.02,
                                       np.minimum(COMFORT_BAND_C[1] - prop_T[window], prop_T[window] - COMFORT_BAND_C[0]),
                                       np.inf).min()),
    }
    err = (actual_red - pred_red) / max(abs(pred_red), 1.0) if a.feasible_kw > 0 else 0.0
    a.verify = {"predicted_kw": pred_red, "actual_kw": actual_red, "error_pct": 100 * err,
                "predicted_rebound_kw": float(best["rebound_kw"]), "actual_rebound_kw": a.actual["rebound_kw"]}

    # --- LEARN: bias correction of the flexibility estimate (not ML)
    corr = float(np.clip(actual_red / pred_red, 0.7, 1.3)) if pred_red > 1.0 else 1.0
    a.updated_available_kw = max_feasible_kw(res) * memory_correction * corr
    a.verify["correction_factor"] = corr

    # --- KPIs baseline vs proposed (all from simulation)
    area = sum(z.area_m2 for z in data.spec.zones)
    eb, ep = energy_kwh(base_load.total_kw, dt), energy_kwh(prop_total, dt)
    pb, ib = peak_kw(base_load.total_kw)
    pp, ip = peak_kw(prop_total)
    wk = slice(i0, i0 + n_event + RECOVERY_MIN // 5)
    a.kpis = {
        "Total energy (kWh)": (eb, ep),
        "Energy intensity (kWh/m²·day)": (eb / area, ep / area),
        "Daily peak demand (kW)": (pb, pp),
        "Peak in event + recovery window (kW)": (float(base_load.total_kw[wk].max()), float(prop_total[wk].max())),
        "Mean load during event (kW)": (float(base_load.total_kw[ev].mean()), float(prop_total[ev].mean())),
        "Comfort violations (min, building)": (cv_b["building_minutes"], cv_p["building_minutes"]),
        "Comfort violations (zone-min)": (cv_b["zone_minutes"], cv_p["zone_minutes"]),
    }
    a.trace = _trace(a, res)
    return a


def _limiting_reason(a: Assessment, res: SearchResult) -> str:
    if a.status == "full":
        return ""
    t = res.table
    if res.requested_kw > res.upper_bound_kw:
        return (f"The request exceeds the total controllable load (HVAC + dimmable lighting = "
                f"{res.upper_bound_kw:.0f} kW).")
    cand_ok = t[(t["reduction_kw"] >= res.requested_kw * FULL_FRACTION) & (~t["feasible"])
                & ~t["rejected_by"].str.contains("lighting minimum|essential|duration|equipment")]
    if len(cand_ok):
        row = cand_ok.sort_values("reduction_kw").iloc[0]
        return f"Meeting {res.requested_kw:.0f} kW would require '{row['action']}', rejected: {row['reason']}."
    return "No candidate that meets the request passes all constraints."


def _trace(a: Assessment, res: SearchResult) -> list:
    s = a.state
    n_total, n_rej = len(a.table), int((~a.table["feasible"]).sum())
    b = a.best
    return [
        ("1 SENSE", f"{s['clock']} | load {s['current_load_kw']:.0f} kW | occupancy {s['occupancy']:.0%} | "
                    f"outdoor {s['t_out_c']:.1f} °C | tightest zone {s['tightest_zone']} at "
                    f"{s['zone_T'][a.zone_names.index(s['tightest_zone'])]:.1f} °C"),
        ("2 PREDICT", f"Baseline thermostat forecast for {res.duration_min} min event + {RECOVERY_MIN} min recovery "
                      f"(first-order RC model)."),
        ("3 GENERATE", f"{n_total} candidate actions (HVAC levels x strategies x lighting)."),
        ("4 CONSTRAIN", f"{n_rej} rejected" + (f" ({', '.join(f'{k}: {v}' for k, v in a.reject_counts.items())})"
                                              if a.reject_counts else "") + f"; {n_total - n_rej} feasible."),
        ("5 EVALUATE", f"Max feasible reduction at {res.duration_min} min: {max_feasible_kw(res):.0f} kW."),
        ("6 DECIDE", f"Chosen: {b['action']} -> predicted {b['reduction_kw']:.0f} kW, rebound {b['rebound_kw']:.0f} kW."),
        ("7 ACT", f"Applied to simulated building from {s['clock']}."),
        ("8 VERIFY", f"Actual {a.verify['actual_kw']:.0f} kW vs predicted {a.verify['predicted_kw']:.0f} kW "
                     f"({a.verify['error_pct']:+.1f} %)."),
        ("9 LEARN", f"Correction factor {a.verify['correction_factor']:.2f}; updated available flexibility "
                    f"{a.updated_available_kw:.0f} kW."),
    ]


# ----------------------------------------------------------------------------- sensitivity

def flexibility_timeline(data: SimulationData, duration_min: int, requested_kw: float,
                         mismatch: dict | None = None, hours=None) -> pd.DataFrame:
    """Available flexibility vs building load across the day (same event length, every start time)."""
    mismatch = mismatch or PLANT_MISMATCH
    hours = np.arange(7.0, 19.01, 0.5) if hours is None else hours
    rows = []
    for h in hours:
        plan = _plan(data, float(h), duration_min, requested_kw, mismatch, full_envelope=False)
        res = plan.searches[duration_min]
        rows.append({"hour": float(h), "load_kw": float(plan.base_load.total_kw[plan.i0]),
                     "available_kw": max_feasible_kw(res),
                     "occupancy": float(data.building_occupancy()[plan.i0]),
                     "headroom_c": float((COMFORT_BAND_C[1] - plan.T0).min())})
    df = pd.DataFrame(rows)
    df["share_pct"] = 100 * df["available_kw"] / df["load_kw"]
    return df


def sensitivity(builder, weather: str, occupancy: str, start_hour: float, duration_min: int,
                requested_kw: float, mismatch: dict | None = None) -> pd.DataFrame:
    """Same event under other occupancy / weather settings (planning only, no actuation)."""
    mismatch = mismatch or PLANT_MISMATCH
    rows = []
    settings = [("Occupancy", o, weather, o) for o in ("low", "normal", "high")] + \
               [("Weather", w, w, occupancy) for w in ("mild", "hot")]
    for var, label, w, o in settings:
        data = builder(w, o)
        plan = _plan(data, start_hour, duration_min, requested_kw, mismatch)
        res = plan.searches[duration_min]
        best = res.table.loc[res.best_idx]
        rows.append({
            "Varied": var, "Setting": label,
            "Building load (kW)": float(plan.base_load.total_kw[plan.i0]),
            f"Available flexibility @ {duration_min} min (kW)": max_feasible_kw(res),
            "Safe duration for request (min)": _longest_duration(plan.envelope, requested_kw),
            "Tightest zone headroom (°C)": float((COMFORT_BAND_C[1] - plan.T0).min()),
            "Rebound of chosen action (kW)": float(best["rebound_kw"]),
        })
    return pd.DataFrame(rows)
