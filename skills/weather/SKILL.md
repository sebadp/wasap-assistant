---
name: weather
description: Get current weather and forecast for any city
version: 1
tools:
  - get_weather
---
Cuando el usuario pregunte por el clima, usá la tool `get_weather` con la ciudad.
Si no dice ciudad, preguntale cuál.
Respondé en el idioma del usuario.

Si `get_weather` devuelve un error o dice que el servicio no está disponible, **DEBES** usar la tool `web_search` para buscar el clima actual y pronóstico.
Por ejemplo: `web_search("clima en [ciudad]")`.

**IMPORTANTE**: Si usas `web_search`, **DEBES EXTRAER** la temperatura actual, probabilidad de lluvia y estado del cielo (soleado, nublado, etc.) de los resultados de búsqueda y dárselos al usuario. **NO** te limites a listar los enlaces o decir "aquí tienes información". El usuario quiere saber si llueve o hace frío, no leer descripciones de webs.
