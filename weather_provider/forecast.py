"""Today's forecast high for an IMS forecast city (ims.location in the config).

The city forecast behind ims.gov.il's city pages, written by IMS's
forecasters. Fetched once a day, and only while the summer panel is shown;
Open-Meteo's high is the fallback.
"""

import json
import urllib.request

URL = "https://ims.gov.il/he/full_forecast_data/{location}"
LOCATIONS_URL = "https://ims.gov.il/en/locations_info"
USER_AGENT = "weather-provider (home LED sign)"


def parse(payload: dict) -> dict:
    """{"YYYY-MM-DD": forecast high in °C} for each day in the forecast."""
    highs = {}
    for day, values in payload["data"].items():
        try:
            t = float(values["daily"]["maximum_temperature"])
        except (KeyError, TypeError, ValueError):
            continue  # a day without a usable high; the others may be fine
        if -30 <= t <= 60:
            highs[day] = t
    if not highs:
        raise ValueError("no forecast highs")
    return highs


def parse_locations(payload: dict) -> list:
    """[(id, English name, lat, lon)] of IMS's forecast cities."""
    out = []
    for loc in payload["data"].values():
        try:
            out.append((str(loc["lid"]), loc["name"], float(loc["lat"]), float(loc["lon"])))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def locations(timeout: float = 15) -> list:
    req = urllib.request.Request(LOCATIONS_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse_locations(json.load(resp))


def fetch(location: str, timeout: float = 15) -> dict:
    req = urllib.request.Request(URL.format(location=location), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse(json.load(resp))
