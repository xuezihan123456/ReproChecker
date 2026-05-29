"""环境搭建管理 — 支持 Docker / conda / venv / pip"""

from __future__ import annotations

import json
import re
from pathlib import Path

from reprochecker.logging import get_logger

logger = get_logger(__name__.replace("reprochecker.", ""))

# 环境搭建方法优先级（索引越小优先级越高）
_METHOD_PRIORITY = ["docker", "conda", "venv", "pip"]


def _parse_requirements_txt(repo_path: Path) -> list[dict[str, str]]:
    """解析 requirements.txt 中的包列表。

    Args:
        repo_path: 仓库根目录。

    Returns:
        包字典列表，每项包含 name 和 version。
    """
    req_path = repo_path / "requirements.txt"
    if not req_path.exists():
        return []

    packages: list[dict[str, str]] = []
    try:
        lines = req_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return packages

    # 匹配常见格式：package, package==1.0, package>=1.0, package~=1.0
    pkg_re = re.compile(r"^([A-Za-z0-9_.-]+)\s*(?:([><=!~]=?)\s*([^\s,;#]+))?")

    for line in lines:
        line = line.strip()
        # 跳过注释、空行、选项行、URL 行
        if not line or line.startswith("#") or line.startswith("-") or "://" in line:
            continue
        match = pkg_re.match(line)
        if match:
            name = match.group(1)
            version = ""
            if match.group(2) and match.group(3):
                version = f"{match.group(2)}{match.group(3)}"
            packages.append({"name": name, "version": version})

    return packages


def _parse_environment_yml(repo_path: Path) -> dict:
    """解析 environment.yml 中的 conda 环境信息。

    Args:
        repo_path: 仓库根目录。

    Returns:
        包含 name、python_version、packages 的字典。
    """
    yml_path = repo_path / "environment.yml"
    if not yml_path.exists():
        return {"name": None, "python_version": None, "packages": []}

    try:
        import yaml
        with open(yml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, Exception):
        return {"name": None, "python_version": None, "packages": []}

    if not isinstance(data, dict):
        return {"name": None, "python_version": None, "packages": []}

    env_name = data.get("name", "reprochecker_env")
    deps = data.get("dependencies", [])
    packages: list[dict[str, str]] = []
    python_version: str | None = None

    for dep in deps:
        if isinstance(dep, str):
            # conda 包格式：package=1.0 或 package
            parts = dep.split("=", 1)
            name = parts[0].strip()
            version = parts[1].strip() if len(parts) > 1 else ""
            if name.startswith("python"):
                python_version = version or None
            else:
                packages.append({"name": name, "version": version})
        elif isinstance(dep, dict) and "pip" in dep:
            # pip 子依赖
            for pip_dep in dep["pip"]:
                if isinstance(pip_dep, str):
                    pkg_re = re.compile(r"^([A-Za-z0-9_.-]+)\s*(?:([><=!~]=?)\s*([^\s,;#]+))?")
                    match = pkg_re.match(pip_dep.strip())
                    if match:
                        ver = ""
                        if match.group(2) and match.group(3):
                            ver = f"{match.group(2)}{match.group(3)}"
                        packages.append({"name": match.group(1), "version": ver})

    return {"name": env_name, "python_version": python_version, "packages": packages}


