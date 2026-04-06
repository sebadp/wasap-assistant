# PRP: PR Review Phase A — Core Review Engine (Plan 63-A)

## Archivos a Modificar

| Archivo | Cambio |
|---------|--------|
| `app/reviews/__init__.py` | **Nuevo** — package init |
| `app/reviews/models.py` | **Nuevo** — Todos los dataclasses del dominio |
| `app/reviews/providers/__init__.py` | **Nuevo** — package init |
| `app/reviews/providers/base.py` | **Nuevo** — `SCMProvider` Protocol + modelos compartidos |
| `app/reviews/providers/github.py` | **Nuevo** — GitHub REST API implementation |
| `app/reviews/providers/factory.py` | **Nuevo** — Factory: URL → provider |
| `app/reviews/diff_parser.py` | **Nuevo** — Unified diff parser → modelos estructurados |
| `app/reviews/reviewer.py` | **Nuevo** — LLM review pipeline (summary + line-by-line) |
| `app/reviews/formatter.py` | **Nuevo** — WhatsApp formatting del review |
| `app/commands/builtins.py` | Agregar `cmd_pr_review` + registrar `/pr-review` |
| `app/commands/context.py` | Agregar `settings` access (ya existe) |
| `app/config.py` | Settings: `pr_review_*` config |
| `.env.example` | Documentar settings |
| `Makefile` | (no necesario — es un command, no un script) |
| `tests/test_diff_parser.py` | **Nuevo** — Tests del diff parser |
| `tests/test_review_models.py` | **Nuevo** — Tests de modelos |
| `tests/test_review_github.py` | **Nuevo** — Tests del GitHub provider (mocked) |
| `tests/test_review_pipeline.py` | **Nuevo** — Tests del reviewer (mocked LLM) |
| `tests/test_review_formatter.py` | **Nuevo** — Tests del formatter |
| `docs/features/63-pr_review.md` | Feature doc |
| `docs/testing/63-pr_review_testing.md` | Testing doc |

## Fases de Implementación

### Phase 1: Domain Models (`app/reviews/models.py`)

Los modelos son el corazón del diseño. Se definen primero porque todo depende de ellos.

- [x] `Severity` enum: `critical`, `warning`, `suggestion`, `nitpick`
- [x] `Category` enum: `security`, `bug`, `performance`, `error_handling`, `maintainability`, `style`, `test_coverage`, `documentation`
- [x] `RiskLevel` enum: `low`, `medium`, `high`, `critical`
- [x] `DiffLineType` enum: `context`, `add`, `remove`
- [x] `FileDiffStatus` enum: `added`, `modified`, `deleted`, `renamed`
- [x] `DiffLine` dataclass:
  ```python
  @dataclass
  class DiffLine:
      type: DiffLineType
      content: str
      old_line_no: int | None  # None for added lines
      new_line_no: int | None  # None for deleted lines
      diff_position: int       # 1-indexed position in the diff hunk (for GitHub API)
  ```
- [x] `DiffHunk` dataclass:
  ```python
  @dataclass
  class DiffHunk:
      old_start: int
      old_count: int
      new_start: int
      new_count: int
      header: str             # function/class context after @@
      lines: list[DiffLine]
  ```
- [x] `DiffFile` dataclass:
  ```python
  @dataclass
  class DiffFile:
      path: str
      status: FileDiffStatus
      hunks: list[DiffHunk]
      language: str           # Detected from extension
      additions: int
      deletions: int
      is_generated: bool      # Lockfiles, .min.js, etc.
      old_path: str | None    # For renames
  ```
- [x] `PullRequestInfo` dataclass:
  ```python
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
      commit_sha: str         # HEAD commit for review
  ```
- [x] `ReviewFinding` dataclass:
  ```python
  @dataclass
  class ReviewFinding:
      path: str
      line: int
      side: str               # "RIGHT" (new) or "LEFT" (old)
      severity: Severity
      category: Category
      body: str               # Markdown comment body
      suggestion: str | None  # Concrete code fix suggestion
      confidence: float       # 0.0-1.0, used for filtering
      start_line: int | None  # For multi-line comments
  ```
- [x] `ReviewSummary` dataclass:
  ```python
  @dataclass
  class ReviewSummary:
      title: str              # One-line summary
      overview: str           # 2-3 sentence description
      risk_level: RiskLevel
      key_changes: list[str]  # Bullet points
      stats: dict             # files, additions, deletions, findings by severity
      findings: list[ReviewFinding]
      files_reviewed: int
      files_skipped: int
      duration_ms: float
  ```
- [x] Tests: `tests/test_review_models.py` — construction, serialization

### Phase 2: Provider Abstraction (`app/reviews/providers/`)

