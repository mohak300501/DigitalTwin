from __future__ import annotations

from dataclasses import asdict
import numpy as np
import pandas as pd
from .config import TwinConfig


def _fit_linear(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    X1 = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(X1, y, rcond=None)
    return beta


def _predict_linear(beta: np.ndarray, X: np.ndarray) -> np.ndarray:
    X1 = np.column_stack([np.ones(len(X)), X])
    return X1 @ beta


class DigitalTwin:
    """A first-generation hybrid UPS twin.

    The state model is intentionally transparent:
      - battery SOC evolves from measured load and calibrated usable energy;
      - battery voltage is a calibrated telemetry surrogate;
      - UPS temperature is a calibrated ambient/load surrogate;
      - vendor electrical/thermal ranges remain explicit constraints.

    This is a calibrated engineering model, not a first-principles electrochemical model.
    """

    def __init__(self, config: TwinConfig | None = None):
        self.cfg = config or TwinConfig()
        self.fitted = False
        self.usable_battery_kwh = self.cfg.fallback_usable_battery_kwh
        self.recharge_pct_per_hour = 100.0 / self.cfg.vendor_recharge_hours
        self.vbat_beta = None
        self.temp_beta = None
        self.baseline_stats: dict[str, dict[str, float]] = {}
        self.fit_summary: dict[str, float] = {}

    def fit(self, df: pd.DataFrame) -> "DigitalTwin":
        d = df.copy()
        d = d.sort_values("timestamp").reset_index(drop=True)

        # Estimate effective usable energy from intervals where SOC falls.
        delta_soc = d["%Cap"].diff()
        discharge = (delta_soc < 0) & (d["load_w"] > 0) & (d["dt_h"] > 0)
        energy_kwh = float((d.loc[discharge, "load_w"] * d.loc[discharge, "dt_h"]).sum() / 1000.0)
        soc_drop = float((-delta_soc.loc[discharge]).sum())
        if energy_kwh > 0 and soc_drop > 0:
            self.usable_battery_kwh = energy_kwh / (soc_drop / 100.0)

        # Estimate recharge rate from intervals where SOC rises while mains is available.
        recharge = (delta_soc > 0) & (d["mains_available"]) & (d["dt_h"] > 0)
        hours = float(d.loc[recharge, "dt_h"].sum())
        gained = float(delta_soc.loc[recharge].sum())
        if hours > 0 and gained > 0:
            self.recharge_pct_per_hour = gained / hours

        # Battery voltage surrogate: Vbat ~ SOC + load.
        valid_v = d[["Vbat", "%Cap", "%Wout"]].dropna()
        self.vbat_beta = _fit_linear(
            valid_v["Vbat"].to_numpy(float),
            valid_v[["%Cap", "%Wout"]].to_numpy(float),
        )

        # Thermal surrogate: Tups ~ ambient + load.
        valid_t = d[["TupsC", "T1ambC", "%Wout"]].dropna()
        self.temp_beta = _fit_linear(
            valid_t["TupsC"].to_numpy(float),
            valid_t[["T1ambC", "%Wout"]].to_numpy(float),
        )

        for col in ["Vbat", "TupsC", "T1ambC", "%Wout", "%Cap", "Freq", "thermal_delta_c"]:
            s = pd.to_numeric(d[col], errors="coerce").dropna()
            if len(s) > 1:
                self.baseline_stats[col] = {"mean": float(s.mean()), "std": float(s.std(ddof=1) or 1.0)}

        self.fit_summary = {
            "usable_battery_kwh": float(self.usable_battery_kwh),
            "recharge_pct_per_hour": float(self.recharge_pct_per_hour),
            "vendor_recharge_hours": float(self.cfg.vendor_recharge_hours),
            "samples": float(len(d)),
        }
        self.fitted = True
        return self

    def predict_observed(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self.fitted:
            raise RuntimeError("Call fit() before predict_observed().")
        out = df.copy()
        out["Vbat_twin"] = _predict_linear(
            self.vbat_beta,
            out[["%Cap", "%Wout"]].to_numpy(float),
        )
        out["Tups_twin"] = _predict_linear(
            self.temp_beta,
            out[["T1ambC", "%Wout"]].to_numpy(float),
        )
        out["Vbat_residual"] = out["Vbat"] - out["Vbat_twin"]
        out["Tups_residual"] = out["TupsC"] - out["Tups_twin"]
        return out

    def step(
        self,
        soc_pct: float,
        load_pct: float,
        ambient_c: float,
        dt_minutes: float,
        mains_available: bool,
    ) -> dict[str, float | str | bool]:
        if not self.fitted:
            raise RuntimeError("Call fit() before step().")

        dt_h = max(float(dt_minutes), 0.0) / 60.0
        load_pct = float(np.clip(load_pct, 0.0, 100.0))
        soc_pct = float(np.clip(soc_pct, 0.0, 100.0))
        load_w = load_pct / 100.0 * self.cfg.rated_w

        if mains_available:
            soc_next = min(100.0, soc_pct + self.recharge_pct_per_hour * dt_h)
        else:
            soc_next = max(
                0.0,
                soc_pct - (load_w * dt_h / max(self.usable_battery_kwh, 1e-9)) * 100.0,
            )

        vbat = float(_predict_linear(self.vbat_beta, np.array([[soc_next, load_pct]]))[0])
        tups = float(_predict_linear(self.temp_beta, np.array([[ambient_c, load_pct]]))[0])
        output_active = load_pct > 0
        output_v = self.cfg.nominal_output_v if output_active else 0.0
        freq = self.cfg.nominal_freq_hz

        mode = "Mains" if mains_available else "Battery"
        return {
            "soc_pct": soc_next,
            "load_pct": load_pct,
            "load_w": load_w,
            "ambient_c": float(ambient_c),
            "TupsC": tups,
            "Vbat": vbat,
            "Vout": output_v,
            "Freq": freq,
            "mains_available": mains_available,
            "mode": mode,
        }

    def simulate_outage(
        self,
        start_soc_pct: float,
        load_pct: float,
        ambient_c: float,
        duration_minutes: int,
        step_minutes: int = 3,
    ) -> pd.DataFrame:
        if duration_minutes <= 0:
            return pd.DataFrame()
        state = []
        soc = float(start_soc_pct)
        for minute in range(0, duration_minutes + 1, step_minutes):
            row = self.step(
                soc_pct=soc,
                load_pct=load_pct,
                ambient_c=ambient_c,
                dt_minutes=0 if minute == 0 else step_minutes,
                mains_available=False,
            )
            row["elapsed_min"] = minute
            state.append(row)
            soc = float(row["soc_pct"])
            if soc <= 0:
                break
        return pd.DataFrame(state)

    def to_dict(self) -> dict:
        return {"config": asdict(self.cfg), "fit_summary": self.fit_summary}
