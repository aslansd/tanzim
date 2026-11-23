from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from statistics import mean, median, variance

from .schema import AuditConfig, Finding, Severity, TelemetryPoint
from .tariffs import IranTariffProfile


def _is_occupied(p: TelemetryPoint, cfg: AuditConfig) -> bool:
    return (
        p.timestamp.weekday() not in cfg.weekend_weekdays
        and cfg.occupied_start_hour <= p.timestamp.hour < cfg.occupied_end_hour
    )


def infer_timestep_hours(points: list[TelemetryPoint]) -> float:
    if len(points) < 2:
        return 0.25
    deltas = [
        (points[i].timestamp - points[i - 1].timestamp).total_seconds() / 3600.0
        for i in range(1, len(points))
    ]
    positive = [d for d in deltas if d > 0]
    return median(positive) if positive else 0.25


def detect_simultaneous_heat_cool(
    points: list[TelemetryPoint],
    dt_h: float,
    cfg: AuditConfig,
    tariff: IranTariffProfile,
) -> list[Finding]:
    overlap_pts = [
        p
        for p in points
        if p.heating_valve_pct is not None
        and p.cooling_valve_pct is not None
        and p.heating_valve_pct >= cfg.simultaneous_valve_pct
        and p.cooling_valve_pct >= cfg.simultaneous_valve_pct
    ]
    overlap_hours = len(overlap_pts) * dt_h
    if overlap_hours < cfg.simultaneous_min_hours:
        return []

    waste_kwh = sum(p.power_kw * dt_h * 0.35 for p in overlap_pts)
    cost_irr = sum(
        p.power_kw * dt_h * 0.35 * cfg.base_kwh_price_irr * tariff.multiplier_for(p.timestamp)
        for p in overlap_pts
    )
    severity = Severity.CRITICAL if overlap_hours >= 4.0 else Severity.WARNING
    return [
        Finding(
            code="SIMULTANEOUS_HEAT_COOL",
            title="Simultaneous heating and cooling (valve fighting)",
            severity=severity,
            summary=(
                f"Heating and cooling valves were both open (>={cfg.simultaneous_valve_pct:.0f}%) "
                f"for {overlap_hours:.1f} hours across {len(overlap_pts)} intervals."
            ),
            estimated_waste_kwh=round(waste_kwh, 2),
            estimated_cost_irr=round(cost_irr, 0),
            start_time=overlap_pts[0].timestamp.isoformat(),
            end_time=overlap_pts[-1].timestamp.isoformat(),
            evidence={
                "overlap_hours": round(overlap_hours, 2),
                "max_heating_valve_pct": round(max(p.heating_valve_pct or 0.0 for p in overlap_pts), 1),
                "max_cooling_valve_pct": round(max(p.cooling_valve_pct or 0.0 for p in overlap_pts), 1),
            },
        )
    ]


