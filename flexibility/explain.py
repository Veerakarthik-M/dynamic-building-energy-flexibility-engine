"""Explanations are generated from computed numbers — never hard-coded claims."""
from __future__ import annotations

import numpy as np

from data.synthetic_building import COMFORT_BAND_C


def explain(a, sens=None) -> list:
    """Return a list of (kind, text). kind in {headline, state, why, action, rebound, verify}."""
    s, out = a.state, []
    req, feas = a.requested_kw, a.feasible_kw
    if a.status == "full":
        out.append(("headline", f"Request of {req:.0f} kW for {a.duration_min} min is fully feasible "
                                f"(predicted {feas:.0f} kW)."))
    elif a.status == "partial":
        out.append(("headline", f"Request of {req:.0f} kW is only partially feasible: "
                                f"{feas:.0f} kW deliverable, shortfall {a.shortfall_kw:.0f} kW."))
    else:
        out.append(("headline", f"Request of {req:.0f} kW is not feasible for {a.duration_min} min: only "
                                f"{feas:.0f} kW can be delivered safely."))

    out.append(("state", f"Building state at {s['clock']}: occupancy {s['occupancy']:.0%}, outdoor "
                         f"{s['t_out_c']:.1f} °C, load {s['current_load_kw']:.0f} kW of which HVAC "
                         f"{s['hvac_kw']:.0f} kW. Tightest zone: {s['tightest_zone']} with only "
                         f"{s['tightest_headroom_c']:.1f} °C below the {COMFORT_BAND_C[1]:.0f} °C limit "
                         f"(about {float(np.min(s['minutes_to_limit'])):.0f} min if its HVAC stopped)."))

    if a.status != "full" and a.limiting_reason:
        out.append(("why", f"Why not more: {a.limiting_reason}"))
    if a.status != "full":
        sd = a.safe_duration_requested_min
        out.append(("why", (f"The requested {req:.0f} kW could be sustained for at most {sd} min "
                            f"(flexibility envelope)." if sd > 0 else
                            f"{req:.0f} kW cannot be sustained even for 5 min from the current state; "
                            f"a smaller request or shorter event is needed.")))
    if a.reject_counts:
        top = ", ".join(f"{k} ({v})" for k, v in sorted(a.reject_counts.items(), key=lambda kv: -kv[1]))
        out.append(("why", f"Constraint filter rejected candidates because of: {top}."))

    cut = {z: 1 - v for z, v in a.zone_scale.items() if 1 - v > 0.005}
    lc = a.best["light_cut"]
    parts = []
    if cut:
        parts.append("HVAC cut in " + ", ".join(f"{z} ({c:.0%})" for z, c in cut.items()))
    if lc > 0:
        parts.append(f"lighting dimmed {lc:.0%}")
    out.append(("action", ("Chosen action: " + "; ".join(parts) + "." if parts else
                           "No safe curtailment found: staying on baseline control.")
                + " Selected because it meets the request with the lowest rebound and comfort risk, "
                  "not because it cuts the most."))

    ac = a.actual
    out.append(("rebound", f"Rebound: after the event the building must recover; HVAC demand ran up to "
                           f"{ac['rebound_kw']:.0f} kW above baseline for ~{ac['rebound_min']:.0f} min "
                           f"({ac['rebound_kwh']:.1f} kWh). Net energy over the window: "
                           f"{(a.proposed_total - a.baseline_total)[a.i0:a.i0 + a.n_event + a.n_recovery].sum() * (5 / 60):+.1f} kWh "
                           f"vs baseline."))
    v = a.verify
    out.append(("verify", f"Verification: predicted {v['predicted_kw']:.0f} kW, simulated actual "
                          f"{v['actual_kw']:.0f} kW ({v['error_pct']:+.1f} %). Estimate corrected by "
                          f"x{v['correction_factor']:.2f}. Model error is simulated (UA {a.mismatch['ua'] - 1:+.0%}, "
                          f"C {a.mismatch['c'] - 1:+.0%}, solar {a.mismatch['solar'] - 1:+.0%})."))

    if sens is not None and len(sens):
        col = [c for c in sens.columns if c.startswith("Available flexibility")][0]
        occ = sens[sens["Varied"] == "Occupancy"].set_index("Setting")
        wth = sens[sens["Varied"] == "Weather"].set_index("Setting")
        hd, ld = "Tightest zone headroom (°C)", "Building load (kW)"
        share = lambda df, k: 100 * df.loc[k, col] / df.loc[k, ld]
        out.append(("why", f"Dynamic, not fixed (same {a.duration_min}-min event): available flexibility is "
                           f"{occ.loc['low', col]:.0f} / {occ.loc['normal', col]:.0f} / {occ.loc['high', col]:.0f} kW at "
                           f"low / normal / high occupancy, i.e. {share(occ, 'low'):.1f}% / {share(occ, 'normal'):.1f}% / "
                           f"{share(occ, 'high'):.1f}% of load, while comfort headroom shrinks "
                           f"{occ.loc['low', hd]:.2f} / {occ.loc['normal', hd]:.2f} / {occ.loc['high', hd]:.2f} °C. "
                           f"By weather: {wth.loc['mild', col]:.0f} kW (mild) vs {wth.loc['hot', col]:.0f} kW (hot)."))
    return out
