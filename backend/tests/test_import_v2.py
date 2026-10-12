"""新版數據庫（數據庫-1008.xlsx）匯入與 Level 3 點檢監控。

新版差異：KPOV 庫新增 OP 人工站（設備 A0001–A0008 來自「設備對應參考」）、
告警拆成「鎖附設備告警」＋「塗覆設備告警」、修護報表偵測欄語意改變、
新增 PCN / ECN 紀錄與高風險項點檢。
"""
from __future__ import annotations

import collections
import datetime as dt
import pathlib

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.importer.excel import import_workbook, parse_interval_hours
from app.models import (
    ArDevice,
    ArInspection,
    DimEquipment,
    FactAlarm,
    FactChangeRecord,
    FactCheckItem,
    FactKpov,
    FactLevelEvent,
    FactRepair,
)
from app.services.check_monitor import check_items, monitor_rows

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
RAW = ROOT / "raw_data.xlsx"
V2 = ROOT / "數據庫-1008.xlsx"

pytestmark = pytest.mark.skipif(not V2.exists(), reason="數據庫-1008.xlsx 不存在")


@pytest.fixture(scope="module")
def imported():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    batch, report = import_workbook(session, str(V2), V2.name)
    yield session, batch, report
    session.close()


def _kpovs(session, batch, **where):
    query = select(FactKpov).where(FactKpov.batch_id == batch.id)
    for field, value in where.items():
        query = query.where(getattr(FactKpov, field) == value)
    return session.scalars(query).all()


def test_op_stations_get_equipment_from_reference(imported):
    session, batch, report = imported
    op = _kpovs(session, batch, attribute1="OP")
    assert len(op) == 87  # 「ACME 導入 / 8站」小計列不算
    assert report.row_counts["kpovOp"] == 87
    by_station = {(k.station_group, k.station, k.equipment_code) for k in op}
    assert ("人工1", "插線/理線", "A0001") in by_station
    assert ("人工4", "固定銅排/ 電感", "A0004") in by_station
    assert ("人工7", "固定絕緣片/PWB板", "A0007") in by_station
    assert all(k.equipment_code for k in op)

    codes = set(session.scalars(select(DimEquipment.equipment_code).where(DimEquipment.batch_id == batch.id)))
    assert {f"A000{i}" for i in range(1, 9)} <= codes


def test_station_column_uses_last_duplicate(imported):
    session, batch, _ = imported
    ctp = _kpovs(session, batch, equipment_code="OT00420112")
    assert {k.station for k in ctp} == {"鎖PWB"}
    assert {k.station_group for k in ctp} == {"自動1"}


def test_auto3_is_ot00420118(imported):
    session, batch, report = imported
    auto3 = _kpovs(session, batch, station_group="自動3")
    assert {k.equipment_code for k in auto3} == {"OT00420118"}
    assert len(auto3) == 26
    assert any("OT00420118" in w for w in report.warnings)


def test_alarms_union_screw_and_coating(imported):
    session, batch, report = imported
    assert report.row_counts["alarmsScrew"] > 9000
    assert report.row_counts["alarmsCoating"] == 200
    counts = collections.Counter(
        session.scalars(select(FactAlarm.source).where(FactAlarm.batch_id == batch.id))
    )
    assert counts["鎖附"] == report.row_counts["alarmsScrew"]
    coating = session.scalars(
        select(FactAlarm).where(FactAlarm.batch_id == batch.id, FactAlarm.source == "塗覆").limit(1)
    ).one()
    assert (coating.equipment_code, coating.kpov_no, coating.kpov_name) == ("OT00400010", "K00299", "噴塗偏移")
    assert coating.period == "202512"


def test_repair_op_rows_resolved_by_station(imported):
    session, batch, report = imported
    assert report.skipped_repair_rows == []
    rows = session.scalars(
        select(FactRepair).where(FactRepair.batch_id == batch.id, FactRepair.station == "固定銅排/ 電感")
    ).all()
    assert rows and {r.equipment_code for r in rows} == {"A0004"}


