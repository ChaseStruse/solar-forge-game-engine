"""Measure and exercise a Widgets-only Qt subset in a fresh Python environment.

This packaging spike copies only installed, trusted runtime dependencies. It never
loads a project script, downloads a package, or publishes a distribution bundle.
"""

import argparse
import base64
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import venv
from pathlib import Path

from solar_forge_engine.core.animation import Animation
from solar_forge_engine.core.scene import Entity, Role, Scene
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.project.exporting import export_game
from solar_forge_engine.project.runtime_dependencies import (
    footprint,
    package_root,
    select_dependencies,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qpa", choices=("offscreen", "wayland"), default="offscreen")
    args = parser.parse_args()
    if platform.system() != "Linux" or sys.version_info[:2] != (3, 14):
        parser.error("This spike requires Linux and Python 3.14.")
    for package in ("PySide6-Essentials", "shiboken6"):
        if importlib.metadata.version(package) != "6.11.2":
            parser.error("Use the frozen PySide6/shiboken6 6.11.2 environment.")
    roots = {name: package_root(name) for name in ("PySide6", "shiboken6")}
    start = time.perf_counter()
    selected, external = select_dependencies(roots)
    selection_ms = (time.perf_counter() - start) * 1000
    with tempfile.TemporaryDirectory(prefix="solar-runtime-package-") as temporary:
        root = Path(temporary)
        environment_root = root / "player-env"
        venv.EnvBuilder(with_pip=False).create(environment_root)
        site = environment_root / "lib/python3.14/site-packages"
        start = time.perf_counter()
        for relative, source in selected.items():
            target = site / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        copy_ms = (time.perf_counter() - start) * 1000
        pixels = base64.b64encode(bytes((80, 220, 140, 255, 245, 190, 70, 255))).decode("ascii")
        scene = Scene(
            "Widgets package check",
            (
                Entity(
                    "player",
                    role=Role.PLAYER,
                    sprite=Sprite(2, 1, pixels),
                    animation=Animation(2, 1, 10),
                ),
                Entity("coin", x=64, role=Role.COIN),
            ),
        )
        archive = root / "Game.pyz"
        archive_bytes = export_game(archive, scene)
        interpreter = str(environment_root / "bin/python")
        environment = dict(
            os.environ,
            QT_QPA_PLATFORM=args.qpa,
            QT_QPA_PLATFORMTHEME="",
            XDG_CONFIG_HOME=str(root / "config"),
            XDG_CACHE_HOME=str(root / "cache"),
        )
        for key in ("PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT"):
            environment.pop(key, None)
        missing = subprocess.run(
            [
                interpreter,
                "-I",
                "-c",
                "import importlib.util; print(importlib.util.find_spec('solar_forge_engine'))",
            ],
            capture_output=True,
            text=True,
            env=environment,
            check=True,
            timeout=5,
        )
        if missing.stdout.strip() != "None":
            raise ValueError("The isolated environment unexpectedly contains the engine.")
        start = time.perf_counter()
        result = subprocess.run(
            [interpreter, "-I", str(archive), "--smoke-check"],
            capture_output=True,
            text=True,
            env=environment,
            timeout=10,
        )
        launch_and_smoke_ms = (time.perf_counter() - start) * 1000
        if result.returncode:
            raise ValueError(f"Subset launch failed: {result.stderr[-4000:]}")
        report = json.loads(result.stdout)
        if (
            not report["runtime_from_archive"]
            or report["editor_loaded"]
            or report["collected"] != 1
        ):
            raise ValueError("The subset did not complete editor-independent gameplay.")
        print(
            json.dumps(
                {
                    "platform": platform.system(),
                    "machine": platform.machine(),
                    "qpa": args.qpa,
                    "python": platform.python_version(),
                    "qt": "6.11.2",
                    "installed_package_bytes": sum(footprint(path) for path in roots.values()),
                    "subset_bytes": sum(path.stat().st_size for path in selected.values()),
                    "subset_files": sorted(selected),
                    "external_system_libraries": external,
                    "selection_ms": round(selection_ms, 3),
                    "copy_ms": round(copy_ms, 3),
                    "launch_and_smoke_ms": round(launch_and_smoke_ms, 3),
                    "archive_bytes": archive_bytes,
                    "game": report,
                    "scope": (
                        "Temporary Widgets/Wayland/offscreen subset; Python, OS libraries "
                        "and fonts remain prerequisites. Not a release bundle."
                    ),
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
