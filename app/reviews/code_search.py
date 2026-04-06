"""Code search engine — grep + glob over local clone (Plan 63-C).

Inspired by Claude Code: no embeddings, just ripgrep + glob for code intelligence.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from app.reviews.models import CodeReference, DiffFile, SymbolUsage

logger = logging.getLogger(__name__)

_EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "vendor",
    "dist",
    "build",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "target",
    ".next",
}

_DEF_PATTERNS = {
    "python": r"(?:async\s+)?def\s+{name}\b|class\s+{name}\b",
    "javascript": r"(?:function|const|let|var|class)\s+{name}\b",
    "typescript": r"(?:function|const|let|var|class|interface|type)\s+{name}\b",
    "go": r"func\s+(?:\([^)]*\)\s+)?{name}\b|type\s+{name}\b",
    "rust": r"(?:pub\s+)?(?:fn|struct|enum|trait)\s+{name}\b",
}

_TEST_GLOBS = (
    "tests/**/test_*.py",
    "tests/**/*_test.py",
    "**/*.test.ts",
    "**/*.test.js",
    "**/*.test.tsx",
    "**/*.test.jsx",
    "**/*.spec.ts",
    "**/*.spec.js",
    "**/*_test.go",
    "tests/**/*.rs",
)


async def _run_rg(args: list[str], cwd: Path, timeout: int = 10) -> str:
    """Run ripgrep with fallback to grep."""
    exclude_args: list[str] = []
    for d in _EXCLUDE_DIRS:
        exclude_args.extend(["--glob", f"!{d}"])

    try:
        proc = await asyncio.create_subprocess_exec(
            "rg",
            *exclude_args,
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode(errors="replace")
    except FileNotFoundError:
        # Fallback to grep
        grep_args = ["grep", "-rn", "--include=*"]
        # Extract pattern (last positional arg before flags)
        pattern = args[-1] if args else ""
        proc = await asyncio.create_subprocess_exec(
            *grep_args,
            pattern,
            ".",
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return stdout.decode(errors="replace")
    except TimeoutError:
        logger.warning("Search timed out after %ds", timeout)
        return ""


def _parse_rg_output(output: str, clone_path: Path) -> list[tuple[str, int, str]]:
    """Parse ripgrep output into (path, line_no, content) tuples."""
    results: list[tuple[str, int, str]] = []
    for line in output.strip().split("\n"):
        if not line:
            continue
        # rg format: path:line:content
        parts = line.split(":", 2)
        if len(parts) >= 3:
            path = parts[0]
            try:
                line_no = int(parts[1])
            except ValueError:
                continue
            content = parts[2]
            results.append((path, line_no, content))
    return results


def _read_context(clone_path: Path, path: str, center_line: int, context: int = 5) -> str:
    """Read lines around a match for context."""
    file_path = clone_path / path
    if not file_path.is_file():
        return ""
    try:
        lines = file_path.read_text(errors="replace").split("\n")
    except OSError:
        return ""
    start = max(0, center_line - context - 1)
    end = min(len(lines), center_line + context)
    return "\n".join(lines[start:end])


def _classify_match(path: str, content: str, symbol_name: str) -> str:
    """Classify a grep match as definition, usage, import, test, or related."""
    lower = content.lower()
    # Test files
    if "/test" in path or "test_" in path or ".test." in path or ".spec." in path:
        return "test"
    # Definition patterns
    def_keywords = (
        "def ",
        "class ",
        "function ",
        "func ",
        "const ",
        "let ",
        "var ",
        "type ",
        "struct ",
        "enum ",
        "trait ",
        "interface ",
    )
    for kw in def_keywords:
        if kw in lower and symbol_name in content:
            return "definition"
    # Import
    if "import" in lower or "from" in lower or "require" in lower or "use " in lower:
        return "import"
    return "usage"


async def find_references(
    symbol: SymbolUsage,
    clone_path: Path,
    exclude_file: str = "",
    max_results: int = 10,
) -> list[CodeReference]:
    """Find references to a symbol in the clone via grep."""
    output = await _run_rg(
        ["-n", "--no-heading", "-w", symbol.name],
        cwd=clone_path,
    )
    matches = _parse_rg_output(output, clone_path)

    refs: list[CodeReference] = []
    for path, line_no, content in matches:
        if exclude_file and path == exclude_file:
            continue
        match_type = _classify_match(path, content, symbol.name)
        ctx = _read_context(clone_path, path, line_no)
        refs.append(
            CodeReference(
                path=path,
                start_line=max(1, line_no - 5),
                end_line=line_no + 5,
                content=ctx,
                match_type=match_type,
                symbol=symbol.name,
            )
        )
        if len(refs) >= max_results:
            break
    return refs


async def find_definitions(
    symbol_name: str,
    clone_path: Path,
    language: str = "",
) -> list[CodeReference]:
    """Find definitions of a symbol using language-aware patterns."""
    pattern = _DEF_PATTERNS.get(language, "")
    if pattern:
        pattern = pattern.format(name=re.escape(symbol_name))
    else:
        # Generic: any common def keyword
        pattern = (
            rf"(?:def|class|function|func|const|type|struct|interface)\s+{re.escape(symbol_name)}\b"
        )

    output = await _run_rg(
        ["-n", "--no-heading", "-e", pattern],
        cwd=clone_path,
    )
    matches = _parse_rg_output(output, clone_path)

    refs: list[CodeReference] = []
    for path, line_no, _content in matches:
        ctx = _read_context(clone_path, path, line_no, context=10)
        refs.append(
            CodeReference(
                path=path,
                start_line=max(1, line_no - 2),
                end_line=line_no + 10,
                content=ctx,
                match_type="definition",
                symbol=symbol_name,
            )
        )
    return refs


async def find_tests(
    file_path: str,
    clone_path: Path,
) -> list[CodeReference]:
    """Find test files related to a changed file."""
    # Extract module name from path
    stem = Path(file_path).stem  # e.g. "auth" from "app/auth.py"

    output = await _run_rg(
        ["-n", "--no-heading", "-l", "-w", stem],
        cwd=clone_path,
    )
    refs: list[CodeReference] = []
    for line in output.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Only test files
        if not any(p in line for p in ("test_", "_test.", ".test.", ".spec.")):
            continue
        refs.append(
            CodeReference(
                path=line,
                start_line=1,
                end_line=1,
                content=f"Test file related to {file_path}",
                match_type="test",
                symbol=stem,
            )
        )
        if len(refs) >= 5:
            break
    return refs


async def find_related_files(
    file_path: str,
    clone_path: Path,
) -> list[str]:
    """Find files related to a changed file (similar names, importers)."""
    stem = Path(file_path).stem
    related: list[str] = []

    # Glob for similar names
    for entry in clone_path.rglob(f"*{stem}*"):
        if entry.is_file() and str(entry.relative_to(clone_path)) != file_path:
            rel = str(entry.relative_to(clone_path))
            if not any(d in rel for d in _EXCLUDE_DIRS):
                related.append(rel)
                if len(related) >= 10:
                    break

    return related


# ---------------------------------------------------------------------------
# C5: Assemble cross-file context
# ---------------------------------------------------------------------------

_CHARS_PER_TOKEN = 3.5


async def get_cross_file_context(
    diff_file: DiffFile,
    symbols: list[SymbolUsage],
    clone_path: Path,
    token_budget: int = 3000,
) -> str:
    """Build cross-file context for a file review.

    Searches the clone for definitions, usages, and tests of symbols
    found in the diff. Returns formatted XML blocks.
    """
    from app.tracing.context import get_current_trace

    trace = get_current_trace()
    all_refs: list[CodeReference] = []

    for sym in symbols:
        if sym.source_path != diff_file.path:
            continue

        # Find definitions
        defs = await find_definitions(sym.name, clone_path, diff_file.language)
        for ref in defs:
            if ref.path != diff_file.path:
                all_refs.append(ref)

        # Find references/usages
        usages = await find_references(sym, clone_path, exclude_file=diff_file.path, max_results=5)
        all_refs.extend(usages)

    # Find tests for the file
    tests = await find_tests(diff_file.path, clone_path)
    all_refs.extend(tests)

    if not all_refs:
        return ""

    # Dedup by path+symbol
    seen: set[str] = set()
    unique: list[CodeReference] = []
    for ref in all_refs:
        key = f"{ref.path}:{ref.symbol}:{ref.match_type}"
        if key not in seen:
            seen.add(key)
            unique.append(ref)

    # Sort: definitions > usages > tests > related
    priority = {"definition": 0, "import": 1, "usage": 2, "test": 3, "related": 4}
    unique.sort(key=lambda r: priority.get(r.match_type, 99))

    # Format and truncate to budget
    char_budget = int(token_budget * _CHARS_PER_TOKEN)
    parts = ["<cross_file_context>"]
    used = len(parts[0])

    for ref in unique:
        block = (
            f'\n<reference type="{ref.match_type}" symbol="{ref.symbol}" '
            f'path="{ref.path}" lines="{ref.start_line}-{ref.end_line}">\n'
            f"{ref.content}\n"
            f"</reference>"
        )
        if used + len(block) > char_budget:
            break
        parts.append(block)
        used += len(block)

    parts.append("\n</cross_file_context>")
    result = "\n".join(parts)

    if trace:
        async with trace.span("pr_review.cross_file_context") as span:
            span.set_output({
                "symbols_searched": len([s for s in symbols if s.source_path == diff_file.path]),
                "refs_found": len(unique),
                "context_chars": len(result),
            })

    return result
