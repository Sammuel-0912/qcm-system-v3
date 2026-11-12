"""刪除維修紀錄並重算等級（v2.20，spec §26）。

維修跨批次累積（REQ-IMP-11），在 Excel 刪列再匯入不會移除；管理者從製程清單刪除後，
等級事件以剩下的維修與 PCN 重新推導，結果要和「一開始就沒有這筆維修」的匯入完全一致。
"""
from __future__ import annotations

import io

import openpyxl

from tests.test_rbac import ADMIN, V1026, XLSX, app_ctx, needs_data  # noqa: F401  (app_ctx 為 fixture)

PM1, PM2 = "WJ1-DCS-PM1", "WJ1-DCS-PM2"


def _import(su, data: bytes, dataset: str, day: str = "1026"):
    res = su.post("/api/v1/import", files={"file": (f"{dataset}-數據庫-{day}.xlsx", data, XLSX)})
    assert res.status_code == 200, res.text
    return res.json()["report"]


def _repairs(su, dataset: str) -> list[dict]:
    out, page = [], 1
    while True:
        res = su.get("/api/v1/repairs", params={"pageSize": 50, "page": page}, headers={"X-QCM-Dataset": dataset}).json()
        out += res["items"]
        if len(out) >= res["total"] or not res["items"]:
            return out
        page += 1


def _levels(su, dataset: str) -> dict[tuple, tuple]:
    items = su.get("/api/v1/kpov", params={"pageSize": 500}, headers={"X-QCM-Dataset": dataset}).json()["items"]
    return {(k["kpovNo"], k["equipmentCode"]): (k["levelBaseline"], k["levelCurrent"]) for k in items}


def _without_row(raw: bytes, serial: str, kpov_no: str) -> bytes:
    wb = openpyxl.load_workbook(io.BytesIO(raw))
    ws = next(s for s in wb.worksheets if "修護" in s.title)
    for row in ws.iter_rows():
        values = {str(c.value).strip() for c in row if c.value is not None}
        if serial in values and kpov_no in values:
            ws.delete_rows(row[0].row)
            break
    else:
        raise AssertionError(f"修護報表找不到 {serial} × {kpov_no}")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@needs_data
def test_delete_repair_recomputes_levels(app_ctx):
    su = app_ctx(ADMIN)
    raw = V1026.read_bytes()
    _import(su, raw, PM1)
    before = _repairs(su, PM1)
    # 挑一筆讓現況和基準不同的維修（刪掉後等級應該會變）
    target = next(r for r in before if r["serialNo"] and r["levelAfter"] is not None and r["levelAfter"] != r["levelBefore"])
    key = (target["kpovNo"], target["equipmentCode"])

    # 一般使用者不能刪；別的批次／不存在的 id 回 404
    su.post("/api/v1/users", json={"username": "wj1op", "displayName": "WJ1", "password": "wj1-op-pass", "plant": "WJ1"})
    op = app_ctx({"username": "wj1op", "password": "wj1-op-pass"})
    assert op.delete(f"/api/v1/repairs/{target['id']}").status_code == 403
    assert su.delete("/api/v1/repairs/999999").status_code == 404

    levels_before = _levels(su, PM1)
    res = su.delete(f"/api/v1/repairs/{target['id']}", headers={"X-QCM-Dataset": PM1})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["deleted"] == {"serialNo": target["serialNo"], "kpovNo": key[0], "equipmentCode": key[1]}
    assert su.delete(f"/api/v1/repairs/{target['id']}").status_code == 404  # 已刪除

    after = _repairs(su, PM1)
    assert len(after) == len(before) - 1
    assert all(r["id"] != target["id"] for r in after)

    # 對照組：另一條線匯入「Excel 刪掉這一列」的檔案（沒有前一批可沿用）——所有 KPOV 的等級要一模一樣
    edited = _without_row(raw, target["serialNo"], key[0])
    _import(su, edited, PM2)
    assert _levels(su, PM1) == _levels(su, PM2)
    assert levels_before != _levels(su, PM1)  # 這筆維修確實影響等級，對照才有意義
    assert (body["levelBaseline"], body["levelCurrent"]) == _levels(su, PM1)[key]
    history = su.get(f"/api/v1/kpov/{key[0]}/{key[1]}/history", headers={"X-QCM-Dataset": PM1}).json()
    assert all(e.get("repairSerial") != target["serialNo"] for e in history["events"])

    # 匯入歷程留下刪除紀錄
    batch = next(b for b in su.get("/api/v1/import/history").json() if b["dataset"] == PM1 and b["isActive"])
    assert batch["rowCounts"]["repairs"] == len(after)

    # 之後匯入「已從 Excel 刪掉這一列」的檔案，不會再沿用回來
    report = _import(su, edited, PM1, day="1027")
    assert report["rowCounts"]["repairsCarried"] == 0
    assert all(r["serialNo"] != target["serialNo"] or r["kpovNo"] != key[0] for r in _repairs(su, PM1))
    assert _levels(su, PM1) == _levels(su, PM2)