def detect_phantom_baseload(
    points: list[TelemetryPoint],
    dt_h: float,
    cfg: AuditConfig,
    tariff: IranTariffProfile,
) -> list[Finding]:
    occ_kw = [p.power_kw for p in points if _is_occupied(p, cfg)]
    night_pts = [
        p
        for p in points
        if cfg.night_start_hour <= p.timestamp.hour < cfg.night_end_hour
    ]
    if len(occ_kw) < 4 or len(night_pts) < 4:
        return []

    med_occ = median(occ_kw)
    if med_occ <= 1.0:
        return []

    by_night: dict[date, list[TelemetryPoint]] = defaultdict(list)
    for p in night_pts:
        by_night[p.timestamp.date()].append(p)

    offending_nights: list[tuple[date, float]] = []
    offending_pts: list[TelemetryPoint] = []
    for d, pts in sorted(by_night.items()):
        if len(pts) < 2:
            continue
        m_night = median(p.power_kw for p in pts)
        if (m_night / med_occ) > cfg.phantom_baseload_ratio and m_night >= 5.0:
            offending_nights.append((d, m_night))
            offending_pts.extend(pts)

    if not offending_pts or (len(offending_nights) < 2 and len(offending_nights) < len(by_night)):
        return []

    med_bad_night = median(p.power_kw for p in offending_pts)
    ratio = med_bad_night / med_occ
    target_night_kw = med_occ * cfg.phantom_target_ratio
    waste_kwh = sum(max(0.0, p.power_kw - target_night_kw) * dt_h for p in offending_pts)
    cost_irr = sum(
        max(0.0, p.power_kw - target_night_kw)
        * dt_h
        * cfg.base_kwh_price_irr
        * tariff.multiplier_for(p.timestamp)
        for p in offending_pts
    )
    severity = Severity.CRITICAL if ratio >= 0.65 else Severity.WARNING
    return [
        Finding(
            code="PHANTOM_BASELOAD",
            title="Excessive unoccupied night baseload (schedule drift)",
            severity=severity,
            summary=(
                f"Median night load ({med_bad_night:.1f} kW) across "
                f"{len(offending_nights)}/{len(by_night)} nights is {ratio * 100:.0f}% of "
                f"daytime occupied median ({med_occ:.1f} kW), exceeding the "
                f"{cfg.phantom_baseload_ratio * 100:.0f}% threshold."
            ),
            estimated_waste_kwh=round(waste_kwh, 2),
            estimated_cost_irr=round(cost_irr, 0),
            start_time=offending_pts[0].timestamp.isoformat(),
            end_time=offending_pts[-1].timestamp.isoformat(),
            evidence={
                "affected_nights": len(offending_nights),
                "total_nights": len(by_night),
                "median_occupied_kw": round(med_occ, 2),
                "median_night_kw": round(med_bad_night, 2),
                "night_to_day_ratio": round(ratio, 3),
                "target_standby_kw": round(target_night_kw, 2),
            },
        )
    ]


def detect_sensor_flatline(
    points: list[TelemetryPoint],
    dt_h: float,
    cfg: AuditConfig,
) -> list[Finding]:
    channels = (
        "supply_air_temp_c",
        "chilled_water_supply_c",
        "chilled_water_return_c",
        "power_kw",
    )
    min_samples = max(4, int(math.ceil(cfg.flatline_min_hours / max(dt_h, 1e-6))))
    findings: list[Finding] = []

    for ch in channels:
        best_run: list[TelemetryPoint] = []
        current_run: list[TelemetryPoint] = []
        last_val: float | None = None
        last_ts = None

        for p in points:
            val = getattr(p, ch)
            active = p.power_kw >= cfg.active_plant_kw_floor
            gap_ok = (
                last_ts is None
                or ((p.timestamp - last_ts).total_seconds() / 3600.0) <= dt_h * 3.0
            )
            if val is not None and active and gap_ok and last_val is not None and abs(val - last_val) <= 1e-6:
                current_run.append(p)
            else:
                if len(current_run) > len(best_run):
                    best_run = current_run
                current_run = [p] if (val is not None and active) else []
            last_val = val
            last_ts = p.timestamp

        if len(current_run) > len(best_run):
            best_run = current_run

        if len(best_run) >= min_samples:
            dur_h = len(best_run) * dt_h
            frozen_val = getattr(best_run[0], ch)
            findings.append(
                Finding(
                    code="SENSOR_FLATLINE",
                    title=f"Frozen sensor / flatlined telemetry on '{ch}'",
                    severity=Severity.WARNING,
                    summary=(
                        f"Channel '{ch}' stayed locked at {frozen_val:.2f} for {dur_h:.1f} hours "
                        f"while plant load was active, risking blind PID control."
                    ),
                    start_time=best_run[0].timestamp.isoformat(),
                    end_time=best_run[-1].timestamp.isoformat(),
                    evidence={
                        "channel": ch,
                        "frozen_value": round(float(frozen_val), 3),
                        "duration_hours": round(dur_h, 2),
                        "sample_count": len(best_run),
                    },
                )
            )
    return findings


