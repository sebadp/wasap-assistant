"""Unified diff parser → structured DiffFile/DiffHunk/DiffLine models (Plan 63-A)."""

from __future__ import annotations

import re

from app.reviews.models import DiffFile, DiffHunk, DiffLine, DiffLineType, FileDiffStatus

_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)")
_RENAME_FROM_RE = re.compile(r"^rename from (.+)$")
_RENAME_TO_RE = re.compile(r"^rename to (.+)$")

_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".cs": "csharp",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".md": "markdown",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".sql": "sql",
    ".dockerfile": "dockerfile",
}

_GENERATED_PATTERNS = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Pipfile.lock",
    "poetry.lock",
    "Cargo.lock",
    "go.sum",
    "Gemfile.lock",
    "composer.lock",
)
_GENERATED_SUFFIXES = (".min.js", ".min.css", ".generated.ts", ".generated.go", ".pb.go")


def _detect_language(path: str) -> str:
    lower = path.lower()
    if lower.endswith("dockerfile") or lower.startswith("dockerfile"):
        return "dockerfile"
    for ext, lang in _LANGUAGE_MAP.items():
        if lower.endswith(ext):
            return lang
    return ""


def _is_generated_file(path: str) -> bool:
    basename = path.rsplit("/", 1)[-1]
    if basename in _GENERATED_PATTERNS:
        return True
    lower = path.lower()
    return any(lower.endswith(s) for s in _GENERATED_SUFFIXES)


def parse_unified_diff(raw_diff: str) -> list[DiffFile]:
    """Parse a unified diff string into structured DiffFile models."""
    files: list[DiffFile] = []
    current_file: DiffFile | None = None
    current_hunk: DiffHunk | None = None
    old_line = 0
    new_line = 0
    diff_pos = 0
    rename_from: str | None = None
    status = FileDiffStatus.modified

    for raw_line in raw_diff.split("\n"):
        # --- New file header ---
        m = _DIFF_HEADER_RE.match(raw_line)
        if m:
            # Finalize previous file
            if current_file is not None:
                _finalize_file(current_file)
                files.append(current_file)
            _a_path, b_path = m.group(1), m.group(2)
            rename_from = None
            status = FileDiffStatus.modified
            current_file = DiffFile(
                path=b_path,
                status=status,
                language=_detect_language(b_path),
                is_generated=_is_generated_file(b_path),
            )
            current_hunk = None
            diff_pos = 0
            continue

        if current_file is None:
            continue

        # --- Metadata lines ---
        if raw_line.startswith("new file"):
            current_file.status = FileDiffStatus.added
            continue
        if raw_line.startswith("deleted file"):
            current_file.status = FileDiffStatus.deleted
            continue
        rm = _RENAME_FROM_RE.match(raw_line)
        if rm:
            rename_from = rm.group(1)
            continue
        rt = _RENAME_TO_RE.match(raw_line)
        if rt:
            current_file.status = FileDiffStatus.renamed
            current_file.old_path = rename_from
            continue
        if raw_line.startswith("Binary files"):
            continue
        if raw_line.startswith("---") or raw_line.startswith("+++"):
            continue
        if raw_line.startswith("index ") or raw_line.startswith("similarity index"):
            continue

        # --- Hunk header ---
        hm = _HUNK_RE.match(raw_line)
        if hm:
            old_line = int(hm.group(1))
            new_line = int(hm.group(3))
            current_hunk = DiffHunk(
                old_start=old_line,
                old_count=int(hm.group(2) or 1),
                new_start=new_line,
                new_count=int(hm.group(4) or 1),
                header=hm.group(5).strip(),
            )
            current_file.hunks.append(current_hunk)
            diff_pos = 0
            continue

        if current_hunk is None:
            continue

        # --- Diff lines ---
        diff_pos += 1
        if raw_line.startswith("+"):
            line = DiffLine(
                type=DiffLineType.add,
                content=raw_line[1:],
                old_line_no=None,
                new_line_no=new_line,
                diff_position=diff_pos,
            )
            current_file.additions += 1
            new_line += 1
        elif raw_line.startswith("-"):
            line = DiffLine(
                type=DiffLineType.remove,
                content=raw_line[1:],
                old_line_no=old_line,
                new_line_no=None,
                diff_position=diff_pos,
            )
            current_file.deletions += 1
            old_line += 1
        else:
            # Context line (starts with space or is empty)
            content = raw_line[1:] if raw_line.startswith(" ") else raw_line
            line = DiffLine(
                type=DiffLineType.context,
                content=content,
                old_line_no=old_line,
                new_line_no=new_line,
                diff_position=diff_pos,
            )
            old_line += 1
            new_line += 1

        current_hunk.lines.append(line)

    # Finalize last file
    if current_file is not None:
        _finalize_file(current_file)
        files.append(current_file)

    return files


