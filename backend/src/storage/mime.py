JPEG = "image/jpeg"
PNG = "image/png"
WEBP = "image/webp"
MP4 = "video/mp4"
WEBM = "video/webm"

EXTENSIONS = {
    JPEG: ".jpg",
    PNG: ".png",
    WEBP: ".webp",
    MP4: ".mp4",
    WEBM: ".webm",
}

SIGNATURES = {
    b"\xff\xd8\xff": JPEG,
    b"\x89PNG\r\n\x1a\n": PNG,
}
