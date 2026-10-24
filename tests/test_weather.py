from datetime import datetime, timezone

import pytest

from weather_provider import openmeteo
from weather_provider.colors import temperature_color
from weather_provider.font import GLYPHS, SMALL_GLYPHS
from weather_provider.render import HEIGHT, WIDTH, render, to_rgb565

SAMPLE = {
    "current": {"time": "2026-10-02T17:15", "interval": 900,
                "temperature_2m": 21.6, "relative_humidity_2m": 83},
}


def reading(t=21.6, rh=83):
    return openmeteo.Reading(t, rh, datetime(2026, 10, 2, tzinfo=timezone.utc), "OM")


@pytest.mark.parametrize("t, rgb", [
    (5, (0, 0, 255)),      # fully blue at 5 °C
    (-3, (0, 0, 255)),     # and stays blue below
    (15, (255, 255, 255)), # white
    (41.5, (255, 0, 0)),   # red, as in Wikipedia's table
    (48, (255, 0, 0)),     # stays red instead of darkening to black
])
def test_temperature_color_anchors(t, rgb):
    assert temperature_color(t) == rgb


def test_temperature_color_gets_warmer():
    greens = [temperature_color(t)[1] for t in range(15, 42)]
    assert greens == sorted(greens, reverse=True)


def test_glyphs_are_rectangular():
    for table, height in ((GLYPHS, 7), (SMALL_GLYPHS, 5)):
        for name, rows in table.items():
            assert len(rows) == height, name
            assert len({len(r) for r in rows}) == 1, name


def test_parse():
    r = openmeteo.parse(SAMPLE)
    assert (r.temperature_c, r.humidity_pct, r.source) == (21.6, 83, "OM")
    assert r.observed_at == datetime(2026, 10, 2, 17, 15, tzinfo=timezone.utc)


@pytest.mark.parametrize("field, value", [("temperature_2m", 99), ("relative_humidity_2m", 140)])
def test_parse_rejects_implausible(field, value):
    bad = {"current": dict(SAMPLE["current"], **{field: value})}
    with pytest.raises(ValueError):
        openmeteo.parse(bad)


@pytest.mark.parametrize("r", [reading(), reading(-12, 5), reading(45, 100), reading(20, 7), None])
def test_render_fits_panel(r):
    img = render(r)
    assert img.size == (WIDTH, HEIGHT)
    assert len(to_rgb565(img)) == WIDTH * HEIGHT * 2



def test_parse_local_time_high_and_sunset():
    payload = {
        "timezone": "Asia/Jerusalem",
        "current": {"time": "2026-10-03T01:30", "temperature_2m": 19.8, "relative_humidity_2m": 88},
        "daily": {"time": ["2026-10-03"], "temperature_2m_max": [26.6], "sunset": ["2026-10-03T18:22"]},
    }
    r = openmeteo.parse(payload)
    assert r.observed_at == datetime(2026, 10, 2, 22, 30, tzinfo=timezone.utc)
    assert r.max_temp_c == 26.6
    assert (r.sunset.hour, r.sunset.minute) == (18, 22)


def test_parse_without_daily_still_works():
    r = openmeteo.parse(SAMPLE)
    assert r.max_temp_c is None and r.sunset is None


def test_parse_uv_index():
    assert openmeteo.parse(SAMPLE).uv_index is None
    cur = dict(SAMPLE["current"], uv_index=6.4)
    assert openmeteo.parse({"current": cur}).uv_index == 6.4
    cur["uv_index"] = 99  # implausible: dropped, the reading stays
    assert openmeteo.parse({"current": cur}).uv_index is None
