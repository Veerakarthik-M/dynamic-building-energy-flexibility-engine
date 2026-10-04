"""Dynamic Building Energy Flexibility Engine — Streamlit Web Prototype

All data is SIMULATION DATA generated from physics-informed building models.
All parameters are prototype assumptions, not field measurements.
Comfort band (23-26 °C) is a prototype comfort assumption.
"""
from __future__ import annotations

import streamlit as st
import pandas as pd

from scenarios import SCENARIOS
from flexibility.engine import assess, sensitivity, flexibility_timeline
from flexibility.explain import explain
from visualization.charts import (
    plot_baseline_vs_proposed,
    plot_indoor_temperatures,
    plot_load_breakdown,
    plot_envelope,
    plot_daily_flexibility_timeline,
)

# Page configuration
st.set_page_config(
    page_title="Dynamic Building Energy Flexibility Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for clean, professional light-theme polish
st.markdown("""
<style>
    .stApp {
        background-color: #f9fafb;
        color: #111827;
    }
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        padding: 16px;
        text-align: center;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
    }
    .metric-value {
        font-size: 2.2rem;
        font-weight: 700;
        margin-top: 4px;
        margin-bottom: 2px;
        color: #1f2937;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #6b7280;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .status-banner-full {
        background-color: #ecfdf5;
        border: 1px solid #10b981;
        border-radius: 6px;
        padding: 14px;
        color: #065f46;
    }
    .status-banner-partial {
        background-color: #fffbeb;
        border: 1px solid #f59e0b;
        border-radius: 6px;
        padding: 14px;
        color: #92400e;
    }
    .status-banner-infeasible {
        background-color: #fef2f2;
        border: 1px solid #ef4444;
        border-radius: 6px;
        padding: 14px;
        color: #991b1b;
    }
    .sim-tag {
        background-color: #e5e7eb;
        color: #374151;
        font-size: 0.75rem;
        padding: 2px 8px;
        border-radius: 4px;
    }
    /* Readability: force dark text on light background everywhere */
    .stApp, .stApp p, .stApp li, .stApp span, .stApp label, .stApp h1, .stApp h2, .stApp h3,
    .stApp [data-testid="stMarkdownContainer"], .stApp [data-testid="stCaptionContainer"] {
        color: #111827;
    }
    [data-testid="stCaptionContainer"], .stApp small { color: #4b5563 !important; }
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e5e7eb; }
    [data-testid="stSidebar"] * { color: #111827; }
    [data-testid="stSidebar"] button[kind="primary"] * { color: #ffffff; }
    .stTabs [data-baseweb="tab"] p { color: #374151 !important; font-weight: 600; }
    .stTabs [aria-selected="true"] p { color: #1d4ed8 !important; }
    [data-testid="stTable"] table, [data-testid="stTable"] th, [data-testid="stTable"] td {
        color: #111827 !important; background-color: #ffffff !important;
        border-color: #e5e7eb !important;
    }
    [data-testid="stExpander"] { background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 6px; }
    [data-testid="stExpander"] summary p { color: #111827 !important; }
    [data-baseweb="select"] > div { background-color: #ffffff; color: #111827; }
</style>
""", unsafe_allow_html=True)

# App Header
st.title("⚡ Dynamic Building Energy Flexibility Engine")
st.caption("🔬 **SIMULATION PROTOTYPE** | *Physics-Informed Building Thermal Model & Constraint-Aware Control*")

# Sidebar Controls
st.sidebar.header("🎛️ Simulation Controls")

scenario_key = st.sidebar.selectbox("Scenario", list(SCENARIOS.keys()), index=0)
scenario = SCENARIOS[scenario_key]

weather = st.sidebar.selectbox("Weather Condition", ["hot", "mild"], index=0 if scenario.default_weather == "hot" else 1)
occupancy_level = st.sidebar.selectbox("Occupancy Level", ["low", "normal", "high"], index=1)

st.sidebar.markdown("---")
st.sidebar.subheader("⚡ Demand Response Event")

requested_kw = st.sidebar.slider("Requested Reduction (kW)", min_value=10.0, max_value=80.0, value=scenario.default_request_kw, step=5.0)
duration_min = st.sidebar.slider("Event Duration (min)", min_value=5, max_value=60, value=scenario.default_duration_min, step=5)

# Clock time selector
default_h = scenario.default_start_hour
start_hour = st.sidebar.slider("Event Start Time (Hour)", min_value=8.0, max_value=18.0, value=default_h, step=0.25, format="%.2f")

st.sidebar.markdown("---")
run_clicked = st.sidebar.button("🚀 Run Flexibility Assessment", use_container_width=True, type="primary")

# Execute engine simulation
@st.cache_data(ttl=600, show_spinner=False)
def run_simulation(s_key, wth, occ, start_h, dur_m, req_kw):
    sc = SCENARIOS[s_key]
    data = sc.build(wth, occ)
    assessment = assess(data, start_h, dur_m, req_kw)
    sens_df = sensitivity(sc.build, wth, occ, start_h, dur_m, req_kw)
    timeline_df = flexibility_timeline(data, dur_m, req_kw)
    return assessment, sens_df, timeline_df

with st.spinner("Running 9-stage flexibility assessment simulation..."):
    assessment, sens_df, timeline_df = run_simulation(scenario_key, weather, occupancy_level, start_hour, duration_min, requested_kw)

sensed = assessment.state

# ------------------------------------------------------------- 1. TOP KPI CARDS
col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Current Load</div>
        <div class="metric-value" style="color: #374151;">{sensed['current_load_kw']:.0f} <span style="font-size:1rem;">kW</span></div>
        <div style="font-size:0.8rem; color:#4b5563;">HVAC: {sensed['hvac_kw']:.0f} kW</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    avail_color = "#1d4ed8" if assessment.available_kw >= requested_kw else "#b45309"
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Available Flexibility</div>
        <div class="metric-value" style="color: {avail_color};">{assessment.available_kw:.0f} <span style="font-size:1rem;">kW</span></div>
        <div style="font-size:0.8rem; color:#4b5563;">Delivered: {assessment.feasible_kw:.0f} kW</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Safe Duration</div>
        <div class="metric-value" style="color: #6d28d9;">{assessment.safe_duration_min} <span style="font-size:1rem;">min</span></div>
        <div style="font-size:0.8rem; color:#4b5563;">Requested: {duration_min} min</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    risk_color = "#15803d" if assessment.comfort_risk == "Low" else ("#b45309" if assessment.comfort_risk == "Medium" else "#b91c1c")
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Comfort Risk</div>
        <div class="metric-value" style="color: {risk_color};">{assessment.comfort_risk}</div>
        <div style="font-size:0.8rem; color:#4b5563;">Margin: {assessment.actual['min_margin_c']:.2f} °C</div>
    </div>
    """, unsafe_allow_html=True)

with col5:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">Expected Rebound</div>
        <div class="metric-value" style="color: #be185d;">{assessment.actual['rebound_kw']:.0f} <span style="font-size:1rem;">kW</span></div>
        <div style="font-size:0.8rem; color:#4b5563;">Duration: ~{assessment.actual['rebound_min']:.0f} min</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ------------------------------------------------------------- 2. RECOMMENDATION & EXPLANATION PANEL
explanations = explain(assessment, sens_df)
headline_type, headline_text = explanations[0]

status_class = "status-banner-full" if assessment.status == "full" else ("status-banner-partial" if assessment.status == "partial" else "status-banner-infeasible")

st.markdown(f"""
<div class="{status_class}">
    <h3 style="margin:0 0 4px 0; font-size:1.25rem;">📢 Engine Recommendation: {headline_text}</h3>
</div>
""", unsafe_allow_html=True)

with st.expander("🔍 **Detailed Decision & Physical Explainability (Why Flexibility Changed)**", expanded=True):
    for kind, text in explanations[1:]:
        if kind == "state":
            st.markdown(f"• 🌡️ **Building State:** {text}")
        elif kind == "why":
            st.markdown(f"• ⚠️ **Limiting Constraints:** {text}")
        elif kind == "action":
            st.markdown(f"• 🎯 **Recommended Action:** {text}")
        elif kind == "rebound":
            st.markdown(f"• 🔄 **Rebound & Recovery Impact:** {text}")
        elif kind == "verify":
            st.markdown(f"• ✅ **Verification & Model Update:** {text}")

# Pipeline Execution Trace Expander
with st.expander("⚙️ **9-Stage Architectural Flow Trace (SENSE -> LEARN)**", expanded=False):
    trace_cols = st.columns(3)
    for idx, (stage, details) in enumerate(assessment.trace):
        with trace_cols[idx % 3]:
            st.markdown(f"**{stage}**\n\n{details}")

st.markdown("---")

# ------------------------------------------------------------- 3. CHARTS GRID
c_left, c_right = st.columns([1.6, 1.0])

with c_left:
    st.plotly_chart(plot_baseline_vs_proposed(assessment), use_container_width=True)
    st.plotly_chart(plot_indoor_temperatures(assessment), use_container_width=True)

with c_right:
    st.plotly_chart(plot_load_breakdown(assessment), use_container_width=True)
    st.plotly_chart(plot_envelope(assessment.envelope, requested_kw, duration_min), use_container_width=True)

st.markdown("---")

# ------------------------------------------------------------- 4. DYNAMIC FLEXIBILITY PROOF & IMPACT
tab1, tab2, tab3 = st.tabs(["📊 Baseline vs. Proposed Impact Table", "📈 Daily Dynamic Flexibility Profile", "🧪 Sensitivity Analysis"])

with tab1:
    st.subheader("Simulated Performance Metrics")
    kpi_rows = []
    for metric, (b_val, p_val) in assessment.kpis.items():
        diff = p_val - b_val
        pct = (diff / b_val * 100) if b_val != 0 else 0
        kpi_rows.append({
            "Metric": metric,
            "Baseline": f"{b_val:.1f}",
            "Proposed (Flexibility-Aware)": f"{p_val:.1f}",
            "Delta": f"{diff:+.1f} ({pct:+.1f}%)"
        })
    st.table(pd.DataFrame(kpi_rows))
    st.caption("ℹ️ *All metrics generated directly by physics simulation runs.*")

with tab2:
    st.subheader("Proof of Dynamic Flexibility (Flexibility ≠ Fixed Percentage of Load)")
    st.plotly_chart(plot_daily_flexibility_timeline(timeline_df), use_container_width=True)
    st.info("💡 **Core Insight:** Notice how available flexibility (kW) and flexibility share (%) fluctuate dramatically throughout the day based on occupancy, outdoor heat, and thermal headroom—proving that building flexibility is dynamic.")

with tab3:
    st.subheader("Sensitivity across Occupancy & Weather Conditions")
    st.dataframe(sens_df, use_container_width=True)

# Footer
st.markdown("---")
st.caption("Yuva Yodha Hackathon 2026 • Smart Buildings • Dynamic Building Energy Flexibility Engine • *Simulation Data Only*")

