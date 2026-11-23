from __future__ import annotations

from pathlib import Path

from ..schema import AdapterInfo, TelemetryPoint
from .base import parse_csv_with_preamble

SCHNEIDER_PATTERNS: dict[str, tuple[str, ...]] = {
    "timestamp": (r"^date/time", r"^timestamp", r"^local.?time", r"^time.?stamp"),
    "date": (r"^date$",),
    "time": (r"^time$",),
    "power_kw": (
        r"active power total",
        r"real power",
        r"active power",
        r"total.*kw",
        r"power.*\(k?w\)",
    ),
    "outdoor_temp_c": (r"outside air temp", r"outdoor.*temp", r"ambient.*temp", r"\boat\b"),
    "supply_air_temp_c": (r"supply air temp", r"discharge air temp", r"\bsat\b"),
    "chilled_water_supply_c": (r"chw supply", r"chilled water supply", r"\bchws\b"),
    "chilled_water_return_c": (r"chw return", r"chilled water return", r"\bchwr\b"),
    "heating_valve_pct": (r"heating valve", r"htg valve", r"hw valve"),
    "cooling_valve_pct": (r"cooling valve", r"clg valve", r"cw valve"),
    "gas_m3_hr": (r"gas.*\(m3", r"natural gas", r"gas flow"),
}


def can_parse(sample_text: str) -> bool:
    low = sample_text.lower()
    if any(tok in low for tok in ("ecostruxure", "schneider", "power monitoring expert", "struxureware")):
        return True
    if "date/time" in low and ("active power" in low or "real power" in low):
        return True
    return False


def load_schneider_csv(path: Path) -> tuple[list[TelemetryPoint], AdapterInfo]:
    """Parse Schneider EcoStruxure Building Operation / PME CSV exports (auto-converts Watts to kW)."""
    return parse_csv_with_preamble(
        path=path,
        adapter_name="schneider_ecostruxure",
        column_patterns=SCHNEIDER_PATTERNS,
        header_markers=("date/time", "timestamp", "local time"),
    )
