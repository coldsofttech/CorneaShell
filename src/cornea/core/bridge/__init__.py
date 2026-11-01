"""The native bridge: a short allowlist of native actions the page can call."""

from cornea.core.bridge.bridge import (
    ActionRegistry,
    BadArguments,
    BuiltinActions,
    UnknownAction,
)

__all__ = ["ActionRegistry", "BadArguments", "BuiltinActions", "UnknownAction"]
