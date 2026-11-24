import { api, setPrefix } from "./api";
import { MenuBarView } from "./bar";
import { MenuStack, visibleEntries } from "./menu";
import type { Point } from "./menu";
import { collect, matches } from "./shortcuts";
import type { Binding } from "./shortcuts";
import { TitleBarView } from "./titlebar";
import type { Definition, Entry, MenuClickDetail, Theme } from "./types";

export interface Options {
  /** The API prefix, when the script does not come from Cornea itself. Default: the server's. */
  prefix?: string;
  /** Override the theme the server names. */
  theme?: Theme;
  /** Open the context menus on right-click. Default: true. */
  contextMenus?: boolean;
}

const STYLE_ATTR = "data-cornea-menus";

function ensureStyles(doc: Document, theme: Theme): void {
  doc.documentElement.dataset.cmTheme = theme;
  const base = api.prefix() + "/menus";
  for (const href of [`${base}/base.css`, `${base}/themes/${theme}.css`]) {
    const known = [...doc.querySelectorAll(`link[${STYLE_ATTR}]`)].some(
      (node) => node.getAttribute("href") === href,
    );
    if (known) continue;
    // Only one theme's styles stay: switching theme replaces the old one.
    if (href.includes("/themes/")) {
      doc.querySelectorAll(`link[${STYLE_ATTR}][href*="/themes/"]`).forEach((node) => node.remove());
    }
    const link = doc.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    link.setAttribute(STYLE_ATTR, "");
    doc.head.appendChild(link);
  }
}

/** Holds the menus of a page: what is defined, what is drawn, and what a click does. */
export class Controller {
  definition: Definition | null = null;
  readonly stack: MenuStack;
  private readonly bars: MenuBarView[] = [];
  private readonly titleBars: TitleBarView[] = [];
  private bindings: Binding[] = [];
  private readonly docs = new Set<Document>();
  /** Windows that hear `cornea:menu-click` besides this one (the app's frame). */
  readonly targets: (() => Window | null)[] = [];
  /** Where a context menu's coordinates start, when its event came from inside a frame. */
  private frameOffset: (() => Point) | null = null;
  private started = false;
  private readonly options: Options;

  constructor(
    readonly doc: Document,
    options: Options = {},
  ) {
    this.options = options;
    if (options.prefix) setPrefix(options.prefix);
    this.stack = new MenuStack({
      doc,
      choose: (entry, menu) => void this.choose(entry, menu),
      horizontal: (direction) => this.activeBar()?.step(direction),
      closed: () => this.bars.forEach((bar) => bar.closed()),
    });
  }

  /** Fetch the definition, load the styles and listen for changes and keys. */
  async start(): Promise<void> {
    if (this.started) return;
    this.started = true;
    await this.refresh();
    this.doc.defaultView?.addEventListener("cornea:menu-changed", () => void this.refresh());
    this.listen(this.doc);
  }

  async refresh(): Promise<void> {
    try {
      this.definition = await api.definition();
    } catch (error) {
      console.warn("Cornea menus: the menus could not be loaded.", error);
      return;
    }
    ensureStyles(this.doc, this.options.theme ?? this.definition.theme);
    this.bindings = [
      ...collect(this.definition.bar, null),
      ...Object.entries(this.definition.context).flatMap(([name, items]) => collect(items, name)),
    ];
    for (const bar of this.bars) bar.render(this.definition.bar);
  }

  /** The page defines the menus itself. */
  async define(value: { bar?: Entry[]; context?: Record<string, Entry[]> }): Promise<void> {
    await api.define({ bar: value.bar ?? [], context: value.context ?? {} });
    await this.refresh();
  }

  // ----- views ----------------------------------------------------------------------------

  mountBar(container: HTMLElement): { destroy(): void } {
    const bar = new MenuBarView(
      this.doc,
      this.stack,
      (index, point, focusFirst) => {
        const entry = visibleEntries(this.definition?.bar ?? []).filter((e) => e.type === "submenu")[index];
        if (entry) this.stack.open(entry.items ?? [], point, null, { focusFirst, inside: [bar.el] });
      },
      () => this.stack.closeAll(false),
    );
    this.bars.push(bar);
    container.appendChild(bar.el);
    if (this.definition) bar.render(this.definition.bar);
    return {
      destroy: () => {
        this.bars.splice(this.bars.indexOf(bar), 1);
        bar.el.remove();
      },
    };
  }

