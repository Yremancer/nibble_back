"""Определение реального формата файла по содержимому, не по расширению."""

from pathlib import Path

import filetype

_PHOTO_MIME_PREFIXES = ("image/",)
_VIDEO_MIME_PREFIXES = ("video/",)


def detect_mime(path: Path) -> str:
    kind = filetype.guess(str(path))
    if kind is None:
        return "application/octet-stream"
    return kind.mime


def media_type_for_mime(mime_type: str) -> str | None:
    if mime_type.startswith(_PHOTO_MIME_PREFIXES):
        return "photo"
    if mime_type.startswith(_VIDEO_MIME_PREFIXES):
        return "video"
    return None
