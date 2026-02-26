from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class PolicyAction(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"
    FLAG = "flag"


class PolicyRule(BaseModel):
    id: str
    target_tool: str
    argument_match: dict[str, str] = Field(default_factory=dict)
    action: PolicyAction
    reason: str

    model_config = ConfigDict(frozen=True)


class BasePolicy(BaseModel):
    version: str
    default_action: PolicyAction
    rules: list[PolicyRule]


class PolicyDecision(BaseModel):
    action: PolicyAction
    reason: str | None = None
    rule_id: str | None = None

    @property
    def is_allowed(self) -> bool:
        return self.action == PolicyAction.ALLOW

    @property
    def is_blocked(self) -> bool:
        return self.action == PolicyAction.BLOCK

    @property
    def requires_flag(self) -> bool:
        return self.action == PolicyAction.FLAG
