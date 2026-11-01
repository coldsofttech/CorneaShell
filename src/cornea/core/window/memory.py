"""Remember where a window was and how big it was, between runs."""

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MIN_VISIBLE = (120, 60)
"""How much of the window's top-left corner must lie on a screen for the position to be kept."""
_FAR_OFF_SCREEN = -30000  # Windows reports minimized windows near here


@dataclass(frozen=True, slots=True)
class Remembered:
    """A window's place and size. ``x`` and ``y`` are ``None`` if it was never placed."""

    width: int
    height: int
    x: int | None = None
    y: int | None = None
    maximized: bool = False


class WindowMemory:
    """Reads and writes one remembered window in a JSON file."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Remembered | None:
        """What was remembered, or ``None`` if there is nothing usable."""
        try:
            data: Any = json.loads(self.path.read_text(encoding="utf-8"))
            width, height = int(data["width"]), int(data["height"])
            x = int(data["x"]) if data.get("x") is not None else None
            y = int(data["y"]) if data.get("y") is not None else None
            maximized = bool(data.get("maximized", False))
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if width <= 0 or height <= 0 or (x is None) != (y is None):
            return None
        return Remembered(width, height, x, y, maximized)

    def save(self, remembered: Remembered) -> None:
        """Write it so that a crash half-way never leaves a broken file."""
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(remembered)), encoding="utf-8")
        temporary.replace(self.path)


def fit_to_screens(
    remembered: Remembered,
    screens: Sequence[tuple[int, int, int, int]],
    minimum: tuple[int, int],
) -> Remembered:
    """Make a remembered window safe to reopen.

    The size is never smaller than ``minimum``. The position is dropped (so the system places the
    window) unless the top-left corner is still on a screen: a monitor may have been unplugged.
    ``screens`` are ``(x, y, width, height)`` rectangles.
    """
    width, height = max(remembered.width, minimum[0]), max(remembered.height, minimum[1])
    x, y = remembered.x, remembered.y
    if (
        x is not None
        and y is not None
        and (x <= _FAR_OFF_SCREEN or y <= _FAR_OFF_SCREEN or not _visible(x, y, screens))
    ):
        x = y = None
    return Remembered(width, height, x, y, remembered.maximized)


def _visible(x: int, y: int, screens: Sequence[tuple[int, int, int, int]]) -> bool:
    if not screens:
        return True  # nothing to check against
    need_width, need_height = MIN_VISIBLE
    return any(
        left <= x <= left + width - need_width and top <= y <= top + height - need_height
        for left, top, width, height in screens
    )
