# Streamlit

A small Streamlit app (a title, a text box and a button) shown in a Cornea window. Streamlit talks over a WebSocket, so this also shows that the proxy forwards WebSockets.

```bash
uv sync --group examples                                       # once
uv run cornea open --url http://127.0.0.1:8501 --run "uv run streamlit run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false" --run-cwd examples/streamlit_app --mode proxy --csp-profile dev
uv run python examples/streamlit_app/main.py                   # Python
```

Streamlit's page uses inline scripts and styles, so it runs with the development security policy. No Streamlit CORS or XSRF flag was needed in testing: the WebSocket connects through Cornea with Streamlit's defaults.
