from __future__ import annotations

import json
import urllib.error
import urllib.request

from .schema import AuditReport


def _fallback_ticket(report: AuditReport, lang: str) -> str:
    if lang == "fa":
        lines = [
            f"گزارش دستور کار نگهداری و بهینه‌سازی انرژی (tanzim v{report.tool_version})",
            f"کل انرژی بررسی‌شده: {report.total_energy_kwh:,.1f} kWh | اتلاف برآوردی: {report.total_estimated_waste_kwh:,.1f} kWh",
            "",
        ]
        for idx, f in enumerate(report.findings, 1):
            lines.append(f"{idx}. [{f.severity.value.upper()}] {f.code} — {f.title}")
            lines.append(f"   شرح فنی: {f.summary}")
            lines.append(f"   برآورد هزینه قابل صرفه‌جویی: {f.estimated_cost_irr:,.0f} ریال")
        return "\n".join(lines)

    lines = [
        f"Maintenance & Energy Optimization Work Order (tanzim v{report.tool_version})",
        f"Audited energy: {report.total_energy_kwh:,.1f} kWh | Estimated waste: {report.total_estimated_waste_kwh:,.1f} kWh",
        "",
    ]
    for idx, f in enumerate(report.findings, 1):
        lines.append(f"{idx}. [{f.severity.value.upper()}] {f.code} — {f.title}")
        lines.append(f"   Details: {f.summary}")
    return "\n".join(lines)


def generate_work_order(
    report: AuditReport,
    lang: str = "fa",
    model: str = "gemma3:12b",
    ollama_url: str = "http://localhost:11434/api/generate",
    timeout_sec: int = 60,
) -> str:
    if not report.findings:
        return "هیچ خطای پنهان انرژی شناسایی نشد." if lang == "fa" else "No silent energy faults detected."

    language_directive = (
        "Write a clear, concise maintenance work order in natural Persian (Farsi) for a Tehran building facility engineer."
        if lang == "fa"
        else "Write a clear, concise maintenance work order in English for a building facility engineer."
    )
    prompt = (
        f"{language_directive}\n"
        "For each finding, list: (1) Root cause to inspect on-site, (2) Immediate corrective step, "
        "(3) Expected energy/tariff benefit. Do not invent numbers outside the JSON.\n\n"
        f"AUDIT JSON:\n{json.dumps(report.to_dict(), ensure_ascii=False, indent=2)}"
    )

    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    req = urllib.request.Request(
        ollama_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            text = str(body.get("response", "")).strip()
            return text or _fallback_ticket(report, lang)
    except (urllib.error.URLError, TimeoutError, ValueError):
        return _fallback_ticket(report, lang)
