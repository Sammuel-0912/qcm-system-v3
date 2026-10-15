"""站別 × Level 柱狀圖：KPOV 原始 Level 分佈、期間內客訴與維修筆數。

站別以設備代碼區分（同名站可能是不同設備，例：兩個「鎖PWB」），
順序依 KPOV 數據庫的列序（即製程順序）。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FactComplaint, FactKpov, FactRepair
from .lifecycle import KpovState
from .measure_rows import events_by_repair
from .query import in_bounds, window_bounds


def _empty() -> dict[str, int]:
    return {str(level): 0 for level in range(4)}


def station_order(session: Session, batch_id: int) -> list[tuple[str, str]]:
    """（設備代碼, 站別名稱），依 KPOV 數據庫第一次出現的順序。"""
    seen: dict[str, str] = {}
    for code, station in session.execute(
        select(FactKpov.equipment_code, FactKpov.station)
        .where(FactKpov.batch_id == batch_id)
        .order_by(FactKpov.id)
    ):
        if code and code not in seen:
            seen[code] = station
    return list(seen.items())


def kpov_levels(session: Session, batch_id: int) -> dict:
    """各站 KPOV 個數，依 KPOV 數據庫的原始 Level（不套用維修／改善，不分期間）。"""
    stations = {code: {"equipmentCode": code, "station": name, "counts": _empty()}
                for code, name in station_order(session, batch_id)}
    unrated = 0
    for code, level in session.execute(
        select(FactKpov.equipment_code, FactKpov.level_baseline).where(FactKpov.batch_id == batch_id)
    ):
        if code not in stations:
            continue
        if level is None:
            unrated += 1
        else:
            stations[code]["counts"][str(level)] += 1
    return {"stations": list(stations.values()), "unrated": unrated}


def event_levels(session: Session, batch_id: int, window: str, scoped: list[KpovState]) -> dict:
    """期間內各站的客訴與維修筆數，依「發生當時」的 Level 分色。

    客訴依客訴日期、取改善前 Level；維修依測試時間、取該筆惡化事件後的 Level。
    只計入篩選範圍（線別／屬性／站別）內的設備；客訴未填設備ID 者另計 unmappedComplaints，
    算不出 Level 者另計 unknownLevel。
    """
    bounds = window_bounds(window)
    allowed = {s.kpov.equipment_code for s in scoped if s.kpov.equipment_code}
    stations = {
        code: {"equipmentCode": code, "station": name, "complaints": _empty(), "repairs": _empty()}
        for code, name in station_order(session, batch_id)
        if code in allowed
    }
    unmapped = 0
    unknown = {"complaints": 0, "repairs": 0}

    def record(code: str | None, kind: str, level: int | None) -> None:
        if code not in stations:
            return
        if level is None:
            unknown[kind] += 1
        else:
            stations[code][kind][str(level)] += 1

    for code, at, level in session.execute(
        select(FactComplaint.equipment_code, FactComplaint.complained_at, FactComplaint.level_before).where(
            FactComplaint.batch_id == batch_id
        )
    ):
        if not in_bounds(at, bounds):
            continue
        if code:
            record(code, "complaints", level)
        else:
            unmapped += 1

    events = events_by_repair(session, batch_id)
    for repair in session.scalars(select(FactRepair).where(FactRepair.batch_id == batch_id)):
        if in_bounds(repair.tested_at, bounds):
            degrade = events.get(repair.id, {}).get("DEGRADE")
            record(repair.equipment_code, "repairs", degrade.level_after if degrade else None)

    return {
        "window": window,
        "stations": list(stations.values()),
        "unmappedComplaints": unmapped,
        "unknownLevel": unknown,
    }
