"""Normalize a user-selected PNG into bounded, path-free scene data."""

import base64
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtGui import QImage, QImageReader

from solar_forge_engine.core.sprite import MAX_SPRITE_SIDE, Sprite

MAX_PNG_BYTES = 2 * 1024 * 1024


def import_png(path: Path) -> Sprite:
    if not path.is_file():
        raise ValueError("Choose a regular PNG file.")
    with path.open("rb") as handle:
        raw = handle.read(MAX_PNG_BYTES + 1)
    if len(raw) > MAX_PNG_BYTES:
        raise ValueError("PNG imports must be no larger than 2 MiB.")
    buffer = QBuffer()
    buffer.setData(QByteArray(raw))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer, b"png")
    reader.setAutoDetectImageFormat(False)
    size = reader.size()
    if not (1 <= size.width() <= MAX_SPRITE_SIDE and 1 <= size.height() <= MAX_SPRITE_SIDE):
        raise ValueError("Choose a valid PNG no larger than 256 × 256 pixels.")
    image = reader.read()
    if image.isNull():
        raise ValueError("The PNG could not be decoded.")
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    pixels = base64.b64encode(bytes(image.constBits())).decode("ascii")
    return Sprite(image.width(), image.height(), pixels)
