"""Fail-closed cleanup planning and reversible quarantine of managed sprite files."""

import base64
import hashlib
import json
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.project.assets import digest, load_project_scene
from solar_forge_engine.project.storage import MAX_FILE_BYTES
from solar_forge_engine.project.workspace import Project, open_project

MAX_SCAN_FILES = 512
MAX_SCAN_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class CleanupPlan:
    candidates: tuple[str, ...]
    inventory: tuple[tuple[str, str], ...]
    bytes_unused: int


def sprite_reference(sprite: Sprite) -> str:
    return f"assets/{digest(sprite.width, sprite.height, base64.b64decode(sprite.pixels))}.rgba"


def plan_cleanup(project: Project, protected: set[Sprite]) -> CleanupPlan:
    open_project(project.root)
    used = {sprite_reference(sprite) for sprite in protected}
    inventory: list[tuple[str, str]] = []
    assets: dict[str, int] = {}
    remaining = MAX_SCAN_BYTES
    count = 0

    def record(path: Path) -> bytes:
        nonlocal remaining, count
        count += 1
        if count > MAX_SCAN_FILES or path.is_symlink() or not path.is_file():
            raise ValueError("Cleanup requires a complete scan of regular files (maximum 512).")
        with path.open("rb") as handle:
            raw = handle.read(min(remaining, MAX_FILE_BYTES) + 1)
        if len(raw) > min(remaining, MAX_FILE_BYTES):
            raise ValueError("Cleanup scan exceeds its file or 32 MiB total limit.")
        remaining -= len(raw)
        inventory.append(
            (path.relative_to(project.root).as_posix(), hashlib.sha256(raw).hexdigest())
        )
        return raw

    record(project.root / "project.json")
    scenes = project.root / "scenes"
    if scenes.is_symlink():
        raise ValueError("Cleanup refuses symbolic-link scene folders.")

    def walk_error(error: OSError) -> None:
        raise error

    for folder, directories, filenames in os.walk(scenes, followlinks=False, onerror=walk_error):
        for directory in directories:
            count += 1
            if count > MAX_SCAN_FILES or (Path(folder) / directory).is_symlink():
                raise ValueError("Cleanup refuses symlink folders or an incomplete scan.")
        for name in filenames:
            path = Path(folder) / name
            raw = record(path)
            if name.endswith(".recovery.json"):
                data = json.loads(raw)
                if (
                    not isinstance(data, dict)
                    or set(data) != {"format_version", "base_hash", "scene"}
                    or type(data["format_version"]) is not int
                    or data["format_version"] != 1
                    or not isinstance(data["base_hash"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", data["base_hash"])
                ):
                    raise ValueError("Cleanup cannot validate a recovery snapshot.")
                scene = Scene.from_data(data["scene"])
            elif re.fullmatch(r".+\.forge\.json(?:\.v[123]\.bak)?", name):
                reference = path.relative_to(project.root).as_posix()
                # Validate the full parent chain even for backup files.
                replace(
                    project,
                    scene=re.sub(r"\.v[123]\.bak$", "", reference)
                    if name.endswith(".bak")
                    else reference,
                ).scene_path()
                scene = load_project_scene(project.root, path)
            else:
                raise ValueError(f"Cleanup cannot classify scene-folder file: {name}")
            used.update(
                sprite_reference(entity.sprite) for entity in scene.entities if entity.sprite
            )
    assets_folder = project.root / "assets"
    if assets_folder.is_symlink() or not assets_folder.is_dir():
        raise ValueError("Cleanup requires a regular assets folder.")
    with os.scandir(assets_folder) as entries:
        for entry in entries:
            raw = record(Path(entry.path))
            if not re.fullmatch(r"[0-9a-f]{64}\.rgba", entry.name):
                raise ValueError("Cleanup found an unknown asset file; no files will be moved.")
            assets[f"assets/{entry.name}"] = len(raw)
    candidates = tuple(sorted(set(assets) - used))
    return CleanupPlan(
        candidates, tuple(sorted(inventory)), sum(assets[name] for name in candidates)
    )


def quarantine_assets(project: Project, protected: set[Sprite], plan: CleanupPlan) -> Path:
    if plan_cleanup(project, protected) != plan:
        raise ValueError("Project files changed after review. Scan again before cleanup.")
    trash = project.root / ".asset-quarantine"
    if trash.is_symlink():
        raise ValueError("Quarantine folders must not use symbolic links.")
    trash.mkdir(exist_ok=True)
    destination = trash / uuid4().hex
    destination.mkdir()
    moved: list[tuple[Path, Path]] = []
    try:
        for reference in plan.candidates:
            source = project.root / reference
            target = destination / source.name
            source.rename(target)
            moved.append((source, target))
    except OSError:
        for source, target in reversed(moved):
            os.link(target, source)
            target.unlink()
        destination.rmdir()
        raise
    return destination
