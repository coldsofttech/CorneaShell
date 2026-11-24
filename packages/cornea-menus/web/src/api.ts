import type { Definition, MenuClickDetail, WindowState } from "./types";

// The server replaces the one placeholder below with the real API prefix when it serves the script.
const injected = "__API_PREFIX__";
let prefix = injected.charAt(0) === "/" ? injected : "/api";

/** Use another API prefix. Only needed when the script does not come from Cornea itself. */
export function setPrefix(value: string): void {
  prefix = value.replace(/\/+$/, "");
}

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} };
  if (body !== undefined) {
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const response = await fetch(prefix + path, init);
  const data = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  if (!response.ok) {
    const detail = data.error ?? data.detail;
    throw new Error(typeof detail === "string" ? detail : `The request failed (${response.status}).`);
  }
  return data as T;
}

export const api = {
  prefix: (): string => prefix,
  definition: (): Promise<Definition> => request("/menus"),
  click: (id: string, menu: string | null): Promise<MenuClickDetail> =>
    request("/menus/click", "POST", { id, menu }),
  define: (value: { bar?: unknown; context?: unknown }): Promise<{ ok: boolean }> =>
    request("/menus/definition", "POST", value),
  windowState: (): Promise<WindowState> => request("/window"),
  minimize: (): Promise<unknown> => request("/window/minimize", "POST"),
  maximize: (): Promise<unknown> => request("/window/maximize", "POST"),
  restore: (): Promise<unknown> => request("/window/restore", "POST"),
  close: (): Promise<{ ok: boolean; blocked?: boolean }> => request("/window/close", "POST", {}),
  setTitle: (title: string): Promise<unknown> => request("/window/title", "POST", { title }),
};
