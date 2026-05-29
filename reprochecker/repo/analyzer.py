"""仓库结构与内容分析"""

from __future__ import annotations

import ast
import re
from pathlib import Path

# 框架 import 模式映射
_FRAMEWORK_PATTERNS: dict[str, list[str]] = {
    "pytorch": ["torch", "pytorch", "torchvision", "torchaudio", "lightning"],
    "tensorflow": ["tensorflow", "tf", "keras", "tensorflow.keras"],
    "jax": ["jax", "flax", "optax", "haiku"],
}

# 入口脚本候选关键词（优先级从高到低）
_ENTRY_KEYWORDS = ["train", "main", "run", "test", "eval"]

# 配置文件 glob 模式
_CONFIG_GLOBS = ["*.yaml", "*.yml", "*.toml", "*.json", "*.cfg", "*.ini"]


def _collect_py_files(repo_path: Path, max_files: int = 200) -> list[Path]:
    """递归收集仓库中的 Python 文件，跳过隐藏目录和常见的非源码目录。

    Args:
        repo_path: 仓库根目录。
        max_files: 最大收集数量，防止超大仓库。

    Returns:
        Python 文件路径列表。
    """
    skip_dirs = {
        ".git", "__pycache__", ".venv", "venv", "env", ".env",
        "node_modules", ".mypy_cache", ".pytest_cache", "build", "dist",
        ".eggs", "*.egg-info",
    }
    py_files: list[Path] = []
    for p in repo_path.rglob("*.py"):
        # 检查路径中是否包含需要跳过的目录
        parts = set(p.relative_to(repo_path).parts)
        if parts & skip_dirs:
            continue
        py_files.append(p)
        if len(py_files) >= max_files:
            break
    return py_files


def _parse_imports(py_files: list[Path]) -> set[str]:
    """从 Python 文件中解析所有顶层 import 模块名。

    使用 AST 解析，安全且准确。

    Args:
        py_files: Python 文件路径列表。

    Returns:
        所有 import 的顶层模块名集合。
    """
    modules: set[str] = set()
    for py_file in py_files:
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, OSError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    modules.add(node.module.split(".")[0])
    return modules


def detect_framework(modules: set[str]) -> str:
    """根据 import 模块名检测 ML 框架。

    Args:
        modules: 顶层模块名集合。

    Returns:
        框架名称字符串（pytorch / tensorflow / jax / unknown）。
    """
    for framework, keywords in _FRAMEWORK_PATTERNS.items():
        if any(kw in modules for kw in keywords):
            return framework
    return "unknown"


def detect_python_version(repo_path: Path) -> str | None:
    """从 setup.py、pyproject.toml 或 classifiers 中提取 Python 版本要求。

    Args:
        repo_path: 仓库根目录。

    Returns:
        Python 版本字符串，如 ">=3.8"；未检测到则返回 None。
    """
    # 优先检查 pyproject.toml
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8")
        except OSError:
            content = ""
        # requires-python
        match = re.search(r'requires-python\s*=\s*"([^"]+)"', content)
        if match:
            return match.group(1)
        # classifiers 中的 Python 版本
        for m in re.finditer(r"Programming Language :: Python :: (\d+\.\d+)", content):
            return f">={m.group(1)}"

    # 检查 setup.py
    setup_py = repo_path / "setup.py"
    if setup_py.exists():
        try:
            content = setup_py.read_text(encoding="utf-8")
        except OSError:
            content = ""
        match = re.search(r"python_requires\s*=\s*['\"]([^'\"]+)['\"]", content)
        if match:
            return match.group(1)
        for m in re.finditer(r"Programming Language :: Python :: (\d+\.\d+)", content):
            return f">={m.group(1)}"

    # 检查 setup.cfg
    setup_cfg = repo_path / "setup.cfg"
    if setup_cfg.exists():
        try:
            content = setup_cfg.read_text(encoding="utf-8")
        except OSError:
            content = ""
        match = re.search(r"python_requires\s*=\s*(\S+)", content)
        if match:
            return match.group(1)

    return None


def detect_entry_script(repo_path: Path, py_files: list[Path]) -> str | None:
    """检测项目入口脚本。

    策略：
    1. 在仓库根目录下查找 train.py / main.py / run.py 等
    2. 在子目录中查找包含 argparse 或 __main__ 的文件
    3. 查找 run.sh / run_script.sh

    Args:
        repo_path: 仓库根目录。
        py_files: Python 文件路径列表。

    Returns:
        入口脚本相对路径字符串；未检测到则返回 None。
    """
    # 策略 1：根目录下按关键字匹配
    root_py = {p.name: p for p in py_files if p.parent == repo_path}
    for keyword in _ENTRY_KEYWORDS:
        candidates = [
            name for name in root_py
            if keyword in name.lower() and name.endswith(".py")
        ]
        if candidates:
            # 优先精确匹配
            for preferred in [f"{keyword}.py", f"{keyword}_script.py"]:
                if preferred in candidates:
                    return preferred
            return sorted(candidates)[0]

    # 策略 2：查找 bash 脚本
    for script_name in ("run.sh", "run_script.sh", "run_experiments.sh"):
        if (repo_path / script_name).exists():
            return script_name

    # 策略 3：在所有 py 文件中查找 argparse / __main__
    for py_file in py_files:
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if 'if __name__ == "__main__"' in source and "argparse" in source:
            return str(py_file.relative_to(repo_path))

    return None