def detect_chiller_low_delta_t(
    points: list[TelemetryPoint],
    dt_h: float,
    cfg: AuditConfig,
    tariff: IranTariffProfile,
) -> list[Finding]:
    has_cooling_valve = any(p.cooling_valve_pct is not None for p in points)
    night_kw = [
        p.power_kw
        for p in points
        if cfg.night_start_hour <= p.timestamp.hour < cfg.night_end_hour
    ]
    standby_floor = (median(night_kw) + 15.0) if night_kw else cfg.active_plant_kw_floor
    active_floor = max(cfg.active_plant_kw_floor, standby_floor)

    active_chw: list[tuple[TelemetryPoint, float]] = []
    for p in points:
        if p.chilled_water_supply_c is None or p.chilled_water_return_c is None:
            continue
        plant_on = (
            (p.cooling_valve_pct or 0.0) >= 15.0
            if has_cooling_valve
            else p.power_kw >= active_floor
        )
        if plant_on and p.power_kw >= cfg.active_plant_kw_floor:
            active_chw.append((p, p.chilled_water_return_c - p.chilled_water_supply_c))

    if len(active_chw) < 8:
        return []

    low_pts = [(p, dt) for p, dt in active_chw if dt < cfg.low_delta_t_c]
    frac = len(low_pts) / len(active_chw)
    if frac < cfg.low_delta_t_min_fraction or len(low_pts) < 4:
        return []

    avg_low_dt = mean(dt for _, dt in low_pts)
    waste_kwh = sum(p.power_kw * dt_h * 0.15 for p, _ in low_pts)
    cost_irr = sum(
        p.power_kw * dt_h * 0.15 * cfg.base_kwh_price_irr * tariff.multiplier_for(p.timestamp)
        for p, _ in low_pts
    )
    severity = Severity.CRITICAL if frac >= 0.35 else Severity.WARNING
    return [
        Finding(
            code="CHILLER_LOW_DELTA_T",
            title="Chiller Low-Delta-T syndrome (over-pumping / coil fouling)",
            severity=severity,
            summary=(
                f"Chilled-water Delta-T fell below {cfg.low_delta_t_c:.1f} C during "
                f"{frac * 100:.1f}% of active cooling hours (mean low Delta-T = {avg_low_dt:.2f} C)."
            ),
            estimated_waste_kwh=round(waste_kwh, 2),
            estimated_cost_irr=round(cost_irr, 0),
            start_time=low_pts[0][0].timestamp.isoformat(),
            end_time=low_pts[-1][0].timestamp.isoformat(),
            evidence={
                "affected_fraction": round(frac, 3),
                "mean_low_delta_t_c": round(avg_low_dt, 2),
                "design_reference_delta_t_c": 5.5,
                "affected_hours": round(len(low_pts) * dt_h, 2),
            },
        )
    ]


def _weather_adjusted_residuals(points: list[TelemetryPoint]) -> list[float]:
    """Subtract linear cooling/heating degree dependence on outdoor temperature."""
    paired = [(i, p.outdoor_temp_c, p.power_kw) for i, p in enumerate(points) if p.outdoor_temp_c is not None]
    if len(paired) < len(points) * 0.8 or len(paired) < 10:
        avg_p = mean(p.power_kw for p in points)
        return [p.power_kw - avg_p for p in points]

    mean_oat = mean(t for _, t, _ in paired)
    cooling_mode = mean_oat >= 18.0
    xs = [max(0.0, t - 18.0) if cooling_mode else max(0.0, 16.0 - t) for _, t, _ in paired]
    ys = [kw for _, _, kw in paired]

    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx < 1e-6:
        return [p.power_kw - my for p in points]

    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    intercept = my - slope * mx

    residuals: list[float] = []
    for p in points:
        if p.outdoor_temp_c is None:
            residuals.append(0.0)
        else:
            x = max(0.0, p.outdoor_temp_c - 18.0) if cooling_mode else max(0.0, 16.0 - p.outdoor_temp_c)
            residuals.append(p.power_kw - (intercept + slope * x))
    return residuals


