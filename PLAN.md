# Dynamic Building Energy Flexibility Engine — Implementation Plan

> All data is **SIMULATION DATA**. All thermal/electrical parameters are **prototype assumptions**, not measurements.
> Comfort band 23–26 °C is a **prototype comfort assumption**.

## 1. Repository structure

```
yuva_yodha/
├── PLAN.md  README.md  requirements.txt  pytest.ini  app.py (Phase 12)
├── data/synthetic_building.py     # Phase 1  ZoneSpec/BuildingSpec + driver generator
├── scenarios/college.py           # Phase 1  college BuildingSpec + demo timeline
├── scenarios/office.py            # Phase 13
├── models/thermal_model.py        # Phase 2  first-order RC step/simulate/required-cooling
├── models/baseline_controller.py  # Phase 3  thermostat
├── models/load_model.py           # Phase 4  thermal kW -> electrical kW, building total
├── flexibility/event.py           # Phase 5  DemandResponseEvent
├── flexibility/candidate_actions.py  # Phase 6
├── flexibility/constraints.py     # Phase 7
├── flexibility/evaluator.py       # Phase 8
├── flexibility/optimizer.py       # Phase 9  (enumerate + score; no solver)
├── flexibility/rebound.py         # Phase 10
├── visualization/charts.py        # Phase 12
└── tests/                         # grows every phase
```

## 2. Data flow (one rolling decision)

```
SimulationData (drivers) ─► state at t0 (T per zone, HVAC level)
  ─► baseline forecast (thermostat, 30–60 min)           [SENSE, PREDICT]
  ─► candidate actions (HVAC level x lighting level)     [GENERATE]
  ─► simulate each with thermal model + load model       [PREDICT]
  ─► constraints (comfort, equipment, min lighting)      [CONSTRAIN]
  ─► score feasible (shortfall, comfort margin, rebound) [EVALUATE]
  ─► best action                                         [DECIDE]
  ─► "actual" run with perturbed params (plant != model) [ACT]
  ─► compare actual vs predicted                         [VERIFY]
  ─► correction factor on flexibility estimate           [LEARN]
```

Key design decision: the **plant** (what the sim "really" does) and the **predictor** (what the engine believes)
use the same equation but different parameters (e.g. UA/solar off by a few %). Without this, VERIFY/LEARN is theatre.

## 3. Phase table

| Ph | Build | Inputs | Outputs | Test |
|----|-------|--------|---------|------|
| 1 | Driver generator | BuildingSpec, weather, occupancy level | `SimulationData` (288×zones) | shapes, ranges, determinism, 70 % @13:30 |
| 2 | Thermal model | T, T_out, Q_int, Q_sol, Q_hvac | T_next / trajectory / required cooling | directionality, energy balance, capacity adequacy |
| 3 | Thermostat | SimulationData, params | T(t), HVAC thermal(t), comfort minutes | stays in band, no-event unchanged |
| 4 | Load model | HVAC thermal, COP, lighting, base | electrical kW(t) | kWh sums, COP direction |
| 5 | DR event | start, duration, kW | event object + mask | bounds validation |
| 6 | Candidates | state, event | list of (hvac_level, light_level) | levels in range |
| 7 | Constraints | trajectory | pass/fail + reason | comfort/lighting/equipment reject |
| 8 | Evaluator | feasible trajectories | metrics per candidate | reduction = baseline − proposed |
| 9 | Decision | metrics | best action + flexibility envelope | monotonic envelope |
| 10 | Rebound | post-event trajectory | rebound kW / kWh | aggressive > mild |
| 11 | Compare | baseline vs proposed | KPI table | no event ⇒ identical |
| 12 | Streamlit | all | one page | manual demo run |
| 13 | Office | spec | scenario B | flexibility differs by time |
| 14 | Edge tests | — | — | listed in brief |
| 15 | PPT evidence | final runs | screenshots, KPI CSV | numbers traceable to code |

## 4. Improvement classification

| Item | Class |
|------|-------|
| Constant system COP in load model | MUST (simple) |
| COP derating with T_out | SHOULD (makes "very hot" edge case honest) |
| Plant-vs-model parameter mismatch for VERIFY/LEARN | MUST |
| Flexibility envelope (kW vs safe minutes) chart | SHOULD |
| Confidence band from model mismatch | SHOULD |
| EV charging | OPTIONAL (only after Phase 12 stable) |
| Random noise in data | DO NOT BUILD NOW |
| MPC / solver / deep learning | DO NOT BUILD NOW |
| Inter-zone heat coupling, humidity/latent load | DO NOT BUILD NOW |

## 5. Honest weaknesses (say these before a judge does)

1. Single-node RC per zone: no envelope thermal-mass lag, no humidity. Directionally right, not calibrated.
2. Parameters are invented. Output kW values are scenario results, not predictions for a real building.
3. Rebound exists only because thermostat recovery is capacity-limited; this is realistic but sensitive to
   recovery-ramp assumptions — document them.
4. "Learning" is a bias/correction factor, not ML. Call it *verification-based correction*.
5. Dynamic flexibility estimation is not novel by itself (MPC / DR literature). Our differentiator is
   actionable + comfort- and rebound-aware + load-agnostic + retrofit framing.

## 6. Units (everywhere)

kW, kWh, °C, hours for Δt. `C` = kWh/°C, `UA` = kW/°C, all heat terms in kW **thermal**.
HVAC electrical kW = thermal kW / system COP.
