"""环境搭建模块测试"""

from __future__ import annotations

from pathlib import Path

from reprochecker.repo.env_builder import (
    _determine_method,
    _parse_environment_yml,
    _parse_requirements_txt,
    _parse_setup_packages,
    build_env,
)


class TestParseRequirementsTxt:
    """requirements.txt 解析测试"""

    def test_basic_packages(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text(
            "torch>=2.0\nnumpy==1.24.0\npandas\n", encoding="utf-8"
        )
        pkgs = _parse_requirements_txt(tmp_path)
        names = [p["name"] for p in pkgs]
        assert "torch" in names
        assert "numpy" in names
        assert "pandas" in names

    def test_version_parsing(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text(
            "torch>=2.0\nnumpy==1.24.0\n", encoding="utf-8"
        )
        pkgs = _parse_requirements_txt(tmp_path)
        by_name = {p["name"]: p["version"] for p in pkgs}
        assert by_name["torch"] == ">=2.0"
        assert by_name["numpy"] == "==1.24.0"

    def test_skips_comments_and_blank(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text(
            "# comment\n\ntorch\n  # indented\n", encoding="utf-8"
        )
        pkgs = _parse_requirements_txt(tmp_path)
        assert len(pkgs) == 1
        assert pkgs[0]["name"] == "torch"

    def test_skips_options_and_urls(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text(
            "-f https://download.pytorch.org\n--index-url https://pypi.org\ntorch\n",
            encoding="utf-8",
        )
        pkgs = _parse_requirements_txt(tmp_path)
        assert len(pkgs) == 1

    def test_no_file(self, tmp_path: Path) -> None:
        assert _parse_requirements_txt(tmp_path) == []

    def test_empty_file(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("", encoding="utf-8")
        assert _parse_requirements_txt(tmp_path) == []


class TestParseEnvironmentYml:
    """environment.yml 解析测试"""

    def test_basic_yaml(self, tmp_path: Path) -> None:
        content = (
            "name: myenv\ndependencies:\n"
            "  - python=3.10\n  - numpy=1.24\n  - pip:\n    - torch>=2.0\n"
        )
        (tmp_path / "environment.yml").write_text(content, encoding="utf-8")
        result = _parse_environment_yml(tmp_path)
        assert result["name"] == "myenv"
        assert result["python_version"] == "3.10"
        names = [p["name"] for p in result["packages"]]
        assert "numpy" in names
        assert "torch" in names

    def test_no_file(self, tmp_path: Path) -> None:
        result = _parse_environment_yml(tmp_path)
        assert result["name"] is None
        assert result["python_version"] is None
        assert result["packages"] == []

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "environment.yml").write_text("not: valid: yaml: [[", encoding="utf-8")
        result = _parse_environment_yml(tmp_path)
        # Should not crash, returns defaults
        assert isinstance(result, dict)


class TestParseSetupPackages:
    """setup.py / pyproject.toml 解析测试"""

    def test_pyproject_toml(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "test"\ndependencies = [\n  "torch>=2.0",\n  "numpy",\n]\n',
            encoding="utf-8",
        )
        pkgs = _parse_setup_packages(tmp_path)
        names = [p["name"] for p in pkgs]
        assert "torch" in names
        assert "numpy" in names

    def test_setup_py(self, tmp_path: Path) -> None:
        content = (
            'from setuptools import setup\nsetup(\n  name="test",\n'
            '  install_requires=["torch>=2.0", "numpy"],\n)\n'
        )
        (tmp_path / "setup.py").write_text(content, encoding="utf-8")
        pkgs = _parse_setup_packages(tmp_path)
        names = [p["name"] for p in pkgs]
        assert "torch" in names
        assert "numpy" in names

    def test_no_files(self, tmp_path: Path) -> None:
        assert _parse_setup_packages(tmp_path) == []


class TestDetermineMethod:
    """环境方法选择测试"""

    def test_docker_highest_priority(self) -> None:
        analysis = {
            "has_dockerfile": True,
            "has_environment_yml": True,
            "has_requirements": True,
        }
        assert _determine_method(analysis) == "docker"

    def test_conda_second_priority(self) -> None:
        analysis = {
            "has_dockerfile": False,
            "has_environment_yml": True,
            "has_requirements": True,
        }
        assert _determine_method(analysis) == "conda"

    def test_venv_third_priority(self) -> None:
        analysis = {
            "has_dockerfile": False,
            "has_environment_yml": False,
            "has_requirements": True,
        }
        assert _determine_method(analysis) == "venv"

    def test_pip_lowest_priority(self) -> None:
        analysis = {
            "has_dockerfile": False,
            "has_environment_yml": False,
            "has_requirements": False,
        }
        assert _determine_method(analysis) == "pip"

    def test_empty_analysis(self) -> None:
        assert _determine_method({}) == "pip"


class TestBuildEnv:
    """完整环境搭建测试"""

    def test_auto_selects_venv(self, tmp_path: Path) -> None:
        (tmp_path / "requirements.txt").write_text("torch>=2.0\n", encoding="utf-8")
        result = build_env(tmp_path, method="auto", analysis={"has_requirements": True})
        assert result["method"] == "venv"
        assert result["package_count"] >= 1

    def test_explicit_pip(self, tmp_path: Path) -> None:
        result = build_env(tmp_path, method="pip", analysis={})
        assert result["method"] == "pip"

    def test_unknown_method_falls_back(self, tmp_path: Path) -> None:
        result = build_env(tmp_path, method="invalid", analysis={})
        assert result["method"] == "pip"
