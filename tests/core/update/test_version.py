import pytest

from cornea.core.update.version import is_newer, parse_version


@pytest.mark.parametrize(
    ("newer", "older"),
    [
        ("1.4.0", "1.3.9"),
        ("v1.10", "1.9.9"),
        ("2.0", "1.99.99"),
        ("1.5.0", "1.5.0rc1"),
        ("1.5.0rc2", "1.5.0rc1"),
        ("1.5.0rc1", "1.5.0b3"),
        ("1.0.1", "1.0"),
    ],
)
def test_ordering(newer: str, older: str) -> None:
    assert is_newer(newer, older)
    assert not is_newer(older, newer)


def test_trailing_zeros_are_the_same_version() -> None:
    assert parse_version("1.0") == parse_version("1.0.0")
    assert not is_newer("1.4", "1.4.0")


@pytest.mark.parametrize("text", ["", "abc", "1..2", "1.2.x", "latest"])
def test_rejects_non_versions(text: str) -> None:
    with pytest.raises(ValueError, match="not a version"):
        parse_version(text)
