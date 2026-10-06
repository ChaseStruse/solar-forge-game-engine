"""Bounded behavior-worker messages, validated before they affect the game."""

import math
import re
from dataclasses import dataclass

MAX_PACKET_BYTES = 64 * 1024
MAX_ACTIONS = 64
MAX_LOGS = 16
MAX_INPUT_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class ScriptFault:
    entity_id: str
    path: str
    line: int
    message: str


@dataclass(frozen=True)
class ScriptAction:
    entity_id: str
    kind: str
    values: tuple[float | str | bool, ...]


@dataclass(frozen=True)
class ScriptResult:
    actions: tuple[ScriptAction, ...]
    logs: tuple[str, ...]
    fault: ScriptFault | None


def scalar(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Behavior coordinates must be numbers.")
    if not math.isfinite(value) or abs(value) > 100_000:
        raise ValueError("Behavior coordinates must be finite and within ±100,000.")
    return float(value)


def parse_result(value: object, request_id: int, bindings: dict[str, str]) -> ScriptResult:
    if not isinstance(value, dict) or set(value) != {"id", "actions", "logs", "error"}:
        raise ValueError("Invalid behavior response fields.")
    if type(value["id"]) is not int or value["id"] != request_id:
        raise ValueError("The behavior response is stale.")
    entries, messages, error = value["actions"], value["logs"], value["error"]
    if not isinstance(entries, list) or len(entries) > MAX_ACTIONS:
        raise ValueError("Behavior action limit exceeded.")
    actions = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"entity_id", "kind", "values"}:
            raise ValueError("Invalid behavior action fields.")
        identity, kind, values = entry["entity_id"], entry["kind"], entry["values"]
        if not isinstance(identity, str) or identity not in bindings or not isinstance(kind, str):
            raise ValueError("Behavior actions must identify an attached object.")
        if not isinstance(values, list):
            raise ValueError("Invalid behavior action values.")
        normalized: tuple[float | str | bool, ...]
        if kind in ("move", "position") and len(values) == 2:
            normalized = (scalar(values[0]), scalar(values[1]))
        elif kind == "rotation" and len(values) == 1:
            normalized = (scalar(values[0]),)
        elif kind == "color" and len(values) == 1:
            color = values[0]
            if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError("Behavior colors must use six-digit hex values.")
            normalized = (color,)
        elif kind == "visible" and len(values) == 1 and type(values[0]) is bool:
            normalized = (values[0],)
        elif kind == "score" and len(values) == 1:
            points = values[0]
            if type(points) is not int or abs(points) > 1000:
                raise ValueError("Behavior score changes must be integers within ±1,000.")
            normalized = (float(points),)
        else:
            raise ValueError("Unknown behavior action or invalid value count.")
        actions.append(ScriptAction(identity, kind, normalized))
    if not isinstance(messages, list) or len(messages) > MAX_LOGS:
        raise ValueError("Behavior log limit exceeded.")
    if any(not isinstance(message, str) or len(message) > 512 for message in messages):
        raise ValueError("Invalid behavior log message.")
    fault = None
    if error is not None:
        if not isinstance(error, dict) or set(error) != {"entity_id", "path", "line", "message"}:
            raise ValueError("Invalid behavior error fields.")
        identity, path, line, message = (
            error["entity_id"],
            error["path"],
            error["line"],
            error["message"],
        )
        if not isinstance(identity, str) or bindings.get(identity) != path:
            raise ValueError("The behavior error identifies an unknown source file.")
        if type(line) is not int or not 0 <= line <= 65536:
            raise ValueError("Invalid behavior error line.")
        if not isinstance(message, str) or len(message) > 2048:
            raise ValueError("Invalid behavior error message.")
        fault = ScriptFault(identity, path, line, message)
    return ScriptResult(tuple(actions), tuple(messages), fault)
