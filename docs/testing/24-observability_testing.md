# Testing Manual: Observability & Langfuse Tracing

> **Feature documentada**: [`docs/features/24-observability.md`](../features/24-observability.md)
> **Requisitos previos**: Container local de Langfuse corriendo (`docker compose up -d langfuse-server langfuse-db`), modelos de Ollama activos.

---

## Verificar que la feature está activa

Al arrancar Langfuse local:

```bash
docker compose logs -f langfuse-server
```

Confirmar la disponibilidad visitando `http://localhost:3000`. Cargar las llaves generadas en Langfuse adentro del archivo `.env`:

```env
LANGFUSE_PUBLIC_KEY="pk-lf-..."
LANGFUSE_SECRET_KEY="sk-lf-..."
LANGFUSE_HOST="http://localhost:3000"
```

El WasAP imprimirá `Langfuse tracing enabled` durante la inicialización.

---

## Casos de prueba principales

| Mensaje / Acción | Resultado esperado |
|---|---|
| Enviar un mensaje "Hola ¿quién sos?" a WasAP | En `http://localhost:3000` aparecerá un trace llamado `interaction` en la solapa de Traces, con múltiples layers adentro de la cascada. |
| Responder con `/rate 4` | En la solapa "Scores" de Langfuse aparecerá un score de nombre `human_rating` con valor `0.8` atado al TraceID de "Hola ¿quién sos?". |

---

## Edge cases y validaciones

| Escenario | Resultado esperado |
|---|---|
| Hablarle a WasAP mientras el servidor de Langfuse local está caído. | El bot igual responde sin tirarle error al usuario. En el terminal de Docker de `wasap` dirá "[WARNING] Failed to upload trace". |

---

## Verificar en logs Deep Debug (`LOG_LEVEL=DEBUG`)

Para verificar que no existen cajas negras en las entradas a los componentes:

```bash
# Cambiar en .env LOG_LEVEL=DEBUG
# Ver logs exactos del prompt del Intent Classifier
docker compose logs -f wasap 2>&1 | grep -i "Intent Classifier"

# Ver payloads brutos que entran a las tools de ejecución (mcp)
docker compose logs -f wasap 2>&1 | grep -i "Tool Execution RAW"

# Ver la salida cruda literal parseada de audio
docker compose logs -f wasap 2>&1 | grep -i "Audio (Whisper) RAW INTERPRETATION"
```

---

## Queries de verificación en DB (Fallback)

```bash
# Asegurarse que a pesar de enviar a Langfuse, sigue emitiendo datos a local
sqlite3 data/wasap.db "SELECT * FROM traces ORDER BY start_time DESC LIMIT 1;"
sqlite3 data/wasap.db "SELECT COUNT(*) FROM trace_spans;"
```

---

## Verificar graceful degradation

1. Detener Langfuse mediante `docker compose stop langfuse-server langfuse-db`.
2. Enviar `/help` al bot.
3. Verificar que el bot responde `*Available commands:...*`.
4. El log indicará una falla de red (timeout / connection refused), pero la DB y el LLM seguirán funcionando al 100%.

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| Las trazas no aparecen en el portal de Langfuse | Claves en `.env` no actualizadas. | Crea un proyecto nuevo en la UI de Langfuse, emití claves para API, pegalas en el archivo `.env` del bot y reiniciá `docker compose restart wasap`. |
| Las latencias no aparecen anidadas. | Problema de ContextVars en código asíncrono. | Validar que no haya hilos sueltos ejecutándose ajenos a `TraceContext`. |

---

## Variables relevantes para testing

| Variable (`.env`) | Valor de test | Efecto |
|---|---|---|
| `LOG_LEVEL` | `DEBUG` | Activa la visibilidad detallada de los tool loops, audio y visión. |
| `LANGFUSE_PUBLIC_KEY` | `""` | Si lo configuras en vacío y reinicias el bot, la integración se deshabilita preventivamente (vuelve todo a SQLite). |
