// Milestone 4: the app's own look and the revised window frame.
//
//  - App palettes and light/dark mode (F16): the palette's colours become CSS
//    variables; Light, Dark or Follow the computer; New palette from this one
//    with a colour picker for every colour; a palette's own stylesheet.
//  - The Settings window (F18): Application, Colours, Modules and Adventure.
//  - The toolbar's insert groups (F9, revised 6 Nov 2026) and the small
//    Light / Dark switch at the right end of the menu bar.

import { call, on } from "./bridge";
import { t } from "./i18n";
import { ElementDef } from "./model";
import iconStructure from "./icons/tree-structure.svg";
import iconBoxes from "./icons/frame-corners.svg";
import iconPeople from "./icons/users-three.svg";
import iconRules from "./icons/dice-five.svg";
import iconHandouts from "./icons/scroll.svg";
import iconTable from "./icons/table.svg";
import iconImage from "./icons/image.svg";
import iconSun from "./icons/sun.svg";
import iconMoon from "./icons/moon.svg";
import iconCaret from "./icons/caret-down.svg";

export interface ShellMenuItem {
  label: string;
  action?: () => void;
  shortcut?: string;
  disabled?: boolean;
  heading?: boolean;
  children?: ShellMenuItem[];
  foot?: boolean;
}

export interface ShellContext {
  defs: () => ElementDef[];
  hasDocument: () => boolean;
  readOnly: () => boolean;
  insert: (kind: string, variant?: string) => void;
  showPopup: (anchor: HTMLElement, items: ShellMenuItem[]) => void;
  newEntry: () => void;
  newMap: () => void;
  styleOfFocus: () => string | null;
  /** The paragraph styles offered at the cursor (Sub-heading 1–3 inside a scene, M6 part C). */
  styleKinds: () => string[];
  /** A kind's name in menus: "Sub-heading 1" for heading-3 and so on. */
  kindLabel: (kind: string) => string;
  setStyle: (kind: string) => void;
  fillAdventure: () => Promise<void>;
  refresh: () => Promise<void>;
  adventureName: () => string | null;
  addFont: () => void;
  onStartMode: (mode: string) => void;
}

let ctx: ShellContext;
let app: any = null; // the core's app settings, palettes and modules

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

function h<K extends keyof HTMLElementTagNameMap>(tag: K, cls?: string, text?: string): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = text;
  return el;
}

function icon(svg: string): HTMLElement {
  const span = h("span", "icon-svg");
  span.setAttribute("aria-hidden", "true");
  span.innerHTML = svg; // bundled Phosphor drawing, never user content
  span.style.display = "inline-flex";
  return span;
}

// --- palettes and light/dark (F16) -----------------------------------------------------

/** Whether the window is drawn dark now. */
export function isDark(): boolean {
  if (!app) return false;
  const mode = app.values.mode;
  return mode === "dark" || (mode === "system" && !!app.systemDark);
}

/** Put the palette's colours on the window; nothing on the page preview changes. */
export function applyAppearance(preview?: { light: Record<string, string>; dark: Record<string, string> }): void {
  if (!app) return;
  const dark = isDark();
  const root = document.documentElement;
  const palette = app.palette;
  const vars: Record<string, string> = preview
    ? toVars(dark ? preview.dark : preview.light)
    : palette ? (dark ? palette.darkVars : palette.lightVars) : {};
  for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value);
  root.dataset.mode = dark ? "dark" : "light";
  root.style.setProperty("--ui-size", `${app.values.ui_size}px`);
  root.style.setProperty("--editor-size", `${app.values.editor_size}px`);
  // A palette's own window stylesheet (palette.css), unless Shift was held
  // at start; it was checked for internet addresses at install.
  let style = document.getElementById("palette-css") as HTMLStyleElement | null;
  if (!style) {
    style = document.createElement("style");
    style.id = "palette-css";
    document.head.append(style);
  }
  style.textContent = palette?.css ?? "";
  renderModeSwitch();
}

