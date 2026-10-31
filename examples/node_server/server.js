// A Node.js server that Cornea does not run, shown in a Cornea window as a direct address.
//
//   node examples/node_server/server.js
//   uv run cornea open http://127.0.0.1:3000                 # direct
//   uv run cornea open http://127.0.0.1:3000 --mode proxy    # through Cornea
//
// No packages are needed. Opened directly, Cornea does not serve this page, so it is not behind
// Cornea's security and needs the normal window frame (no --frameless). Through the proxy
// (`pip install "cornea-shell[proxy]"`) the page is served from Cornea's own address, so it gets
// the security layer, the window controls and a frameless window.

const http = require("node:http");
const { readFile } = require("node:fs/promises");
const path = require("node:path");

const port = Number(process.env.PORT ?? 3000);

const server = http.createServer(async (request, response) => {
  const { pathname, searchParams } = new URL(request.url, "http://localhost");
  if (pathname === "/hello") {
    const name = searchParams.get("name") ?? "world";
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ message: `Hello, ${name}, from Node.js ${process.version}!` }));
  } else if (pathname === "/") {
    const page = await readFile(path.join(__dirname, "index.html"));
    response.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    response.end(page);
  } else {
    response.writeHead(404).end("Not found");
  }
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Listening on http://127.0.0.1:${port}`);
});
