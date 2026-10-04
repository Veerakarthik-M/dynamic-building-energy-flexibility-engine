# ⚡ Dynamic Building Energy Flexibility Engine

[![Hackathon](https://img.shields.io/badge/Yuva%20Yodha-2026-blue.svg)](https://www.yuvayodhatech.com/challenges)
[![Theme](https://img.shields.io/badge/Track-Smart%20Buildings-emerald.svg)]()
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![UI](https://img.shields.io/badge/Dashboard-Streamlit-red.svg)](https://streamlit.io/)
[![Physics](https://img.shields.io/badge/Physics-Grey--Box%20RC%20Model-orange.svg)]()
[![Tests](https://img.shields.io/badge/Tests-39%20Passed-brightgreen.svg)]()

> **Yuva Yodha Hackathon 2026 — Smart Buildings Track**  
> *A Physics-Informed Building Thermal Model & Constraint-Aware Control Engine for Dynamic Demand Response.*

> 🔬 **SIMULATION NOTICE:** All datasets, thermal parameters, and baseline metrics are **SIMULATION DATA** generated from first-order physics-informed building models (lumped-capacitance RC thermal networks modeled after commercial ASHRAE standards). Comfort bands ($23.0 - 26.0^\circ\text{C}$) are prototype comfort assumptions.

---

## 📌 Executive Summary & Problem Statement

### The Problem with Traditional Grid Demand Response
When power grids experience peak stress, utilities send demand response (DR) signals asking commercial buildings to cut power by a **static percentage** (e.g., *"cut 10% for 45 minutes"*). However:
1. **Buildings are dynamic thermochemical systems:** Room temperatures rise rapidly depending on occupancy density, solar heat gain, and outdoor ambient temperature.
2. **Blind cuts breach human comfort:** Unconstrained HVAC curtailment causes rooms to overheat, creating tenant dissatisfaction and safety violations.
3. **The Rebound Peak Penalty:** When the DR event ends, HVAC chillers kick back on simultaneously at full power to recover temperature setpoints. This creates a massive **post-event rebound peak** that can incur severe utility peak-demand charges.

### Our Solution
The **Dynamic Building Energy Flexibility Engine** replaces static guesswork with **real-time thermodynamic physics**. It continuously senses the building's thermal state, predicts 24-hour baseline trajectories, evaluates candidate control actions against thermal comfort constraints, and delivers a **physics-backed, guaranteed safe flexibility capacity (kW)** alongside explicit post-event rebound predictions.

---

## 🏗️ 9-Stage Architectural Pipeline

The engine operates on a closed-loop **SENSE $\rightarrow$ LEARN** pipeline:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       9-STAGE ENGINE ARCHITECTURE                           │
└─────────────────────────────────────────────────────────────────────────────┘

  [1. SENSE] ───────► Ingest live building state (Zone Temps, Outdoor T, Occupancy)
        │
  [2. PREDICT] ─────► Roll out 24-hour Baseline Trajectory (1st-Order RC Physics)
        │
  [3. GENERATE] ────► Formulate Candidate Actions (HVAC Curtailment x Lighting)
        │
  [4. CONSTRAIN] ───► Filter Violations (Comfort Band 23–26°C, Peak Limit)
        │
  [5. EVALUATE] ────► Multi-objective Scoring (Shortfall, Rebound, Thermal Headroom)
        │
  [6. DECIDE] ──────► Select Optimal Feasible Control Action
        │
  [7. ACT] ─────────► Dispatch Control Signal to Plant Simulation
        │
  [8. VERIFY] ──────► Measure Mismatch (Simulated Plant vs Model Trajectory)
        │
  [9. LEARN] ───────► Apply Adaptive Bias-Correction Model Factor
```

---

## 📐 Simulation Parameters (Grey-Box Specifications)

To ensure evaluators and judges have full transparency into the underlying physics simulation, the engine uses the following explicitly defined environmental and operational boundary conditions:

### ☀️ Weather Profiles
- **Hot (Peak Summer):** Mean Outdoor Temp = $34.0^\circ\text{C}$, Amplitude = $\pm 5.0^\circ\text{C}$ (Peak at 15:00), Solar Multiplier = $1.0\times$
- **Mild (Shoulder Season):** Mean Outdoor Temp = $27.0^\circ\text{C}$, Amplitude = $\pm 4.0^\circ\text{C}$ (Peak at 15:00), Solar Multiplier = $0.7\times$

### 👥 Occupancy Levels
- **Low:** $50\%$ of the baseline scheduled capacity.
- **Normal:** $100\%$ of the baseline scheduled capacity.
- **High:** $115\%$ of the baseline scheduled capacity (Simulating overcrowding or peak-event scenarios, capped at max physical capacity).

### 🌡️ Comfort Constraints
- **Absolute Comfort Band:** $23.0^\circ\text{C}$ (lower limit) to $26.0^\circ\text{C}$ (upper limit).
- **Proactive Planning Limit:** $25.8^\circ\text{C}$ (Ensures a $0.2^\circ\text{C}$ safety buffer to prevent mathematical limit violations during HVAC curtailment).

---

## 🔄 System Flowcharts

### A. End-to-End Decision Flow (what happens for one DR request)

```mermaid
flowchart TD
    A([Grid / Facility request:<br/>reduce X kW for D min]) --> B[1. SENSE<br/>zone temps, outdoor T, occupancy]
    B --> C[2. PREDICT<br/>baseline trajectory from RC model]
    C --> D[3. GENERATE<br/>candidate actions:<br/>setpoint relax, zone priority, lighting cut]
    D --> E{4. CONSTRAIN<br/>occupied zones T ≤ 25.8 °C,<br/>essential load untouched, ...?}
    E -- No --> F[Reject candidate]
    E -- Yes --> G[5. EVALUATE<br/>shortfall, rebound, thermal headroom]
    G --> H[6. DECIDE<br/>best feasible action]
    H --> I{Delivered kW vs request}
    I -- ≥ 97% --> J[FULL feasible]
    I -- 50% to 97% --> K[PARTIAL feasible]
    I -- < 50% --> L[INFEASIBLE]
    J --> M[7. ACT → 8. VERIFY → 9. LEARN]
    K --> M
    L --> M
    M --> N([Report: feasible kW, safe duration,<br/>comfort risk, rebound risk, confidence])
```

### B. Constraint Filter (why an action is accepted or rejected)

```mermaid
flowchart LR
    C[Candidate action] --> S[Simulate every zone<br/>with RC model]
    C --> Q{Essential base load cut = 0,<br/>lighting ≥ minimum level,<br/>HVAC 0–100 %, duration ≤ max?}
    Q -- No --> R0[❌ Rejected: static rule]
    Q -- Yes --> S
    S --> T{Occupied zones<br/>T ≤ 25.8 °C and ≥ 23 °C<br/>throughout?}
    T -- No --> R[❌ Rejected: comfort breach]
    T -- Yes --> P{HVAC output ≤<br/>equipment capacity?}
    P -- No --> R2[❌ Rejected: equipment limit]
    P -- Yes --> B{Recovery peak ≤<br/>baseline day peak + 10 %?}
    B -- No --> R3[❌ Rejected: new peak]
    B -- Yes --> OK[✅ Feasible candidate]
```

### C. Closed-Loop Learning (stages 7 to 9)

```mermaid
flowchart LR
    A[Dispatch plan] --> B[Simulated plant responds<br/>UA x1.07, C x0.95, solar x1.05 vs model]
    B --> C[Compare actual reduction vs<br/>model-predicted reduction]
    C --> D[Compute correction factor]
    D --> E[Apply memory correction<br/>to next flexibility estimate]
    E --> A
```

---

## 🧮 Formula Reference (all equations used by the engine)

| # | Quantity | Formula | Where in code |
| :-: | :--- | :--- | :--- |
| 1 | **Zone temperature update** (discrete RC step) | $T_{k+1} = T_k + \dfrac{\Delta t}{C}\left[\,UA\,(T_{out} - T_k) + Q_{int} + Q_{solar} - Q_{hvac}\,\right]$ | `models/thermal_model.py` |
| 2 | **Continuous form** | $C\,\dfrac{dT}{dt} = UA\,(T_{out}-T) + Q_{int} + Q_{solar} - Q_{hvac}$ | same |
| 3 | **Thermostat cooling fraction** | $f = \text{clip}\!\left(\dfrac{T - 23.5}{25.5 - 23.5},\,0,\,1\right)$, $\;Q_{hvac} = f \cdot Q_{cap}$ | `models/baseline_controller.py` |
| 4 | **COP derating with outdoor temp** | $COP(T_{out}) = COP_{ref}\cdot\max\!\big(1 - 0.01\,(T_{out}-35),\;0.5\big)$ | `models/load_model.py` |
| 5 | **HVAC electrical power** | $P_{hvac} = \dfrac{Q_{hvac}}{COP(T_{out})}$ | `models/load_model.py` |
| 6 | **Total building load** | $P_{total} = P_{hvac} + P_{lighting} + P_{base}$ | `models/load_model.py` |
| 7 | **Delivered reduction** | $\Delta P = P_{baseline} - P_{controlled}$ over the event window | `flexibility/engine.py` |
| 8 | **Feasibility class** | Full if $\dfrac{\Delta P}{P_{req}} \ge 0.97$; Infeasible if $< 0.50$; else Partial | `flexibility/engine.py` |
| 9 | **Rebound (recovery excess)** | $P_{rebound}(t) = P_{recovery}(t) - P_{baseline}(t)$; peak = $\max_t P_{rebound}$ | `flexibility/rebound.py` |
| 10 | **Comfort constraint** (occupied zones) | $23.0 \le T_{zone}(t) \le 26.0 - 0.2 = 25.8\,^\circ\text{C}$ | `flexibility/constraints.py` |
| 11 | **New-peak constraint** | $\max_t P_{total}(t) \le 1.10 \times P_{baseline,peak}$ | `flexibility/constraints.py` |
| 12 | **Comfort-risk level** | worst thermal margin $m$: Low if $m \ge 0.5\,^\circ\text{C}$, Medium if $m \ge 0.3\,^\circ\text{C}$, else High | `flexibility/engine.py` |
| 13 | **Energy** | $E = \sum_k P_k\,\Delta t$ (kWh) | `models/load_model.py` |

**Symbols:** $T$ zone temperature (°C), $T_{out}$ outdoor temperature (°C), $C$ thermal capacitance (kWh/°C), $UA$ envelope conductance (kW/°C), $Q_{int}$ internal gains from people, equipment and lights (kW), $Q_{solar}$ solar gain (kW), $Q_{hvac}$ cooling delivered (kW thermal), $\Delta t$ timestep (h).

> All parameter values are **simulation assumptions** (see the Simulation Parameters section above).

---

## ✨ Key Technical Innovations

### 1. Grey-Box RC Thermal Network Modeling
Building thermal dynamics are simulated using a first-order lumped capacitance RC thermal model:

$$C_{\text{zone}}\frac{dT_{\text{zone}}}{dt} = UA\,(T_{\text{out}} - T_{\text{zone}}) + Q_{\text{int}} + Q_{\text{solar}} - Q_{\text{hvac}}, \qquad UA = \frac{1}{R_{\text{envelope}}}$$

- **Thermal Mass Heat Capacity ($C_{\text{zone}}$):** Captures heat stored in structural walls, floors, and furniture acting as a "thermal battery".
- **Thermal Resistance ($R_{\text{envelope}}$):** Models building envelope heat gain based on outdoor ambient weather conditions.

### 2. Constraint-Aware Decision Filtering
Candidate control actions are evaluated across strict thermal bounds:
- **Upper Comfort Boundary:** $26.0^\circ\text{C}$ (Hard limit).
- **Safety Planning Limit:** $25.8^\circ\text{C}$ (Safety headroom threshold).
- **Max Rebound Guard:** Post-event recovery power may not exceed the day's baseline peak demand by more than a $10\%$ tolerance.

### 3. Proof of Dynamic Flexibility
Building flexibility is **not a constant number**. The engine proves that available kW reduction fluctuates dynamically across 24 hours based on:
- Solar radiation profile (morning vs. peak afternoon heat).
- Variable occupant density (empty rooms vs. packed exam halls).
- Pre-existing thermal headroom stored in the building mass.

### 4. Natural Language Physical Explainability
Instead of acting as a black box, the decision engine outputs human-readable physical justifications:
- **State Explanation:** Live building thermal state and outdoor weather impact.
- **Limiting Constraints:** Exact reason why a request was modified (e.g., *"Meeting requested 50 kW would cause thermal breach in Zone 2 at t=15 min"*).
- **Recommended Action:** Feasible kW reduction delivered with zone-wise breakdown.
- **Rebound Impact:** Anticipated recovery duration and peak rebound kW.

---

## 📊 Interactive Web Simulation Dashboard

Built using **Streamlit** and **Plotly**, featuring an enterprise-grade light theme:

| Feature / Panel | Description |
| :--- | :--- |
| **🎛️ Simulation Controls** | Interactive sidebar for building scenario (College / Office), weather (hot / mild), occupancy levels, event duration, target kW reduction, and start time. |
| **💳 Top KPI Cards** | Real-time display of Current Load, Available Flexibility, Delivered kW, Safe Duration, Comfort Risk, and Expected Rebound. |
| **📢 Decision Recommendation** | Color-coded status banner (Green: Full Feasible, Yellow: Partial Feasible, Red: Infeasible) with physical explainability dropdowns. |
| **📈 Load Profile Chart** | 24-Hour baseline vs. flexibility-aware load curves highlighting DR event window & post-event recovery rebound bump. |
| **🌡️ Temperature & Headroom** | Multi-zone temperature trajectories plotted against the $23.0 - 26.0^\circ\text{C}$ comfort band and $25.8^\circ\text{C}$ planning threshold. |
| **🧩 Load Breakdown & Envelope** | Bar chart of HVAC curtailment vs. lighting dimming, alongside the mathematical Flexibility Envelope curve (Max Reduction vs. Duration). |
| **📅 Daily Dynamic Timeline** | 24-Hour hourly flexibility profile proving dynamic capacity fluctuation across operating hours. |

---

## 🚀 Quick Start Guide

### 1. Prerequisites
Ensure Python **3.10+** is installed on your system.

### 2. Installation
Clone the repository and install required packages:

```bash
git clone https://github.com/Veerakarthik-M/dynamic-building-energy-flexibility-engine.git
cd dynamic-building-energy-flexibility-engine
pip install -r requirements.txt
```

### 3. Launch Interactive Web Dashboard
Run the Streamlit web application:

```bash
streamlit run app.py
```

The app will open automatically in your web browser at `http://localhost:8501`.

### 4. Run Automated Test Suite
Verify model stability, physics directionality, and constraint enforcement across **39 automated unit tests**:

```bash
python -m pytest
```

### 5. Generate PPT Simulation Evidence & CSV Reports
Export quantitative performance metrics and interactive HTML chart evidence:

```bash
python generate_final_evidence.py
```

Generated outputs will be saved to `output_evidence/` and `baseline_preview.html`.

---

## 📂 Project Architecture & Directory Structure

```
dynamic-building-energy-flexibility-engine/
├── app.py                      # Streamlit Web Application Dashboard
├── requirements.txt            # Dependencies (NumPy, Pandas, Plotly, Streamlit, Pytest)
├── pytest.ini                  # Pytest runner configuration
├── .gitignore                  # Git tracking exclusion rules
├── PLAN.md                     # Engineering & Architecture Blueprint
├── README.md                   # Evaluator Documentation & Project Guide
│
├── data/
│   └── synthetic_building.py   # Synthetic Driver & Weather Data Generator
│
├── models/
│   ├── thermal_model.py        # First-Order Lumped RC Physics Thermal Model
│   ├── baseline_controller.py  # Proportional Thermostat Baseline Controller
│   └── load_model.py           # Electrical Load & COP Temperature Derating Model
│
├── flexibility/
│   ├── event.py                # Demand Response Event Data Structures
│   ├── candidate_actions.py    # Candidate Control Action Generator
│   ├── constraints.py          # Constraint Filter & Physical Violation Parser
│   ├── evaluator.py            # Batched Candidate Trajectory Evaluator
│   ├── optimizer.py            # Multi-Objective Flexibility Decision Engine
│   ├── rebound.py              # Post-Event Recovery Rebound Model
│   ├── engine.py               # 9-Stage Orchestrator (Sense, Act, Verify, Learn)
│   └── explain.py              # Natural Language Decision Explainability Engine
│
├── scenarios/
│   ├── base.py                 # Scenario Specification Standard
│   ├── college.py              # Scenario A: College Building (Primary Demo)
│   └── office.py               # Scenario B: Office Building (Dynamic Flexibility Proof)
│
├── visualization/
│   └── charts.py               # Plotly Dashboard Visualization Functions (Light Theme)
│
├── tests/
│   ├── test_synthetic_data.py  # Synthetic Generator Validation Tests
│   ├── test_thermal_model.py   # Thermal Physics Stability & Directionality Tests
│   ├── test_baseline_and_load.py # Thermostat & Electrical Load Tests
│   └── test_flexibility.py     # End-to-End Engine & Edge-Case Constraint Tests
│
└── output_evidence/           # Generated KPI Summary CSVs and Evidence HTML Reports
```

---

## 🧪 Quantitative Verification & Test Coverage

All core modules are verified by a comprehensive 39-test suite covering:
- **Physics Directionality:** Higher ambient temperature $\rightarrow$ faster indoor temperature rise.
- **Thermostat Stability:** Proportional cooling response without numerical divergence.
- **Constraint Enforcement:** Temperature never breaches upper limit in approved plans.
- **Rebound Peak Accounting:** Post-event demand bump accurately calculated.
- **Dynamic Capacity Variation:** Verification that available flexibility changes dynamically across hours.

---

## 👥 Team & Responsibilities

- **Simulation & Lead Engineer (Veerakarthik M):** First-order thermal physics model, engine orchestrator, Streamlit UI dashboard, visualization charts, and system integration.
- **Optimization & Test Engineering Lead (Puneeth):** Candidate action generation, constraint filtering algorithms, post-event rebound model, unit test suite.
- **Impact & Business Strategy Lead (Akhilesh):** Scenario definition, economic impact analysis, retrofit payback estimation, presentation.
- **Research & System Architecture Lead (Nandini):** System architecture design, Indian commercial building parameters, literature landscape & research gap analysis.

---

<p align="center">
  <b>Yuva Yodha Hackathon 2026</b> • Smart Buildings Track • <i>Dynamic Building Energy Flexibility Engine</i>
</p>
