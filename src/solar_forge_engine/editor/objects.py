"""View-only object search and role filtering, independent of scene commands."""

from PySide6.QtCore import QModelIndex, QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QVBoxLayout,
    QWidget,
)

from solar_forge_engine.core.scene import Role

ROLE_DATA = int(Qt.ItemDataRole.UserRole) + 1


class SceneObjects(QWidget):
    filter_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.search = QLineEdit()
        self.search.setMaxLength(100)
        self.search.setPlaceholderText("Find object by name or ID…")
        self.search.setAccessibleName("Search scene objects")
        self.search.setClearButtonEnabled(True)
        self.role = QComboBox()
        self.role.addItem("All roles", None)
        for role in (Role.PLAYER, Role.WALL, Role.COIN, Role.DECORATION):
            self.role.addItem(role.value.capitalize(), role.value)
        self.role.setAccessibleName("Filter scene objects by role")
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Scene objects", "Drag"])
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setAccessibleName("Scene objects")
        self.tree.setUniformRowHeights(True)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setTextFormat(Qt.TextFormat.PlainText)
        for widget in (self.search, self.role, self.tree, self.hint):
            layout.addWidget(widget)
        self.search.textChanged.connect(lambda _: self.filter_changed.emit())
        self.role.currentIndexChanged.connect(lambda _: self.filter_changed.emit())

    def set_locked(self, ids: frozenset[str]) -> None:
        for index in range(self.tree.topLevelItemCount()):
            row = self.tree.topLevelItem(index)
            if row is not None:
                entity_id = row.data(0, Qt.ItemDataRole.UserRole)
                locked = entity_id in ids
                row.setText(1, "Locked" if locked else "")
                row.setToolTip(
                    0,
                    f"ID: {entity_id}\nRole: {row.data(0, ROLE_DATA)}\n"
                    f"Viewport drag: {'locked' if locked else 'enabled'}",
                )

    def apply_filter(self, selected_id: str | None) -> None:
        query = self.search.text().strip().casefold()
        role = self.role.currentData()
        total = self.tree.topLevelItemCount()
        visible = 0
        hidden_selection: str | None = None
        with QSignalBlocker(self.tree):
            self.tree.clearSelection()
            self.tree.setCurrentIndex(QModelIndex())
            for index in range(total):
                row = self.tree.topLevelItem(index)
                if row is None:
                    continue
                entity_id = row.data(0, Qt.ItemDataRole.UserRole)
                matches = (not query or query in f"{row.text(0)} {entity_id}".casefold()) and (
                    role is None or role == row.data(0, ROLE_DATA)
                )
                row.setHidden(not matches)
                if matches:
                    visible += 1
                if entity_id == selected_id:
                    if matches:
                        self.tree.setCurrentItem(row)
                    else:
                        hidden_selection = row.text(0)
        message = f"{visible} / {total} objects"
        if visible == 0 and total:
            message += " · No matches; clear search or choose All roles."
        if hidden_selection is not None:
            message += f"\nSelection outside filter: {hidden_selection}"
        self.hint.setText(message)
