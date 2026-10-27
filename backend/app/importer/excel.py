"""Excel 匯入 — spec.md §6。

匯入順序（有相依，REQ-IMP-07）：
    dim_detection_method -> dim_equipment / dim_error_code -> fact_kpov
    -> fact_repair -> fact_level_event
整個流程為單一交易，失敗不留半套資料（REQ-IMP-09）。

只有「修護報表」每次都必須提供。Dim_Equipment、KPOV 庫、錯誤碼庫、告警明細
若未提供（工作表不存在或完全空白），沿用目前生效批次的資料複製到新批次；
首次匯入（尚無生效批次）時，Dim_Equipment 與 KPOV 庫仍為必要。

維修紀錄跨批次累積：以（序號, KPOV 編號, 設備ID）比對前一批次，
內容完全相同者略過、內容有變（例如後來補上改善）者以新版取代、
其餘為新增；這次檔案沒有的舊紀錄原樣保留。等級異動事件以合併後的全部紀錄重新推導。
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any

import openpyxl
from sqlalchemy import func, insert, literal, select, update
from sqlalchemy.orm import Session

from ..models import (
    DimDetectionMethod,
    DimEquipment,
    DimErrorCode,
    FactAlarm,
    FactChangeRecord,
    FactCheckItem,
    FactComplaint,
    FactKpov,
    FactRepair,
    ImportBatch,
)
from ..config import CHECK_SHIFTS
from ..services.auth import DatasetName, parse_dataset_filename
from ..services.level import compute_level
from . import mapping as M
from .level_events import derive_level_events


class ImportError_(Exception):
    """匯入失敗，整批 rollback。"""


@dataclass
class ImportReport:
    row_counts: dict[str, int] = field(default_factory=dict)
    level_mismatches: list[dict] = field(default_factory=list)
    unknown_detection_methods: list[dict] = field(default_factory=list)
    unmatched_keys: list[dict] = field(default_factory=list)
    skipped_repair_rows: list[dict] = field(default_factory=list)
    level_events: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        escalated = sum(1 for e in self.level_events if e["transition"] == "ESCALATED")
        improved = sum(1 for e in self.level_events if e["transition"] == "IMPROVED")
        return {
            "rowCounts": self.row_counts,
            "levelMismatches": self.level_mismatches,
            "unknownDetectionMethods": self.unknown_detection_methods,
            "unmatchedKeys": self.unmatched_keys,
            "skippedRepairRows": self.skipped_repair_rows,
            "levelEvents": self.level_events,
            "levelEventSummary": {
                "total": len(self.level_events),
                "escalated": escalated,
                "improved": improved,
                "unchanged": len(self.level_events) - escalated - improved,
            },
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------- 值轉換


def _to_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


_DATE_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d")


def _to_datetime(value: Any) -> dt.datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time.min, tzinfo=dt.timezone.utc)
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    return None


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coerce(field_name: str, value: Any) -> Any:
    if field_name in M.INT_FIELDS:
        return _to_int(value)
    if field_name in M.FLOAT_FIELDS:
        return _to_float(value)
    if field_name in M.DATETIME_FIELDS:
        return _to_datetime(value)
    return _to_text(value)


# --------------------------------------------------------------------------- 工作表存取


def _find_sheet(workbook, role: str):
    prefixes = M.SHEET_PREFIXES[role]
    for sheet in workbook.worksheets:
        name = M.normalize(sheet.title)
        for prefix in prefixes:
            if name.startswith(M.normalize(prefix)):
                return sheet
    return None


def _match_header(header_name: str, column_map: dict[str, str]) -> str | None:
    """把一個表頭對應到欄位規格。

    來源檔的錯誤碼庫表頭是中英雙行（例：`設備錯誤碼_x000D_\\nMachine error code`），
    normalize 後成為「設備錯誤碼 Machine error code」，無法完全比對，因此採前綴比對。
    取「最長」匹配，避免「設備型號描述」被短規格「設備型號」吃掉。
    """
    best: str | None = None
    for spec in column_map:
        if header_name == spec or header_name.startswith(spec):
            if best is None or len(spec) > len(best):
                best = spec
    return best


# 1019 版的修護報表表頭在第 5 列（上方有 8D 區塊的多層分組標題），保留一些餘裕
_HEADER_SCAN_ROWS = 8


def _map_header(
    header: list[str],
    column_map: dict[str, str],
    duplicates: dict[str, str] | None,
    paired: tuple[str, ...],
) -> tuple[dict[str, int], set[str]]:
    """把一列表頭對應成 {欄位: 索引}。

    duplicates：{欄位: 前一個出現者改名為}。同名表頭出現多次時，最後一個取得原欄位，
        較早出現者改名（新版 KPOV 庫有兩個「站別」：第一個是站位，最後一個才是原站別）。
    paired：同名欄位依出現順序分成 `<欄位>_before`、`<欄位>_after`（PCN/ECN 切入前後）。
    其餘欄位重複出現時，第一個勝出。
    """
    field_index: dict[str, int] = {}
    matched_specs: set[str] = set()
    for i, name in enumerate(header):
        if not name:
            continue
        spec = _match_header(name, column_map)
        if spec is None:
            continue
        field = column_map[spec]
        matched_specs.add(spec)
        if field in paired:
            slot = f"{field}_before" if f"{field}_before" not in field_index else f"{field}_after"
            field_index.setdefault(slot, i)
            continue
        if field in field_index:
            if duplicates and field in duplicates:
                field_index[duplicates[field]] = field_index[field]
                field_index[field] = i
            continue
        field_index[field] = i
    return field_index, matched_specs


def _read_table(
    sheet,
    column_map: dict[str, str],
    required: tuple[str, ...],
    role: str,
    *,
    duplicates: dict[str, str] | None = None,
    paired: tuple[str, ...] = (),
):
    """讀出 (欄位索引, 資料列, 表頭)。表頭以名稱對應，缺必要欄位即拋錯。

    表頭不一定在第一列（新版「鎖附設備告警」、PCN/ECN 上方有空白列或分組標題），
    因此在前幾列中取第一個具備全部必要欄位的列當表頭。
    """
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ImportError_(f"工作表「{sheet.title}」是空的")

    best_missing: list[str] | None = None
    for header_row in range(min(_HEADER_SCAN_ROWS, len(rows))):
        header = [M.normalize(cell) for cell in rows[header_row]]
        field_index, matched_specs = _map_header(header, column_map, duplicates, paired)
        # 「A|B」：兩個表頭擇一即可（新舊版欄名不同）
        missing = [col for col in required if not any(alt in matched_specs for alt in col.split("|"))]
        if not missing:
            return field_index, rows[header_row + 1 :], header
        if best_missing is None or len(missing) < len(best_missing):
            best_missing = missing

    missing_text = "、".join(col.replace("|", "／") for col in (best_missing or required))
    raise ImportError_(f"工作表「{sheet.title}」缺少必要欄位：{missing_text}")


def _row_to_dict(row: tuple, field_index: dict[str, int]) -> dict:
    out = {}
    for field_name, idx in field_index.items():
        value = row[idx] if idx < len(row) else None
        out[field_name] = _coerce(field_name, value)
    return out


def _provided_sheet(workbook, role: str):
    """找出工作表；不存在或完全空白（連表頭都沒有）視為未提供。"""
    sheet = _find_sheet(workbook, role)
    if sheet is None:
        return None
    for row in sheet.iter_rows(values_only=True):
        if any(cell is not None and str(cell).strip() for cell in row):
            return sheet
    return None


# --------------------------------------------------------------------------- 沿用前一批次


def _active_batch_id(session: Session, dataset: str | None) -> int | None:
    """同一個資料集（一條線）的生效批次：沿用上一批與維修累積都只看自己這條線。"""
    return session.scalar(
        select(ImportBatch.id)
        .where(ImportBatch.is_active.is_(True), ImportBatch.dataset == dataset)
        .order_by(ImportBatch.id.desc())
        .limit(1)
    )


def _carry_over(session: Session, model, from_batch: int, to_batch: int) -> int:
    """以 INSERT ... SELECT 把前一批次的整張表複製到新批次，回傳筆數。"""
    table = model.__table__
    columns = [c for c in table.columns if c.name not in ("id", "batch_id")]
    source = select(literal(to_batch).label("batch_id"), *columns).where(table.c.batch_id == from_batch)
    session.execute(insert(table).from_select(["batch_id", *(c.name for c in columns)], source))
    return session.scalar(select(func.count()).select_from(table).where(table.c.batch_id == to_batch)) or 0


def _carry_over_where(session: Session, model, from_batch: int, to_batch: int, condition) -> int:
    """同 _carry_over，但只複製符合條件的列，回傳複製筆數。"""
    table = model.__table__
    columns = [c for c in table.columns if c.name not in ("id", "batch_id")]
    source = select(literal(to_batch).label("batch_id"), *columns).where(table.c.batch_id == from_batch, condition)
    result = session.execute(insert(table).from_select(["batch_id", *(c.name for c in columns)], source))
    return result.rowcount or 0


# --------------------------------------------------------------------------- 維修紀錄合併

# 兩版欄位的聯集；底線開頭者（新版的分數欄）只供比對，不入庫
REPAIR_FIELDS = tuple(
    f
    for f in dict.fromkeys(
        [
            *M.REPAIR_COLUMNS.values(),
            *M.REPAIR_COLUMNS_V2.values(),
            # 1019 版起的 8D 區塊（含由預計／實際完成時間推出的日期）
            *(M.REPAIR_EIGHT_D_PREFIX + f for f in (*M.EIGHT_D_COLUMNS.values(), "planned_at", "done_at")),
        ]
    )
    if not f.startswith("_")
)


def _comparable(value: Any) -> Any:
    # SQLite 讀回的 datetime 不帶時區，統一成 UTC 才能與剛解析的值比較
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=dt.timezone.utc)
        return value.astimezone(dt.timezone.utc)
    return value


def _repair_values(source) -> dict:
    get = source.get if isinstance(source, dict) else lambda f: getattr(source, f, None)
    return {f: _comparable(get(f)) for f in REPAIR_FIELDS}


def _repair_key(values: dict) -> tuple:
    if values.get("serial_no"):
        return (values["serial_no"], values["kpov_no"], values["equipment_code"])
    # 沒有序號就無法辨識是否為同一筆，只把內容完全相同的視為同一筆
    return ("", *(str(values[f]) for f in REPAIR_FIELDS))


# --------------------------------------------------------------------------- 偵測方式字典


def _dictionary_rank(pairs: list[tuple[str, int]]) -> tuple[int, int]:
    return (len({score for _, score in pairs}), len(pairs))


def parse_detection_dictionary(sheet) -> list[tuple[str, int]]:
    """從「修護報表」工作表解析偵測方式字典（spec.md §2.5 / REQ-IMP-05）。

    字典停在無表頭的欄位（現況為第 27–28 欄），與左側維修紀錄無關，
    因此不能用表頭對應來讀。作法：找出所有「無表頭」的相鄰欄位配對，
    其中左欄為文字、右欄為 1–10 的整數。
    """
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []
    header = [M.normalize(cell) for cell in rows[0]]
    width = max(len(r) for r in rows)
    unnamed = {i for i in range(width) if i >= len(header) or not header[i]}

    best: list[tuple[str, int]] = []
    for col in sorted(unnamed):
        if col + 1 not in unnamed:
            continue
        pairs: list[tuple[str, int]] = []
        for row in rows:
            name = _to_text(row[col]) if col < len(row) else None
            score = _to_int(row[col + 1]) if col + 1 < len(row) else None
            if name and score is not None and 1 <= score <= 10:
                pairs.append((name, score))
        # 1019 版的修護報表多了 8D 區塊，裡面也有「偵測方式＋偵測度」的相鄰欄位（例：「直流轉換器
        # 電流不平衡關機｜5」），筆數還比字典多。真正的字典是 1–10 分各一種方式，分數幾乎不重複；
        # 8D 區塊則是同一分數重複出現。因此先比「不同分數的個數」，再比筆數。
        if _dictionary_rank(pairs) > _dictionary_rank(best):
            best = pairs

    # 去重，保留首次出現
    seen: set[str] = set()
    result: list[tuple[str, int]] = []
    for name, score in best:
        if name not in seen:
            seen.add(name)
            result.append((name, score))
    return result


# --------------------------------------------------------------------------- 主流程


def import_workbook(
    session: Session,
    path: str,
    filename: str,
    *,
    imported_by: str | None = None,
    dataset: DatasetName | None = None,
) -> tuple[ImportBatch, ImportReport]:
    """匯入一份 Excel 成為該資料集（一條線）的新生效批次。

    dataset 未給時依檔名解析；檔名不合格式（例：測試或命令列匯入）時歸到預設的 WJ1-DCS-PM1。
    API 會在呼叫前先驗證檔名與權限（spec §15）。
    """
    if dataset is None:
        try:
            dataset = parse_dataset_filename(filename)
        except ValueError:
            dataset = DatasetName("WJ1", "DCS", "PM1", "")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    report = ImportReport()

    batch = ImportBatch(
        filename=filename,
        imported_by=imported_by,
        status="pending",
        row_counts={},
        plant=dataset.plant,
        factory=dataset.factory,
        line_code=dataset.line,
        dataset=dataset.key,
        data_date=dataset.date or None,
    )
    session.add(batch)
    session.flush()

    try:
        _import_all(session, workbook, batch, report)
    except ImportError_:
        session.rollback()
        raise
    finally:
        workbook.close()

    batch.row_counts = report.row_counts
    batch.status = "success"
    batch.error_log = report.as_dict()

    # 切換生效批次（單一交易內）：只停用同一個資料集的舊批次，其他廠／線不受影響
    session.execute(
        update(ImportBatch)
        .where(ImportBatch.id != batch.id, ImportBatch.dataset == batch.dataset)
        .values(is_active=False)
    )
    batch.is_active = True
    session.commit()
    return batch, report


def _clean_ref(value: Any) -> str | None:
    """NA / N/A 視為未填（ECN 的影響站別、設備ID 常填 NA 表示全廠）。"""
    text = _to_text(value)
    if text is None or text.upper() in ("NA", "N/A", "-"):
        return None
    return text


def parse_equipment_reference(sheet) -> list[dict]:
    """解析「設備對應參考」。

    工作表左右並排兩塊表（CTP：MES站別/站別/屬性/設備名稱/設備ID；
    OP：站別/屬性/設備名稱/設備代碼），表頭列也不一樣，因此不能用 _read_table：
    逐列找「設備名稱」表頭，往右取最近的設備代碼欄、往左取站別、屬性欄，
    之後的列即為該塊的資料。
    """
    rows = list(sheet.iter_rows(values_only=True))
    blocks: list[dict] = []  # {start_row, name_col, code_col, station_col, attr_col}
    for r, row in enumerate(rows[:_HEADER_SCAN_ROWS]):
        header = [M.normalize(cell) for cell in row]
        for c, name in enumerate(header):
            if name != M.EQUIPMENT_REF_NAME:
                continue
            if any(b["name_col"] == c for b in blocks):
                continue
            code_col = next(
                (i for i in range(c + 1, len(header)) if header[i] in M.EQUIPMENT_REF_CODES), None
            )
            if code_col is None:
                continue
            left = header[:c]
            station_col = max((i for i, h in enumerate(left) if h == "站別"), default=None)
            attr_col = max((i for i, h in enumerate(left) if h == "屬性"), default=None)
            blocks.append(
                {"start": r + 1, "name_col": c, "code_col": code_col, "station_col": station_col, "attr_col": attr_col}
            )

    def cell(row, idx):
        return _to_text(row[idx]) if idx is not None and idx < len(row) else None

    out: list[dict] = []
    for block in blocks:
        for row in rows[block["start"] :]:
            name = cell(row, block["name_col"])
            code = cell(row, block["code_col"])
            if not name or not code or name == M.EQUIPMENT_REF_NAME:
                continue
            station_group = cell(row, block["station_col"])
            out.append(
                {
                    "name": name,
                    "code": code,
                    "station_group": station_group,
                    "attribute": cell(row, block["attr_col"]),
                }
            )
    return out


_REF_KEY_PREFIX = "REF:"
_INTERVAL = re.compile(r"(\d+(?:\.\d+)?)\s*(h|hr|小時)", re.IGNORECASE)


def parse_interval_hours(frequency: str | None) -> float:
    """點檢頻率字串 -> 間隔小時。

    「開線/班、巡檢: 2h/次」-> 2；只有「開線/班」（每班一次）-> 一整班的時數，首頁只畫 1 格。
    解析不到預設 2 小時。
    """
    if frequency:
        match = _INTERVAL.search(frequency)
        if match:
            return float(match.group(1))
        if "班" in frequency:
            return float(max(length for _, _, length in CHECK_SHIFTS))
    return 2.0


class _StationLookup:
    """站別名稱 -> 設備代碼。修護報表、高風險點檢的 OP 列沒有設備ID，靠此補上。"""

    def __init__(self, by_name: dict[str, str]):
        self.by_name = by_name

    def resolve(self, station: str | None, *, op: bool) -> str | None:
        if not station:
            return None
        name = station.strip()
        if name in self.by_name:
            return self.by_name[name]
        if op and name in M.STATION_ALIASES_OP:
            return self.by_name.get(M.STATION_ALIASES_OP[name])
        return None


def _import_all(session: Session, workbook, batch: ImportBatch, report: ImportReport) -> None:
    previous = _active_batch_id(session, batch.dataset)

    def carry(model, label: str, key: str) -> None:
        count = _carry_over(session, model, previous, batch.id)
        report.row_counts[key] = count
        report.warnings.append(f"未提供「{label}」，沿用批次 #{previous} 的 {count} 筆資料")

    repair_sheet = _find_sheet(workbook, "repair")
    if repair_sheet is None:
        raise ImportError_("找不到「修護報表」工作表")

    # 1) 偵測方式字典（其他步驟相依於它）
    dictionary = parse_detection_dictionary(repair_sheet)
    if not dictionary:
        raise ImportError_("在「修護報表」中找不到偵測方式字典（偵測方式 ↔ 1–10 分數對照）")
    for name, score in dictionary:
        session.add(DimDetectionMethod(batch_id=batch.id, method_name=name, score=score))
    method_scores = dict(dictionary)
    report.row_counts["detectionMethods"] = len(dictionary)
    # 分數 → 偵測方式：補空白的偵測方式欄用（同分有兩種以上方式時無法判定，不補）
    by_score: dict[int, list[str]] = {}
    for name, score in dictionary:
        by_score.setdefault(score, []).append(name)
    method_by_score = {score: names[0] for score, names in by_score.items() if len(names) == 1}

    # 2) 設備維度：Dim_Equipment（舊版）＋ 設備對應參考（新版，含 OP 人工站）
    equipment_sheet = _provided_sheet(workbook, "equipment")
    ref_sheet = _provided_sheet(workbook, "equipment_ref")
    equipment_codes: set[str] = set()
    if equipment_sheet is not None:
        idx, rows, _ = _read_table(equipment_sheet, M.EQUIPMENT_COLUMNS, M.EQUIPMENT_REQUIRED, "equipment")
        for row in rows:
            data = _row_to_dict(row, idx)
            code = data.get("equipment_code")
            if not code or code in equipment_codes:
                continue
            equipment_codes.add(code)
            session.add(DimEquipment(batch_id=batch.id, **data))
    elif previous is not None:
        carry(DimEquipment, "Dim_Equipment", "equipment")
        equipment_codes = set(
            session.scalars(select(DimEquipment.equipment_code).where(DimEquipment.batch_id == batch.id))
        )
    elif ref_sheet is None:
        raise ImportError_("首次匯入必須包含「Dim_Equipment」或「設備對應參考」工作表")

    # 站別名稱 -> 設備代碼，依序以後者覆蓋前者：
    #   內建 OP 預設對照 -> 前批由「設備對應參考」補入的設備 -> 本次檔案
    # 1011 版的「設備對應參考」少了 OP 區，靠預設／前批對照仍能補上 A000N。
    station_to_code: dict[str, str] = {name: code for _, name, code in M.DEFAULT_OP_EQUIPMENT}
    session.flush()
    for code, desc in session.execute(
        select(DimEquipment.equipment_code, DimEquipment.equipment_desc).where(
            DimEquipment.batch_id == batch.id,
            DimEquipment.equipment_key.like(f"{_REF_KEY_PREFIX}%"),
        )
    ):
        if desc:
            station_to_code[desc] = code
    if ref_sheet is not None:
        reference = parse_equipment_reference(ref_sheet)
        if not reference:
            report.warnings.append(f"「{ref_sheet.title}」中找不到設備名稱／設備代碼對照")
        # OP 優先：站別查找主要用於 OP 列
        reference.sort(key=lambda e: 0 if e["attribute"] == "OP" else 1)
        file_names: set[str] = set()
        for entry in reference:
            if entry["name"] not in file_names:
                # 同名以檔案中第一筆（OP 優先）為準，並覆蓋前批對照
                file_names.add(entry["name"])
                station_to_code[entry["name"]] = entry["code"]
            if entry["code"] not in equipment_codes:
                equipment_codes.add(entry["code"])
                session.add(
                    DimEquipment(
                        batch_id=batch.id,
                        equipment_code=entry["code"],
                        # 標記來源，之後的批次沒附「設備對應參考」時仍能重建站別對照
                        equipment_key=f"{_REF_KEY_PREFIX}{entry['station_group'] or ''}",
                        model_desc=entry["name"],
                        equipment_desc=entry["name"],
                    )
                )
    lookup = _StationLookup(station_to_code)

    # 3) 錯誤碼字典
    error_sheet = _provided_sheet(workbook, "error_code")
    error_count = 0
    if error_sheet is None and previous is not None:
        carry(DimErrorCode, "設備告警品質相關代碼庫", "errorCodes")
    elif error_sheet is not None:
        idx, rows, _ = _read_table(error_sheet, M.ERROR_CODE_COLUMNS, M.ERROR_CODE_REQUIRED, "error_code")
        seen_codes: set[str] = set()
        for row in rows:
            data = _row_to_dict(row, idx)
            code = data.get("error_code")
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            session.add(DimErrorCode(batch_id=batch.id, **data))
            error_count += 1
        report.row_counts["errorCodes"] = error_count
    else:
        report.row_counts["errorCodes"] = 0

    dup_sheet = _find_sheet(workbook, "error_code_dup")
    if dup_sheet is not None:
        report.warnings.append(
            f"已忽略工作表「{dup_sheet.title}」（與「設備告警品質相關代碼庫」內容重複，REQ-IMP-04）"
        )

    # 4) KPOV 基準
    kpov_sheet = _provided_sheet(workbook, "kpov")
    if kpov_sheet is not None:
        idx, rows, _ = _read_table(
            kpov_sheet,
            M.KPOV_COLUMNS,
            M.KPOV_REQUIRED,
            "kpov",
            duplicates={"station": "station_group"},
        )
        kpov_count = 0
        seen_kpov: set[tuple[str, str, str]] = set()
        op_count = 0
        for row_no, row in enumerate(rows, start=2):
            data = _row_to_dict(row, idx)
            # OP 站原本沒有設備代碼，只要有站別就是有效列——不可用 equipment_code 當存在性判斷。
            # 沒有 KPOV 名稱的是小計列（例：「ACME 導入 / 8站」），略過。
            if not data.get("station") or not data.get("kpov_name"):
                continue
            attribute1 = data.get("attribute1") or "UNKNOWN"

            override = M.EQUIPMENT_OVERRIDES.get(data["station"]) if attribute1 == "CTP" else None
            if override and data.get("equipment_code") and data["equipment_code"] != override:
                report.warnings.append(
                    f"KPOV 第 {row_no} 列（{data['station']} · {data.get('kpov_no')}）設備ID "
                    f"{data['equipment_code']} 依現場確認改為 {override}"
                )
                data["equipment_code"] = override
            if attribute1 == "OP" and not data.get("equipment_code"):
                code = lookup.resolve(data["station"], op=True)
                if code:
                    data["equipment_code"] = code
                elif station_to_code:
                    report.unmatched_keys.append(
                        {
                            "table": "fact_kpov",
                            "row": row_no,
                            "station": data["station"],
                            "reason": "OP 站別在「設備對應參考」中找不到設備代碼",
                        }
                    )

            key = (attribute1, data["station"], data.get("kpov_no") or "")
            if key in seen_kpov:
                report.warnings.append(
                    f"KPOV 第 {row_no} 列重複（{attribute1} · {key[1]} · 編號 {key[2]}），已略過"
                )
                continue
            seen_kpov.add(key)
            if attribute1 == "OP":
                op_count += 1

            level = compute_level(data.get("small_y_score"), data.get("big_y_score"))
            source = data.get("level_source")
            mismatch = False
            if source and level is not None:
                expected = f"Level {level}"
                if M.normalize(source) != expected:
                    mismatch = True
                    report.level_mismatches.append(
                        {
                            "row": row_no,
                            "kpovNo": data.get("kpov_no"),
                            "kpovName": data.get("kpov_name"),
                            "equipmentCode": data.get("equipment_code"),
                            "station": data.get("station"),
                            "smallY": data.get("small_y_score"),
                            "bigY": data.get("big_y_score"),
                            "sourceLevel": source,
                            "computedLevel": expected,
                        }
                    )
            equipment_code = data.get("equipment_code")
            if equipment_code and equipment_code not in equipment_codes:
                # 新版不再提供 Dim_Equipment，「設備對應參考」也不一定列全（例：OT00420118）。
                # KPOV 庫用到的設備補進設備維度，AR 設備綁定與線別篩選才找得到。
                equipment_codes.add(equipment_code)
                session.add(
                    DimEquipment(
                        batch_id=batch.id,
                        equipment_code=equipment_code,
                        equipment_desc=data["station"],
                        model_desc=data["station"],
                    )
                )

            session.add(FactKpov(batch_id=batch.id, level_baseline=level, level_mismatch=mismatch, **data))
            kpov_count += 1
        report.row_counts["kpov"] = kpov_count
        report.row_counts["kpovOp"] = op_count
        report.row_counts["kpovCtp"] = kpov_count - op_count
    elif previous is not None:
        carry(FactKpov, "KPOV库-by 站", "kpov")
        op_count = session.scalar(
            select(func.count()).select_from(FactKpov).where(
                FactKpov.batch_id == batch.id, FactKpov.attribute1 == "OP"
            )
        ) or 0
        report.row_counts["kpovOp"] = op_count
        report.row_counts["kpovCtp"] = report.row_counts["kpov"] - op_count
    else:
        raise ImportError_("首次匯入必須包含「KPOV库-by 站」工作表")

    session.flush()
    # 設備筆數在 KPOV 之後才算：KPOV 用到但維度沒有的設備會在上一步補入
    report.row_counts["equipment"] = session.scalar(
        select(func.count()).select_from(DimEquipment).where(DimEquipment.batch_id == batch.id)
    ) or 0
    kpov_keys = set(
        session.execute(
            select(FactKpov.kpov_no, FactKpov.equipment_code).where(FactKpov.batch_id == batch.id)
        ).all()
    )

    # 5) 告警明細：鎖附 + 塗覆（新版）或單一告警表（舊版）
    _import_alarms(session, workbook, batch, report, previous, kpov_keys, carry)

    # 6) PCN / ECN 變更紀錄、高風險項點檢
    _import_changes(session, workbook, batch, report, previous, lookup)
    _import_check_items(session, workbook, batch, report, previous, carry, lookup)
    _import_complaints(session, workbook, batch, report, previous, carry)

    # 7) 維修紀錄（只讀有表頭的欄位，字典欄位已在步驟 1 分開處理）
    header_text = " ".join(
        M.normalize(c) for row in repair_sheet.iter_rows(max_row=_HEADER_SCAN_ROWS, values_only=True) for c in row
    )
    legacy = M.REPAIR_V1_MARKER in header_text
    repair_map = M.REPAIR_COLUMNS if legacy else M.REPAIR_COLUMNS_V2
    idx, rows, _ = _read_table(repair_sheet, repair_map, M.REPAIR_REQUIRED, "repair")
    eight_d = _repair_eight_d_index(repair_sheet, report)
    if "emergency_measure" not in idx:
        report.warnings.append("修護報表沒有「緊急措施」欄，措施表的緊急措施會是空白（1019 版以前的檔案）")
    has_improve_time = "improvement_effective_at" in idx
    if not has_improve_time:
        report.warnings.append("修護報表沒有「改善時間」欄，改善事件暫以匯入時間代替（舊版檔案）")
    incoming: dict[tuple, dict] = {}
    for row_no, row in enumerate(rows, start=2):
        data = _row_to_dict(row, idx)
        if not data.get("equipment_code") and not data.get("kpov_no"):
            continue  # 字典區的列，不是維修紀錄
        if eight_d:
            for field, value in _eight_d_values(row, eight_d).items():
                data[M.REPAIR_EIGHT_D_PREFIX + field] = value
        if not data.get("equipment_code") and data.get("station"):
            # 沒有設備ID 的是 OP 站，依站別查「設備對應參考」
            data["equipment_code"] = lookup.resolve(data["station"], op=True)
        if not data.get("equipment_code") or not data.get("kpov_no"):
            report.skipped_repair_rows.append(
                {
                    "row": row_no,
                    "reason": "設備ID 或 KPOV 编号 缺值（站別也無法對應設備）",
                    "serialNo": data.get("serial_no"),
                    "station": data.get("station"),
                }
            )
            continue
        _fill_methods_from_eight_d(data, method_by_score, row_no, report)
        if not legacy:
            for method_field, score_field in (
                ("small_y_method_after", "_small_y_score_after"),
                ("big_y_method_after", "_big_y_score_after"),
                ("small_y_method_improved", "_small_y_score_improved"),
                ("big_y_method_improved", "_big_y_score_improved"),
            ):
                method = data.get(method_field)
                given = _to_int(data.get(score_field))
                if method in method_scores and given is not None and given != method_scores[method]:
                    report.warnings.append(
                        f"修護報表第 {row_no} 列「{method}」填 {given} 分，字典為 {method_scores[method]} 分，以字典為準"
                    )
        values = _repair_values(data)
        key = _repair_key(values)
        if key in incoming:
            report.warnings.append(
                f"修護報表第 {row_no} 列與前面的紀錄重複（序號 {values['serial_no']}），以第 {row_no} 列為準"
            )
        incoming[key] = values

    # 與前一批次合併
    merged: dict[tuple, dict] = {}
    if previous is not None:
        for old in session.scalars(
            select(FactRepair).where(FactRepair.batch_id == previous).order_by(FactRepair.id)
        ):
            values = _repair_values(old)
            merged[_repair_key(values)] = values
    new_count = updated_count = unchanged_count = 0
    for key, values in incoming.items():
        old = merged.get(key)
        if old is None:
            new_count += 1
        elif old == values:
            unchanged_count += 1
        else:
            updated_count += 1
        merged[key] = values

    repairs: list[FactRepair] = []
    for values in merged.values():
        repair = FactRepair(batch_id=batch.id, **values)
        session.add(repair)
        repairs.append(repair)
    session.flush()
    report.row_counts["repairs"] = len(repairs)
    report.row_counts["repairsNew"] = new_count
    report.row_counts["repairsUpdated"] = updated_count
    report.row_counts["repairsUnchanged"] = unchanged_count
    report.row_counts["repairsCarried"] = len(merged) - len(incoming)

    # 8) 等級異動事件
    derive_level_events(
        session, batch, repairs, method_scores, report, improve_time_fallback=not has_improve_time
    )
    report.row_counts["levelEvents"] = len(report.level_events)


def _period_from(value: str | None) -> str | None:
    """告警日期 20251016 / 202608 -> 期別 YYYYMM。"""
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    return digits[:6] if len(digits) >= 6 else value


def _import_alarms(session, workbook, batch, report, previous, kpov_keys, carry) -> None:
    sources = [
        ("alarm_screw", "鎖附", M.ALARM_COLUMNS, M.ALARM_REQUIRED, "alarmsScrew"),
        ("alarm_coat", "塗覆", M.ALARM_COATING_COLUMNS, M.ALARM_COATING_REQUIRED, "alarmsCoating"),
        ("alarm", "legacy", M.ALARM_COLUMNS, M.ALARM_REQUIRED, "alarmsLegacy"),
    ]
    provided = [(s, _provided_sheet(workbook, s[0])) for s in sources]
    provided = [(s, sheet) for s, sheet in provided if sheet is not None]
    if not provided:
        if previous is not None:
            carry(FactAlarm, "設備告警", "alarms")
        else:
            report.row_counts["alarms"] = 0
        return

    total = 0
    unmatched: dict[tuple[str, str], int] = {}
    for (role, source, columns, required, count_key), sheet in provided:
        idx, rows, _ = _read_table(sheet, columns, required, role)
        buffer = []
        count = 0
        for row in rows:
            data = _row_to_dict(row, idx)
            if not data.get("equipment_code"):
                continue
            data["period"] = _period_from(data.get("period")) or (
                data["stop_start_at"].strftime("%Y%m") if data.get("stop_start_at") else None
            )
            kpov_no = data.get("kpov_no")
            if kpov_no and (kpov_no, data["equipment_code"]) not in kpov_keys:
                pair = (kpov_no, data["equipment_code"])
                unmatched[pair] = unmatched.get(pair, 0) + 1
            buffer.append(FactAlarm(batch_id=batch.id, source=source, **data))
            count += 1
            if len(buffer) >= 2000:
                session.bulk_save_objects(buffer)
                buffer.clear()
        if buffer:
            session.bulk_save_objects(buffer)
        report.row_counts[count_key] = count
        total += count
    report.row_counts["alarms"] = total
    for (kpov_no, code), n in sorted(unmatched.items()):
        report.unmatched_keys.append(
            {
                "table": "fact_alarm",
                "kpovNo": kpov_no,
                "equipmentCode": code,
                "count": n,
                "reason": "告警的 KPOV × 設備 組合在 KPOV 庫中不存在",
            }
        )


def _import_changes(session, workbook, batch, report, previous, lookup: _StationLookup) -> None:
    for role, kind in (("pcn", "PCN"), ("ecn", "ECN")):
        sheet = _provided_sheet(workbook, role)
        key = f"{kind.lower()}Records"
        if sheet is None:
            if previous is not None:
                count = _carry_over_where(session, FactChangeRecord, previous, batch.id, FactChangeRecord.kind == kind)
                report.row_counts[key] = count
                if count:
                    report.warnings.append(f"未提供「{kind} 紀錄」，沿用批次 #{previous} 的 {count} 筆資料")
            else:
                report.row_counts[key] = 0
            continue
        idx, rows, _ = _read_table(sheet, M.CHANGE_COLUMNS, M.CHANGE_REQUIRED, role, paired=M.CHANGE_PAIRED)
        count = 0
        for row in rows:
            data = _row_to_dict(row, idx)
            if not data.get("effective_at") and not data.get("content"):
                continue
            for field in ("station", "equipment_code", "kpov_name", "kpov_no"):
                data[field] = _clean_ref(data.get(field))
            if kind == "PCN" and not data.get("kpov_no"):
                continue
            # OP 人工站的 PCN 沒填設備ID，與修護報表相同，依影響站別查「設備對應參考」
            if not data.get("equipment_code") and data.get("station"):
                data["equipment_code"] = lookup.resolve(data["station"], op=True)
                if kind == "PCN" and not data["equipment_code"]:
                    report.unmatched_keys.append(
                        {
                            "table": "fact_change_record",
                            "station": data["station"],
                            "kpovNo": data.get("kpov_no"),
                            "reason": "PCN 的影響站別在「設備對應參考」中找不到設備代碼",
                        }
                    )
            session.add(FactChangeRecord(batch_id=batch.id, kind=kind, **data))
            count += 1
        report.row_counts[key] = count


def _import_check_items(session, workbook, batch, report, previous, carry, lookup: _StationLookup) -> None:
    sheet = _provided_sheet(workbook, "check_item")
    if sheet is None:
        if previous is not None:
            carry(FactCheckItem, "高風險項點檢", "checkItems")
        else:
            report.row_counts["checkItems"] = 0
        return
    idx, rows, _ = _read_table(sheet, M.CHECK_ITEM_COLUMNS, M.CHECK_ITEM_REQUIRED, "check_item")
    count = 0
    for row_no, row in enumerate(rows, start=3):
        data = _row_to_dict(row, idx)
        if not data.get("check_content") or not data.get("kpov_no"):
            continue
        if not data.get("equipment_code"):
            data["equipment_code"] = lookup.resolve(data.get("station"), op=data.get("attribute1") == "OP")
            if not data["equipment_code"]:
                report.unmatched_keys.append(
                    {
                        "table": "fact_check_item",
                        "row": row_no,
                        "station": data.get("station"),
                        "kpovNo": data.get("kpov_no"),
                        "reason": "點檢項目的站別在「設備對應參考」中找不到設備代碼",
                    }
                )
        session.add(
            FactCheckItem(batch_id=batch.id, interval_hours=parse_interval_hours(data.get("frequency")), **data)
        )
        count += 1
    report.row_counts["checkItems"] = count


_DATE_IN_TEXT = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})")
_LEVEL_IN_TEXT = re.compile(r"Level\s*([0-3])", re.IGNORECASE)


def _complaint_dates(value: Any) -> tuple[dt.datetime | None, bool]:
    """客訴的預計／實際完成時間可能是日期、文字日期，或多項對策並列（「1.2026/11/3 2.2026/7/30」）。

    回傳 (最晚的日期, 是否每一項都有日期)。任一項是 NA 表示尚未全部完成。
    """
    if value is None:
        return None, False
    if isinstance(value, (dt.datetime, dt.date)):
        return _to_datetime(value), True
    text = str(value)
    dates = [
        dt.datetime(int(y), int(m), int(d), tzinfo=dt.timezone.utc)
        for y, m, d in _DATE_IN_TEXT.findall(text)
    ]
    if not dates:
        return None, False
    pending = bool(re.search(r"(?<![A-Za-z])N/?A(?![A-Za-z])", text, re.IGNORECASE))
    return max(dates), not pending


def _import_complaints(session, workbook, batch, report, previous, carry) -> None:
    from openpyxl.utils import column_index_from_string

    sheet = _provided_sheet(workbook, "complaint")
    if sheet is None:
        if previous is not None:
            carry(FactComplaint, "客訴報表", "complaints")
        else:
            report.row_counts["complaints"] = 0
        return

    rows = list(sheet.iter_rows(values_only=True))
    index = {field: column_index_from_string(letter) - 1 for letter, field in M.COMPLAINT_COLUMNS.items()}

    # 驗證表頭：每個關鍵欄位的文字必須出現在前幾列的該欄
    head = rows[: M.COMPLAINT_HEADER_ROWS]
    wrong = _header_mismatches(head, M.COMPLAINT_HEADER_CHECKS)
    if wrong:
        raise ImportError_(f"「{sheet.title}」欄位位置與預期不符：{'；'.join(wrong)}")
    # 緊急措施等欄位位置可能再變動，以表頭文字定位（找不到就不讀）
    named = _named_columns(head, M.COMPLAINT_NAMED_COLUMNS)

    count = 0
    for row in rows[M.COMPLAINT_HEADER_ROWS - 2 :]:
        seq = _to_int(row[0]) if row else None
        if seq is None:
            continue  # 表頭、範本空列、右側偵測字典列
        data: dict[str, Any] = {
            field: _clean_text(row[i]) if i < len(row) else None for field, i in index.items()
        }
        data.update(_eight_d_values(row, index))
        data["seq"] = seq
        data["complained_at"] = _to_datetime(row[index["complained_at"]]) or _complaint_dates(
            row[index["complained_at"]]
        )[0]
        for field, i in named.items():
            raw = row[i] if i < len(row) else None
            data[field] = _to_datetime(raw) if field.endswith("_at") else _clean_text(raw)
        session.add(FactComplaint(batch_id=batch.id, **data))
        count += 1
    report.row_counts["complaints"] = count


def _clean_text(value: Any) -> str | None:
    text = _to_text(value)
    return None if text in ("#N/A", "N/A", "NA", "-") else text


def _header_mismatches(head: list[tuple], checks: dict[str, str], offset: int = 0) -> list[str]:
    """表頭文字檢查：checks 的每個欄位（可整段位移 offset 欄）都要在前幾列出現指定文字。"""
    from openpyxl.utils import column_index_from_string

    wrong = []
    for letter, label in checks.items():
        col = column_index_from_string(letter) - 1 + offset
        texts = [M.normalize(r[col]) if col < len(r) else "" for r in head]
        if not any(label in t.replace(" ", "") for t in texts):
            wrong.append(f"{M.shift_letter(letter, offset)} 欄應為「{label}」")
    return wrong


def _named_columns(head: list[tuple], names: dict[str, str]) -> dict[str, int]:
    """在表頭列中以完全相同的文字找欄位，回傳 {欄位: 索引}；同名取第一個。"""
    found: dict[str, int] = {}
    for row in head:
        for i, cell in enumerate(row):
            field = names.get(M.normalize(cell))
            if field and field not in found:
                found[field] = i
    return found


# 修護報表的偵測方式欄（BQ～BT）空白時，改用同一列 8D 區塊的偵測度分數換成字典裡的偵測方式（v2.8）：
# 改善前 小y／大Y（Z／W 欄）→ 不良發生時；改善後（AX／BA 欄）→ 改善後。
_EIGHT_D_METHOD_FALLBACK = (
    ("small_y_method_after", "small_y_score_before", "小y偵測方式"),
    ("big_y_method_after", "big_y_score_before", "大y偵測方式"),
    ("small_y_method_improved", "small_y_score_after", "小y偵測方式(變化後)"),
    ("big_y_method_improved", "big_y_score_after", "大y偵測方式(變化後)"),
)


def _fill_methods_from_eight_d(data: dict, method_by_score: dict[int, str], row_no: int, report) -> None:
    filled, missing = [], []
    for method_field, score_field, label in _EIGHT_D_METHOD_FALLBACK:
        if data.get(method_field):
            continue
        score = _to_int(data.get(M.REPAIR_EIGHT_D_PREFIX + score_field))
        if score is None:
            continue
        method = method_by_score.get(score)
        if method is None:
            missing.append(f"{label}（8D {score} 分）")
            continue
        data[method_field] = method
        filled.append(f"{label}＝{method}（8D {score} 分）")
    serial = data.get("serial_no") or "（無序號）"
    if filled:
        report.warnings.append(f"修護報表第 {row_no} 列（序號 {serial}）偵測方式空白，依 8D 偵測度補上：" + "、".join(filled))
    if missing:
        report.warnings.append(
            f"修護報表第 {row_no} 列（序號 {serial}）偵測方式空白，8D 分數在字典中對不到唯一的偵測方式：" + "、".join(missing)
        )


def _eight_d_values(row: tuple, index: dict[str, int]) -> dict[str, Any]:
    """讀 8D 區塊（客訴報表與修護報表共用）：index 為 {8D 欄位: 欄索引}。

    分數轉整數、「Level 3」轉 3、預計／實際完成時間另存日期（多項對策取最晚日期；
    實際完成時間要每一項都有日期才算完成）。
    """
    def raw(field: str):
        i = index.get(field)
        return row[i] if i is not None and i < len(row) else None

    data: dict[str, Any] = {field: _clean_text(raw(field)) for field in M.EIGHT_D_COLUMNS.values()}
    for field in M.EIGHT_D_INT_FIELDS:
        data[field] = _to_int(data[field])
    for field in M.EIGHT_D_LEVEL_FIELDS:
        match = _LEVEL_IN_TEXT.search(data[field] or "")
        data[field] = int(match.group(1)) if match else None
    data["planned_at"], _ = _complaint_dates(raw("planned_text"))
    done_at, all_done = _complaint_dates(raw("done_text"))
    data["done_at"] = done_at if all_done else None
    for field in ("planned_text", "done_text"):
        if isinstance(raw(field), (dt.datetime, dt.date)):
            data[field] = _to_datetime(raw(field)).date().isoformat()
    return data


def _repair_eight_d_index(sheet, report: "ImportReport") -> dict[str, int]:
    """修護報表的 8D 區塊（1019 版起）：位置與客訴報表相同但右移 11 欄。

    表頭文字全部對得上才讀；完全沒有這段（舊版）就略過；只對上一部分代表欄位位置變了，
    寧可不讀並提出警告，也不要讀錯欄。
    """
    from openpyxl.utils import column_index_from_string

    head = list(sheet.iter_rows(max_row=M.COMPLAINT_HEADER_ROWS, values_only=True))
    wrong = _header_mismatches(head, M.EIGHT_D_HEADER_CHECKS, M.REPAIR_EIGHT_D_OFFSET)
    if len(wrong) == len(M.EIGHT_D_HEADER_CHECKS):
        return {}
    if wrong:
        report.warnings.append(f"修護報表的 8D 區塊欄位位置與預期不符，未匯入 8D 內容：{'；'.join(wrong)}")
        return {}
    return {
        field: column_index_from_string(letter) - 1 + M.REPAIR_EIGHT_D_OFFSET
        for letter, field in M.EIGHT_D_COLUMNS.items()
    }

