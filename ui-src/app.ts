// Scriptorum main window (F9 window frame; Milestone 2: writing and safety;
// Milestone 3: world-building, see world.ts).

import { applyZoom, currentZoom, initZoom, isSpread, loadZoom, rememberZoom, setSpread, setZoom, zoomPercent, zoomStep } from "./preview";
import { call, connect, on } from "./bridge";
import { applyStrings, setStrings, t } from "./i18n";
import { openGuide, wireGuide } from "./guide";
import iconCornersIn from "./icons/corners-in.svg";
import iconCornersOut from "./icons/corners-out.svg";
import { aboutTest, initAbout, openAbout } from "./about";
import { dragging, DropTarget, startDrag } from "./drag";
import { EditorHooks, isSubHeading, kindOf, Place, SourceEditor, SUB_HEADINGS, VisualEditor } from "./editor";
import { escapeInline, setChipLabeler, setInlineKinds } from "./inline";
import { Block, Chapter, Doc, ElementDef, isDoc, OutlineItem } from "./model";
import { Spelling } from "./spell";
import {
  appValues, applyAppearance, beforeCloseSettings, groupItems, initShell, modeSwitch, openSettingsWindow, renderStyle, renderToolbar,
  settingsSection, shellTest, showSection,
  ask as askChoice,
} from "./shell";
import {
  ask, closeView, codex, initWorld, loadCodex, refreshListsSoon, newEntry, newMap, offerUpgrade, openChart, openEntry, openMap,
  renderHandoutsPanel, updateScenePanel, viewOpen, worldTest,
} from "./world";

type Mode = "visual" | "hybrid" | "source";

interface Problem {
  key: string;
  text: string;
  chapter: string | null;
  line: number | null;
}

interface ElementSpot {
  chapter: number;
  path: number[];
  kind: string;
  page: number;
  x: number;
  y: number;
}

const state = {
  info: null as any,
  chapter: null as Chapter | null,
  chapterIndex: 0,
  mode: "visual" as Mode,
  defs: [] as ElementDef[],
  history: [] as string[],
  historyPos: -1,
  pages: [] as string[],
  elements: [] as ElementSpot[],
  errors: [] as Problem[],
  warnings: [] as Problem[],
  exportWarnings: [] as any[], // F7.5 (M5): preflight warnings of the last export
  currentPage: 1,
  line: null as number | null,
  building: false,
  ready: false,
  tabs: [] as any[],
  findHits: [] as any[],
  findIndex: -1,
  hybrid: null as { block: Block; place: Place } | null,
  suggestFor: null as string | null,
  // M3: history positions at which a codex or map change was made, so Undo
  // undoes it in the core (F4.12).
  worldMarks: [] as number[],
  handoutsOnly: false,
  adventureId: null as string | null,
  navTab: "outline" as "outline" | "codex" | "handouts",
};

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;

let visual: VisualEditor;
let source: SourceEditor;
let spelling: Spelling;
let sendQueue: Promise<unknown> = Promise.resolve();
let pendingTimer: number | null = null;
let pendingSend: (() => Promise<void>) | null = null;

// --- sending edits to the core -----------------------------------------------

function schedule(send: () => Promise<void>, delay: number): void {
  pendingSend = send;
  if (pendingTimer !== null) clearTimeout(pendingTimer);
  pendingTimer = window.setTimeout(() => {
    pendingTimer = null;
    const job = pendingSend;
    pendingSend = null;
    if (job) sendQueue = sendQueue.then(job).catch(console.error);
  }, delay);
}

/** Send any waiting edit now and wait until the core has it. */
async function flush(): Promise<void> {
  if (pendingTimer !== null) {
    clearTimeout(pendingTimer);
    pendingTimer = null;
    const job = pendingSend;
    pendingSend = null;
    if (job) sendQueue = sendQueue.then(job).catch(console.error);
  }
  await sendQueue;
}

/** A structural change is one undo step of its own (F4.2, F4.13). */
function commit(doc: Doc): void {
  if (pendingTimer !== null) {
    clearTimeout(pendingTimer);
    pendingTimer = null;
    pendingSend = null;
  }
  sendQueue = sendQueue.then(() => sendDoc(doc)).catch(console.error);
}

function pushHistory(text: string): void {
  if (state.history[state.historyPos] === text) return;
  state.history = state.history.slice(0, state.historyPos + 1);
  state.history.push(text);
  if (state.history.length > 300) state.history.shift();
  state.historyPos = state.history.length - 1;
}

async function sendDoc(doc: Doc): Promise<void> {
  if (state.info?.readOnly) return;
  const chapter: Chapter = await call("setChapterDoc", state.chapterIndex, JSON.stringify(doc));
  if (!state.chapter) return;
  state.chapter.text = chapter.text;
  state.chapter.outline = chapter.outline;
  state.chapter.words = chapter.words;
  pushHistory(chapter.text);
  renderOutline();
  updateStatus();
  renderTabs();
  refreshListsSoon();
}

async function sendText(text: string): Promise<void> {
  if (state.info?.readOnly) return;
  const chapter: Chapter = await call("setChapterText", state.chapterIndex, text);
  state.chapter = chapter;
  pushHistory(chapter.text);
  renderOutline();
  updateStatus();
  renderTabs();
  refreshListsSoon();
}

async function applyText(text: string): Promise<void> {
  const chapter: Chapter = await call("setChapterText", state.chapterIndex, text);
  state.chapter = chapter;
  if (state.mode !== "source") visual.load(chapter.doc);
  else source.set(chapter.text);
  renderOutline();
  updateStatus();
  renderTabs();
}

async function undo(): Promise<void> {
  await flush();
  const mark = state.worldMarks[state.worldMarks.length - 1];
  if (mark !== undefined && mark >= state.historyPos) {
    // The last change was in the codex, a map or the chart.
    state.worldMarks.pop();
    const reply = await call("worldUndo");
    if (reply?.ok) {
      await reloadAfterWorld();
      flashStatus(t("status.undone"));
    }
    return;
  }
  if (state.historyPos <= 0) return;
  state.historyPos -= 1;
  await applyText(state.history[state.historyPos]);
}

async function redo(): Promise<void> {
  await flush();
  if (state.historyPos >= state.history.length - 1) return;
  state.historyPos += 1;
  await applyText(state.history[state.historyPos]);
}

// --- modes (F4.1) ----------------------------------------------------------------

async function setMode(mode: Mode): Promise<void> {
  await flush();
  state.mode = mode;
  for (const m of ["visual", "hybrid", "source"]) $("mode-" + m).setAttribute("aria-pressed", String(mode === m));
  $("visual").classList.toggle("hidden", mode === "source");
  $("source").classList.toggle("hidden", mode !== "source");
  $("hybrid").classList.toggle("hidden", mode !== "hybrid");
  if (!state.chapter) return;
  if (mode === "source") {
    source.set(state.chapter.text);
    markErrorLine();
  } else {
    const chapter: Chapter = await call("chapter", state.chapterIndex);
    state.chapter = chapter;
    visual.load(chapter.doc);
    showHybrid(null);
  }
}

/** F4.1 Hybrid: the source of the block under the cursor, editable. */
async function showHybrid(focus: { block: Block; place: Place } | null): Promise<void> {
  state.hybrid = focus;
  const area = $<HTMLTextAreaElement>("hybrid-source");
  if (state.mode !== "hybrid") return;
  if (!focus) {
    area.value = "";
    area.disabled = true;
    $("hybrid-label").textContent = t("hybrid.nothing");
    return;
  }
  await flush();
  const reply = await call("blockSource", JSON.stringify(focus.block));
  area.value = reply.text;
  area.disabled = !!state.info?.readOnly;
  const def = visual.definition(focus.block.kind ?? "");
  $("hybrid-label").textContent = t("hybrid.label", { kind: def?.name ?? t(`kind.${focus.block.type}`) });
}

async function applyHybrid(): Promise<void> {
  const focus = state.hybrid;
  const area = $<HTMLTextAreaElement>("hybrid-source");
  if (!focus || area.disabled) return;
  const reply = await call("blockSource", JSON.stringify(focus.block));
  if (reply.text === area.value) return;
  focus.block.raw = area.value;
  for (const outer of focus.place.chain) delete outer.raw;
  await flush();
  await sendDoc(visual.current());
  const chapter: Chapter = await call("chapter", state.chapterIndex);
  state.chapter = chapter;
  visual.load(chapter.doc);
  state.hybrid = null;
}

// --- loading ---------------------------------------------------------------------

/** After a change in the core: the codex, the chapter and the editor. */
async function reloadAfterWorld(): Promise<void> {
  await loadCodex();
  if (!state.chapter) return;
  const chapter: Chapter = await call("chapter", state.chapterIndex);
  const changed = chapter.text !== state.chapter.text;
  state.chapter = chapter;
  if (changed) {
    pushHistory(chapter.text);
    if (state.mode === "source") source.set(chapter.text);
    else visual.load(chapter.doc);
  } else if (state.mode !== "source") {
    visual.render();
  }
  state.info = await call("info");
  renderOutline();
  updateStatus();
  renderTabs();
  updateScenePanel(state.line);
}

// F4 (M6 part C3): coming back to the same place in the text. The place is
// the editor's scroll position and the block and caret that had the cursor,
// remembered for each open adventure tab.
interface Spot { scroll: number; line: string | null; caret: number | null }
const spots = new Map<string, Spot>();

function caretOffset(box: HTMLElement): number | null {
  const sel = getSelection();
  if (!sel || !sel.rangeCount || !box.contains(sel.anchorNode)) return null;
  const range = document.createRange();
  range.selectNodeContents(box);
  range.setEnd(sel.anchorNode!, sel.anchorOffset);
  return range.toString().length;
}

function placeCaret(box: HTMLElement, offset: number): void {
  const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
  let left = offset;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const length = node.textContent?.length ?? 0;
    if (left <= length) {
      const range = document.createRange();
      range.setStart(node, left);
      range.collapse(true);
      getSelection()?.removeAllRanges();
      getSelection()?.addRange(range);
      return;
    }
    left -= length;
  }
}

function saveSpot(id: string | null = state.adventureId): void {
  const pane = $("editor-pane");
  if (!id || pane.classList.contains("world-open") || state.mode === "source") return;
  const active = document.activeElement instanceof HTMLElement && $("visual").contains(document.activeElement) ? document.activeElement : null;
  const section = active?.closest<HTMLElement>("section.blk") ?? null;
  spots.set(id, { scroll: pane.scrollTop, line: section?.dataset.line ?? null, caret: active ? caretOffset(active) : null });
}

function restoreSpot(id: string | null = state.adventureId): void {
  const spot = id ? spots.get(id) : undefined;
  if (!spot || state.mode === "source") return;
  const pane = $("editor-pane");
  const apply = () => {
    if (spot.line) {
      const sections = [...document.querySelectorAll<HTMLElement>(`#visual section.blk[data-line="${spot.line}"]`)];
      const section = sections[sections.length - 1];
      const box = section?.querySelector<HTMLElement>(":scope > .rich, :scope > .heading-edit, :scope > .el .rich, :scope > .el input");
      if (box) {
        box.focus({ preventScroll: true });
        if (spot.caret !== null && box.isContentEditable) placeCaret(box, spot.caret);
      }
    }
    pane.scrollTop = spot.scroll;
  };
  apply();
  const first = pane.scrollTop;
  // Once more after the editor has laid itself out again, unless the author
  // has scrolled or moved on in the meantime.
  const focused = document.activeElement;
  requestAnimationFrame(() => {
    if (pane.scrollTop === first && document.activeElement === focused) apply();
  });
}

async function refresh(): Promise<void> {
  saveSpot();
  state.info = await call("info");
  const has = state.info.hasDocument;
  $("welcome").classList.toggle("hidden", has);
  $("workspace").classList.toggle("hidden", !has);
  $("toolbar").classList.toggle("hidden", !has);
  $("statusbar").classList.toggle("hidden", !has);
  await renderTabs();
  buildMenus();
  renderBanner();
  if (!has) {
    renderWelcome();
    return;
  }
  state.defs = (await call("editorInfo")).elements;
  setInlineKinds(state.defs.filter((d) => d.inlineForm === "call").map((d) => d.id));
  visual.setDefinitions(state.defs);
  visual.readOnly = !!state.info.readOnly;
  source.readOnly = !!state.info.readOnly;
  renderToolbar(); // F9: insert groups list only what the game system turns on
  state.pages = [];
  state.elements = [];
  state.errors = [];
  state.warnings = [];
  renderPages();
  const opened = state.info.id !== state.adventureId;
  state.adventureId = state.info.id;
  if (opened) await loadZoom(); // F7.2: the size this adventure was last looked at
  if (opened) {
    closeView();
    state.worldMarks = [];
  }
  await loadCodex();
  await loadChapter(0, true);
  if (!viewOpen()) restoreSpot(state.info.id);
  // F18: the editor mode the app starts in, for the first adventure opened.
  if (!startModeApplied) {
    startModeApplied = true;
    const start = appValues()?.start_mode;
    if (start && start !== state.mode) await setMode(start);
  }
  updateScenePanel(null);
  // F3.12: an adventure saved before M3 is offered its text-to-codex links.
  if (opened && !state.info.readOnly) await offerUpgrade(false);
}

