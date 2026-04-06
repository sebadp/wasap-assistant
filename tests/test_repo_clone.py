"""Tests for repo clone manager (Plan 63-C)."""

from pathlib import Path

from app.reviews.repo_clone import (
    _clone_dir,
    cleanup_stale_clones,
    get_clone_path,
    remove_clone,
)


def test_clone_dir_safe_name():
    base = Path("/tmp/clones")
    result = _clone_dir("github:owner/repo", base)
    assert result == base / "github_owner_repo"


def test_get_clone_path_not_exists(tmp_path):
    assert get_clone_path("github:nope/nope", str(tmp_path)) is None


def test_get_clone_path_exists(tmp_path):
    clone = tmp_path / "github_owner_repo"
    clone.mkdir()
    (clone / ".git").mkdir()
    result = get_clone_path("github:owner/repo", str(tmp_path))
    assert result == clone


def test_remove_clone(tmp_path):
    clone = tmp_path / "github_owner_repo"
    clone.mkdir()
    (clone / ".git").mkdir()
    assert remove_clone("github:owner/repo", str(tmp_path))
    assert not clone.exists()


def test_remove_clone_not_exists(tmp_path):
    assert not remove_clone("github:nope/nope", str(tmp_path))


def test_cleanup_stale_clones(tmp_path):
    # Create a "stale" clone
    clone = tmp_path / "old_clone"
    clone.mkdir()
    (clone / ".git").mkdir()
    import os
    import time

    # Set mtime to 60 days ago
    old_time = time.time() - (60 * 86400)
    os.utime(clone, (old_time, old_time))

    removed = cleanup_stale_clones(str(tmp_path), max_age_days=30)
    assert removed == 1
    assert not clone.exists()


def test_cleanup_keeps_fresh_clones(tmp_path):
    clone = tmp_path / "fresh_clone"
    clone.mkdir()
    (clone / ".git").mkdir()
    removed = cleanup_stale_clones(str(tmp_path), max_age_days=30)
    assert removed == 0
    assert clone.exists()
