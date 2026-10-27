"""API 端點 — spec.md §7。"""
from __future__ import annotations

import datetime as dt
import io
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...config import SITE_UTC_OFFSET_HOURS
from ...services.storage import get_storage, key_from_url
from ...services.storage import url_for as storage_url_for
from ...db import get_session
from ..deps import Scope, current_scope, current_user, require_admin, require_super
from ...services.auth import can_import, can_view_plant, parse_dataset_filename
from ...importer.excel import ImportError_, import_workbook
from ...models import (
    CheckCountImport,
    CheckPhotoInspection,
    DimEquipment,
    FactChangeRecord,
    FactCheckItem,
    FactComplaint,
    FactLevelEvent,
    FactRepair,
    ImportBatch,
    User,
)
from ...services.measure_rows import events_by_repair, repair_row
from ...importer.mapping import REPAIR_EIGHT_D_PREFIX as M_REPAIR_PREFIX
from ...services.eight_d import eight_d_out
from ...services.station_levels import event_levels, kpov_levels, station_order
from ...services.tracking import complaint_summary, paginate, process_summary
from ...services.check_monitor import (
    EXPORT_SHIFT_NAMES,
    SLOT_MISSED,
    SLOT_OK,
    SLOT_WARN,
    check_items,
    item_key,
    monitor_rows,
    shift_of,
    shift_payload,
    summarize_rows,
    utc,
)
from ...services import presence
from ...services.check_trend import check_trend
from ...services.count_import import CountImportError, parse_count_workbook
from ...services.due import (
    DUE_FILTERS,
    due_matches,
    due_stats,
    due_status,
    in_day_range,
    parse_day,
    site_today,
)
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

# 除了登入（auth_routes）以外，所有 /api/v1 都要先登入（spec §15）
router = APIRouter(prefix="/api/v1", dependencies=[Depends(current_user)])


def _check_view(view: str) -> str:
    if view not in VIEWS:
        raise HTTPException(status_code=400, detail=f"view 必須是 {', '.join(VIEWS)} 其中之一")
    return view


def _batch_info(batch: ImportBatch) -> dict:
    return {
        "id": batch.id,
        "filename": batch.filename,
        "importedAt": _iso_utc(batch.imported_at),
        "dataset": batch.dataset,
        "plant": batch.plant,
        "factory": batch.factory,
        "line": batch.line_code,
        "importedBy": batch.imported_by,
    }


