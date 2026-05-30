"""CLI 集成测试 — 覆盖 reprochecker.cli 全部 7 个命令"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from reprochecker.cli import app
from tests.conftest import patch_db, sample_comparisons, sample_record, sample_stats

runner = CliRunner()

# 向后兼容别名 —— 现有测试代码继续使用 _sample_record 等名称
_sample_record = sample_record
_sample_comparisons = sample_comparisons
_sample_stats = sample_stats
_patch_db = patch_db


# ── 1. repro check ───────────────────────────────────────────────────────────


class TestCheckCommand:
    """repro check 命令测试"""

    def test_help(self) -> None:
        """check --help 应显示用法说明"""
        result = runner.invoke(app, ["check", "--help"])
        assert result.exit_code == 0
        assert "执行可复现性检验" in result.output or "GitHub" in result.output

    @patch("reprochecker.cli.db")
    @patch("reprochecker.pipeline.run_check")
    def test_check_success(self, mock_run: MagicMock, mock_cli_db: MagicMock) -> None:
        """正常执行应创建记录并调用 run_check"""
        mock_run.return_value = None
        mock_cli_db.create_check.return_value = 1
        result = runner.invoke(app, ["check", "https://github.com/user/repo"])

        assert result.exit_code == 0, result.output
        mock_cli_db.create_check.assert_called_once_with(
            repo_url="https://github.com/user/repo",
            pdf_path=None,
        )
        mock_run.assert_called_once()
        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs["check_id"] == 1

    @patch("reprochecker.cli.db")
    @patch("reprochecker.pipeline.run_check")
    def test_check_with_all_options(self, mock_run: MagicMock, mock_cli_db: MagicMock) -> None:
        """传入所有选项时应正确转发"""
        mock_run.return_value = None
        mock_cli_db.create_check.return_value = 1
        pdf_path = Path("/tmp/paper.pdf")
        result = runner.invoke(
            app,
            [
                "check",
                "https://github.com/user/repo",
                "--pdf",
                str(pdf_path),
                "--cmd",
                "python run.py",
                "--env",
                "conda",
                "--timeout",
                "3600",
                "--gpu",
                "1",
                "--seed",
                "123",
                "--no-cache",
                "--name",
                "MyExperiment",
            ],
        )

        assert result.exit_code == 0, result.output
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["url"] == "https://github.com/user/repo"
        assert call_kwargs["pdf_path"] == pdf_path
        assert call_kwargs["cmd"] == "python run.py"
        assert call_kwargs["env"] == "conda"
        assert call_kwargs["timeout"] == 3600
        assert call_kwargs["gpu"] == 1
        assert call_kwargs["seed"] == 123
        assert call_kwargs["no_cache"] is True
        assert call_kwargs["name"] == "MyExperiment"

    @patch("reprochecker.cli.db")
    @patch("reprochecker.pipeline.run_check")
    def test_check_failure_exits_1(self, mock_run: MagicMock, mock_cli_db: MagicMock) -> None:
        """run_check 抛异常时应 exit(1) 并更新状态为 failed"""
        mock_run.side_effect = RuntimeError("clone failed")
        mock_cli_db.create_check.return_value = 1
        result = runner.invoke(app, ["check", "https://github.com/user/repo"])

        assert result.exit_code == 1
        assert "失败" in result.output or "failed" in result.output.lower()
        mock_cli_db.update_check.assert_called_once_with(
            1,
            run_status="failed",
            notes="clone failed",
        )


# ── 2. repro list ─────────────────────────────────────────────────────────────


class TestListCommand:
    """repro list 命令测试"""

    def test_help(self) -> None:
        result = runner.invoke(app, ["list", "--help"])
        assert result.exit_code == 0
        assert "列出检验记录" in result.output or "status" in result.output.lower()

    def test_list_shows_records(self, mock_db: MagicMock) -> None:
        """有记录时应渲染表格"""
        mock_db.list_checks.return_value = [_sample_record(1), _sample_record(2)]
        with _patch_db(mock_db):
            result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        mock_db.list_checks.assert_called_once()

    def test_list_empty(self, mock_db: MagicMock) -> None:
        """无记录时应显示提示"""
        mock_db.list_checks.return_value = []
        with _patch_db(mock_db):
            result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "暂无" in result.output

    def test_list_with_filters(self, mock_db: MagicMock) -> None:
        """传入筛选参数应转发到 db.list_checks"""
        mock_db.list_checks.return_value = [_sample_record(1)]
        with _patch_db(mock_db):
            result = runner.invoke(
                app,
                [
                    "list",
                    "--status",
                    "success",
                    "--repo",
                    "user",
                    "--grade",
                    "A",
                    "--sort",
                    "overall_score",
                    "--limit",
                    "5",
                ],
            )

        assert result.exit_code == 0
        mock_db.list_checks.assert_called_once_with(
            status="success",
            repo="user",
            grade="A",
            sort="overall_score",
            limit=5,
        )


# ── 3. repro show ─────────────────────────────────────────────────────────────


class TestShowCommand:
    """repro show 命令测试"""

    def test_help(self) -> None:
        result = runner.invoke(app, ["show", "--help"])
        assert result.exit_code == 0
        assert "查看检验详情" in result.output

    def test_show_existing_record(self, mock_db: MagicMock) -> None:
        """存在的 ID 应显示详情"""
        record = _sample_record(42)
        mock_db.get_check.return_value = record
        mock_db.get_comparisons.return_value = _sample_comparisons()
        with _patch_db(mock_db):
            result = runner.invoke(app, ["show", "42"])

        assert result.exit_code == 0
        assert "42" in result.output
        mock_db.get_check.assert_called_once_with(42)

    def test_show_with_comparisons(self, mock_db: MagicMock) -> None:
        """有指标对比数据时应渲染对比表格"""
        mock_db.get_check.return_value = _sample_record(1)
        mock_db.get_comparisons.return_value = _sample_comparisons()
        with _patch_db(mock_db):
            result = runner.invoke(app, ["show", "1"])

        assert result.exit_code == 0
        assert "accuracy" in result.output or "指标" in result.output

    def test_show_nonexistent_id(self, mock_db: MagicMock) -> None:
        """不存在的 ID 应 exit(1) 并提示"""
        mock_db.get_check.return_value = None
        with _patch_db(mock_db):
            result = runner.invoke(app, ["show", "999"])

        assert result.exit_code == 1
        assert "不存在" in result.output

    def test_show_missing_argument(self) -> None:
        """缺少 ID 参数应报错"""
        result = runner.invoke(app, ["show"])
        assert result.exit_code != 0


# ── 4. repro report ───────────────────────────────────────────────────────────


class TestReportCommand:
    """repro report 命令测试"""

    def test_help(self) -> None:
        result = runner.invoke(app, ["report", "--help"])
        assert result.exit_code == 0
        assert "生成/导出报告" in result.output or "format" in result.output.lower()

    @patch("reprochecker.cli.db")
    @patch("reprochecker.report.generator.generate_report")
    def test_report_success(self, mock_gen: MagicMock, mock_cli_db: MagicMock) -> None:
        """正常生成报告"""
        mock_gen.return_value = Path("/tmp/check_1.html")
        mock_cli_db.get_check.return_value = _sample_record(1)
        result = runner.invoke(app, ["report", "1"])

        assert result.exit_code == 0, result.output
        assert "已保存" in result.output
        mock_gen.assert_called_once_with(1, format="html", output_dir=None)

    @patch("reprochecker.cli.db")
    @patch("reprochecker.report.generator.generate_report")
    def test_report_json_format(self, mock_gen: MagicMock, mock_cli_db: MagicMock) -> None:
        """指定 --format json"""
        mock_gen.return_value = Path("/tmp/check_1.json")
        mock_cli_db.get_check.return_value = _sample_record(1)
        result = runner.invoke(app, ["report", "1", "--format", "json"])

        assert result.exit_code == 0, result.output
        mock_gen.assert_called_once_with(1, format="json", output_dir=None)

    @patch("reprochecker.cli.db")
    @patch("reprochecker.report.generator.generate_report")
    def test_report_with_output_dir(self, mock_gen: MagicMock, mock_cli_db: MagicMock) -> None:
        """指定 --output 输出目录"""
        out = Path("/tmp/reports")
        mock_gen.return_value = out / "check_1.html"
        mock_cli_db.get_check.return_value = _sample_record(1)
        result = runner.invoke(app, ["report", "1", "-o", str(out)])

        assert result.exit_code == 0, result.output
        mock_gen.assert_called_once_with(1, format="html", output_dir=out)

    def test_report_nonexistent_id(self, mock_db: MagicMock) -> None:
        """不存在的 ID 应 exit(1)"""
        mock_db.get_check.return_value = None
        with _patch_db(mock_db):
            result = runner.invoke(app, ["report", "999"])

        assert result.exit_code == 1
        assert "不存在" in result.output

    def test_report_missing_argument(self) -> None:
        """缺少 ID 参数应报错"""
        result = runner.invoke(app, ["report"])
        assert result.exit_code != 0


# ── 5. repro compare ──────────────────────────────────────────────────────────


class TestCompareCommand:
    """repro compare 命令测试"""

    def test_help(self) -> None:
        result = runner.invoke(app, ["compare", "--help"])
        assert result.exit_code == 0
        assert "对比两次检验结果" in result.output

    def test_compare_two_records(self, mock_db: MagicMock) -> None:
        """对比两条记录应输出概要"""
        r1 = _sample_record(1, repo_name="repo-a", overall_score=80.0, grade="B")
        r2 = _sample_record(2, repo_name="repo-b", overall_score=90.0, grade="A")
        mock_db.get_check.side_effect = lambda cid: r1 if cid == 1 else r2 if cid == 2 else None
        mock_db.get_comparisons.return_value = []
        with _patch_db(mock_db):
            result = runner.invoke(app, ["compare", "1", "2"])

        assert result.exit_code == 0
        assert "1" in result.output and "2" in result.output

    def test_compare_with_metric_changes(self, mock_db: MagicMock) -> None:
        """有指标数据时应显示变化表"""
        r1 = _sample_record(1)
        r2 = _sample_record(2)
        mock_db.get_check.side_effect = lambda cid: r1 if cid == 1 else r2
        c1 = [{"metric_name": "accuracy", "actual_value": 90.0}]
        c2 = [{"metric_name": "accuracy", "actual_value": 93.5}]
        mock_db.get_comparisons.side_effect = lambda cid: c1 if cid == 1 else c2
        with _patch_db(mock_db):
            result = runner.invoke(app, ["compare", "1", "2"])

        assert result.exit_code == 0
        assert "accuracy" in result.output

    def test_compare_first_id_missing(self, mock_db: MagicMock) -> None:
        """第一个 ID 不存在应 exit(1)"""
        mock_db.get_check.return_value = None
        with _patch_db(mock_db):
            result = runner.invoke(app, ["compare", "1", "2"])

        assert result.exit_code == 1
        assert "不存在" in result.output

    def test_compare_second_id_missing(self, mock_db: MagicMock) -> None:
        """第二个 ID 不存在应 exit(1)"""

        def _get(cid: int):
            return _sample_record(cid) if cid == 1 else None

        mock_db.get_check.side_effect = _get
        with _patch_db(mock_db):
            result = runner.invoke(app, ["compare", "1", "2"])

        assert result.exit_code == 1
        assert "不存在" in result.output

    def test_compare_missing_arguments(self) -> None:
        """缺少参数应报错"""
        result = runner.invoke(app, ["compare"])
        assert result.exit_code != 0

    def test_compare_only_one_argument(self) -> None:
        """只传一个 ID 应报错"""
        result = runner.invoke(app, ["compare", "1"])
        assert result.exit_code != 0


# ── 6. repro stats ────────────────────────────────────────────────────────────


class TestStatsCommand:
    """repro stats 命令测试"""

    def test_help(self) -> None:
        result = runner.invoke(app, ["stats", "--help"])
        assert result.exit_code == 0
        assert "统计概览" in result.output

    def test_stats_display(self, mock_db: MagicMock) -> None:
        """正常统计应输出统计信息"""
        mock_db.get_stats.return_value = _sample_stats()
        with _patch_db(mock_db):
            result = runner.invoke(app, ["stats"])

        assert result.exit_code == 0
        assert "总检验次数" in result.output
        assert "5" in result.output

    def test_stats_empty_db(self, mock_db: MagicMock) -> None:
        """空数据库也应正常输出"""
        mock_db.get_stats.return_value = {
            "total": 0,
            "success": 0,
            "success_rate": 0,
            "grades": {},
            "avg_score": 0,
            "avg_duration_sec": 0,
            "top_repos": [],
        }
        with _patch_db(mock_db):
            result = runner.invoke(app, ["stats"])

        assert result.exit_code == 0
        assert "0" in result.output

    def test_stats_shows_top_repos(self, mock_db: MagicMock) -> None:
        """应显示最常检验的仓库"""
        mock_db.get_stats.return_value = _sample_stats()
        with _patch_db(mock_db):
            result = runner.invoke(app, ["stats"])

        assert result.exit_code == 0
        assert "user/repo" in result.output


# ── 7. repro delete ───────────────────────────────────────────────────────────


class TestDeleteCommand:
    """repro delete 命令测试"""

    def test_help(self) -> None:
        result = runner.invoke(app, ["delete", "--help"])
        assert result.exit_code == 0
        assert "删除检验记录" in result.output

    def test_delete_with_force(self, mock_db: MagicMock) -> None:
        """--force 跳过确认应直接删除"""
        mock_db.get_check.return_value = _sample_record(1)
        with _patch_db(mock_db):
            result = runner.invoke(app, ["delete", "1", "--force"])

        assert result.exit_code == 0
        assert "已删除" in result.output
        mock_db.delete_check.assert_called_once_with(1)

    def test_delete_with_short_force_flag(self, mock_db: MagicMock) -> None:
        """-f 短选项同样生效"""
        mock_db.get_check.return_value = _sample_record(1)
        with _patch_db(mock_db):
            result = runner.invoke(app, ["delete", "1", "-f"])

        assert result.exit_code == 0
        mock_db.delete_check.assert_called_once_with(1)

    def test_delete_confirm_yes(self, mock_db: MagicMock) -> None:
        """确认提示输入 y 应执行删除"""
        mock_db.get_check.return_value = _sample_record(1)
        with _patch_db(mock_db):
            result = runner.invoke(app, ["delete", "1"], input="y\n")

        assert result.exit_code == 0
        mock_db.delete_check.assert_called_once_with(1)

    def test_delete_confirm_no(self, mock_db: MagicMock) -> None:
        """确认提示输入 n 应中止"""
        mock_db.get_check.return_value = _sample_record(1)
        with _patch_db(mock_db):
            result = runner.invoke(app, ["delete", "1"], input="n\n")

        # typer.confirm 输入 n 时抛 Abort
        assert result.exit_code != 0
        mock_db.delete_check.assert_not_called()

    def test_delete_nonexistent_id(self, mock_db: MagicMock) -> None:
        """不存在的 ID 应 exit(1)"""
        mock_db.get_check.return_value = None
        with _patch_db(mock_db):
            result = runner.invoke(app, ["delete", "999", "--force"])

        assert result.exit_code == 1
        assert "不存在" in result.output
        mock_db.delete_check.assert_not_called()

    def test_delete_missing_argument(self) -> None:
        """缺少 ID 参数应报错"""
        result = runner.invoke(app, ["delete"])
        assert result.exit_code != 0


# ── 8. 版本与全局回调 ─────────────────────────────────────────────────────────


class TestGlobalCallbacks:
    """全局选项与回调测试"""

    def test_version_flag(self) -> None:
        """--version 应输出版本号"""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_version_short_flag(self) -> None:
        """-v 短选项应输出版本号"""
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert "ReproChecker" in result.output

    def test_help_no_args(self) -> None:
        """无参数时应显示帮助或错误提示"""
        result = runner.invoke(app, [])
        # Typer 返回 0 或 2 取决于版本
        assert result.exit_code in (0, 2)
        assert "Usage" in result.output or "repro" in result.output


# ── 9. repro cache 子命令 ────────────────────────────────────────────────────


@pytest.fixture
def fake_cache(tmp_path: Path) -> Path:
    """创建模拟的缓存目录结构。"""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()

    for repo_dir in ("user__repo-a", "org__repo-b"):
        repo_path = cache_dir / repo_dir
        repo_path.mkdir()
        (repo_path / "README.md").write_text("# test", encoding="utf-8")
        (repo_path / "data.bin").write_bytes(b"\x00" * 1024)

    return cache_dir


class TestCacheSubcommandRegistration:
    """缓存子命令注册测试"""

    def test_cache_group_exists(self) -> None:
        """cache 子命令组应已注册。"""
        result = runner.invoke(app, ["cache", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "clear" in result.output

    def test_cache_list_help(self) -> None:
        """cache list 应有帮助文本。"""
        result = runner.invoke(app, ["cache", "list", "--help"])
        assert result.exit_code == 0
        assert "缓存" in result.output or "仓库" in result.output

    def test_cache_clear_help(self) -> None:
        """cache clear 应有帮助文本。"""
        result = runner.invoke(app, ["cache", "clear", "--help"])
        assert result.exit_code == 0
        assert "缓存" in result.output


class TestCacheList:
    """repro cache list 命令测试"""

    def test_list_shows_cached_repos(self, fake_cache: Path) -> None:
        """应列出所有缓存仓库及其大小信息。"""
        mock_repos = [
            {
                "name": "user/repo-a",
                "path": str(fake_cache / "user__repo-a"),
                "commit_hash": "abc123def456789",
            },
            {
                "name": "org/repo-b",
                "path": str(fake_cache / "org__repo-b"),
                "commit_hash": "987654fed321cba",
            },
        ]

        with patch("reprochecker.repo.cloner.list_cached_repos", return_value=mock_repos):
            result = runner.invoke(app, ["cache", "list"])

        assert result.exit_code == 0
        assert "user/repo-a" in result.output
        assert "org/repo-b" in result.output
        assert "abc123def456" in result.output
        assert "KB" in result.output or "B" in result.output
        assert "共 2 个缓存仓库" in result.output

    def test_list_empty_cache(self) -> None:
        """无缓存时应显示提示信息。"""
        with patch("reprochecker.repo.cloner.list_cached_repos", return_value=[]):
            result = runner.invoke(app, ["cache", "list"])

        assert result.exit_code == 0
        assert "暂无缓存仓库" in result.output

    def test_list_includes_total_size(self, fake_cache: Path) -> None:
        """应显示总大小。"""
        mock_repos = [
            {
                "name": "user/repo-a",
                "path": str(fake_cache / "user__repo-a"),
                "commit_hash": "abc123",
            },
        ]

        with patch("reprochecker.repo.cloner.list_cached_repos", return_value=mock_repos):
            result = runner.invoke(app, ["cache", "list"])

        assert result.exit_code == 0
        assert "总大小" in result.output


class TestCacheClear:
    """repro cache clear 命令测试"""

    def test_clear_all_with_force(self, tmp_path: Path) -> None:
        """--force 应跳过确认直接清除全部缓存。"""
        mock_repos = [{"name": "a/b", "path": str(tmp_path / "a__b")}]
        with (
            patch("reprochecker.repo.cloner.list_cached_repos", return_value=mock_repos),
            patch("reprochecker.repo.cloner.clear_cache", return_value=1) as mock_clear,
        ):
            result = runner.invoke(app, ["cache", "clear", "--force"])

        assert result.exit_code == 0, result.output
        assert "已清除 1 个缓存仓库" in result.output
        mock_clear.assert_called_once()

    def test_clear_all_empty_cache(self) -> None:
        """无缓存时执行清除应提示并退出。"""
        with patch("reprochecker.repo.cloner.list_cached_repos", return_value=[]):
            result = runner.invoke(app, ["cache", "clear"])

        assert result.exit_code == 0
        assert "暂无缓存仓库" in result.output

    def test_clear_specific_repo_with_force(self, tmp_path: Path) -> None:
        """--force 应跳过确认直接清除指定仓库。"""
        # 创建模拟的缓存目录结构: tmp_path/.reprochecker/cache/user__repo/
        cache_base = tmp_path / ".reprochecker" / "cache" / "user__repo"
        cache_base.mkdir(parents=True)
        (cache_base / "README.md").write_text("# test", encoding="utf-8")

        with (
            patch("reprochecker.repo.cloner.clear_cache", return_value=1) as mock_clear,
            patch("reprochecker.cli.Path.home", return_value=tmp_path),
        ):
            result = runner.invoke(
                app,
                ["cache", "clear", "user/repo", "--force"],
            )

        assert result.exit_code == 0, result.output
        assert "已清除仓库 'user/repo' 的缓存" in result.output
        mock_clear.assert_called_once_with("user/repo")

    def test_clear_nonexistent_repo(self) -> None:
        """清除不存在的仓库缓存应报错退出。"""
        result = runner.invoke(app, ["cache", "clear", "nobody/nope", "--force"])
        assert result.exit_code == 1
        assert "未找到仓库" in result.output

    def test_clear_all_confirm_declined(self) -> None:
        """用户拒绝确认时应中止操作。"""
        with patch("reprochecker.repo.cloner.list_cached_repos", return_value=[{"name": "a/b"}]):
            result = runner.invoke(app, ["cache", "clear"], input="n\n")

        assert result.exit_code != 0  # typer.Abort
