import type { Entry } from "./types";

export interface Chord {
  ctrl: boolean;
  shift: boolean;
  alt: boolean;
  meta: boolean;
  key: string;
}

const NAMES: Record<string, string> = {
  esc: "escape",
  del: "delete",
  ins: "insert",
  return: "enter",
  left: "arrowleft",
  right: "arrowright",
  up: "arrowup",
  down: "arrowdown",
  plus: "+",
  space: " ",
  pgup: "pageup",
  pgdn: "pagedown",
};

/** `Ctrl+Shift+S` as a chord, or `null` if it is not one. */
export function parseChord(spec: string): Chord | null {
  const parts = spec.split("+").map((part) => part.trim());
  // "Ctrl++" ends in an empty piece: that is the plus key.
  if (spec.endsWith("++")) parts.splice(-2, 2, "plus");
  const rawKey = parts.pop();
  if (!rawKey) return null;
  const chord: Chord = { ctrl: false, shift: false, alt: false, meta: false, key: "" };
  for (const part of parts) {
    switch (part.toLowerCase()) {
      case "ctrl":
      case "control":
        chord.ctrl = true;
        break;
      case "shift":
        chord.shift = true;
        break;
      case "alt":
      case "option":
        chord.alt = true;
        break;
      case "cmd":
      case "command":
      case "meta":
      case "win":
        chord.meta = true;
        break;
      default:
        return null;
    }
  }
  const lowered = rawKey.toLowerCase();
  chord.key = NAMES[lowered] ?? lowered;
  return chord;
}

/** Whether the key press is this chord. */
export function matches(chord: Chord, event: KeyboardEvent): boolean {
  return (
    event.ctrlKey === chord.ctrl &&
    event.shiftKey === chord.shift &&
    event.altKey === chord.alt &&
    event.metaKey === chord.meta &&
    event.key.toLowerCase() === chord.key
  );
}

/** A plain letter must not be taken from someone typing, so a chord needs a modifier or a function key. */
export function isSafe(chord: Chord): boolean {
  return chord.ctrl || chord.alt || chord.meta || /^f\d{1,2}$/.test(chord.key);
}

export interface Binding {
  chord: Chord;
  id: string;
  menu: string | null;
}

/** Every shortcut of the entries that can be chosen now. */
export function collect(entries: Entry[], menu: string | null, into: Binding[] = []): Binding[] {
  for (const entry of entries) {
    if (entry.enabled === false || entry.visible === false) continue;
    if (entry.type === "submenu") {
      collect(entry.items ?? [], menu, into);
    } else if (entry.shortcut && entry.id) {
      const chord = parseChord(entry.shortcut);
      if (chord && isSafe(chord)) into.push({ chord, id: entry.id, menu });
    }
  }
  return into;
}
