# PRD: PR Review — AI Code Review desde WhatsApp (Plan 63)

## Objetivo y Contexto

Implementar un sistema de code review AI-powered que se invoca desde WhatsApp via `/pr-review <url>`, revisa un PR línea por línea con análisis profundo, envía un summary por WhatsApp y postea comentarios puntualizados en líneas específicas del PR en GitHub.

**Inspiración**: CodeRabbit, Qodo/pr-agent, GitHub Copilot Code Review. La diferencia clave es que nuestro flujo se inicia desde WhatsApp y combina delivery de summary conversacional + comentarios técnicos en el provider.

**Por qué**: Un developer debería poder pedir "revisá mi PR" desde el celular, recibir un resumen ejecutivo por WhatsApp, y encontrar comentarios detallados en las líneas relevantes del PR cuando abra GitHub.

## Arquitectura por Fases

El sistema se construye en 3 fases incrementales, cada una con su propio PRP:

```
Phase A: Core Review (diff-only)
  /pr-review <url> → fetch diff → LLM review → WhatsApp summary + GitHub comments
  Sin ingesta. Sin contexto del repo. Solo el diff + PR description.

Phase B: Repo Setup & Context (metadata + conventions)
  /pr-setup <url> → validate → fetch tree + README + configs → persist RepoProfile
  Las reviews ahora tienen contexto: framework, linter, convenciones, structure.

Phase C: Deep Indexing (embeddings + code graph)
  /pr-setup <url> --deep → clone → chunk → embed → vector store
  Las reviews resuelven cross-file references, conocen el codebase completo.
```

### Dependency Flow

```
Phase A (core)
    │
    ▼
Phase B (setup + context)  ← Enriches Phase A reviews with repo metadata
    │
    ▼
Phase C (deep indexing)    ← Enriches Phase B with embeddings + code search
```

## Phase A: Core Review (Plan 63-A)

**PRP**: [`63a-pr_review_core_prp.md`](63a-pr_review_core_prp.md)

### Alcance

**A1. Domain Models** (`app/reviews/models.py`)
- Enums: `Severity` (critical/warning/suggestion/nitpick), `Category` (8 tipos), `RiskLevel`, `DiffLineType`, `FileDiffStatus`
- Dataclasses: `DiffLine`, `DiffHunk`, `DiffFile`, `PullRequestInfo`, `ReviewFinding`, `ReviewSummary`, `ReviewComment`

**A2. Provider Abstraction** (`app/reviews/providers/`)
- `SCMProvider` Protocol: get_pull_request, get_diff, get_changed_files, post_review, get_existing_comments
- `GitHubProvider`: REST API via httpx (no `gh` CLI)
- `create_provider(url)` factory: parse URL → provider
- Rate limit handling con retry

**A3. Diff Parser** (`app/reviews/diff_parser.py`)
- Parse unified diff → `DiffFile`/`DiffHunk`/`DiffLine` models
- Parse GitHub files API response (alternative)
- Detect generated files (lockfiles, .min.js, etc.)
- Detect language from extension

**A4. LLM Review Pipeline** (`app/reviews/reviewer.py`)
- **Pass 1 — Summary**: All files context → title, overview, risk_level, key_changes
- **Pass 2 — Line-by-line**: Per file → `ReviewFinding[]` en JSON
- Single LLM call per file (patrón Qodo)
- Token budgeting: sort files by size, fill to 80% budget, overflow as file list
- Confidence threshold filtering (default 0.6)
- `think=False` para structured output

**A5. WhatsApp Formatter** (`app/reviews/formatter.py`)
- Summary: risk badge, stats, key changes, top findings
- GitHub comment: severity badge, category, body, suggestion block

**A6. Command `/pr-review`** (`app/commands/builtins.py`)
- Parse URL, validate token, background execution
- Progress updates por WhatsApp
- Post batch review en GitHub (single API call)

### Restricciones Técnicas
- No usar `gh` CLI — httpx directo contra REST API
- `line`+`side` para comments (no `position` deprecated)
- Batch comments en un solo `POST /reviews` → una notificación
- `think=False` para JSON output del LLM
- Background task (asyncio.create_task) con progress updates

## Phase B: Repo Setup & Context (Plan 63-B)

**PRP**: [`63b-pr_review_setup_prp.md`](63b-pr_review_setup_prp.md)

### Alcance

**B1. RepoProfile Model** (`app/reviews/models.py`)
```python
@dataclass
class RepoProfile:
    owner: str
    repo: str
    provider: str              # "github", "gitlab", "bitbucket"
    default_branch: str
    primary_language: str
    framework: str | None      # "fastapi", "react", "nextjs", etc.
    linter: str | None         # "ruff", "eslint", etc.
    test_runner: str | None    # "pytest", "jest", "vitest", etc.
    conventions: list[str]     # Extracted from config files
    file_tree: list[str]       # Top-level structure (max depth 3)
    readme_summary: str        # First ~500 chars of README
    config_files: dict[str, str]  # filename → content of key configs
    created_at: str
    updated_at: str
    indexing_level: int        # 0=none, 1=metadata, 2=deep
```

