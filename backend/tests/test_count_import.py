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
    # 系統內已有一筆與 v3 檔案第一列相同的拍照點檢：匯入時要略過
    first = parse_count_workbook(str(V3_EXPORT)).rows[0]
    with SessionLocal() as s:
        s.add(CheckPhotoInspection(equipment_code=first.equipment_code, kpov_no="K00026", check_content=first.check_content,
                                   status=first.status, photo_url="/api/ar/uploads/checks/x.png",
                                   inspected_at=first.inspected_at, dataset="WJ1-DCS-PM1"))
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
