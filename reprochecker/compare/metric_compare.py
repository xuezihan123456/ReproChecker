"""最终指标对比"""

from __future__ import annotations

from reprochecker.config import get_config


def compare_metrics(
    paper_results: list[dict],
    actual_results: list[dict],
) -> list[dict]:
    """对比论文报告指标与实际运行指标

    Args:
        paper_results: 论文提取的指标列表，每项含 metric_name, metric_value
        actual_results: 实际运行的指标列表，每项含 metric_name, metric_value

    Returns:
        对比结果列表，每项含 metric_name, paper_value, actual_value,
        absolute_error, relative_error, within_tolerance, tolerance_band
    """
    config = get_config()

    # 按指标名索引实际结果（取最后一次出现的值）
    actual_map: dict[str, float] = {}
    for r in actual_results:
        name = _normalize_name(r["metric_name"])
        actual_map[name] = r["metric_value"]

    comparisons: list[dict] = []
    for pr in paper_results:
        name = _normalize_name(pr["metric_name"])
        paper_val = pr["metric_value"]
        actual_val = actual_map.get(name)

        if actual_val is None:
            comparisons.append(
                {
                    "metric_name": pr["metric_name"],
                    "paper_value": paper_val,
                    "actual_value": None,
                    "absolute_error": None,
                    "relative_error": None,
                    "within_tolerance": None,
                    "tolerance_band": None,
                }
            )
            continue

        abs_err = abs(actual_val - paper_val)
        if paper_val != 0:
            rel_err = abs_err / abs(paper_val) * 100
        elif abs_err < 1e-6:
            # 论文值和实际值都接近 0，视为完全匹配
            rel_err = 0.0
        else:
            # 论文值为 0 但实际值非零，使用绝对误差作为替代
            rel_err = abs_err * 100

        band = _get_tolerance_band(rel_err, config)
        within = rel_err <= config.tolerance_poor * 100  # 20% 以内算可复现

        comparisons.append(
            {
                "metric_name": pr["metric_name"],
                "paper_value": paper_val,
                "actual_value": actual_val,
                "absolute_error": round(abs_err, 4),
                "relative_error": round(rel_err, 2),
                "within_tolerance": within,
                "tolerance_band": band,
            }
        )

    return comparisons


def _normalize_name(name: str) -> str:
    """标准化指标名（小写、去空格、统一常见别名）"""
    name = name.strip().lower().replace(" ", "_")
    aliases = {
        "acc": "accuracy",
        "top1": "accuracy",
        "top-1": "accuracy",
        "top1_acc": "accuracy",
        "top5": "top5_accuracy",
        "top-5": "top5_accuracy",
        "f1": "f1",
        "f1_score": "f1",
        "f1-score": "f1",
        "prec": "precision",
        "rec": "recall",
        "map": "map",
        "map50": "map_50",
        "map@50": "map_50",
        "map_0.5": "map_50",
        "bleu": "bleu",
        "bleu-4": "bleu_4",
        "bleu4": "bleu_4",
        "psnr": "psnr",
        "ssim": "ssim",
        "iou": "iou",
        "miou": "miou",
        "m_iou": "miou",
        "perplexity": "perplexity",
        "ppl": "perplexity",
    }
    return aliases.get(name, name)


def _get_tolerance_band(rel_err_pct: float, config: object) -> str:
    """根据相对误差百分比返回容差区间"""
    if rel_err_pct < 1.0:
        return "<1%"
    elif rel_err_pct < 5.0:
        return "1-5%"
    elif rel_err_pct < 10.0:
        return "5-10%"
    elif rel_err_pct < 20.0:
        return "10-20%"
    else:
        return ">20%"
