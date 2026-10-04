"""Weather via Open-Meteo (free, no API key). All calls block: run them in a thread."""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.parse
import urllib.request

from .textsafe import clean_label

MAX_RESPONSE = 512 * 1024

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


class _HttpsOnly(urllib.request.HTTPRedirectHandler):
    """Refuse redirects that leave HTTPS (no downgrade to plain HTTP or other schemes)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not newurl.lower().startswith("https://"):
            raise urllib.error.URLError("blocked non-HTTPS redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_HttpsOnly)


def _get_json(url: str, timeout: float = 8.0) -> dict:
    if not url.lower().startswith("https://"):
        raise ValueError("HTTPS only")
    req = urllib.request.Request(url, headers=_UA)
    with _OPENER.open(req, timeout=timeout) as resp:
        raw = resp.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError("response too large")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("unexpected response")
    return data


def _num(v, lo: float, hi: float) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError("bad number")
    return float(v)


def geocode(city: str) -> dict | None:
    city = clean_label(city, 80)
    if not city:
        return None
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": city, "count": 1, "language": "en"})
    results = _get_json(url).get("results") or []
    if not results:
        return None
    r = results[0]
    return {"name": clean_label(r.get("name", city), 80) or city,
            "lat": _num(r["latitude"], -90, 90), "lon": _num(r["longitude"], -180, 180)}


def locate_by_ip() -> dict | None:
    data = _get_json("https://ipwho.is/")
    if not data.get("success", True) or "latitude" not in data:
        return None
    return {"name": clean_label(data.get("city") or "Here", 80) or "Here",
            "lat": _num(data["latitude"], -90, 90), "lon": _num(data["longitude"], -180, 180)}


def fetch(lat: float, lon: float, imperial: bool = False) -> dict:
    lat, lon = _num(lat, -90, 90), _num(lon, -180, 180)
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 4,
        "current": "temperature_2m,weather_code,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit" if imperial else "celsius",
    })
    data = _get_json(url)
    cur, daily = data["current"], data["daily"]
    times, codes = daily["time"], daily["weather_code"]
    highs, lows = daily["temperature_2m_max"], daily["temperature_2m_min"]
    if not (isinstance(times, list) and 1 <= len(times) <= 8 and len(codes) == len(highs) == len(lows) == len(times)):
        raise ValueError("bad forecast")
    days = []
    for i in range(len(times)):
        if not isinstance(times[i], str) or len(times[i]) != 10:
            raise ValueError("bad date")
        days.append({"date": times[i], "code": int(_num(codes[i], 0, 999)),
                     "hi": _num(highs[i], -200, 200), "lo": _num(lows[i], -200, 200)})
    return {"temp": _num(cur["temperature_2m"], -200, 200), "code": int(_num(cur["weather_code"], 0, 999)),
            "is_day": bool(cur.get("is_day", 1)), "days": days}
