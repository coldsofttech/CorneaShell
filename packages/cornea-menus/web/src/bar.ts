import { mnemonic, parseLabel } from "./label";
import type { MenuStack, Point } from "./menu";
import { visibleEntries } from "./menu";
import type { Entry } from "./types";

/** The menu bar: one button per top-level menu. */
export class MenuBarView {
  readonly el: HTMLElement;
  private entries: Entry[] = [];
  private buttons: HTMLElement[] = [];
  private current = -1;
  private altDown = false;

  constructor(
    private readonly doc: Document,
    private readonly stack: MenuStack,
    private readonly choose: (index: number, point: Point, focusFirst: boolean) => void,
    private readonly closeMenus: () => void,
  ) {
    this.el = doc.createElement("div");
    this.el.className = "cm-bar";
    this.el.setAttribute("role", "menubar");
    this.el.addEventListener("keydown", (event) => this.onKey(event));
  }

  get isOpen(): boolean {
    return this.current >= 0 && this.stack.isOpen;
  }

  render(entries: Entry[]): void {
    this.entries = visibleEntries(entries).filter((entry) => entry.type === "submenu");
    this.el.textContent = "";
    this.buttons = this.entries.map((entry, index) => {
      const button = this.doc.createElement("div");
      button.className = "cm-bar-item";
      button.setAttribute("role", "menuitem");
      button.setAttribute("aria-haspopup", "menu");
      button.tabIndex = index === 0 ? 0 : -1;
      if (entry.enabled === false) {
        button.classList.add("cm-disabled");
        button.setAttribute("aria-disabled", "true");
      }
      const parsed = parseLabel(entry.label ?? "");
      button.appendChild(this.doc.createTextNode(parsed.before));
      if (parsed.key) {
        const key = this.doc.createElement("span");
        key.className = "cm-mnemonic";
        key.textContent = parsed.key;
        button.appendChild(key);
        button.appendChild(this.doc.createTextNode(parsed.after));
      }
      button.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        if (this.current === index && this.stack.isOpen) this.closeMenus();
        else this.show(index, false);
      });
      button.addEventListener("pointerenter", () => {
        if (this.stack.isOpen && this.current !== index) this.show(index, false);
      });
      this.el.appendChild(button);
      return button;
    });
    if (this.current >= this.buttons.length) this.current = -1;
  }

  /** Open the menu at `index`, below its button. */
  show(index: number, focusFirst: boolean): void {
    const button = this.buttons[index];
    if (!button || this.entries[index]?.enabled === false) return;
    this.current = index;
    const rect = button.getBoundingClientRect();
    // Open first: closing the menu that was open clears the highlight, and this one must keep it.
    this.choose(index, { x: rect.left, y: rect.bottom }, focusFirst);
    for (const [i, item] of this.buttons.entries()) {
      item.classList.toggle("cm-open", i === index);
      item.tabIndex = i === index ? 0 : -1;
    }
  }

  /** The menus closed: clear the highlight. */
  closed(): void {
    for (const item of this.buttons) item.classList.remove("cm-open");
  }

  /** Move to the next (1) or previous (-1) menu while one is open. */
  step(direction: -1 | 1): void {
    const count = this.buttons.length;
    if (!count) return;
    for (let tries = 1; tries <= count; tries++) {
      const index = (this.current + direction * tries + count * tries) % count;
      if (this.entries[index]?.enabled !== false) {
        this.show(index, true);
        return;
      }
    }
  }

  items(): HTMLElement[] {
    return [this.el];
  }

  /** Alt alone moves to the bar; Alt with a letter opens that menu. Call from keydown/keyup. */
  handleAlt(event: KeyboardEvent): boolean {
    if (event.type === "keydown") {
      if (event.key === "Alt") {
        this.altDown = true;
        return false;
      }
      const letter = event.key.length === 1 ? event.key.toLowerCase() : "";
      if (event.altKey && !event.ctrlKey && !event.metaKey && letter) {
        const index = this.entries.findIndex((entry) => mnemonic(entry.label ?? "") === letter);
        if (index >= 0) {
          this.altDown = false;
          this.show(index, true);
          return true;
        }
      }
      if (event.key === "F10" && !event.shiftKey) {
        this.altDown = false;
        this.show(0, true);
        return true;
      }
      this.altDown = false;
      return false;
    }
    if (event.key === "Alt" && this.altDown) {
      this.altDown = false;
      this.buttons[0]?.focus({ preventScroll: true });
      return true;
    }
    return false;
  }

  private onKey(event: KeyboardEvent): void {
    const focused = this.buttons.indexOf(event.target as HTMLElement);
    if (focused < 0) return;
    const count = this.buttons.length;
    const go = (index: number): void => {
      event.preventDefault();
      this.buttons[index]?.focus({ preventScroll: true });
    };
    switch (event.key) {
      case "ArrowRight":
        go((focused + 1) % count);
        break;
      case "ArrowLeft":
        go((focused - 1 + count) % count);
        break;
      case "Home":
        go(0);
        break;
      case "End":
        go(count - 1);
        break;
      case "ArrowDown":
      case "Enter":
      case " ":
        event.preventDefault();
        this.show(focused, true);
        break;
      case "Escape":
        (this.doc.activeElement as HTMLElement | null)?.blur();
        break;
    }
  }
}
