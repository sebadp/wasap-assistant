# Feature: Skills y Herramientas

> **Versión**: v1.0
> **Fecha de implementación**: 2026-01
> **Fase**: Fase 4
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

El agente puede usar herramientas externas (tools) para realizar acciones concretas: consultar la hora, hacer cálculos, ver el clima, tomar notas, auto-inspeccionarse (selfcode), instalar MCP servers, y gestionar proyectos. Las tools se organizan en skills con configuración en archivos SKILL.md.

---

## Arquitectura

```
[Mensaje del usuario]
        │
        ▼
[classify_intent] ──► categorías: ["datetime", "notes", ...]
        │
        ▼
[select_tools] ──► filtra tools relevantes por categoría
        │
        ▼
[execute_tool_loop — max 5 iteraciones]
    │
    ├─ LLM genera tool_calls
    ├─ _run_tool_call() ejecuta cada tool en paralelo
    ├─ Resultados vuelven como ChatMessage(role="tool")
    └─ LLM decide: más tools o responder al usuario
        │
        ▼
[Respuesta final al usuario]
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/skills/registry.py` | `SkillRegistry` — registro de tools y skills |
| `app/skills/executor.py` | `execute_tool_loop` — loop de tool calling |
| `app/skills/router.py` | `classify_intent`, `select_tools`, `TOOL_CATEGORIES` |
| `app/skills/loader.py` | Parser de SKILL.md (regex, sin PyYAML) |
| `app/skills/models.py` | `ToolDefinition`, `ToolCall`, `ToolResult`, `SkillMetadata` |
| `app/skills/tools/datetime_tools.py` | Hora actual, fecha |
| `app/skills/tools/calculator_tools.py` | Calculadora con AST safe eval |
| `app/skills/tools/weather_tools.py` | Clima via API externa |
| `app/skills/tools/notes_tools.py` | CRUD de notas persistentes |
| `app/skills/tools/selfcode_tools.py` | Auto-inspección: código, config, health |
| `app/skills/tools/expand_tools.py` | Hot-install MCP servers, skill from URL |
| `app/skills/tools/project_tools.py` | Gestión de proyectos, tareas, actividad |
| `app/mcp/manager.py` | `McpManager` — conexión a MCP servers (stdio/HTTP) |
| `skills/*/SKILL.md` | Definiciones de skills con frontmatter + instrucciones |

---

## Walkthrough técnico

1. **Intent classification**: LLM clasifica el mensaje en categorías (`TOOL_CATEGORIES`) para filtrar tools relevantes
2. **Tool selection**: `select_tools()` filtra por categoría, retorna ≤`max_tools` tools
3. **Tool loop**: `execute_tool_loop()` envía context + tools al LLM → recibe `tool_calls` → ejecuta en paralelo → resultados vuelven como `role="tool"` → repite hasta texto o max 5 iteraciones
4. **Safe execution**: cada tool tiene handler async con validación de parámetros
5. **Dedup atómico**: `processed_messages` tabla con `INSERT OR IGNORE` para evitar procesar el mismo mensaje dos veces
6. **Reply context**: si el usuario responde a un mensaje, el texto citado se inyecta en el prompt
7. **Graceful shutdown**: `_track_task()` registra todas las tareas background, `wait_for_in_flight()` espera a que completen en shutdown

---

## Cómo extenderla

### Agregar un tool nuevo a un skill existente

```python
# En app/skills/tools/<skill>_tools.py
async def my_new_tool(param1: str) -> str:
    """Description for the LLM."""
    return f"Result: {param1}"

skill_registry.register_tool(
    name="my_new_tool",
    description="What this tool does",
    parameters={...},
    handler=my_new_tool,
    skill_name="my_skill",
)
```

### Crear un skill nuevo

1. Crear `skills/<nombre>/SKILL.md` con frontmatter YAML
2. Crear `app/skills/tools/<nombre>_tools.py` con `register()` function
3. Llamar `register()` desde `register_builtin_tools()` en `app/skills/tools/__init__.py`
4. Agregar categoría a `TOOL_CATEGORIES` en `router.py`

### Instalar un MCP server

El usuario puede pedir: "Instalá el server de GitHub" → el agente usa `expand_tools` para buscar en Smithery y hot-install el server.

---

## Guía de testing

→ Ver [`docs/testing/skills_herramientas_testing.md`](../testing/skills_herramientas_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| SKILL.md con frontmatter regex | YAML completo (PyYAML) | Sin dependencia extra, más simple |
| AST safe eval para calculator | `eval()` directo | Seguridad — eval() permite ejecución arbitraria |
| Clasificación LLM para routing | Keyword matching | Maneja sinónimos, ambigüedad, idiomas |
| Tools en paralelo por iteración | Secuencial | ~50% reducción en latencia con 2+ tool calls |
| MCP hot-install sin restart | Solo vía config file | UX superior — "instalá X" y funciona |
| `_cached_tools_map` module-level | Reconstruir en cada request | Performance — el map se construye 1 vez |

---

## Gotchas y edge cases

- **El calculator** usa whitelist AST estricta — operaciones como `import` o `__` son rechazadas
- **`selfcode` tools** bloquean acceso a archivos sensibles (tokens de WhatsApp) via `_is_safe_path()`
- **MCP servers** pueden fallar al conectar — la app continúa sin ellos (fail-open)
- **`expand_tools.hot_add_server()`** persiste config + llama `reset_tools_cache()` + `register_dynamic_category()`
- **El intent classifier** a veces retorna `"none"` para mensajes ambiguos — ahora tiene fallback con sticky categories (Fase Context Engineering)

---

## Variables de configuración relevantes

| Variable (`config.py`) | Default | Efecto |
|---|---|---|
| `SKILLS_DIR` | `skills` | Directorio de definiciones de skills |
| `MAX_TOOLS_PER_CALL` | `8` | Tools máximos por payload al LLM |
| `MCP_CONFIG_PATH` | `data/mcp_servers.json` | Config de MCP servers |
| `AGENT_WRITE_ENABLED` | `False` | Habilita tools que modifican archivos |
