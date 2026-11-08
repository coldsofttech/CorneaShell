"""``import cornea`` must stay cheap: the server libraries load only when they are needed."""

import subprocess
import sys

import pytest

HEAVY = ("fastapi", "starlette", "uvicorn", "pydantic", "typer", "rich")


def _loaded_after(code: str) -> set[str]:
    """Which heavy top-level packages a fresh interpreter has loaded after running ``code``."""
    script = f"import sys\n{code}\nprint(*sorted(m for m in {HEAVY!r} if m in sys.modules))"
    result = subprocess.run(
        [sys.executable, "-I", "-c", script], capture_output=True, text=True, check=True
    )
    return set(result.stdout.split())


def test_import_cornea_does_not_load_the_server() -> None:
    assert _loaded_after("import cornea") == set()


def test_settings_and_sources_stay_light() -> None:
    code = "from cornea import Window, Security, Bridge, Static, Asgi, configure_logging"
    assert _loaded_after(code) == set()


def test_core_packages_stay_light() -> None:
    code = (
        "import cornea.core.app, cornea.core.bridge, cornea.core.security,"
        " cornea.core.sources, cornea.core.window, cornea.core.page"
    )
    assert _loaded_after(code) == set()


@pytest.mark.parametrize(
    "name", ["Shell", "run", "Timings", "ready_line", "AppFactory", "create_app"]
)
def test_server_names_load_on_first_use(name: str) -> None:
    assert "fastapi" in _loaded_after(f"import cornea\ncornea.{name}")


def test_lazy_names_are_listed_and_unknown_names_fail() -> None:
    script = (
        "import cornea\n"
        "assert {'Shell', 'run', 'create_app', 'preload'} <= set(dir(cornea))\n"
        "try:\n    cornea.nope\nexcept AttributeError:\n    print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", script], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "ok"


def test_importing_the_cli_does_not_load_the_server() -> None:
    code = "from cornea.cli import commands"
    assert _loaded_after(code) <= {"typer", "rich"}
    assert "fastapi" not in _loaded_after(code)


def test_preload_loads_the_server_in_the_background() -> None:
    code = "import cornea\ncornea.preload().join()"
    assert "fastapi" in _loaded_after(code)
    assert "uvicorn" in _loaded_after(code)


def test_preload_is_started_once() -> None:
    from cornea.core.preload import preload

    assert preload() is preload()
