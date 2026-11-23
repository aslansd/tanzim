# Installing tanzim

## Core auditor and M&V engine

```bash
pip install tanzim
```

The core package has **zero runtime dependencies** and runs on Python 3.10+.
It requires no internet connection, no account, and no cloud API keys.

Verify your installation:

```bash
python -c "import tanzim; print(tanzim.__version__)"
tanzim doctor
```

---

## Optional dashboard extras

| Extra | Command | What it adds |
|---|---|---|
| `web` | `pip install "tanzim[web]"` | FastAPI backend + self-contained RTL Persian web dashboard (`tanzim serve`) |
| `streamlit` | `pip install "tanzim[streamlit]"` | Interactive RTL Persian Streamlit dashboard |
| `all` | `pip install "tanzim[all]"` | Both FastAPI and Streamlit interfaces |
| `dev` | `pip install -e ".[dev]"` | `pytest`, `ruff`, and `httpx` (for FastAPI endpoint tests) |

### Using `uv` (recommended on macOS / Linux)

```bash
uv venv && source .venv/bin/activate
uv pip install -e ".[dev,web,streamlit]"
tanzim doctor
```

---

## Local Persian work orders (Ollama)

`tanzim audit --ticket fa` calls a local Ollama daemon over standard HTTP
(`http://localhost:11434/api/generate`) using Python's `urllib`—no extra Python
SDK is needed. If Ollama is unreachable, `tanzim` falls back cleanly to a
deterministic Persian or English template.

Recommended local models for technical Persian maintenance tickets:

- `gemma3:12b` (best balance of Persian fluency and speed on 16–32 GB RAM)
- `gemma3:4b` (lightweight fallback on 8 GB machines)
- `llama3.2:latest` (fast English tickets)
