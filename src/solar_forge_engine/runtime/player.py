"""Native Play window with built-in movement and isolated Python behaviors."""

import base64
import json
import time
from dataclasses import asdict

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QBrush, QCloseEvent, QColor, QKeyEvent, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractGraphicsShapeItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMainWindow,
    QPushButton,
    QToolBar,
)

from solar_forge_engine.core.scene import InputPreset, Scene
from solar_forge_engine.runtime.audio import SoundPlayer
from solar_forge_engine.runtime.rendering import SpriteAnimator, render_scene
from solar_forge_engine.runtime.script_host import ScriptHost
from solar_forge_engine.runtime.script_protocol import ScriptFault, ScriptResult
from solar_forge_engine.runtime.simulation import FIXED_STEP, WORLD_HEIGHT, WORLD_WIDTH, Simulation

LEFT = {Qt.Key.Key_A, Qt.Key.Key_Left}
RIGHT = {Qt.Key.Key_D, Qt.Key.Key_Right}
UP = {Qt.Key.Key_W, Qt.Key.Key_Up}
DOWN = {Qt.Key.Key_S, Qt.Key.Key_Down}
MOVEMENT_KEYS = LEFT | RIGHT | UP | DOWN
DENSE_ANIMATION_CHANGES = 1000
KEY_NAMES = (
    {
        int(getattr(Qt.Key, "Key_" + letter)): letter.casefold()
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    }
    | {int(getattr(Qt.Key, "Key_" + digit)): digit for digit in "0123456789"}
    | {
        int(Qt.Key.Key_Left): "left",
        int(Qt.Key.Key_Right): "right",
        int(Qt.Key.Key_Up): "up",
        int(Qt.Key.Key_Down): "down",
        int(Qt.Key.Key_Space): "space",
        int(Qt.Key.Key_Return): "enter",
        int(Qt.Key.Key_Shift): "shift",
        int(Qt.Key.Key_Control): "ctrl",
    }
)


