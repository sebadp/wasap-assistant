"""Tests for the unified diff parser (Plan 63-A)."""

from app.reviews.diff_parser import (
    _detect_language,
    _is_generated_file,
    parse_github_files,
    parse_unified_diff,
)
from app.reviews.models import DiffLineType, FileDiffStatus

SAMPLE_DIFF = """\
diff --git a/app/auth.py b/app/auth.py
index abc1234..def5678 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -10,6 +10,8 @@ def authenticate(token):
     if not token:
         return False
+    if token.startswith("Bearer "):
+        token = token[7:]
     return validate(token)

diff --git a/tests/test_auth.py b/tests/test_auth.py
new file mode 100644
--- /dev/null
+++ b/tests/test_auth.py
@@ -0,0 +1,5 @@
+import pytest
+
+def test_auth():
+    assert authenticate("Bearer abc") is True
+    assert authenticate("") is False
"""


def test_parse_two_files():
    files = parse_unified_diff(SAMPLE_DIFF)
    assert len(files) == 2
    assert files[0].path == "app/auth.py"
    assert files[1].path == "tests/test_auth.py"


def test_file_status():
    files = parse_unified_diff(SAMPLE_DIFF)
    assert files[0].status == FileDiffStatus.modified
    assert files[1].status == FileDiffStatus.added


def test_additions_deletions():
    files = parse_unified_diff(SAMPLE_DIFF)
    assert files[0].additions == 2
    assert files[0].deletions == 0
    assert files[1].additions == 5


def test_hunk_lines():
    files = parse_unified_diff(SAMPLE_DIFF)
    hunk = files[0].hunks[0]
    assert hunk.old_start == 10
    assert hunk.new_start == 10
    add_lines = [dl for dl in hunk.lines if dl.type == DiffLineType.add]
    assert len(add_lines) == 2
    assert add_lines[0].content == '    if token.startswith("Bearer "):'


def test_language_detection():
    files = parse_unified_diff(SAMPLE_DIFF)
    assert files[0].language == "python"
    assert files[1].language == "python"


def test_detect_language_helper():
    assert _detect_language("foo.ts") == "typescript"
    assert _detect_language("foo.go") == "go"
    assert _detect_language("Dockerfile") == "dockerfile"
    assert _detect_language("unknown.xyz") == ""


def test_is_generated():
    assert _is_generated_file("package-lock.json")
    assert _is_generated_file("foo.min.js")
    assert not _is_generated_file("app/main.py")


def test_rename_diff():
    diff = """\
diff --git a/old.py b/new.py
similarity index 95%
rename from old.py
rename to new.py
index abc..def 100644
--- a/old.py
+++ b/new.py
@@ -1,3 +1,3 @@
-old_name = True
+new_name = True
"""
    files = parse_unified_diff(diff)
    assert len(files) == 1
    assert files[0].status == FileDiffStatus.renamed
    assert files[0].old_path == "old.py"
    assert files[0].path == "new.py"


def test_parse_github_files():
    response = [
        {
            "filename": "app/main.py",
            "status": "modified",
            "additions": 3,
            "deletions": 1,
            "patch": "@@ -1,3 +1,5 @@\n+import os\n import sys\n-old_line\n+new_line\n+another",
        }
    ]
    files = parse_github_files(response)
    assert len(files) == 1
    assert files[0].path == "app/main.py"
    assert files[0].additions == 3
    assert len(files[0].hunks) == 1
    assert len(files[0].hunks[0].lines) == 5


def test_diff_position_tracking():
    files = parse_unified_diff(SAMPLE_DIFF)
    hunk = files[0].hunks[0]
    # First line is context, position 1
    assert hunk.lines[0].diff_position == 1
    assert hunk.lines[0].type == DiffLineType.context
