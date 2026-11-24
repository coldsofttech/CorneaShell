"""What :class:`Menus` does with a definition, an update and a click."""

import logging

import pytest

from cornea_menus import (
    Check,
    ContextMenu,
    Item,
    Menu,
    MenuBar,
    MenuClick,
    MenuError,
    Menus,
    Radio,
    Separator,
    Submenu,
)


def make() -> Menus:
    return Menus(
        MenuBar(
            [
                Menu(
                    "&File",
                    [Item("file.save", "Save"), Submenu("Recent", [Item("recent.a", "a.txt")])],
                ),
                Menu(
                    "&View",
                    [
                        Check("view.wrap", "Wrap"),
                        Radio("s.small", "S", group="s"),
                        Radio("s.large", "L", group="s", checked=True),
                    ],
                ),
            ]
        ),
        context=[ContextMenu("editor", [Item("edit.copy", "Copy")])],
    )


def test_it_validates_its_settings() -> None:
    with pytest.raises(ValueError, match="theme"):
        Menus(theme="vista")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="mode"):
        Menus(mode="popup")  # type: ignore[arg-type]
    for path in ("app", "//evil.example", "/\\x"):
        with pytest.raises(ValueError, match="app_path"):
            Menus(app_path=path)


def test_the_definition_carries_what_the_page_needs() -> None:
    menus = make()
    definition = menus.definition()
    assert definition["theme"] == "win11"
    assert [m["label"] for m in definition["bar"]] == ["&File", "&View"]
    assert list(definition["context"]) == ["editor"]


def test_a_bad_definition_changes_nothing() -> None:
    menus = make()
    before = menus.definition()["version"]
    with pytest.raises(MenuError):
        menus.define([Menu("X", [Item("a", "A"), Item("a", "B")])])
    assert menus.definition()["version"] == before
    assert len(menus.definition()["bar"]) == 2


def test_context_menu_names_are_checked() -> None:
    with pytest.raises(MenuError, match="name"):
        Menus(context={"bad name": [Item("a", "A")]})


def test_ids_are_unique_between_the_bar_and_context_menus() -> None:
    with pytest.raises(MenuError, match="twice"):
        Menus([Menu("F", [Item("a", "A")])], context={"c": [Item("a", "A again")]})


def test_set_context_adds_replaces_and_removes() -> None:
    menus = make()
    menus.set_context("tab", [Item("tab.close", "Close")])
    assert set(menus.definition()["context"]) == {"editor", "tab"}
    menus.set_context("tab", None)
    assert set(menus.definition()["context"]) == {"editor"}
    menus.set_bar(None)
    assert menus.definition()["bar"] == []
    assert "editor" in menus.definition()["context"]


def test_update_changes_an_entry_and_bumps_the_version() -> None:
    menus = make()
    before = menus.definition()["version"]
    menus.update("file.save", enabled=False, label="Save &As")
    entry = menus.entry("file.save")
    assert entry["enabled"] is False
    assert entry["label"] == "Save &As"
    assert menus.definition()["version"] > before


def test_update_refuses_what_is_not_allowed() -> None:
    menus = make()
    with pytest.raises(KeyError):
        menus.update("nope", enabled=False)
    with pytest.raises(MenuError):
        menus.update("file.save", checked=True)  # not a check entry
    with pytest.raises(MenuError):
        menus.update("file.save", label="")
    assert menus.entry("file.save")["label"] == "Save"


def test_update_can_change_a_submenu_without_losing_its_entries() -> None:
    menus = Menus([Menu("&File", [Submenu("Recent", [Item("recent.a", "a")], id="recent")])])
    menus.update("recent", enabled=False)
    assert menus.entry("recent")["items"][0]["id"] == "recent.a"


def test_choosing_a_radio_entry_turns_the_others_in_its_group_off() -> None:
    menus = make()
    menus.update("s.small", checked=True)
    assert menus.entry("s.small")["checked"] is True
    assert menus.entry("s.large")["checked"] is False


