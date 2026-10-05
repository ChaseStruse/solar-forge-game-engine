"""One native geometry and sprite renderer shared by authoring and built-in playback."""

import base64

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QGraphicsScene

from solar_forge_engine.core.animation import Animation
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
    for index, entity in enumerate(scene.entities):
        item: QGraphicsItem
        if entity.sprite is not None:
            sprite = entity.sprite
            if sprite not in pixmaps:
                pixmaps[sprite] = sprite_pixmap(sprite)
            pixmap = pixmaps[sprite]
            frame_width, frame_height = sprite.width, sprite.height
            if entity.animation is not None:
                frame_width //= entity.animation.columns
                frame_height //= entity.animation.rows
                pixmap = pixmap.copy(0, 0, frame_width, frame_height)
            sprite_item = canvas.addPixmap(pixmap)
            sprite_item.setShapeMode(QGraphicsPixmapItem.ShapeMode.BoundingRectShape)
            sprite_item.setTransform(
                QTransform.fromScale(entity.width / frame_width, entity.height / frame_height)
            )
            item = sprite_item
        else:
            draw = canvas.addEllipse if entity.role == Role.COIN else canvas.addRect
            item = draw(
                0,
                0,
                entity.width,
                entity.height,
                QPen(Qt.PenStyle.NoPen),
                QBrush(QColor(entity.color)),
            )
        item.setPos(entity.x, entity.y)
        item.setZValue(index)
        item.setData(0, entity.id)
        item.setToolTip(entity.name)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, selectable)
        items[entity.id] = item
    return items


class SpriteAnimator:
    """Cache shared frames once; update only visible items whose frame changed."""

    def __init__(self, scene: Scene, items: dict[str, QGraphicsItem]) -> None:
        cache: dict[tuple[Sprite, int, int], tuple[QPixmap, ...]] = {}
        self.entries: list[tuple[QGraphicsPixmapItem, Animation, tuple[QPixmap, ...]]] = []
        for entity in scene.entities:
            if entity.animation is None or entity.sprite is None:
                continue
            animation, sprite = entity.animation, entity.sprite
            key = (sprite, animation.columns, animation.rows)
            if key not in cache:
                sheet = sprite_pixmap(sprite)
                width, height = sprite.width // animation.columns, sprite.height // animation.rows
                cache[key] = tuple(
                    sheet.copy(column * width, row * height, width, height)
                    for row in range(animation.rows)
                    for column in range(animation.columns)
                )
            item = items[entity.id]
            assert isinstance(item, QGraphicsPixmapItem)
            self.entries.append((item, animation, cache[key]))
        self._frames: dict[str, int] = {}

    def update(self, ticks: int) -> int:
        """Return the number of visible items whose frame pixmap actually changed."""
        changed = 0
        for item, animation, frames in self.entries:
            frame = animation.frame_at(ticks)
            entity_id = str(item.data(0))
            if item.isVisible() and self._frames.get(entity_id) != frame:
                item.setPixmap(frames[frame])
                self._frames[entity_id] = frame
                changed += 1
        return changed
