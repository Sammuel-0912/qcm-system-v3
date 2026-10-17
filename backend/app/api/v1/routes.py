"""API 端點 — spec.md §7。"""
from __future__ import annotations

import datetime as dt
import io
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import AR_UPLOAD_DIR, AR_UPLOAD_URL_PREFIX, SITE_UTC_OFFSET_HOURS
from ...db import get_session
from ...importer.excel import ImportError_, import_workbook
from ...models import (
    CheckPhotoInspection,
    DimEquipment,
    EmergencyMeasure,
    FactChangeRecord,
    FactCheckItem,
    FactComplaint,
    FactLevelEvent,
    FactRepair,
    ImportBatch,
)
from ...services.measure_rows import events_by_repair, measure_out, measures_for, repair_row
from ...services.station_levels import event_levels, kpov_levels, station_order
from ...services.tracking import complaint_summary, paginate, process_summary
from ...services.check_monitor import check_items, monitor_rows, shift_payload, summarize_rows, utc
from ...services import presence
from ...services.level import LEVEL_COLORS, LEVEL_DESCRIPTIONS
from ...services.lifecycle import VIEWS, build_states
from ...services.query import (
    CHANGE_WINDOWS,
    active_batch,
    apply_filters,
    quadrant_payload,
    trend_payload,
    window_bounds,
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
        "stations": sorted(stations.values(), key=lambda s: (s["attribute"] or "", s["code"] or "")),
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
    window: str | None = Query(None, pattern="^(day|week|month|year)$"),
    session: Session = Depends(get_session),
):
    """象限圖。母體一律為全部 KPOV；給 window 時另回 start＝期間第一天當時的 Level 分佈（期初 → 現在）。"""
    _check_view(view)
    batch = _batch_or_404(session)
    states = build_states(session, batch.id)
    bounds = window_bounds(window)
    start_states = build_states(session, batch.id, as_of=bounds[0]) if bounds else None
    payload = quadrant_payload(
        session, batch.id, states, station, line, view, attribute, target, start_states=start_states
    )
    payload["batch"] = _batch_info(batch)
    return payload


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
    window: str | None = Query(None, pattern="^(day|week|month|year)$"),
    session: Session = Depends(get_session),
):
    _check_view(view)
    batch = _batch_or_404(session)
    # 與象限圖同一個母體（全部 KPOV）；window 已不影響明細，保留參數只為相容舊連結
    states = build_states(session, batch.id)
    scoped, _ = apply_filters(session, batch.id, states, station, line, attribute, target)

    if level is not None:
        scoped = [s for s in scoped if s.level_for(view) == level]
    if deviated_only:
        scoped = [s for s in scoped if s.deviates_from_baseline]

    # 三個欄位都要防 None：OP 站的 equipment_code 為空，部分列的 station 也可能缺，
    # 混入 None 會讓 sort 在比對時丟 TypeError。
    scoped.sort(key=lambda s: (s.kpov.station or "", s.kpov.kpov_no or "", s.kpov.equipment_code or ""))
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

    # 惡化節點的 tooltip 需要維修紀錄的敘述欄位。fact_level_event 只存了
    # 「不良描述」（來源三筆全是 NO ERROR CODE，沒有資訊量），因此這裡以
    # repair_id 回查 fact_repair，不另外複製欄位進帳本。
    repair_ids = {e.repair_id for e in match.events if e.repair_id}
    repairs: dict[int, FactRepair] = {}
    if repair_ids:
        repairs = {
            r.id: r
            for r in session.scalars(select(FactRepair).where(FactRepair.id.in_(repair_ids)))
        }

    def repair_detail(event: FactLevelEvent) -> dict | None:
        repair = repairs.get(event.repair_id) if event.repair_id else None
        if repair is None:
            return None
        return {
            "serialNo": repair.serial_no,
            "productDefectDesc": repair.product_defect_desc,
            "subCategory": repair.sub_category,
            "defectCause": repair.defect_cause,
            "countermeasure": repair.countermeasure,
            "remark": repair.remark,
            "technician": repair.technician,
            "improvement": repair.improvement,
        }

    return {
        "kpovNo": match.kpov.kpov_no,
        "kpovName": match.kpov.kpov_name,
        "equipmentCode": match.kpov.equipment_code,
        "station": match.kpov.station,
        "attribute": match.kpov.attribute1,
        "targetId": match.target_id,
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
                "repair": repair_detail(e),
            }
            for e in match.events
        ],
        "changes": _change_records(session, batch.id, match.kpov),
        "current": {"level": match.level_current},
        "target": {"level": match.level_target},
    }