let startModeApplied = false;

async function loadChapter(index: number, resetHistory: boolean): Promise<void> {
  state.chapterIndex = index;
  const chapter: Chapter = await call("chapter", index);
  state.chapter = chapter;
  if (resetHistory) {
    state.history = [chapter.text];
    state.historyPos = 0;
  }
  visual.load(chapter.doc);
  source.set(chapter.text);
  renderOutline();
  updateStatus();
  await call("requestBuild");
}

// F14.3 (M6 part A): a module version on trial shows a bar over the preview;
// nothing in the adventure changes until Apply.
function renderVersionBar(): void {
  const pv = state.info?.versionPreview;
  $("version-bar").classList.toggle("hidden", !pv);
  if (pv) $("version-bar-text").textContent = t("version.previewing", { name: pv.name, version: pv.version });
}

async function pickVersion(which: "gameSystem" | "theme", version: string): Promise<void> {
  const info = await call("settings");
  const current = info.versions?.[which]?.current;
  if (version !== current && version.split(".")[0] !== String(current).split(".")[0]) {
    // 9.2: another main version may lack things the adventure uses.
    const name = which === "theme" ? info.theme : info.gameSystem;
    const answer = await askChoice(t("version.majorWarning", { name, version, from: current }), t("version.try"), "", t("dialog.cancel"));
    if (answer !== "yes") {
      fillSettings(info, false);
      return;
    }
  }
  const reply = version === current ? await call("cancelVersion") : await call("previewVersion", which, version);
  if (reply?.ok === false) {
    $("settings-foot-note").textContent = reply.error ?? "";
    fillSettings(info, false);
    return;
  }
  $("settings-foot-note").textContent = "";
  if (version !== current) await closeSettings(); // so the preview and its bar are in view
  await refresh();
}

async function endVersionPreview(apply: boolean): Promise<void> {
  await call(apply ? "applyVersion" : "cancelVersion");
  await refresh();
}

function renderBanner(): void {
  renderVersionBar();
  const banner = $("banner");
  const ro = state.info?.readOnly;
  if (!ro) {
    banner.classList.add("hidden");
    return;
  }
  if (ro === "protected") {
    // F2.9, F14 (M6): every missing or disabled module, by name, ID and version.
    const names = state.info.missingText || (state.info.missingModules ?? []).map((m: any) => m.id + " " + m.version).join(", ");
    banner.textContent = t("banner.protected", { modules: names });
  } else {
    banner.textContent = t("banner.openElsewhere");
  }
  banner.classList.remove("hidden");
}

// --- tabs (F2.2) ---------------------------------------------------------------------

async function renderTabs(): Promise<void> {
  state.tabs = await call("tabs");
  const bar = $("tabbar");
  bar.textContent = "";
  const open = state.tabs.filter((tab) => tab.title !== null);
  bar.classList.toggle("hidden", open.length === 0);
  for (const tab of open) {
    const item = document.createElement("div");
    item.className = "tab-item" + (tab.active ? " active" : "");
    item.setAttribute("role", "tab");
    item.setAttribute("aria-selected", String(tab.active));
    const label = document.createElement("button");
    label.type = "button";
    label.className = "tab-label";
    label.textContent = tab.title + (tab.dirty ? " •" : "");
    label.title = tab.readOnly ? t("tabs.readOnly") : tab.title;
    label.addEventListener("click", () => switchTab(tab.id));
    const close = document.createElement("button");
    close.type = "button";
    close.className = "tab-close";
    close.textContent = "×";
    close.title = t("tabs.close");
    close.setAttribute("aria-label", t("tabs.close"));
    close.addEventListener("click", () => closeTab(tab.id));
    item.append(label, close);
    bar.append(item);
  }
  const add = document.createElement("button");
  add.type = "button";
  add.className = "tab-new";
  add.textContent = "+";
  add.title = t("menu.new");
  add.setAttribute("aria-label", t("menu.new"));
  add.addEventListener("click", () => openNewDialog());
  bar.append(add);
}

async function switchTab(id: string): Promise<void> {
  await flush();
  const result = await call("switchTab", id);
  if (result?.ok) await refresh();
}

async function closeTab(id: string): Promise<void> {
  await flush();
  const result = await call("closeTab", id);
  if (result?.ok) await refresh();
}

// --- welcome, menus, dialogs ----------------------------------------------------------

function renderWelcome(): void {
  const list = $("w-recent");
  list.textContent = "";
  for (const path of state.info.recent as string[]) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.className = "link";
    button.textContent = path.split(/[\\/]/).pop() || path;
    button.title = path;
    button.addEventListener("click", () => openPath(path));
    item.append(button);
    list.append(item);
  }
  $("w-recent-title").classList.toggle("hidden", state.info.recent.length === 0);
}

interface MenuItem {
  label: string;
  action?: () => void;
  shortcut?: string;
  disabled?: boolean;
  children?: MenuItem[];
  heading?: boolean;
  foot?: boolean; // F9: "New codex entry…" at the foot of a toolbar group
}

function menuModel(): { key: string; items: MenuItem[] }[] {
  const has = !!state.info?.hasDocument;
  const ro = !!state.info?.readOnly;
  // With no adventure open, or a read-only one, there is nothing to insert into.
  const later = { label: t(has ? "menu.insertReadOnly" : "menu.insertNeedsAdventure"), disabled: true };
  const recent: MenuItem[] = (state.info?.recent ?? []).map((p: string) => ({
    label: p.split(/[\\/]/).pop() || p,
    action: () => openPath(p),
  }));
  return [
    { key: "menu.file", items: [
      { label: t("menu.new"), action: () => openNewDialog(), shortcut: "Ctrl+N" },
      { label: t("menu.open"), action: () => openDialog(), shortcut: "Ctrl+O" },
      { label: t("menu.openFolder"), action: () => openFolder() },
      { label: t("menu.openRecent"), children: recent.length ? recent : [{ label: t("menu.noRecent"), disabled: true }] },
      { label: t("menu.save"), action: () => save("save"), shortcut: "Ctrl+S", disabled: !has },
      { label: t("menu.saveAs"), action: () => save("saveAs"), disabled: !has },
      { label: t("menu.saveAsFolder"), action: () => save("saveAsFolderDialog"), disabled: !has },
      { label: t("menu.revert"), action: () => openRevert(), disabled: !has || ro },
      { label: t("menu.export"), disabled: !has, children: [
        { label: t("menu.exportBook"), action: () => exportPdf(), disabled: !has },
        { label: t("menu.exportHandouts"), action: () => exportHandouts(), disabled: !has },
        // F7.6 (M5): two pages per sheet, and the print-shop version.
        { label: t("menu.exportBooklet"), action: () => exportVariant("booklet"), disabled: !has },
        { label: t("menu.exportPrintShop"), action: () => exportVariant("print-shop"), disabled: !has },
        // F17.5 (M5): the accessible PDF.
        { label: t("menu.exportAccessible"), action: () => exportVariant("accessible"), disabled: !has },
      ] },
      { label: t("menu.settings"), action: () => openSettingsWindow(), shortcut: "Ctrl+," },
      { label: t("menu.closeTab"), action: () => closeTab(state.info.id), shortcut: "Ctrl+W", disabled: !has },
      { label: t("menu.quit"), action: () => call("quit"), shortcut: "Ctrl+Q" },
    ] },
    { key: "menu.edit", items: [
      { label: t("menu.undo"), action: () => undo(), shortcut: "Ctrl+Z", disabled: !has || ro },
      { label: t("menu.redo"), action: () => redo(), shortcut: "Ctrl+Shift+Z", disabled: !has || ro },
      { label: t("menu.find"), action: () => openFind(), shortcut: "Ctrl+F", disabled: !has },
      { label: t("menu.upgrade"), action: () => offerUpgrade(true), disabled: !has || ro },
    ] },
    { key: "menu.view", items: [
      { label: t("menu.visual"), action: () => setMode("visual"), disabled: !has },
      { label: t("menu.hybrid"), action: () => setMode("hybrid"), disabled: !has },
      { label: t("menu.source"), action: () => setMode("source"), disabled: !has },
      { label: t(previewShown ? "menu.hidePreview" : "menu.showPreview"), action: () => setPreview(!previewShown), disabled: !has },
      // F7.2 (M5): a two-page spread, and the preview in a window of its own.
      { label: t("menu.spread"), action: () => setSpread(!isSpread()), disabled: !has },
      { label: t("menu.previewWindow"), action: () => call("openPreviewWindow"), disabled: !has },
      { label: t(state.handoutsOnly ? "menu.showBook" : "menu.handoutsOnly"), action: () => setHandoutsOnly(!state.handoutsOnly), disabled: !has },
      // F7.2 (M5): marks page and column breaks in the preview only.
      { label: t(showBreaks ? "menu.hideBreaks" : "menu.showBreaks"), action: () => setShowBreaks(!showBreaks), disabled: !has },
      { label: t(fullScreen ? "menu.exitFullScreen" : "menu.enterFullScreen"), action: () => setFullScreen(!fullScreen), shortcut: "F11" },
      { label: t("menu.chart"), action: () => openChart(), disabled: !has },
      { label: t("menu.codexTab"), action: () => showNavTab("codex"), disabled: !has },
      { label: t("menu.handoutsTab"), action: () => showNavTab("handouts"), disabled: !has },
    ] },
    { key: "menu.insert", items: has && !ro ? insertItems() : [later] },
    { key: "menu.format", items: [
      { label: t("toolbar.bold"), action: () => document.execCommand("bold"), shortcut: "Ctrl+B", disabled: !has || ro },
      { label: t("toolbar.italic"), action: () => document.execCommand("italic"), shortcut: "Ctrl+I", disabled: !has || ro },
      { label: t("menu.style"), disabled: !has || ro, children:
        styleKinds().map((kind) => ({ label: kindLabel(kind), action: () => setStyle(kind) })) },
    ] },
    { key: "menu.help", items: [
      { label: t("menu.example"), action: () => openExample() },
      // F9 (M5): the start-up checks on demand, with the theme self-test.
      { label: t("menu.checkInstallation"), action: () => openCheckDialog() },
      // F21 (M6 part C): the only network request the app makes.
      { label: t("menu.checkUpdates"), action: () => checkForUpdates() },
      // F19 (M5): the author guides, opened inside the app.
      { label: t("menu.guideTheme"), action: () => openGuide("guide-theme") },
      { label: t("menu.guideGameSystem"), action: () => openGuide("guide-game-system") },
      { label: t("menu.about"), action: () => openAbout() },
    ] },
  ];
}

function kindLabel(kind: string): string {
  if (kind === "paragraph") return t("editor.paragraph");
  if (kind === "heading") return t("editor.actHeading");
  // F4 (M6 part C): heading levels 3, 4 and 5 are Sub-heading 1, 2 and 3.
  if (kind === "scene-end") return t("editor.endScene");
  if (kind === "heading-3") return t("editor.subHeading1");
  if (kind === "heading-4") return t("editor.subHeading2");
  if (kind === "heading-5") return t("editor.subHeading3");
  if (kind === "table") return t("editor.table");
  if (kind === "image") return t("editor.image");
  return state.defs.find((d) => d.id === kind)?.name ?? kind;
}