def detect_regime_changepoint(
    points: list[TelemetryPoint],
    dt_h: float,
    cfg: AuditConfig,
    tariff: IranTariffProfile,
) -> list[Finding]:
    residuals = _weather_adjusted_residuals(points)
    by_day: dict[date, list[float]] = defaultdict(list)
    for p, r in zip(points, residuals):
        by_day[p.timestamp.date()].append(r)

    days = sorted(by_day.keys())
    if len(days) < 6:
        return []

    daily_means = [mean(by_day[d]) for d in days]
    best_k: int | None = None
    best_score = 0.0
    best_delta = 0.0

    for k in range(2, len(days) - 1):
        before = daily_means[:k]
        after = daily_means[k:]
        delta = mean(after) - mean(before)
        if delta <= cfg.changepoint_min_delta_kw:
            continue
        v1 = variance(before) if len(before) > 1 else 0.0
        v2 = variance(after) if len(after) > 1 else 0.0
        se = math.sqrt(v1 / len(before) + v2 / len(after) + 1.0)
        score = delta / se
        if score > best_score:
            best_score = score
            best_k = k
            best_delta = delta

    if best_k is None or best_score < cfg.changepoint_min_z:
        return []

    shift_day = days[best_k]
    post_pts = [p for p in points if p.timestamp.date() >= shift_day]
    waste_kwh = best_delta * len(post_pts) * dt_h
    cost_irr = sum(
        best_delta * dt_h * cfg.base_kwh_price_irr * tariff.multiplier_for(p.timestamp)
        for p in post_pts
    )
    return [
        Finding(
            code="REGIME_CHANGE_POINT",
            title="Upward baseline load shift (weather-adjusted change-point)",
            severity=Severity.CRITICAL,
            summary=(
                f"Detected a persistent +{best_delta:.1f} kW weather-adjusted load step-up "
                f"starting on {shift_day.isoformat()} (z={best_score:.2f})."
            ),
            estimated_waste_kwh=round(waste_kwh, 2),
            estimated_cost_irr=round(cost_irr, 0),
            start_time=post_pts[0].timestamp.isoformat(),
            end_time=post_pts[-1].timestamp.isoformat(),
            evidence={
                "changepoint_date": shift_day.isoformat(),
                "step_increase_kw": round(best_delta, 2),
                "z_score": round(best_score, 2),
                "post_shift_days": len(days) - best_k,
            },
        )
    ]


