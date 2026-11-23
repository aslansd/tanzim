from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class TelemetryPoint:
    timestamp: datetime
    power_kw: float
    outdoor_temp_c: float | None = None
    supply_air_temp_c: float | None = None
    chilled_water_supply_c: float | None = None
    chilled_water_return_c: float | None = None
    heating_valve_pct: float | None = None
    cooling_valve_pct: float | None = None
    gas_m3_hr: float | None = None


@dataclass(frozen=True)
class Finding:
    code: str
    title: str
    severity: Severity
    summary: str
    estimated_waste_kwh: float = 0.0
    estimated_cost_irr: float = 0.0
    start_time: str | None = None
    end_time: str | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data


@dataclass(frozen=True)
class AuditConfig:
    occupied_start_hour: int = 8
    occupied_end_hour: int = 17
    night_start_hour: int = 0
    night_end_hour: int = 5
    # Iran weekends: Friday (weekday() == 4) and optionally Thursday afternoon
    weekend_weekdays: tuple[int, ...] = (4,)
    simultaneous_valve_pct: float = 15.0
    simultaneous_min_hours: float = 1.0
    phantom_baseload_ratio: float = 0.45
    phantom_target_ratio: float = 0.25
    flatline_min_hours: float = 2.0
    low_delta_t_c: float = 2.5
    low_delta_t_min_fraction: float = 0.20
    active_plant_kw_floor: float = 15.0
    changepoint_min_z: float = 3.5
    changepoint_min_delta_kw: float = 10.0
    short_cycle_max_per_hour: int = 4
    short_cycle_min_swing_kw: float = 25.0
    contracted_demand_kw: float | None = None
    peak_to_mid_ratio_limit: float = 1.30
    base_kwh_price_irr: float = 12_000.0  # Configurable commercial/industrial IRR/kWh

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuditReport:
    tool_version: str
    audited_at_utc: str
    source_path: str
    source_sha256: str
    config_sha256: str
    record_count: int
    timestep_hours: float
    total_energy_kwh: float
    peak_energy_kwh: float
    total_estimated_waste_kwh: float
    total_estimated_cost_irr: float
    findings: list[Finding]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_version": self.tool_version,
            "audited_at_utc": self.audited_at_utc,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "config_sha256": self.config_sha256,
            "record_count": self.record_count,
            "timestep_hours": round(self.timestep_hours, 4),
            "total_energy_kwh": round(self.total_energy_kwh, 2),
            "peak_energy_kwh": round(self.peak_energy_kwh, 2),
            "total_estimated_waste_kwh": round(self.total_estimated_waste_kwh, 2),
            "total_estimated_cost_irr": round(self.total_estimated_cost_irr, 0),
            "findings": [f.to_dict() for f in self.findings],
        }