def test_repair_v2_method_semantics(imported):
    """新版：無後綴 = 惡化（DEGRADE）、(變化後) = 改善（IMPROVE）。"""
    session, batch, _ = imported
    events = session.scalars(
        select(FactLevelEvent).where(
            FactLevelEvent.batch_id == batch.id,
            FactLevelEvent.kpov_no == "K00004",
            FactLevelEvent.equipment_code == "OT00420118",
        )
    ).all()
    degrade = [e for e in events if e.event_type == "DEGRADE"]
    improve = [e for e in events if e.event_type == "IMPROVE"]
    assert degrade and all(e.small_y_score_after == 7 for e in degrade)
    assert improve and all(e.small_y_score_after == 5 for e in improve)


def test_pcn_ecn_records(imported):
    session, batch, report = imported
    assert report.row_counts["pcnRecords"] == 136
    assert report.row_counts["ecnRecords"] == 1
    pcn = session.scalars(
        select(FactChangeRecord).where(
            FactChangeRecord.batch_id == batch.id,
            FactChangeRecord.kind == "PCN",
            FactChangeRecord.kpov_no == "K00002",
            FactChangeRecord.equipment_code == "OT00420102",
        )
    ).one()
    assert (pcn.level_before, pcn.level_after) == ("Level 3", "Level 1")
    ecn = session.scalars(
        select(FactChangeRecord).where(FactChangeRecord.batch_id == batch.id, FactChangeRecord.kind == "ECN")
    ).one()
    # NA = 全廠
    assert ecn.station is None and ecn.equipment_code is None and ecn.ecn_no == "104-25B067"


def test_check_items_resolve_op_aliases(imported):
    session, batch, report = imported
    items = session.scalars(select(FactCheckItem).where(FactCheckItem.batch_id == batch.id)).all()
    assert report.row_counts["checkItems"] == len(items) == 11
    by_station = {i.station: i.equipment_code for i in items}
    assert by_station["固定絕緣片"] == "A0007"
    assert by_station["鎖軟銅排2"] == "A0005"
    assert by_station["軟銅排1"] == "A0006"
    assert by_station["鎖PWB"] == "OT00420112"
    assert all(float(i.interval_hours) == 2 for i in items)


def test_parse_interval_hours():
    assert parse_interval_hours("開線/班、巡檢: 2h/次") == 2
    assert parse_interval_hours("每 4 小時") == 4
    assert parse_interval_hours(None) == 2


def test_check_monitor_status(imported):
    session, batch, _ = imported
    items = check_items(session, batch.id, {"OT00420112"})
    assert len(items) == 3
    now = dt.datetime(2026, 10, 8, 12, 0, tzinfo=dt.timezone.utc)
    assert {r["status"] for r in monitor_rows(session, items, now)} == {"never"}

    session.add(ArDevice(marker_id=5, name="鎖PWB", equipment_code="OT00420112"))
    first, second, third = items
    for item, status, hours_ago in ((first, "ok", 1), (second, "ok", 3), (third, "warn", 0.5)):
        session.add(
            ArInspection(
                marker_id=5,
                status=status,
                inspected_at=now - dt.timedelta(hours=hours_ago),
                equipment_code=item.equipment_code,
                kpov_no=item.kpov_no,
                check_content=item.check_content,
            )
        )
    session.flush()
    rows = {r["id"]: r for r in monitor_rows(session, items, now)}
    assert rows[first.id]["status"] == "ok"
    assert rows[second.id]["status"] == "overdue"
    assert rows[third.id]["status"] == "warn"
    assert rows[first.id]["nextDueAt"].startswith("2026-10-08T13:00")
    session.rollback()


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_legacy_then_v2_import():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        import_workbook(session, str(RAW), RAW.name)
        batch, report = import_workbook(session, str(V2), V2.name)
        # 新檔沒有 Dim_Equipment：沿用前批，再補上 OP 設備
        assert any("Dim_Equipment" in w for w in report.warnings)
        codes = set(
            session.scalars(select(DimEquipment.equipment_code).where(DimEquipment.batch_id == batch.id))
        )
        assert "A0001" in codes and "OT00420118" in codes
        assert report.row_counts["kpovOp"] == 87


