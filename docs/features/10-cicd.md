# Feature: CI/CD

> **Versión**: v1.0
> **Fecha de implementación**: 2026-01
> **Fase**: Fase 7
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

Pipeline automatizado de calidad: pre-commit hooks verifican lint, types, y tests antes de cada commit. GitHub Actions ejecuta 3 jobs en paralelo (lint → typecheck → test) en cada push y PR. Un AI code reviewer analiza PRs con feedback automático.

---

## Arquitectura

```
[git commit]
    │
    ▼
[Pre-commit hooks]
    ├─ ruff (lint + format)
    ├─ mypy (type checking)
    └─ pytest (tests)
    │
    ▼
[git push]
    │
    ▼
[GitHub Actions CI]
    ├─ Job 1: ruff lint + format check
    ├─ Job 2: mypy type check
    └─ Job 3: pytest
    │
    ▼ (en PRs)
[AI Code Reviewer]
    └─ Analiza diff, postea comentarios en el PR
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `Makefile` | Targets: `test`, `lint`, `format`, `typecheck`, `check`, `dev` |
| `.pre-commit-config.yaml` | Configuración de pre-commit hooks |
| `.github/workflows/ci.yml` | GitHub Actions: lint, typecheck, test en paralelo |
| `pyproject.toml` | Config de ruff, mypy, pytest |

---

## Walkthrough técnico

### Pre-commit hooks

1. `make dev` instala hooks: `pip install pre-commit && pre-commit install`
2. En cada `git commit`, se ejecutan en orden: ruff → mypy → pytest
3. Si falla cualquiera, el commit se bloquea

### GitHub Actions

1. Trigger: push a cualquier branch o PR
2. 3 jobs en paralelo:
   - **Lint**: `ruff check . && ruff format --check .`
   - **Type check**: `mypy app/`
   - **Test**: `pytest tests/ -v`
3. Todos deben pasar para merge

### AI Code Reviewer

1. Se activa en PRs
2. Analiza el diff y genera comentarios con análisis de calidad
3. Puede aprobar o bloquear el PR según la severidad

### Configuración relevante

- **ruff ignores**: `E501` (líneas largas), `B008` (FastAPI `Depends()` como default)
- **mypy**: `ignore_missing_imports = true` (faster-whisper, sqlite-vec, mcp, watchdog no tienen stubs)
- **pytest**: `asyncio_mode = "auto"` — no hace falta `@pytest.mark.asyncio`

---

## Cómo extenderla

- **Agregar un linter**: añadir al `Makefile` y a `.pre-commit-config.yaml`
- **Cambiar reglas de ruff**: modificar `[tool.ruff]` en `pyproject.toml`
- **Agregar un job de CI**: editar `.github/workflows/ci.yml`
- **Desactivar AI reviewer**: eliminar el workflow correspondiente

---

## Guía de testing

→ Ver [`docs/testing/10-cicd_testing.md`](../testing/10-cicd_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| Ruff (lint + format) | Flake8 + Black + isort | Una sola herramienta, 10-100x más rápido |
| Pre-commit hooks | Solo CI | Feedback inmediato sin esperar push |
| Jobs paralelos en CI | Job secuencial | Reducción de ~50% en tiempo de CI |
| AI reviewer | Solo human review | Captura issues que humanos pueden pasar por alto |
| mypy lenient | mypy strict | Muchas dependencias sin stubs — strict sería inmanejable |

---

## Gotchas y edge cases

- **`make check`** ejecuta lint + typecheck + tests en secuencia — usar esto antes de pushear.
- **Pre-commit hooks** solo corren en files staged — si editas un archivo pero no lo stageas, no se valida.
- **mypy en `tests/`** está deshabilitado porque los tests usan mock patterns que son difíciles de tipear.

---

## Variables de configuración relevantes

| Archivo | Sección | Efecto |
|---|---|---|
| `pyproject.toml` | `[tool.ruff]` | Reglas de lint y formato |
| `pyproject.toml` | `[tool.mypy]` | Configuración de type checking |
| `pyproject.toml` | `[tool.pytest.ini_options]` | Configuración de tests |
| `.github/workflows/ci.yml` | Jobs | Qué corre en CI |
