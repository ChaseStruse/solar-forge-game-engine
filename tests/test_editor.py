from PySide6.QtCore import Qt

from solar_forge_engine.core.commands import SetEntity
from solar_forge_engine.core.scene import Role
from solar_forge_engine.editor.window import EditorWindow


def test_native_edit_save_reopen_and_undo(qtbot, tmp_path):
    window = EditorWindow()
    qtbot.addWidget(window)
    window.show()
    window.add_rectangle()
    entity_id = window.document.scene.entities[0].id
    window.name_field.setText("Player")
    window.numbers["x"].setValue(240)
    qtbot.mouseClick(window.apply_button, Qt.MouseButton.LeftButton)
    assert window.tree.topLevelItem(0).text(0) == "Player"
    assert window.document.scene.entity(entity_id).x == 240
    window.undo()
    assert window.document.scene.entity(entity_id).x == 100
    window.redo()
    assert window.document.scene.entity(entity_id).x == 240

    path = tmp_path / "scene.forge.json"
    window.path = path
    assert window.save()
    assert not window.dirty

    reopened = EditorWindow()
    qtbot.addWidget(reopened)
    assert reopened.load(path)
    assert reopened.document.scene == window.document.scene
    assert reopened.tree.topLevelItemCount() == 1
    assert not reopened.document.can_undo

    window.delete_selected()
    assert window.document.scene.entities == ()
    window.undo()
    assert window.document.scene == reopened.document.scene
    assert not window.dirty


def test_duplicate_preserves_properties_and_round_trips(qtbot, tmp_path):
    window = EditorWindow()
    qtbot.addWidget(window)
    assert not window.duplicate_action.isEnabled()
    window.add_rectangle()
    original_id = window.selected_id
    window.execute(
        SetEntity(
            original_id,
            {"name": "Wall", "role": "wall", "width": 120, "color": "#123456"},
        )
    )
    original = window.document.scene.entity(original_id)
    window.duplicate_action.trigger()
    duplicate = window.document.scene.entity(window.selected_id)
    assert duplicate.id != original.id
    assert duplicate.name == "Wall copy"
    assert (duplicate.x, duplicate.y) == (original.x + 24, original.y + 24)
    assert (duplicate.width, duplicate.height, duplicate.color, duplicate.role) == (
        original.width,
        original.height,
        original.color,
        Role.WALL,
    )
    window.undo()
    assert window.document.scene.entities == (original,)
    assert not window.duplicate_action.isEnabled()
    window.redo()
    assert window.document.scene.entities == (original, duplicate)
    window.path = tmp_path / "duplicates.forge.json"
    assert window.save()
    reopened = EditorWindow()
    qtbot.addWidget(reopened)
    assert reopened.load(window.path)
    assert reopened.document.scene == window.document.scene
