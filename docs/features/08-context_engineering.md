# Feature: Context Engineering

> **Versión**: v1.0
> **Fecha de implementación**: 2026-02-22
> **Fase**: Fase 5 (post Agent Mode)
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

El sistema de context engineering garantiza que el agente mantenga coherencia entre mensajes consecutivos: recuerda qué herramientas se usaron en el turno anterior, inyecta datos del usuario (como su username de GitHub) directamente en el loop de herramientas, y evita que los resultados crudos de las APIs acumulen tokens innecesarios en la ventana de contexto.

---

## Arquitectura

```
[Mensaje del usuario]
         │
         ▼
[Phase C: classify_intent]
  ↑ recibe: últimos 6 mensajes (contexto)
  ↑ recibe: sticky_categories (turno anterior)
  └ fallback automático si retorna "none"
         │
         ▼
[execute_tool_loop]
  ↑ inyecta: user_facts como system message
    ("GitHub username: sebadp")
  ↑ recibe: sticky_categories, recent_messages
         │
         ▼ (por cada iteración)
    [Tool call] → resultado → [_clear_old_tool_results]
                                  ↑ reemplaza payloads viejos
                                  ↑ con resumen de 1 línea
         │
         ▼
[LLM reply]
         │
         ▼
[Guardrails]
    si fallan: _save_self_correction_memory
               ↑ cooldown 2h por tipo de check
               ↑ cleanup automático cada hora (TTL 24h)
         │
         ▼
[save_sticky_categories → conversation_state DB]

─────────────────── MODO AGENTE ───────────────────

[Objetivo del usuario]
         │
         ▼
[run_agent_session — outer loop (max 15 rounds)]  ← Fase 4
    │
    ├── Inyectar task plan como system message
    ├── execute_tool_loop (max 8 tools/round)
    ├── ¿Completo? (sin [ ] pendientes) → break
    └── _clear_old_tool_results(keep_last_n=2)
         │
         ▼
[Mensaje final al usuario con plan status]
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/context/fact_extractor.py` | Extrae user_facts desde memorias con regex (sin LLM) |
| `app/context/conversation_context.py` | Dataclass de estado conversacional + factory async |
| `app/skills/router.py` | `classify_intent()` con contexto conversacional y sticky fallback |
| `app/skills/executor.py` | `execute_tool_loop()` con inyección de facts + tool result clearing |
| `app/database/db.py` | Tabla `conversation_state` para sticky categories |
| `app/database/repository.py` | Métodos get/save/clear_sticky_categories + self-correction queries |
| `app/formatting/compaction.py` | Compactación JSON-aware (3 niveles: JSON → LLM → truncate) |
| `app/webhook/router.py` | Orquestación: carga sticky, extrae facts, persiste categorías |
| `app/main.py` | Scheduler de cleanup de self-corrections (cada hora) |
| `app/agent/loop.py` | Loop agéntico con control de iteraciones, task plan injection, clearing |

---

## Walkthrough técnico: cómo funciona

### 1. Carga de sticky categories y user_facts (Phase C)

Al llegar un mensaje, después de cargar las memorias (Phase B), el router:

1. Llama `repository.get_sticky_categories(conv_id)` — una query SQLite que retorna las categorías del turno anterior (ej: `["github"]`)
2. Extrae `user_facts` de las memorias cargadas con `extract_facts()` — regex puro, ~0.5ms
3. Si el `classify_task` retorna `"none"` pero hay `sticky_categories` o historial, vuelve a clasificar pasando contexto

→ `app/webhook/router.py` (Phase C block)

### 2. Clasificación contextual

```python
# Se arma un bloque de contexto con los últimos 3 turnos
recent_context = """
Recent conversation (for context only):
User: Muéstrame mis repositorios de GitHub
Assistant: Encontré 49 repositorios. Los más recientes son...
User: Ambos        ← este mensaje no tiene contexto sin lo anterior
"""
```

El clasificador ve el mensaje ambiguo en contexto y puede resolverlo. Si igual retorna `"none"`, el sticky fallback activa las categorías del turno anterior.

