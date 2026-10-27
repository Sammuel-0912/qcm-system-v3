"""點檢看板趨勢與分布（spec §18）。"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from app.services.check_trend import check_trend
from tests.test_rbac import ADMIN, V1026, _import, app_ctx, needs_data  # noqa: F401  (app_ctx 為 fixture)

SITE = dt.timezone(dt.timedelta(hours=8))


def _site(day: int, hour: int) -> dt.datetime:
    return dt.datetime(2026, 10, day, hour, tzinfo=SITE)


def _item(code: str, interval: float):
    return SimpleNamespace(equipment_code=code, kpov_no="K1", check_content=f"點檢{code}", interval_hours=interval,
                           station=f"站{code}", kpiv_control_level="B")


def _rec(code: str, at: dt.datetime, status: str = "ok"):
    return SimpleNamespace(equipment_code=code, kpov_no="K1", check_content=f"點檢{code}", inspected_at=at, status=status)


def test_trend_counts_warn_and_missed_slots_from_first_inspection():
    # A：開線/班（一班一次）；B：每 5 小時一次（一班兩格）
    items = [_item("A", 10), _item("B", 5)]
    records = [
        _rec("A", _site(25, 9)),
        _rec("A", _site(25, 21), "warn"),  # 10/25 夜班
        _rec("B", _site(26, 9)),
    ]
    out = check_trend(items, records, days=3, now=_site(26, 12))
    rows = {r["date"]: r for r in out["series"]}
    # 10/24 在第一筆點檢之前：不算漏點檢
    assert rows["2026-10-24"] == {"date": "2026-10-24", "warn": 0, "inspected": 0, "missed": 0, "expected": 0}
    # 10/25 日班：B 兩格漏；夜班：B 兩格漏；A 兩班都有點（夜班為異常）
    assert rows["2026-10-25"] == {"date": "2026-10-25", "warn": 1, "inspected": 2, "missed": 4, "expected": 6}
    # 10/26 日班進行中：已過的時段都有點，進行中與未到的不算漏；夜班尚未開始
    assert rows["2026-10-26"] == {"date": "2026-10-26", "warn": 0, "inspected": 1, "missed": 0, "expected": 3}
    assert out["totals"] == {"total": 3, "ok": 2, "warn": 1, "missed": 4, "imported": 0}
    a = out["items"][0]
    assert (a["equipmentCode"], a["total"], a["warn"], a["station"]) == ("A", 2, 1, "站A")
    assert out["trackingFrom"] == _site(25, 8).astimezone(dt.timezone.utc).isoformat()


def test_trend_without_records():
    out = check_trend([_item("A", 10)], [], days=7, now=_site(26, 12))
    assert len(out["series"]) == 7 and out["totals"] == {"total": 0, "ok": 0, "warn": 0, "missed": 0, "imported": 0}
    assert out["trackingFrom"] is None and out["items"] == []


@needs_data
def test_trend_api(app_ctx):
    su = app_ctx(ADMIN)
    assert _import(su, V1026, "WJ1-DCS-PM1-數據庫-1026.xlsx").status_code == 200
    out = su.get("/api/v1/check-inspections/trend", params={"days": 7}).json()
    assert len(out["series"]) == 7 and out["totals"]["total"] == 0
    assert su.get("/api/v1/check-inspections/trend", params={"days": 0}).status_code == 422


def test_trend_includes_imported_counts_but_not_missed():
    # 匯入列（spec §19）沒有 KPOV 編號：依設備代碼＋點檢內容對回點檢項目；對不到的另列一項
    items = [_item("A", 10)]
    records = [_rec("A", _site(25, 9))]
    imported = [
        SimpleNamespace(equipment_code="A", check_content="點檢A", station="舊站名", inspected_at=_site(25, 10), status="warn"),
        SimpleNamespace(equipment_code="Z", check_content="舊內容", station="舊站Z", inspected_at=_site(24, 10), status="warn"),
        SimpleNamespace(equipment_code="A", check_content="點檢A", station=None, inspected_at=_site(1, 10), status="warn"),  # 期間外
    ]
    base = check_trend(items, records, days=3, now=_site(26, 12))
    out = check_trend(items, records, days=3, now=_site(26, 12), imported=imported)
    rows = {r["date"]: r for r in out["series"]}
    assert (rows["2026-10-25"]["warn"], rows["2026-10-25"]["inspected"]) == (1, 2)
    assert (rows["2026-10-24"]["warn"], rows["2026-10-24"]["missed"]) == (1, 0)
    # 漏點檢只看拍照點檢
    assert [r["missed"] for r in out["series"]] == [r["missed"] for r in base["series"]]
    assert out["totals"] == {**base["totals"], "total": 3, "warn": 2, "ok": 1, "imported": 2}
    by_code = {i["equipmentCode"]: i for i in out["items"]}
    assert (by_code["A"]["total"], by_code["A"]["warn"], by_code["A"]["kpovNo"], by_code["A"]["station"]) == (2, 1, "K1", "站A")
    assert (by_code["Z"]["warn"], by_code["Z"]["station"], by_code["Z"]["kpovNo"]) == (1, "舊站Z", None)
