import pytest

from weather_provider import forecast

# Trimmed from https://ims.gov.il/he/full_forecast_data/<id> (2026-10-05).
PAYLOAD = {"data": {
    "2026-10-05": {"country": {}, "daily": {"lid": "12", "maximum_temperature": "28", "minimum_temperature": "21"}},
    "2026-10-06": {"daily": {"lid": "12", "maximum_temperature": "27"}},
    "2026-10-07": {"daily": {"lid": "12"}},  # no high: skipped
    "2026-10-08": {"daily": {"lid": "12", "maximum_temperature": "99"}},  # implausible: skipped
}, "method": "GET"}


def test_parse():
    assert forecast.parse(PAYLOAD) == {"2026-10-05": 28.0, "2026-10-06": 27.0}


@pytest.mark.parametrize("bad", [
    {"data": {}},
    {"data": {"2026-10-05": {"daily": {"maximum_temperature": "x"}}}},
    {"nothing": 1},
])
def test_parse_rejects_bad_payloads(bad):
    with pytest.raises((KeyError, ValueError)):
        forecast.parse(bad)
