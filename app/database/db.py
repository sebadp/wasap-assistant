from __future__ import annotations

import logging

import aiosqlite

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    phone_number  TEXT UNIQUE NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    wa_message_id   TEXT UNIQUE,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_wa_id ON messages(wa_message_id);

CREATE TABLE IF NOT EXISTS summaries (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id),
    content         TEXT NOT NULL,
    message_count   INTEGER NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS memories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content    TEXT NOT NULL,
    category   TEXT,
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    content    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS processed_messages (
    wa_message_id TEXT PRIMARY KEY,
    processed_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

VEC_SCHEMA_MEMORIES = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS vec_memories "
    "USING vec0(memory_id INTEGER PRIMARY KEY, embedding float[{dims}])"
)
VEC_SCHEMA_NOTES = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS vec_notes "
    "USING vec0(note_id INTEGER PRIMARY KEY, embedding float[{dims}])"
)


async def init_db(db_path: str, embedding_dims: int = 768) -> tuple[aiosqlite.Connection, bool]:
    """Initialize database and optionally load sqlite-vec.

    Returns (connection, vec_available).
    """
    # check_same_thread=False allows accessing the raw connection from
    # the main thread (needed for enable_load_extension during init)
    conn = await aiosqlite.connect(db_path, check_same_thread=False)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA synchronous=NORMAL")   # Faster, safe with WAL
    await conn.execute("PRAGMA cache_size=-32000")    # 32MB page cache in memory
    await conn.execute("PRAGMA temp_store=MEMORY")    # Temp tables in RAM
    await conn.execute("PRAGMA foreign_keys=ON")
    await conn.executescript(SCHEMA)
    await conn.commit()

    # Try to load sqlite-vec
    vec_available = False
    try:
        import sqlite_vec

        ext_path = sqlite_vec.loadable_path()
        # Load extension via the raw connection (safe during init — no concurrent queries)
        conn._connection.enable_load_extension(True)
        conn._connection.load_extension(ext_path)
        conn._connection.enable_load_extension(False)

        # Create vector tables
        await conn.execute(VEC_SCHEMA_MEMORIES.format(dims=embedding_dims))
        await conn.execute(VEC_SCHEMA_NOTES.format(dims=embedding_dims))
        await conn.commit()
        vec_available = True
        logger.info("sqlite-vec loaded successfully (dims=%d)", embedding_dims)
    except Exception:
        logger.warning("sqlite-vec not available, semantic search disabled", exc_info=True)

    return conn, vec_available
