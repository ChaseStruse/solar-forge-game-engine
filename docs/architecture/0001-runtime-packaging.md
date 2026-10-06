# Native runtime packaging

Status: bundled Linux export implemented; clean Arch userspace checks pass.
Independent hardware/kernel coverage and compositor presentation gates remain open.

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

The native export dialog preserves the small archive option and now offers a
`.tar.gz` bundle. It carries a copied Python 3.14.7 interpreter/standard library,
Qt subset, game archive, `Play` launcher, version/dependency inventory with hashes,
and upstream notices/source locations. No installed Python, Qt binding, engine,
editor, model provider or Docker is required to play. Tk/IDLE/turtle, site packages,
Python tests and bytecode caches are excluded. Standard-library links are rejected;
only interpreter and resolved native dependencies enter the runtime. System
libraries stay external, including graphics/fonts and optional PipeWire.

The exporter verifies relocation with an empty environment before publication,
then performs runtime-only dependency/restriction checks without executing authored
source. Builds run outside the Qt UI thread. Existing output files are preserved;
only a completed archive is published through the existing exclusive atomic writer.
Bundles are bounded to 256 MiB uncompressed and 4,096 files and target x86_64 glibc
Linux/Wayland. Both native and Docker interpreter layouts are exercised.

The [bundle verification record](../performance/2026-10-05-native-bundle.json)
contains size, build timing and first-paint samples. Clean Arch userspace without
installed Python or Qt bindings passes offscreen and native Wayland playback with
restricted showcase behaviors. Docker shares the host kernel; Wayland shares its
compositor. These checks do not certify unrelated hardware, an older kernel,
cold-start latency, compositor presentation, or every possible game script.

Repeat with `scripts/check_bundle_arch.py archive.tar.gz [--wayland]`. Its optional
verification image installs system libraries/fonts; routine tests remain offline
and offscreen. `scripts/benchmark_export.py extracted/Game --samples 3` measures
fresh-process startup through the normal exported entry point with a paint observer.
Filesystem/bytecode caches may warm across samples. The existing subset probe now
shares native-dependency selection with the exporter instead of duplicating rules.
