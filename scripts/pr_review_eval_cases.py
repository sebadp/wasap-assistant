"""PR Review eval cases — ~50 synthetic diffs for Plan 64 eval dataset.

Each case is a unified diff with known issues (or clean diffs for false positive testing).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _PRCase:
    """Lightweight case struct — converted to EvalCase at import time in seed_eval_dataset."""

    name: str
    diff: str
    section: str
    expected_category: str = ""
    expected_severity: str = ""
    expected_min_findings: int = 1
    expected_max_findings: int = 5
    is_clean: bool = False


# ---------------------------------------------------------------------------
# §pr_review_security — Security vulnerabilities (~10)
# ---------------------------------------------------------------------------

PR_REVIEW_RAW: list[_PRCase] = [
    _PRCase(
        "SQL injection — f-string query",
        """\
--- a/app/db.py
+++ b/app/db.py
@@ -10,6 +10,8 @@ class UserRepo:
     async def get_user(self, user_id: str):
-        query = "SELECT * FROM users WHERE id = ?"
-        return await self.db.execute(query, (user_id,))
+        query = f"SELECT * FROM users WHERE id = '{user_id}'"
+        return await self.db.execute(query)
""",
        "pr_review_security",
        expected_category="security",
        expected_severity="critical",
    ),
    _PRCase(
        "SQL injection — Django raw SQL",
        """\
--- a/views.py
+++ b/views.py
@@ -5,3 +5,5 @@ def search(request):
+    term = request.GET.get("q", "")
+    results = MyModel.objects.raw("SELECT * FROM mymodel WHERE name LIKE '%" + term + "%'")
+    return render(request, "results.html", {"results": results})
""",
        "pr_review_security",
        expected_category="security",
        expected_severity="critical",
    ),
    _PRCase(
        "Command injection — subprocess with user input",
        """\
--- a/utils.py
+++ b/utils.py
@@ -1,4 +1,6 @@
+import subprocess
+
+def compress_file(filename: str):
+    subprocess.run(f"gzip {filename}", shell=True)
""",
        "pr_review_security",
        expected_category="security",
        expected_severity="critical",
    ),
    _PRCase(
        "Command injection — os.system",
        """\
--- a/deploy.py
+++ b/deploy.py
@@ -8,3 +8,5 @@ def deploy(branch: str):
+def cleanup(path: str):
+    os.system(f"rm -rf {path}")
""",
        "pr_review_security",
        expected_category="security",
        expected_severity="critical",
    ),
    _PRCase(
        "Hardcoded API key",
        """\
--- a/config.py
+++ b/config.py
@@ -1,3 +1,5 @@
+STRIPE_SECRET_KEY = "sk_live_FAKE_KEY_FOR_EVAL_TEST_ONLY"
+SENDGRID_API_KEY = "SG.FAKE_KEY_FOR_EVAL_TEST_ONLY"
""",
        "pr_review_security",
        expected_category="security",
        expected_severity="critical",
    ),
    _PRCase(
        "Hardcoded password in default param",
        """\
--- a/auth.py
+++ b/auth.py
@@ -3,4 +3,6 @@ import hashlib
+def create_admin(username: str, password: str = "admin123"):
+    hashed = hashlib.md5(password.encode()).hexdigest()
+    db.execute("INSERT INTO users VALUES (?, ?, 1)", (username, hashed))
""",
        "pr_review_security",
        expected_category="security",
        expected_severity="critical",
    ),
    _PRCase(
        "Path traversal — open with user path",
        """\
--- a/files.py
+++ b/files.py
@@ -5,3 +5,6 @@ from flask import request
+@app.route("/download")
+def download():
+    path = request.args.get("file")
+    return open(f"/data/{path}", "rb").read()
""",
        "pr_review_security",
        expected_category="security",
        expected_severity="critical",
    ),
    _PRCase(
        "Insecure deserialization — pickle.loads",
        """\
--- a/cache.py
+++ b/cache.py
@@ -1,4 +1,7 @@
+import pickle
+
+def load_session(data: bytes):
+    return pickle.loads(data)
""",
        "pr_review_security",
        expected_category="security",
        expected_severity="critical",
    ),
    _PRCase(
        "Eval injection",
        """\
