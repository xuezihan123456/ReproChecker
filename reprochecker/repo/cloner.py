"""Git 仓库克隆与缓存管理"""

from __future__ import annotations

import re
import shutil
import time
from pathlib import Path

import git

from reprochecker.config import get_config
from reprochecker.logging import get_logger

logger = get_logger(__name__.replace("reprochecker.", ""))

# 通用 Git URL 正则：匹配多种托管平台的 HTTPS/SSH 格式
_GIT_HTTPS_RE = re.compile(
    r"https?://(?:github\.com|gitlab\.com|bitbucket\.org)"
    r"/(?P<owner>[^/]+)/(?P<repo>[^/\s]+?)(?:\.git)?(?:/)?(?:\s|$)"
)
_GIT_SSH_RE = re.compile(
    r"git@(?:github\.com|gitlab\.com|bitbucket\.org)"
    r":(?P<owner>[^/]+)/(?P<repo>[^/\s]+?)(?:\.git)?(?:\s|$)"
)
# HuggingFace: https://huggingface.co/user/repo
_HF_RE = re.compile(
    r"https?://huggingface\.co/(?P<owner>[^/]+)/(?P<repo>[^/\s]+?)(?:/)?(?:\s|$)"
)


def parse_repo_name(url: str) -> str:
    """从 Git URL 中提取 'owner/repo' 格式的仓库名。

    支持 GitHub、GitLab、Bitbucket、HuggingFace 的 HTTPS/SSH 格式。
    无法匹配时回退到 URL 最后两段路径。

    Args:
        url: Git 仓库 URL。

    Returns:
        'owner/repo' 格式的字符串。

    Raises:
        ValueError: 无法从 URL 中解析出仓库名。
    """
    url = url.strip().rstrip("/")

    match = _GIT_HTTPS_RE.search(url) or _GIT_SSH_RE.search(url) or _HF_RE.search(url)
    if match:
        return f"{match.group('owner')}/{match.group('repo')}"

    # 回退：取 URL 最后两段
    parts = [p for p in url.rstrip("/").split("/") if p]
    if len(parts) >= 2:
        repo = parts[-1].removesuffix(".git")
        return f"{parts[-2]}/{repo}"

    raise ValueError(f"无法从 URL 中解析仓库名: {url}")


def _get_cache_path(repo_name: str) -> Path:
    """获取仓库缓存目录路径。

    Args:
        repo_name: 'owner/repo' 格式的仓库名。

    Returns:
        缓存目录的绝对路径。
    """
    config = get_config()
    # 将 'owner/repo' 映射为 'owner___repo' 避免子目录问题
    # 使用三下划线分隔，避免与仓库名中的双下划线冲突
    safe_name = repo_name.replace("/", "___")
    return config.cache_dir / safe_name


def _get_commit_hash(repo: git.Repo) -> str:
    """获取仓库当前 HEAD 的 commit hash。

    Args:
        repo: gitpython Repo 对象。

    Returns:
        完整的 commit SHA 字符串。
    """
    return repo.head.commit.hexsha


def _retry_clone(url: str, target: str, retries: int = 3) -> git.Repo:
    """带指数退避的克隆重试。"""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return git.Repo.clone_from(url, target)
        except git.GitCommandError as e:
            last_exc = e
            if attempt < retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    "克隆失败 (attempt %d/%d)，%ds 后重试: %s",
                    attempt + 1, retries, wait, e,
                )
                time.sleep(wait)
    raise last_exc  # type: ignore[misc]


def clone_repo(url: str, no_cache: bool = False) -> tuple[Path, str, str | None]:
    """克隆 Git 仓库到本地缓存目录。

    如果缓存已存在且 no_cache=False，直接使用缓存（执行 git pull 更新）。
    如果 no_cache=True，删除缓存后重新克隆。网络失败时自动重试 3 次。

    Args:
        url: Git 仓库 URL。
        no_cache: 是否忽略缓存，强制重新克隆。

    Returns:
        三元组 (repo_path, commit_hash, repo_name)：
        - repo_path: 本地仓库路径
        - commit_hash: 当前 HEAD 的 commit hash
        - repo_name: 'owner/repo' 格式的仓库名
    """
    config = get_config()
    config.ensure_dirs()

    repo_name = parse_repo_name(url)
    cache_path = _get_cache_path(repo_name)

    if cache_path.exists() and not no_cache:
        repo = git.Repo(cache_path)
        try:
            origin = repo.remotes.origin
            origin.pull()
        except git.GitCommandError:
            logger.debug("git pull 失败，使用本地缓存")
        commit_hash = _get_commit_hash(repo)
        return cache_path, commit_hash, repo_name

    if cache_path.exists():
        shutil.rmtree(cache_path, ignore_errors=True)

    repo = _retry_clone(url, str(cache_path))
    commit_hash = _get_commit_hash(repo)
    return cache_path, commit_hash, repo_name


def clear_cache(repo_name: str | None = None) -> int:
    """清除缓存目录。

    Args:
        repo_name: 指定仓库名清除单个缓存；为 None 时清除全部缓存。

    Returns:
        删除的缓存目录数量。
    """
    config = get_config()

    if repo_name is not None:
        cache_path = _get_cache_path(repo_name)
        if cache_path.exists():
            shutil.rmtree(cache_path, ignore_errors=True)
            return 1
        return 0

    # 清除全部缓存
    count = 0
    if config.cache_dir.exists():
        for child in config.cache_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                count += 1
    return count


def list_cached_repos() -> list[dict[str, str]]:
    """列出所有已缓存的仓库信息。

    Returns:
        字典列表，每项包含 name、path、commit_hash。
    """
    config = get_config()
    results: list[dict[str, str]] = []

    if not config.cache_dir.exists():
        return results

    for child in sorted(config.cache_dir.iterdir()):
        if not child.is_dir():
            continue
        try:
            repo = git.Repo(child)
            commit_hash = _get_commit_hash(repo)
        except (git.InvalidGitRepositoryError, Exception):
            commit_hash = "unknown"

        # 将 'owner___repo' 还原为 'owner/repo'
        name = child.name.replace("___", "/", 1)
        results.append({
            "name": name,
            "path": str(child),
            "commit_hash": commit_hash,
        })

    return results
