from PySide6.QtCore import QPointF, Qt
from test_viewport import point, window_with_object

from solar_forge_engine.core.commands import DeleteEntity, SetEntity
from solar_forge_engine.core.scene import Role
from solar_forge_engine.project.storage import load_scene


def drag(qtbot, window, start, target):
    viewport = window.view.viewport()
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(viewport, target)
    qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=target)


def test_lock_prevents_drag_but_allows_selection_inspector_and_unlock(qtbot, tmp_path):
    window = window_with_object(qtbot)
    original = window.document.scene
    entity_id = window.selected_id
    revision = window.document.revision
    window.name_field.setText("Unapplied name")
    window.lock_drag_check.setChecked(True)
    assert window.name_field.text() == "Unapplied name"
    assert window.lock_action.isChecked()
    assert window.tree.currentItem().text(1) == "Locked"
    window.canvas.clearSelection()
    start, target = point(window, 120, 120), point(window, 200, 180)
    drag(qtbot, window, start, target)
    assert window.selected_id == entity_id
    assert window.view._item is None
    assert window.document.scene == original
    assert window.document.revision == revision
    assert not window.dirty
    assert window.document.can_undo
    window.name_field.setText("Hero")
    window.apply_inspector()
    assert window.document.scene.entity(entity_id).name == "Hero"
    assert entity_id in window.view.locked_ids
    window.path = tmp_path / "locked.forge.json"
    assert window.save()
    assert load_scene(window.path) == window.document.scene
    window.lock_action.setChecked(False)
    assert not window.lock_drag_check.isChecked()
    drag(qtbot, window, start, target)
    assert window.document.scene.entity(entity_id).x != original.entity(entity_id).x


def test_lock_mid_drag_rolls_back_preview_and_blocks_late_commit(qtbot):
    window = window_with_object(qtbot)
    original = window.document.scene
    entity_id = window.selected_id
    viewport = window.view.viewport()
    start, target = point(window, 120, 120), point(window, 220, 220)
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseMove(viewport, target)
    assert window.view._item.pos() != QPointF(100, 100)
    window.set_selected_lock(True)
    qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=target)
    assert window.document.scene == original
    assert not window.dirty
    window._commit_drag(entity_id, 300, 300)
    assert window.document.scene == original
    assert "locked" in window.log.toPlainText()


def test_decoration_bulk_lock_undo_retention_and_document_reset(qtbot):
    window = window_with_object(qtbot)
    window.new_showcase()
    original = window.document.scene
    window.lock_decorations()
    assert window.view.locked_ids == frozenset(
        entity.id for entity in original.entities if entity.role == Role.DECORATION
    )
    assert "courier" not in window.view.locked_ids
    assert window.document.scene == original and not window.document.can_undo
    window.unlock_all_action.trigger()
    assert window.view.locked_ids == frozenset()
    window.lock_decorations()
    entity_id = window.selected_id
    window.set_selected_lock(True)
    window.execute(SetEntity(entity_id, {"x": 120}))
    assert entity_id in window.view.locked_ids
    window.execute(DeleteEntity(entity_id))
    assert not window.lock_action.isEnabled()
    window.undo()
    assert entity_id in window.view.locked_ids
    window.new_showcase()
    assert window.view.locked_ids == frozenset()
    assert not window.lock_action.isChecked()
