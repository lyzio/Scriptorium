// World-building in the interface (Milestone 3): the Codex and Handouts
// sidebars and the "In this scene" panel (F9.3), the entry editor (F3), the
// codex type editor (F3.2), the map editor (F5), the relationship chart
// (F3.9) and the dialog that turns M2 text into codex links (F3.12).
//
// Every change goes to the core and is one undo step there; the core keeps
// the codex and the maps, the interface only shows them.

import cytoscape from "cytoscape";
import { call } from "./bridge";
import { t } from "./i18n";
import { htmlToInline, inlineToHtml } from "./inline";
import { Block } from "./model";

export interface CodexType {
  id: string;
  name: string;
  icon: string;
  title_field: string;
  fields: { name: string; kind: string; label: string; required?: boolean; options?: { id: string; label: string }[]; types?: string[] | null; accept?: string }[];
  card: string | null;
  own: boolean;
}

export interface Codex {
  types: CodexType[];
  entries: { id: string; type: string; title: string; folder: string; tags: string[]; text?: string }[];
  /** F3 (M6 part C4): the elements an author's own type may be shown as. */
  cardKinds?: { id: string; name: string }[];
  maps: { id: string; title: string }[];
  handouts: { number: number; kind: string; title: string; chapter: number; line: number; sheets?: number }[];
}

export interface WorldApi {
  showMessage(text: string): void;
  flash(text: string): void;
  /** After a change in the core: reload the codex, the chapter and the editor. */
  afterChange(): Promise<void>;
  /** The change was one undo step in the core (F4.12). */
  markUndoStep(): void;
  insertInline(markup: string): boolean;
  insertBlock(block: Block): void;
  goTo(chapter: number, line: number): Promise<void>;
  chapterIndex(): number;
  readOnly(): boolean;
  setHandoutsOnly(on: boolean): void;
  handoutsOnly(): boolean;
  exportHandouts(): void;
  /** F4 (M6 part C3): remember where the text was, and go back there. */
  saveSpot?(): void;
  restoreSpot?(): void;
}

let api: WorldApi;
export let codex: Codex = { types: [], entries: [], maps: [], handouts: [] };
let codexFilter = "";
let openView: { kind: "entry" | "map" | "chart" | "type"; id: string } | null = null;

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

