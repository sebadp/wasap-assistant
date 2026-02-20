# Testing Manual: Eval Skill

> **Feature documentada**: [`docs/features/eval_skill.md`](../features/eval_skill.md)
> **Requisitos previos**: Container corriendo, `tracing_enabled=true` en `.env`, algunas interacciones previas trazadas.

---

## Verificar que el skill está cargado

```bash
# Vía WhatsApp
/review-skill eval

# Resultado esperado:
# Skill: eval
# Version: 1
# Description: Self-evaluation and continuous improvement tools
# Tools:
#   ✓ get_eval_summary
#   ✓ list_recent_failures
#   ... etc
```

---

## Casos de prueba

### get_eval_summary

| Mensaje | Resultado esperado |
|---|---|
| "¿cómo te fue esta semana?" | Score summary de los últimos 7 días |
| "mostrá métricas de los últimos 3 días" | Summary con `days=3` |
| "resumen de rendimiento" | Misma función activada por classify_intent |

### list_recent_failures

| Mensaje | Resultado esperado |
|---|---|
| "mostrá los fallos recientes" | Lista de trazas con min_score < 0.5 |
| "qué salió mal últimamente" | Misma función |

### diagnose_trace

```
1. Obtener trace_id de list_recent_failures
2. "explicame qué pasó en trace_<id>"
→ Deep-dive con spans, scores y input/output completo
```

### add_to_dataset

```
Usuario: "ese fallo fue error mío, márcalo como golden"
→ add_to_dataset(trace_id="...", entry_type="golden")
→ "Trace agregada como golden."

Verificar en DB:
sqlite3 data/wasap.db "SELECT * FROM eval_dataset ORDER BY created_at DESC LIMIT 1;"
```

### propose_correction

```
Usuario: "en esa respuesta debiste decir 'El tipo de cambio es $1250'"
→ propose_correction(trace_id="...", correction="El tipo de cambio es $1250")
→ "Correction pair guardado."
```

### run_quick_eval

```
# Necesita al menos 1 entry con expected_output
# (creado por propose_correction o correction pair automático)

Usuario: "corrí una evaluación rápida"
→ run_quick_eval()
→ "Avg word overlap vs expected: 45%"
```

---

## Queries de verificación en DB

```bash
# Verificar que el skill aparece en la tabla de tools registrados
# (el registry vive en memoria, no en DB — verificar via /review-skill)

# Verificar trazas disponibles para diagnóstico
sqlite3 data/wasap.db "
SELECT id, phone_number, status, started_at
FROM traces
ORDER BY started_at DESC LIMIT 5;"

# Verificar scores disponibles para get_eval_summary
sqlite3 data/wasap.db "
SELECT name, source, AVG(value), COUNT(*)
FROM trace_scores
GROUP BY name, source;"

# Verificar fallos (traces con score < 0.5)
sqlite3 data/wasap.db "
SELECT DISTINCT t.id, MIN(ts.value) as min_score
FROM traces t
JOIN trace_scores ts ON ts.trace_id = t.id
WHERE ts.value < 0.5
GROUP BY t.id
ORDER BY t.started_at DESC LIMIT 5;"
```

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| Skill no aparece en `/review-skill` | `tracing_enabled=false` | Activar en `.env` y reiniciar |
| `get_eval_summary` retorna 0 traces | Sin interacciones trazadas aún | Hacer algunas conversaciones primero |
| `list_recent_failures` retorna vacío | Todos los scores son ≥ 0.5 | Normal si el agente funciona bien; probar con `/rate 1` |
| `diagnose_trace` dice "not found" | trace_id incorrecto | Copiar el ID completo de `list_recent_failures` |
| `run_quick_eval` no tiene entries | Dataset sin correction pairs | Usar `propose_correction` primero |

---

## Variables relevantes para testing

| Variable (`.env`) | Valor de test | Efecto |
|---|---|---|
| `TRACING_ENABLED` | `true` | Necesario para que eval_tools se registren |
| `TRACING_SAMPLE_RATE` | `1.0` | Trazar todo para tener datos |
