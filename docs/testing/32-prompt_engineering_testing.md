# Testing Manual: Prompt Engineering & Versioning

> **Feature documentada**: [`docs/features/32-prompt_engineering.md`](../features/32-prompt_engineering.md)
> **Requisitos previos**: Container corriendo (`docker compose up -d`), modelos de Ollama disponibles.

---

## Verificar que la feature está activa

Al arrancar el container, buscar en los logs:

```bash
docker compose logs -f localforge | head -60
```

Confirmar las siguientes líneas:
- `Seeded N default prompt(s) into DB` — indica que los prompts se insertaron en DB (solo aparece en el primer arranque o si se agrega un prompt nuevo al catálogo)
- Si no aparece, todos los prompts ya tenían versión activa → comportamiento correcto

---

## Casos de prueba principales

| Mensaje / Acción | Resultado esperado |
|---|---|
| `/prompts` | Lista todos los prompts registrados con versión activa, creador y fecha |
| `/prompts classifier` | Muestra el contenido activo del classifier (truncado si >600 chars) + historial de versiones |
| `/prompts classifier 1` | Muestra el contenido de la versión 1 específica con marker ✅ si está activa |
| `/approve-prompt classifier 2` | Corre eval, muestra score ✅/⚠️, activa la versión 2 |
| `/approve-prompt classifier 99` | "No encontré la versión 99..." |
| `/prompts nonexistent` | "No encontré el prompt 'nonexistent'..." |

---

## Flujo completo: proponer y activar una mejora de prompt

```bash
# 1. Verificar el prompt activo actual
/prompts classifier

# 2. Pedir al agente que proponga una mejora (via eval skill)
# (requiere sesión agéntica o tool loop con eval skill activo)
"propone una mejora al prompt classifier que mejore la detección de preguntas de math"

# 3. Si el agente usó propose_prompt_change(), verificar la nueva versión
/prompts classifier
# → Debe aparecer v2 en el historial (no activa aún)

# 4. Evaluar y activar
/approve-prompt classifier 2
# → Muestra eval score (si hay dataset entries) y activa

# 5. Verificar activación
/prompts classifier
# → v2 debe aparecer con ✅

# 6. Rollback si hay regresión
/approve-prompt classifier 1
```

---

## Edge cases y validaciones

| Escenario | Resultado esperado |
|---|---|
| `/prompts` con DB vacía | "No hay prompts registrados..." |
| `/approve-prompt classifier abc` | "La versión debe ser un número." |
| `/approve-prompt` sin args | Mensaje de uso con ejemplo |
| `/approve-prompt classifier 1` cuando v1 ya está activa | "Esa versión ya está activa." |
| `/approve-prompt` cuando Ollama no está disponible | Activa sin eval, sin error visible al usuario |
| `/approve-prompt` cuando no hay dataset entries | Activa con nota "sin dataset entries para evaluar" |
| Reiniciar el container después de activar v2 | v2 sigue activa (persiste en DB), no se sobreescribe al seedear |

---

## Verificar en logs

```bash
# Seeding al startup
docker compose logs localforge | grep -i "seeded"

# Cache invalidation al aprobar prompt
docker compose logs localforge | grep -i "prompt cache invalidated"

# Eval score al aprobar
docker compose logs localforge | grep -i "activate_with_eval"

# Fallback al default cuando DB no tiene versión
docker compose logs localforge | grep -i "prompt_manager"
```

---

## Queries de verificación en DB

```bash
# Ver todos los prompts registrados
sqlite3 data/localforge.db "SELECT prompt_name, version, is_active, created_by FROM prompt_versions ORDER BY prompt_name, version;"

# Ver historial de un prompt específico
sqlite3 data/localforge.db "SELECT version, is_active, created_by, approved_at FROM prompt_versions WHERE prompt_name='classifier' ORDER BY version;"

# Verificar que hay exactamente 1 activo por prompt
sqlite3 data/localforge.db "SELECT prompt_name, COUNT(*) as activos FROM prompt_versions WHERE is_active=1 GROUP BY prompt_name HAVING activos != 1;"
# → debe retornar vacío (0 rows)

# Ver el contenido del prompt activo
sqlite3 data/localforge.db "SELECT content FROM prompt_versions WHERE prompt_name='classifier' AND is_active=1;"
```

---

## Verificar degradación graceful

**Escenario: DB inaccesible al resolver un prompt**

El sistema usa fail-open: si `get_active_prompt()` no puede leer de DB, cae al default del registry y luego al param `default` explícito. El mensaje se procesa igual.

```bash
# Simular: renombrar temporalmente el archivo de DB
mv data/localforge.db data/localforge.db.bak
# Enviar mensaje de WhatsApp → debe responder (usando defaults hardcodeados)
# Restaurar
mv data/localforge.db.bak data/localforge.db
```

**Escenario: Ollama no disponible al correr /approve-prompt**

```bash
docker compose stop ollama
# En WhatsApp: /approve-prompt classifier 2
# → Debe activar el prompt igual, con mensaje "_Eval: no se pudo correr (activando de todas formas)_"
docker compose start ollama
```

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| `/prompts` retorna "No hay prompts..." en producción | `prompt_versioning_enabled=False` en `.env` | Setear `PROMPT_VERSIONING_ENABLED=true` y reiniciar |
| El contenido del prompt no cambia después de `/approve-prompt` | Cache en memoria no invalidado | El cache se invalida automáticamente — verificar logs. Si persiste, reiniciar el container |
| `activate_with_eval` siempre retorna score 0 | Dataset sin `expected_output` | Usar `/correct` o `add_to_dataset` con expected output antes de evaluar |
| `propose_prompt_change` no aparece como tool | `tracing_enabled=False` | El eval skill requiere `TRACING_ENABLED=true` |
| Prompt seeded en startup sobreescribe versión personalizada | Nunca ocurre — `seed_default_prompts` es conservador | Si igual ocurre, es un bug: reportar con el contenido de `prompt_versions` |

---

## Variables relevantes para testing

| Variable (`.env`) | Valor de test | Efecto |
|---|---|---|
| `PROMPT_VERSIONING_ENABLED` | `true` | Activa seeding en startup y el uso de versiones de DB |
| `TRACING_ENABLED` | `true` | Habilita eval skill (necesario para `propose_prompt_change` y `run_quick_eval`) |
| `EVAL_AUTO_CURATE` | `true` | Curación automática al dataset — alimenta el eval suite con más entries |
