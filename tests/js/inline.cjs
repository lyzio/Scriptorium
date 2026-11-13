"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// inline.ts
var inline_exports = {};
__export(inline_exports, {
  chipHtml: () => chipHtml,
  escapeInline: () => escapeInline,
  htmlToInline: () => htmlToInline,
  inlineToHtml: () => inlineToHtml,
  inlineToPlain: () => inlineToPlain,
  setChipLabeler: () => setChipLabeler,
  setInlineKinds: () => setInlineKinds
});
module.exports = __toCommonJS(inline_exports);
var inlineKinds = /* @__PURE__ */ new Set();
function setInlineKinds(kinds) {
  inlineKinds = new Set(kinds);
}
var INLINE_CALL = /^#([A-Za-z][A-Za-z0-9-]*)\(([^()\[\]]*)\)/;
var chipLabeler = null;
function setChipLabeler(labeler) {
  chipLabeler = labeler;
}
function chipHtml(source) {
  const m = INLINE_CALL.exec(source);
  const args = m ? m[2] : "";
  const value = /"((?:[^"\\]|\\.)*)"/.exec(args);
  const face = /face:\s*(\d+)/.exec(args);
  const custom = m && chipLabeler ? chipLabeler(m[1], args) : null;
  const label = custom ?? (face ? "\u2684 " + face[1] : "\u2684 " + (value ? value[1] : m ? m[1] : ""));
  return '<span class="ichip" contenteditable="false" data-src="' + escapeAttr(source) + '">' + escapeHtml(label) + "</span>";
}
function escapeAttr(text) {
  return escapeHtml(text).replace(/"/g, "&quot;");
}
var ESCAPE_CHARS = new Set("\\*_#$@<>[]`~/".split(""));
function escapeChars(plain) {
  let out = "";
  for (const ch of plain) out += ESCAPE_CHARS.has(ch) ? "\\" + ch : ch;
  return out;
}
function escapeLineStart(text) {
  const stripped = text.replace(/^[ \t]+/, "");
  const indent = text.slice(0, text.length - stripped.length);
  if (/^[=\-+]/.test(stripped)) return indent + "\\" + stripped;
  const m = /^(\d+)\./.exec(stripped);
  if (m) return indent + m[1] + "\\." + stripped.slice(m[0].length);
  return text;
}
function escapeInline(plain) {
  return escapeChars(plain).split("\n").map(escapeLineStart).join("\n");
}
function escapeHtml(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function paragraphToHtml(markup) {
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
function isWordChar(ch) {
  return !!ch && /[\p{L}\p{N}]/u.test(ch);
}
function isIntraWord(text, i) {
  return isWordChar(text[i - 1]) && isWordChar(text[i + 1]);
}
function inlineToHtml(markup) {
  const paragraphs = markup.split(/\n[ \t]*\n/);
  if (paragraphs.length === 1) return paragraphToHtml(paragraphs[0]);
  return paragraphs.map((p) => "<div>" + (paragraphToHtml(p) || "<br>") + "</div>").join("");
}
function collect(node, bold, italic, paragraphs) {
  const current = () => paragraphs[paragraphs.length - 1];
  if (node.nodeType === Node.TEXT_NODE) {
    const text = (node.textContent || "").replace(/\u00a0/g, " ").replace(/\n/g, " ");
    if (text) current().push({ text, bold, italic });
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return;
  const el = node;
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
function runsToMarkup(runs) {
  const merged = [];
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
    const lead = /^\s*/.exec(run.text)[0];
    const trail = /\s*$/.exec(run.text)[0];
    const core = run.text.slice(lead.length, run.text.length - trail.length);
    let piece = escapeChars(core);
    if (core && run.italic) piece = "_" + piece + "_";
    if (core && run.bold) piece = "*" + piece + "*";
    out += lead + piece + trail;
  }
  return escapeLineStart(out.replace(/[ \t]+/g, " ").trim());
}
function htmlToInline(root) {
  const paragraphs = [[]];
  root.childNodes.forEach((child) => collect(child, false, false, paragraphs));
  return paragraphs.map(runsToMarkup).filter((p) => p.length > 0).join("\n\n");
}
function inlineToPlain(markup) {
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
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  chipHtml,
  escapeInline,
  htmlToInline,
  inlineToHtml,
  inlineToPlain,
  setChipLabeler,
  setInlineKinds
});
