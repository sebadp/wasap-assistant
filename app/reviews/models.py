"""Domain models for the PR Review subsystem (Plan 63-A)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    critical = "critical"
    warning = "warning"
    suggestion = "suggestion"
    nitpick = "nitpick"


class Category(str, Enum):
    security = "security"
    bug = "bug"
    performance = "performance"
    error_handling = "error_handling"
    maintainability = "maintainability"
    style = "style"
    test_coverage = "test_coverage"
    documentation = "documentation"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class DiffLineType(str, Enum):
    context = "context"
    add = "add"
    remove = "remove"


class FileDiffStatus(str, Enum):
    added = "added"
    modified = "modified"
    deleted = "deleted"
    renamed = "renamed"


# ---------------------------------------------------------------------------
# Diff models
# ---------------------------------------------------------------------------


@dataclass
class DiffLine:
    type: DiffLineType
    content: str
    old_line_no: int | None  # None for added lines
    new_line_no: int | None  # None for deleted lines
    diff_position: int  # 1-indexed position in the diff hunk (for GitHub API)


@dataclass
class DiffHunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str  # function/class context after @@
    lines: list[DiffLine] = field(default_factory=list)


@dataclass
class DiffFile:
    path: str
    status: FileDiffStatus
    hunks: list[DiffHunk] = field(default_factory=list)
    language: str = ""
    additions: int = 0
    deletions: int = 0
    is_generated: bool = False
    old_path: str | None = None  # For renames


# ---------------------------------------------------------------------------
# Pull Request info
# ---------------------------------------------------------------------------


@dataclass
class PullRequestInfo:
    number: int
    title: str
    description: str
    author: str
    base_branch: str
    head_branch: str
    url: str
    repo_owner: str
    repo_name: str
    files_changed: int
    additions: int
    deletions: int
    commit_sha: str


# ---------------------------------------------------------------------------
# Review findings
# ---------------------------------------------------------------------------


@dataclass
class ReviewFinding:
    path: str
    line: int
    side: str  # "RIGHT" (new) or "LEFT" (old)
    severity: Severity
    category: Category
    body: str
    suggestion: str | None = None
    confidence: float = 8.0  # 1-10 scale
    start_line: int | None = None  # For multi-line comments
    exploit_scenario: str | None = None  # For security/bug findings


@dataclass
class ReviewSummary:
    title: str
    overview: str
    risk_level: RiskLevel
    key_changes: list[str]
    stats: dict[str, int | float]
    findings: list[ReviewFinding]
    files_reviewed: int
    files_skipped: int
    duration_ms: float


# ---------------------------------------------------------------------------
# Repo Profile (Phase B)
# ---------------------------------------------------------------------------


@dataclass
class RepoProfile:
    repo_key: str  # "github:owner/repo"
    owner: str
    repo: str
    provider: str = "github"
    default_branch: str = "main"
    primary_language: str = ""
    framework: str | None = None
    linter: str | None = None
    test_runner: str | None = None
    conventions: list[str] = field(default_factory=list)
    file_tree: list[str] = field(default_factory=list)
    readme_summary: str = ""
    config_snippets: dict[str, str] = field(default_factory=dict)
    indexing_level: int = 0  # 0=metadata, 1=deep
    last_analyzed_at: str = ""


# ---------------------------------------------------------------------------
# Deep Code Search models (Phase C)
# ---------------------------------------------------------------------------


@dataclass
class CodeReference:
    path: str
    start_line: int
    end_line: int
    content: str
    match_type: str  # "definition", "usage", "import", "test", "related"
    symbol: str


@dataclass
class SymbolUsage:
    name: str  # "validate_token", "UserModel", etc.
    kind: str  # "function", "class", "variable", "import", "type"
    source_path: str
    source_line: int


# ---------------------------------------------------------------------------
# Provider-level comment (what SCMProvider needs to post)
# ---------------------------------------------------------------------------


@dataclass
class VerificationResult:
    is_valid: bool
    confidence: float  # 1-10 scale
    reasoning: str
    revised_severity: Severity | None = None


@dataclass
class ReviewComment:
    path: str
    line: int
    side: str
    body: str
    start_line: int | None = None
    start_side: str | None = None
