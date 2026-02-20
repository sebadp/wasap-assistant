# Feature: Señales de Usuario para Evaluación

> **Versión**: v1.0
> **Fecha de implementación**: 2026-02-19
> **Fase**: Eval — Iteración 2
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

El sistema captura señales de calidad de las respuestas directamente desde el usuario, sin necesidad de encuestas ni fricción:

1. **Reacciones de WhatsApp** (👍 ❤️ 😂 😮 😢 👎 🙏): cuando el usuario reacciona a un mensaje del bot, esa reacción se convierte automáticamente en un score de calidad
2. **`/feedback <texto>`**: permite dar feedback en lenguaje natural; el bot analiza el sentimiento y lo convierte en un score numérico
3. **`/rate <1-5>`**: calificación explícita escala Likert
4. **Detección de correcciones**: el sistema detecta automáticamente cuando el usuario corrige al bot y registra una penalización en la traza anterior

---

## Arquitectura

```
[Usuario reacciona 👍 a mensaje WA]
        │
        ▼
POST /webhook → extract_reactions() → _handle_reaction()
        │
        ▼
repository.get_trace_id_by_wa_message_id(wa_message_id)
        │
        ▼
repository.save_trace_score(name="user_reaction", value=1.0, source="user")

[Usuario escribe /feedback estuvo bien pero faltó detalle]
        │
        ▼
cmd_feedback() → ollama_client.chat() → sentiment score 0.0-1.0
        │
        ▼
repository.save_trace_score(name="human_feedback", source="human")

[Usuario escribe "eso no es lo que te pregunté"]
        │
        ▼
_detect_correction() → score 0.0 (high-confidence)
        │
        ▼
repository.save_trace_score(trace_id=PREV_trace, name="user_correction", source="system")
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/models.py` | `WhatsAppReaction` model |
| `app/webhook/parser.py` | `extract_reactions()` — parseo de reacciones del payload WA |
| `app/webhook/router.py` | `_handle_reaction()`, `_REACTION_SCORE_MAP`, `_detect_correction()`, `_is_repeated_question()` |
| `app/commands/builtins.py` | `cmd_feedback()`, `cmd_rate()` |
| `app/database/repository.py` | `get_latest_trace_id()`, `save_trace_score()`, `get_recent_user_message_embeddings()` |

---

## Walkthrough técnico: cómo funciona

### Reacciones WA

1. **Payload llega** a `POST /webhook` → `router.py:incoming_webhook`
2. **Extracción**: `extract_reactions(payload)` en `parser.py` — busca `msg.type == "reaction"`, extrae `reacted_message_id` y `emoji`. NO agrega "reaction" a `_SUPPORTED_TYPES` (bypass del pipeline normal)
3. **Procesamiento async**: `background_tasks.add_task(_handle_reaction, reaction, repository)` — fire-and-forget, sin dedup, sin rate limit
4. **Vinculación a traza**: `repository.get_trace_id_by_wa_message_id(reacted_message_id)` — usa el índice `idx_traces_wa_msg` para O(1) lookup
5. **Score**: `_REACTION_SCORE_MAP[emoji]` → valor 0.0-1.0 → `save_trace_score(source="user")`

### Comandos /feedback y /rate

1. **Parsing**: `parse_command("/feedback texto")` → `cmd_feedback(args="texto", ctx)` en `builtins.py`
2. **Última traza**: `ctx.repository.get_latest_trace_id(ctx.phone_number)` — la traza más reciente completada del usuario
3. **Sentiment** (`/feedback`): `ollama_client.chat([...prompt de scoring...])` → float 0.0-1.0
4. **Persistencia**: `save_trace_score(name="human_feedback"|"human_rating", source="human")`

### Detección de correcciones

1. **Trigger**: al inicio de `_run_normal_flow()`, si hay `trace_ctx` y `user_text`
2. **Patterns**: dos tiers — `_CORR_HIGH_RE` (ej: "no era eso", "eso es incorrecto") → score 0.0; `_CORR_LOW_RE` → score 0.3
3. **Score en traza anterior**: `repository.get_latest_trace_id(phone)` → `save_trace_score(trace_id=prev_trace_id)` — la penalización se aplica a la respuesta problemática, no al mensaje de corrección

---

## Cómo extenderla

**Agregar un emoji nuevo al score map:**
```python
# app/webhook/router.py — _REACTION_SCORE_MAP
_REACTION_SCORE_MAP["🔥"] = 0.95  # muy positivo
```

**Agregar un patrón de corrección:**
```python
# app/webhook/router.py — _CORRECTION_PATTERNS_HIGH
_CORRECTION_PATTERNS_HIGH.append(r"te equivocaste")
```

**Agregar un comando de feedback nuevo:** seguir el patrón de `cmd_rate` en `builtins.py` + `registry.register()` en `register_builtins()`.

---

## Guía de testing

→ Ver [`docs/testing/eval_user_signals_testing.md`](../testing/eval_user_signals_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| Reacciones en path separado (no `_SUPPORTED_TYPES`) | Agregar "reaction" al pipeline normal | Evitar dedup, rate limit, `_handle_message` — las reacciones no son mensajes conversacionales |
| Score en traza ANTERIOR para correcciones | Score en traza actual | La corrección evalúa la respuesta previa, no la corrección misma |
| Sentiment analysis via LLM para `/feedback` | Score fijo (0.5) | Convierte feedback cualitativo en señal cuantitativa accionable |
| Patrones high/low confidence separados | Un solo conjunto de patrones | Reduce falsos positivos; "no" solo no es corrección, "eso es incorrecto" casi siempre lo es |
| `_is_repeated_question()` como placeholder | Implementar embeddings por mensaje | Requiere tabla adicional y overhead de embed por mensaje; diferido a iteración futura |

---

## Gotchas y edge cases

- **Sin traza previa**: si el usuario hace `/rate 5` pero no hubo interacción trazada aún (tracing_enabled=False o primera sesión), el comando devuelve "No encontré una interacción reciente"
- **Reacción a mensaje sin `wa_message_id`**: si la traza no tiene `wa_message_id` (test environment, wa_client falló), `get_trace_id_by_wa_message_id` retorna None → reacción ignorada silenciosamente
- **Emoji fuera del mapa**: emojis no listados en `_REACTION_SCORE_MAP` reciben score 0.5 (neutral)
- **Detección de correcciones con tracing desactivado**: el bloque de detección está dentro de `if trace_ctx`, así que si tracing está off, no se detectan correcciones (trade-off deliberado — sin traza, no hay dónde guardar el score)
- **`/feedback` sin Ollama**: si `ollama_client` es None o falla, el sentiment defaultea a 0.5 (neutral) y el feedback se guarda igual

---

## Variables de configuración relevantes

| Variable (`config.py`) | Default | Efecto |
|---|---|---|
| `tracing_enabled` | `True` | Si False, detección de correcciones y señales implícitas no corren |
| `tracing_sample_rate` | `1.0` | Fracción de mensajes trazados; reacciones siempre se procesan (independiente del rate) |
