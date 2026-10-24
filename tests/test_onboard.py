import json

import pytest

from weather_provider import coast, config, forecast, onboard, radar


def test_scope_layout_matches_nw_default():
    home_x, home_y, km_per_px, rings = onboard.scope_layout("nw", 100)
    s = radar.Scope(0, 0)
    assert (home_x, home_y, rings) == (s.home_x, s.home_y, list(s.ring_km))
    assert km_per_px == pytest.approx(s.km_per_px, abs=0.02)


@pytest.mark.parametrize("direction", list(onboard.HOME_FOR_DIRECTION))
def test_home_is_on_the_panel(direction):
    x, y, _, _ = onboard.scope_layout(direction, 100)
    assert 0 <= x < radar.WIDTH and 0 <= y < radar.HEIGHT


def test_nearest_city_only_from_allowed():
    cities = [("1", "A", 32.0, 35.0), ("2", "B", 32.5, 35.0), ("3", "C", 33.0, 35.0)]
    assert onboard.nearest_city(cities, 32.1, 35.0)[:2] == ("1", "A")
    assert onboard.nearest_city(cities, 32.1, 35.0, {"2", "3"})[:2] == ("2", "B")


def test_parse_locations():
    payload = {"data": {"12": {"lid": "12", "name": "Town", "lat": "31.5", "lon": "35.0"},
                        "9": {"lid": "9", "name": "Broken", "lat": None, "lon": "35"}}}
    assert forecast.parse_locations(payload) == [("12", "Town", 31.5, 35.0)]


def test_simplify_drops_points_on_the_line():
    line = [(0, 0), (0, 0.5), (0, 1), (0.0001, 1.5), (0, 2), (1, 2)]
    assert coast.simplify(line) == [(0, 0), (0, 2), (1, 2)]


def test_coast_parse_save_load(tmp_path):
    payload = {"elements": [
        {"geometry": [{"lat": 32.0, "lon": 34.0}, {"lat": 32.1, "lon": 34.1}]},
        {"geometry": [{"lat": 32.0, "lon": 34.0}]},  # a single point isn't a line
    ]}
    lines = coast.parse(payload)
    path = tmp_path / "coast.json"
    coast.save(path, lines, (1, 2, 3, 4))
    data = json.loads(path.read_text())
    assert "ODbL" in data["license"] and "OpenStreetMap" in data["source"]
    assert coast.load(path) == [[[32.0, 34.0], [32.1, 34.1]]]
    assert coast.load(tmp_path / "missing.json") == []


def test_bbox_covers_the_panel():
    s = radar.Scope(31.5, 35.0)
    south, west, north, east = coast.bbox(s, radar.WIDTH, radar.HEIGHT)
    for x, y in [(0, 0), (radar.WIDTH, radar.HEIGHT)]:
        lat, lon = s.to_latlon(x, y)
        assert south < lat < north and west < lon < east


def test_setup_outside_israel_uses_open_meteo_only(tmp_path, monkeypatch):
    monkeypatch.setattr(onboard.openmeteo, "timezone_at", lambda lat, lon: "Europe/London")
    path = tmp_path / "config.toml"
    onboard.run(["--config", str(path), "--lat", "51.5", "--lon", "-0.12", "--defaults"])
    cfg = config.load(path)
    assert cfg.location.timezone == "Europe/London"
    assert not cfg.radar.enabled and cfg.ims.station is None and cfg.ims.location is None
    assert not (tmp_path / "coast.json").exists()


def test_setup_marks_itself_complete(tmp_path, monkeypatch):
    monkeypatch.setattr(onboard.openmeteo, "timezone_at", lambda lat, lon: "Europe/London")
    path = tmp_path / "config.toml"
    onboard.run(["--config", str(path), "--lat", "51.5", "--lon", "-0.12", "--defaults"])
    assert config.load(path).setup.complete is True


def test_setup_without_terminal_takes_the_config_file(tmp_path, monkeypatch):
    monkeypatch.setattr(onboard.openmeteo, "timezone_at", lambda lat, lon: "Europe/Paris")
    path = tmp_path / "config.toml"
    path.write_text('[location]\nlatitude = 48.85\nlongitude = 2.35\n[sign]\nserver = "http://sign:5001/frame"\n')
    onboard.run(["--config", str(path), "--defaults"])
    cfg = config.load(path)
    assert (cfg.location.latitude, cfg.sign.server) == (48.85, "http://sign:5001/frame")
    assert cfg.location.timezone == "Europe/Paris" and cfg.setup.complete


def test_setup_without_location_says_what_is_missing(tmp_path):
    with pytest.raises(SystemExit, match=r"latitude and longitude under \[location\]"):
        onboard.run(["--config", str(tmp_path / "c.toml"), "--defaults"])


def test_bad_direction_in_config_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(onboard.openmeteo, "timezone_at", lambda lat, lon: "Asia/Jerusalem")
    monkeypatch.setattr(onboard.forecast, "locations", lambda: [])
    monkeypatch.setattr(onboard.uvi, "location_ids", lambda: set())
    path = tmp_path / "c.toml"
    path.write_text('[location]\nlatitude = 31.5\nlongitude = 35.0\n[radar]\ndirection = "UP"\n')
    with pytest.raises(SystemExit, match="Direction"):
        onboard.run(["--config", str(path), "--defaults"])


def test_download_falls_back_to_the_next_server(monkeypatch):
    import io
    tried = []

    def fake_urlopen(req, timeout):
        tried.append(req.full_url)
        if len(tried) == 1:
            raise OSError("502 Bad Gateway")
        return io.BytesIO(json.dumps({"elements": []}).encode())

    monkeypatch.setattr(coast.urllib.request, "urlopen", fake_urlopen)
    assert coast.download((1, 2, 3, 4)) == []
    assert tried == coast.OVERPASS_URLS[:2]


def test_download_raises_when_every_server_fails(monkeypatch):
    def fail(req, timeout):
        raise OSError("busy")

    monkeypatch.setattr(coast.urllib.request, "urlopen", fail)
    monkeypatch.setattr(coast.time, "sleep", lambda s: None)
    with pytest.raises(OSError):
        coast.download((1, 2, 3, 4))
