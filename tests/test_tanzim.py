from __future__ import annotations

from pathlib import Path

from tanzim import AuditConfig, audit_file, audit_records
from tanzim.synthetic import generate_tehran_summer_bms, write_telemetry_csv


def test_clean_tehran_plant_has_zero_false_positives() -> None:
    pts = generate_tehran_summer_bms(days=14, step_minutes=5, inject_faults=False, seed=7)
    report = audit_records(pts, config=AuditConfig(contracted_demand_kw=180.0))
    assert report.findings == []
    assert report.total_energy_kwh > 0


def test_faulted_tehran_plant_catches_all_seven_faults(tmp_path: Path) -> None:
    pts = generate_tehran_summer_bms(days=14, step_minutes=5, inject_faults=True, seed=42)
    csv_path = write_telemetry_csv(pts, tmp_path / "faulted.csv")

    report = audit_file(csv_path, config=AuditConfig(contracted_demand_kw=180.0))
    codes = {f.code for f in report.findings}

    expected = {
        "SIMULTANEOUS_HEAT_COOL",
        "PHANTOM_BASELOAD",
        "SENSOR_FLATLINE",
        "CHILLER_LOW_DELTA_T",
        "REGIME_CHANGE_POINT",
        "PEAK_TARIFF_EXPOSURE",
        "SHORT_CYCLING",
    }
    assert expected.issubset(codes)
    assert len(report.source_sha256) == 64
    assert report.total_estimated_waste_kwh > 0
    assert report.total_estimated_cost_irr > 0