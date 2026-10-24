# weather-provider

Draws the weather and rain radar for a 128×32 LED sign and posts them to
[sign-server](https://github.com/benC1232/sign-server) as two regions. It was built for a sign in Israel,
so there it uses the Israel Meteorological Service (IMS) station readings,
forecasts and rain radar; anywhere else it runs on
[Open-Meteo](https://open-meteo.com/) alone and shows the summer panel all year.
A first-run setup works out which sources apply to you.

**Weather panel** (40×32, right edge):
- **Temperature** on top, colored like Wikipedia's climate tables (blue at
  5 °C, white at 15 °C, orange in the high 20s, red at 41.5 °C). The cold end is
  squeezed compared to Wikipedia because the sign it was built for rarely sees
  freezing.
- **Humidity** along the bottom edge at the same size, with a drop icon.

**Radar scope** (88×32, left side), an old-style radar screen looking west
through north by default (see below):
- Home is the red dot; the gray line is the coastline (downloaded from
  OpenStreetMap at setup); range rings at 33, 67 and 100 km in different colors, with a legend down the left edge.
- Rain is copied from the latest IMS radar image, in IMS's own colors (blue and
  teal for light rain through green, yellow, red, and magenta for the heaviest).
- **Animated:** the 4 previous IMS frames (20 minutes) once each, then the
  current one 4 times, so the loop pauses on "now" and you can see which way
  the rain is moving. Images already downloaded are kept, so it still fetches
  only one new image from IMS every 5 minutes.
- If the newest radar frame is too old, the rain is left out and the rings turn
  gray, so "no data" doesn't look like "no rain".
- Only shown in the rain season, **Oct 1 to May 30** by default
  (`radar.season`). The rest of the year, and all year outside Israel, no
  radar is fetched and the left side shows the summer panel below.
- Home is placed so the scope sees furthest toward where your rain usually
  comes from; setup asks. The default is north-west (see below).

**Summer panel** (88×32, left side, outside the rain season):
- **Heat stress** (עומס חום) as IMS's level number, 0–5, next to the sun, in
  that level's color, using IMS's scale (index rounded): 0 none (white, under
  22), 1 light/קל (yellow, 22), 2 moderate/מתון (orange, 24), 3 medium/בינוני
  (red, 26), 4 heavy/כבד (dark red, 28), 5 extreme/קיצוני (magenta, 30+). The index is IMS's
  (temperature + wet-bulb temperature) / 2, calculated from the temperature
  and humidity on the weather panel, so it comes from the same source (IMS or
  Open-Meteo) and is credited the same way.
- **UV index** inside a sun icon, colored by IMS's UV scale: green (low, 1),
  yellow (moderate, 3), orange (high, 6), red (very high, 8), violet (extreme,
  11+). Gray at night when it's 0.
