"""Measure and exercise a Widgets-only Qt subset in a fresh Python environment.

This packaging spike copies only installed, trusted runtime dependencies. It never
loads a project script, downloads a package, or publishes a distribution bundle.
"""

import argparse
import base64
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
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

DEPENDENCY = re.compile(r"^\s*(\S+)\s+=>\s+(.+?)\s+\(0x[0-9a-f]+\)", re.MULTILINE)
FORBIDDEN = ("qml", "quick", "webengine", "webchannel")


def package_root(name: str) -> Path:
    spec = importlib.util.find_spec(name)
    if spec is None or spec.origin is None:
        raise ValueError(f"Required installed package is missing: {name}")
    return Path(spec.origin).resolve().parent


def footprint(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def select_dependencies(roots: dict[str, Path]) -> tuple[dict[str, Path], list[str]]:
    qt = roots["PySide6"]
    seeds = [qt / f"{module}.abi3.so" for module in ("QtCore", "QtGui", "QtWidgets")]
    seeds += [roots["shiboken6"] / "Shiboken.abi3.so"]
    seeds += [
        qt / "Qt/plugins/platforms" / f"libq{plugin}.so" for plugin in ("wayland", "offscreen")
    ]
    seeds += [qt / "Qt/plugins/wayland-shell-integration/libxdg-shell.so"]
    selected: dict[str, Path] = {}
    external: set[str] = set()
    environment = dict(os.environ, LC_ALL="C")
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT"):
        environment.pop(key, None)

    def include(path: Path) -> bool:
        normalized = path.resolve(strict=True)
        for package, root in roots.items():
            if normalized.is_relative_to(root):
                relative = f"{package}/{normalized.relative_to(root)}"
                if any(part in relative.casefold() for part in FORBIDDEN):
                    raise ValueError(f"Unexpected non-Widgets dependency: {relative}")
                selected[relative] = normalized
                return True
        return False

    for seed in seeds:
        if not include(seed):
            raise ValueError("A runtime seed escaped its installed package.")
        result = subprocess.run(
            ["/usr/bin/ldd", str(seed)],
            capture_output=True,
            text=True,
            timeout=3,
            env=environment,
            check=True,
        )
        if len(result.stdout) > 64 * 1024 or "=> not found" in result.stdout:
            raise ValueError(f"A native dependency could not be resolved: {seed.name}")
        for name, filename in DEPENDENCY.findall(result.stdout):
            if not include(Path(filename)):
                external.add(name)
    for package, root in roots.items():
        python_files = list(root.glob("*.py"))
        if package == "PySide6":
            python_files += list((root / "support").glob("*.py"))
        for path in python_files:
            include(path)
    if len(selected) > 128:
        raise ValueError("The Widgets runtime subset exceeded its file bound.")
    return selected, sorted(external)


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
