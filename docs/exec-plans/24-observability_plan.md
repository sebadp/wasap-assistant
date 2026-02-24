# Plan de Implementación: Mejoras de Observabilidad y Langfuse

## Objetivo
Mejorar la visibilidad interna del sistema WasAP permitiendo logs con nivel `DEBUG` detallados, e integrando **Langfuse** para la visualización profunda de las trazas jerárquicas (spans, generaciones LLM, guardrails, policy engine).

## Contexto Actual
Actualmente, WasAP recolecta trazas usando `contextvars` y un `TraceRecorder` que guarda datos serializados en SQLite (`data/wasap.db`). El logging está configurado vía `app/logging_config.py` y obedece a `LOG_LEVEL` en el `.env`, pero no tenemos una UI dedicada para analizar las métricas.

## 1. Mejoras en Logging (Cobertura Profunda Nivel DEBUG)
Actualmente el logging obedece a `LOG_LEVEL` en el `.env`, pero **faltan logs detallados** en las fronteras críticas de decisión del sistema.
- **Acción requerida**: Intervenir los archivos core para volcar estado interno usando `logger.debug()`.
  1. `app/skills/router.py`: Loggear la entrada exacta al clasificador de intenciones y la decisión de categoría (o "none") que toma el LLM.
  2. `app/skills/executor.py` y `app/mcp/manager.py`: Loggear el payload crudo (`raw input`) que se le envía a la herramienta (inkluyendo comandos o requests a MCPs como Puppeteer), y la salida cruda devuelta por el servidor MCP o el SO antes de que el LLM la formatee.
  3. `app/webhook/router.py` y `app/agent/loop.py`: Loggear las transiciones de fase (Phase A completada, entrando a Phase B, etc.).
  4. **Interpretación Multimedia (Audios/Imágenes)**: Loggear el texto exacto que interpreta Whisper (Audio) y la respuesta literal generada por el modelo LLaVA (Visión) al "ver" una imagen, previo a cualquier filtrado o procesamiento de negocio.
- **Resultado esperado**: Al setear `LOG_LEVEL=DEBUG`, el desarrollador debe poder leer la consola y entender exactamente qué string se evalúa y por qué el sistema tomó cada rama.

## 2. Integración de Langfuse y OpenTelemetry (Trazas)

Basados en las mejores prácticas de **OpenTelemetry para GenAI en 2026**, la observabilidad no se trata solo de escupir logs, sino de adherirse a **Convenciones Semánticas (Semantic Conventions for GenAI)** para estandarizar atributos y construir una jerarquía clara.

### Arquitectura de Spans (Jerarquía Estandarizada)
Para visualizar correctamente el ciclo de vida del agente, `TraceRecorder` debe emitir spans jerárquicos:
- **[TRACE ROOT] Session / Message**: La interacción completa iniciada por el usuario (ej: `POST /webhook`).
  - **[SPAN] Intent Classification**: El modelo decide qué hacer (ej: `category: run_agent`).
  - **[SPAN] Agent Loop (Step N)**: Cada iteración del razonamiento del agente.
    - **[SPAN] LLM Generation**: La llamada al LLM (Ollama). **Debe incluir `gen_ai.usage.input_tokens` y `gen_ai.usage.output_tokens`**.
    - **[SPAN] Tool Execution**: La llamada a `execute_tool_loop`.
      - **[SPAN] Tool Call (e.g. `run_command`)**: Opciones crudas y salidas.
  - **[SPAN] Guardrails Evaluation**: Tiempo tomado por `pipeline.py`.
  
### Enfoque Propuesto: Langfuse como Segundo "Recorder"
Mantener la propagación actual nativa pura (`async with trace_ctx.span()`) y hacer que `app/tracing/recorder.py` emita eventos **tanto a SQLite como a Langfuse** a través del Langfuse Python SDK.

- **Ventajas**: No acopla fuertemente el pipeline base al decorador `@observe()` de Langfuse, que históricamente nos dio dolores de cabeza con AsyncIO y llamadas a DB concurrentes. Si Langfuse falla, la DB sigue teniendo el rastro.
- **Cómo hacerlo**: 
  1. Instalar `langfuse` via `pyproject.toml`.
  2. Modificar `TraceRecorder.record_span_end()` y `record_generation()` para traducir el `SpanData` y sus atributos a la API de Langfuse en background.
  3. Asegurarse de adjuntar atributos OTel-friendly (ej. `gen_ai.request.model`, `gen_ai.system`).
  4. Vincular los "Scores" (de los Guardrails o del Feedback humano `/rate`) al `trace_id` de Langfuse.

## 3. Infraestructura Langfuse Local

Para probar sin sacar los datos de la máquina local, agregaremos los servicios necesarios al stack de Docker Compose de desarrollo (`docker-compose.yml` o crear un `docker-compose.langfuse.yml` separado para no forzarlo si no se necesita).

**Servicios de Langfuse necesarios:**
- `langfuse-server` (Node HTTP API)
- `langfuse-web` (Next.js Frontend)
- `postgres` (Base de datos relacional requerida por Langfuse)

## Resumen de Cambios Necesarios

| Archivo | Cambio |
|---|---|
| `pyproject.toml` | Añadir dependencia `langfuse` de Python. |
| `docker-compose.yml` | Integrar el stack de Langfuse (Server + DB). |
| `app/config.py` | Añadir variables `langfuse_public_key`, `langfuse_secret_key`, `langfuse_host`. |
| `app/tracing/recorder.py` | Instanciar `Langfuse()` SDK. Duplicar la persistencia de los objetos `SpanData` y `TraceContext` hacia la API de Langfuse async. |
| `app/commands/builtins.py` | El comando `/rate` y `/feedback` ahora deberán reportar el `.score()` también a Langfuse usando el `trace_id`. |

## Orden de Ejecución Sugerido
1. Actualizar configuración local e infraestructura (Docker + Env + Config). Levantar UI de Langfuse en `localhost:3000`.
2. Integrar el SDK en `TraceRecorder` e instanciarlo condicionalmente (solo si se proveen las Keys).
3. Hacer una petición al agente y comprobar en la UI de Langfuse que el árbol de trazas se forma correctamente sin quiebres (mismo root).
