# Bangkok PM2.5 and PM10 Forecast

A pipeline that collects public air quality and weather data, then forecasts PM2.5 and PM10 for Bangkok.

The project is under construction. No forecast accuracy is claimed yet.

## Data

Hourly data comes from Open-Meteo and needs no credentials. All timestamps are stored in UTC.

- Air quality: PM2.5, PM10, NO2, O3, SO2 and CO from the CAMS global model
- Weather: temperature, humidity, precipitation and wind

Open-Meteo air quality values come from an atmospheric model at about 45 km resolution. They are not measurements from a ground station.

## Run locally

```bash
python3.12 -m venv .venv
make install
make test
make backfill
```

`make backfill` fetches only the hours missing from `data/`, so it is safe to run repeatedly.
