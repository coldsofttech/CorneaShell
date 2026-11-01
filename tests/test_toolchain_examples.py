"""Examples that need an outside tool (Go, PHP, Java, .NET, Node, Streamlit, MkDocs).

Each case runs two ways, the way a reader would: through the Python entry point, and through the
``cornea`` command. A case skips when its tool is missing, so on a developer machine only the
installed ones run. The examples workflow installs everything and runs them all.

Run with: ``uv run pytest -m toolchains --no-cov -rs``
"""

import http.client
import importlib.util
import json
import shutil
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from cornea import Shell

pytestmark = pytest.mark.toolchains

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
STARTUP_SECONDS = 180


@dataclass(frozen=True)
class Case:
    folder: str
    tool: str
    command: str
    """What the cornea command runs; {dir} and {port} are filled in."""
    page: str
    hello: str | None = None
    """Text the /hello?name=Zed answer must contain; None when the example has no such route."""
    python_args: dict[str, Any] = field(default_factory=dict)
    cli_args: tuple[str, ...] = ()
    module: str | None = None
    """A Python module that must be importable, for tools installed with uv."""


CASES = [
    Case(
        "dotnet_server",
        "dotnet",
        "dotnet run --project {dir} --urls http://127.0.0.1:{port}",
        "Hello from .NET",
        "Hello, Zed, from .NET",
    ),
    Case(
        "java_server",
        "java",
        "java Server.java {port}",
        "Hello from Java",
        "Hello, Zed, from Java",
    ),
    Case(
        "php_server",
        "php",
        "php -S 127.0.0.1:{port} -t {dir} {dir}/index.php",
        "Hello from PHP",
        "Hello, Zed, from PHP",
    ),
    Case("go_server", "go", "go run . {port}", "Hello from Go", "Hello, Zed, from Go"),
    Case(
        "node_server",
        "node",
        "node server.js {port}",
        "Hello from Node.js",
        "Hello, Zed, from Node.js",
    ),
    Case(
        "streamlit_app",
        sys.executable,
        "{python} -m streamlit run app.py --server.headless true --server.address 127.0.0.1"
        " --server.port {port} --browser.gatherUsageStats false",
        "Streamlit",
        cli_args=("--csp-profile", "dev"),
        module="streamlit",
    ),
    Case(
        "mkdocs_site",
        sys.executable,
        "{python} -m mkdocs serve -a 127.0.0.1:{port}",
        "Hello from MkDocs",
        python_args={"live": True},
        cli_args=("--csp-profile", "dev"),
        module="mkdocs",
    ),
]


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def get(port: int, path: str, cookie: str = "", origin: str = "") -> tuple[int, str, str]:
    headers = {"Cookie": cookie, "Origin": origin} if cookie else {}
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    try:
        connection.request("GET", path, headers=headers)
        response = connection.getresponse()
        return (
            response.status,
            response.getheader("Set-Cookie") or "",
            response.read().decode(errors="replace"),
        )
    finally:
        connection.close()


def sign_in(port: int, token: str) -> str:
    return get(port, f"/?cornea_token={token}")[1].split(";")[0]


def check(case: Case, port: int, token: str) -> None:
    """The page and the API answer through Cornea's address."""
    cookie = sign_in(port, token)
    origin = f"http://127.0.0.1:{port}"
    status, _, page = get(port, "/", cookie, origin)
    assert status == 200
    assert case.page in page
    if case.hello is not None:
        assert case.hello in get(port, "/hello?name=Zed", cookie, origin)[2]


def sdk_installed() -> bool:
    listing = subprocess.run(
        [shutil.which("dotnet") or "dotnet", "--list-sdks"], capture_output=True, text=True
    )
    return bool(listing.stdout.strip())


@pytest.fixture
def prepared(request: pytest.FixtureRequest) -> Case:
    case: Case = request.param
    if shutil.which(case.tool) is None and case.tool != sys.executable:
        pytest.skip(f"{case.tool} is not installed")
    if case.tool == "dotnet" and not sdk_installed():
        pytest.skip("the .NET SDK is not installed (only a runtime)")
    if case.module is not None and importlib.util.find_spec(case.module) is None:
        pytest.skip(f"{case.module} is not installed (uv sync --group examples)")
    return case


by_case = pytest.mark.parametrize(
    "prepared", CASES, ids=[case.folder for case in CASES], indirect=True
)


@by_case
def test_the_python_entry_point_works_through_the_proxy(prepared: Case) -> None:
    case = prepared
    spec = importlib.util.spec_from_file_location(
        f"toolchain_{case.folder}", EXAMPLES / case.folder / "main.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    port = free_port()
    arguments: dict[str, Any] = {"headless": True, "port": port, **case.python_args}
    if case.folder in {"dotnet_server", "java_server", "php_server", "go_server", "node_server"}:
        arguments["mode"] = "proxy"

    shell: Shell = module.build_shell(**arguments)
    with shell:
        check(case, shell.port, shell.app.state.bootstrap_token)
    with (
        pytest.raises((ConnectionRefusedError, TimeoutError)),
        socket.create_connection(("127.0.0.1", port), timeout=2),
    ):
        pass  # the server stopped with the shell


@by_case
def test_the_cornea_command_works_through_the_proxy(prepared: Case) -> None:
    case = prepared
    port = free_port()
    folder = EXAMPLES / case.folder
    command = case.command.format(dir=folder, port=port, python=sys.executable)
    cornea = shutil.which("cornea") or str(Path(sys.executable).parent / "cornea")
    process = subprocess.Popen(
        [
            cornea,
            "serve",
            "--url",
            f"http://127.0.0.1:{port}",
            "--run",
            command,
            "--run-cwd",
            str(folder),
            "--run-timeout",
            str(STARTUP_SECONDS),
            "--mode",
            "proxy",
            *case.cli_args,
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    watchdog = threading.Timer(STARTUP_SECONDS + 30, process.kill)
    watchdog.start()
    try:
        assert process.stdout is not None
        ready = json.loads(process.stdout.readline())
        check(case, ready["port"], ready["url"].split("cornea_token=")[1])
    finally:
        watchdog.cancel()
        process.terminate()
        process.wait(timeout=30)
