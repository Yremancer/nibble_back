
import hashlib
import re
import unicodedata

NORMALIZATION_VERSION = "v1"

_FLAG_MAP = {
    "IGNORECASE": re.IGNORECASE,
    "DOTALL": re.DOTALL,
    "MULTILINE": re.MULTILINE,
}


def _compile_flags(flags: str) -> int:
    result = 0
    for part in flags.split("|"):
        part = part.strip()
        if part:
            result |= _FLAG_MAP[part]
    return result


def strip_boilerplate(text: str, rules: list) -> tuple[str, str | None]:
    removed_parts: list[str] = []
    cleaned = text
    for rule in rules:
        pattern = re.compile(rule.pattern, _compile_flags(rule.flags))
        match = pattern.search(cleaned)
        if match:
            removed_parts.append(match.group(0))
            cleaned = cleaned[: match.start()] + cleaned[match.end() :]
    cleaned = cleaned.rstrip()
    removed = "\n---\n".join(removed_parts) if removed_parts else None
    return cleaned, removed


def normalize_for_hash(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def content_hash(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def normalize_post_text(raw_text: str, boilerplate_rules: list) -> dict:
    cleaned, removed = strip_boilerplate(raw_text, boilerplate_rules)
    normalized = normalize_for_hash(cleaned)
    return {
        "original_text": raw_text,
        "normalized_text": cleaned,
        "removed_boilerplate": removed,
        "hash_text": normalized,
        "content_hash": content_hash(normalized),
        "normalization_version": NORMALIZATION_VERSION,
    }
