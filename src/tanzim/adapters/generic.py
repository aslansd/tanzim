from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schema import AdapterInfo, TelemetryPoint
from .base import infer_power_scale, match_columns, parse_csv_with_preamble, parse_float, parse_timestamp

GENERIC_PATTERNS: dict[str, tuple[str, ...]] = {
    "timestamp": (r"^timestamp$", r"^time$", r"^datetime$", r"^ts$", r"^date_time$"),
    "date": (r"^date$",),
    "time": (r"^time$",),
    "power_kw": (r"^power_kw$", r"^kw$", r"^active_power_kw$", r"^load_kw$", r"^elec_kw$", r"^power_w$"),
    "outdoor_temp_c": (r"^outdoor_temp_c$", r"^oat$", r"^t_out$", r"^ambient_temp_c$"),
    "supply_air_temp_c": (r"^supply_air_temp_c$", r"^sat$", r"^t_sa$"),
    "chilled_water_supply_c": (r"^chilled_water_supply_c$", r"^chws$", r"^chw_supply_c$"),
    "chilled_water_return_c": (r"^chilled_water_return_c$", r"^chwr$", r"^chw_return_c$"),
    "heating_valve_pct": (r"^heating_valve_pct$", r"^hw_valve$", r"^heat_valve_pct$"),
    "cooling_valve_pct": (r"^cooling_valve_pct$", r"^cw_valve$", r"^cool_valve_pct$"),
    "gas_m3_hr": (r"^gas_m3_hr$", r"^gas_flow$", r"^gas_m3h$"),
}


def load_generic_telemetry(path: Path) -> tuple[list[TelemetryPoint], AdapterInfo]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return parse_csv_with_preamble(
            path=path,
            adapter_name="generic_csv",
            column_patterns=GENERIC_PATTERNS,
            header_markers=("timestamp", "datetime", "time", "ts"),
            max_preamble_lines=5,
        )
    if suffix in {".jsonl", ".ndjson"}:
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        if not rows:
            raise ValueError(f"No records found in {path}")
        col_map = match_columns(list(rows[0].keys()), GENERIC_PATTERNS)
        if "timestamp" not in col_map or "power_kw" not in col_map:
            raise ValueError(f"JSONL must include timestamp and power_kw (resolved={col_map}).")
        scale = infer_power_scale(col_map["power_kw"])
        pts: list[TelemetryPoint] = []
        for row in rows:
            raw_ts = row.get(col_map["timestamp"])
            raw_kw = parse_float(row.get(col_map["power_kw"]))
            if not raw_ts or raw_kw is None:
                continue

            def opt(name: str) -> float | None:
                src = col_map.get(name)
                return parse_float(row.get(src)) if src else None

            pts.append(
                TelemetryPoint(
                    timestamp=parse_timestamp(raw_ts),
                    power_kw=round(raw_kw * scale, 4),
                    outdoor_temp_c=opt("outdoor_temp_c"),
                    supply_air_temp_c=opt("supply_air_temp_c"),
                    chilled_water_supply_c=opt("chilled_water_supply_c"),
                    chilled_water_return_c=opt("chilled_water_return_c"),
                    heating_valve_pct=opt("heating_valve_pct"),
                    cooling_valve_pct=opt("cooling_valve_pct"),
                    gas_m3_hr=opt("gas_m3_hr"),
                )
            )
        pts.sort(key=lambda p: p.timestamp)
        return pts, AdapterInfo(
            adapter="generic_jsonl",
            delimiter="jsonl",
            power_unit_scale=scale,
            resolved_columns=col_map,
        )
    raise ValueError(f"Unsupported telemetry format '{suffix}'. Use .csv or .jsonl.")
