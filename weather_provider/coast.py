"""The coastline on the radar scope, from OpenStreetMap.

Setup downloads the natural=coastline ways around home from the Overpass API,
simplifies them (Douglas-Peucker) and saves them as coast.json next to the
config. The file records its source and license: it is OSM data and stays
under the ODbL (docs/COMPLIANCE.md). Inland, the file is just empty.
"""

import json
import logging
import math
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

# Public Overpass servers, tried in turn: they're often busy (502, 504, 429).
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
log = logging.getLogger("weather_provider")
USER_AGENT = "weather-provider (home LED sign)"
LICENSE = "ODbL 1.0, (c) OpenStreetMap contributors, https://www.openstreetmap.org/copyright"
TOLERANCE = 0.001  # degrees, about 100 m: far below one sign pixel


def bbox(scope, width, height, margin_px=4):
    """(south, west, north, east) covering the panel, plus a few pixels."""
    corners = [scope.to_latlon(x, y) for x in (-margin_px, width + margin_px)
               for y in (-margin_px, height + margin_px)]
    lats, lons = [c[0] for c in corners], [c[1] for c in corners]
    return round(min(lats), 4), round(min(lons), 4), round(max(lats), 4), round(max(lons), 4)


def _distance(p, a, b):
    """Distance from point p to segment a-b, in degrees (fine at this scale)."""
    (py, px), (ay, ax), (by, bx) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def simplify(points, tolerance=TOLERANCE):
    """Douglas-Peucker: drop points closer than tolerance to the line."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        best, best_d = None, tolerance
        for k in range(i + 1, j):
            d = _distance(points[k], points[i], points[j])
            if d > best_d:
                best, best_d = k, d
        if best is not None:
            keep[best] = True
            stack += [(i, best), (best, j)]
    return [p for p, k in zip(points, keep) if k]


def parse(payload: dict, tolerance=TOLERANCE):
    """[[(lat, lon), ...], ...] from an Overpass `out geom` answer."""
    lines = []
    for el in payload.get("elements", []):
        geom = el.get("geometry") or []
        pts = [(round(g["lat"], 5), round(g["lon"], 5)) for g in geom]
        if len(pts) >= 2:
            lines.append(simplify(pts, tolerance))
    return lines


def download(box, timeout=120, rounds=2, wait=20):
    """Coastline lines inside (south, west, north, east). Tries each Overpass
    server, `rounds` times over, waiting between rounds; raises the last error."""
    s, w, n, e = box
    query = f'[out:json][timeout:{timeout - 10}];way["natural"="coastline"]({s},{w},{n},{e});out geom;'
    data = urllib.parse.urlencode({"data": query}).encode()
    error = None
    for attempt in range(rounds):
        if attempt:
            time.sleep(wait)
        for url in OVERPASS_URLS:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return parse(json.load(resp))
            except Exception as ex:  # busy server, timeout, bad answer: try the next
                log.debug("Overpass %s failed: %s", url, ex)
                error = ex
    raise error


def save(path, lines, box, today=None):
    s, w, n, e = box
    data = {
        "source": f"OpenStreetMap natural=coastline, Overpass query bbox ({s},{w},{n},{e}), "
                  f"fetched {(today or date.today()).isoformat()}, "
                  f"simplified (Douglas-Peucker, {TOLERANCE} deg)",
        "license": LICENSE,
        "lines": lines,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":")))


def load(path):
    """The saved lines, or [] if there's no file (no coastline drawn)."""
    try:
        return json.loads(Path(path).read_text())["lines"]
    except FileNotFoundError:
        return []