@router.get("/filters")
def get_filters(scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session)):
    batch = scope.batch
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
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """象限圖。母體一律為全部 KPOV；給 window 時另回 start＝期間第一天當時的 Level 分佈（期初 → 現在）。"""
    _check_view(view)
    batch = scope.batch
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
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    batch = scope.batch
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
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    _check_view(view)
    batch = scope.batch
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
def kpov_history(kpov_no: str, equipment_code: str, scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session)):
    batch = scope.batch
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
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """Level 3 高風險項點檢監控：點檢項目 × AR 逐項點檢最新結果。"""
    batch = scope.batch
    codes: set[str] | None = None
    if station or line or attribute or target:
        states = build_states(session, batch.id)
        scoped, _ = apply_filters(session, batch.id, states, station, line, attribute, target)
        codes = {s.kpov.equipment_code for s in scoped if s.kpov.equipment_code}
    rows = monitor_rows(session, check_items(session, batch.id, codes), dataset=scope.dataset)
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
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    batch = scope.batch
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
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """等級異動總覽：近 1／7／30／365 天內發生的惡化或改善，後端分頁。

    惡化以不良發生（測試）時間落在區間內為準；改善以改善時間落在區間內為準。
    尚未到的預計改善不算「已改善」。兩個卡片的數字（escalated / improved）同樣依區間計算。
    """
    batch = scope.batch
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

    items = []
    for e in page_items:
        repair = repairs.get(e.repair_id) if e.repair_id else None
        if repair is None:
            continue  # 事件一律來自維修紀錄；找不到代表資料不一致，略過而不是組出半套的列
        row = repair_row(
            repair,
            states_by_key.get((e.kpov_no, e.equipment_code)),
            events.get(repair.id, {}),
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


# --------------------------------------------------------------------------- 總覽廣播


@router.get("/broadcast")
def get_broadcast(
    window: str = Query("month", pattern="^(day|week|month|year)$"),
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """總覽頁頂端的廣播（spec §16）。一律看整條線、不吃篩選器：

    - level3：Level 3 個數，期初（期間第一天）→ 現在，與象限圖同一套算法
    - inspection：當班（白班／夜班）的點檢次數：已點檢／應點檢、其中異常
    - escalations：期間內等級提升的站別（ESCALATED 事件，依不良發生時間）
    - alerts：跑馬燈只列需要關注的項目（v2.7）：當班漏點檢、當班點檢異常、期間內升到 Level 3、期間內新增的 Level 3
    """
    batch = scope.batch
    now = dt.datetime.now(dt.timezone.utc)
    since, _ = window_bounds(window)
    states = build_states(session, batch.id)
    start_states = build_states(session, batch.id, as_of=since)
    level3_now = sum(1 for s in states if s.level_for("current") == 3)
    level3_start = sum(1 for s in start_states if s.level_for("current") == 3)

    rows = monitor_rows(session, check_items(session, batch.id), now=now, dataset=scope.dataset)
    slots = [slot for row in rows for slot in row["slots"]]
    shift = shift_payload(now)

    kpovs = {(s.kpov.kpov_no, s.kpov.equipment_code): s.kpov for s in states}
    events = session.scalars(
        select(FactLevelEvent)
        .where(FactLevelEvent.batch_id == batch.id, FactLevelEvent.transition == CHANGE_KINDS_UI["escalated"])
        .order_by(FactLevelEvent.effective_at.desc(), FactLevelEvent.id.desc())
    ).all()
    escalations = []
    for e in events:
        at = utc(e.effective_at)
        kpov = kpovs.get((e.kpov_no, e.equipment_code))
        if kpov is None or not since <= at <= now:
            continue
        escalations.append(
            {
                "station": kpov.station,
                "kpovNo": e.kpov_no,
                "kpovName": kpov.kpov_name,
                "equipmentCode": e.equipment_code,
                "levelBefore": e.level_before,
                "levelAfter": e.level_after,
                "at": at.isoformat(),
            }
        )

    alerts = []
    for row in rows:
        for kind, state in (("missed", SLOT_MISSED), ("warn", SLOT_WARN)):
            count = sum(1 for slot in row["slots"] if slot["state"] == state)
            if count:
                alerts.append({"kind": kind, "station": row["station"], "equipmentCode": row["equipmentCode"],
                               "kpovNo": row["kpovNo"], "text": row["checkContent"], "count": count})
    # 升到 Level 3：每個 KPOV 取期間內最近一次（escalations 已新到舊）
    to_level3 = {}
    for e in escalations:
        if e["levelAfter"] == 3:
            to_level3.setdefault((e["kpovNo"], e["equipmentCode"]), e)
    for e in to_level3.values():
        alerts.append({"kind": "escalatedL3", "station": e["station"], "equipmentCode": e["equipmentCode"],
                       "kpovNo": e["kpovNo"], "text": e["kpovName"], "levelBefore": e["levelBefore"], "levelAfter": 3})
    # 新增的 Level 3：期初不是 Level 3、現在是；已在「升到 Level 3」列出的不重複
    was_level3 = {(s.kpov.kpov_no, s.kpov.equipment_code) for s in start_states if s.level_for("current") == 3}
    for st in states:
        key = (st.kpov.kpov_no, st.kpov.equipment_code)
        if st.level_for("current") == 3 and key not in was_level3 and key not in to_level3:
            alerts.append({"kind": "level3New", "station": st.kpov.station, "equipmentCode": st.kpov.equipment_code,
                           "kpovNo": st.kpov.kpov_no, "text": st.kpov.kpov_name})

    return {
        "window": window,
        "since": since.isoformat(),
        "alerts": alerts,
        "level3": {"start": level3_start, "now": level3_now, "delta": level3_now - level3_start},
        "inspection": {
            # 使用者慣稱白班／夜班（與點檢紀錄匯出相同）
            "shift": {
                **shift,
                "name": EXPORT_SHIFT_NAMES.get(shift["name"], shift["name"]),
                "label": shift["label"].replace(shift["name"], EXPORT_SHIFT_NAMES.get(shift["name"], shift["name"]), 1),
            },
            "items": len(rows),
            "expected": len(slots),
            "completed": sum(1 for slot in slots if slot["state"] in (SLOT_OK, SLOT_WARN)),
            "warn": sum(1 for slot in slots if slot["state"] == SLOT_WARN),
        },
        "escalations": escalations,
        "escalatedStations": sorted({x["station"] for x in escalations}),
    }


# --------------------------------------------------------------------------- 站別風險地圖


@router.get("/station-risk")
def get_station_risk(
    window: str = Query("month", pattern="^(day|week|month|year)$"),
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """站別風險地圖：近 1／7／30／365 天內各設備的維修與客訴筆數，以及期間內最嚴重的 Level。

    維修依測試時間、客訴依客訴日期落在區間內計數。Level 取「發生當時」：
    維修＝該筆的惡化事件後 Level；客訴＝改善前 Level。前端依 worstLevel 上卡片底色。
    客訴未填設備ID 者無法歸到任何站，另計 unmappedComplaints。不套用上方篩選：地圖本身就是全線一覽。
    """
    batch = scope.batch
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
def get_station_kpov_levels(scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session)):
    """站別柱狀圖（layout 下方）：各站 KPOV 個數，依 KPOV 數據庫原始 Level。全線一覽，不套用篩選與期間。"""
    batch = scope.batch
    return kpov_levels(session, batch.id)


@router.get("/station-levels/events")
def get_station_event_levels(
    window: str = Query("month", pattern="^(day|week|month|year)$"),
    station: str | None = None,
    line: str | None = None,
    attribute: str | None = None,
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """客訴／製程柱狀圖：期間內各站的客訴與維修筆數，依發生當時的 Level 分色；套用上方篩選。"""
    batch = scope.batch
    scoped, _ = apply_filters(session, batch.id, build_states(session, batch.id), station, line, attribute)
    return event_levels(session, batch.id, window, scoped)


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
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """首頁：Level 3–0 客訴筆數（改善前／改善後）與客訴問題追蹤表（後端分頁）。

    有篩選（站別／線別／屬性／Layout 選取）時，只計入有對應到範圍內 KPOV 的客訴。
    """
    batch = scope.batch
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
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """首頁：製程問題追蹤（修護報表）— Level 3–0 維修筆數與追蹤表（後端分頁）。"""
    batch = scope.batch
    _, scoped, _ = _scope(session, batch.id, station, line, attribute, target)
    counts, rows = process_summary(session, batch.id, scoped, window_bounds(window))
    return {"levelCounts": counts, **paginate(rows, page, page_size)}


def _iso_utc(value: dt.datetime | None) -> str | None:
    """帶時區的 UTC ISO 字串（SQLite 讀回不帶時區）。"""
    return utc(value).isoformat() if value else None


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
        # 1019 版起：緊急措施；長期措施＝改善措施／改善時間
        "emergencyMeasure": c.emergency_measure,
        "emergencyMeasureAt": _iso_utc(c.emergency_measure_at),
        "improvement": c.improvement,
        "improvementAt": _iso_utc(c.improvement_effective_at),
    }
    if full:
        out["eightD"] = eight_d_out(c)
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


class ListFilters:
    """製程風險管理／客訴案件管理的清單篩選（spec §17）。

    日期範圍為廠區當地日期（YYYY-MM-DD，起訖皆含）；多選以重複的查詢參數傳入（?station=A&station=B）。
    due：planned（預計完成）、overdue（全部逾期）、lt7／d7_14／gt14（逾期天數分組）。
    """

    def __init__(
        self,
        occurred_from: str | None = Query(None, alias="occurredFrom"),
        occurred_to: str | None = Query(None, alias="occurredTo"),
        group: list[str] = Query([]),
        station: list[str] = Query([]),
        kpov: list[str] = Query([]),
        improved_from: str | None = Query(None, alias="improvedFrom"),
        improved_to: str | None = Query(None, alias="improvedTo"),
        due: str | None = Query(None, pattern="^(" + "|".join(DUE_FILTERS) + ")$"),
        page: int = Query(1, ge=1),
        page_size: int = Query(10, alias="pageSize", ge=1, le=50),
    ):
        self.occurred = (parse_day(occurred_from), parse_day(occurred_to))
        self.groups = set(group)
        self.stations = set(station)
        self.kpovs = set(kpov)
        self.improved = (parse_day(improved_from), parse_day(improved_to))
        self.due = due
        self.page = page
        self.page_size = page_size

    def keep(self, row: dict) -> bool:
        """除 due 以外的條件（圓餅圖依這組結果統計，再由 due 決定清單）。"""
        return (
            in_day_range(row["_occurred"], *self.occurred)
            and (not self.groups or row["_group"] in self.groups)
            and (not self.stations or row["station"] in self.stations)
            and (not self.kpovs or row["kpovNo"] in self.kpovs)
            and in_day_range(row["_improved"], *self.improved)
        )


def _filtered_listing(rows: list[dict], f: ListFilters) -> dict:
    """rows 帶 _occurred／_group／_improved 私有欄位與 due；回傳分頁清單＋圓餅統計＋篩選選項。"""
    kpov_labels: dict[str, str] = {}
    for r in rows:
        if r["kpovNo"] and r["kpovNo"] not in kpov_labels:
            kpov_labels[r["kpovNo"]] = r.get("kpovName") or r["kpovNo"]
    filter_options = {
        "groups": sorted({r["_group"] for r in rows if r["_group"]}),
        "stations": sorted({r["station"] for r in rows if r["station"]}),
        "kpovs": [{"value": k, "label": v} for k, v in sorted(kpov_labels.items())],
    }
    kept = [r for r in rows if f.keep(r)]
    stats = due_stats([r["due"] for r in kept])
    listed = [{k: v for k, v in r.items() if not k.startswith("_")} for r in kept if due_matches(r["due"], f.due)]
    return {**paginate(listed, f.page, f.page_size), "dueStats": stats, "options": filter_options}


@router.get("/complaints")
def list_complaints(
    f: ListFilters = Depends(),
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """客訴清單（後端分頁），新到舊。篩選：日期、客戶、站別、KPOV、改善時間、完成期限（spec §17）。

    客訴報表沒有機種欄位，第二個篩選用客戶；站別取 KPOV 對應的站別，對不到時用製程單元。
    """
    batch = scope.batch
    states = {(s.kpov.kpov_no, s.kpov.equipment_code): s for s in build_states(session, batch.id)}
    complaints = session.scalars(
        select(FactComplaint)
        .where(FactComplaint.batch_id == batch.id)
        .order_by(FactComplaint.complained_at.desc(), FactComplaint.seq.desc())
    ).all()
    today = site_today()
    rows = []
    for c in complaints:
        state = states.get((c.kpov_no, c.equipment_code))
        rows.append(
            {
                **_complaint_out(c, full=True),
                "station": state.kpov.station if state else c.process_unit,
                "kpovName": state.kpov.kpov_name if state else c.product_kpov,
                "due": due_status(c.planned_at, c.done_at, today),
                "_occurred": c.complained_at,
                "_group": c.customer,
                "_improved": c.improvement_effective_at,
            }
        )
    return _filtered_listing(rows, f)


@router.get("/repairs")
def list_repairs(
    f: ListFilters = Depends(),
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """製程清單：修護報表（後端分頁），依測試時間新到舊。
    篩選：測試時間、機種、站別、KPOV、改善時間、完成期限（spec §17）。"""
    batch = scope.batch
    states = {(s.kpov.kpov_no, s.kpov.equipment_code): s for s in build_states(session, batch.id)}
    repairs = session.scalars(select(FactRepair).where(FactRepair.batch_id == batch.id)).all()
    epoch = dt.datetime.min.replace(tzinfo=dt.timezone.utc)

    def utc(value):
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)

    repairs = sorted(repairs, key=lambda r: utc(r.tested_at) or epoch, reverse=True)
    now = dt.datetime.now(dt.timezone.utc)
    today = site_today(now)
    rows = []
    for r in repairs:
        state = states.get((r.kpov_no, r.equipment_code))
        name = state.kpov.kpov_name if state else None
        station = r.station or (state.kpov.station if state else None)
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
                "emergencyMeasure": r.emergency_measure,
                "emergencyMeasureAt": _iso_utc(r.emergency_measure_at),
                "improvement": r.improvement,
                "improvedAt": improve_at.isoformat() if improve_at else None,
                "improvePlanned": bool(improve_at and improve_at > now),
                "levelBefore": state.level_baseline if state else None,
                "levelAfter": state.level_current if state else None,
                # 8D 預計完成 vs 實際完成
                "due": due_status(r.d8_planned_at, r.d8_done_at, today),
                "_occurred": r.tested_at,
                "_group": r.product_model,
                "_improved": r.improvement_effective_at,
            }
        )
    return _filtered_listing(rows, f)


@router.get("/repairs/{repair_id}")
def get_repair(repair_id: int, scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session)):
    """單筆維修明細：基本資料、緊急措施、長期措施（改善措施／改善時間）與 8D 內容。"""
    batch = scope.batch
    r = session.get(FactRepair, repair_id)
    if r is None or r.batch_id != batch.id:
        raise HTTPException(status_code=404, detail="找不到這筆維修紀錄，請重新整理後再試")
    return {
        "id": r.id,
        "serialNo": r.serial_no,
        "month": r.month,
        "productModel": r.product_model,
        "workOrder": r.work_order,
        "line": r.line,
        "team": r.team,
        "testedAt": _iso_utc(r.tested_at),
        "defectDesc": r.defect_desc,
        "productDefectDesc": r.product_defect_desc,
        "repairPartLocation": r.repair_part_location,
        "responsibility": r.responsibility,
        "defectCause": r.defect_cause,
        "subCategory": r.sub_category,
        "technician": r.technician,
        "repairedAt": _iso_utc(r.repaired_at),
        "countermeasure": r.countermeasure,
        "responsibleDept": r.responsible_dept,
        "remark": r.remark,
        "station": r.station,
        "equipmentCode": r.equipment_code,
        "kpovNo": r.kpov_no,
        "emergencyMeasure": r.emergency_measure,
        "emergencyMeasureAt": _iso_utc(r.emergency_measure_at),
        "improvement": r.improvement,
        "improvementAt": _iso_utc(r.improvement_effective_at),
        "eightD": eight_d_out(r, M_REPAIR_PREFIX),
    }


