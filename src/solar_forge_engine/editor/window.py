"""First editor workflow: create, inspect, undo, save and reopen a scene."""

import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QElapsedTimer, QEventLoop, QProcess, QSignalBlocker, QSize, Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QCloseEvent, QColor, QIcon, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGraphicsScene,
    QGroupBox,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolBar,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from solar_forge_engine.core.animation import Animation
from solar_forge_engine.core.commands import (
    Command,
    CreateEntity,
    DeleteEntity,
    Document,
    MoveEntity,
    RestoreScene,
    SetCoinSound,
    SetEntity,
    SetSceneName,
    SetSceneScript,
)
from solar_forge_engine.core.scene import Entity, InputPreset, Role, Scene
from solar_forge_engine.core.showcase import ember_run
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.core.templates import coin_collector
from solar_forge_engine.editor.assistant import AssistantPanel
from solar_forge_engine.editor.audio import SoundsDialog
from solar_forge_engine.editor.catalog import AssetIndexer
from solar_forge_engine.editor.cleanup import CleanupWorker
from solar_forge_engine.editor.exporting import ExportWorker
from solar_forge_engine.editor.locks import LockPersistence
from solar_forge_engine.editor.objects import ROLE_DATA, SceneObjects
from solar_forge_engine.editor.quarantine import QuarantineDialog
from solar_forge_engine.editor.recovery import RecoveryCleaner, RecoveryWriter
from solar_forge_engine.editor.saving import SceneSaver
from solar_forge_engine.editor.scripts import ScriptDialog
from solar_forge_engine.editor.startup import StartupWriter
from solar_forge_engine.editor.theme import STYLE, ForgeWorkspace
from solar_forge_engine.editor.viewport import SceneView
from solar_forge_engine.project.images import import_png
from solar_forge_engine.project.recovery import clear_recovery, read_recovery
from solar_forge_engine.project.storage import MAX_FILE_BYTES, load_scene
from solar_forge_engine.project.workspace import (
    Project,
    create_project,
    create_scene,
    list_scenes,
    new_scene_target,
    open_project,
    read_project,
)
from solar_forge_engine.project.workspace import (
    open_scene as open_project_scene,
)
from solar_forge_engine.runtime.rendering import render_scene, sprite_pixmap
from solar_forge_engine.runtime.simulation import controlled_entity

SCENE_FILTER = "Solar Forge scene (*.forge.json)"


class EditorWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.document = Document()
        self._lock_document = self.document
        self.path: Path | None = None
        self._saved_path: Path | None = None
        self.project: Project | None = None
        self.saved_scene = self.document.scene
        self.selected_id: str | None = None
        self._recovery_job: RecoveryWriter | RecoveryCleaner | None = None
        self._recovery_cleanup: list[tuple[Project, Scene | None]] = []
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
        self.view.setBackgroundBrush(QBrush(QColor("#060a08")))
        self.view.setAccessibleName("2D scene viewport")
        self.workspace = ForgeWorkspace(self.view)
        self.workspace.showcase_button.clicked.connect(self.new_showcase)
        self.workspace.create_button.clicked.connect(self.add_rectangle)
        self.workspace.open_button.clicked.connect(self.choose_open_project)
        self.setCentralWidget(self.workspace)

        self.objects = SceneObjects()
        self.tree = self.objects.tree
        self._dock("Scene", self.objects, Qt.DockWidgetArea.LeftDockWidgetArea)
        self.objects.filter_changed.connect(lambda: self.objects.apply_filter(self.selected_id))
        self.tree.currentItemChanged.connect(self._tree_selected)
        self.canvas.selectionChanged.connect(self._canvas_selected)

        self.asset_sprites: list[Sprite] = []
        self._known_assets: set[Sprite] = set()
        self._asset_document: Document | None = None
        self._asset_index_job: AssetIndexer | None = None
        self._closing = False
        self._cleanup_job: CleanupWorker | None = None
        self._save_job: SceneSaver | None = None
        self._export_job: ExportWorker | None = None
        self._asset_bytes = 0
        asset_panel = QWidget()
        asset_layout = QVBoxLayout(asset_panel)
        self.asset_hint = QLabel("Import a PNG to build your sprite palette.")
        self.asset_hint.setWordWrap(True)
        asset_layout.addWidget(self.asset_hint)
        self.asset_search = QLineEdit()
        self.asset_search.setMaxLength(100)
        self.asset_search.setPlaceholderText("Find sprite by name or size…")
        self.asset_search.setAccessibleName("Search reusable sprites")
        self.asset_search.setClearButtonEnabled(True)
        asset_layout.addWidget(self.asset_search)
        self.asset_list = QListWidget()
        self.asset_list.setIconSize(QSize(48, 48))
        self.asset_list.setAccessibleName("Reusable scene sprites")
        asset_layout.addWidget(self.asset_list)
        self.asset_count = QLabel()
        self.asset_count.setObjectName("muted")
        self.asset_count.setWordWrap(True)
        asset_layout.addWidget(self.asset_count)
        self.add_asset_button = QPushButton("Add to scene")
        self.add_asset_button.clicked.connect(self.add_asset)
        asset_layout.addWidget(self.add_asset_button)
        self.apply_asset_button = QPushButton("Apply to selected object")
        self.apply_asset_button.clicked.connect(self.apply_asset)
        asset_layout.addWidget(self.apply_asset_button)
        self.asset_list.currentItemChanged.connect(self._update_asset_actions)
        self.asset_search.textChanged.connect(self._filter_assets)
        self.refresh_assets_button = QPushButton("Refresh project assets")
        self.refresh_assets_button.clicked.connect(self.refresh_project_assets)
        asset_layout.addWidget(self.refresh_assets_button)
        self.cleanup_assets_button = QPushButton("Review unused assets")
        self.cleanup_assets_button.clicked.connect(self.review_unused_assets)
        asset_layout.addWidget(self.cleanup_assets_button)
        self.quarantine_button = QPushButton("Browse quarantined assets")
        self.quarantine_button.clicked.connect(self.browse_quarantine)
        asset_layout.addWidget(self.quarantine_button)
        self.asset_list.itemDoubleClicked.connect(lambda item: self.add_asset())
        asset_scroll = QScrollArea()
        asset_scroll.setWidgetResizable(True)
        asset_scroll.setWidget(asset_panel)
        self._dock("Assets", asset_scroll, Qt.DockWidgetArea.LeftDockWidgetArea)

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
        self._startup_project: Project | None = None
        self._startup_job: StartupWriter | None = None
        self.startup_label = QLabel("Startup scene: no project")
        self.startup_label.setTextFormat(Qt.TextFormat.PlainText)
        self.startup_label.setWordWrap(True)
        scene_layout.insertWidget(0, self.startup_label)
        self.startup_button = QPushButton("Set selected as startup scene")
        self.startup_button.clicked.connect(self.set_selected_startup_scene)
        scene_layout.addWidget(self.startup_button)
        self.project_scene_list.currentRowChanged.connect(self._update_startup_actions)
        self.refresh_scenes_button = QPushButton("Refresh scenes")
        self.refresh_scenes_button.clicked.connect(self.refresh_project_scenes)
        scene_layout.addWidget(self.refresh_scenes_button)
        self.project_scene_list.itemDoubleClicked.connect(
            lambda item: self.open_selected_project_scene()
        )
        self._scene_root: Path | None = None
        scene_scroll = QScrollArea()
        scene_scroll.setWidgetResizable(True)
        scene_scroll.setWidget(scene_panel)
        self._dock("Project scenes", scene_scroll, Qt.DockWidgetArea.RightDockWidgetArea)

        self.inspector = QWidget()
        inspector_layout = QVBoxLayout(self.inspector)
        inspector_layout.setContentsMargins(8, 8, 8, 8)
        inspector_layout.setSpacing(12)
        forms: dict[str, QFormLayout] = {}
        for title in ("Object", "Transform", "Appearance", "Movement"):
            group = QGroupBox(title)
            group.setObjectName("inspectorGroup")
            form = QFormLayout(group)
            form.setContentsMargins(12, 24, 12, 12)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            inspector_layout.addWidget(group)
            forms[title] = form
        inspector_layout.addStretch()
        self.name_field = QLineEdit()
        self.name_field.setMaxLength(100)
        forms["Object"].addRow("&Name", self.name_field)
        self.lock_drag_check = QCheckBox("Lock viewport dragging")
        self.lock_drag_check.setToolTip(
            "Drag protection saved locally for named scenes. "
            "Inspector and assistant edits still work."
        )
        self.lock_drag_check.toggled.connect(self.set_selected_lock)
        forms["Object"].addRow(self.lock_drag_check)
        self.numbers: dict[str, QDoubleSpinBox] = {}
        for key, label in (("x", "X"), ("y", "Y"), ("width", "Width"), ("height", "Height")):
            field = QDoubleSpinBox()
            field.setRange(1 if key in ("width", "height") else -100_000, 100_000)
            field.setDecimals(2)
            field.setKeyboardTracking(False)
            forms["Transform"].addRow(f"&{label}", field)
            self.numbers[key] = field
        self.color_field = QLineEdit()
        self.color_field.setPlaceholderText("#f4b544")
        self.color_field.setMaxLength(7)
        forms["Appearance"].addRow("&Color", self.color_field)
        self.role_field = QComboBox()
        for role in Role:
            self.role_field.addItem(role.value.title(), role.value)
        forms["Object"].addRow("&Role", self.role_field)
        self.draw_order_label = QLabel()
        self.draw_order_label.setToolTip("Objects later in the list draw over earlier ones.")
        forms["Object"].addRow("Draw order", self.draw_order_label)
        self.speed_field = QDoubleSpinBox()
        self.speed_field.setRange(0, 2000)
        self.speed_field.setSuffix(" units/s")
        self.speed_field.setKeyboardTracking(False)
        self.speed_field.setToolTip(
            "Speed of this object when controlled in Play; zero disables movement."
        )
        forms["Movement"].addRow("Speed", self.speed_field)
        self.input_field = QComboBox()
        for label, preset in (
            ("WASD + arrows", InputPreset.BOTH),
            ("WASD", InputPreset.WASD),
            ("Arrows", InputPreset.ARROWS),
        ):
            self.input_field.addItem(label, preset.value)
        forms["Movement"].addRow("Keys", self.input_field)
        self.sprite_label = QLabel()
        forms["Appearance"].addRow("Sprite", self.sprite_label)
        self.animation_check = QCheckBox("Loop sprite sheet in Play")
        forms["Appearance"].addRow("Animation", self.animation_check)
        self.animation_fields: dict[str, QSpinBox] = {}
        for key, label, limit, default in (
            ("columns", "Frame columns", 256, 1),
            ("rows", "Frame rows", 256, 1),
            ("fps", "Frames/second", 60, 8),
        ):
            animation_field = QSpinBox()
            animation_field.setRange(1, limit)
            animation_field.setValue(default)
            animation_field.setKeyboardTracking(False)
            forms["Appearance"].addRow(label, animation_field)
            self.animation_fields[key] = animation_field
        self.animation_check.setToolTip(
            "Equal-sized frames in row order; the editor displays the first frame."
        )
        self.animation_check.toggled.connect(self._update_animation_fields)
        self.clear_sprite_button = QPushButton("Remove sprite")
        self.clear_sprite_button.clicked.connect(self.clear_sprite)
        forms["Appearance"].addRow(self.clear_sprite_button)
        self.apply_button = QPushButton("Apply changes")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(self.apply_inspector)
        inspector_scroll = QScrollArea()
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setWidget(self.inspector)
        inspector_panel = QWidget()
        panel_layout = QVBoxLayout(inspector_panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(inspector_scroll, 1)
        panel_layout.addWidget(self.apply_button)
        self._dock("Inspector", inspector_panel, Qt.DockWidgetArea.RightDockWidgetArea)
        inspector_fields = [
            self.name_field,
            self.lock_drag_check,
            self.role_field,
            *self.numbers.values(),
            self.color_field,
            self.animation_check,
            *self.animation_fields.values(),
            self.clear_sprite_button,
            self.speed_field,
            self.input_field,
            self.apply_button,
        ]
        for previous, following in zip(inspector_fields, inspector_fields[1:]):
            QWidget.setTabOrder(previous, following)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(100)
        self.log.setMaximumHeight(130)
        self._dock("Activity", self.log, Qt.DockWidgetArea.BottomDockWidgetArea)
        self.log.appendPlainText(
            "Create a rectangle, edit its properties, and save your first scene."
        )
        self.lock_preferences = LockPersistence(self)
        self.lock_preferences.restored.connect(self._set_viewport_locks)
        self.lock_preferences.warning.connect(self.log.appendPlainText)

        self.assistant = AssistantPanel(lambda: (self.document, self.selected_id), self.refresh)
        assistant_scroll = QScrollArea()
        assistant_scroll.setWidgetResizable(True)
        assistant_scroll.setWidget(self.assistant)
        self._dock("Assistant", assistant_scroll, Qt.DockWidgetArea.RightDockWidgetArea)
        assistant_dock = self.findChild(QDockWidget, "Assistant")
        inspector_dock = self.findChild(QDockWidget, "Inspector")
        if assistant_dock is not None and inspector_dock is not None:
            self.tabifyDockWidget(inspector_dock, assistant_dock)
            inspector_dock.raise_()

        toolbar = QToolBar("Scene tools")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        file_menu = self.menuBar().addMenu("&File")
        edit_menu = self.menuBar().addMenu("&Edit")
        scene_menu = self.menuBar().addMenu("&Scene")
        rename = scene_menu.addAction("Rename scene title…")
        rename.triggered.connect(self.rename_scene)
        self.script_action = scene_menu.addAction("Edit scene script…")
        self.script_action.setShortcut("Ctrl+Shift+E")
        self.script_action.triggered.connect(self.edit_script)
        find_object = scene_menu.addAction("Find object")
        find_object.setShortcut("Ctrl+L")
        find_object.triggered.connect(self.find_object)
        find_sprite = scene_menu.addAction("Find sprite")
        find_sprite.setShortcut("Ctrl+Alt+L")
        find_sprite.triggered.connect(self.find_sprite)
        order_menu = scene_menu.addMenu("Draw order")
        self.draw_order_actions: dict[str, QAction] = {}
        for label, direction, shortcut in (
            ("Bring forward", "forward", "Ctrl+PgUp"),
            ("Send backward", "backward", "Ctrl+PgDown"),
            ("Bring to front", "front", "Ctrl+Shift+PgUp"),
            ("Send to back", "back", "Ctrl+Shift+PgDown"),
        ):
            order_action = order_menu.addAction(label)
            order_action.setShortcut(shortcut)
            order_action.triggered.connect(
                lambda checked=False, direction=direction: self.move_selected(direction)
            )
            self.draw_order_actions[direction] = order_action
        self.lock_action = scene_menu.addAction("Lock viewport dragging")
        self.lock_action.setCheckable(True)
        self.lock_action.setShortcut("Ctrl+Shift+L")
        self.lock_action.toggled.connect(self.set_selected_lock)
        lock_decorations = scene_menu.addAction("Lock decorations against dragging")
        lock_decorations.triggered.connect(self.lock_decorations)
        self.unlock_all_action = scene_menu.addAction("Unlock all viewport dragging")
        self.unlock_all_action.triggered.connect(lambda: self._set_viewport_locks(frozenset()))

        def action(label: str, shortcut: QKeySequence.StandardKey | str) -> QAction:
            item = QAction(label, self)
            item.setShortcut(shortcut)
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
        showcase = action("Forge showcase", "Ctrl+Shift+F")
        showcase.triggered.connect(self.new_showcase)
        file_menu.addAction(showcase)
        starter = file_menu.addAction("Coin starter")
        starter.setShortcut("Ctrl+Shift+N")
        starter.triggered.connect(self.new_collector)
        save_as = file_menu.addAction("Save &As…")
        save_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        save_as.triggered.connect(lambda: self.save(choose_path=True))
        self.export_action = file_menu.addAction("Export active scene as game…")
        self.export_action.triggered.connect(self.choose_export)
        self.undo_action = action("Undo", QKeySequence.StandardKey.Undo)
        self.undo_action.triggered.connect(self.undo)
        self.redo_action = action("Redo", QKeySequence.StandardKey.Redo)
        self.redo_action.triggered.connect(self.redo)
        edit_menu.addActions([self.undo_action, self.redo_action])
        add = action("Add rectangle", "Ctrl+Shift+A")
        add.triggered.connect(self.add_rectangle)
        import_sprite = action("Import PNG", "Ctrl+Shift+I")
        import_sprite.triggered.connect(self.choose_sprite)
        scene_menu.addAction(import_sprite)
        self.sounds_action = scene_menu.addAction("Project sounds…")
        self.sounds_action.triggered.connect(self.browse_sounds)
        self.clear_sound_action = scene_menu.addAction("Remove collection sound")
        self.clear_sound_action.triggered.connect(lambda: self.execute(SetCoinSound(None)))
        self.duplicate_action = action("Duplicate object", "Ctrl+D")
        self.duplicate_action.triggered.connect(self.duplicate_selected)
        self.delete_action = action("Delete object", "Ctrl+Delete")
        self.delete_action.triggered.connect(self.delete_selected)
        scene_menu.addActions([add, self.duplicate_action, self.delete_action])
        fit = scene_menu.addAction("Fit scene")
        fit.setShortcut("F")
        fit.triggered.connect(self.fit_scene)
        toolbar.addActions([self.save_action, self.undo_action, self.redo_action])
        toolbar.addSeparator()
        toolbar.addAction(import_sprite)
        toolbar.addSeparator()
        viewport_toolbar = toolbar
        viewport_toolbar.addAction(fit)
        for label, shortcut, factor in (
            ("Zoom out", "Ctrl+-", 1 / 1.2),
            ("Zoom in", "Ctrl+=", 1.2),
        ):
            zoom = scene_menu.addAction(label)
            zoom.setShortcut(shortcut)
            zoom.triggered.connect(
                lambda checked=False, factor=factor: self.view.zoom_to(
                    self.view.transform().m11() * factor
                )
            )
        actual_size = scene_menu.addAction("100%")
        actual_size.setShortcut("Ctrl+0")
        actual_size.triggered.connect(lambda: self.view.zoom_to(1))
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(80)
        self.zoom_label.setAccessibleName("Viewport zoom")
        self.view.zoom_changed.connect(lambda scale: self.zoom_label.setText(f"{scale * 100:.1f}%"))
        viewport_toolbar.addWidget(self.zoom_label)
        self.view.setToolTip("Drag objects to move · Middle-drag to pan · Ctrl+wheel to zoom")
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
        self.grid_action = viewport_toolbar.addWidget(self.grid_field)
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
        play_button = viewport_toolbar.widgetForAction(self.play_action)
        if play_button is not None:
            play_button.setObjectName("launch")
        scene_dock = self.findChild(QDockWidget, "Scene")
        project_dock = self.findChild(QDockWidget, "Project scenes")
        if scene_dock is not None and project_dock is not None:
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, project_dock)
            self.tabifyDockWidget(scene_dock, project_dock)
            scene_dock.raise_()
        activity_dock = self.findChild(QDockWidget, "Activity")
        if activity_dock is not None:
            self.resizeDocks([activity_dock], [90], Qt.Orientation.Vertical)
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
        enabled = self.snap_action.isChecked()
        self.grid_action.setVisible(enabled)
        self.view.set_grid(enabled, self.grid_field.value())

    def _drag_started(self) -> None:
        self._drag_context = (self.document, self.document.revision)

    def _commit_drag(self, entity_id: str, x: float, y: float) -> None:
        if entity_id in self.view.locked_ids:
            self.log.appendPlainText("Drag canceled because the object is locked.")
            self.refresh()
            return
        if self._drag_context != (self.document, self.document.revision):
            self.log.appendPlainText("Drag canceled because the scene changed.")
            self.refresh()
            return
        self.execute(SetEntity(entity_id, {"x": x, "y": y}))

    def refresh(self) -> None:
        self.assistant.scene_changed()
        if self.document is not self._lock_document:
            self._lock_document = self.document
            self.view.set_locked(frozenset())
            self._drag_context = None
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
        self.export_action.setEnabled(
            bool(self.document.scene.entities) and self._export_job is None
        )
        self.sounds_action.setEnabled(self.project is not None)
        self.clear_sound_action.setEnabled(self.document.scene.coin_sound is not None)
        self.quarantine_button.setEnabled(self.project is not None and self._cleanup_job is None)
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
            for entity in self.document.scene.entities:
                row = QTreeWidgetItem([entity.name])
                row.setData(0, Qt.ItemDataRole.UserRole, entity.id)
                row.setData(0, ROLE_DATA, entity.role.value)
                self.tree.addTopLevelItem(row)
                item = items[entity.id]
                if entity.id == self.selected_id:
                    self.tree.setCurrentItem(row)
                    item.setSelected(True)
        self.lock_preferences.activate(self.document, self.path, self.view.locked_ids)
        self.objects.set_locked(self.view.locked_ids)
        self.objects.apply_filter(self.selected_id)
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
        self.workspace.update_scene(self.document.scene.name, len(ids), self.dirty)
        self.setWindowTitle(f"{'* ' if self.dirty else ''}{title} — Solar Forge Game Engine")
        self.statusBar().showMessage(
            f"{len(ids)} objects · Revision {self.document.revision} · "
            f"{'Unsaved changes' if self.dirty else 'Ready'}"
        )

    def _update_lock_controls(self) -> None:
        self.unlock_all_action.setEnabled(bool(self.view.locked_ids))
        locked = self.selected_id in self.view.locked_ids
        with QSignalBlocker(self.lock_action), QSignalBlocker(self.lock_drag_check):
            self.lock_action.setEnabled(self.selected_id is not None)
            self.lock_action.setChecked(locked)
            self.lock_drag_check.setChecked(locked)

    def _set_viewport_locks(self, ids: frozenset[str]) -> None:
        self.view.set_locked(ids)
        self.lock_preferences.update(ids)
        self._drag_context = None
        self.objects.set_locked(ids)
        self._update_lock_controls()

    def set_selected_lock(self, locked: bool) -> None:
        if self.selected_id is None:
            return
        ids = self.view.locked_ids
        self._set_viewport_locks(ids | {self.selected_id} if locked else ids - {self.selected_id})

    def lock_decorations(self) -> None:
        self._set_viewport_locks(
            self.view.locked_ids
            | {
                entity.id
                for entity in self.document.scene.entities
                if entity.role == Role.DECORATION
            }
        )
        self.log.appendPlainText(
            "Decorations locked against viewport dragging. Named scenes save locks locally."
        )

    def _update_inspector(self) -> None:
        self._update_lock_controls()
        self._update_asset_actions()
        self.inspector.setEnabled(self.selected_id is not None)
        self.apply_button.setEnabled(self.selected_id is not None)
        self.delete_action.setEnabled(self.selected_id is not None)
        self.duplicate_action.setEnabled(self.selected_id is not None)
        position = next(
            (
                index
                for index, entity in enumerate(self.document.scene.entities)
                if entity.id == self.selected_id
            ),
            None,
        )
        last = len(self.document.scene.entities) - 1
        for direction, order_action in self.draw_order_actions.items():
            order_action.setEnabled(
                position is not None
                and (position < last if direction in ("forward", "front") else position > 0)
            )
        self.draw_order_label.setText(
            f"{position + 1} / {last + 1} · back → front" if position is not None else ""
        )
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
        self.animation_check.setEnabled(entity.sprite is not None)
        self.animation_check.setChecked(entity.animation is not None)
        settings = entity.animation or Animation()
        for key, animation_field in self.animation_fields.items():
            animation_field.setValue(getattr(settings, key))
        self._update_animation_fields()
        self.role_field.setCurrentIndex(self.role_field.findData(entity.role.value))
        self.speed_field.setValue(entity.move_speed)
        self.input_field.setCurrentIndex(self.input_field.findData(entity.input_preset.value))
        self.name_field.setText(entity.name)
        self.color_field.setText(entity.color)
        for key, field in self.numbers.items():
            field.setValue(getattr(entity, key))

    def _update_animation_fields(self) -> None:
        for field in self.animation_fields.values():
            field.setEnabled(self.animation_check.isEnabled() and self.animation_check.isChecked())

    def find_object(self) -> None:
        dock = self.findChild(QDockWidget, "Scene")
        if dock is not None:
            dock.show()
            dock.raise_()
        self.objects.search.setFocus()
        self.objects.search.selectAll()

    def find_sprite(self) -> None:
        dock = self.findChild(QDockWidget, "Assets")
        if dock is not None:
            dock.show()
            dock.raise_()
        self.asset_search.setFocus()
        self.asset_search.selectAll()

    def _tree_selected(self) -> None:
        row = self.tree.currentItem()
        self.selected_id = row.data(0, Qt.ItemDataRole.UserRole) if row else None
        with QSignalBlocker(self.canvas):
            for item in self.canvas.items():
                item.setSelected(item.data(0) == self.selected_id and self.selected_id is not None)
        self.objects.apply_filter(self.selected_id)
        self._update_inspector()

    def _canvas_selected(self) -> None:
        items = self.canvas.selectedItems()
        self.selected_id = str(items[0].data(0)) if items else None
        self.objects.apply_filter(self.selected_id)
        self._update_inspector()

    def execute(self, command: Command, *, expected_revision: int | None = None) -> bool:
        try:
            self.document.execute(
                command,
                expected_revision=self.document.revision
                if expected_revision is None
                else expected_revision,
            )
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
        self.log.appendPlainText(f"Imported {path.name}")
        return True

    def _execute_bounded(self, command: Command, *, expected_revision: int | None = None) -> bool:
        try:
            candidate = command.apply(self.document.scene)
            if len(json.dumps(candidate.to_data(), indent=2).encode("utf-8")) + 1 > MAX_FILE_BYTES:
                raise ValueError("This edit would exceed the 4 MiB scene limit.")
        except ValueError as error:
            self._error(str(error))
            return False
        return self.execute(command, expected_revision=expected_revision)

    def _add_sprite_entity(self, entity: Entity) -> bool:
        if not self._execute_bounded(CreateEntity(entity)):
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
        self._filter_assets()

    def _filter_assets(self) -> None:
        query = self.asset_search.text().strip().casefold()
        visible = 0
        for index in range(self.asset_list.count()):
            row = self.asset_list.item(index)
            if row is None:
                continue
            matches = not query or query in row.text().casefold()
            row.setHidden(not matches)
            visible += matches
        chosen = self.asset_list.currentItem()
        if chosen is not None and chosen.isHidden():
            self.asset_list.clearSelection()
            self.asset_list.setCurrentRow(-1)
        total = self.asset_list.count()
        message = f"{visible} / {total} sprites"
        if total and not visible:
            message += " · No matches; clear search to see your palette."
        self.asset_count.setText(message)
        self._update_asset_actions()

    def _remember_asset(self, name: str, sprite: Sprite) -> bool:
        if sprite in self._known_assets:
            return True
        size = sprite.width * sprite.height * 4
        if len(self.asset_sprites) >= 128 or self._asset_bytes + size > MAX_FILE_BYTES:
            return False
        row = QListWidgetItem(
            QIcon(sprite_pixmap(sprite)), f"{name}\n{sprite.width} × {sprite.height} pixels"
        )
        row.setData(Qt.ItemDataRole.UserRole, len(self.asset_sprites))
        row.setToolTip(
            f"{name}\n{sprite.width} × {sprite.height} pixels\nDouble-click to add to scene."
        )
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
                    self.log.appendPlainText("Project asset palette limit reached.")
                    break
            for warning in job.warnings:
                self.log.appendPlainText(warning)
            self._refresh_assets()
            self.log.appendPlainText("Project assets refreshed from saved scenes.")
        self._asset_index_job = None
        self.refresh_assets_button.setEnabled(self.project is not None)
        self.refresh_assets_button.setText("Refresh project assets")
        job.deleteLater()
        if not self._closing and self.project is not None and self.project.root != job.project.root:
            self.refresh_project_assets()

    def rename_scene(self) -> None:
        document, revision = self.document, self.document.revision
        name, accepted = QInputDialog.getText(
            self, "Rename scene title", "Scene name", text=document.scene.name
        )
        if not accepted:
            return
        if self.document is not document:
            self._error("The scene changed. Reopen Rename before changing its title.")
            return
        self.execute(SetSceneName(name), expected_revision=revision)

    def edit_script(self) -> None:
        document, revision = self.document, self.document.revision
        dialog = ScriptDialog(document.scene, self.selected_id, self)

        def apply(source: str) -> None:
            if self.document is not document or document.revision != revision:
                dialog.status.setText(
                    "The scene changed. Copy your draft and reopen the script editor."
                )
                return
            if self._execute_bounded(SetSceneScript(source), expected_revision=revision):
                dialog.accept()

        dialog.apply_requested.connect(apply)
        dialog.exec()
        dialog.deleteLater()

    def browse_sounds(self) -> None:
        if self.project is None:
            return
        document, revision = self.document, self.document.revision
        dialog = SoundsDialog(self.project, self, coin_sound=document.scene.coin_sound)
        dialog.exec()
        if dialog.sound_changed:
            if self.document is not document:
                self._error("The scene changed. Reopen sounds before assigning a clip.")
            else:
                self._execute_bounded(
                    SetCoinSound(asdict(dialog.chosen_clip) if dialog.chosen_clip else None),
                    expected_revision=revision,
                )
        dialog.deleteLater()

    def browse_quarantine(self) -> None:
        if self.project is None or self._cleanup_job is not None:
            return
        dialog = QuarantineDialog(self.project, self)
        dialog.exec()
        if dialog.restored:
            self.log.appendPlainText("Quarantined assets restored; scene data was not changed.")
            self.refresh_project_assets()
        if dialog.purged:
            self.log.appendPlainText(
                "Quarantined assets permanently deleted; scene data unchanged."
            )
        dialog.deleteLater()

    def review_unused_assets(self) -> None:
        if self.project is None or self.dirty or self._cleanup_job is not None:
            return
        protected = self.document.retained_sprites() | self._known_assets
        job = CleanupWorker(self.project, protected)
        context = (self.document, self.document.revision)
        self._cleanup_job = job
        self.cleanup_assets_button.setEnabled(False)
        self.quarantine_button.setEnabled(False)
        job.finished.connect(lambda: self._cleanup_finished(job, context))
        job.start()

    def _cleanup_finished(self, job: CleanupWorker, context: tuple[Document, int]) -> None:
        if job is not self._cleanup_job:
            return
        self._cleanup_job = None
        self.setEnabled(True)
        job.deleteLater()
        if job.error:
            self.log.appendPlainText(f"Cleanup stopped: {job.error}")
        elif job.destination is not None:
            self.log.appendPlainText(
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
                self.log.appendPlainText("No unused managed assets found.")
        else:
            self.log.appendPlainText("Cleanup review expired because the editor state changed.")
        self.quarantine_button.setEnabled(self.project is not None and self._cleanup_job is None)
        self.cleanup_assets_button.setEnabled(
            self.project is not None and not self.dirty and self._cleanup_job is None
        )

    def _update_asset_actions(self) -> None:
        row = self.asset_list.currentItem()
        chosen = row is not None and not row.isHidden()
        self.add_asset_button.setEnabled(chosen)
        self.apply_asset_button.setEnabled(chosen and self.selected_id is not None)

    def add_asset(self) -> None:
        row = self.asset_list.currentItem()
        if row is None or row.isHidden():
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
        if row is not None and not row.isHidden() and self.selected_id is not None:
            sprite = self.asset_sprites[row.data(Qt.ItemDataRole.UserRole)]
            self._execute_bounded(
                SetEntity(
                    self.selected_id,
                    {
                        "animation": None,
                        "sprite": {
                            "width": sprite.width,
                            "height": sprite.height,
                            "pixels": sprite.pixels,
                        },
                    },
                )
            )

    def clear_sprite(self) -> None:
        if self.selected_id is not None:
            self.execute(SetEntity(self.selected_id, {"sprite": None, "animation": None}))

    def apply_inspector(self) -> None:
        if self.selected_id is not None:
            changes: dict[str, object] = {
                "name": self.name_field.text(),
                "color": self.color_field.text(),
                "role": self.role_field.currentData(),
                "move_speed": self.speed_field.value(),
                "input_preset": self.input_field.currentData(),
                "animation": {key: field.value() for key, field in self.animation_fields.items()}
                if self.animation_check.isChecked()
                else None,
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

    def move_selected(self, direction: str) -> None:
        if self.selected_id is None:
            return
        position = next(
            index
            for index, entity in enumerate(self.document.scene.entities)
            if entity.id == self.selected_id
        )
        last = len(self.document.scene.entities) - 1
        target = {
            "forward": min(last, position + 1),
            "backward": max(0, position - 1),
            "front": last,
            "back": 0,
        }[direction]
        self.execute(MoveEntity(self.selected_id, target))

    def undo(self) -> None:
        self.document.undo()
        self.refresh()

    def redo(self) -> None:
        self.document.redo()
        self.refresh()

    def fit_scene(self) -> None:
        bounds = self.canvas.sceneRect().united(self.canvas.itemsBoundingRect())
        self.view.fit_workspace(bounds)

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
        controlled_id = controlled_entity(self.document.scene, self.selected_id)
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
        self.log.appendPlainText(
            "Play started · WASD / arrows move the controlled object · Esc closes"
        )

    def _preview_finished(self, exit_code: int, status: QProcess.ExitStatus) -> None:
        detail = f" (exit {exit_code})" if exit_code and not self._stopping_preview else ""
        self.log.appendPlainText(f"Play stopped{detail}. Authored scene retained.")
        self.stop_action.setEnabled(False)
        self.play_action.setEnabled(bool(self.document.scene.entities))

    def _preview_error(self, error: QProcess.ProcessError) -> None:
        if self._stopping_preview and error == QProcess.ProcessError.Crashed:
            return
        self.log.appendPlainText(f"Preview process: {self.preview.errorString()}")
        if self.preview.state() == QProcess.ProcessState.NotRunning:
            self.stop_action.setEnabled(False)
            self.play_action.setEnabled(bool(self.document.scene.entities))

    def _preview_output(self) -> None:
        message = bytes(self.preview.readAllStandardError().data()).decode(
            "utf-8", errors="replace"
        )
        self.log.appendPlainText(message[:4000])

    def _preview_ready(self) -> None:
        message = bytes(self.preview.readAllStandardOutput().data()).decode(
            "utf-8", errors="replace"
        )
        self.log.appendPlainText(message[:4000].strip())

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

    def choose_export(self) -> None:
        filename, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export active scene as a native game",
            "Game.pyz",
            "Lightweight game (*.pyz);;Linux bundle with Python and Qt (*.tar.gz)",
        )
        if filename:
            path = Path(filename)
            extension = ".tar.gz" if "*.tar.gz" in selected_filter else ".pyz"
            if not path.suffix or path.suffix.lower() == ".pyz" and extension == ".tar.gz":
                path = path.with_suffix(extension)
            elif path.name.lower().endswith(".tar.gz") and extension == ".pyz":
                path = path.with_name(path.name[:-7] + extension)
            self.export_game_to(path)

    def export_game_to(self, path: Path) -> bool:
        if self._export_job is not None:
            return False
        if not self.document.scene.entities:
            self._error("Add an object before exporting the scene.")
            return False
        job = ExportWorker(path, self.document.scene)
        self._export_job = job
        self.export_action.setEnabled(False)
        self.log.appendPlainText(f"Exporting {job.scene.name}…")
        job.finished.connect(lambda: self._export_finished(job))
        job.start()
        return True

    def _export_finished(self, job: ExportWorker) -> None:
        self._export_job = None
        job.deleteLater()
        self.export_action.setEnabled(bool(self.document.scene.entities))
        if job.error:
            self._error(f"Could not export game: {job.error}")
        else:
            instructions = (
                "Extract the complete Game folder and run play. Python and Qt are included. "
                "Linux graphics libraries are required; see the bundled README. "
                "Redistribution notices still need review before external release."
                if job.bundled
                else "Requires Python 3.14 and PySide6-Essentials 6.11.2. "
                "Editor and Docker are not needed."
            )
            self.log.appendPlainText(
                f"Exported {job.scene.name} to {job.path.name} ({job.size} bytes). {instructions}"
            )

    def save(self, checked: bool = False, *, choose_path: bool = False) -> bool:
        if self._save_job is not None:
            return False
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
        document, snapshot = self.document, self.document.scene
        root = self.project.root if self.project is not None and not choose_path else None
        baseline = self.saved_scene if self._saved_path == path and not choose_path else None
        if root is not None:
            assert self.project is not None
            try:
                path = self.project.scene_path()
            except ValueError as error:
                self._error(f"Could not save scene: {error}")
                return False
        job = SceneSaver(path, snapshot, root, baseline)
        self._save_job = job
        enabled = self.isEnabled()
        self.setEnabled(False)
        self.log.appendPlainText(f"Saving {path.name}…")
        loop = QEventLoop(self)
        job.finished.connect(loop.quit)
        job.start()
        loop.exec()
        job.wait()
        self._save_job = None
        self.setEnabled(enabled)
        job.deleteLater()
        loop.deleteLater()
        if job.error:
            self._error(f"Could not save scene: {job.error}")
            return False
        if self.document is not document:
            self.log.appendPlainText(
                f"Saved {path.name}; the active document changed during saving."
            )
            return False
        self._clear_recovery()
        self.path = path
        self._saved_path = path
        if choose_path:
            self.project = None
        self.saved_scene = snapshot
        self.log.appendPlainText(f"Saved {path.name}")
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
        self._saved_path = path
        self.selected_id = None
        self.refresh()
        self.fit_scene()
        self.log.appendPlainText(f"Opened {path.name}")
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
        self._saved_path = self.path
        self.saved_scene = self.document.scene
        self.refresh()
        self.refresh_project_assets()
        self.log.appendPlainText(f"Created project {project.name} from the current applied scene.")
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
            self.log.appendPlainText(f"Recovery snapshot unavailable: {error}")
        choice = self._choose_recovery() if recovered is not None else "keep"
        if choice == "discard":
            try:
                clear_recovery(project)
            except (OSError, ValueError) as error:
                self.log.appendPlainText(f"Could not discard recovery: {error}")
        self._close_preview()
        self.document = Document(scene)
        self.project = project
        self.path = project.scene_path()
        self._saved_path = self.path
        self.saved_scene = scene
        self.selected_id = None
        self.refresh()
        self.fit_scene()
        self.refresh_project_scenes()
        self.refresh_project_assets()
        self.log.appendPlainText(f"Opened {project.name} / {scene.name}")
        if choice == "recover" and recovered is not None:
            self.execute(RestoreScene(recovered))
            self.log.appendPlainText(
                "Recovered edits. Save to keep them; Undo restores the saved scene."
            )

    def _update_startup_actions(self) -> None:
        row = self.project_scene_list.currentItem()
        self.startup_button.setEnabled(
            self.project is not None
            and self._startup_project is not None
            and self._startup_job is None
            and row is not None
            and row.data(Qt.ItemDataRole.UserRole) != self._startup_project.scene
        )

    def set_selected_startup_scene(self) -> None:
        row = self.project_scene_list.currentItem()
        if (
            self.project is None
            or self._startup_project is None
            or row is None
            or self._startup_job is not None
        ):
            return
        job = StartupWriter(self.project, row.data(Qt.ItemDataRole.UserRole), self._startup_project)
        self._startup_job = job
        self.setEnabled(False)
        self.startup_label.setText("Validating startup scene…")
        job.finished.connect(lambda: self._startup_finished(job))
        job.start()

    def _startup_finished(self, job: StartupWriter) -> None:
        self._startup_job = None
        self.setEnabled(True)
        job.deleteLater()
        if job.error:
            self.log.appendPlainText(f"Startup scene unchanged: {job.error}")
        else:
            self.log.appendPlainText(
                f"Startup scene set to {job.reference}; active scene unchanged."
            )
        self.refresh_project_scenes()

    def refresh_project_scenes(self) -> None:
        self._startup_project = None
        self.startup_label.setText("Startup scene: no project")
        self.project_scene_list.clear()
        if self.project is None:
            return
        try:
            references = list_scenes(self.project)
            self._startup_project = read_project(self.project.root)
            self.startup_label.setText(f"Startup scene: {Path(self._startup_project.scene).name}")
        except (OSError, ValueError) as error:
            self.startup_label.setText(
                "Startup scene unavailable; refresh after fixing project settings."
            )
            self._update_startup_actions()
            self.log.appendPlainText(f"Scene browser unavailable: {error}")
            return
        for reference in references:
            row = QListWidgetItem(Path(reference).name.removesuffix(".forge.json"))
            row.setData(Qt.ItemDataRole.UserRole, reference)
            row.setToolTip(reference)
            self.project_scene_list.addItem(row)
            if reference == self.project.scene:
                self.project_scene_list.setCurrentItem(row)
        self._update_startup_actions()

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
        self._open_starter(
            coin_collector(), "Collect all five coins. Gray walls are solid; the teal player moves."
        )

    def new_showcase(self) -> None:
        self._open_starter(
            ember_run(),
            "EMBER RUN · Recover twelve energy cores. "
            "WASD/arrows move the courier. Press F5 to launch.",
        )

    def _open_starter(self, scene: Scene, message: str) -> None:
        if not self._confirm_discard():
            return
        self._close_preview()
        self.document = Document(scene)
        self.saved_scene = Scene()
        self.path = None
        self.project = None
        self.selected_id = next(
            entity.id for entity in scene.entities if entity.role == Role.PLAYER
        )
        self.refresh()
        self.fit_scene()
        self.log.appendPlainText(message)

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
            self._clear_recovery(force=True)
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

    def _recovery_finished(self, job: RecoveryWriter | RecoveryCleaner) -> None:
        if job is not self._recovery_job:
            return
        if isinstance(job, RecoveryCleaner):
            if job.error:
                self.log.appendPlainText(f"Recovery retained: {job.error}")
        elif job.error:
            self.log.appendPlainText(
                f"Autosave failed: {job.error}. Manual Save is still available."
            )
        elif not job.discard:
            self.log.appendPlainText("Recovery snapshot updated.")
        self._recovery_job = None
        job.deleteLater()
        self._start_recovery_cleanup()

    def _clear_recovery(self, *, force: bool = False) -> None:
        self.recovery_timer.stop()
        if self.project is None:
            return
        if (
            isinstance(self._recovery_job, RecoveryWriter)
            and self._recovery_job.project == self.project
        ):
            self._recovery_job.discard = True
        baseline = None if force else self.saved_scene
        for index, (project, previous) in enumerate(self._recovery_cleanup):
            if project == self.project:
                self._recovery_cleanup[index] = (project, None if previous is None else baseline)
                break
        else:
            self._recovery_cleanup.append((self.project, baseline))
        self._start_recovery_cleanup()

    def _start_recovery_cleanup(self) -> None:
        if self._recovery_job is not None or not self._recovery_cleanup:
            return
        project, baseline = self._recovery_cleanup.pop(0)
        job = RecoveryCleaner(project, baseline)
        self._recovery_job = job
        job.finished.connect(lambda: self._recovery_finished(job))
        job.start()

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
        self.log.appendPlainText(message)
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Scene could not be changed")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.exec()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._export_job is not None:
            self.log.appendPlainText("Finishing native export; close again shortly.")
            event.ignore()
            return
        if self._save_job is not None:
            self.log.appendPlainText("Finishing the scene save; close again shortly.")
            event.ignore()
            return
        if self.assistant.busy:
            self.assistant.discard()
            self.log.appendPlainText("Finishing assistant request; close again shortly.")
            event.ignore()
            return
        if self._startup_job is not None:
            self.log.appendPlainText("Finishing startup scene update; close again shortly.")
            event.ignore()
            return
        if self._confirm_discard():
            if not self.lock_preferences.drain(1000):
                self.log.appendPlainText("Finishing editor lock settings; close again shortly.")
                event.ignore()
                return
            self._closing = True
            if self._cleanup_job is not None and not self._cleanup_job.wait(1000):
                self._closing = False
                self.log.appendPlainText("Finishing cleanup; close again shortly.")
                event.ignore()
                return
            if self._asset_index_job is not None:
                job_index = self._asset_index_job
                job_index.requestInterruption()
                if not job_index.wait(1000):
                    self.log.appendPlainText("Finishing asset scan; close again shortly.")
                    self._closing = False
                    event.ignore()
                    return
                self._asset_index_finished(job_index)
            recovery_deadline = QElapsedTimer()
            recovery_deadline.start()
            while self._recovery_job is not None:
                job = self._recovery_job
                remaining = max(0, 1000 - recovery_deadline.elapsed())
                if not remaining or not job.wait(remaining):
                    self.log.appendPlainText("Finishing recovery snapshot; close again shortly.")
                    self._closing = False
                    event.ignore()
                    return
                self._recovery_finished(job)
            self._close_preview()
            event.accept()
        else:
            event.ignore()
