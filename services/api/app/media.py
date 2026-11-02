"""Private raster assets: decode, bound pixels, re-encode, strip metadata."""

import hashlib
import io
import os
import warnings
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.db import uid

MAX_BYTES = 5 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 16_000_000


def asset_root():
    root = Path(os.getenv("ASSET_ROOT", "/tmp/prospectos-assets")).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def sanitize_image(payload: bytes):
    if not payload or len(payload) > MAX_BYTES:
        raise HTTPException(413, "Bild darf höchstens 5 MB groß sein.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(payload))
            if (
                image.format not in ("PNG", "JPEG", "WEBP")
                or image.width * image.height > 16_000_000
            ):
                raise ValueError()
            image.load()
            image = image.convert("RGB")
            output = io.BytesIO()
            image.save(output, format="JPEG", quality=90)
    except (
        UnidentifiedImageError,
        ValueError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        raise HTTPException(
            422,
            "Nur gültige PNG-, JPEG- oder WebP-Bilder mit höchstens 16 Megapixeln sind erlaubt.",
        ) from None
    data = output.getvalue()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Das verarbeitete Bild ist zu groß.")
    return data


def store_image(payload: bytes):
    data = sanitize_image(payload)
    key = uid() + ".jpg"
    path = asset_root() / key
    with path.open("xb") as output:
        output.write(data)
    path.chmod(0o600)
    return key, len(data), hashlib.sha256(data).hexdigest()


def private_path(key: str):
    # Only server-issued keys reach this function; fail closed even with corrupt metadata.
    path = (asset_root() / key).resolve()
    if path.parent != asset_root() or not path.is_file():
        raise HTTPException(404, "Datei nicht gefunden.")
    return path
