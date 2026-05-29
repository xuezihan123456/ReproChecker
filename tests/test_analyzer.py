"""仓库分析器测试"""

from __future__ import annotations

from pathlib import Path

from reprochecker.repo.analyzer import (
    _ENTRY_KEYWORDS,
    _collect_py_files,
    _parse_imports,
    analyze_repo,
    detect_entry_script,
    detect_framework,
    detect_seed,
)


class TestDetectFramework:
    """框架检测测试"""

    def test_detects_pytorch(self) -> None:
        assert detect_framework({"torch", "torchvision"}) == "pytorch"

    def test_detects_tensorflow(self) -> None:
        assert detect_framework({"tensorflow", "keras"}) == "tensorflow"

    def test_detects_jax(self) -> None:
        assert detect_framework({"jax", "flax"}) == "jax"

    def test_unknown_framework(self) -> None:
        assert detect_framework({"numpy", "pandas"}) == "unknown"

    def test_empty_modules(self) -> None:
        assert detect_framework(set()) == "unknown"


class TestDetectEntryScript:
    """入口脚本检测测试"""

    def test_finds_train_py(self, tmp_path: Path) -> None:
        (tmp_path / "train.py").write_text("# training script\n", encoding="utf-8")
        py_files = _collect_py_files(tmp_path)
        result = detect_entry_script(tmp_path, py_files)
        assert result == "train.py"

    def test_finds_main_py(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("# main\n", encoding="utf-8")
        py_files = _collect_py_files(tmp_path)
        result = detect_entry_script(tmp_path, py_files)
        assert result == "main.py"

    def test_no_entry_script(self, tmp_path: Path) -> None:
        (tmp_path / "utils.py").write_text("# utils\n", encoding="utf-8")
        py_files = _collect_py_files(tmp_path)
        result = detect_entry_script(tmp_path, py_files)
        assert result is None

    def test_prioritizes_train_over_main(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("# main\n", encoding="utf-8")
        (tmp_path / "train.py").write_text("# train\n", encoding="utf-8")
        py_files = _collect_py_files(tmp_path)
        result = detect_entry_script(tmp_path, py_files)
        assert result == "train.py"


class TestDetectSeed:
    """种子检测测试"""

    def test_detects_manual_seed(self, tmp_path: Path) -> None:
        (tmp_path / "train.py").write_text(
            "import torch\ntorch.manual_seed(42)\n", encoding="utf-8"
        )
        py_files = _collect_py_files(tmp_path)
        assert detect_seed(py_files) is True

    def test_detects_random_seed(self, tmp_path: Path) -> None:
        (tmp_path / "train.py").write_text("import random\nrandom.seed(42)\n", encoding="utf-8")
        py_files = _collect_py_files(tmp_path)
        assert detect_seed(py_files) is True

    def test_no_seed(self, tmp_path: Path) -> None:
        (tmp_path / "train.py").write_text("print('hello')\n", encoding="utf-8")
        py_files = _collect_py_files(tmp_path)
        assert detect_seed(py_files) is False


class TestCollectPyFiles:
    """Python 文件收集测试"""

    def test_collects_py_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.py").write_text("# a\n", encoding="utf-8")
        (tmp_path / "b.py").write_text("# b\n", encoding="utf-8")
        (tmp_path / "c.txt").write_text("text\n", encoding="utf-8")
        result = _collect_py_files(tmp_path)
        names = {p.name for p in result}
        assert "a.py" in names
        assert "b.py" in names
        assert "c.txt" not in names

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "hook.py").write_text("# hook\n", encoding="utf-8")
        (tmp_path / "main.py").write_text("# main\n", encoding="utf-8")
        result = _collect_py_files(tmp_path)
        names = {p.name for p in result}
        assert "main.py" in names
        assert "hook.py" not in names


class TestParseImports:
    """import 解析测试"""

    def test_extracts_imports(self, tmp_path: Path) -> None:
        (tmp_path / "train.py").write_text(
            "import torch\nimport numpy as np\nfrom os import path\n",
            encoding="utf-8",
        )
        py_files = _collect_py_files(tmp_path)
        modules = _parse_imports(py_files)
        assert "torch" in modules
        assert "numpy" in modules
        assert "os" in modules


class TestAnalyzeRepo:
    """完整仓库分析测试"""

    def test_full_analysis(self, tmp_path: Path) -> None:
        (tmp_path / "train.py").write_text(
            "import torch\ntorch.manual_seed(42)\n", encoding="utf-8"
        )
        (tmp_path / "requirements.txt").write_text("torch>=2.0\n", encoding="utf-8")
        (tmp_path / "Dockerfile").write_text("FROM python:3.10\n", encoding="utf-8")

        result = analyze_repo(tmp_path)

        assert result["framework"] == "pytorch"
        assert result["entry_script"] == "train.py"
        assert result["has_seed"] is True
        assert result["has_requirements"] is True
        assert result["has_dockerfile"] is True

    def test_minimal_repo(self, tmp_path: Path) -> None:
        (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")

        result = analyze_repo(tmp_path)

        assert result["framework"] == "unknown"
        assert result["entry_script"] == "main.py"
        assert result["has_seed"] is False
        assert result["has_requirements"] is False
        assert result["has_dockerfile"] is False


class TestEntryKeywordsNoDuplicates:
    """入口关键词无重复测试"""

    def test_no_duplicates(self) -> None:
        assert len(_ENTRY_KEYWORDS) == len(set(_ENTRY_KEYWORDS))
