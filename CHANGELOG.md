# Changelog

## 0.2.0 — M&V diff, Siemens/Schneider/Modbus adapters, and RTL Persian dashboards

### Measurement & Verification (`tanzim diff`)
- Added `src/tanzim/mv.py` implementing IPMVP Option C-style weather-normalized
  daily degree-day modeling (`diff_telemetry`, `diff_json_reports`, `diff_files`).
- Models Iranian workdays and Fridays (`weekend_weekdays=(4,)`) separately so
  unoccupied Fridays do not distort the cooling/heating regression R^2.
- **Non-physical slope guard:** If a mid-baseline regime shift confounds
  outdoor temperature and yields a negative degree-day slope, `tanzim diff`
  refuses to extrapolate, falls back to daily mean, and records
  `normalization_method = daily_mean_nonphysical_slope`.
- Compares fault sets across periods (`resolved_findings`,
  `persisting_findings`, `new_findings`) and emits clear verdicts
  (`verified_savings`, `marginal_change`, `regression`, `incomparable`).

### Real BMS / SCADA CSV adapters (`src/tanzim/adapters/`)
- Added zero-dependency auto-detecting adapters for **Siemens Desigo CC**,
  **Schneider EcoStruxure / PME**, **Modbus-RTU/TCP loggers**, and generic
  CSV/JSONL files.
- Handles vendor metadata preambles, semicolon delimiters, European decimal
  commas, `DD.MM.YYYY` and Unix epoch timestamps, Persian/Arabic digits
  (`۰۱۲۳۴۵۶۷۸۹`), and automatic `(W) -> kW` / `(MW) -> kW` scaling.
- Records full ingestion provenance (`adapter_info`) inside `AuditReport`.

### Offline RTL Persian dashboards & tooling
- Added `src/tanzim/api.py` (`tanzim serve`) with a self-contained RTL Persian
  HTML dashboard and `/api/audit` + `/api/diff` endpoints.
- Added `src/tanzim/streamlit_app.py` for interactive RTL Persian auditing and
  M&V comparison.
- Added `tanzim doctor` and single-source-of-truth `src/tanzim/__version__.py`
  enforced by `test_version_matches_pyproject`.

## 0.1.0 — Initial offline auditor

- Seven silent-fault detectors (`SIMULTANEOUS_HEAT_COOL`, `PHANTOM_BASELOAD`,
  `SENSOR_FLATLINE`, `CHILLER_LOW_DELTA_T`, `REGIME_CHANGE_POINT`,
  `PEAK_TARIFF_EXPOSURE`, `SHORT_CYCLING`) with Iranian seasonal Time-of-Use
  tariff valuation and local Ollama work-order generation.
- Fixed four v0.1.0 detector edge cases: chiller Delta-T gating against
  overnight standby, occupied-only peak-to-mid comparison, per-night phantom
  baseload detection, and local hourly hysteresis swing detection for whole-meter
  short-cycling.
