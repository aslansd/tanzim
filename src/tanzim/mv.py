from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean

from .__version__ import __version__
from .detectors import infer_timestep_hours
from .engine import audit_records
from .io import load_telemetry_with_info, sha256_file
from .schema import AuditConfig, MVResult, TelemetryPoint
from .tariffs import IranTariffProfile


def _daily_aggregates(
    points: list[TelemetryPoint],
    dt_h: float,
) -> list[tuple[date, float, float | None]]:
    by_day: dict[date, list[TelemetryPoint]] = defaultdict(list)
    for p in points:
        by_day[p.timestamp.date()].append(p)

    rows: list[tuple[date, float, float | None]] = []
    for d in sorted(by_day.keys()):
        pts = by_day[d]
        kwh = sum(p.power_kw * dt_h for p in pts)
        oats = [p.outdoor_temp_c for p in pts if p.outdoor_temp_c is not None]
        mean_oat = mean(oats) if len(oats) >= len(pts) * 0.5 else None
        rows.append((d, kwh, mean_oat))
    return rows


def _fit_degree_day_model(
    daily_before: list[tuple[date, float, float | None]],
    weekend_weekdays: tuple[int, ...],
) -> tuple[bool, str, float, float, float | None, bool, float | None]:
    """Fit workday E_day = intercept + slope * DD_day + separate weekend mean (IPMVP Option C)."""
    workdays = [row for row in daily_before if row[0].weekday() not in weekend_weekdays]
    weekends = [row for row in daily_before if row[0].weekday() in weekend_weekdays]
    weekend_mean = mean(kwh for _, kwh, _ in weekends) if weekends else None

    target_rows = workdays if len(workdays) >= 3 else daily_before
    with_oat = [(kwh, oat) for _, kwh, oat in target_rows if oat is not None]
    if len(with_oat) < 3 or len(with_oat) < len(target_rows) * 0.7:
        avg_kwh = mean(kwh for _, kwh, _ in target_rows) if target_rows else 0.0
        return False, "daily_mean_unadjusted", avg_kwh, 0.0, None, True, weekend_mean

    mean_oat = mean(oat for _, oat in with_oat)
    cooling_mode = mean_oat >= 18.0
    xs = [max(0.0, oat - 18.0) if cooling_mode else max(0.0, 16.0 - oat) for _, oat in with_oat]
    ys = [kwh for kwh, _ in with_oat]
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)

    if sxx < 1e-6:
        return False, "daily_mean_constant_weather", my, 0.0, 0.0, cooling_mode, weekend_mean

    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    if slope < 0.0:
        return False, "daily_mean_nonphysical_slope", my, 0.0, 0.0, cooling_mode, weekend_mean

    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 1e-6 else 0.0

    method = "ipmvp_cdd_linear" if cooling_mode else "ipmvp_hdd_linear"
    return True, method, intercept, slope, max(0.0, min(1.0, r2)), cooling_mode, weekend_mean


