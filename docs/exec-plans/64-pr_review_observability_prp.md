# PRP: PR Review Hardening — Prompts, Multi-Pass, Tracing & Eval (Plan 64)

> **Depende de**: Plan 63 (PR Review A+B+C) completado
> **Inspirado en**: Claude Code `/security-review`, `/ultrareview` bughunter

## Archivos a Modificar

| Archivo | Cambio |
|---------|--------|
| `app/reviews/prompts.py` | **Nuevo** — Prompts centralizados: review, verify, summary |
| `app/reviews/reviewer.py` | Reemplazar prompts inline → `prompts.py`, agregar multi-pass, tracing spans |
| `app/reviews/verifier.py` | **Nuevo** — Pass 2: false positive verification |
| `app/reviews/models.py` | Agregar `VerificationResult`, extender `ReviewFinding` con `exploit_scenario` |
| `app/reviews/code_search.py` | Agregar tracing spans |
| `app/reviews/symbol_extractor.py` | Agregar tracing spans (via reviewer.py caller) |
| `app/commands/builtins.py` | Tracing spans en `_run_review()`, flag `--thorough`, trace scores |
| `app/config.py` | `pr_review_min_confidence` default 7.0 (escala 1-10) |
| `scripts/pr_review_eval_cases.py` | **Nuevo** — 50 diffs sintéticos |
| `scripts/seed_eval_dataset.py` | `extra` field en EvalCase, import PR review cases |
| `scripts/run_eval.py` | Modo `pr-review` con `_run_pr_review()` |
| `Makefile` | Target `eval-pr-review` |

## Fases de Implementación

---

### Phase 1: Prompt Engineering — Review Prompt Exhaustivo ✅

Reemplazar el review prompt de 8 líneas con uno inspirado en Claude Code `/security-review`:
taxonomy de categorías, hard exclusions, precedentes, y confidence scoring 1-10.

- [x] **Nuevo archivo `app/reviews/prompts.py`** — centralizar todos los prompts
- [x] `REVIEW_SYSTEM` — prompt principal (~100 líneas):
  - 5 categorías: Security, Bugs, Performance, Error Handling, Maintainability
  - 17 hard exclusions (style, docs, type hints, TODO, test code, generated files, etc.)
  - Confidence scoring 1-10 con guidelines por rango
  - Precedents (env vars trusted, UUIDs unguessable, React safe by default)
  - `exploit_scenario` field en output JSON
- [x] `SUMMARY_SYSTEM` — prompt de summary (mantener existente)
- [x] `VERIFY_SYSTEM` — prompt para verificación (Phase 2)
- [x] Actualizar `reviewer.py` para importar de `prompts.py` en vez de strings inline
- [x] Migrar confidence de 0.0-1.0 → 1-10 (config default 7.0)
- [x] Agregar `exploit_scenario` a `ReviewFinding`
- [x] Tests actualizados con nueva escala de confidence

---

### Phase 2: Multi-Pass Architecture — Find → Verify → Filter ✅

Inspirado en Claude Code bughunter: Pass 1 encuentra issues, Pass 2 verifica cada finding
con un segundo LLM call que intenta refutar el finding. Solo sobreviven los verified.

- [x] **Nuevo modelo `VerificationResult`** en `models.py`:
  - `is_valid: bool`, `confidence: float`, `reasoning: str`, `revised_severity: Severity | None`
- [x] **Nuevo archivo `app/reviews/verifier.py`**:
  - `verify_finding()` — LLM call individual con `VERIFY_SYSTEM`
  - `verify_findings()` — itera findings, filtra false positives, ajusta severity
- [x] Integrar en `review_pull_request()` con `thorough=True` (opt-in)
- [x] Flag `--thorough` en `/pr-review` (`builtins.py`)

---

### Phase 3: Tracing Spans ✅

Cada paso del pipeline emite un span via `get_current_trace()`.
Si no hay trace activo, noop.

- [x] **`reviewer.py`** — `review_pull_request()`:
  - Span `pr_review.summary` (kind=`generation`)
  - Span `pr_review.file.{path}` per file (kind=`generation`)
  - Span `pr_review.verify` (kind=`generation`, solo si thorough)
  - Span `pr_review.symbol_extraction`
