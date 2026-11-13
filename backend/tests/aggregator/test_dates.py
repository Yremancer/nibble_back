"""Сценарий 10: относительная дата учитывает часовой пояс
Asia/Vladivostok относительно времени публикации, а не момента обработки."""

from datetime import datetime, timezone

from src.aggregator.normalize.dates import resolve_fishing_date


def test_yesterday_relative_to_published_at_in_vladivostok_tz():
    # 00:30 UTC = 10:30 Владивосток того же дня -> "вчера" от 13 ноября = 12 ноября
    published_at = datetime(2026, 11, 13, 0, 30, tzinfo=timezone.utc)

    result = resolve_fishing_date("вчера", published_at)

    assert result.isoformat() == "2026-11-12"


def test_yesterday_near_midnight_boundary_in_local_tz():
    # 15:30 UTC = 01:30 следующего дня во Владивостоке (UTC+10) ->
    # "вчера" должно считаться от локальной даты публикации, а не UTC.
    published_at = datetime(2026, 11, 12, 15, 30, tzinfo=timezone.utc)

    result = resolve_fishing_date("вчера", published_at)

    # локально уже 13 ноября 01:30, поэтому "вчера" = 12 ноября
    assert result.isoformat() == "2026-11-12"


def test_ambiguous_expression_returns_none():
    published_at = datetime(2026, 11, 13, 5, 0, tzinfo=timezone.utc)

    assert resolve_fishing_date("на днях", published_at) is None
    assert resolve_fishing_date(None, published_at) is None


def test_explicit_date_without_year_near_publication():
    published_at = datetime(2026, 11, 13, 5, 0, tzinfo=timezone.utc)

    result = resolve_fishing_date("10 ноября", published_at)

    assert result.isoformat() == "2026-11-10"


def test_compound_date_from_live_classification_requires_agreement():
    published_at = datetime(2026, 11, 13, 2, 0, tzinfo=timezone.utc)
    assert resolve_fishing_date("Вчера, 12 ноября", published_at).isoformat() == "2026-11-12"
    assert resolve_fishing_date("Вчера, 11 ноября", published_at) is None
