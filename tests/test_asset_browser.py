from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

from solar_forge_engine.core.commands import SetEntity
from solar_forge_engine.core.scene import Role
from solar_forge_engine.editor.window import EditorWindow


def test_sprite_palette_reuses_applies_and_survives_undo_and_removal(qtbot, tmp_path):
    source = tmp_path / "Hero.png"
    image = QImage(8, 8, QImage.Format.Format_RGBA8888)
    image.fill(QColor("#f4b544"))
    assert image.save(str(source), "PNG")
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert not editor.add_asset_button.isEnabled()
    assert editor.import_sprite(source)
    sprite_id = editor.selected_id
    sprite = editor.document.scene.entity(sprite_id).sprite
    assert editor.asset_list.count() == 1
    editor.asset_list.setCurrentRow(0)
    qtbot.mouseClick(editor.add_asset_button, Qt.MouseButton.LeftButton)
    assert editor.selected_id != sprite_id
    assert editor.document.scene.entity(editor.selected_id).sprite == sprite
    assert editor.asset_list.count() == 1
    editor.undo()
    assert len(editor.document.scene.entities) == 1
    editor.add_rectangle()
    target_id = editor.selected_id
    editor.execute(SetEntity(target_id, {"role": "wall", "width": 100, "x": 300}))
    original = editor.document.scene.entity(target_id)
    qtbot.mouseClick(editor.apply_asset_button, Qt.MouseButton.LeftButton)
    textured = editor.document.scene.entity(target_id)
    assert textured.sprite == sprite
    assert (textured.width, textured.x, textured.role) == (100, 300, Role.WALL)
    editor.undo()
    assert editor.document.scene.entity(target_id) == original
    editor.selected_id = sprite_id
    editor.delete_selected()
    assert editor.asset_list.count() == 1
    assert not editor.apply_asset_button.isEnabled()
    qtbot.mouseClick(editor.add_asset_button, Qt.MouseButton.LeftButton)
    assert editor.document.scene.entity(editor.selected_id).sprite == sprite
    root = tmp_path / "Game"
    assert editor.create_workspace(root)
    assert len(list((root / "assets").iterdir())) == 1
    source.unlink()
    assert editor.load_workspace(root)
    assert editor.asset_list.count() == 1
    editor.asset_list.setCurrentRow(0)
    editor.add_asset()
    assert editor.save()
    assert len(list((root / "assets").iterdir())) == 1
    editor.new_scene()
    assert editor.asset_list.count() == 0
    assert not editor.add_asset_button.isEnabled()


def test_palette_edit_rejects_oversized_scene_without_changing_selection(
    qtbot, tmp_path, monkeypatch
):
    source = tmp_path / "sprite.png"
    image = QImage(8, 8, QImage.Format.Format_RGBA8888)
    image.fill(QColor("red"))
    assert image.save(str(source), "PNG")
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.import_sprite(source)
    editor.asset_list.setCurrentRow(0)
    previous = editor.document.scene
    selected = editor.selected_id
    revision = editor.document.revision
    monkeypatch.setattr("solar_forge_engine.editor.window.MAX_FILE_BYTES", 1)
    errors = []
    monkeypatch.setattr(editor, "_error", errors.append)
    editor.add_asset()
    assert errors
    assert editor.document.scene == previous
    assert editor.document.revision == revision
    assert editor.selected_id == selected
    editor.saved_scene = previous
