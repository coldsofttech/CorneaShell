#!/usr/bin/env python3
"""Generate docs/api-reference.md from the public API in ``cornea.__all__``.

Usage: uv run python scripts/gen_api_reference.py [output]
CI regenerates the file and fails if it differs from the committed copy.
"""

import ast
import dataclasses
import importlib
import inspect
import pkgutil
import re
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any

import cornea
import cornea.core

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "api-reference.md"
MAX_DEFAULT = 40


def type_name(annotation: Any) -> str:
    if isinstance(annotation, type):
        return annotation.__name__
    text = re.sub(r"\b(?:typing|collections\.abc|pathlib)\.", "", str(annotation))
    return re.sub(r"Callable\[.*\]", "Callable[...]", text)


def signature_text(function: Any) -> str:
    """Signature without ``self``, with module prefixes and long callables shortened."""
    text = re.sub(r"\b(?:typing|collections\.abc|pathlib)\.", "", str(inspect.signature(function)))
    text = re.sub(r"Callable\[.*\]", "Callable[...]", text)
    return text.replace("(self, ", "(").replace("(self)", "()")


def default_text(field: "dataclasses.Field[Any]") -> str:
    if field.default is not dataclasses.MISSING:
        text = repr(field.default)
    elif field.default_factory is not dataclasses.MISSING:
        text = repr(field.default_factory())
    else:
        return "required"
    return text if len(text) <= MAX_DEFAULT else text[: MAX_DEFAULT - 1] + "…"


def attribute_docs(cls: type) -> dict[str, str]:
    """Map attribute names to the string literal that follows them in the class body."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    docs: dict[str, str] = {}
    body = tree.body[0]
    assert isinstance(body, ast.ClassDef)  # noqa: S101
    for current, following in zip(body.body, body.body[1:], strict=False):
        if (
            isinstance(current, ast.AnnAssign)
            and isinstance(current.target, ast.Name)
            and isinstance(following, ast.Expr)
            and isinstance(following.value, ast.Constant)
            and isinstance(following.value.value, str)
        ):
            text = " ".join(inspect.cleandoc(following.value.value).split())
            docs[current.target.id] = markdown(text)
    return docs


def example_block(obj: object) -> list[str]:
    """Lines of the docstring's ``Example:`` section, dedented, or an empty list."""
    lines = (inspect.getdoc(obj) or "").splitlines()
    for index, line in enumerate(lines):
        if line.strip() in {"Example:", "Examples:"}:
            block = []
            for following in lines[index + 1 :]:
                if following.strip() and not following.startswith(" "):
                    break
                block.append(following)
            lines = textwrap.dedent("\n".join(block)).strip().splitlines()
            # Doctest directives are for the test run, not for the reader.
            return [re.sub(r"\s+# doctest: .*$", "", line) for line in lines]
    return []


def render_example(obj: object) -> list[str]:
    example = example_block(obj)
    return ["", "Example:", "", "```pycon", *example, "```"] if example else []


def tidy(text: str) -> str:
    """Drop module prefixes (``fastapi.routing.APIRouter`` -> ``APIRouter``) and string quotes."""
    text = re.sub(r"\b(?:[a-z_][a-z_0-9]*\.)+(?=[A-Z])", "", text)
    return text


def markdown(text: str) -> str:
    """Turn the docstring's reStructuredText inline markup into Markdown."""
    text = re.sub(r":\w+:`~?([^`]+)`", r"`\1`", text)
    return re.sub(r"``([^`]+)``", r"`\1`", text)


def first_paragraph(obj: object) -> str:
    return markdown(" ".join((inspect.getdoc(obj) or "").split("\n\n")[0].split()))


def escape(text: str) -> str:
    return text.replace("|", "\\|")


def render_dataclass(cls: type) -> list[str]:
    lines = [f"## `{cls.__name__}`", "", body_text(cls), ""]
    docs = attribute_docs(cls)
    fields = dataclasses.fields(cls)
    if fields:
        lines += ["| Parameter | Type | Default | Description |", "| --- | --- | --- | --- |"]
    for field in fields:
        lines.append(
            f"| `{field.name}` | `{escape(type_name(field.type))}` | "
            f"`{escape(default_text(field))}` | {escape(docs.get(field.name, ''))} |"
        )
    return [*lines, *member_lines(cls), *render_example(cls), ""]


