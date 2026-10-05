"""One native geometry and sprite renderer shared by authoring and built-in playback."""

import base64

from PySide6.QtGui import QBrush, QColor, QImage, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene

from solar_forge_engine.core.scene import Role, Scene
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.runtime.simulation import WORLD_HEIGHT, WORLD_WIDTH


def sprite_pixmap(sprite: Sprite) -> QPixmap:
    raw = base64.b64decode(sprite.pixels)
    image = QImage(raw, sprite.width, sprite.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(image.copy())


def render_scene(
    canvas: QGraphicsScene, scene: Scene, *, selectable: bool = False
) -> dict[str, QGraphicsItem]:
    canvas.clear()
    border = canvas.addRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT, QPen(QColor("#596170")))
    border.setZValue(-1)
    items: dict[str, QGraphicsItem] = {}
    pixmaps: dict[Sprite, QPixmap] = {}
    for entity in scene.entities:
        item: QGraphicsItem
        if entity.sprite is not None:
            sprite = entity.sprite
            if sprite not in pixmaps:
                pixmaps[sprite] = sprite_pixmap(sprite)
            sprite_item = canvas.addPixmap(pixmaps[sprite])
            sprite_item.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
            sprite_item.setTransform(
                QTransform.fromScale(entity.width / sprite.width, entity.height / sprite.height)
            )
            item = sprite_item
        else:
            draw = canvas.addEllipse if entity.role == Role.COIN else canvas.addRect
            item = draw(
                0,
                0,
                entity.width,
                entity.height,
                QPen(QColor("#ffffff")),
                QBrush(QColor(entity.color)),
            )
        item.setPos(entity.x, entity.y)
        item.setData(0, entity.id)
        item.setToolTip(entity.name)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, selectable)
        items[entity.id] = item
    return items
