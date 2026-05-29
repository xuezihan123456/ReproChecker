"""dry-run 模式测试"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestDryRun:
    """dry-run 模式测试"""

    @patch("reprochecker.pipeline.db")
    def test_dry_run_skips_db_status_update(self, mock_db: MagicMock) -> None:
        """dry_run=True 时不应设置 run_status='running'"""
        from reprochecker.pipeline import run_check

        progress_calls: list[tuple[int, str, str]] = []

        def capture_progress(step: int, name: str, msg: str) -> None:
            progress_calls.append((step, name, msg))

        run_check(
            check_id=1,
            url="https://github.com/example/test-repo",
            dry_run=True,
            on_progress=capture_progress,
        )

        # 不应调用 run_status="running" 或 run_status="success"
        for call in mock_db.update_check.call_args_list:
            args, kwargs = call
            assert kwargs.get("run_status") not in ("running", "success"), (
                f"dry_run 模式不应更新 DB 状态为 running/success，但调用了: {call}"
            )

    @patch("reprochecker.pipeline.db")
    def test_dry_run_calls_all_6_steps(self, mock_db: MagicMock) -> None:
        """dry_run 应经过全部 6 个阶段"""
        from reprochecker.pipeline import run_check

        progress_calls: list[tuple[int, str, str]] = []

        def capture_progress(step: int, name: str, msg: str) -> None:
            progress_calls.append((step, name, msg))

        run_check(
            check_id=1,
            url="https://github.com/example/test-repo",
            dry_run=True,
            on_progress=capture_progress,
        )

        steps_seen = {call[0] for call in progress_calls}
        assert steps_seen == {1, 2, 3, 4, 5, 6}, f"缺少步骤: {set(range(1, 7)) - steps_seen}"

    @patch("reprochecker.pipeline.db")
    def test_dry_run_prints_clone_info(self, mock_db: MagicMock) -> None:
        """dry_run 应打印克隆目标信息"""
        from reprochecker.pipeline import run_check

        progress_calls: list[tuple[int, str, str]] = []

        def capture_progress(step: int, name: str, msg: str) -> None:
            progress_calls.append((step, name, msg))

        run_check(
            check_id=1,
            url="https://github.com/example/my-project.git",
            dry_run=True,
            on_progress=capture_progress,
        )

        # 检查步骤 1 的消息包含仓库名
        step1_msgs = [msg for step, _, msg in progress_calls if step == 1]
        assert any("my-project" in msg for msg in step1_msgs), (
            f"步骤 1 应包含仓库名 'my-project'，实际: {step1_msgs}"
        )

    @patch("reprochecker.pipeline.db")
    def test_dry_run_uses_custom_name(self, mock_db: MagicMock) -> None:
        """dry_run 使用 --name 参数"""
        from reprochecker.pipeline import run_check

        progress_calls: list[tuple[int, str, str]] = []

        def capture_progress(step: int, name: str, msg: str) -> None:
            progress_calls.append((step, name, msg))

        run_check(
            check_id=1,
            url="https://github.com/example/test-repo",
            name="custom-name",
            dry_run=True,
            on_progress=capture_progress,
        )

        step1_msgs = [msg for step, _, msg in progress_calls if step == 1]
        assert any("custom-name" in msg for msg in step1_msgs), (
            f"步骤 1 应使用自定义名称 'custom-name'，实际: {step1_msgs}"
        )

    @patch("reprochecker.pipeline.db")
    def test_dry_run_prints_command(self, mock_db: MagicMock) -> None:
        """dry_run 应打印将执行的命令"""
        from reprochecker.pipeline import run_check

        progress_calls: list[tuple[int, str, str]] = []

        def capture_progress(step: int, name: str, msg: str) -> None:
            progress_calls.append((step, name, msg))

        run_check(
            check_id=1,
            url="https://github.com/example/test-repo",
            cmd="python custom_train.py --epochs 10",
            dry_run=True,
            on_progress=capture_progress,
        )

        step4_msgs = [msg for step, _, msg in progress_calls if step == 4]
        assert any("custom_train.py" in msg for msg in step4_msgs), (
            f"步骤 4 应包含自定义命令，实际: {step4_msgs}"
        )

    @patch("reprochecker.pipeline.db")
    def test_dry_run_prints_env_method(self, mock_db: MagicMock) -> None:
        """dry_run 应打印环境方式"""
        from reprochecker.pipeline import run_check

        progress_calls: list[tuple[int, str, str]] = []

        def capture_progress(step: int, name: str, msg: str) -> None:
            progress_calls.append((step, name, msg))

        run_check(
            check_id=1,
            url="https://github.com/example/test-repo",
            env="docker",
            dry_run=True,
            on_progress=capture_progress,
        )

        step3_msgs = [msg for step, _, msg in progress_calls if step == 3]
        assert any("docker" in msg for msg in step3_msgs), (
            f"步骤 3 应包含环境方式 'docker'，实际: {step3_msgs}"
        )

    @patch("reprochecker.pipeline.db")
    def test_dry_run_returns_placeholder_score(self, mock_db: MagicMock) -> None:
        """dry_run 返回占位评分（不保存到 DB）"""
        from reprochecker.pipeline import run_check

        progress_calls: list[tuple[int, str, str]] = []

        def capture_progress(step: int, name: str, msg: str) -> None:
            progress_calls.append((step, name, msg))

        run_check(
            check_id=1,
            url="https://github.com/example/test-repo",
            dry_run=True,
            on_progress=capture_progress,
        )

        # 检查步骤 6 包含占位评分
        step6_msgs = [msg for step, _, msg in progress_calls if step == 6]
        assert any("0/100" in msg or "0" in msg for msg in step6_msgs), (
            f"步骤 6 应包含占位评分，实际: {step6_msgs}"
        )

    @patch("reprochecker.pipeline.db")
    def test_dry_run_does_not_clone(self, mock_db: MagicMock) -> None:
        """dry_run 不应调用 clone_repo"""
        from reprochecker.pipeline import run_check

        with patch("reprochecker.repo.cloner.clone_repo") as mock_clone:
            run_check(
                check_id=1,
                url="https://github.com/example/test-repo",
                dry_run=True,
            )
            mock_clone.assert_not_called()


class TestDryRunCli:
    """CLI --dry-run 参数测试"""

    def test_cli_check_has_dry_run_option(self) -> None:
        """check 命令应有 --dry-run 选项"""
        from typer.testing import CliRunner

        from reprochecker.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["check", "--help"])
        assert result.exit_code == 0
        assert "--dry-run" in result.output