--- a/calc.py
+++ b/calc.py
@@ -3,3 +3,5 @@ from flask import request
+@app.route("/calc")
+def calc():
+    expr = request.form["expression"]
+    return str(eval(expr))
""",
        "pr_review_security",
        expected_category="security",
        expected_severity="critical",
    ),
    _PRCase(
        "JWT without verification",
        """\
--- a/auth.py
+++ b/auth.py
@@ -8,4 +8,6 @@ import jwt
+def get_user_from_token(token: str):
+    payload = jwt.decode(token, options={"verify_signature": False})
+    return payload["user_id"]
""",
        "pr_review_security",
        expected_category="security",
        expected_severity="critical",
    ),

    # ---------------------------------------------------------------------------
    # §pr_review_bugs — Bug patterns (~10)
    # ---------------------------------------------------------------------------
    _PRCase(
        "Off-by-one — range loses last element",
        """\
--- a/process.py
+++ b/process.py
@@ -5,4 +5,6 @@ def process_items(items):
+def validate_all(items):
+    for i in range(len(items) - 1):
+        if not items[i].is_valid():
+            return False
+    return True
""",
        "pr_review_bugs",
        expected_category="bug",
        expected_severity="warning",
    ),
    _PRCase(
        "Null dereference — .get() without default then .strip()",
        """\
--- a/parse.py
+++ b/parse.py
@@ -3,3 +3,5 @@ def parse_header(headers: dict):
+    content_type = headers.get("Content-Type")
+    return content_type.strip().lower()
""",
        "pr_review_bugs",
        expected_category="bug",
        expected_severity="warning",
    ),
    _PRCase(
        "Type mismatch — int compared with str",
        """\
--- a/check.py
+++ b/check.py
@@ -1,3 +1,6 @@
+def check_age(form_data: dict):
+    age = form_data.get("age")  # str from form
+    if age > 18:
+        return "adult"
+    return "minor"
""",
        "pr_review_bugs",
        expected_category="bug",
        expected_severity="warning",
    ),
    _PRCase(
        "Race condition — check-then-act on file",
        """\
--- a/upload.py
+++ b/upload.py
@@ -5,3 +5,7 @@ import os
+def save_upload(path: str, data: bytes):
+    if not os.path.exists(path):
+        with open(path, "wb") as f:
+            f.write(data)
+    else:
+        raise FileExistsError(path)
""",
        "pr_review_bugs",
        expected_category="bug",
        expected_severity="suggestion",
    ),
    _PRCase(
        "Resource leak — open without context manager",
        """\
--- a/reader.py
+++ b/reader.py
@@ -1,3 +1,6 @@
+def read_config(path: str) -> dict:
+    f = open(path)
+    data = json.load(f)
+    return data
""",
        "pr_review_bugs",
        expected_category="bug",
        expected_severity="warning",
    ),
    _PRCase(
        "Logic error — and where should be or",
        """\
--- a/auth.py
+++ b/auth.py
@@ -10,4 +10,6 @@ def check_access(user):
+def is_authorized(user, resource):
+    if user.role == "admin" and user.role == "superadmin":
+        return True
+    return False
""",
        "pr_review_bugs",
        expected_category="bug",
        expected_severity="warning",
    ),
    _PRCase(
        "Division by zero — no check",
        """\
--- a/stats.py
+++ b/stats.py
@@ -3,3 +3,5 @@ def compute_stats(values: list[float]):
+def average(values: list[float]) -> float:
+    total = sum(values)
+    return total / len(values)
""",
        "pr_review_bugs",
        expected_category="bug",
        expected_severity="warning",
    ),
    _PRCase(
        "Infinite loop — condition never updated",
        """\
--- a/poll.py
+++ b/poll.py
@@ -1,3 +1,7 @@
+def wait_for_ready(client):
+    ready = False
+    while not ready:
+        status = client.get_status()
+        if status == "done":
+            return status
""",
        "pr_review_bugs",
        expected_category="bug",
        expected_severity="warning",
    ),
    _PRCase(
        "Wrong variable returned — shadow",
        """\
