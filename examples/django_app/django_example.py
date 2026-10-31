"""A whole Django site in one file, shown in a Cornea window.

    uv run cornea open --asgi django_example:application --app-dir examples/django_app

Django is mounted in the same process. Its ALLOWED_HOSTS must accept the local address that
Cornea serves on. Routes may be anywhere except under the API prefix (/api) and /health.
"""

from pathlib import Path

from django.conf import settings
from django.core.asgi import get_asgi_application
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.urls import path

HERE = Path(__file__).parent

if not settings.configured:
    settings.configure(
        DEBUG=False,
        SECRET_KEY="example-only-not-a-secret",  # noqa: S106 - a throwaway example site
        ROOT_URLCONF=__name__,
        ALLOWED_HOSTS=["127.0.0.1", "localhost"],
        MIDDLEWARE=[],
        INSTALLED_APPS=[],
    )

PAGE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Cornea: Django</title>
    <script type="module" src="/app.js"></script>
  </head>
  <body>
    <h1>Hello from Django</h1>
    <p>
      <input id="name" value="Ada" aria-label="Your name" />
      <button id="greet">Call a Django view</button>
    </p>
    <pre id="output">Press the button.</pre>
  </body>
</html>
"""


def index(request: HttpRequest) -> HttpResponse:
    return HttpResponse(PAGE)


def script(request: HttpRequest) -> HttpResponse:
    return HttpResponse(
        (HERE / "app.js").read_text(encoding="utf-8"), content_type="text/javascript"
    )


def hello(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"message": f"Hello, {request.GET.get('name', 'world')}, from Django!"})


urlpatterns = [path("", index), path("app.js", script), path("hello", hello)]

application = get_asgi_application()
