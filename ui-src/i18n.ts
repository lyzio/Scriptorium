// Interface text (F15). Nothing visible is written in the code: every text
// is looked up in the interface-language module the core sends us.

let table: Record<string, string> = {};

export function setStrings(strings: Record<string, string>): void {
  table = strings;
}

/** Every key that starts with a prefix, in order (F19: a guide's sections). */
export function keysWith(prefix: string): string[] {
  return Object.keys(table).filter((key) => key.startsWith(prefix)).sort();
}

export function t(key: string, details: Record<string, string | number> = {}): string {
  let text = table[key] ?? key;
  for (const [name, value] of Object.entries(details)) {
    text = text.split("{" + name + "}").join(String(value));
  }
  return text;
}

/** Fill every element marked with data-i18n attributes. */
export function applyStrings(root: ParentNode): void {
  root.querySelectorAll<HTMLElement>("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n!);
  });
  root.querySelectorAll<HTMLElement>("[data-i18n-title]").forEach((el) => {
    const text = t(el.dataset.i18nTitle!);
    el.title = text;
    if (!el.getAttribute("aria-label")) el.setAttribute("aria-label", text);
  });
  root.querySelectorAll<HTMLElement>("[data-i18n-aria]").forEach((el) => {
    el.setAttribute("aria-label", t(el.dataset.i18nAria!));
  });
  root.querySelectorAll<HTMLInputElement>("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder!);
  });
}
