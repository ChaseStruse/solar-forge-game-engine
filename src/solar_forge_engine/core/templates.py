"""Editable starter data; no project code executes when a template opens."""

from solar_forge_engine.core.scene import Entity, Role, Scene


def coin_collector() -> Scene:
    player = Entity("player", "Player", 80, 80, 32, 32, "#65d6ce", Role.PLAYER)
    walls = tuple(
        Entity(f"wall-{index}", f"Wall {index + 1}", x, y, width, height, "#667387", Role.WALL)
        for index, (x, y, width, height) in enumerate(
            [
                (300, 130, 32, 300),
                (600, 0, 32, 300),
                (700, 430, 220, 24),
            ]
        )
    )
    coins = tuple(
        Entity(f"coin-{index}", f"Coin {index + 1}", x, y, 20, 20, "#f4b544", Role.COIN)
        for index, (x, y) in enumerate([(170, 90), (430, 90), (450, 400), (750, 100), (920, 500)])
    )
    return Scene("Coin collector", (player, *walls, *coins))
