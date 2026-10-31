"""A Flask app shown in a Cornea window.

    uv run cornea open --wsgi flask_example:app --app-dir examples/flask_app

Flask is a WSGI app, so Cornea mounts it in the same process. Routes may be anywhere except
under the API prefix (/api) and /health, which belong to Cornea.
"""

from flask import Flask, jsonify, request

app = Flask(__name__)

PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Cornea: Flask</title>
    <link rel="stylesheet" href="/static/style.css" />
    <script type="module" src="/static/app.js"></script>
  </head>
  <body>
    <main>
      <h1>Hello from Flask</h1>
      <p>
        <input id="name" value="Ada" aria-label="Your name" />
        <button id="greet">Call a Flask route</button>
      </p>
      <pre id="output">Press the button.</pre>
    </main>
  </body>
</html>
"""


@app.get("/")
def index() -> str:
    return PAGE


@app.get("/hello")
def hello() -> object:
    return jsonify(message=f"Hello, {request.args.get('name', 'world')}, from Flask!")
