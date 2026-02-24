# Plan de Implementación — Context Engineering

> Documento técnico que baja la intención "El agente pierde contexto entre iteraciones,
> clasifica mal follow-ups, y la compactación destruye información clave" a cambios
> concretos en el codebase de WasAP.
>
> **Basado en**: [Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) (Anthropic, 2025)
> y el análisis de bugs de la sesión de debugging del 22/02/2026.

---

## Resumen de Fases

| Fase | Capacidad | Dependencias | Archivos principales |
|------|-----------|-------------|------|
| 1 | `ConversationContext` + Classifier contextual + Sticky Categories | Ninguna | `app/context/`, `router.py`, `executor.py` |
| 2 | Compactación JSON-aware + Tool Result Clearing | Fase 1 | `compaction.py`, `executor.py` |
| 3 | Self-Correction con cooldown + TTL | Ninguna | `router.py`, `repository.py` |
| 4 | Agent Loop propio (separar de tool loop) | Fase 2 | `agent/loop.py`, `agent/models.py` |

### Contexto: por qué este plan

En las pruebas de producción del 22/02, el agente mostró 3 tipos de falla:

1. **Clasificación incorrecta de follow-ups**: El usuario dice "Ambos" (refiriéndose a repos
   públicos y privados) → el classifier ve una palabra sin contexto → `categories=none` → responde
   sin usar herramientas de GitHub.
2. **Compactación destruye identifiers**: La API de GitHub devuelve 15KB → el LLM de compactación
   resume como `[repo-name-1], [repo-name-2]` → el usuario ve placeholders en vez de nombres reales.
3. **Loop de guardrails → self-correction → memory watcher**: Cada guardrail failure genera una
   memoria de autocorrección que el watcher intenta sincronizar, generando ruido.

El artículo de Anthropic de 2025 sobre context engineering propone principios que mapean directamente
a estos problemas:

| Principio Anthropic | Problema WasAP | Solución propuesta |
|---|---|---|
| "Context as finite resource" | Contexto se llena con tool results crudos | Tool result clearing |
| "Just-in-time retrieval" | Se pre-cargan todos los datos sin filtrar | `user_facts` on-demand |
| "Structured note-taking" | El tool loop pierde coherencia entre iteraciones | Scratchpad |
| "Compaction preserves decisions" | Compactación destruye identifiers | JSON-aware extraction |
| "Minimal viable tool set" | Classifier no sabe qué tools dar | Sticky categories |

---

## Fase 1: ConversationContext + Classifier Contextual

### Objetivo

Crear un objeto de contexto que fluya por todo el pipeline de procesamiento de mensajes,
reemplazando la lógica dispersa en `_handle_message`. Este objeto lleva el estado conversacional
(facts del usuario, categorías recientes, scratchpad) a los subsistemas que lo necesitan.

### Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `app/context/__init__.py` | [NEW] Package init |
| `app/context/conversation_context.py` | [NEW] `ConversationContext` dataclass + builder |
| `app/context/fact_extractor.py` | [NEW] Extracción de user facts desde memorias |
| `app/skills/router.py` | Modificar `classify_intent` para recibir contexto |
| `app/skills/executor.py` | Modificar `execute_tool_loop` para inyectar facts |
| `app/webhook/router.py` | Usar `ConversationContext` en `_handle_message` |
| `app/database/repository.py` | Agregar `get_sticky_categories` / `save_sticky_categories` |
| `app/database/migrations.py` | Agregar tabla `conversation_state` |

### Schema de datos

#### Tabla `conversation_state` (nueva)

```sql
CREATE TABLE IF NOT EXISTS conversation_state (
    conversation_id INTEGER PRIMARY KEY,
    sticky_categories TEXT DEFAULT '[]',    -- JSON array de categorías recientes
    last_tool_categories TEXT DEFAULT '[]', -- Categorías del último turno con tools
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);
```

#### `ConversationContext` dataclass