def _parse_setup_packages(repo_path: Path) -> list[dict[str, str]]:
    """从 setup.py / pyproject.toml 中提取 install_requires 列表。

    简单的正则提取，不做完整 AST 解析。

    Args:
        repo_path: 仓库根目录。

    Returns:
        包字典列表。
    """
    packages: list[dict[str, str]] = []

    # 尝试 pyproject.toml
    pyproject = repo_path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8")
        except OSError:
            content = ""
        # 提取 [project] 下的 dependencies 数组
        dep_block = re.search(
            r'\[project\].*?dependencies\s*=\s*\[(.*?)\]',
            content, re.DOTALL,
        )
        if dep_block:
            for m in re.finditer(r'"([^"]+)"', dep_block.group(1)):
                dep_str = m.group(1)
                pkg_re = re.compile(r"^([A-Za-z0-9_.-]+)\s*(?:([><=!~]=?)\s*([^\s,;#]+))?")
                match = pkg_re.match(dep_str)
                if match:
                    ver = ""
                    if match.group(2) and match.group(3):
                        ver = f"{match.group(2)}{match.group(3)}"
                    packages.append({"name": match.group(1), "version": ver})
        return packages

    # 尝试 setup.py（正则提取 install_requires）
    setup_py = repo_path / "setup.py"
    if setup_py.exists():
        try:
            content = setup_py.read_text(encoding="utf-8")
        except OSError:
            return packages
        # 匹配 install_requires=[...] 块
        dep_block = re.search(r"install_requires\s*=\s*\[(.*?)\]", content, re.DOTALL)
        if dep_block:
            for m in re.finditer(r"['\"]([^'\"]+)['\"]", dep_block.group(1)):
                dep_str = m.group(1)
                pkg_re = re.compile(r"^([A-Za-z0-9_.-]+)\s*(?:([><=!~]=?)\s*([^\s,;#]+))?")
                match = pkg_re.match(dep_str)
                if match:
                    ver = ""
                    if match.group(2) and match.group(3):
                        ver = f"{match.group(2)}{match.group(3)}"
                    packages.append({"name": match.group(1), "version": ver})

    return packages


def _determine_method(analysis: dict) -> str:
    """根据仓库分析结果自动选择环境搭建方法。

    优先级：Docker > conda > venv > pip

    Args:
        analysis: analyze_repo 返回的分析字典。

    Returns:
        选定的方法名称。
    """
    if analysis.get("has_dockerfile"):
        return "docker"
    if analysis.get("has_environment_yml"):
        return "conda"
    if analysis.get("has_requirements"):
        return "venv"
    return "pip"


def _build_docker(repo_path: Path, analysis: dict) -> dict:
    """Docker 环境搭建（模拟实现）。

    Args:
        repo_path: 仓库根目录。
        analysis: 仓库分析结果。

    Returns:
        搭建结果字典。
    """
    log_lines: list[str] = []
    log_lines.append("[docker] 检测到 Dockerfile")
    log_lines.append(f"[docker] 仓库路径: {repo_path}")

    # 读取 Dockerfile 内容用于日志
    dockerfile = repo_path / "Dockerfile"
    try:
        content = dockerfile.read_text(encoding="utf-8")
        # 提取 FROM 指令
        from_lines = [
            line for line in content.splitlines()
            if line.strip().upper().startswith("FROM")
        ]
        for fl in from_lines:
            log_lines.append(f"[docker] 基础镜像: {fl.strip()}")
    except OSError:
        log_lines.append("[docker] 警告: 无法读取 Dockerfile 内容")

    # 模拟 docker build 命令
    log_lines.append("[docker] 执行: docker build -t reprochecker-env .")
    log_lines.append("[docker] 注意: 实际 Docker 构建尚未实现，当前为模拟模式")

    # 同时解析 requirements.txt 获取包信息
    packages = _parse_requirements_txt(repo_path)
    if not packages:
        packages = _parse_setup_packages(repo_path)

    return {
        "method": "docker",
        "packages": packages,
        "package_count": len(packages),
        "log": "\n".join(log_lines),
    }


def _build_conda(repo_path: Path, analysis: dict) -> dict:
    """Conda 环境搭建（模拟实现）。

    Args:
        repo_path: 仓库根目录。
        analysis: 仓库分析结果。

    Returns:
        搭建结果字典。
    """
    log_lines: list[str] = []
    env_info = _parse_environment_yml(repo_path)
    env_name = env_info.get("name") or "reprochecker_env"
    packages = env_info.get("packages", [])

    log_lines.append(f"[conda] 检测到 environment.yml, 环境名: {env_name}")
    log_lines.append(f"[conda] Python 版本: {env_info.get('python_version', '未指定')}")
    log_lines.append(f"[conda] 包数量: {len(packages)}")

    # 模拟 conda 命令
    log_lines.append(f"[conda] 执行: conda env create -f environment.yml -n {env_name}")
    log_lines.append("[conda] 注意: 实际 conda 环境创建尚未实现，当前为模拟模式")

    for pkg in packages:
        ver_str = f" ({pkg['version']})" if pkg.get("version") else ""
        log_lines.append(f"[conda]   - {pkg['name']}{ver_str}")

    return {
        "method": "conda",
        "packages": packages,
        "package_count": len(packages),
        "log": "\n".join(log_lines),
    }