function insertItems(kinds?: string[], onPick?: (kind: string) => void): MenuItem[] {
  const pick = onPick ?? ((kind: string) => insert(kind));
  const allowed = kinds ?? ["paragraph", "heading", ...SUB_HEADINGS, "scene-end", ...state.defs.filter((d) => !d.onlyInside).map((d) => d.id), "table", "image"];
  const items: MenuItem[] = [];
  for (const kind of ["paragraph", "heading", ...SUB_HEADINGS, "scene-end"]) {
    if (allowed.includes(kind)) items.push({ label: kindLabel(kind), action: () => pick(kind) });
  }
  const seenGroups = new Set<string>();
  for (const def of state.defs.filter((d) => d.category !== "layout" && allowed.includes(d.id))) {
    let shortcut = def.shortcut ?? undefined;
    if (def.shortcutGroup) {
      if (seenGroups.has(def.shortcutGroup)) shortcut = undefined;
      seenGroups.add(def.shortcutGroup);
    }
    items.push({ label: def.name, action: () => pick(def.id), shortcut });
  }
  for (const kind of ["table", "image"]) {
    if (allowed.includes(kind)) items.push({ label: kindLabel(kind), action: () => pick(kind) });
  }
  const layout = state.defs.filter((d) => d.category === "layout" && allowed.includes(d.id));
  if (layout.length) {
    items.push({ label: t("menu.layout"), heading: true });
    for (const def of layout) items.push({ label: def.name, action: () => pick(def.id), shortcut: def.shortcut ?? undefined });
  }
  return items;
}

// The live preview can be hidden to give the editor the whole width.
let previewShown = true;

function setPreview(show: boolean): void {
  previewShown = show;
  try {
    localStorage.setItem("scriptorum.preview", show ? "1" : "0");
  } catch {
    // Storage may be unavailable; the choice then lasts for this run only.
  }
  $("workspace").classList.toggle("no-preview", !show);
  $("preview-pane").classList.toggle("hidden", !show);
  // F9: Handouts only is shown only while the preview is shown.
  $("tb-handouts").classList.toggle("hidden", !show);
  const button = $("tb-preview");
  button.setAttribute("aria-pressed", String(show));
  const label = t(show ? "toolbar.hidePreview" : "toolbar.showPreview");
  button.title = label;
  button.setAttribute("aria-label", label);
  buildMenus();
}

// The items are worked out when a menu opens, so they always match the
// adventure and the elements its game system turns on.
function freshItems(key: string): MenuItem[] {
  return menuModel().find((m) => m.key === key)?.items ?? [];
}

function buildMenus(): void {
  const bar = $("menubar");
  bar.textContent = "";
  for (const menu of menuModel()) {
    const button = document.createElement("button");
    button.className = "menu-btn";
    button.textContent = t(menu.key);
    button.setAttribute("aria-haspopup", "true");
    button.addEventListener("click", () => {
      if (popupOpenFor(button)) hidePopup();
      else showPopup(button, freshItems(menu.key));
    });
    // Moving along the menu bar while a menu is open opens the next one.
    button.addEventListener("mouseenter", () => {
      const open = !$("menu-popup").classList.contains("hidden") && popupAnchor?.classList.contains("menu-btn");
      if (open && popupAnchor !== button) showPopup(button, freshItems(menu.key));
    });
    bar.append(button);
  }
  bar.append(modeSwitch()); // F9, F16: the small Light / Dark switch
}

function showPopup(anchor: HTMLElement | { left: number; top: number }, items: MenuItem[]): void {
  const popup = $("menu-popup");
  popup.textContent = "";
  for (const item of items) {
    if (item.heading) {
      const h = document.createElement("div");
      h.className = "menu-heading";
      h.textContent = item.label;
      popup.append(h);
      continue;
    }
    const row = document.createElement("button");
    row.className = "menu-item" + (item.foot ? " menu-foot" : "");
    row.setAttribute("role", "menuitem");
    row.disabled = !!item.disabled;
    const label = document.createElement("span");
    label.textContent = item.label;
    row.append(label);
    if (item.shortcut) {
      const sc = document.createElement("span");
      sc.className = "shortcut";
      sc.textContent = item.shortcut;
      row.append(sc);
    }
    if (item.children) {
      row.classList.add("has-children");
      row.addEventListener("click", (e) => {
        e.stopPropagation();
        showPopup(anchor, item.children!);
      });
    } else if (item.action) {
      row.addEventListener("mousedown", (e) => e.preventDefault());
      row.addEventListener("click", () => {
        hidePopup();
        item.action!();
      });
    }
    popup.append(row);
  }
  let left: number;
  let top: number;
  if (anchor instanceof HTMLElement) {
    const rect = anchor.getBoundingClientRect();
    left = rect.left;
    top = rect.bottom + 2;
  } else {
    left = anchor.left;
    top = anchor.top;
  }
  popupAnchor = anchor instanceof HTMLElement ? anchor : null;
  popup.classList.remove("hidden");
  popup.style.left = Math.max(4, Math.min(left, window.innerWidth - popup.offsetWidth - 8)) + "px";
  popup.style.top = Math.max(4, Math.min(top, window.innerHeight - popup.offsetHeight - 8)) + "px";
}

// The element that opened the popup, so clicking it again closes it.
let popupAnchor: HTMLElement | null = null;

/** One lasting listener closes the popup on a press outside it. (M2-0.2.1
 * added a one-time click listener per popup; a left-over listener then
 * closed every later menu the moment it opened.) */
function hideOnOutside(event: MouseEvent): void {
  const popup = $("menu-popup");
  if (popup.classList.contains("hidden")) return;
  const target = event.target as Node;
  if (popup.contains(target)) return;
  if (popupAnchor && popupAnchor.contains(target)) return;
  hidePopup();
}

function hidePopup(): void {
  $("menu-popup").classList.add("hidden");
  popupAnchor = null;
}

function popupOpenFor(anchor: HTMLElement): boolean {
  return !$("menu-popup").classList.contains("hidden") && popupAnchor === anchor;
}

async function openNewDialog(): Promise<void> {
  const dialog = $<HTMLDialogElement>("new-dialog");
  const systems: any[] = await call("gameSystems");
  const gs = $<HTMLSelectElement>("new-system");
  const th = $<HTMLSelectElement>("new-theme");
  gs.textContent = "";
  systems.forEach((s, i) => {
    const option = document.createElement("option");
    option.value = String(i);
    option.textContent = s.name;
    gs.append(option);
  });
  const fillThemes = () => {
    th.textContent = "";
    for (const theme of systems[Number(gs.value)]?.themes ?? []) {
      const option = document.createElement("option");
      option.value = JSON.stringify(theme);
      option.textContent = theme.name;
      th.append(option);
    }
  };
  gs.onchange = fillThemes;
  fillThemes();
  $<HTMLInputElement>("new-title").value = "";
  $("new-error").textContent = "";
  dialog.showModal();
  $<HTMLInputElement>("new-title").focus();
  $("new-create").onclick = async (event) => {
    event.preventDefault();
    const title = $<HTMLInputElement>("new-title").value.trim();
    if (!title) {
      $("new-error").textContent = t("dialog.titleRequired");
      return;
    }
    const system = systems[Number(gs.value)];
    const theme = JSON.parse(th.value);
    await flush();
    const result = await call("newAdventure", JSON.stringify({
      title, gameSystem: { id: system.id, version: system.version }, theme: { id: theme.id, version: theme.version },
    }));
    if (!result.ok) {
      $("new-error").textContent = result.error ?? "";
      return;
    }
    dialog.close();
    await refresh();
  };
  $("new-cancel").onclick = (event) => {
    event.preventDefault();
    dialog.close();
  };
}

async function openDialog(): Promise<void> {
  await flush();
  const result = await call("openDialog");
  if (result?.ok) await refresh();
}

async function openFolder(): Promise<void> {
  await flush();
  const result = await call("openFolderDialog");
  if (result?.ok) await refresh();
}

async function openPath(path: string): Promise<void> {
  await flush();
  const result = await call("openPath", path);
  if (result?.ok) await refresh();
}

async function save(slot: "save" | "saveAs" | "saveAsFolderDialog"): Promise<void> {
  await flush();
  const result = await call(slot);
  if (result?.ok) {
    const wasReadOnly = state.info?.readOnly;
    state.info = await call("info");
    flashStatus(t("status.saved"));
    rememberZoom(); // F7.2: a first save gives the zoom a place to be remembered
    buildMenus();
    renderTabs();
    if (wasReadOnly && !state.info.readOnly) await refresh();
  }
}

async function exportPdf(): Promise<void> {
  await flush();
  const result = await call("exportDialog");
  if (result?.ok) state.info = await call("info");
  afterExport(result);
}

/** F7.6 (M5): the booklet and the print-shop version. */
async function exportVariant(variant: string): Promise<void> {
  await flush();
  const result = await call("exportVariantDialog", variant);
  afterExport(result);
}

/** F7.5 (M5): an export's preflight warnings join the status bar and the panel. */
function afterExport(result: any): void {
  if (result?.ok) {
    state.exportWarnings = result.warnings ?? [];
    flashStatus(t("status.exported", { file: result.file }));
    updateStatus();
    if (state.exportWarnings.length) openWarnings();
  } else if (result?.errors) {
    state.errors = result.errors;
    showErrors();
  }
}

function allWarnings(): any[] {
  const seen = new Set<string>();
  return [...state.errors.map((e: any) => ({ ...e, error: true })), ...state.warnings, ...state.exportWarnings].filter((w) => {
    if (seen.has(w.text)) return false;
    seen.add(w.text);
    return true;
  });
}

/** F7.5.5: warnings are shown in the status bar and listed in a panel. */
function openWarnings(): void {
  const list = $("warnings-list");
  list.textContent = "";
  const items = allWarnings();
  if (!items.length) {
    const li = document.createElement("li");
    li.textContent = t("status.warningsNone");
    list.append(li);
  }
  for (const w of items) {
    const li = document.createElement("li");
    li.textContent = w.text;
    li.classList.toggle("error", !!w.error);
    if (w.line && w.chapter) {
      li.classList.add("goes");
      li.addEventListener("click", async () => {
        const index = (state.info?.chapters ?? []).findIndex((c: any) => c.path === w.chapter);
        if (index >= 0 && index !== state.chapterIndex) await loadChapter(index, true);
        if (state.mode === "source") source.goToLine(w.line);
        else visual.scrollToLine(w.line);
      });
    }
    if (w.key === "warning.heading.skipsLevel" && w.details?.to && !state.info?.readOnly) {
      // F4 (M6 part C): an older adventure's heading that skips a level opens
      // unchanged; the warnings panel offers to raise it, as one undo step.
      const raise = document.createElement("button");
      raise.type = "button";
      raise.className = "small-btn warning-fix";
      raise.textContent = t("editor.raiseTo", { level: Number(w.details.sub) });
      raise.addEventListener("click", async (e) => {
        e.stopPropagation();
        const index = (state.info?.chapters ?? []).findIndex((c: any) => c.path === w.chapter);
        if (index >= 0 && index !== state.chapterIndex) await loadChapter(index, true);
        if (state.mode === "source") await setMode("visual");
        const block = visual.blockOnLine(w.line);
        if (block && visual.setLevel(block, Number(w.details.to))) {
          raise.disabled = true;
          flashStatus(t("editor.raised", { title: w.details.title, level: Number(w.details.sub) }));
        }
      });
      li.append(" ", raise);
    }
    list.append(li);
  }
  $("warnings-panel").classList.remove("hidden");
}

/** F7.6.2: the player PDF with only the handouts. */
async function exportHandouts(): Promise<void> {
  await flush();
  const result = await call("exportHandoutsDialog");
  afterExport(result);
}

let showBreaks = false;

/** F7.2 (M5): View ▸ Show breaks marks page and column breaks in the preview. */
async function setShowBreaks(on: boolean): Promise<void> {
  showBreaks = on;
  await call("setShowBreaks", on);
}

/** F6.4: the preview shows exactly what the players will receive. */
async function setHandoutsOnly(on: boolean): Promise<void> {
  state.handoutsOnly = on;
  const b = $("tb-handouts");
  b.setAttribute("aria-pressed", String(on));
  b.classList.toggle("pressed", on);
  $("preview-pane").classList.toggle("players", on);
  await call("setHandoutsOnly", on);
  buildMenus();
  renderHandoutsPanel();
}

/** The navigator's tabs: Outline, Codex and Handouts (F9.3). */
function showNavTab(tab: "outline" | "codex" | "handouts"): void {
  state.navTab = tab;
  for (const name of ["outline", "codex", "handouts"]) {
    const button = $("nav-" + name);
    button.classList.toggle("active", name === tab);
    button.setAttribute("aria-selected", String(name === tab));
  }
  $("outline").classList.toggle("hidden", tab !== "outline");
  $("codex-panel").classList.toggle("hidden", tab !== "codex");
  $("handouts-panel").classList.toggle("hidden", tab !== "handouts");
}

// The last cursor position in the text, so the codex can insert there even
// while an entry or a map is shown in place of the editor (F3.4).
let lastRange: Range | null = null;