def _change_records(session: Session, batch_id: int, kpov) -> list[dict]:
    """該 KPOV 的 PCN / ECN 變更紀錄，只供時間軸顯示，不影響等級計算。

    PCN 以 (KPOV 編號, 設備ID) 對應，沒有設備ID 時以 (KPOV 編號, 站別)；ECN 若影響站別與設備ID 皆為 NA 視為全廠，
    否則依設備ID 或站別對應。
    """
    records = session.scalars(
        select(FactChangeRecord)
        .where(FactChangeRecord.batch_id == batch_id)
        .order_by(FactChangeRecord.effective_at, FactChangeRecord.id)
    ).all()
    out = []
    for r in records:
        if r.kind == "PCN":
            if r.kpov_no != kpov.kpov_no:
                continue
            # 有設備ID 以設備比對；OP 站的 PCN 若匯入時未補上設備ID（舊批次），退回以站別比對
            if r.equipment_code:
                if r.equipment_code != kpov.equipment_code:
                    continue
            elif not r.station or r.station != kpov.station:
                continue
        else:
            plant_wide = not r.equipment_code and not r.station
            hits = (r.equipment_code and r.equipment_code == kpov.equipment_code) or (
                r.station and r.station == kpov.station
            )
            if not plant_wide and not hits:
                continue
            if r.kpov_no and r.kpov_no != kpov.kpov_no:
                continue
        out.append(
            {
                "kind": r.kind,
                "effectiveAt": r.effective_at.isoformat() if r.effective_at else None,
                "ecnNo": r.ecn_no,
                "content": r.content,
                "station": r.station,
                "plantWide": r.kind == "ECN" and not r.equipment_code and not r.station,
                "smallYBefore": r.small_y_before,
                "bigYBefore": r.big_y_before,
                "levelBefore": r.level_before,
                "smallYAfter": r.small_y_after,
                "bigYAfter": r.big_y_after,
                "levelAfter": r.level_after,
            }
        )
    return out


@router.get("/check-monitor")
def get_check_monitor(
    station: str | None = None,
    line: str | None = None,
    attribute: str | None = None,
    target: str | None = None,
    session: Session = Depends(get_session),
):
    """Level 3 高風險項點檢監控：點檢項目 × AR 逐項點檢最新結果。"""
    batch = _batch_or_404(session)
    codes: set[str] | None = None
    if station or line or attribute or target:
        states = build_states(session, batch.id)
        scoped, _ = apply_filters(session, batch.id, states, station, line, attribute, target)
        codes = {s.kpov.equipment_code for s in scoped if s.kpov.equipment_code}
    rows = monitor_rows(session, check_items(session, batch.id, codes))
    rows.sort(key=lambda r: (r["station"] or "", r["kpovNo"] or "", r["checkContent"] or ""))
    return {"items": rows, "summary": summarize_rows(rows), "shift": shift_payload()}


@router.get("/events")
def list_events(
    station: str | None = None,
    line: str | None = None,
    attribute: str | None = None,
    target: str | None = None,
    transition: str | None = None,
    level_after: int | None = Query(None, alias="levelAfter", ge=0, le=3),
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

    now = dt.datetime.now(dt.timezone.utc)
    items = []
    # 各「變化後 Level」的筆數：供總覽的 Level 篩選顯示，不受 levelAfter 與 limit 影響
    level_counts = {str(level): 0 for level in range(4)}
    for e in events:
        key = (e.kpov_no, e.equipment_code)
        if key not in allowed:
            continue
        if transition and e.transition != transition:
            continue
        if e.level_after is not None and str(e.level_after) in level_counts:
            level_counts[str(e.level_after)] += 1
        if level_after is not None and e.level_after != level_after:
            continue
        if len(items) >= limit:
            continue
        effective = e.effective_at if e.effective_at.tzinfo else e.effective_at.replace(tzinfo=dt.timezone.utc)
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
                # 改善時間在未來：預計改善，尚未生效
                "planned": effective > now,
            }
        )

    escalated_open = sum(1 for s in scoped if s.is_escalated_open)
    improved = sum(1 for s in scoped if s.is_improved)
    return {
        "summary": {"escalatedOpen": escalated_open, "improved": improved, "totalEvents": len(items)},
        "levelCounts": level_counts,
        "items": items,
    }


