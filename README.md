# tanzim

**تنظیم** — *tuning, regulation, balancing.* The same word in Persian (*tanzīm*),
Azerbaijani (*tənzim*), and Turkish (*tanzim*).

Audit building BMS and industrial SCADA logs offline to catch silent energy
faults, quantify Iranian peak-tariff exposure, and verify post-retrofit savings
with weather-normalized Measurement & Verification (`tanzim diff`).

Commercial towers, hospitals, campuses, and factories routinely lose 15–30% of
their electricity and gas to faults that trigger no BMS alarm: valves fighting
simultaneously, chillers left in manual mode overnight, frozen supply-air
sensors blinding PID loops, low chilled-water Delta-T, and unmonitored regime
shifts. Most energy platforms assume cloud connectivity, new IoT hardware, and
foreign API keys. `tanzim` sits on top of the CSV exports your existing meters
and BMS already produce.

**Zero runtime dependencies for the core engine. Runs 100% offline. No account, no cloud, no hardware.**

```bash
pip install tanzim
```

Python 3.10+. Apache 2.0.

[INSTALL](INSTALL.md) · [TESTING](TESTING.md) · [TROUBLESHOOTING](TROUBLESHOOTING.md) ·
[PUBLISHING](PUBLISHING.md) · [ROADMAP](ROADMAP.md) · [CHANGELOG](CHANGELOG.md)

---

## The thirty-second version

```bash
# 1. Generate a realistic 14-day Tehran summer chiller log and audit it
tanzim demo --out-csv tehran_before.csv

# 2. Audit any Siemens Desigo, Schneider EcoStruxure, or Modbus CSV + Persian work order via Ollama
tanzim audit tehran_before.csv --demand-cap 180 --json-out before.json --ticket fa --model gemma3:12b

# 3. After fixing the plant, prove weather-normalized kWh and IRR savings
tanzim demo --clean --out-csv tehran_after.csv
tanzim diff tehran_before.csv tehran_after.csv --demand-cap 180 --json-out mv_cert.json
```

Output of `tanzim diff`:

```text
tanzim diff v0.2.0 | mode=telemetry_mv | verdict=VERIFIED_SAVINGS
--- before: tehran_before.csv (eeef9c403a73)
+++ after:  tehran_after.csv  (a68bd2da1750)
------------------------------------------------------------------------------
normalization : ipmvp_cdd_linear (weather_normalized=True, baseline_r2=0.94)
counterfactual: 27,272.5 kWh -> actual: 18,140.1 kWh
verified save : 9,132.4 kWh (+33.5%) | 153,649,088 IRR | peak_delta=+43.4 kW
resolved (7)  : CHILLER_LOW_DELTA_T, PEAK_TARIFF_EXPOSURE, PHANTOM_BASELOAD, ...
persisting (0): none
new faults (0): none
```

---

## Seven silent faults detected out of the box

| Code | What it catches |
|---|---|
| `SIMULTANEOUS_HEAT_COOL` | Heating and cooling valves open together (valve fighting / deadband collapse) |
| `PHANTOM_BASELOAD` | Unoccupied night baseload exceeding threshold on >= 2 nights (manual AHU/chiller overrides) |
| `SENSOR_FLATLINE` | Supply-air, chilled-water, or power telemetry locked on an identical reading while plant is active |
| `CHILLER_LOW_DELTA_T` | Active cooling hours with chilled-water Delta-T < 2.5 C (over-pumping / fouled coils) |
| `REGIME_CHANGE_POINT` | Persistent upward step-change in weather-adjusted daily load |
| `PEAK_TARIFF_EXPOSURE` | Iranian seasonal Time-of-Use peak overload and contracted demand-cap breaches |
| `SHORT_CYCLING` | Rapid compressor ON/OFF load swings (>= 4 starts/hour) accelerating mechanical wear |

---

## Built-in BMS / SCADA adapters

Every adapter runs on the Python standard library and records its resolved
delimiter, skipped preamble lines, power unit scale (`W -> kW`), and mapped
columns inside `adapter_info`:

| Adapter | Vendor / Export Format | Handles |
|---|---|---|
| `siemens` | Siemens Desigo CC / Insight | Metadata preamble rows, `;` delimiter, European decimal commas, `DD.MM.YYYY`, split `Date;Time` |
| `schneider` | Schneider EcoStruxure / PME | Report headers, `Date/Time`, automatic `(W) -> kW` scaling |
| `modbus` | Industrial Modbus-RTU/TCP loggers | Register headers (`40001`/`30001`), Unix epochs, Persian/Arabic digits (`۰۱۲۳۴۵۶۷۸۹`), Watt scaling |
| `generic` | Clean `.csv` and `.jsonl` | Standard ISO timestamps and column aliases |

---

## Measurement & Verification (`tanzim diff`) verdicts

`tanzim diff` separates raw electricity reduction from **weather-normalized
counterfactual savings** (IPMVP Option C linear degree-day model fitted on
workdays, with Iranian Fridays modeled separately):

| Verdict | Meaning |
|---|---|
| `verified_savings` | Weather-normalized savings >= 5% with zero newly introduced faults |
| `marginal_change` | Net weather-normalized change within +/- 5% |
| `regression` | Weather-normalized energy increased > 5% or new faults appeared |
| `incomparable` | Mismatched `config_sha256` across JSON reports or unusable telemetry |

If a mid-baseline fault confounds temperature and produces a non-physical
negative cooling/heating slope, `tanzim` refuses to extrapolate it, falls back
to daily mean, and records `normalization_method = daily_mean_nonphysical_slope`.

---

## Offline RTL Persian dashboards

```bash
# FastAPI + built-in RTL Persian UI (no npm/Node build required)
pip install "tanzim[web]"
tanzim serve --port 8000

# Or Streamlit RTL Persian dashboard
pip install "tanzim[streamlit]"
streamlit run src/tanzim/streamlit_app.py
```

## Licence

Apache 2.0.
