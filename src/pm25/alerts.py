"""Public alerts when tomorrow's PM2.5 forecast crosses a health threshold.

This is a scaffold. The decision and the message are implemented and tested;
the delivery channels are stubs to be filled in. It is not run by the daily
workflow yet. See docs/alerts.md for how to add a channel and switch it on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

# Thai 24-hour PM2.5 standard (Pollution Control Department, since 1 June 2023).
# Above it the PCD scale says the air starts to affect health.
PM25_STANDARD = 37.5
PM25_RED = 75.0


@dataclass(frozen=True)
class Alert:
    date: str
    pm25: float
    level: str  # "orange" or "red", the PCD colour
    text_th: str
    text_en: str


def decide(forecast: dict[str, Any], threshold: float = PM25_STANDARD) -> Alert | None:
    """Return an alert when tomorrow's PM2.5 forecast is above the threshold."""
    tomorrow = next((day for day in forecast.get("daily", []) if day.get("label") == "tomorrow"), None)
    if tomorrow is None or tomorrow.get("pm25") is None or tomorrow["pm25"] <= threshold:
        return None
    value = float(tomorrow["pm25"])
    red = value > PM25_RED
    high = tomorrow.get("pm25_high")
    likely = f" (likely up to {high:.0f})" if high is not None else ""
    likely_th = f" (อาจสูงถึง {high:.0f})" if high is not None else ""
    return Alert(
        date=tomorrow["date"],
        pm25=value,
        level="red" if red else "orange",
        text_th=(
            f"พรุ่งนี้ {tomorrow['date']} คาดว่า PM2.5 กรุงเทพฯ {value:.0f} µg/m³{likely_th} "
            + ("มีผลกระทบต่อสุขภาพ ทุกคนควรงดกิจกรรมกลางแจ้ง" if red else "เริ่มมีผลกระทบต่อสุขภาพ ควรลดกิจกรรมกลางแจ้งและสวมหน้ากาก")
        ),
        text_en=(
            f"Tomorrow, {tomorrow['date']}, Bangkok PM2.5 is forecast at {value:.0f} µg/m³{likely}. "
            + ("This affects health; everyone should avoid outdoor activity." if red else "This starts to affect health; reduce time outdoors and wear a mask.")
        ),
    )


class Channel(Protocol):
    """A delivery channel. Credentials come from environment variables only."""

    name: str

    def send(self, alert: Alert) -> None: ...


class ConsoleChannel:
    """Prints the alert. Used for dry runs and as a reference implementation."""

    name = "console"

    def send(self, alert: Alert) -> None:
        print(f"[{alert.level}] {alert.text_th}\n[{alert.level}] {alert.text_en}")


class DiscordChannel:
    """TODO: POST {"content": ...} to the webhook URL in DISCORD_WEBHOOK_URL."""

    name = "discord"

    def send(self, alert: Alert) -> None:
        raise NotImplementedError("Discord delivery is not implemented yet, see docs/alerts.md")


class LineChannel:
    """TODO: LINE Messaging API broadcast with LINE_CHANNEL_ACCESS_TOKEN (LINE Notify has closed)."""

    name = "line"

    def send(self, alert: Alert) -> None:
        raise NotImplementedError("LINE delivery is not implemented yet, see docs/alerts.md")


class EmailChannel:
    """TODO: send through SMTP with SMTP_HOST, SMTP_USER, SMTP_PASSWORD and ALERT_EMAIL_TO."""

    name = "email"

    def send(self, alert: Alert) -> None:
        raise NotImplementedError("Email delivery is not implemented yet, see docs/alerts.md")


CHANNELS: dict[str, type] = {
    "console": ConsoleChannel,
    "discord": DiscordChannel,
    "line": LineChannel,
    "email": EmailChannel,
}
