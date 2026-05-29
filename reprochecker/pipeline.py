"""主流程编排器 — 串联 6 个阶段"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from rich.console import Console

from reprochecker.logging import get_logger
from reprochecker.storage.db import Database

console = Console()
db = Database()
logger = get_logger("pipeline")

# 进度回调类型：(step_index, step_name, message)
ProgressCallback = Callable[[int, str, str], None]


def _default_progress(step: int, name: str, msg: str) -> None:
    console.print(f"[bold cyan][{step}/6] {name}...[/]")
    if msg:
        console.print(f"  {msg}")


def run_check(
    check_id: int,
    url: str,
    pdf_path: Path | None = None,
    cmd: str | None = None,
    env: str = "auto",
    timeout: int = 14400,
    gpu: int = 0,
    seed: int = 42,
    no_cache: bool = False,
    name: str | None = None,
    on_progress: ProgressCallback | None = None,
    dry_run: bool = False,
) -> None:
    """执行完整的可复现性检验流程

    Args:
        check_id: 数据库检验记录 ID
        url: GitHub 仓库 URL
        pdf_path: 论文 PDF 路径（可选）
        cmd: 自定义运行命令
        env: 环境方式 (auto/docker/conda/venv)
        timeout: 最大运行时间（秒）
        gpu: GPU 编号
        seed: 随机种子
        no_cache: 是否重新 clone
        name: 自定义检验名称
        on_progress: 进度回调函数
        dry_run: 试运行模式，仅打印计划不实际执行
    """
    progress = on_progress or _default_progress
    logger.info("开始检验 #%d: %s (dry_run=%s)", check_id, url, dry_run)

    if not dry_run:
        db.update_check(check_id, run_status="running")

    if dry_run:
        _run_dry(check_id, url, pdf_path, cmd, env, timeout, gpu, seed, no_cache, name, progress)
        return

    # ── Step 1: 克隆仓库 ──
    progress(1, "克隆仓库", "")
    from reprochecker.repo.cloner import clone_repo

    try:
        repo_path, commit_hash, repo_name = clone_repo(url, no_cache=no_cache)
    except Exception as e:
        logger.error("克隆失败: %s", e)
        db.update_check(check_id, run_status="failed", notes=f"克隆失败: {e}")
        raise
    db.update_check(check_id, commit_hash=commit_hash, repo_name=repo_name or name)
    logger.info("克隆完成: commit=%s", commit_hash[:8])
    progress(1, "克隆仓库", f"✓ commit: {commit_hash[:8]}")

    # ── Step 2: 分析项目 ──
    progress(2, "分析项目", "")
    from reprochecker.repo.analyzer import analyze_repo

    try:
        analysis = analyze_repo(repo_path)
    except Exception as e:
        logger.error("分析失败: %s", e)
        db.update_check(check_id, run_status="failed", notes=f"分析失败: {e}")
        raise
    db.update_check(
        check_id,
        framework=analysis.get("framework"),
        python_version=analysis.get("python_version"),
        has_dockerfile=analysis.get("has_dockerfile"),
        has_requirements=analysis.get("has_requirements"),
        entry_script=analysis.get("entry_script"),
        has_seed=analysis.get("has_seed"),
    )
    fw = analysis.get("framework", "unknown")
    entry = analysis.get("entry_script", "N/A")
    logger.info("分析完成: framework=%s, entry=%s", fw, entry)
    progress(2, "分析项目", f"✓ {fw}, entry: {entry}")

    # ── Step 3: 搭建环境 ──
    progress(3, "搭建环境", "")
    from reprochecker.repo.env_builder import build_env

    try:
        env_info = build_env(repo_path, method=env, analysis=analysis)
    except Exception as e:
        logger.error("环境搭建失败: %s", e)
        db.update_check(check_id, run_status="failed", notes=f"环境搭建失败: {e}")
        raise
    db.update_check(
        check_id,
        env_method=env_info.get("method"),
        installed_packages=env_info.get("packages_json"),
        env_setup_log=env_info.get("log"),
    )
    method = env_info.get("method", "manual")
    pkg_count = env_info.get("package_count", 0)
    logger.info("环境搭建完成: method=%s, packages=%d", method, pkg_count)
    progress(3, "搭建环境", f"✓ {method}, {pkg_count} packages")

    # ── Step 4: 运行实验 ──
    progress(4, "运行实验", "")
    from reprochecker.runner.executor import run_experiment

    run_cmd = cmd or analysis.get("default_command", "python train.py")
    try:
        result = run_experiment(
            repo_path=repo_path,
            command=run_cmd,
            timeout=timeout,
            gpu=gpu,
            seed=seed,
            has_seed=analysis.get("has_seed", False),
        )
    except Exception as e:
        logger.error("实验运行异常: %s", e)
        db.update_check(check_id, run_status="failed", notes=f"运行异常: {e}")
        raise
    db.update_check(
        check_id,
        run_command=result.get("command"),
        run_status=result.get("status", "failed"),
        exit_code=result.get("exit_code"),
        stdout=result.get("stdout"),
        stderr=result.get("stderr"),
        start_time=result.get("start_time"),
        end_time=result.get("end_time"),
        duration_sec=result.get("duration_sec"),
    )
    status = result.get("status", "failed")
    duration = result.get("duration_sec", 0)
    logger.info("实验完成: status=%s, duration=%.0fs", status, duration)
    progress(4, "运行实验", f"✓ {status}, {duration:.0f}s")

    # ── Step 5: 捕获指标 ──
    progress(5, "捕获指标", "")
    from reprochecker.runner.metric_capture import capture_metrics

    metrics = capture_metrics(result.get("stdout", ""), result.get("stderr", ""))
    for m in metrics:
        db.add_actual_result(
            check_id,
            metric_name=m["name"],
            metric_value=m["value"],
            step=m.get("step"),
            epoch=m.get("epoch"),
        )
    logger.info("捕获 %d 个指标", len(metrics))
    progress(5, "捕获指标", f"✓ 捕获 {len(metrics)} 个指标")

    # ── Step 6: PDF 解析 + 对比 + 评分 ──
    if pdf_path and pdf_path.exists():
        progress(6, "解析论文 + 对比", "")
        from reprochecker.compare.metric_compare import compare_metrics
        from reprochecker.pdf.extractor import extract_from_pdf
        from reprochecker.report.scorer import calculate_score

        try:
            paper_results = extract_from_pdf(pdf_path)
        except Exception as e:
            logger.warning("PDF 解析失败: %s，跳过论文对比", e)
            paper_results = []

        for pr in paper_results:
            db.add_paper_result(check_id, **pr)

        comparisons = compare_metrics(paper_results, metrics)
        for c in comparisons:
            db.add_comparison(check_id, **c)

        score = calculate_score(comparisons, env_info, analysis)
        _save_score(check_id, score)
        logger.info("评分完成: %s (%.0f/100)", score["grade"], score["overall"])
        progress(6, "解析论文 + 对比", f"✓ {score['grade']} ({score['overall']:.0f}/100)")
    else:
        progress(6, "跳过 PDF 解析", "未提供 PDF")
        from reprochecker.report.scorer import calculate_score_no_paper

        score = calculate_score_no_paper(env_info, analysis)
        _save_score(check_id, score)
        logger.info("评分完成(无数论文): %s (%.0f/100)", score["grade"], score["overall"])
        progress(6, "评分", f"✓ {score['grade']} ({score['overall']:.0f}/100)")

    db.update_check(check_id, run_status="success")
    grade = score["grade"]
    total = score["overall"]
    console.print(f"\n[bold green]═══ 检验完成: {grade} ({total:.0f}/100) ═══[/]")
    logger.info("检验 #%d 完成", check_id)


def _run_dry(
    check_id: int,
    url: str,
    pdf_path: Path | None,
    cmd: str | None,
    env: str,
    timeout: int,
    gpu: int,
    seed: int,
    no_cache: bool,
    name: str | None,
    progress: ProgressCallback,
) -> None:
    """试运行模式：打印计划但不实际执行"""
    console.print("[bold yellow]═══ 试运行模式 (dry-run) ═══[/]")

    # Step 1: 克隆仓库
    progress(1, "克隆仓库", "")
    repo_name = name or url.rstrip("/").split("/")[-1].replace(".git", "")
    console.print(f"  [dim]将克隆: {url}[/]")
    console.print(f"  [dim]no_cache={no_cache}[/]")
    import tempfile

    repo_path = Path(tempfile.gettempdir()) / "reprochecker_dry" / repo_name
    progress(1, "克隆仓库", f"(跳过) -> {repo_name}")

    # Step 2: 分析项目
    progress(2, "分析项目", "")
    from reprochecker.repo.analyzer import analyze_repo

    if repo_path.exists():
        analysis = analyze_repo(repo_path)
    else:
        analysis = {
            "framework": "unknown",
            "python_version": "3.10",
            "has_dockerfile": False,
            "has_requirements": False,
            "entry_script": "N/A",
            "has_seed": False,
        }
    fw = analysis.get("framework", "unknown")
    entry = analysis.get("entry_script", "N/A")
    progress(2, "分析项目", f"(模拟) framework={fw}, entry={entry}")

    # Step 3: 搭建环境
    progress(3, "搭建环境", "")
    console.print(f"  [dim]环境方式: {env}[/]")
    progress(3, "搭建环境", f"(跳过) method={env}")

    # Step 4: 运行实验
    progress(4, "运行实验", "")
    run_cmd = cmd or analysis.get("default_command", "python train.py")
    console.print(f"  [dim]将执行: {run_cmd}[/]")
    console.print(f"  [dim]timeout={timeout}s, gpu={gpu}, seed={seed}[/]")
    progress(4, "运行实验", f"(跳过) cmd={run_cmd}")

    # Step 5: 捕获指标
    progress(5, "捕获指标", "")
    progress(5, "捕获指标", "(跳过) 无实际输出")

    # Step 6: 评分
    progress(6, "评分", "")
    progress(6, "评分", "(占位) 0/100")

    console.print("\n[bold yellow]═══ 试运行完成（无实际操作） ═══[/]")


def _save_score(check_id: int, score: dict, dry_run: bool = False) -> None:
    """保存评分到数据库（dry_run 时跳过）"""
    if dry_run:
        return
    db.update_check(
        check_id,
        overall_score=score["overall"],
        grade=score["grade"],
        metric_score=score.get("metric_score"),
        env_score=score["env_score"],
        code_score=score["code_score"],
    )
