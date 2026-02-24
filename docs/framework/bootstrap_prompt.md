# Prompt: Bootstrapper del Contrato Agente-Humano

> **Uso**: pegá este prompt en un agente AI (Claude, Gemini, GPT, Cursor, etc.) dentro de un repositorio donde quieras establecer el contrato de colaboración. El agente analizará el proyecto y generará los archivos fundacionales.

---

## El Prompt

```
Vas a analizar este repositorio y crear los archivos fundacionales para establecer un contrato de colaboración agente-humano. Este contrato define cómo deben trabajar juntos humanos y agentes AI en este codebase.

## Tu tarea

Analizá el repositorio actual (estructura, README existente, código, configs) y creá los siguientes archivos. Adaptá cada uno al proyecto real — no copies texto genérico.

### 1. CLAUDE.md (Convenciones Técnicas)

Creá `CLAUDE.md` en la raíz del proyecto con:

- **Stack**: lenguajes, frameworks, versiones exactas (extraer de package.json, pyproject.toml, Cargo.toml, etc.)
- **Estructura**: tree comentado del proyecto (hasta 2 niveles, con descripciones de qué hace cada carpeta)
- **Tests**: cómo correr tests, convenciones (async mode, fixtures, mocking patterns)
- **Calidad de código**: linter, formatter, type checker con los comandos exactos
- **Patrones**: listar los patrones arquitectónicos que ya existen en el código y que deben preservarse. Por cada patrón, incluir:
  - Qué es (1 línea)
  - Dónde está (archivo)
  - Por qué importa (1 línea)
- **Performance**: si hay un critical path, documentarlo (paralelismo, caching, etc.)

**Formato**: usar el proyecto real, no ejemplos genéricos. Si el proyecto usa React + TypeScript, documentar eso. Si usa FastAPI + SQLite, documentar eso.

### 2. AGENTS.md (Mapa del Proyecto)

Creá `AGENTS.md` en la raíz del proyecto con:

**Sección 1: Mapa de Documentación**
Tabla con "Qué buscás" → "Dónde está" para navegar el proyecto.

**Sección 2: Mapa de Código — Quién Posee Qué**
Tabla con dominio → archivos clave → qué leer antes de tocar.

**Sección 3: Workflow de Desarrollo y Validación**
```
Roles:
  - Humano (Arquitecto): define intención, aprueba merges, realiza el testing manual/funcional
  - Agente (Ejecutor): implementa, corre tests automatizados (unit/integration), documenta
  - Regla: el agente valida en teoría (tests), el humano en la práctica (ux). Si el agente se bloquea (ej: link inaccesible), debe avisar y no alucinar.

Ciclo por Feature:
  1. PLAN        → docs/exec-plans/<feature>.md
  2. IMPLEMENTAR → branch, tests automatizados obligatorios
  3. DOCUMENTAR  → docs/features/ + docs/testing/ + CLAUDE.md + AGENTS.md
  4. EVALUATE    → humano sigue docs/testing/; si descubre blockers o bugs, el ciclo itera y vuelve a (2)
  5. DELIVER     → commit, push, PR
