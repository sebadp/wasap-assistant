"""Tests for the LLM review pipeline (mocked LLM) — Plan 63-A."""

import json
from unittest.mock import AsyncMock

import pytest

from app.reviews.diff_parser import parse_unified_diff
from app.reviews.models import RiskLevel, Severity
from app.reviews.reviewer import (
    _budget_files,
    _extract_json,
    _parse_findings_json,
    review_pull_request,
)

SAMPLE_DIFF = """\
diff --git a/app/auth.py b/app/auth.py
--- a/app/auth.py
+++ b/app/auth.py
@@ -10,4 +10,6 @@ def authenticate(token):
     if not token:
         return False
+    if token.startswith("Bearer "):
+        token = token[7:]
     return validate(token)
"""


@pytest.fixture
def files():
    return parse_unified_diff(SAMPLE_DIFF)


@pytest.fixture
def pr():
    from app.reviews.models import PullRequestInfo

    return PullRequestInfo(
        number=1,
        title="Fix auth",
        description="Strip bearer prefix",
        author="dev",
        base_branch="main",
        head_branch="fix",
        url="https://github.com/o/r/pull/1",
        repo_owner="o",
        repo_name="r",
        files_changed=1,
        additions=2,
        deletions=0,
        commit_sha="abc",
    )


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


def test_budget_files(files):
    selected, overflow = _budget_files(files, max_tokens=50000)
    assert len(selected) == 1
    assert len(overflow) == 0


def test_budget_files_overflow(files):
    # Tiny budget forces overflow
    selected, overflow = _budget_files(files, max_tokens=1)
    assert len(selected) == 0
    assert len(overflow) == 1


def test_extract_json_plain():
    assert _extract_json("[]") == "[]"


def test_extract_json_fenced():
    raw = '```json\n[{"a": 1}]\n```'
    assert _extract_json(raw) == '[{"a": 1}]'


def test_parse_findings_valid(files):
    raw = json.dumps(
        [
            {
                "line": 12,
                "side": "RIGHT",
                "severity": "warning",
                "category": "bug",
                "body": "issue",
                "suggestion": None,
                "confidence": 9,
                "start_line": None,
            }
        ]
    )
    findings = _parse_findings_json(raw, files[0], min_confidence=7.0, max_findings=10)
    assert len(findings) == 1
    assert findings[0].severity == Severity.warning


def test_parse_findings_filters_low_confidence(files):
    raw = json.dumps(
        [
            {
                "line": 12,
                "side": "RIGHT",
                "severity": "warning",
                "category": "bug",
                "body": "maybe",
                "confidence": 3,
            }
        ]
    )
    findings = _parse_findings_json(raw, files[0], min_confidence=7.0, max_findings=10)
    assert len(findings) == 0


def test_parse_findings_invalid_json(files):
    findings = _parse_findings_json("not json", files[0], 7.0, 10)
    assert findings == []


def test_parse_findings_invalid_line(files):
    raw = json.dumps(
        [
            {
                "line": 9999,
                "side": "RIGHT",
                "severity": "warning",
                "category": "bug",
                "body": "bad line",
                "confidence": 9,
            }
        ]
    )
    findings = _parse_findings_json(raw, files[0], 7.0, 10)
    assert len(findings) == 0


async def test_review_pull_request(pr, files, mock_client):
    # Summary response
    summary_json = json.dumps(
        {
            "title": "Auth fix",
            "overview": "Strips bearer",
            "risk_level": "low",
            "key_changes": ["strip bearer"],
        }
    )
    # File review response (line 12 is valid in our diff)
    review_json = json.dumps(
        [
            {
                "line": 12,
                "side": "RIGHT",
                "severity": "suggestion",
                "category": "style",
                "body": "Consider extracting prefix",
                "suggestion": None,
                "confidence": 8,
            }
        ]
    )
    mock_client.chat = AsyncMock(side_effect=[summary_json, review_json])

    result = await review_pull_request(pr, files, mock_client)
    assert result.title == "Auth fix"
    assert result.risk_level == RiskLevel.low
    assert result.files_reviewed == 1
    assert len(result.findings) == 1
