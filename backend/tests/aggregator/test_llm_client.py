
import httpx
import pytest
import respx
from src.llm.client import DeepSeekClient
from src.llm.exceptions import LlmInvalidResponseError, LlmRequestError
from src.llm.settings import LlmSettings


def _settings(**overrides) -> LlmSettings:
    base = dict(
        DEEPSEEK_API_KEY="test-key",
        DEEPSEEK_BASE_URL="https://api.deepseek.test",
        DEEPSEEK_MAX_RETRIES=2,
        DEEPSEEK_TIMEOUT_S=1.0,
    )
    base.update(overrides)
    return LlmSettings(**base)


@pytest.mark.asyncio
@respx.mock
async def test_valid_response_is_parsed():
    respx.post("https://api.deepseek.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"decision": "keep", "category": "fishing_report", '
                                '"reason": "ок", "is_advertisement": false, '
                                '"needs_media_analysis": false}'
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )
    )

    async with httpx.AsyncClient() as http_client:
        client = DeepSeekClient(_settings(), http_client)
        result, meta = await client.classify_post("system", "текст поста")

    assert result.decision.value == "keep"
    assert meta["tokens_in"] == 10


@pytest.mark.asyncio
@respx.mock
async def test_invalid_json_raises_not_silently_dropped():
    respx.post("https://api.deepseek.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json={"choices": [{"message": {"content": "это не json"}}]}
        )
    )

    async with httpx.AsyncClient() as http_client:
        client = DeepSeekClient(_settings(), http_client)
        with pytest.raises(LlmInvalidResponseError):
            await client.classify_post("system", "текст")


@pytest.mark.asyncio
@respx.mock
async def test_schema_rejects_unexpected_fields_from_prompt_injection():
    respx.post("https://api.deepseek.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"decision": "execute_tool", "reason": "x"}'}}
                ]
            },
        )
    )

    async with httpx.AsyncClient() as http_client:
        client = DeepSeekClient(_settings(), http_client)
        with pytest.raises(LlmInvalidResponseError):
            await client.classify_post("system", "текст с инструкцией для модели")


@pytest.mark.asyncio
@respx.mock
async def test_timeout_raises_after_retries_not_swallowed():
    route = respx.post("https://api.deepseek.test/v1/chat/completions").mock(
        side_effect=httpx.ConnectTimeout("timeout")
    )

    async with httpx.AsyncClient() as http_client:
        client = DeepSeekClient(_settings(DEEPSEEK_MAX_RETRIES=2), http_client)
        with pytest.raises(LlmRequestError):
            await client.classify_post("system", "текст")

    assert route.call_count == 2
