# Feature: UX y Multimedia

> **Versión**: v1.0
> **Fecha de implementación**: 2025-12
> **Fase**: Fase 3
> **Estado**: ✅ Implementada

---

## ¿Qué hace?

El agente puede recibir y procesar audio (transcripción local con Whisper) e imágenes (análisis con LLaVA). Los mensajes se formatean correctamente para WhatsApp (negrita, listas, etc.), se respetan rate limits, y el logging es estructurado en JSON.

---

## Arquitectura

```
[Mensaje WhatsApp]
    │
    ├─ Texto ──────────────► directo al LLM
    │
    ├─ Audio (.ogg) ──────► [Transcriber (faster-whisper)]
    │                              │
    │                              ▼
    │                        texto transcrito → LLM
    │
    └─ Imagen ────────────► descarga via WA API
                                   │
                                   ▼
                           [OllamaClient.chat(model=llava:7b)]
                                   │
                                   ▼
                             descripción/análisis
```

---

## Archivos clave

| Archivo | Rol |
|---|---|
| `app/audio/transcriber.py` | `Transcriber` — wrapper de faster-whisper, transcripción local |
| `app/llm/client.py` | `OllamaClient` con soporte de imágenes (base64) para LLaVA |
| `app/webhook/parser.py` | Detecta tipo de mensaje (texto/audio/imagen) y extrae datos |
| `app/formatting/markdown_to_wa.py` | Convierte markdown a formato WhatsApp (bold, italic, code, lists) |
| `app/formatting/splitter.py` | Divide respuestas largas en chunks ≤4096 chars |
| `app/webhook/rate_limiter.py` | Rate limiter por número con ventana deslizante |
| `app/logging_config.py` | Logging JSON estructurado con `structlog` o `logging` |

---

## Walkthrough técnico

### Audio

1. WhatsApp envía el audio como referencia (media ID)
2. `parser.py` detecta `type="audio"` y extrae el `media_id`
3. `_handle_message` descarga el audio via WhatsApp API (`/media/{id}`)
4. `Transcriber.transcribe()` convierte a texto con faster-whisper (modelo configurable)
5. El texto transcrito se usa como input al LLM igual que un mensaje de texto

### Imágenes

1. `parser.py` detecta `type="image"` y extrae `media_id` + `caption`
2. Se descarga la imagen y se codifica en base64
3. Se envía al LLM con modelo de visión (llava:7b) para análisis
4. El LLM describe o responde sobre la imagen

### Formato WhatsApp

- `*bold*` → **bold**, `_italic_` → _italic_, \`code\` → code
- Listas con `-` se convierten a formato legible
- Links se preservan
- Headers `##` se convierten a `*HEADER*`

---

## Cómo extenderla

- **Cambiar modelo de transcripción**: `WHISPER_MODEL` en `.env` (default: `base`)
- **Cambiar modelo de visión**: `OLLAMA_VISION_MODEL` en `.env` (default: `llava:7b`)
- **Agregar soporte para video**: extender `parser.py` para detectar tipo `video`
- **Personalizar formato**: modificar `markdown_to_wa.py`

---

## Guía de testing

→ Ver [`docs/testing/05-ux_multimedia_testing.md`](../testing/05-ux_multimedia_testing.md)

---

## Decisiones de diseño

| Decisión | Alternativa descartada | Motivo |
|---|---|---|
| faster-whisper local | Whisper API (OpenAI) | Privacidad, sin costo, funciona offline |
| LLaVA para visión | GPT-4V, Claude Vision | Consistente con la stack Ollama local |
| Rate limiter por teléfono | Rate limiter global | Un usuario no debe afectar a otro |
| Logging JSON | Logging plain text | Parseable por herramientas de observabilidad |
| Split en 4096 chars | Truncado simple | WhatsApp tiene límite hard, mejor dividir que perder contenido |

---

## Gotchas y edge cases

- **Whisper necesita CPU/GPU**: el modelo corre en `app/audio/transcriber.py` con `faster-whisper`. En CPU es lento (~5s para 30s de audio).
- **La descarga de media** usa un token de la Graph API que puede expirar — verificar `WHATSAPP_ACCESS_TOKEN`.
- **Imágenes grandes** se redimensionan internamente por Ollama, pero la descarga puede ser lenta en servidores con poco bandwidth.
- **El formato de WhatsApp** no soporta markdown completo — tablas, por ejemplo, se renderizan como texto plano.

---

## Variables de configuración relevantes

| Variable (`config.py`) | Default | Efecto |
|---|---|---|
| `WHISPER_MODEL` | `base` | Modelo de transcripción (tiny/base/small/medium/large) |
| `WHISPER_DEVICE` | `cpu` | Dispositivo (cpu/cuda) |
| `WHISPER_COMPUTE_TYPE` | `int8` | Precisión (float16/int8) |
| `RATE_LIMIT_MAX` | `30` | Mensajes máximos por ventana |
| `RATE_LIMIT_WINDOW` | `60` | Ventana en segundos |
| `LOG_LEVEL` | `INFO` | Nivel de logging |
| `LOG_JSON` | `True` | Formato JSON en logs |
