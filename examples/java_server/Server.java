// A Java server shown in Cornea, using only the JDK.
//   java Server.java 5102        (JDK 21 or newer; runs the source file directly)

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;

public class Server {
    private static final String PAGE = """
        <!doctype html>
        <html lang="en">
          <head><meta charset="utf-8"><title>Cornea: Java</title></head>
          <body>
            <h1>Hello from Java</h1>
            <p>Try <a href="/hello?name=Zed">/hello?name=Zed</a>.</p>
          </body>
        </html>
        """;

    public static void main(String[] args) throws IOException {
        String text = args.length > 0 ? args[0] : System.getenv().getOrDefault("PORT", "5102");
        int port = Integer.parseInt(text);
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);

        server.createContext("/hello", exchange -> {
            String name = queryValue(exchange.getRequestURI().getRawQuery(), "name", "world");
            String json = "{\"message\": \"Hello, " + jsonEscape(name) + ", from Java "
                    + System.getProperty("java.version") + "!\"}";
            send(exchange, 200, "application/json", json);
        });
        server.createContext("/", exchange -> {
            if (exchange.getRequestURI().getPath().equals("/")) {
                send(exchange, 200, "text/html; charset=utf-8", PAGE);
            } else {
                send(exchange, 404, "text/plain; charset=utf-8", "Not found");
            }
        });

        server.start();
        System.out.println("Listening on http://127.0.0.1:" + port);
    }

    private static void send(HttpExchange exchange, int status, String type, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", type);
        exchange.sendResponseHeaders(status, bytes.length);
        try (var out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static String queryValue(String query, String key, String fallback) {
        if (query == null) {
            return fallback;
        }
        for (String pair : query.split("&")) {
            int equals = pair.indexOf('=');
            String name = equals < 0 ? pair : pair.substring(0, equals);
            if (name.equals(key) && equals >= 0) {
                return URLDecoder.decode(pair.substring(equals + 1), StandardCharsets.UTF_8);
            }
        }
        return fallback;
    }

    private static String jsonEscape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