- [x] `base.py` — `SCMProvider` Protocol:
  ```python
  class SCMProvider(Protocol):
      async def get_pull_request(self, pr_id: int) -> PullRequestInfo: ...
      async def get_diff(self, pr_id: int) -> str: ...
      async def get_changed_files(self, pr_id: int) -> list[dict]: ...
      async def post_review(
          self, pr_id: int, body: str, event: str,
          comments: list[ReviewComment],
      ) -> str: ...
      async def get_existing_review_comments(self, pr_id: int) -> list[dict]: ...
  ```
- [x] `ReviewComment` dataclass (lo que el provider necesita para postear):
  ```python
  @dataclass
  class ReviewComment:
      path: str
      line: int
      side: str
      body: str
      start_line: int | None = None
      start_side: str | None = None
  ```
- [x] `github.py` — `GitHubProvider(SCMProvider)`:
  - Constructor: `(owner, repo, token, http_client)`
  - `get_pull_request()`: `GET /repos/{owner}/{repo}/pulls/{number}`
  - `get_diff()`: `GET /repos/{owner}/{repo}/pulls/{number}` con `Accept: application/vnd.github.diff`
  - `get_changed_files()`: `GET /repos/{owner}/{repo}/pulls/{number}/files`
  - `post_review()`: `POST /repos/{owner}/{repo}/pulls/{number}/reviews`
    - Batch all comments in single request
    - Map `ReviewComment` → GitHub API format (`path`, `line`, `side`, `body`, `start_line`, `start_side`)
  - `get_existing_review_comments()`: `GET /repos/{owner}/{repo}/pulls/{number}/comments`
  - Rate limit handling: retry with backoff on 403/429
- [x] `factory.py` — `create_provider(url: str, settings) -> SCMProvider`:
  - Parse URL: `github.com/{owner}/{repo}/pull/{number}` → GitHubProvider
  - Future: `gitlab.com/...` → GitLabProvider
  - Raise `ValueError` on unsupported URL
- [x] Tests: `tests/test_review_github.py` — mocked httpx responses

### Phase 3: Diff Parser (`app/reviews/diff_parser.py`)

- [x] `parse_unified_diff(raw_diff: str) -> list[DiffFile]`:
  - Parse `diff --git a/path b/path` headers
  - Parse `@@ -old_start,count +new_start,count @@ context` hunks
  - Track line numbers (old + new) and diff positions
  - Handle binary files, renames (`rename from/to`)
  - Detect language from file extension
  - Detect generated files: `*.lock`, `*.min.*`, `*-lock.json`, `package-lock.json`, `yarn.lock`, `Pipfile.lock`, `poetry.lock`, `*.generated.*`
- [x] `parse_github_files(files_response: list[dict]) -> list[DiffFile]`:
  - Alternative: parse from GitHub files API (`patch` field per file)
  - Complementa con metadata (status, additions, deletions)
- [x] `get_diff_position(file: DiffFile, line_no: int, side: str) -> int | None`:
  - Map file line number → diff position (necesario si se usa `position` legacy)
- [x] Helper: `_detect_language(path: str) -> str`
- [x] Helper: `_is_generated_file(path: str) -> bool`
- [x] Tests: `tests/test_diff_parser.py` — con diffs reales como fixtures

### Phase 4: LLM Review Pipeline (`app/reviews/reviewer.py`)

- [x] `review_pull_request(pr: PullRequestInfo, files: list[DiffFile], client: OllamaClient, settings) -> ReviewSummary`:
  - Orchestrator principal
  - Skip generated files
  - Pass 1: summary
  - Pass 2: line-by-line per file
  - Aggregate findings, compute stats, risk level
- [x] `_generate_summary(pr: PullRequestInfo, files: list[DiffFile], client) -> tuple[str, str, RiskLevel, list[str]]`:
  - Prompt con lista de archivos cambiados + stats + PR description
  - Output: title, overview, risk_level, key_changes
  - `think=False` para output JSON
- [x] `_review_file(file: DiffFile, pr: PullRequestInfo, client) -> list[ReviewFinding]`:
  - **Single LLM call per file** (pattern de Qodo — latencia predecible, retry aislado)
  - Prompt con diff del archivo + contexto (PR description, archivos relacionados)
  - Output: JSON array de findings
  - Retry parsing: si JSON inválido, 1 retry con prompt simplificado
  - Si archivo > ~3000 líneas de diff: chunkear por hunks
- [x] `_budget_files(files: list[DiffFile], max_tokens: int) -> tuple[list[DiffFile], list[str]]`:
  - Sort files por language, luego por token count (descendente)
  - Agregar al budget hasta 80% del context window
  - Return: (files_to_review, overflow_file_names)
  - Pattern de Qodo: overflow files se mencionan como "also changed" en el summary
