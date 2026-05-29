"""输出流指标捕获 — 从 stdout/stderr 中正则提取训练指标"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# 正则模式集合
# ---------------------------------------------------------------------------
# 每个模式必须包含命名组:
#   name  — 指标名称
#   value — 数值
# 可选组: step, epoch

_METRIC_PATTERNS: list[re.Pattern[str]] = [
    # ---- 带 epoch / step 上下文的复合行 ----
    # "Epoch 3/100 ... loss: 0.5 acc: 0.8"
    re.compile(
        r"Epoch\s+(?P<epoch>\d+)\s*/\s*\d+"
        r".*?"
        r"(?P<name>loss|acc(?:uracy)?|val_loss|val_acc(?:uracy)?)\s*[:=]\s*(?P<value>[\d.]+)",
        re.IGNORECASE,
    ),
    # "Step 1000: loss=0.03"
    re.compile(
        r"Step\s+(?P<step>\d+)[:\s]+"
        r"(?P<name>loss|acc(?:uracy)?|val_loss|val_acc(?:uracy)?)\s*[:=]\s*(?P<value>[\d.]+)",
        re.IGNORECASE,
    ),
    # "[Epoch 5][Step 200] train/loss = 0.123"
    re.compile(
        r"\[?\s*Epoch\s+(?P<epoch>\d+)\s*\]?"
        r".*?"
        r"\[?\s*Step\s+(?P<step>\d+)\s*\]?"
        r".*?"
        r"(?P<name>[\w./]+)\s*[:=]\s*(?P<value>[\d.]+)",
        re.IGNORECASE,
    ),
    # ---- 百分比格式 ----
    # "Accuracy: 92.1%"
    re.compile(
        r"(?P<name>accuracy|acc|precision|recall|f1(?:[_\-]?score)?|top[_\-]?[15]|mAP|IoU|AUC|ROC)"
        r"\s*[:=]\s*(?P<value>\d+\.?\d*)\s*%",
        re.IGNORECASE,
    ),
    # ---- 标准 key: value / key = value ----
    # "accuracy: 0.921" / "accuracy = 0.921"
    re.compile(
        r"(?P<name>accuracy|acc|f1(?:[_\-]?score)?|precision|recall|auc|roc[_\-]?auc|mAP|IoU|top[_\-]?[15])"
        r"\s*[:=]\s*(?P<value>\d*\.?\d+(?:[eE][+-]?\d+)?)",
        re.IGNORECASE,
    ),
    # "loss: 0.0345" / "val_loss = 0.02"
    re.compile(
        r"(?P<name>(?:val[_\-])?loss(?:[_\-]?\w*)?|cross[_\-]?entropy|bce|mse|mae|rmse)"
        r"\s*[:=]\s*(?P<value>\d*\.?\d+(?:[eE][+-]?\d+)?)",
        re.IGNORECASE,
    ),
    # "F1: 0.903" / "f1_score: 0.903"
    re.compile(
        r"(?P<name>f1(?:[_\-]?score)?|F1)"
        r"\s*[:=]\s*(?P<value>\d*\.?\d+(?:[eE][+-]?\d+)?)",
        re.IGNORECASE,
    ),
    # "BLEU: 32.5" / "bleu_score = 31.2"
    re.compile(
        r"(?P<name>bleu(?:[_\-]?score)?|rouge[_\-]?[12L]|WER|CER|PSNR|SSIM|FID|IS)"
        r"\s*[:=]\s*(?P<value>\d*\.?\d+(?:[eE][+-]?\d+)?)",
        re.IGNORECASE,
    ),
    # ---- 训练进度行 (epoch/step 信息) ----
    # "train_loss: 0.123 (epoch 5, step 1000)"
    re.compile(
        r"(?P<name>[\w./]+)\s*[:=]\s*(?P<value>\d*\.?\d+(?:[eE][+-]?\d+)?)"
        r".*?(?:epoch|ep)\s*[:=]?\s*(?P<epoch>\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<name>[\w./]+)\s*[:=]\s*(?P<value>\d*\.?\d+(?:[eE][+-]?\d+)?)"
        r".*?(?:step|iter|iteration)\s*[:=]?\s*(?P<step>\d+)",
        re.IGNORECASE,
    ),
]

# 名称归一化映射
_NAME_ALIASES: dict[str, str] = {
    "acc": "accuracy",
    "acc.": "accuracy",
    "train_acc": "train_accuracy",
    "val_acc": "val_accuracy",
    "test_acc": "test_accuracy",
    "f1": "f1_score",
    "f1-score": "f1_score",
    "f1score": "f1_score",
    "top-1": "top_1_accuracy",
    "top1": "top_1_accuracy",
    "top-5": "top_5_accuracy",
    "top5": "top_5_accuracy",
    "cross_entropy": "cross_entropy_loss",
    "bce": "bce_loss",
    "mse": "mse_loss",
    "mae": "mae_loss",
    "rmse": "rmse_loss",
    "bleu": "bleu_score",
    "bleu-score": "bleu_score",
    "bleuscore": "bleu_score",
}

# 过滤掉的非指标行关键词（避免误匹配日志噪声）
_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:^|\s)(?:INFO|DEBUG|WARNING|ERROR|CRITICAL)\b", re.IGNORECASE),
    re.compile(r"(?:Traceback|File \")", re.IGNORECASE),
    re.compile(r"(?:\.py:\d+|http[s]?://)", re.IGNORECASE),
]


def _normalize_name(raw: str) -> str:
    """将原始指标名统一为小写下划线格式。"""
    cleaned = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return _NAME_ALIASES.get(cleaned, cleaned)


def _is_noise(line: str) -> bool:
    """判断一行是否为日志噪声。"""
    return any(p.search(line) for p in _NOISE_PATTERNS)


def _parse_float(raw: str) -> float | None:
    """安全解析浮点数。"""
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def capture_metrics(stdout: str, stderr: str) -> list[dict[str, Any]]:
    """从 stdout 和 stderr 中捕获所有可识别的指标。

    Parameters
    ----------
    stdout : str
        子进程标准输出。
    stderr : str
        子进程标准错误。

    Returns
    -------
    list[dict]
        每项包含 name, value, step (可选), epoch (可选)。
        同名同值的指标只保留最后一次出现（去重）。
    """
    combined = stdout + "\n" + stderr
    # 用于去重: (name, value) -> 最后一条记录的索引
    seen: dict[tuple[str, float], int] = {}
    results: list[dict[str, Any]] = []

    for line in combined.splitlines():
        stripped = line.strip()
        if not stripped or _is_noise(stripped):
            continue

        for pattern in _METRIC_PATTERNS:
            for match in pattern.finditer(stripped):
                groups = match.groupdict()
                raw_name = groups.get("name")
                raw_value = groups.get("value")
                if not raw_name or not raw_value:
                    continue

                value = _parse_float(raw_value)
                if value is None:
                    continue

                name = _normalize_name(raw_name)

                # 百分比自动转小数: 如果模式匹配了 "%" 后缀
                if "%" in stripped[match.start() : match.end() + 2]:
                    if value > 1.0:
                        value = round(value / 100.0, 6)

                # 提取 step / epoch
                step: int | None = None
                epoch: int | None = None
                if groups.get("step"):
                    step = _parse_int(groups["step"])
                if groups.get("epoch"):
                    epoch = _parse_int(groups["epoch"])

                entry: dict[str, Any] = {"name": name, "value": value}
                if step is not None:
                    entry["step"] = step
                if epoch is not None:
                    entry["epoch"] = epoch

                # 去重: 同名同值只保留最后一条
                dedup_key = (name, value)
                if dedup_key in seen:
                    idx = seen[dedup_key]
                    results[idx] = entry
                else:
                    seen[dedup_key] = len(results)
                    results.append(entry)

    return results


def _parse_int(raw: str) -> int | None:
    """安全解析整数。"""
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None