CHANGE_KINDS_UI = {"escalated": "ESCALATED", "improved": "IMPROVED"}


@router.get("/level-changes")
def list_level_changes(
    station: str | None = None,
    line: str | None = None,
    attribute: str | None = None,
    target: str | None = None,
    window: str = Query("month", pattern="^(day|week|month|year)$"),
    kind: str = Query("escalated", pattern="^(escalated|improved)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=50),
    session: Session = Depends(get_session),
):
    """等級異動總覽：近 1／7／30／365 天內發生的惡化或改善，後端分頁。

    惡化以不良發生（測試）時間落在區間內為準；改善以改善時間落在區間內為準。
    尚未到的預計改善不算「已改善」。兩個卡片的數字（escalated / improved）同樣依區間計算。
    """
    batch = _batch_or_404(session)
    states = build_states(session, batch.id)
    scoped, _ = apply_filters(session, batch.id, states, station, line, attribute, target)
    allowed = {(s.kpov.kpov_no, s.kpov.equipment_code): s.kpov for s in scoped}
    states_by_key = {(s.kpov.kpov_no, s.kpov.equipment_code): s for s in scoped}

    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=CHANGE_WINDOWS[window])

    def utc(value: dt.datetime) -> dt.datetime:
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)

    events = session.scalars(
        select(FactLevelEvent)
        .where(
            FactLevelEvent.batch_id == batch.id,
            FactLevelEvent.transition.in_(tuple(CHANGE_KINDS_UI.values())),
        )
        .order_by(FactLevelEvent.effective_at.desc(), FactLevelEvent.id.desc())
    ).all()
    in_window = [
        e
        for e in events
        if (e.kpov_no, e.equipment_code) in allowed and since <= utc(e.effective_at) <= now
    ]
    counts = {
        key: sum(1 for e in in_window if e.transition == transition) for key, transition in CHANGE_KINDS_UI.items()
    }
    selected = [e for e in in_window if e.transition == CHANGE_KINDS_UI[kind]]

    total = len(selected)
    pages = max(1, -(-total // page_size))
    page = min(page, pages)
    page_items = selected[(page - 1) * page_size : page * page_size]

    # 列內容以「該筆異動所屬的維修」組成，與客訴／製程追蹤同一套欄位（services/measure_rows.py）
    repair_ids = {e.repair_id for e in page_items if e.repair_id}
    repairs = (
        {r.id: r for r in session.scalars(select(FactRepair).where(FactRepair.id.in_(repair_ids)))}
        if repair_ids
        else {}
    )
    events = events_by_repair(session, batch.id)
    measures = measures_for(session, list(repairs.values()))

    items = []
    for e in page_items:
        repair = repairs.get(e.repair_id) if e.repair_id else None
        if repair is None:
            continue  # 事件一律來自維修紀錄；找不到代表資料不一致，略過而不是組出半套的列
        row = repair_row(
            repair,
            states_by_key.get((e.kpov_no, e.equipment_code)),
            events.get(repair.id, {}),
            measures.get((repair.serial_no, repair.kpov_no, repair.equipment_code)),
            # 只有高風險列可編輯措施層別；已改善列只顯示同一份分類
            editable=kind == "escalated",
            now=now,
        )
        row["transition"] = e.transition
        row["effectiveAt"] = utc(e.effective_at).isoformat()
        items.append(row)

    return {
        "window": window,
        "since": since.isoformat(),
        "kind": kind,
        "counts": counts,
        "page": page,
        "pageSize": page_size,
        "total": total,
        "pages": pages,
        "items": items,
    }


# --------------------------------------------------------------------------- 站別風險地圖


@router.get("/station-risk")
def get_station_risk(
    window: str = Query("month", pattern="^(day|week|month|year)$"),
    session: Session = Depends(get_session),
):
    """站別風險地圖：近 1／7／30／365 天內各設備的維修與客訴筆數，以及期間內最嚴重的 Level。

    維修依測試時間、客訴依客訴日期落在區間內計數。Level 取「發生當時」：
    維修＝該筆的惡化事件後 Level；客訴＝改善前 Level。前端依 worstLevel 上卡片底色。
    客訴未填設備ID 者無法歸到任何站，另計 unmappedComplaints。不套用上方篩選：地圖本身就是全線一覽。
    """
    batch = _batch_or_404(session)
    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=CHANGE_WINDOWS[window])

    def in_window(value: dt.datetime | None) -> bool:
        if value is None:
            return False
        value = value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
        return since <= value <= now

    stations: dict[str, dict] = {}

    def record(code: str, kind: str, level: int | None) -> None:
        entry = stations.setdefault(code, {"repairs": 0, "complaints": 0, "worstLevel": None})
        entry[kind] += 1
        if level is not None and (entry["worstLevel"] is None or level > entry["worstLevel"]):
            entry["worstLevel"] = level

    events = events_by_repair(session, batch.id)
    for repair in session.scalars(select(FactRepair).where(FactRepair.batch_id == batch.id)):
        if repair.equipment_code and in_window(repair.tested_at):
            degrade = events.get(repair.id, {}).get("DEGRADE")
            record(repair.equipment_code, "repairs", degrade.level_after if degrade else None)

    unmapped = 0
    for code, complained_at, level_before in session.execute(
        select(FactComplaint.equipment_code, FactComplaint.complained_at, FactComplaint.level_before).where(
            FactComplaint.batch_id == batch.id
        )
    ):
        if not in_window(complained_at):
            continue
        if code:
            record(code, "complaints", level_before)
        else:
            unmapped += 1

    return {"window": window, "since": since.isoformat(), "stations": stations, "unmappedComplaints": unmapped}


@router.get("/station-levels/kpov")
def get_station_kpov_levels(session: Session = Depends(get_session)):
    """站別柱狀圖（layout 下方）：各站 KPOV 個數，依 KPOV 數據庫原始 Level。全線一覽，不套用篩選與期間。"""
    batch = _batch_or_404(session)
    return kpov_levels(session, batch.id)


@router.get("/station-levels/events")
def get_station_event_levels(
    window: str = Query("month", pattern="^(day|week|month|year)$"),
    station: str | None = None,
    line: str | None = None,
    attribute: str | None = None,
    session: Session = Depends(get_session),
):
    """客訴／製程柱狀圖：期間內各站的客訴與維修筆數，依發生當時的 Level 分色；套用上方篩選。"""
    batch = _batch_or_404(session)
    scoped, _ = apply_filters(session, batch.id, build_states(session, batch.id), station, line, attribute)
    return event_levels(session, batch.id, window, scoped)


# --------------------------------------------------------------------------- 緊急措施分類


class EmergencyMeasureIn(BaseModel):
    repair_serial: str = Field(alias="repairSerial", min_length=1)
    kpov_no: str = Field(alias="kpovNo", min_length=1)
    equipment_code: str = Field(alias="equipmentCode", min_length=1)
    solution_type: str = Field(alias="solutionType", pattern="^(technical|management)$")
    tech_target: str | None = Field(None, alias="techTarget", pattern="^(KPOV|KPIV)$")
    design_elimination: bool = Field(False, alias="designElimination")
    equipment_interception: bool = Field(False, alias="equipmentInterception")
    foolproof: bool = False
    smart_monitoring: bool = Field(False, alias="smartMonitoring")
    management_note: str | None = Field(None, alias="managementNote")


@router.put("/emergency-measures")
def save_emergency_measure(data: EmergencyMeasureIn, session: Session = Depends(get_session)):
    """儲存一筆高風險異動的緊急措施分類（upsert）。

    技術解／管理解二選一；技術解再分 KPOV 或 KPIV，只保留該分類的兩個勾選項，
    切換分類時另一組一律清除，避免資料庫留下互相矛盾的組合。
    """
    batch = _batch_or_404(session)
    exists = session.scalar(
        select(FactRepair.id).where(
            FactRepair.batch_id == batch.id,
            FactRepair.serial_no == data.repair_serial,
            FactRepair.kpov_no == data.kpov_no,
            FactRepair.equipment_code == data.equipment_code,
        )
    )
    if exists is None:
        raise HTTPException(status_code=404, detail="找不到這筆維修紀錄，請重新整理後再試")

    fields = {
        "solution_type": data.solution_type,
        "tech_target": None,
        "design_elimination": False,
        "equipment_interception": False,
        "foolproof": False,
        "smart_monitoring": False,
        "management_note": None,
    }
    if data.solution_type == "technical":
        if not data.tech_target:
            raise HTTPException(status_code=422, detail="技術解需選擇 KPOV 或 KPIV")
        fields["tech_target"] = data.tech_target
        if data.tech_target == "KPOV":
            fields["design_elimination"] = data.design_elimination
            fields["equipment_interception"] = data.equipment_interception
        else:
            fields["foolproof"] = data.foolproof
            fields["smart_monitoring"] = data.smart_monitoring
    else:
        note = (data.management_note or "").strip()
        if not note:
            raise HTTPException(status_code=422, detail="管理解請填寫內容")
        fields["management_note"] = note

    measure = session.scalars(
        select(EmergencyMeasure).where(
            EmergencyMeasure.repair_serial == data.repair_serial,
            EmergencyMeasure.kpov_no == data.kpov_no,
            EmergencyMeasure.equipment_code == data.equipment_code,
        )
    ).first()
    if measure is None:
        measure = EmergencyMeasure(
            repair_serial=data.repair_serial, kpov_no=data.kpov_no, equipment_code=data.equipment_code, **fields
        )
        session.add(measure)
    else:
        for key, value in fields.items():
            setattr(measure, key, value)
        measure.updated_at = dt.datetime.now(dt.timezone.utc)
    session.commit()
    return measure_out(measure)


# --------------------------------------------------------------------------- 客訴／製程問題追蹤


def _scope(session: Session, batch_id: int, station, line, attribute, target):
    states = build_states(session, batch_id)
    filtered = bool(station or line or attribute or target)
    scoped, _ = apply_filters(session, batch_id, states, station, line, attribute, target)
    return states, scoped, filtered


@router.get("/complaints/summary")
def get_complaint_summary(
    station: str | None = None,
    line: str | None = None,
    attribute: str | None = None,
    target: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=50),
    window: str | None = Query(None, pattern="^(day|week|month|year)$"),
    session: Session = Depends(get_session),
):
    """首頁：Level 3–0 客訴筆數（改善前／改善後）與客訴問題追蹤表（後端分頁）。

    有篩選（站別／線別／屬性／Layout 選取）時，只計入有對應到範圍內 KPOV 的客訴。
    """
    batch = _batch_or_404(session)
    states, scoped, filtered = _scope(session, batch.id, station, line, attribute, target)
    counts, rows = complaint_summary(
        session, batch.id, states, scoped if filtered else None, window_bounds(window)
    )
    return {"levelCounts": counts, **paginate(rows, page, page_size)}


