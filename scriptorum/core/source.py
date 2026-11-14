"""Source format reader and writer (design document 3.4, D11, F4.11).

Chapter text is Typst markup limited to the element kinds the game system
defines. This module turns a chapter into a list of blocks the editor can
show, and turns blocks back into text.

Rules:

* Every block keeps its original text (``raw``) and the whitespace before it
  (``sep``). Writing an unchanged block returns exactly that text, so opening
  and saving without edits never changes a file (T-FILE-07, T-SRC-01).
* Anything the editor does not recognise becomes a ``locked`` block. It is
  shown but never rewritten, and Typst still compiles it (F4.11).
* An edited block has no ``raw``; it is written in the canonical form below.

Block shapes (JSON, shared with the interface):

    {"type": "heading",   "level": 1, "text": "<inline markup>"}
    {"type": "paragraph", "text": "<inline markup>"}
    {"type": "element",   "kind": "scene", "fields": {...}, "variant": None,
                          "new_page": None, "body": None | "<inline>" | {"blocks": [...], "trail": ""}}
    {"type": "table",     "columns": 2, "header": ["<inline>", ...], "rows": [["<inline>", ...], ...]}
    {"type": "image",     "path": "/assets/images/<name>"}
    {"type": "locked"}

plus ``sep``, ``raw``, ``line`` (1-based) and, for elements, ``head_raw``
and ``locked_fields`` (rich fields kept exactly as written, such as a table
in a creature's attacks).
Inline markup supported: plain text, escapes, *bold*, _italic_ and calls of
inline elements without a body, such as ``#dice(dice: "D6")`` (11.7).
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


class Unbalanced(Exception):
    pass


# Field kinds written as Typst strings (9.4). From M3 a codex reference
# (F3.5) and a map reference (F5.4) are the entry's or map's permanent ID.
TEXT_KINDS = {"text", "choice", "image", "dice", "element-ref", "id", "codex", "map-ref"}
# Field kinds written as a Typst array of strings: several codex references,
# such as the people who know an Information item (11.3, F3.5).
LIST_KINDS = {"codex-list"}
# Field kinds written as Typst integers: a number, and the hidden "look" of a
# handout (F6.5, the New look button).
INT_KINDS = {"number", "seed"}


# --------------------------------------------------------------------------
# Inline markup

ESCAPE_CHARS = set("\\*_#$@<>[]`~/")
LINE_START_MARKERS = re.compile(r"^(=+\s|[-+]\s|/\s|\d+\.\s)")


def escape_inline(plain: str) -> str:
    """Escape plain text so Typst prints it exactly as typed (T-SRC-04)."""
    out = []
    for ch in plain:
        if ch in ESCAPE_CHARS:
            out.append("\\" + ch)
        else:
            out.append(ch)
    text = "".join(out)
    # Characters that only mean something at the start of a line.
    lines = text.split("\n")
    fixed = []
    for line in lines:
        stripped = line.lstrip(" \t")
        indent = line[: len(line) - len(stripped)]
        if stripped[:1] in ("=", "-", "+"):
            stripped = "\\" + stripped
        else:
            m = re.match(r"^(\d+)\.", stripped)
            if m:
                stripped = m.group(1) + "\\." + stripped[m.end():]
        fixed.append(indent + stripped)
    return "\n".join(fixed)


def inline_ok(markup: str, inline_kinds: frozenset = frozenset()) -> bool:
    """True when the markup uses only what the editor supports: text,
    escapes, bold, italic and calls of inline elements (11.7)."""
    strong = emph = False
    i, n = 0, len(markup)
    at_line_start = True
    while i < n:
        c = markup[i]
        if at_line_start:
            rest = markup[i:]
            stripped = rest.lstrip(" \t")
            if LINE_START_MARKERS.match(stripped):
                return False
            at_line_start = False
        if c == "\\":
            if i + 1 < n and markup[i + 1] == "u" and markup[i + 2:i + 3] == "{":
                return False
            i += 2
            continue
        if c == "\n":
            at_line_start = True
        elif c in "*_" and _intra_word(markup, i):
            pass  # Typst prints * and _ between two word characters as is
        elif c == "*":
            strong = not strong
        elif c == "_":
            emph = not emph
        elif c == "#" and inline_kinds:
            end = _inline_call_end(markup, i, inline_kinds)
            if end is None:
                return False
            i = end
            continue
        elif c in "#$@`[]":
            return False
        elif c == "<" and re.match(r"<[\w\-:.]+>", markup[i:]):
            return False
        elif c == "/" and markup[i + 1:i + 2] in ("/", "*"):
            return False
        i += 1
    return not strong and not emph


INLINE_CALL = re.compile(r"#[A-Za-z][A-Za-z0-9-]*\([^()\[\]]*\)")


def _inline_call_end(markup: str, i: int, inline_kinds) -> Optional[int]:
    """End of an inline element call such as #dice(dice: "D6"), or None."""
    k = _read_ident(markup, i + 1)
    if markup[i + 1:k] not in inline_kinds or k >= len(markup) or markup[k] != "(":
        return None
    try:
        end = _scan_code_group(markup, k)
        _split_args(markup[k + 1:end - 1])
    except Unbalanced:
        return None
    if end < len(markup) and markup[end] in "([":
        return None
    # A full stop ends the sentence; Typst reads it as field access only when
    # a name follows it ("#see(entry: ...)." is fine, M3).
    if end < len(markup) and markup[end] == "." and end + 1 < len(markup) and _is_ident_start(markup[end + 1]):
        return None
    return end


