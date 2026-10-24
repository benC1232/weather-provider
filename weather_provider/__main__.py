"""Fetches the weather and rain radar and posts them to sign-server.

Settings come from config.toml (config.py), written by
`python -m weather_provider setup`. Setup also runs by itself while the
config's [setup] complete is false: asking questions on a terminal, or
taking the config's own values without one (Docker, systemd). With no config
file at all it needs a terminal. Command-line options override the file.

Two regions: the weather panel on the right (--x, --y) and the radar scope on
the left (0, 0), which also carries the data source credits. Fetches the
weather every --fetch-minutes and the radar every --radar-minutes, and
re-posts every --post-seconds so the panels come back quickly if the server
restarts. Temperature and humidity come from the configured IMS station when
there is one and its newest reading is no older than --ims-stale-minutes;
otherwise Open-Meteo's is shown (labelled OM). Open-Meteo is fetched every
time anyway, for today's high, sunset and the UV fallback. Old data is never
shown as current: the weather shows dashes after --stale-minutes without an
Open-Meteo reading either, and the radar drops its rain (rings go gray) once
its newest frame is older than --radar-stale-minutes. The radar animates: the
4 previous frames once each, then the current one 4 times, so the loop pauses
on "now". Outside the rain season (radar.season, Oct 1 to May 30 by default),
or all year without the radar, no radar is fetched and the left panel shows
heat stress and the UV index instead. With an IMS forecast city, the UV index
and today's high are IMS's forecasts, each fetched once a day while the
summer panel is shown; otherwise (or if they fail) Open-Meteo's.
"""

import argparse
import logging
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, forecast, ims, onboard, openmeteo, radar, summer, uvi
from .render import HEIGHT, WIDTH, render, to_rgb565

log = logging.getLogger("weather_provider")


# Radar animation: this many previous frames once each, then the current one
# HOLD_FRAMES times (a pause on "now"). The server sets how long each shows.
PREVIOUS_FRAMES = 4
HOLD_FRAMES = 4


def post(server_url: str, x: int, y: int, w: int, h: int, body: bytes, frames: int = 1):
    url = f"{server_url}?x={x}&y={y}&w={w}&h={h}"
    if frames > 1:
        url += f"&frames={frames}"
    req = urllib.request.Request(
        url, data=body, method="POST", headers={"Content-Type": "application/octet-stream"}
    )
    with urllib.request.urlopen(req, timeout=10):
        pass


def log_reading(r):
    log.info("%s: %.1f°C %d%% (as of %s UTC)", r.source, r.temperature_c, r.humidity_pct,
             r.observed_at.strftime("%H:%M"))


def parse_args(argv=None):
    """Options; each one left out (None) keeps the config file's value."""
    p = argparse.ArgumentParser(prog="weather_provider", epilog="First time? Run: python -m weather_provider setup")
    p.add_argument("--config", type=Path, default=None, help=f"config file (default {config.default_path()})")
    p.add_argument("--lat", type=float)
    p.add_argument("--lon", type=float)
    p.add_argument("--timezone", help="IANA time zone, e.g. Asia/Jerusalem")
    p.add_argument("--server", help="sign-server's frame URL")
    p.add_argument("--x", type=int, help="left edge of the weather panel on the sign")
    p.add_argument("--y", type=int)
    p.add_argument("--fetch-minutes", type=float)
    p.add_argument("--radar-minutes", type=float)
    p.add_argument("--post-seconds", type=float)
    p.add_argument("--stale-minutes", type=float)
    p.add_argument("--ims-stale-minutes", type=float,
                   help="use Open-Meteo when the newest IMS reading is older than this")
    p.add_argument("--radar-stale-minutes", type=float)
    p.add_argument("--radar-season", metavar="MM-DD:MM-DD",
                   help="dates (inclusive) when the radar is shown; heat stress and UV otherwise")
    p.add_argument("--no-radar", action="store_true", help="show the summer panel all year")
    p.add_argument("--weather-only", action="store_true", help="only the weather panel, nothing on the left")
    p.add_argument("--no-label", action="store_true", help="don't show the data source credits")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return p, p.parse_args(argv)


