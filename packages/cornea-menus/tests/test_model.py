"""What a menu may contain, whether Python or the page wrote it."""

from typing import Any

import pytest

from cornea_menus import Check, Item, Menu, MenuBar, MenuError, Radio, Separator, Submenu
from cornea_menus.model import MAX_DEPTH, MAX_ENTRIES, normalise


def bar(*entries: object) -> list[dict[str, Any]]:
    return normalise([Menu("&File", list(entries))], bar=True)


def test_an_entry_is_completed_with_its_defaults() -> None:
    [menu] = bar(Item("file.new", "New"))
    assert menu["items"] == [
        {"type": "item", "id": "file.new", "label": "New", "enabled": True, "visible": True}
    ]


def test_the_page_sends_the_same_shape_python_builds() -> None:
    built = normalise(
        MenuBar([Menu("File", [Item("a", "A", shortcut="Ctrl+A")])]).to_nodes(), bar=True
    )
    sent = normalise(
        [
            {
                "type": "submenu",
                "label": "File",
                "items": [{"type": "item", "id": "a", "label": "A", "shortcut": "Ctrl+A"}],
            }
        ],
        bar=True,
    )
    assert built == sent


@pytest.mark.parametrize(
    "entry",
    [
        {"type": "nope", "label": "x"},
        {"type": "item", "label": "x"},  # no id
        {"type": "item", "id": "1bad", "label": "x"},
        {"type": "item", "id": "a b", "label": "x"},
        {"type": "item", "id": "a", "label": ""},
        {"type": "item", "id": "a", "label": "x" * 81},
        {"type": "item", "id": "a", "label": "line\nbreak"},
        {"type": "item", "id": "a", "label": "x", "enabled": "yes"},
        {"type": "item", "id": "a", "label": "x", "onclick": "alert(1)"},
        {"type": "item", "id": "a", "label": "x", "icon": "https://evil.example/x.png"},
        {"type": "item", "id": "a", "label": "x", "icon": "//evil.example/x.png"},
        {"type": "item", "id": "a", "label": "x", "icon": "/a/../b.png"},
        {"type": "item", "id": "a", "label": "x", "icon": "javascript:alert(1)"},
        {"type": "item", "id": "a", "label": "x", "shortcut": "<script>"},
        {"type": "radio", "id": "a", "label": "x"},  # no group
        {"type": "check", "id": "a", "label": "x", "checked": 1},
        "not an object",
    ],
)
def test_an_entry_that_is_not_allowed_is_refused(entry: object) -> None:
    with pytest.raises(MenuError):
        normalise([{"type": "submenu", "label": "M", "items": [entry]}], bar=True)


def test_the_bar_holds_menus_not_single_entries() -> None:
    with pytest.raises(MenuError, match="menus"):
        normalise([Item("a", "A")], bar=True)


def test_an_id_is_used_once() -> None:
    with pytest.raises(MenuError, match="twice"):
        bar(Item("a", "A"), Submenu("More", [Item("a", "B")]))


def test_ids_are_unique_across_menus_that_share_the_used_set() -> None:
    used: set[str] = set()
    normalise([Item("a", "A")], used=used)
    with pytest.raises(MenuError, match="twice"):
        normalise([Item("a", "B")], used=used)


def test_menus_nest_only_so_far() -> None:
    inner: Submenu = Submenu("deepest", [Item("leaf", "Leaf")])
    for level in range(MAX_DEPTH - 1):
        inner = Submenu(f"level{level}", [inner])
    with pytest.raises(MenuError, match="nest"):
        normalise([inner], bar=True)


def test_a_menu_has_a_limited_number_of_entries() -> None:
    entries = [Item(f"i{n}", "x") for n in range(MAX_ENTRIES + 1)]
    with pytest.raises(MenuError, match="at most"):
        bar(*entries)


def test_only_the_first_checked_radio_of_a_group_stays_on() -> None:
    [menu] = bar(
        Radio("a", "A", group="g", checked=True),
        Radio("b", "B", group="g", checked=True),
        Radio("c", "C", group="h", checked=True),
    )
    assert [entry["checked"] for entry in menu["items"]] == [True, False, True]


def test_a_separator_takes_no_fields() -> None:
    assert bar(Separator())[0]["items"] == [{"type": "separator"}]
    with pytest.raises(MenuError):
        normalise(
            [{"type": "submenu", "label": "M", "items": [{"type": "separator", "label": "x"}]}],
            bar=True,
        )


def test_check_and_radio_start_unchecked() -> None:
    [menu] = bar(Check("c", "C"), Radio("r", "R", group="g"))
    assert [entry["checked"] for entry in menu["items"]] == [False, False]
