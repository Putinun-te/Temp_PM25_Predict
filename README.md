# Bangkok PM2.5 and PM10 Forecast

A pipeline that collects public air quality and weather data, then forecasts PM2.5 and PM10 for Bangkok.

The project is under construction. No forecast accuracy is claimed yet.

## Data

All timestamps are stored in UTC.

| Source | Role | Data | Access |
|---|---|---|---|
| OpenAQ (Air4Thai reference monitors) | Forecast target | Hourly PM2.5 and PM10 measured at a fixed panel of stations | Free API key |
| Open-Meteo Air Quality | Feature | PM2.5, PM10, NO2, O3, SO2 and CO from the CAMS global model | No key |
| Open-Meteo Historical Weather | Feature | Temperature, humidity, precipitation and wind | No key |

Open-Meteo air quality values come from an atmospheric model at about 45 km resolution. They are never used to fill gaps in the measured target.

## Run locally

```bash
python3.12 -m venv .venv
make install
make test
cp .env.example .env    # then set OPENAQ_API_KEY
set -a; source .env; set +a
make backfill
```

`make backfill` fetches only the hours missing from `data/`, so it is safe to run repeatedly. The first OpenAQ load takes about 15 minutes because requests are paced for the free tier.
