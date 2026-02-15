from __future__ import annotations

from typing import TYPE_CHECKING

from app.skills.registry import SkillRegistry

if TYPE_CHECKING:
    from app.database.repository import Repository


import logging

logger = logging.getLogger(__name__)

def register(registry: SkillRegistry, repository: Repository) -> None:
    async def save_note(title: str, content: str) -> str:
        logger.info(f"Saving note: {title}")
        note_id = await repository.save_note(title, content)
        msg = f"Note saved (ID: {note_id}): {title}"
        logger.info(msg)
        return msg

    async def list_notes() -> str:
        logger.info("Listing notes")
        notes = await repository.list_notes()
        if not notes:
            logger.info("No notes found")
            return "No notes found."
        lines = []
        for n in notes:
            lines.append(f"[{n.id}] {n.title}: {n.content[:80]}")
        count = len(notes)
        logger.info(f"Found {count} notes")
        return "\n".join(lines)

    async def search_notes(query: str) -> str:
        logger.info(f"Searching notes with query: {query}")
        notes = await repository.search_notes(query)
        if not notes:
            logger.info(f"No notes match query: {query}")
            return f"No notes matching '{query}'."
        lines = []
        for n in notes:
            lines.append(f"[{n.id}] {n.title}: {n.content[:80]}")
        logger.info(f"Found {len(notes)} matching notes")
        return "\n".join(lines)

    async def delete_note(note_id: int) -> str:
        logger.info(f"Deleting note ID: {note_id}")
        deleted = await repository.delete_note(note_id)
        if deleted:
            msg = f"Note {note_id} deleted."
            logger.info(msg)
            return msg
        msg = f"Note {note_id} not found."
        logger.warning(msg)
        return msg

    registry.register_tool(
        name="save_note",
        description="Save a new note with a title and content",
        parameters={
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the note",
                },
                "content": {
                    "type": "string",
                    "description": "Content of the note",
                },
            },
            "required": ["title", "content"],
        },
        handler=save_note,
        skill_name="notes",
    )

    registry.register_tool(
        name="list_notes",
        description="List all saved notes",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=list_notes,
        skill_name="notes",
    )

    registry.register_tool(
        name="search_notes",
        description="Search notes by keyword in title or content",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keyword",
                },
            },
            "required": ["query"],
        },
        handler=search_notes,
        skill_name="notes",
    )

    registry.register_tool(
        name="delete_note",
        description="Delete a note by its ID",
        parameters={
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "integer",
                    "description": "ID of the note to delete",
                },
            },
            "required": ["note_id"],
        },
        handler=delete_note,
        skill_name="notes",
    )
