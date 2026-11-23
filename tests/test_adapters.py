from __future__ import annotations

from pathlib import Path

from tanzim import audit_file, detect_adapter, load_with_adapter


def test_siemens_desigo_adapter_preamble_semicolon_and_euro_decimals(tmp_path: Path) -> None:
    content = """Export Source;Siemens Desigo CC v5.1
Trend Definition;Tehran_Tower_CHW_Plant
Date;Time;B1.Plant.ActivePower_kW;OAT_Temp;CHW_SupTemp;CHW_RetTemp;HtgVlvPos;ClgVlvPos
01.07.2026;09:00:00;112,5;33,2;7,1;12,6;40,0;80,0
01.07.2026;09:30:00;115,0;34,0;7,2;12,7;42,0;82,0
01.07.2026;10:00:00;118,4;34,8;7,1;12,8;45,0;85,0
01.07.2026;10:30:00;120,1;35,5;7,2;12,6;45,0;88,0
"""
    p = tmp_path / "desigo_export.csv"
    p.write_text(content, encoding="utf-8")

    assert detect_adapter(p) == "siemens"
    pts, info = load_with_adapter(p)
    assert info.adapter == "siemens_desigo"
    assert info.delimiter == ";"
    assert info.skipped_preamble_lines == 2
    assert len(pts) == 4
    assert pts[0].power_kw == 112.5
    assert pts[0].outdoor_temp_c == 33.2

    report = audit_file(p)
    assert any(f.code == "SIMULTANEOUS_HEAT_COOL" for f in report.findings)


def test_schneider_ecostruxure_watts_to_kw_conversion(tmp_path: Path) -> None:
    content = """Report Generated: EcoStruxure Power Monitoring Expert
Site: Vanak Medical Center
Date/Time,Active Power Total (W),Outside Air Temp (°C),CHW Supply Temp,CHW Return Temp,Cooling Valve Cmd (%)
2026-07-01 10:00:00,85000,35.0,7.0,12.5,75
2026-07-01 10:15:00,87500,35.4,7.1,12.4,78
"""
    p = tmp_path / "pme_export.csv"
    p.write_text(content, encoding="utf-8")

    assert detect_adapter(p) == "schneider"
    pts, info = load_with_adapter(p)
    assert info.adapter == "schneider_ecostruxure"
    assert info.power_unit_scale == 0.001
    assert pts[0].power_kw == 85.0
    assert pts[1].power_kw == 87.5


def test_modbus_logger_unix_epoch_persian_digits_and_watts(tmp_path: Path) -> None:
    content = """# Modbus-RTU Logger Shamsabad Plant 2
unix_ts,slave_id,reg_40001_power_w,ir_30001_oat,ir_30002_chws,ir_30003_chwr
1782896400,1,۱۲۵۰۰۰,۳۶٫۵,۷٫۲,۱۲٫۸
1782897300,1,۱۲۸۵۰۰,۳۷٫۰,۷٫۱,۱۲٫۹
"""
    p = tmp_path / "shamsabad_modbus.csv"
    p.write_text(content, encoding="utf-8")

    assert detect_adapter(p) == "modbus"
    pts, info = load_with_adapter(p)
    assert info.adapter == "modbus_logger"
    assert info.power_unit_scale == 0.001
    assert pts[0].power_kw == 125.0
    assert pts[0].outdoor_temp_c == 36.5
