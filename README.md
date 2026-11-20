# Bangkok PM2.5 and PM10 Forecast

A pipeline that collects public air quality and weather data, forecasts PM2.5, PM10, temperature and humidity for Bangkok, and serves the forecast through a dashboard, a JSON API and Power BI. GitHub Actions runs it every day; nothing runs on a server of its own.

It forecasts the next seven days as daily means (city-wide and for 20 reference stations) with a range and the chance of going above the Thai PM2.5 standard, each hour to the end of tomorrow, and the next three calendar months as monthly means. Each station has its own page on the dashboard. The results so far are summarised in [docs/results.md](docs/results.md).

## Architecture

```mermaid
flowchart LR
    subgraph SRC["Public sources"]
        OA["OpenAQ<br/>Air4Thai stations, hourly"]
        OM["Open-Meteo<br/>weather, past forecasts, CAMS"]
        FI["NASA FIRMS<br/>fires"]
        TM["TMD and GISTDA<br/>reference forecasts"]
    end
    subgraph GA["GitHub Actions"]
        D["Daily forecast, 07:17<br/>backfill, quality check, train weekly,<br/>predict, report, score, load SQL"]
        H["Hourly update, 13:03 and 19:03<br/>newer station hours"]
        HC["Health check, 10:37, 14:37, 20:37"]
    end
    SRC --> D
    OA --> H
    D <--> DB[("data branch<br/>bronze, silver, gold CSV and JSON,<br/>models, metrics")]
    H <--> DB
    DB --> HC
    HC -->|"problem"| IS["GitHub issue<br/>emails the owner"]
    D --> SQL[("Azure SQL<br/>bronze, silver, gold, views")]
    SQL -->|"refresh 10:00"| PBI["Power BI report"]
    DB --> WEB["Dashboard<br/>Next.js static, App Service and Blob"]
    DB --> API["JSON API<br/>Azure Functions"]
    D --> FB[("Firebase<br/>/predictions")]
```

Every job reads the `data` branch, adds to it and writes it back as a single commit, so the branch is the only state. The dashboard and the API read it directly, so a new forecast appears without a deploy. Azure is optional: without it, the forecast, the dashboard on GitHub Pages and the JSON on the `data` branch keep working.

| Time (Bangkok) | Job | What it does |
|---|---|---|
| 07:17 | Daily forecast | Fetches missing hours, checks data quality, retrains weekly, forecasts, scores past forecasts, loads Azure SQL |
| 10:00 | Power BI refresh | Imports the views from Azure SQL |
| 10:37 | Health check | Opens a GitHub issue if any output is missing or stale |
| 13:03 | Hourly update | Repeats the hourly forecast with station hours up to 09:00, adds TMD values the morning missed |
| 14:37 | Health check | Also checks that the afternoon hourly update used hours up to 09:00 |
| 19:03 | Hourly update | Repeats it again with hours up to 16:00 |
| 20:37 | Health check | Also checks that the evening hourly update used hours up to 16:00 |

| Module | Responsibility |
|---|---|
| `pm25.ingest` | Fetches only the hours missing locally, stores them as UTC CSV, never duplicates a row |
| `pm25.features` | Builds daily targets and features that only use information known at forecast time |
| `pm25.evaluate` | Walk-forward splits, metrics and the promotion gate |
| `pm25.train` | Compares models with baselines and decides what each forecast slot publishes |
| `pm25.predict` | Builds the forecast document |
| `pm25.publish` | Writes the document to Firebase in one atomic request |
| `pm25.hourly` | Hourly city forecast for the morning, afternoon and evening runs |
| `pm25.station_model` | Pooled per-station forecasts for seven days |
| `pm25.monitor` | Scores every published forecast against what was measured |
| `pm25.warehouse` | Loads the layers into Azure SQL and reads back what it holds |
| `pm25.health` | Decides whether today's outputs are fresh and trustworthy |

## Live dashboard

![The dashboard: today's values, the seven-day table, the hourly chart switched to PM10, the station map for tomorrow and in six days, a station's popup, and the live accuracy page](docs/media/dashboard-demo.gif)

