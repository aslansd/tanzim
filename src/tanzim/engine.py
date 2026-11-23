from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .__version__ import __version__
from .detectors import (
    detect_chiller_low_delta_t,
    detect_peak_tariff_exposure,
    detect_phantom_baseload,
    detect_regime_changepoint,
    detect_sensor_flatline,
    detect_short_cycling,
    detect_simultaneous_heat_cool,
    infer_timestep_hours,
)
from .io import load_telemetry_with_info, sha256_dict, sha256_file
from .schema import AdapterInfo, AuditConfig, AuditReport, Severity, TelemetryPoint
from .tariffs import IranTariffProfile

_SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}


def audit_records(
    points: list[TelemetryPoint],
    config: AuditConfig | None = None,
    tariff: IranTariffProfile | None = None,
    source_path: str = "<in-memory>",
    source_sha256: str = "",
    adapter_info: AdapterInfo | None = None,
) -> AuditReport:
    cfg = config or AuditConfig()
    tar = tariff or IranTariffProfile()
    dt_h = infer_timestep_hours(points)

    findings = []
    findings.extend(detect_simultaneous_heat_cool(points, dt_h, cfg, tar))
    findings.extend(detect_phantom_baseload(points, dt_h, cfg, tar))
    findings.extend(detect_sensor_flatline(points, dt_h, cfg))
    findings.extend(detect_chiller_low_delta_t(points, dt_h, cfg, tar))
    findings.extend(detect_regime_changepoint(points, dt_h, cfg, tar))
    findings.extend(detect_peak_tariff_exposure(points, dt_h, cfg, tar))
    findings.extend(detect_short_cycling(points, dt_h, cfg))

    findings.sort(key=lambda f: (_SEVERITY_ORDER[f.severity], -f.estimated_cost_irr, f.code))

    total_kwh = sum(p.power_kw * dt_h for p in points)
    peak_kwh = sum(p.power_kw * dt_h for p in points if tar.period_for(p.timestamp) == "peak")
    total_waste_kwh = sum(f.estimated_waste_kwh for f in findings)
    total_cost_irr = sum(f.estimated_cost_irr for f in findings)

    return AuditReport(
        tool_version=__version__,
        audited_at_utc=datetime.now(timezone.utc).isoformat(),
        source_path=source_path,
        source_sha256=source_sha256,
        config_sha256=sha256_dict(cfg.to_dict()),
        record_count=len(points),
        timestep_hours=dt_h,
        total_energy_kwh=total_kwh,
        peak_energy_kwh=peak_kwh,
        total_estimated_waste_kwh=total_waste_kwh,
        total_estimated_cost_irr=total_cost_irr,
        findings=findings,
        adapter_info=adapter_info,
    )


def audit_file(
    path: str | Path,
    config: AuditConfig | None = None,
    tariff: IranTariffProfile | None = None,
    adapter: str = "auto",
) -> AuditReport:
    p = Path(path)
    points, info = load_telemetry_with_info(p, adapter=adapter)
    return audit_records(
        points=points,
        config=config,
        tariff=tariff,
        source_path=str(p),
        source_sha256=sha256_file(p),
        adapter_info=info,
    )
