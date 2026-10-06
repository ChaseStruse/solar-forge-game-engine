"""Bounded JSON reads and same-directory atomic scene writes."""

import fcntl
import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from solar_forge_engine.core.limits import MAX_FILE_BYTES as MAX_FILE_BYTES
from solar_forge_engine.core.scene import Scene


class PublicationBusy(ValueError):
    """A cooperating metadata writer currently holds the publication guard."""


def read_regular_bytes(path: Path, maximum: int) -> bytes | None:
    """Read at most maximum + 1 bytes; missing files return None, unsafe files fail."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("Project data files must be regular files.")
        return handle.read(maximum + 1)


def read_scene_bytes(path: Path) -> bytes | None:
    """Read a bounded regular file without following links or waiting on a FIFO."""
    raw = read_regular_bytes(path, MAX_FILE_BYTES)
    if raw is None:
        return None
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Scene files must be smaller than 4 MiB.")
    return raw


def check_file_revision(path: Path, expected_fingerprint: str) -> None:
    current = read_scene_bytes(path)
    if current is None or hashlib.sha256(current).hexdigest() != expected_fingerprint:
        raise ValueError("The scene file changed during saving. Use Save As or reopen it.")


def load_scene(path: Path) -> Scene:
    raw = read_scene_bytes(path)
    if raw is None:
        raise FileNotFoundError(f"Scene file is missing: {path.name}")
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("format_version") in (4, 6, 8, 10, 12):
            raise ValueError("This scene uses project assets. Use File → Open project instead.")
        return Scene.from_data(data)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("This file is not a valid UTF-8 JSON scene.") from error


def save_scene(
    path: Path, scene: Scene, *, exclusive: bool = False, expected_fingerprint: str | None = None
) -> None:
    save_scene_data(
        path, scene.to_data(), exclusive=exclusive, expected_fingerprint=expected_fingerprint
    )


def save_scene_data(
    path: Path,
    data: dict[str, object],
    *,
    exclusive: bool = False,
    expected_fingerprint: str | None = None,
) -> None:
    """Write validated scene data, preserving supported originals before upgrades."""
    with publication_guard(path):
        _publish_scene_data(path, data, exclusive, expected_fingerprint)


@contextmanager
def publication_guard(path: Path) -> Iterator[None]:
    """Coordinate engine metadata publication on a local Linux directory inode."""
    # A directory inode survives scene replacement and needs no persistent sidecar.
    # This coordinates engine writers on local Linux filesystems, not arbitrary tools.
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise PublicationBusy(
                "Another save is in progress in this folder. Retry saving."
            ) from error
        yield
    finally:
        os.close(descriptor)


def _publish_scene_data(
    path: Path, data: dict[str, object], exclusive: bool, expected_fingerprint: str | None
) -> None:
    if expected_fingerprint is not None:
        check_file_revision(path, expected_fingerprint)
    if path.is_symlink():
        raise ValueError("Choose a regular file instead of saving through a symbolic link.")
    raw = (json.dumps(data, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Scene files must be smaller than 4 MiB.")
    if exclusive and path.exists():
        raise FileExistsError("A scene with this filename already exists.")
    if path.exists():
        previous = read_scene_bytes(path)
        if previous is None:
            raise ValueError("The scene disappeared during saving.")
        try:
            previous_data = json.loads(previous) if len(previous) <= MAX_FILE_BYTES else None
        except ValueError, UnicodeDecodeError, RecursionError:
            previous_data = None
        if (
            isinstance(previous_data, dict)
            and type(previous_data.get("format_version")) is int
            and previous_data["format_version"] in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)
            and previous_data["format_version"] < data["format_version"]
        ):
            # Project v4/v6 carry asset references; retain its opaque bytes exactly.
            # Its references are validated by the project loader, not Scene.from_data.
            if previous_data["format_version"] not in (4, 6, 8, 10):
                Scene.from_data(previous_data)
            backup = path.with_name(f"{path.name}.v{previous_data['format_version']}.bak")
            try:
                with backup.open("xb") as handle:
                    handle.write(previous)
                    handle.flush()
                    os.fsync(handle.fileno())
            except FileExistsError as error:
                raise ValueError(
                    "Legacy scene backup already exists. Use Save As to keep both copies."
                ) from error
            flush_directory(path.parent)
    atomic_write(path, raw, exclusive=exclusive, expected_fingerprint=expected_fingerprint)


def atomic_write(
    path: Path,
    raw: bytes,
    *,
    exclusive: bool = False,
    expected_fingerprint: str | None = None,
    mode: int = 0o600,
) -> None:
    """Publish bytes through a flushed same-directory temporary file."""
    if path.is_symlink():
        raise ValueError("Do not write through symbolic links.")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".forge-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fchmod(handle.fileno(), mode)
            os.fsync(handle.fileno())
        if expected_fingerprint is not None:
            check_file_revision(path, expected_fingerprint)
        if exclusive:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
        flush_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def flush_directory(path: Path) -> None:
    """Flush directory entries after publication or before dependent writes."""
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
