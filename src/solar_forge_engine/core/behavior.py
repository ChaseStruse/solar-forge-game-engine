"""Immutable object attachments; shared with the preloaded restricted worker."""

import keyword
import math
import re
from dataclasses import dataclass

MAX_BEHAVIORS = 32
MAX_PARAMETERS = 16


def identifier(value: object) -> str:
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", value)
        or keyword.iskeyword(value)
    ):
        raise ValueError(
            "Behavior and parameter names must be Python identifiers (1–64 characters)."
        )
    return value


@dataclass(frozen=True)
class BehaviorParameter:
    name: str
    value: float

    def __post_init__(self) -> None:
        identifier(self.name)
        if (
            isinstance(self.value, bool)
            or not isinstance(self.value, (int, float))
            or not -100_000 <= self.value <= 100_000
            or not math.isfinite(self.value)
        ):
            raise ValueError("Behavior parameters must be finite numbers within ±100,000.")
        object.__setattr__(self, "value", float(self.value))


@dataclass(frozen=True)
class Behavior:
    name: str
    parameters: tuple[BehaviorParameter, ...] = ()

    def __post_init__(self) -> None:
        identifier(self.name)
        if self.name == "on":
            raise ValueError("The name on is reserved for scene callbacks.")
        if (
            not isinstance(self.parameters, tuple)
            or len(self.parameters) > MAX_PARAMETERS
            or any(not isinstance(item, BehaviorParameter) for item in self.parameters)
        ):
            raise ValueError("A behavior supports at most 16 numeric parameters.")
        if len({item.name for item in self.parameters}) != len(self.parameters):
            raise ValueError("Behavior parameter names must be unique.")

    @classmethod
    def from_data(cls, value: object) -> "Behavior":
        if not isinstance(value, dict) or set(value) != {"name", "parameters"}:
            raise ValueError("Invalid behavior attachment fields.")
        parameters = value["parameters"]
        if not isinstance(parameters, (list, tuple)) or len(parameters) > MAX_PARAMETERS:
            raise ValueError("A behavior supports at most 16 numeric parameters.")
        result = []
        for item in parameters:
            if not isinstance(item, dict) or set(item) != {"name", "value"}:
                raise ValueError("Invalid behavior parameter fields.")
            result.append(BehaviorParameter(identifier(item["name"]), item["value"]))
        return cls(identifier(value["name"]), tuple(result))