function restoreRange(): boolean {
  if (!lastRange || !document.contains(lastRange.startContainer)) return false;
  const selection = getSelection();
  selection?.removeAllRanges();
  selection?.addRange(lastRange);
  const box = (lastRange.startContainer instanceof HTMLElement ? lastRange.startContainer : lastRange.startContainer.parentElement)?.closest<HTMLElement>(".rich");
  box?.focus();
  selection?.removeAllRanges();
  selection?.addRange(lastRange);
  return true;
}

async function addFont(): Promise<void> {
  const result = await call("addFontDialog");
  if (result?.ok) {
    flashStatus(t("status.fontAdded", { family: result.family || result.file, licence: result.licence }));
    state.defs = (await call("editorInfo")).elements;
    visual.setDefinitions(state.defs);
    visual.render();
    renderTabs();
  } else if (result?.error) {
    showMessage(result.error);
  }
}

function showMessage(text: string): void {
  const dialog = $<HTMLDialogElement>("message-dialog");
  $("message-text").textContent = text;
  dialog.showModal();
}

// --- inserting -------------------------------------------------------------------

async function insert(kind: string, place?: Place | null, variant?: string): Promise<void> {
  hidePopup();
  if (state.info?.readOnly) return;
  if (state.mode === "source") await setMode("visual");
  if (kind === "scene-end") {
    visual.endScene(place ?? undefined);
    return;
  }
  if (kind === "image") {
    const result = await call("addImageDialog");
    if (result?.ok) visual.insertBlock({ type: "image", path: result.path }, place ?? undefined);
    return;
  }
  const def = state.defs.find((d) => d.id === kind);
  if (def?.codexRef === "mention" || def?.codexRef === "see") {
    // F3.4: choose the entry, then it goes into the sentence as a chip.
    const anchor = document.activeElement instanceof HTMLElement ? document.activeElement : $("tb-groups");
    const range = getSelection()?.rangeCount ? getSelection()!.getRangeAt(0).cloneRange() : null;
    const items: MenuItem[] = codex.entries.map((e) => ({ label: e.title, action: () => {
      if (range) {
        getSelection()?.removeAllRanges();
        getSelection()?.addRange(range);
      }
      if (!visual.insertInline(`#${kind}(entry: "${e.id}")`)) flashStatus(t("codex.placeCursor"));
    } }));
    items.unshift({ label: t("codex.pickEntry"), heading: true });
    items.push({ label: t("editor.newEntry"), action: async () => {
      const id = await newEntry();
      if (!id) return;
      if (range) {
        getSelection()?.removeAllRanges();
        getSelection()?.addRange(range);
      }
      visual.insertInline(`#${kind}(entry: "${id}")`);
    } });
    showPopup(anchor, items);
    return;
  }
  if (kind === "footnote") {
    // F7.7 (M5): ask for the footnote's text; it goes into the sentence as a chip.
    const range = getSelection()?.rangeCount ? getSelection()!.getRangeAt(0).cloneRange() : null;
    const answer = await ask(t("editor.footnoteTitle"), { label: t("editor.footnoteLabel") });
    if (!answer?.text.trim()) return;
    if (range) {
      getSelection()?.removeAllRanges();
      getSelection()?.addRange(range);
    }
    if (!visual.insertInline(`#footnote(text: ${JSON.stringify(answer.text.trim())})`)) flashStatus(t("codex.placeCursor"));
    return;
  }
    if (def?.inlineForm === "call" && place === undefined) {
    // 11.7: dice typed inside a sentence go in as an inline chip.
    const field = def.fields.find((f) => f.required);
    const markup = "#" + kind + "(" + (field ? field.name + ": \"" + (field.default ?? "") + "\"" : "") + ")";
    if (visual.insertInline(markup)) return;
  }
  visual.insert(kind, place === undefined ? visual.focused() : place, variant);
}

// F9: the paragraph style of the block at the cursor.
function styleOfFocus(): string | null {
  const place = visual?.focused();
  const block = place ? place.list.blocks[place.index] : null;
  if (!block) return null;
  if (block.type === "paragraph" || block.type === "heading") return kindOf(block);
  return kindLabel(kindOf(block));
}

/** The paragraph styles at the cursor: a paragraph, and an act heading at
 * the top level or Sub-heading 1, 2 and 3 directly inside a scene (F4). */
function styleKinds(): string[] {
  const place = visual?.focused();
  if (!place) return ["paragraph", "heading"];
  const allowed = visual.kindsFor(place.list, place.chain, null);
  return ["paragraph", "heading", ...SUB_HEADINGS].filter((k) => allowed.includes(k));
}

function setStyle(kind: string): void {
  const place = visual.focused();
  const block = place ? place.list.blocks[place.index] : null;
  if (!place || !block || (block.type !== "paragraph" && block.type !== "heading")) return;
  if (kindOf(block) !== kind && styleKinds().includes(kind)) visual.convert(place, kind);
  renderStyle();
}

// F20: the example adventure opens as a copy in the user's documents.
async function openExample(): Promise<void> {
  await flush();
  const reply = await call("openExample");
  if (reply?.ok) {
    await refresh();
    flashStatus(t("status.exampleCopied", { path: reply.path }));
  } else if (reply?.error) showMessage(reply.error);
}

/** Ctrl+D: dice or a check (11.7, 11.8). */
function chooseGroup(group: string): void {
  const defs = state.defs.filter((d) => d.shortcutGroup === group);
  const anchor = document.activeElement instanceof HTMLElement ? document.activeElement : $("tb-groups");
  showPopup(anchor, defs.map((d) => ({ label: d.name, action: () => insert(d.id) })));
}

// --- context menu: spelling, Convert to, Insert (F4.2, F4.8) ---------------------------

function openContextMenu(event: MouseEvent, place: Place): void {
  const items: MenuItem[] = [];
  const word = spelling.wordAt(event.clientX, event.clientY);
  if (word) {
    items.push({ label: t("spell.suggestions", { word: word.word }), heading: true });
    items.push({ label: t("spell.looking"), disabled: true });
    state.suggestFor = word.word;
    pendingWord = word;
    call("suggest", word.word);
  }
  if (!state.info?.readOnly) {
    // F3.7: a codex entry from selected text, or from a loose person card.
    const selection = getSelection();
    const selected = selection && !selection.isCollapsed ? selection.toString().trim() : "";
    if (selected) {
      items.push({ label: t("codex.fromSelection"), action: async () => {
        await flush();
        const id = await newEntry("", selected);
        if (!id) return;
        // The text becomes a mention of the new entry, in the block's own
        // markup (the editor may have been redrawn meanwhile).
        const block = place.list.blocks[place.index];
        const needle = escapeInline(selected);
        const mention = `#mention(entry: "${id}")`;
        const updated: Block = { ...block };
        delete updated.raw;
        if (typeof block.text === "string" && block.text.includes(needle)) updated.text = block.text.replace(needle, mention);
        else if (typeof block.body === "string" && block.body.includes(needle)) updated.body = block.body.replace(needle, mention);
        else return;
        visual.replaceBlock(place, updated);
        visual.render();
      } });
    }
    const block = place.list.blocks[place.index];
    if (block?.type === "element" && block.kind === "person" && state.defs.some((d) => d.id === "card")) {
      items.push({ label: t("codex.personToEntry"), action: () => personToEntry(place) });
    }
    // F4 (M6 part C): Raise and Lower a sub-heading, one level at a time;
    // Lower only where it would not skip a level.
    if (isSubHeading(block)) {
      if (visual.canRaise(place)) items.push({ label: t("editor.raise"), action: () => visual.changeLevel(place, -1), shortcut: "Shift+Tab" });
      if (visual.canLower(place)) items.push({ label: t("editor.lower"), action: () => visual.changeLevel(place, 1), shortcut: "Tab" });
    }
    const convert = visual.convertKinds(place);
    if (convert.length) {
      items.push({ label: t("editor.convertTo"), heading: true });
      for (const kind of convert) items.push({ label: kindLabel(kind), action: () => visual.convert(place, kind) });
    }
    items.push({ label: t("editor.insertAfter"), heading: true });
    items.push(...insertItems(visual.kindsFor(place.list, place.chain, null).filter((k) =>
      place.chain.length === 0 || k !== "heading"), (kind) => insert(kind, place)));
  }
  contextItems = items;
  contextAt = { left: event.clientX, top: event.clientY };
  showPopup(contextAt, items);
}

/** F3.7: a loose person card becomes a codex entry and a codex card. */
async function personToEntry(place: Place): Promise<void> {
  const block = place.list.blocks[place.index];
  const f = block.fields ?? {};
  const fields: Record<string, unknown> = { mood: f.mood, description: f.description };
  if (Array.isArray(f.links)) fields["linked-to"] = f.links;
  const reply = await call("createEntry", JSON.stringify({ type: "person", title: inlineName(String(f.name ?? "")), fields }));
  if (!reply?.ok) {
    if (reply?.error) showMessage(reply.error);
    return;
  }
  state.worldMarks.push(state.historyPos);
  await loadCodex();
  visual.replaceBlock(place, { type: "element", kind: "card", fields: { entry: reply.id }, body: isDoc(block.body) ? block.body : { blocks: [], trail: "\n" } });
  visual.render();
  flashStatus(t("codex.entryCreated", { title: reply.title }));
}

function inlineName(markup: string): string {
  return markup.replace(/\\(.)/g, "$1");
}

let contextItems: MenuItem[] = [];
let contextAt = { left: 0, top: 0 };
let pendingWord: { word: string; range: Range } | null = null;

function onSuggestions(reply: { word: string; suggestions: string[] }): void {
  if (reply.word !== state.suggestFor || $("menu-popup").classList.contains("hidden") || !pendingWord) return;
  const word = pendingWord;
  const at = contextItems.findIndex((i) => i.label === t("spell.looking"));
  if (at < 0) return;
  const replacements: MenuItem[] = reply.suggestions.length
    ? reply.suggestions.map((s) => ({ label: s, action: () => replaceWord(word.range, s) }))
    : [{ label: t("spell.none"), disabled: true }];
  contextItems.splice(at, 1, ...replacements);
  showPopup(contextAt, contextItems);
}

function replaceWord(range: Range, replacement: string): void {
  const node = range.startContainer.parentElement?.closest<HTMLElement>("[contenteditable=true]");
  if (!node) return;
  node.focus();
  const selection = getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
  document.execCommand("insertText", false, replacement);
}

// --- outline (F4.9) ------------------------------------------------------------------

/** A sub-heading inside a scene (path [scene, index]), as the outline lists it. */
function isOutlineSub(item: OutlineItem): boolean {
  // Inside a scene (path of two) or, from M6 part C3, outside any scene.
  return item.kind === "heading" && (item.level ?? 1) >= 3 && [1, 2].includes(item.path?.length ?? 0);
}

