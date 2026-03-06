# Testing Manual: Context Engineering

> **Feature documentada**: [`docs/features/08-context_engineering.md`](../features/08-context_engineering.md)
> **Requisitos previos**: Container corriendo (`docker compose up -d`), modelos de Ollama disponibles.

---

## Verificar que la feature está activa

Al arrancar el container, buscar en los logs:

```bash
docker compose logs -f localforge | head -80
```

Confirmar las siguientes líneas:
- `Self-correction cleanup: ...` (o que el scheduler arrancó sin error)
- `sqlite-vec loaded successfully` *(opcional, para semantic search)*

Para verificar que la tabla nueva existe:

```bash
sqlite3 data/localforge.db ".schema conversation_state"
# Debe mostrar: CREATE TABLE IF NOT EXISTS conversation_state (...)
```

---

## Casos de prueba principales

### A. Sticky Categories (follow-ups ambiguos)

El caso más importante. Reproducir el bug original:

| Paso | Mensaje enviado | Resultado esperado |
|------|----------------|-------------------|
| 1 | `"Listar mis repositorios de GitHub"` | El agente llama `search_repositories` y lista repos con nombres reales |
| 2 | `"Ambos"` *(refiriéndose a repos públicos y privados)* | El agente sigue usando tools de GitHub — NO responde como chat genérico |
| 3 | `"Los de los últimos meses"` | El agente filtra repos por fecha, sigue en contexto GitHub |
| 4 | `"Cuántos hay en total"` | Responde con el número de repos, sigue en contexto |

**Verificar en logs**:
```bash
docker compose logs -f localforge 2>&1 | grep -E "sticky|fallback|categories"
```

Debe verse:
```
Classifier returned 'none', falling back to sticky categories: ['github']
```

O si el contexto ayudó a clasificar correctamente:
```
Tool router: categories=['github'], selected N tools: [...]
```

**Verificar en DB** (después del paso 1):
```bash
sqlite3 data/localforge.db "
SELECT c.phone_number, cs.sticky_categories, cs.updated_at
FROM conversation_state cs
JOIN conversations c ON c.id = cs.conversation_id
ORDER BY cs.updated_at DESC LIMIT 5;
"
```
Debe mostrar `["github"]` para el número del usuario.

---

### B. User Facts: inyección de github_username

| Paso | Acción | Resultado esperado |
|------|--------|-------------------|
| 1 | Guardar una memoria: `"Mi usuario de GitHub es sebadp"` (vía `/memory` o conversación normal) | La memoria queda en DB |
| 2 | Pedir: `"Abrí un issue en localforge-assistant sobre el bug de fechas"` | El agente crea el issue usando `sebadp/localforge-assistant`, no un username inventado |
| 3 | Pedir: `"Listá mis pull requests"` | El agente lista PRs bajo `sebadp`, no el nombre del owner de la instalación |

**Verificar en logs**:
```bash
docker compose logs -f localforge 2>&1 | grep "user_facts"
```

Debe verse:
```
Extracted user_facts from memories: ['github_username']
Injected user_facts into tool loop: ['github_username']
```

---

### C. JSON-aware Compaction (sin placeholders)

| Paso | Acción | Resultado esperado |
|------|--------|-------------------|
| 1 | Pedir: `"Listar todos mis repositorios"` (si tiene >15 repos) | El agente lista repos **con nombres reales** como `localforge-assistant`, `portfolio`, etc. |
| 2 | El usuario ve nombres reales, NO `[repo-name-1]`, `[repo-name-2]` | ✅ |

**Verificar en logs**:
```bash
docker compose logs -f localforge 2>&1 | grep -i "compact"
```

Si el payload fue grande:
```
Tool 'search_repositories' compacted via JSON extraction: 18432 → 2841 chars
```

Si el payload era JSON válido pero cayó en LLM (raro):
```
Tool 'X' compacted via LLM: N → M chars
```

---

### D. Tool Result Clearing (eficiencia de contexto)

Este caso es difícil de observar directamente; se verifica por ausencia de problemas en iteraciones largas.

