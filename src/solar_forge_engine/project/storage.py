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
        return Scene.from_data(json.loads(raw))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("This file is not a valid UTF-8 JSON scene.") from error


def save_scene(path: Path, scene: Scene) -> None:
    if path.is_symlink():
        raise ValueError("Choose a regular file instead of saving through a symbolic link.")
    raw = (json.dumps(scene.to_data(), indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Scene files must be smaller than 4 MiB.")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".forge-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
