import uuid

from src.storage.exceptions import FileTooLargeError, UnsupportedFileTypeError
from src.storage.mime import (
    EXTENSIONS,
    MP4,
    SIGNATURES,
    WEBM,
    WEBP,
)
from src.storage.policy import Category


def detect_content_type(data: bytes) -> str:
    for signature, content_type in SIGNATURES.items():
        if data.startswith(signature):
            return content_type

    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return WEBP

    if len(data) >= 12 and data[4:8] == b"ftyp":
        return MP4

    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return WEBM

    raise UnsupportedFileTypeError


def check_allowed(data: bytes, content_type: str, category: Category) -> None:
    if content_type not in category.allowed_types:
        raise UnsupportedFileTypeError
    if len(data) > category.max_bytes:
        raise FileTooLargeError


def build_key(category: Category, content_type: str) -> str:
    return f"{category.name}/{uuid.uuid4().hex}{EXTENSIONS[content_type]}"
