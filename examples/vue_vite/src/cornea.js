// The few calls a page makes to Cornea. All are same-origin fetches to /api, so the session
// cookie goes with them and no CORS setup is needed.
async function call(path, method = "GET", body) {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  return response.json();
}

export const windowState = () => call("/window");
export const control = (name) => call(`/window/${name}`, "POST");
export const nativeAction = (name, args = {}) => call(`/bridge/${name}`, "POST", args);
