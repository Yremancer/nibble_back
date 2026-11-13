
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Asia/Vladivostok")

_RELATIVE_PATTERNS: list[tuple[re.Pattern, int]] = [
    (re.compile(r"^\s*сегодня\s*$", re.IGNORECASE), 0),
    (re.compile(r"^\s*вчера\s*$", re.IGNORECASE), -1),
    (re.compile(r"^\s*позавчера\s*$", re.IGNORECASE), -2),
]

_MONTHS = {
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "июн": 6,
    "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
}


def resolve_fishing_date(expression: str | None, published_at: datetime) -> date | None:
    if not expression:
        return None

    expr = expression.strip()
    published_local = published_at.astimezone(_TZ)

    for pattern, offset_days in _RELATIVE_PATTERNS:
        if pattern.match(expr):
            return (published_local + timedelta(days=offset_days)).date()

    iso_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", expr)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    dm_match = re.match(r"^(\d{1,2})\s+([а-яё]+)\.?\s*(\d{4})?$", expr, re.IGNORECASE)
    if dm_match:
        day_str, month_word, year_str = dm_match.groups()
        month_num = None
        for prefix, num in _MONTHS.items():
            if month_word.lower().startswith(prefix):
                month_num = num
                break
        if month_num is not None:
            year = int(year_str) if year_str else published_local.year
            try:
                candidate = date(year, month_num, int(day_str))
            except ValueError:
                return None
            if not year_str and abs((published_local.date() - candidate).days) > 200:
                return None
            return candidate

    return None
