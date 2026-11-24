import { mnemonic, parseLabel, plain } from "./label";
import type { Entry } from "./types";

export interface Point {
  x: number;
  y: number;
}

export interface OpenOptions {
  /** Open upward when there is no room below (a context menu). A bar menu shifts instead. */
  flip?: boolean;
  /** Highlight the first entry, as when the keyboard opened the menu. */
  focusFirst?: boolean;
  /** Elements that count as "inside": a click there does not close the menu. */
  inside?: HTMLElement[];
}

export interface StackHost {
  doc: Document;
  choose(entry: Entry, menu: string | null): void;
  /** Left (-1) or right (1) pressed on the outermost menu: the bar moves to its neighbour. */
  horizontal?(direction: -1 | 1): void;
  closed?(): void;
}

interface Row {
  el: HTMLElement;
  entry: Entry;
}

interface Panel {
  el: HTMLElement;
  rows: Row[];
  active: number;
  /** The row of the parent panel that opened this one. */
  owner?: HTMLElement;
}

const MARGIN = 4;
const SUBMENU_DELAY = 140;

/** Entries that are shown, with stray separators removed. */
export function visibleEntries(entries: Entry[]): Entry[] {
  const shown: Entry[] = [];
  for (const entry of entries) {
    if (entry.visible === false) continue;
    if (entry.type === "separator") {
      const last = shown[shown.length - 1];
      if (!last || last.type === "separator") continue;
    }
    shown.push(entry);
  }
  while (shown.length && shown[shown.length - 1]?.type === "separator") shown.pop();
  return shown;
}

function el<K extends keyof HTMLElementTagNameMap>(
  doc: Document,
  tag: K,
  className: string,
  parent?: HTMLElement,
): HTMLElementTagNameMap[K] {
  const node = doc.createElement(tag);
  node.className = className;
  parent?.appendChild(node);
  return node;
}

function labelNode(doc: Document, text: string, parent: HTMLElement): void {
  const parsed = parseLabel(text);
  parent.appendChild(doc.createTextNode(parsed.before));
  if (parsed.key) {
    el(doc, "span", "cm-mnemonic", parent).textContent = parsed.key;
    parent.appendChild(doc.createTextNode(parsed.after));
  }
}

/** A menu with its submenus, drawn in a layer above the page. */
export class MenuStack {
  private panels: Panel[] = [];
  private layer: HTMLElement | null = null;
  private menuName: string | null = null;
  private timer = 0;
  private returnFocus: HTMLElement | null = null;
  private inside: HTMLElement[] = [];
  private watched = new Set<Document>();
  private readonly onPointer = (event: Event): void => this.outside(event);
  private readonly onBlur = (): void => this.closeAll(false);

  constructor(private readonly host: StackHost) {}

  get isOpen(): boolean {
    return this.panels.length > 0;
  }

  /** Close the menu when a click lands in this document too (the app's frame). */
  watch(doc: Document): void {
    this.watched.add(doc);
  }

  open(items: Entry[], at: Point, menu: string | null, options: OpenOptions = {}): void {
    const doc = this.host.doc;
    this.closeAll(false);
    this.menuName = menu;
    this.inside = options.inside ?? [];
    const active = doc.activeElement;
    this.returnFocus = active instanceof HTMLElement ? active : null;
    const layer = el(doc, "div", "cm-layer", doc.body);
    layer.addEventListener("keydown", (event) => this.onKey(event));
    this.layer = layer;
    const panel = this.build(items, layer);
    this.panels = [panel];
    this.place(panel, at, undefined, Boolean(options.flip));
    for (const watched of [doc, ...this.watched]) {
      watched.addEventListener("pointerdown", this.onPointer, true);
    }
    // Only the window's own blur: moving focus from the app's frame to the menu must not close it.
    doc.defaultView?.addEventListener("blur", this.onBlur);
    panel.el.focus({ preventScroll: true });
    if (options.focusFirst) this.move(panel, 1);
  }

  closeAll(restore = true): void {
    window.clearTimeout(this.timer);
    if (!this.layer) return;
    for (const watched of [this.host.doc, ...this.watched]) {
      watched.removeEventListener("pointerdown", this.onPointer, true);
    }
    this.host.doc.defaultView?.removeEventListener("blur", this.onBlur);
    this.layer.remove();
    this.layer = null;
    this.panels = [];
    if (restore) this.returnFocus?.focus({ preventScroll: true });
    this.returnFocus = null;
    this.host.closed?.();
  }

  // ----- building -------------------------------------------------------------------------

