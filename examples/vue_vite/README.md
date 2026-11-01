# Vue + Vite

A Vue project built with Vite, with its own title bar when the window is frameless. Same shape as the React example.

```bash
npm install && npm run build                                   # in this folder
uv run cornea open examples/vue_vite/dist --frameless          # command line
uv run python examples/vue_vite/main.py                        # Python
uv run python examples/vue_vite/main.py --dev                  # dev server with hot reload
```

`--dev` starts Vite for you, shows it through Cornea (proxy mode) and stops it with the window. Vite injects inline scripts, so `--dev` uses the development security policy; the built version uses the strict one.
