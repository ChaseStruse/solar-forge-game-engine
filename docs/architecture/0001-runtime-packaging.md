# Native runtime packaging

Status: experimental Python/Qt folder bundles implemented; redistribution audit remains open.

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

The editor retains the small `.pyz` option and can now publish a `.tar.gz` folder
bundle. The shared selector inspects only trusted installed dependencies, never
project binaries. The bundle copies the interpreter, Python source standard library,
its shared library when available, and the Widgets subset. It excludes installed
packages, test packages, Tk, caches and site customizations. No project code runs.

`play` resolves its folder, chooses the bundled interpreter and Qt plugin directory,
and starts Python with `-I -S -B`. The bootstrap rejects fallback to the build
machine's Python prefix. Qt remains dynamically linked and replaceable. Bundles
retain the host CPU architecture and need system graphics libraries/fonts; this
is not a general Linux ABI or other-platform compatibility promise.

A worker builds from one immutable scene snapshot in a private staging directory.
Only a completed, flushed tar archive is published, through an exclusive hard link.
Existing targets and late competing exports are preserved. Handled failures clean
staging files. Process termination can leave a hidden staging directory; complete
power-loss cleanup is not guaranteed. `bundle.json` includes versions, hashes and
external Qt library names without recording builder filesystem paths or identity.

October 6 verification: relocation with spaces, isolated imports, read-only clean
Arch execution without installed Python/Qt, native Wayland playback, hashes,
existing/late targets, failed-build cleanup and immutable editor snapshots pass.
The initial two-object host bundle was 64,128,560 compressed bytes; that observation
predates inclusion of the engine MIT notice and is not a size budget. All 286 tests
pass locally (16.59 s) and in Docker (17.64 s), plus Ruff, formatting and strict mypy.
The Docker interpreter and native installed interpreter both pass relocation checks.

The engine/runtime now use MIT. Exports carry its notice, installed Python license
text and Qt package metadata. A full audit of Qt/Python embedded third-party
licenses and corresponding sources remains required before external redistribution;
`redistribution_ready` remains false. Qt documents its component licenses and
third-party notices in [Qt licensing](https://doc.qt.io/qt-6/licensing.html).
Python standalone distributions may embed additional libraries; see their
[distribution guidance](https://gregoryszorc.com/docs/python-build-standalone/main/running.html).
Do not infer licenses for imported game assets. No dependency downloads occur during
export. The older probe remains useful for measuring the Qt subset separately.
