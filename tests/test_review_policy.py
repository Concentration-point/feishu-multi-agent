from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import (
    REVIEW_PASS_THRESHOLD_DEFAULT,
    REVIEW_RED_FLAG_KEYWORDS,
    REVIEW_THRESHOLDS_BY_PROJECT_TYPE,
)


def _contains_red_flag_for_test(text: str) -> bool:
    normalized = (text or "").strip()
    return any(keyword in normalized for keyword in REVIEW_RED_FLAG_KEYWORDS)


def test_project_type_threshold_mapping():
    assert REVIEW_THRESHOLDS_BY_PROJECT_TYPE["电商大促"] == 0.6
    assert REVIEW_THRESHOLDS_BY_PROJECT_TYPE["新品发布"] == 0.7
    assert REVIEW_THRESHOLDS_BY_PROJECT_TYPE["品牌传播"] == 0.7
    assert REVIEW_PASS_THRESHOLD_DEFAULT == 0.6


def test_red_flag_detection_keywords():
    assert _contains_red_flag_for_test("存在严重合规风险，建议驳回") is True
    assert _contains_red_flag_for_test("该内容存在虚假宣传风险") is True
    assert _contains_red_flag_for_test("整体可发布，仅建议优化标题") is False
