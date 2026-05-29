"""可复现性评分计算"""

from __future__ import annotations

from reprochecker.config import get_config


def calculate_score(
    comparisons: list[dict],
    env_info: dict,
    analysis: dict,
) -> dict:
    """计算完整可复现性评分（有论文对比时）

    Args:
        comparisons: metric_compare 返回的对比结果
        env_info: env_builder 返回的环境信息
        analysis: analyzer 返回的分析结果

    Returns:
        包含 overall, grade, metric_score, env_score, code_score
    """
    config = get_config()

    # 指标复现分（50%）
    metric_score = _calc_metric_score(comparisons)

    # 环境复现分（20%）
    env_score = _calc_env_score(env_info, analysis)

    # 代码质量分（30%）
    code_score = _calc_code_score(analysis)

    overall = (
        metric_score * config.metric_weight
        + env_score * config.env_weight
        + code_score * config.code_weight
    )

    return {
        "overall": round(overall, 1),
        "grade": _get_grade(overall),
        "metric_score": round(metric_score, 1),
        "env_score": round(env_score, 1),
        "code_score": round(code_score, 1),
    }


def calculate_score_no_paper(
    env_info: dict,
    analysis: dict,
) -> dict:
    """计算评分（无数论文对比时，仅基于环境和代码质量）"""
    config = get_config()

    env_score = _calc_env_score(env_info, analysis)
    code_score = _calc_code_score(analysis)

    # 无数论文对比时，指标分默认给 50（中性）
    metric_score = 50.0

    overall = (
        metric_score * config.metric_weight
        + env_score * config.env_weight
        + code_score * config.code_weight
    )

    return {
        "overall": round(overall, 1),
        "grade": _get_grade(overall),
        "metric_score": round(metric_score, 1),
        "env_score": round(env_score, 1),
        "code_score": round(code_score, 1),
    }


def _calc_metric_score(comparisons: list[dict]) -> float:
    """指标复现评分（0-100）

    评分逻辑：
    - <1% 误差: 100 分
    - 1-5%: 85 分
    - 5-10%: 65 分
    - 10-20%: 40 分
    - >20%: 15 分
    - 无法对比: 0 分
    """
    if not comparisons:
        return 50.0  # 无对比数据，给中性分

    band_scores = {
        "<1%": 100,
        "1-5%": 85,
        "5-10%": 65,
        "10-20%": 40,
        ">20%": 15,
    }

    total = 0.0
    count = 0
    for c in comparisons:
        band = c.get("tolerance_band")
        if band and band in band_scores:
            total += band_scores[band]
            count += 1

    return total / count if count > 0 else 50.0


def _calc_env_score(env_info: dict, analysis: dict) -> float:
    """环境复现评分（0-100）

    评分项：
    - 有 Dockerfile: +40
    - 有 requirements.txt (有版本锁定): +30
    - 有 requirements.txt (无版本锁定): +15
    - 有 environment.yml: +25
    - 有 setup.py / pyproject.toml: +15
    - Python 版本明确: +10
    - 入口脚本可识别: +10
    """
    score = 0.0

    if analysis.get("has_dockerfile"):
        score += 40
    elif analysis.get("has_requirements"):
        score += 25  # 无 Docker 但有 requirements

    if analysis.get("has_requirements"):
        score += 20  # requirements 基础分

    if analysis.get("python_version"):
        score += 10

    if analysis.get("entry_script"):
        score += 10

    return min(score, 100.0)


def _calc_code_score(analysis: dict) -> float:
    """代码质量评分（0-100）

    评分项：
    - 有 README: +20
    - 有随机种子设置: +20
    - 有数据集下载脚本: +15
    - 有预训练权重: +15
    - 有配置文件: +10
    - 框架可识别: +10
    - 入口脚本可识别: +10
    """
    score = 0.0

    # 依赖管理检测（通过 requirements 间接推断项目较规范）
    if analysis.get("has_requirements"):
        score += 10

    if analysis.get("has_seed"):
        score += 20

    if analysis.get("entry_script"):
        score += 15

    if analysis.get("framework") and analysis["framework"] != "unknown":
        score += 15

    if analysis.get("config_files"):
        score += 10

    # 基础分：代码能被分析
    score += 20

    return min(score, 100.0)


def _get_grade(score: float) -> str:
    """分数转等级"""
    if score >= 90:
        return "A"
    elif score >= 75:
        return "B"
    elif score >= 60:
        return "C"
    elif score >= 40:
        return "D"
    else:
        return "F"
