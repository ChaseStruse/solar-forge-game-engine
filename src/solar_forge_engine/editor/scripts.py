"""Native Python authoring, source snapshots and navigable Play diagnostics."""

import keyword
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QThread, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QResizeEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from solar_forge_engine.core.commands import Document, SetScript
from solar_forge_engine.core.scene import Scene
from solar_forge_engine.core.script import ScriptBinding
from solar_forge_engine.core.script_templates import TEMPLATES
from solar_forge_engine.project.scripts import read_source
from solar_forge_engine.runtime.script_protocol import ScriptFault


class PythonHighlight(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self.rules = (
            (re.compile(r"\b(?:" + "|".join(keyword.kwlist) + r")\b"), "#f3cb77"),
            (re.compile(r"\b(?:ctx|dt|True|False|None)\b"), "#77e6b6"),
            (re.compile(r"\b\d+(?:\.\d+)?\b"), "#b9a2ed"),
            (re.compile(r""""(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*' """.strip()), "#a7d58b"),
            (re.compile(r"#.*$"), "#778e84"),
        )

    def highlightBlock(self, text: str) -> None:
        for pattern, color in self.rules:
            style = QTextCharFormat()
            style.setForeground(QColor(color))
            for match in pattern.finditer(text):
                self.setFormat(match.start(), match.end() - match.start(), style)


class LineNumbers(QWidget):
    def __init__(self, editor: "PythonEdit") -> None:
        super().__init__(editor)
        self.editor = editor

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor("#0b1611"))
        painter.setPen(QColor("#778e84"))
        block = self.editor.firstVisibleBlock()
        top = int(
            self.editor.blockBoundingGeometry(block).translated(self.editor.contentOffset()).y()
        )
        while block.isValid() and top <= event.rect().bottom():
            height = int(self.editor.blockBoundingRect(block).height())
            if block.isVisible() and top + height >= event.rect().top():
                painter.drawText(
                    QRect(0, top, self.width() - 6, height),
                    Qt.AlignmentFlag.AlignRight,
                    str(block.blockNumber() + 1),
                )
            top += height
            block = block.next()