def detect_peak_tariff_exposure(
    points: list[TelemetryPoint],
    dt_h: float,
    cfg: AuditConfig,
    tariff: IranTariffProfile,
) -> list[Finding]:
    peak_all = [p for p in points if tariff.period_for(p.timestamp) == "peak"]
    mid_all = [p for p in points if tariff.period_for(p.timestamp) == "mid_peak"]
    occ_peak = [p for p in peak_all if _is_occupied(p, cfg)]
    occ_mid = [p for p in mid_all if _is_occupied(p, cfg)]

    # Compare occupied peak vs occupied mid-peak when occupied schedules overlap
    use_occ = len(occ_peak) >= 4 and len(occ_mid) >= 4
    peak_ref = occ_peak if use_occ else peak_all
    mid_ref = occ_mid if use_occ else mid_all

    if len(peak_ref) < 4 or len(mid_ref) < 4:
        return []

    avg_peak = mean(p.power_kw for p in peak_ref)
    avg_mid = mean(p.power_kw for p in mid_ref)
    max_peak = max(p.power_kw for p in peak_all)
    ratio = avg_peak / max(avg_mid, 1.0)

    cap_breach_pts = (
        [p for p in peak_all if p.power_kw > cfg.contracted_demand_kw]
        if cfg.contracted_demand_kw is not None
        else []
    )
    if not cap_breach_pts and ratio <= cfg.peak_to_mid_ratio_limit:
        return []

    shiftable_kw = max(0.0, avg_peak - avg_mid)
    shiftable_kwh = shiftable_kw * len(peak_ref) * dt_h
    surcharge_delta = max(0.0, tariff.peak_multiplier - tariff.off_peak_multiplier)
    avoidable_cost_irr = shiftable_kwh * cfg.base_kwh_price_irr * surcharge_delta

    reasons: list[str] = []
    if cap_breach_pts and cfg.contracted_demand_kw is not None:
        reasons.append(
            f"breached contracted demand cap ({cfg.contracted_demand_kw:.0f} kW) "
            f"in {len(cap_breach_pts)} peak intervals (max {max_peak:.1f} kW)"
        )
    if ratio > cfg.peak_to_mid_ratio_limit:
        reasons.append(
            f"peak-window average ({avg_peak:.1f} kW) is {ratio:.2f}x mid-peak average ({avg_mid:.1f} kW)"
        )

    return [
        Finding(
            code="PEAK_TARIFF_EXPOSURE",
            title="Iran peak-window overload & demand-cap exposure",
            severity=Severity.CRITICAL if cap_breach_pts else Severity.WARNING,
            summary="Facility " + " and ".join(reasons) + ".",
            estimated_waste_kwh=0.0,
            estimated_cost_irr=round(avoidable_cost_irr, 0),
            start_time=peak_all[0].timestamp.isoformat(),
            end_time=peak_all[-1].timestamp.isoformat(),
            evidence={
                "avg_peak_kw": round(avg_peak, 2),
                "max_peak_kw": round(max_peak, 2),
                "avg_mid_peak_kw": round(avg_mid, 2),
                "peak_to_mid_ratio": round(ratio, 3),
                "occupied_comparison": use_occ,
                "contracted_demand_kw": cfg.contracted_demand_kw,
                "cap_breach_intervals": len(cap_breach_pts),
                "shiftable_peak_kwh": round(shiftable_kwh, 2),
            },
        )
    ]


def detect_short_cycling(
    points: list[TelemetryPoint],
    dt_h: float,
    cfg: AuditConfig,
) -> list[Finding]:
    # Short-cycling detection requires sub-20-minute telemetry
    if dt_h > 0.34 or len(points) < 12:
        return []

    by_hour: dict[tuple[date, int], list[float]] = defaultdict(list)
    for p in points:
        by_hour[(p.timestamp.date(), p.timestamp.hour)].append(p.power_kw)

    bad_hours: list[tuple[tuple[date, int], int, float]] = []
    for key, vals in sorted(by_hour.items()):
        if len(vals) < 6:
            continue
        lo, hi = min(vals), max(vals)
        span = hi - lo
        if span < cfg.short_cycle_min_swing_kw:
            continue
        high_th = lo + 0.65 * span
        low_th = lo + 0.35 * span
        is_on = vals[0] >= high_th
        starts = 0
        for v in vals[1:]:
            if not is_on and v >= high_th:
                is_on = True
                starts += 1
            elif is_on and v <= low_th:
                is_on = False
        if starts >= cfg.short_cycle_max_per_hour:
            bad_hours.append((key, starts, round(span, 1)))

    if not bad_hours:
        return []

    worst_key, worst_count, worst_span = max(bad_hours, key=lambda x: x[1])
    return [
        Finding(
            code="SHORT_CYCLING",
            title="Rapid compressor / equipment short-cycling",
            severity=Severity.WARNING,
            summary=(
                f"Detected {len(bad_hours)} hour(s) with >={cfg.short_cycle_max_per_hour} "
                f"ON/OFF swings/hour (worst: {worst_count} starts, {worst_span:.1f} kW swing at "
                f"{worst_key[0].isoformat()} {worst_key[1]:02d}:00)."
            ),
            evidence={
                "affected_hours": len(bad_hours),
                "max_starts_per_hour": worst_count,
                "worst_swing_kw": worst_span,
                "worst_hour": f"{worst_key[0].isoformat()}T{worst_key[1]:02d}:00",
            },
        )
    ]