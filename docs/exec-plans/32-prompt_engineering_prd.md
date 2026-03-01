# PRD: Prompt Engineering & Versioning

## 1. Objetivo y Contexto

WasAP tiene **28 prompts** distribuidos en 14 archivos. Solo 1 (el system prompt principal) es
versionable via DB — los otros 27 son constantes hardcodeadas en Python sin posibilidad de
iteración, A/B testing, rollback o evolución automática.

Además, varios prompts tienen problemas técnicos concretos:
- Guardrail LLM checks y summarizer no usan `think=False` → latencia innecesaria y riesgo de JSON parse failure
- El classifier no tiene few-shot examples → accuracy baja en mensajes ambiguos
- El compaction prompt pide "add a note that full result is available" → genera filler text
- Onboarding prompts en inglés para un sistema multilingüe

**Investigación de mercado (Feb 2026):**
- "Context engineering" reemplazó a "prompt engineering" como mental model (Anthropic sept 2025)
- Prompts deben ser artefactos versionados de primera clase (Braintrust, Langfuse, PromptHub)
- Evaluación acoplada a versiones: cada cambio de prompt debe correr eval suite antes de activarse
- DSPy/PromptWizard demuestran que optimización automática es viable con pocos ejemplos
- Multi-turn degradation de ~39% es real y se mitiga con re-inyección periódica de facts

**Objetivo:** Convertir todos los prompts críticos en artefactos versionables, corregir los
bugs técnicos, y establecer un pipeline de evaluación acoplada al versionado.

## 2. Alcance

### In Scope
- **Fase 1 — Quick Fixes:** Corregir `think=False` faltante, few-shot en classifier, limpiar compaction prompt
- **Fase 2 — Prompt Registry:** Extender `prompt_manager.py` para soportar N prompts nombrados con seeding automático de defaults
- **Fase 3 — Eval-Coupled Versioning:** Acoplar eval suite a `activate_prompt_version()` — no activar sin validar
- **Fase 4 — Prompt Catalog & Commands:** Comando `/prompts` para listar, ver, comparar versiones

### Out of Scope
- Optimización automática via DSPy/PromptWizard (requiere dataset más grande, fase futura)
- A/B testing con traffic splitting (requiere infraestructura de routing, fase futura)
- UI/dashboard para edición de prompts (Langfuse ya provee esto parcialmente)
- Cambios al `ContextBuilder` o context engineering (ya implementado en exec plan 31)
- System prompt reminder injection para conversaciones largas (mejora separada)
- Hacer onboarding prompts bilingües (cambio UX, evaluar separadamente)

## 3. Casos de Uso Críticos

### CU1: Fix de latencia en guardrails
Usuario envía mensaje. Guardrails LLM checks corren `check_tool_coherence` y `check_hallucination`.
Actualmente qwen3 genera chain-of-thought antes de responder "yes"/"no", agregando ~2s de latencia
por check. Con `think=False`, la respuesta es inmediata.

### CU2: Classifier con few-shot
Usuario escribe "cuánto es 15% de 230". El classifier sin examples podría clasificar como `"none"`
(texto que parece pregunta simple). Con few-shot examples, clasifica correctamente como `"math"`.

### CU3: Evolución de summarizer prompt
El equipo nota que los summaries pierden detalles técnicos. Usa `propose_prompt_change("summarizer", "loses technical details", "emphasize code references and error messages")`. El LLM genera una versión mejorada. Se corre eval → si pasa, se activa con `/approve-prompt summarizer 2`.

### CU4: Rollback de prompt
Se activa una nueva versión del classifier prompt que causa regresiones. El equipo detecta caída
en accuracy via eval. Ejecuta `/approve-prompt classifier 1` → rollback inmediato al prompt anterior.

### CU5: Diagnóstico de prompts
Desarrollador ejecuta `/prompts` → ve lista de todos los prompts registrados con su versión activa.
Ejecuta `/prompts classifier` → ve contenido actual, historial de versiones, y scores del eval.

## 4. Restricciones Arquitectónicas

- **Backward compatible:** Si no hay versión en DB para un prompt, se usa el default hardcodeado
- **Zero-overhead si deshabilitado:** El registry no debe agregar latencia si `prompt_versioning_enabled=False`
- **Same DB:** Usa la tabla `prompt_versions` existente (ya soporta N prompt_names)
- **Fail-open:** Error en prompt_manager → usar default hardcodeado, nunca crashear
- **No PyYAML:** Mantener la restricción existente de no agregar PyYAML como dependencia
- **`think=False` para todo prompt binario/JSON:** Convención explícita, no depender del default del modelo
- **Eval coupling es advisory, no blocking:** El eval corre, reporta, pero el humano decide si activar

## 5. Prompts a Registrar (Prioridad)

| Prompt Name | Archivo Actual | Prioridad | Justificación |
|---|---|---|---|
| `system_prompt` | `config.py` | Ya existe | — |
| `classifier` | `router.py` | Alta | Afecta tool selection → toda la UX |
| `summarizer` | `summarizer.py` | Alta | Afecta calidad de memoria a largo plazo |
| `flush_to_memory` | `summarizer.py` | Alta | Afecta extracción de facts |
| `consolidator` | `consolidator.py` | Media | Menos frecuente, pero afecta memoria |
| `compaction` | `compaction.py` | Media | Solo se activa con outputs grandes |
| `tool_coherence` | `checks.py` | Baja | Gated por flag, uso infrecuente |
| `hallucination_check` | `checks.py` | Baja | Gated por flag, uso infrecuente |
| `planner_create` | `planner.py` | Media | Crítico para agentes |
| `planner_replan` | `planner.py` | Media | Crítico para agentes |
| `planner_synthesize` | `planner.py` | Baja | Menos crítico |
| `eval_judge` | `eval_tools.py` | Baja | Auto-evaluación |

## 6. Métricas de Éxito

- `think=False` en todos los prompts binarios/JSON → medible via latencia de guardrails y summarizer
- Todos los prompts de prioridad Alta registrados en DB con v1 seeded del default
- `propose_prompt_change()` funciona para cualquier prompt registrado (no solo `system_prompt`)
- `/prompts` command operativo
- Eval suite corre automáticamente al proponer `activate_prompt_version()`
- Tests unitarios para cada cambio