  /** Draws the title bar. Resolves with whether the window is frameless. */
  async mountTitleBar(
    container: HTMLElement,
    closeBlocked: () => void = () => undefined,
  ): Promise<{ destroy(): void; view: TitleBarView; frameless: boolean }> {
    const view = new TitleBarView(this.doc, closeBlocked);
    this.titleBars.push(view);
    container.appendChild(view.el);
    const { frameless } = await view.sync();
    return {
      view,
      frameless,
      destroy: () => {
        this.titleBars.splice(this.titleBars.indexOf(view), 1);
        view.el.remove();
      },
    };
  }

  private activeBar(): MenuBarView | undefined {
    return this.bars.find((bar) => bar.isOpen) ?? this.bars[0];
  }

  // ----- events ---------------------------------------------------------------------------

  /** Listen for right-clicks and shortcuts in `doc` (the page, or the app's frame). */
  listen(doc: Document, offset: (() => Point) | null = null): void {
    if (this.docs.has(doc)) return;
    this.docs.add(doc);
    if (doc !== this.doc) this.stack.watch(doc);
    if (this.options.contextMenus !== false) {
      doc.addEventListener("contextmenu", (event) => this.onContext(event, offset));
    }
    doc.addEventListener("keydown", (event) => this.onKey(event));
    doc.addEventListener("keyup", (event) => {
      if (this.bars.some((bar) => bar.handleAlt(event))) event.preventDefault();
    });
  }

  forget(doc: Document): void {
    this.docs.delete(doc);
  }

  private onContext(event: MouseEvent, offset: (() => Point) | null): void {
    if (!this.definition) return;
    // Not `instanceof Element`: an event from the app's frame belongs to that frame's own classes.
    const target = event.target as Element | null;
    const named = target?.closest?.<HTMLElement>("[data-cornea-context]")?.dataset.corneaContext;
    const name = named && this.definition.context[named] ? named : "default";
    const items = this.definition.context[name];
    if (!items || !visibleEntries(items).length) return;
    event.preventDefault();
    const shift = offset ? offset() : { x: 0, y: 0 };
    this.popup(name, { x: event.clientX + shift.x, y: event.clientY + shift.y });
  }

  /** Open a context menu at a point of the window. */
  popup(name: string, at: Point, focusFirst = false): boolean {
    const items = this.definition?.context[name];
    if (!items) return false;
    this.stack.open(items, at, name, { flip: true, focusFirst });
    return true;
  }

  private onKey(event: KeyboardEvent): void {
    if (this.stack.isOpen) return;
    if (this.bars.some((bar) => bar.handleAlt(event))) {
      event.preventDefault();
      return;
    }
    for (const binding of this.bindings) {
      if (matches(binding.chord, event)) {
        event.preventDefault();
        void this.choose({ type: "item", id: binding.id }, binding.menu);
        return;
      }
    }
  }

  // ----- choosing -------------------------------------------------------------------------

  /** Tell the server an entry was chosen, then tell the page. */
  async choose(entry: Entry, menu: string | null): Promise<void> {
    if (!entry.id) return;
    let detail: MenuClickDetail;
    try {
      detail = await api.click(entry.id, menu);
    } catch (error) {
      console.warn("Cornea menus: the click could not be sent.", error);
      return;
    }
    const payload: MenuClickDetail = { id: detail.id, checked: detail.checked, menu: detail.menu };
    for (const target of [this.doc.defaultView, ...this.targets.map((get) => get())]) {
      if (!target) continue;
      // The event is made in the window that hears it, so its class belongs to that window.
      target.dispatchEvent(new (target as Window & typeof globalThis).CustomEvent("cornea:menu-click", { detail: payload }));
    }
    await this.refresh();
  }
}
