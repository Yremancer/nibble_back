"""Проверка защиты от SSRF при скачивании вложений: запрет на локальные/
служебные адреса и обрыв при превышении лимита размера."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
from src.aggregator.exceptions import UnsafeUrlError
from src.aggregator.safe_fetch import download_to_file
from src.storage.exceptions import FileTooLargeError

# cdn.example.com не резолвится в тестовом окружении без сети; подменяем
# разрешение DNS, чтобы проверять логику скачивания отдельно от SSRF-фильтра
# (его отдельно проверяют test_*_is_rejected с реальными приватными IP).
_FAKE_PUBLIC_ADDRINFO = [(2, 1, 6, "", ("93.184.216.34", 0))]


@pytest.mark.asyncio
async def test_localhost_url_is_rejected():
    async with httpx.AsyncClient() as client:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            with pytest.raises(UnsafeUrlError):
                await download_to_file(client, "http://127.0.0.1:8000/secret", dest, 1024)


@pytest.mark.asyncio
async def test_private_network_url_is_rejected():
    async with httpx.AsyncClient() as client:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            with pytest.raises(UnsafeUrlError):
                await download_to_file(client, "http://192.168.1.1/admin", dest, 1024)


@pytest.mark.asyncio
@respx.mock
@patch("socket.getaddrinfo", return_value=_FAKE_PUBLIC_ADDRINFO)
async def test_oversized_download_is_aborted(_mock_dns):
    respx.get("https://cdn.example.com/big.jpg").mock(
        return_value=httpx.Response(200, content=b"x" * 2000)
    )

    async with httpx.AsyncClient() as client:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            with pytest.raises(FileTooLargeError):
                await download_to_file(client, "https://cdn.example.com/big.jpg", dest, 1000)
            assert not dest.exists(), "частично скачанный файл не должен оставаться"


@pytest.mark.asyncio
@respx.mock
@patch("socket.getaddrinfo", return_value=_FAKE_PUBLIC_ADDRINFO)
async def test_valid_download_succeeds(_mock_dns):
    respx.get("https://cdn.example.com/photo.jpg").mock(
        return_value=httpx.Response(200, content=b"fake-image-bytes")
    )

    async with httpx.AsyncClient() as client:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out.bin"
            size = await download_to_file(
                client, "https://cdn.example.com/photo.jpg", dest, 1_000_000
            )
            assert size == len(b"fake-image-bytes")
            assert dest.read_bytes() == b"fake-image-bytes"


@pytest.mark.asyncio
@respx.mock
@patch("socket.getaddrinfo", return_value=_FAKE_PUBLIC_ADDRINFO)
async def test_redirect_download_succeeds(_mock_dns):
    respx.get("https://cdn.example.com/start").mock(
        return_value=httpx.Response(302, headers={"Location": "/photo.jpg"})
    )
    respx.get("https://cdn.example.com/photo.jpg").mock(
        return_value=httpx.Response(200, content=b"image")
    )
    async with httpx.AsyncClient() as client:
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "photo.jpg"
            assert await download_to_file(client, "https://cdn.example.com/start", dest, 100) == 5
