"""SQLite 存储层"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from reprochecker.config import get_config

# 列名白名单 — 防止 SQL 注入
_CHECKS_COLS = frozenset({
    "repo_url", "pdf_path", "repo_name", "commit_hash", "framework",
    "python_version", "has_dockerfile", "has_requirements", "entry_script",
    "has_seed", "env_method", "env_setup_log", "installed_packages",
    "run_command", "run_status", "exit_code", "stdout", "stderr",
    "start_time", "end_time", "duration_sec", "peak_gpu_mem_mb",
    "peak_cpu_percent", "peak_ram_mb", "model_params", "model_size_mb",
    "inference_ms", "overall_score", "grade", "metric_score", "env_score",
    "code_score", "created_at", "notes", "report_path",
})
_PAPER_RESULTS_COLS = frozenset({
    "check_id", "table_caption", "method_name", "metric_name",
    "metric_value", "is_best",
})
_ACTUAL_RESULTS_COLS = frozenset({
    "check_id", "metric_name", "metric_value", "step", "epoch", "timestamp",
})
_COMPARISONS_COLS = frozenset({
    "check_id", "metric_name", "paper_value", "actual_value",
    "absolute_error", "relative_error", "within_tolerance", "tolerance_band",
})
_CURVES_COLS = frozenset({
    "check_id", "metric_name", "step", "value", "epoch", "timestamp",
})


def _validate_columns(names: Iterable[str], allowed: frozenset[str]) -> None:
    """校验列名是否在白名单内，防止 SQL 注入"""
    bad = set(names) - allowed
    if bad:
        raise ValueError(f"非法列名: {bad}")


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS checks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_url        TEXT NOT NULL,
    pdf_path        TEXT,
    repo_name       TEXT,
    commit_hash     TEXT,
    framework       TEXT,
    python_version  TEXT,
    has_dockerfile  BOOLEAN,
    has_requirements BOOLEAN,
    entry_script    TEXT,
    has_seed        BOOLEAN,
    env_method      TEXT,
    env_setup_log   TEXT,
    installed_packages TEXT,
    run_command     TEXT,
    run_status      TEXT NOT NULL DEFAULT 'pending',
    exit_code       INTEGER,
    stdout          TEXT,
    stderr          TEXT,
    start_time      TIMESTAMP,
    end_time        TIMESTAMP,
    duration_sec    REAL,
    peak_gpu_mem_mb REAL,
    peak_cpu_percent REAL,
    peak_ram_mb     REAL,
    model_params    INTEGER,
    model_size_mb   REAL,
    inference_ms    REAL,
    overall_score   REAL,
    grade           TEXT,
    metric_score    REAL,
    env_score       REAL,
    code_score      REAL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes           TEXT,
    report_path     TEXT
);

CREATE TABLE IF NOT EXISTS paper_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id        INTEGER NOT NULL REFERENCES checks(id) ON DELETE CASCADE,
    table_caption   TEXT,
    method_name     TEXT,
    metric_name     TEXT NOT NULL,
    metric_value    REAL NOT NULL,
    is_best         BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS actual_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id        INTEGER NOT NULL REFERENCES checks(id) ON DELETE CASCADE,
    metric_name     TEXT NOT NULL,
    metric_value    REAL NOT NULL,
    step            INTEGER,
    epoch           INTEGER,
    timestamp       TIMESTAMP
);

CREATE TABLE IF NOT EXISTS comparisons (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id        INTEGER NOT NULL REFERENCES checks(id) ON DELETE CASCADE,
    metric_name     TEXT NOT NULL,
    paper_value     REAL,
    actual_value    REAL,
    absolute_error  REAL,
    relative_error  REAL,
    within_tolerance BOOLEAN,
    tolerance_band  TEXT
);

CREATE TABLE IF NOT EXISTS training_curves (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    check_id        INTEGER NOT NULL REFERENCES checks(id) ON DELETE CASCADE,
    metric_name     TEXT NOT NULL,
    step            INTEGER NOT NULL,
    value           REAL NOT NULL,
    epoch           INTEGER,
    timestamp       TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_checks_repo ON checks(repo_url);
CREATE INDEX IF NOT EXISTS idx_checks_grade ON checks(grade);
CREATE INDEX IF NOT EXISTS idx_checks_created ON checks(created_at);
CREATE INDEX IF NOT EXISTS idx_paper_results_check ON paper_results(check_id);
CREATE INDEX IF NOT EXISTS idx_actual_results_check ON actual_results(check_id);
CREATE INDEX IF NOT EXISTS idx_comparisons_check ON comparisons(check_id);
CREATE INDEX IF NOT EXISTS idx_curves_check ON training_curves(check_id);
CREATE INDEX IF NOT EXISTS idx_curves_metric ON training_curves(check_id, metric_name);
"""


