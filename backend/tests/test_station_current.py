"""製程柱狀圖的「現況（KPOV 項數）」檢視（v2.21，spec §27）：各站加總要與四象限的現況分佈一致。"""
from __future__ import annotations

from tests.test_rbac import ADMIN, V1026, XLSX, app_ctx, needs_data  # noqa: F401  (app_ctx 為 fixture)


def _sum_current(events: dict) -> dict[str, int]:
    out = {f"level{i}": 0 for i in range(4)}
    for s in events["stations"]:
        for i in range(4):
            out[f"level{i}"] += s["current"][str(i)]
    return out


def _assert_matches_quadrant(su, **filters):
    events = su.get("/api/v1/station-levels/events", params={"window": "year", **filters}).json()
    scope = su.get("/api/v1/quadrant", params={"view": "current", **filters}).json()["scope"]
    sums = _sum_current(events)
    assert sums == {k: scope[k] for k in sums}, filters
    assert sum(sums.values()) + events["unknownLevel"]["current"] == scope["total"], filters
    return events


@needs_data
def test_current_view_matches_quadrant(app_ctx):
    su = app_ctx(ADMIN)
    res = su.post("/api/v1/import", files={"file": ("WJ1-DCS-PM1-數據庫-1026.xlsx", V1026.read_bytes(), XLSX)})
    assert res.status_code == 200, res.text

    year = _assert_matches_quadrant(su)
    assert sum(_sum_current(year).values()) > 0

    filters = su.get("/api/v1/filters").json()
    station = filters["stations"][0]
    _assert_matches_quadrant(su, station=station["code"], attribute=station["attribute"])
    _assert_matches_quadrant(su, attribute=station["attribute"])
    if filters["lines"]:
        _assert_matches_quadrant(su, line=filters["lines"][0]["code"])

    # 現況不分期間；維修筆數（發生當時）照舊依期間
    day = su.get("/api/v1/station-levels/events", params={"window": "day"}).json()
    assert [s["current"] for s in day["stations"]] == [s["current"] for s in year["stations"]]
    total = lambda ev: sum(sum(s["repairs"].values()) for s in ev["stations"])  # noqa: E731
    assert total(day) <= total(year)


@needs_data
def test_kpov_map_current_matches_quadrant(app_ctx):
    """站別 Level 分佈／風險地圖的「現況」（v2.22，spec §28）：全線加總＝四象限現況；基準照舊。"""
    su = app_ctx(ADMIN)
    res = su.post("/api/v1/import", files={"file": ("WJ1-DCS-PM1-數據庫-1026.xlsx", V1026.read_bytes(), XLSX)})
    assert res.status_code == 200, res.text

    kpov = su.get("/api/v1/station-levels/kpov").json()
    scope = su.get("/api/v1/quadrant", params={"view": "current"}).json()["scope"]
    current = {f"level{i}": sum(s["current"][str(i)] for s in kpov["stations"]) for i in range(4)}
    assert current == {k: scope[k] for k in current}
    assert sum(current.values()) + kpov["unratedCurrent"] == scope["total"]

    # 與製程柱狀圖「現況」（不篩選）逐站一致
    events = su.get("/api/v1/station-levels/events", params={"window": "year"}).json()
    by_code = {s["equipmentCode"]: s["current"] for s in events["stations"]}
    for s in kpov["stations"]:
        assert s["current"] == by_code.get(s["equipmentCode"], s["current"])

    # 基準（counts）總數不變：每個 KPOV 都算在基準或現況其中一邊的總數裡
    baseline_total = sum(sum(s["counts"].values()) for s in kpov["stations"]) + kpov["unrated"]
    assert baseline_total == sum(current.values()) + kpov["unratedCurrent"]
