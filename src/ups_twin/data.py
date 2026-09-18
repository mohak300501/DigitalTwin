from __future__ import annotations

from pathlib import Path
import warnings
import pandas as pd

REQUIRED_COLUMNS = [
    "Date", "Time", "Vmin", "Vmax", "Vout", "Iout", "%Wout", "Freq",
    "%Cap", "Vbat", "TupsC", "%VAout", "T1ambC"
]


def _excel_time_to_timedelta(s: pd.Series) -> pd.Series:
    """Parse Excel day-fractions or clock strings to timedeltas from midnight."""
    out = pd.Series(pd.NaT, index=s.index, dtype="timedelta64[ns]")
    numeric = pd.to_numeric(s, errors="coerce")
    mask_num = numeric.notna()
    out.loc[mask_num] = pd.to_timedelta(numeric.loc[mask_num], unit="D")

    mask_text = ~mask_num
    if mask_text.any():
        parsed = pd.to_timedelta(s.loc[mask_text].astype(str), errors="coerce")
        # pandas may parse HH:MM:SS strings directly.
        out.loc[mask_text] = parsed
    return out


def load_telemetry(path: str | Path) -> tuple[pd.DataFrame, list[str]]:
    """Load the supplied UPS workbook and create a canonical time-ordered table.

    Important: the uploaded data contains mixed date encodings and rows are stored
    in descending time order. We therefore use the Time-of-day column for ordering
    and keep the raw Date column untouched rather than silently rewriting the source.
    """
    path = Path(path)
    df = pd.read_excel(path)
    warnings_out: list[str] = []

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing telemetry columns: {missing}")

    df = df[REQUIRED_COLUMNS].copy()
    df["time_of_day"] = _excel_time_to_timedelta(df["Time"])

    if df["time_of_day"].isna().any():
        bad = int(df["time_of_day"].isna().sum())
        warnings_out.append(f"Dropped {bad} row(s) with invalid Time values.")
        df = df.dropna(subset=["time_of_day"]).copy()

    # Check for suspiciously inconsistent date encodings, but do not overwrite them.
    date_as_text = df["Date"].astype(str).str.strip()
    if date_as_text.nunique(dropna=True) > 1:
        counts = date_as_text.value_counts(dropna=True)
        most_common = counts.index[0] if len(counts) else None
        warnings_out.append(
            "Date column has mixed encodings/values. The model uses Time-of-day for chronology "
            f"instead; most common raw Date is {most_common!r}."
        )

    df = df.sort_values("time_of_day").reset_index(drop=True)
    anchor_date = pd.Timestamp("2000-01-01")
    df["timestamp"] = anchor_date + df["time_of_day"]
    df["dt_h"] = df["timestamp"].diff().dt.total_seconds().div(3600).fillna(0.0)

    # Derived engineering variables.
    df["load_w"] = df["%Wout"] / 100.0 * 670.0
    df["load_va"] = df["%VAout"] / 100.0 * 1000.0
    df["power_factor_est"] = (df["load_w"] / df["load_va"].replace(0, float("nan"))).astype(float)
    df["thermal_delta_c"] = df["TupsC"] - df["T1ambC"]
    df["mains_available"] = df["Vmin"] > 0
    df["output_active"] = df["Vout"] > 0

    return df, warnings_out
