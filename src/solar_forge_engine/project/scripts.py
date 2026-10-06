"""Immutable, content-addressed Python files belonging to a project."""

from pathlib import Path

from solar_forge_engine.core.script import MAX_SCRIPT_BYTES, SCRIPT_PATH, ScriptBinding
from solar_forge_engine.project.storage import atomic_write, flush_directory, read_regular_bytes


def script_path(root: Path, reference: str) -> Path:
    if not isinstance(reference, str) or SCRIPT_PATH.fullmatch(reference) is None:
        raise ValueError("Python behaviors must use a content-addressed path inside scripts/.")
    path = root / reference
    if root.is_symlink() or (root / "scripts").is_symlink() or path.is_symlink():
        raise ValueError("Python behavior paths must not use symbolic links.")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Python behavior files must stay inside the project.")
    return path


def read_source(path: Path) -> str:
    raw = read_regular_bytes(path, MAX_SCRIPT_BYTES)
    if raw is None:
        raise ValueError(f"Python behavior is missing: {path.name}")
    if len(raw) > MAX_SCRIPT_BYTES:
        raise ValueError("Python behaviors must be no larger than 64 KiB.")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Python behaviors must use UTF-8 text.") from error


def store_scripts(root: Path, bindings: tuple[ScriptBinding, ...]) -> None:
    if not bindings:
        return
    folder = root / "scripts"
    if root.is_symlink() or folder.is_symlink():
        raise ValueError("Python behavior folders must not use symbolic links.")
    folder.mkdir(exist_ok=True)
    for binding in bindings:
        path = script_path(root, binding.path)
        if path.exists():
            if read_source(path) != binding.source:
                raise ValueError(f"Existing Python behavior is damaged: {path.name}")
            continue
        try:
            atomic_write(path, binding.source.encode("utf-8"), exclusive=True)
        except FileExistsError:
            if read_source(path) != binding.source:
                raise ValueError(f"Existing Python behavior is damaged: {path.name}") from None
    flush_directory(folder)
    flush_directory(root)