def diff_telemetry(
    before_points: list[TelemetryPoint],
    after_points: list[TelemetryPoint],
    config: AuditConfig | None = None,
    tariff: IranTariffProfile | None = None,
    before_source: str = "<before>",
    after_source: str = "<after>",
    before_sha256: str = "",
    after_sha256: str = "",
) -> MVResult:
    """Weather-normalized Measurement & Verification (M&V) comparison between baseline and post-retrofit telemetry."""
    cfg = config or AuditConfig()
    tar = tariff or IranTariffProfile()

    rep_before = audit_records(before_points, config=cfg, tariff=tar, source_path=before_source, source_sha256=before_sha256)
    rep_after = audit_records(after_points, config=cfg, tariff=tar, source_path=after_source, source_sha256=after_sha256)

    dt_b = infer_timestep_hours(before_points)
    dt_a = infer_timestep_hours(after_points)
    daily_b = _daily_aggregates(before_points, dt_b)
    daily_a = _daily_aggregates(after_points, dt_a)

    notes: list[str] = []
    if not daily_b or not daily_a:
        return MVResult(
            tool_version=__version__,
            compared_at_utc=datetime.now(timezone.utc).isoformat(),
            mode="telemetry_mv",
            verdict="incomparable",
            before_source=before_source,
            after_source=after_source,
            before_sha256=before_sha256,
            after_sha256=after_sha256,
            config_match=True,
            weather_normalized=False,
            normalization_method="insufficient_data",
            baseline_r2=None,
            before_days=len(daily_b),
            after_days=len(daily_a),
            counterfactual_after_kwh=0.0,
            actual_after_kwh=0.0,
            raw_savings_kwh=0.0,
            verified_savings_kwh=0.0,
            verified_savings_pct=0.0,
            verified_cost_savings_irr=0.0,
            peak_reduction_kw=0.0,
            resolved_findings=[],
            persisting_findings=[],
            new_findings=[],
            notes=["One or both telemetry files contain zero usable daily intervals."],
        )

    weather_norm, method, intercept, slope, r2, cooling_mode, weekend_mean = _fit_degree_day_model(
        daily_b, cfg.weekend_weekdays
    )
    if method == "daily_mean_nonphysical_slope":
        notes.append(
            "Baseline degree-day slope was negative (likely confounded by a mid-baseline regime shift); "
            "refused non-physical weather extrapolation and fell back to daily mean."
        )
    if weather_norm and any(oat is None for _, _, oat in daily_a):
        weather_norm = False
        method = "daily_mean_missing_after_oat"
        notes.append("Outdoor temperature missing in post-retrofit telemetry; fell back to unadjusted daily mean.")

    before_avg_daily = mean(kwh for _, kwh, _ in daily_b)
    actual_after_kwh = sum(kwh for _, kwh, _ in daily_a)
    raw_expected_after = before_avg_daily * len(daily_a)
    raw_savings_kwh = raw_expected_after - actual_after_kwh

    if weather_norm:
        cf_days = []
        for d, _, oat in daily_a:
            if d.weekday() in cfg.weekend_weekdays and weekend_mean is not None:
                cf_days.append(weekend_mean)
            else:
                dd = max(0.0, (oat or 0.0) - 18.0) if cooling_mode else max(0.0, 16.0 - (oat or 0.0))
                cf_days.append(max(0.0, intercept + slope * dd))
        counterfactual_after_kwh = sum(cf_days)
    else:
        counterfactual_after_kwh = raw_expected_after

    verified_savings_kwh = counterfactual_after_kwh - actual_after_kwh
    verified_savings_pct = (
        (verified_savings_kwh / counterfactual_after_kwh) * 100.0
        if counterfactual_after_kwh > 1e-6
        else 0.0
    )

    total_mult_kwh = sum(p.power_kw * dt_a * tar.multiplier_for(p.timestamp) for p in after_points)
    blended_mult = (total_mult_kwh / actual_after_kwh) if actual_after_kwh > 1e-6 else 1.0
    verified_cost_savings_irr = verified_savings_kwh * cfg.base_kwh_price_irr * blended_mult

    peak_b = [p.power_kw for p in before_points if tar.period_for(p.timestamp) == "peak"]
    peak_a = [p.power_kw for p in after_points if tar.period_for(p.timestamp) == "peak"]
    peak_reduction_kw = (mean(peak_b) - mean(peak_a)) if (peak_b and peak_a) else 0.0

    codes_b = {f.code for f in rep_before.findings}
    codes_a = {f.code for f in rep_after.findings}
    resolved = sorted(codes_b - codes_a)
    persisting = sorted(codes_b & codes_a)
    new_faults = sorted(codes_a - codes_b)

    if verified_savings_pct >= 5.0 and not new_faults:
        verdict = "verified_savings"
    elif verified_savings_pct <= -5.0 or (new_faults and verified_savings_pct < 5.0):
        verdict = "regression"
    else:
        verdict = "marginal_change"

    if r2 is not None and weather_norm and r2 < 0.35:
        notes.append(f"Baseline weather fit R^2={r2:.2f} is modest; check non-weather occupancy or schedule shifts.")
    if len(daily_b) < 7 or len(daily_a) < 7:
        notes.append("Fewer than 7 full days in one period; weekend/weekday mix may bias daily averages.")

    return MVResult(
        tool_version=__version__,
        compared_at_utc=datetime.now(timezone.utc).isoformat(),
        mode="telemetry_mv",
        verdict=verdict,
        before_source=before_source,
        after_source=after_source,
        before_sha256=before_sha256,
        after_sha256=after_sha256,
        config_match=True,
        weather_normalized=weather_norm,
        normalization_method=method,
        baseline_r2=r2,
        before_days=len(daily_b),
        after_days=len(daily_a),
        counterfactual_after_kwh=counterfactual_after_kwh,
        actual_after_kwh=actual_after_kwh,
        raw_savings_kwh=raw_savings_kwh,
        verified_savings_kwh=verified_savings_kwh,
        verified_savings_pct=verified_savings_pct,
        verified_cost_savings_irr=verified_cost_savings_irr,
        peak_reduction_kw=peak_reduction_kw,
        resolved_findings=resolved,
        persisting_findings=persisting,
        new_findings=new_faults,
        notes=notes,
    )


