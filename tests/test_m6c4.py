"""M6 part C4 (build M6-0.6.6): the codex points of F3, 11.3 and 11.4.

Convert to codex entry everywhere it fits (T-WORLD-30), with a taken name and
several fitting types (T-WORLD-31); clues as Information (T-WORLD-32); How to
play and the Clues line (T-WORLD-33); the text written back (T-SRC-20); the
Person, Creature and Clue pickers and the Codex card item (T-UI-42); codex
actions never fail silently (T-UI-43)."""

from __future__ import annotations

import hashlib
import io
import json
import re

import pytest
from pypdf import PdfReader

from scriptorum.core import source
from scriptorum.core.i18n import Strings
from scriptorum.core.modules import Library
from scriptorum.core.recent import RecentFiles
from scriptorum.core.session import Session
from scriptorum.core.world import WorldError
from tests.conftest import pack_sample, sample_text
from tests.test_m6c2 import BUNDLED, DRAG_HELPERS, FIND

# The m1-basic checksum of M6-0.6.4 and 0.6.5: Information without a clue
# and a person card without How to play print exactly as before.
M1_BASIC = "8d2c3db82974b610e7a745d1b21bc6ed2cf4fac4e32d379bb28c7c351f7c8d69"

# Paths in the sample m6-clues: the scene's body.
MARTA, ULRIKA_CARD, CLUE_OUTSIDE, CREATURE, LOOSE_ULRIKA = [0, 1], [0, 2], [0, 3], [0, 5], [0, 6]


def _open(session, tmp_path, name="m6-clues"):
    session.open(pack_sample(name, tmp_path))
    return session


def _text(session) -> str:
    return session.adventure.chapter_text(session.adventure.chapters[0])


def _pdf_words(session, tmp_path, variant="full", name="out.pdf") -> str:
    reply = session.export_pdf(tmp_path / name, variant=variant)
    assert reply["ok"], reply
    reader = PdfReader(io.BytesIO((tmp_path / name).read_bytes()))
    return re.sub(r"\s+", "", "".join(p.extract_text() for p in reader.pages))


# --- T-SRC-20 ------------------------------------------------------------------------------

@pytest.mark.unit
def test_T_SRC_20_written_back(session, tmp_path):
    """T-SRC-20: a clue Information with an empty body, a person card with
    How to play and a card that keeps fields parse and write back
    byte-identical; after an edit they are written again with their values."""
    _open(session, tmp_path)
    kinds = session.kinds()
    text = sample_text("m6-clues")
    doc = source.parse(text, kinds)
    assert source.serialize(doc, kinds) == text
    assert not [b for b in source._walk(doc["blocks"]) if b["type"] == "locked"]
    blocks = list(source._walk(doc["blocks"]))
    marta = blocks[2]
    assert marta["kind"] == "person" and marta["fields"]["how-to-play"].startswith("Wrings her hands")
    clue = blocks[6]
    assert clue["kind"] == "information" and clue["fields"]["clue"] == "c-broken-oar" and clue["body"] == ""
    for b in (marta, clue):
        b.pop("head_raw", None)
        source.mark_changed(b)
    for b in blocks[:1]:
        source.mark_changed(b)
    again = source.serialize(doc, kinds)
    assert 'how-to-play: [Wrings her hands; *always* answers a question with a question.]' in again
    assert '#information(known-by: ("c-anders-lind",), clue: "c-broken-oar", variant: "hint")[]' in again
    # A card that keeps a field its codex type lacks.
    kept = '#card(entry: "c-ulrika", linked-to: "The old mill", description: [Kept *here*.])[\n]\n'
    d = source.parse(kept, kinds)
    card = d["blocks"][0]
    assert card["kind"] == "card" and card["extra"] == {"linked-to": '"The old mill"', "description": "[Kept *here*.]"}
    assert source.serialize(d, kinds) == kept
    card.pop("head_raw")
    assert source.serialize(d, kinds) == kept
    # Older samples are unchanged.
    for name in ("m1-basic", "m3-world", "m4-look", "example-jattens-skuld"):
        old = sample_text(name)
        assert source.serialize(source.parse(old, kinds), kinds) == old


