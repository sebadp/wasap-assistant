"""Tests for repo_profiles CRUD (Plan 63-B)."""

import pytest

from app.database.db import init_db
from app.database.repository import Repository


@pytest.fixture
async def repo():
    conn, _ = await init_db(":memory:")
    r = Repository(conn)
    yield r
    await conn.close()


async def test_save_and_get(repo):
    profile = {
        "repo_key": "github:acme/app",
        "owner": "acme",
        "repo": "app",
        "provider": "github",
        "default_branch": "main",
        "primary_language": "Python",
        "framework": "fastapi",
        "linter": "ruff",
        "test_runner": "pytest",
        "conventions": ["line-length = 120"],
        "file_tree": ["app/", "tests/"],
        "readme_summary": "A test project",
        "config_snippets": {"pyproject.toml": "[tool.ruff]"},
        "indexing_level": 0,
        "last_analyzed_at": "2026-01-01T00:00:00",
    }
    await repo.save_repo_profile(profile)
    result = await repo.get_repo_profile("github:acme/app")
    assert result is not None
    assert result["primary_language"] == "Python"
    assert result["framework"] == "fastapi"
    assert result["conventions"] == ["line-length = 120"]
    assert result["file_tree"] == ["app/", "tests/"]
    assert result["config_snippets"] == {"pyproject.toml": "[tool.ruff]"}


async def test_get_nonexistent(repo):
    result = await repo.get_repo_profile("github:nope/nope")
    assert result is None


async def test_list_profiles(repo):
    await repo.save_repo_profile(
        {
            "repo_key": "github:a/b",
            "owner": "a",
            "repo": "b",
        }
    )
    await repo.save_repo_profile(
        {
            "repo_key": "github:c/d",
            "owner": "c",
            "repo": "d",
        }
    )
    profiles = await repo.list_repo_profiles()
    assert len(profiles) == 2


async def test_delete_profile(repo):
    await repo.save_repo_profile(
        {
            "repo_key": "github:a/b",
            "owner": "a",
            "repo": "b",
        }
    )
    assert await repo.delete_repo_profile("github:a/b")
    assert await repo.get_repo_profile("github:a/b") is None


async def test_delete_nonexistent(repo):
    assert not await repo.delete_repo_profile("github:nope/nope")


async def test_upsert(repo):
    await repo.save_repo_profile(
        {
            "repo_key": "github:a/b",
            "owner": "a",
            "repo": "b",
            "primary_language": "Python",
        }
    )
    await repo.save_repo_profile(
        {
            "repo_key": "github:a/b",
            "owner": "a",
            "repo": "b",
            "primary_language": "Go",
        }
    )
    result = await repo.get_repo_profile("github:a/b")
    assert result["primary_language"] == "Go"