@router.get("/process/summary")
def get_process_summary(
    station: str | None = None,
    line: str | None = None,
    attribute: str | None = None,
    target: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=50),
    window: str | None = Query(None, pattern="^(day|week|month|year)$"),
    session: Session = Depends(get_session),
):
    """首頁：製程問題追蹤（修護報表）— Level 3–0 維修筆數與追蹤表（後端分頁）。"""
    batch = _batch_or_404(session)
    _, scoped, _ = _scope(session, batch.id, station, line, attribute, target)
    counts, rows = process_summary(session, batch.id, scoped, window_bounds(window))
    return {"levelCounts": counts, **paginate(rows, page, page_size)}


def _matches(q: str | None, *values) -> bool:
    if not q:
        return True
    needle = q.strip().lower()
    return any(needle in str(v).lower() for v in values if v is not None)


def _complaint_out(c: FactComplaint, *, full: bool = False) -> dict:
    out = {
        "id": c.id,
        "seq": c.seq,
        "reportNo": c.report_no,
        "complainedAt": c.complained_at.isoformat() if c.complained_at else None,
        "customer": c.customer,
        "category": c.category,
        "item": c.item,
        "processUnit": c.process_unit,
        "productKpov": c.product_kpov,
        "levelBefore": c.level_before,
        "levelAfter": c.level_after,
        "owner": c.owner,
        "plannedAt": c.planned_at.isoformat() if c.planned_at else None,
        "doneAt": c.done_at.isoformat() if c.done_at else None,
        "plannedText": c.planned_text,
        "doneText": c.done_text,
        "effectiveness": c.effectiveness,
        "equipmentCode": c.equipment_code,
        "kpovNo": c.kpov_no,
    }
    if full:
        out.update(
            {
                "site": c.site,
                "plant": c.plant,
                "causeOccur": c.cause_occur,
                "causeEscape": c.cause_escape,
                "countermeasure": c.countermeasure,
                "verdict": c.verdict,
                "before": {
                    "bigYItem": c.big_y_item_before,
                    "bigYMethod": c.big_y_method_before,
                    "bigYScore": c.big_y_score_before,
                    "smallYMethod": c.small_y_method_before,
                    "smallYScore": c.small_y_score_before,
                },
                "after": {
                    "smallYMethod": c.small_y_method_after,
                    "smallYScore": c.small_y_score_after,
                    "bigYMethod": c.big_y_method_after,
                    "bigYScore": c.big_y_score_after,
                },
            }
        )
    return out


