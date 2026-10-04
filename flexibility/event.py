"""Phase 5 — Demand-response (grid/facility) event. SIMULATED request, no real DISCOM API."""
from __future__ import annotations

from dataclasses import dataclass

DT_MIN = 5
MAX_EVENT_MIN = 60     # prototype operating constraint: longest curtailment allowed
RECOVERY_MIN = 60      # window after the event in which rebound is measured


@dataclass(frozen=True)
class DemandResponseEvent:
    start_idx: int
    duration_min: int
    requested_kw: float

    def __post_init__(self):
        if self.duration_min <= 0 or self.duration_min % DT_MIN:
            raise ValueError("duration_min must be a positive multiple of 5")
        if self.requested_kw <= 0:
            raise ValueError("requested_kw must be > 0")
        if self.start_idx < 0:
            raise ValueError("start_idx must be >= 0")

    @property
    def n_steps(self) -> int:
        return self.duration_min // DT_MIN

    @property
    def end_idx(self) -> int:
        return self.start_idx + self.n_steps