```

**Sección 4: Protocolo de Documentación** (obligatorio al terminar una feature)
- El nombre de los archivos debe usar un prefijo numérico cronológico (ej. `01-auth.md`, `02-database.md`) para mantener el orden de implementación.
- Crear: walkthrough feature + guía de testing
- Actualizar: CLAUDE.md (patrones) + AGENTS.md (skills/módulos)
- Exec plans: ANTES de implementar features complejas (≥3 archivos)

**Sección 5: Estado Actual y Próximos Pasos**
Listar componentes existentes y sus estados.

**Sección 6: Principios del Proyecto**
Extraer de la filosofía del proyecto (3-7 principios, concretos, no genéricos).

### 3. docs/exec-plans/README.md

Creá el directorio `docs/exec-plans/` con un `README.md` que contenga:
- Descripción: "Documentos técnicos que bajan una intención de producto a cambios concretos"
- Tabla de planes disponibles (vacía inicialmente, con header)
- Convenciones: cuándo crear un plan, los nombres deben incluir prefijo cronológico (`01-feature.md`), qué incluir, estados (📋→🚧→✅)
- Template mínimo de exec plan

### 4. docs/features/README.md

Creá `docs/features/` con un `README.md` que:
- Liste features existentes (si hay docs previos, indexarlos)
- Tenga convenciones (un archivo por feature con prefijo cronológico e.g. `01-feature.md`, linkear a testing)
- Incluya una instrucción: "Copiar TEMPLATE.md como punto de partida"

### 5. docs/testing/README.md

Creá `docs/testing/` con un `README.md` que:
- Liste guías de testing existentes
- Indique el rol del archivo: "Estas guías son obligatorias y sirven como el protocolo de aceptación manual del humano."
- Tenga convenciones (un archivo por feature con el mismo prefijo cronológico `01-feature_testing.md`, incluir: happy path, edge cases preventivos, workarounds si hay blockers técnicos, verificación en logs/DB)

### 6. Templates

Creá `docs/features/TEMPLATE.md`:
```markdown
# [Nombre de la Feature]

## Qué hace
[1-2 párrafos]

## Cómo funciona
[Explicación técnica con diagrama si aplica]

## Archivos involucrados
| Archivo | Rol |
|---|---|

## Decisiones de diseño
| Decisión | Alternativa descartada | Razón |
|---|---|---|

## Gotchas / Edge cases
[Cosas que el próximo developer debe saber]

## Testing
📋 [Guía de testing](../testing/<nombre>_testing.md)
```

Creá `docs/testing/TEMPLATE.md`:
```markdown
# Testing: [Nombre de la Feature]

## Pre-requisitos
[Setup necesario]

## Test Cases

### TC-01: [nombre del caso]
**Acción**: [qué hacer]
**Esperado**: [qué debe pasar]

## Edge Cases
| Escenario | Esperado |
|---|---|

## Verificación en logs
[Comandos para verificar]

## Troubleshooting
| Síntoma | Causa | Solución |
|---|---|---|
```

## Reglas

1. **Analizá el código real** — no inventes patrones que no existen. Si el proyecto no tiene tests, no documentes "cómo correr tests", pero advertí la deuda.
2. **Sé específico** — usa nombres de archivos, funciones y módulos reales del proyecto.
3. **No sobrecargues** — cada archivo debe ser conciso y navegable. Si CLAUDE.md tiene más de 200 líneas, probablemente tiene demasiado para empezar.
4. **Priorizá lo destructivo y los límites** — documenta PRIMERO lo que un agente podría romper si no lo sabe, y los casos donde el agente **no puede operar** (ej. "el entorno no tiene acceso a internet exterior", "links detrás de Auth0 no se pueden scrapear").
5. **El README existente no se reemplaza** — si ya hay un README, mejoralo. No lo sobreescribas.
```

---

## Cómo usarlo

1. Abrí tu repo en un agente AI (Claude Code, Cursor, Gemini, etc.)
2. Pegá el prompt de arriba
3. El agente analizará tu proyecto y generará los archivos
4. Revisá y ajustá — el agente propone, vos decidís
5. Commiteá los archivos como "docs: establish agent-human contract"

## Después del bootstrap

Con los archivos fundacionales en su lugar, cada feature nueva sigue el ciclo iterativo:

```
PLAN → IMPLEMENT → DOCUMENT → EVALUATE (HUMAN) ↺ → DELIVER
```

El contrato crece orgánicamente resolviendo problemas reales: cada vez que el agente se bloquea (ej. no puede leer una URL) o asume algo erróneo, se documenta en `CLAUDE.md` o `docs/testing/` para que no vuelva a suceder.
