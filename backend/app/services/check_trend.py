"""點檢看板的趨勢與分布（spec §18）。

- 每日異常次數：拍照點檢結果為異常的次數，依所屬班別的開班日（夜班跨午夜記為開班當天）。
- 每日漏點檢數：各點檢項目在該日各班的點檢時段（與點檢監控相同，見 check_monitor._slots）中，
  時段已結束卻沒有點檢的格數。只從這條線第一筆拍照點檢所在的班開始算，避免系統啟用前的日子全算漏點檢。
  v2.12：另有起算日（CHECK_MISSED_FROM，之前為試運行）；不生產的星期（CHECK_OFF_WEEKDAYS，預設週日）
  與整班沒有任何點檢紀錄的班別（視為沒開線）都不算漏點檢。
- KPIV 點檢內容分布：期間內各點檢項目的異常次數與佔全部點檢的比例（前端只畫有異常的項目）。
- 最高權限管理者「匯入歷史點檢數量」的資料（spec §19）也算進每日異常次數與分布；
  v2.11 起也算進點檢時段：時段內有匯入的點檢就不算漏點檢（依設備代碼＋點檢內容對回點檢項目，對不到的不算）。
  起算點仍是第一筆拍照點檢所在的班，匯入的舊資料不會讓起算點提前。
- v2.15：異常次數、分布與站別卡片也從起算日算（counts_on）；不生產的星期可由看板勾選是否排除（預設排除），
  排除時異常次數與漏點檢都不算那幾天。
"""
from __future__ import annotations

import datetime as dt

from ..config import CHECK_MISSED_FROM, CHECK_OFF_WEEKDAYS, CHECK_SHIFTS, SITE_UTC_OFFSET_HOURS
from ..models import CheckCountImport, CheckPhotoInspection, FactCheckItem
from .check_monitor import SLOT_MISSED, _slots, current_shift, item_key, shift_of, utc

SITE_TZ = dt.timezone(dt.timedelta(hours=SITE_UTC_OFFSET_HOURS))


def _shifts_of_day(day: dt.date) -> list[dict]:
    shifts = []
    for name, hour, length in CHECK_SHIFTS:
        start = dt.datetime.combine(day, dt.time(hour), tzinfo=SITE_TZ)
        shifts.append({"name": name, "start": start.astimezone(dt.timezone.utc),
                       "end": (start + dt.timedelta(hours=length)).astimezone(dt.timezone.utc)})
    return shifts


def counts_on(at: dt.datetime, exclude_off_days: bool = True) -> bool:
    """這筆點檢（拍照或匯入）是否算進點檢看板：所屬班的開班日不早於起算日，且（排除時）不是不生產的星期。"""
    day = shift_of(utc(at))["date"]
    return day >= CHECK_MISSED_FROM and not (exclude_off_days and day.weekday() in CHECK_OFF_WEEKDAYS)


