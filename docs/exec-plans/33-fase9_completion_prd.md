# PRD: Fase 9 Completion — Reaction→Curation Loop (Plan 33)

## Objetivo y Contexto

La Fase 9 (Evaluación y Mejora Continua) está implementada en su mayoría: guardrails,
trazabilidad, `/feedback`, `/rate`, reacciones de WhatsApp, dataset vivo, auto-evolución de
prompts. Sin embargo, hay un gap en el ciclo de feedback implícito:

**Gap actual**: cuando un usuario reacciona con 👍 o 👎 a un mensaje, se guarda un score en
`trace_scores` (`user_reaction`) pero el pipeline de dataset curation **no se dispara**. La
señal queda registrada pero no cierra el loop hacia el dataset de entrenamiento.

**Estado de lo que ya existe:**
- `extract_reactions()` en `parser.py` — parsea reacciones del webhook ✅
- `_handle_reaction()` en `router.py` — busca `trace_id` por `wa_message_id`, guarda score ✅
- `maybe_curate_to_dataset()` — curación 3-tier con señal positiva/negativa ✅
- `_REACTION_SCORE_MAP` — mapeo emoji → float (👍=1.0, 👎=0.0, ❤️=1.0, ...) ✅

**Lo que falta**: conectar `_handle_reaction()` con `maybe_curate_to_dataset()` para que las
reacciones alimenten el dataset automáticamente, cerrando el loop de mejora continua.

---

## Alcance (In Scope & Out of Scope)

### In Scope

1. **Reaction → dataset curation**: `_handle_reaction()` llama `maybe_curate_to_dataset()`
   con el `trace_id` encontrado y la señal de usuario derivada del score del emoji.
   - Score >= 0.8 → `user_positive_signal=True` (promueve a golden confirmado si el sistema también pasó)
   - Score <= 0.2 → `user_positive_signal=False` (promueve a failure, dispara corrección automática si hay correction memory)

2. **Reaction → correction pair prompt**: cuando la reacción es muy negativa (score <= 0.2),
   enviar un mensaje al usuario preguntando "¿Qué debería haber respondido?". Si responde,
   guardar como correction pair via `add_correction_pair()`.

3. **Tests**: cobertura del nuevo flujo reaction→curation y reaction→correction_prompt.

4. **Repository method**: `get_message_content_by_trace_id()` para recuperar el input/output
   del trace al momento de curar (necesario para construir el dataset entry correctamente).

### Out of Scope

- Cambiar el esquema de `trace_scores` o `eval_dataset`
- A/B testing de reacciones por tipo de mensaje
- Reacciones a mensajes del usuario (solo reacciones a mensajes del bot)
- Análisis de patrones de reacciones en el tiempo (eso es dashboard)
- Corrección proactiva automática sin intervención humana

---

## Casos de Uso Críticos

### 1. Reacción positiva → golden confirmado

**Flujo:**
1. Bot responde un mensaje, guarda `wa_message_id` en la traza
2. Usuario reacciona con 👍
3. WhatsApp envía webhook de tipo `reaction`
4. `_handle_reaction()` encuentra `trace_id`, score=1.0
5. `maybe_curate_to_dataset(user_positive_signal=True)` → entry tipo `golden_confirmed`

**Resultado:** el dataset crece con ejemplos de calidad validados por el usuario.

### 2. Reacción negativa → failure + prompt de corrección

**Flujo:**
1. Bot responde, usuario reacciona con 👎
2. `_handle_reaction()` score=0.0 → `maybe_curate_to_dataset(user_positive_signal=False)` → `failure`
3. Bot envía al usuario: "Vi que no te gustó mi respuesta. ¿Qué debería haber dicho? (respondé a este mensaje con la respuesta correcta)"
4. Usuario responde → `add_correction_pair()` con el texto del usuario como `expected_output`

**Resultado:** failure en dataset + correction pair para reentrenamiento offline.

### 3. Reacción a mensaje sin traza

**Flujo:**
1. Usuario reacciona a un mensaje antiguo (sin traza o con traza expirada)
2. `get_trace_id_by_wa_message_id()` retorna `None`
3. `_handle_reaction()` loguea debug y retorna sin error

**Resultado:** best-effort, no explota.

### 4. Curation ya corrió para esa traza

**Flujo:**
1. `maybe_curate_to_dataset()` es llamado con un `trace_id` que ya tiene un entry en `eval_dataset`
2. La función detecta duplicado y no inserta (ya existe lógica de FK + UNIQUE en el schema)

**Resultado:** idempotente, no genera duplicados.

---

## Restricciones Arquitectónicas / Requerimientos Técnicos

- **Best-effort**: todo en `_handle_reaction()` debe estar en try/except — nunca propagar excepciones
- **Background task**: curation y el prompt de corrección se lanzan como `asyncio.create_task`, no bloquean el handler de la reacción
- **`maybe_curate_to_dataset()` ya acepta `user_positive_signal`**: verificar firma actual antes de modificar
- **`settings.eval_auto_curate`**: la curation vía reacción debe respetar este flag (igual que la curation normal)
- **No enviar prompt de corrección en loop**: si el usuario ya recibió un prompt de corrección para esa traza, no enviar otro. Usar `trace_scores` para detectar si ya se procesó.
- **`wa_client` en `_handle_reaction`**: actualmente la función no recibe `wa_client`. Necesita recibirlo para enviar el prompt de corrección. Modificar firma y call site.
- **El `user_text` e `output_text` para la curation**: `maybe_curate_to_dataset()` requiere `input_text` y `output_text`. Deben recuperarse desde la traza via `repository`.
