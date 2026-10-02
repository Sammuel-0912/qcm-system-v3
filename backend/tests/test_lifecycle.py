"""以真實 raw_data.xlsx 做端到端驗收 — spec.md §9 AC-1 ~ AC-15。"""
from __future__ import annotations

import os
import pathlib

import pytest

RAW = pathlib.Path(__file__).resolve().parent.parent.parent / "raw_data.xlsx"


@pytest.fixture(scope="module")
def imported(tmp_path_factory):
    db = tmp_path_factory.mktemp("db") / "qcm.db"
    os.environ["QCM_DATABASE_URL"] = f"sqlite:///{db}"

    from app.db import SessionLocal, init_db
    from app.importer.excel import import_workbook

    init_db()
    session = SessionLocal()
    batch, report = import_workbook(session, str(RAW), "raw_data.xlsx")
    yield session, batch, report
    session.close()


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_ac1_row_counts(imported):
    _, _, report = imported
    counts = report.row_counts
    assert counts["kpov"] == 267          # 244 筆 CTP + 23 筆 OP
    assert counts["kpovCtp"] == 244       # 第 246-247 列為空白列與殘留公式，非資料
    assert counts["kpovOp"] == 23         # OP 站無設備代碼，不得被匯入器丟棄
    assert counts["alarms"] == 17069
    assert counts["equipment"] == 132
    assert counts["errorCodes"] == 8
    assert counts["detectionMethods"] == 10
    assert counts["repairs"] == 3


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_ac2_level_mismatch_detected(imported):
    _, _, report = imported
    assert len(report.level_mismatches) == 1
    bad = report.level_mismatches[0]
    assert bad["smallY"] == 7 and bad["bigY"] == 7
    assert bad["sourceLevel"] == "Level 0"
    assert bad["computedLevel"] == "Level 3"


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_ac3_baseline_distribution(imported):
    session, batch, _ = imported
    from app.services.lifecycle import build_states, summarize

    states = build_states(session, batch.id)
    ctp = [s for s in states if s.kpov.attribute1 == "CTP"]
    assert summarize(ctp, "baseline") == {
        "level0": 160, "level1": 82, "level2": 0, "level3": 2, "unrated": 0, "total": 244,
    }
    # OP 人工站的品控力明顯較差，且是 Level 2 的唯一來源
    op = [s for s in states if s.kpov.attribute1 == "OP"]
    assert summarize(op, "baseline") == {
        "level0": 1, "level1": 13, "level2": 4, "level3": 5, "unrated": 0, "total": 23,
    }


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_ac10_six_level_events(imported):
    _, _, report = imported
    assert len(report.level_events) == 6  # 3 筆維修 × (DEGRADE + IMPROVE)


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_ac11_k00004_history(imported):
    session, batch, _ = imported
    from app.services.lifecycle import build_states

    states = {(s.kpov.kpov_no, s.kpov.equipment_code): s for s in build_states(session, batch.id)}
    target = states[("K00004", "OT00420118")]

    assert target.level_baseline == 1
    first = target.events[0]
    assert first.event_type == "DEGRADE"
    assert (first.level_before, first.level_after) == (1, 2)
    assert first.transition == "ESCALATED"
    assert first.small_y_score_before == 3 and first.small_y_score_after == 7
    assert first.big_y_score_before == 7 and first.big_y_score_after == 5

    improve = [e for e in target.events if e.event_type == "IMPROVE"][0]
    assert improve.level_after == 0
    assert improve.transition == "IMPROVED"
    assert target.level_current == 0


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_ac12_other_equipment_not_affected(imported):
    session, batch, _ = imported
    from app.services.lifecycle import build_states

    states = build_states(session, batch.id)
    others = [
        s
        for s in states
        if s.kpov.kpov_no == "K00004"
        and s.kpov.attribute1 == "CTP"
        and s.kpov.equipment_code not in {"OT00420118", "OT00420104"}
    ]
    assert len(others) == 7
    assert all(s.level_current == 1 for s in others), "未出現在維修報表的設備不得被連坐降級"
    assert all(not s.events for s in others)

    # OP 站也叫 K00004（鎖後蓋、鎖銅排），同樣不得被 CTP 的事件影響
    op_same_code = [s for s in states if s.kpov.kpov_no == "K00004" and s.kpov.attribute1 == "OP"]
    assert len(op_same_code) == 2
    assert all(not s.events for s in op_same_code)


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_op_rows_have_no_equipment_and_no_events(imported):
    """OP 站沒有設備代碼，因此不會有等級異動事件（事件靠維修報表的設備 ID 定位）。"""
    session, batch, _ = imported
    from app.services.lifecycle import build_states

    op = [s for s in build_states(session, batch.id) if s.kpov.attribute1 == "OP"]
    assert len(op) == 23
    assert all(s.kpov.equipment_code is None for s in op)
    assert all(not s.events for s in op)
    assert all(s.target_id.startswith("op:") for s in op)


