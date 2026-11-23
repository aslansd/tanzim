from __future__ import annotations

import argparse
import json
from pathlib import Path

from .engine import audit_file
from .llm_tickets import generate_work_order
from .schema import AuditConfig, AuditReport
from .synthetic import generate_tehran_summer_bms, write_telemetry_csv


def _print_report(report: AuditReport) -> None:
    print(f"tanzim v{report.tool_version} | source={report.source_path}")
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
            print(
                f"           impact: {f.estimated_waste_kwh:,.1f} kWh | "
                f"{f.estimated_cost_irr:,.0f} IRR"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tanzim", description="Offline BMS/SCADA silent-fault auditor.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_audit = sub.add_parser("audit", help="Audit a BMS/SCADA CSV or JSONL file.")
    p_audit.add_argument("file", help="Path to telemetry .csv or .jsonl")
    p_audit.add_argument("--demand-cap", type=float, default=None, help="Contracted peak demand cap (kW)")
    p_audit.add_argument("--price-irr", type=float, default=12_000.0, help="Base electricity rate (IRR/kWh)")
    p_audit.add_argument("--json-out", type=str, default=None, help="Write provenance JSON report to path")
    p_audit.add_argument("--ticket", choices=("fa", "en"), default=None, help="Generate technician work order via Ollama")
    p_audit.add_argument("--model", type=str, default="gemma3:12b", help="Local Ollama model name")

    p_demo = sub.add_parser("demo", help="Generate a synthetic Tehran summer BMS dataset and audit it.")
    p_demo.add_argument("--out-csv", type=str, default="tehran_bms_demo.csv")
    p_demo.add_argument("--demand-cap", type=float, default=180.0)
    p_demo.add_argument("--clean", action="store_true", help="Generate healthy baseline without injected faults")

    args = parser.parse_args(argv)

    if args.cmd == "demo":
        pts = generate_tehran_summer_bms(days=14, step_minutes=5, inject_faults=not args.clean)
        csv_path = write_telemetry_csv(pts, args.out_csv)
        cfg = AuditConfig(contracted_demand_kw=args.demand_cap)
        report = audit_file(csv_path, config=cfg)
        _print_report(report)
        return 0

    if args.cmd == "audit":
        cfg = AuditConfig(
            contracted_demand_kw=args.demand_cap,
            base_kwh_price_irr=args.price_irr,
        )
        report = audit_file(args.file, config=cfg)
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

    return 1


if __name__ == "__main__":
    raise SystemExit(main())