class Database:
    """SQLite 数据库管理"""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or get_config().db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ---- checks CRUD ----

    def create_check(self, repo_url: str, pdf_path: str | None = None, **kwargs: Any) -> int:
        """创建新的检验记录，返回 ID"""
        fields = {"repo_url": repo_url, "pdf_path": pdf_path, **kwargs}
        fields = {k: v for k, v in fields.items() if v is not None}
        _validate_columns(fields.keys(), _CHECKS_COLS)
        placeholders = ", ".join(f":{k}" for k in fields)
        columns = ", ".join(fields.keys())
        with self._connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO checks ({columns}) VALUES ({placeholders})", fields
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def update_check(self, check_id: int, **kwargs: Any) -> None:
        """更新检验记录字段"""
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        if not kwargs:
            return
        _validate_columns(kwargs.keys(), _CHECKS_COLS)
        set_clause = ", ".join(f"{k} = :{k}" for k in kwargs)
        kwargs["check_id"] = check_id
        with self._connect() as conn:
            conn.execute(
                f"UPDATE checks SET {set_clause} WHERE id = :check_id", kwargs
            )

    def get_check(self, check_id: int) -> dict[str, Any] | None:
        """获取单条检验记录"""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM checks WHERE id = ?", (check_id,)).fetchone()
            return dict(row) if row else None

    def list_checks(
        self,
        status: str | None = None,
        repo: str | None = None,
        grade: str | None = None,
        sort: str = "created_at",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """列出检验记录"""
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("run_status = ?")
            params.append(status)
        if repo:
            conditions.append("repo_name LIKE ?")
            params.append(f"%{repo}%")
        if grade:
            conditions.append("grade = ?")
            params.append(grade)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        allowed_sorts = ("created_at", "overall_score", "grade")
        if sort not in allowed_sorts:
            raise ValueError(f"无效排序字段: {sort!r}，允许: {allowed_sorts}")
        order = sort
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM checks{where} ORDER BY {order} DESC LIMIT ?",
                params + [limit],
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_check(self, check_id: int) -> None:
        """删除检验记录（级联删除关联数据）"""
        with self._connect() as conn:
            conn.execute("DELETE FROM checks WHERE id = ?", (check_id,))

    # ---- paper_results ----

    def add_paper_result(self, check_id: int, **kwargs: Any) -> int:
        kwargs["check_id"] = check_id
        _validate_columns(kwargs.keys(), _PAPER_RESULTS_COLS)
        columns = ", ".join(kwargs.keys())
        placeholders = ", ".join(f":{k}" for k in kwargs)
        with self._connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO paper_results ({columns}) VALUES ({placeholders})", kwargs
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def get_paper_results(self, check_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM paper_results WHERE check_id = ?", (check_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- actual_results ----

    def add_actual_result(self, check_id: int, **kwargs: Any) -> int:
        kwargs["check_id"] = check_id
        _validate_columns(kwargs.keys(), _ACTUAL_RESULTS_COLS)
        columns = ", ".join(kwargs.keys())
        placeholders = ", ".join(f":{k}" for k in kwargs)
        with self._connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO actual_results ({columns}) VALUES ({placeholders})", kwargs
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def get_actual_results(self, check_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM actual_results WHERE check_id = ?", (check_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- comparisons ----

    def add_comparison(self, check_id: int, **kwargs: Any) -> int:
        kwargs["check_id"] = check_id
        _validate_columns(kwargs.keys(), _COMPARISONS_COLS)
        columns = ", ".join(kwargs.keys())
        placeholders = ", ".join(f":{k}" for k in kwargs)
        with self._connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO comparisons ({columns}) VALUES ({placeholders})", kwargs
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def get_comparisons(self, check_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM comparisons WHERE check_id = ?", (check_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- training_curves ----

    def add_curve_point(self, check_id: int, metric_name: str, step: int, value: float,
                        epoch: int | None = None) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO training_curves (check_id, metric_name, step, value, epoch) "
                "VALUES (?, ?, ?, ?, ?)",
                (check_id, metric_name, step, value, epoch),
            )
            return cursor.lastrowid  # type: ignore[return-value]

    def get_curve(self, check_id: int, metric_name: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM training_curves "
                "WHERE check_id = ? AND metric_name = ? ORDER BY step",
                (check_id, metric_name),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---- 统计 ----

    def get_stats(self) -> dict[str, Any]:
        """获取全局统计信息"""
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM checks").fetchone()[0]
            success = conn.execute(
                "SELECT COUNT(*) FROM checks WHERE run_status = 'success'"
            ).fetchone()[0]
            grades = conn.execute(
                "SELECT grade, COUNT(*) as cnt FROM checks WHERE grade IS NOT NULL GROUP BY grade"
            ).fetchall()
            avg_score = conn.execute(
                "SELECT AVG(overall_score) FROM checks WHERE overall_score IS NOT NULL"
            ).fetchone()[0]
            avg_duration = conn.execute(
                "SELECT AVG(duration_sec) FROM checks WHERE duration_sec IS NOT NULL"
            ).fetchone()[0]
            top_repos = conn.execute(
                "SELECT repo_name, COUNT(*) as cnt FROM checks "
                "GROUP BY repo_url ORDER BY cnt DESC LIMIT 5"
            ).fetchall()

            return {
                "total": total,
                "success": success,
                "success_rate": success / total if total > 0 else 0,
                "grades": {r["grade"]: r["cnt"] for r in grades},
                "avg_score": round(avg_score, 1) if avg_score else 0,
                "avg_duration_sec": round(avg_duration, 0) if avg_duration else 0,
                "top_repos": [{"name": r["repo_name"], "count": r["cnt"]} for r in top_repos],
            }

    def get_trend(self, repo_url: str, limit: int = 10) -> list[dict[str, Any]]:
        """获取同一仓库的检验趋势（按时间排序）"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, overall_score, grade, run_status, created_at, "
                "metric_score, env_score, code_score, duration_sec "
                "FROM checks WHERE repo_url = ? "
                "ORDER BY created_at ASC, id ASC LIMIT ?",
                (repo_url, limit),
            ).fetchall()
            return [dict(r) for r in rows]