**B2. Repo Analyzer** (`app/reviews/repo_analyzer.py`)
- Fetch repo metadata: languages, default branch, description
- Fetch file tree (top 3 levels, max 500 files)
- Fetch & parse config files: pyproject.toml, package.json, .eslintrc, tsconfig.json, Makefile, etc.
- Detect framework, linter, test runner from configs
- Extract conventions: line length, indent style, import order, etc.
- Summarize README (first 500 chars)

**B3. DB Persistence** (`app/database/`)
- Table `repo_profiles` en SQLite
- CRUD: save_repo_profile, get_repo_profile, list_repo_profiles, delete_repo_profile

**B4. Command `/pr-setup`**
- `/pr-setup https://github.com/owner/repo` → analyze → persist → "✅ Listo"
- `/pr-setup` (sin args) → list configured repos
- `/pr-setup owner/repo --remove` → delete profile

**B5. Context Injection in Reviewer**
- Si existe RepoProfile para el repo del PR, inyectar en el system prompt:
  - Framework/language/linter info
  - Convenciones extraídas
  - File tree summary (para que el LLM entienda la estructura)

## Phase C: Deep Indexing (Plan 63-C)

**PRP**: [`63c-pr_review_deep_index_prp.md`](63c-pr_review_deep_index_prp.md)

### Alcance

**C1. Repo Cloner** (`app/reviews/indexer.py`)
- Shallow clone (`--depth 1`) del repo a directorio temporal
- Cleanup automático post-indexing
- Exclude patterns: node_modules, .git, vendored, binary

**C2. Code Chunker**
- Split archivos en chunks semánticos (funciones, clases, bloques)
- Fallback: chunks de ~500 líneas con overlap de 50
- Metadata por chunk: path, start_line, end_line, symbol_name, language

**C3. Embedding Pipeline**
- Embed chunks via Ollama (nomic-embed-text, 768 dims)
- Store en sqlite-vec (ya usado para memorias)
- Tabla `repo_embeddings`: repo_key, chunk_id, path, start_line, end_line, content, embedding

**C4. RAG at Review Time**
- Para cada archivo en el diff, buscar chunks relacionados via semantic search
- Inyectar top-K chunks relevantes como contexto en el prompt del reviewer
- "¿Quién llama a esta función?" → embedding search + contexto

**C5. Incremental Re-index**
- Al correr `/pr-setup owner/repo --deep --update`: solo re-indexar archivos cambiados desde último index
- Track last_indexed_commit en repo_profiles

### Research: Agent Search (Claude Code pattern)

Claude Code **no usa embeddings/RAG**. Su approach es:
- **Grep** (ripgrep) para búsqueda lexical rápida
- **Glob** para file discovery
- **LSP** para code intelligence: go-to-definition, find-references, call hierarchy, workspace symbols

Esto sugiere un **approach híbrido** para Phase C:
1. **Embeddings** para contexto semántico amplio ("archivos relacionados con auth")
2. **Grep-like search** para referencias exactas ("¿dónde se usa `validate_token`?")
3. No necesitamos LSP (requiere language server running) — grep + embeddings cubren el 90%

## Out of Scope (todas las fases)
- GitLab/Bitbucket provider implementation (solo la abstracción)
- Incremental re-review (solo cambios nuevos post-push)
- Aprendizaje de dismissals
- OAuth flow (solo token estático)
- Auto-apply suggestions

## Métricas de Éxito

| Métrica | Phase A | Phase B | Phase C |
|---------|---------|---------|---------|
| Latencia (PR típico 5-15 files) | < 120s | < 130s | < 150s |
| Findings relevantes (no false positives) | > 60% | > 70% | > 80% |
| Coverage de archivos revisados | > 90% | > 90% | > 95% |
| Context-aware findings (cross-file) | 0% | ~20% | > 50% |

## Research Summary

### Tools de referencia
- **CodeRabbit**: Index-light, on-demand file fetching via API, learnings store
- **Qodo/pr-agent**: Single LLM call per file, token budgeting (sort by size), GitProvider abstraction, structured YAML output
- **Greptile**: Index-heavy, clone → embed → vector store → RAG, setup step requerido
- **GitHub Copilot**: Leverages GitHub's code graph infra, no user-visible indexing
- **Claude Code**: No embeddings/RAG — grep + glob + LSP for code intelligence

### GitHub API (key endpoints)
- `POST /repos/{owner}/{repo}/pulls/{number}/reviews` — batch review + comments
- `comments[].line` + `comments[].side` (RIGHT/LEFT) — modern positioning (no `position`)
- `comments[].start_line` — multi-line comments
- `GET /pulls/{number}/files` — changed files con patch
- `Accept: application/vnd.github.diff` — raw unified diff

### Key design decisions
1. **Single LLM call per file** (Qodo pattern) — predictable latency, isolated retry
2. **Token budgeting** — sort files by size, fill to 80%, overflow as file list
3. **`line`+`side`** (not `position`) — modern, simpler, no diff position mapping needed
4. **Batch review** — one POST, one notification
5. **3-phase architecture** — incremental value, each phase works standalone
6. **Hybrid context** (Phase C) — embeddings for semantic + grep for lexical (inspired by Claude Code)
