# Feature: Dataset Vivo de Evaluación

> **Versión**: v1.0
> **Fecha de implementación**: 2026-02-19
> **Fase**: Eval — Iteración 3
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

Convierte trazas de producción en un dataset de evaluación reutilizable de forma automática. Cada interacción completada se analiza y, si cumple criterios, se guarda en `eval_dataset` para usarla en tests de regresión, fine-tuning o análisis de calidad.

---

## Arquitectura

```
[Trace completa con scores]
        │
        ▼
maybe_curate_to_dataset(trace_id) ← background task post-reply
        │
        ▼
get_trace_scores(trace_id)
        │
   ┌────┴─────────────────────────────────┐
   │ Failure: sistema < 0.3 O usuario < 0.3│  → entry_type="failure"
   ├──────────────────────────────────────┤
   │ Golden confirmado: sistema ≥ 0.8 Y   │  → entry_type="golden", confirmed=True
   │            usuario ≥ 0.8             │
   ├──────────────────────────────────────┤
   │ Golden candidato: sistema ≥ 0.8,     │  → entry_type="golden", confirmed=False
   │            sin señal del usuario     │
   └──────────────────────────────────────┘

[Corrección high-confidence detectada]
        │
        ▼
add_correction_pair(prev_trace_id, correction_text)
        │
        ▼
entry_type="correction", expected_output=correction_text
```

---

## Schema

```sql
CREATE TABLE IF NOT EXISTS eval_dataset (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id        TEXT REFERENCES traces(id),
    entry_type      TEXT NOT NULL CHECK (entry_type IN ('golden', 'failure', 'correction')),
    input_text      TEXT NOT NULL,
    output_text     TEXT,
    expected_output TEXT,
    metadata        TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS eval_dataset_tags (
    dataset_id  INTEGER NOT NULL REFERENCES eval_dataset(id) ON DELETE CASCADE,
    tag         TEXT NOT NULL,
    PRIMARY KEY (dataset_id, tag)
);
```

> Tags como tabla join separada (no JSON array) para permitir índices eficientes.

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/database/db.py` | `DATASET_SCHEMA` — tablas `eval_dataset` y `eval_dataset_tags` |
| `app/database/repository.py` | `add_dataset_entry()`, `get_dataset_entries()`, `add_dataset_tags()`, `get_dataset_stats()` |
| `app/eval/dataset.py` | `maybe_curate_to_dataset()`, `add_correction_pair()` |
| `app/eval/exporter.py` | `export_to_jsonl()` — exporta a JSONL para tests offline |
| `app/webhook/router.py` | Integración: background task al final de `_run_normal_flow()` |

---

## Walkthrough técnico

### Curación automática (`maybe_curate_to_dataset`)

1. **Trigger**: llamada como `_track_task(asyncio.create_task(...))` al final de `_run_normal_flow()`, solo cuando `trace_ctx` existe y `eval_auto_curate=True`
2. **Fetch scores**: `repository.get_trace_scores(trace_id)` — todos los scores (system, user, human)
3. **Clasificación 3-tier** (en orden de prioridad):
   - **Failure**: cualquier score de sistema < 0.3 (guardrail fallido) o cualquier score de usuario < 0.3 (señal negativa)
   - **Golden confirmado**: todos los scores de sistema ≥ 0.8 Y al menos un score de usuario ≥ 0.8
   - **Golden candidato**: todos los scores de sistema ≥ 0.8, sin señal de usuario → guardado como golden con `metadata.confirmed=False`
4. **Persistencia**: `add_dataset_entry()` con FK a `traces(id)` — enforced por `PRAGMA foreign_keys=ON`

### Correction pairs (`add_correction_pair`)

Cuando `_detect_correction()` retorna `0.0` (high-confidence) en router.py:
1. Se obtiene la traza previa con `get_trace_with_spans(prev_trace_id)`
2. Se llama `add_correction_pair()` con `input_text` de la traza previa, `output_text` (respuesta incorrecta) y `correction_text` (lo que el usuario envió como corrección)
3. Se guarda como `entry_type="correction"` con `expected_output=correction_text`

### Export a JSONL

```python
from app.eval.exporter import export_to_jsonl
from pathlib import Path

count = await export_to_jsonl(
    repository,
    output_path=Path("data/eval/dataset.jsonl"),
    entry_type="golden",  # None para todos
    limit=1000,
)
```

Cada línea del JSONL tiene: `id`, `trace_id`, `entry_type`, `input`, `output`, `expected_output`, `metadata`, `created_at`.

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| Tags en tabla join separada | JSON array en `metadata` | Permite `CREATE INDEX` eficiente — SQL no puede indexar arrays JSON |
| Failure tiene prioridad sobre golden | Clasificación por mayoría de scores | Detectar problemas es más valioso que confirmar éxitos |
| Golden candidato (sin señal del usuario) | Solo guardar goldens confirmados | La mayoría de interacciones no tienen feedback explícito — necesitamos datos |
| `eval_auto_curate` como toggle de config | Siempre curar | Permite desactivar en dev o cuando el dataset ya es suficientemente grande |
| Background task (fire-and-forget) | Await sincrónico | No agrega latencia al usuario — curación es best-effort |
| FK enforced (`PRAGMA foreign_keys=ON`) | Sin FK o ON DELETE CASCADE | Consistencia — no puede haber dataset entries sin traza |

---

## Guía de testing

→ Ver [`docs/testing/eval_dataset_testing.md`](../testing/eval_dataset_testing.md)

---

## Variables de configuración relevantes

| Variable (`config.py`) | Default | Efecto |
|---|---|---|
| `eval_auto_curate` | `True` | Si False, no se cura automáticamente (la función existe, no se llama) |
| `tracing_enabled` | `True` | Si False, no hay `trace_ctx` y no se cura nada |
| `tracing_sample_rate` | `1.0` | Fracción de mensajes trazados → fracción que puede ser curada |

---

## Extensibilidad

**Agregar tags automáticos**: modificar `maybe_curate_to_dataset()` para extraer tags de la traza:
```python
tags = []
if "audio" in trace.get("message_type", ""):
    tags.append("audio")
await repository.add_dataset_entry(..., tags=tags)
```

**Curación manual via SQL**:
```bash
sqlite3 data/wasap.db \
  "INSERT INTO eval_dataset (trace_id, entry_type, input_text, output_text)
   SELECT id, 'golden', input_text, output_text FROM traces WHERE id = 'trace_xyz';"
```