const CSS_VARS: Record<string, string> = {
  window: "--bg", bar: "--bar", sidebar: "--panel", editor: "--paper", input: "--input", line: "--line",
  "line-strong": "--line-strong", text: "--ink", "text-2": "--ink-2", muted: "--quiet", faint: "--faint",
  claret: "--accent", "on-claret": "--on-accent", "claret-text": "--accent-ink", "claret-tint": "--accent-tint",
  teal: "--focus", "teal-text": "--focus-text", green: "--ok", frame: "--frame", ochre: "--ochre",
  secret: "--secret", public: "--public", hint: "--hint", error: "--error", preview: "--preview-bg",
};

function toVars(colours: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(colours)) if (CSS_VARS[k]) out[CSS_VARS[k]] = v;
  return out;
}

// The same contrast rule as the core (scriptorum/core/palettes.py, T-UI-20).
const TEXT_PAIRS: [string, string][] = [
  ["text", "window"], ["text", "bar"], ["text", "sidebar"], ["text", "editor"], ["text", "input"], ["text", "claret-tint"],
  ["text-2", "window"], ["text-2", "sidebar"], ["text-2", "editor"],
  ["muted", "window"], ["muted", "bar"], ["muted", "sidebar"], ["muted", "editor"],
  ["claret-text", "window"], ["claret-text", "sidebar"], ["claret-text", "editor"], ["claret-text", "claret-tint"],
  ["on-claret", "claret"], ["teal-text", "editor"], ["teal-text", "sidebar"],
  ["secret", "editor"], ["public", "editor"], ["hint", "editor"], ["error", "editor"], ["ochre", "editor"],
];

function luminance(hex: string): number {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}

export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

function lowContrast(colours: Record<string, string>): { text: string; background: string; ratio: number }[] {
  const out = [];
  for (const [fg, bg] of TEXT_PAIRS) {
    if (colours[fg] && colours[bg]) {
      const ratio = contrast(colours[fg], colours[bg]);
      if (ratio < 4.5) out.push({ text: fg, background: bg, ratio: Math.round(ratio * 100) / 100 });
    }
  }
  return out;
}

async function setApp(changes: Record<string, unknown>): Promise<void> {
  app = await call("setAppSettings", JSON.stringify(changes));
  applyAppearance();
  if (currentSection) renderSection(currentSection);
}

/** The small Light / Dark switch at the right end of the menu bar (F9, F16). */
function renderModeSwitch(): void {
  const host = document.getElementById("mode-switch");
  if (!host) return;
  const dark = isDark();
  for (const button of host.querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String((button.dataset.mode === "dark") === dark));
  }
}

export function modeSwitch(): HTMLElement {
  const wrap = h("div", "menu-end");
  const group = h("div", "mode-switch");
  group.id = "mode-switch";
  group.setAttribute("role", "group");
  group.setAttribute("aria-label", t("settings.mode"));
  for (const [mode, svg] of [["light", iconSun], ["dark", iconMoon]] as const) {
    const button = h("button");
    button.type = "button";
    button.dataset.mode = mode;
    button.title = t(`settings.mode.${mode}`);
    button.setAttribute("aria-label", t(`settings.mode.${mode}`));
    button.append(icon(svg));
    button.addEventListener("click", () => setApp({ mode }));
    group.append(button);
  }
  wrap.append(group);
  setTimeout(renderModeSwitch, 0);
  return wrap;
}

// --- toolbar insert groups (F9) ---------------------------------------------------------

const GROUPS: { id: string; icon: string }[] = [
  { id: "structure", icon: iconStructure },
  { id: "boxes", icon: iconBoxes },
  { id: "people", icon: iconPeople },
  { id: "rules", icon: iconRules },
  { id: "handouts", icon: iconHandouts },
];