def _local(hour: int, minute: int = 0, day: int = 8) -> dt.datetime:
    """廠區當地時間（UTC+8）-> UTC。"""
    site = dt.timezone(dt.timedelta(hours=8))
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=site).astimezone(dt.timezone.utc)


@pytest.mark.parametrize(
    ("now", "name", "start"),
    [
        (_local(9), "日班", _local(8)),
        (_local(19), "日班", _local(8)),  # 18–20 空檔：顯示剛結束的日班
        (_local(23), "夜班", _local(20)),
        (_local(3), "夜班", _local(20, day=7)),  # 跨午夜
        (_local(7), "夜班", _local(20, day=7)),  # 06–08 空檔
    ],
)
def test_current_shift(now, name, start):
    from app.services.check_monitor import current_shift

    shift = current_shift(now)
    assert shift["name"] == name
    assert shift["start"] == start
    assert shift["end"] - shift["start"] == dt.timedelta(hours=10)


def test_shift_slots_progress(imported):
    """一班 5 格，每格 20%；同一時段多次只算一格；異常算完成但標紅。"""
    session, batch, _ = imported
    item = check_items(session, batch.id, {"OT00420112"})[0]
    session.add(ArDevice(marker_id=6, name="鎖PWB", equipment_code="OT00420112"))
    for hour, minute, status in ((8, 30, "ok"), (9, 10, "ok"), (10, 5, "warn")):
        session.add(
            ArInspection(
                marker_id=6,
                status=status,
                inspected_at=_local(hour, minute),
                equipment_code=item.equipment_code,
                kpov_no=item.kpov_no,
                check_content=item.check_content,
            )
        )
    session.flush()
    row = monitor_rows(session, [item], now=_local(15))[0]
    assert [s["state"] for s in row["slots"]] == ["ok", "warn", "missed", "current", "upcoming"]
    assert row["completed"] == 2
    assert row["progress"] == 40
    session.rollback()


def test_op_pcn_equipment_resolved_by_station(imported):
    """OP 站的 PCN 沒填設備ID，依影響站別查「設備對應參考」補上。"""
    session, batch, _ = imported
    op = session.scalars(
        select(FactChangeRecord).where(
            FactChangeRecord.batch_id == batch.id,
            FactChangeRecord.kind == "PCN",
            FactChangeRecord.station == "鎖後蓋",
        )
    ).all()
    assert op and {r.equipment_code for r in op} == {"A0003"}
    kpovs = {(k.kpov_no, k.equipment_code) for k in _kpovs(session, batch, attribute1="OP")}
    assert sum((r.kpov_no, r.equipment_code) in kpovs for r in op) == len(op)


V3 = ROOT / "數據庫-1011.xlsx"


