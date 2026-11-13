"""Нормализация текста публикации: удаление служебных блоков источника и
подготовка хеша содержимого для точной дедупликации.

Очистка настраивается по источнику (см. sources.json -> normalization) и не
должна удалять произвольные ссылки/контакты во всех публикациях — только
распознанный шаблон конкретного канала (см. ТЗ, раздел 8).
"""

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
    """Возвращает (очищенный_текст, удалённый_фрагмент_или_None).
    rules — список NormalizationRule (pattern/flags) для конкретного источника."""
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
    """Схлопывает пробелы и приводит регистр для сравнения точных дублей и
    построения content_hash. Не меняет смысл текста."""
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
