"""品控力等級判定 — spec.md §2.3。

這是全系統唯一計算等級的地方。任何其他模組都必須呼叫 compute_level()，
不得自行以分數比大小推導等級。
"""
from __future__ import annotations

from ..config import DETECTION_THRESHOLD

# 象限配色 — spec.md §2.2 / §8.2，與 gemini-svg.svg 逐字相符
LEVEL_COLORS: dict[int, str] = {
    0: "#BFFFDA",
    1: "#C5E9FF",
    2: "#F3EA95",
    3: "#FFCCFF",
}

# 嚴重度排序 — spec.md §2.6：0 < 1 < 2 < 3
LEVEL_SEVERITY: dict[int, int] = {0: 0, 1: 1, 2: 2, 3: 3}

LEVEL_DESCRIPTIONS: dict[int, dict[str, str]] = {
    0: {"smallY": "y 100%機測", "bigY": "Y 100%機測"},
    1: {"smallY": "y 100%機測", "bigY": "Y 人檢/機測(未證實可靠)"},
    2: {"smallY": "y 人檢/機測(未證實可靠)", "bigY": "Y 100%機測"},
    3: {"smallY": "y 人檢/機測(未證實可靠)", "bigY": "Y 人檢/機測(未證實可靠)"},
}


def is_high_detection(score: int | None) -> bool | None:
    """偵測能力是否為「高」。分數越小能力越強，切點為 5/6（spec.md §2.1）。"""
    if score is None:
        return None
    return score <= DETECTION_THRESHOLD


def compute_level(small_y: int | None, big_y: int | None) -> int | None:
    """依兩軸偵測度回傳品控力等級 0~3；任一軸缺值回傳 None（未評估）。

    象限（spec.md §2.2）：
        小y高 + 大Y高 -> Level 0   (右上)
        小y高 + 大Y低 -> Level 1   (右下)
        小y低 + 大Y高 -> Level 2   (左上)
        小y低 + 大Y低 -> Level 3   (左下)
    """
    y_high = is_high_detection(small_y)
    big_high = is_high_detection(big_y)
    if y_high is None or big_high is None:
        return None
    if y_high and big_high:
        return 0
    if y_high and not big_high:
        return 1
    if not y_high and big_high:
        return 2
    return 3


def classify_transition(level_before: int | None, level_after: int) -> str:
    """判定異動方向 — spec.md §3.6。依 §2.6 嚴重度排序，非象限位置。"""
    if level_before is None:
        return "UNCHANGED"
    before = LEVEL_SEVERITY[level_before]
    after = LEVEL_SEVERITY[level_after]
    if after > before:
        return "ESCALATED"
    if after < before:
        return "IMPROVED"
    return "UNCHANGED"
