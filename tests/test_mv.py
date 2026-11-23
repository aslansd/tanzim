from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from tanzim import AuditConfig, audit_file, diff_files
from tanzim.synthetic import generate_tehran_summer_bms, write_telemetry_csv


def test_mv_verifies_weather_normalized_savings_when_after_is_hotter(tmp_path: Path) -> None:
    base_clean = generate_tehran_summer_bms(
        days=14, step_minutes=15, inject_faults=False, seed=10,
        start_date=datetime(2026, 7, 1, 0, 0), temp_offset_c=0.0,
    )
    before_pts = [
        replace(p, power_kw=round(p.power_kw + (65.0 if p.timestamp.hour < 6 else 25.0), 2))
        for p in base_clean
    ]
    after_pts = generate_tehran_summer_bms(
        days=14, step_minutes=15, inject_faults=False, seed=11,
        start_date=datetime(2026, 7, 15, 0, 0), temp_offset_c=3.5,
    )
    fb = write_telemetry_csv(before_pts, tmp_path / "before.csv")
    fa = write_telemetry_csv(after_pts, tmp_path / "after.csv")

    mv = diff_files(fb, fa, config=AuditConfig(contracted_demand_kw=180.0))
    assert mv.verdict == "verified_savings"
    assert mv.weather_normalized is True
    assert mv.baseline_r2 is not None and mv.baseline_r2 > 0.35
    assert mv.verified_savings_kwh > mv.raw_savings_kwh
    assert mv.verified_savings_pct > 25.0
    assert mv.verified_cost_savings_irr > 0
    assert "PHANTOM_BASELOAD" in mv.resolved_findings
    assert mv.new_findings == []


def test_mv_refuses_nonphysical_negative_weather_slope(tmp_path: Path) -> None:
    before_pts = generate_tehran_summer_bms(
        days=14, step_minutes=15, inject_faults=True, seed=10,
        start_date=datetime(2026, 7, 1, 0, 0), temp_offset_c=0.0,
    )
    after_pts = generate_tehran_summer_bms(
        days=14, step_minutes=15, inject_faults=False, seed=11,
        start_date=datetime(2026, 7, 15, 0, 0), temp_offset_c=3.0,
    )
    fb = write_telemetry_csv(before_pts, tmp_path / "before_shift.csv")
    fa = write_telemetry_csv(after_pts, tmp_path / "after_clean.csv")

    mv = diff_files(fb, fa, config=AuditConfig(contracted_demand_kw=180.0))
    assert mv.normalization_method == "daily_mean_nonphysical_slope"
    assert mv.weather_normalized is False
    assert mv.verdict == "verified_savings"
    assert mv.verified_savings_kwh > 0


def test_mv_detects_regression_when_faults_introduced(tmp_path: Path) -> None:
    clean_pts = generate_tehran_summer_bms(days=14, step_minutes=15, inject_faults=False, seed=20)
    fault_pts = generate_tehran_summer_bms(
        days=14, step_minutes=15, inject_faults=True, seed=21,
        start_date=datetime(2026, 7, 15, 0, 0),
    )
    fb = write_telemetry_csv(clean_pts, tmp_path / "clean.csv")
    fa = write_telemetry_csv(fault_pts, tmp_path / "faulted.csv")

    mv = diff_files(fb, fa, config=AuditConfig(contracted_demand_kw=180.0))
    assert mv.verdict == "regression"
    assert mv.verified_savings_kwh < 0
    assert "PHANTOM_BASELOAD" in mv.new_findings


def test_json_report_diff_flags_config_mismatch_as_incomparable(tmp_path: Path) -> None:
    pts = generate_tehran_summer_bms(days=7, step_minutes=15, inject_faults=False, seed=3)
    csv_p = write_telemetry_csv(pts, tmp_path / "p.csv")

    r1 = audit_file(csv_p, config=AuditConfig(base_kwh_price_irr=12_000.0))
    r2 = audit_file(csv_p, config=AuditConfig(base_kwh_price_irr=18_000.0))
    j1, j2 = tmp_path / "r1.json", tmp_path / "r2.json"
    j1.write_text(json.dumps(r1.to_dict()), encoding="utf-8")
    j2.write_text(json.dumps(r2.to_dict()), encoding="utf-8")

    mv = diff_files(j1, j2)
    assert mv.verdict == "incomparable"
    assert mv.config_match is False
