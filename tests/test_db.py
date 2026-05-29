"""数据库层测试"""

from pathlib import Path

import pytest

from reprochecker.storage.db import Database


@pytest.fixture
def db(tmp_path: Path) -> Database:
    return Database(db_path=tmp_path / "test.db")


def test_create_and_get_check(db: Database) -> None:
    check_id = db.create_check(repo_url="https://github.com/user/repo")
    assert check_id > 0
    record = db.get_check(check_id)
    assert record is not None
    assert record["repo_url"] == "https://github.com/user/repo"
    assert record["run_status"] == "pending"


def test_update_check(db: Database) -> None:
    check_id = db.create_check(repo_url="https://github.com/user/repo")
    db.update_check(check_id, run_status="success", overall_score=85.0, grade="B")
    record = db.get_check(check_id)
    assert record["run_status"] == "success"
    assert record["overall_score"] == 85.0
    assert record["grade"] == "B"


def test_list_checks_with_filters(db: Database) -> None:
    db.create_check(repo_url="https://github.com/a/repo")
    db.create_check(repo_url="https://github.com/b/repo")
    cid = db.create_check(repo_url="https://github.com/c/repo")
    db.update_check(cid, run_status="success", grade="A")

    all_checks = db.list_checks()
    assert len(all_checks) == 3

    success_checks = db.list_checks(status="success")
    assert len(success_checks) == 1

    grade_a = db.list_checks(grade="A")
    assert len(grade_a) == 1


def test_delete_check_cascades(db: Database) -> None:
    check_id = db.create_check(repo_url="https://github.com/user/repo")
    db.add_paper_result(check_id, metric_name="accuracy", metric_value=92.1)
    db.add_actual_result(check_id, metric_name="accuracy", metric_value=93.3)
    db.add_comparison(check_id, metric_name="accuracy", paper_value=92.1, actual_value=93.3)

    db.delete_check(check_id)
    assert db.get_check(check_id) is None
    assert db.get_paper_results(check_id) == []
    assert db.get_actual_results(check_id) == []
    assert db.get_comparisons(check_id) == []


def test_paper_results(db: Database) -> None:
    check_id = db.create_check(repo_url="https://github.com/user/repo")
    db.add_paper_result(check_id, metric_name="accuracy", metric_value=92.1, is_best=True)
    db.add_paper_result(check_id, metric_name="f1", metric_value=90.3)

    results = db.get_paper_results(check_id)
    assert len(results) == 2
    assert results[0]["metric_name"] == "accuracy"
    assert results[0]["is_best"]


def test_training_curves(db: Database) -> None:
    check_id = db.create_check(repo_url="https://github.com/user/repo")
    for step in range(10):
        db.add_curve_point(check_id, "loss", step=step, value=2.0 - step * 0.1)

    curve = db.get_curve(check_id, "loss")
    assert len(curve) == 10
    assert curve[0]["value"] == pytest.approx(2.0)
    assert curve[-1]["value"] == pytest.approx(1.1)


def test_stats(db: Database) -> None:
    db.create_check(repo_url="https://github.com/a/repo")
    cid = db.create_check(repo_url="https://github.com/b/repo")
    db.update_check(cid, run_status="success", overall_score=90.0, grade="A")

    stats = db.get_stats()
    assert stats["total"] == 2
    assert stats["success"] == 1
    assert stats["success_rate"] == pytest.approx(0.5)


def test_rejects_invalid_column_name(db: Database) -> None:
    """非法列名应被拒绝，防止 SQL 注入"""
    with pytest.raises(ValueError, match="非法列名"):
        db.create_check(repo_url="https://github.com/user/repo", malicious_col="x")

    check_id = db.create_check(repo_url="https://github.com/user/repo")
    with pytest.raises(ValueError, match="非法列名"):
        db.update_check(check_id, bad_col="x")

    with pytest.raises(ValueError, match="非法列名"):
        db.add_paper_result(check_id, metric_name="acc", metric_value=1.0, hack="x")

    with pytest.raises(ValueError, match="非法列名"):
        db.add_actual_result(check_id, metric_name="acc", metric_value=1.0, hack="x")

    with pytest.raises(ValueError, match="非法列名"):
        db.add_comparison(check_id, metric_name="acc", paper_value=1.0, hack="x")


def test_list_checks_rejects_invalid_sort(db: Database) -> None:
    """list_checks 应拒绝无效排序字段"""
    with pytest.raises(ValueError, match="无效排序字段"):
        db.list_checks(sort="malicious_col")
