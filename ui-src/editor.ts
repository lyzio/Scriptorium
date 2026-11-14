// The Visual and Source editors (F4).
//
// The Visual editor shows each block as formatted text or as the form/frame
// its element definition asks for (F4.3). It edits the block model it was
// given and removes the stored text ("raw") of every block it changes, so
// the core writes changed blocks afresh and leaves every other block
// byte-identical (F4.11).
//
// Milestone 3 adds: codex reference fields (one entry or several, F3.5), map
// references and "Handout also" (F5.4, F5.5), the New look button of a
// handout (F6.5), and M2 text fields shown only while they still hold text
// (F3.12).
//
// Milestone 6 part C2 adds: three levels of sub-heading inside scenes, moved
// with everything under them, raised and lowered (F4); the grip as a strip
// down the block's left side and Scriptorum's own dragging (F4.13, drag.ts);
// moving blocks into and out of containers, with Alt+→ and Alt+←; and
// Information moved into and out of person cards keeping who knows it.
//
// Milestone 2 adds: the grip handle with drag and drop, the arrows and
// Alt+↑/↓ (F4.13), Convert to (F4.2), every field kind of 9.4, creature stat
// blocks (11.5), countdowns (11.6), inline dice (11.7), tables (F4.5),
// images (F4.6) and read-only display (F2.3, F2.9).

import { DropTarget, startDrag } from "./drag";
import { t } from "./i18n";
import { chipHtml, escapeInline, htmlToInline, inlineToHtml, inlineToPlain } from "./inline";
import { Block, Doc, ElementDef, FieldDef, isDoc } from "./model";

export interface Place {
  list: Doc;
  index: number;
  chain: Block[]; // element blocks that contain the list, outermost first
}

export interface EditorHooks {
  /** An edit while typing: sent after a pause (F7.1). */
  onChange(doc: Doc): void;
  /** A structural change (move, convert, insert, delete): one undo step now. */
  onCommit(doc: Doc): void;
  onFocusBlock(block: Block | null, place: Place | null): void;
  openInsertMenu(anchor: HTMLElement, place: Place, kinds: string[]): void;
  openContextMenu(event: MouseEvent, place: Place): void;
  pickImage(accept?: string): Promise<string | null>;
  storeImage(name: string, dataUrl: string): Promise<string | null>;
  imageUrl(path: string): Promise<string | null>;
  afterRender(): void;
  /** An act or scene was folded or unfolded (screen only, never saved). */
  onCollapseChange?(): void;
  // Milestone 3: codex references (F3.5) and maps (F5.4).
  codexEntries(): { id: string; title: string; type: string; text?: string }[];
  /** F3 (M6 part C4): codex types that have a card of their own (Person, Creature). */
  typesWithCard?(): string[];
  maps(): { id: string; title: string }[];
  /** A new codex entry; with a name and a single type it is made at once. */
  createEntry(type: string, title?: string): Promise<string | null>;
  openEntry(id: string): void;
  /** Issue #7 (M6-0.6.9): text typed into a clue's Information item while
   *  the clue has no description becomes the clue's description. */
  adoptClueText?(clue: string, markup: string): void;
  openMap(id: string): void;
  /** M6 part C2: a short message in the status bar (why a block may not go somewhere). */
  flash(text: string): void;
}

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className = "",
  attrs: Record<string, string> = {},
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

/** Issue #9: the block whose ↑ ↓ + × menu the pointer is on. */
let heldMenu: HTMLElement | null = null;

function holdMenu(wrap: HTMLElement): void {
  if (heldMenu && heldMenu !== wrap) heldMenu.classList.remove("menu-held");
  heldMenu = wrap;
  wrap.classList.add("menu-held");
  document.body.classList.add("blk-menu-held");
}

function releaseMenu(): void {
  heldMenu?.classList.remove("menu-held");
  heldMenu = null;
  document.body.classList.remove("blk-menu-held");
}

// A button that moves or removes its block redraws the editor, so the menu
// may vanish without the pointer leaving it: let go as soon as the pointer is
// anywhere else.
document.addEventListener("pointermove", (event) => {
  if (heldMenu && !(event.target instanceof Element && event.target.closest(".blk-controls"))) releaseMenu();
}, true);

function iconButton(labelKey: string, symbol: string, onClick: () => void): HTMLButtonElement {
  const button = el("button", "icon-btn", { type: "button" });
  const text = t(labelKey);
  button.title = text;
  button.setAttribute("aria-label", text);
  button.textContent = symbol; // a glyph, not text
  button.addEventListener("mousedown", (e) => e.preventDefault());
  button.addEventListener("click", (e) => {
    e.stopPropagation();
    onClick();
  });
  return button;
}

/** The kind of a block as the allow-lists see it. Sub-headings 1, 2 and 3
 * (heading levels 3, 4 and 5) are "heading-3", "heading-4" and "heading-5";
 * an act heading (and any level 1 or 2) is "heading". */
export function kindOf(block: Block): string {
  if (block.type === "heading") return isSubHeading(block) ? "heading-" + block.level : "heading";
  return block.type === "element" ? block.kind! : block.type;
}

/** The sub-heading kinds, for menus and the paragraph style (F4, M6 part C). */
export const SUB_HEADINGS = ["heading-3", "heading-4", "heading-5"];

export function isSubHeading(block: Block | undefined): boolean {
  return !!block && block.type === "heading" && (block.level ?? 1) >= 3;
}

function levelOf(block: Block | undefined): number {
  return block && block.type === "heading" ? block.level ?? 1 : 0;
}

/** Pixels of pointer position per nesting level when a drag is at the edge
 * of a container (M6 part C2). */
const INDENT = 24;

function newSceneId(): string {
  return "s-" + Math.random().toString(16).slice(2, 8);
}

export class VisualEditor {
  private doc: Doc = { blocks: [], trail: "\n" };
  private defs = new Map<string, ElementDef>();
  private focus: Place | null = null;
  private sceneNumber = 0;
  /** Each block's place, for Scriptorum's own dragging (M6 part C2). */
  private placeOf = new WeakMap<HTMLElement, Place>();
  private subKey = 0;
  private openSections = new Set<string>();
  readOnly = false;

  constructor(private root: HTMLElement, private hooks: EditorHooks) {
    root.addEventListener("keydown", (e) => this.onKey(e));
  }

  setDefinitions(defs: ElementDef[]): void {
    this.defs = new Map(defs.map((d) => [d.id, d]));
  }

  definitions(): ElementDef[] {
    return [...this.defs.values()];
  }

  definition(kind: string): ElementDef | undefined {
    return this.defs.get(kind);
  }

  load(doc: Doc): void {
    this.doc = doc;
    this.focus = null;
    this.render();
  }

  current(): Doc {
    return this.doc;
  }

  focused(): Place | null {
    return this.focus;
  }

  // --- rendering -----------------------------------------------------------

  /** Folded acts ("h:<n>") and scenes ("s:<n>"). Screen only: the text and print never change. */
  readonly collapsed = new Set<string>();
  private actKey = 0;
  private sceneKey = 0;

  toggleCollapse(key: string): void {
    if (this.collapsed.has(key)) this.collapsed.delete(key);
    else this.collapsed.add(key);
    this.applyCollapse();
    this.hooks.onCollapseChange?.();
  }

  /** Hide the blocks of folded acts and the content of folded scenes. */
  private applyCollapse(): void {
    const list = this.root.querySelector(":scope > .blk-list");
    if (!list) return;
    let hiding = false;
    let foldedTop = 0; // a folded sub-heading outside any scene (M6 part C3)
    for (const child of Array.from(list.children) as HTMLElement[]) {
      const key = child.dataset.collapseKey;
      if (child.dataset.act === "1") {
        hiding = !!key && this.collapsed.has(key);
        foldedTop = 0;
        child.classList.toggle("collapsed", hiding);
        child.classList.remove("collapse-hidden");
        continue;
      }
      const level = Number(child.dataset.subLevel || 0);
      if (foldedTop && (level ? level <= foldedTop : key?.startsWith("s:"))) foldedTop = 0;
      child.classList.toggle("collapse-hidden", (hiding || !!foldedTop) && child.classList.contains("blk"));
      if (key) child.classList.toggle("collapsed", this.collapsed.has(key));
      if (level && !hiding && !foldedTop && key && this.collapsed.has(key)) foldedTop = level;
    }
    // F4 (M6 part C): a folded sub-heading hides the blocks under it, up to
    // the next sub-heading of the same level or higher.
    for (const inner of Array.from(this.root.querySelectorAll<HTMLElement>(".el-scene > .el-children > .blk-list"))) {
      let foldedAt = 0;
      for (const child of Array.from(inner.children) as HTMLElement[]) {
        if (!child.classList.contains("blk")) continue;
        const level = Number(child.dataset.subLevel || 0);
        if (level && foldedAt && level <= foldedAt) foldedAt = 0;
        child.classList.toggle("collapse-hidden", !!foldedAt);
        if (level && !foldedAt) {
          const folded = this.collapsed.has(child.dataset.collapseKey ?? "");
          child.classList.toggle("collapsed", folded);
          if (folded) foldedAt = level;
        }
      }
    }
  }

  private foldButton(key: string): HTMLButtonElement {
    const button = el("button", "fold", { type: "button" });
    const update = () => {
      const folded = this.collapsed.has(key);
      button.textContent = folded ? "▸" : "▾"; // glyphs
      const label = t(folded ? "editor.expand" : "editor.collapse");
      button.title = label;
      button.setAttribute("aria-label", label);
      button.setAttribute("aria-expanded", String(!folded));
    };
    update();
    button.addEventListener("mousedown", (e) => e.preventDefault());
    button.addEventListener("click", (e) => {
      e.stopPropagation();
      this.toggleCollapse(key);
      update();
    });
    return button;
  }