```python
# app/context/conversation_context.py
from __future__ import annotations

from dataclasses import dataclass, field
from app.models import ChatMessage


@dataclass
class ConversationContext:
    """State object that flows through the message pipeline.
    
    Replaces the ad-hoc variable passing in _handle_message.
    Every subsystem can read what it needs from this object.
    """
    # Identity
    phone_number: str
    user_text: str
    conv_id: int
    
    # Pre-fetched data (build phase)
    user_facts: dict[str, str] = field(default_factory=dict)
    memories: list[str] = field(default_factory=list)
    history: list[ChatMessage] = field(default_factory=list)
    summary: str | None = None
    daily_logs: str | None = None
    
    # Routing state
    sticky_categories: list[str] = field(default_factory=list)
    current_categories: list[str] = field(default_factory=list)
    
    # Tool loop state (Fase 2)
    scratchpad: str = ""
    
    # Metadata
    query_embedding: list[float] | None = None

    @classmethod
    async def build(
        cls,
        phone_number: str,
        user_text: str,
        repository,
        memory_repository,
        conversation_manager,
        **kwargs,
    ) -> ConversationContext:
        """Factory: fetch all necessary data in parallel and return a ready context."""
        import asyncio
        
        conv_id = await conversation_manager.get_conversation_id(phone_number)
        
        # Parallel fetches
        memories_task = memory_repository.get_active_memories()
        history_task = conversation_manager.get_history(phone_number)
        summary_task = repository.get_latest_summary(conv_id)
        sticky_task = repository.get_sticky_categories(conv_id)
        
        memories, history, summary, sticky = await asyncio.gather(
            memories_task, history_task, summary_task, sticky_task,
        )
        
        # Extract structured facts from memories
        from app.context.fact_extractor import extract_facts
        user_facts = extract_facts(memories)
        
        return cls(
            phone_number=phone_number,
            user_text=user_text,
            conv_id=conv_id,
            user_facts=user_facts,
            memories=memories,
            history=history,
            summary=summary,
            sticky_categories=sticky,
            **kwargs,
        )
```

#### Extractor de Facts

```python
# app/context/fact_extractor.py
"""Extract structured facts from memory strings using pattern matching.

No LLM calls — this is a fast, deterministic extraction.
"""
import re

# Patterns to extract known fact types from free-text memories
_FACT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("github_username", re.compile(
        r"(?:github|usuario.*github|github.*user(?:name)?)\s+(?:es|is|:)\s+(\S+)",
        re.IGNORECASE,
    )),
    ("name", re.compile(
        r"(?:se llama|nombre.*es|(?:my )?name is)\s+([A-ZÁ-Ú]\w+(?:\s+[A-ZÁ-Ú]\w+)?)",
        re.IGNORECASE,
    )),
    ("language", re.compile(
        r"(?:prefiere|habla|idioma.*es|speaks?)\s+(\w+)",
        re.IGNORECASE,
    )),
]


def extract_facts(memories: list[str]) -> dict[str, str]:
    """Extract key-value facts from a list of memory strings."""
    facts: dict[str, str] = {}
    for mem in memories:
        for fact_key, pattern in _FACT_PATTERNS:
            match = pattern.search(mem)
            if match and fact_key not in facts:
                facts[fact_key] = match.group(1).strip()
    return facts
```

### Classifier contextual

