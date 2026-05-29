"""Markdown 报告测试"""

from __future__ import annotations

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
        "has_dockerfile": True,
        "has_requirements": True,
        "has_seed": True,
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
    ]


class TestMarkdownReport:
    """Markdown 报告生成测试"""

    @patch("reprochecker.report.generator.db")
    def test_md_generation(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = _sample_comparisons()
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="md", output_dir=tmp_path)

        assert path.exists()
        assert path.suffix == ".md"
        mock_db.update_check.assert_called_once()

    @patch("reprochecker.report.generator.db")
    def test_md_contains_header(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="md", output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")

        assert "# " in content
        assert "ReproChecker" in content
        assert "user/repo" in content

    @patch("reprochecker.report.generator.db")
    def test_md_contains_scores(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="md", output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")

        assert "指标复现" in content
        assert "环境复现" in content
        assert "代码质量" in content

    @patch("reprochecker.report.generator.db")
    def test_md_contains_comparisons(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = _sample_comparisons()
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="md", output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")

        assert "accuracy" in content
        assert "指标对比" in content

    @patch("reprochecker.report.generator.db")
    def test_md_contains_code_quality(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="md", output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")

        assert "requirements.txt" in content
        assert "Dockerfile" in content

    @patch("reprochecker.report.generator.db")
    def test_md_grade_emoji(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="md", output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")

        assert "🔵" in content  # B 级蓝色圆
