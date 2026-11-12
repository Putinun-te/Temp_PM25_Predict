# Power BI report on Azure SQL

The pipeline loads its medallion layers into an Azure SQL Database free tier database named `pm25`. Power BI connects to the views in the `gold` schema.

## What to connect to

| Object | Contents | Use it for |
|---|---|---|
| `gold.v_latest_forecast` | Today, tomorrow and the next three months from the newest run | Cards and the monthly outlook |
| `gold.v_daily_actual_vs_forecast` | Each day's measured values next to the forecast issued the day before | Accuracy over time |
| `gold.model_metrics` | Out-of-sample MAE, persistence MAE and skill per forecast slot and run | Model quality trend |
| `silver.daily_city` | Cleaned daily Bangkok series since 2021 | Seasonal and long-term charts |

## Connect

Power BI Desktop runs on Windows only. On a Mac, use a Windows machine or the Power BI service in the browser, which may need a licence from your university account.

1. Allow your network through the database firewall: Azure portal, SQL server, Networking, add your client IP. For the Power BI service, also tick "Allow Azure services and resources to access this server". The database only accepts Microsoft Entra sign-in, so this does not open it to anyone without an account.
2. In Power BI choose Get data, then Azure SQL database.
3. Server: `<your-server>.database.windows.net`. Database: `pm25`. Choose Import mode.
4. Sign in with your Microsoft account (Microsoft Entra ID). Password sign-in is turned off on purpose.
5. Select the four objects above.

## Suggested report page

- Cards: PM2.5 and PM10 today and tomorrow from `v_latest_forecast`, filtered to `kind = daily`.
- Line chart: `date` on the axis, `measured_pm25` and `forecast` from `v_daily_actual_vs_forecast` with `target = pm25`.
- Column chart: `skill` by `slot` from `model_metrics` for the latest `as_of`.
- Line chart: monthly average of `pm25` from `silver.daily_city` to show the haze season.

## Keeping it free

The database is serverless and pauses after an hour without use. The free allowance is 100,000 vCore seconds a month, and the database is set to pause, not bill, when the allowance runs out. Each refresh wakes it, so schedule at most one refresh a day.