```python
# Cambios en app/skills/router.py

_CLASSIFIER_PROMPT_TEMPLATE = (
    "Classify this message into tool categories. "
    'Reply with ONLY category names separated by commas, or "none".\n'
    "Categories: {categories}, none\n\n"
    "{recent_context}"  # <-- NUEVO: últimos mensajes como contexto
    "Message: {user_message}"
)


async def classify_intent(
    user_message: str,
    ollama_client: OllamaClient,
    recent_messages: list[ChatMessage] | None = None,   # <-- NUEVO
    sticky_categories: list[str] | None = None,         # <-- NUEVO
) -> list[str]:
    """Classify with conversational context."""
    
    # Build recent context string (last 3 user+assistant turns)
    recent_context = ""
    if recent_messages:
        context_lines = []
        for msg in recent_messages[-6:]:  # last 3 turns = 6 messages
            role = "User" if msg.role == "user" else "Assistant"
            context_lines.append(f"{role}: {msg.content[:150]}")
        recent_context = (
            "Recent conversation for context:\n"
            + "\n".join(context_lines)
            + "\n\n"
        )
    
    categories_str = ", ".join(TOOL_CATEGORIES.keys())
    prompt = _CLASSIFIER_PROMPT_TEMPLATE.format(
        categories=categories_str,
        user_message=user_message,
        recent_context=recent_context,
    )
    
    # ... existing LLM call ...
    
    # NUEVO: If classifier returns "none" but we have sticky categories, use them
    if categories == ["none"] and sticky_categories:
        logger.info("Classifier returned none, using sticky categories: %s", sticky_categories)
        return sticky_categories
    
    return categories
```

### Decisiones de diseño

- **Facts sin LLM.** El extractor usa regex, no LLM. Esto es intencional: la extracción debe ser
  rápida (<1ms), determinista, y no costar tokens. Si una memoria no matchea, simplemente no se
  extrae como fact — no es crítico que sea exhaustivo. Los patrones se pueden expandir incrementalmente.

- **Sticky categories con TTL implícito.** Se guardan las categorías del último turno que usó tools.
  Si el siguiente turno no tiene tools, las sticky categories se limpian. Esto evita que categorías
  viejas contaminen clasificaciones futuras. El TTL es "1 turno sin tools".

- **`ConversationContext` es inmutable post-build.** El builder hace todos los fetches en paralelo
  y construye un snapshot. Los subsistemas lo leen pero no lo mutan (excepto `scratchpad` que es
  append-only durante el tool loop).

---

## Fase 2: Compactación JSON-aware + Tool Result Clearing

### Objetivo

Mejorar la compactación de tool outputs para preservar información crítica (nombres, IDs, URLs)
y reducir el uso de contexto limpiando tool results de iteraciones anteriores en el tool loop.

### Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `app/formatting/compaction.py` | Agregar `_try_json_extraction`, mejorar prompt LLM |
| `app/skills/executor.py` | Agregar tool result clearing entre iteraciones |

### Compactación JSON-aware

```python
# app/formatting/compaction.py

import json

# Fields to preserve per API type (extensible)
_JSON_KEY_FIELDS: dict[str, list[str]] = {
    "default": ["name", "full_name", "id", "title", "description", "html_url", "url",
                 "updated_at", "created_at", "language", "state", "number"],
    "github_repos": ["name", "full_name", "description", "html_url", "language",
                     "stargazers_count", "updated_at", "private"],
    "github_issues": ["number", "title", "state", "html_url", "created_at", "user"],
}


def _try_json_extraction(text: str, max_length: int = 6000) -> str | None:
    """Try to extract key fields from a JSON payload without using LLM.
    
    Returns a compact JSON string with only the relevant fields, or None
    if the text is not valid JSON or can't be meaningfully compressed.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    
    # GitHub API: paginated responses with "items" key
    if isinstance(data, dict) and "items" in data:
        items = data["items"]
        return _extract_items(items, "default", max_length, 
                              total=data.get("total_count"))
    
    # Direct list response (e.g., list_issues, list_pull_requests)
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        return _extract_items(data, "default", max_length)
    
    return None


def _extract_items(items: list[dict], profile: str, max_length: int, 
                   total: int | None = None) -> str:
    """Extract key fields from a list of items."""
    key_fields = _JSON_KEY_FIELDS.get(profile, _JSON_KEY_FIELDS["default"])
    
    extracted = []
    for item in items:
        entry = {}
        for k in key_fields:
            if k in item:
                val = item[k]
                # Flatten nested dicts (e.g., user.login)
                if isinstance(val, dict) and "login" in val:
                    entry[k] = val["login"]
                else:
                    entry[k] = val
        extracted.append(entry)
    
    # Build result, truncating items if too long
    while extracted:
        result = json.dumps(extracted, indent=2, ensure_ascii=False)
        if total:
            result += f"\n\n(Showing {len(extracted)} of {total} total results)"
        if len(result) <= max_length:
            return result
        # Remove last item and try again
        extracted.pop()
    
    return None


async def compact_tool_output(tool_name, text, user_request, ollama_client, 
                               max_length=4000):
    """Compact a large tool output to fit within the context budget.
    
    Strategy (ordered by preference):
    1. If small enough, return as-is
    2. Try JSON-aware extraction (no LLM cost)
    3. Fall back to LLM summarization
    4. Hard truncate as last resort
    """
    if len(text) <= max_length:
        return text
    
    # Step 1: JSON-aware extraction
    structured = _try_json_extraction(text, max_length)
    if structured:
        logger.info("Compacted %s via JSON extraction: %d → %d chars",
                    tool_name, len(text), len(structured))
        return structured
    
    # Step 2: LLM compaction (existing, with improved prompt)
    return await _llm_compact(tool_name, text, user_request, ollama_client, max_length)
```