→ `app/skills/router.py:classify_intent()`

### 3. Inyección de user_facts en el tool loop

Antes del primer LLM call con herramientas, se inserta un system message:

```
Known user facts (use these directly, do not ask the user again):
- GitHub username: sebadp
- Name: Sebastián
```

Esto previene que el LLM use el nombre del dueño de la instalación (ej: `sebastiandavila`) en vez del username del usuario (ej: `sebadp`) al llamar tools de GitHub.

→ `app/skills/executor.py:execute_tool_loop()` — bloque "Inject user facts"

### 4. Tool result clearing

Después de la iteración 2 del tool loop, los resultados anteriores se compactan:

```
[Previous result processed — summary: [{"name": "wasap-assistant"...]
```

Esto libera espacio de contexto siguiendo el principio de Anthropic: _"once a tool has been called deep in the message history, why would the agent need to see the raw result again?"_

→ `app/skills/executor.py:_clear_old_tool_results()`

### 5. Compactación JSON-aware

Cuando un tool retorna más de 4000 caracteres:

1. **JSON extraction** (nuevo, sin LLM): Si el payload es JSON válido, extrae campos clave (`name`, `full_name`, `html_url`, `language`, etc.) preservando valores exactos
2. **LLM summarization** (fallback): Prompt con regla explícita "NEVER substitute with [placeholder]"
3. **Hard truncate** (último recurso): truncado plano con aviso

El paso 1 resuelve el bug donde el LLM de compactación reemplazaba `"wasap-assistant"` con `"[repo-name-1]"`.

→ `app/formatting/compaction.py:compact_tool_output()` y `_try_json_extraction()`

### 6. Persistencia de sticky categories

Al final de cada turno, el router persiste las categorías usadas:

- Si se usaron tools → `save_sticky_categories(conv_id, ["github"])` en background
- Si no se usaron tools → `clear_sticky_categories(conv_id)` en background

→ `app/webhook/router.py` — bloque "Persist sticky categories for next turn"

### 7. Self-correction con cooldown

Cuando los guardrails detectan un problema:

1. Se consultan las correcciones recientes (últimas 2h)
2. Si el mismo tipo de check ya tiene una corrección → se omite (evita spam)
3. Si es un check nuevo → se guarda solo en DB (no en MEMORY.md, evitando el loop del watcher)
4. Un cleanup scheduler expira correcciones >24h cada hora en background

→ `app/webhook/router.py:_save_self_correction_memory()`

### 8. Agent loop con control propio de iteraciones (Modo Agente)

El modo agente tiene ahora un loop externo propio, separado del tool loop interno:

```
Para iteration in range(max_iterations=15):
    1. _inject_task_plan()  → re-inyecta el plan como system message
    2. execute_tool_loop(max_tools=8)  → 1 ronda de hasta 8 tool calls
    3. _is_session_complete()?  → si plan sin [ ] pendientes: break
    4. _clear_old_tool_results(keep_last_n=2)  → libera contexto
```

**Capacidad efectiva**: 8 tools/round × 15 rounds = hasta 120 tool calls por sesión.

**Completion detection**: el check primario es si el `task_plan` no tiene `[ ]` pendientes (determinista). Si no hay plan, se usan señales de texto (`"completad"`, `"done"`, etc.).

**Mensaje final**: incluye resumen del plan (`_Plan: 7 pasos completados, 0 pendientes._`).

→ `app/agent/loop.py:run_agent_session()`, `_inject_task_plan()`, `_is_session_complete()`


## Cómo extenderla

### Agregar nuevos tipos de user_facts

Editar `app/context/fact_extractor.py`:

```python
_FACT_PATTERNS.append((
    "preferred_editor",
    re.compile(r"(?:usa|prefiere)\s+(vscode|vim|emacs)", re.IGNORECASE),
))
```

El nuevo fact se propagará automáticamente al tool loop como:
```
- Preferred editor: vscode
```

### Agregar campos a la extracción JSON

Editar `_JSON_KEY_FIELDS` en `app/formatting/compaction.py`:

