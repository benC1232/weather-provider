"""First-run setup: `python -m weather_provider setup`.

Asks where you are and where the sign is, then works out the rest: the time
zone (from Open-Meteo), whether you're inside the IMS radar's coverage, the
nearest IMS station and forecast city, where to put home on the radar scope,
and the coastline around it (OpenStreetMap, via Overpass). Writes it all to
config.toml, plus coast.json beside it, and sets [setup] complete = true.

Starting weather_provider runs this by itself while complete is false. With
no terminal to ask on (Docker, systemd) it takes every answer from the config
file as it stands, so fill in at least the location first (README). Run it
again any time: it starts from what's already there. `--coast-only` just
re-downloads the coastline.
"""

import argparse
import os
import sys
from pathlib import Path

from . import coast, config, forecast, ims, openmeteo, radar, uvi

# Where home goes on the 88x32 radar panel so the scope sees furthest toward
# the direction rain usually comes from. NW is the original hand-tuned layout.
HOME_FOR_DIRECTION = {
    "N": (48, 25), "NE": (20, 19), "E": (14, 16), "SE": (20, 12),
    "S": (48, 7), "SW": (75, 12), "W": (80, 16), "NW": (75, 19),
    "ALL": (48, 16),
}
EDGE_PX = 60.6  # the outer ring's radius in pixels: 1.65 km/px for 100 km, as in the NW layout
STATION_MAX_KM = 30  # further than this, Open-Meteo is likely closer to the truth
CITY_MAX_KM = 40


def scope_layout(direction: str, radius_km: float):
    """(home_x, home_y, km_per_px, rings_km) for a look direction and scope radius."""
    home_x, home_y = HOME_FOR_DIRECTION[direction.upper()]
    rings = [round(radius_km / 3), round(2 * radius_km / 3), round(radius_km)]
    return home_x, home_y, round(radius_km / EDGE_PX, 3), rings


def nearest_city(cities, lat, lon, allowed=None):
    """(id, name, km) of the nearest IMS forecast city, or None."""
    best = None
    for lid, name, clat, clon in cities:
        if allowed is not None and lid not in allowed:
            continue
        km = ims.distance_km(lat, lon, clat, clon)
        if best is None or km < best[2]:
            best = (lid, name, km)
    return best


class Prompter:
    """Asks questions on the terminal, or takes every default with --defaults."""

    def __init__(self, defaults_only: bool):
        self.defaults_only = defaults_only

    def ask(self, question, default=None, parse=str, secret=False):
        while True:
            if self.defaults_only:
                if default is None:
                    raise SystemExit(f"setup: no value for {question!r}; set it in the config file "
                                     "or run setup from a terminal")
                try:
                    return parse(str(default))  # the config file's value, checked like an answer
                except ValueError as e:
                    raise SystemExit(f"setup: {question}: {e}")
            shown = "" if default in (None, "") else f" [{'****' if secret else default}]"
            answer = input(f"{question}{shown}: ").strip()
            if not answer:
                if default is not None:
                    return default
                continue
            try:
                return parse(answer)
            except ValueError as e:
                print(f"  {e}")

    def yes(self, question, default=True):
        answer = self.ask(question + " (y/n)", "y" if default else "n",
                          lambda a: a.lower()[:1] if a.lower()[:1] in "yn" else _bad("y or n"))
        return answer == "y"


def _bad(what):
    raise ValueError(f"please enter {what}")


def _latitude(text):
    v = float(text)
    return v if -90 <= v <= 90 else _bad("a latitude between -90 and 90")


def _longitude(text):
    v = float(text)
    return v if -180 <= v <= 180 else _bad("a longitude between -180 and 180")


def _direction(text):
    return text.upper() if text.upper() in HOME_FOR_DIRECTION else _bad(" ".join(HOME_FOR_DIRECTION))


def _season(text):
    radar.parse_season(text)
    return text


def _legacy_key():
    """The IMS key from older versions' ~/.config/weather-provider.env, if any."""
    try:
        with open(os.path.expanduser("~/.config/weather-provider.env")) as f:
            for line in f:
                name, _, value = line.partition("=")
                if name.strip() == "IMS_API_KEY":
                    return value.strip().strip("'\"")
    except FileNotFoundError:
        pass
    return ""


def make_coast(cfg, out=print):
    """Downloads and saves the coastline for cfg's radar scope."""
    s = scope_for(cfg)
    box = coast.bbox(s, radar.WIDTH, radar.HEIGHT)
    out(f"Downloading the coastline around home from OpenStreetMap (bbox {box}); this can take a minute...")
    lines = coast.download(box)
    coast.save(cfg.coastline_path(), lines, box)
    out(f"  {len(lines)} coastline pieces saved to {cfg.coastline_path()}"
        + ("" if lines else " (none here: no coast in view)"))


def scope_for(cfg):
    r = cfg.radar
    return radar.Scope(cfg.location.latitude, cfg.location.longitude,
                       r.home_x, r.home_y, r.km_per_px, tuple(r.rings_km),
                       coast.load(cfg.coastline_path()))