- Main: https://app-pm25-forecast-1716.azurewebsites.net (Azure App Service, free F1 plan)
- Backup: https://stpm25webd0b881.z23.web.core.windows.net (Azure Blob Storage static website)

Pages: the forecast with Thai air quality colours (PCD scale) and a station map, `/station/?id=<location>` for one station (its last 14 days, its seven-day forecast and how its forecasts have done, linked from the map), and `/accuracy/` with live accuracy. Both have Thai and English text (`?lang=th` or `?lang=en`, or the switch at the top).

Both sites serve the same Next.js static export from `web/` (TypeScript, React, Chart.js). The page is plain files with no server, and it fetches the `data` branch in the browser, so each morning's forecast appears without a rebuild. Types in `web/lib/types.ts` mirror the forecast document, so a schema change on the Python side fails the TypeScript build. `deploy-dashboard-pages.yml` publishes the same build to GitHub Pages once Azure is removed.

To work on the dashboard locally:

```bash
cd web
npm ci
npm run dev      # http://localhost:3000
npm test
npm run build    # static files in web/out
```

## API

A read-only JSON API runs on Azure Functions (TypeScript, `api/`). It serves the same files as the dashboard from the `data` branch, cached for 10 minutes, with CORS open to any site.

Base URL: https://func-pm25-api-d0b8.azurewebsites.net/api

| Endpoint | Returns |
|---|---|
| `/help` | The list of endpoints |
| `/forecast` | The next seven days, the next three months, and each station |
| `/hourly` | Hourly PM2.5 and PM10 to 23:00 tomorrow: from 04:00 after the morning run, from 10:00 after the afternoon update, from 17:00 after the evening update |
| `/measured?target=pm25&from=2026-11-01&to=2026-11-12` | Measured Bangkok daily values; `target` is `pm25`, `pm10`, `temp_c` or `rh_pct` |
| `/forecasts?target=pm25&label=tomorrow&from=…&to=…` | Every published daily forecast in the range; labels `today`, `tomorrow`, `day2` to `day6` |
| `/accuracy` | Live accuracy over 7, 30 and 90 days |
| `/stations` | Daily values per reference station for the last 14 days |

Ranges default to the last 30 days and can cover at most 400 days. Bad parameters return 400 with a message. `.github/workflows/deploy-api.yml` tests, builds and deploys on every change to `api/`. After Azure ends, the same JSON stays available directly from the `data` branch on raw.githubusercontent.com.

## Azure resources

Everything lives in one resource group, `rg-pm25-forecast`, on an Azure for Students subscription, so it can be deleted in one step without affecting the pipeline.

| Resource | Purpose | Cost |
|---|---|---|
| Azure SQL Database, free tier, serverless | Warehouse with `bronze`, `silver` and `gold` schemas and views for Power BI | Free; pauses instead of billing when the monthly allowance is used |
| App Service plan F1 and web app | Main dashboard | Free |
| Storage account, static website | Backup dashboard, and the Functions deployment package | Free for 12 months, then a few cents |
| Function app, Flex Consumption (`func-pm25-api-d0b8`) | Public read-only API, at most 10 instances of 512 MB, no Application Insights | Monthly free grant of 250,000 executions and 100,000 GB-s per subscription |
| User-assigned managed identity | GitHub Actions signs in with OIDC, scoped to these resources only | Free |

The database accepts Microsoft Entra sign-in only. CI opens the SQL firewall for its own address during the load and removes the rule afterwards. Azure steps never block the forecast or the Firebase publish.

## Data

