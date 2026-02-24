class SecurityException(Exception):
    """Base exception for security-related errors."""

    pass


class HitlRequiredException(SecurityException):
    """Raised when a tool execution is flagged and requires human-in-the-loop approval."""

    def __init__(self, tool_name: str, arguments: dict, reason: str, rule_id: str):
        self.tool_name = tool_name
        self.arguments = arguments
        self.reason = reason
        self.rule_id = rule_id
        super().__init__(f"Tool {tool_name} flagged for HITL approval. Reason: {reason}")
