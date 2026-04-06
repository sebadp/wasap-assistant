"""Factory: URL → SCMProvider (Plan 63-A)."""

from __future__ import annotations

import re

from app.reviews.providers.base import SCMProvider
from app.reviews.providers.github import GitHubProvider

_GITHUB_PR_RE = re.compile(
    r"(?:https?://)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """Parse a PR URL and return (owner, repo, pr_number).

    Raises ValueError for unsupported URLs.
    """
    m = _GITHUB_PR_RE.match(url)
    if m:
        return m.group("owner"), m.group("repo"), int(m.group("number"))
    raise ValueError(f"Unsupported PR URL: {url}")


def create_provider(url: str, token: str) -> tuple[SCMProvider, int]:
    """Create an SCM provider from a PR URL.

    Returns (provider, pr_number).
    """
    owner, repo, number = parse_pr_url(url)
    provider = GitHubProvider(owner=owner, repo=repo, token=token)
    return provider, number
