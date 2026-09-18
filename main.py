from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from ups_twin import DigitalTwin, TwinConfig, load_telemetry, assess_health

DATA = ROOT / "data" / "ups_telemetry.xlsx"

def main():
    df, warnings = load_telemetry(DATA)
    twin = DigitalTwin(TwinConfig()).fit(df)
    fitted = twin.predict_observed(df)
    latest = fitted.iloc[-1]

    print("=== UPS DIGITAL TWIN ===")
    print(f"Samples: {len(df)}")
    print(f"Time span: {df['timestamp'].min()} -> {df['timestamp'].max()}")
    print(f"Calibrated usable battery energy: {twin.usable_battery_kwh:.3f} kWh")
    print(f"Calibrated recharge rate: {twin.recharge_pct_per_hour:.1f} %/h")
    print("\nLatest observed state:")
    print(f"  SOC:      {latest['%Cap']:.1f} %")
    print(f"  Vbat:     {latest['Vbat']:.2f} V")
    print(f"  Load:     {latest['%Wout']:.1f} % ({latest['load_w']:.1f} W)")
    print(f"  Tups:     {latest['TupsC']:.1f} °C")
    print(f"  Ambient:  {latest['T1ambC']:.1f} °C")

    health = assess_health({
        "soc_pct": latest["%Cap"],
        "load_pct": latest["%Wout"],
        "ambient_c": latest["T1ambC"],
        "Vbat": latest["Vbat"],
    })
    print(f"  Health:   {health['severity']}")
    print(f"  Flags:    {', '.join(health['flags'])}")

    if warnings:
        print("\nData warnings:")
        for w in warnings:
            print(f"  - {w}")

if __name__ == "__main__":
    main()
