"""AR 設備點檢 API — 整合自 webXR-test，見 ar-integration-spec.md §5。

原專案用原生 sqlite3 直接拼 SQL，這裡改寫為 SQLAlchemy 以共用品控力的
連線、交易與資料庫方言處理（SQLite 開發、PostgreSQL 正式）。

移植時一併修掉原版的三個問題：
  1. `GET /results` 原本回傳「以 UUID 為鍵的物件」，不利於排序與分頁，改回陣列。
  2. `/export` 原本把 temp_report.xlsx 寫到行程的工作目錄且從不刪除，
     併發匯出會互相覆寫。改為在記憶體產生後直接串流。
  3. 啟動時塞三筆 UPS 示範設備。整合版不塞——示範資料混進正式庫很難分辨。
"""
from __future__ import annotations

import datetime as dt
import io
import os
import shutil
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ...config import AR_UPLOAD_DIR, AR_UPLOAD_URL_PREFIX
from ...db import get_session
from ...models import ArDevice, ArInspection, DimEquipment, FactKpov
from ...services.lifecycle import build_states
from ...services.query import active_batch

router = APIRouter(prefix="/api/ar", tags=["ar"])

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_MARKER_ID = 63


# --------------------------------------------------------------------------- schema


class DeviceCreate(BaseModel):
    marker_id: int = Field(ge=0, le=MAX_MARKER_ID)
    name: str
    description: Optional[str] = None
    work_instruction: Optional[str] = None
    image_url: Optional[str] = None
    equipment_code: Optional[str] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    work_instruction: Optional[str] = None
    image_url: Optional[str] = None
    equipment_code: Optional[str] = None


class InspectionCreate(BaseModel):
    marker_id: int = Field(ge=0, le=MAX_MARKER_ID)
    status: str = Field(pattern="^(ok|warn)$")


def _device_out(d: ArDevice) -> dict:
    return {
        "markerId": d.marker_id,
        "name": d.name,
        "description": d.description,
        "workInstruction": d.work_instruction,
        "imageUrl": d.image_url,
        "equipmentCode": d.equipment_code,
        "createdAt": d.created_at.isoformat() if d.created_at else None,
    }


def _get_device(session: Session, marker_id: int) -> ArDevice:
    device = session.get(ArDevice, marker_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"找不到 marker {marker_id} 對應的設備")
    return device


# --------------------------------------------------------------------------- 設備


@router.get("/devices")
def list_devices(session: Session = Depends(get_session)):
    devices = session.scalars(select(ArDevice).order_by(ArDevice.marker_id)).all()
    return [_device_out(d) for d in devices]


@router.get("/devices/{marker_id}")
def get_device(marker_id: int, session: Session = Depends(get_session)):
    return _device_out(_get_device(session, marker_id))


@router.post("/devices", status_code=201)
def create_device(data: DeviceCreate, session: Session = Depends(get_session)):
    if session.get(ArDevice, data.marker_id) is not None:
        raise HTTPException(status_code=409, detail=f"marker {data.marker_id} 已存在，請改用 PATCH 更新")
    device = ArDevice(
        marker_id=data.marker_id,
        name=data.name,
        description=data.description,
        work_instruction=data.work_instruction,
        image_url=data.image_url,
        equipment_code=data.equipment_code,
    )
    session.add(device)
    session.commit()
    return _device_out(device)


@router.patch("/devices/{marker_id}")
def update_device(marker_id: int, data: DeviceUpdate, session: Session = Depends(get_session)):
    device = _get_device(session, marker_id)
    patch = data.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="請至少提供一個要更新的欄位")
    for key, value in patch.items():
        setattr(device, key, value)
    session.commit()
    return _device_out(device)


@router.delete("/devices/{marker_id}")
def delete_device(marker_id: int, session: Session = Depends(get_session)):
    device = _get_device(session, marker_id)
    session.delete(device)  # 點檢紀錄隨 cascade 一併刪除
    session.commit()
    return {"markerId": marker_id, "deleted": True}