| Source | Role | Data | Access |
|---|---|---|---|
| OpenAQ, Air4Thai reference monitors | Forecast target | Hourly PM2.5 at 20 stations and PM10 at 8; the city value uses a fixed panel of 10 and 3 of them | Free API key |
| Open-Meteo Air Quality | Feature | PM2.5, NO2, O3, SO2 and CO from the CAMS global model | No key |
| Open-Meteo Historical Weather | Feature, and the target for temperature and humidity | Temperature, humidity, precipitation and wind from 2021 | No key |
| TMD Weather Forecast API | Reference shown next to our forecast | Hourly temperature and humidity forecast, 3 km model | Free token |
| Open-Meteo Previous Runs (JMA model) | Feature | The weather forecast for the target day as it was issued one to seven days before: temperature, humidity, rain, wind, pressure and cloud, from 2021 | No key |
| Open-Meteo Air Quality forecast (CAMS) | Archived for later | Each morning's CAMS PM2.5 forecast for today and tomorrow, saved to `bronze/cams_forecast_archive.csv` | No key |
| GISTDA PM2.5 (pm25.gistda.or.th) | Reference shown next to our forecast | Bangkok hourly and 24-hour average PM2.5 estimated from satellite data and a model | No key; the website's own endpoint, no published API contract, so an outage only drops the reference |
| NASA FIRMS (VIIRS NOAA-20) | Feature, optional | Daily fire detection count and total fire radiative power in a box over central Thailand, western Cambodia and the Myanmar border (97.5–105.5 E, 11.5–17.5 N) | Free MAP_KEY |

The daily target is the median across a fixed panel of stations, so one faulty station cannot move it. A station-day needs 18 hours of data, and a city-day needs at least 5 PM2.5 stations or 2 PM10 stations. Days are Bangkok local days. Gaps in the measured target are never filled with model data.

Ten more Air4Thai stations (five with PM10) were added on 19 November 2026 for the station map and the per-station models. Each reported on at least 90 % of days over the previous year. They are kept out of the city median, so the city series the daily models learn from is unchanged.

Modelled PM10 from Open-Meteo is not used, because its ratio to PM2.5 changes abruptly in November 2024.

The target-day weather forecast uses the Previous Runs API, which returns each hour as forecast one or two days earlier, so training never sees hindsight. Today's forecast uses runs from one day before and tomorrow's from two days before; both runs exist before the 07:17 job starts. Past CAMS air quality forecasts are not available anywhere free, so the pipeline archives them from now on, to be tested as a feature once about a year has built up.

Fire detections are stored as hourly totals (count and FRP), not single detections, so the file stays small. Archive (standard processing) data is used where it exists and near real time data after it. Days that were never fetched stay missing rather than zero. The fire features only reach a published forecast if a model trained with them passes the promotion gate. Each promoted model records its feature list, so models saved before the fire features existed keep working.

## Run locally

### Requirements

Python 3.12 or newer. Library versions are pinned in `requirements.txt`, so every install gets the same versions.

| Library | Used for |
|---|---|
| pandas, numpy | Data handling |
| scikit-learn, joblib | Models and saving them |
| matplotlib | Evaluation plot and PDF report |
| requests | Calls to OpenAQ, Open-Meteo and Firebase |
| google-auth | Service account login for Firebase publishing |
| pytest | Tests (`requirements-dev.txt`) |

### Install

macOS or Linux:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pip install -e . --no-deps
pytest
```

Windows (PowerShell):

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
pip install -e . --no-deps
pytest
```

If PowerShell refuses to run the activation script, allow local scripts for your user once:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

The last install line makes the `pm25` package and its `python -m pm25` commands available. On macOS and Linux, `make install` and `make test` do the same.

### Run

Create your settings file, then open `.env` and fill in the values. Commands read `.env` automatically, so there is nothing to load by hand.

macOS or Linux:

```bash
cp .env.example .env
```

Windows (PowerShell):

```powershell
Copy-Item .env.example .env
```

Then run the pipeline with the virtual environment active. These commands are the same on every platform:

```bash
python -m pm25 backfill
python -m pm25 train
python -m pm25 predict
python -m pm25 report
python -m pm25 monitor   # score published forecasts against measurements
python -m pm25 health    # exit 1 if today's outputs are stale or failing
python -m pm25 publish
```

`publish` is optional and needs Firebase credentials. On macOS and Linux, `make pipeline` runs backfill, train, predict and report in one go. Values already set in the shell or in CI take priority over `.env`.

The first OpenAQ load takes about 30 minutes because requests are paced for the free tier. Later runs only fetch new hours.

## Automation

`.github/workflows/daily-forecast.yml` runs the pipeline every morning and can also be started by hand (`workflow_dispatch`).

