"""报告生成器测试 — 覆盖 HTML / JSON / PDF 三种格式"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from reprochecker.report.generator import generate_report


def _sample_record() -> dict[str, Any]:
    return {
        "id": 1,
        "repo_url": "https://github.com/user/repo",
        "repo_name": "user/repo",
        "commit_hash": "abc123def456",
        "framework": "pytorch",
        "python_version": "3.10",
        "has_dockerfile": True,
        "has_requirements": True,
        "entry_script": "train.py",
        "has_seed": True,
        "env_method": "docker",
        "run_status": "success",
        "duration_sec": 360,
        "overall_score": 85.0,
        "grade": "B",
        "metric_score": 90.0,
        "env_score": 80.0,
        "code_score": 75.0,
        "created_at": "2026-05-28 10:00:00",
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


# ── HTML 报告 ─────────────────────────────────────────────────────────────────


class TestHtmlReport:
    """HTML 报告生成测试"""

    @patch("reprochecker.report.generator.db")
    def test_html_generation(self, mock_db: MagicMock, tmp_path: Path) -> None:
        """应生成有效的 HTML 文件"""
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = _sample_comparisons()
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="html", output_dir=tmp_path)

        assert path.exists()
        assert path.suffix == ".html"
        content = path.read_text(encoding="utf-8")
        assert "ReproChecker Report" in content
        assert "user/repo" in content
        mock_db.update_check.assert_called_once()

    @patch("reprochecker.report.generator.db")
    def test_html_contains_grade(self, mock_db: MagicMock, tmp_path: Path) -> None:
        """HTML 应包含等级信息"""
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="html", output_dir=tmp_path)
        content = path.read_text(encoding="utf-8")

        assert "B" in content  # grade


# ── JSON 报告 ─────────────────────────────────────────────────────────────────


class TestJsonReport:
    """JSON 报告生成测试"""

    @patch("reprochecker.report.generator.db")
    def test_json_generation(self, mock_db: MagicMock, tmp_path: Path) -> None:
        """应生成有效的 JSON 文件"""
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = _sample_comparisons()
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="json", output_dir=tmp_path)

        assert path.exists()
        assert path.suffix == ".json"

        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["check_id"] == 1
        assert data["repo_url"] == "https://github.com/user/repo"
        assert data["score"]["grade"] == "B"
        mock_db.update_check.assert_called_once()

    @patch("reprochecker.report.generator.db")
    def test_json_schema_version(self, mock_db: MagicMock, tmp_path: Path) -> None:
        """JSON 应包含 schema_version"""
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        path = generate_report(1, format="json", output_dir=tmp_path)

        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        assert "schema_version" in data


# ── PDF 报告 ──────────────────────────────────────────────────────────────────


class TestPdfReport:
    """PDF 报告生成测试"""

    @patch("reprochecker.report.generator.db")
    def test_pdf_raises_when_no_backend(self, mock_db: MagicMock, tmp_path: Path) -> None:
        """WeasyPrint 和 pdfkit 都不可用时应抛出 ImportError"""
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        import builtins

        real_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name in ("weasyprint", "pdfkit"):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            with pytest.raises(ImportError, match="weasyprint"):
                generate_report(1, format="pdf", output_dir=tmp_path)

    @patch("reprochecker.report.generator.db")
    def test_pdf_with_weasyprint(self, mock_db: MagicMock, tmp_path: Path) -> None:
        """WeasyPrint 可用时应生成 PDF"""
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        mock_html_instance = MagicMock()

        def weasy_write_pdf(dest: str) -> None:
            Path(dest).write_bytes(b"%PDF-1.4 fake")

        mock_html_instance.write_pdf.side_effect = weasy_write_pdf

        with patch.dict("sys.modules", {"weasyprint": MagicMock()}):
            import sys

            mock_weasyprint = sys.modules["weasyprint"]
            mock_weasyprint.HTML.return_value = mock_html_instance

            path = generate_report(1, format="pdf", output_dir=tmp_path)

            assert path.exists()
            assert path.suffix == ".pdf"
            mock_weasyprint.HTML.assert_called_once()
            mock_html_instance.write_pdf.assert_called_once()
            mock_db.update_check.assert_called_once()

    @patch("reprochecker.report.generator.db")
    def test_pdf_fallback_to_pdfkit(self, mock_db: MagicMock, tmp_path: Path) -> None:
        """WeasyPrint 不可用时应尝试 pdfkit"""
        mock_db.get_check.return_value = _sample_record()
        mock_db.get_comparisons.return_value = []
        mock_db.get_paper_results.return_value = []
        mock_db.get_actual_results.return_value = []

        import builtins

        real_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "weasyprint":
                raise ImportError("No module named 'weasyprint'")
            return real_import(name, *args, **kwargs)

        def pdfkit_from_string(html: str, dest: str, **kwargs: Any) -> None:
            Path(dest).write_bytes(b"%PDF-1.4 fake")

        with (
            patch("builtins.__import__", side_effect=mock_import),
            patch.dict("sys.modules", {"pdfkit": MagicMock()}),
        ):
            import sys

            mock_pdfkit = sys.modules["pdfkit"]
            mock_pdfkit.from_string.side_effect = pdfkit_from_string

            path = generate_report(1, format="pdf", output_dir=tmp_path)

            assert path.exists()
            assert path.suffix == ".pdf"
            mock_pdfkit.from_string.assert_called_once()
            mock_db.update_check.assert_called_once()

    @patch("reprochecker.report.generator.db")
    def test_pdf_nonexistent_check(self, mock_db: MagicMock, tmp_path: Path) -> None:
        """不存在的检验 ID 应抛出 ValueError"""
        mock_db.get_check.return_value = None

        with pytest.raises(ValueError, match="不存在"):
            generate_report(999, format="pdf", output_dir=tmp_path)
