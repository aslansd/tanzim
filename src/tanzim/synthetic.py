from __future__ import annotations

import csv
import math
import random
from datetime import datetime, timedelta
from pathlib import Path

from .schema import TelemetryPoint


def generate_tehran_summer_bms(
    days: int = 14,
    step_minutes: int = 10,
    inject_faults: bool = True,
    seed: int = 42,
) -> list[TelemetryPoint]:
    """Generate realistic Tehran summer commercial chiller/BMS telemetry."""
    rng = random.Random(seed)
    start = datetime(2026, 7, 1, 0, 0, 0)
    total_steps = int((days * 24 * 60) / step_minutes)
    points: list[TelemetryPoint] = []

    for i in range(total_steps):
        ts = start + timedelta(minutes=i * step_minutes)
        day_idx = (ts - start).days
        hour_f = ts.hour + ts.minute / 60.0

        # Tehran July outdoor temperature cycle (~24C at 05:00 -> ~39C at 15:30)
        oat = 31.5 - 7.5 * math.cos(2 * math.pi * (hour_f - 4.0) / 24.0) + rng.gauss(0, 0.3)

        occupied = (ts.weekday() != 4) and (8 <= ts.hour < 17)
        base_kw = 22.0 + rng.gauss(0, 0.8)
        cooling_kw = max(0.0, (oat - 18.0) * 4.2) if occupied else 0.0
        occ_internal_kw = 28.0 if occupied else 0.0
        power_kw = base_kw + cooling_kw + occ_internal_kw

        sat = 13.5 + rng.gauss(0, 0.25)
        chws = 7.2 + rng.gauss(0, 0.12)
        chwr = chws + (5.8 if occupied else 1.2) + rng.gauss(0, 0.15)
        heat_v = 0.0
        cool_v = min(100.0, max(0.0, (oat - 18.0) * 4.0)) if occupied else 0.0

        if inject_faults:
            # 1. Simultaneous heat/cool on Days 3-4 (09:00-15:00)
            if day_idx in (3, 4) and 9 <= ts.hour < 15:
                heat_v = 45.0
                cool_v = 82.0
                power_kw += 24.0

            # 2. Frozen supply-air temperature sensor on Day 5 (08:00-14:00)
            if day_idx == 5 and 8 <= ts.hour < 14:
                sat = 13.40

            # 3. Persistent +38 kW regime shift + phantom night baseload from Day 7 onward
            if day_idx >= 7:
                power_kw += 38.0
                if 0 <= ts.hour < 5:
                    power_kw += 36.0  # Chiller/AHU left in manual hand mode overnight

            # 4. Low Delta-T syndrome on Days 9-12
            if day_idx in (9, 10, 11, 12) and occupied:
                chwr = chws + 1.6 + rng.gauss(0, 0.08)

            # 5. Severe summer peak overload (14:00-18:00) from Day 8 onward
            if day_idx >= 8 and 14 <= ts.hour < 18:
                power_kw += 55.0

            # 6. Rapid compressor short-cycling on Day 12 (10:00-11:00) -> 6 cycles/hr at 10-min step?
            # Use 10-min step: alternating ON/OFF every sample gives 3 starts; let's inject on 5-min or flag >=3
            if day_idx == 12 and 10 <= ts.hour < 12:
                power_kw = 155.0 if (i % 2 == 0) else 25.0

        points.append(
            TelemetryPoint(
                timestamp=ts,
                power_kw=round(max(0.0, power_kw), 2),
                outdoor_temp_c=round(oat, 2),
                supply_air_temp_c=round(sat, 2),
                chilled_water_supply_c=round(chws, 2),
                chilled_water_return_c=round(chwr, 2),
                heating_valve_pct=round(heat_v, 1),
                cooling_valve_pct=round(cool_v, 1),
            )
        )
    return points


def write_telemetry_csv(points: list[TelemetryPoint], path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "timestamp",
        "power_kw",
        "outdoor_temp_c",
        "supply_air_temp_c",
        "chilled_water_supply_c",
        "chilled_water_return_c",
        "heating_valve_pct",
        "cooling_valve_pct",
    ]
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for p in points:
            writer.writerow(
                {
                    "timestamp": p.timestamp.isoformat(),
                    "power_kw": p.power_kw,
                    "outdoor_temp_c": p.outdoor_temp_c,
                    "supply_air_temp_c": p.supply_air_temp_c,
                    "chilled_water_supply_c": p.chilled_water_supply_c,
                    "chilled_water_return_c": p.chilled_water_return_c,
                    "heating_valve_pct": p.heating_valve_pct,
                    "cooling_valve_pct": p.cooling_valve_pct,
                }
            )
    return out