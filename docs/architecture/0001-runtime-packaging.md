# Native runtime packaging

Status: measured direction; release bundling remains incomplete.

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

## Implementation checkpoint — October 6, 2026

The packaging probe and forthcoming bundle writer share one Qt dependency selector.
The selector inspects only trusted installed engine dependencies, never imported
project binaries. Keep the small `.pyz` option and add a separate compressed folder
bundle with an isolated, relative launcher, copied Python runtime and Widgets subset.
Build in a worker from the captured scene; publish a completed archive exclusively
so failed builds cannot replace existing exports. Do not copy development packages,
user preferences, environment files or the editor into games.

Acceptance requires relocation (including spaces in paths), execution without a
system Python/Qt or development checkout, missing-dependency diagnostics, preserved
existing targets and immutable scene snapshots. Record the actual Linux libraries
left outside the bundle. Clean Arch offscreen and native Wayland checks establish
different properties and must be reported separately. Engine license selection and
third-party redistribution notices remain release work; no license is inferred.
