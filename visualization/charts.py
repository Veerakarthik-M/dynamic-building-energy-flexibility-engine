"""Charts (Plotly) for Streamlit Dashboard.

Includes:
1. Chart 1: 24-hour Baseline vs Proposed Electrical Load (with Event & Rebound highlighted)
2. Chart 2: Indoor Temperature per zone vs Prototype Comfort Band (23-26 °C)
3. Chart 3: Flexibility Load Contribution (HVAC vs Lighting breakdown)
4. Chart 4: Flexibility Envelope & Safe Duration vs Requested kW
5. Chart 5: Daily Flexibility Timeline across hours
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data.synthetic_building import COMFORT_BAND_C

SIM_NOTE = "SIMULATION DATA — prototype assumptions, not field measurements"


def plot_baseline_vs_proposed(a) -> go.Figure:
    """Chart 1: 24-hour Baseline vs Proposed load with event & rebound shading."""
    t = a.time
    i0 = a.i0
    n_ev = a.n_event
    n_rec = a.n_recovery

    fig = go.Figure()

    # Event highlight box
    t_start = t[i0]
    t_end_ev = t[min(i0 + n_ev, len(t) - 1)]
    t_end_rec = t[min(i0 + n_ev + n_rec, len(t) - 1)]

    fig.add_vrect(
        x0=t_start, x1=t_end_ev,
        fillcolor="#3b82f6", opacity=0.15, line_width=1, line_color="#3b82f6",
        annotation_text="DR Event", annotation_position="top left"
    )
    fig.add_vrect(
        x0=t_end_ev, x1=t_end_rec,
        fillcolor="#d97706", opacity=0.10, line_width=1, line_dash="dot", line_color="#d97706",
        annotation_text="Recovery / Rebound", annotation_position="top left"
    )

    # Baseline load trace
    fig.add_trace(go.Scatter(
        x=t, y=a.baseline_total, name="Baseline Load (kW)",
        line=dict(color="#475569", width=2, dash="dash")
    ))

    # Proposed load trace
    fig.add_trace(go.Scatter(
        x=t, y=a.proposed_total, name="Flexibility-Aware Load (kW)",
        line=dict(color="#2563eb", width=3)
    ))

    fig.update_layout(
        title=f"24-Hour Building Load Profile — Baseline vs. Proposed<br><sup>{SIM_NOTE}</sup>",
        xaxis_title="Time of Day",
        yaxis_title="Electrical Demand (kW)",
        template="plotly_white",
        height=380,
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig


def plot_indoor_temperatures(a) -> go.Figure:
    """Chart 2: Indoor temperature per zone vs comfort band."""
    t = a.time
    i0 = a.i0
    n_ev = a.n_event
    n_rec = a.n_recovery

    fig = go.Figure()

    # Comfort band rect
    fig.add_hrect(
        y0=COMFORT_BAND_C[0], y1=COMFORT_BAND_C[1],
        fillcolor="#22c55e", opacity=0.12, line_width=1, line_color="#22c55e",
        annotation_text="Prototype Comfort Assumption (23.0 - 26.0 °C)", annotation_position="bottom right"
    )

    # Upper planning limit (25.8 °C)
    fig.add_hline(
        y=25.8, line_dash="dash", line_color="#ef4444", opacity=0.6,
        annotation_text="Planning Limit (25.8 °C)", annotation_position="top right"
    )

    # Event highlight
    fig.add_vrect(
        x0=t[i0], x1=t[min(i0 + n_ev, len(t) - 1)],
        fillcolor="#3b82f6", opacity=0.10, line_width=0
    )

    colors = ["#2563eb", "#7c3aed", "#c026d3", "#db2777", "#ea580c"]
    for j, zname in enumerate(a.zone_names):
        # Baseline dashed
        fig.add_trace(go.Scatter(
            x=t, y=a.baseline_T[:, j], name=f"{zname} (Base)",
            line=dict(color=colors[j % len(colors)], width=1, dash="dot"),
            showlegend=False
        ))
        # Proposed solid
        fig.add_trace(go.Scatter(
            x=t, y=a.proposed_T[:, j], name=zname,
            line=dict(color=colors[j % len(colors)], width=2.5)
        ))

    fig.update_layout(
        title=f"Zone Indoor Temperatures — Thermal Headroom & Comfort<br><sup>{SIM_NOTE}</sup>",
        xaxis_title="Time of Day",
        yaxis_title="Indoor Temp (°C)",
        template="plotly_white",
        height=380,
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig


def plot_load_breakdown(a) -> go.Figure:
    """Chart 3: Flexibility Contribution Breakdown during event."""
    fig = go.Figure()

    labels = ["HVAC Curtailment", "Lighting Dimming"]
    values = [a.contrib_hvac_kw, a.contrib_light_kw]
    colors = ["#2563eb", "#d97706"]

    fig.add_trace(go.Bar(
        x=labels, y=values,
        marker_color=colors,
        text=[f"{v:.1f} kW" for v in values],
        textposition="auto"
    ))

    fig.update_layout(
        title=f"Flexibility Contribution by Load Type<br><sup>{SIM_NOTE}</sup>",
        yaxis_title="Reduction Delivered (kW)",
        template="plotly_white",
        height=320,
        margin=dict(l=40, r=40, t=60, b=40),
        showlegend=False
    )
    return fig


def plot_envelope(envelope_dict, requested_kw: float, current_duration: int) -> go.Figure:
    """Chart 4: Flexibility Envelope — Reduction Amount vs. Safe Duration."""
    durations = sorted(envelope_dict.keys())
    max_kws = [envelope_dict[d] for d in durations]

    fig = go.Figure()

    # Envelope line
    fig.add_trace(go.Scatter(
        x=durations, y=max_kws, mode="lines+markers",
        name="Max Safe Reduction (kW)",
        line=dict(color="#2563eb", width=3),
        marker=dict(size=8, color="#1d4ed8")
    ))

    # Requested point marker
    fig.add_trace(go.Scatter(
        x=[current_duration], y=[requested_kw],
        mode="markers", name="Current Request",
        marker=dict(size=14, color="#ef4444", symbol="star")
    ))

    fig.update_layout(
        title=f"Flexibility Envelope — Max Reduction vs. Safe Duration<br><sup>{SIM_NOTE}</sup>",
        xaxis_title="Event Duration (minutes)",
        yaxis_title="Feasible Reduction (kW)",
        template="plotly_white",
        height=320,
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig


def plot_daily_flexibility_timeline(df_timeline) -> go.Figure:
    """Chart 5: Dynamic flexibility available across hours of the day."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(go.Scatter(
        x=df_timeline["hour"], y=df_timeline["load_kw"],
        name="Building Total Load (kW)",
        line=dict(color="#475569", width=2, dash="dash")
    ), secondary_y=False)

    fig.add_trace(go.Bar(
        x=df_timeline["hour"], y=df_timeline["available_kw"],
        name="Available Flexibility (kW)",
        marker_color="#2563eb", opacity=0.7
    ), secondary_y=False)

    fig.add_trace(go.Scatter(
        x=df_timeline["hour"], y=df_timeline["share_pct"],
        name="Flexibility Share (% of Load)",
        line=dict(color="#d97706", width=2.5)
    ), secondary_y=True)

    fig.update_layout(
        title=f"Daily Flexibility Profile — Dynamic Capacity across Operating Hours<br><sup>{SIM_NOTE}</sup>",
        xaxis_title="Clock Hour",
        template="plotly_white",
        height=350,
        margin=dict(l=40, r=40, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_yaxes(title_text="kW", secondary_y=False)
    fig.update_yaxes(title_text="% of Total Load", secondary_y=True)
    return fig


def baseline_preview(data, traj, load) -> go.Figure:
    t = data.time
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                        subplot_titles=("Baseline electrical load (kW)",
                                        "Indoor temperature per zone vs prototype comfort band"))
    for name, y, col in (("Base (essential)", load.base_kw, "#64748b"),
                         ("Lighting", load.lighting_kw, "#d97706"),
                         ("HVAC", load.hvac_kw, "#2563eb")):
        fig.add_trace(go.Scatter(x=t, y=y, name=name, stackgroup="one", line=dict(width=0.5, color=col)),
                      row=1, col=1)
    for j, zname in enumerate(data.spec.zone_names):
        fig.add_trace(go.Scatter(x=t, y=traj.T_series[:, j], name=zname, mode="lines"), row=2, col=1)
    fig.add_hrect(y0=COMFORT_BAND_C[0], y1=COMFORT_BAND_C[1], fillcolor="green", opacity=0.1,
                  line_width=0, row=2, col=1, annotation_text="Prototype comfort assumption 23–26 °C")
    fig.update_layout(height=750, template="plotly_white",
                      title=f"{data.spec.name} — baseline thermostat | {data.weather} / {data.occupancy_level} "
                            f"<br><sup>{SIM_NOTE}</sup>")
    fig.update_yaxes(title_text="kW", row=1, col=1)
    fig.update_yaxes(title_text="°C", row=2, col=1)
    return fig

