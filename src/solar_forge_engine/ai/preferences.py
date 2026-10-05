"""Versioned user-local connection preferences; never stored in game projects."""

import json
import os
import stat
from pathlib import Path

from solar_forge_engine.ai.ollama import OllamaProvider
from solar_forge_engine.project.storage import atomic_write

MAX_PROFILE_BYTES = 4096


def profile_path() -> Path:
    root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    if not root.is_absolute():
        root = Path.home() / ".config"
    return root / "solar-forge-engine" / "assistant.json"


def read_profile(path: Path) -> OllamaProvider | None:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("Connection preferences must be a regular file.")
        raw = handle.read(MAX_PROFILE_BYTES + 1)
    if len(raw) > MAX_PROFILE_BYTES:
        raise ValueError("Connection preferences exceed 4 KiB.")
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Connection preferences are not valid JSON.") from error
    if (
        not isinstance(data, dict)
        or set(data) != {"format_version", "endpoint", "model", "timeout"}
        or type(data["format_version"]) is not int
        or data["format_version"] != 1
        or not isinstance(data["endpoint"], str)
        or len(data["endpoint"]) > 200
        or not isinstance(data["model"], str)
        or type(data["timeout"]) is not int
    ):
        raise ValueError("Connection preferences have invalid fields or version.")
    return OllamaProvider(data["endpoint"], data["model"], data["timeout"])


def save_profile(path: Path, provider: OllamaProvider) -> None:
    data = {
        "format_version": 1,
        "endpoint": provider.endpoint,
        "model": provider.model,
        "timeout": provider.timeout,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, (json.dumps(data, indent=2) + "\n").encode())