  private build(items: Entry[], parent: HTMLElement, owner?: HTMLElement): Panel {
    const doc = this.host.doc;
    const el_ = el(doc, "div", "cm-menu", parent);
    el_.setAttribute("role", "menu");
    el_.tabIndex = -1;
    const panel: Panel = { el: el_, rows: [], active: -1, owner };
    for (const entry of visibleEntries(items)) {
      if (entry.type === "separator") {
        el(doc, "div", "cm-sep", el_).setAttribute("role", "separator");
        continue;
      }
      panel.rows.push({ el: this.row(entry, el_, panel), entry });
    }
    return panel;
  }

  private row(entry: Entry, parent: HTMLElement, panel: Panel): HTMLElement {
    const doc = this.host.doc;
    const row = el(doc, "div", "cm-item", parent);
    const disabled = entry.enabled === false;
    row.dataset.type = entry.type;
    row.setAttribute(
      "role",
      entry.type === "check" ? "menuitemcheckbox" : entry.type === "radio" ? "menuitemradio" : "menuitem",
    );
    if (entry.type === "check" || entry.type === "radio") {
      row.setAttribute("aria-checked", String(Boolean(entry.checked)));
      if (entry.checked) row.classList.add("cm-checked");
    }
    if (disabled) {
      row.classList.add("cm-disabled");
      row.setAttribute("aria-disabled", "true");
    }
    row.tabIndex = -1;
    const gutter = el(doc, "span", "cm-gutter", row);
    if (entry.icon) {
      const icon = el(doc, "img", "cm-icon", gutter);
      icon.src = entry.icon;
      icon.alt = "";
    } else if (entry.type === "check" || entry.type === "radio") {
      el(doc, "span", "cm-mark", gutter);
    }
    labelNode(doc, entry.label ?? "", el(doc, "span", "cm-label", row));
    if (entry.type === "submenu") {
      row.setAttribute("aria-haspopup", "menu");
      el(doc, "span", "cm-arrow", row);
    } else if (entry.shortcut) {
      el(doc, "span", "cm-shortcut", row).textContent = entry.shortcut;
    }
    row.addEventListener("pointermove", () => this.hover(panel, row));
    row.addEventListener("click", (event) => {
      event.preventDefault();
      this.activate(panel, row, false);
    });
    return row;
  }

  private place(panel: Panel, at: Point, owner: HTMLElement | undefined, flip: boolean): void {
    const view = this.host.doc.defaultView;
    const width = view?.innerWidth ?? 800;
    const height = view?.innerHeight ?? 600;
    const style = panel.el.style;
    style.left = "0px";
    style.top = "0px";
    const box = panel.el.getBoundingClientRect();
    let x = at.x;
    let y = at.y;
    if (owner) {
      const rect = owner.getBoundingClientRect();
      x = rect.right - 2;
      y = rect.top - 4;
      if (x + box.width > width - MARGIN) x = rect.left - box.width + 2;
    } else if (x + box.width > width - MARGIN) {
      x = flip ? x - box.width : width - box.width - MARGIN;
    }
    if (y + box.height > height - MARGIN) {
      y = flip && y - box.height >= MARGIN ? y - box.height : height - box.height - MARGIN;
    }
    style.left = `${Math.max(MARGIN, x)}px`;
    style.top = `${Math.max(MARGIN, y)}px`;
    style.maxHeight = `${height - MARGIN * 2}px`;
  }

  // ----- behaviour ------------------------------------------------------------------------

  private panelOf(row: HTMLElement): Panel | undefined {
    return this.panels.find((panel) => panel.el.contains(row));
  }

  private closeAfter(panel: Panel): void {
    const index = this.panels.indexOf(panel);
    for (const child of this.panels.splice(index + 1)) child.el.remove();
  }

  private setActive(panel: Panel, index: number): void {
    panel.active = index;
    panel.rows.forEach((row, i) => row.el.classList.toggle("cm-active", i === index));
    panel.rows[index]?.el.focus({ preventScroll: true });
  }

  private hover(panel: Panel, row: HTMLElement): void {
    const index = panel.rows.findIndex((candidate) => candidate.el === row);
    if (index < 0 || panel.active === index) return;
    this.setActive(panel, index);
    window.clearTimeout(this.timer);
    const entry = panel.rows[index]?.entry;
    const child = this.panels[this.panels.indexOf(panel) + 1];
    if (entry?.type === "submenu" && entry.enabled !== false) {
      this.timer = window.setTimeout(() => this.openSub(panel, row, false), SUBMENU_DELAY);
    } else if (child) {
      this.timer = window.setTimeout(() => this.closeAfter(panel), SUBMENU_DELAY);
    }
  }

