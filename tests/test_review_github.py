"""Tests for GitHubProvider (mocked httpx) — Plan 63-A."""

from unittest.mock import AsyncMock

import httpx
import pytest

from app.reviews.models import ReviewComment
from app.reviews.providers.github import GitHubProvider


@pytest.fixture
def mock_client():
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def provider(mock_client):
    return GitHubProvider(owner="acme", repo="app", token="ghp_test", http_client=mock_client)


def _make_response(json_data=None, text="", status_code=200):
    import json

    if json_data is not None:
        content = json.dumps(json_data).encode()
    else:
        content = text.encode()
    return httpx.Response(
        status_code=status_code, content=content, request=httpx.Request("GET", "https://x")
    )


async def test_get_pull_request(provider, mock_client):
    mock_client.request.return_value = _make_response(
        json_data={
            "number": 42,
            "title": "Fix",
            "body": "desc",
            "html_url": "https://github.com/acme/app/pull/42",
            "user": {"login": "dev"},
            "base": {"ref": "main"},
            "head": {"ref": "fix", "sha": "abc"},
            "changed_files": 3,
            "additions": 10,
            "deletions": 2,
        }
    )
    pr = await provider.get_pull_request(42)
    assert pr.number == 42
    assert pr.author == "dev"
    assert pr.commit_sha == "abc"


async def test_get_diff(provider, mock_client):
    mock_client.request.return_value = _make_response(text="diff --git a/f b/f\n+line")
    diff = await provider.get_diff(1)
    assert "diff --git" in diff


async def test_get_changed_files_paginated(provider, mock_client):
    page1 = [{"filename": f"f{i}.py"} for i in range(100)]
    page2 = [{"filename": "last.py"}]
    mock_client.request.side_effect = [
        _make_response(json_data=page1),
        _make_response(json_data=page2),
    ]
    files = await provider.get_changed_files(1)
    assert len(files) == 101


async def test_post_review(provider, mock_client):
    mock_client.request.return_value = _make_response(json_data={"html_url": "https://review/1"})
    comments = [ReviewComment(path="a.py", line=5, side="RIGHT", body="fix")]
    url = await provider.post_review(1, "summary", "COMMENT", comments)
    assert url == "https://review/1"
    call_kwargs = mock_client.request.call_args
    payload = call_kwargs.kwargs["json"]
    assert len(payload["comments"]) == 1
    assert payload["comments"][0]["line"] == 5


async def test_post_review_multiline(provider, mock_client):
    mock_client.request.return_value = _make_response(json_data={"html_url": "https://review/1"})
    comments = [
        ReviewComment(
            path="a.py", line=10, side="RIGHT", body="fix", start_line=5, start_side="RIGHT"
        )
    ]
    await provider.post_review(1, "body", "COMMENT", comments)
    payload = mock_client.request.call_args.kwargs["json"]
    assert payload["comments"][0]["start_line"] == 5
    assert payload["comments"][0]["start_side"] == "RIGHT"
