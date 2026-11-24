"""The hook that lets an optional package (such as ``cornea-menus``) add to a shell."""

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from fastapi import APIRouter

    from cornea.core.shell import Shell


class Extension(Protocol):
    """What an optional package gives a :class:`~cornea.core.shell.Shell`.

    Pass instances with ``Shell(..., extensions=[...])``. The shell mounts their routes under
    the API prefix, opens the window on their start path, allows framing when asked, and calls
    :meth:`bind` once the shell exists.
    """

    @property
    def allows_framing(self) -> bool:
        """Whether the extension shows the app in a frame of its own page. Cornea then lets the
        page frame its own address (``frame-ancestors 'self'``) instead of refusing every frame."""
        ...

    def routers(self) -> Iterable["APIRouter"]:
        """Routes to mount under the API prefix."""
        ...

    def start_path(self, api_prefix: str) -> str:
        """The path the window opens first, such as ``/`` or ``/api/menus/frame``."""
        ...

    def bind(self, shell: "Shell") -> None:
        """Called once, right after the shell is built."""
        ...
