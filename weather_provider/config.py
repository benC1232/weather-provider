"""Settings, from a TOML file written by `python -m weather_provider setup`.

The repo ships config/config.example.toml; copy it to config/config.toml
(gitignored) and fill it in. A config at
~/.config/weather-provider/config.toml wins over it (handy for keeping your
key out of the checkout), and WEATHER_PROVIDER_CONFIG or --config win over
both (default_path()). It holds the location, the
sign's address, the IMS key and which IMS station and forecast city to use,
the radar scope's layout, the timings and the on/off switches that the
command-line flags also set. Anything left out gets the default below. The
coastline drawn on the radar sits next to it (coast.json).

[setup] complete says whether setup has run: while it's false (or the file
is new), starting weather_provider runs setup first, then sets it to true.

Keep the file out of the repo: it has your coordinates and API key.
"""

import os
import tomllib
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

USER_PATH = Path(os.path.expanduser("~/.config/weather-provider/config.toml"))
REPO_PATH = Path(__file__).resolve().parent.parent / "config" / "config.toml"
EXAMPLE_PATH = REPO_PATH.with_name("config.example.toml")


@dataclass
class Setup:
    complete: bool = False


@dataclass
class Location:
    latitude: float | None = None
    longitude: float | None = None
    timezone: str = "UTC"


@dataclass
class Sign:
    server: str = "http://localhost:5001/frame"
    x: int = 88
    y: int = 0
    left_panel: bool = True


@dataclass
class IMS:
    api_key: str = ""
    station: int | None = None
    location: int | None = None


@dataclass
class Radar:
    enabled: bool = True
    season: str = "10-01:05-30"
    direction: str = "NW"
    range_km: float = 100
    home_x: int = 75
    home_y: int = 19
    km_per_px: float = 1.65
    rings_km: list = field(default_factory=lambda: [33, 67, 100])
    coastline: str = "coast.json"


@dataclass
class Timing:
    fetch_minutes: float = 10
    radar_minutes: float = 5
    post_seconds: float = 60
    stale_minutes: float = 45
    ims_stale_minutes: float = 45
    radar_stale_minutes: float = 30


@dataclass
class Display:
    credits: bool = True
    verbose: bool = False


# What each section and setting is for; written into the file as comments.
SECTION_DOCS = {
    "setup": "Set complete = false to run setup again on the next start (it also runs\n"
             "while this is false on a new install). `python -m weather_provider setup`\n"
             "runs it any time.",
    "location": "Where to get the weather for. Fill in latitude and longitude before the\n"
                "first start (remove the # in front); setup looks up the time zone itself.",
    "sign": "Where sign-server is and where the panels go on the 128x32 sign.",
    "ims": "Israel Meteorological Service: only in and around Israel. Each part is\n"
           "optional; without it Open-Meteo is used instead. Setup fills in station\n"
           "and location (the nearest ones) when you give it a key or are in Israel.",
    "radar": "The IMS rain radar scope (Israel only: off by itself elsewhere). Outside\n"
             "the season, or when disabled, the left panel shows heat stress and UV.\n"
             "Setup works out home_x, home_y, km_per_px and rings_km from direction\n"
             "and range_km; edit those four only to fine-tune.",
    "timing": "Minutes between fetches, how often to re-post, and when data is too old.",
    "display": "",
}
SETTING_DOCS = {
    "setup.complete": "true once setup has run (true/false)",
    "location.latitude": "decimal degrees, north positive, e.g. 31.5 (required)",
    "location.longitude": "decimal degrees, east positive, e.g. 34.9 (required)",
    "location.timezone": 'IANA name, e.g. "Asia/Jerusalem"; sets "today", the season and sunset. --timezone',
    "sign.server": "sign-server's frame URL. --server",
    "sign.x": "top-left of the 40x32 weather panel. --x",
    "sign.y": "--y",
    "sign.left_panel": "true: radar / summer panel on the left 88x32. false = --weather-only",
    "ims.api_key": "for IMS station readings (free, ims.gov.il); the IMS_API_KEY environment variable wins",
    "ims.station": "IMS station id for temperature and humidity",
    "ims.location": "IMS forecast city id for the UV index and today's high",
    "radar.enabled": "true: radar in the rain season. false = --no-radar (summer panel all year)",
    "radar.season": 'dates the radar is shown, "MM-DD:MM-DD", inclusive. --radar-season',
    "radar.direction": "where your rain usually comes from: N NE E SE S SW W NW, or ALL (centered)",
    "radar.range_km": "radius of the outer ring",
    "radar.home_x": "home's pixel on the 88x32 panel",
    "radar.home_y": "",
    "radar.km_per_px": "",
    "radar.rings_km": "",
    "radar.coastline": "OpenStreetMap coastline file, next to this one; `setup --coast-only` refreshes it",
    "timing.fetch_minutes": "how often to fetch the weather. --fetch-minutes",
    "timing.radar_minutes": "how often to fetch the radar (IMS makes a frame every 5). --radar-minutes",
    "timing.post_seconds": "how often to re-post the panels. --post-seconds",
    "timing.stale_minutes": "dashes after this long without a good reading. --stale-minutes",
    "timing.ims_stale_minutes": "Open-Meteo when the newest IMS reading is older. --ims-stale-minutes",
    "timing.radar_stale_minutes": "leave out rain older than this. --radar-stale-minutes",
    "display.credits": "true: show the IMS / OM source labels (the data terms require them). false = --no-label",
    "display.verbose": "true: debug logging. true = -v / --verbose",
}


