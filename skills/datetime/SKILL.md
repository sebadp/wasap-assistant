---
name: datetime
description: Get current date/time and convert between timezones
version: 1
tools:
  - get_current_datetime
  - convert_timezone
---
When the user asks for the current time or date, use `get_current_datetime`.
Default to the user's timezone if known, otherwise use UTC.
For timezone conversions, use `convert_timezone`.
Use IANA timezone names (e.g. America/Argentina/Buenos_Aires, Europe/London, Asia/Tokyo).
