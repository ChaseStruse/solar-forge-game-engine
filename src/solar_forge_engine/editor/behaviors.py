"""Native object attachment and numeric parameter editing; never evaluates source."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from solar_forge_engine.core.behavior import MAX_PARAMETERS, Behavior, BehaviorParameter
from solar_forge_engine.core.scene import Entity


class BehaviorDialog(QDialog):
    apply_requested = Signal(object)

    def __init__(self, entity: Entity, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Object behavior — {entity.name}")
        self.resize(620, 480)
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Define name_start(game, instance) and/or name_update(game, instance, dt) "
            "in Scene → Edit scene script. Each object gets its own instance.data; "
            "numeric settings below are available as instance.parameters. Apply, then Play."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.enabled = QCheckBox("Attach behavior")
        self.enabled.setChecked(entity.behavior is not None)
        layout.addWidget(self.enabled)
        self.name = QLineEdit(entity.behavior.name if entity.behavior else "")
        self.name.setMaxLength(64)
        self.name.setPlaceholderText("Callback name, e.g. bob")
        self.name.setAccessibleName("Behavior callback name")
        layout.addWidget(self.name)
        self.parameters = QTableWidget(0, 2)
        self.parameters.setHorizontalHeaderLabels(["Parameter name", "Value"])
        self.parameters.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.parameters, 1)
        row = QHBoxLayout()
        self.add = QPushButton("Add parameter")
        self.add.clicked.connect(lambda: self.add_parameter())
        row.addWidget(self.add)
        self.remove = QPushButton("Remove selected parameter")
        self.remove.clicked.connect(self.remove_parameter)
        row.addWidget(self.remove)
        layout.addLayout(row)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        self.apply_button = QPushButton("Apply behavior")
        self.apply_button.clicked.connect(self._apply)
        actions.addWidget(self.apply_button)
        layout.addLayout(actions)
        self.name.textChanged.connect(self._validate)
        self.parameters.itemChanged.connect(self._validate)
        self.enabled.toggled.connect(self._validate)
        if entity.behavior:
            for parameter in entity.behavior.parameters:
                self.add_parameter(parameter.name, parameter.value)
        self._validate()

    def add_parameter(self, name: str = "", value: float = 0) -> None:
        if self.parameters.rowCount() >= MAX_PARAMETERS:
            return
        row = self.parameters.rowCount()
        self.parameters.insertRow(row)
        field = QLineEdit(repr(value))
        field.setMaxLength(64)
        field.setAccessibleName("Numeric parameter value")
        field.textChanged.connect(self._validate)
        self.parameters.setCellWidget(row, 1, field)
        self.parameters.setItem(row, 0, QTableWidgetItem(name))
        self._validate()

    def remove_parameter(self) -> None:
        row = self.parameters.currentRow()
        if row >= 0:
            self.parameters.removeRow(row)
            self._validate()

    def attachment(self) -> Behavior | None:
        if not self.enabled.isChecked():
            return None
        parameters = []
        for row in range(self.parameters.rowCount()):
            item = self.parameters.item(row, 0)
            value = self.parameters.cellWidget(row, 1)
            if item is None or not isinstance(value, QLineEdit):
                raise ValueError("Complete each parameter name and value.")
            try:
                number = float(value.text())
            except ValueError as error:
                raise ValueError("Parameter values must be numbers.") from error
            parameters.append(BehaviorParameter(item.text(), number))
        return Behavior(self.name.text(), tuple(parameters))

    def _validate(self) -> None:
        enabled = self.enabled.isChecked()
        self.name.setEnabled(enabled)
        self.parameters.setEnabled(enabled)
        self.add.setEnabled(enabled and self.parameters.rowCount() < MAX_PARAMETERS)
        self.remove.setEnabled(enabled)
        try:
            self.attachment()
        except ValueError as error:
            self.status.setText(str(error))
            self.apply_button.setEnabled(False)
        else:
            self.status.setText("Editing does not run source. Apply is undoable; Save keeps it.")
            self.apply_button.setEnabled(True)

    def _apply(self) -> None:
        try:
            attachment = self.attachment()
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.apply_requested.emit(attachment)
