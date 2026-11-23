from __future__ import annotations

from pathlib import Path
import pytest

from tanzim.synthetic import generate_tehran_summer_bms, write_telemetry_csv


def test_fastapi_audit_and_diff_endpoints(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from tanzim.api import create_app

    client = TestClient(create_app())
    assert client.get("/api/health").status_code == 200
    assert 'dir="rtl"' in client.get("/").text

    fb = write_telemetry_csv(
        generate_tehran_summer_bms(days=10, step_minutes=15, inject_faults=True, seed=1),
        tmp_path / "b.csv",
    )
    fa = write_telemetry_csv(
        generate_tehran_summer_bms(days=10, step_minutes=15, inject_faults=False, seed=2),
        tmp_path / "a.csv",
    )

    with fb.open("rb") as f:
        r_audit = client.post(
            "/api/audit",
            files={"file": ("b.csv", f, "text/csv")},
            data={"demand_cap": "180"},
        )
    assert r_audit.status_code == 200
    assert len(r_audit.json()["report"]["findings"]) > 0

    with fb.open("rb") as f1, fa.open("rb") as f2:
        r_diff = client.post(
            "/api/diff",
            files={
                "before_file": ("b.csv", f1, "text/csv"),
                "after_file": ("a.csv", f2, "text/csv"),
            },
            data={"demand_cap": "180"},
        )
    assert r_diff.status_code == 200
    assert r_diff.json()["verdict"] == "verified_savings"
