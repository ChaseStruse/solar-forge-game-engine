"""Measure a bundle's normal export entry point to first Qt paint (not presentation)."""

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path


def child(root: Path) -> None:
    import runpy

    sys.path.insert(0, str(root / "game.pyz"))
    from PySide6.QtCore import QEvent, QObject, QTimer

    from solar_forge_engine.runtime import application

    started = int(os.environ["FORGE_EXPORT_START_NS"])
    first_paint: float | None = None
    script_ready: float | None = None
    original = application.PlayerWindow

    class PaintProbe(QObject):
        def eventFilter(self, watched: QObject, event: QEvent) -> bool:
            nonlocal first_paint
            if event.type() == QEvent.Type.Paint and first_paint is None:
                first_paint = (time.perf_counter_ns() - started) / 1_000_000
            return False

    class MeasuredWindow(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.probe = PaintProbe(self)
            self.view.viewport().installEventFilter(self.probe)
            self.measure_timer = QTimer(self)
            self.measure_timer.timeout.connect(self.finish_measurement)
            self.measure_timer.start(10)
            QTimer.singleShot(10000, self.close)

        def finish_measurement(self):
            nonlocal script_ready
            if self.script_host and self.script_host.failed:
                raise RuntimeError("Exported game script initialization failed.")
            if self.script_host and not self.script_host.ready:
                return
            if self.script_host and script_ready is None:
                script_ready = (time.perf_counter_ns() - started) / 1_000_000
            if first_paint is None:
                return
            self.measure_timer.stop()
            print(
                "EXPORT_BENCHMARK "
                + json.dumps(
                    {
                        "first_paint_ms": first_paint,
                        "script_ready_ms": script_ready,
                    }
                ),
                flush=True,
            )
            self.close()

    application.PlayerWindow = MeasuredWindow
    sys.argv = [str(root / "game.pyz")]
    runpy.run_path(sys.argv[0], run_name="__main__")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="Extracted Game folder")
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = args.bundle.resolve(strict=True)
    if args.child:
        child(root)
        return
    if not 1 <= args.samples <= 10:
        parser.error("Use 1–10 samples.")
    reports = []
    for _ in range(args.samples):
        environment = dict(os.environ, FORGE_EXPORT_START_NS=str(time.perf_counter_ns()))
        result = subprocess.run(
            [
                str(root / "runtime/bin/python3.14"),
                "-I",
                str(Path(__file__).resolve()),
                str(root),
                "--child",
            ],
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        lines = [
            line.removeprefix("EXPORT_BENCHMARK ")
            for line in result.stdout.splitlines()
            if line.startswith("EXPORT_BENCHMARK ")
        ]
        if len(lines) != 1:
            raise RuntimeError("The exported game did not report one first-paint measurement.")
        reports.append(json.loads(lines[0]))
    print(
        json.dumps(
            {
                "measurement": "Launch through normal game entry point to first Qt viewport paint; "
                "filesystem/bytecode caches may warm across samples; "
                "not compositor presentation or a cold-start gate.",
                "qpa": os.environ.get("QT_QPA_PLATFORM", "default"),
                "samples": reports,
                "median_first_paint_ms": round(
                    statistics.median(r["first_paint_ms"] for r in reports), 3
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
