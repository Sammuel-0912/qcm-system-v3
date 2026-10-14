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

    # OP 站：K00048 插線/理線沒有 PCN，只看得到全廠 ECN
    op = client.get("/api/v1/kpov/K00048/A0001/history").json()
    assert [c["kind"] for c in op["changes"]] == ["ECN"]

    # OP 站的 PCN（Excel 未填設備ID）也要出現：鎖後蓋 = A0003
    pcn_op = client.get("/api/v1/kpov/K00001/A0003/history").json()
    assert sorted(c["kind"] for c in pcn_op["changes"]) == ["ECN", "PCN"]


@pytest.mark.skipif(not V2.exists(), reason="數據庫-1008.xlsx 不存在")
def test_photo_upload_records_inspection(client):
    with V2.open("rb") as fh:
        client.post(
            "/api/v1/import",
            files={"file": (V2.name, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
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


@pytest.mark.skipif(not V2.exists(), reason="數據庫-1008.xlsx 不存在")
def test_events_level_after_filter(client):
    with V2.open("rb") as fh:
        client.post(
            "/api/v1/import",
            files={"file": (V2.name, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    full = client.get("/api/v1/events", params={"limit": 500}).json()
    counts = full["levelCounts"]
    assert sum(counts.values()) == len(full["items"])
    l3 = client.get("/api/v1/events", params={"levelAfter": 3, "limit": 500}).json()
    assert len(l3["items"]) == counts["3"] > 0
    assert {i["levelAfter"] for i in l3["items"]} == {3}
    assert l3["levelCounts"] == counts


@pytest.mark.skipif(not V2.exists(), reason="數據庫-1008.xlsx 不存在")
def test_level_changes_window_kind_and_paging(client):
    import datetime as dt
    import math

    with V2.open("rb") as fh:
        client.post(
            "/api/v1/import",
            files={"file": (V2.name, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
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


V3 = RAW.parent / "數據庫-1011.xlsx"


def _import_v3(client):
    with V3.open("rb") as fh:
        res = client.post(
            "/api/v1/import",
            files={"file": (V3.name, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
    assert res.status_code == 200, res.text
    return res.json()


@pytest.mark.skipif(not V3.exists(), reason="數據庫-1011.xlsx 不存在")
def test_complaints_list_and_summary(client):
    report = _import_v3(client)["report"]
    assert report["rowCounts"]["complaints"] == 8  # 序號 1–6、8、9；範本列與字典列略過

    listing = client.get("/api/v1/complaints").json()
    assert listing["total"] == 8 and len(listing["items"]) == 8
    by_seq = {c["seq"]: c for c in listing["items"]}
    assert by_seq[8]["complainedAt"].startswith("2026-07-10")  # 文字日期
    assert by_seq[2]["doneAt"] is None  # 「1.NA 2.2026/7/24」尚未全部完成
    assert by_seq[2]["plannedAt"].startswith("2026-11-03")  # 多項取最晚
    assert by_seq[1]["kpovNo"] == "K00004" and by_seq[2]["kpovNo"] is None  # #N/A -> 空
    assert client.get("/api/v1/complaints", params={"q": "sharp"}).json()["total"] == 2
    paged = client.get("/api/v1/complaints", params={"pageSize": 3, "page": 3}).json()
    assert paged["pages"] == 3 and len(paged["items"]) == 2

    summary = client.get("/api/v1/complaints/summary").json()
    # 每格只有一個數字：依改善後 Level（目前狀態）
    counts = summary["levelCounts"]
    assert {k: counts[k] for k in "0123"} == {"0": 3, "1": 4, "2": 1, "3": 0} and counts["total"] == 8
    mapped = [r for r in summary["items"] if r["mapped"]]
    assert len(mapped) == 1
    row = mapped[0]
    assert (row["station"], row["kpovNo"], row["complaintCount"]) == ("鎖銅排", "K00004", 1)
    assert sum(r["complaintCount"] for r in summary["items"]) == 8
    # 客訴：Level(原)＝改善前；Level(變化後)＝改善前→改善後；措施層別讀 Excel（序號 1：AC、AD 欄有填）
    assert row["levelOrig"]["after"] == 3
    assert (row["levelChanged"]["before"], row["levelChanged"]["after"]) == (3, 1)
    assert row["layer"]["editable"] is False
    assert row["layer"]["summary"] == "技術解・KPOV：設備攔截；KPIV：防呆防錯"
    assert row["emergency"]["text"] == "導入智能機械手臂自動鎖付"
    assert row["improvedAt"].startswith("2025-12-05") and not row["improvePlanned"]
    # 序號 6：實際完成未填、預計 2026/9/10 已過 -> 預計且逾期
    overdue = [r for r in summary["items"] if r["improveOverdue"]]
    assert overdue and all(r["improvePlanned"] for r in overdue)

    # 有篩選時只計入對應到範圍內 KPOV 的客訴
    scoped = client.get("/api/v1/complaints/summary", params={"target": "equip:OT00420118"}).json()
    assert scoped["levelCounts"]["total"] == 1 and scoped["total"] == 1


@pytest.mark.skipif(not V3.exists(), reason="數據庫-1011.xlsx 不存在")
def test_process_summary_and_repairs_list(client):
    _import_v3(client)
    repairs = client.get("/api/v1/repairs", params={"pageSize": 50}).json()
    assert repairs["total"] == 27
    assert client.get("/api/v1/repairs", params={"q": "K00057"}).json()["total"] > 0

    summary = client.get("/api/v1/process/summary").json()
    assert summary["pageSize"] == 10 and len(summary["items"]) <= 10
    counted = sum(summary["levelCounts"]["current"].values())
    assert counted == summary["levelCounts"]["total"]
    # 對得到 KPOV 的維修都要進到彙總（K00051/A0003 對不到 KPOV，不列入）
    assert summary["levelCounts"]["total"] == 25
    # 每筆維修一列
    full = client.get("/api/v1/process/summary", params={"pageSize": 50}).json()
    assert full["total"] == 25 and len(full["items"]) == 25
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
    assert row["emergency"]["at"].startswith("2025-11-17T09:20")  # 修復時間
    assert row["longTerm"] is None and row["complaintCount"] == 0
    assert row["layer"]["editable"] is False


@pytest.mark.skipif(not V3.exists(), reason="數據庫-1011.xlsx 不存在")
def test_emergency_measure_classification(client):
    _import_v3(client)
    escalated = client.get("/api/v1/level-changes", params={"window": "year", "pageSize": 50}).json()["items"]
    row = next(i for i in escalated if i["repairSerial"])
    assert row["complaintCount"] == 0 and row["layer"]["measure"] is None
    assert row["layer"]["editable"] is True
    improved = client.get("/api/v1/level-changes", params={"window": "year", "kind": "improved"}).json()["items"]
    assert improved and all(i["layer"]["editable"] is False for i in improved)

    key = {"repairSerial": row["repairSerial"], "kpovNo": row["kpovNo"], "equipmentCode": row["equipmentCode"]}

    def save(**body):
        return client.put("/api/v1/emergency-measures", json={**key, **body})

    def current():
        items = client.get("/api/v1/level-changes", params={"window": "year", "pageSize": 50}).json()["items"]
        return next(
            i["layer"]["measure"]
            for i in items
            if (i["repairSerial"], i["kpovNo"], i["equipmentCode"])
            == (key["repairSerial"], key["kpovNo"], key["equipmentCode"])
        )

    assert save(solutionType="technical", techTarget="KPOV", designElimination=True).status_code == 200
    m = current()
    assert (m["solutionType"], m["techTarget"], m["designElimination"], m["equipmentInterception"]) == (
        "technical", "KPOV", True, False,
    )

    # 改成 KPIV：KPOV 的兩個框要被清掉
    save(solutionType="technical", techTarget="KPIV", designElimination=True, smartMonitoring=True)
    m = current()
    assert m["techTarget"] == "KPIV" and m["smartMonitoring"] and not m["designElimination"]

    # 改成管理解：技術欄位清空
    assert save(solutionType="management", managementNote="  加強稽核頻率  ").status_code == 200
    m = current()
    assert m["solutionType"] == "management" and m["managementNote"] == "加強稽核頻率"
    assert m["techTarget"] is None and not m["smartMonitoring"]

    assert save(solutionType="management", managementNote="   ").status_code == 422
    assert save(solutionType="technical").status_code == 422
    assert save(solutionType="other").status_code == 422
    missing = client.put(
        "/api/v1/emergency-measures",
        json={**key, "repairSerial": "NOPE", "solutionType": "management", "managementNote": "x"},
    )
    assert missing.status_code == 404

    # 不掛批次：重新匯入後分類仍在
    _import_v3(client)
    assert current()["managementNote"] == "加強稽核頻率"


@pytest.mark.skipif(not V3.exists(), reason="數據庫-1011.xlsx 不存在")
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
    # 只有序號 1 的客訴填了設備（OT00420118），其餘 7 筆未對應站別
    assert year["stations"]["OT00420118"]["complaints"] == 1
    assert year["unmappedComplaints"] == 7
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


@pytest.mark.skipif(not V3.exists(), reason="數據庫-1011.xlsx 不存在")
def test_window_filters_quadrant_and_tracking(client):
    """期間篩選連動：象限圖只算期間內有維修或客訴的 KPOV；客訴、製程追蹤依日期篩選。"""
    import datetime as dt

    _import_v3(client)
    now = dt.datetime.now(dt.timezone.utc)

    def at(value):
        parsed = dt.datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)

    full = client.get("/api/v1/quadrant").json()["scope"]
    year = client.get("/api/v1/quadrant", params={"window": "year"}).json()["scope"]
    day = client.get("/api/v1/quadrant", params={"window": "day"}).json()["scope"]
    assert full["total"] == 331
    assert 0 < year["total"] < full["total"]
    assert day["total"] == 0

    # 象限圖的 KPOV 範圍＝期間內有維修（測試時間）或已對應客訴（客訴日期）的 KPOV
    since = now - dt.timedelta(days=365)
    repairs = client.get("/api/v1/repairs", params={"pageSize": 50}).json()["items"]
    complaints = client.get("/api/v1/complaints", params={"pageSize": 50}).json()["items"]
    keys = {(r["kpovNo"], r["equipmentCode"]) for r in repairs if r["testedAt"] and since <= at(r["testedAt"])}
    keys |= {
        (c["kpovNo"], c["equipmentCode"])
        for c in complaints
        if c["kpovNo"] and c["equipmentCode"] and c["complainedAt"] and since <= at(c["complainedAt"])
    }
    kpov_year = client.get("/api/v1/kpov", params={"window": "year", "pageSize": 500}).json()
    assert {(i["kpovNo"], i["equipmentCode"]) for i in kpov_year["items"]} <= keys
    assert kpov_year["total"] == year["total"]

    # 客訴、製程追蹤依日期篩選
    c_all = client.get("/api/v1/complaints/summary").json()
    c_day = client.get("/api/v1/complaints/summary", params={"window": "day"}).json()
    assert c_all["levelCounts"]["total"] == 8 and c_day["levelCounts"]["total"] == 0 and c_day["total"] == 0
    p_all = client.get("/api/v1/process/summary").json()
    p_month = client.get("/api/v1/process/summary", params={"window": "month", "pageSize": 50}).json()
    month_since = now - dt.timedelta(days=30)
    assert all(month_since <= at(r["occurredAt"]) for r in p_month["items"])
    assert p_month["total"] < p_all["total"]
    assert client.get("/api/v1/quadrant", params={"window": "decade"}).status_code == 422
