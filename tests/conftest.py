import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test under an ``integration`` folder as an integration test."""
    for item in items:
        if "integration" in item.path.parts:
            item.add_marker(pytest.mark.integration)
