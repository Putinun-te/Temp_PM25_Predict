# Bangkok PM2.5 and PM10 forecast, 2026-11-14

Generated 2026-11-14T07:48:59+07:00 from station data up to 2026-11-13. Status: ok.

## Daily mean air quality (µg/m³)

| Day | Date | PM2.5 | PM2.5 range | PM2.5 method | PM10 | PM10 range | PM10 method |
|---|---|---|---|---|---|---|---|
| Today | 2026-11-14 | 20.8 | 16.1 to 25.6 | gradient boosting | 36.2 | 28.9 to 43.6 | random forest |
| Tomorrow | 2026-11-15 | 22.6 | 15.6 to 29.7 | random forest | 33.1 | 23.0 to 43.2 | random forest |

## Daily weather

Our forecast is trained on Open-Meteo history. TMD is the Thai Meteorological Department's own 3 km model, shown as an independent reference.

| Day | Date | Temperature °C | Range | Method | Humidity % | Range | Method | TMD temperature °C (min to max) | TMD humidity % |
|---|---|---|---|---|---|---|---|---|---|
| Today | 2026-11-14 | 28.4 | 27.6 to 29.2 | random forest | 70.4 | 65.6 to 75.2 | random forest | 28.2 (24.0 to 32.3) | 74.3 |
| Tomorrow | 2026-11-15 | 28.0 | 26.9 to 29.0 | random forest | 64.2 | 58.2 to 70.1 | random forest | 29.8 (26.9 to 33.7) | 66.2 |

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
| PM2.5 today | gradient boosting | 3.09 | 3.45 | 10% | kept: only 3 days are unseen by the current model |
| PM2.5 tomorrow | random forest | 4.29 | 5.28 | 19% | kept: only 3 days are unseen by the current model |
| PM10 today | random forest | 4.61 | 4.89 | 6% | kept: only 3 days are unseen by the current model |
| PM10 tomorrow | random forest | 6.45 | 7.46 | 14% | kept: only 3 days are unseen by the current model |
| Temperature today | random forest | 0.51 | 0.59 | 14% | kept: only 1 days are unseen by the current model |
| Temperature tomorrow | random forest | 0.64 | 0.86 | 26% | kept: only 3 days are unseen by the current model |
| Humidity today | random forest | 2.96 | 3.44 | 14% | kept: only 0 days are unseen by the current model |
| Humidity tomorrow | random forest | 3.69 | 4.90 | 25% | kept: only 3 days are unseen by the current model |

Ranges cover 80 % of past out-of-sample errors. Data: OpenAQ (Air4Thai reference stations), Open-Meteo and TMD.
