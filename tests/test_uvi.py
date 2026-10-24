from datetime import datetime

import pytest

from weather_provider import uvi

# Trimmed from https://ims.gov.il/he/uvi_hourly (2026-10-05).
PAYLOAD = {"data": {"text": "<p>...</p>", "locations": {
    "1": {"2026-10-05": {"12": "7"}},
    "12": {
        "2026-10-05": {"7": "0", "8": "1", "12": "7", "13": "7", "20": "0"},
        "2026-10-06": {"12": "6"},
    },
}}, "method": "GET"}


def test_parse_picks_the_location():
    table = uvi.parse(PAYLOAD, "12")
    assert table["2026-10-05"][12] == 7
    assert table["2026-10-06"] == {12: 6}


@pytest.mark.parametrize("when, uv", [
    (datetime(2026, 10, 5, 12, 45), 7),  # the hour it's in
    (datetime(2026, 10, 5, 8, 0), 1),
    (datetime(2026, 10, 5, 3, 0), 0),    # night: not in the table
    (datetime(2026, 10, 6, 12, 5), 6),
    (datetime(2026, 10, 9, 12, 0), None),  # day not covered
])
def test_at(when, uv):
    assert uvi.at(uvi.parse(PAYLOAD, "12"), when) == uv


def test_at_without_table():
    assert uvi.at(None, datetime(2026, 10, 5, 12)) is None


@pytest.mark.parametrize("bad", [
    {"data": {"locations": {"1": {}}}},                                  # no such location
    {"data": {"locations": {"12": {}}}},                                  # empty
    {"data": {"locations": {"12": {"2026-10-05": {"12": "x"}}}}},         # not a number
    {"data": {"locations": {"12": {"2026-10-05": {"12": "40"}}}}},        # implausible
    {"data": {"locations": {"12": {"05/10/2026": {"12": "7"}}}}},         # date format
])
def test_parse_rejects_bad_tables(bad):
    with pytest.raises((KeyError, ValueError)):
        uvi.parse(bad, "12")