@router.get("/complaints")
def list_complaints(
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=50),
    session: Session = Depends(get_session),
):
    """客訴清單（後端分頁、關鍵字搜尋），新到舊。"""
    batch = _batch_or_404(session)
    complaints = session.scalars(
        select(FactComplaint)
        .where(FactComplaint.batch_id == batch.id)
        .order_by(FactComplaint.complained_at.desc(), FactComplaint.seq.desc())
    ).all()
    rows = [
        _complaint_out(c, full=True)
        for c in complaints
        if _matches(q, c.report_no, c.customer, c.category, c.item, c.process_unit, c.product_kpov, c.owner, c.kpov_no)
    ]
    return paginate(rows, page, page_size)


@router.get("/repairs")
def list_repairs(
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, alias="pageSize", ge=1, le=50),
    session: Session = Depends(get_session),
):
    """製程清單：修護報表（後端分頁、關鍵字搜尋），依測試時間新到舊。"""
    batch = _batch_or_404(session)
    states = {(s.kpov.kpov_no, s.kpov.equipment_code): s for s in build_states(session, batch.id)}
    repairs = session.scalars(select(FactRepair).where(FactRepair.batch_id == batch.id)).all()
    epoch = dt.datetime.min.replace(tzinfo=dt.timezone.utc)

    def utc(value):
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)

    repairs = sorted(repairs, key=lambda r: utc(r.tested_at) or epoch, reverse=True)
    now = dt.datetime.now(dt.timezone.utc)
    rows = []
    for r in repairs:
        state = states.get((r.kpov_no, r.equipment_code))
        name = state.kpov.kpov_name if state else None
        station = r.station or (state.kpov.station if state else None)
        if not _matches(q, r.serial_no, r.product_model, r.line, station, r.equipment_code, r.kpov_no, name,
                        r.product_defect_desc, r.improvement):
            continue
        improve_at = utc(r.improvement_effective_at)
        rows.append(
            {
                "id": r.id,
                "testedAt": utc(r.tested_at).isoformat() if r.tested_at else None,
                "serialNo": r.serial_no,
                "productModel": r.product_model,
                "line": r.line,
                "station": station,
                "equipmentCode": r.equipment_code,
                "kpovNo": r.kpov_no,
                "kpovName": name,
                "defectDesc": r.product_defect_desc or r.defect_desc,
                "improvement": r.improvement,
                "improvedAt": improve_at.isoformat() if improve_at else None,
                "improvePlanned": bool(improve_at and improve_at > now),
                "levelBefore": state.level_baseline if state else None,
                "levelAfter": state.level_current if state else None,
            }
        )
    return paginate(rows, page, page_size)


