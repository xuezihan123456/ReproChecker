"""报告生成器"""

from __future__ import annotations

import base64
import csv
import json
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from reprochecker.config import get_config
from reprochecker.storage.db import Database

db = Database()


def generate_training_chart(
    metrics: list[dict],
    output_path: Path,
) -> Path | None:
    """生成训练曲线图

    Args:
        metrics: 指标列表，每个元素包含 name/value/step/epoch
        output_path: 图片输出路径

    Returns:
        图片路径，matplotlib 未安装时返回 None
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    if not metrics:
        return None

    # 按指标名分组
    series: dict[str, list[tuple[int, float]]] = {}
    for m in metrics:
        name = m.get("metric_name") or m.get("name", "unknown")
        value = m.get("metric_value") if m.get("metric_value") is not None else m.get("value")
        step = m.get("step") or m.get("epoch") or 0
        if value is not None:
            series.setdefault(name, []).append((step, float(value)))

    if not series:
        return None

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#8b5cf6", "#ec4899"]

    for i, (name, points) in enumerate(sorted(series.items())):
        points.sort(key=lambda p: p[0])
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        color = colors[i % len(colors)]
        ax.plot(xs, ys, marker="o", markersize=3, label=name, color=color, linewidth=1.5)

    ax.set_xlabel("Step / Epoch", fontsize=12)
    ax.set_ylabel("Metric Value", fontsize=12)
    ax.set_title("Training Metrics", fontsize=14, fontweight="bold")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return output_path


def _chart_to_base64(chart_path: Path | None) -> str | None:
    """将图片转为 base64 data URI"""
    if chart_path is None or not chart_path.exists():
        return None
    data = chart_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:image/png;base64,{b64}"


def generate_report(
    check_id: int,
    format: str = "html",
    output_dir: Path | None = None,
) -> Path:
    """生成检验报告

    Args:
        check_id: 检验 ID
        format: 输出格式 html / pdf / json
        output_dir: 输出目录

    Returns:
        报告文件路径
    """
    config = get_config()
    out_dir = output_dir or config.reports_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    record = db.get_check(check_id)
    if not record:
        raise ValueError(f"检验记录 #{check_id} 不存在")

    comparisons = db.get_comparisons(check_id)
    paper_results = db.get_paper_results(check_id)
    actual_results = db.get_actual_results(check_id)

    if format == "json":
        return _generate_json(check_id, record, comparisons, paper_results, actual_results, out_dir)
    elif format == "pdf":
        return _generate_pdf(check_id, record, comparisons, paper_results, actual_results, out_dir)
    elif format == "csv":
        return _generate_csv(check_id, record, comparisons, actual_results, out_dir)
    elif format == "md":
        return _generate_md(check_id, record, comparisons, actual_results, out_dir)
    else:
        return _generate_html(check_id, record, comparisons, paper_results, actual_results, out_dir)


def _generate_json(
    check_id: int,
    record: dict,
    comparisons: list[dict],
    paper_results: list[dict],
    actual_results: list[dict],
    output_dir: Path,
) -> Path:
    """生成 JSON 报告"""
    report = {
        "schema_version": "1.0",
        "check_id": check_id,
        "repo_url": record["repo_url"],
        "commit": record.get("commit_hash"),
        "framework": record.get("framework"),
        "score": {
            "overall": record.get("overall_score"),
            "grade": record.get("grade"),
            "metric_score": record.get("metric_score"),
            "env_score": record.get("env_score"),
            "code_score": record.get("code_score"),
        },
        "paper_results": paper_results,
        "actual_results": actual_results,
        "comparisons": comparisons,
        "code_quality": {
            "has_readme": bool(record.get("has_requirements")),
            "has_requirements": bool(record.get("has_requirements")),
            "has_dockerfile": bool(record.get("has_dockerfile")),
            "has_seed": bool(record.get("has_seed")),
            "entry_script": record.get("entry_script"),
        },
        "environment": {
            "method": record.get("env_method"),
            "packages": record.get("installed_packages"),
        },
        "resources": {
            "duration_sec": record.get("duration_sec"),
            "peak_gpu_mem_mb": record.get("peak_gpu_mem_mb"),
            "model_params": record.get("model_params"),
            "model_size_mb": record.get("model_size_mb"),
            "inference_ms": record.get("inference_ms"),
        },
        "created_at": record.get("created_at"),
    }

    path = output_dir / f"check_{check_id}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    # 更新数据库中的报告路径
    db.update_check(check_id, report_path=str(path))
    return path


def _generate_csv(
    check_id: int,
    record: dict,
    comparisons: list[dict],
    actual_results: list[dict],
    output_dir: Path,
) -> Path:
    """生成 CSV 报告（检验摘要 + 指标对比 + 捕获指标）"""
    path = output_dir / f"check_{check_id}.csv"

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        # 检验摘要
        writer.writerow(["# 检验摘要"])
        writer.writerow(["字段", "值"])
        writer.writerow(["检验ID", check_id])
        writer.writerow(["仓库", record.get("repo_url", "")])
        writer.writerow(["Commit", record.get("commit_hash", "")])
        writer.writerow(["框架", record.get("framework", "")])
        writer.writerow(["入口脚本", record.get("entry_script", "")])
        writer.writerow(["环境方式", record.get("env_method", "")])
        writer.writerow(["总分", record.get("overall_score", "")])
        writer.writerow(["等级", record.get("grade", "")])
        writer.writerow(["指标复现分", record.get("metric_score", "")])
        writer.writerow(["环境复现分", record.get("env_score", "")])
        writer.writerow(["代码质量分", record.get("code_score", "")])
        writer.writerow(["耗时(秒)", record.get("duration_sec", "")])
        writer.writerow([])

        # 指标对比
        if comparisons:
            writer.writerow(["# 指标对比"])
            writer.writerow(["指标名", "论文值", "实际值", "相对误差(%)", "是否达标"])
            for c in comparisons:
                writer.writerow([
                    c.get("metric_name", ""),
                    c.get("paper_value", ""),
                    c.get("actual_value", ""),
                    f"{c.get('relative_error', 0):.1f}",
                    "是" if c.get("within_tolerance") else "否",
                ])
            writer.writerow([])

        # 捕获的指标
        if actual_results:
            writer.writerow(["# 捕获的指标"])
            writer.writerow(["指标名", "值", "Epoch", "Step"])
            for r in actual_results:
                writer.writerow([
                    r.get("metric_name", ""),
                    r.get("metric_value", ""),
                    r.get("epoch", ""),
                    r.get("step", ""),
                ])

    db.update_check(check_id, report_path=str(path))
    return path


def _generate_md(
    check_id: int,
    record: dict,
    comparisons: list[dict],
    actual_results: list[dict],
    output_dir: Path,
) -> Path:
    """生成 Markdown 报告（方便嵌入 GitHub Issues/PR）"""
    grade = record.get("grade", "-") or "-"
    score = record.get("overall_score", 0) or 0
    repo_name = record.get("repo_name", "") or record.get("repo_url", "")

    grade_emoji = {
        "A": "🟢", "B": "🔵", "C": "🟡", "D": "🟠", "F": "🔴",
    }
    emoji = grade_emoji.get(grade, "⚪")

    lines: list[str] = []
    lines.append(f"# {emoji} ReproChecker 报告 #{check_id}")
    lines.append("")
    lines.append(f"**仓库:** {repo_name}  ")
    lines.append(f"**等级:** {grade} ({score:.0f}/100)  ")
    lines.append(f"**Commit:** {record.get('commit_hash', 'N/A')[:8]}  ")
    lines.append(f"**框架:** {record.get('framework', 'N/A')}  ")
    lines.append(f"**环境:** {record.get('env_method', 'N/A')}  ")
    if record.get("duration_sec"):
        mins, secs = divmod(int(record["duration_sec"]), 60)
        lines.append(f"**耗时:** {mins}m {secs}s  ")
    lines.append("")

    # 评分明细
    lines.append("## 评分明细")
    lines.append("")
    lines.append("| 维度 | 分数 | 权重 |")
    lines.append("|------|------|------|")
    lines.append(f"| 指标复现 | {record.get('metric_score', 0):.0f} | 50% |")
    lines.append(f"| 环境复现 | {record.get('env_score', 0):.0f} | 20% |")
    lines.append(f"| 代码质量 | {record.get('code_score', 0):.0f} | 30% |")
    lines.append("")

    # 指标对比
    if comparisons:
        lines.append("## 指标对比")
        lines.append("")
        lines.append("| 指标 | 论文值 | 实际值 | 相对误差 | 状态 |")
        lines.append("|------|--------|--------|----------|------|")
        for c in comparisons:
            status = "✅" if c.get("within_tolerance") else "❌"
            paper = f"{c['paper_value']:.2f}" if c.get("paper_value") is not None else "-"
            actual = f"{c['actual_value']:.2f}" if c.get("actual_value") is not None else "-"
            error = f"{c.get('relative_error', 0):.1f}%" if c.get("relative_error") is not None else "-"
            lines.append(f"| {c['metric_name']} | {paper} | {actual} | {error} | {status} |")
        lines.append("")

    # 代码质量
    lines.append("## 代码质量")
    lines.append("")
    lines.append(f"- {'✅' if record.get('has_requirements') else '❌'} requirements.txt")
    lines.append(f"- {'✅' if record.get('has_dockerfile') else '❌'} Dockerfile")
    lines.append(f"- {'✅' if record.get('has_seed') else '❌'} 随机种子设置")
    lines.append("")

    # 捕获的指标
    if actual_results:
        lines.append("## 捕获的指标")
        lines.append("")
        lines.append("| 指标 | 值 | Epoch | Step |")
        lines.append("|------|-----|-------|------|")
        for r in actual_results:
            epoch = r.get("epoch", "-") or "-"
            step = r.get("step", "-") or "-"
            val = r.get('metric_value')
            val_s = f"{val:.4f}" if val is not None else "-"
            lines.append(
                f"| {r['metric_name']} | {val_s} | {epoch} | {step} |"
            )
        lines.append("")

    lines.append("---")
    lines.append("*Generated by ReproChecker v0.1.0*")

    content = "\n".join(lines)
    path = output_dir / f"check_{check_id}.md"
    path.write_text(content, encoding="utf-8")

    db.update_check(check_id, report_path=str(path))
    return path


def _render_html(
    check_id: int,
    record: dict,
    comparisons: list[dict],
    paper_results: list[dict],
    actual_results: list[dict],
    output_dir: Path,
) -> str:
    """渲染 HTML 报告内容（共享逻辑）。"""
    env = Environment(
        loader=FileSystemLoader(str(Path(__file__).parent / "templates")),
        autoescape=True,
    )

    try:
        template = env.get_template("report.html")
    except Exception:
        template = env.from_string(_BUILTIN_TEMPLATE)

    duration_str = ""
    if record.get("duration_sec"):
        mins, secs = divmod(int(record["duration_sec"]), 60)
        duration_str = f"{mins}m {secs}s"

    grade_colors = {
        "A": "#22c55e",
        "B": "#3b82f6",
        "C": "#f59e0b",
        "D": "#f97316",
        "F": "#ef4444",
    }

    chart_b64 = None
    if actual_results:
        chart_path = output_dir / f"check_{check_id}_chart.png"
        chart_file = generate_training_chart(actual_results, chart_path)
        chart_b64 = _chart_to_base64(chart_file)

    return template.render(
        check_id=check_id,
        record=record,
        comparisons=comparisons,
        paper_results=paper_results,
        actual_results=actual_results,
        duration_str=duration_str,
        grade_color=grade_colors.get(record.get("grade", ""), "#6b7280"),
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        chart_b64=chart_b64,
    )


def _generate_html(
    check_id: int,
    record: dict,
    comparisons: list[dict],
    paper_results: list[dict],
    actual_results: list[dict],
    output_dir: Path,
) -> Path:
    """生成 HTML 报告"""
    html = _render_html(
        check_id, record, comparisons, paper_results, actual_results, output_dir,
    )

    path = output_dir / f"check_{check_id}.html"
    path.write_text(html, encoding="utf-8")

    db.update_check(check_id, report_path=str(path))
    return path


def _generate_pdf(
    check_id: int,
    record: dict,
    comparisons: list[dict],
    paper_results: list[dict],
    actual_results: list[dict],
    output_dir: Path,
) -> Path:
    """生成 PDF 报告（先生成 HTML 再转换）

    优先使用 WeasyPrint，其次尝试 pdfkit，都不可用时抛出 ImportError。
    """
    html = _render_html(
        check_id, record, comparisons, paper_results, actual_results, output_dir,
    )

    pdf_path = output_dir / f"check_{check_id}.pdf"

    try:
        from weasyprint import HTML  # type: ignore[import-untyped]

        HTML(string=html).write_pdf(str(pdf_path))
        db.update_check(check_id, report_path=str(pdf_path))
        return pdf_path
    except ImportError:
        pass

    try:
        import pdfkit  # type: ignore[import-untyped]

        pdfkit.from_string(html, str(pdf_path))
        db.update_check(check_id, report_path=str(pdf_path))
        return pdf_path
    except ImportError:
        pass

    raise ImportError(
        "PDF 生成需要额外依赖。请安装 weasyprint:\n"
        "  pip install weasyprint\n"
        "或安装 pdfkit + wkhtmltopdf:\n"
        "  pip install pdfkit"
    )


_BUILTIN_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ReproChecker Report #{{ check_id }}</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f8fafc; color: #1e293b; line-height: 1.6; padding: 2rem; }
  .container { max-width: 900px; margin: 0 auto; }
  .header { text-align: center; margin-bottom: 2rem; }
  .grade { font-size: 4rem; font-weight: 700; color: {{ grade_color }};
           display: inline-block; width: 80px; height: 80px; line-height: 80px;
           border-radius: 50%; border: 4px solid {{ grade_color }}; }
  .score { font-size: 1.5rem; color: #64748b; margin-top: 0.5rem; }
  .section { background: white; border-radius: 12px; padding: 1.5rem;
             margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .section h2 { font-size: 1.1rem; color: #334155; margin-bottom: 1rem;
                padding-bottom: 0.5rem; border-bottom: 2px solid #e2e8f0; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 0.6rem 1rem; text-align: left; border-bottom: 1px solid #f1f5f9; }
  th { background: #f8fafc; font-weight: 600; color: #475569; font-size: 0.85rem; }
  .check { color: #22c55e; } .cross { color: #ef4444; }
  .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
  .info-item { display: flex; justify-content: space-between; }
  .info-label { color: #64748b; }
  .sub-scores { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; text-align: center; }
  .sub-score { padding: 1rem; background: #f8fafc; border-radius: 8px; }
  .sub-score .value { font-size: 1.8rem; font-weight: 700; }
  .sub-score .label { font-size: 0.8rem; color: #64748b; }
  .footer { text-align: center; color: #94a3b8; font-size: 0.8rem; margin-top: 2rem; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div class="grade">{{ record.get('grade', '-') }}</div>
    <div class="score">{{ "%.0f"|format(record.get('overall_score', 0)) }}/100</div>
    <h1 style="margin-top:0.5rem">{{ record.get('repo_name', record.get('repo_url', '')) }}</h1>
    <p style="color:#64748b">检验 #{{ check_id }} | {{ record.get('created_at', '')[:10] }}</p>
  </div>

  <div class="section">
    <h2>评分明细</h2>
    <div class="sub-scores">
      <div class="sub-score">
        <div class="value">{{ "%.0f"|format(record.get('metric_score', 0)) }}</div>
        <div class="label">指标复现 (50%)</div>
      </div>
      <div class="sub-score">
        <div class="value">{{ "%.0f"|format(record.get('env_score', 0)) }}</div>
        <div class="label">环境复现 (20%)</div>
      </div>
      <div class="sub-score">
        <div class="value">{{ "%.0f"|format(record.get('code_score', 0)) }}</div>
        <div class="label">代码质量 (30%)</div>
      </div>
    </div>
  </div>

  <div class="section">
    <h2>基本信息</h2>
    <div class="info-grid">
      <div class="info-item"><span class="info-label">仓库</span><span>{{ record.get('repo_url', '') }}</span></div>
      <div class="info-item"><span class="info-label">Commit</span><span>{{ record.get('commit_hash', 'N/A')[:8] if record.get('commit_hash') else 'N/A' }}</span></div>
      <div class="info-item"><span class="info-label">框架</span><span>{{ record.get('framework', 'N/A') }}</span></div>
      <div class="info-item"><span class="info-label">入口脚本</span><span>{{ record.get('entry_script', 'N/A') }}</span></div>
      <div class="info-item"><span class="info-label">环境方式</span><span>{{ record.get('env_method', 'N/A') }}</span></div>
      <div class="info-item"><span class="info-label">运行耗时</span><span>{{ duration_str }}</span></div>
    </div>
  </div>

  {% if comparisons %}
  <div class="section">
    <h2>指标对比</h2>
    <table>
      <thead><tr><th>指标</th><th>论文值</th><th>实际值</th><th>相对误差</th><th>状态</th></tr></thead>
      <tbody>
      {% for c in comparisons %}
      <tr>
        <td>{{ c.metric_name }}</td>
        <td>{{ "%.2f"|format(c.paper_value) if c.paper_value is not none else '-' }}</td>
        <td>{{ "%.2f"|format(c.actual_value) if c.actual_value is not none else '-' }}</td>
        <td>{{ "%.1f"|format(c.relative_error) }}%</td>
        <td class="{{ 'check' if c.within_tolerance else 'cross' }}">{{ '✓' if c.within_tolerance else '✗' }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}

  {% if chart_b64 %}
  <div class="section">
    <h2>训练曲线</h2>
    <img src="{{ chart_b64 }}" alt="Training Metrics Chart"
         style="width:100%; max-width:800px; display:block; margin:0 auto; border-radius:8px;">
  </div>
  {% endif %}

  <div class="section">
    <h2>代码质量</h2>
    <table>
      <tbody>
        <tr><td>{{ '✓' if record.get('has_requirements') else '✗' }} requirements.txt</td></tr>
        <tr><td>{{ '✓' if record.get('has_dockerfile') else '✗' }} Dockerfile</td></tr>
        <tr><td>{{ '✓' if record.get('has_seed') else '✗' }} 随机种子设置</td></tr>
      </tbody>
    </table>
  </div>

  <div class="footer">
    Generated by ReproChecker v0.1.0 | {{ generated_at }}
  </div>
</div>
</body>
</html>"""