@router.get("/complaints/{complaint_id}")
def get_complaint(complaint_id: int, scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session)):
    """單筆客訴明細（含 8D 內容）。"""
    batch = scope.batch
    c = session.get(FactComplaint, complaint_id)
    if c is None or c.batch_id != batch.id:
        raise HTTPException(status_code=404, detail="找不到這筆客訴，請重新整理後再試")
    return _complaint_out(c, full=True)


@router.post("/import")
def do_import(
    file: UploadFile = File(...),
    actor: User = Depends(require_admin),
    session: Session = Depends(get_session),
):
    # 刻意用 def 而非 async def：內部的檔案寫入、openpyxl 解析與 DB 寫入全是同步且
    # 耗時的工作。宣告成 async def 會讓它直接跑在 event loop 上，匯入期間整個程序
    # 無法接受新連線，反向代理會出現 connect timeout。用 def 交給 threadpool 執行。
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="請上傳 .xlsx 檔案")
    # 檔名決定資料集（廠-產品廠-線別），廠管理者只能匯入自己廠的檔案（spec §15）
    try:
        dataset = parse_dataset_filename(file.filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not can_import(actor.role, actor.plant, dataset.plant):
        raise HTTPException(status_code=403, detail=f"沒有匯入 {dataset.plant} 資料的權限（你屬於 {actor.plant}）")

    tmp = Path(tempfile.mkdtemp()) / file.filename
    with tmp.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    try:
        batch, report = import_workbook(
            session, str(tmp), os.path.basename(file.filename), imported_by=actor.username, dataset=dataset
        )
    except ImportError_ as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)

    return {"batchId": batch.id, "batch": _batch_info(batch), "report": report.as_dict()}