@pytest.mark.skipif(not V3.exists(), reason="數據庫-1011.xlsx 不存在")
def test_1011_improve_uses_excel_time_after_1008():
    """1011 版：改善事件用修護報表的「改善時間」，不再是匯入時間；
    「設備對應參考」少了 OP 區時沿用前批對照；鎖銅排設備強制為 OT00420118。"""
    from app.services.lifecycle import build_states

    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        import_workbook(session, str(V2), V2.name)
        batch, report = import_workbook(session, str(V3), V3.name)

        assert report.skipped_repair_rows == []
        assert {k.equipment_code for k in _kpovs(session, batch, attribute1="OP")} == {
            f"A000{i}" for i in range(1, 9)
        }
        by_station = collections.Counter(
            (k.station, k.equipment_code) for k in _kpovs(session, batch, attribute1="CTP")
        )
        assert by_station[("鎖銅排", "OT00420118")] == 26
        assert by_station[("鎖電感", "OT00420104")] == 26
        codes = set(session.scalars(select(DimEquipment.equipment_code).where(DimEquipment.batch_id == batch.id)))
        assert "OT00420118" in codes

        improves = session.scalars(
            select(FactLevelEvent).where(
                FactLevelEvent.batch_id == batch.id, FactLevelEvent.event_type == "IMPROVE"
            )
        ).all()
        dates = {e.effective_at.date() for e in improves}
        assert dt.date(2025, 11, 17) in dates
        # 每筆改善都對應到維修紀錄的改善時間，沒有任何一筆落在匯入時間
        repair_times = {r.improvement_effective_at.date() for r in session.scalars(
            select(FactRepair).where(FactRepair.batch_id == batch.id)) if r.improvement_effective_at}
        assert dates <= repair_times

        # 未來的改善（預計改善）不得提前影響現況等級
        before = dt.datetime(2026, 10, 13, tzinfo=dt.timezone.utc)
        after = dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc)
        key = ("K00049", "A0004")
        state_before = next(s for s in build_states(session, batch.id, as_of=before) if (s.kpov.kpov_no, s.kpov.equipment_code) == key)
        state_after = next(s for s in build_states(session, batch.id, as_of=after) if (s.kpov.kpov_no, s.kpov.equipment_code) == key)
        assert state_before.level_current != state_after.level_current


def test_improve_without_time_is_not_import_time(imported):
    """有「改善時間」欄但未填：不產生改善事件，也不用匯入時間代替。"""
    from app.importer.level_events import derive_level_events
    from app.importer.excel import ImportReport

    session, batch, _ = imported
    repair = session.scalars(
        select(FactRepair).where(FactRepair.batch_id == batch.id, FactRepair.small_y_method_improved.is_not(None))
    ).first()
    saved = repair.improvement_effective_at
    repair.improvement_effective_at = None
    report = ImportReport()
    session.query(FactLevelEvent).filter(FactLevelEvent.batch_id == batch.id).delete()
    derive_level_events(session, batch, [repair], {}, report, improve_time_fallback=False)
    assert not any(e["eventType"] == "IMPROVE" for e in report.level_events)
    assert any("未填改善時間" in w for w in report.warnings)
    repair.improvement_effective_at = saved
    session.rollback()


def test_photo_inspection_counts_in_monitor(imported):
    session, batch, _ = imported
    from app.models import CheckPhotoInspection

    item = check_items(session, batch.id, {"A0007"})[0]
    now = _local(15)
    session.add(
        CheckPhotoInspection(
            equipment_code=item.equipment_code,
            kpov_no=item.kpov_no,
            check_content=item.check_content,
            status="ok",
            photo_url="/api/ar/uploads/checks/x.jpg",
            inspected_at=_local(14, 30),
        )
    )
    session.flush()
    row = monitor_rows(session, [item], now=now)[0]
    assert row["slots"][3]["state"] == "ok"
    assert row["slots"][3]["photoUrl"] == "/api/ar/uploads/checks/x.jpg"
    assert row["lastPhotoUrl"] == "/api/ar/uploads/checks/x.jpg"
    session.rollback()


@pytest.mark.skipif(not V3.exists(), reason="數據庫-1011.xlsx 不存在")
def test_1011_into_empty_db_uses_default_op_mapping():
    """1011 版沒有 OP 對照區、資料庫也沒有前批：以內建 OP 對照補上 A000N。"""
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        batch, report = import_workbook(session, str(V3), V3.name)
        assert report.skipped_repair_rows == []
        assert report.row_counts["repairs"] == 27
        op = _kpovs(session, batch, attribute1="OP")
        assert {k.equipment_code for k in op} == {f"A000{i}" for i in range(1, 9)}
        codes = set(session.scalars(select(DimEquipment.equipment_code).where(DimEquipment.batch_id == batch.id)))
        assert {f"A000{i}" for i in range(1, 9)} <= codes
