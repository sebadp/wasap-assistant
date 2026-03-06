# PRP: Fase 9 Completion — Reaction→Curation Loop (Plan 33)

## Archivos a Modificar

| Archivo | Cambio |
|---------|--------|
| `app/database/repository.py` | Nuevo método `get_trace_io_by_id(trace_id)` → `(input_text, output_text) \| None` |
| `app/webhook/router.py` | `_handle_reaction()`: agregar `wa_client` + `settings` a la firma; llamar `maybe_curate_to_dataset`; enviar prompt de corrección en reacciones muy negativas |
| `app/models.py` | Verificar que `WhatsAppReaction` tiene `from_number` (ya existe — no cambiar) |
| `tests/test_reaction_curation.py` | **Nuevo** — tests del flujo reaction→curation y reaction→correction prompt |

---

## Fases de Implementación

### Phase 1: Repository — recuperar I/O de una traza

**Objetivo:** poder reconstruir `input_text`/`output_text` desde una traza para pasarlos a `maybe_curate_to_dataset`.

- [ ] Leer el schema actual de la tabla `traces` en `app/database/db.py` para confirmar columnas disponibles (`input_text`, `output_text` o equivalentes)
- [ ] Agregar método `get_trace_io_by_id(trace_id: str) -> tuple[str, str] | None` en `repository.py`:
  ```python
  async def get_trace_io_by_id(self, trace_id: str) -> tuple[str, str] | None:
      """Return (input_text, output_text) for a trace, or None if not found."""
      row = await self._conn.fetchone(
          "SELECT input_text, output_text FROM traces WHERE id = ?", (trace_id,)
      )
      if not row:
          return None
      return row["input_text"] or "", row["output_text"] or ""
  ```
- [ ] Verificar firma actual de `maybe_curate_to_dataset()` en `app/eval/dataset.py` — confirmar que acepta `user_positive_signal: bool | None = None` (debería existir ya)

---

### Phase 2: `_handle_reaction()` — cerrar el loop

**Objetivo:** conectar reacción → score → curation → (opcional) prompt de corrección.

- [ ] Leer `_handle_reaction()` completo en `router.py` (líneas ~582-614)
- [ ] Leer el call site en `process_incoming_message()` / `webhook_post()` para entender cómo se llama `_handle_reaction`
- [ ] Agregar `wa_client` y `settings` a la firma de `_handle_reaction()`:
  ```python
  async def _handle_reaction(reaction, repository, wa_client=None, settings=None) -> None:
  ```
- [ ] Actualizar el call site para pasar `wa_client=wa_client` y `settings=settings`
- [ ] Después de guardar el score, agregar bloque de curation (best-effort, gated por `settings.eval_auto_curate`):
  ```python
  if settings and settings.eval_auto_curate:
      io = await repository.get_trace_io_by_id(trace_id)
      if io:
          input_text, output_text = io
          asyncio.create_task(
              maybe_curate_to_dataset(
                  trace_id=trace_id,
                  input_text=input_text,
                  output_text=output_text,
                  repository=repository,
                  user_positive_signal=(value >= 0.8),
              )
          )
  ```
- [ ] Para reacciones muy negativas (`value <= 0.2`), enviar prompt de corrección si `wa_client` disponible:
  ```python
  if value <= 0.2 and wa_client:
      # Check we haven't already sent a correction prompt for this trace
      existing_scores = await repository.get_trace_scores(trace_id)
      already_prompted = any(s["name"] == "correction_prompted" for s in existing_scores)
      if not already_prompted:
          await repository.save_trace_score(
              trace_id=trace_id,
              name="correction_prompted",
              value=1.0,
              source="system",
              comment="correction prompt sent after negative reaction",
          )
          asyncio.create_task(
              wa_client.send_message(
                  reaction.from_number,
                  "Vi que no te gustó mi respuesta. "
                  "¿Qué debería haber dicho? "
                  "Respondé con la respuesta correcta y la recordaré para mejorar.",
              )
          )
  ```

---

### Phase 3: Manejo de la respuesta de corrección

**Objetivo:** cuando el usuario responde al prompt de corrección, guardar el correction pair.

> **Nota:** este es el paso más complejo porque requiere correlacionar el mensaje del usuario
> con el contexto de la traza negativa previa. Hay dos enfoques posibles:
>
> **Opción A (simple):** detectar que el mensaje llega poco después de un prompt de corrección
> y tratar ese mensaje como corrección de la última interacción con score < 0.2.
>
> **Opción B (explícita):** el usuario responde al mensaje de corrección via WhatsApp reply
> (quoted message) — el `reply_context` ya es parseado por `parser.py`.
>
> Implementar **Opción A** primero como heurística simple:

