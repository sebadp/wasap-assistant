# Plan de Implementación: Agentic Security Layer (Inspirado en Oktsec)

## Objetivo
Implementar una capa de seguridad para la modalidad de *Autonomous Agent* de WasAP. Basado en la arquitectura de **Oktsec** y las mejores prácticas de seguridad agéntica de **2026** (Agentic Detection and Response, Zero-Trust, Human-in-the-Loop). El foco es asegurar el uso de herramientas destructivas o críticas, particularmente `run_command` y llamadas a servidores MCP.

## Pilares de la Capa de Seguridad

### 1. Policy Engine (Reglas como Código)
Un evaluador de tiempo de ejecución (runtime) que intercepta el ciclo de ejecución de herramientas (`app/skills/executor.py`) *antes* de que la herramienta actúe.

- **Formato**: Archivo de configuración `data/security_policies.yaml`.
- **Reglas**: Basadas en expresiones regulares sobre los argumentos de las llamadas a variables (`run_command.command`, `scp`, etc.).
- **Acciones (Actions)**:
  - `allow`: La herramienta se ejecuta.
  - `block`: La herramienta se rechaza con un mensaje de error directo al modelo.
  - `flag` (Human-in-the-Loop): La ejecución se pausa. WasAP le envía al usuario un WhatsApp interactivo: *"El agente intenta ejecutar: `rm -rf data/`. ¿Autorizas? [Sí] [No]"*.

### 2. Audit Trail (Log Forense Inmutable)
Trazabilidad de seguridad de cada herramienta que altera estado. Ya tenemos `TraceRecorder` para las interacciones con el LLM, pero necesitamos un log específico y persistente de las *acciones del agente* en el SO.

- **Registro**: Base de datos SQLite o archivo Append-Only JSONL en `data/audit_trail.jsonl`.
- **Qué se guarda**: Timestamp, Tool Name, Argumentos Completos, Resultado de la Evaluación del Policy Engine (`allowed`, `blocked`, `flagged_approved`, `flagged_rejected`), y el resultado de la herramienta.
- **Hash/Inmutabilidad**: Opcionalmente, cada entrada incluye un hash SHA-256 de la entrada anterior para evitar tampering (estilo micro-blockchain, análogo a Oktsec).

## Archivos a Modificar / Crear

| Archivo | Acción | Descripción |
|---|---|---|
| `data/security_policies.yaml` | [NEW] | Archivo con las reglas base (ej: bloquear `rm -rf /`, flaggear `sudo`, etc.) |
| `app/security/__init__.py` | [NEW] | Módulo base de seguridad. |
| `app/security/policy_engine.py` | [NEW] | Parseador del YAML y evaluador de políticas contra un `ToolCall`. |
| `app/security/audit.py` | [NEW] | Grabador del Audit Trail con hash encoding (Append-Only). |
| `app/skills/executor.py` | [MODIFY] | Integrar `policy_engine.evaluate(tool_call)` antes de `_run_tool_call()`. Implementar la pausa de ejecución si el dictamen es `flag`. |
| `app/agent/loop.py` | [MODIFY] | Manejar pausas de ejecución (Human-in-the-Loop) esperando input de WhatsApp. |

## Muestra del `security_policies.yaml` a implementar:

```yaml
version: "1.0"
default_action: "allow"

rules:
  - id: "block_system_rm"
    target_tool: "run_command"
    argument_match:
      CommandLine: "(?i).*rm\\s+-r.*\\s+/(?!Users|tmp).*"
    action: "block"
    reason: "Destructive filesystem modification outside user directories is forbidden."

  - id: "flag_sudo_usage"
    target_tool: "run_command"
    argument_match:
      CommandLine: "(?i).*sudo\\s+.*"
    action: "flag"
    reason: "Requires explicit operator approval to run elevated commands."
    
  - id: "flag_mcp_install"
    target_tool: "install_mcp_server"
    argument_match: {} # All matches
    action: "flag"
    reason: "Installing external AI servers requires approval."
```

## Secuencia de Ejecución (Human-in-the-Loop)

1. El LLM decide llamar a `run_command` con `sudo apt update`.
2. `skills/executor.py` captura el `ToolCall`. Pasa los argumentos a `PolicyEngine.evaluate()`.
3. El `PolicyEngine` hace match con la regla `flag_sudo_usage`. Retorna acción `flag`.
4. El ejecutor frena el loop. Envía un mensaje especial vía `wa_client` al usuario: *"⚠️ **Alerta de Seguridad**\nEl agente intenta ejecutar: `sudo apt update`\nResponde 'Aprobar' o 'Rechazar'."*
5. El estado del agente se suspende (`AgentState.AWAITING_APPROVAL`).
6. El usuario responde. El webhook reanuda la sesión. Si aprobó, se llama la tool y se loggea en el Audit Trail. Si rechazó, se retorna al LLM: *"The user explicitly rejected this tool call: permission denied."*

## Decisiones de Diseño (2026 Best Practices)
- **Agentic Detection and Response (ADR):** Evaluamos las intenciones en *runtime* contra constraints determinísticos, no confiamos en "prompts de seguridad" vagos.
- **Rules as Code:** Las políticas son versionables en YAML, separadas de la lógica dura de Python.
- **Fail-Secure:** Ante una duda del parseador de políticas o error de regex, la política default para comandos bash riesgosos es detener y pedir autorización (HitL).
