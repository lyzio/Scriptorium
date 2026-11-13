// Scriptorum's own dragging (F4.13, revised 12 November 2026, built in M6
// part C2).
//
// The operating system's drag-and-drop is not used, so the window can never
// lock up during a drag (it did on Linux). A drag is plain pointer events:
// the block lifts as a faint copy that follows the pointer, one line shows
// where it will land, no line and a "not allowed" pointer where it may not
// go, the list scrolls by itself near its top and bottom edge, and Esc or
// letting go outside the area cancels the drag with nothing moved.

/** Where a drop would land, as the caller works it out from the pointer. */
export interface DropTarget {
  ok: boolean;
  /** The drop line: viewport coordinates, from left to right at y. */
  line?: { left: number; right: number; y: number };
  /** Why it may not go here, for the status bar. */
  reason?: string;
  /** Carry out the move. */
  drop?: () => void;
}

export interface DragOptions {
  /** What follows the pointer: a copy of the block (it is cloned). */
  source: HTMLElement;
  /** The area a drop must land in; letting go outside it cancels. */
  area: HTMLElement;
  /** The element that scrolls near its edges. */
  scroller: HTMLElement;
  target(x: number, y: number): DropTarget | null;
  /** The reason a place is not allowed changed (null: allowed again). */
  onReason?(reason: string | null): void;
  onEnd?(moved: boolean): void;
}

const START_DISTANCE = 4; // pixels before a press becomes a drag
const EDGE = 40;          // pixels from the top or bottom edge that scroll
const SPEED = 14;         // pixels per step while scrolling

let active: { cancel(): void } | null = null;

/** True while a block is being dragged (the tests ask). */
export function dragging(): boolean {
  return active !== null;
}

/** Begin on pointerdown on a grip. Returns at once; the drag runs on its own. */
export function startDrag(down: PointerEvent, options: DragOptions): void {
  if (down.button !== 0 || active) return;
  // The press itself is not cancelled, so the mouse press that follows it
  // still closes an open menu; text selection is prevented by the grip's
  // style and, once the drag starts, by cancelling each move.
  const startX = down.clientX;
  const startY = down.clientY;
  let started = false;
  let x = startX;
  let y = startY;
  let ghost: HTMLElement | null = null;
  let line: HTMLElement | null = null;
  let target: DropTarget | null = null;
  let reason: string | null = null;
  let timer: number | null = null;
  const offsetY = Math.min(24, Math.max(0, startY - options.source.getBoundingClientRect().top));

  const setReason = (next: string | null) => {
    if (next === reason) return;
    reason = next;
    options.onReason?.(next);
  };

  const begin = () => {
    started = true;
    const rect = options.source.getBoundingClientRect();
    ghost = options.source.cloneNode(true) as HTMLElement;
    ghost.classList.add("drag-ghost");
    ghost.removeAttribute("id");
    ghost.querySelectorAll("[id]").forEach((n) => n.removeAttribute("id"));
    ghost.setAttribute("aria-hidden", "true");
    ghost.style.width = rect.width + "px";
    document.body.append(ghost);
    line = document.createElement("div");
    line.className = "drop-line hidden";
    document.body.append(line);
    options.source.classList.add("dragging");
    document.body.classList.add("dragging-block");
    timer = window.setInterval(autoScroll, 16);
  };

  const place = () => {
    if (!ghost || !line) return;
    ghost.style.left = x + 12 + "px";
    ghost.style.top = y - offsetY + "px";
    target = inside(options.area, x, y) ? options.target(x, y) : null;
    const ok = !!target?.ok && !!target.line;
    line.classList.toggle("hidden", !ok);
    document.body.classList.toggle("drag-not-allowed", !!target && !target.ok);
    if (ok && target!.line) {
      line.style.left = target!.line.left + "px";
      line.style.width = Math.max(20, target!.line.right - target!.line.left) + "px";
      line.style.top = target!.line.y - 1.5 + "px";
    }
    setReason(target && !target.ok ? target.reason ?? null : null);
  };

  function autoScroll(): void {
    const rect = options.scroller.getBoundingClientRect();
    let step = 0;
    if (y < rect.top + EDGE && y > rect.top - EDGE * 2) step = -SPEED;
    else if (y > rect.bottom - EDGE && y < rect.bottom + EDGE * 2) step = SPEED;
    if (!step) return;
    const before = options.scroller.scrollTop;
    options.scroller.scrollTop += step;
    if (options.scroller.scrollTop !== before) place();
  }

  const finish = (moved: boolean) => {
    window.removeEventListener("pointermove", onMove, true);
    window.removeEventListener("pointerup", onUp, true);
    window.removeEventListener("pointercancel", onCancel, true);
    document.removeEventListener("keydown", onKey, true);
    if (timer !== null) clearInterval(timer);
    ghost?.remove();
    line?.remove();
    options.source.classList.remove("dragging");
    document.body.classList.remove("dragging-block", "drag-not-allowed");
    if (reason) setReason(null);
    active = null;
    options.onEnd?.(moved);
  };

  function onMove(e: PointerEvent): void {
    x = e.clientX;
    y = e.clientY;
    if (!started) {
      if (Math.hypot(x - startX, y - startY) < START_DISTANCE) return;
      begin();
    }
    e.preventDefault();
    place();
  }

  function onUp(e: PointerEvent): void {
    x = e.clientX;
    y = e.clientY;
    if (!started) {
      finish(false);
      return;
    }
    e.preventDefault();
    place();
    const chosen = target;
    // Letting go outside the area, or where it may not go, moves nothing.
    const go = !!chosen && chosen.ok && inside(options.area, x, y);
    finish(go);
    if (go) chosen!.drop?.();
  }

  function onCancel(): void {
    finish(false);
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key !== "Escape") return;
    e.preventDefault();
    e.stopPropagation();
    finish(false);
  }

  window.addEventListener("pointermove", onMove, true);
  window.addEventListener("pointerup", onUp, true);
  window.addEventListener("pointercancel", onCancel, true);
  document.addEventListener("keydown", onKey, true);
  active = { cancel: () => finish(false) };
}

/** Cancel a drag in progress (closing the adventure, for example). */
export function cancelDrag(): void {
  active?.cancel();
}

function inside(area: HTMLElement, x: number, y: number): boolean {
  const r = area.getBoundingClientRect();
  return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom;
}
