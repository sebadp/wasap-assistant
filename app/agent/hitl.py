"""Human-in-the-Loop (HITL) mechanism for agentic sessions.

Allows the agent to pause and ask the user a question via WhatsApp,
waiting for their reply before resuming execution.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.whatsapp.client import WhatsAppClient

logger = logging.getLogger(__name__)

# Per-user: event that fires when the user replies, and the reply text
_pending_approvals: dict[str, asyncio.Event] = {}
_approval_replies: dict[str, str] = {}

_DEFAULT_TIMEOUT = 120  # seconds


async def request_user_approval(
    phone_number: str,
    question: str,
    wa_client: WhatsAppClient,
    timeout: int = _DEFAULT_TIMEOUT,
) -> str:
    """Pause the agent and ask the user a yes/no or free-text question via WhatsApp.

    The agent execution block here. The router injects the user's next message
    via resolve_hitl(). Returns the user's response string, or a TIMEOUT message.
    """
    event = asyncio.Event()
    _pending_approvals[phone_number] = event
    _approval_replies[phone_number] = ""

    await wa_client.send_message(
        phone_number,
        f"⏸️ *El agente necesita tu aprobación para continuar:*\n\n{question}\n\n"
        "_Responde con tu confirmación o instrucciones._",
    )
    logger.info("HITL: waiting for approval from %s (timeout=%ds)", phone_number, timeout)

    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        reply = _approval_replies.pop(phone_number, "")
        logger.info("HITL: received approval from %s: %r", phone_number, reply[:50])
        return reply
    except TimeoutError:
        logger.warning("HITL: timeout waiting for approval from %s", phone_number)
        return f"TIMEOUT: The user did not respond within {timeout} seconds. Proceeding with the safest option."
    finally:
        _pending_approvals.pop(phone_number, None)
        _approval_replies.pop(phone_number, None)  # Fix: also clean up on timeout



def resolve_hitl(phone_number: str, user_message: str) -> bool:
    """Called from router.py when a message arrives for a user with an active HITL wait.

    Returns True if the message was consumed by the HITL (and should NOT be processed
    as a normal chat message). Returns False if there is no active HITL for this user.
    """
    event = _pending_approvals.get(phone_number)
    if event and not event.is_set():
        _approval_replies[phone_number] = user_message
        event.set()
        logger.info("HITL: resolved for %s", phone_number)
        return True
    return False


def has_pending_approval(phone_number: str) -> bool:
    """Check whether there is an active HITL wait for this user."""
    event = _pending_approvals.get(phone_number)
    return event is not None and not event.is_set()
