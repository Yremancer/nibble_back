from dataclasses import dataclass

from src.storage.mime import JPEG, MP4, PNG, WEBM, WEBP

MB = 1024 * 1024


@dataclass(frozen=True, slots=True)
class Category:
    name: str
    allowed_types: frozenset[str]
    max_bytes: int


IMAGE = Category("image", frozenset({JPEG, PNG, WEBP}), 10 * MB)
VIDEO = Category("video", frozenset({MP4, WEBM}), 500 * MB)
CATEGORIES = {c.name: c for c in (IMAGE, VIDEO)}
