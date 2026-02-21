"""Agent session data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AgentStatus(str, Enum):
    RUNNING = "running"
    WAITING_USER = "waiting_user"  # HITL: esperando aprobación del usuario
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentSession:
    session_id: str
    phone_number: str
    objective: str               # El pedido original del usuario
    status: AgentStatus = AgentStatus.RUNNING
    iteration: int = 0
    max_iterations: int = 15
    started_at: datetime = field(default_factory=datetime.utcnow)
    context_messages: list = field(default_factory=list)
    task_plan: str | None = None  # task.md content (actualizado por el agente durante la sesión)
