"""Потоковая загрузка внешних вложений с защитой от SSRF.

Запрещает обращения к локальным/служебным адресам и проверяет каждый шаг
редиректа отдельно (источник не должен иметь возможность направить
загрузчик во внутреннюю сеть через 3xx-ответ).
"""

import ipaddress
import socket
from contextlib import suppress
from pathlib import Path
from urllib.parse import urlparse

import httpx
from src.storage.exceptions import DownloadError, FileTooLargeError, UnsafeUrlError

_MAX_REDIRECTS = 5


def _is_private_address(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"не удалось разрешить адрес: {host}") from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return True
    return False


def _assert_safe_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise UnsafeUrlError(f"недопустимая схема: {parsed.scheme}")
    if not parsed.hostname:
        raise UnsafeUrlError("нет хоста в URL")
    if _is_private_address(parsed.hostname):
        raise UnsafeUrlError(f"адрес указывает на локальную/служебную сеть: {url}")


async def download_to_file(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    max_size_bytes: int,
) -> int:
    """Скачивает url в dest потоково, проверяя каждый редирект на SSRF и
    обрывая загрузку при превышении лимита по фактически полученным байтам.
    Возвращает размер файла. Не публикует частично скачанный файл: при
    ошибке временный файл удаляется вызывающим кодом."""

    current_url = url
    for _ in range(_MAX_REDIRECTS + 1):
        _assert_safe_url(current_url)
        async with client.stream("GET", current_url, follow_redirects=False) as resp:
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if not location:
                    raise DownloadError(f"редирект без Location: {current_url}")
                current_url = httpx.URL(current_url).join(location).human_repr()
                continue

            resp.raise_for_status()
            written = 0
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    written += len(chunk)
                    if written > max_size_bytes:
                        with suppress(OSError):
                            dest.unlink()
                        raise FileTooLargeError(
                            f"файл превышает лимит {max_size_bytes} байт: {url}"
                        )
                    f.write(chunk)
            return written

    raise DownloadError(f"слишком много редиректов: {url}")
