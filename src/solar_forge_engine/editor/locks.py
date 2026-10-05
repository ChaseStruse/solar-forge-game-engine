"""Bounded, user-local per-scene drag locks with serialized background I/O."""

import hashlib
import json
import os
import re
import stat
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from solar_forge_engine.ai.preferences import profile_path
from solar_forge_engine.project.storage import atomic_write

MAX_BYTES = 1024 * 1024
MAX_LOCKS = 10_000


def metadata_path(scene: Path) -> Path:
    key = hashlib.sha256(os.fsencode(scene.absolute())).hexdigest()
    return profile_path().parent / "scene-locks" / f"{key}.json"


def read_locks(path: Path) -> tuple[frozenset[str], bytes | None]:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return frozenset(), None
    with os.fdopen(descriptor, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError("Editor locks must be a regular file.")
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Editor lock metadata exceeds 1 MiB.")
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Editor lock metadata is not valid JSON.") from error
    if (
        not isinstance(data, dict)
        or set(data) != {"format_version", "locked_ids"}
        or type(data["format_version"]) is not int
        or data["format_version"] != 1
    ):
        raise ValueError("Invalid editor lock metadata version or fields.")
    ids = data["locked_ids"]
    if (
        not isinstance(ids, list)
        or len(ids) > MAX_LOCKS
        or any(
            not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value)
            for value in ids
        )
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Invalid or excessive editor lock IDs.")
    return frozenset(ids), raw


def write_locks(path: Path, ids: frozenset[str], expected: bytes | None) -> bytes:
    # Revalidate existing bytes before replacing preferences from another instance.
    if read_locks(path)[1] != expected:
        raise ValueError("Editor locks changed externally; reopen the scene before changing locks.")
    raw = json.dumps({"format_version": 1, "locked_ids": sorted(ids)}).encode()
    if len(ids) > MAX_LOCKS or len(raw) > MAX_BYTES:
        raise ValueError("Editor locks exceed their storage limit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, raw)
    return raw


@dataclass(eq=False)
class LockState:
    owner: object
    scene: Path | None
    ids: frozenset[str]
    parent: LockState | None = None
    edits: dict[str, bool] = field(default_factory=dict)
    expected: bytes | None = None
    known: bool = False
    dirty: bool = False
    blocked: bool = False


class LockWorker(QThread):
    def __init__(self, state: LockState) -> None:
        super().__init__()
        self.state = state
        self.loading = not state.known
        self.ids = state.ids
        self.expected = state.expected
        self.raw: bytes | None = None
        self.error: str | None = None

    def run(self) -> None:
        try:
            assert self.state.scene is not None
            path = metadata_path(self.state.scene)
            if self.loading:
                self.ids, self.raw = read_locks(path)
            else:
                self.raw = write_locks(path, self.ids, self.expected)
        except (OSError, ValueError) as error:
            self.error = str(error)


class LockPersistence(QObject):
    restored = Signal(object)
    warning = Signal(str)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self.active: LockState | None = None
        self._pending: list[LockState] = []
        self._job: LockWorker | None = None

    @property
    def busy(self) -> bool:
        return self._job is not None or bool(self._pending)

    def activate(self, owner: object, scene: Path | None, ids: frozenset[str]) -> None:
        scene = scene.absolute() if scene is not None else None
        previous = self.active
        if previous is not None and previous.owner is owner and previous.scene == scene:
            return
        state = LockState(
            owner,
            scene,
            ids,
            parent=previous if previous is not None and previous.owner is owner else None,
        )
        self.active = state
        if scene is not None:
            self._queue(state)

    def update(self, ids: frozenset[str]) -> None:
        state = self.active
        if state is None or ids == state.ids:
            return
        if not state.known:
            for entity_id in state.ids ^ ids:
                state.edits[entity_id] = entity_id in ids
        state.ids = ids
        state.dirty = True
        if state.scene is not None and not state.blocked:
            self._queue(state)

    def _queue(self, state: LockState) -> None:
        if state not in self._pending and (self._job is None or self._job.state is not state):
            self._pending.append(state)
        self._pump()

    def _pump(self) -> None:
        if self._job is not None:
            return
        while self._pending:
            state = self._pending.pop(0)
            if state.blocked or (state.known and not state.dirty):
                continue
            job = LockWorker(state)
            self._job = job
            job.finished.connect(lambda job=job: self._finished(job))
            job.start()
            return

    def _finished(self, job: LockWorker) -> None:
        if job is not self._job:
            return
        self._job = None
        job.deleteLater()
        state = job.state
        if job.error:
            state.blocked = True
            self.warning.emit(f"Editor locks kept in memory; persistence failed: {job.error}")
        elif job.loading:
            base = state.parent.ids if state.parent is not None else job.ids
            restored = set(base)
            for entity_id, locked in state.edits.items():
                if locked:
                    restored.add(entity_id)
                else:
                    restored.discard(entity_id)
            state.parent = None
            state.ids = frozenset(restored)
            state.expected = job.raw
            state.known = True
            state.dirty = state.ids != job.ids
            if state is self.active:
                self.restored.emit(state.ids)
        else:
            state.expected = job.raw
            state.dirty = state.ids != job.ids
        if state.dirty and not state.blocked and state not in self._pending:
            self._pending.insert(0, state)
        self._pump()

    def drain(self, milliseconds: int) -> bool:
        deadline = time.monotonic() + milliseconds / 1000
        while self._job is not None:
            job = self._job
            remaining = max(0, int((deadline - time.monotonic()) * 1000))
            if not remaining or not job.wait(remaining):
                return False
            self._finished(job)
        return not self._pending