def inline_to_plain(markup: str) -> str:
    """Readable text for outlines and word counts."""
    markup = INLINE_CALL.sub("", markup)
    out, i, n = [], 0, len(markup)
    while i < n:
        c = markup[i]
        if c == "\\" and i + 1 < n:
            nxt = markup[i + 1]
            out.append(" " if nxt in " \n" else nxt)
            i += 2
            continue
        if c in "*_" and not _intra_word(markup, i):
            i += 1
            continue
        out.append(c)
        i += 1
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _intra_word(text: str, i: int) -> bool:
    return 0 < i < len(text) - 1 and text[i - 1].isalnum() and text[i + 1].isalnum()


# --------------------------------------------------------------------------
# Typst strings

def quote_string(value: str) -> str:
    return '"' + (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
    ) + '"'


def unquote_string(literal: str) -> str:
    body = literal[1:-1]
    out, i = [], 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt == "n":
                out.append("\n")
            elif nxt == "t":
                out.append("\t")
            elif nxt == "r":
                out.append("\r")
            elif nxt == "u" and body[i + 2:i + 3] == "{":
                end = body.index("}", i)
                out.append(chr(int(body[i + 3:end], 16)))
                i = end + 1
                continue
            else:
                out.append(nxt)
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


# --------------------------------------------------------------------------
# Scanners (bracket matching that understands strings, raw text, math,
# comments and nested code)

def _is_ident_start(c: str) -> bool:
    return c.isalpha() or c == "_"


def _read_ident(s: str, i: int) -> int:
    n = len(s)
    if i >= n or not _is_ident_start(s[i]):
        return i
    j = i + 1
    while j < n and (s[j].isalnum() or s[j] in "_-"):
        j += 1
    # A trailing hyphen is not part of a Typst identifier.
    while j > i + 1 and s[j - 1] == "-":
        j -= 1
    return j


def _scan_string(s: str, i: int) -> int:
    n = len(s)
    i += 1
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return i + 1
        if c == "\n":
            raise Unbalanced()
        i += 1
    raise Unbalanced()


def _scan_comment(s: str, i: int) -> int:
    if s.startswith("//", i):
        end = s.find("\n", i)
        return len(s) if end < 0 else end
    end = s.find("*/", i + 2)
    if end < 0:
        raise Unbalanced()
    return end + 2


def _scan_raw(s: str, i: int) -> int:
    j = i
    while j < len(s) and s[j] == "`":
        j += 1
    ticks = s[i:j]
    if len(ticks) == 2:  # empty raw ``
        return j
    end = s.find(ticks, j)
    if end < 0:
        raise Unbalanced()
    return end + len(ticks)


def _scan_math(s: str, i: int) -> int:
    j = i + 1
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "$":
            return j + 1
        j += 1
    raise Unbalanced()


def _scan_code_group(s: str, i: int) -> int:
    """s[i] is '(' or '{'. Returns the index after the matching close."""
    n = len(s)
    depth = 0
    while i < n:
        c = s[i]
        if c == '"':
            i = _scan_string(s, i)
            continue
        if c == "[":
            i = _scan_content(s, i)
            continue
        if c == "/" and s[i + 1:i + 2] in ("/", "*"):
            i = _scan_comment(s, i)
            continue
        if c in "({":
            depth += 1
        elif c in ")}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise Unbalanced()