  render(): void {
    this.sceneNumber = 0;
    this.actKey = 0;
    this.sceneKey = 0;
    this.subKey = 0;
    this.placeOf = new WeakMap();
    this.root.textContent = "";
    this.root.classList.toggle("read-only", this.readOnly);
    if (this.doc.blocks.length === 0) {
      const empty = el("p", "empty-note");
      empty.textContent = t("editor.empty");
      this.root.append(empty);
    }
    this.root.append(this.renderList(this.doc, [], null));
    this.applyCollapse();
    this.hooks.afterRender();
  }

  private renderList(list: Doc, chain: Block[], allow: string[] | null): HTMLElement {
    const box = el("div", "blk-list");
    list.blocks.forEach((block, index) => {
      box.append(this.renderBlock(block, { list, index, chain }, allow));
    });
    if (this.readOnly) return box;
    const add = el("div", "add-row");
    const kinds = this.kindsFor(list, chain, allow);
    const addButton = el("button", "add-btn", { type: "button" });
    const single = allow && allow.length === 1 ? this.defs.get(allow[0]) : undefined;
    addButton.textContent = "+ " + (single ? t("editor.addKind", { kind: single.name }) : t("editor.add"));
    addButton.addEventListener("click", () => {
      const place = { list, index: list.blocks.length - 1, chain };
      if (single) this.insert(single.id, place);
      else this.hooks.openInsertMenu(addButton, place, kinds);
    });
    add.append(addButton);
    // A list also receives a dragged block at its end; an empty container
    // shows a "Drop here" area while a block is dragged (M6 part C2).
    this.placeOf.set(add, { list, index: list.blocks.length, chain });
    if (list.blocks.length === 0 && chain.length > 0) {
      add.classList.add("empty-list");
      const here = el("div", "drop-here");
      here.textContent = t("editor.dropHere");
      add.prepend(here);
    }
    box.append(add);
    return box;
  }

  /** Block kinds (plus "paragraph", "heading", "table", "image") that may be
   * added to a list. */
  kindsFor(list: Doc, chain: Block[], allow: string[] | null): string[] {
    if (allow) return [...allow];
    const kinds = ["paragraph"];
    if (chain.length === 0) kinds.push("heading");
    // F4 (M6 part C): sub-headings stand directly inside a scene; from part
    // C3 also outside any scene (an info page before the first scene).
    const owner = chain[chain.length - 1];
    if (!owner || (owner.type === "element" && owner.kind === "scene")) kinds.push(...SUB_HEADINGS);
    kinds.push("table", "image");
    for (const def of this.defs.values()) {
      // A scene stands on its own; Boxes, Quotes and the layout sections
      // take any other block (M6 part C2).
      if (def.id === "scene" && chain.length > 0) continue;
      if (def.onlyInside && def.onlyInside.length) continue;
      kinds.push(def.id);
    }
    return kinds;
  }

  private allowOf(chain: Block[]): string[] | null {
    const owner = chain[chain.length - 1];
    return owner ? this.defs.get(owner.kind!)?.allow ?? null : null;
  }

  private renderBlock(block: Block, place: Place, allow: string[] | null): HTMLElement {
    const wrap = el("section", "blk blk-" + block.type);
    if (block.line) wrap.dataset.line = String(block.line);
    // Folding acts and scenes in the editor (screen only).
    if (place.chain.length === 0) {
      let key = "";
      if (block.type === "heading" && (block.level ?? 1) === 1) {
        key = "h:" + ++this.actKey;
        wrap.dataset.act = "1";
      } else if (block.type === "element" && block.kind === "scene") {
        key = "s:" + ++this.sceneKey;
      } else if (isSubHeading(block)) {
        // M6 part C3: a sub-heading outside any scene folds the same way.
        key = "u:" + ++this.subKey;
        wrap.dataset.subLevel = String(block.level);
      }
      if (key) {
        wrap.dataset.collapseKey = key;
        wrap.append(this.foldButton(key));
      }
    } else if (isSubHeading(block) && place.chain.length === 1 && place.chain[0].kind === "scene") {
      // F4 (M6 part C): a sub-heading folds to its heading, hiding what is
      // under it up to the next sub-heading of the same level or higher.
      const key = "u:" + ++this.subKey;
      wrap.dataset.collapseKey = key;
      wrap.dataset.subLevel = String(block.level);
      wrap.append(this.foldButton(key));
    }
    this.placeOf.set(wrap, place);
    wrap.addEventListener("focusin", (event) => {
      // Only the innermost block counts; outer blocks see the event bubble up.
      if ((event.target as HTMLElement).closest("section.blk") !== wrap) return;
      this.focus = place;
      this.hooks.onFocusBlock(block, place);
    });
    wrap.addEventListener("contextmenu", (event) => {
      if ((event.target as HTMLElement).closest("section.blk") !== wrap) return;
      event.preventDefault();
      this.focus = place;
      this.hooks.openContextMenu(event, place);
    });

    if (!this.readOnly) {
      // F4.13 (revised 12 November 2026, M6 part C2): the grip is a strip
      // down the whole left side of the block, touching it, with "::" in
      // its middle; the pointer is a hand anywhere on it. Dragging is done
      // by Scriptorum itself (drag.ts), never the system's drag-and-drop.
      const strip = el("div", "grip-strip", { role: "button", tabindex: "-1" });
      const dots = el("span", "grip");
      dots.textContent = "::"; // the grip handle, a glyph
      strip.append(dots);
      strip.title = t("editor.drag");
      strip.setAttribute("aria-label", t("editor.drag"));
      strip.addEventListener("pointerdown", (e) => this.beginDrag(e, place, wrap));
      wrap.append(strip);
      const controls = el("div", "blk-controls");
      controls.append(
        iconButton("editor.moveUp", "↑", () => this.move(place, -1)),
        iconButton("editor.moveDown", "↓", () => this.move(place, 1)),
        iconButton("editor.addAfter", "+", () => {
          this.hooks.openInsertMenu(controls, place, this.kindsFor(place.list, place.chain, allow));
        }),
        iconButton("editor.delete", "×", () => this.remove(place)),
      );
      // Issue #9 (M6-0.6.7, F4.13): while the pointer is on this menu it stays
      // on top and no other block's menu shows, even where the square hangs
      // beside the next block.
      controls.addEventListener("pointerenter", () => holdMenu(wrap));
      controls.addEventListener("pointerleave", () => releaseMenu());
      wrap.append(controls);
    }

    if (block.type === "heading") {
      wrap.append(this.headingBox(block, place));
    } else if (block.type === "paragraph") {
      wrap.append(this.richBox(block.text ?? "", (markup) => {
        block.text = markup;
        this.changed(block, place.chain);
      }, "para", t("editor.paragraph"), { place, splitPaste: true }));
    } else if (block.type === "locked") {
      const pre = el("pre", "locked-code");
      pre.textContent = block.raw ?? "";
      const note = el("div", "locked-note");
      note.textContent = t("editor.locked");
      pre.tabIndex = 0;
      wrap.append(note, pre);
    } else if (block.type === "table") {
      wrap.append(this.renderTable(block, place));
    } else if (block.type === "image") {
      wrap.append(this.renderImage(block, place));
    } else if (block.type === "element") {
      wrap.append(this.renderElement(block, place));
    }
    return wrap;
  }

  private headingBox(block: Block, place: Place): HTMLElement {
    const h = el("div", "heading-edit level-" + (block.level ?? 1), { contenteditable: this.readOnly ? "false" : "true", role: "textbox" });
    h.setAttribute("aria-label", t("editor.heading"));
    h.innerHTML = inlineToHtml(block.text ?? "");
    h.addEventListener("input", () => {
      block.text = htmlToInline(h).replace(/\n+/g, " ");
      this.changed(block, place.chain);
    });
    h.addEventListener("keydown", (e) => {
      if (e.key === "Enter") e.preventDefault();
      // F4 (M6 part C): Tab lowers a sub-heading one level, Shift+Tab raises it.
      if (e.key === "Tab" && isSubHeading(block) && !this.readOnly) {
        e.preventDefault();
        this.changeLevel(place, e.shiftKey ? -1 : 1);
      }
    });
    return h;
  }

