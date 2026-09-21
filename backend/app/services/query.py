"""篩選與彙總查詢 — spec.md §7 / §11.1（D-01 線別繼承）。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DimEquipment, ImportBatch
from .level import LEVEL_COLORS
from .lifecycle import KpovState, build_states, summarize


def active_batch(session: Session) -> ImportBatch | None:
    return session.scalars(
        select(ImportBatch).where(ImportBatch.is_active.is_(True)).order_by(ImportBatch.id.desc())
    ).first()


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def equipment_index(session: Session, batch_id: int) -> dict[str, DimEquipment]:
    rows = session.scalars(select(DimEquipment).where(DimEquipment.batch_id == batch_id)).all()
    return {row.equipment_code: row for row in rows}


def apply_filters(
    session: Session,
    batch_id: int,
    states: list[KpovState],
    station: str | None,
    line: str | None,
) -> tuple[list[KpovState], dict]:
    """套用站別／線別篩選。

    D-01（REQ-LINE-01~03）：KPOV 的歸屬維度是「站別」，不是「線別」。
    線別篩選時先取該線別的設備 -> 反查其站別 -> 顯示這些站別的 KPOV。
    若該線別本身沒有 KPOV 定義（例如 DCS-PM2 的孿生設備），視為繼承同站別的定義。
    """
    stations = _split(station)
    lines = _split(line)
    meta: dict = {"inherited": False, "inheritedFrom": None, "inheritedStations": []}

    selected = states
    if stations:
        selected = [s for s in selected if s.kpov.station in set(stations)]

    if lines:
        equipment = equipment_index(session, batch_id)
        line_set = set(lines)

        # 該線別上的設備
        codes_on_line = {code for code, eq in equipment.items() if eq.line in line_set}
        # 這些設備所屬的站別（透過 KPOV 庫反查）
        stations_on_line = {s.kpov.station for s in states if s.kpov.equipment_code in codes_on_line}

        direct = [s for s in selected if s.kpov.equipment_code in codes_on_line]
        if direct:
            selected = direct
        else:
            # 線別無自有 KPOV -> 繼承同站別定義
            equip_descs = {equipment[c].equipment_desc for c in codes_on_line if c in equipment}
            inherited_stations = sorted(
                {
                    s.kpov.station
                    for s in states
                    if s.kpov.equipment_code in equipment
                    and equipment[s.kpov.equipment_code].equipment_desc in equip_descs
                }
            )
            if inherited_stations:
                source_lines = sorted(
                    {
                        equipment[s.kpov.equipment_code].line
                        for s in states
                        if s.kpov.station in set(inherited_stations)
                        and s.kpov.equipment_code in equipment
                        and equipment[s.kpov.equipment_code].line not in line_set
                    }
                )
                selected = [s for s in selected if s.kpov.station in set(inherited_stations)]
                meta = {
                    "inherited": True,
                    "inheritedFrom": source_lines[0] if source_lines else None,
                    "inheritedStations": inherited_stations,
                }
            else:
                selected = []
        if not meta["inherited"] and stations_on_line:
            meta["inheritedStations"] = sorted(stations_on_line)

    return selected, meta


def quadrant_payload(
    session: Session,
    batch_id: int,
    all_states: list[KpovState],
    station: str | None,
    line: str | None,
    view: str,
) -> dict:
    scoped, meta = apply_filters(session, batch_id, all_states, station, line)
    filtered = bool(_split(station) or _split(line))
    deviation = sum(1 for s in scoped if s.deviates_from_baseline)
    return {
        "view": view,
        "scope": summarize(scoped, view),
        "plant": summarize(all_states, view),
        "baseline": summarize(scoped, "baseline"),
        "filtered": filtered,
        "deviationCount": deviation,
        "lineInheritance": meta,
    }


def bar_payload(
    session: Session,
    batch_id: int,
    all_states: list[KpovState],
    station: str | None,
    line: str | None,
    view: str,
) -> dict:
    scoped, _ = apply_filters(session, batch_id, all_states, station, line)
    current = summarize(scoped, view)
    baseline = summarize(scoped, "baseline")
    return {
        "bars": [
            {
                "level": level,
                "count": current[f"level{level}"],
                "baselineCount": baseline[f"level{level}"],
                "color": LEVEL_COLORS[level],
            }
            for level in range(4)
        ],
        "unrated": current["unrated"],
    }
