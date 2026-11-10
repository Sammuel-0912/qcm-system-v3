"""製程完成率／客訴結案率（v2.15）：與圓餅同一組篩選結果。"""
from __future__ import annotations

from tests.test_rbac import ADMIN, V1026, _import, app_ctx, needs_data  # noqa: F401  (app_ctx 為 fixture)


@needs_data
def test_repairs_completion_and_complaints_closure_rate(app_ctx):
    from app.db import SessionLocal
    from app.models import FactComplaint, FactRepair

    su = app_ctx(ADMIN)
    assert _import(su, V1026, "WJ1-DCS-PM1-數據庫-1026.xlsx").status_code == 200
    with SessionLocal() as s:
        done = sum(1 for r in s.query(FactRepair).all() if r.d8_done_at is not None)
        ok = sum(1 for c in s.query(FactComplaint).all() if (c.verdict or "").strip().upper() == "OK")

    repairs = su.get("/api/v1/repairs").json()
    assert repairs["rate"] == {"done": done, "total": repairs["total"]}
    complaints = su.get("/api/v1/complaints").json()
    assert complaints["rate"] == {"done": ok, "total": complaints["total"]}

    # 完成期限篩選只影響清單，不影響完成率（與圓餅相同）
    overdue = su.get("/api/v1/repairs", params={"due": "overdue"}).json()
    assert overdue["rate"] == repairs["rate"]
    # 其他篩選會一起縮小分母
    none = su.get("/api/v1/repairs", params={"station": "不存在的站"}).json()
    assert none["rate"] == {"done": 0, "total": 0}


@needs_data
def test_import_history_lists_each_import_with_report(app_ctx):
    """匯入歷程（v2.16）：每次匯入一筆，新到舊；帶出生效狀態、筆數與匯入警告。"""
    su = app_ctx(ADMIN)
    for _ in range(2):
        assert _import(su, V1026, "WJ1-DCS-PM1-數據庫-1026.xlsx").status_code == 200
    rows = [r for r in su.get("/api/v1/import/history").json() if r["dataset"] == "WJ1-DCS-PM1"]
    assert len(rows) >= 2 and rows[0]["id"] > rows[1]["id"]
    latest, previous = rows[0], rows[1]
    assert latest["isActive"] and not previous["isActive"] and latest["status"] == "success"
    assert latest["rowCounts"]["kpov"] == 331 and latest["importedBy"]
    assert isinstance(latest["warnings"], list) and latest["levelEventSummary"]["total"] == latest["rowCounts"]["levelEvents"]
