"""Check that the published outputs are fresh and trustworthy.

Runs after the daily forecast, on the saved data branch. A failed daily run,
stale station data, a failed quality gate or a model that has fallen behind
persistence each produce a problem. The workflow turns problems into a GitHub
issue, which emails the repository owner.
"""

from __future__ import annotations

from datetime import date
from typing import Any

MAX_DATA_AGE_DAYS = 2


def check_health(
    forecast: dict[str, Any] | None,
    quality: dict[str, Any] | None,
    accuracy: dict[str, Any] | None,
    today: date,
) -> list[str]:
    """Return a list of problems in plain English. An empty list means healthy."""
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
    if quality is None:
        problems.append("No data quality report found (silver/quality_report.json is missing).")
    elif not quality.get("passed", False):
        failed = [c["name"] for c in quality.get("checks", []) if not c["passed"] and c["severity"] == "error"]
        problems.append("Data quality checks failed: " + "; ".join(failed or ["see the report"]) + ".")
    if accuracy:
        problems.extend(f"Live accuracy: {alert}." for alert in accuracy.get("alerts", []))
    return problems


def render(problems: list[str], today: date) -> str:
    """Return a Markdown body for the alert issue or the job summary."""
    if not problems:
        return f"Pipeline healthy on {today}."
    lines = [f"Pipeline health check found {len(problems)} problem(s) on {today}:", ""]
    lines += [f"- {problem}" for problem in problems]
    return "\n".join(lines) + "\n"
