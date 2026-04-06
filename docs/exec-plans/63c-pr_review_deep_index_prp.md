# PRP: PR Review Phase C — Deep Code Search (Plan 63-C)

> **Depende de**: Plan 63-B (Repo Setup) completado
> **Patrón**: Claude Code — grep + glob + LSP, sin embeddings

## Filosofía

Claude Code demuestra que **no se necesitan embeddings** para code intelligence de alta calidad. Su approach:

1. **Grep** (ripgrep) — búsqueda lexical de símbolos, imports, usages
2. **Glob** — discovery de archivos por patron
3. **LSP** — go-to-definition, find-references, call hierarchy

Esto es más rápido, no requiere indexing upfront, no consume storage, y se mantiene actualizado automáticamente (siempre busca en el HEAD actual).

**Nuestra implementación**: Al hacer `/pr-setup --deep`, clonamos el repo (shallow). Luego, en cada review, usamos grep/glob sobre ese clone para encontrar contexto cross-file. Opcionalmente, si hay un language server disponible, usamos LSP.

## Archivos a Modificar

| Archivo | Cambio |
|---------|--------|
| `app/reviews/code_search.py` | **Nuevo** — grep + glob + LSP search engine |
| `app/reviews/symbol_extractor.py` | **Nuevo** — Extract symbols from diff (imports, function calls, types) |
| `app/reviews/repo_clone.py` | **Nuevo** — Shallow clone management (create, update, cleanup) |
| `app/reviews/reviewer.py` | Integrar code_search para cross-file context |
| `app/reviews/models.py` | Agregar `CodeReference`, `SymbolUsage` models |
| `app/reviews/providers/github.py` | Agregar `get_clone_url()` |
| `app/commands/builtins.py` | Extend `/pr-setup --deep` (clone repo) |
| `app/config.py` | `pr_review_clones_dir`, `pr_review_deep_context_budget` |
| `tests/test_symbol_extractor.py` | **Nuevo** |
| `tests/test_code_search.py` | **Nuevo** |
| `tests/test_repo_clone.py` | **Nuevo** |
| `docs/features/63-pr_review.md` | Actualizar con Phase C |

## Fases de Implementación

### Phase C1: Models

- [x] `CodeReference` dataclass:
  ```python
  @dataclass
  class CodeReference:
      path: str
      start_line: int
      end_line: int
      content: str           # The relevant lines
      match_type: str        # "definition", "usage", "import", "test", "related"
      symbol: str            # The symbol that linked us here
  ```
- [x] `SymbolUsage` dataclass:
  ```python
  @dataclass
  class SymbolUsage:
      name: str              # "validate_token", "UserModel", etc.
      kind: str              # "function", "class", "variable", "import", "type"
      source_path: str       # File where it appears in the diff
      source_line: int
  ```

### Phase C2: Repo Clone Manager (`app/reviews/repo_clone.py`)

- [x] `ensure_clone(repo_key: str, clone_url: str, clones_dir: Path) -> Path`:
  - Si ya existe el clone dir → `git fetch origin && git reset --hard origin/HEAD`
  - Si no existe → `git clone --depth 1 --single-branch {url} {dir}`
  - Clone URL con token: `https://x-access-token:{token}@github.com/{owner}/{repo}.git`
  - Return: path al clone
- [x] `get_clone_path(repo_key: str, clones_dir: Path) -> Path | None`:
  - Check si el clone existe y es válido (has .git/)
- [x] `remove_clone(repo_key: str, clones_dir: Path) -> bool`
- [x] `cleanup_stale_clones(clones_dir: Path, max_age_days: int = 30)`:
  - Borrar clones que no se usaron en N días
- [x] Config: `pr_review_clones_dir: str = "data/repo_clones"`
- [x] Security: el clone se hace con `--depth 1` (no baja todo el history)
- [x] Tests

### Phase C3: Symbol Extractor (`app/reviews/symbol_extractor.py`)

Analiza el diff y extrae qué símbolos fueron tocados, para saber qué buscar en el repo.

