"""Private Python behavior interpreter. Project code runs only after OS isolation."""

import inspect
import io
import json
import math
import random
import re
import sys
import traceback
from collections.abc import Callable
from types import MappingProxyType, ModuleType
from typing import TextIO

from solar_forge_engine.runtime.script_protocol import (
    MAX_ACTIONS,
    MAX_INPUT_BYTES,
    MAX_LOGS,
    scalar,
)
from solar_forge_engine.runtime.script_security import enforce

PARENT_PID: int | None = None

CALLBACKS = ("start", "update", "on_collision", "on_collect", "on_key", "stop")


class Output(io.TextIOBase):
    def __init__(self) -> None:
        self.messages: list[str] = []
        self._partial = ""

    def write(self, text: str) -> int:
        remaining = text
        while remaining and len(self.messages) < MAX_LOGS:
            chunk, separator, remaining = remaining.partition("\n")
            self._partial = (self._partial + chunk[:512])[:512]
            if not separator:
                break
            self.flush()
        return len(text)

    def clear(self) -> None:
        self.messages.clear()
        self._partial = ""

    def flush(self) -> None:
        if self._partial.strip() and len(self.messages) < MAX_LOGS:
            self.messages.append(self._partial)
        self._partial = ""


class Input:
    def __init__(self, keys: list[str]) -> None:
        self._keys = frozenset(keys)
        self.x = int(self.down("right") or self.down("d")) - int(
            self.down("left") or self.down("a")
        )
        self.y = int(self.down("down") or self.down("s")) - int(self.down("up") or self.down("w"))
        length = math.hypot(self.x, self.y)
        self.horizontal = self.x / length if length else 0.0
        self.vertical = self.y / length if length else 0.0

    def down(self, key: str) -> bool:
        return key.casefold() in self._keys


class Context:
    def __init__(
        self,
        identity: str,
        bodies: dict[str, dict[str, object]],
        state: dict[str, object],
        keys: list[str],
        elapsed: float,
        actions: list[dict[str, object]],
    ) -> None:
        self.id = identity
        self.input = Input(keys)
        self.state = state
        self.elapsed = elapsed
        self.world_width, self.world_height = 1024, 576
        self._bodies = bodies
        self._actions = actions

    @property
    def x(self) -> float:
        return scalar(self._bodies[self.id]["x"])

    @property
    def y(self) -> float:
        return scalar(self._bodies[self.id]["y"])

    def get(self, identity: str) -> MappingProxyType[str, object]:
        """Read another object's most recently observed runtime properties."""
        return MappingProxyType(self._bodies[identity])

    def _emit(self, kind: str, *values: float | str | bool) -> None:
        if len(self._actions) >= MAX_ACTIONS:
            raise ValueError("A behavior frame supports at most 64 actions.")
        self._actions.append({"entity_id": self.id, "kind": kind, "values": list(values)})

    def move(self, dx: float, dy: float) -> None:
        dx, dy = scalar(dx), scalar(dy)
        self._emit("move", dx, dy)
        self._bodies[self.id]["x"] = self.x + dx
        self._bodies[self.id]["y"] = self.y + dy

    def set_position(self, x: float, y: float) -> None:
        x, y = scalar(x), scalar(y)
        self._emit("position", x, y)
        self._bodies[self.id]["x"], self._bodies[self.id]["y"] = x, y

    def set_rotation(self, degrees: float) -> None:
        self._emit("rotation", scalar(degrees))

    def set_color(self, color: str) -> None:
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Colors must use six-digit hex values.")
        self._emit("color", color)

    def set_visible(self, visible: bool) -> None:
        if type(visible) is not bool:
            raise ValueError("Visibility must be True or False.")
        self._emit("visible", visible)

    def add_score(self, points: int) -> None:
        if type(points) is not int or abs(points) > 1000:
            raise ValueError("Score changes must be integers within ±1,000.")
        self._emit("score", points)


