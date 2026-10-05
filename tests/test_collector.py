import json

import pytest

from solar_forge_engine.core.scene import Entity, Role, Scene
from solar_forge_engine.core.templates import coin_collector
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.storage import load_scene, save_scene
from solar_forge_engine.runtime.player import PlayerWindow
from solar_forge_engine.runtime.simulation import Simulation


def test_swept_wall_collision_blocks_thin_wall_and_allows_sliding():
    scene = Scene(
        entities=(
            Entity("player", x=10, y=10, width=10, height=10, role=Role.PLAYER),
            Entity("wall", x=25, y=0, width=1, height=200, role=Role.WALL),
        )
    )
    simulation = Simulation(scene, "player")
    simulation.step(1, 0, 0.1)
    assert simulation.x == 15
    simulation.step(1, 1, 0.1)
    assert simulation.x == 15
    assert simulation.y > 10
    simulation.step(-1, 0)
    assert simulation.x < 15


def test_collection_is_once_per_coin_and_restart_restores_score_and_visibility(qtbot):
    scene = Scene(
        entities=(
            Entity("player", x=10, y=10, role=Role.PLAYER),
            Entity("coin", x=20, y=20, role=Role.COIN),
        )
    )
    player = PlayerWindow(scene, "player")
    qtbot.addWidget(player)
    for _ in range(3):
        player.simulation.step(0, 0)
    player._sync_position()
    assert player.simulation.collected == {"coin"}
    assert player.simulation.won
    assert not player.items["coin"].isVisible()
    assert "All coins collected" in player.score_label.text()
    player.restart()
    assert not player.simulation.collected
    assert player.items["coin"].isVisible()
    assert "Coins: 0/1" in player.score_label.text()
    assert scene.entities[1].role == Role.COIN


def test_starter_can_be_edited_saved_and_reopened_with_roles(qtbot, tmp_path):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.new_collector()
    assert editor.dirty
    assert editor.document.scene == coin_collector()
    editor.name_field.setText("My player")
    editor.apply_inspector()
    assert editor.document.scene.entity("player").role == Role.PLAYER
    editor.path = tmp_path / "collector.forge.json"
    assert editor.save()
    assert load_scene(editor.path) == editor.document.scene


def test_version_one_migration_preserves_original_bytes_before_save(tmp_path):
    path = tmp_path / "old.forge.json"
    data = Scene(entities=(Entity("rectangle"),)).to_data()
    data["format_version"] = 1
    for entity in data["entities"]:
        del entity["role"]
    original = json.dumps(data).encode()
    path.write_bytes(original)
    upgraded = load_scene(path)
    assert path.read_bytes() == original
    assert upgraded.entity("rectangle").role == Role.DECORATION
    save_scene(path, upgraded)
    assert (tmp_path / "old.forge.json.v1.bak").read_bytes() == original
    assert json.loads(path.read_text())["format_version"] == 2
    assert load_scene(path) == upgraded


def test_invalid_roles_are_rejected():
    data = Entity("player").__dict__ | {"role": "execute-script"}
    with pytest.raises(ValueError):
        Entity.from_data(data)


def test_starter_level_can_be_completed_without_crossing_walls():
    scene = coin_collector()
    simulation = Simulation(scene, "player")
    route = [
        (160, 80),
        (430, 80),
        (450, 80),
        (450, 400),
        (450, 360),
        (750, 360),
        (750, 100),
        (960, 100),
        (960, 500),
        (920, 500),
    ]
    for target_x, target_y in route:
        for _ in range(400):
            dx, dy = target_x - simulation.x, target_y - simulation.y
            if abs(dx) <= 4 and abs(dy) <= 4:
                break
            simulation.step(
                (1 if dx > 0 else -1) if abs(dx) > 4 else 0,
                (1 if dy > 0 else -1) if abs(dy) > 4 else 0,
            )
            assert not any(simulation.overlaps(wall) for wall in simulation.walls)
        else:
            pytest.fail("Starter route was blocked")
    assert simulation.won
    assert len(simulation.collected) == 5
    assert len(scene.entities) == 9
