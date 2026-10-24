"""Rain radar panel: an old-style radar scope looking west from home.

Rain comes from the IMS radar images that ims.gov.il shows on its radar page.
The coastline is OpenStreetMap data (coast.py, ODbL). The IMS radar only
covers Israel and its surroundings (covers()); elsewhere setup turns it off.
"""

import io
import json
import math
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from .font import SMALL_GLYPHS, draw_text, text_width

FRAMES_URL = "https://ims.gov.il/he/radar_satellite/1"
IMS_BASE = "https://ims.gov.il"
USER_AGENT = "weather-provider (home LED sign)"
ISRAEL = ZoneInfo("Asia/Jerusalem")

# Where ims.gov.il puts the IMSRadar image on its (web-Mercator) map, from
# set_satellite_radar_on_map() in the site's ims_tools.js.
RADAR_NORTH = 34.5318966003582659
RADAR_SOUTH = 29.4468656950938161
RADAR_WEST = 31.7662931774178858
RADAR_EAST = 37.8648132475530090

WIDTH = 88
HEIGHT = 32

COAST_COLOR = (170, 170, 170)
HOME_COLOR = (255, 0, 0)
# One color per range ring, innermost first; the legend uses the same colors.
# Blues, getting lighter from the inner ring out. Lightened with a bit more
# green than red so they stay blue on the LEDs instead of turning lavender.
RING_COLORS = [(0, 0, 160), (30, 60, 255), (90, 140, 255)]
STALE_RING_COLOR = (60, 60, 60)
LABEL_COLOR = (70, 70, 70)


def covers(lat, lon) -> bool:
    """Is (lat, lon) on the IMS radar image? Rain is only measured well
    nearer the radar than the image's edges, so this is a minimum."""
    return RADAR_SOUTH <= lat <= RADAR_NORTH and RADAR_WEST <= lon <= RADAR_EAST


# Rain season: the radar is only shown between these dates (inclusive, local
# time). Outside it nothing is fetched from IMS and the panel shows summer.py.
SEASON = ((10, 1), (5, 30))  # Oct 1 to May 30


def parse_season(text: str):
    """"MM-DD:MM-DD" -> ((month, day), (month, day))."""
    try:
        start, end = text.split(":")
        season = tuple(tuple(int(n) for n in part.split("-")) for part in (start, end))
        for month, day in season:
            datetime(2024, month, day)  # validates (2024 allows Feb 29)
        return season
    except ValueError as e:
        raise ValueError(f"season must look like 10-01:05-30, got {text!r}") from e


def in_season(day, season=SEASON) -> bool:
    """Is `day` (a date) inside the season? Seasons may wrap over New Year."""
    (sm, sd), (em, ed) = season
    md = (day.month, day.day)
    if (sm, sd) <= (em, ed):
        return (sm, sd) <= md <= (em, ed)
    return md >= (sm, sd) or md <= (em, ed)


@dataclass
class RadarFrame:
    image: Image.Image  # RGBA, transparent where there's no rain
    taken_at: datetime  # aware, Israel time
    # IMS's color scale as ((r, g, b), mm/h), used to find the heaviest rain
    # when several radar pixels land on one sign pixel. Empty: use any rain.
    levels: list = field(default_factory=list)

    def intensity(self, rgb):
        """mm/h for a radar color: the nearest color on IMS's scale."""
        if not self.levels:
            return 1.0
        return min(self.levels, key=lambda lv: sum((a - b) ** 2 for a, b in zip(lv[0], rgb)))[1]


