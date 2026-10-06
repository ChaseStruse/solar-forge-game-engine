"""Ember Run: original pixel-art showcase built entirely from editable scene data."""

import base64
import math
import struct
from functools import lru_cache

from solar_forge_engine.core.animation import Animation
from solar_forge_engine.core.audio import SoundClip
from solar_forge_engine.core.scene import Entity, Role, Scene
from solar_forge_engine.core.script import ScriptBinding
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
    floor.rect(0, 0, 32, 32, "091713")
    floor.rect(1, 1, 30, 30, "10221e")
    floor.rect(2, 2, 28, 1, "203b30")
    floor.rect(3, 27, 26, 2, "0a1915")
    for x, y in ((4, 4), (27, 4), (4, 27), (27, 27)):
        floor.rect(x, y, 1, 1, "35513b")
    floor.rect(8, 14, 16, 1, "142b23")
    for x, y in ((6, 9), (22, 18), (13, 24), (26, 11)):
        floor.rect(x, y, 2, 1, "193027")

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
    reactor.rect(2, 2, 60, 106, "52745b")
    reactor.rect(5, 5, 54, 100, "142a23")
    for y in range(12, 100, 12):
        reactor.rect(7, y, 6, 5, "395866")
        reactor.rect(51, y, 6, 5, "395866")
        reactor.rect(8, y + 1, 3, 2, "7ec9c2")
    for radius, color in ((23, "a0c68b"), (21, "0b211b"), (19, "edc371"), (17, "72502d")):
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
    garden = Pixels(32, 24)
    garden.rect(0, 0, 32, 24, "081711")
    garden.rect(1, 1, 30, 21, "405f42")
    garden.rect(2, 2, 28, 2, "b6c484")
    garden.rect(3, 5, 26, 14, "142e22")
    for x in range(4, 29, 6):
        garden.rect(x + 2, 8, 1, 11, "669651")
        garden.rect(x, 9, 3, 3, "8fbd6b")
        garden.rect(x + 3, 12, 3, 3, "43784c")
        garden.rect(x + 1, 6, 3, 3, "cde58c")
        garden.rect(x, 12, 4, 2, "3e7044")
        garden.rect(x + 1, 13, 2, 1, "75a65a")
        garden.rect(x + 2, 9, 1, 2, "daf0aa")
    garden.rect(4, 18, 24, 1, "476a41")
    garden.rect(4, 4, 24, 1, "273f31")
    for x in (2, 28):
        garden.rect(x, 5, 2, 15, "8ba876")
        garden.rect(x, 6, 1, 12, "d4deb0")
    garden.rect(2, 20, 28, 2, "78d9b0")

    solar = Pixels(32, 24)
    solar.rect(0, 0, 32, 24, "081719")
    solar.rect(1, 1, 30, 21, "b79959")
    solar.rect(3, 3, 26, 16, "164750")
    for x in range(4, 29, 6):
        for y in range(4, 19, 5):
            solar.rect(x, y, 4, 3, "28717a")
            solar.rect(x, y, 4, 1, "75c5bc")
    solar.rect(3, 20, 26, 1, "ffe09b")
    solar.rect(4, 4, 1, 14, "96d1c0")
    solar.rect(4, 4, 12, 1, "bce4c8")
    solar.rect(25, 20, 3, 2, "715b36")

    plant = Pixels(24, 32)
    plant.rect(7, 23, 12, 7, "684f36")
    plant.rect(6, 22, 14, 3, "c6ad74")
    plant.rect(12, 7, 2, 16, "669353")
    for x, y, color in ((3, 7, "427951"), (13, 3, "99c96b"), (5, 15, "82b863"), (13, 12, "5a9d66")):
        plant.rect(x, y, 8, 4, color)
        plant.rect(x + 2, y - 2, 4, 2, color)
    plant.rect(9, 26, 2, 2, "a48b56")

    halo = Pixels(32, 32)
    for radius, color in ((15, "183b30"), (13, "2e6550"), (10, "7bdab0")):
        halo.ring(16, 16, radius, color)
    for x, y in ((16, 1), (16, 29), (1, 16), (29, 16)):
        halo.rect(x, y, 2, 2, "ffe1a0")

    vine = Pixels(32, 16)
    for x in range(2, 31, 4):
        y = 5 + (x // 4) % 3
        vine.rect(x, y, 4, 1, "487343")
        vine.rect(x, y - 3, 3, 3, "83ab58")
        vine.rect(x + 2, y + 2, 3, 3, "51854d")
        vine.rect(x + 1, y - 3, 1, 1, "c4d886")

    motes = Pixels(64, 16)
    for frame in range(4):
        x = frame * 16
        for px, py in ((3, 3), (11, 7), (6, 12)):
            motes.rect(x + px, (py + frame * 2) % 14, 1, 1, "e6eda2")
        motes.rect(x + 10, 2 + frame, 2, 1, "7fd5ad")

    return {
        "vine": vine.sprite(),
        "garden": garden.sprite(),
        "solar": solar.sprite(),
        "plant": plant.sprite(),
        "halo": halo.sprite(),
        "motes": motes.sprite(),
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
    "P": "110101110100100",
    "W": "101101111111101",
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


@lru_cache(maxsize=1)
def collection_chime() -> SoundClip:
    """An original short two-note bell, stored as portable mono PCM."""
    rate = 16000
    samples = bytearray()
    for index in range(3200):
        time = index / rate
        envelope = min(time / 0.008, 1) * (1 - time / 0.2) ** 2
        tone = math.sin(math.tau * 880 * time) + 0.5 * math.sin(math.tau * 1320 * time)
        samples.extend(struct.pack("<h", round(tone * envelope * 5500)))
    return SoundClip(rate, 1, 2, base64.b64encode(samples).decode("ascii"))


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
    for x, y in (
        (64, 80),
        (368, 48),
        (608, 48),
        (928, 96),
        (368, 256),
        (608, 256),
        (928, 272),
        (64, 448),
        (368, 480),
        (608, 480),
    ):
        add("Walkway inset", x, y, 64, 64, color="#142c22")
        add("Walkway light", x + 4, y + 4, 2, 14, color="#749e63")
    for y in (64, 272, 496):
        add("Amber guide strip", 32, y + 20, 960, 2, color="#6b653e")
    for x in (80, 384, 624, 944):
        add("Guide rail", x + 12, 40, 2, 488, color="#28533d")
    for x, y, width, height in (
        (0, 0, 1024, 16),
        (0, 560, 1024, 16),
        (0, 16, 16, 544),
        (1008, 16, 16, 544),
    ):
        add("Station bulkhead", x, y, width, height, color="#345e49", role=Role.WALL)
    for index, (x, y, width, height) in enumerate(
        ((192, 96, 144, 112), (192, 352, 144, 112), (704, 96, 192, 96), (704, 384, 192, 96))
    ):
        add("Machine shadow", x + 6, y + 8, width, height, color="#06100e")
        add(
            f"Forge block {index + 1}",
            x,
            y,
            width,
            height,
            texture="garden" if index < 2 else "solar",
            role=Role.WALL,
        )
    for x, y in ((192, 76), (192, 332), (704, 76), (704, 364)):
        add("Trailing garden canopy", x, y, 144, 32, texture="vine")
    for x, y in ((24, 120), (24, 376), (960, 192), (960, 368)):
        add("Station fern", x, y, 40, 56, texture="plant")
    for x, y in ((344, 104), (592, 352), (352, 376), (912, 208)):
        add("Pollen drift", x, y, 64, 64, texture="motes", animated=True)
    add("Reactor shadow", 456, 184, 128, 224, color="#06100e")
    add("Reactor housing", 448, 176, 128, 224, texture="reactor", role=Role.WALL)
    add("Reactor aureole", 464, 232, 96, 96, texture="halo")
    halo_id = entities[-1].id
    add("Living forge", 480, 242, 64, 64, texture="flame", animated=True)
    for x, y in ((56, 248), (848, 484)):
        add("Landing pad", x, y, 80, 80, texture="halo")
    drones = []
    for x, y in ((368, 192), (608, 336)):
        add("Garden tender", x, y, 32, 32, texture="drone", animated=True)
        drones.append(entities[-1].id)
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
        ("SOLAR SANCTUARY", 336, 28, "93d8b6"),
        ("DOCK", 48, 232, "66c4bd"),
        ("GARDEN A", 196, 216, "b7ce89"),
        ("GARDEN B", 196, 472, "b7ce89"),
        ("CORE CHAMBER", 440, 418, "e9ba69"),
        ("SOLAR ARRAY", 736, 206, "e8c780"),
        ("EXTRACTION", 824, 528, "66c4bd"),
        ("WASD OR ARROWS", 32, 536, "95b69b"),
        ("RECOVER 12 CORES", 376, 536, "efd790"),
    ):
        sprite = lettering(title, color)
        entities.append(
            Entity(
                f"ember-{len(entities)}",
                title,
                x,
                y,
                sprite.width * (3 if title == "EMBER RUN" else 2),
                15 if title == "EMBER RUN" else 10,
                sprite=sprite,
            )
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
    orbit = """import math


def start(ctx):
    ctx.state["origin"] = (ctx.x, ctx.y)


def update(ctx, dt):
    x, y = ctx.state["origin"]
    ctx.set_position(x + math.sin(ctx.elapsed * 0.8) * 12, y + math.sin(ctx.elapsed * 1.6) * 5)
    ctx.set_rotation(math.sin(ctx.elapsed * 0.8) * 8)
"""
    spin = """def update(ctx, dt):
    ctx.set_rotation(ctx.elapsed * 18)
"""
    scripts = (
        ScriptBinding.from_source(halo_id, "reactor_aureole", spin),
        *(ScriptBinding.from_source(entity_id, "garden_tender", orbit) for entity_id in drones),
    )
    return Scene(
        "Ember Run — solar sanctuary",
        tuple(entities),
        coin_sound=collection_chime(),
        scripts=scripts,
    )


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
