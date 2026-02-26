# Feature: Observability & Langfuse Tracing

> **Versión**: v1.0
> **Fecha de implementación**: 2026-02-24
> **Fase**: Fase 2
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

Agrega observabilidad profunda al ciclo de vida del agente. Todas las interacciones, clasificaciones de intención, ejecuciones de herramientas, análisis de audio e imagen se emiten hacia **Langfuse** utilizando convenciones de **OpenTelemetry (OTel)** (generations, spans, token usage, scores), al mismo tiempo que imprime entradas crudas en consola si el `LOG_LEVEL` es `DEBUG`.

---

## Arquitectura

```
[Usuario via WhatsApp]
        │
        ▼
   [TraceContext] ──(async contextvars)──► [Spans & Generations]
        │                                             │
        ▼                                             ▼
[Agent Pipeline]                             [TraceRecorder]
        │                                      (Best-Effort)
        │                                       ↙         ↘
        ▼                             [SQLite DB]      [Langfuse SDK]
[Respuesta a Usuario]
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/tracing/recorder.py` | Envía los rastros (traces, spans, scores, generations) tanto a Langfuse como a SQLite. |
| `app/tracing/context.py` | ContextManager asincrónico para encapsular las ejecuciones de pipeline. |
| `app/skills/router.py` | Expone al log la entrada y respuesta del clasificador de intenciones (`logger.debug`). |
| `app/skills/executor.py` | Registra el input y output crudo enorme de los payloads de herramientas (ej: MCP). |
| `app/commands/builtins.py` | Los comandos `/rate` y `/feedback` emiten scores a Langfuse. |

---

## Walkthrough técnico: cómo funciona

1. **Inicialización**: Al recibir un mensaje, en `app/webhook/router.py` se abre el `TraceContext(phone_number, input_text, recorder)`. Automáticamente genera el *Trace Root* en Langfuse.
2. **Propagación**: El bloque `async with trace.span(...)` mide latencias y crea *Spans* y *Generations* que cuelgan del TraceID.
3. **Métricas de OTel**: Si durante un span tipo `generation` el LLM devuelve diccionarios con llaves `gen_ai.usage.input_tokens` en metadata, el `TraceRecorder` mapea esos campos a la entidad correcta en la API de Langfuse (`usage={"input": X, "output": Y}`).
4. **Cierre de Ciclo**: Al terminar la ejecución, `TraceRecorder.finish_trace()` actualiza el estado de la API (`completed`, `failed`) y envia la respuesta que vio el usuario.
5. **Human Feedback**: Si un usuario ejecuta `/rate 5` o `/feedback X`, la capa de base de datos lee el último `trace_id` del número e inyecta la calificación en Langfuse llamando a `recorder.add_score(...)`.

---

## Cómo extenderla

- Para agregar una nueva traza de LLM independiente, haz un nuevo bloque asíncrono en cualquier parte del ciclo y pone como *kind* a `"generation"`.
- Para cambiar de plataforma de observabilidad, solamente es necesario editar `app/tracing/recorder.py`. El co-sistema del `TraceContext` aísla al pipeline del vendor-lock.

---

## Guía de testing

→ Ver [`docs/testing/24-observability_testing.md`](../testing/24-observability_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| Langfuse **junto** con SQLite | Usar solo el SDK de Langfuse (reemplazo) | Si nos quedamos sin internet o el Docker local muere, perderíamos los historiales necesarios para Context Engineering. El doble volcado es más seguro. |
| No usar el decorador `@observe` de Langfuse | Usar `@observe` nativamente | Ya teníamos un pipeline maduro con `contextvars` (`TraceContext`). Además `@observe` suele generar Spans desconectados en backgrounds asíncronos (`create_task` en el bot webhook). |

---

## Gotchas y edge cases

- **Fallback Seguro**: Si el servidor de Langfuse falla (`localhost:3000`), el `TraceRecorder` captura la excepción, la registra como un warning simple en consola, y **no interrumpe el mensaje del WhatsApp al usuario**.
- **Spans Desconectados**: Cualquier función que se envíe adentro de `asyncio.create_task` hereda automáticamente el `TraceContext` actual, así que los sub-procesos quedan acoplados bajo el Trace inicial.

---

## Variables de configuración relevantes

| Variable (`.env`) | Default | Efecto |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Al ponerlo en `DEBUG`, el Agent Loop desborda la consola con payloads gigantes de tools y respuestas raw de LLaVA. |
| `LANGFUSE_PUBLIC_KEY` | `""` | Si están vacías, Langfuse simplemente se apaga y el sistema opera solo con SQLite. |
| `LANGFUSE_HOST` | `http://localhost:3000` | URL del endpoint de ingesta de trazas. |
