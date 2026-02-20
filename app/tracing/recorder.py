"""TraceRecorder: async SQLite persistence for traces and spans. Best-effort."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class TraceRecorder:
    """Persists trace data to SQLite via the shared Repository.

    All methods are best-effort: exceptions are caught and logged, never propagated.
    """

    def __init__(self, repository) -> None:
        self._repo = repository

    async def start_trace(
        self,
        trace_id: str,
        phone_number: str,
        input_text: str,
        message_type: str = "text",
    ) -> None:
        try:
            await self._repo.save_trace(trace_id, phone_number, input_text, message_type)
        except Exception:
            logger.debug("TraceRecorder.start_trace failed", exc_info=True)

    async def finish_trace(
        self,
        trace_id: str,
        status: str,
        output_text: str | None = None,
        wa_message_id: str | None = None,
    ) -> None:
        try:
            await self._repo.finish_trace(trace_id, status, output_text, wa_message_id)
        except Exception:
            logger.debug("TraceRecorder.finish_trace failed", exc_info=True)

    async def start_span(
        self,
        trace_id: str,
        span_id: str,
        name: str,
        kind: str,
        parent_id: str | None,
    ) -> None:
        try:
            await self._repo.save_trace_span(span_id, trace_id, name, kind, parent_id)
        except Exception:
            logger.debug("TraceRecorder.start_span failed", exc_info=True)

    async def finish_span(
        self,
        span_id: str,
        status: str,
        latency_ms: float,
        input_data: Any = None,
        output_data: Any = None,
        metadata: dict | None = None,
    ) -> None:
        try:
            await self._repo.finish_trace_span(
                span_id,
                status,
                latency_ms,
                input_data,
                output_data,
                metadata,
            )
        except Exception:
            logger.debug("TraceRecorder.finish_span failed", exc_info=True)

    async def add_score(
        self,
        trace_id: str,
        name: str,
        value: float,
        source: str = "system",
        comment: str | None = None,
        span_id: str | None = None,
    ) -> None:
        try:
            await self._repo.save_trace_score(trace_id, name, value, source, comment, span_id)
        except Exception:
            logger.debug("TraceRecorder.add_score failed", exc_info=True)

    async def set_trace_output(self, trace_id: str, output_text: str) -> None:
        # Output is set when finishing the trace; this is a no-op that can be
        # called mid-stream to cache the value before __aexit__
        pass  # stored in TraceContext._output_text

    async def set_trace_wa_message_id(self, trace_id: str, wa_message_id: str) -> None:
        # wa_message_id is set when finishing the trace; same pattern
        pass  # stored in TraceContext._wa_message_id
