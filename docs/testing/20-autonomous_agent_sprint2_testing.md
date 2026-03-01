# Testing: Autonomous Agent Sprint 2 — Diff Preview, PR Creation, Session Persistence, Bootstrap Files

## Tests automatizados

```bash
# Ver test_agent.py para tests de loop, HITL y persistence
pytest tests/test_agent.py -v
```

---

## Tests manuales

### F4: Diff Preview

**Setup**: `AGENT_WRITE_ENABLED=true` en `.env`

1. **Preview básico**:
   ```
   /agent Muéstrame un diff de cómo quedaría README.md si cambias "WasAP" por "WasApp"
   ```
   **Esperado**: El agente llama `preview_patch`, muestra diff formateado con `+`/`-`, NO modifica el archivo.

2. **Preview + aprobación + apply**:
   ```
   /agent Agrega un comentario "# TODO: optimize" al inicio de app/config.py, muéstrame el diff primero
   ```
   **Esperado**: Muestra diff → pide aprobación → aplica el cambio.

3. **Preview con search no encontrado**:
   ```
   /agent Muéstrame diff si cambias "texto_que_no_existe" en app/main.py
   ```
   **Esperado**: Mensaje de error claro, no diff vacío.

---

### F5: PR Creation

**Setup**: `GITHUB_TOKEN=<token>` y `GITHUB_REPO=owner/repo` en `.env`

1. **Crear PR básico**:
   ```
   /agent Crea un PR con título "test: add health endpoint" y body "Testing PR creation"
   ```
   **Esperado**: Retorna URL del PR creado (https://github.com/owner/repo/pull/N).

2. **PR sin credenciales**:
   ```
   # Con GITHUB_TOKEN vacío:
   /agent Crea un PR titulado "test"
   ```
   **Esperado**: Mensaje descriptivo sobre credenciales faltantes, no crash.

3. **Verificación en GitHub**:
   - Abrir la URL retornada → verificar que el PR existe con el título correcto.

---

### F6: Session Persistence

1. **Verificar archivos creados**:
   ```bash
   ls -la data/agent_sessions/
   ```
   **Esperado**: Archivos `<phone>_<session_id>.jsonl` creados después de cada sesión.

2. **Verificar contenido**:
   ```bash
   cat data/agent_sessions/*.jsonl | python -m json.tool | head -50
   ```
   **Esperado**: JSON válido con campos `round`, `tool_calls`, `reply_preview`, `task_plan_snapshot`.

3. **Sesión que falla**: Iniciar sesión → cortar conexión → verificar que los rounds ya persistidos están en el JSONL.

---

### F7: Bootstrap Files

1. **Crear archivos de bootstrap**:
   ```bash
   echo "Eres un asistente de programación muy preciso." > data/workspace/SOUL.md
   echo "Usuario: Sebastian, prefiere respuestas concisas." > data/workspace/USER.md
   ```

2. **Verificar que se cargan**:
   ```
   /agent Lista los archivos en el directorio raíz
   ```
   Verificar en logs: `Loaded bootstrap file: data/workspace/SOUL.md`

3. **Sin archivos bootstrap**: Borrar los archivos → iniciar sesión → debe funcionar sin error.

---

## Verificación en logs

```bash
# Persistencia de sesión
grep "agent.session.save" data/wasap.log

# Bootstrap files cargados
grep "bootstrap" data/wasap.log

# PR creation
grep "git_create_pr" data/wasap.log
```

---

## Queries de DB

```sql
-- Verificar que no hay tabla de sesiones en SQLite (persistencia es en JSONL, no SQLite)
-- Los archivos JSONL están en data/agent_sessions/
```
