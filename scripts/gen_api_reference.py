#!/usr/bin/env python3
"""Generate docs/api-reference.md from the public API in ``cornea.__all__``.

Usage: uv run python scripts/gen_api_reference.py [output]
CI regenerates the file and fails if it differs from the committed copy.
"""

import ast
import dataclasses
import inspect
import re
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Any

import cornea

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
            return textwrap.dedent("\n".join(block)).strip().splitlines()
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
    lines = [f"## `{cls.__name__}`", "", first_paragraph(cls), ""]
    docs = attribute_docs(cls)
    fields = dataclasses.fields(cls)
    if fields:
        lines += ["| Parameter | Type | Default | Description |", "| --- | --- | --- | --- |"]
    for field in fields:
        lines.append(
            f"| `{field.name}` | `{escape(type_name(field.type))}` | "
            f"`{escape(default_text(field))}` | {escape(docs.get(field.name, ''))} |"
        )
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
    if methods:
        lines += ["", "Methods:", ""]
        lines += [
            f"- `{name}{signature_text(member)}`: {first_paragraph(member)}"
            for name, member in methods
        ]
    return [*lines, *render_example(cls), ""]


def body_text(obj: object) -> str:
    """The docstring without its ``Example:`` section, as Markdown."""
    lines = (inspect.getdoc(obj) or "").splitlines()
    for index, line in enumerate(lines):
        if line.strip() in {"Example:", "Examples:"}:
            lines = lines[:index]
            break
    return markdown("\n".join(lines).strip())


def signature_block(function: Any) -> str:
    """A ``def`` block with one parameter per line, module paths and quotes removed."""
    signature = inspect.signature(function)
    params = [tidy(str(parameter)) for parameter in signature.parameters.values()]
    kinds = [parameter.kind for parameter in signature.parameters.values()]
    if inspect.Parameter.KEYWORD_ONLY in kinds and inspect.Parameter.VAR_POSITIONAL not in kinds:
        params.insert(kinds.index(inspect.Parameter.KEYWORD_ONLY), "*")
    returns = ""
    if signature.return_annotation is not inspect.Signature.empty:
        returns = f" -> {tidy(type_name(signature.return_annotation))}"
    if not params:
        return f"def {function.__name__}(){returns}"
    inner = ",\n".join(f"    {param}" for param in params)
    return f"def {function.__name__}(\n{inner},\n){returns}"


def render_callable(obj: Any) -> list[str]:
    return [
        f"## `{obj.__name__}`",
        "",
        "```python",
        signature_block(obj),
        "```",
        "",
        body_text(obj),
        *render_example(obj),
        "",
    ]


def render(module: ModuleType) -> str:
    lines = [
        "# Python API reference",
        "",
        "<!-- Generated by scripts/gen_api_reference.py. Do not edit by hand. -->",
        "",
        "Public names exported by `cornea`. Install with `pip install cornea-shell`.",
        "",
    ]
    for name in module.__all__:
        if name.startswith("__"):
            continue
        obj = getattr(module, name)
        if inspect.isclass(obj) and dataclasses.is_dataclass(obj):
            lines += render_dataclass(obj)
        elif callable(obj):
            lines += render_callable(obj)
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> None:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output.write_text(render(cornea), encoding="utf-8", newline="\n")
    print(f"API reference saved to: {output}")


if __name__ == "__main__":
    main()
