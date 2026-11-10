"""表頭簡繁體／空白不同也要對得到（1106 版 KPOV-by 站 整列表頭變簡體，高風險項點檢反而變繁體）。"""
from __future__ import annotations

from app.importer import mapping as M
from app.importer.excel import _map_header, _match_header


def test_header_key_ignores_script_and_spaces():
    assert M.header_key("KPOV 编号") == M.header_key("KPOV 編號") == M.header_key("KPOV編號")
    assert M.header_key("小y侦测度") == M.header_key("小y偵測度")
    assert M.header_key("设备ID") == M.header_key("設備ID")


def test_simplified_kpov_header_maps_all_required_columns():
    header = [M.normalize(h) for h in (
        "SPU流水号", "制程类别", "站别", "属性1", "站别", "分类", "KPOV", "KPOV 编号",
        "设备告警代码", "设备ID", "小y侦测度", "CC/SC原因", "大Y侦测度", "品控力等级",
    )]
    idx, matched = _map_header(header, M.KPOV_COLUMNS, {"station": "station_slot"}, ())
    assert set(M.KPOV_REQUIRED) <= matched
    # 兩個「站别」：最後一個才是原站別
    assert idx["station"] == 4 and idx["station_slot"] == 2
    assert idx["kpov_no"] == 7 and idx["kpov_name"] == 6
    assert idx["equipment_code"] == 9 and idx["big_y_score"] == 12


def test_traditional_check_item_header_matches_simplified_spec():
    assert _match_header("KPOV 編號", M.CHECK_ITEM_COLUMNS) == "KPOV 编号"
    # 最長匹配仍然成立：「KPOV 編號」不會被短規格「KPOV」吃掉
    assert _match_header("KPOV", M.CHECK_ITEM_COLUMNS) == "KPOV"
