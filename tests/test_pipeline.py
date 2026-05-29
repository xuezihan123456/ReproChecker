"""主流程编排器测试"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reprochecker.pipeline import _save_score


class TestSaveScore:
    """评分保存测试"""

    @patch("reprochecker.pipeline.db")
    def test_saves_all_score_fields(self, mock_db: MagicMock) -> None:
        score = {
            "overall": 85.0,
            "grade": "B",
            "metric_score": 90.0,
            "env_score": 70.0,
            "code_score": 80.0,
        }
        _save_score(1, score)
        mock_db.update_check.assert_called_once_with(
            1,
            overall_score=85.0,
            grade="B",
            metric_score=90.0,
            env_score=70.0,
            code_score=80.0,
        )

    @patch("reprochecker.pipeline.db")
    def test_skips_on_dry_run(self, mock_db: MagicMock) -> None:
        score = {
            "overall": 85.0,
            "grade": "B",
            "env_score": 70.0,
            "code_score": 80.0,
        }
        _save_score(1, score, dry_run=True)
        mock_db.update_check.assert_not_called()

    @patch("reprochecker.pipeline.db")
    def test_handles_missing_optional_fields(self, mock_db: MagicMock) -> None:
        score = {
            "overall": 50.0,
            "grade": "D",
            "env_score": 30.0,
            "code_score": 40.0,
        }
        _save_score(1, score)
        mock_db.update_check.assert_called_once_with(
            1,
            overall_score=50.0,
            grade="D",
            metric_score=None,
            env_score=30.0,
            code_score=40.0,
        )


class TestPipelineStageErrors:
    """阶段错误传播测试"""

    @patch("reprochecker.pipeline.db")
    @patch("reprochecker.repo.cloner.clone_repo")
    def test_clone_failure_marks_failed(
        self, mock_clone: MagicMock, mock_db: MagicMock
    ) -> None:
        mock_clone.side_effect = RuntimeError("网络错误")
        from reprochecker.pipeline import run_check

        with pytest.raises(RuntimeError, match="网络错误"):
            run_check(check_id=1, url="https://github.com/user/repo")

        calls = mock_db.update_check.call_args_list
        failed_calls = [c for c in calls if "failed" in str(c)]
        assert len(failed_calls) >= 1

    @patch("reprochecker.pipeline.db")
    @patch("reprochecker.repo.cloner.clone_repo")
    @patch("reprochecker.repo.analyzer.analyze_repo")
    def test_analysis_failure_marks_failed(
        self,
        mock_analyze: MagicMock,
        mock_clone: MagicMock,
        mock_db: MagicMock,
    ) -> None:
        mock_clone.return_value = (Path("/tmp/repo"), "abc123", "user/repo")
        mock_analyze.side_effect = RuntimeError("分析失败")
        from reprochecker.pipeline import run_check

        with pytest.raises(RuntimeError, match="分析失败"):
            run_check(check_id=1, url="https://github.com/user/repo")
