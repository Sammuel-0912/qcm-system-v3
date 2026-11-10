"""客訴報表序號欄可填 13 碼英數產品序號（v2.17），數字流水號照舊。"""
from __future__ import annotations

import io
import pathlib

from tests.test_rbac import ADMIN, V1026, XLSX, app_ctx, needs_data  # noqa: F401  (app_ctx 為 fixture)

from app.importer.excel import _product_serial


def test_product_serial_rules():
    assert _product_serial("IOV25C75081W0") == "IOV25C75081W0"
    assert _product_serial(" iov25c75081w0 ") == "IOV25C75081W0"  # 前後空白、小寫都接受
    assert _product_serial("IOV25C7508") is None  # 長度不對
    assert _product_serial("IOV25C75081W-") is None  # 有符號
    assert _product_serial("ABCDEFGHIJKLM") is None  # 沒有數字
    assert _product_serial("1234567890123") is None  # 純數字是流水號，不是產品序號
    assert _product_serial("序號") is None
    assert _product_serial(None) is None


def _with_serials(path: pathlib.Path, serials: list[str]) -> bytes:
    """把客訴報表前幾筆資料列的序號改成指定文字。"""
    import openpyxl

    from app.importer import mapping as M

    wb = openpyxl.load_workbook(path)
    sheet = next(ws for ws in wb.worksheets if "客訴" in M.header_key(ws.title))
    rows = [r for r in sheet.iter_rows(min_row=M.COMPLAINT_HEADER_ROWS - 1) if isinstance(r[0].value, (int, float))]
    assert len(rows) >= len(serials)
    for row, serial in zip(rows, serials):
        row[0].value = serial
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@needs_data
def test_complaint_import_accepts_product_serial(app_ctx):
    su = app_ctx(ADMIN)

    def imported(serials):
        content = _with_serials(V1026, serials)
        res = su.post("/api/v1/import", files={"file": ("WJ1-DCS-PM1-數據庫-1026.xlsx", content, XLSX)})
        assert res.status_code == 200, res.text
        return res.json()["report"]

    plain = su.post("/api/v1/import", files={"file": ("WJ1-DCS-PM1-數據庫-1026.xlsx", V1026.read_bytes(), XLSX)})
    before = plain.json()["report"]["rowCounts"]["complaints"]
    assert before >= 1
    assert all(isinstance(c["seq"], int) and c["serialNo"] is None for c in su.get("/api/v1/complaints").json()["items"])

    # 13 碼產品序號：照常匯入，序號存在 serialNo
    report = imported(["IOV25C75081W0"])
    assert report["rowCounts"]["complaints"] == before
    items = su.get("/api/v1/complaints").json()["items"]
    hit = [c for c in items if c["serialNo"] == "IOV25C75081W0"]
    assert len(hit) == 1 and hit[0]["seq"] is None

    # 長度不對：不匯入，並在警告說明
    report = imported(["IOV25C7508"])
    assert report["rowCounts"]["complaints"] == before - 1
    assert any("IOV25C7508」不是 13 碼" in w for w in report["warnings"])
