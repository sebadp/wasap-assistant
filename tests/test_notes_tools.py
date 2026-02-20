from app.skills.models import ToolCall
from app.skills.registry import SkillRegistry
from app.skills.tools.notes_tools import register


async def _make_registry(repository):
    reg = SkillRegistry(skills_dir="/nonexistent")
    register(reg, repository)
    return reg


async def test_save_note(repository):
    reg = await _make_registry(repository)
    result = await reg.execute_tool(
        ToolCall(
            name="save_note",
            arguments={"title": "Shopping", "content": "Buy milk and eggs"},
        )
    )
    assert result.success
    assert "Shopping" in result.content
    assert "ID:" in result.content


async def test_list_notes_empty(repository):
    reg = await _make_registry(repository)
    result = await reg.execute_tool(ToolCall(name="list_notes", arguments={}))
    assert result.success
    assert "No notes" in result.content


async def test_list_notes_with_data(repository):
    reg = await _make_registry(repository)
    await repository.save_note("Note 1", "Content 1")
    await repository.save_note("Note 2", "Content 2")

    result = await reg.execute_tool(ToolCall(name="list_notes", arguments={}))
    assert result.success
    assert "Note 1" in result.content
    assert "Note 2" in result.content


async def test_search_notes(repository):
    reg = await _make_registry(repository)
    await repository.save_note("Shopping", "Buy milk")
    await repository.save_note("Work", "Fix the bug")

    result = await reg.execute_tool(ToolCall(name="search_notes", arguments={"query": "milk"}))
    assert result.success
    assert "Shopping" in result.content
    assert "Work" not in result.content


async def test_search_notes_no_results(repository):
    reg = await _make_registry(repository)
    result = await reg.execute_tool(
        ToolCall(name="search_notes", arguments={"query": "nonexistent"})
    )
    assert result.success
    assert "No notes" in result.content


async def test_delete_note(repository):
    reg = await _make_registry(repository)
    note_id = await repository.save_note("To Delete", "Delete me")

    result = await reg.execute_tool(ToolCall(name="delete_note", arguments={"note_id": note_id}))
    assert result.success
    assert "deleted" in result.content

    # Verify it's gone
    notes = await repository.list_notes()
    assert len(notes) == 0


async def test_delete_nonexistent_note(repository):
    reg = await _make_registry(repository)
    result = await reg.execute_tool(ToolCall(name="delete_note", arguments={"note_id": 999}))
    assert result.success
    assert "not found" in result.content
