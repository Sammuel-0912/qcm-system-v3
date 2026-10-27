"""修護報表偵測方式空白時以 8D 偵測度補上（spec §20）。"""
from __future__ import annotations

from app.importer.excel import _fill_methods_from_eight_d
from tests.test_rbac import ADMIN, V1026, _import, app_ctx, needs_data  # noqa: F401  (app_ctx 為 fixture)

BY_SCORE = {8: "人工檢測(未證實可靠)", 5: "機器偵測(已證實可靠)"}


class _Report:
    def __init__(self):
        self.warnings: list[str] = []


def test_fill_only_blank_methods_by_score():
    data = {"serial_no": "SN1", "small_y_method_after": None, "big_y_method_after": "隨機稽查",
            "d8_small_y_score_before": 8, "d8_big_y_score_before": 5,
            "d8_small_y_score_after": 5, "d8_big_y_score_after": 4}
    report = _Report()
    _fill_methods_from_eight_d(data, BY_SCORE, 7, report)
    assert data["small_y_method_after"] == "人工檢測(未證實可靠)"
    assert data["big_y_method_after"] == "隨機稽查"  # 有填的不動
    assert data["small_y_method_improved"] == "機器偵測(已證實可靠)"
    assert data.get("big_y_method_improved") is None  # 4 分對不到
    assert len(report.warnings) == 2 and "第 7 列" in report.warnings[0] and "對不到" in report.warnings[1]


def test_nothing_to_fill():
    data = {"small_y_method_after": "A", "d8_small_y_score_before": None}
    report = _Report()
    _fill_methods_from_eight_d(data, BY_SCORE, 3, report)
    assert report.warnings == []


@needs_data
def test_1026_blank_rows_get_levels_from_eight_d(app_ctx):
    su = app_ctx(ADMIN)
    r = _import(su, V1026, "WJ1-DCS-PM1-數據庫-1026.xlsx")
    assert r.status_code == 200
    filled = [w for w in r.json()["report"]["warnings"] if "依 8D 偵測度補上" in w]
    assert len(filled) == 2 and any("IOW26A01997W0" in w for w in filled) and any("IOW26A02741W0" in w for w in filled)
    # 人工四（A0004）這兩筆有等級事件了：不良發生時 Level 2、改善後 Level 0（與 8D 上的 Level 相同）
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import FactLevelEvent, FactRepair

    with SessionLocal() as s:
        for sn in ("IOW26A01997W0", "IOW26A02741W0"):
            repair = s.scalars(select(FactRepair).where(FactRepair.serial_no == sn)).one()
            assert (repair.small_y_method_after, repair.big_y_method_after) == ("人工檢測(未證實可靠)", "機器偵測(已證實可靠)")
            events = {e.event_type: e.level_after for e in s.scalars(select(FactLevelEvent).where(FactLevelEvent.repair_id == repair.id))}
            assert events == {"DEGRADE": 2, "IMPROVE": 0} == {"DEGRADE": repair.d8_level_before, "IMPROVE": repair.d8_level_after}