--- a/transform.py
+++ b/transform.py
@@ -1,3 +1,7 @@
+def transform(data: list) -> list:
+    result = []
+    for item in data:
+        transformed = item.upper()
+        result.append(transformed)
+    return data  # should be result
""",
        "pr_review_bugs",
        expected_category="bug",
        expected_severity="warning",
    ),
    _PRCase(
        "Missing await on async function",
        """\
--- a/service.py
+++ b/service.py
@@ -5,3 +5,6 @@ class UserService:
+    async def create_and_notify(self, user_data: dict):
+        user = await self.repo.create(user_data)
+        self.notifier.send_welcome(user)  # send_welcome is async
+        return user
""",
        "pr_review_bugs",
        expected_category="bug",
        expected_severity="warning",
    ),

    # ---------------------------------------------------------------------------
    # §pr_review_performance — Performance issues (~5)
    # ---------------------------------------------------------------------------
    _PRCase(
        "N+1 query — SELECT in loop",
        """\
--- a/report.py
+++ b/report.py
@@ -3,3 +3,7 @@ def generate_report(order_ids: list[int]):
+    results = []
+    for oid in order_ids:
+        order = db.execute("SELECT * FROM orders WHERE id = ?", (oid,)).fetchone()
+        customer = db.execute("SELECT * FROM customers WHERE id = ?", (order["customer_id"],)).fetchone()
+        results.append({"order": order, "customer": customer})
+    return results
""",
        "pr_review_performance",
        expected_category="performance",
        expected_severity="warning",
    ),
    _PRCase(
        "Unbounded SELECT — no LIMIT",
        """\
--- a/export.py
+++ b/export.py
@@ -1,3 +1,5 @@
+def export_all_logs():
+    rows = db.execute("SELECT * FROM audit_logs").fetchall()
+    return [dict(r) for r in rows]
""",
        "pr_review_performance",
        expected_category="performance",
        expected_severity="warning",
    ),
    _PRCase(
        "Sync I/O in async — requests.get in async func",
        """\
--- a/fetcher.py
+++ b/fetcher.py
@@ -1,4 +1,7 @@
+import requests
+
+async def fetch_data(url: str):
+    resp = requests.get(url)
+    return resp.json()
""",
        "pr_review_performance",
        expected_category="performance",
        expected_severity="warning",
    ),
    _PRCase(
        "Quadratic — nested loop with list lookup",
        """\
--- a/dedup.py
+++ b/dedup.py
@@ -1,3 +1,7 @@
+def find_duplicates(items: list[str]) -> list[str]:
+    dupes = []
+    for i, a in enumerate(items):
+        for j, b in enumerate(items):
+            if i != j and a == b and a not in dupes:
+                dupes.append(a)
+    return dupes
""",
        "pr_review_performance",
        expected_category="performance",
        expected_severity="warning",
    ),
    _PRCase(
        "Repeated DB query in loop without cache",
        """\
--- a/render.py
+++ b/render.py
@@ -3,3 +3,7 @@ def render_dashboard(widgets: list[dict]):
+    for widget in widgets:
+        settings = db.execute("SELECT * FROM settings WHERE key = 'dashboard'").fetchone()
+        widget["theme"] = settings["theme"]
+    return widgets
""",
        "pr_review_performance",
        expected_category="performance",
        expected_severity="warning",
    ),

    # ---------------------------------------------------------------------------
    # §pr_review_error_handling (~5)
    # ---------------------------------------------------------------------------
    _PRCase(
        "Bare except — silences everything",
        """\
--- a/worker.py
+++ b/worker.py
@@ -5,3 +5,7 @@ def process_task(task):
+    try:
+        result = heavy_computation(task)
+        save_result(result)
+    except:
+        pass
""",
        "pr_review_error_handling",
        expected_category="error_handling",
        expected_severity="warning",
    ),
    _PRCase(
        "Swallowed exception — except returns None",
        """\
--- a/parser.py
+++ b/parser.py
@@ -1,3 +1,6 @@
+def parse_config(path: str) -> dict | None:
+    try:
+        return json.loads(open(path).read())
+    except Exception:
+        return None
""",
        "pr_review_error_handling",
        expected_category="error_handling",
        expected_severity="warning",
    ),
    _PRCase(
        "Missing error handling on user file path",
        """\
