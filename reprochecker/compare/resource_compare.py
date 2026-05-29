"""模型资源对比 — 参数量、文件大小、推理速度"""

from __future__ import annotations


def compare_resources(
    paper_info: dict,
    actual_info: dict,
) -> dict:
    """对比模型资源信息

    Args:
        paper_info: 论文报告的资源信息，可含 model_params, model_size_mb, inference_ms
        actual_info: 实际测量的资源信息，同上

    Returns:
        对比结果字典
    """
    result: dict = {}

    # 参数量对比
    paper_params = paper_info.get("model_params")
    actual_params = actual_info.get("model_params")
    if paper_params and actual_params:
        param_diff = actual_params - paper_params
        param_pct = abs(param_diff) / paper_params * 100 if paper_params else 0
        result["params"] = {
            "paper": paper_params,
            "actual": actual_params,
            "diff": param_diff,
            "diff_percent": round(param_pct, 1),
            "match": param_pct < 5.0,  # 5% 以内视为一致
        }

    # 模型大小对比
    paper_size = paper_info.get("model_size_mb")
    actual_size = actual_info.get("model_size_mb")
    if paper_size and actual_size:
        size_diff = actual_size - paper_size
        size_pct = abs(size_diff) / paper_size * 100 if paper_size else 0
        result["model_size"] = {
            "paper": paper_size,
            "actual": actual_size,
            "diff_mb": round(size_diff, 1),
            "diff_percent": round(size_pct, 1),
            "match": size_pct < 10.0,  # 10% 以内视为一致
        }

    # 推理速度对比（仅作参考，硬件差异大）
    paper_ms = paper_info.get("inference_ms")
    actual_ms = actual_info.get("inference_ms")
    if paper_ms and actual_ms:
        speed_ratio = actual_ms / paper_ms if paper_ms > 0 else 0
        result["inference_speed"] = {
            "paper_ms": paper_ms,
            "actual_ms": actual_ms,
            "ratio": round(speed_ratio, 2),
            "note": "仅供参考，受硬件差异影响",
        }

    return result


def format_resource_summary(comparison: dict) -> str:
    """格式化资源对比摘要"""
    lines: list[str] = []

    if "params" in comparison:
        p = comparison["params"]
        status = "✓" if p["match"] else "✗"
        lines.append(
            f"  {status} 参数量: {p['paper']:,} → {p['actual']:,} "
            f"({p['diff']:+,}, {p['diff_percent']:+.1f}%)"
        )

    if "model_size" in comparison:
        s = comparison["model_size"]
        status = "✓" if s["match"] else "✗"
        lines.append(
            f"  {status} 模型大小: {s['paper']:.1f}MB → {s['actual']:.1f}MB ({s['diff_mb']:+.1f}MB)"
        )

    if "inference_speed" in comparison:
        sp = comparison["inference_speed"]
        lines.append(
            f"  ~ 推理速度: {sp['paper_ms']:.1f}ms → {sp['actual_ms']:.1f}ms ({sp['ratio']:.2f}x)"
        )

    return "\n".join(lines) if lines else "  无资源对比数据"
