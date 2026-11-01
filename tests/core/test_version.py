import cornea


def test_version_is_defined() -> None:
    assert isinstance(cornea.__version__, str)
