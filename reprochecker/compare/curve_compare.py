"""训练曲线对比 — DTW 相似度计算"""

from __future__ import annotations

import math


def compare_curves(
    paper_curve: list[dict],
    actual_curve: list[dict],
) -> dict:
    """对比两条训练曲线

    Args:
        paper_curve: 论文曲线数据，每项含 step, value
        actual_curve: 实际曲线数据，每项含 step, value

    Returns:
        包含 similarity, trend_match, overfit_detected, underfit_detected
    """
    if not paper_curve or not actual_curve:
        return {
            "similarity": 0.0,
            "trend_match": "unknown",
            "overfit_detected": False,
            "underfit_detected": False,
        }

    paper_vals = [p["value"] for p in paper_curve]
    actual_vals = [p["value"] for p in actual_curve]

    # 对齐长度（截取到较短的长度）
    min_len = min(len(paper_vals), len(actual_vals))
    paper_vals = paper_vals[:min_len]
    actual_vals = actual_vals[:min_len]

    # DTW 相似度
    dtw_dist = _dtw_distance(paper_vals, actual_vals)
    max_dist = max(_euclidean(paper_vals, actual_vals), 1e-8)
    similarity = max(0.0, 1.0 - dtw_dist / max_dist)

    # 趋势匹配
    trend_match = _compare_trend(paper_vals, actual_vals)

    # 过拟合/欠拟合检测
    overfit = _detect_overfit(actual_vals)
    underfit = _detect_underfit(actual_vals)

    return {
        "similarity": round(similarity, 4),
        "trend_match": trend_match,
        "overfit_detected": overfit,
        "underfit_detected": underfit,
    }


def _dtw_distance(s: list[float], t: list[float]) -> float:
    """Dynamic Time Warping 距离"""
    n, m = len(s), len(t)
    # 使用 O(m) 空间的 DTW
    prev = [float("inf")] * (m + 1)
    curr = [float("inf")] * (m + 1)
    prev[0] = 0.0

    for i in range(1, n + 1):
        curr[0] = float("inf")
        for j in range(1, m + 1):
            cost = abs(s[i - 1] - t[j - 1])
            curr[j] = cost + min(prev[j], curr[j - 1], prev[j - 1])
        prev, curr = curr, prev

    return prev[m]


def _euclidean(a: list[float], b: list[float]) -> float:
    """欧氏距离"""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _compare_trend(paper: list[float], actual: list[float]) -> str:
    """比较收敛趋势"""
    if len(paper) < 3 or len(actual) < 3:
        return "insufficient_data"

    # 计算斜率（简单线性回归）
    paper_slope = _slope(paper)
    actual_slope = _slope(actual)

    # 符号一致
    if paper_slope * actual_slope > 0:
        return "consistent"
    elif abs(paper_slope) < 0.001 and abs(actual_slope) < 0.001:
        return "both_flat"
    else:
        return "divergent"


def _slope(values: list[float]) -> float:
    """简单线性回归斜率"""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    return num / den if den != 0 else 0.0


def _detect_overfit(values: list[float]) -> bool:
    """检测过拟合：后段指标下降"""
    if len(values) < 10:
        return False
    mid = len(values) // 2
    first_half_avg = sum(values[:mid]) / mid
    second_half_avg = sum(values[mid:]) / (len(values) - mid)
    # 损失类指标上升 或 精度类指标下降
    return second_half_avg > first_half_avg * 1.1


def _detect_underfit(values: list[float]) -> bool:
    """检测欠拟合：指标未收敛"""
    if len(values) < 10:
        return False
    last_10pct = values[len(values) * 9 // 10:]
    if not last_10pct:
        return False
    mean = sum(last_10pct) / len(last_10pct)
    variance = sum((v - mean) ** 2 for v in last_10pct) / len(last_10pct)
    # 后 10% 波动大说明未收敛
    return variance > 0.01
