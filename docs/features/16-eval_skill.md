# Feature: Eval Skill — Self-Evaluation via WhatsApp

> **Versión**: v1.0
> **Fecha de implementación**: 2026-02-19
> **Fase**: Eval — Iteración 4
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

Un skill `/eval` que permite al agente diagnosticar sus propias fallas, proponer correcciones, y alimentar el dataset — todo via WhatsApp. El usuario puede preguntarle al bot cómo le fue esta semana, ver los fallos recientes, o pedir que evalúe su respuesta en un dataset de ejemplos.

---

## Herramientas disponibles

| Tool | Descripción |
|---|---|
| `get_eval_summary(days=7)` | Resumen de métricas de los últimos N días: traces, scores promedio por fuente |
| `list_recent_failures(limit=10)` | Lista trazas con al menos un score < 0.5 |
| `diagnose_trace(trace_id)` | Deep-dive: spans, scores, input/output completo de una traza |
| `propose_correction(trace_id, correction)` | Propone qué debería haberse respondido (guarda correction pair) |
| `add_to_dataset(trace_id, entry_type)` | Curación manual de una traza al dataset |
| `get_dataset_stats()` | Composición del dataset: totales por tipo y top tags |
| `run_quick_eval(category="all")` | Eval offline contra correction pairs del dataset (sin tool loop) |

---

## Arquitectura

```
[Usuario: "revisá cómo te fue esta semana"]
        │
        ▼
classify_intent → ["evaluation"]
        │
        ▼
select_tools → [get_eval_summary]
        │
        ▼
execute_tool_loop → get_eval_summary(days=7)
        │
        ▼
repository.get_eval_summary(7) → dict con scores agregados
        │
        ▼
LLM formatea la respuesta en lenguaje natural
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `skills/eval/SKILL.md` | Definición del skill (frontmatter + instrucciones para el LLM) |
| `app/skills/tools/eval_tools.py` | Implementación de los 7 tools + `register()` |
| `app/skills/router.py` | `TOOL_CATEGORIES["evaluation"]` — el classifier incluye la categoría |
| `app/skills/tools/__init__.py` | `register_builtin_tools()` llama `eval_tools.register()` si `tracing_enabled` |
| `app/database/repository.py` | `get_eval_summary()`, `get_failed_traces()`, `cleanup_old_traces()` |

---

## Walkthrough técnico

### Registración

```python
# app/skills/tools/__init__.py
if settings is not None and settings.tracing_enabled:
    from app.skills.tools.eval_tools import register as register_eval
    register_eval(registry, repository, ollama_client=ollama_client)
```

Las tools son closures sobre `repository` y `ollama_client`. El skill solo se activa cuando `tracing_enabled=True` (sin trazas no hay datos que evaluar).

### Clasificación

```python
# app/skills/router.py — TOOL_CATEGORIES
"evaluation": [
    "get_eval_summary", "list_recent_failures", "diagnose_trace",
    "propose_correction", "add_to_dataset", "get_dataset_stats",
    "run_quick_eval",
]
```

`classify_intent()` usa `", ".join(TOOL_CATEGORIES.keys())` dinámicamente — no hay que actualizar el `CLASSIFIER_PROMPT` manualmente.

### run_quick_eval — sin recursión

`run_quick_eval` usa `ollama_client.chat()` directo (sin tools), comparando la respuesta del LLM plano contra el `expected_output` del dataset. **No** pasa por `execute_tool_loop` para evitar un tool loop anidado.

Métrica usada: word overlap (palabras compartidas / palabras esperadas) — simple pero efectiva sin necesitar un juez LLM adicional.

---

## Flujos de uso

**Diagnóstico semanal:**
```
Usuario: "¿cómo te fue esta semana?"
→ get_eval_summary(days=7)
→ "Tuve 155 interacciones. Score promedio sistema: 0.87. 3 fallos de idioma."
```

**Revisión de fallos:**
```
Usuario: "mostrá los últimos fallos"
→ list_recent_failures(limit=5)
→ "trace_abc: min_score=0.0, input: 'qué es el clima...'"

Usuario: "el tercero fue error mío, agregalo como golden"
→ add_to_dataset(trace_id="trace_abc", entry_type="golden")
→ "Trace agregada como golden."
```

**Proponer corrección:**
```
Usuario: "en trace_xyz debiste decir 'Buenos Aires'"
→ propose_correction(trace_id="trace_xyz", correction="Buenos Aires")
→ "Correction pair guardado."
```

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| Guard `tracing_enabled` para registrar | Siempre registrar | Sin trazas no hay datos; las queries fallarían silenciosamente |
| `run_quick_eval` con `chat()` directo | Pasar por `execute_tool_loop` | Evita recursión: tool loop dentro de otro tool loop no es soportado |
| Métrica de word overlap | LLM judge | No requiere Ollama call adicional; suficiente para señal rápida |
| `propose_correction` guarda correction pair directo | Solo mostrar la sugerencia | Permite que el dataset se alimente desde la conversación |

---

## Guía de testing

→ Ver [`docs/testing/16-eval_skill_testing.md`](../testing/16-eval_skill_testing.md)
