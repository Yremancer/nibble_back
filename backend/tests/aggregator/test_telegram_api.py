from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from src.app import app


def post(message_id, *, album=False):
    media = f'''<a class="tgme_widget_message_photo_wrap grouped_media_wrap"
      href="https://t.me/testchannel/{message_id}?single"
      style="background-image:url('https://cdn4.telesco.pe/photo.jpg')"></a>
      <a class="grouped_media_wrap" href="https://t.me/testchannel/{message_id + 1}?single">
        <video class="js-message_video" src="https://cdn4.telesco.pe/video.mp4"></video>
      </a>''' if album else ""
    return f'''<div class="tgme_widget_message" data-post="testchannel/{message_id}">
      <div class="tgme_widget_message_text">Отчёт {message_id}</div>{media}
      <a class="tgme_widget_message_date"><time datetime="2026-11-13T10:00:00+00:00"></time></a>
    </div>'''


def page(*posts, before=None):
    more = f'<a class="tme_messages_more" data-before="{before}"></a>' if before else ""
    return more + "".join(posts)


@pytest.fixture
def upstream():
    return SimpleNamespace(responses=[httpx.Response(200, text=page(post(1)))], error=None, requests=[])


@pytest.fixture
async def api(upstream, monkeypatch):
    def respond(request):
        upstream.requests.append(request)
        if upstream.error is not None:
            raise upstream.error
        return upstream.responses.pop(0) if len(upstream.responses) > 1 else upstream.responses[0]

    monkeypatch.setattr("src.aggregator.sources.telegram_public.asyncio.sleep", AsyncMock())
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as outbound:
        monkeypatch.setattr(app.state, "http", outbound, raising=False)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            yield client


async def test_limit_paginates_newest_first_and_returns_album_media(api, upstream):
    upstream.responses = [
        httpx.Response(200, text=page(post(10), post(12, album=True), before=10)),
        httpx.Response(200, text=page(post(8), post(9))),
    ]
    response = await api.get("/aggregator/telegram", params={"channel": "testchannel", "limit": 3})
    assert response.status_code == 200
    data = response.json()
    assert [item["external_id"] for item in data] == ["12", "10", "9"]
    assert data[0]["text"] == "Отчёт 12"
    assert data[0]["all_message_ids"] == [12, 13]
    assert data[0]["original_url"] == "https://t.me/testchannel/12"
    assert data[0]["media"] == [
        {"url": "https://cdn4.telesco.pe/photo.jpg", "media_type": "photo"},
        {"url": "https://cdn4.telesco.pe/video.mp4", "media_type": "video"},
    ]
    assert len(upstream.requests) == 2
    assert upstream.requests[1].url.params["before"] == "10"


async def test_short_history_returns_available_posts(api, upstream):
    response = await api.get("/aggregator/telegram", params={"channel": "testchannel", "limit": 5})
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert len(upstream.requests) == 1


@pytest.mark.parametrize("params", [
    {"channel": "testchannel", "limit": limit} for limit in (0, -1, 51, "abc")
] + [{}, {"channel": "@channel"}, {"channel": "https://t.me/channel"},
     {"channel": "../channel"}, {"channel": "-100123"}, {"channel": "a" * 33}])
async def test_invalid_parameters_fail_before_fetch(api, upstream, params):
    assert (await api.get("/aggregator/telegram", params=params)).status_code == 422
    assert upstream.requests == []


@pytest.mark.parametrize("failure", ["http", "timeout", "connect", "private", "malformed"])
async def test_upstream_failure_returns_readable_502(api, upstream, failure):
    if failure == "http":
        upstream.responses = [httpx.Response(403)]
    elif failure == "timeout":
        upstream.error = httpx.ReadTimeout("timeout")
    elif failure == "connect":
        upstream.error = httpx.ConnectError("connection failed")
    elif failure == "private":
        upstream.responses = [httpx.Response(200, text="<html>Private channel</html>")]
    else:
        upstream.responses = [httpx.Response(200, text='<div class="tgme_widget_message" data-post="testchannel/1"></div>')]
    response = await api.get("/aggregator/telegram", params={"channel": "testchannel"})
    assert response.status_code == 502
    assert "Telegram" in response.json()["detail"]


async def test_swagger_exposes_channel_limit_and_media(api):
    schema = (await api.get("/openapi.json")).json()
    operation = schema["paths"]["/aggregator/telegram"]["get"]
    parameters = {p["name"]: p for p in operation["parameters"]}
    assert parameters["channel"]["required"] is True
    limit = parameters["limit"]["schema"]
    assert (limit["minimum"], limit["maximum"], limit["default"]) == (1, 50, 5)
    assert "media" in schema["components"]["schemas"]["TelegramPostPreview"]["properties"]