### Tool Result Clearing

Siguiendo la recomendación de Anthropic: "once a tool has been called deep in the message history,
why would the agent need to see the raw result again?"

```python
# En app/skills/executor.py — dentro de execute_tool_loop, después de cada iteración:

def _clear_old_tool_results(messages: list[ChatMessage], keep_last_n: int = 2) -> None:
    """Replace old tool results with short summaries to free context space.
    
    Keeps the last `keep_last_n` tool results intact (most recent are most useful).
    Older results are replaced with a one-line placeholder.
    """
    tool_indices = [i for i, m in enumerate(messages) if m.role == "tool"]
    
    if len(tool_indices) <= keep_last_n:
        return
    
    for idx in tool_indices[:-keep_last_n]:
        old_content = messages[idx].content
        # Keep first line as summary
        first_line = old_content.split("\n")[0][:100]
        messages[idx] = ChatMessage(
            role="tool",
            content=f"[Previous result: {first_line}…]",
        )
```

### Decisiones de diseño

- **JSON extraction antes de LLM.** La extracción es determinista, instantánea, y preserva
  los identifiers exactos. El LLM solo se usa como fallback para payloads que no son JSON.
  
- **Profiles extensibles.** El dict `_JSON_KEY_FIELDS` permite agregar perfiles por API
  (e.g., `"github_repos"`, `"github_issues"`) sin cambiar la lógica de extracción.

- **Tool result clearing conservativo.** Siempre mantiene los últimos 2 tool results intactos.
  Esto es un punto de partida seguro; se puede hacer más agresivo después de testear.

---

## Fase 3: Self-Correction con Cooldown + TTL

### Objetivo

Evitar que los guardrails generen un flujo continuo de memorias `self_correction` que contaminan
el contexto y generan loops en el memory watcher.

### Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `app/webhook/router.py` | Agregar cooldown a `_save_self_correction_memory` |
| `app/database/repository.py` | Agregar `get_recent_self_corrections()`, `cleanup_expired_self_corrections()` |

### Implementación

```python
# En app/database/repository.py

async def get_recent_self_corrections(self, hours: int = 2) -> list[Memory]:
    """Return self_correction memories created in the last N hours."""
    cursor = await self._conn.execute(
        "SELECT id, content, category, active, created_at FROM memories "
        "WHERE category = 'self_correction' AND active = 1 "
        "AND created_at > datetime('now', ?)",
        (f"-{hours} hours",),
    )
    rows = await cursor.fetchall()
    return [
        Memory(id=r[0], content=r[1], category=r[2], active=bool(r[3]), created_at=r[4])
        for r in rows
    ]


async def cleanup_expired_self_corrections(self, ttl_hours: int = 24) -> int:
    """Deactivate self_correction memories older than TTL."""
    cursor = await self._conn.execute(
        "UPDATE memories SET active = 0 "
        "WHERE category = 'self_correction' AND active = 1 "
        "AND created_at < datetime('now', ?)",
        (f"-{ttl_hours} hours",),
    )
    await self._conn.commit()
    return cursor.rowcount
```