def _scan_hash(s: str, i: int) -> int:
    """s[i] is '#'. Returns the end of the embedded code expression."""
    n = len(s)
    j = i + 1
    if j < n and s[j] in "({":
        return _scan_code_group(s, j)
    k = _read_ident(s, j)
    if k == j:
        return j
    j = k
    while j < n:
        if s[j] in "({":
            j = _scan_code_group(s, j)
        elif s[j] == "[":
            j = _scan_content(s, j)
        elif s[j] == "." and j + 1 < n and _is_ident_start(s[j + 1]):
            j = _read_ident(s, j + 1)
        else:
            break
    return j


def _scan_content(s: str, i: int) -> int:
    """s[i] is '['. Returns the index after the matching ']'."""
    n = len(s)
    depth = 0
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return i + 1
        elif c == "#":
            i = _scan_hash(s, i)
            continue
        elif c == "`":
            i = _scan_raw(s, i)
            continue
        elif c == "$":
            i = _scan_math(s, i)
            continue
        elif c == "/" and s[i + 1:i + 2] in ("/", "*"):
            i = _scan_comment(s, i)
            continue
        i += 1
    raise Unbalanced()


BLANK_LINE = re.compile(r"\n[ \t]*\n")


def _scan_chunk(s: str, i: int) -> int:
    """From i, find the end of a markup chunk: the first blank line outside
    any brackets, or the end of the text. Trailing whitespace is excluded."""
    n = len(s)
    j = i
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "\n":
            if BLANK_LINE.match(s, j):
                break
            j += 1
            continue
        try:
            if c == "#":
                j = _scan_hash(s, j)
                continue
            if c == "[":
                j = _scan_content(s, j)
                continue
            if c == "`":
                j = _scan_raw(s, j)
                continue
            if c == "$":
                j = _scan_math(s, j)
                continue
            if c == "/" and s[j + 1:j + 2] in ("/", "*"):
                j = _scan_comment(s, j)
                continue
        except Unbalanced:
            return len(s.rstrip())
        j += 1
    end = min(j, n)
    while end > i and s[end - 1] in " \t\n\r":
        end -= 1
    return end


# --------------------------------------------------------------------------
# Arguments

ARG_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.+)$", re.DOTALL)


def _split_args(text: str) -> List[str]:
    parts, depth, start, i, n = [], 0, 0, 0, len(text)
    while i < n:
        c = text[i]
        if c == '"':
            i = _scan_string(text, i)
            continue
        if c == "[":
            i = _scan_content(text, i)
            continue
        if c in "({":
            depth += 1
        elif c in ")}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def _parse_value(value: str):
    """Returns ('str', text) | ('content', inner) | ('bool', b) | ('none', None)
    | ('int', n) | ('list', [text, ...])."""
    value = value.strip()
    if value.startswith("(") and value.endswith(")"):
        # An array of strings, such as ("c-lovisa", "c-nils") or ("c-lovisa",).
        if _scan_code_group(value, 0) != len(value):
            raise ValueError(value)
        items = []
        for part in _split_args(value[1:-1]):
            kind, item = _parse_value(part)
            if kind != "str":
                raise ValueError(value)
            items.append(item)
        return ("list", items)
    if value.startswith('"'):
        end = _scan_string(value, 0)
        if end == len(value):
            return ("str", unquote_string(value))
    elif value.startswith("["):
        end = _scan_content(value, 0)
        if end == len(value):
            return ("content", value[1:-1])
    elif value in ("true", "false"):
        return ("bool", value == "true")
    elif value == "none":
        return ("none", None)
    elif re.fullmatch(r"-?\d+", value):
        return ("int", int(value))
    raise ValueError(value)


# --------------------------------------------------------------------------
# Blocks

def _line_of(text: str, index: int, base_line: int) -> int:
    return base_line + text.count("\n", 0, index)


def inline_kinds_of(kinds: Dict[str, dict]) -> frozenset:
    """Element kinds that can stand inside a sentence (category inline or
    both, written as a call without a body)."""
    return frozenset(k for k, d in kinds.items() if d.get("inline_form") == "call")


def parse(text: str, kinds: Dict[str, dict], base_line: int = 1, allow: Optional[List[str]] = None) -> dict:
    """Parse a chapter (or an element body) into blocks."""
    blocks = []
    i, n = 0, len(text)
    while True:
        j = i
        while j < n and text[j] in " \t\n\r":
            j += 1
        sep = text[i:j]
        if j >= n:
            return {"blocks": blocks, "trail": sep}
        end, block = _parse_block(text, j, kinds, base_line, allow)
        if end <= j:  # never stall on text no rule understands
            end, block = j + 1, {"type": "locked"}
        block["sep"] = sep
        block["raw"] = text[j:end]
        block["line"] = _line_of(text, j, base_line)
        blocks.append(block)
        i = end


