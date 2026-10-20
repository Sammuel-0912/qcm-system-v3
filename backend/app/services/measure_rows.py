"""四張措施表（高風險、已改善、製程問題追蹤、客訴問題追蹤）共用的列格式。

欄位：高風險站別｜高風險KPOV｜Level 等級變化(原)｜緊急措施（＋緊急措施時間）｜長期措施（＋改善時間）｜
      措施層別｜Level 等級變化(變化後)｜改善時間｜客訴筆數

1019 版起（spec.md v2.0）：
  - 緊急措施 ＝ 修護報表 BM／BN（客訴報表「緊急措施／緊急措施時間」）
  - 長期措施 ＝ 改善措施／改善時間（修護報表 BR／BQ；客訴報表同名欄）
  - 措施層別 ＝ 8D 區塊的管理解／技術解欄位，一律唯讀（不再提供系統內手動分類）
維修列：
  - Level(原)      ＝ 該筆維修的惡化事件（DEGRADE）前 → 後
  - Level(變化後)  ＝ 該筆維修的改善事件（IMPROVE）前 → 後；改善時間未到標示預計
客訴列：
  - Level(原)      ＝ 改善前等級；Level(變化後) ＝ 改善前 → 改善後
  - 改善時間       ＝ 改善時間欄；沒有時以實際完成時間（未完成以預計代替並標示）
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..importer.mapping import REPAIR_EIGHT_D_PREFIX
from ..models import FactComplaint, FactLevelEvent, FactRepair
from .lifecycle import KpovState

# 客訴筆數：維修列尚未定義對應規則，先固定 0（使用者指定）
REPAIR_COMPLAINT_PLACEHOLDER = 0


def utc(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value


def _iso(value: dt.datetime | None) -> str | None:
    value = utc(value)
    return value.isoformat() if value else None


def events_by_repair(session: Session, batch_id: int) -> dict[int, dict[str, FactLevelEvent]]:
    """repair_id -> {"DEGRADE": 事件, "IMPROVE": 事件}"""
    out: dict[int, dict[str, FactLevelEvent]] = {}
    for e in session.scalars(
        select(FactLevelEvent).where(FactLevelEvent.batch_id == batch_id, FactLevelEvent.repair_id.is_not(None))
    ):
        out.setdefault(e.repair_id, {})[e.event_type] = e
    return out


def _change(event: FactLevelEvent | None, now: dt.datetime) -> dict | None:
    if event is None:
        return None
    at = utc(event.effective_at)
    return {"before": event.level_before, "after": event.level_after, "planned": bool(at and at > now)}


def _measure(text: str | None, at: dt.datetime | None) -> dict:
    return {"text": text, "at": _iso(at)}


def repair_row(
    repair: FactRepair,
    state: KpovState | None,
    events: dict[str, FactLevelEvent],
    *,
    now: dt.datetime,
) -> dict:
    degrade = events.get("DEGRADE")
    improve = events.get("IMPROVE")
    improve_at = utc(improve.effective_at) if improve else utc(repair.improvement_effective_at)
    return {
        "station": state.kpov.station if state else repair.station,
        "kpovNo": repair.kpov_no,
        "kpovName": state.kpov.kpov_name if state else None,
        "equipmentCode": repair.equipment_code,
        "mapped": state is not None,
        "levelOrig": _change(degrade, now),
        "emergency": _measure(repair.emergency_measure, repair.emergency_measure_at),
        "longTerm": _measure(repair.improvement, repair.improvement_effective_at),
        "layer": {"summary": layer_summary(repair, REPAIR_EIGHT_D_PREFIX)},
        "levelChanged": _change(improve, now),
        "improvedAt": _iso(improve_at),
        "improvePlanned": bool(improve_at and improve_at > now),
        "improveOverdue": False,
        "complaintCount": REPAIR_COMPLAINT_PLACEHOLDER,
        "repairSerial": repair.serial_no,
        "repairId": repair.id,
        "complaintId": None,
        "occurredAt": _iso(repair.tested_at),
    }


def layer_summary(record, prefix: str = "") -> str | None:
    """8D 區塊的管理解／技術解欄位 -> 「管理解／技術解・KPOV：設計消除、設備攔截；KPIV：防呆防錯」。

    客訴與維修共用；維修的 8D 欄位有 d8_ 前綴。欄位有填內容（非空）即視為採用。
    """
    def has(field: str) -> bool:
        return bool(getattr(record, prefix + field, None))

    tech = []
    if has("tech_ccsc_interception"):
        tech.append("CC/SC：設備攔截")
    kpov = [label for label, f in (("設計消除", "tech_kpov_design_elimination"), ("設備攔截", "tech_kpov_interception")) if has(f)]
    if kpov:
        tech.append(f"KPOV：{'、'.join(kpov)}")
    kpiv = [label for label, f in (("防呆防錯", "tech_kpiv_foolproof"), ("智能監控", "tech_kpiv_smart")) if has(f)]
    if kpiv:
        tech.append(f"KPIV：{'、'.join(kpiv)}")
    parts = []
    if has("mgmt_measure"):
        parts.append("管理解")
    if tech:
        parts.append("技術解・" + "；".join(tech))
    return "／".join(parts) or None


def complaint_row(items: list[FactComplaint], state: KpovState | None, mapped_key: bool, now: dt.datetime) -> dict:
    """同一（設備, KPOV）或（製程單元, 產品KPOV）的客訴合併成一列，內容取最新一筆。"""
    latest = items[-1]
    improved = utc(latest.improvement_effective_at) or utc(latest.done_at)
    planned = utc(latest.planned_at)
    shown = improved or planned
    return {
        "station": state.kpov.station if state else latest.process_unit,
        "kpovNo": latest.kpov_no if mapped_key else None,
        "kpovName": state.kpov.kpov_name if state else latest.product_kpov,
        "equipmentCode": latest.equipment_code if mapped_key else None,
        "mapped": mapped_key and state is not None,
        "levelOrig": (
            {"before": None, "after": latest.level_before, "planned": False}
            if latest.level_before is not None
            else None
        ),
        "emergency": _measure(latest.emergency_measure, latest.emergency_measure_at),
        "longTerm": _measure(latest.improvement, latest.improvement_effective_at),
        "layer": {"summary": layer_summary(latest)},
        "levelChanged": (
            {"before": latest.level_before, "after": latest.level_after, "planned": improved is None}
            if latest.level_after is not None
            else None
        ),
        "improvedAt": _iso(shown),
        "improvePlanned": improved is None and shown is not None,
        # 實際完成未填且預計完成已過：逾期
        "improveOverdue": improved is None and planned is not None and planned < now,
        "complaintCount": len(items),
        "repairSerial": None,
        "repairId": None,
        "complaintId": latest.id,
        "occurredAt": _iso(latest.complained_at),
    }
