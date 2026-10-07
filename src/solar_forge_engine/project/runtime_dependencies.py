"""Select installed, trusted Qt Widgets files for native Linux game bundles.

Only engine dependencies are inspected. Never pass project-supplied binaries to ldd.
"""

import importlib.util
import os
import re
import subprocess
from pathlib import Path

DEPENDENCY = re.compile(r"^\s*(\S+)\s+=>\s+(.+?)\s+\(0x[0-9a-f]+\)", re.MULTILINE)
FORBIDDEN = ("qml", "quick", "webengine", "webchannel")


def package_root(name: str) -> Path:
    spec = importlib.util.find_spec(name)
    if spec is None or spec.origin is None:
        raise ValueError(f"Required installed package is missing: {name}")
    return Path(spec.origin).resolve().parent


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
