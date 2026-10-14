"""客訴問題追蹤與製程問題追蹤（首頁左半邊）。

兩張表與等級異動總覽同一套欄位（見 services/measure_rows.py）。
- 客訴：依（設備ID, KPOV 編號）合併，來源未填 KPOV 者依（製程單元, 產品KPOV）另列並標示未對應；
  客訴筆數為該組實際筆數。
- 製程：修護報表每筆維修一列（新欄位沒有筆數欄，合併會失去資訊）；客訴筆數先固定 0。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FactComplaint, FactRepair
from .lifecycle import KpovState
from .measure_rows import complaint_row, events_by_repair, measures_for, repair_row, utc


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
    """回傳（各 Level 客訴筆數, 追蹤列）。Level 筆數依改善後等級（目前狀態）統計。

    scoped 為 None 表示未篩選（含未對應 KPOV 的客訴）。
    """
    by_key = {(s.kpov.kpov_no, s.kpov.equipment_code): s for s in states}
    allowed = None if scoped is None else {(s.kpov.kpov_no, s.kpov.equipment_code) for s in scoped}

    complaints = session.scalars(
        select(FactComplaint).where(FactComplaint.batch_id == batch_id).order_by(FactComplaint.seq)
    ).all()
    if allowed is not None:
        complaints = [c for c in complaints if (c.kpov_no, c.equipment_code) in allowed]

    counts = {**_empty_level_counts(), "total": len(complaints)}
    groups: dict[tuple, list[FactComplaint]] = {}
    for c in complaints:
        if c.level_after is not None:
            counts[str(c.level_after)] += 1
        mapped = bool(c.kpov_no and c.equipment_code)
        key = ("kpov", c.equipment_code, c.kpov_no) if mapped else ("unmapped", c.process_unit, c.product_kpov)
        groups.setdefault(key, []).append(c)

    now = dt.datetime.now(dt.timezone.utc)
    epoch = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    rows = []
    for key, items in groups.items():
        items.sort(key=lambda c: (utc(c.complained_at) or epoch, c.seq or 0))
        mapped = key[0] == "kpov"
        state = by_key.get((items[-1].kpov_no, items[-1].equipment_code)) if mapped else None
        rows.append(complaint_row(items, state, mapped, now))
    rows.sort(key=lambda r: r["occurredAt"] or "", reverse=True)
    return counts, rows


def process_summary(
    session: Session,
    batch_id: int,
    scoped: list[KpovState],
) -> tuple[dict, list[dict]]:
    """修護報表每筆維修一列（只列對得到範圍內 KPOV 者），依測試時間新到舊。
    Level 筆數依該 KPOV 現況 Level 統計維修筆數。"""
    by_key = {(s.kpov.kpov_no, s.kpov.equipment_code): s for s in scoped}
    repairs = [
        r
        for r in session.scalars(select(FactRepair).where(FactRepair.batch_id == batch_id))
        if (r.kpov_no, r.equipment_code) in by_key
    ]
    epoch = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    repairs.sort(key=lambda r: utc(r.tested_at) or epoch, reverse=True)

    counts = {"current": _empty_level_counts(), "total": len(repairs)}
    events = events_by_repair(session, batch_id)
    measures = measures_for(session, repairs)
    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    for r in repairs:
        state = by_key[(r.kpov_no, r.equipment_code)]
        if state.level_current is not None:
            counts["current"][str(state.level_current)] += 1
        rows.append(
            repair_row(
                r,
                state,
                events.get(r.id, {}),
                measures.get((r.serial_no, r.kpov_no, r.equipment_code)),
                editable=False,
                now=now,
            )
        )
    return counts, rows
