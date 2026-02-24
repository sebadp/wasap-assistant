# Feature: Maduración del Sistema de Evaluación

> **Versión**: v1.0
> **Fecha de implementación**: 2026-02-20
> **Fase**: Eval — Iteración 6
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

Iteración 6 cierra el ciclo de evaluación con cuatro mejoras:

1. **LLM guardrails** (`tool_coherence`, `hallucination_check`): checks opcionales que usan el LLM para detectar incoherencia con herramientas y alucinaciones.
2. **Span instrumentation**: cada tool call dentro de `execute_tool_loop` registra un span `tool:<nombre>` en la traza activa, con input/output.
3. **Limpieza automática de trazas**: APScheduler corre un job diario (03:00 UTC) que purga trazas más antiguas que `trace_retention_days` (default: 90 días).
4. **Dashboard queries**: dos nuevos métodos en repository (`get_failure_trend`, `get_score_distribution`) expuestos como tool `get_dashboard_stats` en el eval skill.

---

## Arquitectura

### LLM Guardrails

```
run_guardrails(guardrails_llm_checks=True, ollama_client=client)
        │
        ├─ deterministic checks (siempre)
        │
        └─ llm_checks_enabled AND ollama_client is not None
                │
                ├─ tool_calls_used=True → check_tool_coherence (timeout: 500ms)
                └─ always → check_hallucination (timeout: 500ms)
                        │
                        └─ asyncio.wait_for(coro, timeout=0.5) → fail open on TimeoutError
```

### Span Instrumentation

```
execute_tool_loop()
        │
        └─ _run_tool_call(tc, registry, mcp)
                │
                ├─ get_current_trace() → TraceContext | None
                │
                └─ if trace:
                        async with trace.span(f"tool:{tool_name}", kind="tool") as span:
                            span.set_input({"tool": ..., "arguments": ...})
                            result = await execute(tool_call)
                            span.set_output({"content": result[:200]})
```

### Trace Cleanup Job

```
main.py lifespan (startup):
    scheduler.add_job(
        _cleanup_old_traces,
        trigger="cron", hour=3, minute=0,
        id="trace_cleanup", replace_existing=True,
    )

_cleanup_old_traces():
    deleted = await repository.cleanup_old_traces(days=settings.trace_retention_days)
    logger.info("Trace cleanup: deleted %d old traces", deleted)
```

### Dashboard Queries

```
get_failure_trend(days=30) → list[{day, total, failed}]
get_score_distribution()   → list[{check, count, avg_score, failures}]
        ↓
get_dashboard_stats(days=30) tool → formatted report via WhatsApp
```

---

## Archivos clave

| Archivo | Cambio |
|---|---|
| `app/guardrails/checks.py` | `check_tool_coherence()`, `check_hallucination()` (async, fail-open) |
| `app/guardrails/pipeline.py` | `_run_async_check()` con timeout 500ms; `run_guardrails()` acepta `ollama_client` |
| `app/webhook/router.py` | `run_guardrails(ollama_client=ollama_client)` en ambas ramas del call site |
| `app/skills/executor.py` | Import `get_current_trace`; span `tool:<name>` en `_run_tool_call` |
| `app/main.py` | Job APScheduler `trace_cleanup` (cron: 03:00) gated por `tracing_enabled` |
| `app/database/repository.py` | `get_failure_trend()`, `get_score_distribution()` |
| `app/skills/tools/eval_tools.py` | Tool `get_dashboard_stats` |
| `skills/eval/SKILL.md` | Agrega `get_dashboard_stats` a la lista de tools |
| `app/skills/router.py` | `get_dashboard_stats` en categoría `evaluation` |

---

## Walkthrough técnico

### LLM Guardrails

Los dos nuevos checks son funciones `async` en `checks.py`:

```python
async def check_tool_coherence(user_text, reply, ollama_client) -> GuardrailResult:
    # Prompt binario: "Does the reply coherently address the question? yes/no"
    # passed = answer.startswith("yes"); fail open on exception

async def check_hallucination(user_text, reply, ollama_client) -> GuardrailResult:
    # Prompt binario: "Does the reply contain hallucinated facts? yes/no"
    # passed = answer.startswith("no"); fail open on exception
```

Integración en pipeline con timeout de 500ms:

```python
async def _run_async_check(results, check_name, coro, timeout=0.5) -> None:
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
    except TimeoutError:
        # Fail open: append passed=True result
```

Activación (en `.env`):
```
GUARDRAILS_LLM_CHECKS=true
```

### Span Instrumentation

Las trazas ya registraban fases (A/B/C/guardrails). Con este cambio, cada tool call individual genera un span `tool:<nombre>`:

```
trace
  ├─ span: phase_a
  ├─ span: phase_b
  ├─ span: guardrails
  └─ span: tool:get_current_datetime   ← NUEVO
      input: {tool: ..., arguments: {}}
      output: {content: "2026-02-20T..."}
```

El span se crea solo si `get_current_trace()` retorna un contexto activo (no nulo). Si no hay traza, el tool call sigue funcionando igual.

### Dashboard

```python
await get_dashboard_stats(days=30)
# Retorna:
# *Dashboard — últimos 30 días*
#
# *Tendencia general:*
# - Interacciones: 142
# - Con fallos: 8 (5.6%)
# - Tasa de éxito: 94.4%
#
# *Últimos 7 días:*
#   2026-02-20: 23 total, 1 fallidos
#   ...
#
# *Scores por check:*
#   language_match: avg=0.95, fallos=3/142
#   not_empty: avg=1.00, fallos=0/142
```

---

## Configuración

| Variable | Default | Descripción |
|---|---|---|
| `guardrails_llm_checks` | `false` | Activar checks LLM (tool_coherence + hallucination) |
| `trace_retention_days` | `90` | Días antes de purgar trazas (cleanup diario) |

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| Timeout 500ms para LLM checks | Sin timeout | Evita bloquear el pipeline en Ollama lento |
| `guardrails_llm_checks=False` por default | Habilitado por default | LLM checks son costosos y pueden tener falsos positivos; opt-in explícito |
| Cleanup diario a las 03:00 | TTL por fila | APScheduler ya está disponible; simple de configurar |
| `get_failure_trend` por día | Por hora | Granularidad suficiente para análisis; evita noise |

---

## Guía de testing

→ Ver [`docs/testing/17-eval_maduracion_testing.md`](../testing/17-eval_maduracion_testing.md)