def settings(p, args) -> config.Config:
    """The config file with the command line on top. Runs setup first while
    the config says it hasn't run (unless --lat/--lon stand in for it)."""
    path = args.config or config.default_path()
    try:
        cfg = config.load(path)
    except ValueError as e:
        p.error(f"{path}: {e}")
    if args.lat is None and (cfg is None or not cfg.setup.complete):
        interactive = sys.stdin.isatty()
        if cfg is None and not interactive:
            p.error(f"no config at {path}: copy config/config.example.toml to config/config.toml and fill it in (README), "
                    "or run `python -m weather_provider setup` from a terminal")
        print(f"Setup hasn't run yet ({path}); running it{'' if interactive else ' from the config file'}.\n")
        onboard.main(["--config", str(path)] + ([] if interactive else ["--defaults"]))
        cfg = config.load(path)
    cfg = cfg or config.Config(path=path)
    for value, section, key in [
        (args.lat, "location", "latitude"), (args.lon, "location", "longitude"),
        (args.timezone, "location", "timezone"), (args.server, "sign", "server"),
        (args.x, "sign", "x"), (args.y, "sign", "y"),
        (args.fetch_minutes, "timing", "fetch_minutes"), (args.radar_minutes, "timing", "radar_minutes"),
        (args.post_seconds, "timing", "post_seconds"), (args.stale_minutes, "timing", "stale_minutes"),
        (args.ims_stale_minutes, "timing", "ims_stale_minutes"),
        (args.radar_stale_minutes, "timing", "radar_stale_minutes"),
        (args.radar_season, "radar", "season"),
    ]:
        if value is not None:
            setattr(getattr(cfg, section), key, value)
    if args.no_radar:
        cfg.radar.enabled = False
    if args.weather_only:
        cfg.sign.left_panel = False
    if args.no_label:
        cfg.display.credits = False
    if args.verbose:
        cfg.display.verbose = True
    if cfg.location.latitude is None or cfg.location.longitude is None:
        p.error(f"no location: set it in {path} or pass --lat and --lon")
    return cfg


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["setup"]:
        return onboard.main(argv[1:])
    p, args = parse_args(argv)
    cfg = settings(p, args)
    logging.basicConfig(
        level=logging.DEBUG if cfg.display.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    loc, t = cfg.location, cfg.timing
    try:
        season = radar.parse_season(cfg.radar.season)
        tz = ZoneInfo(loc.timezone)
    except (ValueError, KeyError) as e:
        p.error(str(e))
    if cfg.radar.enabled and not radar.covers(loc.latitude, loc.longitude):
        log.warning("home is outside the IMS radar's coverage, turning the radar off")
        cfg.radar.enabled = False
    left_panel = cfg.sign.left_panel
    radar_enabled = left_panel and cfg.radar.enabled
    if radar_enabled and not cfg.coastline_path().exists():
        # Setup couldn't get it (Overpass is often busy); try again each start.
        try:
            onboard.make_coast(cfg, log.info)
        except Exception as e:
            log.warning("coastline download failed (%s); the radar has no coast until a later start", e)
    scope = onboard.scope_for(cfg) if radar_enabled else None
    fetcher = radar.Fetcher()

    ims_key = cfg.ims_api_key
    ims_station = cfg.ims.station
    ims_city = None if cfg.ims.location is None else str(cfg.ims.location)
    if ims_station is not None and ims_key is None:
        log.warning("IMS station set but no API key (ims.api_key or IMS_API_KEY), using Open-Meteo")
    use_ims_station = ims_station is not None and ims_key is not None
    ims_reading = om_reading = None
    om_good = None  # when we last got an Open-Meteo reading
    shown_source = None
    uv_table = None  # IMS hourly UV forecast for the IMS city
    uv_day = None  # local date it was fetched
    next_uv = 0.0  # earliest retry after a failed UV fetch
    highs = None  # IMS forecast highs for the IMS city, by date
    highs_day = None  # local date they were fetched
    next_highs = 0.0  # earliest retry after a failed forecast fetch
    frames = []  # recent radar frames, oldest first
    was_in_season = None
    next_fetch = next_radar = 0.0
    while True:
        now = time.monotonic()
        radar_on = radar_enabled and radar.in_season(datetime.now(tz).date(), season)
        if radar_on != was_in_season:
            if radar_enabled:
                log.info("rain season %s: showing %s", "on" if radar_on else "over",
                         "the radar" if radar_on else "heat stress and UV")
            was_in_season = radar_on
            if not radar_on:
                frames = []
        if now >= next_fetch:
            next_fetch = now + t.fetch_minutes * 60
            if use_ims_station:
                try:
                    ims_reading = ims.fetch(ims_key, ims_station)
                    log_reading(ims_reading)
                except Exception as e:
                    log.warning("IMS fetch failed: %s", e)
            try:
                om_reading = openmeteo.fetch(loc.latitude, loc.longitude, loc.timezone)
                om_good = now
                log_reading(om_reading)
            except Exception as e:
                log.warning("Open-Meteo fetch failed: %s", e)

        today = datetime.now(tz).date()
        summer_on = left_panel and not radar_on
        if ims_city and summer_on and uv_day != today and now >= next_uv:
            try:
                uv_table = uvi.fetch(ims_city)
                uv_day = today
                log.info("UV forecast for today: %s", " ".join(
                    f"{h}:{v}" for h, v in sorted(uv_table.get(today.isoformat(), {}).items())))
            except Exception as e:
                next_uv = now + 3600  # try again in an hour, not every loop
                log.warning("UV forecast fetch failed: %s", e)
        if ims_city and summer_on and highs_day != today and now >= next_highs:
            try:
                highs = forecast.fetch(ims_city)
                highs_day = today
                log.info("IMS forecast high for today: %s", highs.get(today.isoformat()))
            except Exception as e:
                next_highs = now + 3600
                log.warning("IMS forecast fetch failed: %s", e)

        if radar_on and now >= next_radar:
            next_radar = now + t.radar_minutes * 60
            try:
                frames = fetcher.recent(PREVIOUS_FRAMES + 1)
                log.info("radar frames %s", " ".join(f.taken_at.strftime("%H:%M") for f in frames))
            except Exception as e:
                log.warning("radar fetch failed: %s", e)

        if om_good is not None and now - om_good > t.stale_minutes * 60:
            om_reading = None
        # IMS if its newest reading is recent enough, else Open-Meteo (IMS §10).
        reading, why = om_reading, "no IMS reading"
        if ims_reading is not None:
            age_min = (datetime.now(timezone.utc) - ims_reading.observed_at).total_seconds() / 60
            if age_min <= t.ims_stale_minutes:
                reading = ims_reading
            else:
                why = f"newest IMS reading is {age_min:.0f} min old"
        source = reading.source if reading else None
        if source != shown_source:
            if source == "IMS":
                log.info("weather panel now shows IMS")
            else:
                log.warning("weather panel now shows %s (%s)", source or "dashes", why)
            shown_source = source
        # The animation: previous frames once each, then "now" held. Only if the
        # newest frame is fresh; otherwise a single frame with no rain.
        loop = []
        if frames:
            age_min = (datetime.now(radar.ISRAEL) - frames[-1].taken_at).total_seconds() / 60
            if age_min > t.radar_stale_minutes:
                log.warning("newest radar frame is %d min old, not showing rain", age_min)
            else:
                loop = frames[:-1] + [frames[-1]] * HOLD_FRAMES
        shown_frame = loop[-1] if loop else None

        # The summer panel: UV and today's high are IMS's forecasts when there's
        # an IMS city (Open-Meteo's if IMS has none for now); sunset is Open-Meteo's.
        extras = om_reading if summer_on else None
        uv = uv_source = None
        if summer_on:
            uv = uvi.at(uv_table, datetime.now(tz))
            if uv is not None:
                uv_source = "IMS"
            elif extras is not None and extras.uv_index is not None:
                uv, uv_source = extras.uv_index, "OM"
        high = high_source = None
        if summer_on:
            high = (highs or {}).get(today.isoformat())
            if high is not None:
                high_source = "IMS"
            elif extras is not None and extras.max_temp_c is not None:
                high, high_source = extras.max_temp_c, "OM"

        # Credit whichever sources are on screen right now (docs/COMPLIANCE.md).
        sources = []
        if shown_frame is not None or uv_source == "IMS" or high_source == "IMS":
            sources.append("IMS")
        if reading is not None:
            sources.append(reading.source)
        if (extras is not None and extras.sunset is not None) or "OM" in (high_source, uv_source):
            sources.append("OM")
        sources = sorted(set(sources), key=["IMS", "OM"].index)
        credit = " ".join(sources) if cfg.display.credits else ""

        try:
            post(cfg.sign.server, cfg.sign.x, cfg.sign.y, WIDTH, HEIGHT, to_rgb565(render(reading)))
            if left_panel:
                if radar_on:
                    panels = [radar.render(scope, f, credit) for f in (loop or [None])]
                else:
                    # Heat stress from the reading on the weather panel.
                    hs = reading and summer.heat_stress_level(
                        summer.heat_stress_index(reading.temperature_c, reading.humidity_pct))
                    panels = [summer.render(hs, uv, credit,
                                            sunset=extras and extras.sunset,
                                            max_temp_c=high)]
                post(cfg.sign.server, 0, 0, radar.WIDTH, radar.HEIGHT,
                     b"".join(to_rgb565(p) for p in panels), frames=len(panels))
        except Exception as e:
            log.warning("post to %s failed: %s", cfg.sign.server, e)
        time.sleep(t.post_seconds)


if __name__ == "__main__":
    main()
