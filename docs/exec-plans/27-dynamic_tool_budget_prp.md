# PRP: Dynamic Tool Budget & `request_more_tools`

## Objetivo

Fix de distribución de budget en `select_tools()` + meta-tool para expansión dinámica
de tools dentro del loop. Ver PRD para contexto y decisiones arquitectónicas.

## Archivos a Modificar

| Archivo | Cambio |
|---|---|
| `app/skills/router.py` | Fix `select_tools()` + agregar `REQUEST_MORE_TOOLS_NAME` + `build_request_more_tools_schema()` |
| `app/skills/executor.py` | `execute_tool_loop()`: inyectar meta-tool + manejar llamadas a `request_more_tools` inline |
| `app/webhook/router.py` | `_build_capabilities_section()`: 1 línea mencionando `request_more_tools` |
| `tests/test_tool_router.py` | Tests para nueva lógica de `select_tools` + schema del meta-tool |
| `tests/test_tool_executor.py` | Test de expansión dinámica en el loop |
| `docs/exec-plans/README.md` | Agregar entrada 27 |

## Phase 1: Fix de budget distribution en `select_tools()`

- [x] Modificar `select_tools()` en `app/skills/router.py`:
  - Calcular `per_cat = max(2, max_tools // len(categories))`
  - Iterar categorías, agregar hasta `per_cat` tools por categoría
  - Aplicar `[:max_tools]` como safety cap al final
- [x] Verificar retrocompatibilidad: 1 categoría → `per_cat = max_tools` → sin cambio
- [x] Agregar tests en `tests/test_tool_router.py`:
  - `test_select_tools_distributes_budget_with_two_categories` — ambas categorías representadas
  - `test_select_tools_single_category_unchanged` — comportamiento anterior preservado
  - `test_select_tools_empty_categories_returns_empty` — ya cubierto por `test_select_empty_categories`

## Phase 2: Meta-tool `request_more_tools` — schema y constante

- [x] Agregar en `app/skills/router.py` (después de `select_tools()`):
  - Constante `REQUEST_MORE_TOOLS_NAME = "request_more_tools"`
  - Función `build_request_more_tools_schema(available_categories: list[str]) -> dict`
    - Descripción incluye lista de categorías disponibles para que el LLM sepa cuáles pedir
    - Parámetros: `categories` (array, required) + `reason` (string, optional)
- [x] Actualizar import en `app/skills/executor.py`:
  - Importar `REQUEST_MORE_TOOLS_NAME`, `build_request_more_tools_schema`, `TOOL_CATEGORIES`
- [x] Agregar tests en `tests/test_tool_router.py`:
  - `test_build_request_more_tools_schema_lists_categories`
  - `test_build_request_more_tools_schema_has_required_categories_param`

## Phase 3: Integración en `execute_tool_loop()`

- [x] En `app/skills/executor.py`, en `execute_tool_loop()`, después de `select_tools()`:
  - Construir `meta_tool_schema = build_request_more_tools_schema(list(TOOL_CATEGORIES.keys()))`
  - Prepend: `tools = [meta_tool_schema] + tools`
- [x] Dentro del for loop (reemplazar el `asyncio.gather` actual):
  - Separar `meta_calls` (name == REQUEST_MORE_TOOLS_NAME) de `regular_calls`
  - Para cada `meta_call`: extraer categories + reason, llamar `select_tools()`, mergear
    en `tools` (dedup por nombre), loggear con `logger.info`, agregar `ChatMessage(role="tool")`
    con confirmación de tools cargadas
  - Para `regular_calls`: ejecutar con `asyncio.gather` como hoy
  - Asegurar que `working_messages.extend()` recibe ambos grupos en orden correcto
- [x] Agregar test en `tests/test_tool_executor.py`:
  - `test_request_more_tools_expands_tool_set_in_loop` — mock de 2 respuestas Ollama:
    primera llama `request_more_tools(['github'])`, segunda usa tool de github y responde

## Phase 4: Capabilities section

- [x] En `app/webhook/router.py`, función `_build_capabilities_section()`:
  - Agregar al final de la sección de tool usage: una línea indicando que el LLM puede
    llamar `request_more_tools(categories=[...])` si necesita tools no disponibles actualmente

## Phase 5: Verificación y Documentación

- [x] Correr `make check` (lint + typecheck + tests) — 0 errores (441 passed, 23 skipped)
- [ ] Smoke test manual: enviar por WhatsApp un mensaje que requiera 2 categorías
  y verificar en logs que ambas tienen tools representadas
- [ ] Smoke test `request_more_tools`: mensaje donde el clasificador devuelva solo 1 categoría
  pero la tarea requiera 2 → verificar en logs la expansión dinámica
- [x] Actualizar `CLAUDE.md` con el patrón: `request_more_tools` siempre presente en tools,
  manejado inline en executor, no pasa por PolicyEngine
- [x] Actualizar `docs/exec-plans/README.md` con entrada 27
