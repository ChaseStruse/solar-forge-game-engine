"""One native rectangle renderer shared by authoring and built-in playback."""

from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsScene

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.runtime.simulation import WORLD_HEIGHT, WORLD_WIDTH


def render_scene(
    canvas: QGraphicsScene, scene: Scene, *, selectable: bool = False
) -> dict[str, QGraphicsRectItem]:
    canvas.clear()
    border = canvas.addRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT, QPen(QColor("#596170")))
    border.setZValue(-1)
    items = {}
    for entity in scene.entities:
        item = canvas.addRect(
            0, 0, entity.width, entity.height, QPen(QColor("#ffffff")), QBrush(QColor(entity.color))
        )
        item.setPos(entity.x, entity.y)
        item.setData(0, entity.id)
        item.setToolTip(entity.name)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, selectable)
        items[entity.id] = item
    return items