| Escenario | Resultado esperado |
|-----------|-------------------|
| El agente hace 4+ tool calls en una sola respuesta | No se produce OOM ni respuestas incoherentes en iteraciones 4/5 |

**Verificar en logs** (iteraciones múltiples):
```bash
docker compose logs -f localforge 2>&1 | grep "Tool iteration"
```

Debe mostrar:
```
Tool iteration 1: LLM generated 3 tool call(s): [...]
Tool iteration 2: LLM decided to reply directly: ...
```

---

### E. Self-correction Cooldown

| Paso | Acción | Resultado esperado |
|------|--------|-------------------|
| 1 | Provocar un guardrail failure (ej: responder en inglés cuando el usuario escribió en español) | Se guarda UNA corrección en DB |
| 2 | Provocar el mismo tipo de fallo 5 minutos después | **No** se guarda una segunda corrección |
| 3 | Repetir después de 2h | Se guarda correctamente (cooldown expirado) |

**Verificar cooldown activo**:
```bash
docker compose logs -f localforge 2>&1 | grep "Self-correction"
```

Debe verse:
```
Self-correction skipped (cooldown active for: language_match)
```

**Verificar en DB**:
```bash
sqlite3 data/localforge.db "
SELECT id, content, created_at
FROM memories
WHERE category = 'self_correction' AND active = 1
ORDER BY created_at DESC LIMIT 10;
"
```

---

### F. Agent Loop — Control de iteraciones (Modo Agente)

Requiere haber activado una sesión agéntica (`/agent <objetivo>`).

| Paso | Acción / Verificación | Resultado esperado |
|------|----------------------|-------------------|
| 1 | Enviar: `/agent Abrí un issue en localforge-assistant con el título 'Test de context engineering'` | El agente inicia, crea un task plan y ejecuta en rounds |
| 2 | Verificar logs: `grep "Agent session .* round"` | Debe mostrar rondas numeradas: `round 1/15`, `round 2/15`, etc. |
| 3 | Verificar que el plan se re-inyecta | Logs: `grep "CURRENT TASK PLAN"` en debug |
| 4 | Al completar, el mensaje de WhatsApp incluye el resumen del plan | `_Plan: N pasos completados, 0 pendientes._` |
| 5 | Verificar que NO se usaron más de 8 tool calls en un mismo round | Logs: `grep "Tool iteration"` debe mostrar máx. 8 por ronda |

**Verificar rounds en logs**:
```bash
docker compose logs -f localforge 2>&1 | grep -E "Agent session|round [0-9]+/"
```

Debe verse:
```
Agent session abc123 started for +549...: Abrí un issue...
Agent session abc123 — round 1/15
Agent session abc123 — round 2/15
Agent session abc123: detected completion at round 2
Agent session abc123 completed after 2 round(s)
```

**Verificar clearing entre rounds**:
```bash
docker compose logs -f localforge 2>&1 | grep "Previous result processed"
```

---

## Edge cases y validaciones

| Escenario | Resultado esperado |
|---|---|
| Usuario sin ninguna memoria guardada | `user_facts={}`, sin inyección de facts — funciona normalmente |
| Usuario con memoria de github_username en formato diferente (`"GitHub: sebadp"`) | Regex lo captura igual |
| Payload de tool que NO es JSON (ej: texto plano) | Compactación LLM normal — sin cambios respecto al comportamiento anterior |
| `conversation_state` no tiene fila para esta conversación | `get_sticky_categories()` retorna `[]` — sin error |
| Dos guardrail failures de distintos tipos en el mismo turno | Se guardan ambos — cooldown es por tipo, no global |
| Agente no crea task plan en el primer round | `_is_session_complete()` usa señales de texto; agente sigue hasta `max_iterations` |
| Task plan con todos los pasos ya marcados `[x]` desde el primer round | Completion detectada en round 1 — no itera más |
| Sesión agéntica cancelada a mitad de un round (CancelledError) | El agente envía `"🛑 Sesión agéntica cancelada."` y limpia el estado |

---

## Verificar en logs

