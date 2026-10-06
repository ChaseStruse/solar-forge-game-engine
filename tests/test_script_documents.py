import hashlib
import json
from dataclasses import asdict, replace

import pytest

from solar_forge_engine.core.commands import DeleteEntity, Document, SetScript
from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.core.script import ScriptBinding
from solar_forge_engine.project.assets import save_project_scene
from solar_forge_engine.project.recovery import read_recovery, recovery_path
from solar_forge_engine.project.storage import load_scene, save_scene
from solar_forge_engine.project.workspace import create_project, open_project


def test_script_commands_are_revision_checked_undoable_and_preserve_callback_order():
    first = ScriptBinding.from_source(
        "one", "motion", "def update(ctx, dt):\n    ctx.move(10 * dt, 0)\n"
    )
    second = ScriptBinding.from_source("two", "other", "def start(ctx):\n    pass\n")
    original = Scene(entities=(Entity("one"), Entity("two")), scripts=(first, second))
    document = Document(original)
    changed = ScriptBinding.from_source("one", "motion", first.source.replace("10", "20"))
    document.execute(SetScript("one", asdict(changed)), expected_revision=0)
    assert document.scene.scripts == (changed, second)
    document.undo()
    assert document.scene == original
    document.redo()
    with pytest.raises(ValueError, match="scene changed"):
        document.execute(SetScript("one", None), expected_revision=0)
    revision = document.revision
    with pytest.raises(ValueError, match="different object"):
        document.execute(SetScript("one", asdict(second)), expected_revision=revision)
    assert document.revision == revision
    document.execute(DeleteEntity("one"), expected_revision=revision)
    assert document.scene.scripts == (second,)
    document.undo()
    assert document.scene.scripts == (changed, second)


def test_project_and_standalone_python_snapshots_move_without_executing_source(tmp_path):
    marker = tmp_path / "must-not-run"
    source = f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    binding = ScriptBinding.from_source("actor", "behavior", source)
    scene = Scene(entities=(Entity("actor"),), scripts=(binding,))
    project = create_project(tmp_path / "Game", scene)
    assert (project.root / binding.path).read_text() == source
    data = json.loads(project.scene_path().read_bytes())
    assert data["scripts"] == [{"entity_id": "actor", "path": binding.path}]
    moved = tmp_path / "Moved"
    project.root.rename(moved)
    assert open_project(moved)[1] == scene
    standalone = tmp_path / "portable.forge.json"
    save_scene(standalone, scene)
    (moved / binding.path).unlink()
    assert load_scene(standalone) == scene
    assert not marker.exists()


@pytest.mark.parametrize("attack", ["traversal", "damaged", "symlink"])
def test_invalid_project_script_references_are_rejected_without_execution(tmp_path, attack):
    binding = ScriptBinding.from_source("actor", "behavior", "raise RuntimeError('not on load')\n")
    project = create_project(
        tmp_path / "Game", Scene(entities=(Entity("actor"),), scripts=(binding,))
    )
    path = project.root / binding.path
    if attack == "traversal":
        data = json.loads(project.scene_path().read_bytes())
        data["scripts"][0]["path"] = "../outside.py"
        project.scene_path().write_text(json.dumps(data))
    elif attack == "damaged":
        path.write_text("print('changed externally')\n")
    else:
        outside = tmp_path / "outside.py"
        path.rename(outside)
        path.symlink_to(outside)
    with pytest.raises((OSError, ValueError)):
        open_project(project.root)


@pytest.mark.parametrize("version", [9, 10])
def test_previous_sound_scenes_and_recovery_upgrade_with_exact_backups(tmp_path, version):
    baseline = Scene(entities=(Entity("actor"),))
    project = create_project(tmp_path / "Game", baseline)
    old = Scene.from_data(baseline.to_data()).to_data()
    del old["scripts"]
    old["format_version"] = version
    raw = json.dumps(old).encode()
    project.scene_path().write_bytes(raw)
    assert open_project(project.root)[1] == baseline
    recovery_base = dict(old, format_version=9)
    recovered = dict(recovery_base, name="Recovered")
    recovery_path(project).write_text(
        json.dumps(
            {
                "format_version": 1,
                "base_hash": hashlib.sha256(
                    json.dumps(recovery_base, sort_keys=True).encode()
                ).hexdigest(),
                "scene": recovered,
            }
        )
    )
    assert read_recovery(project, baseline) == replace(baseline, name="Recovered")
    save_project_scene(project.root, project.scene_path(), baseline)
    backup = project.scene_path().with_name(project.scene_path().name + f".v{version}.bak")
    assert backup.read_bytes() == raw
    assert open_project(project.root)[1] == baseline
