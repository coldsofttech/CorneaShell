import { api } from "./api";

const SVG = "http://www.w3.org/2000/svg";

type Glyph = "minimize" | "maximize" | "restore" | "close";

function glyph(doc: Document, kind: Glyph): SVGElement {
  const svg = doc.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 10 10");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", "cm-glyph");
  const path = doc.createElementNS(SVG, "path");
  const shapes: Record<Glyph, string> = {
    minimize: "M1 5.5h8",
    maximize: "M1.5 1.5h7v7h-7z",
    restore: "M3 1.5h5.5V7M1.5 3h5.5v5.5H1.5z",
    close: "M1.5 1.5l7 7M8.5 1.5l-7 7",
  };
  path.setAttribute("d", shapes[kind]);
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1");
  svg.appendChild(path);
  return svg;
}

/** The title and window buttons of a frameless window. */
export class TitleBarView {
  readonly el: HTMLElement;
  private readonly title: HTMLElement;
  private readonly maximize: HTMLButtonElement;
  private maximized = false;

  constructor(
    private readonly doc: Document,
    private readonly closeBlocked: () => void,
  ) {
    this.el = doc.createElement("div");
    this.el.className = "cm-titlebar pywebview-drag-region";
    const icon = doc.createElement("span");
    icon.className = "cm-title-icon";
    this.title = doc.createElement("span");
    this.title.className = "cm-title pywebview-drag-region";
    const controls = doc.createElement("div");
    controls.className = "cm-controls";
    controls.setAttribute("role", "group");
    controls.setAttribute("aria-label", "Window controls");
    const minimize = this.button("minimize", "Minimize", () => void api.minimize());
    this.maximize = this.button("maximize", "Maximize", () => void this.toggle());
    const close = this.button("close", "Close", () => void this.close());
    controls.append(minimize, this.maximize, close);
    this.el.append(icon, this.title, controls);
    this.el.addEventListener("dblclick", (event) => {
      if ((event.target as HTMLElement).closest(".cm-controls")) return;
      void this.toggle();
    });
    this.el.dataset.titleBar = "";
  }

  setTitle(text: string): void {
    this.title.textContent = text;
  }

  /** Reads the window's state and shows the right button. */
  async sync(): Promise<{ frameless: boolean }> {
    try {
      const state = await api.windowState();
      this.setTitle(state.title);
      this.setMaximized(state.maximized);
      return { frameless: state.frameless };
    } catch {
      return { frameless: false };
    }
  }

  private setMaximized(value: boolean): void {
    this.maximized = value;
    this.el.dataset.maximized = String(value);
    const label = value ? "Restore" : "Maximize";
    this.maximize.setAttribute("aria-label", label);
    this.maximize.title = label;
    this.maximize.replaceChildren(glyph(this.doc, value ? "restore" : "maximize"));
  }

  private async toggle(): Promise<void> {
    try {
      if (this.maximized) await api.restore();
      else await api.maximize();
      this.setMaximized(!this.maximized);
    } catch {
      /* the window could not change: leave the button as it is */
    }
  }

  private async close(): Promise<void> {
    try {
      const result = await api.close();
      if (result.blocked) this.closeBlocked();
    } catch {
      /* nothing to close */
    }
  }

  private button(kind: Glyph, label: string, onClick: () => void): HTMLButtonElement {
    const button = this.doc.createElement("button");
    button.type = "button";
    button.className = `cm-control cm-${kind}`;
    button.setAttribute("aria-label", label);
    button.title = label;
    button.appendChild(glyph(this.doc, kind));
    button.addEventListener("click", onClick);
    return button;
  }
}
