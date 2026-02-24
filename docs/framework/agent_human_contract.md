# Framework: Contrato Agente-Humano para Repositorios

> **Destilado de la experiencia real** construyendo [wasap-assistant](https://github.com/sebadp/wasap-assistant): 8 fases, 3 sprints agénticos, 30+ features implementadas con pair programming humano–AI.

---

## 1. El Contrato en una Frase

> El humano decide **qué** y **por qué**. El agente decide **cómo** y **ejecuta**. La documentación es el medio de transmisión entre ambos — y hacia el próximo agente.

---

## 2. Roles y Responsabilidades

| | Humano (Arquitecto) | Agente (Ejecutor) |
|---|---|---|
| **Define** | Intención, prioridades, alcance | Plan técnico detallado |
| **Revisa** | Exec plans, PRs, decisiones de diseño, **casos límite** | Código propio via tests automatizados |
| **Aprueba** | Planes, merges, operaciones destructivas | N/A |
| **Escribe** | Feature requests, feedback, **guías de testing manual** | Código, tests, documentación |
| **Testea** | **Funcionalidad real via `docs/testing/`, asumiendo el rol del usuario final** | **Tests unitarios y de integración automatizados** |
| **Escala** | Cuando el agente loopea o no entiende | Cuando necesita input del humano (HITL) o encuentra un blocker (ej. link inaccesible) |

**Regla de falla**: si el agente falla → no se fuerza el código. Se mejoran las restricciones, herramientas o contexto. Nunca se acepta código incorrecto por velocidad.

---

## 3. Los 7 Artefactos del Contrato

Estos son los documentos que constituyen el "contrato" entre humano y agente en un repositorio. Juntos, le dan a cualquier agente (o humano nuevo) el contexto completo para operar.

### 3.1 `README.md` — La Puerta de Entrada

**Audiencia**: humanos y agentes nuevos.
**Contiene**: qué hace el proyecto, cómo levantarlo, stack, arquitectura, flujos.
**Regla**: si un humano no puede levantar el proyecto en 5 minutos leyendo el README, está incompleto.

### 3.2 `CLAUDE.md` (o `CONVENTIONS.md`) — El Código de Conducta Técnico

**Audiencia**: agentes que van a modificar código.
**Contiene**:
- Stack y versiones exactas
- Estructura del proyecto (tree comentado)
- Patrones arquitectónicos que **deben preservarse** (con razón)
- Reglas de calidad (linter, formatter, type checker, comandos)
- Performance: critical path documentado, qué NO tocar
- Cada patrón nuevo que se establece se agrega aquí

**Regla**: este archivo crece con el proyecto. Cada decisión arquitectónica que el próximo agente necesita respetar va aquí.

### 3.3 `AGENTS.md` — El Mapa de Navegación

**Audiencia**: agentes que necesitan orientarse rápido.
**Contiene**:
- Mapa de documentación (dónde encontrar cada cosa)
- Mapa de código (quién "posee" cada módulo + qué leer antes de tocar)
- Workflow de desarrollo (ciclo humano ↔ agente)
- Protocolo de documentación (obligatorio al terminar)
- Estado actual del proyecto + próximos pasos
- Principios del proyecto (valores no negociables)

**Regla**: este archivo es el GPS. Un agente que lea solo este archivo debe saber a dónde ir para cualquier tarea.

### 3.4 `docs/exec-plans/` — Planes de Ejecución

**Audiencia**: humano (para revisar) y agente (para seguir).
**Contiene**: un archivo por feature compleja (≥3 archivos afectados). Las convenciones exigen un prefijo numérico cronológico (ej. `01-setup.md`, `02-auth.md`) para mantener el orden histórico.
**Cada plan incluye**: objetivo, archivos a modificar, schema de datos, orden de implementación, decisiones de diseño, riesgos.

**Regla**: se crea **antes** de implementar. Es un artefacto de primera clase: documenta **decisiones**, no solo pasos. El humano aprueba el plan antes de que el agente empiece a codear.

### 3.5 `docs/features/` — Walkthroughs de Features

**Audiencia**: el próximo agente/humano que necesite mantener o extender.
**Contiene**: retrospectivas técnicas de cada feature. Llevan el mismo prefijo numérico que su exec-plan correspondiente (ej. `02-auth.md`) para que el explorador de archivos cuente la historia del proyecto en orden. Cada archivo detalla qué hace, cómo funciona internamente, decisiones de diseño, gotchas, cómo extender.

**Regla**: una feature sin walkthrough no está terminada.

### 3.6 `docs/testing/` — Guías de Testing y Validación Humana

**Audiencia**: agentes (para entender los casos de uso) y humanos (para validar).
**Contiene**: test cases manuales, edge cases preventivos, verificación en logs/DB, troubleshooting. Llevan el mismo prefijo numérico (ej. `02-auth_testing.md`).

**Regla Core**: el testing automatizado es del agente, pero **el testing funcional es del humano**. El humano usa esta guía paso a paso para estresar la feature. Si un paso falla, no se lo parchea al vuelo: se vuelve al ciclo iterativo. Cada walkthrough de feature tiene su guía de testing correspondiente.

### 3.7 Archivos Bootstrap (opcionales) — `SOUL.md`, `TOOLS.md`

**Audiencia**: el agente autónomo.
**Contiene**: personalidad/style del agente, herramientas disponibles, restricciones adicionales.
**Regla**: se inyectan en el system prompt automáticamente si existen en la raíz del proyecto.

---

## 4. Workflow por Feature: El Ciclo

```
┌─────────────────────────────────────────────────────────────┐
│  1. PLAN      Humano describe intención                     │
│               Agente crea docs/exec-plans/<feature>.md      │
│               Humano revisa y aprueba el plan               │
│                                                             │
│  2. IMPLEMENT Agente codea en branch, corre tests aut.      │
│               Agente pide aprobación para destructivas      │
│                                                             │
│  3. DOCUMENT  Agente crea docs/features/<feature>.md        │
│               Agente crea docs/testing/<feature>_testing.md │
│               Agente actualiza CLAUDE.md si hay patrones    │
│               Agente actualiza AGENTS.md si hay módulos     │
│                                                             │
│  4. EVALUATE  Humano realiza test manual (docs/testing/)    │
│  (Iteración)  Si falla o hay bloqueo → feedback al agente   │
│               Agente itera código/docs y vuelve a (2)       │
│                                                             │
│  5. DELIVER   Agente commitea, pushea, crea PR              │
│               Humano revisa PR, mergea                      │
└─────────────────────────────────────────────────────────────┘
```

**La Importancia de la Fase 4 (Iteración)**: El código que pasa tests unitarios frecuentemente falla en la integración real (e.g. un agente que no puede acceder a un hipervínculo protegido). El ciclo natural asume la iteración: el humano valida el *happy path* y los *edge cases* documentados. Si descubre una limitación, pide al agente un workaround (ej. "el link da 403, probá parsear este JSON en cambio"). El ciclo se repite hasta que el test manual es exitoso.

**Regla de Oro**: una feature no está terminada si no tiene documentación y testing manual validado. Si no está en el repositorio, no existe para el próximo agente.

---

## 5. Principios del Contrato

1. **Documentación como transmisión**: el contexto se pasa entre agentes via archivos, no via memoria. Lo que no está escrito, se pierde.
2. **Restricciones mecánicas > voluntad**: linters, tests y patterns de código previenen la entropía mejor que instrucciones verbales.
3. **Exec plan antes de código**: para features complejas, el plan es el primer artefacto. El humano aprueba ANTES de que se escriba código.
4. **Validación asimétrica**: el agente es responsable de que funcione en la teoría (tests automatizados); el humano es responsable de que funcione en la práctica (test manual iterativo).
5. **Best-effort para lo no crítico**: logging, embeddings, trazas — nunca bloquean el pipeline principal. Fallan silenciosamente.
6. **Scope acotado**: cada skill/módulo tiene un dominio claro. No hay "módulo hace todo".
7. **Falla segura y explícita**: si el agente no puede (ej: link protegido, timeout) → pide ayuda (HITL). Nunca finge éxito ni fuerza código incorrecto.
8. **Incrementalismo**: sprints chicos, features con scope contenido, tests después de cada cambio, validación humana periódica.

---

## 6. Anti-Patterns (Lo que NO hacer)

| Anti-pattern | Por qué falla | Alternativa |
|---|---|---|
| Implementar sin plan | El agente divaga, el humano no puede revisar el approach | Exec plan → aprobación → código |
| Dejar docs para "después" | El próximo agente no tiene contexto | Docs son parte de la feature, no un extra |
| Asumir que los unit tests bastan | Rotura en integración o UX pobre | Humano ejecuta testing manual obligatoriamente |
| Ignorar blockers de acceso | El agente "alucina" contenido de una URL protegida o local | Framear restricciones explícitas; proveer workarounds (curl, mock) |
| Aceptar código sin tests | La deuda técnica se acumula exponencialmente | Test after every edit, never commit untested code |
| Un archivo god-object para todo | Imposible de navegar, alto riesgo de conflictos | Separar por dominio, documentar ownership en AGENTS.md |
| Solo verbal, sin archivos | Se pierde al cruzar sesiones/agentes | Todo en markdown en el repo |
| Forzar una solución que falla | Se stackean hacks sobre hacks | Si falla 3 veces → el humano reevalúa la viabilidad, vuelve al paso de Planning |

---

## 7. Checklist de Onboarding para un Repo Nuevo

Cuando aplicás este framework a un repositorio nuevo (o existente), creá/verificá estos archivos:

- [ ] `README.md` — quickstart funcional en ≤5 minutos
- [ ] `CLAUDE.md` (o `CONVENTIONS.md`) — stack, estructura, patrones, quality rules
- [ ] `AGENTS.md` — mapa del proyecto, workflow, protocolo de docs, principios
- [ ] `docs/exec-plans/README.md` — índice de planes + template
- [ ] `docs/features/README.md` — índice de walkthroughs + template
- [ ] `docs/testing/README.md` — índice de guías de testing + template
- [ ] `.github/workflows/ci.yml` (o equivalente) — lint, typecheck, test
- [ ] `Makefile` (o equivalente) — shortcuts: `make check`, `make test`, `make lint`

---

*Framework v1.0 — Febrero 2026*
*Destilado del proyecto wasap-assistant (sebadp/wasap-assistant)*
