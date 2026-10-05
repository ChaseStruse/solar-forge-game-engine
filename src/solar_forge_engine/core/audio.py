"""Portable, bounded PCM data; no source paths, devices or editor dependencies."""

import base64
import binascii
from dataclasses import dataclass

MAX_PCM_BYTES = 4 * 1024 * 1024
MAX_ENCODED_PCM = ((MAX_PCM_BYTES + 2) // 3) * 4


@dataclass(frozen=True)
class SoundClip:
    rate: int
    channels: int
    width: int
    samples: str

    def __post_init__(self) -> None:
        if (
            type(self.rate) is not int
            or not 8000 <= self.rate <= 48000
            or type(self.channels) is not int
            or self.channels not in (1, 2)
            or type(self.width) is not int
            or self.width not in (1, 2)
        ):
            raise ValueError("Use mono/stereo PCM, 8/16 bit, 8–48 kHz.")
        if not isinstance(self.samples, str) or len(self.samples) > MAX_ENCODED_PCM:
            raise ValueError("Sound sample data exceeds its size limit.")
        try:
            raw = base64.b64decode(self.samples, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("Sound samples must be valid base64 PCM.") from error
        if (
            not raw
            or len(raw) > MAX_PCM_BYTES
            or len(raw) % (self.channels * self.width)
            or len(raw) > self.rate * self.channels * self.width * 30
            or base64.b64encode(raw).decode("ascii") != self.samples
        ):
            raise ValueError("Sound samples must be aligned PCM, nonempty and at most 30 seconds.")

    @property
    def duration(self) -> float:
        size = len(self.samples) // 4 * 3 - (len(self.samples) - len(self.samples.rstrip("=")))
        return size / (self.channels * self.width * self.rate)

    @classmethod
    def from_data(cls, value: object) -> "SoundClip":
        if not isinstance(value, dict) or set(value) != {"rate", "channels", "width", "samples"}:
            raise ValueError("Invalid sound clip fields.")
        return cls(value["rate"], value["channels"], value["width"], value["samples"])
