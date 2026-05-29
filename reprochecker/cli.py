"""ReproChecker CLI 入口"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from reprochecker import __version__
from reprochecker.config import ConfigError, load_config
from reprochecker.storage.db import Database

app = typer.Typer(
    name="repro",
    help="ReproChecker — 学术论文可复现性自动检验工具",
    add_completion=False,
)
cache_app = typer.Typer(
    name="cache",
    help="管理克隆仓库缓存",
    add_completion=False,
)
app.add_typer(cache_app, name="cache")
console = Console()
db = Database()

# 全局配置字典，由 main() 回调填充
_runtime_config: dict[str, Any] = {}


def get_runtime_config() -> dict[str, Any]:
    """获取当前运行时配置"""
    return _runtime_config


def version_callback(value: bool) -> None:
    if value:
        console.print(f"ReproChecker v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool | None = typer.Option(  # noqa: UP007
        None,
        "--version",
        "-v",
        callback=version_callback,
        is_eager=True,
        help="显示版本号",
    ),
    config: Path | None = typer.Option(  # noqa: UP007
        None,
        "--config",
        "-c",
        help="配置文件路径（repro.yaml / repro.json）",
    ),
) -> None:
    """ReproChecker — 学术论文可复现性自动检验工具"""
    global _runtime_config
    try:
        _runtime_config = load_config(config)
    except (ConfigError, FileNotFoundError) as e:
        console.print(f"[bold red]配置错误: {e}[/]")
        raise typer.Exit(code=1)


@app.command()
def check(
    url: str = typer.Argument(help="GitHub 仓库 URL"),
    pdf: Path | None = typer.Option(None, "--pdf", help="论文 PDF 路径"),  # noqa: UP007
    cmd: str | None = typer.Option(None, "--cmd", help="自定义运行命令"),  # noqa: UP007
    env: str | None = typer.Option(None, "--env", help="环境方式: docker/conda/venv/auto"),  # noqa: UP007
    timeout: int | None = typer.Option(None, "--timeout", help="最大运行时间（秒）"),  # noqa: UP007
    gpu: int | None = typer.Option(None, "--gpu", help="GPU 编号"),  # noqa: UP007
    seed: int | None = typer.Option(None, "--seed", help="随机种子"),  # noqa: UP007
    no_cache: bool = typer.Option(False, "--no-cache", help="不使用缓存，重新 clone"),
    name: str | None = typer.Option(None, "--name", help="自定义检验名称"),  # noqa: UP007
    dry_run: bool = typer.Option(False, "--dry-run", help="试运行模式，仅打印计划不实际执行"),
) -> None:
    """执行可复现性检验"""
    from reprochecker.pipeline import run_check

    # 从配置文件获取默认值，CLI 参数优先
    defaults = _runtime_config.get("defaults", {})
    resolved_env = env if env is not None else defaults.get("env", "auto")
    resolved_timeout = timeout if timeout is not None else defaults.get("timeout", 14400)
    resolved_gpu = gpu if gpu is not None else defaults.get("gpu", 0)
    resolved_seed = seed if seed is not None else defaults.get("seed", 42)

    check_id = db.create_check(repo_url=url, pdf_path=str(pdf) if pdf else None)
    console.print(f"[bold green]创建检验记录 #{check_id}[/]")

    try:
        run_check(
            check_id=check_id,
            url=url,
            pdf_path=pdf,
            cmd=cmd,
            env=resolved_env,
            timeout=resolved_timeout,
            gpu=resolved_gpu,
            seed=resolved_seed,
            no_cache=no_cache,
            name=name,
            dry_run=dry_run,
        )
    except Exception as e:
        db.update_check(check_id, run_status="failed", notes=str(e))
        console.print(f"[bold red]检验失败: {e}[/]")
        raise typer.Exit(code=1)


@app.command(name="list")
def list_checks(
    status: str | None = typer.Option(None, "--status", help="按状态筛选"),  # noqa: UP007
    repo: str | None = typer.Option(None, "--repo", help="按仓库筛选"),  # noqa: UP007
    grade: str | None = typer.Option(None, "--grade", help="按等级筛选"),  # noqa: UP007
    sort: str = typer.Option("created_at", "--sort", help="排序字段"),
    limit: int = typer.Option(20, "--limit", help="返回数量"),
) -> None:
    """列出检验记录"""
    records = db.list_checks(status=status, repo=repo, grade=grade, sort=sort, limit=limit)
    if not records:
        console.print("[yellow]暂无检验记录[/]")
        return

    table = Table(title="ReproChecker 检验记录")
    table.add_column("ID", justify="right")
    table.add_column("仓库")
    table.add_column("等级", justify="center")
    table.add_column("评分", justify="right")
    table.add_column("状态")
    table.add_column("日期")

    status_colors = {
        "success": "green",
        "failed": "red",
        "running": "yellow",
        "pending": "dim",
    }

    for r in records:
        color = status_colors.get(r["run_status"], "white")
        table.add_row(
            str(r["id"]),
            r.get("repo_name") or r["repo_url"][:40],
            r.get("grade") or "-",
            f"{r['overall_score']:.0f}" if r.get("overall_score") else "-",
            f"[{color}]{r['run_status']}[/]",
            r.get("created_at", "-")[:10],
        )

    console.print(table)


@app.command()
def show(
    check_id: int = typer.Argument(help="检验 ID"),
) -> None:
    """查看检验详情"""
    record = db.get_check(check_id)
    if not record:
        console.print(f"[red]检验记录 #{check_id} 不存在[/]")
        raise typer.Exit(code=1)

    console.print(f"\n[bold]═══ 检验 #{record['id']}: {record.get('repo_name', 'N/A')} ═══[/]")
    console.print(f"  仓库: {record['repo_url']}")
    console.print(f"  Commit: {record.get('commit_hash', 'N/A')}")
    console.print(f"  框架: {record.get('framework', 'N/A')}")
    console.print(f"  入口: {record.get('entry_script', 'N/A')}")
    console.print(f"  环境: {record.get('env_method', 'N/A')}")
    if record.get("duration_sec"):
        mins, secs = divmod(int(record["duration_sec"]), 60)
        console.print(f"  耗时: {mins}m {secs}s")
    if record.get("overall_score") is not None:
        grade = record.get("grade", "-")
        score = record["overall_score"]
        console.print(f"\n  [bold]评分: {grade} ({score:.0f}/100)[/]")
        console.print(f"  指标复现: {record.get('metric_score', '-')}")
        console.print(f"  环境复现: {record.get('env_score', '-')}")
        console.print(f"  代码质量: {record.get('code_score', '-')}")

    comparisons = db.get_comparisons(check_id)
    if comparisons:
        console.print("\n  [bold]── 指标对比 ──[/]")
        ct = Table(show_header=True, box=None)
        ct.add_column("指标")
        ct.add_column("论文值", justify="right")
        ct.add_column("实际值", justify="right")
        ct.add_column("误差", justify="right")
        ct.add_column("状态")
        for c in comparisons:
            status_str = "✓" if c.get("within_tolerance") else "✗"
            ct.add_row(
                c["metric_name"],
                f"{c['paper_value']}" if c.get("paper_value") is not None else "-",
                f"{c['actual_value']}" if c.get("actual_value") is not None else "-",
                f"{c.get('relative_error', 0):.1f}%"
                if c.get("relative_error") is not None
                else "-",
                status_str,
            )
        console.print(ct)
    console.print()


@app.command()
def report(
    check_id: int = typer.Argument(help="检验 ID"),
    format: str = typer.Option("html", "--format", "-f", help="输出格式: html/pdf/json/csv/md"),
    output: Path | None = typer.Option(None, "--output", "-o", help="输出目录"),  # noqa: UP007
) -> None:
    """生成/导出报告"""
    from reprochecker.report.generator import generate_report

    record = db.get_check(check_id)
    if not record:
        console.print(f"[red]检验记录 #{check_id} 不存在[/]")
        raise typer.Exit(code=1)

    path = generate_report(check_id, format=format, output_dir=output)
    console.print(f"[green]报告已保存: {path}[/]")


@app.command()
def badge(
    check_id: int = typer.Argument(help="检验 ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="输出路径"),  # noqa: UP007
) -> None:
    """生成可复现性 SVG 徽章"""
    from reprochecker.report.badge import generate_badge

    record = db.get_check(check_id)
    if not record:
        console.print(f"[red]检验记录 #{check_id} 不存在[/]")
        raise typer.Exit(code=1)

    path = generate_badge(check_id, output_path=output)
    console.print(f"[green]徽章已保存: {path}[/]")


@app.command()
def latex(
    check_id: int = typer.Argument(help="检验 ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="输出目录"),  # noqa: UP007
) -> None:
    """导出 LaTeX 表格（可嵌入论文）"""
    from reprochecker.report.latex import generate_latex

    record = db.get_check(check_id)
    if not record:
        console.print(f"[red]检验记录 #{check_id} 不存在[/]")
        raise typer.Exit(code=1)

    path = generate_latex(check_id, output_dir=output)
    console.print(f"[green]LaTeX 表格已保存: {path}[/]")


@app.command()
def chart(
    check_id: int = typer.Argument(help="检验 ID"),
    output: Path | None = typer.Option(None, "--output", "-o", help="输出路径"),  # noqa: UP007
) -> None:
    """生成论文值 vs 实际值的对比图"""
    from reprochecker.report.chart import generate_comparison_chart

    record = db.get_check(check_id)
    if not record:
        console.print(f"[red]检验记录 #{check_id} 不存在[/]")
        raise typer.Exit(code=1)

    path = generate_comparison_chart(check_id, output_path=output)
    if path:
        console.print(f"[green]对比图已保存: {path}[/]")
    else:
        console.print("[yellow]matplotlib 未安装，无法生成图表[/]")


@app.command()
def batch(
    file: Path = typer.Argument(help="批检验配置文件路径（YAML/JSON）"),
    env: str | None = typer.Option(None, "--env", help="环境方式: docker/conda/venv/auto"),  # noqa: UP007
    timeout: int | None = typer.Option(None, "--timeout", help="最大运行时间（秒）"),  # noqa: UP007
    gpu: int | None = typer.Option(None, "--gpu", help="GPU 编号"),  # noqa: UP007
    seed: int | None = typer.Option(None, "--seed", help="随机种子"),  # noqa: UP007
    no_cache: bool = typer.Option(False, "--no-cache", help="不使用缓存，重新 clone"),
    dry_run: bool = typer.Option(False, "--dry-run", help="试运行模式，仅打印计划不实际执行"),
) -> None:
    """批量执行可复现性检验"""
    import json as _json

    import yaml

    from reprochecker.pipeline import run_check

    # 从配置文件获取默认值，CLI 参数优先
    defaults = _runtime_config.get("defaults", {})
    resolved_env = env if env is not None else defaults.get("env", "auto")
    resolved_timeout = timeout if timeout is not None else defaults.get("timeout", 14400)
    resolved_gpu = gpu if gpu is not None else defaults.get("gpu", 0)
    resolved_seed = seed if seed is not None else defaults.get("seed", 42)

    if not file.exists():
        console.print(f"[bold red]配置文件不存在: {file}[/]")
        raise typer.Exit(code=1)

    text = file.read_text(encoding="utf-8")
    suffix = file.suffix.lower()
    if suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    else:
        data = _json.loads(text)

    if not isinstance(data, dict) or "repos" not in data:
        console.print("[bold red]配置文件格式错误：需要包含 'repos' 列表[/]")
        raise typer.Exit(code=1)

    repos = data["repos"]
    if not isinstance(repos, list) or len(repos) == 0:
        console.print("[bold red]'repos' 列表为空[/]")
        raise typer.Exit(code=1)

    from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

    total = len(repos)
    results: list[dict[str, object]] = []

    with Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("批量检验", total=total)

        for idx, repo_entry in enumerate(repos, 1):
            url = repo_entry.get("url")
            if not url:
                progress.update(task, description=f"[red]跳过 #{idx}[/]")
                results.append({"url": "(missing)", "status": "skipped", "grade": "-"})
                progress.advance(task)
                continue

            pdf_path = Path(repo_entry["pdf"]) if repo_entry.get("pdf") else None
            cmd = repo_entry.get("cmd")
            check_id = db.create_check(
                repo_url=url,
                pdf_path=str(pdf_path) if pdf_path else None,
            )

            short_url = url.split("/")[-1] if "/" in url else url[:30]
            progress.update(task, description=f"[cyan]{short_url}[/]")

            try:
                run_check(
                    check_id=check_id,
                    url=url,
                    pdf_path=pdf_path,
                    cmd=cmd,
                    env=resolved_env,
                    timeout=resolved_timeout,
                    gpu=resolved_gpu,
                    seed=resolved_seed,
                    no_cache=no_cache,
                    dry_run=dry_run,
                )
                record = db.get_check(check_id)
                results.append(
                    {
                        "url": url,
                        "status": "success",
                        "grade": record.get("grade", "-") if record else "-",
                        "score": record.get("overall_score") if record else None,
                    }
                )
            except Exception as e:
                db.update_check(check_id, run_status="failed", notes=str(e))
                results.append({"url": url, "status": "failed", "grade": "-"})
                console.print(f"[bold red]  检验失败: {e}[/]")

            progress.advance(task)

    # 汇总表格
    console.print("\n[bold]═══ 批量检验汇总 ═══[/]")
    table = Table(title=f"批检验结果 ({total} 个仓库)")
    table.add_column("#", justify="right")
    table.add_column("仓库")
    table.add_column("状态")
    table.add_column("等级", justify="center")
    table.add_column("评分", justify="right")

    for i, r in enumerate(results, 1):
        status = r["status"]
        color = "green" if status == "success" else "red" if status == "failed" else "yellow"
        score_str = f"{r['score']:.0f}" if r.get("score") is not None else "-"
        table.add_row(
            str(i),
            str(r["url"])[:50],
            f"[{color}]{status}[/]",
            str(r.get("grade", "-")),
            score_str,
        )

    console.print(table)


@app.command()
def compare(
    id1: int = typer.Argument(help="第一次检验 ID"),
    id2: int = typer.Argument(help="第二次检验 ID"),
) -> None:
    """对比两次检验结果"""
    r1 = db.get_check(id1)
    r2 = db.get_check(id2)
    if not r1:
        console.print(f"[red]检验记录 #{id1} 不存在[/]")
        raise typer.Exit(code=1)
    if not r2:
        console.print(f"[red]检验记录 #{id2} 不存在[/]")
        raise typer.Exit(code=1)

    console.print(f"\n[bold]═══ 对比: #{id1} vs #{id2} ═══[/]")
    name1 = r1.get("repo_name", "N/A")
    g1 = r1.get("grade", "-")
    s1 = r1.get("overall_score", "-")
    name2 = r2.get("repo_name", "N/A")
    g2 = r2.get("grade", "-")
    s2 = r2.get("overall_score", "-")
    console.print(f"  #{id1}: {name1} — {g1} ({s1})")
    console.print(f"  #{id2}: {name2} — {g2} ({s2})")

    c1 = db.get_comparisons(id1)
    c2 = db.get_comparisons(id2)
    if c1 and c2:
        metrics2 = {c["metric_name"]: c for c in c2}
        console.print("\n  [bold]── 指标变化 ──[/]")
        ct = Table(show_header=True, box=None)
        ct.add_column("指标")
        ct.add_column(f"#{id1}", justify="right")
        ct.add_column(f"#{id2}", justify="right")
        ct.add_column("变化", justify="right")
        for c in c1:
            m = c["metric_name"]
            v1 = c.get("actual_value")
            v2_data = metrics2.get(m)
            v2 = v2_data.get("actual_value") if v2_data else None
            if v1 is not None and v2 is not None:
                diff = v2 - v1
                arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
                ct.add_row(m, f"{v1:.2f}", f"{v2:.2f}", f"{diff:+.2f} {arrow}")
            else:
                ct.add_row(m, str(v1) if v1 else "-", str(v2) if v2 else "-", "-")
        console.print(ct)
    console.print()


@app.command()
def stats() -> None:
    """统计概览"""
    s = db.get_stats()
    console.print("\n[bold]═══ ReproChecker 统计 ═══[/]")
    console.print(f"  总检验次数: {s['total']}")
    console.print(f"  成功率: {s['success_rate']:.0%} ({s['success']}/{s['total']})")
    if s["grades"]:
        console.print("\n  等级分布:")
        for g in ("A", "B", "C", "D", "F"):
            cnt = s["grades"].get(g, 0)
            bar = "█" * (cnt * 20 // max(s["grades"].values(), default=1))
            console.print(f"    {g}: {cnt:3d}  {bar}")
    console.print(f"\n  平均评分: {s['avg_score']}")
    if s["avg_duration_sec"]:
        mins, secs = divmod(int(s["avg_duration_sec"]), 60)
        console.print(f"  平均耗时: {mins}m {secs}s")
    if s["top_repos"]:
        console.print("\n  最常检验的仓库:")
        for i, r in enumerate(s["top_repos"], 1):
            console.print(f"    {i}. {r['name']} ({r['count']} 次)")
    console.print()


@app.command()
def trend(
    repo: str = typer.Argument(help="仓库 URL 或 owner/repo 格式"),
    limit: int = typer.Option(10, "--limit", "-n", help="显示条数"),
) -> None:
    """查看仓库的检验趋势"""
    records = db.get_trend(repo, limit=limit)
    if not records:
        # 尝试模糊匹配
        all_checks = db.list_checks(repo=repo, limit=1)
        if all_checks:
            repo_url = all_checks[0]["repo_url"]
            records = db.get_trend(repo_url, limit=limit)
        else:
            console.print(f"[yellow]未找到仓库 '{repo}' 的检验记录[/]")
            return

    console.print(f"\n[bold]═══ 趋势: {records[0].get('repo_url', repo)} ═══[/]")

    table = Table(title=f"最近 {len(records)} 次检验趋势")
    table.add_column("#", justify="right")
    table.add_column("评分", justify="right")
    table.add_column("等级", justify="center")
    table.add_column("指标", justify="right")
    table.add_column("环境", justify="right")
    table.add_column("代码", justify="right")
    table.add_column("状态")
    table.add_column("日期")

    status_colors = {
        "success": "green",
        "failed": "red",
        "running": "yellow",
        "pending": "dim",
    }

    for r in records:
        color = status_colors.get(r.get("run_status", ""), "white")
        table.add_row(
            str(r["id"]),
            f"{r['overall_score']:.0f}" if r.get("overall_score") else "-",
            r.get("grade") or "-",
            f"{r['metric_score']:.0f}" if r.get("metric_score") else "-",
            f"{r['env_score']:.0f}" if r.get("env_score") else "-",
            f"{r['code_score']:.0f}" if r.get("code_score") else "-",
            f"[{color}]{r.get('run_status', '?')}[/]",
            r.get("created_at", "-")[:10],
        )

    console.print(table)

    # 趋势分析
    if len(records) >= 2:
        scores = [r["overall_score"] for r in records if r.get("overall_score")]
        if len(scores) >= 2:
            diff = scores[-1] - scores[0]
            arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
            console.print(
                f"\n  趋势: {arrow} {diff:+.1f} 分（从 {scores[0]:.0f} 到 {scores[-1]:.0f}）"
            )
    console.print()


@app.command()
def delete(
    check_id: int = typer.Argument(help="检验 ID"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
) -> None:
    """删除检验记录"""
    record = db.get_check(check_id)
    if not record:
        console.print(f"[red]检验记录 #{check_id} 不存在[/]")
        raise typer.Exit(code=1)

    if not force:
        confirm = typer.confirm(f"确认删除检验 #{check_id} ({record.get('repo_name', '')})？")
        if not confirm:
            raise typer.Abort()

    db.delete_check(check_id)
    console.print(f"[green]已删除检验记录 #{check_id}[/]")


@app.command()
def export(
    output: Path = typer.Argument(help="导出文件路径（.jsonl）"),
    status: str | None = typer.Option(None, "--status", help="按状态筛选"),  # noqa: UP007
    limit: int = typer.Option(1000, "--limit", help="最大导出条数"),
) -> None:
    """导出检验数据为 JSONL 格式（便于迁移和备份）"""
    import json as _json

    records = db.list_checks(status=status, limit=limit, sort="created_at")
    if not records:
        console.print("[yellow]暂无检验记录可导出[/]")
        return

    count = 0
    with output.open("w", encoding="utf-8") as f:
        for record in records:
            cid = record["id"]
            entry = {
                "check": record,
                "paper_results": db.get_paper_results(cid),
                "actual_results": db.get_actual_results(cid),
                "comparisons": db.get_comparisons(cid),
            }
            f.write(_json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            count += 1

    console.print(f"[green]已导出 {count} 条记录到 {output}[/]")


@app.command()
def import_data(
    file: Path = typer.Argument(help="JSONL 导入文件路径"),
    skip_existing: bool = typer.Option(
        True, "--skip-existing/--overwrite", help="跳过已存在的记录"
    ),
) -> None:
    """从 JSONL 文件导入检验数据"""
    import json as _json

    if not file.exists():
        console.print(f"[red]文件不存在: {file}[/]")
        raise typer.Exit(code=1)

    imported = 0
    skipped = 0
    for line_num, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entry = _json.loads(line)
        except _json.JSONDecodeError as e:
            console.print(f"[yellow]第 {line_num} 行 JSON 解析失败: {e}，跳过[/]")
            continue

        check_data = entry.get("check", {})
        old_id = check_data.get("id")

        if skip_existing and old_id:
            existing = db.get_check(old_id)
            if existing:
                skipped += 1
                continue

        # 创建新记录（不保留旧 ID，避免冲突）
        check_data.pop("id", None)
        new_id = db.create_check(
            **{k: v for k, v in check_data.items() if k not in ("id",) and v is not None}
        )

        # 导入关联数据
        for pr in entry.get("paper_results", []):
            pr.pop("id", None)
            pr.pop("check_id", None)
            db.add_paper_result(new_id, **{k: v for k, v in pr.items() if v is not None})

        for ar in entry.get("actual_results", []):
            ar.pop("id", None)
            ar.pop("check_id", None)
            db.add_actual_result(new_id, **{k: v for k, v in ar.items() if v is not None})

        for comp in entry.get("comparisons", []):
            comp.pop("id", None)
            comp.pop("check_id", None)
            db.add_comparison(new_id, **{k: v for k, v in comp.items() if v is not None})

        imported += 1

    console.print(f"[green]导入完成: {imported} 条导入, {skipped} 条跳过[/]")


@app.command(name="config")
def config_show() -> None:
    """显示当前生效的配置"""
    import json as _json

    from rich.panel import Panel
    from rich.syntax import Syntax

    cfg_json = _json.dumps(_runtime_config, indent=2, ensure_ascii=False)
    panel = Panel(
        Syntax(cfg_json, "json", theme="monokai"),
        title="ReproChecker 配置",
        border_style="cyan",
    )
    console.print(panel)


def _format_size(size_bytes: int) -> str:
    """将字节数格式化为可读的文件大小字符串。"""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} TB"


def _dir_size(path: Path) -> int:
    """递归计算目录总大小（字节）。"""
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            total += item.stat().st_size
    return total


@cache_app.command(name="list")
def cache_list() -> None:
    """列出所有已缓存的仓库及其大小"""
    from reprochecker.repo.cloner import list_cached_repos

    repos = list_cached_repos()
    if not repos:
        console.print("[yellow]暂无缓存仓库[/]")
        return

    table = Table(title="缓存仓库列表")
    table.add_column("仓库名")
    table.add_column("Commit", style="dim")
    table.add_column("大小", justify="right")
    table.add_column("路径", style="dim")

    total_size = 0
    for entry in repos:
        repo_path = Path(entry["path"])
        size = _dir_size(repo_path) if repo_path.exists() else 0
        total_size += size
        table.add_row(
            entry["name"],
            entry["commit_hash"][:12] if entry["commit_hash"] != "unknown" else "unknown",
            _format_size(size),
            entry["path"],
        )

    console.print(table)
    console.print(f"\n[bold]共 {len(repos)} 个缓存仓库，总大小: {_format_size(total_size)}[/]")


@cache_app.command(name="clear")
def cache_clear(
    repo_name: str | None = typer.Argument(  # noqa: UP007
        None,
        help="指定仓库名清除（格式: owner/repo），为空则清除全部",
    ),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
) -> None:
    """清除缓存仓库"""
    from reprochecker.repo.cloner import clear_cache, list_cached_repos

    if repo_name:
        # 清除指定仓库
        safe_name = repo_name.replace("/", "__")
        cache_dir = Path.home() / ".reprochecker" / "cache" / safe_name
        if not cache_dir.exists():
            console.print(f"[yellow]未找到仓库 '{repo_name}' 的缓存[/]")
            raise typer.Exit(code=1)

        size = _dir_size(cache_dir) if cache_dir.exists() else 0
        if not force:
            confirm = typer.confirm(f"确认清除仓库 '{repo_name}' 的缓存（{_format_size(size)}）？")
            if not confirm:
                raise typer.Abort()

        count = clear_cache(repo_name)
        console.print(f"[green]已清除仓库 '{repo_name}' 的缓存[/]")
    else:
        # 清除全部
        repos = list_cached_repos()
        if not repos:
            console.print("[yellow]暂无缓存仓库[/]")
            return

        total_size = 0
        for entry in repos:
            repo_path = Path(entry["path"])
            if repo_path.exists():
                total_size += _dir_size(repo_path)

        if not force:
            console.print(f"[bold]将清除 {len(repos)} 个缓存仓库（{_format_size(total_size)}）[/]")
            confirm = typer.confirm("确认清除全部缓存？")
            if not confirm:
                raise typer.Abort()

        count = clear_cache()
        console.print(f"[green]已清除 {count} 个缓存仓库[/]")
