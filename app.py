from pathlib import Path
import sys

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from ups_twin import DigitalTwin, TwinConfig, load_telemetry, assess_health

st.set_page_config(page_title="UPS Digital Twin", layout="wide")
st.title("APC Smart-UPS Digital Twin")
st.caption("Telemetry-driven v1: calibrated state model + scenario simulator; ML can be added later.")

data_file = ROOT / "data" / "ups_telemetry.xlsx"
df, warnings = load_telemetry(data_file)
twin = DigitalTwin(TwinConfig()).fit(df)
pred = twin.predict_observed(df)
latest = pred.iloc[-1]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Battery SOC", f"{latest['%Cap']:.0f}%")
c2.metric("Battery voltage", f"{latest['Vbat']:.2f} V")
c3.metric("UPS temperature", f"{latest['TupsC']:.1f} °C")
c4.metric("Load", f"{latest['%Wout']:.1f}%")

health = assess_health({
    "soc_pct": latest["%Cap"],
    "load_pct": latest["%Wout"],
    "ambient_c": latest["T1ambC"],
    "Vbat": latest["Vbat"],
})
st.write(f"**Current health:** {health['severity']} — {'; '.join(health['flags'])}")

st.subheader("Observed telemetry")
fig = go.Figure()
fig.add_trace(go.Scatter(x=pred["timestamp"], y=pred["%Cap"], name="SOC %"))
fig.add_trace(go.Scatter(x=pred["timestamp"], y=pred["Vbat"], name="Vbat V", yaxis="y2"))
fig.update_layout(
    height=420,
    xaxis_title="Time of day",
    yaxis_title="SOC (%)",
    yaxis2=dict(title="Battery voltage (V)", overlaying="y", side="right"),
)
st.plotly_chart(fig, use_container_width=True)

fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=pred["timestamp"], y=pred["%Wout"], name="Load %"))
fig2.add_trace(go.Scatter(x=pred["timestamp"], y=pred["TupsC"], name="UPS temp °C", yaxis="y2"))
fig2.add_trace(go.Scatter(x=pred["timestamp"], y=pred["T1ambC"], name="Ambient °C", yaxis="y2"))
fig2.update_layout(
    height=420,
    xaxis_title="Time of day",
    yaxis_title="Load (%Wout)",
    yaxis2=dict(title="Temperature (°C)", overlaying="y", side="right"),
)
st.plotly_chart(fig2, use_container_width=True)

st.subheader("Scenario: battery outage")
a, b, c = st.columns(3)
with a:
    start_soc = st.slider("Starting SOC (%)", 10, 100, int(latest["%Cap"]))
with b:
    load_pct = st.slider("Constant load (% of 670 W)", 1, 90, 20)
with c:
    ambient = st.slider("Ambient temperature (°C)", 10, 45, int(latest["T1ambC"]))
duration = st.slider("Outage duration (minutes)", 15, 480, 180, 15)

sim = twin.simulate_outage(start_soc, load_pct, ambient, duration)
fig3 = go.Figure()
fig3.add_trace(go.Scatter(x=sim["elapsed_min"], y=sim["soc_pct"], name="Simulated SOC %"))
fig3.update_layout(height=360, xaxis_title="Elapsed minutes", yaxis_title="SOC (%)", yaxis_range=[0, 100])
st.plotly_chart(fig3, use_container_width=True)

st.write(f"**Predicted end SOC:** {sim.iloc[-1]['soc_pct']:.1f}%")
if sim.iloc[-1]["soc_pct"] <= twin.cfg.low_soc_pct:
    st.warning("Scenario reaches the project low-SOC threshold. The threshold is configurable and is not a vendor alarm specification.")

with st.expander("Twin calibration"):
    st.json(twin.fit_summary)
    if warnings:
        st.write({"data_warnings": warnings})
