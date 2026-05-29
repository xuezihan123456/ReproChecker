"""全局配置管理"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ── 默认配置（嵌套结构，与 repro.yaml 格式一致） ──────────────────────
_DEFAULTS: dict[str, Any] = {
    "scoring": {
        "metric_weight": 0.50,
        "env_weight": 0.20,
        "code_weight": 0.30,
    },
    "tolerance": {
        "excellent": 0.01,   # <1% 完全复现
        "good": 0.05,        # 1-5% 基本复现
        "acceptable": 0.10,  # 5-10% 部分复现
        "poor": 0.20,        # 10-20% 难以复现
    },
    "defaults": {
        "env": "auto",
        "timeout": 14400,
        "gpu": 0,
        "seed": 42,
    },
    "report": {
        "format": "html",
        "output_dir": "./reports",
    },
}

# 允许的顶层 key 和子 key，用于校验未知字段
_KNOWN_KEYS: dict[str, set[str]] = {
    "scoring": {"metric_weight", "env_weight", "code_weight"},
    "tolerance": {"excellent", "good", "acceptable", "poor"},
    "defaults": {"env", "timeout", "gpu", "seed"},
    "report": {"format", "output_dir"},
}

# 配置文件搜索路径（按优先级从高到低）
_SEARCH_NAMES = ["repro.yaml", "repro.yml", "repro.json"]
_HOME_CONFIG = Path.home() / ".reprochecker" / "config.yaml"


class ConfigError(Exception):
    """配置校验错误"""


# ── 配置文件加载与合并 ────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并字典，override 中的值覆盖 base。

    返回新字典，不修改输入。
    """
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _validate_config(cfg: dict) -> None:
    """校验配置值的合法性。

    Raises:
        ConfigError: 当配置值不合法时。
    """
    # 检查未知的顶层 key
    unknown_top = set(cfg.keys()) - set(_KNOWN_KEYS.keys())
    if unknown_top:
        raise ConfigError(f"配置文件包含未知字段: {', '.join(sorted(unknown_top))}")

    # 检查各 section 内的未知 key
    for section, allowed in _KNOWN_KEYS.items():
        if section in cfg and isinstance(cfg[section], dict):
            unknown = set(cfg[section].keys()) - allowed
            if unknown:
                raise ConfigError(
                    f"[{section}] 包含未知字段: {', '.join(sorted(unknown))}"
                )

    # 评分权重必须和为 1.0
    if "scoring" in cfg:
        weights = cfg["scoring"]
        total = sum(
            weights.get(k, _DEFAULTS["scoring"][k])
            for k in ("metric_weight", "env_weight", "code_weight")
        )
        if abs(total - 1.0) > 1e-6:
            raise ConfigError(
                f"评分权重之和必须为 1.0，当前为 {total:.4f}"
            )

    # 容差阈值必须递增
    if "tolerance" in cfg:
        t = cfg["tolerance"]
        vals = [
            t.get("excellent", _DEFAULTS["tolerance"]["excellent"]),
            t.get("good", _DEFAULTS["tolerance"]["good"]),
            t.get("acceptable", _DEFAULTS["tolerance"]["acceptable"]),
            t.get("poor", _DEFAULTS["tolerance"]["poor"]),
        ]
        for i in range(len(vals) - 1):
            if vals[i] >= vals[i + 1]:
                raise ConfigError(
                    "容差阈值必须递增: excellent < good < acceptable < poor"
                )

    # timeout 必须为正整数
    if "defaults" in cfg and "timeout" in cfg["defaults"]:
        if cfg["defaults"]["timeout"] <= 0:
            raise ConfigError("timeout 必须为正整数")


def _find_config_file() -> Path | None:
    """按搜索顺序查找配置文件，返回第一个找到的路径。"""
    cwd = Path.cwd()
    for name in _SEARCH_NAMES:
        candidate = cwd / name
        if candidate.is_file():
            return candidate
    if _HOME_CONFIG.is_file():
        return _HOME_CONFIG
    return None


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """加载配置文件并与默认值合并。

    搜索顺序（第一个找到的生效）:
        1. 显式指定的 config_path
        2. ./repro.yaml / ./repro.yml / ./repro.json
        3. ~/.reprochecker/config.yaml

    Args:
        config_path: 显式指定的配置文件路径，为 None 则自动搜索。

    Returns:
        合并后的配置字典（嵌套结构）。

    Raises:
        ConfigError: 配置值校验失败。
        FileNotFoundError: 显式指定的路径不存在。
    """
    if config_path is not None:
        config_path = Path(config_path)
        if not config_path.is_file():
            raise FileNotFoundError(f"指定的配置文件不存在: {config_path}")
        file_to_load = config_path
    else:
        file_to_load = _find_config_file()

    if file_to_load is None:
        # 没找到任何配置文件，返回默认值的深拷贝
        return json.loads(json.dumps(_DEFAULTS))

    # 读取配置文件
    suffix = file_to_load.suffix.lower()
    text = file_to_load.read_text(encoding="utf-8")

    if suffix in (".yaml", ".yml"):
        loaded = yaml.safe_load(text)
    elif suffix == ".json":
        loaded = json.loads(text)
    else:
        raise ConfigError(f"不支持的配置文件格式: {suffix}")

    if not isinstance(loaded, dict):
        raise ConfigError("配置文件顶层必须是字典结构")

    # 校验
    _validate_config(loaded)

    # 合并
    return _deep_merge(_DEFAULTS, loaded)


def flatten_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """将嵌套配置展平为单层字典，方便按 key 索引。

    例如: {"scoring": {"metric_weight": 0.5}} → {"scoring.metric_weight": 0.5}
    """
    flat: dict[str, Any] = {}
    for section, values in cfg.items():
        if isinstance(values, dict):
            for k, v in values.items():
                flat[f"{section}.{k}"] = v
        else:
            flat[section] = values
    return flat


# ── 旧式 Config dataclass（保持向后兼容） ─────────────────────────────

@dataclass(frozen=True)
class Config:
    """ReproChecker 全局配置"""

    # 数据目录
    data_dir: Path = field(default_factory=lambda: Path.home() / ".reprochecker")
    db_path: Path = field(default_factory=lambda: Path.home() / ".reprochecker" / "checks.db")
    reports_dir: Path = field(default_factory=lambda: Path.home() / ".reprochecker" / "reports")
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".reprochecker" / "cache")

    # 运行参数
    default_timeout: int = 14400  # 4 小时
    default_seed: int = 42
    max_output_lines: int = 1000  # stdout/stderr 保留行数

    # 评分权重
    metric_weight: float = 0.50
    env_weight: float = 0.20
    code_weight: float = 0.30

    # 容差阈值
    tolerance_excellent: float = 0.01  # <1% 完全复现
    tolerance_good: float = 0.05      # 1-5% 基本复现
    tolerance_fair: float = 0.10       # 5-10% 部分复现
    tolerance_poor: float = 0.20       # 10-20% 难以复现

    # LLM 配置
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"
    llm_api_key: str = field(
        default_factory=lambda: os.environ.get("OPENAI_API_KEY", "")
    )

    def ensure_dirs(self) -> None:
        """确保所有必要目录存在"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)


_config: Config | None = None


def get_config() -> Config:
    """获取全局配置单例"""
    global _config
    if _config is None:
        _config = Config()
        _config.ensure_dirs()
    return _config
