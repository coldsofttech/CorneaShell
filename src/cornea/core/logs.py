"""Logging for Cornea: quiet by default, one call to switch it on.

Cornea writes to the standard ``cornea`` logger and never configures logging by itself. A
program that already sets up logging sees Cornea's messages like any other library's.
:func:`configure_logging` is the quick way to read them. The start-up link carries a one-time
token, so anything that looks like ``cornea_token=...`` is hidden before a line is written.
"""

import logging
import logging.handlers
import re
import sys
from pathlib import Path
from typing import Literal, get_args

from cornea.core.appdata import logs_dir

LogLevel = Literal["debug", "info", "warning", "error"]
"""The levels :func:`configure_logging` accepts."""

LOG_LEVELS: tuple[str, ...] = get_args(LogLevel)

_ROOT = "cornea"
LOG_FILE_SIZE = 1_000_000
"""A log file is started over (keeping three older ones) when it reaches this many bytes."""
LOG_FILE_BACKUPS = 3
_TOKEN = re.compile(r"(cornea_token=)[^&\s'\"]+")
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


class _Formatter(logging.Formatter):
    """Formats a line and hides any start-up token in it, tracebacks included."""

    def format(self, record: logging.LogRecord) -> str:
        return _TOKEN.sub(r"\1<hidden>", super().format(record))


def configure_logging(level: LogLevel = "debug", *, file: Path | str | None = None) -> None:
    """Show Cornea's log messages on stderr, and optionally write all of them to a file.

    ``level`` is the least important message shown on stderr. The file always gets every
    message, down to ``debug``, so it is the one to attach to a bug report. Calling this again
    replaces the earlier setup. Start-up tokens are never written.

    Raises:
        ValueError: If ``level`` is not one of :data:`LOG_LEVELS`.
        OSError: If the file cannot be opened.
    """
    if level not in LOG_LEVELS:
        raise ValueError(f"level must be one of {', '.join(LOG_LEVELS)}, got {level!r}")
    logger = logging.getLogger(_ROOT)
    for handler in list(logger.handlers):
        if getattr(handler, "cornea_handler", False):
            logger.removeHandler(handler)
            handler.close()

    formatter = _Formatter(_FORMAT)
    shown = getattr(logging, level.upper())
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    handlers[0].setLevel(shown)
    if file is not None:
        target = Path(file)
        target.parent.mkdir(parents=True, exist_ok=True)
        to_file = logging.handlers.RotatingFileHandler(
            target, maxBytes=LOG_FILE_SIZE, backupCount=LOG_FILE_BACKUPS, encoding="utf-8"
        )
        to_file.setLevel(logging.DEBUG)
        handlers.append(to_file)
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.cornea_handler = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if file is not None else shown)
    logger.propagate = False  # the handlers above are the whole setup: no doubled lines


def default_log_file() -> Path:
    """Where debug mode writes its log when nothing else is set up.

    That is ``cornea.log`` in ``%LOCALAPPDATA%\\Cornea\\logs``, which every user can write to,
    whatever folder the program was started from.
    """
    return logs_dir() / "cornea.log"


def _has_handlers(logger: logging.Logger) -> bool:
    """Whether a handler of ``logger`` or of a logger above it would receive its messages."""
    return logger.hasHandlers()


def enable_debug_logging() -> Path | None:
    """Debug mode's logging: do nothing if logging is already set up, otherwise log to a file.

    Logging counts as set up when the ``cornea`` logger, or the root logger, already has a
    handler: the program chose where logs go. Otherwise this shows debug messages on stderr
    and writes them to :func:`default_log_file`, creating the folder. If that file cannot be
    written, debug messages only go to stderr. Returns the file, or ``None`` when no file is
    written.
    """
    if _has_handlers(logging.getLogger(_ROOT)):
        return None
    return start_debug_logging()


def start_debug_logging() -> Path | None:
    """Set up debug logging to the default file, whatever is configured. See above for the rest."""
    logger = logging.getLogger(_ROOT)
    target = default_log_file()
    try:
        configure_logging("debug", file=target)
    except OSError as exc:
        configure_logging("debug")
        logger.debug("Debug mode: cannot write %s (%s); logging to the screen only", target, exc)
        return None
    logger.debug("Debug mode: writing the log to %s", target)
    return target
