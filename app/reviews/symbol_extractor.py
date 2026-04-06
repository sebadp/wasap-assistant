"""Extract symbols from diffs for cross-file search (Plan 63-C).

Analyzes added lines to find definitions, imports, function calls, and types.
"""

from __future__ import annotations

import re

from app.reviews.models import DiffFile, DiffLineType, SymbolUsage

# ---------------------------------------------------------------------------
# Language-specific regex patterns (applied to added lines only)
# ---------------------------------------------------------------------------

_PYTHON_DEF = re.compile(r"(?:async\s+)?def\s+(\w+)")
_PYTHON_CLASS = re.compile(r"class\s+(\w+)")
_PYTHON_IMPORT = re.compile(r"(?:from\s+\S+\s+)?import\s+(.+)")
_PYTHON_TYPE = re.compile(r"(?:->|:)\s*(\w+)")

_JS_FUNCTION = re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)")
_JS_CONST = re.compile(r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=")
_JS_IMPORT = re.compile(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]")
_JS_CLASS = re.compile(r"class\s+(\w+)")

_GO_FUNC = re.compile(r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)")
_GO_TYPE = re.compile(r"type\s+(\w+)\s+struct")

_RUST_FN = re.compile(r"(?:pub\s+)?fn\s+(\w+)")
_RUST_STRUCT = re.compile(r"(?:pub\s+)?struct\s+(\w+)")

_CALL_RE = re.compile(r"(\w{3,})\s*\(")

# Built-ins and common names to ignore
_IGNORE = frozenset(
    {
        "self",
        "cls",
        "None",
        "True",
        "False",
        "print",
        "len",
        "str",
        "int",
        "float",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
        "type",
        "range",
        "super",
        "isinstance",
        "issubclass",
        "hasattr",
        "getattr",
        "setattr",
        "open",
        "map",
        "filter",
        "zip",
        "enumerate",
        "sorted",
        "reversed",
        "any",
        "all",
        "min",
        "max",
        "sum",
        "abs",
        "round",
        "id",
        "hash",
        "if",
        "else",
        "elif",
        "for",
        "while",
        "return",
        "yield",
        "with",
        "try",
        "except",
        "finally",
        "raise",
        "assert",
        "pass",
        "break",
        "continue",
        "import",
        "from",
        "as",
        "in",
        "not",
        "and",
        "or",
        "is",
        "async",
        "await",
        "def",
        "class",
        "lambda",
        "const",
        "let",
        "var",
        "function",
        "export",
        "default",
        "new",
        "require",
        "module",
        "console",
        "log",
        "error",
        "warn",
        "null",
        "undefined",
        "true",
        "false",
        "this",
        "that",
        "func",
        "package",
        "main",
        "fmt",
        "err",
        "fn",
        "pub",
        "mut",
        "impl",
        "use",
        "mod",
        "crate",
        "test",
        "describe",
        "expect",
    }
)


def extract_symbols_from_diff(files: list[DiffFile]) -> list[SymbolUsage]:
    """Extract symbols from added lines in diff files."""
    symbols: dict[str, SymbolUsage] = {}  # dedup by name

    for f in files:
        lang = f.language
        for hunk in f.hunks:
            for line in hunk.lines:
                if line.type != DiffLineType.add:
                    continue
                content = line.content
                line_no = line.new_line_no or 0

                found = _extract_from_line(content, lang, f.path, line_no)
                for sym in found:
                    if sym.name not in symbols:
                        symbols[sym.name] = sym

    return list(symbols.values())


def _extract_from_line(content: str, lang: str, path: str, line_no: int) -> list[SymbolUsage]:
    """Extract symbols from a single added line."""
    results: list[SymbolUsage] = []
    stripped = content.strip()

    if lang == "python":
        results.extend(_extract_python(stripped, path, line_no))
    elif lang in ("javascript", "typescript"):
        results.extend(_extract_js(stripped, path, line_no))
    elif lang == "go":
        results.extend(_extract_go(stripped, path, line_no))
    elif lang == "rust":
        results.extend(_extract_rust(stripped, path, line_no))

    # Generic: function calls (any language)
    for m in _CALL_RE.finditer(stripped):
        name = m.group(1)
        if _is_valid_symbol(name) and not any(s.name == name for s in results):
            results.append(
                SymbolUsage(name=name, kind="call", source_path=path, source_line=line_no)
            )

    return [s for s in results if _is_valid_symbol(s.name)]


def _extract_python(line: str, path: str, line_no: int) -> list[SymbolUsage]:
    results: list[SymbolUsage] = []
    m = _PYTHON_DEF.search(line)
    if m:
        results.append(
            SymbolUsage(name=m.group(1), kind="function", source_path=path, source_line=line_no)
        )
    m = _PYTHON_CLASS.search(line)
    if m:
        results.append(
            SymbolUsage(name=m.group(1), kind="class", source_path=path, source_line=line_no)
        )
    m = _PYTHON_IMPORT.search(line)
    if m:
        for name in m.group(1).split(","):
            name = name.strip().split(" as ")[0].strip()
            if _is_valid_symbol(name):
                results.append(
                    SymbolUsage(name=name, kind="import", source_path=path, source_line=line_no)
                )
    for m in _PYTHON_TYPE.finditer(line):
        name = m.group(1)
        if _is_valid_symbol(name) and name[0].isupper():
            results.append(
                SymbolUsage(name=name, kind="type", source_path=path, source_line=line_no)
            )
    return results


def _extract_js(line: str, path: str, line_no: int) -> list[SymbolUsage]:
    results: list[SymbolUsage] = []
    m = _JS_FUNCTION.search(line)
    if m:
        results.append(
            SymbolUsage(name=m.group(1), kind="function", source_path=path, source_line=line_no)
        )
    m = _JS_CONST.search(line)
    if m:
        results.append(
            SymbolUsage(name=m.group(1), kind="variable", source_path=path, source_line=line_no)
        )
    m = _JS_CLASS.search(line)
    if m:
        results.append(
            SymbolUsage(name=m.group(1), kind="class", source_path=path, source_line=line_no)
        )
    m = _JS_IMPORT.search(line)
    if m:
        results.append(
            SymbolUsage(name=m.group(1), kind="import", source_path=path, source_line=line_no)
        )
    return results


def _extract_go(line: str, path: str, line_no: int) -> list[SymbolUsage]:
    results: list[SymbolUsage] = []
    m = _GO_FUNC.search(line)
    if m:
        results.append(
            SymbolUsage(name=m.group(1), kind="function", source_path=path, source_line=line_no)
        )
    m = _GO_TYPE.search(line)
    if m:
        results.append(
            SymbolUsage(name=m.group(1), kind="class", source_path=path, source_line=line_no)
        )
    return results


def _extract_rust(line: str, path: str, line_no: int) -> list[SymbolUsage]:
    results: list[SymbolUsage] = []
    m = _RUST_FN.search(line)
    if m:
        results.append(
            SymbolUsage(name=m.group(1), kind="function", source_path=path, source_line=line_no)
        )
    m = _RUST_STRUCT.search(line)
    if m:
        results.append(
            SymbolUsage(name=m.group(1), kind="class", source_path=path, source_line=line_no)
        )
    return results


def _is_valid_symbol(name: str) -> bool:
    """Filter out noise: short names, built-ins, primitives."""
    if len(name) <= 2:
        return False
    if name in _IGNORE:
        return False
    if name.startswith("_"):
        return False
    return True
