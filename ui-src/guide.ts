// F19 Author guides: Help ▸ How to write a theme, and Help ▸ How to write a
// game system, open inside the app with no network access (D9). Their text
// is interface text in the interface-language module (strings/guide-*.json,
// F15), so a translation of the interface translates them too.
//
// A section's text uses a small, plain markup (tools/make_guides.py):
// paragraphs separated by a blank line, "- " list items, `code`, **bold**,
// and code blocks between ``` lines, whose first line may name a file. It is
// drawn with DOM nodes and textContent only, never as HTML.

import { keysWith, t } from "./i18n";

export type GuideArea = "guide-theme" | "guide-game-system";

export interface GuideSection { id: string; title: string; body: string; }

export function guideSections(area: GuideArea): GuideSection[] {
  return keysWith(area + ".s")
    .filter((key) => key.endsWith(".title"))
    .map((key) => {
      const id = key.slice(area.length + 1, -".title".length);
      return { id, title: t(key), body: t(`${area}.${id}.body`) };
    });
}

/** `code` and **bold** inside a line of text. */
export function inlineNodes(text: string): Node[] {
  const nodes: Node[] = [];
  const pattern = /`([^`]+)`|\*\*([^*]+)\*\*/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index! > last) nodes.push(document.createTextNode(text.slice(last, match.index)));
    const el = document.createElement(match[1] !== undefined ? "code" : "strong");
    el.textContent = match[1] ?? match[2];
    nodes.push(el);
    last = match.index! + match[0].length;
  }
  if (last < text.length) nodes.push(document.createTextNode(text.slice(last)));
  return nodes;
}

/** A section's text as paragraphs, lists and code blocks. */
export function bodyNodes(body: string): HTMLElement[] {
  const out: HTMLElement[] = [];
  const lines = body.split("\n");
  let para: string[] = [];
  let list: HTMLElement | null = null;
  const endPara = () => {
    if (para.length) {
      const p = document.createElement("p");
      p.append(...inlineNodes(para.join(" ")));
      out.push(p);
    }
    para = [];
  };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith("```")) {
      endPara();
      list = null;
      const info = line.slice(3).trim();
      const code: string[] = [];
      for (i++; i < lines.length && !lines[i].startsWith("```"); i++) code.push(lines[i]);
      const figure = document.createElement("figure");
      figure.className = "guide-code";
      const name = info.match(/^(?:file|theme):\s*(.+)$/);
      if (name) {
        const caption = document.createElement("figcaption");
        caption.textContent = name[1];
        figure.append(caption);
      }
      const pre = document.createElement("pre");
      pre.textContent = code.join("\n");
      figure.append(pre);
      out.push(figure);
    } else if (line.startsWith("- ")) {
      endPara();
      if (!list) {
        list = document.createElement("ul");
        out.push(list);
      }
      const li = document.createElement("li");
      li.append(...inlineNodes(line.slice(2)));
      list.append(li);
    } else if (line.trim() === "") {
      endPara();
      list = null;
    } else {
      list = null;
      para.push(line.trim());
    }
  }
  endPara();
  return out;
}

let current: GuideArea = "guide-theme";

/** Fill the guide window with one guide and open it. */
export function openGuide(area: GuideArea): void {
  current = area;
  const dialog = document.getElementById("guide-dialog") as HTMLDialogElement;
  const toc = document.getElementById("guide-toc")!;
  const text = document.getElementById("guide-text")!;
  toc.textContent = "";
  text.textContent = "";
  const title = document.createElement("h1");
  title.id = "guide-title";
  title.textContent = t(area + ".title");
  text.append(title, ...bodyNodes(t(area + ".intro")));
  for (const section of guideSections(area)) {
    const head = document.createElement("h2");
    head.id = `guide-${section.id}`;
    head.textContent = section.title;
    text.append(head, ...bodyNodes(section.body));
    const item = document.createElement("li");
    const link = document.createElement("button");
    link.type = "button";
    link.className = "link";
    link.textContent = section.title;
    link.addEventListener("click", () => {
      head.scrollIntoView({ block: "start" });
      head.setAttribute("tabindex", "-1");
      head.focus({ preventScroll: true });
    });
    item.append(link);
    toc.append(item);
  }
  const other: GuideArea = area === "guide-theme" ? "guide-game-system" : "guide-theme";
  const otherButton = document.getElementById("guide-other")!;
  otherButton.textContent = t(other === "guide-theme" ? "guide.openTheme" : "guide.openGameSystem");
  dialog.dataset.guide = area;
  text.scrollTop = 0;
  if (!dialog.open) dialog.showModal();
  text.focus({ preventScroll: true });
  document.body.dataset.guideShown = String(Number(document.body.dataset.guideShown || 0) + 1);
}

export function wireGuide(): void {
  const dialog = document.getElementById("guide-dialog") as HTMLDialogElement;
  document.getElementById("guide-close")!.addEventListener("click", () => dialog.close());
  document.getElementById("guide-other")!.addEventListener("click", () =>
    openGuide(current === "guide-theme" ? "guide-game-system" : "guide-theme"));
}
