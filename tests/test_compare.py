"""对比模块测试"""

from __future__ import annotations

import pytest

from reprochecker.compare.curve_compare import _dtw_distance, compare_curves
from reprochecker.compare.metric_compare import _normalize_name, compare_metrics
from reprochecker.compare.resource_compare import compare_resources, format_resource_summary


class TestMetricCompare:
    def test_exact_match(self) -> None:
        paper = [{"metric_name": "accuracy", "metric_value": 0.921}]
        actual = [{"metric_name": "accuracy", "metric_value": 0.921}]
        result = compare_metrics(paper, actual)
        assert len(result) == 1
        assert result[0]["relative_error"] == pytest.approx(0.0, abs=0.01)
        assert result[0]["within_tolerance"] is True
        assert result[0]["tolerance_band"] == "<1%"

    def test_5pct_error(self) -> None:
        paper = [{"metric_name": "accuracy", "metric_value": 92.0}]
        actual = [{"metric_name": "accuracy", "metric_value": 96.6}]  # ~5% error
        result = compare_metrics(paper, actual)
        assert result[0]["tolerance_band"] == "1-5%"

    def test_20pct_error(self) -> None:
        paper = [{"metric_name": "accuracy", "metric_value": 90.0}]
        actual = [{"metric_name": "accuracy", "metric_value": 70.0}]  # ~22% error
        result = compare_metrics(paper, actual)
        assert result[0]["tolerance_band"] == ">20%"
        assert result[0]["within_tolerance"] is False

    def test_missing_actual(self) -> None:
        paper = [{"metric_name": "accuracy", "metric_value": 92.0}]
        actual: list[dict] = []
        result = compare_metrics(paper, actual)
        assert result[0]["actual_value"] is None
        assert result[0]["within_tolerance"] is None

    def test_multiple_metrics(self) -> None:
        paper = [
            {"metric_name": "accuracy", "metric_value": 92.0},
            {"metric_name": "f1", "metric_value": 90.0},
            {"metric_name": "precision", "metric_value": 91.0},
        ]
        actual = [
            {"metric_name": "accuracy", "metric_value": 92.5},
            {"metric_name": "f1", "metric_value": 88.0},
            {"metric_name": "precision", "metric_value": 91.5},
        ]
        result = compare_metrics(paper, actual)
        assert len(result) == 3

    def test_normalize_aliases(self) -> None:
        assert _normalize_name("acc") == "accuracy"
        assert _normalize_name("f1-score") == "f1"
        assert _normalize_name("F1_Score") == "f1"  # alias: f1_score -> f1
        assert _normalize_name("top-1") == "accuracy"
        assert _normalize_name("map@50") == "map_50"

    def test_percentage_value_handling(self) -> None:
        """百分比值应当正确计算误差"""
        paper = [{"metric_name": "accuracy", "metric_value": 92.0}]
        actual = [{"metric_name": "accuracy", "metric_value": 93.0}]
        result = compare_metrics(paper, actual)
        assert result[0]["absolute_error"] == pytest.approx(1.0, abs=0.01)
        assert result[0]["relative_error"] == pytest.approx(1.09, abs=0.1)


class TestCurveCompare:
    def test_identical_curves(self) -> None:
        curve = [{"step": i, "value": 2.0 - i * 0.1} for i in range(20)]
        result = compare_curves(curve, curve)
        assert result["similarity"] > 0.95
        assert result["trend_match"] == "consistent"

    def test_empty_curves(self) -> None:
        result = compare_curves([], [])
        assert result["similarity"] == 0.0
        assert result["trend_match"] == "unknown"

    def test_dtw_distance(self) -> None:
        s = [1.0, 2.0, 3.0, 4.0]
        t = [1.0, 2.0, 3.0, 4.0]
        assert _dtw_distance(s, t) == pytest.approx(0.0)

        t2 = [1.5, 2.5, 3.5, 4.5]
        assert _dtw_distance(s, t2) > 0

    def test_overfit_detection(self) -> None:
        # 先降后大幅上升 = 过拟合
        values = [2.0 - i * 0.1 for i in range(15)] + [0.5 + i * 0.2 for i in range(15)]
        result = compare_curves(
            [{"step": i, "value": v} for i, v in enumerate(values)],
            [{"step": i, "value": v} for i, v in enumerate(values)],
        )
        assert result["overfit_detected"] is True

    def test_trend_divergence(self) -> None:
        paper = [{"step": i, "value": 2.0 - i * 0.1} for i in range(20)]
        actual = [{"step": i, "value": 0.5 + i * 0.1} for i in range(20)]
        result = compare_curves(paper, actual)
        assert result["trend_match"] == "divergent"


class TestResourceCompare:
    def test_params_match(self) -> None:
        paper = {"model_params": 25600000}
        actual = {"model_params": 25800000}
        result = compare_resources(paper, actual)
        assert "params" in result
        assert result["params"]["match"] is True

    def test_params_mismatch(self) -> None:
        paper = {"model_params": 25600000}
        actual = {"model_params": 30000000}
        result = compare_resources(paper, actual)
        assert result["params"]["match"] is False

    def test_empty_resources(self) -> None:
        result = compare_resources({}, {})
        assert result == {}

    def test_format_summary(self) -> None:
        comparison = {
            "params": {
                "paper": 25600000,
                "actual": 25800000,
                "diff": 200000,
                "diff_percent": 0.8,
                "match": True,
            },
        }
        summary = format_resource_summary(comparison)
        assert "25,600,000" in summary
        assert "✓" in summary
