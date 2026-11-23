# Testing tanzim

## Quick run

```bash
uv pip install -e ".[dev]"
pytest -q
```

## Test suites

| File | Tests | Needs | What it guards |
|---|---|---|---|
| `tests/test_tanzim.py` | 3 | nothing | Version parity (`__version__` vs `pyproject.toml`), zero false positives on clean Tehran summer plant, all 7 faults caught on faulted plant |
| `tests/test_adapters.py` | 3 | nothing | Siemens Desigo preamble/semicolon/decimal-comma parsing, Schneider Watt-to-kW scaling, Modbus Unix epoch + Persian digits |
| `tests/test_mv.py` | 4 | nothing | Weather-normalized savings in hotter post-retrofit weeks, refusal to extrapolate non-physical negative weather slopes, regression detection, JSON config-hash mismatch |
| `tests/test_web.py` | 1 | `fastapi`, `httpx` | `/api/health`, RTL Persian HTML rendering, `/api/audit`, `/api/diff` (skips cleanly if `[web]` is not installed) |

## End-to-end CLI smoke test

```bash
tanzim doctor
tanzim demo --out-csv before.csv
tanzim demo --clean --out-csv after.csv
tanzim diff before.csv after.csv --demand-cap 180
```

`tanzim diff` exits `0` on `verified_savings` or `marginal_change` and `1` on
`regression` or `incomparable`, so it can gate scheduled monthly building
audits in cron or CI.
