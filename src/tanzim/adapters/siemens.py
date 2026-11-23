from __future__ import annotations

from pathlib import Path

from ..schema import AdapterInfo, TelemetryPoint
from .base import parse_csv_with_preamble

SIEMENS_PATTERNS: dict[str, tuple[str, ...]] = {
    "timestamp": (r"^date.?time$", r"^timestamp$", r"^time.?stamp$", r"^zeitstempel$"),
    "date": (r"^date$", r"^datum$"),
    "time": (r"^time$", r"^uhrzeit$"),
    "power_kw": (
        r"(active|elec|total|chiller|plant|main).*power",
        r"\.pwr|pwr_kw|power_kw|kw_tot|p_act",
        r"\bkw\b|\(kw\)|\(w\)",
    ),
    "outdoor_temp_c": (r"oat|outside.?air|outdoor.?temp|amb.?temp|aussentemp",),
    "supply_air_temp_c": (r"sat|sup.?air|supply.?air|zuluft",),
    "chilled_water_supply_c": (r"chws|chw.?sup|chilled.*sup|vorlauf",),
    "chilled_water_return_c": (r"chwr|chw.?ret|chilled.*ret|ruecklauf|rücklauf",),
    "heating_valve_pct": (r"htg.?vlv|heat.?vlv|heating.*valve|hw.?valve|heizventil",),
    "cooling_valve_pct": (r"clg.?vlv|cool.?vlv|cooling.*valve|cw.?valve|kuehlventil|kühlventil",),
    "gas_m3_hr": (r"gas.*flow|gas_m3|gasverbrauch",),
}


def can_parse(sample_text: str) -> bool:
    low = sample_text.lower()
    if any(tok in low for tok in ("desigo", "siemens", "trend definition", "apogee", "insight")):
        return True
    if ";" in sample_text and any(tok in low for tok in ("htgvlv", "clgvlv", "chw_sup", "date;time", "datum;uhrzeit")):
        return True
    return False


def load_siemens_csv(path: Path) -> tuple[list[TelemetryPoint], AdapterInfo]:
    """Parse Siemens Desigo CC / Insight BMS CSV exports (handles metadata preamble, ';' delimiter, and DD.MM.YYYY)."""
    return parse_csv_with_preamble(
        path=path,
        adapter_name="siemens_desigo",
        column_patterns=SIEMENS_PATTERNS,
        header_markers=("date", "datum", "timestamp", "time"),
    )
