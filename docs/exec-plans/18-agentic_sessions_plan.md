# Plan de Implementación — Sesiones Agénticas (Agent Mode)

> Documento técnico que baja la intención de producto "El asistente puede trabajar de forma autónoma,
> crear branches, editar código, y abrir PRs" a cambios concretos en el codebase de WasAP.
>
> **Revisión 1** — Basada en investigación de OpenClaw, ManusIA, Claude Code, y Antigravity.

---

## Estado de Implementación

- [x] Fase 0: Write tools (write_source_file, apply_patch) en selfcode_tools.py
- [x] Fase 0: Config toggle `agent_write_enabled` en app/config.py
- [x] Fase 1: `app/agent/models.py` — AgentSession, AgentStatus dataclasses
- [x] Fase 1: `app/agent/loop.py` — run_agent_session() con outer loop (15 rounds × 8 tools)
- [x] Fase 1: `app/agent/__init__.py` — Package init
- [x] Fase 2: `app/agent/task_memory.py` — create_task_plan, update_task_status, get_task_plan
- [x] Fase 2: Task plan re-inyectado entre rounds en loop.py
- [x] Fase 3: `app/skills/tools/git_tools.py` — git_status, git_create_branch, git_commit, git_push, git_create_pr
- [x] Fase 4: `app/agent/hitl.py` — request_user_approval, resolve_hitl
- [x] Fase 4: Integración HITL en webhook/router.py (resolve_hitl antes del flujo normal)
- [x] Fase 4: HITL callback inyectado en execute_tool_loop desde agent/loop.py


---

## Resumen de Fases

| Fase | Capacidad | Dependencias | Archivos principales |
|------|-----------|-------------|------|
| 0 | Prerequisitos: write tools + `<think>` strip + context compaction | Ninguna | `client.py`, `compaction.py`, `selfcode_tools.py` |
| 1 | Agent Loop asincrónico | Fase 0 | `app/agent/loop.py`, `app/agent/models.py`, `router.py` |
| 2 | Markdown Task Memory | Fase 1 | `app/agent/task_memory.py`, `prompt_builder.py` |
| 3 | Git & PR tools | Fase 0 | `app/skills/tools/git_tools.py` |
| 4 | Human-in-the-Loop (HITL) | Fases 1+2 | `app/agent/hitl.py`, `router.py` |

### Prerequisitos transversales

Antes de empezar cualquier fase, hay cambios de infraestructura ya aplicados o pendientes:

**1. Compactación de contexto para tool outputs (`app/formatting/compaction.py`)**

Ya implementado. Cuando un tool devuelve un payload mayor a ~4000 chars, se comprime via
un LLM auxiliar que resume el contenido relevante. Esto es **crítico** para las sesiones
agénticas porque el agente iterará múltiples veces con tools que pueden devolver texto largo.

**2. Stripping de `<think>` tags (`app/llm/client.py`)**

Ya implementado. El cliente Ollama elimina bloques `<think>...</think>` antes de retornar
el contenido. Esto es imprescindible para evitar que el razonamiento interno del LLM
contamine el historial del agente durante iteraciones largas.

**3. `selfcode_tools.py` ya tiene capacidades de lectura read-only.**

Funciones existentes: `read_source_file`, `list_source_files`, `search_source_code`,
`get_recent_logs`, `get_version_info`. Estas serán reutilizadas en el Agent Loop.

**4. `project_tools.py` ya tiene tracking de tareas.**

Funciones existentes: `create_project`, `add_task`, `update_task`, `project_progress`.
Estas se pueden integrar al Agent Loop para el seguimiento de progreso persistente.

---

## Fase 0: Write Tools — Ampliar `selfcode_tools.py`

### Objetivo
Actualmente el asistente puede **leer** su propio código fuente pero **no puede escribir**.
Para que pueda actuar como agente de software, necesita herramientas de escritura con
controles de seguridad estrictos.

### Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `app/skills/tools/selfcode_tools.py` | Agregar `write_source_file`, `apply_patch` |
| `app/config.py` | Agregar `agent_write_enabled: bool = False` (safety toggle) |

### Nuevas herramientas

```python
# En selfcode_tools.py — dentro de register()

async def write_source_file(path: str, content: str) -> str:
    """Write content to a file within the project. Creates the file if it doesn't exist.

    Safety: Only allows writing within PROJECT_ROOT. Blocks .env, secrets, and binary files.
    Requires agent_write_enabled=True in config.
    """
    if not settings.agent_write_enabled:
        return "Error: Write operations are disabled. Set AGENT_WRITE_ENABLED=true in .env."

    target = (PROJECT_ROOT / path).resolve()
    if not _is_safe_path(target):
        return f"Blocked: {path} is outside the project or is a sensitive file."

    # Block binary extensions
    BLOCKED_EXT = {".pyc", ".pyo", ".db", ".sqlite", ".jpg", ".png", ".gif", ".zip"}
    if target.suffix.lower() in BLOCKED_EXT:
        return f"Blocked: Cannot write binary file {target.suffix}"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"✅ Written {len(content)} chars to {path}"
```

```python
async def apply_patch(path: str, search: str, replace: str) -> str:
    """Apply a targeted text replacement in a source file.

    Finds the FIRST occurrence of `search` in the file and replaces it with `replace`.
    This is safer than full file rewrites for small edits.
    """
    if not settings.agent_write_enabled:
        return "Error: Write operations are disabled."

    target = (PROJECT_ROOT / path).resolve()
    if not _is_safe_path(target):
        return f"Blocked: {path} is outside the project or is a sensitive file."
    if not target.exists():
        return f"Error: File {path} does not exist."

    text = target.read_text(encoding="utf-8")
    if search not in text:
        return f"Error: Search string not found in {path}. Use read_source_file to check."

    new_text = text.replace(search, replace, 1)
    target.write_text(new_text, encoding="utf-8")
    return f"✅ Patched {path}: replaced {len(search)} chars with {len(replace)} chars."
```

### Config (`app/config.py`)

```python
# Agent Mode
agent_write_enabled: bool = False  # Habilita escritura de archivos desde el agente
agent_max_iterations: int = 15     # Límite de iteraciones por sesión agéntica
agent_session_timeout: int = 300   # Timeout en segundos (5 minutos)
```

### Decisiones de diseño

- **Write tools deshabilitados por defecto.** El usuario debe optar explícitamente
  con `AGENT_WRITE_ENABLED=true` en `.env`. Esto evita que en producción un prompt
  injection pueda destruir archivos.
- **`apply_patch` en lugar de `write_source_file` para ediciones.** El patrón
  search/replace es más seguro y auditable que reescribir archivos completos.
  Solo se usa `write_source_file` para archivos nuevos.
- **Sin ejecución de código arbitrario (no CodeAct).** A diferencia de ManusIA que
  ejecuta scripts completos en un Docker sandbox, nosotros no tenemos sandbox.
  Limitarnos a tools predefinidos es la opción segura para un entorno sin aislamiento.

---

## Fase 1: Agent Loop — Ejecución Asincrónica en Background

### Objetivo
Permitir que el agente trabaje de forma autónoma después de recibir un pedido complejo
del usuario. El usuario NO tiene que esperar a que el agente termine; recibe una
confirmación inmediata y luego un resultado final por WhatsApp.

### Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `app/agent/__init__.py` | [NEW] Package init |
| `app/agent/models.py` | [NEW] `AgentSession` dataclass |
| `app/agent/loop.py` | [NEW] `run_agent_session()` — el loop principal |
| `app/webhook/router.py` | Detectar pedidos complejos e iniciar sesión agéntica |
| `app/profiles/prompt_builder.py` | System prompt variant para Agent Mode |
| `app/config.py` | Config keys para Agent Mode |

### Schema de datos

