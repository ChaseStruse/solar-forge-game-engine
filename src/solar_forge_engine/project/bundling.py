"""Offline Linux folder bundles, built from installed trusted runtime dependencies."""

import hashlib
import importlib.metadata
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
from solar_forge_engine.project.runtime_dependencies import package_root, select_dependencies
from solar_forge_engine.project.storage import flush_directory

MAX_BUNDLE_BYTES = 512 * 1024 * 1024
MAX_BUNDLE_FILES = 5000
STDLIB_EXCLUSIONS = {
    "site-packages",
    "dist-packages",
    "__pycache__",
    "test",
    "tests",
    "ensurepip",
    "idlelib",
    "tkinter",
    "turtledemo",
    "venv",
}
LAUNCHER = """#!/bin/sh
set -eu
bundle_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
unset PYTHONHOME PYTHONPATH LD_PRELOAD LD_AUDIT QT_PLUGIN_PATH QT_QPA_PLATFORM_PLUGIN_PATH
export LD_LIBRARY_PATH="$bundle_dir/runtime/lib"
export QT_PLUGIN_PATH="$bundle_dir/runtime/lib/python3.14/site-packages/PySide6/Qt/plugins"
export QT_QPA_PLATFORMTHEME=
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-wayland}"
exec "$bundle_dir/runtime/bin/python3.14" -I -S -B "$bundle_dir/launch.py" "$@"
"""
BOOTSTRAP = '''"""Start only the bundled interpreter, standard library and Qt bindings."""
import runpy
import sys
from pathlib import Path
from importlib.resources import files

root = Path(__file__).resolve().parent
runtime = root / "runtime"
if Path(sys.base_prefix).resolve() != runtime:
    raise SystemExit("Cannot locate bundled Python. Extract the complete game folder again.")
if sys.version_info[:2] != (3, 14):
    raise SystemExit("This bundle requires its included Python 3.14 runtime.")
sys.dont_write_bytecode = True
sys.path.append(str(runtime / "lib/python3.14/site-packages"))
try:
    import PySide6.QtWidgets
except ImportError as error:
    raise SystemExit(f"Cannot load bundled Qt: {error}. See README.txt for Linux prerequisites.")
sys.argv[0] = str(root / "Game.pyz")
runpy.run_path(sys.argv[0], run_name="__main__")
'''
README = """Solar Forge native Linux game bundle

Extract the complete Game folder, then run ./play from that folder.
The folder can be moved or renamed. Python and Qt are included; the editor,
Docker, uv, pip and a model service are not needed to play.
Use ./play --smoke-check for a brief movement check that exits automatically.

Target: Linux on the build machine's CPU architecture, Wayland desktop.
System graphics libraries, fonts and an active Wayland session are required.
On Arch the graphics prerequisites are mesa, libglvnd, libxkbcommon, wayland,
fontconfig, ttf-dejavu, glib2, dbus and libseccomp (plus their package dependencies).
Optional sound uses the system pipewire-audio client and a running PipeWire session.
QT_QPA_PLATFORM=offscreen ./play --smoke-check checks playback without a desktop.
X11 and other Linux distributions are not validated release targets.

bundle.json records versions, file hashes and external Qt library names.
The library list is diagnostic, not a complete cross-distribution ABI guarantee.
Python was copied from the builder's trusted interpreter installation. Installed
third-party packages, user site packages and project code are not copied into it.
The Qt subset uses dynamically linked Widgets libraries, kept as separate files.

Redistribution status: experimental/private pending a complete notice/source audit.
Installed Python license text and Qt package metadata are included under notices/.
These are not a complete set of third-party notices for every interpreter build or
Qt embedded library. Review redistribution requirements before external release.
Scene scripts run only in the kernel-restricted worker and require system libseccomp.
No unrestricted script fallback is available.
No license is assigned to your game assets or imported content by exporting them.
"""


def python_files() -> dict[str, Path]:
    """Copy the active interpreter's standard library, excluding installed packages."""
    stdlib = Path(sysconfig.get_path("stdlib")).resolve(strict=True)
    selected = {"runtime/bin/python3.14": Path(sys.executable).resolve(strict=True)}
    for path in sorted(stdlib.rglob("*")):
        relative = path.relative_to(stdlib)
        if any(part in STDLIB_EXCLUSIONS for part in relative.parts):
            continue
        if path.name in {"sitecustomize.py", "usercustomize.py"} or path.name.startswith(
            ("_tkinter.", "_test", "_sysconfigdata_")
        ):
            continue
        if path.suffix not in {".py", ".so"} or not path.is_file():
            continue
        if not path.resolve().is_relative_to(stdlib):
            raise ValueError("A Python runtime file points outside its standard library.")
        selected[f"runtime/lib/python3.14/{relative}"] = path
    libdir = Path(sysconfig.get_config_var("LIBDIR"))
    name = sysconfig.get_config_var("INSTSONAME")
    if isinstance(name, str) and name.endswith((".so", ".so.1.0")):
        library = libdir / name
        if library.is_file():
            selected[f"runtime/lib/{name}"] = library.resolve(strict=True)
    license_file = stdlib / "LICENSE.txt"
    if not license_file.is_file():
        raise ValueError("The installed Python runtime is missing LICENSE.txt.")
    selected["notices/Python-LICENSE.txt"] = license_file
    return selected


