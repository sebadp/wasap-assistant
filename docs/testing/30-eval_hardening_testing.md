# Testing: Eval Stack Hardening (Plan 30)

## Archivos de test

- `tests/test_guardrails.py` — 10 tests de guardrails y remediation
- `tests/test_eval_tools.py` — 5 tests de LLM-as-judge en `run_quick_eval`

## Tests unitarios clave

### Guardrail checks

| Test | Qué verifica |
|------|-------------|
| `test_check_not_empty_passes` | Texto no vacío pasa |
| `test_check_not_empty_fails_on_blank` | Solo espacios falla |
| `test_language_match_skip_short_text` | < 30 chars siempre pasa (langdetect unreliable) |
| `test_language_match_skip_short_reply` | Reply < 30 chars siempre pasa |
| `test_language_match_details_contains_user_lang_on_failure` | `details` = ISO code del usuario (ej. "es") |

### Language match remediation (Phase 1)

| Test | Qué verifica |
|------|-------------|
| `test_language_remediation_prompt_is_bilingual` | Hint contiene "español" Y "IMPORTANT" (ambos idiomas) |
| `test_language_remediation_unknown_lang_uses_bilingual_generic` | Lang code desconocido → fallback genérico bilingüe, sin enviar el code raw |
| `test_language_remediation_creates_span_when_trace_ctx_provided` | `trace_ctx.span("guardrails:remediation", kind="generation")` llamado + `set_metadata({check, lang_code})` |
| `test_language_remediation_no_span_without_trace_ctx` | Sin `trace_ctx` no hay error, LLM call directa |

### Timeout configurable (Phase 2)

| Test | Qué verifica |
|------|-------------|
| `test_guardrails_llm_timeout_from_settings` | `_run_async_check` recibe el timeout de `settings.guardrails_llm_timeout` |

### run_quick_eval LLM-as-judge (Phase 3)

| Test | Qué verifica |
|------|-------------|
| `test_run_quick_eval_uses_llm_judge_yes` | "yes" → passed=True → "✅" + "1/1" en output |
| `test_run_quick_eval_uses_llm_judge_no` | "no" → passed=False → "❌" + "0/1" en output |
| `test_run_quick_eval_judge_uses_think_false` | Segunda llamada a `ollama_client.chat` tiene `think=False` |
| `test_run_quick_eval_skips_entries_without_expected_output` | Entradas sin `expected_output` se saltan, `chat` no es llamado |
| `test_run_quick_eval_no_entries_returns_helpful_message` | Dataset vacío → mensaje con "add_to_dataset()" |

## Smoke tests manuales

### 1. Language match remediation

Enviar un mensaje largo en español. Si el LLM responde en inglés (raro, pero posible):
- En Langfuse: buscar el trace → verificar span `guardrails` con `failed_checks: ["language_match"]`
- Verificar span hijo `guardrails:remediation` con `lang_code: "es"`
- Verificar que la respuesta final del bot está en español

### 2. LLM judges con timeout real

Setear en `.env`:
```
GUARDRAILS_LLM_CHECKS=true
GUARDRAILS_LLM_TIMEOUT=3.0
```
Enviar un mensaje y verificar que los checks `tool_coherence` / `hallucination_check`
aparecen como scores en Langfuse (si el timeout fuera 0.5s, siempre darían timeout y no aparecerían como scored).

### 3. Tags en dataset

Forzar un guardrail failure (ej. mensaje < 30 chars en inglés → reply en español).
Luego verificar:
```sql
SELECT tag, count(*) FROM eval_dataset_tags GROUP BY tag;
-- Debe mostrar: guardrail:language_match | 1
```

### 4. Benchmark offline

```bash
python scripts/run_eval.py --db data/wasap.db --ollama http://localhost:11434 --limit 5
```

Verificar:
- Imprime tabla con columns: entry_id | type | passed | input (preview)
- Imprime summary: `X/Y correct (Z%)`
- Exit code 0 si accuracy >= 70%, 1 si below

## Regresiones a verificar

- Tests de webhook no rompidos por cambios en `router.py`: `test_webhook_commands.py`, `test_webhook_incoming.py`
- Tests de ollama_client no rompidos por nuevo param `think` en `chat()`: `test_ollama_client.py`
- Suite completa: 485 passed (excluyendo los 2 archivos que requieren langfuse instalado)
