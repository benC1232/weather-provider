import pytest

from weather_provider import __main__ as main, config


def write(path, complete):
    cfg = config.Config()
    cfg.location.latitude, cfg.location.longitude = 51.5, -0.12
    cfg.setup.complete = complete
    config.save(cfg, path)


@pytest.fixture
def setup_calls(monkeypatch):
    calls = []

    def fake_setup(argv):
        calls.append(argv)
        cfg = config.load(argv[1])
        cfg.setup.complete = True
        config.save(cfg, argv[1])

    monkeypatch.setattr(main.onboard, "main", fake_setup)
    monkeypatch.setattr(main.sys.stdin, "isatty", lambda: False)
    return calls


def settings(argv):
    return main.settings(*main.parse_args(argv))


def test_setup_runs_while_not_complete(tmp_path, setup_calls):
    path = tmp_path / "c.toml"
    write(path, complete=False)
    assert settings(["--config", str(path)]).setup.complete
    assert setup_calls == [["--config", str(path), "--defaults"]]  # no terminal: from the file


def test_setup_skipped_once_complete(tmp_path, setup_calls):
    path = tmp_path / "c.toml"
    write(path, complete=True)
    settings(["--config", str(path)])
    assert setup_calls == []


def test_no_config_without_terminal_is_an_error(tmp_path, setup_calls):
    with pytest.raises(SystemExit):
        settings(["--config", str(tmp_path / "missing.toml")])
    assert setup_calls == []


def test_flags_override_switches(tmp_path, setup_calls):
    path = tmp_path / "c.toml"
    write(path, complete=True)
    cfg = settings(["--config", str(path), "--no-radar", "--weather-only", "--no-label", "-v"])
    assert (cfg.radar.enabled, cfg.sign.left_panel, cfg.display.credits, cfg.display.verbose) \
        == (False, False, False, True)