- [x] **`code_search.py`** — `get_cross_file_context()`:
  - Span `pr_review.cross_file_context`
- [x] **`builtins.py`** — `_run_review()`:
  - Span `pr_review.fetch` (GitHub API)
  - Span `pr_review.parse` (diff parsing)
  - Span `pr_review.github_post` (POST /reviews)
- [x] **Trace scores** al finalizar:
  - `pr_review_duration_ms`, `pr_review_findings_count`, `pr_review_critical_count`
  - `pr_review_files_reviewed`, `pr_review_avg_confidence`

**Diagrama de spans:**
```
pr_review.fetch              (GitHub API)
pr_review.parse              (diff parsing)
pr_review.symbol_extraction  (regex)
pr_review.summary            (LLM: generate summary)
pr_review.file.{path}        (LLM: review file)
  └── pr_review.cross_file_context  (grep/glob)
pr_review.verify             (LLM: verify findings, --thorough only)
pr_review.github_post        (POST /reviews)
```

---

### Phase 4: Eval Dataset Exhaustivo ✅

50 diffs sintéticos en `scripts/pr_review_eval_cases.py`:

- [x] Extender `EvalCase` con campo `extra: dict` para metadata pr-review-specific
- [x] **Section `pr_review_security`** (10 cases):
  SQL injection (2), command injection (2), hardcoded secrets (2), path traversal, pickle, eval, JWT
- [x] **Section `pr_review_bugs`** (10 cases):
  Off-by-one, null deref, type mismatch, race condition, resource leak, logic error, div by zero, infinite loop, wrong variable, missing await
- [x] **Section `pr_review_performance`** (5 cases):
  N+1 query, unbounded load, sync in async, quadratic, repeated query
- [x] **Section `pr_review_error_handling`** (5 cases):
  Bare except, swallowed exception, missing handling, stack trace leak, unchecked subprocess
- [x] **Section `pr_review_maintainability`** (5 cases):
  Deep nesting, copy-paste, misleading name, magic numbers, god function
- [x] **Section `pr_review_clean`** (15 cases — false positive testing):
  Rename, docstring, formatting, type hints, test file, TODO, import reorder, dependency version, log message, .gitignore, README, __init__.py, timeout constant, file move, remove debug print

---

### Phase 5: Eval Mode `pr-review` ✅

- [x] Función `_run_pr_review()` en `run_eval.py`:
  - Parse diff → DiffFile[] → synthetic PullRequestInfo → review_pull_request()
  - **Scoring** (4 criteria):
    - Detection (0.4): ¿detectó finding de categoría esperada?
    - Severity accuracy (0.2): ¿severity correcto?
    - Precision (0.2): ratio findings relevantes vs total
    - Count (0.2): dentro del rango esperado
  - Clean diffs: 1.0 si 0 findings, 0.0 si >0
- [x] `pr-review` agregado a choices de `--mode`
- [x] Filter por `pr_review` eval type
- [x] **Makefile**: target `eval-pr-review`

---

### Phase 6: Docs ✅

- [x] Actualizar `docs/features/63-pr_review.md` con Plan 64 (prompts, multi-pass, tracing, eval)
- [x] Actualizar `docs/testing/63-pr_review_testing.md` con nuevos archivos y eval testing
- [x] Actualizar `docs/exec-plans/README.md` → ✅ Completado

## Dependencias entre fases

```
Phase 1 (Prompts) ──┬── Phase 2 (Multi-Pass) ── Phase 3 (Tracing)
                    │
                    └── Phase 4 (Eval Dataset) ── Phase 5 (Eval Mode)
                                                        │
Phase 6 (Docs) ←────────────────────────────────────────┘
```

## Estimación de Impacto

| Métrica | Antes (Plan 63) | Después (Plan 64) |
|---------|-----------------|-------------------|
| Prompt size | ~8 líneas | ~100+ líneas con taxonomy |
| False positive rate | ~40% (estimado) | ~15% (con verify pass) |
| Confidence scoring | 0.0-1.0 (vago) | 1-10 con precedentes |
| Tracing | 0 spans | ~8 spans per review |
| Eval coverage | 0 cases | 50 cases |
| Latencia (normal) | ~30s | ~30s (sin cambio) |
| Latencia (thorough) | n/a | ~60s (2x por verify pass) |