// The order inside each group, as in the design document (F9).
const GROUP_ORDER: Record<string, string[]> = {
  // F4 (M6 part C): the three sub-heading levels follow the scene.
  structure: ["heading", "scene", "heading-3", "heading-4", "heading-5", "scene-end", "page-break", "column-break"],
  boxes: ["read-aloud", "information:secret", "information:public", "information:hint", "box", "quote"],
  people: ["person", "creature", "card", "mention", "see"],
  rules: ["check", "dice", "countdown", "pacing"],
  handouts: ["handout", "map", "relationship-chart"],
};

/** The items of one insert group: only the elements the game system turns on. */
export function groupItems(group: string): ShellMenuItem[] {
  const defs = ctx.defs();
  const items: ShellMenuItem[] = [];
  for (const entry of GROUP_ORDER[group] ?? []) {
    const [kind, variant] = entry.split(":");
    if (kind === "heading" || kind.startsWith("heading-") || kind === "scene-end") {
      items.push({ label: ctx.kindLabel(kind), action: () => ctx.insert(kind) });
      continue;
    }
    const def = defs.find((d) => d.id === kind);
    if (!def) continue;
    const label = variant ? t(`toolbar.item.information.${variant}`) : def.name;
    items.push({ label, action: () => ctx.insert(kind, variant), shortcut: variant && variant !== "secret" ? undefined : def.shortcut ?? undefined });
  }
  // New codex entries and maps are made from the foot of these two groups.
  if (group === "people" && items.length) items.push({ label: t("toolbar.newEntry"), action: () => ctx.newEntry(), foot: true });
  if (group === "handouts" && items.some((i) => i.label === defs.find((d) => d.id === "map")?.name)) {
    items.push({ label: t("toolbar.newMap"), action: () => ctx.newMap(), foot: true });
  }
  return items;
}

export function renderToolbar(): void {
  const host = $("tb-groups");
  host.textContent = "";
  const ro = ctx.readOnly();
  for (const group of GROUPS) {
    const items = groupItems(group.id);
    if (!items.filter((i) => !i.foot).length) continue; // a group with none is hidden
    const button = h("button", "tb-group");
    button.type = "button";
    button.id = `tb-group-${group.id}`;
    button.disabled = ro;
    button.setAttribute("aria-haspopup", "true");
    button.append(icon(group.icon), h("span", undefined, t(`toolbar.group.${group.id}`)));
    const caret = icon(iconCaret);
    caret.classList.add("caret");
    button.append(caret);
    button.addEventListener("click", () => ctx.showPopup(button, groupItems(group.id)));
    host.append(button);
  }
  for (const [id, svg, kind] of [["tb-table", iconTable, "table"], ["tb-image", iconImage, "image"]] as const) {
    const button = h("button", "tb-plain");
    button.type = "button";
    button.id = id;
    button.disabled = ro;
    button.append(icon(svg), h("span", undefined, t(`toolbar.${kind}`)));
    button.addEventListener("click", () => ctx.insert(kind));
    host.append(button);
  }
  renderStyle();
}

/** The paragraph style of the block at the cursor (F9). */
export function renderStyle(): void {
  const select = $<HTMLSelectElement>("tb-style");
  if (!select) return;
  const current = ctx.styleOfFocus();
  const kinds = ctx.styleKinds();
  select.textContent = "";
  for (const kind of kinds) {
    const o = h("option", undefined, ctx.kindLabel(kind));
    o.value = kind;
    select.append(o);
  }
  if (current && !kinds.includes(current)) {
    const o = h("option", undefined, current);
    o.value = "other";
    select.append(o);
    select.value = "other";
    select.disabled = true;
  } else {
    select.value = current ?? "paragraph";
    select.disabled = current === null || ctx.readOnly();
  }
}

// --- the Settings window (F18) -------------------------------------------------------------

let currentSection: string | null = null;