- [x] `extract_symbols_from_diff(files: list[DiffFile]) -> list[SymbolUsage]`:
  - Para cada línea agregada/modificada:
    - Detectar **definiciones**: `def foo(`, `class Bar`, `function baz(`, `const qux =`
    - Detectar **imports**: `from app.auth import validate`, `import { UserModel }`, `use crate::auth`
    - Detectar **type annotations**: `: UserModel`, `-> TokenResult`
    - Detectar **function calls**: `validate_token(`, `repo.save(`
  - Dedup por nombre
  - Return lista de SymbolUsage con metadata
- [x] Language-specific regex patterns:
  ```python
  _PYTHON_DEF = re.compile(r"^\+\s*(async\s+)?def\s+(\w+)")
  _PYTHON_CLASS = re.compile(r"^\+\s*class\s+(\w+)")
  _PYTHON_IMPORT = re.compile(r"^\+\s*(?:from\s+\S+\s+)?import\s+(.+)")
  _JS_FUNCTION = re.compile(r"^\+\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)")
  _JS_CONST = re.compile(r"^\+\s*(?:export\s+)?const\s+(\w+)\s*=")
  _JS_IMPORT = re.compile(r"^\+\s*import\s+.*from\s+['\"](.+)['\"]")
  _GO_FUNC = re.compile(r"^\+\s*func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)")
  ```
- [x] Heuristic: solo extraer símbolos de líneas `+` (added), no `-` (removed)
- [x] Filter: ignorar símbolos de 1-2 chars, built-ins (print, len, etc.), primitives
- [x] Tests con diffs de diferentes lenguajes

### Phase C4: Code Search Engine (`app/reviews/code_search.py`)

La pieza central. Busca en el clone local usando grep y glob, como Claude Code.

- [x] `find_references(symbol: SymbolUsage, clone_path: Path, exclude_file: str, max_results: int = 10) -> list[CodeReference]`:
  - **grep** por el nombre del símbolo en el repo
  - Filtrar: excluir el archivo de origen, node_modules, .git, vendored
  - Para cada match: leer contexto ±5 líneas
  - Clasificar match_type: "definition" (def/class/function), "usage" (call), "import", "test" (en tests/), "related" (other)
  - Usar `subprocess.run(["rg", ...])` o fallback a `grep -rn`
- [x] `find_definitions(symbol_name: str, clone_path: Path) -> list[CodeReference]`:
  - Grep por patrones de definición: `def {name}`, `class {name}`, `function {name}`, `const {name}`
  - Retorna definiciones con contexto completo de la función/clase
- [x] `find_tests(file_path: str, clone_path: Path) -> list[CodeReference]`:
  - Glob: `tests/**/test_*.py`, `**/*.test.ts`, `**/*.spec.js`, etc.
  - Grep dentro de tests por el nombre del módulo/función tocado
  - "¿Hay tests para lo que se cambió?"
- [x] `find_related_files(file_path: str, clone_path: Path) -> list[str]`:
  - Glob por archivos con nombre similar (e.g., `models.py` → `test_models.py`, `models_schema.py`)
  - Grep por imports del archivo modificado
- [x] `_run_rg(args: list[str], cwd: Path, timeout: int = 10) -> str`:
  - Wrapper de ripgrep/grep con timeout y error handling
  - Fallback: `grep -rn` si `rg` no está disponible
- [x] Config: `pr_review_deep_context_budget: int = 3000` (tokens max de contexto cross-file per file review)
- [x] Tests

### Phase C5: Assemble Cross-File Context

