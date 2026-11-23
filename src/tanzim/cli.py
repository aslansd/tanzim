from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import platform
import sys
from pathlib import Path

from .__version__ import __version__
from .adapters import ADAPTER_REGISTRY
from .engine import audit_file
from .llm_tickets import generate_work_order
from .mv import diff_files
from .schema import AuditConfig, AuditReport, MVResult
from .synthetic import generate_tehran_summer_bms, write_telemetry_csv


def _print_report(report: AuditReport) -> None:
    adapter_name = report.adapter_info.adapter if report.adapter_info else "in-memory"
    print(f"tanzim v{report.tool_version} | adapter={adapter_name} | source={report.source_path}")
    print(f"sha256={report.source_sha256[:16]}... | records={report.record_count} (dt={report.timestep_hours:.2f}h)")
    print(
        f"energy={report.total_energy_kwh:,.1f} kWh | peak={report.peak_energy_kwh:,.1f} kWh | "
        f"est_waste={report.total_estimated_waste_kwh:,.1f} kWh | "
        f"est_savings={report.total_estimated_cost_irr:,.0f} IRR"
    )
    print("-" * 78)
    if not report.findings:
        print("OK: No silent BMS/SCADA energy faults detected.")
        return
    for f in report.findings:
        print(f"[{f.severity.value.upper():8}] {f.code:<24} | {f.title}")
        print(f"           {f.summary}")
        if f.estimated_waste_kwh > 0 or f.estimated_cost_irr > 0:
            print(f"           impact: {f.estimated_waste_kwh:,.1f} kWh | {f.estimated_cost_irr:,.0f} IRR")


def _print_mv(mv: MVResult) -> None:
    print(f"tanzim diff v{mv.tool_version} | mode={mv.mode} | verdict={mv.verdict.upper()}")
    print(f"--- before: {mv.before_source} ({mv.before_sha256[:12]})")
    print(f"+++ after:  {mv.after_source} ({mv.after_sha256[:12]})")
    print("-" * 78)
    print(
        f"normalization : {mv.normalization_method} "
        f"(weather_normalized={mv.weather_normalized}, baseline_r2={mv.baseline_r2})"
    )
    print(f"counterfactual: {mv.counterfactual_after_kwh:,.1f} kWh -> actual: {mv.actual_after_kwh:,.1f} kWh")
    print(
        f"verified save : {mv.verified_savings_kwh:,.1f} kWh ({mv.verified_savings_pct:+.1f}%) | "
        f"{mv.verified_cost_savings_irr:,.0f} IRR | peak_delta={mv.peak_reduction_kw:+.1f} kW"
    )
    print(f"resolved ({len(mv.resolved_findings)})  : {', '.join(mv.resolved_findings) or 'none'}")
    print(f"persisting ({len(mv.persisting_findings)}): {', '.join(mv.persisting_findings) or 'none'}")
    print(f"new faults ({len(mv.new_findings)}): {', '.join(mv.new_findings) or 'none'}")
    for note in mv.notes:
        print(f"note          : {note}")


def _run_doctor() -> int:
    print(f"tanzim {__version__}")
    print(f"python {platform.python_version()} on {platform.system()} {platform.machine()}")
    try:
        meta_ver = importlib.metadata.version("tanzim")
    except importlib.metadata.PackageNotFoundError:
        meta_ver = "uninstalled"
    print(f"package metadata: {meta_ver}")
    print("")
    print("Built-in BMS/SCADA adapters (zero dependencies):")
    for name in ADAPTER_REGISTRY:
        print(f"  {name:<12} ok")
    print("")
    print("Optional dashboard extras:")
    for pkg in ("fastapi", "uvicorn", "streamlit"):
        status = "ok" if importlib.util.find_spec(pkg) is not None else "-       not installed"
        print(f"  {pkg:<12} {status}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tanzim", description="Offline BMS/SCADA silent-fault auditor & M&V tool.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_audit = sub.add_parser("audit", help="Audit a BMS/SCADA CSV or JSONL file.")
    p_audit.add_argument("file", help="Path to telemetry .csv or .jsonl")
    p_audit.add_argument("--adapter", default="auto", help="Adapter: auto, siemens, schneider, modbus, generic")
    p_audit.add_argument("--demand-cap", type=float, default=None, help="Contracted peak demand cap (kW)")
    p_audit.add_argument("--price-irr", type=float, default=12_000.0, help="Base electricity rate (IRR/kWh)")
    p_audit.add_argument("--json-out", type=str, default=None, help="Write provenance JSON report to path")
    p_audit.add_argument("--ticket", choices=("fa", "en"), default=None, help="Generate work order via local Ollama")
    p_audit.add_argument("--model", type=str, default="gemma3:12b", help="Local Ollama model name")

    p_diff = sub.add_parser("diff", help="Measurement & Verification (M&V) comparison of before/after files.")
    p_diff.add_argument("before", help="Baseline CSV/JSONL telemetry or audit JSON")
    p_diff.add_argument("after", help="Post-retrofit CSV/JSONL telemetry or audit JSON")
    p_diff.add_argument("--adapter", default="auto", help="Adapter for telemetry files")
    p_diff.add_argument("--demand-cap", type=float, default=None, help="Contracted demand cap (kW)")
    p_diff.add_argument("--price-irr", type=float, default=12_000.0, help="Base electricity rate (IRR/kWh)")
    p_diff.add_argument("--json-out", type=str, default=None, help="Write M&V certificate JSON")

    p_demo = sub.add_parser("demo", help="Generate synthetic Tehran summer BMS dataset and audit.")
    p_demo.add_argument("--out-csv", type=str, default="tehran_bms_demo.csv")
    p_demo.add_argument("--demand-cap", type=float, default=180.0)
    p_demo.add_argument("--clean", action="store_true", help="Generate healthy baseline without injected faults")

    sub.add_parser("doctor", help="Inspect Python environment, built-in adapters, and optional UI extras.")

    p_serve = sub.add_parser("serve", help="Run the offline RTL Persian FastAPI dashboard.")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)

    if args.cmd == "doctor":
        return _run_doctor()

    if args.cmd == "demo":
        pts = generate_tehran_summer_bms(days=14, step_minutes=5, inject_faults=not args.clean)
        csv_path = write_telemetry_csv(pts, args.out_csv)
        report = audit_file(csv_path, config=AuditConfig(contracted_demand_kw=args.demand_cap))
        _print_report(report)
        return 0

    if args.cmd == "audit":
        cfg = AuditConfig(contracted_demand_kw=args.demand_cap, base_kwh_price_irr=args.price_irr)
        report = audit_file(args.file, config=cfg, adapter=args.adapter)
        _print_report(report)
        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\nSaved provenance report -> {args.json_out}")
        if args.ticket:
            print("\n" + "=" * 78)
            print(generate_work_order(report, lang=args.ticket, model=args.model))
        return 0

    if args.cmd == "diff":
        cfg = AuditConfig(contracted_demand_kw=args.demand_cap, base_kwh_price_irr=args.price_irr)
        mv = diff_files(args.before, args.after, config=cfg, adapter=args.adapter)
        _print_mv(mv)
        if args.json_out:
            Path(args.json_out).write_text(
                json.dumps(mv.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\nSaved M&V certificate -> {args.json_out}")
        return 0 if mv.verdict in {"verified_savings", "marginal_change"} else 1

    if args.cmd == "serve":
        try:
            import uvicorn
        except ImportError:
            print("Missing web dependencies. Run: pip install 'tanzim[web]'", file=sys.stderr)
            return 1
        from .api import create_app
        uvicorn.run(create_app(), host=args.host, port=args.port)
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