```bash
# Clasificación e intent routing
docker compose logs -f localforge 2>&1 | grep -E "Tool router|sticky|fallback"

# User facts
docker compose logs -f localforge 2>&1 | grep -E "user_facts|Injected"

# Compactación
docker compose logs -f localforge 2>&1 | grep -i "compact"

# Self-correction
docker compose logs -f localforge 2>&1 | grep -i "self.correction\|guardrail"

# Errores
docker compose logs -f localforge 2>&1 | grep -i "error\|exception" | grep -v "DeprecationWarning"
```

---

## Queries de verificación en DB

```bash
# Sticky categories actuales por conversación
sqlite3 data/localforge.db "
SELECT c.phone_number, cs.sticky_categories, cs.updated_at
FROM conversation_state cs JOIN conversations c ON c.id = cs.conversation_id
ORDER BY cs.updated_at DESC LIMIT 10;
"

# Self-corrections activas (no expiradas)
sqlite3 data/localforge.db "
SELECT id, content, created_at FROM memories
WHERE category = 'self_correction' AND active = 1
ORDER BY created_at DESC;
"

# Cuántas self-corrections se expirarían hoy (TTL 24h)
sqlite3 data/localforge.db "
SELECT COUNT(*) FROM memories
WHERE category = 'self_correction' AND active = 1
AND created_at < datetime('now', '-24 hours');
"

# Verificar que conversation_state tabla existe
sqlite3 data/localforge.db ".tables" | grep conversation_state
```

---

## Verificar graceful degradation

El sistema está diseñado para degradar gracefully: si cualquier componente falla, el chat sigue funcionando sin context engineering.

**Simular fallo de sticky categories**:
1. Borrar datos de la tabla: `sqlite3 data/localforge.db "DELETE FROM conversation_state;"`
2. Enviar un follow-up ambiguo
3. Verificar que el sistema responde (quizás sin contexto, pero sin error)

**Simular fallo de fact_extractor**:
1. El extractor tiene un `try/except` que loguea y continúa — no hay un "fallo" visible
2. Verificar en logs: `grep "user_facts extraction failed"`

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| Sticky categories no funcionan entre mensajes | La tabla `conversation_state` no existe (DB antigua) | Reiniciar el container — el schema se aplica en startup con `CREATE TABLE IF NOT EXISTS` |
| `"Ambos"` sigue sin contexto aunque el turno anterior usó GitHub | La tarea background de `save_sticky_categories` no completó antes del siguiente mensaje | Verificar que no hay errores en `grep "Could not save sticky_categories"` |
| Nombres reales no aparecen en la respuesta | El payload era texto plano (no JSON), cayó en LLM compaction | Verificar logs: `grep "compact"` para ver qué método se usó |
| `github_username` no se extrae de la memoria | Formato no matchea ningún patrón regex | Agregar el patrón en `fact_extractor.py` y reiniciar |
| Self-corrections se siguen guardando más de una vez | El formato del campo `detectaron:` en el note cambió | Verificar que el parsing del cooldown coincide con el formato actual |
| El agente se detiene en el round 1 sin terminar el objetivo | `_is_session_complete()` detectó señal falsa de texto | Revisar si la respuesta del LLM contiene palabras como `"listo"` fuera de contexto; agregar task plan para usar completion determinista |
| El agente itera todos los 15 rounds sin completar | Objetivo demasiado ambicioso o tools insuficientes | Reducir el scope del objetivo; verificar que los tools de GitHub están configurados |

---

## Variables relevantes para testing

| Variable (`.env`) | Valor recomendado para test | Efecto |
|---|---|---|
| `GUARDRAILS_ENABLED` | `true` | Activa el pipeline de guardrails (necesario para probar cooldown) |
| `MAX_TOOLS_PER_CALL` | `8` | Cuántas tools por iteración |
| `CONVERSATION_MAX_MESSAGES` | `20` | Cuántos mensajes históricos pasan como contexto al classifier |

### Agent loop específico

| Constante (`agent/loop.py`) | Default | Efecto |
|---|---|---|
| `_TOOLS_PER_ROUND` | `8` | Tool calls máximos por round agéntico |
| `max_iterations` (parámetro de sesión) | `15` | Rounds máximos por sesión |