# --- T-WORLD-30 Convert to codex entry --------------------------------------------------------

@pytest.mark.integration
def test_T_WORLD_30_convert_person_creature_and_own_type(session, tmp_path):
    """T-WORLD-30: a loose person card, a creature and a block whose kind is
    the card element of an author-defined type become codex entries; the
    page prints the same text; Information stays in the card and is known by
    the new entry; a codex card offers nothing; each is one undo step."""
    _open(session, tmp_path)
    before = _pdf_words(session, tmp_path, name="before.pdf")
    original = _text(session)
    w = session.world
    assert [t["id"] for t in w.fitting_types("person")] == ["person", "t-river-folk"]
    assert [t["id"] for t in w.fitting_types("creature")] == ["creature"]
    assert w.fitting_types("card") == []
    with pytest.raises(WorldError):
        session.convert_to_entry(0, ULRIKA_CARD, "person")
    steps = len(session.world_history)

    r = session.convert_to_entry(0, MARTA, "person")
    assert len(session.world_history) == steps + 1
    entry = session.world.entry(r["id"])
    assert entry["type"] == "person" and entry["title"] == "Märta Holm"
    assert entry["fields"]["mood"] == "Nervous"
    assert entry["fields"]["how-to-play"].startswith("Wrings her hands")
    assert entry["fields"]["description"] == "Keeps the inn by the landing."
    text = _text(session)
    assert f'#card(entry: "{r["id"]}")[\n#information(variant: "secret")[She saw the ferryman' in text
    assert "#person(name: \"Märta Holm\"" not in text

    r2 = session.convert_to_entry(0, CREATURE, "creature")
    creature = session.world.entry(r2["id"])
    assert creature["fields"]["might"] == 3 and creature["fields"]["magic"] == 4
    assert creature["fields"]["weaknesses"] == "Steel thrown into the water."

    # The author's own type has no Description or How to play: they stay on the card.
    r3 = session.convert_to_entry(0, LOOSE_ULRIKA, "t-river-folk")
    assert r3["kept"] == ["description"]
    own = session.world.entry(r3["id"])
    assert own["type"] == "t-river-folk" and own["fields"] == {"name": "Ulrika", "mood": "nervous"}
    assert f'#card(entry: "{r3["id"]}", description: [Seen at the landing at dusk.])[' in _text(session)

    after = _pdf_words(session, tmp_path, name="after.pdf")
    assert after == before
    assert "WHATTHEYKNOW" in after.upper() and "Sawtheferrymanrowoutalone".lower() in after.lower()

    for _ in range(3):
        assert session.world_undo()
    assert _text(session) == original
    assert set(session.world.entries()) == {"c-ulrika", "c-anders-lind", "c-broken-oar", "c-ferry-ledger", "c-ferry-landing"}


# --- T-WORLD-31 a taken name, several types -----------------------------------------------

@pytest.mark.integration
def test_T_WORLD_31_taken_name_link_or_new(session, tmp_path):
    """T-WORLD-31: a card named like an existing entry lists every differing
    value; Link keeps the entry's values and fills its empty fields; New
    makes a second entry; two fitting types are both offered."""
    _open(session, tmp_path)
    info = session.convert_info(0, LOOSE_ULRIKA)
    assert [t["id"] for t in info["types"]] == ["person", "t-river-folk"]
    person = info["types"][0]
    assert person["taken"] == [{"id": "c-ulrika", "title": "Ulrika",
                                "differences": [{"field": "mood", "label": "Mood", "card": "nervous", "entry": "calm"}]}]
    assert session.t("codex.convertTaken", title="Ulrika") == "Link to the existing Ulrika, or make a new entry?"
    assert session.t("codex.convertDiff", label="Mood", card="nervous", entry="calm") == "Mood: card says ‘nervous’, entry says ‘calm’"

    r = session.convert_to_entry(0, LOOSE_ULRIKA, "person", "c-ulrika")
    assert r == {"id": "c-ulrika", "title": "Ulrika", "linked": True, "kept": []}
    fields = session.world.entry("c-ulrika")["fields"]
    assert fields["mood"] == "calm" and fields["description"] == "Seen at the landing at dusk."
    assert _text(session).count('#card(entry: "c-ulrika")[') == 2
    assert session.world_undo()
    assert "description" not in session.world.entry("c-ulrika")["fields"]

    r = session.convert_to_entry(0, LOOSE_ULRIKA, "person")
    assert r["id"] == "c-ulrika-2" and session.world.entry("c-ulrika-2")["fields"]["mood"] == "nervous"


