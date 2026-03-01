# Testing Protocol: Web Browsing & URL Fetching

> **Feature asociada**: `docs/features/22-web_browsing.md`
> **Tipo**: Manual (End-to-End en WhatsApp) + Unit Tests (`pytest`)

---

## 1. Prerrequisitos
- Contenedor de `wasap` activo junto con `ollama` y la red conectada.
- El servidor MCP de puppeteer debe estar disponible en `data/mcp_servers.json`. (O tener skills `fetch_*` locales en `skills/`).

## 2. Test Cases Manuales (WhatsApp)

### Test Case 1: URL simple y pública
- **Acción**: Enviar `Mira este link: https://example.com/` vía WhatsApp.
- **Aprobación esperada (Backend Logs)**: 
  - `classify_intent` fuerza la categoría `['fetch']`.
  - El LLM, mediante `executor.py`, lanza la tool correspondiente (ej. `fetch_html`).
- **Aprobación esperada (Respuesta Wa)**: El asistente responde con el contenido de la página (ej. "Example Domain...").

### Test Case 2: URL de Redes Sociales (LinkedIn / Instagram / Drive)
- **Acción**: Enviar `https://www.linkedin.com/posts/milanmilanovic_ia-development-activity` o `https://share.google/ab123`.
- **Aprobación esperada (Backend)**: Igual que el TC1, el intento de `fetch` DEBE dispararse. Si no funciona por falta de autenticación, el error viene de la ejecución (403/Captchas).
- **Aprobación esperada (Respuesta Wa)**: Ya no debe haber respuestas prematuras del tipo *"El enlace requiere autenticación, por ende no puedo entrar... ¿Qué puedo hacer por ti?"* SIN haberlo intentado antes en los logs. Informará que lo intentó pero fue bloqueado por el servidor externo.

### Test Case 3: URL combinada con múltiples intenciones
- **Acción**: Enviar `Busca en internet el nombre del fundador de Anthropic y compáralo con este artículo https://www.anthropic.com/engineering/infrastructure-noise`
- **Aprobación esperada**: `classify_intent` debería registrar ambos: `search` (por la instrucción buscar) y `fetch` (forizado por el Regex de URL).

---

## 3. Pruebas Unitarias
Ejecutar `pytest tests/test_tool_router.py`. Estas verifican que bajo ninguna circunstancia el clasificador LLM pierda una URL viva dentro de un mensaje.

- `test_classify_url_adds_fetch`
- `test_classify_url_overrides_none`
- `test_classify_url_appends_to_others`
