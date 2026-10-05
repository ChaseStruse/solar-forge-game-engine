"""Deterministic offline fixture provider. This is not an LLM or natural-language parser."""

import json
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from solar_forge_engine.core.scene import Scene


@dataclass(frozen=True)
class Context:
    scene: Scene
    revision: int
    selected_id: str | None


class Provider(Protocol):
    def propose(self, prompt: str, context: Context) -> str: ...


class DemoProvider:
    def propose(self, prompt: str, context: Context) -> str:
        if not prompt.strip() or len(prompt) > 2000:
            raise ValueError("Enter a demo request of 1–2,000 characters.")
        requests = [request.strip() for request in prompt.split(";")]
        if not 1 <= len(requests) <= 16:
            raise ValueError("Use at most 16 requests separated by semicolons.")
        commands: list[dict[str, object]] = []
        occupied = {entity.id for entity in context.scene.entities}
        for index, request in enumerate(requests):
            if request in ("add rectangle", "add coin"):
                counter = 0
                while True:
                    entity_id = str(
                        uuid5(
                            NAMESPACE_URL,
                            f"solar-forge-demo:{context.revision}:{index}:{request}:{counter}",
                        )
                    )
                    if entity_id not in occupied:
                        break
                    counter += 1
                occupied.add(entity_id)
                coin = request == "add coin"
                commands.append(
                    {
                        "tool": "create_entity",
                        "entity": {
                            "id": entity_id,
                            "name": "Coin" if coin else "Rectangle",
                            "x": 100 + index * 24,
                            "y": 100 + index * 24,
                            "width": 24 if coin else 64,
                            "height": 24 if coin else 64,
                            "role": "coin" if coin else "decoration",
                        },
                    }
                )
                continue
            if context.selected_id is None:
                raise ValueError("Select an object for this demo request.")
            context.scene.entity(context.selected_id)
            if request == "delete selected":
                commands.append({"tool": "delete_entity", "id": context.selected_id})
                continue
            changes: dict[str, object]
            move = re.fullmatch(r"move selected to (-?\d+(?:\.\d+)?) (-?\d+(?:\.\d+)?)", request)
            if move:
                changes = {"x": float(move[1]), "y": float(move[2])}
            elif request.startswith("rename selected "):
                changes = {"name": request.removeprefix("rename selected ")}
            elif request.startswith("color selected "):
                changes = {"color": request.removeprefix("color selected ")}
            elif request.startswith("speed selected "):
                try:
                    changes = {"move_speed": float(request.removeprefix("speed selected "))}
                except ValueError as error:
                    raise ValueError("Speed must be a number.") from error
            else:
                raise ValueError(
                    "Unsupported demo request. Use one of the examples shown in the panel."
                )
            commands.append({"tool": "set_entity", "id": context.selected_id, "changes": changes})
        return json.dumps(
            {
                "format_version": 1,
                "revision": context.revision,
                "summary": "Offline demo proposal — review all changes before applying.",
                "commands": commands,
            }
        )
