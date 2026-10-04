"""Phase 1 — Synthetic building driver generator.

*** SIMULATION DATA — synthetic, NOT field measurements. ***
All parameters are prototype assumptions.

Generates the *drivers* of the simulation on a 5-minute grid for 24 h:
outdoor temperature, solar gain, zone occupancy, internal heat gain,
lighting demand and base (non-HVAC, non-lighting) load.

Indoor temperature and HVAC demand are NOT generated here: they are results
of the thermal model + controller (Phases 2-3).

Units: kW, kWh, degC, hours. Heat terms are kW thermal.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

SIMULATION_LABEL = "SIMULATION DATA — synthetic, not field measurements"

DT_MINUTES = 5
DT_HOURS = DT_MINUTES / 60.0
STEPS_PER_DAY = 24 * 60 // DT_MINUTES  # 288

# Prototype comfort assumption (NOT a universal standard).
COMFORT_BAND_C = (23.0, 26.0)
PERSON_SENSIBLE_KW = 0.075  # sensible heat per person (prototype assumption)

# Weather presets (prototype assumptions): daily mean/amplitude, peak at 15:00.
WEATHER_PRESETS = {
    "hot": {"mean_c": 34.0, "amp_c": 5.0, "solar_mult": 1.0},
    "mild": {"mean_c": 27.0, "amp_c": 4.0, "solar_mult": 0.7},
}
# Occupancy level multipliers (clipped to [0, 1] after scaling).
OCCUPANCY_LEVELS = {"low": 0.5, "normal": 1.0, "high": 1.15}


@dataclass(frozen=True)
class ZoneSpec:
    """One thermal zone (all values are prototype assumptions)."""
    name: str
    area_m2: float
    max_occupants: int
    c_kwh_per_k: float        # effective thermal capacity
    ua_kw_per_k: float        # envelope heat-transfer coefficient
    solar_peak_kw: float      # solar heat gain at clear-sky noon, hot-day
    equip_w_m2: float         # equipment heat/electric density at full use
    light_w_m2: float         # lighting power density at full use
    hvac_cap_th_kw: float     # max cooling delivered (thermal)
    occupancy_keypoints: tuple  # ((hour, fraction), ...) piecewise-linear


@dataclass(frozen=True)
class BuildingSpec:
    name: str
    zones: tuple
    hvac_cop: float           # constant system COP (prototype assumption)
    base_day_kw: float        # non-HVAC non-lighting load at full occupancy
    base_night_kw: float      # always-on essential load
    setpoint_c: float = 24.5

    @property
    def n_zones(self) -> int:
        return len(self.zones)

    @property
    def zone_names(self) -> list:
        return [z.name for z in self.zones]


@dataclass(frozen=True)
class WeatherShift:
    """Smooth persistent weather change between start_h and end_h (e.g. a front)."""
    start_h: float
    end_h: float
    delta_t_c: float = 0.0
    solar_mult_factor: float = 1.0


@dataclass
class SimulationData:
    """Container of generated drivers. Arrays are indexed [time] or [time, zone]."""
    spec: BuildingSpec
    weather: str
    occupancy_level: str
    time: pd.DatetimeIndex
    t_out_c: np.ndarray            # (n,)
    solar_factor: np.ndarray       # (n,) 0..~1 effective solar (incl. weather mult)
    occupancy: np.ndarray          # (n, z) fraction of max occupants
    q_solar_kw: np.ndarray         # (n, z)
    q_internal_kw: np.ndarray      # (n, z) people + equipment + lighting heat
    lighting_kw: np.ndarray        # (n, z) normal-operation lighting electrical
    base_load_kw: np.ndarray       # (n,)
    label: str = SIMULATION_LABEL
    dt_h: float = DT_HOURS

    @property
    def n_steps(self) -> int:
        return len(self.time)

    @property
    def hvac_cap_th_kw(self) -> np.ndarray:
        return np.array([z.hvac_cap_th_kw for z in self.spec.zones])

    def building_occupancy(self) -> np.ndarray:
        """Capacity-weighted building occupancy fraction (n,)."""
        w = np.array([z.max_occupants for z in self.spec.zones], dtype=float)
        return (self.occupancy * w).sum(axis=1) / w.sum()

    def index_at(self, hour: float) -> int:
        """Step index for a clock hour (e.g. 14.33 -> 14:20)."""
        return int(round(hour * 60 / DT_MINUTES))

    def to_frame(self) -> pd.DataFrame:
        df = pd.DataFrame(
            {
                "t_out_c": self.t_out_c,
                "solar_factor": self.solar_factor,
                "occupancy_building": self.building_occupancy(),
                "q_internal_total_kw": self.q_internal_kw.sum(axis=1),
                "q_solar_total_kw": self.q_solar_kw.sum(axis=1),
                "lighting_kw": self.lighting_kw.sum(axis=1),
                "base_load_kw": self.base_load_kw,
            },
            index=self.time,
        )
        for j, name in enumerate(self.spec.zone_names):
            df[f"occ_{name}"] = self.occupancy[:, j]
        df.attrs["label"] = self.label
        return df


def _smoothstep(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _hours_grid() -> np.ndarray:
    return np.arange(STEPS_PER_DAY) * DT_HOURS


def outdoor_temperature(hours: np.ndarray, weather: str, shifts=()) -> np.ndarray:
    p = WEATHER_PRESETS[weather]
    t = p["mean_c"] + p["amp_c"] * np.cos(2 * np.pi * (hours - 15.0) / 24.0)
    for s in shifts:
        t = t + s.delta_t_c * _smoothstep((hours - s.start_h) / (s.end_h - s.start_h))
    return t


def solar_factor(hours: np.ndarray, weather: str, shifts=()) -> np.ndarray:
    """Clear-sky bell 06:00-18:00 scaled by weather multiplier (and shifts)."""
    bell = np.where((hours > 6) & (hours < 18), np.sin(np.pi * (hours - 6) / 12), 0.0)
    mult = np.full_like(hours, WEATHER_PRESETS[weather]["solar_mult"])
    for s in shifts:
        w = _smoothstep((hours - s.start_h) / (s.end_h - s.start_h))
        mult = mult * (1 + (s.solar_mult_factor - 1) * w)
    return bell * mult


def zone_occupancy(zone: ZoneSpec, hours: np.ndarray, level: str) -> np.ndarray:
    hk, fk = zip(*zone.occupancy_keypoints)
    occ = np.interp(hours, hk, fk) * OCCUPANCY_LEVELS[level]
    return np.clip(occ, 0.0, 1.0)


def generate_building_data(
    spec: BuildingSpec,
    weather: str = "hot",
    occupancy_level: str = "normal",
    shifts=(),
) -> SimulationData:
    """Deterministic driver generation (no randomness)."""
    if weather not in WEATHER_PRESETS:
        raise ValueError(f"weather must be one of {list(WEATHER_PRESETS)}")
    if occupancy_level not in OCCUPANCY_LEVELS:
        raise ValueError(f"occupancy_level must be one of {list(OCCUPANCY_LEVELS)}")

    hours = _hours_grid()
    time = pd.date_range("2025-06-02 00:00", periods=STEPS_PER_DAY, freq=f"{DT_MINUTES}min")
    t_out = outdoor_temperature(hours, weather, shifts)
    sol = solar_factor(hours, weather, shifts)

    occ = np.column_stack([zone_occupancy(z, hours, occupancy_level) for z in spec.zones])
    area = np.array([z.area_m2 for z in spec.zones])
    max_occ = np.array([z.max_occupants for z in spec.zones], dtype=float)
    equip = np.array([z.equip_w_m2 for z in spec.zones])
    light = np.array([z.light_w_m2 for z in spec.zones])
    solar_peak = np.array([z.solar_peak_kw for z in spec.zones])

    # Lights follow occupancy: 5% security floor, saturate at 25% occupancy.
    light_frac = np.clip(0.05 + occ / 0.25, 0.05, 1.0)
    lighting_kw = light_frac * (light * area / 1000.0)
    equip_kw = (0.15 + 0.85 * occ) * (equip * area / 1000.0)  # 15% standby
    people_kw = occ * max_occ * PERSON_SENSIBLE_KW
    q_internal = people_kw + equip_kw + lighting_kw
    q_solar = sol[:, None] * solar_peak[None, :]

    w = max_occ / max_occ.sum()
    bld_occ = (occ * w).sum(axis=1)
    base = spec.base_night_kw + (spec.base_day_kw - spec.base_night_kw) * bld_occ

    return SimulationData(
        spec=spec, weather=weather, occupancy_level=occupancy_level, time=time,
        t_out_c=t_out, solar_factor=sol, occupancy=occ, q_solar_kw=q_solar,
        q_internal_kw=q_internal, lighting_kw=lighting_kw, base_load_kw=base,
    )