@router.post("/devices/{marker_id}/image")
def upload_device_image(
    marker_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    device = _get_device(session, marker_id)

    ext = os.path.splitext(file.filename or "image.jpg")[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=422,
            detail=f"不支援的圖片格式 {ext or '(無副檔名)'}；可用：{', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}",
        )

    filename = f"device_{marker_id}_{uuid.uuid4().hex[:8]}{ext}"
    AR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with (AR_UPLOAD_DIR / filename).open("wb") as fh:
        shutil.copyfileobj(file.file, fh)

    device.image_url = f"{AR_UPLOAD_URL_PREFIX}/{filename}"
    session.commit()
    return {"markerId": marker_id, "imageUrl": device.image_url}


# --------------------------------------------------------------------------- 點檢


@router.post("/inspections", status_code=201)
def create_inspection(data: InspectionCreate, session: Session = Depends(get_session)):
    _get_device(session, data.marker_id)  # 不存在就 404，避免孤兒紀錄
    record = ArInspection(marker_id=data.marker_id, status=data.status)
    session.add(record)
    session.commit()
    return {
        "id": record.id,
        "markerId": record.marker_id,
        "status": record.status,
        "inspectedAt": record.inspected_at.isoformat(),
    }


@router.get("/results")
def list_results(
    marker_id: Optional[int] = Query(None, alias="markerId"),
    start: Optional[dt.datetime] = None,
    end: Optional[dt.datetime] = None,
    limit: int = Query(200, le=1000),
    session: Session = Depends(get_session),
):
    stmt = (
        select(ArInspection, ArDevice.name)
        .join(ArDevice, ArDevice.marker_id == ArInspection.marker_id, isouter=True)
        .order_by(ArInspection.inspected_at.desc(), ArInspection.id.desc())
    )
    if marker_id is not None:
        stmt = stmt.where(ArInspection.marker_id == marker_id)
    if start:
        stmt = stmt.where(ArInspection.inspected_at >= start)
    if end:
        stmt = stmt.where(ArInspection.inspected_at <= end)

    rows = session.execute(stmt.limit(limit)).all()
    return {
        "total": len(rows),
        "items": [
            {
                "id": rec.id,
                "markerId": rec.marker_id,
                "deviceName": name or "（已刪除）",
                "status": rec.status,
                "inspectedAt": rec.inspected_at.isoformat(),
            }
            for rec, name in rows
        ],
    }


@router.delete("/results/{record_id}")
def delete_result(record_id: int, session: Session = Depends(get_session)):
    record = session.get(ArInspection, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="找不到該筆點檢紀錄")
    session.delete(record)
    session.commit()
    return {"id": record_id, "deleted": True}


def _stats_rows(session: Session, marker_id: Optional[int] = None) -> list[dict]:
    stmt = (
        select(
            ArInspection.marker_id,
            func.count().label("total"),
            func.sum(case((ArInspection.status == "ok", 1), else_=0)).label("ok_count"),
            func.sum(case((ArInspection.status == "warn", 1), else_=0)).label("warn_count"),
        )
        .group_by(ArInspection.marker_id)
        .order_by(ArInspection.marker_id)
    )
    if marker_id is not None:
        stmt = stmt.where(ArInspection.marker_id == marker_id)

    names = {
        d.marker_id: d.name for d in session.scalars(select(ArDevice)).all()
    }
    out = []
    for mid, total, ok_count, warn_count in session.execute(stmt).all():
        ok_count = int(ok_count or 0)
        out.append(
            {
                "markerId": mid,
                "deviceName": names.get(mid, "（已刪除）"),
                "total": int(total),
                "okCount": ok_count,
                "warnCount": int(warn_count or 0),
                "okRate": round(ok_count / total, 4) if total else 0.0,
            }
        )
    return out


@router.get("/stats")
def get_stats(session: Session = Depends(get_session)):
    return _stats_rows(session)


@router.get("/stats/{marker_id}")
def get_stats_by_device(marker_id: int, session: Session = Depends(get_session)):
    rows = _stats_rows(session, marker_id)
    if not rows:
        raise HTTPException(status_code=404, detail=f"marker {marker_id} 尚無點檢紀錄")
    return rows[0]


# --------------------------------------------------------------------------- 品控力橋接


@router.get("/devices/{marker_id}/quality")
def device_quality(marker_id: int, session: Session = Depends(get_session)):
    """該 AR 設備在品控力系統的現況（ar-integration-spec.md REQ-DATA-04）。

    以 equipment_code 對到「當前 active 批次」的 dim_equipment / fact_kpov。
    刻意不用外鍵：dim_equipment 的主鍵含 batch_id，綁外鍵會在下次匯入時斷裂。
    """
    device = _get_device(session, marker_id)
    if not device.equipment_code:
        return {"linked": False, "reason": "此設備尚未綁定設備代碼"}

    batch = active_batch(session)
    if batch is None:
        return {"linked": False, "equipmentCode": device.equipment_code, "reason": "尚未匯入品控力資料"}

    in_batch = session.scalar(
        select(func.count())
        .select_from(DimEquipment)
        .where(
            DimEquipment.batch_id == batch.id,
            DimEquipment.equipment_code == device.equipment_code,
        )
    )
    if not in_batch:
        return {
            "linked": False,
            "equipmentCode": device.equipment_code,
            # REQ-DATA-05：找不到要講清楚，不可靜默忽略
            "reason": f"設備代碼 {device.equipment_code} 不在目前匯入批次中",
        }

    states = [
        s
        for s in build_states(session, batch.id)
        if s.kpov.equipment_code == device.equipment_code
    ]
    counts = {str(i): 0 for i in range(4)}
    worst: int | None = None
    for state in states:
        level = state.level_current
        if level is None:
            continue
        counts[str(level)] += 1
        if worst is None or level > worst:
            worst = level

    recent = [
        {
            "kpovNo": s.kpov.kpov_no,
            "kpovName": s.kpov.kpov_name,
            "levelBaseline": s.level_baseline,
            "levelCurrent": s.level_current,
            "transition": s.last_event.transition if s.last_event else None,
            "effectiveAt": s.last_event.effective_at.isoformat() if s.last_event else None,
        }
        for s in states
        if s.deviates_from_baseline
    ]

    return {
        "linked": True,
        "equipmentCode": device.equipment_code,
        "station": states[0].kpov.station if states else None,
        "kpovCount": len(states),
        "levelCounts": counts,
        "worstLevel": worst,
        "escalatedOpen": sum(1 for s in states if s.is_escalated_open),
        "deviations": recent,
        "batch": {"id": batch.id, "filename": batch.filename},
    }


@router.get("/equipment-options")
def equipment_options(session: Session = Depends(get_session)):
    """設備管理頁的設備代碼下拉（REQ-DATA-03）：只列當前 active 批次有 KPOV 的設備。"""
    batch = active_batch(session)
    if batch is None:
        return {"batch": None, "options": []}

    rows = session.execute(
        select(FactKpov.equipment_code, FactKpov.station, func.count().label("kpov_count"))
        .where(FactKpov.batch_id == batch.id, FactKpov.equipment_code.is_not(None))
        .group_by(FactKpov.equipment_code, FactKpov.station)
        .order_by(FactKpov.station)
    ).all()
    return {
        "batch": {"id": batch.id, "filename": batch.filename},
        "options": [
            {"equipmentCode": code, "station": station, "kpovCount": int(n)}
            for code, station, n in rows
        ],
    }


# --------------------------------------------------------------------------- 匯出


@router.get("/export")
def export_report(session: Session = Depends(get_session)):
    """點檢紀錄匯出 Excel。

    原版把檔案寫到行程工作目錄再回傳，檔案不會清掉、併發匯出還會互相覆寫。
    這裡改為在記憶體組出活頁簿直接串流。
    """
    from openpyxl import Workbook

    rows = session.execute(
        select(ArInspection, ArDevice.name)
        .join(ArDevice, ArDevice.marker_id == ArInspection.marker_id, isouter=True)
        .order_by(ArInspection.inspected_at.desc())
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="目前沒有點檢紀錄可匯出")

    wb = Workbook()
    ws = wb.active
    ws.title = "點檢紀錄"
    ws.append(["紀錄編號", "Marker ID", "設備名稱", "狀態", "點檢時間"])
    for rec, name in rows:
        ws.append(
            [
                rec.id,
                rec.marker_id,
                name or "（已刪除）",
                "正常" if rec.status == "ok" else "異常",
                rec.inspected_at.strftime("%Y-%m-%d %H:%M:%S"),
            ]
        )

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="ar_inspection_{stamp}.xlsx"'},
    )
