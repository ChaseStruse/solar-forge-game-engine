"""Native scene-source editing. Editing and applying never evaluate Python."""

import keyword
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFontDatabase,
    QKeyEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from solar_forge_engine.core.scene import Scene

EXAMPLE = """# Called once when Play starts, and again on Restart.
def on_start(game):
    game.set_speed(300)
    game.say("Collect all the coins!")


# Called before each simulation step. dt is 1/60 second.
def on_update(game, dt):
    if game.total_coins and game.collected == game.total_coins:
        game.say("All collected! Restart to play again.")
"""
API_HELP = """Scene Python API

on_start(game)
Runs once per Play/Restart.

on_update(game, dt)
Runs before each simulation step.

Read current state:
  game.player["id"]
  game.player["x"], ["y"], ["speed"]
  game.objects[object_id]
    id, name, x, y, width, height, role
  game.input["x"], ["y"]
    -1, 0 or 1 from movement keys
  game.actions["dash"] (Space)
    ["held"], ["pressed"], ["released"]
    Boolean flags. Edges occur once per
    callback; quick taps can set both.
    Repeats are ignored. Pause/focus loss
    and Restart clear input, without edges.
  game.collected, game.total_coins
  game.time (simulation seconds)

Change gameplay:
  game.set_speed(400)
  game.set_position("object-id", x, y)
  game.say("A message")

Remember values between updates:
  game.data["elapsed"] = 0
  game.data["elapsed"] += dt
Globals also persist until Restart.

math and random are already available.
print() sends output to Activity.
Use Insert selected object ID below to target
an object in game.set_position().

Positions move existing objects,
including walls and coins. Player
positions stay inside the arena.
Teleporting does not resolve overlaps.
Editing the returned dictionaries
alone does not change the game.

Limits: 32 KiB source, 256 objects,
32 commands and 4 KiB log per call.
No files, network, subprocesses,
threads, Qt or package loading.
Play requires Linux x86_64 and
libseccomp. Errors stop scripted Play.
An empty source removes the script.
"""


class PythonHighlight(QSyntaxHighlighter):
    def highlightBlock(self, text: str) -> None:
        rules = (
            (r"\b(?:" + "|".join(keyword.kwlist) + r")\b", "#d4b6ff"),
            (r"\b\d+(?:\.\d+)?\b", "#f0ce85"),
            (r""""[^"\\]*(?:\\.[^"\\]*)*"|'[^'\\]*(?:\\.[^'\\]*)*' """, "#a8ee75"),
            (r"#.*", "#8ca99a"),
        )
        for pattern, color in rules:
            style = QTextCharFormat()
            style.setForeground(QColor(color))
            for match in re.finditer(pattern.strip(), text):
                offset = len(text[: match.start()].encode("utf-16-le")) // 2
                length = len(match.group().encode("utf-16-le")) // 2
                self.setFormat(offset, length, style)


class CodeEdit(QPlainTextEdit):
    def __init__(self, source: str) -> None:
        super().__init__(source)
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.setAccessibleName("Scene Python source")
        self.highlight = PythonHighlight(self.document())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        cursor = self.textCursor()
        if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            start = self.document().findBlock(cursor.selectionStart())
            end = self.document().findBlock(max(cursor.selectionStart(), cursor.selectionEnd() - 1))
            selected = cursor.hasSelection()
            if not selected and event.key() == Qt.Key.Key_Tab:
                self.insertPlainText("    ")
                return
            cursor.setPosition(start.position())
            cursor.setPosition(end.position() + end.length() - 1, QTextCursor.MoveMode.KeepAnchor)
            lines = cursor.selectedText().split("\u2029")
            if event.key() == Qt.Key.Key_Backtab:
                lines = [line[min(4, len(line) - len(line.lstrip(" "))) :] for line in lines]
            else:
                lines = ["    " + line for line in lines]
            position = cursor.selectionStart()
            replacement = "\n".join(lines)
            cursor.insertText(replacement)
            inserted_end = cursor.position()
            if selected:
                cursor.setPosition(position)
                cursor.setPosition(inserted_end, QTextCursor.MoveMode.KeepAnchor)
            self.setTextCursor(cursor)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not cursor.hasSelection():
            prefix_cursor = QTextCursor(cursor)
            prefix_cursor.movePosition(
                QTextCursor.MoveOperation.StartOfBlock, QTextCursor.MoveMode.KeepAnchor
            )
            prefix = prefix_cursor.selectedText()
            indent = prefix[: len(prefix) - len(prefix.lstrip(" "))]
            if prefix.rstrip().endswith(":"):
                indent += "    "
            self.insertPlainText("\n" + indent)
            return
        super().keyPressEvent(event)


