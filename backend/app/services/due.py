"""完成期限與清單篩選（spec §17）：製程風險管理（修護報表）與客訴案件管理共用。

逾期一律以 8D 的「預計完成時間」對「實際完成時間」判定：
- 有實際完成：實際晚於預計＝逾期，天數＝實際 − 預計；不晚＝準時完成
- 沒有實際完成：預計已過（早於今天）＝逾期，天數＝今天 − 預計；否則＝預計完成（未到期）
- 沒有預計完成：不列入
日期一律換成廠區當地日期再比，天數為日曆天。
"""
from __future__ import annotations

import datetime as dt

from ..config import SITE_UTC_OFFSET_HOURS

SITE_TZ = dt.timezone(dt.timedelta(hours=SITE_UTC_OFFSET_HOURS))

DUE_PLANNED = "planned"  # 尚未完成、還沒到期
DUE_ONTIME = "ontime"  # 已準時完成（不放進圓餅）
DUE_OVERDUE = "overdue"
# 逾期天數分組：1–6 天、7–14 天、15 天以上
BUCKET_LT7 = "lt7"
BUCKET_7_14 = "d7_14"
BUCKET_GT14 = "gt14"
DUE_FILTERS = (DUE_PLANNED, DUE_ONTIME, DUE_OVERDUE, BUCKET_LT7, BUCKET_7_14, BUCKET_GT14)


def site_date(value: dt.datetime | None) -> dt.date | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(SITE_TZ).date()


def site_today(now: dt.datetime | None = None) -> dt.date:
    return (now or dt.datetime.now(dt.timezone.utc)).astimezone(SITE_TZ).date()


def overdue_bucket(days: int) -> str:
    if days < 7:
        return BUCKET_LT7
    if days <= 14:
        return BUCKET_7_14
    return BUCKET_GT14


def due_status(planned: dt.datetime | None, done: dt.datetime | None, today: dt.date) -> dict | None:
    """→ {status, overdueDays, bucket, plannedAt, doneAt}；沒有預計完成時為 None。"""
    planned_d = site_date(planned)
    if planned_d is None:
        return None
    done_d = site_date(done)
    days = ((done_d or today) - planned_d).days
    if done_d is not None:
        status = DUE_OVERDUE if days > 0 else DUE_ONTIME
    else:
        status = DUE_OVERDUE if days > 0 else DUE_PLANNED
    overdue = status == DUE_OVERDUE
    return {
        "status": status,
        "overdueDays": days if overdue else 0,
        "bucket": overdue_bucket(days) if overdue else None,
        "plannedAt": planned_d.isoformat(),
        "doneAt": done_d.isoformat() if done_d else None,
    }


def due_matches(due: dict | None, wanted: str | None) -> bool:
    if not wanted:
        return True
    if due is None:
        return False
    if wanted in (DUE_PLANNED, DUE_ONTIME, DUE_OVERDUE):
        return due["status"] == wanted
    return due["bucket"] == wanted


def due_stats(dues: list[dict | None]) -> dict:
    """圓餅圖：預計完成（未到期）與逾期三組；準時完成與沒有預計日期的不列入。"""
    stats = {DUE_PLANNED: 0, BUCKET_LT7: 0, BUCKET_7_14: 0, BUCKET_GT14: 0}
    for due in dues:
        if due is None:
            continue
        if due["status"] == DUE_PLANNED:
            stats[DUE_PLANNED] += 1
        elif due["status"] == DUE_OVERDUE:
            stats[due["bucket"]] += 1
    stats[DUE_OVERDUE] = stats[BUCKET_LT7] + stats[BUCKET_7_14] + stats[BUCKET_GT14]
    return stats


def parse_day(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


def in_day_range(value: dt.datetime | None, start: dt.date | None, end: dt.date | None) -> bool:
    """起訖皆含；有給範圍時，沒有日期的資料不符合。"""
    if start is None and end is None:
        return True
    day = site_date(value)
    if day is None:
        return False
    return (start is None or day >= start) and (end is None or day <= end)


def options(values) -> list[str]:
    return sorted({v for v in values if v})
