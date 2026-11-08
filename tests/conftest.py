import pytest
from rich.console import Console


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test under an ``integration`` folder as an integration test."""
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def plain_console_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give the CLI plain-text consoles, whatever the terminal or environment ran pytest.

    The shared consoles decide on color when they are created, at import time, so a color-forcing
    environment (or an earlier test turning color off) would otherwise leak ANSI codes into output.
    """
    from cornea.cli import output

    monkeypatch.setattr(output, "console", Console(force_terminal=False, color_system=None))
    monkeypatch.setattr(
        output, "err_console", Console(stderr=True, force_terminal=False, color_system=None)
    )
