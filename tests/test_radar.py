import math
from datetime import date, datetime

import pytest
from PIL import Image, ImageDraw

from weather_provider import radar

HOME = (32.08, 34.78)  # Tel Aviv, rounded


def scope():
    return radar.Scope(*HOME)


def test_scope_round_trip():
    s = scope()
    assert s.to_pixel(*HOME) == (s.home_x, s.home_y)
    lat, lon = s.to_latlon(30, 20)
    x, y = s.to_pixel(lat, lon)
    assert (round(x, 6), round(y, 6)) == (30, 20)


def test_scope_scale():
    s = scope()
    # 50 km due west is on the first ring
    lat, lon = s.to_latlon(s.home_x - 50 / s.km_per_px, s.home_y)
    assert lat == pytest.approx(HOME[0])
    assert (HOME[1] - lon) * 111.32 * math.cos(math.radians(HOME[0])) == pytest.approx(50, rel=0.01)


def test_edge_is_100_km():
    assert scope().ring_km[-1] == 100


def test_bottom_row_is_12_px_south():
    lat, _ = scope().to_latlon(0, radar.HEIGHT - 1)
    assert (HOME[0] - lat) * 110.574 == pytest.approx(12 * 1.65)


def test_covers():
    assert radar.covers(*HOME)
    assert not radar.covers(51.5, -0.12)  # London


def test_coast_is_drawn():
    s = scope()
    s.coast = [[s.to_latlon(40, 5), s.to_latlon(40, 25)]]
    assert radar.render(s, None).getpixel((40, 15)) == radar.COAST_COLOR


@pytest.mark.parametrize("lat, lon, expected", [
    (radar.RADAR_NORTH - 1e-9, radar.RADAR_WEST, (0, 0)),
    (radar.RADAR_SOUTH + 1e-9, radar.RADAR_EAST - 1e-9, (939, 939)),
])
def test_radar_pixel_corners(lat, lon, expected):
    assert radar.radar_pixel((940, 940), lat, lon) == expected


def test_radar_pixel_outside():
    assert radar.radar_pixel((940, 940), 40.0, 34.9) is None


def test_latest_frame_skips_non_overlay_files():
    payload = {"data": {"types": {"IMSRadar": [
        {"forecast_time": "2026-10-02 21:25:00", "file_name": "/a/IMSRadar4GIS_202610022125_0.png"},
        {"forecast_time": "2026-10-02 21:35:00", "file_name": "/a/IMSRadar4GIS_202610022135_1.png"},
        {"forecast_time": "2026-10-02 21:30:00", "file_name": "/a/IMSRadar4GIS_202610022130_0.png"},
    ]}}}
    name, taken = radar.latest_frame_info(payload)
    assert name.endswith("202610022130_0.png")
    assert (taken.hour, taken.minute, taken.utcoffset().total_seconds()) == (21, 30, 3 * 3600)


def frame_with_rain_at(lat, lon, color=(1, 211, 28, 255)):
    img = Image.new("RGBA", (940, 940))
    x, y = radar.radar_pixel(img.size, lat, lon)
    ImageDraw.Draw(img).rectangle([x - 3, y - 3, x + 3, y + 3], fill=color)
    return radar.RadarFrame(img, datetime.now(radar.ISRAEL))


def test_rain_shows_in_its_own_color():
    s = scope()
    lat, lon = s.to_latlon(48, 20)  # inside the scope
    img = radar.render(s, frame_with_rain_at(lat, lon))
    assert img.getpixel((48, 20)) == (1, 211, 28)


def test_rain_outside_scope_is_dropped():
    s = scope()
    lat, lon = s.to_latlon(15, 2)  # left of the 100 km edge, right of the legend
    img = radar.render(s, frame_with_rain_at(lat, lon))
    assert img.getpixel((15, 2)) == (0, 0, 0)


def test_home_and_size():
    s = scope()
    img = radar.render(s, None, "IMS OM")
    assert img.size == (radar.WIDTH, radar.HEIGHT)
    assert img.getpixel((s.home_x, s.home_y)) == radar.HOME_COLOR


def test_rings_gray_without_data():
    s = scope()
    colors = set(radar.render(s, None).get_flattened_data())
    assert radar.STALE_RING_COLOR in colors
    assert not (colors - {radar.HOME_COLOR}) & set(radar.RING_COLORS)


def test_heaviest_rain_wins_when_pixels_share_a_sign_pixel():
    s = scope()
    lat, lon = s.to_latlon(48, 20)
    light, heavy = (0, 195, 201), (225, 10, 18)
    img = Image.new("RGBA", (940, 940))
    x, y = radar.radar_pixel(img.size, lat, lon)
    d = ImageDraw.Draw(img)
    d.rectangle([x - 4, y - 4, x + 4, y + 4], fill=light + (255,))
    d.point((x, y), fill=heavy + (255,))
    frame = radar.RadarFrame(img, datetime.now(radar.ISRAEL), [(light, 0.2), (heavy, 50.0)])
    assert radar.render(s, frame).getpixel((48, 20)) == heavy


def test_color_levels_from_payload():
    payload = {"data": {"radar_colorbar": {"items": {"1": {"color": "#e10a12", "mark": "50"}}}}}
    assert radar.color_levels(payload) == [((225, 10, 18), 50.0)]
    assert radar.color_levels({}) == []


@pytest.mark.parametrize("day, expected", [
    (date(2026, 10, 1), True),   # first day
    (date(2026, 9, 30), False),  # day before
    (date(2027, 1, 15), True),   # winter, across New Year
    (date(2027, 5, 30), True),   # last day
    (date(2027, 5, 31), False),  # day after
    (date(2027, 7, 1), False),   # summer
])
def test_in_season(day, expected):
    assert radar.in_season(day) is expected


def test_parse_season():
    assert radar.parse_season("10-01:05-30") == ((10, 1), (5, 30))
    assert radar.in_season(date(2026, 6, 15), radar.parse_season("06-01:08-31"))  # non-wrapping
    for bad in ("10-01", "13-01:05-30", "10-32:05-30", "x"):
        with pytest.raises(ValueError):
            radar.parse_season(bad)



def payload_with(times):
    return {"data": {"types": {"IMSRadar": [
        {"forecast_time": f"2026-10-03 {t}:00", "file_name": f"/r/IMSRadar4GIS_{t.replace(':', '')}_0.png"}
        for t in times
    ]}}}


def test_recent_frames_are_newest_oldest_first():
    infos = radar.recent_frame_infos(payload_with(["01:20", "01:40", "01:30", "01:25", "01:35", "01:45"]), 5)
    assert [t.strftime("%H:%M") for _, t in infos] == ["01:25", "01:30", "01:35", "01:40", "01:45"]


def test_fetcher_downloads_only_new_frames(monkeypatch):
    import io as _io
    import json as _json
    times = ["01:20", "01:25", "01:30", "01:35", "01:40"]
    downloads = []
    png = _io.BytesIO()
    Image.new("RGBA", (940, 940)).save(png, "PNG")

    def fake_get(url, timeout=15):
        if url == radar.FRAMES_URL:
            return _json.dumps(payload_with(times)).encode()
        downloads.append(url)
        return png.getvalue()

    monkeypatch.setattr(radar, "_get", fake_get)
    f = radar.Fetcher()
    assert len(f.recent(5)) == 5 and len(downloads) == 5
    times.append("01:45")  # IMS publishes one more frame
    frames = f.recent(5)
    assert len(downloads) == 6  # only the new one was downloaded
    assert frames[-1].taken_at.strftime("%H:%M") == "01:45"