```python
_JSON_KEY_FIELDS.append("merged_at")  # para PRs mergeados
```

### Cambiar el tiempo de cooldown de self-corrections

En `app/webhook/router.py`:
```python
recent = await repository.get_recent_self_corrections(hours=4)  # de 2h a 4h
```

O cambiar el TTL:
```python
await repository.cleanup_expired_self_corrections(ttl_hours=48)  # de 24h a 48h
```

### Cambiar la estrategia del agent loop

- **Rounds por sesión**: `AgentSession(max_iterations=N)` al crear la sesión
- **Tools por round**: constante `_TOOLS_PER_ROUND = 8` en `app/agent/loop.py`
- **Tool result clearing**: parámetro `keep_last_n` en `_clear_old_tool_results()`
- **Señales de completion por texto**: lista `completion_signals` en `_is_session_complete()`

---

## Guía de testing

→ Ver [`docs/testing/08-context_engineering_testing.md`](../testing/08-context_engineering_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| Regex para user_facts, sin LLM | LLM dedicado para extractar facts | Latencia 0, determinista, sin costo de tokens |
| Sticky categories (1 turno) | Memoria de largo plazo de categorías | Evita que categorías viejas contaminen conversaciones nuevas |
| JSON extraction antes de LLM | Solo LLM para compactar | El LLM hallucina placeholders; JSON extraction es exacto |
| Cooldown por tipo de check | Cooldown global | Permite guardar errores nuevos sin bloquear todo |
| `conversation_state` en SQLite | En memoria (dict) | Sobrevive reinicios del container; ya tenemos SQLite |
| Tool result clearing (keep_last_n=2) | Clearing agresivo (keep_last_n=1) | Conservador — los últimos 2 resultados son los más útiles |
| Outer agent loop (15 rounds × 8 tools) | Un solo execute_tool_loop(max_tools=15) | Control explícito de contexto; permite clearing entre rounds |
| Completion por `[ ]` en task plan | Completion solo por señales de texto | Determinista; señales de texto son ambiguas en respuestas largas |

---

## Gotchas y edge cases

- **El `classify_task` corre en paralelo con Phase A/B**, por lo que cuando llega a Phase C ya tiene la respuesta del LLM. El re-classify solo ocurre cuando esa respuesta es `"none"` Y hay historial o sticky categories disponibles — agrega ~0.5s solo en ese caso excepcional.

- **Las sticky categories se persisten en background** (`asyncio.create_task`). Si el proceso se reinicia entre el reply y el task completion, el primer follow-up del usuario puede no tener sticky categories. Esto es aceptable — el segundo follow-up ya las tendrá.

- **`fact_extractor` solo captura el primer match de cada tipo**. Si el usuario tiene dos memorias contradictorias (ej: dos github usernames), gana la primera en orden de ID. El consolidador de memorias debería resolver las contradicciones antes de que lleguen aquí.

- **JSON extraction no funciona con payloads que son texto plano o Markdown**. En ese caso, el sistema pasa directamente al LLM summarizer — comportamiento idéntico al anterior.

- **El `user_facts` system message se inserta después del system message principal** (índice 1), no al final del historial. Esto es intencional: los facts de usuario deben tener alta prioridad de atención.

- **El task plan re-injection reemplaza el mensaje anterior** (busca `"CURRENT TASK PLAN"` en los system messages). Si se insertara uno nuevo cada round, el historial se llenaría de planes duplicados.

- **Si el agente no llama `create_task_plan` en el primer round**, el campo `session.task_plan` es `None` y `_is_session_complete()` cae al check de señales de texto. El agente eventualmente llega a `max_iterations` y se envía el último reply al usuario.

---

## Variables de configuración relevantes

| Variable (`config.py`) | Default | Efecto |
|---|---|---|
| `max_tools_per_call` | `8` | Cuántas tools se ofrecen al LLM por iteración |
| `conversation_max_messages` | `20` | Cuántos mensajes se pasan como `recent_messages` al classifier |
| `guardrails_enabled` | `True` | Si está en `False`, no se generam self-corrections |
