# PRP: Agentic Security Layer Implementation

This plan outlines the execution steps for the Agentic Security Layer PRD.

## Phase 1: Configuration & Models
- [x] Create `data/security_policies.yaml` with default rules (e.g., block destructive `rm`, flag `sudo`).
- [x] Create `app/security/__init__.py`.
- [x] Create Pydantic models in `app/security/models.py` (or within `policy_engine.py`) for `PolicyRule`, `PolicyDecision`.

## Phase 2: Core Policy & Audit Modules
- [x] Implement `app/security/policy_engine.py` with `PolicyEngine.evaluate(tool_call)`.
- [x] Write integration test/unit tests for `PolicyEngine` to ensure regex matches and action precedence.
- [x] Implement `app/security/audit.py` (`AuditTrail` class) with SHA-256 rolling hash append-only to `data/audit_trail.jsonl`.
- [x] Write tests for `AuditTrail` integrity.

## Phase 3: Agent Loop & Executor Integration
- [x] Modify `app/skills/executor.py` to instantiate `PolicyEngine` and `AuditTrail`.
- [x] Inject `PolicyEngine.evaluate()` before executing `_run_tool_call()`.
- [x] Handle `block` action: Return an immediate text error to the tool result payload.
- [x] Handle `flag` action: Abort current tool iteration and raise `HitlRequiredException`.

## Phase 4: Human-in-the-Loop & UX
- [x] Modify `app/agent/loop.py` to catch `HitlRequiredException` (implemented via hitl_callback instead).
- [x] On exception, mutate agent status to `AWAITING_APPROVAL`, send WhatsApp message asking to reply "Aprobar" / "Rechazar", and halt the round.
- [x] Add intent mappings in `webhook/router.py` or new commands (`/approve`, `/reject`) to resume an `AWAITING_APPROVAL` session.
- [x] If approved, replay the flagged tool call; if rejected, return permission denied to the agent.

## Phase 5: Documentation
- [x] Check off tasks in this PRP as they are completed.
- [x] Run `make check` to ensure tests pass and code style is maintained.
- [x] Write `docs/features/23-agentic_security.md`.
- [x] Write `docs/testing/23-agentic_security_testing.md`.
- [x] Update `docs/features/README.md`, `docs/testing/README.md`, and `CLAUDE.md` following the 5-step protocol.
