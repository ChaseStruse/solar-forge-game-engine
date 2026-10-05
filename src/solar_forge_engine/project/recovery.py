"""One bounded, self-contained recovery snapshot per project scene."""

import hashlib
import json
from pathlib import Path

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.project.storage import MAX_FILE_BYTES, atomic_write
from solar_forge_engine.project.workspace import Project


def fingerprint(scene: Scene) -> str:
    return hashlib.sha256(
        json.dumps(Scene.from_data(scene.to_data()).to_data(), sort_keys=True).encode()
    ).hexdigest()


def recovery_path(project: Project) -> Path:
    scene = project.scene_path()
    path = scene.with_name(scene.name + ".recovery.json")
    if path.is_symlink():
        raise ValueError("Recovery snapshots must not use symbolic links.")
    return path


def write_recovery(project: Project, scene: Scene, baseline: Scene) -> None:
    data = {"format_version": 1, "base_hash": fingerprint(baseline), "scene": scene.to_data()}
    raw = (json.dumps(data, allow_nan=False) + "\n").encode()
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Recovery snapshots must be no larger than 4 MiB.")
    atomic_write(recovery_path(project), raw)


def read_recovery(project: Project, baseline: Scene) -> Scene | None:
    path = recovery_path(project)
    if not path.exists():
        return None
    if not path.is_file():
        raise ValueError("Recovery snapshots must be regular files.")
    with path.open("rb") as handle:
        raw = handle.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Recovery snapshot exceeds 4 MiB.")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise ValueError("Recovery snapshot is not valid UTF-8 JSON.") from error
    if not isinstance(data, dict) or set(data) != {"format_version", "base_hash", "scene"}:
        raise ValueError("Invalid recovery snapshot fields.")
    if type(data["format_version"]) is not int or data["format_version"] != 1:
        raise ValueError("Unsupported recovery format version.")
    if data["base_hash"] != fingerprint(baseline):
        raise ValueError(
            "Recovery snapshot is from an older saved scene; retained without restoring."
        )
    scene = Scene.from_data(data["scene"])
    return scene if scene != baseline else None


def clear_recovery(project: Project) -> None:
    recovery_path(project).unlink(missing_ok=True)
