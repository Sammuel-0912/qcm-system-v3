"""等級異動事件推導 — spec.md §3.4。

一筆維修紀錄最多產生兩筆事件：
  DEGRADE — 依「變化後」偵測方式，生效時間 = 測試時間（不良被發現的時刻）
  IMPROVE — 依「提升後」偵測方式，生效時間 = 修護報表的「改善時間」
            （不得使用「修復時間」，那是 touchup 完工時間，見 REQ-LIFE-04 / D-03）。
            改善時間晚於現在者為「預計改善」：事件照樣入帳，但現況等級要到該時間才採用
            （見 lifecycle.build_states 的 as_of）。
            來源檔有「改善時間」欄但該列沒填 -> 不產生 IMPROVE，列入匯入報告；
            只有完全沒有此欄的舊版檔案，才退回以匯入批次時間代替。

事件以 (維修序號, KPOV編號, 設備代碼, 事件類型) 為自然鍵去重（REQ-LIFE-05）。

PCN（v2.19，spec §25）：PCN 紀錄的「切入後」小y／大Y 也產生一筆事件，生效時間 = 切入時間，
與維修事件一起依時間排序串接前後等級，現況取最後一筆。事件的 note 記 "PCN#<變更紀錄 id>"，
時間軸用它把事件對回 PCN 紀錄。同一時刻的排序：PCN → DEGRADE → IMPROVE（變更先切入，之後才觀察到不良）。
"""
from __future__ import annotations

import datetime as dt
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FactChangeRecord, FactKpov, FactLevelEvent, FactRepair, ImportBatch
from ..services.level import classify_transition, compute_level


def _aware(value: dt.datetime) -> dt.datetime:
    """比較用：不帶時區的時間視為 UTC（SQLite 讀回與 Excel 解析的時間都不帶時區）。"""
    return value.replace(tzinfo=dt.timezone.utc) if value.tzinfo is None else value


def _resolve(method: str | None, method_scores: dict[str, int]) -> tuple[str, int] | None:
    if not method:
        return None
    name = method.strip()
    if name not in method_scores:
        return None
    return name, method_scores[name]


_EVENT_RANK = {"PCN": 0, "DEGRADE": 1, "IMPROVE": 2}


def _pcn_axis(value: str | None, method_scores: dict[str, int], by_score: dict[int, list[str]]) -> tuple[str, int] | None:
    """PCN 的偵測度欄：通常是分數（"5.0"），也接受偵測方式名稱。回傳（顯示用方式名稱, 分數）。"""
    if value is None or str(value).strip() == "":
        return None
    text_ = str(value).strip()
    try:
        score = int(float(text_))
    except ValueError:
        return _resolve(text_, method_scores)
    if not 1 <= score <= 10:
        return None
    names = by_score.get(score, [])
    return (names[0] if len(names) == 1 else f"偵測度 {score}"), score


def _pcn_level_text(value: str | None) -> int | None:
    match = re.search(r"\d", value or "")
    return int(match.group()) if match else None


def _pcn_targets(record: FactChangeRecord, baseline: dict[tuple[str, str], FactKpov]) -> list[tuple[str, str]]:
    """PCN 對應的 KPOV：有設備ID 以（KPOV 編號, 設備ID），沒有則以（KPOV 編號, 站別）——與時間軸相同（§13.8）。"""
    if not record.kpov_no:
        return []
    if record.equipment_code:
        key = (record.kpov_no, record.equipment_code)
        return [key] if key in baseline else []
    if not record.station:
        return []
    return [key for key, kpov in baseline.items() if key[0] == record.kpov_no and kpov.station == record.station]


def _pcn_label(record: FactChangeRecord, kpov: FactKpov | None) -> str:
    day = record.effective_at.date().isoformat() if record.effective_at else "日期未填"
    station = (kpov.station if kpov else None) or record.station or ""
    return f"PCN（{day}）{station} · {record.kpov_no} × {record.equipment_code or '—'}"


