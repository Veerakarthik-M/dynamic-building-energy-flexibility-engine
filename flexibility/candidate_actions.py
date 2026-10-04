"""Phase 6 — Candidate flexibility actions (prototype assumptions, not field commands).

HVAC lever: an override multiplier on what the thermostat would command
(1.0 = normal). Two strategies per level:
  * uniform        : same multiplier in every zone
  * headroom-first : same total cut, concentrated in zones with the most thermal
                     headroom (longest time to reach the comfort limit)
Lighting lever: fraction of lighting power shed. Anything beyond the allowed flexible
portion is generated on purpose so the constraint filter visibly rejects it.
EV charging: NOT implemented (OPTIONAL, only after the core demo is stable).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

HVAC_LEVELS = [round(x, 2) for x in np.arange(1.0, -0.001, -0.1)]
LIGHT_CUTS = [0.0, 0.15, 0.30, 0.50]
LIGHT_MIN_LEVEL = 0.70   # prototype assumption: lighting never below 70 % of normal


@dataclass(frozen=True)
class Candidate:
    strategy: str
    hvac_level: float
    light_cut: float
    scale: tuple             # per-zone HVAC multiplier
    base_cut_kw: float = 0.0  # essential load curtailment (must stay 0)

    @property
    def label(self) -> str:
        if self.hvac_level >= 1.0 and self.light_cut == 0:
            return "No action (baseline)"
        return f"HVAC {self.hvac_level:.0%} ({self.strategy}) + lights -{self.light_cut:.0%}"


@dataclass
class CandidateSet:
    candidates: list

    @property
    def scales(self) -> np.ndarray:
        return np.array([c.scale for c in self.candidates], dtype=float)

    @property
    def light_cuts(self) -> np.ndarray:
        return np.array([c.light_cut for c in self.candidates], dtype=float)

    def __len__(self):
        return len(self.candidates)


def _headroom_first_scale(level: float, minutes_to_limit: np.ndarray) -> np.ndarray:
    z = len(minutes_to_limit)
    remaining = (1.0 - level) * z
    scale = np.ones(z)
    for j in np.argsort(-minutes_to_limit):
        cut = min(1.0, remaining)
        scale[j] = 1.0 - cut
        remaining -= cut
    return scale


def generate_candidates(minutes_to_limit: np.ndarray) -> CandidateSet:
    z = len(minutes_to_limit)
    out, seen = [], set()
    for level in HVAC_LEVELS:
        for strat in ("uniform", "headroom-first"):
            scale = np.full(z, level) if strat == "uniform" else _headroom_first_scale(level, minutes_to_limit)
            for cut in LIGHT_CUTS:
                key = (tuple(np.round(scale, 3)), cut)
                if key in seen:
                    continue
                seen.add(key)
                out.append(Candidate(strat, level, cut, tuple(float(s) for s in scale)))
    # no-action candidate must be index 0
    out.sort(key=lambda c: not (c.hvac_level >= 1.0 and c.light_cut == 0))
    return CandidateSet(out)
