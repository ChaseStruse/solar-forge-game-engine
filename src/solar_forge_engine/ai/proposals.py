"""Bounded untrusted tool responses compiled into shared scene commands."""

import json
from dataclasses import asdict, dataclass

from solar_forge_engine.core.commands import (
    Command,
    CreateEntity,
    DeleteEntity,
    Document,
    SetEntity,
    SetScript,
)
from solar_forge_engine.core.limits import MAX_FILE_BYTES
from solar_forge_engine.core.scene import Entity, Scene, text
from solar_forge_engine.core.script import ScriptBinding

MAX_RESPONSE_BYTES = 16 * 1024
MAX_COMMANDS = 16
EDITABLE = {"name", "x", "y", "width", "height", "color", "role", "move_speed", "input_preset"}


@dataclass(frozen=True)
class Proposal:
    revision: int
    commands: tuple[Command, ...]
    review: str


def decode_proposal(raw: str, scene: Scene, revision: int) -> Proposal:
    if (
        not isinstance(raw, str)
        or len(raw) > MAX_RESPONSE_BYTES
        or len(raw.encode()) > MAX_RESPONSE_BYTES
    ):
        raise ValueError("Assistant response exceeds its 16 KiB limit.")
    try:
        data = json.loads(raw)
    except (ValueError, RecursionError) as error:
        raise ValueError("Assistant response is not valid JSON.") from error
    if not isinstance(data, dict) or set(data) != {
        "format_version",
        "revision",
        "summary",
        "commands",
    }:
        raise ValueError("Invalid assistant proposal fields.")
    if type(data["format_version"]) is not int or data["format_version"] != 1:
        raise ValueError("Unsupported assistant proposal version.")
    if type(data["revision"]) is not int or data["revision"] != revision:
        raise ValueError("Assistant proposal uses a stale scene revision.")
    summary = text(data["summary"], "Proposal summary", 500)
    entries = data["commands"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_COMMANDS:
        raise ValueError("A proposal must contain 1–16 scene commands.")
    commands: list[Command] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid assistant command.")
        tool = entry.get("tool")
        if tool == "create_entity" and set(entry) == {"tool", "entity"}:
            fields = entry["entity"]
            if (
                not isinstance(fields, dict)
                or "id" not in fields
                or not set(fields) <= EDITABLE | {"id"}
            ):
                raise ValueError("Invalid assistant entity fields.")
            commands.append(
                CreateEntity(Entity.from_data({**asdict(Entity("proposal")), **fields}))
            )
        elif tool == "set_entity" and set(entry) == {"tool", "id", "changes"}:
            changes = entry["changes"]
            if not isinstance(changes, dict) or not changes or not set(changes) <= EDITABLE:
                raise ValueError("Assistant edits support only bounded scene properties.")
            commands.append(SetEntity(text(entry["id"], "Entity ID", 64), changes))
        elif tool == "set_script" and set(entry) == {"tool", "id", "name", "source"}:
            binding = ScriptBinding.from_source(entry["id"], entry["name"], entry["source"])
            commands.append(SetScript(binding.entity_id, asdict(binding)))
        elif tool == "detach_script" and set(entry) == {"tool", "id"}:
            commands.append(SetScript(text(entry["id"], "Entity ID", 64), None))
        elif tool == "delete_entity" and set(entry) == {"tool", "id"}:
            commands.append(DeleteEntity(text(entry["id"], "Entity ID", 64)))
        else:
            raise ValueError("Unsupported assistant tool or command fields.")
    preview = Document(scene)
    preview.execute(*commands, expected_revision=0)
    if len(json.dumps(preview.scene.to_data(), indent=2).encode()) + 1 > MAX_FILE_BYTES:
        raise ValueError("Assistant edits would exceed the 4 MiB scene limit.")
    if preview.scene == scene:
        raise ValueError("The proposal makes no scene changes.")
    before = {entity.id: entity for entity in scene.entities}
    after = {entity.id: entity for entity in preview.scene.entities}
    lines = [summary, f"Scene revision: {revision}", ""]
    for entity_id in sorted(before.keys() | after.keys()):
        if entity_id not in after:
            lines.append(f"Delete {before[entity_id].name} [{entity_id}]")
        elif entity_id not in before:
            entity = after[entity_id]
            lines.append(f"Create {entity.name} [{entity_id}]")
            lines.extend(f"  {key}: {getattr(entity, key)}" for key in sorted(EDITABLE))
        elif before[entity_id] != after[entity_id]:
            lines.append(f"Edit {before[entity_id].name} [{entity_id}]")
            for key in sorted(EDITABLE):
                old, new = getattr(before[entity_id], key), getattr(after[entity_id], key)
                if old != new:
                    lines.append(f"  {key}: {old} → {new}")
    before_scripts = {binding.entity_id: binding for binding in scene.scripts}
    after_scripts = {binding.entity_id: binding for binding in preview.scene.scripts}
    for entity_id in sorted(before_scripts.keys() | after_scripts.keys()):
        old_script, new_script = before_scripts.get(entity_id), after_scripts.get(entity_id)
        if old_script == new_script:
            continue
        if new_script is None:
            lines.append(f"Detach Python behavior [{entity_id}]")
        else:
            action = "Replace" if old_script else "Attach"
            lines.extend(
                (
                    f"{action} Python {new_script.name} [{entity_id}]",
                    "Source for review — runs only in restricted Play:",
                    new_script.source,
                )
            )
    return Proposal(revision, tuple(commands), "\n".join(lines))