# --- T-WORLD-32 clues as Information --------------------------------------------------------

@pytest.mark.integration
def test_T_WORLD_32_clue_information_prints_the_clue(session, tmp_path):
    """T-WORLD-32: a clue Information prints the clue's description with the
    clue's name, in full where written and as a pointer on the cards of
    others who know it; renaming and editing the clue changes every place;
    no empty-element warning; the accessible PDF passes."""
    _open(session, tmp_path)
    text = _text(session).replace('#information(variant: "public")', '#card(entry: "c-anders-lind")[\n]\n\n#information(variant: "public")')
    session.set_chapter_text(0, text)
    words = _pdf_words(session, tmp_path)
    assert "HINTTheferryledgerThelastpageoftheledger" in words
    assert "HINTThebrokenoarAnoarsnapped" in words
    # Anders knows the broken oar: a pointer with its page on his card.
    anders = words[words.index("ANDERSLIND"):]
    assert re.search(r"HINTThebrokenoar→p\.\d", anders)
    assert not [p for p in session.empty_elements() if p.key == "warning.build.emptyElement"]
    session.update_entry("c-broken-oar", {"fields": {"name": "The split oar", "description": "Split along the grain."}})
    words = _pdf_words(session, tmp_path, name="renamed.pdf")
    assert "HINTThesplitoarSplitalongthegrain." in words and "brokenoar" not in words.lower()
    assert _pdf_words(session, tmp_path, variant="accessible", name="ua.pdf")


@pytest.mark.integration
def test_T_WORLD_32_without_a_clue_prints_as_before(session, tmp_path):
    """T-WORLD-32: Information without a clue prints exactly as before: the
    m1-basic sample exports to the reference checksum."""
    _open(session, tmp_path, "m1-basic")
    assert session.export_pdf(tmp_path / "m1.pdf")["ok"]
    assert hashlib.sha256((tmp_path / "m1.pdf").read_bytes()).hexdigest() == M1_BASIC


@pytest.mark.unit
def test_T_WORLD_32_clue_is_a_reference(session, tmp_path):
    """T-WORLD-32: a clue in use cannot be deleted; the editor gets its text."""
    _open(session, tmp_path)
    with pytest.raises(WorldError):
        session.world.delete_entry("c-broken-oar")
    entry = next(e for e in session.codex()["entries"] if e["id"] == "c-broken-oar")
    assert entry["text"].startswith("An oar snapped clean in two")
    assert "text" not in next(e for e in session.codex()["entries"] if e["id"] == "c-ulrika")


# --- T-WORLD-33 How to play and the Clues line ---------------------------------------------

@pytest.mark.integration
def test_T_WORLD_33_how_to_play_and_clues(session, tmp_path):
    """T-WORLD-33: How to play prints under Mood with its label; the Clues
    line lists each clue once with its page; a card without either has no
    such line; the Clue entry and the clue overview say who knows it; How
    to play never reaches the handouts PDF."""
    _open(session, tmp_path)
    assert "how-to-play" in [f["name"] for f in session.world.types()["person"]["fields"]]
    words = _pdf_words(session, tmp_path)
    marta = words[words.index("MÄRTAHOLM"):words.index("ULRIKA")]
    assert "Mood:NervousHOWTOPLAYWringsherhands" in marta and "Clues:" not in marta
    ulrika = words[words.index("ULRIKA"):words.index("HINTThebrokenoarAnoar")]
    assert "Mood:calmHOWTOPLAYSpeaksslowly" in ulrika
    clues = re.search(r"Clues:(.*)", ulrika).group(1)
    assert re.fullmatch(r"Theferryledger→p\.\d,Thebrokenoar→p\.\d", clues)
    last = words[words.rindex("ULRIKA"):]
    assert "HOWTOPLAY" not in last[:60] and "Clues:" not in last[:120]
    overview = words[words.index("Clueoverview"):]
    assert "Knownby:AndersLind,Ulrika" in overview and "Knownby:Ulrika" in overview
    assert session.entry_info("c-broken-oar")["knownBy"] == [
        {"id": "c-anders-lind", "title": "Anders Lind", "type": "person"}, {"id": "c-ulrika", "title": "Ulrika", "type": "person"}]
    session.set_chapter_text(0, _text(session).rstrip()[:-1] + '\n#handout(title: "A note")[Meet me at the landing.]\n]\n')
    handouts = _pdf_words(session, tmp_path, variant="handouts", name="handouts.pdf")
    assert "Meetmeatthelanding." in handouts and "HOWTOPLAY" not in handouts


