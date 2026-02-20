# Testing Manual: Dataset Vivo de Evaluación

> **Feature documentada**: [`docs/features/eval_dataset.md`](../features/eval_dataset.md)
> **Requisitos previos**: Container corriendo, `tracing_enabled=true`, `eval_auto_curate=true` en `.env`.

---

## Verificar que la feature está activa

```bash
docker compose logs -f wasap 2>&1 | grep -i "curate\|dataset\|golden\|failure"
```

---

## Casos de prueba

### Curación automática — Golden confirmado

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | Enviar un mensaje y esperar respuesta | Traza creada con `status='completed'` |
| 2 | Ejecutar `/rate 5` | Score `1.0` en `trace_scores`, `source='human'` |
| 3 | Esperar ~1s | Entry creada en `eval_dataset` con `entry_type='golden'`, `metadata.confirmed=True` |

### Curación automática — Golden candidato

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | Enviar un mensaje y esperar respuesta | Traza con guardrails todos en ≥ 0.8 |
| 2 | No dar feedback explícito | Entry `entry_type='golden'`, `metadata.confirmed=False` |

### Curación automática — Failure

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | Reaccionar 👎 a un mensaje del bot | Score `0.0` en `trace_scores`, `source='user'` |
| 2 | Esperar ~1s | Entry `entry_type='failure'` para esa traza |

### Correction pair

| Paso | Acción | Resultado esperado |
|---|---|---|
| 1 | Recibir respuesta del bot | Traza completada |
| 2 | Enviar "eso no es lo que te pregunté" | Score `0.0` en traza anterior + entry `entry_type='correction'` con `expected_output=<tu mensaje>` |

---

## Queries de verificación en DB

```bash
# Ver composición del dataset
sqlite3 data/wasap.db "
SELECT entry_type, COUNT(*) as n,
       SUM(CASE WHEN json_extract(metadata,'$.confirmed')=1 THEN 1 ELSE 0 END) as confirmed
FROM eval_dataset
GROUP BY entry_type;"

# Ver últimas entradas con sus tags
sqlite3 data/wasap.db "
SELECT d.entry_type, d.input_text, GROUP_CONCAT(t.tag) as tags, d.created_at
FROM eval_dataset d
LEFT JOIN eval_dataset_tags t ON t.dataset_id = d.id
GROUP BY d.id
ORDER BY d.created_at DESC LIMIT 10;"

# Ver golden confirmados (tienen señal positiva del usuario)
sqlite3 data/wasap.db "
SELECT d.input_text, d.output_text, d.metadata
FROM eval_dataset d
WHERE d.entry_type = 'golden'
  AND json_extract(d.metadata,'$.confirmed') = 1
ORDER BY d.created_at DESC LIMIT 5;"

# Ver correction pairs
sqlite3 data/wasap.db "
SELECT d.input_text, d.output_text as bad_output, d.expected_output as correction
FROM eval_dataset d
WHERE d.entry_type = 'correction'
ORDER BY d.created_at DESC LIMIT 5;"

# Stats generales
sqlite3 data/wasap.db "
SELECT
  COUNT(*) as total,
  SUM(entry_type='golden') as golden,
  SUM(entry_type='failure') as failure,
  SUM(entry_type='correction') as correction
FROM eval_dataset;"
```

---

## Exportar a JSONL

```bash
# Desde Python interactivo
python - <<'EOF'
import asyncio
from pathlib import Path
from app.database.db import init_db
from app.database.repository import Repository
from app.eval.exporter import export_to_jsonl

async def main():
    conn, _ = await init_db("data/wasap.db")
    repo = Repository(conn)
    count = await export_to_jsonl(repo, Path("data/eval/dataset.jsonl"))
    print(f"Exported {count} entries")
    await conn.close()

asyncio.run(main())
EOF

# Verificar el JSONL
head -5 data/eval/dataset.jsonl | python -m json.tool
```

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| No se crean entries en `eval_dataset` | `tracing_enabled=false` o `eval_auto_curate=false` | Verificar `.env` |
| Entry `golden` con `confirmed=False` inesperado | Sistema aprobó pero no hubo señal de usuario | Normal — candidato a confirmar con `/rate 5` |
| `FOREIGN KEY constraint failed` | `trace_id` no existe en `traces` | Bug — `maybe_curate_to_dataset` debe llamarse solo para trazas reales |
| Correction pair no creado | Corrección fue low-confidence (score=0.3) | Solo high-confidence (score=0.0) genera correction pairs |
| Dataset crece demasiado rápido | `tracing_sample_rate=1.0` + mucho tráfico | Reducir `TRACING_SAMPLE_RATE` o agregar TTL al dataset (futuro) |

---

## Variables relevantes para testing

| Variable (`.env`) | Valor de test | Efecto |
|---|---|---|
| `TRACING_ENABLED` | `true` | Necesario para trazas y dataset |
| `TRACING_SAMPLE_RATE` | `1.0` | Trazar todos los mensajes |
| `EVAL_AUTO_CURATE` | `true` | Activar curación automática |
