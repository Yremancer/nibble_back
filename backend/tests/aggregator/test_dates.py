
from datetime import datetime, timezone

from src.aggregator.normalize.dates import resolve_fishing_date


def test_yesterday_relative_to_published_at_in_vladivostok_tz():
    published_at = datetime(2026, 11, 13, 0, 30, tzinfo=timezone.utc)

    result = resolve_fishing_date("вчера", published_at)

    assert result.isoformat() == "2026-11-12"


def test_yesterday_near_midnight_boundary_in_local_tz():
    published_at = datetime(2026, 11, 12, 15, 30, tzinfo=timezone.utc)

    result = resolve_fishing_date("вчера", published_at)

    assert result.isoformat() == "2026-11-12"


def test_ambiguous_expression_returns_none():
    published_at = datetime(2026, 11, 13, 5, 0, tzinfo=timezone.utc)

    assert resolve_fishing_date("на днях", published_at) is None
    assert resolve_fishing_date(None, published_at) is None


def test_explicit_date_without_year_near_publication():
    published_at = datetime(2026, 11, 13, 5, 0, tzinfo=timezone.utc)

    result = resolve_fishing_date("10 ноября", published_at)

    assert result.isoformat() == "2026-11-10"
