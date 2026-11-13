// Spell check in Swedish and English (F4.8).
//
// The core knows the dictionaries; the interface collects the words of the
// editable text, asks which are wrong, and underlines them with the CSS
// Custom Highlight API, so the text itself is never changed by marking it.

const WORD = /[\p{L}](?:[\p{L}]|['’-](?=[\p{L}]))*/gu;

export class Spelling {
  private wrong = new Set<string>();
  private timer: number | null = null;

  constructor(private root: HTMLElement, private check: (words: string[]) => Promise<{ ready: boolean; wrong: string[] }>) {}

  /** Check again a little after typing stops. */
  schedule(delay = 600): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = window.setTimeout(() => {
      this.timer = null;
      this.run();
    }, delay);
  }

  private textNodes(): Text[] {
    const nodes: Text[] = [];
    this.root.querySelectorAll<HTMLElement>("[contenteditable=true]").forEach((box) => {
      const walker = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
      for (let n = walker.nextNode(); n; n = walker.nextNode()) {
        if (!(n.parentElement && n.parentElement.closest(".ichip"))) nodes.push(n as Text);
      }
    });
    return nodes;
  }

  async run(): Promise<void> {
    const nodes = this.textNodes();
    const words = new Set<string>();
    for (const node of nodes) for (const m of (node.data.match(WORD) ?? [])) words.add(m);
    const reply = await this.check([...words]);
    this.wrong = new Set(reply.wrong);
    this.paint(nodes);
  }

  private paint(nodes: Text[]): void {
    const registry = (CSS as any).highlights;
    const HighlightClass = (window as any).Highlight;
    if (!registry || !HighlightClass) return;
    const ranges: Range[] = [];
    for (const node of nodes) {
      for (const m of node.data.matchAll(WORD)) {
        if (!this.wrong.has(m[0])) continue;
        const range = document.createRange();
        range.setStart(node, m.index!);
        range.setEnd(node, m.index! + m[0].length);
        ranges.push(range);
      }
    }
    registry.set("misspelt", new HighlightClass(...ranges));
    document.body.dataset.misspelt = String(ranges.length);
  }

  /** The misspelt word under a point, with its range, if any. */
  wordAt(x: number, y: number): { word: string; range: Range } | null {
    const caret = (document as any).caretRangeFromPoint?.(x, y) as Range | null;
    const node = caret?.startContainer;
    if (!caret || !node || node.nodeType !== Node.TEXT_NODE) return null;
    const text = (node as Text).data;
    for (const m of text.matchAll(WORD)) {
      const start = m.index!;
      const end = start + m[0].length;
      if (caret.startOffset >= start && caret.startOffset <= end && this.wrong.has(m[0])) {
        const range = document.createRange();
        range.setStart(node, start);
        range.setEnd(node, end);
        return { word: m[0], range };
      }
    }
    return null;
  }

  isWrong(word: string): boolean {
    return this.wrong.has(word);
  }
}
