"""等級生命週期 — spec.md §3。

現況等級的推算刻意放在應用層（而非 SQL view），以維持 SQLite 與 PostgreSQL
的行為一致；原規格 §5.4 使用 PostgreSQL 專有的 LATERAL join，不可攜。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import FactKpov, FactLevelEvent

VIEW_BASELINE = "baseline"
VIEW_CURRENT = "current"
VIEW_TARGET = "target"
VIEWS = (VIEW_BASELINE, VIEW_CURRENT, VIEW_TARGET)


@dataclass(slots=True)
class KpovState:
    """單一 (KPOV × 設備) 在某口徑下的狀態。"""

    kpov: FactKpov
    level_baseline: int | None
    level_current: int | None
    level_target: int | None
    small_y_current: int | None
    big_y_current: int | None
    last_event: FactLevelEvent | None
    events: list[FactLevelEvent]

    @property
    def deviates_from_baseline(self) -> bool:
        return self.last_event is not None and self.level_current != self.level_baseline

    def level_for(self, view: str) -> int | None:
        if view == VIEW_BASELINE:
            return self.level_baseline
        if view == VIEW_TARGET:
            return self.level_target
        return self.level_current

    @property
    def is_escalated_open(self) -> bool:
        """惡化中：現況等級比基準嚴重（spec.md REQ-UI-18 / §2.6）。

        刻意比對「現況 vs 基準」，而非最後一筆事件的 transition：
        同一 (KPOV, 設備) 若有多張維修單宣告同一項改善，最後一筆會是
        UNCHANGED，但該 KPOV 實際上仍相對基準有變化。
        """
        if self.level_current is None or self.level_baseline is None:
            return False
        return self.level_current > self.level_baseline

    @property
    def is_improved(self) -> bool:
        """已改善：現況等級優於基準。"""
        if self.level_current is None or self.level_baseline is None:
            return False
        return self.level_current < self.level_baseline


def _event_sort_key(event: FactLevelEvent) -> tuple[dt.datetime, int]:
    effective = event.effective_at
    if effective.tzinfo is None:
        effective = effective.replace(tzinfo=dt.timezone.utc)
    return (effective, event.id or 0)


def build_states(
    session: Session,
    batch_id: int,
    *,
    as_of: dt.datetime | None = None,
) -> list[KpovState]:
    """組出該批次所有 KPOV 的基準／現況／目標等級。"""
    as_of = as_of or dt.datetime.now(dt.timezone.utc)

    kpovs = session.scalars(select(FactKpov).where(FactKpov.batch_id == batch_id)).all()
    events = session.scalars(
        select(FactLevelEvent).where(FactLevelEvent.batch_id == batch_id)
    ).all()

    by_target: dict[tuple[str, str], list[FactLevelEvent]] = {}
    for event in events:
        by_target.setdefault((event.kpov_no, event.equipment_code), []).append(event)
    for bucket in by_target.values():
        bucket.sort(key=_event_sort_key)

    states: list[KpovState] = []
    for kpov in kpovs:
        bucket = by_target.get((kpov.kpov_no or "", kpov.equipment_code), [])
        effective = [e for e in bucket if _event_sort_key(e)[0] <= as_of]
        last = effective[-1] if effective else None

        # 目標口徑：最近一筆 IMPROVE 事件宣告要達到的等級；沒有則同現況
        target_event = next((e for e in reversed(bucket) if e.event_type == "IMPROVE"), None)

        states.append(
            KpovState(
                kpov=kpov,
                level_baseline=kpov.level_baseline,
                level_current=last.level_after if last else kpov.level_baseline,
                level_target=target_event.level_after if target_event else (last.level_after if last else kpov.level_baseline),
                small_y_current=last.small_y_score_after if last else kpov.small_y_score,
                big_y_current=last.big_y_score_after if last else kpov.big_y_score,
                last_event=last,
                events=bucket,
            )
        )
    return states


def summarize(states: list[KpovState], view: str) -> dict[str, int]:
    """彙總成象限／柱狀圖用的數字。"""
    counts = {f"level{i}": 0 for i in range(4)}
    unrated = 0
    for state in states:
        level = state.level_for(view)
        if level is None:
            unrated += 1
        else:
            counts[f"level{level}"] += 1
    counts["unrated"] = unrated
    counts["total"] = len(states)
    return counts
