# PRP: PR Review Phase B — Repo Setup & Context (Plan 63-B)

> **Depende de**: Plan 63-A (Core Review) completado

## Archivos a Modificar

| Archivo | Cambio |
|---------|--------|
| `app/reviews/models.py` | Agregar `RepoProfile` dataclass |
| `app/reviews/repo_analyzer.py` | **Nuevo** — Fetch & analyze repo metadata |
| `app/reviews/reviewer.py` | Inyectar RepoProfile context en prompts |
| `app/database/db.py` | Tabla `repo_profiles` |
| `app/database/repository.py` | CRUD para repo_profiles |
| `app/commands/builtins.py` | Agregar `cmd_pr_setup` + registrar `/pr-setup` |
| `app/config.py` | (usa `github_token` existente) |
| `tests/test_repo_analyzer.py` | **Nuevo** |
| `tests/test_repo_profile_crud.py` | **Nuevo** |
| `docs/features/63-pr_review.md` | Actualizar con Phase B |
| `docs/testing/63-pr_review_testing.md` | Actualizar |

## Fases de Implementación

### Phase B1: RepoProfile Model

- [x] `RepoProfile` dataclass en `app/reviews/models.py`:
  ```python
  @dataclass
  class RepoProfile:
      repo_key: str              # "github:owner/repo" — unique identifier
      owner: str
      repo: str
      provider: str              # "github"
      default_branch: str
      primary_language: str
      framework: str | None
      linter: str | None
      test_runner: str | None
      conventions: list[str]     # ["ruff", "line-length=120", "pytest", ...]
      file_tree: list[str]       # ["app/", "app/main.py", "tests/", ...]
      readme_summary: str
      config_snippets: dict[str, str]  # {"pyproject.toml": "...", "package.json": "..."}
      indexing_level: int        # 0=metadata, 1=deep
      last_analyzed_at: str      # ISO timestamp
  ```
- [x] Tests de serialización / construction

### Phase B2: DB Persistence

- [x] Tabla `repo_profiles` en `app/database/db.py`:
  ```sql
  CREATE TABLE IF NOT EXISTS repo_profiles (
      repo_key TEXT PRIMARY KEY,
      owner TEXT NOT NULL,
      repo TEXT NOT NULL,
      provider TEXT NOT NULL DEFAULT 'github',
      default_branch TEXT DEFAULT 'main',
      primary_language TEXT DEFAULT '',
      framework TEXT,
      linter TEXT,
      test_runner TEXT,
      conventions TEXT DEFAULT '[]',       -- JSON array
      file_tree TEXT DEFAULT '[]',         -- JSON array
      readme_summary TEXT DEFAULT '',
      config_snippets TEXT DEFAULT '{}',   -- JSON dict
      indexing_level INTEGER DEFAULT 0,
      last_analyzed_at TEXT,
      created_at TEXT DEFAULT (datetime('now')),
      updated_at TEXT DEFAULT (datetime('now'))
  );
  ```
- [x] `repository.py` methods:
  - `save_repo_profile(profile: dict) -> None`
  - `get_repo_profile(repo_key: str) -> dict | None`
  - `list_repo_profiles() -> list[dict]`
  - `delete_repo_profile(repo_key: str) -> bool`
- [x] Tests CRUD

### Phase B3: Repo Analyzer

- [x] `app/reviews/repo_analyzer.py`:
  - `analyze_repo(owner, repo, provider: SCMProvider) -> RepoProfile`
  - `_fetch_repo_metadata(provider)` → languages, default_branch, description
  - `_fetch_file_tree(provider, max_depth=3, max_files=500)` → list[str]
  - `_fetch_config_files(provider, tree)` → dict[str, str]:
    - Targets: `pyproject.toml`, `package.json`, `tsconfig.json`, `.eslintrc*`, `Makefile`, `Dockerfile`, `.github/workflows/*`, `requirements.txt`, `Cargo.toml`, `go.mod`
  - `_detect_framework(configs: dict) -> str | None`:
    - FastAPI, Django, Flask (Python); React, Next.js, Vue (JS/TS); etc.
  - `_detect_linter(configs: dict) -> str | None`:
    - ruff, eslint, prettier, black, flake8, etc.
  - `_detect_test_runner(configs: dict) -> str | None`:
    - pytest, jest, vitest, go test, cargo test, etc.
  - `_extract_conventions(configs: dict) -> list[str]`:
    - Line length, indent, import style, etc. from config files
- [x] Necesita endpoints adicionales en `GitHubProvider`:
  - `get_repo_info()` → repo metadata (language, description, default_branch)
  - `get_file_tree(path="", depth=3)` → recursive tree via contents API
  - `get_file_content(path)` → raw file content
- [x] Tests con mocked API responses

### Phase B4: Command `/pr-setup`

- [x] `cmd_pr_setup(args, context)`:
  - `/pr-setup https://github.com/owner/repo`:
    1. Parse URL → owner, repo
    2. Create provider, validate access
    3. Run `analyze_repo()`
    4. Persist `RepoProfile`
    5. Reply: "✅ Repo owner/repo configurado (Python/FastAPI, ruff, pytest). Listo para /pr-review."
  - `/pr-setup` (sin args):
    - List configured repos con stats
  - `/pr-setup owner/repo --remove`:
    - Delete profile
  - `/pr-setup owner/repo --refresh`:
    - Re-analyze y actualizar
- [x] Register `CommandSpec("pr-setup", ...)`
- [x] Background execution para el análisis (puede tardar ~10s)

### Phase B5: Context Injection en Reviewer

- [x] En `review_pull_request()`:
  - Lookup `RepoProfile` por `repo_key = f"{provider}:{owner}/{repo}"`
  - Si existe, inyectar en system prompt:
    ```
    REPOSITORY CONTEXT:
    - Project: {owner}/{repo} ({primary_language}, {framework})
    - Linter: {linter}, Test runner: {test_runner}
    - Conventions: {conventions}
    - Structure: {file_tree summary}
    
    Use this context to make reviews more specific to this project's patterns.
    ```
  - Si no existe, review funciona igual que Phase A (solo diff)
- [x] Tests: verificar que el prompt incluye contexto cuando hay profile

### Phase B6: Documentación

- [x] Actualizar `docs/features/63-pr_review.md` con Phase B
- [x] Actualizar `docs/testing/63-pr_review_testing.md`
- [x] `make check`
