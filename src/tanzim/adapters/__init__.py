from __future__ import annotations

from pathlib import Path
from typing import Callable

from ..schema import AdapterInfo, TelemetryPoint
from .generic import load_generic_telemetry
from .modbus import can_parse as is_modbus
from .modbus import load_modbus_csv
from .schneider import can_parse as is_schneider
from .schneider import load_schneider_csv
from .siemens import can_parse as is_siemens
from .siemens import load_siemens_csv

ADAPTER_REGISTRY: dict[str, Callable[[Path], tuple[list[TelemetryPoint], AdapterInfo]]] = {
    "siemens": load_siemens_csv,
    "schneider": load_schneider_csv,
    "modbus": load_modbus_csv,
    "generic": load_generic_telemetry,
}


def detect_adapter(path: Path) -> str:
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        return "generic"
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    if is_siemens(sample):
        return "siemens"
    if is_schneider(sample):
        return "schneider"
    if is_modbus(sample):
        return "modbus"
    return "generic"


def load_with_adapter(
    path: str | Path,
    adapter: str = "auto",
) -> tuple[list[TelemetryPoint], AdapterInfo]:
    p = Path(path)
    chosen = detect_adapter(p) if adapter == "auto" else adapter.lower()
    if chosen not in ADAPTER_REGISTRY:
        raise ValueError(f"Unknown adapter '{adapter}'. Choose from: auto, {', '.join(ADAPTER_REGISTRY)}")
    return ADAPTER_REGISTRY[chosen](p)


__all__ = ["ADAPTER_REGISTRY", "detect_adapter", "load_with_adapter"]
