"""匯入歷史點檢數量（spec §19）：只累加點檢看板卡片的正常／異常次數。"""
from __future__ import annotations

import datetime as dt
import io
import pathlib

import pytest
from openpyxl import Workbook

from app.services.count_import import CountImportError, parse_count_workbook
from tests.test_rbac import ADMIN, ROOT, V1026, XLSX, _import, app_ctx, needs_data  # noqa: F401  (app_ctx 為 fixture)

V2_EXPORT = ROOT / "點檢紀錄1017全.xlsx"  # 舊版（v2）匯出：欄位順序不同、點檢時間為 Excel 日期
V3_EXPORT = ROOT / "點檢紀錄_20261026_224746.xlsx"  # 本系統「匯出紀錄（含照片）」
needs_exports = pytest.mark.skipif(not (V2_EXPORT.exists() and V3_EXPORT.exists()), reason="需要兩份點檢紀錄 Excel")


@pytest.fixture(autouse=True)
def _count_from_any_day(monkeypatch):
    """兩份點檢紀錄是 10/16–10/26（試運行期間）：關掉 v2.15 的起算日與排除週日，只測匯入與累加。"""
    monkeypatch.setattr("app.services.check_trend.CHECK_MISSED_FROM", dt.date(2026, 1, 1))
    monkeypatch.setattr("app.services.check_trend.CHECK_OFF_WEEKDAYS", frozenset())


def _xlsx(tmp_path: pathlib.Path, rows: list[list]) -> str:
    wb = Workbook()
    for r in rows:
        wb.active.append(r)
    path = tmp_path / "x.xlsx"
    wb.save(path)
    return str(path)


def test_parse_by_header_name_and_site_time(tmp_path):
    path = _xlsx(tmp_path, [
        ["僅匯出最新 1000 筆，請縮小時間範圍後再匯出其餘紀錄"],  # 表頭在第 2 列
        ["點檢結果", "設備代碼", "站別", "點檢內容", "點檢時間（UTC+8）"],
        ["正常", "A0007", "固定絕緣片", "內容1", "2026-10-21 20:35:15"],
        ["異常", "A0007", "固定絕緣片", "內容1", dt.datetime(2026, 10, 22, 8, 0, 0)],
        ["正常", "A0007", "固定絕緣片", "內容1", "2026-10-21 20:35:15"],  # 同檔重複只算一次
        ["其他", "A0007", None, None, "2026-10-21 21:00:00"],
        ["正常", None, None, None, "2026-10-21 21:00:00"],
        ["正常", "A0006", None, None, "不是時間"],
        [None, None, None, None, None],
    ])
    out = parse_count_workbook(path)
    assert [(r.status, r.inspected_at) for r in out.rows] == [
        ("ok", dt.datetime(2026, 10, 21, 12, 35, 15, tzinfo=dt.timezone.utc)),  # UTC+8 → UTC
        ("warn", dt.datetime(2026, 10, 22, 0, 0, 0, tzinfo=dt.timezone.utc)),
    ]
    assert out.invalid == 3 and len(out.reasons) == 3 and "不是正常或異常" in out.reasons[0]


def test_parse_requires_headers(tmp_path):
    with pytest.raises(CountImportError, match="找不到表頭"):
        parse_count_workbook(_xlsx(tmp_path, [["日期", "站別"], ["2026-10-21", "A"]]))


@needs_exports
def test_parse_real_exports():
    v2, v3 = parse_count_workbook(str(V2_EXPORT)), parse_count_workbook(str(V3_EXPORT))
    assert (len(v2.rows), v2.invalid) == (99, 0) and (len(v3.rows), v3.invalid) == (91, 0)
    # v2 的點檢時間 11:34:40 為廠區時間
    assert v2.rows[0].inspected_at == dt.datetime(2026, 10, 16, 3, 34, 40, tzinfo=dt.timezone.utc)


def _upload(client, path: pathlib.Path, dataset: str = "WJ1-DCS-PM1"):
    with path.open("rb") as fh:
        return client.post("/api/v1/check-inspections/count-import", files={"file": (path.name, fh, XLSX)},
                           headers={"X-QCM-Dataset": dataset})


