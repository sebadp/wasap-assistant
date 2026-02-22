# Testing Manual: CI/CD

> **Feature documentada**: [`docs/features/cicd.md`](../features/cicd.md)
> **Requisitos previos**: `make dev` ejecutado (instala pre-commit hooks).

---

## Casos de prueba principales

| Acción | Resultado esperado |
|---|---|
| `make lint` | Ruff pasa sin errores |
| `make typecheck` | mypy pasa sin errores |
| `make test` | Todos los tests pasan |
| `make check` | Lint + typecheck + tests pasan en secuencia |
| `git commit` con un error de lint | Pre-commit hook bloquea el commit |

---

## Edge cases y validaciones

| Escenario | Resultado esperado |
|---|---|
| Archivo con línea >120 chars | Ruff no falla (E501 ignorado) |
| `Depends()` como default parameter | Ruff no falla (B008 ignorado) |
| Import de `faster-whisper` sin stubs | mypy no falla (`ignore_missing_imports`) |
| Test async sin `@pytest.mark.asyncio` | Funciona (`asyncio_mode = "auto"`) |

---

## Verificar CI en GitHub

1. Pushear un branch con cambios
2. Ir a la pestaña Actions del repo
3. Verificar que los 3 jobs (lint, typecheck, test) corren en paralelo
4. Verificar que pasan

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| Pre-commit hooks no corren | No instalados | `make dev` o `pre-commit install` |
| mypy falla con "missing stubs" | Nuevo import sin stubs | Agregar a `ignore_missing_imports` |
| CI falla pero local pasa | Versión de Python o dependencia diferente | Verificar `ci.yml` matches local setup |
| AI reviewer da falsos positivos | Contexto insuficiente | Revisar y descartar comentarios irrelevantes |
