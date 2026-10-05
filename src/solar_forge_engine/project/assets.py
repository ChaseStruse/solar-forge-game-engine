"""Content-addressed project sprites; resolve into portable data before playback."""

import base64
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from solar_forge_engine.core.scene import FORMAT_VERSION, MAX_ENTITIES, Scene
from solar_forge_engine.core.sprite import MAX_PIXEL_BYTES, Sprite
from solar_forge_engine.project.storage import MAX_FILE_BYTES, load_scene, save_scene_data

PROJECT_SCENE_VERSION = 8


def asset_path(root: Path, reference: str) -> Path:
    if not re.fullmatch(r"assets/[0-9a-f]{64}\.rgba", reference):
        raise ValueError("Sprite assets must use a relative content-addressed path inside assets/.")
    if root.is_symlink() or (root / "assets").is_symlink() or (root / reference).is_symlink():
        raise ValueError("Sprite asset paths must not use symbolic links.")
    path = root / reference
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Sprite assets must stay inside the project folder.")
    return path


def digest(width: int, height: int, raw: bytes) -> str:
    return hashlib.sha256(f"{width}x{height}:".encode() + raw).hexdigest()


def read_asset(path: Path) -> bytes:
    if not path.is_file():
        raise ValueError(f"Sprite asset is missing or is not a regular file: {path.name}")
    with path.open("rb") as handle:
        raw = handle.read(MAX_PIXEL_BYTES + 1)
    if len(raw) > MAX_PIXEL_BYTES:
        raise ValueError("Sprite asset exceeds its pixel-data limit.")
    return raw


def store_asset(path: Path, raw: bytes) -> None:
    """Publish immutable bytes only after flushing; never overwrite an existing asset."""
    if path.exists():
        if read_asset(path) != raw:
            raise ValueError(f"Existing sprite asset is damaged: {path.name}")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".sprite-", delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if read_asset(path) != raw:
                    raise ValueError(f"Existing sprite asset is damaged: {path.name}") from None
        finally:
            temporary.unlink(missing_ok=True)


def save_project_scene(root: Path, path: Path, scene: Scene, *, exclusive: bool = False) -> None:
    data = scene.to_data()
    # Keep snapshots bounded for the standalone scene and data-only Play contracts.
    if len(json.dumps(data, indent=2).encode()) + 1 > MAX_FILE_BYTES:
        raise ValueError("Resolved scenes must be smaller than 4 MiB.")
    data["format_version"] = PROJECT_SCENE_VERSION
    entries = data["entities"]
    assert isinstance(entries, list)
    assets: dict[Path, bytes] = {}
    for entity, entry in zip(scene.entities, entries, strict=True):
        if entity.sprite is None:
            continue
        sprite = entity.sprite
        raw = base64.b64decode(sprite.pixels)
        reference = f"assets/{digest(sprite.width, sprite.height, raw)}.rgba"
        target = asset_path(root, reference)
        assets[target] = raw
        entry["sprite"] = {"width": sprite.width, "height": sprite.height, "asset": reference}
    # Assets precede the atomic scene replacement. Interrupted/failed saves may leave
    # unused immutable assets; they never break references in the previously saved scene.
    for target, raw in assets.items():
        target.parent.mkdir(exist_ok=True)
        store_asset(target, raw)
    save_scene_data(path, data, exclusive=exclusive)


def load_project_scene(root: Path, path: Path) -> Scene:
    with path.open("rb") as handle:
        raw = handle.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Scene files must be smaller than 4 MiB.")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise ValueError("This file is not a valid UTF-8 JSON scene.") from error
    if not isinstance(data, dict) or data.get("format_version") not in (
        4,
        6,
        PROJECT_SCENE_VERSION,
    ):
        return load_scene(path)
    if type(data["format_version"]) is not int or set(data) != {
        "format_version",
        "name",
        "entities",
    }:
        raise ValueError("Invalid project scene document fields.")
    entries = data["entities"]
    if not isinstance(entries, list) or len(entries) > MAX_ENTITIES:
        raise ValueError("Invalid project entity list.")
    cache: dict[str, bytes] = {}
    decoded_size = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid project entity fields.")
        sprite = entry.get("sprite")
        if sprite is None:
            continue
        if not isinstance(sprite, dict) or set(sprite) != {"width", "height", "asset"}:
            raise ValueError("Invalid project sprite fields.")
        reference = sprite["asset"]
        if not isinstance(reference, str):
            raise ValueError("Sprite asset references must be strings.")
        target = asset_path(root, reference)
        if reference not in cache:
            cache[reference] = read_asset(target)
        pixels = cache[reference]
        decoded_size += ((len(pixels) + 2) // 3) * 4
        if decoded_size > MAX_FILE_BYTES:
            raise ValueError("Resolved scenes must be smaller than 4 MiB.")
        normalized = Sprite.from_data(
            {
                "width": sprite["width"],
                "height": sprite["height"],
                "pixels": base64.b64encode(pixels).decode("ascii"),
            }
        )
        expected = f"assets/{digest(normalized.width, normalized.height, pixels)}.rgba"
        if reference != expected:
            raise ValueError(f"Sprite asset content does not match its hash: {target.name}")
        entry["sprite"] = {
            "width": normalized.width,
            "height": normalized.height,
            "pixels": normalized.pixels,
        }
    data["format_version"] = {4: 3, 6: 5}.get(data["format_version"], FORMAT_VERSION)
    scene = Scene.from_data(data)
    if len(json.dumps(scene.to_data(), indent=2).encode()) + 1 > MAX_FILE_BYTES:
        raise ValueError("Resolved scenes must be smaller than 4 MiB.")
    return scene
