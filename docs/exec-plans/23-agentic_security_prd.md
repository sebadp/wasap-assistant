# PRD: Agentic Security Layer

## 1. Goal & Context
The goal is to implement a robust security layer for the WasAP Autonomous Agent mode to prevent potentially destructive actions or unauthorized tool usage. This is inspired by modern "Agentic Detection and Response" (ADR) practices, employing Zero-Trust principles and Human-in-the-Loop workflows to secure the execution of sensitive tools.

## 2. The "What"
The security layer will consist of three main pillars:
1. **Runtime Policy Engine**: An evaluator that intercepts tool calls right before execution, acting as a deterministic filter separate from the LLM.
2. **Cryptographic Audit Trail**: An append-only log that securely records every sensitive action the agent takes along with the policy decision (allow, block, flag).
3. **Human-in-the-Loop (HitL)**: A mechanism that pauses execution when a tool matches a "flag" policy, requesting explicit authorization from the human operator via a WhatsApp interactive message.

## 3. The "Why"
As the agent gains more autonomy (e.g., shell access via `run_command` or external server connections via MCP), relying solely on LLM "prompted safety" is insufficient. A deterministic, rules-as-code barrier is strictly necessary to prevent accidental self-destruction or unauthorized operations.

## 4. Constraints
- **Format**: Policies must be defined in a versionable YAML file (`data/security_policies.yaml`), separating rules from core Python logic.
- **Fail-Secure**: If the policy engine encounters an error or ambiguous state, it MUST default to blocking or requesting human approval for sensitive endpoints.
- **Tracing Integration**: The security layer must interoperate cleanly with the existing tracing infrastructure, preferably adding its decisions to the existing tool execution spans.
- **Audit Tamper-Resistance**: Each entry in the Audit Trail must be cryptographically hashed (SHA-256) sequentially to mimic an immutable ledger.