@needs_data
@needs_exports
def test_count_import_adds_to_cards_only(app_ctx):
    from app.db import SessionLocal
    from app.models import CheckPhotoInspection

    su = app_ctx(ADMIN)
    assert _import(su, V1026, "WJ1-DCS-PM1-數據庫-1026.xlsx").status_code == 200
    # 系統內已有與 v3 檔案相同的拍照點檢：
    # - 在目前點檢項目底下（卡片有算到）的要略過
    # - 點檢內容已改版、卡片沒算到的（這裡用不存在的 KPOV 模擬）照樣匯入，卡片才不會少算（v2.9）
    items = {(i["equipmentCode"], (i["checkContent"] or "").strip()): i["kpovNo"]
             for i in su.get("/api/v1/check-monitor").json()["items"]}
    v3_rows = parse_count_workbook(str(V3_EXPORT)).rows
    first = next(r for r in v3_rows if (r.equipment_code, r.check_content) in items)
    hidden = next(r for r in v3_rows if r is not first)
    with SessionLocal() as s:
        for row, kpov in ((first, items[(first.equipment_code, first.check_content)]), (hidden, "K99999")):
            s.add(CheckPhotoInspection(equipment_code=row.equipment_code, kpov_no=kpov, check_content=row.check_content,
                                       status=row.status, photo_url="/api/ar/uploads/checks/x.png",
                                       inspected_at=row.inspected_at, dataset="WJ1-DCS-PM1"))
        s.commit()
    before = {c["equipmentCode"]: c for c in su.get("/api/v1/check-inspections/stats").json()}
    listed_before = su.get("/api/v1/check-inspections").json()["total"]

    r2 = _upload(su, V2_EXPORT).json()
    assert (r2["added"], r2["duplicates"], r2["invalid"]) == (99, 0, 0)
    r3 = _upload(su, V3_EXPORT).json()
    assert (r3["added"], r3["duplicates"]) == (90, 1)
    again = _upload(su, V3_EXPORT).json()
    assert (again["added"], again["duplicates"]) == (0, 91)
    assert again["summary"]["total"] == 189 and len(again["summary"]["files"]) == 2

    after = {c["equipmentCode"]: c for c in su.get("/api/v1/check-inspections/stats").json()}
    assert sum(c["importedCount"] for c in after.values()) == 189
    for code, card in after.items():
        prev = before.get(code, {"total": 0, "okCount": 0, "warnCount": 0})
        assert card["total"] == prev["total"] + card["importedCount"]
        assert card["okCount"] + card["warnCount"] == card["total"]
    # 點檢紀錄（raw data）不變
    assert su.get("/api/v1/check-inspections").json()["total"] == listed_before
    # 趨勢圖的異常次數／分布也算入匯入的數量（期間內的部分），漏點檢不受影響
    trend = su.get("/api/v1/check-inspections/trend", params={"days": 90}).json()
    since = dt.datetime.fromisoformat(trend["since"])
    rows = {(r.equipment_code, r.check_content, r.inspected_at): r for f in (V2_EXPORT, V3_EXPORT)
            for r in parse_count_workbook(str(f)).rows}
    rows.pop((first.equipment_code, first.check_content, first.inspected_at))  # 與拍照點檢重複、沒匯入
    in_window = [r for r in rows.values() if r.inspected_at >= since]
    assert trend["totals"]["imported"] == len(in_window)
    assert sum(r["warn"] for r in trend["series"]) <= trend["totals"]["warn"]

    # 只有最高權限管理者能匯入／查看／清除
    su.post("/api/v1/users", json={"username": "wj1admin", "displayName": "WJ1", "password": "wj1-admin-pw",
                                   "role": "plant_admin", "plant": "WJ1"})
    pa = app_ctx({"username": "wj1admin", "password": "wj1-admin-pw"})
    assert _upload(pa, V3_EXPORT).status_code == 403
    assert pa.get("/api/v1/check-inspections/count-import").status_code == 403
    assert pa.delete("/api/v1/check-inspections/count-import").status_code == 403
    # 卡片數量大家都看得到
    assert sum(c["importedCount"] for c in pa.get("/api/v1/check-inspections/stats").json()) == 189

    assert su.delete("/api/v1/check-inspections/count-import").json() == {"deleted": 189}
    cleared = {c["equipmentCode"]: c["total"] for c in su.get("/api/v1/check-inspections/stats").json()}
    assert cleared == {k: v["total"] for k, v in before.items()}


