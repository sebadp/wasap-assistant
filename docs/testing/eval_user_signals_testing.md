# Testing Manual: Señales de Usuario para Evaluación

> **Feature documentada**: [`docs/features/eval_user_signals.md`](../features/eval_user_signals.md)
> **Requisitos previos**: Container corriendo, `tracing_enabled=true` en `.env`.

---

## Verificar que la feature está activa

```bash
docker compose logs -f wasap 2>&1 | grep -i "reaction\|feedback\|correction"
```

---

## Casos de prueba

### Reacciones WA

| Acción | Resultado esperado en DB |
|---|---|
| Reaccionar 👍 a un mensaje del bot | `trace_scores`: `name="user_reaction"`, `value=1.0`, `source="user"`, `comment="👍"` |
| Reaccionar 👎 a un mensaje del bot | `value=0.0` |
| Reaccionar ❤️ | `value=1.0` |
| Reaccionar 😂 | `value=0.8` |
| Reaccionar a mensaje propio (no del bot) | Ignorado — el mensaje del usuario no tiene `wa_message_id` en `traces.wa_message_id` |
| Reaccionar con emoji fuera del mapa | `value=0.5` (neutral) |

### /feedback

| Mensaje | Resultado esperado |
|---|---|
| `/feedback estuvo perfecto, muy útil` | Score ~0.9-1.0, `source="human"`, `name="human_feedback"` |
| `/feedback no entendió lo que le pregunté` | Score ~0.0-0.2 |
| `/feedback` (sin args) | Respuesta de uso: "Uso: /feedback <comentario>..." |

### /rate

| Mensaje | Score en DB |
|---|---|
| `/rate 5` | `value=1.0` |
| `/rate 3` | `value=0.6` |
| `/rate 1` | `value=0.2` |
| `/rate 6` | Error: "Uso: /rate <1-5>" |
| `/rate abc` | Error: "Uso: /rate <1-5>" |

### Detección de correcciones

| Mensaje del usuario | Resultado esperado |
|---|---|
| "eso no es lo que te pregunté" | Score `0.0` en traza anterior, `name="user_correction"` |
| "no era eso" | Score `0.0` en traza anterior |
| "eso está mal" | Score `0.0` en traza anterior |
| "no eso está mal" (low-confidence) | Score `0.3` en traza anterior |
| "no gracias, ya lo resolví" | Sin score (no es corrección) |
| "no tengo tiempo" | Sin score (no matchea patrones) |

---

## Queries de verificación en DB

```bash
# Ver scores de usuario de las últimas 24h
sqlite3 data/wasap.db "
SELECT ts.name, ts.value, ts.source, ts.comment, t.started_at
FROM trace_scores ts
JOIN traces t ON t.id = ts.trace_id
WHERE ts.source IN ('user', 'human')
  AND t.started_at > datetime('now', '-1 day')
ORDER BY t.started_at DESC;"

# Ver reacciones registradas
sqlite3 data/wasap.db "
SELECT ts.comment AS emoji, ts.value, t.phone_number
FROM trace_scores ts
JOIN traces t ON t.id = ts.trace_id
WHERE ts.name = 'user_reaction'
ORDER BY ts.created_at DESC LIMIT 10;"

# Ver feedbacks humanos
sqlite3 data/wasap.db "
SELECT ts.value, ts.comment, ts.created_at
FROM trace_scores ts
WHERE ts.name IN ('human_feedback', 'human_rating')
ORDER BY ts.created_at DESC LIMIT 10;"

# Ver correcciones detectadas
sqlite3 data/wasap.db "
SELECT ts.value, ts.comment, ts.created_at
FROM trace_scores ts
WHERE ts.name = 'user_correction'
ORDER BY ts.created_at DESC LIMIT 10;"

# Distribución de scores por fuente
sqlite3 data/wasap.db "
SELECT source, name, AVG(value) as avg_score, COUNT(*) as n
FROM trace_scores
GROUP BY source, name
ORDER BY source, name;"
```

---

## Simular una reacción (sin WhatsApp real)

Para testear `_handle_reaction` sin un número real, usar el endpoint de webhook directamente:

```bash
# Primero obtener un wa_message_id real de la DB
sqlite3 data/wasap.db "SELECT wa_message_id FROM traces WHERE wa_message_id IS NOT NULL LIMIT 1;"

# Enviar payload de reacción
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Hub-Signature-256: sha256=..." \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "type": "reaction",
            "from": "5491112345678",
            "reaction": {
              "message_id": "<wa_message_id_del_step_anterior>",
              "emoji": "👍"
            }
          }]
        }
      }]
    }]
  }'
```

---

## Verificar graceful degradation

**Sin traza previa:**
1. Desactivar tracing: `TRACING_ENABLED=false`
2. Enviar un mensaje
3. Ejecutar `/rate 5`
4. Resultado esperado: "No encontré una interacción reciente para evaluar."

**Ollama no disponible para `/feedback`:**
1. Detener Ollama temporalmente
2. Ejecutar `/feedback excelente respuesta`
3. Resultado esperado: feedback guardado con `value=0.5` (neutral default)

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| Reacción no registra score | `wa_message_id` no está en la traza | Verificar que `tracing_enabled=true` y que el reply llegó a la Graph API real |
| `/rate` retorna "No encontré interacción" | `tracing_sample_rate < 1.0` y este mensaje no fue trazado | Subir `TRACING_SAMPLE_RATE=1.0` |
| Corrección no detectada | Patrón no matchea | Revisar `_CORRECTION_PATTERNS_HIGH/LOW` en `router.py` |
| Corrección registra score en traza equivocada | Bug en `get_latest_trace_id` | Verificar que retorna la traza completada más reciente, no "started" |

---

## Variables relevantes para testing

| Variable (`.env`) | Valor de test | Efecto |
|---|---|---|
| `TRACING_ENABLED` | `true` | Necesario para que se registren scores |
| `TRACING_SAMPLE_RATE` | `1.0` | Trazar todos los mensajes para facilitar el test |
