"""AR 點檢 API 測試 — ar-integration-spec.md §5 / §6。"""
from __future__ import annotations

import io
import os
import pathlib
import tempfile

import pytest

# v3 只以數據庫-1019 為準（不再相容 1008／1011／raw_data 的測試）
DATA = pathlib.Path(__file__).resolve().parent.parent.parent / "數據庫-1019.xlsx"
RAW = DATA
# 匯入檔名須符合 WJ<1-8>-<產品廠>-<線別>-數據庫-<MMDD>.xlsx（spec §15）
DATA_NAME = "WJ1-DCS-PM1-數據庫-1019.xlsx"


# 在 import app 之前就把資料庫與資料目錄指到暫存位置：
# app.db 的 engine 是模組層級物件，匯入後才改環境變數已經來不及，
# 而 importlib.reload(app.models) 會把同名類別重複註冊進 declarative base。
_TMP = pathlib.Path(tempfile.mkdtemp(prefix="qcm-ar-test-"))
os.environ["QCM_DATABASE_URL"] = f"sqlite:///{_TMP / 'ar.db'}"
os.environ["QCM_DATA_DIR"] = str(_TMP)

from sqlalchemy.orm import close_all_sessions  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


@pytest.fixture()
def client():
    """每個測試一套乾淨的資料表。"""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from fastapi.testclient import TestClient

    with TestClient(fastapi_app) as c:
        # 所有 API 都要登入（spec §15）：以最高權限管理者登入
        assert c.post("/api/v1/auth/login", json={"username": "admin", "password": "admin-pass-1234"}).status_code == 200
        yield c
    close_all_sessions()
    # engine 是模組層級、跨測試檔共用；不清掉的話，最後匯入的批次會成為
    # 後續測試檔（例如 test_lifecycle）的「前一批次」而被合併進去
    Base.metadata.drop_all(engine)


def test_device_crud(client):
    assert client.get("/api/ar/devices").json() == []

    created = client.post(
        "/api/ar/devices",
        json={"marker_id": 3, "name": "鎖銅排點檢", "equipment_code": "OT00420118"},
    )
    assert created.status_code == 201
    assert created.json()["markerId"] == 3

    # marker_id 重複要擋下來，而不是覆寫
    assert client.post("/api/ar/devices", json={"marker_id": 3, "name": "x"}).status_code == 409

    patched = client.patch("/api/ar/devices/3", json={"name": "改名後"})
    assert patched.json()["name"] == "改名後"
    # 未提供的欄位不應被清空
    assert patched.json()["equipmentCode"] == "OT00420118"

    assert client.delete("/api/ar/devices/3").status_code == 200
    assert client.get("/api/ar/devices/3").status_code == 404


@pytest.mark.parametrize("marker_id", [-1, 64, 999])
def test_marker_id_must_be_within_3x3_barcode_range(client, marker_id):
    """AR.js 3x3 barcode 的有效值是 0~63，超出的 marker 永遠掃不到。"""
    r = client.post("/api/ar/devices", json={"marker_id": marker_id, "name": "x"})
    assert r.status_code == 422


def test_inspection_requires_existing_device(client):
    """沒有設備就不該留下孤兒點檢紀錄。"""
    r = client.post("/api/ar/inspections", json={"marker_id": 9, "status": "ok"})
    assert r.status_code == 404


def test_inspection_status_is_constrained(client):
    client.post("/api/ar/devices", json={"marker_id": 1, "name": "A"})
    assert client.post("/api/ar/inspections", json={"marker_id": 1, "status": "bad"}).status_code == 422


def test_stats_and_results(client):
    client.post("/api/ar/devices", json={"marker_id": 1, "name": "A"})
    for status in ("ok", "ok", "warn"):
        client.post("/api/ar/inspections", json={"marker_id": 1, "status": status})

    results = client.get("/api/ar/results").json()
    assert results["total"] == 3
    # 最新的在最前面
    assert results["items"][0]["status"] == "warn"

    stats = client.get("/api/ar/stats").json()
    assert stats == [
        {
            "markerId": 1,
            "deviceName": "A",
            "total": 3,
            "okCount": 2,
            "warnCount": 1,
            "okRate": round(2 / 3, 4),
        }
    ]


def test_deleting_device_cascades_inspections(client):
    client.post("/api/ar/devices", json={"marker_id": 1, "name": "A"})
    client.post("/api/ar/inspections", json={"marker_id": 1, "status": "ok"})
    client.delete("/api/ar/devices/1")
    assert client.get("/api/ar/results").json()["total"] == 0