def _finalize_file(f: DiffFile) -> None:
    """Recompute additions/deletions from hunks (already tracked incrementally)."""
    pass  # additions/deletions tracked during parsing


def parse_github_files(files_response: list[dict]) -> list[DiffFile]:
    """Parse GitHub's GET /pulls/{n}/files response into DiffFile models.

    Uses the ``patch`` field from each file entry.
    """
    results: list[DiffFile] = []
    for entry in files_response:
        path = entry.get("filename", "")
        status_str = entry.get("status", "modified")
        status_map = {
            "added": FileDiffStatus.added,
            "removed": FileDiffStatus.deleted,
            "modified": FileDiffStatus.modified,
            "renamed": FileDiffStatus.renamed,
        }
        status = status_map.get(status_str, FileDiffStatus.modified)

        patch = entry.get("patch", "")
        # Parse the patch as a mini unified diff (hunks only, no file header)
        hunks = _parse_patch(patch)

        df = DiffFile(
            path=path,
            status=status,
            hunks=hunks,
            language=_detect_language(path),
            additions=entry.get("additions", 0),
            deletions=entry.get("deletions", 0),
            is_generated=_is_generated_file(path),
            old_path=entry.get("previous_filename"),
        )
        results.append(df)
    return results


def _parse_patch(patch: str) -> list[DiffHunk]:
    """Parse the patch field from a single file (contains hunks only)."""
    if not patch:
        return []
    hunks: list[DiffHunk] = []
    current_hunk: DiffHunk | None = None
    old_line = 0
    new_line = 0
    diff_pos = 0

    for raw_line in patch.split("\n"):
        hm = _HUNK_RE.match(raw_line)
        if hm:
            old_line = int(hm.group(1))
            new_line = int(hm.group(3))
            current_hunk = DiffHunk(
                old_start=old_line,
                old_count=int(hm.group(2) or 1),
                new_start=new_line,
                new_count=int(hm.group(4) or 1),
                header=hm.group(5).strip(),
            )
            hunks.append(current_hunk)
            diff_pos = 0
            continue

        if current_hunk is None:
            continue

        diff_pos += 1
        if raw_line.startswith("+"):
            current_hunk.lines.append(
                DiffLine(
                    type=DiffLineType.add,
                    content=raw_line[1:],
                    old_line_no=None,
                    new_line_no=new_line,
                    diff_position=diff_pos,
                )
            )
            new_line += 1
        elif raw_line.startswith("-"):
            current_hunk.lines.append(
                DiffLine(
                    type=DiffLineType.remove,
                    content=raw_line[1:],
                    old_line_no=old_line,
                    new_line_no=None,
                    diff_position=diff_pos,
                )
            )
            old_line += 1
        else:
            content = raw_line[1:] if raw_line.startswith(" ") else raw_line
            current_hunk.lines.append(
                DiffLine(
                    type=DiffLineType.context,
                    content=content,
                    old_line_no=old_line,
                    new_line_no=new_line,
                    diff_position=diff_pos,
                )
            )
            old_line += 1
            new_line += 1

    return hunks
