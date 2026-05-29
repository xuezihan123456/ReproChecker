"""LLM 解析器和正则提取测试"""

from __future__ import annotations

import json

import pytest

from reprochecker.pdf.llm_parser import (
    _deduplicate_results,
    _normalize_result,
    _parse_llm_json,
    _to_float,
    parse_paper_results,
    parse_with_regex,
)


class TestToFloat:
    """数值转换测试"""

    def test_int(self) -> None:
        assert _to_float(42) == 42.0

    def test_float(self) -> None:
        assert _to_float(3.14) == pytest.approx(3.14)

    def test_string_number(self) -> None:
        assert _to_float("92.1") == pytest.approx(92.1)

    def test_string_percentage(self) -> None:
        assert _to_float("92.1%") == pytest.approx(92.1)

    def test_string_with_spaces(self) -> None:
        assert _to_float("  85.5  ") == pytest.approx(85.5)

    def test_invalid_string(self) -> None:
        assert _to_float("not_a_number") is None

    def test_none(self) -> None:
        assert _to_float(None) is None


class TestNormalizeResult:
    """结果规范化测试"""

    def test_valid_result(self) -> None:
        item = {
            "metric_name": "accuracy",
            "metric_value": 92.1,
            "method_name": "Ours",
            "is_best": True,
        }
        result = _normalize_result(item)
        assert result is not None
        assert result["metric_name"] == "accuracy"
        assert result["metric_value"] == pytest.approx(92.1)
        assert result["is_best"] is True

    def test_missing_metric_name(self) -> None:
        assert _normalize_result({"metric_value": 92.1}) is None

    def test_missing_metric_value(self) -> None:
        assert _normalize_result({"metric_name": "accuracy"}) is None

    def test_invalid_value(self) -> None:
        assert _normalize_result({"metric_name": "acc", "metric_value": "N/A"}) is None

    def test_best_marker_method(self) -> None:
        item = {"metric_name": "acc", "metric_value": 95.0, "method_name": "Ours"}
        result = _normalize_result(item)
        assert result is not None
        assert result["is_best"] is True

    def test_unknown_method(self) -> None:
        item = {"metric_name": "acc", "metric_value": 95.0}
        result = _normalize_result(item)
        assert result is not None
        assert result["method_name"] == "Unknown"


class TestParseLlmJson:
    """LLM JSON 解析测试"""

    def test_valid_json_array(self) -> None:
        content = json.dumps([
            {"metric_name": "accuracy", "metric_value": 92.1, "method_name": "Ours"}
        ])
        result = _parse_llm_json(content)
        assert len(result) == 1
        assert result[0]["metric_name"] == "accuracy"

    def test_wrapped_in_dict(self) -> None:
        content = json.dumps({
            "results": [
                {"metric_name": "accuracy", "metric_value": 92.1, "method_name": "Ours"}
            ]
        })
        result = _parse_llm_json(content)
        assert len(result) == 1

    def test_markdown_code_block(self) -> None:
        content = '```json\n[{"metric_name": "acc", "metric_value": 95, "method_name": "X"}]\n```'
        result = _parse_llm_json(content)
        assert len(result) == 1

    def test_invalid_json(self) -> None:
        assert _parse_llm_json("not json at all") is None

    def test_empty_array(self) -> None:
        assert _parse_llm_json("[]") is None


class TestParseWithRegex:
    """正则提取测试"""

    def test_empty_text(self) -> None:
        assert parse_with_regex("") == []
        assert parse_with_regex("   ") == []

    def test_key_value_format(self) -> None:
        text = "Accuracy: 92.1\nF1-score = 88.5\n"
        results = parse_with_regex(text)
        assert len(results) >= 1
        names = [r["metric_name"] for r in results]
        assert "accuracy" in names

    def test_percentage_format(self) -> None:
        text = "The accuracy achieved 95.3% on the test set."
        results = parse_with_regex(text)
        acc_results = [r for r in results if r["metric_name"] == "accuracy"]
        assert len(acc_results) >= 1
        assert acc_results[0]["metric_value"] == pytest.approx(95.3)

    def test_no_metrics(self) -> None:
        text = "This is just a regular paragraph with no numbers."
        results = parse_with_regex(text)
        assert results == []


class TestDeduplicateResults:
    """去重测试"""

    def test_removes_duplicates(self) -> None:
        items = [
            {"method_name": "Ours", "metric_name": "accuracy", "metric_value": 92.0},
            {"method_name": "Ours", "metric_name": "accuracy", "metric_value": 93.0},
        ]
        result = _deduplicate_results(items)
        assert len(result) == 1
        assert result[0]["metric_value"] == 92.0  # 保留第一条

    def test_different_metrics_kept(self) -> None:
        items = [
            {"method_name": "Ours", "metric_name": "accuracy", "metric_value": 92.0},
            {"method_name": "Ours", "metric_name": "f1", "metric_value": 88.0},
        ]
        result = _deduplicate_results(items)
        assert len(result) == 2


class TestParsePaperResults:
    """主入口测试"""

    def test_empty_text(self) -> None:
        assert parse_paper_results("") == []
        assert parse_paper_results("   ") == []

    def test_degrades_to_regex(self) -> None:
        """无 LLM 时应降级到正则方式"""
        text = "Accuracy: 92.1\nF1 = 88.5\n"
        results = parse_paper_results(text)
        assert len(results) >= 1
