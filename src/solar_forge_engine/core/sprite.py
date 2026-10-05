"""Bounded, portable RGBA sprite data; independent of Qt and source file paths."""

import base64
import binascii
from dataclasses import dataclass

MAX_SPRITE_SIDE = 256
MAX_PIXEL_BYTES = MAX_SPRITE_SIDE * MAX_SPRITE_SIDE * 4
MAX_ENCODED_BYTES = ((MAX_PIXEL_BYTES + 2) // 3) * 4


@dataclass(frozen=True)
class Sprite:
    width: int
    height: int
    pixels: str

    def __post_init__(self) -> None:
        if any(
            type(side) is not int or not 1 <= side <= MAX_SPRITE_SIDE
            for side in (self.width, self.height)
        ):
            raise ValueError("Sprites must be between 1 and 256 pixels on each side.")
        if not isinstance(self.pixels, str) or len(self.pixels) > MAX_ENCODED_BYTES:
            raise ValueError("Sprite pixel data exceeds its size limit.")
        try:
            raw = base64.b64decode(self.pixels, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("Sprite pixels must be valid base64 RGBA data.") from error
        if len(raw) != self.width * self.height * 4:
            raise ValueError("Sprite pixel data does not match its dimensions.")

    @classmethod
    def from_data(cls, value: object) -> "Sprite":
        if not isinstance(value, dict) or set(value) != {"width", "height", "pixels"}:
            raise ValueError("Invalid sprite fields.")
        return cls(value["width"], value["height"], value["pixels"])
