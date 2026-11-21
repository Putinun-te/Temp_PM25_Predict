# Bangkok PM2.5 and PM10 forecast, 2026-11-21

Generated 2026-11-21T07:46:10+07:00 from station data up to 2026-11-20. Status: ok.

## Daily mean air quality (µg/m³)

| Day | Date | PM2.5 | PM2.5 range | PM2.5 method | PM10 | PM10 range | PM10 method |
|---|---|---|---|---|---|---|---|
| Today | 2026-11-21 | 20.2 | 14.7 to 25.6 | gradient boosting | 35.0 | 27.6 to 42.5 | gradient boosting |
| Tomorrow | 2026-11-22 | 26.7 | 19.7 to 33.8 | random forest | 38.8 | 29.3 to 48.4 | gradient boosting |
| In 2 days | 2026-11-23 | 32.4 | 20.2 to 44.6 | random forest | 52.1 | 36.5 to 67.8 | random forest |
| In 3 days | 2026-11-24 | 31.7 | 20.4 to 43.0 | random forest | 49.7 | 33.0 to 66.5 | random forest |
| In 4 days | 2026-11-25 | 29.5 | 15.7 to 43.2 | random forest | 41.3 | 29.0 to 53.7 | gradient boosting |
| In 5 days | 2026-11-26 | 32.3 | 18.6 to 45.9 | random forest | 48.5 | 31.9 to 65.1 | random forest |
| In 6 days | 2026-11-27 | 29.9 | 17.8 to 42.0 | random forest | 45.6 | 27.9 to 63.4 | gradient boosting |

## Daily weather

Our forecast is trained on Open-Meteo history. TMD is the Thai Meteorological Department's own 3 km model, shown as an independent reference.

| Day | Date | Temperature °C | Range | Method | Humidity % | Range | Method | TMD temperature °C (min to max) | TMD humidity % |
|---|---|---|---|---|---|---|---|---|---|
| Today | 2026-11-21 | 30.2 | 29.4 to 31.0 | random forest | 55.5 | 50.6 to 60.5 | random forest | 28.4 (24.7 to 31.6) | 58.3 |
| Tomorrow | 2026-11-22 | 29.3 | 28.0 to 30.6 | random forest | 58.7 | 51.5 to 66.0 | random forest | 28.4 (23.8 to 33.1) | 61.1 |
| In 2 days | 2026-11-23 | 29.7 | 28.7 to 30.6 | random forest | 59.5 | 52.0 to 67.0 | random forest | n/a | n/a |
| In 3 days | 2026-11-24 | 29.6 | 28.0 to 31.1 | gradient boosting | 59.9 | 51.5 to 68.3 | random forest | n/a | n/a |
| In 4 days | 2026-11-25 | 29.0 | 27.5 to 30.6 | gradient boosting | 62.2 | 54.1 to 70.3 | random forest | n/a | n/a |
| In 5 days | 2026-11-26 | 29.1 | 27.8 to 30.4 | random forest | 61.7 | 50.8 to 72.5 | random forest | n/a | n/a |
| In 6 days | 2026-11-27 | 29.2 | 27.5 to 30.9 | random forest | 58.1 | 47.5 to 68.8 | random forest | n/a | n/a |

## Monthly mean

| Month | PM2.5 µg/m³ | PM2.5 range | PM10 µg/m³ | PM10 range | Temperature °C | Humidity % | Method |
|---|---|---|---|---|---|---|---|
| 2026-12 | 30.0 | 25.0 to 35.0 | 49.2 | 41.8 to 56.7 | 27.2 | 61.1 | climatology |
| 2027-01 | 33.5 | 28.0 to 38.9 | 53.4 | 45.9 to 60.9 | 27.3 | 58.2 | climatology |
| 2027-02 | 29.7 | 26.1 to 33.3 | 44.9 | 37.1 to 52.7 | 28.2 | 68.8 | climatology |

## Out-of-sample check