- UV is IMS's hourly UV forecast for your IMS forecast city for the current
  hour (the table on ims.gov.il's hourly UV page), fetched once a day while
  this panel is shown. No IMS station measures UV. Without an IMS city, it's
  Open-Meteo's current UV index. Heat stress or UV shows a dash when there's
  no data.
- On the left: today's **sunset** time (sunset icon) and today's **high**
  (thermometer-and-arrow icon), colored like the temperature on the weather
  panel. The high is IMS's forecast for your IMS city (fetched once a day,
  Open-Meteo's if IMS has none); the sunset comes from Open-Meteo.

The temperature and humidity come from the nearest IMS station (10-minute
readings, IMS API; needs a free API key). If there's no key or station, or its
newest reading is more than `ims_stale_minutes` old or can't be fetched,
Open-Meteo's is shown instead, and the credit changes from `IMS` to `OM` so
the sign always names the source on screen. Open-Meteo is fetched every time
anyway for today's high, sunset and UV.

## Which sources you get

| Where you are | Weather panel | Left panel | UV and today's high |
|---|---|---|---|
| Israel, with an IMS API key | nearest IMS station, Open-Meteo backup | radar in season, summer panel otherwise | IMS forecast city, Open-Meteo backup |
| Israel, no key | Open-Meteo | radar in season, summer panel otherwise | IMS forecast city, Open-Meteo backup |
| Anywhere else | Open-Meteo | summer panel all year | Open-Meteo |

## Why the scope looks north-west by default

Where the sign was built, ten rainy seasons (2015–2025) of hourly ERA5
precipitation at home and at 32 points 50 and 100 km around it showed rain
mostly arriving from the north-west (about 70% from WNW–NNW), not the
south-west. Home sits low on the panel (pixel 75,19) so the scope sees
furthest in that direction. With the earlier top-right placement only ~58% of
storms would have been on screen an hour before arriving, against ~97% now. ERA5 is coarse (25 km
grid, hourly), so treat the numbers as a comparison, not a forecast.

## Getting it running

You need a [sign-server](https://github.com/benC1232/sign-server) driving the sign, and either Docker
or Python 3.11+. It takes about five minutes.

### 1. Get the code

```sh
git clone https://github.com/benC1232/weather-provider.git
cd weather-provider
```

### 2. Fill in `config/config.toml`

```sh
cp config/config.example.toml config/config.toml
```

Everything is set in that one file, copied from
[`config/config.example.toml`](config/config.example.toml), and every setting
has a comment explaining it. On/off settings are
`true` or `false`. Before the first start, set:

| Setting | Needed | What to put |
|---|---|---|
| `[location]` `latitude`, `longitude` | **yes** | Your location in decimal degrees (north and east positive), e.g. `latitude = 31.5`. Remove the `#` in front of both lines. |
| `[sign]` `server` | if sign-server is elsewhere | Its frame URL. The default `http://localhost:5001/frame` is right when it runs on the same machine. |
| `[ims]` `api_key` | optional, Israel only | A free [IMS API key](https://ims.gov.il/en/ObservationDataAPI) for live readings from the nearest IMS station. Without one, readings come from Open-Meteo; the radar, UV and forecast high still come from IMS. |
| `[radar]` `direction` | optional, Israel only | Where most of your rain comes from: `N` `NE` `E` `SE` `S` `SW` `W` `NW`, or `ALL` to center home. Default `NW`. |
| `[radar]` `range_km`, `enabled`, `season` | optional | How far the scope reaches (default 100 km), turning the radar off (summer panel all year), or its season. |

Leave the rest alone, including `[setup] complete = false`: setup fills in the
time zone, the IMS station and forecast city, and the radar layout.

### 3. Start it

**With Docker** (recommended; starts again after a reboot or crash):

```sh
docker compose up -d --build
```

**Or with Python:**

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m weather_provider
```

From a terminal you can skip step 2: with no location in the config, setup asks
for everything. To start at boot without Docker, use the included systemd unit,
[`weather-provider.service`](weather-provider.service): set its `User=` and
paths, then

```sh
sudo cp weather-provider.service /etc/systemd/system/
sudo systemctl enable --now weather-provider
```

Use Docker or systemd, not both: two copies would fight over the sign.

### 4. Watch the first start

```sh
docker compose logs -f            # or: journalctl -u weather-provider -f
```

The first start runs setup, because `complete = false`. It:

1. looks up your time zone (Open-Meteo),
2. checks whether you're inside the IMS radar's coverage (Israel and around).
   Outside it, everything comes from Open-Meteo and the left panel shows heat
   stress and UV all year,
3. picks the nearest IMS station (with an API key) and the nearest IMS
   forecast city,
4. places home on the radar scope so it sees furthest toward `direction`,
5. downloads the coastline around you from OpenStreetMap into
   `config/coast.json`. The public servers are often busy; if it fails, every
   start tries again until it works,
6. writes all of that back into `config/config.toml` and sets
   `complete = true`, so later starts skip setup.

Then the panels appear on the sign, and the log shows each reading, e.g.
`IMS: 29.6°C 52%`. If you forgot the location, the log says
`set latitude and longitude under [location]`: fill it in, then
`docker compose restart`.

### 5. Later

- **Change a setting:** edit `config/config.toml`, then `docker compose restart`
  (or `sudo systemctl restart weather-provider`).
- **Run setup again**, e.g. after moving: set `complete = false` and restart. Or
  answer its questions yourself with `docker compose run --rm weather-provider setup`
  (`python -m weather_provider setup` without Docker), then restart.
- **Refresh the coastline:** add `setup --coast-only` to the same command.
- **Update:** `git pull`, then `docker compose up -d --build`.

### Keeping your config private

`config/config.toml` holds your location and API key, so it's gitignored:
only `config/config.example.toml` is in the repo.

The IMS key can also stay out of the file altogether: set `IMS_API_KEY` in the
environment (uncomment it in `docker-compose.yml`).

### Where the config lives

In order, the first that applies:

1. `--config <file>` or `$WEATHER_PROVIDER_CONFIG` (Docker sets this to
   `/config/config.toml`, which is the repo's `config/` folder),
2. `~/.config/weather-provider/config.toml`, if it exists: a place outside the
   repo for your private copy,
3. the repo's `config/config.toml` (your copy of the example).

`coast.json` is always next to the config.

## Options

Each option overrides its config setting for that run. Flags without a
value turn a `true`/`false` setting on or off.

| Option              | Config setting                 | Default                       | Meaning |
|---------------------|--------------------------------|-------------------------------|---------|
| `setup` (first word) |                               |                               | Run setup now, whatever `setup.complete` says |
| `--config`          |                                | see [Where the config lives](#where-the-config-lives) | Config file |
| `--lat`, `--lon`    | `location.latitude/longitude`  | (required)                    | Where to get the weather for |
| `--timezone`        | `location.timezone`            | (from setup)                  | Local time for "today", the season and sunset |
| `--server`          | `sign.server`                  | `http://localhost:5001/frame` | sign-server's frame URL |
| `--x`, `--y`        | `sign.x`, `sign.y`             | `88`, `0`                     | Top-left of the weather panel on the sign |
| `--fetch-minutes`   | `timing.fetch_minutes`         | `10`                          | How often to fetch the weather |
| `--radar-minutes`   | `timing.radar_minutes`         | `5`                           | How often to fetch the radar (IMS makes a new frame every 5 min) |
| `--post-seconds`    | `timing.post_seconds`          | `60`                          | How often to re-post the panels |
| `--stale-minutes`   | `timing.stale_minutes`         | `45`                          | Show dashes if no good reading for this long |
| `--ims-stale-minutes` | `timing.ims_stale_minutes`   | `45`                          | Use Open-Meteo when the newest IMS reading is older than this |
| `--radar-stale-minutes` | `timing.radar_stale_minutes` | `30`                       | Leave out rain older than this |
| `--radar-season`    | `radar.season`                 | `10-01:05-30`                 | Dates (inclusive) the radar is shown; summer panel otherwise |
| `--no-radar`        | `radar.enabled = false`        | `true`                        | Summer panel all year |
| `--weather-only`    | `sign.left_panel = false`      | `true`                        | Weather panel only, nothing on the left |
| `--no-label`        | `display.credits = false`      | `true`                        | Hide the source credits (the data terms expect them) |
| `-v`, `--verbose`   | `display.verbose = true`       | `false`                       | Debug logging |

Setup's own options: `--coast-only`, `--defaults` (don't ask; take everything
from the config, as it does without a terminal), and `--lat`, `--lon`,
`--direction` to answer those questions up front.


## Tests

```sh
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
```

## License

MIT, see [LICENSE](LICENSE). The data sources below have their own terms.

## Data sources and credit

- [Weather data by Open-Meteo.com](https://open-meteo.com/), licensed under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Values are rounded
  and rendered as pixels for display.
- Rain radar, weather observations and the UV and high forecasts: Israel
  Meteorological Service (IMS), www.ims.gov.il. The IMS is not responsible for
  the information or its use, and is not a party to its publication.
- Coastline: © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
  available under the [ODbL](https://opendatacommons.org/licenses/odbl/).
  The `coast.json` that setup writes is an extract of OSM coastline data,
  records its source and license inside the file, and stays under the ODbL.

What each source's terms require, and how this project meets them, is in
[docs/COMPLIANCE.md](docs/COMPLIANCE.md).
