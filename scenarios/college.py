"""Scenario A — College building (primary demo). SIMULATION parameters.

Five zones. Occupancy profiles are shaped so that (normal level):
  13:30 -> ~70 % building occupancy, 14:00-14:20 -> large lecture fills the hall (95 %).
Demo timeline: event request at 14:20 for 20 minutes (ends 14:40).
"""
from __future__ import annotations

from data.synthetic_building import BuildingSpec, ZoneSpec, generate_building_data
from scenarios.base import ScenarioDef

DEMO_EVENT_START_H = 14 + 20 / 60
DEMO_EVENT_DURATION_MIN = 20
DEMO_EVENT_REQUEST_KW = 50.0

_HALL = ((0, 0), (8.5, 0), (9, .7), (10.5, .8), (12, .75), (12.75, .3), (13.25, .4),
         (13.5, .5), (14, .5), (14.25, .95), (16, .95), (16.5, .4), (17.5, .05),
         (18.5, 0), (24, 0))
_CLASS_A = ((0, 0), (7.5, 0), (8, .05), (9, .8), (12, .85), (12.75, .5), (13.5, .85), (14.25, .92),
            (16.5, .9), (17, .35), (18, .05), (19, 0), (24, 0))
_CLASS_B = ((0, 0), (7.5, 0), (8, .05), (9.25, .75), (12, .8), (12.75, .45), (13.5, .85), (14.25, .92),
            (16.5, .85), (17.25, .3), (18.25, .05), (19, 0), (24, 0))
_LAB = ((0, 0), (8, 0), (8.5, .05), (9.5, .7), (12.5, .75), (13, .6), (13.5, .8), (14.25, .9),
        (17, .8), (18, .4), (19, .1), (19.5, 0), (24, 0))
_ADMIN = ((0, 0), (7, 0), (8, .1), (9, .7), (12, .75), (13, .6), (14, .75), (17, .7), (18, .3),
          (19, .05), (20, 0), (24, 0))

COLLEGE = BuildingSpec(
    name="College building (SIMULATED)",
    zones=(
        ZoneSpec("Lecture Hall", 900, 450, 22, 3.5, 10, 10, 12, 150, _HALL),
        ZoneSpec("Classrooms A", 700, 280, 17, 3.0, 12, 8, 12, 120, _CLASS_A),
        ZoneSpec("Classrooms B", 700, 280, 17, 3.0, 16, 8, 12, 120, _CLASS_B),
        ZoneSpec("Computer Labs", 500, 150, 12, 2.2, 6, 35, 12, 110, _LAB),
        ZoneSpec("Admin & Library", 800, 200, 20, 3.2, 8, 12, 10, 100, _ADMIN),
    ),
    hvac_cop=2.8,
    base_day_kw=70.0,
    base_night_kw=20.0,
)


def college_data(weather: str = "hot", occupancy_level: str = "normal"):
    return generate_building_data(COLLEGE, weather=weather, occupancy_level=occupancy_level)


SCENARIO = ScenarioDef(
    key="College", spec=COLLEGE, build=college_data,
    default_start_hour=DEMO_EVENT_START_H, default_duration_min=DEMO_EVENT_DURATION_MIN,
    default_request_kw=DEMO_EVENT_REQUEST_KW, default_weather="hot", default_occupancy="normal",
    timeline=(("13:30", "~70% occupancy, hot conditions"),
              ("14:00", "Large lecture starts; hall occupancy rises toward 95%"),
              ("14:20", "Grid/facility request arrives"),
              ("14:40", "Event ends; recovery/rebound checked, estimate updated")),
)