```python
# app/agent/models.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

class AgentStatus(str, Enum):
    RUNNING = "running"
    WAITING_USER = "waiting_user"  # HITL: esperando aprobación
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class AgentSession:
    session_id: str
    phone_number: str
    objective: str               # El pedido original del usuario
    status: AgentStatus = AgentStatus.RUNNING
    iteration: int = 0
    max_iterations: int = 15
    started_at: datetime = field(default_factory=datetime.utcnow)
    context_messages: list = field(default_factory=list)
    task_plan: str | None = None # task.md content (Fase 2)
```

### El Agent Loop

```python
# app/agent/loop.py
import asyncio
import logging
import uuid

from app.agent.models import AgentSession, AgentStatus
from app.llm.client import OllamaClient
from app.models import ChatMessage
from app.skills.executor import execute_tool_loop
from app.skills.registry import SkillRegistry
from app.whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)

# Active sessions indexed by phone number (one session per user at a time)
_active_sessions: dict[str, AgentSession] = {}


async def run_agent_session(
    session: AgentSession,
    ollama_client: OllamaClient,
    skill_registry: SkillRegistry,
    wa_client: WhatsAppClient,
    mcp_manager=None,
) -> None:
    """Run a full agentic session in the background.

    The agent iterates: Think → Call Tools → Observe → Loop
    until the objective is complete or max_iterations is reached.
    """
    _active_sessions[session.phone_number] = session

    try:
        # Build initial system prompt for agent mode
        agent_system = (
            "You are in AGENT MODE. You have been given an objective by the user "
            "and must complete it autonomously using the available tools.\n\n"
            f"OBJECTIVE: {session.objective}\n\n"
            "RULES:\n"
            "1. Break the objective into small steps.\n"
            "2. Execute one step at a time using tools.\n"
            "3. After completing ALL steps, respond with your final summary.\n"
            "4. If you need user input, call the `notify_user` tool.\n"
            "5. Never loop on the same action — if a tool fails, try a different approach.\n"
        )

        messages = [
            ChatMessage(role="system", content=agent_system),
            ChatMessage(role="user", content=session.objective),
        ]

        # Agent loop
        reply = await execute_tool_loop(
            messages=messages,
            ollama_client=ollama_client,
            skill_registry=skill_registry,
            mcp_manager=mcp_manager,
            max_tools=session.max_iterations,
        )

        session.status = AgentStatus.COMPLETED

        # Proactively send the result to the user
        from app.formatting.markdown_to_wa import markdown_to_whatsapp
        await wa_client.send_message(
            session.phone_number,
            markdown_to_whatsapp(f"✅ **Sesión completada**\n\n{reply}"),
        )

    except asyncio.CancelledError:
        session.status = AgentStatus.CANCELLED
        logger.info("Agent session %s cancelled", session.session_id)
    except Exception:
        session.status = AgentStatus.FAILED
        logger.exception("Agent session %s failed", session.session_id)
        await wa_client.send_message(
            session.phone_number,
            "❌ La sesión agéntica falló. Usa /debug para investigar.",
        )
    finally:
        _active_sessions.pop(session.phone_number, None)


def get_active_session(phone_number: str) -> AgentSession | None:
    return _active_sessions.get(phone_number)


def cancel_session(phone_number: str) -> bool:
    session = _active_sessions.get(phone_number)
    if session:
        session.status = AgentStatus.CANCELLED
        return True
    return False
```

### Integración en `router.py`

El trigger para entrar en Agent Mode se basa en una clasificación del intent.
Actualmente el router usa `classify_intent` para determinar qué tools usar.
Agregamos un nuevo intent: `"agent_task"`.

```python
# En _handle_message, después de classify_intent:
if pre_classified and "agent_task" in pre_classified:
    from app.agent.loop import run_agent_session, get_active_session
    from app.agent.models import AgentSession

    if get_active_session(msg.from_number):
        await wa_client.send_message(msg.from_number,
            "⚠️ Ya hay una sesión activa. Usa /cancel para detenerla.")
        return

    session = AgentSession(
        session_id=uuid.uuid4().hex,
        phone_number=msg.from_number,
        objective=user_text,
        max_iterations=settings.agent_max_iterations,
    )

    # Responder inmediatamente al usuario
    await wa_client.send_message(msg.from_number,
        "🤖 Entendido, inicio sesión de trabajo autónoma. "
        "Te avisaré cuando termine.")

    # Lanzar la sesión en background
    task = asyncio.create_task(
        run_agent_session(session, ollama_client, skill_registry, wa_client, mcp_manager)
    )
    _track_task(task)
    return
```

