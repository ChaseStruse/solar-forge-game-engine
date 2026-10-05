"""Native Play window for data-only scenes and built-in keyboard movement."""

import time

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QKeyEvent, QResizeEvent
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QMainWindow,
    QPushButton,
    QToolBar,
)

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.runtime.rendering import render_scene
from solar_forge_engine.runtime.simulation import FIXED_STEP, WORLD_HEIGHT, WORLD_WIDTH, Simulation

LEFT = {Qt.Key.Key_A, Qt.Key.Key_Left}
RIGHT = {Qt.Key.Key_D, Qt.Key.Key_Right}
UP = {Qt.Key.Key_W, Qt.Key.Key_Up}
DOWN = {Qt.Key.Key_S, Qt.Key.Key_Down}
MOVEMENT_KEYS = LEFT | RIGHT | UP | DOWN


class GameView(QGraphicsView):
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class PlayerWindow(QMainWindow):
    def __init__(self, scene: Scene, controlled_id: str) -> None:
        super().__init__()
        self.simulation = Simulation(scene, controlled_id)
        self.keys: set[int] = set()
        self.paused = False
        self._accumulator = 0.0
        self._last_tick = time.monotonic()
        self.setWindowTitle(f"Play — {scene.name} — Solar Forge")
        self.resize(1040, 660)
        self.canvas = QGraphicsScene(self)
        self.canvas.setSceneRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT)
        self.items = render_scene(self.canvas, scene)
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
        toolbar.addWidget(
            QLabel(f"  {self.simulation.controlled.name} · WASD / arrows · Esc closes   ")
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
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)
        self._sync_position()

    def _sync_position(self) -> None:
        self.items[self.simulation.controlled.id].setPos(self.simulation.x, self.simulation.y)
        for coin in self.simulation.coins:
            self.items[coin.id].setVisible(coin.id not in self.simulation.collected)
        if self.simulation.coins:
            suffix = " · All coins collected!" if self.simulation.won else ""
            self.score_label.setText(
                f"  Coins: {len(self.simulation.collected)}/{len(self.simulation.coins)}{suffix}"
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
        horizontal = int(bool(self.keys & RIGHT)) - int(bool(self.keys & LEFT))
        vertical = int(bool(self.keys & DOWN)) - int(bool(self.keys & UP))
        while self._accumulator >= FIXED_STEP:
            self.simulation.step(horizontal, vertical)
            self._accumulator -= FIXED_STEP
        self._sync_position()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        self.pause_button.setText("Resume" if self.paused else "Pause")
        self.keys.clear()
        self._accumulator = 0
        self._last_tick = time.monotonic()

    def restart(self) -> None:
        self.paused = False
        self.pause_button.setText("Pause")
        self.simulation = Simulation(self.simulation.scene, self.simulation.controlled.id)
        self.keys.clear()
        self._accumulator = 0
        self._last_tick = time.monotonic()
        self._sync_position()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() in MOVEMENT_KEYS:
            self.keys.add(event.key())
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() in MOVEMENT_KEYS and not event.isAutoRepeat():
            self.keys.discard(event.key())
        else:
            super().keyReleaseEvent(event)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            self.keys.clear()
        super().changeEvent(event)
