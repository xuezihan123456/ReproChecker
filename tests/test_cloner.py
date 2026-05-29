"""Git 克隆模块测试"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reprochecker.repo.cloner import (
    _get_cache_path,
    clear_cache,
    list_cached_repos,
    parse_repo_name,
)


class TestParseRepoName:
    """URL 解析测试"""

    def test_https_github(self) -> None:
        assert parse_repo_name("https://github.com/user/repo") == "user/repo"

    def test_https_github_trailing_slash(self) -> None:
        assert parse_repo_name("https://github.com/user/repo/") == "user/repo"

    def test_https_github_dot_git(self) -> None:
        assert parse_repo_name("https://github.com/user/repo.git") == "user/repo"

    def test_ssh_github(self) -> None:
        assert parse_repo_name("git@github.com:user/repo.git") == "user/repo"

    def test_ssh_github_no_suffix(self) -> None:
        assert parse_repo_name("git@github.com:user/repo") == "user/repo"

    def test_https_gitlab(self) -> None:
        assert parse_repo_name("https://gitlab.com/group/project") == "group/project"

    def test_ssh_gitlab(self) -> None:
        assert parse_repo_name("git@gitlab.com:group/project.git") == "group/project"

    def test_https_bitbucket(self) -> None:
        assert parse_repo_name("https://bitbucket.org/team/repo") == "team/repo"

    def test_ssh_bitbucket(self) -> None:
        assert parse_repo_name("git@bitbucket.org:team/repo.git") == "team/repo"

    def test_huggingface(self) -> None:
        url = "https://huggingface.co/bert-base-uncased/bert-model"
        assert parse_repo_name(url) == "bert-base-uncased/bert-model"

    def test_generic_url_fallback(self) -> None:
        assert parse_repo_name("https://example.com/owner/repo.git") == "owner/repo"

    def test_generic_url_no_suffix(self) -> None:
        assert parse_repo_name("https://my-git.edu/lab/project") == "lab/project"

    def test_invalid_url_raises(self) -> None:
        with pytest.raises(ValueError, match="无法从 URL 中解析仓库名"):
            parse_repo_name("not-a-url")

    def test_bare_word_raises(self) -> None:
        with pytest.raises(ValueError, match="无法从 URL 中解析仓库名"):
            parse_repo_name("just-a-word")

    def test_strips_whitespace(self) -> None:
        assert parse_repo_name("  https://github.com/user/repo  ") == "user/repo"


class TestCachePath:
    """缓存路径测试"""

    @patch("reprochecker.repo.cloner.get_config")
    def test_cache_path_uses_triple_underscore(self, mock_config: MagicMock) -> None:
        """缓存路径应使用三下划线分隔 owner 和 repo"""
        mock_config.return_value.cache_dir = Path("/tmp/cache")
        result = _get_cache_path("user/repo")
        assert result == Path("/tmp/cache/user___repo")

    @patch("reprochecker.repo.cloner.get_config")
    def test_cache_path_preserves_double_underscore(self, mock_config: MagicMock) -> None:
        """仓库名中的双下划线应保留"""
        mock_config.return_value.cache_dir = Path("/tmp/cache")
        result = _get_cache_path("user/my__repo")
        assert result == Path("/tmp/cache/user___my__repo")


class TestClearCache:
    """缓存清理测试"""

    @patch("reprochecker.repo.cloner.get_config")
    def test_clear_single_cache(self, mock_config: MagicMock, tmp_path: Path) -> None:
        """应清除指定仓库的缓存"""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        repo_dir = cache_dir / "user___repo"
        repo_dir.mkdir()
        mock_config.return_value.cache_dir = cache_dir

        count = clear_cache("user/repo")
        assert count == 1
        assert not repo_dir.exists()

    @patch("reprochecker.repo.cloner.get_config")
    def test_clear_nonexistent_cache(self, mock_config: MagicMock, tmp_path: Path) -> None:
        """清除不存在的缓存应返回 0"""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        mock_config.return_value.cache_dir = cache_dir

        count = clear_cache("user/nonexistent")
        assert count == 0

    @patch("reprochecker.repo.cloner.get_config")
    def test_clear_all_cache(self, mock_config: MagicMock, tmp_path: Path) -> None:
        """应清除所有缓存"""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "repo1").mkdir()
        (cache_dir / "repo2").mkdir()
        mock_config.return_value.cache_dir = cache_dir

        count = clear_cache()
        assert count == 2
        assert list(cache_dir.iterdir()) == []


class TestListCachedRepos:
    """缓存列表测试"""

    @patch("reprochecker.repo.cloner.get_config")
    def test_list_empty_cache(self, mock_config: MagicMock, tmp_path: Path) -> None:
        """空缓存目录应返回空列表"""
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        mock_config.return_value.cache_dir = cache_dir

        result = list_cached_repos()
        assert result == []

    @patch("reprochecker.repo.cloner.get_config")
    def test_list_nonexistent_cache_dir(self, mock_config: MagicMock) -> None:
        """缓存目录不存在应返回空列表"""
        mock_config.return_value.cache_dir = Path("/nonexistent/path")

        result = list_cached_repos()
        assert result == []