function renderOutline(): void {
  const list = $("outline");
  list.textContent = "";
  const chapters = state.info?.chapters ?? [];
  const items: OutlineItem[] = state.chapter?.outline ?? [];
  if (chapters.length > 1) {
    chapters.forEach((ch: any) => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.className = "outline-item chapter" + (ch.index === state.chapterIndex ? " current" : "");
      button.textContent = ch.title;
      button.addEventListener("click", async () => {
        await flush();
        await loadChapter(ch.index, true);
      });
      li.append(button);
      list.append(li);
    });
  }
  if (!items.some((i) => i.kind === "scene")) {
    const empty = document.createElement("li");
    empty.className = "outline-empty";
    empty.textContent = t("sidebar.emptyOutline");
    list.append(empty);
  }
  let scene = 0;
  let act = 0;
  let sub = 0;
  let actKey = "";
  let sceneKey = "";
  let foldedSub = 0; // the level of a folded sub-heading whose section is hidden
  items.forEach((item, position) => {
    const li = document.createElement("li");
    li.dataset.item = String(position);
    const button = document.createElement("button");
    const isAct = item.kind === "heading" && item.level === 1;
    const isSub = isOutlineSub(item);
    button.className = "outline-item " + item.kind + (isAct ? " act" : "") + (isSub ? " sub level-" + item.level : "");
    // Folding (screen only): the same keys as the editor's fold buttons.
    let foldKey = "";
    if (isAct) {
      foldKey = actKey = "h:" + ++act;
      sceneKey = "";
    } else if (item.kind === "scene") {
      foldKey = sceneKey = "s:" + (scene + 1);
      foldedSub = 0;
    } else if (isSub) {
      foldKey = "u:" + ++sub;
      if (item.path?.length === 1) sceneKey = ""; // outside any scene
    }
    let hidden = !isAct && !!actKey && visual.collapsed.has(actKey);
    if (isSub) {
      // F4 (M6 part C): sub-headings are indented under their scene and fold
      // with it; a folded sub-heading hides the deeper ones under it.
      if (foldedSub && (item.level ?? 3) <= foldedSub) foldedSub = 0;
      hidden = hidden || (!!sceneKey && visual.collapsed.has(sceneKey)) || !!foldedSub;
      if (!hidden && visual.collapsed.has(foldKey)) foldedSub = item.level ?? 3;
    }
    if (hidden) li.classList.add("collapse-hidden");
    if (isSub) li.dataset.level = String(item.level);
    if (foldKey) {
      const fold = document.createElement("span");
      fold.className = "fold";
      const folded = visual.collapsed.has(foldKey);
      fold.textContent = folded ? "▸" : "▾"; // glyphs
      fold.title = t(folded ? "editor.expand" : "editor.collapse");
      fold.setAttribute("role", "button");
      fold.setAttribute("aria-label", fold.title);
      fold.setAttribute("aria-expanded", String(!folded));
      const key = foldKey;
      fold.addEventListener("click", (e) => {
        e.stopPropagation();
        visual.toggleCollapse(key);
      });
      li.append(fold);
    }
    const parentAct = isAct ? "" : actKey;
    if (item.kind === "scene") {
      scene += 1;
      const number = document.createElement("span");
      number.className = "num";
      number.textContent = t("sidebar.sceneNumber", { number: scene });
      button.append(number);
    }
    const title = document.createElement("span");
    title.textContent = item.title || t("sidebar.untitled");
    button.append(title);
    button.addEventListener("click", () => {
      if (dragging()) return;
      if (parentAct && visual.collapsed.has(parentAct)) visual.toggleCollapse(parentAct);
      if (state.mode !== "source") visual.scrollToLine(item.line);
      else source.goToLine(item.line);
    });
    if ((item.index !== undefined || isSub) && !state.info?.readOnly) {
      // F4.9, F4.13 (M6 part C2): drag acts, scenes and sub-headings in the
      // outline, with Scriptorum's own dragging (drag.ts).
      li.classList.add("draggable");
      li.addEventListener("pointerdown", (e) => {
        if ((e.target as HTMLElement).closest(".fold") || state.mode === "source") return;
        const scroller = list.closest<HTMLElement>(".navigator") ?? list;
        startDrag(e, {
          source: li,
          area: list,
          scroller,
          target: (x, y) => outlineTarget(item, x, y),
          onReason: (reason) => { if (reason) flashStatus(reason); },
        });
      });
    }
    li.append(button);
    list.append(li);
  });
  const end = document.createElement("li");
  end.className = "outline-end";
  list.append(end);
}

/** Where an outline item dragged to a point would land (M6 part C2). Acts
 * and scenes go between the top-level items. A sub-heading goes just before
 * the item below the line if that is a sub-heading of the same scene, else
 * at the end of the scene of the item above it; the line is indented to the
 * level it will get there (never more than one deeper than the one above). */
function outlineTarget(dragged: OutlineItem, x: number, y: number): DropTarget | null {
  const list = $("outline");
  const items: OutlineItem[] = state.chapter?.outline ?? [];
  const lis = [...list.querySelectorAll<HTMLElement>("li[data-item]")].filter((li) => !li.classList.contains("collapse-hidden"));
  if (!lis.length) return null;
  let k = lis.findIndex((li) => {
    const r = li.getBoundingClientRect();
    return y < r.top + r.height / 2;
  });
  if (k < 0) k = lis.length;
  const aboveLi = k > 0 ? lis[k - 1] : null;
  const belowLi = k < lis.length ? lis[k] : null;
  const above = aboveLi ? items[Number(aboveLi.dataset.item)] : null;
  const below = belowLi ? items[Number(belowLi.dataset.item)] : null;
  const box = list.getBoundingClientRect();
  const lineY = belowLi ? belowLi.getBoundingClientRect().top : (aboveLi ? aboveLi.getBoundingClientRect().bottom : box.top);
  const doc = visual.current();
  const found = visual.blockAt(dragged.path ?? [dragged.index ?? 0]);
  if (!found) return null;
  const from = found.place;

  if (!isOutlineSub(dragged) || dragged.path?.length === 1) {
    // An act or a scene: before the next top-level item.
    let index = doc.blocks.length;
    for (let i = belowLi ? Number(belowLi.dataset.item) : items.length; i < items.length; i++) {
      if (items[i].index !== undefined) {
        index = items[i].index!;
        break;
      }
    }
    const atLi = lis.find((li) => items[Number(li.dataset.item)].index === index);
    return {
      ok: true,
      line: { left: box.left + 8, right: box.right - 8, y: atLi ? atLi.getBoundingClientRect().top : lineY },
      drop: () => visual.moveTo(from, { list: doc, index, chain: [] }),
    };
  }
  // A sub-heading: only inside a scene.
  const scenePos = above ? (above.kind === "scene" ? above.path : isOutlineSub(above) ? [above.path![0]] : null) : null;
  const sceneFound = scenePos ? visual.blockAt(scenePos) : null;
  if (!sceneFound || sceneFound.block.kind !== "scene" || !sceneFound.block.body || !("blocks" in (sceneFound.block.body as any))) {
    return { ok: false, reason: t("editor.reason.subHeading") };
  }
  const sceneBlock = sceneFound.block;
  const body = sceneBlock.body as Doc;
  const index = below && isOutlineSub(below) && below.path![0] === scenePos![0] ? below.path![1] : body.blocks.length;
  const to: Place = { list: body, index, chain: [sceneBlock] };
  if (from.list === body) {
    const [start, end] = visual.unitOf(body, from.index);
    if (index >= start && index <= end) return { ok: false, reason: t("editor.reason.itself") };
  }
  const reason = visual.reasonAgainst(found.block, to);
  if (reason) return { ok: false, reason };
  const levelAbove = above && isOutlineSub(above) ? above.level ?? 3 : 2;
  const level = Math.max(3, Math.min(dragged.level ?? 3, levelAbove + 1));
  const indent = 28 + (level - 2) * 14;
  return {
    ok: true,
    line: { left: box.left + indent, right: box.right - 8, y: lineY },
    drop: () => visual.moveTo(from, to),
  };
}

/** Move a top-level block (an act heading or a scene) before another. */
function moveInOutline(from: number, before: number): boolean {
  if (state.mode === "source") return false;
  const doc = visual.current();
  return visual.moveTo({ list: doc, index: from, chain: [] }, { list: doc, index: before, chain: [] });
}

// --- preview (F7) and editing on the page (F12 stage 1) --------------------------------

function renderPages(): void {
  const box = $("pages");
  const imgs = box.querySelectorAll("img");
  state.pages.forEach((url, i) => {
    let img = imgs[i] as HTMLImageElement | undefined;
    if (!img) {
      img = document.createElement("img");
      img.className = "page";
      img.alt = t("status.page", { page: i + 1, pages: state.pages.length });
      img.addEventListener("click", (e) => onPageClick(e, i));
      // F7.2: a new page takes the zoom as soon as its size is known.
      img.addEventListener("load", () => applyZoom());
      box.append(img);
    }
    img.src = url;
  });
  for (let i = state.pages.length; i < imgs.length; i++) imgs[i].remove();
  applyZoom(); // the zoom holds while the preview refreshes
  updateStatus();
}

/** The element under a point of a page (positions in pt from the build). */
function elementAt(page: number, xPt: number, yPt: number, widthPt: number): ElementSpot | null {
  const here = state.elements.filter((e) => e.page === page + 1 && e.y <= yPt + 2);
  const sameColumn = here.filter((e) => e.x <= xPt + 4 && xPt - e.x < widthPt / 2);
  const pool = sameColumn.length ? sameColumn : here;
  let best: ElementSpot | null = null;
  for (const spot of pool) if (!best || spot.y >= best.y) best = spot;
  return best;
}

async function onPageClick(event: MouseEvent, page: number): Promise<void> {
  const img = event.currentTarget as HTMLImageElement;
  const rect = img.getBoundingClientRect();
  const widthPt = img.naturalWidth * 0.75;
  const heightPt = img.naturalHeight * 0.75;
  const xPt = ((event.clientX - rect.left) / rect.width) * widthPt;
  const yPt = ((event.clientY - rect.top) / rect.height) * heightPt;
  await openPopoverAt(page, xPt, yPt, widthPt, event.clientX, event.clientY);
}

async function openPopoverAt(page: number, xPt: number, yPt: number, widthPt: number, left: number, top: number): Promise<boolean> {
  const spot = elementAt(page, xPt, yPt, widthPt);
  if (!spot) return false;
  await flush();
  if (spot.chapter !== state.chapterIndex) await loadChapter(spot.chapter, true);
  if (state.mode === "source") await setMode("visual");
  const found = visual.blockAt(spot.path);
  if (!found) return false;
  if (found.block.type !== "element") {
    // An inline element inside a paragraph: show the paragraph.
    visual.focusBlock(found.block);
    return true;
  }
  const pop = $("popover");
  const body = $("popover-body");
  body.textContent = "";
  body.append(visual.renderElement(found.block, found.place));
  pop.classList.remove("hidden");
  pop.style.left = Math.max(8, Math.min(left, window.innerWidth - pop.offsetWidth - 12)) + "px";
  pop.style.top = Math.max(8, Math.min(top, window.innerHeight - pop.offsetHeight - 12)) + "px";
  body.querySelector<HTMLElement>("input, [contenteditable=true]")?.focus();
  return true;
}

/** Closing the popover applies the change; the page updates (F12.1). */
async function closePopover(): Promise<void> {
  const pop = $("popover");
  if (pop.classList.contains("hidden")) return;
  pop.classList.add("hidden");
  $("popover-body").textContent = "";
  await flush();
  visual.render();
}

function markErrorLine(): void {
  const error = state.errors.find((e) => e.chapter === state.chapter?.path && e.line);
  source?.markError(error ? error.line : null);
}