Walk-forward results over all past folds. Skill is the share of persistence error removed.

| Forecast | Published method | Best model MAE | Persistence MAE | Skill | Decision |
|---|---|---|---|---|---|
| PM2.5 today | gradient boosting | 3.09 | 3.45 | 11% | promoted: beats every baseline (replaces a model trained on other features) |
| PM2.5 tomorrow | random forest | 4.28 | 5.29 | 19% | promoted: beats every baseline (replaces a model trained on other features) |
| PM2.5 in 2 days | random forest | 4.46 | 6.09 | 27% | kept: only 2 days are unseen by the current model |
| PM2.5 in 3 days | random forest | 4.51 | 6.41 | 30% | kept: only 2 days are unseen by the current model |
| PM2.5 in 4 days | random forest | 4.86 | 6.53 | 26% | kept: only 2 days are unseen by the current model |
| PM2.5 in 5 days | random forest | 5.06 | 6.59 | 23% | kept: only 2 days are unseen by the current model |
| PM2.5 in 6 days | random forest | 5.03 | 6.70 | 25% | kept: only 2 days are unseen by the current model |
| PM10 today | gradient boosting | 4.61 | 4.90 | 6% | promoted: beats every baseline (replaces a model trained on other features) |
| PM10 tomorrow | gradient boosting | 6.43 | 7.47 | 14% | promoted: beats every baseline (replaces a model trained on other features) |
| PM10 in 2 days | random forest | 6.84 | 8.57 | 20% | kept: only 2 days are unseen by the current model |
| PM10 in 3 days | random forest | 6.83 | 9.12 | 25% | kept: only 2 days are unseen by the current model |
| PM10 in 4 days | gradient boosting | 7.32 | 9.28 | 21% | kept: only 0 days are unseen by the current model |
| PM10 in 5 days | random forest | 7.42 | 9.26 | 20% | kept: only 2 days are unseen by the current model |
| PM10 in 6 days | gradient boosting | 7.60 | 9.45 | 20% | kept: only 0 days are unseen by the current model |
| Temperature today | random forest | 0.51 | 0.59 | 14% | promoted: beats every baseline (replaces a model trained on other features) |
| Temperature tomorrow | random forest | 0.64 | 0.86 | 26% | promoted: beats every baseline (replaces a model trained on other features) |
| Temperature in 2 days | random forest | 0.72 | 1.00 | 28% | kept: only 2 days are unseen by the current model |
| Temperature in 3 days | gradient boosting | 0.77 | 1.07 | 28% | kept: only 2 days are unseen by the current model |
| Temperature in 4 days | gradient boosting | 0.81 | 1.12 | 28% | kept: only 2 days are unseen by the current model |
| Temperature in 5 days | random forest | 0.80 | 1.15 | 31% | kept: only 2 days are unseen by the current model |
| Temperature in 6 days | random forest | 0.84 | 1.17 | 28% | kept: only 2 days are unseen by the current model |
| Humidity today | random forest | 2.96 | 3.45 | 14% | kept: only 6 days are unseen by the current model |
| Humidity tomorrow | random forest | 3.70 | 4.91 | 25% | promoted: beats every baseline (replaces a model trained on other features) |
| Humidity in 2 days | random forest | 4.01 | 5.66 | 29% | kept: only 2 days are unseen by the current model |
| Humidity in 3 days | random forest | 4.21 | 6.03 | 30% | kept: only 2 days are unseen by the current model |
| Humidity in 4 days | random forest | 4.54 | 6.34 | 28% | kept: only 2 days are unseen by the current model |
| Humidity in 5 days | random forest | 4.64 | 6.48 | 28% | kept: only 2 days are unseen by the current model |
| Humidity in 6 days | random forest | 4.91 | 6.63 | 26% | kept: only 2 days are unseen by the current model |

Ranges cover 80 % of past out-of-sample errors. Data: OpenAQ (Air4Thai reference stations), Open-Meteo and TMD.
