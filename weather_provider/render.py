"""Draws the weather panel: temperature over humidity."""

from array import array
from functools import lru_cache
import math
import sys

from PIL import Image, ImageDraw

from .colors import temperature_color
from .font import GLYPHS, draw_glyph, draw_text, text_width

WIDTH = 40
HEIGHT = 32

DROP_COLOR = (0, 120, 255)
HUMIDITY_COLOR = (200, 200, 200)
MISSING_COLOR = (90, 90, 90)

# Rows: temperature 1-14, humidity 18-31 (bottom edge), both at 2x.
TEMP_Y = 1
HUMIDITY_Y = HEIGHT - 14

@lru_cache(maxsize=None)
def smooth_drop(w: int, h: int) -> Image.Image:
    """Anti-aliased teardrop coverage mask (mode "L"), w x h pixels.

    A circle at the bottom plus the two lines from the tip that touch it,
    drawn at 8x and scaled down so edge pixels get partial brightness.
    """
    k = 8
    W, H = w * k, h * k
    r = W / 2 - 0.5
    cx, cy = W / 2, H - r - 0.5
    d = cy  # tip is at the top edge
    phi = math.acos(r / d)  # angle of the tangent points from straight up
    tx, ty = r * math.sin(phi), cy - r * math.cos(phi)
    mask = Image.new("L", (W, H))
    draw = ImageDraw.Draw(mask)
    draw.polygon([(cx, 0), (cx + tx, ty), (cx, cy), (cx - tx, ty)], fill=255)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    return mask.resize((w, h), Image.Resampling.BOX)


@lru_cache(maxsize=None)
def smooth_ring(size: int) -> Image.Image:
    """Anti-aliased ring coverage mask (mode "L"), size x size, for the degree sign."""
    k = 8
    S = size * k
    t = S * 0.2  # line thickness
    mask = Image.new("L", (S, S))
    draw = ImageDraw.Draw(mask)
    draw.ellipse([0, 0, S - 1, S - 1], fill=255)
    draw.ellipse([t, t, S - 1 - t, S - 1 - t], fill=0)
    return mask.resize((size, size), Image.Resampling.BOX)


def draw_degree(img: Image.Image, x: int, y: int, color, scale: int):
    """Round degree sign in the glyph's top-left box: a pixel ring at 1x, smooth above."""
    if scale == 1:
        draw_glyph(ImageDraw.Draw(img), x, y, GLYPHS["°"], color)
        return
    size = len(GLYPHS["°"][0]) * scale
    img.paste(color, (x, y, x + size, y + size), smooth_ring(size))


def draw_drop(img: Image.Image, x: int, y: int, scale: int):
    if scale == 1:
        draw_glyph(ImageDraw.Draw(img), x, y, GLYPHS["drop"], DROP_COLOR)
        return
    mask = smooth_drop(len(GLYPHS["drop"][0]) * scale, len(GLYPHS["drop"]) * scale)
    img.paste(DROP_COLOR, (x, y, x + mask.width, y + mask.height), mask)


def render(reading) -> Image.Image:
    """The 40x32 weather panel. `reading` is an openmeteo.Reading, or None to show dashes."""
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    if reading is None:
        temp_text, temp_color, hum_digits = "--°", MISSING_COLOR, "--"
    else:
        temp_text = f"{round(reading.temperature_c)}°"
        temp_color = temperature_color(reading.temperature_c)
        hum_digits = str(round(reading.humidity_pct))

    # Both rows are flush right, against the edge of the screen.
    # Temperature: 2x, or 1x if it wouldn't fit (e.g. "-12°").
    scale = 2 if text_width(temp_text, scale=2) <= WIDTH else 1
    # Degree sign flush right; the number sits a fixed gap from the sign,
    # measured from the digits' actual ink beside the ring (a "1" has empty
    # columns on its right, an "8" doesn't), so the gap looks the same for all.
    ring = len(GLYPHS["°"][0]) * scale
    ring_x = WIDTH - ring
    draw_degree(img, ring_x, TEMP_Y, temp_color, scale)
    digits = temp_text[:-1]
    dw = text_width(digits, scale=scale)
    ink = Image.new("L", (dw, 7 * scale))
    draw_text(ImageDraw.Draw(ink), 0, 0, digits, 255, scale=scale)
    box = ink.crop((0, 0, dw, ring)).getbbox()
    right = box[2] if box else dw  # 1 past the rightmost lit column beside the ring
    x = ring_x - (scale + 1) - right
    img.paste(temp_color, (x, TEMP_Y, x + dw, TEMP_Y + 7 * scale), ink)

    # Humidity: drop and digits at 2x with a 1x "%" on the baseline; all 1x if
    # that doesn't fit (e.g. "100").
    drop_w = len(GLYPHS["drop"][0])
    pct_w = len(GLYPHS["%"][0])
    for scale in (2, 1):
        row_w = drop_w * scale + 2 + text_width(hum_digits, scale=scale) + 1 + pct_w
        if row_w <= WIDTH:
            break
    x = WIDTH - row_w
    y = HEIGHT - 7 * scale
    draw_drop(img, x, y, scale)
    x += drop_w * scale + 2
    draw_text(draw, x, y, hum_digits, HUMIDITY_COLOR, scale=scale)
    x += text_width(hum_digits, scale=scale) + 1
    draw_glyph(draw, x, HEIGHT - 7, GLYPHS["%"], HUMIDITY_COLOR)
    return img


def to_rgb565(img: Image.Image) -> bytes:
    """Little-endian RGB565, row-major: what sign-server expects."""
    rgb = img.convert("RGB").tobytes()
    out = array("H", bytes(len(rgb) // 3 * 2))
    for i in range(len(out)):
        r, g, b = rgb[3 * i], rgb[3 * i + 1], rgb[3 * i + 2]
        out[i] = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    if sys.byteorder != "little":
        out.byteswap()
    return out.tobytes()