### Decisiones de diseño

- **Una sesión por usuario.** Esto simplifica el estado y evita conflictos de herramientas.
  Si el usuario ya tiene una sesión activa, se le pide que la cancele primero.
- **Reutilización de `execute_tool_loop`.** No reimplementamos el loop de herramientas.
  Usamos el existente con `max_tools` elevado. Esto garantiza que las mismas herramientas,
  el compactador de contexto, y el stripping de `<think>` se apliquen automáticamente.
- **No hay base de datos para sesiones.** Las sesiones viven en memoria durante su
  ejecución (máximo 5 minutos). Si el servidor se reinicia, se pierden. Esto es
  aceptable para la v1; en v2 se puede persistir en SQLite.

---

## Fase 2: Markdown Task Memory

### Objetivo
Darle al agente una "memoria de trabajo" estructurada para que no pierda el hilo durante
iteraciones largas, siguiendo el patrón de Claude Code / Antigravity.

### Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `app/agent/task_memory.py` | [NEW] Herramientas para crear/leer/actualizar task plan |
| `app/agent/loop.py` | Inyectar task plan en el prompt del agente |

### Implementación

En lugar de crear archivos `.wasap/task.md` en el repo del usuario (que requiere acceso
al filesystem del usuario y es complejo de manejar), almacenamos el task plan como un
campo de texto en el `AgentSession`. El agente lo actualiza entre iteraciones usando
un tool dedicado.

```python
# app/agent/task_memory.py

def register_agent_tools(skill_registry, session_getter):
    """Register agent-specific tools that only work during an active session."""

    async def get_task_plan() -> str:
        """Read the current task plan for this agent session."""
        session = session_getter()
        if not session or not session.task_plan:
            return "No task plan created yet. Use create_task_plan to create one."
        return session.task_plan

    async def create_task_plan(plan: str) -> str:
        """Create or overwrite the task plan for this session.

        Format: A markdown checklist with [ ] for pending and [x] for done items.
        Example:
        - [ ] Read the target file
        - [ ] Apply the fix
        - [ ] Verify the change
        """
        session = session_getter()
        if not session:
            return "Error: No active agent session."
        session.task_plan = plan
        return f"✅ Task plan created with {plan.count('[ ]')} pending items."

    async def update_task_status(task_index: int, done: bool = True) -> str:
        """Mark a specific task as done [x] or pending [ ] by its 1-based index."""
        session = session_getter()
        if not session or not session.task_plan:
            return "Error: No task plan exists."

        lines = session.task_plan.split("\n")
        task_count = 0
        for i, line in enumerate(lines):
            if "[ ]" in line or "[x]" in line:
                task_count += 1
                if task_count == task_index:
                    if done:
                        lines[i] = line.replace("[ ]", "[x]")
                    else:
                        lines[i] = line.replace("[x]", "[ ]")
                    session.task_plan = "\n".join(lines)
                    return f"✅ Task {task_index} marked as {'done' if done else 'pending'}."

        return f"Error: Task {task_index} not found (total: {task_count})."

    # Register all three tools
    skill_registry.register_tool("get_task_plan", get_task_plan, ...)
    skill_registry.register_tool("create_task_plan", create_task_plan, ...)
    skill_registry.register_tool("update_task_status", update_task_status, ...)
```

### Inyección en el prompt

Al comienzo de cada iteración del Agent Loop, si existe un task plan, se inyecta
en el system prompt:

