"""Current temperature, humidity and UV index, plus today's high and sunset, from Open-Meteo's free API.

Works anywhere, so it's the baseline every other source falls back to.

Terms (see docs/COMPLIANCE.md): non-commercial use only, under 10,000
calls/day, and credit under CC BY 4.0.
"""

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "weather-provider (home LED sign)"


@dataclass
class Reading:
    temperature_c: float
    humidity_pct: float
    observed_at: datetime  # UTC
    source: str  # label shown on the sign
    max_temp_c: float | None = None  # today's forecast high
    sunset: datetime | None = None  # today's sunset, local time
    uv_index: float | None = None  # now


def parse(payload: dict) -> Reading:
    cur = payload["current"]
    t = float(cur["temperature_2m"])
    rh = float(cur["relative_humidity_2m"])
    # Sanity check before trusting anything (IMS §4 asks the same of us).
    if not -30 <= t <= 60:
        raise ValueError(f"implausible temperature {t}")
    if not 0 <= rh <= 100:
        raise ValueError(f"implausible humidity {rh}")
    tz = ZoneInfo(payload.get("timezone", "UTC"))
    observed = datetime.fromisoformat(cur["time"]).replace(tzinfo=tz).astimezone(timezone.utc)

    # UV, today's high and sunset are extras: drop any that's missing or odd.
    uv = None
    try:
        uv = float(cur["uv_index"])
        if not 0 <= uv <= 20:
            uv = None
    except (KeyError, TypeError, ValueError):
        pass
    daily = payload.get("daily") or {}
    max_temp = sunset = None
    try:
        max_temp = float(daily["temperature_2m_max"][0])
        if not -30 <= max_temp <= 60:
            max_temp = None
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    try:
        sunset = datetime.fromisoformat(daily["sunset"][0]).replace(tzinfo=tz)
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return Reading(t, rh, observed, "OM", max_temp, sunset, uv)


def timezone_at(lat: float, lon: float, timeout: float = 15) -> str:
    """The IANA time zone name Open-Meteo picks for a place (used by setup)."""
    query = urllib.parse.urlencode({"latitude": lat, "longitude": lon, "timezone": "auto",
                                    "current": "temperature_2m", "forecast_days": 1})
    req = urllib.request.Request(f"{URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        name = json.load(resp)["timezone"]
    ZoneInfo(name)  # validates
    return name


def fetch(lat: float, lon: float, tz: str = "UTC", timeout: float = 15) -> Reading:
    query = urllib.parse.urlencode({
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,uv_index",
        "daily": "temperature_2m_max,sunset",
        "forecast_days": 1,
        "timezone": tz,  # so "today" and sunset are local
    })
    req = urllib.request.Request(f"{URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse(json.load(resp))
