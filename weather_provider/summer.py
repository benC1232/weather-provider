"""Panel for the months without the rain radar: heat stress and UV index.

Heat stress is calculated from the temperature and humidity on the weather
panel (the IMS station, or Open-Meteo when IMS is late). UV is IMS's hourly
forecast for the configured IMS city (uvi.py).

Heat stress (עומס חום) is shown as IMS's level number, 0-5, the same
numbering as the heat_stress_level field in IMS's forecasts. The index is
IMS's (T + Tw) / 2, air plus wet-bulb temperature; the station's wet-bulb
sensor reported nothing valid, so Tw is calculated from T and humidity
(Stull 2011), which matched IMS's own index within about 0.2.

Levels as ims.gov.il labels an index (colorbar.heat_stress, read 2026-10-05):
round to a whole number (halves up), then

    0 none under 22, 1 light (קל) 22-23, 2 moderate (מתון) 24-25,
    3 medium (בינוני) 26-27, 4 heavy (כבד) 28-29, 5 extreme (קיצוני) 30+

(The heat_stress_level field in IMS's hourly forecasts starts each level
half a degree higher; we follow the scale the site labels values with.)

UV levels follow IMS's UV scale: 1 low, 3 moderate, 6 high, 8 very high,
11 extreme. Colors keep IMS's order but use near-pure hues, since mixed
colors shift on the LED panel (amber reads yellow, light red reads pink).
"""

import math
from functools import lru_cache

from PIL import Image, ImageDraw

from .colors import temperature_color
from .font import LARGE_GLYPHS, MEDIUM_GLYPHS, SMALL_GLYPHS, draw_text, text_width

WIDTH = 88
HEIGHT = 32

LABEL_COLOR = (70, 70, 70)
MISSING_COLOR = (90, 90, 90)
NO_STRESS_COLOR = (230, 230, 230)
NIGHT_SUN_COLOR = (70, 70, 70)

# Heat stress level -> (lowest rounded index for that level, color). Level 0 is none.
HEAT_STRESS_LEVELS = {
    0: (None, NO_STRESS_COLOR),
    1: (22, (255, 220, 0)),  # light (קל)
    2: (24, (255, 100, 0)),  # moderate (מתון)
    3: (26, (255, 0, 0)),    # medium (בינוני)
    4: (28, (140, 0, 0)),    # heavy (כבד)
    5: (30, (255, 0, 255)),  # extreme (קיצוני)
}
# (lower bound, color), highest first.
UV_LEVELS = [
    (11, (140, 0, 255)),  # extreme
    (8, (255, 0, 0)),     # very high
    (6, (255, 100, 0)),   # high
    (3, (255, 220, 0)),   # moderate
    (1, (0, 200, 0)),     # low
]

SUN_CENTER = (71, 16)
SUN_SIZE = 31
HS_GAP = 3  # heat stress number sits this far left of the sun

# Left column: source credit in the top-left corner, sunset time 2 px under
# it, today's high 3 px under that and flush with the bottom edge. The two
# rows split the remaining height, so they're as big as they can be.
CREDIT_Y = 0                         # rows 0-4 (small glyphs are 5 tall)
SUNSET_Y = CREDIT_Y + 5 + 2          # rows 7-17
ROW_H = 11                           # LARGE_GLYPHS height
MAX_TEMP_Y = HEIGHT - ROW_H          # rows 21-31
assert MAX_TEMP_Y - (SUNSET_Y + ROW_H) == 3
ROW_Y = (SUNSET_Y, MAX_TEMP_Y)
ICON_X = 0
TEXT_X = 10
SUNSET_TEXT_COLOR = (255, 170, 60)

# Pixel icons, 9x11. Each letter is a color; "." is off.
ICON_COLORS = {
    "s": (255, 120, 0),   # setting sun
    "h": (60, 90, 255),   # horizon / sea
    "r": (255, 30, 0),    # thermometer fill and arrow
    "w": (200, 200, 200), # thermometer glass
}
SUNSET_ICON = [
    "....s....",
    ".s..s..s.",
    "..s...s..",
    ".........",
    "...sss...",
    "..sssss..",
    ".sssssss.",
    "sssssssss",
    "hhhhhhhhh",
    ".hhhhhhh.",
    "...hhh...",
]
MAX_TEMP_ICON = [
    ".r....w..",
    "rrr..w.w.",
    ".r...w.w.",
    ".r...wrw.",
    ".r...wrw.",
    ".r...wrw.",
    ".r...wrw.",
    "....wrrrw",
    "....wrrrw",
    "....wrrrw",
    ".....www.",
]


def _level_color(value, levels, below):
    for bound, color in levels:
        if value >= bound:
            return color
    return below


