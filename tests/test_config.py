import os

import pytest

from weather_provider import config


def test_missing_file_is_none(tmp_path):
    assert config.load(tmp_path / "nope.toml") is None


def test_round_trip(tmp_path):
    cfg = config.Config()
    cfg.location.latitude, cfg.location.longitude = 31.5, 35.0
    cfg.location.timezone = "Asia/Jerusalem"
    cfg.ims.api_key, cfg.ims.station, cfg.ims.location = 'k"ey', 43, 3
    cfg.radar.rings_km = [10, 20, 30]
    path = tmp_path / "sub" / "config.toml"
    config.save(cfg, path)
    assert os.stat(path).st_mode & 0o777 == 0o600
    back = config.load(path)
    assert back.location == cfg.location
    assert back.ims == cfg.ims
    assert back.radar == cfg.radar
    assert back.coastline_path() == tmp_path / "sub" / "coast.json"


def test_unset_values_are_commented_out(tmp_path):
    text = config.dumps(config.Config())
    assert "\n# latitude =" in text and "\n# station =" in text
    assert 'server = "http://localhost:5001/frame"' in text
    assert "complete = false" in text
    path = tmp_path / "c.toml"
    path.write_text(text)
    assert config.load(path).location.latitude is None


def test_every_setting_has_docs():
    from dataclasses import fields
    for section in config.SECTIONS:
        assert section in config.SECTION_DOCS
        for f in fields(getattr(config.Config(), section)):
            assert f"{section}.{f.name}" in config.SETTING_DOCS


def test_defaults_fill_in(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text("[location]\nlatitude = 1.5\nlongitude = 2.5\n")
    cfg = config.load(path)
    assert cfg.location.latitude == 1.5
    assert cfg.timing.fetch_minutes == 10 and cfg.sign.x == 88


@pytest.mark.parametrize("text", ["[nope]\na = 1\n", "[sign]\nport = 1\n"])
def test_unknown_settings_raise(tmp_path, text):
    path = tmp_path / "c.toml"
    path.write_text(text)
    with pytest.raises(ValueError):
        config.load(path)


def test_environment_key_wins(monkeypatch):
    cfg = config.Config()
    cfg.ims.api_key = "from-file"
    monkeypatch.setenv("IMS_API_KEY", "")
    assert cfg.ims_api_key == "from-file"
    monkeypatch.setenv("IMS_API_KEY", " from-env ")
    assert cfg.ims_api_key == "from-env"
    cfg.ims.api_key = ""
    monkeypatch.delenv("IMS_API_KEY")
    assert cfg.ims_api_key is None


def test_shipped_config_is_a_blank_template():
    cfg = config.load(config.EXAMPLE_PATH)
    assert cfg.location.latitude is None and cfg.location.longitude is None
    assert cfg.ims.api_key == "" and cfg.ims.station is None
    assert cfg.setup.complete is False  # a new install runs setup on first start


def test_default_path(monkeypatch, tmp_path):
    monkeypatch.delenv("WEATHER_PROVIDER_CONFIG", raising=False)
    monkeypatch.setattr(config, "USER_PATH", tmp_path / "home" / "config.toml")
    assert config.default_path() == config.REPO_PATH  # nothing in ~/.config: the repo's
    config.USER_PATH.parent.mkdir()
    config.USER_PATH.write_text("")
    assert config.default_path() == config.USER_PATH  # ~/.config wins once it exists
    monkeypatch.setenv("WEATHER_PROVIDER_CONFIG", str(tmp_path / "x.toml"))
    assert config.default_path() == tmp_path / "x.toml"