| Setting | Value |
|---|---|
| Schedule | 00:17 UTC, which is 07:17 in Bangkok; GitHub may start it some minutes late |
| Overlap | A concurrency group stops two runs overlapping |
| Timeout | 120 minutes, for the first load of a new data source |
| State | Data, models and reports live on a `data` branch that always holds a single commit |
| Daily report | Markdown, CSV and PDF in the run summary and the `daily-report-<date>` artifact, kept 30 days |
| Report history | `reports/<date>.md` and `reports/forecast_history.csv` on the `data` branch |
| Model artifacts | Model, registry and metrics, kept 7 days |

Repository secrets: `OPENAQ_API_KEY`, `TMD_API_TOKEN` (optional), `FIRMS_MAP_KEY` (optional), `FIREBASE_DB_URL` and `FIREBASE_SERVICE_ACCOUNT_JSON` (the JSON key of a service account with the Firebase Realtime Database Admin role).

### Live accuracy and alerts

`python -m pm25 monitor` runs after the report. It joins every published daily forecast in `gold/forecast_history.csv` with the measured value once it exists, and compares it with persistence as it stood on the day the forecast was issued. It writes `gold/live_accuracy.csv` (one row per scored forecast) and `gold/live_accuracy_summary.json` (MAE, persistence MAE, skill and range coverage over 7, 30 and 90 days). If the published forecast for a target is worse than persistence over 30 days with at least 14 scored days, the summary carries an alert.

The hourly forecast and the per-station forecasts are scored the same way. Each run appends them to `gold/hourly_forecast_history.csv` and `gold/station_forecast_history.csv`; `monitor` writes `gold/live_accuracy_hourly.csv` and `gold/live_accuracy_stations.csv` and adds `hourly` and `stations` sections to the summary. The hourly baseline is the same hour of the previous day as known at 03:00; the station baseline is the station's own last measured day. The afternoon hourly update, hourly PM10 and the PM10 station forecasts are scored separately, as `hourly_afternoon`, `hourly_pm10`, `hourly_pm10_afternoon` and `stations_pm10`.

`.github/workflows/health-check.yml` runs at 10:37, 14:37 and 20:37 Bangkok time on the `data` branch. It raises an alert when no forecast was published today, the newest complete station day is more than two days old, the data quality gate failed, the live accuracy summary carries an alert, today's hourly forecast (with PM10) is missing or uses older hours than the run due by then (03:00 in the morning, 09:00 after 14:30, 16:00 after 20:30), or no station has a forecast for one of the seven days. The live accuracy summary alerts when a published forecast is worse than persistence over 30 days, and when an 80 % range (city, station or hourly) held fewer than 65 % of outcomes over the last 30 days with at least 14 days scored. An alert opens a GitHub issue labelled `pipeline-health` (or comments on the open one), which emails the repository owner; the next healthy run closes it. GitHub also emails the owner when a scheduled run fails.

`python -m pm25 alert` is a scaffold for public alerts when tomorrow's PM2.5 is above the Thai standard. See [docs/alerts.md](docs/alerts.md).

Cost and limits for a public repository: GitHub-hosted standard runners are free with no minute limit. Scheduled runs can start late when GitHub is busy, and GitHub disables schedules in public repositories after 60 days without repository activity. Artifacts can be kept up to 90 days; this workflow keeps them 7.

Recommended Realtime Database rules, which let anyone read forecasts and nobody write except the service account:

```json
{
  "rules": {
    ".read": false,
    ".write": false,
    "predictions": { ".read": true, ".write": false }
  }
}
```

## Forecast document

`/predictions/latest` and `/predictions/history/<date>` hold the same document:

```json
{
  "schema_version": 1,
  "as_of": "2026-11-11",
  "latest_data_date": "2026-11-10",
  "data_age_days": 0,
  "status": "ok",
  "units": "ug/m3",
  "daily": [
    {"date": "2026-11-12", "label": "tomorrow", "pm25": 21.1, "pm25_low": 13.7, "pm25_high": 28.5, "pm25_method": "random_forest", "pm10": 34.6, "...": "..."}
  ],
  "monthly": [
    {"month": "2026-12", "months_ahead": 1, "pm25": 30.0, "pm25_low": 25.0, "pm25_high": 35.0, "pm25_method": "climatology", "...": "..."}
  ]
}
```

