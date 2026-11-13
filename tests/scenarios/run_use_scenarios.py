"""Test Plan group USE: T-USE-01 and T-USE-02, driven through the real window.

Run:  python tests/scenarios/run_use_scenarios.py [output-folder]

The script acts like a Game Master: it clicks buttons and menu items, types
and pastes into the editor, and records what happened. It is not a pass/fail
test suite; it prints a log, saves screenshots and PDFs, and writes
findings.json for the test report. Findings are judged by the person or
agent running it and recorded in the report.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "scenario-output").resolve()
OUT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("SCRIPTORUM_HOME", str(OUT / "home"))
os.environ.setdefault("SCRIPTORUM_DOCUMENTS", str(OUT / "documents"))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from scriptorum.app.main import MainWindow  # noqa: E402
from scriptorum.core.session import Session  # noqa: E402

from tests.drag_js import HELPERS as DRAG_HELPERS  # noqa: E402

HELPERS = r"""
window.__u = {
  q: (sel, i = 0) => document.querySelectorAll(sel)[i < 0 ? document.querySelectorAll(sel).length + i : i],
  count: (sel) => document.querySelectorAll(sel).length,
  click: (sel, i = 0) => { const el = window.__u.q(sel, i); if (!el) return false; el.click(); return true; },
  focus: (sel, i = 0) => { const el = window.__u.q(sel, i); if (!el) return false; el.focus(); return true; },
  // Type at the caret, as a keyboard would.
  type: (sel, i, text) => {
    const el = window.__u.q(sel, i); if (!el) return false; el.focus();
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      el.value += text; el.dispatchEvent(new Event('input', {bubbles: true}));
    } else {
      const r = document.createRange(); r.selectNodeContents(el); r.collapse(false);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r);
      document.execCommand('insertText', false, text);
    }
    return true;
  },
  // Paste plain text from the clipboard.
  paste: (sel, i, text) => {
    const el = window.__u.q(sel, i); if (!el) return false; el.focus();
    const dt = new DataTransfer(); dt.setData('text/plain', text);
    const ev = new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true});
    const handled = !el.dispatchEvent(ev);
    if (!handled && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) {
      el.value += text; el.dispatchEvent(new Event('input', {bubbles: true}));
    }
    return true;
  },
  select: (sel, i, value) => { const el = window.__u.q(sel, i); el.value = value; el.dispatchEvent(new Event('change', {bubbles: true})); return true; },
  menuItems: () => [...document.querySelectorAll('#menu-popup .menu-item, #menu-popup .menu-heading')].map(b => (b.disabled ? '(off) ' : '') + b.textContent),
  pick: (label) => { const b = [...document.querySelectorAll('#menu-popup .menu-item')].find(x => x.firstChild.textContent === label && !x.disabled); if (!b) return false; b.click(); return true; },
  menu: (name) => { const b = [...document.querySelectorAll('#menubar .menu-btn')].find(x => x.textContent === name); b.click(); return window.__u.menuItems(); },
  // Right-click a block whose text contains the words, as a person would.
  rightClick: (words) => {
    const blocks = [...document.querySelectorAll('section.blk')].filter(s => s.textContent.includes(words));
    const s = blocks.pop(); if (!s) return null;
    const box = s.querySelector('.rich, .heading-edit, input') || s;
    const r = box.getBoundingClientRect();
    box.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: r.left + 4, clientY: r.top + 4}));
    return window.__u.menuItems();
  },
  key: (key, mods) => { const el = document.activeElement; el.dispatchEvent(new KeyboardEvent('keydown', Object.assign({key, bubbles: true, cancelable: true}, mods || {}))); return true; },
};
true
"""


class Scenario:
    def __init__(self, name: str, window: MainWindow):
        self.name = name
        self.w = window
        self.steps = 0
        self.log = []
        self.findings = []
        self.started = time.monotonic()

    # --- driving -----------------------------------------------------------
    def wait(self, ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def js(self, code: str):
        wrapped = f"JSON.stringify(eval({json.dumps(code)}))"
        box = {}
        loop = QEventLoop()
        self.w.page.runJavaScript(wrapped, 0, lambda r: (box.setdefault("r", r), loop.quit()))
        QTimer.singleShot(10000, loop.quit)
        loop.exec()
        r = box.get("r")
        return json.loads(r) if isinstance(r, str) and r else None

    def act(self, description: str, code: str, settle: int = 250):
        """One thing the Game Master does."""
        self.steps += 1
        result = self.js(code)
        self.wait(settle)
        self.log.append(f"{self.steps:>3}. {description} -> {json.dumps(result, ensure_ascii=False)[:160]}")
        return result

    def flush(self) -> None:
        self.js("window.__done=false; window.__scriptorum.flush().then(()=>window.__done=true); null")
        for _ in range(100):
            if self.js("window.__done"):
                break
            self.wait(50)
        self.wait(700)  # let the 0.3 s build finish

    def state(self) -> dict:
        return self.js("window.__scriptorum.state()")

    def shot(self, name: str) -> None:
        self.w.grab().save(str(OUT / f"{self.name}-{name}.png"))

    def note(self, kind: str, text: str, milestone: str) -> None:
        self.findings.append({"kind": kind, "text": text, "milestone": milestone})

    def check(self, label: str, ok: bool) -> bool:
        self.log.append(f"     check: {label}: {'yes' if ok else 'NO'}")
        return ok

    def summary(self) -> dict:
        return {
            "scenario": self.name,
            "steps": self.steps,
            "seconds_of_automation": round(time.monotonic() - self.started, 1),
            "log": self.log,
            "findings": self.findings,
        }


def new_adventure(s: Scenario, title: str, game_system: str = "") -> None:
    s.act("File menu", "window.__u.menu('File')")
    s.act("File → New adventure…", "window.__u.pick('New adventure…')", 600)
    # M5 (F8): Plain is offered first and preselected.
    chosen = s.js("[document.getElementById('new-system').selectedOptions[0].textContent, document.getElementById('new-theme').selectedOptions[0].textContent]")
    s.check("Plain game system and Plain theme preselected", chosen == ["Plain", "Plain"])
    if game_system:
        s.act(f"Game system: {game_system}", f"""(() => {{ const g = document.getElementById('new-system');
            g.value = [...g.options].find(o => o.textContent === {json.dumps(game_system)}).value; g.onchange(); return true; }})()""")
    s.act("Type the title", f"window.__u.type('#new-title', 0, {json.dumps(title)})")
    s.act("Create", "window.__u.click('#new-create')", 1500)


def insert_from_menu(s: Scenario, label: str) -> list:
    # M4: the Insert menu keeps the full list (the toolbar has insert groups).
    items = s.act("Insert menu", "window.__u.menu('Insert')")
    s.act(f"Insert → {label}", f"window.__u.pick({json.dumps(label)})", 400)
    # M6 part C4: Person and Creature first offer the codex; a one-off
    # character is written as a loose card, as before.
    if label in ("Person", "Creature") and s.js("document.getElementById('pick-dialog').open"):
        s.act("Picker → Write a loose card here", "window.__u.click('#pick-loose')", 400)
    return items


# ---------------------------------------------------------------------------
# T-USE-01: quick design of an existing adventure

def use_01(window: MainWindow) -> dict:
    s = Scenario("T-USE-01", window)
    text = (ROOT / "tests" / "samples" / "use-existing-adventure.txt").read_text("utf-8")
    parts = {p.split("\n", 1)[0]: p for p in text.split("\n\n")}
    para = lambda key: " ".join(parts[key].split("\n")) if key in parts else key  # noqa: E731

    new_adventure(s, "The Bell of Skärvik")
    st = s.state()
    s.check("adventure open", st["info"]["hasDocument"])
    # M4 (F7.9): a new adventure starts with its first scene, no title line.
    s.check("starts with one scene and no title line", [o["kind"] for o in st["outline"]] == ["scene"])

    # The GM wants the act heading "Act one: The silent bell". Is there a way to add a heading?
    s.act("Click into the scene title", "window.__u.focus('.el-scene > .el-fields .field-title input')")
    items = s.act("Toolbar → Structure", "window.__u.click('#tb-group-structure'); window.__u.menuItems()")
    if not s.check("Structure offers an act heading", any("Act heading" in i for i in items)):
        s.note("missing feature", "No way to insert an act heading in Visual mode.", "M2 (F4.2/F4.4)")
    s.act("Structure → Act heading", "window.__u.pick('Act heading')", 400)
    s.act("Type the act heading", "const h=[...document.querySelectorAll('.heading-edit')].pop(); h.focus(); document.execCommand('insertText', false, 'Act one: The silent bell'); true")
    s.act("Move it above the scene (Alt+↑)", "window.__u.key('ArrowUp', {altKey: true})", 400)
    s.flush()
    if not s.check("the act heading comes first", (s.state()["text"] or "").startswith("= Act one: The silent bell")):
        s.note("friction", "An act heading inserted from the toolbar lands after the scene and must be moved up.", "M5")

    # Scene 1 header
    s.act("Scene title", "const i=window.__u.q('.el-scene > .el-fields .field-title input'); i.focus(); i.value=''; i.dispatchEvent(new Event('input',{bubbles:true})); true")
    s.act("Type scene title", "window.__u.type('.el-scene > .el-fields .field-title input', 0, 'The harbour')")
    # From M3 the location and the people are codex entries (F3.5): a pasted
    # name becomes a new entry and is linked.
    s.act("Paste location", "window.__u.paste('.el-scene .field-place input', 0, 'Skärvik harbour, early morning')", 900)
    s.act("Paste people present", "window.__u.paste('.el-scene .field-people input', 0, 'Harbour master Lovisa Berg')", 900)
    loc = s.js("[...document.querySelectorAll('.el-scene .field-place .codex-chip-name')].map(b => b.textContent).join()")
    if not s.check("paste into a field works", loc == "Skärvik harbour, early morning"):
        s.note("bug", "Pasting into a scene field did not insert the text.", "M1")

    # Read-aloud inside the scene
    s.act("Focus the scene title", "window.__u.focus('.el-scene > .el-fields .field-title input')")
    insert_from_menu(s, "Read-aloud")
    s.act("Paste the read-aloud text", "window.__u.paste('.el-read-aloud .el-body', 0, " + json.dumps(" ".join(parts["READ ALOUD:"].split("\n")[1:])) + ")")
    s.check("read-aloud is inside scene 1", s.js("!!document.querySelector('.el-scene .el-read-aloud')"))

    # Plain paragraph after the read-aloud
    insert_from_menu(s, "Paragraph")
    body = next(p for p in parts.values() if p.startswith("The fishing boats"))
    s.act("Paste the paragraph", "window.__u.paste('.blk-paragraph .para', -1, " + json.dumps(" ".join(body.split("\n"))) + ")")

    # Secret
    insert_from_menu(s, "Information")
    s.act("Paste the secret", "window.__u.paste('.el-information .el-body', -1, " + json.dumps(parts["SECRET: The bell belongs to the Hoppet, which sank with all hands forty years ago."].replace("SECRET: ", "")) + ")")
    s.check("Information defaults to Secret", s.js("window.__u.q('.el-information .variant-select', -1).value") == "secret")

    # Person with two Information lines
    insert_from_menu(s, "Person")
    s.act("Person name", "window.__u.paste('.el-person .field-name input', 0, 'Lovisa Berg')")
    s.act("Mood", "window.__u.paste('.el-person .field-mood input', 0, 'Tired and stubborn')")
    s.act("Description", "window.__u.paste('.el-person .field-description .rich', 0, 'Harbour master for twenty years. Lost a brother at sea.')")
    s.act("Linked to", "window.__u.paste('.el-person .field-linked-to input', 0, 'The harbour, the Hoppet')")
    s.act("Add information to the person", "window.__u.click('.el-person .add-btn')", 400)
    s.act("Type: public", "window.__u.select('.el-person .el-information .variant-select', 0, 'public')")
    s.act("Paste what she knows (public)", "window.__u.paste('.el-person .el-information .el-body', 0, 'No boat has gone out since Sunday.')")
    s.act("Add a second information line", "window.__u.click('.el-person .add-btn')", 400)
    s.act("Paste what she knows (secret)", "window.__u.paste('.el-person .el-information .el-body', 1, \"She heard her brother's voice in the fog last night.\")")
    s.check("person card has two information lines", s.js("window.__u.count('.el-person .el-information')") == 2)

    # Paragraph after the person
    s.act("Focus the person name", "window.__u.focus('.el-person .field-name input')")
    insert_from_menu(s, "Paragraph")
    s.act("Paste the closing paragraph", "window.__u.paste('.blk-paragraph .para', -1, " + json.dumps(" ".join(parts[next(k for k in parts if k.startswith('If the characters'))].split("\n"))) + ")")
    s.flush()
    last_scene_children = s.js("[...window.__u.q('.el-scene').querySelectorAll(':scope > .el-children > .blk-list > .blk')].map(b => b.className)")
    s.check("closing paragraph landed inside scene 1 after the person", bool(last_scene_children) and "blk-paragraph" in last_scene_children[-1])

    # Scene 2
    insert_from_menu(s, "Scene")
    s.check("a second scene exists", s.js("window.__u.count('.el-scene')") == 2)
    s.act("Scene 2 title", "window.__u.type('.el-scene > .el-fields .field-title input', 1, 'The chapel')")
    s.act("Scene 2 location", "window.__u.paste('.el-scene .field-location input', 1, \"The fishermen's chapel on the hill\")")
    s.act("Scene 2 people", "window.__u.paste('.el-scene .field-present input', 1, 'Sexton Nils Ek')")
    s.act("Focus scene 2 title", "window.__u.focus('.el-scene > .el-fields .field-title input', 1)")
    insert_from_menu(s, "Information")
    s.act("Type: hint", "window.__u.select('.el-information .variant-select', -1, 'hint')")
    s.act("Paste the hint", "window.__u.paste('.el-information .el-body', -1, \"The chapel's records list the crew of the Hoppet.\")")
    insert_from_menu(s, "Paragraph")
    s.act("Paste last paragraph", "window.__u.paste('.blk-paragraph .para', -1, " + json.dumps(" ".join(parts[next(k for k in parts if k.startswith('The sexton'))].split("\n"))) + ")")
    s.flush()

    st = s.state()
    s.check("no build errors", st["errors"] == [])
    s.check("outline shows both scenes", [o["title"] for o in st["outline"] if o["kind"] == "scene"] == ["The harbour", "The chapel"])
    s.shot("visual")
    reply = json.loads(window.bridge.exportTo(str(OUT / "T-USE-01.pdf")))
    s.steps += 1
    s.log.append(f"{s.steps:>3}. Export PDF (native file dialog replaced by a fixed path) -> ok={reply.get('ok')}")
    s.check("PDF exported", bool(reply.get("ok")))
    (OUT / "T-USE-01.typ").write_text(st["text"], "utf-8")

    # Way B: paste everything as plain text, then change parts to the right type.
    new_adventure(s, "The Bell of Skärvik (pasted)")
    # The starter scene from New is not wanted: delete it with its × button.
    s.act("Delete the empty starter scene", "window.__u.q('.el-scene').closest('section.blk').querySelector(':scope > .blk-controls .icon-btn:last-child').click(); true", 500)
    s.act("Focus the title heading", "window.__u.focus('.heading-edit')")
    insert_from_menu(s, "Paragraph")
    s.act("Paste the whole adventure as plain text", "window.__u.paste('.blk-paragraph .para', -1, " + json.dumps(text) + ")", 600)
    s.flush()
    st = s.state()
    paragraphs = s.js("window.__u.count('.blk-paragraph')")
    s.check("whole text pasted", "Sexton Nils Ek" in st["text"])
    s.check("one paragraph per line straight after the paste (T-USE finding 3)", paragraphs >= 20)
    s.log.append(f"     paragraphs shown in Visual mode right after the paste: {paragraphs}")
    def convert(words: str, label: str) -> bool:
        items = s.act(f"Right-click “{words[:28]}”", f"window.__u.rightClick({json.dumps(words)})")
        if not items or not any(i == label for i in items):
            s.act("Close the menu", "document.body.click()")
            return False
        s.act(f"Convert to → {label}", f"window.__u.pick({json.dumps(label)})", 500)
        return True

    s.check("right-click offers Convert to", convert("Act one: The silent bell", "Act heading"))
    s.check("scene 1 converted", convert("Scene 1: The harbour", "Scene"))
    s.check("read-aloud converted", convert("Fog lies thick", "Read-aloud"))
    s.check("secret converted", convert("SECRET: The bell belongs", "Information"))
    s.check("person converted", convert("PERSON: Lovisa Berg", "Person"))
    s.check("scene 2 converted (it starts a new scene)", convert("Scene 2: The chapel", "Scene"))
    s.check("hint converted", convert("HINT: The chapel's records", "Information"))
    s.act("Hint type", "window.__u.select('.el-information .variant-select', -1, 'hint')")
    s.flush()
    st = s.state()
    s.check("outline shows the act and both scenes", [o["title"] for o in st["outline"]][:3] == ["THE BELL OF SKÄRVIK", "Act one: The silent bell", "Scene 1: The harbour"] or
            [o["kind"] for o in st["outline"]].count("scene") == 2)
    s.check("no build errors", st["errors"] == [])
    reply = json.loads(window.bridge.exportTo(str(OUT / "T-USE-01-pasted.pdf")))
    s.steps += 1
    s.log.append(f"{s.steps:>3}. Export PDF (second route) -> ok={reply.get('ok')}")
    s.check("PDF exported by the second route", bool(reply.get("ok")))
    (OUT / "T-USE-01-pasted.typ").write_text(s.state()["text"], "utf-8")
    s.note("friction", "After converting pasted lines, the labels typed in the original text stay in the text: a scene is titled “Scene 1: The harbour”, a person “PERSON: Lovisa Berg” and Information starts with “SECRET:”. The Location and Present lines stay as paragraphs and have to be moved into the scene's fields by hand.", "later (import, L3)")
    s.shot("pasted")
    return s.summary()


# ---------------------------------------------------------------------------
# T-USE-02: writing an adventure from the ground

def use_02(window: MainWindow) -> dict:
    s = Scenario("T-USE-02", window)
    # A Vaesen adventure: the Game Master picks Vaesen instead of Plain (M5).
    new_adventure(s, "Ljuset under isen", "Vaesen")
    s.act("Name scene 1", "const i=window.__u.q('.el-scene > .el-fields .field-title input'); i.focus(); i.select(); document.execCommand('insertText', false, 'The frozen lake'); true")
    s.act("Location", "window.__u.type('.el-scene .field-location input', 0, 'Lake Mörtsjön')")
    s.act("Focus scene 1", "window.__u.focus('.el-scene > .el-fields .field-title input')")
    insert_from_menu(s, "Read-aloud")
    s.act("Write the read-aloud", "window.__u.type('.el-read-aloud .el-body', 0, 'The ice groans under your feet. Far out, a green light pulses beneath it.')")
    insert_from_menu(s, "Paragraph")
    s.act("Write GM text with bold", "window.__u.type('.blk-paragraph .para', -1, 'The light is the ')")
    s.act("Bold on", "document.execCommand('bold'); true")
    s.act("Type bold words", "document.execCommand('insertText', false, 'lyktgubbe'); true")
    s.act("Bold off", "document.execCommand('bold'); true")
    s.act("Continue typing", "document.execCommand('insertText', false, ', luring travellers onto thin ice.'); true")

    for n, (title, place) in enumerate([("The fishing hut", "The hut on the shore"), ("The village", "Mörtby")], start=2):
        insert_from_menu(s, "Scene")
        s.act(f"Name scene {n}", f"window.__u.type('.el-scene > .el-fields .field-title input', {n - 1}, {json.dumps(title)})")
        s.act(f"Location {n}", f"window.__u.type('.el-scene .field-location input', {n - 1}, {json.dumps(place)})")
        s.act(f"Focus scene {n}", f"window.__u.focus('.el-scene > .el-fields .field-title input', {n - 1})")
        insert_from_menu(s, "Paragraph")
        s.act(f"Write scene {n} text", f"window.__u.type('.blk-paragraph .para', -1, {json.dumps('Text for ' + title.lower() + '.')})")
    s.flush()
    st = s.state()
    s.check("three scenes in order", [o["title"] for o in st["outline"] if o["kind"] == "scene"] == ["The frozen lake", "The fishing hut", "The village"])

    # A person in the village
    s.act("Focus scene 3", "window.__u.focus('.el-scene > .el-fields .field-title input', 2)")
    insert_from_menu(s, "Person")
    s.act("Name", "window.__u.type('.el-person .field-name input', 0, 'Old Märta')")
    s.act("Mood", "window.__u.type('.el-person .field-mood input', 0, 'Suspicious of strangers')")
    s.act("Add what she knows", "window.__u.click('.el-person .add-btn')", 400)
    s.act("Write it", "window.__u.type('.el-person .el-information .el-body', 0, 'Her son followed the light last winter.')")

    # Reorder: the village should come before the fishing hut, by dragging in the outline.
    # M6 part C2: Scriptorum's own dragging with the pointer (F4.13).
    s.js(DRAG_HELPERS)
    s.act("Drag “The village” above “The fishing hut” in the outline", """(() => {
        const lis = [...document.querySelectorAll('#outline li.draggable')];
        const from = lis.find(l => l.textContent.includes('The village')), to = lis.find(l => l.textContent.includes('The fishing hut'));
        const r = to.getBoundingClientRect();
        window.__drag(from, r.left + 40, r.top + 3);
        return true; })()""", 500)
    s.flush()
    st = s.state()
    order = [o["title"] for o in st["outline"] if o["kind"] == "scene"]
    s.check("village moved above the fishing hut", order == ["The frozen lake", "The village", "The fishing hut"])

    # A vaesen with its stats, a countdown that sends the GM to a scene, and dice.
    s.act("Focus scene 1", "window.__u.focus('.el-scene > .el-fields .field-title input', 0)")
    insert_from_menu(s, "Creature")
    s.act("Creature name", "window.__u.type('.el-creature .field-name input', 0, 'The lyktgubbe')")
    s.act("Type", "window.__u.type('.el-creature .field-type input', 0, 'Vaesen')")
    for stat, value in (("might", "3"), ("body-control", "4"), ("magic", "5"), ("manipulation", "4"), ("fear", "3")):
        s.act(f"Stat {stat}", f"window.__u.type('.el-creature .field-{stat} input', 0, '{value}')")
    s.act("Open the Banishment section", "[...document.querySelectorAll('.el-creature .section-open')].find(b => b.textContent.includes('Banishment')).click(); true", 400)
    s.act("Write how it is banished", "window.__u.type('.el-creature .field-banishment .rich', 0, 'Break the green glass of its lantern.')")
    s.act("Focus scene 2 (the village)", "window.__u.focus('.el-scene > .el-fields .field-title input', 1)")
    insert_from_menu(s, "Countdown")
    s.act("Countdown title", "window.__u.type('.el-countdown .field-title input', 0, 'The night of the lights')")
    s.act("First step: when", "window.__u.type('.el-countdown-step .field-when input', 0, 'Dusk')")
    s.act("First step: what happens", "window.__u.type('.el-countdown-step .el-body', 0, 'The light appears on the ice.')")
    s.act("Press Enter for the next step", "window.__u.focus('.el-countdown-step .el-body', 0); window.__u.key('Enter')", 500)
    s.act("Second step: what happens", "window.__u.type('.el-countdown-step .el-body', 1, 'A child walks out onto the lake.')")
    s.act("Second step goes to scene 1", "window.__u.select('.el-countdown-step .field-go-to select', 1, '0')")
    s.act("Focus the village text", "[...document.querySelectorAll('.blk-paragraph .para')].find(p => p.textContent.includes('village')).focus(); true")
    s.act("Ctrl+D", "window.__u.key('d', {ctrlKey: true}); window.__u.menuItems()")
    s.act("Choose Check", "window.__u.pick('Check')", 400)
    s.act("Roll", "window.__u.type('.el-check .field-roll input', -1, 'Vigilance')")
    s.act("Difficulty", "window.__u.type('.el-check .field-difficulty input', -1, 'hard')")
    s.act("What a success gives", "window.__u.type('.el-check .el-body', -1, 'They see footprints leading out onto the ice.')")
    s.flush()
    st = s.state()
    s.check("creature, countdown and check in the text", all(k in st["text"] for k in ("#creature(", "#countdown(", "#countdown-step(", "#check(")))
    s.check("the countdown step points to scene 1", 'go-to: "s-' in st["text"])
    s.check("no build errors", st["errors"] == [])

    # The title page from the adventure settings.
    s.act("File → Settings… → Adventure", "window.__u.menu('File'); window.__u.pick('Settings…')", 600)
    s.act("Adventure section", "window.__u.click('#sn-adventure')", 400)
    s.act("Subtitle", "window.__u.type('#set-subtitle', 0, 'A winter mystery')")
    s.act("Author", "window.__u.type('#set-author', 0, 'Märta Lind')")
    s.act("Done", "window.__u.click('#settings-close')", 600)

    # Revise and undo
    s.act("Revise scene 1 title", "const i=window.__u.q('.el-scene > .el-fields .field-title input'); i.focus(); i.value='The frozen lake at night'; i.dispatchEvent(new Event('input',{bubbles:true})); true")
    s.flush()
    s.act("Undo", "window.__scriptorum.undo()", 800)
    s.check("undo brought the old title back", "The frozen lake\"" in s.state()["text"])

    # Save, close, reopen, continue
    path = OUT / "ljuset.scav"
    reply = json.loads(window.bridge.saveTo(str(path)))
    s.steps += 1
    s.log.append(f"{s.steps:>3}. Save (native dialog replaced by a fixed path) -> ok={reply.get('ok')}")
    before = s.state()["text"]
    new_adventure(s, "Something else")  # stands in for closing the window
    reply = json.loads(window.bridge.openPath(str(path)))
    s.act("Reopen from File → Open recent", "window.__scriptorum.refresh()", 1200)
    s.check("reopened text identical", s.state()["text"] == before)
    recent = s.act("Look at File → Open recent", "window.__u.menu('File'); window.__u.pick('Open recent'); window.__u.menuItems()")
    s.act("Close the menu", "document.body.click()")
    s.check("the adventure is in Open recent", any("ljuset.scav" in r for r in (recent or [])))
    s.act("Focus scene 3 (fishing hut)", "window.__u.focus('.el-scene > .el-fields .field-title input', 2)")
    insert_from_menu(s, "Information")
    s.act("Write a hint", "window.__u.select('.el-information .variant-select', -1, 'hint'); window.__u.type('.el-information .el-body', -1, 'A lantern with green glass hangs in the hut.')")
    s.flush()
    st = s.state()
    s.check("no build errors", st["errors"] == [])
    s.shot("visual")
    reply = json.loads(window.bridge.exportTo(str(OUT / "T-USE-02.pdf")))
    s.steps += 1
    s.log.append(f"{s.steps:>3}. Export PDF -> ok={reply.get('ok')}")
    s.check("PDF exported", bool(reply.get("ok")))
    (OUT / "T-USE-02.typ").write_text(st["text"], "utf-8")
    title_bar = window.windowTitle()
    s.log.append(f"     window title after export: {title_bar}")
    world_steps(s, window)
    look_steps(s, window)
    print_steps(s, window)
    module_steps(s, window)
    window_steps(s, window)
    portrait_steps(s, window)
    sub_heading_steps(s, window)
    codex_steps(s, window)
    return s.summary()


def answer_prompt(s: Scenario, text: str, choice: str = "") -> None:
    """Fill in the small name dialog of the codex, as a person would."""
    for _ in range(40):
        if s.js("document.getElementById('prompt-dialog').open"):
            break
        s.wait(50)
    s.act(f"Type the name “{text}”", f"window.__u.type('#prompt-input', 0, {json.dumps(text)})")
    if choice:
        s.act(f"Choose the type {choice}", f"window.__u.select('#prompt-choice', 0, {json.dumps(choice)})")
    s.act("OK", "window.__u.click('#prompt-ok')", 900)


def world_steps(s: Scenario, window: MainWindow) -> None:
    """Milestone 3 steps of T-USE-02: the Game Master builds the world of the
    adventure: codex entries, links in the text, a map and the handouts."""
    s.act("Open the Codex tab", "window.__u.click('#nav-codex')")
    s.act("New entry", "window.__u.click('#codex-panel .codex-actions button', 0)", 300)
    answer_prompt(s, "Märta the fisherwoman", "person")
    st = s.js("window.__scriptorum.world.viewOpen()")
    s.check("the new entry opens", bool(st) and st.get("kind") == "entry")
    s.act("Write her mood", "window.__u.type('#worldview-body .field-mood .field-input', 0, 'Worried')", 900)
    s.act("Back to the text", "window.__u.click('#worldview-back')", 300)
    s.act("New entry for the lake", "window.__u.click('#codex-panel .codex-actions button', 0)", 300)
    answer_prompt(s, "The frozen lake", "place")
    s.act("Back to the text", "window.__u.click('#worldview-back')", 300)
    s.act("Scene 1: type the location", "(() => { const i = window.__u.q('.el-scene .field-place input'); i.focus(); i.value = 'The frozen lake';"
          " i.dispatchEvent(new Event('change', {bubbles: true})); return true; })()", 700)
    s.act("Scene 1: add Märta as present", "(() => { const i = window.__u.q('.el-scene .field-people input'); i.focus(); i.value = 'märta the fisherwoman';"
          " i.dispatchEvent(new Event('change', {bubbles: true})); return true; })()", 700)
    s.flush()
    text = s.state()["text"] or ""
    s.check("the scene links the place and the person", 'place: "c-the-frozen-lake"' in text and "c-marta-the-fisherwoman" in text)
    # A mention inside a sentence, from the Insert menu.
    s.act("Click into the first paragraph", "window.__u.focus('#visual .el-scene .rich', 0)")
    items = insert_from_menu(s, "Mention")
    s.act("Choose Märta", "window.__u.pick('Märta the fisherwoman')", 500)
    s.flush()
    s.check("the mention is in the text", '#mention(entry: "c-marta-the-fisherwoman")' in (s.state()["text"] or ""))
    if "Mention" not in " ".join(items or []):
        s.note("bug", "Mention is missing from the Insert menu.", "M3")
    # A map from a picture.
    png = base64.b64encode(_scenario_png()).decode()
    reply = json.loads(window.bridge.createMapData("The lake", "lake.png", png))
    s.steps += 1
    s.log.append(f"{s.steps:>3}. Add a map from a picture -> ok={reply.get('ok')}")
    s.act("Refresh the codex", "window.__scriptorum.reloadAfterWorld()", 600)
    s.act("Open the map", "window.__scriptorum.world.openMap('m-the-lake')", 500)
    s.act("Pin tool", "window.__u.click('.map-tools button[data-tool=pin]')")
    s.act("Place a pin", "(() => { const svg = document.querySelector('.map-overlay'); const r = svg.getBoundingClientRect();"
          " svg.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2})); return true; })()", 900)
    s.act("Link the pin to the lake", "window.__u.select('.map-side select', 0, 'c-the-frozen-lake')", 900)
    m = window.bridge.session.world.maps().get("m-the-lake", {})
    s.check("the pin links the lake", any(i.get("entry") == "c-the-frozen-lake" for l in m.get("layers", []) for i in l["items"]))
    s.act("Put the map in the text", "window.__u.click('.map-head .small-btn', 0)", 800)
    s.flush()
    s.act("Mark the map as a handout", "window.__u.click('.el-map .field-check', 0)", 600)
    s.flush()
    s.shot("map")
    # Handouts.
    s.act("Open the Handouts tab", "window.__u.click('#nav-handouts')")
    handouts = s.js("[...document.querySelectorAll('#handouts-panel .handout-item')].map(b => b.textContent)")
    s.check("the map is handout #1", bool(handouts) and handouts[0].startswith("#1The lake"))
    s.act("Handouts only", "window.__u.click('#tb-handouts')", 2500)
    s.shot("handouts-only")
    s.check("the preview shows the player pages", window.bridge.player_preview is True)
    s.act("Back to the adventure", "window.__u.click('#tb-handouts')", 1500)
    reply = json.loads(window.bridge.exportHandoutsTo(str(OUT / "T-USE-02-handouts.pdf")))
    s.steps += 1
    s.log.append(f"{s.steps:>3}. Export handouts PDF -> ok={reply.get('ok')}")
    s.check("handouts PDF exported", bool(reply.get("ok")))
    s.note("friction", "Adding a map always goes through a file dialog; dragging a picture onto the Codex panel would be quicker.", "M5")


def look_steps(s: Scenario, window: MainWindow) -> None:
    """Milestone 4 steps of T-USE-02: the Game Master sets a rule apart in a
    Box, adds a quote and a pacing note from the toolbar's groups, tries
    another theme, works in dark mode and opens the example adventure."""
    s.act("Click into the first scene", "window.__u.focus('#visual .el-scene .rich', 0)")
    items = s.act("Toolbar → Boxes", "window.__u.click('#tb-group-boxes'); window.__u.menuItems()")
    s.check("Boxes lists Box and Quote", any(i.startswith("Box") for i in items) and any(i.startswith("Quote") for i in items))
    s.act("Boxes → Box", "window.__u.pick('Box')", 400)
    s.act("Box title", "window.__u.type('.el-box .field-title input', -1, 'Special rule: the ice')")
    s.act("Type in the box", "window.__u.type('.el-box .rich', -1, 'Each round on the ice, roll Agility.')")
    s.act("Toolbar → Boxes → Quote", "window.__u.click('#tb-group-boxes'); window.__u.pick('Quote')", 400)
    s.act("Signature", "window.__u.type('.el-quote .field-signature input', -1, 'Old Märta')")
    s.act("Type the quote", "window.__u.type('.el-quote .rich', -1, 'The ice remembers every step.')")
    items = s.act("Toolbar → Rules", "window.__u.click('#tb-group-rules'); window.__u.menuItems()")
    s.check("Rules lists the pacing note", any(i.startswith("Pacing note") for i in items))
    s.act("Rules → Pacing note", "window.__u.pick('Pacing note')", 400)
    s.act("Type the pacing note", "window.__u.type('.el-pacing .rich', -1, 'Give them about twenty minutes on the ice.')")
    s.flush()
    text = s.state()["text"] or ""
    s.check("box, quote and pacing note in the text", all(k in text for k in ("#box(", "#quote(", "#pacing[")))
    if "Each round on the ice" not in text or "The ice remembers" not in text:
        s.note("bug", "Typing into a new Box or Quote did not reach the text.", "M4")
    s.act("File → Settings… → Adventure", "window.__u.menu('File'); window.__u.pick('Settings…')", 600)
    s.act("Adventure section", "window.__u.click('#sn-adventure')", 400)
    s.act("Theme: Legends and Lattes", "window.__u.select('#set-theme', 0, 'scriptorum.legends-and-lattes')", 2500)
    s.shot("theme-lattes")
    s.check("theme switched", window.bridge.session.adventure.theme.id == "scriptorum.legends-and-lattes")
    s.act("Done", "window.__u.click('#settings-close')", 600)
    s.check("no build errors in the new theme", s.state()["errors"] == [])
    s.act("Dark mode from the menu bar", "window.__u.click('#mode-switch button[data-mode=dark]')", 800)
    s.shot("dark")
    s.check("the window is dark", s.js("document.documentElement.dataset.mode") == "dark")
    s.act("Light mode again", "window.__u.click('#mode-switch button[data-mode=light]')", 500)
    reply = json.loads(window.bridge.exportTo(str(OUT / "T-USE-02-lattes.pdf")))
    s.steps += 1
    s.log.append(f"{s.steps:>3}. Export PDF in Legends and Lattes -> ok={reply.get('ok')}")
    s.check("PDF exported in the new theme", bool(reply.get("ok")))
    s.act("Help → Open the example adventure", "window.__u.menu('Help'); window.__u.pick('Open the example adventure')", 4000)
    s.check("the example adventure is open", (s.state()["info"] or {}).get("title") == "Jätten Finns skuld")
    s.shot("example")


def print_steps(s: Scenario, window: MainWindow) -> None:
    """Milestone 5 (part A) steps of T-USE-02: the Game Master zooms the
    preview to read the small print and checks the installation."""
    s.act("Zoom in twice with +", "window.__u.click('#zoom-in'); window.__u.click('#zoom-in'); document.getElementById('zoom-value').textContent", 600)
    size = s.js("document.getElementById('zoom-value').textContent")
    s.check("the zoom bar shows a size", size.endswith("%"))
    s.act("Ctrl + wheel over the page", """(() => { const r = document.querySelector('#pages img.page').getBoundingClientRect();
        document.getElementById('preview-pane').dispatchEvent(new WheelEvent('wheel', {deltaY: -100, ctrlKey: true, clientX: r.left + 100, clientY: r.top + 100, bubbles: true, cancelable: true}));
        return document.getElementById('zoom-value').textContent; })()""", 400)
    s.check("Ctrl + wheel zooms in", s.js("document.getElementById('zoom-value').textContent") != size)
    s.shot("zoom")
    s.act("Whole page", "window.__u.click('#zoom-whole-page')", 400)
    s.check("Whole page shows the full page", s.js("document.querySelector('#pages img.page').getBoundingClientRect().height <= document.getElementById('preview-pane').clientHeight"))
    s.act("Help → Check installation…", "window.__u.menu('Help'); window.__u.pick('Check installation…')", 3000)
    s.check("every installation check passes", s.js("document.getElementById('check-summary').textContent") == "Every check passed.")
    s.shot("check-installation")
    s.act("Close", "window.__u.click('#check-close')", 300)
    # M5 part E (F19): the Game Master looks up how to make a theme of their own.
    s.act("Help → How to write a theme", "window.__u.menu('Help'); window.__u.pick('How to write a theme')", 800)
    s.check("the theme guide opens in the app", s.js("document.getElementById('guide-title')?.textContent") == "How to write a theme")
    s.act("Contents → Handout papers", "[...document.querySelectorAll('#guide-toc button')].find(b => b.textContent === 'Handout papers').click()", 400)
    s.check("the contents jump to the section", s.js("document.getElementById('guide-text').scrollTop > 0"))
    s.shot("guide-theme")
    s.act("Open How to write a game system", "window.__u.click('#guide-other')", 500)
    s.check("the game-system guide replaces it", s.js("document.getElementById('guide-title').textContent") == "How to write a game system")
    s.act("Close", "window.__u.click('#guide-close')", 300)
    s.check("the guide closes", s.js("document.getElementById('guide-dialog').open") is False)
    # M5 part B: the Game Master prepares the adventure for the printer.
    s.act("View → Show breaks", "window.__u.menu('View'); window.__u.pick('Show breaks')", 2500)
    s.check("Show breaks is on", window.bridge.show_breaks is True)
    s.shot("show-breaks")
    s.act("View → Hide breaks", "window.__u.menu('View'); window.__u.pick('Hide breaks')", 1500)
    s.act("Two pages", "window.__u.click('#zoom-spread')", 600)
    s.check("two-page spread", s.js("window.__scriptorum.zoom.get().spread") is True)
    s.act("One page again", "window.__u.click('#zoom-spread')", 300)
    s.act("File → Settings… → Adventure", "window.__u.menu('File'); window.__u.pick('Settings…')", 600)
    s.act("Adventure section", "window.__u.click('#sn-adventure')", 600)
    s.act("Classical proportions", "window.__u.click('#set-classical')", 1500)
    s.check("classical margins set", "inside" in ((window.bridge.session.adventure.settings.get("page") or {}).get("margin_mm") or {}))
    s.act("Footer line", "window.__u.type('#set-pageFooter', 0, 'Ljuset under isen')", 900)
    s.act("Done", "window.__u.click('#settings-close')", 1500)
    s.flush()
    for variant in ("booklet", "print-shop"):
        reply = json.loads(window.bridge.exportVariantTo(str(OUT / f"T-USE-02-{variant}.pdf"), variant))
        s.steps += 1
        s.log.append(f"{s.steps:>3}. Export {variant} PDF -> ok={reply.get('ok')}")
        s.check(f"{variant} PDF exported", bool(reply.get("ok")))


def module_steps(s: Scenario, window: MainWindow) -> None:
    """Milestone 6 part A steps of T-USE-02: a friend sends the Game Master
    a theme as a .scmod file. They install it in File ▸ Settings… ▸ Modules,
    see which adventures use the Vaesen theme, save the new theme as a file to
    pass on, and look at what disabling the Vaesen theme would mean."""
    import tempfile

    from tests.test_m6a import scmod, theme_folder

    folder = Path(tempfile.mkdtemp(prefix="use-module-"))
    package = scmod(theme_folder(folder, module_id="friend.harbour-ink", name="Harbour Ink"), folder)
    s.act("File → Settings… → Modules", "window.__u.menu('File'); window.__u.pick('Settings…')", 600)
    s.act("Modules section", "window.__scriptorum.showSection('modules')", 600)
    s.act("Install module… (the friend's .scmod)",
          f"window.__scriptorum.shell.installModule({json.dumps(str(package))})", 30000)
    status = s.js("document.getElementById('module-status').textContent")
    s.check("the theme is installed after its checks", status == "Harbour Ink 1.0.0 is installed.")
    s.check("it is listed", s.js("!!document.querySelector('tr[data-module=\"friend.harbour-ink@1.0.0\"]')"))
    s.shot("module-manager")
    used = s.js("document.querySelector('tr[data-module=\"scriptorum.vaesen@1.0.0\"] .module-used').textContent")
    s.check("the Vaesen theme names this adventure", "Ljuset under isen" in used)
    target = folder / "sent" / "harbour-ink.scmod"
    target.parent.mkdir()
    s.act("Save as .scmod file…",
          f"window.__scriptorum.shell.saveModule('friend.harbour-ink@1.0.0', {json.dumps(str(target))})", 800)
    s.check("the file is saved to pass on", target.is_file())
    s.act("Disable the Vaesen theme…",
          "document.querySelector('tr[data-module=\"scriptorum.vaesen@1.0.0\"] button[data-action=disable]').click()", 600)
    warning = s.js("document.getElementById('ask-text').textContent")
    s.check("the warning names the adventure", "Ljuset under isen" in (warning or ""))
    s.act("Cancel", "window.__u.click('#ask-cancel')", 300)
    s.check("nothing was disabled", not window.bridge.session.library.is_disabled("scriptorum.vaesen", "1.0.0"))
    s.act("Done", "window.__u.click('#settings-close')", 800)


def window_steps(s: Scenario, window: MainWindow) -> None:
    """Milestone 6 part B steps of T-USE-02: the Game Master works in full
    screen for a while, then looks up what Scriptorum is built on."""
    s.act("Full screen (toolbar button)", "window.__u.click('#tb-fullscreen')", 800)
    s.check("the window fills the screen", window.isFullScreen())
    s.act("Esc", "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); true", 800)
    s.check("Esc leaves full screen", not window.isFullScreen())
    s.act("Help → About Scriptorum", "window.__u.menu('Help'); window.__u.pick('About Scriptorum')", 800)
    s.check("the About window names the idea", "Idea by lyzio" in (s.js("document.getElementById('about-page-about').textContent") or ""))
    s.act("Under the hood", "window.__u.click('#about-tab-hood')", 400)
    s.act("Typst's licence", "[...document.querySelectorAll('#about-hood tr.about-row')].find(r => r.dataset.part === 'typst').click()", 500)
    s.check("Typst's licence text shows", "Apache License" in (s.js("document.getElementById('about-text').textContent") or ""))
    s.shot("about")
    s.act("Close", "window.__u.click('#about-close')", 300)


def portrait_steps(s: Scenario, window: MainWindow) -> None:
    """Milestone 6 part C1 steps of T-USE-02: the Game Master gives a person a
    portrait, adds a column break, and looks for a newer Scriptorum."""
    face = OUT / "face.png"
    face.write_bytes(_scenario_png(900, 1200))
    window.bridge.pick_portrait = lambda: str(face)  # stands in for the native file dialog
    s.act("Open the Codex tab", "window.__u.click('#nav-codex')")
    people = s.js("[...document.querySelectorAll('#codex-panel .codex-item')].map(b => b.textContent)") or []
    name = next((p for p in people if p.startswith("Johanna")), people[0] if people else "")
    s.act(f"Open {name}", f"[...document.querySelectorAll('#codex-panel .codex-item')].find(b => b.textContent === {json.dumps(name)}).click()", 600)
    s.check("the Person entry has a Portrait field", bool(s.js("!!document.querySelector('#worldview-body .field-portrait button')")))
    s.act("Choose a portrait (file dialog stands in)", "window.__u.click('#worldview-body .field-portrait button')", 900)
    s.act("Describe it for screen readers", "window.__u.type('#worldview-body .field-portrait-description .field-input', 0, 'A young woman in a dark coat')", 900)
    s.act("Back to the text", "window.__u.click('#worldview-back')", 1500)
    entry = next((e for e in window.bridge.session.world.entries().values() if e["title"] == name), {})
    s.check("the portrait and its description are stored", bool(entry.get("fields", {}).get("portrait"))
            and entry.get("fields", {}).get("portrait-description") == "A young woman in a dark coat")
    s.flush()
    s.check("no build errors with the portrait", s.state()["errors"] == [])
    s.shot("portrait")
    # A column break from the Insert menu (it used to print "(..) => ..").
    s.act("Click into the first scene", "window.__u.focus('#visual .el-scene .rich', 0)")
    insert_from_menu(s, "Column break")
    s.flush()
    text = s.state()["text"] or ""
    s.check("the column break is written with its brackets", "#column-break()" in text)
    reply = json.loads(window.bridge.exportTo(str(OUT / "T-USE-02-portrait.pdf")))
    s.steps += 1
    s.log.append(f"{s.steps:>3}. Export PDF -> ok={reply.get('ok')}")
    s.check("PDF exported with the portrait", bool(reply.get("ok")))
    # Help ▸ Check for updates… with the placeholder address.
    s.act("Help → Check for updates…", "window.__u.menu('Help'); window.__u.pick('Check for updates…')", 1200)
    message = s.js("document.getElementById('update-text').textContent") or ""
    s.check("it says no update address is set yet", message.startswith("No update address is set yet"))
    s.check("no request was made", window.bridge.update_requests == [])
    s.shot("updates")
    s.act("Close", "window.__u.click('#update-close')", 300)


def _in_order(text: str, *parts: str) -> bool:
    """Each part is in the text, in this order."""
    places = [text.find(p) for p in parts]
    return -1 not in places and places == sorted(places)


def sub_heading_steps(s: Scenario, window: MainWindow) -> None:
    """Milestone 6 part C2 steps of T-USE-02: the Game Master organises a
    scene with sub-headings, moves a part of it with the grip and in the
    outline, lowers one with Tab, and moves a block into a Box."""
    new_adventure(s, "The Salt Marsh", "Vaesen")
    s.js(DRAG_HELPERS)
    s.act("Scene title", "(() => { const i = document.querySelector('#visual .el-scene .field-title input'); i.focus(); i.select(); document.execCommand('insertText', false, 'The salt marsh'); return true; })()")
    s.act("Click into the scene", "window.__u.focus('#visual .el-scene .rich', 0)")
    s.act("Write the opening", "window.__u.type('#visual .el-scene .rich', 0, 'Mist hangs over the reeds.')")
    for title in ("The reeds", "The hut", "The causeway"):
        items = s.act("Toolbar → Structure", "window.__u.click('#tb-group-structure'); window.__u.menuItems()")
        if title == "The reeds":
            s.check("Structure lists the three sub-headings", all(f"Sub-heading {n}" in " ".join(items or []) for n in (1, 2, 3)))
        s.act("Structure → Sub-heading 1", "window.__u.pick('Sub-heading 1')", 400)
        s.act(f"Type “{title}”", f"(() => {{ const h = [...document.querySelectorAll('#visual .heading-edit')].find(x => !x.textContent); h.focus();"
              f" document.execCommand('insertText', false, {json.dumps(title)}); return true; }})()")
        insert_from_menu(s, "Paragraph")
        s.act("Type it", f"window.__u.type('#visual .el-scene .blk-paragraph .rich', -1, {json.dumps('Notes on ' + title.lower() + '.')})")
    s.flush()
    text = s.state()["text"] or ""
    s.check("three sub-headings in the text", all(f"=== {t}" in text for t in ("The reeds", "The hut", "The causeway")))
    s.act("Tab in “The hut” (lower it to Sub-heading 2)", """(() => { const h = [...document.querySelectorAll('#visual .heading-edit')].find(x => x.textContent === 'The hut');
        h.focus(); h.dispatchEvent(new KeyboardEvent('keydown', {key: 'Tab', bubbles: true, cancelable: true})); return true; })()""", 500)
    s.flush()
    s.check("“The hut” is a Sub-heading 2", "==== The hut" in (s.state()["text"] or ""))
    s.act("Open the Outline tab", "window.__u.click('#nav-outline')", 300)
    outline = s.js("[...document.querySelectorAll('#outline li[data-item] .outline-item')].map(b => b.textContent)") or []
    s.check("the outline lists the sub-headings under the scene", outline[1:] == ["The reeds", "The hut", "The causeway"])
    s.shot("sub-headings")
    s.act("Drag “The causeway” above “The reeds” in the outline", """(() => {
        const lis = [...document.querySelectorAll('#outline li.draggable')];
        const from = lis.find(l => l.textContent.includes('The causeway')), to = lis.find(l => l.textContent.includes('The reeds'));
        const r = to.getBoundingClientRect(); window.__drag(from, r.left + 60, r.top + 3); return true; })()""", 600)
    s.flush()
    text = s.state()["text"] or ""
    s.check("the causeway moved with its notes", _in_order(text, "=== The causeway", "Notes on the causeway", "=== The reeds"))
    s.act("Undo", "window.__scriptorum.undo()", 600)
    s.flush()
    s.log.append("     text after undo: " + json.dumps((s.state()["text"] or "")[:400], ensure_ascii=False))
    # The grip strip: drag “The reeds” (with The hut under it) below the causeway's notes.
    s.act("Drag “The reeds” by its grip below the causeway", """(() => {
        const sec = [...document.querySelectorAll('#visual section.blk-heading')].find(x => x.textContent.includes('The reeds'));
        const target = [...document.querySelectorAll('#visual .blk-paragraph')].find(x => x.textContent.includes('Notes on the causeway'));
        target.scrollIntoView({block: 'center'}); const r = target.getBoundingClientRect();
        window.__drag(sec.querySelector(':scope > .grip-strip'), r.left + 90, r.bottom - 3); return true; })()""", 600)
    s.flush()
    text = s.state()["text"] or ""
    s.check("the reeds moved with the hut under it", _in_order(text, "=== The causeway", "=== The reeds", "==== The hut"))
    (OUT / "T-USE-02-sub-headings.typ").write_text(text, "utf-8")
    # A Box, and a paragraph moved into it with Alt+→.
    s.act("Click into the causeway's notes", "window.__u.focus('#visual .blk-paragraph .rich', 0)")
    items = s.act("Toolbar → Boxes", "window.__u.click('#tb-group-boxes'); window.__u.menuItems()")
    s.act("Boxes → Box", "window.__u.pick('Box')", 400)
    s.act("Box title", "window.__u.type('.el-box .field-title input', -1, 'Crossing the causeway')")
    s.flush()
    text = s.state()["text"] or ""
    s.check("the Box is in the text", '#box(title: "Crossing the causeway")' in text)
    s.shot("grip-strip")
    reply = json.loads(window.bridge.exportTo(str(OUT / "T-USE-02-sub-headings.pdf")))
    s.steps += 1
    s.log.append(f"{s.steps:>3}. Export PDF -> ok={reply.get('ok')}")
    s.check("PDF with sub-headings exported", bool(reply.get("ok")))
    end_of_scene_steps(s, window)


def end_of_scene_steps(s: Scenario, window: MainWindow) -> None:
    """Milestone 6 part C3 steps of T-USE-02: the Game Master ends the scene
    to write an info page after it, gives it a sub-heading, and adds a
    handout that is only handed out."""
    s.act("Click into the causeway's notes", "window.__u.focus('#visual .blk-paragraph .rich', 0)")
    items = s.act("Toolbar → Structure", "window.__u.click('#tb-group-structure'); window.__u.menuItems()")
    s.check("Structure lists End of scene", "End of scene" in " ".join(items or []))
    s.act("Structure → End of scene", "window.__u.pick('End of scene')", 400)
    s.flush()
    text = s.state()["text"] or ""
    s.check("blocks after the cursor now stand after the scene", _in_order(text, "Notes on the causeway", "]\n", "Crossing the causeway", "=== The reeds"))
    (OUT / "T-USE-02-end-of-scene.typ").write_text(text, "utf-8")
    s.act("Toolbar → Structure", "window.__u.click('#tb-group-structure'); window.__u.menuItems()")
    s.act("Structure → Sub-heading 1", "window.__u.pick('Sub-heading 1')", 400)
    s.act("Type “About the marsh”", "(() => { const h = [...document.querySelectorAll('#visual .heading-edit')].find(x => !x.textContent); h.focus();"
          " document.execCommand('insertText', false, 'About the marsh'); return true; })()")
    s.flush()
    text = s.state()["text"] or ""
    s.check("a sub-heading outside the scene", "\n=== About the marsh\n" in text and text.index("=== About the marsh") > text.index("]\n"))
    s.check("the editor shows where the scene ends", (s.js("document.querySelectorAll('#visual .scene-end-line').length") or 0) >= 1)
    s.shot("end-of-scene")
    # A handout that is only handed out: the adventure PDF says when to give it.
    s.act("Click into the opening", "window.__u.focus('#visual .el-scene .rich', 0)")
    s.act("Toolbar → Handouts", "window.__u.click('#tb-group-handouts'); window.__u.menuItems()")
    s.act("Handouts → Handout", "window.__u.pick('Handout')", 400)
    s.act("Handout title", "window.__u.type('.el-handout .field-title input', -1, 'A note in the reeds')")
    s.act("Tick Only as handout", "(() => { const c = [...document.querySelectorAll('.el-handout label')].find(l => l.textContent.includes('Only as handout')).querySelector('input'); c.click(); return true; })()", 400)
    s.flush()
    text = s.state()["text"] or ""
    s.check("the handout is marked only as handout", "only-handout: true" in text)
    reply = json.loads(window.bridge.exportTo(str(OUT / "T-USE-02-end-of-scene.pdf")))
    s.steps += 1
    s.log.append(f"{s.steps:>3}. Export PDF -> ok={reply.get('ok')}")
    s.check("PDF with an info page and a give-out line exported", bool(reply.get("ok")))


def codex_steps(s: Scenario, window: MainWindow) -> None:
    """Milestone 6 part C4 steps of T-USE-02: the Game Master turns a loose
    person card into a codex person, gives her How to play, inserts a codex
    person and a clue through the pickers, and exports."""
    s.act("Click into the first scene", "window.__u.focus('#visual .el-scene .rich', 0)")
    insert_from_menu(s, "Person")
    s.act("Name", "window.__u.type('.el-person .field-name input', 0, 'Ebba Rask')")
    s.act("Mood", "window.__u.type('.el-person .field-mood input', 0, 'Restless')")
    loose = s.js("[...document.querySelectorAll('#visual .el-person')].length") or 0
    s.check("a loose person card to convert", loose >= 1)
    s.act("Write How to play", "window.__u.type('.el-person .field-how-to-play .rich', 0, 'Talks fast, never sits down.')")
    s.flush()
    s.act("Right-click the person card", """(() => { const sec = document.querySelector('#visual .el-person').closest('section.blk');
        const r = sec.getBoundingClientRect(); sec.querySelector('.rich, input').dispatchEvent(new MouseEvent('contextmenu',
        {bubbles: true, cancelable: true, clientX: r.left + 40, clientY: r.top + 8})); return window.__u.menuItems(); })()""")
    s.act("Convert to codex entry", "window.__u.pick('Convert to codex entry')", 900)
    if s.js("document.getElementById('ask-dialog').open"):
        s.act("Make a new entry", "window.__u.click('#ask-no')", 900)
    s.flush()
    text = s.state()["text"] or ""
    s.check("the person card became a codex card", "#card(entry:" in text)
    s.act("Click into the first scene", "window.__u.focus('#visual .el-scene .rich', 0)")
    insert_from_menu_raw = s.act("Insert menu", "window.__u.menu('Insert')")
    s.check("Insert menu lists Clue", "Clue" in " ".join(insert_from_menu_raw or []))
    s.act("Insert → Person", "window.__u.pick('Person')", 400)
    people = s.js("[...document.querySelectorAll('#pick-list .pick-item')].map(b => b.textContent)") or []
    s.check("the picker lists the codex people", len(people) >= 1)
    s.act("Picker → New codex person…", "window.__u.click('#pick-new')", 400)
    answer_prompt(s, "Greta Vik")
    s.act("Insert menu", "window.__u.menu('Insert')")
    s.act("Insert → Clue", "window.__u.pick('Clue')", 400)
    s.act("Picker → New clue…", "window.__u.click('#pick-new')", 400)
    answer_prompt(s, "The wet footprints")
    s.flush()
    text = s.state()["text"] or ""
    s.check("a card of the new codex person", '#card(entry: "c-greta-vik")' in text)
    s.check("a clue Information of the Hint variant", 'clue: "c-the-wet-footprints", variant: "hint"' in text)
    s.note("friction", "A new clue starts without a description. Text typed into its Information item stays with that item "
           "and is not saved as the clue's description, so a second item showing the same clue prints only its name "
           "until the clue is given a text in the codex.", "later")
    (OUT / "T-USE-02-codex.typ").write_text(text, "utf-8")
    s.shot("codex")
    reply = json.loads(window.bridge.exportTo(str(OUT / "T-USE-02-codex.pdf")))
    s.steps += 1
    s.log.append(f"{s.steps:>3}. Export PDF -> ok={reply.get('ok')}")
    s.check("PDF with codex cards and a clue exported", bool(reply.get("ok")))


def _scenario_png(width: int = 2400, height: int = 1600) -> bytes:
    import struct
    import zlib

    rows = b"".join(b"\x00" + bytes((236, 232, 220)) * width for _ in range(height))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def main() -> None:
    app = QApplication.instance() or QApplication([])
    session = Session.start()
    window = MainWindow(session, headless_test=True)
    window.bridge.confirm_discard = lambda: True
    window.resize(1440, 900)
    window.show()
    loop = QEventLoop()
    for _ in range(600):
        if window.bridge.ui_ready:
            break
        QTimer.singleShot(100, loop.quit)
        loop.exec()
    runner = Scenario("setup", window)
    runner.js(HELPERS)
    results = [use_01(window)]
    runner.js(HELPERS)
    results.append(use_02(window))
    (OUT / "findings.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), "utf-8")
    for result in results:
        print(f"\n== {result['scenario']}: {result['steps']} actions")
        print("\n".join(result["log"]))
        for f in result["findings"]:
            print(f"   FINDING [{f['kind']}] ({f['milestone']}): {f['text']}")
    window.close()


if __name__ == "__main__":
    main()