def test_station_name_is_not_unique_across_attributes(imported):
    """「鎖銅排」同時是 CTP 站與 OP 站，兩者必須各自獨立。"""
    session, batch, _ = imported
    from app.services.lifecycle import build_states

    states = build_states(session, batch.id)
    copper = [s for s in states if s.kpov.station == "鎖銅排"]
    ctp = [s for s in copper if s.kpov.attribute1 == "CTP"]
    op = [s for s in copper if s.kpov.attribute1 == "OP"]
    assert len(ctp) == 26 and len(op) == 8
    assert {s.target_id for s in ctp} == {"equip:OT00420118"}
    assert {s.target_id for s in op} == {"op:鎖銅排"}


def test_ac13_baseline_differs_from_current(imported):
    session, batch, _ = imported
    from app.services.lifecycle import build_states, summarize

    states = [s for s in build_states(session, batch.id) if s.kpov.attribute1 == "CTP"]
    baseline = summarize(states, "baseline")
    current = summarize(states, "current")
    assert baseline != current
    assert current["level0"] == baseline["level0"] + 2
    assert current["level1"] == baseline["level1"] - 2


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_event_chronology(imported):
    """較早的不良事件不得被較晚才生效的改善影響 level_before。"""
    session, batch, _ = imported
    from app.services.lifecycle import build_states

    states = {(s.kpov.kpov_no, s.kpov.equipment_code): s for s in build_states(session, batch.id)}
    events = states[("K00004", "OT00420118")].events
    assert [e.event_type for e in events] == ["DEGRADE", "DEGRADE", "IMPROVE", "IMPROVE"]
    # 第二次不良發生時，第一次的改善尚未生效，因此仍處於 Level 2
    assert events[1].level_before == 2
    assert events[1].transition == "UNCHANGED"


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_ac14_import_is_idempotent(tmp_path):
    """同一檔案重複匯入，事件數不得翻倍（REQ-LIFE-05）。"""
    os.environ["QCM_DATABASE_URL"] = f"sqlite:///{tmp_path / 'idem.db'}"
    import importlib

    import app.config
    import app.db

    importlib.reload(app.config)
    importlib.reload(app.db)
    import app.models

    importlib.reload(app.models)
    from app.db import SessionLocal, init_db
    from app.importer.excel import import_workbook

    init_db()
    session = SessionLocal()
    _, first = import_workbook(session, str(RAW), "raw_data.xlsx")
    _, second = import_workbook(session, str(RAW), "raw_data.xlsx")
    assert len(first.level_events) == len(second.level_events) == 6
    session.close()


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_ac15_unknown_detection_method_is_reported(imported):
    """字典查無的偵測方式必須進錯誤報告，不得以 0 帶過。"""
    from app.importer.level_events import _resolve

    assert _resolve("機器偵測(已證實可靠)", {"機器偵測(已證實可靠)": 5}) == ("機器偵測(已證實可靠)", 5)
    assert _resolve("不存在的偵測方式", {"機器偵測(已證實可靠)": 5}) is None


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_detection_dictionary_parsed(imported):
    """偵測方式字典停在無表頭欄位，必須與維修紀錄分開解析（REQ-IMP-05）。"""
    session, batch, _ = imported
    from sqlalchemy import select

    from app.models import DimDetectionMethod

    rows = session.scalars(
        select(DimDetectionMethod).where(DimDetectionMethod.batch_id == batch.id)
    ).all()
    lookup = {r.method_name: r.score for r in rows}
    assert lookup == {
        "未建立": 10,
        "隨機稽查": 9,
        "人工檢測(未證實可靠)": 8,
        "機器偵測(未證實可靠)": 7,
        "人工檢測(已證實可靠)": 6,
        "機器偵測(已證實可靠)": 5,
        "機器自動偵測(製程下游)": 4,
        "機器自動偵測(站內)": 3,
        "機器偵測可偵測出失效原因且預防失效模式發生": 2,
        "失效模式不會實際發生": 1,
    }
    # 切點語意（spec.md §2.1）：>= 6 的方式都不是「已證實可靠的機器偵測」
    unreliable = {name for name, score in lookup.items() if score >= 6}
    assert unreliable == {"未建立", "隨機稽查", "人工檢測(未證實可靠)", "機器偵測(未證實可靠)", "人工檢測(已證實可靠)"}


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_repair_only_workbook_carries_over_previous_batch(tmp_path):
    """第二次匯入只放「修護報表」：其餘工作表沿用前一批次，事件照常推導。"""
    import openpyxl

    os.environ["QCM_DATABASE_URL"] = f"sqlite:///{tmp_path / 'carry.db'}"
    import importlib

    import app.config
    import app.db

    importlib.reload(app.config)
    importlib.reload(app.db)
    import app.models

    importlib.reload(app.models)
    from app.db import SessionLocal, init_db
    from app.importer.excel import ImportError_, import_workbook

    repair_only = tmp_path / "repair_only.xlsx"
    wb = openpyxl.load_workbook(RAW)
    for sheet in list(wb.worksheets):
        if not sheet.title.startswith("修護報表"):
            wb.remove(sheet)
    wb.save(repair_only)

    init_db()
    session = SessionLocal()

    # 首次匯入不可缺 Dim_Equipment / KPOV
    with pytest.raises(ImportError_):
        import_workbook(session, str(repair_only), "repair_only.xlsx")

    first_batch, first = import_workbook(session, str(RAW), "raw_data.xlsx")
    second_batch, second = import_workbook(session, str(repair_only), "repair_only.xlsx")

    assert second_batch.is_active and not first_batch.is_active
    for key in ("equipment", "kpov", "kpovOp", "kpovCtp", "errorCodes", "alarms", "repairs"):
        assert second.row_counts[key] == first.row_counts[key], key
    assert len(second.level_events) == len(first.level_events) == 6
    assert any("沿用批次" in w for w in second.warnings)
    assert second.row_counts["repairsUnchanged"] == first.row_counts["repairs"]
    assert second.row_counts["repairsNew"] == second.row_counts["repairsUpdated"] == 0
    session.close()


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_repair_records_merge_across_imports(tmp_path):
    """舊紀錄相同者略過、有變者更新、檔案中沒有的舊紀錄保留、新序號為新增。"""
    import openpyxl

    os.environ["QCM_DATABASE_URL"] = f"sqlite:///{tmp_path / 'merge.db'}"
    import importlib

    import app.config
    import app.db

    importlib.reload(app.config)
    importlib.reload(app.db)
    import app.models

    importlib.reload(app.models)
    from sqlalchemy import select

    from app.db import SessionLocal, init_db
    from app.importer import mapping as M
    from app.importer.excel import import_workbook
    from app.models import FactRepair

    wb = openpyxl.load_workbook(RAW)
    for sheet in list(wb.worksheets):
        if not sheet.title.startswith("修護報表"):
            wb.remove(sheet)
    ws = wb.worksheets[0]
    col = {M.normalize(c.value): c.column for c in ws[1] if c.value}
    serial, equip, kpov, remark = col["序號"], col["設備ID"], col["KPOV 编号"], col["維修備註"]
    records = [r for r in range(2, ws.max_row + 1) if ws.cell(r, equip).value and ws.cell(r, kpov).value]
    assert len(records) == 3
    changed, removed, template = records

    removed_serial = str(ws.cell(removed, serial).value)
    ws.cell(changed, remark).value = "已改善完成"
    # 只清掉維修紀錄欄位，同一列右側的偵測方式字典要保留
    for c in col.values():
        ws.cell(removed, c).value = None
    new_row = ws.max_row + 1
    for c in col.values():
        ws.cell(new_row, c).value = ws.cell(template, c).value
    ws.cell(new_row, serial).value = "NEW-001"
    merged_file = tmp_path / "merged.xlsx"
    wb.save(merged_file)

    init_db()
    session = SessionLocal()
    import_workbook(session, str(RAW), "raw_data.xlsx")
    batch, report = import_workbook(session, str(merged_file), "merged.xlsx")

    counts = report.row_counts
    assert counts["repairsNew"] == 1
    assert counts["repairsUpdated"] == 1
    assert counts["repairsUnchanged"] == 1
    assert counts["repairsCarried"] == 1
    assert counts["repairs"] == 4

    rows = session.scalars(select(FactRepair).where(FactRepair.batch_id == batch.id)).all()
    by_serial = {r.serial_no: r for r in rows}
    assert "NEW-001" in by_serial
    assert removed_serial in by_serial
    assert by_serial[str(ws.cell(changed, serial).value)].remark == "已改善完成"
    session.close()