def run(argv=None):
    p = argparse.ArgumentParser(prog="weather_provider setup",
                                description="Write the config file (asks questions).")
    p.add_argument("--config", type=Path, default=config.default_path())
    p.add_argument("--lat", type=_latitude)
    p.add_argument("--lon", type=_longitude)
    p.add_argument("--direction", type=_direction, help="where rain usually comes from: N, NE, ... NW, ALL")
    p.add_argument("--defaults", action="store_true",
                   help="don't ask; take every answer from the config file (needs the location)")
    p.add_argument("--coast-only", action="store_true", help="just re-download the coastline")
    args = p.parse_args(argv)

    cfg = config.load(args.config) or config.Config(path=args.config)
    cfg.path = args.config
    if args.coast_only:
        if cfg.location.latitude is None:
            p.error(f"no location in {args.config}; run setup first")
        make_coast(cfg)
        return

    lat = cfg.location.latitude if args.lat is None else args.lat
    lon = cfg.location.longitude if args.lon is None else args.lon
    if args.defaults and (lat is None or lon is None):
        raise SystemExit(f"setup: set latitude and longitude under [location] in {args.config} "
                         "(remove the # in front), then start again")
    ask = Prompter(args.defaults)
    print(f"weather-provider setup: writing {args.config}\n")

    # Where.
    loc = cfg.location
    loc.latitude = args.lat if args.lat is not None else ask.ask("Latitude (e.g. 31.5)", loc.latitude, _latitude)
    loc.longitude = args.lon if args.lon is not None else ask.ask("Longitude (e.g. 34.9)", loc.longitude, _longitude)
    try:
        tz = openmeteo.timezone_at(loc.latitude, loc.longitude)
    except Exception as e:
        print(f"  (couldn't look up the time zone: {e})")
        tz = loc.timezone
    loc.timezone = ask.ask("Time zone", tz)

    # The sign.
    cfg.sign.server = ask.ask("sign-server frame URL", cfg.sign.server)

    # IMS: only useful in and around Israel.
    in_israel = radar.covers(loc.latitude, loc.longitude)
    if not in_israel:
        print("\nOutside the IMS (Israel) coverage: using Open-Meteo for everything, no rain radar.")
        cfg.ims = config.IMS()
        cfg.radar.enabled = False
    else:
        print("\nInside the Israel Meteorological Service's coverage.")
        key = ask.ask("IMS API key, for station readings (Enter to skip; ims.gov.il/en/ObservationDataAPI)",
                      os.environ.get("IMS_API_KEY") or cfg.ims.api_key or _legacy_key(), secret=True)
        cfg.ims.api_key, cfg.ims.station = key, None
        if key:
            try:
                found = ims.nearest_station(ims.stations(key), loc.latitude, loc.longitude)
            except Exception as e:
                found = None
                print(f"  couldn't list IMS stations ({e}); check the key. Open-Meteo will be used.")
            if found and found[1] <= STATION_MAX_KM:
                st, km = found
                print(f"  nearest station with temperature and humidity: {st['name']} ({km:.0f} km)")
                if ask.yes("  Use it?"):
                    cfg.ims.station = int(st["stationId"])
            elif found:
                print(f"  nearest station is {found[1]:.0f} km away; using Open-Meteo instead")

        cfg.ims.location = None
        try:
            city = nearest_city(forecast.locations(), loc.latitude, loc.longitude, uvi.location_ids())
        except Exception as e:
            city = None
            print(f"  couldn't list IMS forecast cities ({e}); Open-Meteo will be used for UV and highs.")
        if city and city[2] <= CITY_MAX_KM:
            print(f"  nearest IMS forecast city, for the UV index and today's high: {city[1]} ({city[2]:.0f} km)")
            if ask.yes("  Use it?"):
                cfg.ims.location = int(city[0])

        cfg.radar.enabled = ask.yes("Show the IMS rain radar in the rain season?", True)

    # Radar scope.
    if cfg.radar.enabled:
        cfg.radar.season = ask.ask("Rain season (MM-DD:MM-DD; the summer panel shows otherwise)",
                                   cfg.radar.season, _season)
        print("The scope sees furthest in one direction; pick where most of your rain comes from.")
        r = cfg.radar
        r.direction = args.direction or ask.ask("Direction (N NE E SE S SW W NW, or ALL for centered)",
                                                r.direction.upper(), _direction)
        r.range_km = ask.ask("Radar range in km (the outer ring)", r.range_km, float)
        r.home_x, r.home_y, r.km_per_px, r.rings_km = scope_layout(r.direction, r.range_km)
        try:
            make_coast(cfg)
        except Exception as e:
            print(f"  coastline download failed ({e}); it will be tried again on every start until it works")

    cfg.setup.complete = True
    config.save(cfg, args.config)
    print(f"\nSaved {args.config} (readable only by you).")
    print("Data sources and their terms: README.md and docs/COMPLIANCE.md.")


def main(argv=None):
    try:
        run(argv)
    except (KeyboardInterrupt, EOFError):
        print("\nsetup cancelled; nothing saved", file=sys.stderr)
        sys.exit(1)
