# HTMX with FastAPI

FastAPI answers with small pieces of HTML (Jinja2 templates) and HTMX puts them in the page, with no JavaScript of our own.

```bash
uv sync --group examples                                             # once
uv run cornea open --asgi main:app --app-dir examples/htmx_fastapi   # command line
uv run python examples/htmx_fastapi/main.py                          # Python
```

`static/htmx.min.js` is HTMX 2.0.11 from the `htmx.org` npm package, copied into the example because the strict security policy blocks scripts from a CDN. HTMX is under the Zero-Clause BSD licence. The page turns off HTMX's built-in indicator styles, which would be an inline `<style>`.
