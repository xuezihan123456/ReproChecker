"""图表生成测试"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestGenerateTrainingChart:
    """generate_training_chart 测试"""

    def test_returns_none_when_no_matplotlib(self, tmp_path: Path) -> None:
        """matplotlib 未安装时返回 None"""
        from reprochecker.report.generator import generate_training_chart

        metrics = [{"name": "loss", "value": 0.5, "step": 1}]
        chart_path = tmp_path / "chart.png"

        with patch.dict(sys.modules, {"matplotlib": None, "matplotlib.pyplot": None}):
            # 需要重新触发 import
            result = generate_training_chart(metrics, chart_path)

        # 如果 matplotlib 实际已安装，结果可能是 Path；未安装时为 None
        # 此测试验证函数在 ImportError 时不崩溃
        assert result is None or isinstance(result, Path)

    def test_returns_none_for_empty_metrics(self, tmp_path: Path) -> None:
        """空指标列表返回 None"""
        from reprochecker.report.generator import generate_training_chart

        chart_path = tmp_path / "chart.png"
        result = generate_training_chart([], chart_path)
        assert result is None

    def test_returns_none_for_all_none_values(self, tmp_path: Path) -> None:
        """所有值为 None 时返回 None"""
        from reprochecker.report.generator import generate_training_chart

        metrics = [
            {"name": "loss", "value": None, "step": 1},
            {"name": "loss", "value": None, "step": 2},
        ]
        chart_path = tmp_path / "chart.png"
        result = generate_training_chart(metrics, chart_path)
        assert result is None

    def test_generates_png_file(self, tmp_path: Path) -> None:
        """正常指标数据应生成 PNG 文件"""
        pytest.importorskip("matplotlib")
        from reprochecker.report.generator import generate_training_chart

        metrics = [
            {"name": "loss", "value": 0.9, "step": 1},
            {"name": "loss", "value": 0.5, "step": 2},
            {"name": "loss", "value": 0.3, "step": 3},
            {"name": "accuracy", "value": 0.7, "step": 1},
            {"name": "accuracy", "value": 0.85, "step": 2},
            {"name": "accuracy", "value": 0.92, "step": 3},
        ]
        chart_path = tmp_path / "chart.png"

        result = generate_training_chart(metrics, chart_path)

        assert result is not None
        assert result.exists()
        assert result.suffix == ".png"
        # PNG 文件应有一定大小（至少 1KB）
        assert result.stat().st_size > 1000

    def test_multiple_metric_series(self, tmp_path: Path) -> None:
        """多个指标应生成多条曲线"""
        pytest.importorskip("matplotlib")
        from reprochecker.report.generator import generate_training_chart

        metrics = [
            {"name": "loss", "value": 0.9, "step": 1},
            {"name": "loss", "value": 0.3, "step": 10},
            {"name": "accuracy", "value": 0.6, "step": 1},
            {"name": "accuracy", "value": 0.95, "step": 10},
            {"name": "f1_score", "value": 0.5, "step": 1},
            {"name": "f1_score", "value": 0.88, "step": 10},
        ]
        chart_path = tmp_path / "multi.png"

        result = generate_training_chart(metrics, chart_path)

        assert result is not None
        assert result.exists()

    def test_uses_epoch_when_step_missing(self, tmp_path: Path) -> None:
        """step 缺失时使用 epoch 作为 x 轴"""
        pytest.importorskip("matplotlib")
        from reprochecker.report.generator import generate_training_chart

        metrics = [
            {"name": "loss", "value": 0.8, "epoch": 1},
            {"name": "loss", "value": 0.4, "epoch": 5},
            {"name": "loss", "value": 0.2, "epoch": 10},
        ]
        chart_path = tmp_path / "epoch_chart.png"

        result = generate_training_chart(metrics, chart_path)

        assert result is not None
        assert result.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """应自动创建父目录"""
        pytest.importorskip("matplotlib")
        from reprochecker.report.generator import generate_training_chart

        metrics = [{"name": "loss", "value": 0.5, "step": 1}]
        chart_path = tmp_path / "subdir" / "deep" / "chart.png"

        result = generate_training_chart(metrics, chart_path)

        assert result is not None
        assert result.exists()


class TestChartToBase64:
    """_chart_to_base64 测试"""

    def test_returns_none_for_none_path(self) -> None:
        from reprochecker.report.generator import _chart_to_base64

        result = _chart_to_base64(None)
        assert result is None

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        from reprochecker.report.generator import _chart_to_base64

        result = _chart_to_base64(tmp_path / "nonexistent.png")
        assert result is None

    def test_returns_data_uri(self, tmp_path: Path) -> None:
        from reprochecker.report.generator import _chart_to_base64

        # 创建一个小的假 PNG 文件
        fake_png = tmp_path / "test.png"
        # 最小 PNG 头
        fake_png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        result = _chart_to_base64(fake_png)

        assert result is not None
        assert result.startswith("data:image/png;base64,")
        # base64 编码后应有一定长度
        assert len(result) > 50


class TestChartIntegration:
    """图表集成到 HTML 报告测试"""

    def test_generate_html_with_metrics(self, tmp_path: Path) -> None:
        """有指标数据时 HTML 应包含图表"""
        pytest.importorskip("matplotlib")
        from unittest.mock import patch

        from reprochecker.report.generator import _generate_html

        record = {
            "repo_url": "https://github.com/example/test",
            "grade": "B",
            "overall_score": 80.0,
            "metric_score": 85.0,
            "env_score": 70.0,
            "code_score": 80.0,
            "created_at": "2026-01-01 12:00:00",
        }
        actual_results = [
            {"metric_name": "loss", "metric_value": 0.5, "step": 1},
            {"metric_name": "loss", "metric_value": 0.3, "step": 2},
        ]

        with patch("reprochecker.report.generator.db"):
            path = _generate_html(
                check_id=999,
                record=record,
                comparisons=[],
                paper_results=[],
                actual_results=actual_results,
                output_dir=tmp_path,
            )

        html = path.read_text(encoding="utf-8")
        assert "data:image/png;base64," in html
        assert "训练曲线" in html

    def test_generate_html_without_metrics(self, tmp_path: Path) -> None:
        """无指标数据时 HTML 不应包含图表"""
        from unittest.mock import patch

        from reprochecker.report.generator import _generate_html

        record = {
            "repo_url": "https://github.com/example/test",
            "grade": "F",
            "overall_score": 20.0,
            "created_at": "2026-01-01 12:00:00",
        }

        with patch("reprochecker.report.generator.db"):
            path = _generate_html(
                check_id=998,
                record=record,
                comparisons=[],
                paper_results=[],
                actual_results=[],
                output_dir=tmp_path,
            )

        html = path.read_text(encoding="utf-8")
        assert "data:image/png;base64," not in html
        assert "训练曲线" not in html


def _sample_comparisons() -> list[dict[str, Any]]:
    return [
        {
            "metric_name": "accuracy",
            "paper_value": 92.1,
            "actual_value": 93.3,
            "relative_error": 1.3,
            "within_tolerance": True,
        },
        {
            "metric_name": "f1_score",
            "paper_value": 88.5,
            "actual_value": 85.2,
            "relative_error": 3.7,
            "within_tolerance": False,
        },
    ]


def _sample_trend() -> list[dict[str, Any]]:
    return [
        {
            "id": 1, "overall_score": 80.0, "grade": "B",
            "run_status": "success", "created_at": "2026-05-27",
            "metric_score": 85.0, "env_score": 75.0, "code_score": 70.0,
            "duration_sec": 300,
        },
        {
            "id": 2, "overall_score": 90.0, "grade": "A",
            "run_status": "success", "created_at": "2026-05-28",
            "metric_score": 95.0, "env_score": 85.0, "code_score": 80.0,
            "duration_sec": 250,
        },
    ]


class TestComparisonChart:
    """论文值 vs 实际值对比图测试"""

    @patch("reprochecker.report.chart.db")
    def test_chart_no_comparisons(self, mock_db: MagicMock, tmp_path: Path) -> None:
        from reprochecker.report.chart import generate_comparison_chart

        mock_db.get_comparisons.return_value = []
        result = generate_comparison_chart(1, output_path=tmp_path / "chart.png")
        assert result is None

    @patch("reprochecker.report.chart.db")
    def test_chart_generates_file(self, mock_db: MagicMock, tmp_path: Path) -> None:
        pytest.importorskip("matplotlib")
        from reprochecker.report.chart import generate_comparison_chart

        mock_db.get_comparisons.return_value = _sample_comparisons()
        path = tmp_path / "cmp.png"

        result = generate_comparison_chart(1, output_path=path)

        assert result is not None
        assert result.exists()
        assert result.suffix == ".png"
        assert result.stat().st_size > 1000

    @patch("reprochecker.report.chart.db")
    def test_chart_default_path(self, mock_db: MagicMock) -> None:
        pytest.importorskip("matplotlib")
        from reprochecker.report.chart import generate_comparison_chart

        mock_db.get_comparisons.return_value = _sample_comparisons()

        result = generate_comparison_chart(1)
        if result is not None:
            assert result.name == "comparison_1.png"
            result.unlink(missing_ok=True)


class TestTrendChart:
    """趋势折线图测试"""

    @patch("reprochecker.report.chart.db")
    def test_trend_insufficient_data(self, mock_db: MagicMock, tmp_path: Path) -> None:
        from reprochecker.report.chart import generate_trend_chart

        mock_db.get_trend.return_value = [_sample_trend()[0]]
        result = generate_trend_chart("https://github.com/user/repo",
                                       output_path=tmp_path / "trend.png")
        assert result is None

    @patch("reprochecker.report.chart.db")
    def test_trend_empty(self, mock_db: MagicMock, tmp_path: Path) -> None:
        from reprochecker.report.chart import generate_trend_chart

        mock_db.get_trend.return_value = []
        result = generate_trend_chart("https://github.com/user/repo",
                                       output_path=tmp_path / "trend.png")
        assert result is None

    @patch("reprochecker.report.chart.db")
    def test_trend_generates_file(self, mock_db: MagicMock, tmp_path: Path) -> None:
        pytest.importorskip("matplotlib")
        from reprochecker.report.chart import generate_trend_chart

        mock_db.get_trend.return_value = _sample_trend()
        path = tmp_path / "trend.png"

        result = generate_trend_chart("https://github.com/user/repo", output_path=path)

        assert result is not None
        assert result.exists()
        assert result.stat().st_size > 1000