- [x] System prompt para review:
  ```
  You are a senior code reviewer. Review this diff and report issues.
  
  Rules:
  - Only report real issues. Do NOT manufacture problems.
  - For each finding, provide a concrete fix suggestion.
  - Rate confidence (0.0-1.0). Only report findings with confidence > 0.6.
  - Respond in {language}.
  
  Output JSON array:
  [{"line": N, "side": "RIGHT", "severity": "warning", "category": "bug",
    "body": "explanation", "suggestion": "fixed code", "confidence": 0.8}]
  ```
- [x] `_parse_findings_json(raw: str, file: DiffFile) -> list[ReviewFinding]`:
  - Parse JSON con fallback (buscar `[...]` en el raw text)
  - Validar que `line` existe en el diff
  - Filtrar por confidence threshold
- [x] Config: `pr_review_min_confidence: float = 0.6`
- [x] Config: `pr_review_min_severity: str = "suggestion"` (filtro)
- [x] Config: `pr_review_max_findings_per_file: int = 10`
- [x] Tracing: spans para cada paso (summary, per-file review)
- [x] Tests: `tests/test_review_pipeline.py` — mocked LLM responses

### Phase 5: WhatsApp Formatter (`app/reviews/formatter.py`)

- [x] `format_review_summary(summary: ReviewSummary, pr: PullRequestInfo) -> str`:
  - Header: `🔍 *PR Review: #{number} — {title}*`
  - Risk badge: 🟢 Low | 🟡 Medium | 🟠 High | 🔴 Critical
  - Stats: `{files_reviewed} archivos | +{additions} -{deletions} | {n} findings`
  - Key changes: bullet list
  - Top findings (max 5, highest severity first):
    ```
    ⚠️ *security* `src/auth.py:42` — SQL injection en query parameter
    ⚡ *performance* `api/handlers.py:156` — N+1 query en el loop
    ```
  - Footer: `🔗 {pr_url} | {duration}s`
- [x] `format_finding_for_github(finding: ReviewFinding) -> str`:
  - Severity badge: 🔴 critical | ⚠️ warning | 💡 suggestion | 📝 nitpick
  - Category tag: `**[security]**`
  - Body text
  - Suggestion block (si existe):
    ````
    ```suggestion
    corrected_code_here
    ```
    ````
  - Footer: `Confidence: {confidence:.0%} | Generated by LocalForge`
- [x] `_severity_emoji(severity: Severity) -> str`
- [x] `_risk_emoji(risk: RiskLevel) -> str`
- [x] Tests: `tests/test_review_formatter.py`

### Phase 6: Command `/pr-review` (`app/commands/builtins.py`)

- [x] `cmd_pr_review(args: str, context: CommandContext) -> str`:
  - Parse args: URL requerida, flags opcionales (`--summary-only`, `--severity critical,warning`)
  - Validar URL: extract owner/repo/number
  - Validar token: `settings.github_token` debe existir
  - Quick response: "Analizando PR #{number}..."
  - Background task:
    1. Create provider via factory
    2. Fetch PR metadata + diff + files
    3. Parse diff
    4. Run reviewer pipeline
    5. Format summary → enviar por WhatsApp
    6. Si no `--summary-only`: post review en GitHub
    7. Enviar confirmación: "Review posteado: {n} comentarios en {url}"
  - Error handling: enviar error por WhatsApp si algo falla
- [x] Registrar en `register_builtins()`:
  ```python
  CommandSpec(
      name="pr-review",
      description="Review a GitHub PR with AI — summary + line comments",
      usage="/pr-review <url> [--summary-only] [--severity critical,warning]",
      handler=cmd_pr_review,
  )
  ```
- [x] Config settings en `app/config.py`:
  ```python
  pr_review_min_confidence: float = 0.6
  pr_review_min_severity: str = "suggestion"  # minimum severity to post
  pr_review_max_findings_per_file: int = 10
  pr_review_skip_generated: bool = True
  pr_review_language: str = "es"  # language for review comments
  ```
- [x] `.env.example`: documentar settings

### Phase 7: Documentación y Testing

- [x] Crear `docs/features/63-pr_review.md`
- [x] Crear `docs/testing/63-pr_review_testing.md`
- [x] Actualizar `docs/features/README.md` y `docs/testing/README.md`
- [x] Actualizar `AGENTS.md` con `app/reviews/`
- [x] Actualizar `docs/exec-plans/README.md` con Plan 63
- [x] `make check` (lint + typecheck + tests)

## Dependencias entre fases

```
Phase 1 (Models) ──┬── Phase 2 (Providers) ──┬── Phase 6 (Command)
                   │                         │
                   ├── Phase 3 (Diff Parser) ─┤
                   │                         │
                   └── Phase 5 (Formatter)   │
                                             │
                        Phase 4 (Reviewer) ──┘
```

Phases 1→2→3 son secuenciales. Phase 4 depende de 1+3. Phase 5 depende de 1. Phase 6 integra todo.
