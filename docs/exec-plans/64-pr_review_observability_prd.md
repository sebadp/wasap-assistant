# PRD: PR Review Hardening — Prompts, Multi-Pass, Tracing & Eval (Plan 64)

## Objetivo y Contexto

El subsistema de PR Review (Plan 63) está funcional pero tiene 3 debilidades:

1. **Prompts básicos**: Nuestro review prompt tiene 8 líneas. El de Claude Code `/security-review` tiene 200+ líneas con taxonomy de vulnerabilidades, 17 hard exclusions de false positives, precedentes codificados, y scoring de confidence 1-10. Nuestros reviews son genéricos donde deberían ser precisos.

2. **Single-pass architecture**: Hacemos un solo LLM call per file. Claude Code bughunter hace find → verify → filter (3 fases). El single-pass genera false positives que erosionan la confianza del usuario.

3. **Zero observability**: No hay tracing spans, no hay trace scores, no hay eval dataset. No podemos medir calidad, detectar regressions, ni iterar con datos.

**Inspiración directa**:
- Claude Code `/security-review` — prompt exhaustivo, hard exclusions, confidence 1-10
- Claude Code `/ultrareview` bughunter — fleet de agents paralelos, find + verify + synthesize
- Claude Code VCR fixtures — testing determinístico de pipelines LLM

## Alcance

### In Scope
- **A) Prompt engineering profundo** — review prompt con taxonomy, exclusions, precedentes, confidence scoring
- **B) Multi-pass review** — Pass 1: find issues, Pass 2: verify/filter false positives, Pass 3: synthesize
- **C) Tracing spans** — observabilidad end-to-end del pipeline
- **D) Eval dataset exhaustivo** — ~50+ diffs sintéticos con bugs conocidos + clean diffs

### Out of Scope
- Bughunter fleet paralelo (múltiples agents) — demasiado costoso para Ollama local
- VCR fixture system completo — útil pero es un proyecto separado
- Real PR testing automation
- Langfuse dashboard customization

## Casos de Uso Críticos

1. `/pr-review` de un PR con SQL injection → el reviewer lo detecta como critical/security con confidence ≥8, no genera false positives en el resto del diff
2. `/pr-review` de un PR cosmético (rename, formatting) → 0 findings o solo nitpicks, no inventa bugs
3. `make eval-pr-review` → accuracy ≥ 0.5 en el dataset, con detection rate ≥ 0.7 para security bugs
4. Langfuse muestra spans del pipeline con latencias per-fase

## Restricciones Técnicas
- `think=False` obligatorio en todos los prompts JSON
- Usar `TraceContext.span()` existente
- Eval funciona sin GitHub token (diffs sintéticos inline)
- Multi-pass es opt-in (flag `--thorough`) para no duplicar latencia en uso normal
