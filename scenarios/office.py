"""Scenario B — Office building. SIMULATION parameters (prototype assumptions).

Purpose: prove that flexibility is DYNAMIC. Same building, different state at different times:
  11:00 ~40 % occupancy, mild | 12:00 meeting rooms fill | 13:00 weather/solar change | 14:00 request.
"""
from __future__ import annotations

from data.synthetic_building import BuildingSpec, WeatherShift, ZoneSpec, generate_building_data
from scenarios.base import ScenarioDef

# 13:00-13:45: warmer, clearer afternoon (+3 degC, solar x1.6)
OFFICE_SHIFT = WeatherShift(start_h=13.0, end_h=13.75, delta_t_c=3.0, solar_mult_factor=1.6)

_OPEN_E = ((0, 0), (8.5, 0), (9, .2), (10, .4), (11, .5), (12, .45), (13, .4), (14, .5), (15, .55),
           (17, .4), (18, .1), (19, 0), (24, 0))
_OPEN_W = ((0, 0), (8.5, 0), (9, .2), (10, .4), (11, .5), (12, .45), (13, .45), (14, .55), (15, .6),
           (17, .4), (18, .1), (19, 0), (24, 0))
_MEET = ((0, 0), (9, 0), (9.5, .1), (11, .25), (12, .85), (13, .9), (13.5, .6), (14, .75), (15, .85),
         (16, .5), (17, .1), (18, 0), (24, 0))
_CABIN = ((0, 0), (8.5, 0), (9, .3), (11, .5), (13, .4), (15, .5), (17, .4), (18, .1), (19, 0), (24, 0))
_IT = ((0, 0), (8, 0), (9, .6), (11, .6), (17, .6), (18, .3), (19, 0), (24, 0))

OFFICE = BuildingSpec(
    name="Office building (SIMULATED)",
    zones=(
        ZoneSpec("Open Plan East", 900, 110, 18, 3.0, 14, 15, 10, 110, _OPEN_E),
        ZoneSpec("Open Plan West", 900, 110, 18, 3.0, 20, 15, 10, 120, _OPEN_W),
        ZoneSpec("Meeting Rooms", 400, 120, 8, 1.5, 5, 8, 12, 70, _MEET),
        ZoneSpec("Cabins", 300, 30, 6, 1.4, 6, 12, 12, 45, _CABIN),
        ZoneSpec("IT & Support", 300, 20, 5, 1.2, 2, 30, 8, 40, _IT),
    ),
    hvac_cop=3.0,
    base_day_kw=45.0,
    base_night_kw=12.0,
)


def office_data(weather: str = "mild", occupancy_level: str = "normal"):
    return generate_building_data(OFFICE, weather=weather, occupancy_level=occupancy_level,
                                  shifts=(OFFICE_SHIFT,))


SCENARIO = ScenarioDef(
    key="Office", spec=OFFICE, build=office_data,
    default_start_hour=14.0, default_duration_min=20, default_request_kw=20.0,
    default_weather="mild", default_occupancy="normal",
    timeline=(("11:00", "~40% occupancy, mild conditions"),
              ("12:00", "Meeting rooms fill"),
              ("13:00", "Weather/solar conditions change (warmer, sunnier)"),
              ("14:00", "Grid/facility request arrives"),
              ("14:20", "Event ends; recovery/rebound measured")),
)