def test_image_upload_rejects_non_image(client):
    client.post("/api/ar/devices", json={"marker_id": 1, "name": "A"})
    r = client.post(
        "/api/ar/devices/1/image",
        files={"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert r.status_code == 422


def test_image_upload_stores_relative_url(client):
    client.post("/api/ar/devices", json={"marker_id": 1, "name": "A"})
    r = client.post(
        "/api/ar/devices/1/image",
        files={"file": ("photo.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")},
    )
    assert r.status_code == 200
    url = r.json()["imageUrl"]
    # 必須是相對路徑且帶 /api/ar 前綴，前端才不需要再拼接 host（REQ-API-04）
    assert url.startswith("/api/ar/uploads/")
    assert client.get("/api/ar/devices/1").json()["imageUrl"] == url


def test_export_without_records_is_404(client):
    assert client.get("/api/ar/export").status_code == 404


def test_export_returns_xlsx(client):
    client.post("/api/ar/devices", json={"marker_id": 1, "name": "A"})
    client.post("/api/ar/inspections", json={"marker_id": 1, "status": "ok"})
    r = client.get("/api/ar/export")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    # xlsx 是 zip，開頭必為 PK
    assert r.content[:2] == b"PK"
    # 原版會把 temp_report.xlsx 留在工作目錄，改為記憶體串流後不應再有殘檔
    assert not os.path.exists("temp_report.xlsx")


# --------------------------------------------------------------------- 品控力橋接


def test_quality_bridge_unlinked(client):
    client.post("/api/ar/devices", json={"marker_id": 1, "name": "A"})
    body = client.get("/api/ar/devices/1/quality").json()
    assert body["linked"] is False
    assert "尚未綁定" in body["reason"]


def test_quality_bridge_without_import(client):
    client.post("/api/ar/devices", json={"marker_id": 1, "name": "A", "equipment_code": "OT00420118"})
    body = client.get("/api/ar/devices/1/quality").json()
    assert body["linked"] is False
    assert "尚未匯入" in body["reason"]


@pytest.mark.skipif(not RAW.exists(), reason="數據庫-1019.xlsx 不存在")
def test_quality_bridge_links_to_active_batch(client):
    with RAW.open("rb") as fh:
        imported = client.post(
            "/api/v1/import",
            files={"file": (DATA_NAME, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert imported.status_code == 200

    client.post(
        "/api/ar/devices",
        json={"marker_id": 1, "name": "鎖銅排點檢", "equipment_code": "OT00420118"},
    )
    body = client.get("/api/ar/devices/1/quality").json()
    assert body["linked"] is True
    assert body["station"] == "鎖銅排"
    assert body["kpovCount"] == 26
    assert sum(body["levelCounts"].values()) == 26

    # 代碼不在批次中時要明講，不可靜默忽略（REQ-DATA-05）
    client.post("/api/ar/devices", json={"marker_id": 2, "name": "壞代碼", "equipment_code": "NOPE"})
    bad = client.get("/api/ar/devices/2/quality").json()
    assert bad["linked"] is False
    assert "不在目前匯入批次" in bad["reason"]


@pytest.mark.skipif(not RAW.exists(), reason="數據庫-1019.xlsx 不存在")
def test_equipment_options_come_from_active_batch(client):
    with RAW.open("rb") as fh:
        client.post(
            "/api/v1/import",
            files={"file": (DATA_NAME, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    body = client.get("/api/ar/equipment-options").json()
    codes = {o["equipmentCode"] for o in body["options"]}
    assert "OT00420118" in codes
    # OP 站沒有設備代碼，不該出現在下拉中
    assert None not in codes


V2 = DATA


@pytest.mark.skipif(not V2.exists(), reason="數據庫-1019.xlsx 不存在")
def test_item_inspection_feeds_check_monitor(client):
    with V2.open("rb") as fh:
        imported = client.post(
            "/api/v1/import",
            files={"file": (DATA_NAME, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert imported.status_code == 200, imported.text

    monitor = client.get("/api/v1/check-monitor").json()
    assert monitor["summary"]["total"] == len(monitor["items"]) > 0
    assert {r["status"] for r in monitor["items"]} == {"never"}

    client.post("/api/ar/devices", json={"marker_id": 7, "name": "鎖PWB", "equipment_code": "OT00420112"})
    items = client.get("/api/ar/devices/7/check-items").json()["items"]
    assert len(items) == 3
    target = items[0]
    created = client.post(
        "/api/ar/inspections",
        json={
            "marker_id": 7,
            "status": "warn",
            "kpov_no": target["kpovNo"],
            "check_content": target["checkContent"],
        },
    )
    assert created.status_code == 201

    rows = client.get("/api/v1/check-monitor", params={"target": "equip:OT00420112"}).json()["items"]
    assert len(rows) == 3
    assert {r["id"]: r["status"] for r in rows}[target["id"]] == "warn"

    # 未綁設備代碼的 AR 設備不能逐項點檢
    client.post("/api/ar/devices", json={"marker_id": 8, "name": "未綁定"})
    bad = client.post(
        "/api/ar/inspections", json={"marker_id": 8, "status": "ok", "kpov_no": "K1", "check_content": "x"}
    )
    assert bad.status_code == 400


@pytest.mark.skipif(not V2.exists(), reason="數據庫-1019.xlsx 不存在")
def test_history_includes_pcn_and_plant_wide_ecn(client):
    with V2.open("rb") as fh:
        client.post(
            "/api/v1/import",
            files={"file": (DATA_NAME, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    body = client.get("/api/v1/kpov/K00002/OT00420102/history").json()
    kinds = [c["kind"] for c in body["changes"]]
    assert kinds.count("PCN") == 1 and kinds.count("ECN") == 1
    pcn = next(c for c in body["changes"] if c["kind"] == "PCN")
    assert (pcn["levelBefore"], pcn["levelAfter"]) == ("Level 3", "Level 1")

    # OP 站：K00048 插線/理線沒有 PCN，只看得到全廠 ECN
    op = client.get("/api/v1/kpov/K00048/A0001/history").json()
    assert [c["kind"] for c in op["changes"]] == ["ECN"]

    # OP 站的 PCN（Excel 未填設備ID）也要出現：鎖後蓋 = A0003
    pcn_op = client.get("/api/v1/kpov/K00001/A0003/history").json()
    assert sorted(c["kind"] for c in pcn_op["changes"]) == ["ECN", "PCN"]


@pytest.mark.skipif(not V2.exists(), reason="數據庫-1019.xlsx 不存在")
def test_photo_upload_records_inspection(client):
    with V2.open("rb") as fh:
        client.post(
            "/api/v1/import",
            files={"file": (DATA_NAME, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    body = client.get("/api/v1/check-items").json()
    assert "固定絕緣片" in body["stations"]
    items = client.get("/api/v1/check-items", params={"station": "鎖PWB"}).json()["items"]
    assert len(items) == 3
    item = items[0]
    form = {
        "equipmentCode": item["equipmentCode"],
        "kpovNo": item["kpovNo"],
        "checkContent": item["checkContent"],
        "status": "warn",
        "note": "治具缺角",
    }
    uploaded = client.post(
        "/api/v1/check-inspections", data=form, files={"file": ("p.jpg", b"\xff\xd8fakejpeg", "image/jpeg")}
    )
    assert uploaded.status_code == 201, uploaded.text
    photo = uploaded.json()["photoUrl"]
    assert client.get(photo).content == b"\xff\xd8fakejpeg"

    rows = client.get("/api/v1/check-monitor", params={"target": "equip:OT00420112"}).json()["items"]
    row = next(r for r in rows if r["id"] == item["id"])
    assert row["status"] == "warn" and row["lastPhotoUrl"] == photo and row["lastNote"] == "治具缺角"

    # 項目不存在 -> 404；格式不符 -> 422，且都不留檔
    bad = client.post(
        "/api/v1/check-inspections",
        data={**form, "checkContent": "不存在"},
        files={"file": ("p.jpg", b"x", "image/jpeg")},
    )
    assert bad.status_code == 404
    wrong = client.post("/api/v1/check-inspections", data=form, files={"file": ("p.exe", b"x", "x/y")})
    assert wrong.status_code == 422
    from app.config import AR_UPLOAD_DIR

    assert len(list((AR_UPLOAD_DIR / "checks").iterdir())) == 1


def _png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (640, 480), (30, 120, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_shift_of():
    """匯出班別：白班 08–18、夜班 20–06（UTC+8），空檔歸入剛結束的班，夜班日期記為開班日。"""
    import datetime as dt

    from app.services.check_monitor import shift_of

    tw = dt.timezone(dt.timedelta(hours=8))

    def at(day, hour):
        return dt.datetime(2026, 10, day, hour, tzinfo=tw).astimezone(dt.timezone.utc)

    cases = [
        (at(16, 9), "白班", 16),
        (at(16, 19), "白班", 16),  # 18–20 空檔 -> 剛結束的白班
        (at(16, 21), "夜班", 16),
        (at(17, 2), "夜班", 16),  # 跨午夜 -> 開班日 10/16
        (at(17, 7), "夜班", 16),  # 06–08 空檔 -> 剛結束的夜班
    ]
    for when, name, day in cases:
        shift = shift_of(when)
        assert (shift["name"], shift["date"]) == (name, dt.date(2026, 10, day)), when


# V3 定義在檔案後段，裝飾器在定義當下求值，這裡直接寫路徑
@pytest.mark.skipif(not DATA.exists(), reason="數據庫-1019.xlsx 不存在")
def test_photo_inspection_dashboard(client):
    """點檢儀表板：拍照點檢紀錄（帶時區的 UTC）、依站別統計、匯出用廠區時間、刪除連同照片。"""
    import datetime as dt
    import io

    import openpyxl

    from app.config import AR_UPLOAD_DIR, AR_UPLOAD_URL_PREFIX

    _import_v3(client)
    station = client.get("/api/v1/check-items").json()["stations"][0]
    item = client.get("/api/v1/check-items", params={"station": station}).json()["items"][0]
    form = {"equipmentCode": item["equipmentCode"], "kpovNo": item["kpovNo"], "checkContent": item["checkContent"]}
    ids = []
    for status in ("ok", "warn"):
        res = client.post(
            "/api/v1/check-inspections",
            data={**form, "status": status},
            # 正常那筆用真的 PNG（匯出時會嵌入縮圖）；異常那筆是讀不出來的假圖（匯出顯示「照片遺失」）
            files={"file": ("p.png", _png() if status == "ok" else b"\xff\xd8broken", "image/png")},
        )
        assert res.status_code == 201, res.text
        assert res.json()["inspectedAt"].endswith("+00:00")
        ids.append(res.json()["id"])

    body = client.get("/api/v1/check-inspections").json()
    assert body["total"] == 2
    items = body["items"]
    assert [i["id"] for i in items] == ids[::-1]  # 新到舊
    for i in items:
        assert i["inspectedAt"].endswith("+00:00")
        assert i["station"] and i["equipmentCode"] == item["equipmentCode"]
        assert client.get(i["photoUrl"]).status_code == 200

    # 篩選：設備代碼、時間（帶時區）
    assert client.get("/api/v1/check-inspections", params={"equipmentCode": "NOPE"}).json()["total"] == 0
    future = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()
    past = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
    assert client.get("/api/v1/check-inspections", params={"start": future}).json()["total"] == 0
    assert client.get("/api/v1/check-inspections", params={"start": past, "end": future}).json()["total"] == 2
    # 點檢結果篩選（v2.17）：正常／異常；列表與匯出都吃這個條件
    warn_only = client.get("/api/v1/check-inspections", params={"status": "warn"}).json()
    assert [i["id"] for i in warn_only["items"]] == [ids[1]]
    assert [i["id"] for i in client.get("/api/v1/check-inspections", params={"status": "ok"}).json()["items"]] == [ids[0]]
    assert client.get("/api/v1/check-inspections", params={"status": "bad"}).status_code == 422
    exported = client.get("/api/v1/check-inspections/export", params={"status": "ok"})
    assert exported.status_code == 200
    assert openpyxl.load_workbook(io.BytesIO(exported.content)).active.max_row >= 2

    stats = client.get("/api/v1/check-inspections/stats").json()
    assert stats == [
        {
            "equipmentCode": item["equipmentCode"],
            "station": items[0]["station"],
            "total": 2,
            "okCount": 1,
            "warnCount": 1,
            "okRate": 0.5,
            "importedCount": 0,  # 匯入的歷史點檢數量（spec §19）
        }
    ]

    # 匯出：舊到新、廠區時間（UTC+8）、班別、正常那筆嵌入縮圖、異常那筆照片讀不出來
    # 緊急措施（v2.15）：可填寫、修改、清空；記錄修改人與時間；別的資料集看不到這筆
    oldest = items[-1]
    url = f"/api/v1/check-inspections/{oldest['id']}/emergency-measure"
    saved = client.put(url, json={"emergencyMeasure": "  更換治具後重新點檢  "})
    assert saved.status_code == 200, saved.text
    assert saved.json()["emergencyMeasure"] == "更換治具後重新點檢"
    assert saved.json()["emergencyMeasureBy"] and saved.json()["emergencyMeasureAt"].endswith("+00:00")
    assert saved.json()["note"] == oldest["note"]  # 異常說明不受影響
    listed = {i["id"]: i for i in client.get("/api/v1/check-inspections").json()["items"]}
    assert listed[oldest["id"]]["emergencyMeasure"] == "更換治具後重新點檢"
    assert client.put("/api/v1/check-inspections/999999/emergency-measure", json={"emergencyMeasure": "x"}).status_code == 404
    assert client.put(url, json={"emergencyMeasure": "x" * 2001}).status_code == 422

    export = client.get("/api/v1/check-inspections/export", params={"baseUrl": "https://qcm.example.com"})
    assert export.status_code == 200
    assert "filename*=UTF-8''" in export.headers["content-disposition"]
    assert "x-export-truncated" not in export.headers
    ws = openpyxl.load_workbook(io.BytesIO(export.content)).active
    assert [c.value for c in ws[1]] == [
        "日期", "班別", "點檢時間（UTC+8）", "站別", "設備代碼", "KPOV 編號",
        "點檢內容", "點檢結果", "異常說明", "緊急措施", "照片", "原圖連結",
    ]
    oldest = items[-1]
    exported = dt.datetime.strptime(ws.cell(2, 3).value, "%Y-%m-%d %H:%M:%S")
    utc_at = dt.datetime.fromisoformat(oldest["inspectedAt"]).replace(tzinfo=None, microsecond=0)
    assert exported - utc_at == dt.timedelta(hours=8)
    assert ws.cell(2, 2).value in ("白班", "夜班")
    assert [ws.cell(r, 8).value for r in (2, 3)] == ["正常", "異常"]
    assert ws.cell(2, 10).value == "更換治具後重新點檢"
    assert len(ws._images) == 1 and ws.cell(2, 11).value is None
    assert ws.cell(3, 11).value == "照片遺失"
    assert ws.cell(2, 12).hyperlink.target == "https://qcm.example.com" + oldest["photoUrl"]
    # 篩選與列表相同；沒有符合的紀錄回 404；baseUrl 不是 http(s) 回 422
    assert client.get("/api/v1/check-inspections/export", params={"equipmentCode": "NOPE"}).status_code == 404
    assert client.get("/api/v1/check-inspections/export", params={"baseUrl": "javascript:x"}).status_code == 422

    # 列表帶出目前點檢項目的 KPIV 管控等級
    assert all(i["kpivControlLevel"] == item["kpivControlLevel"] for i in items)

    # 點檢紀錄不可刪除（稽核證據）：沒有刪除 API，紀錄與照片都還在
    for i in items:
        path = AR_UPLOAD_DIR / i["photoUrl"][len(AR_UPLOAD_URL_PREFIX) + 1 :]
        assert client.delete(f"/api/v1/check-inspections/{i['id']}").status_code in (404, 405)
        assert path.exists()
    assert client.get("/api/v1/check-inspections").json()["total"] == 2
    # 清掉本測試的照片，避免影響其他測試對上傳目錄的檔案數檢查
    for i in items:
        (AR_UPLOAD_DIR / i["photoUrl"][len(AR_UPLOAD_URL_PREFIX) + 1 :]).unlink()


@pytest.mark.skipif(not V2.exists(), reason="數據庫-1019.xlsx 不存在")
def test_events_level_after_filter(client):
    with V2.open("rb") as fh:
        client.post(
            "/api/v1/import",
            files={"file": (DATA_NAME, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    full = client.get("/api/v1/events", params={"limit": 500}).json()
    counts = full["levelCounts"]
    assert sum(counts.values()) == len(full["items"])
    l3 = client.get("/api/v1/events", params={"levelAfter": 3, "limit": 500}).json()
    assert len(l3["items"]) == counts["3"] > 0
    assert {i["levelAfter"] for i in l3["items"]} == {3}
    assert l3["levelCounts"] == counts


@pytest.mark.skipif(not V2.exists(), reason="數據庫-1019.xlsx 不存在")
def test_level_changes_window_kind_and_paging(client):
    import datetime as dt
    import math

    with V2.open("rb") as fh:
        client.post(
            "/api/v1/import",
            files={"file": (DATA_NAME, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    now = dt.datetime.now(dt.timezone.utc)
    events = client.get("/api/v1/events", params={"limit": 500}).json()["items"]

    def at(value: str) -> dt.datetime:
        # SQLite 讀回的時間不帶時區，一律視為 UTC
        parsed = dt.datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)

    def expected(transition: str, days: int) -> int:
        since = now - dt.timedelta(days=days)
        return sum(1 for e in events if e["transition"] == transition and since <= at(e["effectiveAt"]) <= now)

    year = client.get("/api/v1/level-changes", params={"window": "year"}).json()
    assert year["counts"] == {"escalated": expected("ESCALATED", 365), "improved": expected("IMPROVED", 365)}
    assert year["counts"]["escalated"] > 0
    assert {i["transition"] for i in year["items"]} == {"ESCALATED"}

    improved = client.get("/api/v1/level-changes", params={"window": "year", "kind": "improved"}).json()
    assert {i["transition"] for i in improved["items"]} <= {"IMPROVED"}
    assert all(not i["improvePlanned"] for i in improved["items"])

    # 分頁：每頁 2 筆，頁數 = ceil(total / 2)；超出的頁碼收斂到最後一頁
    first = client.get("/api/v1/level-changes", params={"window": "year", "pageSize": 2}).json()
    assert first["pages"] == math.ceil(first["total"] / 2) and len(first["items"]) <= 2
    last = client.get("/api/v1/level-changes", params={"window": "year", "pageSize": 2, "page": 999}).json()
    assert last["page"] == last["pages"]
    seen = [
        (i["kpovNo"], i["equipmentCode"], i["effectiveAt"])
        for p in range(1, first["pages"] + 1)
        for i in client.get(
            "/api/v1/level-changes", params={"window": "year", "pageSize": 2, "page": p}
        ).json()["items"]
    ]
    assert len(seen) == first["total"]

    day = client.get("/api/v1/level-changes", params={"window": "day"}).json()
    assert day["counts"]["escalated"] == expected("ESCALATED", 1)
    assert client.get("/api/v1/level-changes", params={"window": "decade"}).status_code == 422


V3 = DATA


def _import_v3(client):
    with V3.open("rb") as fh:
        res = client.post(
            "/api/v1/import",
            files={"file": (DATA_NAME, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.skipif(not V3.exists(), reason="數據庫-1019.xlsx 不存在")
def test_complaints_list_and_summary(client):
    report = _import_v3(client)["report"]
    assert report["rowCounts"]["complaints"] == 1  # 1019 版只留序號 1（已對應 KPOV 的客訴）

    listing = client.get("/api/v1/complaints").json()
    assert listing["total"] == 1
    c = listing["items"][0]
    assert (c["seq"], c["kpovNo"], c["equipmentCode"]) == (1, "K00004", "OT00420118")
    assert c["complainedAt"].startswith("2026-05-11")
    # 1019 版新增：緊急措施／緊急措施時間；長期措施＝改善措施／改善時間
    assert c["emergencyMeasure"].startswith("1. 已導入使用智能電鎖")
    assert c["emergencyMeasureAt"].startswith("2026-05-11") and c["emergencyMeasureAt"].endswith("+00:00")
    assert c["improvement"] == "鎖付角度DOE優化，得出最佳參數保護"
    assert c["improvementAt"].startswith("2025-12-05")
    # 8D：改善前 Level 3、改善後 Level 1；KPIV 管控等級 E -> A
    d8 = c["eightD"]
    assert (d8["before"]["level"], d8["after"]["level"]) == (3, 1)
    assert (d8["before"]["kpiv"]["level"], d8["after"]["kpiv"]["level"]) == ("E", "A")
    assert d8["measures"]["owner"] == "劉鎮鑫" and d8["measures"]["doneAt"].startswith("2025-12-05")
    # 篩選（spec §17）：客訴沒有機種，第二個篩選為客戶；站別取 KPOV 對應的站別
    assert c["station"] == "鎖銅排" and listing["options"]["groups"] == ["台南廠"]
    assert client.get("/api/v1/complaints", params={"group": "台南廠", "station": "鎖銅排", "kpov": "K00004"}).json()["total"] == 1
    assert client.get("/api/v1/complaints", params={"station": "鎖後蓋"}).json()["total"] == 0
    assert client.get("/api/v1/complaints", params={"occurredFrom": "2026-05-11", "occurredTo": "2026-05-11"}).json()["total"] == 1
    assert client.get("/api/v1/complaints", params={"occurredFrom": "2026-05-12"}).json()["total"] == 0
    # 預計 2025/12/5、實際 2025/12/5：準時完成，不進圓餅
    assert c["due"]["status"] == "ontime" and listing["dueStats"]["overdue"] == 0
    assert client.get(f"/api/v1/complaints/{c['id']}").json()["eightD"] == d8
    assert client.get("/api/v1/complaints/999999").status_code == 404

    summary = client.get("/api/v1/complaints/summary").json()
    counts = summary["levelCounts"]
    assert {k: counts[k] for k in "0123"} == {"0": 0, "1": 1, "2": 0, "3": 0} and counts["total"] == 1
    row = summary["items"][0]
    assert row["mapped"] and (row["station"], row["kpovNo"], row["complaintCount"]) == ("鎖銅排", "K00004", 1)
    assert row["levelOrig"]["after"] == 3
    assert (row["levelChanged"]["before"], row["levelChanged"]["after"]) == (3, 1)
    # 措施表：緊急措施＝緊急措施欄；長期措施＝改善措施／改善時間；措施層別讀 Excel（AC、AD 欄有填）
    assert row["emergency"] == {"text": c["emergencyMeasure"], "at": c["emergencyMeasureAt"]}
    assert row["longTerm"] == {"text": c["improvement"], "at": c["improvementAt"]}
    assert row["layer"] == {"summary": "技術解・KPOV：設備攔截；KPIV：防呆防錯"}
    assert row["improvedAt"].startswith("2025-12-05") and not row["improvePlanned"]
    assert row["complaintId"] == c["id"]

    scoped = client.get("/api/v1/complaints/summary", params={"target": "equip:OT00420118"}).json()
    assert scoped["levelCounts"]["total"] == 1 and scoped["total"] == 1


@pytest.mark.skipif(not V3.exists(), reason="數據庫-1019.xlsx 不存在")
def test_process_summary_and_repairs_list(client):
    _import_v3(client)
    repairs = client.get("/api/v1/repairs", params={"pageSize": 50}).json()
    assert repairs["total"] == 28
    assert client.get("/api/v1/repairs", params={"kpov": "K00057"}).json()["total"] > 0
    assert {"groups", "stations", "kpovs"} <= set(repairs["options"])

    summary = client.get("/api/v1/process/summary").json()
    assert summary["pageSize"] == 10 and len(summary["items"]) <= 10
    counted = sum(summary["levelCounts"]["current"].values())
    assert counted == summary["levelCounts"]["total"]
    # 對得到 KPOV 的維修都要進到彙總（對不到 KPOV 的不列入）
    states = {(r["kpovNo"], r["equipmentCode"]) for r in client.get("/api/v1/kpov", params={"pageSize": 500}).json()["items"]}
    mapped_total = sum(1 for r in repairs["items"] if (r["kpovNo"], r["equipmentCode"]) in states)
    assert summary["levelCounts"]["total"] == mapped_total == 26
    # 每筆維修一列
    full = client.get("/api/v1/process/summary", params={"pageSize": 50}).json()
    assert full["total"] == 26 and len(full["items"]) == 26
    row = next(r for r in full["items"] if r["repairSerial"] == "ALG25B01310WB")
    history = client.get(f"/api/v1/kpov/{row['kpovNo']}/{row['equipmentCode']}/history").json()["events"]
    mine = {e["type"]: e for e in history if e["repairSerial"] == "ALG25B01310WB"}
    # Level(原)＝該筆維修的惡化事件前→後；Level(變化後)＝該筆維修的改善事件前→後
    assert (row["levelOrig"]["before"], row["levelOrig"]["after"]) == (
        mine["DEGRADE"]["levelBefore"], mine["DEGRADE"]["levelAfter"],
    )
    assert (row["levelChanged"]["before"], row["levelChanged"]["after"]) == (
        mine["IMPROVE"]["levelBefore"], mine["IMPROVE"]["levelAfter"],
    )
    # 1019 版：緊急措施＝BM／BN；長期措施＝BR 改善措施／BQ 改善時間；措施層別讀 8D 區塊（AN–AP 有填）
    assert row["emergency"] == {"text": "下個人工站及總檢加強檢驗(異常處打點)", "at": "2025-11-17T00:00:00+00:00"}
    assert row["longTerm"] == {"text": "鎖付角度DOE優化，得出最佳參數保護", "at": "2025-11-17T00:00:00+00:00"}
    assert row["layer"] == {"summary": "技術解・KPOV：設備攔截；KPIV：防呆防錯、智能監控"}
    assert row["complaintCount"] == 0
    detail = client.get(f"/api/v1/repairs/{row['repairId']}").json()
    assert detail["serialNo"] == "ALG25B01310WB" and detail["emergencyMeasure"] == row["emergency"]["text"]
    assert (detail["eightD"]["before"]["level"], detail["eightD"]["after"]["level"]) == (2, 0)
    assert detail["eightD"]["measures"]["owner"] == "肖華陽"
    assert client.get("/api/v1/repairs/999999").status_code == 404


@pytest.mark.skipif(not V3.exists(), reason="數據庫-1019.xlsx 不存在")
def test_layer_is_read_only_from_excel(client):
    """措施層別一律讀 Excel 的 8D 區塊，系統內手動分類的 API 已移除。"""
    _import_v3(client)
    gone = client.put(
        "/api/v1/emergency-measures",
        json={"repairSerial": "x", "kpovNo": "K00004", "equipmentCode": "OT00420118", "solutionType": "management"},
    )
    assert gone.status_code in (404, 405)
    changes = client.get("/api/v1/level-changes", params={"window": "year", "kind": "escalated"}).json()
    assert changes["items"]
    for row in changes["items"]:
        assert set(row["layer"]) == {"summary"}
        assert set(row["emergency"]) == {"text", "at"} and set(row["longTerm"]) == {"text", "at"}


@pytest.mark.skipif(not V3.exists(), reason="數據庫-1019.xlsx 不存在")
def test_station_risk_counts(client):
    import collections
    import datetime as dt

    _import_v3(client)
    year = client.get("/api/v1/station-risk", params={"window": "year"}).json()

    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=365)
    repairs = client.get("/api/v1/repairs", params={"pageSize": 50}).json()["items"]
    expected = collections.Counter(
        r["equipmentCode"]
        for r in repairs
        if r["testedAt"] and since <= dt.datetime.fromisoformat(r["testedAt"]) <= now
    )
    assert {code: v["repairs"] for code, v in year["stations"].items() if v["repairs"]} == dict(expected)
    # 1019 版客訴報表只有序號 1（OT00420118），沒有未對應站別的客訴
    assert year["stations"]["OT00420118"]["complaints"] == 1
    assert year["unmappedComplaints"] == 0
    # 最嚴重 Level：OT00420118 有序號 1 的客訴（改善前 Level 3）-> 3
    assert year["stations"]["OT00420118"]["worstLevel"] == 3
    # 只有維修的站：worstLevel 為該站各筆維修惡化事件後 Level 的最大值
    history_levels = {}
    for r in repairs:
        if r["testedAt"] and since <= dt.datetime.fromisoformat(r["testedAt"]) <= now:
            res = client.get(f"/api/v1/kpov/{r['kpovNo']}/{r['equipmentCode']}/history")
            if res.status_code == 404:
                continue  # KPOV 庫沒有這個 KPOV×設備（例：鎖後蓋 K00051），沒有等級事件
            for e in res.json()["events"]:
                if e["repairSerial"] == r["serialNo"] and e["type"] == "DEGRADE":
                    code = r["equipmentCode"]
                    history_levels[code] = max(history_levels.get(code, -1), e["levelAfter"])
    for code, level in history_levels.items():
        if not year["stations"][code]["complaints"]:
            assert year["stations"][code]["worstLevel"] == level, code

    day = client.get("/api/v1/station-risk", params={"window": "day"}).json()
    assert all(v["repairs"] == 0 and v["complaints"] == 0 for v in day["stations"].values())
    assert client.get("/api/v1/station-risk", params={"window": "decade"}).status_code == 422


@pytest.mark.skipif(not V3.exists(), reason="數據庫-1019.xlsx 不存在")
def test_station_level_charts(client):
    """站別柱狀圖：KPOV 原始 Level 分佈；期間內客訴／維修筆數依發生當時 Level，與風險地圖一致。"""
    _import_v3(client)

    kpov = client.get("/api/v1/station-levels/kpov").json()
    codes = [s["equipmentCode"] for s in kpov["stations"]]
    assert len(codes) == len(set(codes)) == 18
    assert codes[0] == "OT00400010"  # 依 KPOV 數據庫列序（製程順序）
    # 與象限圖的基準口徑同一個母體
    baseline = client.get("/api/v1/quadrant", params={"view": "baseline"}).json()["scope"]
    for level in range(4):
        assert sum(s["counts"][str(level)] for s in kpov["stations"]) == baseline[f"level{level}"]

    events = client.get("/api/v1/station-levels/events", params={"window": "year"}).json()
    risk = client.get("/api/v1/station-risk", params={"window": "year"}).json()
    by_code = {s["equipmentCode"]: s for s in events["stations"]}
    for code, r in risk["stations"].items():
        if code not in by_code:
            continue
        drawn = sum(by_code[code]["repairs"].values())
        assert drawn <= r["repairs"]
    total_repairs = sum(sum(s["repairs"].values()) for s in events["stations"])
    assert total_repairs + events["unknownLevel"]["repairs"] == sum(r["repairs"] for r in risk["stations"].values())
    # 序號 1 的客訴：OT00420118、改善前 Level 3
    assert by_code["OT00420118"]["complaints"]["3"] == 1
    assert events["unmappedComplaints"] == 0

    # 篩選：只看 OP 站時不會出現 CTP 設備
    op = client.get("/api/v1/station-levels/events", params={"window": "year", "attribute": "OP"}).json()
    assert op["stations"] and all(s["equipmentCode"].startswith("A") for s in op["stations"])
    day = client.get("/api/v1/station-levels/events", params={"window": "day"}).json()
    assert all(not any(s["repairs"].values()) for s in day["stations"])


@pytest.mark.skipif(not V3.exists(), reason="數據庫-1019.xlsx 不存在")
def test_window_filters_quadrant_and_tracking(client):
    """期間篩選連動：象限圖母體為全部 KPOV，start＝期間第一天當時的分佈；客訴、製程追蹤依日期篩選。"""
    import collections
    import datetime as dt

    _import_v3(client)
    now = dt.datetime.now(dt.timezone.utc)

    def at(value):
        parsed = dt.datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)

    full = client.get("/api/v1/quadrant").json()
    assert full["scope"]["total"] == 331
    assert full["start"] is None

    # 有等級事件的 KPOV（維修或計入等級的 PCN，v2.19）：以 history 逐筆推算「某時點」的 Level，作為期初分佈的獨立對照
    repairs = client.get("/api/v1/repairs", params={"pageSize": 50}).json()["items"]
    pcn_keys = {
        (c["kpovNo"], c["equipmentCode"])
        for c in client.get("/api/v1/kpov", params={"pageSize": 500}).json()["items"]
        if c.get("kpovNo") and c.get("equipmentCode")
    }
    histories = []
    for key in {(r["kpovNo"], r["equipmentCode"]) for r in repairs if r["kpovNo"] and r["equipmentCode"]} | pcn_keys:
        res = client.get(f"/api/v1/kpov/{key[0]}/{key[1]}/history")
        if res.status_code != 200:
            continue
        h = res.json()
        steps = [(at(e["effectiveAt"]), 1, e["levelAfter"]) for e in h["events"]]
        # PCN 與維修同時刻時 PCN 在前（rank 0）
        steps += [(at(c["effectiveAt"]), 0, c["counted"]["levelAfter"]) for c in h["changes"] if c.get("counted")]
        if steps:
            h["steps"] = sorted(steps, key=lambda t: (t[0], t[1]))
            histories.append(h)

    def level_at(history, when):
        level = history["baseline"]["level"]
        for effective, _, after in history["steps"]:
            if effective <= when:
                level = after
        return level

    for window, days in (("day", 1), ("week", 7), ("month", 30), ("year", 365)):
        q = client.get("/api/v1/quadrant", params={"window": window}).json()
        # 母體固定：現在與期初都是全部 KPOV
        assert q["scope"] == full["scope"], window
        assert q["start"]["total"] == 331, window
        since = now - dt.timedelta(days=days)
        expected = collections.Counter({f"level{i}": full["baseline"][f"level{i}"] for i in range(4)})
        for h in histories:
            expected[f"level{h['baseline']['level']}"] -= 1
            expected[f"level{level_at(h, since)}"] += 1
        assert {f"level{i}": q["start"][f"level{i}"] for i in range(4)} == dict(expected), window

    # Level 明細與象限圖同一母體：帶不帶 window 都是全部 KPOV
    assert client.get("/api/v1/kpov", params={"pageSize": 500}).json()["total"] == 331
    assert client.get("/api/v1/kpov", params={"window": "day", "pageSize": 500}).json()["total"] == 331

    # 客訴、製程追蹤依日期篩選
    c_all = client.get("/api/v1/complaints/summary").json()
    c_day = client.get("/api/v1/complaints/summary", params={"window": "day"}).json()
    assert c_all["levelCounts"]["total"] == 1 and c_day["levelCounts"]["total"] == 0 and c_day["total"] == 0
    p_all = client.get("/api/v1/process/summary").json()
    p_month = client.get("/api/v1/process/summary", params={"window": "month", "pageSize": 50}).json()
    month_since = now - dt.timedelta(days=30)
    assert all(month_since <= at(r["occurredAt"]) for r in p_month["items"])
    assert p_month["total"] < p_all["total"]
    assert client.get("/api/v1/quadrant", params={"window": "decade"}).status_code == 422


@pytest.mark.skipif(not DATA.exists(), reason="數據庫-1019.xlsx 不存在")
def test_check_items_1019_control_level_and_once_per_shift(client):
    """1019 版高風險項點檢：KPIV(x) 點檢內容與管控等級；「開線/班」每班只算 1 格，巡檢 2h 維持多格。"""
    report = _import_v3(client)["report"]
    assert report["rowCounts"]["checkItems"] == 10
    items = client.get("/api/v1/check-monitor").json()["items"]
    assert len(items) == 10
    assert all(i["kpivControlLevel"] for i in items)
    smart = [i for i in items if i["kpivControlLevel"].startswith("A")]
    assert [i["equipmentCode"] for i in smart] == ["OT00420108"]  # 鎖軟銅排2 改為 CTP 設備
    for i in items:
        if "巡檢" in (i["frequency"] or ""):
            assert i["intervalHours"] == 2.0 and len(i["slots"]) == 5
        else:
            assert i["intervalHours"] == 10.0 and len(i["slots"]) == 1


@pytest.mark.skipif(not DATA.exists(), reason="數據庫-1019.xlsx 不存在")
def test_dashboard_hides_records_of_retired_items(client):
    """點檢內容改版後，舊項目底下的拍照點檢紀錄不在儀表板顯示（使用者決定只看新項目）。"""
    from app.db import SessionLocal
    from app.models import CheckPhotoInspection

    _import_v3(client)
    station = client.get("/api/v1/check-items").json()["stations"][0]
    item = client.get("/api/v1/check-items", params={"station": station}).json()["items"][0]
    with SessionLocal() as s:
        s.add_all(
            [
                CheckPhotoInspection(
                    equipment_code=item["equipmentCode"], kpov_no=item["kpovNo"], check_content=item["checkContent"],
                    status="ok", photo_url="/api/ar/uploads/checks/new.png", dataset="WJ1-DCS-PM1",
                ),
                CheckPhotoInspection(
                    equipment_code=item["equipmentCode"], kpov_no=item["kpovNo"], check_content="生產時是否有進行數量管控",
                    status="ok", photo_url="/api/ar/uploads/checks/old.png", dataset="WJ1-DCS-PM1",
                ),
            ]
        )
        s.commit()
    listed = client.get("/api/v1/check-inspections").json()
    assert listed["total"] == 1 and listed["items"][0]["checkContent"] == item["checkContent"]
    assert sum(r["total"] for r in client.get("/api/v1/check-inspections/stats").json()) == 1


@pytest.mark.skipif(not DATA.exists(), reason="數據庫-1019.xlsx 不存在")
def test_improvement_never_precedes_its_own_defect(client):
    """改善時間只填日期（00:00）時，不得排在同一筆維修當天稍晚的不良之前（否則現況停在惡化後等級）。"""
    import datetime as dt

    _import_v3(client)
    history = client.get("/api/v1/kpov/K00051/A0006/history").json()
    mine = [e for e in history["events"] if e["repairSerial"] == "IOW26A00347W0"]
    degrade = next(e for e in mine if e["type"] == "DEGRADE")
    improve = next(e for e in mine if e["type"] == "IMPROVE")
    assert dt.datetime.fromisoformat(improve["effectiveAt"]) >= dt.datetime.fromisoformat(degrade["effectiveAt"])
    # 前後等級要接得起來：改善前＝惡化後
    assert improve["levelBefore"] == degrade["levelAfter"] == 3 and improve["levelAfter"] == 0
    assert history["current"]["level"] == 0
