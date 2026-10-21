"""8D 明細（現狀盤查 → 原因 → 改善對策 → 改善後盤查），客訴與維修共用。

欄位定義見 importer/mapping.EIGHT_D_COLUMNS；維修的 8D 欄位有 d8_ 前綴。
"""
from __future__ import annotations

import datetime as dt

from ..importer.mapping import EIGHT_D_COLUMNS


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    value = value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value
    return value.isoformat()


def _side(get, suffix: str, kpov_field: str, big_item_field: str) -> dict:
    return {
        "bigY": {
            "item": get(big_item_field),
            "method": get(f"big_y_method_{suffix}"),
            "score": get(f"big_y_score_{suffix}"),
        },
        "smallY": {
            "kpov": get(kpov_field),
            "method": get(f"small_y_method_{suffix}"),
            "score": get(f"small_y_score_{suffix}"),
        },
        "level": get(f"level_{suffix}"),
        "kpiv": {
            "factor": get(f"kpiv_factor_{suffix}"),
            "foolproof": get(f"kpiv_foolproof_{suffix}"),
            "foolproofDesc": get(f"kpiv_foolproof_desc_{suffix}"),
            "monitor": get(f"kpiv_monitor_{suffix}"),
            "monitorDesc": get(f"kpiv_monitor_desc_{suffix}"),
            "level": get(f"kpiv_level_{suffix}"),
        },
    }


def eight_d_out(record, prefix: str = "") -> dict | None:
    """一筆客訴／維修的 8D 內容；整段都沒填（例：舊版修護報表）時回 None。"""

    def get(field: str):
        return getattr(record, prefix + field, None)

    if not any(get(f) not in (None, "") for f in EIGHT_D_COLUMNS.values()):
        return None
    return {
        "processUnit": get("process_unit"),
        "before": _side(get, "before", "product_kpov", "big_y_item_before"),
        "causes": {"occur": get("cause_occur"), "escape": get("cause_escape")},
        "measures": {
            "mgmtVerdict": get("mgmt_verdict"),
            "mgmt": get("mgmt_measure"),
            "tech": {
                "ccscInterception": get("tech_ccsc_interception"),
                "kpovDesignElimination": get("tech_kpov_design_elimination"),
                "kpovInterception": get("tech_kpov_interception"),
                "kpivFoolproof": get("tech_kpiv_foolproof"),
                "kpivSmart": get("tech_kpiv_smart"),
            },
            "content": get("countermeasure"),
            "owner": get("owner"),
            "plannedText": get("planned_text"),
            "doneText": get("done_text"),
            "plannedAt": _iso(get("planned_at")),
            "doneAt": _iso(get("done_at")),
            "effectiveness": get("effectiveness"),
        },
        "after": _side(get, "after", "product_kpov_after", "big_y_item_after"),
        "verdict": get("verdict"),
    }
