import pytest

from weather_provider import summer


@pytest.mark.parametrize("index, level", [
    # IMS's scale: round (halves up), then 22 light, 24, 26, 28, 30 extreme.
    (21.4, 0), (21.5, 1), (22, 1), (23.4, 1), (23.5, 2), (24.5, 2), (25.5, 3),
    (27.4, 3), (27.5, 4), (29.4, 4), (29.5, 5), (35, 5), (60, 5),
])
def test_heat_stress_level_from_index(index, level):
    assert summer.heat_stress_level(index) == level


def test_heat_stress_level_colors_are_distinct():
    colors = [summer.heat_stress_color(level) for level in range(6)]
    assert len(set(colors)) == 6
    assert colors[0] == summer.NO_STRESS_COLOR


@pytest.mark.parametrize("uv, color", [
    (0.2, summer.NIGHT_SUN_COLOR), (1, (0, 200, 0)), (4, (255, 220, 0)),
    (6.6, (255, 100, 0)), (9, (255, 0, 0)), (12, (140, 0, 255)),
])
def test_uv_levels(uv, color):
    assert summer.uv_color(uv) == color


@pytest.mark.parametrize("level, uv", [(3, 6.6), (5, 11.3), (0, 0), (None, None)])
def test_render_fits(level, uv):
    img = summer.render(level, uv, "OM")
    assert img.size == (summer.WIDTH, summer.HEIGHT)


def test_values_are_drawn_in_their_level_colors():
    colors = set(summer.render(3, 6.6).get_flattened_data())
    assert summer.heat_stress_color(3) in colors
    assert summer.uv_color(6.6) in colors


def test_placeholders_are_gray():
    """With no data, nothing but the icons is in color."""
    icon_colors = set(summer.ICON_COLORS.values())
    colors = set(summer.render().get_flattened_data()) - {(0, 0, 0)} - icon_colors
    assert summer.MISSING_COLOR in colors
    assert all(r == g == b for r, g, b in colors)


def test_sunset_and_high_are_drawn():
    from datetime import datetime
    img = summer.render(2, 5, "", sunset=datetime(2026, 7, 1, 19, 47), max_temp_c=31)
    colors = set(img.get_flattened_data())
    assert summer.SUNSET_TEXT_COLOR in colors
    from weather_provider.colors import temperature_color
    assert temperature_color(31) in colors


def test_heat_stress_sits_left_of_the_sun():
    img = summer.render(5, 11)
    sun_left = summer.SUN_CENTER[0] - summer.SUN_SIZE // 2
    color = summer.heat_stress_color(5)
    xs = [x for x in range(summer.WIDTH) for y in range(summer.HEIGHT) if img.getpixel((x, y)) == color]
    assert max(xs) == sun_left - summer.HS_GAP - 1


@pytest.mark.parametrize("uv", range(0, 16))
def test_uv_number_keeps_a_pixel_of_disc_around_it(uv):
    """Every text pixel has disc on all eight sides: at least one pixel to the edge."""
    mask = summer.sun_mask()
    sx = summer.SUN_CENTER[0] - summer.SUN_SIZE // 2
    sy = summer.SUN_CENTER[1] - summer.SUN_SIZE // 2
    px = summer.render(None, uv).load()
    text = [(x, y) for y in range(sy, sy + summer.SUN_SIZE) for x in range(sx, sx + summer.SUN_SIZE)
            if mask.getpixel((x - sx, y - sy)) >= 250 and px[x, y] == (0, 0, 0)]
    assert text, "number not drawn"
    for x, y in text:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                assert mask.getpixel((x + dx - sx, y + dy - sy)) >= 250


def test_left_column_spacing():
    """Credit top-left, 2 px to the sunset row, 3 px to the high, high flush with the bottom."""
    from datetime import datetime
    from weather_provider.colors import temperature_color
    img = summer.render(None, None, "OM", sunset=datetime(2026, 7, 1, 19, 47), max_temp_c=31)

    def rows_with(color):
        return sorted({y for y in range(summer.HEIGHT) for x in range(40) if img.getpixel((x, y)) == color})

    credit = rows_with(summer.LABEL_COLOR)
    sunset = rows_with(summer.SUNSET_TEXT_COLOR)
    high = rows_with(temperature_color(31))
    assert credit[0] == 0                       # top-left
    assert sunset[0] - credit[-1] - 1 == 2      # 2 px under the credit
    assert high[0] - sunset[-1] - 1 == 3        # 3 px between the rows
    assert high[-1] == summer.HEIGHT - 1        # flush with the bottom


def test_left_column_clears_the_heat_stress_number():
    """The widest sunset time must end before the heat stress digit starts."""
    from datetime import datetime
    from weather_provider.font import LARGE_GLYPHS, text_width
    widest = max(text_width(f"{h:02d}:{m:02d}", LARGE_GLYPHS) for h in range(24) for m in range(60))
    hs_left = summer.SUN_CENTER[0] - summer.SUN_SIZE // 2 - summer.HS_GAP - text_width("5", scale=2)
    assert summer.TEXT_X + widest < hs_left


@pytest.mark.parametrize("t, rh, index", [
    # Hourly values from IMS's Rishon LeZion forecast (2026-10-06): temperature,
    # humidity and IMS's own heat stress index.
    (22.5, 72, 20.7), (21.3, 80, 20.0), (23.2, 69, 21.2), (27.4, 45, 23.2),
    (27.5, 46, 23.3), (25.9, 52, 22.4), (24.6, 64, 22.2),
])
def test_heat_stress_index_matches_ims(t, rh, index):
    assert summer.heat_stress_index(t, rh) == pytest.approx(index, abs=0.25)


def test_wet_bulb_limits():
    assert summer.wet_bulb(30, 100) == pytest.approx(30, abs=0.5)  # saturated: Tw = T
    assert summer.wet_bulb(30, 0) < summer.wet_bulb(30, 50) < 30
