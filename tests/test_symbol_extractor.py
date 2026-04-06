"""Tests for symbol extractor (Plan 63-C)."""

from app.reviews.diff_parser import parse_unified_diff
from app.reviews.symbol_extractor import extract_symbols_from_diff

PYTHON_DIFF = """\
diff --git a/app/auth.py b/app/auth.py
--- a/app/auth.py
+++ b/app/auth.py
@@ -1,3 +1,8 @@
+from app.tokens import validate_token
+
+class AuthMiddleware:
+    async def authenticate(self, request: HttpRequest) -> bool:
+        return validate_token(request.headers.get("Authorization"))
"""

JS_DIFF = """\
diff --git a/src/auth.ts b/src/auth.ts
--- a/src/auth.ts
+++ b/src/auth.ts
@@ -1,2 +1,5 @@
+import { validateToken } from './tokens'
+
+export const authenticate = async (req: Request) => {
+    return validateToken(req.headers.get('Authorization'))
+}
"""

GO_DIFF = """\
diff --git a/auth.go b/auth.go
--- a/auth.go
+++ b/auth.go
@@ -1,2 +1,5 @@
+func (s *Server) Authenticate(token string) bool {
+    return ValidateToken(token)
+}
+type AuthConfig struct {
+}
"""


def test_python_symbols():
    files = parse_unified_diff(PYTHON_DIFF)
    symbols = extract_symbols_from_diff(files)
    names = {s.name for s in symbols}
    assert "validate_token" in names
    assert "AuthMiddleware" in names
    assert "authenticate" in names


def test_python_import():
    files = parse_unified_diff(PYTHON_DIFF)
    symbols = extract_symbols_from_diff(files)
    imports = [s for s in symbols if s.kind == "import"]
    assert any(s.name == "validate_token" for s in imports)


def test_python_type_annotation():
    files = parse_unified_diff(PYTHON_DIFF)
    symbols = extract_symbols_from_diff(files)
    types = [s for s in symbols if s.kind == "type"]
    assert any(s.name == "HttpRequest" for s in types)


def test_js_symbols():
    files = parse_unified_diff(JS_DIFF)
    symbols = extract_symbols_from_diff(files)
    names = {s.name for s in symbols}
    assert "authenticate" in names
    assert "validateToken" in names


def test_go_symbols():
    files = parse_unified_diff(GO_DIFF)
    symbols = extract_symbols_from_diff(files)
    names = {s.name for s in symbols}
    assert "Authenticate" in names
    assert "AuthConfig" in names
    assert "ValidateToken" in names


def test_ignores_short_names():
    diff = """\
diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,2 @@
+x = 1
"""
    files = parse_unified_diff(diff)
    symbols = extract_symbols_from_diff(files)
    assert not any(s.name == "x" for s in symbols)


def test_ignores_builtins():
    diff = """\
diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,2 @@
+print(len(items))
"""
    files = parse_unified_diff(diff)
    symbols = extract_symbols_from_diff(files)
    assert not any(s.name == "print" for s in symbols)
    assert not any(s.name == "len" for s in symbols)


def test_dedup():
    diff = """\
diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,3 @@
+validate_token(x)
+validate_token(y)
"""
    files = parse_unified_diff(diff)
    symbols = extract_symbols_from_diff(files)
    count = sum(1 for s in symbols if s.name == "validate_token")
    assert count == 1
