"""徽章生成器测试"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reprochecker.report.badge import generate_badge, generate_badge_svg


class TestGenerateBadgeSvg:
    """SVG 字符串生成测试"""

    def test_grade_a(self) -> None:
        svg = generate_badge_svg("A", 95.0)
        assert "A" in svg
        assert "95/100" in svg
        assert svg.startswith("<svg")
        assert "#22c55e" in svg  # A 级绿色

    def test_grade_f(self) -> None:
        svg = generate_badge_svg("F", 20.0)
        assert "F" in svg
        assert "20/100" in svg
        assert "#ef4444" in svg  # F 级红色

    def test_grade_b_color(self) -> None:
        svg = generate_badge_svg("B", 80.0)
        assert "#3b82f6" in svg  # B 级蓝色

    def test_unknown_grade(self) -> None:
        svg = generate_badge_svg("?", 0)
        assert "?" in svg
        assert "#6b7280" in svg  # 灰色

    def test_custom_repo_name(self) -> None:
        svg = generate_badge_svg("A", 95.0, repo_name="user/repo")
        assert "user/repo" in svg

    def test_score_formatting(self) -> None:
        svg = generate_badge_svg("B", 85.7)
        assert "86/100" in svg  # 四舍五入

    def test_valid_svg_structure(self) -> None:
        svg = generate_badge_svg("C", 70.0)
        assert "</svg>" in svg
        assert "xmlns=" in svg


class TestGenerateBadge:
    """徽章文件生成测试"""

    @patch("reprochecker.report.badge.db")
    def test_generates_svg_file(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = {
            "id": 1,
            "repo_name": "user/repo",
            "grade": "A",
            "overall_score": 95.0,
        }

        path = generate_badge(1, output_path=tmp_path / "badge.svg")

        assert path.exists()
        assert path.suffix == ".svg"
        content = path.read_text(encoding="utf-8")
        assert "<svg" in content
        assert "A" in content

    @patch("reprochecker.report.badge.db")
    def test_nonexistent_check_raises(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = None
        with pytest.raises(ValueError, match="不存在"):
            generate_badge(999, output_path=tmp_path / "badge.svg")

    @patch("reprochecker.report.badge.db")
    def test_creates_parent_dirs(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = {
            "id": 1,
            "repo_name": "",
            "grade": "B",
            "overall_score": 80.0,
        }

        nested = tmp_path / "a" / "b" / "badge.svg"
        path = generate_badge(1, output_path=nested)
        assert path.exists()

    @patch("reprochecker.report.badge.db")
    def test_handles_missing_grade(self, mock_db: MagicMock, tmp_path: Path) -> None:
        mock_db.get_check.return_value = {
            "id": 1,
            "repo_name": "",
            "grade": None,
            "overall_score": None,
        }

        path = generate_badge(1, output_path=tmp_path / "badge.svg")
        content = path.read_text(encoding="utf-8")
        assert "F" in content  # grade=None -> "F"
        assert "0/100" in content  # score=None -> 0
