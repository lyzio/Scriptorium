// Help ▸ About Scriptorum (design document F9, built in M6 part B): three
// tabs. About: name, version, logo, "Idea by lyzio · lyzio.net" and the GPL.
// Under the hood: every part Scriptorum is built on, with version, what it
// does and licence; a row opens its full licence text. Licences: the full
// text of each licence used. Everything is read from the app, offline (D9).

import { call } from "./bridge";
import { t } from "./i18n";

const $ = <T extends HTMLElement = HTMLElement>(id: string): T => document.getElementById(id) as T;

function h<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

let info: any = null;

function showTab(tab: string): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>("#about-dialog .about-tabs button")) {
    button.setAttribute("aria-selected", String(button.dataset.tab === tab));
  }
  for (const name of ["about", "hood", "licences"]) $(`about-page-${name}`).classList.toggle("hidden", name !== tab);
  $("about-text-box").classList.add("hidden");
}

async function showText(title: string, ref: string, note = ""): Promise<void> {
  const reply = await call("aboutText", ref);
  $("about-text-title").textContent = title;
  $("about-text").textContent = (note ? note + "\n\n" : "") + (reply?.ok ? reply.text : t("about.notFound"));
  for (const name of ["about", "hood", "licences"]) $(`about-page-${name}`).classList.add("hidden");
  $("about-text-box").classList.remove("hidden");
  $("about-text").scrollTop = 0;
}

function refOf(row: any): string {
  return row.file ? `part:${row.file}` : row.path ? `file:${row.path}` : "";
}

function section(title: string, rows: any[]): HTMLElement {
  const wrap = h("div");
  wrap.append(h("h3", undefined, title));
  const table = h("table");
  const head = h("tr");
  for (const k of ["colName", "colVersion", "colWhat", "colLicence"]) head.append(h("th", undefined, t(`about.${k}`)));
  table.append(head);
  for (const row of rows) {
    const tr = h("tr", "about-row");
    tr.dataset.part = row.id;
    const what = row.what === "font"
      ? `${t("about.what.font")} · ${row.module}`
      : t(`about.what.${row.what}`) + (row.modules?.length ? ` (${t("about.inModules", { modules: row.modules.join(", ") })})` : "");
    tr.append(h("td", undefined, row.name), h("td", undefined, row.version || ""), h("td", undefined, what), h("td", undefined, row.licence));
    tr.addEventListener("click", () => showText(`${row.name} — ${row.licence}`, refOf(row), row.note === "chromium" ? t("about.chromiumNote") : ""));
    table.append(tr);
  }
  wrap.append(table);
  return wrap;
}

function render(): void {
  $("about-version").textContent = t("about.version", { version: info.version });
  const idea = $("about-idea");
  idea.textContent = t("about.ideaBy", { name: info.ideaBy });
  const link = h("button", "about-link", info.ideaSite.replace(/^https:\/\//, ""));
  link.type = "button";
  link.id = "about-site";
  link.addEventListener("click", () => call("openIdeaSite"));
  idea.append(link);
  const hood = $("about-hood");
  hood.textContent = "";
  hood.append(
    section(t("about.programs"), info.programs),
    section(t("about.packages"), info.packages),
    section(t("about.fonts"), info.fonts),
    section(t("about.dictionaries"), info.dictionaries),
  );
  const list = $("about-licences");
  list.textContent = "";
  for (const licence of info.licences) {
    const li = h("li");
    const button = h("button", undefined, licence.name);
    button.type = "button";
    button.dataset.licence = licence.id;
    button.addEventListener("click", () => showText(licence.name, `licence:${licence.id}`));
    li.append(button);
    list.append(li);
  }
}

export async function openAbout(): Promise<void> {
  info = await call("aboutInfo");
  render();
  showTab("about");
  const dialog = $<HTMLDialogElement>("about-dialog");
  if (!dialog.open) dialog.showModal();
}

export function initAbout(): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>("#about-dialog .about-tabs button")) {
    button.addEventListener("click", () => showTab(button.dataset.tab!));
  }
  $("about-gpl").addEventListener("click", () => showText(t("about.free"), "licence:GPL-3.0"));
  $("about-text-back").addEventListener("click", () => {
    const tab = document.querySelector<HTMLButtonElement>("#about-dialog .about-tabs button[aria-selected=true]")?.dataset.tab ?? "about";
    showTab(tab);
  });
  $("about-close").addEventListener("click", () => $<HTMLDialogElement>("about-dialog").close());
}

export const aboutTest = { openAbout, showTab, showText, info: () => info };
