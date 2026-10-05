from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QMessageBox

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.workspace import create_project


def test_project_names_and_errors_render_as_literal_text_without_loading_images(qtbot, tmp_path):
    scene = Scene("<b>Literal scene name</b>")
    project = create_project(tmp_path / "Game", scene)
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.load_workspace(project.root)
    assert scene.name in editor.log.toPlainText()
    private = QImage(8, 8, QImage.Format.Format_RGB32)
    private.fill(QColor("#ff00ff"))
    path = tmp_path / "private.png"
    assert private.save(str(path))
    message = f"Cannot load <img src='{path}'>"
    results = []

    def inspect_and_close():
        dialog = QApplication.activeModalWidget()
        if not isinstance(dialog, QMessageBox):
            return
        try:
            painted = dialog.grab().toImage()
            results.append(
                any(
                    painted.pixelColor(x, y) == QColor("#ff00ff")
                    for x in range(painted.width())
                    for y in range(painted.height())
                )
            )
        finally:
            dialog.accept()

    QTimer.singleShot(0, inspect_and_close)
    editor._error(message)
    assert results == [False]
    assert message in editor.log.toPlainText()
    assert editor.document.scene == scene
    editor.close()
