---
name: datetime
description: Get current date/time and convert between timezones
version: 1
tools:
  - get_current_datetime
  - convert_timezone
---
When the user asks for the current time or date, use `get_current_datetime`.
Default to the user's timezone if known from their profile, otherwise use UTC.
For timezone conversions, use `convert_timezone`.

Use IANA timezone names:
- Argentina: America/Argentina/Buenos_Aires
- Spain: Europe/Madrid
- Mexico City: America/Mexico_City
- Colombia: America/Bogota
- USA East: America/New_York
- USA West: America/Los_Angeles
- UK: Europe/London
- Japan: Asia/Tokyo

How to respond:
- "qué hora es" → get_current_datetime with their timezone, reply naturally: "Son las 14:32 en Buenos Aires"
- "qué hora es en Tokio" → get_current_datetime(timezone="Asia/Tokyo")
- "si acá son las 3pm, qué hora es en Londres" → convert_timezone
- Include the date only if the user asks for it or if it's relevant (e.g. different day in the target timezone)