def test_a_click_runs_the_handlers_after_the_state_changed() -> None:
    menus = make()
    seen: list[MenuClick] = []
    order: list[str] = []

    @menus.on("view.wrap")
    def wrapped(click: MenuClick) -> None:
        seen.append(click)
        order.append(f"wrap={menus.entry('view.wrap')['checked']}")

    @menus.on("view.wrap")
    def no_arguments() -> None:
        order.append("second")

    @menus.on_click
    def everything(click: MenuClick) -> None:
        order.append(f"any:{click.id}")

    result = menus.click("view.wrap")
    assert result == {"ok": True, "id": "view.wrap", "checked": True, "menu": None}
    assert seen == [MenuClick("view.wrap", True, None)]
    assert order == ["wrap=True", "second", "any:view.wrap"]
    assert menus.click("view.wrap")["checked"] is False


def test_a_radio_click_is_always_on() -> None:
    menus = make()
    assert menus.click("s.small")["checked"] is True
    assert menus.entry("s.large")["checked"] is False
    assert menus.click("s.small")["checked"] is True


def test_a_context_menu_entry_is_found_only_in_its_menu() -> None:
    menus = make()
    assert menus.click("edit.copy", "editor")["menu"] == "editor"
    with pytest.raises(KeyError):
        menus.click("edit.copy")  # it is not in the bar
    with pytest.raises(KeyError):
        menus.click("edit.copy", "other")


@pytest.mark.parametrize("ident", ["nope", "recent", "file.save"])
def test_an_entry_that_cannot_be_chosen_is_refused(ident: str) -> None:
    menus = Menus(
        [
            Menu(
                "&File",
                [
                    Item("file.save", "Save", enabled=False),
                    Submenu("Recent", [Item("r", "r")], id="recent"),
                    Item("hidden", "H", visible=False),
                ],
            )
        ]
    )
    with pytest.raises(KeyError):
        menus.click(ident)
    with pytest.raises(KeyError):
        menus.click("hidden")


def test_a_failing_handler_is_logged_and_does_not_fail_the_click(
    caplog: pytest.LogCaptureFixture,
) -> None:
    menus = make()
    ran: list[str] = []

    @menus.on("file.save")
    def broken() -> None:
        raise RuntimeError("boom")

    @menus.on_click
    def after(click: MenuClick) -> None:
        ran.append(click.id)

    with caplog.at_level(logging.ERROR):
        assert menus.click("file.save")["ok"] is True
    assert ran == ["file.save"]
    assert "file.save" in caplog.text


def test_the_page_defines_menus_when_allowed() -> None:
    menus = Menus()
    menus.define_from_page(
        {
            "bar": [
                {
                    "type": "submenu",
                    "label": "F",
                    "items": [{"type": "item", "id": "x", "label": "X"}],
                }
            ],
            "context": {"default": [{"type": "item", "id": "y", "label": "Y"}]},
        }
    )
    assert menus.entry("x")["label"] == "X"
    assert list(menus.definition()["context"]) == ["default"]


def test_the_page_may_be_refused_the_right_to_define_menus() -> None:
    menus = Menus(page_can_define=False)
    with pytest.raises(PermissionError):
        menus.define_from_page({"bar": []})


@pytest.mark.parametrize(
    "raw", [[], "x", {"bar": "x"}, {"bar": [], "context": []}, {"bar": [], "context": {"c": "x"}}]
)
def test_a_malformed_page_definition_is_refused(raw: object) -> None:
    with pytest.raises(MenuError):
        Menus().define_from_page(raw)


def test_it_tells_the_shell_when_menus_change() -> None:
    class FakeShell:
        def __init__(self) -> None:
            self.sent: list[tuple[str, object]] = []

        def notify(self, event: str, detail: object = None) -> None:
            self.sent.append((event, detail))

    menus = make()
    shell = FakeShell()
    menus.bind(shell)  # type: ignore[arg-type]
    menus.update("file.save", enabled=False)
    assert shell.sent == [("menu-changed", {"version": menus.definition()["version"]})]


def test_frame_mode_names_its_own_start_page_and_allows_framing() -> None:
    assert Menus().allows_framing is False
    assert Menus().start_path("/api") == "/"
    framed = Menus(mode="frame")
    assert framed.allows_framing is True
    assert framed.start_path("/api") == "/api/menus/frame"


def test_a_separator_between_entries_is_kept_in_the_definition() -> None:
    menus = Menus([Menu("F", [Item("a", "A"), Separator(), Item("b", "B")])])
    assert [e["type"] for e in menus.definition()["bar"][0]["items"]] == [
        "item",
        "separator",
        "item",
    ]
