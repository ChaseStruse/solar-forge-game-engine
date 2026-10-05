"""Ember Run: original pixel-art showcase built entirely from editable scene data."""

import base64
from functools import lru_cache

from solar_forge_engine.core.animation import Animation
from solar_forge_engine.core.scene import Entity, Role, Scene
from solar_forge_engine.core.sprite import Sprite


class Pixels:
    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.data = bytearray(width * height * 4)

    def rect(self, x: int, y: int, width: int, height: int, color: str) -> None:
        rgba = bytes.fromhex(color.removeprefix("#")) + b"\xff"
        for row in range(max(0, y), min(self.height, y + height)):
            for column in range(max(0, x), min(self.width, x + width)):
                offset = (row * self.width + column) * 4
                self.data[offset : offset + 4] = rgba

    def ring(self, x: int, y: int, radius: int, color: str, thickness: int = 1) -> None:
        for row in range(y - radius, y + radius + 1):
            for column in range(x - radius, x + radius + 1):
                distance = (column - x) ** 2 + (row - y) ** 2
                if (radius - thickness) ** 2 <= distance <= radius**2:
                    self.rect(column, row, 1, 1, color)

    def sprite(self) -> Sprite:
        return Sprite(self.width, self.height, base64.b64encode(self.data).decode())


