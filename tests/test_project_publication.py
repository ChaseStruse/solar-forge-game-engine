import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.project import storage, workspace


@pytest.mark.parametrize("kind", ["fifo", "symlink"])
def test_manifest_reader_rejects_unsafe_file_without_waiting(tmp_path, kind):
    project = workspace.create_project(tmp_path / "Game", Scene())
    manifest = project.root / workspace.MANIFEST
    original = manifest.read_bytes()
    manifest.unlink()
    if kind == "fifo":
        os.mkfifo(manifest)
    else:
        outside = tmp_path / "outside.json"
        outside.write_bytes(original)
        manifest.symlink_to(outside)
    script = """
import sys
from pathlib import Path
from solar_forge_engine.project.workspace import read_project
try:
    read_project(Path(sys.argv[1]))
except (OSError, ValueError):
    sys.exit(0)
sys.exit(1)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(project.root)],
        capture_output=True,
        timeout=3,
    )
    assert result.returncode == 0, result.stderr


def test_late_external_manifest_change_is_preserved(tmp_path, monkeypatch):
    project = workspace.create_project(tmp_path / "Game", Scene())
    target, _ = workspace.create_scene(project, "Second")
    manifest = project.root / workspace.MANIFEST
    data = json.loads(manifest.read_bytes())
    data["name"] = "External edit"
    external = json.dumps(data).encode()
    original = workspace.atomic_write

    def changed(path, raw, **options):
        path.write_bytes(external)
        original(path, raw, **options)

    monkeypatch.setattr(workspace, "atomic_write", changed)
    with pytest.raises(ValueError, match="changed during saving"):
        workspace.set_startup_scene(project, target.scene, project)
    assert manifest.read_bytes() == external
    assert not list(project.root.glob(".forge-*"))


def test_competing_startup_publication_preserves_first_writer(tmp_path, monkeypatch):
    project = workspace.create_project(tmp_path / "Game", Scene())
    target, _ = workspace.create_scene(project, "Second")
    original = storage.os.replace
    manifest = project.root / workspace.MANIFEST
    previous = manifest.read_bytes()

    def held(source, destination):
        with pytest.raises(ValueError, match="save is in progress"):
            workspace.set_startup_scene(project, project.scene, project)
        assert manifest.read_bytes() == previous
        original(source, destination)

    monkeypatch.setattr(storage.os, "replace", held)
    updated = workspace.set_startup_scene(project, target.scene, project)
    assert workspace.read_project(project.root) == updated


@pytest.mark.parametrize("fail_parent", [False, True])
def test_project_creation_flushes_manifest_root_and_parent_or_rolls_back(
    tmp_path, monkeypatch, fail_parent
):
    root = tmp_path / "Game"
    flushed = []
    original = os.fsync

    def record(descriptor):
        target = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
        flushed.append(target)
        if fail_parent and target == tmp_path:
            raise OSError("project parent flush unavailable")
        original(descriptor)

    monkeypatch.setattr(storage.os, "fsync", record)
    if fail_parent:
        with pytest.raises(OSError, match="project parent flush"):
            workspace.create_project(root, Scene())
        assert not root.exists()
    else:
        project = workspace.create_project(root, Scene())
        scene_flush = next(
            index for index, path in enumerate(flushed) if path.parent == root / "scenes"
        )
        manifest_flush = next(
            index
            for index, path in enumerate(flushed)
            if path.parent == root and path.name.startswith(".forge-")
        )
        assert scene_flush < manifest_flush < flushed.index(root) < flushed.index(tmp_path)
        assert workspace.open_project(root) == (project, Scene())