  private richBox(
    markup: string,
    update: (markup: string) => void,
    className: string,
    label: string,
    options: { place?: Place; splitPaste?: boolean; onEnter?: () => void } = {},
  ): HTMLElement {
    const box = el("div", "rich " + className, { contenteditable: this.readOnly ? "false" : "true", role: "textbox" });
    box.setAttribute("aria-multiline", "true");
    box.setAttribute("aria-label", label);
    box.dataset.placeholder = t("editor.placeholder");
    box.innerHTML = inlineToHtml(markup);
    box.addEventListener("input", () => update(htmlToInline(box)));
    box.addEventListener("paste", (e) => {
      // Paste as plain text; formatting comes from the theme (3.2).
      e.preventDefault();
      const text = (e.clipboardData?.getData("text/plain") ?? "").replace(/\r\n?/g, "\n");
      if (options.splitPaste && options.place && this.pasteIntoParagraph(box, text, options.place)) return;
      document.execCommand("insertText", false, text);
    });
    if (options.onEnter) {
      box.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          options.onEnter!();
        }
      });
    }
    return box;
  }

  /** F4.5 and a T-USE finding: text pasted into a paragraph becomes one
   * paragraph per line at once; tab-separated lines become a table. */
  private pasteIntoParagraph(box: HTMLElement, text: string, place: Place): boolean {
    const lines = text.split("\n").map((l) => l.replace(/\s+$/, ""));
    while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
    const nonEmpty = lines.filter((l) => l.trim());
    if (nonEmpty.length >= 1 && nonEmpty.every((l) => l.includes("\t")) && place.list.blocks[place.index].type === "paragraph") {
      const cells = nonEmpty.map((l) => l.split("\t").map((c) => escapeCell(c.trim())));
      const columns = Math.max(...cells.map((r) => r.length));
      const pad = (r: string[]) => [...r, ...Array(columns - r.length).fill("")];
      const table: Block = { type: "table", columns, header: pad(cells[0]), rows: cells.slice(1).map(pad) };
      this.replaceOrAfter(box, place, [table]);
      return true;
    }
    if (nonEmpty.length <= 1) return false;
    const paragraphs: Block[] = nonEmpty.map((l) => ({ type: "paragraph", text: escapeCell(l.trim()) }));
    this.replaceOrAfter(box, place, paragraphs);
    return true;
  }

  private replaceOrAfter(box: HTMLElement, place: Place, blocks: Block[]): void {
    const current = place.list.blocks[place.index];
    const empty = !htmlToInline(box).trim();
    if (empty) {
      blocks[0].sep = current.sep;
      place.list.blocks.splice(place.index, 1, ...blocks);
    } else {
      place.list.blocks.splice(place.index + 1, 0, ...blocks);
      current.text = htmlToInline(box);
      delete current.raw;
    }
    this.commit(place.chain);
    this.focusBlock(blocks[blocks.length - 1]);
  }

  private fieldControl(block: Block, field: FieldDef, place: Place): HTMLElement | null {
    block.fields = block.fields ?? {};
    const fields = block.fields;
    const value = fields[field.name];
    const set = (v: string | number | undefined) => {
      if (v === undefined || v === "") delete fields[field.name];
      else fields[field.name] = v;
      this.changed(block, place.chain, true);
    };
    const disabled = this.readOnly;
    if ((block.locked_fields ?? []).includes(field.name)) {
      const pre = el("pre", "locked-code field-locked");
      pre.textContent = String(value ?? "");
      pre.title = t("editor.locked");
      return pre;
    }
    switch (field.kind) {
      case "id":
      case "seed":
        return null;
      case "codex": {
        // F3 (M6 part C4): a codex card is for everything else: people and
        // creatures have cards of their own (Insert ▸ Person, Creature).
        const own = block.kind === "card" && field.name === "entry" ? this.hooks.typesWithCard?.() ?? [] : [];
        const picker = this.codexPicker(field, value === undefined ? [] : [String(value)], false, (ids) => {
          set(ids[0]);
          // Picking a clue shows its text in place of the item's own (11.3).
          if (block.kind === "information" && field.name === "clue") this.render();
        }, own);
        return picker;
      }
      case "codex-list": {
        const picker = this.codexPicker(field, Array.isArray(value) ? (value as string[]) : [], true, (ids) => {
          if (!ids.length) delete fields[field.name];
          else (fields as any)[field.name] = ids;
          this.changed(block, place.chain, true);
        });
        // F3 (M6 part C4): Information written in a codex card is known by
        // that card's entry, so the person shows in its Known by.
        const owner = place.chain[place.chain.length - 1];
        const holder = owner?.kind === "card" ? String(owner.fields?.entry ?? "") : "";
        if (block.kind === "information" && field.name === "known-by" && holder) {
          const chip = el("span", "codex-chip codex-chip-fixed");
          chip.textContent = (this.hooks.codexEntries().find((e) => e.id === holder)?.title ?? holder) + " · " + t("codex.inCard");
          picker.prepend(chip);
        }
        return picker;
      }
      case "map-ref": {
        const row = el("div", "field-ref-row");
        const select = el("select", "field-input field-ref");
        select.disabled = disabled;
        const none = el("option");
        none.value = "";
        none.textContent = t("editor.chooseMap");
        select.append(none);
        for (const m of this.hooks.maps()) {
          const o = el("option");
          o.value = m.id;
          o.textContent = m.title;
          select.append(o);
        }
        select.value = value === undefined ? "" : String(value);
        select.addEventListener("change", () => set(select.value || undefined));
        row.append(select);
        if (value) {
          const open = el("button", "small-btn", { type: "button" });
          open.textContent = t("editor.openMap");
          open.addEventListener("click", () => this.hooks.openMap(String(value)));
          row.append(open);
        }
        return row;
      }
      case "bool": {
        const check = el("input", "field-check", { type: "checkbox" });
        // A true/false field that is on by default (a quote's Tint, 11.11)
        // shows its default when the text does not set it.
        const onByDefault = field.default === true;
        check.checked = value === undefined ? onByDefault : value === true || (value as unknown) === "true";
        check.disabled = disabled;
        check.addEventListener("change", () => {
          if (check.checked === onByDefault) delete fields[field.name];
          else (fields as any)[field.name] = check.checked;
          this.changed(block, place.chain, true);
        });
        return check;
      }
      case "rich":
        return this.richBox(String(value ?? ""), (markup) => set(markup), "field-rich", field.label);
      case "number": {
        const input = el("input", "field-input field-number", { type: "number" });
        if (field.min != null) input.min = String(field.min);
        if (field.max != null) input.max = String(field.max);
        input.value = value === undefined ? "" : String(value);
        input.disabled = disabled;
        input.addEventListener("input", () => {
          const n = input.value === "" ? undefined : Math.round(Number(input.value));
          set(n === undefined || Number.isNaN(n) ? undefined : n);
        });
        return input;
      }
      case "choice": {
        const select = el("select", "field-input field-choice");
        select.disabled = disabled;
        const none = el("option");
        none.value = "";
        none.textContent = t("editor.none");
        select.append(none);
        for (const option of field.options ?? []) {
          const o = el("option");
          o.value = option.id;
          // F6.7: a hand is listed by its kind, with the font's name beside it
          // and a short description; an added font by its font name.
          o.textContent = option.font && option.font !== option.label ? `${option.label} · ${option.font}` : option.label;
          if (option.note) o.title = option.note;
          select.append(o);
        }
        if (value !== undefined && ![...select.options].some((o) => o.value === String(value))) {
          const o = el("option");
          o.value = String(value);
          o.textContent = String(value);
          select.append(o);
        }
        select.value = value === undefined ? "" : String(value);
        select.addEventListener("change", () => set(select.value || undefined));
        return select;
      }
      case "image": {
        const row = el("div", "field-image");
        const name = el("span", "image-name");
        name.textContent = value ? String(value).split("/").pop()! : t("editor.noImage");
        const choose = el("button", "small-btn", { type: "button" });
        choose.textContent = t("editor.chooseImage");
        choose.disabled = disabled;
        choose.addEventListener("click", async () => {
          const path = await this.hooks.pickImage(field.accept);
          if (path) {
            set(path);
            name.textContent = path.split("/").pop()!;
          }
        });
        row.append(choose, name);
        if (value && !disabled) {
          const clear = iconButton("editor.removeImage", "×", () => {
            set(undefined);
            this.render();
          });
          row.append(clear);
        }
        return row;
      }
      case "element-ref": {
        // 9.4 element reference: pick a scene; the scene gets an ID the
        // first time something points to it.
        const select = el("select", "field-input field-ref");
        select.disabled = disabled;
        const none = el("option");
        none.value = "";
        none.textContent = t("editor.none");
        select.append(none);
        const scenes = this.scenes();
        scenes.forEach((s, i) => {
          const o = el("option");
          o.value = String(i);
          o.textContent = t("editor.sceneOption", { number: i + 1, title: String(s.fields?.title ?? "") });
          if (s.fields?.id && s.fields.id === value) o.selected = true;
          select.append(o);
        });
        select.addEventListener("change", () => {
          if (select.value === "") {
            set(undefined);
            return;
          }
          const target = scenes[Number(select.value)];
          target.fields = target.fields ?? {};
          if (!target.fields.id) {
            target.fields.id = newSceneId();
            delete target.raw;
            delete target.head_raw;
            for (const outer of this.chainOf(target)) delete outer.raw;
          }
          set(String(target.fields.id));
        });
        return select;
      }
      default: {
        if (field.multiline) {
          // F8 Plain game system: free stat lines, one per line ("Strength 3").
          const area = el("textarea", "field-input", { rows: "4" });
          area.value = value === undefined ? "" : String(value);
          area.disabled = disabled;
          area.addEventListener("input", () => set(area.value));
          return area;
        }
        const input = el("input", "field-input", { type: "text" });
        input.value = value === undefined ? "" : String(value);
        if (field.required) input.required = true;
        input.disabled = disabled;
        input.addEventListener("input", () => {
          set(input.value);
          if (field.name === "title") this.root.dispatchEvent(new CustomEvent("outline-changed"));
        });
        return input;
      }
    }
  }

  /** F3.5: pick one codex entry, or several, of the types the field allows. */
  private codexPicker(field: FieldDef, ids: string[], many: boolean, set: (ids: string[]) => void, notTypes: string[] = []): HTMLElement {
    const row = el("div", "codex-picker");
    const entries = this.hooks.codexEntries().filter((e) => (!field.types || field.types.includes(e.type)) && !notTypes.includes(e.type));
    const titleOf = (id: string) => this.hooks.codexEntries().find((e) => e.id === id)?.title ?? t("editor.missingEntry", { id });
    for (const id of ids) {
      const chip = el("span", "codex-chip");
      const open = el("button", "codex-chip-name", { type: "button" });
      open.textContent = titleOf(id);
      open.title = t("editor.openEntry");
      open.addEventListener("click", () => this.hooks.openEntry(id));
      chip.append(open);
      if (!this.readOnly) {
        chip.append(iconButton("editor.removeEntry", "×", () => {
          set(ids.filter((x) => x !== id));
          this.render();
        }));
      }
      row.append(chip);
    }
    if (!this.readOnly && (many || ids.length === 0)) {
      // Type or paste a name: an existing entry is linked, a new name becomes
      // a new entry (F3.5, T-USE-01: text pasted straight into a field).
      const input = el("input", "field-input field-codex", { type: "text" });
      input.setAttribute("aria-label", field.label);
      input.placeholder = t(many && ids.length ? "editor.addEntry" : "editor.chooseEntry");
      const listId = "codex-list-" + Math.random().toString(36).slice(2, 8);
      const list = el("datalist");
      list.id = listId;
      for (const e of entries.filter((e) => !ids.includes(e.id))) {
        const o = el("option");
        o.value = e.title;
        list.append(o);
      }
      input.setAttribute("list", listId);
      const types = field.types ?? [];
      const take = async () => {
        const name = input.value.trim();
        if (!name) return;
        input.value = "";
        const found = entries.find((e) => e.title.toLowerCase() === name.toLowerCase());
        const id = found ? found.id : await this.hooks.createEntry(types.length === 1 ? types[0] : "", name);
        if (id && !ids.includes(id)) {
          set(many ? [...ids, id] : [id]);
          this.render();
        }
      };
      input.addEventListener("change", () => take());
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          take();
        }
      });
      input.addEventListener("paste", (e) => {
        const text = e.clipboardData?.getData("text/plain");
        if (!text) return;
        e.preventDefault();
        input.value = text.trim();
        take();
      });
      row.append(input, list);
    }
    return row;
  }

  /** Replace one block (F3.7: a loose person card becomes a codex card). */
  replaceBlock(place: Place, block: Block): void {
    block.sep = place.list.blocks[place.index].sep;
    place.list.blocks.splice(place.index, 1, block);
    this.commit(place.chain);
  }

  /** Every scene in the chapter, in order. */
  private scenes(): Block[] {
    const found: Block[] = [];
    const walk = (doc: Doc) => doc.blocks.forEach((b) => {
      if (b.type === "element" && b.kind === "scene") found.push(b);
      if (isDoc(b.body)) walk(b.body);
    });
    walk(this.doc);
    return found;
  }

  private chainOf(target: Block): Block[] {
    const search = (doc: Doc, chain: Block[]): Block[] | null => {
      for (const b of doc.blocks) {
        if (b === target) return chain;
        if (isDoc(b.body)) {
          const found = search(b.body, [...chain, b]);
          if (found) return found;
        }
      }
      return null;
    };
    return search(this.doc, []) ?? [];
  }

  renderElement(block: Block, place: Place): HTMLElement {
    const def = this.defs.get(block.kind!);
    const box = el("div", "el el-" + (def?.editor ?? "frame") + " el-" + block.kind);
    if (!def) return box;
    const variant = block.variant ?? def.defaultVariant;
    if (variant) box.classList.add("variant-" + variant);

    const head = el("div", "el-head");
    const name = el("span", "el-name");
    name.textContent = def.name;
    if (def.numbered) {
      this.sceneNumber += 1;
      name.textContent = def.name + " " + this.sceneNumber;
    }
    if (def.editor === "row") name.textContent = "☐"; // a countdown step's tick box, a glyph
    head.append(name);
    if (def.fields.some((f) => f.name === "only-handout")) {
      // F6 (M6 part C3): a tag shows that the handout prints only as a handout.
      const tag = el("span", "el-tag only-handout-tag");
      tag.textContent = t("editor.onlyHandoutTag");
      const update = () => { tag.hidden = block.fields?.["only-handout"] !== true; };
      update();
      box.addEventListener("change", () => queueMicrotask(update));
      head.append(tag);
    }

    if (def.variants.length) {
      const select = el("select", "variant-select");
      select.setAttribute("aria-label", t("editor.variant"));
      select.disabled = this.readOnly;
      for (const v of def.variants) {
        const option = el("option");
        option.value = v.id;
        option.textContent = v.label;
        select.append(option);
      }
      select.value = variant ?? def.variants[0].id;
      select.addEventListener("change", () => {
        block.variant = select.value;
        box.className = box.className.replace(/variant-\S+/, "variant-" + select.value);
        this.changed(block, place.chain, true);
      });
      head.append(select);
    }

    if (def.newLook && !this.readOnly) {
      // F6.5: another look for this handout; the text is not changed.
      const button = el("button", "small-btn new-look", { type: "button" });
      button.textContent = t("editor.newLook");
      button.title = t("editor.newLookHint");
      button.addEventListener("mousedown", (e) => e.preventDefault());
      button.addEventListener("click", () => {
        block.fields = block.fields ?? {};
        block.fields.look = Number(block.fields.look ?? 0) + 1;
        this.changed(block, place.chain, true);
      });
      head.append(button);
    }

    if (def.pageStartSwitchable) {
      const label = el("label", "newpage");
      const check = el("input", "", { type: "checkbox" });
      check.checked = block.new_page !== false;
      check.disabled = this.readOnly;
      check.addEventListener("change", () => {
        block.new_page = check.checked ? null : false;
        this.changed(block, place.chain, true);
      });
      const span = el("span");
      span.textContent = t("editor.newPage");
      label.append(check, span);
      head.append(label);
    }
    box.append(head);

    // F3.12: an M2 text field shows only while it still holds text.
    const visible = def.fields.filter((f) => f.kind !== "id" && f.kind !== "seed" &&
      !(f.legacy && (block.fields?.[f.name] === undefined || block.fields?.[f.name] === "")));
    if (visible.length) {
      const form = el("div", "el-fields");
      const stats = el("div", "el-stats");
      const folded = el("div", "el-folded");
      for (const field of visible) {
        const filled = block.fields?.[field.name] !== undefined && block.fields?.[field.name] !== "";
        const key = block.kind + ":" + field.name + ":" + (block.line ?? "");
        if (field.section && !filled && !this.openSections.has(key)) {
          // 11.5: empty sections are folded away until the author opens them.
          if (this.readOnly) continue;
          const open = el("button", "small-btn section-open", { type: "button" });
          open.textContent = "+ " + field.label;
          open.addEventListener("click", () => {
            this.openSections.add(key);
            this.render();
            this.focusField(block, field.name);
          });
          folded.append(open);
          continue;
        }
        const control = this.fieldControl(block, field, place);
        if (!control) continue;
        const row = el("label", "field field-" + field.name + (field.group ? " field-group-" + field.group : ""));
        const caption = el("span", "field-label");
        caption.textContent = field.label + (field.required ? " *" : "");
        row.append(caption, control);
        if (field.group === "stats") {
          // 11.5: the game system's stats in one row.
          if (!stats.parentElement) form.append(stats);
          stats.append(row);
        } else {
          form.append(row);
        }
      }
      box.append(form);
      if (folded.childElementCount) box.append(folded);
    }

    const chain = [...place.chain, block];
    const clue = block.kind === "information" ? String(block.fields?.clue ?? "") : "";
    const clueEntry = clue ? this.hooks.codexEntries().find((e) => e.id === clue) : undefined;
    if (clue && clueEntry?.text) {
      // F3 (M6 part C4): the text is written once, in the clue's entry.
      const shown = el("div", "clue-text");
      const caption = el("div", "children-caption");
      caption.textContent = t("codex.clueText");
      const text = el("div", "rich el-body clue-body", { role: "note" });
      text.innerHTML = inlineToHtml(clueEntry.text);
      const edit = el("button", "small-btn", { type: "button" });
      edit.textContent = t("codex.editClue");
      edit.addEventListener("click", () => this.hooks.openEntry(clue));
      shown.append(caption, text, edit);
      box.append(shown);
    } else if (def.body === "rich" || def.body === "plain") {
      if (clue) {
        const note = el("div", "children-caption clue-empty");
        note.textContent = t("codex.clueEmpty");
        box.append(note);
      }
      const text = typeof block.body === "string" ? block.body : "";
      const onEnter = def.enterAddsNext ? () => this.insert(def.id, place) : undefined;
      const body = this.richBox(text, (markup) => {
        block.body = markup;
        this.changed(block, place.chain);
      }, "el-body", def.name, { onEnter });
      if (clue && clueEntry && !this.readOnly) {
        // Issue #7 (M6-0.6.9): leaving the item saves its text as the clue's
        // description, so every place that shows the clue prints it. The
        // item keeps its own text, so undoing the description loses nothing.
        body.addEventListener("focusout", () => {
          const markup = typeof block.body === "string" ? block.body.trim() : "";
          const now = this.hooks.codexEntries().find((e) => e.id === clue);
          if (markup && now && !now.text) this.hooks.adoptClueText?.(clue, markup);
        });
      }
      box.append(body);
    } else if (def.body === "blocks") {
      if (!isDoc(block.body)) block.body = { blocks: [], trail: "\n" };
      const inner = el("div", "el-children");
      if (def.allow && def.allow.length === 1 && def.allow[0] === "information") {
        const caption = el("div", "children-caption");
        caption.textContent = t("editor.whatTheyKnow");
        inner.append(caption);
      }
      inner.append(this.renderList(block.body, chain, def.allow));
      // M6 part C3: where the scene ends, a thin labelled line.
      if (block.kind === "scene") {
        const end = el("div", "scene-end-line");
        end.textContent = t("editor.sceneEndLine");
        inner.append(end);
      }
      box.append(inner);
    }
    const kept = (block as Block & { extra?: Record<string, string> }).extra;
    if (block.kind === "card" && kept && Object.keys(kept).length) {
      // F3 (M6 part C4): fields the codex type lacks stay on the card as written.
      const list = el("div", "kept-fields");
      const caption = el("div", "children-caption");
      caption.textContent = t("codex.keptOnCard");
      list.append(caption);
      for (const [name, raw] of Object.entries(kept)) {
        const line = el("div", "kept-field");
        line.textContent = name + ": " + raw;
        list.append(line);
      }
      box.append(list);
    }
    return box;
  }

  /** The path of indexes to a block, as the core finds it (F3, M6 part C4). */
  pathOf(place: Place): number[] {
    const path: number[] = [];
    let list = this.doc;
    for (const outer of place.chain) {
      path.push(list.blocks.indexOf(outer));
      list = outer.body as Doc;
    }
    path.push(place.index);
    return path;
  }

  // --- tables (F4.5) and images (F4.6) ---------------------------------------

  private renderTable(block: Block, place: Place): HTMLElement {
    const box = el("div", "tbl-edit");
    const table = el("table", "tbl");
    const header = block.header ?? [];
    const rows = block.rows ?? [];
    const all = [header, ...rows];
    const cellAt = (r: number, c: number) => table.querySelector<HTMLElement>(`[data-r="${r}"][data-c="${c}"]`);
    all.forEach((row, r) => {
      const tr = el("tr");
      row.forEach((value, c) => {
        const td = el(r === 0 ? "th" : "td");
        const cell = el("div", "rich cell", { contenteditable: this.readOnly ? "false" : "true", role: "textbox" });
        cell.dataset.r = String(r);
        cell.dataset.c = String(c);
        cell.setAttribute("aria-label", t("editor.cell", { row: r + 1, column: c + 1 }));
        cell.innerHTML = inlineToHtml(value);
        cell.addEventListener("input", () => {
          const markup = htmlToInline(cell).replace(/\n+/g, " ");
          if (r === 0) header[c] = markup;
          else rows[r - 1][c] = markup;
          this.changed(block, place.chain);
        });
        cell.addEventListener("keydown", (e) => {
          if (e.key !== "Tab") return;
          // F4.5.1: Tab moves between cells; Tab in the last cell adds a row.
          e.preventDefault();
          const columns = block.columns ?? 1;
          let index = r * columns + c + (e.shiftKey ? -1 : 1);
          if (index >= all.length * columns) {
            rows.push(Array(columns).fill(""));
            this.commit(place.chain);
            this.focusCell(block, all.length, 0);
            return;
          }
          index = Math.max(0, index);
          cellAt(Math.floor(index / columns), index % columns)?.focus();
        });
        cell.addEventListener("paste", (e) => {
          // F4.5.2: tab-separated text from a spreadsheet fills the cells.
          const text = (e.clipboardData?.getData("text/plain") ?? "").replace(/\r\n?/g, "\n").replace(/\n+$/, "");
          if (!text.includes("\t") && !text.includes("\n")) return;
          e.preventDefault();
          const grid = text.split("\n").map((l) => l.split("\t").map((v) => escapeCell(v.trim())));
          const columns = Math.max(block.columns ?? 1, c + Math.max(...grid.map((g) => g.length)));
          const widen = (row: string[]) => { while (row.length < columns) row.push(""); };
          block.columns = columns;
          widen(header);
          rows.forEach(widen);
          grid.forEach((values, i) => {
            const target = r + i;
            while (target > rows.length) rows.push(Array(columns).fill(""));
            const row = target === 0 ? header : rows[target - 1];
            values.forEach((v, j) => (row[c + j] = v));
          });
          this.commit(place.chain);
        });
        td.append(cell);
        tr.append(td);
      });
      table.append(tr);
    });
    box.append(table);
    if (!this.readOnly) {
      const tools = el("div", "tbl-tools");
      const button = (key: string, action: () => void) => {
        const b = el("button", "small-btn", { type: "button" });
        b.textContent = t(key);
        b.addEventListener("click", () => {
          action();
          this.commit(place.chain);
        });
        tools.append(b);
      };
      const columns = () => block.columns ?? 1;
      button("editor.addRow", () => rows.push(Array(columns()).fill("")));
      button("editor.addColumn", () => {
        block.columns = columns() + 1;
        header.push("");
        rows.forEach((row) => row.push(""));
      });
      button("editor.removeRow", () => { if (rows.length) rows.pop(); });
      button("editor.removeColumn", () => {
        if (columns() <= 1) return;
        block.columns = columns() - 1;
        header.pop();
        rows.forEach((row) => row.pop());
      });
      box.append(tools);
    }
    return box;
  }

  private focusCell(block: Block, r: number, c: number): void {
    const sections = this.blockSections();
    const index = this.order().indexOf(block);
    sections[index]?.querySelector<HTMLElement>(`[data-r="${r}"][data-c="${c}"]`)?.focus();
  }

  private renderImage(block: Block, place: Place): HTMLElement {
    const figure = el("figure", "img-block");
    const img = el("img", "img-preview");
    img.alt = block.alt || block.path || "";
    this.hooks.imageUrl(block.path ?? "").then((url) => { if (url) img.src = url; });
    const caption = el("figcaption");
    caption.textContent = (block.path ?? "").split("/").pop() ?? "";
    // F17.3 (M5): the description screen readers read in place of the picture.
    const label = el("label", "field img-description");
    const span = el("span", "field-label");
    span.textContent = t("editor.imageDescription");
    const input = el("input", "field-input", { type: "text" });
    input.value = block.alt ?? "";
    input.placeholder = t("editor.imageDescriptionHint");
    input.disabled = this.readOnly;
    input.addEventListener("input", () => {
      if (input.value.trim()) block.alt = input.value;
      else delete block.alt;
      this.changed(block, place.chain);
    });
    label.append(span, input);
    figure.append(img, caption, label);
    return figure;
  }

  /** F4.6: an image dragged into the editor is copied into the adventure. */
  async dropImage(file: File, place: Place | null): Promise<void> {
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(file);
    });
    const path = await this.hooks.storeImage(file.name, dataUrl);
    if (path) this.insertBlock({ type: "image", path }, place);
  }

  // --- changes ----------------------------------------------------------------

  /** Forget the stored text of a changed block and of every block around it. */
  private changed(block: Block, chain: Block[], head = false): void {
    delete block.raw;
    if (head) delete block.head_raw;
    for (const outer of chain) delete outer.raw;
    this.hooks.onChange(this.doc);
  }

  /** A structural change: redraw and send now, as one undo step. */
  private commit(chain: Block[]): void {
    for (const outer of chain) delete outer.raw;
    this.hooks.onCommit(this.doc);
    this.render();
  }

  newBlock(kind: string): Block {
    if (kind === "paragraph") return { type: "paragraph", text: "" };
    if (kind === "heading") return { type: "heading", level: 1, text: "" };
    if (SUB_HEADINGS.includes(kind)) return { type: "heading", level: Number(kind.slice(-1)), text: "" };
    if (kind === "table") return { type: "table", columns: 2, header: ["", ""], rows: [["", ""]] };
    const def = this.defs.get(kind)!;
    const block: Block = { type: "element", kind, fields: {}, variant: def.defaultVariant, new_page: null };
    for (const f of def.fields) {
      if (f.default !== undefined && f.kind !== "choice") block.fields![f.name] = f.default;
    }
    if (def.body === "blocks") {
      block.body = { blocks: [], trail: "\n" };
      if (def.allow && def.allow.length === 1 && this.defs.get(def.allow[0])?.onlyInside) {
        (block.body as Doc).blocks.push(this.newBlock(def.allow[0]));
      } else if (def.bodyRequired) {
        // A Box or a Quote (11.10, 11.11) starts with a paragraph to type in.
        (block.body as Doc).blocks.push(this.newBlock("paragraph"));
      }
    } else if (def.body === "rich" || def.body === "plain") block.body = "";
    else block.body = null;
    return block;
  }

  /** Where a new block of this kind may go, starting from a place. Inserting
   * from a scene's header appends it at the end of the scene (T-USE finding). */
  private targetFor(kind: string, place: Place | null): Place {
    let target: Place = place ?? { list: this.doc, index: this.doc.blocks.length - 1, chain: [] };
    for (;;) {
      const allow = this.allowOf(target.chain);
      const allowed = this.kindsFor(target.list, target.chain, allow).includes(kind);
      if (allowed || target.chain.length === 0) break;
      const owner = target.chain[target.chain.length - 1];
      const outerChain = target.chain.slice(0, -1);
      const outerList = this.listOf(outerChain);
      target = { list: outerList, index: outerList.blocks.indexOf(owner), chain: outerChain };
    }
    const focused = target.list.blocks[target.index];
    if (focused && focused.type === "element" && isDoc(focused.body) && kind !== focused.kind) {
      const inner = { list: focused.body, index: focused.body.blocks.length - 1, chain: [...target.chain, focused] };
      if (this.kindsFor(inner.list, inner.chain, this.allowOf(inner.chain)).includes(kind)) target = inner;
    }
    return target;
  }

  insert(kind: string, place: Place | null = this.focus, variant?: string): void {
    const block = this.newBlock(kind);
    // F9: the Boxes group inserts Information as a secret, public information or a hint.
    if (variant && block.type === "element") block.variant = variant;
    this.insertBlock(block, place);
  }

  insertBlock(block: Block, place: Place | null = this.focus): void {
    const target = this.targetFor(kindOf(block), place);
    // Only where it is allowed: a sub-heading only inside a scene (M6 part C).
    const reason = this.reasonAgainst(block, { list: target.list, index: target.index + 1, chain: target.chain });
    if (reason) {
      this.hooks.flash(reason);
      return;
    }
    target.list.blocks.splice(target.index + 1, 0, block);
    if (isSubHeading(block)) {
      // The level follows the position: it never skips a level (F4).
      const at = target.list.blocks.indexOf(block);
      block.level = Math.max(3, Math.min(levelOf(block), this.levelAbove(target.list, at) + 1));
    }
    const next = target.list.blocks[target.index + 2];
    if (next) delete next.sep; // let the core choose clean spacing
    this.commit(target.chain);
    this.focusBlock(block);
  }

  /** F4 (M6 part C3): End of scene. The scene's text already ends at its
   * closing bracket, so no marker is written: the blocks after the one
   * holding the cursor leave the scene and stand just after it, outside any
   * scene. With nothing after the cursor, an empty paragraph is placed just
   * after the scene to write in. One undo step. */
  endScene(place: Place | null = this.focus): boolean {
    if (!place) {
      this.hooks.flash(t("editor.reason.notInScene"));
      return false;
    }
    const sceneAt = place.chain.findIndex((b) => b.type === "element" && b.kind === "scene");
    const scene = sceneAt >= 0 ? place.chain[sceneAt] : (place.chain.length === 0 && place.list.blocks[place.index]?.kind === "scene" ? null : undefined);
    if (!scene) {
      this.hooks.flash(t("editor.reason.notInScene"));
      return false;
    }
    const body = scene.body as Doc;
    // The block directly inside the scene that holds the cursor.
    const holder = sceneAt + 1 < place.chain.length ? place.chain[sceneAt + 1] : place.list.blocks[place.index];
    const at = body.blocks.indexOf(holder);
    const outer = this.listOf(place.chain.slice(0, sceneAt));
    const sceneIndex = outer.blocks.indexOf(scene);
    const moved = at >= 0 ? body.blocks.splice(at + 1) : [];
    let focus: Block;
    if (moved.length) {
      for (const b of moved) b.line = undefined;
      delete moved[0].sep;
      focus = moved[0];
    } else {
      focus = this.newBlock("paragraph");
      moved.push(focus);
    }
    outer.blocks.splice(sceneIndex + 1, 0, ...moved);
    const next = outer.blocks[sceneIndex + 1 + moved.length];
    if (next) delete next.sep;
    this.commit(place.chain.slice(0, sceneAt + 1));
    this.focusBlock(focus);
    return true;
  }

  /** Insert an inline element (11.7) at the caret of the focused text. */
  insertInline(source: string): boolean {
    const selection = getSelection();
    const node = selection?.anchorNode;
    const box = (node instanceof HTMLElement ? node : node?.parentElement)?.closest<HTMLElement>(".rich");
    if (!box || box.getAttribute("contenteditable") !== "true" || !this.root.contains(box)) return false;
    document.execCommand("insertHTML", false, chipHtml(source) + "\u200b");
    box.dispatchEvent(new Event("input", { bubbles: true }));
    return true;
  }

  private listOf(chain: Block[]): Doc {
    let list = this.doc;
    for (const block of chain) list = block.body as Doc;
    return list;
  }

  remove(place: Place): void {
    const [block] = place.list.blocks.splice(place.index, 1);
    const next = place.list.blocks[place.index];
    if (next && place.index === 0) delete next.sep;
    if (block) this.commit(place.chain);
  }

  // --- moving blocks (F4.13; sub-headings and containers in M6 part C2) -----------

  /** The blocks that move together, [start, end): a sub-heading carries
   * everything under it up to the next sub-heading of the same level or
   * higher (F4); any other block moves alone. */
  unitOf(list: Doc, index: number): [number, number] {
    const block = list.blocks[index];
    if (!isSubHeading(block)) return [index, index + 1];
    const level = levelOf(block);
    let end = index + 1;
    while (end < list.blocks.length) {
      const next = list.blocks[end];
      if (next.type === "heading" && levelOf(next) <= level) break;
      // At the top level a scene ends a sub-heading's section (M6 part C3).
      if (next.type === "element" && next.kind === "scene") break;
      end += 1;
    }
    return [index, end];
  }

  /** The level of the nearest sub-heading above an index in a list, or 2 (a
   * scene's own heading) when there is none. */
  private levelAbove(list: Doc, index: number): number {
    for (let i = index - 1; i >= 0; i--) {
      const b = list.blocks[i];
      if (b.type === "heading") return Math.max(2, levelOf(b));
      if (b.type === "element" && b.kind === "scene") return 2;
    }
    return 2;
  }

  /** The level follows the position (F4): a moved sub-heading is never more
   * than one level deeper than the sub-heading above it, and directly under
   * a scene it is a Sub-heading 1. One that would skip a level rises by
   * itself, and the sub-headings under it rise with it. */
  private fitLevels(list: Doc, start: number, end: number): void {
    const first = list.blocks[start];
    if (!isSubHeading(first)) return;
    const wanted = Math.max(3, Math.min(levelOf(first), this.levelAbove(list, start) + 1));
    const delta = wanted - levelOf(first);
    if (!delta) return;
    for (let i = start; i < end; i++) {
      const b = list.blocks[i];
      if (isSubHeading(b)) {
        b.level = Math.max(3, Math.min(5, levelOf(b) + delta));
        delete b.raw;
      }
    }
  }

  /** ↑ and ↓ (and Alt+↑ / Alt+↓): one step, one undo step (F4.13). A
   * sub-heading steps past the sub-heading of the same level above or below
   * it, with everything under both. At the top or bottom of a container the
   * block moves out of it, just before or after it (M6 part C2). */
  move(place: Place, step: number): void {
    const list = place.list;
    const blocks = list.blocks;
    const [start, end] = this.unitOf(list, place.index);
    const block = blocks[start];
    if ((step < 0 && start === 0) || (step > 0 && end >= blocks.length)) {
      this.moveOut(place, step < 0 ? "before" : "after");
      return;
    }
    let to: number; // where the unit goes, counted before it is taken out
    if (!isSubHeading(block)) {
      to = step < 0 ? start - 1 : end + 1;
    } else if (step < 0) {
      const level = levelOf(block);
      let k = start - 1;
      while (k >= 0 && !(blocks[k].type === "heading" && levelOf(blocks[k]) <= level)) k -= 1;
      // A sibling of the same level: step past its whole section. Otherwise
      // step past the one block above (out of a parent heading directly above).
      to = k >= 0 && (levelOf(blocks[k]) === level || k === start - 1) ? k : start - 1;
    } else {
      const next = blocks[end];
      to = levelOf(next) === levelOf(block) ? this.unitOf(list, end)[1] : end + 1;
    }
    this.moveUnit(place, { list, index: to, chain: place.chain });
  }

  /** Move a block (with its section) out of its container, just before or
   * after it, where that is allowed. */
  moveOut(place: Place, side: "before" | "after"): boolean {
    const owner = place.chain[place.chain.length - 1];
    if (!owner) return false;
    const outerChain = place.chain.slice(0, -1);
    const outer = this.listOf(outerChain);
    const at = outer.blocks.indexOf(owner);
    return this.moveUnit(place, { list: outer, index: side === "before" ? at : at + 1, chain: outerChain }, true);
  }

  /** Alt+→: into the container just above, at its end, where allowed. */
  moveIn(place: Place): boolean {
    const above = place.list.blocks[place.index - 1];
    if (!above || above.type !== "element" || !isDoc(above.body)) {
      this.hooks.flash(t("editor.reason.noContainerAbove"));
      return false;
    }
    return this.moveUnit(place, { list: above.body, index: above.body.blocks.length, chain: [...place.chain, above] }, true);
  }

  /** The person a card stands for: a codex Person, or a loose person card. */
  private personOf(owner: Block | undefined): { entry: string | null; name: string } | null {
    if (!owner || owner.type !== "element") return null;
    if (owner.kind === "person") return { entry: null, name: String(owner.fields?.name ?? "") };
    if (owner.kind === "card") {
      const id = String(owner.fields?.entry ?? "");
      const entry = this.hooks.codexEntries().find((e) => e.id === id);
      return entry && entry.type === "person" ? { entry: id, name: entry.title } : null;
    }
    return null;
  }

  /** Why a block may not go to a place, or null when it may (M6 part C2). */
  reasonAgainst(block: Block, target: Place): string | null {
    if (target.chain.includes(block)) return t("editor.reason.itself");
    const allow = this.allowOf(target.chain);
    const kind = kindOf(block);
    if (this.kindsFor(target.list, target.chain, allow).includes(kind) || (block.type === "locked" && !allow)) return null;
    const owner = target.chain[target.chain.length - 1];
    if (owner && allow) {
      if (owner.kind === "person" || owner.kind === "card") return t("editor.reason.personCard");
      if (owner.kind === "countdown") return t("editor.reason.countdown");
      return t("editor.reason.only", { container: this.defs.get(owner.kind!)?.name ?? "", kinds: allow.map((k) => this.defs.get(k)?.name ?? k).join(", ") });
    }
    if (kind === "scene") return t("editor.reason.scene");
    if (SUB_HEADINGS.includes(kind)) return t("editor.reason.subHeading");
    if (kind === "heading") return t("editor.reason.actHeading");
    return t("editor.reason.generic", { kind: this.defs.get(kind)?.name ?? kind });
  }

  /** May this block be placed in that list? (F4.13: only where allowed) */
  canPlace(block: Block, target: Place): boolean {
    return this.reasonAgainst(block, target) === null;
  }

  /** Move a block to another place (drag and drop, the outline). */
  moveTo(from: Place, to: Place): boolean {
    return this.moveUnit(from, to);
  }

  /** Move a block, with its section if it is a sub-heading, to a place in a
   * list (an index counted before the block is taken out). One undo step;
   * the moved blocks' text and fields are untouched, except who knows an
   * Information moved into or out of a person card (F3.6). */
  moveUnit(from: Place, to: Place, explain = false): boolean {
    const [start, end] = this.unitOf(from.list, from.index);
    const unit = from.list.blocks.slice(start, end);
    if (!unit.length) return false;
    const inside = unit.some((b) => to.chain.includes(b));
    const reason = inside ? t("editor.reason.itself") : this.reasonAgainst(unit[0], to);
    if (reason) {
      if (explain) this.hooks.flash(reason);
      return false;
    }
    let index = to.index;
    if (from.list === to.list) {
      if (index >= start && index <= end) return false; // it is already there
      if (index > end) index -= unit.length;
    }
    // Information leaving or entering a person card keeps who knows it.
    const fromPerson = this.personOf(from.chain[from.chain.length - 1]);
    const toPerson = this.personOf(to.chain[to.chain.length - 1]);
    let note = "";
    if (unit.length === 1 && unit[0].type === "element" && unit[0].kind === "information" && from.list !== to.list) {
      const info = unit[0];
      const known: string[] = Array.isArray(info.fields?.["known-by"]) ? [...(info.fields!["known-by"] as string[])] : [];
      let changed = false;
      if (fromPerson && !toPerson) {
        if (fromPerson.entry) {
          if (!known.includes(fromPerson.entry)) {
            known.push(fromPerson.entry);
            changed = true;
          }
        } else {
          note = t("editor.noLongerKnows", { person: fromPerson.name || t("editor.thePerson") });
        }
      }
      if (toPerson?.entry && known.includes(toPerson.entry)) {
        known.splice(known.indexOf(toPerson.entry), 1);
        changed = true;
      }
      if (changed) {
        info.fields = info.fields ?? {};
        if (known.length) info.fields["known-by"] = known;
        else delete info.fields["known-by"];
        delete info.head_raw;
        delete info.raw;
      }
    }
    from.list.blocks.splice(start, unit.length);
    to.list.blocks.splice(index, 0, ...unit);
    delete unit[0].sep;
    const next = to.list.blocks[index + unit.length];
    if (next) delete next.sep;
    const after = from.list.blocks[start];
    if (after) delete after.sep;
    this.fitLevels(to.list, index, index + unit.length);
    for (const outer of from.chain) delete outer.raw;
    this.commit(to.chain);
    this.focus = { list: to.list, index, chain: to.chain };
    this.focusBlock(unit[0]);
    if (note) this.hooks.flash(note);
    return true;
  }

  // --- raising and lowering sub-headings (F4, M6 part C) -------------------------------

  /** Raise (-1) or lower (+1) a sub-heading one level, with the sub-headings
   * under it, in one undo step. Lower only where it would not skip a level. */
  changeLevel(place: Place, delta: number): boolean {
    if (!(delta < 0 ? this.canRaise(place) : this.canLower(place))) {
      if (delta > 0) this.hooks.flash(t("editor.reason.lower"));
      return false;
    }
    const [start, end] = this.unitOf(place.list, place.index);
    for (let i = start; i < end; i++) {
      const b = place.list.blocks[i];
      if (isSubHeading(b)) {
        b.level = levelOf(b) + delta;
        delete b.raw;
      }
    }
    const block = place.list.blocks[start];
    this.commit(place.chain);
    this.focusBlock(block);
    return true;
  }

  canRaise(place: Place): boolean {
    const block = place.list.blocks[place.index];
    return isSubHeading(block) && levelOf(block) > 3;
  }

  canLower(place: Place): boolean {
    const block = place.list.blocks[place.index];
    if (!isSubHeading(block) || levelOf(block) >= 5) return false;
    if (levelOf(block) + 1 > this.levelAbove(place.list, place.index) + 1) return false;
    const [start, end] = this.unitOf(place.list, place.index);
    return place.list.blocks.slice(start, end).every((b) => !isSubHeading(b) || levelOf(b) < 5);
  }

  /** Set a sub-heading's level (the warnings panel's Raise, F4). */
  setLevel(block: Block, level: number): boolean {
    const found = this.placeOfBlock(block);
    if (!found || block.type !== "heading") return false;
    block.level = level;
    delete block.raw;
    this.commit(found.chain);
    this.focusBlock(block);
    return true;
  }

  /** Raise all (issue #6, M6-0.6.9): set several sub-headings' levels in
   *  one undo step. Each pair is a block and the level it gets. */
  setLevels(changes: { block: Block; level: number }[]): number {
    const chains: Block[] = [];
    let done = 0;
    for (const { block, level } of changes) {
      const found = this.placeOfBlock(block);
      if (!found || block.type !== "heading") continue;
      block.level = level;
      delete block.raw;
      chains.push(...found.chain);
      done++;
    }
    if (done) this.commit(chains);
    return done;
  }

  /** The block that starts on a line of the chapter (the warnings panel). */
  blockOnLine(line: number): Block | null {
    return this.order().find((b) => b.line === line) ?? null;
  }

  private placeOfBlock(block: Block): Place | null {
    const chain = this.chainOf(block);
    const list = this.listOf(chain);
    const index = list.blocks.indexOf(block);
    return index < 0 ? null : { list, index, chain };
  }

  // --- Scriptorum's own dragging (F4.13, M6 part C2) ------------------------------

  private beginDrag(e: PointerEvent, place: Place, wrap: HTMLElement): void {
    if (this.readOnly) return;
    const scroller = this.root.closest<HTMLElement>(".editor-pane") ?? this.root;
    startDrag(e, {
      source: wrap,
      area: scroller,
      scroller,
      target: (x, y) => this.dropTarget(place, x, y),
      onReason: (reason) => { if (reason) this.hooks.flash(reason); },
    });
  }

  /** Where a dragged block would land under the pointer. Over the edge of a
   * container the pointer's left or right position chooses: over the
   * container's own frame it goes just before or after the container, over
   * its contents it goes inside; the line is indented to show which. */
  dropTarget(from: Place, x: number, y: number): DropTarget | null {
    const hit = document.elementFromPoint(x, y) as HTMLElement | null;
    if (!hit || !this.root.contains(hit)) return null;
    const node = hit.closest<HTMLElement>("section.blk, .add-row");
    if (!node || !this.root.contains(node)) return null;
    const place = this.placeOf.get(node);
    if (!place) return null;
    const listBox = (node.parentElement ?? node).getBoundingClientRect();
    const rect = node.getBoundingClientRect();
    let target: Place;
    let lineY: number;
    if (node.classList.contains("add-row")) {
      target = place;
      lineY = node.classList.contains("empty-list") ? rect.top + rect.height / 2 : rect.top - 4;
    } else {
      const after = y > rect.top + rect.height / 2;
      target = { list: place.list, index: place.index + (after ? 1 : 0), chain: place.chain };
      lineY = after ? rect.bottom + 6 : rect.top - 6;
    }
    // At the start or end of a container the pointer's left or right
    // position chooses the depth: each INDENT pixels from the editor's left
    // edge is one level, so moving left steps out of the container, just
    // before or after it. The line is indented to the depth it lands at.
    const rootLeft = (this.root.querySelector(":scope > .blk-list") ?? this.root).getBoundingClientRect().left;
    const wanted = Math.max(0, Math.floor((x - rootLeft) / INDENT));
    while (target.chain.length > wanted && (target.index === 0 || target.index >= target.list.blocks.length)) {
      const owner = target.chain[target.chain.length - 1];
      const outerChain = target.chain.slice(0, -1);
      const outer = this.listOf(outerChain);
      const at = outer.blocks.indexOf(owner);
      const sec = this.blockSections()[this.order().indexOf(owner)];
      const r = sec?.getBoundingClientRect();
      if (target.index === 0 && target.list.blocks.length > 0) {
        target = { list: outer, index: at, chain: outerChain };
        if (r) lineY = r.top - 6;
      } else {
        target = { list: outer, index: at + 1, chain: outerChain };
        if (r) lineY = r.bottom + 6;
      }
    }
    const [start, end] = this.unitOf(from.list, from.index);
    const unit = from.list.blocks.slice(start, end);
    const reason = unit.some((b) => target.chain.includes(b)) ? t("editor.reason.itself") : this.reasonAgainst(unit[0], target);
    if (reason) return { ok: false, reason };
    const chosen = target;
    return {
      ok: true,
      line: { left: rootLeft + INDENT * target.chain.length, right: listBox.right, y: lineY },
      drop: () => this.moveUnit(from, chosen),
    };
  }

  // --- Convert to (F4.2) --------------------------------------------------------

  /** The kinds this block can be converted to where it stands. */
  convertKinds(place: Place): string[] {
    const block = place.list.blocks[place.index];
    if (!block || block.type === "locked" || block.type === "table" || block.type === "image") return [];
    const current = kindOf(block);
    const kinds = this.kindsFor(place.list, place.chain, this.allowOf(place.chain));
    if (this.splitsScene(place) && !kinds.includes("scene")) kinds.splice(kinds.indexOf("heading") + 1 || 1, 0, "scene");
    return kinds.filter((k) => k !== current && k !== "table" && k !== "image" && this.defs.get(k)?.category !== "layout");
  }

  /** A block directly inside a top-level scene can become a new scene that
   * starts after it (pasted text: "Scene 2: …" inside scene 1). */
  private splitsScene(place: Place): boolean {
    const owner = place.chain[place.chain.length - 1];
    return place.chain.length === 1 && !!owner && owner.kind === "scene" && this.defs.has("scene");
  }

  /** Change a block into another kind in one undoable step. The text is
   * kept; a scene takes in the blocks after it, up to the next scene. */
  convert(place: Place, kind: string): void {
    if (kind === "scene" && this.splitsScene(place)) {
      // Split the scene: this block and everything after it move out into a
      // new top-level scene placed after the current one.
      const owner = place.chain[0];
      const taken = place.list.blocks.splice(place.index);
      const top = this.doc.blocks.indexOf(owner);
      this.doc.blocks.splice(top + 1, 0, ...taken);
      delete owner.raw;
      taken.forEach((b) => delete b.sep);
      this.convert({ list: this.doc, index: top + 1, chain: [] }, "scene");
      return;
    }
    const block = place.list.blocks[place.index];
    const text = textOf(block, this.defs.get(block.kind ?? ""));
    const children = isDoc(block.body) ? block.body.blocks : [];
    const target = this.newBlock(kind);
    target.sep = block.sep;
    const singleLine = !text.includes("\n") && inlineToPlain(text).length <= 80;
    const release: Block[] = [];

    if (target.type === "paragraph") {
      target.text = text;
      release.push(...children);
    } else if (target.type === "heading") {
      target.text = text.replace(/\s*\n+\s*/g, " ");
      release.push(...children);
      if (isSubHeading(target)) {
        // The level follows the position: never more than one level deeper
        // than the sub-heading above it (F4).
        target.level = Math.max(3, Math.min(levelOf(target), this.levelAbove(place.list, place.index) + 1));
      }
    } else {
      const def = this.defs.get(kind)!;
      const required = def.fields.find((f) => f.required && f.kind === "text");
      const richField = def.fields.find((f) => f.kind === "rich");
      const plain = inlineToPlain(text);
      if (text && required && singleLine && (def.body === "blocks" || def.body === "none" || !def.bodyRequired)) {
        target.fields![required.name] = plain;
      } else if (text && (def.body === "rich" || def.body === "plain")) {
        target.body = text;
      } else if (text && def.body === "blocks" && def.allow && def.allow.length === 1) {
        const child = this.newBlock(def.allow[0]);
        child.body = text;
        (target.body as Doc).blocks = [child];
      } else if (text && def.body === "blocks") {
        (target.body as Doc).blocks = [{ type: "paragraph", text }];
      } else if (text && richField) {
        target.fields![richField.name] = text;
      } else if (text && required) {
        target.fields![required.name] = plain;
      }
      if (def.body === "blocks" && isDoc(target.body)) {
        const keep = children.filter((c) => !def.allow || def.allow.includes(kindOf(c)));
        target.body.blocks.push(...keep);
        release.push(...children.filter((c) => !keep.includes(c)));
        if (kind === "scene" && place.chain.length === 0) {
          // A scene holds everything up to the next scene or act heading.
          const rest = place.list.blocks.slice(place.index + 1);
          const stop = rest.findIndex((b) => (b.type === "element" && b.kind === "scene") || b.type === "heading");
          const taken = stop < 0 ? rest : rest.slice(0, stop);
          place.list.blocks.splice(place.index + 1, taken.length);
          target.body.blocks.push(...taken);
        }
        target.body.blocks.forEach((b, i) => { if (i === 0) delete b.sep; });
      } else {
        release.push(...children);
      }
    }
    release.forEach((b) => delete b.sep);
    place.list.blocks.splice(place.index, 1, target, ...release);
    this.commit(place.chain);
    this.focusBlock(target);
  }

  // --- keyboard and focus ---------------------------------------------------------

  private onKey(e: KeyboardEvent): void {
    if (!e.altKey || this.readOnly || !this.focus) return;
    if (e.key === "ArrowUp" || e.key === "ArrowDown") {
      e.preventDefault();
      this.move(this.focus, e.key === "ArrowUp" ? -1 : 1);
    } else if (e.key === "ArrowRight") {
      // M6 part C2: into the container just above, at its end.
      e.preventDefault();
      this.moveIn(this.focus);
    } else if (e.key === "ArrowLeft") {
      // M6 part C2: out of the container, to just after it.
      e.preventDefault();
      if (!this.focus.chain.length) this.hooks.flash(t("editor.reason.notInContainer"));
      else this.moveOut(this.focus, "after");
    }
  }

  private order(): Block[] {
    const order: Block[] = [];
    const walk = (doc: Doc) => doc.blocks.forEach((b) => {
      order.push(b);
      if (isDoc(b.body)) walk(b.body);
    });
    walk(this.doc);
    return order;
  }

  private blockSections(): HTMLElement[] {
    return [...this.root.querySelectorAll<HTMLElement>("section.blk")];
  }

  focusBlock(block: Block): void {
    const index = this.order().indexOf(block);
    const wrapper = this.blockSections()[index];
    const target = wrapper?.querySelector<HTMLElement>("input:not([type=checkbox]), [contenteditable=true], select");
    target?.focus();
    wrapper?.scrollIntoView({ block: "nearest" });
  }

  private focusField(block: Block, name: string): void {
    const index = this.order().indexOf(block);
    const wrapper = this.blockSections()[index];
    wrapper?.querySelector<HTMLElement>(`.field-${name} input, .field-${name} [contenteditable=true]`)?.focus();
  }

  /** The block at a path of indexes (F12: the element clicked on a page). */
  blockAt(path: number[]): { block: Block; place: Place } | null {
    let list = this.doc;
    const chain: Block[] = [];
    for (let i = 0; i < path.length; i++) {
      const block = list.blocks[path[i]];
      if (!block) return null;
      if (i === path.length - 1) return { block, place: { list, index: path[i], chain } };
      if (!isDoc(block.body)) return null;
      chain.push(block);
      list = block.body;
    }
    return null;
  }

  scrollToLine(line: number): void {
    const sections = this.blockSections();
    const match = sections.find((s) => Number(s.dataset.line) === line);
    match?.scrollIntoView({ block: "start", behavior: "smooth" });
    match?.querySelector<HTMLElement>("input, [contenteditable=true]")?.focus();
  }
}