def check_trend(
    items: list[FactCheckItem],
    records: list[CheckPhotoInspection],
    days: int,
    now: dt.datetime | None = None,
    imported: list[CheckCountImport] = (),
    exclude_off_days: bool = True,
) -> dict:
    """items：目前的點檢項目；records：這條線的拍照點檢紀錄（任意順序）；imported：這條線匯入的歷史點檢數量。"""
    now = utc(now or dt.datetime.now(dt.timezone.utc))
    today = now.astimezone(SITE_TZ).date()
    first_day = today - dt.timedelta(days=days - 1)
    since = _shifts_of_day(first_day)[0]["start"]

    records = sorted(records, key=lambda r: utc(r.inspected_at), reverse=True)
    # 匯入列沒有 KPOV 編號：依設備代碼＋點檢內容對回目前的點檢項目，對不到的另列一項
    by_content = {(i.equipment_code or "", (i.check_content or "").strip()): i for i in items}

    def _key(r) -> tuple:
        if getattr(r, "kpov_no", None) is None:
            item = by_content.get((r.equipment_code or "", (r.check_content or "").strip()))
            if item is not None:
                return item_key(item.equipment_code, item.kpov_no, item.check_content)
        return item_key(r.equipment_code, getattr(r, "kpov_no", None), r.check_content)

    # 點檢時段：拍照點檢＋匯入的點檢（_slots 需要新到舊）
    by_item: dict[tuple, list] = {}
    for r in sorted([*records, *imported], key=lambda r: utc(r.inspected_at), reverse=True):
        by_item.setdefault(_key(r), []).append(r)
    # 漏點檢從第一筆拍照點檢所在的班開始算，且不早於起算日
    tracking_from = current_shift(utc(records[-1].inspected_at))["start"] if records else None
    if tracking_from is not None:
        tracking_from = max(tracking_from, _shifts_of_day(CHECK_MISSED_FROM)[0]["start"])
    # 有點檢紀錄（拍照或匯入，不限目前點檢項目）的班別；整班都沒有紀錄視為沒開線
    worked_shifts = {current_shift(utc(r.inspected_at))["start"] for r in [*records, *imported]}

    series = []
    for offset in range(days):
        day = first_day + dt.timedelta(days=offset)
        missed = expected = 0
        for shift in _shifts_of_day(day):
            if shift["start"] > now or tracking_from is None or shift["start"] < tracking_from:
                continue
            if (exclude_off_days and day.weekday() in CHECK_OFF_WEEKDAYS) or shift["start"] not in worked_shifts:
                continue
            for item in items:
                interval = dt.timedelta(hours=float(item.interval_hours or 2))
                slots = _slots(by_item.get(item_key(item.equipment_code, item.kpov_no, item.check_content), []),
                               shift, interval, now)
                expected += len(slots)
                missed += sum(1 for s in slots if s["state"] == SLOT_MISSED)
        series.append({"date": day.isoformat(), "warn": 0, "inspected": 0, "missed": missed, "expected": expected})

    index = {row["date"]: row for row in series}
    in_range = [
        r for r in [*records, *imported]
        if since <= utc(r.inspected_at) <= now and counts_on(r.inspected_at, exclude_off_days)
    ]
    for r in in_range:
        row = index.get(shift_of(utc(r.inspected_at))["date"].isoformat())
        if row is None:  # 期間第一天 08:00 前的紀錄屬於前一天夜班
            continue
        row["inspected"] += 1
        row["warn"] += r.status == "warn"

    # KPIV 點檢內容分布：以點檢項目為單位
    meta = {item_key(i.equipment_code, i.kpov_no, i.check_content): i for i in items}
    dist: dict[tuple, dict] = {}
    for r in in_range:
        key = _key(r)
        item = meta.get(key)
        entry = dist.setdefault(key, {
            "station": item.station if item else (getattr(r, "station", None) or r.equipment_code),
            "equipmentCode": r.equipment_code,
            "kpovNo": item.kpov_no if item else getattr(r, "kpov_no", None),
            "checkContent": r.check_content,
            "kpivControlLevel": item.kpiv_control_level if item else None,
            "total": 0,
            "warn": 0,
        })
        entry["total"] += 1
        entry["warn"] += r.status == "warn"
    total = len(in_range)
    warn = sum(1 for r in in_range if r.status == "warn")
    imported_ids = {id(r) for r in imported}
    imported_in_range = sum(1 for r in in_range if id(r) in imported_ids)
    return {
        "days": days,
        "since": since.isoformat(),
        "countFrom": CHECK_MISSED_FROM.isoformat(),
        "excludeOffDays": exclude_off_days,
        "trackingFrom": tracking_from.isoformat() if tracking_from else None,
        "series": series,
        "items": sorted(dist.values(), key=lambda e: (-e["warn"], -e["total"], e["station"] or "")),
        "totals": {"total": total, "ok": total - warn, "warn": warn,
                   "missed": sum(row["missed"] for row in series), "imported": imported_in_range},
    }