export async function openSettingsWindow(section?: string): Promise<void> {
  app = await call("appSettings");
  renderFoot();
  const name = ctx.adventureName();
  $("sn-adventure").toggleAttribute("disabled", !name);
  $("sn-adventure-name").textContent = name ?? t("settings.noAdventure");
  let wanted = section ?? currentSection ?? "application";
  if (wanted === "adventure" && !name) wanted = "application";
  $("settings").classList.remove("hidden");
  await showSection(wanted);
}

export async function showSection(section: string): Promise<void> {
  currentSection = section;
  for (const button of document.querySelectorAll<HTMLButtonElement>(".settings-nav button")) {
    button.setAttribute("aria-selected", String(button.dataset.section === section));
  }
  for (const page of document.querySelectorAll<HTMLElement>(".settings-page")) {
    page.classList.toggle("hidden", page.id !== `sp-${section}`);
  }
  await renderSection(section);
}

export function settingsSection(): string | null {
  return $("settings").classList.contains("hidden") ? null : currentSection;
}

async function renderSection(section: string): Promise<void> {
  if (section === "application") renderApplication();
  else if (section === "colours") renderColours();
  else if (section === "modules") renderModules();
  else if (section === "adventure") await ctx.fillAdventure();
}

function row(label: string, control: HTMLElement): HTMLElement {
  const r = h("label", "settings-row");
  r.append(h("span", undefined, label), control);
  return r;
}

function select(options: [string, string][], value: string, onChange: (v: string) => void, id?: string): HTMLSelectElement {
  const s = h("select");
  if (id) s.id = id;
  for (const [v, label] of options) {
    const o = h("option", undefined, label);
    o.value = v;
    s.append(o);
  }
  s.value = value;
  s.addEventListener("change", () => onChange(s.value));
  return s;
}

function numberInput(value: number, min: number, max: number, onChange: (v: number) => void, id?: string): HTMLInputElement {
  const input = h("input");
  input.type = "number";
  if (id) input.id = id;
  input.min = String(min);
  input.max = String(max);
  input.value = String(value);
  input.addEventListener("change", () => onChange(Number(input.value)));
  return input;
}

function renderApplication(): void {
  const page = $("sp-application");
  page.textContent = "";
  const v = app.values;
  page.append(h("h3", undefined, t("settings.app.editor")));
  page.append(row(t("settings.app.spell"), select(
    [["sv", t("settings.app.spell.sv")], ["en", t("settings.app.spell.en")], ["en-gb", t("settings.app.spell.en-gb")]],
    v.spell_language, (x) => setApp({ spell_language: x }), "app-spell")));
  page.append(row(t("settings.app.startMode"), select(
    [["visual", t("toolbar.visual")], ["hybrid", t("toolbar.hybrid")], ["source", t("toolbar.source")]],
    v.start_mode, (x) => { setApp({ start_mode: x }); ctx.onStartMode(x); }, "app-startMode")));
  page.append(h("h3", undefined, t("settings.app.files")));
  page.append(row(t("settings.app.snapshotMinutes"), numberInput(v.snapshot_minutes, 1, 120, (x) => setApp({ snapshot_minutes: x }), "app-snapshotMinutes")));
  page.append(row(t("settings.app.snapshotKeep"), numberInput(v.snapshot_keep, 1, 200, (x) => setApp({ snapshot_keep: x }), "app-snapshotKeep")));
  const logs = h("div", "settings-row");
  const open = h("button", "small-btn", t("settings.app.openLogs"));
  open.type = "button";
  open.id = "app-openLogs";
  open.addEventListener("click", () => call("openCrashLogFolder"));
  logs.append(h("span", undefined, t("settings.app.crashLogs")), h("code", undefined, app.crashLogs), open);
  page.append(logs);
  // F21 (M6 part C): the weekly update check, off by default.
  page.append(h("h3", undefined, t("settings.app.updates")));
  const weekly = h("input");
  weekly.type = "checkbox";
  weekly.id = "app-updateWeekly";
  weekly.checked = !!v.update_weekly;
  weekly.addEventListener("change", () => setApp({ update_weekly: weekly.checked }));
  const label = h("label", "settings-check");
  label.append(weekly, h("span", undefined, t("settings.app.updateWeekly")));
  page.append(label, h("p", "settings-note", t("settings.app.updateNote")));
  page.append(h("h3", undefined, t("settings.app.language")));
  page.append(row(t("settings.app.interfaceLanguage"), select(
    app.languages.map((l: any) => [l.id, l.name]), v.language, (x) => setApp({ language: x }), "app-language")));
}

