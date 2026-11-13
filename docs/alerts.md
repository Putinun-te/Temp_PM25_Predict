# Public PM2.5 alerts (scaffold)

`python -m pm25 alert` decides whether tomorrow's PM2.5 forecast is above the
Thai 24-hour standard of 37.5 µg/m³ and builds a Thai and English message.
Only the `console` channel works today, and the daily workflow does not run
the command yet.

```bash
python -m pm25 alert                   # prints the alert, if any
python -m pm25 alert --channel discord # raises NotImplementedError for now
```

## What is done

- `pm25.alerts.decide`: picks tomorrow's forecast, returns an `Alert` with the
  PCD colour (orange above 37.5, red above 75) and the message in both languages.
- `Channel` protocol and a registry (`CHANNELS`), with `ConsoleChannel` as the
  reference implementation.
- Tests in `tests/test_alerts.py`.

## What is left

1. Implement one channel in `src/pm25/alerts.py`. Read every credential from an
   environment variable, never from code or a committed file.
   - Discord: `POST` `{"content": text}` to `DISCORD_WEBHOOK_URL`.
   - LINE: Messaging API broadcast with `LINE_CHANNEL_ACCESS_TOKEN`
     (LINE Notify closed in 2025).
   - Email: SMTP with `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_TO`.
2. Add a test that fakes the HTTP or SMTP call, like `tests/test_tmd.py` does.
3. Avoid repeats: send at most once per forecast date, for example by keeping
   the last alerted date in `data/gold/`.
4. Add the secret in GitHub (Settings, Secrets and variables, Actions) and a
   step after "Write daily report" in `.github/workflows/daily-forecast.yml`:

   ```yaml
   - name: Send PM2.5 alert
     continue-on-error: true # An alert outage must not block the forecast
     env:
       DISCORD_WEBHOOK_URL: ${{ secrets.DISCORD_WEBHOOK_URL }}
     run: python -m pm25 alert --channel discord
   ```