function escapeCell(text: string): string {
  // Typed text, printed exactly as typed (T-SRC-04).
  return escapeInline(text);
}

/** The text of a block, for Convert to. */
function textOf(block: Block, def: ElementDef | undefined): string {
  if (block.type === "paragraph" || block.type === "heading") return block.text ?? "";
  if (block.type !== "element") return "";
  if (typeof block.body === "string" && block.body.trim()) return block.body;
  const parts: string[] = [];
  for (const f of def?.fields ?? []) {
    const v = block.fields?.[f.name];
    if (typeof v === "string" && v.trim() && f.kind !== "id" && f.kind !== "element-ref" && f.kind !== "image") parts.push(v);
  }
  return parts.join("\n\n");
}

export class SourceEditor {
  private gutter: HTMLElement;
  readonly area: HTMLTextAreaElement;
  // F4.10 (issue #12, M6-0.6.9): every line with an error is marked.
  private errorLines = new Set<number>();

  constructor(root: HTMLElement, onInput: (text: string) => void, onCaret: (line: number) => void) {
    root.textContent = "";
    this.gutter = el("pre", "gutter", { "aria-hidden": "true" });
    this.area = el("textarea", "source-area", { spellcheck: "false", wrap: "off" });
    this.area.setAttribute("aria-label", t("editor.sourceLabel"));
    root.append(this.gutter, this.area);
    this.area.addEventListener("input", () => {
      this.renderGutter();
      onInput(this.area.value);
    });
    const caret = () => onCaret(this.caretLine());
    this.area.addEventListener("keyup", caret);
    this.area.addEventListener("click", caret);
    this.area.addEventListener("focus", caret);
    this.area.addEventListener("scroll", () => {
      this.gutter.scrollTop = this.area.scrollTop;
    });
  }

