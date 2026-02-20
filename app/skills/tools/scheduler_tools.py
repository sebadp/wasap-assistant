from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from app.whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)

# Global references (set via set_scheduler / set_current_user)
_scheduler: AsyncIOScheduler | None = None
_whatsapp_client: WhatsAppClient | None = None
_current_user_phone: str | None = None
_message_received_at: datetime | None = None

DEFAULT_TIMEZONE = ZoneInfo("UTC")


def set_scheduler(scheduler: AsyncIOScheduler, wa_client: WhatsAppClient) -> None:
    """Initialize the global scheduler reference."""
    global _scheduler, _whatsapp_client
    _scheduler = scheduler
    _whatsapp_client = wa_client


def set_current_user(phone_number: str, received_at: datetime) -> None:
    """Set the current user context for tool calls."""
    global _current_user_phone, _message_received_at
    _current_user_phone = phone_number
    _message_received_at = received_at


async def _send_reminder(phone_number: str, message: str) -> None:
    """Callback function to send the reminder."""
    if _whatsapp_client:
        try:
            await _whatsapp_client.send_message(phone_number, f"\u23f0 *Reminder*: {message}")
            logger.info("Sent reminder to %s: %s", phone_number, message)
        except Exception as e:
            logger.error("Failed to send reminder to %s: %s", phone_number, e)
    else:
        logger.warning("WhatsApp client not initialized, cannot send reminder")


async def schedule_task(
    description: str,
    delay_minutes: int | None = None,
    when: str | None = None,
    timezone: str = "UTC",
) -> str:
    """
    Schedule a one-time task or reminder.

    Use delay_minutes for relative times ("in 10 minutes") or
    when for absolute times ("tomorrow at 5pm").
    """
    if not _scheduler:
        return "Error: Scheduler is not initialized."

    phone = _current_user_phone
    if not phone:
        return "Error: No user phone number available."

    try:
        tz = ZoneInfo(timezone)
    except (KeyError, Exception):
        logger.warning("Invalid timezone %r, falling back to UTC", timezone)
        tz = DEFAULT_TIMEZONE

    try:
        if delay_minutes is not None:
            # Relative scheduling: base_time + N minutes
            # Use message_received_at so the delay counts from when the user
            # sent the message, not from when the LLM finished processing.
            delay = int(delay_minutes)
            if delay < 1:
                return "Error: delay_minutes must be at least 1."
            base = _message_received_at or datetime.now(tz)
            if base.tzinfo is None:
                base = base.replace(tzinfo=tz)
            run_date = base + timedelta(minutes=delay)
        elif when:
            # Absolute scheduling: parse ISO 8601
            run_date = datetime.fromisoformat(when)
            if run_date.tzinfo is None:
                run_date = run_date.replace(tzinfo=tz)
        else:
            return "Error: Provide either delay_minutes or when."

        job = _scheduler.add_job(
            _send_reminder,
            DateTrigger(run_date=run_date),
            args=[phone, description],
            name=description,
        )

        return f"Scheduled reminder '{description}' for {run_date} (Job ID: {job.id})"

    except ValueError as e:
        return f"Error: Invalid input. {e}"
    except Exception as e:
        logger.exception("Failed to schedule task")
        return f"Error scheduling task: {e}"


async def list_schedules() -> str:
    """List all currently scheduled active jobs."""
    if not _scheduler:
        return "Error: Scheduler is not active."

    jobs = _scheduler.get_jobs()
    if not jobs:
        return "No active schedules found."

    output = ["**Active Schedules:**"]
    for job in jobs:
        next_run = (
            job.next_run_time.strftime("%Y-%m-%d %H:%M:%S %Z") if job.next_run_time else "N/A"
        )
        output.append(f"- ID: `{job.id}` | Time: {next_run} | Task: {job.name}")

    return "\n".join(output)


if TYPE_CHECKING:
    from app.skills.registry import SkillRegistry


def register(registry: SkillRegistry) -> None:
    registry.register_tool(
        name="schedule_task",
        description="Schedule a future task or reminder. Use delay_minutes for relative times (e.g. 'in 10 minutes') or when for absolute times.",
        parameters={
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "What to remind about.",
                },
                "delay_minutes": {
                    "type": "integer",
                    "description": "Minutes from now to trigger the reminder. Use this for relative times like 'in 10 minutes', 'in an hour' (60).",
                },
                "when": {
                    "type": "string",
                    "description": "ISO 8601 datetime (YYYY-MM-DDTHH:MM:SS). Use this for absolute times like 'tomorrow at 5pm'. Only if delay_minutes is not suitable.",
                },
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone for the schedule (e.g. America/Argentina/Buenos_Aires). Default: UTC.",
                },
            },
            "required": ["description"],
        },
        handler=schedule_task,
        skill_name="scheduler",
    )
    registry.register_tool(
        name="list_schedules",
        description="List all active scheduled tasks.",
        parameters={
            "type": "object",
            "properties": {},
        },
        handler=list_schedules,
        skill_name="scheduler",
    )
