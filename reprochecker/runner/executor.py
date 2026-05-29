"""子进程运行实验 — 启动训练/推理命令并捕获输出"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from reprochecker.logging import get_logger

logger = get_logger(__name__.replace("reprochecker.", ""))

# 危险 shell 模式 — 命令注入检测
_DANGEROUS_PATTERNS = re.compile(
    r"(?:"
    r"`[^`]+`"           # backtick subshell
    r"|\$\([^)]+\)"      # $(...) subshell
    r"|\|\s*(?:bash|sh|zsh|curl|wget|nc|ncat)\b"  # pipe to shell/network
    r"|;\s*(?:rm|mkfs|dd|chmod|chown)\b"  # chained destructive commands
    r"|>\s*/etc/"         # redirect to system files
    r")",
    re.IGNORECASE,
)


def _validate_command(command: str) -> None:
    """检查命令是否包含明显的注入模式，危险时抛出 ValueError"""
    if _DANGEROUS_PATTERNS.search(command):
        raise ValueError(
            f"命令包含潜在危险模式，请手动检查: {command[:100]}"
        )

# 输出截断参数
_HEAD_LINES = 200
_TAIL_LINES = 800


def _truncate_output(text: str, head: int = _HEAD_LINES, tail: int = _TAIL_LINES) -> str:
    """保留前 head 行 + 后 tail 行，中间用省略提示隔开。

    如果总行数不超过 head + tail，则原样返回。
    """
    lines = text.splitlines(keepends=True)
    total = len(lines)
    if total <= head + tail:
        return text

    head_part = lines[:head]
    tail_part = lines[-tail:]
    omitted = total - head - tail
    separator = f"\n... [{omitted} lines omitted] ...\n"
    return "".join(head_part) + separator + "".join(tail_part)


def _inject_seed(command: str, seed: int) -> str:
    """向命令中注入 --seed 参数。

    如果命令中已经包含 --seed / --random_seed / --seed= 等形式，则不重复注入。
    """
    if re.search(r"--(?:random_)?seed(?:=|\s)", command):
        return command
    return f"{command} --seed {seed}"


def run_experiment(
    repo_path: Path,
    command: str,
    timeout: int = 14400,
    gpu: int = 0,
    seed: int = 42,
    has_seed: bool = False,
) -> dict:
    """在 repo_path 下以子进程方式运行实验命令。

    Parameters
    ----------
    repo_path : Path
        仓库根目录，作为子进程的 cwd。
    command : str
        要执行的命令字符串（会被 shell 解析）。
    timeout : int
        超时秒数，默认 14400（4 小时）。
    gpu : int
        分配的 GPU 编号，映射到 CUDA_VISIBLE_DEVICES。
    seed : int
        随机种子，默认 42。
    has_seed : bool
        代码是否已经内置种子设置。如果为 False 且命令中无种子参数，则自动注入。

    Returns
    -------
    dict
        包含 command, status, exit_code, stdout, stderr,
        start_time, end_time, duration_sec。
    """
    # 安全校验
    _validate_command(command)

    # 如果代码未内置种子且命令中没有种子参数，则注入 --seed
    effective_command = command
    if not has_seed:
        effective_command = _inject_seed(command, seed)

    # 构建环境变量
    env_overrides: dict[str, str] = {
        "CUDA_VISIBLE_DEVICES": str(gpu),
    }

    # 使用固定种子的环境变量（供未接收 --seed 的框架使用）
    if not has_seed:
        env_overrides["PYTHONHASHSEED"] = str(seed)

    merged_env = {**os.environ, **env_overrides}

    logger.info(
        "Running experiment: %s (cwd=%s, gpu=%s, timeout=%ds)",
        effective_command, repo_path, gpu, timeout,
    )

    start_time = datetime.now(timezone.utc)
    status = "failed"
    exit_code: int | None = None
    stdout_text = ""
    stderr_text = ""

    try:
        proc = subprocess.run(
            effective_command,
            shell=True,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged_env,
            encoding="utf-8",
            errors="replace",
        )
        exit_code = proc.returncode
        stdout_text = proc.stdout or ""
        stderr_text = proc.stderr or ""
        status = "success" if exit_code == 0 else "failed"

    except subprocess.TimeoutExpired as exc:
        status = "timeout"
        exit_code = -1
        # TimeoutExpired 可能有部分输出
        stdout_text = (
            exc.stdout.decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        )
        stderr_text = (
            exc.stderr.decode("utf-8", errors="replace")
            if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        )
        logger.warning("Experiment timed out after %ds", timeout)

    except Exception as exc:
        status = "failed"
        exit_code = -1
        stderr_text = f"[executor error] {type(exc).__name__}: {exc}"
        logger.exception("Experiment failed with exception")

    end_time = datetime.now(timezone.utc)
    duration_sec = (end_time - start_time).total_seconds()

    # 截断输出
    stdout_truncated = _truncate_output(stdout_text)
    stderr_truncated = _truncate_output(stderr_text)

    result = {
        "command": effective_command,
        "status": status,
        "exit_code": exit_code,
        "stdout": stdout_truncated,
        "stderr": stderr_truncated,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_sec": round(duration_sec, 2),
    }

    logger.info(
        "Experiment finished: status=%s, exit_code=%s, duration=%.1fs",
        status,
        exit_code,
        duration_sec,
    )
    return result