class GameView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self._animation_changes = 0

    def queue_animation_updates(self, changed: int) -> None:
        # Dense frame swaps benefit from avoiding dirty-region merging. Keep sparse
        # updates cheap, and retain the dense mode until queued changes are painted.
        self._animation_changes += changed
        self.setViewportUpdateMode(
            self.ViewportUpdateMode.FullViewportUpdate
            if self._animation_changes >= DENSE_ANIMATION_CHANGES
            else self.ViewportUpdateMode.MinimalViewportUpdate
        )

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        self._animation_changes = 0

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class PlayerWindow(QMainWindow):
    def __init__(self, scene: Scene, controlled_id: str) -> None:
        super().__init__()
        self.sound_player = SoundPlayer(self)
        self._sound_pcm = base64.b64decode(scene.coin_sound.samples) if scene.coin_sound else b""
        self._audio_count = 0
        self._closing = False
        self._restart_pending = False
        self.script_host: ScriptHost | None = None
        self._script_time = 0.0
        self._script_started = False
        self._log_window = time.monotonic()
        self._log_count = 0
        self.sound_player.finished.connect(self._audio_finished)
        self.simulation = Simulation(scene, controlled_id)
        preset = self.simulation.controlled.input_preset
        key_sets = {
            InputPreset.BOTH: MOVEMENT_KEYS,
            InputPreset.WASD: {Qt.Key.Key_A, Qt.Key.Key_D, Qt.Key.Key_W, Qt.Key.Key_S},
            InputPreset.ARROWS: {Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down},
        }
        self.left, self.right, self.up, self.down = (
            keys & key_sets[preset] for keys in (LEFT, RIGHT, UP, DOWN)
        )
        self.movement_keys = self.left | self.right | self.up | self.down
        self.keys: set[int] = set()
        self.paused = False
        self._accumulator = 0.0
        self._last_tick = time.monotonic()
        self.setWindowTitle(f"Play — {scene.name} — Solar Forge")
        self.resize(1040, 660)
        self.setStyleSheet("""
            QMainWindow, QToolBar { background: #111d26; color: #d1e4df; }
            QToolBar { padding: 8px; spacing: 10px; border-bottom: 1px solid #385361; }
            QLabel { color: #d1e4df; padding: 4px; }
            QPushButton { background: #243b47; color: #f0ce85; border: 1px solid #527681;
                          padding: 7px 14px; border-radius: 3px; }
            QPushButton:hover { background: #34515b; }
        """)
        self.canvas = QGraphicsScene(self)
        self.canvas.setSceneRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT)
        self.items = render_scene(self.canvas, scene)
        self.animator = SpriteAnimator(scene, self.items)
        self._ticks = 0
        self.view = GameView(self.canvas)
        self.view.setBackgroundBrush(QBrush(QColor("#15181e")))
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.view.setAccessibleName("Game preview")
        self.setCentralWidget(self.view)
        toolbar = QToolBar("Playback")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        key_label = {
            InputPreset.BOTH: "WASD / arrows",
            InputPreset.WASD: "WASD",
            InputPreset.ARROWS: "arrows",
        }[preset]
        self.controls_label = QLabel(
            f"  {self.simulation.controlled.name} · {key_label} · Esc closes   "
        )
        self.controls_label.setTextFormat(Qt.TextFormat.PlainText)
        toolbar.addWidget(self.controls_label)
        self.pause_button = QPushButton("Pause")
        self.pause_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.pause_button.clicked.connect(self.toggle_pause)
        toolbar.addWidget(self.pause_button)
        restart = QPushButton("Restart")
        restart.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        restart.clicked.connect(self.restart)
        toolbar.addWidget(restart)
        self.score_label = QLabel()
        toolbar.addWidget(self.score_label)
        self.audio_label = QLabel()
        self.audio_label.setTextFormat(Qt.TextFormat.PlainText)
        if scene.coin_sound is not None:
            toolbar.addWidget(self.audio_label)
            self.audio_label.setAccessibleName("Game sound status")
            self.sound_player.message.connect(self._audio_message)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self._sync_position()
        self.script_label = QLabel()
        self.script_label.setTextFormat(Qt.TextFormat.PlainText)
        self.script_label.setMaximumWidth(380)
        if scene.scripts:
            toolbar.addWidget(self.script_label)
            self._start_scripts()

    def _start_scripts(self) -> None:
        if not self.simulation.scene.scripts:
            return
        self._script_time = 0.0
        self._script_started = False
        self.script_label.setText("Starting Python…")
        host = ScriptHost(self.simulation.scene, self)
        self.script_host = host
        host.result.connect(lambda result: self._script_result(host, result))
        host.fault.connect(self._script_fault)
        host.finished.connect(self._scripts_finished)
        host.start()

    def _script_result(self, host: ScriptHost, result: ScriptResult) -> None:
        if host is not self.script_host:
            return
        if time.monotonic() - self._log_window >= 1:
            self._log_window, self._log_count = time.monotonic(), 0
        for message in result.logs:
            if self._log_count < 32:
                print("SCRIPT_LOG " + json.dumps(message), flush=True)
                self._log_count += 1
            elif self._log_count == 32:
                print('SCRIPT_LOG "Further Python logs suppressed for this second."', flush=True)
                self._log_count += 1
        if result.fault is not None or self._closing or self._restart_pending or host.stopping:
            return
        if not self.paused and (not self._script_started or self.isActiveWindow()):
            self.simulation.apply(result)
            self._sync_position()
        self._script_started = True
        self.script_label.setText("Python active")

    def _script_fault(self, fault: ScriptFault) -> None:
        self.paused = True
        self.pause_button.setText("Restart to retry")
        self.pause_button.setEnabled(False)
        self.keys.clear()
        self.sound_player.stop()
        location = f"line {fault.line}: " if fault.line else ""
        self.script_label.setText("Python stopped · " + location + fault.message[:80])
        self.script_label.setToolTip(f"{fault.path}:{fault.line} — {fault.message}")
        print("SCRIPT_ERROR " + json.dumps(asdict(fault)), flush=True)

    def _scripts_finished(self) -> None:
        if self._closing:
            self._finish_close()
        elif self._restart_pending:
            self._restart_pending = False
            self.restart()

    def _sync_position(self) -> None:
        self.items[self.simulation.controlled.id].setPos(self.simulation.x, self.simulation.y)
        for identity in self.simulation.changed:
            body, item = self.simulation.bodies[identity], self.items[identity]
            item.setPos(body.x, body.y)
            item.setTransformOriginPoint(item.boundingRect().center())
            item.setRotation(body.rotation)
            item.setVisible(body.visible)
            if isinstance(item, QAbstractGraphicsShapeItem):
                item.setBrush(QBrush(QColor(body.color)))
        self.simulation.changed.clear()
        for coin in self.simulation.coins:
            self.items[coin.id].setVisible(
                coin.visible and coin.id not in self.simulation.collected
            )
        count = len(self.simulation.collected)
        clip = self.simulation.scene.coin_sound
        if count > self._audio_count and clip is not None and not self.paused:
            self.sound_player.play(self._sound_pcm, clip.rate, clip.channels, clip.width)
        self._audio_count = count
        self.view.queue_animation_updates(self.animator.update(self._ticks))
        if self.simulation.coins:
            suffix = " · All collected! · Restart for another run" if self.simulation.won else ""
            self.score_label.setText(
                f"  Collected: {len(self.simulation.collected)}/"
                f"{len(self.simulation.coins)}{suffix}"
            )

        if self.simulation.scene.scripts:
            existing = self.score_label.text() if self.simulation.coins else ""
            self.score_label.setText(f"{existing} · Score: {self.simulation.score}")

    def tick(self) -> None:
        now = time.monotonic()
        elapsed = min(now - self._last_tick, 0.1)
        self._last_tick = now
        host = self.script_host
        if self.paused or not self.isActiveWindow() or (host is not None and not host.ready):
            self.keys.clear()
            self._accumulator = 0
            return
        self._accumulator += elapsed
        horizontal = int(bool(self.keys & self.right)) - int(bool(self.keys & self.left))
        vertical = int(bool(self.keys & self.down)) - int(bool(self.keys & self.up))
        if host is not None and self.simulation.controlled.id in host.bindings:
            horizontal = vertical = 0
        while self._accumulator >= FIXED_STEP:
            self.simulation.step(horizontal, vertical)
            self._ticks += 1
            self._accumulator -= FIXED_STEP
        self._sync_position()
        if host is not None:
            self._script_time = min(self._script_time + elapsed, 0.1)
            identities = set(host.bindings) | {self.simulation.controlled.id}
            positions = {
                identity: (self.simulation.bodies[identity].x, self.simulation.bodies[identity].y)
                for identity in identities
            }
            if host.step(
                self._script_time,
                self._ticks * FIXED_STEP,
                sorted(KEY_NAMES[key] for key in self.keys if key in KEY_NAMES),
                positions,
                self.simulation.events,
            ):
                self._script_time = 0.0
                self.simulation.events.clear()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        if self.paused:
            self.sound_player.stop()
        self.pause_button.setText("Resume" if self.paused else "Pause")
        self.keys.clear()
        self._accumulator = 0
        self._last_tick = time.monotonic()

    def restart(self) -> None:
        if self.script_host is not None and self.script_host.active:
            self._restart_pending = True
            self.paused = True
            self.keys.clear()
            self.script_host.stop()
            return
        if self.script_host is not None:
            self.script_host.deleteLater()
            self.script_host = None
        self.sound_player.stop()
        self._audio_count = 0
        self.paused = False
        self.pause_button.setText("Pause")
        self.pause_button.setEnabled(True)
        self.simulation = Simulation(self.simulation.scene, self.simulation.controlled.id)
        self._ticks = 0
        self.keys.clear()
        self._accumulator = 0
        self._last_tick = time.monotonic()
        for entity in self.simulation.scene.entities:
            body = self.simulation.bodies[entity.id]
            self.items[entity.id].setVisible(True)
            self.simulation.changed.add(body.id)
        self._sync_position()
        self._start_scripts()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() in self.movement_keys or (
            self.script_host is not None and event.key() in KEY_NAMES
        ):
            self.keys.add(event.key())
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if (
            event.key() in self.movement_keys
            or (self.script_host is not None and event.key() in KEY_NAMES)
        ) and not event.isAutoRepeat():
            self.keys.discard(event.key())
        else:
            super().keyReleaseEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.keys.clear()
            self.sound_player.stop()
        super().changeEvent(event)

    def _audio_message(self, message: str) -> None:
        self.audio_label.setText(message[:72])
        self.audio_label.setToolTip(message)

    def _audio_finished(self) -> None:
        if self._closing:
            self._finish_close()

    def _finish_close(self) -> None:
        if not self.sound_player.active and not (self.script_host and self.script_host.active):
            self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        self.keys.clear()
        if self.sound_player.active or (self.script_host and self.script_host.active):
            event.ignore()
            if not self._closing:
                self._closing = True
                self._restart_pending = False
                self.sound_player.stop()
                if self.script_host is not None:
                    self.script_host.stop()
        else:
            super().closeEvent(event)
