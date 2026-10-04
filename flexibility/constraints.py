"""Phase 7 — Constraint filter. Every violation returns a human-readable reason.

Constraints (prototype assumptions):
  1. essential loads (base load) are never curtailed
  2. lighting never below LIGHT_MIN_LEVEL of normal
  3. HVAC override within [0, 1] and output within equipment capacity
  4. event duration <= MAX_EVENT_MIN
  5. comfort: occupied zones stay inside the band minus a planning margin
  6. no new daily peak above baseline peak (+ small tolerance) during recovery
"""
from __future__ import annotations

import numpy as np

from data.synthetic_building import COMFORT_BAND_C
from flexibility.candidate_actions import LIGHT_MIN_LEVEL
from flexibility.event import MAX_EVENT_MIN

COMFORT_PLANNING_MARGIN_C = 0.2   # keep predicted T this far inside the upper limit
PEAK_TOLERANCE = 0.10             # prototype assumption: recovery may exceed baseline day peak by 10 %
OCC_THRESHOLD = 0.02

CATEGORY = {"essential": "essential load", "lighting": "lighting minimum", "equipment": "equipment limit",
            "duration": "max duration", "comfort": "comfort", "peak": "new peak"}


def static_violations(cand, duration_min: int) -> list:
    """Checks that do not need a simulation. Returns list of (category, message)."""
    v = []
    if cand.base_cut_kw > 0:
        v.append(("essential", f"interrupts essential load ({cand.base_cut_kw:.0f} kW)"))
    if 1.0 - cand.light_cut < LIGHT_MIN_LEVEL - 1e-9:
        v.append(("lighting", f"lighting {1 - cand.light_cut:.0%} is below the {LIGHT_MIN_LEVEL:.0%} minimum"))
    if min(cand.scale) < -1e-9 or max(cand.scale) > 1 + 1e-9:
        v.append(("equipment", "HVAC override outside 0-100 %"))
    if duration_min > MAX_EVENT_MIN:
        v.append(("duration", f"event {duration_min} min exceeds max {MAX_EVENT_MIN} min"))
    return v


def trajectory_violations(T, occupancy, q_th, cap_kw, total_kw, baseline_peak_kw, zone_names, times,
                          band=COMFORT_BAND_C) -> list:
    """T (h,z) predicted temperatures after each step; occupancy (h,z); q_th (h,z)."""
    lo, hi = band
    v = []
    occ = occupancy > OCC_THRESHOLD
    limit = hi - COMFORT_PLANNING_MARGIN_C
    hot = occ & (T > limit + 1e-9)
    if hot.any():
        k, j = np.unravel_index(np.argmax(np.where(hot, T, -np.inf)), T.shape)
        v.append(("comfort", f"{zone_names[j]} reaches {T[k, j]:.1f} °C at {times[k]} "
                             f"(planning limit {limit:.1f} °C)"))
    cold = occ & (T < lo - 1e-9)
    if cold.any():
        k, j = np.unravel_index(np.argmax(np.where(cold, lo - T, -np.inf)), T.shape)
        v.append(("comfort", f"{zone_names[j]} drops to {T[k, j]:.1f} °C at {times[k]}"))
    if (q_th > cap_kw[None, :] + 1e-6).any():
        v.append(("equipment", "HVAC output above equipment capacity"))
    if total_kw.max() > baseline_peak_kw * (1 + PEAK_TOLERANCE):
        v.append(("peak", f"recovery creates a new peak {total_kw.max():.0f} kW "
                          f"(baseline day peak {baseline_peak_kw:.0f} kW)"))
    return v
