"""Select native Widgets dependencies from the trusted, frozen installation."""

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


def footprint(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def _dependency_environment() -> dict[str, str]:
    environment = dict(os.environ, LC_ALL="C")
    for key in ("LD_LIBRARY_PATH", "LD_PRELOAD", "LD_AUDIT"):
        environment.pop(key, None)
    return environment


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
    environment = _dependency_environment()

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
        try:
            result = subprocess.run(
                ["/usr/bin/ldd", str(seed)],
                capture_output=True,
                text=True,
                timeout=3,
                env=environment,
                check=True,
            )
        except subprocess.SubprocessError as error:
            raise ValueError(f"Could not inspect native dependency {seed.name}.") from error
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


def python_dependencies(
    executable: Path, standard_library: Path, base: Path
) -> tuple[dict[str, Path], list[str]]:
    """Resolve only the copied interpreter/extensions; system libraries stay external."""
    seeds = [executable, *sorted((standard_library / "lib-dynload").glob("*.so"))]
    seeds = [path for path in seeds if not path.name.startswith("_tkinter")]
    if len(seeds) > 256:
        raise ValueError("Too many Python native extensions to package.")
    try:
        result = subprocess.run(
            ["/usr/bin/ldd", *(str(path) for path in seeds)],
            capture_output=True,
            text=True,
            timeout=10,
            env=_dependency_environment(),
        )
    except subprocess.SubprocessError as error:
        raise ValueError("Could not inspect Python native dependencies.") from error
    if result.returncode or len(result.stdout) > 1024 * 1024 or "=> not found" in result.stdout:
        raise ValueError("Installed Python native dependencies could not be resolved.")
    selected: dict[str, Path] = {}
    external: set[str] = set()
    for name, filename in DEPENDENCY.findall(result.stdout):
        path = Path(filename).resolve(strict=True)
        private = path.is_relative_to(base) and (
            base not in (Path("/usr"), Path("/")) or name.startswith("libpython")
        )
        if private:
            if not path.is_relative_to(base / "lib") or "/" in name:
                raise ValueError("A Python dependency escaped its native library directory.")
            selected[name] = path
        else:
            external.add(name)
    return selected, sorted(external)
