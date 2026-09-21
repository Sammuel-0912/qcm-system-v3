"""等級異動事件推導 — spec.md §3.4。

一筆維修紀錄最多產生兩筆事件：
  DEGRADE — 依「變化後」偵測方式，生效時間 = 測試時間（不良被發現的時刻）
  IMPROVE — 依「提升後」偵測方式，生效時間 = 改善生效日，無則取匯入批次時間
            （不得使用「修復時間」，那是 touchup 完工時間，見 REQ-LIFE-04 / D-03）

事件以 (維修序號, KPOV編號, 設備代碼, 事件類型) 為自然鍵去重（REQ-LIFE-05）。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FactKpov, FactLevelEvent, FactRepair, ImportBatch
from ..services.level import classify_transition, compute_level


def _resolve(method: str | None, method_scores: dict[str, int]) -> tuple[str, int] | None:
    if not method:
        return None
    name = method.strip()
    if name not in method_scores:
        return None
    return name, method_scores[name]


def derive_level_events(
    session: Session,
    batch: ImportBatch,
    repairs: list[FactRepair],
    method_scores: dict[str, int],
    report,
) -> None:
    batch_time = batch.imported_at or dt.datetime.now(dt.timezone.utc)

    # 該批次 KPOV 基準，供第一筆事件取 before 值
    baseline: dict[tuple[str, str], FactKpov] = {}
    for kpov in session.scalars(select(FactKpov).where(FactKpov.batch_id == batch.id)):
        baseline[(kpov.kpov_no or "", kpov.equipment_code)] = kpov

    # --- 階段一：蒐集候選事件（尚未決定 before 值）---------------------------
    # 必須先全部蒐集、再依 effective_at 全域排序，才能正確串接前後狀態。
    # 若按維修紀錄逐筆處理，一筆較早不良的 IMPROVE（生效於匯入時間）會被
    # 提前套用到另一筆較晚不良的 DEGRADE 之前，算出錯誤的 level_before。
    candidates: list[dict] = []
    seen_keys: set[tuple] = set()

    for repair in repairs:
        key = (repair.kpov_no or "", repair.equipment_code or "")
        if key not in baseline:
            report.unmatched_keys.append(
                {
                    "table": "fact_level_event",
                    "serialNo": repair.serial_no,
                    "kpovNo": repair.kpov_no,
                    "equipmentCode": repair.equipment_code,
                    "reason": "維修紀錄的 KPOV × 設備 組合在 KPOV 庫中不存在",
                }
            )
            continue

        plan = [
            ("DEGRADE", repair.small_y_method_after, repair.big_y_method_after, repair.tested_at or batch_time),
            (
                "IMPROVE",
                repair.small_y_method_improved,
                repair.big_y_method_improved,
                repair.improvement_effective_at or batch_time,
            ),
        ]

        for event_type, small_method, big_method, effective_at in plan:
            small = _resolve(small_method, method_scores)
            big = _resolve(big_method, method_scores)

            # 有填但查不到字典 -> 錯誤報告，不得以 0 帶過（REQ-DICT-02）
            for raw, resolved, axis in ((small_method, small, "小y"), (big_method, big, "大Y")):
                if raw and resolved is None:
                    report.unknown_detection_methods.append(
                        {
                            "serialNo": repair.serial_no,
                            "kpovNo": repair.kpov_no,
                            "equipmentCode": repair.equipment_code,
                            "eventType": event_type,
                            "axis": axis,
                            "method": raw,
                        }
                    )
            if small is None or big is None:
                continue

            dedupe_key = (repair.serial_no, repair.kpov_no, repair.equipment_code, event_type)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)

            level_after = compute_level(small[1], big[1])
            if level_after is None:
                continue

            candidates.append(
                {
                    "key": key,
                    "repair": repair,
                    "event_type": event_type,
                    "effective_at": effective_at,
                    "small": small,
                    "big": big,
                    "level_after": level_after,
                }
            )

    # --- 階段二：依生效時間全域排序，串接 before 值 --------------------------
    def order(candidate: dict):
        effective = candidate["effective_at"]
        if effective.tzinfo is None:
            effective = effective.replace(tzinfo=dt.timezone.utc)
        # 同一時刻時，DEGRADE 先於 IMPROVE；再以維修發生時間與序號穩定排序
        type_rank = 0 if candidate["event_type"] == "DEGRADE" else 1
        repair = candidate["repair"]
        tested = repair.tested_at or effective
        if tested.tzinfo is None:
            tested = tested.replace(tzinfo=dt.timezone.utc)
        return (effective, type_rank, tested, repair.serial_no or "")

    state: dict[tuple[str, str], dict] = {}

    def current_state(key: tuple[str, str]) -> dict:
        if key not in state:
            kpov = baseline.get(key)
            state[key] = {
                "small_y_method": None,
                "small_y_score": kpov.small_y_score if kpov else None,
                "big_y_method": None,
                "big_y_score": kpov.big_y_score if kpov else None,
                "level": kpov.level_baseline if kpov else None,
            }
        return state[key]

    for candidate in sorted(candidates, key=order):
        key = candidate["key"]
        repair = candidate["repair"]
        small = candidate["small"]
        big = candidate["big"]
        level_after = candidate["level_after"]
        before = current_state(key)
        transition = classify_transition(before["level"], level_after)

        session.add(
            FactLevelEvent(
                batch_id=batch.id,
                kpov_no=repair.kpov_no,
                equipment_code=repair.equipment_code,
                event_type=candidate["event_type"],
                effective_at=candidate["effective_at"],
                small_y_method_before=before["small_y_method"],
                small_y_score_before=before["small_y_score"],
                big_y_method_before=before["big_y_method"],
                big_y_score_before=before["big_y_score"],
                level_before=before["level"],
                small_y_method_after=small[0],
                small_y_score_after=small[1],
                big_y_method_after=big[0],
                big_y_score_after=big[1],
                level_after=level_after,
                transition=transition,
                repair_id=repair.id,
                repair_serial=repair.serial_no,
                defect_desc=repair.defect_desc,
                improvement=repair.improvement if candidate["event_type"] == "IMPROVE" else None,
            )
        )
        report.level_events.append(
            {
                "kpovNo": repair.kpov_no,
                "equipmentCode": repair.equipment_code,
                "eventType": candidate["event_type"],
                "effectiveAt": candidate["effective_at"].isoformat(),
                "levelBefore": before["level"],
                "levelAfter": level_after,
                "transition": transition,
                "serialNo": repair.serial_no,
            }
        )

        state[key] = {
            "small_y_method": small[0],
            "small_y_score": small[1],
            "big_y_method": big[0],
            "big_y_score": big[1],
            "level": level_after,
        }

    session.flush()
