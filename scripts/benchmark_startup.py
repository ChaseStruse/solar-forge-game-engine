"""Isolated warm-process startup to first Qt viewport paint; not compositor presentation."""

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def child(showcase: bool) -> None:
    from PySide6 import __version__ as qt_version
    from PySide6.QtCore import QEvent, QObject, QTimer
    from PySide6.QtWidgets import QApplication

    from solar_forge_engine.editor.window import EditorWindow

    started = int(os.environ["FORGE_BENCHMARK_START_NS"])
    app = QApplication([])
    app.setApplicationName("Solar Forge Game Engine")
    app.setOrganizationName("Solar Forge Studios")
    app.setStyle("Fusion")
    window = EditorWindow()
    window._confirm_discard = lambda: True
    if showcase:
        window.new_showcase()
    first_paint: int | None = None

    class PaintProbe(QObject):
        def eventFilter(self, watched: QObject, event: QEvent) -> bool:
            nonlocal first_paint
            if event.type() == QEvent.Type.Paint and first_paint is None:
                first_paint = time.perf_counter_ns()
                QTimer.singleShot(0, finish)
            return False

    def finish() -> None:
        if window.assistant.busy or window.lock_preferences.busy:
            QTimer.singleShot(10, finish)
            return
        assert first_paint is not None
        rss = next(
            line
            for line in Path("/proc/self/status").read_text().splitlines()
            if line.startswith("VmRSS:")
        )
        print(
            json.dumps(
                {
                    "first_paint_ms": (first_paint - started) / 1_000_000,
                    "rss_mib": int(rss.split()[1]) / 1024,
                    "qpa": app.platformName(),
                    "python": platform.python_version(),
                    "qt": qt_version,
                }
            ),
            flush=True,
        )
        window.close()
        app.quit()

    probe = PaintProbe(window)
    surface = window.view.viewport() if showcase else window.workspace
    surface.installEventFilter(probe)
    window.show()
    window.fit_scene()
    QTimer.singleShot(12000, app.quit)
    app.exec()
    if first_paint is None:
        raise RuntimeError("No viewport paint observed within 12 seconds.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=5, help="Fresh processes, from 1 to 10")
    parser.add_argument("--showcase", action="store_true", help="Open Ember Run before first paint")
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.samples <= 10:
        parser.error("--samples must be from 1 to 10")
    if args.child:
        child(args.showcase)
        return
    samples = []
    for _ in range(args.samples):
        with tempfile.TemporaryDirectory(prefix="forge-startup-") as directory:
            environment = dict(os.environ, XDG_CONFIG_HOME=directory)
            command = [sys.executable, str(Path(__file__).absolute()), "--child"]
            if args.showcase:
                command.append("--showcase")
            environment["FORGE_BENCHMARK_START_NS"] = str(time.perf_counter_ns())
            result = subprocess.run(
                command, env=environment, capture_output=True, text=True, timeout=15, check=True
            )
            samples.append(json.loads(result.stdout))
    times = [sample["first_paint_ms"] for sample in samples]
    print(
        json.dumps(
            {
                "fixture": "Ember Run" if args.showcase else "empty editor welcome",
                "measurement": "launch to first Qt paint; warm filesystem; isolated preferences",
                "samples": len(samples),
                "python": samples[0]["python"],
                "qt": samples[0]["qt"],
                "qpa": samples[0]["qpa"],
                "platform": platform.platform(),
                "median_ms": round(statistics.median(times), 3),
                "max_ms": round(max(times), 3),
                "median_rss_mib": round(statistics.median(s["rss_mib"] for s in samples), 3),
                "first_paint_samples_ms": [round(value, 3) for value in times],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
