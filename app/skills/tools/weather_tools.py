from __future__ import annotations

import logging
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from app.skills.registry import SkillRegistry

logger = logging.getLogger(__name__)

OPENMETEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
OPENMETEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
API_TIMEOUT = 10.0


async def _resolve_and_fetch(client: httpx.AsyncClient, url: str, params: dict) -> httpx.Response:
    """
    Manually resolves DNS to find a reachable IP (preferring IPv6 for this environment)
    and performs the request using the IP address + Host header.
    """
    parsed = urlparse(url)
    hostname = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    # Get all addresses (IPv4 and IPv6)
    try:
        # 0, 0 means any family (AF_UNSPEC), any socktype (SOCK_STREAM)
        addrs = socket.getaddrinfo(hostname, port, 0, socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise httpx.ConnectError(f"DNS resolution failed for {hostname}: {e}") from e

    # Sort addresses: Try IPv6 first (AF_INET6 = 10)
    # This is a heuristic for this specific IPv6-only environment
    addrs.sort(key=lambda x: x[0] == socket.AF_INET6, reverse=True)

    last_exc = None
    for family, _, _, _, sockaddr in addrs:
        ip = sockaddr[0]
        try:
            # Construct new URL with IP
            new_netloc = f"[{ip}]:{port}" if family == socket.AF_INET6 else f"{ip}:{port}"
            new_url = parsed._replace(netloc=new_netloc).geturl()

            # Host header is critical for SNI/Virtual Hosts
            headers = {"Host": hostname}

            logger.info(f"Trying IP {ip} for {hostname}...")
            resp = await client.get(new_url, params=params, headers=headers)  # type: ignore[arg-type]
            return resp
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
            logger.warning(f"Failed to connect to {ip}: {e}")
            last_exc = e
            continue

    raise last_exc or httpx.ConnectError(f"All addresses failed for {hostname}")


def register(registry: SkillRegistry) -> None:
    async def get_weather(city: str) -> str:
        """
        Get current weather and 3-day forecast for a city using OpenMeteo (IPv6 supported).
        Returns real data only — do NOT add or invent any information not present in the result.
        """
        try:
            async with httpx.AsyncClient(timeout=API_TIMEOUT, verify=False) as client:
                # Step 1: Geocoding (City -> Lat/Lon)
                # Try full name first; if not found, retry with just the city (before any comma)
                async def _geocode(name_query: str) -> dict:
                    logger.info(f"Geocoding city: {name_query}")
                    geo_params = {
                        "name": name_query,
                        "count": 1,
                        "language": "en",
                        "format": "json",
                    }
                    geo_resp = await _resolve_and_fetch(client, OPENMETEO_GEOCODING_URL, geo_params)
                    geo_resp.raise_for_status()
                    result = geo_resp.json()
                    logger.info(f"Geocoding response: {result}")
                    return result

                geo_data = await _geocode(city)

                if not geo_data.get("results") and "," in city:
                    # Retry with just the city name (strip province/country suffix)
                    city_only = city.split(",")[0].strip()
                    logger.info(f"No results for full name, retrying with: {city_only!r}")
                    geo_data = await _geocode(city_only)

                if not geo_data.get("results"):
                    return (
                        f"Could not find location: '{city}'. "
                        "Try using just the city name without province or country."
                    )

                location = geo_data["results"][0]
                lat = location["latitude"]
                lon = location["longitude"]
                loc_name = location["name"]
                country = location.get("country", "")
                logger.info(f"Found location: {loc_name}, {country} ({lat}, {lon})")

                # Step 2: Weather Forecast — 7 days so LLM can answer about any day this week
                logger.info(f"Fetching forecast for {lat}, {lon}")
                forecast_params = {
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                    "daily": (
                        "weather_code,"
                        "temperature_2m_max,temperature_2m_min,"
                        "precipitation_probability_max,precipitation_sum,"
                        "wind_speed_10m_max,"
                        "uv_index_max"
                    ),
                    "timezone": "auto",
                    "forecast_days": 7,
                }

                weather_resp = await _resolve_and_fetch(
                    client, OPENMETEO_FORECAST_URL, forecast_params
                )

                weather_resp.raise_for_status()
                weather_data = weather_resp.json()
                logger.info("Forecast received successfully")

                return _format_weather_response(loc_name, country, weather_data)

        except httpx.HTTPStatusError as e:
            return f"Weather service error: HTTP {e.response.status_code}"
        except httpx.HTTPError as e:
            return f"Weather service unavailable: {e}"
        except Exception as e:
            logger.exception("Weather fetch failed")
            return f"Error fetching weather: {e}"

    registry.register_tool(
        name="get_weather",
        description=(
            "Get current weather and 3-day forecast for a city. "
            "IMPORTANT: Only report what this tool returns. If it returns an error, "
            "tell the user the location was not found — do NOT invent or estimate weather data."
        ),
        parameters={
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "Full city name including province/region if applicable (e.g. 'El Soberbio, Misiones', 'Buenos Aires, Argentina'). BE SPECIFIC to avoid ambiguity.",
                },
            },
            "required": ["city"],
        },
        handler=get_weather,
        skill_name="weather",
    )


