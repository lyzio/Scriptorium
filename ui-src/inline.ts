// Inline text between Typst markup and the Visual editor (D11, T-SRC-04/05).
// Supported: plain text, escapes, *bold*, _italic_ and inline element calls
// without a body, such as #dice(dice: "D6") (11.7), shown as chips.
// The escaping rules match scriptorum/core/source.py exactly.

let inlineKinds = new Set<string>();

/** Element kinds that can stand inside a sentence (from the definitions). */
export function setInlineKinds(kinds: string[]): void {
  inlineKinds = new Set(kinds);
}

const INLINE_CALL = /^#([A-Za-z][A-Za-z0-9-]*)\(([^()\[\]]*)\)/;

// F3.4: a mention or "see page" chip shows the entry's name; the app tells
// this module the names.
let chipLabeler: ((kind: string, args: string) => string | null) | null = null;

export function setChipLabeler(labeler: (kind: string, args: string) => string | null): void {
  chipLabeler = labeler;
}

/** The chip for an inline element call: a small non-editable span that
 * carries its source text. */
export function chipHtml(source: string): string {
  const m = INLINE_CALL.exec(source);
  const args = m ? m[2] : "";
  const value = /"((?:[^"\\]|\\.)*)"/.exec(args);
  const face = /face:\s*(\d+)/.exec(args);
  const custom = m && chipLabeler ? chipLabeler(m[1], args) : null;
  const label = custom ?? (face ? "\u2684 " + face[1] : "\u2684 " + (value ? value[1] : m ? m[1] : ""));
  return '<span class="ichip" contenteditable="false" data-src="' + escapeAttr(source) + '">' + escapeHtml(label) + "</span>";
}

function escapeAttr(text: string): string {
  return escapeHtml(text).replace(/"/g, "&quot;");
}

const ESCAPE_CHARS = new Set("\\*_#$@<>[]`~/".split(""));

function escapeChars(plain: string): string {
  let out = "";
  for (const ch of plain) out += ESCAPE_CHARS.has(ch) ? "\\" + ch : ch;
  return out;
}

function escapeLineStart(text: string): string {
  const stripped = text.replace(/^[ \t]+/, "");
  const indent = text.slice(0, text.length - stripped.length);
  if (/^[=\-+]/.test(stripped)) return indent + "\\" + stripped;
  const m = /^(\d+)\./.exec(stripped);
  if (m) return indent + m[1] + "\\." + stripped.slice(m[0].length);
  return text;
}

/** Plain text → markup that Typst prints exactly as typed. */
export function escapeInline(plain: string): string {
  return escapeChars(plain).split("\n").map(escapeLineStart).join("\n");
}

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function paragraphToHtml(markup: string): string {
  let html = "";
  let strong = false;
  let emph = false;
  for (let i = 0; i < markup.length; i++) {
    const c = markup[i];
    if (c === "\\" && i + 1 < markup.length) {
      const next = markup[i + 1];
      html += next === "\n" || next === " " ? " " : escapeHtml(next);
      i++;
      continue;
    }
    if (c === "#") {
      const m = INLINE_CALL.exec(markup.slice(i));
      if (m && inlineKinds.has(m[1])) {
        html += chipHtml(m[0]);
        i += m[0].length - 1;
        continue;
      }
    }
    if (c === "*" && !isIntraWord(markup, i)) {
      html += strong ? "</strong>" : "<strong>";
      strong = !strong;
      continue;
    }
    if (c === "_" && !isIntraWord(markup, i)) {
      html += emph ? "</em>" : "<em>";
      emph = !emph;
      continue;
    }
    html += c === "\n" ? " " : escapeHtml(c);
  }
  if (emph) html += "</em>";
  if (strong) html += "</strong>";
  return html;
}

function isWordChar(ch: string | undefined): boolean {
  return !!ch && /[\p{L}\p{N}]/u.test(ch);
}

/** Typst ignores * and _ between two word characters. */
function isIntraWord(text: string, i: number): boolean {
  return isWordChar(text[i - 1]) && isWordChar(text[i + 1]);
}

/** Markup → HTML for a contenteditable element. Paragraphs become <div>s. */
export function inlineToHtml(markup: string): string {
  const paragraphs = markup.split(/\n[ \t]*\n/);
  if (paragraphs.length === 1) return paragraphToHtml(paragraphs[0]);
  return paragraphs.map((p) => "<div>" + (paragraphToHtml(p) || "<br>") + "</div>").join("");
}

interface Run {
  text: string;
  bold: boolean;
  italic: boolean;
  raw?: boolean; // an inline element call, written as it is
}

function collect(node: Node, bold: boolean, italic: boolean, paragraphs: Run[][]): void {
  const current = () => paragraphs[paragraphs.length - 1];
  if (node.nodeType === Node.TEXT_NODE) {
    const text = (node.textContent || "").replace(/\u00a0/g, " ").replace(/\n/g, " ");
    if (text) current().push({ text, bold, italic });
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return;
  const el = node as HTMLElement;
  const tag = el.tagName;
  if (el.dataset && el.dataset.src) {
    current().push({ text: el.dataset.src, bold, italic, raw: true });
    return;
  }
  if (tag === "BR") {
    paragraphs.push([]);
    return;
  }
  const isBlock = tag === "DIV" || tag === "P";
  if (isBlock && current().length > 0) paragraphs.push([]);
  const weight = el.style.fontWeight;
  const b = bold || tag === "B" || tag === "STRONG" || weight === "bold" || Number(weight) >= 600;
  const i = italic || tag === "I" || tag === "EM" || el.style.fontStyle === "italic";
  el.childNodes.forEach((child) => collect(child, b, i, paragraphs));
  if (isBlock) paragraphs.push([]);
}

function runsToMarkup(runs: Run[]): string {
  // Merge neighbouring runs with the same style.
  const merged: Run[] = [];
  for (const run of runs) {
    const last = merged[merged.length - 1];
    if (last && !last.raw && !run.raw && last.bold === run.bold && last.italic === run.italic) last.text += run.text;
    else merged.push({ ...run });
  }
  let out = "";
  for (const run of merged) {
    if (run.raw) {
      out += run.text;
      continue;
    }
    const lead = /^\s*/.exec(run.text)![0];
    const trail = /\s*$/.exec(run.text)![0];
    const core = run.text.slice(lead.length, run.text.length - trail.length);
    let piece = escapeChars(core);
    if (core && run.italic) piece = "_" + piece + "_";
    if (core && run.bold) piece = "*" + piece + "*";
    out += lead + piece + trail;
  }
  return escapeLineStart(out.replace(/[ \t]+/g, " ").trim());
}

/** HTML of a contenteditable element → markup. */
export function htmlToInline(root: HTMLElement): string {
  const paragraphs: Run[][] = [[]];
  root.childNodes.forEach((child) => collect(child, false, false, paragraphs));
  return paragraphs
    .map(runsToMarkup)
    .filter((p) => p.length > 0)
    .join("\n\n");
}

/** Readable text, for outlines. */
export function inlineToPlain(markup: string): string {
  markup = markup.replace(/#[A-Za-z][A-Za-z0-9-]*\([^()\[\]]*\)/g, "");
  let out = "";
  for (let i = 0; i < markup.length; i++) {
    const c = markup[i];
    if (c === "\\" && i + 1 < markup.length) {
      out += markup[i + 1] === "\n" ? " " : markup[i + 1];
      i++;
    } else if ((c === "*" || c === "_") && !isIntraWord(markup, i)) {
      continue;
    } else out += c;
  }
  return out.replace(/\s+/g, " ").trim();
}
