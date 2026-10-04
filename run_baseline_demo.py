"""Run the college baseline and write baseline_preview.html + print KPIs.

    python run_baseline_demo.py [hot|mild] [low|normal|high]
"""
import sys
import webbrowser
from pathlib import Path

from models.baseline_controller import run_baseline
from models.load_model import comfort_violation_minutes, electrical_load, energy_kwh, peak_kw
from scenarios.college import college_data
from visualization.charts import baseline_preview

weather = sys.argv[1] if len(sys.argv) > 1 else "hot"
occ = sys.argv[2] if len(sys.argv) > 2 else "normal"

data = college_data(weather, occ)
traj = run_baseline(data)
load = electrical_load(data, traj.q_hvac_th)
pk, i = peak_kw(load.total_kw)
cv = comfort_violation_minutes(traj.T_series, data.occupancy, data.dt_h)
print(f"[SIMULATION] College | {weather} | {occ}")
print(f"Energy: {energy_kwh(load.total_kw, data.dt_h):.0f} kWh | Peak: {pk:.1f} kW at {data.time[i]:%H:%M}")
print(f"Comfort violations: {cv['building_minutes']:.0f} building-min, {cv['zone_minutes']:.0f} zone-min")
j = data.index_at(14 + 20 / 60)
print(f"At 14:20 -> total {load.total_kw[j]:.1f} kW (HVAC {load.hvac_kw[j]:.1f}, "
      f"lighting {load.lighting_kw[j]:.1f}, base {load.base_kw[j]:.1f}); zone T {traj.T_series[j].round(2)}")

out = Path("baseline_preview.html").resolve()
baseline_preview(data, traj, load).write_html(out)
print("Wrote", out)
webbrowser.open(out.as_uri())
