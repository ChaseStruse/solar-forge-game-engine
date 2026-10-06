"""Portable source snapshots; parsing a binding never executes Python."""

import hashlib
import re
from dataclasses import dataclass

MAX_SCRIPTS = 16
MAX_SCRIPT_BYTES = 64 * 1024
MAX_SCRIPT_TOTAL_BYTES = 512 * 1024
SCRIPT_PATH = re.compile(r"scripts/([A-Za-z0-9][A-Za-z0-9_-]{0,47})--([0-9a-f]{64})\.py")


@dataclass(frozen=True)
class ScriptBinding:
    entity_id: str
    path: str
    source: str

    def __post_init__(self) -> None:
        if not isinstance(self.entity_id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{1,64}", self.entity_id
        ):
            raise ValueError("A behavior must identify a valid object.")
        match = SCRIPT_PATH.fullmatch(self.path) if isinstance(self.path, str) else None
        if match is None:
            raise ValueError("Behaviors must use a content-addressed Python path inside scripts/.")
        if not isinstance(self.source, str) or not self.source.strip() or "\0" in self.source:
            raise ValueError("Python source must be nonempty UTF-8 text without NUL characters.")
        raw = self.source.encode("utf-8")
        if len(raw) > MAX_SCRIPT_BYTES:
            raise ValueError("A Python behavior must be no larger than 64 KiB.")
        if hashlib.sha256(raw).hexdigest() != match.group(2):
            raise ValueError("Python behavior content does not match its path hash.")

    @classmethod
    def from_source(cls, entity_id: str, name: str, source: str) -> "ScriptBinding":
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,47}", name):
            raise ValueError("Behavior names need 1–48 letters, digits, underscores or hyphens.")
        if not isinstance(source, str):
            raise ValueError("Python source must be text.")
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        return cls(entity_id, f"scripts/{name}--{digest}.py", source)

    @classmethod
    def from_data(cls, value: object) -> "ScriptBinding":
        if not isinstance(value, dict) or set(value) != {"entity_id", "path", "source"}:
            raise ValueError("Invalid Python behavior fields.")
        return cls(value["entity_id"], value["path"], value["source"])

    @property
    def name(self) -> str:
        return self.path.removeprefix("scripts/").split("--", 1)[0]
