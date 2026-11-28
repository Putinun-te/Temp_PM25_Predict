# Bangkok PM2.5 and PM10 forecast, 2026-11-28

Generated 2026-11-28T14:29:39+07:00 from station data up to 2026-11-27. Status: ok.

## Daily mean air quality (µg/m³)

| Day | Date | PM2.5 | PM2.5 range | PM2.5 method | PM10 | PM10 range | PM10 method |
|---|---|---|---|---|---|---|---|
| Today | 2026-11-28 | 23.4 | 18.2 to 28.5 | random forest change | 37.6 | 31.3 to 43.9 | random forest change |
| Tomorrow | 2026-11-29 | 23.7 | 16.7 to 30.8 | gradient boosting change | 39.1 | 29.8 to 48.4 | random forest change |
| In 2 days | 2026-11-30 | 26.7 | 19.6 to 33.8 | random forest | 37.9 | 28.0 to 47.8 | random forest change |
| In 3 days | 2026-12-01 | 29.1 | 17.7 to 40.4 | random forest | 38.8 | 28.1 to 49.5 | random forest blend |
| In 4 days | 2026-12-02 | 29.0 | 15.1 to 42.8 | random forest | 37.7 | 27.3 to 48.1 | random forest blend |
| In 5 days | 2026-12-03 | 23.4 | 14.2 to 32.7 | random forest blend | 37.0 | 26.1 to 47.9 | random forest blend |
| In 6 days | 2026-12-04 | 20.9 | 12.2 to 29.6 | random forest blend | 32.4 | 21.5 to 43.3 | gradient boosting blend |

## Daily weather

Our forecast is trained on Open-Meteo history. TMD is the Thai Meteorological Department's own 3 km model, shown as an independent reference.

| Day | Date | Temperature °C | Range | Method | Humidity % | Range | Method | TMD temperature °C (min to max) | TMD humidity % |
|---|---|---|---|---|---|---|---|---|---|
| Today | 2026-11-28 | 30.2 | 29.5 to 31.0 | gradient boosting change | 59.8 | 55.3 to 64.4 | gradient boosting change | 29.6 (25.2 to 36.7) | 53.7 |
| Tomorrow | 2026-11-29 | 29.4 | 28.3 to 30.5 | gradient boosting | 60.4 | 52.7 to 68.2 | gradient boosting change | 27.8 (24.6 to 33.6) | 51.4 |
| In 2 days | 2026-11-30 | 29.0 | 27.8 to 30.3 | gradient boosting change | 60.9 | 52.3 to 69.6 | random forest | n/a | n/a |
| In 3 days | 2026-12-01 | 29.9 | 28.3 to 31.4 | random forest | 60.3 | 51.0 to 69.6 | random forest | n/a | n/a |
| In 4 days | 2026-12-02 | 30.5 | 28.9 to 32.2 | gradient boosting | 58.9 | 48.6 to 69.2 | random forest | n/a | n/a |
| In 5 days | 2026-12-03 | 29.5 | 28.3 to 30.8 | random forest | 59.7 | 48.1 to 71.2 | random forest | n/a | n/a |
| In 6 days | 2026-12-04 | 29.2 | 27.7 to 30.8 | random forest | 72.1 | 61.6 to 82.6 | random forest | n/a | n/a |

## Monthly mean

| Month | PM2.5 µg/m³ | PM2.5 range | PM10 µg/m³ | PM10 range | Temperature °C | Humidity % | Method |
|---|---|---|---|---|---|---|---|
| 2026-12 | 30.0 | 24.6 to 35.3 | 49.2 | 40.9 to 57.6 | 27.2 | 61.1 | climatology |
| 2027-01 | 33.5 | 28.1 to 38.9 | 53.4 | 44.8 to 62.0 | 27.3 | 58.2 | climatology |
| 2027-02 | 29.7 | 24.5 to 35.0 | 44.9 | 36.0 to 53.8 | 28.2 | 68.8 | climatology |

