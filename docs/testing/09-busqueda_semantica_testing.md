# Testing Manual: Búsqueda Semántica

> **Feature documentada**: [`docs/features/09-busqueda_semantica.md`](../features/09-busqueda_semantica.md)
> **Requisitos previos**: Container corriendo, `nomic-embed-text` descargado en Ollama, sqlite-vec disponible.

---

## Verificar que la feature está activa

```bash
docker compose logs -f wasap | head -40
```

Confirmar:
- `sqlite-vec loaded successfully` (o `sqlite-vec not available — falling back to recency`)
- `Embedding backfill completed` (o `Embedding backfill failed at startup` si no hay modelo)

---

## Casos de prueba principales

| Paso | Acción | Resultado esperado |
|------|--------|-------------------|
| 1 | `/remember Mi cumpleaños es el 15 de marzo` | Memoria guardada + embedding creado |
| 2 | Esperar 2 segundos (backfill async) | |
| 3 | `¿Cuándo es mi cumpleaños?` | El agente encuentra la memoria semánticamente y responde "15 de marzo" |
| 4 | `¿Qué sé sobre fechas importantes?` | Busca memorias semánticamente relacionadas a "fechas" |

---

## Verificar en logs

```bash
# Backfill al startup
docker compose logs -f wasap 2>&1 | grep -i "backfill\|embed"

# Búsqueda semántica por request
docker compose logs -f wasap 2>&1 | grep -i "semantic\|similarity\|vec_memories"
```

---

## Queries de verificación en DB

```bash
# Memorias con embedding
sqlite3 data/wasap.db "SELECT m.id, substr(m.content,1,50) FROM memories m JOIN vec_memories v ON v.rowid=m.id WHERE m.active=1;"

# Notas con embedding
sqlite3 data/wasap.db "SELECT COUNT(*) FROM vec_notes;"

# Verificar que sqlite-vec está cargado
sqlite3 data/wasap.db "SELECT vec_version();"
```

---

## Verificar graceful degradation

1. Renombrar la extensión sqlite-vec (para simular que no existe)
2. Reiniciar container
3. Verificar en logs: `sqlite-vec not available`
4. Enviar mensajes — el agente debe funcionar normalmente usando fallback por recencia

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| `sqlite-vec not available` | Extensión no compilada para la plataforma/arch | Verificar que `sqlite-vec` está en el Dockerfile |
| Búsqueda no encuentra memorias nuevas | Embedding aún no creado (async) | Verificar `grep embed` en logs |
| `nomic-embed-text not found` | Modelo no descargado | `ollama pull nomic-embed-text` |
