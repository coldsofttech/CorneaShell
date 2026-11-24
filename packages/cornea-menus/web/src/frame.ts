import { api } from "./api";
import { Controller } from "./controller";
import type { Point } from "./menu";

/**
 * Frame mode: draws the title bar and menu bar, and shows the app in a frame below them.
 *
 * The app is on the same address, so this page can reach its document directly: it hears the
 * app's right-clicks, shortcuts and clicks without the app doing anything. Events that Python
 * sends to the window (`cornea:*`) are passed on to the app, so it hears them as usual.
 */
export async function runFrame(doc: Document = document): Promise<Controller> {
  const win = doc.defaultView as Window;
  const controller = new Controller(doc);
  await controller.start();
  const definition = controller.definition;

  const root = doc.body;
  root.textContent = "";
  const top = doc.createElement("div");
  top.className = "cm-frame-top";
  const bars = doc.createElement("div");
  bars.className = "cm-frame-bars";
  const frame = doc.createElement("iframe");
  frame.className = "cm-app-frame";
  frame.title = "Application";
  top.appendChild(bars);
  root.append(top, frame);

  const titleBar = await controller.mountTitleBar(bars, () => relay("close-blocked", null));
  if (titleBar.frameless) {
    doc.documentElement.dataset.cmFrameless = "";
  } else {
    titleBar.destroy();
  }
  controller.mountBar(bars);

  const offset = (): Point => {
    const box = frame.getBoundingClientRect();
    return { x: box.left, y: box.top };
  };

  // Everything Python sends to the window also reaches the app.
  const original = win.dispatchEvent.bind(win);
  win.dispatchEvent = (event: Event): boolean => {
    const result = original(event);
    if (event.type.startsWith("cornea:") && event.type !== "cornea:menu-changed") {
      const inner = frame.contentWindow;
      if (inner) {
        const detail = (event as CustomEvent).detail as unknown;
        inner.dispatchEvent(new (inner as Window & typeof globalThis).CustomEvent(event.type, { detail }));
      }
    }
    return result;
  };
  function relay(name: string, detail: unknown): void {
    win.dispatchEvent(new CustomEvent(`cornea:${name}`, { detail }));
  }

  let titleTimer = 0;
  const syncTitle = (inner: Document): void => {
    const text = inner.title.trim();
    if (!text) return;
    doc.title = text;
    titleBar.view.setTitle(text);
    win.clearTimeout(titleTimer);
    // The window's own title (taskbar, Alt+Tab) follows the app too.
    titleTimer = win.setTimeout(() => void api.setTitle(text).catch(() => undefined), 200);
  };

  frame.addEventListener("load", () => {
    const inner = frame.contentDocument;
    if (!inner) return;
    controller.listen(inner, offset);
    syncTitle(inner);
    const head = inner.querySelector("title") ?? inner.head;
    if (head) new MutationObserver(() => syncTitle(inner)).observe(head, { childList: true, subtree: true, characterData: true });
    // The page is gone after navigating, so its listeners are too; let the next one be added.
    inner.defaultView?.addEventListener("pagehide", () => controller.forget(inner));
  });
  frame.src = definition?.app_path ?? "/";
  return controller;
}