```python
# En agent/loop.py, antes de cada iteración:
if session.task_plan:
    plan_reminder = f"\n\n--- CURRENT TASK PLAN ---\n{session.task_plan}\n--- END TASK PLAN ---\n"
    messages[0] = ChatMessage(
        role="system",
        content=agent_system + plan_reminder,
    )
```

---

## Fase 3: Git & PR Tools

### Objetivo
Dar al agente la capacidad de interactuar con Git (branching, committing, pushing) y
crear Pull Requests en GitHub, completando el ciclo de "software worker".

### Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `app/skills/tools/git_tools.py` | [NEW] Herramientas Git: branch, commit, push |
| `app/config.py` | Agregar `github_token` opcional para PRs |

### Herramientas Git

> **Nota**: Muchas operaciones Git ya están disponibles vía el MCP GitHub server.
> Sin embargo, las operaciones locales (branch, commit, push) requieren CLI git.
> `create_pull_request` se delega al MCP server existente.

```python
# app/skills/tools/git_tools.py

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TIMEOUT = 30  # seconds


async def git_status() -> str:
    """Show the current Git status of the project."""
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=TIMEOUT,
    )
    return result.stdout or "(working tree clean)"


async def git_create_branch(branch_name: str) -> str:
    """Create and switch to a new Git branch."""
    result = subprocess.run(
        ["git", "checkout", "-b", branch_name],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=TIMEOUT,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return f"✅ Created and switched to branch: {branch_name}"


async def git_commit(message: str) -> str:
    """Stage all changes and create a commit."""
    # Stage everything
    subprocess.run(["git", "add", "-A"], cwd=PROJECT_ROOT, timeout=TIMEOUT)
    result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=TIMEOUT,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return f"✅ Committed: {message}"


async def git_push(branch_name: str = "") -> str:
    """Push the current branch to origin."""
    cmd = ["git", "push", "origin"]
    if branch_name:
        cmd.append(branch_name)
    else:
        cmd.append("HEAD")

    result = subprocess.run(
        cmd, cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=TIMEOUT,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return f"✅ Pushed to origin"


async def git_diff() -> str:
    """Show the current unstaged diff."""
    result = subprocess.run(
        ["git", "diff", "--stat"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=TIMEOUT,
    )
    return result.stdout or "(no changes)"
```

### Flujo completo: Del pedido al PR

```
Usuario: "Crea un PR que cambie el color del header a azul"
  ↓
1. Agent clasifica como "agent_task"
2. Agent responde: "Entendido, inicio sesión de trabajo"
3. Agent Loop arranca:
   a. create_task_plan("- [ ] Leer index.css\n- [ ] Cambiar color\n- [ ] Crear branch\n- [ ] Commit\n- [ ] Push\n- [ ] Crear PR")
   b. read_source_file("app/static/index.css")
   c. apply_patch("app/static/index.css", "color: red", "color: blue")
   d. update_task_status(1, done=True)
   e. update_task_status(2, done=True)
   f. git_create_branch("fix/header-color-blue")
   g. git_commit("fix: change header color to blue")
   h. git_push("fix/header-color-blue")
   i. create_pull_request(title="fix: header color blue", ...)  # via MCP
   j. update_task_status(3..6, done=True)
4. Agent envía resultado: "✅ PR creado: https://github.com/..."
```

---

## Fase 4: Human-in-the-Loop (HITL)

### Objetivo
Permitir que el agente **pause** su ejecución para solicitar aprobación humana en
decisiones críticas (antes de hacer un commit, antes de crear un PR, etc.).

### Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `app/agent/hitl.py` | [NEW] Mecanismo de pausa/reanudación |
| `app/agent/loop.py` | Integrar HITL checkpoints |
| `app/webhook/router.py` | Detectar respuestas a HITL y reanudar sesión |

### Implementación

