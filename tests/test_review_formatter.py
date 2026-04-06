"""Tests for PR review formatters (Plan 63-A)."""

from app.reviews.formatter import format_finding_for_github, format_review_summary
from app.reviews.models import (
    Category,
    PullRequestInfo,
    ReviewFinding,
    ReviewSummary,
    RiskLevel,
    Severity,
)


def _make_pr():
    return PullRequestInfo(
        number=42,
        title="Fix auth",
        description="",
        author="dev",
        base_branch="main",
        head_branch="fix",
        url="https://github.com/o/r/pull/42",
        repo_owner="o",
        repo_name="r",
        files_changed=3,
        additions=10,
        deletions=5,
        commit_sha="abc",
    )


def _make_summary(findings=None):
    return ReviewSummary(
        title="Fix auth",
        overview="Fixed authentication flow",
        risk_level=RiskLevel.medium,
        key_changes=["Strip bearer prefix"],
        stats={"additions": 10, "deletions": 5, "findings_total": len(findings or [])},
        findings=findings or [],
        files_reviewed=2,
        files_skipped=1,
        duration_ms=1500.0,
    )


def test_format_summary_basic():
    text = format_review_summary(_make_summary(), _make_pr())
    assert "PR Review: #42" in text
    assert "Fix auth" in text
    assert "Medium" in text


def test_format_summary_with_findings():
    findings = [
        ReviewFinding(
            path="a.py",
            line=10,
            side="RIGHT",
            severity=Severity.warning,
            category=Category.bug,
            body="Potential null",
        ),
    ]
    text = format_review_summary(_make_summary(findings), _make_pr())
    assert "bug" in text
    assert "a.py:10" in text


def test_format_summary_skipped_note():
    text = format_review_summary(_make_summary(), _make_pr())
    assert "1 archivos omitidos" in text


def test_format_finding_github():
    f = ReviewFinding(
        path="a.py",
        line=10,
        side="RIGHT",
        severity=Severity.critical,
        category=Category.security,
        body="SQL injection risk",
        suggestion="use parameterized query",
        confidence=0.95,
    )
    text = format_finding_for_github(f)
    assert "**[security]**" in text
    assert "SQL injection risk" in text
    assert "```suggestion" in text
    assert "use parameterized query" in text
    assert "95%" in text


def test_format_finding_no_suggestion():
    f = ReviewFinding(
        path="a.py",
        line=5,
        side="RIGHT",
        severity=Severity.nitpick,
        category=Category.style,
        body="naming",
    )
    text = format_finding_for_github(f)
    assert "```suggestion" not in text
    assert "LocalForge" in text
