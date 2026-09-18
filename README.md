# UPS Digital Twin Starter

This project turns the supplied APC Smart-UPS telemetry into a first-generation digital twin that can:

1. ingest and time-order the telemetry;
2. derive engineering variables such as load (W), apparent power (VA), estimated power factor and thermal rise;
3. calibrate an effective usable battery-energy model from the observed discharge period;
4. calibrate simple battery-voltage and thermal surrogate equations from the telemetry;
5. reproduce/compare observed behavior with the calibrated twin;
6. run a "what-if" battery-outage simulation;
7. expose a Streamlit dashboard;
8. leave a clean place for a later ML maintenance/anomaly layer.

## What the supplied data tells us

The workbook has 480 telemetry samples plus a header row, with approximately 3-minute sampling intervals. The source rows are in descending time order. There is also a mixed/raw date encoding issue in the Date column, so the loader deliberately uses Time-of-day for model chronology and does **not** silently rewrite the source Date values.

The telemetry contains a clear battery discharge/recharge episode: load becomes non-zero, `%Cap` falls from around 100% toward 30%, `Vbat` drops toward the low-24-V range, and `%Cap` later rises again. This is useful for the first calibration of an energy/SOC state model.

The current workbook does **not** contain a `Maintenance_Required` ground-truth column. Therefore the starter does not pretend that a maintenance classifier has already been trained. Rule-based health flags are separate from any future ML target.

## Vendor parameters used in the twin

From the supplied Schneider Electric/APC product datasheet for the SUA1000I-IN:

- nominal input/output: 230 V AC, 1 phase;
- rated power: 670 W / 1000 VA;
- input limits: 151–302 V adjustable;
- nominal frequency: 50/60 Hz auto-sensing;
- UPS type: line-interactive;
- battery: internal lead-acid;
- battery recharge time: 3 h;
- battery charger: 88 W rated;
- specified operating ambient: 0–40 °C.

The project defaults also include monitoring thresholds such as 30% low-SOC and 80% high-load. These are project defaults for experimentation, **not** vendor specifications.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
streamlit run app.py
```

## Recommended next ML layer

Do not start with the maintenance classifier. First collect more operating cycles and create validated labels. Then use rolling/time-window features such as:

- SOC level and SOC slope;
- battery-voltage level and slope;
- load and load variability;
- UPS temperature, ambient temperature and thermal rise;
- frequency/output-voltage deviations;
- time spent at high load or low SOC.

A KNN model (as in the handwritten prototype) can then be added, but a chronological train/test split is preferable for a future-state prediction problem so that future observations do not leak into the training set.

## Suggested architecture after v1

```text
Telemetry CSV/XLSX
      |
      v
Data ingestion + quality checks
      |
      v
State estimator / digital twin
  |       |        |
  v       v        v
 SOC    Battery   Thermal
        voltage    state
  |       |        |
  +-------+--------+
          |
          v
      Health layer
          |
          +--> rule-based alarms
          |
          +--> ML residual/anomaly model
          |
          +--> Maintenance classifier / RUL (later)
```

The important design choice is to keep the physics/engineering state model separate from ML. That lets the twin remain interpretable even before enough labeled maintenance data exists.
