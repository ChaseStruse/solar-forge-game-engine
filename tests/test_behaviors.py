import hashlib
import json
from dataclasses import asdict, replace

import pytest

from solar_forge_engine.core.behavior import Behavior, BehaviorParameter
from solar_forge_engine.core.commands import CreateEntity, Document, SetEntity, SetSceneScript
from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.project.assets import save_project_scene
from solar_forge_engine.project.recovery import read_recovery, recovery_path, write_recovery
from solar_forge_engine.project.storage import load_scene, save_scene
from solar_forge_engine.project.workspace import create_project, open_project


def attachment(speed=20):
    return Behavior("drift", (BehaviorParameter("speed", speed),))


def scene(source="# reusable callbacks go here"):
    return Scene(entities=(Entity("first"), Entity("second", x=100)), script=source)


def test_attachment_edit_duplicate_undo_save_and_recovery_never_evaluate_source(tmp_path):
    marker = tmp_path / "not-executed"
    original = scene(f"open({str(marker)!r}, 'w').close()")
    document = Document(original)
    document.execute(SetEntity("first", {"behavior": asdict(attachment())}), expected_revision=0)
    attached = document.scene
    document.execute(
        CreateEntity(replace(attached.entity("first"), id="copy")), expected_revision=1
    )
    assert document.scene.entity("copy").behavior == attachment()
    document.undo()
    assert document.scene == attached
    document.undo()
    assert document.scene == original
    document.redo()
    with pytest.raises(ValueError, match="changed"):
        document.execute(SetEntity("first", {"behavior": None}), expected_revision=0)
    with pytest.raises(ValueError, match="detach"):
        document.execute(SetSceneScript(""), expected_revision=document.revision)
    path = tmp_path / "Scene.forge.json"
    save_scene(path, document.scene)
    assert load_scene(path) == attached
    project = create_project(tmp_path / "Project", original)
    write_recovery(project, attached, original)
    assert read_recovery(project, original) == attached
    save_project_scene(project.root, project.scene_path(), attached)
    assert open_project(project.root)[1] == attached
    assert not marker.exists()


@pytest.mark.parametrize("version", [11, 12])
def test_behavior_upgrade_keeps_exact_backup_and_previous_recovery(tmp_path, version):
    baseline = Scene.from_data(scene().to_data())
    project = create_project(tmp_path / "Project", baseline)
    old = baseline.to_data()
    for entry in old["entities"]:
        del entry["behavior"]
    legacy = dict(old, format_version=11)
    recovery_path(project).write_text(
        json.dumps(
            {
                "format_version": 1,
                "base_hash": hashlib.sha256(
                    json.dumps(legacy, sort_keys=True).encode()
                ).hexdigest(),
                "scene": dict(legacy, name="Recovered"),
            }
        )
    )
    old["format_version"] = version
    raw = json.dumps(old).encode()
    project.scene_path().write_bytes(raw)
    assert open_project(project.root)[1] == baseline
    assert read_recovery(project, baseline) == replace(baseline, name="Recovered")
    attached = replace(baseline, entities=(replace(baseline.entities[0], behavior=attachment()),))
    save_project_scene(project.root, project.scene_path(), attached)
    assert (
        project.scene_path().with_name(project.scene_path().name + f".v{version}.bak").read_bytes()
        == raw
    )
    assert open_project(project.root)[1] == attached
    with pytest.raises(ValueError, match="older saved scene"):
        read_recovery(project, attached)


@pytest.mark.parametrize(
    "data",
    [
        {"name": "../bad", "parameters": []},
        {"name": "on", "parameters": []},
        {"name": "drift", "parameters": [{"name": "speed", "value": True}]},
        {"name": "drift", "parameters": [{"name": "speed", "value": float("nan")}]},
        {"name": "drift", "parameters": [{"name": "speed", "value": 10**400}]},
        {"name": "drift", "parameters": [{"name": "speed", "value": 1}] * 2},
    ],
)
def test_invalid_attachment_preserves_transaction(data):
    document = Document(scene())
    with pytest.raises(ValueError):
        document.execute(
            SetEntity("first", {"x": 200}),
            SetEntity("second", {"behavior": data}),
            expected_revision=0,
        )
    assert document.scene == scene() and document.revision == 0
    assert not document.can_undo


def test_behavior_count_and_parameter_count_are_bounded():
    with pytest.raises(ValueError, match="32"):
        Scene(
            entities=tuple(Entity(f"e{i}", behavior=attachment()) for i in range(33)),
            script="# code",
        )
    with pytest.raises(ValueError, match="16"):
        Behavior("drift", tuple(BehaviorParameter(f"p{i}", 0) for i in range(17)))
