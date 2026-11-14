import base64
from datetime import datetime

from src.exceptions import InvalidCursorError


def encode(moment: datetime, item_id: int) -> str:
    raw = f"{moment.isoformat()}|{item_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode(cursor: str) -> tuple[datetime, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        moment, item_id = base64.urlsafe_b64decode(padded).decode().split("|")
        return datetime.fromisoformat(moment), int(item_id)
    except ValueError as exc:
        raise InvalidCursorError from exc
