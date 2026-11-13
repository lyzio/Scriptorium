"use strict";
(() => {
  // bridge.ts
  var core = null;
  function connect() {
    return new Promise((resolve) => {
      new QWebChannel(qt.webChannelTransport, (channel) => {
        core = channel.objects.core;
        resolve();
      });
    });
  }
  function call(name, ...args) {
    return new Promise((resolve, reject) => {
      core[name](...args, (reply) => {
        try {
          resolve(reply ? JSON.parse(reply) : null);
        } catch (error) {
          reject(error);
        }
      });
    });
  }
  function on(signal, handler) {
    core[signal].connect((reply) => handler(reply ? JSON.parse(reply) : null));
  }

  // i18n.ts
  var table = {};
  function setStrings(strings) {
    table = strings;
  }
  function t(key, details = {}) {
    let text = table[key] ?? key;
    for (const [name, value] of Object.entries(details)) {
      text = text.split("{" + name + "}").join(String(value));
    }
    return text;
  }
  function applyStrings(root) {
    root.querySelectorAll("[data-i18n]").forEach((el) => {
      el.textContent = t(el.dataset.i18n);
    });
    root.querySelectorAll("[data-i18n-title]").forEach((el) => {
      const text = t(el.dataset.i18nTitle);
      el.title = text;
      if (!el.getAttribute("aria-label")) el.setAttribute("aria-label", text);
    });
    root.querySelectorAll("[data-i18n-aria]").forEach((el) => {
      el.setAttribute("aria-label", t(el.dataset.i18nAria));
    });
    root.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
      el.placeholder = t(el.dataset.i18nPlaceholder);
    });
  }

  // preview.ts
  var STEPS = [50, 67, 75, 90, 100, 110, 125, 150, 175, 200, 250, 300, 400];
  var MIN = 50;
  var MAX = 400;
  var PAD = 18;
  var zoom = "fit-width";
  var spread = false;
  var saveTimer = null;
  var $ = (id) => document.getElementById(id);
  var pane = () => $("preview-pane");
  var pages = () => $("pages");
  var clamp = (percent) => Math.max(MIN, Math.min(MAX, Math.round(percent)));
  function natural() {
    for (const img of pages().querySelectorAll("img.page")) {
      if (img.naturalWidth) return { w: img.naturalWidth, h: img.naturalHeight };
    }
    return null;
  }
  function widthFor(z) {
    const n = natural();
    if (!n) return null;
    const availableWidth = Math.max(80, (pane().clientWidth - 2 * PAD - (spread ? 6 : 0)) / (spread ? 2 : 1));
    if (z === "fit-width") return availableWidth;
    if (z === "whole-page") {
      const availableHeight = Math.max(80, pane().clientHeight - $("zoom-bar").offsetHeight - PAD - 14);
      return Math.min(availableWidth, availableHeight * n.w / n.h);
    }
    return n.w * z / 100;
  }
  function zoomPercent() {
    const n = natural();
    const width = widthFor(zoom);
    if (n && width) return Math.round(width / n.w * 100);
    return typeof zoom === "number" ? zoom : null;
  }
  function applyZoom() {
    const width = widthFor(zoom);
    pages().classList.toggle("spread", spread);
    $("zoom-spread")?.setAttribute("aria-pressed", String(spread));
    pages().classList.toggle("sized", width !== null);
    if (width !== null) {
      for (const img of pages().querySelectorAll("img.page")) img.style.width = `${width}px`;
    }
    const percent = zoomPercent();
    $("zoom-value").textContent = percent === null ? "" : t("zoom.percent", { percent });
    $("zoom-fit-width").setAttribute("aria-pressed", String(zoom === "fit-width"));
    $("zoom-whole-page").setAttribute("aria-pressed", String(zoom === "whole-page"));
    $("zoom-out").disabled = percent !== null && percent <= MIN;
    $("zoom-in").disabled = percent !== null && percent >= MAX;
  }
  function setZoom(next, anchor, remember = true) {
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
  function zoomStep(direction, anchor) {
    const current = zoomPercent() ?? 100;
    const next = direction > 0 ? STEPS.find((s) => s > current) ?? MAX : [...STEPS].reverse().find((s) => s < current) ?? MIN;
    setZoom(next, anchor);
  }
  async function loadZoom() {
    const reply = await call("previewZoom");
    zoom = reply?.zoom ?? "fit-width";
    applyZoom();
  }
  function setSpread(on2) {
    spread = on2;
    applyZoom();
  }
  function initZoom() {
    $("zoom-out").addEventListener("click", () => zoomStep(-1));
    $("zoom-in").addEventListener("click", () => zoomStep(1));
    $("zoom-fit-width").addEventListener("click", () => setZoom("fit-width"));
    $("zoom-whole-page").addEventListener("click", () => setZoom("whole-page"));
    $("zoom-spread")?.addEventListener("click", () => setSpread(!spread));
    pane().addEventListener("wheel", (event) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      event.preventDefault();
      const current = zoomPercent() ?? 100;
      const next = clamp(current * (event.deltaY < 0 ? 1.1 : 1 / 1.1));
      setZoom(next === current ? current + (event.deltaY < 0 ? 1 : -1) : next, { x: event.clientX, y: event.clientY });
    }, { passive: false });
    pane().addEventListener("keydown", (event) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      if (event.key === "+" || event.key === "=") zoomStep(1);
      else if (event.key === "-" || event.key === "_") zoomStep(-1);
      else if (event.key === "0") setZoom(100);
      else return;
      event.preventDefault();
      event.stopPropagation();
    });
    new ResizeObserver(() => {
      if (typeof zoom !== "number") applyZoom();
      else applyZoom();
    }).observe(pane());
  }

  // preview-window.ts
  var $2 = (id) => document.getElementById(id);
  function show(result) {
    if (!result) return;
    const banner = $2("preview-error");
    if (!result.ok) {
      banner.textContent = (result.errors ?? []).map((e) => e.text).join("\n");
      banner.classList.remove("hidden");
      return;
    }
    banner.classList.add("hidden");
    const box = $2("pages");
    const imgs = box.querySelectorAll("img");
    result.pages.forEach((url, i) => {
      let img = imgs[i];
      if (!img) {
        img = document.createElement("img");
        img.className = "page";
        img.addEventListener("load", () => applyZoom());
        box.append(img);
      }
      img.src = url;
    });
    for (let i = result.pages.length; i < imgs.length; i++) imgs[i].remove();
    applyZoom();
    document.body.dataset.buildCount = String(Number(document.body.dataset.buildCount || 0) + 1);
  }
  async function boot() {
    await connect();
    setStrings(await call("strings"));
    applyStrings(document);
    document.title = (await call("previewWindowTitle")).title;
    const app = await call("appSettings");
    const palette = app?.palette;
    const dark = app?.values?.mode === "dark" || app?.values?.mode === "system" && app?.systemDark;
    const vars = palette ? dark ? palette.darkVars : palette.lightVars : {};
    for (const [k, v] of Object.entries(vars)) document.documentElement.style.setProperty(k, v);
    initZoom();
    await loadZoom();
    on("buildFinished", show);
    on("documentChanged", async () => {
      document.title = (await call("previewWindowTitle")).title;
      await loadZoom();
    });
    show(await call("lastBuild"));
    window.__preview = { ready: true };
  }
  boot();
})();
