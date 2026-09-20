"""Weather via Open-Meteo (free, no API key). All calls block: run them in a thread."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

_UA = {"User-Agent": "ThemeStudio/1.0"}

# WMO weather code -> (description, emoji day, emoji night)
_CODES = {
    0: ("Clear", "\u2600\ufe0f", "\U0001F319"), 1: ("Mostly clear", "\U0001F324\ufe0f", "\U0001F319"),
    2: ("Partly cloudy", "\u26C5", "\u2601\ufe0f"), 3: ("Overcast", "\u2601\ufe0f", "\u2601\ufe0f"),
    45: ("Fog", "\U0001F32B\ufe0f", "\U0001F32B\ufe0f"), 48: ("Fog", "\U0001F32B\ufe0f", "\U0001F32B\ufe0f"),
    51: ("Drizzle", "\U0001F326\ufe0f", "\U0001F327\ufe0f"), 53: ("Drizzle", "\U0001F326\ufe0f", "\U0001F327\ufe0f"),
    55: ("Drizzle", "\U0001F327\ufe0f", "\U0001F327\ufe0f"), 61: ("Rain", "\U0001F327\ufe0f", "\U0001F327\ufe0f"),
    63: ("Rain", "\U0001F327\ufe0f", "\U0001F327\ufe0f"), 65: ("Heavy rain", "\U0001F327\ufe0f", "\U0001F327\ufe0f"),
    71: ("Snow", "\u2744\ufe0f", "\u2744\ufe0f"), 73: ("Snow", "\u2744\ufe0f", "\u2744\ufe0f"),
    75: ("Heavy snow", "\u2744\ufe0f", "\u2744\ufe0f"), 80: ("Showers", "\U0001F326\ufe0f", "\U0001F327\ufe0f"),
    81: ("Showers", "\U0001F327\ufe0f", "\U0001F327\ufe0f"), 82: ("Heavy showers", "\U0001F327\ufe0f", "\U0001F327\ufe0f"),
    95: ("Thunderstorm", "\u26C8\ufe0f", "\u26C8\ufe0f"), 96: ("Thunderstorm", "\u26C8\ufe0f", "\u26C8\ufe0f"),
    99: ("Thunderstorm", "\u26C8\ufe0f", "\u26C8\ufe0f"),
}


def describe(code: int, is_day: bool = True) -> tuple[str, str]:
    label, day, night = _CODES.get(code, ("Unknown", "\u2601\ufe0f", "\u2601\ufe0f"))
    return label, (day if is_day else night)


def _get_json(url: str, timeout: float = 8.0) -> dict:
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def geocode(city: str) -> dict | None:
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": city, "count": 1, "language": "en"})
    results = _get_json(url).get("results") or []
    if not results:
        return None
    r = results[0]
    return {"name": r.get("name", city), "lat": r["latitude"], "lon": r["longitude"]}


def locate_by_ip() -> dict | None:
    data = _get_json("https://ipwho.is/")
    if not data.get("success", True) or "latitude" not in data:
        return None
    return {"name": data.get("city") or "Here", "lat": data["latitude"], "lon": data["longitude"]}


def fetch(lat: float, lon: float, imperial: bool = False) -> dict:
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 4,
        "current": "temperature_2m,weather_code,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit" if imperial else "celsius",
    })
    data = _get_json(url)
    cur, daily = data["current"], data["daily"]
    days = [{"date": daily["time"][i], "code": daily["weather_code"][i],
             "hi": daily["temperature_2m_max"][i], "lo": daily["temperature_2m_min"][i]}
            for i in range(len(daily["time"]))]
    return {"temp": cur["temperature_2m"], "code": cur["weather_code"],
            "is_day": bool(cur.get("is_day", 1)), "days": days}
