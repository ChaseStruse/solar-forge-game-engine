"""Offline export readiness checks; never compile or execute project Python source."""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from importlib.resources import files
from typing import TypedDict


class RuntimeCheck(TypedDict):
    name: str
    status: str
    detail: str


class RuntimeReport(TypedDict):
    format_version: int
    ready: bool
    checks: list[RuntimeCheck]


PYTHON_VERSION = "3.14"
QT_VERSION = "6.11.2"


def requirements(*, scripts: bool, audio: bool) -> dict[str, object]:
    return {
        "format_version": 1,
        "python": PYTHON_VERSION,
        "qt": QT_VERSION,
        "scripts": scripts,
        "audio": audio,
    }


def check_runtime(required: dict[str, object]) -> RuntimeReport:
    if (
        set(required) != {"format_version", "python", "qt", "scripts", "audio"}
        or type(required["format_version"]) is not int
        or required["format_version"] != 1
        or required["python"] != PYTHON_VERSION
        or required["qt"] != QT_VERSION
        or type(required["scripts"]) is not bool
        or type(required["audio"]) is not bool
    ):
        raise ValueError("Invalid game runtime requirements.")
    checks: list[RuntimeCheck] = []

    def record(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    compatible = platform.system() == "Linux" and sys.version_info[:2] == (3, 14)
    record(
        "platform",
        "ok" if compatible else "fail",
        f"{platform.system()} / Python {platform.python_version()}; requires Linux / Python 3.14.",
    )
    environment = dict(os.environ, QT_DEBUG_PLUGINS="0", QT_QPA_PLATFORMTHEME="")
    for key in ("PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_AUDIT"):
        environment.pop(key, None)
    display = environment.get("QT_QPA_PLATFORM") or (
        "wayland"
        if environment.get("WAYLAND_DISPLAY")
        else "xcb"
        if environment.get("DISPLAY")
        else ""
    )
    record(
        "display",
        "ok" if display else "fail",
        display or "No display found. Use a Wayland session, or QT_QPA_PLATFORM=offscreen for CI.",
    )
    environment["QT_QPA_PLATFORM"] = display or "offscreen"

    def probe(name: str, source: str) -> None:
        if not compatible:
            record(name, "skip", "Install the supported Linux Python environment first.")
            return
        try:
            result = subprocess.run(
                [sys.executable, "-I", "-c", source],
                env=environment,
                capture_output=True,
                text=True,
                timeout=5,
            )
            detail = (result.stdout if result.returncode == 0 else result.stderr).strip()[-2000:]
            record(
                name,
                "ok" if result.returncode == 0 else "fail",
                detail or f"Compatibility probe exited with code {result.returncode}.",
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            record(name, "fail", str(error)[:2000])

    probe(
        "qt",
        f"""import PySide6
from PySide6.QtCore import qVersion
from PySide6.QtWidgets import QApplication
if PySide6.__version__ != {QT_VERSION!r} or qVersion() != {QT_VERSION!r}:
    raise RuntimeError('Install matching PySide6-Essentials and Qt {QT_VERSION}.')
app = QApplication([])
print('Qt {QT_VERSION}: ' + app.platformName() + ' display plugin initialized.')
""",
    )
    if required["scripts"]:
        source = (
            files("solar_forge_engine.runtime").joinpath("script_security.py").read_text("utf-8")
        )
        if len(source.encode("utf-8")) > 64 * 1024:
            raise ValueError("Trusted script restriction helper exceeds its size limit.")
        probe("scripting", source + "\nprint('Landlock ABI', enforce(), 'and seccomp enforced.')\n")
    else:
        record("scripting", "skip", "This game has no Python behaviors.")
    if required["audio"]:
        available = shutil.which("pw-play") is not None
        record(
            "audio",
            "ok" if available else "warning",
            "pw-play available; playback needs a working PipeWire session."
            if available
            else "Optional audio unavailable: install pw-play. Gameplay remains available.",
        )
    return {
        "format_version": 1,
        "ready": not any(c["status"] == "fail" for c in checks),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-runtime", action="store_true", required=True)
    parser.add_argument("--json", action="store_true", help="Print a machine-readable report")
    args = parser.parse_args()
    try:
        with files("game_data").joinpath("requirements.json").open("rb") as handle:
            raw = handle.read(4097)
        if len(raw) > 4096:
            raise ValueError("Game runtime requirements exceed their size limit.")
        required = json.loads(raw)
        if not isinstance(required, dict):
            raise ValueError("Invalid game runtime requirements.")
        report = check_runtime(required)
    except (OSError, ValueError, UnicodeDecodeError, RecursionError) as error:
        print(f"Cannot check runtime: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for check in report["checks"]:
            print(f"{check['status'].upper()}: {check['name']} — {check['detail']}")
        print(
            "Runtime ready."
            if report["ready"]
            else "Runtime needs attention; game code was not run."
        )
    return 0 if report["ready"] else 1
