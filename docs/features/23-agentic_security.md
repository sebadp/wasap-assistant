# Observability: Agentic Security Layer
**Fecha:** 2026-02-24
**Módulos Afectados:** `app/security`, `app/skills/executor.py`, `app/agent/loop.py`
**Fase:** 5

## 1. Responsabilidad
Este módulo establece un motor determinista de seguridad para el agente autónomo ("Agentic Engine Validation"), operando como una capa de Defensa en Profundidad que audita e intercepta la ejecución de herramientas sensibles usando políticas configurables.

## 2. Flujo Principal
Cuando el LLM (dentro de `execute_tool_loop`) decide usar una herramienta:
1. Pasa la solicitud al `executor.py` (`_run_tool_call`).
2. El `PolicyEngine` localiza la herramienta e intenta emparejar los `argument_match` de la política YAML con la carga.
3. El `PolicyAction` define el resultado:
    - **ALLOW**: Se ejecuta la herramienta y se registra mediante `audit.record`.
    - **BLOCK**: El agente recibe un error inmediato, sin ejecutar nada, y se registra mediante `audit.record`.
    - **FLAG**: Se aborta la ejecución temporalmente. El agente lanza un mecanismo Human-In-The-Loop usando el `wa_client` para solicitar permiso expreso de un operador de seguridad vía mensaje. Si se autoriza, se reanuda la acción; caso contrario, se rechaza y bloquea.

## 3. Estado & Persistencia
* **Reglas**: Cargadas desde `data/security_policies.yaml`. Altera de forma declarativa sin refactorizar lógica.
* **Audit Trail**: Append-only log criptográfico conservado en `data/audit_trail.jsonl`. Cada registro procesa un Hash Secuencial SHA-256 (`entry_hash`), referenciando con `previous_hash` a la línea anterior en el log, probando la inmutabilidad retrospectiva para compliance de seguridad.

## 4. Interfaces Claves
### PolicyEngine
Responsable de leer las reglas, soportar expresiones regulares simples sobre los argumentos invocados de las herramientas, y mapear hacia 1 de 3 verbos: `allow`, `flag`, o `block`. El fallback por defecto es el "Default Action" especificado en el yaml.

### AuditTrail
Provee inmutabilidad criptográfica continua para las decisiones de seguridad, permitiendo post-mortems auditables y probando qué comandos exactos la IA se intentó ejecutar en el host.
