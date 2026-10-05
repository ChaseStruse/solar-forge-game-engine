"""Native assistant proposal review; mutations remain on the editor's main thread."""

from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import Qt, QThread
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from solar_forge_engine.ai.demo import Context, DemoProvider, Provider
from solar_forge_engine.ai.ollama import OllamaProvider
from solar_forge_engine.ai.proposals import Proposal, decode_proposal
from solar_forge_engine.core.commands import Document


class ProposalWorker(QThread):
    def __init__(self, provider: Provider, prompt: str, context: Context) -> None:
        super().__init__()
        self.provider, self.prompt, self.context = provider, prompt, context
        self.proposal: Proposal | None = None
        self.error: str | None = None

    def run(self) -> None:
        try:
            raw = self.provider.propose(
                self.prompt, replace(self.context, cancelled=self.isInterruptionRequested)
            )
            if not self.isInterruptionRequested():
                self.proposal = decode_proposal(raw, self.context.scene, self.context.revision)
        except Exception as error:
            # A provider failure must not unwind through Qt or affect the authored scene.
            self.error = str(error)[:1000] or "Provider failed."


class AssistantPanel(QWidget):
    def __init__(
        self, context: Callable[[], tuple[Document, str | None]], refresh: Callable[[], None]
    ) -> None:
        super().__init__()
        self.context = context
        self.refresh_editor = refresh
        self.provider: Provider = DemoProvider()
        self._job: ProposalWorker | None = None
        self._document: Document | None = None
        self._proposal: Proposal | None = None
        layout = QVBoxLayout(self)
        self.provider_choice = QComboBox()
        self.provider_choice.addItems(["Offline demo", "Ollama · loopback"])
        self.provider_choice.setAccessibleName("Assistant provider")
        layout.addWidget(self.provider_choice)
        self.connection_settings = QWidget()
        settings = QFormLayout(self.connection_settings)
        settings.setContentsMargins(0, 0, 0, 0)
        self.endpoint = QLineEdit("http://127.0.0.1:11434")
        self.endpoint.setMaxLength(200)
        self.model = QLineEdit()
        self.model.setMaxLength(100)
        self.model.setPlaceholderText("Installed local model name")
        self.timeout = QSpinBox()
        self.timeout.setRange(1, 120)
        self.timeout.setValue(60)
        self.timeout.setSuffix(" s")
        settings.addRow("Local server", self.endpoint)
        settings.addRow("Model", self.model)
        settings.addRow("Deadline", self.timeout)
        settings.addRow(QLabel("Run Ollama with OLLAMA_NO_CLOUD=1 for local-only inference."))
        layout.addWidget(self.connection_settings)
        self.connection_settings.hide()
        self.provider_choice.currentIndexChanged.connect(self._provider_changed)
        label = QLabel("Default: offline demo. Ollama sends metadata only to a loopback server.")
        label.setWordWrap(True)
        layout.addWidget(label)
        examples = QLabel(
            "Try: add rectangle; add coin\n"
            "Selected object: move selected to 200 150; rename selected Hero\n"
            "color selected #33aa88; speed selected 120; delete selected"
        )
        examples.setWordWrap(True)
        layout.addWidget(examples)
        self.prompt = QLineEdit()
        self.prompt.setMaxLength(2000)
        self.prompt.setPlaceholderText("Enter a supported demo request")
        self.prompt.setAccessibleName("Assistant request")
        layout.addWidget(self.prompt)
        self.generate_button = QPushButton("Propose edits")
        self.generate_button.clicked.connect(self.generate)
        self.prompt.returnPressed.connect(self.generate)
        layout.addWidget(self.generate_button)
        self.review = QTextEdit()
        self.review.setReadOnly(True)
        self.review.setAcceptRichText(False)
        self.review.setAccessibleName("Assistant proposed scene changes")
        layout.addWidget(self.review)
        self.status = QLabel(
            "Review proposals before applying. Undo remains available after Apply."
        )
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.apply_button = QPushButton("Apply reviewed edits")
        self.apply_button.clicked.connect(self.apply)
        layout.addWidget(self.apply_button)
        self.discard_button = QPushButton("Discard / cancel proposal")
        self.discard_button.clicked.connect(self.discard)
        layout.addWidget(self.discard_button)
        self.apply_button.setEnabled(False)

    def _provider_changed(self, index: int) -> None:
        self.discard()
        self.connection_settings.setVisible(index == 1)
        self.prompt.setPlaceholderText(
            "Describe the scene edits you want" if index == 1 else "Enter a supported demo request"
        )

    def _set_busy(self, busy: bool) -> None:
        self.generate_button.setEnabled(not busy)
        self.provider_choice.setEnabled(not busy)
        self.connection_settings.setEnabled(not busy)

    @property
    def busy(self) -> bool:
        return self._job is not None

    def generate(self) -> None:
        if self._job is not None:
            return
        self.discard()
        if self.provider_choice.currentIndex() == 1:
            try:
                self.provider = OllamaProvider(
                    self.endpoint.text(), self.model.text(), self.timeout.value()
                )
            except ValueError as error:
                self.status.setText(str(error))
                return
        elif isinstance(self.provider, OllamaProvider):
            self.provider = DemoProvider()
        document, selected = self.context()
        self._document = document
        job = ProposalWorker(
            self.provider, self.prompt.text(), Context(document.scene, document.revision, selected)
        )
        self._job = job
        self._set_busy(True)
        self.status.setText("Preparing a proposal…")
        job.finished.connect(lambda: self._finished(job))
        job.start()

    def _finished(self, job: ProposalWorker) -> None:
        self._job = None
        job.deleteLater()
        self._set_busy(False)
        document, _ = self.context()
        if job.isInterruptionRequested():
            self.status.setText("Proposal canceled.")
        elif self._document is not document or document.revision != job.context.revision:
            self.status.setText("Scene changed; generate a fresh proposal.")
        elif job.error:
            self.status.setText(f"Proposal rejected: {job.error}")
        elif job.proposal is not None:
            self._proposal = job.proposal
            self.review.setPlainText(job.proposal.review)
            self.status.setText("Ready for review. No scene edits have been applied.")
            self.apply_button.setEnabled(True)

    def scene_changed(self) -> None:
        document, _ = self.context()
        if self._proposal is not None and (
            document is not self._document or document.revision != self._proposal.revision
        ):
            self._proposal = None
            self.apply_button.setEnabled(False)
            self.status.setText("Scene changed; generate a fresh proposal.")

    def apply(self) -> None:
        document, _ = self.context()
        proposal = self._proposal
        if proposal is None:
            return
        if document is not self._document:
            self.scene_changed()
            return
        try:
            document.execute(*proposal.commands, expected_revision=proposal.revision)
        except ValueError as error:
            self._proposal = None
            self.apply_button.setEnabled(False)
            self.status.setText(f"Proposal rejected: {error}")
            return
        self._proposal = None
        self.apply_button.setEnabled(False)
        self.refresh_editor()
        self.status.setText("Applied as one undoable edit. Save to keep the changes.")

    def discard(self) -> None:
        if self._job is not None:
            self._job.requestInterruption()
        self._proposal = None
        self.apply_button.setEnabled(False)
        self.review.clear()
        self.status.setText("Proposal discarded; scene unchanged.")
