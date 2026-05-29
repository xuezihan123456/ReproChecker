"""评分模块测试"""

from __future__ import annotations

import pytest

from reprochecker.report.scorer import (
    _calc_code_score,
    _calc_env_score,
    _calc_metric_score,
    _get_grade,
    calculate_score,
    calculate_score_no_paper,
)


class TestScorer:
    def test_perfect_score(self) -> None:
        comparisons = [{"tolerance_band": "<1%"}]
        env_info = {"method": "docker"}
        analysis = {
            "has_dockerfile": True,
            "has_requirements": True,
            "python_version": "3.10",
            "entry_script": "train.py",
            "has_seed": True,
            "framework": "pytorch",
            "config_files": ["config.yaml"],
        }
        result = calculate_score(comparisons, env_info, analysis)
        # metric=100*0.5 + env=80*0.2 + code=90*0.3 = 50+16+27 = 93.0
        assert result["overall"] == pytest.approx(93.0, abs=0.1)
        assert result["grade"] == "A"

    def test_worst_score(self) -> None:
        comparisons = [{"tolerance_band": ">20%"}]
        env_info: dict = {}
        analysis: dict = {}
        result = calculate_score(comparisons, env_info, analysis)
        # metric=15*0.5 + env=0*0.2 + code=20*0.3 = 7.5+0+6 = 13.5
        assert result["overall"] == pytest.approx(13.5, abs=0.1)
        assert result["grade"] == "F"

    def test_no_paper_score(self) -> None:
        env_info = {"method": "pip"}
        analysis = {"has_requirements": True, "has_seed": True, "entry_script": "main.py"}
        result = calculate_score_no_paper(env_info, analysis)
        assert "overall" in result
        assert "grade" in result

    def test_metric_score_bands(self) -> None:
        assert _calc_metric_score([{"tolerance_band": "<1%"}]) == 100
        assert _calc_metric_score([{"tolerance_band": "1-5%"}]) == 85
        assert _calc_metric_score([{"tolerance_band": "5-10%"}]) == 65
        assert _calc_metric_score([{"tolerance_band": "10-20%"}]) == 40
        assert _calc_metric_score([{"tolerance_band": ">20%"}]) == 15

    def test_metric_score_empty(self) -> None:
        assert _calc_metric_score([]) == 50.0

    def test_env_score_docker(self) -> None:
        analysis = {
            "has_dockerfile": True, "has_requirements": True,
            "python_version": "3.10", "entry_script": "train.py",
        }
        score = _calc_env_score({}, analysis)
        assert score == 80  # 40 + 20 + 10 + 10

    def test_env_score_pip_only(self) -> None:
        analysis = {"has_requirements": True}
        score = _calc_env_score({}, analysis)
        assert score == 45  # 25 + 20

    def test_code_score_full(self) -> None:
        analysis = {
            "has_seed": True,
            "entry_script": "train.py",
            "framework": "pytorch",
            "config_files": ["config.yaml"],
        }
        score = _calc_code_score(analysis)
        # 20(seed) + 15(entry) + 15(framework) + 10(config) + 20(base) = 80
        assert score == 80

    def test_code_score_minimal(self) -> None:
        score = _calc_code_score({})
        assert score == 20  # 基础分

    def test_grade_boundaries(self) -> None:
        assert _get_grade(95) == "A"
        assert _get_grade(85) == "B"
        assert _get_grade(70) == "C"
        assert _get_grade(50) == "D"
        assert _get_grade(30) == "F"

    def test_mixed_tolerances(self) -> None:
        comparisons = [
            {"tolerance_band": "<1%"},
            {"tolerance_band": "1-5%"},
            {"tolerance_band": ">20%"},
        ]
        score = _calc_metric_score(comparisons)
        expected = (100 + 85 + 15) / 3
        assert score == pytest.approx(expected, abs=0.1)