`status` becomes `stale` and values become `null` when the latest station data is older than the forecast origin. The range covers 80 % of past out-of-sample errors.

## Model card

### What each forecast uses

Each target and horizon is a slot. A slot publishes a fitted model only after the model passes the promotion gate; otherwise it publishes the best baseline. The gate runs daily, so the published method can change. The table shows the run of 2026-11-11.

| Slot | Published method |
|---|---|
| PM2.5 today | Gradient boosting |
| PM2.5 tomorrow | Random forest |
| PM10 today and tomorrow | Random forest |
| Temperature and humidity today | Persistence (yesterday's value) |
| Temperature and humidity tomorrow | Random forest |
| Monthly PM2.5 and PM10, 1 to 3 months ahead | Climatology (mean of the same calendar month) |
| Monthly temperature and humidity | Climatology or damped anomaly, whichever passes the gate |

Temperature and humidity are trained and scored against Open-Meteo history from 2021, which is a model reanalysis and not a station measurement. Compared with station records from 2023 to 2026, it reads about 1 °C cooler than central Bangkok. Measured temperature that is free and updated daily was not found.

The Thai Meteorological Department (TMD) forecast for today and tomorrow is published next to ours as `tmd_*` fields. It is an independent 3 km weather model, and its accuracy against Bangkok stations has not been measured here. TMD publishes its new run around 07:45, after the daily job starts, so the morning run often has today's values only. The afternoon update (`tmd-refresh`) adds the missing days and never changes values already published.

### How it is evaluated

- Walk-forward, expanding window, never shuffled. The first test block starts one year after the data begins. Each 30-day block is predicted by a model trained only on rows whose outcome was known before the block started.
- Every method is scored on the same rows, so a method cannot look better by skipping hard days.
- Baselines: persistence (yesterday), seven-day seasonal naive (same weekday last week), and for monthly forecasts, climatology.
- Promotion gate: a candidate must cut MAE by at least 1 % against every baseline over the latest 90 days and over all folds. The candidate with the lower MAE over all folds is tried first; if it fails and no model is published yet, the other candidate is tried before the slot falls back to a baseline. If a model is already published, the candidate must also beat it on days that model never trained on, and at least 14 such days must exist.
- Tests check that no feature uses data after its forecast origin and that walk-forward training never sees a test-period outcome.
- Training takes about half an hour, so the daily job runs `train --max-age-days 7`: it refits only when the saved models are a week old or a forecast slot is missing from the registry. Predictions still use each day's newest data. Running the workflow by hand with `retrain` ticked trains at once. The 14-day rule above means a refit model rarely replaced the published one more often than this anyway.

### Results

Out-of-sample walk-forward results from the 2026-11-11 run. Air quality slots cover about 1,150 days and weather slots about 1,650 days, ending November 2026. Skill is the share of persistence error removed.

| Slot | Best model | MAE | RMSE | R² | Persistence MAE | Skill |
|---|---|---|---|---|---|---|
| PM2.5 today (µg/m³) | Gradient boosting | 3.21 | 4.61 | 0.81 | 3.45 | 7 % |
| PM2.5 tomorrow (µg/m³) | Random forest | 4.64 | 6.52 | 0.63 | 5.28 | 12 % |
| PM10 today (µg/m³) | Random forest | 4.81 | 6.78 | 0.81 | 4.89 | 2 % |
| PM10 tomorrow (µg/m³) | Random forest | 6.89 | 9.46 | 0.62 | 7.47 | 8 % |
| Temperature today (°C) | Random forest, not published | 0.59 | 0.78 | 0.79 | 0.59 | 1 % |
| Temperature tomorrow (°C) | Random forest | 0.83 | 1.07 | 0.59 | 0.86 | 3 % |
| Humidity today (%) | Random forest, not published | 3.50 | 4.68 | 0.82 | 3.44 | −2 % |
| Humidity tomorrow (%) | Random forest | 4.81 | 6.37 | 0.66 | 4.89 | 2 % |

PM2.5 tomorrow by season of the target date (MAE, model against persistence): cool haze season November to February 7.0 against 8.4, hot season March to May 5.7 against 5.8, rainy season June to October 2.7 against 3.2.

Monthly errors over 25 to 27 out-of-sample months for air quality and about 40 months for weather: MAE 2.8 to 3.0 µg/m³ for PM2.5, 4.4 to 4.5 µg/m³ for PM10, 0.8 °C for temperature and 3.5 to 3.7 % for humidity.

For context, the Open-Meteo CAMS value for the same day, which is hindsight rather than a forecast, has a PM2.5 MAE of 11.0 against the station panel. The model reads high for Bangkok.

### Feature experiments

Each addition was tested on the same walk-forward folds, with and without it. MAE of the best candidate, measured on 2026-11-13 to 2026-11-16:

| Addition | PM2.5 today | PM2.5 tomorrow | PM10 today | PM10 tomorrow | Decision |
|---|---|---|---|---|---|
| Target-day weather forecast (JMA previous runs) | 3.19 → 3.08 | 4.55 → 4.28 | 4.80 → 4.63 | 6.75 → 6.40 | Kept. Temperature tomorrow 0.83 → 0.64 °C, humidity tomorrow 4.78 → 3.69 % |
| Fire count and radiative power in the region (NASA FIRMS) | no clear change | no clear change | no clear change | no clear change | Kept as inputs; the gate decides |
| Fire power weighted by wind direction (fires upwind of Bangkok, eight compass sectors) | 3.08 → 3.11 | 4.28 → 4.31 | 4.63 → 4.64 | 6.41 → 6.48 | Rejected: slightly worse in every slot, and no better in the haze season (PM2.5 tomorrow 6.29 → 6.30). Not in the code |

The fire rows are a caution against assuming a plausible feature helps. A daily mean wind and eight sectors may be too coarse; trajectories would be the next thing to try.

### Forecast ranges

The range is the forecast plus or minus the error that 80 % of past walk-forward forecasts stayed within. One value for the whole year was too narrow in the haze season and too wide in the rainy season, so the value depends on the season of the target date. Coverage measured out of sample, each year's ranges taken from earlier years only (target 80 %):

| Slot | Haze season, one range | Haze season, seasonal | Rainy season, one range | Rainy season, seasonal |
|---|---|---|---|---|
| PM2.5 today | 70 % | 86 % | 94 % | 79 % |
| PM2.5 tomorrow | 63 % | 77 % | 94 % | 82 % |
| PM10 today | 63 % | 87 % | 89 % | 84 % |
| PM10 tomorrow | 62 % | 80 % | 93 % | 82 % |

**How each range is chosen.** Errors also grow with the forecast itself (a forecast of 60 µg/m³ misses by more than one of 15), and humidity errors have grown in recent years, so one fixed recipe is not right for every slot. Training tries two shapes, by season of the target date and by four bands of forecast level, each calibrated on all past walk-forward forecasts, on the newest two years only and on the newest year only. Each of the six is calibrated on all but the newest year and checked on that year. Those whose coverage there is within 7 points of 80 % are eligible, and the one with the lowest interval score (width plus a penalty for each miss, scaled by how far outside it fell) is published, refitted on the same window up to the newest forecast. The comparison is kept in `metrics.json` under `range`. Hourly ranges do the same per part of the forecast (rest of today, tomorrow), with one value or level bands.

Coverage on the newest year, run of 19 November 2026: old method (seasons, all history) against the published one, with its mean width:

| Slot | Seasons, all history | Published | Width |
|---|---|---|---|
| PM2.5 today | 90 % | 81 %, seasons, newest year | 8.7 µg/m³ |
| PM2.5 tomorrow | 86 % | 83 %, level bands, two years | 14.1 µg/m³ |
| PM10 in 6 days | 92 % | 85 %, level bands, two years | 27.2 µg/m³ |
| Humidity today | 69 % | 84 %, level bands, newest year | 12.4 % |
| Humidity tomorrow | 70 % | 82 %, level bands, newest year | 15.6 % |
| Hourly PM2.5 today, evening run | 94 % | 86 %, one value, newest year | 4.8 µg/m³ |

Air quality ranges were too wide and humidity ranges too narrow; both are now closer to 80 %. Coverage is measured on the same year that picked the method, so it flatters the chosen one a little. Humidity 4 to 6 days ahead still covers only 73 to 78 %.

### Chance above the standard

City and station daily PM2.5 forecasts carry `pm25_p_above_standard` (stations: `p_above_standard`), the chance that the daily mean goes above the Thai 24-hour standard of 37.5 µg/m³. It comes from the signed errors of past walk-forward forecasts in the same band of forecast level: the share of them that, added to today's forecast, would land above the standard. It is published for a slot only when, on the newest year, the standard was crossed at least ten times and the chance beat always quoting the historical rate (Brier score). City PM2.5: Brier 0.027 against 0.054 for today and 0.050 against 0.054 for tomorrow, on 18 days above the standard. Stations: 0.032 against 0.087 for today, about 590 station-days above. PM10 never went above its standard of 120 µg/m³ in the newest year, so no PM10 chance is published. With 18 city events the chance is coarse: in testing, days given 60 to 80 % went above about half the time. Each published chance is kept in the forecast history and scored once the day is measured: the accuracy page shows its live Brier score next to always quoting the share of days that went above in the same window.

### Seven-day forecast

The daily forecast covers today and the six days after it. Each day and value is its own slot with its own promotion gate, so a day shows a model only if the model beat the simple rules for that day. Beyond tomorrow a third rule joins persistence and the same weekday last week: the mean of the last seven days, which there beats yesterday's value. The weather forecast for each target day is the run issued as many days before it as the horizon, stored as run ages 3 to 7 in `bronze/openmeteo_nwp_long.csv`.

Walk-forward MAE of the model against the best simple rule:

| | In 2 days | In 4 days | In 6 days |
|---|---|---|---|
| PM2.5 µg/m³ | 4.47 vs 5.68 | 4.86 vs 5.78 | 5.04 vs 5.83 |
| PM10 µg/m³ | 6.84 vs 8.10 | 7.32 vs 8.36 | 7.61 vs 8.59 (rule published, see below) |
| Temperature °C | 0.71 vs 0.95 | 0.81 vs 1.00 | 0.83 vs 1.03 |
| Humidity % | 4.00 vs 5.42 | 4.53 vs 5.80 | 4.90 vs 6.18 |

Without the weather forecasts for the target day, PM2.5 in 6 days would be 5.85, no better than the weekly mean. PM10 in 6 days publishes the weekly mean for now: the model is better over all folds but not over the latest 90 days, which the gate also requires. Training all 28 daily slots takes about 25 minutes.

### Hourly forecast

`gold/hourly_forecast.json` holds PM2.5 for each hour from 04:00 today to 23:00 tomorrow, Bangkok time. It is made once a day in the same run, so it adds no scheduled jobs. Station hours reach OpenAQ two to three hours late and the run starts between 07:17 and 08:00, so the model only uses hours up to 03:00. One gradient boosting model covers all 44 lead times, with the hour of day, the lead and the weather forecast for each target hour as features.

Walk-forward over 53,633 hours: MAE 3.66 µg/m³ against 4.91 for the same hour yesterday and 4.80 for yesterday's mean. Hours of today 2.79 against 3.95; hours of tomorrow 4.40 against 5.52. It is published only while it beats both baselines by 1 %.

**Afternoon and evening updates.** The `Hourly update` workflow runs at about 13:00 and 19:00. It fetches the newest station hours and repeats the forecast with a model that sees hours up to 09:00 (afternoon) or 16:00 (evening), so `gold/hourly_forecast.json` then starts at 10:00 or 17:00. It trains nothing: the morning run trains all the models when it retrains. The job takes a few minutes and is skipped when the newest hours have not arrived, which leaves the earlier forecast in place. A daily run started by hand later in the day keeps a newer update rather than replacing it with the morning forecast. Walk-forward MAE, run of 19 November 2026:

| Run | Hours known | Hours evaluated | MAE | Same hour yesterday | Rest of today | Tomorrow |
|---|---|---|---|---|---|---|
| Morning | to 03:00 | 53,818 | 3.67 | 4.92 | 2.79 | 4.42 |
| Afternoon | to 09:00 | 46,015 | 3.42 | 4.77 | 2.37 | 4.03 |
| Evening | to 16:00 | 37,061 | 3.21 | 4.54 | 2.12 | 3.51 |

Each later run sees more of the day, so its forecast for tomorrow is better too: 4.42, 4.03 and 3.51 µg/m³.

**Hourly PM10.** Each hour also carries `pm10`, `pm10_low` and `pm10_high`, from the same code with its own morning and afternoon models (`pm10_method` names the method). The city value is the median of at least two of the three PM10 stations. Walk-forward over 53,506 hours: MAE 5.47 µg/m³ against 6.84 for yesterday's mean and 7.18 for the same hour yesterday; hours of today 4.29, tomorrow 6.48. The afternoon model: 5.18 against 7.00; hours of today 3.74. The evening model: 4.95 against 6.71; hours of today 3.47, tomorrow 5.37. All three passed the promotion gate.

The dashboard also colours each forecast hour by the PCD band of its value. The official index uses the 24-hour average, so the colours are a guide to the time of day, not the official level.

### Station forecasts

`station_forecasts` in the forecast document gives PM2.5 for each of 20 stations for the same seven days as the city forecast (`today`, `tomorrow`, `day2` to `day6`). One pooled model per horizon covers all stations, trained in the same GitHub Actions run: a row is a station on an origin day, with that station's recent values, its usual offset from the city, and all city features. Seven models instead of 140 keeps training short and lets stations with gaps borrow from the others. Each horizon passes the promotion gate on its own; a horizon that fails publishes the better of persistence and the city forecast.

The eight stations that measure PM10 also get a PM10 forecast, under `pm10` of each day's entry, from the same code with its own models, one per horizon.

Walk-forward MAE (µg/m³) per horizon, run of 19 November 2026, after the ten new stations were added. Each cell is model / station persistence / city forecast. The model is published for every horizon of both targets.

| Horizon | PM2.5, about 18,600 station-days | PM10, about 5,500 station-days |
|---|---|---|
| Today | 3.23 / 3.77 / 4.60 | 4.80 / 5.54 / 7.22 |
| Tomorrow | 4.63 / 5.61 / 5.41 | 6.48 / 8.14 / 8.09 |
| In 2 days | 4.86 / 6.41 / 5.56 | 7.07 / 9.19 / 8.22 |
| In 3 days | 5.02 / 6.73 / 5.59 | 7.42 / 9.63 / 8.30 |
| In 4 days | 5.45 / 6.85 / 5.86 | 7.68 / 9.92 / 9.89 |
| In 5 days | 5.49 / 6.96 / 5.98 | 7.90 / 9.91 / 8.58 |
| In 6 days | 5.54 / 6.97 / 5.98 | 7.83 / 10.06 / 10.04 |

With 10 PM2.5 stations the same table read 3.20 / 3.64 / 4.57 for today and 5.49 / 6.87 / 6.03 for 6 days, so the new stations, mostly further from the centre, are about as predictable as the old ones. PM10 in 5 days, which published the city forecast with three stations, now passes the gate.

### Limitations

- The better of two candidate models is picked on the same walk-forward results that are reported, so the reported model error is slightly optimistic.
- R² is flattered by the strong seasonal cycle. Skill against persistence is the more honest number, and it is small for the same-day forecast.
- About five years of station data contain only five cool seasons, so monthly forecasts cannot learn much beyond the seasonal average.
- The city PM10 value rests on three stations and represents the city less well than PM2.5.
- Recent Open-Meteo weather is preliminary and may be revised. Training uses revised history, so live inputs are slightly noisier than training inputs.
- The station panel is fixed. If stations stop reporting for long, the city value is missing rather than estimated.
- Burning-season smoke from outside Bangkok is only represented by regional fire totals. Weighting fires by wind direction did not help.
- Live scores for the hourly and station forecasts only start on 17 November 2026, so for some weeks their walk-forward results are the better guide.

## Data sources and attribution

Station data from [OpenAQ](https://openaq.org), originally published by Thailand's Pollution Control Department (Air4Thai). Weather and modelled air quality from [Open-Meteo](https://open-meteo.com), licensed CC BY 4.0. Check each provider's terms before reusing the data.
