"""Native application entry point; core imports do not initialize Qt."""

import sys

from PySide6.QtWidgets import QApplication

from solar_forge_engine.editor.window import EditorWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Solar Forge Game Engine")
    app.setOrganizationName("Solar Forge Studios")
    app.setStyle("Fusion")
    window = EditorWindow()
    window.show()
    window.fit_scene()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
