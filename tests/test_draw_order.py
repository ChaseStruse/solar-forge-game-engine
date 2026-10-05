import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QGraphicsScene

from solar_forge_engine.core.commands import Document, MoveEntity, SetEntity
from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.storage import load_scene
from solar_forge_engine.project.workspace import open_project
from solar_forge_engine.runtime.rendering import render_scene


def overlapping_scene():
    return Scene(entities=tuple(Entity(name, name=name) for name in ("back", "middle", "front")))


@pytest.mark.parametrize("index", [-1, 3, True, 1.5])
def test_invalid_draw_index_leaves_transaction_unchanged(index):
    original = overlapping_scene()
    document = Document(original)
    with pytest.raises(ValueError, match="Draw index"):
        document.execute(
            SetEntity("back", {"name": "changed"}), MoveEntity("back", index), expected_revision=0
        )
    assert document.scene == original
    assert document.revision == 0
    assert not document.can_undo


def test_draw_order_preserves_entities_and_validates_revision_and_id():
    original = overlapping_scene()
    document = Document(original)
    document.execute(MoveEntity("back", 2), expected_revision=0)
    assert document.scene.entities == (
        original.entities[1],
        original.entities[2],
        original.entities[0],
    )
    document.execute(MoveEntity("back", 2), expected_revision=1)
    assert document.revision == 1
    with pytest.raises(ValueError):
        document.execute(MoveEntity("missing", 0), expected_revision=1)
    with pytest.raises(ValueError, match="scene changed"):
        document.execute(MoveEntity("back", 0), expected_revision=0)
    document.undo()
    assert document.scene == original
    document.redo()
    assert document.scene.entities[-1].id == "back"


def test_editor_draw_order_changes_hit_testing_and_survives_saves(qtbot, tmp_path):
    window = EditorWindow()
    qtbot.addWidget(window)
    window._confirm_discard = lambda: True
    window.document = Document(overlapping_scene())
    window.selected_id = "middle"
    window.refresh()
    original = window.document.scene
    assert window.canvas.itemAt(QPointF(10, 10), window.view.transform()).data(0) == "front"
    window.draw_order_actions["front"].trigger()
    assert window.selected_id == "middle"
    assert window.tree.currentItem().data(0, Qt.ItemDataRole.UserRole) == "middle"
    assert not window.draw_order_actions["front"].isEnabled()
    assert window.draw_order_actions["back"].isEnabled()
    assert window.canvas.itemAt(QPointF(10, 10), window.view.transform()).data(0) == "middle"
    assert "3 / 3" in window.draw_order_label.text()
    playback = QGraphicsScene()
    render_scene(playback, window.document.scene)
    assert playback.itemAt(QPointF(10, 10), window.view.transform()).data(0) == "middle"
    edited = window.document.scene
    window.path = tmp_path / "order.forge.json"
    assert window.save()
    assert load_scene(window.path) == edited
    assert window.create_workspace(tmp_path / "Game")
    assert open_project(window.project.root)[1] == edited
    window.undo()
    assert window.document.scene == original
    window.redo()
    assert window.document.scene == edited
    window.draw_order_actions["backward"].trigger()
    assert window.document.scene == original
    window.draw_order_actions["back"].trigger()
    assert window.document.scene.entities[0].id == "middle"
    assert not window.draw_order_actions["backward"].isEnabled()
    window.draw_order_actions["forward"].trigger()
    assert window.document.scene == original
    window.selected_id = None
    window.refresh()
    assert not any(action.isEnabled() for action in window.draw_order_actions.values())
