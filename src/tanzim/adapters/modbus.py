from __future__ import annotations

from pathlib import Path

from ..schema import AdapterInfo, TelemetryPoint
from .base import parse_csv_with_preamble

MODBUS_PATTERNS: dict[str, tuple[str, ...]] = {
    "timestamp": (r"unix|epoch|timestamp|ts|date.?time|time_utc|log_time",),
    "date": (r"^date$",),
    "time": (r"^time$",),
    "power_kw": (
        r"(reg_?|hr_?|ir_?)?40001",
        r"p_tot|p_active|active_p|power_w|power_kw|tot_kw|tot_w",
    ),
    "outdoor_temp_c": (r"(reg_?|hr_?|ir_?)?30001|oat|t_amb|t_out",),
    "supply_air_temp_c": (r"(reg_?|hr_?|ir_?)?30004|t_sa|sat",),
    "chilled_water_supply_c": (r"(reg_?|hr_?|ir_?)?30002|chws|t_chws",),
    "chilled_water_return_c": (r"(reg_?|hr_?|ir_?)?30003|chwr|t_chwr",),
    "heating_valve_pct": (r"(reg_?|hr_?|ir_?)?40011|heat_vlv|htg_vlv|hw_v",),
    "cooling_valve_pct": (r"(reg_?|hr_?|ir_?)?40010|cool_vlv|clg_vlv|cw_v",),
    "gas_m3_hr": (r"(reg_?|hr_?|ir_?)?30010|gas_m3|gas_flow",),
}


def can_parse(sample_text: str) -> bool:
    low = sample_text.lower()
    if any(tok in low for tok in ("modbus", "slave_id", "unit_id", "reg_40001", "hr40001", "hr_40001", "40001_")):
        return True
    if any(tok in low for tok in ("epoch", "unix_ts")) and any(tok in low for tok in ("p_tot", "power_w", "power_kw")):
        return True
    return False


def load_modbus_csv(path: Path) -> tuple[list[TelemetryPoint], AdapterInfo]:
    """Parse industrial Modbus-RTU/TCP PLC & meter logger CSVs (register names, Unix epochs, W->kW, Persian digits)."""
    return parse_csv_with_preamble(
        path=path,
        adapter_name="modbus_logger",
        column_patterns=MODBUS_PATTERNS,
        header_markers=("epoch", "unix", "timestamp", "time", "40001", "slave"),
    )
