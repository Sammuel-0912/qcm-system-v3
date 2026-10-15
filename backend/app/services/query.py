"""篩選與彙總查詢 — spec.md §7 / §11.1（D-01 線別繼承）。"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DimEquipment, ImportBatch
from .lifecycle import KpovState, build_states, summarize


# 期間篩選：天／週／月／年 = 近 1／7／30／365 天
CHANGE_WINDOWS = {"day": 1, "week": 7, "month": 30, "year": 365}


def window_bounds(window: str | None) -> tuple[dt.datetime, dt.datetime] | None:
    """期間 -> (起, 迄)，UTC。window 為 None 表示不篩期間。"""
    if window is None:
        return None
    now = dt.datetime.now(dt.timezone.utc)
    return now - dt.timedelta(days=CHANGE_WINDOWS[window]), now


def in_bounds(value: dt.datetime | None, bounds: tuple[dt.datetime, dt.datetime] | None) -> bool:
    if bounds is None:
        return True
    if value is None:
        return False
    value = value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    return bounds[0] <= value <= bounds[1]


def active_batch(session: Session) -> ImportBatch | None:
    return session.scalars(
        select(ImportBatch).where(ImportBatch.is_active.is_(True)).order_by(ImportBatch.id.desc())
    ).first()


def _sort_key(value: str | None) -> str:
    """排序鍵：站別、線別等欄位可能為 None（OP 站無設備碼、來源資料缺漏），
    直接排序會在 None 與 str 比對時丟 TypeError，統一視為空字串排在最前。
    """
    return value or ""


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _is_op(state: KpovState) -> bool:
    # OP 站現在也有設備代碼（A000N），不能再以「沒有設備代碼」判斷
    return state.kpov.attribute1 == "OP" or not state.kpov.equipment_code


def equipment_index(session: Session, batch_id: int) -> dict[str, DimEquipment]:
    rows = session.scalars(select(DimEquipment).where(DimEquipment.batch_id == batch_id)).all()
    return {row.equipment_code: row for row in rows}


def apply_filters(
    session: Session,
    batch_id: int,
    states: list[KpovState],
    station: str | None,
    line: str | None,
    attribute: str | None = None,
    target: str | None = None,
) -> tuple[list[KpovState], dict]:
    """套用屬性／站別／線別／熱區目標篩選。

    D-01（REQ-LINE-01~03）：KPOV 的歸屬維度是「站別」，不是「線別」。
    線別篩選時先取該線別的設備 -> 反查其站別 -> 顯示這些站別的 KPOV。
    若該線別本身沒有 KPOV 定義（例如 DCS-PM2 的孿生設備），視為繼承同站別的定義。

    OP 人工站（設備 A0001–A0008 來自「設備對應參考」）不屬於任何線別，
    因此**不受線別篩選影響**（線別篩選只作用於 CTP）。
    """
    stations = _split(station)
    lines = _split(line)
    attributes = _split(attribute)
    meta: dict = {"inherited": False, "inheritedFrom": None, "inheritedStations": []}

    selected = states
    if attributes:
        selected = [s for s in selected if (s.kpov.attribute1 or "UNKNOWN") in set(attributes)]
    if stations:
        selected = [s for s in selected if s.kpov.station in set(stations)]

    # 熱區目標優先於站別篩選：點 layout 就是要看那一個站
    if target:
        selected = [s for s in selected if s.target_id == target]
        return selected, meta

    if lines:
        # OP 站不參與線別篩選，先抽出來稍後併回
        op_states = [s for s in selected if _is_op(s)]
        selected = [s for s in selected if not _is_op(s) and s.kpov.equipment_code]
        equipment = equipment_index(session, batch_id)
        line_set = set(lines)

        # 該線別上的設備
        codes_on_line = {code for code, eq in equipment.items() if eq.line in line_set}
        # 這些設備所屬的站別（透過 KPOV 庫反查）
        stations_on_line = {s.kpov.station for s in states if s.kpov.equipment_code in codes_on_line}

        direct = [s for s in selected if s.kpov.equipment_code in codes_on_line]
        if direct:
            selected = direct
        else:
            # 線別無自有 KPOV -> 繼承同站別定義
            equip_descs = {equipment[c].equipment_desc for c in codes_on_line if c in equipment}
            inherited_stations = sorted(
                {
                    s.kpov.station
                    for s in states
                    if s.kpov.equipment_code in equipment
                    and equipment[s.kpov.equipment_code].equipment_desc in equip_descs
                },
                key=_sort_key,
            )
            if inherited_stations:
                source_lines = sorted(
                    {
                        equipment[s.kpov.equipment_code].line
                        for s in states
                        if s.kpov.station in set(inherited_stations)
                        and s.kpov.equipment_code in equipment
                        and equipment[s.kpov.equipment_code].line not in line_set
                    },
                    key=_sort_key,
                )
                selected = [s for s in selected if s.kpov.station in set(inherited_stations)]
                meta = {
                    "inherited": True,
                    "inheritedFrom": source_lines[0] if source_lines else None,
                    "inheritedStations": inherited_stations,
                }
            else:
                selected = []
        if not meta["inherited"] and stations_on_line:
            meta["inheritedStations"] = sorted(stations_on_line, key=_sort_key)

        # OP 站與線別無關，併回結果
        selected = selected + op_states
        meta["opExemptFromLineFilter"] = len(op_states) > 0

    return selected, meta


def quadrant_payload(
    session: Session,
    batch_id: int,
    all_states: list[KpovState],
    station: str | None,
    line: str | None,
    view: str,
    attribute: str | None = None,
    target: str | None = None,
    start_states: list[KpovState] | None = None,
) -> dict:
    """象限圖。start_states 為期間第一天當時的狀態（build_states 的 as_of），
    有給時另回 start：同一組 KPOV 在期初的 Level 分佈，與 scope（現在）相減即期間內的淨變化。"""
    scoped, meta = apply_filters(session, batch_id, all_states, station, line, attribute, target)
    start = None
    if start_states is not None:
        start_scoped, _ = apply_filters(session, batch_id, start_states, station, line, attribute, target)
        start = summarize(start_scoped, "current")
    # 全廠基準沿用同一個屬性範圍，否則 CTP/OP 切換時比較基準會跳動
    plant, _ = apply_filters(session, batch_id, all_states, None, None, attribute, None)
    filtered = bool(_split(station) or _split(line) or target)
    deviation = sum(1 for s in scoped if s.deviates_from_baseline)
    return {
        "view": view,
        "scope": summarize(scoped, view),
        "plant": summarize(plant, view),
        "baseline": summarize(scoped, "baseline"),
        "start": start,
        "filtered": filtered,
        "deviationCount": deviation,
        "lineInheritance": meta,
    }


def trend_payload(
    session: Session,
    batch_id: int,
    all_states: list[KpovState],
    station: str | None,
    line: str | None,
    attribute: str | None = None,
    target: str | None = None,
    granularity: str = "month",
) -> dict:
    """等級異動趨勢 — 累計惡化數與累計改善數。

    刻意畫「累計」而非「當期新增」：目前維修紀錄稀疏（3 筆，集中在 1 個 KPOV），
    當期新增會是幾乎全零的折線，看起來像壞掉；累計線是一條有意義的階梯線。

    惡化／改善一律以 level 的變化判定（見 services/level.classify_transition），
    不可用單軸偵測度分數比大小——K00004 的案例中小y 3→7 變差、大Y 7→5 變好，
    只看單軸會得到相反的結論。
    """
    scoped, _ = apply_filters(session, batch_id, all_states, station, line, attribute, target)
    allowed = {(s.kpov.kpov_no, s.kpov.equipment_code) for s in scoped if s.kpov.equipment_code}
    has_equipment = bool(allowed)

    now = dt.datetime.now(dt.timezone.utc)
    buckets: dict[str, dict[str, int]] = {}
    for state in scoped:
        for event in state.events:
            if (state.kpov.kpov_no, state.kpov.equipment_code) not in allowed:
                continue
            effective = event.effective_at
            if effective.tzinfo is None:
                effective = effective.replace(tzinfo=dt.timezone.utc)
            # 預計改善（改善時間尚未到）不計入趨勢，到期後自然出現
            if effective > now:
                continue
            period = effective.strftime("%Y-%m") if granularity == "month" else effective.strftime("%Y-W%V")
            entry = buckets.setdefault(period, {"escalated": 0, "improved": 0})
            if event.transition == "ESCALATED":
                entry["escalated"] += 1
            elif event.transition == "IMPROVED":
                entry["improved"] += 1

    points = []
    cum_esc = cum_imp = 0
    for period in sorted(buckets):
        entry = buckets[period]
        cum_esc += entry["escalated"]
        cum_imp += entry["improved"]
        points.append(
            {
                "period": period,
                "escalated": entry["escalated"],
                "improved": entry["improved"],
                "escalatedCumulative": cum_esc,
                "improvedCumulative": cum_imp,
            }
        )

    reason = None
    if not points:
        reason = (
            "此站別沒有設備，等級異動需透過維修報表的設備 ID 建立"
            if not has_equipment
            else "此範圍尚無等級異動紀錄"
        )

    return {
        "granularity": granularity,
        "points": points,
        "totals": {"escalated": cum_esc, "improved": cum_imp},
        "emptyReason": reason,
    }
