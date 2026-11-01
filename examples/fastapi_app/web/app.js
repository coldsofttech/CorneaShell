const output = document.querySelector("#output");
const name = document.querySelector("#name");

async function show(request) {
  const response = await request;
  output.textContent = JSON.stringify(await response.json(), null, 2);
}

document.querySelector("#greet").addEventListener("click", () => {
  // The route defined in main.py: GET /api/greeting (/greeting when FastAPI is mounted)
  const url = document.querySelector("meta[name=greeting-url]").content;
  show(fetch(`${url}?name=${encodeURIComponent(name.value)}`));
});

document.querySelector("#shout").addEventListener("click", () => {
  // The action registered with @shell.action("shout"): POST /api/bridge/shout
  show(
    fetch("/api/bridge/shout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: name.value }),
    }),
  );
});