--- a/importer.py
+++ b/importer.py
@@ -5,3 +5,5 @@ def import_data(user_path: str):
+    with open(user_path) as f:
+        data = json.load(f)
+    return process(data)
""",
        "pr_review_error_handling",
        expected_category="error_handling",
        expected_severity="suggestion",
    ),
    _PRCase(
        "Error message leaks stack trace",
        """\
--- a/api.py
+++ b/api.py
@@ -10,4 +10,8 @@ @app.route("/process")
+def process():
+    try:
+        result = do_work(request.json)
+        return jsonify(result)
+    except Exception as e:
+        return jsonify({"error": traceback.format_exc()}), 500
""",
        "pr_review_error_handling",
        expected_category="error_handling",
        expected_severity="warning",
    ),
    _PRCase(
        "Unchecked subprocess return",
        """\
--- a/build.py
+++ b/build.py
@@ -3,3 +3,5 @@ import subprocess
+def build_project(path: str):
+    subprocess.run(["make", "-C", path, "build"])
+    subprocess.run(["make", "-C", path, "install"])
""",
        "pr_review_error_handling",
        expected_category="error_handling",
        expected_severity="suggestion",
    ),

    # ---------------------------------------------------------------------------
    # §pr_review_maintainability (~5)
    # ---------------------------------------------------------------------------
    _PRCase(
        "Deep nesting — 5 levels",
        """\
--- a/handler.py
+++ b/handler.py
@@ -1,3 +1,15 @@
+def handle_event(event):
+    if event.type == "message":
+        if event.channel == "main":
+            if event.user:
+                if event.user.is_active:
+                    if not event.user.is_banned:
+                        process_message(event)
+                    else:
+                        log.warn("banned")
+                else:
+                    log.warn("inactive")
+            else:
+                log.warn("no user")
""",
        "pr_review_maintainability",
        expected_category="maintainability",
        expected_severity="suggestion",
    ),
    _PRCase(
        "Copy-paste duplication",
        """\
--- a/validators.py
+++ b/validators.py
@@ -1,3 +1,18 @@
+def validate_email(email: str) -> bool:
+    if not email:
+        return False
+    if "@" not in email:
+        return False
+    if len(email) > 254:
+        return False
+    return True
+
+def validate_username(username: str) -> bool:
+    if not username:
+        return False
+    if "@" not in username:
+        return False
+    if len(username) > 254:
+        return False
+    return True
""",
        "pr_review_maintainability",
        expected_category="maintainability",
        expected_severity="suggestion",
    ),
    _PRCase(
        "Misleading name — get_user modifies DB",
        """\
--- a/users.py
+++ b/users.py
@@ -5,3 +5,8 @@ class UserService:
+    def get_user(self, user_id: int):
+        user = self.db.query(User).get(user_id)
+        user.last_accessed = datetime.now()
+        self.db.commit()
+        return user
""",
        "pr_review_maintainability",
        expected_category="maintainability",
        expected_severity="suggestion",
    ),
    _PRCase(
        "Magic numbers without explanation",
        """\
--- a/retry.py
+++ b/retry.py
@@ -1,3 +1,8 @@
+def retry_request(url: str):
+    for i in range(7):
+        resp = requests.get(url, timeout=3.7)
+        if resp.status_code < 429:
+            return resp
+        time.sleep(2 ** i * 0.37)
+    raise TimeoutError()
""",
        "pr_review_maintainability",
        expected_category="maintainability",
        expected_severity="nitpick",
    ),
    _PRCase(
        "God function — too many responsibilities",
        """\
--- a/pipeline.py
+++ b/pipeline.py
@@ -1,3 +1,25 @@
+def process_order(order_data: dict):
+    # Validate
+    if not order_data.get("items"):
+        raise ValueError("No items")
+    if not order_data.get("customer_id"):
+        raise ValueError("No customer")
+    # Calculate totals
+    subtotal = sum(i["price"] * i["qty"] for i in order_data["items"])
+    tax = subtotal * 0.21
+    total = subtotal + tax
+    # Create record
+    order = db.execute("INSERT INTO orders ...", (total,))
+    # Send notification
+    email = get_customer_email(order_data["customer_id"])
+    send_email(email, f"Order {order.id} confirmed: ${total}")
+    # Update inventory
+    for item in order_data["items"]:
+        db.execute("UPDATE inventory SET stock = stock - ? WHERE id = ?", (item["qty"], item["id"]))
+    # Log
+    audit_log.info(f"Order {order.id} processed for {total}")
+    # Return
+    return {"order_id": order.id, "total": total}
""",
        "pr_review_maintainability",
        expected_category="maintainability",
        expected_severity="suggestion",
    ),

    # ---------------------------------------------------------------------------
    # §pr_review_clean — False positive testing (~15)
    # Reviewer should return [] for these
    # ---------------------------------------------------------------------------
    _PRCase(
        "Clean — variable rename",
        """\