def _locked(text: str, j: int) -> Tuple[int, dict]:
    return _scan_chunk(text, j), {"type": "locked"}


def _allowed_here(ident: str, kinds: Dict[str, dict], allow) -> bool:
    if allow is not None:
        return ident in allow
    # Elements that only live inside another (a countdown step) are not
    # allowed at the top of a chapter or scene.
    return not kinds[ident].get("only_inside")


def _parse_block(text: str, j: int, kinds: Dict[str, dict], base_line: int, allow) -> Tuple[int, dict]:
    n = len(text)
    inline = inline_kinds_of(kinds)
    # Heading: "= Title" on one line.
    m = re.match(r"(=+)[ \t]+([^\n]*)", text[j:])
    if m and allow is None:
        end = j + m.end()
        stripped_end = end
        while stripped_end > j and text[stripped_end - 1] in " \t":
            stripped_end -= 1
        body = m.group(2).rstrip()
        if inline_ok(body, inline):
            return stripped_end, {"type": "heading", "level": len(m.group(1)), "text": body}
        return _locked(text, j)

    if text[j] == "#":
        ident_end = _read_ident(text, j + 1)
        ident = text[j + 1:ident_end]
        if ident in kinds and _allowed_here(ident, kinds, allow):
            parsed = _parse_element(text, j, ident, ident_end, kinds, base_line)
            if parsed is not None:
                return parsed
        if allow is None and ident == "table":
            parsed = _parse_table(text, j, ident_end, inline)
            if parsed is not None:
                return parsed
        if allow is None and ident == "image":
            parsed = _parse_image(text, j, ident_end)
            if parsed is not None:
                return parsed
        if allow is None and ident in inline:
            # An inline element at the start of a paragraph (11.7).
            end = _scan_chunk(text, j)
            raw = text[j:end]
            if inline_ok(raw, inline):
                return end, {"type": "paragraph", "text": raw}
        return _locked(text, j)

    if allow is not None:
        # Inside a restricted body (a person card) only allowed elements fit.
        return _locked(text, j)

    end = _scan_chunk(text, j)
    raw = text[j:end]
    if inline_ok(raw, inline):
        return end, {"type": "paragraph", "text": raw}
    return end, {"type": "locked"}


def _rest_of_line_empty(text: str, k: int) -> bool:
    eol = text.find("\n", k)
    eol = len(text) if eol < 0 else eol
    return not text[k:eol].strip()


def _parse_table(text: str, j: int, k: int, inline) -> Optional[Tuple[int, dict]]:
    """F4.5: a table the editor can edit, written in the canonical form
    ``#table(columns: N, table.header([..], ..), [..], ..)``. Any other
    table stays a locked block."""
    if k >= len(text) or text[k] != "(":
        return None
    try:
        end = _scan_code_group(text, k)
        parts = _split_args(text[k + 1:end - 1])
    except Unbalanced:
        return None
    if not _rest_of_line_empty(text, end) or len(parts) < 2:
        return None
    m = re.fullmatch(r"columns:\s*(\d+)", parts[0])
    if not m or not parts[1].startswith("table.header(") or not parts[1].endswith(")"):
        return None
    columns = int(m.group(1))
    try:
        header = [_cell(c, inline) for c in _split_args(parts[1][len("table.header("):-1])]
        cells = [_cell(c, inline) for c in parts[2:]]
    except ValueError:
        return None
    if columns < 1 or len(header) != columns or len(cells) % columns:
        return None
    rows = [cells[i:i + columns] for i in range(0, len(cells), columns)]
    return end, {"type": "table", "columns": columns, "header": header, "rows": rows}


def _cell(part: str, inline) -> str:
    part = part.strip()
    if not part.startswith("["):
        raise ValueError(part)
    try:
        if _scan_content(part, 0) != len(part):
            raise ValueError(part)
    except Unbalanced:
        raise ValueError(part)
    inner = part[1:-1]
    if not inline_ok(inner, inline):
        raise ValueError(part)
    return inner


