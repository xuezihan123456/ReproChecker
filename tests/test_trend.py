"""趋势追踪测试"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from reprochecker.cli import app

runner = CliRunner()


class TestTrendCommand:
    """repro trend 命令测试"""

    def test_help(self) -> None:
        result = runner.invoke(app, ["trend", "--help"])
        assert result.exit_code == 0
        assert "trend" in result.output.lower() or "趋势" in result.output

    @patch("reprochecker.cli.db")
    def test_trend_shows_records(self, mock_db: MagicMock) -> None:
        mock_db.get_trend.return_value = [
            {
                "id": 1, "overall_score": 80.0, "grade": "B",
                "run_status": "success", "created_at": "2026-05-28",
                "metric_score": 85.0, "env_score": 75.0, "code_score": 70.0,
                "duration_sec": 300,
            },
            {
                "id": 2, "overall_score": 90.0, "grade": "A",
                "run_status": "success", "created_at": "2026-05-29",
                "metric_score": 95.0, "env_score": 85.0, "code_score": 80.0,
                "duration_sec": 250,
            },
        ]

        result = runner.invoke(app, ["trend", "https://github.com/user/repo"])
        assert result.exit_code == 0
        mock_db.get_trend.assert_called_once()

    @patch("reprochecker.cli.db")
    def test_trend_empty(self, mock_db: MagicMock) -> None:
        mock_db.get_trend.return_value = []
        mock_db.list_checks.return_value = []

        result = runner.invoke(app, ["trend", "https://github.com/user/repo"])
        assert result.exit_code == 0
        assert "未找到" in result.output

    @patch("reprochecker.cli.db")
    def test_trend_with_limit(self, mock_db: MagicMock) -> None:
        mock_db.get_trend.return_value = []
        mock_db.list_checks.return_value = []

        result = runner.invoke(app, ["trend", "user/repo", "-n", "5"])
        assert result.exit_code == 0


class TestDbTrend:
    """Database.get_trend 测试"""

    def test_get_trend(self, tmp_path: Path) -> None:
        from reprochecker.storage.db import Database

        db_path = tmp_path / "test.db"
        db = Database(db_path)

        # 创建多条记录
        for i in range(3):
            cid = db.create_check(
                repo_url="https://github.com/user/repo",
                pdf_path=None,
            )
            db.update_check(
                cid,
                run_status="success",
                overall_score=80.0 + i * 5,
                grade="B" if i < 2 else "A",
            )

        trend = db.get_trend("https://github.com/user/repo")
        assert len(trend) == 3
        # 应按时间正序（最旧在前）
        assert trend[0]["overall_score"] == 80.0
        assert trend[-1]["overall_score"] == 90.0

    def test_get_trend_limit(self, tmp_path: Path) -> None:
        from reprochecker.storage.db import Database

        db_path = tmp_path / "test.db"
        db = Database(db_path)

        for i in range(5):
            cid = db.create_check(
                repo_url="https://github.com/user/repo",
                pdf_path=None,
            )
            db.update_check(cid, run_status="success", overall_score=float(i * 10))

        trend = db.get_trend("https://github.com/user/repo", limit=3)
        assert len(trend) == 3

    def test_get_trend_empty(self, tmp_path: Path) -> None:
        from reprochecker.storage.db import Database

        db_path = tmp_path / "test.db"
        db = Database(db_path)

        trend = db.get_trend("https://github.com/nonexistent/repo")
        assert trend == []
