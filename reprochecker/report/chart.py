"""对比差异图 — 论文值 vs 实际值的可视化柱状图"""

from __future__ import annotations

from pathlib import Path

from reprochecker.storage.db import Database

db = Database()


def generate_comparison_chart(
    check_id: int,
    output_path: Path | None = None,
) -> Path | None:
    """生成论文值 vs 实际值的柱状对比图

    Args:
        check_id: 检验记录 ID
        output_path: 输出图片路径，默认 comparison_{check_id}.png

    Returns:
        图片路径，matplotlib 未安装时返回 None
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return None

    comparisons = db.get_comparisons(check_id)
    if not comparisons:
        return None

    output_path = output_path or Path(f"comparison_{check_id}.png")

    metric_names = [c["metric_name"] for c in comparisons]
    paper_vals = [c.get("paper_value", 0) or 0 for c in comparisons]
    actual_vals = [c.get("actual_value", 0) or 0 for c in comparisons]

    x = np.arange(len(metric_names))
    width = 0.35

    fig, ax = plt.subplots(figsize=(max(6, len(metric_names) * 1.5), 5))

    bars1 = ax.bar(x - width / 2, paper_vals, width, label="Paper", color="#4A90D9", alpha=0.9)
    bars2 = ax.bar(x + width / 2, actual_vals, width, label="Actual", color="#E8524A", alpha=0.9)

    # 标注数值
    for bar in bars1:
        height = bar.get_height()
        ax.annotate(f"{height:.2f}",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8)

    for bar in bars2:
        height = bar.get_height()
        ax.annotate(f"{height:.2f}",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=8)

    # 标记达标/不达标
    for i, c in enumerate(comparisons):
        ok = c.get("within_tolerance")
        marker = "✓" if ok else "✗"
        color = "#27AE60" if ok else "#E74C3C"
        max_val = max(paper_vals[i], actual_vals[i])
        ax.text(
            x[i], max_val * 1.08, marker,
            ha="center", fontsize=14, color=color, fontweight="bold",
        )

    ax.set_ylabel("Value")
    ax.set_title(f"Reproduction Comparison — Check #{check_id}")
    ax.set_xticks(x)
    ax.set_xticklabels(metric_names, rotation=30, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)

    db.update_check(check_id, report_path=str(output_path))
    return output_path


def generate_trend_chart(
    repo_url: str,
    output_path: Path | None = None,
    limit: int = 10,
) -> Path | None:
    """生成评分趋势折线图

    Args:
        repo_url: 仓库 URL
        output_path: 输出图片路径
        limit: 最多显示条数

    Returns:
        图片路径，matplotlib 未安装时返回 None
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    records = db.get_trend(repo_url, limit=limit)
    if len(records) < 2:
        return None

    output_path = output_path or Path("trend.png")

    dates = [r.get("created_at", "")[:10] for r in records]
    metric_scores = [r.get("metric_score", 0) or 0 for r in records]
    env_scores = [r.get("env_score", 0) or 0 for r in records]
    code_scores = [r.get("code_score", 0) or 0 for r in records]
    overall = [r.get("overall_score", 0) or 0 for r in records]

    fig, ax = plt.subplots(figsize=(max(6, len(records) * 0.8), 5))

    ax.plot(
        range(len(dates)), overall, "o-",
        color="#2C3E50", linewidth=2, label="Overall", zorder=5,
    )
    ax.plot(range(len(dates)), metric_scores, "s--", color="#4A90D9", alpha=0.7, label="Metric")
    ax.plot(range(len(dates)), env_scores, "^--", color="#27AE60", alpha=0.7, label="Environment")
    ax.plot(range(len(dates)), code_scores, "D--", color="#E8524A", alpha=0.7, label="Code Quality")

    ax.set_xticks(range(len(dates)))
    ax.set_xticklabels(dates, rotation=45, ha="right")
    ax.set_ylabel("Score")
    parts = repo_url.rstrip("/").split("/")
    repo_label = f"{parts[-2]}/{parts[-1]}" if len(parts) >= 2 else repo_url
    ax.set_title(f"Reproduction Trend — {repo_label}")
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    ax.set_ylim(0, 105)

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)

    return output_path