def _get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def recent_frame_infos(payload: dict, count: int):
    """[(file_name, taken_at)] of the newest `count` IMSRadar frames the site
    would show, oldest first."""
    frames = [
        f for f in payload["data"]["types"]["IMSRadar"]
        if f.get("file_name", "").endswith("_0.png")  # the site only overlays these
    ]
    if not frames:
        raise ValueError("no IMSRadar frames listed")
    frames.sort(key=lambda f: f["forecast_time"])
    return [
        (f["file_name"], datetime.strptime(f["forecast_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ISRAEL))
        for f in frames[-count:]
    ]


def latest_frame_info(payload: dict):
    """(file_name, taken_at) of the newest IMSRadar frame the site would show."""
    return recent_frame_infos(payload, 1)[-1]


def color_levels(payload: dict):
    """IMS's radar color scale as ((r, g, b), mm/h), or [] if it's missing."""
    try:
        items = payload["data"]["radar_colorbar"]["items"].values()
        return [(tuple(int(i["color"][k : k + 2], 16) for k in (1, 3, 5)), float(i["mark"])) for i in items]
    except (KeyError, TypeError, ValueError):
        return []


def fetch() -> RadarFrame:
    """Just the newest frame."""
    return Fetcher().recent(1)[-1]


class Fetcher:
    """Fetches the most recent frames, keeping images it already has, so each
    call downloads only frames IMS has published since the last one."""

    def __init__(self):
        self._images = {}  # file_name -> RGBA image

    def recent(self, count: int) -> list:
        """The newest `count` frames, oldest first."""
        payload = json.loads(_get(FRAMES_URL))
        infos = recent_frame_infos(payload, count)
        levels = color_levels(payload)
        wanted = {name for name, _ in infos}
        self._images = {name: img for name, img in self._images.items() if name in wanted}
        for name, _ in infos:
            if name not in self._images:
                self._images[name] = Image.open(io.BytesIO(_get(IMS_BASE + name))).convert("RGBA")
        return [RadarFrame(self._images[name], taken, levels) for name, taken in infos]


def _mercator_y(lat):
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


@dataclass
class Scope:
    """Maps between sign pixels and the ground around home."""
    lat: float
    lon: float
    # By default home sits low and right so the scope looks west through
    # north: in ten seasons of ERA5 data most of the rain where this was built
    # arrived from the north-west. Setup places it for the direction you pick.
    home_x: int = 75  # home's pixel on the panel
    home_y: int = 19
    # Zoomed so the 100 km ring sits ~61 px from home.
    km_per_px: float = 1.65
    ring_km: tuple = (33, 67, 100)  # evenly spaced; the last is the scope's edge
    coast: list = field(default_factory=list)  # [[(lat, lon), ...], ...], coast.load()

    @property
    def radius_px(self):
        return self.ring_km[-1] / self.km_per_px

    def to_pixel(self, lat, lon):
        kx = 111.32 * math.cos(math.radians(self.lat))
        x = self.home_x + (lon - self.lon) * kx / self.km_per_px
        y = self.home_y - (lat - self.lat) * 110.574 / self.km_per_px
        return x, y

    def to_latlon(self, x, y):
        kx = 111.32 * math.cos(math.radians(self.lat))
        lon = self.lon + (x - self.home_x) * self.km_per_px / kx
        lat = self.lat - (y - self.home_y) * self.km_per_px / 110.574
        return lat, lon


def radar_pixel(frame_size, lat, lon):
    """Pixel in an IMSRadar image for a lat/lon, or None if outside it."""
    w, h = frame_size
    fx = (lon - RADAR_WEST) / (RADAR_EAST - RADAR_WEST)
    top, bottom = _mercator_y(RADAR_NORTH), _mercator_y(RADAR_SOUTH)
    fy = (top - _mercator_y(lat)) / (top - bottom)
    if not (0 <= fx < 1 and 0 <= fy < 1):
        return None
    return int(fx * w), int(fy * h)


def _rain_at(scope, frame, src, x, y):
    """Heaviest rain color among the radar pixels under sign pixel (x, y)."""
    a = radar_pixel(frame.image.size, *scope.to_latlon(x - 0.5, y - 0.5))
    b = radar_pixel(frame.image.size, *scope.to_latlon(x + 0.5, y + 0.5))
    if a is None or b is None:
        return None
    best, best_mm = None, -1.0
    for ry in range(a[1], b[1] + 1):
        for rx in range(a[0], b[0] + 1):
            r, g, bl, alpha = src[rx, ry]
            if alpha:
                mm = frame.intensity((r, g, bl))
                if mm > best_mm:
                    best, best_mm = (r, g, bl), mm
    return best


def render(scope: Scope, frame: RadarFrame | None, credit: str = "") -> Image.Image:
    """The radar panel. `frame` None (no data, or too old) draws the scope without rain."""
    img = Image.new("RGB", (WIDTH, HEIGHT))
    px = img.load()
    r2 = scope.radius_px ** 2

    # Rain, in the radar's own colors, inside the scope.
    if frame is not None:
        src = frame.image.load()
        for y in range(HEIGHT):
            for x in range(WIDTH):
                if (x - scope.home_x) ** 2 + (y - scope.home_y) ** 2 <= r2:
                    rain = _rain_at(scope, frame, src, x, y)
                    if rain:
                        px[x, y] = rain

    # Coastline.
    draw = ImageDraw.Draw(img)
    for line in scope.coast:
        draw.line([scope.to_pixel(lat, lon) for lat, lon in line], fill=COAST_COLOR)

    # Range rings, the outermost being the edge of the scope. Gray when
    # there's no current radar frame, so "no rain" and "no data" look different.
    colors = RING_COLORS if frame is not None else [STALE_RING_COLOR] * len(RING_COLORS)
    radii = [km / scope.km_per_px for km in scope.ring_km]
    for y in range(HEIGHT):
        for x in range(WIDTH):
            d = math.hypot(x - scope.home_x, y - scope.home_y)
            if d > scope.radius_px + 0.5:
                px[x, y] = (0, 0, 0)  # nothing outside the scope
            elif px[x, y] == (0, 0, 0):  # rings go under rain and coast
                for r, color in zip(radii, colors):
                    if abs(d - r) < 0.5:
                        px[x, y] = color

    # Home.
    draw.rectangle([scope.home_x - 1, scope.home_y - 1, scope.home_x, scope.home_y], fill=HOME_COLOR)

    # Legend: ring distances in their ring colors, down the left edge.
    y = 9
    for km, color in zip(scope.ring_km, colors):
        draw_text(draw, 1, y, str(km), color, SMALL_GLYPHS)
        y += 6
    draw_text(draw, 1, y, "KM", LABEL_COLOR, SMALL_GLYPHS)

    # Data source credits (docs/COMPLIANCE.md), top-left corner of the screen.
    if credit:
        draw.rectangle([0, 0, text_width(credit, SMALL_GLYPHS) + 1, 6], fill=(0, 0, 0))
        draw_text(draw, 1, 1, credit, LABEL_COLOR, SMALL_GLYPHS)
    return img

