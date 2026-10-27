"""總覽廣播（spec §16）：Level 3 個數變化、當班點檢次數、等級提升的站別。"""
from __future__ import annotations

import pytest

from tests.test_rbac import ADMIN, V1019, _import, app_ctx, needs_data  # noqa: F401  (app_ctx 為 fixture)


@needs_data
@pytest.mark.parametrize("window", ["day", "month", "year"])
def test_broadcast_matches_overview_widgets(app_ctx, window):
    su = app_ctx(ADMIN)
    assert _import(su, V1019, "WJ1-DCS-PM1-數據庫-1019.xlsx").status_code == 200

    b = su.get("/api/v1/broadcast", params={"window": window}).json()

    # a. Level 3：與象限圖（不篩選）的期初 → 現在相同
    q = su.get("/api/v1/quadrant", params={"window": window}).json()
    assert b["level3"] == {
        "start": q["start"]["level3"],
        "now": q["scope"]["level3"],
        "delta": q["scope"]["level3"] - q["start"]["level3"],
    }

    # b. 當班點檢：與點檢監控的時段加總相同，班別用白班／夜班稱呼
    m = su.get("/api/v1/check-monitor").json()
    insp = b["inspection"]
    assert insp["items"] == len(m["items"])
    assert insp["expected"] == sum(len(r["slots"]) for r in m["items"])
    assert insp["completed"] == sum(r["completed"] for r in m["items"]) == 0
    assert insp["shift"]["name"] in ("白班", "夜班")
    assert insp["shift"]["label"].startswith(insp["shift"]["name"])

    # c. 等級提升：與等級異動總覽的惡化筆數相同，且都是升級
    changes = su.get("/api/v1/level-changes", params={"window": window}).json()
    assert len(b["escalations"]) == changes["counts"]["escalated"]
    assert all(e["levelAfter"] > (e["levelBefore"] or 0) for e in b["escalations"])
    assert b["escalatedStations"] == sorted({e["station"] for e in b["escalations"]})


def test_broadcast_requires_login(app_ctx):
    assert app_ctx().get("/api/v1/broadcast").status_code == 401


@needs_data
def test_broadcast_alerts_only_list_items_needing_attention(app_ctx):
    """跑馬燈（v2.7）：當班漏點檢／點檢異常、期間內升到 Level 3、新增的 Level 3。"""
    import datetime as dt

    from app.db import SessionLocal
    from app.models import CheckPhotoInspection

    su = app_ctx(ADMIN)
    assert _import(su, V1019, "WJ1-DCS-PM1-數據庫-1019.xlsx").status_code == 200
    item = su.get("/api/v1/check-monitor").json()["items"][0]
    with SessionLocal() as s:  # 當班第一個時段點檢異常
        s.add(CheckPhotoInspection(equipment_code=item["equipmentCode"], kpov_no=item["kpovNo"],
                                   check_content=item["checkContent"], status="warn", photo_url="/x.png",
                                   inspected_at=dt.datetime.fromisoformat(item["slots"][0]["start"]) + dt.timedelta(minutes=1),
                                   dataset="WJ1-DCS-PM1"))
        s.commit()

    b = su.get("/api/v1/broadcast", params={"window": "year"}).json()
    m = su.get("/api/v1/check-monitor").json()["items"]
    by_kind: dict[str, list] = {}
    for a in b["alerts"]:
        by_kind.setdefault(a["kind"], []).append(a)
    assert set(by_kind) <= {"missed", "warn", "escalatedL3", "level3New"}

    warn = by_kind["warn"]
    assert [(a["equipmentCode"], a["text"], a["count"]) for a in warn] == [(item["equipmentCode"], item["checkContent"], 1)]
    missed = sum(1 for r in m for slot in r["slots"] if slot["state"] == "missed")
    assert sum(a["count"] for a in by_kind.get("missed", [])) == missed

    to3 = {(e["kpovNo"], e["equipmentCode"]) for e in b["escalations"] if e["levelAfter"] == 3}
    assert {(a["kpovNo"], a["equipmentCode"]) for a in by_kind.get("escalatedL3", [])} == to3
    assert all(a["levelAfter"] == 3 for a in by_kind.get("escalatedL3", []))
    new3 = {(a["kpovNo"], a["equipmentCode"]) for a in by_kind.get("level3New", [])}
    assert not new3 & to3
    # 新增的 Level 3 不會多於 Level 3 個數的增加量＋升到 Level 3 的項目
    assert len(new3) + len(to3) >= max(b["level3"]["delta"], 0)