def member_lines(cls: type) -> list[str]:
    """The public properties and methods a class defines, as Markdown lists."""
    lines: list[str] = []
    properties = [
        (name, member)
        for name, member in vars(cls).items()
        if isinstance(member, property) and not name.startswith("_")
    ]
    if properties:
        lines += ["", "Properties:", ""]
        lines += [f"- `{name}`: {first_paragraph(member)}" for name, member in properties]
    methods = [
        (name, member)
        for name, member in vars(cls).items()
        if inspect.isfunction(member) and not name.startswith("_")
    ]
    for name, member in methods:
        lines += [
            "",
            f"### `{cls.__name__}.{name}`",
            "",
            "```python",
            signature_block(member, name=f"{cls.__name__}.{name}"),
            "```",
            "",
            body_text(member),
            *render_example(member),
        ]
    return lines


def render_class(cls: type) -> list[str]:
    """A regular (non-dataclass) class: its constructor, description and members."""
    return [
        f"## `{cls.__name__}`",
        "",
        "```python",
        signature_block(cls, prefix=""),
        "```",
        "",
        body_text(cls),
        *member_lines(cls),
        *render_example(cls),
        "",
    ]


def body_text(obj: object) -> str:
    """The docstring without its ``Example:`` section, as Markdown."""
    lines = (inspect.getdoc(obj) or "").splitlines()
    for index, line in enumerate(lines):
        if line.strip() in {"Example:", "Examples:"}:
            lines = lines[:index]
            break
    return markdown(sections("\n".join(lines).strip()))


def sections(text: str) -> str:
    """Turn a ``Raises:`` block into a Markdown list: one bullet per exception."""
    out: list[str] = []
    in_raises = False
    for line in text.splitlines():
        if line.strip() == "Raises:":
            out += ["**Raises:**", ""]
            in_raises = True
        elif in_raises and line.startswith("    ") and not line.startswith("     "):
            name, _, rest = line.strip().partition(":")
            out.append(f"- `{name}`:{rest}")
        elif in_raises and line.startswith("     "):
            out[-1] += " " + line.strip()
        else:
            in_raises = False
            out.append(line)
    return "\n".join(out)


def parameter_text(parameter: inspect.Parameter) -> str:
    """One parameter; a dataclass default that is all defaults is shown as ``Name()``."""
    text = tidy(str(parameter))
    default = parameter.default
    if dataclasses.is_dataclass(default) and not isinstance(default, type):
        cls = type(default)
        if default == cls():
            text = text.replace(repr(default), f"{cls.__name__}()")
    return text


def signature_block(function: Any, prefix: str = "def ", name: str | None = None) -> str:
    """A ``def`` block with one parameter per line, module paths and quotes removed.

    ``name`` is the public name, for a function that is exported under another name.
    """
    name = name or function.__name__
    signature = inspect.signature(function)
    shown = [p for p in signature.parameters.values() if p.name != "self"]
    params = [parameter_text(parameter) for parameter in shown]
    kinds = [parameter.kind for parameter in shown]
    if inspect.Parameter.KEYWORD_ONLY in kinds and inspect.Parameter.VAR_POSITIONAL not in kinds:
        params.insert(kinds.index(inspect.Parameter.KEYWORD_ONLY), "*")
    returns = ""
    if prefix and signature.return_annotation is not inspect.Signature.empty:
        returns = f" -> {tidy(type_name(signature.return_annotation))}"
    if not params:
        return f"{prefix}{name}(){returns}"
    inner = ",\n".join(f"    {param}" for param in params)
    return f"{prefix}{name}(\n{inner},\n){returns}"


def render_callable(obj: Any, name: str) -> list[str]:
    """A function or method, shown under the name ``cornea`` exports it as."""
    lines = [
        f"## `{name}`",
        "",
        "```python",
        signature_block(obj, name=name),
        "```",
        "",
        body_text(obj),
        *render_example(obj),
        "",
    ]
    # A method exported as a function (create_app = AppFactory.create) shows its public name.
    return [line.replace(f"{obj.__qualname__}(", f"{name}(") for line in lines]


