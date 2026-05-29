"""LaTeX 表格导出测试"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from reprochecker.report.latex import generate_latex


def _sample_record() -> dict[str, Any]:
    return {
        "id": 1,
        "repo_url": "https://github.com/user/repo",
        "repo_name": "user/repo",
        "commit_hash": "abc123def456",
        "framework": "pytorch",
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
            "metric_name": "f1_score",
            "paper_value": 88.5,
            "actual_value": 85.2,
            "relative_error": 3.7,
            "within_tolerance": False,
        },
    ]


class TestLatexExport:
    """LaTeX 导出测试"""

    @patch("reprochecker.report.latex.db")
    def test_tex_generation(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = _sample_comparisons()

        path = generate_latex(1, output_dir=tmp_path)

        assert path.exists()
        assert path.suffix == ".tex"
        mock_db.update_check.assert_called_once()

    @patch("reprochecker.report.latex.db")
    def test_tex_contains_begin_document(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []

        path = generate_latex(1, output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")

        assert r"\begin{table}" in content
        assert r"\end{table}" in content

    @patch("reprochecker.report.latex.db")
    def test_tex_contains_comparison_table(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = _sample_comparisons()

        path = generate_latex(1, output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")

        assert "accuracy" in content
        assert "f1\\_score" in content
        assert r"\checkmark" in content
        assert r"$\times$" in content

    @patch("reprochecker.report.latex.db")
    def test_tex_contains_scores(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []

        path = generate_latex(1, output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")

        assert "指标复现" in content
        assert "环境复现" in content
        assert "代码质量" in content
        assert "85" in content

    @patch("reprochecker.report.latex.db")
    def test_tex_nonexistent_check(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = None

        import pytest

        with pytest.raises(ValueError, match="不存在"):
            generate_latex(999, output_dir=tmp_path)

    @patch("reprochecker.report.latex.db")
    def test_tex_escapes_special_chars(self, mock_db: MagicMock, tmp_path: Path) -> None:
        record = _sample_record()
        record["repo_name"] = "user/repo_name"
        mock_db.get_check.return_value = record
        mock_db.get_comparisons.return_value = []

        path = generate_latex(1, output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")

        assert r"\_" in content

    @patch("reprochecker.report.latex.db")
    def test_tex_no_comparisons(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []

        path = generate_latex(1, output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")

        # 应有评分表但无对比表
        assert r"\begin{tabular}{lrl}" in content
