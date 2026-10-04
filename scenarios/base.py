from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from data.synthetic_building import BuildingSpec


@dataclass(frozen=True)
class ScenarioDef:
    key: str
    spec: BuildingSpec
    build: Callable                 # (weather, occupancy_level) -> SimulationData
    default_start_hour: float
    default_duration_min: int
    default_request_kw: float
    default_weather: str
    default_occupancy: str
    timeline: tuple                 # ((clock, text), ...) demo story