  private openSub(panel: Panel, row: HTMLElement, focusFirst: boolean): void {
    const index = panel.rows.findIndex((candidate) => candidate.el === row);
    const entry = panel.rows[index]?.entry;
    if (!entry || entry.type !== "submenu" || !this.layer) return;
    const open = this.panels[this.panels.indexOf(panel) + 1];
    if (open && open.owner === row) {
      if (focusFirst) this.move(open, 1);
      return;
    }
    this.closeAfter(panel);
    const child = this.build(entry.items ?? [], this.layer, row);
    this.panels.push(child);
    this.place(child, { x: 0, y: 0 }, row, false);
    row.setAttribute("aria-expanded", "true");
    if (focusFirst) this.move(child, 1);
  }

  private activate(panel: Panel, row: HTMLElement, viaKeyboard: boolean): void {
    const index = panel.rows.findIndex((candidate) => candidate.el === row);
    const entry = panel.rows[index]?.entry;
    if (!entry || entry.enabled === false) return;
    if (entry.type === "submenu") {
      this.setActive(panel, index);
      this.openSub(panel, row, viaKeyboard);
      return;
    }
    const menu = this.menuName;
    this.closeAll(viaKeyboard);
    this.host.choose(entry, menu);
  }

  private move(panel: Panel, step: 1 | -1): void {
    const rows = panel.rows;
    if (!rows.length) return;
    let index = panel.active;
    for (let tries = 0; tries < rows.length; tries++) {
      index = index < 0 ? (step === 1 ? 0 : rows.length - 1) : (index + step + rows.length) % rows.length;
      if (rows[index]?.entry.enabled !== false) {
        this.setActive(panel, index);
        return;
      }
    }
  }

  private edge(panel: Panel, last: boolean): void {
    const order = last ? [...panel.rows.keys()].reverse() : [...panel.rows.keys()];
    const found = order.find((i) => panel.rows[i]?.entry.enabled !== false);
    if (found !== undefined) this.setActive(panel, found);
  }

  private onKey(event: KeyboardEvent): void {
    const panel = this.panels[this.panels.length - 1];
    if (!panel) return;
    const row = panel.rows[panel.active];
    const handled = (): void => {
      event.preventDefault();
      event.stopPropagation();
    };
    switch (event.key) {
      case "ArrowDown":
        handled();
        this.move(panel, 1);
        return;
      case "ArrowUp":
        handled();
        this.move(panel, -1);
        return;
      case "Home":
        handled();
        this.edge(panel, false);
        return;
      case "End":
        handled();
        this.edge(panel, true);
        return;
      case "Enter":
      case " ":
        handled();
        if (row) this.activate(panel, row.el, true);
        return;
      case "ArrowRight":
        handled();
        if (row?.entry.type === "submenu") this.activate(panel, row.el, true);
        else if (this.panels.length === 1) this.host.horizontal?.(1);
        return;
      case "ArrowLeft":
        handled();
        if (this.panels.length > 1) {
          this.panels.pop()?.el.remove();
          const parent = this.panels[this.panels.length - 1];
          parent?.rows[parent.active]?.el.removeAttribute("aria-expanded");
          if (parent) this.setActive(parent, parent.active);
        } else {
          this.host.horizontal?.(-1);
        }
        return;
      case "Escape":
        handled();
        if (this.panels.length > 1) {
          this.panels.pop()?.el.remove();
          const parent = this.panels[this.panels.length - 1];
          if (parent) this.setActive(parent, parent.active);
        } else {
          this.closeAll(true);
        }
        return;
      case "Tab":
        handled();
        this.closeAll(true);
        return;
      default:
        if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
          handled();
          this.letter(panel, event.key.toLowerCase());
        }
    }
  }

  /** A letter chooses the entry with that mnemonic, or moves to the next one that starts with it. */
  private letter(panel: Panel, key: string): void {
    const usable = panel.rows
      .map((row, index) => ({ row, index }))
      .filter(({ row }) => row.entry.enabled !== false);
    const byMnemonic = usable.filter(({ row }) => mnemonic(row.entry.label ?? "") === key);
    const pool = byMnemonic.length ? byMnemonic : usable.filter(({ row }) => plain(row.entry.label ?? "").toLowerCase().startsWith(key));
    if (!pool.length) return;
    const after = pool.find(({ index }) => index > panel.active) ?? pool[0];
    if (!after) return;
    this.setActive(panel, after.index);
    if (pool.length === 1 && byMnemonic.length) this.activate(panel, after.row.el, true);
  }

  private outside(event: Event): void {
    // Not `instanceof Node`: a click in the app's frame comes from that frame's own classes.
    const target = event.target as Node | null;
    if (!target || typeof target.nodeType !== "number") return;
    if (this.layer?.contains(target)) return;
    if (this.inside.some((node) => node.contains(target))) return;
    this.closeAll(false);
  }
}
