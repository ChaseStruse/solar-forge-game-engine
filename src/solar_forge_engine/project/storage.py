"""Bounded JSON reads and same-directory atomic scene writes."""

import json
import os
import tempfile
from pathlib import Path

from solar_forge_engine.core.scene import Scene

MAX_FILE_BYTES = 4 * 1024 * 1024


def load_scene(path: Path) -> Scene:
    with path.open("rb") as handle:
        raw = handle.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Scene files must be smaller than 4 MiB.")
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("format_version") in (4, 6, 8, 10):
            raise ValueError("This scene uses project assets. Use File → Open project instead.")
        return Scene.from_data(data)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("This file is not a valid UTF-8 JSON scene.") from error


def save_scene(path: Path, scene: Scene) -> None:
    save_scene_data(path, scene.to_data())


def save_scene_data(path: Path, data: dict[str, object], *, exclusive: bool = False) -> None:
    """Write validated scene data, preserving supported originals before upgrades."""
    if path.is_symlink():
        raise ValueError("Choose a regular file instead of saving through a symbolic link.")
    raw = (json.dumps(data, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Scene files must be smaller than 4 MiB.")
    if exclusive and path.exists():
        raise FileExistsError("A scene with this filename already exists.")
    if path.exists():
        with path.open("rb") as handle:
            previous = handle.read(MAX_FILE_BYTES + 1)
        try:
            previous_data = json.loads(previous) if len(previous) <= MAX_FILE_BYTES else None
        except ValueError, UnicodeDecodeError, RecursionError:
            previous_data = None
        if (
            isinstance(previous_data, dict)
            and type(previous_data.get("format_version")) is int
            and previous_data["format_version"] in (1, 2, 3, 4, 5, 6, 7, 8, 9)
            and previous_data["format_version"] < data["format_version"]
        ):
            # Project v4/v6 carry asset references; retain its opaque bytes exactly.
            # Its references are validated by the project loader, not Scene.from_data.
            if previous_data["format_version"] not in (4, 6, 8):
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
    atomic_write(path, raw, exclusive=exclusive)


def atomic_write(path: Path, raw: bytes, *, exclusive: bool = False) -> None:
    """Publish bytes through a flushed same-directory temporary file."""
    if path.is_symlink():
        raise ValueError("Do not write through symbolic links.")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".forge-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if exclusive:
            os.link(temporary, path)
        else:
            os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