class PythonEdit(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        font = QFont("monospace", 10)
        font.setFixedPitch(True)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.highlighter = PythonHighlight(self.document())
        self.numbers = LineNumbers(self)
        self.blockCountChanged.connect(self._margin)
        self.updateRequest.connect(self._update_numbers)
        self._margin()

    def _margin(self) -> None:
        width = 12 + self.fontMetrics().horizontalAdvance("9") * len(str(self.blockCount()))
        self.setViewportMargins(width, 0, 0, 0)
        self.numbers.setGeometry(0, 0, width, self.contentsRect().height())

    def _update_numbers(self, rect: QRect, dy: int) -> None:
        if dy:
            self.numbers.scroll(0, dy)
        else:
            self.numbers.update(0, rect.y(), self.numbers.width(), rect.height())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._margin()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Tab and not self.textCursor().hasSelection():
            self.insertPlainText(" " * 4)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            line = self.textCursor().block().text()[: self.textCursor().positionInBlock()]
            indent = line[: len(line) - len(line.lstrip())]
            self.insertPlainText("\n" + indent + (" " * 4 if line.rstrip().endswith(":") else ""))
        else:
            super().keyPressEvent(event)


@dataclass
class Draft:
    base: ScriptBinding | None
    name: str
    source: str

    @property
    def changed(self) -> bool:
        original = (self.base.name, self.base.source) if self.base else ("behavior", "")
        return (self.name, self.source) != original


class SourceLoader(QThread):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.source = ""
        self.error: str | None = None

    def run(self) -> None:
        try:
            self.source = read_source(self.path)
            ScriptBinding.from_source("imported", "behavior", self.source)
        except (OSError, ValueError) as error:
            self.error = str(error)


class ScriptPanel(QWidget):
    draft_changed = Signal()
    navigate = Signal(str)

    def __init__(
        self,
        apply: Callable[[tuple[SetScript, ...], int], bool],
        report: Callable[[str], None],
    ) -> None:
        super().__init__()
        self.apply_commands, self.report = apply, report
        self.document: Document | None = None
        self.selected: str | None = None
        self.drafts: dict[str, Draft] = {}
        self._loading = False
        self._generation = 0
        self.loader: SourceLoader | None = None
        layout = QVBoxLayout(self)
        self.title = QLabel("Select an object to add a Python behavior.")
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.title)
        self.name = QLineEdit()
        self.name.setMaxLength(48)
        self.name.setPlaceholderText("Behavior name")
        self.name.setAccessibleName("Python behavior name")
        layout.addWidget(self.name)
        row = QHBoxLayout()
        self.templates = QComboBox()
        self.templates.addItems(list(TEMPLATES))
        row.addWidget(self.templates)
        self.template_button = QPushButton("Use template")
        self.template_button.setToolTip("Replace the selected source draft with this template.")
        self.template_button.clicked.connect(self.use_template)
        row.addWidget(self.template_button)
        self.import_button = QPushButton("Import .py…")
        self.import_button.clicked.connect(self.choose_import)
        row.addWidget(self.import_button)
        layout.addLayout(row)
        self.code = PythonEdit()
        self.code.setAccessibleName("Python behavior source")
        self.code.setPlaceholderText(
            "Write a callback or choose a template. Code runs only in Play."
        )
        self.code.setMinimumHeight(120)
        self.controls = QWidget()
        controls = QHBoxLayout(self.controls)
        controls.setContentsMargins(8, 4, 8, 4)
        self.apply_button = QPushButton("Apply behavior")
        self.apply_button.clicked.connect(self.apply_selected)
        controls.addWidget(self.apply_button)
        self.detach_button = QPushButton("Detach")
        self.detach_button.clicked.connect(self.detach)
        controls.addWidget(self.detach_button)
        revert = QPushButton("Revert all drafts")
        revert.clicked.connect(self.revert)
        controls.addWidget(revert)
        help_button = QPushButton("API help")
        help_button.clicked.connect(self.show_help)
        controls.addWidget(help_button)
        layout.addWidget(self.code)
        self.hint = QLabel("Save/Play/Export apply drafts. Stop/start Play to load changed code.")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.errors = QListWidget()
        self.errors.setMaximumHeight(80)
        self.errors.hide()
        self.errors.setAccessibleName("Python behavior errors; double-click to open source line")
        self.errors.itemActivated.connect(self._open_error)
        layout.addWidget(self.errors)
        self.name.textChanged.connect(self._edited)
        self.code.textChanged.connect(self._edited)

    def show_help(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Python behavior API")
        dialog.resize(640, 520)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(
            "Callbacks (all optional, at least one required):\n"
            "  start(ctx), update(ctx, dt), stop(ctx)\n"
            "  on_key(ctx, key, pressed)\n"
            "  on_collision(ctx, other_id), on_collect(ctx, other_id)\n\n"
            "Context: ctx.id, x, y, elapsed, world_width, world_height\n"
            "  ctx.state: persistent per-object dictionary, reset on Restart\n"
            "  ctx.get(id): read-only object snapshot\n"
            "Input: ctx.input.down('space'), x/y integer axes,\n"
            "  horizontal/vertical normalized WASD/arrow axes\n"
            "  Keys: letters, digits, arrows, space, enter, shift, ctrl\n\n"
            "Actions affect your own runtime object:\n"
            "  ctx.move(dx, dy): swept wall collisions and arena bounds\n"
            "  ctx.set_position(x, y): teleport, arena bounds only\n"
            "  ctx.set_rotation(degrees): visual rotation\n"
            "  ctx.set_color('#rrggbb'): shapes only; no sprite tint\n"
            "  ctx.set_visible(True): visuals only, keeps collisions\n"
            "  ctx.add_score(points): integer within +/-1,000\n"
            "  print(...): captured in Activity\n\n"
            "Code runs only during Play, with OS restrictions.\n"
            "Standard-library math/random work; project files, Qt, networking,\n"
            "installed packages and child processes are unavailable.\n"
            "Keep callbacks short: updates have a 250 ms deadline.\n"
            "Limit: 64 actions/request, 64 KiB/source, 16 behaviors/scene.\n"
            "Double-click Play errors to open their source line.\n"
            "Apply, then stop/start Play to load changed code."
        )
        layout.addWidget(text)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec()

    @property
    def pending(self) -> bool:
        return any(draft.changed for draft in self.drafts.values())

    def _binding(self, identity: str) -> ScriptBinding | None:
        if self.document is None:
            return None
        return next((b for b in self.document.scene.scripts if b.entity_id == identity), None)

    def sync(self, document: Document, selected: str | None) -> None:
        if document is not self.document:
            self.document = document
            self.drafts.clear()
            self.errors.clear()
            self.errors.hide()
        if selected != self.selected:
            self._generation += 1
        self.selected = selected
        self._loading = True
        try:
            binding = self._binding(selected) if selected else None
            draft = self.drafts.get(selected) if selected else None
            if selected and (draft is None or (not draft.changed and draft.base != binding)):
                draft = Draft(
                    binding,
                    binding.name if binding else "behavior",
                    binding.source if binding else "",
                )
                self.drafts[selected] = draft
            name, source = (draft.name, draft.source) if draft else ("", "")
            if self.name.text() != name:
                self.name.setText(name)
            if self.code.toPlainText() != source:
                self.code.setPlainText(source)
            for widget in (
                self.name,
                self.code,
                self.templates,
                self.template_button,
                self.import_button,
            ):
                widget.setEnabled(selected is not None)
            self.detach_button.setEnabled(binding is not None)
            self.apply_button.setEnabled(selected is not None)
            self._label()
        finally:
            self._loading = False

    def _label(self) -> None:
        if self.document is None or self.selected is None:
            self.title.setText("Select an object to add a Python behavior.")
            return
        draft = self.drafts[self.selected]
        binding = self._binding(self.selected)
        suffix = " · draft" if draft.changed else " · attached" if binding else " · no behavior"
        if draft.changed and draft.base != binding:
            suffix += " · applied source changed; revert or Undo before applying"
        self.title.setText(self.document.scene.entity(self.selected).name + suffix)
        self.title.setToolTip(
            binding.path if binding else "Python snapshots are stored when saved."
        )

    def _edited(self) -> None:
        if self._loading or self.selected is None:
            return
        draft = self.drafts[self.selected]
        draft.name, draft.source = self.name.text(), self.code.toPlainText()
        self._generation += 1
        self._label()
        self.draft_changed.emit()

    def use_template(self) -> None:
        if self.selected is not None:
            self.code.setPlainText(TEMPLATES[self.templates.currentText()])

    def commands(self, only: str | None = None) -> tuple[SetScript, ...]:
        if self.document is None:
            return ()
        commands = []
        for identity, draft in self.drafts.items():
            if not draft.changed or (only is not None and identity != only):
                continue
            if identity not in {entity.id for entity in self.document.scene.entities}:
                raise ValueError(
                    "A draft's object was deleted. Undo deletion or Revert all drafts."
                )
            if draft.base != self._binding(identity):
                raise ValueError(
                    "Applied source changed while editing. Undo that change or Revert all drafts."
                )
            binding = ScriptBinding.from_source(identity, draft.name, draft.source)
            commands.append(SetScript(identity, asdict(binding)))
        return tuple(commands)

    def snapshot(self) -> Scene:
        assert self.document is not None
        scene = self.document.scene
        for command in self.commands():
            scene = command.apply(scene)
        return scene

    def flush(self, only: str | None = None) -> bool:
        if self.document is None:
            return True
        try:
            commands = self.commands(only)
        except ValueError as error:
            self.report(str(error))
            return False
        if not commands:
            return True
        if not self.apply_commands(commands, self.document.revision):
            return False
        for command in commands:
            self.drafts.pop(command.entity_id, None)
        self.sync(self.document, self.selected)
        self.draft_changed.emit()
        return True

    def apply_selected(self) -> bool:
        return self.flush(self.selected) if self.selected is not None else False

    def detach(self) -> None:
        if self.document is not None and self.selected is not None:
            if self.apply_commands((SetScript(self.selected, None),), self.document.revision):
                self.drafts.pop(self.selected, None)
                self.sync(self.document, self.selected)
                self.draft_changed.emit()

    def revert(self) -> None:
        self.drafts.clear()
        if self.document is not None:
            self.sync(self.document, self.selected)
        self.draft_changed.emit()

    def choose_import(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import Python behavior", "", "Python (*.py)"
        )
        if filename:
            self.import_source(Path(filename))

    def import_source(self, path: Path) -> bool:
        if self.selected is None or self.loader is not None:
            return False
        context = (self.document, self.selected, self._generation, self._binding(self.selected))
        job = SourceLoader(path)
        self.loader = job

        def finished() -> None:
            self.loader = None
            job.deleteLater()
            current = (self.document, self.selected, self._generation, self._binding(context[1]))
            if context != current:
                self.report("Python import canceled because the object or draft changed.")
            elif job.error:
                self.report(f"Could not import Python: {job.error}")
            else:
                name = re.sub(r"[^A-Za-z0-9_-]", "_", path.stem).strip("_-")[:48] or "behavior"
                self.name.setText(name)
                self.code.setPlainText(job.source)

        job.finished.connect(finished)
        job.start()
        return True

    def add_error(self, fault: ScriptFault) -> None:
        self.errors.show()
        while self.errors.count() >= 32:
            self.errors.takeItem(0)
        row = QListWidgetItem(
            f"{Path(fault.path).name.rsplit('--', 1)[0]}:{fault.line} — {fault.message}"
        )
        row.setData(Qt.ItemDataRole.UserRole, fault)
        row.setToolTip(f"{fault.path}:{fault.line}\n{fault.message}")
        self.errors.addItem(row)

    def _open_error(self, row: QListWidgetItem) -> None:
        fault = row.data(Qt.ItemDataRole.UserRole)
        if not isinstance(fault, ScriptFault):
            return
        binding = self._binding(fault.entity_id)
        draft = self.drafts.get(fault.entity_id)
        if binding is None or binding.path != fault.path or (draft and draft.changed):
            self.report(
                "This error belongs to an older Play snapshot. Apply changes and restart Play."
            )
            return
        self.navigate.emit(fault.entity_id)
        cursor = QTextCursor(self.code.document().findBlockByNumber(max(0, fault.line - 1)))
        self.code.setTextCursor(cursor)
        self.code.centerCursor()
        self.code.setFocus()
