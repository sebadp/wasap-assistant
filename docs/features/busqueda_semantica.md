# Feature: Búsqueda Semántica

> **Versión**: v1.0
> **Fecha de implementación**: 2026-01
> **Fase**: Fase 6
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

El agente busca memorias y notas por significado, no solo por texto exacto. Usa embeddings locales (nomic-embed-text) almacenados en sqlite-vec para encontrar información semánticamente relevante al mensaje del usuario.

---

## Arquitectura

```
[Mensaje del usuario: "¿Cuándo es mi cumpleaños?"]
         │
         ▼
[OllamaClient.embed(query)] ──► vector 768 dims
         │
         ├─► vec_memories (sqlite-vec) → cosine similarity → top-K memorias
         ├─► vec_notes (sqlite-vec) → cosine similarity → top-K notas
         └─► vec_project_notes (sqlite-vec) → cosine similarity → notas de proyecto
         │
         ▼
[Resultados inyectados en contexto LLM como "Relevant memories: ..."]
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/embeddings/indexer.py` | `embed_memory()`, `embed_note()`, `backfill_embeddings()` |
| `app/database/db.py` | Tablas virtual `vec_memories`, `vec_notes`, `vec_project_notes` |
| `app/database/repository.py` | `search_memories_by_embedding()`, `search_notes_by_embedding()` |
| `app/llm/client.py` | `OllamaClient.embed()` — genera embeddings via Ollama |
| `app/webhook/router.py` | `_get_query_embedding()` — computa una vez, reutiliza para memorias + notas |

---

## Walkthrough técnico

1. **Startup**: `backfill_embeddings()` indexa memorias/notas que no tienen embedding aún
2. **Per-request**: `_get_query_embedding()` computa el embedding del mensaje del usuario (una vez)
3. **Búsqueda**: el embedding se usa en `search_memories_by_embedding()` con cosine distance
4. **Top-K**: se retornan las `semantic_search_top_k` memorias más similares
5. **Fallback**: si sqlite-vec no está disponible → `get_active_memories(limit=...)` por recencia
6. **Indexing en escritura**: al crear una memoria, `embed_memory()` genera y almacena el embedding

### Formato de almacenamiento

- Vectores serializados con `struct.pack(f"{len(v)}f", *v)` como BLOB en sqlite-vec
- Dimensión: 768 (nomic-embed-text)
- Distancia: cosine (1 - similarity)

---

## Cómo extenderla

- **Cambiar modelo de embeddings**: `EMBEDDING_MODEL` en `.env` (cambiar dimensiones en `EMBEDDING_DIMENSIONS`)
- **Agregar nueva tabla vectorial**: DDL en `db.py`, indexer en `indexer.py`, query en `repository.py`
- **Cambiar top-K**: `SEMANTIC_SEARCH_TOP_K` en `.env`

---

## Guía de testing

→ Ver [`docs/testing/busqueda_semantica_testing.md`](../testing/busqueda_semantica_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| sqlite-vec | Pinecone, ChromaDB, FAISS | Zero-dependency externa, misma DB del app |
| nomic-embed-text (768 dims) | all-MiniLM (384 dims) | Mejor calidad, corre local en Ollama |
| Backfill en startup | Lazy indexing | Garantiza que todo está indexado al arrancar |
| Fallback a recencia si no hay vec | Error duro | La app funciona sin embeddings |
| Un embedding por query, reutilizado | Embedding separado por búsqueda | Performance — embed() es ~50ms |

---

## Gotchas y edge cases

- **sqlite-vec puede no cargar** si la extensión no está compilada para la plataforma. La app continúa sin búsqueda semántica.
- **`check_same_thread=False`** es necesario para sqlite-vec porque asyncio puede cambiar de thread.
- **`enable_load_extension()`** se llama durante init, luego se deshabilita por seguridad.
- **Backfill** es best-effort — errores se loguean pero nunca propagan.

---

## Variables de configuración relevantes

| Variable (`config.py`) | Default | Efecto |
|---|---|---|
| `SEMANTIC_SEARCH_ENABLED` | `True` | Habilita/deshabilita búsqueda semántica |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Modelo para embeddings |
| `EMBEDDING_DIMENSIONS` | `768` | Dimensiones del vector |
| `SEMANTIC_SEARCH_TOP_K` | `10` | Resultados máximos por búsqueda |