def derive_level_events(
    session: Session,
    batch: ImportBatch,
    repairs: list[FactRepair],
    method_scores: dict[str, int],
    report,
    *,
    improve_time_fallback: bool = True,
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
        ]
        improve_at = repair.improvement_effective_at or (batch_time if improve_time_fallback else None)
        degrade_at = repair.tested_at
        if improve_at is not None and degrade_at is not None and _aware(improve_at) < _aware(degrade_at):
            # 改善時間多半只填日期（00:00），當天稍晚才發現的不良會排到改善之後，
            # 現況就停在惡化後的等級。同一筆維修的改善不可能早於它的不良，以不良時間為下限。
            improve_at = degrade_at
        if improve_at is not None:
            plan.append(("IMPROVE", repair.small_y_method_improved, repair.big_y_method_improved, improve_at))
        elif repair.small_y_method_improved or repair.big_y_method_improved:
            report.warnings.append(
                f"維修紀錄 {repair.serial_no or '（無序號）'} · {repair.kpov_no} 有改善後偵測方式但未填改善時間，"
                "未產生改善事件"
            )

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

    # PCN：切入後的偵測度計入等級（v2.19）
    by_score: dict[int, list[str]] = {}
    for name, score in method_scores.items():
        by_score.setdefault(score, []).append(name)
    pcn_records = session.scalars(
        select(FactChangeRecord)
        .where(FactChangeRecord.batch_id == batch.id, FactChangeRecord.kind == "PCN")
        .order_by(FactChangeRecord.effective_at, FactChangeRecord.id)
    ).all()
    for record in pcn_records:
        targets = _pcn_targets(record, baseline)
        if not targets or record.effective_at is None:
            continue
        small = _pcn_axis(record.small_y_after, method_scores, by_score)
        big = _pcn_axis(record.big_y_after, method_scores, by_score)
        if small is None or big is None:
            report.warnings.append(
                f"{_pcn_label(record, baseline.get(targets[0]))}：切入後偵測度未填或無法辨識，未計入等級"
            )
            continue
        level_after = compute_level(small[1], big[1])
        if level_after is None:
            continue
        small_before = _pcn_axis(record.small_y_before, method_scores, by_score)
        big_before = _pcn_axis(record.big_y_before, method_scores, by_score)
        stated_before = (
            compute_level(small_before[1], big_before[1])
            if small_before and big_before
            else _pcn_level_text(record.level_before)
        )
        for key in targets:
            candidates.append(
                {
                    "key": key,
                    "pcn": record,
                    "event_type": "PCN",
                    "effective_at": record.effective_at,
                    "small": small,
                    "big": big,
                    "level_after": level_after,
                    "stated_before": stated_before,
                }
            )

    # --- 階段二：依生效時間全域排序，串接 before 值 --------------------------
    def order(candidate: dict):
        effective = candidate["effective_at"]
        if effective.tzinfo is None:
            effective = effective.replace(tzinfo=dt.timezone.utc)
        # 同一時刻時：PCN → DEGRADE → IMPROVE；再以維修發生時間與序號（PCN 以紀錄 id）穩定排序
        type_rank = _EVENT_RANK[candidate["event_type"]]
        repair = candidate.get("repair")
        if repair is None:
            return (effective, type_rank, effective, f"{candidate['pcn'].id:09d}")
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

    stated_mismatch: list[str] = []
    for candidate in sorted(candidates, key=order):
        key = candidate["key"]
        repair = candidate.get("repair")
        pcn = candidate.get("pcn")
        small = candidate["small"]
        big = candidate["big"]
        level_after = candidate["level_after"]
        before = current_state(key)
        transition = classify_transition(before["level"], level_after)

        if pcn is not None:
            label = _pcn_label(pcn, baseline.get(key))
            stated = candidate["stated_before"]
            if stated is not None and before["level"] is not None and stated != before["level"]:
                stated_mismatch.append(f"{label}（PCN 填 Level {stated}，系統 Level {before['level']}）")
            if transition == "ESCALATED":
                report.warnings.append(
                    f"{label}：切入後 Level {level_after} 比當時的 Level {before['level']} 差，"
                    "現況會變差，請確認 PCN 的切入後偵測度"
                )

        session.add(
            FactLevelEvent(
                batch_id=batch.id,
                kpov_no=key[0],
                equipment_code=key[1],
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
                repair_id=repair.id if repair else None,
                repair_serial=repair.serial_no if repair else None,
                defect_desc=repair.defect_desc if repair else None,
                improvement=(
                    repair.improvement
                    if repair and candidate["event_type"] == "IMPROVE"
                    else (pcn.content if pcn else None)
                ),
                note=f"PCN#{pcn.id}" if pcn is not None else None,
            )
        )
        report.level_events.append(
            {
                "kpovNo": key[0],
                "equipmentCode": key[1],
                "eventType": candidate["event_type"],
                "effectiveAt": candidate["effective_at"].isoformat(),
                "levelBefore": before["level"],
                "levelAfter": level_after,
                "transition": transition,
                "serialNo": repair.serial_no if repair else None,
            }
        )

        state[key] = {
            "small_y_method": small[0],
            "small_y_score": small[1],
            "big_y_method": big[0],
            "big_y_score": big[1],
            "level": level_after,
        }

    if stated_mismatch:
        # 常見於 KPOV 庫已更新成 PCN 後的偵測度、PCN 表的「切入前」仍是舊值；筆數多，彙總成一則
        examples = "；".join(stated_mismatch[:5])
        more = f"…等 {len(stated_mismatch)} 筆" if len(stated_mismatch) > 5 else ""
        report.warnings.append(
            f"有 {len(stated_mismatch)} 筆 PCN 的「切入前」等級與系統當時的等級（KPOV 庫基準或之前的維修／PCN）不同，"
            f"前後等級以系統為準：{examples}{more}"
        )

    session.flush()


def rederive_batch_events(session: Session, batch: ImportBatch, report, *, drop: FactRepair | None = None) -> int:
    """刪除維修紀錄（v2.20，spec §26）：移除 drop 後，以批次中剩下的維修與 PCN 重新推導全部等級事件。

    匯入時的 improve_time_fallback（修護報表沒有「改善時間」欄的舊檔）沒有存下來，由既有事件反推：
    有 IMPROVE 事件的維修卻沒有改善時間，就是當時用了匯入時間代替。回傳重算後的事件數。
    """
    from ..models import DimDetectionMethod

    events = session.scalars(select(FactLevelEvent).where(FactLevelEvent.batch_id == batch.id)).all()
    repairs = list(
        session.scalars(select(FactRepair).where(FactRepair.batch_id == batch.id).order_by(FactRepair.id))
    )
    by_id = {r.id: r for r in repairs}
    fallback = any(
        e.event_type == "IMPROVE" and e.repair_id in by_id and by_id[e.repair_id].improvement_effective_at is None
        for e in events
    )
    for event in events:
        session.delete(event)
    session.flush()  # 事件參照維修，先刪事件再刪維修
    if drop is not None:
        session.delete(drop)
        session.flush()
        repairs = [r for r in repairs if r.id != drop.id]
    method_scores = {
        m.method_name: m.score
        for m in session.scalars(select(DimDetectionMethod).where(DimDetectionMethod.batch_id == batch.id))
    }
    derive_level_events(session, batch, repairs, method_scores, report, improve_time_fallback=fallback)
    return len(report.level_events)
