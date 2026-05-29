"""CSV 导出测试"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from reprochecker.report.generator import generate_report


def _sample_record() -> dict[str, Any]:
    return {
        "id": 1,
        "repo_url": "https://github.com/user/repo",
        "repo_name": "user/repo",
        "commit_hash": "abc123def456",
        "framework": "pytorch",
        "entry_script": "train.py",
        "env_method": "docker",
        "overall_score": 85.0,
        "grade": "B",
        "metric_score": 90.0,
        "env_score": 80.0,
        "code_score": 75.0,
        "duration_sec": 360,
        "created_at": "2026-05-29 10:00:00",
    }


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
            "metric_name": "loss",
            "paper_value": 0.05,
            "actual_value": 0.08,
            "relative_error": 60.0,
            "within_tolerance": False,
        },
    ]


class TestCsvExport:
    """CSV 报告生成测试"""

    @patch("reprochecker.report.generator.db")
    def test_csv_generation(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = _sample_comparisons()
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="csv", output_dir=tmp_path)

        assert path.exists()
        assert path.suffix == ".csv"
        mock_db.update_check.assert_called_once()

    @patch("reprochecker.report.generator.db")
    def test_csv_contains_summary(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="csv", output_dir=tmp_path)
        content = path.read_text(encoding="utf-8-sig")

        assert "检验摘要" in content
        assert "user/repo" in content
        assert "B" in content
        assert "85" in content

    @patch("reprochecker.report.generator.db")
    def test_csv_contains_comparisons(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = _sample_comparisons()
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="csv", output_dir=tmp_path)
        content = path.read_text(encoding="utf-8-sig")

        assert "指标对比" in content
        assert "accuracy" in content
        assert "loss" in content

    @patch("reprochecker.report.generator.db")
    def test_csv_contains_actual_results(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = [
            {"metric_name": "acc", "metric_value": 0.95, "epoch": 10, "step": 1000},
        ]

        path = generate_report(1, format="csv", output_dir=tmp_path)
        content = path.read_text(encoding="utf-8-sig")

        assert "捕获的指标" in content
        assert "acc" in content

    @patch("reprochecker.report.generator.db")
    def test_csv_valid_format(self, mock_db: MagicMock, tmp_path: Path) -> None:
        """CSV 应该是有效的 CSV 格式"""
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = _sample_comparisons()
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="csv", output_dir=tmp_path)

        # 应该能被 csv 模块解析
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) > 10  # 至少有摘要行 + 对比行

    @patch("reprochecker.report.generator.db")
    def test_csv_utf8_bom(self, mock_db: MagicMock, tmp_path: Path) -> None:
        """CSV 应包含 UTF-8 BOM，方便 Excel 打开"""
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="csv", output_dir=tmp_path)
        raw = path.read_bytes()
        assert raw[:3] == b"\xef\xbb\xbf"  # UTF-8 BOM
