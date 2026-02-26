# Testing Manual: Guardrails y Trazabilidad

> **Feature documentada**: [`docs/features/12-eval_guardrails_tracing.md`](../features/12-eval_guardrails_tracing.md)
> **Requisitos previos**: Container corriendo (`docker compose up -d`), modelos de Ollama disponibles.

---

## Verificar que la feature está activa

Al arrancar el container, verificar en los logs:

```bash
docker compose logs -f wasap | head -60
```

No hay línea de log específica de guardrails al startup (no hay setup costoso). Se activan por mensaje. Para verificar, enviar un mensaje y buscar:

```bash
docker compose logs -f wasap 2>&1 | grep -i "guardrail"
```

Si hay fallas de guardrail, se verá:
```
WARNING - Guardrail checks failed: ['language_match'] (total=12.3ms)
```

---

## Tests automatizados

```bash
# Solo guardrails (rápido, sin Ollama)
.venv/bin/python -m pytest tests/guardrails/ -v

# Todos los tests
.venv/bin/python -m pytest tests/ -v
```

Los 32 tests de guardrails son determinísticos — no requieren Ollama ni DB.

---

## Casos de prueba principales

### Guardrails

| Escenario | Mensaje de test | Resultado esperado |
|---|---|---|
| Respuesta en idioma incorrecto | Mensaje largo en español → LLM responde en inglés (>30 chars ambos) | Guardrail `language_match` falla → se re-prompta en español |
| Respuesta vacía | Cualquier mensaje (forzar vacío mockeando LLM) | Guardrail `not_empty` falla → se reintenta una vez |
| Respuesta >8000 chars | Cualquier mensaje | Guardrail `excessive_length` falla → se logea (pass through) |
| Raw tool JSON en respuesta | (forzar con mock) | Guardrail `no_raw_tool_json` falla → pass through + log |

### Trazas

| Acción | Resultado esperado en DB |
|---|---|
| Enviar un mensaje | Nueva fila en `traces` con `status='completed'` |
| Mensaje procesado con tools | Filas en `trace_spans` con `kind='generation'` y `kind='guardrail'` |
| Guardrail falla | Fila en `trace_scores` con `value=0.0`, `source='system'` |
| Reply enviado OK | `traces.wa_message_id` populado con el ID del mensaje WA |

---

## Edge cases y validaciones

| Escenario | Resultado esperado |
|---|---|
| Mensaje muy corto (< 30 chars) en español | `language_match` skippeado (ambos textos muy cortos) |
| Bot repite email que el usuario ya dio | `no_pii` pasa (el email estaba en el input del usuario) |
| Bot genera un email nuevo | `no_pii` falla → `redact_pii()` reemplaza con `[REDACTED_EMAIL]` |
| `tracing_enabled=False` | No se crean filas en `traces` — pipeline normal sin overhead |
| `guardrails_enabled=False` | Respuesta se envía directamente, sin validación |
| DB falla durante recording | Traza no se guarda, pipeline continúa sin interrumpirse |

---

## Verificar en logs

```bash
# Guardrail failures
docker compose logs -f wasap 2>&1 | grep -i "guardrail"

# Trace recording errors (best-effort — no afectan el pipeline)
docker compose logs -f wasap 2>&1 | grep -i "tracerecorder"

# Guardrail remediation (re-prompts)
docker compose logs -f wasap 2>&1 | grep -i "guardrail_failure"
```

---

## Queries de verificación en DB

```bash
# Ver últimas trazas
sqlite3 data/wasap.db "SELECT id, phone_number, status, started_at, completed_at FROM traces ORDER BY started_at DESC LIMIT 10;"

# Spans de una traza específica
sqlite3 data/wasap.db "SELECT name, kind, status, latency_ms FROM trace_spans WHERE trace_id = '<trace_id>' ORDER BY started_at;"

# Scores de guardrails (últimas 24h)
sqlite3 data/wasap.db "SELECT ts.name, ts.value, ts.source, t.started_at FROM trace_scores ts JOIN traces t ON t.id = ts.trace_id WHERE t.started_at > datetime('now', '-1 day') ORDER BY t.started_at DESC;"

# Trazas con guardrail failures
sqlite3 data/wasap.db "SELECT DISTINCT t.id, t.phone_number, ts.name FROM traces t JOIN trace_scores ts ON ts.trace_id = t.id WHERE ts.value < 1.0 AND ts.source = 'system' ORDER BY t.started_at DESC LIMIT 10;"

# Contar trazas por estado
sqlite3 data/wasap.db "SELECT status, COUNT(*) FROM traces GROUP BY status;"

# Verificar wa_message_id vinculado
sqlite3 data/wasap.db "SELECT id, wa_message_id FROM traces WHERE wa_message_id IS NOT NULL ORDER BY started_at DESC LIMIT 5;"
```

---

## Verificar graceful degradation

**Si el guardrail pipeline falla:**
1. Poner un bug intencional en `pipeline.py` (ej: `raise Exception`)
2. Enviar un mensaje
3. Verificar que el usuario recibe una respuesta normal (el error está caught en el `try/except` del pipeline)
4. Revertir el bug

**Si el TraceRecorder falla:**
1. Desconectar/cerrar la DB (simular con: `mv data/wasap.db data/wasap.db.bak`)
2. Enviar un mensaje
3. Verificar que el usuario recibe respuesta (tracing es best-effort)
4. Restaurar la DB

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| `langdetect` no disponible | No instalado en el entorno | `pip install langdetect>=1.0.9` |
| `language_match` falla en mensajes cortos | Umbral de 30 chars no está funcionando | Verificar en `checks.py:check_language_match` que el skip es correcto |
| Tablas `traces` / `trace_spans` no existen | `TRACING_SCHEMA` no aplicado en `init_db` | Verificar `db.py:init_db` llama `executescript(TRACING_SCHEMA)` |
| `wa_message_id` siempre NULL en trazas | Graph API en modo sandbox/mock no retorna ID | Normal en test; solo funciona con tokens reales |
| Guardrail PII tiene falsos positivos | Patrones demasiado agresivos | Ajustar regex en `_RE_PHONE` / `_RE_DNI` en `checks.py` |

---

## Variables relevantes para testing

| Variable (`.env`) | Valor de test | Efecto |
|---|---|---|
| `GUARDRAILS_ENABLED` | `false` | Desactiva todos los guardrails |
| `GUARDRAILS_LANGUAGE_CHECK` | `false` | Solo desactiva check de idioma |
| `GUARDRAILS_PII_CHECK` | `false` | Solo desactiva check de PII |
| `TRACING_ENABLED` | `false` | Desactiva toda la trazabilidad |
| `TRACING_SAMPLE_RATE` | `0.1` | Traza solo el 10% de los mensajes |
