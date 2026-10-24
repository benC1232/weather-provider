from datetime import datetime, timezone

import pytest

from weather_provider import ims


def channel(name, value, valid=True):
    return {"id": 0, "name": name, "alias": None, "value": value,
            "status": 1 if valid else 2, "valid": valid, "description": None}


def payload(td=21.1, rh=68.0, **kw):
    channels = [channel("WS", 1.4), channel("TD", td, kw.get("td_valid", True)),
                channel("RH", rh, kw.get("rh_valid", True)), channel("TW", -999.0, False)]
    return {"stationId": 43, "data": [{"datetime": "2026-10-05T20:50:00+03:00", "channels": channels}]}


NOW = datetime(2026, 10, 5, 19, 30, tzinfo=timezone.utc)  # 22:30 in Israel


def test_parse():
    r = ims.parse(payload(), NOW)
    assert (r.temperature_c, r.humidity_pct, r.source) == (21.1, 68.0, "IMS")
    # Labelled 20:50+03:00, but IMS means winter time: 20:50+02:00.
    assert r.observed_at == datetime(2026, 10, 5, 18, 50, tzinfo=timezone.utc)
    assert r.max_temp_c is None and r.sunset is None


def test_observed_time_trusts_label_if_winter_time_is_in_the_future():
    # 22:20+03:00 read as +02:00 would be 23:20 Israel time, an hour from now.
    t = ims.observed_time("2026-10-05T22:20:00+03:00", NOW)
    assert t == datetime(2026, 10, 5, 19, 20, tzinfo=timezone.utc)


def test_observed_time_in_winter_is_unchanged():
    t = ims.observed_time("2026-12-05T10:00:00+02:00", datetime(2026, 12, 5, 9, tzinfo=timezone.utc))
    assert t == datetime(2026, 12, 5, 8, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize("kw", [{"td_valid": False}, {"rh_valid": False}, {"td": -999.0}, {"rh": 140}])
def test_parse_rejects_bad_readings(kw):
    with pytest.raises(ValueError):
        ims.parse(payload(**kw), NOW)


def test_parse_rejects_missing_channel():
    p = payload()
    p["data"][0]["channels"] = [c for c in p["data"][0]["channels"] if c["name"] != "RH"]
    with pytest.raises(ValueError):
        ims.parse(p, NOW)


def station(sid, lat, lon, monitors=("TD", "RH"), active=True):
    return {"stationId": sid, "name": f"S{sid}", "active": active,
            "location": {"latitude": lat, "longitude": lon},
            "monitors": [{"name": m, "active": True} for m in monitors]}


def test_nearest_station_needs_temperature_and_humidity():
    stations = [
        station(1, 31.00, 35.00, monitors=("TD",)),  # closest, but no humidity
        station(2, 31.00, 35.01, active=False),
        station(3, 31.10, 35.10),
        station(4, 31.70, 35.50),
    ]
    st, km = ims.nearest_station(stations, 31.00, 35.00)
    assert st["stationId"] == 3 and 10 < km < 20
    assert ims.nearest_station([], 31.0, 35.0) is None


def test_distance_km():
    assert ims.distance_km(0, 0, 0, 1) == pytest.approx(111.2, rel=0.01)
