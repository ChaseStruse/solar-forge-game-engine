"""First editor workflow: create, inspect, undo, save and reopen a scene."""

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QModelIndex, QSignalBlocker, Qt
from PySide6.QtGui import QAction, QBrush, QCloseEvent, QColor, QKeySequence, QPen
from PySide6.QtWidgets import (
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsItem,
    QGraphicsScene,
    QGraphicsView,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QWidget,
)

from solar_forge_engine.core.commands import (
    Command,
    CreateEntity,
    DeleteEntity,
    Document,
    SetEntity,
)
from solar_forge_engine.core.scene import Entity
from solar_forge_engine.project.storage import load_scene, save_scene

STYLE = """
QMainWindow, QWidget { background: #20232a; color: #e9edf2; }
QMenuBar, QMenu, QToolBar { background: #292d36; }
QDockWidget::title { background: #292d36; padding: 8px; }
QLineEdit, QDoubleSpinBox, QTreeWidget, QTextEdit {
    background: #191c22; border: 1px solid #464d5b; border-radius: 4px; padding: 5px;
}
QPushButton { background: #343b48; border: 1px solid #596170; padding: 8px 12px; }
QPushButton:hover { border-color: #f4b544; }
QPushButton:focus, QLineEdit:focus, QDoubleSpinBox:focus { border: 2px solid #f4b544; }
QWidget:disabled { color: #9098a6; }
QTreeWidget::item:selected { background: #4c3b20; color: #ffffff; }
QStatusBar { background: #292d36; }
"""
SCENE_FILTER = "Solar Forge scene (*.forge.json)"


class EditorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.document = Document()
        self.path: Path | None = None
        self.saved_scene = self.document.scene
        self.selected_id: str | None = None
        self.resize(1280, 800)
        self.setStyleSheet(STYLE)

        self.canvas = QGraphicsScene(self)
        self.canvas.setSceneRect(-64, -64, 1152, 704)
        self.view = QGraphicsView(self.canvas)
        self.view.setBackgroundBrush(QBrush(QColor("#15181e")))
        self.view.setAccessibleName("2D scene viewport")
        self.setCentralWidget(self.view)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Scene objects")
        self.tree.setAccessibleName("Scene objects")
        self._dock("Scene", self.tree, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.tree.currentItemChanged.connect(self._tree_selected)
        self.canvas.selectionChanged.connect(self._canvas_selected)

        self.inspector = QWidget()
        form = QFormLayout(self.inspector)
        self.name_field = QLineEdit()
        self.name_field.setMaxLength(100)
        form.addRow("&Name", self.name_field)
        self.numbers: dict[str, QDoubleSpinBox] = {}
        for key, label in (("x", "X"), ("y", "Y"), ("width", "Width"), ("height", "Height")):
            field = QDoubleSpinBox()
            field.setRange(1 if key in ("width", "height") else -100_000, 100_000)
            field.setDecimals(2)
            field.setKeyboardTracking(False)
            form.addRow(f"&{label}", field)
            self.numbers[key] = field
        self.color_field = QLineEdit()
        self.color_field.setPlaceholderText("#f4b544")
        self.color_field.setMaxLength(7)
        form.addRow("&Color", self.color_field)
        self.apply_button = QPushButton("Apply changes")
        self.apply_button.clicked.connect(self.apply_inspector)
        form.addRow(self.apply_button)
        self._dock("Inspector", self.inspector, Qt.DockWidgetArea.RightDockWidgetArea)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setAcceptRichText(False)
        self.log.document().setMaximumBlockCount(100)
        self.log.setMaximumHeight(130)
        self._dock("Activity", self.log, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.log.append("Create a rectangle, edit its properties, and save your first scene.")

        toolbar = QToolBar("Scene tools")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        file_menu = self.menuBar().addMenu("&File")
        edit_menu = self.menuBar().addMenu("&Edit")
        scene_menu = self.menuBar().addMenu("&Scene")

        def action(label: str, shortcut: QKeySequence.StandardKey | str) -> QAction:
            item = QAction(label, self)
            item.setShortcut(shortcut)
            toolbar.addAction(item)
            return item

        self.new_action = action("New", QKeySequence.StandardKey.New)
        self.new_action.triggered.connect(self.new_scene)
        self.open_action = action("Open", QKeySequence.StandardKey.Open)
        self.open_action.triggered.connect(self.open_scene)
        self.save_action = action("Save", QKeySequence.StandardKey.Save)
        self.save_action.triggered.connect(self.save)
        file_menu.addActions([self.new_action, self.open_action, self.save_action])
        save_as = file_menu.addAction("Save &As…")
        save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as.triggered.connect(lambda: self.save(choose_path=True))
        toolbar.addSeparator()
        self.undo_action = action("Undo", QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.undo)
        self.redo_action = action("Redo", QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.redo)
        edit_menu.addActions([self.undo_action, self.redo_action])
        toolbar.addSeparator()
        add = action("Add rectangle", "Ctrl+Shift+A")
        add.triggered.connect(self.add_rectangle)
        self.delete_action = action("Delete object", "Ctrl+Delete")
        self.delete_action.triggered.connect(self.delete_selected)
        scene_menu.addActions([add, self.delete_action])
        fit = scene_menu.addAction("Fit scene")
        fit.setShortcut("F")
        fit.triggered.connect(self.fit_scene)
        self.refresh()

    @property
    def dirty(self) -> bool:
        return self.document.scene != self.saved_scene

    def _dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> None:
        dock = QDockWidget(title, self)
        dock.setObjectName(title)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)

    def refresh(self) -> None:
        ids = {entity.id for entity in self.document.scene.entities}
        if self.selected_id not in ids:
            self.selected_id = None
        with QSignalBlocker(self.tree), QSignalBlocker(self.canvas):
            self.tree.clear()
            self.canvas.clear()
            border = self.canvas.addRect(0, 0, 1024, 576, QPen(QColor("#596170")))
            border.setZValue(-1)
            for entity in self.document.scene.entities:
                row = QTreeWidgetItem([entity.name])
                row.setData(0, Qt.ItemDataRole.UserRole, entity.id)
                self.tree.addTopLevelItem(row)
                item = self.canvas.addRect(
                    0,
                    0,
                    entity.width,
                    entity.height,
                    QPen(QColor("#ffffff")),
                    QBrush(QColor(entity.color)),
                )
                item.setPos(entity.x, entity.y)
                item.setData(0, entity.id)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                item.setToolTip(entity.name)
                if entity.id == self.selected_id:
                    self.tree.setCurrentItem(row)
                    item.setSelected(True)
        self._update_inspector()
        self.undo_action.setEnabled(self.document.can_undo)
        self.redo_action.setEnabled(self.document.can_redo)
        title = self.path.name if self.path else "Untitled scene"
        self.setWindowTitle(f"{'* ' if self.dirty else ''}{title} — Solar Forge Game Engine")
        self.statusBar().showMessage(
            f"{len(ids)} objects · Revision {self.document.revision} · "
            f"{'Unsaved changes' if self.dirty else 'Ready'}"
        )

    def _update_inspector(self) -> None:
        self.inspector.setEnabled(self.selected_id is not None)
        self.delete_action.setEnabled(self.selected_id is not None)
        if self.selected_id is None:
            self.name_field.clear()
            self.color_field.clear()
            return
        entity = self.document.scene.entity(self.selected_id)
        self.name_field.setText(entity.name)
        self.color_field.setText(entity.color)
        for key, field in self.numbers.items():
            field.setValue(getattr(entity, key))

    def _tree_selected(self) -> None:
        row = self.tree.currentItem()
        self.selected_id = row.data(0, Qt.ItemDataRole.UserRole) if row else None
        with QSignalBlocker(self.canvas):
            for item in self.canvas.items():
                item.setSelected(item.data(0) == self.selected_id and self.selected_id is not None)
        self._update_inspector()

    def _canvas_selected(self) -> None:
        items = self.canvas.selectedItems()
        self.selected_id = str(items[0].data(0)) if items else None
        with QSignalBlocker(self.tree):
            self.tree.clearSelection()
            self.tree.setCurrentIndex(QModelIndex())
            for index in range(self.tree.topLevelItemCount()):
                row = self.tree.topLevelItem(index)
                if row is not None and row.data(0, Qt.ItemDataRole.UserRole) == self.selected_id:
                    self.tree.setCurrentItem(row)
                    break
        self._update_inspector()

    def execute(self, command: Command) -> None:
        try:
            self.document.execute(command, expected_revision=self.document.revision)
        except ValueError as error:
            self._error(str(error))
        self.refresh()

    def add_rectangle(self) -> None:
        offset = (len(self.document.scene.entities) % 8) * 24
        entity = Entity(str(uuid4()), x=100 + offset, y=100 + offset)
        self.selected_id = entity.id
        self.execute(CreateEntity(entity))

    def apply_inspector(self) -> None:
        if self.selected_id is not None:
            changes: dict[str, object] = {
                "name": self.name_field.text(),
                "color": self.color_field.text(),
                **{key: field.value() for key, field in self.numbers.items()},
            }
            self.execute(SetEntity(self.selected_id, changes))

    def delete_selected(self) -> None:
        if self.selected_id is not None:
            self.execute(DeleteEntity(self.selected_id))

    def undo(self) -> None:
        self.document.undo()
        self.refresh()

    def redo(self) -> None:
        self.document.redo()
        self.refresh()

    def fit_scene(self) -> None:
        self.view.fitInView(self.canvas.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def save(self, checked: bool = False, *, choose_path: bool = False) -> bool:
        path = self.path
        if path is None or choose_path:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Save scene",
                str(path) if path else "scene.forge.json",
                SCENE_FILTER,
            )
            if not filename:
                return False
            path = Path(filename)
        try:
            save_scene(path, self.document.scene)
        except (OSError, ValueError) as error:
            self._error(f"Could not save scene: {error}")
            return False
        self.path = path
        self.saved_scene = self.document.scene
        self.log.append(f"Saved {path.name}")
        self.refresh()
        return True

    def load(self, path: Path) -> bool:
        """Replace the current document only after the entire file validates."""
        try:
            scene = load_scene(path)
        except (OSError, ValueError) as error:
            self._error(f"Could not open scene: {error}")
            return False
        self.document = Document(scene)
        self.saved_scene = scene
        self.path = path
        self.selected_id = None
        self.refresh()
        self.fit_scene()
        self.log.append(f"Opened {path.name}")
        return True

    def open_scene(self) -> None:
        if not self._confirm_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Open scene", "", SCENE_FILTER)
        if filename:
            self.load(Path(filename))

    def new_scene(self) -> None:
        if self._confirm_discard():
            self.document = Document()
            self.saved_scene = self.document.scene
            self.path = None
            self.selected_id = None
            self.refresh()
            self.fit_scene()

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(
            self,
            "Unsaved scene",
            "Save your changes before continuing?",
            buttons.Save | buttons.Discard | buttons.Cancel,
            buttons.Save,
        )
        if answer == buttons.Save:
            return self.save()
        return answer == buttons.Discard

    def _error(self, message: str) -> None:
        self.log.append(message)
        QMessageBox.warning(self, "Scene could not be changed", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()
