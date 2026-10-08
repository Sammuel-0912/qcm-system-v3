"""AR 點檢 API 測試 — ar-integration-spec.md §5 / §6。"""
from __future__ import annotations

import io
import os
import pathlib
import tempfile

import pytest

RAW = pathlib.Path(__file__).resolve().parent.parent.parent / "raw_data.xlsx"


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


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_quality_bridge_links_to_active_batch(client):
    with RAW.open("rb") as fh:
        imported = client.post(
            "/api/v1/import",
            files={"file": ("raw_data.xlsx", fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
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


@pytest.mark.skipif(not RAW.exists(), reason="raw_data.xlsx 不存在")
def test_equipment_options_come_from_active_batch(client):
    with RAW.open("rb") as fh:
        client.post(
            "/api/v1/import",
            files={"file": ("raw_data.xlsx", fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    body = client.get("/api/ar/equipment-options").json()
    codes = {o["equipmentCode"] for o in body["options"]}
    assert "OT00420118" in codes
    # OP 站沒有設備代碼，不該出現在下拉中
    assert None not in codes


V2 = RAW.parent / "數據庫-1008.xlsx"


@pytest.mark.skipif(not V2.exists(), reason="數據庫-1008.xlsx 不存在")
def test_item_inspection_feeds_check_monitor(client):
    with V2.open("rb") as fh:
        imported = client.post(
            "/api/v1/import",
            files={"file": (V2.name, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
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


@pytest.mark.skipif(not V2.exists(), reason="數據庫-1008.xlsx 不存在")
def test_history_includes_pcn_and_plant_wide_ecn(client):
    with V2.open("rb") as fh:
        client.post(
            "/api/v1/import",
            files={"file": (V2.name, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    body = client.get("/api/v1/kpov/K00002/OT00420102/history").json()
    kinds = [c["kind"] for c in body["changes"]]
    assert kinds.count("PCN") == 1 and kinds.count("ECN") == 1
    pcn = next(c for c in body["changes"] if c["kind"] == "PCN")
    assert (pcn["levelBefore"], pcn["levelAfter"]) == ("Level 3", "Level 1")

    # OP 站也看得到全廠 ECN
    op = client.get("/api/v1/kpov/K00048/A0001/history").json()
    assert [c["kind"] for c in op["changes"]] == ["ECN"]
