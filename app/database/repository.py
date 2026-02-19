from __future__ import annotations

import json
import struct

import aiosqlite

from app.models import ChatMessage, Memory, Note


class Repository:
    def __init__(self, conn: aiosqlite.Connection):
        self._conn = conn

    async def get_or_create_conversation(self, phone_number: str) -> int:
        cursor = await self._conn.execute(
            "SELECT id FROM conversations WHERE phone_number = ?",
            (phone_number,),
        )
        row = await cursor.fetchone()
        if row:
            await self._conn.execute(
                "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
                (row[0],),
            )
            await self._conn.commit()
            return row[0]
        cursor = await self._conn.execute(
            "INSERT INTO conversations (phone_number) VALUES (?)",
            (phone_number,),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def save_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        wa_message_id: str | None = None,
    ) -> int:
        cursor = await self._conn.execute(
            "INSERT INTO messages (conversation_id, role, content, wa_message_id) VALUES (?, ?, ?, ?)",
            (conversation_id, role, content, wa_message_id),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def get_recent_messages(
        self, conversation_id: int, limit: int
    ) -> list[ChatMessage]:
        cursor = await self._conn.execute(
            "SELECT role, content FROM messages "
            "WHERE conversation_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (conversation_id, limit),
        )
        rows = await cursor.fetchall()
        return [ChatMessage(role=r[0], content=r[1]) for r in reversed(rows)]

    async def get_message_count(self, conversation_id: int) -> int:
        cursor = await self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        row = await cursor.fetchone()
        return row[0]

    async def is_duplicate(self, wa_message_id: str) -> bool:
        cursor = await self._conn.execute(
            "SELECT 1 FROM messages WHERE wa_message_id = ?",
            (wa_message_id,),
        )
        return await cursor.fetchone() is not None

    async def clear_conversation(self, conversation_id: int) -> None:
        await self._conn.execute(
            "DELETE FROM messages WHERE conversation_id = ?",
            (conversation_id,),
        )
        await self._conn.execute(
            "DELETE FROM summaries WHERE conversation_id = ?",
            (conversation_id,),
        )
        await self._conn.commit()

    async def save_summary(
        self, conversation_id: int, summary_text: str, message_count: int
    ) -> None:
        await self._conn.execute(
            "INSERT INTO summaries (conversation_id, content, message_count) VALUES (?, ?, ?)",
            (conversation_id, summary_text, message_count),
        )
        await self._conn.commit()

    async def get_latest_summary(self, conversation_id: int) -> str | None:
        cursor = await self._conn.execute(
            "SELECT content FROM summaries WHERE conversation_id = ? ORDER BY id DESC LIMIT 1",
            (conversation_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def add_memory(self, content: str, category: str | None = None) -> int:
        cursor = await self._conn.execute(
            "INSERT INTO memories (content, category) VALUES (?, ?)",
            (content, category),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def remove_memory(self, content: str) -> bool:
        cursor = await self._conn.execute(
            "UPDATE memories SET active = 0 WHERE content = ? AND active = 1",
            (content,),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    async def list_memories(self) -> list[Memory]:
        cursor = await self._conn.execute(
            "SELECT id, content, category, active, created_at FROM memories WHERE active = 1 ORDER BY id",
        )
        rows = await cursor.fetchall()
        return [
            Memory(id=r[0], content=r[1], category=r[2], active=bool(r[3]), created_at=r[4])
            for r in rows
        ]

    async def get_active_memories(self, limit: int | None = None) -> list[str]:
        sql = "SELECT content FROM memories WHERE active = 1 ORDER BY id"
        params: tuple = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        cursor = await self._conn.execute(sql, params)
        rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def delete_old_messages(
        self, conversation_id: int, keep_last: int
    ) -> int:
        cursor = await self._conn.execute(
            "DELETE FROM messages WHERE conversation_id = ? AND id NOT IN "
            "(SELECT id FROM messages WHERE conversation_id = ? ORDER BY created_at DESC, id DESC LIMIT ?)",
            (conversation_id, conversation_id, keep_last),
        )
        await self._conn.commit()
        return cursor.rowcount

    # --- Deduplication ---

    async def try_claim_message(self, wa_message_id: str) -> bool:
        """Atomically claim a message ID. Returns True if already processed (duplicate)."""
        cursor = await self._conn.execute(
            "INSERT OR IGNORE INTO processed_messages (wa_message_id) VALUES (?)",
            (wa_message_id,),
        )
        await self._conn.commit()
        # If rowcount == 0, the INSERT was ignored → message was already claimed
        return cursor.rowcount == 0

    # --- Reply context ---

    async def get_message_by_wa_id(self, wa_message_id: str) -> ChatMessage | None:
        cursor = await self._conn.execute(
            "SELECT role, content FROM messages WHERE wa_message_id = ?",
            (wa_message_id,),
        )
        row = await cursor.fetchone()
        if row:
            return ChatMessage(role=row[0], content=row[1])
        return None

    # --- Notes ---

    async def save_note(self, title: str, content: str) -> int:
        cursor = await self._conn.execute(
            "INSERT INTO notes (title, content) VALUES (?, ?)",
            (title, content),
        )
        await self._conn.commit()
        return cursor.lastrowid

    async def list_notes(self) -> list[Note]:
        cursor = await self._conn.execute(
            "SELECT id, title, content, created_at FROM notes ORDER BY id DESC",
        )
        rows = await cursor.fetchall()
        return [
            Note(id=r[0], title=r[1], content=r[2], created_at=r[3])
            for r in rows
        ]

    async def search_notes(self, query: str) -> list[Note]:
        cursor = await self._conn.execute(
            "SELECT id, title, content, created_at FROM notes "
            "WHERE title LIKE ? OR content LIKE ? ORDER BY id DESC",
            (f"%{query}%", f"%{query}%"),
        )
        rows = await cursor.fetchall()
        return [
            Note(id=r[0], title=r[1], content=r[2], created_at=r[3])
            for r in rows
        ]

    async def delete_note(self, note_id: int) -> bool:
        cursor = await self._conn.execute(
            "DELETE FROM notes WHERE id = ?",
            (note_id,),
        )
        await self._conn.commit()
        return cursor.rowcount > 0

    # --- Embeddings (sqlite-vec) ---

    @staticmethod
    def _serialize_vector(vec: list[float]) -> bytes:
        return struct.pack(f"{len(vec)}f", *vec)

    async def save_embedding(self, memory_id: int, embedding: list[float]) -> None:
        blob = self._serialize_vector(embedding)
        await self._conn.execute(
            "INSERT OR REPLACE INTO vec_memories (memory_id, embedding) VALUES (?, ?)",
            (memory_id, blob),
        )
        await self._conn.commit()

    async def delete_embedding(self, memory_id: int) -> None:
        await self._conn.execute(
            "DELETE FROM vec_memories WHERE memory_id = ?",
            (memory_id,),
        )
        await self._conn.commit()

    async def search_similar_memories(
        self, embedding: list[float], top_k: int = 10
    ) -> list[str]:
        blob = self._serialize_vector(embedding)
        cursor = await self._conn.execute(
            "SELECT m.content FROM vec_memories v "
            "JOIN memories m ON m.id = v.memory_id "
            "WHERE m.active = 1 AND v.embedding MATCH ? AND k = ? "
            "ORDER BY distance",
            (blob, top_k),
        )
        rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def get_unembedded_memories(self) -> list[tuple[int, str]]:
        cursor = await self._conn.execute(
            "SELECT m.id, m.content FROM memories m "
            "LEFT JOIN vec_memories v ON v.memory_id = m.id "
            "WHERE m.active = 1 AND v.memory_id IS NULL",
        )
        rows = await cursor.fetchall()
        return [(r[0], r[1]) for r in rows]

    async def remove_memory_return_id(self, content: str) -> int | None:
        """Deactivate a memory and return its ID (for embedding cleanup)."""
        cursor = await self._conn.execute(
            "SELECT id FROM memories WHERE content = ? AND active = 1",
            (content,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        memory_id = row[0]
        await self._conn.execute(
            "UPDATE memories SET active = 0 WHERE id = ?",
            (memory_id,),
        )
        await self._conn.commit()
        return memory_id

    # --- Note Embeddings ---

    async def save_note_embedding(self, note_id: int, embedding: list[float]) -> None:
        blob = self._serialize_vector(embedding)
        await self._conn.execute(
            "INSERT OR REPLACE INTO vec_notes (note_id, embedding) VALUES (?, ?)",
            (note_id, blob),
        )
        await self._conn.commit()

    async def delete_note_embedding(self, note_id: int) -> None:
        await self._conn.execute(
            "DELETE FROM vec_notes WHERE note_id = ?",
            (note_id,),
        )
        await self._conn.commit()

    async def search_similar_notes(
        self, embedding: list[float], top_k: int = 5
    ) -> list[Note]:
        blob = self._serialize_vector(embedding)
        cursor = await self._conn.execute(
            "SELECT n.id, n.title, n.content, n.created_at FROM vec_notes v "
            "JOIN notes n ON n.id = v.note_id "
            "WHERE v.embedding MATCH ? AND k = ? "
            "ORDER BY distance",
            (blob, top_k),
        )
        rows = await cursor.fetchall()
        return [
            Note(id=r[0], title=r[1], content=r[2], created_at=r[3])
            for r in rows
        ]

    # --- User Profiles ---

    async def get_user_profile(self, phone_number: str) -> dict:
        """Return user profile dict, creating the row if it doesn't exist yet."""
        cursor = await self._conn.execute(
            "SELECT onboarding_state, data, message_count FROM user_profiles WHERE phone_number = ?",
            (phone_number,),
        )
        row = await cursor.fetchone()
        if row:
            return {
                "onboarding_state": row[0],
                "data": json.loads(row[1]),
                "message_count": row[2],
            }
        # Create on first access
        await self._conn.execute(
            "INSERT OR IGNORE INTO user_profiles (phone_number) VALUES (?)",
            (phone_number,),
        )
        await self._conn.commit()
        return {"onboarding_state": "pending", "data": {}, "message_count": 0}

    async def save_user_profile(self, phone_number: str, state: str, data: dict) -> None:
        """Upsert user profile state and data."""
        await self._conn.execute(
            "INSERT INTO user_profiles (phone_number, onboarding_state, data, updated_at) "
            "VALUES (?, ?, ?, datetime('now')) "
            "ON CONFLICT(phone_number) DO UPDATE SET "
            "onboarding_state = excluded.onboarding_state, "
            "data = excluded.data, "
            "updated_at = excluded.updated_at",
            (phone_number, state, json.dumps(data, ensure_ascii=False)),
        )
        await self._conn.commit()

    async def increment_profile_message_count(self, phone_number: str) -> int:
        """Atomically increment message_count and return the new value."""
        await self._conn.execute(
            "INSERT INTO user_profiles (phone_number, message_count) VALUES (?, 1) "
            "ON CONFLICT(phone_number) DO UPDATE SET "
            "message_count = message_count + 1, updated_at = datetime('now')",
            (phone_number,),
        )
        await self._conn.commit()
        cursor = await self._conn.execute(
            "SELECT message_count FROM user_profiles WHERE phone_number = ?",
            (phone_number,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 1

    async def reset_user_profile(self, phone_number: str) -> None:
        """Reset profile to pending state (for /setup command)."""
        await self._conn.execute(
            "INSERT INTO user_profiles (phone_number, onboarding_state, data, message_count) "
            "VALUES (?, 'pending', '{}', 0) "
            "ON CONFLICT(phone_number) DO UPDATE SET "
            "onboarding_state = 'pending', data = '{}', message_count = 0, "
            "updated_at = datetime('now')",
            (phone_number,),
        )
        await self._conn.commit()

    async def get_unembedded_notes(self) -> list[tuple[int, str, str]]:
        cursor = await self._conn.execute(
            "SELECT n.id, n.title, n.content FROM notes n "
            "LEFT JOIN vec_notes v ON v.note_id = n.id "
            "WHERE v.note_id IS NULL",
        )
        rows = await cursor.fetchall()
        return [(r[0], r[1], r[2]) for r in rows]
