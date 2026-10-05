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
QWidget { background: #171c24; color: #e2e6ec; font-size: 12px; }
QMainWindow::separator { background: #10151c; width: 5px; height: 5px; }
QMainWindow::separator:hover { background: #ed9951; }
QMenuBar, QMenu, QToolBar { background: #202732; }
QMenuBar::item, QMenu::item { padding: 7px 12px; }
QMenuBar::item:selected, QMenu::item:selected { background: #493528; }
QToolBar { spacing: 4px; padding: 5px; border-bottom: 1px solid #303b49; }
QToolButton { padding: 7px 9px; border: 1px solid transparent; border-radius: 5px; }
QToolButton:hover { background: #35404d; border-color: #657585; }
QToolButton:checked { background: #493528; color: #ffbc78; border-color: #aa7546; }
QDockWidget::title { background: #252e3a; color: #b9c9d7; padding: 10px; }
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox, QTreeWidget, QListWidget, QTextEdit {
    background: #101720; border: 1px solid #364353; border-radius: 5px; padding: 5px;
    selection-background-color: #62402d; selection-color: #fff1db;
}
QComboBox::drop-down { border: none; width: 22px; }
QTreeWidget::item, QListWidget::item { padding: 5px; }
QTreeWidget::item:hover, QListWidget::item:hover { background: #263442; }
QTreeWidget::item:selected, QListWidget::item:selected { background: #493528; color: #ffcc93; }
QHeaderView::section { background: #202c38; color: #92a9bb; padding: 7px; border: none; }
QPushButton { background: #2c3947; border: 1px solid #4b6072; padding: 8px 12px;
              border-radius: 5px; }
QPushButton:hover { background: #394958; border-color: #ed9951; }
QPushButton:pressed { background: #493528; }
QPushButton:focus, QToolButton:focus, QLineEdit:focus, QDoubleSpinBox:focus,
QSpinBox:focus, QComboBox:focus { border: 1px solid #ffc17d; }
QPushButton#primary { background: #db8c48; color: #181c24; font-weight: bold;
                      border: 1px solid #ffbe79; padding: 12px 18px; }
QPushButton#primary:hover { background: #ffb568; }
QWidget:disabled { color: #77838f; }
QPushButton:disabled { background: #202b36; border-color: #303c49; }
QTabBar::tab { background: #202b36; padding: 8px 16px; border-bottom: 2px solid #202b36; }
QTabBar::tab:selected { background: #303a45; color: #ffbc78; border-bottom-color: #ed9951; }
QScrollArea, QGraphicsView { border: none; }
QScrollBar:vertical { background: #151c24; width: 10px; }
QScrollBar:horizontal { background: #151c24; height: 10px; }
QScrollBar::handle { background: #415364; border-radius: 4px; min-width: 20px; min-height: 20px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QStatusBar { background: #202b36; color: #a8bcca; border-top: 1px solid #344555; }
QToolTip { background: #293848; color: #fff1db; border: 1px solid #ed9951; padding: 6px; }
QWidget#workspaceHeader { background: #202b36; border-bottom: 1px solid #42515f; }
QLabel#eyebrow { color: #efad70; font-size: 11px; font-weight: bold; letter-spacing: 2px; }
QLabel#headline { font-size: 30px; font-weight: bold; color: #fff0dc; }
QLabel#muted { color: #a7bdcc; }
QLabel#badge { background: #25413e; color: #98dcc8; padding: 6px 10px; border-radius: 5px; }
QWidget#welcomeCard { background: #222d39; border: 1px solid #425365; border-radius: 12px; }
QWidget#welcomeCard QLabel, QWidget#workspaceHeader QLabel { background: transparent; }
QToolButton#launch { background: #db8c48; color: #181c24; font-weight: bold; }
QToolButton#launch:hover { background: #ffb568; }
QToolButton#launch:disabled { background: #293541; color: #77838f; }
"""


class ForgeMark(QWidget):
    """Small vector ember: no image dependency, timer, or animation loop."""

    def __init__(self, size: int = 42) -> None:
        super().__init__()
        self.setFixedSize(size, size)
        self.setAccessibleName("Solar Forge ember")

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(self.width() / 48, self.height() / 48)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#364452"))
        painter.drawRoundedRect(1, 1, 46, 46, 11, 11)
        painter.setBrush(QColor("#ed9951"))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(x, y)
                    for x, y in (
                        (12, 34),
                        (14, 24),
                        (21, 27),
                        (25, 8),
                        (36, 25),
                        (36, 34),
                        (30, 40),
                        (19, 40),
                    )
                ]
            )
        )
        painter.setBrush(QColor("#ffe0a4"))
        painter.drawPolygon(
            QPolygonF(
                [QPointF(x, y) for x, y in ((20, 34), (24, 24), (29, 31), (28, 38), (23, 38))]
            )
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
        row.addWidget(label("2D WORKSHOP", "badge"))
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
        content.addWidget(label("SMALL WORLDS. BIG SPARKS.", "eyebrow"))
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