def _format_weather_response(name: str, country: str, data: dict[str, Any]) -> str:
    try:
        current = data.get("current", {})
        daily = data.get("daily", {})
        units = data.get("current_units", {})

        temp_unit = units.get("temperature_2m", "°C")
        wind_unit = units.get("wind_speed_10m", "km/h")

        # Current conditions
        temp = current.get("temperature_2m", "?")
        humidity = current.get("relative_humidity_2m", "?")
        wind = current.get("wind_speed_10m", "?")
        code = current.get("weather_code", 0)
        desc = _get_wmo_description(code)

        lines = [
            f"Weather in {name}, {country}:",
            f"  Now: {desc}, {temp}{temp_unit} | Humidity: {humidity}% | Wind: {wind} {wind_unit}",
        ]

        # 7-day daily forecast
        dates = daily.get("time", [])
        if dates:
            lines.append(f"  {len(dates)}-Day Forecast:")
            for i, date in enumerate(dates):

                def _get(key: str, default: Any = "?", _i: int = i) -> Any:
                    vals = daily.get(key, [])
                    return vals[_i] if _i < len(vals) else default

                max_t = _get("temperature_2m_max")
                min_t = _get("temperature_2m_min")
                d_code = _get("weather_code", 0)
                d_desc = _get_wmo_description(int(d_code) if d_code != "?" else 0)
                precip_prob = _get("precipitation_probability_max", 0)
                precip_mm = _get("precipitation_sum", 0)
                wind_max = _get("wind_speed_10m_max", "?")
                uv = _get("uv_index_max", "?")

                if i == 0:
                    label = f"Today    ({date})"
                elif i == 1:
                    label = f"Tomorrow ({date})"
                else:
                    label = f"         ({date})"

                # Build compact info string
                parts = [f"{d_desc}, {min_t}-{max_t}{temp_unit}"]
                if precip_prob and precip_prob != "?" and int(precip_prob) > 0:
                    mm_str = (
                        f" {precip_mm}mm"
                        if precip_mm and precip_mm != "?" and float(precip_mm) > 0
                        else ""
                    )
                    parts.append(f"rain:{precip_prob}%{mm_str}")
                if wind_max and wind_max != "?":
                    parts.append(f"wind:{wind_max}{wind_unit}")
                if uv and uv != "?" and float(uv) >= 6:
                    parts.append(f"UV:{uv}")

                lines.append(f"    {label}: {' | '.join(parts)}")

        return "\n".join(lines)
    except Exception as e:
        logger.error(f"Error formatting weather data: {e}")
        return "Error formatting weather data."


def _get_wmo_description(code: int) -> str:
    # WMO Weather interpretation codes (WW)
    # https://open-meteo.com/en/docs
    if code == 0:
        return "Clear sky"
    elif code in (1, 2, 3):
        return "Partly cloudy"
    elif code in (45, 48):
        return "Foggy"
    elif code in (51, 53, 55):
        return "Drizzle"
    elif code in (56, 57):
        return "Freezing drizzle"
    elif code in (61, 63, 65):
        return "Rain"
    elif code in (66, 67):
        return "Freezing rain"
    elif code in (71, 73, 75):
        return "Snowfall"
    elif code == 77:
        return "Snow grains"
    elif code in (80, 81, 82):
        return "Rain showers"
    elif code in (85, 86):
        return "Snow showers"
    elif code in (95, 96, 99):
        return "Thunderstorm"
    else:
        return "Unknown"
