"""API 端點 — spec.md §7。"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db import get_session
from ...importer.excel import ImportError_, import_workbook
from ...models import DimEquipment, FactLevelEvent, ImportBatch
from ...services.level import LEVEL_COLORS, LEVEL_DESCRIPTIONS
from ...services.lifecycle import VIEWS, build_states
from ...services.query import (
    active_batch,
    apply_filters,
    bar_payload,
    quadrant_payload,
    trend_payload,
)

router = APIRouter(prefix="/api/v1")


def _batch_or_404(session: Session) -> ImportBatch:
    batch = active_batch(session)
    if batch is None:
        raise HTTPException(status_code=404, detail="尚無資料，請先匯入 Excel")
    return batch


def _check_view(view: str) -> str:
    if view not in VIEWS:
        raise HTTPException(status_code=400, detail=f"view 必須是 {', '.join(VIEWS)} 其中之一")
    return view


def _batch_info(batch: ImportBatch) -> dict:
    return {
        "id": batch.id,
        "filename": batch.filename,
        "importedAt": batch.imported_at.isoformat() if batch.imported_at else None,
    }


@router.get("/filters")
def get_filters(session: Session = Depends(get_session)):
    batch = _batch_or_404(session)
    states = build_states(session, batch.id)

    # 站別不再唯一（「鎖銅排」同時是 CTP 站與 OP 站），因此以 屬性1+站別 為鍵
    stations: dict[tuple[str, str], dict] = {}
    for state in states:
        attribute = state.kpov.attribute1 or "UNKNOWN"
        entry = stations.setdefault(
            (attribute, state.kpov.station),
            {
                "attribute": attribute,
                "code": state.kpov.station,
                "equipmentCode": state.kpov.equipment_code,
                "targetId": state.target_id,
                "kpovCount": 0,
                "worstLevel": None,
                "levelCounts": {str(i): 0 for i in range(4)},
            },
        )
        entry["kpovCount"] += 1
        level = state.level_current
        if level is not None:
            entry["levelCounts"][str(level)] += 1
            # 最嚴重等級（依 §2.6 排序 0<1<2<3），供 layout 熱區上色
            if entry["worstLevel"] is None or level > entry["worstLevel"]:
                entry["worstLevel"] = level

    lines = sorted(
        {
            row.line
            for row in session.scalars(select(DimEquipment).where(DimEquipment.batch_id == batch.id))
            if row.line
        }
    )
    return {
        "stations": sorted(stations.values(), key=lambda s: (s["attribute"], s["code"])),
        "attributes": sorted({s.kpov.attribute1 or "UNKNOWN" for s in states}),
        "lines": [{"code": line, "label": line} for line in lines],
        "batch": _batch_info(batch),
        "levelMeta": [
            {"level": level, "color": LEVEL_COLORS[level], **LEVEL_DESCRIPTIONS[level]} for level in range(4)
        ],
    }


@router.get("/quadrant")
def get_quadrant(
    view: str = Query("current"),
    station: str | None = None,
    line: str | None = None,
    attribute: str | None = None,
    target: str | None = None,
    session: Session = Depends(get_session),
):
    _check_view(view)
    batch = _batch_or_404(session)
    states = build_states(session, batch.id)
    payload = quadrant_payload(session, batch.id, states, station, line, view, attribute, target)
    payload["batch"] = _batch_info(batch)
    return payload


@router.get("/levels/bar")
def get_bar(
    view: str = Query("current"),
    station: str | None = None,
    line: str | None = None,
    attribute: str | None = None,
    target: str | None = None,
    session: Session = Depends(get_session),
):
    _check_view(view)
    batch = _batch_or_404(session)
    states = build_states(session, batch.id)
    return bar_payload(session, batch.id, states, station, line, view, attribute, target)


@router.get("/trend")
def get_trend(
    station: str | None = None,
    line: str | None = None,
    attribute: str | None = None,
    target: str | None = None,
    granularity: str = Query("month", pattern="^(month|week)$"),
    session: Session = Depends(get_session),
):
    batch = _batch_or_404(session)
    states = build_states(session, batch.id)
    return trend_payload(session, batch.id, states, station, line, attribute, target, granularity)


@router.get("/kpov")
def list_kpov(
    view: str = Query("current"),
    station: str | None = None,
    line: str | None = None,
    attribute: str | None = None,
    target: str | None = None,
    level: int | None = None,
    deviated_only: bool = Query(False, alias="deviatedOnly"),
    page: int = 1,
    page_size: int = Query(100, alias="pageSize", le=500),
    session: Session = Depends(get_session),
):
    _check_view(view)
    batch = _batch_or_404(session)
    states = build_states(session, batch.id)
    scoped, _ = apply_filters(session, batch.id, states, station, line, attribute, target)

    if level is not None:
        scoped = [s for s in scoped if s.level_for(view) == level]
    if deviated_only:
        scoped = [s for s in scoped if s.deviates_from_baseline]

    scoped.sort(key=lambda s: (s.kpov.station, s.kpov.kpov_no or "", s.kpov.equipment_code))
    total = len(scoped)
    start = (page - 1) * page_size
    window = scoped[start : start + page_size]

    return {
        "total": total,
        "page": page,
        "pageSize": page_size,
        "items": [
            {
                "kpovNo": s.kpov.kpov_no,
                "kpovName": s.kpov.kpov_name,
                "station": s.kpov.station,
                "attribute": s.kpov.attribute1,
                "targetId": s.target_id,
                "category": s.kpov.category,
                "equipmentCode": s.kpov.equipment_code,
                "smallYBaseline": s.kpov.small_y_score,
                "bigYBaseline": s.kpov.big_y_score,
                "smallYCurrent": s.small_y_current,
                "bigYCurrent": s.big_y_current,
                "levelBaseline": s.level_baseline,
                "levelCurrent": s.level_current,
                "levelTarget": s.level_target,
                "deviates": s.deviates_from_baseline,
                "escalatedOpen": s.is_escalated_open,
                "lastEventAt": s.last_event.effective_at.isoformat() if s.last_event else None,
                "transition": s.last_event.transition if s.last_event else None,
                "eventCount": len(s.events),
            }
            for s in window
        ],
    }


@router.get("/kpov/{kpov_no}/{equipment_code}/history")
def kpov_history(kpov_no: str, equipment_code: str, session: Session = Depends(get_session)):
    batch = _batch_or_404(session)
    states = build_states(session, batch.id)
    match = next(
        (s for s in states if s.kpov.kpov_no == kpov_no and s.kpov.equipment_code == equipment_code), None
    )
    if match is None:
        raise HTTPException(status_code=404, detail="找不到該 KPOV × 設備組合")

    return {
        "kpovNo": match.kpov.kpov_no,
        "kpovName": match.kpov.kpov_name,
        "equipmentCode": match.kpov.equipment_code,
        "station": match.kpov.station,
        "baseline": {
            "smallY": {"method": None, "score": match.kpov.small_y_score},
            "bigY": {"method": None, "score": match.kpov.big_y_score},
            "level": match.level_baseline,
        },
        "events": [
            {
                "type": e.event_type,
                "effectiveAt": e.effective_at.isoformat(),
                "transition": e.transition,
                "levelBefore": e.level_before,
                "levelAfter": e.level_after,
                "smallY": {"method": e.small_y_method_after, "score": e.small_y_score_after},
                "bigY": {"method": e.big_y_method_after, "score": e.big_y_score_after},
                "smallYBefore": {"method": e.small_y_method_before, "score": e.small_y_score_before},
                "bigYBefore": {"method": e.big_y_method_before, "score": e.big_y_score_before},
                "defectDesc": e.defect_desc,
                "improvement": e.improvement,
                "repairSerial": e.repair_serial,
            }
            for e in match.events
        ],
        "current": {"level": match.level_current},
        "target": {"level": match.level_target},
    }


@router.get("/events")
def list_events(
    station: str | None = None,
    line: str | None = None,
    attribute: str | None = None,
    target: str | None = None,
    transition: str | None = None,
    limit: int = Query(50, le=500),
    session: Session = Depends(get_session),
):
    batch = _batch_or_404(session)
    states = build_states(session, batch.id)
    scoped, _ = apply_filters(session, batch.id, states, station, line, attribute, target)
    allowed = {(s.kpov.kpov_no, s.kpov.equipment_code) for s in scoped}
    names = {(s.kpov.kpov_no, s.kpov.equipment_code): s.kpov for s in states}

    events = session.scalars(
        select(FactLevelEvent)
        .where(FactLevelEvent.batch_id == batch.id)
        .order_by(FactLevelEvent.effective_at.desc(), FactLevelEvent.id.desc())
    ).all()

    items = []
    for e in events:
        key = (e.kpov_no, e.equipment_code)
        if key not in allowed:
            continue
        if transition and e.transition != transition:
            continue
        kpov = names.get(key)
        items.append(
            {
                "kpovNo": e.kpov_no,
                "kpovName": kpov.kpov_name if kpov else None,
                "station": kpov.station if kpov else None,
                "equipmentCode": e.equipment_code,
                "eventType": e.event_type,
                "effectiveAt": e.effective_at.isoformat(),
                "levelBefore": e.level_before,
                "levelAfter": e.level_after,
                "transition": e.transition,
                "defectDesc": e.defect_desc,
                "improvement": e.improvement,
                "repairSerial": e.repair_serial,
            }
        )
        if len(items) >= limit:
            break

    escalated_open = sum(1 for s in scoped if s.is_escalated_open)
    improved = sum(1 for s in scoped if s.is_improved)
    return {
        "summary": {"escalatedOpen": escalated_open, "improved": improved, "totalEvents": len(items)},
        "items": items,
    }


@router.post("/import")
async def do_import(file: UploadFile = File(...), session: Session = Depends(get_session)):
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="請上傳 .xlsx 檔案")

    tmp = Path(tempfile.mkdtemp()) / file.filename
    with tmp.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    try:
        batch, report = import_workbook(session, str(tmp), file.filename)
    except ImportError_ as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)

    return {"batchId": batch.id, "batch": _batch_info(batch), "report": report.as_dict()}


@router.get("/import/history")
def import_history(session: Session = Depends(get_session)):
    batches = session.scalars(select(ImportBatch).order_by(ImportBatch.id.desc())).all()
    return [
        {**_batch_info(b), "status": b.status, "isActive": b.is_active, "rowCounts": b.row_counts}
        for b in batches
    ]
