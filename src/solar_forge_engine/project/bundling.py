"""Offline, exclusive Linux bundles from the trusted Python/Qt installation."""

import gzip
import hashlib
import importlib.metadata
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import tempfile
from importlib.resources import files
from pathlib import Path

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.project.exporting import export_game
from solar_forge_engine.project.runtime_dependencies import (
    package_root,
    python_dependencies,
    select_dependencies,
)
from solar_forge_engine.project.storage import atomic_write

MAX_BUNDLE_BYTES = 256 * 1024 * 1024
MAX_BUNDLE_FILES = 4096
LAUNCHER = b"""#!/bin/sh
set -eu
bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec "$bundle_dir/runtime/bin/python3.14" -I "$bundle_dir/game.pyz" "$@"
"""
BUNDLE_README = """Solar Forge native Linux game

Extract the whole archive, then run ./Play from inside the extracted folder.
The folder can be moved; keep Play, game.pyz, runtime and notices together.
Python and Qt are included. No editor, pip, model provider or Docker is needed.

Check dependencies without executing game source: ./Play --check-runtime
Machine-readable check: ./Play --check-runtime --json
Exercise actual gameplay (including attached scripts): ./Play --smoke-check

Target: x86_64 Linux with glibc; Wayland desktop. The offscreen platform is
included for CI. X11/xcb, macOS, Windows and musl/Alpine are not bundled targets.
System graphics, fonts, sound and OS scripting restrictions remain prerequisites.
See bundle.json for exact versions and external native library requirements.
Audio is optional and uses the system pw-play/PipeWire session when available.
Scripted games require Linux 6.12+, Landlock ABI 6+ and libseccomp.so.2.

Arch dependencies (install through your normal package manager):
libglvnd libxkbcommon dbus glib2 fontconfig wayland ttf-dejavu libseccomp
Python builds may also need: bzip2 expat libffi openssl sqlite gdbm readline
ncurses libnsl xz. The dependency report identifies missing libraries.

Third-party notices and source locations are in notices/. Qt/PySide shared
libraries remain replaceable in runtime/lib/python3.14/site-packages. Preserve
notices when redistributing, and comply with the included dependency licenses.
"""


def _copy_python(root: Path) -> list[str]:
    base = Path(sys.base_prefix).resolve(strict=True)
    executable = Path(sys.executable).resolve(strict=True)
    if not executable.is_relative_to(base):
        raise ValueError("The Python interpreter is outside its installation prefix.")
    interpreter = root / "runtime/bin/python3.14"
    interpreter.parent.mkdir(parents=True)
    shutil.copyfile(executable, interpreter)
    interpreter.chmod(0o755)
    standard_library = Path(sysconfig.get_path("stdlib")).resolve(strict=True)
    if not standard_library.is_relative_to(base):
        raise ValueError("The Python standard library is outside its installation prefix.")
    destination = root / "runtime/lib/python3.14"
    excluded = {"site-packages", "__pycache__", "test", "tests", "idlelib", "tkinter", "turtledemo"}
    total, count = 0, 0
    for folder, directories, filenames in os.walk(standard_library, followlinks=False):
        directories[:] = [name for name in directories if name not in excluded]
        for name in [*directories, *filenames]:
            if (Path(folder) / name).is_symlink():
                raise ValueError("The Python standard library contains a symbolic link.")
        for name in filenames:
            if name == "turtle.py" or name.startswith("_tkinter"):
                continue
            if not (name.endswith((".py", ".so")) or name == "LICENSE.txt"):
                continue
            source = Path(folder) / name
            if not source.is_file():
                raise ValueError("The Python standard library contains an unsafe file.")
            total += source.stat().st_size
            count += 1
            if total > MAX_BUNDLE_BYTES // 2 or count > MAX_BUNDLE_FILES // 2:
                raise ValueError("The Python standard library exceeds its packaging limit.")
            target = destination / source.relative_to(standard_library)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    native, external = python_dependencies(executable, standard_library, base)
    for name, source in native.items():
        shutil.copyfile(source, root / "runtime/lib" / name)
    relocated, _ = python_dependencies(interpreter, destination, root / "runtime")
    if set(relocated) != set(native):
        raise ValueError(
            "Python still resolves installation libraries outside the bundle. "
            "Use the frozen managed Python or Docker installation."
        )
    license_path = destination / "LICENSE.txt"
    if not license_path.is_file():
        raise ValueError("The installed Python license text is missing.")
    notices = root / "notices"
    notices.mkdir()
    shutil.copyfile(license_path, notices / "Python.txt")
    return external


