import hashlib
import json
from dataclasses import replace

import pytest

from solar_forge_engine.core.commands import Document, SetSceneScript
from solar_forge_engine.core.scene import Scene
from solar_forge_engine.project.assets import save_project_scene
from solar_forge_engine.project.recovery import read_recovery, recovery_path, write_recovery
from solar_forge_engine.project.storage import load_scene, save_scene
from solar_forge_engine.project.workspace import create_project, open_project


def test_source_is_undoable_portable_and_never_runs_during_edit_load_or_recovery(tmp_path):
    marker = tmp_path / "must-not-run"
    source = f"open({str(marker)!r}, 'w').write('executed')\n"
    document = Document()
    document.execute(SetSceneScript(source), expected_revision=0)
    assert document.scene.script == source
    document.undo()
    assert document.scene.script == ""
    document.redo()
    with pytest.raises(ValueError, match="changed"):
        document.execute(SetSceneScript(""), expected_revision=0)
    project = create_project(tmp_path / "Project", document.scene)
    assert open_project(project.root)[1] == document.scene
    standalone = tmp_path / "Scene.forge.json"
    save_scene(standalone, document.scene)
    assert load_scene(standalone) == document.scene
    recovered = replace(document.scene, script=source + "# recovered\n")
    write_recovery(project, recovered, document.scene)
    assert read_recovery(project, document.scene) == recovered
    assert not marker.exists()


@pytest.mark.parametrize("source", [None, True, "\0", "x" * 32769, "🔥" * 8193, "\ud800"])
def test_invalid_source_preserves_document(source):
    document = Document()
    with pytest.raises(ValueError):
        document.execute(SetSceneScript(source), expected_revision=0)
    assert document.revision == 0 and not document.can_undo


@pytest.mark.parametrize("version", [9, 10])
def test_script_upgrade_preserves_old_bytes_and_recovery_hashes(tmp_path, version):
    baseline = Scene()
    project = create_project(tmp_path / "Project", baseline)
    old = baseline.to_data()
    del old["script"]
    old["format_version"] = version
    raw = json.dumps(old).encode()
    project.scene_path().write_bytes(raw)
    assert open_project(project.root)[1] == baseline
    old["format_version"] = 9
    recovery_path(project).write_text(
        json.dumps(
            {
                "format_version": 1,
                "base_hash": hashlib.sha256(json.dumps(old, sort_keys=True).encode()).hexdigest(),
                "scene": dict(old, name="Recovered"),
            }
        )
    )
    assert read_recovery(project, baseline) == replace(baseline, name="Recovered")
    scripted = replace(baseline, script="def on_start(game):\n    game.set_speed(300)\n")
    save_project_scene(project.root, project.scene_path(), scripted)
    assert (
        project.scene_path().with_name(project.scene_path().name + f".v{version}.bak").read_bytes()
        == raw
    )
    assert open_project(project.root)[1] == scripted
    with pytest.raises(ValueError, match="older saved scene"):
        read_recovery(project, scripted)
