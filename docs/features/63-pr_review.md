# PR Review — AI Code Review desde WhatsApp (Plan 63)

## Overview

Sistema de code review AI-powered invocado desde WhatsApp via `/pr-review <url>`. Revisa un PR linea por linea, envia un summary por WhatsApp y postea comentarios puntualizados en GitHub.

## Phase A: Core Review Engine

### Comando

```
/pr-review https://github.com/owner/repo/pull/123
/pr-review https://github.com/owner/repo/pull/123 --summary-only
/pr-review https://github.com/owner/repo/pull/123 --severity critical,warning
```

### Flujo

1. Parse URL -> extract owner/repo/number
2. Fetch PR metadata + unified diff via GitHub REST API
3. Parse diff -> structured `DiffFile`/`DiffHunk`/`DiffLine` models
4. **Pass 1**: Generate summary (title, overview, risk level, key changes)
5. **Pass 2**: Per-file line-by-line review -> `ReviewFinding[]`
6. Format summary -> send via WhatsApp
7. Post batch review en GitHub (single API call, one notification)

### Modelos

- **Enums**: `Severity`, `Category`, `RiskLevel`, `DiffLineType`, `FileDiffStatus`
- **Diff**: `DiffLine`, `DiffHunk`, `DiffFile`
- **PR**: `PullRequestInfo`
- **Review**: `ReviewFinding`, `ReviewSummary`, `ReviewComment`

### Key Design Decisions

- **Single LLM call per file** (patron Qodo): latencia predecible, retry aislado
- **Token budgeting**: sort files by size, fill to 80% budget, overflow as file list
- **`line`+`side`** (no `position`): API moderna de GitHub, sin mapping de diff positions
- **Batch review**: un POST, una notificacion
- **Confidence filtering**: default 7 (escala 1-10), solo findings con alta confianza se postean

### Config

| Setting | Default | Description |
|---------|---------|-------------|
| `GITHUB_TOKEN` | (requerido) | GitHub personal access token |
| `PR_REVIEW_MIN_CONFIDENCE` | 7.0 | Minimum confidence threshold (1-10 scale) |
| `PR_REVIEW_MIN_SEVERITY` | suggestion | Minimum severity to post |
| `PR_REVIEW_MAX_FINDINGS_PER_FILE` | 10 | Max findings per file |
| `PR_REVIEW_SKIP_GENERATED` | true | Skip lockfiles, .min.js, etc. |
| `PR_REVIEW_LANGUAGE` | es | Language for review comments |

### Archivos

| Archivo | Proposito |
|---------|-----------|
| `app/reviews/models.py` | Domain models (enums, dataclasses) |
| `app/reviews/providers/base.py` | `SCMProvider` Protocol |
| `app/reviews/providers/github.py` | GitHub REST API implementation |
| `app/reviews/providers/factory.py` | URL -> provider factory |
| `app/reviews/diff_parser.py` | Unified diff parser |
| `app/reviews/reviewer.py` | LLM review pipeline |
| `app/reviews/formatter.py` | WhatsApp + GitHub formatting |
| `app/commands/builtins.py` | `/pr-review` command |

## Phase B: Repo Setup & Context

`/pr-setup <url>` analiza un repo y persiste metadata (framework, linter, convenciones, file tree). Las reviews usan este contexto para ser mas especificas.

| Archivo | Proposito |
|---------|-----------|
| `app/reviews/repo_analyzer.py` | Fetch + analyze repo metadata |
| `app/reviews/models.py` | `RepoProfile` dataclass |
| `app/database/db.py` | Tabla `repo_profiles` |
| `app/database/repository.py` | CRUD repo_profiles |

## Phase C: Deep Code Search (patron Claude Code)

`/pr-setup <url> --deep` clona el repo (shallow). En cada review, grep + glob sobre el clone para cross-file context. Sin embeddings.

| Archivo | Proposito |
|---------|-----------|
| `app/reviews/repo_clone.py` | Shallow clone management |
| `app/reviews/symbol_extractor.py` | Extract symbols from diff (regex) |
| `app/reviews/code_search.py` | grep + glob search engine + context assembly |

### Flujo deep review

1. Symbol extractor analiza lineas `+` del diff -> `SymbolUsage[]`
2. Para cada symbol: `find_definitions()` + `find_references()` via ripgrep
3. `find_tests()` busca test files relacionados
4. Resultados formateados como XML `<cross_file_context>` blocks
5. Inyectados en el system prompt del reviewer per-file

## Plan 64: Hardening — Prompts, Multi-Pass, Tracing & Eval

### Prompt Engineering

Prompt exhaustivo (~100 líneas) inspirado en Claude Code `/security-review`:
- **Taxonomy**: 5 categorías (security, bugs, performance, error_handling, maintainability) con sub-items específicos
- **17 hard exclusions**: style preferences, missing docs, type hints, TODO comments, test code, generated files, theoretical DoS, etc.
- **Confidence scoring 1-10**: 9-10 certain, 7-8 high, below 5 do not report
- **Precedents**: env vars trusted, UUIDs unguessable, React safe by default
- **exploit_scenario** field para security/bug findings

Prompts centralizados en `app/reviews/prompts.py`: `REVIEW_SYSTEM`, `SUMMARY_SYSTEM`, `VERIFY_SYSTEM`.

### Multi-Pass Review (--thorough)

Inspirado en Claude Code bughunter (find → verify → filter):
- **Pass 1**: Find issues (per-file LLM call) — mismo que antes
- **Pass 2**: Per-file review — unchanged
- **Pass 3** (opt-in `--thorough`): Verify each finding con segundo LLM call que intenta refutarlo
  - Solo findings que sobreviven verificación pasan al output
  - Puede ajustar severity hacia abajo

```
/pr-review https://github.com/owner/repo/pull/123 --thorough
```

Archivos: `app/reviews/verifier.py`, `app/reviews/models.py` (`VerificationResult`)

### Observability — Tracing Spans

Spans end-to-end del pipeline via `TraceContext.span()`:

```
pr_review.fetch              (GitHub API)
pr_review.parse              (diff parsing)
pr_review.symbol_extraction  (regex)
pr_review.summary            (LLM: generate summary)
pr_review.file.{path}        (LLM: review file)
pr_review.cross_file_context (grep/glob)
pr_review.verify             (LLM: verify findings, --thorough only)
pr_review.github_post        (POST /reviews)
```

Trace scores: `pr_review_duration_ms`, `pr_review_findings_count`, `pr_review_critical_count`, `pr_review_avg_confidence`.

### Eval Dataset

50 synthetic diffs en `scripts/pr_review_eval_cases.py`:
- 10 security (SQL injection, command injection, hardcoded secrets, path traversal, etc.)
- 10 bugs (off-by-one, null deref, type mismatch, resource leak, etc.)
- 5 performance (N+1, unbounded load, sync in async, quadratic)
- 5 error handling (bare except, swallowed exception, stack trace leak)
- 5 maintainability (deep nesting, copy-paste, misleading names)
- 15 clean diffs (false positive testing — rename, docstring, formatting, tests)

Eval mode: `make eval-pr-review` — 4-criteria scoring (detection 0.4 + severity 0.2 + precision 0.2 + count 0.2)
