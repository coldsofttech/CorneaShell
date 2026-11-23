import sys

import pytest

from cornea.core.window.tray import Win32Backend

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="needs the Windows shell")


def test_a_real_icon_can_be_added_renamed_and_removed() -> None:
    backend = Win32Backend()
    events: list[str] = []

    backend.start("Cornea test", None, events.append)
    try:
        assert backend._hwnd is not None
        backend.set_tooltip("Cornea test, renamed")
    finally:
        backend.stop()

    assert backend._hwnd is None
    assert backend._thread is not None
    assert not backend._thread.is_alive()
