# Data source terms — what they require of this project

Plan: **IMS** (Israel Meteorological Service) station observations as the
primary source, with **Open-Meteo** as the backup that IMS §10 requires.

**Current state (2026-10-24):** temperature and humidity come from the **IMS
station in the config** (API; setup picks the nearest), with **Open-Meteo** shown instead when there's no key or
station, the newest IMS reading is over 45 minutes old, or the fetch fails.
Outside the rain season the UV index is **IMS's hourly UV forecast** for the
configured IMS city, read once a day from the table behind ims.gov.il's hourly
UV page (`/he/uvi_hourly`), and today's high is IMS's forecast for that city
(`/he/full_forecast_data/<id>`), also once a day; both are credited `IMS`.
Without an IMS city, both are Open-Meteo's and credited `OM`. Setup also reads
IMS's station list (API) and forecast city list (`/en/locations_info`) once,
to pick the nearest. Outside Israel no IMS data is used at all.
Apart from the radar, those are the only data taken from the IMS website. The
**rain radar is IMS data** (the radar images on ims.gov.il's radar page), so the
IMS obligations already apply to it. The coastline on the radar is
**OpenStreetMap** data (ODbL, section at the end). Each source's conditions are
below.

This is a working summary, not legal advice. The saved copies in `docs/` are
the authority; re-check them if either source publishes a newer version.

## Rules that apply whenever data is on the sign

- The credit in the screen's top-left corner names exactly the sources whose
  data is on screen: `IMS` while radar rain is shown, `OM` while Open-Meteo
  readings are shown. Never show IMS's label on Open-Meteo data or the reverse.
- The README carries the full credit text for both sources (below).

---

# IMS (primary)

Source: [`ims-terms-of-use-2026-01-07.pdf`](ims-terms-of-use-2026-01-07.pdf),
"Rights and terms of use of the Israel Meteorological Service website and in
the information that is provided by the Israel Meteorological Service",
dated 07.01.26, downloaded 2026-10-02 from
<https://ims.gov.il/sites/default/files/2026-03/Rights%20and%20terms%20of%20use%2007.01.26_0.pdf>.

## Obligations

| § | Requirement | How weather-provider meets it |
|---|-------------|-------------------------------|
| 2 | Data may be copied, displayed and used for derivative works, subject to the rest of the terms. | Showing IMS readings on the sign is allowed use. |
| 3 | **Credit IMS in a conspicuous, visible place**, without misrepresenting IMS, and state that **IMS is not liable for the information and is not a party to its publication**. Not required only if the data is processed so it can't be recovered without substantial effort; a temperature shown as a number is directly recoverable, so this applies. | The sign shows an `IMS` source label whenever IMS data is on screen. The full credit and disclaimer text is in the README. |
| 4 | The user is solely responsible for its use, and must check accuracy, completeness, timeliness and suitability. Suspected errors may be reported to IMS. | Readings are sanity-checked (plausible range, observation timestamp) before display; implausible values are dropped and logged. |
| 5–8 | IMS and the State accept no liability for the data or for any damage from using it; the user may not make claims against them. | Nothing to implement. Covered by the disclaimer in the README. |
| 9 | IMS may change or stop the data, its format, or access, without notice. | Treat the API response format as unstable: parse defensively and fail closed (show nothing or a fallback), never crash. |
| 10 | **A continuous service must have its own monitoring** for missing or late data, **and a backup mechanism** for when data isn't received or is late. Users are invited to tell IMS about disruptions. | Track each observation's timestamp; if it is older than a threshold, or fetches fail, log it and switch to Open-Meteo (below), labelled `OM` so it isn't presented as IMS data. |
| 11 | Any breach lets IMS cut off access immediately. | Keep this file in sync with the code. |
| 12 | Personal details given to IMS are kept under the Protection of Privacy Law. | Nothing to implement. |
| 13 | Official State publications override the website/API data where they differ. | Nothing to implement. |
| 14 | The website uses cookies. | Not relevant to API use. |

## Signed commitment

The last page is a letter of commitment to these terms, written for a company
signatory (ID no., private company no., address, email, signature). IMS
probably requires it when you request API access. As an individual, ask IMS
whether you can sign it personally.

## Not covered by the IMS document

- **API rate limits or token conditions.** Those come with the token (if at
  all) and should be added here when received.
- **Keeping the token secret.** Never commit it; it goes in an untracked config
  or environment variable.

## IMS credit text (for the README)

> Weather observations: Israel Meteorological Service (IMS), www.ims.gov.il.
> The IMS is not responsible for the information or its use, and is not a party
> to its publication.

---

# Open-Meteo (backup)

Source: snapshots of <https://open-meteo.com/en/terms> and
<https://open-meteo.com/en/licence>, fetched 2026-10-02:
[`open-meteo-terms-2026-10-02.txt`](open-meteo-terms-2026-10-02.txt),
[`open-meteo-licence-2026-10-02.txt`](open-meteo-licence-2026-10-02.txt).
Open-Meteo says changes to its terms take effect on posting and are tracked on
GitHub.

## Obligations

| Requirement | How weather-provider meets it |
|-------------|-------------------------------|
| **Free API is non-commercial only.** "Personal home automation" is listed as qualifying; subscriptions, ads, or commercial products are not. | A personal home sign. If this ever becomes commercial, it needs a paid plan. |
| **Rate limits:** under 10,000 calls/day, 5,000/hour, 600/minute (and 300,000/month). Misuse can get an IP blocked without notice. | Called once per `--fetch-minutes` (10 by default), about 150 calls/day, for the backup reading and the sunset. |
| **CC BY 4.0:** give appropriate credit, link to the licence, indicate if changes were made, and don't imply endorsement. Open-Meteo asks for a link "next to any location Open-Meteo data are displayed", e.g. "Weather data by Open-Meteo.com". | A 128×32 LED panel can't hold a link, so the sign shows an `OM` label (CC BY allows credit "in any reasonable manner" for the medium). The README carries the full credit, licence link and change note. |
| No warranty: Open-Meteo accepts no responsibility for accuracy, availability or losses. | Same defensive handling as IMS: sanity-check values, never crash. |

Open-Meteo's data comes from national weather services (DWD, ECMWF, NOAA,
Met Norway, etc.) and, for air quality, from Copernicus (CAMS). Those
upstream licences are listed on the licence page; crediting Open-Meteo as
asked is how its CC BY licence expects downstream users to comply.

## Open-Meteo credit text (for the README)

> Backup weather data: [Weather data by Open-Meteo.com](https://open-meteo.com/),
> licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
> Values are rounded and rendered as pixels for display.

---

# OpenStreetMap (coastline)

Source: `coast.json` beside the config, OSM `natural=coastline` ways for the
area the radar scope shows, downloaded by setup via the Overpass API (one query
per setup; Overpass asks for light use). Nothing from OSM ships in the repo.

| Requirement | How weather-provider meets it |
|-------------|-------------------------------|
| **ODbL 1.0 attribution:** credit "© OpenStreetMap contributors" and make clear the data is under the ODbL. | Credited in the README. The coastline drawn on the sign is a Produced Work; OSM's attribution guidelines accept credit in a reasonable place for the medium, and a 128×32 sign has no room. |
| **Share-alike for the data:** a database derived from OSM stays under the ODbL. | `coast.json` records its source, query and license inside the file and stays under the ODbL. |