--- a/utils.py
+++ b/utils.py
@@ -5,4 +5,4 @@ def process(data):
-    tmp = data.strip()
-    return tmp.lower()
+    cleaned = data.strip()
+    return cleaned.lower()
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — add docstring",
        """\
--- a/utils.py
+++ b/utils.py
@@ -1,3 +1,6 @@
 def process(data: str) -> str:
+    \"\"\"Process the input data by stripping and lowering.
+
+    Args:
+        data: Raw input string.
+    \"\"\"
     return data.strip().lower()
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — formatting change",
        """\
--- a/config.py
+++ b/config.py
@@ -1,5 +1,5 @@
-SETTINGS = {"debug":True,"verbose":False,"timeout":30}
+SETTINGS = {
+    "debug": True,
+    "verbose": False,
+    "timeout": 30,
+}
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — add type hints",
        """\
--- a/math.py
+++ b/math.py
@@ -1,4 +1,4 @@
-def add(a, b):
+def add(a: int, b: int) -> int:
     return a + b
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — add test file",
        """\
--- /dev/null
+++ b/tests/test_utils.py
@@ -0,0 +1,8 @@
+import pytest
+from app.utils import process
+
+def test_process_strips():
+    assert process("  hello  ") == "hello"
+
+def test_process_lowers():
+    assert process("HELLO") == "hello"
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — add TODO comment",
        """\
--- a/api.py
+++ b/api.py
@@ -10,3 +10,4 @@ def get_users():
     users = db.query(User).all()
+    # TODO: add pagination
     return jsonify([u.to_dict() for u in users])
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — import reorder",
        """\
--- a/main.py
+++ b/main.py
@@ -1,4 +1,4 @@
-import os
 import json
+import os
 import sys
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — update dependency version",
        """\
--- a/requirements.txt
+++ b/requirements.txt
@@ -3,3 +3,3 @@
-flask==2.3.0
+flask==3.0.1
 requests==2.31.0
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — change log message",
        """\
--- a/worker.py
+++ b/worker.py
@@ -8,3 +8,3 @@ def run_task(task):
-    logger.info("Task started: %s", task.id)
+    logger.info("Processing task %s (priority=%s)", task.id, task.priority)
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — add .gitignore entry",
        """\
--- a/.gitignore
+++ b/.gitignore
@@ -5,3 +5,4 @@
 *.pyc
 __pycache__/
+.coverage
 .env
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — update README",
        """\
--- a/README.md
+++ b/README.md
@@ -1,3 +1,5 @@
 # My Project

-A simple web app.
+A web application for managing tasks.
+
+## Getting Started
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — add empty __init__.py",
        """\
--- /dev/null
+++ b/app/utils/__init__.py
@@ -0,0 +1 @@
+
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — increase timeout constant",
        """\
--- a/config.py
+++ b/config.py
@@ -5,3 +5,3 @@
-REQUEST_TIMEOUT = 10
+REQUEST_TIMEOUT = 30
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — rename file via move",
        """\
--- a/helpers.py
+++ /dev/null
@@ -1,5 +0,0 @@
-def helper():
-    pass
--- /dev/null
+++ b/utils/helpers.py
@@ -0,0 +1,5 @@
+def helper():
+    pass
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
    _PRCase(
        "Clean — remove debug print",
        """\
--- a/process.py
+++ b/process.py
@@ -5,4 +5,3 @@ def run(data):
     result = transform(data)
-    print(f"DEBUG: result = {result}")
     return result
""",
        "pr_review_clean",
        is_clean=True,
        expected_max_findings=0,
        expected_min_findings=0,
    ),
]