@router.post("/import")
def do_import(file: UploadFile = File(...), session: Session = Depends(get_session)):
    # 刻意用 def 而非 async def：內部的檔案寫入、openpyxl 解析與 DB 寫入全是同步且
    # 耗時的工作。宣告成 async def 會讓它直接跑在 event loop 上，匯入期間整個程序
    # 無法接受新連線，反向代理會出現 connect timeout。用 def 交給 threadpool 執行。
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


class PresenceIn(BaseModel):
    sid: str = Field(min_length=1, max_length=64)


@router.post("/presence/heartbeat")
def presence_heartbeat(body: PresenceIn):
    presence.touch(body.sid)
    return {"online": presence.count()}


@router.post("/presence/leave", status_code=204)
def presence_leave(body: PresenceIn):
    # 由 navigator.sendBeacon 在關閉分頁時呼叫，回應不會被讀取
    presence.leave(body.sid)


# --------------------------------------------------------------------------- 拍照點檢

PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
PHOTO_MAX_BYTES = 10 * 1024 * 1024
PHOTO_SUBDIR = "checks"


@router.get("/check-items")
def get_check_items(station: str | None = None, session: Session = Depends(get_session)):
    """拍照點檢頁：站別清單，與指定站別的點檢項目＋本班進度。"""
    batch = _batch_or_404(session)
    items = check_items(session, batch.id)
    stations = sorted({i.station for i in items if i.station and i.equipment_code})
    selected = [i for i in items if i.station == station and i.equipment_code] if station else []
    return {
        "stations": stations,
        "items": monitor_rows(session, selected),
        "shift": shift_payload(),
    }


