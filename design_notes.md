# Digital Twin Design Notes

## 1. State variables

Core states:

- `soc_pct`: battery state of charge, initialized from `%Cap`.
- `vbat`: battery-bank voltage, calibrated from `%Cap` and `%Wout`.
- `tups_c`: UPS temperature, calibrated from ambient temperature and load.
- `load_pct`: `%Wout`, converted to watts using the 670 W rating.
- `mains_available`: inferred from telemetry as `Vmin > 0` for this dataset.

Derived:

- apparent power from `%VAout` and 1000 VA;
- estimated power factor = W / VA when VA > 0;
- thermal rise = `TupsC - T1ambC`;
- output active state from `Vout > 0`.

## 2. Battery energy model

During a discharge interval:

`E_step = P_load * dt`

and the effective usable battery energy is estimated from the observed SOC drop:

`E_usable = sum(E_step) / (SOC_drop / 100)`

This is an empirical system-level parameter. It should not be confused with the battery's nameplate Ah/Wh rating because the product datasheet supplied for this project does not specify that value.

## 3. Scenario model

For a battery outage:

`SOC(t+dt) = SOC(t) - P_load * dt / E_usable`

where SOC is expressed as a fraction in the equation and clipped to 0–100% in the implementation.

For mains operation, SOC is advanced using a calibrated recharge rate when the data contains recharge observations; otherwise the code falls back to the vendor 3 h recharge time.

## 4. Thermal surrogate

The first model is deliberately simple:

`Tups = beta0 + beta1 * Tambient + beta2 * load_pct`

This is not claimed to be a thermal finite-element model. Once more data are collected, replace this with a first-order heat-balance model or a state-space model.

## 5. ML extension

Possible progression:

### Stage A — anomaly detection

Train an unsupervised model on healthy windows only (e.g. Isolation Forest or One-Class SVM) using rolling features and residuals from the digital twin.

### Stage B — maintenance classification

Only after `Maintenance_Required` labels are validated by maintenance records, train KNN/logistic regression/tree-based models.

### Stage C — RUL / degradation

When multiple battery replacement cycles exist, move to remaining-useful-life or survival modeling.

## 6. What to collect next

The single uploaded day is useful for a proof of concept but is not enough for a trustworthy maintenance ML model. Aim for multiple events covering:

- normal mains operation;
- controlled battery discharge at multiple loads;
- recharge cycles;
- high ambient-temperature periods;
- transient input-voltage events;
- actual maintenance/replacement dates and reasons.
