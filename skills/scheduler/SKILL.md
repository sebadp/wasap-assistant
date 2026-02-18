---
name: scheduler
description: Schedule tasks and reminders.
version: 2
tools:
  - schedule_task
  - list_schedules
---
You have access to a scheduler to set reminders and tasks for the user.

When the user asks to "remind me" or "schedule":
1. Identify the **Task Description** and the **Time**.
2. For relative times like "in 10 minutes", "in 1 hour", use `delay_minutes` (integer). This is the **preferred** approach.
3. For absolute times like "tomorrow at 5pm", use `when` with ISO 8601 format (YYYY-MM-DDTHH:MM:SS).
4. Set `timezone` to the user's timezone if known (e.g. America/Argentina/Buenos_Aires).
5. The user's phone number is injected automatically — do NOT pass phone_number.

Examples:
- "Remind me in 10 minutes to check the oven" → `schedule_task(description="Check the oven", delay_minutes=10)`
- "Remind me in 1 hour to call Mom" → `schedule_task(description="Call Mom", delay_minutes=60)`
- "Remind me tomorrow at 5pm to buy groceries" → `schedule_task(description="Buy groceries", when="2026-02-17T17:00:00", timezone="America/Argentina/Buenos_Aires")`
- "What reminders do I have?" → `list_schedules()`