let editing: { name: string; light: Record<string, string>; dark: Record<string, string> } | null = null;

function swatches(p: any, dark: boolean): HTMLElement {
  const box = h("div", "palette-swatches");
  const c = dark ? p.dark : p.light;
  for (const k of ["window", "sidebar", "editor", "claret", "teal", "green"]) {
    const s = h("span");
    s.style.background = c[k] ?? "transparent";
    box.append(s);
  }
  return box;
}

function renderColours(): void {
  const page = $("sp-colours");
  page.textContent = "";
  const v = app.values;
  page.append(h("h3", undefined, t("settings.colours.palette")));
  const list = h("div", "palette-list");
  for (const p of app.palettes) {
    const card = h("button", "palette-card");
    card.type = "button";
    card.dataset.palette = p.id;
    card.setAttribute("aria-pressed", String(app.palette && p.id === app.palette.id));
    card.append(swatches(p, isDark()), h("div", undefined, p.name));
    card.addEventListener("click", () => setApp({ palette: p.id }));
    list.append(card);
  }
  page.append(list);
  const modes = h("div", "seg-choice");
  modes.id = "app-mode";
  for (const mode of ["light", "dark", "system"]) {
    const b = h("button", undefined, t(`settings.mode.${mode}`));
    b.type = "button";
    b.dataset.mode = mode;
    b.setAttribute("aria-pressed", String(v.mode === mode));
    b.addEventListener("click", () => setApp({ mode }));
    modes.append(b);
  }
  page.append(row(t("settings.mode"), modes));
  page.append(row(t("settings.colours.uiSize"), numberInput(v.ui_size, 11, 18, (x) => setApp({ ui_size: x }), "app-uiSize")));
  page.append(row(t("settings.colours.editorSize"), numberInput(v.editor_size, 12, 24, (x) => setApp({ editor_size: x }), "app-editorSize")));
  const buttons = h("div", "settings-row");
  const fresh = h("button", "small-btn", t("settings.colours.newPalette"));
  fresh.type = "button";
  fresh.id = "app-newPalette";
  fresh.addEventListener("click", () => {
    const p = app.palette;
    editing = { name: t("settings.colours.copyName", { name: p.name }), light: { ...p.light }, dark: { ...p.dark } };
    editingDirty = false;
    footNote("");
    renderColours();
  });
  const reset = h("button", "small-btn", t("settings.colours.reset"));
  reset.type = "button";
  reset.id = "app-resetPalette";
  reset.addEventListener("click", async () => {
    editing = null;
    editingDirty = false;
    footNote("");
    app = await call("resetPalette");
    applyAppearance();
    renderColours();
  });
  buttons.append(fresh, reset);
  page.append(buttons);
  if (app.skipCss) page.append(h("p", "quiet-warning", t("settings.colours.cssSkipped")));
  if (editing) page.append(paletteEditor());
  renderFoot();
}

// --- the foot of the Settings window (F16, decided 11 Nov 2026, M5) ----------------------
// While a new palette is being edited, its Save and Cancel buttons sit at the
// foot of the Settings window, next to Done, so they are always in view
// however long the list of colours is.

let editingDirty = false;

function footNote(text: string, quiet = false): void {
  const note = $("settings-foot-note");
  note.textContent = text;
  note.classList.toggle("quiet", quiet);
}

