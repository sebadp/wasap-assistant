# Testing Manual: Auto-Evolución de Prompts

> **Feature documentada**: [`docs/features/15-eval_auto_evolution.md`](../features/15-eval_auto_evolution.md)
> **Requisitos previos**: Container corriendo, `tracing_enabled=true`, `guardrails_enabled=true`.

---

## Nivel 1: Memorias de auto-corrección

### Verificar que se guardan tras guardrail failure

```bash
# Simular un mensaje que causaría language_match failure
# (bot responde en idioma incorrecto — difícil de triggear manualmente)

# Verificar memorias de self_correction en DB
sqlite3 data/wasap.db "
SELECT id, content, category, created_at
FROM memories
WHERE category = 'self_correction'
ORDER BY created_at DESC LIMIT 5;"

# Verificar en MEMORY.md
grep -A2 "auto-corrección" data/memory/MEMORY.md
```

### Verificar que aparecen en el contexto

```bash
# Las memorias de self_correction se inyectan en Phase B
# Verificar en los logs del container:
docker compose logs -f wasap 2>&1 | grep "self_correction\|memories"
```

---

## Nivel 2: Prompt versioning

### Guardar la primera versión del prompt

```bash
# Desde Python (o via eval tool en WhatsApp)
python - <<'EOF'
import asyncio
from app.database.db import init_db
from app.database.repository import Repository

async def main():
    conn, _ = await init_db("data/wasap.db")
    repo = Repository(conn)

    # Leer el prompt actual de config
    from app.config import Settings
    settings = Settings()

    # Guardar como v1
    vid = await repo.save_prompt_version(
        "system_prompt", 1, settings.system_prompt, "human"
    )
    await repo.activate_prompt_version("system_prompt", 1)
    print(f"Guardado y activado como v1 (id={vid})")
    await conn.close()

asyncio.run(main())
EOF
```

### Proponer un cambio via WhatsApp

```
Usuario: "los últimos fallos son de idioma. proponé un fix al system prompt"
→ El agente llama: propose_prompt_change(
    prompt_name="system_prompt",
    diagnosis="Responde en inglés a mensajes en español",
    proposed_change="Agregar: SIEMPRE responde en el idioma del usuario"
  )
→ "Propuesta guardada: system_prompt v2. Usa /approve-prompt system_prompt 2"
```

### Verificar la propuesta en DB

```bash
sqlite3 data/wasap.db "
SELECT version, is_active, created_by, created_at,
       substr(content, 1, 100) as content_preview
FROM prompt_versions
WHERE prompt_name = 'system_prompt'
ORDER BY version DESC;"
```

### Aprobar una versión

```
Usuario: /approve-prompt system_prompt 2
→ "Prompt 'system_prompt' v2 activado."
```

### Verificar que la cache se invalida

```bash
# Los próximos mensajes deben usar v2
# Verificar en logs:
docker compose logs -f wasap 2>&1 | grep "prompt cache\|active_prompt"

# O desde Python:
python - <<'EOF'
import asyncio
from app.database.db import init_db
from app.database.repository import Repository
from app.eval.prompt_manager import get_active_prompt, invalidate_prompt_cache

async def main():
    conn, _ = await init_db("data/wasap.db")
    repo = Repository(conn)
    invalidate_prompt_cache("system_prompt")
    prompt = await get_active_prompt("system_prompt", repo, "default")
    print(f"Active prompt (first 100 chars): {prompt[:100]}")
    await conn.close()

asyncio.run(main())
EOF
```

---

## Queries de verificación

```bash
# Listar todas las versiones de prompts
sqlite3 data/wasap.db "
SELECT prompt_name, version, is_active, created_by, approved_at
FROM prompt_versions
ORDER BY prompt_name, version DESC;"

# Ver memorias de auto-corrección
sqlite3 data/wasap.db "
SELECT content, created_at
FROM memories
WHERE category = 'self_correction'
ORDER BY created_at DESC;"
```

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| No se crean memorias de self_correction | Guardrails no fallan | Activar `guardrails_language_check=true` y enviar en un idioma no soportado |
| `/approve-prompt` dice "versión no encontrada" | Versión no existe aún | Usar `propose_prompt_change()` o `save_prompt_version()` primero |
| Prompt no cambia tras `/approve-prompt` | Cache no invalidada | Reiniciar el container (la cache es module-level) o esperar a que expire (no hay TTL) |
| `propose_prompt_change` retorna error | Sin versión activa en DB | Guardar la v1 del prompt actual manualmente primero |
