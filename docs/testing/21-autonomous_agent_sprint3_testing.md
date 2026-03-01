# Testing: Autonomous Agent Sprint 3 — Cron Jobs, File Outline, Multi-Project Workspace

## Tests automatizados

```bash
pytest tests/test_scheduler_tools.py -v
# (workspace y selfcode tools incluidos en test_tool_executor.py)
```

---

## Tests manuales

### F8: Cron Jobs

1. **Crear cron básico**:
   ```
   Programa un recordatorio para mañana a las 9am: "Revisar tasks del día"
   ```
   **Esperado**: Agente confirma creación con schedule y ID.

2. **Listar crons**:
   ```
   ¿Qué recordatorios tengo programados?
   ```
   **Esperado**: Lista con ID, schedule, message para cada cron activo.

3. **Eliminar cron**:
   ```
   Elimina el cron con ID 1
   ```
   **Esperado**: Confirmación de eliminación.

4. **Cron inválido**:
   ```
   Crea un cron con schedule "cada unicornio"
   ```
   **Esperado**: Error descriptivo de validación del cron expression.

5. **Verificar disparo**: Crear cron en 1 minuto → esperar → verificar que el mensaje llega por WhatsApp.

---

### F9: Intelligent File Loading

1. **Outline de archivo Python**:
   ```
   /agent Dame el outline de app/webhook/router.py
   ```
   **Esperado**: Lista de funciones/clases con números de línea.

2. **Leer rango específico**:
   ```
   /agent Lee las líneas 100-150 de app/webhook/router.py
   ```
   **Esperado**: Exactamente 51 líneas con números de línea prefixados.

3. **Outline de archivo no-Python**:
   ```
   /agent Dame el outline de CLAUDE.md
   ```
   **Esperado**: Respuesta útil (puede ser via regex o texto plano).

4. **Rango out-of-bounds**:
   ```
   /agent Lee las líneas 99999-99999 de app/config.py
   ```
   **Esperado**: Error descriptivo o resultado vacío (no crash).

5. **Path traversal bloqueado**:
   ```
   /agent Lee ../../../etc/passwd
   ```
   **Esperado**: Error de seguridad (bloqueado por `_is_safe_path`).

---

### F10: Multi-Project Workspace

**Setup**: `PROJECTS_ROOT=/path/to/projects` en `.env` con al menos 2 proyectos.

1. **Listar workspaces**:
   ```
   /agent ¿Qué proyectos tengo disponibles?
   ```
   **Esperado**: Lista de subdirectorios en `PROJECTS_ROOT`.

2. **Cambiar workspace**:
   ```
   /agent Cambia al proyecto "backend-api"
   ```
   **Esperado**: Confirmación del cambio, próximas operaciones en el nuevo directorio.

3. **Verificar cambio**:
   ```
   /agent Lista los archivos del directorio raíz
   ```
   **Esperado**: Archivos del proyecto "backend-api" (no del proyecto original).

4. **Workspace inválido**:
   ```
   /agent Cambia al workspace "no_existe"
   ```
   **Esperado**: Error descriptivo.

5. **Sin PROJECTS_ROOT**:
   Con `PROJECTS_ROOT=""`, listar workspaces → error descriptivo.

---

## Verificación en logs

```bash
# Cron job creado
grep "create_cron" data/wasap.log

# Cron disparado
grep "cron.*fired\|cron.*dispatched" data/wasap.log

# Workspace switch
grep "switch_workspace\|set_project_root" data/wasap.log
```

---

## Queries de DB

```sql
-- Cron jobs activos
SELECT * FROM user_cron_jobs WHERE active=1;

-- Historial de crons (incluyendo eliminados)
SELECT id, phone_number, schedule, message, active, created_at FROM user_cron_jobs ORDER BY id DESC LIMIT 10;
```