def wet_bulb(t, rh):
    """Wet-bulb temperature (°C) from air temperature (°C) and relative
    humidity (%), Stull (2011). Good to about 0.3 °C for 5-99% humidity."""
    rh = min(max(rh, 5), 99)
    return (t * math.atan(0.151977 * math.sqrt(rh + 8.313659))
            + math.atan(t + rh) - math.atan(rh - 1.676331)
            + 0.00391838 * rh ** 1.5 * math.atan(0.023101 * rh) - 4.686035)


def heat_stress_index(t, rh):
    """IMS's heat stress index: the mean of air and wet-bulb temperature."""
    return (t + wet_bulb(t, rh)) / 2


def heat_stress_level(index):
    """IMS level 0-5 for a heat stress index, using IMS's scale."""
    index = math.floor(index + 0.5)  # rounds halves up, like the site (round() wouldn't)
    for level in range(5, 0, -1):
        if index >= HEAT_STRESS_LEVELS[level][0]:
            return level
    return 0


def heat_stress_color(level):
    return HEAT_STRESS_LEVELS[level][1]


def uv_color(uv):
    return _level_color(round(uv), UV_LEVELS, NIGHT_SUN_COLOR)


@lru_cache(maxsize=None)
def sun_mask(size=SUN_SIZE):
    """Anti-aliased sun (disc plus eight rays) as an "L" mask."""
    k = 8
    S = size * k
    c = S / 2
    mask = Image.new("L", (S, S))
    d = ImageDraw.Draw(mask)
    disc = S * 0.31
    d.ellipse([c - disc, c - disc, c + disc, c + disc], fill=255)
    inner, outer, half_w = S * 0.385, S * 0.49, S * 0.045
    for i in range(8):
        a = math.radians(i * 45)
        ux, uy = math.cos(a), math.sin(a)
        px, py = -uy * half_w, ux * half_w
        d.polygon([
            (c + ux * inner + px, c + uy * inner + py),
            (c + ux * outer + px, c + uy * outer + py),
            (c + ux * outer - px, c + uy * outer - py),
            (c + ux * inner - px, c + uy * inner - py),
        ], fill=255)
    return mask.resize((size, size), Image.Resampling.BOX)


def draw_icon(img, x, y, icon):
    px = img.load()
    for row, line in enumerate(icon):
        for col, c in enumerate(line):
            if c != ".":
                px[x + col, y + row] = ICON_COLORS[c]


def render(heat_stress_level=None, uv=None, credit: str = "", sunset=None, max_temp_c=None) -> Image.Image:
    """Heat stress level (0-5, IMS numbering) and UV index next to the sun, with
    sunset time and today's high on the left. None shows a placeholder."""
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    # Sun with the UV index inside, colored by UV level; gray at night (UV 0).
    sun_color = MISSING_COLOR if uv is None else uv_color(uv)
    mask = sun_mask()
    sx, sy = SUN_CENTER[0] - SUN_SIZE // 2, SUN_CENTER[1] - SUN_SIZE // 2
    img.paste(sun_color, (sx, sy, sx + SUN_SIZE, sy + SUN_SIZE), mask)
    uv_text = "-" if uv is None else str(round(uv))
    tw = text_width(uv_text, MEDIUM_GLYPHS)
    th = len(MEDIUM_GLYPHS["0"])
    # Center on the disc; ties go left/up, matching where the disc's center lands.
    draw_text(draw, SUN_CENTER[0] - tw // 2, SUN_CENTER[1] - th // 2, uv_text, (0, 0, 0), MEDIUM_GLYPHS)

    # Heat stress level, 2x, in that level's color, just left of the sun.
    if heat_stress_level is None:
        hs_text, hs_color = "-", MISSING_COLOR
    else:
        hs_text, hs_color = str(heat_stress_level), heat_stress_color(heat_stress_level)
    w = text_width(hs_text, scale=2)
    draw_text(draw, sx - HS_GAP - w, (HEIGHT - 14) // 2, hs_text, hs_color, scale=2)

    # Sunset time.
    draw_icon(img, ICON_X, SUNSET_Y, SUNSET_ICON)
    if sunset is None:
        draw_text(draw, TEXT_X, SUNSET_Y, "--:--", MISSING_COLOR, LARGE_GLYPHS)
    else:
        draw_text(draw, TEXT_X, SUNSET_Y, sunset.strftime("%H:%M"), SUNSET_TEXT_COLOR, LARGE_GLYPHS)

    # Today's high, colored like the temperature on the weather panel.
    draw_icon(img, ICON_X, MAX_TEMP_Y, MAX_TEMP_ICON)
    if max_temp_c is None:
        text, color = "--°", MISSING_COLOR
    else:
        text, color = f"{round(max_temp_c)}°", temperature_color(max_temp_c)
    draw_text(draw, TEXT_X, MAX_TEMP_Y, text, color, LARGE_GLYPHS)

    if credit:
        draw_text(draw, 1, CREDIT_Y, credit, LABEL_COLOR, SMALL_GLYPHS)
    return img