def diff_json_reports(before_path: Path, after_path: Path) -> MVResult:
    b = json.loads(before_path.read_text(encoding="utf-8"))
    a = json.loads(after_path.read_text(encoding="utf-8"))

    cfg_match = b.get("config_sha256") == a.get("config_sha256")
    codes_b = {f["code"] for f in b.get("findings", [])}
    codes_a = {f["code"] for f in a.get("findings", [])}
    resolved = sorted(codes_b - codes_a)
    persisting = sorted(codes_b & codes_a)
    new_faults = sorted(codes_a - codes_b)

    e_b = float(b.get("total_energy_kwh", 0.0))
    e_a = float(a.get("total_energy_kwh", 0.0))
    raw_sav = e_b - e_a
    pct = (raw_sav / e_b * 100.0) if e_b > 1e-6 else 0.0
    cost_delta = float(b.get("total_estimated_cost_irr", 0.0)) - float(a.get("total_estimated_cost_irr", 0.0))

    notes: list[str] = []
    if not cfg_match:
        verdict = "incomparable"
        notes.append("Audit config_sha256 differs between the two JSON reports; re-audit raw CSVs under one config.")
    elif pct >= 5.0 and not new_faults:
        verdict = "verified_savings"
    elif pct <= -5.0 or (new_faults and pct < 5.0):
        verdict = "regression"
    else:
        verdict = "marginal_change"
    notes.append("JSON-only diff is not weather-normalized; pass raw CSV files for IPMVP weather normalization.")

    return MVResult(
        tool_version=__version__,
        compared_at_utc=datetime.now(timezone.utc).isoformat(),
        mode="report_json",
        verdict=verdict,
        before_source=str(before_path),
        after_source=str(after_path),
        before_sha256=str(b.get("source_sha256", "")),
        after_sha256=str(a.get("source_sha256", "")),
        config_match=cfg_match,
        weather_normalized=False,
        normalization_method="report_json_unadjusted",
        baseline_r2=None,
        before_days=0,
        after_days=0,
        counterfactual_after_kwh=e_b,
        actual_after_kwh=e_a,
        raw_savings_kwh=raw_sav,
        verified_savings_kwh=raw_sav,
        verified_savings_pct=pct,
        verified_cost_savings_irr=cost_delta,
        peak_reduction_kw=0.0,
        resolved_findings=resolved,
        persisting_findings=persisting,
        new_findings=new_faults,
        notes=notes,
    )


def diff_files(
    before_path: str | Path,
    after_path: str | Path,
    config: AuditConfig | None = None,
    tariff: IranTariffProfile | None = None,
    adapter: str = "auto",
) -> MVResult:
    pb, pa = Path(before_path), Path(after_path)
    if pb.suffix.lower() == ".json" and pa.suffix.lower() == ".json":
        return diff_json_reports(pb, pa)
    pts_b, _ = load_telemetry_with_info(pb, adapter=adapter)
    pts_a, _ = load_telemetry_with_info(pa, adapter=adapter)
    return diff_telemetry(
        before_points=pts_b,
        after_points=pts_a,
        config=config,
        tariff=tariff,
        before_source=str(pb),
        after_source=str(pa),
        before_sha256=sha256_file(pb),
        after_sha256=sha256_file(pa),
    )
