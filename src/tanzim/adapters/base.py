from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..schema import AdapterInfo, TelemetryPoint

_PERSIAN_ARABIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫٬", "01234567890123456789.,")

_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %I:%M %p",
)


def normalize_digits(text: str) -> str:
    return text.translate(_PERSIAN_ARABIC_DIGITS).strip()


def parse_float(raw: Any, decimal_comma: bool = False) -> float | None:
    if raw is None:
        return None
    text = normalize_digits(str(raw))
    if not text or text.lower() in {"na", "n/a", "nan", "null", "none", "-", "--", "bad", "uncertain"}:
        return None
    text = re.sub(r"\s*(kw|w|c|°c|%|m3/h|m3/hr)$", "", text, flags=re.IGNORECASE).strip()
    if decimal_comma and "," in text and "." not in text:
        text = text.replace(",", ".")
    elif "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text and re.match(r"^-?\d+,\d{1,3}$", text):
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_timestamp(raw: Any) -> datetime:
    text = normalize_digits(str(raw))
    if not text:
        raise ValueError("Empty timestamp")
    if re.fullmatch(r"\d{10}(\.\d+)?", text):
        return datetime.fromtimestamp(float(text), tz=timezone.utc).replace(tzinfo=None)
    if re.fullmatch(r"\d{13}", text):
        return datetime.fromtimestamp(float(text) / 1000.0, tz=timezone.utc).replace(tzinfo=None)

    iso_candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(iso_candidate)
        return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
    except ValueError:
        pass

    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized timestamp format: {raw!r}")


def detect_delimiter(header_line: str) -> str:
    for delim in (";", ",", "\t"):
        if delim in header_line and len(header_line.split(delim)) >= 2:
            return delim
    return ","


def infer_power_scale(power_col_name: str) -> float:
    low = power_col_name.lower()
    if any(tok in low for tok in ("(mw)", "_mw", " mw")):
        return 1000.0
    if any(tok in low for tok in ("(w)", "[w]", "_w", "_watt", "watts")) and "kw" not in low:
        return 0.001
    return 1.0


def match_columns(fieldnames: list[str], patterns: dict[str, tuple[str, ...]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    cleaned = [(c, re.sub(r"\s+", " ", c.strip().lower())) for c in fieldnames if c]
    for canonical, regexes in patterns.items():
        for rx in regexes:
            compiled = re.compile(rx, flags=re.IGNORECASE)
            for orig, low in cleaned:
                if compiled.search(low):
                    mapping[canonical] = orig
                    break
            if canonical in mapping:
                break
    return mapping


def parse_csv_with_preamble(
    path: Path,
    adapter_name: str,
    column_patterns: dict[str, tuple[str, ...]],
    header_markers: tuple[str, ...],
    max_preamble_lines: int = 25,
) -> tuple[list[TelemetryPoint], AdapterInfo]:
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    header_idx = 0
    delimiter = ","

    for idx, line in enumerate(lines[:max_preamble_lines]):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cand_delim = detect_delimiter(stripped)
        cols = [c.strip().strip('"').lower() for c in stripped.split(cand_delim)]
        if len(cols) >= 2 and any(any(m in c for m in header_markers) for c in cols):
            header_idx = idx
            delimiter = cand_delim
            break

    data_lines = lines[header_idx:]
    if not data_lines:
        raise ValueError(f"No tabular data found in {path}")

    reader = csv.DictReader(data_lines, delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError(f"Empty CSV header in {path}")

    col_map = match_columns(list(reader.fieldnames), column_patterns)
    has_split_dt = "date" in col_map and "time" in col_map
    if ("timestamp" not in col_map and not has_split_dt) or "power_kw" not in col_map:
        raise ValueError(
            f"Adapter '{adapter_name}' could not resolve required timestamp and power columns "
            f"from headers {reader.fieldnames!r} (resolved={col_map})."
        )

    power_scale = infer_power_scale(col_map["power_kw"])
    dec_comma = delimiter == ";"
    points: list[TelemetryPoint] = []

    for row in reader:
        if not row:
            continue
        if "timestamp" in col_map:
            raw_ts = row.get(col_map["timestamp"])
        else:
            d_part = (row.get(col_map["date"]) or "").strip()
            t_part = (row.get(col_map["time"]) or "").strip()
            raw_ts = f"{d_part} {t_part}".strip()

        raw_kw = parse_float(row.get(col_map["power_kw"]), decimal_comma=dec_comma)
        if not raw_ts or raw_kw is None:
            continue

        try:
            ts = parse_timestamp(raw_ts)
        except ValueError:
            continue

        def opt(name: str) -> float | None:
            src = col_map.get(name)
            return parse_float(row.get(src), decimal_comma=dec_comma) if src else None

        points.append(
            TelemetryPoint(
                timestamp=ts,
                power_kw=round(raw_kw * power_scale, 4),
                outdoor_temp_c=opt("outdoor_temp_c"),
                supply_air_temp_c=opt("supply_air_temp_c"),
                chilled_water_supply_c=opt("chilled_water_supply_c"),
                chilled_water_return_c=opt("chilled_water_return_c"),
                heating_valve_pct=opt("heating_valve_pct"),
                cooling_valve_pct=opt("cooling_valve_pct"),
                gas_m3_hr=opt("gas_m3_hr"),
            )
        )

    points.sort(key=lambda p: p.timestamp)
    info = AdapterInfo(
        adapter=adapter_name,
        delimiter=delimiter,
        skipped_preamble_lines=header_idx,
        power_unit_scale=power_scale,
        resolved_columns=col_map,
    )
    return points, info
