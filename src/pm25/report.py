"""Render the daily report as Markdown, CSV and PDF."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

REPORT_FILENAME = "report.md"
CSV_FILENAME = "report.csv"
PDF_FILENAME = "report.pdf"
HISTORY_FILENAME = "forecast_history.csv"
CSV_COLUMNS = [
    "as_of",
    "generated_at",
    "kind",
    "period",
    "label",
    "target",
    "value",
    "low",
    "high",
    "method",
]
HISTORY_KEYS = ["as_of", "kind", "period", "target"]
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


def forecast_table(forecast: dict[str, Any]) -> pd.DataFrame:
    """Return one row per forecast value, the shape that suits spreadsheets."""
    rows = []
    for kind, period_key, label_key in (
        ("daily", "date", "label"),
        ("monthly", "month", "months_ahead"),
    ):
        for item in forecast[kind]:
            for target in ("pm25", "pm10"):
                rows.append(
                    {
                        "as_of": forecast["as_of"],
                        "generated_at": forecast["generated_at"],
                        "kind": kind,
                        "period": item[period_key],
                        "label": item[label_key],
                        "target": target,
                        "value": item[target],
                        "low": item[f"{target}_low"],
                        "high": item[f"{target}_high"],
                        "method": item[f"{target}_method"],
                    }
                )
    return pd.DataFrame(rows, columns=CSV_COLUMNS)


def append_history(path: Path, table: pd.DataFrame) -> pd.DataFrame:
    """Add today's rows to the history file. Rerunning a day replaces that day's rows."""
    if path.exists():
        history = pd.read_csv(path, dtype=str)
        table = pd.concat([history, table.astype(str)], ignore_index=True)
    table = table.drop_duplicates(HISTORY_KEYS, keep="last").sort_values(HISTORY_KEYS)
    path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(path, index=False)
    return table


def write_pdf(
    path: Path, forecast: dict[str, Any], table: pd.DataFrame, plot: Path | None = None
) -> None:
    """Write a one-page A4 summary: headline, the forecast table and the evaluation plot."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure = plt.figure(figsize=(8.27, 11.69))
    figure.text(0.07, 0.95, f"Bangkok PM2.5 and PM10 forecast, {forecast['as_of']}", fontsize=16, weight="bold")
    figure.text(
        0.07,
        0.925,
        f"Generated {forecast['generated_at']} from station data up to "
        f"{forecast['latest_data_date']}. Status: {forecast['status']}. Values in µg/m³.",
        fontsize=9,
        color="#444444",
    )

    def cell(value: Any) -> str:
        return "n/a" if value is None or pd.isna(value) else f"{float(value):.1f}"

    body = [
        [
            row["period"],
            str(row["label"]),
            row["target"].upper().replace("PM25", "PM2.5"),
            cell(row["value"]),
            f"{cell(row['low'])} to {cell(row['high'])}",
            str(row["method"]).replace("_", " "),
        ]
        for _, row in table.iterrows()
    ]
    table_axis = figure.add_axes([0.07, 0.52, 0.86, 0.38])
    table_axis.axis("off")
    grid = table_axis.table(
        cellText=body,
        colLabels=["Date or month", "Horizon", "Pollutant", "Forecast", "Range", "Method"],
        loc="upper center",
        cellLoc="left",
        colLoc="left",
    )
    grid.auto_set_font_size(False)
    grid.set_fontsize(9)
    grid.scale(1, 1.4)

    if plot is not None and plot.exists():
        image_axis = figure.add_axes([0.05, 0.12, 0.9, 0.36])
        image_axis.imshow(plt.imread(plot))
        image_axis.axis("off")

    figure.text(
        0.07,
        0.06,
        "Ranges cover 80 % of past out-of-sample errors. "
        "Data: OpenAQ (Air4Thai reference stations) and Open-Meteo.",
        fontsize=8,
        color="#444444",
    )
    figure.savefig(path)
    plt.close(figure)
