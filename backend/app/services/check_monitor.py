"""Level 3 高風險項點檢監控 — 點檢項目（fact_check_item）× 點檢紀錄。

點檢紀錄有兩個來源，一律視為同一種點檢：
  - ar_inspection：AR 掃 marker 後逐項按正常／異常
  - check_photo_inspection：免掃碼，拍照上傳即算點檢

點檢項目每次匯入都重建，AR 點檢紀錄則持續累積，兩者以
(設備代碼, KPOV 編號, 點檢內容) 自然鍵對應，不建外鍵（理由同 ArDevice.equipment_code）。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import CHECK_SHIFTS, SITE_UTC_OFFSET_HOURS
from ..models import ArInspection, CheckPhotoInspection, FactCheckItem

STATUS_OK = "ok"  # 最近一次正常，且未超過點檢間隔
STATUS_WARN = "warn"  # 最近一次點檢結果異常
STATUS_OVERDUE = "overdue"  # 最近一次正常，但已超過點檢間隔
STATUS_NEVER = "never"  # 從未點檢


# 班內時段狀態
SLOT_OK = "ok"  # 該時段有點檢且結果正常
SLOT_WARN = "warn"  # 該時段有點檢但結果異常（算完成，標紅）
SLOT_MISSED = "missed"  # 時段已過卻沒點檢
SLOT_CURRENT = "current"  # 進行中的時段，尚未點檢
SLOT_UPCOMING = "upcoming"  # 尚未到的時段


def current_shift(now: dt.datetime) -> dict:
    """依廠區當地時間找出「目前或剛結束」的班別。

    兩班之間的空檔（18–20、06–08）顯示剛結束的那一班，讓交接時還看得到結果。
    回傳的 start / end 為 UTC。
    """
    site = dt.timezone(dt.timedelta(hours=SITE_UTC_OFFSET_HOURS))
    local_now = utc(now).astimezone(site)
    best: tuple[dt.datetime, str, int] | None = None
    for day_offset in (-1, 0):
        day = local_now.date() + dt.timedelta(days=day_offset)
        for name, hour, length in CHECK_SHIFTS:
            start = dt.datetime.combine(day, dt.time(hour), tzinfo=site)
            if start <= local_now and (best is None or start > best[0]):
                best = (start, name, length)
    start, name, length = best  # type: ignore[misc]
    end = start + dt.timedelta(hours=length)
    return {
        "name": name,
        "start": start.astimezone(dt.timezone.utc),
        "end": end.astimezone(dt.timezone.utc),
        "label": f"{name} {start:%H:%M}–{end:%H:%M}",
        "ended": local_now >= end,
    }


# 匯出報表用的班別名稱（使用者慣稱白班）；首頁仍沿用 CHECK_SHIFTS 的「日班」
EXPORT_SHIFT_NAMES = {"日班": "白班"}


def shift_of(at: dt.datetime) -> dict:
    """某筆點檢屬於哪一班：與 current_shift 同一套規則，空檔歸入剛結束的班。

    date 為開班當天的廠區日期——夜班跨午夜時（例：10/16 02:00）記為前一天（10/15）夜班。
    """
    shift = current_shift(at)
    site = dt.timezone(dt.timedelta(hours=SITE_UTC_OFFSET_HOURS))
    return {
        "name": EXPORT_SHIFT_NAMES.get(shift["name"], shift["name"]),
        "date": shift["start"].astimezone(site).date(),
    }


Record = ArInspection | CheckPhotoInspection


def _slots(records: list[Record], shift: dict, interval: dt.timedelta, now: dt.datetime) -> list[dict]:
    """把班別切成數個點檢時段，每段取該段內最後一次點檢的結果。

    同一時段點檢多次只算一格，避免短時間內連按灌高完成度。
    """
    count = max(1, round((shift["end"] - shift["start"]) / interval))
    slots = []
    for i in range(count):
        start = shift["start"] + interval * i
        end = start + interval
        # records 已依時間新到舊排序，第一筆落在區間內的就是最後一次
        hit = next((r for r in records if start <= utc(r.inspected_at) < end), None)
        if hit is not None:
            state = SLOT_WARN if hit.status == "warn" else SLOT_OK
        elif end <= now:
            state = SLOT_MISSED
        elif start <= now:
            state = SLOT_CURRENT
        else:
            state = SLOT_UPCOMING
        slots.append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "state": state,
                "inspectedAt": utc(hit.inspected_at).isoformat() if hit else None,
                "photoUrl": getattr(hit, "photo_url", None) if hit else None,
            }
        )
    return slots


def utc(value: dt.datetime) -> dt.datetime:
    # SQLite 讀回的 datetime 不帶時區
    return value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value.astimezone(dt.timezone.utc)


def item_key(equipment_code: str | None, kpov_no: str | None, check_content: str | None) -> tuple:
    return (equipment_code or "", kpov_no or "", (check_content or "").strip())


def check_items(session: Session, batch_id: int, equipment_codes: set[str] | None = None) -> list[FactCheckItem]:
    query = select(FactCheckItem).where(FactCheckItem.batch_id == batch_id)
    if equipment_codes is not None:
        query = query.where(FactCheckItem.equipment_code.in_(equipment_codes))
    items = session.scalars(query.order_by(FactCheckItem.id)).all()
    # 來源表同一項目可能重複列出（例：K00048 + 同一點檢內容出現兩次），只保留第一筆
    seen: set[tuple] = set()
    unique = []
    for item in items:
        key = item_key(item.equipment_code, item.kpov_no, item.check_content)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def monitor_rows(
    session: Session,
    items: list[FactCheckItem],
    now: dt.datetime | None = None,
) -> list[dict]:
    now = utc(now or dt.datetime.now(dt.timezone.utc))
    codes = {i.equipment_code for i in items if i.equipment_code}
    history: dict[tuple, list[Record]] = {}
    if codes:
        records: list[Record] = [
            *session.scalars(
                select(ArInspection).where(
                    ArInspection.equipment_code.in_(codes), ArInspection.check_content.is_not(None)
                )
            ),
            *session.scalars(select(CheckPhotoInspection).where(CheckPhotoInspection.equipment_code.in_(codes))),
        ]
        records.sort(key=lambda r: utc(r.inspected_at), reverse=True)
        for record in records:
            history.setdefault(item_key(record.equipment_code, record.kpov_no, record.check_content), []).append(
                record
            )

    shift = current_shift(now)
    rows = []
    for item in items:
        interval = dt.timedelta(hours=float(item.interval_hours or 2))
        records = history.get(item_key(item.equipment_code, item.kpov_no, item.check_content), [])
        last = records[0] if records else None
        last_at = utc(last.inspected_at) if last else None
        if last is None:
            status = STATUS_NEVER
        elif last.status == "warn":
            status = STATUS_WARN
        elif now - last_at > interval:
            status = STATUS_OVERDUE
        else:
            status = STATUS_OK
        slots = _slots(records, shift, interval, now)
        done = sum(1 for slot in slots if slot["state"] in (SLOT_OK, SLOT_WARN))
        rows.append(
            {
                "id": item.id,
                "station": item.station,
                "attribute": item.attribute1,
                "equipmentCode": item.equipment_code,
                "kpovNo": item.kpov_no,
                "kpovName": item.kpov_name,
                "level": item.level_source,
                "checkContent": item.check_content,
                "frequency": item.frequency,
                "intervalHours": float(item.interval_hours or 2),
                "status": status,
                "lastResult": last.status if last else None,
                "lastInspectedAt": last_at.isoformat() if last_at else None,
                "lastPhotoUrl": getattr(last, "photo_url", None) if last else None,
                "lastNote": getattr(last, "note", None) if last else None,
                "nextDueAt": (last_at + interval).isoformat() if last_at else None,
                "overdue": bool(last_at and now - last_at > interval),
                "slots": slots,
                "completed": done,
                "progress": round(done / len(slots) * 100),
                "count24h": sum(1 for r in records if now - utc(r.inspected_at) <= dt.timedelta(hours=24)),
            }
        )
    return rows


def shift_payload(now: dt.datetime | None = None) -> dict:
    shift = current_shift(utc(now or dt.datetime.now(dt.timezone.utc)))
    return {**shift, "start": shift["start"].isoformat(), "end": shift["end"].isoformat()}


def summarize_rows(rows: list[dict]) -> dict:
    summary = {STATUS_OK: 0, STATUS_WARN: 0, STATUS_OVERDUE: 0, STATUS_NEVER: 0}
    for row in rows:
        summary[row["status"]] += 1
    summary["total"] = len(rows)
    slots = [slot for row in rows for slot in row["slots"]]
    summary["progress"] = round(sum(r["progress"] for r in rows) / len(rows)) if rows else 0
    summary["missedSlots"] = sum(1 for s in slots if s["state"] == SLOT_MISSED)
    summary["warnSlots"] = sum(1 for s in slots if s["state"] == SLOT_WARN)
    return summary