function showErrors(): void {
  const banner = $("preview-error");
  if (state.errors.length) {
    banner.textContent = state.errors.map((e) => e.text).join("\n");
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
  markErrorLine();
  updateStatus();
}

function onBuild(result: any): void {
  state.building = false;
  if (result.ok) {
    state.pages = result.pages;
    state.elements = result.elements ?? [];
    state.errors = [];
    state.warnings = result.warnings ?? [];
    renderPages();
  } else {
    // F7.1.2: keep the last good pages.
    state.errors = result.errors ?? [];
  }
  showErrors();
  document.body.dataset.buildCount = String(Number(document.body.dataset.buildCount || 0) + 1);
}

function updateCurrentPage(): void {
  const pane = $("preview-pane");
  const imgs = [...$("pages").querySelectorAll("img")];
  const middle = pane.scrollTop + pane.clientHeight / 3;
  let current = 1;
  imgs.forEach((img, i) => {
    if ((img as HTMLElement).offsetTop <= middle) current = i + 1;
  });
  state.currentPage = current;
  updateStatus();
}

let flashTimer: number | null = null;
function flashStatus(text: string): void {
  const flash = $("st-flash");
  flash.textContent = text;
  if (flashTimer !== null) clearTimeout(flashTimer);
  flashTimer = window.setTimeout(() => (flash.textContent = ""), 5000);
}

function updateStatus(): void {
  if (!state.chapter) return;
  $("st-line").textContent = state.line ? t("status.line", { line: state.line }) : "";
  $("st-page").textContent = state.pages.length
    ? t("status.page", { page: Math.min(state.currentPage, state.pages.length), pages: state.pages.length })
    : t("status.noPages");
  $("st-words").textContent = t("status.words", { count: state.chapter.words });
  const problems = $("st-problems");
  const parts = [];
  // F7.1 (M6): a build stopped by the time limit, or a crash in the build
  // helper, is said in words in the status bar, not counted as an error.
  const stopped = state.errors.find((e: any) => e.key === "error.build.timeLimit" || e.key === "error.build.crashed");
  if (stopped) parts.push(stopped.text);
  else parts.push(state.errors.length ? t("status.errors", { count: state.errors.length }) : t("status.noErrors"));
  const warningCount = allWarnings().filter((w) => !w.error).length;
  if (warningCount) parts.push(t("status.warnings", { count: warningCount }));
  problems.textContent = parts.join(" · ");
  problems.classList.toggle("bad", state.errors.length > 0);
  problems.title = allWarnings().map((p) => p.text).join("\n");
  const last = state.info?.lastExport;
  $("st-export").textContent = last ? t("status.lastExport", { time: last.time, file: last.file }) : t("status.noExport");
}

// --- adventure settings page (F7.3, F7.9) ------------------------------------------------

const TITLE_KEYS = ["title", "header", "subtitle", "author", "description", "extra"];
const PAGE_KEYS = ["paper", "orientation", "columns"];
let settingsTimer: number | null = null;

// F18: the adventure settings page is the Adventure section of the Settings window.
async function openSettings(): Promise<void> {
  await flush();
  await openSettingsWindow("adventure");
  $<HTMLInputElement>("set-title").focus();
}

async function fillAdventure(): Promise<void> {
  if (!state.info?.hasDocument) return;
  const info = await call("settings");
  fillSettings(info, true);
}

const SWITCH_KEYS = ["clueOverview", "index", "easyRead"];

function fillSettings(info: any, values: boolean): void {
  const ro = !!state.info?.readOnly;
  // F8: the game system and the theme are chosen here only; F7.3: the secret box fill.
  $("set-gameSystem").textContent = info.gameSystem ?? "";
  const theme = $<HTMLSelectElement>("set-theme");
  theme.textContent = "";
  for (const option of info.themes ?? []) {
    const o = document.createElement("option");
    o.value = option.id;
    o.textContent = option.general ? t("settings.themeGeneral", { name: option.name }) : option.name;
    theme.append(o);
  }
  theme.value = info.themeId ?? "";
  theme.disabled = ro;
  // F14.3 (M6): the version of each, chosen beside it.
  for (const which of ["gameSystem", "theme"]) {
    const pick = $<HTMLSelectElement>(`set-${which}Version`);
    const versions = info.versions?.[which];
    pick.textContent = "";
    for (const version of versions?.installed ?? []) {
      const o = document.createElement("option");
      o.value = version;
      o.textContent = version;
      pick.append(o);
    }
    pick.value = info.versionPreview?.which === which ? info.versionPreview.version : versions?.current ?? "";
    pick.disabled = ro || (versions?.installed ?? []).length < 2;
  }
  const fill = $<HTMLSelectElement>("set-secretFill");
  fill.textContent = "";
  for (const option of ["grey", "beige"]) {
    const o = document.createElement("option");
    o.value = option;
    o.textContent = t(`settings.fill.${option}`);
    fill.append(o);
  }
  fill.value = info.secretFill ?? "grey";
  fill.disabled = ro;
  $<HTMLButtonElement>("set-addFont").disabled = ro;
  for (const key of SWITCH_KEYS) {
    const box = $<HTMLInputElement>("set-" + key);
    box.checked = !!info.switches?.[key];
    box.disabled = ro;
  }
  for (const key of TITLE_KEYS) {
    const input = $<HTMLInputElement | HTMLTextAreaElement>("set-" + key);
    if (values) input.value = info.titlePage[key] ?? "";
    input.disabled = ro;
  }
  for (const key of PAGE_KEYS) {
    const select = $<HTMLSelectElement>("set-" + key);
    if (values) {
      select.textContent = "";
      for (const option of info.options[key]) {
        const o = document.createElement("option");
        o.value = String(option);
        o.textContent = t(`settings.${key}.${option}`);
        select.append(o);
      }
    }
    select.value = String(info.page[key]);
    select.disabled = ro;
    const origin = info.origins[key];
    // F7.3.2: where each value comes from.
    $("origin-" + key).textContent = t(`settings.from.${origin}`, { theme: info.theme });
    $("reset-" + key).classList.toggle("hidden", origin !== "adventure" || ro);
  }
  fillPrintSettings(info, values, ro);
  fillPrint(info, ro);
  // F17.2 (M5): the document language.
  const language = $<HTMLSelectElement>("set-language");
  language.textContent = "";
  for (const code of info.languages ?? ["en"]) {
    const o = document.createElement("option");
    o.value = code;
    const key = `settings.lang.${code}`;
    o.textContent = t(key) === key ? code : t(key);
    language.append(o);
  }
  language.value = info.language ?? "en";
  language.disabled = ro;
}

// F7.3 (M5): margins, header, footer and page numbers; F7.4: page starts.
const MARGIN_KEYS = ["top", "bottom", "inside", "outside"];

function fillPrintSettings(info: any, values: boolean, ro: boolean): void {
  const page = info.page ?? {};
  const m = page.margin_mm ?? {};
  const margins: Record<string, number> = "inside" in m
    ? m : { top: m.top, bottom: m.bottom, inside: m.x, outside: m.x };
  for (const key of MARGIN_KEYS) {
    const input = $<HTMLInputElement>("set-margin-" + key);
    if (values || document.activeElement !== input) input.value = String(margins[key] ?? "");
    input.disabled = ro;
  }
  const origin = info.origins?.margin_mm ?? "theme";
  $("origin-margin_mm").textContent = t(`settings.from.${origin}`, { theme: info.theme });
  $("reset-margin_mm").classList.toggle("hidden", origin !== "adventure" || ro);
  $<HTMLButtonElement>("set-classical").disabled = ro;
  const note = $("set-columnNote");
  note.textContent = t(info.columnTooNarrow ? "settings.columnTooNarrow" : "settings.columnWidth", { mm: info.columnMm });
  note.classList.toggle("warn", !!info.columnTooNarrow);
  const header = $<HTMLInputElement>("set-pageHeader");
  const footer = $<HTMLInputElement>("set-pageFooter");
  if (values || document.activeElement !== header) header.value = page.header ?? "";
  if (values || document.activeElement !== footer) footer.value = page.footer ?? "";
  header.disabled = footer.disabled = ro;
  const numbers = $<HTMLInputElement>("set-pageNumbers");
  numbers.checked = page.page_numbers !== false;
  numbers.disabled = ro;
  const compact = $<HTMLInputElement>("set-compact");
  compact.checked = !!info.compact;
  compact.disabled = ro;
  const grid = $("set-pageStart");
  grid.textContent = "";
  for (const row of info.pageStart ?? []) {
    const name = document.createElement("span");
    name.textContent = row.name;
    const select = document.createElement("select");
    select.dataset.kind = row.kind;
    for (const rule of ["always", "when-needed", "never"]) {
      const o = document.createElement("option");
      o.value = rule;
      o.textContent = rule === row.default ? t("settings.ruleDefault", { rule: t(`settings.rule.${rule}`) }) : t(`settings.rule.${rule}`);
      select.append(o);
    }
    select.value = row.rule;
    select.classList.toggle("changed", !!row.stored);
    select.disabled = ro || !!info.compact;
    select.addEventListener("change", () => settingsChanged("pageStart", row.kind, select.value));
    grid.append(name, select);
  }
}

function fillPrint(info: any, ro: boolean): void {
  const pr = info.print ?? {};
  const order = $<HTMLSelectElement>("set-bookletOrder");
  order.textContent = "";
  for (const o of ["fold", "side-by-side"]) {
    const el = document.createElement("option");
    el.value = o;
    el.textContent = t(`settings.booklet.order.${o}`);
    order.append(el);
  }
  order.value = pr.order ?? "fold";
  const sheet = $<HTMLSelectElement>("set-bookletSheet");
  sheet.textContent = "";
  for (const o of info.sheetOptions ?? []) {
    const el = document.createElement("option");
    el.value = o;
    el.textContent = t(`settings.paper.${o}`);
    sheet.append(el);
  }
  sheet.value = pr.sheet ?? "";
  const bleed = $<HTMLInputElement>("set-bleed");
  if (document.activeElement !== bleed) bleed.value = String(pr.bleed_mm ?? 3);
  order.disabled = sheet.disabled = bleed.disabled = ro;
}

function sendMargins(): void {
  const margins: Record<string, number> = {};
  for (const key of MARGIN_KEYS) {
    const value = Number($<HTMLInputElement>("set-margin-" + key).value);
    if (!Number.isFinite(value) || value <= 0) return;
    margins[key] = value;
  }
  settingsChanged("page", "margin_mm", margins);
}

function settingsChanged(part: "titlePage" | "page" | "switches" | "look" | "pageStart" | "compact" | "print", key: string, value: unknown): void {
  pendingSettings[part] = { ...(pendingSettings[part] ?? {}), [key]: value };
  if (settingsTimer !== null) clearTimeout(settingsTimer);
  settingsTimer = window.setTimeout(sendSettings, part === "titlePage" || key === "header" || key === "footer" ? 400 : 0);
}

let pendingSettings: Record<string, Record<string, unknown>> = {};

async function sendSettings(): Promise<void> {
  settingsTimer = null;
  const data: Record<string, unknown> = pendingSettings;
  pendingSettings = {};
  if (!Object.keys(data).length) return;
  // The look (theme, secret box fill) is sent as plain values.
  const look = (data.look ?? {}) as Record<string, unknown>;
  delete data.look;
  Object.assign(data, look);
  // F7.4 (M5): compact mode is one value.
  if (data.compact) data.compact = (data.compact as Record<string, unknown>).on;
  const info = await call("setSettings", JSON.stringify(data));
  fillSettings(info, false);
  state.info = await call("info");
  renderTabs();
  await call("requestBuild");
}

async function closeSettings(): Promise<void> {
  // F16 (M5): closing with unsaved colours asks whether to save them.
  if (!(await beforeCloseSettings())) return;
  if (settingsTimer !== null) {
    clearTimeout(settingsTimer);
    await sendSettings();
  }
  $("settings").classList.add("hidden");
  if (state.info?.hasDocument) {
    state.defs = (await call("editorInfo")).elements;
    visual.setDefinitions(state.defs);
    renderToolbar();
  }
}

// --- find and replace (F4.7) -----------------------------------------------------------

function openFind(): void {
  $("findbar").classList.remove("hidden");
  const input = $<HTMLInputElement>("find-query");
  input.focus();
  input.select();
}

async function runFind(): Promise<void> {
  await flush();
  state.findHits = await call("find", JSON.stringify({ query: $<HTMLInputElement>("find-query").value, matchCase: $<HTMLInputElement>("find-case").checked }));
  state.findIndex = -1;
  $("find-count").textContent = t("find.count", { count: state.findHits.length });
  if (state.findHits.length) await stepFind(1);
}

async function stepFind(step: number): Promise<void> {
  if (!state.findHits.length) return;
  state.findIndex = (state.findIndex + step + state.findHits.length) % state.findHits.length;
  const hit = state.findHits[state.findIndex];
  $("find-count").textContent = t("find.position", { index: state.findIndex + 1, count: state.findHits.length });
  if (hit.chapter !== state.chapterIndex) await loadChapter(hit.chapter, true);
  if (state.mode === "source") source.goToLine(hit.line);
  else visual.scrollToLine(hit.line);
}

async function replaceAll(): Promise<void> {
  await flush();
  const query = $<HTMLInputElement>("find-query").value;
  const reply = await call("replaceAll", JSON.stringify({
    query, replacement: $<HTMLInputElement>("find-replace").value, matchCase: $<HTMLInputElement>("find-case").checked,
  }));
  $("find-count").textContent = t("find.replaced", { count: reply.count });
  if (reply.count) {
    const chapter: Chapter = await call("chapter", state.chapterIndex);
    state.chapter = chapter;
    pushHistory(chapter.text);
    if (state.mode === "source") source.set(chapter.text);
    else visual.load(chapter.doc);
    renderOutline();
    updateStatus();
    renderTabs();
  }
  state.findHits = [];
}

// --- work protection dialogs (F2.7, F2.8) ------------------------------------------------

async function offerRecovery(): Promise<void> {
  const items: any[] = await call("recoveries");
  if (!items.length) return;
  const dialog = $<HTMLDialogElement>("recover-dialog");
  const list = $("recover-list");
  const fill = (rest: any[]) => {
    list.textContent = "";
    if (!rest.length) {
      dialog.close();
      return;
    }
    for (const item of rest) {
      const li = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = t("recover.item", { title: item.title, time: new Date(item.time * 1000).toLocaleString() });
      const restore = document.createElement("button");
      restore.type = "button";
      restore.className = "primary small";
      restore.textContent = t("recover.restore");
      restore.addEventListener("click", async () => {
        await call("restoreRecovery", item.session);
        dialog.close();
        await refresh();
      });
      const discard = document.createElement("button");
      discard.type = "button";
      discard.textContent = t("recover.discard");
      discard.addEventListener("click", async () => {
        await call("discardRecovery", item.session);
        fill(rest.filter((r) => r !== item));
      });
      li.append(label, restore, discard);
      list.append(li);
    }
  };
  fill(items);
  dialog.showModal();
}

async function openRevert(): Promise<void> {
  await flush();
  const items: any[] = await call("snapshots");
  const dialog = $<HTMLDialogElement>("revert-dialog");
  const list = $("revert-list");
  list.textContent = "";
  $("revert-empty").classList.toggle("hidden", items.length > 0);
  for (const item of items) {
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "link";
    button.textContent = new Date(item.time * 1000).toLocaleString();
    button.addEventListener("click", async () => {
      dialog.close();
      await call("revertTo", item.id);
      await loadChapter(0, false);
      const chapter: Chapter = await call("chapter", 0);
      pushHistory(chapter.text);
      renderTabs();
    });
    li.append(button);
    list.append(li);
  }
  dialog.showModal();
}

// --- the start-up checks in the main window (F9, M5) -------------------------------------

let spellNoted = false;
let checkReport = "";

/** The quiet bar that names what the start-up window found missing. */
async function showStartupReport(): Promise<void> {
  const report = await call("startupReport");
  const problems: { text: string }[] = report?.problems ?? [];
  $("startup-bar").classList.toggle("hidden", problems.length === 0);
  $("startup-bar-text").textContent = problems.length
    ? t("startup.barText", { parts: problems.map((p) => p.text).join("; ") })
    : "";
  if (report?.openError) showMessage(report.openError);
}

function checkLine(ok: boolean, text: string): HTMLElement {
  const li = document.createElement("li");
  li.className = ok ? "passed" : "failed";
  const mark = document.createElement("span");
  mark.className = "mark";
  mark.textContent = ok ? "\u2713" : "\u2715";
  const line = document.createElement("span");
  line.textContent = text;
  li.append(mark, line);
  return li;
}

/** Help ▸ Check installation: the same list as the start-up window. */
async function openCheckDialog(): Promise<void> {
  const dialog = $<HTMLDialogElement>("check-dialog");
  $("check-list").textContent = "";
  $("check-themes").textContent = "";
  $("check-summary").textContent = t("startup.checking");
  $("check-version").textContent = "";
  if (!dialog.open) dialog.showModal();
  const reply = await call("checkInstallation");
  checkReport = reply.report;
  $("check-version").textContent = t("startup.version", { version: reply.version });
  for (const r of reply.results) $("check-list").append(checkLine(r.ok, r.text));
  const failed = reply.results.filter((r: any) => !r.ok).length;
  $("check-summary").textContent = failed ? t("startup.someFailed", { count: failed }) : t("startup.allPassed");
  $<HTMLButtonElement>("check-selftest").disabled = false;
  document.body.dataset.checkDone = String(Number(document.body.dataset.checkDone || 0) + 1);
  await showStartupReport();
}

async function runSelfTest(): Promise<void> {
  $<HTMLButtonElement>("check-selftest").disabled = true;
  $("check-themes").textContent = "";
  $("check-summary").textContent = t("startup.selfTestRunning");
  await call("themeSelfTest");
}

function onSelfTest(reply: any): void {
  const lines: any[] = reply?.lines ?? [];
  const bad = lines.filter((l) => !l.ok);
  for (const l of lines) {
    $("check-themes").append(checkLine(l.ok, l.ok
      ? t("startup.selfTestLine", { theme: l.theme, gameSystem: l.gameSystem })
      : t("startup.selfTestLineFailed", { theme: l.theme, gameSystem: l.gameSystem, problem: l.problems.join("; ") })));
  }
  const failed = reply?.ok === false ? 1 : bad.length;
  $("check-summary").textContent = failed ? t("startup.selfTestFailed", { count: failed }) : t("startup.selfTestPassed");
  $<HTMLButtonElement>("check-selftest").disabled = false;
  checkReport += "\n" + $("check-summary").textContent + "\n" + [...$("check-themes").children].map((li) => li.textContent).join("\n") + "\n";
  document.body.dataset.selfTestDone = String(Number(document.body.dataset.selfTestDone || 0) + 1);
}

// --- the update check (F21, M6 part C) -------------------------------------------------

let updateWanted = false;

/** Help ▸ Check for updates…: reads the update file in the background. */
async function checkForUpdates(): Promise<void> {
  const dialog = $<HTMLDialogElement>("update-dialog");
  $("update-text").textContent = t("update.checking");
  $("update-note-box").classList.add("hidden");
  $("update-open").classList.add("hidden");
  if (!dialog.open) dialog.showModal();
  updateWanted = true;
  await call("checkForUpdates");
}

function onUpdateChecked(r: any): void {
  // The weekly check stays quiet unless a newer version exists (F21.4).
  if (r?.auto ? r.state !== "newer" : !updateWanted) return;
  if (!r.auto) updateWanted = false;
  const texts: Record<string, string> = {
    "no-address": t("update.noAddress"),
    "not-https": t("update.notHttps"),
    current: t("update.current", { current: r.current }),
    unreachable: t("update.unreachable"),
    invalid: t("update.invalid"),
  };
  const newer = r.state === "newer";
  $("update-text").textContent = newer
    ? t("update.newer", { version: r.version, current: r.current }) + (r.download ? "" : " " + t("update.noDownload"))
    : texts[r.state] ?? texts.invalid;
  $("update-note").textContent = newer ? r.note || "" : "";
  $("update-note-box").classList.toggle("hidden", !(newer && r.note));
  $("update-open").classList.toggle("hidden", !(newer && r.download));
  const dialog = $<HTMLDialogElement>("update-dialog");
  if (!dialog.open) dialog.showModal();
  document.body.dataset.updateState = r.state;
  document.body.dataset.updateDone = String(Number(document.body.dataset.updateDone || 0) + 1);
}

/** F21.4: at first start Scriptorum asks once, with the answer off by default;
 * then the weekly check runs only if the author turned it on. */
async function offerUpdateQuestion(): Promise<void> {
  const reply = await call("updatePrompt");
  if (reply?.ask) {
    const answer = await askChoice(t("update.askText"), t("update.askYes"), "", t("update.askNo"));
    await call("answerUpdatePrompt", answer === "yes");
  }
  await call("weeklyUpdateCheck");
}

// --- keyboard ---------------------------------------------------------------------------

// --- full screen (F9, M6 part B) -------------------------------------------------------
let fullScreen = false;

function renderFullScreen(): void {
  const b = $("tb-fullscreen");
  b.innerHTML = fullScreen ? iconCornersIn : iconCornersOut;
  b.setAttribute("aria-pressed", String(fullScreen));
  const label = t(fullScreen ? "toolbar.exitFullScreen" : "toolbar.fullScreen");
  b.title = label;
  b.setAttribute("aria-label", label);
}

async function setFullScreen(on: boolean): Promise<void> {
  const reply = await call("setFullScreen", on);
  fullScreen = !!reply?.fullScreen;
  renderFullScreen();
  buildMenus();
}

function onKey(event: KeyboardEvent): void {
  // F9 (M6): F11 (Windows, Linux) and Ctrl+⌘+F (Mac) switch full screen.
  if (event.key === "F11" || (event.ctrlKey && event.metaKey && event.key.toLowerCase() === "f")) {
    event.preventDefault();
    setFullScreen(!fullScreen);
    return;
  }
  if (event.key === "Escape") {
    // Esc leaves full screen only when nothing else is open to close.
    const somethingOpen = viewOpen() || !!document.querySelector("dialog[open]") || !$("settings").classList.contains("hidden")
      || !$("popover").classList.contains("hidden") || !$("menu-popup").classList.contains("hidden");
    if (fullScreen && !somethingOpen) {
      setFullScreen(false);
      return;
    }
    if (viewOpen() && !document.querySelector("dialog[open]")) closeView();
    closePopover();
    hidePopup();
    if (!$("settings").classList.contains("hidden")) closeSettings();
    return;
  }
  const mod = event.ctrlKey || event.metaKey;
  if (!mod) return;
  const key = event.key.toLowerCase();
  const has = !!state.info?.hasDocument;
  if (key === "z" && has) {
    event.preventDefault();
    if (event.shiftKey) redo();
    else undo();
  } else if (key === "y" && has) {
    event.preventDefault();
    redo();
  } else if (key === "s" && !event.shiftKey && has) {
    event.preventDefault();
    save("save");
  } else if (key === ",") {
    event.preventDefault();
    openSettingsWindow();
  } else if (key === "o") {
    event.preventDefault();
    openDialog();
  } else if (key === "n") {
    event.preventDefault();
    openNewDialog();
  } else if (key === "f" && has) {
    event.preventDefault();
    openFind();
  } else if (key === "w" && has) {
    event.preventDefault();
    closeTab(state.info.id);
  } else if (key === "enter" && state.mode === "hybrid" && document.activeElement === $("hybrid-source")) {
    event.preventDefault();
    applyHybrid();
  } else if (has && !state.info.readOnly) {
    const groups = new Set<string>();
    for (const def of state.defs) {
      if (def.shortcut && matches(def.shortcut, event)) {
        event.preventDefault();
        if (def.shortcutGroup) {
          if (!groups.has(def.shortcutGroup)) chooseGroup(def.shortcutGroup);
          groups.add(def.shortcutGroup);
          continue;
        }
        insert(def.id);
        return;
      }
    }
  }
}

function matches(shortcut: string, event: KeyboardEvent): boolean {
  const parts = shortcut.toLowerCase().split("+");
  const key = parts[parts.length - 1];
  const wantShift = parts.includes("shift");
  const k = event.key.toLowerCase();
  return (k === key || (key === "enter" && k === "enter")) && event.shiftKey === wantShift;
}

// --- start --------------------------------------------------------------------------------

async function boot(): Promise<void> {
  await connect();
  setStrings(await call("strings"));
  document.title = t("app.name");
  applyStrings(document);

  const hooks: EditorHooks = {
    onChange: (doc) => schedule(() => sendDoc(doc), 350),
    onCommit: (doc) => commit(doc),
    onFocusBlock: (block, place) => {
      state.line = block?.line ?? null;
      updateStatus();
      updateScenePanel(state.line);
      if (state.mode === "hybrid" && block && place) showHybrid({ block, place });
    },
    openInsertMenu: (anchor, place, kinds) => showPopup(anchor, insertItems(kinds, (kind) => insert(kind, place))),
    openContextMenu: (event, place) => openContextMenu(event, place),
    // M6 part C2: why a block may not go somewhere, and who no longer knows something.
    flash: (text) => flashStatus(text),
    pickImage: async (accept) => {
      // 11.4 (M6 part C): a portrait must be a JPEG or PNG file.
      const result = await call(accept === "jpeg-png" ? "addPortraitDialog" : "addImageDialog");
      if (!result?.ok && result?.error) showMessage(result.error);
      return result?.ok ? result.path : null;
    },
    storeImage: async (name, dataUrl) => {
      const result = await call("addImageData", name, dataUrl);
      if (!result?.ok && result?.error) showMessage(result.error);
      return result?.ok ? result.path : null;
    },
    imageUrl: async (path) => {
      const result = await call("imageUrl", path);
      return result?.ok ? result.url : null;
    },
    afterRender: () => spelling?.schedule(200),
    codexEntries: () => codex.entries,
    maps: () => codex.maps,
    createEntry: async (type, title) => {
      if (type && title) {
        const reply = await call("createEntry", JSON.stringify({ type, title }));
        if (!reply?.ok) {
          if (reply?.error) showMessage(reply.error);
          return null;
        }
        state.worldMarks.push(state.historyPos);
        await loadCodex();
        return reply.id;
      }
      return newEntry(type, title ?? "");
    },
    openEntry: (id) => openEntry(id),
    openMap: (id) => openMap(id),
    onCollapseChange: () => renderOutline(),
  };
  visual = new VisualEditor($("visual"), hooks);
  await initShell({
    defs: () => state.defs,
    refresh: () => refresh(),
    hasDocument: () => !!state.info?.hasDocument,
    readOnly: () => !!state.info?.readOnly,
    insert: (kind, variant) => insert(kind, undefined, variant),
    showPopup: (anchor, items) => showPopup(anchor, items as MenuItem[]),
    newEntry: () => newEntry().then((id) => { if (id) openEntry(id); }),
    newMap: () => newMap(),
    styleOfFocus,
    styleKinds,
    kindLabel,
    setStyle,
    fillAdventure,
    adventureName: () => (state.info?.hasDocument ? state.info.title : null),
    addFont: () => addFont(),
    onStartMode: () => undefined,
  });
  setChipLabeler((kind, args) => {
    if (kind === "footnote") {
      // F7.7 (M5): a footnote chip shows the start of its text.
      const text = /text:\s*"((?:[^"\\]|\\.)*)"/.exec(args)?.[1] ?? "";
      return "\u2020 " + (text.length > 28 ? text.slice(0, 28) + "\u2026" : text);
    }
    if (kind !== "mention" && kind !== "see") return null;
    const id = /entry:\s*"([^"]*)"/.exec(args)?.[1] ?? "";
    const title = codex.entries.find((e) => e.id === id)?.title ?? t("editor.missingEntry", { id });
    return (kind === "see" ? "\u2192 " : "@ ") + title;
  });
  initWorld({
    showMessage,
    flash: flashStatus,
    afterChange: reloadAfterWorld,
    markUndoStep: () => state.worldMarks.push(state.historyPos),
    insertInline: (markup) => {
      closeView();
      if (state.mode === "source") return false;
      return restoreRange() && visual.insertInline(markup);
    },
    insertBlock: (block) => {
      closeView();
      if (state.mode === "source") setMode("visual");
      visual.insertBlock(block, visual.focused());
    },
    goTo: async (chapter, line) => {
      closeView();
      if (chapter !== state.chapterIndex) await loadChapter(chapter, true);
      if (state.mode === "source") source.goToLine(line);
      else visual.scrollToLine(line);
    },
    chapterIndex: () => state.chapterIndex,
    readOnly: () => !!state.info?.readOnly,
    setHandoutsOnly: (on) => setHandoutsOnly(on),
    handoutsOnly: () => state.handoutsOnly,
    exportHandouts: () => exportHandouts(),
    saveSpot: () => saveSpot(),
    restoreSpot: () => restoreSpot(),
  });
  document.addEventListener("selectionchange", () => {
    const sel = getSelection();
    if (!sel || !sel.rangeCount) return;
    const node = sel.anchorNode;
    const el = node instanceof HTMLElement ? node : node?.parentElement;
    if (el && $("visual").contains(el) && el.closest(".rich")) lastRange = sel.getRangeAt(0).cloneRange();
  });
  spelling = new Spelling($("visual"), async (words) => {
    const reply = await call("spell", JSON.stringify(words));
    // F9: spell check says it is unavailable instead of waiting silently.
    if (reply?.unavailable && !spellNoted) {
      spellNoted = true;
      flashStatus(reply.unavailable);
    }
    return reply;
  });
  $("visual").addEventListener("input", () => spelling.schedule());
  $("visual").addEventListener("dragover", (e) => {
    if (e.dataTransfer?.types.includes("Files")) e.preventDefault();
  });
  $("visual").addEventListener("drop", (e) => {
    const file = e.dataTransfer?.files?.[0];
    if (!file || state.info?.readOnly) return;
    e.preventDefault();
    visual.dropImage(file, visual.focused());
  });
  source = new SourceEditor(
    $("source"),
    (text) => schedule(() => sendText(text), 300),
    (line) => {
      state.line = line;
      updateStatus();
    },
  );

  for (const m of ["visual", "hybrid", "source"] as Mode[]) $("mode-" + m).addEventListener("click", () => setMode(m));
  $("hybrid-source").addEventListener("blur", () => applyHybrid());
  $("tb-style").addEventListener("change", (e) => setStyle((e.target as HTMLSelectElement).value));
  document.addEventListener("focusin", () => renderStyle());
  $("w-new").addEventListener("click", () => openNewDialog());
  $("w-example").addEventListener("click", () => openExample());
  $("set-theme").addEventListener("change", (e) => settingsChanged("look", "theme", (e.target as HTMLSelectElement).value));
  $("set-gameSystemVersion").addEventListener("change", (e) => pickVersion("gameSystem", (e.target as HTMLSelectElement).value));
  $("set-themeVersion").addEventListener("change", (e) => pickVersion("theme", (e.target as HTMLSelectElement).value));
  $("version-apply").addEventListener("click", () => endVersionPreview(true));
  $("version-cancel").addEventListener("click", () => endVersionPreview(false));
  $("set-secretFill").addEventListener("change", (e) => settingsChanged("look", "secretFill", (e.target as HTMLSelectElement).value));
  $("set-language").addEventListener("change", async (e) => {
    settingsChanged("look", "language", (e.target as HTMLSelectElement).value);
    spelling.schedule(400); // F17.2: spell check follows the document language
  });
  $("set-addFont").addEventListener("click", () => addFont());
  $("w-open").addEventListener("click", () => openDialog());
  $("preview-pane").addEventListener("scroll", updateCurrentPage);
  $("popover-close").addEventListener("click", () => closePopover());
  document.addEventListener("mousedown", (e) => {
    const pop = $("popover");
    if (!pop.classList.contains("hidden") && !pop.contains(e.target as Node) && !$("menu-popup").contains(e.target as Node)) closePopover();
  });
  $("settings-close").addEventListener("click", () => closeSettings());
  for (const key of TITLE_KEYS) $("set-" + key).addEventListener("input", (e) => settingsChanged("titlePage", key, (e.target as HTMLInputElement).value));
  for (const key of PAGE_KEYS) {
    $("set-" + key).addEventListener("change", (e) => settingsChanged("page", key, (e.target as HTMLSelectElement).value));
    $("reset-" + key).addEventListener("click", () => settingsChanged("page", key, null));
  }
  for (const key of MARGIN_KEYS) $("set-margin-" + key).addEventListener("change", () => sendMargins());
  $("reset-margin_mm").addEventListener("click", () => settingsChanged("page", "margin_mm", null));
  $("set-classical").addEventListener("click", async () => {
    const info = await call("settings");
    for (const key of MARGIN_KEYS) $<HTMLInputElement>("set-margin-" + key).value = String(info.classical[key]);
    sendMargins();
  });
  $("set-pageHeader").addEventListener("input", (e) => settingsChanged("page", "header", (e.target as HTMLInputElement).value));
  $("set-pageFooter").addEventListener("input", (e) => settingsChanged("page", "footer", (e.target as HTMLInputElement).value));
  $("set-pageNumbers").addEventListener("change", (e) => settingsChanged("page", "page_numbers", (e.target as HTMLInputElement).checked));
  $("set-compact").addEventListener("change", (e) => settingsChanged("compact", "on", (e.target as HTMLInputElement).checked));
  $("set-bookletOrder").addEventListener("change", (e) => settingsChanged("print", "booklet_order", (e.target as HTMLSelectElement).value));
  $("set-bookletSheet").addEventListener("change", (e) => settingsChanged("print", "booklet_sheet", (e.target as HTMLSelectElement).value));
  $("set-bleed").addEventListener("change", (e) => settingsChanged("print", "bleed_mm", Number((e.target as HTMLInputElement).value)));
  $("st-problems").addEventListener("click", () => openWarnings());
  $("warnings-close").addEventListener("click", () => $("warnings-panel").classList.add("hidden"));
  $("find-go").addEventListener("click", () => runFind());
  $("find-query").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (state.findHits.length) stepFind(e.shiftKey ? -1 : 1);
      else runFind();
    }
  });
  $("find-query").addEventListener("input", () => (state.findHits = []));
  $("find-next").addEventListener("click", () => stepFind(1));
  $("find-prev").addEventListener("click", () => stepFind(-1));
  $("find-all").addEventListener("click", () => replaceAll());
  $("find-close").addEventListener("click", () => $("findbar").classList.add("hidden"));
  $("recover-later").addEventListener("click", () => $<HTMLDialogElement>("recover-dialog").close());
  $("revert-cancel").addEventListener("click", () => $<HTMLDialogElement>("revert-dialog").close());
  $("message-ok").addEventListener("click", () => $<HTMLDialogElement>("message-dialog").close());
  document.addEventListener("keydown", onKey, true);
  document.addEventListener("mousedown", hideOnOutside, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hidePopup();
  });
  $("tb-preview").addEventListener("click", () => setPreview(!previewShown));
  $("tb-handouts").addEventListener("click", () => setHandoutsOnly(!state.handoutsOnly));
  $("tb-fullscreen").addEventListener("click", () => setFullScreen(!fullScreen));
  initAbout();
  on("fullScreenChanged", (on: boolean) => {
    fullScreen = !!on;
    renderFullScreen();
    buildMenus();
  });
  call("isFullScreen").then((on: boolean) => {
    fullScreen = !!on;
    renderFullScreen();
  });
  for (const name of ["outline", "codex", "handouts"] as const) $("nav-" + name).addEventListener("click", () => showNavTab(name));
  for (const key of SWITCH_KEYS) $("set-" + key).addEventListener("change", (e) => settingsChanged("switches", key, (e.target as HTMLInputElement).checked));
  let storedPreview: string | null = null;
  try {
    storedPreview = localStorage.getItem("scriptorum.preview");
  } catch {
    storedPreview = null;
  }
  setPreview(storedPreview !== "0");

  on("buildFinished", onBuild);
  on("buildStarted", () => (state.building = true));
  on("documentChanged", () => refresh());
  on("spellReady", () => spelling.schedule(0));
  on("suggestions", onSuggestions);
  on("selfTestFinished", onSelfTest);
  on("updateChecked", onUpdateChecked);
  $("update-close").addEventListener("click", () => $<HTMLDialogElement>("update-dialog").close());
  $("update-open").addEventListener("click", () => call("openDownloadPage"));
  initZoom();
  $("zoom-window").addEventListener("click", () => call("openPreviewWindow"));
  $("startup-bar-close").addEventListener("click", () => $("startup-bar").classList.add("hidden"));
  $("startup-bar-check").addEventListener("click", () => openCheckDialog());
  $("check-close").addEventListener("click", () => $<HTMLDialogElement>("check-dialog").close());
  wireGuide();
  $("check-copy").addEventListener("click", () => call("copyText", checkReport));
  $("check-selftest").addEventListener("click", () => runSelfTest());

  await refresh();
  state.ready = true;
  await call("uiReady");
  await showStartupReport();
  await offerRecovery();
  await offerUpdateQuestion();
}

