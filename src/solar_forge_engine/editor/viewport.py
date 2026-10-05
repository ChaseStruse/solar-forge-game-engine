"""Single-object drag previews; authored positions change only on release."""

import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFocusEvent, QHideEvent, QKeyEvent, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsView


class SceneView(QGraphicsView):
    drag_started = Signal()
    position_committed = Signal(str, float, float)

    def __init__(self) -> None:
        super().__init__()
        self.snap_enabled = False
        self.grid_size = 16
        self._item: QGraphicsItem | None = None
        self._origin = QPointF()
        self._pointer = QPointF()
        self._press = QPoint()
        self._moving = False

    def set_grid(self, enabled: bool, size: int) -> None:
        self.cancel_drag()
        self.snap_enabled = enabled
        self.grid_size = size
        self.viewport().update()

    def cancel_drag(self) -> None:
        if self._item is not None:
            self._item.setPos(self._origin)
        self._item = None
        self._moving = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.cancel_drag()
        item = self.itemAt(event.position().toPoint())
        if event.button() != Qt.MouseButton.LeftButton or item is None or item.data(0) is None:
            super().mousePressEvent(event)
            return
        self.setFocus()
        if not item.isSelected() or len(self.scene().selectedItems()) != 1:
            self.scene().clearSelection()
            item.setSelected(True)
        self._item = item
        self._origin = item.pos()
        self._press = event.position().toPoint()
        self._pointer = self.mapToScene(self._press)
        self.drag_started.emit()
        event.accept()

    def _preview(self, position: QPoint) -> None:
        if self._item is None:
            return
        if not self._moving:
            self._moving = (
                position - self._press
            ).manhattanLength() >= QApplication.startDragDistance()
        if not self._moving:
            return
        target = self._origin + self.mapToScene(position) - self._pointer
        coordinates = [target.x(), target.y()]
        if self.snap_enabled:
            coordinates = [
                math.floor(value / self.grid_size + 0.5) * self.grid_size for value in coordinates
            ]
        self._item.setPos(*(min(100_000, max(-100_000, value)) for value in coordinates))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._item is None:
            super().mouseMoveEvent(event)
        else:
            self._preview(event.position().toPoint())
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._item is None or event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        self._preview(event.position().toPoint())
        item = self._item
        entity_id = str(item.data(0))
        target = item.pos()
        changed = self._moving and target != self._origin
        self.cancel_drag()
        if changed:
            self.position_committed.emit(entity_id, target.x(), target.y())
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape and self._item is not None:
            self.cancel_drag()
            event.accept()
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event: QFocusEvent) -> None:
        self.cancel_drag()
        super().focusOutEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:
        self.cancel_drag()
        super().hideEvent(event)

    def drawBackground(self, painter: QPainter, rect: QRectF | QRect) -> None:
        super().drawBackground(painter, rect)
        if not self.snap_enabled or self.grid_size * abs(self.transform().m11()) < 4:
            return
        left = math.floor(rect.left() / self.grid_size)
        right = math.ceil(rect.right() / self.grid_size)
        top = math.floor(rect.top() / self.grid_size)
        bottom = math.ceil(rect.bottom() / self.grid_size)
        if right - left + bottom - top > 512:
            return
        pen = QPen(QColor("#29313c"))
        pen.setCosmetic(True)
        painter.setPen(pen)
        for column in range(left, right + 1):
            x = column * self.grid_size
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        for row in range(top, bottom + 1):
            y = row * self.grid_size
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
