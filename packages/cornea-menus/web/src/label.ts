export interface ParsedLabel {
  before: string;
  key: string;
  after: string;
}

/** `&Open` puts the underline under O and makes Alt+O choose it. `&&` is a plain ampersand. */
export function parseLabel(label: string): ParsedLabel {
  let before = "";
  let index = 0;
  while (index < label.length) {
    const char = label.charAt(index);
    if (char === "&") {
      const next = label.charAt(index + 1);
      if (next === "&") {
        before += "&";
        index += 2;
        continue;
      }
      if (next !== "") {
        return { before, key: next, after: label.slice(index + 2).replace(/&&/g, "&") };
      }
    }
    before += char;
    index += 1;
  }
  return { before, key: "", after: "" };
}

/** The label without its `&`. */
export function plain(label: string): string {
  const parsed = parseLabel(label);
  return parsed.before + parsed.key + parsed.after;
}

/** The mnemonic letter, lower case, or "". */
export function mnemonic(label: string): string {
  return parseLabel(label).key.toLowerCase();
}
