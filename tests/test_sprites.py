import json

import pytest
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QGraphicsPixmapItem

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.storage import load_scene, save_scene
from solar_forge_engine.runtime.player import PlayerWindow


def test_png_import_undo_persistence_and_native_play(qtbot, tmp_path):
    source = tmp_path / "hero.png"
    image = QImage(8, 6, QImage.Format.Format_RGBA8888)
    image.fill(QColor("#12ab34"))
    image.setPixelColor(0, 0, QColor(0, 0, 0, 0))
    assert image.save(str(source), "PNG")
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.import_sprite(source)
    entity = editor.document.scene.entity(editor.selected_id)
    assert (entity.width, entity.height) == (8, 6)
    editor.undo()
    assert not editor.document.scene.entities
    editor.redo()
    editor.selected_id = entity.id
    editor.refresh()
    editor.duplicate_selected()
    assert editor.document.scene.entities[1].sprite == entity.sprite
    editor.path = tmp_path / "sprites.forge.json"
    assert editor.save()
    source.unlink()
    assert editor.load(editor.path)
    assert editor.document.scene.entities[0] == entity
    player = PlayerWindow(editor.document.scene, entity.id)
    qtbot.addWidget(player)
    item = player.items[entity.id]
    assert isinstance(item, QGraphicsPixmapItem)
    texture = item.pixmap().toImage()
    assert texture.pixelColor(0, 0).alpha() == 0
    assert texture.pixelColor(1, 1).name() == "#12ab34"
    player.simulation.step(1, 0)
    player._sync_position()
    assert item.pos().x() > entity.x
    editor.play()
    assert editor.preview.waitForStarted(5000)
    qtbot.waitUntil(lambda: "Preview ready" in editor.log.toPlainText(), timeout=5000)
    editor.stop_preview()
    assert editor.preview.waitForFinished(5000)
    editor.selected_id = entity.id
    editor.refresh()
    editor.clear_sprite()
    assert editor.document.scene.entity(entity.id).sprite is None
    editor.undo()
    assert editor.document.scene.entity(entity.id).sprite == entity.sprite
    assert not editor.dirty


@pytest.mark.parametrize(
    "dimensions,pixels", [((257, 1), ""), ((True, 1), ""), ((1, 1), "bad!"), ((2, 2), "AAAAAA==")]
)
def test_invalid_sprite_data_rejected(dimensions, pixels):
    with pytest.raises(ValueError):
        Sprite(*dimensions, pixels)


def test_png_import_rejects_large_or_invalid_images_without_mutating_scene(
    qtbot, tmp_path, monkeypatch
):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.add_rectangle()
    original = editor.document.scene
    revision = editor.document.revision
    selected = editor.selected_id
    errors = []
    monkeypatch.setattr(editor, "_error", errors.append)
    path = tmp_path / "oversized.png"
    image = QImage(257, 1, QImage.Format.Format_RGBA8888)
    image.fill(QColor("red"))
    assert image.save(str(path), "PNG")
    assert not editor.import_sprite(path)
    path.write_bytes(b"not a PNG")
    assert not editor.import_sprite(path)
    assert len(errors) == 2
    assert editor.document.scene == original
    assert editor.document.revision == revision
    assert editor.selected_id == selected
    editor.saved_scene = original


@pytest.mark.parametrize("version", [1, 2])
def test_legacy_scene_upgrade_preserves_bytes_and_existing_backup(tmp_path, version):
    path = tmp_path / "legacy.forge.json"
    data = Scene(entities=(Entity("wall"),)).to_data()
    data["format_version"] = version
    for entry in data["entities"]:
        del entry["sprite"]
        if version == 1:
            del entry["role"]
    original = json.dumps(data).encode()
    path.write_bytes(original)
    loaded = load_scene(path)
    backup = path.with_name(f"{path.name}.v{version}.bak")
    backup.write_bytes(b"already backed up")
    with pytest.raises(ValueError, match="backup already exists"):
        save_scene(path, loaded)
    assert path.read_bytes() == original
    assert backup.read_bytes() == b"already backed up"
    backup.unlink()
    save_scene(path, loaded)
    assert backup.read_bytes() == original
    assert load_scene(path) == loaded
    assert json.loads(path.read_bytes())["format_version"] == 3
