"""World-building: codex, maps, relationship chart and handouts (F3, F5, F6).

Everything here is stored in the adventure as plain UTF-8 JSON, one file per
thing, so an unpacked adventure stays readable in Git (design doc section 4):

    codex/<entry-id>.json        one codex entry (F3)
    codex/types/<type-id>.json   a codex type the author defined (F3.2)
    codex/relationship-chart.json  saved positions of the chart (F3.9)
    maps/<map-id>/map.json       a map: base image, size and layers (F5)
    maps/<map-id>/base.png|jpg   the map's base image (F5.7)

Entry file:  {"id", "type", "fields": {...}, "folder": "", "tags": []}
Map file:    {"id", "title", "image", "width", "height", "layers": [
                {"id", "name", "show_in_handout", "items": [
                   {"id", "type": "pin"|"label"|"area"|"note"|"line",
                    "x", "y" (0..1 of the image) | "points": [[x, y], ...],
                    "text", "entry",
                    pin: "number", "note" (M6 part C3),
                    line: "points" or "from", "to" (pin IDs), "style"}]}]}

References between files always use permanent IDs, never names or paths.
"""

from __future__ import annotations

import json
import re
import struct
import unicodedata
from typing import Dict, Iterable, List, Optional, Tuple

from scriptorum.core import source

ENTRY_PREFIX = "codex/"
TYPES_PREFIX = "codex/types/"
CHART_FILE = "codex/relationship-chart.json"
MAPS_PREFIX = "maps/"
ENTRY_ID = re.compile(r"^c-[a-z0-9-]+$")
MAP_ID = re.compile(r"^m-[a-z0-9-]+$")
INLINE_REF = re.compile(r'#(mention|see)\(entry:\s*"((?:[^"\\]|\\.)*)"\)')

# F3.2: the field kinds an author can give a codex type.
FIELD_KINDS = ("text", "rich", "number", "image", "link", "choice")
# F5.8: an area has 3 to 15 corner points (decided 6 Nov 2026).
AREA_MIN, AREA_MAX = 3, 15
ITEM_TYPES = ("pin", "label", "area", "note", "line")
LINE_STYLES = ("solid", "dashed")  # F5 (M6 part C3)



def pin_numbers(m: dict) -> Dict[str, int]:
    """F5 (M6 part C3): the number each pin of a map prints. A pin keeps the
    number it was given when it was placed (or that the author typed); an
    older pin without one gets the next free number, in the map's order."""
    pins = [item for layer in m.get("layers", []) for item in layer.get("items", []) if item.get("type") == "pin"]
    taken = {p["number"] for p in pins if isinstance(p.get("number"), int) and p["number"] > 0}
    out, n = {}, 1
    for p in pins:
        if isinstance(p.get("number"), int) and p["number"] > 0:
            out[p["id"]] = p["number"]
            continue
        while n in taken:
            n += 1
        out[p["id"]] = n
        taken.add(n)
    return out

class WorldError(Exception):
    """Refused change. ``key`` is an interface-string key (F15)."""

    def __init__(self, key: str, **details):
        super().__init__(key)
        self.key = key
        self.details = details