# --- the window ----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ui(tmp_path_factory):
    from PySide6.QtWidgets import QApplication

    from scriptorum.app.main import MainWindow
    from tests.test_ui_smoke import Driver

    folder = tmp_path_factory.mktemp("ui-m6c4")
    library = Library(folder / "library")
    library.install_bundled(BUNDLED)
    app = QApplication.instance() or QApplication([])
    session = Session(library, Strings.from_library(library), RecentFiles(folder / "recent.json"), folder / "build",
                      home=folder / "home")
    window = MainWindow(session, headless_test=True)
    window.bridge.confirm_discard = lambda: True
    window.bridge.crash_folder = folder / "logs"
    window.resize(1440, 900)
    window.show()
    driver = Driver(app, window)
    driver.folder = folder
    driver.wait_until(lambda: window.bridge.ui_ready, 60)
    yield driver
    window.close()


def open_clues(ui, sub: str):
    (ui.folder / sub).mkdir(exist_ok=True)
    path = pack_sample("m6-clues", ui.folder / sub)
    assert json.loads(ui.window.bridge.openPath(str(path)))["ok"]
    ui.run("window.__scriptorum.refresh()")
    ui.run("window.__scriptorum.setMode('visual')")
    ui.js(DRAG_HELPERS)
    ui.js(FIND)
    return ui.window.bridge.session


def text(ui) -> str:
    ui.run("window.__scriptorum.flush()")
    return ui.state()["text"]


def picker(ui, kind: str) -> list:
    ui.js(f"window.__scriptorum.insertFromCodex('{kind}'); true")
    ui.wait_until(lambda: ui.js("document.getElementById('pick-dialog').open"), 5)
    return ui.js("[...document.querySelectorAll('#pick-list .pick-item')].map(b => b.textContent)")


@pytest.mark.ui
def test_T_UI_42_person_picker(ui):
    """T-UI-42: Insert ▸ Person lists the codex's people, narrows as you
    type and inserts the picked entry's card; New codex person… makes the
    entry and its card in one undo step; Write a loose card here inserts a
    loose card."""
    session = open_clues(ui, "pick")
    ui.run("window.__scriptorum.focusBlock([0, 0])")
    assert picker(ui, "person") == ["Anders Lind", "Ulrika"]
    assert ui.js("document.getElementById('pick-new').textContent") == "New codex person…"
    assert ui.js("document.getElementById('pick-loose').textContent") == "Write a loose card here"
    ui.js("(() => { const i = document.getElementById('pick-search'); i.value = 'and'; i.dispatchEvent(new Event('input')); return true; })()")
    assert ui.js("[...document.querySelectorAll('#pick-list .pick-item')].map(b => b.textContent)") == ["Anders Lind"]
    ui.js("document.getElementById('pick-search').dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true})); true")
    ui.wait_until(lambda: '#card(entry: "c-anders-lind")' in text(ui), 5)
    ui.run("window.__scriptorum.undo()")
    assert '#card(entry: "c-anders-lind")' not in text(ui)
    # New codex person…
    ui.run("window.__scriptorum.focusBlock([0, 0])")
    picker(ui, "person")
    ui.js("document.getElementById('pick-new').click(); true")
    ui.wait_until(lambda: ui.js("document.getElementById('prompt-dialog').open"), 5)
    ui.js("document.getElementById('prompt-input').value = 'Olof Strand'; document.getElementById('prompt-ok').click(); true")
    ui.wait_until(lambda: '#card(entry: "c-olof-strand")' in text(ui), 10)
    assert "c-olof-strand" in session.world.entries()
    ui.run("window.__scriptorum.undo()")
    ui.wait_until(lambda: "c-olof-strand" not in session.world.entries(), 5)
    assert '#card(entry: "c-olof-strand")' not in text(ui)
    # Write a loose card here.
    before = text(ui).count("#person")
    ui.run("window.__scriptorum.focusBlock([0, 0])")
    picker(ui, "person")
    ui.js("document.getElementById('pick-loose').click(); true")
    ui.wait_until(lambda: text(ui).count("#person") == before + 1, 5)


