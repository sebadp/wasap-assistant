from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.skills.models import ToolCall
from app.skills.registry import SkillRegistry
from app.skills.tools.weather_tools import register, OPENMETEO_GEOCODING_URL, OPENMETEO_FORECAST_URL


def _make_registry():
    reg = SkillRegistry(skills_dir="/nonexistent")
    register(reg)
    return reg


SAMPLE_GEO_RESPONSE = {
    "results": [
        {
            "id": 123,
            "name": "Buenos Aires",
            "latitude": -34.61,
            "longitude": -58.38,
            "country": "Argentina",
        }
    ]
}

SAMPLE_FORECAST_RESPONSE = {
    "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
    "current": {
        "temperature_2m": 22.5,
        "relative_humidity_2m": 60,
        "wind_speed_10m": 15.0,
        "weather_code": 1,  # Partly cloudy
    },
    "daily": {
        "time": ["2024-01-01"],
        "temperature_2m_max": [28.0],
        "temperature_2m_min": [18.0],
        "precipitation_probability_max": [0],
    },
}


async def test_get_weather_success():
    reg = _make_registry()

    # Mock responses
    mock_geo_resp = MagicMock()
    mock_geo_resp.raise_for_status = MagicMock()
    mock_geo_resp.json.return_value = SAMPLE_GEO_RESPONSE

    mock_weather_resp = MagicMock()
    mock_weather_resp.raise_for_status = MagicMock()
    mock_weather_resp.json.return_value = SAMPLE_FORECAST_RESPONSE

    # Patch the _resolve_and_fetch helper function
    with patch("app.skills.tools.weather_tools._resolve_and_fetch", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.side_effect = [mock_geo_resp, mock_weather_resp]
        
        result = await reg.execute_tool(ToolCall(name="get_weather", arguments={"city": "Buenos Aires"}))

    assert result.success
    assert "Buenos Aires" in result.content
    assert "22.5°C" in result.content
    assert "Partly cloudy" in result.content
    assert "18.0°C - 28.0°C" in result.content
    
    assert mock_resolve.call_count == 2


async def test_get_weather_city_not_found():
    reg = _make_registry()

    mock_geo_resp = MagicMock()
    mock_geo_resp.raise_for_status = MagicMock()
    mock_geo_resp.json.return_value = {"results": []}  # Empty results

    with patch("app.skills.tools.weather_tools._resolve_and_fetch", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = mock_geo_resp

        result = await reg.execute_tool(ToolCall(name="get_weather", arguments={"city": "NonexistentCity"}))

    assert result.success
    assert "Could not find location" in result.content


async def test_get_weather_http_error():
    reg = _make_registry()

    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=mock_resp
    )

    with patch("app.skills.tools.weather_tools._resolve_and_fetch", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.side_effect = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_resp)

        result = await reg.execute_tool(ToolCall(name="get_weather", arguments={"city": "ErrorCity"}))

    assert result.success
    assert "Weather service error" in result.content or "HTTP 404" in result.content
