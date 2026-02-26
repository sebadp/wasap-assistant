# Testing Manual: Persistencia y Memoria

> **Feature documentada**: [`docs/features/03-persistencia_memoria.md`](../features/03-persistencia_memoria.md)
> **Requisitos previos**: Container corriendo (`docker compose up -d`).

---

## Verificar que la feature está activa

```bash
docker compose logs -f wasap | head -40
```

Confirmar que no hay errores de DB al startup.

---

## Casos de prueba principales

| Mensaje / Acción | Resultado esperado |
|---|---|
| `/remember Mi GitHub es sebadp` | "✅ Memoria guardada (id: N)" |
| `/memories` | Lista de memorias activas incluyendo la recién guardada |
| `/forget N` | "✅ Memoria N eliminada" |
| `/clear` | Historial limpiado, snapshot guardado |
| Enviar 25 mensajes seguidos | Summarization se activa (verificar en logs) |

---

## Verificar en logs

```bash
# Comandos procesados
docker compose logs -f wasap 2>&1 | grep -i "command"

# Summarization
docker compose logs -f wasap 2>&1 | grep -i "summar\|compact\|flush"
```

---

## Queries de verificación en DB

```bash
# Memorias activas
sqlite3 data/wasap.db "SELECT id, content, category FROM memories WHERE active=1 ORDER BY id DESC LIMIT 10;"

# Conversaciones
sqlite3 data/wasap.db "SELECT id, phone_number, created_at FROM conversations;"

# Mensajes recientes
sqlite3 data/wasap.db "SELECT role, substr(content,1,50), created_at FROM messages ORDER BY id DESC LIMIT 10;"

# Summaries
sqlite3 data/wasap.db "SELECT conversation_id, substr(content,1,80), created_at FROM summaries ORDER BY id DESC LIMIT 5;"
```

---

## Edge cases y validaciones

| Escenario | Resultado esperado |
|---|---|
| `/remember` sin texto | Mensaje de error |
| `/forget 999` (ID inexistente) | Mensaje de error indicando que no se encontró |
| DB file no existe al startup | Se crea automáticamente |
| MEMORY.md editado manualmente | Watcher detecta el cambio y sincroniza con DB |

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| "database is locked" | Múltiples escrituras concurrentes | Verificar que solo hay 1 instancia del container |
| Memorias desaparecen tras restart | MEMORY.md watcher no estaba activo | Verificar `MEMORY_FILE_WATCH_ENABLED=true` |
| Summarization no se activa | Menos de `conversation_max_messages` mensajes | Enviar más mensajes o bajar el threshold |
