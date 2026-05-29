"""批量检验命令测试"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml
from typer.testing import CliRunner

from reprochecker.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _mock_config() -> MagicMock:
    """自动 mock load_config，防止 main() 回调因配置文件问题失败。"""
    with patch("reprochecker.cli.load_config", return_value={}) as m:
        yield m


def _sample_record(check_id: int = 1) -> dict[str, Any]:
    return {
        "id": check_id,
        "repo_url": "https://github.com/user/repo",
        "repo_name": "user/repo",
        "commit_hash": "abc123",
        "framework": "pytorch",
        "run_status": "success",
        "overall_score": 85.0,
        "grade": "B",
        "metric_score": 90.0,
        "env_score": 80.0,
        "code_score": 75.0,
        "created_at": "2026-05-28 10:00:00",
    }


# ── batch 命令 ────────────────────────────────────────────────────────────────


class TestBatchCommand:
    """repro batch 命令测试"""

    def test_help(self) -> None:
        """batch --help 应显示用法说明"""
        result = runner.invoke(app, ["batch", "--help"])
        assert result.exit_code == 0
        assert "批量" in result.output

    @patch("reprochecker.cli.db")
    @patch("reprochecker.pipeline.run_check")
    def test_batch_yaml(self, mock_run: MagicMock, mock_cli_db: MagicMock, tmp_path: Path) -> None:
        """应正确解析 YAML 配置并执行检验"""
        mock_cli_db.create_check.return_value = 1
        mock_cli_db.get_check.return_value = _sample_record(1)
        mock_run.return_value = None

        config = {
            "repos": [
                {"url": "https://github.com/user/repo1"},
                {"url": "https://github.com/user/repo2"},
            ]
        }
        config_file = tmp_path / "batch.yaml"
        config_file.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")

        result = runner.invoke(app, ["batch", str(config_file)])

        assert result.exit_code == 0, result.output
        assert mock_run.call_count == 2
        assert "汇总" in result.output

    @patch("reprochecker.cli.db")
    @patch("reprochecker.pipeline.run_check")
    def test_batch_json(self, mock_run: MagicMock, mock_cli_db: MagicMock, tmp_path: Path) -> None:
        """应正确解析 JSON 配置"""
        mock_cli_db.create_check.return_value = 1
        mock_cli_db.get_check.return_value = _sample_record(1)
        mock_run.return_value = None

        config = {"repos": [{"url": "https://github.com/user/repo1"}]}
        config_file = tmp_path / "batch.json"
        config_file.write_text(json.dumps(config), encoding="utf-8")

        result = runner.invoke(app, ["batch", str(config_file)])

        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()

    @patch("reprochecker.cli.db")
    @patch("reprochecker.pipeline.run_check")
    def test_batch_with_options(
        self, mock_run: MagicMock, mock_cli_db: MagicMock, tmp_path: Path
    ) -> None:
        """应正确传递 cmd/pdf 等选项"""
        mock_cli_db.create_check.return_value = 1
        mock_cli_db.get_check.return_value = _sample_record(1)
        mock_run.return_value = None

        config = {
            "repos": [
                {
                    "url": "https://github.com/user/repo1",
                    "pdf": "/tmp/paper.pdf",
                    "cmd": "python run.py",
                },
            ]
        }
        config_file = tmp_path / "batch.yaml"
        config_file.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")

        result = runner.invoke(app, ["batch", str(config_file), "--env", "conda", "--seed", "123"])

        assert result.exit_code == 0, result.output
        call_kwargs = mock_run.call_args.kwargs
        assert call_kwargs["env"] == "conda"
        assert call_kwargs["seed"] == 123
        assert call_kwargs["cmd"] == "python run.py"
        assert call_kwargs["pdf_path"] == Path("/tmp/paper.pdf")

    def test_batch_missing_file(self) -> None:
        """配置文件不存在应 exit(1)"""
        result = runner.invoke(app, ["batch", "/nonexistent/batch.yaml"])
        assert result.exit_code == 1
        assert "不存在" in result.output

    def test_batch_invalid_format(self, tmp_path: Path) -> None:
        """配置文件缺少 repos 字段应 exit(1)"""
        config_file = tmp_path / "bad.yaml"
        config_file.write_text(yaml.dump({"wrong_key": []}), encoding="utf-8")

        result = runner.invoke(app, ["batch", str(config_file)])
        assert result.exit_code == 1
        assert "格式错误" in result.output

    def test_batch_empty_repos(self, tmp_path: Path) -> None:
        """repos 列表为空应 exit(1)"""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text(yaml.dump({"repos": []}), encoding="utf-8")

        result = runner.invoke(app, ["batch", str(config_file)])
        assert result.exit_code == 1
        assert "为空" in result.output

    @patch("reprochecker.cli.db")
    @patch("reprochecker.pipeline.run_check")
    def test_batch_partial_failure(
        self, mock_run: MagicMock, mock_cli_db: MagicMock, tmp_path: Path
    ) -> None:
        """部分检验失败时应继续执行并在汇总中显示"""
        call_count = 0

        def side_effect(**kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("clone failed")

        mock_run.side_effect = side_effect
        mock_cli_db.create_check.return_value = 1

        def get_check(cid: int) -> dict[str, Any]:
            return _sample_record(cid)

        mock_cli_db.get_check.side_effect = get_check

        config = {
            "repos": [
                {"url": "https://github.com/user/repo1"},
                {"url": "https://github.com/user/repo2"},
            ]
        }
        config_file = tmp_path / "batch.yaml"
        config_file.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")

        result = runner.invoke(app, ["batch", str(config_file)])

        assert result.exit_code == 0, result.output
        assert mock_run.call_count == 2
        assert "failed" in result.output or "失败" in result.output

    @patch("reprochecker.cli.db")
    @patch("reprochecker.pipeline.run_check")
    def test_batch_skip_missing_url(
        self, mock_run: MagicMock, mock_cli_db: MagicMock, tmp_path: Path
    ) -> None:
        """缺少 url 字段的条目应跳过"""
        mock_cli_db.create_check.return_value = 1
        mock_cli_db.get_check.return_value = _sample_record(1)
        mock_run.return_value = None

        config = {
            "repos": [
                {"url": "https://github.com/user/repo1"},
                {"pdf": "/tmp/no-url.pdf"},  # 缺少 url
            ]
        }
        config_file = tmp_path / "batch.yaml"
        config_file.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")

        result = runner.invoke(app, ["batch", str(config_file)])

        assert result.exit_code == 0, result.output
        mock_run.assert_called_once()  # 只执行一次
        assert "缺少" in result.output or "skipped" in result.output

    @patch("reprochecker.cli.db")
    @patch("reprochecker.pipeline.run_check")
    def test_batch_shows_progress(
        self, mock_run: MagicMock, mock_cli_db: MagicMock, tmp_path: Path
    ) -> None:
        """应显示进度信息"""
        mock_cli_db.create_check.return_value = 1
        mock_cli_db.get_check.return_value = _sample_record(1)
        mock_run.return_value = None

        config = {
            "repos": [
                {"url": "https://github.com/user/repo1"},
                {"url": "https://github.com/user/repo2"},
                {"url": "https://github.com/user/repo3"},
            ]
        }
        config_file = tmp_path / "batch.yaml"
        config_file.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")

        result = runner.invoke(app, ["batch", str(config_file)])

        assert result.exit_code == 0, result.output
        # Rich 进度条显示 (3/3) 格式
        assert "(3/3)" in result.output or "100%" in result.output

    def test_batch_malformed_yaml(self, tmp_path: Path) -> None:
        """格式错误的 YAML 文件应报错"""
        config_file = tmp_path / "bad.yaml"
        config_file.write_text("repos: [unclosed_bracket", encoding="utf-8")

        result = runner.invoke(app, ["batch", str(config_file)])
        assert result.exit_code != 0

    def test_batch_malformed_json(self, tmp_path: Path) -> None:
        """格式错误的 JSON 文件应报错"""
        config_file = tmp_path / "bad.json"
        config_file.write_text('{"repos": [unclosed', encoding="utf-8")

        result = runner.invoke(app, ["batch", str(config_file)])
        assert result.exit_code != 0
