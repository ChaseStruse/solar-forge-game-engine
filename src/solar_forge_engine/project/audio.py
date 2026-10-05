"""Bounded, project-owned PCM sounds; no executable content or source paths persist."""

import hashlib
import io
import os
import re
import stat
import wave
from dataclasses import dataclass
from pathlib import Path

from solar_forge_engine.project.storage import atomic_write
from solar_forge_engine.project.workspace import Project

MAX_SOUND_BYTES = 4 * 1024 * 1024
MAX_LIBRARY_BYTES = 32 * 1024 * 1024
MAX_SOUNDS = 128
_SOUND_NAME = re.compile(r"([a-z0-9-]{1,48})--([a-f0-9]{64})\.wav")


@dataclass(frozen=True)
class Sound:
    reference: str
    frames: int
    rate: int
    channels: int
    width: int

    @property
    def name(self) -> str:
        return Path(self.reference).name.split("--")[0].replace("-", " ")

    @property
    def duration(self) -> float:
        return self.frames / self.rate


def _read(path: Path) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("Sounds must be regular files.")
        raw = handle.read(MAX_SOUND_BYTES + 1)
    if len(raw) > MAX_SOUND_BYTES:
        raise ValueError("Sounds must be no larger than 4 MiB.")
    return raw


def decode_wav(raw: bytes, reference: str = "") -> tuple[Sound, bytes]:
    """Return validated metadata and PCM; restrict preview to small uncompressed clips."""
    if len(raw) > MAX_SOUND_BYTES:
        raise ValueError("Sounds must be no larger than 4 MiB.")
    if len(raw) < 12 or raw[:4] != b"RIFF" or int.from_bytes(raw[4:8], "little") != len(raw) - 8:
        raise ValueError("Choose a complete RIFF WAV file.")
    try:
        with wave.open(io.BytesIO(raw), "rb") as handle:
            sound = Sound(
                reference,
                handle.getnframes(),
                handle.getframerate(),
                handle.getnchannels(),
                handle.getsampwidth(),
            )
            if (
                handle.getcomptype() != "NONE"
                or sound.channels not in (1, 2)
                or sound.width not in (1, 2)
                or not 8000 <= sound.rate <= 48000
                or not 0 < sound.frames <= sound.rate * 30
            ):
                raise ValueError(
                    "Use clips up to 30 seconds: mono/stereo PCM WAV, 8/16 bit, 8–48 kHz."
                )
            pcm = handle.readframes(sound.frames + 1)
            if len(pcm) != sound.frames * sound.channels * sound.width:
                raise ValueError("WAV sample data is truncated or misaligned.")
    except (wave.Error, EOFError) as error:
        raise ValueError("Invalid or unsupported PCM WAV file.") from error
    return sound, pcm


def _folder(project: Project) -> Path:
    project.scene_path()
    folder = project.root / "audio"
    if folder.is_symlink() or (folder.exists() and not folder.is_dir()):
        raise ValueError("Project audio must use a regular audio directory.")
    return folder


def load_sound(project: Project, reference: str) -> tuple[Sound, bytes]:
    if not reference.startswith("audio/") or not _SOUND_NAME.fullmatch(reference[6:]):
        raise ValueError("Invalid project sound reference.")
    raw = _read(_folder(project) / reference[6:])
    match = _SOUND_NAME.fullmatch(reference[6:])
    assert match is not None
    if hashlib.sha256(raw).hexdigest() != match[2]:
        raise ValueError("Project sound content changed; its fingerprint no longer matches.")
    return decode_wav(raw, reference)


def list_sounds(project: Project) -> tuple[Sound, ...]:
    folder = _folder(project)
    if not folder.exists():
        return ()
    sounds: list[Sound] = []
    total = 0
    with os.scandir(folder) as entries:
        for entry in entries:
            if entry.name.startswith(".forge-"):
                continue
            if not _SOUND_NAME.fullmatch(entry.name) or not entry.is_file(follow_symlinks=False):
                raise ValueError("Unexpected file in audio/. Restore it before importing sounds.")
            if len(sounds) >= MAX_SOUNDS:
                raise ValueError("The sound library supports at most 128 clips.")
            total += entry.stat(follow_symlinks=False).st_size
            if total > MAX_LIBRARY_BYTES:
                raise ValueError("The sound library supports at most 32 MiB.")
            sounds.append(load_sound(project, f"audio/{entry.name}")[0])
    return tuple(sorted(sounds, key=lambda sound: sound.reference))


def import_wav(project: Project, source: Path) -> Sound:
    sound, pcm = decode_wav(_read(source))
    # Strip source metadata and publish a canonical PCM-only file.
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setparams((sound.channels, sound.width, sound.rate, sound.frames, "NONE", ""))
        handle.writeframes(pcm)
    raw = buffer.getvalue()
    fingerprint = hashlib.sha256(raw).hexdigest()
    existing = list_sounds(project)
    for entry in existing:
        if entry.reference.endswith(f"--{fingerprint}.wav"):
            return entry
    if len(existing) >= MAX_SOUNDS:
        raise ValueError("The sound library supports at most 128 clips.")
    folder = _folder(project)
    total = sum((folder / Path(entry.reference).name).stat().st_size for entry in existing)
    if total + len(raw) > MAX_LIBRARY_BYTES:
        raise ValueError("The sound library supports at most 32 MiB.")
    name = re.sub(r"[^a-z0-9]+", "-", source.stem.lower()).strip("-")[:48] or "sound"
    reference = f"audio/{name}--{fingerprint}.wav"
    folder.mkdir(exist_ok=True)
    atomic_write(folder / Path(reference).name, raw, exclusive=True)
    return Sound(reference, sound.frames, sound.rate, sound.channels, sound.width)
