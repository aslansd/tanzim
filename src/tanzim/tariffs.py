from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TariffWindow:
    peak_hours: tuple[int, int]      # [start, end)
    off_peak_hours: tuple[int, int]  # [start, end)


@dataclass(frozen=True)
class IranTariffProfile:
    """Configurable seasonal Time-of-Use (ToU) schedule for Iranian commercial/industrial meters."""

    spring: TariffWindow = TariffWindow(peak_hours=(21, 22), off_peak_hours=(1, 9))
    summer: TariffWindow = TariffWindow(peak_hours=(14, 18), off_peak_hours=(3, 8))
    autumn: TariffWindow = TariffWindow(peak_hours=(18, 21), off_peak_hours=(1, 9))
    winter: TariffWindow = TariffWindow(peak_hours=(18, 21), off_peak_hours=(1, 9))

    peak_multiplier: float = 2.5
    mid_multiplier: float = 1.0
    off_peak_multiplier: float = 0.5

    def season_for(self, ts: datetime) -> str:
        m = ts.month
        if m in (3, 4, 5):
            return "spring"
        if m in (6, 7, 8):
            return "summer"
        if m in (9, 10, 11):
            return "autumn"
        return "winter"

    def period_for(self, ts: datetime) -> str:
        window: TariffWindow = getattr(self, self.season_for(ts))
        h = ts.hour
        p_start, p_end = window.peak_hours
        o_start, o_end = window.off_peak_hours
        if p_start <= h < p_end:
            return "peak"
        if o_start <= h < o_end:
            return "off_peak"
        return "mid_peak"

    def multiplier_for(self, ts: datetime) -> float:
        period = self.period_for(ts)
        if period == "peak":
            return self.peak_multiplier
        if period == "off_peak":
            return self.off_peak_multiplier
        return self.mid_multiplier