def export_bundle(path: Path, scene: Scene) -> int:
    """Package interpreter and Widgets libraries, never running authored game source."""
    if not path.name.endswith(".tar.gz"):
        raise ValueError("Bundled Linux games must use the .tar.gz extension.")
    if path.is_symlink():
        raise ValueError("Do not export through symbolic links.")
    if path.exists():
        raise FileExistsError("Choose a new filename; an exported game already exists here.")
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise ValueError("Native bundles currently require x86_64 Linux.")
    if sys.version_info[:3] != (3, 14, 7):
        raise ValueError("Bundle exports require the frozen Python 3.14.7 installation.")
    for package in ("PySide6-Essentials", "shiboken6"):
        if importlib.metadata.version(package) != "6.11.2":
            raise ValueError("Bundle exports require the frozen Qt 6.11.2 installation.")
    roots = {name: package_root(name) for name in ("PySide6", "shiboken6")}
    selected, external = select_dependencies(roots)
    with tempfile.TemporaryDirectory(prefix="solar-bundle-") as temporary:
        root = Path(temporary) / "Game"
        root.mkdir()
        export_game(root / "game.pyz", scene)
        python_external = _copy_python(root)
        site = root / "runtime/lib/python3.14/site-packages"
        for relative, source in selected.items():
            target = site / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        notice_root = files("solar_forge_engine.project").joinpath("notices")
        for name in (
            "qtbase.txt",
            "qtwayland.txt",
            "pyside.txt",
            "python-standalone.txt",
            "cpython.txt",
            "icu.txt",
            "sources.json",
            "README.md",
        ):
            (root / "notices" / name).write_bytes(notice_root.joinpath(name).read_bytes())
        (root / "Play").write_bytes(LAUNCHER)
        (root / "Play").chmod(0o755)
        (root / "README.txt").write_text(BUNDLE_README, encoding="utf-8")
        # Empty-environment worker startup must work after relocation: no PATH,
        # PYTHONHOME, LD_LIBRARY_PATH, installed engine or original venv required.
        interpreter = root / "runtime/bin/python3.14"
        try:
            check = subprocess.run(
                [
                    str(interpreter),
                    "-I",
                    "-S",
                    "-c",
                    "import sys, sysconfig; print(sys.prefix); print(sysconfig.get_path('stdlib'))",
                ],
                env={},
                cwd="/",
                capture_output=True,
                text=True,
                timeout=5,
            )
            if check.returncode or check.stdout.splitlines() != [
                str(root / "runtime"),
                str(root / "runtime/lib/python3.14"),
            ]:
                raise ValueError("This Python installation cannot be relocated safely.")
            environment = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QPA_PLATFORMTHEME="")
            check = subprocess.run(
                [str(root / "Play"), "--check-runtime", "--json"],
                env=environment,
                cwd="/",
                capture_output=True,
                text=True,
                timeout=15,
            )
            if check.returncode:
                raise ValueError(
                    "Bundled runtime validation failed: "
                    + check.stdout[-2000:]
                    + check.stderr[-2000:]
                )
            readiness = json.loads(check.stdout)
            if not isinstance(readiness, dict) or readiness.get("ready") is not True:
                raise ValueError("The bundled runtime did not report readiness.")
        except subprocess.TimeoutExpired as error:
            raise ValueError("Bundled runtime validation exceeded its deadline.") from error
        for cache in root.rglob("__pycache__"):
            shutil.rmtree(cache)
        inventory = []
        total = 0
        for entry in sorted(root.rglob("*")):
            if entry.is_dir():
                continue
            if entry.is_symlink() or not entry.is_file():
                raise ValueError("Native bundles must contain only regular files.")
            raw = entry.read_bytes()
            total += len(raw)
            inventory.append(
                {
                    "path": str(entry.relative_to(root)),
                    "bytes": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                }
            )
            if total > MAX_BUNDLE_BYTES or len(inventory) > MAX_BUNDLE_FILES:
                raise ValueError("Native bundle exceeds its size or file limit.")
        manifest = {
            "format_version": 1,
            "target": "Linux-x86_64-glibc",
            "python": platform.python_version(),
            "qt": "6.11.2",
            "uncompressed_bytes": total,
            "external_qt_libraries": external,
            "external_python_libraries": python_external,
            "files": inventory,
        }
        (root / "bundle.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0, compresslevel=6) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for entry in sorted(root.rglob("*")):
                    if not entry.is_file():
                        continue
                    raw = entry.read_bytes()
                    item = tarfile.TarInfo("Game/" + str(entry.relative_to(root)))
                    item.size = len(raw)
                    item.mode = 0o755 if entry.name in ("Play", "python3.14") else 0o644
                    archive.addfile(item, io.BytesIO(raw))
        raw = buffer.getvalue()
        atomic_write(path, raw, exclusive=True, mode=0o644)
        return len(raw)