```python
# En app/webhook/router.py — _save_self_correction_memory

async def _save_self_correction_memory(user_text, failed_checks, repository, ...):
    checks_str = ", ".join(failed_checks)
    
    # Cooldown: skip if we already have a recent correction for these checks
    recent = await repository.get_recent_self_corrections(hours=2)
    recent_check_types = set()
    for m in recent:
        # Parse check types from existing corrections
        if "detectaron:" in m.content:
            existing = m.content.split("detectaron: ")[1].split(".")[0]
            recent_check_types.update(c.strip() for c in existing.split(","))
    
    new_checks = [c for c in failed_checks if c not in recent_check_types]
    if not new_checks:
        logger.info("Self-correction skipped: cooldown active for %s", checks_str)
        return
    
    # Only record the new check types
    note = (
        f"[auto-corrección] Al responder '{user_text[:60]}...', "
        f"los guardrails detectaron: {', '.join(new_checks)}. "
        f"Recordar evitar este tipo de error."
    )
    await repository.add_memory(note, category="self_correction")
    # No memory file sync — self_correction stays in DB only (ya parcheado en Fase anterior)
```

### Cleanup periódico

Llamar `cleanup_expired_self_corrections()` en el startup de la app o en un background task:

```python
# En app/main.py, después de inicializar:
async def _periodic_cleanup(repository):
    while True:
        await asyncio.sleep(3600)  # cada hora
        count = await repository.cleanup_expired_self_corrections(ttl_hours=24)
        if count:
            logger.info("Cleaned up %d expired self-correction memories", count)
```

### Decisiones de diseño

- **Cooldown por tipo de check, no global.** Si `language_match` ya tiene una corrección reciente
  pero `no_pii` es nueva, se guarda solo la de `no_pii`. Esto evita perder señales legítimas.

- **TTL de 24h.** Las self-corrections son útiles en el corto plazo para que el agente ajuste su
  comportamiento, pero no deben acumularse indefinidamente. 24h es suficiente para cubrir una sesión
  de trabajo típica.

---

## Fase 4: Agent Loop con Control Propio de Iteraciones

### Objetivo

Separar el agent loop del tool loop. Actualmente `run_agent_session` delega completamente a
`execute_tool_loop` con `max_tools=15`, pero `execute_tool_loop` tiene un hardcoded
`MAX_TOOL_ITERATIONS = 5`, así que el agente nunca ejecuta más de 5 iteraciones de herramientas.
Además, no hay tool result clearing entre iteraciones del agente.

### Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `app/agent/loop.py` | Implementar loop propio con tool clearing y task plan injection |
| `app/agent/models.py` | Agregar campo `scratchpad: str` |

### Implementación

