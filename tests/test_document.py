import json
from dataclasses import replace

import pytest

from solar_forge_engine.core.commands import CreateEntity, DeleteEntity, Document, SetEntity
from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.project.storage import load_scene, save_scene


def test_transaction_save_reload_and_undo(tmp_path):
    document = Document()
    document.execute(CreateEntity(Entity("player")), expected_revision=0)
    created = document.scene
    document.execute(
        SetEntity("player", {"x": 100, "name": "Player"}),
        CreateEntity(Entity("coin", x=200)),
        expected_revision=1,
    )
    edited = document.scene
    path = tmp_path / "test.forge.json"
    save_scene(path, edited)
    assert load_scene(path) == edited
    document.undo()
    assert document.scene == created
    document.redo()
    assert document.scene == edited
    document.execute(DeleteEntity("coin"), expected_revision=document.revision)
    assert len(document.scene.entities) == 1


def test_invalid_batch_and_stale_revision_leave_scene_and_history_untouched():
    document = Document(Scene(entities=(Entity("player"),)))
    original = document.scene
    with pytest.raises(ValueError, match="positive"):
        document.execute(
            SetEntity("player", {"x": 100}),
            SetEntity("player", {"width": 0}),
            expected_revision=0,
        )
    assert document.scene == original
    assert document.revision == 0
    assert not document.can_undo
    document.execute(SetEntity("player", {"x": 20}), expected_revision=0)
    document.undo()
    with pytest.raises(ValueError, match="scene changed"):
        document.execute(DeleteEntity("player"), expected_revision=0)
    assert document.scene == original
    assert document.can_redo


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(format_version=4),
        lambda data: data.update(format_version=True),
        lambda data: data["entities"].append(data["entities"][0]),
        lambda data: data["entities"][0].update(x=float("nan")),
        lambda data: data["entities"][0].update(width=-1),
        lambda data: data["entities"][0].update(x=True),
        lambda data: data["entities"][0].update(x=10**400),
        lambda data: data["entities"][0].update(script="exec('unexpected')"),
    ],
)
def test_reject_unsafe_or_unsupported_documents(mutation):
    data = Scene(entities=(Entity("player"),)).to_data()
    mutation(data)
    with pytest.raises(ValueError):
        Scene.from_data(data)


def test_failed_save_preserves_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "scene.forge.json"
    original = Scene()
    save_scene(path, original)

    def fail_replace(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr("solar_forge_engine.project.storage.os.replace", fail_replace)
    with pytest.raises(OSError):
        save_scene(path, replace(original, name="Changed"))
    assert load_scene(path) == original
    assert list(tmp_path.iterdir()) == [path]
    assert json.loads(path.read_text())["name"] == original.name
