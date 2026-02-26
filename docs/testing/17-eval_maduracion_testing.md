# Testing Manual: Maduración del Sistema de Eval

> **Feature documentada**: [`docs/features/17-eval_maduracion.md`](../features/17-eval_maduracion.md)
> **Requisitos previos**: Container corriendo, `tracing_enabled=true`.

---

## Nivel 1: LLM Guardrails

### Activar los checks LLM

Agregar al `.env`:
```
GUARDRAILS_LLM_CHECKS=true
```
Reiniciar el container.

### Verificar que se ejecutan

```bash
# Ver en logs del container si los checks LLM se ejecutan
docker compose logs -f wasap 2>&1 | grep "tool_coherence\|hallucination_check\|llm_checks"
```

### Verificar que el timeout falla open

```python
# Smoke test desde Python (simula timeout):
import asyncio
from app.guardrails.pipeline import _run_async_check
from app.guardrails.models import GuardrailResult

results = []

async def slow_coro():
    await asyncio.sleep(10)
    return GuardrailResult(passed=False, check_name="test", details="")

asyncio.run(_run_async_check(results, "test_timeout", slow_coro()))
assert results[0].passed is True  # fail open
assert "timed out" in results[0].details
print("✓ Timeout fail-open OK")
```

### Ver scores en trazas

```bash
sqlite3 data/wasap.db "
SELECT t.id, s.name, s.value
FROM traces t
JOIN trace_scores s ON t.id = s.trace_id
WHERE s.name IN ('tool_coherence', 'hallucination_check')
ORDER BY t.started_at DESC
LIMIT 10;"
```

---

## Nivel 2: Span Instrumentation

### Verificar spans de tool calls

```bash
sqlite3 data/wasap.db "
SELECT ts.name, ts.kind, ts.status, ts.latency_ms,
       substr(ts.input_data, 1, 100) as input_preview
FROM trace_spans ts
WHERE ts.kind = 'tool'
ORDER BY ts.started_at DESC
LIMIT 10;"
```

Cada tool call debe generar un span con `kind='tool'` y `name` del tipo `tool:get_current_datetime`.

### Verificar via eval skill

```
Usuario: "diagnose_trace <id_de_traza_con_tools>"
→ En la sección Spans debe aparecer:
  - tool:get_current_datetime (tool) [45ms] completed
```

---

## Nivel 3: Trace Cleanup Job

### Forzar limpieza manualmente

```python
import asyncio
from app.database.db import init_db
from app.database.repository import Repository

async def main():
    conn, _ = await init_db("data/wasap.db")
    repo = Repository(conn)
    deleted = await repo.cleanup_old_traces(days=0)  # borrar todo
    print(f"Deleted: {deleted} traces")
    await conn.close()

asyncio.run(main())
```

### Verificar que el job está registrado

```bash
# En los logs de startup debe aparecer:
docker compose logs wasap 2>&1 | grep "trace_cleanup\|Scheduled trace cleanup"
```

---

## Nivel 4: Dashboard

### Via eval skill en WhatsApp

```
Usuario: "mostrá el dashboard de los últimos 30 días"
→ El agente llama get_dashboard_stats(days=30)
→ Devuelve: tendencia general + desglose de últimos 7 días + scores por check
```

### Via Python

```python
import asyncio
from app.database.db import init_db
from app.database.repository import Repository

async def main():
    conn, _ = await init_db("data/wasap.db")
    repo = Repository(conn)

    trend = await repo.get_failure_trend(days=30)
    print("Trend:", trend[:3])

    scores = await repo.get_score_distribution()
    print("Scores:", scores[:5])

    await conn.close()

asyncio.run(main())
```

---

## Queries de verificación

```bash
# Ver conteo de spans por tipo
sqlite3 data/wasap.db "
SELECT kind, COUNT(*) as total, AVG(latency_ms) as avg_ms
FROM trace_spans
GROUP BY kind
ORDER BY total DESC;"

# Resumen del dashboard
sqlite3 data/wasap.db "
SELECT date(started_at) as day, COUNT(*) as total,
       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
FROM traces
GROUP BY day
ORDER BY day DESC
LIMIT 7;"
```

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| `tool_coherence`/`hallucination_check` no aparecen en scores | `guardrails_llm_checks=False` | Activar en `.env` + reiniciar |
| LLM checks siempre pasan aunque la respuesta sea mala | Timeout o error silenciado | Revisar logs `_run_async_check raised` |
| Spans de tools no aparecen | `tracing_enabled=False` | Activar tracing |
| Job de cleanup no registrado | `tracing_enabled=False` | El job se registra solo cuando `tracing_enabled=True` |
| `get_dashboard_stats` retorna "Sin datos de trazas aún" | No hay datos en DB | Interactuar con el bot con `tracing_enabled=True` primero |
