"""可复现性徽章 SVG 生成器

生成类似 shields.io 风格的 SVG 徽章，可嵌入 README。
"""

from __future__ import annotations

from pathlib import Path

from reprochecker.storage.db import Database

db = Database()

# 等级颜色映射
_GRADE_COLORS: dict[str, str] = {
    "A": "#22c55e",
    "B": "#3b82f6",
    "C": "#f59e0b",
    "D": "#f97316",
    "F": "#ef4444",
}

_GRADE_LABELS: dict[str, str] = {
    "A": "完全可复现",
    "B": "基本可复现",
    "C": "部分可复现",
    "D": "难以复现",
    "F": "无法复现",
}


def _text_width(text: str, char_width: float = 7.0) -> float:
    """估算文本宽度（像素），用于 SVG 布局。"""
    return len(text) * char_width


def generate_badge_svg(
    grade: str,
    score: float,
    repo_name: str = "",
) -> str:
    """生成 SVG 徽章字符串。

    Args:
        grade: 等级 (A/B/C/D/F)
        score: 评分 (0-100)
        repo_name: 仓库名（可选，显示在左侧）

    Returns:
        SVG 字符串
    """
    grade = grade.upper() if grade else "?"
    color = _GRADE_COLORS.get(grade, "#6b7280")
    score_text = f"{score:.0f}/100"

    # 计算宽度
    left_text = repo_name or "reproducibility"
    left_w = max(_text_width(left_text) + 20, 110)
    right_text = f"{grade} ({score_text})"
    right_w = max(_text_width(right_text) + 20, 80)
    total_w = left_w + right_w

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="20">
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{total_w}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{left_w}" height="20" fill="#555"/>
    <rect x="{left_w}" width="{right_w}" height="20" fill="{color}"/>
    <rect width="{total_w}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle"
     font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{left_w / 2}" y="15" fill="#010101" fill-opacity=".3">{left_text}</text>
    <text x="{left_w / 2}" y="14">{left_text}</text>
    <text x="{left_w + right_w / 2}" y="15" fill="#010101" fill-opacity=".3">{right_text}</text>
    <text x="{left_w + right_w / 2}" y="14">{right_text}</text>
  </g>
</svg>'''
    return svg


def generate_badge(
    check_id: int,
    output_path: Path | None = None,
) -> Path:
    """为指定检验生成 SVG 徽章文件。

    Args:
        check_id: 检验 ID
        output_path: 输出路径，为 None 则使用默认路径

    Returns:
        徽章文件路径
    """
    record = db.get_check(check_id)
    if not record:
        raise ValueError(f"检验记录 #{check_id} 不存在")

    grade = record.get("grade", "F") or "F"
    score = record.get("overall_score", 0) or 0
    repo_name = record.get("repo_name", "") or ""

    svg = generate_badge_svg(grade, score, repo_name)

    if output_path is None:
        from reprochecker.config import get_config

        out_dir = get_config().reports_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"badge_{check_id}.svg"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")
    return output_path
