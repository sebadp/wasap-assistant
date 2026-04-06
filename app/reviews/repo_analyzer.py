"""Repo Analyzer — fetch & analyze repo metadata for context injection (Plan 63-B)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.reviews.models import RepoProfile
from app.reviews.providers.github import GitHubProvider

logger = logging.getLogger(__name__)

# Config files to fetch and analyze
_CONFIG_TARGETS = (
    "pyproject.toml",
    "package.json",
    "tsconfig.json",
    ".eslintrc.json",
    ".eslintrc.js",
    ".prettierrc",
    "Makefile",
    "Dockerfile",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
    ".github/workflows/ci.yml",
    ".github/workflows/ci.yaml",
    "ruff.toml",
    ".ruff.toml",
    "setup.cfg",
)


async def analyze_repo(owner: str, repo: str, provider: GitHubProvider) -> RepoProfile:
    """Analyze a repository and return a RepoProfile."""
    # Fetch metadata
    info = await provider.get_repo_info()
    tree = await provider.get_file_tree()
    configs = await _fetch_config_files(provider, tree)
    readme = await _fetch_readme(provider)

    framework = _detect_framework(configs)
    linter = _detect_linter(configs)
    test_runner = _detect_test_runner(configs)
    conventions = _extract_conventions(configs)

    return RepoProfile(
        repo_key=f"github:{owner}/{repo}",
        owner=owner,
        repo=repo,
        provider="github",
        default_branch=info.get("default_branch", "main"),
        primary_language=info.get("language", "") or "",
        framework=framework,
        linter=linter,
        test_runner=test_runner,
        conventions=conventions,
        file_tree=tree[:500],
        readme_summary=readme[:500] if readme else "",
        config_snippets={k: v[:2000] for k, v in configs.items()},
        indexing_level=0,
        last_analyzed_at=datetime.now(UTC).isoformat(),
    )


async def _fetch_config_files(provider: GitHubProvider, tree: list[str]) -> dict[str, str]:
    """Fetch known config files from the repo."""
    configs: dict[str, str] = {}
    tree_set = set(tree)
    for target in _CONFIG_TARGETS:
        if target in tree_set:
            try:
                content = await provider.get_file_content(target)
                if content:
                    configs[target] = content
            except Exception:
                logger.debug("Could not fetch %s", target)
    return configs


async def _fetch_readme(provider: GitHubProvider) -> str:
    """Fetch README content."""
    for name in ("README.md", "readme.md", "README.rst", "README"):
        try:
            content = await provider.get_file_content(name)
            if content:
                return content
        except Exception:
            continue
    return ""


def _detect_framework(configs: dict[str, str]) -> str | None:
    """Detect the primary framework from config files."""
    pkg = configs.get("package.json", "")
    pyproject = configs.get("pyproject.toml", "")
    req = configs.get("requirements.txt", "")

    # Python
    combined_py = pyproject + req
    if "fastapi" in combined_py.lower():
        return "fastapi"
    if "django" in combined_py.lower():
        return "django"
    if "flask" in combined_py.lower():
        return "flask"

    # JS/TS
    if '"next"' in pkg or '"next":' in pkg:
        return "nextjs"
    if '"react"' in pkg:
        return "react"
    if '"vue"' in pkg:
        return "vue"
    if '"express"' in pkg:
        return "express"
    if '"svelte"' in pkg:
        return "svelte"

    # Go
    if "go.mod" in configs:
        go_mod = configs["go.mod"]
        if "gin-gonic" in go_mod:
            return "gin"
        if "echo" in go_mod:
            return "echo"

    # Rust
    if "Cargo.toml" in configs:
        cargo = configs["Cargo.toml"]
        if "actix" in cargo:
            return "actix"
        if "axum" in cargo:
            return "axum"

    return None


def _detect_linter(configs: dict[str, str]) -> str | None:
    """Detect the linter from config files."""
    if any(k.startswith("ruff") or k.startswith(".ruff") for k in configs):
        return "ruff"
    pyproject = configs.get("pyproject.toml", "")
    if "[tool.ruff]" in pyproject:
        return "ruff"
    if "[tool.black]" in pyproject or "black" in pyproject.lower().split("\n")[0:5]:
        return "black"
    if "[tool.flake8]" in pyproject or "flake8" in configs.get("setup.cfg", ""):
        return "flake8"
    if any(k.startswith(".eslintrc") for k in configs):
        return "eslint"
    if ".prettierrc" in configs:
        return "prettier"
    pkg = configs.get("package.json", "")
    if '"eslint"' in pkg:
        return "eslint"
    return None


def _detect_test_runner(configs: dict[str, str]) -> str | None:
    """Detect the test runner from config files."""
    pyproject = configs.get("pyproject.toml", "")
    if "[tool.pytest" in pyproject or "pytest" in configs.get("requirements.txt", ""):
        return "pytest"
    pkg = configs.get("package.json", "")
    if '"vitest"' in pkg:
        return "vitest"
    if '"jest"' in pkg:
        return "jest"
    if '"mocha"' in pkg:
        return "mocha"
    if "go.mod" in configs:
        return "go test"
    if "Cargo.toml" in configs:
        return "cargo test"
    return None


def _extract_conventions(configs: dict[str, str]) -> list[str]:
    """Extract coding conventions from config files."""
    conventions: list[str] = []
    pyproject = configs.get("pyproject.toml", "")

    # Line length
    for line in pyproject.split("\n"):
        if "line-length" in line or "line_length" in line:
            conventions.append(line.strip())
            break

    # Python target version
    for line in pyproject.split("\n"):
        if "target-version" in line:
            conventions.append(line.strip())
            break

    # Indent
    if "tsconfig.json" in configs:
        conventions.append("typescript")

    # Test framework
    if "[tool.pytest" in pyproject:
        conventions.append("pytest")

    pkg = configs.get("package.json", "")
    if '"type": "module"' in pkg:
        conventions.append("esm")

    return conventions
