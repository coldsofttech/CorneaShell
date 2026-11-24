# Cornea Menus

Menu bars, context menus and title bars for [Cornea Shell](https://github.com/coldsofttech/CorneaShell) pages, in Windows 11, Windows XP, Office, macOS and Ubuntu styles.

Python (or the page) says what the menus are. The page draws them and sends clicks back. Windows draws nothing, so the same menus work in a frameless window and look the same in every theme.

```bash
pip install "cornea-shell[menus]"
```

## Quick start

```python
from cornea import Shell, Static, Window
from cornea_menus import Check, ContextMenu, Item, Menu, MenuBar, Menus, Separator

menus = Menus(
    MenuBar(
        [
            Menu(
                "&File",
                [
                    Item("file.open", "&Open...", shortcut="Ctrl+O"),
                    Separator(),
                    Item("file.quit", "&Quit", shortcut="Ctrl+Q"),
                ],
            ),
            Menu("&View", [Check("view.wrap", "&Word wrap", checked=True)]),
        ]
    ),
    context=[ContextMenu("default", [Item("edit.copy", "Copy", shortcut="Ctrl+C")])],
    theme="win11",
    mode="frame",
)


@menus.on("file.quit")
def quit_app() -> None:
    shell.actions  # do your own thing here


shell = Shell(Static("web/dist"), window=Window(frameless=True), extensions=[menus])
shell.run()
```

`mode="frame"` needs no change to your app: Cornea draws the title bar and menu bar and shows your app below them. Right-clicks, shortcuts and clicks in the app reach the menus on their own.

## In your own page

With `mode="component"` (the default) you put the bars where you want them:

```html
<div id="titlebar"></div>
<div id="menubar"></div>
<script src="/api/menus/menus.js"></script>
<script>
  corneaMenus.mount({ bar: "#menubar", titleBar: "#titlebar" });
  window.addEventListener("cornea:menu-click", (event) => {
    console.log(event.detail.id, event.detail.checked);
  });
</script>
```

Mark an element with `data-cornea-context="editor"` to open the context menu named `editor` on it. The menu named `default` opens everywhere else. The page can also define menus itself with `corneaMenus.set({ bar: [...], context: {...} })` unless you pass `page_can_define=False`.

For React, `cornea-menus/react` has `CorneaMenus`, `MenuBar`, `TitleBar`, `useContextMenu` and `useMenuClick`. It is built from `web/` in this package.

## Entries

| Class | What it is |
| --- | --- |
| `Item(id, label, shortcut=, icon=, enabled=, visible=)` | Does something when chosen |
| `Check(id, label, checked=)` | On or off |
| `Radio(id, label, group=, checked=)` | One of a group |
| `Separator()` | A line |
| `Submenu(label, items)` / `Menu(label, items)` | Opens another menu (up to 4 levels) |

Put `&` before a letter in a label to underline it and make Alt+letter choose it. A shortcut such as `Ctrl+S` or `F5` is shown in the menu and works anywhere in the page. An icon is an address on your app, such as `/icons/save.svg`.

## Changing menus while the app runs

```python
menus.update("file.save", enabled=False)
menus.update("view.wrap", checked=True)
menus.set_context("editor", [Item("edit.cut", "Cut")])
```

The page is told, and redraws.

## Security

- A menu is data. The page never receives code from Python, and the page cannot make Python run anything except the handlers you registered for ids that exist, are enabled and are shown.
- Everything the page sends (a definition or a click) is checked: sizes, depth, ids and icon addresses.
- The script and styles come from Cornea's own address, and styles are plain files, so the strict content security policy needs no change.
- Frame mode lets the page frame its own address (`frame-ancestors 'self'`). Nothing else changes in the policy. If your app sends `X-Frame-Options: DENY` or its own `frame-ancestors 'none'`, the frame stays empty: change it to `SAMEORIGIN` or `'self'`.

## Themes

`win11`, `xp`, `office`, `macos`, `ubuntu`. Colours and sizes are CSS variables (`--cm-*`) on `:root[data-cm-theme="..."]`, so an app can override any of them.

## Building the script

The built script and styles are committed in `src/cornea_menus/static`, so Python users need no Node. To change them:

```bash
cd web
npm install
npm run build      # writes src/cornea_menus/static and web/dist
npm run typecheck
```
