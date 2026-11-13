"""Сценарий 5: служебный хвост не превращает отчёт в рекламу — проверяем,
что normalize/text корректно вырезает боилерплейт ulov25r и не трогает
произвольные ссылки/контакты в других публикациях (см. ТЗ, раздел 8)."""

from src.aggregator.config import NormalizationRule
from src.aggregator.normalize.text import content_hash, normalize_for_hash, strip_boilerplate

ULOV25R_RULE = NormalizationRule(
    pattern=(
        r"Рыболовные места.*?Купи-продай.*?Группа общение.*?"
        r"(пришл(и|ите) (свой )?отчёт.*)?$"
    )
)


def test_boilerplate_is_removed_and_preserved_separately():
    raw_text = (
        "Отличная рыбалка сегодня на Русском, поймал пару терпугов.\n\n"
        "Рыболовные места: t.me/places\n"
        "Купи-продай: t.me/market\n"
        "Группа общение: t.me/chat\n"
        "Пришлите свой отчёт нам в лс!"
    )

    cleaned, removed = strip_boilerplate(raw_text, [ULOV25R_RULE])

    assert "Отличная рыбалка сегодня" in cleaned
    assert "Купи-продай" not in cleaned
    assert "Рыболовные места" not in cleaned
    assert removed is not None
    assert "Купи-продай" in removed


def test_arbitrary_links_not_removed_without_matching_rule():
    """Публикация о происшествии со ссылкой/контактом не должна лишиться
    текста из-за общего правила другого источника."""
    raw_text = "ЧП на льду бухты, спасатели МЧС: +7-900-000-00-00, подробности t.me/news/123"

    cleaned, removed = strip_boilerplate(raw_text, [ULOV25R_RULE])

    assert cleaned == raw_text
    assert removed is None


def test_exact_duplicate_hash_matches_regardless_of_whitespace():
    text_a = "Поймал   терпуга\nна Русском."
    text_b = "поймал терпуга на русском."

    assert content_hash(normalize_for_hash(text_a)) == content_hash(normalize_for_hash(text_b))