- [ ] En `_run_normal_flow()` (o al inicio de `_handle_message()`), verificar si hay una traza reciente con score `correction_prompted=1.0` y sin `correction_received`:
  ```python
  # Si el mensaje parece ser una corrección (traza reciente negativa sin corrección recibida)
  recent_trace = await repository.get_latest_trace_id(phone_number)
  if recent_trace:
      scores = await repository.get_trace_scores(recent_trace)
      prompted = any(s["name"] == "correction_prompted" for s in scores)
      received = any(s["name"] == "correction_received" for s in scores)
      if prompted and not received:
          # Treat this message as a correction
          await add_correction_pair(
              trace_id=recent_trace,
              correction_text=user_text,
              repository=repository,
          )
          await repository.save_trace_score(
              trace_id=recent_trace,
              name="correction_received",
              value=1.0,
              source="human",
          )
          # Still process the message normally — don't short-circuit
  ```
- [ ] Verificar firma de `add_correction_pair()` en `app/eval/dataset.py`
- [ ] Asegurarse de que el flujo normal continúa (la corrección se guarda como background, el LLM igual procesa el mensaje)

---

### Phase 4: Tests

- [ ] Crear `tests/test_reaction_curation.py` con los siguientes tests:

  **Repository:**
  - [ ] `test_get_trace_io_by_id_returns_tuple`
  - [ ] `test_get_trace_io_by_id_returns_none_for_unknown_trace`

  **Reaction → curation:**
  - [ ] `test_positive_reaction_triggers_curation` — mock `maybe_curate_to_dataset`, verificar que se llama con `user_positive_signal=True`
  - [ ] `test_negative_reaction_triggers_curation` — verificar `user_positive_signal=False`
  - [ ] `test_reaction_curation_skipped_when_eval_auto_curate_disabled`
  - [ ] `test_reaction_curation_skipped_when_no_trace_found`

  **Reaction → correction prompt:**
  - [ ] `test_very_negative_reaction_sends_correction_prompt` — mock `wa_client.send_message`, verificar que se llama
  - [ ] `test_correction_prompt_not_sent_twice` — mock `get_trace_scores` retornando `correction_prompted`, verificar que `send_message` NO se llama
  - [ ] `test_neutral_reaction_no_correction_prompt` — score=0.5, verificar que `send_message` NO se llama

  **Correction pair:**
  - [ ] `test_message_after_correction_prompt_saved_as_correction_pair`
  - [ ] `test_correction_not_saved_when_no_pending_prompt`

---

### Phase 5: Tests, lint y documentación

- [ ] Correr `make check` (lint + typecheck + tests): all passed
- [ ] Actualizar `docs/exec-plans/README.md` — marcar plan 33 como ✅ Completado
- [ ] Crear `docs/features/33-fase9_completion.md`
- [ ] Actualizar `CLAUDE.md` con el nuevo patrón de `_handle_reaction` (firma + curation + correction prompt)
- [ ] Marcar Fase 9 como ✅ en `README.md` (ya hecho en la sesión de documentación — verificar)

---

## Diagrama de flujo post-fix

```
WhatsApp webhook (type=reaction)
  └── extract_reactions(payload)       → WhatsAppReaction(emoji, reacted_message_id, from_number)
        └── _handle_reaction(reaction, repository, wa_client, settings)
              ├── get_trace_id_by_wa_message_id(reacted_message_id)
              │     ├── None → log debug, return
              │     └── trace_id → continue
              ├── value = _REACTION_SCORE_MAP.get(emoji, 0.5)
              ├── repository.save_trace_score(trace_id, "user_reaction", value, source="user")
              │
              ├── [if eval_auto_curate]
              │     └── get_trace_io_by_id(trace_id) → (input_text, output_text)
              │           └── asyncio.create_task(
              │                 maybe_curate_to_dataset(
              │                   trace_id, input_text, output_text,
              │                   user_positive_signal=(value >= 0.8)
              │                 )
              │               )
              │
              └── [if value <= 0.2 and wa_client]
                    ├── get_trace_scores(trace_id) → check "correction_prompted"
                    │     ├── already prompted → skip
                    │     └── not prompted →
                    │           ├── save_trace_score("correction_prompted")
                    │           └── asyncio.create_task(
                    │                 wa_client.send_message(from_number, correction_prompt)
                    │               )
                    └── [next message from same user]
                          └── check "correction_prompted" without "correction_received"
                                └── add_correction_pair(trace_id, user_text)
                                      └── save_trace_score("correction_received")
```

---

## Verificación de compleción

```bash
# 1. Tests
make test

# 2. Verificar que reacciones disparan curation (manual)
# Enviar un mensaje, reaccionar con 👍, luego:
sqlite3 data/localforge.db "SELECT entry_type, input_text[:50] FROM eval_dataset ORDER BY created_at DESC LIMIT 5;"

# 3. Verificar que reacciones negativas envían prompt de corrección (manual)
# Reaccionar con 👎 y verificar que llega mensaje de corrección al WhatsApp

# 4. Verificar correction pairs (manual)
# Responder al prompt de corrección, luego:
sqlite3 data/localforge.db "SELECT entry_type, expected_output[:80] FROM eval_dataset WHERE entry_type='correction' ORDER BY created_at DESC LIMIT 5;"
```
