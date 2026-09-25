"""Excel 匯入 — spec.md §6。

匯入順序（有相依，REQ-IMP-07）：
    dim_detection_method -> dim_equipment / dim_error_code -> fact_kpov
    -> fact_repair -> fact_level_event
整個流程為單一交易，失敗不留半套資料（REQ-IMP-09）。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import openpyxl
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..models import (
    DimDetectionMethod,
    DimEquipment,
    DimErrorCode,
    FactAlarm,
    FactKpov,
    FactRepair,
    ImportBatch,
)
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


def _read_table(sheet, column_map: dict[str, str], required: tuple[str, ...], role: str):
    """讀出 (欄位索引, 資料列, 表頭)。表頭以名稱對應，缺必要欄位即拋錯。"""
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise ImportError_(f"工作表「{sheet.title}」是空的")
    header = [M.normalize(cell) for cell in rows[0]]

    field_index: dict[str, int] = {}
    matched_specs: set[str] = set()
    for i, name in enumerate(header):
        if not name:
            continue
        spec = _match_header(name, column_map)
        if spec is None:
            continue
        field = column_map[spec]
        if field in field_index:
            continue  # 同一欄位重複出現，第一個勝出
        field_index[field] = i
        matched_specs.add(spec)

    missing = [col for col in required if col not in matched_specs]
    if missing:
        raise ImportError_(f"工作表「{sheet.title}」缺少必要欄位：{'、'.join(missing)}")

    return field_index, rows[1:], header


def _row_to_dict(row: tuple, field_index: dict[str, int]) -> dict:
    out = {}
    for field_name, idx in field_index.items():
        value = row[idx] if idx < len(row) else None
        out[field_name] = _coerce(field_name, value)
    return out


# --------------------------------------------------------------------------- 偵測方式字典


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
        if len(pairs) > len(best):
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
) -> tuple[ImportBatch, ImportReport]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    report = ImportReport()

    batch = ImportBatch(filename=filename, imported_by=imported_by, status="pending", row_counts={})
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

    # 切換生效批次（單一交易內）
    session.execute(update(ImportBatch).where(ImportBatch.id != batch.id).values(is_active=False))
    batch.is_active = True
    session.commit()
    return batch, report


def _import_all(session: Session, workbook, batch: ImportBatch, report: ImportReport) -> None:
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

    # 2) 設備維度
    equipment_sheet = _find_sheet(workbook, "equipment")
    if equipment_sheet is None:
        raise ImportError_("找不到「Dim_Equipment」工作表")
    idx, rows, _ = _read_table(equipment_sheet, M.EQUIPMENT_COLUMNS, M.EQUIPMENT_REQUIRED, "equipment")
    equipment_codes: set[str] = set()
    equipment_count = 0
    for row in rows:
        data = _row_to_dict(row, idx)
        code = data.get("equipment_code")
        if not code or code in equipment_codes:
            continue
        equipment_codes.add(code)
        session.add(DimEquipment(batch_id=batch.id, **data))
        equipment_count += 1
    report.row_counts["equipment"] = equipment_count

    # 3) 錯誤碼字典
    error_sheet = _find_sheet(workbook, "error_code")
    error_count = 0
    if error_sheet is not None:
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

    dup_sheet = _find_sheet(workbook, "error_code_dup")
    if dup_sheet is not None:
        report.warnings.append(
            f"已忽略工作表「{dup_sheet.title}」（與「設備告警品質相關代碼庫」內容重複，REQ-IMP-04）"
        )

    # 4) KPOV 基準
    kpov_sheet = _find_sheet(workbook, "kpov")
    if kpov_sheet is None:
        raise ImportError_("找不到「KPOV库-by 站」工作表")
    idx, rows, _ = _read_table(kpov_sheet, M.KPOV_COLUMNS, M.KPOV_REQUIRED, "kpov")
    kpov_count = 0
    seen_kpov: set[tuple[str, str]] = set()
    op_count = 0
    for row_no, row in enumerate(rows, start=2):
        data = _row_to_dict(row, idx)
        # OP 站沒有設備代碼，只要有站別就是有效列——不可用 equipment_code 當存在性判斷，
        # 否則 23 筆 OP 會被靜默丟棄。
        if not data.get("station"):
            continue
        attribute1 = data.get("attribute1") or "UNKNOWN"
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
                        "equipmentCode": data["equipment_code"],
                        "station": data.get("station"),
                        "smallY": data.get("small_y_score"),
                        "bigY": data.get("big_y_score"),
                        "sourceLevel": source,
                        "computedLevel": expected,
                    }
                )
        equipment_code = data.get("equipment_code")
        if equipment_code and equipment_code not in equipment_codes:
            report.unmatched_keys.append(
                {"table": "fact_kpov", "row": row_no, "equipmentCode": equipment_code}
            )

        session.add(FactKpov(batch_id=batch.id, level_baseline=level, level_mismatch=mismatch, **data))
        kpov_count += 1
    report.row_counts["kpov"] = kpov_count
    report.row_counts["kpovOp"] = op_count
    report.row_counts["kpovCtp"] = kpov_count - op_count

    # 5) 告警明細
    alarm_sheet = _find_sheet(workbook, "alarm")
    alarm_count = 0
    if alarm_sheet is not None:
        idx, rows, _ = _read_table(alarm_sheet, M.ALARM_COLUMNS, M.ALARM_REQUIRED, "alarm")
        buffer = []
        for row in rows:
            data = _row_to_dict(row, idx)
            if not data.get("equipment_code"):
                continue
            buffer.append(FactAlarm(batch_id=batch.id, **data))
            alarm_count += 1
            if len(buffer) >= 2000:
                session.bulk_save_objects(buffer)
                buffer.clear()
        if buffer:
            session.bulk_save_objects(buffer)
    report.row_counts["alarms"] = alarm_count

    # 6) 維修紀錄（只讀有表頭的欄位，字典欄位已在步驟 1 分開處理）
    idx, rows, _ = _read_table(repair_sheet, M.REPAIR_COLUMNS, M.REPAIR_REQUIRED, "repair")
    repairs: list[FactRepair] = []
    for row_no, row in enumerate(rows, start=2):
        data = _row_to_dict(row, idx)
        if not data.get("equipment_code") and not data.get("kpov_no"):
            continue  # 字典區的列，不是維修紀錄
        if not data.get("equipment_code") or not data.get("kpov_no"):
            report.skipped_repair_rows.append(
                {"row": row_no, "reason": "設備ID 或 KPOV 编号 缺值", "serialNo": data.get("serial_no")}
            )
            continue
        repair = FactRepair(batch_id=batch.id, **data)
        session.add(repair)
        repairs.append(repair)
    session.flush()
    report.row_counts["repairs"] = len(repairs)

    # 7) 等級異動事件
    derive_level_events(session, batch, repairs, method_scores, report)
    report.row_counts["levelEvents"] = len(report.level_events)