@router.get("/import/history")
def import_history(actor: User = Depends(current_user), session: Session = Depends(get_session)):
    batches = [
        b
        for b in session.scalars(select(ImportBatch).order_by(ImportBatch.id.desc())).all()
        if b.plant and can_view_plant(actor.role, actor.plant, b.plant)
    ]
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
def get_check_items(station: str | None = None, scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session)):
    """拍照點檢頁：站別清單，與指定站別的點檢項目＋本班進度。"""
    batch = scope.batch
    items = check_items(session, batch.id)
    stations = sorted({i.station for i in items if i.station and i.equipment_code})
    selected = [i for i in items if i.station == station and i.equipment_code] if station else []
    return {
        "stations": stations,
        "items": monitor_rows(session, selected, dataset=scope.dataset),
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
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """拍照點檢：照片上傳成功即記一次點檢（預設正常，可回報異常）。"""
    batch = scope.batch
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

    # 先讀進記憶體並檢查大小（上限 10 MB），再交給儲存層（本機磁碟或 Cloudflare R2）
    chunks: list[bytes] = []
    size = 0
    while chunk := file.file.read(1024 * 1024):
        size += len(chunk)
        if size > PHOTO_MAX_BYTES:
            raise HTTPException(status_code=413, detail="照片超過 10 MB，請降低解析度後再上傳")
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(status_code=422, detail="照片是空的，請重新拍照")

    storage = get_storage()
    key = f"{PHOTO_SUBDIR}/{uuid.uuid4().hex}{ext}"
    storage.put(key, b"".join(chunks), file.content_type)
    try:

        record = CheckPhotoInspection(
            equipment_code=equipment_code,
            kpov_no=kpov_no,
            check_content=content,
            status=status,
            note=(note or "").strip() or None,
            photo_url=storage_url_for(key),
            dataset=scope.dataset,
        )
        session.add(record)
        session.commit()
    except BaseException:
        # 只有照片與紀錄都成功才算點檢；任一步失敗就不留孤兒檔
        session.rollback()
        storage.delete(key)
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


def _station_names(session: Session, batch: ImportBatch) -> dict[str, str]:
    """設備代碼 -> 站名（依該資料集生效批次的 KPOV 庫）。"""
    return dict(station_order(session, batch.id))


def _photo_records(
    session: Session,
    batch: ImportBatch,
    equipment_code: str | None = None,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
) -> list[CheckPhotoInspection]:
    """該資料集（一條線）的拍照點檢紀錄，新到舊；只列目前點檢項目底下的紀錄（REQ-V2-CHK-03）。"""
    stmt = (
        select(CheckPhotoInspection)
        .where(CheckPhotoInspection.dataset == batch.dataset)
        .order_by(CheckPhotoInspection.inspected_at.desc(), CheckPhotoInspection.id.desc())
    )
    if equipment_code:
        stmt = stmt.where(CheckPhotoInspection.equipment_code == equipment_code)
    records = session.scalars(stmt).all()
    current = {item_key(i.equipment_code, i.kpov_no, i.check_content) for i in check_items(session, batch.id)}
    records = [r for r in records if item_key(r.equipment_code, r.kpov_no, r.check_content) in current]
    # 時間篩選在 Python 端做：SQLite 存的是不帶時區的 UTC，直接在 SQL 比較帶時區的參數不可靠
    if start is not None:
        records = [r for r in records if utc(r.inspected_at) >= utc(start)]
    if end is not None:
        records = [r for r in records if utc(r.inspected_at) <= utc(end)]
    return records


def _control_levels(session: Session, batch: ImportBatch) -> dict[tuple, str | None]:
    """目前點檢項目的 KPIV(x) 管控等級，以（設備, KPOV, 點檢內容）對應。"""
    return {item_key(i.equipment_code, i.kpov_no, i.check_content): i.kpiv_control_level for i in check_items(session, batch.id)}


def _photo_out(record: CheckPhotoInspection, names: dict[str, str], levels: dict[tuple, str | None]) -> dict:
    return {
        "id": record.id,
        "equipmentCode": record.equipment_code,
        "station": names.get(record.equipment_code, record.equipment_code),
        "kpovNo": record.kpov_no,
        "checkContent": record.check_content,
        "kpivControlLevel": levels.get(item_key(record.equipment_code, record.kpov_no, record.check_content)),
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
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """點檢儀表板：拍照點檢紀錄，新到舊。start／end 為帶時區的 ISO 時間（不帶時區視為 UTC）。"""
    records = _photo_records(session, scope.batch, equipment_code, start, end)
    names = _station_names(session, scope.batch)
    levels = _control_levels(session, scope.batch)
    return {"total": len(records), "items": [_photo_out(r, names, levels) for r in records[:limit]]}


@router.get("/check-inspections/stats")
def check_inspection_stats(scope: Scope = Depends(current_scope), session: Session = Depends(get_session)):
    """點檢儀表板的良率卡片：依設備（站別）彙總拍照點檢的正常／異常次數。"""
    names = _station_names(session, scope.batch)
    stats: dict[str, dict] = {}
    for record in _photo_records(session, scope.batch):
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
    # 匯入的歷史點檢數量（spec §19）：只累加卡片，不受「目前點檢項目」過濾（舊點檢內容的文字可能已改）
    for row in session.scalars(select(CheckCountImport).where(CheckCountImport.dataset == scope.dataset)):
        entry = stats.setdefault(
            row.equipment_code,
            {
                "equipmentCode": row.equipment_code,
                "station": names.get(row.equipment_code) or row.station or row.equipment_code,
                "total": 0,
                "okCount": 0,
                "warnCount": 0,
            },
        )
        entry["total"] += 1
        entry["okCount" if row.status == "ok" else "warnCount"] += 1
        entry["importedCount"] = entry.get("importedCount", 0) + 1
    order = {code: i for i, code in enumerate(names)}
    rows = sorted(stats.values(), key=lambda s: (order.get(s["equipmentCode"], len(order)), s["equipmentCode"]))
    for row in rows:
        row["okRate"] = round(row["okCount"] / row["total"], 4)
        row.setdefault("importedCount", 0)
    return rows


@router.get("/check-inspections/trend")
def check_inspection_trend(
    days: int = Query(14, ge=1, le=90),
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """點檢看板：每日異常次數與漏點檢數、KPIV 點檢內容的異常分布（spec §18）。"""
    imported = session.scalars(select(CheckCountImport).where(CheckCountImport.dataset == scope.dataset)).all()
    return check_trend(check_items(session, scope.batch.id), _photo_records(session, scope.batch), days, imported=imported)


def _count_import_summary(session: Session, dataset: str) -> dict:
    rows = session.scalars(select(CheckCountImport).where(CheckCountImport.dataset == dataset)).all()
    files: dict[str, dict] = {}
    for r in rows:
        f = files.setdefault(r.source or "", {"source": r.source, "count": 0, "okCount": 0, "warnCount": 0,
                                               "from": None, "to": None, "importedAt": None, "importedBy": r.imported_by})
        at, imported = utc(r.inspected_at), utc(r.imported_at)
        f["count"] += 1
        f["okCount" if r.status == "ok" else "warnCount"] += 1
        f["from"] = min(f["from"] or at, at)
        f["to"] = max(f["to"] or at, at)
        f["importedAt"] = max(f["importedAt"] or imported, imported)
    out = sorted(files.values(), key=lambda f: f["importedAt"], reverse=True)
    for f in out:
        f.update({k: f[k].isoformat() for k in ("from", "to", "importedAt")})
    return {"dataset": dataset, "total": len(rows), "files": out}


@router.get("/check-inspections/count-import")
def count_import_summary(
    _: User = Depends(require_super), scope: Scope = Depends(current_scope), session: Session = Depends(get_session)
):
    """這條線已匯入的歷史點檢數量（依檔案彙總）。"""
    return _count_import_summary(session, scope.dataset)


@router.post("/check-inspections/count-import")
def import_check_counts(
    file: UploadFile = File(...),
    actor: User = Depends(require_super),
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """匯入歷史點檢數量（spec §19，最高權限管理者）：只累加點檢看板卡片的正常／異常次數，不建立點檢紀錄。

    以（設備代碼, 點檢內容, 點檢時間）去重：已匯入過、或系統內已有同一筆拍照點檢的都略過。
    """
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=422, detail="請上傳 .xlsx 檔")
    tmp = Path(tempfile.mkdtemp()) / "upload.xlsx"
    try:
        with tmp.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        try:
            parsed = parse_count_workbook(str(tmp))
        except CountImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)

    def key(code, content, at):
        return (code, (content or "").strip(), utc(at).replace(microsecond=0))

    existing = {
        key(r.equipment_code, r.check_content, r.inspected_at)
        for r in session.scalars(select(CheckCountImport).where(CheckCountImport.dataset == scope.dataset))
    } | {
        key(r.equipment_code, r.check_content, r.inspected_at)
        for r in session.scalars(select(CheckPhotoInspection).where(CheckPhotoInspection.dataset == scope.dataset))
    }
    names = _station_names(session, scope.batch)
    source = os.path.basename(file.filename)
    now = dt.datetime.now(dt.timezone.utc)
    added = {"ok": 0, "warn": 0}
    stations: dict[str, dict] = {}
    duplicates = 0
    for row in parsed.rows:
        k = key(row.equipment_code, row.check_content, row.inspected_at)
        if k in existing:
            duplicates += 1
            continue
        existing.add(k)
        session.add(CheckCountImport(
            dataset=scope.dataset, equipment_code=row.equipment_code, station=row.station,
            check_content=row.check_content, status=row.status, inspected_at=row.inspected_at,
            source=source, imported_by=actor.username, imported_at=now,
        ))
        added[row.status] += 1
        st = stations.setdefault(row.equipment_code, {
            "equipmentCode": row.equipment_code,
            "station": names.get(row.equipment_code) or row.station or row.equipment_code,
            "okCount": 0, "warnCount": 0,
        })
        st["okCount" if row.status == "ok" else "warnCount"] += 1
    session.commit()
    return {
        "dataset": scope.dataset,
        "source": source,
        "added": added["ok"] + added["warn"],
        "addedOk": added["ok"],
        "addedWarn": added["warn"],
        "duplicates": duplicates,
        "invalid": parsed.invalid,
        "invalidReasons": parsed.reasons,
        "stations": sorted(stations.values(), key=lambda s: s["station"]),
        "summary": _count_import_summary(session, scope.dataset),
    }


@router.delete("/check-inspections/count-import")
def clear_check_counts(
    _: User = Depends(require_super), scope: Scope = Depends(current_scope), session: Session = Depends(get_session)
):
    """清除這條線匯入的歷史點檢數量（誤匯時用）；不影響拍照點檢紀錄。"""
    rows = session.scalars(select(CheckCountImport).where(CheckCountImport.dataset == scope.dataset)).all()
    for r in rows:
        session.delete(r)
    session.commit()
    return {"deleted": len(rows)}


# 點檢紀錄是稽核證據，不提供刪除 API（使用者 2026-10-20 決定）。


def _photo_bytes(photo_url: str | None) -> bytes | None:
    """照片網址 -> 檔案內容（本機磁碟或 R2）；網址不合法或檔案不存在時回 None。"""
    key = key_from_url(photo_url)
    if key is None:
        return None
    try:
        return get_storage().get(key)
    except Exception:
        return None


EXPORT_MAX_ROWS = 1000
EXPORT_THUMB_WIDTH = 240


def _thumbnail(data: bytes | None):
    """照片縮成寬 240px 的 JPEG 供嵌入 Excel；檔案不存在或無法讀取時回 None。"""
    if not data:
        return None
    from openpyxl.drawing.image import Image as XlImage
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")  # 手機照片依 EXIF 轉正
            img.thumbnail((EXPORT_THUMB_WIDTH, EXPORT_THUMB_WIDTH * 2))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=80)
    except Exception:
        return None
    buffer.seek(0)
    return XlImage(buffer)


@router.get("/check-inspections/export")
def export_check_inspections(
    equipment_code: str | None = Query(None, alias="equipmentCode"),
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
    base_url: str | None = Query(None, alias="baseUrl", pattern=r"^https?://[^\s]+$"),
    scope: Scope = Depends(current_scope),
    session: Session = Depends(get_session),
):
    """點檢紀錄匯出 Excel（含照片縮圖），依點檢時間由舊到新，篩選條件與列表相同。

    時間換成廠區當地時間並標示班別（空檔歸入剛結束的班，夜班日期記為開班日）。
    最多匯出最新 1000 筆，超過時於表頭上方提醒並在回應標頭註明。
    """
    from urllib.parse import quote

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    records = _photo_records(session, scope.batch, equipment_code, start, end)  # 新到舊
    if not records:
        raise HTTPException(status_code=404, detail="沒有符合條件的點檢紀錄可匯出")
    truncated = len(records) > EXPORT_MAX_ROWS
    records = list(reversed(records[:EXPORT_MAX_ROWS]))  # 取最新的 N 筆，再改成舊到新
    names = _station_names(session, scope.batch)
    site = dt.timezone(dt.timedelta(hours=SITE_UTC_OFFSET_HOURS))
    offset = f"UTC{SITE_UTC_OFFSET_HOURS:+g}"

    wb = Workbook()
    ws = wb.active
    ws.title = "點檢紀錄"
    headers = [
        "日期", "班別", f"點檢時間（{offset}）", "站別", "設備代碼", "KPOV 編號",
        "點檢內容", "點檢結果", "備註", "照片", "原圖連結",
    ]
    widths = [12, 8, 20, 18, 13, 12, 36, 10, 20, 35, 14]
    if truncated:
        ws.append([f"僅匯出最新 {EXPORT_MAX_ROWS} 筆，請縮小時間範圍後再匯出其餘紀錄"])
        ws.cell(1, 1).font = Font(bold=True, color="C00000")
    ws.append(headers)
    header_row = ws.max_row
    for col, width in enumerate(widths, start=1):
        cell = ws.cell(header_row, col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F5C7A")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = f"A{header_row + 1}"  # 用座標字串：ws.cell() 會建出空列，讓 append 跳過一列

    middle = Alignment(vertical="center", wrap_text=True)
    for r in records:
        at = utc(r.inspected_at)
        shift = shift_of(at)
        ws.append(
            [
                shift["date"].isoformat(),
                shift["name"],
                at.astimezone(site).strftime("%Y-%m-%d %H:%M:%S"),
                names.get(r.equipment_code, r.equipment_code),
                r.equipment_code,
                r.kpov_no,
                r.check_content,
                "正常" if r.status == "ok" else "異常",
                r.note,
                None,
                None,
            ]
        )
        row = ws.max_row
        for col in range(1, len(headers) + 1):
            ws.cell(row, col).alignment = middle
        if r.status != "ok":
            ws.cell(row, 8).font = Font(bold=True, color="C00000")

        image = _thumbnail(_photo_bytes(r.photo_url))
        if image is None:
            ws.cell(row, 10).value = "照片遺失"
            ws.row_dimensions[row].height = 30
        else:
            ws.add_image(image, ws.cell(row, 10).coordinate)
            ws.row_dimensions[row].height = image.height * 0.75 + 6  # px -> pt

        link = ws.cell(row, 11)
        if base_url:
            link.value = "開啟原圖"
            link.hyperlink = base_url.rstrip("/") + r.photo_url
            link.font = Font(color="0563C1", underline="single")
        else:
            link.value = r.photo_url

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    filename = f"點檢紀錄_{dt.datetime.now(site):%Y%m%d_%H%M%S}.xlsx"
    headers_out = {
        # 中文檔名：filename* 為 RFC 5987 編碼，filename 給不支援的舊瀏覽器
        "Content-Disposition": f"attachment; filename=\"check_inspections.xlsx\"; filename*=UTF-8''{quote(filename)}",
        "Access-Control-Expose-Headers": "X-Export-Truncated",
    }
    if truncated:
        headers_out["X-Export-Truncated"] = "1"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers_out,
    )