function renderFoot(): void {
  $("palette-save").classList.toggle("hidden", !editing);
  $("palette-cancel").classList.toggle("hidden", !editing);
  const note = $("settings-foot-note");
  if (editing && (!note.textContent || note.classList.contains("quiet"))) footNote(t("settings.colours.editingNote"), true);
  if (!editing && note.classList.contains("quiet")) footNote("");
}

/** Save the palette being edited. A save that fails shows its reason at the
 * foot of the window, and the colours stay as they are. */
async function savePalette(): Promise<boolean> {
  if (!editing) return true;
  const reply = await call("savePalette", JSON.stringify(editing));
  if (!reply?.ok) {
    footNote(t("settings.colours.saveFailed", { reason: reply?.error ?? "" }));
    return false;
  }
  editing = null;
  editingDirty = false;
  footNote("");
  app = reply;
  applyAppearance();
  if (currentSection === "colours") renderColours();
  else renderFoot();
  return true;
}

function cancelPalette(): void {
  editing = null;
  editingDirty = false;
  footNote("");
  applyAppearance();
  if (currentSection === "colours") renderColours();
  else renderFoot();
}

/** A question with up to three answers. */
export function ask(text: string, yes: string, no: string, cancel: string): Promise<"yes" | "no" | "cancel"> {
  const dialog = $<HTMLDialogElement>("ask-dialog");
  $("ask-text").textContent = text;
  $("ask-yes").textContent = yes;
  $("ask-no").textContent = no;
  $("ask-no").classList.toggle("hidden", !no); // a question with two answers
  $("ask-cancel").textContent = cancel;
  return new Promise((resolve) => {
    const done = (answer: "yes" | "no" | "cancel") => {
      dialog.close();
      resolve(answer);
    };
    $("ask-yes").onclick = () => done("yes");
    $("ask-no").onclick = () => done("no");
    $("ask-cancel").onclick = () => done("cancel");
    dialog.oncancel = (event) => {
      event.preventDefault();
      done("cancel");
    };
    dialog.showModal();
  });
}

/** Closing Settings with unsaved colours asks whether to save them. Returns
 * false when the window should stay open. */
export async function beforeCloseSettings(): Promise<boolean> {
  if (!editing) return true;
  if (!editingDirty) {
    cancelPalette();
    return true;
  }
  const answer = await ask(t("settings.colours.unsaved"), t("settings.colours.save"), t("settings.colours.discard"), t("settings.colours.keepEditing"));
  if (answer === "cancel") return false;
  if (answer === "no") {
    cancelPalette();
    return true;
  }
  return savePalette();
}

/** New palette from this one (F16): a colour picker for each colour of light
 * and dark mode; the window updates live; low contrast gives a quiet warning. */
function paletteEditor(): HTMLElement {
  const box = h("div", "palette-editor");
  box.id = "palette-editor";
  box.append(h("h3", undefined, t("settings.colours.newPalette")));
  const name = h("input");
  name.type = "text";
  name.id = "palette-name";
  name.value = editing!.name;
  name.addEventListener("input", () => {
    editing!.name = name.value;
    editingDirty = true;
  });
  box.append(row(t("settings.colours.name"), name));
  const grid = h("div", "picker-grid");
  grid.append(h("span", "picker-head", ""), h("span", "picker-head", t("settings.mode.light")), h("span", "picker-head", t("settings.mode.dark")));
  const warning = h("div");
  warning.id = "palette-warning";
  const update = () => {
    applyAppearance({ light: editing!.light, dark: editing!.dark });
    const low = [...lowContrast(editing!.light), ...lowContrast(editing!.dark)];
    warning.textContent = "";
    if (low.length) {
      const first = low[0];
      warning.append(h("p", "quiet-warning", t("settings.colours.lowContrast", {
        count: low.length, text: t(`palette.token.${first.text}`), background: t(`palette.token.${first.background}`), ratio: String(first.ratio),
      })));
    }
  };
  for (const token of app.tokens as string[]) {
    grid.append(h("span", undefined, t(`palette.token.${token}`)));
    for (const mode of ["light", "dark"] as const) {
      const input = h("input");
      input.type = "color";
      input.dataset.token = token;
      input.dataset.mode = mode;
      input.value = (editing![mode][token] ?? "#000000").toLowerCase();
      input.addEventListener("input", () => {
        editing![mode][token] = input.value.toUpperCase();
        editingDirty = true;
        update();
      });
      grid.append(input);
    }
  }
  box.append(grid, warning);
  // Save and Cancel are at the foot of the Settings window, next to Done (M5).
  setTimeout(update, 0);
  return box;
}