@lru_cache(maxsize=1)
def artwork() -> dict[str, Sprite]:
    floor = Pixels(32, 32)
    floor.rect(0, 0, 32, 32, "15232b")
    floor.rect(1, 1, 30, 30, "1b2b34")
    floor.rect(2, 2, 28, 1, "283d46")
    floor.rect(3, 27, 26, 2, "142129")
    for x, y in ((4, 4), (27, 4), (4, 27), (27, 27)):
        floor.rect(x, y, 1, 1, "39505a")
    floor.rect(8, 14, 16, 1, "1f313a")

    panel = Pixels(32, 24)
    panel.rect(0, 0, 32, 24, "0c151e")
    panel.rect(1, 1, 30, 21, "385361")
    panel.rect(2, 2, 28, 2, "6b8791")
    panel.rect(3, 5, 26, 15, "223641")
    for x in range(5, 27, 4):
        panel.rect(x, 7, 2, 10, "122630")
        panel.rect(x, 7, 1, 10, "4e6670")
    panel.rect(2, 20, 28, 2, "e5a84a")
    for x in range(3, 29, 6):
        panel.rect(x, 20, 3, 2, "6a4a29")
    for x in (2, 28):
        panel.rect(x, 4, 2, 2, "9bb4b9")

    reactor = Pixels(64, 112)
    reactor.rect(0, 0, 64, 112, "09151e")
    reactor.rect(2, 2, 60, 106, "2d4654")
    reactor.rect(5, 5, 54, 100, "172b37")
    for y in range(12, 100, 12):
        reactor.rect(7, y, 6, 5, "395866")
        reactor.rect(51, y, 6, 5, "395866")
        reactor.rect(8, y + 1, 3, 2, "7ec9c2")
    for radius, color in ((23, "6c8490"), (21, "0b1721"), (19, "ce883c"), (17, "503729")):
        reactor.ring(32, 52, radius, color, 2)
    reactor.rect(20, 87, 24, 3, "f2b95d")
    reactor.rect(23, 94, 18, 2, "658695")

    flame = Pixels(64, 16)
    for frame in range(4):
        x = frame * 16
        for y in range(3, 14):
            span = min(6, 1 + (y - 3) // 2)
            flame.rect(x + 8 - span, y, span * 2, 1, "e36532")
        flame.rect(x + 5, 8 - frame % 2, 6, 6, "ffb44d")
        flame.rect(x + 7, 10 - frame % 2, 3, 4, "fff0b2")
        flame.rect(x + 3 + frame * 2, frame % 3, 1, 2, "f3b958")

    drone = Pixels(128, 32)
    for frame in range(4):
        x = frame * 32
        drone.rect(x + 7, 25, 18, 3, "0b161f")
        drone.rect(x + 9, 21, 5, 5, "43636d")
        drone.rect(x + 19, 21, 5, 5, "43636d")
        drone.rect(x + 6, 12, 4, 9, "194654")
        drone.rect(x + 10, 9, 14, 15, "53b9bd")
        drone.rect(x + 11, 10, 12, 2, "9ee9df")
        drone.rect(x + 12, 5, 12, 10, "dfdbb7")
        drone.rect(x + 14, 8, 12, 5, "153842")
        drone.rect(x + 16, 9, 9, 2, "82edf0")
        drone.rect(x + 23, 16, 5, 4, "365462")
        drone.rect(x + 27, 17, 3, 2, "eeb351")
        drone.rect(x + 3, 19, 3 + frame % 2, 2, "ffb34b")

    cores = Pixels(64, 16)
    for frame in range(4):
        x = frame * 16
        for y in range(2, 14):
            span = min(y - 1, 14 - y)
            cores.rect(x + 8 - span, y, 2 * span, 1, "b77737")
        for y in range(4, 12):
            span = min(y - 3, 12 - y)
            cores.rect(x + 8 - span, y, 2 * span, 1, "ffd779")
        cores.rect(x + 7, 5, 2, 6, "fff3c0")
        cores.rect(x + 2 + frame * 3, 1, 1, 2, "fff3c0")

    beacon = Pixels(64, 16)
    for frame in range(4):
        x = frame * 16
        beacon.rect(x + 1, 5, 14, 7, "0e232e")
        beacon.rect(x + 2, 6, 12, 1, "659096")
        beacon.rect(x + 4, 8, 8, 2, "346a6d")
        beacon.rect(x + 4 + frame * 2, 8, 2, 2, "a2f4df")
    return {
        "floor": floor.sprite(),
        "panel": panel.sprite(),
        "reactor": reactor.sprite(),
        "flame": flame.sprite(),
        "drone": drone.sprite(),
        "core": cores.sprite(),
        "beacon": beacon.sprite(),
    }


# Original 3×5 bitmap lettering, rendered as portable sprite data.
FONT = {
    "A": "010101111101101",
    "B": "110101110101110",
    "C": "011100100100011",
    "D": "110101101101110",
    "E": "111100110100111",
    "F": "111100110100100",
    "G": "011100101101011",
    "H": "101101111101101",
    "I": "111010010010111",
    "K": "101101110101101",
    "L": "100100100100111",
    "M": "101111111101101",
    "N": "101111111111101",
    "O": "010101101101010",
    "R": "110101110101101",
    "S": "011100010001110",
    "T": "111010010010010",
    "U": "101101101101111",
    "V": "101101101101010",
    "X": "101101010101101",
    "Y": "101101010010010",
    "1": "010110010010111",
    "2": "110001010100111",
    "4": "101101111001001",
    " ": "000000000000000",
}


def lettering(value: str, color: str = "8cabb2") -> Sprite:
    image = Pixels(len(value) * 4, 5)
    for index, character in enumerate(value):
        for pixel, bit in enumerate(FONT[character]):
            if bit == "1":
                image.rect(index * 4 + pixel % 3, pixel // 3, 1, 1, color)
    return image.sprite()


def ember_run() -> Scene:
    art = artwork()
    entities: list[Entity] = []

    def add(
        name: str,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        texture: str | None = None,
        color: str = "#385361",
        role: Role = Role.DECORATION,
        animated: bool = False,
    ) -> None:
        entities.append(
            Entity(
                f"ember-{len(entities)}",
                name,
                x,
                y,
                width,
                height,
                color,
                role,
                art[texture] if texture else None,
                animation=Animation(4, 1, 8) if animated else None,
            )
        )

    for row in range(9):
        for column in range(16):
            add("Deck plating", column * 64, row * 64, 64, 64, texture="floor")
    for y in (64, 272, 496):
        add("Amber guide strip", 32, y + 20, 960, 2, color="#665338")
    for x in (80, 384, 624, 944):
        add("Guide rail", x + 12, 40, 2, 488, color="#263f48")
    for x, y, width, height in (
        (0, 0, 1024, 16),
        (0, 560, 1024, 16),
        (0, 16, 16, 544),
        (1008, 16, 16, 544),
    ):
        add("Station bulkhead", x, y, width, height, color="#304956", role=Role.WALL)
    for index, (x, y, width, height) in enumerate(
        ((192, 96, 144, 112), (192, 352, 144, 112), (704, 96, 192, 96), (704, 384, 192, 96))
    ):
        add(f"Forge block {index + 1}", x, y, width, height, texture="panel", role=Role.WALL)
    add("Reactor housing", 448, 176, 128, 224, texture="reactor", role=Role.WALL)
    add("Living forge", 480, 242, 64, 64, texture="flame", animated=True)
    for x, y in ((212, 104), (212, 360), (740, 104), (740, 392), (928, 32)):
        add("Status beacon", x, y, 64, 16, texture="beacon", animated=True)
    for index, (x, y) in enumerate(
        (
            (96, 96),
            (384, 64),
            (624, 64),
            (944, 112),
            (384, 272),
            (624, 272),
            (944, 288),
            (96, 464),
            (384, 496),
            (624, 496),
            (944, 464),
            (480, 128),
        )
    ):
        add(f"Energy core {index + 1}", x, y, 20, 20, texture="core", role=Role.COIN, animated=True)
    for title, x, y, color in (
        ("EMBER RUN", 32, 28, "e9ba69"),
        ("RECOVER 12 CORES", 336, 28, "93aaa8"),
        ("DOCK", 48, 232, "66c4bd"),
        ("FORGE A", 196, 216, "b48b5d"),
        ("FORGE B", 196, 472, "b48b5d"),
        ("CORE CHAMBER", 440, 418, "e9ba69"),
        ("COOLANT", 736, 206, "729fa9"),
        ("EXTRACTION", 824, 528, "66c4bd"),
    ):
        sprite = lettering(title, color)
        entities.append(
            Entity(f"ember-{len(entities)}", title, x, y, sprite.width * 2, 10, sprite=sprite)
        )
    entities.append(
        Entity(
            "courier",
            "Forge courier",
            80,
            272,
            28,
            28,
            role=Role.PLAYER,
            sprite=art["drone"],
            move_speed=220,
            animation=Animation(4, 1, 8),
        )
    )
    return Scene("Ember Run — recover the twelve energy cores", tuple(entities))


def courier_bay() -> Scene:
    main = ember_run()
    decorations = tuple(entity for entity in main.entities[:144])
    art = artwork()
    return Scene(
        "Courier Bay — sprite playground",
        (
            *decorations,
            Entity(
                "bay-player",
                "Forge courier",
                100,
                272,
                48,
                48,
                role=Role.PLAYER,
                sprite=art["drone"],
                animation=Animation(4, 1, 8),
            ),
            Entity(
                "bay-reactor",
                "Forge flame",
                480,
                192,
                128,
                128,
                sprite=art["flame"],
                animation=Animation(4, 1, 12),
            ),
            *(
                Entity(
                    f"bay-core-{index}",
                    "Energy core",
                    x,
                    272,
                    32,
                    32,
                    role=Role.COIN,
                    sprite=art["core"],
                    animation=Animation(4, 1, 8),
                )
                for index, x in enumerate((240, 360, 680, 800))
            ),
        ),
    )