def _parse_image(text: str, j: int, k: int) -> Optional[Tuple[int, dict]]:
    """F4.6: ``#image("/assets/images/<name>")`` on a line of its own; from M5
    with its description for screen readers, ``alt: "…"`` (F17.3)."""
    m = re.match(r'\("(/assets/images/[^"\\]+)"(?:, alt: ("(?:[^"\\]|\\.)*"))?\)', text[k:])
    if not m:
        return None
    end = k + m.end()
    if not _rest_of_line_empty(text, end):
        return None
    block = {"type": "image", "path": m.group(1)}
    if m.group(2) is not None:
        block["alt"] = unquote_string(m.group(2))
    return end, block


def _parse_element(text, j, ident, k, kinds, base_line):
    definition = kinds[ident]
    n = len(text)
    try:
        args_text = None
        if k < n and text[k] == "(":
            args_end = _scan_code_group(text, k)
            args_text = text[k + 1:args_end - 1]
            k = args_end
        head_end = k
        body_inner = None
        body_start = None
        if k < n and text[k] == "[":
            body_end = _scan_content(text, k)
            body_inner = text[k + 1:body_end - 1]
            body_start = k + 1
            k = body_end
    except Unbalanced:
        return None
    if k < n and (text[k] in "([" or text[k] == "."):
        return None
    eol = text.find("\n", k)
    eol = n if eol < 0 else eol
    if text[k:eol].strip():
        return None
    end = k

    fields_by_name = {f["name"]: f for f in definition.get("fields", [])}
    inline = inline_kinds_of(kinds)
    variant_ids = [v["id"] for v in definition.get("variants") or []]
    block = {
        "type": "element",
        "kind": ident,
        "fields": {},
        "variant": None,
        "new_page": None,
        "body": None,
        "head_raw": text[j:head_end],
    }
    try:
        for part in _split_args(args_text or ""):
            am = ARG_RE.match(part)
            if not am:
                return None
            name, value = am.group(1), am.group(2)
            vtype, val = _parse_value(value)
            if name == "variant" and variant_ids:
                if vtype != "str" or val not in variant_ids:
                    return None
                block["variant"] = val
            elif name == "new-page" and definition.get("page_start_switchable"):
                if vtype != "bool":
                    return None
                block["new_page"] = val
            elif name in fields_by_name:
                kind = fields_by_name[name]["kind"]
                if vtype == "none":
                    continue
                if kind in TEXT_KINDS and vtype == "str":
                    block["fields"][name] = val
                elif kind in INT_KINDS and vtype == "int":
                    block["fields"][name] = val
                elif kind in LIST_KINDS and vtype == "list":
                    block["fields"][name] = val
                elif kind == "bool" and vtype == "bool":
                    block["fields"][name] = val
                elif kind == "rich" and vtype == "content" and inline_ok(val.strip("\n"), inline):
                    block["fields"][name] = val.strip("\n")
                elif kind == "rich" and vtype == "content":
                    # Kept exactly as written (for example a table in a
                    # creature's attacks); edited in Source or Hybrid mode.
                    block["fields"][name] = val
                    block.setdefault("locked_fields", []).append(name)
                elif kind == "rich" and vtype == "str":
                    block["fields"][name] = escape_inline(val)
                else:
                    return None
            elif definition.get("keeps_extra_fields") and vtype != "none":
                # F3 (M6 part C4): Convert to codex entry leaves a field the
                # codex type lacks on the card, exactly as written, so
                # nothing is lost; the card prints it as before.
                block.setdefault("extra", {})[name] = value.strip()
            else:
                return None
    except (ValueError, Unbalanced):
        return None

    body_kind = definition.get("body", "none")
    if body_inner is not None:
        if body_kind == "none":
            return None
        if body_kind in ("rich", "plain"):
            stripped = body_inner.strip("\n")
            if not inline_ok(stripped, inline):
                return None
            block["body"] = stripped
        elif body_kind == "blocks":
            inner_line = _line_of(text, body_start, base_line)
            sub = parse(body_inner, kinds, inner_line, definition.get("allow"))
            if any(b["type"] == "locked" for b in _walk(sub["blocks"])) and definition.get("allow"):
                return None
            block["body"] = sub
    return end, block


def _walk(blocks):
    for b in blocks:
        yield b
        body = b.get("body")
        if isinstance(body, dict):
            yield from _walk(body["blocks"])


# --------------------------------------------------------------------------
# Writing

def _default_sep(index: int, nested: bool) -> str:
    if index == 0:
        return "\n" if nested else ""
    return "\n\n"