@pytest.mark.ui
def test_T_UI_42_creature_clue_and_codex_card(ui):
    """T-UI-42: Insert ▸ Creature makes a codex creature; Insert ▸ Clue
    inserts a Hint linked to the clue, inside the person card that holds
    the cursor; the Codex card item lists only entries without a card of
    their own."""
    session = open_clues(ui, "pick2")
    ui.run("window.__scriptorum.focusBlock([0, 0])")
    assert picker(ui, "creature") == []
    ui.js("document.getElementById('pick-new').click(); true")
    ui.wait_until(lambda: ui.js("document.getElementById('prompt-dialog').open"), 5)
    ui.js("document.getElementById('prompt-input').value = 'The well hag'; document.getElementById('prompt-ok').click(); true")
    ui.wait_until(lambda: '#card(entry: "c-the-well-hag")' in text(ui), 10)
    assert session.world.entry("c-the-well-hag")["type"] == "creature"
    # A clue inside Märta's card (the cursor is in its fields); the new
    # creature card stands before it now.
    ui.run("window.__scriptorum.focusBlock([0, 2])")
    assert picker(ui, "clue") == ["The broken oar", "The ferry ledger"]
    assert ui.js("document.getElementById('pick-loose').classList.contains('hidden')")
    ui.js("[...document.querySelectorAll('#pick-list .pick-item')].find(b => b.textContent === 'The broken oar').click(); true")
    ui.wait_until(lambda: 'clue: "c-broken-oar", variant: "hint")[]\n]' in text(ui), 5)
    assert re.search(r'#person\(name: "Märta Holm".*?\)\[\n#information\(variant: "secret"\)\[[^\]]*\]\n\n#information\(clue: "c-broken-oar", variant: "hint"\)\[\]\n\]',
                     text(ui), re.S)
    # The editor shows the clue's text, with a button to edit the clue.
    assert ui.js("[...document.querySelectorAll('#visual .clue-body')].some(b => b.textContent.startsWith('An oar snapped'))")
    # Insert ▸ Clue is in the Insert menu.
    labels = [i["label"] for m in ui.js("window.__scriptorum.menuModel()") if m["key"] == "menu.insert" for i in m["items"]]
    assert "Clue" in labels and labels.index("Clue") == labels.index("Information") + 1
    # The Codex card lists places and clues, not people or creatures.
    ui.run("window.__scriptorum.focusBlock([0, 0])")
    ui.run("window.__scriptorum.insert('card')")
    offered = ui.js("[...[...document.querySelectorAll('#visual .el-card')].find(c => !c.querySelector('.codex-chip')).querySelectorAll('datalist option')].map(o => o.value)")
    assert sorted(offered) == ["The broken oar", "The ferry landing", "The ferry ledger"]