// --- the module manager (F14; M6 part A) ---------------------------------------------
let moduleStatus: { text: string; warn: boolean } | null = null;

function setModuleStatus(text: string, warn = false): void {
  moduleStatus = text ? { text, warn } : null;
  const note = document.getElementById("module-status");
  if (note) {
    note.textContent = text;
    note.classList.toggle("warn", warn);
  }
}

/** A reply of the module manager: the new lists on success, the reason on refusal. */
async function moduleReply(reply: any, done?: (reply: any) => string): Promise<void> {
  if (reply?.cancelled) {
    setModuleStatus("");
    return;
  }
  if (reply?.ok === false) {
    setModuleStatus(reply.error ?? "", true);
    return;
  }
  if (reply?.modules) app = reply;
  moduleStatus = done ? { text: done(reply), warn: false } : null;
  applyAppearance();
  renderModules();
  await ctx.refresh(); // an open adventure may have entered or left protected mode
}

async function installModule(path?: string): Promise<void> {
  setModuleStatus(t("settings.modules.checking"));
  const reply = path ? await call("installModulePath", path) : await call("installModuleDialog");
  await moduleReply(reply, (r) => t(r.status === "already" ? "settings.modules.installed.already" : "settings.modules.installed.done",
    { name: r.module.name, version: r.module.version }));
}

function usedByText(m: any): string {
  if (!m.content) return "";
  const names = (m.usedBy ?? []).map((a: any) => a.title).join(", ");
  return names ? t("settings.modules.confirm.usedBy", { adventures: names }) : t("settings.modules.confirm.usedByNone");
}

async function disableModule(m: any, disabled: boolean): Promise<void> {
  if (disabled) {
    const text = [t("settings.modules.confirm.disable", { name: m.name, version: m.version }), usedByText(m)].filter(Boolean).join(" ");
    if ((await ask(text, t("settings.modules.disable"), "", t("dialog.cancel"))) !== "yes") return;
  }
  await moduleReply(await call("setModuleDisabled", m.id, m.version, disabled));
}

async function removeModule(m: any): Promise<void> {
  const text = [t("settings.modules.confirm.remove", { name: m.name, version: m.version }), usedByText(m)].filter(Boolean).join(" ");
  if ((await ask(text, t("settings.modules.remove"), "", t("dialog.cancel"))) !== "yes") return;
  await moduleReply(await call("removeModule", m.id, m.version));
}

async function saveModule(m: any, path?: string): Promise<void> {
  const reply = path ? await call("saveModuleTo", m.id, m.version, path) : await call("saveModuleDialog", m.id, m.version);
  if (reply?.cancelled) return;
  if (reply?.ok === false) setModuleStatus(reply.error ?? "", true);
  else setModuleStatus(t("settings.modules.saved", { path: reply.path }));
}

function moduleButton(label: string, action: string, m: any, enabled: boolean, reason: string, run: () => void): HTMLButtonElement {
  const button = h("button", undefined, label);
  button.type = "button";
  button.dataset.action = action;
  button.dataset.module = `${m.id}@${m.version}`;
  button.disabled = !enabled;
  if (!enabled && reason) button.title = reason;
  button.addEventListener("click", run);
  return button;
}

