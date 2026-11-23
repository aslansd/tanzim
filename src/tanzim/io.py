from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .schema import TelemetryPoint

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "timestamp": ("timestamp", "time", "datetime", "ts", "date_time"),
    "power_kw": ("power_kw", "kw", "active_power_kw", "load_kw", "elec_kw"),
    "outdoor_temp_c": ("outdoor_temp_c", "oat", "t_out", "ambient_temp_c"),
    "supply_air_temp_c": ("supply_air_temp_c", "sat", "t_sa"),
    "chilled_water_supply_c": ("chilled_water_supply_c", "chws", "chw_supply_c"),
    "chilled_water_return_c": ("chilled_water_return_c", "chwr", "chw_return_c"),
    "heating_valve_pct": ("heating_valve_pct", "hw_valve", "heat_valve_pct"),
    "cooling_valve_pct": ("cooling_valve_pct", "cw_valve", "cool_valve_pct"),
    "gas_m3_hr": ("gas_m3_hr", "gas_flow", "gas_m3h"),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_dict(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _parse_float(raw: Any) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if text == "" or text.lower() in {"na", "nan", "null", "none"}:
        return None
    return float(text)


def _parse_ts(raw: str) -> datetime:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _resolve_columns(fieldnames: list[str]) -> dict[str, str]:
    lowered = {c.strip().lower(): c for c in fieldnames}
    mapping: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[canonical] = lowered[alias]
                break
    return mapping


def _row_to_point(row: dict[str, Any], col_map: dict[str, str]) -> TelemetryPoint | None:
    ts_raw = row.get(col_map["timestamp"])
    kw_raw = _parse_float(row.get(col_map["power_kw"]))
    if not ts_raw or kw_raw is None:
        return None

    def opt(field_name: str) -> float | None:
        src = col_map.get(field_name)
        return _parse_float(row.get(src)) if src else None

    return TelemetryPoint(
        timestamp=_parse_ts(str(ts_raw)),
        power_kw=kw_raw,
        outdoor_temp_c=opt("outdoor_temp_c"),
        supply_air_temp_c=opt("supply_air_temp_c"),
        chilled_water_supply_c=opt("chilled_water_supply_c"),
        chilled_water_return_c=opt("chilled_water_return_c"),
        heating_valve_pct=opt("heating_valve_pct"),
        cooling_valve_pct=opt("cooling_valve_pct"),
        gas_m3_hr=opt("gas_m3_hr"),
    )


def load_telemetry(path: str | Path) -> list[TelemetryPoint]:
    p = Path(path)
    suffix = p.suffix.lower()
    rows: list[dict[str, Any]] = []

    if suffix == ".csv":
        with p.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise ValueError(f"Empty CSV header in {p}")
            col_map = _resolve_columns(list(reader.fieldnames))
            rows = list(reader)
    elif suffix in {".jsonl", ".ndjson"}:
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
        if not rows:
            raise ValueError(f"No records found in {p}")
        col_map = _resolve_columns(list(rows[0].keys()))
    else:
        raise ValueError(f"Unsupported telemetry format '{suffix}'. Use .csv or .jsonl.")

    if "timestamp" not in col_map or "power_kw" not in col_map:
        raise ValueError(
            "Telemetry must contain timestamp and power_kw columns "
            f"(resolved: {list(col_map.keys())})."
        )

    points = [pt for row in rows if (pt := _row_to_point(row, col_map)) is not None]
    points.sort(key=lambda x: x.timestamp)
    return points