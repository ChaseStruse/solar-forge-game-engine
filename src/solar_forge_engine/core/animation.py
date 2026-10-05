"""Bounded row-major sprite-sheet animation metadata."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Animation:
    columns: int = 1
    rows: int = 1
    fps: int = 8

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or not 1 <= value <= 256 for value in (self.columns, self.rows)
        ):
            raise ValueError("Animation columns and rows must be integers within 1–256.")
        if self.columns * self.rows > 256:
            raise ValueError("Animations support at most 256 frames.")
        if type(self.fps) is not int or not 1 <= self.fps <= 60:
            raise ValueError("Animation speed must be an integer within 1–60 frames/second.")

    @classmethod
    def from_data(cls, value: object) -> "Animation":
        if not isinstance(value, dict) or set(value) != {"columns", "rows", "fps"}:
            raise ValueError("Invalid animation fields.")
        return cls(value["columns"], value["rows"], value["fps"])

    def frame_at(self, ticks: int) -> int:
        return ticks * self.fps // 60 % (self.columns * self.rows)
