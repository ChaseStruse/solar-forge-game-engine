"""First editor workflow: create, inspect, undo, save and reopen a scene."""

import json
import sys
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QModelIndex, QProcess, QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QCloseEvent, QColor, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsScene,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from solar_forge_engine.core.commands import (
    Command,
    CreateEntity,
    DeleteEntity,
    Document,
    RestoreScene,
    SetEntity,
)
from solar_forge_engine.core.scene import Entity, InputPreset, Role, Scene
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.core.templates import coin_collector
from solar_forge_engine.editor.catalog import AssetIndexer
from solar_forge_engine.editor.cleanup import CleanupWorker
from solar_forge_engine.editor.recovery import RecoveryWriter
from solar_forge_engine.editor.viewport import SceneView
from solar_forge_engine.project.assets import save_project_scene
from solar_forge_engine.project.images import import_png
from solar_forge_engine.project.recovery import clear_recovery, read_recovery
from solar_forge_engine.project.storage import MAX_FILE_BYTES, load_scene, save_scene
from solar_forge_engine.project.workspace import (
    Project,
    create_project,
    create_scene,
    list_scenes,
    new_scene_target,
    open_project,
)
from solar_forge_engine.project.workspace import (
    open_scene as open_project_scene,
)
from solar_forge_engine.runtime.rendering import render_scene, sprite_pixmap

STYLE = """
QMainWindow, QWidget { background: #20232a; color: #e9edf2; }
QMenuBar, QMenu, QToolBar { background: #292d36; }
QToolBar { spacing: 6px; padding: 6px; }
QToolButton { padding: 6px 10px; border-radius: 4px; }
QToolButton:hover { background: #4c3b20; }
QDockWidget::title { background: #292d36; padding: 8px; }
QLineEdit, QDoubleSpinBox, QTreeWidget, QListWidget, QTextEdit {
    background: #191c22; border: 1px solid #464d5b; border-radius: 4px; padding: 5px;
}
QPushButton { background: #343b48; border: 1px solid #596170; padding: 8px 12px; }
QPushButton:hover { border-color: #f4b544; }
QPushButton:focus, QLineEdit:focus, QDoubleSpinBox:focus { border: 2px solid #f4b544; }
QWidget:disabled { color: #9098a6; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #4c3b20; color: #ffffff; }
QStatusBar { background: #292d36; }
"""
SCENE_FILTER = "Solar Forge scene (*.forge.json)"


class EditorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.document = Document()
        self.path: Path | None = None
        self.project: Project | None = None
        self.saved_scene = self.document.scene
        self.selected_id: str | None = None
        self._recovery_job: RecoveryWriter | None = None
        self._recovery_key: tuple[Document, int] | None = None
        self.recovery_timer = QTimer(self)
        self.recovery_timer.setSingleShot(True)
        self.recovery_timer.setInterval(2000)
        self.recovery_timer.timeout.connect(self.autosave)
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
        self.view = SceneView()
        self.view.setScene(self.canvas)
        self._drag_context: tuple[Document, int] | None = None
        self.view.drag_started.connect(self._drag_started)
        self.view.position_committed.connect(self._commit_drag)
        self.view.setBackgroundBrush(QBrush(QColor("#15181e")))
        self.view.setAccessibleName("2D scene viewport")
        self.setCentralWidget(self.view)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Scene objects")
        self.tree.setAccessibleName("Scene objects")
        self._dock("Scene", self.tree, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.tree.currentItemChanged.connect(self._tree_selected)
        self.canvas.selectionChanged.connect(self._canvas_selected)

        self.asset_sprites: list[Sprite] = []
        self._known_assets: set[Sprite] = set()
        self._asset_document: Document | None = None
        self._asset_index_job: AssetIndexer | None = None
        self._closing = False
        self._cleanup_job: CleanupWorker | None = None
        self._asset_bytes = 0
        asset_panel = QWidget()
        asset_layout = QVBoxLayout(asset_panel)
        self.asset_hint = QLabel("Import a PNG to build your sprite palette.")
        self.asset_hint.setWordWrap(True)
        asset_layout.addWidget(self.asset_hint)
        self.asset_list = QListWidget()
        self.asset_list.setIconSize(QSize(48, 48))
        self.asset_list.setAccessibleName("Reusable scene sprites")
        asset_layout.addWidget(self.asset_list)
        self.add_asset_button = QPushButton("Add to scene")
        self.add_asset_button.clicked.connect(self.add_asset)
        asset_layout.addWidget(self.add_asset_button)
        self.apply_asset_button = QPushButton("Apply to selected object")
        self.apply_asset_button.clicked.connect(self.apply_asset)
        asset_layout.addWidget(self.apply_asset_button)
        self.asset_list.currentItemChanged.connect(self._update_asset_actions)
        self.refresh_assets_button = QPushButton("Refresh project assets")
        self.refresh_assets_button.clicked.connect(self.refresh_project_assets)
        asset_layout.addWidget(self.refresh_assets_button)
        self.cleanup_assets_button = QPushButton("Review unused assets")
        self.cleanup_assets_button.clicked.connect(self.review_unused_assets)
        asset_layout.addWidget(self.cleanup_assets_button)
        self.asset_list.itemDoubleClicked.connect(lambda item: self.add_asset())
        self._dock("Assets", asset_panel, Qt.DockWidgetArea.LeftDockWidgetArea)

        scene_panel = QWidget()
        scene_layout = QVBoxLayout(scene_panel)
        self.project_scene_list = QListWidget()
        self.project_scene_list.setAccessibleName("Project scenes")
        scene_layout.addWidget(self.project_scene_list)
        self.create_scene_button = QPushButton("New project scene")
        self.create_scene_button.clicked.connect(self.choose_new_project_scene)
        scene_layout.addWidget(self.create_scene_button)
        self.switch_scene_button = QPushButton("Open selected scene")
        self.switch_scene_button.clicked.connect(self.open_selected_project_scene)
        scene_layout.addWidget(self.switch_scene_button)
        self.refresh_scenes_button = QPushButton("Refresh scenes")
        self.refresh_scenes_button.clicked.connect(self.refresh_project_scenes)
        scene_layout.addWidget(self.refresh_scenes_button)
        self.project_scene_list.itemDoubleClicked.connect(
            lambda item: self.open_selected_project_scene()
        )
        self._scene_root: Path | None = None
        self._dock("Project scenes", scene_panel, Qt.DockWidgetArea.RightDockWidgetArea)

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
        self.speed_field = QDoubleSpinBox()
        self.speed_field.setRange(0, 2000)
        self.speed_field.setSuffix(" units/s")
        self.speed_field.setKeyboardTracking(False)
        self.speed_field.setToolTip(
            "Speed of this object when controlled in Play; zero disables movement."
        )
        form.addRow("Movement speed", self.speed_field)
        self.input_field = QComboBox()
        for label, preset in (
            ("WASD + arrows", InputPreset.BOTH),
            ("WASD", InputPreset.WASD),
            ("Arrows", InputPreset.ARROWS),
        ):
            self.input_field.addItem(label, preset.value)
        form.addRow("Movement keys", self.input_field)
        self.sprite_label = QLabel()
        form.addRow("Sprite", self.sprite_label)
        self.clear_sprite_button = QPushButton("Remove sprite")
        self.clear_sprite_button.clicked.connect(self.clear_sprite)
        form.addRow(self.clear_sprite_button)
        self.apply_button = QPushButton("Apply changes")
        self.apply_button.clicked.connect(self.apply_inspector)
        form.addRow(self.apply_button)
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setWidget(self.inspector)
        self._dock("Inspector", inspector_scroll, Qt.DockWidgetArea.RightDockWidgetArea)

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
        create_workspace = file_menu.addAction("Create project from scene…")
        create_workspace.setShortcut("Ctrl+Alt+N")
        create_workspace.triggered.connect(self.choose_project_folder)
        open_workspace = file_menu.addAction("Open project…")
        open_workspace.setShortcut("Ctrl+Alt+O")
        open_workspace.triggered.connect(self.choose_open_project)
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
        self.addToolBarBreak()
        viewport_toolbar = QToolBar("Viewport tools")
        viewport_toolbar.setMovable(False)
        self.addToolBar(viewport_toolbar)
        viewport_toolbar.addAction(fit)
        self.snap_action = scene_menu.addAction("Snap to grid")
        self.snap_action.setCheckable(True)
        self.snap_action.setShortcut("Ctrl+Shift+G")
        self.snap_action.setToolTip("Snap dragged object positions to the visible grid")
        viewport_toolbar.addAction(self.snap_action)
        self.grid_field = QSpinBox()
        self.grid_field.setRange(1, 256)
        self.grid_field.setValue(16)
        self.grid_field.setSuffix(" px")
        self.grid_field.setAccessibleName("Grid spacing")
        self.grid_field.setToolTip("Grid spacing in scene units; affects viewport dragging only")
        self.grid_field.setKeyboardTracking(False)
        viewport_toolbar.addWidget(QLabel("Grid spacing"))
        viewport_toolbar.addWidget(self.grid_field)
        self.snap_action.toggled.connect(self._update_grid)
        self.grid_field.valueChanged.connect(self._update_grid)
        self._update_grid()
        toolbar.addSeparator()
        self.play_action = action("▶ Play", "F5")
        self.play_action.setToolTip(
            "Play the Player role, or the selected object when no Player exists"
        )
        self.play_action.triggered.connect(self.play)
        self.stop_action = action("■ Stop", "Shift+F5")
        self.stop_action.triggered.connect(self.stop_preview)
        self.stop_action.setEnabled(False)
        for item in (self.play_action, self.stop_action):
            toolbar.removeAction(item)
            viewport_toolbar.addAction(item)
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

    def _update_grid(self) -> None:
        self.view.set_grid(self.snap_action.isChecked(), self.grid_field.value())

    def _drag_started(self) -> None:
        self._drag_context = (self.document, self.document.revision)

    def _commit_drag(self, entity_id: str, x: float, y: float) -> None:
        if self._drag_context != (self.document, self.document.revision):
            self.log.append("Drag canceled because the scene changed.")
            self.refresh()
            return
        self.execute(SetEntity(entity_id, {"x": x, "y": y}))

    def refresh(self) -> None:
        self.view.cancel_drag()
        key = (self.document, self.document.revision)
        if key != self._recovery_key:
            was_same_document = (
                self._recovery_key is not None and self._recovery_key[0] is self.document
            )
            self._recovery_key = key
            if self.project is not None and self.dirty:
                self.recovery_timer.start()
            else:
                self.recovery_timer.stop()
                if was_same_document and self.project is not None and not self.dirty:
                    self._clear_recovery()
        root = self.project.root if self.project else None
        if root != self._scene_root:
            self._scene_root = root
            self.refresh_project_scenes()
        self.refresh_assets_button.setEnabled(
            self.project is not None and self._asset_index_job is None
        )
        self.cleanup_assets_button.setEnabled(
            self.project is not None and not self.dirty and self._cleanup_job is None
        )
        self.create_scene_button.setEnabled(self.project is not None)
        self.switch_scene_button.setEnabled(self.project is not None)
        self.refresh_scenes_button.setEnabled(self.project is not None)
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
        self._refresh_assets()
        self._update_inspector()
        self.undo_action.setEnabled(self.document.can_undo)
        self.redo_action.setEnabled(self.document.can_redo)
        self.play_action.setEnabled(
            bool(ids) and self.preview.state() == QProcess.ProcessState.NotRunning
        )
        title = self.path.name if self.path else "Untitled scene"
        if self.project is not None:
            title = f"{self.project.name} / {title}"
        self.setWindowTitle(f"{'* ' if self.dirty else ''}{title} — Solar Forge Game Engine")
        self.statusBar().showMessage(
            f"{len(ids)} objects · Revision {self.document.revision} · "
            f"{'Unsaved changes' if self.dirty else 'Ready'}"
        )

    def _update_inspector(self) -> None:
        self._update_asset_actions()
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
        self.speed_field.setValue(entity.move_speed)
        self.input_field.setCurrentIndex(self.input_field.findData(entity.input_preset.value))
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
        except (OSError, ValueError) as error:
            self._error(f"Could not import sprite: {error}")
            return False
        if not self._add_sprite_entity(entity):
            return False
        self.log.append(f"Imported {path.name}")
        return True

    def _execute_sprite(self, command: Command) -> bool:
        try:
            candidate = command.apply(self.document.scene)
            if len(json.dumps(candidate.to_data(), indent=2).encode("utf-8")) + 1 > MAX_FILE_BYTES:
                raise ValueError("This sprite edit would exceed the 4 MiB scene limit.")
        except ValueError as error:
            self._error(str(error))
            return False
        return self.execute(command)

    def _add_sprite_entity(self, entity: Entity) -> bool:
        if not self._execute_sprite(CreateEntity(entity)):
            return False
        self.selected_id = entity.id
        self.refresh()
        return True

    def _refresh_assets(self) -> None:
        if self._asset_document is not self.document:
            self.asset_list.clear()
            self.asset_sprites.clear()
            self._known_assets.clear()
            self._asset_bytes = 0
            self._asset_document = self.document
        limited = False
        for entity in self.document.scene.entities:
            if entity.sprite is not None and not self._remember_asset(entity.name, entity.sprite):
                limited = True
        if limited:
            hint = "Palette limit reached (128 sprites / 4 MiB)."
        elif self.asset_sprites:
            hint = "Double-click to add. Sprites stay available until another scene opens."
        else:
            hint = "Import a PNG to build your sprite palette."
        self.asset_hint.setText(hint)
        self._update_asset_actions()

    def _remember_asset(self, name: str, sprite: Sprite) -> bool:
        if sprite in self._known_assets:
            return True
        size = sprite.width * sprite.height * 4
        if len(self.asset_sprites) >= 128 or self._asset_bytes + size > MAX_FILE_BYTES:
            return False
        row = QListWidgetItem(
            QIcon(sprite_pixmap(sprite)), f"{name} · {sprite.width} × {sprite.height}"
        )
        row.setData(Qt.ItemDataRole.UserRole, len(self.asset_sprites))
        row.setToolTip(name)
        self.asset_list.addItem(row)
        self.asset_sprites.append(sprite)
        self._known_assets.add(sprite)
        self._asset_bytes += size
        return True

    def refresh_project_assets(self) -> None:
        if self.project is None or self._asset_index_job is not None:
            return
        job = AssetIndexer(self.project)
        self._asset_index_job = job
        self.refresh_assets_button.setEnabled(False)
        self.refresh_assets_button.setText("Scanning assets…")
        job.finished.connect(lambda: self._asset_index_finished(job))
        job.start()

    def _asset_index_finished(self, job: AssetIndexer) -> None:
        if job is not self._asset_index_job:
            return
        if self.project is not None and self.project.root == job.project.root:
            for name, sprite in job.sprites:
                if not self._remember_asset(name, sprite):
                    self.log.append("Project asset palette limit reached.")
                    break
            for warning in job.warnings:
                self.log.append(warning)
            self._refresh_assets()
            self.log.append("Project assets refreshed from saved scenes.")
        self._asset_index_job = None
        self.refresh_assets_button.setEnabled(self.project is not None)
        self.refresh_assets_button.setText("Refresh project assets")
        job.deleteLater()
        if not self._closing and self.project is not None and self.project.root != job.project.root:
            self.refresh_project_assets()

    def review_unused_assets(self) -> None:
        if self.project is None or self.dirty or self._cleanup_job is not None:
            return
        protected = self.document.retained_sprites() | self._known_assets
        job = CleanupWorker(self.project, protected)
        context = (self.document, self.document.revision)
        self._cleanup_job = job
        self.cleanup_assets_button.setEnabled(False)
        job.finished.connect(lambda: self._cleanup_finished(job, context))
        job.start()

    def _cleanup_finished(self, job: CleanupWorker, context: tuple[Document, int]) -> None:
        if job is not self._cleanup_job:
            return
        self._cleanup_job = None
        self.setEnabled(True)
        job.deleteLater()
        if job.error:
            self.log.append(f"Cleanup stopped: {job.error}")
        elif job.destination is not None:
            self.log.append(
                f"Unused assets quarantined in {job.destination.relative_to(job.project.root)}"
            )
        elif (
            not self._closing
            and self.project == job.project
            and context == (self.document, self.document.revision)
            and job.protected == self.document.retained_sprites() | self._known_assets
        ):
            if job.plan is not None and job.plan.candidates:
                dialog = QMessageBox(self)
                dialog.setWindowTitle("Review unused assets")
                dialog.setText(
                    f"Quarantine {len(job.plan.candidates)} unused files "
                    f"({job.plan.bytes_unused} bytes)?"
                )
                dialog.setInformativeText(
                    "Files remain in .asset-quarantine for manual restoration. Nothing is deleted."
                )
                dialog.setDetailedText("\n".join(job.plan.candidates))
                dialog.setStandardButtons(
                    QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
                )
                dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
                if (
                    dialog.exec() == QMessageBox.StandardButton.Ok
                    and context == (self.document, self.document.revision)
                    and self.project == job.project
                    and job.protected == self.document.retained_sprites() | self._known_assets
                ):
                    operation = CleanupWorker(job.project, job.protected, job.plan)
                    self._cleanup_job = operation
                    operation.finished.connect(lambda: self._cleanup_finished(operation, context))
                    self.setEnabled(False)
                    operation.start()
            else:
                self.log.append("No unused managed assets found.")
        else:
            self.log.append("Cleanup review expired because the editor state changed.")
        self.cleanup_assets_button.setEnabled(
            self.project is not None and not self.dirty and self._cleanup_job is None
        )

    def _update_asset_actions(self) -> None:
        chosen = self.asset_list.currentItem() is not None
        self.add_asset_button.setEnabled(chosen)
        self.apply_asset_button.setEnabled(chosen and self.selected_id is not None)

    def add_asset(self) -> None:
        row = self.asset_list.currentItem()
        if row is None:
            return
        sprite = self.asset_sprites[row.data(Qt.ItemDataRole.UserRole)]
        offset = (len(self.document.scene.entities) % 8) * 24
        self._add_sprite_entity(
            Entity(
                str(uuid4()),
                name="Sprite",
                x=100 + offset,
                y=100 + offset,
                width=sprite.width,
                height=sprite.height,
                sprite=sprite,
            )
        )

    def apply_asset(self) -> None:
        row = self.asset_list.currentItem()
        if row is not None and self.selected_id is not None:
            sprite = self.asset_sprites[row.data(Qt.ItemDataRole.UserRole)]
            self._execute_sprite(
                SetEntity(
                    self.selected_id,
                    {
                        "sprite": {
                            "width": sprite.width,
                            "height": sprite.height,
                            "pixels": sprite.pixels,
                        }
                    },
                )
            )

    def clear_sprite(self) -> None:
        if self.selected_id is not None:
            self.execute(SetEntity(self.selected_id, {"sprite": None}))

    def apply_inspector(self) -> None:
        if self.selected_id is not None:
            changes: dict[str, object] = {
                "name": self.name_field.text(),
                "color": self.color_field.text(),
                "role": self.role_field.currentData(),
                "move_speed": self.speed_field.value(),
                "input_preset": self.input_field.currentData(),
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
            if self.project is not None and not choose_path:
                path = self.project.scene_path()
                save_project_scene(self.project.root, path, self.document.scene)
            else:
                save_scene(path, self.document.scene)
        except (OSError, ValueError) as error:
            self._error(f"Could not save scene: {error}")
            return False
        self._clear_recovery()
        self.path = path
        if choose_path:
            self.project = None
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
        self.project = None
        self._close_preview()
        self.saved_scene = scene
        self.path = path
        self.selected_id = None
        self.refresh()
        self.fit_scene()
        self.log.append(f"Opened {path.name}")
        return True

    def choose_project_folder(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self, "Create a new project folder from this scene", "My Game"
        )
        if filename:
            self.create_workspace(Path(filename))

    def create_workspace(self, root: Path) -> bool:
        try:
            project = create_project(root, self.document.scene)
        except (OSError, ValueError) as error:
            self._error(f"Could not create project: {error}")
            return False
        self.project = project
        self.path = project.scene_path()
        self.saved_scene = self.document.scene
        self.refresh()
        self.refresh_project_assets()
        self.log.append(f"Created project {project.name} from the current applied scene.")
        return True

    def choose_open_project(self) -> None:
        if not self._confirm_discard():
            return
        directory = QFileDialog.getExistingDirectory(self, "Open Solar Forge project")
        if directory:
            self.load_workspace(Path(directory))

    def load_workspace(self, root: Path) -> bool:
        try:
            project, scene = open_project(root)
        except (OSError, ValueError) as error:
            self._error(f"Could not open project: {error}")
            return False
        self._activate_project_scene(project, scene)
        return True

    def _activate_project_scene(self, project: Project, scene: Scene) -> None:
        recovered = None
        try:
            recovered = read_recovery(project, scene)
        except (OSError, ValueError) as error:
            self.log.append(f"Recovery snapshot unavailable: {error}")
        choice = self._choose_recovery() if recovered is not None else "keep"
        if choice == "discard":
            try:
                clear_recovery(project)
            except (OSError, ValueError) as error:
                self.log.append(f"Could not discard recovery: {error}")
        self._close_preview()
        self.document = Document(scene)
        self.project = project
        self.path = project.scene_path()
        self.saved_scene = scene
        self.selected_id = None
        self.refresh()
        self.fit_scene()
        self.refresh_project_scenes()
        self.refresh_project_assets()
        self.log.append(f"Opened {project.name} / {scene.name}")
        if choice == "recover" and recovered is not None:
            self.execute(RestoreScene(recovered))
            self.log.append("Recovered edits. Save to keep them; Undo restores the saved scene.")

    def refresh_project_scenes(self) -> None:
        self.project_scene_list.clear()
        if self.project is None:
            return
        try:
            references = list_scenes(self.project)
        except (OSError, ValueError) as error:
            self.log.append(f"Scene browser unavailable: {error}")
            return
        for reference in references:
            row = QListWidgetItem(Path(reference).name.removesuffix(".forge.json"))
            row.setData(Qt.ItemDataRole.UserRole, reference)
            row.setToolTip(reference)
            self.project_scene_list.addItem(row)
            if reference == self.project.scene:
                self.project_scene_list.setCurrentItem(row)

    def choose_new_project_scene(self) -> None:
        if self.project is None:
            return
        name, accepted = QInputDialog.getText(self, "New project scene", "Scene name:")
        if accepted:
            self.new_project_scene(name)

    def new_project_scene(self, name: str) -> bool:
        if self.project is None:
            return False
        try:
            new_scene_target(self.project, name)
        except (OSError, ValueError) as error:
            self._error(f"Could not create scene: {error}")
            return False
        if not self._confirm_discard():
            return False
        try:
            project, scene = create_scene(self.project, name)
        except (OSError, ValueError) as error:
            self._error(f"Could not create scene: {error}")
            return False
        self._activate_project_scene(project, scene)
        return True

    def open_selected_project_scene(self) -> None:
        row = self.project_scene_list.currentItem()
        if row is not None:
            self.switch_project_scene(row.data(Qt.ItemDataRole.UserRole))

    def switch_project_scene(self, reference: str) -> bool:
        if self.project is None:
            return False
        if reference == self.project.scene:
            return True
        try:
            project, scene = open_project_scene(self.project, reference)
        except (OSError, ValueError) as error:
            self._error(f"Could not open scene: {error}")
            return False
        if not self._confirm_discard():
            self.refresh_project_scenes()
            return False
        self._activate_project_scene(project, scene)
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
            self.project = None
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
        self.project = None
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
        if answer == buttons.Discard:
            self._clear_recovery()
            return True
        return False

    def autosave(self) -> None:
        if self.project is None or not self.dirty:
            return
        if self._recovery_job is not None:
            self.recovery_timer.start()
            return
        job = RecoveryWriter(self.project, self.document.scene, self.saved_scene)
        self._recovery_job = job
        job.finished.connect(lambda: self._recovery_finished(job))
        job.start()

    def _recovery_finished(self, job: RecoveryWriter) -> None:
        if job is not self._recovery_job:
            return
        if job.discard:
            try:
                clear_recovery(job.project)
            except (OSError, ValueError) as error:
                self.log.append(f"Could not clear recovery: {error}")
        elif job.error:
            self.log.append(f"Autosave failed: {job.error}. Manual Save is still available.")
        else:
            self.log.append("Recovery snapshot updated.")
        self._recovery_job = None
        job.deleteLater()

    def _clear_recovery(self) -> None:
        self.recovery_timer.stop()
        if self.project is None:
            return
        if self._recovery_job is not None and self._recovery_job.project == self.project:
            self._recovery_job.discard = True
        try:
            clear_recovery(self.project)
        except (OSError, ValueError) as error:
            self.log.append(f"Could not clear recovery: {error}")

    def _choose_recovery(self) -> str:
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Recover unsaved scene")
        dialog.setText("An unsaved recovery snapshot is available for this project.")
        recover = dialog.addButton("Recover edits", QMessageBox.ButtonRole.AcceptRole)
        discard = dialog.addButton("Discard snapshot", QMessageBox.ButtonRole.DestructiveRole)
        dialog.addButton("Open saved scene", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        if dialog.clickedButton() == recover:
            return "recover"
        return "discard" if dialog.clickedButton() == discard else "keep"

    def _error(self, message: str) -> None:
        self.log.append(message)
        QMessageBox.warning(self, "Scene could not be changed", message)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._confirm_discard():
            self._closing = True
            if self._cleanup_job is not None and not self._cleanup_job.wait(1000):
                self._closing = False
                self.log.append("Finishing cleanup; close again shortly.")
                event.ignore()
                return
            if self._asset_index_job is not None:
                job_index = self._asset_index_job
                job_index.requestInterruption()
                if not job_index.wait(1000):
                    self.log.append("Finishing asset scan; close again shortly.")
                    self._closing = False
                    event.ignore()
                    return
                self._asset_index_finished(job_index)
            if self._recovery_job is not None:
                job = self._recovery_job
                if not job.wait(1000):
                    self.log.append("Finishing recovery snapshot; close again shortly.")
                    self._closing = False
                    event.ignore()
                    return
                self._recovery_finished(job)
            self._close_preview()
            event.accept()
        else:
            event.ignore()
