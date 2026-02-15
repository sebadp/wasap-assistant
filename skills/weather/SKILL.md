---
name: weather
description: Get current weather and forecast for any city
version: 1
tools:
  - get_weather
---
When the user asks about the weather, use `get_weather` with the city name.
You can pass `lang` to get the weather description in the user's language (e.g. "es" for Spanish).
If the user doesn't specify a city, ask them which city they want.
