// A minimal ASP.NET Core server shown in Cornea.
//   dotnet run --project examples/dotnet_server --urls http://127.0.0.1:5101
// --urls is how Cornea passes the port.

var app = WebApplication.CreateBuilder(args).Build();

var version = Environment.Version;

app.MapGet("/", () => Results.Content(
    """
    <!doctype html>
    <html lang="en">
      <head><meta charset="utf-8" /><title>Cornea: .NET</title></head>
      <body>
        <h1>Hello from .NET</h1>
        <p>Try <a href="/hello?name=Zed">/hello?name=Zed</a>.</p>
      </body>
    </html>
    """,
    "text/html; charset=utf-8"));

app.MapGet("/hello", (string? name) =>
{
    var who = name ?? "world";
    return Results.Json(new { message = $"Hello, {who}, from .NET {version}!" });
});

app.Run();
