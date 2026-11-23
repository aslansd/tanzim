# Troubleshooting

Always start with:

```bash
tanzim doctor
```

---

## `tanzim: error: unrecognized arguments: --model, type=...`

Shell flags do not use Python `argparse` syntax. Pass `--model` with a space,
and include `--ticket fa` (or `--ticket en`) on `tanzim audit`:

```bash
tanzim audit examples/tehran_bms_before.csv --demand-cap 180 --ticket fa --model gemma3:12b
```

Note that `tanzim demo` only generates and audits synthetic data; it does not
call Ollama.

---

## `tanzim diff` reports `daily_mean_nonphysical_slope`

Working as designed. In cooling mode, daily energy should rise with hotter
outdoor temperatures (slope >= 0). If your baseline file contains a sudden
mid-period equipment breakdown or manual override that happened during a cooler
week, ordinary least squares produces a negative slope. Extrapolating that
slope into hotter weather would invent fake energy numbers.

`tanzim` detects slope < 0, refuses to extrapolate, falls back to daily mean
comparison, and logs a note explaining why. To get a clean weather-adjusted
baseline, trim the baseline CSV to a stable operating window or use at least
14 days spanning typical outdoor temperature variation.

---

## `Adapter '...' could not resolve required timestamp and power columns`

Vendor exports vary by site integrator. Inspect the first 10 lines of your CSV:

```bash
head -n 10 your_export.csv
```

Check whether:
1. Metadata preamble exceeds 25 lines (trim excess header lines or override `--adapter`).
2. The power column uses a custom site tag (e.g., `B2_Main_M1`). Rename the header to `power_kw` (or `power_w`) or add the tag regex to the site adapter in `src/tanzim/adapters/`.

---

## `tanzim serve` exits with `Missing web dependencies`

The core package intentionally ships without FastAPI/Uvicorn so it installs on
air-gapped plant servers with zero dependency conflicts. Install the web extra:

```bash
pip install "tanzim[web]"
```

---

## Ollama ticket output falls back to a plain template

`generate_work_order` calls `http://localhost:11434/api/generate` with a 60s
timeout. Verify Ollama is running (`ollama list`) and that the `--model` name
matches an installed tag verbatim (for example `gemma3:12b`, not `gemma3-12b`).