## Out-of-sample check

Walk-forward results over all past folds. Skill is the share of persistence error removed.

| Forecast | Published method | Best model MAE | Persistence MAE | Skill | Decision |
|---|---|---|---|---|---|
| PM2.5 today | random forest change | 2.95 | 3.45 | 14% | kept: only 3 days are unseen by the current model |
| PM2.5 tomorrow | gradient boosting change | 4.31 | 5.28 | 18% | kept: only 3 days are unseen by the current model |
| PM2.5 in 2 days | random forest | 4.50 | 6.08 | 26% | kept: only 10 days are unseen by the current model |
| PM2.5 in 3 days | random forest | 4.55 | 6.40 | 29% | kept: only 3 days are unseen by the current model |
| PM2.5 in 4 days | random forest | 4.90 | 6.53 | 25% | kept: only 3 days are unseen by the current model |
| PM2.5 in 5 days | random forest blend | 5.10 | 6.60 | 23% | kept: only 3 days are unseen by the current model |
| PM2.5 in 6 days | random forest blend | 5.07 | 6.70 | 24% | kept: only 3 days are unseen by the current model |
| PM10 today | random forest change | 4.27 | 4.89 | 13% | kept: only 3 days are unseen by the current model |
| PM10 tomorrow | random forest change | 6.19 | 7.46 | 17% | kept: only 3 days are unseen by the current model |
| PM10 in 2 days | random forest change | 6.69 | 8.54 | 22% | kept: only 3 days are unseen by the current model |
| PM10 in 3 days | random forest blend | 6.88 | 9.10 | 24% | kept: only 3 days are unseen by the current model |
| PM10 in 4 days | random forest blend | 7.27 | 9.28 | 22% | kept: only 3 days are unseen by the current model |
| PM10 in 5 days | random forest blend | 7.38 | 9.27 | 20% | kept: only 3 days are unseen by the current model |
| PM10 in 6 days | gradient boosting blend | 7.46 | 9.45 | 21% | kept: only 3 days are unseen by the current model |
| Temperature today | gradient boosting change | 0.48 | 0.59 | 19% | kept: only 2 days are unseen by the current model |
| Temperature tomorrow | gradient boosting | 0.63 | 0.86 | 28% | kept: only 2 days are unseen by the current model |
| Temperature in 2 days | gradient boosting change | 0.71 | 1.00 | 29% | kept: only 2 days are unseen by the current model |
| Temperature in 3 days | random forest | 0.76 | 1.06 | 28% | kept: only 2 days are unseen by the current model |
| Temperature in 4 days | gradient boosting | 0.80 | 1.12 | 28% | kept: only 2 days are unseen by the current model |
| Temperature in 5 days | random forest | 0.80 | 1.15 | 30% | kept: only 2 days are unseen by the current model |
| Temperature in 6 days | random forest | 0.84 | 1.17 | 28% | kept: only 2 days are unseen by the current model |
| Humidity today | gradient boosting change | 2.79 | 3.45 | 19% | kept: only 2 days are unseen by the current model |
| Humidity tomorrow | gradient boosting change | 3.50 | 4.89 | 28% | kept: only 2 days are unseen by the current model |
| Humidity in 2 days | random forest | 3.94 | 5.65 | 30% | kept: only 2 days are unseen by the current model |
| Humidity in 3 days | random forest | 4.17 | 6.02 | 31% | promoted: beats every baseline (replaces a model trained on other features) |
| Humidity in 4 days | random forest | 4.48 | 6.34 | 29% | kept: only 2 days are unseen by the current model |
| Humidity in 5 days | random forest | 4.53 | 6.48 | 30% | kept: only 2 days are unseen by the current model |
| Humidity in 6 days | random forest | 4.81 | 6.64 | 28% | kept: only 2 days are unseen by the current model |

Ranges cover 80 % of past out-of-sample errors. Data: OpenAQ (Air4Thai reference stations), Open-Meteo and TMD.