function renderModules(): void {
  const page = $("sp-modules");
  page.textContent = "";
  page.append(h("h3", undefined, t("settings.modules.installed")), h("p", "settings-note", t("settings.modules.note")));
  const tools = h("div", "module-tools");
  const install = h("button", "primary", t("settings.modules.install"));
  install.type = "button";
  install.id = "module-install";
  install.addEventListener("click", () => installModule());
  const status = h("p", "module-status" + (moduleStatus?.warn ? " warn" : ""), moduleStatus?.text ?? "");
  status.id = "module-status";
  status.setAttribute("role", "status");
  tools.append(install, status);
  page.append(tools);
  const table = h("table", "module-table");
  const head = h("tr");
  for (const k of ["name", "kind", "version", "usedBy", "actions"]) head.append(h("th", undefined, t(`settings.modules.${k}`)));
  table.append(head);
  for (const m of app.modules) {
    const tr = h("tr", m.disabled ? "is-disabled" : undefined);
    tr.dataset.module = `${m.id}@${m.version}`;
    const name = h("td");
    const title = h("div", "module-name", m.name);
    if (m.bundled) title.append(h("span", "module-tag", t("settings.modules.tag.bundled")));
    if (m.disabled) title.append(h("span", "module-tag", t("settings.modules.tag.disabled")));
    if (m.inUse) title.append(h("span", "module-tag", t("settings.modules.tag.inUse")));
    const about = h("div", "module-about module-desc", m.description ?? "");
    about.title = m.description ?? ""; // the whole text on hover; two lines in the list
    name.append(title, h("div", "module-about", m.id), about);
    const used = h("td", "module-used", m.content ? ((m.usedBy ?? []).map((a: any) => a.title).join(", ") || t("settings.modules.usedBy.none")) : "");
    const actions = h("div", "module-actions");
    const reason = (key: string) => (key ? t(`settings.modules.reason.${key}`) : "");
    actions.append(
      m.disabled
        ? moduleButton(t("settings.modules.enable"), "enable", m, true, "", () => disableModule(m, false))
        : moduleButton(t("settings.modules.disable"), "disable", m, m.canDisable, reason(m.disableReason), () => disableModule(m, true)),
      moduleButton(t("settings.modules.remove"), "remove", m, m.canRemove, reason(m.removeReason), () => removeModule(m)),
      moduleButton(t("settings.modules.save"), "save", m, m.canSave, reason("bundledSave"), () => saveModule(m)),
    );
    const cell = h("td");
    cell.append(actions);
    tr.append(name, h("td", undefined, t(`settings.modules.kind.${m.kind}`)), h("td", undefined, m.version), used, cell);
    table.append(tr);
  }
  page.append(table);
}

export function appValues(): any {
  return app?.values ?? null;
}

export async function initShell(context: ShellContext): Promise<void> {
  ctx = context;
  app = await call("appSettings");
  applyAppearance();
  on("appearanceChanged", (data: any) => {
    if (!app) return;
    app.systemDark = data.systemDark;
    applyAppearance();
  });
  for (const button of document.querySelectorAll<HTMLButtonElement>(".settings-nav button")) {
    button.addEventListener("click", () => showSection(button.dataset.section!));
  }
  $("palette-save").addEventListener("click", () => savePalette());
  $("palette-cancel").addEventListener("click", () => cancelPalette());
}

export const shellTest = {
  app: () => app,
  setApp,
  editing: () => editing,
  editingDirty: () => editingDirty,
  installModule,
  saveModule: (key: string, path: string) => saveModule(app.modules.find((m: any) => `${m.id}@${m.version}` === key), path),
  moduleStatus: () => moduleStatus,
  startEditing: (name: string) => {
    const p = app.palette;
    editing = { name, light: { ...p.light }, dark: { ...p.dark } };
    editingDirty = true;
    renderFoot();
  },
};
