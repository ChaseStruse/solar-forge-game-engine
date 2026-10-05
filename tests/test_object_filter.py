from PySide6.QtCore import Qt
from test_preferences import editor

from solar_forge_engine.core.commands import DeleteEntity, SetEntity
from solar_forge_engine.core.scene import Role


def visible(window):
    return [
        window.tree.topLevelItem(index)
        for index in range(window.tree.topLevelItemCount())
        if not window.tree.topLevelItem(index).isHidden()
    ]


def test_name_id_and_combined_role_filters_leave_scene_and_selection_unchanged(qtbot):
    window = editor(qtbot)
    window.new_showcase()
    original = window.document.scene
    window.saved_scene = original
    revision = window.document.revision
    window.objects.role.setCurrentIndex(window.objects.role.findData(Role.COIN.value))
    assert len(visible(window)) == 12
    assert window.selected_id == "courier"
    assert window.tree.currentItem() is None
    assert "Selection outside filter: Forge courier" in window.objects.hint.text()
    assert window.name_field.text() == "Forge courier"
    window.objects.search.setText("missing")
    assert visible(window) == []
    assert "No matches" in window.objects.hint.text()
    window.objects.role.setCurrentIndex(0)
    window.objects.search.setText("  COURIER  ")
    assert len(visible(window)) == 1
    assert window.tree.currentItem().data(0, Qt.ItemDataRole.UserRole) == "courier"
    window.objects.search.setText("FORGE COURIER")
    assert len(visible(window)) == 1
    assert window.document.scene == original
    assert window.document.revision == revision
    assert not window.document.can_undo
    assert not window.dirty


def test_canvas_can_select_filtered_object_and_tree_selection_updates_inspector(qtbot):
    window = editor(qtbot)
    window.new_collector()
    window.objects.role.setCurrentIndex(window.objects.role.findData(Role.COIN.value))
    row = visible(window)[0]
    window.tree.setCurrentItem(row)
    selected = row.data(0, Qt.ItemDataRole.UserRole)
    assert window.selected_id == selected
    assert window.name_field.text() == window.document.scene.entity(selected).name
    window.canvas.clearSelection()
    player = next(item for item in window.canvas.items() if item.data(0) == "player")
    player.setSelected(True)
    assert window.selected_id == "player"
    assert window.tree.currentItem() is None
    assert window.inspector.isEnabled()
    assert "Selection outside filter" in window.objects.hint.text()
    window.objects.role.setCurrentIndex(0)
    assert window.tree.currentItem().data(0, Qt.ItemDataRole.UserRole) == "player"


def test_filters_refresh_after_rename_role_change_delete_and_undo(qtbot):
    window = editor(qtbot)
    window.add_rectangle()
    entity_id = window.selected_id
    window.objects.search.setText("hero")
    assert visible(window) == []
    window.execute(SetEntity(entity_id, {"name": "Hero", "role": "coin"}))
    assert len(visible(window)) == 1
    window.objects.role.setCurrentIndex(window.objects.role.findData(Role.COIN.value))
    assert len(visible(window)) == 1
    window.execute(SetEntity(entity_id, {"role": "wall"}))
    assert visible(window) == []
    window.undo()
    assert len(visible(window)) == 1
    window.execute(DeleteEntity(entity_id))
    assert visible(window) == []
    assert window.selected_id is None
    assert "outside filter" not in window.objects.hint.text()
    window.undo()
    assert len(visible(window)) == 1
    assert window.objects.search.text() == "hero"
    assert window.objects.role.currentData() == "coin"