def slug(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")[:40] or "entry"


def _load_json(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"))


def _dump(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


# --------------------------------------------------------------------------
# Images (F5.7)

def image_size(data: bytes) -> Optional[Tuple[str, int, int]]:
    """('png'|'jpg', width, height) for a PNG or JPEG file, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return "png", width, height
    if data[:2] == b"\xff\xd8":
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            length = struct.unpack(">H", data[i + 2:i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack(">HH", data[i + 5:i + 9])
                return "jpg", width, height
            i += 2 + length
    return None


# --------------------------------------------------------------------------

class World:
    """The codex, maps, chart and handouts of one open adventure."""

    def __init__(self, adventure, kinds: Dict[str, dict], module_types: Dict[str, dict], labels: Dict[str, str]):
        self.adventure = adventure
        self.kinds = kinds
        self.module_types = module_types
        self.labels = labels

    # --- codex types (F3.1, F3.2, 9.5) ---------------------------------------
    def types(self) -> Dict[str, dict]:
        """Built-in types from the modules, then the author's own types. A type
        may take its fields from an element kind (Creature: the game system's
        stat block, 11.5)."""
        result: Dict[str, dict] = {}
        for type_id, d in self.module_types.items():
            result[type_id] = self._expand_type(d, own=False)
        for name in self.adventure.files_in(TYPES_PREFIX):
            try:
                d = _load_json(self.adventure.files[name])
            except ValueError:
                continue
            if isinstance(d, dict) and d.get("id") and d["id"] not in result:
                result[d["id"]] = self._expand_type(d, own=True)
        return result

    def _expand_type(self, d: dict, own: bool) -> dict:
        fields = list(d.get("fields", []))
        element = d.get("fields_from_element")
        if element and element in self.kinds:
            fields = [{k: v for k, v in f.items()} for f in self.kinds[element].get("fields", []) if f.get("kind") != "id"]
        for f in fields:
            if f.get("kind") == "choice" and f.get("options_from") == "handwriting":
                f["options"] = []  # filled by the session (F3.11)
        name = d.get("name", d["id"])
        return {
            "id": d["id"],
            "name": name if own else self.labels.get(name, name),
            "icon": d.get("icon", "entry"),
            "title_field": d.get("title_field", "name"),
            "fields": fields,
            "card": d.get("card_element"),
            "own": own,
        }

    def save_type(self, data: dict) -> dict:
        """F3.2: create or change an author-defined codex type."""
        name = str(data.get("name", "")).strip()
        if not name:
            raise WorldError("error.codex.typeName")
        type_id = data.get("id") or "t-" + slug(name)
        builtin = set(self.module_types)
        if type_id in builtin:
            raise WorldError("error.codex.typeBuiltIn", name=name)
        fields = []
        seen = set()
        for f in data.get("fields", []):
            fname = slug(str(f.get("label") or f.get("name") or "")).replace("-", "_") or "field"
            while fname in seen:
                fname += "_2"
            seen.add(fname)
            kind = f.get("kind", "text")
            if kind not in FIELD_KINDS:
                raise WorldError("error.codex.fieldKind", kind=kind)
            field = {"name": fname, "kind": kind, "label": str(f.get("label") or fname), "required": False}
            if kind == "choice":
                field["options"] = [str(o) for o in f.get("options", []) if str(o).strip()]
            fields.append(field)
        if not fields or fields[0]["kind"] != "text":
            fields.insert(0, {"name": "name", "kind": "text", "label": "Name", "required": True})
        fields[0]["required"] = True
        definition = {"id": type_id, "name": name, "icon": "entry", "title_field": fields[0]["name"], "fields": fields}
        self.adventure.files[f"{TYPES_PREFIX}{type_id}.json"] = _dump(definition)
        return definition

    # --- entries (F3) -------------------------------------------------------------
    def entry_files(self) -> List[str]:
        return [n for n in self.adventure.files_in(ENTRY_PREFIX)
                if n.count("/") == 1 and n.endswith(".json") and ENTRY_ID.match(n[len(ENTRY_PREFIX):-5])]

    def entries(self) -> Dict[str, dict]:
        types = self.types()
        result = {}
        for name in self.entry_files():
            try:
                e = _load_json(self.adventure.files[name])
            except ValueError:
                continue
            result[e["id"]] = self._complete(e, types)
        return dict(sorted(result.items(), key=lambda kv: kv[1]["title"].lower()))

    def _complete(self, e: dict, types: Dict[str, dict]) -> dict:
        t = types.get(e.get("type"), {})
        fields = e.get("fields", {}) or {}
        title = str(fields.get(t.get("title_field", "name"), "") or "")
        return {
            "id": e["id"], "type": e.get("type"), "fields": fields, "title": title,
            "folder": e.get("folder", "") or "", "tags": list(e.get("tags", []) or []),
        }

    def entry(self, entry_id: str) -> Optional[dict]:
        data = self.adventure.files.get(f"{ENTRY_PREFIX}{entry_id}.json")
        if data is None:
            return None
        return self._complete(_load_json(data), self.types())

    def new_entry_id(self, title: str) -> str:
        base = "c-" + slug(title)
        candidate, n = base, 2
        while f"{ENTRY_PREFIX}{candidate}.json" in self.adventure.files:
            candidate = f"{base}-{n}"
            n += 1
        return candidate

    def create_entry(self, type_id: str, title: str, fields: Optional[dict] = None, folder: str = "",
                     tags: Optional[List[str]] = None) -> dict:
        types = self.types()
        if type_id not in types:
            raise WorldError("error.codex.unknownType", type=type_id)
        title = (title or "").strip()
        if not title:
            raise WorldError("error.codex.titleRequired")
        t = types[type_id]
        data = dict(fields or {})
        data[t["title_field"]] = title
        entry = {"id": self.new_entry_id(title), "type": type_id, "fields": self._clean_fields(t, data),
                 "folder": folder.strip("/ "), "tags": sorted(set(tags or []))}
        self.adventure.files[f"{ENTRY_PREFIX}{entry['id']}.json"] = _dump(entry)
        return self._complete(entry, types)

    def _clean_fields(self, t: dict, data: dict) -> dict:
        clean = {}
        for f in t["fields"]:
            value = data.get(f["name"])
            if value in (None, "", []):
                continue
            kind = f.get("kind")
            if kind == "number":
                try:
                    value = int(value)
                except (TypeError, ValueError):
                    continue
            elif kind == "link":
                value = [v for v in (value if isinstance(value, list) else [value]) if isinstance(v, str) and v]
                if not value:
                    continue
            elif kind == "rich":
                value = str(value)
            else:
                value = str(value)
            clean[f["name"]] = value
        return clean

    def update_entry(self, entry_id: str, data: dict) -> dict:
        """Rename and edit (F3.5): the ID never changes, so every reference
        follows and the adventure text stays the same (T-WORLD-01)."""
        name = f"{ENTRY_PREFIX}{entry_id}.json"
        if name not in self.adventure.files:
            raise WorldError("error.codex.noEntry", entry=entry_id)
        e = _load_json(self.adventure.files[name])
        types = self.types()
        t = types.get(e["type"])
        if "fields" in data and t:
            fields = {**e.get("fields", {}), **data["fields"]}
            title = fields.get(t["title_field"])
            if not str(title or "").strip():
                raise WorldError("error.codex.titleRequired")
            e["fields"] = self._clean_fields(t, fields)
        if "folder" in data:
            e["folder"] = str(data["folder"] or "").strip("/ ")
        if "tags" in data:
            e["tags"] = sorted({str(x).strip() for x in data["tags"] if str(x).strip()})
        self.adventure.files[name] = _dump(e)
        return self._complete(e, types)

    def delete_entry(self, entry_id: str) -> None:
        """F3.8: refused while the entry is still referenced; the refusal
        lists the places that use it (T-WORLD-02)."""
        places = self.usages(entry_id)
        if places:
            raise WorldError("error.codex.inUse", entry=entry_id, places=places)
        self.adventure.files.pop(f"{ENTRY_PREFIX}{entry_id}.json", None)
        self._drop_chart_position(entry_id)

    # --- where entries are used (F3.6, F3.8) ---------------------------------------
    def _chapter_docs(self):
        for index, chapter in enumerate(self.adventure.chapters):
            yield index, chapter, source.parse(self.adventure.chapter_text(chapter), self.kinds)

    def references_in_block(self, block: dict) -> List[Tuple[str, str]]:
        """(entry id, how) for every codex reference written in one block,
        not counting the blocks inside it."""
        refs: List[Tuple[str, str]] = []
        btype = block["type"]
        texts = []
        if btype in ("heading", "paragraph"):
            texts.append(block.get("text", ""))
        elif btype == "table":
            for row in [block.get("header", []), *block.get("rows", [])]:
                texts.extend(row)
        elif btype == "element":
            definition = self.kinds.get(block["kind"], {})
            for f in definition.get("fields", []):
                value = (block.get("fields") or {}).get(f["name"])
                if f.get("kind") == "codex" and isinstance(value, str) and value:
                    refs.append((value, block["kind"] + "." + f["name"]))
                elif f.get("kind") == "codex-list" and isinstance(value, list):
                    refs.extend((v, block["kind"] + "." + f["name"]) for v in value)
                elif f.get("kind") == "rich" and isinstance(value, str):
                    texts.append(value)
            if isinstance(block.get("body"), str):
                texts.append(block["body"])
        for text in texts:
            refs.extend((m.group(2), m.group(1)) for m in INLINE_REF.finditer(text or ""))
        return refs

    def text_references(self) -> List[dict]:
        """Every codex reference in the text, with chapter, line and the
        scene it is in."""
        found = []

        def walk(blocks, chapter, scene):
            for block in blocks:
                here_scene = scene
                if block["type"] == "element" and block["kind"] == "scene":
                    here_scene = (block.get("fields") or {}).get("title", "")
                for entry_id, how in self.references_in_block(block):
                    found.append({"entry": entry_id, "how": how, "chapter": chapter, "line": block.get("line"),
                                  "scene": here_scene})
                if isinstance(block.get("body"), dict):
                    walk(block["body"]["blocks"], chapter, here_scene)

        for index, _chapter, doc in self._chapter_docs():
            walk(doc["blocks"], index, None)
        return found

    def usages(self, entry_id: str) -> List[dict]:
        places = [{"where": "text", "chapter": r["chapter"], "line": r["line"], "scene": r["scene"], "how": r["how"]}
                  for r in self.text_references() if r["entry"] == entry_id]
        for other in self.entries().values():
            if other["id"] == entry_id:
                continue
            if entry_id in self._links_of(other) or any(m.group(2) == entry_id for v in other["fields"].values()
                                                        if isinstance(v, str) for m in INLINE_REF.finditer(v)):
                places.append({"where": "entry", "entry": other["id"], "title": other["title"]})
        for m in self.maps().values():
            for layer in m.get("layers", []):
                for item in layer.get("items", []):
                    if item.get("entry") == entry_id:
                        places.append({"where": "map", "map": m["id"], "title": m.get("title", "")})
        return places

    def _links_of(self, entry: dict) -> List[str]:
        t = self.types().get(entry["type"], {})
        links = []
        for f in t.get("fields", []):
            if f.get("kind") in ("link", "codex-list"):
                value = entry["fields"].get(f["name"])
                links.extend(value if isinstance(value, list) else [value] if value else [])
        return links

    def backlinks(self, entry_id: str) -> List[dict]:
        """F3.6: entries that link to this one, computed, never stored."""
        return [{"id": e["id"], "title": e["title"], "type": e["type"]}
                for e in self.entries().values() if entry_id in self._links_of(e)]

    def scene_entries(self, chapter_index: int, line: Optional[int]) -> dict:
        """The "In this scene" panel (F3.6): the scene at a line and every
        codex entry it refers to, in order of first use."""
        if not (0 <= chapter_index < len(self.adventure.chapters)) or line is None:
            return {"scene": None, "entries": []}
        doc = source.parse(self.adventure.chapter_text(self.adventure.chapters[chapter_index]), self.kinds)
        scenes = [b for b in source._walk(doc["blocks"]) if b["type"] == "element" and b["kind"] == "scene"]
        current = None
        for scene in scenes:
            if scene.get("line", 0) <= line:
                current = scene
        if current is None:
            return {"scene": None, "entries": []}
        ids: List[str] = []
        for block in source._walk([current]):
            for entry_id, _how in self.references_in_block(block):
                if entry_id not in ids:
                    ids.append(entry_id)
        entries = self.entries()
        return {
            "scene": (current.get("fields") or {}).get("title", ""),
            "entries": [{"id": i, "title": entries[i]["title"], "type": entries[i]["type"]} for i in ids if i in entries],
            "missing": [i for i in ids if i not in entries],
        }

    def broken_references(self) -> List[dict]:
        entries = self.entries()
        maps = self.maps()
        broken = [r for r in self.text_references() if r["entry"] not in entries]
        for _index, chapter, doc in self._chapter_docs():
            for block in source._walk(doc["blocks"]):
                if block["type"] == "element" and block["kind"] == "map":
                    map_id = (block.get("fields") or {}).get("map")
                    if map_id and map_id not in maps:
                        broken.append({"entry": map_id, "chapter": chapter, "line": block.get("line"), "how": "map"})
        return broken

    # --- maps (F5) --------------------------------------------------------------------
    def maps(self) -> Dict[str, dict]:
        result = {}
        for name in self.adventure.files_in(MAPS_PREFIX):
            if name.endswith("/map.json") and name.count("/") == 2:
                try:
                    m = _load_json(self.adventure.files[name])
                except ValueError:
                    continue
                result[m["id"]] = m
        return dict(sorted(result.items(), key=lambda kv: kv[1].get("title", "").lower()))

    def create_map(self, title: str, image_name: str, data: bytes) -> dict:
        """F5.1, F5.7: a map on a JPEG or PNG base image; any other file is
        refused with a plain explanation."""
        title = (title or "").strip()
        if not title:
            raise WorldError("error.map.titleRequired")
        info = image_size(data)
        if info is None:
            raise WorldError("error.map.notJpegPng", file=image_name)
        kind, width, height = info
        base, n = "m-" + slug(title), 2
        map_id = base
        while f"{MAPS_PREFIX}{map_id}/map.json" in self.adventure.files:
            map_id, n = f"{base}-{n}", n + 1
        image = f"{MAPS_PREFIX}{map_id}/base.{kind}"
        self.adventure.files[image] = data
        m = {"id": map_id, "title": title, "image": image, "width": width, "height": height, "description": "",
             "layers": [{"id": "l-1", "name": self.labels.get("map.layer.default", "Layer 1"), "show_in_handout": True,
                         "items": []}]}
        self.adventure.files[f"{MAPS_PREFIX}{map_id}/map.json"] = _dump(m)
        return m

    def update_map(self, data: dict) -> dict:
        map_id = data.get("id", "")
        name = f"{MAPS_PREFIX}{map_id}/map.json"
        if name not in self.adventure.files:
            raise WorldError("error.map.noMap", map=map_id)
        m = _load_json(self.adventure.files[name])
        if "title" in data:
            if not str(data["title"]).strip():
                raise WorldError("error.map.titleRequired")
            m["title"] = str(data["title"]).strip()
        if "description" in data:
            m["description"] = str(data["description"] or "")
        if "layers" in data:
            m["layers"] = [self._clean_layer(layer, i) for i, layer in enumerate(data["layers"])]
        self.adventure.files[name] = _dump(m)
        return m

    def _clean_layer(self, layer: dict, index: int) -> dict:
        items = []
        for j, item in enumerate(layer.get("items", [])):
            itype = item.get("type")
            if itype not in ITEM_TYPES:
                continue
            clean = {"id": str(item.get("id") or f"i-{index + 1}-{j + 1}"), "type": itype,
                     "text": str(item.get("text", "") or "")}
            if itype == "line":
                # F5 (M6 part C3): a line joins two pins, or runs through points.
                if item.get("from") and item.get("to"):
                    clean["from"], clean["to"] = str(item["from"]), str(item["to"])
                else:
                    points = [[_unit(p[0]), _unit(p[1])] for p in item.get("points", []) if len(p) == 2]
                    if len(points) < 2:
                        raise WorldError("error.map.lineTooFew")
                    clean["points"] = points
                if item.get("style") in LINE_STYLES and item.get("style") != "solid":
                    clean["style"] = item["style"]
                items.append(clean)
                continue
            if itype == "area":
                points = [[_unit(p[0]), _unit(p[1])] for p in item.get("points", []) if len(p) == 2]
                if len(points) < AREA_MIN:
                    raise WorldError("error.map.areaTooFew", minimum=AREA_MIN)
                if len(points) > AREA_MAX:
                    raise WorldError("error.map.areaTooMany", maximum=AREA_MAX)
                clean["points"] = points
            else:
                clean["x"], clean["y"] = _unit(item.get("x", 0.5)), _unit(item.get("y", 0.5))
            if itype == "pin" and item.get("entry"):
                clean["entry"] = str(item["entry"])
            if itype == "pin":
                # F5 (M6 part C3): the number printed on the pin, and a note for the key.
                try:
                    number = int(item.get("number") or 0)
                except (TypeError, ValueError):
                    number = 0
                if number > 0:
                    clean["number"] = number
                if str(item.get("note", "") or "").strip():
                    clean["note"] = str(item["note"])
            items.append(clean)
        return {"id": str(layer.get("id") or f"l-{index + 1}"), "name": str(layer.get("name", "") or f"{index + 1}"),
                "show_in_handout": bool(layer.get("show_in_handout")), "items": items}

    def delete_map(self, map_id: str) -> None:
        used = [b for _i, _c, doc in self._chapter_docs() for b in source._walk(doc["blocks"])
                if b["type"] == "element" and b["kind"] == "map" and (b.get("fields") or {}).get("map") == map_id]
        if used:
            raise WorldError("error.map.inUse", lines=", ".join(str(b.get("line")) for b in used))
        for name in [n for n in self.adventure.files if n.startswith(f"{MAPS_PREFIX}{map_id}/")]:
            del self.adventure.files[name]

    # --- relationship chart (F3.9) ---------------------------------------------------
    def chart(self) -> dict:
        """Nodes are the entries that link or are linked; edges are the links.
        Saved positions come from the adventure; entries without one get a
        position on a circle, the same on every build (F7.8)."""
        entries = self.entries()
        edges, linked = [], set()
        for e in entries.values():
            for target in self._links_of(e):
                if target in entries and target != e["id"]:
                    pair = (e["id"], target)
                    if pair not in edges and (target, e["id"]) not in edges:
                        edges.append(pair)
                    linked.update(pair)
        stored = {}
        if CHART_FILE in self.adventure.files:
            stored = _load_json(self.adventure.files[CHART_FILE]).get("positions", {})
        ids = [i for i in entries if i in linked]
        import math
        nodes = []
        for k, entry_id in enumerate(ids):
            if entry_id in stored:
                x, y = stored[entry_id]
            else:
                angle = 2 * math.pi * k / max(1, len(ids)) - math.pi / 2
                x, y = 0.5 + 0.4 * math.cos(angle), 0.5 + 0.4 * math.sin(angle)
            e = entries[entry_id]
            nodes.append({"id": entry_id, "title": e["title"], "type": e["type"], "x": round(_unit(x), 4), "y": round(_unit(y), 4)})
        return {"nodes": nodes, "edges": [{"from": a, "to": b} for a, b in edges]}

    def set_chart_positions(self, positions: Dict[str, List[float]]) -> None:
        stored = {}
        if CHART_FILE in self.adventure.files:
            stored = _load_json(self.adventure.files[CHART_FILE]).get("positions", {})
        for entry_id, (x, y) in positions.items():
            stored[entry_id] = [round(_unit(x), 4), round(_unit(y), 4)]
        self.adventure.files[CHART_FILE] = _dump({"positions": dict(sorted(stored.items()))})

    def _drop_chart_position(self, entry_id: str) -> None:
        if CHART_FILE in self.adventure.files:
            data = _load_json(self.adventure.files[CHART_FILE])
            if data.get("positions", {}).pop(entry_id, None) is not None:
                self.adventure.files[CHART_FILE] = _dump(data)

    # --- handouts (F6) --------------------------------------------------------------
    def handouts(self) -> List[dict]:
        """Every handout in adventure order, numbered #1, #2 and so on (F6.2):
        handout elements and maps marked "Handout also" (F5.5)."""
        maps = self.maps()
        result = []
        for index, chapter, doc in self._chapter_docs():
            for block in source._walk(doc["blocks"]):
                if block["type"] != "element":
                    continue
                fields = block.get("fields") or {}
                if block["kind"] == "handout":
                    title = fields.get("title", "")
                elif block["kind"] == "map" and fields.get("handout-also"):
                    title = maps.get(fields.get("map"), {}).get("title", "")
                else:
                    continue
                result.append({"number": len(result) + 1, "kind": block["kind"], "title": title,
                               "chapter": index, "line": block.get("line"),
                               "source": source.block_text(block, self.kinds)})
        return result

    # --- F3.12: upgrade M2 text fields to codex links -----------------------------------
    UPGRADES = (
        # element, old text field, new field, codex type (None: the author picks), split on commas
        ("scene", "location", "place", "place", False),
        ("scene", "present", "people", "person", True),
        ("person", "linked-to", "links", None, True),
        ("handout", "written-by", "writer", "person", False),
    )

    def upgrade_candidates(self) -> List[dict]:
        """Every plain-text value the codex can now hold as a link, with a
        proposed match: an existing entry with the same name, or a new entry
        of the matching type. Nothing changes until the author confirms."""
        entries = self.entries()
        by_title: Dict[str, List[dict]] = {}
        for e in entries.values():
            by_title.setdefault(e["title"].strip().lower(), []).append(e)
        found = []
        for index, chapter, doc in self._chapter_docs():
            for path, block in _walk_paths(doc["blocks"]):
                if block["type"] != "element":
                    continue
                for element, old, new, type_id, split in self.UPGRADES:
                    if block["kind"] != element or old not in (block.get("fields") or {}):
                        continue
                    if new not in {f["name"] for f in self.kinds.get(element, {}).get("fields", [])}:
                        continue
                    raw = source.inline_to_plain(str(block["fields"][old]))
                    values = [v.strip() for v in raw.split(",")] if split else [raw.strip()]
                    for i, value in enumerate(v for v in values if v):
                        matches = [e for e in by_title.get(value.lower(), []) if type_id is None or e["type"] == type_id]
                        match = matches[0] if matches else None
                        found.append({
                            "key": f"{index}:{'.'.join(map(str, path))}:{old}:{i}",
                            "chapter": index, "line": block.get("line"), "element": element, "field": old,
                            "value": value, "type": match["type"] if match else (type_id or "place"),
                            "typeFixed": type_id is not None,
                            "match": match["id"] if match else None,
                            "matchTitle": match["title"] if match else None,
                        })
        return found

    def apply_upgrade(self, choices: List[dict]) -> dict:
        """Turn the confirmed values into links in one step. Declined values
        stay text and print exactly as before."""
        wanted = {c["key"]: c for c in choices if c.get("accept")}
        candidates = [c for c in self.upgrade_candidates() if c["key"] in wanted]
        created: Dict[Tuple[str, str], str] = {}
        linked = 0
        by_block: Dict[Tuple[int, str, str], List[dict]] = {}
        for c in candidates:
            chosen = wanted[c["key"]]
            type_id = chosen.get("type") if not c["typeFixed"] and chosen.get("type") else c["type"]
            entry_id = c["match"] if c["match"] and (c["typeFixed"] or type_id == c["type"]) else None
            if entry_id is None:
                key = (c["value"].lower(), type_id)
                if key not in created:
                    created[key] = self.create_entry(type_id, c["value"])["id"]
                entry_id = created[key]
            chapter, path, field, _i = c["key"].split(":")
            by_block.setdefault((int(chapter), path, field), []).append({**c, "entry": entry_id})
        for chapter_index in sorted({k[0] for k in by_block}):
            chapter = self.adventure.chapters[chapter_index]
            doc = source.parse(self.adventure.chapter_text(chapter), self.kinds)
            for (ci, path, field), items in by_block.items():
                if ci != chapter_index:
                    continue
                chain = _block_chain(doc, [int(p) for p in path.split(".")])
                block = chain[-1]
                element, old, new, _t, split = next(u for u in self.UPGRADES if u[0] == block["kind"] and u[1] == field)
                raw = source.inline_to_plain(str(block["fields"][old]))
                values = [v.strip() for v in raw.split(",")] if split else [raw.strip()]
                values = [v for v in values if v]
                accepted = {int(it["key"].split(":")[3]): it["entry"] for it in items}
                ids = [accepted[i] for i in range(len(values)) if i in accepted]
                rest = [v for i, v in enumerate(values) if i not in accepted]
                kind = next(f["kind"] for f in self.kinds[element]["fields"] if f["name"] == new)
                current = block["fields"].get(new)
                if kind == "codex-list":
                    block["fields"][new] = list(dict.fromkeys([*(current or []), *ids]))
                elif ids:
                    block["fields"][new] = ids[0]
                if rest:
                    block["fields"][old] = source.escape_inline(", ".join(rest))
                else:
                    block["fields"].pop(old, None)
                linked += len(ids)
                for b in chain:
                    source.mark_changed(b)
                block.pop("head_raw", None)
            self.adventure.set_chapter_text(chapter, source.serialize(doc, self.kinds))
        return {"linked": linked, "created": len(created)}

    # --- data for the build (3.3) ------------------------------------------------------
    def build_data(self, mode: str, settings: dict, handwriting: Iterable[str] = ()) -> dict:
        types = self.types()
        entries = self.entries()
        maps = {}
        for map_id, m in self.maps().items():
            numbers = pin_numbers(m)
            pins = {item.get("id"): item for layer in m.get("layers", []) for item in layer.get("items", [])
                    if item.get("type") == "pin"}
            layers = []
            for layer in m.get("layers", []):
                items = []
                for item in layer.get("items", []):
                    item = dict(item)
                    if item.get("entry") in entries:
                        item["title"] = entries[item["entry"]]["title"]
                    if item.get("type") == "pin":
                        item["number"] = numbers[item["id"]]
                    if item.get("type") == "line" and "from" in item:
                        # A line between pins follows the pins (M6 part C3).
                        ends = [pins.get(item["from"]), pins.get(item["to"])]
                        if None in ends:
                            continue
                        item["points"] = [[e["x"], e["y"]] for e in ends]
                    items.append(item)
                layers.append({**layer, "items": items})
            width, height = m.get("width") or 1, m.get("height") or 1
            maps[map_id] = {"id": map_id, "title": m.get("title", ""), "image": "/" + m["image"],
                            "aspect": height / width, "layers": layers,
                            # F17.3 (M5): the description screen readers read.
                            "description": m.get("description", "") or ""}
        end = (settings or {}).get("end_matter", {}) or {}
        return {
            "mode": mode,
            "entries": {i: {"id": i, "type": e["type"], "title": e["title"], "fields": e["fields"]} for i, e in entries.items()},
            "types": {i: {"name": t["name"], "card": t["card"], "title_field": t["title_field"],
                          "fields": [{"name": f["name"], "kind": f.get("kind"), "label": self.labels.get(f.get("label", ""), f.get("label", f["name"]))}
                                     for f in t["fields"]]} for i, t in types.items()},
            "maps": maps,
            "chart": self.chart(),
            "end": {"clue_overview": bool(end.get("clue_overview")), "index": bool(end.get("index"))},
            "easy_read": bool((settings or {}).get("easy_read")),
            # F7.3 (M4): the fill of the secret box, pale grey (default) or pale beige.
            "secret_fill": "beige" if (settings or {}).get("secret_fill") == "beige" else "grey",
        }


def _unit(value) -> float:
    try:
        return min(1.0, max(0.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _walk_paths(blocks, path=()):
    for i, block in enumerate(blocks):
        here = (*path, i)
        yield here, block
        if isinstance(block.get("body"), dict):
            yield from _walk_paths(block["body"]["blocks"], here)


def _block_chain(doc: dict, path: List[int]) -> List[dict]:
    chain, blocks = [], doc["blocks"]
    for i in path:
        block = blocks[i]
        chain.append(block)
        blocks = block["body"]["blocks"] if isinstance(block.get("body"), dict) else []
    return chain
