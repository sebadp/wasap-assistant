# Feature: Guardrails y Trazabilidad Estructurada

> **Versión**: v1.0
> **Fecha de implementación**: 2026-02-19
> **Fase**: Eval — Iteraciones 0 + 1
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

Antes de enviar cada respuesta al usuario, el sistema valida que no esté vacía, no sea excesivamente larga, no contenga JSON crudo de tools, no filtre datos sensibles (PII), y esté en el mismo idioma que el mensaje del usuario. Cada interacción queda registrada como una traza jerárquica en SQLite, con spans para cada fase del pipeline y scores automáticos de los guardrails.

---

## Arquitectura

```
[Usuario via WhatsApp]
        │
        ▼
[_handle_message] ── TraceContext (contextvars)
        │
        ├── Phase A: embed + save + daily_logs ── [span: phase_a]
        ├── Phase B: memories + notes + summary + history ── [span: phase_b]
        ├── Phase C: classify_intent (task paralela)
        ├── Phase D: build_context → execute_tool_loop/chat ── [span: llm_generation]
        │
        ▼
[Guardrail Pipeline] ── [span: guardrail]
  ├── check_not_empty
  ├── check_excessive_length
  ├── check_no_raw_tool_json
  ├── check_language_match (≥30 chars)
  └── check_no_pii
        │
        ├── PASS → send_message → captura wa_message_id ── [span: delivery]
        └── FAIL → _handle_guardrail_failure (single-shot) → send_message
                        │
                        ▼
                [TraceRecorder] → SQLite (traces, trace_spans, trace_scores)
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/guardrails/models.py` | `GuardrailResult`, `GuardrailReport` (Pydantic) |
| `app/guardrails/checks.py` | 5 checks determinísticos + `redact_pii()` |
| `app/guardrails/pipeline.py` | `run_guardrails()` — orquesta todos los checks |
| `app/tracing/context.py` | `TraceContext`, `SpanData`, `get_current_trace()` (contextvars) |
| `app/tracing/recorder.py` | `TraceRecorder` — persistencia async SQLite (best-effort) |
| `app/database/db.py` | `TRACING_SCHEMA` — tablas `traces`, `trace_spans`, `trace_scores` |
| `app/database/repository.py` | 9 métodos nuevos para tracing |
| `app/webhook/router.py` | Integración: `_handle_guardrail_failure`, `_run_normal_flow()` inner fn |
| `app/whatsapp/client.py` | `send_message()` ahora retorna `str | None` (wa_message_id) |
| `app/config.py` | Settings nuevas: guardrails_* + tracing_* |
| `tests/guardrails/` | 32 unit/integration tests |

---

## Walkthrough técnico: cómo funciona

1. **Inicio de traza**: En `_handle_message`, si `tracing_enabled` y el sample_rate lo permite, se crea un `TraceContext` via `async with TraceContext(phone, text, recorder)` → `router.py:~545`
2. **Propagación via contextvars**: `TraceContext` usa `contextvars.ContextVar`. Las sub-tasks de asyncio (`create_task`) heredan el context automáticamente → `tracing/context.py:21`
3. **Spans por fase**: Cada fase del pipeline (A, B, llm_generation, guardrails, delivery) se wrappea con `async with trace_ctx.span(name, kind)` → `router.py:_run_normal_flow`
4. **Pipeline de guardrails**: Después de obtener el reply del LLM, se llama `await run_guardrails(user_text, reply, settings)` → `guardrails/pipeline.py`
5. **Checks individuales**: Cada check retorna un `GuardrailResult(passed, check_name, details, latency_ms)`. Si alguno falla, `pipeline` llama a `_handle_guardrail_failure` (un solo intento de remediation, sin recursión)
6. **Scores → traza**: Los resultados de guardrails se registran como `trace_scores` (value=1.0 si pasó, 0.0 si falló, source="system")
7. **wa_message_id**: `WhatsAppClient.send_message()` captura el ID del mensaje saliente de la Graph API y lo vincula a la traza → `client.py:55`
8. **Persistencia best-effort**: `TraceRecorder` wrappea toda escritura en `try/except`. Si la DB falla, el pipeline continúa sin interrumpirse → `tracing/recorder.py`

