"""reprochecker.config 单元测试"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from reprochecker.config import (
    _DEFAULTS,
    ConfigError,
    _deep_merge,
    _validate_config,
    flatten_config,
    load_config,
)

# ── _deep_merge ────────────────────────────────────────────────────────


class TestDeepMerge:
    def test_flat_merge(self) -> None:
        base = {"a": 1, "b": 2}
        override = {"b": 99, "c": 3}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 99, "c": 3}
        # 不修改原字典
        assert base == {"a": 1, "b": 2}

    def test_nested_merge(self) -> None:
        base = {"scoring": {"metric_weight": 0.5, "env_weight": 0.2}}
        override = {"scoring": {"metric_weight": 0.7}}
        result = _deep_merge(base, override)
        assert result == {"scoring": {"metric_weight": 0.7, "env_weight": 0.2}}

    def test_override_replaces_dict_with_scalar(self) -> None:
        base = {"a": {"x": 1}}
        override = {"a": 42}
        result = _deep_merge(base, override)
        assert result == {"a": 42}


# ── _validate_config ───────────────────────────────────────────────────


class TestValidateConfig:
    def test_valid_full_config(self) -> None:
        cfg = {
            "scoring": {"metric_weight": 0.5, "env_weight": 0.2, "code_weight": 0.3},
            "tolerance": {"excellent": 0.01, "good": 0.05, "acceptable": 0.10, "poor": 0.20},
            "defaults": {"env": "docker", "timeout": 3600, "gpu": 0, "seed": 42},
            "report": {"format": "html", "output_dir": "./reports"},
        }
        _validate_config(cfg)  # 不应抛异常

    def test_valid_partial_config(self) -> None:
        cfg = {"defaults": {"timeout": 7200}}
        _validate_config(cfg)

    def test_empty_config(self) -> None:
        _validate_config({})

    def test_unknown_top_level_key(self) -> None:
        cfg = {"unknown_section": {"foo": 1}}
        with pytest.raises(ConfigError, match="未知字段"):
            _validate_config(cfg)

    def test_unknown_nested_key(self) -> None:
        cfg = {"scoring": {"metric_weight": 0.5, "bad_key": 0.1}}
        with pytest.raises(ConfigError, match="未知字段"):
            _validate_config(cfg)

    def test_weights_not_sum_to_one(self) -> None:
        cfg = {
            "scoring": {"metric_weight": 0.5, "env_weight": 0.3, "code_weight": 0.3},
        }
        with pytest.raises(ConfigError, match="权重之和必须为 1.0"):
            _validate_config(cfg)

    def test_tolerance_not_ascending(self) -> None:
        cfg = {
            "tolerance": {"excellent": 0.10, "good": 0.05, "acceptable": 0.01, "poor": 0.20},
        }
        with pytest.raises(ConfigError, match="容差阈值必须递增"):
            _validate_config(cfg)

    def test_negative_timeout(self) -> None:
        cfg = {"defaults": {"timeout": -1}}
        with pytest.raises(ConfigError, match="timeout 必须为正整数"):
            _validate_config(cfg)


# ── load_config ────────────────────────────────────────────────────────


class TestLoadConfig:
    def test_no_config_file_returns_defaults(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """没有配置文件时应返回默认值"""
        monkeypatch.chdir(tmp_path)
        result = load_config()
        assert result == _DEFAULTS

    def test_load_yaml_config(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "repro.yaml"
        cfg_file.write_text(
            yaml.dump({"scoring": {"metric_weight": 0.6, "env_weight": 0.1, "code_weight": 0.3}}),
            encoding="utf-8",
        )
        result = load_config(cfg_file)
        assert result["scoring"]["metric_weight"] == 0.6
        assert result["scoring"]["env_weight"] == 0.1
        # 未覆盖的字段保持默认值
        assert result["defaults"]["timeout"] == 14400

    def test_load_json_config(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "repro.json"
        cfg_file.write_text(
            json.dumps({"defaults": {"timeout": 7200, "seed": 123}}),
            encoding="utf-8",
        )
        result = load_config(cfg_file)
        assert result["defaults"]["timeout"] == 7200
        assert result["defaults"]["seed"] == 123
        # 未覆盖的字段保持默认值
        assert result["defaults"]["env"] == "auto"

    def test_explicit_path_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="不存在"):
            load_config(tmp_path / "nonexistent.yaml")

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "repro.yaml"
        cfg_file.write_text(
            yaml.dump({"scoring": {"metric_weight": 0.6, "env_weight": 0.3, "code_weight": 0.2}}),
            encoding="utf-8",
        )
        # 权重和 1.1 ≠ 1.0 → 应报错
        with pytest.raises(ConfigError, match="权重之和"):
            load_config(cfg_file)

    def test_yaml_yml_extension(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "repro.yml"
        cfg_file.write_text(
            yaml.dump({"defaults": {"gpu": 2}}),
            encoding="utf-8",
        )
        result = load_config(cfg_file)
        assert result["defaults"]["gpu"] == 2

    def test_unsupported_extension_raises(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "repro.toml"
        cfg_file.write_text("foo = 1", encoding="utf-8")
        with pytest.raises(ConfigError, match="不支持"):
            load_config(cfg_file)

    def test_non_dict_top_level_raises(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "repro.yaml"
        cfg_file.write_text("- item1\n- item2\n", encoding="utf-8")
        with pytest.raises(ConfigError, match="字典结构"):
            load_config(cfg_file)

    def test_search_order_local_over_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """当前目录的 repro.yaml 应优先于 ~/.reprochecker/config.yaml"""
        monkeypatch.chdir(tmp_path)
        # 本地配置
        local_cfg = tmp_path / "repro.yaml"
        local_cfg.write_text(
            yaml.dump({"defaults": {"timeout": 9999}}),
            encoding="utf-8",
        )
        result = load_config()
        assert result["defaults"]["timeout"] == 9999

    def test_merge_preserves_nested_defaults(self, tmp_path: Path) -> None:
        """只覆盖部分字段时，同 section 的其他字段应保持默认值"""
        cfg_file = tmp_path / "repro.yaml"
        cfg_file.write_text(
            yaml.dump({"tolerance": {"good": 0.03}}),
            encoding="utf-8",
        )
        result = load_config(cfg_file)
        assert result["tolerance"]["good"] == 0.03
        assert result["tolerance"]["excellent"] == 0.01
        assert result["tolerance"]["acceptable"] == 0.10
        assert result["tolerance"]["poor"] == 0.20


# ── flatten_config ─────────────────────────────────────────────────────


class TestFlattenConfig:
    def test_basic_flatten(self) -> None:
        cfg = {"scoring": {"metric_weight": 0.5}, "defaults": {"timeout": 3600}}
        flat = flatten_config(cfg)
        assert flat["scoring.metric_weight"] == 0.5
        assert flat["defaults.timeout"] == 3600

    def test_flat_key_preserved(self) -> None:
        cfg = {"top_level": "value"}
        flat = flatten_config(cfg)
        assert flat["top_level"] == "value"