@pytest.mark.ui
def test_T_UI_42_convert_in_the_window(ui):
    """T-WORLD-30, T-WORLD-31 (window): right-click offers Convert to codex
    entry on a loose card and not on a codex card; with two fitting types it
    asks which; a taken name asks Link or New and lists the differences."""
    from tests.test_m6c2 import context_items, pick
    session = open_clues(ui, "convert")
    items = context_items(ui, "window.__el('person', 0)")
    assert "Convert to codex entry" in items
    ui.js("document.getElementById('menu-popup').classList.add('hidden'); true")
    card_items = context_items(ui, "window.__el('card', 0)")
    assert "Convert to codex entry" not in card_items
    ui.js("document.getElementById('menu-popup').classList.add('hidden'); true")
    # The second Ulrika: Person, then Link, then the differences.
    context_items(ui, "window.__el('person', 1)")
    pick(ui, "Convert to codex entry")
    ui.wait_until(lambda: ui.js("[...document.querySelectorAll('#menu-popup .menu-item')].map(b => b.textContent)") == ["Person", "River folk"], 5)
    pick(ui, "Person")
    ui.wait_until(lambda: ui.js("document.getElementById('ask-dialog').open"), 5)
    assert ui.js("document.getElementById('ask-text').textContent") == "Link to the existing Ulrika, or make a new entry?"
    ui.js("document.getElementById('ask-yes').click(); true")
    ui.wait_until(lambda: "card says" in (ui.js("document.getElementById('ask-dialog').open && document.getElementById('ask-text').textContent") or ""), 5)
    assert "Mood: card says ‘nervous’, entry says ‘calm’" in ui.js("document.getElementById('ask-text').textContent")
    ui.js("document.getElementById('ask-yes').click(); true")
    ui.wait_until(lambda: text(ui).count('#card(entry: "c-ulrika")[') == 2, 10)
    assert session.world.entry("c-ulrika")["fields"]["mood"] == "calm"
    ui.run("window.__scriptorum.undo()")
    ui.wait_until(lambda: text(ui).count('#card(entry: "c-ulrika")[') == 1, 5)
    assert "description" not in session.world.entry("c-ulrika")["fields"]


@pytest.mark.ui
def test_T_UI_43_never_silent(ui):
    """T-UI-43: in a read-only adventure codex actions say "This adventure is
    read-only"; an unexpected error shows a plain message, is written to a
    crash log and changes nothing."""
    session = open_clues(ui, "silent")
    bridge = ui.window.bridge
    # An unexpected error inside a codex action.
    real = session.world.__class__.create_entry

    def broken(self, *a, **k):
        raise RuntimeError("deliberate test failure")
    session.world.__class__.create_entry = broken
    try:
        before = set(session.world.entries())
        reply = json.loads(bridge.createEntry(json.dumps({"type": "person", "title": "Nobody"})))
        assert reply["ok"] is False and reply["error"].startswith("Scriptorum could not do that in the codex")
        assert set(session.world.entries()) == before
        logs = list((ui.folder / "logs").glob("crash-*.log"))
        assert logs and "deliberate test failure" in logs[-1].read_text("utf-8")
        # The window shows the message.
        ui.run("window.__scriptorum.focusBlock([0, 0])")
        picker(ui, "person")
        ui.js("document.getElementById('pick-new').click(); true")
        ui.wait_until(lambda: ui.js("document.getElementById('prompt-dialog').open"), 5)
        ui.js("document.getElementById('prompt-input').value = 'Nobody'; document.getElementById('prompt-ok').click(); true")
        ui.wait_until(lambda: ui.js("document.getElementById('message-dialog').open"), 5)
        assert ui.js("document.getElementById('message-text').textContent").startswith("Scriptorum could not do that in the codex")
        ui.js("document.getElementById('message-dialog').close(); true")
    finally:
        session.world.__class__.create_entry = real
    # Read-only.
    session.read_only = "openElsewhere"
    ui.run("window.__scriptorum.refresh()")
    reply = json.loads(bridge.createEntry(json.dumps({"type": "person", "title": "Nobody"})))
    assert reply["ok"] is False and reply["error"].startswith("This adventure is read-only")
    ui.js("(() => { const b = [...document.querySelectorAll('#codex-panel .codex-actions button')][0]; b.disabled = false; b.click(); return true; })()")
    ui.wait_until(lambda: ui.js("document.getElementById('message-dialog').open"), 5)
    assert ui.js("document.getElementById('message-text').textContent") == "This adventure is read-only"
    ui.js("document.getElementById('message-dialog').close(); true")
    session.read_only = None