def detect_seed(py_files: list[Path]) -> bool:
    """检测代码中是否设置了随机种子。

    使用 AST 扫描函数调用和属性访问中的 seed / random / np.random 等关键字。

    Args:
        py_files: Python 文件路径列表。

    Returns:
        如果检测到种子设置则返回 True。
    """
    seed_patterns = re.compile(
        r"(?:seed|manual_seed|set_seed|np\.random\.seed|random\.seed|tf\.random\.set_seed)",
        re.IGNORECASE,
    )
    for py_file in py_files:
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if seed_patterns.search(source):
            return True
    return False


def detect_config_files(repo_path: Path) -> list[str]:
    """检测仓库中的配置文件。

    Args:
        repo_path: 仓库根目录。

    Returns:
        配置文件相对路径列表。
    """
    config_files: list[str] = []
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv"}
    for pattern in _CONFIG_GLOBS:
        for p in repo_path.rglob(pattern):
            parts = set(p.relative_to(repo_path).parts)
            if parts & skip_dirs:
                continue
            config_files.append(str(p.relative_to(repo_path)))
    return sorted(set(config_files))


def detect_data_dir(repo_path: Path) -> str | None:
    """检测数据集目录。

    Args:
        repo_path: 仓库根目录。

    Returns:
        数据目录名；未检测到则返回 None。
    """
    data_dir_names = {"data", "datasets", "dataset", "data_dir", "corpus"}
    for name in data_dir_names:
        candidate = repo_path / name
        if candidate.is_dir():
            return name
    return None


def infer_default_command(
    entry_script: str | None,
    has_dockerfile: bool,
    repo_path: Path,
) -> str | None:
    """推断默认运行命令。

    Args:
        entry_script: 检测到的入口脚本。
        has_dockerfile: 是否存在 Dockerfile。
        repo_path: 仓库根目录。

    Returns:
        推断的默认命令字符串。
    """
    if entry_script is None:
        return None

    if entry_script.endswith(".sh"):
        return f"bash {entry_script}"

    if entry_script.endswith(".py"):
        return f"python {entry_script}"

    return None


def analyze_repo(repo_path: Path) -> dict:
    """分析仓库结构和内容，返回项目元信息。

    检测项包括：框架、Python 版本、Dockerfile、依赖文件、入口脚本、
    随机种子、配置文件、数据目录、默认命令。

    Args:
        repo_path: 仓库根目录。

    Returns:
        包含以下键的字典：
        - framework: ML 框架名称
        - python_version: Python 版本要求
        - has_dockerfile: 是否有 Dockerfile
        - has_requirements: 是否有 requirements.txt
        - has_environment_yml: 是否有 environment.yml
        - has_setup_py: 是否有 setup.py
        - has_pyproject_toml: 是否有 pyproject.toml
        - entry_script: 入口脚本路径
        - has_seed: 是否设置了随机种子
        - default_command: 推断的默认运行命令
        - config_files: 配置文件列表
        - data_dir: 数据目录名
    """
    repo_path = Path(repo_path)

    py_files = _collect_py_files(repo_path)
    modules = _parse_imports(py_files)

    framework = detect_framework(modules)
    python_version = detect_python_version(repo_path)
    entry_script = detect_entry_script(repo_path, py_files)
    has_seed = detect_seed(py_files)
    config_files = detect_config_files(repo_path)
    data_dir = detect_data_dir(repo_path)

    has_dockerfile = (repo_path / "Dockerfile").exists()
    has_requirements = (repo_path / "requirements.txt").exists()
    has_environment_yml = (repo_path / "environment.yml").exists()
    has_setup_py = (repo_path / "setup.py").exists()
    has_pyproject_toml = (repo_path / "pyproject.toml").exists()

    default_command = infer_default_command(entry_script, has_dockerfile, repo_path)

    return {
        "framework": framework,
        "python_version": python_version,
        "has_dockerfile": has_dockerfile,
        "has_requirements": has_requirements,
        "has_environment_yml": has_environment_yml,
        "has_setup_py": has_setup_py,
        "has_pyproject_toml": has_pyproject_toml,
        "entry_script": entry_script,
        "has_seed": has_seed,
        "default_command": default_command,
        "config_files": config_files,
        "data_dir": data_dir,
    }