def serialize(doc: dict, kinds: Dict[str, dict], nested: bool = False) -> str:
    out = []
    for index, block in enumerate(doc.get("blocks", [])):
        sep = block.get("sep")
        if sep is None:
            sep = _default_sep(index, nested)
        out.append(sep + block_text(block, kinds))
    trail = doc.get("trail")
    if trail is None:
        trail = "\n"
    out.append(trail)
    return "".join(out)


def block_text(block: dict, kinds: Dict[str, dict]) -> str:
    raw = block.get("raw")
    if raw is not None:
        return raw
    btype = block["type"]
    if btype == "heading":
        return "=" * int(block.get("level", 1)) + " " + block.get("text", "")
    if btype == "paragraph":
        return block.get("text", "")
    if btype == "locked":
        return block.get("raw", "")
    if btype == "table":
        return _table_text(block)
    if btype == "image":
        if block.get("alt"):
            return f"#image({quote_string(block['path'])}, alt: {quote_string(block['alt'])})"
        return f"#image({quote_string(block['path'])})"
    if btype == "element":
        return _element_text(block, kinds)
    raise ValueError(btype)


def _element_text(block: dict, kinds: Dict[str, dict]) -> str:
    definition = kinds[block["kind"]]
    head = block.get("head_raw") or _element_head(block, definition)
    body = block.get("body")
    body_kind = definition.get("body", "none")
    if body_kind == "none" or body is None:
        if body_kind == "blocks":
            return head + "[\n]"
        if body_kind in ("rich", "plain"):
            return head + "[]"
        return head
    if body_kind in ("rich", "plain"):
        text = body
        if "\n" in text or len(text) > 60:
            return head + "[\n" + text + "\n]"
        return head + "[" + text + "]"
    return head + "[" + serialize(body, kinds, nested=True) + "]"


def _table_text(block: dict) -> str:
    """F4.5: the canonical table form, one row per line."""
    def cells(row):
        return ", ".join(f"[{c}]" for c in row)
    lines = [f"#table(", f"  columns: {block['columns']},", f"  table.header({cells(block['header'])}),"]
    for row in block.get("rows", []):
        lines.append(f"  {cells(row)},")
    lines.append(")")
    return "\n".join(lines)


def _element_head(block: dict, definition: dict) -> str:
    args = []
    fields = block.get("fields") or {}
    for field in definition.get("fields", []):
        value = fields.get(field["name"])
        if value is None or value == "" or value == [] or value is False:
            continue
        if field["kind"] == "rich":
            args.append(f"{field['name']}: [{value}]")
        elif field["kind"] in INT_KINDS:
            args.append(f"{field['name']}: {int(value)}")
        elif field["kind"] in LIST_KINDS:
            items = [quote_string(str(v)) for v in (value if isinstance(value, list) else [value])]
            args.append(f"{field['name']}: (" + ", ".join(items) + ("," if len(items) == 1 else "") + ")")
        elif field["kind"] == "bool":
            args.append(f"{field['name']}: true")
        else:
            args.append(f"{field['name']}: {quote_string(str(value))}")
    for name, raw in (block.get("extra") or {}).items():
        args.append(f"{name}: {raw}")  # F3 (M6 part C4): kept on the card as written
    variant_ids = [v["id"] for v in definition.get("variants") or []]
    if variant_ids:
        variant = block.get("variant") or definition.get("default_variant") or variant_ids[0]
        args.append(f"variant: {quote_string(variant)}")
    if definition.get("page_start_switchable") and block.get("new_page") is False:
        args.append("new-page: false")
    head = "#" + block["kind"]
    if args:
        head += "(" + ", ".join(args) + ")"
    elif definition.get("body", "none") == "none":
        # F4, F7.4 (M6 part C, found 12 November 2026): an element with no
        # body and no fields filled in, such as a page or column break, the
        # table of contents or the relationship chart, is always written
        # with (). Without them Typst prints the function itself,
        # "(..) => ..", instead of calling it.
        head += "()"
    return head


