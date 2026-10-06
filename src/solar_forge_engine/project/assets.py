"""Content-addressed project sprites; resolve into portable data before playback."""

import base64
import hashlib
import json
import re
from pathlib import Path

from solar_forge_engine.core.scene import FORMAT_VERSION, MAX_ENTITIES, Scene
from solar_forge_engine.core.script import MAX_SCRIPTS, ScriptBinding
from solar_forge_engine.core.sprite import MAX_PIXEL_BYTES, Sprite
from solar_forge_engine.project.scripts import read_source, script_path, store_scripts
from solar_forge_engine.project.storage import (
    MAX_FILE_BYTES,
    atomic_write,
    flush_directory,
    load_scene,
    read_regular_bytes,
    read_scene_bytes,
    save_scene_data,
)

PROJECT_SCENE_VERSION = 12


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
    raw = read_regular_bytes(path, MAX_PIXEL_BYTES)
    if raw is None:
        raise ValueError(f"Sprite asset is missing: {path.name}")
    if len(raw) > MAX_PIXEL_BYTES:
        raise ValueError("Sprite asset exceeds its pixel-data limit.")
    return raw


def store_asset(path: Path, raw: bytes) -> None:
    """Publish immutable bytes only after flushing; never overwrite an existing asset."""
    if path.exists():
        if read_asset(path) != raw:
            raise ValueError(f"Existing sprite asset is damaged: {path.name}")
        return
    try:
        atomic_write(path, raw, exclusive=True)
    except FileExistsError:
        if read_asset(path) != raw:
            raise ValueError(f"Existing sprite asset is damaged: {path.name}") from None


def save_project_scene(
    root: Path,
    path: Path,
    scene: Scene,
    *,
    exclusive: bool = False,
    expected_fingerprint: str | None = None,
) -> None:
    data = scene.to_data()
    # Keep snapshots bounded for the standalone scene and data-only Play contracts.
    if len(json.dumps(data, indent=2).encode()) + 1 > MAX_FILE_BYTES:
        raise ValueError("Resolved scenes must be smaller than 4 MiB.")
    data["format_version"] = PROJECT_SCENE_VERSION
    store_scripts(root, scene.scripts)
    data["scripts"] = [
        {"entity_id": binding.entity_id, "path": binding.path} for binding in scene.scripts
    ]
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
    if assets:
        # Also covers reuse of an asset another writer linked before its directory flush.
        flush_directory(root / "assets")
    save_scene_data(path, data, exclusive=exclusive, expected_fingerprint=expected_fingerprint)


def load_project_scene(root: Path, path: Path) -> Scene:
    raw = read_scene_bytes(path)
    if raw is None:
        raise FileNotFoundError(f"Project scene is missing: {path.name}")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise ValueError("This file is not a valid UTF-8 JSON scene.") from error
    if not isinstance(data, dict) or data.get("format_version") not in (
        4,
        6,
        8,
        10,
        PROJECT_SCENE_VERSION,
    ):
        return load_scene(path)
    fields = {"format_version", "name", "entities"}
    if data["format_version"] in (10, PROJECT_SCENE_VERSION):
        fields.add("coin_sound")
    if data["format_version"] == PROJECT_SCENE_VERSION:
        fields.add("scripts")
    if type(data["format_version"]) is not int or set(data) != fields:
        raise ValueError("Invalid project scene document fields.")
    entries = data["entities"]
    if not isinstance(entries, list) or len(entries) > MAX_ENTITIES:
        raise ValueError("Invalid project entity list.")
    if data["format_version"] == PROJECT_SCENE_VERSION:
        scripts = data["scripts"]
        if not isinstance(scripts, list) or len(scripts) > MAX_SCRIPTS:
            raise ValueError("Invalid project Python behavior list.")
        resolved_scripts = []
        for entry in scripts:
            if not isinstance(entry, dict) or set(entry) != {"entity_id", "path"}:
                raise ValueError("Invalid project Python behavior fields.")
            source = read_source(script_path(root, entry["path"]))
            binding = ScriptBinding(entry["entity_id"], entry["path"], source)
            resolved_scripts.append(
                {"entity_id": binding.entity_id, "path": binding.path, "source": source}
            )
        data["scripts"] = resolved_scripts
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
    data["format_version"] = {4: 3, 6: 5, 8: 7, 10: 9}.get(data["format_version"], FORMAT_VERSION)
    scene = Scene.from_data(data)
    if len(json.dumps(scene.to_data(), indent=2).encode()) + 1 > MAX_FILE_BYTES:
        raise ValueError("Resolved scenes must be smaller than 4 MiB.")
    return scene