@router.post("/check-inspections", status_code=201)
def create_check_inspection(
    equipment_code: str = Form(..., alias="equipmentCode"),
    kpov_no: str | None = Form(None, alias="kpovNo"),
    check_content: str = Form(..., alias="checkContent"),
    status: str = Form("ok", pattern="^(ok|warn)$"),
    note: str | None = Form(None),
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """拍照點檢：照片上傳成功即記一次點檢（預設正常，可回報異常）。"""
    batch = _batch_or_404(session)
    content = check_content.strip()
    item = session.scalars(
        select(FactCheckItem).where(
            FactCheckItem.batch_id == batch.id,
            FactCheckItem.equipment_code == equipment_code,
            FactCheckItem.check_content == content,
            (FactCheckItem.kpov_no == kpov_no) if kpov_no else FactCheckItem.kpov_no.is_(None),
        )
    ).first()
    if item is None:
        raise HTTPException(status_code=404, detail="找不到這個點檢項目，請重新整理後再試")

    ext = Path(file.filename or "").suffix.lower() or ".jpg"
    if ext not in PHOTO_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"不支援的圖片格式 {ext}；可用：{', '.join(sorted(PHOTO_EXTENSIONS))}",
        )

    folder = AR_UPLOAD_DIR / PHOTO_SUBDIR
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    target = folder / filename
    size = 0
    try:
        with target.open("wb") as fh:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > PHOTO_MAX_BYTES:
                    raise HTTPException(status_code=413, detail="照片超過 10 MB，請降低解析度後再上傳")
                fh.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="照片是空的，請重新拍照")

        record = CheckPhotoInspection(
            equipment_code=equipment_code,
            kpov_no=kpov_no,
            check_content=content,
            status=status,
            note=(note or "").strip() or None,
            photo_url=f"{AR_UPLOAD_URL_PREFIX}/{PHOTO_SUBDIR}/{filename}",
        )
        session.add(record)
        session.commit()
    except BaseException:
        # 只有照片與紀錄都成功才算點檢；任一步失敗就不留孤兒檔
        session.rollback()
        target.unlink(missing_ok=True)
        raise

    return {
        "id": record.id,
        "status": record.status,
        "photoUrl": record.photo_url,
        "inspectedAt": utc(record.inspected_at).isoformat(),
    }


# --------------------------------------------------------------------------- 點檢儀表板（拍照點檢紀錄）
# 時間一律以帶時區的 UTC 輸出（SQLite 讀回不帶時區，須以 utc() 補上），由前端轉成本地時間顯示；
# 只有匯出的 Excel 直接換成廠區時間。


def _station_names(session: Session) -> dict[str, str]:
    """設備代碼 -> 站名（依目前生效批次的 KPOV 庫）；尚未匯入時為空。"""
    batch = active_batch(session)
    return dict(station_order(session, batch.id)) if batch else {}


def _photo_records(
    session: Session,
    equipment_code: str | None = None,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
) -> list[CheckPhotoInspection]:
    stmt = select(CheckPhotoInspection).order_by(
        CheckPhotoInspection.inspected_at.desc(), CheckPhotoInspection.id.desc()
    )
    if equipment_code:
        stmt = stmt.where(CheckPhotoInspection.equipment_code == equipment_code)
    records = session.scalars(stmt).all()
    # 時間篩選在 Python 端做：SQLite 存的是不帶時區的 UTC，直接在 SQL 比較帶時區的參數不可靠
    if start is not None:
        records = [r for r in records if utc(r.inspected_at) >= utc(start)]
    if end is not None:
        records = [r for r in records if utc(r.inspected_at) <= utc(end)]
    return records