function h<K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(text: string, cls: string, onClick: () => void): HTMLButtonElement {
  const b = h("button", cls, text);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

export function initWorld(world: WorldApi): void {
  api = world;
  $("worldview-back").addEventListener("click", () => closeView());
}

/** Reload the codex from the core and redraw what shows it. */
export async function loadCodex(): Promise<void> {
  codex = await call("codex");
  renderCodexPanel();
  renderHandoutsPanel();
  if (openView) await reopenView();
}

let listsTimer: number | null = null;

/** The text changed: handouts and their numbers may have changed too (F6.2).
 * Only the lists are redrawn; an open entry or map stays as it is. */
export function refreshListsSoon(): void {
  if (listsTimer !== null) clearTimeout(listsTimer);
  listsTimer = window.setTimeout(async () => {
    listsTimer = null;
    codex = await call("codex");
    renderHandoutsPanel();
    if (!(document.activeElement as HTMLElement | null)?.closest("#codex-panel")) renderCodexPanel();
  }, 700);
}

export function typeOf(id: string): CodexType | undefined {
  return codex.types.find((x) => x.id === id);
}

async function change(slot: string, ...args: unknown[]): Promise<any | null> {
  // F3 (M6 part C4): codex actions never fail silently.
  if (api.readOnly()) {
    api.showMessage(t("codex.readOnly"));
    return null;
  }
  const reply = await call(slot, ...args);
  if (!reply?.ok) {
    api.showMessage(reply?.error || t("error.codex.failed"));
    return null;
  }
  api.markUndoStep();
  await api.afterChange();
  return reply;
}

// --- dialogs ------------------------------------------------------------------------

/** A small dialog asking for a name, and a type when there is a choice. */
export function ask(title: string, options?: { label: string; choices?: { id: string; label: string }[]; value?: string; choiceLabel?: string }):
  Promise<{ text: string; choice: string } | null> {
  return new Promise((resolve) => {
    const dialog = $<HTMLDialogElement>("prompt-dialog");
    $("prompt-title").textContent = title;
    $("prompt-label").textContent = options?.label ?? t("codex.name");
    const input = $<HTMLInputElement>("prompt-input");
    input.value = options?.value ?? "";
    const select = $<HTMLSelectElement>("prompt-choice");
    const row = $("prompt-choice-row");
    select.textContent = "";
    row.classList.toggle("hidden", !options?.choices?.length);
    $("prompt-choice-label").textContent = options?.choiceLabel ?? t("codex.type");
    for (const c of options?.choices ?? []) {
      const o = h("option", "", c.label);
      o.value = c.id;
      select.append(o);
    }
    const done = (ok: boolean) => {
      dialog.close();
      $("prompt-ok").onclick = null;
      $("prompt-cancel").onclick = null;
      resolve(ok && input.value.trim() ? { text: input.value.trim(), choice: select.value } : null);
    };
    $("prompt-ok").onclick = (e) => {
      e.preventDefault();
      done(true);
    };
    $("prompt-cancel").onclick = (e) => {
      e.preventDefault();
      done(false);
    };
    dialog.showModal();
    input.focus();
  });
}

/** New entry (F3): ask for the type (unless given) and the name. */
export async function newEntry(type = "", title = "", folder = ""): Promise<string | null> {
  if (api.readOnly()) {
    api.showMessage(t("codex.readOnly"));
    return null;
  }
  const choices = codex.types.filter((x) => !type || x.id === type).map((x) => ({ id: x.id, label: x.name }));
  const answer = await ask(t("codex.newEntryTitle"), { label: t("codex.name"), choices: type ? [] : choices, value: title });
  if (!answer) return null;
  const reply = await change("createEntry", JSON.stringify({ type: type || answer.choice, title: answer.text, folder }));
  return reply ? reply.id : null;
}

// --- Codex sidebar (F9.3) ------------------------------------------------------------

export function renderCodexPanel(): void {
  const panel = $("codex-panel");
  panel.textContent = "";
  const tools = h("div", "codex-tools");
  const search = h("input", "codex-search");
  search.type = "search";
  search.placeholder = t("codex.search");
  search.setAttribute("aria-label", t("codex.search"));
  search.value = codexFilter;
  search.addEventListener("input", () => {
    codexFilter = search.value;
    renderCodexList(list);
  });
  tools.append(search);
  const actions = h("div", "codex-actions");
  actions.append(
    button(t("codex.newEntry"), "small-btn", () => newEntry().then((id) => { if (id) openEntry(id); })),
    button(t("codex.newMap"), "small-btn", () => newMap()),
    button(t("codex.newType"), "small-btn", () => openTypeEditor("")),
    button(t("codex.chart"), "small-btn", () => openChart()),
  );
  for (const b of actions.querySelectorAll("button")) (b as HTMLButtonElement).disabled = api.readOnly() && b.textContent !== t("codex.chart");
  tools.append(actions);
  const list = h("div", "codex-list");
  panel.append(tools, list);
  renderCodexList(list);
}

function renderCodexList(list: HTMLElement): void {
  list.textContent = "";
  const filter = codexFilter.trim().toLowerCase();
  const match = (e: Codex["entries"][number]) => !filter || e.title.toLowerCase().includes(filter) ||
    e.tags.some((tag) => tag.toLowerCase().includes(filter)) || e.folder.toLowerCase().includes(filter);
  for (const type of codex.types) {
    const entries = codex.entries.filter((e) => e.type === type.id && match(e));
    if (!entries.length && filter) continue;
    const group = h("details", "codex-group");
    group.open = true;
    const summary = h("summary", "codex-group-title", `${type.name} (${entries.length})`);
    group.append(summary);
    // F3.3: entries in folders.
    const folders = new Map<string, typeof entries>();
    for (const e of entries) folders.set(e.folder, [...(folders.get(e.folder) ?? []), e]);
    for (const [folder, items] of [...folders.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
      const ul = h("ul", "codex-items");
      if (folder) group.append(h("div", "codex-folder", "▸ " + folder));
      for (const e of items) {
        const li = h("li");
        const b = button(e.title, "codex-item" + (openView?.kind === "entry" && openView.id === e.id ? " current" : ""), () => openEntry(e.id));
        b.dataset.entry = e.id;
        b.title = e.tags.length ? e.tags.map((x) => "#" + x).join(" ") : e.title;
        li.append(b);
        ul.append(li);
      }
      group.append(ul);
    }
    list.append(group);
  }
  const maps = codex.maps.filter((m) => !filter || m.title.toLowerCase().includes(filter));
  const group = h("details", "codex-group");
  group.open = true;
  group.append(h("summary", "codex-group-title", `${t("codex.maps")} (${maps.length})`));
  const ul = h("ul", "codex-items");
  for (const m of maps) {
    const li = h("li");
    const b = button(m.title, "codex-item map-item", () => openMap(m.id));
    b.dataset.map = m.id;
    li.append(b);
    ul.append(li);
  }
  group.append(ul);
  list.append(group);
}

// --- Handouts sidebar (F6, F9.3) -------------------------------------------------------

export function renderHandoutsPanel(): void {
  const panel = $("handouts-panel");
  panel.textContent = "";
  const tools = h("div", "codex-actions");
  const toggle = button(t("toolbar.handoutsOnly"), "small-btn" + (api.handoutsOnly() ? " pressed" : ""), () => api.setHandoutsOnly(!api.handoutsOnly()));
  toggle.setAttribute("aria-pressed", String(api.handoutsOnly()));
  tools.append(toggle, button(t("handouts.export"), "small-btn", () => api.exportHandouts()));
  panel.append(tools);
  if (!codex.handouts.length) {
    panel.append(h("p", "panel-empty", t("handouts.empty")));
    return;
  }
  const ul = h("ol", "handout-list");
  for (const item of codex.handouts) {
    const li = h("li");
    const b = button("", "handout-item", () => api.goTo(item.chapter, item.line));
    b.append(h("span", "handout-number", "#" + item.number), h("span", "handout-title", item.title || t("sidebar.untitled")));
  // F6.5: the number of sheets beside a handout that needs more than one.
  if ((item.sheets ?? 1) > 1) b.append(h("span", "handout-sheets", t("sidebar.sheets", { n: String(item.sheets) })));
    if (item.kind === "map") b.append(h("span", "handout-kind", t("handouts.map")));
    li.append(b);
    ul.append(li);
  }
  panel.append(ul);
}

// --- "In this scene" panel (F3.6) ------------------------------------------------------

let sceneTimer: number | null = null;

export function updateScenePanel(line: number | null): void {
  if (sceneTimer !== null) clearTimeout(sceneTimer);
  sceneTimer = window.setTimeout(async () => {
    sceneTimer = null;
    const info = await call("sceneEntries", api.chapterIndex(), line ?? 0);
    const panel = $("scene-panel-list");
    panel.textContent = "";
    $("scene-panel-scene").textContent = info.scene ? info.scene : t("scene.none");
    if (info.scene && !info.entries.length) panel.append(h("li", "panel-empty", t("scene.noEntries")));
    for (const e of info.entries) {
      const li = h("li");
      const b = button(e.title, "codex-item", () => openEntry(e.id));
      b.prepend(h("span", "type-tag", typeOf(e.type)?.name ?? e.type));
      li.append(b);
      panel.append(li);
    }
  }, 250);
}

// --- the world view: a page in place of the editor -----------------------------------

function showView(title: string): HTMLElement {
  // Remember the place in the text before the view hides it (M6 part C3).
  if ($("worldview").classList.contains("hidden")) api.saveSpot?.();
  $("worldview").classList.remove("hidden");
  $("editor-pane").classList.add("world-open");
  $("worldview-title").textContent = title;
  const body = $("worldview-body");
  body.textContent = "";
  return body;
}

export function closeView(): void {
  const wasOpen = !$("worldview").classList.contains("hidden");
  openView = null;
  $("worldview").classList.add("hidden");
  $("editor-pane").classList.remove("world-open");
  renderCodexPanel();
  if (wasOpen) api.restoreSpot?.();
}

export function viewOpen(): { kind: string; id: string } | null {
  return openView;
}

async function reopenView(): Promise<void> {
  if (!openView) return;
  const view = openView;
  if (view.kind === "entry") {
    if (codex.entries.some((e) => e.id === view.id)) await openEntry(view.id, true);
    else closeView();
  } else if (view.kind === "map") {
    if (codex.maps.some((m) => m.id === view.id)) await openMap(view.id, true);
    else closeView();
  } else if (view.kind === "chart") {
    await openChart(true);
  }
}

// --- entry editor (F3) ----------------------------------------------------------------

let saveTimer: number | null = null;
let pendingEntry: { id: string; data: any } | null = null;

async function flushEntry(): Promise<void> {
  if (saveTimer !== null) clearTimeout(saveTimer);
  saveTimer = null;
  const job = pendingEntry;
  pendingEntry = null;
  if (!job) return;
  const reply = await call("updateEntry", JSON.stringify(job));
  if (!reply?.ok) {
    api.showMessage(reply?.error || t("error.codex.failed"));
    return;
  }
  api.markUndoStep();
  codex = await call("codex");
  renderCodexPanel();
  await api.afterChange();
}

function queueEntry(id: string, data: any): void {
  pendingEntry = { id, data: { ...(pendingEntry?.id === id ? pendingEntry.data : {}), ...data,
    fields: { ...(pendingEntry?.id === id ? pendingEntry.data.fields : {}), ...(data.fields ?? {}) } } };
  if (saveTimer !== null) clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => flushEntry(), 600);
}

export async function openEntry(id: string, keepScroll = false): Promise<void> {
  await flushEntry();
  const info = await call("entry", id);
  if (!info?.ok) {
    api.showMessage(info?.error || t("error.codex.failed"));
    return;
  }
  const type = typeOf(info.type);
  const scroll = $("worldview-body").scrollTop;
  openView = { kind: "entry", id };
  const body = showView(info.title || t("sidebar.untitled"));
  body.dataset.view = "entry";
  body.dataset.entry = id;
  const ro = api.readOnly();
  body.append(h("div", "entry-type", type?.name ?? info.type));

  const form = h("div", "entry-form");
  for (const field of type?.fields ?? []) {
    const row = h("label", "field entry-field field-" + field.name);
    row.append(h("span", "field-label", field.label + (field.required ? " *" : "")));
    row.append(entryControl(id, field, info.fields[field.name], ro));
    form.append(row);
  }
  const folder = h("label", "field entry-field");
  folder.append(h("span", "field-label", t("codex.folder")));
  const folderInput = h("input", "field-input");
  folderInput.value = info.folder ?? "";
  folderInput.disabled = ro;
  folderInput.addEventListener("input", () => queueEntry(id, { folder: folderInput.value }));
  folder.append(folderInput);
  const tags = h("label", "field entry-field");
  tags.append(h("span", "field-label", t("codex.tags")));
  const tagsInput = h("input", "field-input");
  tagsInput.value = (info.tags ?? []).join(", ");
  tagsInput.placeholder = t("codex.tagsHint");
  tagsInput.disabled = ro;
  tagsInput.addEventListener("input", () => queueEntry(id, { tags: tagsInput.value.split(",") }));
  tags.append(tagsInput);
  form.append(folder, tags);
  body.append(form);

  // F3.4: put the entry into the text in one of three ways.
  if (!ro) {
    const insert = h("div", "entry-insert");
    insert.append(h("span", "field-label", t("codex.insertInText")));
    insert.append(
      button(t("codex.insertMention"), "small-btn", () => api.insertInline(`#mention(entry: "${id}")`) || api.flash(t("codex.placeCursor"))),
      button(t("codex.insertCard"), "small-btn", () => api.insertBlock({ type: "element", kind: "card", fields: { entry: id }, body: { blocks: [], trail: "\n" } })),
      button(t("codex.insertSee"), "small-btn", () => api.insertInline(`#see(entry: "${id}")`) || api.flash(t("codex.placeCursor"))),
    );
    body.append(insert);
  }

  // F3.6: where the entry is used, computed, never stored.
  const used = h("div", "entry-used");
  used.append(h("h3", "", t("codex.whereUsed")));
  const lines: HTMLElement[] = [];
  if (info.scenes.length) lines.push(h("p", "", t("codex.inScenes", { scenes: info.scenes.join(", ") })));
  if (info.pages.length) lines.push(h("p", "", t("codex.onPages", { pages: info.pages.join(", ") })));
  // F3 (M6 part C4): a Clue entry shows who knows it.
  if (info.knownBy?.length) {
    const p = h("p", "entry-known-by", t("codex.knownBy") + " ");
    info.knownBy.forEach((k: any, i: number) => {
      if (i) p.append(", ");
      if (k.id) p.append(button(k.title, "link", () => openEntry(k.id)));
      else p.append(k.title);
    });
    lines.push(p);
  }
  if (info.backlinks.length) {
    const p = h("p", "", t("codex.linkedFrom") + " ");
    info.backlinks.forEach((b: any, i: number) => {
      if (i) p.append(", ");
      p.append(button(b.title, "link", () => openEntry(b.id)));
    });
    lines.push(p);
  }
  for (const use of info.usages.filter((u: any) => u.where === "map")) {
    const p = h("p", "", t("codex.onMap") + " ");
    p.append(button(use.title, "link", () => openMap(use.map)));
    lines.push(p);
  }
  if (!lines.length) lines.push(h("p", "panel-empty", t("codex.notUsed")));
  used.append(...lines);
  body.append(used);

  if (!ro) {
    const danger = h("div", "entry-danger");
    danger.append(button(t("codex.delete"), "small-btn danger", async () => {
      await flushEntry();
      const reply = await change("deleteEntry", id);
      if (reply) closeView();
    }));
    body.append(danger);
  }
  renderCodexPanel();
  if (keepScroll) $("worldview-body").scrollTop = scroll;
}

function entryControl(id: string, field: CodexType["fields"][number], value: any, ro: boolean): HTMLElement {
  const set = (v: any) => queueEntry(id, { fields: { [field.name]: v } });
  switch (field.kind) {
    case "rich": {
      const box = h("div", "rich field-rich");
      box.contentEditable = ro ? "false" : "true";
      box.setAttribute("role", "textbox");
      box.setAttribute("aria-label", field.label);
      box.innerHTML = inlineToHtml(String(value ?? ""));
      box.addEventListener("input", () => set(htmlToInline(box)));
      return box;
    }
    case "number": {
      const input = h("input", "field-input field-number");
      input.type = "number";
      input.value = value === undefined || value === null ? "" : String(value);
      input.disabled = ro;
      input.addEventListener("input", () => set(input.value === "" ? null : Number(input.value)));
      return input;
    }
    case "choice": {
      const select = h("select", "field-input");
      select.disabled = ro;
      select.append(h("option", "", t("editor.none")));
      (select.firstChild as HTMLOptionElement).value = "";
      for (const o of field.options ?? []) {
        const opt = h("option", "", o.label);
        opt.value = o.id;
        select.append(opt);
      }
      select.value = value ?? "";
      select.addEventListener("change", () => set(select.value || null));
      return select;
    }
    case "link":
    case "codex-list": {
      const row = h("div", "codex-picker");
      const ids: string[] = Array.isArray(value) ? value : value ? [value] : [];
      for (const target of ids) {
        const chip = h("span", "codex-chip");
        chip.append(button(codex.entries.find((e) => e.id === target)?.title ?? target, "codex-chip-name", () => openEntry(target)));
        if (!ro) chip.append(button("×", "icon-btn", async () => {
          set(ids.filter((x) => x !== target));
          await flushEntry();
        }));
        row.append(chip);
      }
      if (!ro) {
        const select = h("select", "field-input field-codex");
        select.append(h("option", "", t("editor.addEntry")));
        (select.firstChild as HTMLOptionElement).value = "";
        for (const e of codex.entries.filter((e) => e.id !== id && !ids.includes(e.id))) {
          const opt = h("option", "", `${e.title} (${typeOf(e.type)?.name ?? e.type})`);
          opt.value = e.id;
          select.append(opt);
        }
        select.addEventListener("change", async () => {
          if (!select.value) return;
          set([...ids, select.value]);
          await flushEntry();
        });
        row.append(select);
      }
      return row;
    }
    case "image": {
      const row = h("div", "field-image");
      row.append(h("span", "image-name", value ? String(value).split("/").pop()! : t("editor.noImage")));
      if (!ro) row.prepend(button(t("editor.chooseImage"), "small-btn", async () => {
        // 11.4 (M6 part C): a portrait must be a JPEG or PNG file.
        const reply = await call(field.accept === "jpeg-png" ? "addPortraitDialog" : "addImageDialog");
        if (!reply?.ok && reply?.error) api.showMessage(reply.error);
        if (reply?.ok) {
          set(reply.path);
          await flushEntry();
        }
      }));
      return row;
    }
    default: {
      const input = h("input", "field-input");
      input.value = value ?? "";
      input.disabled = ro;
      input.addEventListener("input", () => {
        set(input.value);
        if (field.name === typeOf(codex.entries.find((e) => e.id === id)?.type ?? "")?.title_field) {
          $("worldview-title").textContent = input.value;
        }
      });
      return input;
    }
  }
}

// --- codex type editor (F3.2) ------------------------------------------------------------

const FIELD_KINDS = ["text", "rich", "number", "image", "link", "choice"];

export function openTypeEditor(id: string): void {
  openView = { kind: "type", id };
  const body = showView(t("codex.newTypeTitle"));
  body.dataset.view = "type";
  const name = h("input", "field-input");
  name.placeholder = t("codex.typeName");
  const nameRow = h("label", "field entry-field");
  nameRow.append(h("span", "field-label", t("codex.typeName")), name);
  body.append(nameRow, h("p", "settings-note", t("codex.typeNote")));
  // F3 (M6 part C4): the element that shows the entry in the text; a person
  // card or a creature lets Convert to codex entry offer this type too.
  const card = h("select", "field-input type-card");
  const plain = h("option", "", t("codex.typeCardPlain"));
  plain.value = "";
  card.append(plain);
  for (const k of codex.cardKinds ?? []) {
    const o = h("option", "", k.name);
    o.value = k.id;
    card.append(o);
  }
  const cardRow = h("label", "field entry-field");
  cardRow.append(h("span", "field-label", t("codex.typeCard")), card);
  body.append(cardRow);
  const rows = h("div", "type-fields");
  const addRow = () => {
    const row = h("div", "type-field");
    const label = h("input", "field-input");
    label.placeholder = t("codex.fieldLabel");
    const kind = h("select", "field-input");
    for (const k of FIELD_KINDS) {
      const o = h("option", "", t(["codex.kind", k].join(".")));
      o.value = k;
      kind.append(o);
    }
    const options = h("input", "field-input hidden");
    options.placeholder = t("codex.choiceOptions");
    kind.addEventListener("change", () => options.classList.toggle("hidden", kind.value !== "choice"));
    row.append(label, kind, options, button("×", "icon-btn", () => row.remove()));
    rows.append(row);
  };
  addRow();
  body.append(rows, button(t("codex.addField"), "small-btn", addRow));
  const save = button(t("codex.saveType"), "primary", async () => {
    const fields = [...rows.querySelectorAll(".type-field")].map((row) => {
      const [label, kind, options] = row.querySelectorAll<HTMLInputElement | HTMLSelectElement>("input, select");
      return { label: label.value.trim(), kind: kind.value, options: options.value.split(",").map((x) => x.trim()).filter(Boolean) };
    }).filter((f) => f.label);
    const reply = await change("saveCodexType", JSON.stringify({ name: name.value, fields, card: card.value || undefined }));
    if (reply) {
      api.flash(t("codex.typeSaved", { name: name.value }));
      closeView();
    }
  });
  body.append(h("div", "dialog-actions"));
  body.lastElementChild!.append(save);
  name.focus();
}

// --- maps (F5) --------------------------------------------------------------------------

export async function newMap(): Promise<void> {
  if (api.readOnly()) {
    api.showMessage(t("codex.readOnly"));
    return;
  }
  const answer = await ask(t("map.newTitle"), { label: t("map.title") });
  if (!answer) return;
  const reply = await change("createMapDialog", answer.text);
  if (reply?.id) await openMap(reply.id);
}

type Tool = "browse" | "select" | "pin" | "label" | "area" | "note" | "line";

interface MapState {
  map: any;
  url: string | null;
  tool: Tool;
  layer: number;
  selected: { layer: number; item: number } | null;
  drawing: number[][];
  /** The pin a line starts at, when it starts at a pin (M6 part C3). */
  lineFrom: string | null;
  message: string;
}

/** F5 (M6 part C3): the number each pin prints, as the core works it out:
 * a pin keeps the number it was given; one without gets the next free one. */
export function pinNumbers(map: any): Map<string, number> {
  const pins = map.layers.flatMap((l: any) => l.items.filter((i: any) => i.type === "pin"));
  const taken = new Set<number>(pins.filter((p: any) => p.number > 0).map((p: any) => p.number));
  const out = new Map<string, number>();
  let n = 1;
  for (const p of pins) {
    if (p.number > 0) {
      out.set(p.id, p.number);
      continue;
    }
    while (taken.has(n)) n++;
    out.set(p.id, n);
    taken.add(n);
  }
  return out;
}

function nextPinNumber(map: any): number {
  return Math.max(0, ...pinNumbers(map).values()) + 1;
}

function pinById(map: any, id: string): any {
  for (const l of map.layers) for (const i of l.items) if (i.type === "pin" && i.id === id) return i;
  return null;
}

let mapState: MapState | null = null;

export async function openMap(id: string, keep = false): Promise<void> {
  const reply = await call("mapInfo", id);
  if (!reply?.ok) {
    if (reply?.error) api.showMessage(reply.error);
    return;
  }
  const previous = keep && mapState?.map.id === id ? mapState : null;
  mapState = {
    map: reply.map, url: reply.url,
    tool: previous?.tool ?? "browse",
    layer: Math.min(previous?.layer ?? 0, Math.max(0, reply.map.layers.length - 1)),
    // A reload after a save keeps what the author is in the middle of.
    selected: previous?.selected ?? null, drawing: previous?.drawing ?? [], lineFrom: previous?.lineFrom ?? null,
    message: previous?.message ?? "",
  };
  openView = { kind: "map", id };
  renderMap();
  renderCodexPanel();
}

async function saveMap(data: any): Promise<boolean> {
  const reply = await call("updateMap", JSON.stringify({ id: mapState!.map.id, ...data }));
  if (!reply?.ok) {
    if (reply?.error) {
      mapState!.message = reply.error;
      renderMap();
    }
    return false;
  }
  api.markUndoStep();
  mapState!.map = { ...mapState!.map, ...reply };
  codex = await call("codex");
  renderCodexPanel();
  await api.afterChange();
  return true;
}

function renderMap(): void {
  const st = mapState!;
  const m = st.map;
  const body = showView(m.title);
  body.dataset.view = "map";
  body.dataset.map = m.id;
  const ro = api.readOnly();

  const head = h("div", "map-head");
  const title = h("input", "field-input map-title");
  title.value = m.title;
  title.disabled = ro;
  title.setAttribute("aria-label", t("map.title"));
  title.addEventListener("change", () => saveMap({ title: title.value }));
  head.append(title);
  // F17.3 (M5): the map's description for screen readers.
  const description = h("input", "field-input map-description");
  description.value = m.description ?? "";
  description.disabled = ro;
  description.placeholder = t("map.description");
  description.setAttribute("aria-label", t("map.description"));
  description.addEventListener("change", () => saveMap({ description: description.value }));
  head.append(description);
  if (!ro) {
    head.append(button(t("map.insert"), "small-btn", () => api.insertBlock({ type: "element", kind: "map", fields: { map: m.id } })));
    head.append(button(t("map.delete"), "small-btn danger", async () => {
      const r = await change("deleteMap", m.id);
      if (r) closeView();
    }));
  }
  body.append(head);

  const tools = h("div", "map-tools seg");
  const toolNames: Tool[] = ro ? ["browse"] : ["browse", "select", "pin", "label", "area", "note", "line"];
  for (const tool of toolNames) {
    const b = button(t(["map.tool", tool].join(".")), "", () => {
      st.tool = tool;
      st.drawing = [];
      st.lineFrom = null;
      st.message = "";
      renderMap();
    });
    b.setAttribute("aria-pressed", String(st.tool === tool));
    b.dataset.tool = tool;
    tools.append(b);
  }
  body.append(tools);
  const hint = h("p", "map-hint", st.message || t(["map.hint", st.tool].join(".")));
  hint.classList.toggle("map-message", !!st.message);
  body.append(hint);

  const layout = h("div", "map-layout");
  const stage = h("div", "map-stage");
  const img = h("img", "map-image");
  if (st.url) img.src = st.url;
  img.alt = m.title;
  img.draggable = false;
  stage.append(img);
  const W = 1000;
  const H = Math.round((W * (m.height || 1)) / (m.width || 1));
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("class", "map-overlay tool-" + st.tool);
  stage.append(svg);
  drawItems(svg, W, H);
  attachMapPointer(svg, W, H);
  layout.append(stage, renderLayerPanel());
  body.append(layout);
}

function svgEl(tag: string, attrs: Record<string, string | number>): SVGElement {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  return node;
}

function drawItems(svg: SVGSVGElement, W: number, H: number): void {
  const st = mapState!;
  const numbers = pinNumbers(st.map);
  st.map.layers.forEach((layer: any, li: number) => {
    const g = svgEl("g", { class: "map-layer" + (li === st.layer ? " active" : "") });
    layer.items.forEach((item: any, ii: number) => {
      const selected = st.selected?.layer === li && st.selected.item === ii;
      const cls = "map-item item-" + item.type + (selected ? " selected" : "");
      const label = item.entry ? codex.entries.find((e) => e.id === item.entry)?.title ?? item.text : item.text;
      if (item.type === "line") {
        // F5 (M6 part C3): a line between pins follows them.
        const ends = item.from ? [pinById(st.map, item.from), pinById(st.map, item.to)] : null;
        const points: number[][] = ends ? (ends.every(Boolean) ? ends.map((p: any) => [p.x, p.y]) : []) : item.points;
        if (points.length < 2) return;
        const pts = points.map((p) => `${p[0] * W},${p[1] * H}`).join(" ");
        const line = svgEl("polyline", { points: pts, class: cls + (item.style === "dashed" ? " dashed" : "") });
        line.dataset.layer = String(li);
        line.dataset.item = String(ii);
        g.append(line);
        if (label) {
          const mid = points[Math.floor((points.length - 1) / 2)];
          const next = points[Math.floor((points.length - 1) / 2) + 1];
          const text = svgEl("text", { x: (mid[0] + next[0]) / 2 * W, y: (mid[1] + next[1]) / 2 * H - 6, class: "map-text centre" });
          text.textContent = label;
          g.append(text);
        }
        if (selected && st.tool === "select" && !item.from) {
          item.points.forEach((p: number[], pi: number) => {
            const handle = svgEl("circle", { cx: p[0] * W, cy: p[1] * H, r: 7, class: "map-handle" });
            handle.dataset.layer = String(li);
            handle.dataset.item = String(ii);
            handle.dataset.point = String(pi);
            g.append(handle);
          });
        }
      } else if (item.type === "area") {
        const pts = item.points.map((p: number[]) => `${p[0] * W},${p[1] * H}`).join(" ");
        const poly = svgEl("polygon", { points: pts, class: cls });
        poly.dataset.layer = String(li);
        poly.dataset.item = String(ii);
        g.append(poly);
        if (label) {
          const cx = item.points.reduce((a: number, p: number[]) => a + p[0], 0) / item.points.length * W;
          const cy = item.points.reduce((a: number, p: number[]) => a + p[1], 0) / item.points.length * H;
          const text = svgEl("text", { x: cx, y: cy, class: "map-text centre" });
          text.textContent = label;
          g.append(text);
        }
        if (selected && st.tool === "select") {
          item.points.forEach((p: number[], pi: number) => {
            const handle = svgEl("circle", { cx: p[0] * W, cy: p[1] * H, r: 7, class: "map-handle" });
            handle.dataset.layer = String(li);
            handle.dataset.item = String(ii);
            handle.dataset.point = String(pi);
            g.append(handle);
          });
        }
      } else {
        const x = item.x * W;
        const y = item.y * H;
        let shape: SVGElement;
        if (item.type === "pin") shape = svgEl("circle", { cx: x, cy: y, r: 10, class: cls });
        else if (item.type === "note") shape = svgEl("rect", { x: x, y: y, width: 18, height: 14, class: cls });
        else shape = svgEl("circle", { cx: x, cy: y, r: 5, class: cls });
        shape.dataset.layer = String(li);
        shape.dataset.item = String(ii);
        g.append(shape);
        if (item.type === "pin") {
          // The pin shows its number; its name goes in the key (M6 part C3).
          const num = svgEl("text", { x, y: y + 4, class: "map-pin-number" });
          num.textContent = String(numbers.get(item.id) ?? "");
          g.append(num);
        }
        if (label) {
          const text = svgEl("text", { x: item.type === "label" ? x : x + 14, y: item.type === "label" ? y - 8 : y + 5,
            class: "map-text" + (item.type === "label" ? " centre big" : "") });
          text.textContent = label;
          g.append(text);
        }
      }
    });
    svg.append(g);
  });
  if (st.drawing.length) {
    const pts = st.drawing.map((p) => `${p[0] * W},${p[1] * H}`).join(" ");
    svg.append(svgEl("polyline", { points: pts, class: "map-drawing" }));
    st.drawing.forEach((p, i) => svg.append(svgEl("circle", { cx: p[0] * W, cy: p[1] * H, r: i === 0 ? 9 : 5, class: "map-handle" + (i === 0 ? " first" : "") })));
  }
}

const AREA_MAX = 15; // F5.8: 3 to 15 corner points (decided 6 Nov 2026)

function attachMapPointer(svg: SVGSVGElement, W: number, H: number): void {
  const st = mapState!;
  const point = (e: MouseEvent) => {
    const r = svg.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
  };
  let drag: { layer: number; item: number; point: number | null; moved: boolean } | null = null;
  svg.addEventListener("mousedown", (e) => {
    const target = e.target as SVGElement;
    const [x, y] = point(e);
    const li = target.dataset.layer !== undefined ? Number(target.dataset.layer) : null;
    const ii = target.dataset.item !== undefined ? Number(target.dataset.item) : null;
    if (st.tool === "browse") {
      // F5.3: a click on a pin opens its codex entry.
      if (li !== null && ii !== null) {
        const item = st.map.layers[li].items[ii];
        if (item.entry) openEntry(item.entry);
      }
      return;
    }
    if (st.tool === "select") {
      if (li !== null && ii !== null) {
        st.selected = { layer: li, item: ii };
        drag = { layer: li, item: ii, point: target.dataset.point !== undefined ? Number(target.dataset.point) : null, moved: false };
      } else {
        st.selected = null;
      }
      renderMap();
      return;
    }
    const layer = st.map.layers[st.layer];
    if (!layer) return;
    if (st.tool === "line") {
      // F5 (M6 part C3): click two pins to join them, or click point by
      // point and double-click to finish a free line.
      const onPin = li !== null && ii !== null && st.map.layers[li].items[ii].type === "pin" ? st.map.layers[li].items[ii] : null;
      if (e.detail >= 2) return; // the double-click is handled below
      if (onPin && !st.drawing.length && !st.lineFrom) {
        st.lineFrom = onPin.id;
        st.drawing = [[onPin.x, onPin.y]];
        renderMap();
        return;
      }
      if (onPin && st.lineFrom && st.drawing.length === 1 && onPin.id !== st.lineFrom) {
        layer.items.push({ type: "line", from: st.lineFrom, to: onPin.id, text: "" });
        finishLine(layer);
        return;
      }
      st.lineFrom = null; // a free line from here on
      st.drawing.push(onPin ? [onPin.x, onPin.y] : [x, y]);
      renderMap();
      return;
    }
    if (st.tool === "area") {
      const first = st.drawing[0];
      if (first && st.drawing.length >= 3 && Math.hypot((first[0] - x) * W, (first[1] - y) * H) < 14) {
        layer.items.push({ type: "area", points: st.drawing, text: "" });
        st.drawing = [];
        st.message = "";
        st.selected = { layer: st.layer, item: layer.items.length - 1 };
        saveMap({ layers: st.map.layers }).then(() => renderMap());
        return;
      }
      if (st.drawing.length >= AREA_MAX) {
        st.message = t("map.areaFull", { maximum: AREA_MAX });
        renderMap();
        return;
      }
      st.drawing.push([x, y]);
      st.message = st.drawing.length >= AREA_MAX ? t("map.areaFull", { maximum: AREA_MAX }) : "";
      renderMap();
      return;
    }
    const placed: any = { type: st.tool, x, y, text: "" };
    if (st.tool === "pin") placed.number = nextPinNumber(st.map); // numbered in the order placed
    layer.items.push(placed);
    st.selected = { layer: st.layer, item: layer.items.length - 1 };
    st.tool = "select";
    saveMap({ layers: st.map.layers }).then(() => renderMap());
  });
  svg.addEventListener("dblclick", () => {
    if (st.tool !== "line") return;
    const layer = st.map.layers[st.layer];
    if (!layer || st.drawing.length < 2) return;
    layer.items.push({ type: "line", points: st.drawing, text: "" });
    finishLine(layer);
  });
  const finishLine = (layer: any) => {
    st.drawing = [];
    st.lineFrom = null;
    st.message = "";
    st.selected = { layer: st.layer, item: layer.items.length - 1 };
    saveMap({ layers: st.map.layers }).then(() => renderMap());
  };
  svg.addEventListener("mousemove", (e) => {
    if (!drag) return;
    const [x, y] = point(e);
    const item = st.map.layers[drag.layer].items[drag.item];
    if (drag.point !== null) item.points[drag.point] = [x, y];
    else if (item.type !== "area" && item.type !== "line") {
      item.x = x;
      item.y = y;
    } else return;
    drag.moved = true;
    svg.textContent = "";
    drawItems(svg, W, H);
  });
  const end = () => {
    if (drag?.moved) saveMap({ layers: st.map.layers }).then(() => renderMap());
    drag = null;
  };
  svg.addEventListener("mouseup", end);
  svg.addEventListener("mouseleave", end);
}

function renderLayerPanel(): HTMLElement {
  const st = mapState!;
  const ro = api.readOnly();
  const panel = h("div", "map-side");
  panel.append(h("h3", "", t("map.layers")));
  st.map.layers.forEach((layer: any, li: number) => {
    const row = h("div", "map-layer-row" + (li === st.layer ? " active" : ""));
    const pick = h("input");
    pick.type = "radio";
    pick.name = "map-layer";
    pick.checked = li === st.layer;
    pick.title = t("map.activeLayer");
    pick.addEventListener("change", () => {
      st.layer = li;
      renderMap();
    });
    const name = h("input", "field-input");
    name.value = layer.name;
    name.disabled = ro;
    name.setAttribute("aria-label", t("map.layerName"));
    name.addEventListener("change", () => {
      mapState!.map.layers[li].name = name.value;
      saveMap({ layers: mapState!.map.layers });
    });
    const show = h("label", "check");
    const box = h("input");
    box.type = "checkbox";
    box.checked = !!layer.show_in_handout;
    box.disabled = ro;
    box.addEventListener("change", () => {
      // Look the layer up now: a save may have replaced the objects.
      mapState!.map.layers[li].show_in_handout = box.checked;
      saveMap({ layers: mapState!.map.layers });
    });
    show.append(box, h("span", "", t("map.showInHandout")));
    row.append(pick, name, show);
    if (!ro && st.map.layers.length > 1) row.append(button("×", "icon-btn", () => {
      st.map.layers.splice(li, 1);
      st.layer = 0;
      saveMap({ layers: st.map.layers }).then(() => renderMap());
    }));
    panel.append(row);
  });
  if (!ro) panel.append(button(t("map.addLayer"), "small-btn", () => {
    st.map.layers.push({ name: t("map.newLayer", { n: st.map.layers.length + 1 }), show_in_handout: false, items: [] });
    st.layer = st.map.layers.length - 1;
    saveMap({ layers: st.map.layers }).then(() => renderMap());
  }));

  if (st.selected) {
    const sel = st.selected;
    const current = () => mapState!.map.layers[sel.layer]?.items[sel.item];
    const item = current();
    if (item) {
      panel.append(h("h3", "", t(["map.item", item.type].join("."))));
      const text = h("input", "field-input");
      text.value = item.text ?? "";
      text.placeholder = t(item.type === "line" ? "map.lineLabel" : "map.itemText");
      text.disabled = ro;
      text.addEventListener("change", () => {
        current().text = text.value;
        saveMap({ layers: mapState!.map.layers }).then(() => renderMap());
      });
      panel.append(text);
      if (item.type === "pin") {
        const select = h("select", "field-input");
        select.disabled = ro;
        select.append(h("option", "", t("map.noEntry")));
        (select.firstChild as HTMLOptionElement).value = "";
        for (const e of codex.entries) {
          const o = h("option", "", e.title);
          o.value = e.id;
          select.append(o);
        }
        select.value = item.entry ?? "";
        select.addEventListener("change", () => {
          const it = current();
          if (select.value) it.entry = select.value;
          else delete it.entry;
          saveMap({ layers: mapState!.map.layers }).then(() => renderMap());
        });
        panel.append(select);
        if (item.entry) panel.append(button(t("editor.openEntry"), "small-btn", () => openEntry(item.entry)));
        // M6 part C3: the pin's number and its note in the key.
        const number = h("input", "field-input map-pin-number-input");
        number.type = "number";
        number.min = "1";
        number.value = String(pinNumbers(mapState!.map).get(item.id) ?? "");
        number.disabled = ro;
        number.setAttribute("aria-label", t("map.pinNumber"));
        number.title = t("map.pinNumber");
        number.addEventListener("change", () => {
          const value = Math.floor(Number(number.value));
          if (!(value > 0)) return;
          current().number = value;
          saveMap({ layers: mapState!.map.layers }).then(() => renderMap());
        });
        const note = h("input", "field-input");
        note.value = item.note ?? "";
        note.placeholder = t("map.pinNote");
        note.disabled = ro;
        note.setAttribute("aria-label", t("map.pinNote"));
        note.addEventListener("change", () => {
          if (note.value.trim()) current().note = note.value;
          else delete current().note;
          saveMap({ layers: mapState!.map.layers }).then(() => renderMap());
        });
        panel.append(h("span", "field-label", t("map.pinNumber")), number, note);
      }
      if (item.type === "line") {
        const style = h("select", "field-input");
        style.disabled = ro;
        style.setAttribute("aria-label", t("map.lineStyle"));
        for (const s of ["solid", "dashed"]) {
          const o = h("option", "", t(["map.lineStyle", s].join(".")));
          o.value = s;
          style.append(o);
        }
        style.value = item.style ?? "solid";
        style.addEventListener("change", () => {
          if (style.value === "dashed") current().style = "dashed";
          else delete current().style;
          saveMap({ layers: mapState!.map.layers }).then(() => renderMap());
        });
        panel.append(style);
      }
      if (!ro) panel.append(button(t("map.deleteItem"), "small-btn danger", () => {
        st.map.layers[st.selected!.layer].items.splice(st.selected!.item, 1);
        st.selected = null;
        saveMap({ layers: st.map.layers }).then(() => renderMap());
      }));
    }
  }
  return panel;
}

// --- relationship chart (F3.9) --------------------------------------------------------

let chartGraph: cytoscape.Core | null = null;

export async function openChart(keep = false): Promise<void> {
  const data = await call("chart");
  openView = { kind: "chart", id: "" };
  const body = showView(t("codex.chart"));
  body.dataset.view = "chart";
  const ro = api.readOnly();
  const head = h("div", "map-head");
  if (!ro) {
    head.append(
      button(t("chart.layout"), "small-btn", () => relayout()),
      button(t("chart.insert"), "small-btn", () => api.insertBlock({ type: "element", kind: "relationship-chart", fields: {} })),
    );
  }
  body.append(head, h("p", "map-hint", t(data.nodes.length ? "chart.hint" : "chart.empty")));
  const box = h("div", "chart-stage");
  body.append(box);
  chartGraph?.destroy();
  const W = 800;
  const H = 480;
  chartGraph = cytoscape({
    container: box,
    elements: [
      ...data.nodes.map((n: any) => ({ data: { id: n.id, label: n.title, type: n.type }, position: { x: n.x * W, y: n.y * H } })),
      ...data.edges.map((e: any, i: number) => ({ data: { id: "e" + i, source: e.from, target: e.to } })),
    ],
    layout: { name: "preset" },
    autoungrabify: ro,
    userZoomingEnabled: true,
    style: [
      { selector: "node", style: { label: "data(label)", "font-size": 12, "text-valign": "center", "text-halign": "center",
        shape: "round-rectangle", width: (n: any) => Math.max(40, n.data("label").length * 7 + 16), height: 26, "background-color": "#FFFDF8",
        "border-width": 1, "border-color": "#4A2F24", color: "#2B2622" } as any },
      { selector: "node[type = 'place']", style: { "background-color": "#F1ECE2", "border-style": "double", "border-width": 3 } },
      { selector: "node[type = 'clue']", style: { "background-color": "#EEE7D8" } },
      { selector: "edge", style: { width: 1.2, "line-color": "#8A7F75", "curve-style": "straight" } },
    ],
  });
  chartGraph.fit(undefined, 30);
  // Dragging an entry saves its position, so the printed chart matches (F3.9).
  chartGraph.on("dragfree", "node", (event) => {
    const n = event.target;
    const p = n.position();
    savePositions({ [n.id()]: [p.x / W, p.y / H] });
  });
  void keep;
}

async function savePositions(positions: Record<string, number[]>): Promise<void> {
  const reply = await call("setChartPositions", JSON.stringify(positions));
  if (reply?.ok) {
    api.markUndoStep();
    await api.afterChange();
  }
}

function relayout(): void {
  if (!chartGraph) return;
  const W = 800;
  const H = 480;
  const layout = chartGraph.layout({ name: "cose", animate: false, randomize: false, boundingBox: { x1: 0, y1: 0, w: W, h: H } } as any);
  layout.run();
  const positions: Record<string, number[]> = {};
  chartGraph.nodes().forEach((n) => {
    const p = n.position();
    positions[n.id()] = [Math.min(1, Math.max(0, p.x / W)), Math.min(1, Math.max(0, p.y / H))];
  });
  chartGraph.fit(undefined, 30);
  savePositions(positions);
}

// --- F3.12: M2 text to codex links ----------------------------------------------------

export async function offerUpgrade(always: boolean): Promise<void> {
  const reply = await call("upgradeOffer");
  if (!reply.candidates.length) {
    if (always) api.showMessage(t("upgrade.nothing"));
    return;
  }
  if (!always) {
    // On opening: a quiet banner, so nothing interrupts the author (F3.12).
    if (!reply.offer) return;
    const banner = $("upgrade-banner");
    $("upgrade-banner-text").textContent = t("upgrade.banner", { count: reply.candidates.length });
    banner.classList.remove("hidden");
    $("upgrade-banner-review").onclick = () => {
      banner.classList.add("hidden");
      offerUpgrade(true);
    };
    $("upgrade-banner-later").onclick = () => banner.classList.add("hidden");
    return;
  }
  $("upgrade-banner").classList.add("hidden");
  const dialog = $<HTMLDialogElement>("upgrade-dialog");
  const list = $("upgrade-list");
  list.textContent = "";
  const rows: { c: any; check: HTMLInputElement; type: HTMLSelectElement | null }[] = [];
  for (const c of reply.candidates) {
    const tr = h("tr");
    const check = h("input");
    check.type = "checkbox";
    check.checked = true;
    const td0 = h("td");
    td0.append(check);
    const where = h("td", "", t(["upgrade.field", c.element, c.field].join(".")) + " · " + t("upgrade.line", { line: c.line }));
    const value = h("td", "upgrade-value", c.value);
    const proposal = h("td");
    let type: HTMLSelectElement | null = null;
    if (c.match) {
      proposal.textContent = t("upgrade.linkTo", { title: c.matchTitle });
    } else if (c.typeFixed) {
      proposal.textContent = t("upgrade.create", { type: typeOf(c.type)?.name ?? c.type });
    } else {
      proposal.append(t("upgrade.createAs") + " ");
      type = h("select", "field-input");
      for (const x of codex.types) {
        const o = h("option", "", x.name);
        o.value = x.id;
        type.append(o);
      }
      type.value = c.type;
      proposal.append(type);
    }
    tr.append(td0, where, value, proposal);
    list.append(tr);
    rows.push({ c, check, type });
  }
  dialog.showModal();
  $("upgrade-apply").onclick = async (e) => {
    e.preventDefault();
    dialog.close();
    const choices = rows.map((r) => ({ key: r.c.key, accept: r.check.checked, type: r.type ? r.type.value : r.c.type }));
    const done = await change("applyUpgrade", JSON.stringify(choices));
    if (done) api.flash(t("upgrade.done", { linked: done.linked, created: done.created }));
  };
  $("upgrade-later").onclick = (e) => {
    e.preventDefault();
    dialog.close();
  };
}

// Hooks for the automated interface tests.
export const worldTest = {
  codex: () => codex,
  openEntry,
  openMap,
  openChart,
  closeView,
  viewOpen,
  mapState: () => mapState,
  setTool: (tool: Tool) => {
    if (mapState) {
      mapState.tool = tool;
      renderMap();
    }
  },
  chartPositions: () => chartGraph?.nodes().map((n) => ({ id: n.id(), ...n.position() })) ?? [],
  /** As if the author dragged an entry in the chart and let go. */
  moveChartNode: (id: string, x: number, y: number) => {
    const node = chartGraph?.getElementById(id);
    if (!node || node.empty()) return false;
    node.position({ x, y });
    node.emit("dragfree");
    return true;
  },
};