- [x] `get_cross_file_context(diff_file: DiffFile, symbols: list[SymbolUsage], clone_path: Path, token_budget: int = 3000) -> str`:
  - Para cada symbol extraído del diff del archivo:
    1. `find_definitions(symbol)` — ¿dónde está definido lo que se importa/usa?
    2. `find_references(symbol)` — ¿quién más usa lo que se cambió?
    3. `find_tests(file_path)` — ¿hay tests que cubren esto?
  - Dedup, sort by relevance (definitions > usages > tests > related)
  - Format como XML blocks con path:lines:
    ```
    <cross_file_context>
    
    <reference type="definition" symbol="validate_token" path="app/auth/tokens.py" lines="45-62">
    def validate_token(token: str) -> bool:
        """Validate JWT token and return True if valid."""
        try:
            payload = jwt.decode(token, SECRET, algorithms=["HS256"])
            return payload.get("exp", 0) > time.time()
        except jwt.InvalidTokenError:
            return False
    </reference>
    
    <reference type="usage" symbol="validate_token" path="app/middleware/auth.py" lines="23-25">
    if not validate_token(request.headers.get("Authorization", "")):
        raise HTTPException(status_code=401)
    </reference>
    
    <reference type="test" symbol="validate_token" path="tests/test_auth.py" lines="12-20">
    def test_validate_token_expired():
        token = create_token(exp=time.time() - 100)
        assert not validate_token(token)
    </reference>
    
    </cross_file_context>
    ```
  - Truncar al token budget (contar chars × 0.3 como estimación de tokens)
- [x] El reviewer recibe esto en el prompt y puede identificar:
  - Breaking changes (callers que se rompen)
  - Missing test updates
  - Inconsistencias con la definición upstream

### Phase C6: Integration con Reviewer

- [x] En `_review_file()` de `reviewer.py`:
  ```python
  cross_context = ""
  if clone_path and symbols:
      cross_context = get_cross_file_context(
          diff_file, symbols, clone_path,
          token_budget=settings.pr_review_deep_context_budget,
      )
  ```
  - Append al prompt del review per-file
  - Agregar instrucción al system prompt:
    ```
    You have access to cross-file context from the repository.
    Use it to identify:
    - Breaking changes that affect callers of modified functions
    - Missing test updates for changed behavior
    - Inconsistencies with imported definitions
    - Security implications in the broader call chain
    ```
- [x] Tracing: span para symbol extraction + each grep search

### Phase C7: Extend `/pr-setup --deep`

- [x] En `cmd_pr_setup` con `--deep`:
  1. Run Phase B analysis (metadata) — ya existente
  2. Clone repo via `ensure_clone()`
  3. Update `RepoProfile.indexing_level = 1`
  4. Reply: "✅ Repo clonado y listo para deep reviews ({n} archivos)"
- [x] En `cmd_pr_setup` con `--deep --update`:
  - `ensure_clone()` hace fetch + reset (actualiza a HEAD)
- [x] En `cmd_pr_setup` con `--deep --remove`:
  - `remove_clone()` + reset `indexing_level = 0`
- [x] Background cleanup job: `cleanup_stale_clones()` cada 24h

### Phase C8: Documentación

- [x] Actualizar `docs/features/63-pr_review.md` con Phase C
- [x] Actualizar `docs/testing/63-pr_review_testing.md`
- [x] Actualizar `AGENTS.md` con nuevos módulos
- [x] `make check`

## Ventajas vs Embeddings (por qué este approach)

| | Grep+Glob (Claude Code) | Embeddings/RAG (Greptile) |
|---|---|---|
| **Setup time** | ~5s (shallow clone) | ~2-10min (chunk+embed) |
| **Storage** | ~50MB (clone) | ~40MB (vectors) + clone |
| **Freshness** | Siempre actualizado (git fetch) | Requiere re-index |
| **Precision** | Exacta para símbolos | Semántica, puede ser noisy |
| **Cross-file** | Excelente (grep por nombre) | Bueno (similarity search) |
| **Complexity** | Baja (subprocess + regex) | Alta (embed pipeline + vector DB) |
| **Dependencies** | ripgrep (ya lo usamos) | Ollama embeddings + sqlite-vec |

## Estimación de latencia adicional

| Operación | Tiempo |
|-----------|--------|
| Symbol extraction from diff | < 100ms |
| Grep per symbol (5 symbols × 10ms) | ~50ms |
| Read context lines | ~20ms |
| Format cross-file context | < 10ms |
| **Total overhead per file** | **~200ms** |

Mucho más rápido que embed+search (~2s per query con Ollama).