def complete_bare_calls(text: str, kinds: Dict[str, dict]) -> str:
    """F4, F7.4 (M6 part C): the build's own copy of an older adventure's
    text, with () added to every element that was written without them
    (``#column-break`` on a line of its own). The author's files are not
    changed; the block is written with () once it is edited. Line numbers
    stay the same, so build errors still land on the author's line."""
    bare = [k for k, d in kinds.items() if d.get("body", "none") == "none"]
    if not bare:
        return text
    pattern = re.compile(r"(?m)^([ \t]*#(?:" + "|".join(re.escape(k) for k in sorted(bare, key=len, reverse=True)) + r"))([ \t]*)$")
    if not pattern.search(text):
        return text
    lines = text.split("\n")
    doc = parse(text, kinds)
    for block in _walk(doc["blocks"]):
        if block.get("type") != "element" or block.get("kind") not in bare:
            continue
        if block.get("head_raw") != "#" + block["kind"] or not block.get("line"):
            continue
        index = block["line"] - 1
        if 0 <= index < len(lines):
            m = pattern.match(lines[index])
            if m and m.group(1).strip() == "#" + block["kind"]:
                lines[index] = m.group(1) + "()" + m.group(2)
    return "\n".join(lines)


DICE_FORM = re.compile(r"^(\d*)[Dd](\d+)([+\-\u2212]\d+)?$")
# Arguments every creature keeps whatever its game system (F7.4, 9.4).
CREATURE_KEEP = frozenset({"id", "new-page"})


def dice_fits(value: str, notation: dict) -> bool:
    """11.7: whether a dice notation is one the game system uses, by the same
    rule the core element kit's Typst applies (the die, and a modifier only
    where notation.json allows it)."""
    m = DICE_FORM.match(str(value))
    if not m:
        return False
    if m.group(3) and not notation.get("modifiers", False):
        return False
    return "d" + m.group(2) in (notation.get("dice") or ["d6"])


def _calls(text: str, name: str):
    """Every ``#name(`` call in the text: (start, index of "(", end after ")")."""
    for m in re.finditer(r"#" + re.escape(name) + r"\(", text):
        paren = m.end() - 1
        try:
            yield m.start(), paren, _scan_code_group(text, paren)
        except Unbalanced:
            continue


def fit_to_game_system(text: str, kinds: Dict[str, dict], notation: Optional[dict]) -> Tuple[str, List[dict]]:
    """F14 (Change game system, M6-0.6.9): the build's own copy of a chapter
    written for another game system. A creature field the game system's
    stat block lacks (Plain's free stat lines in Vaesen) is left out of the
    copy, and dice outside its notation (a d20 in Vaesen) print as their
    plain notation instead of stopping the build. The author's text is never
    changed, so changing back prints as before, and line numbers stay the
    same. Returns the copy and what was left out, each with its line."""
    found: List[dict] = []
    edits: List[Tuple[int, int, str]] = []
    creature = kinds.get("creature")
    if creature:
        allowed = {f["name"] for f in creature.get("fields", [])} | CREATURE_KEEP
        for start, paren, end in _calls(text, "creature"):
            parts = _split_args(text[paren + 1:end - 1])
            kept, dropped = [], []
            for part in parts:
                m = re.match(r"([A-Za-z_][\w-]*)\s*:", part)
                if m and m.group(1) not in allowed:
                    dropped.append(m.group(1))
                else:
                    kept.append(part)
            if dropped:
                lines = text.count("\n", paren, end)
                edits.append((paren, end, "(" + ", ".join(kept) + "\n" * lines + ")"))
                found.append({"kind": "field", "element": "creature", "fields": dropped, "line": _line_of(text, start, 1)})
    if notation is not None and kinds.get("dice"):
        for start, paren, end in _calls(text, "dice"):
            args = _split_args(text[paren + 1:end - 1])
            value = None
            for part in args:
                m = re.match(r"dice\s*:\s*(.+)$", part, re.S)
                if m:
                    try:
                        value = unquote_string(m.group(1).strip())
                    except Exception:  # noqa: BLE001 - not a plain string: Typst judges it
                        value = None
            if value is None or dice_fits(value, notation):
                continue
            pad = "\n" * text.count("\n", start, end)
            shown = escape_inline(value)
            if text[end:end + 1] == "[":
                # A dice block: its rule follows in [...]; it keeps its own ].
                edits.append((start, end + 1, "#block[" + shown + " " + pad))
            else:
                edits.append((start, end, "#[" + shown + "]" + pad))
            found.append({"kind": "dice", "dice": value, "line": _line_of(text, start, 1)})
    for a, b, new in sorted(edits, reverse=True):
        text = text[:a] + new + text[b:]
    return text, sorted(found, key=lambda f: f["line"])


# --------------------------------------------------------------------------
# Helpers for the interface

def _walk_paths(blocks, path=()):
    for index, b in enumerate(blocks):
        yield b, path + (index,)
        body = b.get("body")
        if isinstance(body, dict):
            yield from _walk_paths(body["blocks"], path + (index,))


