# Roadmap

*Last revised 23 November 2026, against tanzim 0.2.0.*

---

## Where this stands

**0.2.0**, Apache 2.0, **zero runtime dependencies for core**, **11 tests**,
**4 built-in BMS/SCADA adapters**, **IPMVP-style M&V diff**, and **RTL Persian
FastAPI + Streamlit dashboards**.

| Component | Status |
|---|---|
| 7 deterministic silent-fault detectors + Iran seasonal ToU tariff engine | shipped |
| Siemens Desigo, Schneider EcoStruxure, Modbus-RTU/TCP, and Generic adapters | shipped |
| `tanzim diff` weather-normalized M&V engine with non-physical slope guard | shipped |
| Local Ollama Persian/English maintenance ticket generator | shipped |
| Offline RTL Persian FastAPI (`tanzim serve`) and Streamlit dashboards | shipped |
| **Real Tehran pilot datasets (3 sites)** | **next — the only thing that matters now** |

---

## Next 30 days (stop adding features until real logs arrive)

The risk at v0.2.0 is building hypothetical detectors against synthetic CSVs.
Every next commit should come directly from friction on real Iranian building
exports:

1. **Pilot 1 — University of Tehran campus building:** Collect 30 days of main
   feeder + chiller logs, run `tanzim audit`, verify findings on-site with the
   facilities engineer.
2. **Pilot 2 — Private hospital or commercial tower (Tehran District 3 or 6):**
   Test Siemens Desigo / Schneider export quirks (real Jalali dates, missing
   intervals, multi-chiller headers) and harden adapters against real files.
3. **Pilot 3 — Industrial plant (Shamsabad or Karaj):** Test Modbus-RTU meter
   CSVs and peak-demand cap penalties (`--demand-cap`), then run `tanzim diff`
   30 days after schedule/setpoint adjustments to produce a verified IRR savings
   certificate.

## Deferred until requested by a paying pilot

- Jalali (`1405/04/10`) native date-string parser in `adapters/base.py`
- Direct live polling via `pymodbus` / `BAC0` (CSV export is zero-IT-friction first)
- Printable RTL Persian PDF executive reports for building boards and SATBA filings
- Multi-building fleet overview and scheduled monthly email/Telegram alerts
