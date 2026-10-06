# Native runtime packaging

Status: measured direction with export readiness diagnostics; release bundling
and clean-Arch verification remain incomplete.

New exports contain a bounded runtime requirements manifest. Run
`python3.14 -I Game.pyz --check-runtime` (or add `--json`) to check Linux/Python,
matching Qt bindings/libraries and the selected display plugin. Scripted games
also test real Landlock/seccomp enforcement in a disposable trusted subprocess.
The checker neither loads the scene nor executes project source, and runs even
when Qt is missing. Optional audio is reported separately. Probes have deadlines;
readiness failure returns exit code 1. This is a dependency check, not a gameplay
or clean-machine release certification. Older exports need rebuilding to gain it.

The exported `.pyz` contains core/runtime Python and one scene. Native extension
modules cannot load from inside that archive; keep Python and Qt outside it.
See [Python's zipapp documentation](https://docs.python.org/3.14/library/zipapp.html)
and [Qt's Linux deployment guide](https://doc.qt.io/qt-6/linux-deployment.html).

Select the installed Qt Core, Gui and Widgets bindings, their resolved native
dependencies, and the Wayland/xdg-shell and offscreen plugins. Do not copy the
entire PySide6 package: it contains unused QML and other modules. The developer
probe rejects Quick, QML and web dependencies, uses actual file copies, and runs
an exported game in a temporary environment without an installed engine.

The [reference measurements](../performance/2026-10-05-runtime-package.json)
record an 84,303,319-byte subset of 236,514,485 installed package bytes, with
successful movement, animation and coin collection on host offscreen, host
Wayland and desktop-container Wayland. Each run uses Python 3.14.7 and Qt 6.11.2.
Subprocess duration includes a 400 ms gameplay check; it is not startup latency.
This is a single warm-cache sample per environment, not a performance gate.

Keep the current small archive option. A future bundle should carry the selected
Qt files and a compatible interpreter, preserve plugin paths, and include required
third-party notices. System graphics libraries, fonts and optional PipeWire still
need a documented clean-Arch installation contract. The probe reports external
libraries but does not prove that contract, licensing completeness, relocatable
Python, or support on a clean machine. Do not ship its temporary environment as
a release package.
