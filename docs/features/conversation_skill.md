# Feature: Conversation Skill & Auto Debug

> **Versión**: v1.0
> **Fecha de implementación**: 2026-02-21
> **Fase**: Fase 1
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

Permite al asistente acceder al historial de la conversación actual para entender el contexto pasado. Además, cuando el modo "Auto Debug" está activado, el asistente tiene instrucciones para usar de forma proactiva este historial (junto con los logs del sistema) para investigar y explicar errores técnicos al usuario.

---

## Arquitectura

El asistente utiliza la tool `get_recent_messages` para consultar directamente la base de datos a través de la capa de repositorios. No requiere de servicios externos, simplemente acceso de solo lectura al historial de chat del usuario actual.

```
[Usuario/Asistente en Auto Debug]
        │ (Llama a get_recent_messages)
        ▼
[Skill: conversation] ──► [Repository Layer]
        │                        │
        │                        ▼
        │                 [Base de Datos]
        ▼                        
[Historial de mensajes]
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `skills/conversation/SKILL.md` | Definición de la skill y las instrucciones para el LLM sobre cuándo usarla. |
| `app/skills/tools/conversation_tools.py` | Implementación de la tool `get_recent_messages` conectada al `Repository`. |
| `app/profiles/prompt_builder.py` | Inyecta las instrucciones de Auto Debug en el system prompt si el modo está activado. |
| `app/skills/router.py` | Registra la tool dentro de la categoría `conversation` para el enrutamiento. |

---

## Walkthrough técnico: cómo funciona

1. **Invocación**: El LLM decide usar `get_recent_messages`, ya sea porque el usuario preguntó por algo del pasado o porque está en Auto Debug investigando un problema.
2. **Contexto del usuario**: La tool obtiene el número de teléfono del usuario actual usando la variable de contexto `_current_user_phone`. → `app/skills/tools/conversation_tools.py:26`
3. **Consulta de solo lectura**: Se obtiene el ID de la conversación a través de `repository.get_conversation_id(phone)` sin crear una nueva si no existe (evitando efectos secundarios). → `app/skills/tools/conversation_tools.py:31`
4. **Paginación**: Se obtienen los mensajes paginados usando `limit` y `offset`. Se consulta un mensaje adicional (`limit + 1`) para determinar si hay más mensajes antiguos disponibles. → `app/skills/tools/conversation_tools.py:36`
5. **Formateo**: Los mensajes se formatean de forma compacta (truncando mensajes muy largos y mostrando la fecha/hora) y se devuelven al LLM en orden cronológico inverso para esa página. → `app/skills/tools/conversation_tools.py:48`
6. **Auto Debug**: Si `debug_mode` es `True` en el perfil del usuario, `build_system_prompt` agrega una instrucción explícita "🪲 DEBUG MODE ENABLED" que motiva al LLM a usar esta tool y `get_recent_logs` para diagnosticar root causes. → `app/profiles/prompt_builder.py:26`

---

## Cómo extenderla

- Para agregar nuevos parámetros de búsqueda (ej. filtrar por fecha): Modificar `get_recent_messages` en `app/skills/tools/conversation_tools.py` y el método correspondiente en `app/database/repository.py`.
- Para cambiar los límites de paginación: Ajustar el clamp `min(limit, 50)` en `conversation_tools.py:23`.

---

## Guía de testing

→ Ver [`docs/testing/conversation_skill_testing.md`](../testing/conversation_skill_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| Usar un read-only fetcher en el Repository | Reusar `get_or_create_conversation` | Reutilizar `get_or_create_conversation` causaba un efecto secundario (actualizar el timestamp `updated_at` o crear conversaciones vacías) para una operación de solo lectura, rompiendo el encapsulamiento. |
| Limitar la respuesta a 50 mensajes y truncar texto | Permitir extraer la conversación completa entera | Extraer toda la conversación podría exceder la ventana de contexto del LLM y causar errores de token limit (unbounded queries). |
| Implementarlo como Skill modular | Agregarlo directamente como System Prompt estático | Mantenerlo como skill permite cargar o descargar la funcionalidad según la categoría del router y mantener el código base ordenado. |

---

## Gotchas y edge cases

- **Historial vacío**: Si el usuario no tiene historial, la tool devuelve de manera proactiva "The conversation history is empty" sin arrojar errores.
- **Paginación inversa**: El parámetro `offset` permite saltar hacia atrás en el pasado, y el resultado avisa explícitamente al LLM "There are older messages. Use offset=X to see more", facilitando la lectura recursiva.
- **Truncado de mensajes largos**: Para evitar saturar el contexto, cada mensaje devuelto se trunca a 500 caracteres, y los saltos de línea se reemplazan por espacios.
