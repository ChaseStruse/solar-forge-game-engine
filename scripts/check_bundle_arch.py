"""Opt-in clean Arch export check; build installs only native system libraries/fonts."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

IMAGE = "solar-forge-arch-export-check:dev"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Exported .tar.gz game bundle")
    parser.add_argument(
        "--wayland", action="store_true", help="Forward the current Wayland display"
    )
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    if not archive.is_file() or not archive.name.endswith(".tar.gz") or ":" in str(archive):
        parser.error("Choose a regular .tar.gz archive with no colon in its path.")
    display: Path | None = None
    if args.wayland:
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        name = os.environ.get("WAYLAND_DISPLAY")
        if not runtime or not name:
            parser.error("Run --wayland inside a Wayland desktop session.")
        display = Path(runtime) / name
        if not display.is_socket() or ":" in str(display):
            parser.error("The current Wayland socket is unavailable.")
    repository = Path(__file__).resolve().parents[1]
    try:
        subprocess.run(
            [
                "docker",
                "build",
                "-f",
                str(repository / "Dockerfile.export-check"),
                "-t",
                IMAGE,
                str(repository),
            ],
            check=True,
        )
        command = [
            "docker",
            "run",
            "--rm",
            "--init",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--volume",
            f"{archive}:/artifact/Game.tar.gz:ro",
            "--env",
            "XDG_CONFIG_HOME=/tmp/config",
            "--env",
            "XDG_CACHE_HOME=/tmp/cache",
        ]
        if display is not None:
            command += [
                "--volume",
                f"{display}:/tmp/wayland-0:ro",
                "--env",
                "QT_QPA_PLATFORM=wayland",
                "--env",
                "XDG_RUNTIME_DIR=/tmp",
                "--env",
                "WAYLAND_DISPLAY=wayland-0",
            ]
        command += [
            IMAGE,
            "sh",
            "-c",
            "test ! -e /usr/bin/python3 && "
            "test ! -d /usr/lib/python3.14/site-packages/PySide6 && "
            "tar -xzf /artifact/Game.tar.gz && "
            "./Game/Play --check-runtime --json && ./Game/Play --smoke-check",
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        print(result.stdout, end="")
        print(result.stderr, end="", file=sys.stderr)
        if result.returncode:
            return result.returncode
        readiness, end = json.JSONDecoder().raw_decode(result.stdout.lstrip())
        reports = []
        for line in result.stdout.lstrip()[end:].splitlines():
            if line.startswith("{"):
                report = json.loads(line)
                if isinstance(report, dict) and "runtime_from_archive" in report:
                    reports.append(report)
        if len(reports) != 1:
            raise ValueError("The bundle did not report one completed gameplay check.")
        report = reports[0]
        scripted = any(
            check["name"] == "scripting" and check["status"] != "skip"
            for check in readiness["checks"]
        )
        if (
            not readiness["ready"]
            or not report["runtime_from_archive"]
            or report["editor_loaded"]
            or not report["scene_unchanged"]
            or report["script_failed"]
            or (scripted and not report["scripts_ready"])
            or report["ticks"] <= 0
        ):
            raise ValueError("The bundle did not complete independent, initialized gameplay.")
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Arch bundle check failed: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
