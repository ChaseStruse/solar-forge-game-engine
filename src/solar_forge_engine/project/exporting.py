"""Export a single applied scene with an explicit allowlist of trusted runtime code."""

import io
import json
import zipfile
from importlib.resources import files
from pathlib import Path

from solar_forge_engine.core.limits import MAX_FILE_BYTES
from solar_forge_engine.core.scene import Scene
from solar_forge_engine.project.storage import atomic_write
from solar_forge_engine.runtime.simulation import controlled_entity

RUNTIME_FILES = (
    "LICENSE.txt",
    "__init__.py",
    "core/__init__.py",
    "core/limits.py",
    "core/commands.py",
    "core/scene.py",
    "core/sprite.py",
    "core/animation.py",
    "core/audio.py",
    "runtime/__init__.py",
    "runtime/application.py",
    "runtime/exported.py",
    "runtime/player.py",
    "runtime/scripting.py",
    "runtime/script_worker.py",
    "runtime/rendering.py",
    "runtime/simulation.py",
    "runtime/audio.py",
)
ENTRY_POINT = """import sys
if sys.version_info[:2] != (3, 14):
    print("This game requires Python 3.14.", file=sys.stderr)
    raise SystemExit(1)
try:
    from solar_forge_engine.runtime.exported import main
except ImportError as error:
    print("Install PySide6-Essentials 6.11.2 and its Linux libraries to run this game.",
          file=sys.stderr)
    print(str(error), file=sys.stderr)
    raise SystemExit(1)
raise SystemExit(main())
"""


def export_game(path: Path, scene: Scene) -> int:
    """Publish an exclusive native zipapp; Python and Qt remain system prerequisites."""
    if path.suffix.lower() != ".pyz":
        raise ValueError("Native game archives must use the .pyz extension.")
    snapshot = json.dumps(
        {"format_version": 1, "control": controlled_entity(scene), "scene": scene.to_data()},
        allow_nan=False,
    ).encode("utf-8")
    if len(snapshot) > MAX_FILE_BYTES:
        raise ValueError("Game snapshots must be smaller than 4 MiB.")
    buffer = io.BytesIO()
    # Linux env -S supports the isolated interpreter flag without depending on a venv path.
    buffer.write(b"#!/usr/bin/env -S python3 -I\n")
    resources = files("solar_forge_engine")
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in RUNTIME_FILES:
            raw = resources.joinpath(relative).read_bytes()
            if len(raw) > 256 * 1024:
                raise ValueError("A runtime source module exceeds the export limit.")
            _entry(archive, f"solar_forge_engine/{relative}", raw)
        _entry(archive, "__main__.py", ENTRY_POINT.encode())
        _entry(archive, "game_data/__init__.py", b'"""Bundled game data."""\n')
        _entry(archive, "game_data/scene.json", snapshot)
    raw = buffer.getvalue()
    atomic_write(path, raw, exclusive=True, mode=0o755)
    return len(raw)


def _entry(archive: zipfile.ZipFile, name: str, raw: bytes) -> None:
    entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = 0o644 << 16
    archive.writestr(entry, raw)
