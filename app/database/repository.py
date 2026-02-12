from __future__ import annotations

import aiosqlite

from app.models import ChatMessage, Memory


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

    async def get_active_memories(self) -> list[str]:
        cursor = await self._conn.execute(
            "SELECT content FROM memories WHERE active = 1 ORDER BY id",
        )
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
