"""Render a short daily report from the forecast and the evaluation metrics."""

from __future__ import annotations

from typing import Any

REPORT_FILENAME = "report.md"
SLOT_NAMES = {
    "pm25_h1": "PM2.5 today",
    "pm25_h2": "PM2.5 tomorrow",
    "pm10_h1": "PM10 today",
    "pm10_h2": "PM10 tomorrow",
}


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def _range(row: dict[str, Any], target: str) -> str:
    low, high = row.get(f"{target}_low"), row.get(f"{target}_high")
    return "n/a" if low is None or high is None else f"{low:.1f} to {high:.1f}"


def _method(name: str) -> str:
    return name.replace("_", " ")


def build_report(forecast: dict[str, Any], metrics: dict[str, Any]) -> str:
    """Return the report as Markdown, which also reads well as plain text."""
    lines = [
        f"# Bangkok PM2.5 and PM10 forecast, {forecast['as_of']}",
        "",
        f"Generated {forecast['generated_at']} from station data up to "
        f"{forecast['latest_data_date']}. Status: {forecast['status']}.",
        "",
    ]
    if forecast["status"] != "ok":
        lines += [
            f"Warning: the newest station data is {forecast['data_age_days']} days old, "
            "so some values are missing.",
            "",
        ]

    lines += [
        "## Daily mean (µg/m³)",
        "",
        "| Day | Date | PM2.5 | PM2.5 range | PM2.5 method | PM10 | PM10 range | PM10 method |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in forecast["daily"]:
        lines.append(
            f"| {row['label'].capitalize()} | {row['date']} "
            f"| {_number(row['pm25'])} | {_range(row, 'pm25')} | {_method(row['pm25_method'])} "
            f"| {_number(row['pm10'])} | {_range(row, 'pm10')} | {_method(row['pm10_method'])} |"
        )

    lines += [
        "",
        "## Monthly mean (µg/m³)",
        "",
        "| Month | PM2.5 | PM2.5 range | PM10 | PM10 range | Method |",
        "|---|---|---|---|---|---|",
    ]
    for row in forecast["monthly"]:
        lines.append(
            f"| {row['month']} | {_number(row['pm25'])} | {_range(row, 'pm25')} "
            f"| {_number(row['pm10'])} | {_range(row, 'pm10')} | {_method(row['pm25_method'])} |"
        )

    lines += [
        "",
        "## Out-of-sample check",
        "",
        "Walk-forward results over all past folds. Skill is the share of persistence error removed.",
        "",
        "| Forecast | Published method | Best model MAE | Persistence MAE | Skill | Decision |",
        "|---|---|---|---|---|---|",
    ]
    for slot, name in SLOT_NAMES.items():
        entry = metrics.get("daily", {}).get(slot)
        if entry is None:
            continue
        best = entry["overall"][entry["best_candidate"]]["mae"]
        persistence = entry["overall"]["persistence"]["mae"]
        lines.append(
            f"| {name} | {_method(entry['published_method'])} | {best:.2f} | {persistence:.2f} "
            f"| {entry['skill_vs_persistence']:.0%} | {entry['decision']} |"
        )

    lines += [
        "",
        "Ranges cover 80 % of past out-of-sample errors. "
        "Data: OpenAQ (Air4Thai reference stations) and Open-Meteo.",
        "",
    ]
    return "\n".join(lines)
