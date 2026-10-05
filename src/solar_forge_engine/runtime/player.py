"""Native Play window for data-only scenes and built-in keyboard movement."""

import base64
import time

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QBrush, QCloseEvent, QColor, QKeyEvent, QPaintEvent, QResizeEvent
from PySide6.QtWidgets import (
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
from solar_forge_engine.runtime.simulation import FIXED_STEP, WORLD_HEIGHT, WORLD_WIDTH, Simulation

LEFT = {Qt.Key.Key_A, Qt.Key.Key_Left}
RIGHT = {Qt.Key.Key_D, Qt.Key.Key_Right}
UP = {Qt.Key.Key_W, Qt.Key.Key_Up}
DOWN = {Qt.Key.Key_S, Qt.Key.Key_Down}
MOVEMENT_KEYS = LEFT | RIGHT | UP | DOWN
DENSE_ANIMATION_CHANGES = 1000


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
        toolbar.addWidget(
            QLabel(f"  {self.simulation.controlled.name} · {key_label} · Esc closes   ")
        )
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
        if scene.coin_sound is not None:
            toolbar.addWidget(self.audio_label)
            self.audio_label.setAccessibleName("Game sound status")
            self.sound_player.message.connect(self._audio_message)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self._sync_position()

    def _sync_position(self) -> None:
        self.items[self.simulation.controlled.id].setPos(self.simulation.x, self.simulation.y)
        for coin in self.simulation.coins:
            self.items[coin.id].setVisible(coin.id not in self.simulation.collected)
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

    def tick(self) -> None:
        now = time.monotonic()
        elapsed = min(now - self._last_tick, 0.1)
        self._last_tick = now
        if self.paused or not self.isActiveWindow():
            self.keys.clear()
            self._accumulator = 0
            return
        self._accumulator += elapsed
        horizontal = int(bool(self.keys & self.right)) - int(bool(self.keys & self.left))
        vertical = int(bool(self.keys & self.down)) - int(bool(self.keys & self.up))
        while self._accumulator >= FIXED_STEP:
            self.simulation.step(horizontal, vertical)
            self._ticks += 1
            self._accumulator -= FIXED_STEP
        self._sync_position()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        if self.paused:
            self.sound_player.stop()
        self.pause_button.setText("Resume" if self.paused else "Pause")
        self.keys.clear()
        self._accumulator = 0
        self._last_tick = time.monotonic()

    def restart(self) -> None:
        self.sound_player.stop()
        self._audio_count = 0
        self.paused = False
        self.pause_button.setText("Pause")
        self.simulation = Simulation(self.simulation.scene, self.simulation.controlled.id)
        self._ticks = 0
        self.keys.clear()
        self._accumulator = 0
        self._last_tick = time.monotonic()
        self._sync_position()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() in self.movement_keys:
            self.keys.add(event.key())
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() in self.movement_keys and not event.isAutoRepeat():
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
            self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        self.keys.clear()
        if self.sound_player.active:
            event.ignore()
            if not self._closing:
                self._closing = True
                self.sound_player.stop()
        else:
            super().closeEvent(event)
