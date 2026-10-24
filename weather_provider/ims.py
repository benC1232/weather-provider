"""Current temperature and humidity from an IMS weather station.

Uses the IMS observation API (api.ims.gov.il, "envista"). The station is
ims.station in the config (setup picks the nearest one that reports
temperature and humidity). The API key comes from the config or the
IMS_API_KEY environment variable and must never be logged. Terms
(see docs/COMPLIANCE.md): credit IMS, sanity-check every value, and have a
backup for when data is missing or late (Open-Meteo, chosen in __main__).
"""

import json
import math
import urllib.request
from datetime import datetime, timedelta, timezone

from .openmeteo import Reading

URL = "https://api.ims.gov.il/v1/envista/stations/{station}/data/latest"
STATIONS_URL = "https://api.ims.gov.il/v1/envista/stations"
# IMS times are Israel standard (winter) time all year, but the API labels
# them +03:00 in summer. Checked on 2026-10-03/04: sunlight at four stations
# peaked around 11:30 by the API's clock, when the real solar noon was ~12:28.
IMS_TIME = timezone(timedelta(hours=2))
USER_AGENT = "weather-provider (home LED sign)"



def _channel(channels: list, name: str) -> float:
    for ch in channels:
        if ch.get("name") == name:
            # IMS marks bad readings valid=false (and value -999).
            if not ch.get("valid") or ch.get("status") != 1:
                raise ValueError(f"{name} not valid")
            return float(ch["value"])
    raise ValueError(f"no {name} channel")


def observed_time(text: str, now: datetime | None = None) -> datetime:
    """The real (UTC) time of an IMS timestamp like "2026-10-05T21:30:00+03:00"."""
    labelled = datetime.fromisoformat(text)
    if labelled.tzinfo is None:
        raise ValueError("observation time has no time zone")
    actual = labelled.replace(tzinfo=IMS_TIME)
    # If IMS ever fixes its labels, reading them as UTC+2 would put new
    # readings in the future; trust the label then.
    now = now or datetime.now(timezone.utc)
    if actual > now + timedelta(minutes=5):
        actual = labelled
    return actual.astimezone(timezone.utc)


def parse(payload: dict, now: datetime | None = None) -> Reading:
    # IMS may change the format without notice (§9): anything odd raises.
    obs = payload["data"][-1]
    t = _channel(obs["channels"], "TD")
    rh = _channel(obs["channels"], "RH")
    if not -30 <= t <= 60:
        raise ValueError(f"implausible temperature {t}")
    if not 0 <= rh <= 100:
        raise ValueError(f"implausible humidity {rh}")
    return Reading(t, rh, observed_time(obs["datetime"], now), "IMS")


def fetch(key: str, station: int, timeout: float = 15) -> Reading:
    req = urllib.request.Request(URL.format(station=station), headers={
        "Authorization": f"ApiToken {key}",
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse(json.load(resp))


def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(a))


def nearest_station(stations: list, lat: float, lon: float):
    """(station dict, km) of the nearest active station with temperature and
    humidity, or None. `stations` is the IMS stations list."""
    best = None
    for st in stations:
        names = {m.get("name") for m in st.get("monitors", []) if m.get("active")}
        loc = st.get("location") or {}
        if not st.get("active") or not {"TD", "RH"} <= names:
            continue
        try:
            km = distance_km(lat, lon, float(loc["latitude"]), float(loc["longitude"]))
        except (KeyError, TypeError, ValueError):
            continue
        if best is None or km < best[1]:
            best = (st, km)
    return best


def stations(key: str, timeout: float = 30) -> list:
    req = urllib.request.Request(STATIONS_URL, headers={
        "Authorization": f"ApiToken {key}",
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)
