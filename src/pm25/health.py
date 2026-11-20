"""Check that the published outputs are fresh and trustworthy.

Runs after the daily forecast, on the saved data branch. A failed daily run,
stale station data, a failed quality gate, a model that has fallen behind
persistence, a missing hourly forecast, missing station forecasts or an Azure
SQL load that did not bring in today's runs each produce a problem. The workflow turns problems into a GitHub
issue, which emails the repository owner.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

MAX_DATA_AGE_DAYS = 2
# Each hourly run should have published by these Bangkok times, with the last
# measured hour it uses. GitHub can start a run 40 minutes late and station
# hours can arrive late, so the deadlines leave about an hour and a half.
HOURLY_DEADLINES = ((time(20, 30), 16, "evening"), (time(14, 30), 9, "afternoon"))
MORNING_KNOWN_HOUR = 3
STATION_DAYS = ("today", "tomorrow", "day2", "day3", "day4", "day5", "day6")


def check_health(
    forecast: dict[str, Any] | None,
    quality: dict[str, Any] | None,
    accuracy: dict[str, Any] | None,
    today: date,
    hourly: dict[str, Any] | None = None,
    sql_load: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Return a list of problems in plain English. An empty list means healthy.

    `now` is the Bangkok time of the check, which sets the hourly run that
    should have published by then. Without it only the morning run is expected.
    """
    problems: list[str] = []
    if forecast is None:
        problems.append("No forecast has been published (gold/forecast.json is missing).")
    else:
        issued = date.fromisoformat(forecast["as_of"])
        if issued < today:
            problems.append(
                f"No forecast was published today. The newest forecast is for {issued}, "
                "so the daily workflow probably failed."
            )
        latest = date.fromisoformat(forecast["latest_data_date"])
        # Yesterday is the newest day that can be complete.
        age = (today - latest).days - 1
        if age > MAX_DATA_AGE_DAYS:
            problems.append(
                f"Station data is {age} days old (newest complete day {latest}). "
                "OpenAQ or Air4Thai may be delayed."
            )
        problems.extend(_station_problems(forecast.get("station_forecasts") or []))
        problems.extend(_hourly_problems(hourly, today, now))
    problems.extend(_sql_problems(sql_load, today))
    if quality is None:
        problems.append("No data quality report found (silver/quality_report.json is missing).")
    elif not quality.get("passed", False):
        failed = [c["name"] for c in quality.get("checks", []) if not c["passed"] and c["severity"] == "error"]
        problems.append("Data quality checks failed: " + "; ".join(failed or ["see the report"]) + ".")
    if accuracy:
        problems.extend(f"Live accuracy: {alert}." for alert in accuracy.get("alerts", []))
    return problems


def _station_problems(stations: list[dict[str, Any]]) -> list[str]:
    if not stations:
        return ["The forecast has no station forecasts, so the map has nothing to show."]
    missing = [day for day in STATION_DAYS if not any(day in station for station in stations)]
    if missing:
        return ["No station has a forecast for " + ", ".join(missing) + "."]
    return []


def expected_hourly_run(now: datetime | None) -> tuple[int, str]:
    """Return the last measured hour and name of the newest hourly run due by `now`."""
    if now is not None:
        for deadline, known_hour, name in HOURLY_DEADLINES:
            if now.time() >= deadline:
                return known_hour, name
    return MORNING_KNOWN_HOUR, "morning"


def _hourly_problems(hourly: dict[str, Any] | None, today: date, now: datetime | None = None) -> list[str]:
    if hourly is None:
        return ["No hourly forecast has been published today (gold/hourly_forecast.json is missing)."]
    issued = date.fromisoformat(hourly["as_of"])
    if issued < today:
        return [f"The hourly forecast is for {issued}, not today."]
    hours = hourly.get("hours") or []
    if not hours:
        return ["The hourly forecast has no hours."]
    if not any(hour.get("pm10") is not None for hour in hours):
        return ["The hourly forecast has no PM10 values."]
    known_hour, name = expected_hourly_run(now)
    through = datetime.fromisoformat(hourly["inputs_through"])
    if through.date() < today or through.hour < known_hour:
        return [
            f"The hourly forecast uses measurements through {hourly['inputs_through']}, but the {name} run "
            f"should have used them through {known_hour:02d}:00. Check the hourly update run."
        ]
    return []


def _sql_problems(sql_load: dict[str, Any] | None, today: date) -> list[str]:
    # No record means Azure SQL is not configured, which is allowed.
    if sql_load is None:
        return []
    loaded = date.fromisoformat(sql_load["loaded_at"][:10])
    if loaded < today:
        return [f"Azure SQL was last loaded on {loaded}, so Power BI shows old data. Check the load step of the daily run."]
    stale = [
        f"{table} ({newest or 'empty'})"
        for table, newest in sql_load.get("newest_as_of", {}).items()
        if newest is None or date.fromisoformat(newest) < today
    ]
    if stale:
        return ["Azure SQL does not have today's run in " + ", ".join(stale) + "."]
    return []


def render(problems: list[str], today: date) -> str:
    """Return a Markdown body for the alert issue or the job summary."""
    if not problems:
        return f"Pipeline healthy on {today}."
    lines = [f"Pipeline health check found {len(problems)} problem(s) on {today}:", ""]
    lines += [f"- {problem}" for problem in problems]
    return "\n".join(lines) + "\n"
