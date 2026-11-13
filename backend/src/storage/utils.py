import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

from PIL import Image


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_object_key(sha256: str, extension: str) -> str:
    """Ключ на основе содержимого: одинаковый файл всегда получает один и
    тот же ключ, что даёт естественную дедупликацию в S3."""
    return f"media/{sha256[:2]}/{sha256[2:4]}/{sha256}{extension}"


def image_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with Image.open(path) as img:
            return img.width, img.height
    except Exception:  # noqa: BLE001 - битый/неподдерживаемый файл
        return None


async def probe_video(path: Path) -> dict | None:
    """ffprobe: ширина/высота/длительность видео. Возвращает None, если
    ffprobe недоступен или файл не распознан как видео."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        data = json.loads(stdout)
        stream = (data.get("streams") or [{}])[0]
        duration = data.get("format", {}).get("duration")
        return {
            "width": stream.get("width"),
            "height": stream.get("height"),
            "duration_s": int(float(duration)) if duration else None,
        }
    except (FileNotFoundError, json.JSONDecodeError, IndexError):
        return None


async def make_video_preview(source: Path, dest: Path) -> bool:
    """Кадр на первой секунде видео как превью. Оригинал не перекодируется."""
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        "00:00:01",
        "-i",
        str(source),
        "-frames:v",
        "1",
        str(dest),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        await proc.communicate()
        return proc.returncode == 0 and dest.exists()
    except FileNotFoundError:
        return False
