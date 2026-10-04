"""Phase 15 — Generate Final Simulation Evidence & KPI Tables for PPT."""
import os
import pandas as pd

from scenarios import SCENARIOS
from flexibility.engine import assess, sensitivity, flexibility_timeline
from visualization.charts import plot_baseline_vs_proposed, plot_indoor_temperatures

os.makedirs("output_evidence", exist_ok=True)

results_summary = []

for sc_key, sc in SCENARIOS.items():
    data = sc.build(sc.default_weather, sc.default_occupancy)
    a = assess(data, sc.default_start_hour, sc.default_duration_min, sc.default_request_kw)
    
    # Save chart HTMLs
    plot_baseline_vs_proposed(a).write_html(f"output_evidence/{sc_key}_load_profile.html")
    plot_indoor_temperatures(a).write_html(f"output_evidence/{sc_key}_indoor_temp.html")
    
    # Format KPI Table
    kpi_dict = {"Scenario": sc_key, "Weather": sc.default_weather, "Occupancy": sc.default_occupancy,
                "Requested (kW)": sc.default_request_kw, "Available Flex (kW)": a.available_kw,
                "Delivered (kW)": a.feasible_kw, "Status": a.status, "Safe Duration (min)": a.safe_duration_min,
                "Comfort Risk": a.comfort_risk, "Rebound (kW)": a.actual["rebound_kw"],
                "Rebound (min)": a.actual["rebound_min"]}
    results_summary.append(kpi_dict)

df_summary = pd.DataFrame(results_summary)
df_summary.to_csv("output_evidence/final_kpi_summary.csv", index=False)

print("==========================================================================")
print("FINAL SIMULATION-GENERATED KPI EVIDENCE TABLE (FOR PPT)")
print("==========================================================================")
print(df_summary.to_string(index=False))
print("==========================================================================")
print("Saved interactive HTML charts and final_kpi_summary.csv to output_evidence/")
