// Zoom in the live preview (design document F7.2; detailed 11 November 2026,
// built in M5).
//
// A zoom bar on top of the preview pane has − and + buttons, the current size
// (for example "125 %"), Fit width and Whole page. Ctrl and the scroll wheel
// (⌘ on the Mac) zoom around the pointer, and Ctrl + plus, Ctrl + minus and
// Ctrl + 0 work while the preview has focus. The pages are vector drawings
// (SVG, 3.3), so text stays sharp from 50 % to 400 %. The zoom holds while
// the author types and the preview refreshes, and the app remembers it for
// each adventure, outside the .scav file.

import { call } from "./bridge";
import { t } from "./i18n";

export type Zoom = "fit-width" | "whole-page" | number;

const STEPS = [50, 67, 75, 90, 100, 110, 125, 150, 175, 200, 250, 300, 400];
const MIN = 50;
const MAX = 400;
const PAD = 18; // the preview pane's padding

let zoom: Zoom = "fit-width";
let spread = false; // F7.2: two pages side by side, as in a printed book
let saveTimer: number | null = null;

const $ = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
const pane = () => $("preview-pane");
const pages = () => $("pages");
const clamp = (percent: number) => Math.max(MIN, Math.min(MAX, Math.round(percent)));

/** The size of a page at 100 %, in CSS pixels (an SVG page of 595 pt is 794 px). */
function natural(): { w: number; h: number } | null {
  for (const img of pages().querySelectorAll<HTMLImageElement>("img.page")) {
    if (img.naturalWidth) return { w: img.naturalWidth, h: img.naturalHeight };
  }
  return null;
}

function widthFor(z: Zoom): number | null {
  const n = natural();
  if (!n) return null;
  const availableWidth = Math.max(80, (pane().clientWidth - 2 * PAD - (spread ? 6 : 0)) / (spread ? 2 : 1));
  if (z === "fit-width") return availableWidth;
  if (z === "whole-page") {
    const availableHeight = Math.max(80, pane().clientHeight - $("zoom-bar").offsetHeight - PAD - 14);
    return Math.min(availableWidth, (availableHeight * n.w) / n.h);
  }
  return (n.w * z) / 100;
}

/** The size the pages are shown at, in per cent of their real size. */
export function zoomPercent(): number | null {
  const n = natural();
  const width = widthFor(zoom);
  if (n && width) return Math.round((width / n.w) * 100);
  return typeof zoom === "number" ? zoom : null;
}

/** Give every page its width and show the size on the zoom bar. Called
 * again whenever the preview refreshes, so the zoom holds while typing. */
export function applyZoom(): void {
  const width = widthFor(zoom);
  pages().classList.toggle("spread", spread);
  $("zoom-spread")?.setAttribute("aria-pressed", String(spread));
  pages().classList.toggle("sized", width !== null);
  if (width !== null) {
    for (const img of pages().querySelectorAll<HTMLImageElement>("img.page")) img.style.width = `${width}px`;
  }
  const percent = zoomPercent();
  $("zoom-value").textContent = percent === null ? "" : t("zoom.percent", { percent });
  $("zoom-fit-width").setAttribute("aria-pressed", String(zoom === "fit-width"));
  $("zoom-whole-page").setAttribute("aria-pressed", String(zoom === "whole-page"));
  $<HTMLButtonElement>("zoom-out").disabled = percent !== null && percent <= MIN;
  $<HTMLButtonElement>("zoom-in").disabled = percent !== null && percent >= MAX;
}

/** Change the zoom. The point under `anchor` (the pointer) stays where it
 * is; without one, the middle of the pane does. */
export function setZoom(next: Zoom, anchor?: { x: number; y: number }, remember = true): void {
  const box = pages();
  const frame = pane().getBoundingClientRect();
  const at = anchor ?? { x: frame.left + frame.width / 2, y: frame.top + frame.height / 2 };
  const before = box.getBoundingClientRect();
  const fx = before.width ? (at.x - before.left) / before.width : 0.5;
  const fy = before.height ? (at.y - before.top) / before.height : 0;
  zoom = typeof next === "number" ? clamp(next) : next;
  applyZoom();
  const after = box.getBoundingClientRect();
  pane().scrollLeft += after.left + fx * after.width - at.x;
  pane().scrollTop += after.top + fy * after.height - at.y;
  if (remember) {
    if (saveTimer !== null) clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => {
      saveTimer = null;
      call("setPreviewZoom", JSON.stringify(zoom));
    }, 300);
  }
}

/** One step on the − and + buttons. */
export function zoomStep(direction: 1 | -1, anchor?: { x: number; y: number }): void {
  const current = zoomPercent() ?? 100;
  const next = direction > 0 ? STEPS.find((s) => s > current) ?? MAX : [...STEPS].reverse().find((s) => s < current) ?? MIN;
  setZoom(next, anchor);
}

/** The zoom this adventure was last looked at with (kept outside its file). */
export async function loadZoom(): Promise<void> {
  const reply = await call("previewZoom");
  zoom = reply?.zoom ?? "fit-width";
  applyZoom();
}

/** After a first save the adventure has a place to be remembered under. */
export function rememberZoom(): void {
  call("setPreviewZoom", JSON.stringify(zoom));
}

/** F7.2 (M5): the two-page spread. */
export function setSpread(on: boolean): void {
  spread = on;
  applyZoom();
}

export function isSpread(): boolean {
  return spread;
}

export function currentZoom(): Zoom {
  return zoom;
}

export function initZoom(): void {
  $("zoom-out").addEventListener("click", () => zoomStep(-1));
  $("zoom-in").addEventListener("click", () => zoomStep(1));
  $("zoom-fit-width").addEventListener("click", () => setZoom("fit-width"));
  $("zoom-whole-page").addEventListener("click", () => setZoom("whole-page"));
  $("zoom-spread")?.addEventListener("click", () => setSpread(!spread));
  // Ctrl and the scroll wheel (⌘ on the Mac) zoom around the pointer.
  pane().addEventListener("wheel", (event) => {
    if (!(event.ctrlKey || event.metaKey)) return;
    event.preventDefault();
    const current = zoomPercent() ?? 100;
    const next = clamp(current * (event.deltaY < 0 ? 1.1 : 1 / 1.1));
    setZoom(next === current ? current + (event.deltaY < 0 ? 1 : -1) : next, { x: event.clientX, y: event.clientY });
  }, { passive: false });
  // Ctrl + plus, Ctrl + minus and Ctrl + 0 while the preview has focus.
  pane().addEventListener("keydown", (event) => {
    if (!(event.ctrlKey || event.metaKey)) return;
    if (event.key === "+" || event.key === "=") zoomStep(1);
    else if (event.key === "-" || event.key === "_") zoomStep(-1);
    else if (event.key === "0") setZoom(100);
    else return;
    event.preventDefault();
    event.stopPropagation();
  });
  // Fit width and Whole page follow the pane when it changes size.
  new ResizeObserver(() => {
    if (typeof zoom !== "number") applyZoom();
    else applyZoom();
  }).observe(pane());
}
