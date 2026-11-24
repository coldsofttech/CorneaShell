export type EntryType = "item" | "check" | "radio" | "separator" | "submenu";

/** One menu entry as the server sends it. */
export interface Entry {
  type: EntryType;
  id?: string;
  label?: string;
  shortcut?: string;
  icon?: string;
  enabled?: boolean;
  visible?: boolean;
  checked?: boolean;
  group?: string;
  items?: Entry[];
}

export type Theme = "win11" | "xp" | "office" | "macos" | "ubuntu";
export type Mode = "component" | "frame";

export interface Definition {
  version: number;
  theme: Theme;
  mode: Mode;
  app_path: string;
  page_can_define: boolean;
  bar: Entry[];
  context: Record<string, Entry[]>;
}

/** What `cornea:menu-click` carries in `event.detail`. */
export interface MenuClickDetail {
  id: string;
  checked: boolean | null;
  menu: string | null;
}

export interface WindowState {
  title: string;
  maximized: boolean;
  minimized: boolean;
  frameless: boolean;
}