class Behavior:
    def __init__(self, data: dict[str, object]) -> None:
        identity, path, source = data["entity_id"], data["path"], data["source"]
        if (
            not isinstance(identity, str)
            or not isinstance(path, str)
            or not isinstance(source, str)
        ):
            raise ValueError("Invalid behavior source snapshot.")
        self.id, self.path = identity, path
        self.state: dict[str, object] = {}
        module = ModuleType(f"solar_behavior_{self.id}")
        module.__file__ = self.path
        sys.modules[module.__name__] = module
        namespace = module.__dict__
        exec(compile(source, self.path, "exec"), namespace)
        self.callbacks: dict[str, Callable[..., object]] = {}
        for name in CALLBACKS:
            callback = namespace.get(name)
            if callback is not None:
                if not callable(callback):
                    raise ValueError(f"Behavior {name} must be callable.")
                if inspect.iscoroutinefunction(callback) or inspect.isgeneratorfunction(callback):
                    raise ValueError("Behavior callbacks must be synchronous, without yield.")
                self.callbacks[name] = callback
        if not self.callbacks:
            raise ValueError("Define start(ctx), update(ctx, dt) or an event callback.")

    def call(self, name: str, context: Context, *arguments: object) -> None:
        callback = self.callbacks.get(name)
        if callback is not None:
            callback(context, *arguments)


def send(channel: TextIO, value: dict[str, object]) -> None:
    channel.write(json.dumps(value, allow_nan=False) + "\n")
    channel.flush()


def worker_main() -> int:
    # Load all trusted helpers above before narrowing file access. No Qt/editor/model
    # modules are installed in this interpreter's synthetic runtime package.
    channel = sys.stdout
    try:
        enforce(PARENT_PID)
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Python isolation unavailable: {error}", file=sys.stderr, flush=True)
        return 1
    random.seed(0)
    output = Output()
    sys.stdout = output
    sys.stderr = output
    behaviors: list[Behavior] = []
    bodies: dict[str, dict[str, object]] = {}
    previous_keys: set[str] = set()
    elapsed = 0.0
    while raw := sys.stdin.readline(MAX_INPUT_BYTES + 1):
        if len(raw.encode("utf-8")) > MAX_INPUT_BYTES:
            return 1
        request = json.loads(raw)
        identity = request["id"]
        output.clear()
        actions: list[dict[str, object]] = []
        current_id, current_path = "", ""
        try:
            phase = request["op"]
            if phase == "init":
                bodies = {body["id"]: body for body in request["entities"]}
                for data in request["scripts"]:
                    current_id, current_path = data["entity_id"], data["path"]
                    send(channel, {"id": identity, "running": current_id})
                    behavior = Behavior(data)
                    behaviors.append(behavior)
                    context = Context(behavior.id, bodies, behavior.state, [], 0.0, actions)
                    behavior.call("start", context)
            else:
                for entity_id, position in request.get("positions", {}).items():
                    bodies[entity_id]["x"], bodies[entity_id]["y"] = position
                keys = request.get("input", [])
                elapsed = request.get("elapsed", elapsed)
                key_events = [(key, False) for key in sorted(previous_keys - set(keys))]
                key_events += [(key, True) for key in sorted(set(keys) - previous_keys)]
                for behavior in behaviors:
                    current_id, current_path = behavior.id, behavior.path
                    send(channel, {"id": identity, "running": current_id})
                    context = Context(behavior.id, bodies, behavior.state, keys, elapsed, actions)
                    if phase == "stop":
                        behavior.call("stop", context)
                        continue
                    for key, pressed in key_events:
                        behavior.call("on_key", context, key, pressed)
                    for event in request.get("events", []):
                        if event["entity_id"] == behavior.id:
                            behavior.call("on_" + event["kind"], context, event["other"])
                    behavior.call("update", context, request["dt"])
                previous_keys = set(keys)
            output.flush()
            send(
                channel,
                {"id": identity, "actions": actions, "logs": output.messages, "error": None},
            )
            if phase == "stop":
                return 0
        except BaseException as error:
            line = error.lineno or 1 if isinstance(error, SyntaxError) else 1
            for frame in traceback.extract_tb(error.__traceback__, limit=12):
                if frame.filename == current_path:
                    line = frame.lineno or 1
            fault = {
                "entity_id": current_id,
                "path": current_path,
                "line": min(max(line, 1), 65536),
                "message": f"{type(error).__name__}: {error}"[:2048],
            }
            output.flush()
            send(channel, {"id": identity, "actions": [], "logs": output.messages, "error": fault})
            return 1
    return 0
