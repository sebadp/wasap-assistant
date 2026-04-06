"""Tests for PR Review domain models (Plan 63-A)."""

from app.reviews.models import (
    Category,
    DiffFile,
    DiffHunk,
    DiffLine,
    DiffLineType,
    FileDiffStatus,
    PullRequestInfo,
    ReviewComment,
    ReviewFinding,
    ReviewSummary,
    RiskLevel,
    Severity,
)


def test_severity_values():
    assert Severity.critical.value == "critical"
    assert Severity.nitpick.value == "nitpick"


def test_category_values():
    assert Category.security.value == "security"
    assert Category.bug.value == "bug"
    assert len(Category) == 8


def test_diff_line_construction():
    line = DiffLine(
        type=DiffLineType.add,
        content="    return True",
        old_line_no=None,
        new_line_no=42,
        diff_position=3,
    )
    assert line.new_line_no == 42
    assert line.old_line_no is None


def test_diff_hunk_with_lines():
    hunk = DiffHunk(old_start=10, old_count=5, new_start=10, new_count=7, header="def foo()")
    hunk.lines.append(DiffLine(DiffLineType.context, "pass", 10, 10, 1))
    assert len(hunk.lines) == 1


def test_diff_file_defaults():
    f = DiffFile(path="app/main.py", status=FileDiffStatus.modified)
    assert f.additions == 0
    assert f.hunks == []
    assert not f.is_generated
    assert f.old_path is None


def test_pull_request_info():
    pr = PullRequestInfo(
        number=42,
        title="Fix auth",
        description="",
        author="dev",
        base_branch="main",
        head_branch="fix/auth",
        url="https://github.com/o/r/pull/42",
        repo_owner="o",
        repo_name="r",
        files_changed=3,
        additions=10,
        deletions=5,
        commit_sha="abc123",
    )
    assert pr.number == 42
    assert pr.commit_sha == "abc123"


def test_review_finding_defaults():
    f = ReviewFinding(
        path="a.py",
        line=10,
        side="RIGHT",
        severity=Severity.warning,
        category=Category.bug,
        body="bad",
    )
    assert f.confidence == 8.0
    assert f.suggestion is None
    assert f.start_line is None
    assert f.exploit_scenario is None


def test_review_summary():
    s = ReviewSummary(
        title="Fix",
        overview="Fixed stuff",
        risk_level=RiskLevel.low,
        key_changes=["a"],
        stats={"findings_total": 1},
        findings=[],
        files_reviewed=2,
        files_skipped=0,
        duration_ms=500.0,
    )
    assert s.files_reviewed == 2


def test_review_comment():
    c = ReviewComment(path="a.py", line=5, side="RIGHT", body="fix this")
    assert c.start_line is None
    assert c.start_side is None
