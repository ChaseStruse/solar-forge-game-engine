import hashlib
import json
from dataclasses import asdict, replace

import pytest

from solar_forge_engine.core.behavior import Behavior, BehaviorParameter
from solar_forge_engine.core.commands import CreateEntity, Document, SetEntity, SetSceneScript
from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.editor.behaviors import BehaviorDialog
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.assets import save_project_scene
from solar_forge_engine.project.recovery import read_recovery, recovery_path, write_recovery
from solar_forge_engine.project.storage import load_scene, save_scene
from solar_forge_engine.project.workspace import create_project, open_project
from solar_forge_engine.runtime.scripting import ScriptRunner
from solar_forge_engine.runtime.simulation import FIXED_STEP, Simulation

DRIFT_SOURCE = """
def on_start(game):
    game.data["order"] = []

def drift_start(game, instance):
    instance.data["x"] = game.objects[instance.id]["x"]
    instance.data["steps"] = 0
    game.data["order"].append(instance.id)

def on_update(game, dt):
    assert game.data["order"] == ["first", "second"]

def drift_update(game, instance, dt):
    instance.data["steps"] += 1
    instance.data["x"] += instance.parameters["speed"] * dt
    game.set_position(instance.id, instance.data["x"], 0)
    game.say(f"{instance.id}: {instance.data['steps']}")
"""


def scripted_scene(source=DRIFT_SOURCE):
    return Scene(
        entities=(
            Entity("first", behavior=attachment(20)),
            Entity("second", x=100, behavior=attachment(40)),
        ),
        script=source,
    )


@pytest.fixture
def worker(qtbot):
    runners = []

    def start(authored):
        simulation = Simulation(authored, "first")
        runner = ScriptRunner(authored.script, simulation.script_state(0, 0, 0))
        runners.append(runner)
        results, errors = [], []
        runner.completed.connect(lambda operation, commands: results.append(commands))
        runner.failed.connect(lambda message, line: errors.append((message, line)))
        runner.start()
        qtbot.waitUntil(lambda: bool(results or errors), timeout=5000)
        return simulation, runner, results, errors

    yield start
    for runner in runners:
        runner.stop()
        qtbot.waitUntil(lambda: not runner.active)


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


def test_worker_instances_have_independent_state_and_restart_resets_it(worker, qtbot):
    authored = scripted_scene()
    simulation, runner, results, errors = worker(authored)
    assert not errors
    simulation.apply_script(results[0])
    for index in range(1, 4):
        runner.update(simulation.script_state(0, 0, index * FIXED_STEP), FIXED_STEP)
        qtbot.waitUntil(lambda: len(results) == index + 1 or bool(errors))
        assert not errors
        simulation.apply_script(results[-1])
        assert simulation.x == pytest.approx(index * 20 * FIXED_STEP)
        assert simulation.runtime_scene.entity("second").x == pytest.approx(
            100 + index * 40 * FIXED_STEP
        )
        assert simulation.message == f"second: {index}"
    assert simulation.scene == authored
    reset, restarted, reset_results, reset_errors = worker(authored)
    restarted.update(reset.script_state(0, 0, 0), FIXED_STEP)
    qtbot.waitUntil(lambda: len(reset_results) == 2 or bool(reset_errors))
    assert not reset_errors
    reset.apply_script(reset_results[-1])
    assert reset.x == pytest.approx(20 * FIXED_STEP)
    assert reset.message == "second: 1"


@pytest.mark.parametrize(
    "source, message",
    [
        ("# missing callbacks", "requires callable"),
        ("drift_start = 5", "requires callable"),
        (
            "def drift_update(game, instance, dt):\n"
            "    game.set_position('first', 999, 0)\n"
            "    if instance.id == 'second':\n"
            "        raise ValueError('instance failed')",
            "Behavior drift on second",
        ),
    ],
)
def test_behavior_failure_stops_whole_batch_and_reports_object_and_source(
    worker, qtbot, source, message
):
    authored = scripted_scene(source)
    simulation, runner, results, errors = worker(authored)
    if not errors:
        runner.update(simulation.script_state(0, 0, 0), FIXED_STEP)
        qtbot.waitUntil(lambda: bool(errors))
        assert errors[0][1] == 4
        assert len(results) == 1  # No partial update commands escaped.
    assert message in errors[0][0]
    qtbot.waitUntil(lambda: not runner.active)
    assert simulation.runtime_scene == authored


def test_native_attachment_parameter_edit_undo_duplicate_and_stale_guard(qtbot, monkeypatch):
    editor = EditorWindow()
    editor._confirm_discard = lambda: True
    qtbot.addWidget(editor)
    editor.document = Document(scripted_scene())
    editor.selected_id = "second"
    editor.refresh()
    original = editor.document.scene

    def edit(dialog):
        assert dialog.attachment() == attachment(40)
        dialog.parameters.cellWidget(0, 1).setText("75.12345678912345")
        dialog.apply_button.click()
        return dialog.result()

    monkeypatch.setattr(BehaviorDialog, "exec", edit)
    editor.edit_behavior()
    tuned = attachment(75.12345678912345)
    assert editor.document.scene.entity("second").behavior == tuned
    editor.undo()
    assert editor.document.scene == original
    editor.redo()
    editor.duplicate_selected()
    assert editor.document.scene.entities[-1].behavior == tuned

    def stale(dialog):
        dialog.name.setText("replacement")
        editor.execute(SetEntity("first", {"x": 50}))
        before = editor.document.scene
        dialog.apply_button.click()
        assert "scene changed" in dialog.status.text()
        assert dialog.name.text() == "replacement"
        assert editor.document.scene == before
        dialog.reject()
        return dialog.result()

    monkeypatch.setattr(BehaviorDialog, "exec", stale)
    editor.edit_behavior()
    editor._confirm_discard = lambda: True
    editor.close()


def test_native_attachment_validation_and_detach_keep_unapplied_settings(qtbot):
    dialog = BehaviorDialog(Entity("object", behavior=attachment()))
    qtbot.addWidget(dialog)
    dialog.parameters.cellWidget(0, 1).setText("nan")
    assert not dialog.apply_button.isEnabled()
    dialog.enabled.setChecked(False)
    assert dialog.apply_button.isEnabled() and dialog.attachment() is None
    dialog.enabled.setChecked(True)
    assert not dialog.apply_button.isEnabled()
    assert dialog.parameters.cellWidget(0, 1).text() == "nan"
    dialog.parameters.cellWidget(0, 1).setText("50")
    dialog.add_parameter("speed", 5)
    assert not dialog.apply_button.isEnabled()  # Duplicate names cannot Apply.


def test_scene_and_behavior_callbacks_share_one_atomic_command_budget(worker, qtbot):
    source = (
        "def on_update(game, dt):\n"
        "    for _ in range(32): game.say('scene')\n"
        "def drift_update(game, instance, dt):\n"
        "    game.set_position(instance.id, 999, 0)\n"
    )
    authored = scripted_scene(source)
    simulation, runner, results, errors = worker(authored)
    assert not errors
    runner.update(simulation.script_state(0, 0, 0), FIXED_STEP)
    qtbot.waitUntil(lambda: bool(errors))
    assert "32 commands" in errors[0][0]
    assert len(results) == 1 and simulation.runtime_scene == authored