@needs_data
def test_count_import_rejects_bad_files(app_ctx):
    su = app_ctx(ADMIN)
    assert _import(su, V1026, "WJ1-DCS-PM1-數據庫-1026.xlsx").status_code == 200
    bad = su.post("/api/v1/check-inspections/count-import", files={"file": ("a.csv", io.BytesIO(b"x"), "text/csv")})
    assert bad.status_code == 422
    junk = su.post("/api/v1/check-inspections/count-import", files={"file": ("a.xlsx", io.BytesIO(b"not excel"), XLSX)})
    assert junk.status_code == 422 and "無法讀取" in junk.json()["detail"]


@needs_data
@needs_exports
def test_count_import_replace_overwrites_previous_imports(app_ctx):
    """覆蓋（v2.10）：先清掉這條線先前匯入的數量，再以這份檔案為準；只動這條線。"""
    su = app_ctx(ADMIN)
    assert _import(su, V1026, "WJ1-DCS-PM1-數據庫-1026.xlsx").status_code == 200
    _upload(su, V2_EXPORT)
    _upload(su, V3_EXPORT)
    assert su.get("/api/v1/check-inspections/count-import").json()["total"] == 190

    with V3_EXPORT.open("rb") as fh:
        r = su.post("/api/v1/check-inspections/count-import", files={"file": (V3_EXPORT.name, fh, XLSX)},
                    data={"replace": "true"}, headers={"X-QCM-Dataset": "WJ1-DCS-PM1"}).json()
    assert (r["replaced"], r["added"], r["duplicates"]) == (190, 91, 0)
    assert r["summary"]["total"] == 91 and [f["source"] for f in r["summary"]["files"]] == [V3_EXPORT.name]
    assert sum(c["importedCount"] for c in su.get("/api/v1/check-inspections/stats").json()) == 91

    # 檔案無法讀取時不清除
    bad = su.post("/api/v1/check-inspections/count-import", files={"file": ("a.xlsx", io.BytesIO(b"x"), XLSX)},
                  data={"replace": "true"})
    assert bad.status_code == 422
    assert su.get("/api/v1/check-inspections/count-import").json()["total"] == 91
    # 不勾覆蓋時照舊累加
    assert _upload(su, V2_EXPORT).json()["replaced"] == 0


@needs_data
def test_cards_count_from_start_date_and_can_skip_sundays(app_ctx, monkeypatch):
    """v2.15：站別卡片只算起算日之後的點檢；預設不算星期日，excludeOffDays=false 時算進去。"""
    from app.db import SessionLocal
    from app.models import CheckCountImport

    monkeypatch.setattr("app.services.check_trend.CHECK_MISSED_FROM", dt.date(2026, 10, 27))
    monkeypatch.setattr("app.services.check_trend.CHECK_OFF_WEEKDAYS", frozenset({6}))
    su = app_ctx(ADMIN)
    assert _import(su, V1026, "WJ1-DCS-PM1-數據庫-1026.xlsx").status_code == 200
    site = dt.timezone(dt.timedelta(hours=8))
    with SessionLocal() as s:
        for day, status in ((26, "warn"), (27, "ok"), (28, "warn"), (1, "ok")):  # 10/26 試運行、11/1 是星期日
            month = 11 if day == 1 else 10
            s.add(CheckCountImport(dataset="WJ1-DCS-PM1", equipment_code="ZZ01", station="測試站", check_content="c",
                                   status=status, inspected_at=dt.datetime(2026, month, day, 10, tzinfo=site),
                                   source="t.xlsx", imported_by="t"))
        s.commit()

    def card(**params):
        rows = su.get("/api/v1/check-inspections/stats", params=params).json()
        return next(((c["okCount"], c["warnCount"]) for c in rows if c["equipmentCode"] == "ZZ01"), None)

    assert card() == (1, 1)  # 10/27 正常、10/28 異常
    assert card(excludeOffDays="false") == (2, 1)  # 加上星期日 11/1
