# Bundled dependency notices

These text-only notices accompany the frozen Python 3.14.7 / PySide6 6.11.2
Linux runtime. `sources.json` records original source URLs, archive hashes and
collected notice counts. Files retain source paths and original license text;
they include a superset of notices from each component, not extra runtime code.

- `cpython.txt`: notices from CPython 3.14.7, including vendored libraries.
- `python-standalone.txt`: Python build dependency notices from upstream snapshot
  `5974083`. The interpreter's installed `LICENSE.txt` is copied separately by
  the exporter as `Python.txt`. Build variants can differ; the bundle manifest
  records actual external Python libraries rather than copying system libraries.
- `pyside.txt`: Qt for Python / Shiboken 6.11.2 notices.
- `qtbase.txt`, `qtwayland.txt`: Qt 6.11.2 module license texts, third-party
  attribution metadata and supplied copyright/license files.
- `icu.txt`: ICU 73.2 notices, matching the ICU shared libraries in this Qt wheel.

Runtime exports link dynamically to the selected Qt libraries, which remain
replaceable. Upstream source locations are retained in each bundle. No model,
editor, provider credentials, or project directory is included in dependencies.
