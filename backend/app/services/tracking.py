"""客訴問題追蹤與製程問題追蹤（首頁左半邊）。

兩張表格式相同：站別、KPOV、筆數、改善措施、Level 變化、切入時間、追蹤狀況。
- 客訴：來源為客訴報表；依（設備ID, KPOV 編號）合併，來源未填 KPOV 者依（製程單元, 產品KPOV）
  另列並標示未對應。Level 變化為該組最新一筆客訴的「改善前 → 改善後」。
- 製程：來源為修護報表；依（設備ID, KPOV 編號）合併。Level 變化為 KPOV「基準 → 現況」。
追蹤狀況目前一律 0（使用者指定，之後再定義）。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FactComplaint, FactRepair
from .lifecycle import KpovState

TRACKING_PLACEHOLDER = 0


def _utc(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value


def _iso(value: dt.datetime | None) -> str | None:
    value = _utc(value)
    return value.isoformat() if value else None


def paginate(rows: list[dict], page: int, page_size: int) -> dict:
    total = len(rows)
    pages = max(1, -(-total // page_size))
    page = min(max(page, 1), pages)
    return {
        "page": page,
        "pageSize": page_size,
        "total": total,
        "pages": pages,
        "items": rows[(page - 1) * page_size : page * page_size],
    }


def _empty_level_counts() -> dict[str, int]:
    return {str(level): 0 for level in range(4)}


def complaint_summary(
    session: Session,
    batch_id: int,
    states: list[KpovState],
    scoped: list[KpovState] | None,
) -> tuple[dict, list[dict]]:
    """回傳（Level 筆數, 追蹤列）。scoped 為 None 表示未篩選（含未對應 KPOV 的客訴）。"""
    by_key = {(s.kpov.kpov_no, s.kpov.equipment_code): s for s in states}
    allowed = None if scoped is None else {(s.kpov.kpov_no, s.kpov.equipment_code) for s in scoped}

    complaints = session.scalars(
        select(FactComplaint).where(FactComplaint.batch_id == batch_id).order_by(FactComplaint.seq)
    ).all()
    if allowed is not None:
        complaints = [c for c in complaints if (c.kpov_no, c.equipment_code) in allowed]

    counts = {"before": _empty_level_counts(), "after": _empty_level_counts(), "total": len(complaints)}
    groups: dict[tuple, list[FactComplaint]] = {}
    for c in complaints:
        if c.level_before is not None:
            counts["before"][str(c.level_before)] += 1
        if c.level_after is not None:
            counts["after"][str(c.level_after)] += 1
        mapped = bool(c.kpov_no and c.equipment_code)
        key = ("kpov", c.equipment_code, c.kpov_no) if mapped else ("unmapped", c.process_unit, c.product_kpov)
        groups.setdefault(key, []).append(c)

    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    for key, items in groups.items():
        items.sort(key=lambda c: (_utc(c.complained_at) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), c.seq or 0))
        latest = items[-1]
        state = by_key.get((latest.kpov_no, latest.equipment_code)) if key[0] == "kpov" else None
        cutover = _utc(latest.done_at) or _utc(latest.planned_at)
        rows.append(
            {
                "station": state.kpov.station if state else latest.process_unit,
                "kpovNo": latest.kpov_no if key[0] == "kpov" else None,
                "kpovName": state.kpov.kpov_name if state else latest.product_kpov,
                "equipmentCode": latest.equipment_code if key[0] == "kpov" else None,
                "mapped": key[0] == "kpov" and state is not None,
                "count": len(items),
                "improvement": latest.countermeasure,
                "levelBefore": latest.level_before,
                "levelAfter": latest.level_after,
                "cutoverAt": _iso(cutover),
                # 實際完成時間未填（或多項對策尚有未完成）時以預計完成時間呈現
                "cutoverPlanned": latest.done_at is None and cutover is not None,
                "cutoverOverdue": latest.done_at is None and cutover is not None and cutover < now,
                "tracking": TRACKING_PLACEHOLDER,
                "lastAt": _iso(latest.complained_at),
            }
        )
    rows.sort(key=lambda r: r["lastAt"] or "", reverse=True)
    return counts, rows


def process_summary(
    session: Session,
    batch_id: int,
    scoped: list[KpovState],
) -> tuple[dict, list[dict]]:
    """修護報表依（設備ID, KPOV）合併。Level 筆數依該 KPOV 現況 Level 統計維修筆數。"""
    by_key = {(s.kpov.kpov_no, s.kpov.equipment_code): s for s in scoped}
    repairs = session.scalars(select(FactRepair).where(FactRepair.batch_id == batch_id)).all()

    groups: dict[tuple, list[FactRepair]] = {}
    for r in repairs:
        key = (r.kpov_no, r.equipment_code)
        if key in by_key:
            groups.setdefault(key, []).append(r)

    counts = {"current": _empty_level_counts(), "total": 0}
    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    for key, items in groups.items():
        state = by_key[key]
        items.sort(key=lambda r: _utc(r.tested_at) or dt.datetime.min.replace(tzinfo=dt.timezone.utc))
        latest = items[-1]
        improve_at = _utc(latest.improvement_effective_at)
        if state.level_current is not None:
            counts["current"][str(state.level_current)] += len(items)
        counts["total"] += len(items)
        rows.append(
            {
                "station": state.kpov.station,
                "kpovNo": state.kpov.kpov_no,
                "kpovName": state.kpov.kpov_name,
                "equipmentCode": state.kpov.equipment_code,
                "mapped": True,
                "count": len(items),
                "improvement": latest.improvement,
                "levelBefore": state.level_baseline,
                "levelAfter": state.level_current,
                "cutoverAt": _iso(improve_at),
                "cutoverPlanned": bool(improve_at and improve_at > now),
                "cutoverOverdue": False,
                "tracking": TRACKING_PLACEHOLDER,
                "lastAt": _iso(latest.tested_at),
            }
        )
    rows.sort(key=lambda r: r["lastAt"] or "", reverse=True)
    return counts, rows