```python
# app/agent/hitl.py
import asyncio

# Per-user events for HITL synchronization
_hitl_responses: dict[str, asyncio.Event] = {}
_hitl_messages: dict[str, str] = {}


async def request_user_approval(
    phone_number: str,
    question: str,
    wa_client,
    timeout: int = 120,
) -> str:
    """Pause the agent and ask the user a question. Returns the user's response."""
    event = asyncio.Event()
    _hitl_responses[phone_number] = event
    _hitl_messages[phone_number] = ""

    # Send the question to WhatsApp
    await wa_client.send_message(phone_number, f"⏸️ **Necesito tu aprobación:**\n\n{question}")

    # Block until the user responds or timeout
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        return _hitl_messages.pop(phone_number, "")
    except asyncio.TimeoutError:
        return "TIMEOUT: User did not respond within the allowed time."
    finally:
        _hitl_responses.pop(phone_number, None)


def resolve_hitl(phone_number: str, user_message: str) -> bool:
    """Called from router.py when a message arrives for a user with a pending HITL.
    Returns True if the message was consumed by HITL."""
    event = _hitl_responses.get(phone_number)
    if event and not event.is_set():
        _hitl_messages[phone_number] = user_message
        event.set()
        return True
    return False
```

### Integración en el router

```python
# En router.py — al inicio de _handle_message:
from app.agent.hitl import resolve_hitl

# Si el usuario tiene una sesión HITL activa, su mensaje reanuda la sesión
if resolve_hitl(msg.from_number, user_text):
    logger.info("HITL response from %s: %s", msg.from_number, user_text[:50])
    return  # No procesar como mensaje normal
```

### Comando `/cancel`

```python
# app/commands/builtins.py
async def cmd_cancel(args: str, context: CommandContext) -> str:
    """Cancel the active agent session."""
    from app.agent.loop import cancel_session, get_active_session
    session = get_active_session(context.phone_number)
    if not session:
        return "No hay ninguna sesión activa para cancelar."
    cancel_session(context.phone_number)
    return "🛑 Sesión agéntica cancelada."
```

---

## Orden de implementación

1. **Fase 0** — Write tools + config toggles (sin dependencias, requisito de todo lo demás)
2. **Fase 3** — Git tools (independiente, puede ir en paralelo con Fase 1)
3. **Fase 1** — Agent Loop (depende de Fase 0)
4. **Fase 2** — Task Memory (depende de Fase 1)
5. **Fase 4** — HITL (depende de Fases 1+2)

> Fases 0 y 3 se pueden implementar y testear de forma aislada como tools normales,
> sin necesitar el Agent Loop. Esto permite iterar incrementalmente.

## Decisiones de diseño

### ¿Por qué NO CodeAct (ejecución de scripts arbitrarios)?
ManusIA ejecuta scripts Python dentro de un Docker sandbox. Esto es extremadamente
poderoso pero requiere aislamiento de containers por tarea. WasAP corre como un
solo contenedor Docker sin sandboxing. Ejecutar código arbitrario en ese entorno
sería un riesgo de seguridad inaceptable. Las herramientas predefinidas con controles
de seguridad son la opción correcta de seguridad para este contexto.

### ¿Por qué reutilizar `execute_tool_loop` en lugar de un loop custom?
El `execute_tool_loop` ya maneja: retry de LLM, tool dispatching, context compaction,
`<think>` tag stripping, tracing, y más. Reimplementar un loop paralelo introduciría
bugs sutiles y duplicación. Al reutilizarlo con `max_tools` elevado, heredamos toda
la infraestructura existente automáticamente.

### ¿Por qué sesiones en memoria y no en SQLite?
Las sesiones son efímeras (máximo 5 min). Persistirlas en SQLite agrega complejidad
sin beneficio claro: si el servidor se reinicia durante una sesión, el contexto del
LLM se pierde de todas formas. En v2, si se necesita durabilidad, se puede agregar
un `agent_sessions` table con el task plan como campo TEXT.

### ¿Por qué un toggle `AGENT_WRITE_ENABLED`?
En producción, un prompt injection podría instruir al agente a borrar o modificar
archivos del proyecto. El toggle actúa como un interruptor de emergencia: si algo
sale mal, se desactiva sin tocar código. Está OFF por defecto.
