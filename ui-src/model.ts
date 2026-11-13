// Shapes shared with the core (scriptorum/core/source.py, session.py).

export interface Doc {
  blocks: Block[];
  trail?: string;
}

export interface Block {
  type: "heading" | "paragraph" | "element" | "locked" | "table" | "image";
  sep?: string;
  raw?: string;
  line?: number;
  level?: number;
  text?: string;
  kind?: string;
  fields?: Record<string, string | number | string[] | boolean>;
  locked_fields?: string[];
  variant?: string | null;
  new_page?: boolean | null;
  body?: string | Doc | null;
  head_raw?: string;
  // F4.5 tables
  columns?: number;
  header?: string[];
  rows?: string[][];
  // F4.6 images; F17.3 (M5): alt, the description for screen readers
  alt?: string;
  path?: string;
}

export interface FieldDef {
  name: string;
  kind: "text" | "rich" | "number" | "choice" | "image" | "dice" | "element-ref" | "id"
    | "codex" | "codex-list" | "map-ref" | "bool" | "seed";
  types?: string[] | null;
  legacy?: boolean;
  required: boolean;
  label: string;
  hidden?: boolean;
  min?: number | null;
  max?: number | null;
  default?: string | number | boolean;
  group?: string;
  section?: boolean;
  multiline?: boolean;
  /** 11.4 (M6 part C): "jpeg-png" for a portrait, which must be JPEG or PNG. */
  accept?: string;
  target?: string;
  options?: { id: string; label: string ; note?: string; font?: string }[];
}

export interface ElementDef {
  id: string;
  name: string;
  category: "block" | "inline" | "both" | "layout";
  body: "none" | "plain" | "rich" | "blocks";
  allow: string[] | null;
  onlyInside: string[] | null;
  fields: FieldDef[];
  variants: { id: string; label: string }[];
  defaultVariant: string | null;
  pageStart: string;
  pageStartSwitchable: boolean;
  numbered: boolean;
  outline: boolean;
  editor: "frame" | "form" | "chip" | "row";
  inlineForm: string | null;
  bodyRequired: boolean;
  enterAddsNext: boolean;
  shortcut: string | null;
  shortcutGroup: string | null;
  newLook?: boolean;
  codexRef?: string | null;
}

export interface OutlineItem {
  kind: string;
  title: string;
  line: number;
  level?: number;
  index?: number;
  id?: string | null;
  /** M6 part C2: the item's path of indexes in the chapter's blocks. */
  path?: number[];
}

export interface Chapter {
  index: number;
  path: string;
  text: string;
  doc: Doc;
  outline: OutlineItem[];
  words: number;
}

export function isDoc(body: unknown): body is Doc {
  return !!body && typeof body === "object" && Array.isArray((body as Doc).blocks);
}
