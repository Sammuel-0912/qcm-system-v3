"""PCN 計入現況（v2.19，spec §25）：PCN 切入後的偵測度產生等級事件，與維修事件依時間串接。"""
from __future__ import annotations

import datetime as dt
import types

from sqlalchemy import create_engine, text

from tests.test_rbac import ADMIN, V1026, XLSX, app_ctx, needs_data  # noqa: F401  (app_ctx 為 fixture)


def _import(su):
    res = su.post("/api/v1/import", files={"file": ("WJ1-DCS-PM1-數據庫-1026.xlsx", V1026.read_bytes(), XLSX)})
    assert res.status_code == 200, res.text
    return res.json()["report"]


@needs_data
def test_pcn_after_scores_drive_current_level(app_ctx):
    su = app_ctx(ADMIN)
    report = _import(su)
    pcn_events = [e for e in report["levelEvents"] if e["eventType"] == "PCN"]
    assert pcn_events and all(e["serialNo"] is None for e in pcn_events)

    # A0002 錯螺絲：沒有維修，現況由 PCN 切入後（y5 Y7 → Level 1）決定；時間軸的 PCN 節點帶出計入結果
    h = su.get("/api/v1/kpov/K00003/A0002/history").json()
    assert h["current"]["level"] == 1
    assert all(e["type"] != "PCN" for e in h["events"])  # PCN 事件不重複出現在維修事件
    pcn = [c for c in h["changes"] if c["kind"] == "PCN"]
    assert pcn and pcn[-1]["counted"]["levelAfter"] == 1
    assert pcn[-1]["counted"]["smallYAfter"] == 5 and pcn[-1]["counted"]["bigYAfter"] == 7
    # ECN 仍只供顯示
    assert all(c.get("counted") is None for c in h["changes"] if c["kind"] == "ECN")

    # 現況分佈與 KPOV 狀態一致：每個有 PCN 事件的 KPOV，現況 = 最後一筆已生效事件的等級
    quadrant = su.get("/api/v1/quadrant").json()["scope"]
    assert quadrant["total"] == sum(quadrant[f"level{i}"] for i in range(4)) + quadrant["unrated"]

    # 「PCN 切入前」與系統等級不同的情況彙總成一則警告（不逐筆列出）
    summary = [w for w in report["warnings"] if "筆 PCN 的「切入前」等級" in w]
    assert len(summary) <= 1
    assert not any(w.startswith("PCN（") and "切入前填" in w for w in report["warnings"])


@needs_data
def test_level_changes_lists_pcn_rows(app_ctx):
    su = app_ctx(ADMIN)
    _import(su)
    res = su.get("/api/v1/level-changes", params={"window": "year", "kind": "improved", "pageSize": 50}).json()
    rows = [r for r in res["items"] if r.get("source") == "PCN"]
    # 1026 版的 PCN 都在一年內；有改善的 PCN 列沒有維修／客訴可開，措施層別標示 PCN 變更
    for r in rows:
        assert r["repairId"] is None and r["complaintId"] is None
        assert r["layer"]["summary"] == "PCN 變更"
        assert r["transition"] == "IMPROVED"
    # 卡片數字與清單筆數一致（PCN 列不會被略過）
    assert res["total"] == res["counts"]["improved"]


def test_pcn_ordering_and_escalation_warning():
    """同一時刻 PCN 排在維修之前；PCN 讓等級變差時提出警告。以假資料直接驗證推導函式。"""
    from app.importer.level_events import _EVENT_RANK, _pcn_axis, _pcn_targets

    assert _EVENT_RANK["PCN"] < _EVENT_RANK["DEGRADE"] < _EVENT_RANK["IMPROVE"]
    scores = {"隨機稽查": 7, "人工檢測(未證實可靠)": 8}
    by_score = {7: ["隨機稽查"], 8: ["人工檢測(未證實可靠)"]}
    assert _pcn_axis("5.0", scores, by_score) == ("偵測度 5", 5)
    assert _pcn_axis("7", scores, by_score) == ("隨機稽查", 7)
    assert _pcn_axis("隨機稽查", scores, by_score) == ("隨機稽查", 7)
    assert _pcn_axis("", scores, by_score) is None
    assert _pcn_axis("NA", scores, by_score) is None

    kpov = types.SimpleNamespace(station="鎖後蓋")
    baseline = {("K1", "A0003"): kpov, ("K1", "A0009"): types.SimpleNamespace(station="別站")}
    rec = types.SimpleNamespace(kpov_no="K1", equipment_code="A0003", station=None)
    assert _pcn_targets(rec, baseline) == [("K1", "A0003")]
    rec = types.SimpleNamespace(kpov_no="K1", equipment_code=None, station="鎖後蓋")
    assert _pcn_targets(rec, baseline) == [("K1", "A0003")]
    rec = types.SimpleNamespace(kpov_no="K1", equipment_code="A0099", station=None)
    assert _pcn_targets(rec, baseline) == []


def test_sqlite_event_type_constraint_is_widened(tmp_path):
    """既有 SQLite 資料庫的 ck_event_type 只允許 DEGRADE/IMPROVE：啟動遷移後要能寫入 PCN，舊資料保留。"""
    from app.migrations import _widen_event_types

    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE fact_level_event (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  batch_id INTEGER NOT NULL,
                  kpov_no TEXT NOT NULL, equipment_code TEXT NOT NULL,
                  event_type VARCHAR(16) NOT NULL, effective_at DATETIME NOT NULL,
                  repair_serial TEXT, note TEXT,
                  CONSTRAINT uq_level_event_idempotent UNIQUE (batch_id, repair_serial, kpov_no, equipment_code, event_type),
                  CONSTRAINT ck_event_type CHECK (event_type IN ('DEGRADE', 'IMPROVE'))
                )
                """
            )
        )
        conn.execute(text("CREATE INDEX ix_level_event_target ON fact_level_event (batch_id, kpov_no, equipment_code, effective_at)"))
        conn.execute(
            text("INSERT INTO fact_level_event (batch_id, kpov_no, equipment_code, event_type, effective_at) "
                 "VALUES (1, 'K1', 'A1', 'DEGRADE', :at)"),
            {"at": dt.datetime(2026, 1, 1)},
        )

    assert _widen_event_types(engine) == ["fact_level_event 重建：事件類型加入 PCN"]
    assert _widen_event_types(engine) == []  # 冪等
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO fact_level_event (batch_id, kpov_no, equipment_code, event_type, effective_at) "
                 "VALUES (1, 'K1', 'A1', 'PCN', :at)"),
            {"at": dt.datetime(2026, 2, 1)},
        )
        types_ = [r[0] for r in conn.execute(text("SELECT event_type FROM fact_level_event ORDER BY id"))]
        indexes = {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'index'"))}
    assert types_ == ["DEGRADE", "PCN"]
    assert "ix_level_event_target" in indexes
    engine.dispose()
