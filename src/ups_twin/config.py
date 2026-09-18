from dataclasses import dataclass

@dataclass
class TwinConfig:
    # Vendor/product parameters from the supplied APC/Schneider datasheet.
    rated_w: float = 670.0
    rated_va: float = 1000.0
    input_v_min: float = 151.0
    input_v_max: float = 302.0
    nominal_output_v: float = 230.0
    nominal_freq_hz: float = 50.0
    ambient_min_c: float = 0.0
    ambient_max_c: float = 40.0
    vendor_recharge_hours: float = 3.0

    # Model/monitoring thresholds. These are project defaults, not vendor limits.
    low_soc_pct: float = 30.0
    critical_soc_pct: float = 15.0
    high_load_pct: float = 80.0
    overload_risk_pct: float = 90.0

    # Fallback only if the telemetry contains no usable discharge interval.
    fallback_usable_battery_kwh: float = 0.15