def _copy_runtime(root: Path) -> list[str]:
    for package in ("PySide6-Essentials", "shiboken6"):
        if importlib.metadata.version(package) != "6.11.2":
            raise ValueError("Bundle export requires the frozen Qt 6.11.2 dependencies.")
    qt_files, external = select_dependencies(
        {name: package_root(name) for name in ("PySide6", "shiboken6")}
    )
    selected = python_files()
    selected.update(
        {f"runtime/lib/python3.14/site-packages/{name}": path for name, path in qt_files.items()}
    )
    if len(selected) > MAX_BUNDLE_FILES:
        raise ValueError("The runtime bundle exceeds its file limit.")
    total = 0
    for relative, source in selected.items():
        total += source.stat().st_size
        if total > MAX_BUNDLE_BYTES:
            raise ValueError("The runtime bundle exceeds 512 MiB.")
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o755 if relative == "runtime/bin/python3.14" else 0o644)
    (root / "notices/Solar-Forge-MIT.txt").write_bytes(
        files("solar_forge_engine").joinpath("LICENSE.txt").read_bytes()
    )
    for package in ("PySide6-Essentials", "shiboken6"):
        metadata = importlib.metadata.distribution(package).read_text("METADATA")
        if not metadata:
            raise ValueError(f"Missing installed package metadata: {package}")
        (root / "notices" / f"{package}-METADATA.txt").write_text(metadata, encoding="utf-8")
    return external


def _validate_interpreter(root: Path) -> None:
    """Reject an interpreter layout that falls back to the builder's installation."""
    environment = dict(os.environ, LD_LIBRARY_PATH=str(root / "runtime/lib"))
    for key in ("PYTHONHOME", "PYTHONPATH", "LD_PRELOAD", "LD_AUDIT"):
        environment.pop(key, None)
    result = subprocess.run(
        [
            str(root / "runtime/bin/python3.14"),
            "-I",
            "-S",
            "-B",
            "-c",
            "import json, sys; print(json.dumps([sys.base_prefix, sys.path]))",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    prefix, paths = json.loads(result.stdout)
    expected = root / "runtime"
    if Path(prefix).resolve() != expected or any(
        not Path(path).resolve().is_relative_to(expected) for path in paths
    ):
        raise ValueError("This Python installation cannot be relocated into a game bundle.")


def export_bundle(path: Path, scene: Scene) -> int:
    """Publish a complete tar.gz exclusively; failures remove only private staging files."""
    if not path.name.lower().endswith(".tar.gz"):
        raise ValueError("Native game bundles must use the .tar.gz extension.")
    if platform.system() != "Linux" or sys.version_info[:2] != (3, 14):
        raise ValueError("Bundle export requires Linux and Python 3.14.")
    if path.exists() or path.is_symlink():
        raise FileExistsError("The export target already exists. Choose a new filename.")
    with tempfile.TemporaryDirectory(prefix=".forge-bundle-", dir=path.parent) as temporary:
        staging = Path(temporary)
        root = staging / "Game"
        root.mkdir()
        export_game(root / "Game.pyz", scene)
        try:
            external = _copy_runtime(root)
            _validate_interpreter(root)
        except (subprocess.SubprocessError, importlib.metadata.PackageNotFoundError) as error:
            raise ValueError(f"Cannot prepare the native runtime: {error}") from error
        (root / "play").write_text(LAUNCHER, encoding="utf-8")
        (root / "play").chmod(0o755)
        (root / "launch.py").write_text(BOOTSTRAP, encoding="utf-8")
        (root / "README.txt").write_text(README, encoding="utf-8")
        inventory = {}
        for item in sorted(root.rglob("*")):
            if item.is_file():
                with item.open("rb") as handle:
                    digest = hashlib.file_digest(handle, "sha256").hexdigest()
                inventory[str(item.relative_to(root))] = {
                    "bytes": item.stat().st_size,
                    "sha256": digest,
                }
        (root / "bundle.json").write_text(
            json.dumps(
                {
                    "format_version": 1,
                    "platform": "Linux",
                    "machine": platform.machine(),
                    "python": platform.python_version(),
                    "qt": "6.11.2",
                    "external_qt_libraries": external,
                    "files": inventory,
                    "redistribution_ready": False,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        archive = staging / "game.tar.gz"
        with tarfile.open(archive, "w:gz", compresslevel=1) as handle:
            handle.add(root, arcname="Game", filter=_archive_metadata)
        with archive.open("rb") as handle:
            os.fsync(handle.fileno())
        os.chmod(archive, 0o644)
        os.link(archive, path)
        flush_directory(path.parent)
        return path.stat().st_size


def _archive_metadata(info: tarfile.TarInfo) -> tarfile.TarInfo:
    # Omit builder identity and timestamps; keep executability for the launcher/interpreter.
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    info.mtime = 0
    info.mode = 0o755 if info.isdir() or info.mode & 0o111 else 0o644
    info.pax_headers = {}
    return info
