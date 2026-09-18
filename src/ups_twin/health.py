from __future__ import annotations

from .config import TwinConfig


def assess_health(state: dict, cfg: TwinConfig | None = None) -> dict:
    cfg = cfg or TwinConfig()
    flags: list[str] = []
    severity = "NORMAL"

    def raise_level(level: str):
        nonlocal severity
        order = {"NORMAL": 0, "WATCH": 1, "WARNING": 2, "CRITICAL": 3}
        if order[level] > order[severity]:
            severity = level

    soc = float(state.get("soc_pct", 100.0))
    load_pct = float(state.get("load_pct", 0.0))
    ambient = float(state.get("ambient_c", state.get("T1ambC", 25.0)))
    vbat = float(state.get("Vbat", 0.0))

    if soc <= cfg.critical_soc_pct:
        flags.append("Critical battery state")
        raise_level("CRITICAL")
    elif soc <= cfg.low_soc_pct:
        flags.append("Low battery state")
        raise_level("WARNING")

    if load_pct >= cfg.overload_risk_pct:
        flags.append("Very high load")
        raise_level("WARNING")
    elif load_pct >= cfg.high_load_pct:
        flags.append("High load")
        raise_level("WATCH")

    if ambient > cfg.ambient_max_c or ambient < cfg.ambient_min_c:
        flags.append("Ambient outside specified operating range")
        raise_level("CRITICAL")

    # Vbat thresholds are intentionally relative to the calibrated telemetry range,
    # because the supplied datasheet does not specify a battery-bank voltage limit.
    if vbat < 24.0 and soc <= cfg.low_soc_pct:
        flags.append("Low battery voltage observed with low SOC")
        raise_level("WARNING")

    if not flags:
        flags.append("No rule-based issue detected")

    return {"severity": severity, "flags": flags}