def _build_venv(repo_path: Path, analysis: dict) -> dict:
    """venv + pip 环境搭建（模拟实现）。

    Args:
        repo_path: 仓库根目录。
        analysis: 仓库分析结果。

    Returns:
        搭建结果字典。
    """
    log_lines: list[str] = []
    packages = _parse_requirements_txt(repo_path)

    log_lines.append("[venv] 检测到 requirements.txt")
    log_lines.append(f"[venv] 包数量: {len(packages)}")
    log_lines.append("[venv] 执行: python -m venv .venv && source .venv/bin/activate")
    log_lines.append("[venv] 执行: pip install -r requirements.txt")
    log_lines.append("[venv] 注意: 实际 venv 创建尚未实现，当前为模拟模式")

    for pkg in packages:
        ver_str = f" ({pkg['version']})" if pkg.get("version") else ""
        log_lines.append(f"[venv]   - {pkg['name']}{ver_str}")

    return {
        "method": "venv",
        "packages": packages,
        "package_count": len(packages),
        "log": "\n".join(log_lines),
    }


def _build_pip(repo_path: Path, analysis: dict) -> dict:
    """pip 直接安装（模拟实现）。

    尝试从 setup.py / pyproject.toml 提取依赖。

    Args:
        repo_path: 仓库根目录。
        analysis: 仓库分析结果。

    Returns:
        搭建结果字典。
    """
    log_lines: list[str] = []
    packages = _parse_setup_packages(repo_path)

    if analysis.get("has_setup_py"):
        log_lines.append("[pip] 检测到 setup.py")
        log_lines.append("[pip] 执行: pip install -e .")
    elif analysis.get("has_pyproject_toml"):
        log_lines.append("[pip] 检测到 pyproject.toml")
        log_lines.append("[pip] 执行: pip install -e .")
    else:
        log_lines.append("[pip] 未检测到标准依赖文件")
        log_lines.append("[pip] 将尝试直接运行入口脚本")

    log_lines.append(f"[pip] 包数量: {len(packages)}")
    log_lines.append("[pip] 注意: 实际 pip 安装尚未实现，当前为模拟模式")

    for pkg in packages:
        ver_str = f" ({pkg['version']})" if pkg.get("version") else ""
        log_lines.append(f"[pip]   - {pkg['name']}{ver_str}")

    return {
        "method": "pip",
        "packages": packages,
        "package_count": len(packages),
        "log": "\n".join(log_lines),
    }


# 方法分发表
_BUILDERS = {
    "docker": _build_docker,
    "conda": _build_conda,
    "venv": _build_venv,
    "pip": _build_pip,
}


def build_env(
    repo_path: Path,
    method: str = "auto",
    analysis: dict | None = None,
) -> dict:
    """根据仓库分析结果搭建运行环境。

    当 method="auto" 时按优先级自动选择：Docker > conda > venv > pip。
    当前版本为模拟实现，记录检测到的方法和包信息，不实际执行安装操作。

    Args:
        repo_path: 仓库根目录。
        method: 环境搭建方式，可选 "auto" / "docker" / "conda" / "venv" / "pip"。
        analysis: analyze_repo 返回的分析字典；为 None 时自动分析。

    Returns:
        包含以下键的字典：
        - method: 实际使用的方法名称
        - packages_json: 包列表的 JSON 字符串
        - package_count: 包数量
        - log: 搭建过程日志
    """
    repo_path = Path(repo_path)

    if analysis is None:
        from reprochecker.repo.analyzer import analyze_repo
        analysis = analyze_repo(repo_path)

    # 确定搭建方法
    if method == "auto":
        method = _determine_method(analysis)

    if method not in _BUILDERS:
        logger.warning("未知的环境搭建方法 '%s'，回退到 pip", method)
        method = "pip"

    # 执行搭建
    builder = _BUILDERS[method]
    result = builder(repo_path, analysis)

    # 序列化包列表
    packages_json = json.dumps(result["packages"], ensure_ascii=False)

    return {
        "method": result["method"],
        "packages_json": packages_json,
        "package_count": result["package_count"],
        "log": result["log"],
    }
