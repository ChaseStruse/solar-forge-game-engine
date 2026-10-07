import json
import os
import select
import subprocess
import sys
from pathlib import Path

import pytest

from solar_forge_engine.core.scene import Role
from solar_forge_engine.core.showcase import courier_bay, ember_run
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.workspace import open_project, open_scene
from solar_forge_engine.runtime import script_worker
from solar_forge_engine.runtime.script_worker import dash_actions
from solar_forge_engine.runtime.simulation import FIXED_STEP, Simulation


@pytest.fixture
def scripted_game():
    """Exercise the actual restricted worker, including command bounds/validation."""
    workers = []

    def start(scene, player_id):
        simulation = Simulation(scene, player_id)
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-S",
                "-B",
                "-c",
                Path(script_worker.__file__).read_text(),
                str(os.getpid()),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={"LANG": "C.UTF-8", "LD_LIBRARY_PATH": str(Path(sys.base_prefix) / "lib")},
        )
        workers.append(process)

        def receive():
            assert select.select([process.stdout], [], [], 3)[0], "Script response timed out"
            response = json.loads(process.stdout.readline())
            assert response["type"] != "error", response
            return response

        assert receive() == {"type": "ready"}
        sequence = 0

        def update(t, operation="update", *, horizontal=0, vertical=0, actions=None):
            nonlocal sequence
            sequence += 1
            request = {
                "id": sequence,
                "op": operation,
                "state": simulation.script_state(horizontal, vertical, t, actions=actions),
                "dt": FIXED_STEP,
            }
            if operation == "start":
                request["source"] = scene.script
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            result = receive()
            assert result["type"] == "result" and result["id"] == sequence
            assert len(result["commands"]) <= 32
            simulation.apply_script(result["commands"])

        update(0, "start")
        return simulation, update

    yield start
    for process in workers:
        process.kill()
        process.communicate(timeout=3)


@pytest.mark.parametrize("scripted", [False, True])
def test_showcase_route_collects_every_core_without_crossing_walls(scripted_game, scripted):
    scene = ember_run()
    simulation = Simulation(scene, "courier")
    if scripted:
        simulation, update = scripted_game(scene, "courier")
    elapsed = 0.0
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
            if scripted:
                update(elapsed)
            elapsed += FIXED_STEP
            simulation.step(
                (1 if dx > 0 else -1) if abs(dx) > 4 else 0,
                (1 if dy > 0 else -1) if abs(dy) > 4 else 0,
            )
            assert not any(simulation.overlaps(wall) for wall in simulation.walls)
        else:
            pytest.fail(f"Showcase route blocked at {(x, y)}")
    assert simulation.won
    assert len(simulation.collected) == 12
    if scripted:
        update(elapsed)
        assert "All cores secured" in simulation.message
        assert simulation.speed == 220
        assert simulation.scene == scene
        update(elapsed + 1)
        spark = next(e for e in simulation.runtime_scene.entities if e.name == "Reactor spark 1")
        assert abs(spark.x - simulation.x) < 60 and abs(spark.y - simulation.y) < 60


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


def test_showcase_boost_expires_and_restart_resets_state(scripted_game):
    scene = ember_run()
    simulation, update = scripted_game(scene, "courier")
    simulation.collected.add(simulation.coins[0].id)
    update(1)
    assert simulation.speed == 330 and "OVERDRIVE" in simulation.message
    update(3)
    assert simulation.speed == 220 and "1/12 cores" in simulation.message
    restarted, _ = scripted_game(scene, "courier")
    assert restarted.speed == 220 and not restarted.collected
    assert "Recover 12 cores" in restarted.message


def test_showcase_dash_requires_movement_respects_cooldown_and_preserves_pickup_boost(
    scripted_game,
):
    scene = ember_run()
    simulation, update = scripted_game(scene, "courier")
    tap = dash_actions(pressed=True, released=True)
    update(0, actions=tap)
    assert simulation.speed == 220  # A stationary press does not spend the dash.
    update(0.1, horizontal=1, actions=tap)
    assert simulation.speed == 480 and "DASH!" in simulation.message
    start_x = simulation.x
    simulation.step(1, 0)
    assert simulation.x - start_x == pytest.approx(480 * FIXED_STEP)
    simulation.collected.add(simulation.coins[0].id)
    update(0.2, horizontal=1)
    assert simulation.speed == 480  # A pickup never reduces an active dash.
    update(0.4, horizontal=1, actions=tap)
    assert simulation.speed == 330 and "OVERDRIVE" in simulation.message
    update(1.31, horizontal=1, actions=dash_actions(held=True))
    assert simulation.speed == 330  # Holding never retriggers when cooldown expires.
    update(1.32, horizontal=1, actions=tap)
    assert simulation.speed == 480
    update(1.6)
    assert simulation.speed == 220
    simulation.collected.update(coin.id for coin in simulation.coins)
    update(3, horizontal=1, actions=tap)
    assert simulation.speed == 220 and "All cores secured" in simulation.message
    assert simulation.scene == scene
    restarted, update_restart = scripted_game(scene, "courier")
    update_restart(0, horizontal=1, actions=tap)
    assert restarted.speed == 480  # Restart resets cooldown, too.


def test_showcase_dash_cannot_cross_walls(scripted_game):
    simulation, update = scripted_game(ember_run(), "courier")
    wall = simulation.walls[0]
    simulation.x = wall.x - simulation.controlled.width - 1
    simulation.y = wall.y
    update(0, horizontal=1, actions=dash_actions(pressed=True))
    assert simulation.speed == 480
    simulation.step(1, 0)
    assert simulation.x == wall.x - simulation.controlled.width
    assert not any(simulation.overlaps(candidate) for candidate in simulation.walls)


def test_orbital_bay_satellites_are_catchable_and_finish_is_stable(scripted_game):
    scene = courier_bay()
    simulation, update = scripted_game(scene, "bay-player")
    elapsed = 0.0
    update(elapsed)
    start_positions = [(coin.x, coin.y) for coin in simulation.coins]
    update(1)
    assert [(coin.x, coin.y) for coin in simulation.coins] != start_positions
    for _ in range(2400):
        update(elapsed)
        elapsed += FIXED_STEP
        remaining = [coin for coin in simulation.coins if coin.id not in simulation.collected]
        if not remaining:
            break
        target = min(
            remaining, key=lambda coin: (coin.x - simulation.x) ** 2 + (coin.y - simulation.y) ** 2
        )
        dx, dy = target.x - simulation.x, target.y - simulation.y
        simulation.step(
            (1 if dx > 0 else -1) if abs(dx) > 3 else 0, (1 if dy > 0 else -1) if abs(dy) > 3 else 0
        )
    assert simulation.won
    update(elapsed)
    assert "ORBIT COMPLETE" in simulation.message
    message = simulation.message
    update(elapsed + 10)
    assert simulation.message == message
    assert simulation.scene == scene
