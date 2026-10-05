"""Receive a bounded JSON snapshot on stdin. Never import project scripts."""

import argparse
import json
import sys

from PySide6.QtWidgets import QApplication

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.project.storage import MAX_FILE_BYTES
from solar_forge_engine.runtime.player import PlayerWindow


def main() -> int:
    parser = argparse.ArgumentParser(description="Solar Forge built-in scene player")
    parser.add_argument("--control", required=True, help="Entity ID controlled by the keyboard")
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError("Preview snapshot exceeds 4 MiB.")
        scene = Scene.from_data(json.loads(raw))
        scene.entity(args.control)
    except (ValueError, UnicodeDecodeError, RecursionError) as error:
        print(f"Cannot play scene: {error}", file=sys.stderr)
        return 1
    app = QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    window = PlayerWindow(scene, args.control)
    window.show()
    print("Preview ready", flush=True)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
