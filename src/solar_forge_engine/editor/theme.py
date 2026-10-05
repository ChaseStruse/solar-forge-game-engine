"""Solar Forge's native palette and lightweight workspace presentation."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPolygonF
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

STYLE = """
QWidget { background: #080a09; color: #e4f0e7; font-size: 12px; }
QMainWindow::separator { background: #000000; width: 5px; height: 5px; }
QMainWindow::separator:hover { background: #a8ee75; }
QMenuBar, QMenu, QToolBar { background: #0d120f; }
QMenuBar::item, QMenu::item { padding: 7px 12px; }
QMenuBar::item:selected, QMenu::item:selected { background: #233a20; }
QToolBar { spacing: 4px; padding: 5px; border-bottom: 1px solid #253a2b; }
QToolButton { padding: 7px 9px; border: 1px solid transparent; border-radius: 5px; }
QToolButton:hover { background: #182b1e; border-color: #659c71; }
QToolButton:checked { background: #233a20; color: #d9f68a; border-color: #83b758; }
QDockWidget::title { background: #111b14; color: #bbd6c0; padding: 10px; }
QGroupBox#inspectorGroup { border: 1px solid #2b4030; border-radius: 7px;
                         margin-top: 8px; }
QGroupBox#inspectorGroup::title { subcontrol-origin: margin; left: 12px;
                                padding: 0 5px; color: #b5ef83; font-weight: bold; }
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QTreeWidget, QListWidget,
QTextEdit, QPlainTextEdit {
    background: #030605; border: 1px solid #2b4030; border-radius: 5px; padding: 5px;
    selection-background-color: #29472a; selection-color: #f6ffd9;
}
QComboBox::drop-down { border: none; width: 22px; }
QTreeWidget::item, QListWidget::item { padding: 5px; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #172b1b; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #233a20; color: #d2f9a2; }
QHeaderView::section { background: #142219; color: #a0bfa9; padding: 7px; border: none; }
QPushButton { background: #17251a; border: 1px solid #395c42; padding: 8px 12px;
              border-radius: 5px; }
QPushButton:hover { background: #233b27; border-color: #a8ee75; }
QPushButton:pressed { background: #233a20; }
QPushButton:focus, QToolButton:focus, QLineEdit:focus, QDoubleSpinBox:focus,
QSpinBox:focus, QComboBox:focus { border: 1px solid #eed47b; }
QPushButton#primary { background: #edce65; color: #10180d; font-weight: bold;
                      border: 1px solid #f6e59d; padding: 12px 18px; }
QPushButton#primary:hover { background: #ffe89b; }
QWidget:disabled { color: #829487; }
QPushButton:disabled { background: #0d1610; border-color: #293c2e; }
QTabBar::tab { background: #0d1610; padding: 8px 16px; border-bottom: 2px solid #0d1610; }
QTabBar::tab:selected { background: #223922; color: #d9f68a; border-bottom-color: #a8ee75; }
QScrollArea, QGraphicsView { border: none; }
QScrollBar:vertical { background: #050805; width: 10px; }
QScrollBar:horizontal { background: #050805; height: 10px; }
QScrollBar::handle { background: #3e6048; border-radius: 4px; min-width: 20px; min-height: 20px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QStatusBar { background: #0d1610; color: #a9c7b0; border-top: 1px solid #304735; }
QToolTip { background: #122218; color: #f6ffd9; border: 1px solid #a8ee75; padding: 6px; }
QWidget#workspaceHeader { background: #0d1610; border-bottom: 1px solid #354d39; }
QLabel#eyebrow { color: #b5ef83; font-size: 11px; font-weight: bold; letter-spacing: 2px; }
QLabel#headline { font-size: 30px; font-weight: bold; color: #f5f9dc; }
QLabel#muted { color: #a8c6b1; }
QLabel#badge { background: #223b24; color: #c3f298; padding: 6px 10px; border-radius: 5px; }
QWidget#welcomeCard { background: #101b13; border: 1px solid #476740; border-radius: 12px; }
QWidget#welcomeCard QLabel, QWidget#workspaceHeader QLabel { background: transparent; }
QToolButton#launch { background: #edce65; color: #10180d; font-weight: bold; }
QToolButton#launch:hover { background: #ffe89b; }
QToolButton#launch:disabled { background: #18241b; color: #829487; }
"""


class ForgeMark(QWidget):
    """Small vector sun and leaves: no image dependency, timer, or animation loop."""

    def __init__(self, size: int = 42) -> None:
        super().__init__()
        self.setFixedSize(size, size)
        self.setAccessibleName("Solar Forge sun and leaves")

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self.width() / 48, self.height() / 48)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#17251a"))
        painter.drawRoundedRect(1, 1, 46, 46, 14, 14)
        painter.setBrush(QColor("#edce65"))
        painter.drawEllipse(QPointF(31, 16), 8, 8)
        painter.setBrush(QColor("#a8ee75"))
        painter.drawPolygon(
            QPolygonF([QPointF(x, y) for x, y in ((9, 19), (22, 21), (31, 32), (25, 40), (14, 35))])
        )
        painter.setBrush(QColor("#59ba91"))
        painter.drawPolygon(
            QPolygonF([QPointF(x, y) for x, y in ((38, 25), (37, 37), (27, 41), (27, 33))])
        )
        painter.end()


def label(text: str, name: str) -> QLabel:
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(True)
    return widget


class ForgeWorkspace(QWidget):
    def __init__(self, view: QWidget) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QWidget()
        header.setObjectName("workspaceHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(14, 10, 14, 10)
        row.addWidget(ForgeMark())
        identity = QVBoxLayout()
        identity.addWidget(label("SOLAR FORGE", "eyebrow"))
        self.scene_label = label("Your next little world", "muted")
        identity.addWidget(self.scene_label)
        row.addLayout(identity, 1)
        row.addWidget(label("2D GREENHOUSE", "badge"))
        layout.addWidget(header)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        welcome = QWidget()
        outer = QVBoxLayout(welcome)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addStretch()
        card = QWidget()
        card.setObjectName("welcomeCard")
        card.setMaximumWidth(580)
        content = QVBoxLayout(card)
        content.setContentsMargins(28, 28, 28, 28)
        content.setSpacing(16)
        content.addWidget(ForgeMark(64))
        content.addWidget(label("GROW A LITTLE WORLD.", "eyebrow"))
        content.addWidget(label("Make something\nworth playing.", "headline"))
        content.addWidget(
            label(
                "Start with a glowing forge, build a scene from scratch, "
                "or bring your own project. "
                "Every object is yours to shape.",
                "muted",
            )
        )
        self.showcase_button = QPushButton("Explore Ember Run  →")
        self.showcase_button.setObjectName("primary")
        content.addWidget(self.showcase_button)
        actions = QHBoxLayout()
        self.create_button = QPushButton("+ Create an object")
        self.open_button = QPushButton("Open project…")
        actions.addWidget(self.create_button)
        actions.addWidget(self.open_button)
        content.addLayout(actions)
        content.addWidget(label("BUILD  →  PLAY  →  MAKE IT YOURS", "eyebrow"))
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch()
        self.pages.addWidget(welcome)
        self.pages.addWidget(view)

    def update_scene(self, name: str, count: int, dirty: bool) -> None:
        self.scene_label.setText(f"{name} · {count} objects{' · Unsaved' if dirty else ''}")
        self.pages.setCurrentIndex(1 if count else 0)
