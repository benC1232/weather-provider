"""Hourly UV index forecast for an IMS forecast city (ims.location in the config).

The table behind ims.gov.il's hourly UV page (every city, 07:00-20:00, today
and the next two days). Fetched once a day, and only while the summer panel
is shown; apart from the radar this is the only thing taken from the IMS
website (everything else comes from the IMS API or Open-Meteo). Without an
IMS city, Open-Meteo's UV index is shown instead.
"""

import json
import urllib.request
from datetime import datetime

URL = "https://ims.gov.il/he/uvi_hourly"
USER_AGENT = "weather-provider (home LED sign)"


def parse(payload: dict, location: str) -> dict:
    """{"YYYY-MM-DD": {hour: uv}} for one location; raises if it looks wrong."""
    days = payload["data"]["locations"][location]
    table = {}
    for day, hours in days.items():
        datetime.strptime(day, "%Y-%m-%d")  # validates
        table[day] = {}
        for hour, value in hours.items():
            hour, uv = int(hour), int(value)
            if not 0 <= hour <= 23 or not 0 <= uv <= 20:
                raise ValueError(f"implausible UV {value!r} at {day} {hour}")
            table[day][hour] = uv
    if not table:
        raise ValueError("no UV forecast")
    return table


def at(table: dict | None, when: datetime) -> int | None:
    """The UV index for `when` (local time), or None if the table doesn't
    cover that day. Hours the table leaves out (night) are 0."""
    if not table:
        return None
    hours = table.get(when.strftime("%Y-%m-%d"))
    if hours is None:
        return None
    return hours.get(when.hour, 0)


def fetch(location: str, timeout: float = 15) -> dict:
    req = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse(json.load(resp), str(location))


def location_ids(timeout: float = 15) -> set:
    """The forecast cities the UV table has (used by setup)."""
    req = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return set(json.load(resp)["data"]["locations"])