class ScriptDialog(QDialog):
    apply_requested = Signal(str)
    reload_requested = Signal()

    def __init__(
        self, scene: Scene, selected_id: str | None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Scene script — {scene.name} — Python")
        self.resize(1000, 650)
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Apply source, then press Play to run it. Save the scene to keep your script."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.error_hint = QLabel()
        self.error_hint.setTextFormat(Qt.TextFormat.PlainText)
        self.error_hint.setWordWrap(True)
        self.error_hint.hide()
        layout.addWidget(self.error_hint)
        splitter = QSplitter()
        self.code = CodeEdit(scene.script)
        self.code.setPlaceholderText("Write Python here, or insert the starter example below.")
        splitter.addWidget(self.code)
        help_text = QPlainTextEdit(API_HELP)
        help_text.setReadOnly(True)
        help_text.setAccessibleName("Scene script API reference")
        splitter.addWidget(help_text)
        splitter.setSizes([680, 320])
        layout.addWidget(splitter, 1)
        row = QHBoxLayout()
        example = QPushButton("Insert example")
        example.clicked.connect(lambda: self.code.setPlainText(EXAMPLE))
        self.code.textChanged.connect(
            lambda: example.setEnabled(not self.code.toPlainText().strip())
        )
        example.setEnabled(not scene.script.strip())
        row.addWidget(example)
        insert_id = QPushButton("Insert selected object ID")
        insert_id.setEnabled(selected_id is not None)
        insert_id.setToolTip(selected_id or "Select an object before opening the script editor.")
        insert_id.clicked.connect(lambda: self.code.insertPlainText(repr(selected_id)))
        row.addWidget(insert_id)
        self.line = QSpinBox()
        self.line.setRange(1, self.code.blockCount())
        self.line.setPrefix("Line ")
        self.code.blockCountChanged.connect(lambda count: self.line.setMaximum(count))
        row.addWidget(self.line)
        jump = QPushButton("Go")
        jump.clicked.connect(self.go_to_line)
        row.addWidget(jump)
        row.addStretch()
        layout.addLayout(row)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.reload_button = QPushButton("Reload applied source")
        self.reload_button.setToolTip(
            "Replace this draft with the scene's currently applied source."
        )
        self.reload_button.clicked.connect(self.reload_requested.emit)
        actions.addWidget(self.reload_button)
        actions.addStretch()
        cancel = QPushButton("Close · keep draft")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        self.apply_button = QPushButton("Apply script")
        self.apply_button.clicked.connect(
            lambda: self.apply_requested.emit(self.code.toPlainText())
        )
        actions.addWidget(self.apply_button)
        layout.addLayout(actions)
        self.code.textChanged.connect(self._validate)
        self.code.cursorPositionChanged.connect(self._validate)
        self._validate()

    def show_error(self, line: int, detail: str) -> None:
        self.error_hint.setText(detail)
        self.error_hint.show()
        self.line.setValue(max(1, line))
        self.go_to_line()

    def _validate(self) -> None:
        try:
            source = self.code.toPlainText()
            Scene(script=source)
        except ValueError as error:
            self.apply_button.setEnabled(False)
            self.status.setText(str(error))
        else:
            self.apply_button.setEnabled(True)
            cursor = self.code.textCursor()
            self.status.setText(
                f"Line {cursor.blockNumber() + 1}, column {cursor.positionInBlock() + 1} · "
                f"{len(source.encode('utf-8')):,} / 32,768 bytes · Source runs only in Play"
            )

    def go_to_line(self) -> None:
        cursor = QTextCursor(self.code.document().findBlockByNumber(self.line.value() - 1))
        self.code.setTextCursor(cursor)
        self.code.setFocus()
        self.code.centerCursor()
