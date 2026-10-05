import base64

import pytest
from PySide6.QtCore import QPointF, Qt

from solar_forge_engine.core.commands import SetEntity
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.storage import load_scene


def window_with_object(qtbot):
    window = EditorWindow()
    qtbot.addWidget(window)
    window._confirm_discard = lambda: True
    window.show()
    window.add_rectangle()
    window.saved_scene = window.document.scene
    window.fit_scene()
    qtbot.wait(10)
    return window


def point(window, x, y):
    return window.view.mapFromScene(QPointF(x, y))


@pytest.mark.parametrize("sprite", [False, True])
def test_drag_previews_once_then_undo_redo_save(qtbot, tmp_path, sprite):
    window = window_with_object(qtbot)
    if sprite:
        texture = Sprite(1, 1, base64.b64encode(bytes([80, 90, 100, 255])).decode())
        window.execute(SetEntity(window.selected_id, {"sprite": texture.__dict__}))
    original = window.document.scene
    revision = window.document.revision
    entity_id = window.selected_id
    viewport = window.view.viewport()
    start = point(window, 120, 120)
    target = point(window, 200, 180)
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(viewport, target)
    assert window.document.scene == original
    assert window.document.revision == revision
    assert window.view._item.pos() != QPointF(100, 100)
    qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=target)
    edited = window.document.scene
    entity = edited.entity(entity_id)
    assert entity.x == pytest.approx(180, abs=2)
    assert entity.y == pytest.approx(160, abs=2)
    assert window.document.revision == revision + 1
    assert window.numbers["x"].value() == pytest.approx(entity.x, abs=0.01)
    assert window.dirty
    window.undo()
    assert window.document.scene == original
    window.redo()
    assert window.document.scene == edited
    window.path = tmp_path / "drag.forge.json"
    assert window.save()
    assert load_scene(window.path) == edited


def test_grid_snap_and_click_are_distinct(qtbot):
    window = window_with_object(qtbot)
    original = window.document.scene
    viewport = window.view.viewport()
    window.snap_action.setChecked(True)
    window.grid_field.setValue(32)
    start = point(window, 120, 120)
    qtbot.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=start)
    assert window.document.scene == original
    assert not window.dirty
    target = point(window, 190, 180)
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(viewport, target)
    qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=target)
    entity = window.document.scene.entities[0]
    assert (entity.x, entity.y) == (160, 160)
    window.undo()
    assert window.document.scene == original


@pytest.mark.parametrize("cancel", ["escape", "refresh", "focus", "grid"])
def test_drag_cancellation_preserves_document(qtbot, cancel):
    window = window_with_object(qtbot)
    original = window.document.scene
    revision = window.document.revision
    viewport = window.view.viewport()
    start, target = point(window, 120, 120), point(window, 220, 220)
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(viewport, target)
    if cancel == "escape":
        qtbot.keyClick(window.view, Qt.Key.Key_Escape)
    elif cancel == "refresh":
        window.refresh()
    elif cancel == "focus":
        window.name_field.setFocus()
        qtbot.wait(10)
    else:
        window.snap_action.setChecked(True)
    qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=target)
    assert window.document.scene == original
    assert window.document.revision == revision
    assert not window.dirty
    item = next(item for item in window.canvas.items() if item.data(0) == window.selected_id)
    assert item.pos() == QPointF(100, 100)


def test_revision_change_during_drag_does_not_overwrite_new_edit(qtbot):
    window = window_with_object(qtbot)
    viewport = window.view.viewport()
    start, target = point(window, 120, 120), point(window, 220, 220)
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(viewport, target)
    window.document.execute(
        SetEntity(window.selected_id, {"x": 300}), expected_revision=window.document.revision
    )
    changed = window.document.scene
    qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=target)
    assert window.document.scene == changed
    assert "scene changed" in window.log.toPlainText()
    window.saved_scene = changed
