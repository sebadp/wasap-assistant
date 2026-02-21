# Guía de Testing: Conversation Skill & Auto Debug

Esta guía describe cómo verificar que la tool `get_recent_messages` y el modo Auto Debug funcionen correctamente.

## Testing Manual

### 1. Verificar lectura básica
Envíale un par de mensajes sencillos al asistente ("Hola", "¿Cómo estás?").
Luego, pídele explícitamente:
> "¿Qué fue lo primero que te dije hoy?"

**Resultado esperado**: El asistente debe usar `get_recent_messages` y responder indicando que le dijiste "Hola".

### 2. Verificar límites y paginación
Abre el contenedor backend interactivo o modifixa el prompt para forzar una lectura muy grande:
> "Extrae mis últimos 100 mensajes"

**Resultado esperado**: La tool internamente limitará la búsqueda a un máximo de 50 mensajes (debido al clamp interno `min(limit, 50)`). El asistente procesará un máximo de 50 mensajes y podrá avisarte si hay historiales más antiguos.

### 3. Verificar modo Auto Debug
Desde otro entorno (o enviando un mensaje que sabes que causará un error manejado en el backend), activa el flag `debug_mode` del perfil de tu usuario.
Escribe un mensaje, por ejemplo:
> "Parece que hubo un error procesando mi factura. ¿Puedes revisar?"

**Resultado esperado**: Dado el inyectado "[🪲 DEBUG MODE ENABLED]", el LLM proactivamente debería llamar a `get_recent_messages` para ver la charla y a `get_recent_logs` para ver la excepción técnica, explicando finalmente la root cause de forma explícita.

### 4. Verificar edge cases (historial vacío)
Elimina tu conversación en la base de datos SQLite y envíale un primer mensaje pidiendo su historial:
> "¿Recuerdas de qué hablamos ayer?"

**Resultado esperado**: La tool debe devolver de forma controlada "The conversation history is empty" o "No messages found at offset X", y el asistente informará que no hay contexto anterior.
