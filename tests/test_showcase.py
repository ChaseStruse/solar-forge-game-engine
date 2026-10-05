from pathlib import Path

import pytest

from solar_forge_engine.core.scene import Role
from solar_forge_engine.core.showcase import courier_bay, ember_run
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.workspace import open_project, open_scene
from solar_forge_engine.runtime.simulation import Simulation


def test_showcase_route_collects_every_core_without_crossing_walls():
    scene = ember_run()
    simulation = Simulation(scene, "courier")
    route = [
        (80, 96),
        (384, 64),
        (624, 64),
        (944, 64),
        (944, 112),
        (944, 288),
        (624, 272),
        (624, 496),
        (944, 496),
        (944, 464),
        (944, 496),
        (624, 496),
        (384, 496),
        (80, 464),
        (80, 272),
        (384, 272),
        (384, 128),
        (480, 128),
    ]
    for x, y in route:
        for _ in range(600):
            dx, dy = x - simulation.x, y - simulation.y
            if abs(dx) <= 4 and abs(dy) <= 4:
                break
            simulation.step(
                (1 if dx > 0 else -1) if abs(dx) > 4 else 0,
                (1 if dy > 0 else -1) if abs(dy) > 4 else 0,
            )
            assert not any(simulation.overlaps(wall) for wall in simulation.walls)
        else:
            pytest.fail(f"Showcase route blocked at {(x, y)}")
    assert simulation.won
    assert len(simulation.collected) == 12


def test_distributed_project_matches_templates_and_shared_assets():
    root = Path(__file__).resolve().parents[1] / "examples/ember-run"
    project, scene = open_project(root)
    assert scene == ember_run()
    assert open_scene(project, "scenes/Courier Bay.forge.json")[1] == courier_bay()
    assert sum(entity.animation is not None for entity in scene.entities) >= 19
    assert scene.entity("courier").role == Role.PLAYER
    assert sum(path.stat().st_size for path in root.rglob("*") if path.is_file()) < 256_000


def test_showcase_opens_editably_and_plays_without_mutating_authoring(qtbot):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor._confirm_discard = lambda: True
    editor.new_showcase()
    original = editor.document.scene
    assert original == ember_run()
    assert editor.selected_id == "courier"
    assert editor.dirty
    editor.play()
    assert editor.preview.waitForStarted(5000)
    qtbot.waitUntil(lambda: "Preview ready" in editor.log.toPlainText(), timeout=5000)
    editor.stop_preview()
    assert editor.preview.waitForFinished(5000)
    assert editor.document.scene == original
