# Testing Guide: Context Engineering v2

## Tests automatizados

```bash
make test
# O específicamente:
.venv/bin/python -m pytest tests/test_token_estimator.py tests/test_context_builder.py tests/test_context_windowing.py -v
```

Todos los tests nuevos: 22 tests, 0 failures.

## Verificación manual de Token Budget

Enviar un mensaje simple y verificar en logs:

```bash
# Buscar en logs
grep "context.budget" logs/app.log

# Output esperado para "hola":
# context.budget: ~300-500 estimated tokens (2 msgs, 1 system)

# Output esperado para conversación larga:
# context.budget: ~1500-2500 estimated tokens (9 msgs, 1 system)
# (8 verbatim + 1 system consolidado)
```

Para mensajes que excedan el 80% del límite:
```
context.budget.near_limit: XXXXX estimated tokens (82% of 32000)
```

## Verificación de XML consolidation

Verificar que el system message llegue consolidado:

```bash
# Activar DEBUG logging
LOG_LEVEL=DEBUG python -m app.main

# Buscar en logs el system message (via tracing si habilitado)
# O agregar temporalmente un logger.debug en _build_context()
```

El system message debe verse así:
```
You are a helpful personal assistant...

<user_memories>
Important user information:
- Me llamo Sebastián
...
</user_memories>

<recent_activity>
...
</recent_activity>

<capabilities>
...
</capabilities>
```

## Verificación de History Windowing

Con más de 8 mensajes en historial:

```bash
# DB query para ver cuántos mensajes hay
sqlite3 data/wasap.db "SELECT COUNT(*) FROM messages WHERE conversation_id = (SELECT id FROM conversations LIMIT 1);"

# Si hay >8, los logs deben mostrar windowing activo
# ConversationContext build usa get_windowed_history
```

Verificar que el summary de mensajes viejos aparece en el contexto cuando hay >8 mensajes.

## Verificación de Capabilities Filtering

### Caso: mensaje sin tools ("hola")

```
classify_intent → ["none"]
```

En logs:
```
context.capabilities: skipped (has_tools=True, categories=['none'])
```

El system message NO debe contener `<capabilities>` section.

### Caso: mensaje con tools ("qué hora es")

```
classify_intent → ["time"]
```

En logs:
```
context.capabilities: filtered to categories ['time']
```

El system message debe contener solo herramientas de `time` (get_current_datetime, etc.).

## Verificación de Memory Threshold

Ajustar `MEMORY_SIMILARITY_THRESHOLD` a un valor bajo (ej. 0.1) para ver el filtrado:

```env
MEMORY_SIMILARITY_THRESHOLD=0.1
```

En logs:
```
context.memories: 2/8 passed threshold (0.10)
```

Si ninguna pasa:
```
context.memories: fallback to top-3 (none passed threshold)
```

## Verificación del Agent Scratchpad

### Test manual en sesión agéntica

Iniciar una sesión con `/agent buscar un archivo en el proyecto`:

1. En el round 1, el agente puede escribir en el reply:
   ```
   Encontré el archivo en app/skills/router.py
   <scratchpad>
   Key finding: router.py at app/skills/router.py — contains TOOL_CATEGORIES dict
   </scratchpad>
   ```

2. Verificar en logs:
   ```
   Agent session XYZ: scratchpad updated (45 chars)
   ```

3. En el round 2, el system message debe incluir:
   ```
   <scratchpad_context>
   Key finding: router.py at app/skills/router.py — contains TOOL_CATEGORIES dict
   </scratchpad_context>
   ```

## Edge cases

### sqlite-vec no disponible

Con `vec_available=False`, el build debe usar `get_active_memories(limit=K)` como fallback.
No debe fallar ni propagar excepciones.

### Embedding falla

Si Ollama no responde para el embed, `ctx.query_embedding = None` y:
- Memories: fallback a `get_active_memories()`
- Notes: lista vacía
- Sin threshold filtering

### History sin summary

Si hay 15 mensajes pero no se ha generado summary aún (< threshold):
```
(history[-8:], None)
```
Sin sección `<conversation_summary>` en el system message.

## DB queries útiles

```sql
-- Ver cuántos mensajes tiene una conversación
SELECT c.phone_number, COUNT(*) as msg_count
FROM conversations c
JOIN messages m ON m.conversation_id = c.id
GROUP BY c.phone_number;

-- Ver el summary más reciente
SELECT c.phone_number, s.summary_text, s.created_at
FROM conversation_summaries s
JOIN conversations c ON c.id = s.conversation_id
ORDER BY s.created_at DESC
LIMIT 5;

-- Ver memorias de un usuario
SELECT content, active FROM memories
ORDER BY created_at DESC LIMIT 20;
```
