# Evaluación: Experiencia OpenClaw desde WasAP

> **Fecha**: 2026-02-22
> **Estado**: 📋 Evaluación — pendiente de decisión
> **Referencia**: [openclaw/openclaw](https://github.com/openclaw/openclaw) · [docs.openclaw.ai](https://docs.openclaw.ai)

---

## ¿Qué es OpenClaw?

OpenClaw es un asistente personal AI self-hosted que opera como un **agente autónomo de propósito general** conectado a múltiples canales de mensajería (WhatsApp, Telegram, Slack, Discord, Signal, iMessage, Teams, WebChat). A diferencia de Claude Code (que es un coding agent), OpenClaw es un **asistente personal completo** que puede ejecutar comandos, navegar la web, manejar cron jobs, controlar dispositivos, y gestionar procesos en background — todo desde un chat.

---

## Comparativa: OpenClaw vs WasAP (estado actual)

| Capacidad | OpenClaw | WasAP | Gap |
|---|---|---|---|
| **Canal principal** | Multi-canal (WhatsApp + 14 más) | WhatsApp only | 🟡 |
| **Shell execution** | `exec` con sandbox, yieldMs, background, timeout, host selection | ❌ No tiene | 🔴 |
| **Process management** | `process` (list/poll/log/write/kill background commands) | ❌ No tiene | 🔴 |
| **File read/write/patch** | `apply_patch` (workspace-scoped) | `read_source_file`, `write_source_file`, `apply_patch` | ✅ |
| **Git operations** | No built-in (via exec) | `git_status/diff/branch/commit/push` | ✅ WasAP mejor |
| **Browser control** | CDP integration (Chrome managed) | ❌ No tiene | 🟡 |
| **Tool loop guardrails** | Loop detection (genericRepeat, pingPong, knownPollNoProgress) | Guardrails de calidad (language, PII, coherence) | 🟡 Diferente enfoque |
| **Skills system** | ClawHub marketplace + bundled + managed + workspace skills | SkillRegistry + SKILL.md + MCP hot-install | ✅ Similar |
| **Agent workspace** | Configurable root, AGENTS.md/SOUL.md/TOOLS.md/USER.md inyectados | PROJECT_ROOT fijo, system prompt en config | 🟡 |
| **Sessions** | JSONL persistidos, session pruning, multi-agent routing | Agent sessions in-memory, no persistencia | 🔴 |
| **Background processes** | exec con background=true → process.poll para monitorear | `asyncio.create_task` (fire-and-forget) | 🔴 |
| **Cron/automation** | Cron jobs + webhooks + Gmail Pub/Sub nativos | APScheduler para cleanup jobs | 🟡 |
| **Streaming/chunking** | Block streaming + steering while streaming | No streaming (request-response) | 🟡 |
| **Model failover** | Multi-model con failover automático | Single model, no failover | 🟡 |
| **Memory** | AGENTS.md como "memory" (archivo editable) | 3 capas (semántica + episódica + snapshots) + embeddings | ✅ WasAP mejor |
| **Semantic search** | No built-in | sqlite-vec + nomic-embed-text | ✅ WasAP mejor |
| **Evaluación/tracing** | No built-in | Guardrails + Traces + Dataset vivo + Auto-evolución | ✅ WasAP mejor |
| **Voice** | Voice Wake + Talk Mode (ElevenLabs) | Whisper transcription (input only) | 🟡 |
| **Vision** | Via model capabilities | LLaVA local | ✅ Similar |
| **Security sandbox** | Docker per-session sandbox para non-main sessions | `_is_safe_path` + `AGENT_WRITE_ENABLED` flag | 🟡 |

---

## Lo que OpenClaw hace mejor (y que queremos)

### 1. `exec` — Ejecución de comandos con control de procesos 🔴

La pieza central. OpenClaw tiene un tool `exec` sofisticado:

```
exec(
    command: "pytest tests/ -v",
    timeout: 120,           # kill después de N segundos
    yieldMs: 10000,         # si no termina en 10s, mover a background
    background: false,      # o forzar background desde el inicio
    host: "sandbox|gateway|node",  # dónde ejecutar
    security: "allowlist|full",    # nivel de permisos
    ask: "on-miss|always|off",     # cuándo pedir aprobación
)
```

Y un companion tool `process` para manejar procesos en background:
```
process(action: "poll", sessionId: "abc123")   → nuevo output + exit status
process(action: "log", sessionId: "abc123", limit: 50)  → últimas 50 líneas
process(action: "kill", sessionId: "abc123")   → terminar
process(action: "list")                        → todos los procesos activos
```

**Impacto para WasAP**: esto habilita el flujo "editar → testear → arreglar". Es la feature #1 del Claude Code evaluation también.

### 2. Loop detection guardrails 🟡

OpenClaw tiene guardrails específicos para prevenir que el agente entre en loops:
- **genericRepeat**: detecta el mismo tool call con los mismos params repetido
- **knownPollNoProgress**: detecta polling repetido sin cambios en output
- **pingPong**: detecta patrón A→B→A→B sin progreso

Con thresholds configurables: warning (10), critical (20), circuit breaker global (30).

**Impacto para WasAP**: nuestro agent loop no tiene protección contra loops. El agente puede gastar sus 15 rounds haciendo lo mismo.

### 3. Bootstrap files inyectados (SOUL.md, USER.md, IDENTITY.md) 🟡

OpenClaw inyecta varios archivos markdown como contexto al agente:
- **SOUL.md** — personalidad, tono, boundaries
- **USER.md** — perfil del usuario (nombre, preferencias)
- **IDENTITY.md** — nombre del agente, emoji, "vibe"
- **TOOLS.md** — notas del usuario sobre cómo usar herramientas específicas
- **AGENTS.md** — instrucciones operativas + memoria

**Impacto para WasAP**: nosotros tenemos algo similar con `user_facts` (fact_extractor), pero no es tan structured. SOUL.md equivale a nuestro system prompt, AGENTS.md equivale a nuestro CLAUDE.md.

### 4. Sesiones persistidas como JSONL 🟡

OpenClaw guarda cada sesión como un archivo JSONL en `~/.openclaw/agents/<agentId>/sessions/<SessionId>.jsonl`. Esto permite:
- Resumir sesiones después de un restart
- Session pruning (limpieza automática)
- `sessions_history` para ver logs de otra sesión

**Impacto para WasAP**: nuestras agent sessions son in-memory y se pierden al reiniciar.

### 5. Cron/webhook automation 🟡

OpenClaw puede crear cron jobs y webhooks desde el chat:
- "Recordame todos los lunes a las 9am revisar PRs"
- Webhooks que triggerean acciones del agente

**Impacto para WasAP**: nuestro scheduler solo se usa para cleanup jobs internos. El usuario no puede crear sus propios cron jobs.

---

## Lo que WasAP hace mejor

| Feature WasAP | OpenClaw equivalente |
|---|---|
| Búsqueda semántica con embeddings | No tiene (solo archivo AGENTS.md editable) |
| 3 capas de memoria (semántica + episódica + snapshots) | Archivo AGENTS.md simple |
| Guardrails de calidad (language, PII, coherence, hallucination) | Solo loop detection |
| Trazabilidad con traces + spans + scores | No tiene |
| Dataset vivo con curación automática | No tiene |
| Auto-evolución de prompts | No tiene |
| Git tools nativos (status/diff/branch/commit/push) | Via `exec` (no nativo) |
| JSON-aware compaction de tool results | No documentado |
| Context engineering (sticky categories, user_facts injection, tool result clearing) | No documentado |

---

## Features a implementar para una experiencia OpenClaw

### Prioridad 🔴 — Sprint 1 (2-3 días)

#### F1: `run_command` + `manage_process` (exec + process de OpenClaw)

Dos tools:

1. **`run_command`**: ejecutar un comando shell con timeout y opción de background
   - `command`: string (el comando)
   - `timeout`: int (default 30s, max 300s)
   - `background`: bool (false = sync, true = async)
   - Retorna stdout+stderr si sync, o `process_id` si background
   - Allowlist configurable de comandos seguros (o HITL para desconocidos)

2. **`manage_process`**: gestionar procesos en background
   - `action`: list | poll | log | kill
   - `process_id`: string (solo para poll/log/kill)
   - `limit`: int (líneas a retornar en log)

**Archivos**: nuevo `app/skills/tools/shell_tools.py`

#### F2: Loop detection en agent loop

Detectar y abortar loops del agente:
- Track últimos N tool calls (name + params hash)
- Si se repite 3+ veces → warning message inyectado
- Si se repite 5+ veces → circuit breaker (abortar round)
- Detección de pingPong: A→B→A→B sin progreso

**Archivos**: `app/agent/loop.py` (nueva función `_check_loop_detection`)

#### F3: Coding system prompt (SOUL.md equivalente)

System prompt especializado para sesiones de coding:
```
You are a senior software engineer...
WORKFLOW: Understand → Plan → Execute → Test → Deliver
RULES: Always test after edits, use apply_patch, conventional commits
```

**Archivos**: `app/agent/loop.py` (nuevo template `_CODING_AGENT_PROMPT`)

### Prioridad 🟡 — Sprint 2 (3-4 días)

#### F4: Agent sessions persistidas (JSONL)

Guardar sesiones agénticas en disco para resumir después de restart:
- Cada round se appendea a `data/agent_sessions/<session_id>.jsonl`
- Al crear una sesión, check si existe una previa para el mismo usuario
- `/agent-resume` para continuar la última sesión

**Archivos**: `app/agent/persistence.py` (nuevo), `app/agent/loop.py`

#### F5: User-defined cron jobs

El usuario puede crear cron jobs desde el chat:
- "Recordame todos los lunes a las 9am hacer X"
- Tool `create_cron(schedule, message)` que registra en APScheduler
- Tool `list_crons()`, `delete_cron(id)`
- Persistidos en SQLite tabla `user_cron_jobs`

**Archivos**: `app/skills/tools/scheduler_tools.py` (ya existe, extender), `app/database/db.py`

#### F6: Progress updates entre rounds (equivalente a block streaming)

Mientras el agente trabaja, enviar mensajes breves al usuario:
```
📍 Leyendo app/main.py...
🔧 Aplicando patch en router.py...
🧪 Corriendo tests...
✅ 391 passed, 0 failed
📝 Commit: "fix: validate email"
```

**Archivos**: `app/agent/loop.py` (enviar WA message entre rounds)

#### F7: Bootstrap files configurables (SOUL.md, USER.md)

Archivos markdown en el workspace que se inyectan automáticamente:
- `data/workspace/SOUL.md` → personalidad del agente
- `data/workspace/USER.md` → perfil del usuario
- `data/workspace/TOOLS.md` → notas sobre uso de herramientas

**Archivos**: `app/agent/loop.py` (cargar y prepend a messages), `app/config.py`

### Prioridad 🟢 — Sprint 3 (5+ días)

#### F8: Multi-agent sessions (sessions_* tools)

Crear sesiones secundarias que pueden hablar entre sí:
- `sessions_spawn(objective)` → crea un sub-agente
- `sessions_send(session_id, message)` → enviar mensaje a otro agente
- `sessions_list()` → ver sesiones activas

**Archivos**: `app/agent/loop.py`, `app/agent/sessions.py` (nuevo)

#### F9: Browser control (CDP)

Integrar control de browser para scraping e interacción web:
- Usar Playwright o CDP directo
- Tool `browser(action, url, selector)` con actions: navigate, click, type, screenshot
- Sandbox en Docker (evitar el browser del host)

**Archivos**: `app/skills/tools/browser_tools.py` (nuevo)

#### F10: Webhooks inbound

Endpoints que triggerean acciones del agente:
- POST `/<webhook_id>` → ejecuta skill/action predefinido
- Integrable con GitHub webhooks, etc.

---

## Roadmap de convergencia

```
Sprint 1 (2-3 días)     Sprint 2 (3-4 días)      Sprint 3 (5+ días)
─────────────────────    ─────────────────────     ────────────────────
F1: run_command +        F4: Sessions JSONL        F8: Multi-agent
    manage_process       F5: User cron jobs        F9: Browser (CDP)
F2: Loop detection       F6: Progress updates      F10: Webhooks inbound
F3: Coding prompt        F7: Bootstrap files
```

Después del Sprint 1, el agente puede: leer → editar → testear → fixear → commitear.
Después del Sprint 2, el agente puede: persistir sesiones, programar tareas, y dar feedback en tiempo real.
Después del Sprint 3, el agente puede: delegar a sub-agentes, navegar la web, y reaccionar a eventos externos.

---

## Relación con el Claude Code evaluation

Este plan es **complementario** al [EX-claude_code_experience.md](EX-claude_code_experience.md):

| Feature Claude Code eval | Feature OpenClaw eval | Son la misma |
|---|---|---|
| F1: Shell Command | F1: run_command + manage_process | ✅ Sí (OpenClaw más completo) |
| F2: Test-Fix Loop | F2: Loop detection + F3: Coding prompt | ✅ Complementarios |
| F3: Diff Preview | — | OpenClaw no tiene esto nativo |
| F4: Multi-Project | — | Diferente scope |
| F5: PR Creation | — | OpenClaw usa exec para esto |
| F7: Coding Prompt | F3: Coding system prompt | ✅ Misma idea |
| F8: Progress Updates | F6: Progress updates | ✅ Misma idea |
| — | F4: Sessions persistidas | OpenClaw exclusive |
| — | F5: User cron jobs | OpenClaw exclusive |
| — | F7: Bootstrap files | OpenClaw exclusive |

**Recomendación**: fusionar ambos planes en un solo exec plan, tomando lo mejor de cada evaluación.
