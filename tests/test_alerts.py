import pytest

from pm25.alerts import CHANNELS, ConsoleChannel, decide


def forecast(pm25, high=None):
    return {
        "daily": [
            {"label": "today", "date": "2026-11-13", "pm25": 99.0},
            {"label": "tomorrow", "date": "2026-11-14", "pm25": pm25, "pm25_high": high},
        ]
    }


def test_no_alert_at_or_below_the_standard():
    assert decide(forecast(37.5)) is None
    assert decide(forecast(None)) is None
    assert decide({"daily": []}) is None


def test_orange_and_red_alerts_use_tomorrow_only():
    orange = decide(forecast(42.0, 55.0))
    assert orange.level == "orange" and orange.date == "2026-11-14"
    assert "42" in orange.text_en and "up to 55" in orange.text_en
    assert "พรุ่งนี้" in orange.text_th
    assert decide(forecast(80.0)).level == "red"


def test_console_channel_prints_both_languages(capsys):
    ConsoleChannel().send(decide(forecast(42.0)))
    out = capsys.readouterr().out
    assert "[orange]" in out and "Bangkok" in out


def test_unfinished_channels_say_so():
    with pytest.raises(NotImplementedError):
        CHANNELS["discord"]().send(decide(forecast(42.0)))
