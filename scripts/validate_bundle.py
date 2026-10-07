"""Build a trusted export fixture or check it in an Arch image without Python/Qt.

The check subcommand uses only the standard library, allowing CI to run it with
its host Python without installing the editor. Docker never receives its socket,
the checkout, home directory or a project mount inside the checking container.
"""

import argparse
import json
import os
import platform
import subprocess
import tarfile
import time
from pathlib import Path


def build_fixture(destination: Path) -> dict[str, object]:
    from solar_forge_engine.core.animation import Animation
    from solar_forge_engine.core.scene import Entity, Role, Scene
    from solar_forge_engine.core.sprite import Sprite
    from solar_forge_engine.project.bundling import export_bundle

    scene = Scene(
        "Portable export acceptance",
        (
            Entity(
                "player",
                role=Role.PLAYER,
                sprite=Sprite(2, 1, "UNyM//W+R/8="),
                animation=Animation(2, 1, 10),
            ),
            Entity("coin", x=64, role=Role.COIN),
        ),
        script=(
            'def on_start(game):\n    game.set_speed(360)\n    game.say("Scripted export ready")\n'
        ),
    )
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "Game.tar.gz"
    if (destination / "Game").exists() or (destination / "Moved game with spaces").exists():
        raise ValueError("Choose an empty acceptance-test directory.")
    start = time.perf_counter()
    size = export_bundle(archive, scene)
    with tarfile.open(archive) as handle:
        handle.extractall(destination, filter="data")
    root = destination / "Moved game with spaces"
    (destination / "Game").rename(root)
    manifest = json.loads((root / "bundle.json").read_text())
    return {
        "archive_bytes": size,
        "uncompressed_file_bytes": sum(item["bytes"] for item in manifest["files"].values()),
        "build_and_extract_ms": round((time.perf_counter() - start) * 1000, 3),
        "python": manifest["python"],
        "qt": manifest["qt"],
        "machine": manifest["machine"],
    }


def check_fixture(destination: Path, image: str, qpa: str) -> dict[str, object]:
    root = (destination / "Moved game with spaces").resolve(strict=True)
    command = [
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--network=none",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,size=32m",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--mount",
        f"type=bind,src={root},dst=/game,readonly",
        "--env",
        f"QT_QPA_PLATFORM={qpa}",
        "--env",
        "QT_QPA_PLATFORMTHEME=",
    ]
    if qpa == "wayland":
        runtime = Path(os.environ["XDG_RUNTIME_DIR"])
        display = Path(os.environ["WAYLAND_DISPLAY"])
        socket = display if display.is_absolute() else runtime / display
        if not socket.is_socket():
            raise ValueError("An active Wayland socket is required.")
        command += [
            "--mount",
            f"type=bind,src={socket},dst=/tmp/wayland-0,readonly",
            "--env",
            "XDG_RUNTIME_DIR=/tmp",
            "--env",
            "WAYLAND_DISPLAY=wayland-0",
        ]
    command += [
        "--entrypoint",
        "/bin/sh",
        image,
        "-ec",
        "if command -v python3 >/dev/null || command -v python >/dev/null; then "
        'echo "Unexpected system Python" >&2; exit 1; fi; '
        "for package in python pyside6 qt6-base; do "
        'if pacman -Q "$package" >/dev/null 2>&1; then '
        'echo "Unexpected installed runtime: $package" >&2; exit 1; fi; done; '
        "exec /game/play --smoke-check",
    ]
    start = time.perf_counter()
    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError(f"Clean Arch playback failed: {result.stderr[-4000:]}")
    report = json.loads(result.stdout)
    if not (
        report["runtime_from_archive"]
        and not report["editor_loaded"]
        and report["scene_unchanged"]
        and report["collected"] == 1
        and report["x"] > 0
        and report["ticks"] > 0
        and report["script_ready"]
        and not report["script_failed"]
        and report["script_message"] == "Scripted export ready"
    ):
        raise ValueError("The clean Arch game did not complete its acceptance route.")
    image_id = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    return {
        "image": image,
        "image_id": image_id,
        "qpa": qpa,
        "machine": platform.machine(),
        "container_and_smoke_ms": round((time.perf_counter() - start) * 1000, 3),
        "game": report,
        "scope": "Read-only relocated game; no installed Python/Qt or mounted editor. "
        "Includes container/script startup and movement exercise, not launch latency.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    build = subcommands.add_parser("build-fixture")
    build.add_argument("destination", type=Path)
    check = subcommands.add_parser("check")
    check.add_argument("destination", type=Path)
    check.add_argument("--image", default="solar-forge-arch-export-check:dev")
    check.add_argument("--qpa", choices=("offscreen", "wayland"), default="offscreen")
    args = parser.parse_args()
    try:
        report = (
            build_fixture(args.destination)
            if args.command == "build-fixture"
            else check_fixture(args.destination, args.image, args.qpa)
        )
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Bundle validation failed: {error}\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
