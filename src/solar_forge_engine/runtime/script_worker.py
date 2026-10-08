"""Standalone trusted bootstrap; install kernel restrictions before reading game source.

Launched with -I -S -B -c from this installed resource, never as a project module.
The protocol and user callbacks are deliberately in a disposable, Qt-free process.
"""

import contextlib
import ctypes
import errno
import io
import json
import math
import os
import platform
import random
import resource
import signal
import sys

from solar_forge_engine.core.behavior import MAX_BEHAVIORS, Behavior

MAX_MESSAGE_BYTES = 128 * 1024
MAX_OUTPUT_BYTES = 4096
MAX_COMMANDS = 32
MEMORY_LIMIT = 256 * 1024 * 1024
# No pathname, network, process/thread creation, exec, signalling, tracing, ioctl,
# credential, namespace, or kernel-policy syscalls are allowed after installation.
SYSCALLS = (
    "read",
    "write",
    "close",
    "exit",
    "exit_group",
    "brk",
    "mmap",
    "mprotect",
    "munmap",
    "mremap",
    "madvise",
    "futex",
    "clock_gettime",
    "clock_nanosleep",
    "nanosleep",
    "rt_sigreturn",
    "rt_sigaction",
    "rt_sigprocmask",
    "sigaltstack",
    "getrandom",
    "getpid",
    "gettid",
    "restart_syscall",
)


def restrict(parent_pid: int) -> None:
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        raise RuntimeError("Script isolation currently requires Linux x86_64.")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    libc.prctl.restype = ctypes.c_int
    # Kill on parent death, disable core/ptrace access, and forbid privilege gains.
    for option, value in ((1, signal.SIGKILL), (4, 0), (38, 1)):
        if libc.prctl(option, value, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "Cannot restrict the script process")
    if os.getppid() != parent_pid:
        raise RuntimeError("The script owner exited during startup.")
    library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    os.closerange(3, 1_048_576)
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (3, 3))
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT, MEMORY_LIMIT))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    library.seccomp_rule_add.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    library.seccomp_release.restype = None
    policy = library.seccomp_init(0x00050000 | errno.EPERM)
    if not policy:
        raise RuntimeError("Cannot allocate the script syscall policy.")
    try:
        for name in SYSCALLS:
            syscall = library.seccomp_syscall_resolve_name(name.encode("ascii"))
            if syscall < 0 or library.seccomp_rule_add(policy, 0x7FFF0000, syscall, 0) != 0:
                raise RuntimeError(f"Cannot restrict script syscall: {name}")
        if library.seccomp_load(policy) != 0:
            raise RuntimeError("Kernel refused the script syscall policy.")
    finally:
        library.seccomp_release(policy)


class ScriptOutput(io.TextIOBase):
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.size = 0

    def write(self, text: str) -> int:
        self.size += len(text.encode("utf-8"))
        if self.size > MAX_OUTPUT_BYTES:
            raise ValueError("Script output exceeds 4 KiB per callback.")
        self.parts.append(text)
        return len(text)


def dash_actions(
    held: bool = False, pressed: bool = False, released: bool = False
) -> dict[str, dict[str, bool]]:
    """The fixed, device-independent named-action contract; no worker device access."""
    return validate_actions({"dash": {"held": held, "pressed": pressed, "released": released}})


def validate_actions(value: object) -> dict[str, dict[str, bool]]:
    if not isinstance(value, dict) or set(value) != {"dash"}:
        raise ValueError("Script actions must contain only dash.")
    action = value["dash"]
    if (
        not isinstance(action, dict)
        or set(action) != {"held", "pressed", "released"}
        or any(type(flag) is not bool for flag in action.values())
    ):
        raise ValueError("Dash requires boolean held, pressed and released flags.")
    return {"dash": dict(action)}


class Game:
    def __init__(self) -> None:
        self.objects: dict[str, dict[str, object]] = {}
        self.player: dict[str, object] = {}
        self.input: dict[str, object] = {}
        self.actions = dash_actions()
        self.collected = 0
        self.total_coins = 0
        self.time = 0.0
        self.data: dict[str, object] = {}
        self.commands: list[dict[str, object]] = []

    def load(self, state: dict[str, object]) -> None:
        objects, player, inputs = state["objects"], state["player"], state["input"]
        if (
            not isinstance(objects, dict)
            or not isinstance(player, dict)
            or not isinstance(inputs, dict)
        ):
            raise ValueError("Invalid game context.")
        self.objects, self.player, self.input = objects, player, inputs
        self.actions = validate_actions(state.get("actions", dash_actions()))
        collected, total, elapsed = state["collected"], state["total_coins"], state["time"]
        if (
            not isinstance(collected, int)
            or not isinstance(total, int)
            or not isinstance(elapsed, (int, float))
        ):
            raise ValueError("Invalid game counters.")
        self.collected, self.total_coins, self.time = collected, total, elapsed
        self.commands = []

    def set_position(self, entity_id: str, x: float, y: float) -> None:
        self._append({"op": "position", "id": entity_id, "x": x, "y": y})

    def set_speed(self, speed: float) -> None:
        self._append({"op": "speed", "value": speed})

    def say(self, message: str) -> None:
        self._append({"op": "message", "value": message})

    def _append(self, command: dict[str, object]) -> None:
        if len(self.commands) >= MAX_COMMANDS:
            raise ValueError("Scripts support at most 32 commands per callback.")
        self.commands.append(command)


