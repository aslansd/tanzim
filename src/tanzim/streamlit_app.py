from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

from tanzim import AuditConfig, __version__, audit_file, diff_files, generate_work_order

st.set_page_config(page_title="تنظیم | ممیزی انرژی BMS/SCADA", layout="wide")

st.markdown(
    """
    <style>
    html, body, [class*="css"] { direction: rtl; text-align: right; font-family: Tahoma, Vazirmatn, sans-serif; }
    [data-testid="stMetricValue"] { direction: ltr; text-align: right; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title(f"تنظیم (tanzim v{__version__}) — ممیزی آفلاین انرژی و خطاهای پنهان BMS/SCADA")
st.caption("پشتیبانی از خروجی Siemens Desigo، Schneider EcoStruxure، لاگرهای Modbus و تعرفه پیک برق ایران")

with st.sidebar:
    st.header("تنظیمات ممیزی")
    adapter = st.selectbox("آداپتور فایل", ["auto", "siemens", "schneider", "modbus", "generic"])
    demand_cap = st.number_input("دیماند قراردادی (kW)", min_value=0.0, value=180.0, step=10.0)
    price_irr = st.number_input("تعرفه پایه برق (ریال / kWh)", min_value=1000.0, value=12000.0, step=1000.0)
    ollama_model = st.text_input("مدل محلی Ollama", value="gemma3:12b")

cfg = AuditConfig(
    contracted_demand_kw=demand_cap if demand_cap > 0 else None,
    base_kwh_price_irr=price_irr,
)

tab_audit, tab_mv = st.tabs(["۱. ممیزی فایل لاگ (Audit)", "۲. صحه‌گذاری قبل و بعد (M&V Diff)"])

with tab_audit:
    up = st.file_uploader("فایل CSV یا JSONL را بارگذاری کنید", type=["csv", "jsonl", "ndjson"], key="audit_up")
    gen_ticket = st.checkbox("تولید دستور کار فنی به زبان فارسی با Ollama محلی", value=False)
    if up is not None and st.button("اجرای ممیزی", type="primary"):
        suffix = Path(up.name).suffix or ".csv"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(up.getvalue())
            tmp_path = Path(tmp.name)
        try:
            report = audit_file(tmp_path, config=cfg, adapter=adapter)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("آداپتور", report.adapter_info.adapter if report.adapter_info else "generic")
            c2.metric("کل مصرف (kWh)", f"{report.total_energy_kwh:,.1f}")
            c3.metric("اتلاف برآوردی (kWh)", f"{report.total_estimated_waste_kwh:,.1f}")
            c4.metric("صرفه‌جویی بالقوه (ریال)", f"{report.total_estimated_cost_irr:,.0f}")

            if not report.findings:
                st.success("هیچ خطای پنهان انرژی شناسایی نشد.")
            else:
                for f in report.findings:
                    box = st.error if f.severity.value == "critical" else st.warning
                    box(
                        f"**[{f.severity.value.upper()}] {f.code}** — {f.title}\n\n"
                        f"{f.summary}\n\n"
                        f"اتلاف: `{f.estimated_waste_kwh:,.1f} kWh` | صرفه‌جویی بالقوه: `{f.estimated_cost_irr:,.0f} IRR`"
                    )

            if gen_ticket:
                with st.spinner("در حال تولید دستور کار فارسی توسط Ollama..."):
                    ticket_text = generate_work_order(report, lang="fa", model=ollama_model)
                st.subheader("دستور کار نگهداری برای تیم تأسیسات")
                st.text_area("متن دستور کار", ticket_text, height=260)

            st.download_button(
                "دانلود گزارش اصالت‌سنجی‌شده (JSON)",
                data=json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
                file_name="tanzim_audit_report.json",
                mime="application/json",
            )
        finally:
            tmp_path.unlink(missing_ok=True)

with tab_mv:
    col_a, col_b = st.columns(2)
    with col_a:
        up_before = st.file_uploader("فایل دوره پایه (قبل از اصلاح)", type=["csv", "jsonl", "json"], key="mv_b")
    with col_b:
        up_after = st.file_uploader("فایل دوره جدید (پس از اصلاح)", type=["csv", "jsonl", "json"], key="mv_a")

    if up_before is not None and up_after is not None and st.button("محاسبه صرفه‌جویی M&V", type="primary"):
        sb = Path(up_before.name).suffix or ".csv"
        sa = Path(up_after.name).suffix or ".csv"
        with tempfile.NamedTemporaryFile(suffix=sb, delete=False) as tb, tempfile.NamedTemporaryFile(suffix=sa, delete=False) as ta:
            tb.write(up_before.getvalue())
            ta.write(up_after.getvalue())
            pb, pa = Path(tb.name), Path(ta.name)
        try:
            mv = diff_files(pb, pa, config=cfg, adapter=adapter)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("حکم M&V", mv.verdict)
            m2.metric("صرفه‌جویی تاییدشده (kWh)", f"{mv.verified_savings_kwh:,.1f} ({mv.verified_savings_pct:+.1f}%)")
            m3.metric("صرفه‌جویی ریالی", f"{mv.verified_cost_savings_irr:,.0f}")
            m4.metric("کاهش بار پیک (kW)", f"{mv.peak_reduction_kw:+.1f}")

            st.info(
                f"روش تعدیل دمایی: `{mv.normalization_method}` | "
                f"تعدیل با دما: `{mv.weather_normalized}` | `R² = {mv.baseline_r2}`"
            )
            st.write("**خطاهای برطرف‌شده:**", ", ".join(mv.resolved_findings) or "هیچ")
            st.write("**خطاهای باقی‌مانده:**", ", ".join(mv.persisting_findings) or "هیچ")
            st.write("**خطاهای جدید:**", ", ".join(mv.new_findings) or "هیچ")
            for note in mv.notes:
                st.caption(f"نکته: {note}")

            st.download_button(
                "دانلود گواهی M&V (JSON)",
                data=json.dumps(mv.to_dict(), ensure_ascii=False, indent=2),
                file_name="tanzim_mv_certificate.json",
                mime="application/json",
            )
        finally:
            pb.unlink(missing_ok=True)
            pa.unlink(missing_ok=True)
