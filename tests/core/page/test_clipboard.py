"""The opt-in clipboard actions."""

import asyncio
import sys
from typing import Any

import pytest

from cornea import Bridge, Shell, Static
from cornea.core.bridge import ActionRegistry, BuiltinActions
from cornea.core.page.clipboard import MAX_TEXT, Clipboard, ClipboardError


class FakeClipboard:
    def __init__(self) -> None:
        self.text: str | None = None
        self.fail = False

    def read(self) -> str | None:
        if self.fail:
            raise ClipboardError("the clipboard is in use by another program")
        return self.text

    def write(self, text: str) -> None:
        if self.fail:
            raise ClipboardError("the clipboard is in use by another program")
        self.text = text


@pytest.fixture
def clipboard(monkeypatch: pytest.MonkeyPatch) -> FakeClipboard:
    fake = FakeClipboard()
    monkeypatch.setattr(BuiltinActions, "_windows", lambda: True)
    monkeypatch.setattr(Clipboard, "read", staticmethod(fake.read))
    monkeypatch.setattr(Clipboard, "write", staticmethod(fake.write))
    return fake


def invoke(name: str, arguments: dict[str, Any]) -> tuple[int, Any]:
    registry = ActionRegistry(clipboard=True)
    return asyncio.run(registry.invoke(name, arguments, None))


# ----- off by default ---------------------------------------------------------------------------


def test_the_actions_are_off_by_default() -> None:
    assert not {"clipboard_read", "clipboard_write"} & set(ActionRegistry().names())
    assert Bridge().clipboard is False


def test_the_bridge_setting_turns_them_on(tmp_path: Any) -> None:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")

    shell = Shell(Static(tmp_path), window=None, bridge=Bridge(clipboard=True))

    assert {"clipboard_read", "clipboard_write"} <= set(shell.actions.names())


def test_a_disabled_action_stays_off_even_with_the_flag() -> None:
    names = ActionRegistry(["clipboard_write"], clipboard=True).names()

    assert "clipboard_read" in names
    assert "clipboard_write" not in names


def test_calling_one_that_is_off_is_an_unknown_action() -> None:
    status, _ = asyncio.run(ActionRegistry().invoke("clipboard_read", {}, None))

    assert status == 404


# ----- the actions ------------------------------------------------------------------------------


def test_text_is_written_and_read_back(clipboard: FakeClipboard) -> None:
    status, body = invoke("clipboard_write", {"text": "héllo\nworld"})

    assert (status, body["result"]) == (200, {"written": True})
    assert invoke("clipboard_read", {})[1]["result"] == {"text": "héllo\nworld"}


def test_an_empty_string_can_be_written(clipboard: FakeClipboard) -> None:
    invoke("clipboard_write", {"text": ""})

    assert clipboard.text == ""


def test_a_clipboard_without_text_reads_as_none(clipboard: FakeClipboard) -> None:
    assert invoke("clipboard_read", {})[1]["result"] == {"text": None}


@pytest.mark.parametrize("text", [5, None, ["a"], "a\0b", "x" * (MAX_TEXT + 1)])
def test_bad_text_is_refused(clipboard: FakeClipboard, text: object) -> None:
    status, _ = invoke("clipboard_write", {"text": text})

    assert status == 422
    assert clipboard.text is None


def test_text_is_required(clipboard: FakeClipboard) -> None:
    assert invoke("clipboard_write", {})[0] == 422


def test_a_busy_clipboard_is_not_available(clipboard: FakeClipboard) -> None:
    clipboard.fail = True

    for name, arguments in (("clipboard_read", {}), ("clipboard_write", {"text": "x"})):
        status, body = invoke(name, arguments)
        assert (status, body["available"]) == (200, False)
        assert "another program" in body["reason"]


@pytest.mark.skipif(sys.platform == "win32", reason="checks other systems")
def test_other_systems_answer_not_available() -> None:
    for name, arguments in (("clipboard_read", {}), ("clipboard_write", {"text": "x"})):
        status, body = invoke(name, arguments)
        assert (status, body["available"]) == (200, False)
        assert "only works on Windows" in body["reason"]


@pytest.mark.skipif(sys.platform == "win32", reason="checks other systems")
def test_the_clipboard_itself_needs_windows() -> None:
    with pytest.raises(RuntimeError, match="only works on Windows"):
        Clipboard.read()
