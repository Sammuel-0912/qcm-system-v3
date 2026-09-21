"""spec.md §2.4 驗證表格逐列測試 + §3.6 異動判定。"""
from __future__ import annotations

import pytest

from app.services.level import classify_transition, compute_level

# (小y, 大Y, 期望等級) — 取自 spec.md §2.4，涵蓋現有 244 筆資料的全部組合
SPEC_TABLE = [
    (1, 1, 0),
    (3, 5, 0),
    (3, 7, 1),
    (4, 7, 1),
    (5, 7, 1),
    (7, 7, 3),
]


@pytest.mark.parametrize("small_y,big_y,expected", SPEC_TABLE)
def test_spec_table(small_y, big_y, expected):
    assert compute_level(small_y, big_y) == expected


def test_threshold_boundary():
    """切點必須落在 5/6 之間（spec.md §2.1）。"""
    assert compute_level(5, 5) == 0
    assert compute_level(6, 5) == 2
    assert compute_level(5, 6) == 1
    assert compute_level(6, 6) == 3


def test_level2_quadrant_exists():
    """Level 2 = 小y 低、大Y 高（左上象限）。"""
    assert compute_level(7, 1) == 2


@pytest.mark.parametrize("small_y,big_y", [(None, 1), (1, None), (None, None)])
def test_missing_scores_are_unrated(small_y, big_y):
    assert compute_level(small_y, big_y) is None


@pytest.mark.parametrize(
    "before,after,expected",
    [
        (1, 2, "ESCALATED"),   # spec.md §3.5 K00004 的 DEGRADE
        (2, 0, "IMPROVED"),    # spec.md §3.5 K00004 的 IMPROVE
        (0, 3, "ESCALATED"),
        (3, 3, "UNCHANGED"),
        (1, 1, "UNCHANGED"),
        (None, 2, "UNCHANGED"),
    ],
)
def test_classify_transition(before, after, expected):
    assert classify_transition(before, after) == expected


def test_severity_order_level2_worse_than_level1():
    """spec.md §2.6：0 < 1 < 2 < 3，Level 2 比 Level 1 嚴重。"""
    assert classify_transition(1, 2) == "ESCALATED"
    assert classify_transition(2, 1) == "IMPROVED"
