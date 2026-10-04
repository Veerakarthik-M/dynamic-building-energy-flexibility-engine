"""Phase 10 — Rebound (recovery) metrics.

Rebound = extra demand vs baseline in the window AFTER the event ends, caused by
the building recovering (thermostat pulling temperature back). Works on 1-D (h,)
or batched (C, h) series.
"""
from __future__ import annotations

import numpy as np


def rebound_metrics(baseline_kw, proposed_kw, n_event: int, recovery_steps: int, dt_h: float) -> dict:
    b = np.asarray(baseline_kw, dtype=float)
    p = np.asarray(proposed_kw, dtype=float)
    sl = slice(n_event, n_event + max(recovery_steps, 0))
    excess = np.maximum(p[..., sl] - b[..., sl], 0.0)
    if excess.shape[-1] == 0:
        zero = np.zeros(p.shape[:-1])
        return {"rebound_peak_kw": zero, "rebound_kwh": zero, "rebound_minutes": zero}
    return {
        "rebound_peak_kw": excess.max(axis=-1),
        "rebound_kwh": excess.sum(axis=-1) * dt_h,
        "rebound_minutes": (excess > 0.5).sum(axis=-1) * dt_h * 60.0,
    }