  set readOnly(value: boolean) {
    this.area.readOnly = value;
  }

  set(text: string): void {
    if (this.area.value !== text) this.area.value = text;
    this.renderGutter();
  }

  value(): string {
    return this.area.value;
  }

  caretLine(): number {
    return this.area.value.slice(0, this.area.selectionStart).split("\n").length;
  }

  markErrors(lines: number[]): void {
    this.errorLines = new Set(lines);
    this.renderGutter();
  }

  goToLine(line: number): void {
    const lines = this.area.value.split("\n");
    const offset = lines.slice(0, line - 1).reduce((n, l) => n + l.length + 1, 0);
    this.area.focus();
    this.area.setSelectionRange(offset, offset);
    const lineHeight = parseFloat(getComputedStyle(this.area).lineHeight) || 20;
    this.area.scrollTop = Math.max(0, (line - 4) * lineHeight);
  }

  private renderGutter(): void {
    const count = this.area.value.split("\n").length;
    this.gutter.textContent = "";
    for (let i = 1; i <= count; i++) {
      const bad = this.errorLines.has(i);
      const span = el("span", bad ? "gl error" : "gl");
      if (bad) span.title = t("editor.errorLine");
      span.textContent = String(i) + "\n";
      this.gutter.append(span);
    }
    this.gutter.scrollTop = this.area.scrollTop;
  }
}
