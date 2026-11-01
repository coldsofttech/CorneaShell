# MkDocs

A small MkDocs site shown in a window, like an offline help viewer.

```bash
uv sync --group examples                                       # once
uv run mkdocs build -f examples/mkdocs_site/mkdocs.yml
uv run cornea open examples/mkdocs_site/site                   # command line
uv run python examples/mkdocs_site/main.py                     # Python: builds, then shows the site
uv run python examples/mkdocs_site/main.py --live              # mkdocs serve: reloads on edits
```

`--live` shows `mkdocs serve` through Cornea (proxy mode) with the development security policy, because MkDocs reloads over a WebSocket and injects inline scripts. In the built site, the default MkDocs theme has a few inline scripts and loads code highlighting from a CDN; the strict policy blocks them, so highlighting and search do not work there. Reading and navigation do.
