"""One bounded, self-contained recovery snapshot per project scene."""

import hashlib
import json
import os
import stat
from pathlib import Path

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.project.assets import load_project_scene
from solar_forge_engine.project.storage import MAX_FILE_BYTES, atomic_write, scene_write_guard
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
    with scene_write_guard(project.scene_path()):
        _publish_recovery(project, raw, baseline)


def _publish_recovery(project: Project, raw: bytes, baseline: Scene) -> None:
    previous = _read_snapshot(project)
    if previous is not None:
        _decode_snapshot(previous, baseline)
    saved = load_project_scene(project.root, project.scene_path())
    if fingerprint(saved) != fingerprint(baseline):
        raise ValueError("Saved scene changed externally; reopen it before autosaving.")
    if _read_snapshot(project) != previous:
        raise ValueError("Recovery snapshot changed during autosave; retained without replacing.")
    atomic_write(
        recovery_path(project),
        raw,
        exclusive=previous is None,
        expected_fingerprint=hashlib.sha256(previous).hexdigest() if previous is not None else None,
    )


def _read_snapshot(project: Project) -> bytes | None:
    path = recovery_path(project)
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("Recovery snapshots must be regular files.")
        raw = handle.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Recovery snapshot exceeds 4 MiB.")
    return raw


def read_recovery(project: Project, baseline: Scene) -> Scene | None:
    raw = _read_snapshot(project)
    return _decode_snapshot(raw, baseline) if raw is not None else None


def _decode_snapshot(raw: bytes, baseline: Scene) -> Scene | None:
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        raise ValueError("Recovery snapshot is not valid UTF-8 JSON.") from error
    if not isinstance(data, dict) or set(data) != {"format_version", "base_hash", "scene"}:
        raise ValueError("Invalid recovery snapshot fields.")
    if type(data["format_version"]) is not int or data["format_version"] != 1:
        raise ValueError("Unsupported recovery format version.")
    hashes = {fingerprint(baseline)}
    snapshot = data["scene"]
    if (
        isinstance(snapshot, dict)
        and type(snapshot.get("format_version")) is int
        and snapshot["format_version"] in (5, 7)
        and baseline.coin_sound is None
        and (
            snapshot["format_version"] == 7
            or all(entity.animation is None for entity in baseline.entities)
        )
    ):
        # Previous releases hashed canonical scene data before coin sounds existed.
        legacy = Scene.from_data(baseline.to_data()).to_data()
        legacy["format_version"] = snapshot["format_version"]
        del legacy["coin_sound"]
        entries = legacy["entities"]
        assert isinstance(entries, list)
        if snapshot["format_version"] == 5:
            for entry in entries:
                del entry["animation"]
        hashes.add(hashlib.sha256(json.dumps(legacy, sort_keys=True).encode()).hexdigest())
    if not isinstance(data["base_hash"], str) or data["base_hash"] not in hashes:
        raise ValueError(
            "Recovery snapshot is from an older saved scene; retained without restoring."
        )
    scene = Scene.from_data(data["scene"])
    return scene if scene != baseline else None


def clear_recovery(project: Project, baseline: Scene | None = None) -> None:
    with scene_write_guard(project.scene_path()):
        _clear_recovery(project, baseline)


def _clear_recovery(project: Project, baseline: Scene | None) -> None:
    if baseline is not None:
        previous = _read_snapshot(project)
        if previous is None:
            return
        _decode_snapshot(previous, baseline)
        if _read_snapshot(project) != previous:
            raise ValueError("Recovery snapshot changed during cleanup; retained without deleting.")
    path = recovery_path(project)
    path.unlink(missing_ok=True)
    descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
