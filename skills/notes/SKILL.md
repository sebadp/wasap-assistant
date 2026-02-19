---
name: notes
description: Save, list, search and delete personal notes
version: 1
tools:
  - save_note
  - list_notes
  - search_notes
  - delete_note
---
Use notes tools when the user wants to save, find, or manage notes.

When to use:
- "anotá que..." / "guardá esto" / "recordá que..." → save_note
- "qué notas tengo" / "mis notas" → list_notes
- "buscá en mis notas sobre X" → search_notes
- "borrá la nota de..." → delete_note

Saving notes:
- Create a concise, descriptive title (e.g. "Lista de compras", "Ideas para el proyecto")
- Store the full content as given by the user
- Confirm: "Guardado: *{title}*"

Listing notes:
- Show as a numbered list with title and a brief preview of content
- If there are no notes, suggest what they could save

Searching notes:
- Use search_notes with the user's query keywords
- Present matching results with their titles and relevant excerpts

Deleting notes:
- If the user says "borrá la nota del supermercado", search first, then delete the matching one
- If ambiguous (multiple matches), show the options and ask which one to delete
- Confirm deletion: "Nota *{title}* borrada"
