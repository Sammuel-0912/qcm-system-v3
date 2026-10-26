"""完成期限與清單篩選（spec §17）：逾期以 8D 預計完成 vs 實際完成判定。"""
from __future__ import annotations

import datetime as dt

import pytest

from app.services.due import due_stats, due_status, in_day_range, overdue_bucket
from tests.test_rbac import ADMIN, V1026, _import, app_ctx, needs_data  # noqa: F401  (app_ctx 為 fixture)

TODAY = dt.date(2026, 10, 26)


def _at(day: str) -> dt.datetime:
    # 日期欄位匯入後為 UTC 午夜
    return dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc)


def test_due_status_rules():
    assert due_status(None, None, TODAY) is None
    # 未完成、未到期（今天到期也算未到期）
    assert due_status(_at("2026-10-26"), None, TODAY)["status"] == "planned"
    # 未完成、已過預計：逾期到今天
    d = due_status(_at("2026-10-19"), None, TODAY)
    assert (d["status"], d["overdueDays"], d["bucket"]) == ("overdue", 7, "d7_14")
    # 已完成：實際晚於預計才算逾期，天數＝實際 − 預計
    d = due_status(_at("2025-12-30"), _at("2026-04-08"), TODAY)
    assert (d["status"], d["overdueDays"], d["bucket"]) == ("overdue", 99, "gt14")
    assert due_status(_at("2026-08-30"), _at("2026-08-31"), TODAY)["bucket"] == "lt7"
    assert due_status(_at("2026-08-30"), _at("2026-08-30"), TODAY)["status"] == "ontime"
    assert [overdue_bucket(n) for n in (1, 6, 7, 14, 15)] == ["lt7", "lt7", "d7_14", "d7_14", "gt14"]


def test_due_stats_excludes_ontime():
    dues = [due_status(_at(p), _at(d) if d else None, TODAY) for p, d in [
        ("2026-11-01", None), ("2026-10-20", None), ("2026-10-01", None), ("2026-08-30", "2026-08-30"), ("2026-08-30", "2026-09-30"),
    ]] + [None]
    assert due_stats(dues) == {"planned": 1, "lt7": 1, "d7_14": 0, "gt14": 2, "overdue": 3}


def test_day_range_uses_site_date():
    # 測試時間 2026-03-19 20:00 UTC＝廠區（UTC+8）3/20
    at = dt.datetime(2026, 3, 19, 20, 0, tzinfo=dt.timezone.utc)
    assert in_day_range(at, dt.date(2026, 3, 20), dt.date(2026, 3, 20))
    assert not in_day_range(at, None, dt.date(2026, 3, 19))
    assert not in_day_range(None, dt.date(2026, 1, 1), None)
    assert in_day_range(None, None, None)


@needs_data
def test_repairs_filters_and_due_pie(app_ctx):
    su = app_ctx(ADMIN)
    assert _import(su, V1026, "WJ1-DCS-PM1-數據庫-1026.xlsx").status_code == 200
    base = su.get("/api/v1/repairs", params={"pageSize": 50}).json()
    assert base["total"] == 30
    rows = base["items"]
    assert not any(k.startswith("_") for k in rows[0])

    # 圓餅：未到期＋三組逾期，與逐筆 due 一致（1026 的 8D 都有實際完成，逾期 9 筆）
    stats = base["dueStats"]
    assert stats["overdue"] == sum(1 for r in rows if r["due"] and r["due"]["status"] == "overdue") == 9
    assert stats["planned"] == sum(1 for r in rows if r["due"] and r["due"]["status"] == "planned")
    alg = next(r for r in rows if r["serialNo"] == "ALG25B01310WB")
    assert alg["due"] == {"status": "overdue", "overdueDays": 99, "bucket": "gt14",
                          "plannedAt": "2025-12-30", "doneAt": "2026-04-08"}

    # due 篩選只影響清單，圓餅維持同一組（其他條件）的統計
    for key in ("lt7", "d7_14", "gt14", "overdue", "planned"):
        res = su.get("/api/v1/repairs", params={"pageSize": 50, "due": key}).json()
        assert res["total"] == stats[key] and res["dueStats"] == stats
    assert su.get("/api/v1/repairs", params={"due": "bad"}).status_code == 422

    # 機種、站別、KPOV 多選（重複參數）
    model = "3915102662"
    by_model = su.get("/api/v1/repairs", params={"pageSize": 50, "group": model}).json()
    assert by_model["total"] == sum(1 for r in rows if r["productModel"] == model) > 0
    two = su.get("/api/v1/repairs", params=[("pageSize", "50"), ("station", "鎖銅排"), ("station", "鎖電感")]).json()
    assert two["total"] == sum(1 for r in rows if r["station"] in ("鎖銅排", "鎖電感")) == 3
    assert sum(two["dueStats"][k] for k in ("planned", "overdue")) <= two["total"]
    kpov = rows[0]["kpovNo"]
    assert su.get("/api/v1/repairs", params={"pageSize": 50, "kpov": kpov}).json()["total"] == sum(
        1 for r in rows if r["kpovNo"] == kpov
    )
    assert any(o["value"] == kpov for o in base["options"]["kpovs"])

    # 測試時間、改善時間（廠區日期、起訖皆含）
    oct_ = su.get("/api/v1/repairs", params={"pageSize": 50, "occurredFrom": "2026-10-01", "occurredTo": "2026-10-31"}).json()
    assert {r["serialNo"] for r in oct_["items"]} == {"IOW26A00347W0", "IOW26A01997W0", "IOW26A02741W0"}
    nov = su.get("/api/v1/repairs", params={"pageSize": 50, "improvedFrom": "2026-11-14", "improvedTo": "2026-11-14"}).json()
    assert nov["total"] == sum(1 for r in rows if (r["improvedAt"] or "").startswith("2026-11-1"))
