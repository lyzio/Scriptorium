"""Drag with pointer events, as a person does (F4.13, M6 part C2).

Scriptorum drags blocks with its own pointer handling, not the system's
drag-and-drop (which could lock the window up on Linux), so the tests press
on a grip, move the pointer in steps and let go, exactly like a mouse.
"""

# DRAG(grip, x, y, opts): press on the grip, move to (x, y) in steps and let
# go; opts.release = false keeps the drag going (for Esc and the checks made
# mid-drag); opts.steps sets how many moves. Returns nothing.
HELPERS = r"""
window.__drag = (grip, x, y, opts) => {
  opts = opts || {};
  const r = grip.closest('section.blk, li') ? grip.closest('section.blk, li').getBoundingClientRect() : grip.getBoundingClientRect();
  const sx = r.left + 6, sy = r.top + 8;
  const ev = (type, cx, cy) => new PointerEvent(type, {bubbles: true, cancelable: true, clientX: cx, clientY: cy, button: 0, buttons: 1, pointerId: 1, isPrimary: true, pointerType: 'mouse'});
  grip.dispatchEvent(ev('pointerdown', sx, sy));
  // A real mouse press also sends mousedown, which closes open menus.
  grip.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, clientX: sx, clientY: sy, button: 0}));
  const steps = opts.steps || 6;
  for (let i = 1; i <= steps; i++) window.dispatchEvent(ev('pointermove', sx + (x - sx) * i / steps, sy + (y - sy) * i / steps));
  if (opts.release !== false) window.dispatchEvent(ev('pointerup', x, y));
};
window.__dragMove = (x, y) => window.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, buttons: 1, pointerId: 1, isPrimary: true}));
window.__dragUp = (x, y) => window.dispatchEvent(new PointerEvent('pointerup', {bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, pointerId: 1, isPrimary: true}));
window.__strip = (el) => el.closest('section.blk').querySelector(':scope > .grip-strip');
true
"""
