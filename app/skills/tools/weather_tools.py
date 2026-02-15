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
        raise httpx.ConnectError(f"DNS resolution failed for {hostname}: {e}")

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
            resp = await client.get(new_url, params=params, headers=headers)
            return resp
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as e:
            logger.warning(f"Failed to connect to {ip}: {e}")
            last_exc = e
            continue
    
    raise last_exc or httpx.ConnectError(f"All addresses failed for {hostname}")


def register(registry: SkillRegistry) -> None:
    async def get_weather(city: str) -> str:
        """
        Get current weather and forecast for a city using OpenMeteo (IPv6 supported).
        """
        try:
            # Verify SSL is strict but we trust OpenMeteo
            async with httpx.AsyncClient(timeout=API_TIMEOUT, verify=True) as client:
                # Step 1: Geocoding (City -> Lat/Lon)
                logger.info(f"Geocoding city: {city}")
                geo_params = {"name": city, "count": 1, "language": "en", "format": "json"}
                
                # Use custom resolver
                geo_resp = await _resolve_and_fetch(client, OPENMETEO_GEOCODING_URL, geo_params)
                
                geo_resp.raise_for_status()
                geo_data = geo_resp.json()
                logger.info(f"Geocoding response: {geo_data}")

                if not geo_data.get("results"):
                    return f"Could not find location: {city}"

                location = geo_data["results"][0]
                lat = location["latitude"]
                lon = location["longitude"]
                name = location["name"]
                country = location.get("country", "")
                logger.info(f"Found location: {name}, {country} ({lat}, {lon})")

                # Step 2: Weather Forecast
                logger.info(f"Fetching forecast for {lat}, {lon}")
                forecast_params = {
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                    "timezone": "auto",
                    "forecast_days": 1,
                }
                
                # Use custom resolver
                weather_resp = await _resolve_and_fetch(client, OPENMETEO_FORECAST_URL, forecast_params)
                
                weather_resp.raise_for_status()
                weather_data = weather_resp.json()
                logger.info("Forecast received successfully")

                return _format_weather_response(name, country, weather_data)

        except httpx.HTTPStatusError as e:
            return f"Weather service error: HTTP {e.response.status_code}"
        except httpx.HTTPError as e:
            return f"Weather service unavailable: {e}"
        except Exception as e:
            logger.exception("Weather fetch failed")
            return f"Error fetching weather: {e}"

    registry.register_tool(
        name="get_weather",
        description="Get current weather and forecast for a city",
        parameters={
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name (e.g. 'Buenos Aires', 'London')",
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

        # Current weather
        temp = current.get("temperature_2m", "?")
        humidity = current.get("relative_humidity_2m", "?")
        wind = current.get("wind_speed_10m", "?")
        code = current.get("weather_code", 0)
        desc = _get_wmo_description(code)

        temp_unit = units.get("temperature_2m", "°C")
        wind_unit = units.get("wind_speed_10m", "km/h")

        lines = [
            f"Weather in {name}, {country}:",
            f"  {desc}, {temp}{temp_unit}",
            f"  Humidity: {humidity}%",
            f"  Wind: {wind} {wind_unit}",
        ]

        # Daily forecast
        if daily.get("time"):
            max_temp = daily["temperature_2m_max"][0]
            min_temp = daily["temperature_2m_min"][0]
            precip = daily.get("precipitation_probability_max", [0])[0]

            lines.append(f"  Today: {min_temp}{temp_unit} - {max_temp}{temp_unit}")
            if precip > 0:
                lines.append(f"  Precipitation chance: {precip}%")

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
    elif code in (61, 63, 65):
        return "Rain"
    elif code in (80, 81, 82):
        return "Rain showers"
    elif code in (95, 96, 99):
        return "Thunderstorm"
    else:
        return "Overcast/Rain"