class BehaviorInstance:
    def __init__(self, entity_id: str, attachment: Behavior) -> None:
        self.id = entity_id
        self.parameters = {item.name: item.value for item in attachment.parameters}
        self.data: dict[str, object] = {}


def behavior_instances(
    state: dict[str, object], namespace: dict[str, object]
) -> list[tuple[str, BehaviorInstance]]:
    entries = state.get("behaviors", [])
    objects = state.get("objects")
    if (
        not isinstance(entries, list)
        or len(entries) > MAX_BEHAVIORS
        or not isinstance(objects, dict)
    ):
        raise ValueError("Invalid behavior context or more than 32 attachments.")
    result: list[tuple[str, BehaviorInstance]] = []
    ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"id", "attachment"}:
            raise ValueError("Invalid behavior context fields.")
        entity_id = entry["id"]
        if not isinstance(entity_id, str) or entity_id not in objects or entity_id in ids:
            raise ValueError("Behavior objects must exist and have unique IDs.")
        attachment = Behavior.from_data(entry["attachment"])
        callbacks = [namespace.get(attachment.name + suffix) for suffix in ("_start", "_update")]
        if not any(callable(callback) for callback in callbacks) or any(
            callback is not None and not callable(callback) for callback in callbacks
        ):
            raise ValueError(
                f"Behavior {attachment.name} on {entity_id} requires callable callbacks."
            )
        ids.add(entity_id)
        result.append((attachment.name, BehaviorInstance(entity_id, attachment)))
    return result


def send(message: dict[str, object]) -> None:
    raw = (json.dumps(message, allow_nan=False) + "\n").encode("utf-8")
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ValueError("Script response exceeds its message limit.")
    while raw:
        written = os.write(1, raw)
        raw = raw[written:]


def main() -> int:
    try:
        restrict(int(sys.argv[1]))
    except (OSError, ValueError, RuntimeError) as error:
        send({"type": "unavailable", "message": str(error)[:500]})
        return 1
    send({"type": "ready"})
    game = Game()
    namespace: dict[str, object] = {"__name__": "__game__", "math": math, "random": random}
    started = False
    instances: list[tuple[str, BehaviorInstance]] = []
    while True:
        raw = sys.stdin.buffer.readline(MAX_MESSAGE_BYTES + 1)
        if not raw:
            return 0
        if len(raw) > MAX_MESSAGE_BYTES or not raw.endswith(b"\n"):
            return 1
        request_id = -1
        behavior_context = ""
        try:
            request = json.loads(raw)
            if not isinstance(request, dict) or type(request.get("id")) is not int:
                raise ValueError("Invalid script request.")
            request_id = request["id"]
            state = request.get("state")
            if not isinstance(state, dict):
                raise ValueError("Missing game state.")
            game.load(state)
            output = ScriptOutput()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                if request.get("op") == "start" and not started:
                    source = request.get("source")
                    if not isinstance(source, str):
                        raise ValueError("Missing script source.")
                    exec(compile(source, "<scene-script>", "exec"), namespace)
                    instances = behavior_instances(state, namespace)
                    started = True
                    callback = namespace.get("on_start")
                    if callback is not None:
                        if not callable(callback):
                            raise ValueError("on_start must be a function.")
                        callback(game)
                    for name, instance in instances:
                        behavior_context = f"Behavior {name} on {instance.id}: "
                        callback = namespace.get(name + "_start")
                        if callback is not None:
                            if not callable(callback):
                                raise ValueError("Behavior start callback must be a function.")
                            callback(game, instance)
                elif request.get("op") == "update" and started:
                    callback = namespace.get("on_update")
                    if callback is not None:
                        if not callable(callback):
                            raise ValueError("on_update must be a function.")
                        callback(game, request["dt"])
                    for name, instance in instances:
                        behavior_context = f"Behavior {name} on {instance.id}: "
                        callback = namespace.get(name + "_update")
                        if callback is not None:
                            if not callable(callback):
                                raise ValueError("Behavior update callback must be a function.")
                            callback(game, instance, request["dt"])
                else:
                    raise ValueError("Invalid script lifecycle request.")
            send(
                {
                    "type": "result",
                    "id": request_id,
                    "commands": game.commands,
                    "output": "".join(output.parts),
                }
            )
        except BaseException as error:
            line = error.lineno if isinstance(error, SyntaxError) else 0
            trace = error.__traceback__
            while trace:
                if trace.tb_frame.f_code.co_filename == "<scene-script>":
                    line = trace.tb_lineno
                trace = trace.tb_next
            send(
                {
                    "type": "error",
                    "id": request_id,
                    "line": line or 0,
                    "message": f"{behavior_context}{type(error).__name__}: {str(error)[:350]}",
                }
            )
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
