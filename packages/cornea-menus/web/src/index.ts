import { api, setPrefix } from "./api";
import { Controller } from "./controller";
import type { Options } from "./controller";
import type { Entry } from "./types";

export type { Definition, Entry, MenuClickDetail, Mode, Theme } from "./types";
export { Controller } from "./controller";
export type { Options } from "./controller";
export { setPrefix };

function find(target: HTMLElement | string, doc: Document): HTMLElement {
  const node = typeof target === "string" ? doc.querySelector<HTMLElement>(target) : target;
  if (!node) throw new Error(`Cornea menus: nothing matches ${String(target)}`);
  return node;
}

export interface MountOptions extends Options {
  /** Where to draw the menu bar: an element or a selector. */
  bar?: HTMLElement | string;
  /** Where to draw the title bar of a frameless window. It is left empty for a window with a frame. */
  titleBar?: HTMLElement | string;
}

/**
 * Draw the menus into the page and start listening for right-clicks and shortcuts.
 *
 * ```js
 * const menus = await corneaMenus.mount({ bar: "#menubar", titleBar: "#titlebar" });
 * window.addEventListener("cornea:menu-click", (e) => console.log(e.detail.id));
 * ```
 */
export async function mount(options: MountOptions = {}, doc: Document = document): Promise<Controller> {
  const controller = new Controller(doc, options);
  await controller.start();
  if (options.bar) controller.mountBar(find(options.bar, doc));
  if (options.titleBar) {
    const holder = find(options.titleBar, doc);
    const bar = await controller.mountTitleBar(holder);
    if (!bar.frameless) bar.destroy();
  }
  return controller;
}

/** Define the menus from the page, when the app allows it. */
export async function set(value: { bar?: Entry[]; context?: Record<string, Entry[]> }): Promise<void> {
  await api.define({ bar: value.bar ?? [], context: value.context ?? {} });
}