---

## Cómo extenderla

**Agregar un check nuevo:**
1. Implementar la función en `app/guardrails/checks.py`: `def check_mi_check(user_text, reply) -> GuardrailResult`
2. Agregar el call en `app/guardrails/pipeline.py:run_guardrails()`
3. Si es configurable, agregar un setting en `config.py` y condicional en pipeline

**Activar LLM guardrails (Iteración 6):**
- Poner `guardrails_llm_checks = True` en `.env`
- Implementar `check_tool_coherence` y `check_hallucination` en `checks.py`

**Añadir spans a módulos externos:**
```python
from app.tracing.context import get_current_trace
trace_ctx = get_current_trace()
if trace_ctx:
    async with trace_ctx.span("mi_operacion", kind="generation") as span:
        span.set_input({"dato": valor})
        resultado = await mi_funcion()
        span.set_output({"resultado": resultado[:100]})
```

---

## Guía de testing

→ Ver [`docs/testing/12-eval_guardrails_tracing_testing.md`](../testing/12-eval_guardrails_tracing_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| Trazas en SQLite (interno) | Langfuse self-hosted | Zero infra adicional; schema compatible para migrar después |
| `contextvars` para propagación del trace | Pasar `trace_ctx` como parámetro | No rompe firmas existentes; asyncio tasks heredan el context automáticamente |
| Guardrails fail-open (errores → passing) | Fail-closed (errores → bloquean) | Evitar que un bug en el guardrail bloquee todas las respuestas |
| `langdetect` con umbral de 30 chars | Sin umbral | Textos cortos (<30 chars) generan falsos positivos masivos |
| Single-shot remediation | Reintentos múltiples | Evita loops; la calidad del retry raramente supera el original |
| `_run_normal_flow()` inner function | Duplicar código con/sin trace | DRY: permite toggle de tracing sin duplicar la lógica completa del pipeline |

---

## Gotchas y edge cases

- **`classify_intent` como asyncio.Task**: Como se lanza con `create_task()`, el contextvar se copia automáticamente al task — el trace está disponible dentro sin cambiar la firma
- **`langdetect` con textos mixtos** (ej: español con palabras en inglés): puede fallar en la detección. El check falla abierto (passed=True) ante excepción
- **wa_message_id None**: Si la Graph API no retorna el ID (entorno de test, error transitorio), el trace se guarda igualmente sin `wa_message_id`. Las reacciones de Iteración 2 simplemente no se vincularán a ese trace
- **TraceContext con tracing_enabled=False**: El bloque `_run_normal_flow(None)` corre sin instrumentación — zero overhead, zero DB calls de tracing
- **Sample rate < 1.0**: El check `random.random() < tracing_sample_rate` está antes de crear el TraceContext, así que el sampling se hace a nivel de mensaje completo (no a nivel de span)

---

## Variables de configuración relevantes

| Variable (`config.py`) | Default | Efecto |
|---|---|---|
| `guardrails_enabled` | `True` | Activa/desactiva todo el pipeline de guardrails |
| `guardrails_language_check` | `True` | Activa/desactiva check de idioma (con `langdetect`) |
| `guardrails_pii_check` | `True` | Activa/desactiva check de PII (regex) |
| `guardrails_llm_checks` | `False` | LLM guardrails (tool_coherence, hallucination) — pendiente Iteración 6 |
| `tracing_enabled` | `True` | Activa/desactiva trazabilidad estructurada |
| `tracing_sample_rate` | `1.0` | Fracción de mensajes a trazar (1.0 = todos) |
| `trace_retention_days` | `90` | Días antes de purgar trazas antiguas (APScheduler job — Iteración 6) |
