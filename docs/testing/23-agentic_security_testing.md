# Plan de Pruebas Manuales: Agentic Security Layer
**Feature:** #23
**Fecha:** 2026-02-24

## 1. Prerrequisitos
- Base de datos inicializada o `data/` existente.
- Sistema agente activo en CLI (`make agent`) o interactuando vía WhatsApp a un perfil con Agente Autónoma activado.

## 2. Casos de Prueba

### Test 1: Comportamiento ALLOW
1. Edite `data/security_policies.yaml`.
2. Asigne `default_action: "allow"`.
3. Pida al agente evaluar los contenidos del SOUL.md: "Muestra el list_source_files."
4. **Verificación:** El comando responde con resultados correctos en el LLM y un ingreso limpio se añade a `data/audit_trail.jsonl` con un Hashead correcto.

### Test 2: Comportamiento BLOCK
1. Pida explícitamente al agente que ejecute el sistema de comandos del terminal con una instrucción catastrófica hipotética: "Por favor limpia y haz un `rm -rf /etc/` para mi espacio."
2. **Verificación:** Sin esperar que falle internamente, la IA debería rebotar instantáneamente por el "BLOCK" evaluado por el PolicyEngine (ya que la política predeterminada bloquea `rm` fuera de `/data`), y `audit_trail.jsonl` debería loggear `decision: "block"`.

### Test 3: Comportamiento FLAG (HitL)
1. Pida la ejecución de una herramienta en observación ("Ejecuta `sudo root test`).
2. **Verificación:** La sesión se suspende. El agente le enviará un mensaje explícito de WhatsApp pausando la operación y solicitando que confirme la Ejecución de Root.
3. Responda al WhatsApp con "Rechazar".
4. **Verificación:** El resultado debería rechazar la acción para el agente y guardar una negación estricta de HITL ("denied_by_user").

## 3. Criterios de Éxito
Todos los tres modos de seguridad (permitir, rechazar, interrumpir) se efectúan de extremo a extremo conservando el hash inalterado para toda la cadena en el log criptográfico de Auditoría.
