# Testing Manual: [Nombre de la Feature]

> **Feature documentada**: [`docs/features/<nombre>.md`](../features/<nombre>.md)
> **Requisitos previos**: Container corriendo (`docker compose up -d`), modelos de Ollama disponibles.

---

## Verificar que la feature está activa

Al arrancar el container, buscar en los logs:

```bash
docker compose logs -f wasap | head -60
```

Confirmar las siguientes líneas:
- `[línea de log que confirma que el componente se inicializó correctamente]`

---

## Casos de prueba principales

| Mensaje / Acción | Resultado esperado |
|---|---|
| `[mensaje de ejemplo]` | [qué debe responder o hacer] |
| `[mensaje de ejemplo 2]` | [resultado esperado] |

---

## Edge cases y validaciones

| Escenario | Resultado esperado |
|---|---|
| [input inválido o límite] | [error esperado o comportamiento de fallback] |
| [caso borde] | [comportamiento esperado] |

---

## Verificar en logs

```bash
# Actividad general de esta feature
docker compose logs -f wasap 2>&1 | grep -i "<keyword>"

# Errores
docker compose logs -f wasap 2>&1 | grep -i "error"
```

---

## Queries de verificación en DB (si aplica)

```bash
# [Descripción de qué verificar]
sqlite3 data/wasap.db "SELECT ... FROM ... WHERE ...;"

# [Otra verificación]
sqlite3 data/wasap.db "SELECT COUNT(*) FROM ...;"
```

---

## Verificar graceful degradation

[Cómo probar que el sistema funciona correctamente cuando falla este componente.]

1. [Paso para simular el fallo]
2. Verificar que el sistema continúa funcionando
3. [Cómo restaurar]

---

## Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| [síntoma] | [causa] | [solución] |
| [síntoma 2] | [causa] | [solución] |

---

## Variables relevantes para testing

| Variable (`.env`) | Valor de test | Efecto |
|---|---|---|
| `...` | `true/false` | [qué activa/desactiva] |
