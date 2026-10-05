import base64

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.catalog import index_sprites
from solar_forge_engine.project.workspace import create_project, create_scene


def make_project(root):
    sprite = Sprite(1, 1, base64.b64encode(bytes([255, 100, 0, 255])).decode())
    project = create_project(root, Scene(entities=(Entity("hero", name="Hero", sprite=sprite),)))
    second, _ = create_scene(project, "Level 2")
    return project, second, sprite


def test_project_catalog_reuses_other_scene_asset_without_extra_files(qtbot, tmp_path):
    first, second, sprite = make_project(tmp_path / "Game")
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.load_workspace(first.root)
    qtbot.waitUntil(lambda: editor._asset_index_job is None)
    assert editor.switch_project_scene(second.scene)
    qtbot.waitUntil(lambda: editor._asset_index_job is None)
    assert not editor.document.scene.entities
    assert editor.asset_sprites == [sprite]
    editor.asset_list.setCurrentRow(0)
    editor.add_asset()
    assert editor.document.scene.entities[0].sprite == sprite
    assert editor.save()
    assert len(list((first.root / "assets").iterdir())) == 1
    assert editor.switch_project_scene(first.scene)
    qtbot.waitUntil(lambda: editor._asset_index_job is None)
    assert editor.asset_list.count() == 1


def test_catalog_skips_invalid_scene_and_honors_cancellation_and_budget(tmp_path, monkeypatch):
    first, second, sprite = make_project(tmp_path / "Game")
    second.scene_path().write_bytes(b"invalid scene")
    sprites, warnings = index_sprites(first, lambda: False)
    assert sprites == [("Hero", sprite)]
    assert warnings
    assert index_sprites(first, lambda: True) == ([], [])
    monkeypatch.setattr("solar_forge_engine.project.catalog.MAX_INDEX_BYTES", 1)
    sprites, warnings = index_sprites(first, lambda: False)
    assert not sprites
    assert "16 MiB" in warnings[0]


def test_async_scan_from_old_project_cannot_populate_new_project(qtbot, tmp_path):
    first, _, _ = make_project(tmp_path / "First")
    other = create_project(tmp_path / "Other", Scene())
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.load_workspace(first.root)
    assert editor.load_workspace(other.root)
    qtbot.waitUntil(lambda: editor._asset_index_job is None)
    assert editor.project.root == other.root
    assert not editor.asset_sprites
