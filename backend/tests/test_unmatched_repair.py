"""維修的（KPOV, 設備ID）在 KPOV 庫找不到時，匯入警告逐筆列出（v2.18）。"""
from __future__ import annotations

from tests.test_rbac import ADMIN, V1026, XLSX, app_ctx, needs_data  # noqa: F401  (app_ctx 為 fixture)


@needs_data
def test_repairs_missing_from_kpov_library_are_warned(app_ctx):
    su = app_ctx(ADMIN)
    res = su.post("/api/v1/import", files={"file": ("WJ1-DCS-PM1-數據庫-1026.xlsx", V1026.read_bytes(), XLSX)})
    assert res.status_code == 200, res.text
    report = res.json()["report"]

    # 1026 版：鎖後蓋（A0003）的兩筆維修填了 K00051，但 KPOV 庫的 K00051 沒有 A0003
    warned = [w for w in report["warnings"] if "在 KPOV 庫中找不到" in w]
    assert len(warned) == 2
    assert all("K00051 × 設備 A0003" in w and w.startswith("修護報表第 ") for w in warned)
    assert any("IOV26307356W0" in w for w in warned) and any("IOV26801248W0" in w for w in warned)
    repair_keys = [u for u in report["unmatchedKeys"] if u["table"] == "fact_repair"]
    assert repair_keys == [
        {"table": "fact_repair", "kpovNo": "K00051", "equipmentCode": "A0003", "count": 2,
         "reason": "維修的 KPOV × 設備 組合在 KPOV 庫中不存在"}
    ]

    # 清單上這兩筆的 Level 是空的（畫面顯示 －），其餘 K00051 都有
    rows = []
    for page in (1, 2):
        rows += su.get("/api/v1/repairs", params={"pageSize": 50, "page": page}).json()["items"]
    k51 = [r for r in rows if r["kpovNo"] == "K00051"]
    assert {r["serialNo"] for r in k51 if r["levelBefore"] is None} == {"IOV26307356W0", "IOV26801248W0"}

    # 再匯入一次（沿用合併）仍會提醒，不會因為內容沒變就消失
    again = su.post("/api/v1/import", files={"file": ("WJ1-DCS-PM1-數據庫-1026.xlsx", V1026.read_bytes(), XLSX)})
    assert len([w for w in again.json()["report"]["warnings"] if "在 KPOV 庫中找不到" in w]) == 2