def _photo_out(record: CheckPhotoInspection, names: dict[str, str]) -> dict:
    return {
        "id": record.id,
        "equipmentCode": record.equipment_code,
        "station": names.get(record.equipment_code, record.equipment_code),
        "kpovNo": record.kpov_no,
        "checkContent": record.check_content,
        "status": record.status,
        "note": record.note,
        "photoUrl": record.photo_url,
        "inspectedAt": utc(record.inspected_at).isoformat(),
    }


@router.get("/check-inspections")
def list_check_inspections(
    equipment_code: str | None = Query(None, alias="equipmentCode"),
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
    limit: int = Query(200, ge=1, le=1000),
    session: Session = Depends(get_session),
):
    """點檢儀表板：拍照點檢紀錄，新到舊。start／end 為帶時區的 ISO 時間（不帶時區視為 UTC）。"""
    records = _photo_records(session, equipment_code, start, end)
    names = _station_names(session)
    return {"total": len(records), "items": [_photo_out(r, names) for r in records[:limit]]}


@router.get("/check-inspections/stats")
def check_inspection_stats(session: Session = Depends(get_session)):
    """點檢儀表板的良率卡片：依設備（站別）彙總拍照點檢的正常／異常次數。"""
    names = _station_names(session)
    stats: dict[str, dict] = {}
    for record in _photo_records(session):
        entry = stats.setdefault(
            record.equipment_code,
            {
                "equipmentCode": record.equipment_code,
                "station": names.get(record.equipment_code, record.equipment_code),
                "total": 0,
                "okCount": 0,
                "warnCount": 0,
            },
        )
        entry["total"] += 1
        entry["okCount" if record.status == "ok" else "warnCount"] += 1
    order = {code: i for i, code in enumerate(names)}
    rows = sorted(stats.values(), key=lambda s: (order.get(s["equipmentCode"], len(order)), s["equipmentCode"]))
    for row in rows:
        row["okRate"] = round(row["okCount"] / row["total"], 4)
    return rows


@router.delete("/check-inspections/{record_id}")
def delete_check_inspection(record_id: int, session: Session = Depends(get_session)):
    """刪除一筆拍照點檢，照片檔一併刪除。"""
    record = session.get(CheckPhotoInspection, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="找不到該筆點檢紀錄")
    photo = record.photo_url
    session.delete(record)
    session.commit()
    prefix = f"{AR_UPLOAD_URL_PREFIX}/"
    if photo and photo.startswith(prefix):
        target = (AR_UPLOAD_DIR / photo[len(prefix) :]).resolve()
        # 只刪上傳目錄底下的檔案，避免被竄改的路徑刪到其他地方
        if target.is_relative_to(AR_UPLOAD_DIR.resolve()):
            target.unlink(missing_ok=True)
    return {"id": record_id, "deleted": True}


@router.get("/check-inspections/export")
def export_check_inspections(session: Session = Depends(get_session)):
    """點檢紀錄匯出 Excel，時間換成廠區當地時間。"""
    from openpyxl import Workbook

    records = _photo_records(session)
    if not records:
        raise HTTPException(status_code=404, detail="目前沒有點檢紀錄可匯出")
    names = _station_names(session)
    site = dt.timezone(dt.timedelta(hours=SITE_UTC_OFFSET_HOURS))
    offset = f"UTC{SITE_UTC_OFFSET_HOURS:+g}"

    wb = Workbook()
    ws = wb.active
    ws.title = "點檢紀錄"
    ws.append(["紀錄編號", "站別", "設備代碼", "KPOV 編號", "點檢內容", "狀態", "備註", "照片網址", f"點檢時間（{offset}）"])
    for r in records:
        ws.append(
            [
                r.id,
                names.get(r.equipment_code, r.equipment_code),
                r.equipment_code,
                r.kpov_no,
                r.check_content,
                "正常" if r.status == "ok" else "異常",
                r.note,
                r.photo_url,
                utc(r.inspected_at).astimezone(site).strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    stamp = dt.datetime.now(site).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="check_inspections_{stamp}.xlsx"'},
    )