def constant_doc(name: str) -> str:
    """The string literal that follows ``NAME = ...`` in any ``cornea.core`` module."""
    for info in pkgutil.walk_packages(cornea.core.__path__, "cornea.core."):
        module = importlib.import_module(info.name)
        tree = ast.parse(inspect.getsource(module))
        for current, following in zip(tree.body, tree.body[1:], strict=False):
            names = [t.id for t in getattr(current, "targets", []) if isinstance(t, ast.Name)]
            if (
                name in names
                and isinstance(following, ast.Expr)
                and isinstance(following.value, ast.Constant)
                and isinstance(following.value.value, str)
            ):
                return markdown(" ".join(inspect.cleandoc(following.value.value).split()))
    return ""


def render_constant(name: str, value: str) -> list[str]:
    """A documented string constant, with its value one clause per line."""
    clauses = [clause.strip() for clause in value.split(";")]
    shown = ";\n".join(clauses)
    return [f"## `{name}`", "", constant_doc(name), "", "```text", shown, "```", ""]


GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "Running the shell",
        "Build a `Shell` and run it, or use `run()` for the short form.",
        ("Shell", "run", "ready_line", "Timings"),
    ),
    (
        "Web sources",
        "Where the UI comes from. A plain path or address is turned into one of these for you.",
        ("WebSource", "Static", "Url", "Process", "Asgi", "Wsgi"),
    ),
    (
        "Settings",
        "Frozen dataclasses. Each one validates its values when you create it.",
        ("Window", "Security", "DEV_CSP", "Server", "Bridge", "App"),
    ),
    ("Building blocks", "For tests and for mounting Cornea in a larger program.", ("create_app",)),
    (
        "Logging",
        "Cornea is quiet until you ask. It logs to the `cornea` logger.",
        ("configure_logging", "LogLevel"),
    ),
)
BLOCK = re.compile(r"(<!-- BEGIN GENERATED: api -->\n)(.*?)(\n?<!-- END GENERATED -->)", re.DOTALL)


def render_export(module: ModuleType, name: str) -> list[str]:
    """One exported name as Markdown, one heading level below its group."""
    obj = getattr(module, name)
    if inspect.isclass(obj) and dataclasses.is_dataclass(obj):
        lines = render_dataclass(obj)
    elif inspect.isclass(obj):
        lines = render_class(obj)
    elif callable(obj):
        lines = render_callable(obj, name)
    elif isinstance(obj, str):
        lines = render_constant(name, obj)
    else:
        return []
    return [f"#{line}" if line.startswith("#") else line for line in lines]


def render(module: ModuleType) -> str:
    public = [
        name
        for name in module.__all__
        if not name.startswith("__")
        and (callable(getattr(module, name)) or isinstance(getattr(module, name), str))
    ]
    grouped = {name for _, _, names in GROUPS for name in names}
    groups = [*GROUPS, ("Other", "", tuple(name for name in public if name not in grouped))]
    lines = ["## Contents", ""]
    for title, _, names in groups:
        shown = [name for name in names if name in public]
        if shown:
            links = ", ".join(f"[`{name}`](#{name.lower()})" for name in shown)
            lines.append(f"- **{title}:** {links}")
    lines.append("")
    for title, intro, names in groups:
        shown = [name for name in names if name in public]
        if not shown:
            continue
        lines += [f"## {title}", "", intro, ""] if intro else [f"## {title}", ""]
        for name in shown:
            lines += render_export(module, name)
    return "\n".join(lines).rstrip("\n")


def refresh(text: str, module: ModuleType) -> str:
    """Return ``text`` with its generated block rewritten."""
    body = render(module)
    if not BLOCK.search(text):
        sys.exit("The file has no '<!-- BEGIN GENERATED: api -->' block")
    return BLOCK.sub(lambda match: f"{match.group(1)}{body}\n<!-- END GENERATED -->", text)


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    text = target.read_text(encoding="utf-8").replace("\r\n", "\n")
    target.write_text(refresh(text, cornea), encoding="utf-8", newline="\n")
    print(f"API reference saved to: {target}")


if __name__ == "__main__":
    main()
