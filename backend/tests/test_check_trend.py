"""點檢看板趨勢與分布（spec §18）。"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from app.services.check_trend import check_trend
from tests.test_rbac import ADMIN, V1026, _import, app_ctx, needs_data  # noqa: F401  (app_ctx 為 fixture)

SITE = dt.timezone(dt.timedelta(hours=8))


@pytest.fixture(autouse=True)
def _no_trial_or_off_days(monkeypatch):
    """既有案例用 10/24–26（含週日 10/25）：關掉 v2.12 的起算日與不生產星期，只測時段邏輯。"""
    monkeypatch.setattr("app.services.check_trend.CHECK_MISSED_FROM", dt.date(2026, 1, 1))
    monkeypatch.setattr("app.services.check_trend.CHECK_OFF_WEEKDAYS", frozenset())


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


def test_trend_includes_imported_counts_and_fills_missed_slots():
    # 匯入列（spec §19）沒有 KPOV 編號：依設備代碼＋點檢內容對回點檢項目；對不到的另列一項
    items = [_item("A", 10), _item("B", 5)]
    records = [_rec("A", _site(25, 9))]
    imported = [
        SimpleNamespace(equipment_code="A", check_content="點檢A", station="舊站名", inspected_at=_site(25, 10), status="warn"),
        SimpleNamespace(equipment_code="B", check_content="點檢B", station=None, inspected_at=_site(25, 14), status="ok"),
        SimpleNamespace(equipment_code="Z", check_content="舊內容", station="舊站Z", inspected_at=_site(24, 10), status="warn"),
        SimpleNamespace(equipment_code="A", check_content="點檢A", station=None, inspected_at=_site(1, 10), status="warn"),  # 期間外
    ]
    base = check_trend(items, records, days=3, now=_site(26, 12))
    out = check_trend(items, records, days=3, now=_site(26, 12), imported=imported)
    rows = {r["date"]: r for r in out["series"]}
    base_rows = {r["date"]: r for r in base["series"]}
    assert (rows["2026-10-25"]["warn"], rows["2026-10-25"]["inspected"]) == (1, 3)
    # 10/24 在第一筆拍照點檢之前：匯入的點檢算異常，但不會讓漏點檢提前起算
    assert (rows["2026-10-24"]["warn"], rows["2026-10-24"]["missed"], rows["2026-10-24"]["expected"]) == (1, 0, 0)
    # v2.11：B 在 10/25 日班第二格（13–18 時）有匯入的點檢，那格不算漏點檢
    assert rows["2026-10-25"]["missed"] == base_rows["2026-10-25"]["missed"] - 1
    assert rows["2026-10-26"] == {**base_rows["2026-10-26"]}
    assert out["totals"] == {"total": 4, "ok": 2, "warn": 2, "missed": base["totals"]["missed"] - 1, "imported": 3}
    by_code = {i["equipmentCode"]: i for i in out["items"]}
    assert (by_code["A"]["total"], by_code["A"]["warn"], by_code["A"]["kpovNo"], by_code["A"]["station"]) == (2, 1, "K1", "站A")
    assert (by_code["Z"]["warn"], by_code["Z"]["station"], by_code["Z"]["kpovNo"]) == (1, "舊站Z", None)


def test_missed_skips_trial_period_sundays_and_shifts_without_any_record(monkeypatch):
    """v2.12：起算日前（試運行）、週日、整班沒有任何點檢的班別都不算漏點檢。"""
    monkeypatch.setattr("app.services.check_trend.CHECK_MISSED_FROM", dt.date(2026, 10, 24))
    monkeypatch.setattr("app.services.check_trend.CHECK_OFF_WEEKDAYS", frozenset({6}))
    items = [_item("A", 10), _item("B", 5)]
    records = [
        _rec("A", _site(23, 9)),   # 第一筆拍照點檢在試運行期間
        _rec("A", _site(24, 9)),   # 10/24（六）日班有點；夜班沒有任何紀錄
        _rec("A", _site(25, 9)),   # 10/25（日）不生產：有紀錄也不算漏點檢
        _rec("B", _site(26, 21)),  # 10/26（一）只有夜班有點
    ]
    imported = [SimpleNamespace(equipment_code="Z", check_content="舊內容", station=None, inspected_at=_site(27, 9), status="ok")]
    out = check_trend(items, records, days=5, now=_site(27, 12), imported=imported)
    rows = {r["date"]: (r["missed"], r["expected"]) for r in out["series"]}
    assert rows["2026-10-23"] == (0, 0)  # 起算日前
    assert rows["2026-10-24"] == (2, 3)  # 只算日班：A 有點、B 兩格漏
    assert rows["2026-10-25"] == (0, 0)  # 週日
    assert rows["2026-10-26"] == (2, 3)  # 只算夜班：B 點了一格、另一格漏，A 漏
    # 10/27 日班只有一筆對不到項目的匯入，仍算有開線；進行中的班只算已結束的格（B 08–13 尚未結束）
    assert rows["2026-10-27"] == (0, 3)
    assert out["trackingFrom"] == _site(24, 8).astimezone(dt.timezone.utc).isoformat()
