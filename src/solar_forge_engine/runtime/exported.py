"""Read a bounded bundled snapshot without loading editor or project packages."""

import argparse
import json
import sys
from importlib.resources import files

from solar_forge_engine.core.limits import MAX_FILE_BYTES
from solar_forge_engine.core.scene import Scene
from solar_forge_engine.runtime.application import run_scene


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Solar Forge native game",
        epilog="Check dependencies without game code: --check-runtime [--json].",
    )
    parser.add_argument(
        "--smoke-check", action="store_true", help="Briefly exercise playback and close"
    )
    args = parser.parse_args()
    try:
        with files("game_data").joinpath("scene.json").open("rb") as handle:
            raw = handle.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("Game snapshot exceeds 4 MiB.")
        data = json.loads(raw)
        if (
            not isinstance(data, dict)
            or set(data) != {"format_version", "control", "scene"}
            or type(data["format_version"]) is not int
            or data["format_version"] != 1
            or not isinstance(data["control"], str)
        ):
            raise ValueError("Invalid game snapshot.")
        scene = Scene.from_data(data["scene"])
        scene.entity(data["control"])
    except (OSError, ValueError, UnicodeDecodeError, RecursionError) as error:
        print(f"Cannot launch game: {error}", file=sys.stderr)
        return 1
    return run_scene(scene, data["control"], exported=True, smoke=args.smoke_check)
