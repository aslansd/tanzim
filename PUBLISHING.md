# Publishing tanzim

## Release checklist

```bash
pip install build twine
```

1. **Bump the version in two places** (`test_version_matches_pyproject` enforces parity):
   - `src/tanzim/__version__.py`
   - `pyproject.toml`
2. **Write the `CHANGELOG.md` entry first.**
3. **Run full verification:**
   ```bash
   pytest -v
   ruff check src tests
   tanzim doctor
   ```
4. **Build and check the distribution:**
   ```bash
   rm -rf dist build src/*.egg-info
   python -m build
   python -m twine check dist/*
   ```
5. **Test the built wheel in a clean virtual environment** (catches missing subpackages such as `tanzim.adapters`):
   ```bash
   python -m venv /tmp/tanzim-check
   /tmp/tanzim-check/bin/pip install dist/tanzim-*.whl
   /tmp/tanzim-check/bin/tanzim doctor
   /tmp/tanzim-check/bin/tanzim demo --out-csv /tmp/tanzim-check/demo.csv
   ```
6. **Upload and tag:**
   ```bash
   python -m twine upload dist/*
   git tag v0.2.0 && git push --tags
   ```
7. **Verify from PyPI without local cache:**
   ```bash
   pip install --no-cache-dir -U tanzim
   ```
