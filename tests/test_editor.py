from PySide6.QtCore import Qt

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
