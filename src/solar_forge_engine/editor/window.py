"""First editor workflow: create, inspect, undo, save and reopen a scene."""

import json
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QModelIndex, QProcess, QSignalBlocker, Qt
from PySide6.QtGui import QAction, QBrush, QCloseEvent, QColor, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
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
from solar_forge_engine.core.scene import Entity, Role, Scene
from solar_forge_engine.core.templates import coin_collector
from solar_forge_engine.project.images import import_png
from solar_forge_engine.project.storage import MAX_FILE_BYTES, load_scene, save_scene
from solar_forge_engine.runtime.rendering import render_scene

STYLE = """
QMainWindow, QWidget { background: #20232a; color: #e9edf2; }
QMenuBar, QMenu, QToolBar { background: #292d36; }
QToolBar { spacing: 6px; padding: 6px; }
QToolButton { padding: 6px 10px; border-radius: 4px; }
QToolButton:hover { background: #4c3b20; }
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
        self.preview = QProcess(self)
        self._stopping_preview = False
        self.preview.finished.connect(self._preview_finished)
        self.preview.errorOccurred.connect(self._preview_error)
        self.preview.readyReadStandardError.connect(self._preview_output)
        self.preview.readyReadStandardOutput.connect(self._preview_ready)
        self.preview.started.connect(self._preview_started)
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
        self.role_field = QComboBox()
        for role in Role:
            self.role_field.addItem(role.value.title(), role.value)
        form.addRow("&Role", self.role_field)
        self.sprite_label = QLabel()
        form.addRow("Sprite", self.sprite_label)
        self.clear_sprite_button = QPushButton("Remove sprite")
        self.clear_sprite_button.clicked.connect(self.clear_sprite)
        form.addRow(self.clear_sprite_button)
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
        starter = action("Coin starter", "Ctrl+Shift+N")
        starter.triggered.connect(self.new_collector)
        file_menu.addAction(starter)
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
        import_sprite = action("Import PNG", "Ctrl+Shift+I")
        import_sprite.triggered.connect(self.choose_sprite)
        scene_menu.addAction(import_sprite)
        self.duplicate_action = action("Duplicate object", "Ctrl+D")
        self.duplicate_action.triggered.connect(self.duplicate_selected)
        self.delete_action = action("Delete object", "Ctrl+Delete")
        self.delete_action.triggered.connect(self.delete_selected)
        scene_menu.addActions([add, self.duplicate_action, self.delete_action])
        fit = scene_menu.addAction("Fit scene")
        fit.setShortcut("F")
        fit.triggered.connect(self.fit_scene)
        toolbar.addSeparator()
        self.play_action = action("▶ Play", "F5")
        self.play_action.setToolTip(
            "Play the Player role, or the selected object when no Player exists"
        )
        self.play_action.triggered.connect(self.play)
        self.stop_action = action("■ Stop", "Shift+F5")
        self.stop_action.triggered.connect(self.stop_preview)
        self.stop_action.setEnabled(False)
        scene_menu.addActions([self.play_action, self.stop_action])
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
            items = render_scene(self.canvas, self.document.scene, selectable=True)
            if not items:
                welcome = self.canvas.addText(
                    "SOLAR FORGE\n\nAdd a rectangle to start your scene.\n"
                    "Select it, edit its properties, then press Play."
                )
                welcome.setDefaultTextColor(QColor("#d6bd89"))
                welcome.setPos(260, 190)
            for entity in self.document.scene.entities:
                row = QTreeWidgetItem([entity.name])
                row.setData(0, Qt.ItemDataRole.UserRole, entity.id)
                self.tree.addTopLevelItem(row)
                item = items[entity.id]
                if entity.id == self.selected_id:
                    self.tree.setCurrentItem(row)
                    item.setSelected(True)
        self._update_inspector()
        self.undo_action.setEnabled(self.document.can_undo)
        self.redo_action.setEnabled(self.document.can_redo)
        self.play_action.setEnabled(
            bool(ids) and self.preview.state() == QProcess.ProcessState.NotRunning
        )
        title = self.path.name if self.path else "Untitled scene"
        self.setWindowTitle(f"{'* ' if self.dirty else ''}{title} — Solar Forge Game Engine")
        self.statusBar().showMessage(
            f"{len(ids)} objects · Revision {self.document.revision} · "
            f"{'Unsaved changes' if self.dirty else 'Ready'}"
        )

    def _update_inspector(self) -> None:
        self.inspector.setEnabled(self.selected_id is not None)
        self.delete_action.setEnabled(self.selected_id is not None)
        self.duplicate_action.setEnabled(self.selected_id is not None)
        if self.selected_id is None:
            self.name_field.clear()
            self.color_field.clear()
            self.sprite_label.clear()
            self.clear_sprite_button.setEnabled(False)
            return
        entity = self.document.scene.entity(self.selected_id)
        self.sprite_label.setText(
            f"{entity.sprite.width} × {entity.sprite.height} pixels" if entity.sprite else "None"
        )
        self.clear_sprite_button.setEnabled(entity.sprite is not None)
        self.role_field.setCurrentIndex(self.role_field.findData(entity.role.value))
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

    def execute(self, command: Command) -> bool:
        try:
            self.document.execute(command, expected_revision=self.document.revision)
        except ValueError as error:
            self._error(str(error))
            self.refresh()
            return False
        self.refresh()
        return True

    def add_rectangle(self) -> None:
        offset = (len(self.document.scene.entities) % 8) * 24
        entity = Entity(str(uuid4()), x=100 + offset, y=100 + offset)
        self.selected_id = entity.id
        self.execute(CreateEntity(entity))

    def choose_sprite(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import PNG sprite", "", "PNG image (*.png)"
        )
        if filename:
            self.import_sprite(Path(filename))

    def import_sprite(self, path: Path) -> bool:
        """Create a portable sprite object without changing the current selection on failure."""
        try:
            sprite = import_png(path)
            entity = Entity(
                str(uuid4()),
                name=path.stem[:100] or "Sprite",
                x=100,
                y=100,
                width=sprite.width,
                height=sprite.height,
                sprite=sprite,
            )
            command = CreateEntity(entity)
            candidate = command.apply(self.document.scene)
            if len(json.dumps(candidate.to_data(), indent=2).encode("utf-8")) + 1 > MAX_FILE_BYTES:
                raise ValueError("The imported sprite would exceed the 4 MiB scene limit.")
        except (OSError, ValueError) as error:
            self._error(f"Could not import sprite: {error}")
            return False
        if not self.execute(command):
            return False
        self.selected_id = entity.id
        self.refresh()
        self.log.append(f"Imported {path.name}; sprite pixels are stored inside the scene.")
        return True

    def clear_sprite(self) -> None:
        if self.selected_id is not None:
            self.execute(SetEntity(self.selected_id, {"sprite": None}))

    def apply_inspector(self) -> None:
        if self.selected_id is not None:
            changes: dict[str, object] = {
                "name": self.name_field.text(),
                "color": self.color_field.text(),
                "role": self.role_field.currentData(),
                **{key: field.value() for key, field in self.numbers.items()},
            }
            self.execute(SetEntity(self.selected_id, changes))

    def delete_selected(self) -> None:
        if self.selected_id is not None:
            self.execute(DeleteEntity(self.selected_id))

    def duplicate_selected(self) -> None:
        if self.selected_id is None:
            return
        original = self.document.scene.entity(self.selected_id)
        duplicate = replace(
            original,
            id=str(uuid4()),
            name=f"{original.name[:95]} copy",
            x=min(original.x + 24, 100_000),
            y=min(original.y + 24, 100_000),
        )
        if self.execute(CreateEntity(duplicate)):
            self.selected_id = duplicate.id
            self.refresh()

    def undo(self) -> None:
        self.document.undo()
        self.refresh()

    def redo(self) -> None:
        self.document.redo()
        self.refresh()

    def fit_scene(self) -> None:
        self.view.fitInView(self.canvas.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def play(self) -> None:
        if (
            not self.document.scene.entities
            or self.preview.state() != QProcess.ProcessState.NotRunning
        ):
            return
        snapshot = json.dumps(self.document.scene.to_data(), allow_nan=False).encode("utf-8")
        if len(snapshot) > MAX_FILE_BYTES:
            self._error("The scene is too large to preview (4 MiB limit).")
            return
        controlled_id = self.selected_id or self.document.scene.entities[0].id
        for entity in self.document.scene.entities:
            if entity.role == Role.PLAYER:
                controlled_id = entity.id
                break
        self._stopping_preview = False
        self.preview.setProgram(sys.executable)
        self.preview.setArguments(
            ["-I", "-m", "solar_forge_engine.runtime", "--control", controlled_id]
        )
        self.preview.start()
        self.preview.write(snapshot)
        self.preview.closeWriteChannel()
        self.play_action.setEnabled(False)
        self.stop_action.setEnabled(True)

    def _preview_started(self) -> None:
        self.log.append("Play started · WASD / arrows move the controlled object · Esc closes")

    def _preview_finished(self, exit_code: int, status: QProcess.ExitStatus) -> None:
        detail = f" (exit {exit_code})" if exit_code and not self._stopping_preview else ""
        self.log.append(f"Play stopped{detail}. Authored scene retained.")
        self.stop_action.setEnabled(False)
        self.play_action.setEnabled(bool(self.document.scene.entities))

    def _preview_error(self, error: QProcess.ProcessError) -> None:
        if self._stopping_preview and error == QProcess.ProcessError.Crashed:
            return
        self.log.append(f"Preview process: {self.preview.errorString()}")
        if self.preview.state() == QProcess.ProcessState.NotRunning:
            self.stop_action.setEnabled(False)
            self.play_action.setEnabled(bool(self.document.scene.entities))

    def _preview_output(self) -> None:
        message = bytes(self.preview.readAllStandardError().data()).decode(
            "utf-8", errors="replace"
        )
        self.log.append(message[:4000])

    def _preview_ready(self) -> None:
        message = bytes(self.preview.readAllStandardOutput().data()).decode(
            "utf-8", errors="replace"
        )
        self.log.append(message[:4000].strip())

    def stop_preview(self) -> None:
        if self.preview.state() != QProcess.ProcessState.NotRunning:
            self._stopping_preview = True
            self.preview.terminate()

    def _close_preview(self) -> None:
        if self.preview.state() == QProcess.ProcessState.NotRunning:
            return
        self.stop_preview()
        if not self.preview.waitForFinished(1000):
            self.preview.kill()
            self.preview.waitForFinished(1000)

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
        self._close_preview()
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
            self._close_preview()
            self.document = Document()
            self.saved_scene = self.document.scene
            self.path = None
            self.selected_id = None
            self.refresh()
            self.fit_scene()

    def new_collector(self) -> None:
        if not self._confirm_discard():
            return
        self._close_preview()
        self.document = Document(coin_collector())
        self.saved_scene = Scene()
        self.path = None
        self.selected_id = "player"
        self.refresh()
        self.fit_scene()
        self.log.append("Collect all five coins. Gray walls are solid; the teal player moves.")

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
            self._close_preview()
            event.accept()
        else:
            event.ignore()
