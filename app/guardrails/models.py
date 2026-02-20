from pydantic import BaseModel


class GuardrailResult(BaseModel):
    passed: bool
    check_name: str
    details: str = ""
    latency_ms: float = 0.0


class GuardrailReport(BaseModel):
    passed: bool
    results: list[GuardrailResult]
    total_latency_ms: float
