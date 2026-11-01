"""Stand-ins for pywebview, shared by the window tests."""

from collections.abc import Callable
from types import ModuleType, SimpleNamespace
from typing import Any


class FakeEvent:
    def __init__(self) -> None:
        self.handlers: list[Callable[..., None]] = []

    def __iadd__(self, handler: Callable[..., None]) -> "FakeEvent":
        self.handlers.append(handler)
        return self

    def fire(self, *args: Any) -> None:
        for handler in list(self.handlers):
            handler(*args)


class FakeWebViewOptions:
    """Remembers what was set; can be told to fail."""

    fail = False

    def __setattr__(self, name: str, value: object) -> None:
        if FakeWebViewOptions.fail:
            raise RuntimeError("settings not available")
        super().__setattr__(name, value)


class FakeWindow:
    def __init__(self, title: str, url: str, **options: Any) -> None:
        self.title = title
        self.url = url
        self.options = options
        self.calls: list[str] = []
        self.options_object = FakeWebViewOptions()
        self.events = SimpleNamespace(
            maximized=FakeEvent(),
            minimized=FakeEvent(),
            restored=FakeEvent(),
            loaded=FakeEvent(),
            closed=FakeEvent(),
            closing=FakeEvent(),
            shown=FakeEvent(),
            moved=FakeEvent(),
            resized=FakeEvent(),
        )
        core = SimpleNamespace(Settings=self.options_object)
        self.native = SimpleNamespace(webview=SimpleNamespace(CoreWebView2=core))

    def minimize(self) -> None:
        self.calls.append("minimize")

    def maximize(self) -> None:
        self.calls.append("maximize")

    def restore(self) -> None:
        self.calls.append("restore")

    def destroy(self) -> None:
        self.calls.append("destroy")

    def show(self) -> None:
        self.calls.append("show")

    def set_title(self, title: str) -> None:
        self.calls.append(f"title:{title}")


class FakeWebview(ModuleType):
    """Stands in for pywebview: records what is asked and shows no window."""

    def __init__(self) -> None:
        super().__init__("webview")
        self.settings: dict[str, Any] = {"OPEN_DEVTOOLS_IN_DEBUG": True}
        self.windows: list[FakeWindow] = []
        self.start_options: dict[str, Any] = {}
        self.while_open: Callable[[FakeWindow], None] = lambda window: None

    def create_window(self, title: str, url: str, **options: Any) -> FakeWindow:
        window = FakeWindow(title, url, **options)
        self.windows.append(window)
        return window

    def start(self, **options: Any) -> None:
        self.start_options = options
        for window in self.windows:
            window.events.loaded.fire()
            self.while_open(window)
