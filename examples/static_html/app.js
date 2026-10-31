// Talking to Cornea from a page. Everything is a same-origin fetch to /api, so the session
// cookie travels with it and no CORS setup is needed.
async function call(path, method = "GET", body) {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  return response.json();
}

const windowState = () => call("/window");
const control = (name) => call(`/window/${name}`, "POST");
const nativeAction = (name, args = {}) => call(`/bridge/${name}`, "POST", args);

const output = document.querySelector("#output");
const show = (value) => {
  output.textContent = JSON.stringify(value, null, 2);
};

async function start() {
  const state = await windowState();
  // Draw our own title bar only when the window has none.
  document.querySelector("#titlebar").hidden = !state.frameless;
  document.querySelector("#title").textContent = state.title;

  document.querySelector("#minimize").addEventListener("click", () => control("minimize"));
  document.querySelector("#maximize").addEventListener("click", async () => {
    const current = await windowState();
    await control(current.maximized ? "restore" : "maximize");
  });
  document.querySelector("#close").addEventListener("click", () => control("close"));
  document.querySelector("#platform").addEventListener("click", async () => {
    show(await nativeAction("platform_info"));
  });
  document.querySelector("#rename").addEventListener("click", async () => {
    const title = `Renamed at ${new Date().toLocaleTimeString()}`;
    await call("/window/title", "POST", { title });
    document.querySelector("#title").textContent = title;
    show(await windowState());
  });
}

start();
