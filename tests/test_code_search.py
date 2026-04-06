"""Tests for code search engine (Plan 63-C)."""

import os

import pytest

from app.reviews.code_search import (
    _classify_match,
    _read_context,
    find_definitions,
    find_references,
    find_tests,
    get_cross_file_context,
)
from app.reviews.models import (
    DiffFile,
    DiffHunk,
    DiffLine,
    DiffLineType,
    FileDiffStatus,
    SymbolUsage,
)


@pytest.fixture
def mock_repo(tmp_path):
    """Create a minimal repo structure for testing."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "auth.py").write_text(
        "from app.tokens import validate_token\n"
        "\n"
        "def authenticate(request):\n"
        "    token = request.headers.get('Authorization')\n"
        "    return validate_token(token)\n"
    )
    (tmp_path / "app" / "tokens.py").write_text(
        "import jwt\n"
        "\n"
        "def validate_token(token: str) -> bool:\n"
        '    """Validate JWT token."""\n'
        "    try:\n"
        '        payload = jwt.decode(token, "secret", algorithms=["HS256"])\n'
        "        return True\n"
        "    except jwt.InvalidTokenError:\n"
        "        return False\n"
    )
    (tmp_path / "app" / "middleware.py").write_text(
        "from app.auth import authenticate\n"
        "\n"
        "class AuthMiddleware:\n"
        "    def process(self, request):\n"
        "        if not authenticate(request):\n"
        "            raise PermissionError\n"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_auth.py").write_text(
        "from app.auth import authenticate\n"
        "\n"
        "def test_authenticate_valid():\n"
        "    assert authenticate(mock_request)\n"
        "\n"
        "def test_validate_token():\n"
        "    from app.tokens import validate_token\n"
        "    assert validate_token('valid')\n"
    )
    return tmp_path


def test_classify_definition():
    assert (
        _classify_match("app/tokens.py", "def validate_token(token):", "validate_token")
        == "definition"
    )


def test_classify_test():
    assert _classify_match("tests/test_auth.py", "validate_token('x')", "validate_token") == "test"


def test_classify_import():
    assert (
        _classify_match("app/auth.py", "from app.tokens import validate_token", "validate_token")
        == "import"
    )


def test_classify_usage():
    assert _classify_match("app/middleware.py", "authenticate(request)", "authenticate") == "usage"


def test_read_context(mock_repo):
    ctx = _read_context(mock_repo, "app/tokens.py", 3, context=2)
    assert "validate_token" in ctx
    assert "jwt" in ctx


def test_read_context_missing_file(mock_repo):
    assert _read_context(mock_repo, "nonexistent.py", 1) == ""


@pytest.mark.skipif(
    os.system("which rg > /dev/null 2>&1") != 0,
    reason="ripgrep not installed",
)
async def test_find_references(mock_repo):
    sym = SymbolUsage(
        name="validate_token", kind="function", source_path="app/auth.py", source_line=5
    )
    refs = await find_references(sym, mock_repo, exclude_file="app/auth.py")
    assert len(refs) > 0
    paths = {r.path for r in refs}
    assert "app/tokens.py" in paths


@pytest.mark.skipif(
    os.system("which rg > /dev/null 2>&1") != 0,
    reason="ripgrep not installed",
)
async def test_find_definitions(mock_repo):
    refs = await find_definitions("validate_token", mock_repo, language="python")
    assert len(refs) >= 1
    assert any("def validate_token" in r.content for r in refs)


@pytest.mark.skipif(
    os.system("which rg > /dev/null 2>&1") != 0,
    reason="ripgrep not installed",
)
async def test_find_tests(mock_repo):
    refs = await find_tests("app/auth.py", mock_repo)
    assert len(refs) >= 1
    assert any("test_auth" in r.path for r in refs)


@pytest.mark.skipif(
    os.system("which rg > /dev/null 2>&1") != 0,
    reason="ripgrep not installed",
)
async def test_get_cross_file_context(mock_repo):
    symbols = [
        SymbolUsage(
            name="validate_token", kind="function", source_path="app/auth.py", source_line=5
        ),
    ]
    diff_file = DiffFile(
        path="app/auth.py",
        status=FileDiffStatus.modified,
        language="python",
        hunks=[
            DiffHunk(
                old_start=1,
                old_count=3,
                new_start=1,
                new_count=5,
                header="",
                lines=[
                    DiffLine(DiffLineType.add, "    return validate_token(token)", None, 5, 1),
                ],
            )
        ],
    )
    ctx = await get_cross_file_context(diff_file, symbols, mock_repo, token_budget=5000)
    assert "<cross_file_context>" in ctx
    assert "validate_token" in ctx
    assert "</cross_file_context>" in ctx