def outline(doc: dict) -> List[dict]:
    """Acts (headings), scenes and their sub-headings in order (F4.9; sub-
    headings from M6 part C). Top-level items carry their index in the
    chapter, and every item its path of indexes, so the outline can move
    them. A sub-heading carries the path of its scene."""
    items = []
    for block, path in _walk_paths(doc.get("blocks", [])):
        entry = None
        if block["type"] == "heading":
            entry = {"kind": "heading", "level": block["level"], "title": inline_to_plain(block["text"]), "line": block.get("line")}
        elif block["type"] == "element" and block["kind"] == "scene":
            entry = {"kind": "scene", "title": (block.get("fields") or {}).get("title", ""), "line": block.get("line"),
                     "id": (block.get("fields") or {}).get("id")}
        if entry is not None:
            entry["path"] = list(path)
            if len(path) == 1:
                entry["index"] = path[0]
            items.append(entry)
    return items


SUB_HEADING_LEVELS = (3, 4, 5)  # Sub-heading 1, 2 and 3 (F4, M6 part C)


def skipped_headings(doc: dict, kinds: Dict[str, dict]) -> List[dict]:
    """F4 (M6 parts C and C3): every sub-heading that is more than one level
    deeper than the heading above it. Inside a scene the scene's own heading
    is level 2, so Sub-heading 1 (``===``) is level 3. Outside any scene
    (before the first scene, after an act heading or after a scene) a
    sub-heading is printed one level higher, so it sits under the act (level
    1) and Sub-heading 1 is level 2. ``level`` and ``to`` are the levels as
    written in the text. The text is never changed by this; the warnings
    panel offers to raise it."""
    found = []

    def check(heading, above, shift):
        level = heading["level"] - shift
        if level > above + 1:
            found.append({"line": heading.get("line"), "level": heading["level"], "to": above + 1 + shift,
                          "title": inline_to_plain(heading.get("text", ""))})
            return above + 1
        return level

    top_above = 1
    for block in doc.get("blocks", []):
        if block.get("type") == "heading":
            if block.get("level", 1) <= 2:
                top_above = block.get("level", 1)
            else:
                top_above = check(block, top_above, 1)
            continue
        if block.get("type") == "element" and block.get("kind") == "scene":
            top_above = 1
            body = block.get("body")
            if not isinstance(body, dict):
                continue
            above = 2
            for inner in body["blocks"]:
                if inner.get("type") == "heading" and inner.get("level", 1) >= 3:
                    above = check(inner, above, 0)
    return found


OUTSIDE_SUB_LABELS = {3: "scriptorum-sub-1", 4: "scriptorum-sub-2", 5: "scriptorum-sub-3"}


def retag_outside_headings(text: str, kinds: Dict[str, dict]) -> str:
    """F4, F17 (M6 part C3): in the build's own copy of a chapter, a sub-
    heading outside any scene is written one level higher (``===`` becomes
    ``==``) with a label naming its sub-heading style, so it prints like a
    sub-heading but is tagged and bookmarked under its act with no level
    skipped. The author's text is never changed; lines stay where they were,
    so errors still point to the author's own line."""
    if "===" not in text:
        return text
    doc = parse(text, kinds)
    out = []
    changed = False
    for block in doc["blocks"]:
        raw = block["raw"]
        if block["type"] == "heading" and block.get("level") in OUTSIDE_SUB_LABELS:
            raw = "=" * (block["level"] - 1) + " " + block["text"] + " <" + OUTSIDE_SUB_LABELS[block["level"]] + ">"
            changed = True
        out.append(block["sep"] + raw)
    if not changed:
        return text
    return "".join(out) + doc["trail"]


def word_count(doc: dict) -> int:
    words = 0
    for block in _walk(doc.get("blocks", [])):
        texts = []
        if block["type"] in ("heading", "paragraph"):
            texts.append(inline_to_plain(block.get("text", "")))
        elif block["type"] == "table":
            for row in [block.get("header", []), *block.get("rows", [])]:
                texts.extend(inline_to_plain(c) for c in row)
        elif block["type"] == "element":
            for value in (block.get("fields") or {}).values():
                if isinstance(value, str):
                    texts.append(inline_to_plain(value))
            if isinstance(block.get("body"), str):
                texts.append(inline_to_plain(block["body"]))
        for t in texts:
            words += len(t.split())
    return words


def mark_changed(block: dict) -> None:
    """Drop the stored text of an edited block so it is written afresh."""
    block.pop("raw", None)
