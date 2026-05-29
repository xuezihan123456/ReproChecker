"""共享测试夹具与辅助工厂函数"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ── 数据工厂 ─────────────────────────────────────────────────────────────────


def sample_record(check_id: int = 1, **overrides: Any) -> dict[str, Any]:
    """构造一条检验记录的字典，可按需覆盖字段。"""
    base: dict[str, Any] = {
        "id": check_id,
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
        "exit_code": 0,
        "duration_sec": 360.5,
        "overall_score": 85.0,
        "grade": "B",
        "metric_score": 90.0,
        "env_score": 80.0,
        "code_score": 75.0,
        "created_at": "2026-05-28 10:00:00",
    }
    base.update(overrides)
    return base


def sample_comparisons() -> list[dict[str, Any]]:
    """构造两条指标对比记录。"""
    return [
        {
            "metric_name": "accuracy",
            "paper_value": 92.1,
            "actual_value": 93.3,
            "relative_error": 1.3,
            "within_tolerance": True,
        },
        {
            "metric_name": "f1",
            "paper_value": 90.0,
            "actual_value": 85.0,
            "relative_error": 5.56,
            "within_tolerance": False,
        },
    ]


def sample_stats() -> dict[str, Any]:
    """构造统计概览字典。"""
    return {
        "total": 5,
        "success": 3,
        "success_rate": 0.6,
        "grades": {"A": 1, "B": 2, "C": 1, "F": 1},
        "avg_score": 72.3,
        "avg_duration_sec": 300.0,
        "top_repos": [
            {"name": "user/repo", "count": 3},
            {"name": "other/project", "count": 2},
        ],
    }


# ── 共享夹具 ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_db() -> MagicMock:
    """提供一个完全模拟的 Database 实例，注入到 cli 模块。"""
    db = MagicMock()
    db.create_check.return_value = 1
    db.get_check.return_value = sample_record(1)
    db.list_checks.return_value = [sample_record(1)]
    db.get_comparisons.return_value = []
    db.get_stats.return_value = sample_stats()
    db.delete_check.return_value = None
    return db


def patch_db(mock_db_fixture: MagicMock):
    """在 cli 模块上替换 db 对象的上下文管理器。"""
    return patch("reprochecker.cli.db", mock_db_fixture)