```python
# app/agent/loop.py — reemplazar la llamada directa a execute_tool_loop

async def run_agent_session(session, ollama_client, skill_registry, wa_client, mcp_manager):
    # ... existing setup code ...
    
    session_registry = _register_session_tools(session, skill_registry, wa_client)
    
    system_content = _AGENT_SYSTEM_PROMPT.format(objective=session.objective)
    messages: list[ChatMessage] = [
        ChatMessage(role="system", content=system_content),
        ChatMessage(role="user", content=session.objective),
    ]
    
    for iteration in range(session.max_iterations):
        session.iteration = iteration
        logger.info("Agent iteration %d/%d", iteration + 1, session.max_iterations)
        
        # Inject task plan as system message if it exists
        if session.task_plan:
            plan_msg = ChatMessage(
                role="system",
                content=_PLAN_REMINDER.format(task_plan=session.task_plan),
            )
            # Replace or append plan reminder
            _update_or_append_plan(messages, plan_msg)
        
        # Run one round of tool execution (reuses existing tool loop)
        reply = await execute_tool_loop(
            messages=messages,
            ollama_client=ollama_client,
            skill_registry=session_registry,
            mcp_manager=mcp_manager,
            max_tools=8,  # per-iteration tool cap
        )
        
        # Tool result clearing between agent iterations
        _clear_old_tool_results(messages, keep_last_n=2)
        
        # Check if the agent considers itself done
        if _is_complete(reply, session):
            break
        
        messages.append(ChatMessage(role="assistant", content=reply))
    
    # ... existing delivery code ...


def _is_complete(reply: str, session: AgentSession) -> bool:
    """Heuristic: the agent is done if there are no pending tasks or it says so."""
    if session.task_plan and "[ ]" in session.task_plan:
        return False  # Still has pending tasks
    completions = ["completad", "terminad", "done", "finished", "listo"]
    return any(word in reply.lower() for word in completions)
```

### Decisiones de diseño

- **Reutilización de `execute_tool_loop` por iteración.** En lugar de reimplementar el loop
  desde cero, se llama `execute_tool_loop` una vez por iteración del agente. Esto preserva
  la lógica de dispatching, compactación, y tracing existente.

- **`max_tools=8` por iteración, `max_iterations=15` por sesión.** Esto permite hasta 120
  tool calls en total (8×15), pero con clearing de contexto entre cada ronda de 8.

- **`_is_complete` es una heurística.** No es perfecta, pero es simple y funciona como
  primera línea de defensa contra loops infinitos. El `max_iterations` es el safety net.

---

## Orden de implementación

1. **Fase 1** — `ConversationContext` + classifier contextual (sin dependencias, mayor impacto)
2. **Fase 2** — JSON-aware compaction + tool clearing (depende parcialmente de Fase 1)
3. **Fase 3** — Self-correction cooldown (independiente, puede ir en paralelo)
4. **Fase 4** — Agent loop propio (depende de Fase 2 para tool clearing)

> Fases 1 y 3 se pueden implementar en paralelo ya que tocan archivos diferentes.
> Fase 2 depende parcialmente de Fase 1 (para el scratchpad), pero la compactación JSON-aware
> se puede implementar de forma independiente.

## Decisiones de diseño transversales

### ¿Por qué no usar un "planning LLM" separado para clasificar?
Un modelo dedicado al routing podría ser más preciso, pero agrega latencia (~500ms) y
complejidad operacional (otro modelo para mantener). La solución de sticky categories +
contexto conversacional resuelve el 80% de los problemas sin costo operacional adicional.

### ¿Por qué extracción JSON antes de LLM para compactar?
El LLM de compactación tiene un defecto fundamental: puede hallucinar placeholders como
`[repo-name]` en lugar de preservar el valor real `wasap-assistant`. La extracción JSON
es determinista y preserva los valores exactos. No hay riesgo de hallucination.

### ¿Son revertibles estos cambios?
Sí. Cada fase introduce abstracciones sobre el código existente sin reemplazarlo:
- `ConversationContext.build()` es un wrapper sobre las mismas queries que ya hacía `_handle_message`
- La compactación JSON-aware es un paso previo al LLM compactor existente
- Sticky categories es un fallback — el classifier original sigue funcionando igual
- Self-correction cooldown solo agrega un `if` antes de grabar

### ¿Overhead de performance?
- **Fase 1**: Una query SQL extra (sticky categories) + regex fact extraction (~1ms)
- **Fase 2**: Un `json.loads()` attempt (~5ms) antes del LLM call que ya hacemos
- **Fase 3**: Una query SQL extra (recent corrections) antes de guardar
- **Fase 4**: Sin overhead adicional — reorganización de control flow
