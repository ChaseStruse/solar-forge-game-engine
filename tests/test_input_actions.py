import time

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.runtime.player import PlayerWindow
from solar_forge_engine.runtime.scripting import ScriptRunner
from solar_forge_engine.runtime.simulation import FIXED_STEP, Simulation

SOURCE = """
def on_start(game):
    game.data["presses"] = 0
    game.data["releases"] = 0
    assert game.actions["dash"] == {"held": False, "pressed": False, "released": False}
    game.say("ready")

def on_update(game, dt):
    dash = game.actions["dash"]
    game.data["presses"] += int(dash["pressed"])
    game.data["releases"] += int(dash["released"])
    game.say(f"{int(dash['held'])}:{int(dash['pressed'])}:{int(dash['released'])}:"
             f"{game.data['presses']}:{game.data['releases']}")
"""


@pytest.fixture
def player(qtbot):
    def stop(window):
        window.close()
        qtbot.waitUntil(lambda: not any(runner.active for runner in window._script_runners))

    def start(source=SOURCE):
        window = PlayerWindow(Scene(entities=(Entity("player"),), script=source), "player")
        qtbot.addWidget(window, before_close_func=stop)
        window.timer.stop()
        window.show()
        qtbot.waitUntil(lambda: window.isActiveWindow() and window._script_ready, timeout=5000)
        return window

    return start


def dispatch(window):
    assert window._script.idle
    window._last_tick = time.monotonic() - FIXED_STEP * 2
    window.tick()
    assert not window._script.idle


def step(window, qtbot):
    before = window._ticks
    dispatch(window)
    qtbot.waitUntil(lambda: window._ticks == before + 1, timeout=2000)


def test_dash_press_hold_release_and_fast_taps_are_delivered_once(player, qtbot):
    window = player()
    qtbot.keyPress(window, Qt.Key.Key_Space)
    # Native repeats must neither add presses nor manufacture releases.
    for kind in (QEvent.Type.KeyRelease, QEvent.Type.KeyPress):
        window.event(QKeyEvent(kind, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier, " ", True))
    step(window, qtbot)
    assert window.simulation.message == "1:1:0:1:0"
    step(window, qtbot)
    assert window.simulation.message == "1:0:0:1:0"
    qtbot.keyRelease(window, Qt.Key.Key_Space)
    step(window, qtbot)
    assert window.simulation.message == "0:0:1:1:1"
    step(window, qtbot)
    assert window.simulation.message == "0:0:0:1:1"
    qtbot.keyClick(window, Qt.Key.Key_Space)
    step(window, qtbot)
    assert window.simulation.message == "0:1:1:2:2"
    step(window, qtbot)
    assert window.simulation.message == "0:0:0:2:2"


def test_edges_arriving_during_worker_request_survive_until_next_callback(player, qtbot):
    window = player()
    dispatch(window)
    qtbot.keyClick(window, Qt.Key.Key_Space)
    qtbot.waitUntil(lambda: window._ticks == 1)
    assert window.simulation.message == "0:0:0:0:0"
    step(window, qtbot)
    assert window.simulation.message == "0:1:1:1:1"
    step(window, qtbot)
    assert window.simulation.message == "0:0:0:1:1"


@pytest.mark.parametrize("suspend", ["pause", "focus"])
def test_suspend_cancels_input_and_in_flight_commands_even_after_resume(
    player, qtbot, monkeypatch, suspend
):
    window = player(
        "import time\n"
        "def on_update(game, dt):\n"
        "    time.sleep(0.08)\n"
        "    if game.actions['dash']['pressed']:\n"
        "        game.set_speed(900)\n"
    )
    qtbot.keyPress(window, Qt.Key.Key_D)
    qtbot.keyPress(window, Qt.Key.Key_Space)
    dispatch(window)
    if suspend == "pause":
        window.toggle_pause()
        qtbot.keyClick(window, Qt.Key.Key_Space)
        window.toggle_pause()
    else:
        monkeypatch.setattr(window, "isActiveWindow", lambda: False)
        window.changeEvent(QEvent(QEvent.Type.ActivationChange))
        qtbot.keyClick(window, Qt.Key.Key_Space)
        monkeypatch.setattr(window, "isActiveWindow", lambda: True)
    qtbot.waitUntil(lambda: window._script.idle, timeout=2000)
    assert window.simulation.speed == 240 and window.simulation.x == 0
    assert window._ticks == 0 and not window.keys
    step(window, qtbot)
    assert window.simulation.speed == 240 and window.simulation.x == 0


def test_focus_loss_and_restart_clear_held_keys_and_edges(player, qtbot):
    from PySide6.QtWidgets import QWidget

    window = player()
    qtbot.keyPress(window, Qt.Key.Key_D)
    qtbot.keyPress(window, Qt.Key.Key_Space)
    other = QWidget()
    qtbot.addWidget(other)
    other.show()
    other.activateWindow()
    qtbot.waitUntil(lambda: not window.isActiveWindow())
    window.activateWindow()
    qtbot.waitUntil(window.isActiveWindow)
    step(window, qtbot)
    assert window.simulation.message == "0:0:0:0:0" and not window.keys
    qtbot.keyPress(window, Qt.Key.Key_D)
    qtbot.keyPress(window, Qt.Key.Key_Space)
    window.restart()
    qtbot.waitUntil(lambda: window._script_ready, timeout=5000)
    step(window, qtbot)
    assert window.simulation.message == "0:0:0:0:0"
    assert not window.keys and window.simulation.x == 0


@pytest.mark.parametrize(
    "actions",
    [
        {},
        {"jump": {"held": False, "pressed": False, "released": False}},
        {"dash": {"held": 1, "pressed": False, "released": False}},
        {"dash": {"held": False, "pressed": "yes", "released": False}},
        {"dash": {"held": False, "pressed": False}},
    ],
)
def test_invalid_action_context_is_rejected_before_source_evaluation(qtbot, actions):
    state = Simulation(Scene(entities=(Entity("player"),)), "player").script_state(0, 0, 0)
    state["actions"] = actions
    runner = ScriptRunner("print('source evaluated')", state)
    errors, output = [], []
    runner.failed.connect(lambda message, line: errors.append((message, line)))
    runner.output.connect(output.append)
    runner.start()
    qtbot.waitUntil(lambda: bool(errors), timeout=5000)
    qtbot.waitUntil(lambda: not runner.active)
    assert errors[0][1] == 0 and not output
    assert "dash" in errors[0][0].lower()