@dataclass
class Config:
    setup: Setup = field(default_factory=Setup)
    location: Location = field(default_factory=Location)
    sign: Sign = field(default_factory=Sign)
    ims: IMS = field(default_factory=IMS)
    radar: Radar = field(default_factory=Radar)
    timing: Timing = field(default_factory=Timing)
    display: Display = field(default_factory=Display)
    path: Path | None = None  # where it was loaded from

    @property
    def ims_api_key(self) -> str | None:
        return os.environ.get("IMS_API_KEY", "").strip() or self.ims.api_key.strip() or None

    def coastline_path(self) -> Path:
        base = (self.path or default_path()).parent
        return base / self.radar.coastline


SECTIONS = [f.name for f in fields(Config) if f.name != "path"]


def default_path() -> Path:
    """$WEATHER_PROVIDER_CONFIG, else ~/.config/weather-provider/config.toml if
    it exists, else the repo's config/config.toml (when running from a
    checkout), else the ~/.config one, for setup to create."""
    env = os.environ.get("WEATHER_PROVIDER_CONFIG")
    if env:
        return Path(env).expanduser()
    if USER_PATH.exists() or not REPO_PATH.parent.is_dir():
        return USER_PATH
    return REPO_PATH


def from_dict(data: dict, path: Path | None = None) -> Config:
    """A Config from parsed TOML; unknown sections or keys raise ValueError."""
    cfg = Config(path=path)
    for section, values in data.items():
        if section not in SECTIONS or not isinstance(values, dict):
            raise ValueError(f"unknown section [{section}]")
        target = getattr(cfg, section)
        known = {f.name for f in fields(target)}
        for key, value in values.items():
            if key not in known:
                raise ValueError(f"unknown setting {section}.{key}")
            setattr(target, key, value)
    return cfg


def load(path: Path | None = None) -> Config | None:
    """The config at path (default_path() if None), or None if there's no file."""
    path = Path(path) if path else default_path()
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return None
    return from_dict(data, path)


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    raise TypeError(f"can't write {v!r} to TOML")


HEADER = ("# weather-provider settings, written by `python -m weather_provider setup`.\n"
          "# Edit freely. Switches are true or false; each command-line flag named\n"
          "# below overrides its setting for one run. Keep this file private: it has\n"
          "# your location and API key.")


def dumps(cfg: Config, header: str = HEADER) -> str:
    """The config as commented TOML. Unset values (None) are written commented out."""
    out = [header]
    for section in SECTIONS:
        out.append("")
        if SECTION_DOCS[section]:
            out += ["# " + line for line in SECTION_DOCS[section].split("\n")]
        out.append(f"[{section}]")
        for key, value in asdict(getattr(cfg, section)).items():
            doc = SETTING_DOCS.get(f"{section}.{key}")
            note = f"  # {doc}" if doc else ""
            if value is None:
                out.append(f"# {key} ={note}")
            else:
                out.append(f"{key} = {_toml_value(value)}{note}")
    return "\n".join(out) + "\n"


def save(cfg: Config, path: Path) -> None:
    """Writes the config, readable only by its owner (it holds the API key)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(dumps(cfg))
    os.chmod(path, 0o600)
    cfg.path = path
