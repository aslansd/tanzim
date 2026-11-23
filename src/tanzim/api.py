import tempfile
from pathlib import Path
from typing import Any

from .__version__ import __version__
from .engine import audit_file
from .llm_tickets import generate_work_order
from .mv import diff_files
from .schema import AuditConfig

RTL_DASHBOARD_HTML = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>تنظیم | ممیزی هوشمند انرژی و خطاهای پنهان BMS/SCADA</title>
  <style>
    :root { --bg:#0f172a; --card:#1e293b; --border:#334155; --text:#f8fafc; --muted:#94a3b8; --accent:#10b981; --warn:#f59e0b; --crit:#ef4444; }
    * { box-sizing:border-box; font-family: Tahoma, Vazirmatn, system-ui, sans-serif; }
    body { margin:0; background:var(--bg); color:var(--text); padding:24px; line-height:1.7; }
    .wrap { max-width:1100px; margin:0 auto; }
    header { display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid var(--border); padding-bottom:16px; margin-bottom:24px; }
    h1 { margin:0; font-size:1.5rem; }
    .badge { background:#064e3b; color:#6ee7b7; padding:4px 10px; border-radius:999px; font-size:0.85rem; }
    .tabs { display:flex; gap:10px; margin-bottom:20px; }
    .tab { background:var(--card); color:var(--text); border:1px solid var(--border); padding:10px 18px; border-radius:8px; cursor:pointer; }
    .tab.active { background:var(--accent); color:#022c22; font-weight:bold; border-color:var(--accent); }
    .card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:20px; margin-bottom:20px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:12px; margin:16px 0; }
    .kpi { background:#0f172a; border:1px solid var(--border); border-radius:10px; padding:14px; }
    .kpi .lbl { color:var(--muted); font-size:0.82rem; }
    .kpi .val { font-size:1.3rem; font-weight:bold; margin-top:4px; direction:ltr; text-align:right; }
    label { display:block; font-size:0.88rem; color:var(--muted); margin-bottom:6px; }
    input, select { width:100%; padding:9px 10px; border-radius:8px; border:1px solid var(--border); background:#0f172a; color:var(--text); }
    button.primary { background:var(--accent); color:#022c22; border:none; padding:11px 22px; border-radius:8px; font-weight:bold; cursor:pointer; margin-top:14px; }
    .finding { border-right:4px solid var(--warn); background:#0f172a; padding:12px 16px; border-radius:8px; margin-bottom:10px; }
    .finding.critical { border-right-color:var(--crit); }
    pre { background:#020617; padding:14px; border-radius:8px; overflow:auto; white-space:pre-wrap; font-size:0.9rem; }
    .hidden { display:none; }
  </style>
</head>
<body>
<div class="wrap">
  <header>
    <div>
      <h1>تنظیم (tanzim) — ممیزی آفلاین BMS / SCADA</h1>
      <div style="color:var(--muted);font-size:0.9rem;">کشف خطاهای پنهان انرژی، تعرفه پیک ایران و اندازه‌گیری و صحه‌گذاری صرفه‌جویی (M&amp;V)</div>
    </div>
    <span class="badge">v__VERSION__ · ۱۰۰٪ آفلاین</span>
  </header>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('audit')">۱. ممیزی فایل لاگ (Audit)</button>
    <button class="tab" onclick="switchTab('mv')">۲. صحه‌گذاری قبل/بعد (M&amp;V Diff)</button>
  </div>

  <section id="panel-audit" class="card">
    <div class="grid">
      <div><label>فایل CSV / JSONL (زیمنس، اشنایدر، مدباس یا عمومی)</label><input id="audit-file" type="file" accept=".csv,.jsonl,.ndjson" /></div>
      <div><label>آداپتور BMS</label>
        <select id="audit-adapter"><option value="auto">تشخیص خودکار (Auto)</option><option value="siemens">Siemens Desigo</option><option value="schneider">Schneider EcoStruxure</option><option value="modbus">Modbus Logger</option><option value="generic">Generic CSV</option></select>
      </div>
      <div><label>دیماند قراردادی (kW)</label><input id="demand-cap" type="number" value="180" /></div>
      <div><label>تعرفه پایه برق (ریال / kWh)</label><input id="price-irr" type="number" value="12000" /></div>
    </div>
    <div class="grid">
      <div><label>تولید دستورکار فارسی با Ollama محلی؟</label><select id="gen-ticket"><option value="false">خیر (سریع)</option><option value="true">بله (Ollama محلی)</option></select></div>
      <div><label>نام مدل Ollama</label><input id="ollama-model" type="text" value="gemma3:12b" /></div>
    </div>
    <button class="primary" onclick="runAudit()">اجرای ممیزی انرژی</button>
    <div id="audit-out" style="margin-top:20px;"></div>
  </section>

  <section id="panel-mv" class="card hidden">
    <div class="grid">
      <div><label>فایل دوره پایه (قبل از اصلاح)</label><input id="mv-before" type="file" accept=".csv,.jsonl,.json" /></div>
      <div><label>فایل دوره جدید (پس از اصلاح)</label><input id="mv-after" type="file" accept=".csv,.jsonl,.json" /></div>
      <div><label>دیماند قراردادی (kW)</label><input id="mv-cap" type="number" value="180" /></div>
      <div><label>تعرفه پایه برق (ریال / kWh)</label><input id="mv-price" type="number" value="12000" /></div>
    </div>
    <button class="primary" onclick="runMV()">محاسبه صرفه‌جویی تعدیل‌شده با دما (IPMVP)</button>
    <div id="mv-out" style="margin-top:20px;"></div>
  </section>
</div>
<script>
function switchTab(id){
  document.querySelectorAll('.tab').forEach((t,i)=>t.classList.toggle('active',(i===0&&id==='audit')||(i===1&&id==='mv')));
  document.getElementById('panel-audit').classList.toggle('hidden', id!=='audit');
  document.getElementById('panel-mv').classList.toggle('hidden', id!=='mv');
}
async function runAudit(){
  const f = document.getElementById('audit-file').files[0];
  if(!f){ alert('لطفاً یک فایل CSV انتخاب کنید.'); return; }
  const fd = new FormData();
  fd.append('file', f);
  fd.append('adapter', document.getElementById('audit-adapter').value);
  fd.append('demand_cap', document.getElementById('demand-cap').value);
  fd.append('price_irr', document.getElementById('price-irr').value);
  fd.append('ticket', document.getElementById('gen-ticket').value);
  fd.append('model', document.getElementById('ollama-model').value);
  const out = document.getElementById('audit-out');
  out.innerHTML = 'در حال تحلیل...';
  const r = await fetch('/api/audit', {method:'POST', body:fd});
  const d = await r.json();
  if(!r.ok){ out.innerHTML = '<pre>'+JSON.stringify(d,null,2)+'</pre>'; return; }
  const rep = d.report;
  let html = `<div class="grid">
    <div class="kpi"><div class="lbl">آداپتور تشخیص‌داده‌شده</div><div class="val">${rep.adapter_info?.adapter || 'generic'}</div></div>
    <div class="kpi"><div class="lbl">کل مصرف (kWh)</div><div class="val">${rep.total_energy_kwh.toLocaleString()}</div></div>
    <div class="kpi"><div class="lbl">اتلاف برآوردی (kWh)</div><div class="val">${rep.total_estimated_waste_kwh.toLocaleString()}</div></div>
    <div class="kpi"><div class="lbl">صرفه‌جویی بالقوه (ریال)</div><div class="val">${rep.total_estimated_cost_irr.toLocaleString()}</div></div>
  </div>`;
  html += rep.findings.length ? rep.findings.map(x=>`<div class="finding ${x.severity}"><b>[${x.severity.toUpperCase()}] ${x.code}</b> — ${x.title}<br/>${x.summary}<br/><small>اتلاف: ${x.estimated_waste_kwh} kWh | هزینه: ${x.estimated_cost_irr.toLocaleString()} ریال</small></div>`).join('') : '<div class="finding">هیچ خطای پنهانی یافت نشد.</div>';
  if(d.ticket){ html += '<h3>دستور کار نگهداری (Ollama)</h3><pre>'+d.ticket+'</pre>'; }
  out.innerHTML = html;
}
async function runMV(){
  const fb = document.getElementById('mv-before').files[0];
  const fa = document.getElementById('mv-after').files[0];
  if(!fb || !fa){ alert('هر دو فایل قبل و بعد را انتخاب کنید.'); return; }
  const fd = new FormData();
  fd.append('before_file', fb);
  fd.append('after_file', fa);
  fd.append('demand_cap', document.getElementById('mv-cap').value);
  fd.append('price_irr', document.getElementById('mv-price').value);
  const out = document.getElementById('mv-out');
  out.innerHTML = 'در حال محاسبه M&V...';
  const r = await fetch('/api/diff', {method:'POST', body:fd});
  const d = await r.json();
  if(!r.ok){ out.innerHTML = '<pre>'+JSON.stringify(d,null,2)+'</pre>'; return; }
  out.innerHTML = `<div class="grid">
    <div class="kpi"><div class="lbl">حکم M&amp;V</div><div class="val">${d.verdict}</div></div>
    <div class="kpi"><div class="lbl">صرفه‌جویی تاییدشده (kWh)</div><div class="val">${d.verified_savings_kwh.toLocaleString()} (${d.verified_savings_pct}%)</div></div>
    <div class="kpi"><div class="lbl">صرفه‌جویی ریالی</div><div class="val">${d.verified_cost_savings_irr.toLocaleString()}</div></div>
    <div class="kpi"><div class="lbl">تعدیل دمایی (R²)</div><div class="val">${d.weather_normalized ? 'بله ('+(d.baseline_r2 ?? '-')+')' : 'خیر'}</div></div>
  </div>
  <div class="finding"><b>خطاهای برطرف‌شده:</b> ${d.resolved_findings.join(', ') || 'هیچ'}<br/>
  <b>خطاهای باقی‌مانده:</b> ${d.persisting_findings.join(', ') || 'هیچ'}<br/>
  <b>خطاهای جدید:</b> ${d.new_findings.join(', ') || 'هیچ'}</div>`;
}
</script>
</body>
</html>
""".replace("__VERSION__", __version__)


def create_app() -> Any:
    try:
        from fastapi import FastAPI, File, Form, HTTPException, UploadFile
        from fastapi.responses import HTMLResponse
    except ImportError as exc:
        raise ImportError(
            "FastAPI dashboard requires web extras. Install with: pip install 'tanzim[web]'"
        ) from exc

    app = FastAPI(title="tanzim BMS/SCADA Auditor", version=__version__)

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return RTL_DASHBOARD_HTML

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.post("/api/audit")
    async def api_audit(
        file: UploadFile = File(...),
        adapter: str = Form("auto"),
        demand_cap: float | None = Form(None),
        price_irr: float = Form(12_000.0),
        ticket: bool = Form(False),
        model: str = Form("gemma3:12b"),
    ) -> dict[str, Any]:
        suffix = Path(file.filename or "upload.csv").suffix or ".csv"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(await file.read())
            tmp_path = Path(tmp.name)
        try:
            cfg = AuditConfig(contracted_demand_kw=demand_cap, base_kwh_price_irr=price_irr)
            report = audit_file(tmp_path, config=cfg, adapter=adapter)
            work_order = generate_work_order(report, lang="fa", model=model) if ticket else None
            return {"report": report.to_dict(), "ticket": work_order}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            tmp_path.unlink(missing_ok=True)

    @app.post("/api/diff")
    async def api_diff(
        before_file: UploadFile = File(...),
        after_file: UploadFile = File(...),
        adapter: str = Form("auto"),
        demand_cap: float | None = Form(None),
        price_irr: float = Form(12_000.0),
    ) -> dict[str, Any]:
        sb = Path(before_file.filename or "before.csv").suffix or ".csv"
        sa = Path(after_file.filename or "after.csv").suffix or ".csv"
        with tempfile.NamedTemporaryFile(suffix=sb, delete=False) as tb, tempfile.NamedTemporaryFile(suffix=sa, delete=False) as ta:
            tb.write(await before_file.read())
            ta.write(await after_file.read())
            pb, pa = Path(tb.name), Path(ta.name)
        try:
            cfg = AuditConfig(contracted_demand_kw=demand_cap, base_kwh_price_irr=price_irr)
            mv = diff_files(pb, pa, config=cfg, adapter=adapter)
            return mv.to_dict()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            pb.unlink(missing_ok=True)
            pa.unlink(missing_ok=True)

    return app
