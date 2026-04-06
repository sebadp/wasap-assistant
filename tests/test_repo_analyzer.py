"""Tests for repo analyzer (Plan 63-B)."""

from unittest.mock import AsyncMock

from app.reviews.repo_analyzer import (
    _detect_framework,
    _detect_linter,
    _detect_test_runner,
    _extract_conventions,
    analyze_repo,
)


def test_detect_framework_fastapi():
    assert _detect_framework({"pyproject.toml": '[tool.poetry]\nfastapi = "^0.100"'}) == "fastapi"


def test_detect_framework_react():
    assert _detect_framework({"package.json": '{"dependencies": {"react": "^18"}}'}) == "react"


def test_detect_framework_nextjs():
    assert _detect_framework({"package.json": '{"dependencies": {"next": "^14"}}'}) == "nextjs"


def test_detect_framework_none():
    assert _detect_framework({}) is None


def test_detect_linter_ruff():
    assert _detect_linter({"pyproject.toml": "[tool.ruff]\nline-length = 120"}) == "ruff"


def test_detect_linter_eslint():
    assert _detect_linter({".eslintrc.json": "{}"}) == "eslint"


def test_detect_linter_none():
    assert _detect_linter({}) is None


def test_detect_test_runner_pytest():
    assert _detect_test_runner({"pyproject.toml": "[tool.pytest.ini_options]"}) == "pytest"


def test_detect_test_runner_jest():
    assert _detect_test_runner({"package.json": '{"devDependencies": {"jest": "^29"}}'}) == "jest"


def test_detect_test_runner_go():
    assert _detect_test_runner({"go.mod": "module example.com/app"}) == "go test"


def test_extract_conventions_line_length():
    convs = _extract_conventions({"pyproject.toml": "[tool.ruff]\nline-length = 120"})
    assert any("line-length" in c for c in convs)


def test_extract_conventions_empty():
    assert _extract_conventions({}) == []


async def test_analyze_repo():
    provider = AsyncMock()
    provider.get_repo_info.return_value = {
        "language": "Python",
        "default_branch": "main",
        "description": "Test repo",
    }
    provider.get_file_tree.return_value = [
        "app/",
        "app/main.py",
        "tests/",
        "pyproject.toml",
        "README.md",
    ]
    provider.get_file_content.side_effect = lambda path: {
        "pyproject.toml": "[tool.ruff]\nline-length = 120\n[tool.pytest.ini_options]",
        "README.md": "# My Project\nA test project for demo purposes.",
    }.get(path, "")

    profile = await analyze_repo("owner", "repo", provider)
    assert profile.repo_key == "github:owner/repo"
    assert profile.primary_language == "Python"
    assert profile.linter == "ruff"
    assert profile.test_runner == "pytest"
    assert "line-length" in str(profile.conventions)
