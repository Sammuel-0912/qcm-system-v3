"""匯入歷史點檢數量（spec §19）：解析點檢紀錄 Excel，只取卡片計數需要的欄位。

依表頭名稱找欄位（不看順序），本系統「匯出紀錄（含照片）」與舊版（v2）匯出的檔案都能用。
點檢時間一律視為廠區當地時間，轉成 UTC。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from openpyxl import load_workbook

from .due import SITE_TZ

HEADER_SCAN_ROWS = 3  # 本系統匯出超過上限時，第 1 列是提醒文字
REQUIRED = {
    "equipment_code": ("設備代碼",),
    "status": ("點檢結果",),
    "inspected_at": ("點檢時間（UTC+8）", "點檢時間"),
}
OPTIONAL = {
    "station": ("站別",),
    "check_content": ("點檢內容",),
}
STATUS_VALUES = {"正常": "ok", "異常": "warn", "ok": "ok", "warn": "warn"}
MAX_REASONS = 5


class CountImportError(ValueError):
    pass


@dataclass
class ParsedRow:
    equipment_code: str
    station: str | None
    check_content: str
    status: str
    inspected_at: dt.datetime  # UTC


@dataclass
class ParseResult:
    rows: list[ParsedRow] = field(default_factory=list)
    invalid: int = 0
    reasons: list[str] = field(default_factory=list)

    def skip(self, row_no: int, reason: str) -> None:
        self.invalid += 1
        if len(self.reasons) < MAX_REASONS:
            self.reasons.append(f"第 {row_no} 列：{reason}")


def _text(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() == "null" else text


def _site_time(value) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        local = value
    else:
        text = _text(value).replace("/", "-").replace("T", " ").rstrip("Z")
        if not text:
            return None
        try:
            local = dt.datetime.fromisoformat(text)
        except ValueError:
            return None
    if local.tzinfo is None:
        local = local.replace(tzinfo=SITE_TZ)
    return local.astimezone(dt.timezone.utc).replace(microsecond=0)


def _find_header(rows: list[tuple]) -> tuple[int, dict[str, int]]:
    for index, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        names = {_text(v): i for i, v in enumerate(row) if _text(v)}
        columns = {}
        for key, aliases in {**REQUIRED, **OPTIONAL}.items():
            hit = next((names[a] for a in aliases if a in names), None)
            if hit is not None:
                columns[key] = hit
        if all(k in columns for k in REQUIRED):
            return index, columns
    need = "、".join(aliases[0] if len(aliases) == 1 else "／".join(aliases) for aliases in REQUIRED.values())
    raise CountImportError(f"找不到表頭：前 {HEADER_SCAN_ROWS} 列內需要有 {need} 欄。可直接使用點檢看板「匯出紀錄（含照片）」的檔案")


def parse_count_workbook(path: str) -> ParseResult:
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # 不是 Excel 或檔案損毀
        raise CountImportError(f"無法讀取 Excel：{exc}") from exc
    try:
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
    finally:
        wb.close()
    header, columns = _find_header(rows)
    result = ParseResult()
    seen: set[tuple] = set()

    def cell(row: tuple, key: str):
        i = columns.get(key)
        return row[i] if i is not None and i < len(row) else None

    for offset, row in enumerate(rows[header + 1 :], start=header + 2):
        if not any(_text(v) for v in row):
            continue
        code = _text(cell(row, "equipment_code"))
        status = STATUS_VALUES.get(_text(cell(row, "status")).lower())
        at = _site_time(cell(row, "inspected_at"))
        if not code:
            result.skip(offset, "沒有設備代碼")
            continue
        if status is None:
            result.skip(offset, f"點檢結果「{_text(cell(row, 'status'))}」不是正常或異常")
            continue
        if at is None:
            result.skip(offset, f"點檢時間「{_text(cell(row, 'inspected_at'))}」無法辨識")
            continue
        parsed = ParsedRow(code, _text(cell(row, "station")) or None, _text(cell(row, "check_content")), status, at)
        key = (parsed.equipment_code, parsed.check_content, parsed.inspected_at)
        if key in seen:  # 同一份檔案內重複的列只算一次
            continue
        seen.add(key)
        result.rows.append(parsed)
    return result
