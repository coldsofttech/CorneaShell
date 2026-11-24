"""Launch requests, and handing them to the running copy."""

import json
import socket
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from cornea import App, LaunchRequest, Shell, Static
from cornea.core.app.appdata import AppData
from cornea.core.security.single_instance import INFO_FILE, InstanceLock, activate_existing


@pytest.fixture
def site(tmp_path: Path) -> Path:
    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    return tmp_path


def unique_id() -> str:
    return f"test.launch.{uuid.uuid4().hex[:12]}"


# ----- the request ------------------------------------------------------------------------------


def test_urls_files_and_other_arguments_are_told_apart(tmp_path: Path, monkeypatch: Any) -> None:
    document = tmp_path / "notes.txt"
    document.write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    request = LaunchRequest.from_args(["myapp://open/42", "notes.txt", "--flag", "missing.txt"])

    assert request.urls == ("myapp://open/42",)
    assert request.files == (str(document.resolve()),)
    assert request.args == ("myapp://open/42", str(document.resolve()), "--flag", "missing.txt")


def test_an_option_is_never_taken_for_a_file(tmp_path: Path, monkeypatch: Any) -> None:
    (tmp_path / "-r").write_text("x", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert LaunchRequest.from_args(["-r"]).files == ()


def test_no_arguments_is_an_empty_request(monkeypatch: Any) -> None:
    monkeypatch.setattr("sys.argv", ["main.py"])

    assert LaunchRequest.from_args() == LaunchRequest()


@pytest.mark.parametrize("args", [["a"] * 65, ["x" * 5000], ["a\0b"]])
def test_odd_arguments_are_refused(args: list[str]) -> None:
    with pytest.raises(ValueError, match=r"arguments|at most"):
        LaunchRequest.from_args(args)


def test_a_request_round_trips_through_json() -> None:
    request = LaunchRequest(("myapp://x",), ("myapp://x",), ())

    assert LaunchRequest.from_json(json.loads(json.dumps(request.as_json()))) == request


@pytest.mark.parametrize(
    "data", [[], "x", {"args": "x"}, {"args": [1]}, {"urls": ["a\0"]}, {"files": ["a"] * 65}]
)
def test_a_bad_request_is_refused(data: Any) -> None:
    with pytest.raises(ValueError, match=r"request|list|arguments|at most"):
        LaunchRequest.from_json(data)


# ----- handing it to the running copy -----------------------------------------------------------


@pytest.fixture
def first() -> Any:
    lock = InstanceLock(unique_id())
    woken: list[Any] = []
    launched: list[LaunchRequest] = []
    lock.serve(lambda: woken.append(1), launched.append)
    try:
        yield lock, woken, launched
    finally:
        lock.release()


def wait_for(items: list[Any], count: int = 1) -> None:
    deadline = time.monotonic() + 3
    while len(items) < count and time.monotonic() < deadline:
        time.sleep(0.01)


def test_a_second_copy_hands_over_its_arguments(first: Any) -> None:
    lock, woken, launched = first
    request = LaunchRequest(("myapp://open/42",), ("myapp://open/42",), ())

    assert activate_existing(lock.app_id, request) is True
    wait_for(launched)

    assert woken == [1]
    assert launched == [request]


def test_waking_without_arguments_does_not_launch(first: Any) -> None:
    lock, woken, launched = first

    assert activate_existing(lock.app_id) is True

    assert woken == [1]
    assert launched == []


def test_a_handler_that_raises_does_not_stop_the_next_one() -> None:
    lock = InstanceLock(unique_id())
    calls: list[int] = []

    def boom(request: LaunchRequest) -> None:
        calls.append(1)
        raise RuntimeError("x")

    lock.serve(lambda: None, boom)
    try:
        assert activate_existing(lock.app_id, LaunchRequest(("a",))) is True
        assert activate_existing(lock.app_id, LaunchRequest(("a",))) is True
    finally:
        lock.release()

    assert calls == [1, 1]


def test_a_launch_needs_the_secret(first: Any) -> None:
    lock, woken, launched = first
    path = AppData.data_dir(lock.app_id) / INFO_FILE
    info = json.loads(path.read_text(encoding="utf-8"))
    info["secret"] = "guessed"  # noqa: S105
    path.write_text(json.dumps(info), encoding="utf-8")

    assert activate_existing(lock.app_id, LaunchRequest(("a",))) is False

    assert woken == [] and launched == []  # noqa: PT018


def test_a_damaged_body_is_ignored(first: Any) -> None:
    lock, woken, launched = first
    info = json.loads((AppData.data_dir(lock.app_id) / INFO_FILE).read_text(encoding="utf-8"))

    with socket.create_connection(("127.0.0.1", info["port"]), 2) as client:
        client.sendall(f"LAUNCH {info['secret']} not json\n".encode())
        assert client.makefile("r").readline() == ""

    assert woken == [] and launched == []  # noqa: PT018


# ----- the shell --------------------------------------------------------------------------------


def test_handlers_and_the_page_hear_a_launch(site: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shell = Shell(Static(site), window=None)
    heard: list[LaunchRequest] = []
    shell.on_launch(heard.append)

    @shell.on_launch
    def broken(request: LaunchRequest) -> None:
        raise RuntimeError("x")

    sent: list[Any] = []
    monkeypatch.setattr(shell, "notify", lambda event, detail=None: sent.append((event, detail)))
    request = LaunchRequest(("myapp://x",), ("myapp://x",), ())

    shell._launched(request)

    assert heard == [request]
    assert sent == []  # the page is only told when launch_events is on


def test_the_page_is_told_with_launch_events(site: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shell = Shell(
        Static(site), identity=App(id="a", single_instance=True, launch_events=True), loading=None
    )
    sent: list[Any] = []
    monkeypatch.setattr(shell, "notify", lambda event, detail=None: sent.append((event, detail)))

    shell._launched(LaunchRequest(("myapp://x",), ("myapp://x",), ()))

    assert sent == [("launch", {"args": ["myapp://x"], "urls": ["myapp://x"], "files": []})]


def test_launch_events_need_single_instance() -> None:
    with pytest.raises(ValueError, match="single_instance"):
        App(id="a", launch_events=True)


def test_a_second_start_forwards_its_arguments(site: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    given: list[Any] = []
    monkeypatch.setattr(InstanceLock, "acquire", lambda self: False)
    monkeypatch.setattr(
        "cornea.core.shell.activate_existing",
        lambda app_id, launch=None: given.append(launch) or True,
    )
    monkeypatch.setattr("sys.argv", ["main.py", "myapp://open/7"])
    shell = Shell(Static(site), identity=App(id="a", single_instance=True))

    with pytest.raises(Exception, match="already running"):
        shell._take_lock()

    assert given[0].urls == ("myapp://open/7",)


def test_a_second_start_without_arguments_only_wakes(
    site: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    given: list[Any] = []
    monkeypatch.setattr(InstanceLock, "acquire", lambda self: False)
    monkeypatch.setattr(
        "cornea.core.shell.activate_existing",
        lambda app_id, launch=None: given.append(launch) or True,
    )
    monkeypatch.setattr("sys.argv", ["main.py"])

    with pytest.raises(Exception, match="already running"):
        Shell(Static(site), identity=App(id="a", single_instance=True))._take_lock()

    assert given == [None]


def test_the_shell_reads_its_own_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["main.py", "myapp://a"])

    assert Shell(window=None).launch.urls == ("myapp://a",)