// Hooks the automated interface tests use (tests/test_ui_smoke.py).
(window as any).__scriptorum = {
  state: () => ({
    ready: state.ready,
    mode: state.mode,
    text: state.chapter?.text ?? null,
    pages: state.pages.length,
    elements: state.elements,
    errors: state.errors,
    warnings: state.warnings,
    historyPos: state.historyPos,
    historyLength: state.history.length,
    outline: state.chapter?.outline ?? [],
    words: state.chapter?.words ?? 0,
    info: state.info,
    tabs: state.tabs,
    status: ["st-line", "st-page", "st-words", "st-problems", "st-export"].map((id) => $(id).textContent),
  }),
  flush,
  setMode,
  undo,
  redo,
  insert: (kind: string) => insert(kind, visual.focused()),
  insertInline: (kind: string) => insert(kind),
  refresh,
  newDialog: openNewDialog,
  setPreview,
  previewShown: () => previewShown,
  toggleCollapse: (key: string) => visual.toggleCollapse(key),
  convert: (path: number[], kind: string) => {
    const found = visual.blockAt(path);
    if (found) visual.convert(found.place, kind);
  },
  move: (path: number[], step: number) => {
    const found = visual.blockAt(path);
    if (found) visual.move(found.place, step);
  },
  moveInOutline,
  openSettings,
  closeSettings,
  // M5
  zoom: { get: () => ({ zoom: currentZoom(), percent: zoomPercent(), spread: isSpread() }), set: setZoom, step: zoomStep, apply: applyZoom, spread: setSpread },
  openCheckDialog,
  afterExport,
  openWarnings,
  runSelfTest,
  showStartupReport,
  // M4
  setDefs: (defs: ElementDef[]) => {
    state.defs = defs;
    renderToolbar();
  },
  openSettingsWindow,
  showSection,
  settingsSection,
  shell: shellTest,
  setFullScreen,
  fullScreen: () => fullScreen,
  about: aboutTest,
  // M6 part C: the update check (F21)
  updates: { check: checkForUpdates, offer: offerUpdateQuestion },
  pickVersion,
  endVersionPreview,
  groupItems,
  openExample,
  applyAppearance,
  menuModel: () => menuModel().map((m) => ({ key: m.key, items: m.items.map((i) => ({ label: i.label, disabled: !!i.disabled, children: (i.children ?? []).map((c) => c.label) })) })),
  openPopoverAt,
  closePopover,
  runFind,
  replaceAll,
  openFind,
  switchTab,
  closeTab,
  kindOf,
  isDoc,
  dropImage: async (name: string, base64: string) => {
    const bytes = Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
    await visual.dropImage(new File([bytes], name, { type: "image/png" }), visual.focused());
  },
  blockAt: (path: number[]) => visual.blockAt(path)?.block ?? null,
  // M3
  world: worldTest,
  setHandoutsOnly,
  showNavTab,
  personToEntry: (path: number[]) => {
    const found = visual.blockAt(path);
    if (found) return personToEntry(found.place);
  },
  offerUpgrade,
  reloadAfterWorld,
  worldMarks: () => state.worldMarks.length,
};

boot();
